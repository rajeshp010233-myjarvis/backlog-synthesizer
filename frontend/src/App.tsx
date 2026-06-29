import { useState, useEffect } from "react";
import { InputPanel } from "./components/InputPanel/InputPanel";
import { PipelineDashboard } from "./components/PipelineDashboard/PipelineDashboard";
import { OutputTabs } from "./components/OutputTabs/OutputTabs";
import { useSSE } from "./hooks/useSSE";
import { api } from "./services/api";
import type { PipelineResult, AgentModelConfigs, HistoryEntry } from "./types";
import { BrainCircuit, RefreshCw, CheckCircle, History, X, Clock, BookOpen, Star } from "lucide-react";

type AppState = "input" | "running" | "done";

const THEME = {
  bg: "#0d0d10",
  surface: "#16161a",
  border: "rgba(255,255,255,0.07)",
  borderEmphasis: "rgba(255,255,255,0.12)",
  accent: "#6366f1",
  accentMuted: "rgba(99,102,241,0.12)",
  textPrimary: "#f0f0f5",
  textSecondary: "#8b8b9a",
  textMuted: "#4a4a5a",
  success: "#22c55e",
  warning: "#f59e0b",
};

const AGENT_STEPS = [
  {
    id: "ingestion_agent",
    label: "Ingestion Agent", desc: "Extracts intents from transcripts", color: "#6366f1", num: "01",
    tooltip: "Reads meeting transcripts and wiki pages. Uses GPT-4o to extract structured user intents and indexes constraints in ChromaDB for downstream retrieval.",
  },
  {
    id: "story_writer",
    label: "Story Writer", desc: "Writes user stories with AC", color: "#8b5cf6", num: "02",
    tooltip: "Queries ChromaDB for relevant constraints per intent, then generates user stories with a title, description, and Gherkin-style acceptance criteria.",
  },
  {
    id: "gap_detector",
    label: "Gap Detector", desc: "Finds conflicts & coverage gaps", color: "#0ea5e9", num: "03",
    tooltip: "Cross-checks generated stories against your existing backlog to flag duplicate coverage, conflicting requirements, and missing functionality.",
  },
  {
    id: "evaluator",
    label: "Evaluator", desc: "LLM-as-judge quality scoring", color: "#22c55e", num: "04",
    tooltip: "Scores each story 0–5 on completeness, clarity, and testability. Triggers an automatic retry loop if the average score falls below the threshold.",
  },
];

export default function App() {
  const [sessionId, setSessionId]           = useState<string>("");
  const [appState, setAppState]             = useState<AppState>("input");
  const [result, setResult]                 = useState<PipelineResult | null>(null);
  const [lastModelConfigs, setLastModelConfigs] = useState<AgentModelConfigs>({});
  const [runKey, setRunKey]                 = useState(0);
  const [activeTooltip, setActiveTooltip]  = useState<string | null>(null);
  const [showHistory, setShowHistory]       = useState(false);
  const [history, setHistory]               = useState<HistoryEntry[]>([]);

  useEffect(() => {
    api.createSession().then(setSessionId).catch(console.error);
  }, []);

  const loadHistory = () => {
    api.getHistory().then(setHistory).catch(console.error);
  };

  const handleLoadHistoryRun = (entry: HistoryEntry) => {
    if (entry.status !== "done") return;
    api.getResults(entry.session_id).then((r) => {
      setResult(r);
      setAppState("done");
      setShowHistory(false);
    }).catch(console.error);
  };

  const { progress, status, error, reset } = useSSE(sessionId, appState === "running" ? runKey : -1);

  // Derive agent states from SSE progress
  const doneAgents = new Set(progress.filter((p) => p.status === "done").map((p) => p.agent));
  const lastAgent  = progress[progress.length - 1]?.agent ?? "";

  // Per-agent elapsed time (seconds), populated once the agent emits a "done" event
  const agentTimings: Record<string, number> = {};
  for (const p of progress) {
    if (p.status === "done" && p.elapsed_s !== undefined) {
      agentTimings[p.agent] = p.elapsed_s;
    }
  }

  useEffect(() => {
    if (status === "done") {
      api.getResults(sessionId).then((r) => {
        setResult(r);
        setAppState("done");
      });
    }
  }, [status, sessionId]);

  const handleReady = async (modelConfigs: AgentModelConfigs) => {
    setLastModelConfigs(modelConfigs);
    await api.runPipeline(sessionId, modelConfigs);
    setAppState("running");
    setRunKey((k) => k + 1);
  };

  const handleRerun = async () => {
    reset();
    setRunKey((k) => k + 1);
    await api.runPipeline(sessionId, lastModelConfigs);
  };

  const handleReset = () => {
    reset();
    setResult(null);
    setAppState("input");
    window.location.reload();
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: THEME.bg,
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
      color: THEME.textPrimary,
    }}>
      <style>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes dot-pulse { 0%,100%{opacity:.4;transform:scale(1)} 50%{opacity:1;transform:scale(1.3)} }
        @keyframes ring-pulse { 0%,100%{box-shadow:0 0 0 0 rgba(var(--ring-color),0.4)} 70%{box-shadow:0 0 0 10px rgba(var(--ring-color),0)} }
        .nav-btn:hover { background: rgba(255,255,255,0.06) !important; color: ${THEME.textPrimary} !important; }
        .upload-zone { transition: border-color .15s ease, background .15s ease, transform .15s ease; }
        .upload-zone:hover { transform: translateY(-1px); }
        .launch:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); box-shadow: 0 8px 24px rgba(99,102,241,0.3) !important; }
        .launch:active:not(:disabled) { transform: translateY(0); }
        .launch { transition: all .15s ease; }
        select { outline: none; }
        select:focus { border-color: rgba(99,102,241,0.5) !important; }
        .fade-in { animation: fadeIn 0.3s ease both; }
        @keyframes tooltipIn { from { opacity:0; transform: translateX(-50%) translateY(4px); } to { opacity:1; transform: translateX(-50%) translateY(0); } }
        .agent-tooltip { animation: tooltipIn 0.15s ease both; }
        @keyframes agent-spin { to { transform: rotate(360deg); } }
      `}</style>

      {/* ── Header ── */}
      <header style={{
        borderBottom: `1px solid ${THEME.border}`,
        background: "rgba(13,13,16,0.95)",
        backdropFilter: "blur(12px)",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{
          maxWidth: 1280, margin: "0 auto",
          padding: "0 32px", height: 56,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: "linear-gradient(135deg,#4f46e5,#7c3aed)",
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <BrainCircuit size={17} color="white" />
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: THEME.textPrimary, letterSpacing: "-0.01em" }}>
                Backlog Synthesizer
              </div>
              <div style={{ fontSize: 11, color: THEME.textMuted, marginTop: 0 }}>
                AI-powered · Multi-agent pipeline
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {appState !== "input" && (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: appState === "running" ? THEME.warning : THEME.success,
                  animation: appState === "running" ? "dot-pulse 1.5s ease-in-out infinite" : "none",
                }} />
                <span style={{ fontSize: 12, color: THEME.textSecondary }}>
                  {appState === "running" ? "Pipeline running…" : "Pipeline complete"}
                </span>
              </div>
            )}
            <button
              className="nav-btn"
              onClick={() => { loadHistory(); setShowHistory(true); }}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 6,
                background: "transparent",
                border: `1px solid ${THEME.border}`,
                color: THEME.textSecondary, fontSize: 12,
                cursor: "pointer",
              }}
            >
              <History size={11} /> History
            </button>
            {appState !== "input" && (
              <button
                className="nav-btn"
                onClick={handleReset}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "6px 12px", borderRadius: 6,
                  background: "transparent",
                  border: `1px solid ${THEME.border}`,
                  color: THEME.textSecondary, fontSize: 12,
                  cursor: "pointer",
                }}
              >
                <RefreshCw size={11} /> New session
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Main ── */}
      <main style={{ display: "flex" }}>

        {/* Left panel — config form + dashboard */}
        <div style={{
          width: 480, flexShrink: 0,
          borderRight: `1px solid ${THEME.border}`,
          background: THEME.surface,
          padding: "72px 36px 48px",
          display: "flex", flexDirection: "column",
          minHeight: "calc(100vh - 56px)",
        }}>
          <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: THEME.textPrimary, marginBottom: 6, letterSpacing: "-0.02em" }}>
              Configure your pipeline
            </div>
            <div style={{ fontSize: 12, color: THEME.textSecondary, lineHeight: 1.6 }}>
              Meeting transcripts are required · Wiki and backlog are optional
            </div>
          </div>
          <InputPanel
            sessionId={sessionId}
            onReady={handleReady}
            disabled={!sessionId || appState === "running"}
          />

          {appState !== "input" && (
            <div style={{ marginTop: 32 }}>
              <PipelineDashboard progress={progress} status={status} error={error} onRerun={handleRerun} />
            </div>
          )}
        </div>

        {/* Right panel — agents + results */}
        <div style={{
          flex: 1,
          padding: "72px 64px 48px",
          display: "flex", flexDirection: "column",
          overflowY: "auto",
        }}>
          {/* Badge */}
          <div style={{ marginBottom: 20 }}>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "4px 14px", borderRadius: 999,
              background: THEME.accentMuted,
              border: `1px solid rgba(99,102,241,0.25)`,
            }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: THEME.accent }} />
              <span style={{ fontSize: 11, fontWeight: 600, color: THEME.accent, letterSpacing: "0.05em" }}>
                MULTI-AGENT AI PIPELINE
              </span>
            </div>
          </div>

          <h1 style={{
            fontSize: 40, fontWeight: 800, lineHeight: 1.15,
            letterSpacing: "-0.03em", marginBottom: 16,
            color: THEME.textPrimary, textAlign: "center",
          }}>
            Turn meetings<br />
            into a <span style={{ color: THEME.accent }}>product backlog</span>
          </h1>

          <p style={{
            fontSize: 14, color: THEME.textSecondary, lineHeight: 1.75,
            marginBottom: 48, maxWidth: 420, textAlign: "center",
          }}>
            Four agents run in sequence — from raw transcripts to a scored, Jira-ready backlog.
          </p>

          {/* ── Agent steps with live progress ── */}
          <div style={{ display: "flex", alignItems: "flex-start" }}>
            {AGENT_STEPS.map((step, i, arr) => {
              const isDone    = doneAgents.has(step.id);
              const isRunning = !isDone && appState === "running" && lastAgent === step.id;

              const circleBorder = isDone
                ? step.color
                : isRunning
                ? step.color
                : `${step.color}55`;
              const circleBg = isDone
                ? `${step.color}22`
                : isRunning
                ? `${step.color}18`
                : `${step.color}14`;

              return (
                <div key={step.num} style={{ display: "flex", alignItems: "flex-start", flex: 1 }}>
                  <div
                    style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", flex: 1, position: "relative", cursor: "default" }}
                    onMouseEnter={() => setActiveTooltip(step.num)}
                    onMouseLeave={() => setActiveTooltip(null)}
                  >
                    {/* Tooltip */}
                    {activeTooltip === step.num && (
                      <div className="agent-tooltip" style={{
                        position: "absolute",
                        bottom: "calc(100% + 14px)",
                        left: "50%", transform: "translateX(-50%)",
                        width: 220,
                        background: "#1e1e2a",
                        border: `1px solid ${step.color}40`,
                        borderRadius: 10, padding: "12px 14px",
                        zIndex: 50,
                        boxShadow: `0 12px 32px rgba(0,0,0,0.5), 0 0 0 1px ${step.color}20`,
                        pointerEvents: "none", textAlign: "left",
                      }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: step.color, marginBottom: 6, letterSpacing: "0.03em" }}>
                          {step.label}
                        </div>
                        <div style={{ fontSize: 12, color: "#a0a0b8", lineHeight: 1.65 }}>{step.tooltip}</div>
                        <div style={{
                          position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)",
                          width: 0, height: 0,
                          borderLeft: "7px solid transparent", borderRight: "7px solid transparent",
                          borderTop: `7px solid ${step.color}40`,
                        }} />
                      </div>
                    )}

                    {/* Animated circle */}
                    <div style={{
                      width: 56, height: 56, borderRadius: "50%",
                      background: circleBg,
                      border: `2px solid ${circleBorder}`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      marginBottom: 12, flexShrink: 0,
                      transition: "all 0.4s ease",
                      boxShadow: isDone
                        ? `0 0 16px ${step.color}40`
                        : isRunning
                        ? `0 0 22px ${step.color}60, 0 0 0 4px ${step.color}20`
                        : "none",
                      position: "relative",
                    }}>
                      {/* Spinning ring for running */}
                      {isRunning && (
                        <svg
                          width="64" height="64"
                          viewBox="0 0 64 64"
                          style={{
                            position: "absolute", top: -4, left: -4,
                            animation: "agent-spin 1.2s linear infinite",
                            pointerEvents: "none",
                          }}
                        >
                          <circle
                            cx="32" cy="32" r="28"
                            fill="none"
                            stroke={step.color}
                            strokeWidth="2"
                            strokeDasharray="40 88"
                            strokeLinecap="round"
                          />
                        </svg>
                      )}

                      {isDone ? (
                        <CheckCircle size={22} color={step.color} />
                      ) : (
                        <span style={{
                          fontSize: 13, fontWeight: 700,
                          color: isRunning ? step.color : `${step.color}99`,
                          letterSpacing: "0.04em",
                          transition: "color 0.3s",
                        }}>
                          {step.num}
                        </span>
                      )}
                    </div>

                    <div style={{
                      fontSize: 13, fontWeight: 600, marginBottom: 4,
                      color: isDone ? step.color : isRunning ? step.color : THEME.textPrimary,
                      transition: "color 0.3s",
                    }}>
                      {step.label}
                    </div>
                    <div style={{ fontSize: 11, color: THEME.textSecondary, lineHeight: 1.5 }}>
                      {step.desc}
                    </div>

                    {/* Status label + elapsed time below desc */}
                    {(isDone || isRunning) && (
                      <div style={{ marginTop: 6, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                        <div style={{
                          fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
                          color: step.color,
                          opacity: isDone ? 1 : 0.8,
                          animation: isRunning ? "dot-pulse 1.5s ease-in-out infinite" : "none",
                        }}>
                          {isDone ? "✓ DONE" : "● RUNNING"}
                        </div>
                        {isDone && agentTimings[step.id] !== undefined && (
                          <div style={{
                            fontSize: 10, color: THEME.textMuted, fontVariantNumeric: "tabular-nums",
                          }}>
                            {agentTimings[step.id].toFixed(1)}s
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Connector arrow */}
                  {i < arr.length - 1 && (
                    <div style={{
                      display: "flex", alignItems: "center", flexShrink: 0,
                      marginTop: 28, padding: "0 4px",
                    }}>
                      <div style={{
                        width: 24, height: 2,
                        background: doneAgents.has(step.id)
                          ? `linear-gradient(to right, ${step.color}, ${arr[i + 1].color}80)`
                          : `linear-gradient(to right, ${step.color}80, ${arr[i + 1].color}50)`,
                        transition: "all 0.4s ease",
                      }} />
                      <svg width="8" height="10" viewBox="0 0 8 10" fill="none">
                        <path d="M1 1l5 4-5 4"
                          stroke={doneAgents.has(arr[i + 1].id) || lastAgent === arr[i + 1].id ? arr[i + 1].color : `${arr[i + 1].color}60`}
                          strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                          style={{ transition: "stroke 0.4s" }}
                        />
                      </svg>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Tech badges */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 32 }}>
            {["LangGraph", "FastAPI", "ChromaDB", "Redis", "OpenAI"].map((tech) => (
              <span key={tech} style={{
                fontSize: 11, padding: "3px 8px", borderRadius: 4,
                background: "rgba(255,255,255,0.03)",
                border: `1px solid ${THEME.border}`,
                color: THEME.textMuted,
              }}>
                {tech}
              </span>
            ))}
          </div>

          {/* Running hint */}
          {appState === "running" && (
            <div className="fade-in" style={{ marginTop: 40, textAlign: "center", color: THEME.textSecondary }}>
              <div style={{ fontSize: 13 }}>Results will appear below when the pipeline completes</div>
            </div>
          )}

          {/* Halted */}
          {appState === "done" && result?.halt_reason && (
            <div className="fade-in" style={{ marginTop: 48 }}>
              <div style={{
                background: "rgba(245,158,11,0.06)",
                border: "1px solid rgba(245,158,11,0.2)",
                borderRadius: 16, padding: 24,
              }}>
                <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8, flexShrink: 0,
                    background: "rgba(245,158,11,0.12)",
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
                  }}>⚠</div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "#fbbf24", marginBottom: 6 }}>
                      Pipeline stopped early
                    </div>
                    <div style={{ fontSize: 13, color: "#a16207", lineHeight: 1.6 }}>{result.halt_reason}</div>
                    <button onClick={handleReset} style={{
                      marginTop: 14, padding: "8px 18px", borderRadius: 8,
                      background: "#d97706", border: "none",
                      color: "white", fontSize: 13, fontWeight: 600, cursor: "pointer",
                    }}>
                      Start over
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Results below agents */}
          {appState === "done" && result && !result.halt_reason && (
            <div className="fade-in" style={{ marginTop: 48 }}>
              <div style={{
                height: 1,
                background: `linear-gradient(to right, transparent, ${THEME.borderEmphasis}, transparent)`,
                marginBottom: 36,
              }} />
              <OutputTabs result={result} />
            </div>
          )}
        </div>
      </main>

      {/* ── History panel (slide-over) ── */}
      {showHistory && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 200,
          display: "flex", justifyContent: "flex-end",
        }}>
          {/* Backdrop */}
          <div
            onClick={() => setShowHistory(false)}
            style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)" }}
          />

          {/* Panel */}
          <div style={{
            position: "relative", width: 440,
            background: THEME.surface,
            borderLeft: `1px solid ${THEME.border}`,
            display: "flex", flexDirection: "column",
            height: "100vh", overflowY: "auto",
            animation: "fadeIn 0.2s ease both",
          }}>
            {/* Header */}
            <div style={{
              padding: "20px 24px",
              borderBottom: `1px solid ${THEME.border}`,
              display: "flex", alignItems: "center", justifyContent: "space-between",
              position: "sticky", top: 0,
              background: THEME.surface, zIndex: 1,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <History size={16} color={THEME.accent} />
                <span style={{ fontSize: 14, fontWeight: 700, color: THEME.textPrimary }}>Execution History</span>
                <span style={{
                  fontSize: 11, padding: "2px 8px", borderRadius: 999,
                  background: THEME.accentMuted, color: THEME.accent, fontWeight: 600,
                }}>
                  {history.filter(h => h.status === "done").length} runs
                </span>
              </div>
              <button onClick={() => setShowHistory(false)} style={{
                background: "transparent", border: "none",
                color: THEME.textMuted, cursor: "pointer", padding: 4, borderRadius: 4,
              }}>
                <X size={16} />
              </button>
            </div>

            {/* Entries */}
            <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              {history.length === 0 && (
                <div style={{ textAlign: "center", padding: 48, color: THEME.textMuted, fontSize: 13 }}>
                  No executions yet.<br />Run the pipeline to see history here.
                </div>
              )}
              {history.map((entry) => {
                const isDone  = entry.status === "done";
                const isError = entry.status === "error";
                const date    = new Date(entry.created_at);
                const dateStr = date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
                const timeStr = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
                const statusColor = isDone ? THEME.success : isError ? "#f87171" : THEME.warning;

                return (
                  <div
                    key={entry.session_id}
                    onClick={() => isDone && handleLoadHistoryRun(entry)}
                    style={{
                      padding: "14px 16px", borderRadius: 10,
                      border: `1px solid ${THEME.border}`,
                      background: isDone ? "rgba(255,255,255,0.02)" : "transparent",
                      cursor: isDone ? "pointer" : "default",
                      transition: "border-color 0.15s, background 0.15s",
                    }}
                    onMouseEnter={e => { if (isDone) (e.currentTarget as HTMLDivElement).style.borderColor = THEME.accent; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderColor = THEME.border; }}
                  >
                    {/* Top row */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 600, color: THEME.textPrimary, marginBottom: 2 }}>
                          {dateStr} · {timeStr}
                        </div>
                        <div style={{ fontSize: 10, color: THEME.textMuted, fontFamily: "monospace" }}>
                          {entry.session_id.slice(0, 16)}…
                        </div>
                      </div>
                      <div style={{
                        fontSize: 10, fontWeight: 700, letterSpacing: "0.05em",
                        padding: "3px 8px", borderRadius: 999,
                        background: `${statusColor}18`, color: statusColor,
                        border: `1px solid ${statusColor}30`,
                      }}>
                        {entry.status.toUpperCase()}
                      </div>
                    </div>

                    {/* Stats row */}
                    {isDone && (
                      <div style={{ display: "flex", gap: 16 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <BookOpen size={11} color={THEME.textMuted} />
                          <span style={{ fontSize: 11, color: THEME.textSecondary }}>
                            {entry.story_count ?? 0} stories
                          </span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <Star size={11} color={THEME.textMuted} />
                          <span style={{ fontSize: 11, color: THEME.textSecondary }}>
                            {entry.overall_score?.toFixed(1) ?? "—"} / 5
                          </span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <Clock size={11} color={THEME.textMuted} />
                          <span style={{ fontSize: 11, color: THEME.textSecondary }}>
                            {entry.total_elapsed_s?.toFixed(0) ?? "—"}s
                          </span>
                        </div>
                        {(entry.retry_count ?? 0) > 0 && (
                          <span style={{ fontSize: 11, color: THEME.warning }}>
                            {entry.retry_count} retry
                          </span>
                        )}
                      </div>
                    )}

                    {isError && (
                      <div style={{ fontSize: 11, color: "#f87171", marginTop: 4 }}>
                        {entry.error?.slice(0, 80)}
                      </div>
                    )}

                    {isDone && (
                      <div style={{ marginTop: 10, fontSize: 11, color: THEME.accent, fontWeight: 600 }}>
                        Click to load results →
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
