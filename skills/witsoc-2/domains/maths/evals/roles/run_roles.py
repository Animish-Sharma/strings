#!/usr/bin/env python3
"""Role evals — score the DECISION, not the artifact.

The blueprint evals score production and `scripts/negative_control/` scores the
adapter. Neither can tell you whether the Explorer read a bounded result
correctly, whether the Generator caught an under-declared citation, or whether
the Researcher picked the rung that was actually reachable. Those are the
judgements the doctrine is about, and until this existed nothing in the pack
could detect one of them regressing.

A role eval is writable exactly where the judgement has machinery under it. That
constraint is the useful part: to score a decision you must first make it
mechanical, so the absence of a case is itself a finding about which decisions
are still made by eye.

Usage:  run_roles.py [--role explorer|generator|researcher] [--json]
Exit:   0 all pass, 1 failures, 2 IO
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
CONTROLS = PACK / "scripts" / "negative_control"
sys.path.insert(0, str(PACK / "scripts"))
sys.path.insert(0, str(PACK / "scripts" / "gates"))

from premise_audit import top_level_arrows  # noqa: E402

# bounded.py exit codes are the decision: 0 exhaustive pass, 1 refuted,
# 2 error, 3 budget stop. Reading them is the Explorer judgement being scored.
BOUNDED_VERDICT = {0: "pass", 1: "fail", 2: "error", 3: "unknown"}


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def run_explorer(cases: list[dict], tmp: Path) -> list[dict]:
    out = []
    for case in cases:
        if "expect_first_lane" in case:
            state = tmp / f"{case['id']}_state.json"
            state.write_text(json.dumps(case["state"]), encoding="utf-8")
            code, text = run([sys.executable, str(PACK / "scripts" / "lanes.py"), "rank",
                              "--state", str(state), "--json"])
            try:
                payload = json.loads(text)
                ranked = payload.get("ranked_lanes") or payload
                first = (ranked[0].get("name") or ranked[0].get("lane")
                         if isinstance(ranked, list) and ranked else None)
            except (json.JSONDecodeError, AttributeError, IndexError):
                first = None
            out.append({"role": "explorer", "id": case["id"],
                        "want": case["expect_first_lane"], "got": first,
                        "ok": first == case["expect_first_lane"], "why": case["why"]})
            continue

        if case.get("claim"):
            claim_path = CONTROLS / case["claim"]
        else:
            claim_path = tmp / f"{case['id']}.json"
            claim_path.write_text(json.dumps({
                "claim_id": case["id"], "exact_statement": case["id"],
                "frozen_conditions": {"bounded_search": case["inline"]},
                "target_sha256": "0" * 64, "status": "CONJECTURE"}), encoding="utf-8")
        code, _ = run([sys.executable, str(PACK / "scripts" / "tiers" / "bounded.py"),
                       "--claim", str(claim_path), "--json"])
        got = BOUNDED_VERDICT.get(code, f"exit {code}")
        out.append({"role": "explorer", "id": case["id"], "want": case["expect"], "got": got,
                    "ok": got == case["expect"], "why": case["why"]})
    return out


def run_generator(cases: list[dict], tmp: Path) -> list[dict]:
    """The under-declaration check, exercised directly on the hypothesis floor.

    The gate's job is to notice that a cited result carries more hypotheses than
    the claim admits. That comparison is `top_level_arrows(library type)` against
    the declared count, so the eval scores exactly that and does not rebuild a
    WIT artifact to reach it.
    """
    out = []
    for case in cases:
        arrows = top_level_arrows(case["corpus_type"])
        flagged = arrows > case["declared_preconditions"]
        got = "fail" if flagged else "pass"
        out.append({"role": "generator", "id": case["id"], "want": case["expect"], "got": got,
                    "ok": got == case["expect"], "why": case["why"],
                    "detail": f"library type shows {arrows} hypothesis(es), "
                              f"claim declares {case['declared_preconditions']}"})
    return out


def run_researcher(cases: list[dict], tmp: Path) -> list[dict]:
    out = []
    for case in cases:
        if "expect_top" in case:
            path = tmp / f"{case['id']}.json"
            path.write_text(json.dumps({"rungs": case["rungs"]}), encoding="utf-8")
            code, text = run([sys.executable, str(PACK / "scripts" / "rungs.py"), "score",
                              "--rungs", str(path), "--json"])
            try:
                ranked = json.loads(text)["rungs"]
                top = ranked[0]["name"] if ranked else None
            except (json.JSONDecodeError, KeyError, IndexError):
                top = None
            out.append({"role": "researcher", "id": case["id"], "want": case["expect_top"],
                        "got": top, "ok": top == case["expect_top"], "why": case["why"]})
            continue

        target = tmp / f"{case['id']}_target.json"
        target.write_text(json.dumps({"claim_id": case["id"], "exact_statement": "x",
                                      "allowed_external_facts": []}), encoding="utf-8")
        code, text = run([sys.executable, str(PACK / "scripts" / "attackability.py"),
                          "--target", str(target), "--json"])
        try:
            notes = json.loads(text).get("raise_it_by") or []
        except json.JSONDecodeError:
            notes = []
        out.append({"role": "researcher", "id": case["id"], "want": "raise_it_by notes",
                    "got": f"{len(notes)} note(s)", "ok": bool(notes) == case["expect_raise_notes"],
                    "why": case["why"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--role", choices=["explorer", "generator", "researcher"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        spec = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="mathsroles_"))
    results: list[dict] = []
    if args.role in (None, "explorer"):
        results += run_explorer(spec["explorer"], tmp)
    if args.role in (None, "generator"):
        results += run_generator(spec["generator"], tmp)
    if args.role in (None, "researcher"):
        results += run_researcher(spec["researcher"], tmp)

    failures = [r for r in results if not r["ok"]]
    if args.json:
        print(json.dumps({"results": results, "failures": len(failures)}, indent=2))
        return 1 if failures else 0

    current = None
    print("\n  ROLE EVALS — the decision, not the artifact\n")
    for entry in results:
        if entry["role"] != current:
            current = entry["role"]
            print(f"  {current.upper()}")
        print(f"    {'ok  ' if entry['ok'] else 'FAIL'}  {entry['id']:<36} "
              f"want {str(entry['want']):<18} got {entry['got']}")
        print(f"            {entry['why'][:112]}")
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(results) - len(failures)}"
          f"/{len(results)} decisions correct")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
