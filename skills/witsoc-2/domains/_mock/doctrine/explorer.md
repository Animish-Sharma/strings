# Mock pack — explorer doctrine

## Freezing a target here

The frozen claim carries `expected_value` and a `frozen_conditions.normalization`
naming how content is compared. Freeze the normalization: changing it after a
failure silently redefines what passing means, and that is the move this fixture
exists to demonstrate a pack can prevent.

## Tier selection

`exact` is adversarial and reaches VERIFIED; `sampled` is not and caps at
CHECKED_BOUNDED. Pick the cheapest tier that can reach the status the claim
needs, which for anything intended to be admitted means `exact`.

## Arbitrating

A `sampled` pass is evidence about the sample. It is never evidence about the
whole, and the receipt says so.
