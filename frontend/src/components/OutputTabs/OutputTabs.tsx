import { useState } from "react";
import type { PipelineResult, JiraTicket } from "../../types";
import { api } from "../../services/api";
import { StoryCard } from "../StoryCard/StoryCard";

interface Props {
  result: PipelineResult;
}

const TABS = ["Stories", "Gap Report", "Evaluation", "Audit Log"] as const;
type Tab = (typeof TABS)[number];

export function OutputTabs({ result }: Props) {
  const [tab, setTab] = useState<Tab>("Stories");
  const [approvedIds, setApprovedIds]   = useState<Set<string>>(new Set());
  const [rejectedIds, setRejectedIds]   = useState<Set<string>>(new Set());
  const [creatingIds, setCreatingIds]   = useState<Set<string>>(new Set());
  const [createdTickets, setCreatedTickets] = useState<JiraTicket[]>([]);
  const [ticketErrors, setTicketErrors] = useState<Record<string, string>>({});

  const handleApprove = async (id: string) => {
    setApprovedIds((prev) => new Set([...prev, id]));
    setRejectedIds((prev) => { const s = new Set(prev); s.delete(id); return s; });

    // Immediately create the Jira ticket
    setCreatingIds((prev) => new Set([...prev, id]));
    setTicketErrors((prev) => { const s = { ...prev }; delete s[id]; return s; });
    try {
      const res = await api.createStoriesInJira(result.session_id, [id]);
      if (res.created.length > 0) {
        setCreatedTickets((prev) => [...prev, ...res.created]);
      }
      if (res.failed.length > 0) {
        setTicketErrors((prev) => ({ ...prev, [id]: res.failed[0].error ?? "Failed to create ticket" }));
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? "Failed to create ticket in Jira";
      setTicketErrors((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setCreatingIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
    }
  };

  const handleReject = (id: string) => {
    setRejectedIds((prev) => new Set([...prev, id]));
    setApprovedIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
  };

  const createdMap = Object.fromEntries(createdTickets.map((t) => [t.story_id, t]));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-1 border-b border-gray-200 flex-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === t
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t}
              {t === "Stories" && createdTickets.length > 0 && (
                <span className="ml-1.5 bg-green-500 text-white text-xs rounded-full px-1.5 py-0.5">
                  {createdTickets.length}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="flex gap-2 ml-4 flex-shrink-0">
          <a href={api.exportResults(result.session_id, "json")} className="text-xs px-3 py-1 border rounded hover:bg-gray-50">
            Export JSON
          </a>
          <a href={api.exportResults(result.session_id, "markdown")} className="text-xs px-3 py-1 border rounded hover:bg-gray-50">
            Export MD
          </a>
        </div>
      </div>

      {createdTickets.length > 0 && tab === "Stories" && (
        <div className="text-xs bg-green-50 border border-green-200 rounded-lg px-3 py-2 flex flex-wrap gap-3 items-center">
          <span className="text-green-700 font-medium">Created in Jira:</span>
          {createdTickets.map((t) => (
            <a
              key={t.jira_key}
              href={t.jira_url}
              target="_blank"
              rel="noreferrer"
              className="text-blue-600 hover:underline font-mono"
            >
              {t.jira_key}
            </a>
          ))}
        </div>
      )}

      {tab === "Stories" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>{result.user_stories.length} stories generated</span>
            <span>{approvedIds.size} approved · {rejectedIds.size} rejected · {createdTickets.length} in Jira</span>
          </div>
          {result.user_stories.map((story) => (
            <StoryCard
              key={story.id}
              story={story}
              intents={result.extracted_intents ?? []}
              approved={approvedIds.has(story.id)}
              rejected={rejectedIds.has(story.id)}
              creating={creatingIds.has(story.id)}
              createdTicket={createdMap[story.id]}
              ticketError={ticketErrors[story.id]}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ))}
        </div>
      )}

      {tab === "Gap Report" && <GapReportTab report={result.gap_report} />}
      {tab === "Evaluation" && <EvaluationTab scores={result.evaluation_scores} />}
      {tab === "Audit Log" && <AuditTab log={result.audit_log} />}
    </div>
  );
}

function GapReportTab({ report }: { report: any }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <div className="flex-1 bg-gray-100 rounded-full h-3">
          <div className="bg-indigo-500 h-3 rounded-full" style={{ width: `${(report.coverage_score ?? 0) * 100}%` }} />
        </div>
        <span className="text-sm font-medium text-gray-700">
          {((report.coverage_score ?? 0) * 100).toFixed(0)}% Coverage
        </span>
      </div>
      <p className="text-sm text-gray-600">{report.summary}</p>

      {report.conflicts?.length > 0 && (
        <div>
          <h3 className="font-semibold text-red-700 mb-2">Conflicts ({report.conflicts.length})</h3>
          <div className="space-y-2">
            {report.conflicts.map((c: any, i: number) => (
              <div key={i} className="border border-red-200 bg-red-50 rounded-lg p-3 text-sm">
                <p className="font-medium text-red-800">{c.conflict_type}: {c.existing_ticket_id}</p>
                <p className="text-gray-700 mt-1">{c.description}</p>
                <p className="text-gray-500 text-xs mt-1">Recommendation: {c.recommendation}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {report.gaps?.length > 0 && (
        <div>
          <h3 className="font-semibold text-amber-700 mb-2">Gaps ({report.gaps.length})</h3>
          <div className="space-y-2">
            {report.gaps.map((g: any, i: number) => (
              <div key={i} className="border border-amber-200 bg-amber-50 rounded-lg p-3 text-sm">
                <p className="font-medium text-amber-800">{g.gap_type}: {g.request}</p>
                <p className="text-gray-700 mt-1">{g.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EvaluationTab({ scores }: { scores: any }) {
  const metrics = [
    { label: "AC Completeness",      value: `${(scores.ac_completeness_pct ?? 0).toFixed(0)}%`,  pct: (scores.ac_completeness_pct ?? 0) / 100 },
    { label: "Feature Tag F1",       value: (scores.feature_tag_f1 ?? 0).toFixed(2),              pct: scores.feature_tag_f1 ?? 0 },
    { label: "Conflict Detection F1",value: (scores.conflict_detection_f1 ?? 0).toFixed(2),       pct: scores.conflict_detection_f1 ?? 0 },
    { label: "Clarity",              value: `${(scores.clarity_score ?? 0).toFixed(1)}/5`,        pct: (scores.clarity_score ?? 0) / 5 },
    { label: "Feasibility",          value: `${(scores.feasibility_score ?? 0).toFixed(1)}/5`,    pct: (scores.feasibility_score ?? 0) / 5 },
    { label: "Traceability",         value: `${(scores.traceability_score ?? 0).toFixed(1)}/5`,   pct: (scores.traceability_score ?? 0) / 5 },
  ];

  return (
    <div className="space-y-4">
      <div className="text-center py-4">
        <p className="text-5xl font-bold text-indigo-600">{(scores.overall_score ?? 0).toFixed(1)}</p>
        <p className="text-gray-500 text-sm mt-1">Overall Score / 5</p>
      </div>
      <div className="space-y-3">
        {metrics.map((m) => (
          <div key={m.label} className="flex items-center gap-4">
            <p className="text-sm text-gray-700 w-44 flex-shrink-0">{m.label}</p>
            <div className="flex-1 bg-gray-100 rounded-full h-2">
              <div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${m.pct * 100}%` }} />
            </div>
            <p className="text-sm font-medium text-gray-700 w-16 text-right">{m.value}</p>
          </div>
        ))}
      </div>
      <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-600">
        <p className="font-medium text-gray-800 mb-1">Evaluator Feedback</p>
        {scores.feedback}
      </div>
    </div>
  );
}

function AuditTab({ log }: { log: any[] }) {
  return (
    <div className="max-h-[600px] overflow-y-auto space-y-2">
      {log.map((entry: any, i: number) => (
        <div key={i} className="font-mono text-xs bg-gray-900 text-green-400 rounded p-3 space-y-0.5">
          <p><span className="text-gray-400">agent:</span> {entry.agent}</p>
          <p><span className="text-gray-400">tool:</span> {entry.tool}</p>
          <p><span className="text-gray-400">reasoning:</span> {entry.reasoning}</p>
          <p><span className="text-gray-400">ts:</span> {entry.timestamp}</p>
        </div>
      ))}
    </div>
  );
}
