"""Agent harness — decorator applied to every agent node in the pipeline.

Responsibilities (applied centrally so individual agents contain zero boilerplate):

1. INPUT VALIDATION  — checks that required state fields are present and non-empty
                        before the agent runs; returns a safe error state if not.

2. STRUCTURED LOGGING — logs agent start, completion time, session ID, and
                        retry attempt number so every run is traceable in prod.

3. RETRY ON FAILURE  — if the agent raises an exception (LLM 500, rate-limit,
                        ChromaDB timeout, etc.) it is retried once after a short
                        backoff before being declared failed.

4. SAFE ERROR STATE  — if all retries are exhausted the harness returns a valid
                        LangGraph state dict (errors + halt_reason + progress event)
                        so the graph does NOT crash and the SSE stream gets a clean
                        error event instead of an unhandled exception.

5. TOKEN BUDGET GUARD — estimates the combined size of required inputs and emits a
                        WARNING log if it is likely to exceed a 128 k-token context
                        window (rough heuristic: 1 token ≈ 4 chars).

6. TAMPER-EVIDENT AUDIT CHAIN — after every agent (success or failure) appends a
                        cryptographic chain entry to audit_log containing:
                          - input_hash:      SHA-256 of state inputs before the run
                          - output_hash:     SHA-256 of substantive outputs after the run
                          - prev_entry_hash: hash of the previous chain entry ("genesis" if first)
                          - entry_hash:      SHA-256 of this entry (next entry chains to this)
                          - recorded_at:     harness-controlled UTC timestamp (agents cannot fake it)
                        Deleting, reordering, or modifying any entry breaks the chain.

Usage
-----
    from app.agents.harness import agent_harness

    @agent_harness(required_inputs=["transcript_texts"])
    def ingestion_agent_node(state: BacklogState) -> dict:
        ...
"""

import functools
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Callable

from app.exceptions import NonRetryableError

logger = logging.getLogger(__name__)

# Retry config
_MAX_RETRIES   = 1        # one automatic retry on transient failure
_RETRY_DELAY_S = 2.0     # seconds to wait before the retry attempt

# Rough token budget guard: warn if combined required-input text exceeds this
_TOKEN_BUDGET_WARNING = 100_000   # tokens
_CHARS_PER_TOKEN      = 4

# Fields written by the harness/LangGraph infrastructure — excluded from output_hash
# so that the hash covers only the agent's substantive work product.
_AUDIT_EXCLUDED_FIELDS = {"audit_log", "prompt_traces", "progress", "story_iterations", "errors"}


# ── Hashing helpers ────────────────────────────────────────────────────────────

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _hash_inputs(state: dict, keys: list[str]) -> str:
    snapshot = {k: state.get(k) for k in keys}
    return _sha256(json.dumps(snapshot, sort_keys=True, default=str))


def _hash_output(result: dict) -> str:
    snapshot = {k: v for k, v in result.items() if k not in _AUDIT_EXCLUDED_FIELDS}
    return _sha256(json.dumps(snapshot, sort_keys=True, default=str))


def _prev_chain_hash(audit_log: list[dict]) -> str:
    """Return the entry_hash of the last harness chain entry, or 'genesis'."""
    for entry in reversed(audit_log):
        if entry.get("tool") == "harness_chain" and "entry_hash" in entry:
            return entry["entry_hash"]
    return "genesis"


def _build_chain_entry(
    agent_name: str,
    input_hash: str,
    output_hash: str,
    prev_hash: str,
    elapsed_s: float,
    status: str,
    note: str = "",
) -> dict:
    """Build a self-hashing chain entry.  entry_hash covers all other fields."""
    entry: dict = {
        "agent":           agent_name,
        "tool":            "harness_chain",
        "status":          status,          # "ok" | "error" | "validation_failed"
        "input_hash":      input_hash,
        "output_hash":     output_hash,
        "prev_entry_hash": prev_hash,
        "recorded_at":     datetime.now(timezone.utc).isoformat(),
        "elapsed_s":       round(elapsed_s, 3),
    }
    if note:
        entry["note"] = note
    # entry_hash is computed last and covers every other field
    entry["entry_hash"] = _sha256(json.dumps(entry, sort_keys=True))
    return entry


# ── Core helpers ───────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_state(
    agent_name: str,
    message: str,
    existing_errors: list,
    chain_entry: dict | None = None,
) -> dict:
    """Return a LangGraph-safe state dict representing a failed agent run."""
    logger.error("[%s] %s", agent_name, message)
    audit: list[dict] = [{
        "agent":       agent_name,
        "tool":        "harness",
        "input_hash":  "",
        "output_hash": "",
        "reasoning":   message,
        "timestamp":   _now(),
    }]
    if chain_entry:
        audit.append(chain_entry)
    return {
        "errors":      existing_errors + [message],
        "halt_reason": f"Agent '{agent_name}' failed: {message}",
        "progress":    [{"agent": agent_name, "status": "error", "timestamp": _now()}],
        "audit_log":   audit,
    }


# ── Decorator factory ──────────────────────────────────────────────────────────

def agent_harness(required_inputs: list[str] | None = None):
    """Decorator factory.

    Parameters
    ----------
    required_inputs : list[str]
        State keys that must be present and non-empty before the agent runs.
        Example: ["transcript_texts"] or ["user_stories", "extracted_intents"].
    """
    def decorator(fn: Callable) -> Callable:
        agent_name = fn.__name__.replace("_node", "")

        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            session_id      = state.get("session_id", "unknown")
            existing_errors = state.get("errors", [])
            existing_audit  = state.get("audit_log", [])

            # ── 1. Input validation ────────────────────────────────────────────
            if required_inputs:
                missing = [k for k in required_inputs if not state.get(k)]
                if missing:
                    input_hash  = _hash_inputs(state, required_inputs)
                    prev_hash   = _prev_chain_hash(existing_audit)
                    chain_entry = _build_chain_entry(
                        agent_name, input_hash, output_hash="",
                        prev_hash=prev_hash, elapsed_s=0.0,
                        status="validation_failed",
                        note=f"Missing required inputs: {missing}",
                    )
                    return _error_state(
                        agent_name,
                        f"Missing required state inputs: {missing}",
                        existing_errors,
                        chain_entry=chain_entry,
                    )

            # ── 2. Token budget guard ─────────────────────────────────────────
            if required_inputs:
                total_chars = sum(
                    len(json.dumps(state.get(k, "")))
                    for k in required_inputs
                )
                estimated_tokens = total_chars // _CHARS_PER_TOKEN
                if estimated_tokens > _TOKEN_BUDGET_WARNING:
                    logger.warning(
                        "[%s] session=%s — estimated input size %d tokens "
                        "may approach context-window limits.",
                        agent_name, session_id, estimated_tokens,
                    )

            # Hash inputs NOW, before the agent mutates anything
            input_hash = _hash_inputs(state, required_inputs or [])
            prev_hash  = _prev_chain_hash(existing_audit)

            # ── 3. Run with retry ─────────────────────────────────────────────
            attempt   = 0
            last_exc: Exception | None = None

            while attempt <= _MAX_RETRIES:
                if attempt > 0:
                    logger.warning(
                        "[%s] session=%s — retry attempt %d/%d after error: %s",
                        agent_name, session_id, attempt, _MAX_RETRIES, last_exc,
                    )
                    time.sleep(_RETRY_DELAY_S)

                t0 = time.perf_counter()
                logger.info(
                    "[%s] session=%s — started (attempt %d)",
                    agent_name, session_id, attempt + 1,
                )

                try:
                    result  = fn(state)
                    elapsed = time.perf_counter() - t0
                    logger.info(
                        "[%s] session=%s — completed in %.2fs",
                        agent_name, session_id, elapsed,
                    )

                    # ── Append tamper-evident chain entry ──────────────────────
                    output_hash = _hash_output(result)
                    chain_entry = _build_chain_entry(
                        agent_name, input_hash, output_hash,
                        prev_hash, elapsed, status="ok",
                    )
                    result.setdefault("audit_log", [])
                    result["audit_log"] = result["audit_log"] + [chain_entry]
                    return result

                except NonRetryableError as exc:
                    elapsed     = time.perf_counter() - t0
                    output_hash = ""
                    chain_entry = _build_chain_entry(
                        agent_name, input_hash, output_hash,
                        prev_hash, elapsed, status="error",
                        note=f"NonRetryableError: {exc}",
                    )
                    logger.error(
                        "[%s] session=%s — non-retryable error after %.2fs: %s",
                        agent_name, session_id, elapsed, exc,
                    )
                    return _error_state(agent_name, str(exc), existing_errors, chain_entry=chain_entry)

                except Exception as exc:
                    elapsed  = time.perf_counter() - t0
                    last_exc = exc
                    logger.exception(
                        "[%s] session=%s — exception after %.2fs (attempt %d): %s",
                        agent_name, session_id, elapsed, attempt + 1, exc,
                    )
                    attempt += 1

            # ── 4. All retries exhausted → safe error state ───────────────────
            chain_entry = _build_chain_entry(
                agent_name, input_hash, output_hash="",
                prev_hash=prev_hash, elapsed_s=0.0, status="error",
                note=f"Failed after {_MAX_RETRIES + 1} attempt(s). Last: {last_exc}",
            )
            return _error_state(
                agent_name,
                f"Failed after {_MAX_RETRIES + 1} attempt(s). Last error: {last_exc}",
                existing_errors,
                chain_entry=chain_entry,
            )

        return wrapper
    return decorator


# ── Chain verification utility ─────────────────────────────────────────────────

def verify_audit_chain(audit_log: list[dict]) -> dict:
    """Verify the integrity of an audit_log returned from the pipeline.

    Returns
    -------
    dict with keys:
        valid        : bool   — True if the chain is intact
        entries      : int    — total chain entries found
        broken_at    : int|None — index of first broken link (None if valid)
        error        : str|None — description of what broke
    """
    chain_entries = [e for e in audit_log if e.get("tool") == "harness_chain"]
    if not chain_entries:
        return {"valid": False, "entries": 0, "broken_at": None, "error": "No chain entries found"}

    expected_prev = "genesis"
    for i, entry in enumerate(chain_entries):
        # 1. Check prev_entry_hash continuity
        if entry.get("prev_entry_hash") != expected_prev:
            return {
                "valid": False, "entries": len(chain_entries), "broken_at": i,
                "error": f"Chain broken at entry {i}: prev_entry_hash mismatch "
                         f"(expected {expected_prev!r}, got {entry.get('prev_entry_hash')!r})",
            }

        # 2. Re-compute entry_hash and compare
        stored_hash = entry.get("entry_hash", "")
        entry_body  = {k: v for k, v in entry.items() if k != "entry_hash"}
        computed    = _sha256(json.dumps(entry_body, sort_keys=True))
        if computed != stored_hash:
            return {
                "valid": False, "entries": len(chain_entries), "broken_at": i,
                "error": f"Chain broken at entry {i}: entry_hash mismatch — entry was modified",
            }

        expected_prev = stored_hash

    return {"valid": True, "entries": len(chain_entries), "broken_at": None, "error": None}
