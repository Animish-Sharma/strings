#!/usr/bin/env python3
"""Proof autopsy — harvest a closure into a reusable technique.

Run on SUCCESS, not failure. Two operations:

  generalize   replace concrete literals with fresh parameters and re-check. If
               the generalized form still closes, the argument never needed the
               specific numbers and the general version is the reusable one.
               Kernel-gated by construction: a false generalization simply fails
               to close, so this cannot manufacture a result.
  harvest      record the load-bearing move, fingerprinted by goal shape, into
               the technique atlas.

Atlas entries are retrieval hints carrying NO trust. They enter
OPEN_UNFALSIFIED and stay there: knowing that a technique once worked on a
similar-looking goal says nothing about this goal.

Usage:
    proof_autopsy.py generalize --artifact <a.lean> [--json]
    proof_autopsy.py harvest --artifact <a.lean> --atlas <atlas.json> --move "..."
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

FORBIDDEN = ("sorry","admit","axiom","native_decide")
RE_LITERAL = re.compile(r"(?<![\w.])(\d+)(?![\w.])")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generalize"); g.add_argument("--artifact", required=True)
    g.add_argument("--json", action="store_true")
    h = sub.add_parser("harvest"); h.add_argument("--artifact", required=True)
    h.add_argument("--atlas", required=True); h.add_argument("--move", required=True)
    a = ap.parse_args()
    try: src = Path(a.artifact).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    present = [f for f in FORBIDDEN if re.search(rf"(?<![\w]){f}(?![\w])", src)]
    if present:
        print(f"REFUSED: the input is not a closure — it contains {present}. There is "
              "nothing to harvest from an argument that did not close.", file=sys.stderr)
        return 1

    if a.cmd == "generalize":
        literals = sorted({int(x) for x in RE_LITERAL.findall(src)} - {0, 1, 2})
        if not literals:
            out = {"generalizable": False,
                   "why": "no non-trivial literals; the argument is already general in "
                          "its constants"}
            print(json.dumps(out, indent=2) if a.json else f"GENERALIZE: {out['why']}")
            return 0
        candidate = src
        for i, lit in enumerate(literals):
            candidate = RE_LITERAL.sub(
                lambda m, l=lit, n=i: (f"k{n}" if int(m.group(1)) == l else m.group(1)),
                candidate)
        params = " ".join(f"(k{i} : Nat)" for i in range(len(literals)))
        out = {"generalizable": True, "literals_abstracted": literals,
               "new_parameters": params, "candidate": candidate[:1500],
               "next": "re-check the candidate. If the kernel closes it, the general form "
                       "is the reusable one; if not, those constants were load-bearing "
                       "and that is worth knowing too.",
               "safety": "kernel-gated by construction — a false generalization fails to "
                         "close, so this operation cannot manufacture a result"}
        print(json.dumps(out, indent=2) if a.json else
              f"GENERALIZE: abstracted {literals} -> {params}\n  {out['next']}")
        return 0

    signature = hashlib.sha256(re.sub(r"\s+", " ", src).encode()).hexdigest()[:16]
    atlas_path = Path(a.atlas)
    atlas = (json.loads(atlas_path.read_text(encoding="utf-8"))
             if atlas_path.exists() else {"schema":"maths.technique_atlas.v1","entries":[]})
    atlas["entries"].append({"signature":signature,"move":a.move,
        "provenance":f"harvested from {Path(a.artifact).name}",
        "status":"OPEN_UNFALSIFIED","trust":"none",
        "note":"a retrieval hint. That this move once closed a similar-looking goal "
               "says nothing about the next one."})
    atlas_path.write_text(json.dumps(atlas, indent=2)+"\n", encoding="utf-8")
    print(f"harvested {signature}: {a.move}\n  status OPEN_UNFALSIFIED, trust none")
    return 0
if __name__ == "__main__":
    sys.exit(main())
