# Two packs on one claim

Biological plausibility and statistical validity are different competences and
they fail in different directions. A design can be biologically impeccable and
statistically meaningless. An estimator can be provably correct about a quantity
nobody should care about.

The frame's answer is **two packs on one claim** — each auditing within its own
competence, neither speaking for the other's field, and a fatal objection from
either blocking admission — not a
fourth role.

## The division

| Bio pack (Durbin) audits | A statistics pack audits |
|---|---|
| biological context and its limits | the estimand and whether it is identified |
| perturbation modality, dose, efficacy | uncertainty at the matching denominator |
| assay, readout, controls | multiplicity and what a correction controls |
| mechanism plausibility | power and minimum detectable effect |
| dataset suitability | baselines, splits, metrics, leakage |
| generalization and follow-up | formal sub-claims about estimators |

## Until a statistics pack is registered

The `statistical-audit` gate holds those obligations inside this pack **and says
so on every run**. That is deliberate: an audit performed by the same pack that
designed the experiment is weaker than one performed by a specialist who did
not, and the note keeps the weakness visible rather than letting it become the
normal state of affairs.

When such a pack is registered, this gate becomes a delegation. Same
obligations, audited by something with no stake in the design.

## The rules when packs are paired

- **Each pack audits inside its own competence and returns its own verdict.**
  Neither speaks for the other's field.
- **The frozen claim is shared.** Each pack contributes its own frozen conditions
  and the target hash covers all of them.
- **A fatal objection from either pack blocks admission.** Verdicts are not
  averaged, and a pass in one field never compensates for a failure in another.
- **Establishing something in one field does not establish it in the other.** A
  proof about an estimator's properties does not make the estimand biologically
  meaningful. Donor replication does not establish an unrestricted mathematical
  claim.
- **A changed estimand or context starts a new claim** with a new hash, in both
  packs.

## Answering a challenge

A challenge from the other pack is resolved, unresolved-nonfatal, or
unresolved-fatal. **Prose dismissal is not a resolution.** "That analysis assumes
independence we do not have" is answered by changing the analysis or by
defending the assumption with evidence — not by noting that the assumption is
common.
