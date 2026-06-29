"""
Merged ingestion agent — replaces the old context_loader + transcript_analyzer pair.

Responsibilities:
  1. Extract architecture constraints from wiki/Confluence texts → ChromaDB
  2. MAP  — extract intents from transcript batches in parallel (ThreadPoolExecutor)
  3. REDUCE — one LLM call merges and deduplicates all raw intents across batches

Call budget: 1 (wiki) + ⌈N÷3⌉ parallel map calls + 1 reduce call
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.agents.harness import agent_harness
from app.config import get_settings
from app.models.state import BacklogState
from app.providers import complete_for_agent
from app.tools.document_parser import hash_content
from app.tools.vector_store import upsert_documents
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)

_TRANSCRIPT_BATCH_SIZE = 3    # transcripts per map call
_TRANSCRIPT_CHAR_LIMIT = 6000 # characters kept per transcript
_BATCH_CONCURRENCY    = 5    # max parallel LLM calls (rate-limit guard)
_REDUCE_INTENT_CAP    = 150  # max raw intents sent to the reduce call

CONSTRAINTS_SYSTEM = (
    "You are an architecture analyst. Extract all technical constraints, "
    "design decisions, and system boundaries from the provided wiki/Confluence content. "
    "Return a JSON array of constraint objects with fields: id, category, description, impact."
)

INTENTS_SYSTEM = (
    "You are a product analyst. Analyze the provided customer meeting transcript(s) and extract "
    "from EACH transcript: pain points, feature requests, user goals, and implicit needs. "
    "Return a SINGLE JSON array combining all intents across all transcripts. "
    "For each intent use fields: {id, type, title, description, priority, speaker_role, source_quote, source_transcript}. "
    "Set source_transcript to the label shown above each transcript (e.g. 'Transcript 1'). "
    "Types: pain_point | feature_request | user_goal | implicit_need"
)

REDUCE_SYSTEM = (
    "You are a product analyst. You have received intents extracted from multiple meeting transcripts. "
    "Many may be duplicates or near-duplicates (same pain point phrased differently across meetings). "
    "Your task: merge duplicates into one canonical intent keeping the most detailed version. "
    "Do NOT drop unique intents. Do NOT invent new intents not present in the input. "
    "Return a deduplicated JSON array using the same schema: "
    "{id, type, title, description, priority, speaker_role, source_quote, source_transcript}."
)


def _run_map_batch(state: dict, settings, batch: list[str], batch_start: int) -> tuple[list, dict]:
    """Single map-phase worker — runs in a thread pool thread."""
    user_content = "\n\n".join(
        f"=== Transcript {batch_start + i + 1} ===\n{t[:_TRANSCRIPT_CHAR_LIMIT]}"
        for i, t in enumerate(batch)
    )
    raw, trace = complete_for_agent(
        state=state,
        agent_name="ingestion_agent",
        default_provider=settings.default_provider,
        default_model=settings.specialist_model,
        system=INTENTS_SYSTEM,
        user=user_content,
        max_tokens=min(3000 * len(batch), 8000),
    )
    try:
        intents = extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        intents = []
    return intents, trace


@agent_harness(required_inputs=["transcript_texts"])
def ingestion_agent_node(state: BacklogState) -> dict:
    settings   = get_settings()
    session_id = state["session_id"]
    wiki_texts  = state.get("wiki_texts", [])
    transcripts = state.get("transcript_texts", [])

    traces      = []
    audit       = []
    constraints = []
    all_intents = []

    # ── 1. Wiki → architecture constraints ────────────────────────────────────
    if wiki_texts:
        combined  = "\n\n---\n\n".join(wiki_texts)
        wiki_hash = hash_content(combined)

        upsert_documents(
            namespace="constraints",
            session_id=session_id,
            docs=wiki_texts,
            ids=[f"wiki_{i}" for i in range(len(wiki_texts))],
        )

        raw, trace = complete_for_agent(
            state=state,
            agent_name="ingestion_agent",
            default_provider=settings.default_provider,
            default_model=settings.specialist_model,
            system=CONSTRAINTS_SYSTEM,
            user=f"Wiki content:\n\n{combined[:8000]}",
            max_tokens=2048,
        )
        traces.append(trace)

        try:
            constraints = extract_json(raw)
        except (ValueError, json.JSONDecodeError):
            constraints = [{"id": "c1", "category": "general", "description": raw, "impact": "unknown"}]

        audit.append(_audit(
            "ingestion_agent", "extract_constraints", wiki_hash,
            hash_content(json.dumps(constraints)),
            f"Extracted {len(constraints)} constraints from {len(wiki_texts)} wiki document(s)",
            details={
                "wiki_docs": len(wiki_texts),
                "constraints_extracted": len(constraints),
                "provider": trace.get("provider"),
                "model": trace.get("model"),
                "approx_input_tokens": trace.get("approx_input_tokens"),
                "approx_output_tokens": trace.get("approx_output_tokens"),
                "constraint_categories": list({c.get("category") for c in constraints if c.get("category")}),
                "system_prompt": CONSTRAINTS_SYSTEM,
                "ai_decision": "LLM instructed to extract technical constraints, design decisions, and system boundaries as structured JSON.",
            },
        ))
    else:
        audit.append(_audit("ingestion_agent", "skip_wiki", "", "", "No wiki content provided"))

    # ── 2. MAP — parallel batched intent extraction ────────────────────────────
    if transcripts:
        batches = [
            transcripts[i:i + _TRANSCRIPT_BATCH_SIZE]
            for i in range(0, len(transcripts), _TRANSCRIPT_BATCH_SIZE)
        ]
        logger.info(
            "[ingestion_agent] session=%s — %d transcript(s) → %d batch(es), concurrency=%d",
            session_id, len(transcripts), len(batches), _BATCH_CONCURRENCY,
        )

        raw_intents: list = []
        with ThreadPoolExecutor(max_workers=_BATCH_CONCURRENCY) as pool:
            future_to_idx = {
                pool.submit(
                    _run_map_batch, state, settings,
                    batch, idx * _TRANSCRIPT_BATCH_SIZE,
                ): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(future_to_idx):
                intents, trace = future.result()
                raw_intents.extend(intents)
                traces.append(trace)

        logger.info(
            "[ingestion_agent] session=%s — map complete: %d raw intents from %d batch(es)",
            session_id, len(raw_intents), len(batches),
        )

        # ── 3. REDUCE — deduplicate across all batch results ──────────────────
        if raw_intents:
            truncated    = len(raw_intents) > _REDUCE_INTENT_CAP
            reduce_input = raw_intents[:_REDUCE_INTENT_CAP]
            if truncated:
                logger.warning(
                    "[ingestion_agent] session=%s — %d raw intents, capped to %d for reduce call",
                    session_id, len(raw_intents), _REDUCE_INTENT_CAP,
                )

            reduce_raw, reduce_trace = complete_for_agent(
                state=state,
                agent_name="ingestion_agent",
                default_provider=settings.default_provider,
                default_model=settings.specialist_model,
                system=REDUCE_SYSTEM,
                user=(
                    f"Raw intents from {len(batches)} batch(es) "
                    f"({len(reduce_input)} items):\n"
                    f"{json.dumps(reduce_input, indent=2)}"
                ),
                max_tokens=6000,
            )
            traces.append(reduce_trace)

            try:
                all_intents = extract_json(reduce_raw)
            except (ValueError, json.JSONDecodeError):
                # Reduce failed — fall back to raw intents so the pipeline continues
                logger.warning(
                    "[ingestion_agent] session=%s — reduce parse failed, using raw intents",
                    session_id,
                )
                all_intents = raw_intents

        # Collect token usage across all batch traces + reduce trace
        total_in  = sum(t.get("approx_input_tokens", 0)  for t in traces)
        total_out = sum(t.get("approx_output_tokens", 0) for t in traces)
        last_trace = traces[-1] if traces else {}
        audit.append(_audit(
            "ingestion_agent", "extract_intents",
            hash_content(str(transcripts)), hash_content(json.dumps(all_intents)),
            f"Map: {len(raw_intents)} raw intents from {len(transcripts)} transcript(s) "
            f"across {len(batches)} parallel batch(es). "
            f"Reduce: {len(all_intents)} deduplicated intents.",
            details={
                "transcripts": len(transcripts),
                "batches": len(batches),
                "batch_size": _TRANSCRIPT_BATCH_SIZE,
                "raw_intents": len(raw_intents),
                "final_intents": len(all_intents),
                "intent_types": list({i.get("type") for i in all_intents if i.get("type")}),
                "provider": last_trace.get("provider"),
                "model": last_trace.get("model"),
                "approx_input_tokens": total_in,
                "approx_output_tokens": total_out,
                "llm_calls": len(traces),
                "map_system_prompt": INTENTS_SYSTEM,
                "reduce_system_prompt": REDUCE_SYSTEM,
                "ai_decision": (
                    f"Map phase: LLM extracted pain points, feature requests, user goals, and implicit needs "
                    f"from each transcript batch independently. "
                    f"Reduce phase: LLM merged {len(raw_intents)} raw intents into {len(all_intents)} "
                    f"deduplicated canonical intents, preserving the most detailed version of each."
                ),
            },
        ))
    else:
        audit.append(_audit("ingestion_agent", "skip_transcripts", "", "", "No transcripts provided"))

    return {
        "architecture_constraints": constraints,
        "extracted_intents": all_intents,
        "prompt_traces": traces,
        "audit_log": audit,
        "progress": [{"agent": "ingestion_agent", "status": "done", "timestamp": _now()}],
    }


def _audit(agent, tool, input_hash, output_hash, reasoning, details: dict | None = None):
    entry = {
        "agent": agent, "tool": tool,
        "input_hash": input_hash, "output_hash": output_hash,
        "reasoning": reasoning, "timestamp": _now(),
    }
    if details:
        entry["details"] = details
    return entry


def _now():
    return datetime.now(timezone.utc).isoformat()
