"""Run independent checks against authored, compiled and optional review evidence."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from homalg.checks import RULES
from homalg.checks.context import Context, Finding
from homalg.headers import HeaderError, parse_header
from homalg.leanexport import declaration_map, export_lean, local_derived
from homalg.leantext import commands
from homalg.relations import canonical_relation, relation_id
from homalg.repository import documents, node_paths
from homalg.schemas import SchemaStore, YamlError, load_yaml

FILE_RULES = set(
    """schema-header header-syntax header-sections id-path id-grammar lean-style
sorry-named tags-known concepts-known deps-exist aux-parent""".split()
)


def _git(repo: Path, *args: str, optional: bool = False) -> str | None:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode:
        if optional:
            return None
        raise ValueError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def load_context(
    repo: Path,
    selected: tuple[str, ...] = (),
    *,
    changed: bool = False,
    files: tuple = (),
    pr_base: str | None = None,
    pr_head: str | None = None,
    now: str | None = None,
) -> Context:
    """Load all reference facts while restricting per-node rules to the requested scope."""
    repo = repo.resolve()
    schemas = SchemaStore(repo / "schema")
    schemas.check_schemas()
    ctx = Context(repo=repo, schemas=schemas, selected=selected, now=now, file_mode=bool(files))
    all_keys = sorted(path.parent.name for path in (repo / "literature").glob("*/document.yaml"))
    keys = documents(repo, selected) if selected else all_keys
    merge_base = None
    if changed or pr_base:
        merge_base = _git(repo, "merge-base", pr_base or "origin/main", pr_head or "HEAD")
        merge_base = (merge_base or "").strip()
        diff_args = ["diff", "--name-only", "--diff-filter=ACDMRTUXB", merge_base]
        if pr_head:
            diff_args.append(pr_head)
        ctx.changed_paths = set((_git(repo, *diff_args) or "").splitlines())
        if not pr_head:
            ctx.changed_paths.update(
                (_git(repo, "ls-files", "--others", "--exclude-standard") or "").splitlines()
            )
        for path in ctx.changed_paths:
            before = _git(repo, "show", f"{merge_base}:{path}", optional=True)
            if before is not None:
                ctx.base_sources[path] = before
        if changed and not selected:
            touched = {
                Path(path).parts[1]
                for path in ctx.changed_paths
                if len(Path(path).parts) > 2 and Path(path).parts[0] in {"HomAlg", "literature"}
            }
            # Shared changes affect the entire graph; pure document changes narrow it.
            shared = any(
                not path.startswith(("HomAlg/", "literature/")) for path in ctx.changed_paths
            )
            if not shared:
                keys = [key for key in keys if key in touched]
                ctx.selected = tuple(keys)
    else:
        # Existing tracked files are not "new" for local out-of-scope diagnostics.
        tracked = _git(repo, "ls-files", "HomAlg", optional=True)
        for path in (tracked or "").splitlines():
            ctx.base_sources[path] = ""

    def read(
        relative: str,
        schema: str,
        rule: str,
        *,
        optional: bool = False,
        report: bool = True,
        json_input: bool = False,
    ) -> dict | None:
        path = repo / relative
        if optional and not path.exists():
            return None
        try:
            source = path.read_text(encoding="utf-8")
            value = json.loads(source) if json_input else load_yaml(source)
            errors = schemas.validate(value, schema)
            if errors:
                if report:
                    ctx.preloaded.extend(
                        Finding(rule, "error", relative, error.message) for error in errors
                    )
                return None
            return value
        except (OSError, ValueError, YamlError) as exc:
            if report:
                ctx.preloaded.append(
                    Finding(rule, "error", relative, str(exc), getattr(exc, "line", None))
                )
            return None

    for key in all_keys:
        active = key in keys
        document = read(
            f"literature/{key}/document.yaml",
            "document.schema.json",
            "schema-document",
            report=active,
        )
        if document is not None:
            ctx.all_docs[key] = document
            if active:
                ctx.docs[key] = document
        claim = read(
            f"literature/{key}/claim.yaml", "claim.schema.json", "schema-claim", report=active
        )
        if claim is not None:
            ctx.claims[key] = claim
            if active and claim["doc_key"] != key:
                ctx.preloaded.append(
                    Finding(
                        "schema-claim",
                        "error",
                        f"literature/{key}/claim.yaml",
                        "Claim doc_key must match its directory",
                    )
                )
        retired = read(
            f"literature/{key}/retired.yaml",
            "retired.schema.json",
            "id-grammar",
            optional=True,
            report=active,
        )
        if retired:
            for item in retired["retired"]:
                if item["id"] in ctx.retired or item["id"].split(".")[0] != key:
                    ctx.preloaded.append(
                        Finding(
                            "id-grammar",
                            "error",
                            f"literature/{key}/retired.yaml",
                            "Retired ids must be unique and belong to their document",
                        )
                    )
                ctx.retired[item["id"]] = item
        if active:
            inventory = read(
                f"literature/{key}/inventory.yaml",
                "inventory.schema.json",
                "inventory-valid",
                optional=True,
            )
            if inventory is not None:
                ctx.inventories[key] = inventory
            nodes = read(
                f"literature/{key}/nodes.json",
                "nodes-file.schema.json",
                "nodes-json-fresh",
                optional=True,
                json_input=True,
            )
            if nodes is not None:
                ctx.nodes_files[key] = nodes
    for name in ("tags", "concepts", "policy", "foundations-template"):
        value = read(f"taxonomy/{name}.yaml", f"{name}.schema.json", "schema-taxonomy")
        if value is not None:
            ctx.taxonomy[name] = value

    def node(relative: str, source: str, active: bool) -> None:
        for table in (ctx.commands, ctx.headers, ctx.valid_headers, ctx.all_headers):
            table.pop(relative, None)
        ctx.all_sources[relative] = source
        if active:
            ctx.sources[relative] = source
        try:
            header = parse_header(source)
            ctx.commands[relative] = commands(source)
        except HeaderError as exc:
            if active:
                ctx.preloaded.append(
                    Finding("header-syntax", "error", relative, str(exc), exc.line)
                )
            return
        if active:
            ctx.headers[relative] = header
        if not schemas.validate(header.metadata, "node-header.strict.schema.json"):
            ctx.all_headers[relative] = header
            if active:
                ctx.valid_headers[relative] = header

    for path in node_paths(repo, all_keys):
        relative = path.relative_to(repo).as_posix()
        ctx.existing_nodes.add(".".join(path.relative_to(repo).with_suffix("").parts[1:]))
        node(relative, path.read_bytes().decode("utf-8"), path.parent.name in keys and not files)
    if files:
        for entry in files:
            actual, alias = entry if isinstance(entry, (tuple, list)) else (entry, entry)
            actual, alias = Path(actual), Path(alias)
            if not actual.is_absolute():
                actual = repo / actual
            if alias.is_absolute():
                try:
                    alias = alias.relative_to(repo)
                except ValueError as error:
                    raise ValueError(
                        "Files outside the repository require --as HomAlg/Doc/Node.lean"
                    ) from error
            logical = alias.as_posix()
            if (
                len(alias.parts) != 3
                or alias.parts[0] != "HomAlg"
                or alias.suffix != ".lean"
                or alias.parts[1] not in all_keys
            ):
                raise ValueError(f"Invalid logical node path: {logical}")
            ctx.existing_nodes.add(f"{alias.parts[1]}.{alias.stem}")
            node(logical, actual.read_bytes().decode("utf-8"), True)
        ctx.docs = {
            key: value
            for key, value in ctx.all_docs.items()
            if any(header.metadata["doc"] == key for header in ctx.valid_headers.values())
        }
    for path in sorted((repo / "taxonomy/relations").glob("[!_]*.yaml")):
        relative = path.relative_to(repo).as_posix()
        record = read(relative, "relations.schema.json", "relations-valid")
        if record:
            ctx.relation_records.extend(
                (relative, relation, False) for relation in record["relations"]
            )
    for path, header in ctx.all_headers.items():
        for related in header.metadata.get("related", []):
            source, kind, target = canonical_relation(
                header.metadata["id"], related["type"], related["target"]
            )
            record = {
                "id": relation_id(source, kind, target, header=True),
                "source": source,
                "type": kind,
                "target": target,
                "provenance": {"on": related["on"]},
                "review": {"status": "unreviewed"},
            }
            ctx.relation_records.append((path, record, True))
    ctx.relation_reviews = (
        read(
            "taxonomy/relations/_reviews.yaml",
            "relation-reviews.schema.json",
            "relation-reviews-valid",
            optional=True,
        )
        or {}
    )
    for path in sorted((repo / "taxonomy/evolution").glob("*.yaml")):
        relative = path.relative_to(repo).as_posix()
        record = read(relative, "evolution.schema.json", "evolution-valid")
        if record:
            ctx.evolution_files[relative] = record
    health_path = repo / "site/public/data/health.json"
    if health_path.exists():
        try:
            ctx.health = json.loads(health_path.read_text())
        except ValueError as error:
            ctx.preloaded.append(
                Finding("markdown-renders", "warning", "site/public/data/health.json", str(error))
            )
    return ctx


def compiled_context(ctx: Context, raw: dict[str, Any]) -> None:
    """Build expected fresh records in memory; validation never repairs authored files."""
    errors = ctx.schemas.validate(raw, "lean-export.schema.json")
    if errors:
        raise ValueError(f"Invalid Lean export: {errors[0].message}")
    ctx.raw = raw
    ctx.declarations = declaration_map(raw)
    for key in ctx.docs:
        nodes = []
        for path, header in sorted(ctx.valid_headers.items()):
            if header.metadata["doc"] != key:
                continue
            identifier = header.metadata["id"]
            derived = local_derived(
                path,
                ctx.sources[path].encode(),
                header.metadata,
                ctx.declarations.get(f"HomAlg.{identifier}", {}),
            )
            ctx.derived[identifier] = derived
            nodes.append({"id": identifier, "authored": header.authored(), "derived": derived})
        ctx.expected_nodes[key] = {
            "schema_version": 1,
            "doc_key": key,
            "lean": {"toolchain": raw["toolchain"], "mathlib_rev": raw["mathlib_rev"]},
            "nodes": nodes,
        }


def validate_repo(
    repo: Path,
    selected: tuple[str, ...] = (),
    *,
    fast: bool = True,
    changed: bool = False,
    files: tuple = (),
    pr_base: str | None = None,
    pr_author: str | None = None,
    pr_labels: tuple[str, ...] = (),
    pr_created_at: str | None = None,
    pr_number: int | None = None,
    pr_head: str | None = None,
    now: str | None = None,
    only: tuple[str, ...] = (),
    no_build: bool = False,
    export: Path | dict | None = None,
) -> tuple[list[Finding], list[str], dict[str, int]]:
    """Evaluate every available requested rule, listing every unavailable rule explicitly.

    Full validation compiles without modifying committed nodes files. ``no_build``
    requires a supplied raw export, and skips build/freshness claims. External
    invocation failures propagate as ``ExternalToolError`` for CLI exit status 3.
    """
    if only and (unknown := set(only) - RULES.keys()):
        raise ValueError(f"Unknown validation rules: {', '.join(sorted(unknown))}")
    if no_build and export is None:
        raise ValueError("--no-build requires --export PATH")
    if bool(pr_base) != bool(pr_author):
        raise ValueError("PR validation requires both --pr-base and --pr-author")
    if files and (changed or pr_base or selected):
        raise ValueError("--files cannot be combined with document, changed or PR selectors")
    ctx = load_context(
        repo, selected, changed=changed, files=files, pr_base=pr_base, pr_head=pr_head, now=now
    )
    requested = set(only) if only else set(RULES)
    skipped = set()
    if pr_base:
        ctx.pr = {
            "base": pr_base,
            "author": pr_author,
            "labels": pr_labels,
            "created_at": pr_created_at,
            "number": pr_number,
            "head": pr_head or "HEAD",
            "now": now,
        }
    for name in requested:
        rule = RULES[name]
        unavailable = (bool(files) and name not in FILE_RULES) or (
            rule.explicit_only and name not in only
        )
        unavailable |= rule.needs_pr_context and not bool(ctx.pr)
        unavailable |= rule.needs_private and not any(
            (ctx.repo / "literature/.private" / key / "transcription.yaml").exists()
            for key in ctx.docs
        )
        unavailable |= rule.needs_prerender and not bool(ctx.health)
        unavailable |= rule.needs_lean and ((fast and export is None) or bool(files))
        unavailable |= no_build and name in {"lean-build", "nodes-json-fresh"}
        if unavailable:
            skipped.add(name)
    active = requested - skipped
    if any(RULES[name].needs_lean for name in active):
        bad_inputs = any(
            item.severity == "error"
            and item.rule in {"schema-document", "schema-taxonomy", "header-syntax"}
            for item in ctx.preloaded
        ) or len(ctx.valid_headers) != len(ctx.sources)
        if bad_inputs:
            skipped.update(name for name in active if RULES[name].needs_lean)
            active -= skipped
        else:
            if export is None:
                raw = export_lean(
                    ctx.repo,
                    next(iter(ctx.docs)) if len(ctx.docs) == 1 else None,
                    out=ctx.repo / "build/validation-export.json",
                    merge=False,
                )
            else:
                raw = export if isinstance(export, dict) else json.loads(Path(export).read_text())
            compiled_context(ctx, raw)
    if any(RULES[name].needs_pr_context for name in active):
        from homalg.pr_checks import pr_findings

        if active & {
            name for name, rule in RULES.items() if rule.needs_pr_context and not rule.explicit_only
        }:
            ctx.pr_findings.extend(pr_findings(ctx.repo, **ctx.pr))
        if "owner-approval" in active:
            ctx.pr_findings.extend(pr_findings(ctx.repo, **ctx.pr, owner_only=True))
    findings = [item for item in ctx.preloaded if item.rule in active]
    for name in sorted(active):
        findings.extend(RULES[name](ctx))
    if "mathlib-decls-exist" in active:
        for key, document in ctx.docs.items():
            if document["foundations"] and not any(
                header.metadata["doc"] == key for header in ctx.all_headers.values()
            ):
                skipped.add(f"mathlib-decls-exist:{key}:no-node-modules")
    # A loader and a rule may report the same schema issue; emit it once.
    findings = list(dict.fromkeys(findings))
    findings.sort(key=lambda item: (item.file, item.line or 0, item.rule, item.message))
    return findings, sorted(skipped), {"documents": len(ctx.docs), "nodes": len(ctx.sources)}
