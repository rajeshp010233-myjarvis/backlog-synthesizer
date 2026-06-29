"""Tests for the agent harness — audit chain, retry, and validation logic."""
import pytest
from app.agents.harness import agent_harness, verify_audit_chain


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_agent(required=None, fail_times=0, raise_non_retryable=False):
    """Build a decorated agent function for testing."""
    call_count = {"n": 0}

    @agent_harness(required_inputs=required)
    def my_agent_node(state: dict) -> dict:
        call_count["n"] += 1
        if raise_non_retryable:
            from app.exceptions import NonRetryableError
            raise NonRetryableError("Fatal")
        if call_count["n"] <= fail_times:
            raise RuntimeError("Transient error")
        return {
            "user_stories": ["story-1"],
            "audit_log": [],
            "progress": [{"agent": "my_agent", "status": "done", "timestamp": "t"}],
        }

    return my_agent_node, call_count


# ── Input validation ───────────────────────────────────────────────────────────

def test_missing_required_input_returns_error_state():
    agent, _ = _make_agent(required=["transcript_texts"])
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    assert result["halt_reason"] != ""
    assert "transcript_texts" in result["halt_reason"] or "Missing" in result["halt_reason"]


def test_present_required_input_runs_agent():
    agent, calls = _make_agent(required=["transcript_texts"])
    result = agent({
        "session_id": "s1",
        "transcript_texts": ["some text"],
        "errors": [],
        "audit_log": [],
    })
    assert calls["n"] == 1
    assert "user_stories" in result


# ── Retry logic ────────────────────────────────────────────────────────────────

def test_agent_retried_once_on_transient_failure():
    agent, calls = _make_agent(fail_times=1)
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    assert calls["n"] == 2
    assert "user_stories" in result


def test_agent_fails_after_max_retries():
    agent, calls = _make_agent(fail_times=99)
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    assert result["halt_reason"] != ""
    assert len(result["errors"]) > 0


def test_non_retryable_error_not_retried():
    agent, calls = _make_agent(raise_non_retryable=True)
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    assert calls["n"] == 1
    assert result["halt_reason"] != ""


# ── Audit chain ────────────────────────────────────────────────────────────────

def test_successful_run_appends_chain_entry():
    agent, _ = _make_agent()
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    chain = [e for e in result["audit_log"] if e.get("tool") == "harness_chain"]
    assert len(chain) == 1
    assert chain[0]["status"] == "ok"


def test_chain_entry_contains_elapsed_s():
    agent, _ = _make_agent()
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    chain = [e for e in result["audit_log"] if e.get("tool") == "harness_chain"]
    assert "elapsed_s" in chain[0]
    assert chain[0]["elapsed_s"] >= 0


def test_verify_audit_chain_valid():
    state = {"session_id": "s1", "errors": [], "audit_log": []}
    agent, _ = _make_agent()
    r1 = agent(state)
    state2 = {**state, "audit_log": r1["audit_log"]}
    agent2, _ = _make_agent()
    r2 = agent2(state2)

    full_log = r1["audit_log"] + r2["audit_log"]
    verdict = verify_audit_chain(full_log)
    assert verdict["valid"] is True
    assert verdict["entries"] == 2


def test_verify_audit_chain_detects_tampering():
    agent, _ = _make_agent()
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    log = result["audit_log"]
    chain = [e for e in log if e.get("tool") == "harness_chain"]
    chain[0]["input_hash"] = "tampered"

    verdict = verify_audit_chain(log)
    assert verdict["valid"] is False


def test_done_progress_event_tagged_with_elapsed_s():
    agent, _ = _make_agent()
    result = agent({"session_id": "s1", "errors": [], "audit_log": []})
    done_events = [p for p in result.get("progress", []) if p.get("status") == "done"]
    assert all("elapsed_s" in e for e in done_events)
