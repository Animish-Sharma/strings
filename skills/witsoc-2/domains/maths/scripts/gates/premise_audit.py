#!/usr/bin/env python3
"""Premise precondition audit.

Every cited external result has hypotheses. A citation whose preconditions are
not discharged locally is an unresolved gap, not a step — and it is the
canonical way a wrong argument passes review, because the citation looks like
authority.

Checks, per citation:
  - the result is in the claim's allowed_external_facts (otherwise out of scope)
  - it resolves in the corpus (a guessed name is not evidence)
  - each declared precondition is discharged by an EARLIER step

## What `--corpus` changes, and why it matters

Without it, two of those three checks read the claim's own words. Whether a
premise "resolves in the corpus" is a boolean the author typed
(`resolved_in_corpus`), and the preconditions matched against earlier steps are
the preconditions the author chose to list. Under-declare a cited theorem's
hypotheses and the gate passes on every one of them — which is the exact shape
of the failure it was built to catch, since a citation looks like authority and
nobody re-reads its hypotheses.

Pass `--corpus` and the gate looks the premise up itself:

  * an author's `resolved_in_corpus: true` for a name the corpus does not hold
    is a FAILURE, not a hint;
  * the number of top-level hypotheses in the corpus TYPE is compared against
    the number declared, and a shortfall is reported with both numbers.

The arrow count is a FLOOR, not a full parse: hypotheses stated as explicit
binders rather than as arrows are not counted, so this detects under-declaration
and does not detect all of it. A floor derived from the library still beats a
number the author supplied, and saying which one it is keeps the receipt honest.

Usage:  premise_audit.py <artifact.wit> --claim <claim.json>
                         [--corpus <corpus.json>] [--json]
Exit: 0 clean, 1 unmet, 2 IO error.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from witlib import parse  # noqa: E402


def top_level_arrows(type_text: str) -> int:
    """Count `->` arrows at bracket depth zero — a FLOOR on the hypothesis count.

    Depth-aware because `(a -> b) -> c` has one top-level arrow and two written
    ones, and counting the written ones would report a hypothesis that is not
    there. Hypotheses given as explicit binders are not counted at all, so a
    zero here means "this parse found none", never "this lemma has none".
    """
    depth = 0
    count = 0
    index = 0
    text = type_text.replace("\N{RIGHTWARDS ARROW}", "->")
    while index < len(text):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith("->", index):
            # An arrow straight after `}` or `]` closes an IMPLICIT or INSTANCE
            # binder. Those are discharged by unification and by instance search,
            # not by the person citing the lemma, so counting them would demand
            # preconditions nobody is supposed to supply — and a gate that asks
            # for impossible declarations gets routed around rather than fixed.
            before = text[:index].rstrip()
            if not before.endswith(("}", "]")):
                count += 1
            index += 1
        index += 1
    return count

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact"); ap.add_argument("--claim", required=True)
    ap.add_argument("--corpus", help="declaration index; turns two self-reported checks "
                                     "into lookups")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        doc = parse(Path(a.artifact).read_text(encoding="utf-8"))
        claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    # The frozen claim may list allowed facts as bare names or as objects
    # carrying their preconditions. Both are legitimate — a name alone says the
    # fact may be cited and says nothing about what it requires — and crashing on
    # the first shape turns a real gate into an exception that happens to exit
    # non-zero, which reads in the receipt exactly like a failed audit.
    index: dict[str, dict] = {}
    if a.corpus:
        try:
            blob = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
            records = blob.get("declarations", blob) if isinstance(blob, dict) else blob
            index = {d["name"]: d for d in records if isinstance(d, dict) and d.get("name")}
        except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
            print(f"ERROR: corpus unreadable: {exc}", file=sys.stderr); return 2

    allowed = {}
    for fact in claim.get("allowed_external_facts", []) or []:
        if isinstance(fact, str):
            allowed[fact] = {"name": fact}
        elif isinstance(fact, dict) and fact.get("name"):
            allowed[fact["name"]] = fact
    problems, audited = [], []

    for step in doc.steps:
        for cite in step.citations:
            name = cite.split(",")[0].strip()
            match = next((k for k in allowed if k and (k in cite or cite in k)), None)
            if not match:
                problems.append(f"[{step.label}] cites {name!r}, which is not in "
                                "allowed_external_facts — out of scope is not a step")
                continue
            fact = allowed[match]
            record = index.get(match) if index else None
            if index and record is None:
                problems.append(f"[{step.label}] cites {match!r}, which is NOT in the corpus. "
                                "The claim "
                                + ("asserts it resolves" if fact.get("resolved_in_corpus")
                                   else "does not say it resolves")
                                + " — a guessed name is not evidence, and the lookup is the "
                                  "answer, not the assertion")
            elif not index and fact.get("resolved_in_corpus") is False:
                problems.append(f"[{step.label}] cites {match!r}, which is unresolved in "
                                "the corpus — a guessed name is not evidence")
            if record:
                arrows = top_level_arrows(record.get("type") or record.get("statement") or "")
                declared = len(fact.get("preconditions", []) or [])
                if arrows > declared:
                    problems.append(
                        f"[{step.label}] cites {match!r}, whose library type has at least "
                        f"{arrows} hypothesis(es) and the claim declares {declared}. An "
                        "under-declared citation passes every precondition check by having "
                        "fewer of them")
            earlier = {s.label for s in doc.steps if s.line_no < step.line_no}
            earlier_text = " ".join(s.text.lower() for s in doc.steps
                                    if s.line_no < step.line_no)
            for pre in fact.get("preconditions", []):
                key = " ".join(str(pre).lower().split()[:4])
                if key and key not in earlier_text:
                    problems.append(f"[{step.label}] cites {match!r} whose precondition "
                                    f"{str(pre)[:60]!r} is not discharged by any earlier step")
            audited.append({"step": step.label, "cites": match,
                            "preconditions": fact.get("preconditions", [])})

    out = {"verdict": "FAIL" if problems else "PASS", "citations_audited": len(audited),
           "problems": problems, "audited": audited,
           "corpus_consulted": bool(index),
           "provenance": ("hypothesis counts derived from the library type"
                          if index else
                          "resolution and preconditions read from the claim; pass --corpus to "
                          "derive them instead")}
    if a.json: print(json.dumps(out, indent=2))
    else:
        print(f"PREMISE AUDIT: {out['verdict']} ({len(audited)} citation(s))")
        for p in problems: print(f"  {p}")
    return 1 if problems else 0
if __name__ == "__main__":
    sys.exit(main())
