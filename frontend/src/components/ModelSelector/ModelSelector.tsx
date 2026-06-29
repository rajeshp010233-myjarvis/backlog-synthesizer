import { useState } from "react";
import { ChevronDown, ChevronUp, Bot } from "lucide-react";
import type {
  AgentModelConfigs,
  AgentModelConfig,
  AgentName,
  ModelProvider,
} from "../../types";
import { MODEL_OPTIONS, AGENT_LABELS } from "../../types";

const AGENTS: AgentName[] = [
  "ingestion_agent",
  "story_writer",
  "gap_detector",
  "evaluator",
];

const PROVIDER_LABELS: Record<ModelProvider, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Gemini",
  ollama: "Ollama (local)",
};

const PROVIDER_COLORS: Record<ModelProvider, string> = {
  anthropic: "bg-orange-100 text-orange-700",
  openai: "bg-green-100 text-green-700",
  gemini: "bg-blue-100 text-blue-700",
  ollama: "bg-purple-100 text-purple-700",
};

interface Props {
  configs: AgentModelConfigs;
  onChange: (configs: AgentModelConfigs) => void;
}

export function ModelSelector({ configs, onChange }: Props) {
  const [open, setOpen] = useState(false);

  const setAgentConfig = (agent: AgentName, cfg: Partial<AgentModelConfig>) => {
    const current = configs[agent] ?? { provider: "openai", model: "gpt-4o" };
    const updated = { ...current, ...cfg };
    // Reset model when provider changes
    if (cfg.provider && cfg.provider !== current.provider) {
      updated.model = MODEL_OPTIONS[cfg.provider][0];
    }
    onChange({ ...configs, [agent]: updated });
  };

  const summary = () => {
    const providers = new Set(
      Object.values(configs).map((c) => PROVIDER_LABELS[c.provider])
    );
    if (providers.size === 0) return "All agents using OpenAI (default)";
    return `Using: ${[...providers].join(", ")}`;
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-indigo-500" />
          <span className="text-sm font-medium text-gray-700">Model Selection per Agent</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">{summary()}</span>
          {open ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
        </div>
      </button>

      {open && (
        <div className="divide-y divide-gray-100">
          {AGENTS.map((agent) => {
            const cfg = configs[agent] ?? { provider: "anthropic" as ModelProvider, model: "claude-sonnet-4-6" };
            const provider = cfg.provider as ModelProvider;
            const models = MODEL_OPTIONS[provider];

            return (
              <div key={agent} className="px-4 py-3 flex items-center gap-3 flex-wrap">
                <div className="w-40 flex-shrink-0">
                  <p className="text-sm font-medium text-gray-700">{AGENT_LABELS[agent]}</p>
                </div>

                {/* Provider select */}
                <select
                  value={provider}
                  onChange={(e) => setAgentConfig(agent, { provider: e.target.value as ModelProvider })}
                  className="text-sm border border-gray-200 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
                >
                  {(Object.keys(PROVIDER_LABELS) as ModelProvider[]).map((p) => (
                    <option key={p} value={p}>{PROVIDER_LABELS[p]}</option>
                  ))}
                </select>

                {/* Model select or text input for Ollama custom models */}
                {provider === "ollama" ? (
                  <input
                    type="text"
                    value={cfg.model}
                    onChange={(e) => setAgentConfig(agent, { model: e.target.value })}
                    placeholder="e.g. llama3, mistral"
                    className="text-sm border border-gray-200 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300 w-40"
                  />
                ) : (
                  <select
                    value={cfg.model}
                    onChange={(e) => setAgentConfig(agent, { model: e.target.value })}
                    className="text-sm border border-gray-200 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  >
                    {models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                )}

                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${PROVIDER_COLORS[provider]}`}>
                  {PROVIDER_LABELS[provider]}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
