/-!
```yaml node
{"id": "Fixture2002.Thm_1", "doc": "Fixture2002", "kind": "theorem", "source": {"label": "Theorem 1",
"pages": [1], "chapter": "1"}, "tags": ["basic"], "concepts": {"defines": [], "uses": []}, "deps": {"statement": [],
"proof": []}, "decls": ["Fixture2002.add_zero"], "mathlib": {"relation": "same", "decls": ["Nat.add_zero"]},
"fidelity": {"status": "faithful", reviewed: {by: "YijunYuan", kind: "agent", status: "satisfactory",
on: "2026-10-28", decl_hashes: {Fixture2002.add_zero: {statement_sha256: "1d244f86942aed22ee2e3041150eeef8ff6fd1addb3f22a260469d46ea80b157",
type_hash: "000000002aea8c3d", meaning_hash: "000000002aea8c3d"}}, session: "0002-horizon-Fixture2002.STMT.3/source-fidelity-reviewer",
author_session: "0002-horizon-Fixture2002.STMT.3"}}, "nl_proof_source": {"follows": "document"}, "title": "Addition
by zero preserves every natural number."}
```

## Statement

For every natural number n, n + 0 = n.

## Proof

This is the defining zero equation of addition.

## Description

Addition by zero preserves every natural number.

## Formalization notes

The source works with the ordinary natural numbers and recursive addition, which
the document's confirmed foundation boundary identifies with `Nat` and its
recursive `+` (recursion on the second argument). The dictionary is: "natural
number n" is `n : Nat`; "n + 0" is `n + 0` with the `Nat` addition and the
numeral `0 : Nat`; the universal quantifier is the explicit argument `n`. The
Mathlib/core counterpart `Nat.add_zero` has the same statement and is recorded
under `mathlib`; it is not used as the statement. The proof follows the source
route: "the defining zero equation of addition" is the zero-case recursion equation
of `Nat.add` (`n + 0` unfolds to `n`), so the identity holds by `rfl`. No lemma
is invoked, matching the document's proof, which cites no other item.
-/

namespace Fixture2002

/-- **Theorem 1** (HomAlgDB acceptance authors). For every natural number `n`,
`n + 0 = n`.

Source proof: this is the defining zero equation of addition. Formally, `n + 0`
reduces to `n` by the zero equation of the recursive `Nat.add`, so `rfl` closes
the goal. -/
theorem add_zero (n : Nat) : n + 0 = n :=
  rfl

end Fixture2002
