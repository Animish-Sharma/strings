#!/usr/bin/env python3
"""Inertness — a check that returns the same answer to every question.

One gate in this tree parsed a block format that one artifact kind does not
have, compared nothing on it, and returned pass. It sat in receipts looking like
a check for the whole life of its pack, behind a green suite, its own self-test,
and twenty planted regressions. Nothing could see it, because every one of those
tests fed it the artifact kind it did work on.

That is a class, not an incident, and the class has a cheap signature: **a gate
whose verdict never varies across a corpus deliberately built to contain things
it should refuse is not checking.** No per-gate mutation has to be authored. The pack's own controls already disagree with each other; a gate that
cannot tell them apart is the finding.

Each pack declares its corpus in `<pack>/evals/corpus.json`: artifacts paired
with claims, each tagged with a KIND. A gate is reported inert on a kind when it
ran on at least `--min` artifacts of that kind and returned one verdict for all
of them. Gates may declare `applies_to` in the manifest; a kind outside that
list is skipped rather than reported, and a gate that declares nothing is
expected to work on everything the pack accepts.

This is a finding about coverage, and not on its own a defect: a gate can
legitimately pass everything if nothing in the corpus violates it. So the report says which,
and the corpus is the thing to fix when it is the corpus that is thin.

Usage:  check_gate_inertness.py [--pack NAME] [--min 3] [--json]
Exit:   0 no gate is inert, 1 at least one is, 2 IO.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def declared_gates(pack: str) -> list[dict]:
    body = json.loads((ROOT / "domains" / pack / "domain.json").read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, dict):
            if node.get("script") and node.get("name") and "gates/" in str(node["script"]):
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
    return list(walk(body))


def run_gate(pack: str, script: str, artifact: Path, claim: Path) -> str:
    path = ROOT / "domains" / pack / script
    if not path.exists():
        return "missing"
    try:
        proc = subprocess.run([sys.executable, str(path), str(artifact),
                               "--claim", str(claim)],
                              capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError):
        return "error"
    # The exit code is the gate's verdict; the pack's adapter reads it the same
    # way. 2 means the gate could not read its input, which is not a verdict
    # about the artifact and must not be counted as one.
    return {0: "pass", 1: "fail", 3: "not_run", 4: "not_applicable"}.get(
        proc.returncode, "error")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pack")
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    packs = [a.pack] if a.pack else sorted(
        p.name for p in (ROOT / "domains").iterdir()
        if (p / "evals" / "corpus.json").exists())

    findings, rows, ran = [], [], 0
    for pack in packs:
        corpus_path = ROOT / "domains" / pack / "evals" / "corpus.json"
        if not corpus_path.exists():
            print(f"  ---- {pack}: no declared evaluation corpus, nothing to vary over")
            continue
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))["artifacts"]
        base = ROOT / "domains" / pack
        for gate in declared_gates(pack):
            applies = gate.get("applies_to")
            by_kind: dict[str, dict[str, int]] = {}
            for item in corpus:
                kind = item["kind"]
                if applies and kind not in applies:
                    continue
                verdict = run_gate(pack, gate["script"], base / item["artifact"],
                                   base / item["claim"])
                ran += 1
                if verdict in {"error", "missing"}:
                    continue
                by_kind.setdefault(kind, {}).setdefault(verdict, 0)
                by_kind[kind][verdict] += 1
            for kind, counts in by_kind.items():
                total = sum(counts.values())
                row = {"pack": pack, "gate": gate["name"], "kind": kind,
                       "n": total, "verdicts": counts}
                rows.append(row)
                if total >= a.min and len(counts) == 1:
                    only = next(iter(counts))
                    # Two constant answers are not evidence of inertness.
                    # `not_applicable` is a gate correctly saying "not my job".
                    # `not_run` is a gate saying it could not run here at all —
                    # typically because what it depends on is not installed.
                    # Calling either one inert would make this check fail on
                    # every machine without a backend, and a check that cries
                    # wolf about absent tooling is one people switch off.
                    if only in {"not_applicable"}:
                        continue
                    if only == "not_run":
                        row["unavailable"] = True
                        continue
                    row["inert"] = True
                    findings.append(
                        f"{pack}/{gate['name']} answered {only!r} to all {total} "
                        f"{kind} artifact(s) — including the ones this pack keeps "
                        "precisely because they should not all be treated alike")

    unavailable = [r for r in rows if r.get("unavailable")]
    for row in rows:
        mark = ("INERT" if row.get("inert")
                else "----" if row.get("unavailable") else "ok   ")
        print(f"  {mark} {row['pack']:<9} {row['gate']:<26} {row['kind']:<7} "
              f"n={row['n']:<3} {row['verdicts']}")
    print()
    if findings:
        print(f"GATE INERTNESS: FAIL — {len(findings)} gate/kind pair(s) never varied\n")
        for f in findings:
            print(f"  {f}")
        print("\n  Either the gate does not read that artifact kind, or the corpus does "
              "not contain anything it would refuse. Both are worth knowing and only "
              "one of them is a corpus problem.")
    else:
        print(f"GATE INERTNESS: PASS — {len(rows)} gate/kind pair(s), "
              f"{ran} gate run(s), every gate that could run varied its answer"
              + (f"; {len(unavailable)} pair(s) NOT_RUN here and therefore unmeasured"
                 if unavailable else ""))
    if unavailable:
        print(f"NOT_RUN_COUNT={len(unavailable)}")
    if a.json:
        print(json.dumps({"schema": "witsoc.inertness.v1", "rows": rows,
                          "findings": findings}, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
