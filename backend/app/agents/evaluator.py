import json
from datetime import datetime, timezone
from app.models.state import BacklogState
from app.tools.document_parser import hash_content
from app.config import get_settings
from app.providers import complete_for_agent
from app.utils.json_utils import extract_json
from app.agents.harness import agent_harness

EVALUATOR_SYSTEM_PROMPT = """You are a QA evaluator for product backlogs. Score the provided user stories on:

1. AC Completeness (0-100%): Do acceptance criteria follow Given/When/Then with edge cases?
2. Clarity (1-5): Are stories unambiguous and well-written?
3. Feasibility (1-5): Are stories technically implementable given the constraints?
4. Traceability (1-5): Can each story be traced back to a transcript intent?
5. Feature Tag F1 (0-1): Are feature/system tags accurate and complete?
6. Conflict Detection F1 (0-1): How well were conflicts identified in the gap report?

Return ONLY a JSON object:
{
  "ac_completeness_pct": 85.0,
  "feature_tag_f1": 0.78,
  "conflict_detection_f1": 0.82,
  "clarity_score": 4.2,
  "feasibility_score": 3.8,
  "traceability_score": 4.5,
  "overall_score": 4.1,
  "feedback": "Detailed feedback with specific improvement suggestions..."
}"""


@agent_harness(required_inputs=["user_stories"])
def evaluator_node(state: BacklogState) -> dict:
    settings    = get_settings()
    stories     = state.get("user_stories", [])
    gap_report  = state.get("gap_report", {})
    intents     = state.get("extracted_intents", [])
    constraints = state.get("architecture_constraints", [])

    input_payload = {
        "user_stories":     stories,      # evaluate ALL stories, not [:10]
        "gap_report":       gap_report,
        "original_intents": intents,
        "constraints":      constraints[:5],
    }
    input_hash = hash_content(json.dumps(input_payload))

    raw, trace = complete_for_agent(
        state=state,
        agent_name="evaluator",
        default_provider=settings.default_provider,
        default_model=settings.evaluator_model,
        system=EVALUATOR_SYSTEM_PROMPT,
        user=(
            f"User stories to evaluate:\n{json.dumps(stories, indent=2)}\n\n"
            f"Gap report:\n{json.dumps(gap_report, indent=2)}\n\n"
            f"Original intents:\n{json.dumps(intents[:5], indent=2)}"
        ),
        max_tokens=2000,
    )

    try:
        scores = extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        scores = {
            "ac_completeness_pct":   0.0,
            "feature_tag_f1":        0.0,
            "conflict_detection_f1": 0.0,
            "clarity_score":         1.0,
            "feasibility_score":     1.0,
            "traceability_score":    1.0,
            "overall_score":         1.0,
            "feedback":              raw,
        }

    overall  = float(scores.get("overall_score", 0))
    feedback = scores.get("feedback", "")

    output_hash   = hash_content(json.dumps(scores))
    audit_details = {
        "stories_evaluated": len(stories),
        "retry_pass": state.get("retry_count", 0),
        "scores": {
            "overall":              round(overall, 2),
            "clarity":              round(float(scores.get("clarity_score", 0)), 2),
            "feasibility":          round(float(scores.get("feasibility_score", 0)), 2),
            "traceability":         round(float(scores.get("traceability_score", 0)), 2),
            "ac_completeness_pct":  round(float(scores.get("ac_completeness_pct", 0)), 1),
            "feature_tag_f1":       round(float(scores.get("feature_tag_f1", 0)), 3),
            "conflict_detection_f1":round(float(scores.get("conflict_detection_f1", 0)), 3),
        },
        "feedback": feedback,
        "provider": trace.get("provider"),
        "model": trace.get("model"),
        "approx_input_tokens": trace.get("approx_input_tokens"),
        "approx_output_tokens": trace.get("approx_output_tokens"),
        "system_prompt": EVALUATOR_SYSTEM_PROMPT,
        "ai_decision": (
            f"LLM-as-judge evaluated {len(stories)} stories on 6 dimensions. "
            f"Overall score: {overall}/5. "
            f"Clarity {scores.get('clarity_score',0)}/5, "
            f"Feasibility {scores.get('feasibility_score',0)}/5, "
            f"Traceability {scores.get('traceability_score',0)}/5, "
            f"AC Completeness {scores.get('ac_completeness_pct',0):.0f}%. "
            + ("Score above threshold — pipeline complete." if overall >= 3.5 else f"Score below threshold (3.5) — retry pass {state.get('retry_count',0)+1} will be triggered.")
        ),
    }
    return {
        "evaluation_scores":  scores,
        "evaluator_feedback": feedback,
        "last_overall_score": overall,
        "prompt_traces":      [trace],
        "audit_log": [_audit(
            "evaluator", "llm_judge", input_hash, output_hash,
            f"Overall {overall}/5 — clarity {scores.get('clarity_score', 0)}/5, "
            f"feasibility {scores.get('feasibility_score', 0)}/5, "
            f"traceability {scores.get('traceability_score', 0)}/5, "
            f"AC completeness {scores.get('ac_completeness_pct', 0):.0f}%",
            details=audit_details,
        )],
        "progress":  [{"agent": "evaluator", "status": "done", "timestamp": _now()}],
    }


def _audit(agent, tool, input_hash, output_hash, reasoning, details: dict | None = None):
    entry = {
        "agent": agent, "tool": tool,
        "input_hash": input_hash, "output_hash": output_hash,
        "reasoning": reasoning, "timestamp": _now(),
    }
    if details:
        entry["details"] = details
    return entry


def _now():
    return datetime.now(timezone.utc).isoformat()
