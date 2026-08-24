#!/usr/bin/env python3
"""Tactic search — close an authorized leaf by search, with the kernel as judge.

The pack could render a plan, formalize it, and check it, and it had no way to
CLOSE anything. Every obligation's tactic had to be supplied by whoever called
`wit_to_lean`, so a leaf small enough for `omega` still needed a human to say
`omega`. That is the gap between a pipeline that checks proofs and one that
finds them.

## This does not violate "nothing is invented"

The rule protects the PLAN: a step the blueprint did not authorize may not
appear, a cited result may not be conjured, the target may not drift. Closing a
step the plan already authorized, by searching for the tactic that discharges
it, invents nothing — the obligation was stated before the search ran, and the
kernel is still the only thing that says whether it closed. What would violate
the rule is search that *changes the statement* to something closable, which is
what `target_protection.py` exists to catch and why it runs afterwards anyway.

## One import, not nine

The kernel costs about 5.0s to import Mathlib and 0.1s to elaborate a small
proof — the import is 98% of the run (`doctrine/kernel_economics.md`). A
portfolio that tried twelve tactics in twelve processes would cost twelve
imports and about a minute per leaf, which is why nobody would use it.

So every candidate goes into ONE file as its own `example`, elaborated once.
Lean reports diagnostics for the whole file with line positions, and each
candidate owns a line range, so one import yields twelve verdicts. That is the
batching the Generator doctrine asks for, applied to the pack's own machinery.

## What is not in the portfolio

`native_decide` closes goals by trusting a compiled evaluation, and the
placeholder scan rejects it for that reason — a tactic the pack bans downstream
must not be proposed upstream, or the search's best answer is one the gates will
refuse. `sorry` and `admit` are excluded for the obvious reason. The portfolio
is a list in a file, so an addition is a visible decision.

Usage:
    tactic_search.py --goal "<prop>" [--binders "(n : Nat) (h : 0 < n)"]
                     [--imports Mathlib] [--portfolio <file.json>]
                     [--timeout 300] [--json]
    tactic_search.py --self-test

Exit: 0 a tactic closed the goal, 1 none did, 2 usage/IO, 3 toolchain unavailable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Ordered cheapest-first: the ones that fail fast sit early so a timeout that
# truncates elaboration still gets through the decision procedures.
DEFAULT_PORTFOLIO = [
    "rfl",
    "trivial",
    "simp",
    "decide",
    "omega",
    "norm_num",
    "ring",
    "linarith",
    "positivity",
    "simp_all",
    "tauto",
    "nlinarith",
    "aesop",
    "exact?",
]

BANNED = {"native_decide", "sorry", "admit", "by?"}

DIAG = re.compile(r"^(?P<file>[^\s:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>error|warning|info)\b",
                  re.IGNORECASE)
CANDIDATE_PREFIX = "witsoc_candidate_"
IMPORT_LINE = re.compile(r"^\s*(?:public\s+|meta\s+)*import\s+\S")
MODULE_IMPORT = re.compile(r"^\s*(?:public|meta)\s+(?:public\s+|meta\s+)*import\s+\S")
TRY_THIS = re.compile(r"Try this:\s*(?P<suggestion>.+)")


def build_file(goal: str, binders: str, portfolio: list[str], imports: list[str],
               preamble: list[str] | None = None,
               postamble: list[str] | None = None) -> tuple[str, list[dict]]:
    """One file, one import, every candidate as its own named theorem.

    Returns the source and, for each candidate, the line range it owns. The
    ranges are what turn a file-level diagnostic stream back into per-candidate
    verdicts, so they are computed while writing rather than guessed after.

    The candidates were `example`s until a drawn-target batch found the two
    readings disagreeing: a tactic that closed the `example` left a `sorry` in
    the theorem the circularity audit then read. An anonymous `example` and a
    named theorem do not always receive the same goal from the surrounding
    `variable` block, and a search that validates a different statement from
    the artifact anyone checks is worse than no search. Naming them also means
    the audit can read THIS file rather than a reconstruction of it.
    """
    # An import line may already carry the module system's `public` keyword, in
    # which case prefixing another `import` produces a parse error rather than a
    # failed search — the two look identical from the exit code.
    lines: list[str] = []
    # The module system stacks the modifiers: `public import`, `meta import`,
    # and `public meta import` all occur. Matching a fixed list of prefixes
    # missed the stacked form and prepended a second `import` to it, which reads
    # as a parse error at the word `public` and looks like a broken statement.
    given = [n if IMPORT_LINE.match(n) else f"import {n}" for n in imports]
    # `public import` is a module-system form and is a hard parse error outside a
    # `module` file. The header has to come first, before any import.
    if any(MODULE_IMPORT.match(n) for n in given):
        lines.append("module")
        lines.append("")
    lines.extend(given)
    lines.append("")
    # Real goals live inside `open`, `universe` and `variable` declarations. A
    # portfolio run with none of them elaborates only the self-contained tenth
    # of any library, so the caller may replay the goal's own context here.
    if preamble:
        lines.extend(preamble)
        lines.append("")
    spans = []
    for index, tactic in enumerate(portfolio):
        start = len(lines) + 1                      # 1-indexed, like Lean
        lines.append(f"-- CANDIDATE {index}: {tactic}")
        lines.append(f"theorem {CANDIDATE_PREFIX}{index} {binders} : {goal} := by".strip())
        for part in tactic.splitlines():
            lines.append(f"  {part}")
        lines.append("")
        spans.append({"index": index, "tactic": tactic, "first": start, "last": len(lines)})
    # A preamble that OPENS scopes has to close them, or the file ends inside a
    # namespace and Lean rejects the whole thing at EOF.
    if postamble:
        lines.extend(postamble)
    return "\n".join(lines) + "\n", spans


def attribute(output: str, spans: list[dict]) -> tuple[list[dict], list[str]]:
    """Map file-level diagnostics back onto candidates.

    A diagnostic belongs to the candidate whose line range contains it. Errors
    fail that candidate; warnings fail it too, because the warnings Lean emits
    here are `declaration uses 'sorry'` and its relatives. An `info` is not a
    failure — `exact?` reports its answer as info, and a successful search that
    was scored as a failure because it printed something would be the most
    expensive kind of wrong.

    Errors that land OUTSIDE every candidate are returned separately, and they
    are fatal to the whole run. A bad import or a preamble that does not parse
    reports at line 1, inside no candidate's range; ignoring those meant every
    candidate kept its default verdict and a file that never elaborated came
    back as twelve tactics closing the goal in 0.6 seconds.
    """
    verdicts = {span["index"]: {"tactic": span["tactic"], "closed": True,
                                "diagnostics": [], "suggestion": None} for span in spans}
    file_level: list[str] = []
    current: int | None = None
    for raw in output.splitlines():
        match = DIAG.match(raw.strip())
        if match:
            line = int(match.group("line"))
            severity = match.group("sev").lower()
            current = None
            for span in spans:
                if span["first"] <= line <= span["last"]:
                    current = span["index"]
                    break
            if current is None:
                if severity == "error":
                    file_level.append(raw.strip()[:220])
                continue
            if severity in {"error", "warning"}:
                verdicts[current]["closed"] = False
                verdicts[current]["diagnostics"].append(raw.strip()[:220])
            else:
                verdicts[current]["diagnostics"].append(raw.strip()[:220])
        elif current is not None:
            # continuation of a multi-line diagnostic (goal states, case headers)
            if verdicts[current]["diagnostics"]:
                verdicts[current]["diagnostics"][-1] = (
                    verdicts[current]["diagnostics"][-1] + " | " + raw.strip())[:400]
        suggestion = TRY_THIS.search(raw)
        if suggestion and current is not None:
            verdicts[current]["suggestion"] = suggestion.group("suggestion").strip()
    return [verdicts[span["index"]] for span in spans], file_level


def lean_project() -> Path | None:
    root = os.environ.get("WITSOC2_LEAN_PROJECT")
    return Path(root) if root and Path(root).exists() else None


def run_search(goal: str, binders: str, portfolio: list[str], imports: list[str],
               timeout: int, preamble: list[str] | None = None,
               postamble: list[str] | None = None) -> dict:
    banned = [t for t in portfolio if any(b in t for b in BANNED)]
    if banned:
        return {"verdict": "error",
                "reading": f"portfolio contains banned tactics {banned}. The placeholder scan "
                           "rejects these downstream, so proposing one produces a result the "
                           "gates will refuse — a search whose best answer is unusable"}
    project = lean_project()
    if project is None:
        return {"verdict": "unavailable", "checked": 0,
                "reading": "WITSOC2_LEAN_PROJECT is unset or missing. `lake env` takes its "
                           "search path from the directory it runs in, so elaborating anywhere "
                           "else uses the ambient toolchain with an empty path and every import "
                           "fails while looking like a proof problem. This is NOT_RUN, not a "
                           "failure to close the goal"}

    source, spans = build_file(goal, binders, portfolio, imports, preamble, postamble)
    with tempfile.TemporaryDirectory(prefix="tacticsearch_") as tmp:
        path = Path(tmp) / "Search.lean"
        path.write_text(source, encoding="utf-8")
        try:
            proc = subprocess.run(["lake", "env", "lean", str(path)],
                                  capture_output=True, text=True, timeout=timeout,
                                  cwd=str(project))
        except subprocess.TimeoutExpired:
            return {"verdict": "timeout", "budget_seconds": timeout, "candidates": len(portfolio),
                    "reading": "elaboration did not finish inside the budget. A timeout is not a "
                               "refutation of any candidate — nothing was learned about the goal"}
        except OSError as exc:
            return {"verdict": "unavailable", "reading": f"could not run lake: {exc}"}

    results, file_level = attribute(proc.stdout + "\n" + proc.stderr, spans)
    if file_level:
        return {"verdict": "error", "goal": goal, "binders": binders,
                "file_level_errors": file_level, "candidates": len(portfolio),
                "closed_by": [], "first_closing": None, "results": results,
                "imports": imports, "preamble": preamble or [],
                "reading": "the file did not elaborate: " + file_level[0] + ". No candidate "
                           "was tried, so this says nothing about the goal"}
    closed = [r for r in results if r["closed"]]
    return {
        "verdict": "closed" if closed else "open",
        "goal": goal, "binders": binders,
        "candidates": len(portfolio), "closed_by": [r["tactic"] for r in closed],
        "first_closing": closed[0]["tactic"] if closed else None,
        "suggestion": next((r["suggestion"] for r in closed if r["suggestion"]), None),
        "results": results,
        "imports": imports,
        "preamble": preamble or [],
        # The exact source that produced these verdicts, so a downstream audit
        # reads the artifact that was checked rather than a rebuild of it.
        "source": source,
        "candidate_prefix": CANDIDATE_PREFIX,
        "reading": (f"{len(closed)} of {len(portfolio)} candidates closed the goal in a single "
                    "import. The kernel is the judge; this only chose what to hand it."
                    if closed else
                    f"none of {len(portfolio)} candidates closed the goal. That is information "
                    "about the leaf: it is not small, and the plan should split it rather than "
                    "widen the portfolio"),
    }


def self_test() -> int:
    """Offline. The parts that can be wrong without a toolchain are the file
    layout and the attribution, and both are testable against recorded output.

    The live path was exercised earlier against a real Mathlib checkout; on a
    machine where the kernel is unavailable this still tells you whether the
    search would mis-attribute a verdict, which is the failure that would
    silently report a tactic as closing a goal it did not close.
    """
    cases, failures = [], 0
    portfolio = ["simp", "omega", "exact?"]
    source, spans = build_file("n + 0 = n", "(n : Nat)", portfolio, ["Mathlib"])

    cases.append(("one import serves the whole portfolio",
                  source.count("import Mathlib") == 1 and source.count("theorem witsoc_candidate_") == 3,
                  f"{source.count('import Mathlib')} import(s), "
                  f"{source.count('theorem witsoc_candidate_')} candidates"))
    cases.append(("every candidate owns a disjoint line range",
                  all(spans[i]["last"] < spans[i + 1]["first"] for i in range(len(spans) - 1)),
                  str([(s["first"], s["last"]) for s in spans])))

    # An error inside candidate 1 must fail candidate 1 and nothing else.
    line = spans[1]["first"] + 1
    out = f"Search.lean:{line}:2: error: omega could not prove the goal"
    verdicts, _ = attribute(out, spans)
    cases.append(("an error fails exactly the candidate whose range contains it",
                  verdicts[0]["closed"] and not verdicts[1]["closed"] and verdicts[2]["closed"],
                  str([(v["tactic"], v["closed"]) for v in verdicts])))

    # An error at line 1 belongs to no candidate. Before this was separated out
    # it was dropped, every candidate kept its default `closed`, and a file that
    # never elaborated reported the whole portfolio succeeding.
    verdicts, file_level = attribute(
        "Search.lean:1:0: error: cannot use `public import` without `module`", spans)
    cases.append(("a diagnostic outside every candidate is reported as file-level",
                  len(file_level) == 1 and all(v["closed"] for v in verdicts),
                  f"{len(file_level)} file-level error(s)"))

    # A preamble the caller supplies must land between the imports and the
    # candidates, and a `public import` must bring the module header with it.
    src2, _ = build_file("True", "", ["trivial"], ["public meta import Mathlib.Init"],
                         ["variable {a : Nat}"])
    cases.append(("a module-system import gets its header, and the preamble follows it",
                  src2.startswith("module\n") and
                  src2.count("import") == 1 and
                  src2.index("public meta import") < src2.index("variable {a : Nat}") <
                  src2.index("theorem witsoc_candidate_"),
                  src2.splitlines()[0]))

    # An info message must NOT fail a candidate, and its suggestion is kept.
    line = spans[2]["first"] + 1
    out = f"Search.lean:{line}:2: info: Try this: exact Nat.add_zero n"
    verdicts, _ = attribute(out, spans)
    cases.append(("an info message is not a failure and its suggestion is captured",
                  verdicts[2]["closed"] and verdicts[2]["suggestion"] == "exact Nat.add_zero n",
                  str(verdicts[2]["suggestion"])))

    # A sorry warning must fail the candidate: a warning here is never cosmetic.
    line = spans[0]["first"] + 1
    verdicts, _ = attribute(f"Search.lean:{line}:0: warning: declaration uses 'sorry'", spans)
    cases.append(("a sorry warning fails the candidate",
                  not verdicts[0]["closed"], str(verdicts[0]["diagnostics"])[:80]))

    # Multi-line goal states must attach to the diagnostic that opened them.
    line = spans[1]["first"] + 1
    out = f"Search.lean:{line}:2: error: unsolved goals\ncase h\n⊢ n + 0 = n"
    verdicts, _ = attribute(out, spans)
    cases.append(("a multi-line diagnostic stays with its candidate",
                  not verdicts[1]["closed"] and "case h" in verdicts[1]["diagnostics"][0],
                  verdicts[1]["diagnostics"][0][:90]))

    # A banned tactic must be refused before anything is spent.
    result = run_search("True", "", ["native_decide"], ["Mathlib"], 10)
    cases.append(("a banned tactic is refused rather than proposed",
                  result["verdict"] == "error", result["reading"][:100]))

    # No project configured must read as NOT_RUN, never as "no tactic worked".
    saved = os.environ.pop("WITSOC2_LEAN_PROJECT", None)
    result = run_search("True", "", ["simp"], ["Mathlib"], 10)
    if saved:
        os.environ["WITSOC2_LEAN_PROJECT"] = saved
    cases.append(("an absent toolchain is NOT_RUN, not a failed search",
                  result["verdict"] == "unavailable", result["reading"][:100]))

    print("\n  TACTIC SEARCH SELF-TEST (offline — layout and attribution)\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {note[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 62)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    if not lean_project():
        print("  note: the live elaboration path was NOT exercised here — no Lean project is "
              "configured. This suite covers what can be wrong without one.")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--goal")
    ap.add_argument("--binders", default="")
    ap.add_argument("--imports", nargs="*", default=["Mathlib"])
    ap.add_argument("--portfolio", help="JSON list of tactics, replacing the default")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--preamble", help="file of context lines (open/universe/variable) "
                                       "replayed after the imports")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.goal:
        ap.error("--goal is required (or --self-test)")

    portfolio = DEFAULT_PORTFOLIO
    if args.portfolio:
        try:
            portfolio = json.loads(Path(args.portfolio).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    preamble = None
    if args.preamble:
        try:
            preamble = Path(args.preamble).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    result = run_search(args.goal, args.binders, portfolio, args.imports, args.timeout,
                        preamble)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"TACTIC SEARCH: {result['verdict']} — {result.get('goal', '')}")
        if result.get("closed_by"):
            print(f"  closed by      {', '.join(result['closed_by'])}")
        if result.get("suggestion"):
            print(f"  suggestion     {result['suggestion']}")
        print(f"  {result['reading']}")
    return {"closed": 0, "open": 1, "error": 2,
            "unavailable": 3, "timeout": 3}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
