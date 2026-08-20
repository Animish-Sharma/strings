#!/usr/bin/env python3
"""Protected-region patcher.

Distinct from the statement diff. That one asks "does the artifact still state
the target". This one asks "did the edit touch anything it was not allowed to".

The mechanism is the PROTECTED PROJECTION: the artifact with every editable body
removed but its markers preserved. A legal edit changes bodies only, so the
projection is byte-identical before and after. Anything else — an added import, a
new declaration outside a body, a namespace change, a moved marker — changes the
projection and is refused.

The file is RESTORED if post-patch validation fails. A half-applied patch is
worse than a rejected one.

Usage:
    protected_patch.py project <artifact> --contract <c.json> [--json]
    protected_patch.py apply <artifact> --contract <c.json> --range-id R --body <f.txt>
Exit: 0 ok, 1 refused, 2 IO error.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

FORBIDDEN_TOKENS = ("sorry", "admit", "TODO", "placeholder")
# File-level constructs have no business inside a proof body. The projection
# cannot catch these — it REMOVES bodies, so anything hidden inside one is
# invisible to a projection comparison. The body needs its own constraint.
FORBIDDEN_IN_BODY = ("import", "open", "set_option", "namespace", "end",
                     "theorem", "lemma", "def", "axiom", "instance", "macro",
                     "notation", "attribute")

def project(text: str, ranges: list[dict]) -> tuple[str, list[str]]:
    """Remove editable bodies, keep markers. Returns (projection, problems)."""
    problems, out = [], text
    for r in ranges:
        start, end = r["start_marker"], r["end_marker"]
        if out.count(start) != 1:
            problems.append(f"range {r['id']}: start marker appears {out.count(start)} "
                            "times (expected exactly 1) — a duplicate usually means a "
                            "patch landed in the wrong place")
        if out.count(end) != 1:
            problems.append(f"range {r['id']}: end marker appears {out.count(end)} times")
    if problems: return out, problems
    for r in ranges:
        pattern = re.escape(r["start_marker"]) + r".*?" + re.escape(r["end_marker"])
        out = re.sub(pattern, r["start_marker"] + "\n<<BODY>>\n" + r["end_marker"],
                     out, flags=re.DOTALL)
    return out, problems

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["project","apply"]); ap.add_argument("artifact")
    ap.add_argument("--contract", required=True); ap.add_argument("--range-id")
    ap.add_argument("--body"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        art = Path(a.artifact); text = art.read_text(encoding="utf-8")
        contract = json.loads(Path(a.contract).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    ranges = contract.get("editable_ranges", [])

    proj, problems = project(text, ranges)
    digest = hashlib.sha256(proj.encode()).hexdigest()
    if a.cmd == "project":
        out = {"protected_sha256": digest, "problems": problems,
               "matches_baseline": (digest == contract.get("protected_sha256")
                                    if contract.get("protected_sha256") else None)}
        print(json.dumps(out, indent=2) if a.json else
              f"PROJECTION {digest[:16]}...  baseline match: {out['matches_baseline']}\n" +
              "\n".join(f"  {p}" for p in problems))
        return 1 if problems else 0

    if not (a.range_id and a.body):
        ap.error("apply needs --range-id and --body")
    target = next((r for r in ranges if r["id"] == a.range_id), None)
    if not target:
        print(f"REFUSED: no editable range {a.range_id!r}", file=sys.stderr); return 1
    if problems:
        print("REFUSED: projection is already malformed\n  " + "\n  ".join(problems),
              file=sys.stderr); return 1

    before = digest
    body = Path(a.body).read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        if token in body:
            print(f"REFUSED: replacement body contains {token!r}", file=sys.stderr); return 1
    for line in body.splitlines():
        head = line.strip().split(" ")[0] if line.strip() else ""
        if head in FORBIDDEN_IN_BODY:
            print(f"REFUSED: replacement body declares {head!r} at file level:\n"
                  f"    {line.strip()[:80]}\n"
                  "  A proof body may contain local steps only. The protected projection "
                  "cannot see inside a body, so this is checked here or not at all.",
                  file=sys.stderr)
            return 1

    pattern = re.escape(target["start_marker"]) + r".*?" + re.escape(target["end_marker"])
    patched = re.sub(pattern, target["start_marker"] + "\n" + body + "\n" + target["end_marker"],
                     text, flags=re.DOTALL)
    art.write_text(patched, encoding="utf-8")

    after_proj, after_problems = project(patched, ranges)
    after = hashlib.sha256(after_proj.encode()).hexdigest()
    if after != before or after_problems:
        art.write_text(text, encoding="utf-8")     # restore; never leave it half-applied
        print(f"REFUSED and RESTORED: the protected projection changed\n"
              f"  before {before[:16]}...  after {after[:16]}...\n"
              "  The edit touched something outside its permitted body — an import, a "
              "declaration, a namespace, or a marker.", file=sys.stderr)
        return 1
    print(f"APPLIED to range {a.range_id}; protected projection unchanged ({after[:16]}...)")
    return 0
if __name__ == "__main__":
    sys.exit(main())
