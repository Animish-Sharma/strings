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



def rule_path(entry) -> str:
    """A doctrine rule is a path or an object carrying one."""
    return entry if isinstance(entry, str) else (entry or {}).get("path", "")

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
    """Word-boundary match tolerant of plurals and compound separators.

    Technical compound terms routinely alternate between spaces and hyphens,
    for example ``open problem`` and ``open-problem``. Treat those forms as
    equivalent without permitting matches inside a larger alphanumeric token.
    """
    parts = [fold(part) for part in re.split(r"[\s-]+", term.lower()) if part]
    body = r"(?:\s+|-)+".join(parts)
    return re.compile(rf"(?<!\w){body}(?!\w)")



def stage_rules(rules: list, pack_dir: Path, rel: str) -> dict:
    """Group a pack's rules by the moment they are needed.

    A rule with no declared trigger is `always`, which keeps an older pack
    working and costing exactly what it always cost. `always` is a real answer —
    it claims a role cannot take its first step without the document — and it
    should be rare, which is why the resolver prints the count.
    """
    staged: dict[str, list[dict]] = {}
    for entry in rules:
        path = rule_path(entry)
        if not path or not (pack_dir / path).exists():
            continue
        when = entry.get("load_when", "always") if isinstance(entry, dict) else "always"
        roles = entry.get("roles") if isinstance(entry, dict) else None
        why = entry.get("why", "") if isinstance(entry, dict) else ""
        size = (pack_dir / path).stat().st_size
        staged.setdefault(when, []).append(
            {"path": f"{rel}/{path}", "roles": roles or list(ROLES), "why": why,
             "approx_tokens": size // 4})
    return staged


def token_cost(paths: list[str], root: Path) -> int:
    total = 0
    for path in paths:
        candidate = root / path
        if candidate.is_file():
            total += candidate.stat().st_size
    return total // 4

def load_packs() -> tuple[list[dict[str, Any]], list[str]]:
    """Every pack directory with a readable manifest, plus load failures."""
    packs: list[dict[str, Any]] = []
    problems: list[str] = []
    if not DOMAINS_DIR.is_dir():
        # A thin runtime has no domain directory until the first matching pack
        # is activated. Absence is therefore NO_MATCH, not a corrupt install.
        return packs, problems
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
            f"{rel}/{rule_path(r)}" for r in doctrine.get("rules", []) or []
            if (pack_dir / rule_path(r)).exists()
        ],
        # The same rules, staged. A role told to load everything before any work
        # begins pays for thirteen documents to take one step: measured on this
        # pack, 21k tokens of doctrine of which about 4k is used at the moment
        # it arrives. The rest is not free — it is most of the run's context,
        # spent on documents for situations that have not happened.
        "staged_doctrine": stage_rules(doctrine.get("rules", []) or [], pack_dir, rel),
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


def render(result: dict[str, Any], verbose: bool,
           role_filter: list[str] | None = None) -> None:
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
        staged = plan.get("staged_doctrine") or {}
        wanted = role_filter or list(ROLES)

        print("  Load NOW:")
        for role in ROLES:
            if role not in wanted:
                continue
            label = plan["role_names"].get(role)
            shown = f"{role.capitalize()}" + (f" (called {label} here)" if label else "")
            # The GENERIC role contract, which every pack doctrine opens by
            # saying still applies — and which this never named. A load plan
            # that omits a document the role is required to read is not a plan,
            # and its cost was missing from the total for the same reason.
            generic = f"{role}/SKILL.md"
            if (SKILL_ROOT / generic).exists():
                print(f"    {shown + ' (role contract)':<34} {generic}")
            print(f"    {shown + ' (this field)':<34} {plan['role_doctrine'][role]}")
        now = [r for r in staged.get("always", []) if set(r["roles"]) & set(wanted)]
        for entry in now:
            print(f"    {'shared doctrine':<34} {entry['path']}")

        role_docs = [plan["role_doctrine"][r] for r in wanted]
        role_docs += [f"{r}/SKILL.md" for r in wanted
                      if (SKILL_ROOT / f"{r}/SKILL.md").exists()]
        upfront = token_cost(role_docs + [e["path"] for e in now], SKILL_ROOT)
        later = {when: [e for e in entries if set(e["roles"]) & set(wanted)]
                 for when, entries in staged.items() if when != "always"}
        later = {w: e for w, e in later.items() if e}
        if later:
            print("  Load WHEN IT HAPPENS — not before:")
            for when in sorted(later):
                entries = later[when]
                cost = sum(e["approx_tokens"] for e in entries)
                names = ", ".join(Path(e["path"]).name for e in entries)
                print(f"    {when:<16} ~{cost:>5} tok  {names}")
        deferred = sum(e["approx_tokens"] for entries in later.values() for e in entries)
        # SKILL.md is paid by every run before this tool is even called, so a
        # total that omits it understates the only number anyone budgets against.
        route = token_cost(["SKILL.md"], SKILL_ROOT)
        print(f"  First-turn cost  ~{upfront + route} tok, of which ~{route} is SKILL.md "
              "(paid before this ran)")
        print(f"  Doctrine cost    ~{upfront} tok now"
              + (f", ~{deferred} tok deferred" if deferred else "")
              + (f"  (role: {', '.join(wanted)})" if role_filter else
                 "  — pass --role to load one role's share"))
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
    correct, total, lines = held_out_report(packs)
    if lines:
        print("\nHeld-out — statements written without knowledge of the terms:\n")
        for line in lines:
            print(line)
        if total:
            print(f"\n  {correct}/{total} = {correct / total:.0%} across every declared "
                  "held-out set. This is the number that measures generalization; the one "
                  "below measures\n  a fit to the cases the signal lists were written from.")
    print(f"\nSELF-TEST: PASS — {checked} case(s) across {len(packs)} pack(s)")
    return 0


def held_out_report(packs: list[dict]) -> tuple[int, int, list[str]]:
    """Replay statements a pack did NOT write its selection terms from.

    `--self-test` replays each pack's own declared examples, and a perfect score
    there shows a fit to those examples and nothing else — the same hand wrote
    the signals and the cases. That number has been reported honestly for as
    long as it existed and it still cannot measure generalization, because
    nothing it reads came from outside.

    A pack declaring `held_out_cases` points at statements phrased by people who
    did not know the terms. A pack without one is not failing; it is unmeasured,
    and this says which.
    """
    lines: list[str] = []
    total = correct = 0
    for pack in packs:
        rel = pack.get("held_out_cases")
        root = pack["_dir"]
        if not rel:
            lines.append(f"  ....  {pack['domain']:<10} no held-out set declared — the "
                         "self-test number for this pack measures self-consistency only")
            continue
        path = root / rel
        if not path.exists():
            lines.append(f"  MISS  {pack['domain']:<10} declares {rel} and it is not there")
            continue
        blob = json.loads(path.read_text(encoding="utf-8"))
        want = blob.get("expect_domain", pack["domain"])
        hits = 0
        for case in blob.get("cases", []):
            # normalize() first, exactly as the CLI and the self-test do. The
            # first version called decide() on raw text and every case came back
            # NO_MATCH — a held-out set that measures the harness rather than the
            # terms is worse than none, because its number looks like a finding.
            outcome = decide(packs, normalize(case["statement"]))
            got = (outcome.get("domain") if outcome.get("decision") == "SELECTED"
                   else outcome.get("decision"))
            hits += got == want
        count = len(blob.get("cases", []))
        total += count
        correct += hits
        share = hits / count if count else 0.0
        mark = "ok  " if share >= 0.7 else "WARN"
        lines.append(f"  {mark}  {pack['domain']:<10} {hits}/{count} = {share:.0%} on statements "
                     "written without knowledge of its terms")
    return correct, total, lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--statement", help="the problem statement, verbatim")
    group.add_argument("--file", help="file holding the problem statement")
    group.add_argument("--domain", help="select this pack by name, skipping scoring")
    group.add_argument("--list", action="store_true", help="show registered packs")
    group.add_argument("--self-test", action="store_true", help="check every pack's own examples")
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    parser.add_argument("--role", nargs="*", choices=list(ROLES),
                        help="print only this role's doctrine. A run acts as one role at a "
                             "time, and printing all three costs the other two for nothing.")
    parser.add_argument("--explain", action="store_true", help="always show per-pack scores")
    args = parser.parse_args()

    packs, problems = load_packs()
    if not packs and (args.list or args.self_test):
        try:
            from witsoc_core import domain_packages

            packs = domain_packages.routing_packs(SKILL_ROOT)
        except (ImportError, ValueError, OSError) as exc:
            problems.append(f"cannot load dormant package index: {exc}")
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
        render(result, args.explain, args.role)

    return {"SELECTED": 0, "AMBIGUOUS": 3, "NO_MATCH": 4, "UNRESOLVABLE": 5}[result["decision"]]


if __name__ == "__main__":
    sys.exit(main())
