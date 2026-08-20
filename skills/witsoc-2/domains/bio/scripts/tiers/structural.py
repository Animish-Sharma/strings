#!/usr/bin/env python3
"""Structural tier — is this audit bundle even shaped like evidence?

Ceiling SKETCH, not adversarial. It reads the artifact and the frozen claim and
nothing else; it cannot tell you the biology is right, and it is not trying to.
What it catches is the class of failure that makes every later check meaningless:
a context that was never frozen, an evidence graph whose conclusion is not
connected to anything measured, and a bundle that has quietly stopped being about
the claim it names.

Three checks:

1. FREEZE — every dimension of the claim is present. Present includes an
   explicit `unknown` / `not_reported` / `not_applicable`; it excludes silence.
   A silently missing dose is indistinguishable in a report from a dose that did
   not matter, and the two have very different consequences.
2. CONNECTIVITY — every claim node traces back through the graph to at least one
   pinned source or dataset, and no node dangles. A disconnected evidence graph
   is a bibliography drawn as a diagram.
3. BINDING — the bundle's target hash equals the claim's recomputed hash. This
   is where a claim edited to fit the analysis gets caught, and it is cheap, so
   it runs first at every tier.

Usage:  structural.py <bundle.json> --claim <claim.json> [--json]
Exit:   0 pass, 1 fail, 2 error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

EXPLICIT_UNKNOWN = {"unknown", "not_reported", "not_applicable", "none", "n/a"}

# Every dimension that can change how a perturbation result is interpreted.
# Nested paths are dotted.
REQUIRED_DIMENSIONS = [
    # `exact_statement` is the frame's name for this, adopted after a
    # contract-shape check found the pack's own name silently dropping the claim
    # text on the way into campaign state.
    "exact_statement", "organism", "claim_class",
    "biological_context.cell_type", "biological_context.tissue",
    "biological_context.disease_state", "biological_context.donor_or_model_system",
    "perturbation.entity", "perturbation.modality", "perturbation.dose",
    "perturbation.duration", "perturbation.delivery",
    "assay.type", "assay.readout", "assay.experimental_unit",
    "assay.controls", "assay.batches", "assay.replicates",
    "dataset.id", "dataset.version", "dataset.source", "dataset.preprocessing_state",
    "claimed_effect.direction", "claimed_effect.magnitude", "claimed_effect.endpoint",
    "falsification_conditions", "allowed_scope",
]

NODE_KINDS = {"claim", "source", "dataset", "assay", "replicate", "endpoint",
              "model_performance", "analysis", "control"}
GROUNDING_KINDS = {"source", "dataset"}


def dig(obj: dict, path: str):
    node = obj
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def check_freeze(claim: dict) -> list[str]:
    problems = []
    for path in REQUIRED_DIMENSIONS:
        value = dig(claim, path)
        if value is None:
            problems.append(
                f"{path} is absent. Freeze it explicitly — 'unknown' or 'not_reported' is a "
                "frozen value, silence is not, and only one of them survives review"
            )
        elif isinstance(value, str) and not value.strip():
            problems.append(f"{path} is empty; write what is actually known, or 'unknown'")
        elif isinstance(value, list) and not value:
            problems.append(f"{path} is an empty list; if there are none, say 'none' explicitly")
    falsifiers = claim.get("falsification_conditions")
    if isinstance(falsifiers, list) and all(
        isinstance(f, str) and f.strip().lower() in EXPLICIT_UNKNOWN for f in falsifiers
    ):
        problems.append(
            "falsification_conditions are all 'unknown'. A claim with no stated way to be "
            "wrong cannot be audited — there is nothing for a check to fail"
        )
    return problems


def check_graph(bundle: dict) -> tuple[list[str], dict]:
    graph = bundle.get("evidence_graph") or {}
    nodes = {n.get("id"): n for n in graph.get("nodes", []) if isinstance(n, dict) and n.get("id")}
    edges = [tuple(e) for e in graph.get("edges", []) if isinstance(e, (list, tuple)) and len(e) == 2]
    problems = []

    if not nodes:
        return ["evidence_graph has no nodes; there is no evidence structure to check"], {}

    for node_id, node in nodes.items():
        if node.get("kind") not in NODE_KINDS:
            problems.append(
                f"node {node_id!r} has kind {node.get('kind')!r}, which is not one of "
                f"{sorted(NODE_KINDS)}. An unclassified node cannot be reasoned about"
            )

    known = set(nodes)
    for src, dst in edges:
        for end in (src, dst):
            if end not in known:
                problems.append(f"edge references unknown node {end!r}")

    # Reachability from each claim node back to something pinned.
    incoming: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        if dst in incoming:
            incoming[dst].append(src)

    def reaches_ground(start: str) -> bool:
        seen, stack = set(), [start]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if current != start and nodes.get(current, {}).get("kind") in GROUNDING_KINDS:
                return True
            stack.extend(incoming.get(current, []))
        return False

    claim_nodes = [n for n, node in nodes.items() if node.get("kind") == "claim"]
    if not claim_nodes:
        problems.append("evidence_graph has no node of kind 'claim'; nothing is being supported")
    for node_id in claim_nodes:
        if not reaches_ground(node_id):
            problems.append(
                f"claim node {node_id!r} does not trace back to any source or dataset. "
                "Whatever supports it is not in this graph, so the graph cannot support it"
            )

    connected = {n for edge in edges for n in edge}
    for orphan in sorted(set(nodes) - connected):
        problems.append(
            f"node {orphan!r} is connected to nothing. An unattached node is decoration; "
            "attach it or drop it"
        )

    return problems, {
        "nodes": len(nodes),
        "edges": len(edges),
        "claim_nodes": len(claim_nodes),
        "grounding_nodes": sum(1 for n in nodes.values() if n.get("kind") in GROUNDING_KINDS),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--claim", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        bundle = bl.read_json(args.bundle)
        claim = bl.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)}))
        return 2

    problems = check_freeze(claim)

    recomputed = bl.target_sha256(claim)
    declared = claim.get("target_sha256")
    if declared and declared != recomputed:
        problems.append(
            f"claim.target_sha256 is {declared[:16]}... but its contents hash to "
            f"{recomputed[:16]}.... The claim has been edited since it was frozen"
        )
    if bundle.get("target_sha256") not in (None, recomputed):
        problems.append(
            f"bundle is bound to target {str(bundle.get('target_sha256'))[:16]}..., the claim "
            f"hashes to {recomputed[:16]}.... This bundle is evidence about a different claim"
        )

    graph_problems, graph_stats = check_graph(bundle)
    problems += graph_problems

    result = {
        "tier": "structural",
        "verdict": "fail" if problems else "pass",
        "max_status": "SKETCH",
        "target_sha256": recomputed,
        "graph": graph_stats,
        "problems": problems,
        "failure_class": "structural_freeze" if problems else None,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['verdict'].upper()} — {len(problems)} problem(s)")
        for problem in problems:
            print(f"  {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
