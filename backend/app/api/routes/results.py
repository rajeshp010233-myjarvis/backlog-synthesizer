"""Result retrieval routes.

prompt_traces are intentionally excluded from the public response — they
contain full system prompts and raw model outputs that must not be exposed
to API consumers. They remain persisted in Redis for internal audit access.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from app.agents.harness import verify_audit_chain
from app.config import get_settings
from app.security import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/results",
    tags=["results"],
    dependencies=[Depends(require_api_key)],
)


async def _validate_session(session_id: str, request: Request) -> None:
    if not get_settings().session_id_is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session ID format.")
    exists = await request.app.state.redis.exists(f"session:{session_id}:created")
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")


@router.get("/{session_id}")
async def get_results(session_id: str, request: Request) -> dict:
    await _validate_session(session_id, request)
    r = request.app.state.redis

    status_raw = await r.get(f"session:{session_id}:status")
    current_status = (status_raw or b"pending").decode()

    if current_status != "done":
        # Return 200 with a status field rather than abusing 4xx for normal flow
        return {"session_id": session_id, "status": current_status, "ready": False}

    result_raw = await r.get(f"session:{session_id}:result")
    if not result_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No result found for this session.")

    result = json.loads(result_raw)

    # Build per-agent timing summary from harness chain entries
    chain = [e for e in result.get("audit_log", []) if e.get("tool") == "harness_chain"]
    agent_timings = {e["agent"]: e.get("elapsed_s") for e in chain if e.get("agent")}
    total_elapsed = round(sum(e.get("elapsed_s", 0) for e in chain), 2)

    # prompt_traces are never returned to API consumers
    return {
        "session_id":        session_id,
        "status":            "done",
        "ready":             True,
        "user_stories":      result.get("user_stories", []),
        "extracted_intents": result.get("extracted_intents", []),
        "gap_report":        result.get("gap_report", {}),
        "evaluation_scores": result.get("evaluation_scores", {}),
        "audit_log":         result.get("audit_log", []),
        "story_iterations":  result.get("story_iterations", []),
        "retry_count":       result.get("retry_count", 0),
        "halt_reason":       result.get("halt_reason", ""),
        "timing": {
            "agents":        agent_timings,
            "total_elapsed_s": total_elapsed,
        },
    }


@router.get("/{session_id}/export")
async def export_results(session_id: str, request: Request, format: str = "json"):
    await _validate_session(session_id, request)

    result_raw = await request.app.state.redis.get(f"session:{session_id}:result")
    if not result_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No result found.")

    result = json.loads(result_raw)
    result.pop("prompt_traces", None)  # never export traces

    if format == "json":
        return Response(
            content=json.dumps(result, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=backlog_{session_id}.json"},
        )

    if format == "markdown":
        return Response(
            content=_to_markdown(result),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=backlog_{session_id}.md"},
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supported formats: json, markdown")


@router.get("/{session_id}/audit/verify")
async def verify_audit(session_id: str, request: Request) -> dict:
    """Verify the tamper-evident chain of the audit log for a completed session."""
    await _validate_session(session_id, request)
    result_raw = await request.app.state.redis.get(f"session:{session_id}:result")
    if not result_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No result found for this session.")
    audit_log = json.loads(result_raw).get("audit_log", [])
    return verify_audit_chain(audit_log)


def _to_markdown(result: dict) -> str:
    from app.agents.harness import verify_audit_chain

    session_id = result.get("session_id", "unknown")
    lines = [
        "# Backlog Synthesizer — Pipeline Report",
        "",
        f"**Session:** `{session_id}`  ",
        f"**Retry passes:** {result.get('retry_count', 0)}  ",
        "",
        "---",
        "",
    ]

    # ── User Stories ───────────────────────────────────────────────────────────
    stories = result.get("user_stories", [])
    lines += [f"## User Stories ({len(stories)} generated)", ""]
    for s in stories:
        tags = ", ".join(s.get("system_tags", []) + s.get("feature_tags", []))
        lines += [
            f"### [{s.get('id', '?')}] {s.get('title', '')}",
            "",
            f"**Type:** {s.get('type', '?')} | **Priority:** {s.get('priority', '?')}",
            "",
            s.get("description", ""),
            "",
        ]
        acs = s.get("acceptance_criteria", [])
        if acs:
            lines.append("**Acceptance Criteria:**")
            lines.append("")
            for ac in acs:
                lines.append(f"- **Given** {ac.get('given', '')} — **When** {ac.get('when', '')} — **Then** {ac.get('then', '')}")
                for ec in ac.get("edge_cases", []):
                    lines.append(f"  - *Edge case:* {ec}")
            lines.append("")
        if tags:
            lines.append(f"**Tags:** `{tags}`")
        src_ids = s.get("source_intent_ids", [])
        if src_ids:
            lines.append(f"**Source intents:** {', '.join(f'`{i}`' for i in src_ids)}")
        lines.append("")

    # ── Gap & Conflict Report ─────────────────────────────────────────────────
    gap = result.get("gap_report", {})
    lines += [
        "---",
        "",
        "## Gap & Conflict Report",
        "",
        f"**Coverage Score:** {gap.get('coverage_score', 0):.0%}",
        "",
        gap.get("summary", ""),
        "",
    ]
    conflicts = gap.get("conflicts", [])
    if conflicts:
        lines += [f"### Conflicts ({len(conflicts)})", ""]
        for c in conflicts:
            lines += [
                f"- **{c.get('conflict_type', '?').upper()}** — `{c.get('existing_ticket_id', '?')}`",
                f"  - {c.get('description', '')}",
                f"  - *Recommendation:* {c.get('recommendation', '')}",
                "",
            ]
    gaps = gap.get("gaps", [])
    if gaps:
        lines += [f"### Gaps ({len(gaps)})", ""]
        for g in gaps:
            lines += [
                f"- **{g.get('gap_type', '?').upper()}** — {g.get('request', '')}",
                f"  - {g.get('description', '')}",
                "",
            ]

    # ── Evaluation Scores ─────────────────────────────────────────────────────
    scores = result.get("evaluation_scores", {})
    lines += [
        "---",
        "",
        "## Evaluation Scores",
        "",
        "| Metric | Score |",
        "|--------|-------|",
        f"| **Overall** | **{scores.get('overall_score', 0):.1f} / 5** |",
        f"| Clarity | {scores.get('clarity_score', 0):.1f} / 5 |",
        f"| Feasibility | {scores.get('feasibility_score', 0):.1f} / 5 |",
        f"| Traceability | {scores.get('traceability_score', 0):.1f} / 5 |",
        f"| AC Completeness | {scores.get('ac_completeness_pct', 0):.0f}% |",
        f"| Feature Tag F1 | {scores.get('feature_tag_f1', 0):.3f} |",
        f"| Conflict Detection F1 | {scores.get('conflict_detection_f1', 0):.3f} |",
        "",
        "**Evaluator Feedback:**",
        "",
        scores.get("feedback", ""),
        "",
    ]

    # ── Pipeline Timing ───────────────────────────────────────────────────────
    audit_log  = result.get("audit_log", [])
    chain_entries_all = [e for e in audit_log if e.get("tool") == "harness_chain"]
    if chain_entries_all:
        total_elapsed = sum(e.get("elapsed_s", 0) for e in chain_entries_all)
        lines += [
            "---", "",
            "## Pipeline Timing", "",
            "| Agent | Status | Elapsed |",
            "|-------|--------|---------|",
        ]
        for e in chain_entries_all:
            lines.append(
                f"| {e.get('agent', '?')} | {e.get('status', '?')} | {e.get('elapsed_s', '?')}s |"
            )
        lines += [
            f"| **Total** | | **{total_elapsed:.2f}s** |",
            "",
        ]

    # ── Audit Log ─────────────────────────────────────────────────────────────
    chain_check = verify_audit_chain(audit_log)
    integrity_badge = "✅ INTACT" if chain_check["valid"] else f"⚠️ BROKEN at entry {chain_check.get('broken_at')}"

    lines += [
        "---",
        "",
        "## Audit Log",
        "",
        f"**Chain integrity:** {integrity_badge}  ",
        f"**Chain entries:** {chain_check['entries']}  ",
        "",
    ]
    if not chain_check["valid"] and chain_check.get("error"):
        lines += [f"> ⚠️ {chain_check['error']}", ""]

    # Group by agent
    agent_order = ["ingestion_agent", "story_writer", "gap_detector", "evaluator", "orchestrator", "harness"]
    agent_entries: dict[str, list] = {}
    chain_entries: list = []
    for entry in audit_log:
        if entry.get("tool") == "harness_chain":
            chain_entries.append(entry)
        else:
            a = entry.get("agent", "unknown")
            agent_entries.setdefault(a, []).append(entry)

    # Print agent sections in pipeline order
    seen = set()
    ordered_agents = [a for a in agent_order if a in agent_entries] + \
                     [a for a in agent_entries if a not in agent_order]
    for agent in ordered_agents:
        if agent in seen:
            continue
        seen.add(agent)
        entries = agent_entries[agent]
        agent_label = agent.replace("_", " ").title()
        lines += [f"### {agent_label}", ""]
        for e in entries:
            lines += [
                f"**Operation:** `{e.get('tool', '?')}`  ",
                f"**Time:** {e.get('timestamp', '?')}  ",
                f"**Summary:** {e.get('reasoning', '')}  ",
            ]
            details = e.get("details", {})
            if details:
                # Provider / model
                provider = details.get("provider")
                model    = details.get("model")
                if provider and model:
                    lines.append(f"**LLM:** {provider} / `{model}`  ")
                tok_in  = details.get("approx_input_tokens")
                tok_out = details.get("approx_output_tokens")
                if tok_in is not None:
                    lines.append(f"**Tokens:** ~{tok_in} in / ~{tok_out} out  ")
                # Counts table
                count_keys = [
                    ("transcripts", "Transcripts"),
                    ("batches", "Batches"),
                    ("llm_calls", "LLM calls"),
                    ("wiki_docs", "Wiki docs"),
                    ("constraints_extracted", "Constraints"),
                    ("raw_intents", "Raw intents"),
                    ("final_intents", "Final intents"),
                    ("intents_used", "Intents used"),
                    ("stories_generated", "Stories generated"),
                    ("stories_analysed", "Stories analysed"),
                    ("stories_evaluated", "Stories evaluated"),
                    ("existing_tickets", "Existing tickets"),
                    ("conflicts_found", "Conflicts"),
                    ("gaps_found", "Gaps"),
                ]
                rows = [(label, details[key]) for key, label in count_keys if key in details]
                if rows:
                    lines += ["", "| Metric | Value |", "|--------|-------|"]
                    for label, val in rows:
                        lines.append(f"| {label} | {val} |")
                    lines.append("")
                # Scores block (evaluator)
                score_block = details.get("scores")
                if score_block:
                    lines += ["", "**Score breakdown:**", ""]
                    lines += ["| Metric | Score |", "|--------|-------|"]
                    for k, v in score_block.items():
                        lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
                    lines.append("")
                # Planning metadata
                planning = details.get("planning_approach")
                if planning:
                    lines += ["**Planning (Phase 1):**", "", f"> {planning}", ""]
                groups = details.get("intent_groups_planned")
                if groups is not None:
                    lines.append(f"**Intent groups planned:** {groups}  ")
                planned = details.get("total_stories_planned")
                if planned:
                    lines.append(f"**Stories planned:** {planned}  ")
                high_risk = details.get("high_risk_pairs_planned")
                if high_risk is not None:
                    lines.append(f"**High-risk story-ticket pairs flagged:** {high_risk}  ")
                exp_gaps = details.get("expected_gap_areas")
                if exp_gaps:
                    lines.append(f"**Expected gap areas:** {', '.join(exp_gaps)}  ")
                lines.append("")
                # Tool invocation metadata
                tool_calls_made = details.get("tool_calls_made")
                if tool_calls_made is not None:
                    tools_used = details.get("tools_used", [])
                    lines.append(f"**Tool calls made:** {tool_calls_made} ({', '.join(tools_used) or 'none'})  ")
                tool_detail = details.get("tool_calls_detail", [])
                if tool_detail:
                    lines += ["", "**Tool invocations (LLM-driven):**", ""]
                    for tc in tool_detail:
                        lines.append(
                            f"- `{tc.get('tool')}({json.dumps(tc.get('args', {}))})` → "
                            f"{str(tc.get('result_preview', ''))[:120]}…"
                        )
                    lines.append("")
                # AI decision rationale
                ai_decision = details.get("ai_decision")
                if ai_decision:
                    lines += ["**AI Decision:**", "", f"> {ai_decision}", ""]
                # Evaluator feedback
                fb = details.get("feedback")
                if fb:
                    lines += ["**Evaluator Feedback:**", "", f"> {fb}", ""]
                # Story list (story writer)
                story_list = details.get("stories")
                if story_list:
                    lines += ["**Stories generated:**", ""]
                    for st in story_list:
                        lines.append(f"- `{st.get('id')}` [{st.get('priority','?').upper()}] {st.get('title','')}")
                    lines.append("")
                # Coverage score
                cov = details.get("coverage_score")
                if cov is not None:
                    lines.append(f"**Coverage score:** {cov:.0%}  ")
                summary = details.get("summary")
                if summary:
                    lines += ["**Gap summary:**", "", f"> {summary}", ""]
                # System prompt (sanitised — static instruction only, no user data)
                sp = details.get("system_prompt") or details.get("map_system_prompt")
                if sp:
                    lines += [
                        "<details>",
                        "<summary>📋 System prompt (AI instructions used)</summary>", "",
                        f"```\n{sp}\n```", "",
                        "</details>", "",
                    ]
                rsp = details.get("reduce_system_prompt")
                if rsp:
                    lines += [
                        "<details>",
                        "<summary>📋 Reduce system prompt</summary>", "",
                        f"```\n{rsp}\n```", "",
                        "</details>", "",
                    ]
            lines += [
                f"**Input hash:** `{e.get('input_hash', '')}`  ",
                f"**Output hash:** `{e.get('output_hash', '')}`  ",
                "",
            ]

    # Per-story traceability section
    story_traces = [e for e in audit_log if e.get("tool") == "story_trace"]
    if story_traces:
        lines += ["### Story-to-Intent Traceability", "",
                  "Each story is linked to the transcript intents that caused it to be created.", ""]
        for st in story_traces:
            lines += [
                f"#### `{st.get('story_id','?')}` — {st.get('story_title','')}",
                "",
                f"**Type:** {st.get('story_type','?')} | **Priority:** {st.get('priority','?')}",
                "",
                f"**Reasoning:** {st.get('reasoning','')}",
                "",
            ]
            src = st.get("source_intents", [])
            if src:
                lines += ["**Source intents:**", ""]
                for si in src:
                    lines.append(f"- `{si.get('id','')}` [{si.get('type','?')}] **{si.get('title','')}**")
                    if si.get("quote"):
                        lines.append(f"  > \"{si['quote']}\"")
                lines.append("")
            else:
                lines += ["*No explicit intent IDs — derived from transcript context.*", ""]

    # Chain entries
    if chain_entries:
        lines += ["### Integrity Chain", ""]
        lines += ["| # | Agent | Status | Elapsed | Input hash | Output hash | Entry hash |",
                  "|---|-------|--------|---------|------------|-------------|------------|"]
        for i, c in enumerate(chain_entries):
            lines.append(
                f"| {i+1} | {c.get('agent','')} | {c.get('status','')} | {c.get('elapsed_s','?')}s "
                f"| `{c.get('input_hash','')[:12]}…` "
                f"| `{c.get('output_hash','')[:12]}…` "
                f"| `{c.get('entry_hash','')[:12]}…` |"
            )
        lines.append("")

    return "\n".join(lines)
