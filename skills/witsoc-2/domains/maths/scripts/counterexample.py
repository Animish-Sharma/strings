#!/usr/bin/env python3
"""Counterexample families, certificates, and inflation.

Three things, in the order they are actually needed:

  families   the standard objects to test FIRST, by area. Ad hoc search after
             the standard families, not before — and if no family is relevant,
             that absence is itself a recorded finding.
  certify    a witness is not a result until the certificate is complete. Check
             the HYPOTHESES first, then the conclusion: a "counterexample" that
             fails a hypothesis refutes nothing.
  inflate    a single witness becomes a conjectural obstruction FAMILY — and
             inflation always drops status to CONJECTURE, because a family is a
             generalization of one data point.

Usage:
    counterexample.py families [--domain D]
    counterexample.py certify --cert <cert.json> [--json]
    counterexample.py inflate --witness "..." --family "..." [--json]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

FAMILIES = {
 "graph_theory": ["complete graphs","complete multipartite","paths and cycles",
   "random G(n,p)","bipartite incidence graphs","critical graphs","blow-ups",
   "sparse regular graphs","Kneser graphs"],
 "number_theory": ["prime powers","smooth numbers","squarefree numbers",
   "CRT residue constructions","valuation edge cases","highly composite numbers"],
 "additive_combinatorics": ["arithmetic progressions","subgroups and cosets",
   "Bohr-like sets","finite field models","Behrend-type constructions"],
 "geometry": ["grids","degenerate collinear configurations","finite-field geometries",
   "projective planes"],
 "algebra_logic": ["small groups and rings","quotients","nonfaithful representations",
   "free objects","term models"],
 "analysis": ["step functions","Weierstrass-type constructions","boundary cases of "
   "integrability","sequences with slow decay"],
}
REQUIRED_CERT = ["refuted_claim","witness","witness_path","verification_command",
  "verification_result","minimality","variant_alignment","why_hypotheses_satisfied",
  "why_conclusion_fails","independent_check","status"]
MINIMALITY = {"minimal","locally_minimal","not_minimized","unknown"}
CERT_STATUS = {"candidate","checked","verified","rejected"}

def certify(cert: dict) -> list[str]:
    problems = [f"missing field '{f}'" for f in REQUIRED_CERT if not cert.get(f)]
    if cert.get("minimality") and cert["minimality"] not in MINIMALITY:
        problems.append(f"minimality {cert['minimality']!r} not in {sorted(MINIMALITY)}")
    if cert.get("status") and cert["status"] not in CERT_STATUS:
        problems.append(f"status {cert['status']!r} not in {sorted(CERT_STATUS)}")
    # Order matters: a witness failing a hypothesis refutes nothing.
    if cert.get("why_hypotheses_satisfied") in {None, "", "unchecked"}:
        problems.append("hypotheses were not verified first — a witness that fails a "
                        "hypothesis of the claim refutes nothing at all")
    if str(cert.get("status")) in {"checked","verified"} and not cert.get("independent_check"):
        problems.append("a checked/verified certificate needs an independent second check")
    align = str(cert.get("variant_alignment","")).lower()
    if "stronger" in align:
        problems.append("NOTE: this witness refutes only a STRONGER variant. Demote that "
                        "variant and leave the original target OPEN — it is untouched.")
    return problems

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("families"); f.add_argument("--domain")
    c = sub.add_parser("certify"); c.add_argument("--cert", required=True); c.add_argument("--json", action="store_true")
    i = sub.add_parser("inflate"); i.add_argument("--witness", required=True)
    i.add_argument("--family", required=True); i.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "families":
        doms = [a.domain] if a.domain else sorted(FAMILIES)
        for d in doms:
            if d in FAMILIES:
                print(f"{d}:")
                for fam in FAMILIES[d]: print(f"    {fam}")
        print("\n  Test these before ad hoc search. If none is relevant, record that as a "
              "missing search template — the absence is a finding.")
        return 0

    if a.cmd == "inflate":
        out = {"witness": a.witness, "obstruction_family": a.family,
               "status": "CONJECTURE",
               "status_note": ("inflation ALWAYS drops to CONJECTURE. The witness was "
                               "checked; the family it suggests is not."),
               "next_attempt": f"prove that {a.family} preserves the refuting property, "
                               "then state the obstruction as its own target"}
        print(json.dumps(out, indent=2) if a.json else
              f"INFLATED to family: {a.family}\n  status: CONJECTURE — {out['status_note']}\n"
              f"  next: {out['next_attempt']}")
        return 0

    try: cert = json.loads(Path(a.cert).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    problems = certify(cert)
    hard = [p for p in problems if not p.startswith("NOTE:")]
    if a.json: print(json.dumps({"valid": not hard, "problems": problems}, indent=2))
    elif problems:
        print(f"CERTIFICATE: {'INVALID' if hard else 'VALID (with a note)'}\n")
        for p in problems: print(f"  {p}")
    else: print("CERTIFICATE: VALID")
    return 1 if hard else 0

if __name__ == "__main__":
    sys.exit(main())
