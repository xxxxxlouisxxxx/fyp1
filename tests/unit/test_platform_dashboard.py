"""V1 platform tests: only temporary fixture databases are written."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from geo_research.dashboard.platform import (
    KINDS,
    VIEWS,
    filter_frames,
    filter_options,
    guarded_projection,
    load_platform_snapshot,
    safe_url,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def warehouse(tmp_path):
    path = tmp_path / "platform.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA presentation")
        connection.execute(
            "CREATE TABLE presentation.platform_releases (release_id VARCHAR, "
            "status VARCHAR, created_at VARCHAR, metric_version VARCHAR, "
            "manifest_json VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE presentation.platform_current "
            "(slot VARCHAR, release_id VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE presentation.platform_documents (release_id VARCHAR, "
            "kind VARCHAR, document_id VARCHAR, payload_json VARCHAR)"
        )
        for release_id, status in (("done", "completed"), ("old", "completed"),
                                   ("draft", "draft")):
            connection.execute(
                "INSERT INTO presentation.platform_releases VALUES (?, ?, ?, ?, ?)",
                [release_id, status, "2026-10-06", "2.0.0", "{}"],
            )
        connection.execute(
            "INSERT INTO presentation.platform_current VALUES ('current', 'done')"
        )
        records = {
            "coverage": [{"coverage_status": "partial", "denominator": None}],
            "metrics": [
                {"brand_id": "b1", "source_category": "serp", "query_id": "q1",
                 "feature": "organic", "search_engine": "google", "provider": "p",
                 "language_code": "en", "location_code": 2344,
                 "collection_window": "w1", "numerator": 0, "denominator": 2,
                 "presence_rate": 0.0, "availability_status": "available"},
                {"brand_id": "b1", "source_category": "llm", "prompt_id": "p1",
                 "feature": "mention", "platform": "chatgpt", "model_name": "m",
                 "language_code": None, "numerator": None, "denominator": None,
                 "presence_rate": None, "availability_status": "unavailable"},
            ],
            "comparisons": [{"future_comparison_field": {"eligible": False}}],
            "evidence": [{"text": "<script>alert(1)</script>",
                          "citation_url": "https://example.org/evidence",
                          "lineage_hash": "abc", "lineage": {"hash": "abc"}}],
            "opportunities": [{"hypothesis": "Investigate", "review_status": "draft"}],
            "registries": [{"brand_id": "b1", "name": "Example"}],
        }
        for kind, rows in records.items():
            for index, payload in enumerate(rows):
                connection.execute(
                    "INSERT INTO presentation.platform_documents VALUES (?, ?, ?, ?)",
                    ["done", kind, f"{kind}-{index}", json.dumps(payload)],
                )
        connection.execute(
            "INSERT INTO presentation.platform_documents VALUES (?, ?, ?, ?)",
            ["draft", "metrics", "secret-draft", '{"brand_id":"unpublished"}'],
        )
    return path


def test_legacy_absence_and_missing_database(tmp_path):
    missing = tmp_path / "missing.duckdb"
    assert load_platform_snapshot(missing).message
    assert not missing.exists()
    legacy = tmp_path / "legacy.duckdb"
    with duckdb.connect(str(legacy)) as connection:
        connection.execute("CREATE SCHEMA presentation")
        connection.execute("CREATE TABLE presentation.releases (release_id VARCHAR)")
    before = legacy.read_bytes()
    snapshot = load_platform_snapshot(legacy)
    assert snapshot.message
    assert snapshot.release is None
    assert all(frame.empty for frame in snapshot.frames.values())
    assert legacy.read_bytes() == before


def test_completed_only_selection_and_no_latest_fallback(warehouse):
    snapshot = load_platform_snapshot(warehouse)
    assert snapshot.message is None
    assert set(snapshot.releases.release_id) == {"done", "old"}
    assert snapshot.release["release_id"] == "done"
    assert load_platform_snapshot(warehouse, "old").release["release_id"] == "old"
    assert load_platform_snapshot(warehouse, "draft").message
    attack = "done'; DROP TABLE presentation.platform_releases; --"
    assert load_platform_snapshot(warehouse, attack).message
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute(
            "UPDATE presentation.platform_current SET release_id='draft'"
        )
    assert load_platform_snapshot(warehouse).message
    assert load_platform_snapshot(warehouse, "done").message is None
    assert snapshot.release["release_id"] == "done"


def test_snapshot_detached_and_immutable(warehouse):
    snapshot = load_platform_snapshot(warehouse)
    snapshot.release["release_id"] = "changed"
    releases = snapshot.releases
    releases.loc[0, "release_id"] = "changed"
    frames = snapshot.frames
    frames["metrics"].loc[0, "numerator"] = 999
    frames["evidence"].iloc[0]["lineage"]["hash"] = "changed"
    records = snapshot.records
    records["evidence"][0]["lineage"]["hash"] = "changed"
    assert snapshot.release["release_id"] == "done"
    assert snapshot.frames["metrics"].iloc[0].numerator == 0
    assert snapshot.records["evidence"][0]["lineage"]["hash"] == "abc"
    with pytest.raises(FrozenInstanceError):
        snapshot.message = "changed"


def test_frozen_contract_fields_are_not_live_review_overlaid(warehouse):
    with duckdb.connect(str(warehouse)) as connection:
        opportunity = {"opportunity_id": "opportunities-0",
                       "review_status": "unreviewed",
                       "owner": None, "notes": None, "review_history": [],
                       "is_synthetic": True}
        connection.execute(
            "UPDATE presentation.platform_documents SET payload_json=? "
            "WHERE kind='opportunities'", [json.dumps(opportunity)]
        )
        connection.execute("CREATE SCHEMA governance")
        connection.execute(
            "CREATE TABLE governance.platform_opportunity_reviews "
            "(opportunity_id VARCHAR, status VARCHAR)"
        )
        connection.execute(
            "INSERT INTO governance.platform_opportunity_reviews "
            "VALUES ('opportunities-0','approved')"
        )
    snapshot = load_platform_snapshot(warehouse)
    card = snapshot.records["opportunities"][0]
    assert card["opportunity_id"] == card["document_id"]
    assert card["review_status"] == "unreviewed" and card["review_history"] == []
    assert card["is_synthetic"] is True
    assert snapshot.frames["metrics"].iloc[0]["presence_rate"] == 0


def test_read_only_one_transaction_no_mutation(warehouse, monkeypatch):
    before = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    original = duckdb.connect
    statements = []

    class TrackedConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, *args):
            statements.append(sql)
            return self.connection.execute(sql, *args)

        def close(self):
            self.connection.close()

    def connect(*args, **kwargs):
        assert kwargs["read_only"] is True
        return TrackedConnection(original(*args, **kwargs))

    monkeypatch.setattr(duckdb, "connect", connect)
    snapshot = load_platform_snapshot(warehouse)
    assert snapshot.message is None
    assert statements[0] == "BEGIN TRANSACTION"
    assert statements[-1] == "COMMIT"
    assert all(sql.startswith(("SELECT", "BEGIN", "COMMIT")) for sql in statements)
    assert hashlib.sha256(warehouse.read_bytes()).hexdigest() == before


def test_filters_nulls_channel_local_and_guarded_projection(warehouse):
    frames = load_platform_snapshot(warehouse).frames
    assert set(frames) == set(KINDS)
    assert filter_options(frames, "intent_id") == ["prompt_id:p1", "query_id:q1", None]
    assert filter_options(frames, "location_code") == ["2344", None]
    unknown = filter_frames(frames, {"language_code": [None]})["metrics"]
    assert len(unknown) == 1 and unknown.presence_rate.isna().all()
    assert filter_frames(frames, {"brand_id": []})["metrics"].empty
    engine = filter_frames(frames, {"search_engine": ["bing"]})["metrics"]
    assert engine.source_category.tolist() == ["llm"]
    platform = filter_frames(frames, {"platform": ["gemini"]})["metrics"]
    assert platform.source_category.tolist() == ["serp"]
    selected = filter_frames(frames, {"intent_id": ["query_id:q1"]})["metrics"]
    assert len(selected) == 1 and selected.numerator.iloc[0] == 0
    assert frames["metrics"].presence_rate.isna().sum() == 1
    fallback = guarded_projection(frames["comparisons"], ["not_yet_defined"])
    assert "future_comparison_field" in fallback


@pytest.mark.parametrize("value", [
    "javascript:alert(1)", "data:text/html,boom", "file:///etc/passwd",
    "//example.org", "https://user:secret@example.org", "https:///no-host",
    "https://example.org\n/attack", "https://example.org\\attack",
    "https://example.org:bad", "https://[bad", None, "",
])
def test_evidence_url_sanitization(value):
    assert safe_url(value) is None


def test_safe_evidence_urls():
    assert safe_url("https://example.org/citation?q=1#evidence")
    assert safe_url("http://example.org/lineage")


def test_nested_evidence_links_and_spans_are_plain_text(monkeypatch):
    from geo_research.dashboard import platform

    text, links, captions = [], [], []
    monkeypatch.setattr(platform.st, "text", text.append)
    monkeypatch.setattr(platform.st, "caption", captions.append)
    monkeypatch.setattr(platform.st, "link_button",
                        lambda label, url: links.append((label, url)))
    monkeypatch.setattr(
        platform.st, "markdown",
        lambda *args, **kwargs: pytest.fail("Payload Markdown forbidden"),
    )
    platform._record_details({
        "citations": [{"url": "https://example.org/citation",
                       "snippet": "<script>citation</script>"},
                      {"url": "javascript:alert(1)"}],
        "items": [{"url": "https://example.org/item", "excerpt": "Item text",
                   "sources": [{"source_url": "https://example.org/nested"},
                               {"url": "https://user:secret@example.org"}]}],
        "matches": [{"matched_text": "<b>Atlas</b>", "start": 0, "end": 5}],
    })
    assert [url for _, url in links] == [
        "https://example.org/citation", "https://example.org/item",
        "https://example.org/nested",
    ]
    assert "citations[0].snippet: <script>citation</script>" in text
    assert "matches[0].matched_text: <b>Atlas</b>" in text
    assert "matches[0].start: 0" in text and "matches[0].end: 5" in text
    assert len(captions) == 2


def test_textual_gap_disclaimer_matches_publisher_contract():
    from geo_research.dashboard.platform import LIMITATIONS

    assert "not implemented" not in LIMITATIONS
    assert "percentage points" in LIMITATIONS
    assert "GEO answer presence rate" in LIMITATIONS
    assert "organic title/description presence rate" in LIMITATIONS
    assert "owned organic" in LIMITATIONS and "no numeric gap" in LIMITATIONS
    assert "not demand" in LIMITATIONS and "causality" in LIMITATIONS


def test_opportunity_cards_show_frozen_review_support_and_caveats(
    warehouse, monkeypatch,
):
    from streamlit.testing.v1 import AppTest

    payload = {
        "opportunity_id": "human-readable-opportunity",
        "review_status": "under_review", "owner": "frozen-owner",
        "human_review_required": True, "is_synthetic": True,
        "limitations": ["No evidence of demand or causality", "<b>Plain caveat</b>"],
        "comparison": {
            "serp": {"feature": "organic", "presence_rate": 0,
                     "numerator": 0, "denominator": 3},
            "llm": {"feature": "answer_text", "presence_rate": 2 / 3,
                    "numerator": 2, "denominator": 3},
        },
    }
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute("UPDATE presentation.platform_documents SET payload_json=? "
                           "WHERE kind='opportunities'", [json.dumps(payload)])
    before = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    monkeypatch.setenv("GEO_DASHBOARD_DB", str(warehouse))
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=15).run()
    app.sidebar.selectbox(key="dashboard_workspace").set_value("V1 Platform").run()
    app.sidebar.radio(key="platform_view").set_value(VIEWS[4]).run()
    assert not app.exception
    text = [element.value for element in app.text]
    for expected in ("opportunity_id: human-readable-opportunity",
                     "review_status: under_review", "owner: frozen-owner",
                     "human_review_required: True", "serp.presence_rate: 0",
                     "llm.numerator: 2", "llm.denominator: 3",
                     "limitations[1]: <b>Plain caveat</b>"):
        assert expected in text
    assert hashlib.sha256(warehouse.read_bytes()).hexdigest() == before


def test_malformed_documents_fail_closed(warehouse):
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute(
            "UPDATE presentation.platform_documents SET payload_json='[1]' "
            "WHERE kind='metrics'"
        )
    snapshot = load_platform_snapshot(warehouse)
    assert snapshot.message and snapshot.release is None
    assert all(frame.empty for frame in snapshot.frames.values())
    assert set(snapshot.releases.release_id) == {"done", "old"}


def test_app_five_views_and_legacy_switch(warehouse, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("GEO_DASHBOARD_DB", str(warehouse))
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=15).run()
    assert not app.exception
    app.sidebar.selectbox(key="dashboard_workspace").set_value("V1 Platform").run()
    for view in VIEWS:
        app.sidebar.radio(key="platform_view").set_value(view).run()
        assert not app.exception
    app.sidebar.selectbox(key="dashboard_workspace").set_value("Legacy explorer").run()
    assert not app.exception


def test_app_no_release_instructions(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("GEO_DASHBOARD_DB", str(tmp_path / "absent.duckdb"))
    app = AppTest.from_file(str(ROOT / "streamlit_app.py")).run()
    app.sidebar.selectbox(key="dashboard_workspace").set_value("V1 Platform").run()
    assert not app.exception
    assert any("pipeline owner" in element.value for element in app.info)
    assert not app.metric


def test_locale_labels_preserve_raw_filter_codes_and_mixed_providers():
    from geo_research.dashboard import platform

    frames = {"metrics": pd.DataFrame([
        {"language_code": "en", "location_code": 2840, "provider": "dataforseo"},
        {"language_code": "zh-tw", "location_code": 2344,
         "provider": "DataForSEO"},
        {"language_code": "EN", "location_code": 2156, "provider": "dataforseo"},
        {"language_code": "raw-Language", "location_code": 2702,
         "provider": "dataforseo"},
        {"language_code": "en", "location_code": 2360, "provider": "dataforseo"},
        {"language_code": "English", "location_code": 2840, "provider": "other"},
    ], dtype=object)}
    original = frames["metrics"].copy(deep=True)
    languages = platform._locale_formatter(frames, "language_code")
    locations = platform._locale_formatter(frames, "location_code")
    assert languages("en") == "English (en)"
    assert "Traditional Chinese" in languages("zh-tw")
    assert "zh-tw" in languages("zh-tw")
    assert "EN" in languages("EN")
    assert "raw-Language" in languages("raw-Language")
    assert "English" in languages("English")
    assert "United States" not in locations("2840")
    assert "2840" in locations("2840")
    for code, name in (("2344", "Hong Kong"), ("2156", "China"),
                       ("2702", "Singapore"), ("2360", "Indonesia")):
        assert name in locations(code) and code in locations(code)
    assert filter_options(frames, "language_code") == [
        "EN", "English", "en", "raw-Language", "zh-tw",
    ]
    assert filter_options(frames, "location_code") == [
        "2156", "2344", "2360", "2702", "2840",
    ]
    filtered = filter_frames(frames, {"language_code": ["EN"]})["metrics"]
    assert filtered.language_code.tolist() == ["EN"]
    shown = platform._display_frame(frames["metrics"])
    assert shown.location_code.tolist() == original.location_code.tolist()
    assert shown.language_code.tolist() == original.language_code.tolist()
    assert "language_name" in shown and "location_name" in shown
    pd.testing.assert_frame_equal(frames["metrics"], original)


def test_nested_locale_details_inherit_explicit_provider_only(monkeypatch):
    from geo_research.dashboard import platform

    text = []
    monkeypatch.setattr(platform.st, "text", text.append)
    platform._record_details({
        "provider": "DataForSEO", "language_code": "zh-tw",
        "requested": {"location_code": 2840},
        "other": {"provider": "other", "location_code": 2344},
    })
    assert any("Traditional Chinese (zh-tw)" in value for value in text)
    assert any("United States (2840)" in value for value in text)
    assert any("other.location_code:" in value and "2344" in value
               and "Hong Kong" not in value for value in text)
    text.clear()
    platform._record_details({"location_code": 2840})
    assert "2840" in text[0] and "United States" not in text[0]


def test_evidence_brand_filter_uses_nested_approved_not_candidates():
    frames = {"evidence": pd.DataFrame([
        {"result_id": "approved", "matches": [
            {"identity_type": "brand", "identity_id": "b1",
             "review_status": "approved"},
            {"identity_type": "brand_candidate", "identity_id": "candidate1",
             "review_status": "candidate"},
        ]},
        {"result_id": "candidate-only", "brand_id": "b1", "matches": [
            {"identity_type": "brand_candidate", "identity_id": "b1",
             "review_status": "candidate"},
        ]},
        {"result_id": "not-approved", "matches": [
            {"identity_type": "brand", "identity_id": "b1",
             "review_status": "pending"},
        ]},
        {"result_id": "unknown", "brand_coverage_status": "no_approved_registry"},
    ], dtype=object)}
    assert filter_options(frames, "brand_id") == ["b1", None]
    assert filter_frames(frames, {"brand_id": ["b1"]})[
        "evidence"].result_id.tolist() == ["approved"]
    assert filter_frames(frames, {"brand_id": ["candidate1"]})["evidence"].empty
    assert filter_frames(frames, {"brand_id": [None]})[
        "evidence"].result_id.tolist() == [
            "candidate-only", "not-approved", "unknown",
        ]
    assert filter_frames(frames, {"brand_id": []})["evidence"].empty


def test_missing_reviewed_registry_is_unknown_not_zero():
    from geo_research.dashboard import platform

    record = {
        "brand_coverage_status": "no_approved_registry",
        "approved_mentioned_brand_count": 0, "approved_cited_brand_count": 0,
        "approved_evidenced_brand_count": 0, "candidate_brand_count": 2,
    }
    for prefix in ("approved_mentioned", "approved_cited", "approved_evidenced"):
        assert platform._observed_brand_count(record, prefix) is None
    assert platform._observed_brand_count(record, "candidate") == 2
    assert record["approved_mentioned_brand_count"] == 0
    record["brand_coverage_status"] = "approved_registry"
    assert platform._observed_brand_count(record, "approved_mentioned") == 0


def test_evidence_selected_summary_ui_before_raw_and_snapshot_unchanged(
    warehouse, monkeypatch,
):
    from streamlit.testing.v1 import AppTest

    payload = {
        "result_id": "result-brands", "provider": "dataforseo",
        "language_code": "en", "location_code": 2840,
        "collection_status": "partial", "coverage_status": "incomplete",
        "brand_coverage_status": "approved_registry",
        "matches": [
            {"identity_type": "brand", "identity_id": "b1",
             "identity_name": "Atlas", "review_status": "approved",
             "evidence_type": "answer_text", "matched_text": "Atlas",
             "matched_field": "text", "span_start": 0, "span_end": 5},
            {"identity_type": "brand", "identity_id": "b1",
             "identity_name": "Atlas", "review_status": "approved",
             "evidence_type": "answer_text", "matched_text": "Atlas",
             "matched_field": "text", "span_start": 10, "span_end": 15},
            {"identity_type": "brand", "identity_id": "b1",
             "identity_name": "Atlas", "review_status": "approved",
             "evidence_type": "owned_citation", "citation_id": "citation-1"},
            {"identity_type": "brand_candidate", "identity_id": "c1",
             "identity_name": "Possible", "review_status": "candidate",
             "evidence_type": "answer_text", "matched_field": "text"},
        ],
        "citation_url": "https://example.org/evidence",
    }
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute("UPDATE presentation.platform_documents SET payload_json=? "
                           "WHERE kind='evidence'", [json.dumps(payload)])
    before = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    snapshot = load_platform_snapshot(warehouse)
    documents = snapshot._documents
    monkeypatch.setenv("GEO_DASHBOARD_DB", str(warehouse))
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=15).run()
    app.sidebar.selectbox(key="dashboard_workspace").set_value("V1 Platform").run()
    app.sidebar.radio(key="platform_view").set_value(VIEWS[3]).run()
    assert not app.exception
    assert [metric.label for metric in app.metric] == [
        "Approved text-mentioned brands", "Approved cited brands",
        "Candidate brands (unapproved)",
    ]
    assert [metric.value for metric in app.metric] == ["1", "1", "1"]
    assert any("Results brand summary" in heading.value for heading in app.subheader)
    assert any("Zero observed is not proof of absence" in c.value for c in app.caption)
    assert "coverage_status: incomplete" in [text.value for text in app.text]
    assert any("Atlas" in text.value for text in app.text)
    assert any("Possible" in text.value for text in app.text)
    raw = [e for e in app.expander if e.label == "Raw frozen evidence & lineage"]
    assert len(raw) == 1 and not raw[0].proto.expanded
    assert "approved_evidenced_brand_count" in app.dataframe[0].value.columns
    assert not app.dataframe[1].value.empty
    assert snapshot._documents == documents
    assert load_platform_snapshot(warehouse)._documents == documents
    assert hashlib.sha256(warehouse.read_bytes()).hexdigest() == before
    brand = app.sidebar.multiselect(key="platform_brand_id")
    brand.set_value(["b1"]).run()
    assert not app.exception and len(app.metric) == 3