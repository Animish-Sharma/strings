#!/usr/bin/env python3
"""Certificate re-execution.

A recorded certificate is a claim that something was checked. This re-runs it.

The rule that makes it worth having: **UNCHECKED is not PASS.** A certificate
whose checker is unavailable comes back UNCHECKED and stays a visible non-pass.
Treating "I could not verify this" as "this verified" is how a node claiming
CHECKED survives with nothing behind it.

Kinds: exact (arithmetic identity) · finite (enumeration) · sat (DIMACS) ·
external (a recorded command, re-run).

Usage:  recheck.py --certificates <c.json> [--json]
Exit: 0 all PASS, 1 any FAIL, 3 any UNCHECKED (and none failed), 2 IO error.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def recheck_one(cert: dict) -> dict:
    kind = cert.get("kind")
    path = cert.get("path")
    if kind == "exact":
        code, _ = run([sys.executable, str(HERE/"backends"/"exact.py"), "verify",
                       "--certificate", path])
    elif kind == "finite":
        code, _ = run([sys.executable, str(HERE/"backends"/"finite.py"), "enumerate",
                       "--spec", path])
    elif kind == "sat":
        code, _ = run([sys.executable, str(HERE/"backends"/"sat.py"), "solve",
                       "--dimacs", path])
    elif kind == "external":
        cmd = cert.get("command")
        if not cmd:
            return {"id":cert.get("id"),"kind":kind,"verdict":"UNCHECKED",
                    "why":"external certificate records no command to re-run"}
        code, _ = run(cmd.split())
    else:
        return {"id":cert.get("id"),"kind":kind,"verdict":"UNCHECKED",
                "why":f"no re-checker for kind {kind!r}"}
    verdict = "PASS" if code == 0 else ("UNCHECKED" if code in (2,3) else "FAIL")
    return {"id":cert.get("id"),"kind":kind,"verdict":verdict,"exit_code":code}

def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--certificates", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: payload = json.loads(Path(a.certificates).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    certs = payload if isinstance(payload, list) else payload.get("certificates", [])
    results = [recheck_one(c) for c in certs]
    failed = [r for r in results if r["verdict"] == "FAIL"]
    unchecked = [r for r in results if r["verdict"] == "UNCHECKED"]
    out = {"results":results,"passed":len(results)-len(failed)-len(unchecked),
           "failed":len(failed),"unchecked":len(unchecked),
           "rule":"UNCHECKED is a visible non-pass. A node claiming CHECKED without a "
                  "re-checked PASS does not hold that status."}
    if a.json: print(json.dumps(out, indent=2))
    else:
        for r in results:
            print(f"  {r['verdict']:<10} {r.get('id','?')} ({r['kind']})"
                  + (f"  {r.get('why','')}" if r.get("why") else ""))
        print(f"\n  {out['passed']} pass, {out['failed']} fail, {out['unchecked']} unchecked")
        print(f"  {out['rule']}")
    return 1 if failed else (3 if unchecked else 0)
if __name__ == "__main__":
    sys.exit(main())
