# Witsoc

Witsoc is a collection of mathematical research orchestration utilities used by
the Witsoc skill. The package exposes the same command surface as the local
`scripts/witsoc.py` entrypoint while making the tools installable with `pip`.

Initial package scope:

- stable `witsoc` console command;
- compatibility with existing script names and orchestrator calls;
- packaged references, schemas, and subskill files needed by the scripts;
- gradual migration path from standalone scripts to importable modules.

PyPI package:

```text
https://pypi.org/project/witsoc/
```

If the local Witsoc script tree is missing in a fresh environment, install from
PyPI:

```bash
python3 -m pip install -U witsoc
```

or:

```bash
uv pip install -U witsoc
```

The canonical OpenScientist skill directory is:

```text
~/.openscientist/skills/witsoc
```

If that skill folder exists but `scripts/` and/or `src/` were deleted, restore
them into that folder from the installed PyPI package:

```bash
python3 -m pip install -U witsoc
python3 -m witsoc restore-skill --target ~/.openscientist/skills/witsoc --replace
```

Or from a surviving `bootstrap.py` inside the skill folder:

```bash
python3 ~/.openscientist/skills/witsoc/bootstrap.py --replace
```

Check without changing files:

```bash
python3 -m witsoc restore-skill --target ~/.openscientist/skills/witsoc --check
python3 ~/.openscientist/skills/witsoc/bootstrap.py --check
```

Force a refresh from PyPI:

```bash
python3 -m witsoc restore-skill --target ~/.openscientist/skills/witsoc --replace
python3 ~/.openscientist/skills/witsoc/bootstrap.py --replace
```

Restore an explicit target:

```bash
python3 -m witsoc restore-skill --target ~/.openscientist/skills/witsoc --replace
python3 ~/.openscientist/skills/witsoc/bootstrap.py --replace
```

Fresh-machine setup without checking in `scripts/`:

```bash
python3 -m pip install -U witsoc
mkdir -p ~/.openscientist/skills/witsoc
python3 -m witsoc restore-skill --target ~/.openscientist/skills/witsoc
python3 ~/.openscientist/skills/witsoc/scripts/witsoc.py --help
```

## Runtime Preflight

Before using Witsoc scripts from a skill folder, verify:

```bash
test -f ~/.openscientist/skills/witsoc/scripts/witsoc.py
test -f ~/.openscientist/skills/witsoc/src/witsoc/cli.py
```

If either check fails:

```bash
python3 ~/.openscientist/skills/witsoc/bootstrap.py --replace
```

The safest local launcher is:

```bash
python3 ~/.openscientist/skills/witsoc/witsoc.py --help
```

It checks `scripts/` and `src/`, restores them through `bootstrap.py` if they
are missing, and then delegates to `scripts/witsoc.py`.

Example:

```bash
witsoc route "deep run prove or disprove this open conjecture"
witsoc lovasz-packet runs/example
witsoc lovasz-kernel runs/example --write
witsoc lovasz-judge runs/example --write
witsoc lovasz-autopsy runs/example --write
witsoc explorer-target-model runs/example --write
witsoc generator-obligations runs/example --write
witsoc scorecard runs/example --write
witsoc ui-summary runs/example --write
witsoc orchestrator-plan route "prove a theorem"
witsoc map
witsoc target init --source "forall n, P n" --output runs/example/canonical_target.json
witsoc research-graph init runs/example/research_graph.json
witsoc discover init runs/example
witsoc discover search runs/example --generations 50 --harvest
witsoc drive runs/example --finalize
witsoc regression-audit
```

Nested aliases are also available:

```bash
witsoc strategy rank-lanes --prompt "deep run prove or disprove this open conjecture"
witsoc lovasz packet runs/example
witsoc lovasz kernel runs/example --write
witsoc lovasz judge runs/example --write
witsoc lovasz autopsy runs/example --write
witsoc explorer target-model runs/example --write
witsoc explorer discover init runs/example
witsoc lovasz discover search runs/example --generations 100 --harvest
witsoc generator obligations runs/example --write
witsoc generator discover init runs/example
witsoc generator cycle runs/example --lean-file runs/example/Solution.lean --lake-dir .
witsoc durbin evidence-graph runs/bio/example
witsoc durbin target-ladder runs/bio/example
witsoc durbin discover init runs/bio/example
```

## Lazy Surface

Witsoc is intentionally lazy at the package boundary. The default command
surface exposes cheap routing and decision packets first; heavy research engines
remain callable by explicit command name or by the orchestrator after it chooses
a plan.

Cheap boundary calls:

```bash
python3 ~/.openscientist/skills/witsoc/witsoc.py llm-contract
python3 ~/.openscientist/skills/witsoc/witsoc.py subskills
python3 ~/.openscientist/skills/witsoc/witsoc.py next-action runs/<task> --write
python3 ~/.openscientist/skills/witsoc/witsoc.py proof-workflow runs/<task> --write
python3 ~/.openscientist/skills/witsoc/witsoc.py scorecard runs/<task> --write
python3 ~/.openscientist/skills/witsoc/witsoc.py ui-summary runs/<task> --write
python3 ~/.openscientist/skills/witsoc/witsoc.py ui-summary runs/<task> --write --deep
python3 ~/.openscientist/skills/witsoc/witsoc.py explorer target-model runs/<task> --write
python3 ~/.openscientist/skills/witsoc/witsoc.py generator obligations runs/<task> --write
python3 ~/.openscientist/skills/witsoc/witsoc.py lovasz autopsy runs/<task> --write
python3 ~/.openscientist/skills/witsoc/witsoc.py spawn-template explorer --target "..."
witsoc route "..."
witsoc next-action runs/<task> --write
witsoc proof-workflow runs/<task> --write
witsoc scorecard runs/<task> --write
witsoc ui-summary runs/<task> --write
witsoc ui-summary runs/<task> --write --deep
witsoc orchestrator-plan route "..."
witsoc strategy rank-lanes --prompt "..."
witsoc lovasz packet runs/example
witsoc lovasz kernel runs/example --write
witsoc lovasz judge runs/example --write
witsoc lovasz autopsy runs/example --write
```

Discover commands by tier:

```bash
witsoc commands
witsoc commands --tier core
witsoc commands --tier heavy --json
witsoc install-help
```

Old direct aliases still work for compatibility, for example:

```bash
witsoc counterexample-search runs/example
witsoc worker-dispatch runs/example --write
```

Those commands are not imported or loaded until invoked.

## Run Product Contract

For UI and report preview, use:

```bash
witsoc ui-summary runs/<task> --write
```

It writes `witsoc_ui_summary.json`, `reports/witsoc_preview.md`, and a starter
`reports/witsoc_report.md` plus `reports/report.md` from the current Explorer,
Lovasz, Generator, workflow, and scorecard packets. Add `--deep` for deep runs
to scan all WIT, Lean, SOC, JSON, receipt, DAG, and report artifacts.

For serious mathematical work, use the next-action packet as the cheap control
surface:

```bash
witsoc next-action runs/<task> --write
```

It emits `runs/<task>/witsoc_next_action.json` and materializes missing default
scaffolds:

```text
proofs/<task>.soc
reports/witsoc_status.md
```

The packet tells the orchestrator the current status, exact gap, next action,
evaluator, success condition, failure route, and expected artifacts. It is
advisory; the orchestrator remains in charge.

## Build

From this directory:

```bash
uv build
```

This produces:

```text
dist/witsoc-0.2.2.tar.gz
dist/witsoc-0.2.2-py3-none-any.whl
```

Local wheel smoke test:

```bash
python3 -m venv /tmp/witsoc-venv
/tmp/witsoc-venv/bin/pip install --no-deps dist/witsoc-0.2.2-py3-none-any.whl
/tmp/witsoc-venv/bin/witsoc route --field route "deep run prove or disprove this open conjecture"
/tmp/witsoc-venv/bin/witsoc regression-audit --quick
```

Publish, after configuring PyPI credentials:

```bash
uv publish
```

## Migration Model

Version `0.2.2` adds strict typed acceptance evidence, independent Explorer
terminal review, held-out information-gain calibration, optional semantic
retrieval, semantically receipted Lovasz dependency edges, reviewed DAG
compression, executable CEGIS, multi-round Generator proof-body synthesis with
clean rollback, direction-aware Durbin evidence, source-independence gates,
causal hypothesis updates, and a domain-neutral executable regression audit.
Lovasz and Durbin still search freely in an unconstrained arena; only typed,
audited, falsifiable candidates cross the promotion boundary into research
claims.
The stable entrypoint is `witsoc.cli:main`.
