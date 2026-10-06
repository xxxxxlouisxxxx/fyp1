"""Detached, read-only labels and per-result summaries of recorded evidence.

No extraction, registry lookup, storage writes or historical snapshot mutation.
Counts describe reviewed identities observed in this result, not market coverage.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

_LANGUAGES = {
    "id": "Indonesian", "en": "English",
    "zh-tw": "Traditional Chinese", "zh-cn": "Simplified Chinese",
}
_LOCATIONS = {
    "2840": "United States", "2344": "Hong Kong", "2156": "China",
    "2702": "Singapore", "2360": "Indonesia",
}
_TEXT_TYPES = {"answer_text", "serp_text", "product_text"}


def _missing(value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    if isinstance(value, (Mapping, list, tuple, set)):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def language_label(value: Any) -> str:
    """Label only supported codes; generic zh does not identify a script."""
    if _missing(value):
        return "Unknown (not recorded)"
    code = str(value).strip().lower().replace("_", "-")
    return _LANGUAGES.get(code, f"Unknown language ({code})")


def location_label(value: Any, provider: Any = "dataforseo") -> str:
    """Interpret integral DataForSEO codes only within that provider namespace."""
    if _missing(value):
        return "Unknown (not recorded)"
    original = str(value).strip()
    code = original
    try:
        number = Decimal(original)
        if number.is_finite() and number == number.to_integral_value():
            code = str(int(number))
    except (InvalidOperation, ValueError, OverflowError):
        pass
    if not _missing(provider) and str(provider).strip().lower() == "dataforseo":
        if code in _LOCATIONS:
            return _LOCATIONS[code]
    return f"Unknown location ({original})"


def enrich_locale_detail(record: Mapping[str, Any]) -> dict[str, Any]:
    """Add best-known/requested/reported names without changing recorded codes.

An absent provider is not assumed to be DataForSEO. Comparison documents may
use their two recorded source providers only when those providers agree.
"""
    output = deepcopy(dict(record))
    provider = record.get("provider")
    if _missing(provider):
        sources = [record.get(key) for key in ("serp", "llm")]
        providers = [source.get("provider") for source in sources
                     if isinstance(source, Mapping)]
        if (len(providers) == 2 and not _missing(providers[0])
                and providers[0] == providers[1]):
            provider = providers[0]
    for prefix in ("", "requested_", "reported_"):
        output[f"{prefix}language_name"] = language_label(
            record.get(f"{prefix}language_code")
        )
        output[f"{prefix}location_name"] = location_label(
            record.get(f"{prefix}location_code"), provider
        )
    return output


def _visible(match: Mapping[str, Any]) -> bool:
    kind, field = match.get("evidence_type"), match.get("matched_field")
    if kind not in _TEXT_TYPES or field in {"url", "domain", "hostname"}:
        return False
    if kind == "serp_text":
        return field in {"title", "description"}
    return field in {"title", "description", "text", "original_text", "markdown"}


def _coverage(record: Mapping[str, Any]) -> tuple[str, str]:
    available = record.get("approved_registry_available")
    missing_registry = record.get("brand_coverage_status") == "no_approved_registry"
    if available is False or missing_registry:
        return "no_reviewed_registry", "observed_only_no_reviewed_registry"
    features = record.get("features")
    relevant = {"answer_text", "textual_presence", "product"}
    statuses = [row.get("coverage_status") for row in features or []
                if isinstance(row, Mapping) and row.get("feature") in relevant
                and row.get("coverage_status") != "not_applicable"]
    complete = bool(statuses) and all(status == "complete" for status in statuses)
    if not statuses:
        complete = record.get("coverage_status") == "complete"
    if available is True and complete:
        return "complete", "complete_reviewed_registry_observation"
    return "partial", "observed_only_partial_coverage"


def enrich_evidence_detail(record: Mapping[str, Any]) -> dict[str, Any]:
    """Add distinct approved/candidate identities and deduplicated occurrences.

Only explicit approved brand or candidate match snapshots are consumed. Raw
text is never searched here. Text identity is brand/result/item/field/span;
duplicate evidence IDs also cannot inflate occurrences. Citations are distinct
by citation ID and brand, and owned organic counts by result/item and brand.
Zero counts require the accompanying status; they do not assert global absence.
"""
    output = enrich_locale_detail(record)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for match in output.get("matches") or []:
        if not isinstance(match, Mapping):
            continue
        identity = match.get("identity_id", match.get("brand_id"))
        if _missing(identity):
            continue
        if (not _missing(record.get("result_id"))
                and not _missing(match.get("result_id"))
                and match["result_id"] != record["result_id"]):
            continue
        identity_type = match.get("identity_type")
        status = match.get("review_status")
        if identity_type == "brand" and status == "approved":
            review = "approved"
        elif identity_type in {"brand_candidate", "brand"} and status == "candidate":
            review = "candidate"
        else:
            continue
        grouped.setdefault((review, str(identity)), []).append(dict(match))
    details: list[dict[str, Any]] = []
    for (review, identity), matches in sorted(grouped.items()):
        names = sorted({str(row["identity_name"]) for row in matches
                        if not _missing(row.get("identity_name"))})
        text_spans: set[tuple[str, ...]] = set()
        seen_ids: set[str] = set()
        citations: set[str] = set()
        organic: set[tuple[str, str]] = set()
        for match in matches:
            kind = match.get("evidence_type")
            result_id = match.get("result_id")
            if _missing(result_id):
                result_id = record.get("result_id")
            if _visible(match):
                evidence_id = match.get("evidence_id")
                duplicate = (not _missing(evidence_id)
                             and str(evidence_id) in seen_ids)
                if not _missing(evidence_id):
                    seen_ids.add(str(evidence_id))
                # Missing spans cannot certify multiple occurrences.
                if not duplicate:
                    text_spans.add((str(result_id), *(str(match.get(key)) for key in (
                        "item_id", "matched_field",
                        "span_start", "span_end"
                    ))))
            if (kind == "owned_citation"
                    and not _missing(match.get("citation_id"))):
                citations.add(str(match["citation_id"]))
            if kind == "owned_organic" and not _missing(match.get("item_id")):
                organic.add((str(result_id), str(match["item_id"])))
        details.append({
            "brand_id": identity, "brand_name": names[0] if names else identity,
            "review_status": review,
            "text_mention_occurrence_count": len(text_spans),
            "citation_occurrence_count": len(citations),
            "owned_organic_item_count": len(organic),
            "evidence_types": sorted({str(row["evidence_type"]) for row in matches
                                      if not _missing(row.get("evidence_type"))}),
            "matches": matches,
        })
    groups = {
        "approved_evidenced": [row for row in details
                       if row["review_status"] == "approved"],
        "approved_mentioned": [row for row in details
                       if row["review_status"] == "approved"
                       and row["text_mention_occurrence_count"] > 0],
        "approved_cited": [row for row in details
                   if row["review_status"] == "approved"
                   and row["citation_occurrence_count"] > 0],
        "candidate": [row for row in details if row["review_status"] == "candidate"],
    }
    for prefix, rows in groups.items():
        output[f"{prefix}_brand_count"] = len(rows)
        output[f"{prefix}_brand_names"] = [row["brand_name"] for row in rows]
    output["matched_brand_details"] = details
    coverage, mention_status = _coverage(record)
    output.setdefault("coverage_status", coverage)
    output["brand_evidence_coverage_status"] = coverage
    output["mention_count_status"] = mention_status
    output["brand_count_scope"] = "observed_reviewed_identities_per_result_only"
    return output