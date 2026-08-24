#!/usr/bin/env python3
"""Counts — compute the endpoint instead of accepting it.

Everything else in this pack audits what happens AFTER a number exists: which
unit it was computed at, whether the design can carry it, whether it survives
permutation. The number itself arrived in a column and was taken on faith.

That is a real hole and the pack's own doctrine names it: the executable tier
"ignores reported numbers" — it ignores reported STATISTICS and trusts the
reported ENDPOINT, which sits upstream of every check. So this reads the counts
and computes the endpoint, and records exactly how, so the choices become part of
what the claim freezes rather than part of what nobody wrote down.

Four steps, each one a decision someone would otherwise make silently:

1. **QC per cell** — total counts, genes detected, and the fraction from a named
   gene set (mitochondrial by convention). Cells are filtered on stated
   thresholds, and the number removed is reported: a filter that drops half the
   data and says nothing is the most consequential silent step in the pipeline.
2. **Normalization** — counts per 10,000, then log1p. Stated, because "the same
   dataset" at two normalizations is two datasets.
3. **Signature score** — the mean normalized expression of a named gene set,
   minus the mean of a size-matched background set drawn deterministically from
   comparable-expression genes. Without the background the score is mostly a
   measure of how deeply that cell was sequenced.
4. **Emit a metadata table** carrying the score alongside the design columns, so
   the existing tiers consume it exactly as before — and now what they consume is
   something this pack computed and can be asked to recompute.

Standard library only. A 500,000-nonzero matrix streams in under a second; the
sizes where that stops being true are the sizes where a count matrix should not
be in a CSV either.

Formats: MatrixMarket triples (`.mtx` plus barcodes and features), or a dense
CSV with genes as rows and cells as columns.

Usage:
    counts.py --mtx <matrix.mtx> --features <features.tsv> --barcodes <barcodes.tsv>
              --signature <genes.txt> --design <design.csv> --out <metadata.csv>
    counts.py --dense <genes_by_cells.csv> --signature <genes.txt>
              --design <design.csv> --out <metadata.csv>
    counts.py --self-test

Exit: 0 written, 1 QC removed everything or the signature is absent, 2 usage/IO
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import biolib as bl  # noqa: E402

DEFAULT_MIN_COUNTS = 500
DEFAULT_MIN_GENES = 200
DEFAULT_MAX_MITO = 0.20
BACKGROUND_MULTIPLE = 5


def read_mtx(path: Path) -> tuple[int, int, dict[int, dict[int, float]]]:
    """Stream MatrixMarket triples into per-cell sparse columns."""
    cells: dict[int, dict[int, float]] = {}
    genes = ncells = 0
    with path.open(encoding="utf-8") as handle:
        header_seen = False
        for line in handle:
            if line.startswith("%"):
                continue
            parts = line.split()
            if not header_seen:
                genes, ncells = int(parts[0]), int(parts[1])
                header_seen = True
                continue
            gene, cell, value = int(parts[0]), int(parts[1]), float(parts[2])
            cells.setdefault(cell, {})[gene] = value
    return genes, ncells, cells


def read_dense(path: Path) -> tuple[list[str], list[str], dict[int, dict[int, float]]]:
    fields, rows = bl.read_csv(path)
    barcodes = fields[1:]
    features = []
    cells: dict[int, dict[int, float]] = {index + 1: {} for index in range(len(barcodes))}
    for gene_index, row in enumerate(rows, start=1):
        features.append(row[fields[0]])
        for cell_index, barcode in enumerate(barcodes, start=1):
            try:
                value = float(row[barcode])
            except (KeyError, ValueError):
                continue
            if value:
                cells[cell_index][gene_index] = value
    return features, barcodes, cells


def qc(cells: dict[int, dict[int, float]], features: list[str],
       mito_prefix: str) -> dict[int, dict]:
    mito = {index for index, name in enumerate(features, start=1)
            if name.upper().startswith(mito_prefix)}
    out = {}
    for cell, column in cells.items():
        total = sum(column.values())
        out[cell] = {
            "total_counts": total,
            "genes_detected": len(column),
            "mito_fraction": (sum(v for g, v in column.items() if g in mito) / total
                              if total else 0.0),
        }
    return out


def normalize(column: dict[int, float], total: float) -> dict[int, float]:
    """Counts per ten thousand, then log1p. Both stated, because 'the same
    dataset' at two normalizations is two datasets."""
    if not total:
        return {}
    scale = 10_000.0 / total
    return {gene: math.log1p(value * scale) for gene, value in column.items()}


def background_for(signature: set[int], expression_rank: list[int],
                   multiple: int) -> set[int]:
    """A size-matched background of comparable-expression genes.

    Deterministic: genes are ranked by mean expression once, and for each
    signature gene the nearest unused neighbours in that ranking are taken. A
    random background makes the score irreproducible; a background ignoring
    expression level makes the score mostly a measure of sequencing depth, which
    is the artifact the whole control exists to remove.
    """
    position = {gene: index for index, gene in enumerate(expression_rank)}
    chosen: set[int] = set()
    for gene in signature:
        centre = position.get(gene)
        if centre is None:
            continue
        offset = 1
        picked = 0
        while picked < multiple and offset < len(expression_rank):
            for candidate in (expression_rank[max(0, centre - offset)],
                              expression_rank[min(len(expression_rank) - 1, centre + offset)]):
                if candidate not in signature and candidate not in chosen:
                    chosen.add(candidate)
                    picked += 1
                    if picked >= multiple:
                        break
            offset += 1
    return chosen


def prepare(cells: dict[int, dict[int, float]], features: list[str], mito_prefix: str,
            min_counts: int, min_genes: int, max_mito: float) -> dict:
    """QC, normalize, and rank genes by mean expression — the shared preamble.

    Every consumer of this matrix goes through here, so the QC thresholds and the
    normalization are applied once. A diagnostic that re-derived them would be
    auditing a different dataset than the one the endpoint came from, which is
    exactly the kind of quiet divergence this pack exists to catch.
    """
    metrics = qc(cells, features, mito_prefix)
    kept, dropped = [], {"low_counts": 0, "few_genes": 0, "high_mito": 0}
    for cell, m in metrics.items():
        if m["total_counts"] < min_counts:
            dropped["low_counts"] += 1
        elif m["genes_detected"] < min_genes:
            dropped["few_genes"] += 1
        elif m["mito_fraction"] > max_mito:
            dropped["high_mito"] += 1
        else:
            kept.append(cell)
    normalized = {cell: normalize(cells[cell], metrics[cell]["total_counts"]) for cell in kept}
    totals: dict[int, float] = {}
    for column in normalized.values():
        for gene, value in column.items():
            totals[gene] = totals.get(gene, 0.0) + value
    ranked = sorted(totals, key=lambda g: totals[g])
    return {"metrics": metrics, "kept": kept, "dropped": dropped,
            "normalized": normalized, "ranked": ranked}


def score_set(normalized: dict[int, dict[int, float]], kept: list[int], indices: set[int],
              ranked: list[int], multiple: int = BACKGROUND_MULTIPLE) -> tuple[dict, set]:
    """Expression-matched score for one gene set, per cell.

    THE one definition. `counts.py` computes the endpoint with it and
    `expression_diagnostics.py` scores the generic signatures with it, so a
    comparison between the claimed signature and a stress signature is a
    comparison between two numbers built the same way. Two definitions of a
    score is two endpoints, and the second one is always the flattering one.
    """
    background = background_for(indices, ranked, multiple)
    scores = {}
    for cell in kept:
        column = normalized[cell]
        sig = bl.mean([column.get(g, 0.0) for g in indices])
        bg = bl.mean([column.get(g, 0.0) for g in background]) if background else 0.0
        scores[cell] = sig - bg
    return scores, background


def resolve_genes(features: list[str], wanted: set[str]) -> tuple[set[int], list[str]]:
    """Gene names to matrix row indices, case-insensitively. Returns what was
    found and what was not; an unreported miss turns a real signature into a
    small score rather than into an error."""
    index_of = {name.upper(): index for index, name in enumerate(features, start=1)}
    found = {index_of[g] for g in wanted if g in index_of}
    missing = sorted(wanted - set(index_of))
    return found, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mtx"); ap.add_argument("--features"); ap.add_argument("--barcodes")
    ap.add_argument("--dense")
    ap.add_argument("--signature")
    ap.add_argument("--design", help="CSV keyed by barcode carrying the design columns")
    ap.add_argument("--out")
    ap.add_argument("--min-counts", type=int, default=DEFAULT_MIN_COUNTS)
    ap.add_argument("--min-genes", type=int, default=DEFAULT_MIN_GENES)
    ap.add_argument("--max-mito", type=float, default=DEFAULT_MAX_MITO)
    ap.add_argument("--mito-prefix", default="MT-")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.dense or args.mtx) or not args.signature:
        ap.error("supply --dense or --mtx, and --signature")

    try:
        if args.dense:
            features, barcodes, cells = read_dense(Path(args.dense))
        else:
            if not (args.features and args.barcodes):
                ap.error("--mtx needs --features and --barcodes")
            features = [l.split("\t")[0].strip() for l in
                        Path(args.features).read_text(encoding="utf-8").splitlines() if l.strip()]
            barcodes = [l.strip() for l in
                        Path(args.barcodes).read_text(encoding="utf-8").splitlines() if l.strip()]
            _, _, cells = read_mtx(Path(args.mtx))
        wanted = {l.strip().upper() for l in
                  Path(args.signature).read_text(encoding="utf-8").splitlines() if l.strip()}
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    signature, missing = resolve_genes(features, wanted)
    if not signature:
        print(json.dumps({"error": "no signature gene is present in this matrix",
                          "missing": missing[:20],
                          "reading": "a signature score over zero genes is not a small score, "
                                     "it is no score. Check the gene identifiers match"},
                         indent=2), file=sys.stderr)
        return 1

    prepared = prepare(cells, features, args.mito_prefix,
                       args.min_counts, args.min_genes, args.max_mito)
    metrics, kept, dropped = prepared["metrics"], prepared["kept"], prepared["dropped"]

    if not kept:
        print(json.dumps({"error": "quality control removed every cell", "dropped": dropped,
                          "reading": "thresholds that drop everything are a finding about the "
                                     "thresholds or about the data, and either way not a result"},
                         indent=2), file=sys.stderr)
        return 1

    normalized, ranked = prepared["normalized"], prepared["ranked"]
    scores, background = score_set(normalized, kept, signature, ranked)

    design_rows = {}
    design_fields: list[str] = []
    if args.design:
        design_fields, rows = bl.read_csv(Path(args.design))
        key = design_fields[0]
        design_rows = {row[key]: row for row in rows}

    header = ["cell_barcode", "signature_score", "total_counts", "genes_detected",
              "mito_fraction"] + [f for f in design_fields[1:]]
    lines = [",".join(header)]
    written = 0
    for cell in kept:
        barcode = barcodes[cell - 1] if cell - 1 < len(barcodes) else f"cell_{cell}"
        extra = design_rows.get(barcode, {})
        if args.design and not extra:
            continue
        lines.append(",".join([
            barcode, f"{scores[cell]:.6f}", str(metrics[cell]['total_counts']),
            str(metrics[cell]['genes_detected']), f"{metrics[cell]['mito_fraction']:.4f}",
        ] + [str(extra.get(f, "")) for f in design_fields[1:]]))
        written += 1

    provenance = {
        "computed_by": "scripts/counts.py",
        "cells_in": len(metrics), "cells_kept": len(kept), "cells_written": written,
        "dropped": dropped,
        "qc_thresholds": {"min_counts": args.min_counts, "min_genes": args.min_genes,
                          "max_mito_fraction": args.max_mito, "mito_prefix": args.mito_prefix},
        "normalization": "counts per 10,000 then log1p",
        "signature_genes_found": len(signature),
        "signature_genes_missing": missing[:20],
        "background_genes": len(background),
        "background_rule": (f"{BACKGROUND_MULTIPLE} expression-matched genes per signature gene, "
                            "chosen deterministically by nearest rank"),
        "endpoint_column": "signature_score",
        "freeze_this": ("these choices belong in the claim's frozen_conditions. A result computed "
                        "under different thresholds or a different normalization is a result "
                        "about different data"),
    }

    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        Path(str(args.out) + ".provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(provenance, indent=2))
    else:
        print(f"COUNTS: {written} cell(s) written of {len(metrics)} read")
        print(f"  dropped           {dropped}")
        print(f"  signature         {len(signature)} gene(s) found"
              + (f", {len(missing)} missing" if missing else ""))
        print(f"  background        {len(background)} expression-matched gene(s)")
        print(f"  normalization     {provenance['normalization']}")
        if args.out:
            print(f"  wrote             {args.out} (+ .provenance.json)")
        print(f"  {provenance['freeze_this']}")
    return 0


def self_test() -> int:
    """A synthetic matrix where the answer is known, and two ways of being wrong.

    The point is not that the arithmetic runs. It is that a signature genuinely
    elevated in the treated cells comes out elevated, that a depth confound alone
    does NOT produce a score difference once the background is subtracted, and
    that QC removing everything is reported rather than returning an empty
    result that reads like a null.
    """
    import random
    import tempfile

    rng = random.Random(20260821)
    failures = []
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        genes = [f"GENE{i}" for i in range(60)] + ["MT-CO1", "MT-ND1"]
        signature = genes[:8]
        (tmp / "sig.txt").write_text("\n".join(signature))

        def build(name: str, treated_lift: float, depth_confound: bool) -> Path:
            header = ["gene"] + [f"cell{i}" for i in range(40)]
            rows = []
            for gi, gene in enumerate(genes):
                row = [gene]
                for ci in range(40):
                    treated = ci < 20
                    depth = (3.0 if (treated and depth_confound) else 1.0)
                    base = rng.randrange(2, 12) * depth
                    if gene in signature and treated:
                        base *= (1.0 + treated_lift)
                    row.append(str(int(base)))
                rows.append(",".join(row))
            path = tmp / name
            path.write_text("\n".join([",".join(header)] + rows) + "\n")
            return path

        design = tmp / "design.csv"
        design.write_text("cell_barcode,condition,donor\n" + "\n".join(
            f"cell{i},{'treated' if i < 20 else 'control'},donor_{i % 4 + 1}"
            for i in range(40)) + "\n")

        def score_gap(matrix: Path) -> float:
            out = tmp / "meta.csv"
            proc = subprocess_run([sys.executable, str(HERE / "counts.py"), "--dense", str(matrix),
                                   "--signature", str(tmp / "sig.txt"), "--design", str(design),
                                   "--out", str(out), "--min-counts", "1", "--min-genes", "1"])
            if proc != 0:
                return float("nan")
            _, rows = bl.read_csv(out)
            treated = [float(r["signature_score"]) for r in rows if r["condition"] == "treated"]
            control = [float(r["signature_score"]) for r in rows if r["condition"] == "control"]
            return bl.mean(treated) - bl.mean(control)

        real = score_gap(build("real.csv", treated_lift=1.5, depth_confound=False))
        depth = score_gap(build("depth.csv", treated_lift=0.0, depth_confound=True))

        cases = [
            ("a genuinely elevated signature comes out elevated", real > 0.15,
             f"gap {real:.4f} — if this were near zero the score would be measuring nothing"),
            ("a depth confound alone does not move the score", abs(depth) < abs(real) / 2,
             f"gap {depth:.4f} against {real:.4f} — the expression-matched background is what "
             "removes it, and without it this number is mostly sequencing depth"),
        ]

        empty = tmp / "meta2.csv"
        code = subprocess_run([sys.executable, str(HERE / "counts.py"), "--dense",
                               str(tmp / "real.csv"), "--signature", str(tmp / "sig.txt"),
                               "--out", str(empty), "--min-counts", "100000"])
        cases.append(("QC removing every cell is an error, not an empty result", code == 1,
                      "an empty result reads like a null; thresholds that drop everything are a "
                      "finding about the thresholds"))

        absent = tmp / "absent.txt"
        absent.write_text("NOT_A_GENE\nALSO_NOT")
        code = subprocess_run([sys.executable, str(HERE / "counts.py"), "--dense",
                               str(tmp / "real.csv"), "--signature", str(absent)])
        cases.append(("a signature absent from the matrix is refused", code == 1,
                      "a score over zero genes is not a small score, it is no score"))

        print("Counts — the endpoint is computed, and computed correctly:\n")
        for label, ok, why in cases:
            print(f"  {'ok  ' if ok else 'MISS'}  {label}")
            print(f"          {why}")
            if not ok:
                failures.append(label)

    print("\n" + "=" * 62)
    if failures:
        print(f"  COUNTS SELF-TEST: FAIL — {len(failures)}")
        return 1
    print(f"  COUNTS SELF-TEST: PASS — {len(cases)} case(s)")
    return 0


def subprocess_run(cmd: list[str]) -> int:
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True).returncode


if __name__ == "__main__":
    sys.exit(main())
