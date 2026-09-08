#!/usr/bin/env python3
"""Domain pack conformance check — governance rules 3, 5, and 6.

Validates a pack manifest against schemas/frame-domain-pack-v1.schema.json and
then applies the semantic checks a schema cannot express. The schema file is the
single source of truth for the contract: this script reads it rather than
restating it, so a contract version bump changes one file, not two.

Usage:
    validate_domain_pack.py domains/<name>/domain.json

Exit status: 0 conformant, 1 violations, 2 usage/IO error.

Implements a deliberately small subset of JSON Schema draft-07 — the keywords
this contract actually uses. Unknown keywords are ignored rather than guessed
at; if the contract grows a keyword, teach it here explicitly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsonschema_lite import validate  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = SKILL_ROOT / "schemas"

# A pack declares its contract version and the frame never infers it (governance
# rule 6). Version 2 added contract item 6, `selection` — without it a pack is
# resolvable only by explicit name, which is why v1 packs still validate but are
# invisible to scripts/resolve_domain.py.
SCHEMA_BY_VERSION = {
    "1": "frame-domain-pack-v1.schema.json",
    "2": "frame-domain-pack-v2.schema.json",
    "3": "frame-domain-pack-v3.schema.json",
}

STATUS_ORDER = ["CONJECTURE", "SKETCH", "PARTIAL", "CHECKED_BOUNDED", "CONDITIONAL", "VERIFIED"]

# What every receipt crossing the contract line must carry, read from the frame
# schema rather than restated here — the same rule this check enforces on packs.
FRAME_RECEIPT_REQUIRED = json.loads(
    (SCHEMA_DIR / "frame-receipt-v1.schema.json").read_text(encoding="utf-8")).get("required", [])


def selection_checks(pack: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Contract item 6. A selection block that over-claims is worse than none:
    it loads the wrong field's doctrine and reports success while doing it."""
    errors: list[str] = []
    warnings: list[str] = []
    selection = pack.get("selection")
    if not isinstance(selection, dict):
        return errors, warnings

    signals = {t.lower() for t in selection.get("signals", []) or []}
    strong = {t.lower() for t in selection.get("strong_signals", []) or []}
    excludes = {t.lower() for t in selection.get("excludes", []) or []}

    both = sorted((signals | strong) & excludes)
    if both:
        errors.append(
            f"selection lists {both} as both a signal and an exclude. Scoring would add and "
            "subtract for the same word, which is not a considered weighting — it is a mistake "
            "that happens to cancel."
        )
    overlap = sorted(signals & strong)
    if overlap:
        errors.append(
            f"selection lists {overlap} as both a signal and a strong signal; the term would "
            "score 4 instead of either declared weight"
        )

    if selection.get("explicit_only"):
        if signals or strong:
            warnings.append(
                "selection.explicit_only is true, so these signals are never scored. Either drop "
                "them or drop explicit_only — a list that looks live and is not misleads review."
            )
    else:
        if not (signals or strong):
            errors.append(
                "selection declares no signals and is not explicit_only, so this pack can never "
                "be resolved. An unreachable pack is indistinguishable from an absent one."
            )
        if not selection.get("counter_examples"):
            warnings.append(
                "selection declares no counter_examples, so this pack has never been tested "
                "against the problems it is most likely to over-claim. Add at least one "
                "statement that uses its words but belongs to another field."
            )

    return errors, warnings


def provisional_checks(pack: dict[str, Any], tiers: list[dict[str, Any]], pack_dir: Path
                       ) -> tuple[list[str], list[str]]:
    """An improvised pack is allowed to be weak. It is not allowed to be weak
    quietly, and it is not allowed to grant a status its backend cannot support."""
    errors: list[str] = []
    warnings: list[str] = []
    provisional = pack.get("provisional")
    if not isinstance(provisional, dict):
        return errors, warnings

    ceiling = provisional.get("ceiling")
    reachable = [t.get("max_status") for t in tiers if t.get("max_status") in STATUS_ORDER]
    best_tier = max(reachable, key=STATUS_ORDER.index) if reachable else "CONJECTURE"
    if ceiling in STATUS_ORDER and STATUS_ORDER.index(ceiling) > STATUS_ORDER.index(best_tier):
        errors.append(
            f"provisional.ceiling is {ceiling!r} but the strongest tier here caps at "
            f"{best_tier!r}. A ceiling may only lower what the tiers support, never raise it."
        )

    if provisional.get("authored_by") == "orchestrator":
        independent = [
            t for t in tiers
            if t.get("adversarial") is True
            and t.get("authorship") == "independent"
            and t.get("negative_control")
            and (pack_dir / t["negative_control"]).exists()
        ]
        if ceiling == "VERIFIED" and not independent:
            errors.append(
                "provisional.ceiling is VERIFIED on an orchestrator-authored pack with no tier "
                "that is adversarial, independently authored, and backed by a negative control "
                "that exists. That configuration lets the system that produces candidates grant "
                "itself the strongest status in the vocabulary."
            )
        if independent:
            warnings.append(
                f"tier(s) {[t.get('name') for t in independent]} claim independent authorship "
                "inside an orchestrator-authored pack. That is legitimate when the pack is glue "
                "around an external checker — confirm the checker really is external before "
                "relying on the ceiling this buys."
            )

    warnings.append(
        f"this pack is PROVISIONAL (ceiling {ceiling}). Every report of work done under it must "
        f"say so. Promotion requires: "
        + "; ".join(provisional.get("promotion_requirements", []) or ["<none declared>"])
    )
    return errors, warnings

def semantic_checks(
    pack: dict[str, Any], pack_dir: Path
) -> tuple[list[str], list[str], list[str]]:
    """Checks the schema cannot express. Returns (errors, warnings, notes)."""
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    domain = pack.get("domain")
    if domain and domain != pack_dir.name:
        errors.append(
            f"domain {domain!r} does not match its directory name {pack_dir.name!r}; "
            "the frame resolves packs by directory"
        )

    adapter = pack.get("verification_adapter", {})
    tiers = adapter.get("tiers", []) if isinstance(adapter, dict) else []
    tier_names = {t.get("name") for t in tiers if isinstance(t, dict)}
    adversarial_tiers = {
        t.get("name") for t in tiers if isinstance(t, dict) and t.get("adversarial") is True
    }

    # Refinement 1: the refute-attempt gate must actually be dischargeable.
    gates = pack.get("gates", {})
    refute = gates.get("refute_attempt", {}) if isinstance(gates, dict) else {}
    satisfied_by = refute.get("satisfied_by_tier") if isinstance(refute, dict) else None
    if satisfied_by:
        if satisfied_by not in tier_names:
            errors.append(
                f"gates.refute_attempt.satisfied_by_tier names {satisfied_by!r}, "
                f"which is not a declared tier ({sorted(n for n in tier_names if n)})"
            )
        elif satisfied_by not in adversarial_tiers:
            errors.append(
                f"gates.refute_attempt.satisfied_by_tier names {satisfied_by!r}, but that tier "
                "is not marked adversarial. Only a backend that cannot be talked into a false "
                "pass discharges the refute-attempt gate on its own; otherwise declare a "
                "separate perturbed re-run or skeptic pass."
            )
    elif not adversarial_tiers:
        # Legal, but worth saying out loud: nothing here is self-refuting, so the
        # gate must be a real separate step and not a second friendly run.
        warnings.append(
            "no tier is marked adversarial, so gates.refute_attempt must be a genuinely "
            "separate step (perturbed re-run or skeptic pass). Confirm its description "
            "describes an attempt to BREAK a passing result, not to confirm it."
        )

    # Auditing the backend: `adversarial` is a claim about the checker made by
    # the party being checked. These turn it into something with conditions.
    for tier in tiers:
        if not isinstance(tier, dict) or tier.get("adversarial") is not True:
            continue
        name = tier.get("name")
        if tier.get("authorship") != "independent":
            errors.append(
                f"tier {name!r} claims adversarial:true but authorship is "
                f"{tier.get('authorship', 'undeclared')!r}. A backend written by whoever "
                "produces candidates for it cannot be the thing that refuses them."
            )
        if not tier.get("two_sided_evidence"):
            errors.append(
                f"tier {name!r} claims adversarial:true without two_sided_evidence. "
                "A backend nothing has ever failed is unaudited, not trustworthy."
            )
        control = tier.get("negative_control")
        if not control:
            warnings.append(
                f"tier {name!r} declares no negative_control, so adversarial:true stays "
                "an unverified self-report. Register a known-bad artifact it must reject."
            )
        elif not (pack_dir / control).exists():
            errors.append(f"tier {name!r} negative_control {control!r} does not exist in {pack_dir}")

    # A ceiling below the gate it discharges is a contradiction worth catching.
    if satisfied_by:
        tier = next((t for t in tiers if isinstance(t, dict) and t.get("name") == satisfied_by), None)
        if tier and tier.get("max_status") not in (None, "VERIFIED"):
            warnings.append(
                f"tier {satisfied_by!r} discharges the refute-attempt gate but caps status at "
                f"{tier['max_status']!r}. That is legal — passing the gate does not lift a "
                "ceiling — but confirm no admission path reads it as sufficient for VERIFIED."
            )

    sel_errors, sel_warnings = selection_checks(pack)
    errors.extend(sel_errors)
    warnings.extend(sel_warnings)

    prov_errors, prov_warnings = provisional_checks(pack, tiers, pack_dir)
    errors.extend(prov_errors)
    warnings.extend(prov_warnings)

    roles = pack.get("roles")
    if isinstance(roles, dict) and 0 < len(roles) < 3:
        missing = sorted({"explorer", "generator", "researcher"} - set(roles))
        # A partial rename is legitimate and common: a field often has a customary
        # name for one role and none for the others. Report what a run will call
        # them rather than pushing for symmetry that does not exist.
        notes.append(
            f"this pack renames {sorted(roles.items())}; {missing} keep the frame names"
        )

    # Contract item 3 extends frame-receipt-v1. A pack schema that closes itself
    # off, or restates the frame's fields, is not an extension — the first cannot
    # carry the frame's fields at all and the second is a copy that will drift.
    receipt_rel = (pack.get("receipt_format") or {}).get("path")
    if receipt_rel and (pack_dir / receipt_rel).exists():
        try:
            receipt_schema = json.loads((pack_dir / receipt_rel).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{receipt_rel} is not valid JSON — {exc}")
            receipt_schema = {}
        if receipt_schema.get("additionalProperties") is False:
            errors.append(
                f"{receipt_rel} sets additionalProperties:false, so it cannot carry the frame "
                "receipt's fields. Contract item 3 extends frame-receipt-v1; declare only what "
                "this field adds on top")
        frame_required = set(FRAME_RECEIPT_REQUIRED)
        restated = sorted(frame_required & set(receipt_schema.get("properties", {})))
        if restated:
            warnings.append(
                f"{receipt_rel} restates frame receipt fields {restated}. Two definitions of one "
                "field drift, and the copy that drifts is the one nobody re-reads")

    # Declared paths must exist, or the contract points at nothing.
    for label, value in (
        ("claim_schema.path", pack.get("claim_schema", {}).get("path")),
        ("receipt_format.path", pack.get("receipt_format", {}).get("path")),
    ):
        if value and not (pack_dir / value).exists():
            errors.append(f"{label} points at {value!r}, which does not exist in {pack_dir}")

    for index, entry in enumerate(pack.get("doctrine", {}).get("rules", []) or []):
        rule = entry if isinstance(entry, str) else (entry or {}).get("path", "")
        if not (pack_dir / rule).exists():
            warnings.append(f"doctrine.rules[{index}] points at {rule!r}, which does not exist")

    # Per-role doctrine is how a field's instructions actually reach the roles.
    # A path that resolves to nothing means that role has no instructions here.
    for role, rel in (pack.get("doctrine", {}).get("roles", {}) or {}).items():
        if rel and not (pack_dir / rel).exists():
            errors.append(
                f"doctrine.roles.{role} points at {rel!r}, which does not exist in {pack_dir}. "
                f"The {role} role would load nothing when this pack is selected."
            )

    return errors, warnings, notes


def check_reference_data(pack: dict, root: Path) -> list[str]:
    """A declared table that is not there is worse than an undeclared one.

    An undeclared table is a gap in the contract. A declared table that is
    missing is a manifest asserting something false, and the pack still
    validates on every other item while the judgement that rests on the table
    has nothing under it.
    """
    problems: list[str] = []
    for entry in pack.get("reference_data") or []:
        path = root / entry["path"]
        if not path.exists():
            problems.append(f"reference_data declares {entry['path']!r}, which is not there")
            continue
        for script in entry.get("used_by") or []:
            if not (root / script).exists():
                problems.append(f"reference_data {entry['path']!r} names reader {script!r}, "
                                "which is not there")
        cal = entry.get("calibrated_by")
        if cal and not (root / cal).exists():
            problems.append(f"reference_data {entry['path']!r} names calibration {cal!r}, "
                            "which is not there")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("manifest", help="path to a pack's domain.json")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    try:
        pack = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = pack.get("contract_version")
        if version not in SCHEMA_BY_VERSION:
            print(
                f"ERROR: pack declares contract_version {version!r}; this frame implements "
                f"{sorted(SCHEMA_BY_VERSION)}. The frame never infers a version (governance "
                "rule 6).",
                file=sys.stderr,
            )
            return 2
        schema = json.loads((SCHEMA_DIR / SCHEMA_BY_VERSION[version]).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON — {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    validate(pack, schema, "manifest", errors)

    warnings: list[str] = []
    notes: list[str] = []
    if not errors:
        # Semantic checks assume the shape is already valid.
        errors, warnings, notes = semantic_checks(pack, manifest_path.parent)
        errors = list(errors) + check_reference_data(pack, manifest_path.parent)

    name = pack.get("domain", manifest_path.parent.name)
    for note in notes:
        print(f"  note: {note}")
    for warning in warnings:
        print(f"  warning: {warning}")

    if errors:
        print(f"\nDOMAIN PACK '{name}': FAIL — {len(errors)} violation(s)\n")
        for error in errors:
            print(f"  {error}")
        print(
            "\nSee references/domain_pack_contract.md. Every contract item is mandatory; "
            "the refute-attempt gate, the escalation threshold, and (from v2) the selection "
            "block are required precisely so a pack cannot skip them by omission."
        )
        return 1

    items = ("six contract items" if pack.get("contract_version") in {"2", "3"}
             else "five contract items")
    if pack.get("contract_version") == "1":
        print(
            "  note: contract v1 carries no `selection` block, so this pack is resolvable only "
            "by explicit name — scripts/resolve_domain.py will never choose it on its own"
        )
    print(f"DOMAIN PACK '{name}': PASS — all {items} conform")
    return 0


if __name__ == "__main__":
    sys.exit(main())
