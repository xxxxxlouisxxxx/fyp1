"""Read-only V1 UI over completed platform documents, never live analytics.

Required storage contract: presentation.platform_releases(release_id, status,
created_at, metric_version, manifest_json), platform_current(slot, release_id),
platform_documents(release_id, kind, document_id, payload_json). The default
pointer slot is 'current'. Payloads are JSON objects (or lists of objects).
Metric definitions, eligibility and frozen review states belong to the publisher;
this viewer neither recomputes rates nor infers demand or publication readiness.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import duckdb
import pandas as pd  # type: ignore[import-untyped]  # Optional pandas stubs.
import streamlit as st

from geo_research.platform.presentation import (
    enrich_evidence_detail,
    language_label,
    location_label,
)

KINDS = ("coverage", "metrics", "comparisons", "evidence", "opportunities",
         "registries")
FILTER_COLUMNS = (
    "brand_id", "source_category", "language_code", "location_code",
    "collection_window", "provider", "search_engine", "platform", "model_name",
    "intent_id",
)
VIEWS = (
    "Overview · Data Readiness", "Need × Market", "Brand Competition",
    "Evidence & Citation Explorer", "Opportunity Queue",
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LIMITATIONS = (
    "Observed visibility is not demand, traffic, conversion, causality or ROI. "
    "Query/prompt intent is an observation label, not verified buyer need. "
    "Unknown and unavailable values remain unknown, never numeric zero. "
    "Textual presence gap is 100 × (GEO answer presence rate − SERP visible "
    "organic title/description presence rate), in percentage points, only for "
    "supported, fully complete matched slices; otherwise it is unknown. "
    "The separate owned organic versus answer presence pattern is not that "
    "textual gap and has no numeric gap. "
    "Synthetic provenance is source-recorded, "
    "not inferred; unlabelled records are not certified real. "
    "觀測曝光不代表需求、流量、轉化或投資回報；機會僅為待驗證假設。"
)
EMPTY_INSTRUCTIONS = (
    "No usable completed V1 platform release is selected. Ask the publishing "
    "pipeline owner to freeze coverage, metrics, comparisons, evidence, "
    "opportunities and registries documents, mark the platform release completed, "
    "and set platform_current slot 'current', or select a completed historic "
    "release. This viewer cannot publish, collect or repair data. "
    "尚無可用的已完成 V1 快照；請先由發布流程確認覆蓋與證據。"
)


@dataclass(frozen=True)
class PlatformSnapshot:
    """Immutable serialized backing; each accessor returns detached materializations.

    ``release`` is a metadata dict or None; ``releases`` is a completed-only
    DataFrame; ``records`` maps every known kind to a tuple of record dicts;
    ``frames`` maps every kind to a DataFrame. Mutating these copies cannot change
    the snapshot. Empty/error snapshots have all six empty kinds and a message.
    """

    _release_json: str | None = None
    _releases_json: str = "[]"
    _documents: tuple[tuple[str, str, str], ...] = ()
    message: str | None = None

    @property
    def release(self) -> dict[str, Any] | None:
        return json.loads(self._release_json) if self._release_json else None

    @property
    def releases(self) -> pd.DataFrame:
        return pd.DataFrame(json.loads(self._releases_json), columns=[
            "release_id", "status", "created_at", "metric_version", "manifest_json",
        ])

    @property
    def records(self) -> dict[str, tuple[dict[str, Any], ...]]:
        grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
        release = self.release
        for kind, document_id, payload in self._documents:
            decoded = json.loads(payload)
            for row in decoded if isinstance(decoded, list) else [decoded]:
                grouped[kind].append({
                    **row, "document_id": document_id,
                    "release_id": release["release_id"] if release else None,
                })
        return {kind: tuple(rows) for kind, rows in grouped.items()}

    @property
    def frames(self) -> dict[str, pd.DataFrame]:
        # Object dtype preserves JSON integers/codes alongside None without
        # coercing provider IDs to floats or missing numeric values to zero.
        return {kind: pd.DataFrame(rows, dtype=object)
            for kind, rows in self.records.items()}


def _serialize(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, allow_nan=False)


def load_platform_snapshot(
    database: Path, release_id: str | None = None,
) -> PlatformSnapshot:
    """Load metadata, pointer and documents in one read-only transaction.

    No latest-release fallback, schema initialization, cache, APIs or live tables.
    Explicit historical selection must also be completed. Malformed documents
    fail closed, retaining the completed release selector for recovery.
    """
    database = Path(database)
    if not database.is_file():
        return PlatformSnapshot(message="Warehouse is missing; no file was created.")
    releases_json = "[]"
    connection = None
    try:
        connection = duckdb.connect(str(database), read_only=True)
        connection.execute("BEGIN TRANSACTION")
        rows = connection.execute(
            "SELECT release_id, status, created_at, metric_version, manifest_json "
            "FROM presentation.platform_releases WHERE status = 'completed' "
            "ORDER BY created_at DESC, release_id"
        ).fetchall()
        fields = ("release_id", "status", "created_at", "metric_version",
                  "manifest_json")
        releases = [dict(zip(fields, row, strict=True)) for row in rows]
        releases_json = _serialize(releases)
        if release_id is None:
            pointers = connection.execute(
                "SELECT release_id FROM presentation.platform_current "
                "WHERE slot = ?", ["current"],
            ).fetchall()
            release_id = pointers[0][0] if len(pointers) == 1 else None
        selected = [row for row in releases if row["release_id"] == release_id]
        if len(selected) != 1:
            connection.execute("COMMIT")
            return PlatformSnapshot(
                _releases_json=releases_json,
                message="Selected/current release is not a completed V1 release.",
            )
        documents = connection.execute(
            "SELECT kind, document_id, payload_json "
            "FROM presentation.platform_documents WHERE release_id = ? "
            "ORDER BY kind, document_id", [release_id],
        ).fetchall()
        materialized = []
        for kind, document_id, payload in documents:
            if kind not in KINDS:
                continue  # Future kinds never enter V1 analytics implicitly.
            decoded = json.loads(payload)
            records = decoded if isinstance(decoded, list) else [decoded]
            if not all(isinstance(row, dict) for row in records):
                raise ValueError("Platform payload must contain JSON records")
            materialized.append((kind, str(document_id), _serialize(decoded)))
        connection.execute("COMMIT")
        return PlatformSnapshot(
            _release_json=_serialize(selected[0]), _releases_json=releases_json,
            _documents=tuple(materialized),
        )
    except (duckdb.Error, ValueError, TypeError):
        # Do not expose exception details: paths/SQL/provider secrets may occur.
        return PlatformSnapshot(
            _releases_json=releases_json,
            message="V1 snapshot unavailable: missing contract, lock or invalid JSON.",
        )
    finally:
        if connection is not None:
            connection.close()  # Also rolls back any failed read transaction.


def safe_url(value: Any) -> str | None:
    """Permit only absolute HTTP(S) evidence URLs without credentials/controls."""
    if not isinstance(value, str) or not value:
        return None
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    if "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return None
        _ = parsed.port  # Invalid ports must not create execution links.
    except ValueError:
        return None
    return value


def _unknown(value: Any) -> bool:
    if isinstance(value, (dict, list, tuple)):
        return False
    return bool(pd.isna(value))


def display(value: Any) -> str:
    if _unknown(value):
        return "Unknown (not recorded)"
    if isinstance(value, (dict, list, tuple)):
        return _serialize(value)
    return str(value)


def _filter_value(row: Mapping[str, Any], column: str) -> Any:
    if column == "intent_id" and _unknown(row.get(column)):
        # Preserve query/prompt identity; do not invent semantic equivalence.
        for key in ("query_id", "prompt_id"):
            if not _unknown(row.get(key)):
                return f"{key}:{row[key]}"
    return row.get(column)


def _approved_brand_ids(row: Mapping[str, Any]) -> set[str]:
    """Nested approved extraction identities only; candidates are not brands."""
    matches = row.get("matches")
    if not isinstance(matches, (list, tuple)):
        return set()
    return {
        str(match.get("identity_id", match.get("brand_id")))
        for match in matches
        if isinstance(match, Mapping)
        and match.get("identity_type") == "brand"
        and match.get("review_status") == "approved"
           and not _unknown(match.get("identity_id", match.get("brand_id")))
           and (_unknown(row.get("result_id")) or _unknown(match.get("result_id"))
               or match["result_id"] == row["result_id"])
    }


def filter_options(
    frames: Mapping[str, pd.DataFrame], column: str,
) -> list[str | None]:
    values: list[Any] = []
    for kind, frame in frames.items():
        for row in frame.to_dict("records"):
            if kind == "evidence" and column == "brand_id":
                values.extend(_approved_brand_ids(row) or [None])
            else:
                values.append(_filter_value(row, column))
    known = sorted({str(value) for value in values if not _unknown(value)})
    return [*known, *([None] if any(_unknown(v) for v in values) else [])]


def filter_frames(
    frames: Mapping[str, pd.DataFrame],
    filters: Mapping[str, Sequence[str | None] | None],
) -> dict[str, pd.DataFrame]:
    """Filter detached JSON records. Missing fields are Unknown, not inferred.

    Engine filters leave explicitly LLM-only rows alone; platform/model filters
    leave explicitly SERP-only rows alone. Mixed/unknown rows must match. None
    selection means unrestricted; empty selection excludes applicable rows.
    """
    result = {}
    for kind, frame in frames.items():
        keep = []
        for row in frame.to_dict("records"):
            accepted = True
            for column, chosen in filters.items():
                if column not in FILTER_COLUMNS or chosen is None:
                    continue
                category = str(row.get("source_category", "")).lower()
                llm_only = category == "llm" and _unknown(row.get("search_engine"))
                serp_only = category == "serp" and _unknown(row.get("platform"))
                if (column == "search_engine" and llm_only) or (
                    column in {"platform", "model_name"} and serp_only
                ):
                    continue
                if kind == "evidence" and column == "brand_id":
                    identities = _approved_brand_ids(row)
                    if not (identities.intersection(chosen) or (
                        not identities and None in chosen
                    )):
                        accepted = False
                        break
                    continue
                value = _filter_value(row, column)
                normalized = None if _unknown(value) else str(value)
                if normalized not in chosen:
                    accepted = False
                    break
            keep.append(accepted)
        result[kind] = frame.loc[keep].copy(deep=True)
    return result


def guarded_projection(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Project recorded columns only; generic fallback preserves pending schemas."""
    present = [column for column in columns if column in frame]
    return frame[present].copy() if present else frame.copy()


def _named_code(value: Any, label: str) -> str:
    """Shared helpers supply names; always keep the exact recorded code visible."""
    if _unknown(value):
        return display(value)
    raw = str(value)
    if label.startswith("Unknown language"):
        return f"Unknown language ({raw})"
    if label.startswith("Unknown location"):
        return f"Unknown location ({raw})"
    return label if label.endswith(f"({raw})") else f"{label} ({raw})"


def _locale_formatter(
    frames: Mapping[str, pd.DataFrame], column: str,
) -> Any:
    """Widget labels never replace option values or assume a mixed provider."""
    if column == "language_code":
        return lambda value: _named_code(value, language_label(value))
    if column != "location_code":
        return display
    providers: dict[str, set[str]] = {}
    for frame in frames.values():
        for row in frame.to_dict("records"):
            value = row.get(column)
            if not _unknown(value):
                providers.setdefault(str(value), set()).add(
                    str(row.get("provider") or "").casefold(),
                )
    return lambda value: (
        _named_code(value, location_label(
            value, provider="dataforseo" if providers.get(str(value)) == {
                "dataforseo",
            } else "unknown",
        ))
    )


def _display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Add friendly columns to a detached frame, preserving recorded codes."""
    local = frame.copy(deep=True)
    for prefix in ("", "requested_", "reported_"):
        for code, name in (("language_code", "language_name"),
                           ("location_code", "location_name")):
            if f"{prefix}{code}" in local:
                context = frame.rename(columns={f"{prefix}{code}": code}) if (
                    prefix
                ) else frame
                if prefix and code in frame:
                    context = frame.drop(columns=[code]).rename(
                        columns={f"{prefix}{code}": code},
                    )
                formatter = _locale_formatter({"display": context}, code)
                local[f"{prefix}{name}"] = local[f"{prefix}{code}"].map(formatter)
    return local


def _table(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No frozen records match this view/filter. Not observed ≠ zero.")
        return
    # TextColumn disables URL/HTML auto-rendering; nested fields stay plain JSON.
    text = _display_frame(frame).map(display)
    st.dataframe(
        text, hide_index=True, width="stretch",
        column_config={column: st.column_config.TextColumn(column)
                       for column in text.columns},
    )


def _overview(snapshot: PlatformSnapshot, frames: dict[str, pd.DataFrame]) -> None:
    st.subheader("Data readiness / 資料就緒度")
    st.caption("Record counts below describe frozen documents, not observations.")
    for column, kind in zip(st.columns(3), ("coverage", "metrics", "evidence"),
                            strict=True):
        column.metric(f"{kind.title()} records", len(frames[kind]))
    coverage, manifest, registries = st.tabs([
        "Coverage & availability", "Publication manifest", "Frozen registries",
    ])
    with coverage:
        st.caption("Publication completion is not a claim of complete source coverage.")
        _table(frames["coverage"])
    with manifest:
        release = snapshot.release or {}
        st.text(display(release.get("manifest_json")))
    with registries:
        _table(frames["registries"])


def _markets(frames: dict[str, pd.DataFrame]) -> None:
    st.subheader("Need × Market · observed intent/locale map")
    st.warning(
        "‘Need’ means recorded query/prompt intent only, NOT measured demand. "
        "Different instrument, feature, window and sample mixes are not controlled "
        "market effects. Provider location codes are not inferred countries. "
        "需求標籤僅指查詢／提示意圖，不代表市場需求。"
    )
    metrics = frames["metrics"]
    grid, raw = st.tabs(["Observation map", "Full metric records"])
    with grid:
        # Never average incompatible metric grains or fill empty matrix cells.
        scope = [key for key in (
            "brand_id", "brand", "source_category", "provider", "search_engine",
            "platform", "model_name", "feature", "collection_window",
            "metric_version",
        ) if key in metrics]
        local = metrics
        if scope and not metrics.empty:
            labels = metrics[scope].apply(
                lambda row: " | ".join(f"{key}={display(row[key])}" for key in scope),
                axis=1,
            )
            chosen = st.selectbox("Exact instrument / feature / window slice",
                                  sorted(labels.unique()))
            local = metrics.loc[labels.eq(chosen)]
        axes = [key for key in ("intent_id", "query_id", "prompt_id") if key in local]
        locales = [key for key in ("language_code", "location_code") if key in local]
        if axes and locales and "presence_rate" in local and not local.empty:
            mapped = pd.DataFrame({
                "Intent": local[axes].apply(
                    lambda row: " | ".join(f"{k}={display(row[k])}" for k in axes),
                    axis=1,
                ),
                "Locale": local[locales].apply(
                    lambda row: " | ".join(
                        f"{k}={_locale_formatter(frames, k)(row[k])}"
                        for k in locales
                    ),
                    axis=1,
                ),
                "Recorded presence rate": local["presence_rate"],
            })
            if not mapped.duplicated(["Intent", "Locale"]).any():
                _table(mapped.pivot(index="Intent", columns="Locale",
                                    values="Recorded presence rate").reset_index())
            else:
                st.info(
                    "Multiple metric grains per cell: shown separately, not averaged."
                )
        _table(guarded_projection(local, [
            "document_id", "intent_id", "query_id", "prompt_id", "language_code",
            "location_code", "provider", "feature", "numerator", "denominator",
            "presence_rate", "coverage_status", "availability_status",
        ]))
    with raw:
        _table(metrics)


def _competition(frames: dict[str, pd.DataFrame]) -> None:
    st.subheader("Brand competition · separate measurement grains")
    st.caption(
        "Published rates only; no pooled SERP/LLM rate, pair-expanded counts or "
        "implicit Top10/answer-only claims. Counts and rates are different measures."
    )
    metrics = frames["metrics"]
    features = filter_options({"metrics": metrics}, "feature")
    if features:
        feature = st.selectbox("Recorded feature", features, format_func=display)
        mask = metrics["feature"].map(
            lambda value: (None if _unknown(value) else str(value)) == feature,
        ) if "feature" in metrics else pd.Series(True, index=metrics.index)
        metrics = metrics.loc[mask]
    instruments, rates, counts, pairs, full = st.tabs([
        "Instruments", "Rates & availability", "Numerators / denominators",
        "Published comparisons", "All fields",
    ])
    context = ["document_id", "brand_id", "brand", "source_category", "feature",
               "provider", "search_engine", "platform", "model_name",
               "language_code", "location_code", "collection_window", "intent_id",
               "query_id", "prompt_id", "metric_version"]
    with instruments:
        _table(guarded_projection(metrics, context))
    with rates:
        _table(guarded_projection(metrics, [*context, "presence_rate",
               "coverage_status", "availability_status"]))
    with counts:
        _table(guarded_projection(metrics, [*context, "numerator", "denominator",
               "mention_count", "citation_count", "observation_count"]))
    with pairs:
        st.caption(
            "Textual comparisons report 100 × (GEO answer presence rate − SERP "
            "visible organic title/description presence rate), in percentage "
            "points, only for supported, fully complete matched slices. Separate "
            "owned-organic versus answer-presence comparisons report patterns "
            "and separate rates, not a numeric textual gap. Neither measures "
            "demand or causal effects. Unknown gaps remain unknown."
        )
        _table(frames["comparisons"])
    with full:
        _table(metrics)


def _record_details(value: Any, path: str = "", provider: str = "unknown") -> None:
    """Drill nested frozen evidence using plain text and validated links only."""
    child: Any
    if isinstance(value, Mapping):
        provider = str(value.get("provider") or provider).casefold()
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key).lower().endswith("language_code"):
                label = _named_code(child, language_label(child))
                st.text(f"{child_path}: {label}")
            elif str(key).lower().endswith("location_code"):
                label = _named_code(child, location_label(child, provider=provider))
                st.text(f"{child_path}: {label}")
            elif str(key).lower() in {
                "url", "citation_url", "source_url", "lineage_url",
            }:
                st.text(f"{child_path}: {display(child)}")
                url = safe_url(child)
                if url:
                    # Labels are static; no payload is interpreted as Markdown.
                    st.link_button("Open recorded evidence URL", url)
                elif not _unknown(child):
                    st.caption(
                        "Link withheld: only credential-free HTTP(S) is allowed."
                    )
            else:
                _record_details(child, child_path, provider)
    elif isinstance(value, (list, tuple)) and value:
        for index, child in enumerate(value):
            _record_details(child, f"{path}[{index}]", provider)
    else:
        st.text(f"{path}: {display(value)}")


def _observed_brand_count(record: Mapping[str, Any], prefix: str) -> Any:
    count = record.get(f"{prefix}_brand_count")
    blocked = (
        record.get("approved_registry_available") is False
        or record.get("brand_coverage_status") == "no_approved_registry"
        or record.get("mention_count_status") == "observed_only_no_reviewed_registry"
    )
    return None if blocked and prefix != "candidate" and count == 0 else count


def _evidence(frames: dict[str, pd.DataFrame]) -> None:
    st.subheader("Evidence & citation lineage")
    st.caption("Plain text only. URLs are external evidence, not raw execution links.")
    evidence = frames["evidence"]
    # The shared helper receives fresh JSON, not objects owned by caller frames.
    records = [enrich_evidence_detail(json.loads(_serialize(row)))
               for row in evidence.to_dict("records")]
    st.subheader("Results brand summary")
    summary_columns = [
        "result_id", "document_id", "source_category", "provider",
        "language_code", "location_code", "collection_status", "coverage_status",
        "brand_coverage_status", "extraction_status",
        "mention_count_status", "brand_count_scope",
        "approved_mentioned_brand_count", "approved_mentioned_brand_names",
        "approved_cited_brand_count", "approved_cited_brand_names",
        "approved_evidenced_brand_count", "approved_evidenced_brand_names",
        "candidate_brand_count", "candidate_brand_names",
    ]
    summary = pd.DataFrame(records, dtype=object)
    for prefix in ("approved_mentioned", "approved_cited", "approved_evidenced"):
        summary[f"{prefix}_brand_count"] = pd.Series(
            [_observed_brand_count(row, prefix) for row in records], dtype=object,
        )
    _table(guarded_projection(summary, summary_columns))
    if evidence.empty:
        return
    index = st.selectbox(
        "Evidence record", range(len(evidence)),
        format_func=lambda i: (
            f"{i + 1} · {display(evidence.iloc[i].get('document_id'))}"
        ),
    )
    record = records[index]
    st.subheader("Selected result · distinct brand overview")
    st.caption(
        "Distinct extracted identities, not mention frequency. Zero observed is "
        "not proof of absence. Incomplete extraction or blocked/missing approved "
        "registries cannot establish that no brand is present. Candidates are "
        "unapproved and excluded from approved counts and brand filters."
    )
    for column, prefix, label in zip(st.columns(3), (
        "approved_mentioned", "approved_cited", "candidate",
    ), ("Approved text-mentioned brands", "Approved cited brands",
        "Candidate brands (unapproved)"), strict=True):
        column.metric(label, display(_observed_brand_count(record, prefix)))
        column.text(display(record.get(f"{prefix}_brand_names")))
    st.text(
        "Approved evidenced brands (distinct union): "
        f"{display(_observed_brand_count(record, 'approved_evidenced'))} · "
        f"{display(record.get('approved_evidenced_brand_names'))}"
    )
    for key in ("collection_status", "coverage_status", "brand_coverage_status",
                "extraction_status", "mention_count_status", "brand_count_scope",
                "limitations"):
        if key in record:
            st.text(f"{key}: {display(record[key])}")
    st.subheader("Brand match details · approved vs candidate")
    details = record.get("matched_brand_details")
    _table(pd.DataFrame(details if isinstance(details, list) else [], dtype=object))
    with st.expander("Raw frozen evidence & lineage", expanded=False):
        _record_details(record)  # Safe links, excerpts and recorded match spans.


def _opportunities(frames: dict[str, pd.DataFrame]) -> None:
    st.subheader("Opportunity queue · hypotheses, not recommendations to execute")
    st.warning(
        "Demand evidence is missing unless explicitly frozen in the document. "
        "Visibility gaps alone do not establish commercial opportunity. No magic "
        "score, ROI estimate or automatic action. 機會為假設，須另行驗證需求。"
    )
    st.caption(
        "Review statuses, owners and rationale are read-only publication-time "
        "values, if recorded. Durable backend reviews appear only in the next "
        "release; old snapshots remain unchanged. No approve/reject, collection "
        "or publication actions."
    )
    cards = frames["opportunities"]
    if cards.empty:
        _table(cards)
        return
    for index, card in enumerate(cards.to_dict("records"), start=1):
        with st.expander(f"Frozen hypothesis {index}", expanded=True):
            for key in ("opportunity_id", "document_id", "brand_id", "pattern",
                        "classification", "human_review_required", "review_status",
                        "owner", "notes", "reviewed_at", "is_synthetic"):
                st.text(f"{key}: {display(card.get(key))}")
            comparison = card.get("comparison")
            comparison = comparison if isinstance(comparison, Mapping) else {}
            st.caption("Supporting frozen rates and response counts (not demand)")
            for channel in ("serp", "llm"):
                metric = comparison.get(channel)
                metric = metric if isinstance(metric, Mapping) else {}
                for key in ("feature", "presence_rate", "numerator", "denominator",
                            "availability_status", "complete_run_count"):
                    st.text(f"{channel}.{key}: {display(metric.get(key))}")
            st.caption("Caveats / hypothesis boundaries")
            _record_details(card.get("limitations"), "limitations")
            _record_details(comparison.get("limitations"), "comparison.limitations")
            _record_details(card.get("evidence_result_ids"), "evidence_result_ids")
    with st.expander("Full frozen opportunity records", expanded=False):
        _table(cards)


def main() -> None:
    st.set_page_config(page_title="Presence Atlas · V1 Platform", page_icon="◈",
                       layout="wide")
    st.markdown(
        """<style>
        .stApp {background:#f8fafc;}
        [data-testid="stSidebar"] {background:#eef2ff;}
        [data-testid="stMetric"] {background:white;border:1px solid #dbeafe;
          border-radius:16px;padding:18px;}
        h1,h2,h3 {color:#1e3a8a;}
        </style>""", unsafe_allow_html=True,  # Static styles, never document content.
    )
    st.title("◈ Presence Atlas")
    st.caption("V1 · Completed release research / 已完成快照研究 · Read only")
    st.sidebar.title("V1 research workspace")
    database = Path(st.sidebar.text_input(
        "Existing DuckDB warehouse",
        value=os.environ.get("GEO_DASHBOARD_DB", str(
            PROJECT_ROOT / "data/warehouse/geo_research.duckdb",
        )), key="platform_database",
    ))
    initial = load_platform_snapshot(database)
    release_ids = initial.releases.release_id.tolist()
    chosen = st.sidebar.selectbox(
        "Completed platform release", [None, *release_ids],
        format_func=lambda value: "Current pointer" if value is None else str(value),
        key="platform_release",
    )
    snapshot = initial if chosen is None else load_platform_snapshot(database, chosen)
    view = st.sidebar.radio("Research view", VIEWS, key="platform_view")
    st.sidebar.caption("No writes · No paid APIs · No unpublished fallback")
    st.info(LIMITATIONS)
    if snapshot.message:
        st.warning(snapshot.message)
        st.info(EMPTY_INSTRUCTIONS)
        return
    release = snapshot.release or {}
    st.text(
        f"Frozen release: {display(release.get('release_id'))} · "
        f"Created: {display(release.get('created_at'))} · "
        f"Metric version: {display(release.get('metric_version'))}"
    )
    frames = snapshot.frames
    filters = {}
    with st.sidebar.expander("Observation filters", expanded=False):
        for column in FILTER_COLUMNS:
            options = filter_options(frames, column)
            if not options or options == [None]:
                continue
            selected = st.multiselect(column, options, default=options,
                                      format_func=_locale_formatter(frames, column),
                                      key=f"platform_{column}")
            filters[column] = None if len(selected) == len(options) else selected
        st.caption(
            "Missing fields are Unknown; filters may exclude coverage/registry "
            "records without those fields. Query/prompt fallback IDs are typed, "
            "not semantic mappings. Engine/platform filters are channel-local "
            "only for explicitly labelled SERP/LLM records."
        )
    frames = filter_frames(frames, filters)
    if view == VIEWS[0]:
        _overview(snapshot, frames)
    elif view == VIEWS[1]:
        _markets(frames)
    elif view == VIEWS[2]:
        _competition(frames)
    elif view == VIEWS[3]:
        _evidence(frames)
    else:
        _opportunities(frames)