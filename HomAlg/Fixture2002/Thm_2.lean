/-!
```yaml node
{"id": "Fixture2002.Thm_2", "doc": "Fixture2002", "kind": "theorem", "source": {"label": "Theorem 2",
"pages": [2], "chapter": "2"}, "tags": ["basic"], "concepts": {"defines": [], "uses": []}, "deps": {"statement": [],
"proof": []}, "decls": ["Fixture2002.mul_one"], "mathlib": {"relation": "same", "decls": ["Nat.mul_one"],
"note": "The counterpart is recorded only as metadata; the source proof uses the recursive multiplication
equations and zero addition."}, "fidelity": {"status": "faithful", reviewed: {by: "YijunYuan", kind: "agent",
status: "satisfactory", on: "2026-10-28", decl_hashes: {Fixture2002.mul_one: {statement_sha256: "563a3b3cbcee1bcfeeeccb68ce32bed3be064f2e8e2bd882c088d596c7a7fe6d",
type_hash: "0000000050a55181", meaning_hash: "0000000050a55181"}}, session: "0002-horizon-Fixture2002.STMT.4:/root/source_review",
author_session: "0002-horizon-Fixture2002.STMT.4:/root/statement_writer"}}, "title": "Multiplication by
one preserves every natural number."}
```

## Statement

For every natural number n, n * 1 = n.

## Proof

The recursion equation gives n * 1 = n * 0 + n. The zero multiplication equation gives n * 0 = 0, and zero plus n is n.

## Description

Multiplication by one preserves every natural number.
-/

namespace Fixture2002

/-- **Theorem 2** (HomAlgDB acceptance authors). For every natural number n, n * 1 = n.

Source: `docs/fixtures/Fixture2002.md`, page 2.

Proof. The recursion equation gives n * 1 = n * 0 + n. The zero multiplication
equation gives n * 0 = 0, and zero plus n is n.
-/
theorem mul_one (n : Nat) : n * 1 = n := by
  calc
    n * 1 = n * 0 + n := Nat.mul_succ n 0
    _ = 0 + n := congrArg (fun m => m + n) (Nat.mul_zero n)
    _ = n := Nat.zero_add n

end Fixture2002
