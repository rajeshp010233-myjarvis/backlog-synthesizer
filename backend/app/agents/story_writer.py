import json
import uuid
from datetime import datetime, timezone

from app.models.state import BacklogState
from app.tools.document_parser import hash_content
from app.tools.agent_tools import STORY_WRITER_TOOLS, make_story_writer_executor
from app.config import get_settings
from app.providers.factory import plan_for_agent, complete_with_tools_for_agent
from app.utils.json_utils import extract_json
from app.agents.harness import agent_harness


# ── System prompts ─────────────────────────────────────────────────────────

STORY_SYSTEM_PROMPT = """You are a senior product manager writing user stories.
Given extracted intents, architecture constraints, and the existing backlog, generate well-formed user stories.

Rules:
- Do NOT duplicate work already covered by an existing backlog ticket.
- If an intent overlaps with an existing ticket, write a story that EXTENDS or REFINES it instead.
- Respect all architecture constraints in the acceptance criteria.
- Every story MUST be traceable back to one or more specific intents using their IDs.

For each story return a JSON object:
{
  "id": "US-<n>",
  "type": "epic|story|task",
  "title": "...",
  "description": "As a <role>, I want <goal> so that <benefit>",
  "acceptance_criteria": [
    {"given": "...", "when": "...", "then": "...", "edge_cases": ["..."]}
  ],
  "system_tags": ["auth", "api", ...],
  "feature_tags": ["login", "dashboard", ...],
  "source_transcript": "transcript_<n>",
  "source_intent_ids": ["<intent-id-1>", "<intent-id-2>"],
  "priority": "high|medium|low"
}

Return a JSON array of stories. Group related stories under epics."""


STORY_PLANNER_SYSTEM = """You are a senior product manager planning how to write user stories.

Before any stories are written, analyse the intents, constraints, and existing tickets to produce
a structured writing plan.

Your plan must:
1. Group related intents into themes — each theme will become an epic or a cluster of stories
2. Flag intents that risk duplicating existing tickets
3. Decide priority order based on business impact
4. Identify which groups need architecture constraint lookups

Return ONLY a JSON plan (no other text):
{
  "approach": "2-3 sentence summary of your overall strategy",
  "total_stories_planned": 10,
  "intent_groups": [
    {
      "group_name": "DRM & Content Security",
      "intent_ids": ["INT-01", "INT-05"],
      "story_type": "epic",
      "priority": "high",
      "duplication_risk": "overlaps with QSE-101 — write as refinement",
      "constraint_search_queries": ["DRM hardware security", "device attestation"]
    }
  ]
}"""


STORY_TOOL_SYSTEM = """You are a senior product manager writing user stories from extracted meeting intents.

You have access to three tools — use them before writing stories:

  search_constraints(query)      — find relevant architecture constraints for a topic
  check_existing_tickets(keyword)— check if an intent is already in the Jira backlog
  get_intent_detail(intent_id)   — get verbatim source quote and speaker role for an intent

Strategy:
1. For each intent group in the plan, call search_constraints with the provided query terms
2. For any group flagged with duplication risk, call check_existing_tickets before writing
3. Call get_intent_detail when you need the exact quote for an acceptance criterion
4. After all tool lookups, write all stories as a single JSON array

Story format (required for every story):
{
  "id": "US-<n>",
  "type": "epic|story|task",
  "title": "...",
  "description": "As a <role>, I want <goal> so that <benefit>",
  "acceptance_criteria": [
    {"given": "...", "when": "...", "then": "...", "edge_cases": ["..."]}
  ],
  "system_tags": [...],
  "feature_tags": [...],
  "source_transcript": "transcript_<n>",
  "source_intent_ids": ["<intent-id>", ...],
  "priority": "high|medium|low"
}

Return a JSON array of all stories once you have gathered what you need."""


# ── Agent node ─────────────────────────────────────────────────────────────

@agent_harness(required_inputs=["extracted_intents"])
def story_writer_node(state: BacklogState) -> dict:
    settings         = get_settings()
    intents          = state.get("extracted_intents", [])
    constraints      = state.get("architecture_constraints", [])
    existing_tickets = state.get("existing_tickets", [])
    session_id       = state["session_id"]
    retry_count      = state.get("retry_count", 0)
    feedback         = state.get("evaluator_feedback", "")
    prev_score       = state.get("last_overall_score", 0.0)

    if not intents:
        return {
            "user_stories": [],
            "audit_log": [_audit("story_writer", "skip", "", "", "No intents to process")],
        }

    traces: list[dict] = []

    # ── Phase 1: PLANNING ──────────────────────────────────────────────────
    # The LLM reasons about the problem before solving it — groups intents,
    # flags duplication risks, decides which constraints to look up.

    intent_summary = json.dumps(
        [{"id": i.get("id"), "title": i.get("title"), "type": i.get("type"), "priority": i.get("priority")} for i in intents],
        indent=2,
    )
    ticket_summary = "\n".join(
        f"- [{t.get('id')}] {t.get('title')} ({t.get('status', 'unknown')})"
        for t in existing_tickets[:30]
    ) or "None"
    constraint_summary = "\n".join(
        f"- [{c.get('category', '?')}] {c.get('description', '')[:120]}"
        for c in constraints[:10]
    ) or "None"

    planning_user = (
        f"Intents to plan for:\n{intent_summary}\n\n"
        f"Existing backlog (potential duplicates):\n{ticket_summary}\n\n"
        f"Architecture constraints (brief):\n{constraint_summary}"
    )
    if retry_count > 0 and feedback:
        planning_user += (
            f"\n\n---\nThis is REVISION PASS {retry_count} (prev score {prev_score:.1f}/5).\n"
            f"Evaluator feedback to address:\n{feedback}\n\n"
            "Plan how to fix these issues in your revised stories."
        )

    plan, plan_trace = plan_for_agent(
        state=state,
        agent_name="story_writer",
        default_provider=settings.default_provider,
        default_model=settings.specialist_model,
        planning_system=STORY_PLANNER_SYSTEM,
        planning_user=planning_user,
    )
    traces.append(plan_trace)

    # ── Phase 2: TOOL-INVOCATION + GENERATION ─────────────────────────────
    # The LLM receives the plan and the full intent list, then decides which
    # tools to call (search_constraints, check_existing_tickets, get_intent_detail)
    # before producing the final story array.

    tool_executor = make_story_writer_executor(session_id, intents, existing_tickets)

    generation_user = (
        f"Your writing plan:\n{json.dumps(plan, indent=2)}\n\n"
        f"Full intents list:\n{json.dumps(intents, indent=2)}\n\n"
        f"Existing backlog (do not duplicate):\n{ticket_summary}"
    )
    if retry_count > 0 and feedback:
        generation_user += (
            f"\n\n---\nREVISION PASS {retry_count}. Evaluator issues to fix:\n\n{feedback}\n\n"
            "Regenerate ALL stories, addressing every issue above."
        )

    input_hash = hash_content(json.dumps({"intents": intents, "plan": plan}))

    raw, tool_calls, gen_trace = complete_with_tools_for_agent(
        state=state,
        agent_name="story_writer",
        default_provider=settings.default_provider,
        default_model=settings.specialist_model,
        system=STORY_TOOL_SYSTEM,
        user=generation_user,
        tools=STORY_WRITER_TOOLS,
        tool_executor=tool_executor,
        max_tokens=6000,
    )
    traces.append(gen_trace)

    try:
        stories = extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        stories = []

    for s in stories:
        if "id" not in s:
            s["id"] = f"US-{uuid.uuid4().hex[:6]}"

    # ── Audit: per-story traceability ──────────────────────────────────────
    intent_index = {i.get("id"): i for i in intents}
    per_story_audit = []
    for s in stories:
        src_ids = s.get("source_intent_ids") or []
        linked  = [intent_index[iid] for iid in src_ids if iid in intent_index]
        if not linked and s.get("source_transcript"):
            linked = [i for i in intents if i.get("source_transcript") == s["source_transcript"]][:2]
        reasoning = (
            f"Story '{s.get('title')}' (priority: {s.get('priority')}) was derived from "
            + (
                f"{len(linked)} intent(s): " + "; ".join(
                    f"[{i.get('id')}] {i.get('title')} ({i.get('type')})" for i in linked
                ) if linked else "transcript content (no explicit intent IDs linked)"
            )
        )
        per_story_audit.append({
            "agent":          "story_writer",
            "tool":           "story_trace",
            "story_id":       s.get("id"),
            "story_title":    s.get("title"),
            "story_type":     s.get("type"),
            "priority":       s.get("priority"),
            "source_intents": [
                {"id": i.get("id"), "title": i.get("title"), "type": i.get("type"), "quote": i.get("source_quote", "")}
                for i in linked
            ],
            "reasoning":  reasoning,
            "timestamp":  _now(),
        })

    # ── Audit: agent summary ───────────────────────────────────────────────
    output_hash   = hash_content(json.dumps(stories))
    action        = "revise_stories" if retry_count > 0 else "generate_stories"
    note          = (
        f"Revision {retry_count}: {len(stories)} stories (prev score {prev_score:.1f}/5)"
        if retry_count > 0
        else f"Generated {len(stories)} user stories from {len(intents)} intents "
             f"via planning + {len(tool_calls)} tool call(s)"
    )
    story_summary = [
        {"id": s.get("id"), "title": s.get("title"), "type": s.get("type"), "priority": s.get("priority")}
        for s in stories
    ]
    audit_details = {
        "intents_used":           len(intents),
        "constraints_available":  len(constraints),
        "existing_tickets":       len(existing_tickets),
        "stories_generated":      len(stories),
        "story_types":            list({s.get("type") for s in stories if s.get("type")}),
        "priority_breakdown":     {p: sum(1 for s in stories if s.get("priority") == p) for p in ("high", "medium", "low")},
        "stories":                story_summary,
        "retry_pass":             retry_count,
        "prev_score":             round(prev_score, 2) if retry_count > 0 else None,
        "provider":               gen_trace.get("provider"),
        "model":                  gen_trace.get("model"),
        "approx_input_tokens":    sum(t.get("approx_input_tokens", 0) for t in traces),
        "approx_output_tokens":   sum(t.get("approx_output_tokens", 0) for t in traces),
        # Planning metadata
        "planning_approach":      plan.get("approach", ""),
        "intent_groups_planned":  len(plan.get("intent_groups", [])),
        "total_stories_planned":  plan.get("total_stories_planned", 0),
        # Tool invocation metadata
        "tool_calls_made":        len(tool_calls),
        "tools_used":             list({tc["tool"] for tc in tool_calls}),
        "tool_calls_detail":      tool_calls,
        # System prompts (for AI usage documentation)
        "planning_system_prompt": STORY_PLANNER_SYSTEM,
        "generation_system_prompt": STORY_TOOL_SYSTEM,
        "ai_decision": (
            f"Phase 1 (Planning): LLM grouped {len(intents)} intents into "
            f"{len(plan.get('intent_groups', []))} theme(s) and identified duplication risks. "
            f"Phase 2 (Tool use + Generation): LLM made {len(tool_calls)} tool call(s) "
            f"({', '.join({tc['tool'] for tc in tool_calls}) or 'none'}) "
            f"then generated {len(stories)} stories. "
            + (f"Revision pass {retry_count} — addressing evaluator feedback." if retry_count > 0 else "Initial generation pass.")
        ),
    }

    iteration_snapshot = {
        "iteration":    retry_count,
        "story_count":  len(stories),
        "stories":      stories,
        "score_before": prev_score,
        "feedback_used": feedback,
        "plan":         plan,
        "tool_calls":   tool_calls,
        "timestamp":    _now(),
    }

    return {
        "user_stories":      stories,
        "retry_count":       retry_count + 1,
        "story_iterations":  [iteration_snapshot],
        "prompt_traces":     traces,
        "audit_log":         [
            _audit("story_writer", action, input_hash, output_hash, note, details=audit_details)
        ] + per_story_audit,
        "progress": [{"agent": "story_writer", "status": "done", "timestamp": _now()}],
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _audit(agent, tool, input_hash, output_hash, reasoning, details: dict | None = None):
    entry = {
        "agent":       agent,
        "tool":        tool,
        "input_hash":  input_hash,
        "output_hash": output_hash,
        "reasoning":   reasoning,
        "timestamp":   _now(),
    }
    if details:
        entry["details"] = details
    return entry


def _now():
    return datetime.now(timezone.utc).isoformat()
