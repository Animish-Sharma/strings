#!/usr/bin/env python3
"""Claim-class resolution — the decision that sets the ceiling.

The Explorer doctrine opens with "the first decision is the class, not the
method", and it was right and it was unaided. The class fixes what the run may
ever conclude: a realized-screen cell-level association tops out at
CONDITIONAL_WITHIN_SCREEN however clean the analysis, and a donor-replicated
population claim reaches CHECKED_BOUNDED only with donors actually crossed with
the condition. Get the class wrong and every downstream gate guards the wrong
thing while reporting that it passed.

That decision was made by eye. Meanwhile the far less consequential decision of
which PACK to load has a scorer, an explain mode, and a calibration set. This
closes the asymmetry.

## Two answers, and the gap between them is the finding

**Claimed class** comes from the statement's own words — what is being asserted.
**Supportable class** comes from the metadata, when there is any — what the
design can carry. They are different questions and the pack's whole subject is
what happens when people conflate them:

  * claimed `donor_replicated_population`, supportable `guide_conditioned` —
    the population claim is not backed by the design. This is the denominator
    finding, and it now arrives at TRIAGE instead of after the analysis is
    already paid for.
  * claimed `guide_conditioned`, supportable `donor_replicated` — the run is
    under-claiming, which is nobody's crisis and is still worth saying: a design
    that could have carried more was not asked to.

The ceiling is the weaker of the two, always. Evidence lanes do not vote and
neither do these.

## Scoring

    score = 1 x signals + 3 x strong_signals - 3 x excludes

against each class's own `min_score`, with a margin over the runner-up. The
terms live in `data/claim_classes.json`; this file holds no biology, so a term
that misroutes is fixed in the data where it is visible.

AMBIGUOUS is a real answer, not a failure — a claim can genuinely sit between
two classes, and the honest response is the weaker ceiling of the two plus a
narrowing question, rather than a coin flip nobody records.

Usage:
    classify_claim.py --statement "..." [--metadata <file.csv>] [--explain] [--json]
    classify_claim.py --claim <claim.json> [--metadata <file.csv>]
    classify_claim.py --list
    classify_claim.py --calibrate [--cases <file.json>]
    classify_claim.py --self-test

Exit: 0 resolved, 3 ambiguous, 4 no match, 2 usage/IO, 1 self-test/calibration failure
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import biolib as bl  # noqa: E402

MARGIN = 2

# Which estimand a design can carry, weakest first. A class may never be
# assigned above what the metadata supports.
ESTIMAND_ORDER = ["unspecified", "cell_level", "within_screen", "predictive", "population"]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def matches(haystack: str, terms: list[str]) -> list[str]:
    """Whole-term matching, not substring.

    `"rat" in "proliferation"` is true and is the kind of hit that quietly moves
    a claim into the animal class. Alphanumeric boundaries rather than \b so
    hyphenated terms — `cell-level`, `patient-derived`, `perturb-seq` — still
    match, since a hyphen is a boundary here and not a word character.
    """
    found = []
    for term in terms:
        if not term:
            continue
        # Tolerate a plural on the last word: `organoid` must match "organoids"
        # and `patient-derived organoid` must match "patient-derived organoids".
        # Whole-term matching without this trades one error for another — the
        # false positives go and inflections start being missed, which is just
        # as wrong and harder to notice because nothing fires.
        pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?:e?s)?(?![a-z0-9])"
        if re.search(pattern, haystack):
            found.append(term)
    return sorted(set(found))


def score_classes(statement: str, classes: list[dict]) -> list[dict]:
    haystack = norm(statement)
    scored = []
    for entry in classes:
        sel = entry.get("selection") or {}
        sig = matches(haystack, sel.get("signals") or [])
        strong = matches(haystack, sel.get("strong_signals") or [])
        excl = matches(haystack, sel.get("excludes") or [])
        scored.append({
            "id": entry["id"], "label": entry.get("label"),
            "estimand": entry.get("estimand"), "max_status": entry.get("max_status"),
            "refinement": entry.get("refinement"),
            "min_upstream_units": entry.get("min_upstream_units", 0),
            "score": len(sig) + 3 * len(strong) - 3 * len(excl),
            "min_score": sel.get("min_score", 4),
            "signals": sig, "strong_signals": strong, "excludes": excl,
        })
    return sorted(scored, key=lambda s: (-s["score"], s["id"]))


def resolve(statement: str, classes: list[dict]) -> dict:
    scored = score_classes(statement, classes)
    qualifying = [s for s in scored if s["score"] >= s["min_score"]]
    if not qualifying:
        return {"verdict": "NO_MATCH", "ranked": scored[:4],
                "reading": "no class cleared its threshold. The statement is probably "
                           "underspecified — it does not say what unit it is about, and that "
                           "is the first thing to fix, not something to guess past"}
    best = qualifying[0]
    rest = [s for s in qualifying[1:] if best["score"] - s["score"] < MARGIN]
    if rest:
        contenders = [best] + rest
        weakest = min(contenders, key=lambda c: ESTIMAND_ORDER.index(c["estimand"])
                      if c["estimand"] in ESTIMAND_ORDER else 0)
        return {"verdict": "AMBIGUOUS", "candidates": [c["id"] for c in contenders],
                "ceiling_class": weakest["id"], "ranked": scored[:4],
                "reading": f"{len(contenders)} classes within {MARGIN} points. Take the weaker "
                           f"ceiling ({weakest['id']}) and narrow the statement — a class "
                           "decided by a coin flip sets a ceiling nobody can defend"}
    return {"verdict": "RESOLVED", "claimed_class": best["id"], "ranked": scored[:4],
            "detail": best,
            "reading": f"{best['label']} — ceiling {best['max_status']}"
                       + (f" ({best['refinement']})" if best.get("refinement") else "")}


def supportable(metadata: Path, classes: list[dict]) -> dict:
    """What the DESIGN can carry, from the metadata table alone.

    Deliberately blunt: it asks whether there is an upstream unit column crossed
    with the condition, and how many levels it has per arm. That is the question
    the denominator gate asks later at much greater cost, and asking it at
    triage is the difference between a wasted campaign and a narrowed claim.
    """
    fields, rows = bl.read_csv(metadata)
    classified = bl.classify_columns(fields)
    # The taxonomy's own level names, not invented ones. Guessing at the level
    # label made every table look screen-only, which is the most dangerous
    # direction to be wrong in: it reads as a cautious answer and is a wrong one.
    upstream = [c for c, level in classified.items()
                if level == "biological_replicate_candidate"]
    condition = next((c for c, level in classified.items() if level == "condition_or_time"), None)
    if not condition:
        condition = next((c for c in fields if c.lower() in
                          {"condition", "treatment", "arm", "perturbation", "label"}), None)

    result = {"columns": dict(classified), "upstream_unit_columns": upstream,
              "condition_column": condition}
    if not upstream or not condition:
        result.update({"estimand": "within_screen", "units": 0,
                       "reading": ("no upstream biological unit is crossed with the condition in "
                                   "this table" if condition else
                                   "no condition column was identified in this table")
                                  + ". The design can speak about the screen it was measured in "
                                    "and not about a population, whatever the statement says"})
        return result

    unit_col = upstream[0]
    cross = bl.crossed(rows, unit_col, condition)
    units = len(bl.upstream_units(rows, unit_col))
    # Units contributing to each arm. A design is only as strong as its smallest
    # arm: eight donors, seven of them control, is a one-donor treated arm.
    per_arm: dict[str, set[str]] = {}
    for row in rows:
        unit, arm = (row.get(unit_col) or "").strip(), (row.get(condition) or "").strip()
        if unit and arm:
            per_arm.setdefault(arm, set()).add(unit)
    per_arm_counts = {arm: len(units_) for arm, units_ in per_arm.items()}
    smallest = min(per_arm_counts.values()) if per_arm_counts else 0
    separable = not cross.get("completely_confounded")
    if separable and smallest >= 3:
        result.update({"estimand": "population", "units": units, "unit_column": unit_col,
                       "units_per_arm": per_arm_counts,
                       "reading": f"{units} {unit_col}(s) crossed with {condition}, smallest arm "
                                  f"{smallest}. A population claim is supportable"})
    elif separable:
        result.update({"estimand": "within_screen", "units": units, "unit_column": unit_col,
                       "units_per_arm": per_arm_counts,
                       "reading": f"{unit_col} is crossed with {condition} but the smallest arm "
                                  f"holds {smallest} unit(s). Below three, a permutation over "
                                  "units cannot produce a small p-value whatever the effect is"})
    else:
        result.update({"estimand": "within_screen", "units": units, "unit_column": unit_col,
                       "reading": f"{unit_col} is CONFOUNDED with {condition} — they are the same "
                                  "variable in this table. No analysis separates them; this is a "
                                  "design failure and the remedy is a different experiment"})
    return result


def combine(claimed: dict, design: dict | None) -> dict:
    out = dict(claimed)
    if not design:
        out["ceiling_source"] = "statement only — no metadata was given, so what the design can "\
                                "carry is unknown and the class is the claimed one"
        return out
    claimed_id = claimed.get("claimed_class") or claimed.get("ceiling_class")
    claimed_estimand = next((r["estimand"] for r in claimed.get("ranked", [])
                             if r["id"] == claimed_id), "unspecified")
    a = ESTIMAND_ORDER.index(claimed_estimand) if claimed_estimand in ESTIMAND_ORDER else 0
    b = ESTIMAND_ORDER.index(design["estimand"]) if design["estimand"] in ESTIMAND_ORDER else 0
    out["design"] = design
    out["claimed_estimand"] = claimed_estimand
    out["supportable_estimand"] = design["estimand"]
    if a > b:
        out["gap"] = "OVER_CLAIMING"
        out["ceiling_estimand"] = design["estimand"]
        out["reading"] = (f"the statement claims a {claimed_estimand} effect and the design "
                          f"supports {design['estimand']}. {design['reading']}. The ceiling is "
                          "the design's, and finding this at triage costs an afternoon where "
                          "finding it after the analysis costs the campaign")
    elif b > a:
        out["gap"] = "UNDER_CLAIMING"
        out["ceiling_estimand"] = claimed_estimand
        out["reading"] = (f"the design supports {design['estimand']} and the statement only "
                          f"claims {claimed_estimand}. Not a problem — and a design that could "
                          "have carried more was not asked to, which is worth knowing before "
                          "the data is set aside")
    else:
        out["gap"] = "AGREED"
        out["ceiling_estimand"] = claimed_estimand
        out["reading"] = (f"statement and design agree on a {claimed_estimand} estimand. "
                          f"{design['reading']}")
    return out


DEFAULT_CASES = [
 ("Does knocking down GENE-X with CRISPRi reduce the inflammatory signature across donors in primary donor macrophages?", "donor_replicated_population"),
 ("Within the screen, cells receiving the guide show lower pathway score than matched non-targeting controls.", "guide_conditioned_within_screen"),
 ("Model M outperforms the mean baseline on held-out perturbations in this Perturb-seq benchmark.", "model_predictive_superiority"),
 ("The published claim reports that the knockout reduces viability; we assess it based on the literature with no new data.", "literature_only"),
 ("Across mice, in vivo administration reduces the fibrotic signature per animal.", "in_vivo_animal"),
 ("In patient-derived organoids the compound reduces proliferation across patient lines.", "organoid_patient_model"),
 ("Spatial transcriptomics of the tissue section shows the niche is enriched per slide.", "spatial_tissue"),
 ("The gene regulatory network analysis shows GENE-A causally drives GENE-B expression.", "network_causal_method"),
 ("Multiple independent guides per target reduce the readout at target-level with matched efficacy controls.", "target_conditioned"),
 ("At the cell level, pathway score is correlated across cells with the cell state score.", "cell_level_association"),
 ("Does the drug change expression?", None),
 ("A patient-derived biopsy series from independent donors.", "AMBIGUOUS"),
]


def calibrate(classes: list[dict], cases_path: Path | None) -> int:
    cases = DEFAULT_CASES
    if cases_path:
        raw = json.loads(cases_path.read_text(encoding="utf-8"))
        cases = [(c["statement"], c.get("expect")) for c in raw["cases"]]
    wrong = []
    print("\n  CLAIM-CLASS CALIBRATION\n")
    for statement, expect in cases:
        result = resolve(statement, classes)
        got = (result.get("claimed_class") if result["verdict"] == "RESOLVED"
               else result["verdict"] if result["verdict"] in {"AMBIGUOUS", "NO_MATCH"} else None)
        want = expect if expect else "NO_MATCH"
        ok = got == want
        if not ok:
            wrong.append((statement, want, got))
        print(f"  {'ok  ' if ok else 'MISS'}  {want:<32} {statement[:64]}")
        if not ok:
            print(f"          got {got}; top: "
                  + ", ".join(f"{r['id']}={r['score']}" for r in result['ranked'][:3]))
    total = len(cases)
    print("\n" + "=" * 62)
    print(f"  {total - len(wrong)}/{total} correct")
    if wrong:
        print("  a miss is a term problem in data/claim_classes.json, not a scorer problem — "
              "the scorer holds no biology")
    return 1 if wrong else 0


def self_test(classes: list[dict]) -> int:
    cases, failures = [], 0

    r = resolve("Across donors, primary donor macrophages show a reduced signature.", classes)
    cases.append(("a donor-crossed statement resolves to the population class",
                  r["verdict"] == "RESOLVED" and r["claimed_class"] == "donor_replicated_population",
                  r["reading"]))

    r = resolve("Does the drug change expression?", classes)
    cases.append(("an underspecified statement is NO_MATCH, not a guess",
                  r["verdict"] == "NO_MATCH", r["reading"]))

    r = resolve("A patient-derived biopsy series from independent donors.", classes)
    cases.append(("a statement matching two classes is AMBIGUOUS and takes the weaker ceiling",
                  r["verdict"] == "AMBIGUOUS", r["reading"]))

    # over-claiming: population words, screen-only design
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="classify_"))
    (tmp / "screen.csv").write_text(
        "cell_barcode,condition,guide\n" + "\n".join(
            f"c{i},{'treated' if i % 2 else 'control'},g{i%4}" for i in range(40)) + "\n",
        encoding="utf-8")
    claimed = resolve("Across donors, primary donor macrophages show the effect.", classes)
    combined = combine(claimed, supportable(tmp / "screen.csv", classes))
    cases.append(("a population claim on a screen-only table is caught as OVER_CLAIMING",
                  combined["gap"] == "OVER_CLAIMING", combined["reading"]))

    # Each donor must see BOTH arms or the table is confounded, not crossed. The
    # first version keyed both the arm and the donor off `i`, so every donor sat
    # in exactly one arm and the "crossed" fixture was a confounded one.
    (tmp / "donors.csv").write_text(
        "cell_barcode,condition,donor\n" + "\n".join(
            f"c{i},{'treated' if (i // 8) % 2 else 'control'},D{i % 8}" for i in range(160))
        + "\n", encoding="utf-8")
    combined = combine(claimed, supportable(tmp / "donors.csv", classes))
    cases.append(("a donor-crossed table agrees with a population claim",
                  combined["gap"] == "AGREED", combined["reading"]))

    combined = combine(resolve("Within the screen, guide-bearing cells differ from matched "
                               "non-targeting controls.", classes),
                       supportable(tmp / "donors.csv", classes))
    cases.append(("a narrow claim on a strong design reads as UNDER_CLAIMING, not a failure",
                  combined["gap"] == "UNDER_CLAIMING", combined["reading"]))

    (tmp / "confounded.csv").write_text(
        "cell_barcode,condition,donor\n" + "\n".join(
            f"c{i},{'treated' if i < 40 else 'control'},D{0 if i < 40 else 1}"
            for i in range(80)) + "\n", encoding="utf-8")
    design = supportable(tmp / "confounded.csv", classes)
    cases.append(("donor confounded with condition cannot support a population claim",
                  design["estimand"] != "population", design["reading"]))

    print("\n  CLAIM-CLASS SELF-TEST\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {note[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 62)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--statement")
    ap.add_argument("--claim")
    ap.add_argument("--metadata")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--cases")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        table = bl.load_table("claim_classes.json")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    classes = table["classes"]

    if args.list:
        for entry in classes:
            print(f"  {entry['id']:<34} {entry['estimand']:<14} ceiling {entry['max_status']}"
                  + (f" / {entry['refinement']}" if entry.get("refinement") else ""))
        return 0
    if args.self_test:
        return self_test(classes)
    if args.calibrate:
        return calibrate(classes, Path(args.cases) if args.cases else None)

    statement = args.statement
    if args.claim and not statement:
        try:
            claim = bl.read_json(args.claim)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        statement = " ".join(str(claim.get(k, "")) for k in
                             ("exact_statement", "claimed_effect", "allowed_scope"))
    if not statement:
        ap.error("--statement or --claim is required")

    result = resolve(statement, classes)
    design = None
    if args.metadata:
        try:
            design = supportable(Path(args.metadata), classes)
        except (OSError, ValueError, KeyError) as exc:
            print(f"ERROR: metadata unreadable: {exc}", file=sys.stderr)
            return 2
    result = combine(result, design)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"CLAIM CLASS: {result['verdict']}"
              + (f" — {result.get('claimed_class') or result.get('ceiling_class')}"
                 if result['verdict'] != 'NO_MATCH' else ""))
        print(f"  {result['reading']}")
        if result.get("gap"):
            print(f"  gap            {result['gap']}  "
                  f"(claimed {result.get('claimed_estimand')}, "
                  f"supportable {result.get('supportable_estimand')})")
        if args.explain:
            print("\n  scores:")
            for entry in result["ranked"]:
                print(f"    {entry['id']:<34} {entry['score']:>3}  "
                      f"(min {entry['min_score']})  "
                      f"strong={entry['strong_signals']} signals={entry['signals'][:4]}"
                      + (f" excludes={entry['excludes']}" if entry["excludes"] else ""))
    return {"RESOLVED": 0, "AMBIGUOUS": 3, "NO_MATCH": 4}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
