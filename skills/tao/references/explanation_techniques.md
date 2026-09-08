# Explanation Techniques

Read this when a step of the material resists plain language. These are the
working techniques behind pass two of the skill.

## Layered depth

Explain every hard idea three times, in order, in the same subsection:

1. **One sentence** — the idea with no notation, as said across a table.
2. **One paragraph** — the mechanism: what goes in, what comes out, what the
   key move is. Minimal notation, each symbol named in words when introduced.
3. **The precise statement** — the actual definition, theorem, equation, or
   code path, now that the reader knows what it is trying to say.

Never start at layer 3. A reader who already has layers 1–2 can skim; a
reader who lacks them cannot recover from a layer-3 opening.

## Analogy discipline

Analogies are load-bearing only if you also state where they break.

- Pick analogies from domains more familiar than the material, not merely
  different from it.
- After the analogy, add one sentence of the form: "the analogy breaks here:
  ..." — an analogy whose limits are unstated becomes a misconception.
- One analogy per concept. Two competing analogies for the same idea confuse
  more than none.

## Concrete anchors

The best anchor is the smallest instance the reader can verify by hand:

- For a theorem: the smallest nontrivial case (n = 2, the one-dimensional
  version, the identity element).
- For an algorithm: a trace on a five-element input, states written out.
- For a system or codebase: one request/datum followed end to end through the
  stages, named files and functions along the way.
- For a statistical result: what the effect size means for one concrete unit
  ("for a single patient, this means ...").

If you cannot produce a small instance, that is a signal you do not yet
understand the step — go back to the material before writing the explanation.

## Misconception handling

For each step ask: *what would a smart newcomer wrongly assume here?* Common
sources:

- A term that has a different everyday meaning ("significant", "efficient",
  "almost surely", "sound").
- A hidden quantifier ("for all" read as "there exists", or the reverse).
- A converse assumed true ("the theorem says A implies B, not B implies A").
- A limit or asymptotic statement read as a statement about small cases.
- A diagram or notation convention specific to this subfield.

State the trap, then why it is wrong, in two sentences. Do not invent traps
to fill the slot — if a step has no plausible misreading, say nothing.

## Prerequisite honesty

When listing prerequisites (pass one), the failure mode is social, not
technical: it feels condescending to list "what a probability distribution
is", so authors skip it and lose the reader silently. Rules:

- List what the *material* assumes, not what you guess the reader knows.
  The `[core]`/`[helpful]` tags let readers self-select.
- A prerequisite explained in one vague sentence ("familiarity with measure
  theory") is not explained. Name the specific facts used ("that a countable
  union of null sets is null").
- If a prerequisite is itself deep, do not recurse forever: explain the
  one-paragraph working version, mark it `[helpful]` to study fully, and
  point at a reference.

## Handling gaps and disputed claims

- If the material asserts something without justification, the report says
  so: "the paper states this without proof; it is plausible because ...".
- If you had to consult sources beyond the material to explain a step, cite
  them in Sources and mark the step "context added from [source]".
- If two parts of the material contradict each other, present both readings
  and flag it — do not silently pick one.

## Tone

Plain language is not casual language. Keep full sentences, keep technical
terms once defined, drop filler ("basically", "simply", "obviously" — if it
were obvious the reader would not be here). "Simple" means every sentence is
checkable by the target reader, not that the content is diluted.
