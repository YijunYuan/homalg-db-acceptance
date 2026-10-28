"""Compiled export regressions and deterministic local/global data-boundary tests."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from homalg import leanexport
from homalg.extract import extract_document
from homalg.headers import parse_header
from homalg.io import atomic_write, json_text
from homalg.leanexport import ExternalToolError, declaration_map, export_lean, local_derived
from homalg.schemas import SchemaStore

REPO = Path(__file__).resolve().parents[2]
requires_lean = pytest.mark.skipif(
    os.environ.get("HOMALG_LEAN_TESTS") != "1",
    reason="Set HOMALG_LEAN_TESTS=1 for compiled regressions",
)


def raw_declaration(**changes: Any) -> dict[str, Any]:
    """A schema-valid isolated record for testing the merge contract."""
    return {
        "name": "Fixture2000.ChainComplexToy",
        "kind": "structure",
        "type": "Type",
        "type_hash": "0000000000000001",
        "meaning_hash": "0000000000000002",
        "is_prop": False,
        "hollow": False,
        "direct_sorry": False,
        "transitive_sorry": True,
        "axioms": ["sorryAx"],
        "type_uses_nodes": [],
        "value_uses_nodes": [],
        "type_uses_external": [],
        "value_uses_external": [],
        "type_uses_external_truncated": False,
        "value_uses_external_truncated": False,
    } | changes


def minimal_raw(declaration: dict[str, Any]) -> dict[str, Any]:
    """An export of a document root and its single node, as returned by Lean."""
    return {
        "generator": {"name": "homalg-export", "version": "2"},
        "toolchain": "leanprover/lean4:v4.35.0",
        "mathlib_rev": "v4.35.0",
        "modules": [
            {"module": "HomAlg.Fixture2000", "node_id": None, "decls": []},
            {
                "module": "HomAlg.Fixture2000.Def_1",
                "node_id": "Fixture2000.Def_1",
                "decls": [declaration],
            },
        ],
    }


@pytest.fixture
def small_repo(tmp_path: Path) -> Path:
    """An independent authored checkout with no executable toolchain or global state."""
    shutil.copytree(REPO / "schema", tmp_path / "schema")
    (tmp_path / "HomAlg/Fixture2000").mkdir(parents=True)
    (tmp_path / "literature/Fixture2000").mkdir(parents=True)
    for relative in (
        "lakefile.toml",
        "lean-toolchain",
        "HomAlg/Fixture2000/Def_1.lean",
        "literature/Fixture2000/document.yaml",
    ):
        shutil.copy2(REPO / relative, tmp_path / relative)
    (tmp_path / "HomAlg/Fixture2000.lean").write_text("import HomAlg.Fixture2000.Def_1\n")
    return tmp_path


def test_local_records_exclude_global_axioms_and_packaging_evidence() -> None:
    """Import-closure changes must not invalidate another document's committed JSON."""
    path = REPO / "HomAlg/Fixture2000/Def_1.lean"
    content = path.read_bytes()
    header = parse_header(content.decode()).metadata
    declaration = raw_declaration(
        packaged_fields=[{"binder": 0, "structure": "Package", "field": "Package.proof"}],
        is_global_instance=True,
        instance_type_uses_own_doc=True,
    )
    derived = local_derived(
        "HomAlg/Fixture2000/Def_1.lean", content, header, {declaration["name"]: declaration}
    )
    assert derived["local_status"] == "proved"
    local = derived["decl_info"][0]
    for key in (
        "axioms",
        "transitive_sorry",
        "packaged_fields",
        "is_global_instance",
        "instance_type_uses_own_doc",
    ):
        assert key not in local
    assert local["type_sha256"] == hashlib.sha256(b"Type").hexdigest()
    assert derived["file"]["sha256"] == hashlib.sha256(content).hexdigest()
    declaration["axioms"] = []
    declaration["transitive_sorry"] = False
    assert derived == local_derived(
        "HomAlg/Fixture2000/Def_1.lean", content, header, {declaration["name"]: declaration}
    )


def test_definition_values_are_statement_dependencies_and_missing_primaries_are_planned() -> None:
    """A definition's body is part of its statement; proofs use a disjoint dependency set."""
    header = {
        "decls": ["Fixture2000.data", "Fixture2000.result"],
        "deps": {"statement": ["Fixture2000.Def_1"], "proof": ["Fixture2000.Lem_1"]},
    }
    data = raw_declaration(name="Fixture2000.data", value_uses_nodes=["Fixture2000.Def_1"])
    theorem = raw_declaration(
        name="Fixture2000.result",
        is_prop=True,
        kind="theorem",
        value_uses_nodes=["Fixture2000.Def_1", "Fixture2000.Lem_1"],
        direct_sorry=True,
    )
    records = {item["name"]: item for item in (data, theorem)}
    derived = local_derived(
        "test.lean", b"-- sorry in a comment\ntheorem result := sorry\n", header, records
    )
    assert derived["local_status"] == "stated"
    assert derived["verified_deps"] == header["deps"]
    assert derived["sorry_count_text"] == 1
    assert derived["deps_diff"]["verified_not_declared"] == []
    del records[theorem["name"]]
    assert local_derived("test.lean", b"", header, records)["local_status"] == "planned"


def test_export_preserves_authored_records_and_is_byte_reproducible(
    small_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export command updates derived data only, and extraction commutes with it."""
    schemas = SchemaStore(small_repo / "schema")
    original = extract_document(small_repo, "Fixture2000", schemas)
    original["nodes"][0]["authored"]["title"] = "Preserved authored title"
    target = small_repo / "literature/Fixture2000/nodes.json"
    atomic_write(target, json_text(original))
    raw = minimal_raw(raw_declaration())
    calls: list[list[str]] = []

    def fake_run(repo: Path, command: list[str]) -> str:
        assert repo == small_repo
        calls.append(command)
        return "" if command[1] == "build" else json_text(raw)

    monkeypatch.setattr(leanexport, "run_tool", fake_run)
    assert export_lean(small_repo, "Fixture2000") == raw
    exported = json.loads(target.read_text())
    assert exported["nodes"][0]["authored"] == original["nodes"][0]["authored"]
    assert exported["nodes"][0]["derived"]["local_status"] == "proved"
    before = target.read_bytes()
    export_lean(small_repo, "Fixture2000")
    assert target.read_bytes() == before
    assert "HomAlg" not in calls[0]
    assert "HomAlg.Fixture2000.Def_1" in calls[0]
    assert "--check-constants" in calls[1]
    exported_then_extracted = extract_document(small_repo, "Fixture2000", schemas)
    atomic_write(target, json_text(extract_document(small_repo, "Fixture2000", schemas)))
    export_lean(small_repo, "Fixture2000")
    assert json.loads(target.read_text()) == exported_then_extracted


def test_module_list_includes_orphans_without_library_root(small_repo: Path) -> None:
    """Unreferenced auxiliary/cited files must still be built and exported."""
    directory = small_repo / "HomAlg/Fixture2000"
    (directory / "Aux_Def_1_unused.lean").write_text("")
    (directory / "Cited_unused.lean").write_text("")
    assert leanexport.module_list(small_repo, ["Fixture2000"]) == [
        "HomAlg.Fixture2000",
        "HomAlg.Fixture2000.Aux_Def_1_unused",
        "HomAlg.Fixture2000.Cited_unused",
        "HomAlg.Fixture2000.Def_1",
    ]


def test_export_rejects_missing_modules_and_does_not_write_partial_results(
    small_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A syntactically valid but incomplete export cannot masquerade as planned nodes."""
    raw = minimal_raw(raw_declaration())
    raw["modules"] = raw["modules"][:1]
    monkeypatch.setattr(leanexport, "run_tool", lambda *_: json_text(raw))
    with pytest.raises(ValueError, match="omitted requested modules"):
        export_lean(small_repo)
    assert not (small_repo / "literature/Fixture2000/nodes.json").exists()
    assert not (small_repo / "build/lean-export.json").exists()


def test_concurrent_source_edit_invalidates_export(
    small_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compiled export must never be labeled with a later source file's hash."""
    raw = minimal_raw(raw_declaration())

    def edit_during_export(_repo: Path, command: list[str]) -> str:
        if command[1] == "exe":
            path = small_repo / "HomAlg/Fixture2000/Def_1.lean"
            path.write_text(path.read_text() + "\n-- Concurrent edit.\n")
        return json_text(raw)

    monkeypatch.setattr(leanexport, "run_tool", edit_during_export)
    with pytest.raises(ValueError, match="sources changed"):
        export_lean(small_repo)
    assert not (small_repo / "literature/Fixture2000/nodes.json").exists()


def test_duplicate_declarations_and_external_failures_are_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate names cannot be silently overwritten, and build errors retain context."""
    raw = minimal_raw(raw_declaration())
    raw["modules"][0]["decls"] = copy.deepcopy(raw["modules"][1]["decls"])
    with pytest.raises(ValueError, match="Duplicate exported declaration"):
        declaration_map(raw)
    error = ExternalToolError(["lake", "build"], "environment already contains 'Duplicate'", 1)
    assert error.rule == "decl-unique"

    def fail(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 9, "build stdout", "build stderr")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(ExternalToolError, match="build stdoutbuild stderr") as caught:
        leanexport.run_tool(REPO, ["lake", "build"])
    assert caught.value.returncode == 9


REGRESSION_SOURCES = {
    "Def_1": """namespace Fixture2099
/-- A definition whose body belongs to a dependent statement's semantic closure. -/
def Meaning : Nat := 1
/-- A proposition packaged into a structure parameter. -/
structure Pack (n : Nat) where
  conclusion : n = n
/-- Inherited proof fields also participate in packaging checks. -/
structure ChildPack (n : Nat) extends Pack n where
  extra : Nat
/-- A class for kind and instance-scope mapping. -/
class ToyClass (α : Type) where
  value : α
/-- A global instance whose type is owned by this document. -/
instance instToyNat : ToyClass Nat := ⟨0⟩
/-- A scoped instance, deliberately inactive in the importing environment. -/
scoped instance instToyBool : ToyClass Bool := ⟨true⟩
end Fixture2099
""",
    "Lem_1": """namespace Fixture2099
/-- An unfinished theorem, with induction as the intended natural-language proof. -/
theorem unfinished (n : Nat) : n = n := by sorry
/-- A same-file use still counts as direct sorry. -/
theorem same_file (n : Nat) : n = n := unfinished n
/-- A nested proof obligation is not missing data. -/
def nested_proof (n : Nat) : {m : Nat // m = n} := ⟨n, by sorry⟩
/-- A term-mode proof obligation is not missing data. -/
def term_proof (n : Nat) : {m : Nat // m = n} := ⟨n, sorry⟩
/-- This is deliberately hollow negative-fixture data. -/
def hollow_data : Nat := sorry
/-- A same-module data helper must not hide hollow data. -/
def hidden_hollow : Nat := hollow_data
/-- An unfinished type for testing type-side direct sorry. -/
def unfinished_type : Type := sorry
/-- The proof is present but its type uses a same-file sorry. -/
theorem type_side (_x : unfinished_type) : True := True.intro
end Fixture2099
""",
    "Thm_1": """import HomAlg.Fixture2099.Def_1
import HomAlg.Fixture2099.Lem_1
namespace Fixture2099
/-- An unchanged type can depend on a changing definition body. -/
theorem uses_meaning : Meaning = Meaning := rfl
/-- Structure field types are part of the referenced meaning. -/
theorem uses_pack : Pack 0 = Pack 0 := rfl
/-- This structure field is precisely the theorem's conclusion. -/
theorem packaged (n : Nat) (p : Pack n) : n = n := p.conclusion
/-- Packaging through an inherited field is still packaging. -/
theorem child_packaged (n : Nat) (p : ChildPack n) : n = n := p.conclusion
/-- A different-file sorry propagates transitively, not directly. -/
theorem other_file (n : Nat) : n = n := unfinished n
/-- A legitimate user name beginning with eq_. -/
theorem eq_legal (n : Nat) : n = n := rfl
end Fixture2099
""",
}


def compile_module(workspace: Path, module: str) -> None:
    """Compile detached regression sources with the pinned installed Lean, without Lake updates."""
    relative = Path(*module.split("."))
    environment = dict(os.environ, LEAN_PATH=str(workspace))
    result = subprocess.run(
        ["lean", "-o", str(relative.with_suffix(".olean")), str(relative.with_suffix(".lean"))],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def export_regression(workspace: Path) -> dict[str, Any]:
    """Run the actual exporter on an isolated module list, with no library root olean."""
    modules = sorted((workspace / "HomAlg/Fixture2099").glob("*.lean"))
    (workspace / "modules.txt").write_text(
        "".join(f"HomAlg.Fixture2099.{path.stem}\n" for path in modules)
    )
    (workspace / "constants.txt").write_text("Nat\nFixture2099.Meaning\nNotARealDeclaration\n")
    result = subprocess.run(
        [
            str(REPO / ".lake/build/bin/homalg-export"),
            "--modules",
            "modules.txt",
            "--prefix",
            "HomAlg.Fixture2099",
            "--check-constants",
            "constants.txt",
            "--out",
            "export.json",
        ],
        cwd=workspace,
        env=dict(os.environ, LEAN_PATH=str(workspace)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = (workspace / "export.json").read_text()
    raw = json.loads(text)
    assert text == json_text(raw)
    assert not SchemaStore(REPO / "schema").validate(raw, "lean-export.schema.json")
    return raw


def flat(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index declarations from raw JSON for semantic assertions."""
    return {decl["name"]: decl for module in raw["modules"] for decl in module["decls"]}


@pytest.fixture
def regression_workspace(tmp_path: Path) -> Path:
    """Write only disposable negative Lean fixtures outside the project library."""
    (tmp_path / "HomAlg/Fixture2099").mkdir(parents=True)
    shutil.copy2(REPO / "lean-toolchain", tmp_path / "lean-toolchain")
    (tmp_path / "lake-manifest.json").write_text(
        json_text({"packages": [{"name": "mathlib", "inputRev": "v4.35.0"}]})
    )
    for local, source in REGRESSION_SOURCES.items():
        (tmp_path / f"HomAlg/Fixture2099/{local}.lean").write_text(source)
        compile_module(tmp_path, f"HomAlg.Fixture2099.{local}")
    return tmp_path


@requires_lean
def test_real_hollow_detection_and_same_module_closure(regression_workspace: Path) -> None:
    """Labelled/nested proof sorry is not data; named helpers and type-side sorry are followed."""
    records = flat(export_regression(regression_workspace))
    for name in ("nested_proof", "term_proof"):
        assert records[f"Fixture2099.{name}"]["direct_sorry"] is True
        assert records[f"Fixture2099.{name}"]["hollow"] is False
    for name in ("hollow_data", "hidden_hollow"):
        assert records[f"Fixture2099.{name}"]["hollow"] is True
    assert records["Fixture2099.same_file"]["direct_sorry"] is True
    assert records["Fixture2099.type_side"]["direct_sorry"] is True
    assert records["Fixture2099.other_file"]["direct_sorry"] is False
    assert records["Fixture2099.other_file"]["transitive_sorry"] is True
    assert records["Fixture2099.other_file"]["value_uses_nodes"] == ["Fixture2099.Lem_1"]
    assert records["Fixture2099.eq_legal"]["kind"] == "theorem"


@requires_lean
def test_real_packaging_instances_and_unused_constant_lookup(regression_workspace: Path) -> None:
    """Compiler metadata distinguishes global/scoped instances and finds packaged conclusions."""
    raw = export_regression(regression_workspace)
    records = flat(raw)
    assert records["Fixture2099.packaged"]["packaged_fields"] == [
        {"binder": 1, "structure": "Fixture2099.Pack", "field": "Fixture2099.Pack.conclusion"}
    ]
    assert records["Fixture2099.child_packaged"]["packaged_fields"] == [
        {"binder": 1, "structure": "Fixture2099.ChildPack", "field": "Fixture2099.Pack.conclusion"}
    ]
    assert records["Fixture2099.ToyClass"]["kind"] == "class"
    assert records["Fixture2099.instToyNat"]["kind"] == "instance"
    assert records["Fixture2099.instToyNat"]["is_global_instance"] is True
    assert records["Fixture2099.instToyNat"]["instance_type_uses_own_doc"] is True
    assert records["Fixture2099.instToyBool"]["kind"] == "instance"
    assert records["Fixture2099.instToyBool"]["is_global_instance"] is False
    assert raw["external_constants"]["Nat"]["exists"] is True
    assert raw["external_constants"]["Fixture2099.Meaning"]["module"] == "HomAlg.Fixture2099.Def_1"
    assert raw["external_constants"]["NotARealDeclaration"] == {"exists": False, "module": None}


@requires_lean
def test_real_meaning_hash_tracks_definition_bodies_and_structure_fields(
    regression_workspace: Path,
) -> None:
    """A dependent statement's type hash stays fixed while its semantic hash reopens."""
    before = flat(export_regression(regression_workspace))
    path = regression_workspace / "HomAlg/Fixture2099/Def_1.lean"
    path.write_text(path.read_text().replace("Meaning : Nat := 1", "Meaning : Nat := 2"))
    compile_module(regression_workspace, "HomAlg.Fixture2099.Def_1")
    compile_module(regression_workspace, "HomAlg.Fixture2099.Thm_1")
    after = flat(export_regression(regression_workspace))
    name = "Fixture2099.uses_meaning"
    assert before[name]["type_hash"] == after[name]["type_hash"]
    assert before[name]["meaning_hash"] != after[name]["meaning_hash"]
    path.write_text(path.read_text().replace("conclusion : n = n", "conclusion : n + 0 = n"))
    compile_module(regression_workspace, "HomAlg.Fixture2099.Def_1")
    compile_module(regression_workspace, "HomAlg.Fixture2099.Thm_1")
    changed_field = flat(export_regression(regression_workspace))
    name = "Fixture2099.uses_pack"
    assert after[name]["type_hash"] == changed_field[name]["type_hash"]
    assert after[name]["meaning_hash"] != changed_field[name]["meaning_hash"]


@requires_lean
def test_real_external_dependency_lists_are_sorted_and_bounded(regression_workspace: Path) -> None:
    """Both external lists report truncation when more than 200 distinct constants are used."""
    (regression_workspace / "External").mkdir()
    external = (
        "namespace External\n"
        + "\n".join(f"def c{i} : Nat := {i}\ndef P{i} : Prop := True" for i in range(205))
        + "\nend External\n"
    )
    (regression_workspace / "External/Many.lean").write_text(external)
    compile_module(regression_workspace, "External.Many")
    source = "import External.Many\nnamespace Fixture2099\n"
    source += (
        "def external_value : Nat := " + " + ".join(f"External.c{i}" for i in range(205)) + "\n"
    )
    source += "theorem external_type " + " ".join(f"(_h{i} : External.P{i})" for i in range(205))
    source += " : True := True.intro\nend Fixture2099\n"
    (regression_workspace / "HomAlg/Fixture2099/Thm_2.lean").write_text(source)
    compile_module(regression_workspace, "HomAlg.Fixture2099.Thm_2")
    records = flat(export_regression(regression_workspace))
    for name, side in (("external_value", "value"), ("external_type", "type")):
        declaration = records[f"Fixture2099.{name}"]
        values = declaration[f"{side}_uses_external"]
        assert len(values) == 200
        assert values == sorted(set(values))
        assert declaration[f"{side}_uses_external_truncated"] is True


@requires_lean
def test_fixture_json_golden_and_proved_helper_dependency(tmp_path: Path) -> None:
    """The pinned production fixtures define the real exporter compatibility snapshot."""
    keys = ["Fixture2000", "Fixture2001"]
    modules = leanexport.module_list(REPO, keys)
    modules_file = tmp_path / "modules.txt"
    modules_file.write_text("\n".join(modules) + "\n")
    schemas = SchemaStore(REPO / "schema")
    constants_file = tmp_path / "constants.txt"
    constants_file.write_text("\n".join(leanexport.check_constants(REPO, keys, schemas)) + "\n")
    with leanexport.workspace_lock(REPO):
        leanexport.run_tool(REPO, ["lake", "build", "homalg-export", *modules])
        raw = json.loads(
            leanexport.run_tool(
                REPO,
                [
                    "lake",
                    "exe",
                    "homalg-export",
                    "--modules",
                    str(modules_file),
                    "--check-constants",
                    str(constants_file),
                    "--prefix",
                    "HomAlg",
                ],
            )
        )
    assert not schemas.validate(raw, "lean-export.schema.json")
    expected = json.loads((REPO / "tools/tests/golden/fixture-export.json").read_text())
    assert raw == expected
    records = flat(raw)
    assert records["Fixture2000.degree_add_zero"]["value_uses_nodes"] == ["Fixture2000.Lem_2"]
    assert records["Fixture2000.eq_degree_zero"]["value_uses_nodes"] == ["Fixture2000.Lem_2"]
    assert any(module["node_id"] == "Fixture2000.Aux_Thm_1_step" for module in raw["modules"])
    assert records["Fixture2001.PointedToyComplex"]["type_uses_nodes"] == ["Fixture2000.Def_1"]


@requires_lean
def test_real_orphan_declaration_collision_identifies_both_modules(
    regression_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Individually compilable orphan nodes cannot introduce duplicate environment names."""
    modules = ["HomAlg.Fixture2099.Aux_A", "HomAlg.Fixture2099.Aux_B"]
    for index, module in enumerate(modules):
        source = regression_workspace / Path(*module.split(".")).with_suffix(".lean")
        source.write_text(
            f"namespace Fixture2099\ndef collision : Nat := {index}\nend Fixture2099\n"
        )
        compile_module(regression_workspace, module)
    monkeypatch.setenv("LEAN_PATH", str(regression_workspace))
    with pytest.raises(ExternalToolError) as caught:
        leanexport.run_tool(
            regression_workspace,
            [
                str(REPO / ".lake/build/bin/homalg-export"),
                "--root",
                modules[0],
                "--root",
                modules[1],
                "--prefix",
                "HomAlg.Fixture2099",
            ],
        )
    assert caught.value.rule == "decl-unique"
    assert all(module in caught.value.output for module in modules)


@requires_lean
def test_real_type_text_is_independent_of_import_roots(tmp_path: Path) -> None:
    """Unrelated notation and custom delaborators cannot change committed type text."""
    shutil.copy2(REPO / "lean-toolchain", tmp_path / "lean-toolchain")
    (tmp_path / "lake-manifest.json").write_text(
        json_text({"packages": [{"name": "mathlib", "inputRev": "v4.35.0"}]})
    )
    sources = {
        "HomAlg.Fixture2099.Plain": (
            "/-- A theorem with no mathematical notation imports. -/\n"
            "theorem Fixture2099.plain (n : Nat) : n * 1 = n := Nat.mul_one n\n"
        ),
        "Noise.Notation": 'notation "ℕ" => Nat\n',
        "Noise.Printer": (
            "import Lean\nopen Lean PrettyPrinter Delaborator\n"
            "/-- Deliberately ignores the pp.notation option. -/\n"
            "@[delab app.Nat] meta def misleadingNat : Delab := `(String)\n"
        ),
    }
    for module, source in sources.items():
        path = tmp_path / Path(*module.split(".")).with_suffix(".lean")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        compile_module(tmp_path, module)

    def exported(roots: list[str], *, modules_file: bool = False) -> dict[str, Any]:
        """Use both supported scope selectors against the actual production binary."""
        if modules_file:
            (tmp_path / "modules.txt").write_text("\n".join(roots) + "\n")
            scope = ["--modules", "modules.txt"]
        else:
            scope = [value for root in roots for value in ("--root", root)]
        result = subprocess.run(
            [
                str(REPO / ".lake/build/bin/homalg-export"),
                *scope,
                "--prefix",
                "HomAlg.Fixture2099",
            ],
            cwd=tmp_path,
            env=dict(os.environ, LEAN_PATH=str(tmp_path)),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        raw = json.loads(result.stdout)
        assert not SchemaStore(REPO / "schema").validate(raw, "lean-export.schema.json")
        return flat(raw)["Fixture2099.plain"]

    plain = "HomAlg.Fixture2099.Plain"
    baseline = exported([plain])
    variants = []
    for roots, modules_file in (
        ([plain, "Noise.Notation"], False),
        (["Noise.Printer", plain], False),
        ([plain, "Noise.Printer", "Noise.Notation"], True),
        (["Noise.Notation", "Noise.Printer", plain], True),
    ):
        variant = exported(roots, modules_file=modules_file)
        assert variant == baseline
        variants.append(variant)
    assert "Nat" in baseline["type"]
    assert "String" not in baseline["type"]
    assert "ℕ" not in baseline["type"]
    assert "instHMul" not in baseline["type"]
    assert "⋯" not in baseline["type"]

    content = sources[plain].encode()
    header = {"decls": ["Fixture2099.plain"], "deps": {"statement": [], "proof": []}}
    before = local_derived("HomAlg/Fixture2099/Plain.lean", content, header, flat_record(baseline))
    after = local_derived(
        "HomAlg/Fixture2099/Plain.lean",
        content,
        header,
        flat_record(variants[-1]),
    )
    assert before == after

    # A real statement edit still changes both the compiled and displayed hashes.
    source = tmp_path / "HomAlg/Fixture2099/Plain.lean"
    source.write_text(sources[plain].replace("n * 1 = n := Nat.mul_one n", "n + 0 = n := rfl"))
    compile_module(tmp_path, plain)
    changed = exported([plain, "Noise.Printer", "Noise.Notation"])
    assert changed["type"] != baseline["type"]
    assert changed["type_hash"] != baseline["type_hash"]
    assert (
        hashlib.sha256(changed["type"].encode()).digest()
        != hashlib.sha256(baseline["type"].encode()).digest()
    )


def flat_record(declaration: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Adapt one real declaration to the deterministic local merge interface."""
    return {declaration["name"]: declaration}
