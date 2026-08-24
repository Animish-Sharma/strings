#!/usr/bin/env python3
"""WIT -> Lean skeleton.

A structurally-checked WIT artifact *already is* an obligation DAG, so the
translation never hands a model one monolithic goal. It emits a skeleton with
one `have` per step in dependency order, each closed by `sorry`, so every step
becomes a small independently kernel-checkable leaf. A failure then localizes to
one rung instead of to "the proof".

This script does **not** autoformalize the statement and does **not** attempt any
proof. What it will do is *carry* formalizations someone else supplied:
`--formalization` takes a map from step label to the Lean proposition and tactic
for that step, and fills the corresponding hole. Steps with no entry keep their
`sorry`. The distinction matters — a formalization that arrives through this flag
came from somewhere that can be pointed at, and one this script invented could
not be.

Four honest states:

    STATEMENT_NOT_FORMALIZED   no --statement given; no Lean file is emitted
    OBLIGATION_OPEN            skeleton emitted, at least one step still `sorry`
    OBLIGATIONS_FILLED         every step has a supplied proposition and tactic;
                               the file contains no placeholder. This is a claim
                               about the FILE, not about the mathematics.
    PROOF_DISCHARGED           only the caller's kernel run may report this

Emitting a skeleton is not progress on the mathematics. It is progress on
*localizing* the mathematics.

Usage:
    wit_to_lean.py <file.wit> [--statement "theorem foo : ..."]
                   [--formalization <map.json>] [--calc] [--json]
Exit: 0 lean_ready, 1 not ready, 2 IO error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from witlib import OBLIGATION_KEYWORDS, parse, topological  # noqa: E402

# Relations that can chain transitively into a Lean `calc` block.
RELATIONS = ["=", "≤", "<", "≥", ">", "≠", "<=", ">=", "!="]
MIN_CALC_RUNGS = 2

# Steps that introduce context rather than assert an obligation.
CONTEXT_KEYWORDS = {"LET", "ASSUME", "CONSIDER"}


def lean_ident(label: str) -> str:
    return "step" + label.replace(".", "_")


def split_relation(text: str) -> tuple[str, str, str] | None:
    """Split 'a ≤ b' into (lhs, rel, rhs) on the first top-level relation."""
    for rel in sorted(RELATIONS, key=len, reverse=True):
        idx = text.find(rel)
        if idx > 0:
            return text[:idx].strip(), rel, text[idx + len(rel):].strip()
    return None


def detect_calc_chain(steps: list) -> list[dict]:
    """Consecutive HAVE steps where one RHS is the next LHS."""
    chain: list[dict] = []
    for step in steps:
        if step.keyword != "HAVE":
            chain = []
            continue
        parts = split_relation(re.sub(r"\$", "", step.text))
        if not parts:
            chain = []
            continue
        lhs, rel, rhs = parts
        if chain and chain[-1]["rhs"] != lhs:
            chain = []
        chain.append({"label": step.label, "lhs": lhs, "rel": rel, "rhs": rhs})
    return chain if len(chain) >= MIN_CALC_RUNGS else []


def build(doc, statement: str | None, want_calc: bool,
          formalization: dict | None = None) -> dict:
    ordered = topological([s for s in doc.steps])
    obligations = []
    for step in ordered:
        if step.keyword not in OBLIGATION_KEYWORDS or step.keyword == "GAP":
            continue
        if step.keyword in CONTEXT_KEYWORDS:
            continue
        numeric = [r for r in step.refs if re.match(r"^\d", r)]
        named = [r for r in step.refs if not re.match(r"^\d", r)]
        obligations.append({
            "id": step.label,
            "lean_name": lean_ident(step.label),
            "keyword": step.keyword,
            "informal": step.text,
            "may_use_steps": numeric,
            "may_use_hypotheses": named,
            "citations": step.citations,
            "justification": step.by_text,
        })

    gaps = [{"id": s.label, "informal": s.text, "expecting": s.gap_expecting}
            for s in ordered if s.keyword == "GAP"]

    result = {
        "module": doc.module,
        "wit_status": doc.status,
        "is_template": doc.is_template,
        "steps": len(ordered),
        "leaf_obligations": obligations,
        "open_gaps": gaps,
        "state": "STATEMENT_NOT_FORMALIZED",
        "lean_ready": False,
        "skeleton": None,
        "calc_block": None,
    }

    if gaps:
        result["note"] = (
            f"{len(gaps)} explicit GAP step(s). A skeleton can still be emitted, but "
            "the artifact is honestly incomplete and cannot reach a discharged state."
        )

    if not statement:
        result["reason"] = (
            "No --statement supplied. This script does not autoformalize a target: "
            "guessing the formal statement is exactly where fidelity is lost, so no "
            "Lean file is emitted."
        )
        return result

    if want_calc:
        chain = detect_calc_chain(ordered)
        if chain:
            rungs = [f"    {chain[0]['lhs']}"]
            for link in chain:
                rungs.append(f"      {link['rel']} {link['rhs']} := by sorry"
                             f"   -- WIT [{link['label']}]")
            result["calc_block"] = "  calc\n" + "\n".join(rungs)
            result["has_chain"] = True
        else:
            result["has_chain"] = False
            result["calc_note"] = (
                f"no transitive chain of >= {MIN_CALC_RUNGS} rungs; falling back to "
                "the per-step skeleton"
            )

    body = []
    filled, holes = [], []
    for obligation in obligations:
        refs = ", ".join(f"[{r}]" for r in obligation["may_use_steps"]) or "-"
        body.append(f"  -- WIT [{obligation['id']}] {obligation['keyword']}: "
                    f"{obligation['informal'][:100]}")
        body.append(f"  --   uses: {refs}   justification: "
                    f"{obligation['justification'][:80]}")
        supplied = (formalization or {}).get(obligation["id"]) or {}
        prop, tactic = supplied.get("type"), supplied.get("tactic")
        if prop and tactic:
            body.append(f"  have {obligation['lean_name']} : {prop} := by")
            for line in str(tactic).splitlines() or ["exact?"]:
                body.append(f"    {line}")
            filled.append(obligation["id"])
        else:
            # An unsupplied step keeps its hole and says which half is missing.
            missing = "proposition and tactic" if not (prop or tactic) else (
                "tactic" if prop else "proposition")
            body.append(f"  have {obligation['lean_name']} : "
                        f"{prop or 'sorry'} /- formalize: "
                        f"{obligation['informal'][:60]} ({missing} not supplied) -/ := by")
            body.append("    sorry")
            holes.append(obligation["id"])
        body.append("")
    if obligations:
        closing = (formalization or {}).get("__closing__") or {}
        body.append(f"  {closing.get('tactic') or 'exact ' + obligations[-1]['lean_name']}")

    # The SIGNATURE is an obligation too, and it was the one nothing counted.
    # `blueprint_init` writes a FILL-ME there when no formal target is supplied,
    # and a blueprint carrying it produced a Lean file whose theorem line was
    # that sentence — while this function reported "every step carries a
    # supplied proposition and tactic, 0 open". It reached the kernel and failed
    # as a parse error, which is luck, not a guard.
    if "FILL-ME" in statement:
        gaps = list(gaps) + [{
            "id": "TARGET",
            "informal": "the target signature",
            "expecting": "a formal statement. A blueprint whose signature is still a "
                         "FILL-ME has no target to protect and nothing to check against — "
                         "supply --formal, or a claim carrying formal_target"}]
        # `open_gaps` was published earlier in the function; rebinding the local
        # alone left the caller reading the pre-signature list.
        result["open_gaps"] = gaps

    result["skeleton"] = f"{statement} := by\n" + "\n".join(body)
    result["filled_steps"] = filled
    result["open_steps"] = holes
    result["lean_ready"] = True
    if holes or gaps:
        result["state"] = "OBLIGATION_OPEN"
        result["note_state"] = (
            f"OBLIGATION_OPEN: {len(holes)} of {len(obligations)} step(s) are still an open "
            "`sorry`. Only a kernel run may report PROOF_DISCHARGED, and only after the "
            "placeholder scan finds nothing."
        )
    else:
        result["state"] = "OBLIGATIONS_FILLED"
        result["note_state"] = (
            "OBLIGATIONS_FILLED: every step carries a supplied proposition and tactic and the "
            "file contains no placeholder. That is a statement about the FILE. Whether any of "
            "it is true is the kernel's to say, and it has not been asked yet."
        )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact")
    ap.add_argument("--statement", help="the Lean theorem signature, supplied not guessed")
    ap.add_argument("--formalization",
                    help="JSON map: step label -> {type, tactic}. Carried, never invented.")
    ap.add_argument("--calc", action="store_true", help="try a calc block for chains")
    ap.add_argument("--out", help="write the skeleton to this .lean path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        text = Path(args.artifact).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    formalization = None
    if args.formalization:
        try:
            formalization = json.loads(Path(args.formalization).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: --formalization {exc}", file=sys.stderr)
            return 2

    doc = parse(text)
    result = build(doc, args.statement, args.calc, formalization)

    if args.out and result["skeleton"]:
        Path(args.out).write_text(result["skeleton"] + "\n", encoding="utf-8")
        result["written"] = args.out

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"WIT->LEAN: {result['state']}")
        print(f"  module            {result['module']}")
        print(f"  leaf obligations  {len(result['leaf_obligations'])}")
        if result.get("filled_steps") is not None:
            print(f"  filled            {len(result['filled_steps'])}"
                  f"   open  {len(result['open_steps'])}")
        if result["open_gaps"]:
            print(f"  open GAP steps    {len(result['open_gaps'])}  <- honestly incomplete")
        if result.get("has_chain"):
            print("  calc chain        detected — failure localizes to one rung")
        if result.get("reason"):
            print(f"\n  {result['reason']}")
        if result.get("written"):
            print(f"\n  wrote {result['written']}")
    return 0 if result["lean_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
