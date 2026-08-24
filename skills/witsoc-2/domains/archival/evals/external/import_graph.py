#!/usr/bin/env python3
"""External evaluation — the collapse against a derivation graph nobody drew for it.

Every fixture in this pack is a dossier its author wrote, which is the largest
reason to distrust its green results. The collapse is a graph algorithm, and a
graph algorithm tested only on graphs drawn to exercise it has been tested
against its author's idea of a hard case.

A software library's module imports are a real derivation DAG: thousands of
nodes, authored by many people over years for their own purposes, with a depth
nobody designed. Structurally it is the same object this pack collapses —
`derives_from` is `imports` — so it tests the traversal honestly even though the
subject matter has nothing to do with archives.

Three things, on a graph neither implementation was written against:

1. **Agreement.** `archlib.trace` must find the same roots as a second traversal
   written differently. Two implementations that share a bug agree perfectly, so
   the second one is deliberately not the first rearranged: it walks a frontier
   breadth-first where the pack walks a stack.
2. **Termination.** Every chain terminates. A traversal that loops on a real
   graph would loop on a real dossier.
3. **Origin merging.** Nodes sharing a top-level namespace merge, the way sources
   sharing an author do. The reduction from roots to origins is the number this
   pack reports, so it is the number worth checking.

With no `--library`, this uses the Python standard library that is running it.
That is a real derivation DAG of thousands of modules, written over decades by
people who had never heard of this pack, and it is present on every machine that
can execute this file. Requiring the flag meant the one check here that grades
the traversal against something nobody in this project authored reported
NOT_RUN on every machine where nobody thought to pass a path.

Usage:
    import_graph.py [--library <path/to/source>] [--sample 400] [--json]

Exit: 0 the traversals agree everywhere, 1 they do not, 2 usage/IO
"""

from __future__ import annotations

import sysconfig

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
sys.path.insert(0, str(PACK / "scripts"))
import archlib as al  # noqa: E402

RE_IMPORT = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)


RE_PY_IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))",
                          re.MULTILINE)


def build_sources(root: Path, limit: int | None = None) -> dict[str, dict]:
    sources: dict[str, dict] = {}
    # Take a SPREAD through the tree, not the alphabetical head. Slicing a
    # sorted list gave four hundred modules from the start of the alphabet whose
    # imports all pointed outside the sample, so every chain terminated in one
    # hop and the traversal was never actually exercised — a test that passes
    # because it is shallow looks exactly like a test that passes.
    # Index the WHOLE graph and sample which CHAINS to walk, rather than
    # sampling the graph. A sampled graph has most of its edges pointing outside
    # itself, so every chain terminates in one hop and the traversal is never
    # exercised — the test passed at depth 2 and would have passed with the
    # traversal removed.
    # Two shapes of real library, because the point is an import DAG nobody in
    # this project authored — not any particular language. The scanner read only
    # one extension, so the default library (the Python that is running this)
    # produced zero modules and the check quietly had nothing to test.
    suffix, pattern = (".lean", RE_IMPORT) if any(root.rglob("*.lean")) else (".py", RE_PY_IMPORT)
    for path in sorted(root.rglob(f"*{suffix}")):
        module = str(path.relative_to(root)).replace("/", ".")[: -len(suffix)]
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        sources[module] = {
            "id": module, "kind": "primary", "date": "2020",
            # `findall` yields tuples when the pattern has more than one group
            # (`from X import` / `import X`); keep whichever alternative matched.
            "derives_from": [m if isinstance(m, str) else next(filter(None, m), "")
                             for m in pattern.findall(text)],
            "origin": module.split(".")[0],
        }
    return sources


def independent_roots(node: str, sources: dict[str, dict]) -> set[str]:
    """A second traversal, breadth-first over an explicit frontier."""
    roots: set[str] = set()
    seen: set[str] = set()
    frontier = [node]
    while frontier:
        nxt: list[str] = []
        for current in frontier:
            if current in seen:
                continue
            seen.add(current)
            entry = sources.get(current)
            if entry is None:
                roots.add(current)
                continue
            parents = entry.get("derives_from") or []
            if not parents:
                roots.add(current)
            else:
                nxt.extend(parents)
        frontier = nxt
    return roots


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--library",
                    help="default: the standard library of the running Python")
    ap.add_argument("--sample", type=int, default=400)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = (Path(args.library).expanduser() if args.library
            else Path(sysconfig.get_paths()["stdlib"]))
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 2

    sources = build_sources(root)
    if not sources:
        print("no modules found; nothing external to test against", file=sys.stderr)
        return 2

    disagreements, cycles, depths, reductions = [], [], [], []
    merge_candidates: list[str] = []
    # Walk a spread of chains through the full graph, deepest first — a chain
    # with one import tests nothing.
    ordered = sorted(sources, key=lambda m: -len(sources[m]["derives_from"]))
    chains = ordered[:args.sample]
    checked = len(chains)
    for module in chains:
        pack_roots, pack_cycles = al.trace(module, sources)
        theirs = independent_roots(module, sources)
        if set(pack_roots) != theirs:
            disagreements.append({
                "module": module,
                "only_pack": sorted(set(pack_roots) - theirs)[:3],
                "only_independent": sorted(theirs - set(pack_roots))[:3]})
        if pack_cycles:
            cycles.append({"module": module, "cycles": pack_cycles[:3]})
        depths.append(len(pack_roots))
        summary = al.independence([module], sources)
        if summary["independent_support"] < len(summary["distinct_roots"]):
            reductions.append(module)
        merge_candidates.extend(
            r for r in summary["distinct_roots"] if r in sources)

    result = {
        "modules_indexed": len(sources),
        "chains_checked": checked,
        "traversals_agree": f"{checked - len(disagreements)}/{checked}",
        "cycles_found": len(cycles),
        "max_roots_for_one_node": max(depths) if depths else 0,
        "chains_where_origins_reduce_roots": len(reductions),
        "origin_merging_exercised": bool(merge_candidates),
        "note_on_merging": (
            "roots in this graph mostly lie OUTSIDE the indexed set, and a node the set does not "
            "contain has no declared origin — so merging was not exercised here. A zero above "
            "means 'not tested', not 'no cascades found', and the difference is the whole reason "
            "to say it"
            if not merge_candidates else
            f"{len(merge_candidates)} root(s) carried a declared origin, so merging was exercised"),
        "disagreements": disagreements[:5],
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("EXTERNAL — a derivation graph this pack did not draw\n")
        for key in ("modules_indexed", "chains_checked", "traversals_agree", "cycles_found",
                    "max_roots_for_one_node", "chains_where_origins_reduce_roots"):
            print(f"  {key.replace('_', ' '):<32} {result[key]}")
        print(f"  {'origin merging exercised':<32} {result['origin_merging_exercised']}")
        print(f"    {result['note_on_merging']}")
        for item in result["disagreements"]:
            print(f"    DISAGREE {item['module']}: pack-only {item['only_pack']}, "
                  f"independent-only {item['only_independent']}")
        if not disagreements:
            print("\n  Two independently written traversals agree on every chain in a graph\n"
                  "  neither was designed against. That is worth more than agreement with a\n"
                  "  fixture: it is the only evidence here that the collapse is correct rather\n"
                  "  than merely self-consistent.")
    return 1 if disagreements else 0


if __name__ == "__main__":
    sys.exit(main())
