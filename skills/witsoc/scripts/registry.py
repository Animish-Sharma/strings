#!/usr/bin/env python3
"""Run registry and lease ledger — coordination, in the one place that needs a database.

The predecessor keeps its campaign in SQLite with leases and deadlines. Copying
that wholesale would be the wrong move here: this frame's state is
content-addressed and replayable, every revision names its predecessor, and a
mutable table is a worse home for an evidence chain than an append-only file.

But three things genuinely need a transaction, and files cannot give one:

  A REGISTRY   which campaigns exist, where their state lives, and what happened
               to them. Without it a campaign is a directory somebody has to
               remember, and an interrupted one is indistinguishable from one
               nobody started.
  LEASES       who is working which claim, and until when. The scheduler happily
               offers the same claim to every worker that asks; the reducer then
               refuses the second admission on a stale base revision, which is
               correct and arrives after both have paid. A lease is the cheap
               half of that.
  EXPIRY       a worker that dies holding a lease must not hold it forever. A
               lease nobody can break is an outage, so every lease carries a
               deadline and expiry is the default rather than an intervention.

So: SQLite for what is MUTABLE and contended, files for what is EVIDENCE. The
split is the point — nothing here is authoritative about a status, and this
database can be deleted without losing a single verified fact.

Usage:
    registry.py init      --db <path>
    registry.py register  --db <path> --run <id> --state <state.json> [--note ...]
    registry.py runs      --db <path> [--json]
    registry.py acquire   --db <path> --run <id> --claim <id> --actor <id> [--ttl 900]
    registry.py release   --db <path> --run <id> --claim <id> --actor <id>
    registry.py leases    --db <path> --run <id> [--json]
    registry.py --self-test

Exit: 0 ok, 1 refused (lease held, unknown run), 2 IO
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    state_path  TEXT NOT NULL,
    target      TEXT,
    revision    INTEGER,
    outcome     TEXT,
    note        TEXT,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS leases (
    run_id      TEXT NOT NULL,
    claim_id    TEXT NOT NULL,
    actor       TEXT NOT NULL,
    acquired_at REAL NOT NULL,
    expires_at  REAL NOT NULL,
    PRIMARY KEY (run_id, claim_id)
);
"""


def connect(db: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db), isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def register(conn: sqlite3.Connection, run_id: str, state_path: Path,
             note: str | None, now: float) -> dict:
    revision = outcome = target = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            revision, outcome = state.get("revision"), state.get("outcome")
            target = state.get("target_sha256")
        except (OSError, ValueError):
            pass
    conn.execute(
        "INSERT INTO runs (run_id, state_path, target, revision, outcome, note, updated_at) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET "
        "state_path=excluded.state_path, target=excluded.target, revision=excluded.revision, "
        "outcome=excluded.outcome, note=COALESCE(excluded.note, runs.note), "
        "updated_at=excluded.updated_at",
        (run_id, str(state_path), target, revision, outcome, note, now))
    return {"run_id": run_id, "revision": revision, "outcome": outcome}


def acquire(conn: sqlite3.Connection, run_id: str, claim_id: str, actor: str,
            ttl: float, now: float) -> dict:
    """One transaction, because two workers asking at once is the whole point.

    An EXPIRED lease is taken over rather than refused: a worker that died
    holding one must not hold it forever, and a lease nobody can break is an
    outage wearing a safety feature's clothes. Re-acquiring one you already hold
    extends it, so a long job renews instead of racing itself.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT actor, expires_at FROM leases WHERE run_id=? AND claim_id=?",
            (run_id, claim_id)).fetchone()
        if row and row["expires_at"] > now and row["actor"] != actor:
            conn.execute("ROLLBACK")
            return {"granted": False, "held_by": row["actor"],
                    "expires_in": round(row["expires_at"] - now, 1),
                    "reading": f"{claim_id!r} is leased to {row['actor']!r} for another "
                               f"{row['expires_at'] - now:.0f}s. Two workers on one claim is not "
                               "twice the progress: the second admission is refused on a stale "
                               "base revision, after both have paid"}
        took_over = bool(row and row["expires_at"] <= now and row["actor"] != actor)
        conn.execute(
            "INSERT INTO leases (run_id, claim_id, actor, acquired_at, expires_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(run_id, claim_id) DO UPDATE SET "
            "actor=excluded.actor, acquired_at=excluded.acquired_at, "
            "expires_at=excluded.expires_at",
            (run_id, claim_id, actor, now, now + ttl))
        conn.execute("COMMIT")
    except sqlite3.Error:
        conn.execute("ROLLBACK")
        raise
    return {"granted": True, "actor": actor, "expires_in": ttl, "took_over_expired": took_over,
            "reading": (f"took over an expired lease from a worker that did not release it"
                        if took_over else f"leased to {actor!r} for {ttl:.0f}s")}


def release(conn: sqlite3.Connection, run_id: str, claim_id: str, actor: str) -> dict:
    row = conn.execute("SELECT actor FROM leases WHERE run_id=? AND claim_id=?",
                       (run_id, claim_id)).fetchone()
    if row is None:
        return {"released": False, "reading": "no lease to release"}
    if row["actor"] != actor:
        # Releasing somebody else's lease is how one worker cancels another's
        # work without either of them knowing.
        return {"released": False, "held_by": row["actor"],
                "reading": f"{claim_id!r} is leased to {row['actor']!r}, not to {actor!r}"}
    conn.execute("DELETE FROM leases WHERE run_id=? AND claim_id=?", (run_id, claim_id))
    return {"released": True, "reading": f"{claim_id!r} released by {actor!r}"}


def leases(conn: sqlite3.Connection, run_id: str, now: float) -> list[dict]:
    rows = conn.execute("SELECT * FROM leases WHERE run_id=? ORDER BY claim_id",
                        (run_id,)).fetchall()
    return [{"claim_id": r["claim_id"], "actor": r["actor"],
             "expires_in": round(r["expires_at"] - now, 1),
             "expired": r["expires_at"] <= now} for r in rows]


def held_claims(db: str | Path, run_id: str, now: float | None = None) -> set[str]:
    """Claims a scheduler should not offer: leased, and not yet expired."""
    if not Path(db).exists():
        return set()
    now = time.time() if now is None else now
    conn = connect(db)
    try:
        return {r["claim_id"] for r in leases(conn, run_id, now) if not r["expired"]}
    finally:
        conn.close()


def self_test() -> int:
    import tempfile
    cases, failures = [], 0
    tmp = Path(tempfile.mkdtemp(prefix="registry_"))
    db = tmp / "runs.sqlite3"
    state = tmp / "state.json"
    state.write_text(json.dumps({"revision": 3, "outcome": "PARTIAL",
                                 "target_sha256": "a" * 64}))
    conn = connect(db)
    now = 1_000_000.0

    entry = register(conn, "run-1", state, "first", now)
    cases.append(("a run registers with the state it points at",
                  entry["revision"] == 3 and entry["outcome"] == "PARTIAL", str(entry)))

    rows = conn.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"]
    register(conn, "run-1", state, None, now + 1)
    again = conn.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"]
    cases.append(("re-registering the same run updates rather than duplicating",
                  rows == 1 and again == 1, f"{again} row(s)"))

    first = acquire(conn, "run-1", "C1", "worker-a", 900, now)
    cases.append(("a free claim leases", first["granted"], first["reading"]))

    second = acquire(conn, "run-1", "C1", "worker-b", 900, now + 1)
    cases.append(("a held claim is refused, and says who holds it",
                  not second["granted"] and second["held_by"] == "worker-a", second["reading"]))

    renew = acquire(conn, "run-1", "C1", "worker-a", 900, now + 2)
    cases.append(("the holder may renew rather than race itself",
                  renew["granted"] and not renew["took_over_expired"], renew["reading"]))

    stolen = acquire(conn, "run-1", "C1", "worker-b", 900, now + 5000)
    cases.append(("an EXPIRED lease is taken over, not honoured forever",
                  stolen["granted"] and stolen["took_over_expired"], stolen["reading"]))

    wrong = release(conn, "run-1", "C1", "worker-a")
    cases.append(("releasing someone else's lease is refused",
                  not wrong["released"], wrong["reading"]))

    right = release(conn, "run-1", "C1", "worker-b")
    cases.append(("the holder may release", right["released"], right["reading"]))

    acquire(conn, "run-1", "C2", "worker-a", 900, now)
    held = held_claims(db, "run-1", now + 1)
    cases.append(("a scheduler can ask which claims not to offer",
                  held == {"C2"}, f"held: {sorted(held)}"))
    stale = held_claims(db, "run-1", now + 5000)
    cases.append(("and an expired lease stops withholding one",
                  stale == set(), f"held after expiry: {sorted(stale)}"))

    conn.close()
    print("\n  REGISTRY SELF-TEST — coordination, not evidence\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {str(note)[:140]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    print("  Nothing here is authoritative about a status. This database can be deleted "
          "without losing one verified fact.")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    for name in ("init", "register", "runs", "acquire", "release", "leases"):
        s = sub.add_parser(name)
        s.add_argument("--db", required=True)
        s.add_argument("--json", action="store_true")
        if name in ("register", "acquire", "release", "leases"):
            s.add_argument("--run", required=True)
        if name == "register":
            s.add_argument("--state", required=True); s.add_argument("--note")
        if name in ("acquire", "release"):
            s.add_argument("--claim", required=True); s.add_argument("--actor", required=True)
        if name == "acquire":
            s.add_argument("--ttl", type=float, default=900.0)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.cmd:
        ap.error("a subcommand is required (or --self-test)")

    try:
        conn = connect(args.db)
    except sqlite3.Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    now = time.time()
    try:
        if args.cmd == "init":
            out = {"db": args.db, "reading": "registry ready; it holds coordination and never "
                                             "evidence"}
        elif args.cmd == "register":
            out = register(conn, args.run, Path(args.state), args.note, now)
        elif args.cmd == "runs":
            out = {"runs": [dict(r) for r in
                            conn.execute("SELECT * FROM runs ORDER BY updated_at DESC")]}
        elif args.cmd == "acquire":
            out = acquire(conn, args.run, args.claim, args.actor, args.ttl, now)
        elif args.cmd == "release":
            out = release(conn, args.run, args.claim, args.actor)
        else:
            out = {"leases": leases(conn, args.run, now)}
    finally:
        conn.close()

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        if args.cmd == "runs":
            for row in out["runs"]:
                print(f"  {row['run_id']:<20} rev {row['revision']}  {row['outcome']}  "
                      f"{row['state_path']}")
        elif args.cmd == "leases":
            for row in out["leases"]:
                mark = "EXPIRED" if row["expired"] else f"{row['expires_in']:.0f}s"
                print(f"  {row['claim_id']:<16} {row['actor']:<16} {mark}")
        else:
            print(out.get("reading", json.dumps(out)))
    return 0 if out.get("granted", out.get("released", True)) else 1


if __name__ == "__main__":
    sys.exit(main())
