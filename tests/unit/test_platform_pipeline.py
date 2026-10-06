"""Synthetic offline contracts; no paid APIs or production warehouses."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from geo_research.platform import pipeline


def test_runner_registers_module_for_postponed_dataclass_annotations(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "transform_all_raw.py").write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Record:\n"
        "    count: int = 1\n",
        encoding="utf-8",
    )
    old_path, old_bytecode = sys.path[:], sys.dont_write_bytecode
    module = pipeline._runner(tmp_path)
    try:
        assert sys.modules[module.__name__] is module
        assert module.Record().count == 1
        assert sys.path == old_path
        assert sys.dont_write_bytecode is old_bytecode
        assert not (scripts / "__pycache__").exists()
    finally:
        sys.modules.pop(module.__name__, None)


def test_runner_failed_import_removes_registration_and_restores_state(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "transform_all_raw.py").write_text(
        "import sys\n"
        "sys.path.append('synthetic-import-path')\n"
        "raise RuntimeError('synthetic import failure')\n",
        encoding="utf-8",
    )
    old_modules = set(sys.modules)
    old_path, old_bytecode = sys.path[:], sys.dont_write_bytecode
    with pytest.raises(RuntimeError, match="synthetic import failure"):
        pipeline._runner(tmp_path)
    assert not any(name.startswith("_platform_offline_")
                   for name in set(sys.modules) - old_modules)
    assert sys.path == old_path
    assert sys.dont_write_bytecode is old_bytecode
    assert not (scripts / "__pycache__").exists()


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    raw = root / "data/raw/serp/dataforseo/google/2026/09/28/run/request"
    raw.mkdir(parents=True)
    (raw / "request.json").write_text('{}')
    response = {"tasks": [{"status_code": 20000, "result": [{"items": []}]}]}
    (raw / "response.json").write_text(json.dumps(response))
    files = {name: {"sha256": pipeline._hash(raw / name),
                    "byte_size": (raw / name).stat().st_size}
             for name in ("request.json", "response.json")}
    (raw / "metadata.json").write_text(json.dumps({
        "provider": "dataforseo", "platform_or_engine": "google", "files": files,
    }))
    registries = root / "config/registries"
    registries.mkdir(parents=True)
    (registries / "brands.csv").write_text(
        "brand_id,ownership_type\nb,TO_BE_VERIFIED\n"
    )
    (registries / "brand_aliases.csv").write_text("brand_id,alias_text\nb,Brand\n")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "transform_all_raw.py").write_text("# synthetic runner\n")
    calls = []

    def audit_raw(raw_root, raw_date=None):
        rows = []
        for path in sorted(raw_root.rglob("*.json")):
            if raw_date and path.relative_to(raw_root).parts[3:6] != tuple(
                raw_date.strftime("%Y/%m/%d").split("/")
            ):
                continue
            metadata = json.loads(path.with_name("metadata.json").read_text())
            valid = all(pipeline._hash(path.with_name(name)) == item["sha256"]
                        for name, item in metadata["files"].items())
            rows.append({"path": str(path.relative_to(raw_root)),
                         "role": path.stem, "category": "serp", "json_valid": True,
                         "triple_valid": valid, "sha256": pipeline._hash(path)})
        return rows

    def run(work, *, raw_date=None):
        calls.append((work, raw_date))
        database = work / "data/warehouse/new.duckdb"
        database.parent.mkdir(parents=True, exist_ok=True)
        database.write_bytes(b"synthetic warehouse")
        export = work / "data/exports/new"
        export.mkdir(parents=True)
        summary = {"database": str(database), "export": str(export),
                   "raw_unchanged": True, "publication": False,
                   "response_evidence_observations": 1}
        (export / "summary.json").write_text(json.dumps(summary))
        return summary

    runner = SimpleNamespace(
        audit_raw=audit_raw, run=run, supported_serp_engines=lambda: {"google"},
        envelope=lambda payload: ("direct", payload),
        provider_status=lambda block: (
            "no_results" if not block["tasks"][0]["result"] else "available",
            block["tasks"][0], {},
        ),
    )
    monkeypatch.setattr(pipeline, "_runner", lambda _: runner)
    return root, tmp_path / "output", raw, runner, calls


def test_audit_is_dry_and_counts_response_not_query_rows(project):
    root, output, _, _, calls = project
    before = pipeline._snapshot(root, None)
    result = pipeline.audit_project(root, output, "2026-09-28")
    assert result["status"] == "success"
    assert result["audit"]["response_coverage"] == {
        "success": 0, "empty": 1, "failure": 0, "unsupported": 0,
    }
    assert result["audit"]["file_count"] == 3
    assert result["source_unchanged"] and not calls
    assert pipeline._snapshot(root, None) == before
    assert not (root / "data/warehouse").exists()
    assert not result["tests"]["executed"] and not result["api_calls"]
    assert result["registry_approval_gaps"]


def test_repeat_reuses_only_hashed_outputs_in_new_database(project):
    root, output, _, _, calls = project
    first = pipeline.run_pipeline(root, output)
    second = pipeline.run_pipeline(
        root, output, previous_manifest=Path(first["manifest_path"])
    )
    assert first["status"] == second["status"] == "success"
    assert len(calls) == 1
    assert first["outputs"]["database"] != second["outputs"]["database"]
    assert all(step["status"] == "reused" for step in second["steps"])
    assert Path(first["outputs"]["database"]).exists()
    assert first["input_hashes"] == second["input_hashes"]


@pytest.mark.parametrize("relative", [
    "config/registries/brand_aliases.csv", "scripts/transform_all_raw.py",
])
def test_registry_and_code_changes_invalidate_reuse(project, relative):
    root, output, _, _, calls = project
    first = pipeline.run_pipeline(root, output)
    path = root / relative
    path.write_text(path.read_text() + "\n")
    second = pipeline.run_pipeline(
        root, output, previous_manifest=Path(first["manifest_path"])
    )
    assert second["status"] == "success" and len(calls) == 2
    assert second["compatibility_hash"] != first["compatibility_hash"]
    assert "reused_manifest" not in second


def test_evidence_only_requires_compatible_upstream(project):
    root, output, _, _, calls = project
    missing = pipeline.run_pipeline(root, output, stages=("evidence",))
    assert missing["status"] == "failed" and not calls
    first = pipeline.run_pipeline(root, output, stages=("normalize",))
    assert [step["stage"] for step in first["steps"]] == ["normalize", "evidence"]
    second = pipeline.run_pipeline(root, output, stages=("evidence",),
                                   previous_manifest=Path(first["manifest_path"]))
    assert second["status"] == "success" and len(calls) == 1


def test_tampered_output_and_schema_safe_rebuild(project):
    root, output, _, _, calls = project
    first = pipeline.run_pipeline(root, output)
    Path(first["outputs"]["database"]).write_bytes(b"tampered")
    second = pipeline.run_pipeline(
        root, output, previous_manifest=Path(first["manifest_path"])
    )
    assert second["status"] == "success" and len(calls) == 2
    manifest_path = Path(second["manifest_path"])
    second["schema_version"] = "old"
    manifest_path.write_text(json.dumps(second))
    third = pipeline.run_pipeline(root, output, previous_manifest=manifest_path)
    assert third["status"] == "success" and len(calls) == 3


@pytest.mark.parametrize("relative", [
    "data/raw/exports", "data/warehouse/new", "data/input/new", "config/new",
])
def test_protected_output_rejected_before_writes(project, relative):
    root, _, _, _, calls = project
    with pytest.raises(ValueError, match="protected"):
        pipeline.run_pipeline(root, root / relative)
    assert not calls and not (root / relative).exists()


def test_failure_manifest_and_no_source_mutation(project):
    root, output, _, runner, _ = project
    before = pipeline._snapshot(root, None)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    runner.run = fail
    result = pipeline.run_pipeline(root, output)
    persisted = json.loads(Path(result["manifest_path"]).read_text())
    assert persisted["status"] == "failed"
    assert "synthetic failure" in persisted["error"]
    assert persisted["steps"][0]["status"] == "failed"
    assert pipeline._snapshot(root, None) == before


def test_date_scope_empty_and_input_tamper(project):
    root, output, raw, _, _ = project
    empty = pipeline.audit_project(root, output, "2026-09-29")
    assert empty["status"] == "partial" and not empty["input_hashes"]
    (raw / "response.json").write_text("{}")
    invalid = pipeline.audit_project(root, output)
    assert invalid["audit"]["response_coverage"]["failure"] == 1
    assert invalid["status"] == "partial"


def test_invalid_stage_and_date(project):
    root, output, _, _, _ = project
    with pytest.raises(ValueError):
        pipeline.run_pipeline(root, output, stages=("collect",))
    with pytest.raises(ValueError):
        pipeline.audit_project(root, output, "20260928")


def test_scoped_guard_hashes_each_relevant_file_once(project, monkeypatch):
    from datetime import date

    root, _, _, _, _ = project
    warehouse = root / "data/warehouse"
    warehouse.mkdir()
    (warehouse / "geo_research.duckdb").write_bytes(b"baseline")
    (warehouse / "raw_full_old.duckdb").write_bytes(b"excluded derived data")
    (warehouse / "phase_c_gold.duckdb").write_bytes(b"excluded alternate")
    unrelated = root / "data/raw/serp/dataforseo/google/2026/09/29/r/q"
    unrelated.mkdir(parents=True)
    (unrelated / "response.json").write_text("{}")
    calls = []
    original = pipeline._hash

    def track(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(pipeline, "_hash", track)
    snapshot = pipeline._snapshot(root, date(2026, 9, 28))
    assert len(calls) == len(set(calls))
    assert snapshot["provenance_hashes"] == {
        "data/warehouse/geo_research.duckdb": original(
            warehouse / "geo_research.duckdb"
        )
    }
    assert unrelated / "response.json" not in calls
    assert warehouse / "raw_full_old.duckdb" not in calls
    assert warehouse / "phase_c_gold.duckdb" not in calls
    assert "data/warehouse/raw_full_old.duckdb" in snapshot["source_metadata_guard"]


def test_baseline_mutation_invalidates_reuse(project):
    root, output, _, _, calls = project
    warehouse = root / "data/warehouse"
    warehouse.mkdir()
    baseline = warehouse / "geo_research.duckdb"
    baseline.write_bytes(b"baseline")
    first = pipeline.run_pipeline(root, output)
    baseline.write_bytes(b"changed baseline")
    second = pipeline.run_pipeline(root, output,
                                   previous_manifest=Path(first["manifest_path"]))
    assert second["status"] == "success" and len(calls) == 2
    assert second["compatibility_hash"] != first["compatibility_hash"]


def test_outside_scope_metadata_mutation_is_detected(project):
    root, output, _, runner, _ = project
    legacy = root / "data/warehouse/raw_full_old.duckdb"
    legacy.parent.mkdir()
    legacy.write_bytes(b"old")
    original = runner.audit_raw

    def mutating_audit(*args, **kwargs):
        legacy.write_bytes(b"changed outside content scope")
        return original(*args, **kwargs)

    runner.audit_raw = mutating_audit
    result = pipeline.audit_project(root, output, "2026-09-28")
    assert result["status"] == "failed"
    assert result["source_unchanged"] is False


def test_changed_registry_blocks_evidence_only(project):
    root, output, _, _, calls = project
    first = pipeline.run_pipeline(root, output)
    (root / "config/registries/brand_aliases.csv").write_text(
        "brand_id,alias_text\nb,Changed\n"
    )
    result = pipeline.run_pipeline(root, output, stages=("evidence",),
                                   previous_manifest=Path(first["manifest_path"]))
    assert result["status"] == "failed" and len(calls) == 1


def test_changed_scope_blocks_evidence_only(project):
    root, output, _, _, calls = project
    first = pipeline.run_pipeline(root, output)
    result = pipeline.run_pipeline(root, output, raw_date="2026-09-28",
                                   stages=("evidence",),
                                   previous_manifest=Path(first["manifest_path"]))
    assert result["status"] == "failed" and len(calls) == 1


def test_unsupported_provider_and_pending_are_not_success(project):
    root, output, raw, runner, _ = project
    metadata = json.loads((raw / "metadata.json").read_text())
    metadata["provider"] = "unknown"
    (raw / "metadata.json").write_text(json.dumps(metadata))
    result = pipeline.audit_project(root, output)
    assert result["audit"]["response_coverage"]["unsupported"] == 1
    metadata["provider"] = "dataforseo"
    (raw / "metadata.json").write_text(json.dumps(metadata))
    runner.provider_status = lambda block: ("pending", block["tasks"][0], {})
    result = pipeline.audit_project(root, output)
    assert result["audit"]["response_coverage"]["failure"] == 1


def test_missing_runner_evidence_confirmation_fails(project):
    root, output, _, runner, _ = project
    original = runner.run

    def without_evidence(*args, **kwargs):
        result = original(*args, **kwargs)
        result.pop("response_evidence_observations")
        return result

    runner.run = without_evidence
    result = pipeline.run_pipeline(root, output)
    assert result["status"] == "failed"
    assert "evidence enrichment" in result["error"]


@pytest.fixture
def review_database(tmp_path):
    path = tmp_path / "review.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA presentation")
        connection.execute(
            "CREATE TABLE presentation.platform_documents "
            "(kind VARCHAR, status VARCHAR, payload_json VARCHAR)"
        )
        for status, opportunity in (("completed", "known"), ("draft", "unfinished")):
            connection.execute(
                "INSERT INTO presentation.platform_documents VALUES (?, ?, ?)",
                ["opportunities", status, json.dumps({
                    "opportunities": [{"opportunity_id": opportunity}],
                })],
            )
    return path


def test_review_unknown_and_invalid_state_rejected(review_database):
    for opportunity in ("unknown", "unfinished", "known' OR 1=1 --"):
        with pytest.raises(ValueError, match="unknown opportunity"):
            pipeline.review_opportunity(
                review_database, opportunity, status="draft", owner="analyst", notes=""
            )
    with pytest.raises(ValueError, match="status"):
        pipeline.review_opportunity(
            review_database, "known", status="automatic", owner="analyst", notes=""
        )
    with duckdb.connect(str(review_database), read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='governance'"
        ).fetchone()[0] == 0


def test_review_durable_additive_history_and_parameterized_notes(review_database):
    notes = "human review '); DROP TABLE presentation.platform_documents; --"
    for status in (
        "draft", "under_review", "approved", "rejected", "snoozed", "completed",
    ):
        result = pipeline.review_opportunity(
            review_database, "known", status=status, owner="analyst", notes=notes
        )
        assert result["status"] == status
    with duckdb.connect(str(review_database), read_only=True) as connection:
        rows = connection.execute(
            "SELECT status, notes FROM governance.platform_opportunity_reviews "
            "ORDER BY reviewed_at"
        ).fetchall()
        assert len(rows) == 6 and rows[-1] == ("completed", notes)
        assert connection.execute(
            "SELECT count(*) FROM presentation.platform_documents"
        ).fetchone()[0] == 2


@pytest.mark.parametrize("release_table", ["releases", "platform_releases"])
def test_review_completed_release_contract(tmp_path, release_table):
    path = tmp_path / "released.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA presentation")
        connection.execute(
            f"CREATE TABLE presentation.{release_table} "
            "(release_id VARCHAR, status VARCHAR)"
        )
        connection.execute(
            f"INSERT INTO presentation.{release_table} "
            "VALUES ('done', 'completed')"
        )
        if release_table == "platform_releases":
            # Conflicting legacy metadata must not override platform completion.
            connection.execute(
                "CREATE TABLE presentation.releases "
                "(release_id VARCHAR, status VARCHAR)"
            )
            connection.execute(
                "INSERT INTO presentation.releases VALUES ('done', 'draft')"
            )
        connection.execute(
            "CREATE TABLE presentation.platform_documents "
            "(release_id VARCHAR, kind VARCHAR, document_json VARCHAR)"
        )
        connection.execute(
            "INSERT INTO presentation.platform_documents VALUES (?, ?, ?)",
            ["done", "opportunities", '[{"opportunity_id":"known"}]'],
        )
    assert pipeline.review_opportunity(
        path, "known", status="draft", owner="analyst", notes="manual"
    )["status"] == "draft"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            f"UPDATE presentation.{release_table} SET status='draft'"
        )
        if release_table == "platform_releases":
            connection.execute(
                "UPDATE presentation.releases SET status='completed'"
            )
    with pytest.raises(ValueError, match="unknown opportunity"):
        pipeline.review_opportunity(
            path, "known", status="draft", owner="analyst", notes="manual"
        )