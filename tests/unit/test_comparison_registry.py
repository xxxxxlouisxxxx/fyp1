"""Human review gates for explicit comparisons and isolated Bronze seeding."""

from __future__ import annotations

import csv
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from geo_research.domain.comparison import ComparisonMapping
from geo_research.registries.validators import (
    RegistryValidationError,
    load_comparisons,
    validate_registries,
)
from geo_research.storage.duckdb import DuckDBStore
from tests.unit.test_registry_validation import write_registries

ROOT = Path(__file__).resolve().parents[2]
HEADERS = [
    "comparison_id", "query_id", "prompt_id", "intent_id", "review_status",
    "reviewer", "reviewed_at", "active",
]
NOW = datetime(2026, 10, 6, tzinfo=UTC)
spec = importlib.util.spec_from_file_location(
    "comparison_bulk_runner", ROOT / "scripts/transform_all_raw.py"
)
assert spec and spec.loader
bulk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bulk)


def reviewed_row(**changes: str) -> dict[str, str]:
    row = dict(zip(HEADERS, [
        "comparison-1", "query-1", "prompt-1", "intent-1", "approved",
        "Research Reviewer", "2026-10-05T12:00:00Z", "true",
    ], strict=True))
    return row | changes


def write_comparisons(directory: Path, rows: list[dict[str, str]]) -> None:
    with (directory / "comparisons.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def seed(connection, directory: Path, provenance=None, used=None):
    connection.execute("CREATE SCHEMA IF NOT EXISTS meta")
    return bulk.seed_registries(
        connection, directory, provenance or {}, used or {}, NOW
    )


def test_valid_explicit_reviewed_mapping(tmp_path: Path) -> None:
    directory = write_registries(tmp_path)
    write_comparisons(directory, [reviewed_row()])
    result = validate_registries(directory)
    assert result.valid and result.counts["comparisons"] == 1
    mapping, = load_comparisons(directory, {"query-1"}, {"prompt-1"})
    assert mapping.intent_id == "intent-1"
    assert mapping.reviewed_at == datetime(2026, 10, 5, 12, tzinfo=UTC)


@pytest.mark.parametrize("active", ["true", "false"])
@pytest.mark.parametrize("field", ["query_id", "prompt_id"])
def test_comparison_crossrefs_required_even_for_candidates(
    tmp_path: Path, active: str, field: str
) -> None:
    directory = write_registries(tmp_path)
    write_comparisons(directory, [reviewed_row(**{field: "missing", "active": active})])
    with pytest.raises(RegistryValidationError, match=f"{field} does not exist"):
        validate_registries(directory)
    with pytest.raises(RegistryValidationError, match=f"{field} does not exist"):
        load_comparisons(directory, {"query-1"}, {"prompt-1"})


@pytest.mark.parametrize(("field", "value", "message"), [
    ("review_status", "pending", "approved"),
    ("review_status", "rejected", "approved"),
    ("review_status", "APPROVED", "approved"),
    ("reviewer", "", "named reviewer"),
    ("reviewer", "   ", "named reviewer"),
    ("reviewed_at", "", "timestamp"),
    ("reviewed_at", "not-a-timestamp", "reviewed_at"),
    ("reviewed_at", "2026-10-05", "timezone-aware"),
    ("reviewed_at", "2026-10-05T12:00:00", "timezone-aware"),
    ("reviewed_at", "2026-02-30T12:00:00Z", "reviewed_at"),
    ("intent_id", "", "identifier"),
    ("active", "yes", "boolean"),
])
def test_active_comparison_requires_human_evidence(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    directory = write_registries(tmp_path)
    write_comparisons(directory, [reviewed_row(**{field: value})])
    with pytest.raises(RegistryValidationError, match=message):
        validate_registries(directory)
    database = tmp_path / "working.duckdb"
    DuckDBStore(database).initialize()
    with duckdb.connect(str(database)) as connection:
        with pytest.raises(RegistryValidationError, match=message):
            seed(connection, directory)
        assert connection.execute(
            "SELECT count(*) FROM bronze.comparison_registry"
        ).fetchone() == (0,)


@pytest.mark.parametrize("active", ["true", "false"])
def test_duplicate_comparison_ids_rejected(tmp_path: Path, active: str) -> None:
    directory = write_registries(tmp_path)
    write_comparisons(directory, [reviewed_row(active=active)] * 2)
    with pytest.raises(RegistryValidationError, match="duplicate comparison_id"):
        validate_registries(directory)
    with pytest.raises(RegistryValidationError, match="duplicate comparison_id"):
        load_comparisons(directory, {"query-1"}, {"prompt-1"})


def test_duplicate_active_pairs_rejected_across_intents(tmp_path: Path) -> None:
    directory = write_registries(tmp_path)
    write_comparisons(directory, [
        reviewed_row(), reviewed_row(comparison_id="comparison-2", intent_id="intent-2")
    ])
    with pytest.raises(
        RegistryValidationError, match="duplicate active comparison pair"
    ):
        validate_registries(directory)
    with pytest.raises(
        RegistryValidationError, match="duplicate active comparison pair"
    ):
        load_comparisons(directory, {"query-1"}, {"prompt-1"})


def test_inactive_candidates_retained_but_not_seeded(tmp_path: Path) -> None:
    directory = write_registries(tmp_path)
    candidate = reviewed_row(
        active="false", review_status="pending", reviewer="", reviewed_at=""
    )
    write_comparisons(
        directory, [candidate, candidate | {"comparison_id": "candidate-2"}]
    )
    assert validate_registries(directory).counts["comparisons"] == 2
    before = (directory / "comparisons.csv").read_bytes()
    database = tmp_path / "working.duckdb"
    DuckDBStore(database).initialize()
    with duckdb.connect(str(database)) as connection:
        report = seed(connection, directory)
        assert report["counts"]["comparison_registry"] == 0
        assert connection.execute(
            "SELECT count(*) FROM bronze.comparison_registry"
        ).fetchone() == (0,)
        snapshots = connection.execute(
            "SELECT row_json FROM meta.registry_csv WHERE registry_name='comparisons'"
        ).fetchall()
        assert [json.loads(row[0]) for row in snapshots] == [
            candidate, candidate | {"comparison_id": "candidate-2"}
        ]
        assert sum(
            row["table"] == "comparison_registry" for row in report["excluded"]
        ) == 2
    assert (directory / "comparisons.csv").read_bytes() == before


def test_approved_mapping_seed_uses_exact_existing_schema(tmp_path: Path) -> None:
    directory = write_registries(tmp_path)
    write_comparisons(directory, [reviewed_row(), reviewed_row(
        comparison_id="candidate-2", active="false", review_status="pending",
        reviewer="", reviewed_at="",
    )])
    database = tmp_path / "working.duckdb"
    DuckDBStore(database).initialize()
    with duckdb.connect(str(database)) as connection:
        before = connection.execute(
            "PRAGMA table_info('bronze.comparison_registry')"
        ).fetchall()
        report = seed(connection, directory)
        assert report["counts"]["comparison_registry"] == 1
        assert connection.execute(
            "PRAGMA table_info('bronze.comparison_registry')"
        ).fetchall() == before
        assert [column[1] for column in before] == [
            "comparison_id", "query_id", "prompt_id", "active", "recorded_at"
        ]
        assert connection.execute(
            "SELECT * FROM bronze.comparison_registry"
        ).fetchall() == [("comparison-1", "query-1", "prompt-1", True, NOW)]
        snapshot = json.loads(connection.execute(
            "SELECT row_json FROM meta.registry_csv "
            "WHERE registry_name='comparisons' ORDER BY row_json LIMIT 1"
        ).fetchone()[0])
        assert "intent_id" in snapshot and "reviewer" in snapshot


@pytest.mark.parametrize("header_only", [False, True])
def test_legacy_fixtures_and_empty_csv_never_infer_comparisons(
    tmp_path: Path, header_only: bool
) -> None:
    directory = write_registries(tmp_path)
    # Same text is deliberately insufficient to authorize semantic equivalence.
    prompt_path = directory / "llm_prompts.csv"
    prompt_path.write_text(prompt_path.read_text(encoding="utf-8").replace(
        "Which research platform is best?", "research platform"
    ), encoding="utf-8")
    if header_only:
        write_comparisons(directory, [])
    assert validate_registries(directory).counts["comparisons"] == 0
    database = tmp_path / "working.duckdb"
    DuckDBStore(database).initialize()
    legacy = {"source": {"comparison_registry": [{
        "comparison_id": "legacy-1", "query_id": "query-1",
        "prompt_id": "prompt-1", "active": True, "recorded_at": NOW,
    }]}}
    with duckdb.connect(str(database)) as connection:
        report = seed(
            connection, directory, legacy, {"source": {"query-1", "prompt-1"}}
        )
        assert report["counts"]["comparison_registry"] == 0
        assert connection.execute(
            "SELECT count(*) FROM bronze.comparison_registry"
        ).fetchone() == (0,)
        assert any("reviewed CSV" in row["reason"] for row in report["excluded"])
    assert (directory / "comparisons.csv").exists() == header_only


def test_comparison_model_rejects_non_strict_fields() -> None:
    values = reviewed_row() | {"active": True}
    assert ComparisonMapping.model_validate(values).active
    with pytest.raises(ValidationError):
        ComparisonMapping.model_validate(reviewed_row())
    with pytest.raises(ValidationError):
        ComparisonMapping.model_validate(values | {"reviewer": 123})


def test_committed_comparison_csv_is_header_only() -> None:
    with (ROOT / "config/registries/comparisons.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == HEADERS
        assert list(reader) == []