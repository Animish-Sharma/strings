#!/usr/bin/env python3
"""Propose decompositions, and let the rubric choose between them.

The pack could RENDER a plan, CHECK a plan, and score whether a plan's gaps were
good ones — and it could not produce a plan. Every blueprint in this repository
was written by hand, including the ones the producer's own evals run on. So the
first genuinely creative step in the loop was the one step with no tooling at
all, and `sketch_rubric.py` — which exists precisely to compare two
decompositions of the same target — had never had two to compare.

This emits candidates from the SHAPE of the frozen statement, scores each with
that rubric, and returns them ranked. It proposes; the rubric ranks; a person or
a stronger model chooses. None of that invents mathematics: a decomposition is a
claim about structure, and every candidate here is checked by the same gates as
a hand-written one, then closed or not by the kernel.

The patterns, and when each applies:

    DIRECT        no hypotheses to chain and a conclusion a decision procedure
                  plausibly closes. One node. Proposing a three-step plan for a
                  one-tactic goal is how a decomposition adds work.
    CHAIN         one hypothesis per step, each discharged in order.
    BRIDGE        the conclusion relates two sides that the hypotheses relate
                  only THROUGH a middle. This is the transitivity shape, and it
                  is the one that most often turns a stuck goal into two easy
                  ones.
    CASES         the statement carries a disjunction or a comparison whose
                  branches behave differently.
    INDUCTION     quantified over a natural and not closable by arithmetic.

## What it refuses to do

It does not guess at a target it cannot parse. A proposer that always returns
something returns something for a statement it did not understand, and a
plausible plan for a misread goal costs more than no plan — the gates will not
catch it, because the plan is internally coherent and about the wrong thing.

Usage:
    decompose.py --claim <claim.json> [--top N] [--json]
    decompose.py --self-test

Exit: 0 candidates proposed, 1 nothing proposable, 2 IO
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sketch_rubric import score  # noqa: E402

# Relations that compose transitively. The bridge pattern is only proposed when
# the conclusion uses one, because inserting a middle term into a relation that
# does not compose produces two lemmas that do not join.
TRANSITIVE = ("<=", "≤", "<", ">=", "≥", ">", "=", "⊆", "∣")
ARITH_CLOSABLE = re.compile(r"^[\s\w+\-*/()≤<≥>=,.:]+$")


def parse_target(formal: str) -> dict:
    """Binders, hypotheses and conclusion from a `theorem name (...) : goal`."""
    head = re.match(r"\s*(?:theorem|lemma)\s+(\w+)\s*(.*)$", formal.strip(), re.DOTALL)
    if not head:
        return {}
    name, rest = head.group(1), head.group(2)
    # The colon that separates binders from the goal is the one at paren depth
    # ZERO. A non-greedy match stops at the first colon in the string, which is
    # inside the first binder — so every hypothesis went unseen and only the
    # DIRECT pattern was ever proposed, on every target.
    depth = split_at = -1
    depth = 0
    for i, ch in enumerate(rest):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            split_at = i
            break
    if split_at < 0:
        return {}
    binder_text, conclusion = rest[:split_at], rest[split_at + 1:].strip()
    binders = re.findall(r"\(([^)]*)\)", binder_text)
    hypotheses, variables = [], []
    for b in binders:
        if ":" not in b:
            continue
        names, _, typ = b.partition(":")
        entry = {"names": names.split(), "type": typ.strip()}
        # A binder whose type mentions a relation is a hypothesis; one whose
        # type is a sort is a variable. Getting this backwards proposes a plan
        # that discharges a type as if it were an assumption.
        (hypotheses if any(r in typ for r in TRANSITIVE) else variables).append(entry)
    return {"name": name, "variables": variables, "hypotheses": hypotheses,
            "conclusion": conclusion}


def sides(expr: str) -> tuple[str, str, str] | None:
    for rel in ("≤", "<=", "≥", ">=", "<", ">", "=", "⊆", "∣"):
        if rel in expr:
            left, _, right = expr.partition(rel)
            return left.strip(), rel, right.strip()
    return None


def substitute(formal: str, variable: str, value: str) -> str:
    """Replace a bound variable with a value, on token boundaries only.

    `n` inside `Finset.range` or `min` is not the variable, and a plain string
    replace produced propositions that did not parse — which is worse than the
    duplicated node it was meant to fix, because it looks like a real plan.
    """
    return re.sub(rf"(?<![A-Za-z0-9_'.]){re.escape(variable)}(?![A-Za-z0-9_'])",
                  value, formal)


def node(nid: str, statement: str, formal: str, kind: str, granularity: str,
         depends: list[str] | None = None) -> dict:
    return {"id": nid, "statement": statement, "formal_statement": formal, "kind": kind,
            "granularity": granularity, "depends_on": depends or []}


def candidates(parsed: dict) -> list[dict]:
    out: list[dict] = []
    conclusion = parsed["conclusion"]
    hyps = parsed["hypotheses"]
    split = sides(conclusion)

    # DIRECT
    out.append({
        "pattern": "direct",
        "why": "no structure to exploit: one obligation, closed by a decision procedure",
        "nodes": [node("1", "the goal, closed directly", conclusion, "goal", "single_tactic")]})

    # CHAIN — one hypothesis per step
    if hyps:
        nodes, prev = [], []
        for i, h in enumerate(hyps, start=1):
            nodes.append(node(str(i), f"use hypothesis {' '.join(h['names'])}",
                              h["type"], "hypothesis", "single_tactic", list(prev)))
            prev = [str(i)]
        nodes.append(node(str(len(hyps) + 1), "the goal, from the hypotheses in order",
                          conclusion, "goal", "single_tactic", list(prev)))
        out.append({"pattern": "chain",
                    "why": "each hypothesis discharged in turn, then the goal",
                    "nodes": nodes})

    # BRIDGE — the transitivity shape
    if split and len(hyps) >= 2 and split[1] in TRANSITIVE:
        left, rel, right = split
        # The middle is what you get by applying ONE hypothesis to one side of
        # the conclusion. For `a + c <= b + d` with `a <= b`, that is `b + c` —
        # a composite term, not a bare variable, which is why looking only for
        # an unmentioned variable found nothing and the pattern never fired on
        # the shape it exists for.
        middle = None
        rationale = ""
        for h in hyps:
            hsplit = sides(h["type"])
            if not hsplit:
                continue
            src, hrel, dst = hsplit
            if hrel not in TRANSITIVE or not src or not dst:
                continue
            candidate = re.sub(rf"(?<![\w]){re.escape(src)}(?![\w])", dst, left)
            if candidate not in (left, right):
                middle, rationale = candidate, f"rewriting {src!r} to {dst!r} in the left side"
                break
        if middle is None:
            # Fall back to a term the hypotheses mention and the conclusion does
            # not: the classic chain through an intermediate object.
            spare = sorted({v for h in hyps for v in re.findall(r"\b[a-z]\b", h["type"])}
                           - set(re.findall(r"\b[a-z]\b", left))
                           - set(re.findall(r"\b[a-z]\b", right)))
            if spare:
                middle = spare[0]
                rationale = f"through {spare[0]!r}, which the hypotheses mention and the goal "\
                            "does not"
        if middle:
            out.append({
                "pattern": "bridge",
                "why": f"the conclusion relates {left!r} to {right!r}; {rationale} gives "
                       f"{middle!r}, and the two halves join by transitivity",
                "nodes": [
                    node("1", f"the left half, up to {middle}", f"{left} {rel} {middle}",
                         "lemma", "single_tactic"),
                    node("2", f"the right half, from {middle}", f"{middle} {rel} {right}",
                         "lemma", "single_tactic"),
                    node("3", "the goal, by transitivity", conclusion, "composition",
                         "single_tactic", ["1", "2"])]})
    # CASES
    if any(k in conclusion for k in ("∨", " or ")) or (split and split[1] in ("<", ">")):
        out.append({"pattern": "cases",
                    "why": "the statement has branches that behave differently; each is a "
                           "separate, smaller obligation",
                    "nodes": [
                        node("1", "the first branch", conclusion, "case", "single_tactic"),
                        node("2", "the second branch", conclusion, "case", "single_tactic"),
                        node("3", "the goal, from both branches", conclusion, "composition",
                             "single_tactic", ["1", "2"])]})

    # INDUCTION
    nat_var = next((n for v in parsed["variables"]
                    if "Nat" in v["type"] or "ℕ" in v["type"] for n in v["names"]), None)
    if nat_var and not ARITH_CLOSABLE.match(conclusion):
        # All three nodes used to carry the target verbatim, so a decomposition
        # "into three parts" was three copies of the problem and the rubric was
        # scoring a shape rather than a plan. Instantiate: the base case is the
        # goal at zero, the step is the goal at k implying the goal at k+1.
        base = substitute(conclusion, nat_var, "0")
        at_k = substitute(conclusion, nat_var, "k")
        at_k1 = substitute(conclusion, nat_var, "(k + 1)")
        out.append({"pattern": "induction",
                    "why": "quantified over a natural and not closable by arithmetic alone",
                    "nodes": [
                        node("1", f"the base case: the goal at {nat_var} = 0",
                             base, "base", "single_tactic"),
                        node("2", f"the inductive step: from {nat_var} = k to k + 1",
                             f"∀ k : ℕ, ({at_k}) → ({at_k1})", "step", "multi_step", ["1"]),
                        node("3", "the goal, by induction on " + nat_var, conclusion,
                             "composition", "single_tactic", ["1", "2"])]})
    return out


def propose(claim: dict) -> dict:
    formal = (claim.get("formal_target")
              or (claim.get("frozen_conditions") or {}).get("formal_target") or "")
    parsed = parse_target(formal)
    if not parsed:
        return {"verdict": "not_parseable", "formal_target": formal,
                "reading": "the frozen target does not read as `theorem name (binders) : goal`, "
                           "so its structure is unknown. A proposer that returns something for "
                           "a statement it did not understand returns a coherent plan about the "
                           "wrong goal, and no gate downstream catches that"}
    ranked = []
    for cand in candidates(parsed):
        assessment = score({"nodes": cand["nodes"], "target": parsed["conclusion"]})
        ranked.append({**cand, "score": assessment["score"],
                       "components": assessment["components"],
                       "miracles": assessment["miracles"]})
    ranked.sort(key=lambda c: -c["score"])
    return {"verdict": "proposed", "target": parsed, "candidates": ranked,
            "reading": f"{len(ranked)} candidate decomposition(s), ranked by the same rubric "
                       "that judges a hand-written one. It proposes; the rubric ranks; the "
                       "kernel still decides"}


def self_test() -> int:
    cases, failures = [], 0

    def patterns(formal):
        r = propose({"formal_target": formal})
        return r, [c["pattern"] for c in r.get("candidates", [])]

    r, pats = patterns("theorem t (a b c d : Nat) (h1 : a <= b) (h2 : c <= d) : a + c <= b + d")
    cases.append(("a transitive goal whose hypotheses share no term with it proposes a BRIDGE",
                  "bridge" in pats, f"patterns: {pats}"))

    r, pats = patterns("theorem t (n : Nat) : n + 0 = n")
    cases.append(("a goal with no hypotheses proposes DIRECT and no bridge",
                  "direct" in pats and "bridge" not in pats,
                  "inserting a middle into a goal with nothing to bridge through yields two "
                  "lemmas that never join"))

    r, pats = patterns("theorem t (a b : Nat) (h : a <= b) : a + 1 <= b + 1")
    cases.append(("a single-hypothesis goal proposes a CHAIN", "chain" in pats, f"{pats}"))

    r, _ = patterns("this is not a theorem statement at all")
    cases.append(("an unparseable target is refused, not guessed at",
                  r["verdict"] == "not_parseable", r["reading"][:110]))

    r, _ = patterns("theorem t (a b c d : Nat) (h1 : a <= b) (h2 : c <= d) : a + c <= b + d")
    best = r["candidates"][0]
    cases.append(("the rubric ranks, and a restatement of the target is penalised",
                  all(not c["miracles"] or c["score"] < best["score"] for c in r["candidates"]),
                  f"best {best['pattern']} at {best['score']}"))

    parsed = parse_target("theorem t (a b : Nat) (h : a <= b) : a + 1 <= b + 1")
    cases.append(("a sort binder is a VARIABLE and a relation binder a HYPOTHESIS",
                  [v["names"] for v in parsed["variables"]] == [["a", "b"]]
                  and [h["names"] for h in parsed["hypotheses"]] == [["h"]],
                  "getting this backwards discharges a type as if it were an assumption"))

    print("\n  DECOMPOSITION SELF-TEST — it proposes; the rubric ranks\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {str(note)[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claim")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.claim:
        ap.error("--claim is required (or --self-test)")
    try:
        claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = propose(claim)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["verdict"] == "proposed" else 1
    if result["verdict"] != "proposed":
        print(f"NOT PROPOSED: {result['reading']}")
        return 1
    print(f"DECOMPOSE: {result['reading']}\n")
    for cand in result["candidates"][:args.top]:
        print(f"  {cand['score']:.3f}  {cand['pattern']:<10} {len(cand['nodes'])} node(s)")
        print(f"          {cand['why'][:120]}")
        for n in cand["nodes"]:
            dep = f" <- {', '.join(n['depends_on'])}" if n["depends_on"] else ""
            print(f"            [{n['id']}] {n['formal_statement']}{dep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
