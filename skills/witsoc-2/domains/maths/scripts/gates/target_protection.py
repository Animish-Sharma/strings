#!/usr/bin/env python3
"""Target-protection diff.

The easiest way to make something check is to change what it says. This gate
compares the artifact's statement against the frozen target, hash by hash, so
drift is localized rather than merely detected.

Usage:  target_protection.py <artifact> --claim <claim.json> [--json]
Exit:   0 intact, 1 drift, 2 IO error.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# Words whose presence or absence changes what a statement asserts.
QUALIFIERS = ("positive", "negative", "nonzero", "finite", "infinite", "bounded",
              "compact", "unique", "monotone", "continuous", "nonempty", "invertible",
              "prime", "even", "odd", "integral", "closed", "open")
# Quantifiers are deliberately NOT compared for absence: a formal artifact carries
# them in its binders, so "the target says every and the artifact does not" is the
# normal case rather than drift. A SUBSTITUTED quantifier is another matter.
# "a" is deliberately absent from the existential list. It matched "a real
# number" in an honest artifact's GIVEN and reported an existential claim where
# there was an indefinite article — a false positive on the one artifact in the
# set that was meant to pass, which is the failure direction that gets a gate
# switched off rather than fixed.
QUANTIFIER_SETS = {"universal": ("every", "all", "each", "any", "forall"),
                   "existential": ("some", "exists", "there exists", "for some")}
RELATIONS = {"≤": "<=", "≥": ">=", "≠": "!=", "＝": "=", "⩽": "<=", "⩾": ">="}


def relation_multiset(text: str) -> list[str]:
    body = text
    for symbol, ascii_form in RELATIONS.items():
        body = body.replace(symbol, ascii_form)
    return sorted(re.findall(r"<=|>=|!=|<|>|=", body))


def drift_findings(target: str, artifact: str) -> list[str]:
    """Findings only. This can locate drift and can never certify its absence."""
    findings = []
    low_t, low_a = target.lower(), artifact.lower()

    for word in QUALIFIERS:
        in_t = re.search(rf"(?<![\w-]){word}(?![\w-])", low_t) is not None
        in_a = re.search(rf"(?<![\w-]){word}(?![\w-])", low_a) is not None
        if in_a and not in_t:
            findings.append(f"artifact adds the qualifier {word!r}, absent from the frozen target")
        elif in_t and not in_a:
            findings.append(f"artifact drops the qualifier {word!r} present in the frozen target")

    def family(text_: str) -> set[str]:
        return {name for name, words in QUANTIFIER_SETS.items()
                if any(re.search(rf"(?<![\w-]){re.escape(w.strip())}(?![\w-])", text_)
                       for w in words)}

    fam_t, fam_a = family(low_t), family(low_a)
    if fam_t and fam_a and fam_t != fam_a:
        findings.append(f"quantifier changed: target is {sorted(fam_t)}, artifact is {sorted(fam_a)}")

    rel_t, rel_a = relation_multiset(target), relation_multiset(artifact)
    if rel_t and rel_a and rel_t != rel_a:
        findings.append(f"relations differ: target has {rel_t}, artifact has {rel_a}")

    return findings


def normalize(s: str) -> str:
    return " ".join(s.split())

RE_LABEL = re.compile(r"^\s*-?\s*\[[A-Za-z]\w*\]\s*:\s*")


def strip_labels(text: str) -> str:
    """Drop a leading `- [name]:` from each hypothesis."""
    return " ".join(RE_LABEL.sub("", part).strip()
                    for part in re.split(r"(?:^|\s)-\s+", text) if part.strip())


def split_hypotheses(block: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?:^|\s)-\s+", block) if p.strip()]
    return parts or ([block.strip()] if block.strip() else [])


def extract_block(text: str, keyword: str) -> str | None:
    """Pull a GIVEN: or CLAIM: block out of a WIT artifact."""
    m = re.search(rf"^\s*{keyword}:\s*$", text, re.MULTILINE)
    if not m:
        return None
    rest = text[m.end():]
    out = []
    for line in rest.splitlines():
        if re.match(r"^\s*(GIVEN|CLAIM|PROOF|THEOREM|LEMMA|MODULE)\b", line):
            break
        if line.strip():
            out.append(line.strip())
    return normalize(" ".join(out)) if out else None

# Statements that trivially hold — a target weakened into one of these checks
# but establishes nothing.
TRIVIAL = (r"\bTrue\b", r"\bNonempty\b", r"\btrivial\b", r"\b0\s*=\s*0\b")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact"); ap.add_argument("--claim", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        text = Path(a.artifact).read_text(encoding="utf-8")
        claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    frozen = claim.get("frozen_conditions", {})
    problems = []
    compared = []

    for name, keyword in (("given_block", "GIVEN"), ("claim_block", "CLAIM")):
        expected = frozen.get(f"{name}_sha256")
        actual_text = extract_block(text, keyword)
        if expected is None:
            continue
        compared.append(f"{keyword} by frozen hash")
        if actual_text is None:
            problems.append(f"{keyword} block missing from artifact but frozen in the claim")
            continue
        actual = sha(actual_text)
        if actual != expected:
            problems.append(
                f"{keyword} block drifted: frozen {expected[:12]}..., artifact {actual[:12]}...\n"
                f"      artifact reads: {actual_text[:120]}"
            )

    # Fall back when no frozen block hash exists. Without this the gate compared
    # nothing whenever `frozen_conditions.claim_block_sha256` was absent and
    # reported PASS — a no-op on every claim not authored with that optional
    # field, which is every claim from outside this pack's own fixtures. An
    # external evaluation over twelve real library statements caught ZERO of
    # thirty-five deliberate mutations before this existed.
    #
    # The fallback cannot be an equality check. A frozen target is often informal
    # prose while the artifact states it formally, so demanding they match byte
    # for byte rejects every honest artifact — the failure direction that teaches
    # people to route around the gate. So it looks for DRIFT instead: qualifiers
    # the artifact adds or drops, and relations that changed. Weaker than a hash
    # and far better than nothing, and it says which it ran.
    partial = False
    if "CLAIM by frozen hash" not in compared:
        target = claim.get("formal_target") or claim.get("exact_statement") or ""
        artifact_claim = extract_block(text, "CLAIM")
        if target and artifact_claim is not None:
            partial = True
            compared.append("CLAIM by qualifier and relation drift (no frozen hash available)")
            # The GIVEN carries hypotheses the CLAIM does not restate, so a word
            # living there is not missing from the artifact.
            artifact_text = normalize(artifact_claim + " " + (extract_block(text, "GIVEN") or ""))
            problems += drift_findings(normalize(target), artifact_text)
        elif target and artifact_claim is None and not str(a.artifact).endswith(".lean"):
            problems.append("artifact has no CLAIM block to compare against the frozen statement")

    claim_text = extract_block(text, "CLAIM") or ""
    for pattern in TRIVIAL:
        if re.search(pattern, claim_text):
            problems.append(
                f"CLAIM contains {pattern!r} — a target weakened to something trivially "
                "true checks without establishing anything"
            )

    # A binder hypothesis that was never in the frozen GIVEN.
    given_text = extract_block(text, "GIVEN") or ""
    frozen_given = frozen.get("given_text", "")
    if frozen_given and given_text:
        frozen_norm = normalize(strip_labels(frozen_given)).lower()
        for hypothesis in split_hypotheses(given_text):
            # Compare the hypothesis TEXT, not its label. A labelled hypothesis
            # reads as "[hx]: x is real"; comparing that whole string against the
            # frozen text flags every honest artifact, and a gate that fires on
            # everything is one people learn to ignore.
            body = normalize(strip_labels(hypothesis)).lower()
            if body and body not in frozen_norm:
                problems.append(
                    f"GIVEN carries a hypothesis absent from the frozen target: "
                    f"{body[:80]!r}"
                )

    if a.json:
        print(json.dumps({"verdict": "fail" if problems else "pass",
                          "problems": problems}, indent=2))
    elif problems:
        print(f"TARGET PROTECTION: FAIL — {len(problems)} drift finding(s)\n")
        for p in problems:
            print(f"  {p}")
        print("\nDrift is disqualifying, not a tradeoff. Demote the artifact, not the claim.")
    else:
        print(f"TARGET PROTECTION: PASS — {', '.join(compared)}")
        if partial:
            print("  PARTIAL: no frozen block hash on this claim, so only drift checks ran. "
                  "They find drift and cannot certify its absence — freeze "
                  "frozen_conditions.claim_block_sha256 to get the decisive comparison")
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
