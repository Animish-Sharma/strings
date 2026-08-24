#!/usr/bin/env python3
"""Spike — what actually separates a proof from a citation.

`allowed_external_facts` constrains the PLAN. A tactic pulls in whatever it
likes and the premise audit reports "0 citations", so a campaign can be admitted
whose entire content is one library call the claim never authorised. Refusing
that needs a rule, and the rule is not obvious:

  * "any Mathlib constant must be declared" flags an honest induction, because
    `ring` and `omega` emit Mathlib lemmas of their own.
  * "tactic infrastructure is exempt" exempts the very lemma that carried the
    whole claim in the case that motivated this.

So this does not argue. It scores candidate rules against labelled data that
already exists: the drawn batch, where 22 closings were shown to cite the target
and 15 were shown not to, plus two hand-labelled campaign artifacts.

Features per case, read off the rendered proof term:

    size            identifiers in the term
    head            the constant the term is an application of, if it is one
    head_is_target  that head has the target's TYPE, per the corpus
    lib_used        library constants used, excluding core and the term's own
                    auxiliaries
    type_match      any used constant whose corpus type equals the target's

Usage:
    rule_spike.py --targets batch40.json --results batch40_results.json
                  [--extra extra_cases.json] [--out features.json]
    rule_spike.py --score features.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "gates"))
sys.path.insert(0, str(HERE))

from circularity_audit import run_lean, split_prints, cited_names  # noqa: E402
from run_batch import audit_file, module_of                        # noqa: E402

# Foundational namespaces. A proof that uses these has not cited a result; it
# has used the language. Everything else is a library dependency and the point
# of the exercise is deciding which of those matter.
CORE = ("Eq", "Nat", "Int", "Bool", "Prop", "Sort", "Type", "And", "Or", "Not",
        "Iff", "Exists", "True", "False", "Function", "id", "congrArg", "congr",
        "rfl", "trivial", "of_eq_true", "eq_self", "propext", "Classical",
        "Quot", "HEq", "Subtype", "Decidable", "ite", "dite", "letFun")


def term_of(source: str, decl: str, project: str, timeout: int = 300) -> str | None:
    out = run_lean(f"{source}\n#print {decl}\n", project, timeout)
    if out is None:
        return None
    blocks = split_prints(out)
    return blocks.get(decl)


ARROW = re.compile(r"\s(?:→|->)\s")
RELATION = {"∣": "Dvd.dvd", "≤": "LE.le", "≥": "GE.ge", "<": "LT.lt", ">": "GT.gt",
            "∈": "Membership.mem", "⊆": "HasSubset.Subset", "≠": "Ne", "=": "Eq"}


def conclusion_head(type_text: str | None) -> str | None:
    """The head symbol of what a declaration concludes.

    Strips leading binders and every antecedent, then names the leading symbol
    of what is left. `∀ n, 2 ≤ n → Irrational (√n)` concludes `Irrational`.
    Textual, and deliberately so: the alternative is elaborating every candidate
    to compare, which costs a kernel run per constant.
    """
    if not type_text:
        return None
    text = type_text
    # The corpus stores a type as `{binders} (binders) : conclusion`, not as
    # `∀ ..., ...`. Splitting on ∀ found nothing and the head came back as a
    # binder name, which is why this rule scored 1/23 on its first run.
    depth, cut = 0, None
    for i, ch in enumerate(text):
        if ch in "([{⟨":
            depth += 1
        elif ch in ")]}⟩":
            depth -= 1
        elif ch == ":" and depth == 0 and not text[i:i + 2] == ":=":
            cut = i
    if cut is not None:
        text = text[cut + 1:]
    for _ in range(8):
        stripped = re.sub(r"^\s*(?:∀|Π)[^,]*,", "", text)
        if stripped == text:
            break
        text = stripped
    text = ARROW.split(text)[-1].strip().lstrip("(")
    m = re.match(r"([A-Za-z_][\w.']*)", text)
    if m:
        return m.group(1)
    # A conclusion can be headed by notation rather than a name — `2 ∣ n * m`,
    # `1 < x`. The relation IS the head symbol there.
    for sym, name in RELATION.items():
        if sym in text:
            return name
    return None


def head_constant(term: str) -> str | None:
    """The constant a proof term is an application of, after the binders.

    `fun {α} [inst] {x} hx => foo hx` has head `foo`. A term that is a `have`
    chain, a `match`, or a recursor application has no single head, which is
    itself the signal: it did more than hand the goal to one result.
    """
    body = term.split(":=", 1)[-1]
    for _ in range(4):
        body = re.sub(r"^\s*fun\b.*?=>", "", body, flags=re.S).strip()
        # A WIT artifact wraps every step as `have stepN := <term>`, so the head
        # of the artifact is always None unless the wrapper is unwrapped first.
        m = re.match(r"have\s+[\w.']+\s*(?::[^:]*?)?:=\s*", body, flags=re.S)
        if not m:
            break
        body = body[m.end():].strip()
    if body.startswith(("have", "let", "match", "if", "⟨", "(")):
        return None
    m = re.match(r"([A-Za-z_][\w.']*)", body)
    return m.group(1) if m else None


def features(case: dict, by_name: dict, by_type: dict, project: str) -> dict:
    source, decl = case["source"], case["decl"]
    term = term_of(source, decl, project)
    if term is None:
        return {**case, "error": "no term"}
    names = cited_names(term)
    own = {n for n in names if n.startswith(decl)}
    lib = sorted(n for n in names - own
                 if not n.startswith(CORE) and n not in ("sorry", "sorryAx"))
    tgt_type = by_name.get(case["target"])
    same_type = sorted({n for n in names
                        for full in ([n] if n in by_name else by_type.get(n, []))
                        if tgt_type and by_name.get(full) == tgt_type
                        and full != case["target"]}) if tgt_type else []
    head = head_constant(term)
    head_type = by_name.get(head) if head else None
    # What a result CONCLUDES, as opposed to what it assumes. A lemma whose
    # conclusion is headed by the same symbol as the target is doing the
    # target's work, even when it is strictly more general — which is exactly
    # the case a same-type check cannot see.
    tgt_head = conclusion_head(tgt_type) if tgt_type else None
    load_bearing = sorted({
        full for n in names
        for full in ([n] if n in by_name else by_type.get(n, [])[:1])
        if full != case["target"] and tgt_head
        and conclusion_head(by_name.get(full)) == tgt_head
    }) if tgt_head else []
    return {
        "target": case["target"], "tactic": case["tactic"], "label": case["label"],
        "size": len(re.findall(r"[A-Za-z_][\w.']*", term)),
        "head": head,
        "head_is_target_type": bool(head_type and tgt_type and head_type == tgt_type),
        "lib_used": lib[:40], "lib_count": len(lib),
        "type_match": same_type,
        "target_conclusion_head": tgt_head,
        "load_bearing": load_bearing[:20], "load_bearing_count": len(load_bearing),
        "term_excerpt": term[:300],
    }


def build_cases(targets: list[dict], results: dict) -> list[dict]:
    by_target = {t["name"]: t for t in targets}
    cases = []
    for row in results["rows"]:
        t = by_target.get(row["name"])
        if not t:
            continue
        if row["outcome"] == "INDEPENDENT":
            tactic, label = row["proved_by"], "proof"
        elif row["outcome"] == "CITED_TARGET":
            bad = next((a["tactic"] for a in row.get("audits", [])
                        if a["verdict"] == "FAIL"), None)
            if not bad:
                continue
            tactic, label = bad, "citation"
        else:
            continue
        source, decl = audit_file(t, tactic)
        cases.append({"target": row["name"], "tactic": tactic, "label": label,
                      "source": source, "decl": decl})
    return cases


def score(rows: list[dict]) -> None:
    """Every rule is judged on the same two numbers: how many citations it
    catches, and how many honest proofs it destroys. A rule that refuses
    everything catches all of them and is worthless."""
    rules = {
        "a. head constant has the target's type":
            lambda r: r["head_is_target_type"],
        "b. any used constant has the target's type":
            lambda r: bool(r["type_match"]),
        "c. term smaller than 25 identifiers":
            lambda r: r["size"] < 25,
        "d. one library dependency or fewer":
            lambda r: r["lib_count"] <= 1,
        "e. uses a result concluding what the target concludes":
            lambda r: r.get("load_bearing_count", 0) > 0,
        "a or e":
            lambda r: r["head_is_target_type"] or r.get("load_bearing_count", 0) > 0,
        "a or b":
            lambda r: r["head_is_target_type"] or bool(r["type_match"]),
        "b and small (b or (a and size<25))":
            lambda r: bool(r["type_match"]) or (r["head_is_target_type"] and r["size"] < 25),
    }
    cites = [r for r in rows if r["label"] == "citation"]
    proofs = [r for r in rows if r["label"] == "proof"]
    print(f"\n  labelled: {len(cites)} citation(s), {len(proofs)} proof(s)\n")
    print(f"  {'rule':<46} {'caught':>10} {'destroyed':>11}")
    print("  " + "-" * 69)
    for name, fn in rules.items():
        caught = sum(1 for r in cites if fn(r))
        destroyed = sum(1 for r in proofs if fn(r))
        print(f"  {name:<46} {caught:>3}/{len(cites):<6} {destroyed:>4}/{len(proofs):<6}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--targets")
    ap.add_argument("--results")
    ap.add_argument("--extra")
    ap.add_argument("--corpus", default=os.environ.get("WITSOC2_MATHS_CORPUS"))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out")
    ap.add_argument("--score")
    a = ap.parse_args()

    if a.score:
        score(json.loads(Path(a.score).read_text(encoding="utf-8"))["rows"])
        return 0

    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    if not project:
        print("ERROR: WITSOC2_LEAN_PROJECT unset", file=sys.stderr)
        return 3
    targets = json.loads(Path(a.targets).read_text(encoding="utf-8"))["targets"]
    results = json.loads(Path(a.results).read_text(encoding="utf-8"))
    cases = build_cases(targets, results)
    if a.extra:
        cases += json.loads(Path(a.extra).read_text(encoding="utf-8"))

    by_name, by_type = {}, {}
    if a.corpus and Path(a.corpus).exists():
        data = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
        for d in data.get("declarations", []):
            by_name[d["name"]] = d.get("type")
            parts = d["name"].split(".")
            for i in range(1, len(parts)):
                by_type.setdefault(".".join(parts[i:]), []).append(d["name"])

    print(f"[spike] {len(cases)} labelled case(s)", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(lambda c: features(c, by_name, by_type, project), cases))
    rows = [r for r in rows if "error" not in r]
    body = {"schema": "maths.rule_spike.v1", "rows": rows}
    if a.out:
        Path(a.out).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    score(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
