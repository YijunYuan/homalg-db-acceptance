"""Independent review policy preserves human evidence and binds every foundation content field."""

import copy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from homalg import foundations, planning, review
from homalg.documents import read_document, write_metadata
from homalg.nodeio import header_mapping, replace_header
from homalg.review_policy import (
    agent_review_record,
    agent_reviews_allowed,
    foundation_confirmation_valid,
    foundation_confirmed,
    foundation_hash,
    valid_agent_review,
)
from homalg.schemas import SchemaStore

NOW = datetime(2026, 10, 28, tzinfo=UTC)


def enable(repo: Path) -> None:
    path = repo / "horizon/review-policy.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("schema_version: 1\nallow_independent_agent_reviews: true\n")


def evidence(
    repo: Path, *, session: str = "independent-reviewer", author: str = "source-writer"
) -> dict:
    return agent_review_record(
        repo, by="review-agent", session=session, author_session=author, now=NOW
    )


def report(path: Path, *, notion: str = "Source definition", honesty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "Session: independent-reviewer\nAuthor-session: source-writer\n\n"
        "## source-fidelity — independent comparison\nStatus: satisfactory\n"
        "Verdict: Source and formal assumptions agree.\n"
        "| Source | Formal evidence |\n| --- | --- |\n"
        + f"| {notion} | Verified against the source. |\n"
    )
    if honesty:
        text += (
            "\n## honesty — independent comparison\nStatus: satisfactory\n"
            "Verdict: No hidden conclusions.\n| Check | Evidence |\n| --- | --- |\n"
            "| Assumptions | Exactly defining laws. |\n"
        )
    path.write_text(text)


def save(repo: Path, document: dict) -> None:
    write_metadata(
        repo / "literature/Fixture2000/document.yaml",
        document,
        "document.schema.json",
        SchemaStore(repo / "schema"),
    )


def proposed(repo: Path) -> dict:
    document = read_document(repo, "Fixture2000")
    document["foundations"] = [
        {
            "notion": "Additive group",
            "mathlib": ["AddCommGroup"],
            "justification": "Basic linear algebra",
            "status": "proposed",
            "evidence": "Synthetic source p. 1",
        }
    ]
    save(repo, document)
    report(repo / "literature/Fixture2000/reviews/foundations.md", notion="Additive group")
    return document


def test_policy_is_explicit_and_frozen_policy_overrides_live_file(repo: Path) -> None:
    assert not agent_reviews_allowed(repo)
    enable(repo)
    assert agent_reviews_allowed(repo)
    assert not agent_reviews_allowed(
        repo, policy={"schema_version": 1, "allow_independent_agent_reviews": False}
    )
    assert not agent_reviews_allowed(repo, policy={})
    for version in (True, "1", 2):
        assert not agent_reviews_allowed(
            repo, policy={"schema_version": version, "allow_independent_agent_reviews": True}
        )
    assert not agent_reviews_allowed(repo, policy=[])
    with pytest.raises(ValueError, match="distinct"):
        evidence(repo, session="same", author=" same ")
    valid = evidence(repo)
    assert valid_agent_review(valid)
    assert not valid_agent_review(valid | {"on": "2026-02-30"})
    assert not valid_agent_review(valid | {"kind": "human"})
    assert not valid_agent_review(valid | {"author_session": ""})


def test_foundation_confirmation_has_distinct_identity_and_content_hash(repo: Path) -> None:
    enable(repo)
    proposed(repo)
    entry = foundations.review(
        repo,
        "Fixture2000",
        1,
        by="review-agent",
        session="independent-reviewer",
        author_session="source-writer",
        now=NOW,
    )
    assert entry["status"] == "confirmed" and "confirmed_by" not in entry
    assert entry["confirmation"]["kind"] == "agent"
    assert foundation_confirmation_valid(entry) and foundation_confirmed(entry, repo)
    assert not foundation_confirmed(
        entry, policy={"schema_version": 1, "allow_independent_agent_reviews": False}
    )
    for field in ("notion", "evidence", "justification", "note", "mathlib"):
        modified = copy.deepcopy(entry)
        modified[field] = ["Nat"] if field == "mathlib" else "Changed content"
        assert not foundation_confirmation_valid(modified), field
    assert foundation_hash(entry) == foundation_hash(entry | {"status": "proposed"})
    assert not SchemaStore(repo / "schema").validate(
        read_document(repo, "Fixture2000"), "document.schema.json"
    )


@pytest.mark.parametrize("failure", ["disabled", "self", "report-session", "verdict", "human"])
def test_failed_agent_foundation_review_never_changes_document(repo: Path, failure: str) -> None:
    document = proposed(repo)
    if failure != "disabled":
        enable(repo)
    author = "source-writer"
    if failure == "self":
        author = "independent-reviewer"
    elif failure == "report-session":
        author = "different-author"
    elif failure == "verdict":
        path = repo / "literature/Fixture2000/reviews/foundations.md"
        path.write_text(path.read_text().replace("Status: satisfactory", "Status: mismatch"))
    elif failure == "human":
        document["foundations"][0].update(status="confirmed", confirmed_by="fictional-human")
        save(repo, document)
    path = repo / "literature/Fixture2000/document.yaml"
    before = path.read_bytes()
    with pytest.raises(ValueError):
        foundations.review(
            repo,
            "Fixture2000",
            1,
            by="review-agent",
            session="independent-reviewer",
            author_session=author,
        )
    assert path.read_bytes() == before


def test_enabled_policy_locks_explained_deviation_with_agent_provenance(
    repo: Path, monkeypatch
) -> None:
    enable(repo)
    path = repo / "HomAlg/Fixture2000/Thm_1.lean"
    text = path.read_text()
    metadata = header_mapping(text)
    metadata["fidelity"] = {
        "status": "deviates",
        "deviations": [
            {
                "kind": "proof-route",
                "what": "Different elementary calculation",
                "why": "The displayed calculation proves exactly the same source statement",
            }
        ],
    }
    path.write_text(replace_header(text, metadata, SchemaStore(repo / "schema")))
    report(repo / "literature/Fixture2000/reviews/Thm_1.md")
    monkeypatch.setattr("homalg.leanexport.export_lean", lambda *args, **kw: {})
    monkeypatch.setattr(
        review, "require_human", lambda *args, **kw: pytest.fail("agent requested human permission")
    )
    lock = review.review_fidelity(
        repo,
        "Fixture2000.Thm_1",
        by="review-agent",
        session="independent-reviewer",
        author_session="source-writer",
        now=NOW,
    )
    assert valid_agent_review(lock)
    assert lock["decl_hashes"] and lock["kind"] == "agent"
    assert header_mapping(path.read_text())["fidelity"]["reviewed"] == lock


def test_agent_cannot_overwrite_human_fidelity_or_use_same_session(repo: Path, monkeypatch) -> None:
    enable(repo)
    path = repo / "HomAlg/Fixture2000/Def_2.lean"
    text = path.read_text()
    metadata = header_mapping(text)
    metadata["fidelity"]["reviewed"] = {
        "by": "fictional-human",
        "kind": "human",
        "status": "satisfactory",
        "on": "2026-10-28",
        "decl_hashes": {},
    }
    path.write_text(replace_header(text, metadata, SchemaStore(repo / "schema")))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="existing human"):
        review.review_fidelity(
            repo,
            "Fixture2000.Def_2",
            by="review-agent",
            session="independent-reviewer",
            author_session="source-writer",
        )
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="distinct"):
        review.review_fidelity(
            repo, "Fixture2000.Thm_1", by="review-agent", session="same", author_session="same"
        )


def setup_plan(repo: Path, monkeypatch) -> dict:
    enable(repo)
    document = proposed(repo)
    entry = document["foundations"][0]
    entry["status"] = "confirmed"
    entry["confirmation"] = evidence(repo) | {"content_sha256": foundation_hash(entry)}
    document.pop("early_review", None)
    save(repo, document)
    for stage in (None, *planning.STAGES):
        name = "Fixture2000" + ("." + stage if stage else "")
        path = repo / ".archon-horizon/roadmap/items" / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    monkeypatch.setattr(planning, "unlocked_tasks", lambda *args: ([], True))
    monkeypatch.setattr(planning, "tasks", lambda *args: [])
    monkeypatch.setattr(planning, "settings", lambda repo: {"login": "fixture-user"})
    monkeypatch.setattr(
        planning, "scope_nodes", lambda *args: [{"fidelity": {"reviewed": evidence(repo)}}]
    )
    monkeypatch.setattr(
        planning,
        "require_human",
        lambda *args, **kw: pytest.fail("agent requested human permission"),
    )
    return document


def test_early_agent_review_advances_without_human_impersonation(repo: Path, monkeypatch) -> None:
    setup_plan(repo, monkeypatch)
    outcome = planning.plan(
        repo,
        "Fixture2000",
        early_review_ok=True,
        by="review-agent",
        session="independent-reviewer",
        author_session="source-writer",
        no_claim=True,
    )
    assert outcome["early_review"] == "accepted"
    assert valid_agent_review(read_document(repo, "Fixture2000")["early_review"])


def test_early_review_rejects_stale_foundation_confirmation(repo: Path, monkeypatch) -> None:
    document = setup_plan(repo, monkeypatch)
    document["foundations"][0]["evidence"] += " Changed."
    save(repo, document)
    with pytest.raises(ValueError, match="confirmed foundations"):
        planning.plan(
            repo,
            "Fixture2000",
            early_review_ok=True,
            by="review-agent",
            session="independent-reviewer",
            author_session="source-writer",
            no_claim=True,
        )
    assert "early_review" not in read_document(repo, "Fixture2000")


def test_pending_agent_review_uses_supported_inbox_recipient(repo: Path, monkeypatch) -> None:
    setup_plan(repo, monkeypatch)
    calls = []

    def inbox(root: Path, *args: str) -> str:
        assert root == repo and args[:2] == ("inbox", "add")
        assert args[args.index("--to") + 1] == "horizon"
        title, description = args[args.index("--body") + 1].split("\n\n", 1)
        assert "early-review" in title and "independent agent" in description
        calls.append(args)
        return "I-0042"

    monkeypatch.setattr(planning, "horizon", inbox)
    assert planning.plan(repo, "Fixture2000", no_claim=True)["early_review"] == "pending"
    assert len(calls) == 1


def test_pending_policy_review_is_addressed_to_agents(repo: Path, monkeypatch) -> None:
    setup_plan(repo, monkeypatch)
    calls = []
    monkeypatch.setattr(planning, "horizon", lambda *args: calls.append(args))
    planning.plan(repo, "Fixture2000", no_claim=True)
    request = next(args for args in calls if args[1:3] == ("inbox", "add"))
    assert request[request.index("--to") + 1] == "horizon"


def test_report_provenance_uses_latest_review_blocks(repo: Path) -> None:
    from homalg.review_policy import require_report_provenance

    historical = (
        "## source-fidelity — earlier review\nSession: previous-reviewer\n"
        "Author-session: previous-author\nStatus: partial\nVerdict: Incomplete.\n"
    )
    current = (
        "## source-fidelity — independent review\nSession: independent-reviewer\n"
        "Author-session: source-writer\nStatus: satisfactory\nVerdict: Compared.\n"
    )
    require_report_provenance(
        historical + current, session="independent-reviewer", author_session="source-writer"
    )
    with pytest.raises(ValueError, match="Session"):
        require_report_provenance(
            current + historical, session="independent-reviewer", author_session="source-writer"
        )


def test_agent_review_does_not_resolve_open_source_disagreement(repo: Path) -> None:
    enable(repo)
    source = repo / "HomAlg/Fixture2000/Prop_1.lean"
    before = source.read_bytes()
    with pytest.raises(ValueError, match="adjudication"):
        review.review_fidelity(
            repo,
            "Fixture2000.Prop_1",
            by="review-agent",
            session="independent-reviewer",
            author_session="source-writer",
        )
    assert source.read_bytes() == before


def test_foundation_review_cli_writes_only_agent_confirmation(repo: Path) -> None:
    import json

    from click.testing import CliRunner

    from homalg.cli import cli

    enable(repo)
    proposed(repo)
    result = CliRunner().invoke(
        cli,
        [
            "foundations",
            "review",
            "--repo",
            str(repo),
            "--json",
            "Fixture2000",
            "1",
            "--by",
            "review-agent",
            "--session",
            "independent-reviewer",
            "--author-session",
            "source-writer",
        ],
    )
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)["data"]["entry"]
    assert record["confirmation"]["kind"] == "agent" and "confirmed_by" not in record


def test_plan_cli_passes_independent_review_identifiers(repo: Path, monkeypatch) -> None:
    from click.testing import CliRunner

    from homalg.cli import cli

    captured = []
    monkeypatch.setattr(planning, "plan", lambda *args, **kw: captured.append(kw) or {})
    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "--repo",
            str(repo),
            "--json",
            "Fixture2000",
            "--early-review-ok",
            "--by",
            "review-agent",
            "--session",
            "independent-reviewer",
            "--author-session",
            "source-writer",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured[0]["session"] == "independent-reviewer"
    assert captured[0]["author_session"] == "source-writer"
