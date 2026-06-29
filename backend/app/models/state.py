from typing import Annotated
from typing_extensions import TypedDict


class BacklogState(TypedDict):
    # Input artifacts
    transcript_texts: list[str]
    wiki_texts: list[str]
    existing_tickets: list[dict]

    # Intermediate outputs
    extracted_intents: list[dict]
    architecture_constraints: list[dict]

    # Final outputs
    user_stories: list[dict]
    gap_report: dict
    evaluation_scores: dict

    # Append-only logs — LangGraph reducer concatenates across nodes
    audit_log:        Annotated[list[dict], lambda a, b: a + b]
    prompt_traces:    Annotated[list[dict], lambda a, b: a + b]
    story_iterations: Annotated[list[dict], lambda a, b: a + b]
    progress:         Annotated[list[dict], lambda a, b: a + b]

    # Pipeline control
    session_id: str
    errors: list[str]
    agent_model_configs: dict
    halt_reason: str

    # Evaluator feedback loop
    retry_count: int
    evaluator_feedback: str
    last_overall_score: float
