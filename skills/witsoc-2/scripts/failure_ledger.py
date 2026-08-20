#!/usr/bin/env python3
"""The failure ledger — escalation, made mechanical.

ARCHITECTURE.md §5 says escalation is a threshold and not a judgement call. Both
registered packs declare a threshold and a carefully written failure-signature
rule. Until this file existed, nothing read either of them: `resolve_domain.py`
printed the number and no code counted anything, so "the ladder escalates
automatically" described an intention.

The reason it has to be mechanical is specific. The decision to stop attacking a
problem directly and escalate it is exactly the decision a system in the middle
of attacking it is worst placed to make — each attempt feels like it is closing
in, and the count is the only thing that is not affected by that feeling.

Two triggers, and the second usually fires first:

1. **Count.** N consecutive failures on one frozen claim, N from the pack.
2. **Repeat.** The same failure signature twice in a row escalates immediately,
   regardless of N. A second attempt that produced an identical signature changed
   nothing the checker could see, and a third will not either. Waiting out the
   count in that state is spending budget to learn what is already known.

A success resets the counter. Nothing else does — not a retry with a different
seed, not a repair that was not attempted, not time passing.

## Signatures

The frame normalizes generically: lowercase, then strip digits, paths, quoted
identifiers, and hex blobs, all of which vary between two instances of the same
failure. The pack's own signature rule is recorded alongside so a reader can see
what was intended, but the frame does not interpret it — that would require the
frame to understand a field's diagnostics, which is the line it does not cross.

Usage:
    failure_ledger.py record --ledger <l.json> --target <sha> --claim <id>
                             --pack <name> --failure-class <c> --detail <text>
    failure_ledger.py success --ledger <l.json> --target <sha> --claim <id>
    failure_ledger.py status  --ledger <l.json> --target <sha> --claim <id>

Exit: 0 continue, 3 ESCALATE, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DOMAINS = SKILL_ROOT / "domains"

DEFAULT_THRESHOLD = 3

# Everything here varies between two occurrences of the same underlying failure.
# Stripping it is what lets "the same failure twice" be recognised at all.
NOISE = [
    (re.compile(r"[/\\][\w./\\-]+"), " <path> "),          # paths
    (re.compile(r"\b0x[0-9a-f]+\b"), " <hex> "),
    (re.compile(r"\b[0-9a-f]{8,}\b"), " <hash> "),
    (re.compile(r"[`'\"][^`'\"]{1,80}[`'\"]"), " <name> "),  # quoted identifiers
    (re.compile(r"\b\d+\b"), " <n> "),
    (re.compile(r"\s+"), " "),
]


def normalize(text: str) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    line = line.lower()
    for pattern, replacement in NOISE:
        line = pattern.sub(replacement, line)
    return line.strip()


def signature(failure_class: str, detail: str) -> str:
    body = f"{(failure_class or 'unclassified').strip().lower()}|{normalize(detail)}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16], body


def pack_policy(pack: str) -> dict:
    """Threshold and signature rule, read from the pack rather than assumed."""
    manifest = DOMAINS / pack / "domain.json"
    if not manifest.is_file():
        return {"pack": pack, "threshold": DEFAULT_THRESHOLD, "rule": None,
                "note": f"no manifest for pack {pack!r}; using the frame default"}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    escalation = (data.get("doctrine") or {}).get("escalation") or {}
    return {
        "pack": pack,
        "threshold": int(escalation.get("max_consecutive_failures", DEFAULT_THRESHOLD)),
        "rule": escalation.get("failure_signature"),
    }


def load(path: Path) -> dict:
    if not path.exists():
        return {"schema": "frame-failure-ledger-v1", "entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, ledger: dict) -> None:
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def history(ledger: dict, target: str, claim: str) -> list[dict]:
    return [e for e in ledger.get("entries", [])
            if e.get("target_sha256") == target and e.get("claim_id") == claim]


def assess(entries: list[dict], threshold: int) -> dict:
    """Consecutive failures since the last success, and why we would escalate."""
    streak: list[dict] = []
    for entry in reversed(entries):
        if entry.get("kind") == "success":
            break
        streak.append(entry)
    streak.reverse()

    reasons = []
    if len(streak) >= 2 and streak[-1].get("signature") == streak[-2].get("signature"):
        reasons.append(
            f"the same failure signature twice in a row ({streak[-1].get('signature')}). The "
            "second attempt changed nothing the checker could see, so a third will not either")
    if len(streak) >= threshold:
        reasons.append(
            f"{len(streak)} consecutive failures against a threshold of {threshold}")

    return {
        "consecutive_failures": len(streak),
        "threshold": threshold,
        "distinct_signatures": len({e.get("signature") for e in streak}),
        "signatures": [e.get("signature") for e in streak],
        "escalate": bool(reasons),
        "reasons": reasons,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("record", "success", "status"):
        p = sub.add_parser(name)
        p.add_argument("--ledger", required=True)
        p.add_argument("--target", required=True)
        p.add_argument("--claim", required=True)
        p.add_argument("--json", action="store_true")
        if name == "record":
            p.add_argument("--pack", required=True)
            p.add_argument("--failure-class", required=True)
            p.add_argument("--detail", default="")
            p.add_argument("--attempt", type=int)
        if name == "status":
            p.add_argument("--pack")
    args = ap.parse_args()

    path = Path(args.ledger)
    try:
        ledger = load(path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "success":
        ledger.setdefault("entries", []).append({
            "kind": "success", "target_sha256": args.target, "claim_id": args.claim})
        save(path, ledger)
        print(json.dumps({"recorded": "success", "consecutive_failures": 0,
                          "escalate": False,
                          "note": "the counter is reset. Only a success resets it — not a retry "
                                  "with a different seed, and not a repair that was not attempted"},
                         indent=2))
        return 0

    if args.cmd == "status":
        policy = pack_policy(args.pack) if args.pack else {"threshold": DEFAULT_THRESHOLD}
        verdict = assess(history(ledger, args.target, args.claim), policy["threshold"])
        print(json.dumps({**verdict, "policy": policy}, indent=2))
        return 3 if verdict["escalate"] else 0

    policy = pack_policy(args.pack)
    sig, body = signature(args.failure_class, args.detail)
    entry = {
        "kind": "failure", "target_sha256": args.target, "claim_id": args.claim,
        "pack": args.pack, "failure_class": args.failure_class,
        "signature": sig, "normalized": body,
        "detail_excerpt": (args.detail or "")[:300],
    }
    if args.attempt is not None:
        entry["attempt"] = args.attempt
    ledger.setdefault("entries", []).append(entry)
    save(path, ledger)

    verdict = assess(history(ledger, args.target, args.claim), policy["threshold"])
    out = {"recorded": sig, "normalized": body, **verdict, "policy": policy}
    if verdict["escalate"]:
        out["action"] = (
            "ESCALATE to the deep-attack role. This is not a recommendation and not a judgement "
            "call: the obstruction goes to the role built to attack it, and direct production "
            "stops on this claim until it comes back.")
    print(json.dumps(out, indent=2))
    return 3 if verdict["escalate"] else 0


if __name__ == "__main__":
    sys.exit(main())
