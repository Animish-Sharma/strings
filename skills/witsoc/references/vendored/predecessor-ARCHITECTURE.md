# Witsoc Frame / Domain-Pack Architecture

Witsoc's day-to-day behavior is mathematics: freeze a target, decompose it,
search for lemmas, drive a Lean kernel, refuse to call something true without a
verifier receipt. But the control flow underneath that — freeze, triage,
produce, verify, escalate, receipt — is not mathematics-specific. This document
names the boundary explicitly so a second domain (biology, already partially
built as `witsoc-bio`) and any future domain can attach without eroding the
part that is genuinely reusable.

This file is the frame's canonical architecture reference (governance rule 7
below). It does not replace `references/core/architecture.md` (platform
ownership: Witsoc vs. Plane/Theater/backend) or `references/core/services.md`
(the machine-readable service registry) or `references/core/routing.md`
(method dispatch) — it sits above them and states the invariant those files
must keep satisfying.

**Relationship to `witsoc`.** `../witsoc/` is the same architecture rebuilt
with the separation actually done: the identical three protected roles under
the identical names (Explorer / Generator / Researcher), the identical
five-item contract, the identical two refinements, and the identical governance
rules — plus mechanical enforcement (`scripts/check_frame_purity.py`,
`scripts/validate_domain_pack.py`) that this skill does not yet have. The two
must stay aligned. §5 below is the honest gap list between them; it records
what has not been separated here, and is not a competing design.

## 1. The Frame vs. The Domain Pack

**Frame** (domain-agnostic, written once, must not import anything
domain-specific):

- `SKILL.md` — coordinator: routing, status vocabulary, arbitration.
- The three protected roles: **Explorer** (triage/arbitration), **Generator**
  (produce + verify), **Researcher** (deep attack on the hard tail).
- Shared services: the verification-adapter interface, the evidence/lemma
  store, retrieval, the status contract, the failure-recovery ladder.
- The bridge layer: typed handoffs between roles and services
  (`references/core/handoff.md`), coordinator-owned — never role-to-role
  directly.

**Domain pack** (swapped per field, plugged in beneath a fixed contract):

- Math (baseline, as-built): `references/witsoc-explorer/`,
  `references/witsoc-generator/`, `references/witsoc-research-lovasz/`,
  `scripts/witsoc-generator/`, `scripts/witsoc-research-lovasz/`, plus the
  Lean/Mathlib-specific parts of `references/core/` and `scripts/*.py` (see
  §5, Current Compliance — this is the part that is *not yet* cleanly
  separated).
- Biology: `references/witsoc-bio/`, already unified under one directory —
  this is the pattern future domain packs should copy rather than math's
  three-directory, partially-frame-embedded layout.

Role names differ per domain, but the roles are the same three. The frame role
names are **Explorer / Generator / Researcher** — the same three used by the
`witsoc` rebuild, so the two skills describe one architecture. The roles are
general: loading a pack does not create a different role, it creates the same
role operating over that field's machinery.

| Frame role | Math instantiation | Biology instantiation |
|---|---|---|
| Explorer | Explorer (`witsoc-explorer`) | Explorer (freezes `joint_claim.json`, per `references/witsoc-bio/joint_research_protocol.md`) |
| Generator (produce candidate, drive through verification) | Generator (`witsoc-generator`, WIT/Lean) | No distinct name yet — the general Generator runs over the bio pack's analysis/verification path |
| Researcher (deep attack on the hard tail) | **Lovasz** (`witsoc-research-lovasz`) | **Durbin** (`references/witsoc-bio/`) |

`Lovasz` and `Durbin` are the same Researcher role with different fields plugged
in — the math and biology names for it. Neither is a separate role, exactly as
`references/core/compatibility.md` already states: "The stable phase identifiers
`witsoc-explorer`, `witsoc-research-lovasz`, `witsoc-generator`, and
`witsoc-bio` ... name method roles, not separately installed skills."

**Why this is easy to misread.** `references/witsoc-bio/strategy.md` lists the
configurations "Durbin without Lovasz", "Lovasz without Durbin", and "Paired
Durbin-Lovasz", with Durbin doing biological review and Lovasz doing
mathematical/statistical review. That pairing is **two domain packs engaged on
one joint claim** — each contributing its own Researcher within its own
competence — not two frame roles. A claim spanning two fields engages two packs;
it does not add a role. A fatal objection from either blocks admission, and
verdicts are never averaged.

`references/core/architecture.md` and `references/core/services.md` both list
"Explorer, Lovasz, Generator, and Durbin" as four coequal method packs and carry
a one-line correction pointing here. Keep this table as the disambiguation
whenever a new pack is added; do not let the service registry or route table
imply a fourth protected role. The no-fourth-role invariant (§4) depends on
reading it this way.

## 2. The Domain-Pack Contract

A domain pack supplies exactly five things. Nothing here is new invention —
Witsoc's own schema pattern (`math.problem.v1` / `math.result.v1` /
`math.admission.v1` in `references/schemas/`) already sketches items 1–3 for
math; this section makes the five-item boundary explicit and mandatory for any
pack, present or future.

1. **Verification adapter** — `(candidate artifact) -> (pass/fail, receipt)`.
   May be a dispatcher over multiple backends (math: symbolic/CAS check ->
   Lean kernel; a hypothetical quantum pack: symbolic -> simulation ->
   hardware) as long as it returns the same interface. The frame's Generator
   role never needs to know which tier ran.
2. **Claim schema** — a structured, frozen representation of the claim: exact
   claim, frozen target conditions, evidence hash, inputs, allowed mutations,
   required fields, status. Domain-specific fields are added on top of the
   generic ones already in `math.problem.v1`.
3. **Evidence/receipt format** — what counts as a receipt in this field: a
   Lean verifier log for math, a reproducibility manifest + statistical test
   output with seed and script hash for biology.
4. **Doctrine extension** — field-specific rules layered on the frame's
   generic doctrine (target-freeze, failure-recovery ladder, honesty/receipt
   gates): math's repair-budget-before-creative-leap rule
   (`references/core/lean_verification.md`, `references/core/repair.md`),
   biology's pre-registration-before-analysis and disagreement rules
   (`references/witsoc-bio/joint_research_protocol.md`).
5. **Gate definitions** — the checks a Generator artifact must pass before
   status can move from `CONJECTURE`/`OPEN` toward a `CHECKED_*`/`VERIFIED_*`
   status. These are domain-specific instantiations of the frame's generic
   gate mechanism (`references/core/production_gates.md`), not new frame
   code.

A domain pack must never import, monkey-patch, or special-case Explorer,
Generator, Researcher, or the bridge layer. If a field seems to need the frame
to behave differently, that need belongs in one of the five items above, not
in the frame.

## 3. Two Structural Refinements

Both tighten existing contract items (gate definitions, doctrine extension);
neither adds a role or touches Explorer/Generator/Researcher/the bridge layer.

### 3.1 Verification is propose -> adversarial-check -> receipt, not one call

For math, the Lean kernel already cannot be talked into a false pass, so the
existing kernel recheck (`re proves` in `references/core/lean_verification.md`)
*is* the refute-attempt gate — no new mechanism needed, only the recognition
that it is mandatory, not a bonus check.

For graded domains, a single favorable adapter run is not enough. Biology
already implements the right shape: the joint loop in
`references/witsoc-bio/joint_research_protocol.md` requires a candidate
synthesis to survive an independent adversarial audit — and an
unresolved-fatal-challenge check — before `CHECKED_BOUNDED` is reachable.
**Use this as the reference pattern for any future graded domain**: a candidate
is produced, an independent pass whose only job is to break it runs over it, and
only survival of that pass earns a receipt.

Every domain pack's gate-definitions list (contract item 5) must include a
named refute-attempt gate.

**The backend itself must also be audited.** Declaring a checker adversarial is
a claim made by the party being checked, so it carries conditions: independent
authorship, two-sided evidence that it does reject bad input, contamination
controls, and a registered negative control it must fail. Separately, a tier's
honesty and its reach are independent — an exhaustive search over a stated
finite domain is genuinely adversarial *and* permanently bounded — so each
declares a status ceiling that passing the gate never lifts. `witsoc`
enforces both mechanically; here they are doctrine only.

### 3.2 Explorer -> Researcher handoff is a mechanical trigger, not a judgment call

The frame's failure-recovery ladder owns one generic rule: **N consecutive
Generator failures on the same frozen sub-claim, or a repeated identical
failure signature, triggers escalation.** Math already implements this as a
concrete instance — `references/core/failure_recovery.md`'s stop condition
("the same failure class repeats three times ... per the Repair Budget in
`lean_verification.md`") is exactly this rule with `N=3`. Each domain pack
supplies only its own `N` and its own definition of "identical failure
signature" through its doctrine extension (contract item 4); the counter and
ladder mechanism live once, in the frame.

## 4. The No-Fourth-Role Invariant

Explorer, Generator, and Researcher are never collapsed or extended into a
fourth domain-spanning role, in any domain, because triage, production, and
deep-attack have different failure modes and time budgets: Explorer must stay
cheap, Generator must stay volume-efficient, Researcher must be allowed to run
long on one blocker. A proposal to add a fourth role — or to let a domain's
domain's role name (like Durbin) come to mean something structurally
distinct from the general role it labels — should get the same skepticism as a proposal to merge two of the
existing three.

## 5. Current Compliance (audit, 2026-08-19)

Honest status, so this doesn't quietly regress into looking done when it
isn't. Nothing below required a code change to write down; fixing it is future
work, tracked here rather than silently accepted.

- **Frame/domain leakage in `scripts/*.py`.** 184 of 269 top-level scripts
  (the nominally frame-owned service layer, see `references/core/services.md`)
  reference Lean or Mathlib directly (`grep -ril "lean\|mathlib" scripts/*.py`).
  Witsoc was built as a math skill first; the frame and the math domain pack
  grew tangled together at the script layer well before this document existed.
  This is debt, not a new problem, and unwinding it is a physical-reorg-scale
  change (see the repo's `ARCHITECTURE.md`-adjacent discussion in the PR/issue
  that requested this document) — out of scope for this doctrine pass.
- **Frame/domain leakage in `references/core/`.** `generator_gate.md`,
  `lean_verification.md`, and `repair.md` are math/Lean-specific content
  living in the frame's reference layer rather than under a math domain-pack
  directory. `status.md` mixes the domain-neutral research-status vocabulary
  (`OPEN`, `PARTIAL`, `CONDITIONAL`, ...) with WIT-file-header-specific rules
  (`UNVERIFIED`/`VERIFIED`/`GAP`/`REJECTED`) in one file.
  `production_gates.md` references WIT/Lean status explicitly in generic
  pre-answer checklist items. Treat any new frame document the same way: if it
  names Lean, Mathlib, or WIT, it is math domain-pack content and belongs
  under a `witsoc-*` reference directory, not `references/core/`.
- **Stale nested-skill directories.** `witsoc-bio/`, `witsoc-explorer/`,
  `witsoc-flow/`, `witsoc-generator/`, `witsoc-research-lovasz/` exist at the
  skill root as empty directories, left over from when these were separate
  installed skills (see `references/core/compatibility.md`). `witsoc
  restore-skill --replace` already exists to remove them; this document does
  not run it, since deleting directories is outside a doctrine-only pass, but
  a future cleanup pass should invoke that command rather than reinventing it.
- **Import-direction enforcement does not exist yet.** There is no lint or CI
  check that frame code never imports `references/witsoc-*` or hardcodes
  Lean/Mathlib. Governance rule 2 below names this as the cheapest guardrail
  against further erosion; it is not implemented.
- **Biology is the one domain pack that already matches the target shape**:
  one directory, all five contract items identifiable, the refute-attempt
  gate already implemented (§3.1). Point any future domain-pack author at
  `references/witsoc-bio/` before `references/witsoc-generator/`.

## 6. Governance

1. **One canonical location, one source of truth.** No skill or domain pack
   holds a second, independently-editable copy of frame code. If a domain
   pack ever needs its own copy of a frame utility, that need should first be
   asked: is this actually domain-specific, or does the frame need a generic
   hook?
2. **Import-direction enforcement.** Frame code (`SKILL.md`,
   `references/core/`, the domain-agnostic parts of `scripts/`) must never
   import from a `references/witsoc-*/` or `scripts/witsoc-*/` domain-pack
   directory. This is mechanically checkable (a grep-based check over import
   statements and Lean/Mathlib references in `references/core/`) and is the
   single cheapest guardrail against contract erosion — see §5 for why it
   does not exist yet.
3. **The five-item contract is the only extension point.** If adding a domain
   seems to require a new frame capability, ask first whether it is genuinely
   domain-neutral (e.g., a new generic status value useful across all
   domains) or whether it is that domain's verification adapter in disguise.
4. **No fourth role without a structural reason** (§4).
5. **Per-pack conformance, plus one frame suite.** Each domain pack should be
   able to point at its own five-item instantiation
   (`references/witsoc-bio/` already can; math currently cannot without
   reading three directories plus parts of `references/core/` — see §5), and
   the frame should carry a suite that runs against a minimal mock pack to
   prove it has no hidden domain dependency. Neither exists here yet; the
   `witsoc` rebuild implements both (`domains/_mock/`,
   `scripts/validate_domain_pack.py`).
6. **Versioned contract, not a moving target.** If the five-item contract in
   §2 changes, that is a deliberate, versioned change to this document, not
   an implicit one because a domain pack needed a workaround.
7. **Documentation lives with the frame, not per-domain.** This file describes
   the layers, the no-fourth-role invariant, and the contract; each domain
   pack carries only its own five-item instantiation as a short reference
   doc (see `references/core/domain_packs.md` for the current two).
8. **Cruft has no home in the frame tree.** Build artifacts
   (`__pycache__`, `.ruff_cache`, `dist/`, `.venv/`) and stale generated files
   are not architecture; keep them gitignored, not tracked, so their
   accumulation doesn't obscure real structural drift in diffs.

## 7. Extending Witsoc With A New Domain

1. Write the five contract items (§2) as one short reference doc under a new
   `references/witsoc-<domain>/` directory — model it on
   `references/witsoc-bio/`, not on the math directories.
2. Register the domain pack wherever `references/core/routing.md` and
   `references/core/services.md` list domains, and add a row to `SKILL.md`'s
   Route table and Load On Demand table.
3. Reuse Explorer/Generator/Researcher; give the domain's roles whatever
   field-appropriate names make sense (as biology
   did with Durbin), but record the mapping in a table like §1's.
4. Implement the refute-attempt gate (§3.1) and the escalation trigger (§3.2)
   as part of the doctrine extension and gate definitions — they are
   mandatory contract items, not optional extras.
5. Reuse the existing status vocabulary (`references/core/status.md`'s
   research statuses, not its WIT-header section) rather than inventing a
   parallel one.
6. Do not add a new role, and do not have the new domain pack import frame
   internals — everything it needs should be expressible through the five
   contract items.
