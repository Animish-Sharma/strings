import Mathlib

theorem wit_sqrt2_irrational : Irrational (Real.sqrt 2) := by
  -- WIT [1] SHOW: the square root of two is irrational
  --   uses: -   justification: a numeric decision procedure for irrationality of a square root.
  have step1 : Irrational (Real.sqrt 2) := by
    norm_num

  exact step1
