import { CheckCircle, Loader, RefreshCw } from "lucide-react";
import type { ProgressEvent } from "../../types";

const AGENTS = [
  { id: "ingestion_agent", label: "Ingestion Agent", desc: "Wiki constraints + transcript intents", color: "#6366f1" },
  { id: "story_writer",    label: "Story Writer",    desc: "Generating user stories & AC",          color: "#8b5cf6" },
  { id: "gap_detector",    label: "Gap Detector",    desc: "Finding conflicts & gaps",               color: "#0ea5e9" },
  { id: "evaluator",       label: "Evaluator",       desc: "LLM-as-judge scoring",                  color: "#10b981" },
];

interface Props {
  progress: ProgressEvent[];
  status: "idle" | "running" | "done" | "error";
  error: string | null;
  onRerun?: () => void;
}

export function PipelineDashboard({ progress, status, error, onRerun }: Props) {
  const doneAgents = new Set(progress.filter((p) => p.status === "done").map((p) => p.agent));
  const lastAgent = progress[progress.length - 1]?.agent;

  return (
    <div>
      <style>{`
        @keyframes pulse-glow { 0%,100%{opacity:.5;transform:scale(1)} 50%{opacity:1;transform:scale(1.05)} }
        @keyframes spin-dash { to{stroke-dashoffset:-60} }
      `}</style>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#e2e8f0" }}>Pipeline Progress</h2>
        <StatusBadge status={status} />
      </div>

      {error && (
        <div style={{
          background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)",
          borderRadius: 10, padding: "12px 14px", marginBottom: 16,
        }}>
          <div style={{ fontSize: 12, color: "#fca5a5", lineHeight: 1.6, marginBottom: onRerun ? 10 : 0 }}>
            {error}
          </div>
          {onRerun && (
            <button
              onClick={onRerun}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 14px", borderRadius: 6, cursor: "pointer",
                background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.3)",
                color: "#fca5a5", fontSize: 12, fontWeight: 600,
              }}
            >
              <RefreshCw size={11} /> Try Again
            </button>
          )}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {AGENTS.map((agent, i) => {
          const isDone = doneAgents.has(agent.id);
          const isRunning = !isDone && status === "running" && lastAgent === agent.id;

          return (
            <div key={agent.id} style={{
              display: "flex", alignItems: "center", gap: 14, padding: "12px 16px",
              borderRadius: 12, transition: "all 0.3s ease",
              background: isDone
                ? `rgba(${hexRgb(agent.color)}, 0.06)`
                : isRunning
                ? `rgba(${hexRgb(agent.color)}, 0.08)`
                : "rgba(255,255,255,0.02)",
              border: `1px solid ${
                isDone ? `rgba(${hexRgb(agent.color)}, 0.2)`
                : isRunning ? `rgba(${hexRgb(agent.color)}, 0.3)`
                : "rgba(255,255,255,0.05)"
              }`,
              boxShadow: isRunning ? `0 0 20px rgba(${hexRgb(agent.color)}, 0.1)` : "none",
            }}>
              {/* Step number / status icon */}
              <div style={{
                width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: isDone
                  ? `rgba(${hexRgb(agent.color)}, 0.15)`
                  : isRunning
                  ? `rgba(${hexRgb(agent.color)}, 0.1)`
                  : "rgba(255,255,255,0.04)",
                border: `1px solid ${isDone || isRunning ? `rgba(${hexRgb(agent.color)}, 0.3)` : "rgba(255,255,255,0.08)"}`,
              }}>
                {isDone ? (
                  <CheckCircle size={16} color={agent.color} />
                ) : isRunning ? (
                  <Loader size={16} color={agent.color} style={{ animation: "spin 1s linear infinite" }} />
                ) : (
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#4a4a5a" }}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                )}
              </div>

              {/* Labels */}
              <div style={{ flex: 1 }}>
                <div style={{
                  fontSize: 13, fontWeight: 600,
                  color: isDone ? agent.color : isRunning ? agent.color : "#475569",
                  transition: "color 0.3s",
                }}>
                  {agent.label}
                </div>
                <div style={{ fontSize: 11, color: "#52525b", marginTop: 1 }}>{agent.desc}</div>
              </div>

              {/* Right status */}
              {isDone && (
                <span style={{
                  fontSize: 10, fontWeight: 700, color: agent.color,
                  padding: "2px 8px", borderRadius: 999,
                  background: `rgba(${hexRgb(agent.color)}, 0.12)`,
                  border: `1px solid rgba(${hexRgb(agent.color)}, 0.2)`,
                }}>
                  DONE
                </span>
              )}
              {isRunning && (
                <span style={{
                  fontSize: 10, fontWeight: 700, color: agent.color,
                  animation: "pulse-glow 1.5s ease-in-out infinite",
                }}>
                  ●
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Retry count if visible */}
      {status === "done" && (
        <div style={{
          marginTop: 16, padding: "10px 14px", borderRadius: 10,
          background: "rgba(16,185,129,0.06)", border: "1px solid rgba(16,185,129,0.15)",
          fontSize: 12, color: "#6ee7b7", textAlign: "center", fontWeight: 500,
        }}>
          ✓ Pipeline complete
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    idle:    { label: "Waiting",  color: "#64748b", bg: "rgba(100,116,139,0.1)" },
    running: { label: "Running",  color: "#f59e0b", bg: "rgba(245,158,11,0.1)"  },
    done:    { label: "Complete", color: "#10b981", bg: "rgba(16,185,129,0.1)"  },
    error:   { label: "Error",    color: "#ef4444", bg: "rgba(239,68,68,0.1)"   },
  };
  const s = map[status] ?? map.idle;
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 999,
      color: s.color, background: s.bg,
      border: `1px solid ${s.color}30`,
    }}>
      {s.label}
    </span>
  );
}

function hexRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}
