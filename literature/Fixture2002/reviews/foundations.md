# Independent foundation review

Session: root-fixture2002-foundation-independent
Author-session: schema-taxonomy-fixture2002-setup

## source-fidelity — 2026-10-28 root-fixture2002-foundation-independent

Status: satisfactory
Verdict: The sole foundation matches the synthetic source's explicitly stated recursive natural arithmetic; neither target theorem is assumed as a separate source-specific definition.

| Foundation notion | Boundary and evidence |
| --- | --- |
| Natural numbers and their recursive addition and multiplication | Page1 Background explicitly grants Nat and recursive addition/multiplication; Nat.add_zero and Nat.mul_zero/mul_succ are those equations. Nat.zero_add is ordinary elementary arithmetic used in the printed page2 proof. |

The reviewer read the exact Fixture2002.md source and the proposed document.yaml.
Theorem1 is deliberately the defining zero equation, suitable for testing STMT
and PROOF mechanics. Theorem2's required source route expands multiplication by
one and then uses the zero equations; importing Nat.mul_one as a substitute would
bypass that route. No human review is claimed.
