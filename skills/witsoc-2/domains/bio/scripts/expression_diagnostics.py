#!/usr/bin/env python3
"""Expression diagnostics — the count-matrix half of the refutation catalogue.

`diagnostics.py` computes the confounders that live in the metadata table:
batch confounding, depth, unit balance. Four of Durbin's attacks need the counts
themselves, and until this existed they were prose in a doctrine file while the
gate that should have caught their absence read a sentence the author wrote:

    3. generic response    is a stress or cell-cycle signature moving as much as
                           the claimed one? Then the effect is real and not
                           specific, which is a different claim.
    4. composition         did the cells CHANGE, or did DIFFERENT CELLS ARRIVE?
                           Routinely reported as the first when it is the second.
    5. ambient and doublets  is the signal in the soup, or in cells that are two
                           cells?
    8. context reversal    does the contrast keep its sign across cell type,
                           dose, or timepoint? A reversal is a scope finding and
                           the most publishable thing this role produces.

Every score here is built by `counts.score_set` — the same expression-matched
background that computes the endpoint. That is deliberate: comparing a claimed
signature against a stress signature is only meaningful if both numbers were
made the same way, and a second scoring rule would always turn out to be the
flattering one.

What this does NOT do is decide anything it cannot compute. Ambient with no
empty droplets returns `not_computable`, not `clear`. A composition decomposition
with no cluster column returns `not_computable`, not `clear`. The blank is the
honest answer and it fails the sweep gate exactly as a missing check should,
because a diagnostic that guesses is worse than one that abstains: the guess
clears the gate.

Usage:
    expression_diagnostics.py --dense <genes_by_cells.csv> --signature <genes.txt>
        --design <design.csv> --label <col> --unit <col>
        [--cluster <col>] [--context <col>] [--treated <value>]
        [--cell-cycle <genes.txt>] [--stress <genes.txt>]
        [--emit-confounders] [--json]
    expression_diagnostics.py --self-test

Exit: 0 nothing fatal, 1 a fatal or dominant finding, 2 usage/IO
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import biolib as bl  # noqa: E402
import counts as ct  # noqa: E402

# Conventional markers. Overridable, and the defaults are recorded in the output
# so a run is reproducible without knowing what this file said on the day.
CELL_CYCLE = {"MKI67", "TOP2A", "CCNB1", "CCNA2", "CDK1", "PCNA", "MCM2", "MCM5",
              "TYMS", "RRM2", "UBE2C", "BIRC5", "AURKB", "PLK1", "CENPF"}
STRESS = {"HSPA1A", "HSPA1B", "HSPB1", "DNAJB1", "HSPH1", "JUN", "JUNB", "FOS",
          "FOSB", "EGR1", "ATF3", "IER2", "DUSP1", "NR4A1", "SOCS3"}

DOMINANT_RATIO = 1.0     # generic moves at least as much as claimed
ELEVATED_RATIO = 0.5     # generic moves at least half as much
AMBIENT_ENRICHED = 0.8   # soup as enriched for the signature as the cells are
DOUBLET_RATE = 0.10      # flagged fraction above which the rate is worth saying


def read_gene_list(path: Path) -> set[str]:
    return {line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def unit_effect(scores: dict[int, float], barcode_of: dict[int, str],
                design: dict[str, dict], label: str, unit: str,
                treated: str) -> dict:
    """Collapse to one value per experimental unit, then difference the arms.

    Cell-level differencing is available and wrong: it answers a question about
    cells when the claim is about donors. `generator.md` is blunt about this and
    the rule holds for diagnostics too — a composition finding computed at the
    wrong denominator is as misleading as an effect computed there.
    """
    per_unit: dict[tuple[str, str], list[float]] = {}
    for cell, score in scores.items():
        row = design.get(barcode_of.get(cell, ""))
        if not row:
            continue
        u, arm = (row.get(unit) or "").strip(), (row.get(label) or "").strip()
        if u and arm:
            per_unit.setdefault((arm, u), []).append(score)
    arms: dict[str, list[float]] = {}
    for (arm, _u), values in per_unit.items():
        arms.setdefault(arm, []).append(bl.mean(values))
    if treated not in arms or len(arms) < 2:
        return {"effect": None, "units": {a: len(v) for a, v in arms.items()},
                "reading": "fewer than two arms carry units; no contrast exists"}
    control = [a for a in arms if a != treated]
    effect = bl.mean(arms[treated]) - bl.mean([v for a in control for v in arms[a]])
    return {"effect": effect, "arms": sorted(arms),
            "units": {a: len(v) for a, v in arms.items()},
            "unit_means": {a: round(bl.mean(v), 6) for a, v in arms.items()}}


def generic_response(sig: dict, cc: dict, stress: dict) -> dict:
    """Attack 3. Is the claimed signature doing anything a generic one is not?"""
    claimed = sig.get("effect")
    if claimed is None:
        return {"verdict": "not_computable",
                "reading": "the claimed contrast has no unit-level effect to compare against"}
    generics = {"cell_cycle": cc.get("effect"), "stress_viability": stress.get("effect")}
    available = {k: v for k, v in generics.items() if v is not None}
    if not available:
        return {"verdict": "not_computable",
                "reading": "neither generic signature resolved in this matrix"}
    if abs(claimed) < 1e-9:
        return {"verdict": "not_computable", "generic_effects": available,
                "reading": "the claimed effect is zero; there is nothing for a generic "
                           "signature to be a fraction of"}
    ratios = {k: abs(v) / abs(claimed) for k, v in available.items()}
    worst_name = max(ratios, key=lambda k: ratios[k])
    worst = ratios[worst_name]
    if worst >= DOMINANT_RATIO:
        verdict, reading = "dominant", (
            f"the {worst_name.replace('_', ' ')} signature moves {worst:.2f}x as much as the "
            "claimed one. The response is real and it is not specific to this perturbation, "
            "which is a different claim than the one frozen")
    elif worst >= ELEVATED_RATIO:
        verdict, reading = "elevated", (
            f"the {worst_name.replace('_', ' ')} signature moves {worst:.2f}x the claimed effect. "
            "Not disqualifying and it bounds what specificity may be claimed")
    else:
        verdict, reading = "clear", (
            f"the strongest generic signature moves {worst:.2f}x the claimed effect, so the "
            "response is not merely a generic one")
    def one(name: str) -> dict:
        """Each generic signature gets its own verdict. Reporting the worst of
        them under both ids made a cell-cycle row quote a stress finding, which
        is a true sentence filed against the wrong confounder — and the sweep
        gate stores it verbatim."""
        if name not in ratios:
            return {"verdict": "not_computable",
                    "reading": f"the {name.replace('_', ' ')} gene set did not resolve in "
                               "this matrix, so it was not compared"}
        r = ratios[name]
        v = ("dominant" if r >= DOMINANT_RATIO else
             "elevated" if r >= ELEVATED_RATIO else "clear")
        text = {"dominant": (f"the {name.replace('_', ' ')} signature moves {r:.2f}x as much as "
                             "the claimed one. The response is real and it is not specific to "
                             "this perturbation, which is a different claim than the one frozen"),
                "elevated": (f"the {name.replace('_', ' ')} signature moves {r:.2f}x the claimed "
                             "effect. Not disqualifying, and it bounds what specificity may be "
                             "claimed"),
                "clear": (f"the {name.replace('_', ' ')} signature moves {r:.2f}x the claimed "
                          "effect, so the response is not merely that one")}[v]
        return {"verdict": v, "ratio": round(r, 4), "effect": round(available[name], 6),
                "reading": text}

    return {"verdict": verdict, "claimed_effect": round(claimed, 6),
            "generic_effects": {k: round(v, 6) for k, v in available.items()},
            "ratios": {k: round(v, 4) for k, v in ratios.items()},
            "per_signature": {name: one(name) for name in ("cell_cycle", "stress_viability")},
            "reading": reading}


def composition_split(scores: dict[int, float], barcode_of: dict[int, str],
                      design: dict[str, dict], label: str, cluster: str,
                      treated: str) -> dict:
    """Attack 4. Split the arm difference into composition and expression.

    Exact, with no residual:

        delta = SUM_k (p_k^T - p_k^C) * mbar_k   <- composition: which cells are here
              + SUM_k pbar_k * (m_k^T - m_k^C)   <- expression: what each is doing

    with mbar and pbar the two-arm averages. Descriptive and pooled within arm,
    so it carries no p-value and is not a test; it says which of two stories the
    same number is telling.
    """
    if not cluster:
        return {"verdict": "not_computable",
                "reading": "no cluster or cell-type column was given, so a change in which "
                           "cells are present cannot be distinguished from a change in what "
                           "they are doing. This is not a clean result, it is an unasked question"}
    buckets: dict[str, dict[str, list[float]]] = {}
    totals: dict[str, int] = {}
    for cell, score in scores.items():
        row = design.get(barcode_of.get(cell, ""))
        if not row:
            continue
        arm, k = (row.get(label) or "").strip(), (row.get(cluster) or "").strip()
        if arm and k:
            buckets.setdefault(arm, {}).setdefault(k, []).append(score)
            totals[arm] = totals.get(arm, 0) + 1
    arms = sorted(buckets)
    if treated not in buckets or len(arms) != 2:
        return {"verdict": "not_computable",
                "reading": f"need exactly two arms including {treated!r}; found {arms}"}
    control = [a for a in arms if a != treated][0]
    keys = sorted(set(buckets[treated]) | set(buckets[control]))

    comp = expr = 0.0
    per_cluster = {}
    for k in keys:
        t_vals, c_vals = buckets[treated].get(k, []), buckets[control].get(k, [])
        p_t = len(t_vals) / totals[treated] if totals.get(treated) else 0.0
        p_c = len(c_vals) / totals[control] if totals.get(control) else 0.0
        m_t = bl.mean(t_vals) if t_vals else 0.0
        m_c = bl.mean(c_vals) if c_vals else 0.0
        mbar, pbar = (m_t + m_c) / 2.0, (p_t + p_c) / 2.0
        comp += (p_t - p_c) * mbar
        expr += pbar * (m_t - m_c)
        per_cluster[k] = {"proportion": {treated: round(p_t, 4), control: round(p_c, 4)},
                          "mean_score": {treated: round(m_t, 4), control: round(m_c, 4)}}

    total = comp + expr
    share = abs(comp) / (abs(comp) + abs(expr)) if (abs(comp) + abs(expr)) > 1e-12 else 0.0
    if share > 0.5:
        verdict, reading = "composition", (
            f"{share:.0%} of the arm difference is a shift in WHICH cells are present, not in "
            "what they express. The honest statement is about cell composition; stating it as "
            "a change in expression is the substitution this check exists to catch")
    else:
        verdict, reading = "clear", (
            f"{1 - share:.0%} of the arm difference is within-cluster expression change, so the "
            "effect is not principally a composition shift")
    return {"verdict": verdict, "total_difference": round(total, 6),
            "composition_part": round(comp, 6), "expression_part": round(expr, 6),
            "composition_share": round(share, 4), "clusters": per_cluster, "reading": reading}


def ambient_and_doublets(cells: dict, metrics: dict, kept: list[int], signature: set[int],
                         min_counts: int) -> dict:
    """Attack 5. Soup and two-cells-in-one-droplet.

    The ambient profile comes from the droplets QC discarded for low counts —
    which is the one honest use for them, and they are otherwise thrown away.
    If the soup is as enriched for the signature as the cells are, the signature
    may be measuring what leaked rather than what was expressed.
    """
    ambient_cells = [c for c, m in metrics.items() if m["total_counts"] < min_counts]
    out: dict = {"ambient_droplets": len(ambient_cells)}

    if not ambient_cells:
        out["ambient"] = {"verdict": "not_computable",
                          "reading": "no droplet fell below the count threshold, so there is no "
                                     "empty-droplet population to estimate the soup from. Ambient "
                                     "contamination was NOT ruled out; it was not measurable here"}
    else:
        def share(pool):
            sig_sum = total = 0.0
            for c in pool:
                for g, v in cells[c].items():
                    total += v
                    if g in signature:
                        sig_sum += v
            return (sig_sum / total) if total else 0.0
        soup, real = share(ambient_cells), share(kept)
        ratio = (soup / real) if real else 0.0
        verdict = "elevated" if ratio >= AMBIENT_ENRICHED else "clear"
        out["ambient"] = {
            "verdict": verdict,
            "signature_share_in_soup": round(soup, 6),
            "signature_share_in_cells": round(real, 6),
            "ratio": round(ratio, 4),
            "reading": (f"the discarded droplets are {ratio:.2f}x as enriched for the signature as "
                        "the cells are, so part of the per-cell signal may be ambient RNA rather "
                        "than expression" if verdict == "elevated" else
                        f"the soup carries {ratio:.2f}x the signature share of the cells, so the "
                        "signal is not principally ambient")}

    counts_kept = sorted(metrics[c]["total_counts"] for c in kept)
    genes_kept = sorted(metrics[c]["genes_detected"] for c in kept)
    if not counts_kept:
        out["doublets"] = {"verdict": "not_computable", "reading": "no cell survived QC"}
        return out
    med_counts = counts_kept[len(counts_kept) // 2]
    med_genes = genes_kept[len(genes_kept) // 2]
    flagged = [c for c in kept
               if metrics[c]["total_counts"] > 2 * med_counts
               and metrics[c]["genes_detected"] > 1.5 * med_genes]
    rate = len(flagged) / len(kept)
    verdict = "elevated" if rate > DOUBLET_RATE else "clear"
    out["doublets"] = {
        "verdict": verdict, "flagged": len(flagged), "cells": len(kept), "rate": round(rate, 4),
        "median_counts": med_counts, "median_genes": med_genes,
        "method": ("counts above 2x median AND genes above 1.5x median — a screen, not a caller. "
                   "It bounds the doublet rate rather than identifying doublets, and a dedicated "
                   "caller should replace it where the rate matters to the claim"),
        "reading": (f"{rate:.1%} of surviving cells carry both the counts and the complexity of "
                    "two cells, which is high enough to move a per-cell mean"
                    if verdict == "elevated" else
                    f"{rate:.1%} of cells look like possible multiplets, within the usual range")}
    return out


def context_reversal(scores: dict[int, float], barcode_of: dict[int, str], design: dict[str, dict],
                     label: str, unit: str, context: str, treated: str) -> dict:
    """Attack 8. Does the contrast keep its sign across context?"""
    if not context:
        return {"verdict": "not_computable",
                "reading": "no context column was given. An effect measured in one context says "
                           "nothing about another, and the report's scope must say so"}
    levels: dict[str, dict[int, float]] = {}
    for cell, score in scores.items():
        row = design.get(barcode_of.get(cell, ""))
        if not row:
            continue
        level = (row.get(context) or "").strip()
        if level:
            levels.setdefault(level, {})[cell] = score
    per_level = {}
    for level, subset in sorted(levels.items()):
        per_level[level] = unit_effect(subset, barcode_of, design, label, unit, treated)
    effects = {k: v["effect"] for k, v in per_level.items() if v.get("effect") is not None}
    if len(effects) < 2:
        return {"verdict": "not_computable", "levels": list(levels),
                "per_level": per_level,
                "reading": "fewer than two context levels carry a computable contrast"}
    signs = {k: (1 if v > 0 else -1) for k, v in effects.items() if abs(v) > 1e-9}
    if len(set(signs.values())) > 1:
        verdict, reading = "reversal", (
            "the contrast changes sign across context levels "
            f"({ {k: round(v, 4) for k, v in effects.items()} }). The effect is context-specific; "
            "a claim stated without the context is not supported, and the reversal is itself the "
            "finding")
    else:
        verdict, reading = "clear", (
            "the contrast keeps its sign across every context level measured, which bounds the "
            "claim to those levels and no further")
    return {"verdict": verdict, "effects": {k: round(v, 6) for k, v in effects.items()},
            "per_level": per_level, "reading": reading}


def analyse(dense: Path, signature_path: Path, design_path: Path, label: str, unit: str,
            cluster: str = "", context: str = "", treated: str = "",
            cell_cycle: set[str] | None = None, stress: set[str] | None = None,
            min_counts: int = ct.DEFAULT_MIN_COUNTS, min_genes: int = ct.DEFAULT_MIN_GENES,
            max_mito: float = ct.DEFAULT_MAX_MITO, mito_prefix: str = "MT-") -> dict:
    features, barcodes, cells = ct.read_dense(dense)
    wanted = read_gene_list(signature_path)
    signature, missing = ct.resolve_genes(features, wanted)
    if not signature:
        raise ValueError("no signature gene is present in this matrix; a score over zero genes "
                         "is not a small score, it is no score")

    prepared = ct.prepare(cells, features, mito_prefix, min_counts, min_genes, max_mito)
    metrics, kept = prepared["metrics"], prepared["kept"]
    if not kept:
        raise ValueError("quality control removed every cell")
    normalized, ranked = prepared["normalized"], prepared["ranked"]

    design_fields, rows = bl.read_csv(design_path)
    key = design_fields[0]
    design = {row[key]: row for row in rows}
    barcode_of = {index: barcodes[index - 1] for index in kept if index - 1 < len(barcodes)}

    arms = sorted({(design.get(b, {}).get(label) or "").strip()
                   for b in barcode_of.values()} - {""})
    if not treated:
        controlish = {"control", "untreated", "non_targeting", "non-targeting", "nt",
                      "dmso", "vehicle", "ctrl", "wt"}
        candidates = [a for a in arms if a.lower() not in controlish]
        treated = candidates[0] if len(candidates) == 1 else (arms[-1] if arms else "")

    sig_scores, _ = ct.score_set(normalized, kept, signature, ranked)
    cc_idx, cc_missing = ct.resolve_genes(features, cell_cycle or CELL_CYCLE)
    st_idx, st_missing = ct.resolve_genes(features, stress or STRESS)
    cc_scores = ct.score_set(normalized, kept, cc_idx, ranked)[0] if cc_idx else {}
    st_scores = ct.score_set(normalized, kept, st_idx, ranked)[0] if st_idx else {}

    sig_eff = unit_effect(sig_scores, barcode_of, design, label, unit, treated)
    cc_eff = (unit_effect(cc_scores, barcode_of, design, label, unit, treated)
              if cc_scores else {"effect": None})
    st_eff = (unit_effect(st_scores, barcode_of, design, label, unit, treated)
              if st_scores else {"effect": None})

    ad = ambient_and_doublets(cells, metrics, kept, signature, min_counts)
    return {
        "computed_by": "scripts/expression_diagnostics.py",
        "matrix": dense.name, "cells_kept": len(kept), "cells_read": len(metrics),
        "treated_arm": treated, "arms": arms,
        "signature_genes_found": len(signature), "signature_genes_missing": missing[:20],
        "generic_sets": {"cell_cycle": {"found": len(cc_idx), "missing": len(cc_missing)},
                         "stress_viability": {"found": len(st_idx), "missing": len(st_missing)}},
        "claimed_effect": sig_eff,
        "generic_response": generic_response(sig_eff, cc_eff, st_eff),
        "composition": composition_split(sig_scores, barcode_of, design, label, cluster, treated),
        "ambient_rna": ad["ambient"], "moi_doublets": ad["doublets"],
        "ambient_droplets": ad["ambient_droplets"],
        "context_reversal": context_reversal(sig_scores, barcode_of, design, label, unit,
                                             context, treated),
    }


def to_confounder_rows(result: dict) -> list[dict]:
    """Rows for a bundle's `confounders_addressed`, carrying `computed_by`.

    The gate reads this field and refuses to let an author's sentence override a
    computed verdict. That is the whole point: every other line in that list is
    the producer grading their own work.
    """
    gr = result["generic_response"]
    rows = []
    per = gr.get("per_signature") or {}
    for cid in ("cell_cycle", "stress_viability"):
        block = per.get(cid) or {"verdict": gr["verdict"], "reading": gr.get("reading", "")}
        rows.append({"id": cid, "verdict": block["verdict"],
                     "result": block.get("reading", "")[:160],
                     "computed_by": result["computed_by"],
                     "evidence": {"ratio": block.get("ratio"),
                                  "claimed_effect": gr.get("claimed_effect")}})
    for cid, block in (("composition", result["composition"]),
                       ("ambient_rna", result["ambient_rna"]),
                       ("moi_doublets", result["moi_doublets"]),
                       ("context_reversal", result["context_reversal"])):
        rows.append({"id": cid, "verdict": block["verdict"],
                     "result": block.get("reading", "")[:160],
                     "computed_by": result["computed_by"],
                     "evidence": {k: v for k, v in block.items()
                                  if k not in {"reading", "verdict", "per_level", "clusters"}}})
    return rows


# ---------------------------------------------------------------- self-test

def _write_case(root: Path, name: str, spec) -> tuple[Path, Path, Path]:
    """Build one dense matrix + design + signature file from a spec function."""
    genes, cells, design_rows = spec()
    matrix = root / f"{name}_matrix.csv"
    barcodes = [c[0] for c in cells]
    lines = ["gene," + ",".join(barcodes)]
    for gi, gene in enumerate(genes):
        lines.append(gene + "," + ",".join(str(c[1][gi]) for c in cells))
    matrix.write_text("\n".join(lines) + "\n", encoding="utf-8")
    design = root / f"{name}_design.csv"
    fields = list(design_rows[0].keys())
    design.write_text("\n".join([",".join(fields)] +
                                [",".join(str(r[f]) for f in fields) for r in design_rows]) + "\n",
                      encoding="utf-8")
    sig = root / f"{name}_signature.txt"
    sig.write_text("\n".join(g for g in genes if g.startswith("SIG")) + "\n", encoding="utf-8")
    return matrix, design, sig


def _base_genes(n_filler: int = 260) -> list[str]:
    return (["SIG%02d" % i for i in range(10)] + sorted(CELL_CYCLE) + sorted(STRESS)
            + ["FILL%03d" % i for i in range(n_filler)])


def _cell(genes, *, sig=1.0, cc=1.0, stress=1.0, filler=1.0, scale=1.0, detected=0.5, seed=0):
    """A deterministic count vector.

    The filler block carries the depth AND the sparsity: a real cell detects a
    fraction of the transcriptome, which is what makes `genes_detected` a signal
    at all. The first version filled every gene in every cell, so a droplet with
    twice the counts still detected exactly as many genes and the doublet screen
    had nothing to look at — the fixture was flat where the data is not.
    """
    import random
    rng = random.Random(seed)
    vector = []
    for g in genes:
        if g.startswith("SIG"):
            base = 6.0 * sig
        elif g in CELL_CYCLE:
            base = 6.0 * cc
        elif g in STRESS:
            base = 6.0 * stress
        else:
            base = 6.0 * filler if rng.random() < detected else 0.0
        vector.append(max(0, int(round(base * scale + (rng.uniform(-0.5, 0.5) if base else 0.0)))))
    return vector


def self_test() -> int:
    """Two-sided on every detector: each must fire on a matrix built to trip it
    and stay silent on one built not to. A detector only tested on the positive
    is indistinguishable from a detector that always fires."""
    import random
    cases, failures = [], 0
    root = Path(tempfile.mkdtemp(prefix="exprdiag_"))
    genes = _base_genes()

    def build(name, *, sig_t, cc_t, stress_t, clusters=None, contexts=None,
              n_units=6, n_cells=12, ambient=0, doublets=0.0):
        cells, rows = [], []
        seed = 0
        for u in range(n_units):
            # Arm alternates by unit and context blocks two units at a time, so
            # every context level carries BOTH arms. Keying context off `u % 2`
            # as the first version did put every treated unit in context A and
            # every control unit in B, leaving no contrast inside either level.
            arm = "treated" if u % 2 == 0 else "control"
            for c in range(n_cells):
                seed += 1
                bc = f"{name}_u{u}_c{c}"
                t = arm == "treated"
                ctx = (contexts[(u // 2) % len(contexts)] if contexts else "")
                s = sig_t(t, ctx)
                k = (clusters(t, c) if clusters else "")
                if k == "K1":
                    s = s * 2.0          # the cluster itself carries a score level,
                                         # which is what makes a proportion shift move
                                         # the arm mean at all
                scale, detected = 1.0, 0.5
                if doublets and c < int(n_cells * doublets):
                    scale, detected = 3.0, 0.95
                cells.append((bc, _cell(genes, sig=s, cc=cc_t(t), stress=stress_t(t),
                                        scale=scale, detected=detected, seed=seed)))
                row = {"cell_barcode": bc, "condition": arm, "donor": f"D{u}"}
                if clusters:
                    row["cluster"] = k
                if contexts:
                    row["context"] = ctx
                rows.append(row)
        for a in range(ambient):
            seed += 1
            bc = f"{name}_amb{a}"
            cells.append((bc, _cell(genes, sig=4.0, filler=0.02, scale=0.02,
                                    detected=0.5, seed=seed)))
            row = {"cell_barcode": bc, "condition": "control", "donor": "D1"}
            if clusters:
                row["cluster"] = "K0"
            if contexts:
                row["context"] = contexts[0]
            rows.append(row)
        return _write_case(root, name, lambda: (genes, cells, rows))

    def run(name, *, cluster="", context="", **kw):
        m, d, s = build(name, **kw)
        return analyse(m, s, d, "condition", "donor", cluster=cluster, context=context,
                       treated="treated", min_counts=200, min_genes=50)

    # 1/2 generic response, both sides
    r = run("generic_fires", sig_t=lambda t, c: 1.2 if t else 1.0,
            cc_t=lambda t: 1.0, stress_t=lambda t: 2.0 if t else 1.0)
    cases.append(("a stress signature that moves more than the claimed one is dominant",
                  r["generic_response"]["verdict"] == "dominant",
                  r["generic_response"]["reading"]))
    r = run("generic_silent", sig_t=lambda t, c: 2.5 if t else 1.0,
            cc_t=lambda t: 1.0, stress_t=lambda t: 1.0)
    cases.append(("a specific response leaves the generic signatures flat",
                  r["generic_response"]["verdict"] == "clear",
                  r["generic_response"]["reading"]))

    # 3/4 composition, both sides
    rng = random.Random(11)
    r = run("comp_fires", cluster="cluster",
            sig_t=lambda t, c: 1.0, cc_t=lambda t: 1.0, stress_t=lambda t: 1.0,
            clusters=lambda t, c: ("K1" if (c < 9 if t else c < 3) else "K0"))
    cases.append(("a pure proportion shift is called composition, not expression",
                  r["composition"]["verdict"] == "composition",
                  f"composition part {r['composition']['composition_part']} vs expression part "
                  f"{r['composition']['expression_part']} — {r['composition']['reading'][:70]}"))
    r2 = run("comp_expr", cluster="cluster",
             sig_t=lambda t, c: 2.5 if t else 1.0, cc_t=lambda t: 1.0, stress_t=lambda t: 1.0,
             clusters=lambda t, c: "K1" if c < 6 else "K0")
    cases.append(("a within-cluster expression change is not called composition",
                  r2["composition"]["verdict"] == "clear", r2["composition"]["reading"]))
    r3 = run("comp_absent", sig_t=lambda t, c: 2.0 if t else 1.0,
             cc_t=lambda t: 1.0, stress_t=lambda t: 1.0)
    cases.append(("no cluster column returns not_computable, never clear",
                  r3["composition"]["verdict"] == "not_computable",
                  r3["composition"]["reading"]))

    # 5/6 context reversal, both sides
    r = run("ctx_fires", context="context", contexts=["A", "B"],
            sig_t=lambda t, c: (2.5 if t else 1.0) if c == "A" else (1.0 if t else 2.5),
            cc_t=lambda t: 1.0, stress_t=lambda t: 1.0)
    cases.append(("an effect that flips sign across context is a reversal",
                  r["context_reversal"]["verdict"] == "reversal",
                  r["context_reversal"]["reading"]))
    r = run("ctx_silent", context="context", contexts=["A", "B"],
            sig_t=lambda t, c: 2.5 if t else 1.0, cc_t=lambda t: 1.0, stress_t=lambda t: 1.0)
    cases.append(("a consistent effect keeps its sign across context",
                  r["context_reversal"]["verdict"] == "clear",
                  r["context_reversal"]["reading"]))

    # 7/8 ambient, both sides
    r = run("amb_fires", sig_t=lambda t, c: 1.5 if t else 1.0,
            cc_t=lambda t: 1.0, stress_t=lambda t: 1.0, ambient=40)
    cases.append(("soup enriched for the signature is flagged",
                  r["ambient_rna"]["verdict"] == "elevated", r["ambient_rna"]["reading"]))
    r = run("amb_absent", sig_t=lambda t, c: 1.5 if t else 1.0,
            cc_t=lambda t: 1.0, stress_t=lambda t: 1.0, ambient=0)
    cases.append(("no empty droplets returns not_computable, never clear",
                  r["ambient_rna"]["verdict"] == "not_computable", r["ambient_rna"]["reading"]))

    # 9/10 doublets, both sides
    r = run("dbl_fires", sig_t=lambda t, c: 1.5 if t else 1.0,
            cc_t=lambda t: 1.0, stress_t=lambda t: 1.0, doublets=0.35)
    cases.append(("a high multiplet rate is reported",
                  r["moi_doublets"]["verdict"] == "elevated", r["moi_doublets"]["reading"]))
    r = run("dbl_silent", sig_t=lambda t, c: 1.5 if t else 1.0,
            cc_t=lambda t: 1.0, stress_t=lambda t: 1.0, doublets=0.0)
    cases.append(("a clean matrix is not flagged for multiplets",
                  r["moi_doublets"]["verdict"] == "clear", r["moi_doublets"]["reading"]))

    print("\n  EXPRESSION DIAGNOSTICS SELF-TEST\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {note[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 62)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dense")
    ap.add_argument("--signature")
    ap.add_argument("--design")
    ap.add_argument("--label", default="condition")
    ap.add_argument("--unit", default="donor")
    ap.add_argument("--cluster", default="")
    ap.add_argument("--context", default="")
    ap.add_argument("--treated", default="")
    ap.add_argument("--cell-cycle")
    ap.add_argument("--stress")
    ap.add_argument("--min-counts", type=int, default=ct.DEFAULT_MIN_COUNTS)
    ap.add_argument("--min-genes", type=int, default=ct.DEFAULT_MIN_GENES)
    ap.add_argument("--max-mito", type=float, default=ct.DEFAULT_MAX_MITO)
    ap.add_argument("--emit-confounders", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.dense and args.signature and args.design):
        ap.error("--dense, --signature and --design are required (or --self-test)")

    try:
        result = analyse(
            Path(args.dense), Path(args.signature), Path(args.design), args.label, args.unit,
            cluster=args.cluster, context=args.context, treated=args.treated,
            cell_cycle=read_gene_list(Path(args.cell_cycle)) if args.cell_cycle else None,
            stress=read_gene_list(Path(args.stress)) if args.stress else None,
            min_counts=args.min_counts, min_genes=args.min_genes, max_mito=args.max_mito)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.emit_confounders:
        result["confounders_addressed"] = to_confounder_rows(result)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    fatal = (result["generic_response"]["verdict"] == "dominant")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"EXPRESSION DIAGNOSTICS: {result['matrix']} — "
              f"{result['cells_kept']}/{result['cells_read']} cells, treated={result['treated_arm']}")
        for key in ("generic_response", "composition", "ambient_rna", "moi_doublets",
                    "context_reversal"):
            block = result[key]
            mark = {"dominant": "FATAL", "composition": "warn ", "reversal": "warn ",
                    "elevated": "warn ", "not_computable": "?    "}.get(block["verdict"], "ok   ")
            print(f"  [{mark}] {key:<18} {block['verdict']}")
            print(f"          {block.get('reading', '')[:130]}")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
