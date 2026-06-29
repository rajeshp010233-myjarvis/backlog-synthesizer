import { useState } from "react";
import type { UserStory, Intent, JiraTicket } from "../../types";

interface StoryCardProps {
  story: UserStory;
  intents: Intent[];
  approved: boolean;
  rejected: boolean;
  creating?: boolean;
  createdTicket?: JiraTicket;
  ticketError?: string;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

export function StoryCard({
  story,
  intents,
  approved,
  rejected,
  creating = false,
  createdTicket,
  ticketError,
  onApprove,
  onReject,
}: StoryCardProps) {
  const [showEvidence, setShowEvidence] = useState(false);

  const sourceIntents = (() => {
    // 1. Prefer explicit ID links set by the story writer
    if (story.source_intent_ids?.length) {
      const byId = intents.filter((i) => story.source_intent_ids!.includes(i.id));
      if (byId.length) return byId;
    }
    // 2. Fall back to same source transcript
    if (story.source_transcript) {
      const byTranscript = intents.filter((i) => i.source_transcript === story.source_transcript);
      if (byTranscript.length) return byTranscript.slice(0, 3);
    }
    // 3. Last resort: show first 2 intents as likely evidence
    return intents.slice(0, 2);
  })();

  const borderColor = approved
    ? "border-green-400"
    : rejected
    ? "border-red-300"
    : "border-gray-200";

  const priorityColor: Record<string, string> = {
    high:   "bg-red-100 text-red-700",
    medium: "bg-yellow-100 text-yellow-700",
    low:    "bg-green-100 text-green-700",
  };

  const typeColor: Record<string, string> = {
    epic:  "bg-purple-100 text-purple-700",
    story: "bg-blue-100 text-blue-700",
    task:  "bg-gray-100 text-gray-700",
  };

  return (
    <div className={`border-2 ${borderColor} rounded-lg p-4 bg-white transition-all`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-mono text-gray-400">{story.id}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${typeColor[story.type] ?? typeColor.story}`}>
              {story.type}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${priorityColor[story.priority] ?? priorityColor.medium}`}>
              {story.priority}
            </span>
            {createdTicket && (
              <a
                href={createdTicket.jira_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs px-2 py-0.5 rounded-full bg-blue-600 text-white font-medium hover:bg-blue-700"
              >
                {createdTicket.jira_key} ↗
              </a>
            )}
            {creating && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-600 font-medium animate-pulse">
                Creating in Jira…
              </span>
            )}
          </div>
          <h3 className="font-medium text-gray-900 text-sm leading-snug">{story.title}</h3>
          <p className="text-xs text-gray-500 mt-1 leading-relaxed">{story.description}</p>
        </div>

        {/* Approve / Reject */}
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={() => onApprove(story.id)}
            disabled={approved || creating || !!createdTicket}
            title={createdTicket ? "Already created in Jira" : "Approve and create in Jira"}
            className={`text-xs px-3 py-1.5 rounded-md border font-medium transition-colors ${
              approved || createdTicket
                ? "bg-green-500 text-white border-green-500 opacity-80 cursor-default"
                : "border-gray-300 text-gray-600 hover:bg-green-50 hover:border-green-400 hover:text-green-700"
            }`}
          >
            {creating ? "…" : approved || createdTicket ? "✓ Approved" : "Approve →Jira"}
          </button>
          <button
            onClick={() => onReject(story.id)}
            disabled={rejected || !!createdTicket}
            className={`text-xs px-3 py-1.5 rounded-md border font-medium transition-colors ${
              rejected
                ? "bg-red-400 text-white border-red-400"
                : "border-gray-300 text-gray-600 hover:bg-red-50 hover:border-red-300 hover:text-red-600"
            }`}
          >
            {rejected ? "✕ Rejected" : "Reject"}
          </button>
        </div>
      </div>

      {/* Jira creation error */}
      {ticketError && (
        <div className="mt-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
          Jira error: {ticketError}
        </div>
      )}

      {/* Acceptance criteria */}
      {story.acceptance_criteria?.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <p className="text-xs font-medium text-gray-500 mb-1">Acceptance criteria</p>
          <div className="space-y-1">
            {story.acceptance_criteria.slice(0, 2).map((ac, i) => (
              <p key={i} className="text-xs text-gray-600">
                <span className="font-medium">Given</span> {ac.given} —{" "}
                <span className="font-medium">When</span> {ac.when} —{" "}
                <span className="font-medium">Then</span> {ac.then}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Source evidence toggle */}
      {sourceIntents.length > 0 && (
        <div className="mt-3 pt-2 border-t border-gray-100">
          <button
            onClick={() => setShowEvidence((v) => !v)}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
          >
            {showEvidence ? "▾ Hide source evidence" : "▸ Show source evidence"}
            <span className="ml-1 text-gray-400">({sourceIntents.length} intent{sourceIntents.length > 1 ? "s" : ""})</span>
          </button>

          {showEvidence && (
            <div className="mt-2 space-y-3">
              {sourceIntents.map((intent) => (
                <div key={intent.id} className="bg-blue-50 rounded-md p-3 border border-blue-100">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-blue-500">{intent.id}</span>
                    <span className="text-xs text-blue-600 font-medium">{intent.type.replace("_", " ")}</span>
                    {intent.speaker_role && (
                      <span className="text-xs text-gray-500">— {intent.speaker_role}</span>
                    )}
                    {intent.source_transcript && (
                      <span className="text-xs text-gray-400 ml-auto">{intent.source_transcript}</span>
                    )}
                  </div>
                  <p className="text-xs font-medium text-gray-800 mb-1">{intent.title}</p>
                  {intent.source_quote && (
                    <blockquote className="border-l-2 border-blue-300 pl-2 text-xs text-gray-600 italic">
                      "{intent.source_quote}"
                    </blockquote>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
