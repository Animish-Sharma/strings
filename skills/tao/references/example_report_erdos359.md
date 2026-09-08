# Explaining: an agent run on Erdős problem #359

*Date:* 2026-07-29 · *Audience:* reader with general math background, new to
proof assistants and to this problem · *Sources:* the run's exit message;
erdosproblems.com forum thread 359; OEIS A002048

> This is a worked example of the Tao report format, kept in the
> skill's references. In a live OSci run this content would be
> `$PLANE_SESSION_DIR/report.md`, rendered in the Report tab.

## TL;DR

An agent run was asked to attack a genuinely open math problem dating to the
1920s. It could not solve it — nobody can, yet — and instead of pretending
otherwise, it produced the next best thing: it reduced the problem, showing
that both halves of Erdős's question follow from one single missing
ingredient, and had every step of that reduction machine-verified by the
Lean proof checker. The run's message is an honest report: "not solved;
here is real, verified partial progress instead."

## Prerequisites

### The MacMahon sequence `[core]`

- **What it is:** Build a list greedily: start with 1; each next term is the
  smallest integer bigger than the last that is *not* a sum of consecutive
  earlier terms. It begins 1, 2, 4, 5, 8, 10, 14, 15, … (OEIS A002048,
  MacMahon's "prime numbers of measurement").
- **Why this material needs it:** the entire problem is about how fast this
  sequence grows.
- **Where to learn more:** OEIS entry A002048.

### Growth-rate notation `[core]`

- **What it is:** "a_K / K → ∞" means the K-th term grows faster than
  linearly (faster than cK for every constant c). "a_K = K^{1+o(1)}" means
  it grows more slowly than K^{1.01}, K^{1.001}, and so on — barely more
  than linear. Erdős asked to prove the growth is squeezed between the two.
- **Why this material needs it:** both endpoints of the open problem are
  statements in this notation, and Andrews' conjectured precise rate,
  a_K ~ K·logK/loglogK, sits exactly inside that window.
- **Where to learn more:** any asymptotic-notation primer; Andrews (1975)
  for the conjecture.

### Lean and kernel-checking `[core]`

- **What it is:** Lean is a proof assistant — proofs written in it are
  verified by a small trusted "kernel" program, so a claim that compiles is
  mathematically certain. Two ways to cheat exist: `sorry` (a placeholder
  that lets unproved claims compile) and fake axioms (assuming what you
  claim to prove). The run explicitly rules out both.
- **Why this material needs it:** every "proved" claim in the run's message
  means "kernel-checked in Lean", nothing weaker.
- **Where to learn more:** the Lean 4 documentation.

## Step-by-step Explanation

### Step 1 — The problem statement

- **Plain statement:** Erdős #359 asks for a proof that the MacMahon
  sequence grows faster than linearly but only barely so.
- **Why it is here:** it defines the target; nothing is claimed yet.
- **How it works:** the two endpoints from the growth-notation prerequisite
  are exactly the two things Erdős asked to prove.
- **Concrete anchor:** why does the sequence go 1, 2, 4, 5, 8? After (1, 2),
  the number 3 is banned because 3 = 1+2. After (1, 2, 4), the block sums
  are 1, 2, 4, 3, 6, 7 — so 5 is allowed, then 6 = 2+4 and 7 = 1+2+4 are
  banned, giving 8.
- **Common trap:** "sum of consecutive terms" means a contiguous block of
  the sequence, not any subset — 1+4 = 5 is *not* a block sum of (1, 2, 4).

### Step 2 — The honest outcome: not solved, and not faked

- **Plain statement:** the run confirmed the problem is open and did not
  solve it — and backs up, with machine-checked evidence, that it did not
  fabricate a solution.
- **Why it is here:** agent runs on open problems have a known failure mode
  of producing convincing-looking but hollow proofs; the message's central
  claim is that this did not happen.
- **How it works:** the build passes with no `sorry` and standard axioms
  only (8581 kernel-checked jobs). The "cannot just solve it" conclusion was
  cross-checked three independent ways: a literature scan (no known
  technique reaches the result), an independent audit agent that approved
  only the honest partial results, and a formalized impossibility lemma — a
  kernel-checked proof that the simple attack routes cannot work.
- **Concrete anchor:** the impossibility lemma is a real artifact in the
  worktree, not an opinion — it compiles like any theorem.
- **Common trap:** "kernel-checked" does not mean the open problem is
  partially confirmed true. What is verified is the scaffolding the run
  built, not Erdős's statements themselves.

### Step 3 — The deliverable: a reduction to one core

- **Plain statement:** the run collapsed the two open endpoints into one
  precisely-stated missing lemma, with everything around it verified.
- **Why it is here:** this is the run's actual product; without it the run
  would have produced nothing but a status report.
- **How it works:** the run proved in Lean that both the lower and the upper
  endpoint follow from a single unproved "core" — a fine, multi-scale
  statement controlling how the sequence's block sums spread out among the
  integers. Whoever proves the core gets both endpoints for free, with the
  kernel guaranteeing no step in between is wrong. The work is committed at
  `1bc4e29`; the write-up is in the session's Report tab.
- **Concrete anchor:** this is a standard move in mathematics — isolate a
  core that implies the theorem, so later work has one concrete target
  instead of a vague open problem.
- **Common trap:** the impossibility lemma does not say the problem is
  unsolvable — only that specific easy approaches are dead ends.

## Future Directions

- **Prove (or disprove) the multi-scale core** — now the single point of
  attack; both endpoints follow mechanically. `[open problem]`
- **Andrews' precise rate** K·logK/loglogK is stronger than both endpoints;
  Porubský's partial results are the known state of the art. `[open problem]`
- **Compute the sequence far out** to test the conjectured rate
  numerically. `[weekend]`
- **Formalize Porubský's partial results** into the same Lean development,
  extending the verified scaffolding. `[months]`

## Glossary

- **block sum** — a sum of consecutive terms of the sequence.
- **kernel-checked** — verified by Lean's trusted proof-checking core.
- **reduction** — a proof that statement A follows from statement B, so
  proving B settles A.
- **`sorry`** — Lean placeholder that lets an unproved claim compile;
  its absence means no hidden gaps.

## Sources

- The run's exit message — all claims about what the run did.
- https://www.erdosproblems.com/forum/thread/359 — problem identity and open
  status (cross-check; context added from this source).
- https://oeis.org/A002048 — the sequence and MacMahon attribution
  (cross-check).
- Verification status: problem identity, open status, and Andrews'
  conjecture cross-checked against two independent sources; the run's
  internal claims (commit `1bc4e29`, 8581 jobs, audit verdict) are taken
  from the run message and not independently verified.
