"""Numeric status publication and private backups through bounded Git plumbing."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from homalg import engine
from homalg.claims import claim_view, instant, load_status_history, timestamp
from homalg.collaboration import Client, main_claim, policy_for
from homalg.documents import dump_metadata
from homalg.io import atomic_write, json_text
from homalg.repository import documents
from homalg.runtime_state import document_state
from homalg.schemas import SchemaStore, load_yaml
from homalg.stages import graph_comments


def log(repo: Path, message: str, session: Path | None = None) -> None:
    """Keep hook diagnostics off stdout and out of public numeric status payloads."""
    path = session / "hooks.log" if session else repo / ".archon-horizon/overlay/hooks.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{timestamp(datetime.now(UTC))} {message.rstrip()}\n")


def inbox_items(repo: Path) -> list[dict[str, Any]]:
    """Read complete inbox records, including comments, through the public CLI."""
    data = json.loads(engine.horizon(repo, "inbox", "list", "--json"))
    return data if isinstance(data, list) else data.get("items", data.get("data", []))


def related_items(repo: Path, key: str, items: list[dict] | None = None) -> list[dict]:
    """Select by node scope or owning/writing task, never by quoted prose contents."""
    task_ids = {record["id"] for record in engine.tasks(repo, key)}
    result = []
    for item in inbox_items(repo) if items is None else items:
        scope = item.get("scope", {})
        metadata = item.get("metadata", {})
        provenance = metadata.get("provenance", {})
        if isinstance(provenance, str):
            try:
                provenance = json.loads(provenance)
            except ValueError:
                provenance = {}
        owners = {
            item.get("owner_task"),
            metadata.get("owner_task"),
            provenance.get("task"),
            provenance.get("task_id"),
        }
        nodes = scope.get("blueprint_nodes", [])
        if (
            any(node.removeprefix("label:").startswith(key + ".") for node in nodes)
            or task_ids & owners
            or metadata.get("homalg", {}).get("doc") == key
        ):
            result.append(item)
    return result


def notify(
    repo: Path,
    key: str,
    message: str,
    *,
    rule: str,
    node: str | None = None,
    task: str | None = None,
) -> str | None:
    """Deduplicate open machine diagnostics by rule and node/document identity."""
    marker = f"[homalg:{rule}:{node or key}]"
    for item in inbox_items(repo):
        if item.get("status") == "open" and item.get("body", "").startswith(marker):
            return item["id"]
    args = [
        "inbox",
        "add",
        "--kind",
        "issue",
        "--to",
        "human",
        "--author",
        "homalg",
        "--body",
        f"{marker}\n\n{message}",
        "--json",
    ]
    if node:
        args.extend(("--node", node))
    elif not task:
        records = engine.tasks(repo, key)
        if records:
            task = records[0]["id"]
        else:
            paths = sorted((repo / "HomAlg" / key).glob("*.lean"))
            if paths:
                args.extend(("--node", f"{key}.{paths[0].stem}"))
    if task:
        args.extend(("--owner", task))
    response = json.loads(engine.horizon(repo, *args))
    return response.get("id") if isinstance(response, dict) else None


def export_logs(repo: Path, tree: Path, key: str) -> list[str]:
    """Archive complete local inbox and node discussion records in a scoped destination."""
    documents(repo, (key,))
    paths = []
    for item in related_items(repo, key):
        identifier = item["id"]
        if not re.fullmatch(r"I-[A-Za-z0-9_-]+", identifier):
            raise ValueError(f"Unsafe inbox id: {identifier}")
        relative = f"literature/{key}/run-log/inbox/{identifier}.yaml"
        atomic_write(tree / relative, dump_metadata(item))
        paths.append(relative)
    for node, comments in graph_comments(repo, key).items():
        local = node.split(".", 1)[1]
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*", local):
            raise ValueError(f"Unsafe node comment id: {node}")
        parts = [f"# Discussion of {node}\n"]
        for comment in comments:
            parts.extend(
                [
                    f"## {comment['file']}\n",
                    "```yaml\n" + dump_metadata(comment["metadata"]).rstrip() + "\n```\n",
                    comment["body"] + "\n",
                ]
            )
        relative = f"literature/{key}/run-log/comments/{local}.md"
        atomic_write(tree / relative, "\n".join(parts))
        paths.append(relative)
    return paths


def numeric_status(
    repo: Path,
    key: str,
    holder: str,
    *,
    now: datetime | None = None,
    chapters: list[str] | None = None,
) -> dict[str, Any]:
    """Whitelist every public field so private text cannot enter a status publication."""
    current = instant(now or datetime.now(UTC))
    state = document_state(repo, key)
    nodes, counts = state["nodes"], state["counts"]
    main = [
        node for node in nodes if "aux" not in node["authored"] and "cited" not in node["authored"]
    ]
    aux = [node for node in nodes if "aux" in node["authored"]]
    statuses = Counter(node["global"]["status"] for node in main)
    output_counts = {
        name: statuses[name.replace("_", "-")]
        for name in (
            "planned",
            "stated",
            "proved",
            "proved_modulo_citations",
            "proved_pending_deps",
            "proved_with_axioms",
            "disputed",
            "informal",
            "pruned",
        )
    }
    output_counts.update(
        items_total=counts["items_total"],
        aux_total=counts["aux_total"],
        cited_total=sum("cited" in node["authored"] for node in nodes),
        locked=sum(
            bool(node["authored"]["fidelity"].get("reviewed")) and not node["global"]["reopened"]
            for node in main
        ),
        aux_proved=sum(
            node["derived"]["local_status"] == "proved"
            and not node["authored"]["aux"].get("pruned")
            for node in aux
        ),
        pages_total=0,
        pages_reviewed=0,
    )
    for field, source in (
        ("headline", "headline_counts"),
        ("aux_headline", "aux_headline_counts"),
        ("cited_headline", "cited_headline_counts"),
    ):
        output_counts[field] = {
            name.replace("-", "_"): value for name, value in counts[source].items()
        }
    private = repo / "literature/.private" / key / "transcription.yaml"
    if private.exists():
        from homalg.transcription import reconcile

        manifest = load_yaml(private.read_text())
        reconcile(private, manifest)
        pages = manifest["pages"]
        output_counts["pages_total"] = len(pages)
        output_counts["pages_reviewed"] = sum(
            item["status"] == "reviewed" for item in pages.values()
        )
    stages = {}
    for record in engine.tasks(repo, key):
        stage = record["metadata"]["homalg"]["stage"]
        entry = stages.setdefault(stage, {"done": 0, "total": 0})
        entry["total"] += 1
        entry["done"] += record.get("status") == "done"
    check_path = repo / ".archon-horizon/overlay" / f"validate-{key}.json"
    last = {"result": "none", "at": None}
    if check_path.exists():
        check = json.loads(check_path.read_text())
        red = any(finding["severity"] == "error" for finding in check.get("findings", []))
        last = {
            "result": "red" if red else "green",
            "at": check.get("at")
            or timestamp(datetime.fromtimestamp(check_path.stat().st_mtime, UTC)),
        }
    result = {
        "schema_version": 1,
        "doc_key": key,
        "holder": holder,
        "generated_at": timestamp(current),
        "scope_chapters": chapters or [],
        "counts": output_counts,
        "stages": stages,
        "last_check": last,
        "open_for_human": sum(
            item.get("status") == "open" and item.get("audience") == "human"
            for item in related_items(repo, key)
        ),
    }
    errors = SchemaStore(repo / "schema").validate(result, "run-status.schema.json")
    if errors:
        raise ValueError(f"Invalid numeric status: {errors[0].message}")
    return result


def throttled(
    repo: Path, name: str, minutes: int, current: datetime, *, force: bool = False
) -> bool:
    path = repo / ".archon-horizon/overlay" / f"{name}.json"
    if force or not path.exists():
        return False
    value = json.loads(path.read_text())
    return current - instant(value["at"]) < timedelta(minutes=minutes)


def stamp(repo: Path, name: str, current: datetime, **extra: Any) -> None:
    atomic_write(
        repo / ".archon-horizon/overlay" / f"{name}.json",
        json_text({"at": timestamp(current), **extra}),
    )


def publish_status(
    repo: Path,
    key: str,
    *,
    force: bool = False,
    now: datetime | None = None,
    session: Path | None = None,
    client: Client | None = None,
) -> dict:
    """Append numeric status by Git plumbing, preserving both working tree and user index."""
    documents(repo, (key,))
    current = instant(now or datetime.now(UTC))
    name = f"publish-status-{key}"
    minutes = int(os.environ.get("HOMALG_STATUS_MIN", "60"))
    if minutes < 0:
        raise ValueError("HOMALG_STATUS_MIN cannot be negative")
    if throttled(repo, name, minutes, current, force=force):
        return {"published": False, "reason": "throttled"}
    holder = engine.settings(repo).get("login")
    if not holder:
        raise ValueError("Run homalg horizon-init to cache the authenticated contributor login")
    client = client or Client(repo)
    schemas = SchemaStore(repo / "schema")
    try:
        present = client.fetch(key)
        claim = main_claim(client, key, schemas)
        history = load_status_history(repo, key, schemas=schemas) if present else []
        view = claim_view(
            claim, history, current, policy=policy_for(repo, schemas), schemas=schemas
        )
        if view["state"] != "active" or view.get("holder", "").casefold() != holder.casefold():
            message = (
                f"Skipped status/{key}: the cached contributor no longer holds "
                "an active claim on origin/main"
            )
            log(repo, message, session)
            notify(repo, key, message, rule="claim-owner")
            stamp(repo, name, current, skipped=True)
            return {"published": False, "reason": "claim-inactive"}
        payload = numeric_status(repo, key, holder, now=current, chapters=view["scope"]["chapters"])
        parent = (
            client.git("rev-parse", f"refs/remotes/origin/status/{key}").strip()
            if present
            else None
        )
        with tempfile.TemporaryDirectory(prefix="homalg-status-") as temporary:
            path = Path(temporary) / "status.json"
            path.write_text(json_text(payload))
            blob = client.git("hash-object", "-w", str(path)).strip()
            result = subprocess.run(
                ["git", "mktree"],
                cwd=repo,
                input=f"100644 blob {blob}\tstatus.json\n",
                capture_output=True,
                text=True,
                check=True,
            )
            tree = result.stdout.strip()
        args = ["commit-tree", tree, "-m", f"status({key}): numeric progress"]
        if parent:
            args.extend(("-p", parent))
        commit = client.git(*args).strip()
        client.git("push", "origin", f"{commit}:refs/heads/status/{key}")
        client.git("update-ref", f"refs/remotes/origin/status/{key}", commit)
        stamp(repo, name, current, commit=commit)
        return {"published": True, "commit": commit, "status": payload}
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        log(repo, f"Status publication failed; retry next time: {error}", session)
        return {"published": False, "reason": "network-or-git-error"}
