"""Explicit opt-in policy for independent agent reviews, preserving genuine human evidence."""

import hashlib
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from homalg.io import json_text
from homalg.schemas import SchemaStore, load_yaml

POLICY_PATH = "horizon/review-policy.yaml"


def read_policy(repo: Path) -> dict[str, Any]:
    """Read the tracked policy; absence keeps the original human review boundary."""
    path = repo / POLICY_PATH
    if not path.exists():
        return {"schema_version": 1, "allow_independent_agent_reviews": False}
    value = load_yaml(path.read_text())
    errors = SchemaStore(repo / "schema").validate(value, "review-policy.schema.json")
    if errors:
        raise ValueError(f"Invalid review policy: {errors[0].message}")
    return value


def agent_reviews_allowed(repo: Path | None = None, *, policy: dict | None = None) -> bool:
    """Accept a frozen ledger policy when supplied, never rereading live files in that case."""
    value = policy if policy is not None else read_policy(repo) if repo is not None else {}
    return (
        isinstance(value, dict)
        and type(value.get("schema_version")) is int
        and value["schema_version"] == 1
        and value.get("allow_independent_agent_reviews") is True
    )


def valid_agent_review(record: Any) -> bool:
    """Require explicit independent authorship and an actual dated satisfactory agent verdict."""
    if not isinstance(record, dict):
        return False
    if record.get("kind") != "agent" or record.get("status") != "satisfactory":
        return False
    if not all(
        isinstance(record.get(key), str) and record[key].strip()
        for key in ("by", "session", "author_session", "on")
    ):
        return False
    if record["session"].strip() == record["author_session"].strip():
        return False
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["on"])) and bool(
            date.fromisoformat(record["on"])
        )
    except ValueError:
        return False


def agent_review_record(
    repo: Path,
    *,
    by: str,
    session: str,
    author_session: str,
    now: datetime | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Validate authorization and independent session identities before returning new evidence."""
    if not agent_reviews_allowed(repo):
        raise ValueError(
            "Independent agent review substitution is disabled by the tracked review policy"
        )
    record = {
        "kind": "agent",
        "by": by.strip(),
        "status": "satisfactory",
        "on": (now or datetime.now(UTC)).date().isoformat(),
        "session": session.strip(),
        "author_session": author_session.strip(),
    }
    if note:
        record["note"] = note
    if not valid_agent_review(record):
        raise ValueError("An agent review requires distinct, nonempty reviewer and author sessions")
    return record


def foundation_hash(entry: dict[str, Any]) -> str:
    """Bind every source/content field, excluding only the mutable confirmation envelope."""
    content = {
        key: value
        for key, value in entry.items()
        if key not in {"status", "confirmation", "confirmed_by"}
    }
    return hashlib.sha256(json_text(content).encode()).hexdigest()


def foundation_confirmation_valid(entry: dict[str, Any]) -> bool:
    """Check the canonical independent verdict and its complete foundation-content fingerprint."""
    review = entry.get("confirmation")
    return (
        entry.get("status") == "confirmed"
        and not entry.get("confirmed_by")
        and valid_agent_review(review)
        and review.get("content_sha256") == foundation_hash(entry)
    )


def foundation_confirmed(
    entry: dict[str, Any],
    repo: Path | None = None,
    *,
    policy: dict | None = None,
) -> bool:
    """Honor existing human confirmations or current agent evidence under the effective policy."""
    if entry.get("status") != "confirmed":
        return False
    if entry.get("confirmed_by") and not entry.get("confirmation"):
        return True
    return agent_reviews_allowed(repo, policy=policy) and foundation_confirmation_valid(entry)


def early_review_valid(
    record: Any,
    repo: Path | None = None,
    *,
    policy: dict | None = None,
) -> bool:
    """Keep legacy human review records valid while requiring explicit policy for agent records."""
    if not isinstance(record, dict) or not record.get("by") or not record.get("on"):
        return False
    if record.get("kind") == "agent":
        return agent_reviews_allowed(repo, policy=policy) and valid_agent_review(record)
    return record.get("kind") in {None, "human"}


def require_report_provenance(text: str, *, session: str, author_session: str) -> None:
    """Bind latest verdicts to explicit sessions while preserving earlier review history."""
    headings = list(re.finditer(r"(?m)^##\s+(source-fidelity|honesty)\s+[—–-]\s+.+$", text))
    prefix = text[: headings[0].start()] if headings else text
    latest = {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        latest[heading.group(1)] = text[heading.end() : end]
    for body in latest.values() or [text]:
        for label, expected in (("Session", session), ("Author-session", author_session)):
            pattern = rf"(?mi)^{label}:\s*(\S[^\n]*)$"
            values = re.findall(pattern, body) or re.findall(pattern, prefix)
            if not values or any(value.strip() != expected.strip() for value in values):
                raise ValueError(f"Review report must explicitly record {label}: {expected}")
