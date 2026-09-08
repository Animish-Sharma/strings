# Domain distributions

The installed Witsoc skill is an architecture core. Domain sources remain in
the development tree and are released independently:

| Domain | Distribution | Import package |
|---|---|---|
| maths | `witsoc` | `witsoc_domain_maths` |
| bio | `witsoc-bio` | `witsoc_domain_bio` |

`contracts/domain-packages.json` pins the exact version, core API range, domain
contract version, payload file count, byte count, digest, and compact selection
data. Edit the domain source or package version, then regenerate this file with
`python3 scripts/package_domains.py registry --write` before building.

## Runtime lifecycle

`route` scores the compact registry before loading domain files. Mathematical
tasks select `maths`; biological tasks select `bio`. If the selected pack is
dormant, `route` installs a universal wheel into the user cache, verifies every
payload file, and atomically materializes it under
`WITSOC_ROOT/domains/<domain>/`. Ordinary resolution and capability planning
then run against that established path. An unrelated request installs nothing.

The installer accepts only an exact version, binary wheel, and no dependencies.
The pip path uses PyPI directly. The curl fallback reads the exact-version PyPI
JSON endpoint, accepts only `files.pythonhosted.org`, verifies PyPI's SHA256,
extracts without links or path traversal, and then applies the same pinned
payload checks. Installation failure is `UNRESOLVABLE`.

## Mandatory bootstrap procedure

Do not infer availability by listing `WITSOC_ROOT/domains/`: a clean runtime is
supposed to have no domain directories. For every Witsoc request, pass the exact
statement to `route` first. Apply this mapping without substituting another
skill or a generic worker:

| Request | Required domain | Required distribution |
|---|---|---|
| mathematical or open-maths work | `maths` | `witsoc` |
| biological or open-biology work | `bio` | `witsoc-bio` |

`route` consults the compact registry even when the domain directory is absent.
For a selected dormant domain it must install, verify, cache, and activate the
pack before producing the ordinary domain load plan. Accept bootstrap only when
`domain_packages.activation.ok` is true, every action is `INSTALLED`, `READY`,
or `DEVELOPMENT_SOURCE`, the final route is `SELECTED` or `AMBIGUOUS`, and
`load_plan.ok` is true. Then run orchestrator preflight and require
`PREFLIGHT_READY` before creating task artifacts.

If a request is clearly in one of these domains but scoring returns `NO_MATCH`,
treat that as a classifier miss. Select and establish the known domain
explicitly, then route explicitly:

```bash
# Mathematical request
bash "$WITSOC" pack-ensure --domain maths --installer auto
bash "$WITSOC" route --statement "<request verbatim>" --domain maths --role explorer

# Biological request
bash "$WITSOC" pack-ensure --domain bio --installer auto
bash "$WITSOC" route --statement "<request verbatim>" --domain bio --role explorer
```

For normal network bootstrap, `auto` tries the exact pinned wheel through pip
and falls back to verified curl. Force one transport only when diagnosing it:

```bash
bash "$WITSOC" pack-ensure --domain maths --installer pip
bash "$WITSOC" pack-ensure --domain maths --installer curl
bash "$WITSOC" pack-ensure --domain bio --installer pip
bash "$WITSOC" pack-ensure --domain bio --installer curl
```

For an unpublished build, air-gapped host, or controlled rollout, point at the
directory containing the built wheels and prohibit network access:

```bash
WITSOC_PACK_WHEELHOUSE=/absolute/path/to/domain-packs \
WITSOC_PACK_OFFLINE=1 \
  bash "$WITSOC" pack-ensure --domain maths

WITSOC_PACK_WHEELHOUSE=/absolute/path/to/domain-packs \
WITSOC_PACK_OFFLINE=1 \
  bash "$WITSOC" pack-ensure --domain bio
```

After any install or repair, verify both cache and active bytes, then rerun
route and preflight:

```bash
bash "$WITSOC" pack-status --verify
bash "$WITSOC" route --statement "<request verbatim>" --role explorer
bash "$WITSOC" orchestrator-preflight --statement "<request verbatim>" \
  --workspace-root "$KIMI_WORK_DIR" --task-dir "runs/<task>" \
  --plane-tool "$PLANE_TOOL_BIN" \
  --out "$KIMI_WORK_DIR/.witsoc-activation-<task>.json"
```

## Researcher transport

Domain selection must survive worker dispatch. `orchestrator-handoff` emits a
sealed v4 handoff with `domain_binding.packages`, `capabilities`,
`episode_operators`, `skill_view_argv`, allowed commands, reasoning contract,
and the exact Explorer source map. Its capability mode and resources derive
from the exact episode lane, objective, route, evaluator, and expected delta,
so retrieval or computation does not inherit an unrelated campaign-level load.

The worker runs `pack-status --verify`, compares identity/version/digest/status
to the binding, and executes every bound `skill-view` before research. A domain
label in the target or capsule without this load is only classification. New v4
work fails closed rather than continuing with the architecture core alone; a
source-bound episode cannot downgrade to a legacy handoff.

Do not run a bare global `pip install`, copy package files manually, or add the
package cache to `PYTHONPATH`. Those actions bypass activation and do not
establish canonical Plane paths. On `UNRESOLVABLE`, retain the error and stop:
do not create run artifacts, claim the domain is unsupported, continue with the
architecture core alone, or replace Witsoc with another orchestrator.

Inspect or explicitly prepare packs with:

```bash
bash "$WITSOC_ROOT/scripts/witsoc.sh" pack-status --verify
bash "$WITSOC_ROOT/scripts/witsoc.sh" pack-ensure --domain maths
bash "$WITSOC_ROOT/scripts/witsoc.sh" pack-ensure --domain bio
```

Runtime controls:

- `WITSOC_PACK_CACHE`: override the user cache root.
- `WITSOC_PACK_WHEELHOUSE`: prefer local wheels, including offline installs.
- `WITSOC_PACK_INSTALLER=auto|pip|curl`: select the transport.
- `WITSOC_PACK_OFFLINE=1`: prohibit network access.
- `WITSOC_PACK_AUTO_INSTALL=0`: fail closed instead of installing.

## Release

Build and inspect both wheel and source artifacts with:

```bash
python3 scripts/check_domain_packages.py
python3 scripts/package_domains.py build --out dist/domain-packs
```

Never publish artifacts whose registry check or isolated package test is stale.
