"""Classification ordering and owner-approval rules independent of GitHub state."""

import pytest

from homalg.classify import (
    append_only,
    approval_reasons,
    classify_changed,
    document_keys,
    owner_approved,
)


@pytest.mark.parametrize(
    ("paths", "labels", "existing", "kind", "lean"),
    [
        (["literature/Example2000/claim.yaml"], [], [], "claim", False),
        (["literature/Example2000/document.yaml"], [], [], "register", False),
        (["literature/Example2000/document.yaml"], [], ["Example2000"], "formalization", True),
        (["HomAlg/Fixture2000/Def_1.lean"], [], [], "infra", True),
        (["HomAlg/Fixture2001/Thm_1.lean"], [], [], "infra", True),
        (["HomAlg/Fixture2002/Thm_1.lean"], [], ["Fixture2002"], "formalization", True),
        (["literature/Fixture2002/document.yaml"], [], [], "register", False),
        (["literature/Fixture2002/claim.yaml"], [], ["Fixture2002"], "claim", False),
        (["docs/CI.md"], [], [], "infra", False),
        (
            ["literature/Example2000/claim.yaml", "literature/Example2001/claim.yaml"],
            [],
            [],
            "multi-doc",
            True,
        ),
        (["literature/Example2000/claim.yaml"], ["mathlib-bump"], [], "mathlib-bump", True),
        (["lean-toolchain"], [], [], "mathlib-bump", True),
    ],
)
def test_classification_order(
    paths: list[str], labels: list[str], existing: list[str], kind: str, lean: bool
) -> None:
    """Classification follows the specified priority rather than arbitrary kind labels."""
    result = classify_changed(paths, labels, existing_documents=existing)
    assert result["kind"] == kind and result["needs_lean"] is lean


def test_status_branch_cannot_be_merged() -> None:
    """Progress-only branches must never become document PRs."""
    with pytest.raises(ValueError, match="not merged"):
        classify_changed(["status.json"], head_branch="status/Example2000")


def test_only_versioned_baseline_fixtures_are_infrastructure() -> None:
    """A Fixture prefix cannot hide a new document from collaboration policy."""
    paths = [f"literature/Fixture{year}/document.yaml" for year in (2000, 2001, 2002)]
    assert document_keys(paths) == {"Fixture2002"}
    assert document_keys(paths, include_fixtures=True) == {
        "Fixture2000",
        "Fixture2001",
        "Fixture2002",
    }


def test_owner_sensitivity_includes_deleted_keys_but_not_structure() -> None:
    """Field-level gating catches removals without demanding review for page-range work."""
    path = "literature/Example2000/document.yaml"
    before = "doc_key: Example2000\nyear: 2000\nfoundations: []\nstructure: []\n"
    assert not approval_reasons(
        [path], lambda _: before, lambda _: before.replace("structure: []", "structure: [1]")
    )
    assert approval_reasons(
        [path], lambda _: before, lambda _: before.replace("foundations: []\n", "")
    )
    assert approval_reasons([path], lambda _: None, lambda _: before)
    assert approval_reasons([path], lambda _: before, lambda _: None)


def test_owner_review_requires_latest_head_and_decision() -> None:
    """Old approvals and subsequently dismissed/request-changes reviews do not pass."""
    approved = {
        "id": 1,
        "state": "APPROVED",
        "commit_id": "abc",
        "submitted_at": "2026-01-01",
        "user": {"login": "owner"},
    }
    assert owner_approved("owner", "alice", "abc", [approved])
    assert not owner_approved("owner", "alice", "def", [approved])
    assert not owner_approved(
        "owner", "alice", "abc", [approved, approved | {"id": 2, "state": "CHANGES_REQUESTED"}]
    )
    assert owner_approved("owner", "owner", "abc", [])


def test_agent_foundations_need_trusted_policy_and_current_evidence() -> None:
    """Agent review exemptions cannot hide stale content, deletions or human replacement."""
    from homalg.documents import dump_metadata
    from homalg.review_policy import foundation_hash

    path = "literature/Example2000/document.yaml"
    entry = {
        "notion": "Vector spaces",
        "mathlib": ["Module"],
        "justification": "Elementary background",
        "evidence": "Source page 1",
        "status": "proposed",
    }
    reviewed = entry | {
        "status": "confirmed",
        "confirmation": {
            "kind": "agent",
            "status": "satisfactory",
            "by": "reviewer",
            "on": "2026-10-28",
            "session": "review-session",
            "author_session": "author-session",
            "content_sha256": foundation_hash(entry),
        },
    }
    policy = {"schema_version": 1, "allow_independent_agent_reviews": True}

    def reasons(old: list, new: list, effective: dict | None = None) -> list[str]:
        return approval_reasons(
            [path],
            lambda _: dump_metadata({"foundations": old}),
            lambda _: dump_metadata({"foundations": new}),
            review_policy=effective,
        )

    assert reasons([entry], [reviewed])
    assert not reasons([entry], [reviewed], policy)
    assert not reasons([], [reviewed], policy)
    assert reasons([entry], [reviewed | {"evidence": "Changed premise"}], policy)
    assert reasons([reviewed], [], policy)
    human = entry | {"status": "confirmed", "confirmed_by": "human-reviewer"}
    assert reasons([human], [reviewed], policy)


def test_append_only_rejects_mutation_deletion_and_duplicate_ids() -> None:
    """Stable ids are not enough: old records must remain byte-independent equal data."""
    old = {"tags": [{"id": "one", "label": "One"}]}
    assert append_only(old, {"tags": [*old["tags"], {"id": "two"}]}, "tags")
    for items in ([], [{"id": "one", "label": "Changed"}], old["tags"] * 2):
        assert not append_only(old, {"tags": items}, "tags")
