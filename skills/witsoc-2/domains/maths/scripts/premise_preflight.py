#!/usr/bin/env python3
"""Premise pre-flight — do the results this plan cites actually exist?

The kernel tier costs about five seconds per run, essentially all of it import
elaboration (`doctrine/kernel_economics.md`). A blueprint citing a lemma that
does not exist spends that, fails with `unknown_identifier`, and returns a
diagnostic that says precisely what a lookup would have said for free.

So this runs first. Three verdicts per citation, from the corpus:

    KNOWN          resolved: name, type, module
    SEARCH_TARGET  plausible and unresolved — a lead, never a premise
    ABSENT         not in the corpus; establishing it is a sub-claim, not a step

**ABSENT is not a refusal.** A corpus is a snapshot of one library, and a
citation it cannot resolve may be a real result the snapshot does not carry —
which is why this reports rather than blocks, and why the report distinguishes
"I could not find it" from "it is not there". A pre-flight that refuses what it
cannot resolve teaches people to stop citing things it does not know, which is
the opposite of what a premise ledger is for.

What it does refuse: a citation the blueprint's own `external_dependencies`
never declared. That is not a corpus question.

Usage:
    premise_preflight.py --blueprint <bp.json> [--corpus <index>] [--json]

Exit: 0 every citation resolved · 1 something is unresolved or undeclared
      · 2 usage/IO · 3 no corpus available to check against
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--corpus")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        blueprint = json.loads(Path(args.blueprint).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    declared = [d.get("theorem_name") for d in blueprint.get("external_dependencies", [])
                if isinstance(d, dict) and d.get("theorem_name")]
    cited: dict[str, list[str]] = {}
    for step in blueprint.get("lemma_plan", []) or []:
        for name in step.get("cites", []) or []:
            cited.setdefault(name, []).append(str(step.get("step_id")))

    problems = []
    undeclared = sorted(set(cited) - set(declared))
    for name in undeclared:
        problems.append(
            f"step(s) {cited[name]} cite {name!r}, which external_dependencies never declared. "
            "Out of scope is not a step, and this one is not a corpus question")

    unused = sorted(set(declared) - set(cited))

    # Ask the corpus about everything declared, whether or not a step cites it —
    # a dependency listed and never used is still a claim about what exists.
    verdicts: dict[str, dict] = {}
    corpus_available = True
    if declared:
        cmd = [sys.executable, str(HERE / "corpus.py"), "query", *declared, "--json"]
        if args.corpus:
            cmd += ["--corpus", args.corpus]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            corpus_available = False
            payload = {}
        for entry in (payload.get("results") or payload.get("queries") or []):
            if isinstance(entry, dict):
                key = entry.get("query") or entry.get("name")
                if key:
                    verdicts[key] = entry

    if not corpus_available:
        print(json.dumps({
            "verdict": "not_run",
            "declared": declared, "undeclared_citations": undeclared,
            "note": ("no corpus was available, so nothing could be resolved. This is a gap and "
                     "not a pass: the expensive tier will now be the first thing to discover a "
                     "missing premise, which is what this check exists to avoid"),
            "problems": problems,
        }, indent=2))
        return 3 if not problems else 1

    unresolved = [name for name in declared
                  if str(verdicts.get(name, {}).get("verdict", "ABSENT")).upper() != "KNOWN"]

    result = {
        "verdict": "fail" if problems else ("warn" if unresolved else "pass"),
        "declared": len(declared),
        "cited_by_steps": {k: v for k, v in cited.items()},
        "undeclared_citations": undeclared,
        "declared_but_never_cited": unused,
        "unresolved": [{"name": n,
                        "corpus_verdict": verdicts.get(n, {}).get("verdict", "ABSENT"),
                        "meaning": ("a lead, not a premise — establish it or stop citing it"
                                    if str(verdicts.get(n, {}).get("verdict")) == "SEARCH_TARGET"
                                    else "not in this corpus. It may still exist; the corpus is "
                                         "a snapshot of one library, so this is a report and not "
                                         "a verdict on the mathematics")}
                       for n in unresolved],
        "problems": problems,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"PREMISE PRE-FLIGHT: {result['verdict'].upper()} — "
              f"{result['declared']} declared, {len(unresolved)} unresolved")
        for item in result["unresolved"]:
            print(f"  {item['corpus_verdict']:<14} {item['name']}")
            print(f"                 {item['meaning']}")
        for problem in problems:
            print(f"  PROBLEM: {problem}")
        if unused:
            print(f"  declared and never cited: {unused}")
        if result["verdict"] == "pass":
            print("  every cited result resolves. The expensive tier will not be the thing "
                  "that discovers a missing premise")
    return 1 if problems or unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
