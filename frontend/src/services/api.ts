import axios from "axios";
import type { PipelineResult, AgentModelConfigs, JiraTicket, HistoryEntry } from "../types";

// Base URL and API key are set at build time via Vite environment variables.
// In development: create frontend/.env.local with VITE_API_BASE_URL=http://localhost:8000
// In production:  pass VITE_API_BASE_URL and VITE_API_KEY to the Docker build.
const BASE    = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY      ?? "";

// Attach the API key header to every request when configured
const client = axios.create({
  baseURL: BASE,
  headers: API_KEY ? { "X-Api-Key": API_KEY } : {},
});

export const api = {
  /** Create a new server-side session. Must be called before any upload. */
  createSession: (): Promise<string> =>
    client.post("/sessions").then((r) => r.data.session_id),

  uploadTranscripts: (sessionId: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return client.post(`/ingest/transcripts/${sessionId}`, form);
  },

  uploadWiki: (sessionId: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return client.post(`/ingest/wiki/${sessionId}`, form);
  },

  uploadBacklog: (sessionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return client.post(`/ingest/backlog/${sessionId}`, form);
  },

  runPipeline: (sessionId: string, agentModelConfigs: AgentModelConfigs = {}) =>
    client.post(`/pipeline/run/${sessionId}`, { agent_model_configs: agentModelConfigs }),

  streamUrl: (sessionId: string) => `${BASE}/pipeline/stream/${sessionId}`,

  exportResults: (sessionId: string, format: "json" | "markdown") =>
    `${BASE}/results/${sessionId}/export?format=${format}`,

  createStoriesInJira: (
    sessionId: string,
    approvedStoryIds: string[],
  ): Promise<{ created: JiraTicket[]; failed: { story_id: string; error: string }[]; total_created: number }> =>
    client
      .post(`/jira/create-stories/${sessionId}`, { approved_story_ids: approvedStoryIds })
      .then((r) => r.data),

  getCreatedTickets: (sessionId: string): Promise<JiraTicket[]> =>
    client.get(`/jira/tickets/${sessionId}`).then((r) => r.data.tickets),

  getHistory: (): Promise<HistoryEntry[]> =>
    client.get("/sessions/history").then((r) => r.data.history),

  getResults: (sessionId: string): Promise<PipelineResult> =>
    client.get(`/results/${sessionId}`).then((r) => r.data),
};
