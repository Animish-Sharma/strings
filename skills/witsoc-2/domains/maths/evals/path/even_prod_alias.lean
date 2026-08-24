import Mathlib

theorem wit_even_prod (n : ℕ) : 2 ∣ n * (n + 1) := by
  exact Nat.two_dvd_mul_add_one n
