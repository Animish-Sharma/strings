#!/usr/bin/env python3
"""Blueprint init — start a plan from a frozen claim.

Production takes a blueprint and there was no way to get one except by writing
two hundred lines of JSON against a schema you had to read first. That is the
reason a careful person skips the machinery, and machinery people skip is
machinery that only ever runs on the examples its author wrote.

So this writes the skeleton: the metadata, the frozen target hash computed from
the claim rather than typed, the protection block, and one step per obligation
you name — with every formalization left EMPTY.

It does not invent the proof. `generate_wit` renders a reviewed plan and invents
nothing; a scaffolder that guessed the steps would move the invention one file
upstream and call it authored. What it removes is the bookkeeping: the hash, the
schema shape, the field names, the ordering rules.

Usage:
    blueprint_init.py --claim <claim.json> --name <ident> [--steps N]
                      [--formal "theorem foo : ..."] [--out bp.json]
    blueprint_init.py --statement "..." --name <ident> [--steps N]

Exit: 0 written, 2 usage/IO
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from witlib import normalize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claim")
    ap.add_argument("--statement")
    ap.add_argument("--name", required=True)
    ap.add_argument("--steps", type=int, default=2)
    ap.add_argument("--formal")
    ap.add_argument("--preamble")
    ap.add_argument("--out")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.name):
        print("ERROR: --name must be lowercase letters, digits and underscores; it becomes a "
              "Lean identifier", file=sys.stderr)
        return 2

    statement, claim = args.statement, {}
    if args.claim:
        try:
            claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        statement = statement or claim.get("exact_statement") or claim.get("statement")
    if not statement:
        print("ERROR: supply --statement, or a --claim carrying exact_statement", file=sys.stderr)
        return 2

    frozen = hashlib.sha256(normalize(statement).encode()).hexdigest()
    steps = []
    for index in range(1, max(1, args.steps) + 1):
        last = index == args.steps
        steps.append({
            "step_id": str(index),
            "type": "SHOW" if last else "HAVE",
            "statement": statement if last else "FILL-ME: what this step establishes",
            **({"depends_on": [str(i) for i in range(1, index)]} if index > 1 else {}),
            "method": "FILL-ME: how, in one clause",
            "formalization": {"type": "FILL-ME: the Lean proposition",
                              "tactic": "FILL-ME: the tactic block"},
        })

    blueprint = {
        "metadata": {"name": args.name, "kind": "THEOREM"},
        "target_formalization": {
            "claim": statement,
            "hypotheses": claim.get("hypotheses", []),
            **({"preamble": args.preamble} if args.preamble else {}),
            "formal_statement": args.formal or
                "FILL-ME: the Lean signature. Supplied, never guessed — autoformalization is "
                "where fidelity is lost, and a guessed statement type-checks as well as a right one",
        },
        "target_protection": {
            "statement_tampering_forbidden": True,
            "frozen_target_sha256": frozen,
            "original_statement": statement,
            "authorized_mutations": [],
        },
        "external_dependencies": [],
        "lemma_plan": steps,
        "generator_directive": {"status_to_assert": "UNVERIFIED"},
        "_next": [
            "fill every FILL-ME; a step with no formalization keeps its hole and the artifact is "
            "honestly incomplete rather than confidently wrong",
            "declare every result you intend to cite in external_dependencies — a citation "
            "outside it is refused, because out of scope is not a step",
            "python3 scripts/premise_preflight.py --blueprint <this file>",
            "python3 scripts/produce.py --blueprint <this file> --tier kernel",
        ],
    }

    text = json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        blanks = text.count("FILL-ME")
        print(f"BLUEPRINT: wrote {args.out}")
        print(f"  frozen target  {frozen[:16]}...  (computed from the claim, not typed)")
        print(f"  steps          {len(steps)}")
        print(f"  blanks to fill {blanks}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
