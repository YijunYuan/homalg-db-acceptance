"""Local Git integration and fake-gh policy tests; no network or remote account writes."""

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from homalg.collaboration import (
    Client,
    ExternalToolError,
    append_merge_records,
    claim_operation,
    submit,
)
from homalg.documents import dump_metadata, parse_metadata
from homalg.pr_checks import pr_findings

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 1, 10, tzinfo=UTC)


def git(repo: Path, *args: str) -> str:
    """Execute Git only inside a disposable test checkout."""
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Create a real checkout and local bare origin, with one registered article."""
    repo, remote = tmp_path / "repo", tmp_path / "remote.git"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test Contributor")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(tmp_path, "init", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    shutil.copytree(ROOT / "schema", repo / "schema")
    shutil.copytree(ROOT / "taxonomy", repo / "taxonomy")
    document = json.loads((ROOT / "tools/tests/fixtures/good/document.json").read_text())
    document.update(
        doc_key="Example2000",
        type="article",
        pdf={"file": "source.pdf", "sha256": "0" * 64, "license": {"id": "proprietary"}},
    )
    literature = repo / "literature/Example2000"
    literature.mkdir(parents=True)
    (literature / "document.yaml").write_text(dump_metadata(document))
    (literature / "claim.yaml").write_text(
        dump_metadata({"schema_version": 1, "doc_key": "Example2000", "claims": []})
    )
    (repo / "lakefile.toml").write_text('name = "test"\n')
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Initial metadata")
    git(repo, "push", "-u", "origin", "main")
    git(repo, "switch", "-c", "work")
    return repo


class FakeGh(Client):
    """Use real local Git while replacing every authenticated GitHub call."""

    def __init__(self, repo: Path, holder: str = "alice"):
        super().__init__(repo)
        self.holder = holder
        self.calls: list[tuple[str, ...]] = []
        self.reviews: list[dict[str, Any]] = []
        self.body = ""

    def identity(self) -> tuple[str, str]:
        return self.holder, "owner/homalg-db"

    def gh(self, *args: str) -> str:
        self.calls.append(args)
        if args[:2] == ("repo", "view"):
            return '{"nameWithOwner":"owner/homalg-db"}'
        if args[:2] == ("pr", "list"):
            return "[]"
        if args[:2] == ("pr", "create"):
            self.body = Path(args[args.index("--body-file") + 1]).read_text()
            return "https://github.com/owner/homalg-db/pull/1\n"
        if args[:2] == ("pr", "merge"):
            return ""
        raise AssertionError(args)

    def api(self, endpoint: str) -> Any:
        if endpoint.endswith("/reviews"):
            return self.reviews
        return {
            "head": {"repo": {"full_name": "owner/homalg-db"}, "ref": "work"},
            "base": {"repo": {"full_name": "owner/homalg-db"}},
        }


def set_claim(repo: Path, holder: str = "alice", expiry: str = "2026-01-20T00:00:00Z") -> None:
    """Put an existing claim on main as a setup operation."""
    path = repo / "literature/Example2000/claim.yaml"
    data = parse_metadata(path.read_text())
    data["claims"] = [
        {
            "holder": holder,
            "claimed_at": "2026-01-01T00:00:00Z",
            "expires_at": expiry,
            "scope": {"chapters": [], "sections": []},
        }
    ]
    path.write_text(dump_metadata(data))
    git(repo, "add", str(path))
    git(repo, "commit", "-m", "Existing claim")
    git(repo, "push", "origin", "HEAD:main")


def test_claim_dry_run_does_not_change_worktree_or_publish(repository: Path) -> None:
    """Remote-state preview preserves both branch and staged user work."""
    client = FakeGh(repository)
    (repository / "unrelated.txt").write_text("unrelated work")
    git(repository, "add", "unrelated.txt")
    before = git(repository, "status", "--porcelain")
    result = claim_operation(
        repository, "Example2000", "take", now=NOW, dry_run=True, client=client
    )
    assert result["published"] is False
    assert result["claim"]["claims"][0]["holder"] == "alice"
    assert git(repository, "status", "--porcelain") == before
    assert not any(call[:2] == ("pr", "create") for call in client.calls)


def test_claim_publication_is_scoped_and_preserves_user_index(repository: Path) -> None:
    """A claim branch contains exactly claim.yaml despite unrelated staged work."""
    client = FakeGh(repository)
    (repository / "unrelated.txt").write_text("unrelated work")
    git(repository, "add", "unrelated.txt")
    before = git(repository, "status", "--porcelain")
    result = claim_operation(repository, "Example2000", "take", now=NOW, watch=False, client=client)
    assert result["published"]
    assert git(repository, "branch", "--show-current") == "work"
    assert git(repository, "status", "--porcelain") == before
    assert (
        git(repository, "diff", "--name-only", "origin/main...claim/Example2000/alice-20260110")
        == "literature/Example2000/claim.yaml"
    )
    assert len(git(repository, "worktree", "list").splitlines()) == 1
    assert "FR-12" in client.body


def test_takeover_refuses_current_main_holder(repository: Path) -> None:
    """A stale local unclaimed file cannot override someone else's active main claim."""
    set_claim(repository)
    with pytest.raises(ValueError, match="actively claimed"):
        claim_operation(
            repository, "Example2000", "take", now=NOW, client=FakeGh(repository, "bob")
        )


def test_network_failure_is_not_treated_as_missing_status(repository: Path) -> None:
    """Only the absent-reference fetch error is ignorable."""

    class FailedFetch(Client):
        def run(self, *args: str, **kwargs: Any) -> subprocess.CompletedProcess:
            if args[:3] == ("git", "fetch", "origin") and args[3].startswith("status/"):
                return subprocess.CompletedProcess(args, 128, "", "fatal: authentication failed")
            return super().run(*args, **kwargs)

    with pytest.raises(ExternalToolError, match="authentication failed"):
        FailedFetch(repository).fetch("Example2000")


def test_merge_appends_only_new_work_ids_to_current_main() -> None:
    """A maintenance edit on main survives merging unrelated additions from work."""
    base = {"tags": [{"id": "old", "label": "Old"}]}
    main = {"tags": [{"id": "old", "label": "Updated"}, {"id": "other"}]}
    work = {"tags": [*base["tags"], {"id": "new"}]}
    merged = append_merge_records(base, main, work, "tags")
    assert merged["tags"] == [*main["tags"], {"id": "new"}]
    with pytest.raises(ValueError, match="Conflicting"):
        append_merge_records(
            base, main, {"tags": [*base["tags"], {"id": "other", "label": "Conflict"}]}, "tags"
        )


def test_submit_refuses_expired_claim_before_backup(repository: Path) -> None:
    """Submission may never renew an expired claim through its formalization PR."""
    set_claim(repository, expiry="2026-01-05T00:00:00Z")

    class Hooks:
        def ensure_idle(self, *_: Any) -> None:
            pass

        def backup(self, *_: Any) -> None:
            raise AssertionError("backup must not run for an expired claim")

    with pytest.raises(ValueError, match="claim expired"):
        submit(repository, "Example2000", now=NOW, client=FakeGh(repository), hooks=Hooks())
    with pytest.raises(ValueError, match="only permitted"):
        submit(repository, "Example2000", no_claim=True, client=FakeGh(repository))


def test_fixture_named_article_cannot_use_no_claim(repository: Path) -> None:
    """Acceptance bypass follows the reviewed document type, never a name prefix."""
    previous = repository / "literature/Example2000"
    renamed = previous.with_name("Fixture2002")
    previous.rename(renamed)
    for name in ("document.yaml", "claim.yaml"):
        path = renamed / name
        data = parse_metadata(path.read_text())
        data["doc_key"] = "Fixture2002"
        if name == "document.yaml":
            data["year"] = 2002
        path.write_text(dump_metadata(data))
    with pytest.raises(ValueError, match="only permitted for synthetic"):
        submit(repository, "Fixture2002", no_claim=True, client=FakeGh(repository))


def test_owner_check_uses_newest_exact_head_review(repository: Path) -> None:
    """An approval of an older revision does not unlock a sensitive metadata change."""
    base = git(repository, "rev-parse", "HEAD")
    path = repository / "literature/Example2000/document.yaml"
    data = parse_metadata(path.read_text())
    data["may_import"] = ["Other1999"]
    path.write_text(dump_metadata(data))
    git(repository, "add", str(path))
    git(repository, "commit", "-m", "Sensitive metadata")
    client = FakeGh(repository)
    client.reviews = [
        {
            "id": 1,
            "user": {"login": "owner"},
            "state": "APPROVED",
            "commit_id": base,
            "submitted_at": "2026-01-10T00:00:00Z",
        }
    ]
    args = {
        "base": base,
        "author": "alice",
        "owner": "owner",
        "number": 1,
        "owner_only": True,
        "client": client,
    }
    assert any(f.rule == "owner-approval" for f in pr_findings(repository, **args))
    client.reviews[0]["commit_id"] = git(repository, "rev-parse", "HEAD")
    assert not pr_findings(repository, **args)


def test_claim_race_reads_latest_main(repository: Path) -> None:
    """Concurrent takeover is rejected even when the PR's merge base was unclaimed."""
    base = git(repository, "rev-parse", "HEAD")
    set_claim(repository, "alice")
    path = repository / "literature/Example2000/claim.yaml"
    data = parse_metadata(path.read_text())
    data["claims"][0].update(holder="bob", claimed_at="2026-01-10T00:00:00Z")
    path.write_text(dump_metadata(data))
    git(repository, "add", str(path))
    git(repository, "commit", "-m", "Concurrent claim")
    findings = pr_findings(
        repository,
        base=base,
        author="bob",
        created_at="2026-01-10T00:00:00Z",
        now=NOW,
        client=FakeGh(repository, "bob"),
    )
    assert any(f.rule == "claim-author" for f in findings)


def test_registration_publishes_only_two_metadata_files(repository: Path) -> None:
    """Registration never copies node data, private PDFs or unrelated local edits."""
    from homalg.collaboration import register_document

    source = repository / "literature/Example2000/document.yaml"
    document = parse_metadata(source.read_text())
    document["doc_key"] = "New2000"
    files = {
        "literature/New2000/document.yaml": dump_metadata(document),
        "literature/New2000/claim.yaml": dump_metadata(
            {"schema_version": 1, "doc_key": "New2000", "claims": []}
        ),
    }
    result = register_document(repository, "New2000", files, client=FakeGh(repository))
    assert result["branch"] == "register/New2000"
    assert set(
        git(repository, "diff", "--name-only", "origin/main...register/New2000").splitlines()
    ) == set(files)
    with pytest.raises(ValueError, match="exactly"):
        register_document(
            repository, "New2000", files | {"source.pdf": "not allowed"}, client=FakeGh(repository)
        )
