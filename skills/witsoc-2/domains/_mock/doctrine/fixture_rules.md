# Mock Pack Doctrine

This fixture's doctrine extension. A real pack states the rules its field
actually needs; this one states the minimum that keeps the fixture honest.

## Escalation

`max_consecutive_failures: 3`, with the failure signature defined as the pair
`(failure_class, normalized first line of the checker diagnostic)`.

Three consecutive failures on one frozen claim escalate to Researcher. A repeated
signature escalates immediately — if the checker is saying the same thing twice,
the second attempt did not change anything that mattered.

## Normalization is frozen

`frozen_conditions.normalization` is chosen when the claim is frozen and does
not change afterwards. Switching from `exact_bytes` to `strip_whitespace` after
a failure would redefine what passing means, which is target drift wearing a
convenient disguise.

Likewise `sample_size` for the sampled tier: a failing run may not be rescued by
quietly checking less.

## Tier discipline

The cheap exact tier is attempted before the sampled tier. A pass on the sampled
tier is evidence about **the sample**, not about the artifact — it may reach
`CHECKED_BOUNDED` and no further, with the sample size recorded as its bounds.
That ceiling is declared as `max_status` in `domain.json`, not only stated here:
a ceiling that lives in prose is invisible to the frame and to both checks.

Only the exact tier discharges the refute-attempt gate, because only it cannot
be argued into a pass — and it earns `adversarial: true` by declaring
independent authorship, two-sided evidence, and `adapter/negative_control.txt`,
a known-bad artifact it must reject. Without that control the flag would be a
self-report by the party being checked.

## What this fixture is not

It is not a field, and nothing it verifies is a real result. It exists so the
frame's tests can exercise freeze → produce → verify → receipt → refute-attempt
→ escalate end to end without any field's toolchain, and so a frame change can
be shown not to have grown a hidden dependency on one particular domain.
