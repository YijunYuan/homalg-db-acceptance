# Fixture2002.Thm_2 reviews

## source-fidelity — 2026-10-28 — 0002-horizon-Fixture2002.STMT.4:/root/source_review

Status: satisfactory
Verdict: Theorem 2 has exact source-to-Lean statement correspondence; the explicit sorry is appropriate to the STMT task and does not establish the theorem's proof.
Session: 0002-horizon-Fixture2002.STMT.4:/root/source_review
Author-session: 0002-horizon-Fixture2002.STMT.4:/root/statement_writer
Snapshot: ledger commit 03a52b57ad1a06db77ba43b3dd6f9648da0f42ab; source SHA-256 d0075cefbd6e9ba6d93961b4f51aaa6ebe613c79019170eded4704ffa83214d0; pre-lock Lean SHA-256 79cc43b499d022a201e4ba841df9540fbadff8d66888f46bcb3fadc38969c98c.
Scope: docs/fixtures/Fixture2002.md, pages 1–2; literature/Fixture2002/document.yaml foundations; HomAlg/Fixture2002/Thm_2.lean; graph label Fixture2002.Thm_2.

| Aspect | Source evidence | Lean/header evidence | Comparison |
| --- | --- | --- | --- |
| Objects and domain | Page 1 assumes ordinary natural numbers and recursive arithmetic. | Parameter `(n : Nat)` and ordinary multiplication and numerals. | Exact, within the recorded foundation boundary. |
| Quantifiers and hypotheses | Page 2: every natural number n; no further hypotheses. | `theorem mul_one (n : Nat) : n * 1 = n`. | Exact; no restriction or additional assumption. |
| Conclusion and order | `n * 1 = n`, Theorem 2, chapter 2. | Same equality orientation; source label, page 2, chapter 2 preserved. | Exact. |
| Source proof | Recursion gives `n * 1 = n * 0 + n`, then `n * 0 = 0`, then zero addition. | Header Proof and declaration docstring preserve all three steps. | Exact natural-language route; formal proof deferred. |
| Counterpart boundary | Source states its own theorem. | `Nat.mul_one` occurs only in mathlib metadata; main declaration is `Fixture2002.mul_one`. | No substitution or imported proof shortcut. |

Findings:
- [note][fidelity] No statement deviation or proxy construction found; the source sentence, node Statement, graph statement, and Lean signature agree.
- [note][hypothesis] The statement has no theorem-valued premise, positivity restriction, or extra algebraic structure; zero remains included.
- [note][fidelity] The named theorem intentionally uses `by sorry`; this review approves statement fidelity only. The future PROOF task must discharge the recorded recursion route.
- [note][attachment] The graph source anchor is Fixture2002:page-0002; its cached `lean_status=empty` predates the new declaration and is not proof-completion evidence.

Unchecked: No kernel/build certification, transitive axiom audit, or final graph regeneration is claimed by this source-fidelity lane.
Confidence: high.

## honesty — 2026-10-28 — 0002-horizon-Fixture2002.STMT.4:/root/honesty_review

Status: satisfactory
Verdict: honest — axiom/sorry-backed statement, appropriate for STMT only.
Session: 0002-horizon-Fixture2002.STMT.4:/root/honesty_review
Author-session: 0002-horizon-Fixture2002.STMT.4:/root/statement_writer
Snapshot: ledger commit `03a52b57ad1a06db77ba43b3dd6f9648da0f42ab`.
Scope: `Fixture2002.Thm_2`, `Fixture2002.mul_one`, source pages 1–2, task objective, root import, exported declaration evidence and graph status.

| Obligation | Observed artifact | Assessment |
|---|---|---|
| Every natural number `n` satisfies `n * 1 = n` | `Fixture2002.mul_one (n : Nat) : n * 1 = n` | Exact domain and conclusion; no additional premise |
| Preserve source proof for later formalization | Declaration docstring contains recursion, multiplication by zero, and zero addition | Proof route retained |
| STMT retains a named `sorry` | Sole theorem body is `by sorry` | Explicit, task-required remaining obligation |
| Avoid substitution by an imported counterpart | `Nat.mul_one` occurs only in metadata | No theorem alias or imported proof |
| Distinguish compilation from proof | LSP axiom check reports `[sorryAx]`, trust `incomplete`; export reports `local_status: stated` | Must not claim proof completion |
| Reachability and intended use | `HomAlg/Fixture2002.lean` imports this node | Root-reachable; separate PROOF work must fill this theorem body |

Inputs/checks:

- Inspected the recorded `horizon check HomAlg.Fixture2002.Thm_2` result: passed, return code `0`, finished `2026-10-28T05:08:38.045006+00:00`.
- Independently ran `lean_verify` on `Fixture2002.mul_one`: axioms and nonstandard axioms both `[sorryAx]`; trust `incomplete`.
- Manual source scan found one `sorry` at line 65 and no `admit`, custom `axiom`, `unsafe`, or `native_decide`.
- Exported source SHA-256 matches the reviewed file: `79cc43b499d022a201e4ba841df9540fbadff8d66888f46bcb3fadc38969c98c`.
- Source SHA-256: `d0075cefbd6e9ba6d93961b4f51aaa6ebe613c79019170eded4704ffa83214d0`.

Findings:

- **[note][evidence]** `HomAlg/Fixture2002/Thm_2.lean:64`: the theorem is axiom/sorry-backed. This is satisfactory for the explicit STMT objective; the mathematical proof remains pending.
- **[note][packaging][vacuity]** The declaration has only the source variable `n : Nat`. No target-shaped premise, wrapper, empty domain, auxiliary certificate, or hidden assumption was introduced.
- **[note][loop]** The ledger moves from an empty namespace to the named source statement in one authored commit. There is no repeated wrapper or re-expression cycle.
- **[minor][scope]** Current generated `blueprint/src/content.tex:22` renders the first multiplication equation as `n \emph{ 1 = n } 0 + n`. The Lean header and docstring preserve the arithmetic correctly. This is an out-of-scope rendering issue to record locally, not repair by editing generated output.
- **[note][evidence]** The graph still reports `lean_status=empty`, whereas the current compiled export reports `stated`. No source-facing `\leanok` claim was observed; graph status alone is not current declaration evidence.

Frontier before/after: empty `Fixture2002.Thm_2` declaration → faithfully stated `Fixture2002.mul_one`; its proof remains the first unmet mathematical producer.

Unchecked: final fidelity lock and `homalg stage-check Fixture2002.STMT.4` have not been certified by this pass. No substantive downstream theorem consumer exists in this chapter; root import is accessibility evidence only. No accepted files were edited.

Confidence: high for the scoped STMT-versus-PROOF distinction.

## honesty — 2026-10-28 — 0002-horizon-Fixture2002.STMT.4:/root/source_review

Status: satisfactory
Verdict: Independently confirmed axiom/sorry-backed statement suitable for STMT completion only; the mathematical producer remains unproved.
Session: 0002-horizon-Fixture2002.STMT.4:/root/source_review
Author-session: 0002-horizon-Fixture2002.STMT.4:/root/statement_writer
Snapshot: ledger commit 03a52b57ad1a06db77ba43b3dd6f9648da0f42ab; pre-lock Lean SHA-256 79cc43b499d022a201e4ba841df9540fbadff8d66888f46bcb3fadc38969c98c.
Scope: Independent narrow honesty audit after considering the separate /root/honesty_review report; theorem body, compiled export, cached target check, transitive axiom query, root import, graph and generated source rendering.

| Claim or risk | Independently inspected evidence | Assessment |
| --- | --- | --- |
| Faithful generality without hidden premise | The only parameter is `n : Nat`; conclusion is `n * 1 = n`. | No hypothesis packaging, proxy, or vacuous domain. |
| Statement versus proof | Fresh `lean_verify` returns axioms `[sorryAx]`, nonstandard axioms `[sorryAx]`, trust `incomplete`. | Explicitly axiom/sorry-backed; proof completion is not claimed. |
| Current compiled status | Export has `direct_sorry: true`, `local_status: stated`, and source SHA matching the reviewed file. | STMT evidence is current; no proved producer exists yet. |
| Target compilation | Horizon cache records `HomAlg.Fixture2002.Thm_2`, passed, return code 0, finished 2026-10-28T05:08:38.045006+00:00. | Compilation checked separately from mathematical closure. |
| Reachability and consumer boundary | `HomAlg/Fixture2002.lean` imports the node; scoped source search found no downstream use of `Fixture2002.mul_one`. | Root-reachable; the intended next consumer is its PROOF task, not an already proved theorem. |
| Generated evidence | Graph reports cached `empty`; blueprint proof renders multiplication symbols as emphasis. | Neither generated artifact is used as current proof evidence. |

Findings:
- [note][honesty] The named theorem visibly retains exactly one required `sorry`; no wrapper, custom axiom, or theorem-valued input conceals the remaining proof obligation.
- [note][evidence] Independent axiom inspection confirms the earlier honesty review's trust classification. An initial LSP diagnostic initialization timed out; the subsequent axiom verification succeeded.
- [note][loop] Author commit adds the formerly absent source statement without moving its mathematical obligation into another declaration.
- [minor][evidence] `blueprint/src/content.tex:22` contains `n \\emph{ 1 = n } 0 + n` instead of the multiplication equation. The authored header/docstring remain correct; this pre-existing generated rendering issue needs an infrastructure fix outside this task's write scope.

Frontier before/after: empty Fixture2002.Thm_2 namespace → exact named statement Fixture2002.mul_one with required sorry; its recursion proof remains the first unmet mathematical producer.
Unchecked: No proof-completion, final fidelity-lock, stage-check, or global repository acceptance claim is certified here. No authored source or review files were edited by this reviewer.
Confidence: high for the scoped STMT honesty conclusion.

## Verification closeout — 2026-10-28

Session: 0002-horizon-Fixture2002.STMT.4 (lead; this records checks, not another independent verdict).

- The actual source reviewer ran the guarded fidelity command successfully using the distinct author/reviewer sessions above. Post-lock LSP diagnostics contain only the intended `sorry` warning. Final Lean SHA-256: `88b42c149639604aa9476da88324e34e7659f7c0a8af817c2e4658a097f139cd`.
- `homalg stage-check Fixture2002.STMT.4` passed with no findings; the task was set to done. Generated graph refresh now attaches `Fixture2002.mul_one` and reports `lean_status=sorry`, resolving the earlier stale graph-status notes. The source recursion proof remains pending.
- `make site` passed. `make test` failed with 10 failed, 337 passed, and 16 skipped; frontend test steps were not reached. Fixture/golden isolation, source-heading parsing, review-policy context, and ancestor-Git test issues are recorded in local inbox I-0001. The generated arithmetic rendering issue remains in I-0002.
- `make validate` failed on `nodes-json-fresh`, with 15 context-dependent checks skipped and its Lean regression phase not reached. Document-only and global exports print the same type using `Nat` and `ℕ`, respectively, changing the derived text hash; kernel type/meaning hashes agree. This exporter issue is outside the task write scope and is recorded in the local inbox. Generated JSON is excluded from the scoped authored commits.

Claim class: axiom/sorry-backed. Honesty-reviewer: used. No proof-completion or whole-repository acceptance is claimed.

## honesty — 2026-10-28 — 0002-horizon-Fixture2002.PROOF.2:/root/honesty_review

Status: satisfactory
Verdict: honest — proved producer for the exact chapter-2 theorem.
Session: 0002-horizon-Fixture2002.PROOF.2:/root/honesty_review
Author-session: 0002-horizon-Fixture2002.PROOF.2:/root
Snapshot: ledger `eb4d21845ea0a89862c9960444ce0bf94fedc395`; Lean SHA-256 `617e2cc127f05b1b2e5339d1db10f894796f4d787c1d433a14a61aeaeeb4ced3`.
Scope: `Fixture2002.Thm_2`, `Fixture2002.mul_one`, source pages 1–2, proof diff, axiom evidence, compiled dependencies and root reachability.

| Source obligation | Lean evidence | Assessment |
| --- | --- | --- |
| Every natural number satisfies `n * 1 = n` | Unchanged `mul_one (n : Nat) : n * 1 = n` | Exact domain, quantifier and conclusion; no extra premise |
| Expand multiplication by one | `Nat.mul_succ n 0` | Source recursion step |
| Replace multiplication by zero | `congrArg (fun m => m + n) (Nat.mul_zero n)` | Source zero-equation step |
| Simplify zero addition | `Nat.zero_add n` | Source final step |
| Preserve source construction | Compiled value dependencies contain the three arithmetic lemmas and omit `Nat.mul_one` | Counterpart remains metadata only |

Inputs/checks:

- Independently ran `lean_verify`: axioms `[]`, nonstandard axioms `[]`, source warnings `[]`.
- Independently obtained complete LSP diagnostics: success, no diagnostics or failed dependencies.
- Inspected the recorded `horizon check HomAlg.Fixture2002.Thm_2`: passed, return code `0`, finished `2026-10-28T05:25:29.557073+00:00`; no duplicate build was launched.
- Inspected document export: `direct_sorry: false`, `transitive_sorry: false`, `hollow: false`, no packaged fields, and unchanged type/meaning hashes `0000000050a55181`.
- Confirmed root reachability through `HomAlg.lean` → `HomAlg/Fixture2002.lean` → the theorem module.

Findings:

- **[note][packaging][vacuity]** `HomAlg/Fixture2002/Thm_2.lean:36`: the only input is an arbitrary natural number. No wrapper, hidden hypothesis, empty domain or assumed conclusion was introduced.
- **[note][loop]** The committed change removes the sole named `sorry` by implementing the three source steps. The source obligation is discharged rather than relocated.
- **[note][evidence]** During this review, the graph still reported cached `lean_status=sorry`. Current declaration and compiled-export evidence establish proof closure; refresh generated graph status before citing it as current.

Frontier before/after: `Fixture2002.Thm_2` with its recursion proof unmet → the same theorem proved with no remaining producer in this task's scope.

Consumer: this theorem is the chapter's terminal source result. Root imports establish accessibility; no substantive downstream theorem consumer was found or claimed.

Unchecked: final `stage-check`, repository-wide tests/validation/site results, and final graph regeneration belong to the lead's closeout. Existing I-0001/I-0002/I-0003 remain outside this review's repair scope. No files or task state were changed.

Confidence: high for the scoped proof-completion and source-route assessment.

## Proof verification closeout — 2026-10-28

Session: 0002-horizon-Fixture2002.PROOF.2:/root (lead; check record, not an independent verdict).

- The only Lean edit replaces the named `sorry` with the source calculation. The statement, authored dependencies, foundation boundary and existing statement lock remain unchanged. No auxiliary nodes were introduced, so no auxiliary pruning was needed.
- `horizon check HomAlg.Fixture2002.Thm_2` passed with exit code 0. Both lead and independent reviewer obtained complete, empty LSP diagnostics and transitive axiom lists `[]`.
- `homalg stage-check Fixture2002.PROOF.2 --json` passed with exit code 0, `complete: true`, and no findings. The task is done; the broader PROOF roadmap remains active because chapter 1 is outside this task.
- Generated blueprint/graph refresh resolves the reviewer's cached-status note: `Fixture2002.Thm_2` now has `lean_status=lean_ok`. Current document evidence reports `proof-complete`, `reopened: false`, no blockers and no dependency mismatch. The remaining document frontier is the out-of-scope `Fixture2002.Thm_1`.
- `make site` passed. `make test` exited 2: 11 failed, 336 passed, 16 skipped; frontend tests were not reached. In addition to the previously recorded fixture-isolation failures, the benchmark's `template_index` includes Fixture2002 without its raw declaration export. Updated evidence is recorded in I-0001. ESLint and Starlette/httpx deprecation notices remain tracked there.
- `make validate` exited 2 on `nodes-json-fresh`; 15 context-dependent checks were skipped and the Lean regression phase was not reached. Document/global exports still print `Nat`/`ℕ` differently while both type/meaning hashes are `0000000050a55181` and both axiom lists are empty. I-0003 remains open for an infrastructure repair. The generated multiplication-rendering issue I-0002 also remains open.
- Reviewed the task's roadmap/inbox references and open inbox; there are no active protections or unread conversations, and none of the three tooling issues is resolved by this proof. Scratch cleanup found no stale candidates. All authored changes are limited to the scoped theorem and this review file. Finalization also records the generated `nodes.json` proof evidence under the explicit document-export exemption in `tools/homalg/scope.py`; its diff contains only the verified derived status, dependencies and file hash.

Claim class: proved producer. Frontier before/after: `Fixture2002.Thm_2` with one named `sorry` → the exact source theorem proved, with no unmet producer in this task. Consumer: terminal chapter-2 result, accessible through the project root; no downstream theorem consumer is claimed. Honesty-reviewer: used. Whole-repository acceptance remains pending the recorded tooling issues.
