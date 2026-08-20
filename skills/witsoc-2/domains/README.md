# Domain Packs

Everything in this directory sits **below the contract line**. The frame never
reaches in here; it resolves a pack through its `domain.json` manifest and calls
the declared adapter. `scripts/check_frame_purity.py` enforces that direction
mechanically.

## Registered packs

| Pack | Field | Researcher called | Ceiling | Contract | Auto-selected |
|---|---|---|---|---|---|
| `maths` | Mathematics — WIT, kernel elaboration, bounded search | Lovasz | `VERIFIED` | 2 | yes |
| `bio` | Perturbation biology — denominators, recomputation, refutation | Durbin | `CHECKED_BOUNDED` | 2 | yes |
| `archival` | Documentary claims — citation-cascade collapse, survivorship | Ranke | `CHECKED_BOUNDED` | 2 | yes |
| `_mock` | *(not a field — frame test fixture)* | Researcher | `VERIFIED` | 2 | no, `explicit_only` |

`archival` is also the contract's third-party test: it was built under a rule of
changing nothing in the frame, and `domains/archival/FRICTION.md` logs every time
that rule bit. The rule held, and the log is a more useful document than the pack.

The ceiling column is worth reading. `bio` tops out below the lattice's top
status on purpose: empirical support is support for a frozen dataset, context,
and analysis, and calling that `VERIFIED` would erase the distinction the status
contract exists to draw. A pack whose honest maximum is `CHECKED_BOUNDED` is
also the frame's best test that ceilings are enforced rather than advertised.

The frame is usable with no pack at all — it can freeze targets and triage —
but nothing can be admitted until an adapter exists to say no.

## How one gets chosen

Not by eye. Every run starts with:

```bash
python3 scripts/resolve_domain.py --statement "<the problem, verbatim>"
```

It reads each pack's `selection` block — contract item 6 — and prints the exact
files the three roles must load, the adapter, the schemas, the gates, and the
ceiling. A pack that declares no selection block is reachable only by
`--domain <name>`, which means in practice it is never reached: an unloaded pack
is indistinguishable from an unwritten one, and the failure is silent because
the roles run anyway.

`resolve_domain.py --self-test` replays every pack's declared examples and
counter-examples. Run it after touching any `selection` block; a signal list
that has broadened enough to steal another pack's problems fails there rather
than in a campaign.

When nothing matches, `scripts/scaffold_domain.py` improvises a provisional pack
from the closest registered one — a real adapter, a real refute-attempt gate,
real negative controls, and a hard `SKETCH` ceiling, because the system writing
the checker is the one producing candidates for it. It lets a run proceed; it
does not let a run conclude.

## What lives here

One directory per field, self-contained:

```
domains/<name>/
  domain.json          # the six-item manifest, including `selection`
  claim.schema.json    # extends frame-claim-v1
  receipt.schema.json  # what a receipt looks like here
  scripts/             # the verification backend
    check.py             # adapter entry point: (artifact, claim, tier) -> receipt
    availability.py      # probe a tier before spending against it
    tiers/               # one module per backend
    gates/               # blocking checks
    negative_control/    # known-bad inputs the adapter must reject
  doctrine/            # this field's rules
    explorer.md          # loaded by Explorer when this pack is selected
    generator.md         # loaded by Generator
    researcher.md        # loaded by Researcher
```

`doctrine/<role>.md` is the mechanism by which a field's instructions reach the
general roles. All three are required: a pack whose roles have no instructions
cannot actually be worked.

Keep a pack in **one** directory. The predecessor system spread a single field
across several top-level directories and the pieces drifted apart; that is the
specific mistake this layout exists to avoid.

## `_mock`

Not a field. It is the minimal conformant pack the frame tests against, so the
frame can demonstrate it has no hidden dependency on any particular domain
(governance rule 5). Copy its *shape* when writing a real pack, not its content.

Its adapter is a real, working, deliberately trivial checker: it compares an
artifact against an expected value. That is enough to exercise the whole loop —
freeze, produce, verify, receipt, refute-attempt, escalate — without pulling in
any field's toolchain.

## Adding one

See `references/domain_pack_contract.md`. Then:

```bash
python3 scripts/validate_domain_pack.py domains/<name>/domain.json
python3 scripts/check_frame_purity.py
```

Both must pass before the pack is registered in the table above.
