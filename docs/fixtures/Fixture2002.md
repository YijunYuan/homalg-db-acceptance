# Two elementary arithmetic identities

This is a project-authored synthetic source for cold-start acceptance. It is not
part of the golden regression documents and makes no historical claims.

<!-- page 1 -->

## 1. Addition

Background. We use the ordinary natural numbers, zero, one, and recursive
addition and multiplication. Addition recurses on its second argument;
multiplication satisfies n * 0 = 0 and n * (m + 1) = n * m + n.

**Theorem 1.** For every natural number n, n + 0 = n.

**Proof.** This is the defining zero equation of addition.

<!-- page 2 -->

## 2. Multiplication

**Theorem 2.** For every natural number n, n * 1 = n.

**Proof.** The recursion equation gives n * 1 = n * 0 + n. The zero
multiplication equation gives n * 0 = 0, and zero plus n is n.
