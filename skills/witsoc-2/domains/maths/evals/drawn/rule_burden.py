#!/usr/bin/env python3
"""How often does the citation rule fire on proofs nobody here wrote.

`RULE_SPIKE.md` chose the rules against 39 labelled cases, and the rule that
matters most fired on exactly one of them. One demonstration is not a
measurement, and the missing number is not precision — it is BURDEN.

Rule 4 does not claim to tell a proof from a citation. It says: you leaned on a
result that concludes what your target concludes, and you did not declare it.
Whether that is a good default therefore turns on one question this file
answers: **how often would it fire on an honest proof?** If almost always, it is
noise that trains people to switch it off. If seldom, it is a real check.

The control group is the library's own proofs. Each drawn target is rebuilt in
its own scope with the proof its author wrote, and audited with an EMPTY
allowlist — the harshest setting. Every firing is a case where a human proof
would be asked to declare something.

Two further things are recorded, because a rule that fires is only useful if it
fires for a reason you can act on:

  * `escape`: re-auditing with the named constants declared must PASS. If
    declaring what you leaned on does not clear the gate, the gate is unusable.
  * `rule1`: the target's own name appearing in its own proof. In a library
    that would be circular, so this should be ~0 and is a sanity check on the
    whole apparatus.

Usage:
    rule_burden.py --targets batch200.json [--limit N] [--workers 3]
                   [--out burden.json]
Exit: 0 measured, 2 IO, 3 no toolchain.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "gates"))
sys.path.insert(0, str(HERE))

from circularity_audit import audit, load_corpus_index, type_of_formal  # noqa: E402
from run_batch import module_of, preamble_for                          # noqa: E402

PROBE = "witsoc_burden_probe"


def author_source(target: dict) -> str:
    """The target restated in its own scope, carrying the author's proof."""
    imports = list(target["imports"]) + [f"public import {module_of(target['file'])}"]
    proof = target["proof"]
    head = f"theorem {PROBE} {target['binders']} : {target['statement']} :=".strip()
    body = proof if proof.startswith("\n") else " " + proof
    return "\n".join(["module", ""] + imports + [""] + preamble_for(target)
                     + ["", head + body, ""] + target["scope_close"] + [""])


def one(target: dict, by_name: dict, by_suffix: dict, project: str,
        timeout: int) -> dict:
    decl = ".".join(target["namespaces"] + [PROBE])
    formal = f"theorem t {target['binders']} : {target['statement']}"
    ttype = type_of_formal(formal)
    row = {"target": target["name"], "file": target["file"]}
    with tempfile.TemporaryDirectory(prefix="burden_") as td:
        path = Path(td) / "A.lean"
        path.write_text(author_source(target), encoding="utf-8")
        strict = audit(path, decl, {target["name"]}, project, timeout,
                       by_name, by_suffix, target["name"], set(), ttype)
        row["verdict"] = strict["verdict"]
        row["cites"] = strict.get("cites", [])
        row["dependencies"] = len(strict.get("library_dependencies") or [])
        # Rule 1 is the sanity check; rules 2-4 are the burden.
        row["rule"] = ("name" if strict["verdict"] == "FAIL"
                       and target["name"] in strict.get("cites", []) else
                       "undeclared" if strict["verdict"] == "FAIL" else None)
        if strict["verdict"] == "FAIL" and row["rule"] == "undeclared":
            relaxed = audit(path, decl, {target["name"]}, project, timeout,
                            by_name, by_suffix, target["name"],
                            set(strict.get("cites", [])), ttype)
            row["escape"] = relaxed["verdict"]
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--targets", required=True)
    ap.add_argument("--corpus", default=os.environ.get("WITSOC2_MATHS_CORPUS"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--out")
    a = ap.parse_args()

    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    if not project or not Path(project).is_dir():
        print("ERROR: WITSOC2_LEAN_PROJECT must point at a project", file=sys.stderr)
        return 3
    try:
        targets = json.loads(Path(a.targets).read_text(encoding="utf-8"))["targets"]
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if a.limit:
        targets = targets[: a.limit]
    by_name, by_suffix = load_corpus_index(a.corpus)
    if not by_name:
        print("ERROR: this measurement needs the declaration index", file=sys.stderr)
        return 3

    print(f"[burden] {len(targets)} author-written proof(s), empty allowlist",
          file=sys.stderr)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(lambda t: one(t, by_name, by_suffix, project, a.timeout),
                             targets))

    audited = [r for r in rows if r["verdict"] in {"PASS", "FAIL"}]
    fired = [r for r in audited if r["rule"] == "undeclared"]
    circular = [r for r in audited if r["rule"] == "name"]
    escapes = [r for r in fired if r.get("escape") == "PASS"]
    n = len(audited) or 1
    report = {
        "schema": "maths.rule_burden.v1",
        "sampled": len(rows), "audited": len(audited),
        "not_audited": len(rows) - len(audited),
        "fired_undeclared": len(fired), "fire_rate": round(len(fired) / n, 3),
        "self_citing": len(circular),
        "escape_works": len(escapes), "escape_rate":
            round(len(escapes) / len(fired), 3) if fired else None,
        "median_dependencies": sorted(r["dependencies"] for r in audited)[len(audited) // 2]
            if audited else None,
        "rows": rows,
    }
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
