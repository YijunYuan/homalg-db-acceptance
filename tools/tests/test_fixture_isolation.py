"""New synthetic documents cannot silently change the fixed golden test corpus."""

from pathlib import Path

from fixture_support import BASELINE_DOCUMENTS, copy_baseline_repository

from homalg.validate import validate_repo


def test_new_fixture_does_not_pollute_baseline_but_known_changes_survive(repo: Path) -> None:
    """Ignore unrelated acceptance inputs; retain and detect errors in the baseline."""
    for directory in ("HomAlg", "literature"):
        extra = repo / directory / "Fixture2099"
        extra.mkdir()
        (extra / "invalid.txt").write_text("Deliberately not a valid document or node.")
    destination = repo / "isolated"
    copy_baseline_repository(repo, destination)
    for directory in ("HomAlg", "literature"):
        assert {p.name for p in (destination / directory).iterdir() if p.is_dir()} == set(
            BASELINE_DOCUMENTS
        )
    findings, _, counts = validate_repo(destination)
    assert not findings
    assert counts == {"documents": 2, "nodes": 17}

    path = repo / "HomAlg/Fixture2000/Rem_1.lean"
    path.write_text(path.read_text().replace("## Statement", "## MissingStatement"))
    broken = repo / "broken"
    copy_baseline_repository(repo, broken)
    assert (broken / path.relative_to(repo)).read_bytes() == path.read_bytes()
    findings, _, _ = validate_repo(broken)
    assert any(finding.file == "HomAlg/Fixture2000/Rem_1.lean" for finding in findings)
