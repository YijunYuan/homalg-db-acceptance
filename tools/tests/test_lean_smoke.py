"""Source-fixture consistency and opt-in checks against the actual Lean environment."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fixture_support import BASELINE_DOCUMENTS

from homalg.headers import parse_header
from homalg.leanexport import workspace_lock

REPO = Path(__file__).resolve().parents[2]
LEAN_ENABLED = os.environ.get("HOMALG_LEAN_TESTS") == "1"
requires_lean = pytest.mark.skipif(
    not LEAN_ENABLED, reason="Set HOMALG_LEAN_TESTS=1 to build and inspect Lean fixtures"
)


def run_lean(*args: str, timeout: int = 300) -> str:
    """Run a Lake command and preserve build diagnostics on assertion failure."""
    with workspace_lock(REPO):
        result = subprocess.run(
            ["lake", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout
        )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def parse_export(text: str) -> dict[str, dict[str, Any]]:
    """Flatten JSON declarations for the fixture assertions below."""
    raw = json.loads(text)
    parsed = {
        declaration["name"]: declaration | {"module": module["module"]}
        for module in raw["modules"]
        for declaration in module["decls"]
    }
    assert parsed, "The exporter returned no declarations"
    return parsed


@pytest.fixture(scope="module")
def exports() -> dict[str, dict[str, dict[str, Any]]]:
    """Compile the package once, then load each document root independently."""
    run_lean("build", timeout=600)
    return {
        doc: parse_export(
            run_lean("exe", "homalg-export", "--root", f"HomAlg.{doc}", "--prefix", f"HomAlg.{doc}")
        )
        for doc in BASELINE_DOCUMENTS
    }


def test_fixture_statements_and_proofs_match_their_source_pages() -> None:
    """A fixture's authored statement and proof must quote its own paginated source."""
    for path in sorted(
        path for key in BASELINE_DOCUMENTS for path in (REPO / "HomAlg" / key).glob("*.lean")
    ):
        header = parse_header(path.read_text())
        if "aux" in header.metadata:
            continue
        doc = header.metadata["doc"]
        source = (REPO / "docs" / "fixtures" / f"{doc}.md").read_text()
        page = header.metadata["source"]["pages"][0]
        page_text = source.split(f"<!-- page {page} -->", 1)[1].split("<!-- page ", 1)[0]
        label = re.escape(header.metadata["source"]["label"])
        block = re.search(rf"(?ms)^## {label}\n\n(.*?)(?=^## |\Z)", page_text)
        assert block is not None, path
        statement, separator, proof = block.group(1).strip().partition("\n\nProof. ")
        assert header.sections["Statement"] == statement.strip(), path
        if separator:
            assert header.sections["Proof"] == proof.strip(), path
        else:
            assert "Proof" not in header.sections, path


@requires_lean
def test_exports_real_definitions_and_eq_names(
    exports: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """User names beginning with eq_ survive filtering; aliases retain their kind."""
    records = exports["Fixture2000"]
    assert records["Fixture2000.ChainComplexToy"]["kind"] == "structure"
    assert records["Fixture2000.ChainComplexToy.degree"]["kind"] == "projection"
    assert records["Fixture2000.AbelianGroup"]["kind"] == "abbrev"
    assert records["Fixture2000.eq_degree_zero"]["kind"] == "theorem"
    assert records["Fixture2000.eq_degree_zero"]["direct_sorry"] is False
    assert records["Fixture2000.zeroComplex"]["hollow"] is False
    assert records["Fixture2000.zeroComplex"]["direct_sorry"] is False


@requires_lean
def test_separate_file_sorry_and_citation_propagation(
    exports: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """A completed proof depending on another node's sorry is not a direct sorry."""
    records = exports["Fixture2000"]
    lemma = records["Fixture2000.degree_le_mul_one"]
    assert lemma["direct_sorry"] is lemma["transitive_sorry"] is True
    theorem = records["Fixture2000.degree_le_mul_one_add_zero"]
    assert theorem["direct_sorry"] is False
    assert theorem["transitive_sorry"] is True
    assert theorem["value_uses_nodes"] == ["Fixture2000.Lem_1"]
    cited = records["Fixture2000.degree_mul_comm"]
    assert cited["direct_sorry"] is False
    assert cited["transitive_sorry"] is True
    assert cited["value_uses_nodes"] == ["Fixture2000.Cited_mul_comm"]


@requires_lean
def test_cross_document_dependencies_survive_prefix_filter(
    exports: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """Prefix filtering limits exported declarations, not recognized dependencies."""
    records = exports["Fixture2001"]
    assert all(name.startswith("Fixture2001.") for name in records)
    theorem = records["Fixture2001.degree_add_zero"]
    assert theorem["module"] == "HomAlg.Fixture2001.Thm_1"
    assert theorem["value_uses_nodes"] == ["Fixture2000.Thm_1"]
    assert "Fixture2000.Def_1" in theorem["type_uses_nodes"]
    assert theorem["direct_sorry"] is theorem["transitive_sorry"] is False


@requires_lean
def test_native_decide_has_a_nonstandard_axiom(
    exports: dict[str, dict[str, dict[str, Any]]], tmp_path: Path
) -> None:
    """Inspect the real axiom set rather than assuming an obsolete compiler name."""
    theorem = exports["Fixture2000"]["Fixture2000.two_add_two"]
    assert theorem["direct_sorry"] is theorem["transitive_sorry"] is False
    source = tmp_path / "Axioms.lean"
    source.write_text("import HomAlg.Fixture2000.Thm_2\n#print axioms Fixture2000.two_add_two\n")
    output = run_lean("env", "lean", str(source))
    match = re.search(r"depends on axioms: \[([^]]*)\]", output)
    assert match is not None, output
    axioms = {name.strip() for name in match.group(1).split(",") if name.strip()}
    assert "sorryAx" not in axioms
    assert axioms - {"propext", "Classical.choice", "Quot.sound"}
