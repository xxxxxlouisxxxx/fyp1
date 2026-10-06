"""Synthetic-only acceptance contract; no production inputs or terminal calls."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import duckdb
import pytest

from geo_research.dashboard.platform import VIEWS, load_platform_snapshot

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/platform_acceptance_demo.py"
SPEC = importlib.util.spec_from_file_location("platform_acceptance_demo", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "isolated_project"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\nname='synthetic-demo'\n", encoding="utf-8"
    )
    return root


def test_demo_two_releases_read_only_five_views_and_no_overwrite(project: Path) -> None:
    output = project / "data/exports/acceptance"
    report = demo.run_demo(project, output)
    database = Path(report["paths"]["database"])
    assert report["is_synthetic"] is True
    assert report["health"] == "blocked-on-production-registries"
    assert report["fixture_observations"] == {"serp": 3, "llm": 3}
    assert report["first_release"]["status"] == "completed"
    assert report["second_release"]["status"] == "completed"
    assert report["checks"]["first_release_unchanged"] is True
    assert report["checks"]["published_synthetic_provenance_complete"] is True
    assert json.loads((output / "acceptance_report.json").read_text()) == report
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    first = load_platform_snapshot(database, demo.FIRST_RELEASE)
    second = load_platform_snapshot(database, demo.SECOND_RELEASE)
    assert first.message is None and second.message is None
    assert load_platform_snapshot(database).release["release_id"] == demo.SECOND_RELEASE
    assert len(VIEWS) == 5
    # Actual document contracts consumed by the five views, not pretend SQL views.
    required = {
        "coverage": {"document_id", "release_id"},
        "registries": {"table", "rows", "registry_sha256"},
        "metrics": {"brand_id", "feature", "numerator", "denominator", "metric_value",
                    "language_code", "location_code", "collection_window", "run_ids"},
        "comparisons": {"comparison_eligibility", "serp", "llm", "metric_value"},
        "evidence": {"observation_id", "request_id", "response_id", "raw_file_hash",
                     "items", "citations", "matches"},
        "opportunities": {"review_status", "classification", "evidence_result_ids"},
    }
    for snapshot in (first, second):
        for kind, columns in required.items():
            assert not snapshot.frames[kind].empty
            assert columns <= set(snapshot.frames[kind].columns)
        assert all(row["classification"] == "exploratory_hypothesis"
                   for row in snapshot.records["opportunities"])
        for kind in ("metrics", "evidence", "comparisons", "opportunities"):
            for row in snapshot.records[kind]:
                assert row["is_synthetic"] is True, (kind, row["document_id"])
                assert row["source_provenance"], (kind, row["document_id"])
                assert not row.get("synthetic_metadata_conflict")
        for row in snapshot.records["evidence"]:
            traces = [json.loads(value) for value in row["source_provenance"]]
            assert any(trace.get("fixture_id") == row["observation_id"]
                       and trace.get("request_id") == row["request_id"]
                       and trace.get("raw_file_hash") == row["raw_file_hash"]
                       and trace.get("disclaimer") == demo.DISCLAIMER
                       for trace in traces)
    llm = [row for row in first.records["metrics"]
           if row["source_category"] == "llm" and row["feature"] == "answer_text"]
    assert llm[0]["denominator"] == 3
    assert llm[0]["numerator"] == 2
    assert llm[0]["complete_run_count"] == 3
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute(
            "SELECT count(*) FROM meta.schema_migrations"
        ).fetchone()[0] == 9
        assert con.execute(
            "SELECT count(*) FROM silver.evidence_results_v2"
        ).fetchone()[0] == 6
        assert con.execute(
            "SELECT count(DISTINCT run_id) FROM bronze.api_requests"
        ).fetchone()[0] == 6
        assert con.execute(
            "SELECT is_synthetic FROM bronze.brand_registry"
        ).fetchone() == (True,)
        metadata = con.execute(
            "SELECT request_id, metadata_json FROM bronze.api_requests"
        ).fetchall()
        assert len(metadata) == 6
        for request_id, encoded in metadata:
            source = json.loads(encoded)
            assert source["is_synthetic"] is True
            assert source["synthetic_provenance"]["request_id"] == request_id
        assert con.execute("SELECT count(*) FROM bronze.raw_files").fetchone()[0] == 0
    with pytest.raises(ValueError, match="already exists"):
        demo.run_demo(project, output)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not (project / "data/raw").exists()
    assert not (project / "data/warehouse").exists()
    assert not (project / "config").exists()


def test_review_freeze_gate_is_not_fabricated(project: Path) -> None:
    report = demo.run_demo(project, Path("data/exports/review-contract"))
    checks = report["checks"]
    if checks["review_status_frozen_in_new_release"]:
        assert report["review"]["status"] == "under_review"
        assert checks["first_review_status"] == "unreviewed"
        assert checks["second_review_status"] == "under_review"
        assert report["status"] == "synthetic-contract-passed"
        assert report["blockers"] == []
    else:
        assert report["status"] == "blocked"
        assert (
            "publisher does not freeze the recorded review status" in report["blockers"]
        )


@pytest.mark.parametrize("flag,provenance", [
    (None, ["trace"]), (False, ["trace"]), ("true", ["trace"]), (True, []),
])
def test_demo_rejects_unknown_or_missing_published_trace(flag, provenance) -> None:
    documents = [(kind, kind, json.dumps({
        "is_synthetic": flag, "source_provenance": provenance,
    })) for kind in ("metrics", "evidence", "comparisons", "opportunities")]
    before = list(documents)
    with pytest.raises(ValueError, match="missing explicit synthetic trace"):
        demo._assert_synthetic_documents(documents)
    assert documents == before  # Gate cannot relabel frozen documents.


def test_demo_provenance_failure_blocks_report(project: Path, monkeypatch) -> None:
    original = demo._documents

    def missing_trace(database, release):
        records = original(database, release)
        return [(kind, identity,
             json.dumps({**json.loads(payload), "is_synthetic": None})
             if kind == "evidence" else payload)
                for kind, identity, payload in records]

    monkeypatch.setattr(demo, "_documents", missing_trace)
    report = demo.run_demo(project, Path("data/exports/missing-trace"))
    assert report["status"] == "blocked"
    assert any("missing explicit synthetic trace: evidence/" in blocker
               for blocker in report["blockers"])


@pytest.mark.parametrize("relative", ["data/raw/demo", "data/warehouse/demo",
                                      "config/demo", "outside", "data/exports"])
def test_protected_or_non_export_paths_rejected(project: Path, relative: str) -> None:
    output = project / relative
    with pytest.raises(ValueError):
        demo.run_demo(project, output)
    assert not output.exists()


def test_existing_database_and_cli_required_output(project: Path) -> None:
    output = project / "data/exports/existing"
    output.mkdir(parents=True)
    database = output / demo.DATABASE_NAME
    database.write_bytes(b"must not overwrite")
    assert demo.main(["--project", str(project), "--output", str(output)]) == 2
    assert database.read_bytes() == b"must not overwrite"
    with pytest.raises(SystemExit) as exc:
        demo.main(["--project", str(project)])
    assert exc.value.code == 2