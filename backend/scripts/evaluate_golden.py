"""
Golden dataset regression evaluator for the Backlog Synthesizer pipeline.

Domain: QuantumShield Entertainment (QSE) — media streaming platform.
Dataset: backend/data/qse/

Usage (backend container must be running):
    python scripts/evaluate_golden.py
    python scripts/evaluate_golden.py --base-url http://localhost:8000 --api-key your-key
    python scripts/evaluate_golden.py --verbose        # show per-intent/story detail

What it does:
  1. Creates a fresh session via the API
  2. Uploads the 3 QSE transcripts + wiki + existing tickets
  3. Triggers the pipeline and polls until done (or timeout)
  4. Pulls results and compares against golden_output.json on 4 dimensions:
       a) Intent recall   — how many golden intents were found?
       b) Story coverage  — how many golden stories were approximated?
       c) Conflict recall — how many golden conflicts were flagged?
       d) Eval score gap  — how far are pipeline scores from golden targets?
  5. Prints a structured pass/fail report with per-metric detail
  6. Exits 0 if all checks pass, 1 if any fail
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parents[2]
DATA_DIR    = REPO_ROOT / "backend" / "data" / "qse"
GOLDEN_FILE = DATA_DIR / "golden_output.json"

TRANSCRIPTS = [
    DATA_DIR / "transcripts" / "product_strategy_meeting.txt",
    DATA_DIR / "transcripts" / "user_research_session.txt",
    DATA_DIR / "transcripts" / "engineering_review.txt",
]
WIKI_FILES  = [DATA_DIR / "wiki" / "architecture_constraints.txt"]
TICKETS_FILE = DATA_DIR / "tickets.json"

# ── Thresholds (what counts as a pass) ────────────────────────────────────
INTENT_RECALL_THRESHOLD    = 0.60   # ≥60 % of golden intents found by title match
STORY_COVERAGE_THRESHOLD   = 0.50   # ≥50 % of golden stories approximated
CONFLICT_RECALL_THRESHOLD  = 0.50   # ≥50 % of golden conflicts detected
SCORE_MAX_DELTA            = 1.0    # pipeline score must be within ±1.0 of golden score
POLL_INTERVAL_S            = 5
POLL_TIMEOUT_S             = 900    # 15 min hard cap


# ── Helpers ────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lower-case, remove punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_overlap(a: str, b: str) -> float:
    """Word-overlap Jaccard between two strings."""
    sa = set(_normalise(a).split())
    sb = set(_normalise(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _best_match(needle: str, haystack: list[str], threshold: float = 0.25) -> bool:
    """Return True if needle title overlaps ≥threshold with any haystack title."""
    return any(_title_overlap(needle, h) >= threshold for h in haystack)


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _ok(msg: str) -> None:
    print(f"  ✅  {msg}")


def _fail(msg: str) -> None:
    print(f"  ❌  {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠️   {msg}")


def _info(msg: str) -> None:
    print(f"       {msg}")


# ── API helpers ────────────────────────────────────────────────────────────

def create_session(client: httpx.Client) -> str:
    r = client.post("/sessions")
    r.raise_for_status()
    return r.json()["session_id"]


def upload_transcripts(client: httpx.Client, session_id: str) -> None:
    files = [
        ("files", (p.name, p.read_bytes(), "text/plain"))
        for p in TRANSCRIPTS
    ]
    r = client.post(f"/ingest/transcripts/{session_id}", files=files)
    r.raise_for_status()
    print(f"  Uploaded {len(TRANSCRIPTS)} transcript(s).")


def upload_wiki(client: httpx.Client, session_id: str) -> None:
    files = [
        ("files", (p.name, p.read_bytes(), "text/plain"))
        for p in WIKI_FILES
    ]
    r = client.post(f"/ingest/wiki/{session_id}", files=files)
    r.raise_for_status()
    print(f"  Uploaded {len(WIKI_FILES)} wiki file(s).")


def upload_backlog(client: httpx.Client, session_id: str) -> None:
    r = client.post(
        f"/ingest/backlog/{session_id}",
        files={"file": (TICKETS_FILE.name, TICKETS_FILE.read_bytes(), "application/json")},
    )
    r.raise_for_status()
    tickets = json.loads(TICKETS_FILE.read_bytes())
    print(f"  Uploaded {len(tickets)} existing ticket(s).")


def run_pipeline(client: httpx.Client, session_id: str) -> None:
    r = client.post(f"/pipeline/run/{session_id}", json={})
    r.raise_for_status()
    print("  Pipeline started.")


def poll_until_done(client: httpx.Client, session_id: str) -> dict:
    start = time.time()
    dots  = 0
    while True:
        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT_S:
            raise TimeoutError(f"Pipeline did not complete within {POLL_TIMEOUT_S}s")

        r = client.get(f"/results/{session_id}")
        r.raise_for_status()
        data = r.json()

        status = data.get("status", "pending")
        if data.get("ready"):
            print(f"\n  Done in {elapsed:.0f}s.")
            return data
        if status.startswith("error"):
            raise RuntimeError(f"Pipeline error: {status}")

        dots += 1
        print(f"\r  Waiting{'.' * (dots % 4 + 1)}   {elapsed:.0f}s elapsed", end="", flush=True)
        time.sleep(POLL_INTERVAL_S)


# ── Evaluation dimensions ──────────────────────────────────────────────────

def eval_intents(result: dict, golden: dict, verbose: bool) -> tuple[bool, float]:
    """Dimension 1: Intent recall — did the pipeline find the golden intents?"""
    _section("1 / 4  Intent Recall")

    golden_titles  = [i["title"] for i in golden["expected_intents"]]
    pipeline_titles = [i.get("title", "") for i in result.get("extracted_intents", [])]

    found   = [g for g in golden_titles if _best_match(g, pipeline_titles)]
    missed  = [g for g in golden_titles if g not in found]
    recall  = len(found) / len(golden_titles) if golden_titles else 0.0

    print(f"  Golden intents : {len(golden_titles)}")
    print(f"  Pipeline found : {len(pipeline_titles)}")
    print(f"  Matched        : {len(found)} / {len(golden_titles)}  ({recall:.0%})")
    print(f"  Threshold      : {INTENT_RECALL_THRESHOLD:.0%}")

    if verbose:
        if found:
            print("  Matched:")
            for t in found:
                _info(f"✓ {t}")
        if missed:
            print("  Missed:")
            for t in missed:
                _info(f"✗ {t}")

    passed = recall >= INTENT_RECALL_THRESHOLD
    if passed:
        _ok(f"PASS  — recall {recall:.0%} ≥ {INTENT_RECALL_THRESHOLD:.0%}")
    else:
        _fail(f"FAIL  — recall {recall:.0%} < {INTENT_RECALL_THRESHOLD:.0%}")
    return passed, recall


def eval_stories(result: dict, golden: dict, verbose: bool) -> tuple[bool, float]:
    """Dimension 2: Story coverage — did the pipeline generate the expected stories?"""
    _section("2 / 4  Story Coverage")

    golden_titles   = [s["title"] for s in golden["expected_stories"]]
    pipeline_titles = [s.get("title", "") for s in result.get("user_stories", [])]

    found    = [g for g in golden_titles if _best_match(g, pipeline_titles, threshold=0.20)]
    missed   = [g for g in golden_titles if g not in found]
    coverage = len(found) / len(golden_titles) if golden_titles else 0.0

    print(f"  Golden stories  : {len(golden_titles)}")
    print(f"  Pipeline stories: {len(pipeline_titles)}")
    print(f"  Matched         : {len(found)} / {len(golden_titles)}  ({coverage:.0%})")
    print(f"  Threshold       : {STORY_COVERAGE_THRESHOLD:.0%}")

    if verbose:
        if found:
            print("  Matched:")
            for t in found:
                _info(f"✓ {t}")
        if missed:
            print("  Missed:")
            for t in missed:
                _info(f"✗ {t}")

    passed = coverage >= STORY_COVERAGE_THRESHOLD
    if passed:
        _ok(f"PASS  — coverage {coverage:.0%} ≥ {STORY_COVERAGE_THRESHOLD:.0%}")
    else:
        _fail(f"FAIL  — coverage {coverage:.0%} < {STORY_COVERAGE_THRESHOLD:.0%}")
    return passed, coverage


def eval_conflicts(result: dict, golden: dict, verbose: bool) -> tuple[bool, float]:
    """Dimension 3: Conflict recall — did the pipeline flag the golden conflicts?"""
    _section("3 / 4  Conflict Detection Recall")

    golden_conflicts   = golden["expected_gap_report"]["conflicts"]
    pipeline_conflicts = result.get("gap_report", {}).get("conflicts", [])

    golden_descs   = [c["description"] for c in golden_conflicts]
    pipeline_descs = [c.get("description", "") + " " + c.get("new_request", "")
                      for c in pipeline_conflicts]

    found  = [g for g in golden_descs if _best_match(g, pipeline_descs, threshold=0.12)]
    missed = [g for g in golden_descs if g not in found]
    recall = len(found) / len(golden_descs) if golden_descs else 0.0

    print(f"  Golden conflicts  : {len(golden_descs)}")
    print(f"  Pipeline conflicts: {len(pipeline_conflicts)}")
    print(f"  Matched           : {len(found)} / {len(golden_descs)}  ({recall:.0%})")
    print(f"  Threshold         : {CONFLICT_RECALL_THRESHOLD:.0%}")

    if verbose:
        if found:
            print("  Matched:")
            for d in found:
                _info(f"✓ {d[:80]}…")
        if missed:
            print("  Missed:")
            for d in missed:
                _info(f"✗ {d[:80]}…")

    passed = recall >= CONFLICT_RECALL_THRESHOLD
    if passed:
        _ok(f"PASS  — recall {recall:.0%} ≥ {CONFLICT_RECALL_THRESHOLD:.0%}")
    else:
        _fail(f"FAIL  — recall {recall:.0%} < {CONFLICT_RECALL_THRESHOLD:.0%}")
    return passed, recall


def eval_scores(result: dict, golden: dict, verbose: bool) -> tuple[bool, dict]:
    """Dimension 4: Evaluation score proximity — pipeline scores vs golden targets."""
    _section("4 / 4  Evaluation Score Gap")

    golden_scores   = golden["expected_evaluation"]
    pipeline_scores = result.get("evaluation_scores", {})

    metrics = [
        ("overall_score",         "Overall",            5.0),
        ("clarity_score",         "Clarity",            5.0),
        ("feasibility_score",     "Feasibility",        5.0),
        ("traceability_score",    "Traceability",       5.0),
        ("ac_completeness_pct",   "AC Completeness %", 100.0),
        ("feature_tag_f1",        "Feature Tag F1",     1.0),
        ("conflict_detection_f1", "Conflict Detect F1", 1.0),
    ]

    print(f"  {'Metric':<24} {'Golden':>8} {'Pipeline':>10} {'Delta':>8} {'Status':>8}")
    print(f"  {'─'*24} {'─'*8} {'─'*10} {'─'*8} {'─'*8}")

    results_detail = {}
    all_pass = True
    for key, label, _scale in metrics:
        g = float(golden_scores.get(key, 0))
        p = float(pipeline_scores.get(key, 0))
        delta = abs(p - g)
        ok = delta <= SCORE_MAX_DELTA
        if not ok:
            all_pass = False
        status_icon = "✅" if ok else "❌"
        print(f"  {label:<24} {g:>8.2f} {p:>10.2f} {delta:>+8.2f} {status_icon:>8}")
        results_detail[key] = {"golden": g, "pipeline": p, "delta": delta, "pass": ok}

    print(f"\n  Max allowed delta: ±{SCORE_MAX_DELTA}")
    if all_pass:
        _ok("PASS  — all scores within tolerance")
    else:
        _fail("FAIL  — one or more scores outside tolerance")
    return all_pass, results_detail


# ── Report ─────────────────────────────────────────────────────────────────

def print_summary(
    session_id: str,
    checks: list[tuple[str, bool, str]],
    result: dict,
) -> bool:
    _section("SUMMARY")
    print(f"  Session : {session_id}")
    print(f"  Retries : {result.get('retry_count', 0)}")
    print(f"  Halt    : {result.get('halt_reason') or '—'}")
    print()

    overall_pass = True
    for name, passed, detail in checks:
        if passed:
            _ok(f"{name:<32} {detail}")
        else:
            _fail(f"{name:<32} {detail}")
            overall_pass = False

    print()
    if overall_pass:
        print("  ✅  ALL CHECKS PASSED — pipeline meets golden dataset benchmarks.")
    else:
        print("  ❌  ONE OR MORE CHECKS FAILED — see details above.")
    print()
    return overall_pass


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate pipeline against QSE golden dataset")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--api-key",  default="",                      help="X-Api-Key header value (if required)")
    parser.add_argument("--verbose",  action="store_true",              help="Show per-intent/story/conflict detail")
    parser.add_argument("--skip-run", metavar="SESSION_ID",            help="Skip upload+run, evaluate an existing session")
    args = parser.parse_args()

    # Validate data files exist
    for p in [GOLDEN_FILE, TICKETS_FILE, *TRANSCRIPTS, *WIKI_FILES]:
        if not p.exists():
            print(f"ERROR: Required file not found: {p}")
            return 1

    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))

    headers = {}
    if args.api_key:
        headers["X-Api-Key"] = args.api_key

    print("\n" + "═" * 60)
    print("  Backlog Synthesizer — Golden Dataset Evaluator")
    print("  Domain: QuantumShield Entertainment (media streaming)")
    print("═" * 60)

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60) as client:

        if args.skip_run:
            session_id = args.skip_run
            print(f"\n  Using existing session: {session_id}")
        else:
            # Step 1: Session + ingest + run
            print("\n[ Setup ]")
            session_id = create_session(client)
            print(f"  Session created: {session_id}")
            upload_transcripts(client, session_id)
            upload_wiki(client, session_id)
            upload_backlog(client, session_id)
            run_pipeline(client, session_id)

        # Step 2: Poll
        print("\n[ Pipeline ]")
        try:
            result = poll_until_done(client, session_id)
        except (TimeoutError, RuntimeError) as exc:
            print(f"\n  ERROR: {exc}")
            return 1

    # Step 3: Evaluate all 4 dimensions
    p1, recall_intents   = eval_intents(result, golden, args.verbose)
    p2, coverage_stories = eval_stories(result, golden, args.verbose)
    p3, recall_conflicts = eval_conflicts(result, golden, args.verbose)
    p4, score_detail     = eval_scores(result, golden, args.verbose)

    # Step 4: Summary
    checks = [
        ("Intent Recall",      p1, f"{recall_intents:.0%}"),
        ("Story Coverage",     p2, f"{coverage_stories:.0%}"),
        ("Conflict Recall",    p3, f"{recall_conflicts:.0%}"),
        ("Eval Score Gap",     p4, "all within ±1.0" if p4 else "one or more exceeded ±1.0"),
    ]
    overall = print_summary(session_id, checks, result)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
