Prove chapter {chapter} of {doc_title} ({doc_key}) along the document's route (P-2).

Nodes: {node_list}. Write scope: {write_scope}.
Read comments first, then use horizon graph -p HomAlg frontier --type tex to
prioritize ready nodes that unlock later work. Preserve every locked statement
(P-1); use the source Proof and declared dependencies. Additional local helpers
must be Aux_/Bridge_ children of scoped parents, created through homalg new-node.
Build only via horizon check. Prune unused auxiliaries through homalg prune-check.

For every node worked on but unfinished in this session, add a comment beginning
attempt: describing the approach, failure and next obstacle. Distinct sessions
count as separate attempts; duplicate comments do not. Suspected source proof
errors require homalg dispute open --kind proof and a local question for the
owner when the mathematical/source disagreement remains unresolved. Explained
formalization deviations follow the independent review policy in
docs/REVIEW_POLICY.md; do not request routine human review when that policy
authorizes an actual independent agent review. Never silently replace the route
or fabricate a human dispute decision. Do not send GitHub issues.
Review any changed statements before relocking. Never fabricate human approvals,
hide sorry in anonymous examples, or package the desired conclusion as a hypothesis.

Done when homalg stage-check {task_id} exits 0. Then set this task to done.
