"""Confirmed source errors settle statement work without fabricated fidelity locks."""

import copy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from homalg import stages
from homalg.runtime_state import document_state
from homalg.status import compute_status

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("stage", ["STMT", "CITED"])
@pytest.mark.parametrize("case", ["confirmed", "unconfirmed", "stale", "invalid"])
def test_disputed_statement_outcomes(repo: Path, monkeypatch, stage: str, case: str) -> None:
    """Only a fresh, valid, confirmed error can advance without satisfactory reviews."""
    (repo / "build").mkdir()
    golden = ROOT / "tools/tests/golden/fixture-export.json"
    shutil.copyfile(golden, repo / "build/lean-export.json")
    shutil.copyfile(golden, repo / "build/lean-export-Fixture2000.json")
    state = copy.deepcopy(document_state(repo, "Fixture2000"))
    node = next(item for item in state["nodes"] if item["id"] == "Fixture2000.Prop_2")
    assert node["global"]["headline"] == "error"
    assert not node["authored"]["fidelity"].get("reviewed")
    if stage == "CITED":
        node["authored"]["cited"] = {
            "source": {"kind": "folklore", "locator": "Synthetic source, page 3"}
        }
    if case == "unconfirmed":
        node["authored"]["dispute"].pop("confirmed_by")
        node["global"]["headline"] = compute_status(node["authored"], node["derived"], {}, [])[1]
    elif case == "stale":
        node["approx"] = True
    monkeypatch.setattr(stages, "document_state", lambda *_: state)
    validation = (
        [SimpleNamespace(severity="error", rule="source-dispute", message="invalid evidence")]
        if case == "invalid"
        else []
    )
    monkeypatch.setattr(stages, "validate_repo", lambda *args, **kwargs: (validation, {}, {}))
    record = {
        "id": "STMT.1",
        "metadata": {"homalg": {"doc": "Fixture2000", "stage": stage}},
        "write_set": {"files": ["HomAlg/Fixture2000/Prop_2.lean"]},
    }
    result = stages.evaluate(repo, record, refresh_exports=False)
    assert result["complete"] is (case == "confirmed")
    if case == "unconfirmed":
        assert any("statement lock" in failure for failure in result["failures"])
    elif case == "stale":
        assert any("fresh main declarations" in failure for failure in result["failures"])
    elif case == "invalid":
        assert any("invalid evidence" in failure for failure in result["failures"])
