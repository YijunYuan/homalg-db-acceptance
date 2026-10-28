"""Compiled checks use genuine export records and targeted adversarial mutations."""

import copy
import json
from pathlib import Path

import pytest

from homalg.checks import RULES
from homalg.checks.context import Context
from homalg.leantext import statement_hashes
from homalg.validate import compiled_context, load_context

PRIMARY = "HomAlg/Fixture2000/Thm_1.lean"
GOLDEN = Path(__file__).parent / "golden/fixture-export.json"


@pytest.fixture
def ctx(repo: Path) -> Context:
    context = load_context(repo)
    compiled_context(context, json.loads(GOLDEN.read_text()))
    return context


def primary(ctx: Context) -> dict:
    return ctx.main_declarations(ctx.valid_headers[PRIMARY])[0]


def test_missing_decl_and_unreported_dependencies(ctx: Context) -> None:
    ctx.valid_headers[PRIMARY].metadata["decls"].append("Fixture2000.absent")
    assert RULES["decls-exist"](ctx)
    ctx.derived["Fixture2000.Thm_1"]["deps_diff"]["verified_not_declared"] = ["Fixture2000.Lem_2"]
    finding = RULES["deps-verified"](ctx)[0]
    assert finding.severity == "warning" and "fix-deps" in finding.fix


def test_route_comparison_and_explicit_deviation(ctx: Context) -> None:
    derived = ctx.derived["Fixture2000.Thm_1"]
    assert "Fixture2000.Lem_2" in derived["verified_deps"]["proof"]
    derived["verified_deps"]["proof"].remove("Fixture2000.Lem_2")
    assert RULES["route-faithful"](ctx)
    ctx.valid_headers[PRIMARY].metadata["fidelity"]["deviations"] = [
        {"kind": "proof-route", "what": "Use arithmetic", "why": "Independent shorter proof"}
    ]
    assert not RULES["route-faithful"](ctx)
    derived["verified_deps"]["statement"] = []
    assert RULES["deps-statement-unused"](ctx)
    derived["local_status"] = "planned"
    assert not RULES["deps-statement-unused"](ctx)


def test_mathlib_bypass_statement_proof_and_missing_lookup(ctx: Context) -> None:
    declaration = primary(ctx)
    counterpart = "Nat.add_zero"
    ctx.valid_headers[PRIMARY].metadata["mathlib"] = {"decls": [counterpart], "relation": "same"}
    declaration["type_uses_external"].append(counterpart)
    assert RULES["mathlib-bypass-statement"](ctx)
    ctx.valid_headers["HomAlg/Fixture2000/Lem_2.lean"].metadata["mathlib"] = {
        "decls": [counterpart],
        "relation": "same",
    }
    declaration["value_uses_external"].append(counterpart)
    assert RULES["mathlib-bypass-proof"](ctx)
    ctx.raw["external_constants"][counterpart] = {"exists": False, "module": None}
    assert RULES["mathlib-decls-exist"](ctx)
    ctx.raw["external_constants"][counterpart] = {"exists": True, "module": "Init.Data.Nat.Basic"}
    assert not RULES["mathlib-decls-exist"](ctx)


def test_registered_document_defers_foundations_until_a_node_exists(ctx: Context) -> None:
    document = copy.deepcopy(ctx.docs["Fixture2000"])
    document["doc_key"] = "Registered2003"
    document["foundations"] = [{"mathlib": ["Unloaded.Foundation"]}]
    ctx.docs["Registered2003"] = document
    ctx.raw["external_constants"]["Unloaded.Foundation"] = {"exists": False, "module": None}
    assert not RULES["mathlib-decls-exist"](ctx)
    first = copy.deepcopy(ctx.valid_headers[PRIMARY])
    first.metadata["doc"] = "Registered2003"
    ctx.all_headers["HomAlg/Registered2003/Thm_1.lean"] = first
    findings = RULES["mathlib-decls-exist"](ctx)
    assert len(findings) == 1
    assert findings[0].file == "literature/Registered2003/document.yaml"
    assert "Unloaded.Foundation" in findings[0].message


def test_registration_only_foundation_coverage_is_explicit(repo: Path) -> None:
    from homalg.schemas import load_yaml
    from homalg.validate import validate_repo

    document = load_yaml((repo / "literature/Fixture2000/document.yaml").read_text())
    document["doc_key"] = "Registered2003"
    document["foundations"][0]["mathlib"] = ["Unloaded.Foundation"]
    destination = repo / "literature/Registered2003"
    destination.mkdir()
    (destination / "document.yaml").write_text(json.dumps(document))
    raw = json.loads(GOLDEN.read_text())
    raw["external_constants"]["Unloaded.Foundation"] = {"exists": False, "module": None}
    findings, skipped, _ = validate_repo(
        repo, only=("mathlib-decls-exist",), export=raw, no_build=True
    )
    assert not findings
    assert "mathlib-decls-exist:Registered2003:no-node-modules" in skipped


def test_packaging_and_kind_detection(ctx: Context) -> None:
    declaration = primary(ctx)
    declaration["packaged_fields"] = [
        {"binder": 0, "structure": "Fixture2000.Pack", "field": "Fixture2000.Pack.conclusion"}
    ]
    findings = RULES["hypothesis-packaging"](ctx)
    assert findings[0].severity == "warning" and "conclusion" in findings[0].message
    for item in ctx.main_declarations(ctx.valid_headers[PRIMARY]):
        item["is_prop"] = False
    assert RULES["kind-decl"](ctx)


def test_hollow_data_requires_reviewed_allowance(ctx: Context) -> None:
    header = ctx.valid_headers["HomAlg/Fixture2000/Def_3.lean"]
    declaration = ctx.main_declarations(header)[0]
    declaration["hollow"] = True
    assert RULES["hollow-def"](ctx)
    path = ctx.repo / "literature/Fixture2000/hollow-allow.yaml"
    path.write_text(
        json.dumps(
            {
                "allowances": [
                    {
                        "node": header.metadata["id"],
                        "reason": "Temporary missing data in a test",
                        "reviewed": {
                            "by": "fictional-reviewer",
                            "on": "2000-01-01",
                            "status": "satisfactory",
                        },
                    }
                ]
            }
        )
    )
    assert not RULES["hollow-def"](ctx)
    path.write_text(path.read_text().replace("satisfactory", "needs-revision"))
    assert RULES["hollow-def"](ctx)
    path.unlink()
    declaration["hollow"] = False
    declaration["direct_sorry"] = True
    assert not RULES["hollow-def"](ctx)


def test_fidelity_source_type_and_semantic_hashes_are_distinct(ctx: Context) -> None:
    header = ctx.valid_headers[PRIMARY]
    hashes = statement_hashes(ctx.sources[PRIMARY])
    locks = {
        item["name"]: {
            "statement_sha256": hashes[item["name"]],
            "type_hash": item["type_hash"],
            "meaning_hash": item["meaning_hash"],
        }
        for item in ctx.main_declarations(header)
    }
    header.metadata["fidelity"]["reviewed"] = {"kind": "agent", "decl_hashes": locks}
    assert not RULES["fidelity-reopened"](ctx)
    saved = copy.deepcopy(primary(ctx))
    primary(ctx)["meaning_hash"] = "1" * 16
    assert RULES["fidelity-reopened"](ctx)[0].severity == "warning"
    primary(ctx)["type_hash"] = "2" * 16
    assert RULES["fidelity-reopened"](ctx)[0].severity == "error"
    primary(ctx).update(saved)
    ctx.sources[PRIMARY] = ctx.sources[PRIMARY].replace(
        "namespace Fixture2000", "namespace Fixture2000\nopen Nat"
    )
    assert RULES["fidelity-reopened"](ctx)[0].severity == "error"


def test_bridge_requires_both_endpoints(ctx: Context) -> None:
    header = ctx.valid_headers["HomAlg/Fixture2000/Bridge_Def_1_mathlib.lean"]
    declaration = ctx.main_declarations(header)[0]
    declaration["type_uses_nodes"] = []
    declaration["value_uses_nodes"] = []
    assert any("parent" in finding.message for finding in RULES["bridge-witness"](ctx))
    declaration["type_uses_nodes"] = [header.metadata["aux"]["parent"]]
    declaration["type_uses_external"] = []
    declaration["value_uses_external"] = []
    assert any("counterpart" in finding.message for finding in RULES["bridge-witness"](ctx))


def test_global_instance_requires_own_document_type(ctx: Context) -> None:
    declaration = primary(ctx)
    declaration.update(kind="instance", is_global_instance=True, instance_type_uses_own_doc=False)
    assert RULES["instance-scope"](ctx)
    declaration["is_global_instance"] = False
    assert not RULES["instance-scope"](ctx)
    declaration["is_global_instance"] = True
    declaration["instance_type_uses_own_doc"] = True
    assert not RULES["instance-scope"](ctx)
    del declaration["is_global_instance"]
    assert RULES["instance-scope"](ctx)
