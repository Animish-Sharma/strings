# Frame friction log — building the archival pack

This pack was written under one rule: **do not change the frame**. Every time I
wanted to, I wrote it down instead. That list is the point of the exercise. The
contract had only ever been implemented by the person who wrote it, against two
fields chosen because they suited it; a third field, picked because it does
*not* suit it, is the cheapest test available of whether the contract is a
contract or a description of two packs.

The rule held. **No frame file was modified while building this pack.**

Two bugs were found and fixed pack-side, one of them in another pack — which is
the other thing a third implementation buys.

---

## 1. Word-boundary matching forces plural enumeration

**Wanted:** suffix folding in `scripts/resolve_domain.py`.

`chronicles` does not match the signal `chronicle`, so four of this pack's own
examples resolved to NO_MATCH until every plural was listed by hand. The bio pack
hit the same thing and worked around it the same way, which makes this the second
independent occurrence.

**Workaround:** list both forms. Thirty-odd extra strings.

**Cost of not fixing it:** the failure is silent and asymmetric. A missing plural
does not error — the pack simply never gets selected for a problem it owns, and
the run proceeds under no doctrine at all. `--self-test` catches it only for the
examples someone thought to write down.

**Verdict:** a real defect in the frame, cheaply fixable, now witnessed twice.
Fold `-s`, `-es`, `-ies` and re-run every pack's self-test.

---

## 2. `availability_check` presumes an external dependency

**Wanted:** a way to say "this tier is always available; the question is whether
the artifact gives it anything to work on".

In a formal domain availability means a toolchain; in an empirical one, data.
Here it means neither — everything is standard library and the evidence is inside
the artifact. Writing an `availability.py` that answers a different question than
the field asks felt like filling in a form.

**Workaround:** the probe reports on the dossier, and says so plainly. It refuses
`triangulation` for a dossier with fewer than two supporting sources, on the
grounds that the answer is known in advance and running it would dress that up as
a finding.

**Verdict:** mild. The workaround is arguably better than what the contract asked
for, which is usually a sign the contract asked the wrong question rather than
that it asked too much.

---

## 3. `cost_hint` measures the wrong thing

**Wanted:** a cost model that is not about compute.

The enum is `cheap | moderate | expensive`, and everything in this pack is
microseconds. But the real cost of the triangulation tier is not the graph walk —
it is obtaining the manuscripts to build the graph from, which can be travel,
permissions, and months. A pack that declares `moderate` because its Python is
fast tells Explorer something actively misleading about what a campaign will
cost.

**Workaround:** none available. I declared compute cost and this paragraph is the
correction.

**Verdict:** a real gap in the economics model. `cost_hint` conflates *machine
cost* with *cost of the evidence*, and in fields where the second dominates it
guides tier selection in the wrong direction. This is the friction item I would
fix first.

---

## 4. `corpus` has no analogue here

**Wanted:** Explorer's retrieval requirement to have a mechanism in a field with
no standing index.

The frame requires Explorer to retrieve against a domain corpus. In mathematics
that is a library of results; in biology, a source ledger. Here the sources *are*
the artifact — there is no index to retrieve from, only archives to search, and
the search is a physical act.

**Workaround:** the contract makes `corpus` optional, so I omitted it, and
Explorer's doctrine says retrieval is manual and its record is the
`archive_coverage` field. That record does real work: an unrecorded search cannot
be told apart from one nobody ran, and the difference decides what an absence
means.

**Verdict:** the optionality saved it. But an Explorer doctrine requirement with
no mechanism in a registered field is a rule that is true in two packs out of
three, and the frame should say which.

---

## 5. `completeness.all_obligations_covered` presumes a proof

**Wanted:** a field name that is not from formal mathematics.

"Obligations" is a proof-assistant notion. Both this pack and bio reinterpret it
as "every blocking gate returned a verdict", which is a reasonable reading and is
not what the word means.

**Workaround:** reinterpret, consistently, and document it here.

**Verdict:** cosmetic, and worth recording anyway — it is the founding domain
leaking into frame vocabulary, which is precisely what the purity check exists to
catch and cannot, because the leak is in a field name rather than a term the
check knows.

---

## What did not creak

Worth recording, because a friction log that only lists complaints reads as
though nothing worked.

- **The six contract items fit.** Nothing about this field wanted a seventh, and
  nothing had to be forced into an existing one.
- **`adversarial` separate from `max_status`** fit exactly. The cascade collapse
  genuinely cannot be talked into a false pass, and it genuinely tops out below
  `VERIFIED`. Conflating them would have made this pack unrepresentable.
- **The refute-attempt gate fit better here than anywhere.** In this field the
  refutation IS the verification, read the other way round: the same computation
  that counts independent origins is the thing that can destroy the claim's
  support. Nothing had to be invented to satisfy the requirement.
- **The ceiling machinery worked unmodified** on a pack whose honest maximum is
  `CHECKED_BOUNDED`, including through the reducer.
- **The escalation signature rule** transferred without change, including the
  freedom to set a different threshold with a stated reason (three here, not
  bio's two, because an attempt in this field can legitimately bring a new source
  and so is not the same attempt repeated).
- **The status refinements** expressed the field's central distinction —
  documented versus attested — with no frame support beyond what already existed.

---

## Bugs found, both pack-side

**A negation bug in the scope-language gate, in TWO packs.** Term matching fired
on words inside a disclaimer: "nothing here speaks to how typical this was"
failed on `typical`. This is the worst direction for the check to be wrong in —
it failed the honest sentence while passing the evasive one. Found because this
pack's good fixture wrote its bounds explicitly. Fixed here and in `bio`, which
had carried it since it was written and had no fixture that could expose it.

**A wrong fixture, caught by the adapter.** My first cascade control was not a
cascade: one of its sources had a second parent, so it collapsed to two origins
and passed correctly. The self-test failed, and it was the fixture that was
wrong, not the code.
