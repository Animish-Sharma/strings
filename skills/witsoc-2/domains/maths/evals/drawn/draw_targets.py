#!/usr/bin/env python3
"""Draw targets nobody chose.

`drawn_targets.json` held six statements and a README describing how they were
sampled. A procedure described in prose is a procedure that cannot be re-run,
and six is not a rate. This is the sampler, written down.

The filter is deliberately thin, and every condition it applies is a condition
that changes what the resulting number means:

  * `theorem` only — a `def` has no goal to close.
  * the statement fits on one line, because a multi-line statement needs a
    parser and the point of drawing is that nothing about the target was chosen.
  * no `sorry` in the source block.

**Context is carried, not approximated.** Almost every real statement leans on
`variable` declarations and `open` namespaces above it in the file, so a target
lifted out alone does not elaborate — and dropping those would report on the
easy tenth of the library that happens to be self-contained. So each target
records the `import` lines of its file, the `open` and `universe` lines and the
`variable` lines live at its scope, verbatim, and the namespaces it sits in. The
batch runner replays them and lets Lean decide which variables the statement
needs. An earlier version guessed that by matching tokens; Lean already
implements the rule, and guessing it produced both misses and junk binders.

Two consequences worth stating. The target's own file is NOT imported, so the
target is not in scope and cannot be closed by citing itself — the leak is
removed structurally rather than detected afterwards. Neither is anything else
that file defines, so a proof that would have leaned on a sibling result must do
without: this makes the drawn batch harder than the library, not easier.

Everything that survives is drawn uniformly with a stated seed. Nothing is
filtered for being provable, short, or in a friendly area of the library, which
is why the pass rate this feeds is a low number and an honest one.

Usage:
    draw_targets.py --src <Mathlib/> --n 40 [--seed 31337] [--out targets.json]

Exit: 0 drawn, 2 usage/IO
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

# `theorem NAME BINDERS : STATEMENT := ...` on one line, with the binders and
# the statement separated at the last top-level colon.
DECL = re.compile(r"^(theorem|lemma)\s+([\w.'!?]+)\s*(.*?)\s*:=\s*(.*)$")
NAMESPACE = re.compile(r"^namespace\s+([\w.']+)")
SECTION = re.compile(r"^(?:noncomputable\s+)?section\b")
END = re.compile(r"^end\b")
VARIABLE = re.compile(r"^variable\b\s*(.*)$")
OPEN = re.compile(r"^open\s+(.+?)(?:\s+in)?\s*$")
DECLARATION_START = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+|public\s+)*"
    r"(?:theorem|lemma|def|abbrev|instance|example|structure|inductive|class)\b")
UNIVERSE = re.compile(r"^universe\s+(.+)$")
IMPORT = re.compile(r"^\s*(?:public\s+|meta\s+)*import\s+\S")
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_'!?]*")


def binder_groups(text: str) -> list[str]:
    """Split a `variable` line into its individual bracketed groups."""
    groups, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch in "([{⦃":
            if depth == 0:
                start = i
            depth += 1
        elif ch in ")]}⦄":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(text[start:i + 1])
                start = None
    return groups


def split_binders(rest: str) -> tuple[str, str] | None:
    """Separate binders from the statement at the colon that is not inside a
    bracket. A colon inside `(n : Nat)` is a binder's colon, not the split."""
    depth = 0
    for i, ch in enumerate(rest):
        if ch in "([{⟨":
            depth += 1
        elif ch in ")]}⟩":
            depth -= 1
        elif ch == ":" and depth == 0:
            if i + 1 < len(rest) and rest[i + 1] == "=":
                return None
            return rest[:i].strip(), rest[i + 1:].strip()
    return None


def scan(src: Path) -> list[dict]:
    out = []
    for f in sorted(src.rglob("*.lean")):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        # This Mathlib uses the module system, where the line reads
        # `public import M`. Matching only `import ` found nothing in 37 of
        # 40 drawn files and quietly produced context-free probes.
        imports = [ln.strip() for ln in lines
                   if IMPORT.match(ln)]
        # Each frame: (opener line, closer line, raw context lines declared in it).
        # The nesting is replayed verbatim rather than flattened into `open`
        # lines: inside `namespace CategoryTheory`, the file's own `open Limits`
        # means `CategoryTheory.Limits`, and hoisting it to the top of a probe
        # makes it an unknown namespace.
        stack: list[tuple[str, str, list[str]]] = [("", "", [])]
        pending = None          # a `variable`/`open` line still being continued
        comment = 0             # nesting depth of `/- ... -/`
        once: list[str] = []    # `variable ... in` awaiting its one declaration
        for line_index, ln in enumerate(lines):
            # Prose is not syntax. A module docstring containing the word
            # "section" at the start of a line opened a scope that never
            # closed, and every declaration after it in that file inherited a
            # broken context.
            opens, closes = ln.count("/-"), ln.count("-/")
            if comment:
                comment += opens - closes
                continue
            if opens > closes:
                comment += opens - closes
                continue
            if ln.lstrip().startswith("--"):
                continue
            if pending is not None:
                # A continuation is indented; anything at column 0 ends it.
                if ln[:1] in (" ", "\t") and ln.strip():
                    stack[-1][2][-1] += " " + ln.strip()
                    continue
                pending = None
            ns = NAMESPACE.match(ln)
            if ns:
                stack.append((ln.strip(), f"end {ns.group(1)}", []))
                continue
            sec = SECTION.match(ln)
            if sec:
                # `noncomputable section` is anonymous and closes with a bare
                # `end`; taking the last token named it "section".
                toks = ln.strip().split()
                name = toks[toks.index("section") + 1] if toks[-1] != "section" else ""
                stack.append((ln.strip(), f"end {name}".strip(), []))
                continue
            if END.match(ln):
                if len(stack) > 1:
                    stack.pop()
                continue
            # `variable ... in` and `open ... in` scope to the NEXT declaration
            # only. Hoisting them into the section made every later statement in
            # the file inherit binders meant for one theorem, which Lean rejects
            # as a redundant binder annotation update.
            if re.search(r"\bin\s*$", ln) and (VARIABLE.match(ln) or OPEN.match(ln)):
                once.append(ln.strip())
                continue
            if VARIABLE.match(ln) or UNIVERSE.match(ln) or OPEN.match(ln):
                stack[-1][2].append(ln.strip())
                pending = ln
                continue
            if DECLARATION_START.match(ln):
                m = DECL.match(ln)
                attached, once = once, []
            else:
                continue
            if not m or "sorry" in ln:
                continue
            parts = split_binders(m.group(3))
            if not parts:
                continue
            binders, statement = parts
            if not statement or len(statement) > 120:
                continue
            # The author's own proof, where it fits the file's layout: the tail
            # of the declaration line plus the indented block under it. This is
            # the control group for any rule that claims to tell a proof from a
            # citation — nobody here wrote these.
            proof = [m.group(4).rstrip()]
            for follow in lines[line_index + 1:]:
                if not follow.strip():
                    if proof and proof[-1].strip():
                        continue
                    break
                if follow[:1] not in (" ", "\t"):
                    break
                proof.append(follow.rstrip())
            proof_text = "\n".join(proof).rstrip()

            names = [fr[0].split()[-1] for fr in stack
                     if fr[0].startswith("namespace ")]
            full = ".".join(names + [m.group(2)]) if names else m.group(2)
            scope_open, scope_close = [], []
            for opener, closer, ctx in stack:
                if opener:
                    scope_open.append(opener)
                    scope_close.append(closer)
                scope_open.extend(ctx)
            scope_open.extend(attached)
            out.append({
                "name": full,
                "binders": binders,
                "statement": statement,
                "file": str(f.relative_to(src)),
                "namespaces": names,
                "imports": imports,
                "proof": proof_text,
                "scope_open": scope_open,
                "scope_close": list(reversed(scope_close)),
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--out")
    a = ap.parse_args()

    src = Path(a.src)
    if not src.is_dir():
        print(f"ERROR: {src} is not a directory", file=sys.stderr)
        return 2
    pool = scan(src)
    if not pool:
        print("ERROR: no single-line theorems found", file=sys.stderr)
        return 2
    rng = random.Random(a.seed)
    drawn = rng.sample(pool, min(a.n, len(pool)))
    body = {"schema": "maths.drawn_targets.v1", "seed": a.seed,
            "pool_size": len(pool), "drawn": len(drawn), "targets": drawn}
    text = json.dumps(body, indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        print(f"drew {len(drawn)} of {len(pool)} eligible theorems (seed {a.seed}) "
              f"-> {a.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
