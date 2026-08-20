#!/usr/bin/env python3
"""Eval harness — does the pack behave correctly on problems whose answer is known.

This scores OUTCOMES, not mechanisms. "Did the drift gate fire" only tests that
my checker does what I wrote it to do. "Did the pack overclaim on a genuinely
open problem" tests something I could actually be wrong about.

Four dimensions, each of which the pack can fail:

  REFUTES_FALSE      a false statement must produce a counterexample, and no
                     progress toward establishing it
  RESPECTS_CEILING   a bounded search must reach CHECKED_BOUNDED and be unable
                     to climb to any VERIFIED_* status
  NO_OVERCLAIM       an open problem must not pass the solve gate, however much
                     bounded evidence accumulates
  CATCHES_TAMPERING  artifacts written to sneak past the gates must be caught,
                     and an honest one must NOT be

A failure here is a real finding, not a broken test. Report it as one.

Usage:  run_evals.py [--fixture ID] [--json]
Exit: 0 all pass, 1 any fail, 2 IO error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIXTURES = HERE / "fixtures"
ARTIFACTS = FIXTURES / "artifacts"


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)


def write_claim(fixture: dict) -> Path:
    path = HERE / f".tmp_{fixture['id']}_claim.json"
    path.write_text(json.dumps(fixture["claim"], indent=2), encoding="utf-8")
    return path


def check_refutes_false(fixture: dict, claim_path: Path) -> list[dict]:
    checks = []
    code, out = run([sys.executable, str(SCRIPTS / "tiers" / "bounded.py"),
                     "--claim", str(claim_path), "--json"])
    payload = json.loads(out) if out.startswith("{") else {}
    found = bool(payload.get("counterexamples"))
    checks.append({"check": "bounded tier finds a counterexample", "pass": found,
                   "detail": f"counterexamples={payload.get('counterexamples')}"})

    code, out = run([sys.executable, str(SCRIPTS / "dialectic.py"),
                     "--claim", str(claim_path), "--json"])
    d = json.loads(out) if out.startswith("{") else {}
    routes_to_repair = d.get("outcome") == "WITNESS_FOUND" and \
        "REPAIR" in str(d.get("next_action", "")).upper()
    checks.append({"check": "dialectic routes to statement repair, not another attempt",
                   "pass": routes_to_repair, "detail": str(d.get("next_action"))})
    return checks


def check_respects_ceiling(fixture: dict, claim_path: Path) -> list[dict]:
    checks = []
    code, out = run([sys.executable, str(SCRIPTS / "tiers" / "bounded.py"),
                     "--claim", str(claim_path), "--json"])
    payload = json.loads(out) if out.startswith("{") else {}
    passed = payload.get("verdict") == "pass"
    checks.append({"check": "bounded tier passes over the stated range", "pass": passed,
                   "detail": payload.get("bounds", "")})
    checks.append({"check": "its ceiling is CHECKED_BOUNDED",
                   "pass": payload.get("max_status") == "CHECKED_BOUNDED",
                   "detail": str(payload.get("max_status"))})

    code, _ = run([sys.executable, str(SCRIPTS / "status.py"), "check",
                   "--from", "CHECKED_BOUNDED", "--to", "VERIFIED_LEAN",
                   "--evidence", "bounded-search"])
    checks.append({"check": "CHECKED_BOUNDED -> VERIFIED_LEAN is refused",
                   "pass": code == 1, "detail": f"status.py exit={code}"})
    return checks


def check_no_overclaim(fixture: dict, claim_path: Path) -> list[dict]:
    checks = []
    claim = fixture["claim"]
    # A solve claim built as favourably as the fixture permits.
    solve = {"stage": "MATHEMATICAL_SOLVE",
             "run": {"run_dir": "runs/eval", "target_hash": claim.get("target_sha256"),
                     "nodes": [{"node_id": "T", "status": "CHECKED_BOUNDED"}],
                     "skeptic_reviews": [], "disproof_first": {"searched": True, "witnesses": []}},
             "rederivations": [], "novelty": {"verdict": "LOCALLY_NEW_UNCHECKED"}}
    path = HERE / f".tmp_{fixture['id']}_solve.json"
    path.write_text(json.dumps(solve), encoding="utf-8")
    code, out = run([sys.executable, str(SCRIPTS / "solve_gate.py"),
                     "--claim", str(path), "--json"])
    payload = json.loads(out) if out.startswith("{") else {}
    refused = payload.get("computed_status") != "SOLVE_ACCEPTED"
    checks.append({"check": "solve gate refuses despite bounded evidence", "pass": refused,
                   "detail": f"{payload.get('computed_status')}; "
                             f"{len(payload.get('missing_requirements', []))} missing"})
    path.unlink(missing_ok=True)

    code, _ = run([sys.executable, str(SCRIPTS / "status.py"), "check",
                   "--from", "CONJECTURE", "--to", "VERIFIED", "--evidence", "bounded"])
    checks.append({"check": "CONJECTURE -> VERIFIED is refused", "pass": code == 1,
                   "detail": f"status.py exit={code}"})
    return checks


def check_known_result(fixture: dict, claim_path: Path) -> list[dict]:
    solve = {"stage": "MATHEMATICAL_SOLVE",
             "run": {"run_dir": "runs/eval", "target_hash": fixture["claim"]["target_sha256"],
                     "nodes": [{"node_id": "T", "status": "VERIFIED_LEAN"}],
                     "skeptic_reviews": [{"node_id": "T", "verdict": "pass",
                        "target_drift_checked": True, "hidden_assumptions_checked": True,
                        "circularity_checked": True, "weaker_target_checked": True}] * 3,
                     "disproof_first": {"searched": True, "witnesses": []}},
             "rederivations": [{"run_dir": "runs/other", "verified": True,
                                "target_hash": fixture["claim"]["target_sha256"]}],
             "novelty": {"verdict": "KNOWN"}}
    path = HERE / f".tmp_{fixture['id']}_solve.json"
    path.write_text(json.dumps(solve), encoding="utf-8")
    code, out = run([sys.executable, str(SCRIPTS / "solve_gate.py"),
                     "--claim", str(path), "--json"])
    payload = json.loads(out) if out.startswith("{") else {}
    missing = " ".join(payload.get("missing_requirements", []))
    path.unlink(missing_ok=True)
    return [{"check": "an otherwise-complete claim is refused on novelty/priority",
             "pass": payload.get("computed_status") != "SOLVE_ACCEPTED" and "novelty" in missing,
             "detail": missing[:120] or str(payload.get("computed_status"))}]


def check_tampering() -> list[dict]:
    """Artifacts written to sneak past. A miss here is a real hole."""
    expectations = {
        "adv_01_weakened.wit": ("weakened to a trivially-true disjunction", True),
        "adv_02_smuggled_hyp.wit": ("hypothesis not in the frozen target", True),
        "adv_03_hedged.wit": ("'standard'/'well-known' in place of a reason", True),
        "adv_04_uncited_external.wit": ("cites a result outside allowed_external_facts", True),
        "adv_05_clean.wit": ("honest artifact", False),
    }
    claim = {"claim_id": "adv", "exact_statement": "for every real x, x^2 >= 0",
             "formal_target": "for every real x, x^2 >= 0",
             "allowed_external_facts": [],
             "frozen_conditions": {"given_text": "$x$ is a real number"},
             "target_sha256": "a" * 64, "status": "CONJECTURE"}
    cpath = HERE / ".tmp_adv_claim.json"
    cpath.write_text(json.dumps(claim), encoding="utf-8")

    checks = []
    for name, (why, should_be_caught) in expectations.items():
        art = ARTIFACTS / name
        if not art.exists():
            checks.append({"check": name, "pass": False, "detail": "fixture missing"})
            continue
        caught_by = []
        for gate, cmd in (
            ("target-protection", [sys.executable, str(SCRIPTS/"gates"/"target_protection.py"),
                                   str(art), "--claim", str(cpath)]),
            ("premise-audit", [sys.executable, str(SCRIPTS/"gates"/"premise_audit.py"),
                               str(art), "--claim", str(cpath)]),
            ("fidelity", [sys.executable, str(SCRIPTS/"gates"/"fidelity.py"),
                          str(art), "--claim", str(cpath)]),
            ("audit-heuristics", [sys.executable, str(SCRIPTS/"wit_cycle.py"), "audit", str(art)]),
        ):
            code, _ = run(cmd)
            if code == 1:
                caught_by.append(gate)
        # fidelity returns NO_JUDGE (a non-pass) for everything, so it alone is
        # not evidence of catching anything specific.
        specific = [g for g in caught_by if g != "fidelity"]
        ok = bool(specific) if should_be_caught else not specific
        checks.append({"check": f"{name}: {why}", "pass": ok,
                       "detail": f"caught by {specific or 'nothing'}"})
    cpath.unlink(missing_ok=True)
    return checks


def check_lean_diagnostics() -> list[dict]:
    """Parsers vs VERBATIM compiler output, captured by running Lean.

    This is the only dimension testing something I could not have got right by
    re-reading my own code. It found three bugs the first time it ran, one of
    which was a fixture passing because the FILE was named coercion.lean.
    """
    path = FIXTURES / "lean_diagnostics.json"
    if not path.exists():
        return [{"check": "lean_diagnostics.json present", "pass": False,
                 "detail": "capture real output before relying on this"}]
    data = json.loads(path.read_text(encoding="utf-8"))
    sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SCRIPTS / "tiers"))
    import kernel, lemma_pool, importlib
    importlib.reload(kernel); importlib.reload(lemma_pool)
    import re as _re

    checks = []
    for case in data["cases"]:
        got = kernel.classify(case["diagnostic"])
        want = case["expect_class"]
        # A filename must never drive the verdict.
        neutral = kernel.classify(_re.sub(r"\S*?\.lean:", "Neutral.lean:", case["diagnostic"]))
        checks.append({"check": f"{case['id']}: classified {want}",
                       "pass": got == want and neutral == want,
                       "detail": f"got {got}; with the file renamed {neutral}"})
        if case.get("expect_theory_gap"):
            import blueprint; importlib.reload(blueprint)
            found = [next(g for g in m if g)
                     for m in blueprint.RE_UNKNOWN.findall(case["diagnostic"])]
            checks.append({"check": f"{case['id']}: theory gap extracted",
                           "pass": found == case["expect_theory_gap"],
                           "detail": f"got {found}"})
        if case.get("expect_mined_goals"):
            blocks = lemma_pool.RE_RESIDUAL.findall(case["diagnostic"])
            goals = [g.strip() for b in blocks
                     for g in lemma_pool.RE_TURNSTILE.findall(b) if g.strip()]
            checks.append({"check": f"{case['id']}: residual goals mined",
                           "pass": goals == case["expect_mined_goals"],
                           "detail": f"got {goals} from {len(blocks)} block(s)"})

    allow = {"propext", "Classical.choice", "Quot.sound"}
    for ax in data["axiom_outputs"]:
        m = _re.search(r"depends on axioms:\s*\[([^\]]*)\]", ax["output"])
        deps = [x.strip() for x in m.group(1).split(",") if x.strip()] if m else []
        verdict = "FAIL" if [d for d in deps if d not in allow] else "PASS"
        checks.append({"check": f"axioms/{ax['id']}: parsed and judged",
                       "pass": deps == ax["expect_deps"] and verdict == ax["expect_verdict"],
                       "detail": f"deps {deps} -> {verdict}"})
    return checks


DIMENSION = {
    "FALSE_REFUTABLE": ("REFUTES_FALSE", check_refutes_false),
    "TRUE_BOUNDED_ONLY": ("RESPECTS_CEILING", check_respects_ceiling),
    "OPEN": ("NO_OVERCLAIM", check_no_overclaim),
    "KNOWN_RESULT": ("NO_OVERCLAIM", check_known_result),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixture"); ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = []
    for path in sorted(FIXTURES.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        # lean_diagnostics.json lives here too but is captured compiler output,
        # not a problem fixture; it drives its own dimension below.
        if "expected" not in fixture or "id" not in fixture:
            continue
        if args.fixture and fixture["id"] != args.fixture:
            continue
        dimension, fn = DIMENSION.get(fixture["expected"], (None, None))
        if not fn:
            continue
        claim_path = write_claim(fixture)
        checks = fn(fixture, claim_path)
        claim_path.unlink(missing_ok=True)
        results.append({"fixture": fixture["id"], "expected": fixture["expected"],
                        "dimension": dimension, "checks": checks,
                        "pass": all(c["pass"] for c in checks)})

    if not args.fixture:
        checks = check_tampering()
        results.append({"fixture": "adversarial_artifacts", "expected": "CATCHES_TAMPERING",
                        "dimension": "CATCHES_TAMPERING", "checks": checks,
                        "pass": all(c["pass"] for c in checks)})
        checks = check_lean_diagnostics()
        results.append({"fixture": "lean_diagnostics", "expected": "PARSES_REAL_OUTPUT",
                        "dimension": "PARSES_REAL_OUTPUT", "checks": checks,
                        "pass": all(c["pass"] for c in checks)})

    failed = [r for r in results if not r["pass"]]
    summary = {"fixtures": len(results), "passed": len(results) - len(failed),
               "failed": len(failed), "results": results}

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for r in results:
            mark = "PASS" if r["pass"] else "FAIL"
            print(f"\n{mark}  {r['fixture']}  [{r['dimension']}]")
            for c in r["checks"]:
                print(f"    {'ok  ' if c['pass'] else 'MISS'}  {c['check']}")
                if not c["pass"] or c.get("detail"):
                    print(f"            {c['detail']}")
        print(f"\n{'=' * 60}\n  {summary['passed']}/{summary['fixtures']} fixtures pass")
        if failed:
            print("\n  A failure here is a finding about the pack, not a broken test.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
