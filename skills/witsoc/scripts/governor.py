#!/usr/bin/env python3
"""Resource governor — may another expensive worker start, and is there budget.

`ARCHITECTURE.md` listed this in the layer diagram and in the shared-services
paragraph for as long as either existed, and there was no such file. A component
named in an architecture and absent from the tree is worse than an omission: a
reader plans around it, and every run that should have been stopped by it was
not stopped by anything.

Two questions, one answer, because they are the same question asked about
different resources:

    CONCURRENCY   is a slot free at this cost tier? Saturation QUEUES, it does
                  not error — a refused expensive worker and a delayed one have
                  very different consequences for a campaign, and conflating
                  them turns a busy moment into a lost lead.
    BUDGET        has the run spent what it was given? This one REFUSES. A
                  ceiling that queues is not a ceiling.

The budget half is the piece the frame did not have at all. `execution_economics`
described levers and nothing enforced one: a run could be stopped by failures and
by nothing else, in a design whose Researcher role is explicitly "allowed to run
long and expensive on a single blocker". That is exactly the role that needs a
number rather than a temperament.

## What this is not

It does not schedule and it does not dispatch. The orchestrator owns workers,
sessions and cancellation (SKILL.md, Boundary). This answers a question and
returns; whoever asked is free to ignore the answer, and the ledger records that
they did. Recording an override is the point — an unlogged override is
indistinguishable from a decision nobody made.

Usage:
    governor.py init  --out gov.json [--budget 1000000] [--slots cheap=16,moderate=8,expensive=2]
    governor.py ask   --state gov.json --tier expensive [--cost 5000] [--json]
    governor.py start --state gov.json --tier expensive --worker W1 [--cost 5000]
    governor.py done  --state gov.json --worker W1 [--actual-cost 6200]
    governor.py report --state gov.json [--json]
    governor.py --self-test

Exit: 0 ALLOW / ok, 3 QUEUE, 4 REFUSE (budget exhausted), 2 usage/IO, 1 self-test failure
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_SLOTS = {"cheap": 16, "moderate": 8, "expensive": 2}
ALLOW, QUEUE, REFUSE = "ALLOW", "QUEUE", "REFUSE"
EXIT = {ALLOW: 0, QUEUE: 3, REFUSE: 4}


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: str | Path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def new_state(budget: int | None, slots: dict[str, int]) -> dict:
    return {"schema": "frame-governor-v1", "budget_total": budget, "spent": 0,
            "reserved": 0, "slots": dict(slots), "running": {}, "ledger": [],
            "note": ("budget_total null means no ceiling was set. That is a legitimate "
                     "configuration and it is not the same as a large one: nothing will "
                     "stop this run on cost, and the report says so rather than implying "
                     "a limit nobody chose.")}


def remaining(state: dict) -> float:
    total = state.get("budget_total")
    if total is None:
        return float("inf")
    return max(0.0, total - state.get("spent", 0) - state.get("reserved", 0))


def ask(state: dict, tier: str, cost: int) -> dict:
    """The whole decision, as a pure function of the state."""
    limit = state["slots"].get(tier)
    if limit is None:
        return {"verdict": REFUSE, "tier": tier,
                "reading": f"no slot budget is declared for tier {tier!r}. An undeclared tier "
                           "is a configuration gap, and defaulting it to 'allowed' would make "
                           "the governor silent exactly where it is least understood"}
    in_flight = sum(1 for w in state["running"].values() if w["tier"] == tier)
    left = remaining(state)

    if cost and left < cost:
        return {"verdict": REFUSE, "tier": tier, "cost": cost, "remaining": left,
                "in_flight": in_flight,
                "reading": f"this would cost {cost} and {left:.0f} remains of a budget of "
                           f"{state['budget_total']}. A ceiling that queues is not a ceiling — "
                           "the honest move is to stop and report what was reached, which is a "
                           "legitimate result"}
    if in_flight >= limit:
        return {"verdict": QUEUE, "tier": tier, "cost": cost, "remaining": left,
                "in_flight": in_flight, "limit": limit,
                "reading": f"{in_flight} of {limit} {tier} slots are in flight. This queues "
                           "rather than failing: a refused expensive worker and a delayed one "
                           "have different consequences, and conflating them loses leads"}
    return {"verdict": ALLOW, "tier": tier, "cost": cost, "remaining": left,
            "in_flight": in_flight, "limit": limit,
            "reading": f"slot {in_flight + 1} of {limit} at tier {tier}"
                       + (f"; {left:.0f} of budget remains" if left != float("inf")
                          else "; no budget ceiling is set")}


def start(state: dict, tier: str, worker: str, cost: int,
          claim_id: str | None = None) -> dict:
    decision = ask(state, tier, cost)
    if decision["verdict"] != ALLOW:
        state["ledger"].append({"event": "denied", "worker": worker, "tier": tier,
                                "cost": cost, "verdict": decision["verdict"]})
        return decision
    state["running"][worker] = {"tier": tier, "reserved": cost, "claim_id": claim_id}
    state["reserved"] = state.get("reserved", 0) + cost
    state["ledger"].append({"event": "start", "worker": worker, "tier": tier,
                            "cost": cost, "claim_id": claim_id})
    return decision


def record_outcome(state: dict, worker: str, outcome: str) -> dict:
    """Attach what a closed charge actually bought.

    A charge is closed when the work stops, which is BEFORE anyone knows whether
    a status was granted — so every entry carried `outcome: None` and the
    per-admitted-claim report said "nothing was admitted" on runs that admitted
    something. Spend that cannot be tied to what it bought is a ledger of
    prices with no goods.
    """
    for entry in reversed(state.get("ledger", [])):
        if entry.get("event") == "done" and entry.get("worker") == worker:
            entry["outcome"] = outcome
            return {"verdict": ALLOW, "worker": worker, "outcome": outcome}
    return {"verdict": REFUSE,
            "reading": f"no closed charge for worker {worker!r} to attach an outcome to"}


def done(state: dict, worker: str, actual: int | None,
         outcome: str | None = None) -> dict:
    entry = state["running"].pop(worker, None)
    if entry is None:
        return {"verdict": REFUSE, "reading": f"worker {worker!r} is not running. Closing a "
                                              "worker nobody started would credit budget that "
                                              "was never reserved"}
    state["reserved"] = max(0, state.get("reserved", 0) - entry["reserved"])
    charged = entry["reserved"] if actual is None else actual
    state["spent"] = state.get("spent", 0) + charged
    state["ledger"].append({"event": "done", "worker": worker, "tier": entry["tier"],
                            "reserved": entry["reserved"], "charged": charged,
                            "claim_id": entry.get("claim_id"),
                            "outcome": outcome})
    overrun = charged - entry["reserved"]
    return {"verdict": ALLOW, "worker": worker, "charged": charged, "overrun": overrun,
            "remaining": remaining(state),
            "reading": (f"charged {charged}"
                        + (f", {overrun} over its reservation — reservations that are "
                           "routinely low make the ceiling advisory" if overrun > 0 else ""))}



def cost_report(state: dict) -> dict:
    """What a result actually cost, per tier and per admitted claim.

    The governor charged tiers against a `cost_hint` with three values that
    nobody had ever calibrated, so Explorer ranked approaches by "gain per unit
    cost" where the cost was a word. This is the measurement that word was
    standing in for.

    The number that matters is spend per ADMITTED claim rather than per run: a
    tier that is cheap and never closes anything is not cheap, and an expensive
    one that closes on the first attempt may be the cheapest thing available.
    """
    per_tier: dict[str, dict] = {}
    admitted = 0
    for row in state.get("ledger", []):
        if row.get("event") != "done":
            continue
        entry = per_tier.setdefault(row["tier"], {"runs": 0, "spent": 0, "admitted": 0})
        entry["runs"] += 1
        entry["spent"] += row.get("charged", 0)
        if row.get("outcome") == "ADMITTED":
            entry["admitted"] += 1
            admitted += 1
    for tier, entry in per_tier.items():
        entry["per_run"] = round(entry["spent"] / entry["runs"], 2) if entry["runs"] else None
        entry["per_admitted"] = (round(entry["spent"] / entry["admitted"], 2)
                                 if entry["admitted"] else None)
    total = sum(e["spent"] for e in per_tier.values())
    return {"total_spent": total, "admitted_claims": admitted,
            "per_admitted_claim": round(total / admitted, 2) if admitted else None,
            "by_tier": per_tier,
            "reading": (f"{total} spent across {sum(e['runs'] for e in per_tier.values())} run(s) "
                        f"for {admitted} admitted claim(s)"
                        + (f" — {total / admitted:.1f} per admitted claim" if admitted else
                           " — nothing was admitted, so every unit of this bought information "
                           "and no status, which is a real outcome and not a free one"))}


def self_test() -> int:
    cases, failures = [], 0

    state = new_state(1000, {"expensive": 2, "cheap": 4})
        # A charge is closed before anyone knows whether a status was granted, so
    # the outcome has to be attached afterwards. Until it was, every entry read
    # `outcome: None` and the per-admitted-claim report said nothing had been
    # admitted on runs that admitted something.
    st = new_state(100, dict(DEFAULT_SLOTS))
    start(st, "moderate", "w1", 20, claim_id="C-1")
    done(st, "w1", 20)
    before = cost_report(st)
    record_outcome(st, "w1", "ADMITTED")
    after = cost_report(st)
    cases.append(("an outcome attached after the charge reaches the cost report",
                  before.get("admitted_claims", 0) == 0 and after.get("admitted_claims") == 1,
                  f"{before.get('admitted_claims')} -> {after.get('admitted_claims')}"))

    cases.append(("an unknown tier is refused, not allowed by default",
                  ask(state, "mystery", 0)["verdict"] == REFUSE,
                  ask(state, "mystery", 0)["reading"]))

    start(state, "expensive", "W1", 100)
    start(state, "expensive", "W2", 100)
    third = ask(state, "expensive", 100)
    cases.append(("saturation QUEUES rather than erroring",
                  third["verdict"] == QUEUE, third["reading"]))
    cases.append(("a different tier is unaffected by another tier's saturation",
                  ask(state, "cheap", 10)["verdict"] == ALLOW, ask(state, "cheap", 10)["reading"]))

    over = ask(state, "cheap", 5000)
    cases.append(("a request beyond the budget is REFUSED, never queued",
                  over["verdict"] == REFUSE, over["reading"]))

    done(state, "W1", 100)
    cases.append(("finishing a worker frees its slot",
                  ask(state, "expensive", 10)["verdict"] == ALLOW, "slot returned"))
    cases.append(("reservations are released, not double-counted",
                  state["reserved"] == 100 and state["spent"] == 100,
                  f"reserved={state['reserved']} spent={state['spent']}"))

    ghost = done(state, "NEVER_STARTED", 10)
    cases.append(("closing a worker nobody started is refused",
                  ghost["verdict"] == REFUSE, ghost["reading"]))

    # The ceiling actually bites: spend it all, then everything is refused.
    broke = new_state(100, {"cheap": 4})
    start(broke, "cheap", "A", 100)
    done(broke, "A", 100)
    after = ask(broke, "cheap", 1)
    cases.append(("an exhausted budget stops the run",
                  after["verdict"] == REFUSE, after["reading"]))

    unbounded = new_state(None, {"cheap": 1})
    decision = ask(unbounded, "cheap", 10 ** 9)
    cases.append(("no budget set is reported as no ceiling, not as a large one",
                  decision["verdict"] == ALLOW and "no budget ceiling is set" in decision["reading"],
                  decision["reading"]))

    overrun = new_state(1000, {"cheap": 2})
    start(overrun, "cheap", "B", 100)
    closed = done(overrun, "B", 400)
    cases.append(("an overrun is charged and named",
                  closed["overrun"] == 300 and overrun["spent"] == 400, closed["reading"]))

    priced = new_state(10000, {"cheap": 4, "expensive": 4})
    start(priced, "expensive", "W-a", 100, "C1"); done(priced, "W-a", 100, "ADMITTED")
    start(priced, "expensive", "W-b", 100, "C2"); done(priced, "W-b", 100, "FAILED_ATTEMPT")
    start(priced, "cheap", "W-c", 5, "C3"); done(priced, "W-c", 5, "ADMITTED")
    report = cost_report(priced)
    cases.append(("cost is reported per ADMITTED claim, not per run",
                  report["per_admitted_claim"] == 102.5,
                  f"{report['total_spent']} spent, {report['admitted_claims']} admitted "
                  f"-> {report['per_admitted_claim']} each"))
    cases.append(("and per tier, so a tier that never closes anything is visible",
                  report["by_tier"]["expensive"]["per_admitted"] == 200.0
                  and report["by_tier"]["cheap"]["per_admitted"] == 5.0,
                  "the expensive tier cost 200 per admitted claim because half its runs "
                  "closed nothing; the hint said only 'expensive'"))
    barren = new_state(100, {"cheap": 2})
    start(barren, "cheap", "W", 10, "C9"); done(barren, "W", 10, "FAILED_ATTEMPT")
    empty = cost_report(barren)
    cases.append(("a run that admitted nothing says so rather than dividing by zero",
                  empty["per_admitted_claim"] is None and "no status" in empty["reading"],
                  empty["reading"][:120]))

    print("\n  GOVERNOR SELF-TEST\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {note[:140]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 62)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    p_init = sub.add_parser("init"); p_init.add_argument("--out", required=True)
    p_init.add_argument("--budget", type=int)
    p_init.add_argument("--slots", default="")
    for name in ("ask", "start", "done", "report", "cost"):
        s = sub.add_parser(name); s.add_argument("--state", required=True)
        s.add_argument("--json", action="store_true")
        if name in ("ask", "start"):
            s.add_argument("--tier", required=True); s.add_argument("--cost", type=int, default=0)
        if name in ("start", "done"):
            s.add_argument("--worker", required=True)
        if name == "start":
            s.add_argument("--claim")
        if name == "done":
            s.add_argument("--outcome", help="what the run this paid for ended as; "
                                             "ADMITTED is what makes the spend productive")
        if name == "done":
            s.add_argument("--actual-cost", type=int)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.cmd:
        ap.error("a subcommand is required (or --self-test)")

    try:
        if args.cmd == "init":
            slots = dict(DEFAULT_SLOTS)
            for pair in filter(None, args.slots.split(",")):
                key, sep, value = pair.partition("=")
                # `--slots 2` is the obvious thing to type and produced
                # `invalid literal for int() with base 10: ''` — a stack trace
                # where a usage message belongs. A tool that answers a plausible
                # mistake with a Python error teaches people it is fragile.
                if not sep or not value.strip().lstrip("-").isdigit():
                    print(f"ERROR: --slots takes name=count pairs, e.g. "
                          f"'expensive=2,moderate=8'. Got {pair!r}.", file=sys.stderr)
                    return 2
                if key.strip() not in DEFAULT_SLOTS:
                    print(f"ERROR: unknown slot class {key.strip()!r}; this governor knows "
                          f"{sorted(DEFAULT_SLOTS)}", file=sys.stderr)
                    return 2
                slots[key.strip()] = int(value)
            save(args.out, new_state(args.budget, slots))
            print(f"governor initialised at {args.out}: budget "
                  f"{args.budget if args.budget is not None else 'UNSET (no ceiling)'}, "
                  f"slots {slots}")
            return 0

        state = load(args.state)
        if args.cmd == "ask":
            out = ask(state, args.tier, args.cost)
        elif args.cmd == "start":
            out = start(state, args.tier, args.worker, args.cost, getattr(args, "claim", None))
            save(args.state, state)
        elif args.cmd == "done":
            out = done(state, args.worker, args.actual_cost, getattr(args, "outcome", None))
            save(args.state, state)
        elif args.cmd == "cost":
            out = {"verdict": ALLOW, **cost_report(state)}
        else:
            out = {"verdict": ALLOW, "budget_total": state.get("budget_total"),
                   "spent": state.get("spent"), "reserved": state.get("reserved"),
                   "remaining": remaining(state), "running": list(state["running"]),
                   "events": len(state["ledger"]),
                   "reading": "a run stopped on budget is a legitimate result; a run that "
                              "silently continued past one is not"}
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{out['verdict']}: {out.get('reading', '')}")
    return EXIT.get(out["verdict"], 0)


if __name__ == "__main__":
    sys.exit(main())
