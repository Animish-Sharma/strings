#!/usr/bin/env python3
"""Shared machinery for the archival pack.

This field verifies nothing by computation over measurements. There is no kernel
and no dataset to re-analyse; the evidence is documents, and the question is
whether the documents saying the same thing are actually saying it
independently.

The whole pack turns on one graph property. When five sources agree, that is
either five observations or one observation repeated five times, and the two are
indistinguishable in a bibliography. Collapsing the citation graph to its roots
is what tells them apart, and it is the only operation here that cannot be
argued with.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The frame's ceiling order, copied verbatim from scripts/reducer.py. A pack does
# not get its own ordering.
STATUS_ORDER = ["OPEN", "CONJECTURE", "GAP", "FAILED_ATTEMPT", "REJECTED",
                "CHECKED_BOUNDED", "SKETCH", "PARTIAL", "CONDITIONAL", "VERIFIED"]

# Documentary evidence never reaches VERIFIED. A surviving record is evidence
# that something was written, which is not the same as evidence that it happened,
# and no quantity of records closes that gap.
PACK_CEILING = "CHECKED_BOUNDED"


def rank(status: str) -> int:
    return STATUS_ORDER.index(status) if status in STATUS_ORDER else -1


def weakest(*statuses: str) -> str:
    present = [s for s in statuses if s in STATUS_ORDER]
    return min(present, key=rank) if present else "FAILED_ATTEMPT"


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
    return sha256_text(canonical({k: v for k, v in claim.items() if k != "target_sha256"}))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------ the citation graph

def index(sources: list[dict]) -> dict[str, dict]:
    return {s["id"]: s for s in sources if isinstance(s, dict) and s.get("id")}


def trace(source_id: str, sources: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Walk a source back along `derives_from` to whatever it rests on.

    Returns (roots, cycle). A root is a source in the set that derives from
    nothing else in the set — the earliest thing this chain actually reaches.
    A cycle is two sources citing each other, which is not a chain at all and is
    reported rather than silently broken.
    """
    roots: list[str] = []
    seen: set[str] = set()
    stack = [source_id]
    cycle: list[str] = []
    while stack:
        current = stack.pop()
        if current in seen:
            if current == source_id and len(seen) > 1:
                cycle.append(current)
            continue
        seen.add(current)
        node = sources.get(current)
        if node is None:
            # Derives from something outside the declared set. That is the end
            # of what this ledger can see, and pretending otherwise would invent
            # independence out of missing data.
            roots.append(current)
            continue
        parents = [p for p in (node.get("derives_from") or [])]
        if not parents:
            roots.append(current)
            continue
        for parent in parents:
            if parent in seen:
                cycle.append(f"{current}->{parent}")
                continue
            stack.append(parent)
    return sorted(set(roots)), sorted(set(cycle))


def origin_of(source_id: str, sources: dict[str, dict]) -> str:
    """Two roots by the same author, or from the same institutional archive, are
    one origin. Independence is about who observed, not about how many volumes
    the observation was printed in."""
    node = sources.get(source_id) or {}
    return (node.get("origin") or node.get("author") or source_id).strip().lower()


def independence(claim_sources: list[str], sources: dict[str, dict]) -> dict:
    """Collapse the supporting sources to distinct origins.

    This is the pack's central computation and the whole of its refute gate. The
    number that matters is not how many sources agree — it is how many of them
    are still distinct after the chains are followed home.
    """
    per_source, all_roots, cycles = {}, [], []
    for sid in claim_sources:
        roots, cycle = trace(sid, sources)
        per_source[sid] = roots
        all_roots.extend(roots)
        cycles.extend(cycle)
    origins = {origin_of(r, sources) for r in all_roots}
    return {
        "supporting_sources": len(claim_sources),
        "distinct_roots": sorted(set(all_roots)),
        "distinct_origins": sorted(origins),
        "independent_support": len(origins),
        "collapsed": len(claim_sources) - len(origins),
        "per_source_roots": per_source,
        "cycles": cycles,
    }


def receipt(tier: str, claim: dict, artifact: str | Path, verdict: str,
            max_status: str, **extra: Any) -> dict:
    """A frame-receipt-v1, plus what this field adds. Sealed, because an unsealed
    receipt cannot be bound to an admission."""
    artifact_path = Path(artifact)
    gates = extra.get("gates") or []
    payload = {
        "schema": "archival-receipt-v1",
        "receipt_id": f"arch-{sha256_file(artifact_path)[:12]}-{tier}",
        "target_sha256": claim.get("target_sha256", ""),
        "artifact_sha256": sha256_file(artifact_path),
        "tier": tier,
        "verdict": verdict,
        "produced_at": now(),
        "max_status": weakest(max_status, PACK_CEILING),
        "documentary": True,
        "scope_note": (
            "Support is bounded by the surviving record. A document establishes that something "
            "was written, which is not that it happened; and what did not survive is not evidence "
            "that it did not occur."
        ),
    }
    payload.update(extra)
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
    payload.pop("payload_sha256", None)
    payload["payload_sha256"] = sha256_text(canonical(payload))
    return payload
