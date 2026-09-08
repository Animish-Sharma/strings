#!/usr/bin/env python3
"""Schedule PLAN — read the claim graph as a concurrency structure.

`ARCHITECTURE.md` §5.1 called this "the largest piece of performance the
predecessor left unclaimed" and nothing implemented it. Worse, it read as though
the frame did the scheduling, which contradicts the boundary the skill states in
its own first section: the orchestrator owns fanout, ordering, workers, retries
and cancellation.

Both halves of that are fixed here, and the split is the point:

    THE FRAME PLANS.        Which claims are ready, which are racing, which
                            must wait, and what a cancellation would mean.
                            That is a reading of the dependency graph, and the
                            graph is frame-owned.

    THE ORCHESTRATOR RUNS.  Providers, sessions, workers, retries, cancellation.
                            This emits a plan and returns. It starts nothing.

The reading itself is one structure used twice. The claim graph's dependency
relations already decide closure; the same relations decide concurrency:

    OR group   -> a RACE. Siblings dispatch together and the first pass cancels
                  the rest. Running them in sequence pays the full cost of every
                  approach that was never going to win, which is the actual
                  waste this section is about.
    AND group  -> FAN-OUT over every ready child, looped until nothing is ready.
    a loser    -> SUPERSEDED, never a failure. It lost a race; it was not
                  refuted, and recording it as a failure would feed the
                  escalation ladder a signal that means nothing.

`--governor` costs the plan against the resource governor, so a wave that cannot
be afforded is reported as such rather than emitted and refused one worker at a
time.

Usage:
    schedule.py plan --state <state.json> [--governor gov.json] [--json]
    schedule.py --self-test

Exit: 0 a plan was produced, 3 nothing is ready, 4 the plan exceeds the budget,
      2 usage/IO, 1 self-test failure
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import governor as gv  # noqa: E402

# A claim in one of these is settled for scheduling purposes: it is not work.
SETTLED = {"VERIFIED", "CHECKED_BOUNDED", "CONDITIONAL", "PARTIAL", "REJECTED"}
ACCEPTED = {"VERIFIED", "CHECKED_BOUNDED", "CONDITIONAL", "PARTIAL"}

# Losing a race is NOT a status, and writing it as one was tempting enough that
# the first version of this file did it. The frame's own rule forbids it: a step
# finishing, a budget being spent, a worker returning — process states are never
# epistemic status. A cancelled sibling was not refuted and nothing was learned
# about it, so its status stays exactly where it was, and the cancellation is
# recorded as what it is: a scheduling fact, in `superseded_by`.
#
# The practical difference is revival. A claim marked with a status would need a
# transition to come back; an OPEN claim carrying a scheduling annotation is
# reschedulable the moment the winner turns out to fail, which is the case the
# race exists to survive.
SUPERSEDED_FIELD = "superseded_by"


def ready(state: dict, leased: set[str] | None = None) -> tuple[list[str], list[dict], dict]:
    """Claims that can start now, and the races among them.

    A claim is ready when it is unsettled and its dependencies are discharged:
    every dependency accepted for AND, at least one for OR, nothing at all for
    LEAF. That is the same walk closure uses, which is why this needs no second
    structure to maintain — and why the two cannot drift apart.
    """
    claims = state.get("claims") or {}
    leased = leased or set()
    blocked: dict[str, str] = {}
    runnable: list[str] = []

    for claim_id, claim in claims.items():
        status = claim.get("status", "OPEN")
        if status in SETTLED:
            continue
        if claim.get(SUPERSEDED_FIELD):
            continue      # lost a race; still OPEN, still revivable, not work now
        if claim_id in leased:
            continue      # somebody is on it, and offering it again buys a
                          # duplicate that the reducer refuses after both paid
        mode = claim.get("dependency_mode", "LEAF")
        deps = claim.get("dependencies") or []
        if mode == "LEAF" or not deps:
            runnable.append(claim_id)
            continue
        states = [(claims.get(d) or {}).get("status", "OPEN") for d in deps]
        if mode == "AND":
            if all(s in ACCEPTED for s in states):
                runnable.append(claim_id)
            else:
                waiting = [d for d, s in zip(deps, states) if s not in ACCEPTED]
                blocked[claim_id] = f"AND waits on {waiting}"
        elif mode == "OR":
            if any(s in ACCEPTED for s in states):
                runnable.append(claim_id)
            else:
                blocked[claim_id] = f"OR waits on any of {deps}"

    # Races: the unsettled children of an OR parent. They are alternatives to one
    # another, so the first to pass makes the rest pointless rather than wrong.
    races: list[dict] = []
    in_race: set[str] = set()
    for claim_id, claim in claims.items():
        if claim.get("dependency_mode") != "OR":
            continue
        siblings = [d for d in (claim.get("dependencies") or []) if d in runnable]
        if len(siblings) > 1:
            races.append({"parent": claim_id, "siblings": sorted(siblings),
                          "on_first_pass": "cancel the rest as SUPERSEDED",
                          "why": "alternatives, not requirements — sequencing them pays for "
                                 "every approach that was never going to win"})
            in_race.update(siblings)
    return sorted(runnable), races, blocked


def cost_of(claim: dict) -> tuple[str, int]:
    """Cost tier and estimate for a claim, from what the claim itself declares.

    The frame holds no field's cost model. A pack states a tier's `cost_hint`
    and a claim may carry an estimate; absent both, this reports `moderate` with
    a zero estimate and says so, because inventing a number here would make the
    budget check look enforced while resting on nothing.
    """
    tier = (claim.get("cost_tier") or claim.get("tier_cost_hint") or "moderate")
    return tier, int(claim.get("cost_estimate") or 0)


def plan(state: dict, gov_state: dict | None, leased: set[str] | None = None) -> dict:
    runnable, races, blocked = ready(state, leased)
    claims = state.get("claims") or {}

    wave = []
    for claim_id in runnable:
        tier, cost = cost_of(claims.get(claim_id) or {})
        entry = {"claim_id": claim_id, "cost_tier": tier, "cost_estimate": cost,
                 "in_race": any(claim_id in r["siblings"] for r in races)}
        if gov_state is not None:
            entry["governor"] = gv.ask(gov_state, tier, cost)["verdict"]
        wave.append(entry)

    affordable = [w for w in wave if w.get("governor") != gv.REFUSE]
    unaffordable = [w for w in wave if w.get("governor") == gv.REFUSE]
    total = sum(w["cost_estimate"] for w in wave)

    if not wave:
        verdict, reading = "NOTHING_READY", (
            "no claim is both unsettled and unblocked. Either the target is closed or every "
            "open claim waits on something — and a graph where nothing is ready and nothing "
            "is closed is a finding about the graph, not a quiet stop")
    elif unaffordable and not affordable:
        verdict, reading = "OVER_BUDGET", (
            f"all {len(wave)} ready claim(s) exceed the remaining budget "
            f"({gv.remaining(gov_state):.0f}). Stopping here and reporting what was reached is "
            "a legitimate result; continuing past a ceiling nobody raised is not")
    else:
        verdict, reading = "PLAN", (
            f"{len(affordable)} claim(s) may start concurrently"
            + (f", {len(races)} race group(s) among them" if races else "")
            + (f"; {len(unaffordable)} deferred on budget" if unaffordable else ""))

    return {"verdict": verdict, "wave": wave, "races": races, "blocked": blocked,
            "leased_out": sorted(leased or []),
            "total_cost_estimate": total,
            "budget_remaining": (gv.remaining(gov_state) if gov_state is not None else None),
            "executed_by": "orchestrator — this plans and starts nothing",
            "reading": reading}


def self_test() -> int:
    cases, failures = [], 0

    def st(claims):
        return {"schema": "frame-state-v1", "claims": claims}

    leaf = st({"A": {"claim_id": "A", "status": "OPEN", "dependency_mode": "LEAF"},
               "B": {"claim_id": "B", "status": "OPEN", "dependency_mode": "LEAF"}})
    p = plan(leaf, None)
    cases.append(("independent leaves form one concurrent wave",
                  len(p["wave"]) == 2 and p["verdict"] == "PLAN", p["reading"]))

    and_graph = st({
        "T": {"claim_id": "T", "status": "OPEN", "dependency_mode": "AND",
              "dependencies": ["A", "B"]},
        "A": {"claim_id": "A", "status": "VERIFIED", "dependency_mode": "LEAF"},
        "B": {"claim_id": "B", "status": "OPEN", "dependency_mode": "LEAF"}})
    p = plan(and_graph, None)
    cases.append(("an AND parent waits until every dependency is accepted",
                  "T" in p["blocked"] and [w["claim_id"] for w in p["wave"]] == ["B"],
                  p["blocked"].get("T", "")))

    or_graph = st({
        "T": {"claim_id": "T", "status": "OPEN", "dependency_mode": "OR",
              "dependencies": ["A", "B", "C"]},
        "A": {"claim_id": "A", "status": "OPEN", "dependency_mode": "LEAF"},
        "B": {"claim_id": "B", "status": "OPEN", "dependency_mode": "LEAF"},
        "C": {"claim_id": "C", "status": "OPEN", "dependency_mode": "LEAF"}})
    p = plan(or_graph, None)
    cases.append(("an OR group is reported as a race, not a sequence",
                  len(p["races"]) == 1 and p["races"][0]["siblings"] == ["A", "B", "C"],
                  p["races"][0]["why"] if p["races"] else "no race found"))
    cases.append(("the race's siblings all start together",
                  {w["claim_id"] for w in p["wave"]} >= {"A", "B", "C"},
                  f"wave = {[w['claim_id'] for w in p['wave']]}"))

    won = st({
        "T": {"claim_id": "T", "status": "OPEN", "dependency_mode": "OR",
              "dependencies": ["A", "B"]},
        "A": {"claim_id": "A", "status": "CHECKED_BOUNDED", "dependency_mode": "LEAF"},
        "B": {"claim_id": "B", "status": "OPEN", "dependency_mode": "LEAF",
              "superseded_by": "A"}})
    p = plan(won, None)
    cases.append(("one OR dependency accepted releases the parent",
                  "T" in [w["claim_id"] for w in p["wave"]] and not p["blocked"],
                  f"wave = {[w['claim_id'] for w in p['wave']]}"))
    cases.append(("a race loser is not rescheduled",
                  "B" not in [w["claim_id"] for w in p["wave"]],
                  "B is annotated superseded_by and stays out of the wave"))
    cases.append(("and losing a race did not change its STATUS",
                  won["claims"]["B"]["status"] == "OPEN",
                  "it was not refuted; a process state is never an epistemic one, and an "
                  "OPEN claim is revivable the moment the winner fails"))

    revived = st({
        "T": {"claim_id": "T", "status": "OPEN", "dependency_mode": "OR",
              "dependencies": ["A", "B"]},
        "A": {"claim_id": "A", "status": "FAILED_ATTEMPT", "dependency_mode": "LEAF"},
        "B": {"claim_id": "B", "status": "OPEN", "dependency_mode": "LEAF"}})
    p = plan(revived, None)
    cases.append(("when the winner fails, the alternative is schedulable again",
                  "B" in [w["claim_id"] for w in p["wave"]],
                  "clearing superseded_by returns it to the wave — no status transition needed"))

    closed = st({"A": {"claim_id": "A", "status": "VERIFIED", "dependency_mode": "LEAF"}})
    p = plan(closed, None)
    cases.append(("nothing ready is reported, not returned as an empty plan",
                  p["verdict"] == "NOTHING_READY", p["reading"]))

    deadlock = st({"A": {"claim_id": "A", "status": "OPEN", "dependency_mode": "AND",
                         "dependencies": ["B"]},
                   "B": {"claim_id": "B", "status": "REJECTED", "dependency_mode": "LEAF"}})
    p = plan(deadlock, None)
    cases.append(("a graph blocked behind a rejected dependency says so",
                  p["verdict"] == "NOTHING_READY" and "A" in p["blocked"],
                  p["blocked"].get("A", "")))

    gov = gv.new_state(50, {"expensive": 4})
    pricey = st({"A": {"claim_id": "A", "status": "OPEN", "dependency_mode": "LEAF",
                       "cost_tier": "expensive", "cost_estimate": 500}})
    p = plan(pricey, gov)
    cases.append(("a wave nobody can afford is OVER_BUDGET, not a plan",
                  p["verdict"] == "OVER_BUDGET", p["reading"]))

    mixed = st({"A": {"claim_id": "A", "status": "OPEN", "dependency_mode": "LEAF",
                      "cost_tier": "expensive", "cost_estimate": 500},
                "B": {"claim_id": "B", "status": "OPEN", "dependency_mode": "LEAF",
                      "cost_tier": "expensive", "cost_estimate": 10}})
    p = plan(mixed, gv.new_state(50, {"expensive": 4}))
    cases.append(("an affordable claim still runs when a sibling is too expensive",
                  p["verdict"] == "PLAN" and len([w for w in p["wave"]
                                                  if w["governor"] == gv.REFUSE]) == 1,
                  p["reading"]))

    leased_graph = st({"A": {"claim_id": "A", "status": "OPEN", "dependency_mode": "LEAF"},
                       "B": {"claim_id": "B", "status": "OPEN", "dependency_mode": "LEAF"}})
    p = plan(leased_graph, None, leased={"A"})
    cases.append(("a claim somebody already holds is not offered again",
                  [w["claim_id"] for w in p["wave"]] == ["B"],
                  "offering it twice buys a duplicate the reducer refuses after both have paid"))
    p = plan(leased_graph, None, leased={"A", "B"})
    cases.append(("and a fully leased graph is NOTHING_READY, not empty-and-silent",
                  p["verdict"] == "NOTHING_READY", p["reading"][:90]))

    print("\n  SCHEDULE PLAN SELF-TEST\n")
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
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--state", required=True)
    p_plan.add_argument("--governor")
    p_plan.add_argument("--registry", help="lease ledger; claims leased to somebody else are "
                                           "not offered")
    p_plan.add_argument("--run", help="run id, with --registry")
    p_plan.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.cmd != "plan":
        ap.error("`plan` is the only subcommand (or --self-test)")

    try:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
        gov_state = gv.load(args.governor) if args.governor else None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    leased = set()
    if args.registry and args.run:
        import registry
        leased = registry.held_claims(args.registry, args.run)
    out = plan(state, gov_state, leased)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"SCHEDULE: {out['verdict']} — {out['reading']}")
        for entry in out["wave"]:
            mark = "race" if entry["in_race"] else "    "
            print(f"  [{mark}] {entry['claim_id']:<20} {entry['cost_tier']:<10} "
                  f"cost {entry['cost_estimate']}"
                  + (f"  governor {entry['governor']}" if "governor" in entry else ""))
        for race in out["races"]:
            print(f"  race under {race['parent']}: {', '.join(race['siblings'])} "
                  f"-> {race['on_first_pass']}")
        for claim_id, why in out["blocked"].items():
            print(f"  blocked {claim_id}: {why}")
        print(f"  {out['executed_by']}")
    return {"PLAN": 0, "NOTHING_READY": 3, "OVER_BUDGET": 4}[out["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
