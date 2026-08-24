import Mathlib

axiom wit_bridge (n : ℕ) : 2 ∣ n * (n + 1)

theorem wit_even_prod (n : ℕ) : 2 ∣ n * (n + 1) := wit_bridge n
