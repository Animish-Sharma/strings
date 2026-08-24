import Mathlib

theorem wit_even_prod (n : ℕ) : 2 ∣ n * (n + 1) := by
  -- WIT [1] HAVE: if two divides k times k plus one then two divides k plus one times k plus two
  --   uses: -   justification: expanding the product and peeling off a multiple of two.
  have step1 : ∀ k : ℕ, 2 ∣ k * (k + 1) → 2 ∣ (k + 1) * (k + 1 + 1) := by
    intro k ih
    obtain ⟨m, hm⟩ := ih
    exact ⟨m + k + 1, by rw [show (k+1) * (k+1+1) = k * (k+1) + 2*(k+1) by ring, hm]; ring⟩

  -- WIT [2] SHOW: for every natural number n, the product n times n plus one is divisible by two
  --   uses: [1]   justification: [1], induction on n, base by evaluation and step by the lemma above.
  have step2 : 2 ∣ n * (n + 1) := by
    induction n with
    | zero => simp
    | succ k ih => exact step1 k ih

  exact step2
