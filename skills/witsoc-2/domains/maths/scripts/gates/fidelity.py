#!/usr/bin/env python3
"""Fidelity gate — does the artifact say what the frozen target says.

Runs before Lean is generated, and again on the Lean itself. The kernel proves things about the encoding;
whether the encoding is the target is a different question it cannot answer, and
generating Lean from a drifted claim wastes the expensive tier on the wrong
statement.

Four verdicts, and NO_JUDGE is the important one: with no independent judge
available this returns NO_JUDGE, never a silent pass. A gate that blesses by
default is not a gate.

    FAITHFUL   judges agree the artifact states the frozen target
    DRIFT      the artifact states something else -> back to generation
    SPLIT      judges disagree -> unresolved, treat as DRIFT
    NO_JUDGE   nothing independent was available to ask

Usage:  fidelity.py <artifact> --claim <claim.json> [--judge-verdicts <f.json>] [--json]
Exit: 0 FAITHFUL, 1 DRIFT or SPLIT, 2 IO error, 3 NO_JUDGE.

NO_JUDGE exits 3, not 1, and the difference matters. Exit 1 means the gate looked
and found something; exit 3 means it had nothing to ask. The frame reads 3 as
NOT_RUN, which is a gap and is refused for any status needing this check — while
a report saying "fidelity FAILED" when no judge existed asserts a finding nobody
made. Both block admission; only one of them is true.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from witlib import normalize, parse  # noqa: E402

RE_LEAN_SIGNATURE = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+)*"
    r"(theorem|lemma|example)\s+(.*?)\s*:=", re.MULTILINE | re.DOTALL)


def lean_signature(text: str) -> str:
    """The theorem signature of a Lean artifact, up to the `:=`.

    A .lean file has no CLAIM block, and reporting 'artifact has no CLAIM block'
    for one is not a fidelity finding — it is the gate failing to recognise what
    it was handed, and it reads as drift in the report either way. That is the
    worst kind of false positive: indistinguishable from the true one.
    """
    match = RE_LEAN_SIGNATURE.search(text)
    return normalize(match.group(2)) if match else ""


def deterministic_checks(doc, claim: dict, stated_override: str | None = None) -> list[str]:
    """Model-free checks. These can only find drift, never certify its absence."""
    findings = []
    frozen = normalize(claim.get("formal_target") or claim.get("exact_statement") or "")
    stated = stated_override if stated_override is not None else normalize(doc.claim)
    if not stated:
        findings.append("artifact states nothing this gate can read: no WIT CLAIM block and "
                        "no Lean theorem signature")
        return findings

    fz, st = set(frozen.lower().split()), set(stated.lower().split())
    QUANT = {"all", "every", "some", "exists", "forall", "each", "any"}
    if (fz & QUANT) != (st & QUANT):
        findings.append(f"quantifier words differ: target has {sorted(fz & QUANT)}, "
                        f"artifact has {sorted(st & QUANT)}")
    for word in ("finite", "infinite", "nonzero", "positive", "bounded", "compact"):
        if word in st and word not in fz:
            findings.append(f"artifact adds the qualifier '{word}', absent from the target")
        if word in fz and word not in st:
            findings.append(f"artifact drops the qualifier '{word}' present in the target")
    given = " ".join(g[1] for g in doc.given).lower() if doc is not None else ""
    frozen_given = str(claim.get("frozen_conditions", {}).get("given_text", "")).lower()
    if frozen_given:
        for hypothesis in [h.strip() for h in given.split(".") if h.strip()]:
            if hypothesis and hypothesis not in frozen_given:
                findings.append(f"GIVEN carries a hypothesis not in the frozen target: "
                                f"{hypothesis[:70]!r}")
    return findings

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact"); ap.add_argument("--claim", required=True)
    ap.add_argument("--judge-verdicts", help="JSON list of independent verdicts "
                    "(FAITHFUL/DRIFT); majority decides")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        text = Path(a.artifact).read_text(encoding="utf-8")
        claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    # Two artifact kinds reach this gate. A WIT artifact states its target in a
    # CLAIM block; a Lean artifact states it in the theorem signature. Reading
    # only the first and reporting "no CLAIM block" for the second is the gate
    # failing to recognise its input while producing a finding that is
    # indistinguishable from real drift.
    if a.artifact.endswith(".lean"):
        doc, stated = None, lean_signature(text)
    else:
        doc, stated = parse(text), None

    findings = deterministic_checks(doc, claim, stated)
    # Judgements may also travel IN the frozen claim, which is where they
    # belong: the adapter's calling convention is (artifact, claim, tier) and
    # adding a pack-specific flag to it would make this pack uncallable by the
    # frame. A judgement recorded in the claim is also frozen by its hash, so it
    # cannot be added after the fact to rescue a failing run.
    verdicts = [str(v).upper() for v in (claim.get("fidelity_judgements") or [])]
    if a.judge_verdicts:
        try:
            payload = json.loads(Path(a.judge_verdicts).read_text(encoding="utf-8"))
            verdicts = [str(v).upper() for v in (payload if isinstance(payload, list)
                        else payload.get("verdicts", []))]
        except (OSError, json.JSONDecodeError):
            verdicts = []

    if findings:
        verdict, why = "DRIFT", "deterministic checks found drift; no judge can override this"
    elif not verdicts:
        verdict, why = "NO_JUDGE", ("no independent verdicts supplied. Deterministic checks "
            "found nothing, but they can only FIND drift, never certify its absence. "
            "This is not a pass.")
    else:
        faithful = verdicts.count("FAITHFUL")
        if faithful > len(verdicts) / 2:
            verdict, why = "FAITHFUL", f"{faithful}/{len(verdicts)} independent judges agree"
        elif faithful == len(verdicts) / 2:
            verdict, why = "SPLIT", "judges are evenly divided; treat as DRIFT until resolved"
        else:
            verdict, why = "DRIFT", f"only {faithful}/{len(verdicts)} judged it faithful"

    out = {"verdict": verdict, "why": why, "findings": findings,
           "judge_verdicts": verdicts,
           "frozen_target": claim.get("formal_target") or claim.get("exact_statement"),
           "artifact_claim": stated if doc is None else normalize(doc.claim),
           "artifact_kind": "lean" if doc is None else "wit",
           "gate_note": "a fidelity record saying not-faithful is a demotion; a MISSING "
                        "record is equally an error"}
    if a.json: print(json.dumps(out, indent=2))
    else:
        print(f"FIDELITY: {verdict}\n  {why}")
        for f in findings: print(f"    {f}")
    return {"FAITHFUL": 0, "NO_JUDGE": 3}.get(verdict, 1)
if __name__ == "__main__":
    sys.exit(main())
