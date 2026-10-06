# ruff: noqa: E501
"""Deterministic V0.2/V1 analytics and additive snapshot publication.

Public contract
---------------
``assess_v1(Path)`` is read-only, including when the database does not exist.
Returns ``complete: bool``, ``reasons: list[str]`` (blocking reason codes),
``warnings: list[str]``, ``counts: dict[str, int]``, ``metric_version: str``,
``minimum_runs: int`` and ``human_review_required: bool``. Counts contain
approved_brands, evidence_results, evidence_responses, metrics,
available_metrics, comparisons, matched_comparisons and opportunities.
Assessment uses minimum_runs=1; publication assesses its own requested threshold.

``publish_v1(Path, release_id, *, minimum_runs=1)`` returns that report plus
release_id, status='completed', document_counts and snapshot_sha256. Missing
database, invalid arguments, duplicate IDs or failed gates raise ValueError.
All reads, validation, additive DDL, documents and the 'current' slot update
occur in ONE transaction. Failure rolls back everything. No migrations,
enrichment, raw writes or legacy release/current-pointer writes occur here.

Schema: presentation.platform_releases(release_id VARCHAR PRIMARY KEY,
status VARCHAR, created_at TIMESTAMP, metric_version VARCHAR,
manifest_json VARCHAR); platform_documents(release_id VARCHAR, kind VARCHAR,
document_id VARCHAR, payload_json VARCHAR, PRIMARY KEY(release_id,kind,document_id));
platform_current(slot VARCHAR PRIMARY KEY, release_id VARCHAR).

Documents: coverage includes a 'summary' report and result/feature coverage;
metrics are brand/feature/instrument/locale/window slices; comparisons are
approved query/prompt slice comparisons, NOT response Cartesian products;
evidence contains safe result context, excerpts, matches, citation URLs and
hash/JSON-path lineage; registries copies each existing Bronze *_registry;
opportunities contains exploratory hypotheses requiring human review.
Every payload is an object, with document_id equal to its stored document key.
Opportunity payloads also expose opportunity_id=document_id. Durable governance
reviews (latest reviewed_at, review_id tie-break) and complete history are frozen
only into the next release; the viewer never overlays live review state.
presence_rate is an explicit alias of metric_value on metrics, including nulls.
Owned-organic comparisons retain their original IDs, null gap and pattern
semantics. Separate textual_presence_vs_answer_presence comparisons report
100 * (GEO answer presence rate - SERP visible organic text presence rate), in
percentage points, only on supported, fully complete matched slices.
SERP text uses typed raw title/description fields, never URLs or paid items;
normalized_text is a readable projection of those fields, not a text fallback.
Exposure concentration and unbranded ratio are observation-level, channel-local
descriptions of approved identities, not market share. Binary consistency uses
singleton-request known runs, not answer-text similarity or proven independence.
Locale uses recorded Silver best-known values, falling back only to explicit
requested locale. Requested/reported values remain separate: Silver may already
contain a request fallback and is not relabelled as provider-reported evidence.
Explicit is_synthetic metadata is propagated; unknown is not real. Mixed
synthetic and unlabelled/real source results block publication.

Metric denominator: distinct response IDs for which ALL result rows of that
feature are complete. Distinct known run IDs are reported separately; requests
without a run ID cannot meet minimum_runs. Partial positives are recorded but
excluded from both rate numerator and denominator. Unsupported/partial absence
is unknown, not zero. Answer mentions and owned citations are separate channels.
No semantic intent inference: intent is recorded query/prompt identity, with
any registered intent metadata preserved as instrument_registry.

Limits: existing Silver approved matches are trusted extraction evidence; this
does not re-enrich changed dictionaries. Current brand eligibility/effective
dates are rechecked. Gold v2 counts are preferred only when identical to the
Silver-derived count, preventing stale Gold from silently overriding evidence.
No demand, ROI, causality, expected-collection completeness, independent-trial
claim, Top3/Top10 metric, automatic approval or paid API calls. Synthetic test
provenance is retained, never described as production validation. Human review
is always required; absent explicit review metadata is a warning, not fabricated.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import duckdb

from geo_research.platform.presentation import (
    enrich_evidence_detail,
    enrich_locale_detail,
)
from geo_research.transforms.feature_evidence import visible_text
from geo_research.transforms.response_evidence import spans

Record = dict[str, Any]
Documents = dict[str, list[Record]]
METRIC_VERSION = "platform-v1.1.0-feature-v2-textual"
KINDS = ("coverage", "metrics", "comparisons", "evidence", "opportunities", "registries")
CONTEXT = (
    "source_category", "query_id", "prompt_id", "provider", "search_engine",
    "search_type", "device", "os", "platform", "model_name", "language_code",
    "location_code", "collection_window", "search_target_id",
    "requested_language_code", "requested_location_code",
    "reported_language_code", "reported_location_code", "is_synthetic",
)
_PLACEHOLDER = re.compile(
    r"to_be_verified|example|placeholder|sanitized|範例|示例", re.IGNORECASE
)
_SECRET_KEY = re.compile(
    r"password|passwd|secret|token|authorization|api[_-]?key|credential", re.IGNORECASE
)
_SECRET_TEXT = re.compile(
    r"(?i)(?:bearer|basic)\s+[A-Za-z0-9+/=_\-.]+|"
    r"(?:password|passwd|secret|token|authorization|api[_-]?key)"
    r"\s*[=:]\s*[\"']?[^\s,;\"']+"
)
_URL = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)

DDL = """
CREATE SCHEMA IF NOT EXISTS presentation;
CREATE TABLE IF NOT EXISTS presentation.platform_releases (
 release_id VARCHAR PRIMARY KEY, status VARCHAR, created_at TIMESTAMP,
 metric_version VARCHAR, manifest_json VARCHAR
);
CREATE TABLE IF NOT EXISTS presentation.platform_documents (
 release_id VARCHAR, kind VARCHAR, document_id VARCHAR, payload_json VARCHAR,
 PRIMARY KEY (release_id, kind, document_id)
);
CREATE TABLE IF NOT EXISTS presentation.platform_current (
 slot VARCHAR PRIMARY KEY, release_id VARCHAR
);
"""


def _safe_url(value: str) -> str:
    """Never copy URL credentials/query secrets into presentation documents."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return "[invalid URL]"
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        if parsed.port:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme.lower(), host, parsed.path, "", ""))
    except ValueError:
        return "[invalid URL]"


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if _SECRET_KEY.search(str(key)) else _safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return _safe(float(value))
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str):
        return _SECRET_TEXT.sub("[redacted]", _URL.sub(
            lambda match: _safe_url(match[0]), value
        ))
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _dump(value: Any) -> str:
    return json.dumps(_safe(value), sort_keys=True, ensure_ascii=False, allow_nan=False)


def _id(value: Any) -> str:
    return hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()


def _rows(connection: duckdb.DuckDBPyConnection, table: str) -> list[Record]:
    # Identifiers originate exclusively from information_schema, not user input.
    schema, name = table.split(".", 1)
    quoted = '.'.join('"' + part.replace('"', '""') + '"' for part in (schema, name))
    result = connection.execute(f"SELECT * FROM {quoted}")
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def _tables(connection: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        f"{schema}.{name}" for schema, name in connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables"
        ).fetchall()
    }


def _text(value: Any) -> str | None:
    return (str(value).strip() or None) if value is not None else None


def _eligible(brand: Record, collected_at: Any = None) -> bool:
    if (brand.get("active") is not True
            or str(brand.get("ownership_type", "")).lower() not in {"owned", "competitor"}
            or not _text(brand.get("canonical_name")) or _PLACEHOLDER.search(_dump(brand))):
        return False
    if brand.get("review_status") not in (None, "approved"):
        return False
    if collected_at is None:
        return not (brand.get("effective_start_date") or brand.get("effective_end_date"))
    day = str(collected_at)[:10]
    return (
        not brand.get("effective_start_date")
        or str(brand["effective_start_date"])[:10] <= day
    ) and (
        not brand.get("effective_end_date")
        or day <= str(brand["effective_end_date"])[:10]
    )


def _context(result: Record, request: Record) -> Record:
    category = result.get("source_category")
    identity = _text(request.get("query_id"))
    language = (_text(result.get("reported_language_code")) or _text(result.get("language_code"))
                or _text(request.get("requested_language_code")))
    window = _text(request.get("collection_window"))
    # Offline fallback windows isolate requests and do not authorize comparisons.
    if window and window.startswith("raw-request:"):
        window = None
    return {
        **{key: result.get(key) for key in CONTEXT},
        "query_id": identity if category == "serp" else None,
        "prompt_id": identity if category == "llm" else None,
        "intent": identity,
        "search_engine": request.get("search_engine") or (
            result.get("engine_or_platform") if category == "serp" else None
        ),
        "platform": request.get("platform") or (
            result.get("engine_or_platform") if category == "llm" else None
        ),
        "search_type": request.get("search_type"),
        "model_name": result.get("model_name") or request.get("model_name"),
        "search_target_id": request.get("search_target_id"),
        "language_code": language.lower().replace("_", "-") if language else None,
        "location_code": (_text(result.get("reported_location_code")) or _text(result.get("location_code"))
                  or _text(request.get("requested_location_code"))),
        "collection_window": window,
        "raw_language_code": result.get("language_code"),
        "raw_location_code": result.get("location_code"),
        "requested_language_code": _language(request.get("requested_language_code")),
        "requested_location_code": _text(request.get("requested_location_code")),
        "reported_language_code": _language(result.get("reported_language_code")),
        "reported_location_code": _text(result.get("reported_location_code")),
        "locale_basis": {
            field: "explicit_reported" if _text(result.get(f"reported_{field}")) else
            "silver_best_known" if _text(result.get(field)) else
            "explicit_requested" if _text(request.get(f"requested_{field}")) else "unknown"
            for field in ("language_code", "location_code")
        },
        **_provenance([request, result]),
    }


def _language(value: Any) -> str | None:
    text = _text(value)
    return text.lower().replace("_", "-") if text else None


def _metadata(row: Record) -> Record:
    """Only recorded object metadata; never infer from provider/name/path."""
    metadata: Record = {}
    for key in ("metadata_json", "source_metadata_json", "metadata"):
        value = row.get(key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if isinstance(value, dict):
            metadata.update(value)
    return {**metadata, **{key: value for key, value in row.items() if value is not None}}


def _provenance(rows: list[Record]) -> Record:
    sources = [_metadata(row) for row in rows]
    flags = {row.get("is_synthetic") for row in sources if type(row.get("is_synthetic")) is bool}
    provenance = [row[key] for row in sources for key in ("provenance", "synthetic_provenance") if row.get(key) is not None]
    return {"is_synthetic": True if True in flags else False if False in flags else None,
            "synthetic_metadata_conflict": len(flags) > 1 or any(row.get("synthetic_metadata_conflict") for row in sources),
            "source_provenance": sorted({_dump(value) for value in provenance}
                        | {value for row in sources for value in row.get("source_provenance", [])})}


def _brand_count(feature: str, matches: list[Record], items: dict[Any, Record]) -> int:
    identities: set[tuple[Any, ...]] = set()
    for match in matches:
        kind = match.get("evidence_type")
        item_id = match.get("item_id")
        if feature == "textual_presence" and kind == "serp_text":
            if (items.get(item_id, {}).get("item_kind") == "organic"
                    and match.get("matched_field") in {"title", "description"}):
                identities.add((item_id, match.get("matched_field"),
                                match.get("span_start"), match.get("span_end")))
        elif feature == "answer_text" and kind == "answer_text":
            if items.get(item_id, {}).get("item_kind") == "answer_text":
                identities.add((item_id, match.get("matched_field"),
                                match.get("span_start"), match.get("span_end")))
        elif feature == "citation" and kind == "owned_citation":
            if match.get("citation_id"):
                identities.add((match["citation_id"],))
        elif ((feature == "organic" and kind == "owned_organic")
              or (feature == "product" and kind == "product_text")
              or (feature == "paid" and kind == "paid_domain"
                  and items.get(item_id, {}).get("is_top_level"))):
            if item_id in items:
                identities.add((item_id,))
    return len(identities)


def _serp_text(
    results: list[Record], features: list[Record], items: list[Record],
    brands: list[Record], aliases: list[Record],
) -> tuple[list[Record], list[Record]]:
    """Revalidate reviewed terms against actual visible fields, not old URL hits.

    Bronze's reviewed alias schema historically has no status/activity columns;
    absent columns inherit the eligible parent brand. Explicit nonapproval or
    inactivity, placeholder terms and out-of-date aliases always exclude them.
    Existing v2 organic_title_snippet/legacy serp_title_snippet evidence is not
    blindly trusted: it may contain URL tokens inside the title. Recomputing with
    the existing boundary/longest-span matcher also prevents stale alias hits.
    """
    by_result: dict[str, list[Record]] = defaultdict(list)
    for item in items:
        if item.get("item_kind") == "organic":
            by_result[item["result_id"]].append(item)
    organic = {row["result_id"]: row for row in features if row["feature"] == "organic"}
    added_features, added_matches = [], []
    for result in results:
        if result.get("source_category") != "serp" or result["result_id"] not in organic:
            continue
        day = str(result.get("collected_at") or "")[:10]
        eligible = {row["brand_id"]: row for row in brands
                    if _eligible(row, result.get("collected_at"))}
        terms = [(key, row["canonical_name"]) for key, row in eligible.items()]
        terms.extend((row["brand_id"], row["alias_text"]) for row in aliases
                     if row.get("brand_id") in eligible
                     and isinstance(row.get("alias_text"), str) and _text(row["alias_text"])
                     and not _PLACEHOLDER.search(_dump(row))
                     and row.get("review_status") in (None, "approved")
                     and ("active" not in row or row["active"] is True)
                     and all(not row.get(field) or (bool(day) and (
                         str(row[field])[:10] <= day if field == "effective_start_date"
                         else day <= str(row[field])[:10]))
                         for field in ("effective_start_date", "effective_end_date")))
        issues = []
        for item in by_result[result["result_id"]]:
            raw = item.get("raw_evidence_json")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    raw = None
            fields = {field: visible_text(raw[field]) for field in ("title", "description")
                      if isinstance(raw, dict) and isinstance(raw.get(field), str)}
            malformed = (not isinstance(raw, dict) or not fields
                         or any(field in raw and raw[field] is not None
                                and not isinstance(raw[field], str)
                                for field in ("title", "description")))
            if malformed or item.get("coverage_status") != "complete":
                issues.append(item["item_id"] + ":visible_text_unavailable_or_partial")
            item["normalized_text"] = "\n".join(fields.values()) if fields else None
            item["text_method"] = "typed_visible_organic_title_description"
            for field, text in fields.items():
                for identity, start, end, _ in spans(text, terms):
                    added_matches.append({
                        "evidence_id": _id((item["item_id"], identity, "serp_text", field, start, end)),
                        "result_id": result["result_id"], "observation_id": result["observation_id"],
                        "item_id": item["item_id"], "identity_type": "brand",
                        "identity_id": identity, "identity_name": eligible[identity]["canonical_name"],
                        "review_status": "approved", "evidence_type": "serp_text",
                        "matched_field": field, "matched_text": text[start:end],
                        "span_start": start, "span_end": end,
                        "method": "reviewed_alias_boundary_longest_visible_text",
                        "registry_version": _id({"brands": sorted(eligible.values(), key=_dump),
                                                 "terms": sorted(set(terms))}),
                        "metric_version": METRIC_VERSION,
                    })
        feature = organic[result["result_id"]]
        status = feature.get("coverage_status")
        added_features.append({**feature, "feature": "textual_presence",
                               "feature_id": _id((result["result_id"], "textual_presence", METRIC_VERSION)),
                               "coverage_status": "partial" if status == "complete" and issues else status,
                               "issues_json": _dump(issues), "coverage_basis": "organic_and_typed_visible_fields"})
    return added_features, sorted({row["evidence_id"]: row for row in added_matches}.values(), key=_dump)


def _metrics(
    results: list[Record], features: list[Record], brands: list[Record],
    matches: list[Record], items: dict[Any, Record], requests: dict[Any, Record],
    gold: list[Record], minimum_runs: int,
) -> list[Record]:
    by_result = {row["result_id"]: row for row in results}
    by_match: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for match in matches:
        if match.get("identity_type") == "brand" and match.get("review_status") == "approved":
            by_match[(match["result_id"], match["identity_id"])].append(match)
    gold_index = {
        (row["result_id"], row["brand_id"], row["feature"]): row for row in gold
    }
    # One group per instrument slice, brand and independent feature.
    groups: dict[str, list[Record]] = defaultdict(list)
    for feature in features:
        result = by_result.get(feature["result_id"])
        if not result or not result.get("response_id"):
            continue
        request = requests.get(result.get("request_id"), {})
        context = _context(result, request)
        for brand in brands:
            if not _eligible(brand, result.get("collected_at")):
                continue
            channel = feature["feature"]
            count = _brand_count(channel, by_match[(result["result_id"], brand["brand_id"])], items)
            status = feature.get("coverage_status")
            value = count if status in {"complete", "partial"} else None
            candidate = gold_index.get((result["result_id"], brand["brand_id"], channel))
            verified_gold = bool(candidate and candidate.get("coverage_status") == status
                                 and candidate.get("observed_brand_count") == value)
            if verified_gold and candidate is not None:
                value = candidate["observed_brand_count"]
            key = {key: context[key] for key in CONTEXT}
            key.update(brand_id=brand["brand_id"], feature=channel)
            groups[_id(key)].append({
                **key, "intent": context["intent"],
                "source_context": context,
                "brand_canonical_name": brand["canonical_name"],
                "result_id": result["result_id"], "response_id": result["response_id"],
                "observation_id": result["observation_id"],
                "run_id": _text(request.get("run_id")), "coverage_status": status,
                "observed_brand_count": value,
                "count_source": "verified_gold_v2" if verified_gold else "silver_v2",
            })
    output: list[Record] = []
    for document_id, rows in sorted(groups.items()):
        responses: dict[str, list[Record]] = defaultdict(list)
        for row in rows:
            responses[row["response_id"]].append(row)
        complete = {
            response_id: members for response_id, members in responses.items()
            if all(row["coverage_status"] == "complete" for row in members)
            and all(row["observed_brand_count"] is not None for row in members)
            and {row["result_id"] for row in members} == {
                result["result_id"] for result in results
                if result.get("response_id") == response_id
            }
        }
        positive = {
            response_id for response_id, members in complete.items()
            if any(row["observed_brand_count"] > 0 for row in members)
        }
        observed_positive = {
            response_id for response_id, members in responses.items()
            if any((row["observed_brand_count"] or 0) > 0 for row in members)
        }
        runs = {row["run_id"] for members in complete.values() for row in members
                if row["run_id"] is not None}
        available = bool(complete) and len(runs) >= minimum_runs
        # Multiple requests in one run are not independent repeated trials.
        # Unknown runs and runs shared anywhere in this slice are excluded.
        run_requests: dict[str, set[Any]] = defaultdict(set)
        for row in rows:
            if row["run_id"]:
                request_id = by_result[row["result_id"]].get("request_id")
                run_requests[row["run_id"]].add(request_id)
        run_binary: dict[str, list[bool]] = defaultdict(list)
        for response_id, members in complete.items():
            response_runs = {row["run_id"] for row in members}
            if len(response_runs) == 1:
                run_id = next(iter(response_runs))
                if run_id and len(run_requests[run_id]) == 1 and None not in run_requests[run_id]:
                    run_binary[run_id].append(response_id in positive)
        trials = {run_id: values[0] for run_id, values in run_binary.items()
                  if len(values) == 1}
        trial_positive = sum(trials.values())
        consistency = (max(trial_positive, len(trials) - trial_positive) / len(trials)
                       if len(trials) >= max(2, minimum_runs) else None)
        observation_members: dict[Any, list[Record]] = defaultdict(list)
        for row in rows:
            observation_members[row["observation_id"]].append(row)
        complete_observations = {
            observation_id: members for observation_id, members in observation_members.items()
            if all(row["response_id"] in complete for row in members)
            and {row["result_id"] for row in members} == {
                result["result_id"] for result in results
                if result["observation_id"] == observation_id
            }
        }
        positive_observations = sum(any(row["observed_brand_count"] > 0 for row in members)
                                    for members in complete_observations.values())
        base = {key: rows[0][key] for key in (*CONTEXT, "brand_id", "feature",
                                            "intent", "brand_canonical_name")}
        output.append({
            **base, "document_id": document_id, "metric_version": METRIC_VERSION,
            "metric_name": f"{base['feature']}_brand_response_presence",
            "sample_unit": "distinct_complete_response",
            "observation_presence": {
                "sample_unit": "distinct_complete_observation",
                "numerator": positive_observations, "denominator": len(complete_observations),
                "presence_rate": positive_observations / len(complete_observations)
                if available and complete_observations else None,
                "complete_observation_ids": sorted(complete_observations),
            },
            "binary_run_consistency": {
                "metric_value": consistency,
                "availability_status": "available" if consistency is not None else "insufficient_independent_runs",
                "definition": "modal binary presence count / singleton-request distinct complete known runs; not text similarity",
                "distinct_known_run_count": len(runs), "eligible_run_count": len(trials),
                "eligible_run_ids": sorted(trials), "positive_run_count": trial_positive,
                "shared_request_run_ids": sorted(run_id for run_id, ids in run_requests.items() if len(ids) > 1),
                "independence_basis": "distinct recorded IDs with one request and one complete response; statistical independence not verified",
            },
            "numerator": len(positive), "denominator": len(complete),
            "metric_value": len(positive) / len(complete) if available else None,
            "presence_rate": len(positive) / len(complete) if available else None,
            "source_contexts": sorted({_dump(row["source_context"]): row["source_context"] for row in rows}.values(), key=_dump),
            "source_provenance": sorted({value for row in rows for value in row["source_context"]["source_provenance"]}),
            "availability_status": "available" if available else (
                "insufficient_runs" if complete else "unknown"
            ),
            "complete_response_count": len(complete), "complete_run_count": len(runs),
            "observed_response_count": len(responses),
            "observed_positive_response_count": len(observed_positive),
            "partial_positive_response_count": len(observed_positive - set(complete)),
            "unknown_response_count": len(responses) - len(complete),
            "response_ids": sorted(responses), "complete_response_ids": sorted(complete),
            "observation_ids": sorted({row["observation_id"] for row in rows}),
            "result_ids": sorted({row["result_id"] for row in rows}),
            "run_ids": sorted(runs),
            "coverage_statuses": sorted({str(row["coverage_status"]) for row in rows}),
            "count_sources": sorted({row["count_source"] for row in rows}),
            "observed_brand_count": sum(row["observed_brand_count"] or 0 for row in rows)
            if any(row["observed_brand_count"] is not None for row in rows) else None,
        })
    return output


def _exposure_coverage(
    results: list[Record], features: list[Record], brands: list[Record],
    matches: list[Record], items: dict[Any, Record], requests: dict[Any, Record],
    minimum_runs: int,
) -> list[Record]:
    """Channel-local observed exposure; one brand incidence per observation.

    HHI = sum((brand incidence / total incidences)^2), on [0,1]. Unbranded
    observations stay in unbranded ratio but contribute no brand incidences.
    An entirely unbranded slice has undefined HHI, not perfect concentration.
    Eligibility roster is pinned per group so changing dictionaries do not
    silently merge differently scoped absence or concentration denominators.
    """
    statuses: dict[tuple[Any, Any], list[Any]] = defaultdict(list)
    for feature in features:
        statuses[(feature["result_id"], feature["feature"])].append(feature.get("coverage_status"))
    by_match: dict[tuple[Any, Any], list[Record]] = defaultdict(list)
    for match in matches:
        if match.get("identity_type") == "brand" and match.get("review_status") == "approved":
            by_match[(match["result_id"], match["identity_id"])].append(match)
    groups: dict[str, list[Record]] = defaultdict(list)
    for result in results:
        context = _context(result, requests.get(result.get("request_id"), {}))
        channel = "textual_presence" if context["source_category"] == "serp" else "answer_text"
        roster = sorted(row["brand_id"] for row in brands if _eligible(row, result.get("collected_at")))
        key = {field: context[field] for field in CONTEXT}
        key.update(intent=context["intent"], feature=channel, eligible_brand_ids=roster)
        groups[_id(key)].append({"key": key, "result": result})
    output = []
    for key_id, rows in sorted(groups.items()):
        key = rows[0]["key"]
        observations: dict[Any, list[Record]] = defaultdict(list)
        for row in rows:
            observations[row["result"]["observation_id"]].append(row["result"])
        complete: dict[Any, set[str]] = {}
        complete_runs: set[str] = set()
        for observation_id, members in observations.items():
            # An observation spanning another instrument/locale slice is unknown.
            if ({row["result_id"] for row in members} != {
                    row["result_id"] for row in results if row["observation_id"] == observation_id}
                    or not all(row.get("response_id") and statuses[(row["result_id"], key["feature"])]
                               and all(status == "complete" for status in statuses[(row["result_id"], key["feature"])])
                               for row in members)):
                continue
            complete[observation_id] = {brand_id for brand_id in key["eligible_brand_ids"]
                if any(_brand_count(key["feature"], by_match[(row["result_id"], brand_id)], items) > 0 for row in members)}
            complete_runs.update(run_id for row in members
                                 if (run_id := _text(requests.get(row.get("request_id"), {}).get("run_id"))))
        incidences = {brand_id: sum(brand_id in present for present in complete.values())
                      for brand_id in key["eligible_brand_ids"]}
        total = sum(incidences.values())
        n = len(complete)
        known_context = all(key.get(field) for field in ("intent", "provider", "language_code", "location_code", "collection_window"))
        available = bool(n and key["eligible_brand_ids"] and known_context and len(complete_runs) >= minimum_runs)
        output.append({
            **key, "document_id": "observed-exposure:" + key_id, "coverage_kind": "observed_exposure",
            "metric_version": METRIC_VERSION, "sample_unit": "distinct_complete_observation",
            "distinct_n": n, "complete_observation_ids": sorted(complete),
            "observed_observation_count": len(observations), "unknown_observation_count": len(observations) - n,
            "brand_observation_counts": incidences, "total_brand_observation_exposures": total,
            "hhi_observed_exposure": sum((count / total) ** 2 for count in incidences.values()) if available and total else None,
            "unbranded_observation_count": sum(not present for present in complete.values()),
            "unbranded_ratio": sum(not present for present in complete.values()) / n if available else None,
            "availability_status": "available" if available else "missing_context" if not known_context else "unknown" if not n else "insufficient_runs",
            "hhi_availability_status": "available" if available and total else "no_branded_exposure" if available else "unknown",
            "definition": "HHI=sum((brand complete-observation incidences/total brand incidences)^2); unbranded ratio=complete observations without eligible textual brands/distinct n",
            "limitations": ["Observed channel exposure only, not market share", "Unbranded means no eligible registry identity, not no real-world brand"],
        })
    return output


def _comparisons(
    metrics: list[Record], mappings: list[Record], *, textual: bool = False,
) -> list[Record]:
    output: list[Record] = []
    for mapping in mappings:
        if mapping.get("active") is not True or _PLACEHOLDER.search(_dump(mapping)):
            continue
        if mapping.get("review_status") not in (None, "approved"):
            continue
        serp = [row for row in metrics if row["source_category"] == "serp"
            and row["query_id"] == mapping["query_id"]
            and row["feature"] == ("textual_presence" if textual else "organic")]
        llm = [row for row in metrics if row["source_category"] == "llm"
               and row["prompt_id"] == mapping["prompt_id"] and row["feature"] == "answer_text"]
        used: set[str] = set()

        def add(
            left: Record | None, right: Record | None, eligibility: str,
            mapping: Record = mapping,
        ) -> None:
            base = left or right or {}
            available = bool(left and right and eligibility == "matched_context"
                             and left["availability_status"] == "available"
                             and right["availability_status"] == "available")
            if textual:
                available = bool(available and left and right
                                 and left["unknown_response_count"] == 0
                                 and right["unknown_response_count"] == 0)
            record: Record = {
                "comparison_id": mapping["comparison_id"], "query_id": mapping["query_id"],
                "prompt_id": mapping["prompt_id"], "brand_id": base.get("brand_id"),
                "language_code": base.get("language_code"),
                "location_code": base.get("location_code"),
                "collection_window": base.get("collection_window"),
                "comparison_eligibility": eligibility,
                "serp_metric_id": left["document_id"] if left else None,
                "llm_metric_id": right["document_id"] if right else None,
                "serp": left, "llm": right,
                "comparison_kind": "textual_presence_vs_answer_presence" if textual else "owned_organic_vs_answer_presence",
                "metric_version": METRIC_VERSION,
                "metric_value": 100 * (right["presence_rate"] - left["presence_rate"]) if textual and available and left and right else None,
                "metric_unit": "percentage_point" if textual else None,
                "metric_definition": "100 * (GEO answer response presence rate - SERP visible organic text response presence rate)" if textual else "owned organic and answer presence patterns only",
                "serp_presence_rate": left["presence_rate"] if left else None,
                "llm_presence_rate": right["presence_rate"] if right else None,
                "serp_present": left["numerator"] > 0 if available and left else None,
                "llm_present": right["numerator"] > 0 if available and right else None,
                "textual_mention_gap_status": ("available" if available else "unknown") if textual else "not_applicable_owned_channel",
                "limitations": ["Visible organic title/description only; matched instrument slices, not paired independent trials"] if textual else ["Owned organic presence and answer mentions are different channels; no comparable textual mention gap"],
                "is_synthetic": base.get("is_synthetic"),
                "source_provenance": sorted({value for row in (left, right) if row for value in row.get("source_provenance", [])}),
                "available": available,
                "availability_basis": "supported_fully_complete_textual_slices" if textual else "evaluable_presence_pattern_not_gap_rate",
                "availability_status": "available" if available else "unknown",
                "distinct_serp_response_count": left["complete_response_count"] if left else 0,
                "distinct_llm_response_count": right["complete_response_count"] if right else 0,
                "sample_unit": "instrument_slice_not_independent_pairs",
            }
            record["document_id"] = _id({
                key: record[key] for key in ("comparison_id", "serp_metric_id", "llm_metric_id")
            })
            if textual:
                # Unmatched LLM-only slices have the same left=None as legacy
                # comparisons; namespace the new definition without changing
                # any historical owned-organic comparison/opportunity key.
                record["document_id"] = _id((record["document_id"], "textual_presence", METRIC_VERSION))
            record["presence_pattern"] = (
                "both_present" if record["serp_present"] and record["llm_present"] else
                "serp_present_llm_absent" if record["serp_present"] else
                "llm_present_serp_absent" if record["llm_present"] else "neither_present"
            ) if available else None
            output.append(record)

        for left in serp:
            locale = tuple(left[key] for key in ("language_code", "location_code", "collection_window"))
            partners = [right for right in llm if right["brand_id"] == left["brand_id"]
                        and right.get("is_synthetic") == left.get("is_synthetic")
                        and all(locale) and locale == tuple(right[key] for key in (
                            "language_code", "location_code", "collection_window"))]
            if partners:
                for right in partners:
                    used.add(right["document_id"])
                    add(left, right, "matched_context")
            else:
                add(left, None, "unmatched_context" if all(locale) else "missing_context")
        for right in llm:
            if right["document_id"] not in used:
                known = all(right[key] for key in ("language_code", "location_code", "collection_window"))
                add(None, right, "unmatched_context" if known else "missing_context")
        if not serp and not llm:
            add(None, None, "not_collected")
    return output


def _build(connection: duckdb.DuckDBPyConnection, minimum_runs: int) -> tuple[Record, Documents]:
    tables = _tables(connection)

    def read(table: str) -> list[Record]:
        return _rows(connection, table) if table in tables else []

    registry = {table: read(table) for table in sorted(tables)
                if table.startswith("bronze.") and table.endswith("_registry")}
    results = read("silver.evidence_results_v2")
    brands = registry.get("bronze.brand_registry", [])
    approved = [brand for brand in brands if any(
        _eligible(brand, result.get("collected_at")) for result in results
    ) or _eligible(brand)]
    features = read("silver.evidence_features_v2")
    items = read("silver.evidence_items_v2")
    matches = read("silver.evidence_matches_v2")
    requests = {row["request_id"]: _metadata(row) for row in read("bronze.api_requests")}
    responses = {row["response_id"]: _metadata(row) for row in read("bronze.api_responses")}
    for request in requests.values():
        for field in ("language_code", "location_code"):
            request.setdefault(f"requested_{field}", request.get(field))
    for result in results:
        metadata = _metadata(result)
        response = responses.get(result.get("response_id"), {})
        for field in ("language_code", "location_code"):
            result[f"reported_{field}"] = metadata.get(f"reported_{field}") or response.get(f"reported_{field}")
        result.update(_provenance([requests.get(result.get("request_id"), {}), response, metadata]))
    targets = {row["search_target_id"]: row for row in
               registry.get("bronze.search_target_registry", [])}
    for request in requests.values():
        target = targets.get(request.get("search_target_id"), {})
        if "search_type" not in request:
            request["search_type"] = target.get("search_type")
    text_features, text_matches = _serp_text(
        results, features, items, approved, registry.get("bronze.brand_alias_registry", []),
    )
    features = features + text_features
    # Existing extraction evidence remains intact. Derived text is an explicitly
    # versioned additional channel; never trusts URL-containing legacy spans.
    matches = [row for row in matches if row.get("evidence_type") != "serp_text"] + text_matches
    metrics = _metrics(results, features, approved, matches,
                       {row["item_id"]: row for row in items}, requests,
                       read("analytics.gold_feature_brand_visibility_v2"), minimum_runs)
    # Preserve recorded query/prompt intent/group metadata, never infer from text.
    instruments = {
        ("serp", row["query_id"]): row for row in registry.get("bronze.query_registry", [])
    }
    instruments.update({
        ("llm", row["prompt_id"]): row for row in registry.get("bronze.llm_prompt_registry", [])
    })
    for metric in metrics:
        metric["instrument_registry"] = instruments.get((metric["source_category"], metric["intent"]))
    mappings = registry.get("bronze.comparison_registry", [])
    comparisons = _comparisons(metrics, mappings) + _comparisons(metrics, mappings, textual=True)
    reviews: dict[str, list[Record]] = defaultdict(list)
    for review in read("governance.platform_opportunity_reviews"):
        reviews[review["opportunity_id"]].append(review)
    opportunities: list[Record] = []
    for comparison in comparisons:
        if (comparison["availability_status"] != "available"
                or comparison["comparison_kind"] != "owned_organic_vs_answer_presence"):
            continue
        left, right = comparison["serp"], comparison["llm"]
        serp_present, llm_present = left["numerator"] > 0, right["numerator"] > 0
        if serp_present and llm_present:
            continue
        pattern = "serp_present_llm_absent" if serp_present else (
            "llm_present_serp_absent" if llm_present else "neither_present"
        )
        opportunity_id = _id((comparison["document_id"], pattern))
        history = sorted(reviews[opportunity_id], key=lambda row: (str(row.get("reviewed_at") or ""), str(row.get("review_id") or "")))
        latest = history[-1] if history else {}
        opportunities.append({
            "document_id": opportunity_id, "opportunity_id": opportunity_id,
            "comparison_kind": comparison["comparison_kind"],
            **{key: comparison.get(key) for key in ("query_id", "prompt_id", "language_code", "location_code", "collection_window")},
            "is_synthetic": comparison["is_synthetic"],
            "source_provenance": comparison["source_provenance"],
            "comparison_document_id": comparison["document_id"],
            "brand_id": comparison["brand_id"], "pattern": pattern,
            "classification": "exploratory_hypothesis", "human_review_required": True,
            "review_status": latest.get("status", "unreviewed"),
            "owner": latest.get("owner"), "notes": latest.get("notes"),
            "reviewed_at": latest.get("reviewed_at"), "review_history": history,
            "comparison": comparison,
            "evidence_result_ids": sorted(set(left["result_ids"] + right["result_ids"])),
            "limitations": ["Observed feature absence only within complete responses",
                            "Owned organic presence is not SERP textual mention absence; separate textual comparison is not this hypothesis",
                            "Not evidence of demand, traffic, ROI or causality",
                            "Matched locale/window does not prove controlled pairing"],
        })
    warnings = ["recommendation_and_risk_require_manual_labels"]
    if not opportunities or any(row["review_status"] == "unreviewed" for row in opportunities):
        warnings.append("human_review_missing")
    if not registry.get("bronze.comparison_registry"):
        warnings.append("approved_comparison_mapping_missing")
    reasons: list[str] = []
    required = {
        "silver.evidence_results_v2", "silver.evidence_features_v2",
        "silver.evidence_items_v2", "silver.evidence_matches_v2",
        "silver.evidence_citations_v2", "bronze.api_requests",
    }
    if not required <= tables:
        reasons.append("evidence_schema_missing")
    if not approved:
        reasons.append("no_approved_brands")
    approved_ids = {row["brand_id"] for row in approved}
    domains = [row for row in registry.get("bronze.brand_domain_registry", [])
               if row.get("brand_id") in approved_ids and _text(row.get("domain"))
               and row.get("review_status") in (None, "approved")
               and not _PLACEHOLDER.search(_dump(row))
               and not str(row["domain"]).endswith(".test")]
    if not domains:
        reasons.append("no_approved_domains")
    provenance_flags = {row.get("is_synthetic") for row in results}
    if True in provenance_flags and provenance_flags != {True}:
        reasons.append("mixed_synthetic_source_evidence")
    if any(row.get("synthetic_metadata_conflict") for row in results):
        reasons.append("conflicting_synthetic_source_metadata")
    underlying = [row for row in results if row.get("response_id") and row.get("raw_file_hash")]
    if not underlying:
        reasons.append("no_underlying_evidence")
    # Every metric lineage must be backed by a hash-bearing result, not just Gold.
    valid_ids = {row["result_id"] for row in underlying}
    if any(not set(metric["result_ids"]) <= valid_ids for metric in metrics):
        reasons.append("metric_evidence_lineage_missing")
    available = [metric for metric in metrics if metric["availability_status"] == "available"]
    if not available:
        reasons.append("no_approved_metrics")
    report: Record = {
        "complete": not reasons, "reasons": reasons, "warnings": warnings,
        "metric_version": METRIC_VERSION, "minimum_runs": minimum_runs,
        "human_review_required": True,
        "counts": {
            "approved_brands": len(approved), "evidence_results": len(results),
            "evidence_responses": len({row["response_id"] for row in underlying}),
            "metrics": len(metrics), "available_metrics": len(available),
            "comparisons": len(comparisons), "matched_comparisons": sum(
                row["comparison_eligibility"] == "matched_context" for row in comparisons
            ), "opportunities": len(opportunities),
        },
    }
    docs: Documents = {kind: [] for kind in KINDS}
    docs["coverage"] = [{"document_id": "summary", **report,
                         "manual_label_metrics": {
                             "recommendation": {"availability_status": "unavailable_manual_labels_required", "metric_value": None},
                             "risk": {"availability_status": "unavailable_manual_labels_required", "metric_value": None},
                         },
                         "opportunity_basis": "legacy_owned_organic_presence_patterns; textual gaps do not reinterpret existing opportunity IDs"}]
    docs["coverage"].extend(_exposure_coverage(
        results, features, approved, matches, {row["item_id"]: row for row in items}, requests, minimum_runs,
    ))
    docs["metrics"] = [enrich_locale_detail(row) for row in metrics]
    docs["comparisons"] = [enrich_locale_detail(row) for row in comparisons]
    docs["opportunities"] = opportunities
    for table, rows in registry.items():
        docs["registries"].append({
            "document_id": table, "table": table, "rows": sorted(rows, key=_dump),
            "registry_sha256": _id(sorted(rows, key=_dump)),
        })
    by_result: dict[str, list[Record]] = defaultdict(list)
    for item in items:
        by_result[item["result_id"]].append({
            key: item.get(key) for key in ("item_id", "parent_item_id", "json_path",
                                         "item_kind", "coverage_status", "url", "title")
        } | {"excerpt": str(item.get("normalized_text") or item.get("description") or "")[:600]})
    citations: dict[str, list[Record]] = defaultdict(list)
    for citation in read("silver.evidence_citations_v2"):
        citations[citation["result_id"]].append(citation)
    result_matches: dict[str, list[Record]] = defaultdict(list)
    for match in matches:
        result_matches[match["result_id"]].append(match)
    result_features: dict[str, list[Record]] = defaultdict(list)
    for feature in features:
        result_features[feature["result_id"]].append(feature)
    raw_files: dict[Any, list[Record]] = defaultdict(list)
    for raw_file in read("bronze.raw_files"):
        raw_files[raw_file["request_id"]].append({
            key: raw_file.get(key) for key in ("artifact_type", "relative_path", "sha256")
        })
    for result in results:
        result_id = result["result_id"]
        context = _context(result, requests.get(result.get("request_id"), {}))
        docs["coverage"].append({
            "document_id": result_id, **context,
            "result_id": result_id, "observation_id": result["observation_id"],
            "response_id": result.get("response_id"),
            "collection_status": result.get("collection_status"),
            "features": sorted(result_features[result_id], key=_dump),
            "brand_coverage_status": "approved_registry" if approved else "no_approved_registry",
        })
        safe_result = {key: value for key, value in result.items() if key != "issues_json"}
        docs["evidence"].append(enrich_evidence_detail({
            **safe_result, **context, "document_id": result_id,
            "approved_registry_available": any(_eligible(brand, result.get("collected_at")) for brand in approved),
            "features": sorted(result_features[result_id], key=_dump),
            "items": sorted(by_result[result_id], key=_dump),
            "citations": sorted(citations[result_id], key=_dump),
            "matches": sorted(result_matches[result_id], key=_dump),
            "raw_files": sorted(raw_files[result.get("request_id")], key=_dump),
        }))
    # Sanitize BEFORE hashing/storage, so the manifest describes exact safe payloads.
    return report, {kind: sorted((_safe(row) for row in rows), key=lambda row: row["document_id"])
                    for kind, rows in docs.items()}


def assess_v1(database_path: Path) -> dict[str, Any]:
    """Read-only eligibility report; see module docstring for exact contract."""
    if not database_path.is_file():
        return {
            "complete": False, "reasons": ["database_missing"],
            "warnings": ["human_review_missing"], "human_review_required": True,
            "metric_version": METRIC_VERSION, "minimum_runs": 1,
            "counts": dict.fromkeys(("approved_brands", "evidence_results", "evidence_responses",
                                     "metrics", "available_metrics", "comparisons",
                                     "matched_comparisons", "opportunities"), 0),
        }
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            report, _ = _build(connection, 1)
            connection.execute("COMMIT")
            return report
        except Exception:
            connection.execute("ROLLBACK")
            raise


def publish_v1(
    database_path: Path, release_id: str, *, minimum_runs: int = 1,
) -> dict[str, Any]:
    """Atomically validate, freeze six document kinds and switch platform current."""
    if not isinstance(release_id, str) or not release_id.strip():
        raise ValueError("release_id must be a nonempty string")
    if isinstance(minimum_runs, bool) or not isinstance(minimum_runs, int) or minimum_runs < 1:
        raise ValueError("minimum_runs must be a positive integer")
    if not database_path.is_file():
        raise ValueError("database_missing")
    with duckdb.connect(str(database_path)) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            if "presentation.platform_releases" in _tables(connection):
                existing = connection.execute(
                    "SELECT 1 FROM presentation.platform_releases WHERE release_id=?", [release_id]
                ).fetchone()
                if existing:
                    raise ValueError("release_id already exists; snapshots are immutable")
            report, documents = _build(connection, minimum_runs)
            if not report["complete"]:
                raise ValueError("publication blocked: " + ", ".join(report["reasons"]))
            connection.execute(DDL)
            manifest = {
                **report, "release_id": release_id, "status": "completed",
                "document_counts": {kind: len(rows) for kind, rows in documents.items()},
                "snapshot_sha256": _id(documents),
            }
            connection.execute(
                "INSERT INTO presentation.platform_releases VALUES "
                "(?, 'completed', current_timestamp, ?, ?)",
                [release_id, METRIC_VERSION, _dump(manifest)],
            )
            for kind, rows in documents.items():
                if rows:
                    connection.executemany(
                        "INSERT INTO presentation.platform_documents VALUES (?, ?, ?, ?)",
                        [(release_id, kind, row["document_id"], _dump(row)) for row in rows],
                    )
            connection.execute(
                "INSERT INTO presentation.platform_current VALUES ('current', ?) "
                "ON CONFLICT (slot) DO UPDATE SET release_id=excluded.release_id", [release_id]
            )
            connection.execute("COMMIT")
            return manifest
        except Exception:
            connection.execute("ROLLBACK")
            raise