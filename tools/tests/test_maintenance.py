"""Maintenance probes retain source routes and expose real comparison limitations."""

import json
import subprocess
from pathlib import Path

import pytest

from homalg.maintenance import comparison_nodes, redundant_mathlib_imports, review_summary


def test_import_probe_preserves_comments_and_checks_elaboration(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only code imports are removed, and tactic-dependent imports survive a failed probe."""
    source = (
        "import Mathlib.Data.Nat.Basic\nimport Mathlib.Tactic.Omega\n"
        "/- import Mathlib.Fake\n-/\n-- import Mathlib.AlsoFake\n"
        "theorem test (n : Nat) : n < n + 1 := by omega\n"
    )
    visited = []

    def compile_copy(command: list[str], **_: object) -> subprocess.CompletedProcess:
        text = Path(command[-1]).read_text()
        visited.append(text)
        assert "/- import Mathlib.Fake" in text
        assert "-- import Mathlib.AlsoFake" in text
        assert "by omega" in text
        return subprocess.CompletedProcess(
            command, 0 if "import Mathlib.Tactic.Omega" in text else 1, "", ""
        )

    monkeypatch.setattr("homalg.maintenance.subprocess.run", compile_copy)
    assert redundant_mathlib_imports(repo, source) == ["Mathlib.Data.Nat.Basic"]
    assert len(visited) == 2
    assert not list((repo / "build").glob("imports-*"))


def test_review_comparison_uses_committed_blob_without_checkout(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stored before/after change is visible while no baseline is explicitly unknown."""
    # Horizon's TMPDIR is inside its checkout: stop Git discovering that parent.
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    monkeypatch.delenv("GITHUB_BASE_SHA", raising=False)
    assert comparison_nodes(repo, "Fixture2000") == (None, {})
    for command in (
        ["git", "config", "user.name", "Test"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "add", "literature/Fixture2000/nodes.json"],
        ["git", "commit", "-qm", "Baseline"],
    ):
        subprocess.run(command, cwd=repo, check=True)
    path = repo / "literature/Fixture2000/nodes.json"
    data = json.loads(path.read_text())
    node = next(node for node in data["nodes"] if node["id"].endswith(".Thm_1"))
    node["derived"]["local_status"] = "stated"
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    summary = review_summary(repo, "Fixture2000", base="HEAD")
    assert "Comparison base:" in summary
    assert "`Fixture2000.Thm_1` | proved;" in summary
    assert "| stated;" in summary
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="Cannot resolve"):
        comparison_nodes(repo, "Fixture2000", "missing-reference")
