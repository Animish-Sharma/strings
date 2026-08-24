#!/usr/bin/env python3
"""Cross-run memory, adversarially.

`ARCHITECTURE.md` calls this "the only part of the frame that compounds across
runs, and the only store that can launder an answer back in as a prior" — and it
was the one load-bearing component with no test at all. Working memory got a
MECHANICAL laundering guard (an insight id is not sixty-four hex characters; the
reducer refuses evidence that hashes to one). This got prose.

The absence had already cost something. `campaign.py` called `record-result`
without the required `--context`, the call failed, the exit code was discarded,
and every campaign printed "a later campaign starts from what this one learned"
over an empty file. A step that reports success while doing nothing is the exact
failure this frame exists to make impossible, and nothing noticed for as long as
the call existed.

The cases below are the ones that matter for a store that can put an answer back
into a later run: does a hit require the SAME context, does a failure record
actually block a repeat, and is a revival a deliberate act rather than a default.

Usage:  memory_selftest.py [--json]
Exit:   0 all pass, 1 failures
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def hit(out) -> bool:
    """A reuse hit, however the command chose to say it.

    The first version parsed the output as JSON and read a `hit` key, so a plain
    text answer — which is what the command actually returns — read as a miss.
    A test that only understands one output shape reports the tool broken when
    the tool is fine, and that is worse than no test: it gets muted.
    """
    if isinstance(out, dict):
        return bool(out.get("hit") or out.get("reusable"))
    text = str(out).upper()
    # "NO REUSE:" contains "REUSE:". Checking the negative first is the whole
    # fix, and it is the fourth substring collision in this project — the others
    # were `rat` inside `proliferation`, `a ` inside `a real number`, and
    # `shared error` failing to match "share an error". A containment test on
    # prose is a coin flip with extra steps.
    if "NO REUSE" in text:
        return False
    return "REUSE:" in text or "CONTEXT MATCHES" in text


def mem(*args: str) -> tuple[int, dict | str]:
    proc = subprocess.run([sys.executable, str(HERE / "memory.py"), *args],
                          capture_output=True, text=True, timeout=60)
    body = (proc.stdout or proc.stderr).strip()
    try:
        return proc.returncode, json.loads(body)
    except json.JSONDecodeError:
        return proc.returncode, body


def self_test() -> int:
    cases, failures = [], 0
    tmp = Path(tempfile.mkdtemp(prefix="memtest_"))
    store = tmp / "mem.json"
    ctx = json.dumps({"pack": "alpha", "tier": "primary", "claim_id": "C1"})
    other = json.dumps({"pack": "alpha", "tier": "secondary", "claim_id": "C1"})
    stmt = "the frozen statement this store was asked to remember"

    code, _ = mem("init", "--out", str(store))
    cases.append(("a store initialises", code == 0, str(store)))

    code, out = mem("record-result", "--mem", str(store), "--statement", stmt,
                    "--admission-id", "ADM-1", "--context", ctx)
    cases.append(("a result records, and says so by exit code",
                  code == 0, str(out)[:100]))
    entries = json.loads(store.read_text()).get("reuse") or []
    cases.append(("and it actually lands in the file",
                  len(entries) == 1,
                  f"{len(entries)} entry(ies) — the bug this file exists for wrote none"))

    code, out = mem("reuse", "--mem", str(store), "--statement", stmt, "--context", ctx)
    cases.append(("the same statement in the SAME context is a hit",
                  hit(out), str(out)[:110]))

    code, out = mem("reuse", "--mem", str(store), "--statement", stmt, "--context", other)
    miss = not hit(out)
    cases.append(("the same statement in a DIFFERENT context is not",
                  miss,
                  "a cache keyed on anything looser than full context is how an answer "
                  "launders itself back in as a prior"))

    code, out = mem("reuse", "--mem", str(store), "--statement",
                    "a statement nobody recorded", "--context", ctx)
    unknown = not hit(out)
    cases.append(("an unrecorded statement is not a hit", unknown, str(out)[:90]))

    code, out = mem("record-failure", "--mem", str(store), "--statement", stmt,
                    "--method", "primary", "--why", "the backend rejected the candidate at the same place twice",
                    "--revival", "a sub-result that discharges that place, or a different approach")
    cases.append(("a failure records, and a malformed call does NOT report success",
                  code == 0, str(out)[:110]))
    code, out = mem("check", "--mem", str(store), "--statement", stmt, "--method", "primary")
    blocked = (isinstance(out, dict) and (out.get("blocked") or out.get("matches"))) \
              or "blocked:" in str(out).lower()
    cases.append(("a recorded failure blocks the same method on the same statement",
                  bool(blocked), str(out)[:110]))

    code, out = mem("check", "--mem", str(store), "--statement", stmt, "--method", "secondary")
    free = ("no recorded failure" in str(out).lower()
            or not (isinstance(out, dict) and out.get("blocked")))
    cases.append(("and does not block a different method",
                  free,
                  "a store that blocks everything after one failure stops the campaign rather "
                  "than informing it"))

    print("\n  CROSS-RUN MEMORY SELF-TEST\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {str(note)[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.parse_args()
    return self_test()


if __name__ == "__main__":
    sys.exit(main())
