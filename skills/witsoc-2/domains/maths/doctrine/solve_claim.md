# Solve claims — what has to hold before "solved" may be said

A frontier solve is an extraordinary claim. The gate is not "did the kernel
pass": a proof can be correct, kernel-checked, and still not a discovery — and a
run is the worst possible judge of its own result.

## Two stages

| Stage | Claims | Extra requirement |
|---|---|---|
| `MATHEMATICAL_SOLVE` | the argument closes the target | none beyond the four below |
| `FORMAL_SOLVE` | the argument closes it **and** a checker agrees | a validated Lean receipt |

The receipt is validated, not merely present. An unvalidated receipt is
routinely just evidence that Lean ran — environment output with no bearing on
the target — and that must never support a solve.

## Stage 1: the audit

The stage-1 audit is **demote-only**. It blocks; it never blesses. Passing it
authorizes *opening* a claim and nothing more. With evidence missing or
unreadable it returns `NOT_READY` with explicit failures — it must never fall
through to a pass, because an absent file would otherwise read as a satisfied
condition.

A node is **strong** when a closed proof sketch or a kernel-verified status
stands behind it. Eight conditions:

1. **Frozen target** — a run manifest carrying a target hash. Without it there
   is no fixed statement to have solved.
2. **Full closure** — every DAG node is strong, or an honest dead route
   (`FAILED_ATTEMPT`) that nothing strong depends on. Any other status leaves
   the target open.
3. **Grounded dependencies** — every dependency of a strong node resolves to
   another strong node. A strong node leaning on a conjecture, a dead route, or
   a missing node is a proof resting on nothing.
4. **Acyclic** — no dependency cycle among the strong nodes. A cycle is a proof
   of A from A wearing two names.
5. **Skeptic fleet** — at least three passing reviews per strong node, each
   having checked target drift, hidden assumptions, circularity, and
   weaker-target substitution.
6. **No open gaps** — no unresolved gap class recorded against any strong node.
7. **Disproof-first** — a recorded disproof search that found no witness. A
   recorded witness means the target may be false, which outranks any proof of
   it.
8. **Preconditions audited** — every cited theorem's preconditions resolved. An
   unmet hypothesis on a cited result is a hole, not a citation.

## The four requirements

All four are mandatory; none substitutes for another.

1. **Audit passed** — the primary run clears every stage-1 condition.
2. **Formal receipt** — for `FORMAL_SOLVE`, a validated kernel receipt.
3. **Independent re-derivation** — at least one, in a **different run
   directory**, passing its own stage-1 audit, with a **matching frozen-target
   hash**.
4. **Novelty** `NOVEL_CANDIDATE` — `KNOWN` and `KNOWN_INTERNAL` reject the
   claim; `LOCALLY_NEW_UNCHECKED` is not enough at these stakes.

### Why re-derivation must be a separate run

A second pass in the same directory shares the first pass's artifacts, its
framing, and its blind spots. It repeats the derivation; it does not corroborate
it. Independence is the whole content of the requirement, so the check is
structural: same directory is refused outright, and the hash must match or the
re-derivation proved a different statement — the most common way an
"independent confirmation" confirms nothing.

### Why novelty is a requirement

Mathematical priority is real. A correct but already-known result is not a
discovery, and reporting it as one is a false claim about the state of the field
rather than about the mathematics. `KNOWN` therefore rejects on priority even
though the proof is fine. `LOCALLY_NEW_UNCHECKED` means only that this system
has not seen it before, which is a statement about the system's memory, not
about the literature.

## Status is derived

`computed_status` is recomputed from the satisfied requirements on every
mutation and is never stored as a free-form label. A label anyone can write is a
label anyone can write to `SOLVE_ACCEPTED`; deriving it means the status cannot
drift from the evidence.

`CLAIMED → SOLVE_ACCEPTED` only when every machine-verification requirement
holds. **`REJECTED` is terminal** — once rejected, no further evidence is
accepted on that claim. A rejected claim that could be revived by piling on
evidence would let a failed novelty check be outvoted.

Human review may be recorded as optional evidence. It does not substitute for
any machine requirement.

**Only `SOLVE_ACCEPTED` may be reported as a solve of the named problem.**
Everything else — including a run that passes the stage-1 audit — is reported at
its actual status.

## Implementation

`scripts/solve_gate.py` implements the stage-1 conditions and the four
requirements; run `--help` for usage.
