#!/usr/bin/env python3
"""Domain pack resolution — the step that decides which pack a problem belongs to.

Before this existed, pack selection was a sentence in SKILL.md ("identify the
field the claim belongs to and look it up") and nothing else. A sentence is not
a mechanism: a registered pack that is never loaded is indistinguishable from a
pack that was never written, and the failure is silent — the roles simply run
with no field doctrine and produce confident, unverifiable work.

This script makes selection mechanical and auditable. It reads only contract
item 6 (`selection`) from each pack manifest and scores an incoming problem
statement against it. Every term that identifies a field lives in that field's
pack; this file carries none of them, which is what keeps it frame-clean
(governance rule 2).

Scoring is deliberately simple, because a resolution the operator cannot
re-derive by hand is one they will stop trusting:

    score = 1 x (distinct signals matched)
          + 3 x (distinct strong signals matched)
          - 3 x (distinct excludes matched)

A pack is SELECTED when it clears its own `min_score` and beats the runner-up by
MARGIN. Within MARGIN of another qualifying pack the answer is AMBIGUOUS, which
is a real outcome and not a failure: a claim can genuinely engage two packs
(ARCHITECTURE.md 2.2). Below every pack's threshold the answer is NO_MATCH, and
the caller improvises a provisional pack (scaffold_domain.py) rather than
proceeding with no doctrine at all.

Resolution FAILS CLOSED. If the winning pack's manifest points at doctrine,
adapter, or schema files that do not exist, the result is UNRESOLVABLE rather
than a selection, because a pack that resolves to missing files is worse than no
pack: the run believes it loaded a field and did not.

Usage:
    resolve_domain.py --statement "<the problem, verbatim>"
    resolve_domain.py --file problem.txt [--json]
    resolve_domain.py --domain <name>          # explicit; skips scoring
    resolve_domain.py --list
    resolve_domain.py --self-test

Exit status:
    0  SELECTED          one pack, files present
    3  AMBIGUOUS         two or more qualifying packs within MARGIN
    4  NO_MATCH          nothing cleared its threshold
    5  UNRESOLVABLE      a pack was chosen but its declared files are missing
    2  usage / IO error
    1  --self-test failures
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DOMAINS_DIR = SKILL_ROOT / "domains"

DEFAULT_MIN_SCORE = 3.0

# How far ahead the winner must be. Two packs within MARGIN of each other are
# reported as ambiguous rather than decided by a fraction of a signal — the
# scoring is not precise enough to justify a confident split at that distance,
# and pretending otherwise is how a run ends up under the wrong doctrine.
MARGIN = 3.0

WEIGHT = {"signals": 1.0, "strong_signals": 3.0, "excludes": -3.0}

ROLES = ("explorer", "generator", "researcher")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


# Suffix folding, so a pack does not have to enumerate plurals by hand.
#
# Three packs hit this independently: `chronicles` did not match the signal
# `chronicle`, and four of one pack's own examples resolved to NO_MATCH until
# every plural was listed. The failure is silent and asymmetric — a missing
# plural does not error, the pack simply never gets selected for a problem it
# owns, and the run proceeds under no doctrine at all.
#
# Deliberately crude. It folds the endings English inflects most and does not
# stem: `bus`/`bu` and `analysis`/`analysi` are exactly the damage a real
# stemmer does to technical vocabulary, so `-ss` and `-is` are left alone. A
# signal it still misses can always be written out in full, which is what the
# packs were doing for all of them.
SUFFIX_ALTERNATION = r"(?:e?s|ies)?"


def fold(word: str) -> str:
    """A pattern matching the word and its ordinary plural forms."""
    escaped = re.escape(word)
    if word.endswith(("ss", "is", "us")) or len(word) < 4:
        return escaped
    if word.endswith("y"):
        return re.escape(word[:-1]) + r"(?:y|ies)"
    if word.endswith("s"):
        # Already plural: match the singular too, so a pack may list either.
        return re.escape(word[:-1]) + r"s?"
    return escaped + SUFFIX_ALTERNATION


def term_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary match, tolerant of ordinary plurals. A multi-word signal
    tolerates any run of whitespace, so a statement broken across lines still
    matches."""
    parts = [fold(p) for p in term.lower().split()]
    body = r"\s+".join(parts)
    return re.compile(rf"(?<![\w-]){body}(?![\w-])")


def load_packs() -> tuple[list[dict[str, Any]], list[str]]:
    """Every pack directory with a readable manifest, plus load failures."""
    packs: list[dict[str, Any]] = []
    problems: list[str] = []
    if not DOMAINS_DIR.is_dir():
        return packs, [f"no domains directory at {DOMAINS_DIR}"]
    for entry in sorted(DOMAINS_DIR.iterdir()):
        manifest = entry / "domain.json"
        if not manifest.is_file():
            continue
        try:
            pack = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{entry.name}: unreadable manifest — {exc}")
            continue
        pack["_dir"] = entry
        packs.append(pack)
    return packs, problems


def score_pack(pack: dict[str, Any], text: str) -> dict[str, Any]:
    selection = pack.get("selection") or {}
    matched: dict[str, list[str]] = {"signals": [], "strong_signals": [], "excludes": []}
    total = 0.0
    for field, weight in WEIGHT.items():
        for term in dict.fromkeys(selection.get(field, []) or []):
            if term_pattern(term).search(text):
                matched[field].append(term)
                total += weight
    return {
        "domain": pack.get("domain", pack["_dir"].name),
        "score": round(total, 2),
        "min_score": float(selection.get("min_score", DEFAULT_MIN_SCORE)),
        "priority": int(selection.get("priority", 0)),
        "explicit_only": bool(selection.get("explicit_only", False)),
        "has_selection": bool(selection),
        "matched": matched,
    }


def load_plan(pack: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """What a run must load for this pack, and what is missing.

    This is the answer to 'will it actually load the field': named files, each
    one checked to exist right now."""
    pack_dir: Path = pack["_dir"]
    rel = pack_dir.relative_to(SKILL_ROOT).as_posix()
    missing: list[str] = []

    def resolve(value: str | None, label: str, required: bool = True) -> str | None:
        if not value:
            if required:
                missing.append(f"{label}: not declared in the manifest")
            return None
        if not (pack_dir / value).exists():
            missing.append(f"{label}: declared as {value!r}, not present")
            return None
        return f"{rel}/{value}"

    doctrine = pack.get("doctrine", {}) or {}
    role_doctrine = doctrine.get("roles", {}) or {}
    plan_roles = {
        role: resolve(role_doctrine.get(role), f"doctrine.roles.{role}") for role in ROLES
    }

    adapter = pack.get("verification_adapter", {}) or {}
    tiers = [t for t in adapter.get("tiers", []) or [] if isinstance(t, dict)]
    corpus = (adapter.get("corpus") or {}).get("entry_point")

    plan = {
        "pack_dir": rel,
        "role_doctrine": plan_roles,
        "shared_doctrine": [
            f"{rel}/{r}" for r in doctrine.get("rules", []) or [] if (pack_dir / r).exists()
        ],
        "adapter": resolve(adapter.get("entry_point"), "verification_adapter.entry_point"),
        "corpus": resolve(corpus, "verification_adapter.corpus.entry_point", required=False),
        "claim_schema": resolve(
            (pack.get("claim_schema") or {}).get("path"), "claim_schema.path"
        ),
        "receipt_schema": resolve(
            (pack.get("receipt_format") or {}).get("path"), "receipt_format.path"
        ),
        "tiers": [
            {
                "name": t.get("name"),
                "cost_hint": t.get("cost_hint"),
                "max_status": t.get("max_status"),
                "adversarial": bool(t.get("adversarial")),
            }
            for t in tiers
        ],
        "refute_attempt_gate": ((pack.get("gates") or {}).get("refute_attempt") or {}).get("name"),
        "blocking_gates": [
            g.get("name")
            for g in ((pack.get("gates") or {}).get("additional") or [])
            if isinstance(g, dict) and g.get("blocking")
        ],
        "escalate_after": (doctrine.get("escalation") or {}).get("max_consecutive_failures"),
        "role_names": pack.get("roles", {}) or {},
        "contract_version": pack.get("contract_version"),
    }

    # The honest ceiling: the strongest status any tier here can support, further
    # capped if the pack is provisional. A run states this up front rather than
    # discovering it after the budget is gone.
    order = ["CONJECTURE", "SKETCH", "PARTIAL", "CHECKED_BOUNDED", "CONDITIONAL", "VERIFIED"]
    reachable = [t.get("max_status") for t in tiers if t.get("max_status") in order]
    ceiling = max(reachable, key=order.index) if reachable else "CONJECTURE"
    provisional = pack.get("provisional")
    if provisional:
        declared = provisional.get("ceiling")
        if declared in order and order.index(declared) < order.index(ceiling):
            ceiling = declared
        plan["provisional"] = {
            "reason": provisional.get("reason"),
            "authored_by": provisional.get("authored_by"),
            "promotion_requirements": provisional.get("promotion_requirements", []),
        }
    plan["max_admissible_status"] = ceiling
    return plan, missing


def decide(packs: list[dict[str, Any]], text: str) -> dict[str, Any]:
    scored = [score_pack(p, text) for p in packs]
    eligible = [s for s in scored if s["has_selection"] and not s["explicit_only"]]
    ranked = sorted(eligible, key=lambda s: (-s["score"], -s["priority"], s["domain"]))
    qualifying = [s for s in ranked if s["score"] >= s["min_score"]]

    result: dict[str, Any] = {
        "scores": ranked,
        "name_only_packs": [s["domain"] for s in scored if not s["has_selection"]],
        "fixture_packs": [s["domain"] for s in scored if s["explicit_only"]],
    }

    if not qualifying:
        result["decision"] = "NO_MATCH"
        result["domain"] = None
        return result

    best = qualifying[0]
    rivals = [s for s in qualifying[1:] if best["score"] - s["score"] < MARGIN]
    if rivals:
        # A tie broken only by priority is still a tie in evidence; say so.
        result["decision"] = "AMBIGUOUS"
        result["domain"] = None
        result["candidates"] = [best["domain"]] + [r["domain"] for r in rivals]
        return result

    result["decision"] = "SELECTED"
    result["domain"] = best["domain"]
    result["margin"] = round(best["score"] - (qualifying[1]["score"] if len(qualifying) > 1 else 0), 2)
    return result


def attach_plan(result: dict[str, Any], packs: list[dict[str, Any]]) -> dict[str, Any]:
    if result.get("decision") not in {"SELECTED", "AMBIGUOUS"}:
        return result
    names = result.get("candidates") or [result["domain"]]
    plans, missing_all = {}, {}
    for name in names:
        pack = next(p for p in packs if p.get("domain", p["_dir"].name) == name)
        plan, missing = load_plan(pack)
        plans[name] = plan
        if missing:
            missing_all[name] = missing
    result["load"] = plans
    if missing_all:
        result["decision"] = "UNRESOLVABLE"
        result["missing"] = missing_all
    return result


def render(result: dict[str, Any], verbose: bool) -> None:
    decision = result["decision"]
    print(f"DECISION: {decision}")

    if verbose or decision in {"NO_MATCH", "AMBIGUOUS"}:
        print("\nScores (threshold in brackets):")
        for s in result.get("scores", []) or []:
            hits = []
            for field, terms in s["matched"].items():
                if terms:
                    hits.append(f"{field}={','.join(sorted(terms))}")
            print(
                f"  {s['domain']:<16} {s['score']:>6}  [{s['min_score']}]"
                + (f"  {' '.join(hits)}" if hits else "  (no terms matched)")
            )
        for label, names in (
            ("declare no selection block — reachable only by --domain", result.get("name_only_packs")),
            ("fixtures, never auto-selected", result.get("fixture_packs")),
        ):
            if names:
                print(f"  ({', '.join(names)}) {label}")

    if decision == "NO_MATCH":
        print(
            "\nNo registered pack covers this problem. Do NOT proceed with no field doctrine:\n"
            "  1. Confirm the field really is unregistered (re-read the statement; try --list).\n"
            "  2. Improvise a provisional pack:\n"
            "       python3 scripts/scaffold_domain.py --domain <name> --from <closest-pack> \\\n"
            "           --statement \"<the problem>\"\n"
            "  3. A provisional pack carries a hard status ceiling. Work done under it is\n"
            "     labelled provisional and cannot reach the status a registered pack supports."
        )
        return

    if decision == "AMBIGUOUS":
        print(
            f"\nWithin {MARGIN} points: {', '.join(result['candidates'])}.\n"
            "This is a real outcome, not an error. Either the claim genuinely engages both\n"
            "packs (ARCHITECTURE.md 2.2 — both are loaded, a fatal objection from either\n"
            "blocks admission), or the statement is underspecified and Explorer narrows it\n"
            "before any budget is spent. Re-run with --domain <name> once decided."
        )

    if decision == "UNRESOLVABLE":
        print("\nA pack was chosen but its manifest points at files that are not there:")
        for name, missing in result.get("missing", {}).items():
            for item in missing:
                print(f"  {name}: {item}")
        print(
            "\nFail closed. A run that loads a pack whose doctrine is absent believes it is\n"
            "operating under a field's rules while operating under none."
        )
        return

    for name, plan in (result.get("load") or {}).items():
        print(f"\nPACK: {name}   (contract v{plan['contract_version']}, {plan['pack_dir']}/)")
        if plan.get("provisional"):
            p = plan["provisional"]
            print(f"  PROVISIONAL — authored by {p['authored_by']}. {p['reason']}")
        print("  Load, before any work begins:")
        for role in ROLES:
            label = plan["role_names"].get(role)
            shown = f"{role.capitalize()}" + (f" (called {label} here)" if label else "")
            print(f"    {shown:<34} {plan['role_doctrine'][role]}")
        for extra in plan["shared_doctrine"]:
            print(f"    {'shared doctrine':<34} {extra}")
        print(f"  Adapter          {plan['adapter']}")
        if plan["corpus"]:
            print(f"  Corpus           {plan['corpus']}")
        print(f"  Claim schema     {plan['claim_schema']}")
        print(f"  Receipt schema   {plan['receipt_schema']}")
        tiers = ", ".join(
            f"{t['name']}({t['cost_hint'] or '?'}, <={t['max_status']}"
            + (", adversarial)" if t["adversarial"] else ")")
            for t in plan["tiers"]
        )
        print(f"  Tiers            {tiers}")
        print(f"  Refute gate      {plan['refute_attempt_gate']}")
        if plan["blocking_gates"]:
            print(f"  Blocking gates   {', '.join(g for g in plan['blocking_gates'] if g)}")
        print(f"  Escalate after   {plan['escalate_after']} consecutive failures on one claim")
        print(f"  Ceiling          {plan['max_admissible_status']} — nothing here may exceed it")


def self_test(packs: list[dict[str, Any]]) -> int:
    """Every declared example must resolve to its own pack; every declared
    counter-example must not. This is what keeps a signal list honest as it
    grows: a term broad enough to steal another pack's example fails here."""
    failures: list[str] = []
    checked = 0
    for pack in packs:
        selection = pack.get("selection") or {}
        name = pack.get("domain", pack["_dir"].name)
        if not selection or selection.get("explicit_only"):
            continue
        for example in selection.get("examples", []) or []:
            checked += 1
            got = decide(packs, normalize(example))
            if got["decision"] != "SELECTED" or got["domain"] != name:
                detail = got.get("domain") or ", ".join(got.get("candidates", [])) or "-"
                failures.append(
                    f"{name}: own example resolves to {got['decision']} ({detail})\n"
                    f"      {example[:100]!r}"
                )
        for counter in selection.get("counter_examples", []) or []:
            checked += 1
            got = decide(packs, normalize(counter))
            if got["decision"] == "SELECTED" and got["domain"] == name:
                failures.append(
                    f"{name}: counter-example was selected anyway — the signal list "
                    f"over-claims\n      {counter[:100]!r}"
                )
    for pack in packs:
        selection = pack.get("selection") or {}
        if selection and not selection.get("explicit_only") and not selection.get("counter_examples"):
            print(
                f"  warning: {pack.get('domain')} declares no counter_examples, so it has never "
                "been tested against the thing it is most likely to over-claim"
            )
    if failures:
        print(f"\nSELF-TEST: FAIL — {len(failures)} of {checked} case(s)\n")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"SELF-TEST: PASS — {checked} case(s) across {len(packs)} pack(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--statement", help="the problem statement, verbatim")
    group.add_argument("--file", help="file holding the problem statement")
    group.add_argument("--domain", help="select this pack by name, skipping scoring")
    group.add_argument("--list", action="store_true", help="show registered packs")
    group.add_argument("--self-test", action="store_true", help="check every pack's own examples")
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    parser.add_argument("--explain", action="store_true", help="always show per-pack scores")
    args = parser.parse_args()

    packs, problems = load_packs()
    for problem in problems:
        print(f"WARNING: {problem}", file=sys.stderr)
    if not packs:
        print(
            "No domain pack is registered. The frame can freeze a target and triage, but "
            "nothing can be admitted without an adapter to say no.",
            file=sys.stderr,
        )
        return 4

    if args.list:
        for pack in packs:
            selection = pack.get("selection") or {}
            name = pack.get("domain", pack["_dir"].name)
            kind = (
                "fixture" if selection.get("explicit_only")
                else "name-only (no selection block)" if not selection
                else f"{len(selection.get('signals', []))} signals, "
                     f"{len(selection.get('strong_signals', []))} strong"
            )
            flag = " PROVISIONAL" if pack.get("provisional") else ""
            print(f"  {name:<16} v{pack.get('contract_version')}{flag}  {kind}")
            if pack.get("description"):
                print(f"                   {pack['description'][:96]}")
        return 0

    if args.self_test:
        return self_test(packs)

    if args.domain:
        match = next(
            (p for p in packs if p.get("domain", p["_dir"].name) == args.domain), None
        )
        if match is None:
            print(f"ERROR: no pack named {args.domain!r} in {DOMAINS_DIR}", file=sys.stderr)
            return 2
        result = {"decision": "SELECTED", "domain": args.domain, "by": "explicit", "scores": []}
    else:
        text = args.statement
        if args.file:
            try:
                text = Path(args.file).read_text(encoding="utf-8")
            except OSError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
        result = decide(packs, normalize(text))

    result = attach_plan(result, packs)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        render(result, args.explain)

    return {"SELECTED": 0, "AMBIGUOUS": 3, "NO_MATCH": 4, "UNRESOLVABLE": 5}[result["decision"]]


if __name__ == "__main__":
    sys.exit(main())
