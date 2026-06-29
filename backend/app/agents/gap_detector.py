import json
from datetime import datetime, timezone

from app.models.state import BacklogState
from app.tools.document_parser import hash_content
from app.config import get_settings
from app.providers import complete_for_agent
from app.providers.factory import plan_for_agent
from app.utils.json_utils import extract_json
from app.agents.harness import agent_harness


# ── System prompts ─────────────────────────────────────────────────────────

GAP_SYSTEM_PROMPT = """You are a backlog gap analyst. Compare new user stories against existing tickets.
Identify:
1. CONFLICTS: duplicates, contradictions, or significant overlaps
2. GAPS: intents not covered by any existing ticket or new story

Return a JSON object:
{
  "conflicts": [
    {
      "new_request": "...",
      "existing_ticket_id": "...",
      "conflict_type": "duplicate|contradiction|overlap",
      "description": "...",
      "recommendation": "..."
    }
  ],
  "gaps": [
    {
      "request": "...",
      "gap_type": "missing|underspecified",
      "description": "...",
      "suggested_story_ids": ["US-1", ...]
    }
  ],
  "coverage_score": 0.85,
  "summary": "Overall summary of backlog health..."
}"""


GAP_PLANNER_SYSTEM = """You are a backlog gap analyst. Before comparing new stories against existing tickets,
plan your analysis.

Scan the story titles and ticket summaries below. Based on keywords and domain knowledge, identify:
1. High-risk pairs: new stories most likely to duplicate or contradict specific existing tickets
2. Intent coverage gaps: topic areas in the intents that no story or ticket addresses
3. Your comparison strategy (what to look for, in what order)

Return ONLY a JSON plan (no other text):
{
  "approach": "2-3 sentence strategy summary",
  "high_risk_pairs": [
    {"story_title": "...", "ticket_id": "...", "risk": "duplicate|overlap|contradiction", "reason": "..."}
  ],
  "expected_gap_areas": ["semantic search", "CDN failover", ...],
  "coverage_estimate": 0.70
}"""


# ── Agent node ─────────────────────────────────────────────────────────────

@agent_harness(required_inputs=["user_stories", "extracted_intents"])
def gap_detector_node(state: BacklogState) -> dict:
    settings = get_settings()
    stories  = state.get("user_stories", [])
    existing = state.get("existing_tickets", [])
    intents  = state.get("extracted_intents", [])

    traces: list[dict] = []

    # ── Phase 1: PLANNING ──────────────────────────────────────────────────
    # LLM scans story and ticket titles to form a comparison strategy before
    # doing the full analysis — identifying high-risk pairs upfront.

    story_titles  = "\n".join(f"- [{s.get('id')}] {s.get('title')}" for s in stories)
    ticket_titles = "\n".join(
        f"- [{t.get('id')}] {t.get('title')} ({t.get('status', '?')})" for t in existing[:30]
    ) or "None"
    intent_titles = "\n".join(
        f"- [{i.get('id')}] {i.get('title')} ({i.get('type')})" for i in intents
    )

    planning_user = (
        f"New stories ({len(stories)}):\n{story_titles}\n\n"
        f"Existing tickets ({len(existing)}):\n{ticket_titles}\n\n"
        f"Original intents ({len(intents)}):\n{intent_titles}"
    )

    plan, plan_trace = plan_for_agent(
        state=state,
        agent_name="gap_detector",
        default_provider=settings.default_provider,
        default_model=settings.specialist_model,
        planning_system=GAP_PLANNER_SYSTEM,
        planning_user=planning_user,
    )
    traces.append(plan_trace)

    # ── Phase 2: FULL ANALYSIS ─────────────────────────────────────────────
    # LLM receives the plan + full data and performs the structured comparison.

    input_payload = {
        "new_stories":      stories,
        "existing_tickets": existing,
        "intents":          intents,
        "analysis_plan":    plan,
    }
    input_hash = hash_content(json.dumps(input_payload))

    analysis_user = (
        f"Analysis plan:\n{json.dumps(plan, indent=2)}\n\n"
        f"New user stories:\n{json.dumps(stories, indent=2)}\n\n"
        f"Existing tickets:\n{json.dumps(existing, indent=2)}\n\n"
        f"Original intents:\n{json.dumps(intents, indent=2)}"
    )

    raw, analysis_trace = complete_for_agent(
        state=state,
        agent_name="gap_detector",
        default_provider=settings.default_provider,
        default_model=settings.specialist_model,
        system=GAP_SYSTEM_PROMPT,
        user=analysis_user,
        max_tokens=4000,
    )
    traces.append(analysis_trace)

    try:
        gap_report = extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        gap_report = {"conflicts": [], "gaps": [], "coverage_score": 0.0, "summary": raw}

    output_hash    = hash_content(json.dumps(gap_report))
    conflicts      = gap_report.get("conflicts", [])
    gaps           = gap_report.get("gaps", [])
    coverage_score = gap_report.get("coverage_score", 0.0)

    audit_details = {
        "stories_analysed":   len(stories),
        "existing_tickets":   len(existing),
        "intents_checked":    len(intents),
        "conflicts_found":    len(conflicts),
        "conflict_types":     list({c.get("conflict_type") for c in conflicts if c.get("conflict_type")}),
        "gaps_found":         len(gaps),
        "gap_types":          list({g.get("gap_type") for g in gaps if g.get("gap_type")}),
        "coverage_score":     round(coverage_score, 3),
        "summary":            gap_report.get("summary", ""),
        "provider":           analysis_trace.get("provider"),
        "model":              analysis_trace.get("model"),
        "approx_input_tokens":  sum(t.get("approx_input_tokens", 0) for t in traces),
        "approx_output_tokens": sum(t.get("approx_output_tokens", 0) for t in traces),
        # Planning metadata
        "planning_approach":       plan.get("approach", ""),
        "high_risk_pairs_planned": len(plan.get("high_risk_pairs", [])),
        "expected_gap_areas":      plan.get("expected_gap_areas", []),
        "planned_coverage_estimate": plan.get("coverage_estimate"),
        # System prompts
        "planning_system_prompt":  GAP_PLANNER_SYSTEM,
        "system_prompt":           GAP_SYSTEM_PROMPT,
        "ai_decision": (
            f"Phase 1 (Planning): LLM identified {len(plan.get('high_risk_pairs', []))} high-risk "
            f"story-ticket pair(s) and expected gaps in: "
            f"{', '.join(plan.get('expected_gap_areas', [])) or 'none identified'}. "
            f"Phase 2 (Analysis): LLM compared {len(stories)} stories against {len(existing)} tickets "
            f"and {len(intents)} intents. Found {len(conflicts)} conflict(s), {len(gaps)} gap(s). "
            f"Coverage scored at {coverage_score:.0%}."
        ),
    }

    return {
        "gap_report":    gap_report,
        "prompt_traces": traces,
        "audit_log": [_audit(
            "gap_detector", "detect_gaps", input_hash, output_hash,
            f"Coverage {coverage_score:.0%} — {len(conflicts)} conflict(s), {len(gaps)} gap(s)",
            details=audit_details,
        )],
        "progress": [{"agent": "gap_detector", "status": "done", "timestamp": _now()}],
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
