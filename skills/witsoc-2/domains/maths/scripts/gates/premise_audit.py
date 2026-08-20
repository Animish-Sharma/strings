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

Usage:  premise_audit.py <artifact.wit> --claim <claim.json> [--json]
Exit: 0 clean, 1 unmet, 2 IO error.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from witlib import parse  # noqa: E402

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact"); ap.add_argument("--claim", required=True)
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
            if fact.get("resolved_in_corpus") is False:
                problems.append(f"[{step.label}] cites {match!r}, which is unresolved in "
                                "the corpus — a guessed name is not evidence")
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
           "problems": problems, "audited": audited}
    if a.json: print(json.dumps(out, indent=2))
    else:
        print(f"PREMISE AUDIT: {out['verdict']} ({len(audited)} citation(s))")
        for p in problems: print(f"  {p}")
    return 1 if problems else 0
if __name__ == "__main__":
    sys.exit(main())
