"""Deterministic PR classification and field-level owner-approval decisions."""

import re
from collections.abc import Callable, Iterable
from typing import Any

from homalg.headers import parse_header
from homalg.schemas import load_yaml

DOCUMENT_PATH = re.compile(r"^(?:HomAlg/([^/]+)(?:/|\.lean$)|literature/([^/]+)/)")
SENSITIVE_FIELDS = {"doc_key", "year", "type", "foundations", "may_import"}
BASELINE_FIXTURES = {"Fixture2000", "Fixture2001"}


def document_keys(paths: Iterable[str], *, include_fixtures: bool = False) -> set[str]:
    """Project changed paths to document keys; fixed test documents are infrastructure."""
    result = set()
    for path in paths:
        match = DOCUMENT_PATH.match(path)
        if match:
            key = match.group(1) or match.group(2)
            if include_fixtures or key not in BASELINE_FIXTURES:
                result.add(key)
    return result


def classify_changed(
    paths: Iterable[str],
    labels: Iterable[str] = (),
    *,
    existing_documents: Iterable[str] = (),
    head_branch: str = "",
) -> dict[str, Any]:
    """Apply section 10.4's ordered classification, independent of GitHub event labels."""
    files, labels = set(paths), set(labels)
    if head_branch.startswith("status/"):
        raise ValueError("status branches are not merged")
    docs = document_keys(files)
    if {"lake-manifest.json", "lean-toolchain"} & files or "mathlib-bump" in labels:
        return {"kind": "mathlib-bump", "doc": None, "needs_lean": True}
    if len(docs) >= 2:
        return {"kind": "multi-doc", "doc": None, "needs_lean": True}
    if not docs:
        needs = any(
            path.startswith(("HomAlg/", "HomAlgExport/", "tools/homalg/checks/"))
            or path
            in {
                "lakefile.toml",
                "HomAlg.lean",
                "tools/homalg/leanexport.py",
                "tools/homalg/extract.py",
            }
            for path in files
        )
        return {"kind": "infra", "doc": None, "needs_lean": needs}
    key = next(iter(docs))
    if files == {f"literature/{key}/claim.yaml"}:
        return {"kind": "claim", "doc": key, "needs_lean": False}
    registration = {f"literature/{key}/document.yaml", f"literature/{key}/claim.yaml"}
    if files <= registration and key not in set(existing_documents):
        return {"kind": "register", "doc": key, "needs_lean": False}
    return {"kind": "formalization", "doc": key, "needs_lean": True}


def approval_reasons(
    paths: Iterable[str],
    base: Callable[[str], str | None],
    head: Callable[[str], str | None],
    *,
    labels: Iterable[str] = (),
    classification: dict[str, Any] | None = None,
    review_policy: dict[str, Any] | None = None,
) -> list[str]:
    """Find every sensitive change, including deletions and dispute history additions."""
    from homalg.review_policy import agent_reviews_allowed, foundation_confirmation_valid

    reasons = []
    if "taxonomy-maintenance" in labels:
        reasons.append("taxonomy-maintenance")
    if classification and classification["kind"] == "multi-doc":
        reasons.append("multi-doc")
    for path in sorted(paths):
        before, after = base(path), head(path)
        if re.fullmatch(r"literature/[^/]+/document\.yaml", path):
            old = load_yaml(before) if before is not None else {}
            new = load_yaml(after) if after is not None else {}
            if not isinstance(old, dict) or not isinstance(new, dict):
                raise ValueError(f"Invalid document metadata: {path}")
            sensitive = set(SENSITIVE_FIELDS)
            if agent_reviews_allowed(policy=review_policy or {}):
                old_foundations = {entry["notion"]: entry for entry in old.get("foundations", [])}
                new_foundations = {entry["notion"]: entry for entry in new.get("foundations", [])}
                retained = all(
                    notion in new_foundations
                    and (
                        entry == new_foundations[notion]
                        or (
                            not entry.get("confirmed_by")
                            and foundation_confirmation_valid(new_foundations[notion])
                        )
                    )
                    for notion, entry in old_foundations.items()
                )
                reviewed = all(
                    entry == old_foundations.get(notion) or foundation_confirmation_valid(entry)
                    for notion, entry in new_foundations.items()
                )
                if retained and reviewed:
                    sensitive.discard("foundations")
            if before is None or after is None or any(old.get(k) != new.get(k) for k in sensitive):
                reasons.append(f"sensitive-document:{path}")
        if re.fullmatch(r"HomAlg/[^/]+/[^/]+\.lean", path) and after is not None:
            old_header = parse_header(before).metadata if before is not None else {}
            new_header = parse_header(after).metadata
            old_disputes = [old_header.get("dispute", {}), *old_header.get("dispute_history", [])]
            new_disputes = [new_header.get("dispute", {}), *new_header.get("dispute_history", [])]
            if any(
                dispute.get("resolution", {}).get("via") == "proof-route"
                and dispute not in old_disputes
                for dispute in new_disputes
            ):
                reasons.append(f"proof-route-resolution:{path}")
            old_deviations = old_header.get("fidelity", {}).get("deviations", [])
            if any(dispute.get("confirmed_by") for dispute in new_disputes) and any(
                deviation.get("kind") == "proof-route" and deviation not in old_deviations
                for deviation in new_header.get("fidelity", {}).get("deviations", [])
            ):
                reasons.append(f"confirmed-dispute-route:{path}")
    return sorted(set(reasons))


def owner_approved(owner: str, author: str, head: str, reviews: Iterable[dict[str, Any]]) -> bool:
    """Require the owner's latest decisive review to approve the current head commit."""
    if owner.lower() == author.lower():
        return True
    decisions = [
        review
        for review in reviews
        if review.get("user", {}).get("login", "").lower() == owner.lower()
        and review.get("state") in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
    ]
    if not decisions:
        return False
    latest = max(
        decisions, key=lambda review: (review.get("submitted_at") or "", review.get("id", 0))
    )
    return latest.get("state") == "APPROVED" and latest.get("commit_id") == head


def append_only(before: dict[str, Any], after: dict[str, Any], field: str) -> bool:
    """Compare records by stable id, rejecting duplicates, removal and modification."""
    old_items, new_items = before.get(field, []), after.get(field, [])
    if not isinstance(old_items, list) or not isinstance(new_items, list):
        return False
    try:
        old = {item["id"]: item for item in old_items}
        new = {item["id"]: item for item in new_items}
    except (KeyError, TypeError):
        return False
    return (
        len(old) == len(old_items)
        and len(new) == len(new_items)
        and all(key in new and new[key] == value for key, value in old.items())
    )
