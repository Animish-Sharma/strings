#!/usr/bin/env python3
"""Confounder-sweep gate — was every cheap alternative explanation actually tested?

Blocking from the executable tier up. A perturbation result competes against a
short list of explanations that are always available and mostly cheap to check:
batch, depth, guide capture, doublets, ambient RNA, cell cycle, generic stress,
composition shift, selection, off-target, pathway circularity, context reversal.

The list is in `data/confounders.json` with the cheap test for each, because a
confounder named without a test is a caveat, and caveats do not change verdicts.

Three severities, and they behave differently:

    fatal_if_complete   a confounder that is *completely* confounded with
                        treatment is unfixable by analysis. Nothing downstream
                        matters.
    fatal_if_dominant   generic stress that moves as much as the claimed pathway
                        means the claim is not specific, whatever its p-value.
    major               must be addressed with a result, not an intention.
    scope_limiting      does not block, but bounds what may be said.

A confounder marked `addressed` with no `result` is treated as unaddressed. That
is the single most common way this check gets defeated.

## Computed beats asserted, and disagreement is a failure

Everything above still reads a sentence the producer wrote about the producer's
own work — which is the same hole the frame closed in its reducer by DERIVING
checks from sealed evidence instead of reading a self-report. Eight of the twelve
confounders can be decided from the data, and `data/confounders.json` names the
tool for each in `computable_by`.

Pass `--diagnostics` and this gate stops asking:

  * a computed verdict REPLACES the bundle's for that confounder;
  * a bundle asserting something the recomputation contradicts FAILS, and fails
    naming both verdicts — the disagreement is the finding, and it is a much
    harder thing to argue with than a difference of opinion about method;
  * `not_computable` counts as unaddressed, never as clear. A check that could
    not run and a check that came back clean are different, and only one of them
    is evidence.

With no `--diagnostics`, the gate still runs and reports how many confounders
COULD have been computed and were merely asserted. That number belongs in the
receipt: a sweep passed on twelve sentences is a weaker object than one passed
on eight measurements and four sentences, and until now those two were
indistinguishable in the output.

Usage:  confounder_sweep.py <bundle.json> --claim <claim.json>
                            [--diagnostics <result.json> ...]
Exit:   0 pass, 1 fail, 2 error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402


# How bad a computed verdict is. One confounder can be cross-tabulated against
# several technical columns and comes back once per column, so `batch` arrives
# as both "confounded" (against batch) and "clear" (against lane). Keeping the
# LAST row let the reassuring column overwrite the fatal one, which is the
# single most dangerous way to lose a finding: silently, and in the direction
# of a pass.
SEVERITY = {"confounded": 3, "not_computable": 2, "unclear": 2,
            "clear": 0, "resolved": 0}


def merge_verdict(computed: dict, row: dict) -> None:
    cid = row["id"]
    prior = computed.get(cid)
    if prior is None or SEVERITY.get((row.get("verdict") or "").lower(), 1) > \
            SEVERITY.get((prior.get("verdict") or "").lower(), 1):
        computed[cid] = row


def self_computed(bundle: dict, bundle_path: Path) -> dict | None:
    """Run the cheap tests this gate already knows how to describe.

    `data/confounders.json` names `scripts/diagnostics.py` in `computable_by`
    for eight of the twelve, and the gate never called it — it waited to be
    handed the answers. A bundle that simply omitted its diagnostics therefore
    scored better than one that reported honest bad ones, and a design where
    treatment and batch cannot be separated passed. If the bundle ships the
    metadata this gate can compute from, it gets computed here.
    """
    data = bundle.get("data") or {}
    csv_name = data.get("metadata_csv")
    label = data.get("label_column")
    unit = data.get("biological_unit_column") or data.get("unit_column")
    if not (csv_name and label and unit):
        return None
    csv_path = Path(csv_name)
    if not csv_path.is_absolute():
        csv_path = bundle_path.parent / csv_name
    if not csv_path.exists():
        return None
    technical = data.get("technical_columns")
    if not technical:
        try:
            with csv_path.open(encoding="utf-8") as fh:
                header = fh.readline().strip().split(",")
        except OSError:
            return None
        technical = [c for c in header if c.lower() in TECHNICAL_NAMES]
    if not technical:
        return None
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "diagnostics.py"),
         "--metadata", str(csv_path), "--label", label, "--unit", unit,
         "--technical", *technical, "--emit-confounders", "--json"],
        capture_output=True, text=True, timeout=300)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


TECHNICAL_NAMES = {"batch", "lane", "run", "plate", "chip", "flowcell", "well",
                   "sequencing_run", "capture", "date", "site"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--claim", required=True)
    ap.add_argument("--diagnostics", nargs="*", default=[],
                    help="output of diagnostics.py / expression_diagnostics.py --json; "
                         "computed verdicts override what the bundle asserts")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        bundle = bl.read_json(args.bundle)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2

    table = bl.load_table("confounders.json")
    catalogue = {c["id"]: c for c in table["confounders"]}
    addressed = {}
    for entry in bundle.get("confounders_addressed") or []:
        if isinstance(entry, dict) and entry.get("id"):
            addressed[entry["id"]] = entry

    problems, scope_notes = [], []

    # Computed verdicts. The gate computes what it can from the bundle's own
    # data FIRST, then lets supplied diagnostics add to that — never replace it.
    computed: dict[str, dict] = {}
    own = self_computed(bundle, Path(args.bundle))
    if own:
        for row in own.get("confounders_addressed") or []:
            if isinstance(row, dict) and row.get("id") and row.get("verdict"):
                merge_verdict(computed, {**row, "computed_by": "confounder_sweep (own sweep)"})
    for path in args.diagnostics:
        try:
            payload = bl.read_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"error: {path}: {exc}")
            return 2
        for row in payload.get("confounders_addressed") or []:
            if isinstance(row, dict) and row.get("id") and row.get("verdict"):
                merge_verdict(computed, row)
        # a diagnostics payload may also carry blocks keyed by confounder id
        for cid in catalogue:
            block = payload.get(cid)
            if isinstance(block, dict) and block.get("verdict") and cid not in computed:
                computed[cid] = {"id": cid, "verdict": block["verdict"],
                                 "result": block.get("reading", ""),
                                 "computed_by": payload.get("computed_by", str(path))}

    # A computed verdict overrides the bundle, and a contradiction is a failure.
    # An ABSTENTION is neither. `not_computable` means the tool could not decide
    # from the data it was given — which is not evidence against an author who
    # settled the question another way. It records that the pack could not
    # confirm the answer, and leaves the asserted one standing to be judged on
    # its own terms. Treating an abstention as a refutation would train people to
    # withhold diagnostics, which is the opposite of what this gate wants.
    could_not_confirm = []
    for cid, row in computed.items():
        asserted = addressed.get(cid)
        if (row.get("verdict") or "").strip().lower() == "not_computable":
            could_not_confirm.append(f"{cid}: {row.get('result', '')[:80]}")
            if asserted:
                continue
        if asserted:
            claimed = (asserted.get("verdict") or "").strip().lower()
            actual = (row.get("verdict") or "").strip().lower()
            benign = {"clear", "resolved"}
            if claimed and claimed != actual and not (claimed in benign and actual in benign):
                problems.append(
                    f"{cid}: the bundle asserts {claimed!r} and the recomputation returns "
                    f"{actual!r} ({row.get('result', '')[:90]}). A self-reported confounder "
                    "check that the data contradicts is worse than no check, because it "
                    "occupies the slot where the real one would go")
        if (row.get("verdict") or "").strip().lower() == "not_computable" and asserted:
            continue
        addressed[cid] = {**(asserted or {}), **row}

    uncomputed = [cid for cid, spec in catalogue.items()
                  if spec.get("computable_by") and cid not in computed]

    for cid, spec in catalogue.items():
        entry = addressed.get(cid)
        severity = spec["severity"]
        if entry is None:
            if severity == "scope_limiting":
                scope_notes.append(f"{cid}: not examined — {spec['question']}")
            else:
                problems.append(
                    f"{cid} not addressed. {spec['question']} Cheap test: {spec['cheap_test']}")
            continue
        result = (entry.get("result") or "").strip()
        verdict = (entry.get("verdict") or "").strip().lower()
        if verdict == "not_computable":
            problems.append(
                f"{cid} could not be computed from the data provided ({result[:90]}). That is "
                "an unaddressed confounder, not a clean one — a check that could not run and a "
                "check that came back clean are different objects")
            continue
        if not result:
            problems.append(
                f"{cid} is marked addressed with no recorded result. An intention to check is "
                "not a check; write down what the test returned")
            continue
        if severity == "fatal_if_complete" and verdict in {"confounded", "complete", "fatal"}:
            problems.append(
                f"{cid} is completely confounded with treatment ({result[:80]}). No analysis "
                "separates them — this is a design failure, not a modelling problem")
        if severity == "fatal_if_dominant" and verdict in {"dominant", "fatal"}:
            problems.append(
                f"{cid} explains as much as the claimed effect ({result[:80]}). The response is "
                "not specific to the perturbation, whatever its significance")
        if severity == "fatal_if_circular" and verdict in {"circular", "fatal"}:
            problems.append(
                f"{cid}: the gene set was defined using this data ({result[:80]}). The result is "
                "circular and the pathway statement carries no information")
        if verdict in {"unresolved", "unknown"} and severity != "scope_limiting":
            problems.append(f"{cid} was examined and left unresolved ({result[:80]})")
        if severity == "scope_limiting" and verdict not in {"clear", "resolved"}:
            scope_notes.append(f"{cid}: {result[:100]}")

    controls = {c.get("id") for c in bundle.get("negative_controls") or []
                if isinstance(c, dict)}
    for required in table["required_negative_controls"]:
        if required["id"] not in controls:
            problems.append(
                f"negative control {required['id']!r} is absent — {required['why']}. A pipeline "
                "never asked to find nothing has never demonstrated it can")

    computable = sum(1 for spec in catalogue.values() if spec.get("computable_by"))
    decided = [c for c, r in computed.items()
               if (r.get("verdict") or "").lower() != "not_computable"]
    provenance = {"confounders": len(catalogue), "computable": computable,
                  "computed": len(decided), "asserted": len(catalogue) - len(decided),
                  "computable_but_asserted": sorted(uncomputed),
                  "could_not_confirm": could_not_confirm,
                  "negative_controls": len(controls)}

    if args.json:
        print(json.dumps({"verdict": "fail" if problems else "pass", "problems": problems,
                          "scope_notes": scope_notes, "provenance": provenance}, indent=2))
        return 1 if problems else 0

    for note in scope_notes:
        print(f"  scope: {note}")
    if problems:
        print(f"fail: {len(problems)} confounder problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"pass: {len(catalogue)} confounders addressed, {len(decided)} computed from the data "
          f"and {len(catalogue) - len(decided)} asserted, "
          f"{len(controls)} negative control(s) present")
    if uncomputed:
        print(f"  {len(uncomputed)} confounder(s) could have been computed and were asserted "
              f"instead: {', '.join(uncomputed)}")
        print("  that belongs in the receipt — a sweep passed on sentences is a weaker object "
              "than one passed on measurements, and the two must not read alike")
    for note in could_not_confirm:
        print(f"  could not confirm: {note}")
    if scope_notes:
        print("  scope-limiting findings above must appear in the report's bounds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
