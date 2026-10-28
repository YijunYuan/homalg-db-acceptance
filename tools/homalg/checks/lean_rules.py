"""Checks based on compiled declarations and regenerated per-document derived records."""

from homalg.checks.context import Context, Finding
from homalg.checks.text_rules import THEOREM_TYPES, finding
from homalg.io import json_text
from homalg.review import lock_changes
from homalg.schemas import load_yaml


def decls_exist(ctx: Context) -> list[Finding]:
    """Every listed primary declaration must belong to exactly this node's module."""
    return [
        finding("decls-exist", path, f"Missing main declaration in this module: {name}")
        for path, header in ctx.valid_headers.items()
        for name in header.metadata.get("decls", [])
        if name not in ctx.declarations.get(f"HomAlg.{header.metadata['id']}", {})
    ]


def deps_verified(ctx: Context) -> list[Finding]:
    """Surface actual imports absent from the author's declared dependency graph."""
    return [
        Finding(
            "deps-verified",
            "warning",
            path,
            "Undeclared verified dependencies: "
            + ", ".join(derived["deps_diff"]["verified_not_declared"]),
            node=header.metadata["id"],
            fix=f"homalg fix-deps {header.metadata['doc']}",
        )
        for path, header in ctx.valid_headers.items()
        if (derived := ctx.derived.get(header.metadata["id"]))
        and derived["deps_diff"]["verified_not_declared"]
    ]


def route_faithful(ctx: Context) -> list[Finding]:
    """A completed proof must really use every source lemma, unless deviation is explicit."""
    result = []
    for path, header in ctx.valid_headers.items():
        metadata = header.metadata
        derived = ctx.derived.get(metadata["id"], {})
        if (
            metadata["kind"] not in THEOREM_TYPES
            or "aux" in metadata
            or "cited" in metadata
            or derived.get("local_status") != "proved"
        ):
            continue
        if any(
            item["kind"] == "proof-route" for item in metadata["fidelity"].get("deviations", [])
        ):
            continue
        verified = set(derived["verified_deps"]["statement"]) | set(
            derived["verified_deps"]["proof"]
        )
        missing = set(metadata["deps"]["proof"]) - verified
        if missing:
            result.append(
                finding(
                    "route-faithful",
                    path,
                    "Completed proof bypasses source dependencies: " + ", ".join(sorted(missing)),
                )
            )
    return result


def deps_statement_unused(ctx: Context) -> list[Finding]:
    """Warn about source-statement dependencies absent from the compiled statement."""
    result = []
    for path, header in ctx.valid_headers.items():
        derived = ctx.derived.get(header.metadata["id"], {})
        if derived.get("local_status") in {None, "planned"}:
            continue
        missing = set(header.metadata["deps"]["statement"]) - set(
            derived["verified_deps"]["statement"]
        )
        if missing:
            result.append(
                finding(
                    "deps-statement-unused",
                    path,
                    "Unused statement dependencies: " + ", ".join(sorted(missing)),
                    severity="warning",
                )
            )
    return result


def mathlib_bypass_statement(ctx: Context) -> list[Finding]:
    """Counterpart metadata does not authorize replacing a source statement by its library twin."""
    result = []
    for path, header in ctx.valid_headers.items():
        metadata = header.metadata
        if (
            "aux" in metadata
            or "cited" in metadata
            or metadata["fidelity"]["status"] == "foundation"
        ):
            continue
        counterpart = set(metadata.get("mathlib", {}).get("decls", []))
        used = {
            name
            for declaration in ctx.main_declarations(header)
            for name in declaration["type_uses_external"]
        }
        if used & counterpart:
            result.append(
                finding(
                    "mathlib-bypass-statement",
                    path,
                    "Statement uses its own Mathlib counterpart: "
                    + ", ".join(sorted(used & counterpart)),
                )
            )
    return result


def mathlib_bypass_proof(ctx: Context) -> list[Finding]:
    """Warn when a proof directly uses a source lemma's Mathlib counterpart."""
    result = []
    nodes = ctx.node_headers()
    for path, header in ctx.valid_headers.items():
        metadata = header.metadata
        if "cited" in metadata:
            continue
        counterpart = {
            name
            for dep in metadata["deps"]["proof"]
            if dep in nodes
            for name in nodes[dep].metadata.get("mathlib", {}).get("decls", [])
        }
        used = {
            name
            for declaration in ctx.main_declarations(header)
            for name in declaration["value_uses_external"]
        }
        if used & counterpart:
            result.append(
                finding(
                    "mathlib-bypass-proof",
                    path,
                    "Proof may bypass a source lemma through: "
                    + ", ".join(sorted(used & counterpart)),
                    severity="warning",
                )
            )
    return result


def hypothesis_packaging(ctx: Context) -> list[Finding]:
    """Compiled structure projections expose conclusions hidden in theorem assumptions."""
    return [
        finding(
            "hypothesis-packaging",
            path,
            f"{declaration['name']} assumes its conclusion via "
            f"{field['structure']}.{field['field'].split('.')[-1]} "
            f"at binder {field['binder']}",
            severity="warning",
            line=declaration.get("line"),
        )
        for path, header in ctx.valid_headers.items()
        if "aux" not in header.metadata and "cited" not in header.metadata
        for declaration in ctx.main_declarations(header)
        for field in declaration.get("packaged_fields", [])
    ]


def hollow_def(ctx: Context) -> list[Finding]:
    """Data-valued sorry requires a reasoned, satisfactory review exception."""
    allowances = {}
    result = []
    for key in ctx.docs:
        path = ctx.repo / "literature" / key / "hollow-allow.yaml"
        if not path.exists():
            continue
        try:
            record = load_yaml(path.read_text())
            if not isinstance(record, dict) or not isinstance(record.get("allowances"), list):
                raise ValueError(
                    "Expected allowances: [{node, reason, reviewed: {by, on, status}}]"
                )
            for item in record["allowances"]:
                review = item.get("reviewed", {})
                if (
                    not item.get("reason", "").strip()
                    or review.get("status") != "satisfactory"
                    or not review.get("by")
                    or not review.get("on")
                ):
                    raise ValueError(
                        "Every hollow allowance requires a reason and a satisfactory dated review"
                    )
                allowances[item["node"]] = item
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            result.append(finding("hollow-def", path.relative_to(ctx.repo).as_posix(), str(error)))
    return result + [
        finding(
            "hollow-def",
            path,
            f"{declaration['name']} contains missing data, not just an unproved obligation",
        )
        for path, header in ctx.valid_headers.items()
        if header.metadata["id"] not in allowances
        for declaration in ctx.main_declarations(header)
        if declaration["kind"] in {"def", "abbrev", "instance", "opaque", "structure"}
        and declaration["hollow"]
    ]


def kind_decl(ctx: Context) -> list[Finding]:
    """Authored node kinds should agree with the proposition/data distinction."""
    result = []
    for path, header in ctx.valid_headers.items():
        declarations = ctx.main_declarations(header)
        if not declarations:
            continue
        kind = header.metadata["kind"]
        if (
            kind in {"theorem", "lemma", "proposition", "corollary"}
            and not any(item["is_prop"] for item in declarations)
        ) or (
            kind in {"definition", "construction", "notation"}
            and not any(not item["is_prop"] for item in declarations)
        ):
            result.append(
                finding(
                    "kind-decl",
                    path,
                    f"Main declaration kinds do not match authored {kind}",
                    severity="warning",
                )
            )
    return result


def fidelity_reopened(ctx: Context) -> list[Finding]:
    """Compare source/context locks and compiled type/meaning hashes independently."""
    return [
        finding(
            "fidelity-reopened",
            path,
            f"{change['decl']}: {change['reason']}; request a new fidelity review",
            severity=change["severity"],
        )
        for path, header in ctx.valid_headers.items()
        for change in lock_changes(
            ctx.sources[path],
            header.metadata,
            ctx.declarations.get(f"HomAlg.{header.metadata['id']}", {}),
        )
    ]


def mathlib_decls_exist(ctx: Context) -> list[Finding]:
    """Unused counterpart names must resolve too; otherwise bypass checks could pass vacuously."""
    result = []
    references = []
    for path, header in ctx.valid_headers.items():
        references.extend(
            (path, name) for name in header.metadata.get("mathlib", {}).get("decls", [])
        )
        bridge = header.metadata.get("mathlib", {}).get("bridge")
        if bridge:
            candidate = ctx.node_headers().get(bridge)
            if (
                candidate is None
                or candidate.metadata.get("aux", {}).get("kind") != "bridge"
                or candidate.metadata["aux"]["parent"] != header.metadata["id"]
            ):
                result.append(
                    finding(
                        "mathlib-decls-exist",
                        path,
                        "Mathlib bridge must be a bridge node pointing back to this parent",
                    )
                )
    for key, document in ctx.docs.items():
        # Registration intentionally publishes only document/claim metadata. Its
        # foundation imports do not exist until a first node module is authored.
        if not any(header.metadata["doc"] == key for header in ctx.all_headers.values()):
            continue
        references.extend(
            (f"literature/{key}/document.yaml", name)
            for entry in document["foundations"]
            for name in entry["mathlib"]
        )
    lookups = ctx.raw.get("external_constants", {})
    for path, name in references:
        value = lookups.get(name)
        if value is None:
            result.append(
                finding(
                    "mathlib-decls-exist",
                    path,
                    f"Export lacks a compiled lookup for {name}; rerun homalg export-lean",
                )
            )
        elif not value["exists"] or (value["module"] or "").startswith("HomAlg"):
            result.append(
                finding(
                    "mathlib-decls-exist", path, f"{name} must resolve to a non-HomAlg constant"
                )
            )
    return result


def bridge_witness(ctx: Context) -> list[Finding]:
    """An asserted bridge must use both endpoints in its compiled type or value."""
    result = []
    nodes = ctx.node_headers()
    for path, header in ctx.valid_headers.items():
        aux = header.metadata.get("aux", {})
        if aux.get("kind") != "bridge":
            continue
        declarations = ctx.main_declarations(header)
        if not declarations:
            continue
        used_nodes = {
            node
            for declaration in declarations
            for side in ("type_uses_nodes", "value_uses_nodes")
            for node in declaration[side]
        }
        used_external = {
            name
            for declaration in declarations
            for side in ("type_uses_external", "value_uses_external")
            for name in declaration[side]
        }
        parent = nodes.get(aux["parent"])
        if aux["parent"] not in used_nodes:
            result.append(finding("bridge-witness", path, "Bridge does not use its parent node"))
        other = header.metadata["id"].rsplit("_", 1)[-1]
        if other == "mathlib":
            counterparts = (
                set(parent.metadata.get("mathlib", {}).get("decls", [])) if parent else set()
            )
            if not used_external & counterparts:
                result.append(
                    finding(
                        "bridge-witness",
                        path,
                        "Bridge does not use any declared Mathlib counterpart of its parent",
                    )
                )
        elif not any(node.startswith(f"{other}.") for node in used_nodes):
            result.append(
                finding(
                    "bridge-witness",
                    path,
                    f"Bridge does not use its other document endpoint {other}",
                )
            )
    return result


def instance_scope(ctx: Context) -> list[Finding]:
    """Reject global instances whose resulting type has no constant owned by their document."""
    result = []
    for path, header in ctx.valid_headers.items():
        for declaration in ctx.declarations.get(f"HomAlg.{header.metadata['id']}", {}).values():
            if declaration["kind"] != "instance":
                continue
            if (
                "is_global_instance" not in declaration
                or "instance_type_uses_own_doc" not in declaration
            ):
                result.append(
                    finding(
                        "instance-scope",
                        path,
                        "Export lacks authoritative instance scope metadata; rerun export",
                    )
                )
            elif (
                declaration["is_global_instance"] and not declaration["instance_type_uses_own_doc"]
            ):
                result.append(
                    finding(
                        "instance-scope",
                        path,
                        f"{declaration['name']} must be a scoped instance",
                        line=declaration.get("line"),
                    )
                )
    return result


def nodes_json_fresh(ctx: Context) -> list[Finding]:
    """Compare regenerated records without rewriting committed authored or derived content."""

    def stable(record: dict) -> str:
        return json_text({key: value for key, value in record.items() if key != "generator"})

    return [
        Finding(
            "nodes-json-fresh",
            "error",
            f"literature/{key}/nodes.json",
            "Committed nodes.json differs from the authored headers and compiled export",
            fix=f"homalg extract --doc {key} && homalg export-lean --doc {key}",
        )
        for key, expected in ctx.expected_nodes.items()
        if key not in ctx.nodes_files or stable(ctx.nodes_files[key]) != stable(expected)
    ]
