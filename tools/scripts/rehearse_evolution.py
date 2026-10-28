"""Reproduce the source-grounded interactive-agent import in an isolated repository."""

import argparse
import json
import shutil
from pathlib import Path

from homalg.evolution.bundle import build_bundle
from homalg.evolution.importer import import_output
from homalg.io import atomic_write, json_text
from homalg.schemas import SchemaStore, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("build/evolution/rehearsal-repository"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads((root / "docs/evolution/hochschild-evidence.json").read_text())
    output = json.loads((root / "docs/evolution/hochschild-output.json").read_text())
    if evidence["kind"] != "editorial-evidence-draft":
        raise ValueError("Expected the explicitly unreviewed source-evidence draft")
    store = SchemaStore(root / "schema")
    for doc in evidence["documents"]:
        errors = store.validate(doc, "document.schema.json")
        if errors:
            raise ValueError(errors[0].message)
    destination = (root / args.out).resolve()
    if not destination.is_relative_to(root / "build"):
        raise ValueError(
            "Rehearsal output must stay under this repository's ignored build directory"
        )
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "schema", destination / "schema", dirs_exist_ok=True)
    (destination / "taxonomy").mkdir(exist_ok=True)
    atomic_write(
        destination / "taxonomy/concepts.yaml",
        json_text({"schema_version": 1, "concepts": [evidence["concept"]]}),
    )
    inputs = {
        "concepts": [evidence["concept"]],
        "documents": [{"document": doc} for doc in evidence["documents"]],
        "nodes": evidence["nodes"],
        "relations": [],
        "evolution": [],
        "generator": {"commit": "uncommitted-source-rehearsal"},
    }
    bundle = build_bundle(inputs, "cohomology", repo=root)
    atomic_write(destination / "cohomology.bundle.json", json_text(bundle))
    result = import_output(
        destination, output, bundle, model="not-reported", by="interactive-codex-session"
    )
    summary = load_yaml(Path(result["summary_file"]).read_text())
    imported = next(item for item in summary["summaries"] if item["version"] == result["version"])
    if imported["review"]["status"] != "unreviewed":
        raise ValueError("A newly imported summary must remain unreviewed")
    artifact = {
        "concept": "cohomology",
        "current_bundle_sha256": bundle["bundle_sha256"],
        "summaries": [item | {"stale": False} for item in summary["summaries"]],
    }
    errors = store.validate(artifact, "site/evolution.schema.json")
    if errors:
        raise ValueError(errors[0].message)
    atomic_write(destination / "cohomology.site.json", json_text(artifact))
    print(
        json_text(
            result
            | {
                "bundle_sha256": bundle["bundle_sha256"],
                "model_calls": 0,
                "generation": "interactive session; exact model not reported",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
