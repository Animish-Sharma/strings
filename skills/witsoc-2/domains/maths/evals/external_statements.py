#!/usr/bin/env python3
"""External evaluation — the gates against statements this pack did not write.

Every fixture in this pack was authored by whoever built it, which is the single
largest reason to distrust its green results. A gate tuned, however
unconsciously, to the shapes in its own test set will pass that set forever and
tell you nothing.

So this samples real theorem statements from an installed library — written by
its contributors, for their own purposes, years before this pack existed — and
asks the two gates most likely to be overfit whether they can tell a faithful
restatement from a drifted one.

The method:

1. Sample N theorem statements from the library source.
2. For each, build a claim frozen to that statement, and two artifacts: one
   restating it exactly, and one carrying a mechanical MUTATION — a dropped
   hypothesis, an added qualifier, a flipped quantifier, a weakened relation.
3. The gate must accept the faithful artifact and reject the mutated one.

**Both directions are scored, and the accept direction is the one that usually
breaks.** A gate that rejects everything catches every mutation and is useless;
the number that matters is how often it lets the honest restatement through.

Failures here are findings about the gate, not about the library. Where a real
statement uses a construct the gate cannot read, that is worth knowing before a
campaign depends on it.

Usage:
    external_statements.py --library <path/to/source> [--sample 12] [--json]
    external_statements.py --statements <sampled.json>

Exit: 0 the gates discriminate on every sampled statement, 1 otherwise, 2 IO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
sys.path.insert(0, str(PACK / "scripts"))
from witlib import normalize  # noqa: E402

RE_THEOREM = re.compile(
    r"^theorem\s+([A-Za-z_][A-Za-z0-9_'.]*)\s*(\([^\n]*?\))?\s*:\s*(.+?)\s*:=\s*$",
    re.MULTILINE)

# Mutations that a fidelity or target-protection gate must catch. Each changes
# what the statement MEANS while leaving it looking entirely reasonable — which
# is how a drifted target survives review.
MUTATIONS = [
    ("add_qualifier", lambda s: re.sub(r"\bfor all\b", "for all positive", s, count=1)
     if "for all" in s else "positive " + s,
     "adds a qualifier the target does not carry"),
    ("weaken_relation", lambda s: s.replace(" = ", " ≤ ", 1) if " = " in s else s.replace("≤", "<", 1),
     "weakens or strengthens the relation"),
    ("drop_quantifier", lambda s: re.sub(r"\b(every|all|any)\b\s*", "", s, count=1),
     "drops a universal quantifier, narrowing the claim to an instance"),
    ("add_finiteness", lambda s: "finite " + s,
     "adds a finiteness assumption absent from the target"),
]


def sample_statements(root: Path, count: int, seed: int) -> list[dict]:
    files = sorted(root.rglob("*.lean"))
    if not files:
        return []
    rng = random.Random(seed)
    found: list[dict] = []
    for path in rng.sample(files, min(80, len(files))):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in RE_THEOREM.finditer(text):
            statement = match.group(3).strip()
            if len(statement) > 90 or "sorry" in statement:
                continue
            found.append({"name": match.group(1), "statement": statement,
                          "source": str(path.relative_to(root))})
        if len(found) >= count * 4:
            break
    rng.shuffle(found)
    return found[:count]


def wit_artifact(name: str, statement: str) -> str:
    frozen = hashlib.sha256(normalize(statement).encode()).hexdigest()
    return (f"-- Status: UNVERIFIED\n-- Frozen-target-sha256: {frozen}\n\n"
            f"MODULE [{name}]\n\nTHEOREM [{name}]:\n  CLAIM:\n    {statement}\n\n"
            f"PROOF OF [{name}]:\n\n  [1] SHOW {statement}\n      BY the cited result.\n\n"
            f"  QED BY [1].\n")


def run_gate(gate: str, artifact: Path, claim: Path) -> int:
    proc = subprocess.run(
        [sys.executable, str(PACK / "scripts" / "gates" / gate), str(artifact),
         "--claim", str(claim)], capture_output=True, text=True, timeout=120)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--library", help="path to a source tree of the field's library")
    ap.add_argument("--statements", help="a pre-sampled JSON list, to make a run reproducible")
    ap.add_argument("--sample", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20260821)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.statements:
        statements = json.loads(Path(args.statements).read_text(encoding="utf-8"))
    elif args.library:
        root = Path(args.library).expanduser()
        if not root.is_dir():
            print(f"ERROR: {root} is not a directory", file=sys.stderr)
            return 2
        statements = sample_statements(root, args.sample, args.seed)
    else:
        ap.error("supply --library or --statements")

    if not statements:
        print("no statements sampled; nothing external to test against", file=sys.stderr)
        return 2

    gates = [("target_protection.py", "target-protection"), ("fidelity.py", "fidelity")]
    results = []
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for entry in statements:
            statement = entry["statement"]
            claim = {"claim_id": entry["name"], "exact_statement": statement,
                     "formal_target": statement, "allowed_external_facts": [],
                     "target_sha256": hashlib.sha256(
                         normalize(statement).encode()).hexdigest()}
            claim_path = tmp / "claim.json"
            claim_path.write_text(json.dumps(claim, indent=2), encoding="utf-8")

            faithful = tmp / "faithful.wit"
            faithful.write_text(wit_artifact(entry["name"], statement), encoding="utf-8")

            per_gate = {}
            for script, gate_name in gates:
                # A gate that returns NOT_RUN on the honest artifact has not
                # accepted it, and has not rejected it either. Both facts matter:
                # 3 means "I had nothing to ask", and a gate that always says
                # that is a gate that never contributes.
                code = run_gate(script, faithful, claim_path)
                accepted = code == 0
                not_run = code == 3
                caught, missed = [], []
                for label, mutate, why in MUTATIONS:
                    mutated = mutate(statement)
                    if normalize(mutated) == normalize(statement):
                        continue
                    path = tmp / f"{label}.wit"
                    path.write_text(wit_artifact(entry["name"], mutated), encoding="utf-8")
                    mutant_code = run_gate(script, path, claim_path)
                    (caught if mutant_code == 1 else missed).append(
                        {"mutation": label, "why": why, "became": mutated[:70],
                         "exit": mutant_code})
                per_gate[gate_name] = {"faithful_accepted": accepted, "not_run": not_run,
                                       "caught": len(caught), "missed": missed}

            primary = per_gate["target-protection"]
            results.append({"name": entry["name"], "source": entry.get("source"),
                            "statement": statement[:80],
                            "faithful_accepted": primary["faithful_accepted"],
                            "mutations_caught": primary["caught"],
                            "missed": primary["missed"],
                            "per_gate": per_gate})

    accepted = sum(1 for r in results if r["faithful_accepted"])
    applied = sum(r["mutations_caught"] + len(r["missed"]) for r in results)
    caught = sum(r["mutations_caught"] for r in results)

    by_gate = {}
    for _, gate_name in gates:
        rows = [r["per_gate"][gate_name] for r in results]
        by_gate[gate_name] = {
            "faithful_accepted": sum(1 for r in rows if r["faithful_accepted"]),
            "not_run_on_faithful": sum(1 for r in rows if r["not_run"]),
            "caught": sum(r["caught"] for r in rows),
            "applied": sum(r["caught"] + len(r["missed"]) for r in rows),
        }

    summary = {
        "statements": len(results),
        "faithful_accepted": f"{accepted}/{len(results)}",
        "mutations_caught": f"{caught}/{applied}",
        "by_gate": by_gate,
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"EXTERNAL EVALUATION — {len(results)} statement(s) this pack did not write\n")
        for r in results:
            mark = "ok  " if r["faithful_accepted"] else "MISS"
            print(f"  [{mark}] {r['name']:<28} caught {r['mutations_caught']}"
                  f"/{r['mutations_caught'] + len(r['missed'])}   {r['statement'][:46]}")
            for miss in r["missed"]:
                print(f"           missed {miss['mutation']}: {miss['why']}")
        print(f"\n  faithful restatements accepted   {summary['faithful_accepted']}")
        print(f"  mutations caught                 {summary['mutations_caught']}")
        print("\n  per gate:")
        for gate_name, stats in by_gate.items():
            note = ""
            if stats["not_run_on_faithful"] == len(results) and stats["caught"]:
                note = ("   <- NOT_RUN on the honest artifact (no independent judge supplied) "
                        "while its deterministic half still caught drift. Both halves are real; "
                        "only one of them can run unattended")
            elif stats["not_run_on_faithful"] == len(results):
                note = "   <- NOT_RUN everywhere and caught nothing; this gate contributed nothing"
            print(f"    {gate_name:<20} accepted {stats['faithful_accepted']}/{len(results)}"
                  f"   caught {stats['caught']}/{stats['applied']}{note}")
        print("\n  The accept column is the one that matters. A gate that rejects everything\n"
              "  catches every mutation and is useless.")

    ok = accepted == len(results) and caught == applied
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
