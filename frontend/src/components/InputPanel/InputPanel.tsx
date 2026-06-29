import React, { useRef, useState } from "react";
import { FileText, Database, BookOpen, Zap, ChevronDown, ChevronUp, X, CheckCircle2, Upload } from "lucide-react";
import { api } from "../../services/api";
import type { AgentModelConfigs, AgentName, ModelProvider } from "../../types";
import { MODEL_OPTIONS, AGENT_LABELS } from "../../types";

interface Props {
  sessionId: string;
  onReady: (modelConfigs: AgentModelConfigs) => void;
  disabled?: boolean;
}

const AGENTS: AgentName[] = ["ingestion_agent", "story_writer", "gap_detector", "evaluator"];
const PROVIDERS: ModelProvider[] = ["openai", "anthropic", "gemini", "ollama"];

const PROVIDER_META: Record<ModelProvider, { color: string; label: string }> = {
  openai:    { color: "#10b981", label: "OpenAI"    },
  anthropic: { color: "#f97316", label: "Anthropic" },
  gemini:    { color: "#3b82f6", label: "Gemini"    },
  ollama:    { color: "#8b5cf6", label: "Ollama"    },
};

const INPUT_STYLE: React.CSSProperties = {
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 6, color: "#f0f0f5",
  fontSize: 12, padding: "5px 8px",
  cursor: "pointer", outline: "none",
};

export function InputPanel({ sessionId, onReady, disabled = false }: Props) {
  const [transcripts, setTranscripts] = useState<File[]>([]);
  const [wiki, setWiki]               = useState<File[]>([]);
  const [backlog, setBacklog]         = useState<File | null>(null);
  const [uploading, setUploading]     = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [agentOpen, setAgentOpen]     = useState(false);
  const [modelConfigs, setModelConfigs] = useState<AgentModelConfigs>({});
  const [dragOver, setDragOver]       = useState<string | null>(null);

  const tRef = useRef<HTMLInputElement>(null);
  const wRef = useRef<HTMLInputElement>(null);
  const bRef = useRef<HTMLInputElement>(null);

  const setAgent = (agent: AgentName, provider: ModelProvider, model: string) => {
    setModelConfigs((p) => ({ ...p, [agent]: { provider, model } }));
  };

  const handleUpload = async () => {
    setUploading(true);
    setUploadError(null);
    try {
      if (transcripts.length > 0) await api.uploadTranscripts(sessionId, transcripts);
      if (wiki.length > 0)        await api.uploadWiki(sessionId, wiki);
      if (backlog)                 await api.uploadBacklog(sessionId, backlog);
      onReady(modelConfigs);
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? (e instanceof Error ? e.message : "Upload failed. Please try again.");
      setUploadError(msg);
      console.error(e);
    } finally {
      setUploading(false);
    }
  };

  const drop = (type: "t" | "w" | "b") => (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(null);
    const files = Array.from(e.dataTransfer.files);
    if (type === "t") setTranscripts(files);
    else if (type === "w") setWiki(files);
    else setBacklog(files[0] ?? null);
  };

  const ready = transcripts.length > 0 && !disabled;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, opacity: disabled ? 0.5 : 1, pointerEvents: disabled ? "none" : "auto" }}>

      {/* ── Transcript zone (primary) ── */}
      <Zone
        label="Meeting Transcripts"
        hint="PDF · TXT · DOCX"
        badge="Required"
        badgeColor="#6366f1"
        icon={<FileText size={18} />}
        accent="#6366f1"
        files={transcripts}
        dragging={dragOver === "t"}
        onDragOver={() => setDragOver("t")}
        onDragLeave={() => setDragOver(null)}
        onDrop={drop("t")}
        onClick={() => tRef.current?.click()}
        onClear={() => setTranscripts([])}
        primary
      />
      <input ref={tRef} type="file" hidden multiple accept=".pdf,.txt,.docx"
        onChange={(e) => setTranscripts(Array.from(e.target.files ?? []))} />

      {/* ── Wiki + Backlog stacked ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Zone
          label="Wiki / Confluence"
          hint="HTML · PDF · TXT"
          badge="Optional"
          badgeColor="#0ea5e9"
          icon={<BookOpen size={16} />}
          accent="#0ea5e9"
          files={wiki}
          dragging={dragOver === "w"}
          onDragOver={() => setDragOver("w")}
          onDragLeave={() => setDragOver(null)}
          onDrop={drop("w")}
          onClick={() => wRef.current?.click()}
          onClear={() => setWiki([])}
        />
        <Zone
          label="Existing Backlog"
          hint="JSON export"
          badge="Optional"
          badgeColor="#8b5cf6"
          icon={<Database size={16} />}
          accent="#8b5cf6"
          files={backlog ? [backlog] : []}
          dragging={dragOver === "b"}
          onDragOver={() => setDragOver("b")}
          onDragLeave={() => setDragOver(null)}
          onDrop={drop("b")}
          onClick={() => bRef.current?.click()}
          onClear={() => setBacklog(null)}
        />
      </div>
      <input ref={wRef} type="file" hidden multiple accept=".html,.htm,.pdf,.txt"
        onChange={(e) => setWiki(Array.from(e.target.files ?? []))} />
      <input ref={bRef} type="file" hidden accept=".json"
        onChange={(e) => setBacklog(e.target.files?.[0] ?? null)} />

      {/* ── Divider ── */}
      <div style={{ height: 1, background: "rgba(255,255,255,0.06)", margin: "4px 0" }} />

      {/* ── Agent model config ── */}
      <div>
        <button
          onClick={() => setAgentOpen((o) => !o)}
          style={{
            width: "100%", display: "flex", alignItems: "center",
            justifyContent: "space-between", padding: "10px 14px",
            background: "transparent",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: agentOpen ? "8px 8px 0 0" : 8,
            cursor: "pointer", color: "#8b8b9a",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Zap size={14} color="#6366f1" />
            <span style={{ fontSize: 12, fontWeight: 600, color: "#c8c8d8" }}>
              Agent model configuration
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "#4a4a5a" }}>
              {Object.keys(modelConfigs).length === 0
                ? "Using OpenAI defaults"
                : `${Object.keys(modelConfigs).length} agent${Object.keys(modelConfigs).length > 1 ? "s" : ""} customized`}
            </span>
            {agentOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </div>
        </button>

        {agentOpen && (
          <div style={{
            border: "1px solid rgba(255,255,255,0.07)",
            borderTop: "none",
            borderRadius: "0 0 8px 8px",
            overflow: "hidden",
          }}>
            {/* Column header */}
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 110px 130px 16px",
              gap: 8, padding: "7px 14px",
              background: "rgba(255,255,255,0.02)",
              borderBottom: "1px solid rgba(255,255,255,0.05)",
            }}>
              {["Agent", "Provider", "Model", ""].map((h) => (
                <span key={h} style={{ fontSize: 10, fontWeight: 600, color: "#4a4a5a", letterSpacing: "0.06em" }}>
                  {h.toUpperCase()}
                </span>
              ))}
            </div>

            {AGENTS.map((agent, i) => {
              const cfg      = modelConfigs[agent] ?? { provider: "openai" as ModelProvider, model: "gpt-4o" };
              const provider = cfg.provider as ModelProvider;
              const meta     = PROVIDER_META[provider];
              return (
                <div key={agent} className="agent-row" style={{
                  display: "grid", gridTemplateColumns: "1fr 110px 130px 16px",
                  gap: 8, padding: "9px 14px", alignItems: "center",
                  borderTop: i > 0 ? "1px solid rgba(255,255,255,0.04)" : undefined,
                  transition: "background .12s",
                }}>
                  <span style={{ fontSize: 12, color: "#a0a0b0", fontWeight: 500 }}>
                    {AGENT_LABELS[agent]}
                  </span>

                  <select
                    value={provider}
                    style={INPUT_STYLE}
                    onChange={(e) => {
                      const p = e.target.value as ModelProvider;
                      setAgent(agent, p, MODEL_OPTIONS[p][0]);
                    }}
                  >
                    {PROVIDERS.map((p) => (
                      <option key={p} value={p} style={{ background: "#1c1c22" }}>
                        {PROVIDER_META[p].label}
                      </option>
                    ))}
                  </select>

                  {provider === "ollama" ? (
                    <input
                      type="text"
                      value={cfg.model}
                      placeholder="e.g. llama3"
                      style={{ ...INPUT_STYLE, width: "100%" }}
                      onChange={(e) => setAgent(agent, provider, e.target.value)}
                    />
                  ) : (
                    <select
                      value={cfg.model}
                      style={INPUT_STYLE}
                      onChange={(e) => setAgent(agent, provider, e.target.value)}
                    >
                      {MODEL_OPTIONS[provider].map((m) => (
                        <option key={m} value={m} style={{ background: "#1c1c22" }}>{m}</option>
                      ))}
                    </select>
                  )}

                  <div style={{
                    width: 7, height: 7, borderRadius: "50%",
                    background: meta.color,
                    boxShadow: `0 0 5px ${meta.color}80`,
                  }} />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Upload error ── */}
      {uploadError && (
        <div style={{
          padding: "10px 14px", borderRadius: 8,
          background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)",
          fontSize: 12, color: "#fca5a5", lineHeight: 1.5,
        }}>
          {uploadError}
        </div>
      )}

      {/* ── Launch button ── */}
      <button
        className="launch"
        disabled={!ready || uploading}
        onClick={handleUpload}
        style={{
          marginTop: 4,
          width: "100%", padding: "13px",
          borderRadius: 10, border: "none",
          background: ready
            ? "linear-gradient(135deg,#4f46e5,#6d28d9)"
            : "rgba(255,255,255,0.05)",
          color: ready ? "white" : "#3a3a4a",
          fontSize: 13, fontWeight: 600,
          cursor: ready ? "pointer" : "not-allowed",
          letterSpacing: "0.01em",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          boxShadow: ready ? "0 4px 16px rgba(79,70,229,0.25)" : "none",
        }}
      >
        {uploading ? (
          <>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
              style={{ animation: "spin 0.8s linear infinite" }}>
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            Uploading &amp; initializing…
          </>
        ) : (
          <>
            <Zap size={14} />
            {ready ? "Launch pipeline" : "Upload transcripts to begin"}
          </>
        )}
      </button>
    </div>
  );
}

/* ── Upload Zone Component ── */

interface ZoneProps {
  label: string; hint: string; badge: string; badgeColor: string;
  icon: React.ReactNode; accent: string; files: File[];
  dragging: boolean; primary?: boolean;
  onDragOver(): void; onDragLeave(): void;
  onDrop(e: React.DragEvent): void;
  onClick(): void; onClear(): void;
}

function Zone({ label, hint, badge, badgeColor, icon, accent, files, dragging, primary, onDragOver, onDragLeave, onDrop, onClick, onClear }: ZoneProps) {
  const has = files.length > 0;

  return (
    <div
      className="upload-zone"
      onDragOver={(e) => { e.preventDefault(); onDragOver(); }}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 14,
        padding: primary ? "16px 18px" : "12px 16px",
        borderRadius: 10, cursor: "pointer",
        border: `1.5px dashed ${has ? accent : dragging ? accent : "rgba(255,255,255,0.1)"}`,
        background: has
          ? `${accent}0d`
          : dragging
          ? `${accent}08`
          : "rgba(255,255,255,0.02)",
      }}
    >
      {/* Icon */}
      <div style={{
        width: primary ? 40 : 34, height: primary ? 40 : 34,
        borderRadius: 8, flexShrink: 0,
        background: has ? `${accent}1a` : "rgba(255,255,255,0.04)",
        border: `1px solid ${has ? `${accent}40` : "rgba(255,255,255,0.07)"}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        color: has ? accent : "#4a4a5a",
        transition: "all .15s",
      }}>
        {has ? <CheckCircle2 size={primary ? 18 : 15} color={accent} /> : icon}
      </div>

      {/* Text */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 2 }}>
          <span style={{
            fontSize: primary ? 13 : 12,
            fontWeight: 600,
            color: has ? "#f0f0f5" : "#8b8b9a",
          }}>
            {label}
          </span>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
            padding: "1px 5px", borderRadius: 3,
            background: `${badgeColor}18`, color: badgeColor,
          }}>
            {badge.toUpperCase()}
          </span>
        </div>
        <div style={{ fontSize: 11, color: has ? accent : "#3a3a4a", fontWeight: has ? 500 : 400 }}>
          {has
            ? files.map((f) => f.name).join(", ")
            : `${hint} · click or drag`}
        </div>
      </div>

      {/* Right action */}
      {has ? (
        <button
          onClick={(e) => { e.stopPropagation(); onClear(); }}
          style={{
            width: 24, height: 24, borderRadius: "50%", border: "none",
            background: "rgba(255,255,255,0.07)", cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#4a4a5a", flexShrink: 0,
          }}
        >
          <X size={11} />
        </button>
      ) : (
        <Upload size={13} color="#3a3a4a" style={{ flexShrink: 0 }} />
      )}
    </div>
  );
}
