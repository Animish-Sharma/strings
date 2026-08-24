#!/usr/bin/env python3
"""Role evals — score the DECISION, not the artifact.

Every other eval in this pack scores an artifact through a gate: hand a bad
bundle to the adapter and check it is refused. None of them can tell you whether
the Explorer picked the right class, whether the Generator's endpoint measures
biology or sequencing depth, or whether Durbin ran the attack that would have
ended the campaign. Those are the decisions the doctrine is about, and until
this ran, nothing could detect a doctrine regressing.

A role eval is writable exactly where the judgement has machinery under it. That
is the constraint and it is a useful one: to score a decision you must first
make it mechanical, so this file doubles as the map of which judgements are.
Anything still made by eye cannot appear here, and its absence is the finding.

Fixtures are generated rather than stored, because a count matrix in the repo is
a large file nobody re-reads, and a generated one states the effect it contains
in the code that builds it.

Usage:  run_roles.py [--role explorer|generator|researcher] [--json]
Exit:   0 all cases pass, 1 failures, 2 IO
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
sys.path.insert(0, str(PACK / "scripts"))

import biolib as bl                     # noqa: E402
import classify_claim as cc             # noqa: E402
import counts as ct                     # noqa: E402
import expression_diagnostics as ed     # noqa: E402


def metadata_fixtures(root: Path) -> None:
    (root / "screen_only.csv").write_text(
        "cell_barcode,condition,guide\n" + "\n".join(
            f"c{i},{'treated' if i % 2 else 'control'},g{i % 4}" for i in range(60)) + "\n",
        encoding="utf-8")
    # Each donor must appear in BOTH arms, or the table is confounded, not crossed.
    (root / "donor_crossed.csv").write_text(
        "cell_barcode,condition,donor\n" + "\n".join(
            f"c{i},{'treated' if (i // 8) % 2 else 'control'},D{i % 8}" for i in range(160))
        + "\n", encoding="utf-8")
    (root / "donor_confounded.csv").write_text(
        "cell_barcode,condition,donor\n" + "\n".join(
            f"c{i},{'treated' if i < 40 else 'control'},D{0 if i < 40 else 1}"
            for i in range(80)) + "\n", encoding="utf-8")


def matrix_fixture(root: Path, name: str, kind: str):
    """One dense matrix + design + signature per named effect.

    The effect each fixture contains is stated here, in the code, so a case that
    starts failing is read against what the matrix was built to hold rather than
    against a memory of it.
    """
    genes = ed._base_genes(120)
    cells, rows = [], []
    seed = 0
    for u in range(6):
        arm = "treated" if u % 2 == 0 else "control"
        treated = arm == "treated"
        for c in range(12):
            seed += 1
            bc = f"{name}_u{u}_c{c}"
            sig = cc_val = st = 1.0
            cluster = context = ""
            scale = 1.0
            if kind == "signal":
                sig = 2.5 if treated else 1.0
            elif kind == "depth":
                scale = 3.0 if treated else 1.0          # depth only, no biology
            elif kind == "generic":
                sig, st = (1.15 if treated else 1.0), (2.0 if treated else 1.0)
            elif kind == "specific":
                sig = 2.5 if treated else 1.0
            elif kind == "composition":
                cluster = "K1" if (c < 9 if treated else c < 3) else "K0"
                sig = 2.0 if cluster == "K1" else 1.0    # proportions move, means do not
            elif kind == "reversal":
                context = "A" if (u // 2) % 2 == 0 else "B"
                sig = (2.5 if treated else 1.0) if context == "A" else (1.0 if treated else 2.5)
            cells.append((bc, ed._cell(genes, sig=sig, cc=cc_val, stress=st,
                                       scale=scale, seed=seed)))
            row = {"cell_barcode": bc, "condition": arm, "donor": f"D{u}"}
            if cluster:
                row["cluster"] = cluster
            if context:
                row["context"] = context
            rows.append(row)
    matrix, design, signature = ed._write_case(root, name, lambda: (genes, cells, rows))
    if kind == "absent":
        signature.write_text("NOT_A_REAL_GENE_1\nNOT_A_REAL_GENE_2\n", encoding="utf-8")
    return matrix, design, signature


def run_explorer(cases: list[dict], root: Path, classes: list[dict]) -> list[dict]:
    out = []
    for case in cases:
        result = cc.resolve(case["statement"], classes)
        design = None
        if case.get("metadata"):
            design = cc.supportable(root / case["metadata"], classes)
        result = cc.combine(result, design)
        if "expect_class" in case:
            got, want = result.get("claimed_class"), case["expect_class"]
        elif "expect_verdict" in case:
            got, want = result["verdict"], case["expect_verdict"]
        else:
            got, want = result.get("gap"), case["expect_gap"]
        out.append({"role": "explorer", "id": case["id"], "want": want, "got": got,
                    "ok": got == want, "why": case["why"],
                    "detail": result.get("reading", "")[:120]})
    return out


def run_generator(cases: list[dict], root: Path) -> list[dict]:
    out = []
    for case in cases:
        matrix, design, signature = matrix_fixture(root, case["id"], case["fixture"])
        got: object
        ok = False
        try:
            result = ed.analyse(matrix, signature, design, "condition", "donor",
                                treated="treated", min_counts=200, min_genes=30)
            effect = result["claimed_effect"].get("effect")
            got = round(abs(effect), 4) if effect is not None else None
            if "expect_gap_above" in case:
                ok = got is not None and got > case["expect_gap_above"]
            elif "expect_gap_below" in case:
                ok = got is not None and got < case["expect_gap_below"]
            elif case.get("expect_error"):
                ok = False
                got = "no error raised"
        except ValueError as exc:
            got = f"refused: {str(exc)[:60]}"
            ok = bool(case.get("expect_error"))
        want = (case.get("expect_gap_above") or case.get("expect_gap_below")
                or ("an error" if case.get("expect_error") else None))
        out.append({"role": "generator", "id": case["id"], "want": want, "got": got,
                    "ok": ok, "why": case["why"], "detail": ""})
    return out


def run_researcher(cases: list[dict], root: Path) -> list[dict]:
    out = []
    for case in cases:
        matrix, design, signature = matrix_fixture(root, "r_" + case["id"], case["fixture"])
        kwargs = {}
        if case["fixture"] == "composition":
            kwargs["cluster"] = "cluster"
        if case["fixture"] == "reversal":
            kwargs["context"] = "context"
        result = ed.analyse(matrix, signature, design, "condition", "donor",
                            treated="treated", min_counts=200, min_genes=30, **kwargs)
        block = result[case["attack"]]
        out.append({"role": "researcher", "id": case["id"], "want": case["expect_verdict"],
                    "got": block["verdict"], "ok": block["verdict"] == case["expect_verdict"],
                    "why": case["why"], "detail": block.get("reading", "")[:120]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--role", choices=["explorer", "generator", "researcher"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        spec = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
        classes = bl.load_table("claim_classes.json")["classes"]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    root = Path(tempfile.mkdtemp(prefix="roleevals_"))
    metadata_fixtures(root)
    results: list[dict] = []
    if args.role in (None, "explorer"):
        results += run_explorer(spec["explorer"], root, classes)
    if args.role in (None, "generator"):
        results += run_generator(spec["generator"], root)
    if args.role in (None, "researcher"):
        results += run_researcher(spec["researcher"], root)

    failures = [r for r in results if not r["ok"]]
    if args.json:
        print(json.dumps({"results": results, "failures": len(failures)}, indent=2))
        return 1 if failures else 0

    current = None
    print("\n  ROLE EVALS — the decision, not the artifact\n")
    for entry in results:
        if entry["role"] != current:
            current = entry["role"]
            print(f"  {current.upper()}")
        print(f"    {'ok  ' if entry['ok'] else 'FAIL'}  {entry['id']:<28} "
              f"want {str(entry['want']):<28} got {entry['got']}")
        print(f"            {entry['why'][:110]}")
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(results) - len(failures)}"
          f"/{len(results)} decisions correct")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
