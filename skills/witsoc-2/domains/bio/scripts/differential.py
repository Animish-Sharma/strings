#!/usr/bin/env python3
"""Per-gene differential expression, at the unit the claim is about.

The pack could compute ONE endpoint — a signature score — and test it properly.
It could not answer "which genes moved", which is the question most perturbation
analyses actually ask, and the question whose standard answer is wrong in the
one way this pack exists to catch: a cell-level test over twenty thousand genes,
FDR-corrected, reported as a finding about donors.

Correcting for multiplicity does not fix that. The correction controls error
across FEATURES; the problem is the DENOMINATOR. Twenty thousand genes tested at
the wrong unit gives twenty thousand answers to a question nobody asked, and the
false discovery rate among them is controlled exactly as advertised.

So this collapses to one value per gene per unit first, and only then tests.
With units crossed between arms it uses the paired contrast and an exact
sign-flip null, for the reason `tiers/executable.py` does: each unit is its own
control and the between-unit variation that dominates this data cancels.

## The number the ranking rests on

With six donors the smallest attainable two-sided p is 2/2^6 = 0.031, whatever
the effect. That is a fact about the design and it is reported before any gene
is ranked, because a list of "significant" genes from a design that cannot reach
significance is a list of the noisiest genes.

Usage:
    differential.py --dense <matrix.csv> --design <design.csv>
                    --unit donor --label condition --treated treated --control control
                    [--top 20] [--min-cells 3] [--json]
    differential.py --self-test

Exit: 0 computed, 1 the design cannot carry a per-gene test, 2 IO
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import biolib as bl   # noqa: E402
import counts as ct   # noqa: E402


def benjamini_hochberg(pairs: list[tuple[str, float]]) -> dict[str, float]:
    """BH across genes — the correction that IS appropriate once the denominator
    is right. It was never the wrong tool; it was the wrong tool for the wrong
    problem."""
    ordered = sorted(pairs, key=lambda kv: kv[1])
    n = len(ordered)
    out, running = {}, 1.0
    for i in range(n - 1, -1, -1):
        gene, p = ordered[i]
        running = min(running, p * n / (i + 1))
        out[gene] = round(min(1.0, running), 6)
    return out


def analyse(dense: Path, design: Path, unit_col: str, label_col: str,
            treated: str, control: str, min_cells: int = 3,
            min_counts: int = 200, min_genes: int = 30) -> dict:
    features, barcodes, cells = ct.read_dense(dense)
    prepared = ct.prepare(cells, features, "MT-", min_counts, min_genes, 1.0)
    kept, normalized = prepared["kept"], prepared["normalized"]
    if not kept:
        raise ValueError("quality control removed every cell")

    fields, rows = bl.read_csv(design)
    key = fields[0]
    meta = {r[key]: r for r in rows}
    barcode_of = {i: barcodes[i - 1] for i in kept if i - 1 < len(barcodes)}

    # gene -> (unit, arm) -> [per-cell normalized values]
    buckets: dict[int, dict[tuple[str, str], list[float]]] = {}
    seen_units: dict[str, set[str]] = {}
    for cell in kept:
        row = meta.get(barcode_of.get(cell, ""))
        if not row:
            continue
        unit, arm = (row.get(unit_col) or "").strip(), (row.get(label_col) or "").strip()
        if not unit or arm not in (treated, control):
            continue
        seen_units.setdefault(unit, set()).add(arm)
        column = normalized[cell]
        for gene_index in range(1, len(features) + 1):
            buckets.setdefault(gene_index, {}).setdefault((unit, arm), []).append(
                column.get(gene_index, 0.0))

    paired_units = sorted(u for u, arms in seen_units.items() if {treated, control} <= arms)
    if len(paired_units) < 2:
        return {"verdict": "not_computable", "paired_units": len(paired_units),
                "reading": f"{len(paired_units)} unit(s) appear in both arms. A per-gene "
                           "contrast at the unit level needs at least two, and testing at cell "
                           "level instead would answer a question about cells while the claim "
                           "is about donors"}

    floor = 2 / (2 ** len(paired_units))
    results = []
    for gene_index, per_unit in buckets.items():
        diffs = []
        for unit in paired_units:
            t_vals = per_unit.get((unit, treated)) or []
            c_vals = per_unit.get((unit, control)) or []
            if len(t_vals) < min_cells or len(c_vals) < min_cells:
                continue
            diffs.append(bl.mean(t_vals) - bl.mean(c_vals))
        if len(diffs) < 2:
            continue
        null = bl.sign_flip_p(diffs)
        results.append({"gene": features[gene_index - 1],
                        "log_fold_change": round(bl.mean(diffs), 5),
                        "units": len(diffs), "p_value": round(null["p_value"], 6)})

    fdr = benjamini_hochberg([(r["gene"], r["p_value"]) for r in results])
    for r in results:
        r["q_value"] = fdr[r["gene"]]
    results.sort(key=lambda r: (r["p_value"], -abs(r["log_fold_change"])))
    significant = [r for r in results if r["q_value"] <= 0.05]

    # Discreteness, stated rather than discovered by an empty result. A sign flip
    # over n units can only produce p in multiples of 2/2^n, so about G/2^(n-1)
    # of G null genes reach the floor BY CHANCE — and once many genes tie at the
    # floor, BH cannot push any of them below it. At six units that is roughly
    # two null genes in sixty, and no gene of any effect size can pass FDR 0.05.
    #
    # Returning an empty list here without saying why reads as "nothing moved",
    # which is the opposite of what happened: the design cannot answer the
    # question at this scale, and the effect sizes are still worth ranking.
    expected_ties = len(results) * floor
    fdr_available = (floor * len(results)) <= 0.05 or expected_ties < 1
    discreteness = (
        f"a sign flip over {len(paired_units)} units yields p only in multiples of "
        f"{floor:.4f}, so about {expected_ties:.1f} of {len(results)} genes reach that floor by "
        "chance alone"
        + ("" if fdr_available else
           ". FDR discovery is NOT available at this unit count: no gene of any effect size can "
           "pass q<=0.05, and the ranking below is a SCREEN by effect, not a list of findings"))

    return {"verdict": "computed", "design": "paired" if paired_units else "between",
            "fdr_available": fdr_available, "discreteness": discreteness,
            "paired_units": len(paired_units), "genes_tested": len(results),
            "smallest_attainable_p": round(floor, 6),
            "significant_at_q05": len(significant), "results": results,
            "reading": (f"{len(results)} gene(s) tested at the {unit_col} level over "
                        f"{len(paired_units)} paired unit(s); {len(significant)} pass FDR 0.05. "
                        f"The smallest two-sided p reachable here is {floor:.4f} — a fact about "
                        "the design, stated before any gene is ranked"
                        + ("" if floor <= 0.05 else
                           ", and it is ABOVE 0.05, so nothing can be significant and a list of "
                           "hits here would be a list of the noisiest genes"))}


def self_test() -> int:
    import random
    import tempfile
    cases, failures = [], 0
    rng = random.Random(7)
    root = Path(tempfile.mkdtemp(prefix="de_"))
    genes = [f"UP{i:02d}" for i in range(5)] + [f"NULL{i:03d}" for i in range(60)]

    cells, rows = [], []
    for d in range(6):
        base = rng.uniform(0.9, 1.2)
        for arm in ("control", "treated"):
            for k in range(10):
                bc = f"D{d}_{arm}_{k}"
                vec = []
                for g in genes:
                    lam = 8.0 * base * (1.8 if (g.startswith("UP") and arm == "treated") else 1.0)
                    vec.append(max(0, int(rng.gauss(lam, 1.5))))
                cells.append((bc, vec))
                rows.append({"cell_barcode": bc, "condition": arm, "donor": f"D{d}"})

    matrix = root / "m.csv"
    matrix.write_text("gene," + ",".join(b for b, _ in cells) + "\n" + "\n".join(
        g + "," + ",".join(str(c[1][i]) for c in cells) for i, g in enumerate(genes)) + "\n")
    design = root / "d.csv"
    design.write_text("cell_barcode,condition,donor\n" + "\n".join(
        f"{r['cell_barcode']},{r['condition']},{r['donor']}" for r in rows) + "\n")

    out = analyse(matrix, design, "donor", "condition", "treated", "control",
                  min_cells=3, min_counts=50, min_genes=5)
    top5 = {r["gene"] for r in sorted(out["results"],
                                      key=lambda r: -abs(r["log_fold_change"]))[:5]}
    cases.append(("the genes that actually moved rank top by effect",
                  top5 == {f"UP{i:02d}" for i in range(5)}, f"top five by |lfc|: {sorted(top5)}"))
    cases.append(("and no null gene outranks them",
                  all(not g.startswith("NULL") for g in top5),
                  "the effect ranking is the part this design can support"))
    cases.append(("FDR unavailability is STATED, not left as an empty result",
                  out["fdr_available"] is False and "NOT available" in out["discreteness"],
                  out["discreteness"][:150]))
    cases.append(("the design's floor is reported before any ranking",
                  out["smallest_attainable_p"] == 2 / (2 ** 6),
                  f"smallest attainable p {out['smallest_attainable_p']}"))
    cases.append(("the contrast is PAIRED, because every donor is in both arms",
                  out["design"] == "paired" and out["paired_units"] == 6,
                  f"{out['paired_units']} paired unit(s)"))

    # A design with one donor per arm cannot carry a unit-level per-gene test.
    nested = root / "nested.csv"
    nested.write_text("cell_barcode,condition,donor\n" + "\n".join(
        f"{r['cell_barcode']},{r['condition']},"
        f"{'D0' if r['condition'] == 'control' else 'D1'}" for r in rows) + "\n")
    out2 = analyse(matrix, nested, "donor", "condition", "treated", "control",
                   min_cells=3, min_counts=50, min_genes=5)
    cases.append(("a design with no crossed unit is refused, not tested at cell level",
                  out2["verdict"] == "not_computable", out2["reading"][:130]))

    print("\n  DIFFERENTIAL SELF-TEST — one value per gene per unit, then test\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {str(note)[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dense"); ap.add_argument("--design")
    ap.add_argument("--unit", default="donor"); ap.add_argument("--label", default="condition")
    ap.add_argument("--treated", default="treated"); ap.add_argument("--control", default="control")
    ap.add_argument("--min-cells", type=int, default=3)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--json", action="store_true"); ap.add_argument("--self-test",
                                                                    action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not (args.dense and args.design):
        ap.error("--dense and --design are required (or --self-test)")
    try:
        out = analyse(Path(args.dense), Path(args.design), args.unit, args.label,
                      args.treated, args.control, args.min_cells)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(out, indent=2))
        return 0 if out["verdict"] == "computed" else 1
    print(f"DIFFERENTIAL: {out['verdict']}")
    print(f"  {out['reading']}")
    for r in out.get("results", [])[:args.top]:
        print(f"  {r['gene']:<14} lfc {r['log_fold_change']:+.4f}  p {r['p_value']:.4f}  "
              f"q {r['q_value']:.4f}  ({r['units']} units)")
    return 0 if out["verdict"] == "computed" else 1


if __name__ == "__main__":
    sys.exit(main())
