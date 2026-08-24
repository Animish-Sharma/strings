#!/usr/bin/env python3
"""Circularity audit — did the proof close the target by citing the target.

Every other gate in this pack passes a proof that cites the thing it is
supposed to establish. `#print axioms` reports the standard three and calls it
clean. The kernel is entirely happy: `theorem t : P := Mathlib.t` type-checks,
because `Mathlib.t` really does have type `P`.

That is harmless while the target is something nobody has proved. It stops
being harmless the moment a target is drawn from an installed library, which is
exactly what an honest evaluation does — and the tactic portfolio contains
`exact?`, whose whole job is to find a library result of the goal's type. On a
drawn Mathlib target `exact?` will find the target. A pass rate measured
without this gate measures the library, not the pipeline.

## Why it prints instead of asking the environment

The obvious implementation reads `ConstantInfo.value?` and calls
`getUsedConstants`. On Lean 4.31 that returns none for every theorem, imported
or local — theorem values are not carried in the environment the way `def`
values are. `#print` forces and renders the term, so the audit parses what
`#print` writes.

Proof terms lift work into auxiliaries named `<decl>._proof_N`, and a citation
can hide inside one. So the audit runs twice: the first pass prints the
declaration and lists every constant whose name has the declaration as a
prefix, the second prints those. Auxiliaries of auxiliaries carry the same
prefix, so the second pass is complete rather than merely deeper.

If auxiliaries are found and the second pass cannot run, the verdict is
INCONCLUSIVE. It is never PASS: an unread auxiliary is where the citation would
be if there were one.

Usage:
    circularity_audit.py <artifact.lean> --decl <name> --forbid <Name> [...]
    circularity_audit.py <artifact.lean> --decl <name> --claim <claim.json>
    circularity_audit.py --self-test

Exit: 0 clean, 1 circular, 2 usage/IO, 3 not run / inconclusive.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

LISTAUX = """
open Lean Elab Command in
elab "witsoc_listaux " i:ident : command => do
  let env ← getEnv
  let p := i.getId
  let mut acc : List String := []
  for (n, _) in env.constants.toList do
    if p.isPrefixOf n && n != p then acc := (toString n) :: acc
  logInfo ("WITSOC_AUX " ++ String.intercalate " " acc)
"""

from itertools import count
_SERIAL = count()

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_'!?]*(?:\.[A-Za-z0-9_'!?]+)*")


def lean_cmd() -> list[str] | None:
    if shutil.which("lake"):
        return [shutil.which("lake"), "env", "lean"]
    if shutil.which("lean"):
        return [shutil.which("lean")]
    return None


def run_lean(source: str, workdir: str, timeout: int) -> str | None:
    cmd = lean_cmd()
    if cmd is None:
        return None
    # Unique per process: a batch runs these concurrently from one project
    # directory, and a shared filename makes each audit read another's file.
    probe = Path(workdir) / f".witsoc_circularity_{os.getpid()}_{next(_SERIAL)}.lean"
    try:
        probe.write_text(source, encoding="utf-8")
        proc = subprocess.run(cmd + [str(probe)], capture_output=True, text=True,
                              timeout=timeout, cwd=workdir)
        return proc.stdout + proc.stderr
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        probe.unlink(missing_ok=True)


def suffixes(name: str) -> set[str]:
    """Every way `#print` might render a name.

    The pretty printer writes the SHORTEST unambiguous form, so under
    `open Metric` a use of `Metric.sphere_eq_empty_of_neg` prints as
    `sphere_eq_empty_of_neg`. Comparing full names alone therefore passed a
    proof that was nothing but a citation of its own target. Matching any
    suffix over-refuses in principle — another namespace could own the same
    base name — and over-refusing is the direction this gate should err in.
    """
    parts = name.split(".")
    return {".".join(parts[i:]) for i in range(len(parts))}


def cited_names(printed: str) -> set[str]:
    """Identifiers appearing in a rendered proof term.

    Over-collects: binder names and type constructors come along. That is the
    safe direction — the audit asks whether a specific forbidden name is
    present, so a superset can only make it more likely to refuse, never less.
    """
    return set(IDENT.findall(printed))


def split_prints(out: str) -> dict[str, str]:
    """Split combined `#print` output by the declaration each block opens."""
    blocks: dict[str, str] = {}
    current = None
    for line in out.splitlines():
        m = re.match(r"^(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+)*"
                     r"(?:theorem|lemma|def|abbrev|instance)\s+([\w.'!?]+)", line)
        if m:
            # `#print` writes universe parameters as `name.{u_1, u_2}`, and the
            # name pattern swallows the trailing dot. Keyed that way the block
            # never matched the declaration asked for, and the caller silently
            # fell back to scanning the ENTIRE Lean output — which happens to be
            # safe for a forbidden-name check and is wrong for anything that
            # needs THIS declaration's term.
            current = m.group(1).rstrip(".")
            blocks[current] = line + "\n"
        elif current is not None:
            if line.startswith("WITSOC_AUX ") or line.startswith("Try this:"):
                current = None
            else:
                blocks[current] += line + "\n"
    return blocks


ARROW = re.compile(r"\s(?:→|->)\s")
RELATION = {"∣": "Dvd.dvd", "≤": "LE.le", "≥": "GE.ge", "<": "LT.lt", ">": "GT.gt",
            "∈": "Membership.mem", "⊆": "HasSubset.Subset", "≠": "Ne", "=": "Eq"}
# What counts as a library dependency rather than as the language. Deciding
# this by NAME prefix was wrong in a way that silently disabled the check:
# `Nat` is both a core namespace and the home of real theorems, so excluding
# everything starting with "Nat" excluded `Nat.two_dvd_mul_add_one` — a
# citation of the whole target — as if it were a primitive. The module says
# which is which: `Nat.add_comm` lives in `Init.Data.Nat.Basic`,
# `Nat.two_dvd_mul_add_one` in `Mathlib.Algebra.Ring.Parity`.
FOUNDATIONAL_MODULES = ("Init", "Std", "Lean", "Batteries", "Aesop")


def conclusion_head(type_text: str | None) -> str | None:
    """The head symbol of what a declaration CONCLUDES.

    The corpus stores a type as `{binders} (binders) : conclusion`, so the
    conclusion begins after the last colon at bracket depth zero. Antecedents
    are then dropped and the leading symbol named; a conclusion headed by
    notation (`2 ∣ n * m`) is named by its relation.

    This is what lets the gate see a citation that is STRICTLY MORE GENERAL
    than the target — the case a same-name and a same-type check both miss,
    and the one that admitted a claim this pack could not otherwise refuse.
    """
    if not type_text:
        return None
    text, depth, cut = type_text, 0, None
    for i, ch in enumerate(text):
        if ch in "([{⟨":
            depth += 1
        elif ch in ")]}⟩":
            depth -= 1
        elif ch == ":" and depth == 0 and text[i:i + 2] != ":=":
            cut = i
    if cut is not None:
        text = text[cut + 1:]
    for _ in range(8):
        stripped = re.sub(r"^\s*(?:∀|Π)[^,]*,", "", text)
        if stripped == text:
            break
        text = stripped
    text = ARROW.split(text)[-1].strip().lstrip("(")
    m = re.match(r"([A-Za-z_][\w.']*)", text)
    if m:
        return m.group(1)
    for sym, name in RELATION.items():
        if sym in text:
            return name
    return None


def type_of_formal(formal: str | None) -> str | None:
    """`theorem foo (n : Nat) : P n` -> `(n : Nat) : P n`.

    The corpus stores types in exactly that shape, so the claim's own frozen
    target can be read by the same parser as a library declaration.
    """
    if not formal:
        return None
    m = re.match(r"\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+)*"
                 r"(?:theorem|lemma)\s+[\w.'!?]+\s*(.*)", formal, re.S)
    return m.group(1).strip() if m else formal.strip()


MODULE_OF: dict[str, str] = {}


def load_corpus_index(path: str | None) -> tuple[dict, dict]:
    """name -> type, and suffix -> [full names]."""
    if not path or not Path(path).exists():
        return {}, {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    by_name, by_suffix = {}, {}
    for d in data.get("declarations", []):
        by_name[d["name"]] = d.get("type")
        MODULE_OF[d["name"]] = d.get("module") or ""
        parts = d["name"].split(".")
        for i in range(1, len(parts)):
            by_suffix.setdefault(".".join(parts[i:]), []).append(d["name"])
    return by_name, by_suffix


def audit(artifact: Path, decl: str, forbid: set[str], workdir: str,
          timeout: int, by_name: dict | None = None, by_suffix: dict | None = None,
          target: str | None = None, allowed: set[str] | None = None,
          target_type: str | None = None) -> dict:
    source = artifact.read_text(encoding="utf-8")
    # `pp.fullNames` is what makes the reading unambiguous. Without it the
    # printer emits the shortest name that resolves IN THE ARTIFACT'S SCOPE, so
    # a proof using `Multiset.mem_map` under `open Multiset` prints `mem_map` —
    # and matching by suffix then attributes it to `Finset.mem_map`. Measured on
    # 189 library proofs, that misread 6 of them as citing themselves. Printing
    # full names removes the ambiguity at the source rather than guessing after.
    first = run_lean(f"{source}\n{LISTAUX}\nset_option pp.fullNames true in\n"
                     f"#print {decl}\nwitsoc_listaux {decl}\n", workdir, timeout)
    if first is None:
        return {"verdict": "NOT_RUN", "why":
                "no toolchain could render the proof term. That is a gap, not a pass: "
                "a proof that cites its own target type-checks."}
    if f"unknown identifier '{decl}'" in first or f"unknown constant '{decl}'" in first:
        return {"verdict": "NOT_RUN", "why":
                f"'{decl}' is not in the elaborated file, so there was no term to read."}

    aux = []
    m = re.search(r"WITSOC_AUX (.*)", first)
    if m:
        aux = [x for x in m.group(1).split() if x]

    blocks = split_prints(first)
    if decl not in blocks:
        # Falling back to the WHOLE Lean output was described as erring in the
        # safe direction. Measured on 189 library proofs it fabricated five
        # self-citations: names from diagnostics and from the auxiliary listing
        # were read as part of the term. A term that cannot be isolated is a
        # term that was not read.
        return {"verdict": "INCONCLUSIVE", "auxiliaries": [],
                "why": f"'{decl}' produced no printed term to read. That is a gap, not a "
                       "pass, and not grounds for a finding either — nothing was seen."}
    seen = cited_names(blocks[decl])
    inconclusive: list[str] = []

    if aux:
        second = run_lean(f"{source}\n" + "".join(
            f"set_option pp.fullNames true in\n#print {a}\n" for a in aux),
            workdir, timeout)
        if second is None:
            inconclusive = aux
        else:
            sb = split_prints(second)
            for a in aux:
                if a in sb:
                    seen |= cited_names(sb[a])
                else:
                    inconclusive.append(a)

    # The pretty printer writes `sorry`; the constant is `sorryAx`. A failed
    # proof still declares the theorem, so without this a proof that did not
    # exist was audited clean.
    if seen & {"sorryAx", "sorry"}:
        return {"verdict": "NOT_PROVED", "auxiliaries": aux,
                "why": f"the term for '{decl}' contains sorryAx — there is no proof here to "
                       "audit for circularity."}
    by_name = by_name or {}
    by_suffix = by_suffix or {}
    allowed = allowed or set()

    # Resolve what the term names to full declarations, so the checks below can
    # ask the corpus about them.
    resolved: set[str] = set()
    for n in seen:
        if n in by_name:
            resolved.add(n)
        else:
            resolved.update(by_suffix.get(n, [])[:1])
    library = sorted(n for n in resolved if n != target and
                     not (MODULE_OF.get(n, "").split(".")[0] in FOUNDATIONAL_MODULES
                          or not MODULE_OF.get(n)))

    rendered = {r: n for n in forbid for r in suffixes(n)}
    hits = sorted({rendered[r] for r in set(rendered) & seen})
    if hits:
        return {"verdict": "FAIL", "cites": hits, "auxiliaries": aux,
                "library_dependencies": library,
                "why": f"the proof of '{decl}' uses {', '.join(hits)} — it cites what it "
                       "was supposed to establish. The kernel accepts this; it is still "
                       "not an establishment."}

    # The claim's own formal target when it does not restate a library result —
    # which is the normal case, and the case where an undeclared dependency
    # matters most, because there is no library name to forbid.
    target_type = target_type or (by_name.get(target) if target else None)
    # An alias: some other declaration stating literally the target. Closing the
    # target by citing it under a different name is the same evasion.
    aliases = sorted(n for n in library
                     if target_type and by_name.get(n) == target_type
                     and n not in allowed)
    if aliases:
        return {"verdict": "FAIL", "cites": aliases, "auxiliaries": aux,
                "library_dependencies": library,
                "why": f"the proof of '{decl}' uses {', '.join(aliases)}, which state exactly "
                       "what the target states. A different name for the same result is the "
                       "same citation."}

    # The general case: a result that concludes what the target concludes, and
    # that the claim never declared. This is the check that makes
    # `allowed_external_facts` mean something about the PROOF rather than about
    # the plan — a tactic can reach a lemma the plan never mentioned, and until
    # this existed the receipt reported "0 citations" while one library result
    # carried the whole claim.
    target_head = conclusion_head(target_type)
    undeclared = sorted(n for n in library
                        if target_head and conclusion_head(by_name.get(n)) == target_head
                        and n not in allowed)
    if undeclared:
        return {"verdict": "FAIL", "cites": undeclared, "auxiliaries": aux,
                "library_dependencies": library, "target_conclusion": target_head,
                "why": f"the proof of '{decl}' rests on {', '.join(undeclared)}, which "
                       f"conclude{'s' if len(undeclared) == 1 else ''} {target_head} just as "
                       "the target does, and the claim does not declare "
                       f"{'it' if len(undeclared) == 1 else 'them'} in "
                       "allowed_external_facts. Declare the result and the claim is honest "
                       "about resting on it; leave it undeclared and the receipt says the "
                       "proof cited nothing."}
    if inconclusive:
        return {"verdict": "INCONCLUSIVE", "unread_auxiliaries": inconclusive,
                "auxiliaries": aux, "library_dependencies": library,
                "why": "auxiliary lemmas could not be rendered, and an unread auxiliary "
                       "is exactly where a citation would hide."}
    return {"verdict": "PASS", "cites": [], "auxiliaries": aux,
            "library_dependencies": library, "target_conclusion": target_head,
            "why": f"none of {len(forbid)} forbidden name(s) appear in the proof term"
                   + (f"; {len(library)} library dependenc(y/ies) recorded, none of them "
                      f"concluding {target_head}" if by_name else "")}


def self_test() -> int:
    """Two proofs of the same goal: one cites the library result, one does not."""
    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    if not project or not Path(project).is_dir() or lean_cmd() is None:
        print("SELF-TEST: NOT_RUN (needs WITSOC2_LEAN_PROJECT and a toolchain)")
        return 3
    import tempfile
    cases = [
        ("cited", "theorem probe (a b : Nat) : a + b = b + a := Nat.add_comm a b", "FAIL"),
        ("honest", "theorem probe (a b : Nat) : a + b = b + a := by\n"
                   "  induction a with\n  | zero => simp\n  | succ n ih => omega", "PASS"),
        # The pretty printer drops the namespace when it is open, so this cites
        # the same lemma as the first case under a shorter name.
        ("unqualified", "open Nat in\ntheorem probe (a b : Nat) : a + b = b + a := add_comm a b",
         "FAIL"),
        # A declaration whose proof failed still exists, and auditing it clean
        # would report an absence of citation in an absence of proof.
        ("unproved", "theorem probe (a b : Nat) : a + b = b + a := by sorry", "NOT_PROVED"),
    ]
    # These three need the index: they are about what the corpus knows, not
    # about what the claim remembered to forbid.
    corpus = os.environ.get("WITSOC2_MATHS_CORPUS")
    indexed = [
        # An alias — a different name for exactly the target — with nothing
        # forbidden by name at all.
        ("alias", "theorem probe (n : ℕ) : 2 ∣ n * (n + 1) := Nat.two_dvd_mul_add_one n",
         "(n : ℕ) : 2 ∣ n * (n + 1)", set(), "FAIL"),
        # A result STRICTLY MORE GENERAL than the target, undeclared. This is
        # the case a name check and a type check both miss.
        ("undeclared general", "theorem probe : Irrational (Real.sqrt 2) := by norm_num",
         ": Irrational (Real.sqrt 2)", set(), "FAIL"),
        # The same proof, with that result declared. Declaring it is what makes
        # the claim honest about resting on it, so this must pass.
        ("declared general", "theorem probe : Irrational (Real.sqrt 2) := by norm_num",
         ": Irrational (Real.sqrt 2)", {"Tactic.NormNum.irrational_sqrt_nat"}, "PASS"),
    ]
    ok, passed = True, 0
    for name, body, want in cases:
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "A.lean"
            f.write_text("import Mathlib\n\n" + body + "\n", encoding="utf-8")
            got = audit(f, "probe", {"Nat.add_comm"}, project, 900)
        hit = got["verdict"] == want
        passed += hit
        ok &= hit
        print(f"  {'ok ' if hit else 'FAIL'} {name}: want {want}, got {got['verdict']}")
    total = len(cases)
    if corpus and Path(corpus).exists():
        by_name, by_suffix = load_corpus_index(corpus)
        for name, body, ttype, allow, want in indexed:
            total += 1
            with tempfile.TemporaryDirectory() as td:
                f = Path(td) / "A.lean"
                f.write_text("import Mathlib\n\n" + body + "\n", encoding="utf-8")
                got = audit(f, "probe", set(), project, 900, by_name, by_suffix,
                            None, allow, ttype)
            hit = got["verdict"] == want
            passed += hit
            ok &= hit
            print(f"  {'ok ' if hit else 'FAIL'} {name}: want {want}, got {got['verdict']}")
    else:
        print("  ---- 3 index-dependent case(s) skipped: no WITSOC2_MATHS_CORPUS")
    print(f"SELF-TEST: {passed}/{total}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact", nargs="?")
    ap.add_argument("--decl")
    ap.add_argument("--forbid", action="append", default=[])
    ap.add_argument("--claim")
    ap.add_argument("--corpus", default=os.environ.get("WITSOC2_MATHS_CORPUS"),
                    help="declaration index; without it only the name check runs")
    ap.add_argument("--target", help="the library declaration this claim restates, if any")
    ap.add_argument("--allow", action="append", default=[],
                    help="a result the claim declares; adds to allowed_external_facts")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if not a.artifact:
        print("ERROR: need <artifact.lean>", file=sys.stderr)
        return 2

    forbid = set(a.forbid)
    allowed = set(a.allow)
    target = a.target
    target_type = None
    if a.claim:
        try:
            claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        frozen = claim.get("frozen_conditions", {}) or {}
        forbid |= set(frozen.get("forbidden_citations", []))
        name = claim.get("library_name") or frozen.get("library_name")
        if name:
            forbid.add(name)
        allowed |= set(claim.get("allowed_external_facts") or [])
        allowed |= set(frozen.get("allowed_external_facts") or [])
        target = target or name
        target_type = type_of_formal(claim.get("formal_target")
                                     or frozen.get("formal_target"))
    by_name, by_suffix = load_corpus_index(a.corpus)
    # With a corpus and a named target there is always something to check, even
    # when the claim forbids nothing by name: the allowlist itself is now a
    # check against the proof.
    if not forbid and not (by_name and (target or target_type)):
        # NOT_APPLICABLE, not an error. A claim that names nothing to forbid is
        # a claim about something the library does not already contain, and
        # there is no self-citation to look for. Reporting that as a failure
        # would make the gate noise on every honest campaign and teach people
        # to skip it on the one campaign where it matters.
        out = {"verdict": "NOT_APPLICABLE", "forbidden": [],
               "why": "the claim names no forbidden citation, so there is no target for "
                      "the proof to cite. Name results in "
                      "frozen_conditions.forbidden_citations to arm this gate."}
        print(json.dumps(out, indent=2) if a.json else
              f"CIRCULARITY AUDIT: NOT_APPLICABLE\n  {out['why']}")
        return 4

    try:
        artifact = Path(a.artifact)
        decl = a.decl
        if not decl:
            # Same convention as the axiom audit: read the declaration out of
            # the artifact rather than making every caller repeat it.
            m = re.search(r"^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+"
                          r"|noncomputable\s+|public\s+)*(?:theorem|lemma)\s+([\w.'!?]+)",
                          artifact.read_text(encoding="utf-8"), re.MULTILINE)
            if not m:
                print("ERROR: no theorem found and no --decl given", file=sys.stderr)
                return 2
            decl = m.group(1)
        project = os.environ.get("WITSOC2_LEAN_PROJECT")
        workdir = project if project and Path(project).is_dir() else str(artifact.parent)
        out = audit(artifact, decl, forbid, workdir, a.timeout,
                    by_name, by_suffix, target, allowed, target_type)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out["forbidden"] = sorted(forbid)
    out["allowed_external_facts"] = sorted(allowed)
    if target:
        out["target"] = target
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"CIRCULARITY AUDIT: {out['verdict']}\n  {out['why']}")
    out["decl"] = decl
    return {"PASS": 0, "FAIL": 1}.get(out["verdict"], 3)


if __name__ == "__main__":
    sys.exit(main())
