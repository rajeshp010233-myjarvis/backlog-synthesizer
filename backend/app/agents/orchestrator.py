from datetime import datetime, timezone
from langgraph.graph import StateGraph, END
from app.models.state import BacklogState
from app.agents.ingestion_agent import ingestion_agent_node
from app.agents.story_writer import story_writer_node
from app.agents.gap_detector import gap_detector_node
from app.agents.evaluator import evaluator_node

SCORE_THRESHOLD = 3.5
MAX_RETRIES = 2
MIN_INTENTS = 3      # fewer than this → halt and ask for better transcripts


# ── Routing functions ──────────────────────────────────────────────────────────

def _route_after_ingestion(state: BacklogState) -> str:
    """
    Gate 1: Did ingestion produce enough intents to write meaningful stories?
    If not, stop the pipeline and tell the user why.
    """
    if state.get("halt_reason") or state.get("errors"):
        return "halt"
    intents = state.get("extracted_intents", [])
    if len(intents) < MIN_INTENTS:
        return "halt"
    return "story_writer"


def _route_after_story_writer(state: BacklogState) -> str:
    """
    Gate 2: Are there existing Jira/GitHub tickets to compare against?
    If the backlog is empty there is nothing to gap-detect — skip straight to evaluation.
    """
    tickets = state.get("existing_tickets", [])
    if not tickets:
        return "evaluator"          # skip gap_detector
    return "gap_detector"


def _route_after_evaluator(state: BacklogState) -> str:
    """
    Gate 3: Is quality good enough, or should story_writer retry?
    """
    overall = state.get("last_overall_score", 5.0)
    retries = state.get("retry_count", 0)
    if overall < SCORE_THRESHOLD and retries <= MAX_RETRIES:
        return "retry"
    return "done"


# ── Halt node ─────────────────────────────────────────────────────────────────

def halt_node(state: BacklogState) -> dict:
    """
    Reached only when the pipeline cannot proceed.
    Records a human-readable reason so the UI can surface it.
    """
    existing_reason = state.get("halt_reason", "")
    errors = state.get("errors", [])
    if existing_reason:
        reason = existing_reason
    elif errors:
        reason = errors[-1] if isinstance(errors[-1], str) else str(errors[-1])
    else:
        intents = state.get("extracted_intents", [])
        if len(intents) < MIN_INTENTS:
            reason = (
                f"Only {len(intents)} intent(s) were extracted from your transcripts "
                f"(minimum required: {MIN_INTENTS}). "
                "Please upload more detailed meeting transcripts and retry. "
                "Tip: transcripts should contain product discussions, feature requests, or pain points."
            )
        else:
            reason = "Pipeline halted: insufficient input to proceed."

    return {
        "halt_reason": reason,
        "audit_log": [
            {
                "agent": "orchestrator",
                "tool": "halt",
                "input_hash": "",
                "output_hash": "",
                "reasoning": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "progress": [
            {"agent": "orchestrator", "status": "halted", "timestamp": datetime.now(timezone.utc).isoformat()}
        ],
    }


# ── Graph ──────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(BacklogState)

    graph.add_node("ingestion_agent", ingestion_agent_node)
    graph.add_node("halt",            halt_node)
    graph.add_node("story_writer",    story_writer_node)
    graph.add_node("gap_detector",    gap_detector_node)
    graph.add_node("evaluator",       evaluator_node)

    graph.set_entry_point("ingestion_agent")

    # Gate 1: enough intents? → continue or halt
    graph.add_conditional_edges(
        "ingestion_agent",
        _route_after_ingestion,
        {
            "story_writer": "story_writer",
            "halt":         "halt",
        },
    )
    graph.add_edge("halt", END)

    # Gate 2: tickets exist? → run gap_detector or skip it
    graph.add_conditional_edges(
        "story_writer",
        _route_after_story_writer,
        {
            "gap_detector": "gap_detector",
            "evaluator":    "evaluator",
        },
    )

    graph.add_edge("gap_detector", "evaluator")

    # Gate 3: quality good enough? → done or retry story_writer
    graph.add_conditional_edges(
        "evaluator",
        _route_after_evaluator,
        {
            "retry": "story_writer",
            "done":  END,
        },
    )

    return graph.compile()


compiled_graph = build_graph()
