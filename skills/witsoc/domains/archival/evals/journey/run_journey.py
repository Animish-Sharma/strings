#!/usr/bin/env python3
"""The journey — one claim, the whole path, nothing pre-fitted.

Every other check in this pack tests a COMPONENT: does the adapter refuse a bad
dossier, is a decision right, does the stemma group on error. None of them ever
took a claim from a sentence to a status, and in the pack where that gap was
first closed it surfaced nine defects in a row — every one on the shortest path
through the system, every one behind a green suite.

Both directions, because a pack that admits everything and one that refuses
everything look identical from the passing side: the two-origin dossier must
reach a status, and the same claim with the letter copied from the register must
collapse and be refused.

Usage:  run_journey.py [--json]
Exit:   0 the journey behaved as specified, 1 it did not, 2 IO
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
FRAME = PACK.parent.parent


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(PACK))
        return proc.returncode, proc.stdout + proc.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)


def payload(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="arch_journey_"))
    claim = HERE / "claim.json"
    cases: list[dict] = []

    def record(step, ok, detail, why):
        cases.append({"step": step, "ok": ok, "detail": str(detail)[:150], "why": why})

    # 1. resolution — the statement must reach this pack from its own words.
    statement = json.loads(claim.read_text())["exact_statement"]
    code, out = run([sys.executable, str(FRAME / "scripts" / "resolve_domain.py"),
                     "--statement", statement, "--json"])
    decision = payload(out)
    record("resolve", decision.get("domain") == "archival",
           f"{decision.get('decision')} -> {decision.get('domain')}",
           "a pack never loaded is indistinguishable from one nobody wrote")

    # 2. produce — the dossier is BUILT, and its roots derived from the graph.
    built = tmp / "dossier.json"
    code, out = run([sys.executable, "scripts/dossier.py", "--claim", str(claim),
                     "--sources", str(HERE / "sources.json"), "--out", str(built)])
    made = json.loads(built.read_text()) if built.exists() else {}
    record("produce", code == 0 and made.get("derived", {}).get("independent_support") == 2,
           f"exit {code}, support {made.get('derived', {}).get('independent_support')}",
           "this pack could only refuse a dossier until it could make one; a checker without a "
           "producer teaches its format by rejection")

    # 3. the producer leaves the human judgements EMPTY, and the gates say so.
    code, out = run([sys.executable, "scripts/check.py", "--artifact", str(built),
                     "--claim", str(claim), "--tier", "structural", "--json"])
    record("unfinished dossier is refused", code == 1,
           f"exit {code} on a freshly produced dossier",
           "the survival argument and the falsity discriminator are the judgements no tool can "
           "make, and a producer that filled them would manufacture the evidence the gates exist "
           "to demand")

    # 4. answered, it passes — otherwise the gate refuses everything and enforces nothing.
    answered = json.loads(built.read_text())
    answered["archive_coverage"] = ("the Ostia harbour material and the Alexandrian papyri "
                                    "catalogued to 1980 were searched; two provincial archives "
                                    "were not")
    answered["what_the_record_would_look_like_if_false"] = (
        "the register would carry no entry for this hull that season and the letter would name "
        "a different consignment; both are checkable and both were checked")
    answered["interpretation"] = ("Two independent origins record the shipment. Nothing here "
                                  "speaks to how typical it was.")
    good = tmp / "answered.json"
    good.write_text(json.dumps(answered, indent=2))
    code, out = run([sys.executable, "scripts/check.py", "--artifact", str(good),
                     "--claim", str(claim), "--tier", "triangulation", "--json"])
    receipt = payload(out)
    record("answered dossier reaches a status", code == 0 and receipt.get("verdict") == "pass",
           f"exit {code}, verdict {receipt.get('verdict')}, "
           f"max {receipt.get('max_status')}",
           "a gate that refuses everything enforces nothing, it just stops")

    # 5. the cascade — the same claim, the letter copied from the register.
    casc = tmp / "cascade.json"
    code, out = run([sys.executable, "scripts/dossier.py", "--claim", str(claim),
                     "--sources", str(HERE / "sources_cascade.json"), "--out", str(casc)])
    made = json.loads(casc.read_text()) if casc.exists() else {}
    record("cascade collapses to one origin",
           made.get("derived", {}).get("independent_support") == 1,
           f"support {made.get('derived', {}).get('independent_support')}",
           "four agreeing sources copying one register are one voice, and in a bibliography the "
           "two are identical")

    merged = json.loads(casc.read_text())
    merged.update({k: answered[k] for k in
                   ("archive_coverage", "what_the_record_would_look_like_if_false",
                    "interpretation")})
    bad = tmp / "cascade_answered.json"
    bad.write_text(json.dumps(merged, indent=2))
    code, out = run([sys.executable, "scripts/check.py", "--artifact", str(bad),
                     "--claim", str(claim), "--tier", "triangulation", "--json"])
    record("and the claim of two origins is refused", code == 1,
           f"exit {code}", "the claim asserts two independent supports and the graph says one")

    failures = [c for c in cases if not c["ok"]]
    if args.json:
        print(json.dumps({"cases": cases, "failures": len(failures)}, indent=2))
        return 1 if failures else 0

    print("\n  JOURNEY — one claim, the whole path\n")
    for case in cases:
        print(f"  {'ok  ' if case['ok'] else 'FAIL'}  {case['step']:<34} {case['detail']}")
        print(f"          {case['why'][:118]}")
    print("\n" + "=" * 70)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases) - len(failures)}/{len(cases)} "
          "steps behaved as specified")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
