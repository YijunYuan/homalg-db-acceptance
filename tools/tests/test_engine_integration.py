"""Task planning, blueprint generation and real ledger write-scope regressions."""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from homalg.blueprint import generate, markdown_tex
from homalg.cli import cli
from homalg.documents import dump_metadata
from homalg.human import HumanApprovalRequired, active_runs
from homalg.planning import plan
from homalg.runtime_state import document_state, overlay_nodes
from homalg.schemas import load_yaml
from homalg.scope import check_scope, human_fields_changed
from homalg.stages import attempt_sessions

ROOT = Path(__file__).resolve().parents[2]


def test_blueprint_has_scoped_external_stubs_and_exact_math(repo: Path) -> None:
    """Only selected docs and their direct upstream stubs enter the generated graph."""
    result = generate(repo, ("Fixture2001",))
    text = result["blueprint/src/content.tex"]
    assert text.count(r"\label{") == 4
    assert r"\label{Fixture2000.Def_1}" in text
    assert "External: Fixture2000" in text
    assert r"\label{Fixture2000.Thm_3}" not in text
    assert result == generate(repo, ("Fixture2001",))
    config = load_yaml(result["hgraph/config.yaml"])
    assert config["lean"] == ["HomAlg/Fixture2000", "HomAlg/Fixture2001"]
    converted = markdown_tex(r"**Theorem.** *Keep* $d_{n+1}(x)=0$ [uses `Fixture2000.Def_1`] & 50%")
    assert r"$d_{n+1}(x)=0$" in converted
    assert r"\textbf{Theorem.}" in converted
    assert r"\ref{Fixture2000.Def_1}" in converted
    assert r"\& 50\%" in converted


def test_runtime_state_reopens_current_source(repo: Path) -> None:
    """Current compiled facts are authoritative; edited files become explicit approximations."""
    (repo / "build").mkdir()
    shutil.copyfile(
        ROOT / "tools/tests/golden/fixture-export.json", repo / "build/lean-export.json"
    )
    before = document_state(repo, "Fixture2000")
    assert len(before["nodes"]) == 15
    assert not before["approx"]
    path = repo / "HomAlg/Fixture2000/Thm_1.lean"
    path.write_text(path.read_text() + "\n-- edited source\n")
    after = document_state(repo, "Fixture2000")
    assert after["approx"]
    overlay = overlay_nodes(after)
    assert overlay["Fixture2000.Thm_1"]["approx"] is True
    assert overlay["Fixture2000.Thm_1"]["headline"] == "in-progress"
    assert overlay["Fixture2000.Def_1"]["approx"] is False


def test_blueprint_preserves_arithmetic_and_literal_code() -> None:
    """Spaced multiplication signs are not Markdown emphasis delimiters."""
    equation = "n * 1 = n * 0 + n"
    assert markdown_tex(equation) == equation
    assert markdown_tex("*Keep* **both words** and *x*.") == (
        r"\emph{Keep} \textbf{both words} and \emph{x}."
    )
    assert markdown_tex("`a*b*c_1` and [uses `Fixture2000.Def_1`]") == (
        r"\texttt{a*b*c\_1} and \ref{Fixture2000.Def_1}"
    )
    assert markdown_tex("** spaced ** and * spaced *") == "** spaced ** and * spaced *"


def test_human_approval_field_detection() -> None:
    """Agent sessions can raise/reopen reports but cannot confirm, resolve or edit old evidence."""
    document = {"foundations": [{"notion": "N", "status": "proposed"}]}
    updated = copy.deepcopy(document)
    updated["foundations"][0].update(status="confirmed", confirmed_by="human")
    assert human_fields_changed(document, updated, document=True)
    assert human_fields_changed(updated, document, document=True)
    assert human_fields_changed({}, {"early_review": {"by": "human"}}, document=True)
    old = {"dispute": {"status": "open", "kind": "proof", "reason": "A gap"}}
    assert not human_fields_changed({}, old)
    assert human_fields_changed(old, {"dispute": {**old["dispute"], "status": "resolved"}})
    resolved = {"dispute": {"status": "resolved", "kind": "proof", "reason": "old"}}
    reopened = {"dispute": old["dispute"], "dispute_history": [resolved["dispute"]]}
    assert not human_fields_changed(resolved, reopened)
    assert human_fields_changed(resolved, {**reopened, "dispute_history": []})
    assert human_fields_changed({}, {"fidelity": {"reviewed": {"kind": "human"}}})


def test_unknown_process_response_fails_closed() -> None:
    """A changed engine output format cannot silently authorize human edits during a run."""
    with pytest.raises(HumanApprovalRequired):
        active_runs({"unexpected": "shape"})
    assert not active_runs({"runs": []})


def test_agent_confirmation_scope_preserves_real_human_evidence() -> None:
    """Opt-in accepts fresh independent records without rewriting actual human history."""
    from homalg.review_policy import foundation_hash

    original = {
        "notion": "Vector spaces",
        "mathlib": ["Module"],
        "justification": "Background",
        "evidence": "Source page 1",
        "status": "proposed",
    }
    review = {
        "kind": "agent",
        "status": "satisfactory",
        "by": "reviewer",
        "on": "2026-10-28",
        "session": "review-session",
        "author_session": "author-session",
        "content_sha256": foundation_hash(original),
    }
    approved = original | {"status": "confirmed", "confirmation": review}
    before, after = {"foundations": [original]}, {"foundations": [approved]}
    assert human_fields_changed(before, after, document=True)
    assert not human_fields_changed(before, after, document=True, allow_agent_reviews=True)
    stale = {"foundations": [approved | {"evidence": "Changed premise"}]}
    assert human_fields_changed(after, stale, document=True, allow_agent_reviews=True)
    human = {"foundations": [original | {"status": "confirmed", "confirmed_by": "actual-human"}]}
    assert human_fields_changed(human, after, document=True, allow_agent_reviews=True)
    assert human_fields_changed({"fidelity": {"reviewed": {"kind": "human"}}}, {})


def make_ledger(repo: Path) -> list[str]:
    """Create a real independent audit repository with only authored input paths."""
    directory = repo / ".archon-horizon/vcs/workspace.git"
    subprocess.run(["git", "init", "--bare", "-q", str(directory)], check=True)
    return [
        "git",
        "--git-dir",
        str(directory),
        "--work-tree",
        str(repo),
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
    ]


def commit(prefix: list[str], repo: Path) -> str:
    """Capture one session snapshot without including the ledger's own state files."""
    subprocess.run([*prefix, "add", "HomAlg", "literature", "taxonomy"], cwd=repo, check=True)
    subprocess.run([*prefix, "commit", "-qm", "fixture"], cwd=repo, check=True)
    return subprocess.run(
        [*prefix, "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_real_ledger_scope_checks_guard_fields_and_allow_known_nodes(repo: Path) -> None:
    """Allowed proof edits survive; human confirmations and foreign-document edits are listed."""
    prefix = make_ledger(repo)
    task_id = "Fixture2000.PROOF.1"
    task_file = repo / ".archon-horizon/tasks/items" / f"{task_id}.yaml"
    task_file.parent.mkdir(parents=True)
    task_file.write_text(
        dump_metadata(
            {
                "id": task_id,
                "metadata": {"homalg": {"doc": "Fixture2000", "stage": "PROOF"}},
                "write_set": {
                    "files": [
                        "HomAlg/Fixture2000/Thm_1.lean",
                        "literature/Fixture2000/document.yaml",
                    ]
                },
            }
        )
    )
    before = commit(prefix, repo)
    path = repo / "HomAlg/Fixture2000/Thm_1.lean"
    path.write_text(path.read_text() + "\n-- proof edit\n")
    allowed = commit(prefix, repo)
    assert check_scope(repo, task_id, before, allowed) == []
    doc = repo / "literature/Fixture2000/document.yaml"
    metadata = load_yaml(doc.read_text())
    metadata["early_review"] = {"by": "fake-human", "on": "2026-10-28"}
    doc.write_text(dump_metadata(metadata))
    other = repo / "HomAlg/Fixture2001/Def_1.lean"
    other.write_text(other.read_text() + "\n-- foreign edit\n")
    after = commit(prefix, repo)
    assert check_scope(repo, task_id, allowed, after) == [
        "HomAlg/Fixture2001/Def_1.lean",
        "literature/Fixture2000/document.yaml",
    ]
    result = CliRunner().invoke(
        cli,
        [
            "scope-check",
            "--task",
            task_id,
            "--since",
            allowed,
            "--until",
            after,
            "--repo",
            str(repo),
        ],
    )
    assert result.exit_code == 4
    assert json.loads(result.output)["violations"] == check_scope(repo, task_id, allowed, after)


def fake_engine(repo: Path, *args: str) -> str:
    """Materialize the engine's documented task/roadmap shards for planning isolation."""
    kind = args[0]
    if kind == "inbox":
        return "I-0001"
    item_id = args[args.index("--id") + 1]
    path = (
        repo
        / ".archon-horizon"
        / ("tasks" if kind == "task" else "roadmap")
        / "items"
        / f"{item_id}.yaml"
    )
    record: dict = {
        "id": item_id,
        "status": "queued" if kind == "task" else "pending",
        "metadata": {},
    }
    if kind == "task":
        record["write_set"] = {
            "files": [args[index + 1] for index, value in enumerate(args) if value == "--file"]
        }
        record["objective"] = args[args.index("--objective") + 1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_metadata(record))
    return item_id


@pytest.mark.parametrize("enabled_at_start", [False, True])
def test_scope_reads_start_policy_and_never_allows_policy_edits(
    repo: Path, enabled_at_start: bool
) -> None:
    """A task cannot authorize itself by writing the live policy inside its interval."""
    prefix = make_ledger(repo)
    task_id = "Fixture2000.E.1"
    policy_path = "horizon/review-policy.yaml"
    document_path = "literature/Fixture2000/document.yaml"
    policy = repo / policy_path
    policy.parent.mkdir()
    policy.write_text(
        dump_metadata({"schema_version": 1, "allow_independent_agent_reviews": enabled_at_start})
    )
    task_path = repo / ".archon-horizon/tasks/items" / f"{task_id}.yaml"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(
        dump_metadata(
            {
                "id": task_id,
                "metadata": {"homalg": {"doc": "Fixture2000", "stage": "E"}},
                "write_set": {"files": [document_path, policy_path]},
            }
        )
    )
    subprocess.run([*prefix, "add", policy_path], cwd=repo, check=True)
    before = commit(prefix, repo)
    document = repo / document_path
    metadata = load_yaml(document.read_text())
    metadata["early_review"] = {
        "kind": "agent",
        "status": "satisfactory",
        "by": "reviewer",
        "on": "2026-10-28",
        "session": "review-session",
        "author_session": "author-session",
    }
    document.write_text(dump_metadata(metadata))
    # Also edit policy in the authorized branch: even a comment is outside task authority.
    policy.write_text("schema_version: 1\nallow_independent_agent_reviews: true\n# changed\n")
    subprocess.run([*prefix, "add", policy_path], cwd=repo, check=True)
    after = commit(prefix, repo)
    expected = [policy_path] if enabled_at_start else [policy_path, document_path]
    assert check_scope(repo, task_id, before, after) == sorted(expected)


def test_plan_is_idempotent_and_preserves_blocked_tasks(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the initial eligible inventory task is created; blocked statuses remain untouched."""
    shutil.copytree(ROOT / "horizon", repo / "horizon")
    monkeypatch.setattr("homalg.planning.horizon", fake_engine)
    first = plan(repo, "Fixture2000", no_claim=True)
    assert first["created_tasks"] == ["Fixture2000.INV.1"]
    path = repo / ".archon-horizon/tasks/items/Fixture2000.INV.1.yaml"
    record = load_yaml(path.read_text())
    assert record["write_set"]["files"] == [
        "literature/Fixture2000/document.yaml",
        "literature/Fixture2000/inventory.yaml",
    ]
    record["status"] = "blocked"
    path.write_text(dump_metadata(record))
    before = path.read_bytes()
    assert plan(repo, "Fixture2000", advance=True)["created_tasks"] == []
    assert path.read_bytes() == before


def test_session_attempts_do_not_count_duplicate_comments() -> None:
    """A proof is not exhausted merely because one session repeated the same attempt."""
    comments = [{"body": "attempt: simp failed", "session": "one"} for _ in range(3)]
    comments.append({"body": "not an attempt", "session": "two"})
    comments.append({"body": "attempt: no provenance", "session": None})
    assert attempt_sessions(comments) == {"one"}


def test_plan_keeps_global_chapter_ids_after_completed_scope(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finishing one scope permits another without recycling old task ids or write sets."""
    shutil.copytree(ROOT / "horizon", repo / "horizon")
    monkeypatch.setattr("homalg.planning.horizon", fake_engine)
    document_path = repo / "literature/Fixture2000/document.yaml"
    document = load_yaml(document_path.read_text())
    document["structure"].append(
        {"chapter": "2", "title": "Second chapter", "pages": {"first": 5, "last": 6}}
    )
    document_path.write_text(dump_metadata(document))
    assert plan(repo, "Fixture2000", chapters=("1",), no_claim=True)["created_tasks"] == [
        "Fixture2000.INV.1"
    ]
    old = repo / ".archon-horizon/tasks/items/Fixture2000.INV.1.yaml"
    record = load_yaml(old.read_text())
    record["status"] = "done"
    old.write_text(dump_metadata(record))
    before = old.read_bytes()
    next_plan = plan(repo, "Fixture2000", chapters=("2",), no_claim=True)
    assert next_plan["created_tasks"] == ["Fixture2000.INV.2"]
    assert old.read_bytes() == before
    new = load_yaml((old.parent / "Fixture2000.INV.2.yaml").read_text())
    assert new["metadata"]["homalg"]["chapter"] == "2"
