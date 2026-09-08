#!/usr/bin/env python3
"""Independent review by a second method, not a second opinion.

The frame refuses to produce its own review, and it is right to: a reviewer who
can read the producer's reasoning agrees for free. The consequence was that
`VERIFIED` was unreachable in practice, so every run this skill had ever done
topped out at `CHECKED_BOUNDED` — an honest ceiling, and a permanent one.

What makes a review worth something is not a second pass. It is a second
FAILURE DOMAIN. So this reviews by re-running the pack's adapter at a DIFFERENT
tier from the one that produced the result, and reports the method family the
pack declares for that tier. A tier that inspects shape and a tier that searches
for a counterexample fail for unrelated reasons; two runs of the same tier fail
together and are one check wearing two names.

The reducer already refuses a reviewer who shares the producer's role without
establishing a different family. This does not route around that rule — it
satisfies it, or it declines to.

Three things this deliberately does NOT do:

  * invent a verdict. The reviewing tier runs and its verdict is reported.
  * see the producer's reasoning. It is handed the claim and the artifact, which
    is what a reviewer would be handed.
  * claim independence it cannot demonstrate. `independent` is true only when
    the review's family actually differs from the result's, and the actor id
    comes from the caller — the orchestrator — never from here.

Usage:
    review_harness.py --claim C --artifact A --domain D --tier T
                      --result <result.json> --reviewer-actor ID
                      [--role explorer] [--out review.json]

Exit: 0 review written, 1 the reviewing tier refused the artifact, 2 IO,
      3 the tier could not run, 4 no different family is available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest_tiers(domain: str) -> dict[str, dict]:
    body = json.loads((ROOT / "domains" / domain / "domain.json")
                      .read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, dict):
            if node.get("name") and "authorship" in node:
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
    return {t["name"]: t for t in walk(body)}


def manifest_gates(domain: str) -> list[dict]:
    body = json.loads((ROOT / "domains" / domain / "domain.json")
                      .read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, dict):
            if node.get("name") and node.get("script"):
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
    return list(walk(body))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claim", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--tier", required=True, help="the tier to REVIEW with")
    ap.add_argument("--result", required=True)
    ap.add_argument("--reviewer-actor", required=True)
    ap.add_argument("--role", default="explorer",
                    choices=["explorer", "generator", "researcher"])
    ap.add_argument("--out")
    a = ap.parse_args()

    try:
        result = json.loads(Path(a.result).read_text(encoding="utf-8"))
        claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    tiers = manifest_tiers(a.domain)
    if a.tier not in tiers:
        print(f"ERROR: {a.domain} declares no tier {a.tier!r}", file=sys.stderr)
        return 2
    family = tiers[a.tier].get("method_family")
    produced_by = result.get("method_family")
    if not family:
        print(f"ERROR: {a.domain}/{a.tier} declares no method_family, so this review "
              "could not say what failure domain it covers", file=sys.stderr)
        return 4
    if family == produced_by:
        print(f"NOT_RUN: reviewing with {a.tier!r} would repeat the {family!r} family the "
              "result already used. Two checks that fail together are one check — choose a "
              "tier whose failure domain is different.", file=sys.stderr)
        return 4

    adapter = ROOT / "domains" / a.domain / "scripts" / "check.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(adapter), "--artifact", str(Path(a.artifact).resolve()),
             "--claim", str(Path(a.claim).resolve()), "--tier", a.tier, "--json"],
            capture_output=True, text=True, timeout=2400)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    try:
        receipt = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"NOT_RUN: {a.domain}/{a.tier} produced no readable receipt:\n"
              f"{(proc.stdout + proc.stderr)[:400]}", file=sys.stderr)
        return 3

    verdict_word = receipt.get("verdict")
    verdict = {"pass": "accept", "fail": "reject"}.get(verdict_word, "inconclusive")

    # The frame's review contract names four checks and knows nothing about a
    # pack's gates. The PACK says which of its gates feeds which, in
    # `review_check`; anything no gate feeds is NOT_RUN, which is a first-class
    # answer here and the whole reason a reviewing tier with narrow coverage
    # cannot quietly look like a full one.
    feeds = {g["name"]: g.get("review_check") for g in manifest_gates(a.domain)}
    checks = {name: "NOT_RUN" for name in
              ("target_fidelity", "dependencies", "preconditions", "circularity")}
    seen: dict[str, set] = {k: set() for k in checks}
    for entry in receipt.get("gates", []):
        target = feeds.get(entry.get("gate"))
        if target in seen:
            seen[target].add(entry.get("verdict"))
    for name, verdicts in seen.items():
        if {"fail", "error"} & verdicts:
            checks[name] = "FAIL"
        elif "pass" in verdicts:
            checks[name] = "PASS"

    review = {
        "schema": "frame-review-v1",
        "review_id": f"REV-{sha(a.reviewer_actor + str(result.get('result_id')))[:12]}",
        "target_sha256": claim.get("target_sha256") or result.get("target_sha256"),
        "result_sha256": result.get("payload_sha256") or sha(json.dumps(result, sort_keys=True)),
        "producer_ref": result.get("result_id"),
        "reviewer_ref": a.reviewer_actor,
        "independent": True,
        "verdict": verdict,
        "checks": checks,
        "findings": receipt.get("problems", []) or [],
        "method_family": family,
        "reviewer_role": a.role,
        "actor": {"actor_id": a.reviewer_actor, "attested_by": "orchestrator"},
        "note": (f"reviewed by re-running the {a.tier!r} tier, whose declared failure domain "
                 f"is {family!r}; the result under review came from {produced_by!r}. The "
                 "reviewer was handed the claim and the artifact and nothing the producer "
                 "wrote about them."),
    }
    review["payload_sha256"] = sha(json.dumps(
        {k: v for k, v in review.items() if k != "payload_sha256"}, sort_keys=True))

    text = json.dumps(review, indent=2, ensure_ascii=False) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"review {review['review_id']}: {verdict} by {family} "
              f"(actor {a.reviewer_actor}) -> {a.out}")
    else:
        print(text)
    return 0 if verdict == "accept" else 1


if __name__ == "__main__":
    sys.exit(main())
