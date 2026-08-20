#!/usr/bin/env python3
"""SOC memory — the run's working memory.

Three memories exist in this frame and they are kept apart on purpose:

    frame-state-v1   STATUS.    Only an admission may move it. It is evidence.
    memory.py        WHAT SURVIVES a campaign. Attention plus guarded reuse.
    this file        ATTENTION, within one run. It is allowed to be wrong.

That last permission is the design. Attention that can never be wrong is not
attention, it is evidence — so this file may hold a hunch, and may never hold a
status. Nothing here enters a receipt, and the reducer refuses an admission
whose evidence points at it.

What it holds: what is being pursued now, what the run believes and on what
strength, what has been ruled out and why, what was decided and what that turned
out to be worth, and what is planned. Five sections, small enough to re-read.

## Four things this does that its predecessor did not

**Tiers are frame statuses.** The predecessor invented VERIFIED / CHECKED /
CONJECTURAL alongside the status lattice — two ladders with different rungs and
no rule connecting them, so an insight marked VERIFIED in working memory looked
like a claim that had been through admission. Here the tier is a frame status and
means what it means everywhere else. An insight above CONJECTURE must name its
evidence, because the tier is a claim about evidence and a tier with nothing
behind it is precisely the laundering this file exists to prevent.

**Bound to a target.** A soc file carries the frozen target hash. An unbound one
drifts onto the next problem and brings its conclusions along, which is how a run
inherits confidence it never earned.

**Consolidation says what it dropped.** Memory that compacts silently leaves a
reader unable to tell forgetting from never-knowing. Every consolidation records
what it removed and why.

**Structure is canonical; the rendered text is a view.** The predecessor stored
free text and parsed it back with regexes, which is fragile and — worse — made a
speculative insight indistinguishable from a grounded one to both a reader and a
parser.

Usage:
    soc_memory.py init --out soc.json --target <sha> --goal "..."
    soc_memory.py current --soc S [--pursuing X] [--obstruction Y] [--move Z]
    soc_memory.py insight --soc S --text "..." --tier <status> [--evidence REF]
    soc_memory.py failure --soc S --method M --statement "..." --blocker B \
        --do-not-repeat "..." [--revival "..."]
    soc_memory.py decide --soc S --at "..." --option A --option B --chosen A \
        --reason "..."
    soc_memory.py attribute --soc S --decision ID --outcome "..." --reward R
    soc_memory.py check --soc S --statement "..." --method M      (repeat risk)
    soc_memory.py queue --soc S --task T --state pending|active|done|abandoned
    soc_memory.py consolidate --soc S [--max-insights N]
    soc_memory.py render --soc S [--out run.soc]
    soc_memory.py show --soc S [--json]

Exit: 0 ok · 1 refused, or a HIGH repeat risk · 2 IO/usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from jsonschema_lite import validate  # noqa: E402

TIERS = ["CONJECTURE", "SKETCH", "PARTIAL", "CHECKED_BOUNDED", "CONDITIONAL", "VERIFIED"]
NEEDS_EVIDENCE = set(TIERS) - {"CONJECTURE"}
DEFAULT_MAX_INSIGHTS = 24
# Two statements are the same attempt when they share this many distinctive
# tokens. Deliberately lexical: the frame is standard library only, and a
# similarity model that is present on one machine and absent on another makes
# the repeat gate fire differently in different places, which is worse than
# firing less often.
REPEAT_TOKEN_FLOOR = 3
REPEAT_TOKEN_FLOOR_SHORT = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_]+", (text or "").lower()) if len(t) > 4}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, soc: dict) -> None:
    errors: list[str] = []
    schema = json.loads((SKILL_ROOT / "schemas" / "frame-soc-v1.schema.json")
                        .read_text(encoding="utf-8"))
    validate(soc, schema, "soc", errors)
    if errors:
        raise ValueError("refusing to write an invalid soc: " + "; ".join(errors[:4]))
    path.write_text(json.dumps(soc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def blank(target: str, goal: str) -> dict:
    return {
        "schema": "frame-soc-v1",
        "target_sha256": target,
        "goal": goal,
        "run_status": "RUNNING",
        "current": {"pursuing": "unset", "obstruction": "unset", "move": "unset"},
        "insights": [],
        "failed_approaches": [],
        "decisions": [],
        "queue": [
            {"task": "freeze the target", "state": "pending"},
            {"task": "retrieve prior art and record the empty searches", "state": "pending"},
            {"task": "name the obstructions", "state": "pending"},
            {"task": "attempt refutation before support", "state": "pending"},
        ],
        "progress": {"attempts_since_last_progress": 0, "admitted": 0,
                     "failed_attempts": 0, "insights_recorded": 0},
        "consolidations": [],
    }


def repeat_risk(soc: dict, statement: str, method: str) -> dict:
    """Is this attempt one the run has already made and recorded as failed?

    Matching is on method AND statement together where both are given. Method
    alone catches too much — the same technique applied to a different sub-claim
    is a different attempt — and statement alone catches too little, because the
    interesting repeat is the same statement approached the same way again.
    """
    statement_tokens = tokens(statement)
    floor = REPEAT_TOKEN_FLOOR_SHORT if len(statement_tokens) < 8 else REPEAT_TOKEN_FLOOR
    method_l = (method or "").strip().lower()
    matches = []
    for failure in soc.get("failed_approaches", []):
        failed_method = str(failure.get("method", "")).strip().lower()
        failed_tokens = tokens(failure.get("statement", ""))
        overlap = len(statement_tokens & failed_tokens)
        method_same = bool(method_l) and method_l == failed_method
        statement_same = bool(statement_tokens) and overlap >= floor
        if (method_same and statement_same) or \
           (method_same and not statement_tokens) or \
           (statement_same and not method_l):
            matches.append({**failure, "shared_tokens": overlap})
    return {
        "repeat_risk": "HIGH" if matches else "LOW",
        "matches": matches,
        "reading": ("this attempt matches a recorded failure. Re-running it spends budget to "
                    "learn what is already written down; either change an axis or record why "
                    "this time is different"
                    if matches else
                    "no recorded failure matches. That is not evidence the attempt will work — "
                    "only that the run has not already ruled it out"),
    }


def consolidate(soc: dict, max_insights: int) -> dict:
    """Dedupe and cap, keeping the strongest tier, and say what went.

    An unbounded memory dulls attention: a file with two hundred insights is a
    file nobody re-reads, which is the same as a file with none.
    """
    removed = []
    kept: list[dict] = []
    for insight in soc.get("insights", []):
        duplicate = None
        for existing in kept:
            shared = tokens(existing["text"]) & tokens(insight["text"])
            union = tokens(existing["text"]) | tokens(insight["text"])
            if union and len(shared) / len(union) >= 0.7:
                duplicate = existing
                break
        if duplicate is None:
            kept.append(insight)
            continue
        weaker, stronger = ((duplicate, insight)
                            if TIERS.index(insight["tier"]) > TIERS.index(duplicate["tier"])
                            else (insight, duplicate))
        removed.append({"id": weaker["id"], "text": weaker["text"][:80],
                        "why": f"near-duplicate of {stronger['id']} at a tier no higher"})
        if stronger is insight:
            kept[kept.index(duplicate)] = insight

    if len(kept) > max_insights:
        ordered = sorted(kept, key=lambda i: (TIERS.index(i["tier"]), i.get("recorded_at", "")),
                         reverse=True)
        for dropped in ordered[max_insights:]:
            removed.append({"id": dropped["id"], "text": dropped["text"][:80],
                            "why": f"over the cap of {max_insights}; lowest tier and oldest go "
                                   "first, because attention is the scarce thing here"})
        kept = ordered[:max_insights]

    soc["insights"] = kept
    if removed:
        soc.setdefault("consolidations", []).append(
            {"at": now(), "removed": removed,
             "note": "recorded rather than silent: a reader who cannot tell forgetting from "
                     "never-knowing cannot trust what remains"})
    return {"kept": len(kept), "removed": removed}


def render(soc: dict) -> str:
    out = [f"-- Status: {soc.get('run_status', 'RUNNING')}",
           f"-- Target: {soc['target_sha256'][:16]}...",
           "", f"GOAL: {soc.get('goal', '')}", "", "CURRENT:"]
    for key in ("pursuing", "obstruction", "move"):
        out.append(f"  {key}: {soc.get('current', {}).get(key, 'unset')}")
    out.append("")
    out.append("INSIGHTS:")
    for insight in soc.get("insights", []):
        evidence = f"  [{insight['evidence_ref']}]" if insight.get("evidence_ref") else ""
        out.append(f"  - ({insight['tier']}) {insight['text']}{evidence}")
    out.append("")
    out.append("PROGRESS:")
    for key, value in (soc.get("progress") or {}).items():
        out.append(f"  - {key}: {value}")
    out.append("")
    out.append("FAILED_APPROACHES:")
    for failure in soc.get("failed_approaches", []):
        out.append(f"  - id: {failure['id']}")
        out.append(f"    method: {failure['method']}")
        out.append(f"    statement: {failure['statement']}")
        out.append(f"    blocker: {failure['blocker']}")
        out.append(f"    do_not_repeat: {failure['do_not_repeat']}")
        if failure.get("revival_condition"):
            out.append(f"    revival: {failure['revival_condition']}")
    out.append("")
    decisions = soc.get("decisions") or []
    if decisions:
        out.append("DECISIONS:")
        for decision in decisions:
            reward = f"  reward={decision['reward']}" if decision.get("reward") is not None else ""
            out.append(f"  - {decision['decision_point']}: chose {decision['chosen']}"
                       f" ({decision['reason']}){reward}")
        out.append("")
    out.append("QUEUE:")
    for entry in soc.get("queue", []):
        note = f"  ({entry['why_abandoned']})" if entry.get("why_abandoned") else ""
        out.append(f"  - {entry['task']}: {entry['state']}{note}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init"); i.add_argument("--out", required=True)
    i.add_argument("--target", required=True); i.add_argument("--goal", required=True)

    for name in ("current", "insight", "failure", "decide", "attribute", "check",
                 "queue", "consolidate", "render", "show"):
        p = sub.add_parser(name)
        p.add_argument("--soc", required=True)
        p.add_argument("--json", action="store_true")
        if name == "current":
            p.add_argument("--pursuing"); p.add_argument("--obstruction"); p.add_argument("--move")
        if name == "insight":
            p.add_argument("--text", required=True)
            p.add_argument("--tier", choices=TIERS, default="CONJECTURE")
            p.add_argument("--evidence"); p.add_argument("--scope",
                                                         choices=["local", "global"], default="local")
            p.add_argument("--polarity",
                           choices=["supports", "contradicts", "neutral", "unknown"],
                           default="unknown")
        if name == "failure":
            p.add_argument("--method", required=True); p.add_argument("--statement", required=True)
            p.add_argument("--blocker", required=True)
            p.add_argument("--do-not-repeat", required=True)
            p.add_argument("--revival"); p.add_argument("--evidence")
        if name == "decide":
            p.add_argument("--at", required=True); p.add_argument("--option", action="append",
                                                                  required=True)
            p.add_argument("--chosen", required=True); p.add_argument("--reason", required=True)
        if name == "attribute":
            p.add_argument("--decision", required=True); p.add_argument("--outcome", required=True)
            p.add_argument("--reward", type=float, required=True)
        if name == "check":
            p.add_argument("--statement", default=""); p.add_argument("--method", default="")
        if name == "queue":
            p.add_argument("--task", required=True)
            p.add_argument("--state", choices=["pending", "active", "done", "abandoned"],
                           required=True)
            p.add_argument("--why")
        if name == "consolidate":
            p.add_argument("--max-insights", type=int, default=DEFAULT_MAX_INSIGHTS)
        if name == "render":
            p.add_argument("--out")

    args = ap.parse_args()

    try:
        if args.cmd == "init":
            soc = blank(args.target, args.goal)
            save(Path(args.out), soc)
            print(f"initialized {args.out} for target {args.target[:16]}...")
            print("  Attention, not evidence. Nothing here enters a receipt, and an admission "
                  "whose evidence points here is refused.")
            return 0

        path = Path(args.soc)
        soc = load(path)

        if args.cmd == "current":
            for key in ("pursuing", "obstruction", "move"):
                value = getattr(args, key)
                if value:
                    soc["current"][key] = value
            save(path, soc)
            print(json.dumps(soc["current"], indent=2))
            return 0

        if args.cmd == "insight":
            if args.tier in NEEDS_EVIDENCE and not args.evidence:
                print(f"REFUSED: tier {args.tier} with no --evidence. The tier is a claim about "
                      "evidence, so a tier with nothing behind it is exactly the laundering this "
                      "file exists to prevent. Record it as CONJECTURE, or name what backs it.",
                      file=sys.stderr)
                return 1
            entry = {"id": f"i-{short(args.text)}", "text": args.text, "tier": args.tier,
                     "polarity": args.polarity, "scope": args.scope, "recorded_at": now()}
            if args.evidence:
                entry["evidence_ref"] = args.evidence
            soc["insights"].append(entry)
            soc["progress"]["insights_recorded"] = soc["progress"].get("insights_recorded", 0) + 1
            save(path, soc)
            print(f"recorded {entry['id']} at {args.tier}")
            return 0

        if args.cmd == "failure":
            entry = {"id": f"f-{short(args.method + args.statement)}",
                     "method": args.method, "statement": args.statement,
                     "blocker": args.blocker, "do_not_repeat": args.do_not_repeat,
                     "recorded_at": now()}
            if args.revival:
                entry["revival_condition"] = args.revival
            if args.evidence:
                entry["evidence_ref"] = args.evidence
            soc["failed_approaches"].append(entry)
            soc["progress"]["failed_attempts"] = soc["progress"].get("failed_attempts", 0) + 1
            soc["progress"]["attempts_since_last_progress"] = \
                soc["progress"].get("attempts_since_last_progress", 0) + 1
            save(path, soc)
            print(f"recorded {entry['id']}")
            if not args.revival:
                print("  no revival condition: this route is now closed forever, which is "
                      "rarely what anyone meant")
            return 0

        if args.cmd == "decide":
            entry = {"id": f"d-{short(args.at + args.chosen)}", "decision_point": args.at,
                     "options": args.option, "chosen": args.chosen, "reason": args.reason,
                     "recorded_at": now()}
            soc.setdefault("decisions", []).append(entry)
            save(path, soc)
            print(f"recorded {entry['id']}: chose {args.chosen} of {args.option}")
            return 0

        if args.cmd == "attribute":
            found = None
            for decision in soc.get("decisions", []):
                if decision["id"] == args.decision:
                    decision["outcome"] = args.outcome
                    decision["reward"] = args.reward
                    found = decision
            if found is None:
                print(f"no decision {args.decision!r}", file=sys.stderr)
                return 1
            save(path, soc)
            print(f"{args.decision}: {args.outcome} (reward {args.reward}). "
                  "Attribution is what makes this memory learn rather than accumulate.")
            return 0

        if args.cmd == "check":
            verdict = repeat_risk(soc, args.statement, args.method)
            if args.json:
                print(json.dumps(verdict, indent=2))
            else:
                print(f"REPEAT RISK: {verdict['repeat_risk']}")
                for match in verdict["matches"]:
                    print(f"  {match['id']}: {match['method']} — {match['blocker']}")
                    print(f"    do not repeat: {match['do_not_repeat']}")
                    if match.get("revival_condition"):
                        print(f"    unless: {match['revival_condition']}")
                print(f"  {verdict['reading']}")
            return 1 if verdict["repeat_risk"] == "HIGH" else 0

        if args.cmd == "queue":
            for entry in soc["queue"]:
                if entry["task"] == args.task:
                    entry["state"] = args.state
                    if args.why:
                        entry["why_abandoned"] = args.why
                    break
            else:
                soc["queue"].append({"task": args.task, "state": args.state,
                                     **({"why_abandoned": args.why} if args.why else {})})
            save(path, soc)
            print(f"{args.task}: {args.state}")
            return 0

        if args.cmd == "consolidate":
            result = consolidate(soc, args.max_insights)
            save(path, soc)
            print(f"CONSOLIDATED: {result['kept']} insight(s) kept, "
                  f"{len(result['removed'])} removed")
            for removed in result["removed"]:
                print(f"  dropped {removed['id']}: {removed['why']}")
            return 0

        if args.cmd == "render":
            text = render(soc)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
                print(f"wrote {args.out}")
            else:
                print(text)
            return 0

        if args.cmd == "show":
            if args.json:
                print(json.dumps(soc, indent=2))
            else:
                print(render(soc))
            return 0

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
