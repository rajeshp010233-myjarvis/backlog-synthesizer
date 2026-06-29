export interface AcceptanceCriteria {
  given: string;
  when: string;
  then: string;
  edge_cases: string[];
}

export interface UserStory {
  id: string;
  type: "epic" | "story" | "task" | "bug";
  title: string;
  description: string;
  acceptance_criteria: AcceptanceCriteria[];
  system_tags: string[];
  feature_tags: string[];
  source_transcript?: string;
  source_intent_ids?: string[];
  parent_epic_id?: string;
  priority: "high" | "medium" | "low";
}

export interface ConflictItem {
  new_request: string;
  existing_ticket_id: string;
  conflict_type: "duplicate" | "contradiction" | "overlap";
  description: string;
  recommendation: string;
}

export interface GapItem {
  request: string;
  gap_type: "missing" | "underspecified";
  description: string;
  suggested_story_ids: string[];
}

export interface GapReport {
  conflicts: ConflictItem[];
  gaps: GapItem[];
  coverage_score: number;
  summary: string;
}

export interface EvaluationScores {
  ac_completeness_pct: number;
  feature_tag_f1: number;
  conflict_detection_f1: number;
  clarity_score: number;
  feasibility_score: number;
  traceability_score: number;
  overall_score: number;
  feedback: string;
}

export interface Intent {
  id: string;
  type: string;
  title: string;
  description: string;
  priority: string;
  speaker_role: string;
  source_quote: string;
  source_transcript: string;
}

export interface JiraTicket {
  story_id: string;
  jira_key: string;
  jira_url: string;
  status: string;
}

export interface PipelineResult {
  session_id: string;
  user_stories: UserStory[];
  extracted_intents: Intent[];
  gap_report: GapReport;
  evaluation_scores: EvaluationScores;
  audit_log: Record<string, unknown>[];
  retry_count: number;
  halt_reason: string;
}

export type ModelProvider = "anthropic" | "openai" | "gemini" | "ollama";

export interface AgentModelConfig {
  provider: ModelProvider;
  model: string;
}

export type AgentName =
  | "ingestion_agent"
  | "story_writer"
  | "gap_detector"
  | "evaluator";

export type AgentModelConfigs = Partial<Record<AgentName, AgentModelConfig>>;

export const MODEL_OPTIONS: Record<ModelProvider, string[]> = {
  anthropic: ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
  gemini: ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"],
  ollama: ["llama3", "mistral", "phi3", "codellama"],
};

export const AGENT_LABELS: Record<AgentName, string> = {
  ingestion_agent: "Ingestion (wiki + transcripts)",
  story_writer: "Story Writer",
  gap_detector: "Gap Detector",
  evaluator: "Evaluator",
};

export interface ProgressEvent {
  agent: string;
  status: string;
  timestamp: string;
}

export type SSEMessage =
  | { type: "progress"; payload: ProgressEvent }
  | { type: "status"; status: string }
  | { type: "done"; session_id: string }
  | { type: "error"; message: string };
