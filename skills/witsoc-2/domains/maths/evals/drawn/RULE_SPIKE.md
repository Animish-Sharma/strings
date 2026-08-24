# What separates a proof from a citation

`allowed_external_facts` constrained the PLAN and nothing else. A tactic pulled
in whatever it liked, the premise audit reported "0 citations", and a campaign
was admitted whose entire mathematical content was one library lemma the claim
never authorised.

Refusing that needs a rule. The rule was not obvious, so it was not chosen by
argument. `rule_spike.py` scores candidates against labelled data: the 40-target
drawn batch, where 23 closings were shown to cite their target and 16 were shown
not to, plus two hand-labelled campaign artifacts — an honest induction and a
`norm_num` call that looked identical to every gate.

## Scores

| rule | caught (of 23) | honest proofs destroyed (of 16) |
|---|---|---|
| a. head constant has the target's type | 15 | 0 |
| b. any used constant has the target's type | 0 | 0 |
| c. term under 25 identifiers | 9 | 5 |
| d. one library dependency or fewer | 0 | 0 |
| e. uses a result CONCLUDING what the target concludes | 1 | 1 |
| a or e | 16 | 1 |

Read those numbers carefully, because the interesting one looks like the worst.

**(c) and (d) are out.** Size is not a signal: five honest proofs are as short as
the citations, because `rfl` on a definitional lemma is both short and real.

**(b) scores zero by construction, not by failure.** It looks for an ALIAS —
some other declaration with the target's exact type — and this sample contains
none. It is kept because Q1 found one in the wild: `exact?` closed
`2 ∣ n * (n+1)` with `Nat.two_dvd_mul_add_one`, a different name for the same
statement, which the forbidden-name list did not contain.

**(e) scoring 1/23 is the point, not a defect.** All 23 batch citations name
their target directly and are already caught by the name check. (e) is the net
for the case that check cannot see: a proof that cites something STRICTLY MORE
GENERAL than the target. It fired on exactly one case here — the campaign
artifact — and named `Tactic.NormNum.irrational_sqrt_nat`, which is precisely
the lemma that carried that claim. It did not fire on the honest induction.

Its one hit among the "proofs" is `disjoint_compl_right`, closed by `exact?`
using `Disjoint.symm` and `disjoint_compl_left`. That is a sibling result handed
the goal, and calling it a proof was an artifact of labelling by the name check.
Under the adopted rule it passes the moment the claim declares it — which is the
entire mechanism working as intended.

## Adopted

FAIL when any of:

1. the proof term names the target, under any namespace abbreviation, including
   inside a `._proof_` auxiliary *(existing)*;
2. it uses a declaration whose corpus TYPE equals the target's *(alias)*;
3. its head constant has the target's type;
4. it uses a result whose CONCLUSION is headed by the same symbol as the
   target's, and that result is not in `allowed_external_facts`.

Rule 4 is what turns the allowlist from documentation into a check. Every run
also reports `library_dependencies` into the receipt, so what a proof leaned on
is auditable even where no rule fires.

## Burden, measured on 186 proofs nobody here wrote

The spike chose the rules. It did not answer the question that decides whether
rule 4 can be ON by default, which is not precision but BURDEN: **how often does
it fire on an honest proof?** `rule_burden.py` answers that against the library's
own proofs — 200 drawn with a different seed from the tuning set, each rebuilt in
its own scope carrying the proof its author wrote, audited with an EMPTY
allowlist, which is the harshest setting there is.

```
sampled                200
audited                186     (14 produced no readable term)
rule 4 fired            61     32.8% of honest proofs
declaring clears it     60     98.4% of those
constants to declare     1     median (max 3)
```

**One proof in three would be asked to declare something, and naming it clears
the gate 98% of the time.** That is a workflow, not noise: the gate says which
constant, and there is a median of one. It is also not free, and a claim author
who wants none of it can leave rule 4 unarmed by declaring nothing that
concludes what the target concludes — the rule only fires when the proof reaches
for a result of the target's own shape.

The one case where declaring did not clear it is `Finset.uIcc_eq_union`, whose
proof leans on `Set.uIcc_eq_union`: declaring the constant the gate names is not
enough when the term reaches it under a second name.

### What this number is not

It over-reports, by about 2%. Four of 186 proofs came back citing THEMSELVES,
which no library proof can do. The cause is the measurement, not the gate: the
probe imports the target's own module, so `simp` can reach the very theorem
being proved — something the library's own build cannot do, because at that
point the theorem does not exist yet. The gate reads the term correctly; the
term it was given is not the one Mathlib elaborated.

Two earlier readings of this measurement were wrong and were fixed by taking
it. Printing abbreviated names let a use of `Multiset.mem_map` under `open
Multiset` be read as a use of `Finset.mem_map` — six false self-citations, fixed
by printing full names. And when a declaration's block could not be isolated,
the audit scanned the WHOLE of the toolchain's output and read names out of
diagnostics — five more, fixed by refusing to report on a term that was never
read. Both had been described in comments as erring in the safe direction. They
were not. They were fabricating findings, and only volume showed it.

## What this does not do

It does not decide whether a proof is *good*. A claim that declares the one
lemma carrying it passes rule 4 and should — the claim is then honest about
resting on that lemma, which is all the gate was ever able to ask.

Two of 39 targets resolve no conclusion head at all, and for those rule 4 is
silent. That is a gap, and it is reported rather than papered over.

Reproduce:

```bash
python3 rule_spike.py --targets batch40.json --results batch40_results.json \
    --extra extra_cases.json --out rule_features.json
python3 rule_spike.py --score rule_features.json
```
