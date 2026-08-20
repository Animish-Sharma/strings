# Demotion

Demotion rules are not caution. They are the mechanism that makes a status mean
something, and most of them fire on runs that were done carefully.

## Automatic demotions

| Condition | Result |
|---|---|
| target hash missing or mismatched | `FAILED_ATTEMPT` until repaired |
| support is literature-only | at most `CONJECTURE`, unless the claim itself is a literature claim |
| no independent experimental unit | no population-level inference, at any strength |
| no strong baseline | no predictive-superiority claim |
| split leakage on the claimed axis | `REJECTED` for the performance claim |
| model does not beat the strongest baseline | `REJECTED` or `CONJECTURE`, depending on how the claim is worded |
| source provenance missing | demoted until repaired |
| evidence graph disconnected | strong status unavailable |
| analysed context differs from frozen context | narrow to a new claim with a new hash, or demote |
| no independent replication | never `CHECKED_REPRODUCED` |
| negative control fires | everything from that pipeline is uninformative until fixed |

## Demotion is not failure

A correct demotion is the pack working. The corpus this pack is built to serve
rewards correct rejection and correct narrowing, not fluent reports — and a
system that never demotes has not been shown to be right, it has been shown to
be unable to say no.

## Recording a demotion

A demotion carries three things or it is not useful:

1. **Which rule fired**, by name.
2. **What the claim can still support** — usually something, and usually narrower.
   A rejected population claim is often an intact within-screen claim.
3. **The minimal missing evidence** that would lift it. Three more donors crossed
   with condition. One independent accession. A negative control that comes back
   silent. Named, not gestured at.

The third is what makes the record worth keeping, and it is the part usually
left out.

## Do not repair by narrowing silently

The tempting repair for a failed population claim is to analyse the subset where
it worked. That is a new claim, it needs a new hash, and reporting it against the
old statement is the failure the context-protection gate exists to catch. The
legitimate version of the same move is to freeze the narrower claim first, on its
own terms, and audit it honestly.
