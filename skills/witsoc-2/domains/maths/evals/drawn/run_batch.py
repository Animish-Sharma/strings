#!/usr/bin/env python3
"""Batch over drawn targets — a pass rate on material nobody picked.

Two fixtures and a README said the loop closes on a target the pipeline did not
choose. Two is an anecdote. This runs the automatic path over a drawn batch and
reports the funnel, because a single percentage hides the thing worth knowing:

    drawn                 sampled from the library, unfiltered for difficulty
    elaborated            the statement type-checked once its context was replayed
    closed                some tactic in the portfolio discharged it
    independent           ...and the proof term does not cite the target itself

**The last row is the only one that means anything.** The portfolio contains
`exact?`, whose job is to find a library result of the goal's type, and every
target here IS a library result of that type. Without the circularity audit the
closure rate measures Mathlib's completeness. With it, `closed` minus
`independent` is a direct count of how often the search's answer was the answer
key — a number worth printing rather than suppressing.

Targets are forbidden by name and by TYPE: the corpus is consulted for every
declaration whose type matches the target's, so an alias under a different name
counts as a citation. That check needs an index; without one only the name is
forbidden, and the run says so.

Usage:
    run_batch.py --targets batch40.json [--workers 3] [--timeout 300]
                 [--corpus corpus.json] [--out results.json] [--limit N]

Exit: 0 the batch ran, 2 usage/IO, 3 no toolchain.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "gates"))

from tactic_search import (CANDIDATE_PREFIX, DEFAULT_PORTFOLIO,  # noqa: E402
                           build_file, run_search)
from circularity_audit import audit                            # noqa: E402

# Diagnostics that mean the STATEMENT never elaborated, so no tactic was ever
# tried. Scoring these as "the portfolio failed to close it" would blame the
# search for a context the runner failed to rebuild.
CONTEXT_ERRORS = ("unknown identifier", "unknown constant", "Function expected",
                  "invalid binder annotation", "failed to synthesize",
                  "unexpected token", "expected term")


def module_of(rel_file: str) -> str:
    return "Mathlib." + rel_file[:-len(".lean")].replace("/", ".")


def preamble_for(target: dict) -> list[str]:
    """The target's scope, replayed in the order the file declares it."""
    return list(target["scope_open"])


def classify(target: dict, search: dict) -> tuple[str, str]:
    if search["verdict"] == "unavailable":
        return "NOT_RUN", search.get("reading", "")
    if search["verdict"] == "timeout":
        return "TIMEOUT", f"no candidate finished inside {search.get('budget_seconds')}s"
    if search["verdict"] == "error":
        return "ERROR", search.get("reading", "")
    if search["verdict"] == "closed":
        return "CLOSED", ""
    blob = " ".join(d for r in search.get("results", []) for d in r["diagnostics"])
    if any(e in blob for e in CONTEXT_ERRORS):
        return "CONTEXT_FAILED", next(
            (d for r in search["results"] for d in r["diagnostics"]
             if any(e in d for e in CONTEXT_ERRORS)), "")[:200]
    return "NOT_CLOSED", "the portfolio ran and nothing discharged the goal"


def audit_file(target: dict, tactic: str) -> tuple[str, str]:
    """One candidate, alone, built by the same builder the search used.

    Auditing the search's twelve-candidate file looked cheaper and was wrong:
    the candidates are named theorems of the same statement, so `exact?` closed
    the goal by citing candidate 0 and the audit saw no forbidden name. Alone in
    a file there is nothing to cite but the library.
    """
    imports = list(target["imports"]) + [f"public import {module_of(target['file'])}"]
    source, _ = build_file(target["statement"], target["binders"], [tactic], imports,
                           preamble_for(target), target["scope_close"])
    decl = ".".join(target["namespaces"] + [f"{CANDIDATE_PREFIX}0"])
    return source, decl


def one(target: dict, forbid_index: dict[str, set[str]], timeout: int,
        project: str) -> dict:
    started = time.time()
    imports = list(target["imports"]) + [f"public import {module_of(target['file'])}"]
    search = run_search(target["statement"], target["binders"], DEFAULT_PORTFOLIO,
                        imports, timeout, preamble_for(target), target["scope_close"])
    outcome, note = classify(target, search)
    row = {"name": target["name"], "file": target["file"], "outcome": outcome,
           "note": note, "closed_by": search.get("closed_by", []),
           "seconds": round(time.time() - started, 1)}

    if outcome != "CLOSED":
        return row

    forbid = {target["name"]} | forbid_index.get(target["name"], set())
    row["forbidden_count"] = len(forbid)
    citing = []
    for tactic in search["closed_by"]:
        source, decl = audit_file(target, tactic)
        with tempfile.TemporaryDirectory(prefix="drawn_") as td:
            f = Path(td) / "Search.lean"
            f.write_text(source, encoding="utf-8")
            verdict = audit(f, decl, forbid, project, timeout)
        if verdict["verdict"] == "PASS":
            row["outcome"] = "INDEPENDENT"
            row["proved_by"] = tactic
            row["cited_by_others"] = citing
            return row
        citing.append({"tactic": tactic, "verdict": verdict["verdict"],
                       "cites": verdict.get("cites", [])})
    if any(c["verdict"] == "FAIL" for c in citing):
        row["outcome"] = "CITED_TARGET"
    elif all(c["verdict"] == "NOT_PROVED" for c in citing):
        # The portfolio scored these closed and the term is a `sorry`. That is a
        # disagreement between the two readings of the same file, and it is the
        # search that is wrong, not the audit.
        row["outcome"] = "CLOSURE_UNCONFIRMED"
    else:
        row["outcome"] = "AUDIT_INCONCLUSIVE"
    row["audits"] = citing
    return row


def build_forbid_index(corpus_path: str | None, targets: list[dict]) -> dict[str, set[str]]:
    """Names that prove literally the same statement as a target.

    Closing `foo` by citing `foo'` is the same evasion as citing `foo`, and the
    corpus is the only thing that knows the two have one type.
    """
    if not corpus_path or not Path(corpus_path).exists():
        return {}
    data = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    by_name = {}
    by_type: dict[str, list[str]] = {}
    for d in data.get("declarations", []):
        t = d.get("type")
        by_name[d["name"]] = t
        if t:
            by_type.setdefault(t, []).append(d["name"])
    index = {}
    for tgt in targets:
        t = by_name.get(tgt["name"])
        if t:
            index[tgt["name"]] = {n for n in by_type.get(t, []) if n != tgt["name"]}
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--targets", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--corpus", default=os.environ.get("WITSOC2_MATHS_CORPUS"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out")
    a = ap.parse_args()

    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    if not project or not Path(project).is_dir():
        print("ERROR: WITSOC2_LEAN_PROJECT must point at a Lean project", file=sys.stderr)
        return 3
    try:
        body = json.loads(Path(a.targets).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    targets = body["targets"][: a.limit] if a.limit else body["targets"]

    index = build_forbid_index(a.corpus, targets)
    print(f"[batch] {len(targets)} targets, {a.workers} workers, {a.timeout}s each; "
          f"type-aliases known for {len(index)} of them"
          f"{'' if index else ' (no corpus — name-only forbidding)'}", file=sys.stderr)

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for row in pool.map(lambda t: one(t, index, a.timeout, project), targets):
            rows.append(row)
            print(f"  {row['outcome']:<18} {row['seconds']:>6.1f}s  {row['name']}",
                  file=sys.stderr, flush=True)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    # ERROR is a file that did not elaborate, so it belongs on the same side of
    # the funnel as CONTEXT_FAILED. Counting it as elaborated inflated the
    # denominator and made the closure rate look worse than the run showed.
    not_elaborated = sum(counts.get(k, 0) for k in
                         ("CONTEXT_FAILED", "NOT_RUN", "ERROR", "TIMEOUT"))
    elaborated = len(rows) - not_elaborated
    closed = (counts.get("INDEPENDENT", 0) + counts.get("CITED_TARGET", 0)
              + counts.get("AUDIT_INCONCLUSIVE", 0) + counts.get("CLOSURE_UNCONFIRMED", 0))
    report = {"schema": "maths.drawn_batch.v1", "seed": body.get("seed"),
              "pool_size": body.get("pool_size"), "drawn": len(rows),
              "elaborated": elaborated, "not_elaborated": not_elaborated,
              "closed": closed,
              "independent": counts.get("INDEPENDENT", 0),
              "cited_target": counts.get("CITED_TARGET", 0),
              "outcomes": counts, "rows": rows}
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
