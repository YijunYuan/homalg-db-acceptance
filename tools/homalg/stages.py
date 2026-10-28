"""Evidence-based completion criteria for transcription and formalization tasks."""

import json
import re
from pathlib import Path
from typing import Any

from homalg.documents import read_document
from homalg.engine import task
from homalg.headers import parse_header
from homalg.review import review_blocks
from homalg.runtime_state import document_state, refresh
from homalg.schemas import load_yaml
from homalg.transcription import status as transcription_status
from homalg.validate import validate_repo

DEFINITION_KINDS = {"definition", "construction", "notation", "axiom"}


def graph_comments(repo: Path, key: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Read the documented hgraph attachment files with their session provenance."""
    output = {}
    for path in sorted((repo / "hgraph/nodes").glob("*.md")):
        parts = path.read_text().split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            continue
        metadata = load_yaml(parts[1])
        label = metadata.get("label", "")
        if not label or (key is not None and not label.startswith(key + ".")):
            continue
        records = []
        for attachment in sorted(path.with_suffix("").glob("*.md")):
            sections = attachment.read_text().split("---", 2)
            if len(sections) != 3:
                continue
            fields = load_yaml(sections[1])
            provenance = fields.get("provenance", {})
            if isinstance(provenance, str):
                try:
                    provenance = json.loads(provenance)
                except ValueError:
                    provenance = {}
            records.append(
                {
                    "file": attachment.name,
                    "body": sections[2].strip(),
                    "metadata": fields,
                    "session": provenance.get("session") or provenance.get("session_id"),
                }
            )
        output[label] = records
    return output


def attempt_sessions(comments: list[dict[str, Any]]) -> set[str]:
    """Count distinct session-tagged attempts, never duplicate comments from one session."""
    return {
        item["session"]
        for item in comments
        if item.get("session") and item.get("body", "").lstrip().startswith("attempt:")
    }


def task_nodes(state: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    """Include explicitly scoped nodes and newly created descendants of their parent nodes."""
    scopes = set(record.get("write_set", {}).get("files", []))
    ids = {
        path.removeprefix("HomAlg/").removesuffix(".lean").replace("/", ".", 1)
        for path in scopes
        if re.fullmatch(r"HomAlg/[^/]+/[^/]+\.lean", path)
    }
    return [
        node
        for node in state["nodes"]
        if node["id"] in ids or node["authored"].get("aux", {}).get("parent") in ids
    ]


def evaluate(repo: Path, record: dict[str, Any], *, refresh_exports: bool = True) -> dict[str, Any]:
    """Evaluate a task from source and compiled evidence without changing its task status."""
    info = record["metadata"]["homalg"]
    key, stage = info["doc"], info["stage"]
    document = read_document(repo, key)
    failures: list[str] = []
    if stage == "T":
        states = transcription_status(repo, key)["pages"]
        failures.extend(
            f"Page {page:04} is not reviewed"
            for page in info["pages"]
            if states.get(f"{page:04}", {}).get("status") != "reviewed"
        )
    elif stage == "INV":
        path = repo / "literature" / key / "inventory.yaml"
        inventory = load_yaml(path.read_text()) if path.exists() else {"pages": {}}
        for page in info["pages"]:
            entry = inventory["pages"].get(f"{page:04}", {})
            if not entry.get("complete"):
                failures.append(f"Page {page:04} is not completely inventoried")
        if any(entry["status"] == "draft" for entry in document["foundations"]):
            failures.append("Foundation suggestions remain draft")
        findings, _, _ = validate_repo(repo, (key,), fast=True)
        failures.extend(
            f"{finding.rule}: {finding.message}"
            for finding in findings
            if finding.severity == "error"
        )
    else:
        if refresh_exports:
            refresh(repo, key)
        state = document_state(repo, key)
        nodes = task_nodes(state, record)
        for node in nodes:
            authored, derived = node["authored"], node["derived"]
            if "informal" in authored or authored.get("aux", {}).get("pruned"):
                continue
            if stage == "DAG":
                source = parse_header(node["source"])
                section = "Statement" if authored["kind"] in DEFINITION_KINDS else "Proof"
                text = source.sections.get(section, "")
                if not text.strip() or re.search(r"(?im)^\s*TODO\b", text):
                    failures.append(f"{node['id']}: {section} has not been transcribed")
                if section == "Proof":
                    references = set(re.findall(r"\[uses\s+`?([A-Za-z0-9_.]+)`?\]", text))
                    if references != set(authored["deps"]["proof"]):
                        failures.append(f"{node['id']}: proof references differ from deps.proof")
            elif stage in {"CITED", "STMT"}:
                if node["approx"] or derived["local_status"] == "planned":
                    failures.append(f"{node['id']}: fresh main declarations are required")
                if stage == "CITED" and not authored.get("cited", {}).get("source"):
                    failures.append(f"{node['id']}: source citation is incomplete")
                # An owner-confirmed source error is a settled statement outcome.
                # Its counterexample/report must not be relabelled satisfactory.
                # Fresh compiled declarations and the full validation below still apply.
                if node["global"]["headline"] == "error":
                    continue
                if not authored["fidelity"].get("reviewed") or node["global"]["reopened"]:
                    failures.append(
                        f"{node['id']}: a current satisfactory statement lock is required"
                    )
                review_path = (
                    repo / "literature" / key / "reviews" / (node["id"].split(".", 1)[1] + ".md")
                )
                evidence = review_blocks(review_path.read_text()) if review_path.exists() else {}
                if evidence.get("source-fidelity", {}).get("status") != "satisfactory" or any(
                    block["status"] != "satisfactory" for block in evidence.values()
                ):
                    failures.append(f"{node['id']}: latest reviews must be satisfactory")
        if stage == "PROOF":
            candidates = {
                node["id"]: node
                for node in nodes
                if "informal" not in node["authored"]
                and not node["authored"].get("aux", {}).get("pruned")
            }
            comments = graph_comments(repo, key)
            settled = {
                node_id
                for node_id, node in candidates.items()
                if not node["approx"]
                and (
                    node["global"]["headline"] in {"proof-complete", "error"}
                    or (
                        node["global"]["headline"] == "statement-complete"
                        and len(attempt_sessions(comments.get(node_id, []))) >= 3
                    )
                )
            }
            while True:
                more = {
                    node_id
                    for node_id, node in candidates.items()
                    if node_id not in settled
                    and not node["approx"]
                    and node["derived"]["local_status"] == "proved"
                    and node["global"]["headline"] == "statement-complete"
                    and all(
                        dep in settled or dep not in candidates
                        for dep in node["global"]["closure"]["blocked_by"]
                    )
                }
                if not more:
                    break
                settled.update(more)
            failures.extend(
                f"{node_id}: proof work is not settled"
                for node_id in candidates
                if node_id not in settled
            )
        if stage in {"CITED", "STMT", "PROOF"}:
            export = repo / "build" / f"lean-export-{key}.json"
            if export.exists():
                findings, _, _ = validate_repo(
                    repo, (key,), fast=False, no_build=True, export=export
                )
                failures.extend(
                    f"{finding.rule}: {finding.message}"
                    for finding in findings
                    if finding.severity == "error"
                )
            else:
                failures.append("No current compiled document export is available")
    return {
        "task": record["id"],
        "doc_key": key,
        "stage": stage,
        "complete": not failures,
        "failures": sorted(set(failures)),
    }


def stage_check(repo: Path, task_id: str) -> dict[str, Any]:
    """Load the immutable task scope and refresh stale evidence before evaluating."""
    return evaluate(repo, task(repo, task_id))
