Formalize the cited results used in {doc_title} ({doc_key}).

Nodes: {node_list}. Write scope: {write_scope}.
Read comments and the exact source references. State every cited result faithfully,
with full cited.source metadata; use editorial formulations only when explicitly
marked. Keep each unresolved proof as a named theorem with its source and natural
language proof in the docstring. Attempt a proof and record failures as node comments;
Mathlib reuse is permitted for cited proofs. Never conceal remaining assumptions.
Dispatch source-fidelity-reviewer and honesty-reviewer when appropriate. Append
five-level reviews with Verdict and comparison tables under literature/{doc_key}/reviews/.
After satisfactory reviews, the actual independent reviewer runs
homalg review-fidelity <NodeId> --by {login} --session REVIEW_SESSION
--author-session AUTHOR_SESSION. Record distinct actual author and reviewer
executions, following docs/REVIEW_POLICY.md. The author must not self-review or
invent an independent verdict. Never write a human review or confirmation.
Build only through horizon check. Do not send public messages during the run.

Done when homalg stage-check {task_id} exits 0. Then set this task to done.
