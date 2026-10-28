# Independent reviews for Fixture2002.Thm_1

Reports are appended in order; the latest block of each kind is the current verdict.

## source-fidelity — 2026-10-28 — 0002-horizon-Fixture2002.STMT.3/source-fidelity-reviewer
Session: 0002-horizon-Fixture2002.STMT.3/source-fidelity-reviewer
Author-session: 0002-horizon-Fixture2002.STMT.3
Status: satisfactory
Verdict: Compared the verbatim `## Statement`, `## Proof`, docstring and Lean type `Fixture2002.add_zero (n : Nat) : n + 0 = n` at ledger commit aab7f9c against Theorem 1 and the Background paragraph of docs/fixtures/Fixture2002.md page 1 and the confirmed `Nat` foundation entry; objects, quantifier, absence of hypotheses, operation, numeral and conclusion agree exactly, `Nat.add_zero` is metadata only, and no deviation is needed; the only finding is a stale derived block in nodes.json (file hash, line count, sorry count, decl_info, local_status) that must be regenerated before locking.

Reviewed revision: aab7f9cec72af59be4a5c57f9d097b0196b17eff (`state(Fixture2002.Thm_1): …`, Archon-Session 0002-horizon-Fixture2002.STMT.3); node file sha256 from nodes.json: e9c57dbc950832c2d7990e71a515a90464b627f066f23c71c57040b8b33bbf70 (stale, see Findings); actual sha256 of HomAlg/Fixture2002/Thm_1.lean at aab7f9c and in the working tree (identical, `hgit status` clean): 9d45518dd35f78cd3bb511094d20d7fa85e9fdce336c3ad2d8532612b021fb37. This verdict binds to the 9d45518d… bytes.

| Source text and location | Current node excerpt | Comparison |
| --- | --- | --- |
| "**Theorem 1.** For every natural number n, n + 0 = n." — docs/fixtures/Fixture2002.md, page 1 (`<!-- page 1 -->`), §1 Addition, line 14 | `## Statement`: "For every natural number n, n + 0 = n." | Exact, character for character after dropping the bold label; no editorial brackets needed. |
| "**Proof.** This is the defining zero equation of addition." — page 1, line 16 | `## Proof`: "This is the defining zero equation of addition." | Exact; no `[uses …]` annotation needed because the proof cites no document item; `deps.proof: []` consistent. |
| "Background. We use the ordinary natural numbers, zero, one, and recursive addition and multiplication. Addition recurses on its second argument; …" — page 1, lines 10–12 | `## Formalization notes`: "ordinary natural numbers and recursive addition … `Nat` and its recursive `+` (recursion on the second argument)" | Agrees; the notes restate the source convention and the confirmed boundary rather than introducing a new one. |
| Document author per literature/Fixture2002/document.yaml: "HomAlgDB acceptance authors"; label "Theorem 1" | Docstring: "**Theorem 1** (HomAlgDB acceptance authors). For every natural number `n`, `n + 0 = n`." | Starts with `**<source.label>** (<author>).` as HomAlg/AGENTS.md requires; restates the statement and the source proof. |

| Source hypothesis or conclusion | Lean expression | Comparison |
| --- | --- | --- |
| Universal quantifier "For every natural number n" | explicit binder `(n : Nat)` in `theorem add_zero (n : Nat) : …` | Same quantifier and domain; explicit argument is the standard rendering of ∀ over `Nat`. No implicit/instance arguments, no extra variables. |
| Hypotheses: none (statement is unconditional) | no hypotheses in the signature; no `variable`, `section` or instance assumptions in the file (file has no imports; namespace `Fixture2002` only) | Agrees; nothing silently added, nothing from the proof route (the "defining zero equation") promoted to the statement. |
| Left side "n + 0": recursive addition applied to n and the numeral zero | `n + 0` elaborated via `instAddNat` → `Nat.add n 0`, `0 : Nat` via `OfNat Nat 0` (`Nat.zero`) | Same operation, same argument order, same numeral; no coercion to another type, no `Nat.zero` vs `0` substitution. |
| Right side "n" | `n` | Identical. |
| Relation "=" | `=` i.e. `Eq (n + 0) n` on `Nat` | Same relation, same polarity, same orientation (`n + 0 = n`, not `n = n + 0`). |
| Conclusion strength | `n + 0 = n`, no weakening (e.g. no `≤`) and no strengthening (e.g. no `∀ m, n + m = …` or two-sided `0 + n = n`) | Exact. |

| Definition used by the statement | Source construction / foundation boundary | Lean meaning |
| --- | --- | --- |
| Natural numbers | Page 1 Background: "ordinary natural numbers"; confirmed foundation entry "Natural numbers and their recursive addition and multiplication", mathlib `Nat`, status confirmed (agent review root-fixture2002-foundation-independent, content_sha256 92cc73b8…) | `Nat` from Lean core Prelude (inductive `zero | succ`), inside the confirmed boundary; not a proxy such as `ℕ+`, `Fin`, or a document-specific structure. |
| Addition `+` | Page 1 Background: "Addition recurses on its second argument"; foundation entry lists `Nat.add_zero` as the recursion's zero equation | `instAddNat` → `Nat.add`, defined in `~/.elan/toolchains/leanprover--lean4---v4.35.0/src/lean/Init/Prelude.lean:1888` as `\| a, Nat.zero => a \| a, Nat.succ b => Nat.succ (Nat.add a b)` — recursion on the second argument, matching the source convention exactly (this is why the source can call `n + 0 = n` "the defining zero equation"). |
| Numeral `0` | Page 1 Background: "zero" | `(0 : Nat)` = `Nat.zero` via `instOfNatNat 0`; inside the boundary. |
| Equality `=` | Ordinary equality of natural numbers (source uses `=` without comment) | `Eq` on `Nat`; no setoid or alternative relation. |
| Mathlib counterpart `Nat.add_zero` | Recorded in the foundation entry as the zero equation of recursive addition | Core `Init/Core.lean:747`: `@[simp] protected theorem Nat.add_zero (n : Nat) : n + 0 = n := rfl` — same type as the node's declaration, so `mathlib.relation: same` is accurate. The node states its own `theorem add_zero … := by sorry` and does not import, alias or `exact` `Nat.add_zero`; the counterpart is metadata only (P-1 respected). |

Findings:
- major (evidence, not fidelity) — The `derived` block for Fixture2002.Thm_1 in literature/Fixture2002/nodes.json at aab7f9c is stale: it records `file.sha256 e9c57dbc…`, `lines: 48`, `sorry_count_text: 0`, `decl_info: []`, `local_status: "planned"`, which are exactly the pre-STMT scaffold at efa1619 (verified: `hgit show efa1619:HomAlg/Fixture2002/Thm_1.lean | sha256sum` = e9c57dbc…, 48 lines). The committed node file is 9d45518d…, 78 lines, contains one named `sorry` and the declaration `Fixture2002.add_zero`. The commit's nodes.json diff only updates the authored fields (`decls`, `mathlib`, `nl_proof_source`, `notes_md`), so the "Built through horizon check" export was not regenerated into the record. The authored fields themselves (`decls: ["Fixture2002.add_zero"]`, `deps` empty, `fidelity.status: faithful`, no deviations, `imports: {mathlib: [], nodes: []}` matching the import-free file) are consistent with the file and the source. Next step: lead re-runs `horizon check HomAlg.Fixture2002.Thm_1` / the export so the derived block reflects 9d45518d…, then runs `homalg review-fidelity` (which refuses planned nodes and rebuilds fresh exports); do not hand-edit nodes.json. This does not change the statement correspondence, which was audited against the actual committed bytes.
- note — The task is STMT, so the single `sorry` in `theorem add_zero` is expected; it is attached to a named theorem with source label and natural-language proof in the docstring, as HomAlg/AGENTS.md requires. The PROOF task should discharge it via the source route (the defining zero equation, i.e. `rfl`/`Nat.add_zero`-level step), which the foundation entry already licenses.
- note — Verbatim `## Statement` and `## Proof` were compared directly against docs/fixtures/Fixture2002.md since the synthetic document has no PDF and no separate page transcription; no transcription review exists to cite, and none is required for a Markdown-only fixture.

Confidence: high.

Author response (0002-horizon-Fixture2002.STMT.3, 2026-10-28): the major evidence finding was resolved by regenerating the compiled export through the shared lock (ledger commit 9ad9d9d, nodes.json only); the node bytes 9d45518d… reviewed above are unchanged.

Author addendum (0002-horizon-Fixture2002.STMT.3, 2026-10-28): `homalg review-fidelity`, executed by the reviewer session above, reserialized the node header into compact YAML when writing the lock, so the file bytes are now sha256 e3f8e604eb47f38fc0b58e32378056dcdecacdf579f10501dfb0ca9636a667ef; prose, declaration and statement hash 1d244f86… are unchanged and `lock_changes` is empty. A separate honesty audit (session 0002-horizon-Fixture2002.STMT.3/honesty-reviewer, recorded in the session report, not as a lock-bearing block) classified the declaration as an honest sorry-backed statement-stage obligation with no overclaim.

## honesty — 2026-10-28 — 0002-horizon-Fixture2002.PROOF.1/honesty-reviewer
Session: 0002-horizon-Fixture2002.PROOF.1/honesty-reviewer
Author-session: 0002-horizon-Fixture2002.PROOF.1
Status: satisfactory
Verdict: PROOF round. Claim class: proved producer. At ledger 1205e85 (`proof(Fixture2002.Thm_1)`, node file sha256 47b0addf7898ed2b506110efdadb69f54c214d78d2d3cf063a4155962cee2e41) the declaration `Fixture2002.add_zero (n : Nat) : n + 0 = n := rfl` was reproduced as: no `sorry`/`admit`/`axiom`/`native_decide`/`unsafe`/`set_option`, no structure or packaged field, not vacuous; `lean_verify` and the compiled export both report `axioms: []`, `direct_sorry: false`, `hollow: false`; `horizon check HomAlg.Fixture2002.Thm_1` (lake build) returncode 0, run after the file's last modification and before the record refresh. Statement lock unchanged: recomputed `statement_sha256 1d244f86…` and exported `type_hash`/`meaning_hash 000000002aea8c3d` equal the header lock; `## Statement`, `## Proof` and the signature bytes are untouched since the STMT lock. Route: the document proof is "the defining zero equation of addition" with no cited item (`deps.proof: []`); `Nat.add` recurses on its second argument with zero clause `| a, .zero => a`, so `rfl` is the literal rendering of that equation, not a bypass or a stronger theorem, and no deviation is warranted. Docstring and Formalization notes describe exactly this; no human approval is stated or implied. Derived record (`local_status: proved`, `sorry_count_text: 0`, file hash, line numbers) matches the bytes; `homalg stage-check Fixture2002.PROOF.1` is `complete: true`.

Findings:
- note (scope) — Commit 1205e85 also writes the generated `literature/Fixture2002/nodes.json` (outside the explicit write set); it is engine-refreshed output matching the file, the same pattern accepted in STMT.3.
- note (consumer) — Thm_1 has no in-document consumer (Thm_2's route uses n * 0 = 0 and 0 + n = n), matching the source; it is an honest leaf producer.
- note (out of scope) — Generated `blueprint/src/content.tex` renders the Thm_2 proof with `\emph` where the source has `*`; belongs to a Thm_2/tooling task (filed in the local inbox by the lead).

Unchecked: the STMT.3 statement correspondence tables and the foundation confirmation content hash were not re-audited. Confidence: high.
