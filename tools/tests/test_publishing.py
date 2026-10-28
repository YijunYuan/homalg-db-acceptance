"""Numeric status uses live ownership and fast-forward Git plumbing against local bare remotes."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from homalg import publishing
from homalg.collaboration import Client, ExternalToolError
from homalg.documents import dump_metadata
from homalg.lifecycle import git
from homalg.schemas import SchemaStore

NOW = datetime(2026, 1, 15, tzinfo=UTC)


def test_diagnostic_inbox_body_has_a_title_and_paragraph(repo: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(publishing, "inbox_items", lambda _: [])
    monkeypatch.setattr(
        publishing.engine,
        "horizon",
        lambda root, *args: calls.append((root, args)) or '{"id":"I-0001"}',
    )
    assert (
        publishing.notify(
            repo, "Fixture2000", "Publication failed.", rule="publish", node="Fixture2000.Thm_1"
        )
        == "I-0001"
    )
    root, args = calls[0]
    assert root == repo
    body = args[args.index("--body") + 1]
    assert body == "[homalg:publish:Fixture2000.Thm_1]\n\nPublication failed."


@pytest.fixture
def publication(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    remote = tmp_path / "public.git"
    remote.mkdir()
    git(remote, "init", "--bare", "-q", "-b", "main")
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.name", "Test"),
        ("config", "user.email", "test@example.invalid"),
    ):
        git(repo, *args)
    (repo / ".gitignore").write_text(
        ".archon-horizon/\nbuild/\npublic.git/\nliterature/.private/\n"
    )
    claim = {
        "schema_version": 1,
        "doc_key": "Fixture2000",
        "claims": [
            {
                "holder": "alice",
                "claimed_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-03-01T00:00:00Z",
                "scope": {"chapters": ["1"], "sections": [], "note": "PRIVATE CLAIM TEXT"},
            }
        ],
    }
    (repo / "literature/Fixture2000/claim.yaml").write_text(dump_metadata(claim))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Registered contribution")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-qu", "origin", "main")
    git(repo, "checkout", "-qb", "work")
    settings = repo / ".archon-horizon/overlay/homalg.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text("login: alice\n")
    monkeypatch.setattr(publishing, "inbox_items", lambda repo: [])
    monkeypatch.setattr(publishing, "notify", lambda *args, **kwargs: "I-0001")
    return repo, remote


def test_status_is_numeric_and_leaves_worktree_and_index_untouched(publication: tuple) -> None:
    repo, remote = publication
    (repo / "unrelated.txt").write_text("Unrelated staged user work.\n")
    git(repo, "add", "unrelated.txt")
    (repo / "unrelated.txt").write_text("Later unstaged user work.\n")
    before_head = git(repo, "rev-parse", "HEAD").stdout
    before_status = git(repo, "status", "--porcelain").stdout
    before_index = git(repo, "diff", "--cached", "--binary").stdout
    first = publishing.publish_status(repo, "Fixture2000", now=NOW)
    assert first["published"], first
    payload = json.loads(git(remote, "show", "status/Fixture2000:status.json").stdout)
    assert not SchemaStore(repo / "schema").validate(payload, "run-status.schema.json")
    assert "PRIVATE CLAIM TEXT" not in json.dumps(payload)
    assert payload["holder"] == "alice" and payload["last_check"] == {"result": "none", "at": None}
    assert git(remote, "ls-tree", "--name-only", "status/Fixture2000").stdout == b"status.json\n"
    assert git(repo, "rev-parse", "HEAD").stdout == before_head
    assert git(repo, "status", "--porcelain").stdout == before_status
    assert git(repo, "diff", "--cached", "--binary").stdout == before_index
    assert not publishing.publish_status(repo, "Fixture2000", now=NOW + timedelta(minutes=30))[
        "published"
    ]
    second = publishing.publish_status(repo, "Fixture2000", now=NOW + timedelta(minutes=61))
    assert second["published"]
    assert (
        git(remote, "rev-parse", "status/Fixture2000^").stdout.decode().strip() == first["commit"]
    )


def test_status_refuses_stale_working_branch_owner(publication: tuple, tmp_path: Path) -> None:
    repo, remote = publication
    other = tmp_path / "updater"
    git(repo, "clone", "-q", str(remote), str(other))
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.invalid")
    claim_path = other / "literature/Fixture2000/claim.yaml"
    claim_path.write_text(claim_path.read_text().replace("alice", "bob"))
    git(other, "add", str(claim_path))
    git(other, "commit", "-qm", "New claimant on main")
    git(other, "push", "-q", "origin", "main")
    result = publishing.publish_status(repo, "Fixture2000", now=NOW)
    assert result == {"published": False, "reason": "claim-inactive"}
    assert "alice" in (repo / "literature/Fixture2000/claim.yaml").read_text()
    assert git(
        remote, "show-ref", "--verify", "refs/heads/status/Fixture2000", check=False
    ).returncode


def test_expired_claim_cannot_be_revived_by_publication(publication: tuple) -> None:
    repo, _ = publication
    result = publishing.publish_status(repo, "Fixture2000", now=NOW + timedelta(days=400))
    assert result["reason"] == "claim-inactive"


def test_failed_fetch_is_logged_and_retried_without_throttle(publication: tuple) -> None:
    repo, _ = publication

    class Offline(Client):
        def fetch(self, key=None):
            raise ExternalToolError("network unavailable")

    result = publishing.publish_status(repo, "Fixture2000", now=NOW, client=Offline(repo))
    assert result["reason"] == "network-or-git-error"
    assert not (repo / ".archon-horizon/overlay/publish-status-Fixture2000.json").exists()
    assert "network unavailable" in (repo / ".archon-horizon/overlay/hooks.log").read_text()
    assert publishing.publish_status(repo, "Fixture2000", now=NOW)["published"]


def test_concurrent_publication_is_never_force_pushed(publication: tuple) -> None:
    repo, remote = publication
    first = publishing.publish_status(repo, "Fixture2000", now=NOW)
    other = None

    class Racing(Client):
        def git(self, *args, **kwargs):
            nonlocal other
            if (
                args[0] == "push"
                and args[1] == "origin"
                and args[2].endswith(":refs/heads/status/Fixture2000")
            ):
                tree = super().git("rev-parse", f"{first['commit']}^{{tree}}").strip()
                other = (
                    super()
                    .git(
                        "commit-tree",
                        tree,
                        "-p",
                        first["commit"],
                        "-m",
                        "Concurrent numeric status",
                    )
                    .strip()
                )
                super().git("push", "origin", f"{other}:refs/heads/status/Fixture2000")
            return super().git(*args, **kwargs)

    result = publishing.publish_status(
        repo, "Fixture2000", now=NOW + timedelta(minutes=61), client=Racing(repo)
    )
    assert not result["published"]
    assert git(remote, "rev-parse", "status/Fixture2000").stdout.decode().strip() == other


def test_backup_uses_private_remote_and_preserves_unrelated_staging(
    publication: tuple, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from homalg import lifecycle

    repo, public = publication
    private = tmp_path / "backup.git"
    private.mkdir()
    git(private, "init", "--bare", "-q", "-b", "main")
    monkeypatch.setenv("HOMALG_BACKUP_REMOTE", str(private))
    record = {
        "id": "I-001",
        "status": "open",
        "body": "Private detailed discussion",
        "scope": {"blueprint_nodes": ["Fixture2000.Thm_1"]},
    }
    monkeypatch.setattr(publishing, "inbox_items", lambda repo: [record])
    (repo / "unrelated.txt").write_text("Keep this staged separately.\n")
    git(repo, "add", "unrelated.txt")
    before = git(repo, "diff", "--cached", "--binary").stdout
    public_head = git(public, "rev-parse", "main").stdout
    result = lifecycle.backup(repo, now=NOW)
    assert result["backed_up"]
    assert git(repo, "diff", "--cached", "--binary").stdout == before
    assert git(public, "rev-parse", "main").stdout == public_head
    assert (
        b"Private detailed discussion"
        in git(
            private, "show", "backup/alice/work:literature/Fixture2000/run-log/inbox/I-001.yaml"
        ).stdout
    )
    assert git(private, "cat-file", "-e", "backup/alice/work:unrelated.txt", check=False).returncode
    assert lifecycle.backup(repo, now=NOW + timedelta(hours=5))["reason"] == "throttled"
    monkeypatch.setenv("HOMALG_BACKUP_REMOTE", "origin")
    with pytest.raises(ValueError, match="differ from the public origin"):
        lifecycle.backup(repo, now=NOW, force=True)


def advance_main(repo: Path, remote: Path, path: str, content: str) -> None:
    other = repo.parent / (repo.name + "-main-update")
    git(repo, "clone", "-q", str(remote), str(other))
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.invalid")
    (other / path).write_text(content)
    git(other, "add", path)
    git(other, "commit", "-qm", "Main update")
    git(other, "push", "-q", "origin", "main")


def test_sync_owned_conflict_keeps_work_and_regenerates(publication: tuple, monkeypatch) -> None:
    from homalg import lifecycle

    repo, remote = publication
    path = "HomAlg/Fixture2000/Thm_1.lean"
    text = (repo / path).read_text()
    advance_main(repo, remote, path, text + "\n-- Main amendment.\n")
    (repo / path).write_text(text + "\n-- Owner contribution.\n")
    git(repo, "add", path)
    git(repo, "commit", "-qm", "Owner update")
    monkeypatch.setattr(lifecycle, "require_idle", lambda *args: None)
    exported = []
    monkeypatch.setattr(lifecycle, "export_lean", lambda repo, key: exported.append(key))
    result = lifecycle.sync_main(repo, now=NOW)
    assert result["owned"] == ["Fixture2000"]
    assert path in result["resolved"]
    assert "Owner contribution" in (repo / path).read_text()
    assert "Main amendment" not in (repo / path).read_text()
    assert exported == ["Fixture2000"]
    assert not git(repo, "status", "--porcelain").stdout
    assert len(git(repo, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()) == 3


def test_sync_unowned_conflict_aborts_to_original_work(publication: tuple, monkeypatch) -> None:
    from homalg import lifecycle

    repo, remote = publication
    path = "HomAlg/Fixture2001/Thm_1.lean"
    text = (repo / path).read_text()
    advance_main(repo, remote, path, text + "\n-- Main amendment.\n")
    (repo / path).write_text(text + "\n-- Unowned local amendment.\n")
    git(repo, "add", path)
    git(repo, "commit", "-qm", "Unowned update")
    before = git(repo, "rev-parse", "HEAD").stdout
    monkeypatch.setattr(lifecycle, "require_idle", lambda *args: None)
    with pytest.raises(ValueError, match="outside owned"):
        lifecycle.sync_main(repo, now=NOW)
    assert git(repo, "rev-parse", "HEAD").stdout == before
    assert not git(repo, "status", "--porcelain").stdout
    assert git(repo, "rev-parse", "--verify", "MERGE_HEAD", check=False).returncode
