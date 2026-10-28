"""Opt-in compiled acceptance for the source-faithful Hochschild §§1–3 pilot."""

import os
from pathlib import Path

import pytest

from homalg.headers import parse_header
from homalg.leanexport import declaration_map, export_lean, run_tool, workspace_lock

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.environ.get("HOMALG_LEAN_TESTS") != "1",
    reason="Set HOMALG_LEAN_TESTS=1 to inspect the compiled historical pilot",
)
KERNEL_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    """Rebuild actual document modules without changing authored or committed derived records."""
    path = tmp_path_factory.mktemp("pilot-export") / "raw.json"
    return declaration_map(export_lean(REPO, "Hochschild1945", path, merge=False))


def test_first_three_sections_have_actual_closed_proofs(compiled: dict) -> None:
    """Every principal declaration is real and free of direct/transitive sorry or extra axioms."""
    source_count = 0
    for path in (REPO / "HomAlg/Hochschild1945").glob("*.lean"):
        header = parse_header(path.read_text()).metadata
        if header["source"].get("chapter") not in {"1", "2", "3"}:
            continue
        if "aux" not in header and "cited" not in header:
            source_count += 1
        assert header["decls"], path
        records = compiled[f"HomAlg.{header['id']}"]
        for name in header["decls"]:
            declaration = records[name]
            assert not declaration["direct_sorry"], name
            assert not declaration["transitive_sorry"], name
            assert not declaration["hollow"], name
            assert set(declaration["axioms"]) <= KERNEL_AXIOMS, name
    assert source_count == 12


def test_source_proof_route_and_real_bridge_endpoints_are_compiled(compiled: dict) -> None:
    """Source currying and square-zero evidence survive export; bridges use both endpoints."""
    square = compiled["HomAlg.Hochschild1945.Lem_delta_delta_zero"][
        "Hochschild1945.delta_delta_zero"
    ]
    assert {"Hochschild1945.Con_bar_map", "Hochschild1945.Prop_1_1"} <= set(
        square["value_uses_nodes"]
    )
    shift = compiled["HomAlg.Hochschild1945.Thm_3_1"]["Hochschild1945.fundamental_isomorphism"]
    dependencies = set(shift["type_uses_nodes"]) | set(shift["value_uses_nodes"])
    assert {"Hochschild1945.Def_2_3", "Hochschild1945.Con_bar_map"} <= dependencies
    for local, name, external in (
        ("Bridge_Def_cochain_mathlib", "cochain_multilinear_equivalence", "MultilinearMap"),
        ("Bridge_Def_two_sided_module_mathlib", "two_sided_module_bridge", "NonUnitalAlgHom"),
        ("Bridge_Def_separable_mathlib", "basisExtension_tensor_equivalence", "TensorProduct"),
    ):
        declaration = compiled[f"HomAlg.Hochschild1945.{local}"][f"Hochschild1945.{name}"]
        assert not declaration["direct_sorry"], name
        assert not declaration["transitive_sorry"], name
        assert not declaration["hollow"], name
        assert set(declaration["axioms"]) <= KERNEL_AXIOMS, name
        assert (
            external in declaration["type_uses_external"]
            or external in declaration["value_uses_external"]
        )


def test_source_module_allows_nonunital_actions(tmp_path: Path) -> None:
    """The original module definition permits both identity actions to be zero."""
    source = tmp_path / "NonunitalAcceptance.lean"
    source.write_text(
        """import HomAlg.Hochschild1945.Bridge_Def_two_sided_module_mathlib
import HomAlg.Hochschild1945.Def_2_1

open Hochschild1945

def zeroAction : TwoSidedModule ℚ ℚ ℚ where
  left := 0
  right := 0
  left_assoc := by intros; simp
  right_assoc := by intros; simp
  left_right := by intros; simp

example : (moduleToMathlib zeroAction).left (1 : ℚ) = 0 := rfl
example : (moduleToMathlib zeroAction).right (MulOpposite.op (1 : ℚ)) = 0 := rfl
example (p : ℚ) : delta zeroAction 0 p = 0 := by
  rw [delta]
  apply LinearMap.ext
  intro a
  change (0 : ℚ) - 0 = 0
  exact sub_self 0
"""
    )
    with workspace_lock(REPO):
        run_tool(
            REPO, ["lake", "build", "HomAlg.Hochschild1945.Bridge_Def_two_sided_module_mathlib"]
        )
        run_tool(REPO, ["lake", "env", "lean", str(source)])


def test_source_dispute_has_a_closed_counterexample_witness(compiled: dict) -> None:
    """The primitive-dependence objection is a proved source-delta witness, not an axiom."""
    declaration = compiled["HomAlg.Hochschild1945.Aux_Thm_5_1_counterexample"][
        "Hochschild1945.Counterexample5.primitive_dependence"
    ]
    assert not declaration["direct_sorry"]
    assert not declaration["transitive_sorry"]
    assert not declaration["hollow"]
    assert set(declaration["axioms"]) <= KERNEL_AXIOMS
    assert "Hochschild1945.Lem_delta_delta_zero" in declaration["value_uses_nodes"]
    assert "Hochschild1945.Thm_5_1" not in declaration["value_uses_nodes"]


def test_natural_restriction_uses_closed_source_cochain_proofs(compiled: dict) -> None:
    """All-degree restriction and its actual quotient map are independent of disputed §5.1."""
    records = compiled["HomAlg.Hochschild1945.Def_natural_homomorphism"]
    for name in ("naturalHomomorphism", "restrictCochain_delta", "restrict_boundaries"):
        declaration = records[f"Hochschild1945.{name}"]
        assert not declaration["direct_sorry"], name
        assert not declaration["transitive_sorry"], name
        assert not declaration["hollow"], name
        assert set(declaration["axioms"]) <= KERNEL_AXIOMS, name
        assert "Hochschild1945.Thm_5_1" not in declaration["value_uses_nodes"]
    assert (
        "Hochschild1945.Aux_Def_2_1_formula"
        in records["Hochschild1945.restrictCochain_delta"]["value_uses_nodes"]
    )
