from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class StoryType(str, Enum):
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    BUG = "bug"


class AcceptanceCriteria(BaseModel):
    given: str
    when: str
    then: str
    edge_cases: list[str] = Field(default_factory=list)


class UserStory(BaseModel):
    id: str
    type: StoryType
    title: str
    description: str
    acceptance_criteria: list[AcceptanceCriteria]
    system_tags: list[str] = Field(default_factory=list)
    feature_tags: list[str] = Field(default_factory=list)
    source_transcript: Optional[str] = None
    parent_epic_id: Optional[str] = None
    priority: str = "medium"


class ConflictItem(BaseModel):
    new_request: str
    existing_ticket_id: str
    conflict_type: str  # "duplicate" | "contradiction" | "overlap"
    description: str
    recommendation: str


class GapItem(BaseModel):
    request: str
    gap_type: str  # "missing" | "underspecified"
    description: str
    suggested_story_ids: list[str] = Field(default_factory=list)


class GapReport(BaseModel):
    conflicts: list[ConflictItem]
    gaps: list[GapItem]
    coverage_score: float = Field(ge=0.0, le=1.0)
    summary: str


class EvaluationScores(BaseModel):
    ac_completeness_pct: float
    feature_tag_f1: float
    conflict_detection_f1: float
    clarity_score: float = Field(ge=1.0, le=5.0)
    feasibility_score: float = Field(ge=1.0, le=5.0)
    traceability_score: float = Field(ge=1.0, le=5.0)
    overall_score: float = Field(ge=1.0, le=5.0)
    feedback: str


class PipelineResult(BaseModel):
    session_id: str
    user_stories: list[UserStory]
    gap_report: GapReport
    evaluation_scores: EvaluationScores
    audit_log: list[dict]


class AuditEntry(BaseModel):
    agent: str
    tool: str
    input_hash: str
    output_hash: str
    reasoning: str
    timestamp: str
