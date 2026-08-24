-- Modus ponens. No imports: this is a statement about the primitive function
-- type of the logic, so anything imported here would be evidence the encoding
-- had drifted from the frozen target.

theorem wit_modus_ponens (P Q : Prop) (hPQ : P → Q) (hP : P) : Q :=
  hPQ hP
