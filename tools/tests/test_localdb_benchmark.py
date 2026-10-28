"""Opt-in 100k-node API acceptance benchmark plus bounded graph regression cases."""

import copy
import json
import os
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import pytest
from fixture_support import BASELINE_DOCUMENTS

from homalg.index import assemble_index
from homalg.localdb import Database, build_artifacts_db
from homalg.schemas import load_yaml
from homalg.sitedata import build_site_data

ROOT = Path(__file__).resolve().parents[2]


def synthetic_artifacts(count: int, template: dict) -> dict:
    """Create explicitly synthetic public records with chapters, text and a real edge chain."""
    original = next(node for node in template["nodes"] if node["authored"]["kind"] == "theorem")
    key = "Benchmark2000"
    index = {
        **template,
        "nodes": [],
        "edges": [],
        "relations": [],
        "evolution": [],
        "document_graph": [],
    }
    document = copy.deepcopy(template["documents"][0]["document"])
    document.update(
        doc_key=key, year=2000, title="Synthetic local database benchmark", type="synthetic"
    )
    document.pop("pdf", None)
    chapters = defaultdict(list)
    for number in range(count):
        identifier = f"{key}.Thm_{number:06d}"
        chapter = str(number // 1000 + 1)
        chapters[chapter].append(identifier)
        name = f"{key}.theorem_{number:06d}"
        authored = {
            **original["authored"],
            "id": identifier,
            "doc": key,
            "decls": [name],
            "title": f"Synthetic theorem {number}",
            "statement_md": f"A derived functor witness group{number % 1000} is reflexive.",
            "description_md": (
                "Project-generated benchmark data; no real mathematical or review evidence."
            ),
            "source": {
                "label": f"Theorem {number}",
                "pages": [number // 1000 + 1],
                "chapter": chapter,
            },
            "fidelity": {"status": "faithful"},
            "deps": {"statement": [], "proof": []},
        }
        global_ = {
            **original["global"],
            "doc_title": document["title"],
            "doc_year": 2000,
            "doc_authors": ["Benchmark authors"],
            "rank": number % 1000,
            "dependents": [],
            "closure": {"blocked_by": []},
            "status": "proved",
            "headline": "proof-complete",
            "reopened": False,
        }
        derived = {
            **original["derived"],
            "file": {**original["derived"]["file"], "path": f"HomAlg/{key}/Thm_{number:06d}.lean"},
        }
        index["nodes"].append(
            {"id": identifier, "authored": authored, "derived": derived, "global": global_}
        )
        if number:
            previous = index["nodes"][-2]
            previous["global"]["dependents"] = [identifier]
            index["edges"].append(
                {
                    "from": identifier,
                    "to": previous["id"],
                    "kind": "proof",
                    "declared": True,
                    "verified": True,
                }
            )
    document["structure"] = [
        {
            "chapter": chapter,
            "title": f"Chapter {chapter}",
            "sections": [],
            "pages": {"first": int(chapter), "last": int(chapter)},
        }
        for chapter in chapters
    ]
    index["documents"] = [{"document": document, "claim": {"state": "unclaimed"}}]
    return build_site_data(
        index, {node["id"]: "-- Synthetic benchmark only.\n" for node in index["nodes"]}
    )


def template_index() -> dict:
    """Use the fixture index from the acceptance data generation step."""
    docs, nodes = [], []
    for key in BASELINE_DOCUMENTS:
        path = ROOT / "literature" / key / "document.yaml"
        document = load_yaml(path.read_text())
        docs.append({"document": document, "claim": {"state": "unclaimed"}})
        nodes.extend(json.loads((path.parent / "nodes.json").read_text())["nodes"])
    raw = json.loads((Path(__file__).parent / "golden/fixture-export.json").read_text())
    taxonomy = {
        name: load_yaml((ROOT / f"taxonomy/{name}.yaml").read_text())[name]
        for name in ("tags", "concepts")
    }
    return assemble_index(
        docs,
        nodes,
        [raw],
        taxonomy,
        [],
        [],
        commit="benchmark",
        repo_url="https://github.com/example/homalg-db",
        lean={"toolchain": raw["toolchain"], "mathlib_rev": raw["mathlib_rev"]},
    )


def test_recursive_cte_caps_unique_nodes_and_preserves_cycles(tmp_path: Path) -> None:
    artifacts = synthetic_artifacts(520, template_index())
    bundle = next(value for path, value in artifacts.items() if path.startswith("documents/"))
    root = "Benchmark2000.Thm_000000"
    bundle["edges"] = [
        {"from": node["id"], "to": root, "kind": "proof", "declared": True, "verified": True}
        for node in bundle["nodes"]
        if node["id"] != root
    ]
    bundle["edges"].append(
        {
            "from": root,
            "to": "Benchmark2000.Thm_000001",
            "kind": "statement",
            "declared": True,
            "verified": False,
        }
    )
    target = tmp_path / "cap.sqlite"
    build_artifacts_db(artifacts, target)
    edges, truncated = Database(target).neighbors(root, "down", 3)
    assert truncated
    assert len({endpoint for edge in edges for endpoint in (edge["from"], edge["to"])}) <= 500
    assert any(edge["from"] == root for edge in edges)
    result = Database(target).search({"deps": root, "dir": "down", "depth": 3})
    assert result["truncated"] and result["total"] <= 499


@pytest.mark.skipif(
    os.getenv("HOMALG_BENCHMARK") != "1", reason="Opt-in 100k-node performance acceptance"
)
def test_100k_api_search_and_chapter_latency(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from homalg.localserve import create_app

    started = perf_counter()
    artifacts = synthetic_artifacts(100000, template_index())
    artifact_seconds = perf_counter() - started
    target = tmp_path / "100k.sqlite"
    started = perf_counter()
    result = build_artifacts_db(artifacts, target)
    build_seconds = perf_counter() - started
    static = tmp_path / "static"
    static.mkdir()
    client = TestClient(create_app(static, target))
    query = "/api/search?q=group42&kind=theorem&sort=id"
    response = client.get(query)
    assert response.status_code == 200 and response.json()["total"] >= 100
    search_times = []
    chapter_times = []
    for _ in range(5):
        started = perf_counter()
        response = client.get(query)
        search_times.append(perf_counter() - started)
        assert response.status_code == 200
        started = perf_counter()
        response = client.get("/api/documents/Benchmark2000?chapter=42")
        chapter_times.append(perf_counter() - started)
        assert response.status_code == 200 and len(response.json()["nodes"]) == 1000
    measurement = {
        "nodes": 100000,
        "artifact_seconds": artifact_seconds,
        "database_seconds": build_seconds,
        "database_bytes": result["bytes"],
        "search_ms": [round(value * 1000, 3) for value in search_times],
        "chapter_ms": [round(value * 1000, 3) for value in chapter_times],
    }
    output = ROOT / "build/localdb-benchmark.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(measurement, indent=2) + "\n")
    print(json.dumps(measurement))
    assert max(search_times) < 0.2
    assert max(chapter_times) < 1.0
