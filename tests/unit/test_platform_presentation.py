"""Pure presentation contracts: recorded identities, not fresh extraction."""

from copy import deepcopy

import pandas as pd
import pytest

from geo_research.platform.presentation import (
    enrich_evidence_detail,
    enrich_locale_detail,
    language_label,
    location_label,
)


def match(identity="atlas", name="Atlas", **overrides):
    return {
        "identity_id": identity, "identity_name": name,
        "identity_type": "brand", "review_status": "approved",
        "result_id": "r1", "item_id": "i1", "evidence_id": "e1",
        "evidence_type": "answer_text", "matched_field": "text",
        "matched_text": "AT", "span_start": 0, "span_end": 2,
        "method": "explicit_alias_boundary_longest", "registry_version": "v1",
        **overrides,
    }


def record(matches=(), **overrides):
    return {
        "result_id": "r1", "matches": list(matches),
        "approved_registry_available": True,
        "features": [{"feature": "answer_text", "coverage_status": "complete"}],
        **overrides,
    }


@pytest.mark.parametrize(("code", "expected"), [
    ("id", "Indonesian"), ("EN", "English"),
    ("zh_tw", "Traditional Chinese"), ("zh-TW", "Traditional Chinese"),
    ("zh_CN", "Simplified Chinese"), ("zh", "Unknown language (zh)"),
    ("fr", "Unknown language (fr)"), (None, "Unknown (not recorded)"),
    (" ", "Unknown (not recorded)"), (float("nan"), "Unknown (not recorded)"),
    (pd.NA, "Unknown (not recorded)"),
])
def test_language_names_without_inferred_chinese_script(code, expected):
    assert language_label(code) == expected


@pytest.mark.parametrize(("code", "expected"), [
    (2840, "United States"), ("2840.0", "United States"),
    (2840.0, "United States"), ("2344", "Hong Kong"),
    (2156, "China"), (2702, "Singapore"), (2360, "Indonesia"),
    ("2840.1", "Unknown location (2840.1)"),
    ("2840oops", "Unknown location (2840oops)"),
    (9999, "Unknown location (9999)"), (None, "Unknown (not recorded)"),
    (pd.NA, "Unknown (not recorded)"), (float("nan"), "Unknown (not recorded)"),
])
def test_dataforseo_location_codes(code, expected):
    assert location_label(code) == expected


@pytest.mark.parametrize("provider", [None, "", pd.NA, "other", "google"])
def test_provider_namespaces_never_relabel_unknown_provider(provider):
    assert location_label("2840.0", provider) == "Unknown location (2840.0)"


def test_detached_locale_labels_preserve_requested_reported_codes():
    source = {
        "provider": "DataForSEO", "language_code": "zh_tw",
        "location_code": "2840.0", "requested_language_code": "en",
        "requested_location_code": 2344, "reported_language_code": "zh",
        "reported_location_code": None, "nested": {"value": []},
    }
    before = deepcopy(source)
    enriched = enrich_locale_detail(source)
    assert enriched["language_name"] == "Traditional Chinese"
    assert enriched["location_name"] == "United States"
    assert enriched["requested_language_name"] == "English"
    assert enriched["requested_location_name"] == "Hong Kong"
    assert enriched["reported_language_name"] == "Unknown language (zh)"
    assert enriched["reported_location_name"] == "Unknown (not recorded)"
    assert all(enriched[key] == value for key, value in source.items())
    enriched["nested"]["value"].append("changed")
    assert source == before
    assert enrich_locale_detail({"location_code": 2840})["location_name"] == (
        "Unknown location (2840)"
    )


def test_comparison_location_requires_agreeing_recorded_provider():
    source = {"location_code": 2344, "serp": {"provider": "dataforseo"},
              "llm": {"provider": "dataforseo"}}
    assert enrich_locale_detail(source)["location_name"] == "Hong Kong"
    source["llm"]["provider"] = "another_provider"
    assert enrich_locale_detail(source)["location_name"] == "Unknown location (2344)"


def test_distinct_brands_repeated_alias_spans_and_duplicate_evidence():
    first = match()
    repeated = match(evidence_id="e2", span_start=10, span_end=12)
    other = match("b2", "Beacon", evidence_id="b2")
    source = record([
        first, deepcopy(first), repeated,
        match(evidence_id="same-span-new-id"),
        match(evidence_id="e2", span_start=100, span_end=102), other,
    ])
    before = deepcopy(source)
    result = enrich_evidence_detail(source)
    assert result["approved_evidenced_brand_count"] == 2
    assert result["approved_mentioned_brand_count"] == 2
    assert result["approved_mentioned_brand_names"] == ["Atlas", "Beacon"]
    assert result["approved_cited_brand_count"] == 0
    atlas = result["matched_brand_details"][0]
    assert atlas["text_mention_occurrence_count"] == 2
    assert atlas["matches"][0]["matched_text"] == "AT"
    assert atlas["matches"][0]["registry_version"] == "v1"
    assert result["coverage_status"] == "complete"
    assert result["mention_count_status"] == "complete_reviewed_registry_observation"
    result["matches"][0]["matched_text"] = "changed"
    atlas["matches"][0]["matched_text"] = "changed too"
    assert source == before


def test_citation_only_domain_only_and_candidates_are_separate():
    citation = match("cited", "Cited", evidence_type="owned_citation",
                     citation_id="c1", matched_field="hostname")
    owned = match("owned", "Owned", evidence_type="owned_organic",
                  matched_field="hostname", evidence_id="owned")
    candidate = match("candidate", "Candidate", identity_type="brand_candidate",
                      review_status="candidate", evidence_id="candidate")
    result = enrich_evidence_detail(record([
        citation, {**citation, "evidence_id": "different-id"},
        {**citation, "citation_id": "c2"}, owned, deepcopy(owned),
        candidate, deepcopy(candidate),
        match("category", "Category", identity_type="category"),
        match("unreviewed", "Unreviewed", review_status="unreviewed"),
        match("foreign", "Foreign", result_id="another-result"),
    ]))
    assert result["approved_evidenced_brand_count"] == 2
    assert result["approved_mentioned_brand_count"] == 0
    assert result["approved_cited_brand_count"] == 1
    assert result["approved_cited_brand_names"] == ["Cited"]
    assert result["candidate_brand_count"] == 1
    assert result["candidate_brand_names"] == ["Candidate"]
    details = {row["brand_id"]: row for row in result["matched_brand_details"]}
    assert details["cited"]["citation_occurrence_count"] == 2
    assert details["owned"]["owned_organic_item_count"] == 1
    assert details["candidate"]["review_status"] == "candidate"
    assert details["candidate"]["text_mention_occurrence_count"] == 1


def test_serp_and_product_visible_fields_not_urls():
    result = enrich_evidence_detail(record([
        match("serp", "SERP", evidence_type="serp_text", matched_field="title"),
        match("product", "Product", evidence_type="product_text",
              matched_field="description", evidence_id="p"),
        match("url", "URL", evidence_type="serp_text", matched_field="url"),
        match("host", "Host", evidence_type="answer_text", matched_field="hostname"),
    ]))
    assert result["approved_mentioned_brand_count"] == 2
    assert result["approved_mentioned_brand_names"] == ["Product", "SERP"]


@pytest.mark.parametrize(("overrides", "coverage", "status"), [
    ({"approved_registry_available": False}, "no_reviewed_registry",
     "observed_only_no_reviewed_registry"),
    ({"features": [{"feature": "answer_text", "coverage_status": "partial"}]},
     "partial", "observed_only_partial_coverage"),
    ({"features": []}, "partial", "observed_only_partial_coverage"),
    ({}, "complete", "complete_reviewed_registry_observation"),
])
def test_zero_count_always_has_coverage_qualification(overrides, coverage, status):
    result = enrich_evidence_detail(record(**overrides))
    assert result["approved_mentioned_brand_count"] == 0
    assert result["coverage_status"] == coverage
    assert result["mention_count_status"] == status


def test_historical_raw_text_does_not_invent_brands_or_registry_approval():
    source = {"items": [{"title": "Atlas Atlas Beacon"}], "matches": None,
              "language_code": None, "location_code": None}
    result = enrich_evidence_detail(source)
    assert result["approved_mentioned_brand_count"] == 0
    assert result["matched_brand_details"] == []
    assert result["mention_count_status"] == "observed_only_partial_coverage"
    assert result["language_name"] == "Unknown (not recorded)"
    assert result["location_name"] == "Unknown (not recorded)"
    assert "approved_mentioned_brand_count" not in source


def test_missing_match_result_id_is_same_record_and_registry_limits_coverage():
    result = enrich_evidence_detail(record([
        match(), match(result_id=None, evidence_id="another-id"),
    ], approved_registry_available=False, coverage_status="complete"))
    assert result["matched_brand_details"][0]["text_mention_occurrence_count"] == 1
    assert result["brand_evidence_coverage_status"] == "no_reviewed_registry"
    assert result["coverage_status"] == "complete"


def test_existing_analytics_synthetic_serp_matches_are_readable_evidence():
    from geo_research.platform.analytics import _serp_text

    results = [{"result_id": "r1", "observation_id": "o1",
                "source_category": "serp", "collected_at": "2026-10-06"}]
    items = [{"item_id": "i1", "result_id": "r1", "item_kind": "organic",
              "coverage_status": "complete",
              "raw_evidence_json": {"title": "Atlas and AT",
                                    "description": "Unreviewed Other Brand"}}]
    brands = [{"brand_id": "atlas", "canonical_name": "Atlas", "active": True,
               "ownership_type": "owned", "review_status": "approved"}]
    aliases = [{"brand_id": "atlas", "alias_text": "AT"}]
    features, matches = _serp_text(
        results, [{"result_id": "r1", "feature": "organic",
                   "coverage_status": "complete"}], items, brands, aliases,
    )
    result = enrich_evidence_detail(record(matches, features=features))
    assert result["approved_mentioned_brand_count"] == 1
    detail = result["matched_brand_details"][0]
    assert detail["text_mention_occurrence_count"] == 2
    assert {row["matched_text"] for row in detail["matches"]} == {"Atlas", "AT"}
    assert detail["evidence_types"] == ["serp_text"]
    assert result["coverage_status"] == "complete"