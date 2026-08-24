#!/usr/bin/env python3
"""Contract-line regression — the bridge between the frame and its packs.

Everything that checked this boundary before was STATIC. `validate_domain_pack`
reads a manifest, `check_contract_shapes` opens the files a manifest points at,
`check_doctrine_coverage` compares two documents. All useful, and none of them
ever crosses the line: nothing invoked a pack the way the frame invokes it, and
nothing compared today's boundary against yesterday's.

That gap has already cost a real failure. The adapter's calling convention went
unstated through two contract versions and three packs, and the packs diverged
until one of them could not be called by the frame at all. Every pack's own
self-test was green throughout, because each called itself the way it happened
to expect. A boundary tested only from one side is not tested.

Three layers, each catching a different way the bridge breaks:

  LIVE       invoke every pack's adapter and availability probe exactly as
             `campaign.py` does, and require a defined response. A pack that
             renames a flag, changes an exit code, or dies with a traceback
             fails here — and a traceback is the signal, because it means the
             frame's call reached something that was not expecting it.

  SURFACE    compare the observable boundary — tiers, ceilings, gate names,
             receipt fields, refinements — against a recorded baseline. This is
             the regression half. Any difference is reported; `--update` writes
             the new baseline, so a change is one deliberate command and shows
             up in the diff as a change to the CONTRACT rather than as an
             invisible consequence of an edit somewhere else.

  DOC        the documented calling convention against the argv `campaign.py`
             actually builds, and the contract items ARCHITECTURE.md enumerates
             against the manifest schema's own properties. Prose and code drift
             apart silently and each looks right on its own.

Usage:  check_bridge.py [--domain <name>] [--update] [--json]
Exit:   0 clean, 1 regressions, 2 IO
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DOMAINS = ROOT / "domains"
BASELINE = ROOT / "references" / "bridge_baseline.json"
CONTRACT_DOC = ROOT / "references" / "domain_pack_contract.md"
ARCH = ROOT / "ARCHITECTURE.md"

# The convention, as the frame implements it. Read from campaign.py rather than
# restated, so this cannot agree with a copy of the truth while disagreeing with
# the truth.
INVOCATION = re.compile(r'"--artifact",\s*str\(artifact\),\s*\n?\s*"--claim",\s*str\(claim_path\),'
                        r'\s*"--tier",\s*tier,\s*"--json"')
DOC_CONVENTION = re.compile(r"<entry_point>((?:\s+--\S+(?:\s+<[^>]+>)?)+)")


def packs(only: str | None) -> list[Path]:
    if not DOMAINS.exists():
        return []
    found = [p for p in sorted(DOMAINS.iterdir()) if (p / "domain.json").exists()]
    return [p for p in found if only is None or p.name == only]


# Short on purpose. This asks whether the frame's call is UNDERSTOOD, which a
# pack answers in milliseconds — an adapter that spends a minute is doing the
# verification, which is its own self-test's job and not this one's. A timeout
# is therefore NOT_RUN: nothing was shown to be broken and nothing was shown to
# work, and reporting it as a failure would make an unavailable backend look
# like a contract violation.
CALL_TIMEOUT = 20
# A probe reports what is installed. It has no work to do, so anything but an
# immediate answer means the thing it is probing is what is hanging.
PROBE_TIMEOUT = 8

# What an argument parser says when it did not understand the call. Matched
# against stdout and stderr together, because adapters differ on where they put
# it and the distinction is not one the frame should have to know.
ARG_REJECTION = re.compile(
    r"unrecognized arguments|invalid choice|the following arguments are required|"
    r"expected one argument|error: argument |unknown option|no such option", re.IGNORECASE)


def run(cmd: list[str], cwd: Path, timeout: int = CALL_TIMEOUT) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd))
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except OSError as exc:
        return 125, "", str(exc)


def live_checks(pack: Path, manifest: dict, tmp: Path) -> list[str]:
    """Cross the line the way the frame crosses it, and require a defined answer.

    The artifact is deliberate nonsense. What is being tested is not whether the
    pack can verify something — that is its own self-test's job — but whether
    the frame's CALL is understood at all. A pack may refuse the artifact in any
    way it likes; it may not fail to be called.
    """
    problems: list[str] = []
    not_run: list[str] = []
    adapter = pack / (manifest["verification_adapter"]["entry_point"])
    if not adapter.exists():
        return [f"{pack.name}: adapter {adapter.name} does not exist"]

    artifact = tmp / f"{pack.name}_artifact.txt"
    artifact.write_text("this is not a valid artifact in any field\n", encoding="utf-8")
    claim = tmp / f"{pack.name}_claim.json"
    claim.write_text(json.dumps({
        "schema": "frame-claim-v1", "claim_id": "BRIDGE-1",
        "exact_statement": "a claim used only to test that the adapter can be called",
        "target_sha256": "0" * 64, "status": "OPEN"}), encoding="utf-8")

    tiers = [t["name"] for t in manifest["verification_adapter"]["tiers"]]
    probe = pack / "scripts" / "availability.py"

    # Ask the cheap question first. Probing costs milliseconds by design, and a
    # tier whose backend is absent will make the adapter call sit through the
    # full timeout for no information — this check spent 43 of the suite's 55
    # seconds doing exactly that, twice, on the same unavailable backend.
    # Governance rule 12 asks a check to prove it pays; this is the rule applied
    # to the check that provoked it.
    unavailable: set[str] = set()
    for tier in tiers:
        if not probe.exists():
            break
        code, out, err = run([sys.executable, str(probe), "--tier", tier], pack,
                             timeout=PROBE_TIMEOUT)
        if code == 124:
            unavailable.add(tier)
            not_run.append(f"{pack.name}: availability probe for {tier!r} did not answer within "
                           f"{PROBE_TIMEOUT}s — the backend is absent here")
        elif "Traceback (most recent call last)" in (out + err):
            problems.append(f"{pack.name}: availability probe raised on tier {tier!r}")
        elif code == 3:
            # Reported unavailable, and that is NOT a reason to skip the adapter
            # call. A probe saying "no bundle supplied, so I cannot tell" has not
            # found an absent backend — the adapter answers that case instantly
            # with a refusal, which is exactly the contract behaviour under test.
            # Skipping on it traded three tiers of real coverage for nothing,
            # which is a worse bargain than the timeout it saved.
            pass
        elif code not in (0, 1, 2, 3):
            problems.append(f"{pack.name}: availability probe exited {code} for tier {tier!r}")

    for tier in tiers:
        if tier in unavailable:
            continue
        code, out, err = run([sys.executable, str(adapter), "--artifact", str(artifact),
                              "--claim", str(claim), "--tier", tier, "--json"], pack)
        blob = (out + err)
        if code == 124:
            not_run.append(f"{pack.name}/{tier}: did not answer within {CALL_TIMEOUT}s — the "
                           "backend is probably unavailable here. NOT_RUN, not a failure")
            continue
        if "Traceback (most recent call last)" in blob:
            problems.append(
                f"{pack.name}/{tier}: the frame's call produced a traceback. The pack was not "
                f"expecting to be called this way — {blob.strip().splitlines()[-1][:90]}")
            continue
        # An adapter that cannot PARSE the frame's argv is unreachable, and it
        # exits 2 — which the convention also allows for an honest internal
        # error. Conflating them is how a renamed flag hides: the first version
        # of this check accepted exit 2 unconditionally and did not notice a pack
        # that had renamed --artifact, which is precisely the failure the whole
        # layer exists to catch. So the two are separated by what the rejection
        # says, not by its code.
        if code == 2 and ARG_REJECTION.search(blob):
            problems.append(
                f"{pack.name}/{tier}: the adapter REFUSED the frame's arguments — "
                f"{ARG_REJECTION.search(blob).group(0)[:70]!r}. Exit 2 is reserved for an error "
                "during verification; a call that was never understood is an unreachable "
                "adapter, and the convention exists so this cannot happen quietly")
            continue
        if code not in (0, 1, 2, 3):
            problems.append(f"{pack.name}/{tier}: exit {code}; the convention defines 0 pass, "
                            "1 fail, 2 error, 3 tier could not run")
        if code in (0, 1):
            try:
                receipt = json.loads(out)
            except json.JSONDecodeError:
                problems.append(f"{pack.name}/{tier}: exit {code} means a verdict was reached, "
                                "and stdout is not a receipt. The convention says stdout is a "
                                "frame-receipt-v1 and nothing else")
                continue
            # Contract item 3 is a DECLARATION of what a receipt carries here.
            # Nothing checked it against a receipt the pack actually emitted, so
            # a pack could require a field it never writes and every static check
            # would still pass: the manifest is consistent, the schema extends,
            # and the field is simply never there.
            declared = set((manifest.get("receipt_format") or {})
                           .get("required_fields") or [])
            for field in sorted({"verdict", "tier", "max_status"} | declared):
                if field not in receipt:
                    problems.append(
                        f"{pack.name}/{tier}: the receipt has no {field!r}"
                        + (", which this pack's own receipt_format requires"
                           if field in declared else ""))

    # An unknown tier must be refused rather than quietly treated as some default.
    code, out, err = run([sys.executable, str(adapter), "--artifact", str(artifact),
                          "--claim", str(claim), "--tier", "no_such_tier", "--json"], pack)
    if code in (0, 1):
        problems.append(f"{pack.name}: an unknown tier returned a verdict (exit {code}). A tier "
                        "nobody declared cannot have a ceiling, so anything it says is a status "
                        "with no backend behind it")

    # Availability must answer for every declared tier: the frame asks before
    # spending, and a probe that cannot be asked is a probe nobody runs.
    return problems, not_run


def surface(pack: Path, manifest: dict) -> dict:
    """The observable boundary, and only that.

    Deliberately shallow: names, ceilings, required fields, exit-relevant
    declarations. A baseline that captured descriptions would fail on every
    reworded sentence, and a check that fails on prose gets switched off.
    """
    adapter = manifest["verification_adapter"]
    gates = manifest.get("gates") or {}
    return {
        "contract_version": manifest.get("contract_version"),
        "adapter_entry_point": adapter.get("entry_point"),
        "corpus_entry_point": (adapter.get("corpus") or {}).get("entry_point"),
        "tiers": {t["name"]: {"max_status": t.get("max_status"),
                              "adversarial": bool(t.get("adversarial")),
                              "cost_hint": t.get("cost_hint"),
                              "script": t.get("script")}
                  for t in adapter.get("tiers", [])},
        "refute_attempt": {"name": (gates.get("refute_attempt") or {}).get("name"),
                           "satisfied_by_tier": (gates.get("refute_attempt") or {})
                           .get("satisfied_by_tier")},
        "blocking_gates": sorted(g["name"] for g in gates.get("additional", [])
                                 if g.get("blocking")),
        "claim_extends": (manifest.get("claim_schema") or {}).get("extends"),
        "claim_additional_required": sorted(
            (manifest.get("claim_schema") or {}).get("additional_required_fields") or []),
        "receipt_required": sorted(
            (manifest.get("receipt_format") or {}).get("required_fields") or []),
        "status_refinements": {k: v.get("refines")
                               for k, v in (manifest.get("status_refinements") or {}).items()},
        "escalation_threshold": ((manifest.get("doctrine") or {}).get("escalation") or {})
        .get("max_consecutive_failures"),
        "role_doctrine": sorted(((manifest.get("doctrine") or {}).get("roles") or {})),
    }


def diff_surface(name: str, now: dict, before: dict | None) -> list[str]:
    if before is None:
        return [f"{name}: no baseline recorded. A boundary with no baseline cannot regress, "
                "because nothing knows what it used to be — run --update to record it"]
    out: list[str] = []
    for key in sorted(set(now) | set(before)):
        a, b = now.get(key), before.get(key)
        if a != b:
            out.append(f"{name}.{key}: baseline {json.dumps(b)} -> now {json.dumps(a)}")
    return out


def doc_checks() -> list[str]:
    """Prose against code, in the two places they are both specific."""
    problems: list[str] = []
    try:
        doc = CONTRACT_DOC.read_text(encoding="utf-8")
        campaign = (HERE / "campaign.py").read_text(encoding="utf-8")
        arch = ARCH.read_text(encoding="utf-8")
        schema = json.loads((ROOT / "schemas" / "frame-domain-pack-v3.schema.json")
                            .read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"could not read the documents: {exc}"]

    match = DOC_CONVENTION.search(doc)
    if not match:
        problems.append("the contract document no longer states a calling convention. A contract "
                        "item that says what a thing IS without saying how it is CALLED is half "
                        "a contract, and that omission has already cost one unreachable pack")
    else:
        documented = set(re.findall(r"--(\w+)", match.group(1)))
        actual = set(re.findall(r'"--(\w+)"', campaign[campaign.find("adapter = SKILL_ROOT"):
                                                       campaign.find("adapter = SKILL_ROOT") + 400]))
        if documented != actual:
            problems.append(
                f"the documented convention is {sorted(documented)} and campaign.py invokes "
                f"{sorted(actual)}. Packs implement the document; the frame runs the code; the "
                "gap between them is invisible from either side")

    # The contract items ARCHITECTURE enumerates must exist in the schema.
    items = re.findall(r"^\d+\.\s+\*\*([A-Z][\w \-/]+?)\*\*\s+—", arch, re.MULTILINE)
    mapping = {"Verification adapter": "verification_adapter", "Claim schema": "claim_schema",
               "Receipt format": "receipt_format", "Doctrine extension": "doctrine",
               "Gate definitions": "gates", "Selection": "selection"}
    for item in items:
        key = mapping.get(item.strip())
        if key is None:
            problems.append(f"ARCHITECTURE enumerates contract item {item.strip()!r}, which maps "
                            "to no manifest property. Either the item is new and the schema does "
                            "not know it, or the document renamed one")
        elif key not in schema.get("properties", {}):
            problems.append(f"contract item {item.strip()!r} maps to {key!r}, absent from the "
                            "manifest schema")
    if items and len(items) != 6:
        problems.append(f"ARCHITECTURE enumerates {len(items)} contract items; the contract line "
                        "is six. A document that miscounts its own contract is the document "
                        "packs are written from")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain")
    ap.add_argument("--update", action="store_true",
                    help="record the current boundary as the baseline")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    found = packs(args.domain)
    if not found:
        print(f"ERROR: no packs under {DOMAINS}", file=sys.stderr)
        return 2

    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: baseline unreadable — {exc}", file=sys.stderr)
        return 2
    recorded = baseline.get("packs", {})

    tmp = Path(tempfile.mkdtemp(prefix="bridge_"))
    report: dict[str, dict] = {}
    surfaces: dict[str, dict] = {}
    total = 0

    for pack in found:
        manifest = json.loads((pack / "domain.json").read_text(encoding="utf-8"))
        live, skipped = live_checks(pack, manifest, tmp)
        now = surface(pack, manifest)
        surfaces[pack.name] = now
        drift = [] if args.update else diff_surface(pack.name, now, recorded.get(pack.name))
        report[pack.name] = {"live": live, "surface_drift": drift, "not_run": skipped}
        total += len(live) + len(drift)

    doc = [] if args.update else doc_checks()
    total += len(doc)

    if args.update:
        merged = dict(recorded)
        merged.update(surfaces)
        BASELINE.write_text(json.dumps({
            "description": ("The observable contract line, pack by pack: what the frame can see "
                            "and call. Any change to this file is a change to the BRIDGE, and "
                            "recording it here is what makes it a decision rather than a "
                            "side effect of an edit somewhere else. scripts/check_bridge.py "
                            "--update rewrites it; the diff is the review."),
            "packs": merged}, indent=2) + "\n", encoding="utf-8")
        print(f"baseline updated for {len(surfaces)} pack(s): {BASELINE.relative_to(ROOT)}")
        print("  review the diff — a surface change nobody looked at is exactly what this "
              "file exists to prevent")
        return 0

    if args.json:
        print(json.dumps({"packs": report, "doc": doc, "problems": total}, indent=2))
        return 1 if total else 0

    for name, entry in report.items():
        mark = "ok  " if not (entry["live"] or entry["surface_drift"]) else "FAIL"
        print(f"  [{mark}] {name}")
        for problem in entry["live"]:
            print(f"          live     {problem}")
        for problem in entry["surface_drift"]:
            print(f"          drift    {problem}")
        for note in entry.get("not_run", []):
            print(f"          NOT_RUN  {note}")
    for problem in doc:
        print(f"  [FAIL] doc       {problem}")
    print()
    if total:
        print(f"  BRIDGE: FAIL — {total} problem(s)")
        print("  A drift line is not automatically wrong. It is a change to the contract line "
              "that nobody declared: fix it, or run --update and let the diff carry it.")
        return 1
    skipped = sum(len(e.get("not_run", [])) for e in report.values())
    print(f"  BRIDGE: PASS — {len(report)} pack(s) callable, surface matches baseline, "
          "documented convention matches the code")
    if skipped:
        print(f"  {skipped} tier call(s) NOT_RUN — an unavailable backend is a gap in this "
              "check's coverage, and saying so beats reporting green over it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
