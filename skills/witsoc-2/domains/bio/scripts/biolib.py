#!/usr/bin/env python3
"""Shared machinery for the bio pack — one implementation, imported by every
tier and gate.

The maths pack learned this the hard way: four scripts each grew their own
expression evaluator with slightly different namespaces, and a claim one script
could refute another could not even parse. Everything here is the thing that
would otherwise be reimplemented four times — claim hashing, the unit taxonomy,
pseudobulk aggregation, the permutation null, and the status lattice.

Standard library only, by design. A verification adapter that cannot run
without a scientific-Python stack is a tier that is unavailable exactly when a
run needs it, and unavailability discovered late is indistinguishable from a
failed check.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

HERE = Path(__file__).resolve().parent
PACK_ROOT = HERE.parent
DATA = PACK_ROOT / "data"

# The frame's ceiling order, copied verbatim from scripts/reducer.py. A pack that
# invents its own ordering is the exact drift the contract exists to stop, so
# this list is not adjusted to taste — it is the frame's, and the pack lives
# inside it.
#
# One thing to read carefully, because it is counter-intuitive here.
# CHECKED_BOUNDED sits BELOW CONDITIONAL in this order. That is not a claim that
# a conditional result is better evidence than a bounded one; the two are
# different kinds of limitation. CHECKED_BOUNDED says "true inside these bounds,
# silent outside them". CONDITIONAL says "true of the general statement, if an
# assumption holds". The frame ranks by how much the status PERMITS, and a
# conditional statement permits more. In this field the strong outcome is
# usually the bounded one, and the ordering is doing something else than
# ranking quality.
STATUS_ORDER = ["OPEN", "CONJECTURE", "GAP", "FAILED_ATTEMPT", "REJECTED",
                "CHECKED_BOUNDED", "SKETCH", "PARTIAL", "CONDITIONAL", "VERIFIED"]

# VERIFIED is unreachable in this pack, at every tier, under every design. An
# empirical result is support for a frozen dataset, context, and analysis; a
# VERIFIED label would put it in the same box as a machine-checked identity and
# erase the one distinction the status vocabulary exists to draw.
PACK_CEILING = "CONDITIONAL"


def rank(status: str) -> int:
    return STATUS_ORDER.index(status) if status in STATUS_ORDER else -1


def weakest(*statuses: str) -> str:
    """The pack's combination rule. Evidence lanes do not average and do not
    vote: the weakest lane is the answer, because a claim is only as established
    as its least-established necessary part."""
    present = [s for s in statuses if s in STATUS_ORDER]
    return min(present, key=rank) if present else "FAILED_ATTEMPT"


# ---------------------------------------------------------------- io + hashing

def read_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def target_sha256(claim: dict[str, Any]) -> str:
    """Hash of everything in the claim except the hash field itself. Recomputed
    at every gate rather than read back, because a claim edited to fit a result
    is the failure this whole pack is built around."""
    return sha256_text(canonical({k: v for k, v in claim.items() if k != "target_sha256"}))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_table(name: str) -> dict[str, Any]:
    return read_json(DATA / name)


def read_csv(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    """Comma or tab delimited, sniffed from the header. Metadata arrives in both."""
    text = Path(path).read_text(encoding="utf-8")
    first = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "\t" if first.count("\t") > first.count(",") else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    return list(reader.fieldnames or []), list(reader)


# --------------------------------------------------------------- unit taxonomy

def classify_columns(fields: Iterable[str]) -> dict[str, str]:
    """Map each metadata column to a level of the experimental hierarchy.

    An unmatched column is reported as `unclassified`, never dropped: a column
    nobody has classified is a level nobody has thought about, and the wrong
    denominator usually hides in exactly one of those.
    """
    taxonomy = load_table("unit_taxonomy.json")["levels"]
    compiled = [
        (level, [re.compile(p, re.IGNORECASE) for p in spec["patterns"]])
        for level, spec in taxonomy.items()
    ]
    out: dict[str, str] = {}
    for field in fields:
        name = (field or "").strip()
        out[name] = "unclassified"
        for level, patterns in compiled:
            if any(p.search(name) for p in patterns):
                out[name] = level
                break
    return out


def upstream_units(rows: Sequence[dict[str, str]], column: str) -> list[str]:
    """Distinct values of the column proposed as the experimental unit."""
    return sorted({(row.get(column) or "").strip() for row in rows if (row.get(column) or "").strip()})


def crossed(rows: Sequence[dict[str, str]], unit_col: str, condition_col: str) -> dict[str, Any]:
    """Is the unit crossed with the condition, or confounded with it?

    A unit that only ever appears under one condition carries no information
    about the contrast — the comparison is between units, not within them, and
    no amount of cells fixes that.
    """
    by_unit: dict[str, set[str]] = {}
    for row in rows:
        unit = (row.get(unit_col) or "").strip()
        cond = (row.get(condition_col) or "").strip()
        if unit and cond:
            by_unit.setdefault(unit, set()).add(cond)
    conditions = sorted({c for cs in by_unit.values() for c in cs})
    single = sorted(u for u, cs in by_unit.items() if len(cs) < 2)
    return {
        "unit_column": unit_col,
        "condition_column": condition_col,
        "units": len(by_unit),
        "conditions": conditions,
        "units_seeing_one_condition_only": single,
        "fully_crossed": bool(by_unit) and not single,
        "completely_confounded": bool(by_unit) and len(single) == len(by_unit) and len(conditions) > 1,
    }


# ------------------------------------------------------------------ statistics
# Deliberately elementary and exact-ish: every number below can be recomputed by
# hand from the same CSV. A reviewer who cannot reproduce the adapter's
# arithmetic has to trust it, and this pack's entire argument is that nobody
# should have to.

def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def variance(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def stdev(xs: Sequence[float]) -> float:
    v = variance(xs)
    return math.sqrt(v) if v == v else float("nan")


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    va, vb = variance(a), variance(b)
    pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2))
    return (mean(a) - mean(b)) / pooled if pooled else float("nan")


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return float("nan")
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def mae(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or not xs:
        return float("nan")
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)


def effective_n(cluster_sizes: Sequence[int], icc: float) -> float:
    """Design-effect correction. With any positive intra-cluster correlation,
    the effective sample size approaches the number of CLUSTERS, not cells —
    which is the arithmetic behind every pseudoreplication rejection here."""
    return sum(size / (1.0 + (size - 1) * icc) for size in cluster_sizes if size > 0)


def permutation_p(
    values: Sequence[float],
    labels: Sequence[str],
    treatment: str,
    control: str,
    *,
    iterations: int = 2000,
    seed: int = 0,
    strata: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Two-sided permutation test on the difference in means.

    Labels are shuffled WITHIN stratum when strata are given. Shuffling across
    batches destroys the batch structure along with the effect, which makes a
    confounded result look clean — the permutation has to break the thing being
    claimed and nothing else.
    """
    obs_t = [v for v, l in zip(values, labels) if l == treatment]
    obs_c = [v for v, l in zip(values, labels) if l == control]
    if len(obs_t) < 2 or len(obs_c) < 2:
        return {"ran": False, "reason": "fewer than two units in a group; nothing to permute"}

    observed = mean(obs_t) - mean(obs_c)
    rng = random.Random(seed)
    keys = list(strata) if strata else ["_all"] * len(labels)
    buckets: dict[str, list[int]] = {}
    for index, key in enumerate(keys):
        buckets.setdefault(key, []).append(index)

    extreme = 0
    for _ in range(iterations):
        shuffled = list(labels)
        for indexes in buckets.values():
            pool = [labels[i] for i in indexes]
            rng.shuffle(pool)
            for i, label in zip(indexes, pool):
                shuffled[i] = label
        pt = [v for v, l in zip(values, shuffled) if l == treatment]
        pc = [v for v, l in zip(values, shuffled) if l == control]
        if len(pt) < 1 or len(pc) < 1:
            continue
        if abs(mean(pt) - mean(pc)) >= abs(observed) - 1e-12:
            extreme += 1

    return {
        "ran": True,
        "observed_difference": observed,
        "iterations": iterations,
        "seed": seed,
        "stratified_by": "stratum" if strata else "none",
        # +1 in both places: a permutation p-value of exactly zero is an artifact
        # of finite resampling, and reporting it as zero overstates the evidence.
        "p_value": (extreme + 1) / (iterations + 1),
        "n_treatment": len(obs_t),
        "n_control": len(obs_c),
    }


def bootstrap_interval(
    values: Sequence[float],
    labels: Sequence[str],
    treatment: str,
    control: str,
    *,
    iterations: int = 4000,
    seed: int = 0,
    level: float = 0.95,
    strata: Sequence[str] | None = None,
) -> dict[str, Any]:
    """A percentile interval on the difference in unit means.

    A p-value answers "could this be nothing". An interval answers "how big,
    and how sure" — and only the second bounds a claim. A tier whose whole
    ceiling is CHECKED_BOUNDED reporting no bounds was reporting the one number
    that does not do its job.

    Resampling follows the DESIGN. In a matched design — one treated and one
    control unit per stratum — the pairs are resampled, not the arms, because
    that is what the stratified permutation test is testing. Resampling arms
    independently on a paired design throws away the pairing and produces an
    interval far wider than the test: the first version of this function did
    exactly that, and reported an interval spanning zero for an effect the same
    data put at p = 0.03. The interval was not wrong about its own question, it
    was answering a different one.

    Where there is no pairing, resampling is within arm — pooling the arms
    instead would build an interval for a design with no treatment structure at
    all, narrow in exactly the cases where the design is weakest.

    With few units the interval is wide and jagged, and that is the finding. An
    interval computed from four units is honest about a design that cannot say
    much, where a p-value from the same four units reads like a result.
    """
    arm_t = [v for v, l in zip(values, labels) if l == treatment]
    arm_c = [v for v, l in zip(values, labels) if l == control]
    if len(arm_t) < 2 or len(arm_c) < 2:
        return {"ran": False,
                "reason": "fewer than two units in an arm; a resampled interval over this "
                          "design describes the resampling and not the biology"}

    paired = None
    if strata:
        by_stratum: dict[str, dict[str, list[float]]] = {}
        for value, label, stratum in zip(values, labels, strata):
            if label in (treatment, control):
                by_stratum.setdefault(stratum, {}).setdefault(label, []).append(value)
        if len(by_stratum) >= 2 and all(
                len(arms.get(treatment, [])) == 1 and len(arms.get(control, [])) == 1
                for arms in by_stratum.values()):
            paired = [arms[treatment][0] - arms[control][0] for arms in by_stratum.values()]

    rng = random.Random(seed)
    diffs = []
    if paired:
        for _ in range(iterations):
            sample = [paired[rng.randrange(len(paired))] for _ in paired]
            diffs.append(mean(sample))
    else:
        for _ in range(iterations):
            rt = [arm_t[rng.randrange(len(arm_t))] for _ in arm_t]
            rc = [arm_c[rng.randrange(len(arm_c))] for _ in arm_c]
            diffs.append(mean(rt) - mean(rc))
    diffs.sort()
    tail = (1.0 - level) / 2.0
    lo = diffs[max(0, int(tail * len(diffs)) - 1)]
    hi = diffs[min(len(diffs) - 1, int((1.0 - tail) * len(diffs)))]
    point = mean(paired) if paired else mean(arm_t) - mean(arm_c)
    return {
        "ran": True,
        "point_estimate": point,
        "level": level,
        "lower": lo,
        "upper": hi,
        "width": hi - lo,
        "iterations": iterations,
        "resampled": "paired differences" if paired else "within arm",
        "pairs": len(paired) if paired else None,
        "crosses_zero": lo <= 0.0 <= hi,
        "note": ("the interval is the bound; the p-value only says whether zero is in it. "
                 "With few units it is wide, and that width is the design speaking"),
    }


def pseudobulk(
    rows: Sequence[dict[str, str]], unit_col: str, value_col: str, label_col: str
) -> list[dict[str, Any]]:
    """Collapse observations to one value per experimental unit.

    This is the whole fix for pseudoreplication and it is four lines long. The
    difficulty was never computational — it is deciding which column is the unit,
    which is why that decision is frozen in the claim and checked separately.
    """
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        unit = (row.get(unit_col) or "").strip()
        raw = (row.get(value_col) or "").strip()
        if not unit or not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        entry = buckets.setdefault(unit, {"unit": unit, "values": [], "labels": set()})
        entry["values"].append(value)
        label = (row.get(label_col) or "").strip()
        if label:
            entry["labels"].add(label)
    out = []
    for unit, entry in sorted(buckets.items()):
        labels = sorted(entry["labels"])
        out.append({
            "unit": unit,
            "n_observations": len(entry["values"]),
            "mean": mean(entry["values"]),
            "sd": stdev(entry["values"]),
            "label": labels[0] if len(labels) == 1 else "MIXED",
            "labels": labels,
        })
    return out


# --------------------------------------------------------------------- receipts

def paired_units(rows, unit_col: str, value_col: str, label_col: str,
                 treatment: str, control: str) -> tuple[list[dict], list[str]]:
    """One WITHIN-UNIT difference per unit, for a crossed design.

    `pseudobulk` collapses to one value per unit and then asks which arm the unit
    belongs to. For a unit that appears in BOTH arms there is no answer, so it
    was labelled MIXED and excluded — and a donor-replicated population claim
    requires donors crossed with the condition, which means every unit is mixed
    and the whole design was excluded. The pack demanded a design it could not
    analyse.

    A crossed design is not a weaker between-unit design; it is a stronger
    paired one. Each unit is its own control, the between-donor variation that
    dominates this kind of data cancels, and the estimand is the mean
    within-donor difference.
    """
    buckets: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        unit = (row.get(unit_col) or "").strip()
        label = (row.get(label_col) or "").strip()
        raw = (row.get(value_col) or "").strip()
        if not unit or not label or not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        buckets.setdefault(unit, {}).setdefault(label, []).append(value)

    pairs, incomplete = [], []
    for unit in sorted(buckets):
        arms = buckets[unit]
        if treatment in arms and control in arms:
            t_mean, c_mean = mean(arms[treatment]), mean(arms[control])
            pairs.append({"unit": unit, "treatment_mean": t_mean, "control_mean": c_mean,
                          "difference": t_mean - c_mean,
                          "n_treatment": len(arms[treatment]),
                          "n_control": len(arms[control])})
        else:
            incomplete.append(unit)
    return pairs, incomplete


def sign_flip_p(differences: Sequence[float], iterations: int = 20000,
                seed: int = 0) -> dict[str, Any]:
    """The exact null for a paired design: under the null each unit's difference
    is as likely to have come out either way.

    Enumerated exactly when the unit count allows it, because at six units there
    are sixty-four sign patterns and a sampled approximation of a distribution
    you can write down is worse in every respect. The floor is reported: with n
    units the smallest attainable two-sided p is 2/2^n, and a design that cannot
    reach the alpha it is being judged against should say so before it is run.
    """
    n = len(differences)
    if n == 0:
        return {"p_value": None, "reason": "no paired units"}
    observed = abs(mean(differences))
    exact = n <= 20 and 2 ** n <= iterations
    count = total = 0
    if exact:
        for pattern in range(2 ** n):
            flipped = [d if (pattern >> i) & 1 else -d for i, d in enumerate(differences)]
            total += 1
            if abs(mean(flipped)) >= observed - 1e-12:
                count += 1
    else:
        rng = random.Random(seed)
        for _ in range(iterations):
            flipped = [d if rng.random() < 0.5 else -d for d in differences]
            total += 1
            if abs(mean(flipped)) >= observed - 1e-12:
                count += 1
    return {"p_value": count / total, "iterations": total, "exact": exact,
            "smallest_attainable_p": 2 / (2 ** n) if n <= 20 else 1 / iterations,
            "units": n}


def receipt(tier: str, claim: dict[str, Any], artifact: str | Path, verdict: str,
            max_status: str, **extra: Any) -> dict[str, Any]:
    """One shape for everything this pack emits.

    `max_status` is the strongest status this receipt could ever support, and it
    is written by the tier rather than inferred by the reader. A receipt that
    does not carry its own ceiling gets read as stronger than it is, every time.
    """
    artifact_path = Path(artifact)
    payload = {
        "schema": "bio-receipt-v1",
        # frame-receipt-v1 fields first: this receipt has to cross the contract
        # line, and the frame reads it by those names.
        "receipt_id": f"bio-{sha256_file(artifact_path)[:12]}-{tier}",
        "target_sha256": claim.get("target_sha256", ""),
        "artifact_sha256": sha256_file(artifact_path),
        "tier": tier,
        "verdict": verdict,
        "produced_at": now(),
        "max_status": weakest(max_status, PACK_CEILING),
        "empirical": True,
        "scope_note": (
            "Support is bounded by the frozen dataset, context, perturbation, analysis, "
            "and metric set. Nothing here establishes anything outside those bounds."
        ),
    }
    payload.update(extra)
    # Completeness is frame-required and is not a formality here: a bio receipt
    # is complete only when the tier ran, every blocking gate returned a verdict,
    # and nothing is open. A gate that did not run leaves a gap.
    gates = extra.get("gates") or []
    payload.setdefault("completeness", {
        "all_obligations_covered": bool(gates) and all(
            g.get("verdict") in {"pass", "not_run"} for g in gates),
        "concluding_step_covered": verdict == "pass",
        "open_gaps": sum(1 for g in gates if g.get("verdict") == "not_run"),
        "rejections": sum(1 for g in gates if g.get("verdict") in {"fail", "error"}),
    })
    payload.setdefault("environment", {"fresh_process": True, "fresh_copy": False,
                                       "restricted_env": False})
    refute = payload.get("refute_attempt")
    if isinstance(refute, dict):
        refute.setdefault("discharged_by",
                          "adversarial_tier" if extra.get("adversarial") else "skeptic_pass")
    # Sealed, because an unsealed receipt cannot be bound to an admission and an
    # unbound receipt is the hole the reducer exists to close.
    payload.pop("payload_sha256", None)
    payload["payload_sha256"] = hashlib.sha256(canonical(payload).encode()).hexdigest()
    return payload


def emit(payload: dict[str, Any], as_json: bool = True) -> None:
    print(json.dumps(payload, indent=2, default=str) if as_json else payload)
