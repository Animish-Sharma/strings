#!/usr/bin/env python3
"""WIT cycle — check, audit, and receipt completeness.

`audit` is deliberately paranoid heuristics, not a checker: cheap regexes with
high yield. `status` is the one that matters — it verifies the RECEIPT covers
every obligation, because a receipt that silently covers only some steps is how
a partial review reads as a full one.

Usage:
    wit_cycle.py audit <file.wit> [--json]
    wit_cycle.py status <file.wit> --receipt <r.json> [--json]
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from witlib import OBLIGATION_KEYWORDS, parse  # noqa: E402

HEDGES = ("clearly","obvious","obviously","trivial","trivially","standard",
          "straightforward","well-known","well known","classical result","evidently")
HIDDEN = ("nonzero","finite","compact","measurable","positive","bounded","continuous",
          "invertible","non-empty","nonempty")

def audit(doc) -> list[dict]:
    out = []
    for s in doc.steps:
        by = s.by_text or ""
        if s.keyword not in {"GAP","CASE"} and by and not re.search(r"[A-Za-z]{3,}", 
                re.sub(r"\[[^\]]*\]", "", by)):
            out.append({"line": s.line_no, "kind": "weak_justification",
                        "text": f"[{s.label}] BY cites references with no method"})
        for h in HEDGES:
            if h in by.lower() or h in s.text.lower():
                out.append({"line": s.line_no, "kind": "hedge",
                            "text": f"[{s.label}] uses '{h}' where a reason belongs"})
                break
        for w in HIDDEN:
            if re.search(rf"\b{w}\b", s.text, re.IGNORECASE) and w not in " ".join(
                    g[1] for g in doc.given).lower():
                out.append({"line": s.line_no, "kind": "hidden_assumption_risk",
                            "text": f"[{s.label}] assumes '{w}', not in GIVEN"})
                break
        if s.keyword == "GAP":
            out.append({"line": s.line_no, "kind": "gap",
                        "text": f"[{s.label}] explicit GAP" +
                                (f" expecting [{s.gap_expecting}]" if s.gap_expecting else
                                 " (unnamed — prefer GAP EXPECTING [name])")})
        if s.citations:
            out.append({"line": s.line_no, "kind": "cite",
                        "text": f"[{s.label}] cites {s.citations} — preconditions must be "
                                "discharged by a preceding step"})
    return out

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("audit"); a1.add_argument("artifact"); a1.add_argument("--json", action="store_true")
    a2 = sub.add_parser("status"); a2.add_argument("artifact"); a2.add_argument("--receipt", required=True)
    a2.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: doc = parse(Path(a.artifact).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.cmd == "audit":
        warnings = audit(doc)
        if a.json: print(json.dumps({"ok": not warnings, "warnings": warnings}, indent=2))
        elif warnings:
            print(f"AUDIT: {len(warnings)} warning(s)\n")
            for w in warnings: print(f"  line {w['line']:>3} [{w['kind']}] {w['text']}")
        else: print("AUDIT: clean")
        return 1 if warnings else 0

    try: receipt = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    obligations = [s.label for s in doc.steps if s.keyword in OBLIGATION_KEYWORDS]
    covered = {str(v.get("label")) for v in receipt.get("verdicts", [])}
    missing = [o for o in obligations if o not in covered]
    rejected = [v for v in receipt.get("verdicts", []) if v.get("verdict") == "REJECT"]
    gaps = [s.label for s in doc.steps if s.keyword == "GAP"]
    final = [s.label for s in doc.steps if s.keyword == "SHOW"]
    final_covered = (not final) or final[-1] in covered

    problems = []
    if missing: problems.append(f"{len(missing)} obligation(s) have no verdict: {missing}")
    if not final_covered: problems.append("the concluding SHOW step has no verdict")
    if gaps: problems.append(f"{len(gaps)} explicit GAP step(s) remain: {gaps}")
    if rejected: problems.append(f"{len(rejected)} step(s) rejected")
    if receipt.get("final_verdict") and doc.status and \
            receipt["final_verdict"].upper() != doc.status.upper():
        problems.append(f"receipt final_verdict {receipt['final_verdict']} != header "
                        f"Status {doc.status}")
    out = {"complete": not problems, "obligations": len(obligations),
           "covered": len(covered), "problems": problems,
           "note": "a receipt that covers only some obligations is not a partial pass; "
                   "it is an incomplete review"}
    if a.json: print(json.dumps(out, indent=2))
    elif problems:
        print(f"STATUS: INCOMPLETE ({out['covered']}/{out['obligations']} covered)\n")
        for p in problems: print(f"  {p}")
    else: print(f"STATUS: complete — all {out['obligations']} obligations covered")
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
