# ruff: noqa: E501
"""Isolated synthetic provenance only; no production evidence or paid calls."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from geo_research.platform.analytics import assess_v1, publish_v1
from geo_research.storage.duckdb import DuckDBStore
from geo_research.transforms.feature_evidence import enrich_features, persist_features


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.duckdb"
    DuckDBStore(path).initialize()
    with duckdb.connect(str(path)) as con:
        con.execute("""
            CREATE TABLE bronze.brand_registry (
                brand_id VARCHAR PRIMARY KEY, canonical_name VARCHAR,
                ownership_type VARCHAR, active BOOLEAN,
                effective_start_date DATE, effective_end_date DATE,
                review_status VARCHAR, provenance VARCHAR
            );
            CREATE TABLE bronze.brand_domain_registry (
                brand_id VARCHAR, domain VARCHAR, provenance VARCHAR
            );
            CREATE TABLE bronze.brand_alias_registry (
                brand_id VARCHAR, alias_text VARCHAR
            );
            INSERT INTO bronze.brand_registry VALUES
                ('atlas', 'Atlas', 'owned', true, '2026-01-01', NULL,
                 'approved', 'synthetic unit-test provenance; not production');
            INSERT INTO bronze.brand_domain_registry VALUES
                ('atlas', 'atlas.invalid', 'synthetic unit-test ownership');
            INSERT INTO bronze.comparison_registry VALUES
                ('synthetic-map', 'query', 'prompt', true, current_timestamp);
            INSERT INTO presentation.release_current VALUES ('current', 'legacy');
        """)
    return path


def add(
    path: Path, identity: str, category: str = "llm", *, text: str = "Atlas Atlas",
    window: str | None = "2026-10", language: str | None = "en",
    location: str | None = "2344", run: str | None = None,
    serp_items: list[dict[str, Any]] | None = None,
) -> None:
    instrument = "query" if category == "serp" else "prompt"
    engine = "google" if category == "serp" else "gemini"
    registry: dict[str, Any] = {
        "brands": {"atlas": {"brand_id": "atlas", "canonical_name": "Atlas"}},
        "aliases": [], "domains": [{"brand_id": "atlas", "domain": "atlas.invalid"}],
        "version": "synthetic-approved-v1",
    }
    context: dict[str, Any] = {
        "observation_id": identity, "request_id": f"req-{identity}",
        "response_id": f"resp-{identity}", "raw_file_hash": f"synthetic-hash-{identity}",
        "source_category": category, "collection_status": "available",
        "collected_at": "2026-10-06T00:00:00+00:00", "provider": "synthetic",
        "engine_or_platform": engine, "model_name": "synthetic-model",
    }
    items = [{"type": "gemini_text", "original_text": text, "sources": [
        {"url": "https://atlas.invalid/source", "snippet": "Atlas source-only"}
    ]}]
    if category == "serp":
        items = serp_items if serp_items is not None else [{"type": "organic", "rank_group": 1, "rank_absolute": 1,
                  "url": "https://other.invalid/", "title": "Atlas title not owned"}]
    payload = {"tasks": [{"status_code": 20000, "data": {
        "keyword": "synthetic instrument", "language_code": language,
        "location_code": location, "device": "desktop", "os": "windows",
    }, "result": [{"items": items, "sources": []}]}]}
    evidence = enrich_features(context, payload, registry)
    with duckdb.connect(str(path)) as con:
        con.execute("""
            INSERT INTO bronze.api_requests
                (request_id, run_id, source_category, provider, platform,
                 search_engine, model_name, request_status, created_at,
                 query_id, collection_window)
            VALUES (?, ?, ?, 'synthetic', ?, ?, 'synthetic-model',
                    'completed', current_timestamp, ?, ?)
        """, [f"req-{identity}", run or f"synthetic-run-{identity}", category,
              engine if category == "llm" else None,
              engine if category == "serp" else None, instrument, window])
        persist_features(con, evidence)


def documents(path: Path, release: str, kind: str) -> list[dict[str, Any]]:
    with duckdb.connect(str(path), read_only=True) as con:
        return [json.loads(row[0]) for row in con.execute(
            "SELECT payload_json FROM presentation.platform_documents "
            "WHERE release_id=? AND kind=? ORDER BY document_id", [release, kind]
        ).fetchall()]


def metric(path: Path, release: str, feature: str, category: str = "llm") -> dict[str, Any]:
    return next(row for row in documents(path, release, "metrics")
                if row["feature"] == feature and row["source_category"] == category)


def comparison(path: Path, release: str, *, textual: bool = False) -> dict[str, Any]:
    kind = "textual_presence_vs_answer_presence" if textual else "owned_organic_vs_answer_presence"
    return next(row for row in documents(path, release, "comparisons") if row["comparison_kind"] == kind)


def test_missing_database_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "missing.duckdb"
    assert assess_v1(path)["reasons"] == ["database_missing"]
    with pytest.raises(ValueError, match="database_missing"):
        publish_v1(path, "missing")
    assert not path.exists()


def test_failed_empty_publication_and_placeholder_gate(database: Path) -> None:
    report = assess_v1(database)
    assert not report["complete"]
    assert "no_underlying_evidence" in report["reasons"]
    with pytest.raises(ValueError, match="publication blocked"):
        publish_v1(database, "empty")
    add(database, "llm")
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE bronze.brand_registry SET canonical_name='TO_BE_VERIFIED'")
    report = assess_v1(database)
    assert report["counts"]["approved_brands"] == 0
    assert "no_approved_metrics" in report["reasons"]
    with pytest.raises(ValueError, match="no_approved_brands"):
        publish_v1(database, "placeholder")
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute("SELECT * FROM presentation.release_current").fetchall() == [("current", "legacy")]
        assert not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name='platform_releases'").fetchall()


def test_success_contract_synthetic_provenance_and_denominators(database: Path) -> None:
    add(database, "llm")
    add(database, "serp", "serp")
    report = publish_v1(database, "v1")
    assert report["complete"] and report["status"] == "completed"
    assert report["human_review_required"] and "human_review_missing" in report["warnings"]
    assert set(report["document_counts"]) == {"coverage", "metrics", "comparisons", "evidence", "opportunities", "registries"}
    answer = metric(database, "v1", "answer_text")
    assert (answer["numerator"], answer["denominator"], answer["observed_brand_count"]) == (1, 1, 2)
    assert metric(database, "v1", "citation")["observed_brand_count"] == 1
    assert metric(database, "v1", "organic", "serp")["metric_value"] == 0
    assert metric(database, "v1", "organic")["metric_value"] is None
    assert comparison(database, "v1")["comparison_eligibility"] == "matched_context"
    card = documents(database, "v1", "opportunities")[0]
    assert card["pattern"] == "llm_present_serp_absent"
    assert card["classification"] == "exploratory_hypothesis"
    registries = documents(database, "v1", "registries")
    assert "synthetic unit-test provenance" in json.dumps(registries)
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute("SELECT * FROM presentation.platform_current").fetchall() == [("current", "v1")]
        assert con.execute("SELECT * FROM presentation.release_current").fetchall() == [("current", "legacy")]


def test_partial_positive_independent_features_and_distinct_runs(database: Path) -> None:
    add(database, "one", run="shared-run")
    add(database, "two", run="shared-run")
    add(database, "partial")
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE silver.evidence_features_v2 SET coverage_status='partial', exhaustive_count=NULL WHERE observation_id='partial' AND feature='answer_text'")
        con.execute("UPDATE silver.evidence_features_v2 SET coverage_status='unsupported', observed_count=NULL, exhaustive_count=NULL WHERE observation_id='two' AND feature='citation'")
    publish_v1(database, "mixed")
    answer = metric(database, "mixed", "answer_text")
    citation = metric(database, "mixed", "citation")
    assert (answer["numerator"], answer["denominator"], answer["complete_run_count"]) == (2, 2, 1)
    assert answer["partial_positive_response_count"] == 1
    assert citation["denominator"] == 2
    assert citation["unknown_response_count"] == 1
    with pytest.raises(ValueError, match="no_approved_metrics"):
        publish_v1(database, "too-many-runs", minimum_runs=4)
    assert documents(database, "mixed", "metrics")


def test_url_and_source_only_are_not_answer_mentions_and_secrets_removed(database: Path) -> None:
    add(database, "safe", text="generic https://user:password@atlas.invalid/Atlas?api_key=secret token=abcdef Bearer abc123")
    publish_v1(database, "safe")
    assert metric(database, "safe", "answer_text")["metric_value"] == 0
    assert metric(database, "safe", "citation")["metric_value"] == 1
    output = json.dumps(documents(database, "safe", "evidence"))
    assert "abcdef" not in output and "abc123" not in output
    assert "user:password@" not in output and "api_key=secret" not in output
    assert "synthetic-hash-safe" in output and "json_path" in output
    assert "https://atlas.invalid/source" in output


@pytest.mark.parametrize("window,language,location,expected", [
    ("other", "en", "2344", "unmatched_context"),
    ("2026-10", "id", "2344", "unmatched_context"),
    ("2026-10", "en", None, "missing_context"),
    ("raw-request:isolated", "en", "2344", "missing_context"),
])
def test_unmatched_and_missing_context_never_make_gap(
    database: Path, window: str, language: str, location: str | None, expected: str,
) -> None:
    add(database, "s", "serp")
    add(database, "l", window=window, language=language, location=location)
    publish_v1(database, "contexts")
    comparisons = documents(database, "contexts", "comparisons")
    assert expected in {row["comparison_eligibility"] for row in comparisons}
    assert all(row["metric_value"] is None for row in comparisons)
    assert not documents(database, "contexts", "opportunities")


def test_comparison_not_response_cross_product(database: Path) -> None:
    for number in range(3):
        add(database, f"s{number}", "serp")
        add(database, f"l{number}")
    publish_v1(database, "counts")
    comparisons = documents(database, "counts", "comparisons")
    assert len(comparisons) == 2
    assert comparisons[0]["distinct_serp_response_count"] == 3
    assert comparisons[0]["distinct_llm_response_count"] == 3
    assert metric(database, "counts", "answer_text")["denominator"] == 3


def test_immutable_history_duplicate_and_failed_publication(database: Path) -> None:
    add(database, "first")
    first_manifest = publish_v1(database, "first")
    before = {kind: documents(database, "first", kind) for kind in first_manifest["document_counts"]}
    add(database, "second", text="generic")
    second_manifest = publish_v1(database, "second")
    assert second_manifest["snapshot_sha256"] != first_manifest["snapshot_sha256"]
    with pytest.raises(ValueError, match="already exists"):
        publish_v1(database, "first")
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE bronze.brand_registry SET active=false")
    with pytest.raises(ValueError, match="publication blocked"):
        publish_v1(database, "failed")
    assert before == {kind: documents(database, "first", kind) for kind in before}
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute("SELECT release_id FROM presentation.platform_current").fetchone() == ("second",)
        assert con.execute("SELECT count(*) FROM presentation.platform_releases").fetchone() == (2,)


def test_atomic_rollback_after_documents_insert_failure(database: Path) -> None:
    add(database, "one")
    publish_v1(database, "previous")
    with duckdb.connect(str(database)) as con:
        con.execute("ALTER TABLE presentation.platform_documents RENAME TO stored_documents")
        con.execute("CREATE TABLE presentation.platform_documents (release_id VARCHAR, kind VARCHAR CHECK(kind='coverage'), document_id VARCHAR, payload_json VARCHAR, PRIMARY KEY(release_id,kind,document_id))")
    with pytest.raises(duckdb.ConstraintException):
        publish_v1(database, "rollback")
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute("SELECT release_id FROM presentation.platform_current").fetchone() == ("previous",)
        assert con.execute("SELECT count(*) FROM presentation.platform_releases WHERE release_id='rollback'").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM presentation.platform_documents").fetchone() == (0,)


def test_all_results_required_for_response_denominator(database: Path) -> None:
    add(database, "one")
    with duckdb.connect(str(database)) as con:
        con.execute("INSERT INTO silver.evidence_results_v2 SELECT * REPLACE ('additional-result' AS result_id) FROM silver.evidence_results_v2")
    assert "no_approved_metrics" in assess_v1(database)["reasons"]


def test_gold_is_used_only_when_verified_against_silver(database: Path) -> None:
    add(database, "one")
    with duckdb.connect(str(database)) as con:
        con.execute("CREATE SCHEMA analytics")
        con.execute("CREATE TABLE analytics.gold_feature_brand_visibility_v2 AS SELECT result_id, 'atlas' AS brand_id, feature, coverage_status, CASE WHEN feature='answer_text' THEN 2 WHEN feature='citation' THEN 99 ELSE 0 END AS observed_brand_count FROM silver.evidence_features_v2")
    publish_v1(database, "gold")
    assert metric(database, "gold", "answer_text")["count_sources"] == ["verified_gold_v2"]
    assert metric(database, "gold", "citation")["count_sources"] == ["silver_v2"]
    assert metric(database, "gold", "citation")["observed_brand_count"] == 1


@pytest.mark.parametrize("change", [
    "review_status='candidate'", "ownership_type='unknown'",
    "effective_start_date='2027-01-01'", "effective_end_date='2025-12-31'",
])
def test_brand_eligibility_is_rechecked(database: Path, change: str) -> None:
    add(database, "one")
    with duckdb.connect(str(database)) as con:
        # Fixed parametrized test constants, never runtime user SQL.
        con.execute(f"UPDATE bronze.brand_registry SET {change}")
    assert not assess_v1(database)["complete"]
    with pytest.raises(ValueError, match="no_approved_metrics"):
        publish_v1(database, "not-eligible")


def test_deterministic_documents_and_distinct_response_not_result_count(database: Path) -> None:
    add(database, "one")
    with duckdb.connect(str(database)) as con:
        con.execute("INSERT INTO silver.evidence_results_v2 SELECT * REPLACE ('second-result' AS result_id) FROM silver.evidence_results_v2")
        con.execute("INSERT INTO silver.evidence_features_v2 SELECT * REPLACE (feature_id || '-second' AS feature_id, 'second-result' AS result_id) FROM silver.evidence_features_v2")
    first = publish_v1(database, "one")
    second = publish_v1(database, "two")
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    answer = metric(database, "one", "answer_text")
    assert answer["denominator"] == 1 and answer["complete_run_count"] == 1
    assert len(answer["result_ids"]) == 2


def test_missing_feature_schema_fails_closed(database: Path) -> None:
    add(database, "one")
    with duckdb.connect(str(database)) as con:
        con.execute("DROP TABLE silver.evidence_matches_v2")
    assert "evidence_schema_missing" in assess_v1(database)["reasons"]
    with pytest.raises(ValueError, match="evidence_schema_missing"):
        publish_v1(database, "missing-schema")


def test_publish_dashboard_review_then_freeze_next_release(database: Path) -> None:
    from geo_research.dashboard.platform import load_platform_snapshot
    from geo_research.platform.pipeline import review_opportunity

    add(database, "serp", "serp")
    add(database, "llm")
    publish_v1(database, "before-review")
    snapshot = load_platform_snapshot(database)
    assert snapshot.message is None
    card = snapshot.records["opportunities"][0]
    opportunity_id = card["opportunity_id"]
    assert opportunity_id == card["document_id"]
    assert card["review_status"] == "unreviewed"
    assert card["owner"] is None and card["notes"] is None
    assert card["review_history"] == []
    original = snapshot.records
    first = review_opportunity(database, opportunity_id, status="under_review",
                               owner="analyst", notes="Check evidence")
    second = review_opportunity(database, opportunity_id, status="approved",
                                owner="human", notes="Hypothesis reviewed, not demand")
    assert load_platform_snapshot(database).records == original
    publish_v1(database, "after-review")
    reviewed = load_platform_snapshot(database).records["opportunities"][0]
    assert reviewed["opportunity_id"] == opportunity_id
    assert reviewed["review_status"] == "approved"
    assert reviewed["owner"] == "human"
    assert reviewed["notes"] == second["notes"]
    assert [row["review_id"] for row in reviewed["review_history"]] == [first["review_id"], second["review_id"]]
    assert reviewed["human_review_required"] is True
    assert load_platform_snapshot(database, "before-review").records == original
    assert snapshot.records == original
    assert all(row["presence_rate"] == row["metric_value"]
               for row in snapshot.records["metrics"])


def test_unlike_channels_are_pattern_not_textual_gap(database: Path) -> None:
    add(database, "serp", "serp")  # Atlas title present on an unrelated domain.
    add(database, "llm")
    publish_v1(database, "pattern")
    owned = comparison(database, "pattern")
    assert owned["comparison_kind"] == "owned_organic_vs_answer_presence"
    assert owned["metric_value"] is None
    assert owned["available"] is True
    assert owned["serp_presence_rate"] == 0
    assert owned["llm_presence_rate"] == 1
    assert owned["serp_present"] is False
    assert owned["llm_present"] is True
    assert owned["textual_mention_gap_status"] == "not_applicable_owned_channel"
    textual = comparison(database, "pattern", textual=True)
    assert textual["metric_value"] == 0
    assert textual["metric_unit"] == "percentage_point"
    assert textual["serp_presence_rate"] == textual["llm_presence_rate"] == 1
    assert "textual_mention_gap_not_implemented" not in assess_v1(database)["warnings"]


def test_requested_reported_locale_preserved_without_inference(database: Path) -> None:
    add(database, "llm", language=None, location=None)
    with duckdb.connect(str(database)) as con:
        con.execute("ALTER TABLE bronze.api_requests ADD COLUMN metadata_json VARCHAR")
        con.execute("UPDATE bronze.api_requests SET metadata_json=?", [json.dumps({
            "requested_language_code": "ZH_CN", "requested_location_code": 2156,
        })])
    publish_v1(database, "requested")
    row = documents(database, "requested", "evidence")[0]
    assert row["language_code"] == row["requested_language_code"] == "zh-cn"
    assert row["location_code"] == row["requested_location_code"] == "2156"
    assert row["reported_language_code"] is None
    assert row["reported_location_code"] is None
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE silver.evidence_results_v2 SET language_code='EN_us', location_code='2344'")
        con.execute("ALTER TABLE bronze.api_responses ADD COLUMN metadata_json VARCHAR")
        con.execute("INSERT INTO bronze.api_responses (response_id, request_id, response_valid, received_at, metadata_json) VALUES ('resp-llm','req-llm', true, current_timestamp, ?)", [json.dumps({
            "reported_language_code": "EN_us", "reported_location_code": 2344,
        })])
    publish_v1(database, "reported")
    row = documents(database, "reported", "evidence")[0]
    assert row["language_code"] == row["reported_language_code"] == "en-us"
    assert row["location_code"] == row["reported_location_code"] == "2344"
    assert row["requested_language_code"] == "zh-cn"
    assert metric(database, "reported", "answer_text")["source_contexts"][0]["reported_language_code"] == "en-us"


def test_explicit_synthetic_provenance_and_mixed_source_block(database: Path) -> None:
    add(database, "s", "serp")
    add(database, "l")
    with duckdb.connect(str(database)) as con:
        con.execute("ALTER TABLE bronze.api_requests ADD COLUMN metadata_json VARCHAR")
        con.execute("UPDATE bronze.api_requests SET metadata_json=?", [json.dumps({
            "is_synthetic": True, "provenance": "isolated unit-test source metadata",
        })])
    publish_v1(database, "synthetic")
    for kind in ("metrics", "comparisons", "evidence", "opportunities"):
        rows = documents(database, "synthetic", kind)
        assert rows and all(row["is_synthetic"] is True for row in rows)
        assert all("isolated unit-test source metadata" in str(row["source_provenance"]) for row in rows)
    add(database, "unlabelled")
    assert "mixed_synthetic_source_evidence" in assess_v1(database)["reasons"]
    with pytest.raises(ValueError, match="mixed_synthetic_source_evidence"):
        publish_v1(database, "mixed")
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE bronze.api_requests SET metadata_json='{\"is_synthetic\":false}' WHERE request_id='req-unlabelled'")
    assert "mixed_synthetic_source_evidence" in assess_v1(database)["reasons"]


def test_missing_approved_brand_domains_remain_data_blocker(database: Path) -> None:
    add(database, "l")
    with duckdb.connect(str(database)) as con:
        con.execute("DELETE FROM bronze.brand_domain_registry")
    assert "no_approved_domains" in assess_v1(database)["reasons"]
    with pytest.raises(ValueError, match="no_approved_domains"):
        publish_v1(database, "blocked")


def test_duplicate_mentions_citations_deterministic_publication(database: Path) -> None:
    add(database, "l", text="Atlas Atlas [Atlas](https://atlas.invalid/source)")
    first = publish_v1(database, "first")
    second = publish_v1(database, "second")
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert metric(database, "first", "answer_text")["observed_brand_count"] == 3
    assert metric(database, "first", "citation")["observed_brand_count"] == 1
    row = documents(database, "first", "evidence")[0]
    assert len(row["citations"]) == len({item["citation_id"] for item in row["citations"]}) == 1
    assert len(row["matches"]) == len({item["evidence_id"] for item in row["matches"]})


def test_unknown_locale_and_provenance_not_inferred(database: Path) -> None:
    add(database, "l", language=None, location=None)
    publish_v1(database, "unknown")
    answer = metric(database, "unknown", "answer_text")
    assert answer["is_synthetic"] is None  # Synthetic provider name is not metadata.
    assert answer["language_code"] is None and answer["location_code"] is None
    assert answer["reported_language_code"] is None
    unknown = metric(database, "unknown", "organic")
    assert unknown["presence_rate"] is unknown["metric_value"] is None
    row = documents(database, "unknown", "evidence")[0]
    assert row["locale_basis"] == {"language_code": "unknown", "location_code": "unknown"}


def test_review_timestamp_ties_use_deterministic_review_id(database: Path) -> None:
    from geo_research.platform.pipeline import review_opportunity

    add(database, "s", "serp")
    add(database, "l")
    publish_v1(database, "original")
    opportunity_id = documents(database, "original", "opportunities")[0]["opportunity_id"]
    for status in ("under_review", "rejected"):
        review_opportunity(database, opportunity_id, status=status, owner="analyst", notes=status)
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE governance.platform_opportunity_reviews SET reviewed_at='2026-10-06T00:00:00Z'")
        latest = con.execute("SELECT status FROM governance.platform_opportunity_reviews ORDER BY review_id DESC LIMIT 1").fetchone()[0]
    first = publish_v1(database, "tie-one")
    second = publish_v1(database, "tie-two")
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    card = documents(database, "tie-one", "opportunities")[0]
    assert card["review_status"] == latest
    assert len(card["review_history"]) == 2
    assert documents(database, "original", "opportunities")[0]["review_status"] == "unreviewed"


def organic(title: Any, description: Any = None, url: str = "https://other.invalid/") -> dict[str, Any]:
    return {"type": "organic", "rank_group": 1, "rank_absolute": 1,
            "url": url, "title": title, "description": description}


def exposure(path: Path, release: str, category: str = "serp") -> dict[str, Any]:
    return next(row for row in documents(path, release, "coverage")
                if row.get("coverage_kind") == "observed_exposure" and row["source_category"] == category)


def test_textual_presence_excludes_urls_paid_and_substrings(database: Path) -> None:
    add(database, "s", "serp", serp_items=[
        organic("Atlasian atlas_extra https://atlas.invalid/Atlas", "generic", "https://atlas.invalid/Atlas"),
        {"type": "paid", "url": "https://atlas.invalid/", "title": "Atlas paid only"},
    ])
    add(database, "l")
    publish_v1(database, "url-only")
    assert metric(database, "url-only", "organic", "serp")["presence_rate"] == 1
    assert metric(database, "url-only", "textual_presence", "serp")["presence_rate"] == 0
    gap = comparison(database, "url-only", textual=True)
    assert gap["metric_value"] == 100
    assert gap["presence_pattern"] == "llm_present_serp_absent"
    evidence = next(row for row in documents(database, "url-only", "evidence") if row["source_category"] == "serp")
    assert not [row for row in evidence["matches"] if row["evidence_type"] == "serp_text"]
    readable = next(row["excerpt"] for row in evidence["items"] if row["item_kind"] == "organic")
    assert "Atlasian" in readable and "https://" not in readable


def test_textual_reviewed_alias_spans_are_deduplicated(database: Path) -> None:
    with duckdb.connect(str(database)) as con:
        con.execute("INSERT INTO bronze.brand_alias_registry VALUES ('atlas', 'AT'), ('atlas', 'AT')")
    add(database, "s", "serp", serp_items=[organic("AT AT", "Atlas ATLAS")])
    # Alias spans absent from old enrichment are calculated from reviewed Bronze.
    with duckdb.connect(str(database)) as con:
        con.execute("INSERT INTO silver.evidence_matches_v2 SELECT * REPLACE (evidence_id || '-duplicate' AS evidence_id) FROM silver.evidence_matches_v2")
    first = publish_v1(database, "spans")
    second = publish_v1(database, "spans-again")
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    text = metric(database, "spans", "textual_presence", "serp")
    assert (text["numerator"], text["denominator"], text["observed_brand_count"]) == (1, 1, 4)
    evidence = documents(database, "spans", "evidence")[0]
    hits = [row for row in evidence["matches"] if row["evidence_type"] == "serp_text"]
    assert len(hits) == 4
    assert {(row["matched_field"], row["span_start"], row["span_end"]) for row in hits} == {
        ("title", 0, 2), ("title", 3, 5), ("description", 0, 5), ("description", 6, 11),
    }
    assert exposure(database, "spans")["brand_observation_counts"] == {"atlas": 1}


@pytest.mark.parametrize("change", [
    "active=false", "review_status='candidate'", "alias_text='TO_BE_VERIFIED'",
    "effective_start_date='2027-01-01'", "effective_end_date='2025-12-31'",
])
def test_textual_alias_eligibility(database: Path, change: str) -> None:
    with duckdb.connect(str(database)) as con:
        con.execute("ALTER TABLE bronze.brand_alias_registry ADD COLUMN active BOOLEAN DEFAULT true")
        con.execute("ALTER TABLE bronze.brand_alias_registry ADD COLUMN review_status VARCHAR DEFAULT 'approved'")
        con.execute("ALTER TABLE bronze.brand_alias_registry ADD COLUMN effective_start_date DATE")
        con.execute("ALTER TABLE bronze.brand_alias_registry ADD COLUMN effective_end_date DATE")
        con.execute("INSERT INTO bronze.brand_alias_registry (brand_id, alias_text) VALUES ('atlas', 'AT')")
        con.execute(f"UPDATE bronze.brand_alias_registry SET {change}")
    add(database, "s", "serp", serp_items=[organic("AT")])
    publish_v1(database, "alias-gate")
    assert metric(database, "alias-gate", "textual_presence", "serp")["presence_rate"] == 0


@pytest.mark.parametrize("bad_title", [None, 123, {"brand": "Atlas"}, ["Atlas"]])
def test_textual_fields_require_actual_typed_visible_json(database: Path, bad_title: Any) -> None:
    add(database, "s", "serp", serp_items=[organic(bad_title)])
    add(database, "l")
    with duckdb.connect(str(database)) as con:
        # A flattened or readable string cannot repair missing/invalid raw text.
        con.execute("UPDATE silver.evidence_items_v2 SET title='Atlas', normalized_text='Atlas' WHERE item_kind='organic'")
    publish_v1(database, "typed")
    text = metric(database, "typed", "textual_presence", "serp")
    assert text["presence_rate"] is None
    assert text["denominator"] == 0
    assert comparison(database, "typed", textual=True)["metric_value"] is None


@pytest.mark.parametrize("feature,identity", [("organic", "s"), ("answer_text", "l")])
def test_textual_gap_requires_fully_complete_channels(database: Path, feature: str, identity: str) -> None:
    add(database, "s", "serp", serp_items=[organic("generic")])
    add(database, "s-complete", "serp", serp_items=[organic("generic")])
    add(database, "l")
    add(database, "l-complete")
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE silver.evidence_features_v2 SET coverage_status='partial', exhaustive_count=NULL WHERE observation_id=? AND feature=?", [identity, feature])
    publish_v1(database, "partial-gap")
    gap = comparison(database, "partial-gap", textual=True)
    assert gap["comparison_eligibility"] == "matched_context"
    assert gap["metric_value"] is None and gap["available"] is False
    # Legacy owned-organic hypotheses intentionally keep their existing gates.
    assert comparison(database, "partial-gap")["available"] is True


def test_textual_gap_negative_percentage_points(database: Path) -> None:
    add(database, "s", "serp")
    add(database, "l", text="generic")
    publish_v1(database, "negative-gap")
    assert comparison(database, "negative-gap", textual=True)["metric_value"] == -100
    summary = next(row for row in documents(database, "negative-gap", "coverage") if row["document_id"] == "summary")
    assert all(row["metric_value"] is None and row["availability_status"] == "unavailable_manual_labels_required"
               for row in summary["manual_label_metrics"].values())
    assert "v1.1.0" in assess_v1(database)["metric_version"]


def test_observed_hhi_uniform_multispans_and_unbranded(database: Path) -> None:
    with duckdb.connect(str(database)) as con:
        con.execute("INSERT INTO bronze.brand_registry VALUES ('beta', 'Beta', 'competitor', true, '2026-01-01', NULL, 'approved', 'synthetic unit-test provenance')")
    add(database, "both", "serp", serp_items=[organic("Atlas Atlas Beta Beta", "Beta Atlas")])
    add(database, "unbranded", "serp", serp_items=[organic("generic")])
    publish_v1(database, "hhi")
    row = exposure(database, "hhi")
    assert row["distinct_n"] == 2
    assert row["brand_observation_counts"] == {"atlas": 1, "beta": 1}
    assert row["total_brand_observation_exposures"] == 2
    assert row["hhi_observed_exposure"] == pytest.approx(0.5)
    assert row["unbranded_ratio"] == pytest.approx(0.5)
    assert row["unbranded_observation_count"] == 1
    assert "not market share" in " ".join(row["limitations"])


def test_observed_hhi_all_unbranded_is_undefined(database: Path) -> None:
    add(database, "none", "serp", serp_items=[organic("generic")])
    publish_v1(database, "none")
    row = exposure(database, "none")
    assert row["distinct_n"] == 1 and row["unbranded_ratio"] == 1
    assert row["hhi_observed_exposure"] is None
    assert row["hhi_availability_status"] == "no_branded_exposure"


def test_observed_exposure_keeps_locale_window_instrument_slices(database: Path) -> None:
    add(database, "one", "serp")
    add(database, "language", "serp", language="id")
    add(database, "window", "serp", window="2026-11")
    add(database, "instrument", "serp")
    with duckdb.connect(str(database)) as con:
        con.execute("UPDATE bronze.api_requests SET query_id='other-query' WHERE request_id='req-instrument'")
        con.execute("UPDATE silver.evidence_features_v2 SET coverage_status='partial' WHERE observation_id='one' AND feature='organic'")
    publish_v1(database, "slices")
    rows = [row for row in documents(database, "slices", "coverage") if row.get("coverage_kind") == "observed_exposure"]
    assert len(rows) == 4
    assert sorted(row["distinct_n"] for row in rows) == [0, 1, 1, 1]
    assert sum(row["unknown_observation_count"] for row in rows) == 1


@pytest.mark.parametrize("mode", ["one", "shared", "unknown"])
def test_binary_consistency_requires_two_unshared_known_runs(database: Path, mode: str) -> None:
    add(database, "one", run="run-one")
    if mode != "one":
        add(database, "two", run="run-one")
    if mode == "unknown":
        with duckdb.connect(str(database)) as con:
            con.execute("UPDATE bronze.api_requests SET run_id='' WHERE request_id='req-two'")
    publish_v1(database, "insufficient")
    stability = metric(database, "insufficient", "answer_text")["binary_run_consistency"]
    assert stability["metric_value"] is None
    assert stability["availability_status"] == "insufficient_independent_runs"
    assert stability["eligible_run_count"] <= 1
    if mode == "shared":
        assert stability["shared_request_run_ids"] == ["run-one"]


def test_binary_consistency_distinct_runs_is_not_text_similarity(database: Path) -> None:
    add(database, "one", run="run-one", text="Atlas")
    add(database, "two", run="run-two", text="A wholly different answer with Atlas Atlas")
    publish_v1(database, "consistent")
    stability = metric(database, "consistent", "answer_text")["binary_run_consistency"]
    assert stability["eligible_run_count"] == 2
    assert stability["positive_run_count"] == 2
    assert stability["metric_value"] == 1
    add(database, "three", run="run-three", text="generic")
    publish_v1(database, "changed")
    stability = metric(database, "changed", "answer_text")["binary_run_consistency"]
    assert stability["eligible_run_count"] == 3
    assert stability["metric_value"] == pytest.approx(2 / 3)