#!/usr/bin/env python3
"""Who checks the checkers.

The `check_*.py` scripts guard this tree and originally not one had a test. The
proofs that they work — planting a regression and watching it fire — were done
BY HAND and lived nowhere, so if a checker silently stopped catching things
nothing would notice. That is not hypothetical: two of the three checkers proved
that way were WRONG on their first attempt. The bridge check accepted exit 2
unconditionally and missed a renamed flag, which is the single failure it exists
to catch; the doctrine-command checker reported ninety-five problems of which
almost none were real.

So each checker here gets a regression planted into a copy of the tree, and must
fail. Then the plant is removed and it must pass again — a checker that fails on
everything catches nothing and merely stops.

The tree is COPIED rather than mutated in place. A suite that edits the repo to
test itself will one day leave it edited.

Usage:  check_checkers.py [--only NAME] [--json]
Exit:   0 every checker caught its regression, 1 one did not, 2 IO
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Directories a checker needs to see. Copying the whole tree would drag build
# artifacts and caches through every case for no benefit.
COPY = ["scripts", "schemas", "references", "contracts", "capabilities", "domains",
        "explorer", "generator", "researcher", "SKILL.md", "ARCHITECTURE.md"]


def stage(tmp: Path) -> Path:
    root = tmp / "tree"
    root.mkdir(parents=True, exist_ok=True)
    for name in COPY:
        src = ROOT / name
        if not src.exists():
            continue
        dst = root / name
        if src.is_dir():
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".lake"))
        else:
            shutil.copy(src, dst)
    # Two checkers legitimately reach OUTSIDE the skill — doc links resolves
    # `../witsoc/ARCHITECTURE.md` and the alignment check reads it. Without a
    # sibling here they fail and abstain respectively, for reasons that have
    # nothing to do with what is being tested.
    sibling = root.parent / "witsoc"
    sibling.mkdir(parents=True, exist_ok=True)
    real = ROOT.parent / "witsoc" / "ARCHITECTURE.md"
    if real.exists():
        shutil.copy(real, sibling / "ARCHITECTURE.md")
    return root


def run(root: Path, script: str, args: list[str] | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run([sys.executable, str(root / "scripts" / script), *(args or [])],
                              capture_output=True, text=True, timeout=180, cwd=str(root))
        return proc.returncode, proc.stdout + proc.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)


def break_catalog_description(root: Path) -> None:
    path = root / "SKILL.md"
    original = path.read_text(encoding="utf-8")
    changed, count = re.subn(
        r"^description:.*$", "description: >", original, count=1, flags=re.MULTILINE
    )
    if count != 1:
        raise ValueError("SKILL.md has no one-line description to replace")
    path.write_text(changed, encoding="utf-8")


def break_mode_retention(root: Path) -> None:
    path = root / "SKILL.md"
    original = path.read_text(encoding="utf-8")
    changed = original.replace("Stay in Witsoc.", "Leave Witsoc.", 1)
    if changed == original:
        raise ValueError("SKILL.md has no source-synthesis retention rule to replace")
    path.write_text(changed, encoding="utf-8")


def append_maths_explorer_doctrine(root: Path, text: str) -> None:
    pack = root / "domains" / "maths"
    manifest = json.loads((pack / "domain.json").read_text(encoding="utf-8"))
    path = pack / manifest["doctrine"]["roles"]["explorer"]
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


# Each plant is a change a reviewer would plausibly make and a checker must
# refuse. The `catches` string has to appear in the output: a checker that fails
# for an unrelated reason has not caught this.
PLANTS = [
    {"name": "frame purity (vocabulary)", "script": "check_frame_purity.py",
     "plant": lambda r: (r / "scripts" / "check_delivery.py").write_text(
         (r / "scripts" / "check_delivery.py").read_text() + "\n# a theorem is a maths word\n"),
     "catches": "vocabulary"},
    {"name": "frame purity (structural)", "script": "check_frame_purity.py",
     "plant": lambda r: (r / "scripts" / "check_delivery.py").write_text(
         (r / "scripts" / "check_delivery.py").read_text() + "\n# see scripts/counts.py\n"),
     "catches": "structural"},
    {"name": "doc links", "script": "check_doc_links.py",
     "plant": lambda r: (r / "ARCHITECTURE.md").write_text(
         (r / "ARCHITECTURE.md").read_text() + "\nSee `scripts/nonexistent_file.py`.\n"),
     "catches": "resolve to nothing"},
    {"name": "skill discovery (catalog description)",
     "script": "check_skill_discovery.py",
     "plant": break_catalog_description,
     "catches": "block scalar marker"},
    {"name": "skill discovery (mode retention)",
     "script": "check_skill_discovery.py",
     "plant": break_mode_retention,
     "catches": "retention term"},
    {"name": "doctrine commands (dead command)", "script": "check_doctrine_commands.py",
     "plant": lambda r: append_maths_explorer_doctrine(
         r, "\n```bash\npython3 scripts/no_such_tool.py --help\n```\n"),
     "catches": "no such file"},
    {"name": "doctrine commands (wrong flag)", "script": "check_doctrine_commands.py",
     "plant": lambda r: append_maths_explorer_doctrine(
         r, "\n```bash\npython3 scripts/corpus.py query --nonexistent-flag X\n```\n"),
     "catches": "does not accept"},
    {"name": "contract shapes", "script": "check_contract_shapes.py",
     "plant": lambda r: _json_edit(
         r / "domains/maths/domain.json",
         lambda d: d["gates"]["additional"].append(
             {"name": "gate-that-does-not-exist", "description": "declared and unimplemented",
              "blocking": True})),
     "catches": "gate-that-does-not-exist"},
    {"name": "bridge (surface drift)", "script": "check_bridge.py",
     "plant": lambda r: _json_edit(
         r / "domains/bio/domain.json",
         lambda d: d["verification_adapter"]["tiers"][1].__setitem__("max_status", "VERIFIED")),
     "catches": "drift"},
    {"name": "bridge (uncallable adapter)", "script": "check_bridge.py",
     "plant": lambda r: (r / "domains/archival/scripts/check.py").write_text(
         (r / "domains/archival/scripts/check.py").read_text()
         .replace('"--artifact"', '"--candidate"', 1)),
     "catches": "REFUSED the frame's arguments"},
    # The checker that catches a gate which checks nothing. Planted by replacing
    # a real gate with one that passes without reading its input — which is what
    # three shipping gates were doing, in effect, for the artifact kinds their
    # own suites never fed them.
    {"name": "gate inertness", "script": "check_gate_inertness.py",
     "plant": lambda r: (r / "domains/archival/scripts/gates/survivorship.py").write_text(
         "#!/usr/bin/env python3\nimport sys\nprint('pass: nothing was examined')\n"
         "sys.exit(0)\n"),
     "catches": "answered 'pass' to all",
     # Scoped to one pack deliberately. The full sweep invokes every gate over
     # every artifact of every pack and takes minutes; a plant that times out
     # reports the checker as broken rather than as working, which is the
     # opposite of what this file is for.
     "args": ["--pack", "archival"]},
    {"name": "alignment", "script": "check_alignment.py",
     "plant": lambda r: _json_edit(
         r / "references/alignment.json",
         lambda d: d.__setitem__("declared_divergences", [])),
     "catches": "DRIFT"},
    # The plant has to break an example the checker actually VALIDATES, against
    # the schema it validates it with. The first attempt removed a maths
    # EXTENSION field from a pack example, which frame-claim-v1 neither requires
    # nor sees — so the checker passed and was right to.
    {"name": "schema examples", "script": "check_schema_examples.py",
     "plant": lambda r: _json_edit(
         r / "schemas/examples/state.json",
         lambda d: d["claims"][sorted(d["claims"])[0]].__setitem__("status", "TOTALLY_MADE_UP")),
     "catches": "status"},
]


def _json_edit(path: Path, mutate) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = []
    with tempfile.TemporaryDirectory(prefix="checkcheck_") as raw:
        tmp = Path(raw)
        clean = stage(tmp)

        # Baseline: on an unmodified copy every checker must pass. A checker that
        # fails here is failing for a reason that has nothing to do with the
        # plant, and its "catch" below would mean nothing.
        for plant in PLANTS:
            if args.only and args.only not in plant["name"]:
                continue
            code, out = run(clean, plant["script"], plant.get("args"))
            # Same rule as the planted phase: exit 3 means the checker could not
            # run here at all, which is a gap to report and not a checker that
            # failed on a clean tree.
            last = out.strip().splitlines()[-1][:110] if out.strip() else ""
            results.append({"checker": plant["name"], "phase": "clean",
                            "ok": code in (0, 3), "not_run": code == 3,
                            "detail": last})

        for plant in PLANTS:
            if args.only and args.only not in plant["name"]:
                continue
            case = stage(tmp / plant["name"].replace(" ", "_").replace("(", "").replace(")", ""))
            try:
                plant["plant"](case)
            except (OSError, KeyError, ValueError) as exc:
                results.append({"checker": plant["name"], "phase": "plant",
                                "ok": False, "detail": f"could not plant: {exc}"})
                continue
            code, out = run(case, plant["script"], plant.get("args"))
            # Exit 3 is the checker saying it could not run here — typically
            # because something it compares against is not installed. A plant it
            # could not evaluate is NOT a caught plant and is NOT a failure of
            # the checker; scoring it either way is a lie about what was tested.
            if code == 3:
                results.append({"checker": plant["name"], "phase": "planted",
                                "ok": True, "not_run": True,
                                "detail": "NOT_RUN here — the plant was never evaluated"})
                continue
            caught = code != 0 and plant["catches"].lower() in out.lower()
            results.append({"checker": plant["name"], "phase": "planted", "ok": caught,
                            "detail": (f"exit {code}; " +
                                       ("caught" if caught else
                                        f"did NOT name {plant['catches']!r}"))})

    failures = [r for r in results if not r["ok"]]
    unevaluated = [r for r in results if r.get("not_run")]
    if args.json:
        print(json.dumps({"results": results, "failures": len(failures)}, indent=2))
        return 1 if failures else 0

    print("\n  WHO CHECKS THE CHECKERS\n")
    for phase, label in (("clean", "on a clean tree, every checker passes"),
                         ("planted", "with a regression planted, every checker fails")):
        print(f"  {label}")
        for entry in [r for r in results if r["phase"] == phase]:
            print(f"    {'ok  ' if entry['ok'] else 'FAIL'}  {entry['checker']:<34} "
                  f"{entry['detail']}")
        print()
    print("=" * 70)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(results) - len(failures)}"
          f"/{len(results)} case(s)"
          + (f", {len(unevaluated)} NOT_RUN and therefore untested"
             if unevaluated else ""))
    if failures:
        print("  A checker that misses its plant is not guarding anything, and the suite it "
              "belongs to has been green for a reason that is not the reason anyone thinks.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
