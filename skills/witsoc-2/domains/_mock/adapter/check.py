#!/usr/bin/env python3
"""Mock verification adapter — the frame's test fixture backend.

Implements the frame's adapter signature:

    (candidate artifact, claim, tier) -> (pass/fail, receipt)

Deliberately trivial, but genuinely real: it can fail, it binds its verdict to
the artifact's content hash, and it refuses to pretend a sampled check is an
exact one. That is enough to exercise the whole loop without any field's
toolchain.

Usage:
    check.py --artifact <path> --claim <claim.json> [--tier exact|sampled]

Prints a frame-receipt-v1 to stdout. Exit status: 0 pass, 1 fail, 2 error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

PLACEHOLDER_TOKENS = ("TODO", "FIXME", "placeholder", "omitted")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(content: str, mode: str) -> str:
    if mode == "strip_whitespace":
        return " ".join(content.split())
    return content


def self_test() -> int:
    """Every pack that ships an adversarial tier owes this, and the fixture pack
    owes it most of all: it exists to prove the frame has no hidden domain
    dependency, and a checker nobody has ever seen refuse anything proves nothing
    about the frame it stands in for.

    Three controls, and the accept case carries the weight. A checker that
    rejects everything rejects the negative control too, and looks identical to a
    working one from outside.
    """
    import tempfile

    here = Path(__file__).resolve().parent
    failures = []
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        expected = "alpha\nbeta\ngamma"
        claim = {"claim_id": "MOCK-SELFTEST",
                 "exact_statement": "the artifact is the expected value",
                 "expected_value": expected,
                 "frozen_conditions": {"normalization": "strip_whitespace"}}
        claim["target_sha256"] = sha256(json.dumps(
            {k: v for k, v in claim.items() if k != "target_sha256"},
            sort_keys=True, separators=(",", ":")))
        claim_path = tmp / "claim.json"
        claim_path.write_text(json.dumps(claim, indent=2), encoding="utf-8")

        good = tmp / "good.txt"
        good.write_text(expected + "\n")
        placeholder = tmp / "placeholder.txt"
        placeholder.write_text("alpha\nbeta\nTODO finish this\n")

        cases = [
            (here / "negative_control.txt", 1, "the registered known-bad control"),
            (placeholder, 1, "an artifact still carrying a deferral token"),
            (good, 0, "the honest artifact — a checker that refuses this refuses everything"),
        ]
        print("Controls — the first two must be REJECTED, the third accepted:\n")
        for artifact, want, why in cases:
            proc = subprocess.run(
                [sys.executable, str(here / "check.py"), "--artifact", str(artifact),
                 "--claim", str(claim_path), "--tier", "exact"],
                capture_output=True, text=True)
            ok = proc.returncode == want
            print(f"  {'ok  ' if ok else 'MISS'}  {artifact.name:<24} {why}")
            if not ok:
                failures.append(f"{artifact.name}: exit {proc.returncode}, expected {want}")

    if failures:
        print(f"\nSELF-TEST: FAIL — {len(failures)}")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("\nSELF-TEST: PASS — 2 rejected, 1 accepted")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--artifact")
    parser.add_argument("--claim")
    parser.add_argument("--tier", default="exact", choices=["exact", "sampled"])
    # Part of the calling convention every adapter shares: --json is accepted and
    # ignored here because this fixture only ever emits the receipt. An adapter
    # that rejects the flag cannot be called by the frame at all, which is a
    # failure only an end-to-end run surfaces.
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true",
                        help="run the registered controls; every known-bad one must be rejected")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not (args.artifact and args.claim):
        parser.error("--artifact and --claim are required unless --self-test")

    try:
        raw = Path(args.artifact).read_text(encoding="utf-8")
        claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    frozen = claim.get("frozen_conditions", {})
    mode = frozen.get("normalization", "exact_bytes")
    expected = claim.get("expected_value", "")

    actual = normalize(raw, mode)

    # A gate every field needs; only the token set differs.
    found_placeholder = next((t for t in PLACEHOLDER_TOKENS if t in raw), None)

    if found_placeholder:
        # Named exactly as the manifest declares it. A gate the adapter
        # implements under a different name is a gate nobody can trace from the
        # contract to the code, which is how a declared check quietly becomes
        # an undeclared one.
        verdict, detail = "fail", (f"placeholder-scan: token {found_placeholder!r} present")
    elif args.tier == "exact":
        passed = actual == normalize(expected, mode)
        verdict = "pass" if passed else "fail"
        detail = "exact match" if passed else "artifact does not match expected_value"
    else:
        # Sampled tier: check a seeded subset of lines. A pass here is evidence
        # about the sample, never about the artifact.
        size = int(frozen.get("sample_size", 1))
        lines = actual.splitlines() or [actual]
        expected_lines = normalize(expected, mode).splitlines() or [normalize(expected, mode)]
        rng = random.Random(claim.get("target_sha256", ""))
        indexes = rng.sample(range(len(lines)), min(size, len(lines)))
        mismatched = [i for i in indexes if i >= len(expected_lines) or lines[i] != expected_lines[i]]
        verdict = "fail" if mismatched else "pass"
        detail = (
            f"sampled {len(indexes)} of {len(lines)} line(s); "
            + ("all matched — evidence about the sample only" if not mismatched
               else f"mismatch at line(s) {mismatched}")
        )

    receipt = {
        "receipt_id": f"mock-{sha256(raw + args.tier)[:12]}",
        "target_sha256": claim.get("target_sha256", ""),
        "artifact_sha256": sha256(raw),
        "tier": args.tier,
        "verdict": verdict,
        # The tier's ceiling, frame-required so the reducer can enforce it from
        # the evidence instead of from the admission's word for it.
        "max_status": "VERIFIED" if args.tier == "exact" else "CHECKED_BOUNDED",
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "refute_attempt": {
            "gate_name": "exact-recheck",
            # Only the exact tier is adversarial, so only it discharges the gate.
            "discharged_by": "adversarial_tier" if args.tier == "exact" else "perturbed_rerun",
            "outcome": "survived" if verdict == "pass" else "broken",
            **(
                {}
                if args.tier == "exact"
                else {"perturbation": "seeded subset; the exact tier is still owed before admission"}
            ),
        },
        "completeness": {
            "all_obligations_covered": args.tier == "exact",
            "concluding_step_covered": args.tier == "exact",
            "open_gaps": 0 if args.tier == "exact" else 1,
            "rejections": 1 if verdict == "fail" else 0,
        },
        "environment": {
            "fresh_process": True,
            "fresh_copy": False,
            "restricted_env": False,
            "toolchain_version": "mock/1",
            "seed": claim.get("target_sha256", "")[:16],
        },
        "normalization_applied": mode,
        "log_excerpt": detail,
    }

    receipt["payload_sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print(json.dumps(receipt, indent=2))
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
