"""GitHub collaboration using isolated worktrees and current main-branch ownership."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from homalg.claims import claim_view, instant, load_status_history, transition
from homalg.classify import append_only, classify_changed
from homalg.documents import dump_metadata, parse_metadata, read_document, read_metadata
from homalg.io import atomic_write
from homalg.repository import DOC_KEY
from homalg.schemas import SchemaStore, load_yaml


class ExternalToolError(RuntimeError):
    """An external command failed without being mistaken for validation success."""


class Client:
    """Git and gh process boundary, replaceable by a fake client in tests."""

    def __init__(self, repo: Path):
        self.repo = repo

    def run(
        self, *args: str, cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Capture output; never interpolate arguments through a shell."""
        try:
            result = subprocess.run(
                args, cwd=cwd or self.repo, capture_output=True, text=True, check=False
            )
        except OSError as exc:
            raise ExternalToolError(f"Unable to execute {args[0]}: {exc}") from exc
        if check and result.returncode:
            raise ExternalToolError(
                f"{args[0]} failed ({result.returncode}): {result.stderr.strip()}"
            )
        return result

    def git(self, *args: str, cwd: Path | None = None) -> str:
        """Run Git and return its unmodified stdout."""
        return self.run("git", *args, cwd=cwd).stdout

    def gh(self, *args: str) -> str:
        """Run GitHub CLI without printing sensitive subprocess output."""
        return self.run("gh", *args).stdout

    def api(self, endpoint: str) -> Any:
        """Read all pages from a JSON GitHub API endpoint."""
        pages = json.loads(self.gh("api", endpoint, "--paginate", "--slurp"))
        if pages and isinstance(pages[0], list):
            return [item for page in pages for item in page]
        return pages[0] if len(pages) == 1 else pages

    def blob(self, ref: str, path: str) -> str | None:
        """Read a tracked blob, distinguishing absence from a broken Git reference."""
        self.git("rev-parse", "--verify", f"{ref}^{{commit}}")
        exists = self.run("git", "cat-file", "-e", f"{ref}:{path}", check=False)
        if exists.returncode:
            return None
        return self.git("show", f"{ref}:{path}")

    def fetch(self, key: str | None = None) -> bool:
        """Refresh main separately; ignore only a genuinely absent status branch."""
        self.git("fetch", "origin", "main:refs/remotes/origin/main")
        if key is None:
            return False
        if not DOC_KEY.fullmatch(key):
            raise ValueError(f"Invalid document key: {key}")
        result = self.run(
            "git",
            "fetch",
            "origin",
            f"status/{key}:refs/remotes/origin/status/{key}",
            check=False,
        )
        if result.returncode and "couldn't find remote ref" not in result.stderr:
            raise ExternalToolError(f"Cannot fetch status/{key}: {result.stderr.strip()}")
        return result.returncode == 0

    def identity(self) -> tuple[str, str]:
        """Resolve the authenticated contributor and destination repository."""
        self.gh("auth", "status")
        login = self.gh("api", "user", "--jq", ".login").strip()
        repository = json.loads(self.gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
        return login, repository


def changed_paths(client: Client, base: str, head: str = "HEAD") -> list[str]:
    """Include both sides of renames so scope and deletion checks cannot be bypassed."""
    return (
        client.git("diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", "--")
        .strip("\0")
        .split("\0")
        if client.git("rev-parse", "--verify", base).strip()
        else []
    )


def classify_repository(
    client: Client, base: str, labels: list[str], head: str = "HEAD"
) -> dict[str, Any]:
    """Classify a PR from its merge-base tree and current branch name."""
    files = [path for path in changed_paths(client, base, head) if path]
    existing = []
    for path in files:
        match = re.fullmatch(r"literature/([^/]+)/document\.yaml", path)
        if match and client.blob(base, path) is not None:
            existing.append(match.group(1))
    branch = client.git("branch", "--show-current").strip()
    return classify_changed(files, labels, existing_documents=existing, head_branch=branch)


def policy_for(repo: Path, schemas: SchemaStore | None = None) -> dict[str, Any]:
    """Read the shared repository claim policy."""
    return read_metadata(
        repo / "taxonomy/policy.yaml", "policy.schema.json", schemas or SchemaStore(repo / "schema")
    )


def main_claim(client: Client, key: str, schemas: SchemaStore) -> dict[str, Any]:
    """Use ownership from current origin/main, never a contributor's stale work branch."""
    text = client.blob("origin/main", f"literature/{key}/claim.yaml")
    if text is None:
        raise ValueError(f"Document {key} is not registered on origin/main")
    data = parse_metadata(text)
    errors = schemas.validate(data, "claim.schema.json")
    if errors or data["doc_key"] != key:
        raise ValueError(f"Invalid claim on origin/main for {key}")
    return data


def pending_claim_count(
    client: Client, repository: str, holder: str, key: str, *, exclude_pr: int | None = None
) -> int:
    """Count other open claim PRs by their head contents, including concurrent requests."""
    requests = json.loads(
        client.gh(
            "pr",
            "list",
            "--state",
            "open",
            "--author",
            holder,
            "--label",
            "claim",
            "--json",
            "number,files,headRefOid",
        )
    )
    count = 0
    for request in requests:
        if request["number"] == exclude_pr:
            continue
        for file in request["files"]:
            path = file["path"]
            match = re.fullmatch(r"literature/([^/]+)/claim\.yaml", path)
            if not match or match.group(1) == key:
                continue
            text = client.gh(
                "api",
                f"repos/{repository}/contents/{path}",
                "--method",
                "GET",
                "-f",
                f"ref={request['headRefOid']}",
                "-H",
                "Accept: application/vnd.github.raw+json",
            )
            value = load_yaml(text)
            if not isinstance(value, dict) or not isinstance(value.get("claims"), list):
                raise ValueError(f"Malformed pending claim in PR {request['number']}")
            if any(claim.get("holder", "").lower() == holder.lower() for claim in value["claims"]):
                count += 1
    return count


def active_claim_count(
    client: Client,
    holder: str,
    key: str,
    now: datetime,
    schemas: SchemaStore,
    policy: dict[str, Any],
) -> int:
    """Count the holder's other active main-branch claims using fresh status branches."""
    count = 0
    paths = client.git(
        "ls-tree", "-r", "--name-only", "origin/main", "--", "literature"
    ).splitlines()
    for path in paths:
        match = re.fullmatch(r"literature/([^/]+)/claim\.yaml", path)
        if not match or match.group(1) == key:
            continue
        other = match.group(1)
        data = main_claim(client, other, schemas)
        if not data["claims"] or data["claims"][0]["holder"].lower() != holder.lower():
            continue
        present = client.fetch(other)
        history = load_status_history(client.repo, other, schemas=schemas) if present else []
        if claim_view(data, history, now, schemas=schemas, policy=policy)["state"] == "active":
            count += 1
    return count


@contextmanager
def worktree(client: Client, branch: str) -> Iterator[Path]:
    """Build a PR in a disposable checkout, keeping the contributor's checkout in place."""
    with tempfile.TemporaryDirectory(prefix="homalg-pr-") as directory:
        target = Path(directory) / "worktree"
        client.git("worktree", "add", "-b", branch, str(target), "origin/main")
        try:
            yield target
        finally:
            # Worktree contents are generated only by this command; the source is never removed.
            client.git("worktree", "remove", "--force", str(target))


def publish_pr(
    client: Client,
    tree: Path,
    branch: str,
    title: str,
    body: str,
    label: str,
    *,
    auto_merge: bool = False,
    watch: bool = True,
) -> str:
    """Push a fully prepared branch and create a PR using an exact UTF-8 body file."""
    client.git("push", "-u", "origin", f"HEAD:refs/heads/{branch}", cwd=tree)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".md") as body_file:
        body_file.write(body)
        body_file.flush()
        url = client.gh(
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            body_file.name,
            "--label",
            label,
        ).strip()
    if auto_merge:
        client.gh("pr", "merge", url, "--auto", "--squash")
        if watch:
            client.gh("pr", "checks", url, "--watch")
            state = json.loads(client.gh("pr", "view", url, "--json", "state,mergeStateStatus"))
            if state["state"] != "MERGED":
                raise ValueError(
                    f"Checks completed but claim is not merged: {url} ({state['mergeStateStatus']})"
                )
    return url


def claim_operation(
    repo: Path,
    key: str,
    action: str,
    *,
    now: datetime | None = None,
    days: int | None = None,
    chapters: list[str] | None = None,
    note: str = "",
    dry_run: bool = False,
    watch: bool = True,
    client: Client | None = None,
) -> dict[str, Any]:
    """Prepare and publish take/renew/release changes in a dedicated claim worktree."""
    client = client or Client(repo)
    schemas = SchemaStore(repo / "schema")
    document = read_document(repo, key, schemas)
    if document["type"] == "synthetic":
        raise ValueError("Synthetic documents are maintained without claims")
    current = instant(now or datetime.now(UTC))
    holder, repository = client.identity()
    present = client.fetch(key)
    previous = main_claim(client, key, schemas)
    history = load_status_history(repo, key, schemas=schemas) if present else []
    policy = policy_for(repo, schemas)
    active = (
        active_claim_count(client, holder, key, current, schemas, policy)
        if action != "release"
        else 0
    )
    pending = pending_claim_count(client, repository, holder, key) if action != "release" else 0
    result = transition(
        previous,
        action,
        holder,
        current,
        status_log=history,
        policy=policy,
        days=days,
        chapters=chapters,
        note=note,
        active_other_claims=active,
        pending_other_claims=pending,
        schemas=schemas,
    )
    if dry_run:
        return {"action": action, "claim": result, "published": False}
    prefix = f"claim/{key}/{holder}-{current:%Y%m%d}"
    existing = set(client.git("branch", "--format=%(refname:short)").splitlines())
    branch, suffix = prefix, 1
    while branch in existing:
        suffix += 1
        branch = f"{prefix}-{suffix}"
    title = f"claim({key}): {action} by {holder}"
    with worktree(client, branch) as tree:
        path = tree / "literature" / key / "claim.yaml"
        atomic_write(path, dump_metadata(result))
        client.git("add", "--", str(path.relative_to(tree)), cwd=tree)
        client.git("commit", "-m", title, cwd=tree)
        body = (
            f"## Summary\n\n{action.capitalize()} the claim for `{key}`.\n\n"
            "## FR-NFR covered\n\nFR-12; section 10.2.\n\n"
            "## How verified\n\nCurrent main ownership, activity expiry and "
            "active/pending claim limits were checked.\n\n"
            "## Not done & spec issues\n\nNo formalization files are changed.\n"
        )
        url = publish_pr(client, tree, branch, title, body, "claim", auto_merge=True, watch=watch)
    return {"action": action, "claim": result, "published": True, "pr": url}


def append_merge_records(
    base: dict[str, Any], main: dict[str, Any], work: dict[str, Any], field: str
) -> dict[str, Any]:
    """Merge only work-branch additions by id while retaining main's newer records."""
    if not append_only(base, work, field):
        raise ValueError(f"Work-branch {field} changes are not append-only")
    result = deepcopy(main)
    current = {item["id"]: item for item in main.get(field, [])}
    old = {item["id"] for item in base.get(field, [])}
    target = result.setdefault(field, [])
    for item in work.get(field, []):
        if item["id"] in old:
            continue
        if item["id"] in current and current[item["id"]] != item:
            raise ValueError(f"Conflicting {field} id: {item['id']}")
        if item["id"] not in current:
            target.append(deepcopy(item))
    return result


class SubmitHooks(Protocol):
    """Horizon integration points required for real-document submissions."""

    def ensure_idle(self, repo: Path, key: str) -> None: ...
    def backup(self, repo: Path) -> None: ...
    def export_logs(self, repo: Path, tree: Path, key: str) -> None: ...
    def publish_status(self, repo: Path, key: str) -> None: ...
    def escalate(self, repo: Path, key: str) -> None: ...


def submit(
    repo: Path,
    key: str,
    *,
    no_claim: bool = False,
    release_claim: bool = False,
    now: datetime | None = None,
    client: Client | None = None,
    hooks: SubmitHooks | None = None,
) -> dict[str, Any]:
    """Construct and validate a scoped formalization PR without switching the user's worktree."""
    client = client or Client(repo)
    schemas = SchemaStore(repo / "schema")
    document = read_document(repo, key, schemas)
    if no_claim and document["type"] != "synthetic":
        raise ValueError("--no-claim is only permitted for synthetic documents")
    if not no_claim and hooks is None:
        raise ValueError("Real-document submit requires the configured Horizon submission hooks")
    if hooks:
        hooks.ensure_idle(repo, key)
    current = instant(now or datetime.now(UTC))
    holder, _ = client.identity()
    present = client.fetch(key)
    claim = main_claim(client, key, schemas)
    policy = policy_for(repo, schemas)
    if not no_claim:
        history = load_status_history(repo, key, schemas=schemas) if present else []
        view = claim_view(claim, history, current, schemas=schemas, policy=policy)
        if view["state"] != "active" or view.get("holder", "").lower() != holder.lower():
            raise ValueError(
                f"claim expired or held by another contributor: run homalg claim {key}"
            )
    branch = client.git("branch", "--show-current").strip()
    if not branch or branch in {"main", "master"}:
        raise ValueError("Submit from a named work branch, not the default branch")
    paths = [
        f"HomAlg/{key}",
        f"HomAlg/{key}.lean",
        f"literature/{key}",
        "taxonomy/tags.yaml",
        "taxonomy/concepts.yaml",
        f"taxonomy/relations/{key}.yaml",
    ]
    paths = [
        path
        for path in paths
        if (repo / path).exists() or client.git("ls-files", "--", path).strip()
    ]
    dirty = client.git("status", "--porcelain", "--", *paths).strip()
    if dirty:
        client.git("add", "-A", "--", *paths)
        client.git("commit", "--only", "-m", f"work({key}): snapshot for submission", "--", *paths)
    if hooks:
        # Horizon commits to its ledger; back up the actual source snapshot too.
        hooks.backup(repo)
    source = client.git("rev-parse", "HEAD").strip()
    base = client.git("merge-base", source, "origin/main").strip()
    requests = json.loads(
        client.gh(
            "pr",
            "list",
            "--state",
            "all",
            "--search",
            f"head:formalize/{key}-",
            "--json",
            "headRefName",
        )
    )
    numbers = [
        int(match.group(1))
        for request in requests
        if (match := re.fullmatch(rf"formalize/{re.escape(key)}-([0-9]+)", request["headRefName"]))
    ]
    number = max(numbers, default=0) + 1
    target_branch = f"formalize/{key}-{number}"
    with worktree(client, target_branch) as tree:
        client.git(
            "restore",
            f"--source={source}",
            "--staged",
            "--worktree",
            "--",
            f"HomAlg/{key}",
            f"literature/{key}",
            cwd=tree,
        )
        client.git(
            "restore",
            "--source=origin/main",
            "--staged",
            "--worktree",
            "--",
            f"literature/{key}/claim.yaml",
            cwd=tree,
        )
        for relative, field in (
            ("taxonomy/tags.yaml", "tags"),
            ("taxonomy/concepts.yaml", "concepts"),
            (f"taxonomy/relations/{key}.yaml", "relations"),
        ):

            def data(ref: str, relative: str = relative, field: str = field) -> dict[str, Any]:
                text = client.blob(ref, relative)
                return (
                    parse_metadata(text) if text is not None else {"schema_version": 1, field: []}
                )

            merged = append_merge_records(data(base), data("origin/main"), data(source), field)
            if merged[field] or (tree / relative).exists():
                atomic_write(tree / relative, dump_metadata(merged))
        lake = tree / ".lake"
        lake.mkdir(exist_ok=True)
        if (repo / ".lake/packages").exists():
            (lake / "packages").symlink_to(repo / ".lake/packages", target_is_directory=True)
        if (repo / ".lake/build").exists():
            client.run("cp", "-a", "--reflink=auto", str(repo / ".lake/build"), str(lake / "build"))
        for args in (
            ("taxonomy", "apply-merges", "--doc", key),
            ("gen-roots",),
            ("extract", "--doc", key),
            ("export-lean", "--doc", key),
            ("validate", "--doc", key),
        ):
            client.run(sys.executable, "-m", "homalg", *args, "--repo", str(tree), cwd=tree)
        if hooks:
            hooks.export_logs(repo, tree, key)
            hooks.publish_status(repo, key)
        if not no_claim:
            # A long build must not renew a claim that expired or changed holder meanwhile.
            present = client.fetch(key)
            claim = main_claim(client, key, schemas)
            renewal_now = instant(now or datetime.now(UTC))
            history = load_status_history(repo, key, schemas=schemas) if present else []
            view = claim_view(claim, history, renewal_now, schemas=schemas, policy=policy)
            if view["state"] != "active" or view.get("holder", "").lower() != holder.lower():
                raise ValueError(f"claim expired during submission: run homalg claim {key}")
            updated = transition(
                claim,
                "release" if release_claim else "renew",
                holder,
                renewal_now,
                status_log=history,
                policy=policy,
                schemas=schemas,
            )
            atomic_write(tree / f"literature/{key}/claim.yaml", dump_metadata(updated))
        client.git("add", "-A", cwd=tree)
        staged = client.git("diff", "--cached", "--name-only", cwd=tree).splitlines()
        if not staged:
            raise ValueError("There are no document changes to submit")

        def allowed(path: str) -> bool:
            return path in {
                "HomAlg.lean",
                f"HomAlg/{key}.lean",
                "taxonomy/tags.yaml",
                "taxonomy/concepts.yaml",
                f"taxonomy/relations/{key}.yaml",
            } or path.startswith((f"HomAlg/{key}/", f"literature/{key}/"))

        if any(not allowed(path) for path in staged):
            raise ValueError("Submission generated changes outside the selected document scope")
        title = f"formalize({key}): document update run {number}"
        client.git("commit", "-m", title, cwd=tree)
        summary = client.run(
            sys.executable,
            "-m",
            "homalg",
            "review-summary",
            "--doc",
            key,
            "--repo",
            str(tree),
            cwd=tree,
        ).stdout
        body = f"<!-- homalg: doc={key} release_claim={str(release_claim).lower()} -->\n\n{summary}"
        url = publish_pr(client, tree, target_branch, title, body, "formalization")
    if release_claim and not no_claim and hooks:
        hooks.escalate(repo, key)
    return {"doc": key, "pr": url, "branch": target_branch}


def register_document(
    repo: Path,
    key: str,
    files: dict[str, str] | None = None,
    *,
    client: Client | None = None,
) -> dict[str, Any]:
    """Publish exactly the public document and empty claim metadata as a registration PR."""
    if not DOC_KEY.fullmatch(key):
        raise ValueError(f"Invalid document key: {key}")
    allowed = {f"literature/{key}/document.yaml", f"literature/{key}/claim.yaml"}
    if files is None:
        files = {relative: (repo / relative).read_text(encoding="utf-8") for relative in allowed}
    if set(files) != allowed:
        raise ValueError("Registration writes exactly document.yaml and claim.yaml")
    schemas = SchemaStore(repo / "schema")
    for relative, text in files.items():
        value = load_yaml(text)
        schema = (
            "document.schema.json" if relative.endswith("document.yaml") else "claim.schema.json"
        )
        errors = schemas.validate(value, schema)
        if errors or value.get("doc_key") != key:
            raise ValueError(f"Invalid registration metadata: {relative}")
        if schema == "claim.schema.json" and value["claims"]:
            raise ValueError("A new document must start unclaimed")
    client = client or Client(repo)
    holder, _ = client.identity()
    client.fetch()
    if client.blob("origin/main", f"literature/{key}/document.yaml") is not None:
        raise ValueError(f"Document {key} is already registered")
    branch = f"register/{key}"
    with worktree(client, branch) as tree:
        for relative, text in files.items():
            atomic_write(tree / relative, text)
        client.git("add", "--", *sorted(allowed), cwd=tree)
        title = f"register({key}): document by {holder}"
        client.git("commit", "-m", title, cwd=tree)
        body = (
            f"## Summary\n\nRegister `{key}` with public metadata and an empty claim.\n\n"
            "## FR-NFR covered\n\nFR-1, FR-5, FR-12.\n\n"
            "## How verified\n\nDocument and claim schemas pass; no PDF is included.\n\n"
            "## Not done & spec issues\n\n"
            "The owner must approve document identity and foundations.\n"
        )
        url = publish_pr(client, tree, branch, title, body, "register")
    return {"doc": key, "pr": url, "branch": branch}
