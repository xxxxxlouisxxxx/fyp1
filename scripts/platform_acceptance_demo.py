"""Offline synthetic V1 contract exercise; imports require an installed package.

Never seed production registries, read production raw, or patch published documents.
Missing publisher/reviewer integration is reported as blocked, not simulated away.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

from geo_research.platform.analytics import publish_v1
from geo_research.platform.pipeline import review_opportunity
from geo_research.storage.duckdb import DuckDBStore
from geo_research.transforms.feature_evidence import enrich_features, persist_features
from geo_research.transforms.response_evidence import load_brand_registry

FIRST_RELEASE = "synthetic-v1-acceptance"
SECOND_RELEASE = "synthetic-v1-reviewed"
DATABASE_NAME = "synthetic_platform.duckdb"
STAMP = "2026-10-06T00:00:00+00:00"
DISCLAIMER = (
    "is_synthetic=true: invented offline fixture, not production approval, "
    "a real analyst decision, demand, score, recommendation, traffic or ROI."
)


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"


def _destination(project: Path, output: Path) -> tuple[Path, Path]:
    project = project.resolve()
    if not (project / "pyproject.toml").is_file():
        raise ValueError("project must contain pyproject.toml")
    output = (output if output.is_absolute() else project / output).resolve()
    exports = (project / "data" / "exports").resolve()
    # Resolve junctions/symlinks before enforcing the private export boundary.
    for protected in (project / "data" / "raw", project / "data" / "warehouse",
                      project / "config"):
        if output == protected.resolve() or protected.resolve() in output.parents:
            raise ValueError("protected raw/warehouse/config output path")
    if exports not in output.parents:
        raise ValueError("output must be a NEW directory under project data/exports")
    if output.exists() or output.is_symlink():
        raise ValueError(
            "output already exists; refusing overwrite or existing database"
        )
    if output.suffix.casefold() == ".duckdb":
        raise ValueError("--output requires a directory, not a database")
    return project, output


def _seed(database: Path) -> None:
    DuckDBStore(database).initialize()
    with duckdb.connect(str(database)) as con:
        con.execute("""
            CREATE TABLE bronze.brand_registry (
                brand_id VARCHAR PRIMARY KEY, canonical_name VARCHAR,
                ownership_type VARCHAR, active BOOLEAN,
                effective_start_date DATE, effective_end_date DATE,
                review_status VARCHAR, provenance VARCHAR, is_synthetic BOOLEAN
            );
            CREATE TABLE bronze.brand_alias_registry (
                brand_id VARCHAR, alias_text VARCHAR, is_synthetic BOOLEAN
            );
            CREATE TABLE bronze.brand_domain_registry (
                brand_id VARCHAR, domain VARCHAR, provenance VARCHAR,
                is_synthetic BOOLEAN
            );
            CREATE TABLE bronze.synthetic_fixture_registry (
                fixture_id VARCHAR, is_synthetic BOOLEAN, disclaimer VARCHAR,
                provenance VARCHAR
            );
            INSERT INTO bronze.brand_registry VALUES
                ('synthetic-atlas', 'Atlas', 'owned', true, '2026-01-01', NULL,
                 'approved', 'invented fixture identity; not real approval', true);
            INSERT INTO bronze.brand_alias_registry VALUES
                ('synthetic-atlas', 'Atlas Works', true);
            INSERT INTO bronze.brand_domain_registry VALUES
                ('synthetic-atlas', 'atlas.invalid', 'invented fixture domain', true);
            ALTER TABLE bronze.comparison_registry ADD COLUMN is_synthetic BOOLEAN;
            ALTER TABLE bronze.comparison_registry ADD COLUMN review_status VARCHAR;
            ALTER TABLE bronze.comparison_registry ADD COLUMN provenance VARCHAR;
            -- Analytics consumes request metadata, not the fixture registry.
            -- This additive column exists only in this new private fixture DB.
            ALTER TABLE bronze.api_requests ADD COLUMN metadata_json VARCHAR;
            INSERT INTO bronze.comparison_registry VALUES
                ('synthetic-map', 'synthetic-query', 'synthetic-prompt', true,
                 '2026-10-06', true, 'approved', 'fixture-only explicit mapping');
            INSERT INTO bronze.query_registry VALUES
                ('synthetic-query', 'synthetic industrial supplies', true,
                 '2026-10-06');
            INSERT INTO bronze.llm_prompt_registry VALUES
                ('synthetic-prompt', 'synthetic industrial supplies', true,
                 '2026-10-06');
            INSERT INTO bronze.search_target_registry VALUES
                ('synthetic-serp-target', 'synthetic', 'google', 'organic', NULL,
                 true, '2026-10-06');
            INSERT INTO bronze.llm_target_registry VALUES
                ('synthetic-llm-target', 'synthetic', 'gemini', 'synthetic-model',
                 true, '2026-10-06');
        """)
        con.execute("INSERT INTO bronze.synthetic_fixture_registry VALUES (?, ?, ?, ?)",
                    ["synthetic-v1", True, DISCLAIMER,
                     "six generated payloads; no external raw input"])
        registry = load_brand_registry(con)
        for index in range(3):
            for category in ("serp", "llm"):
                identity = f"synthetic-{category}-{index}"
                sources = [{"url": f"https://atlas.invalid/source-{number}",
                            "snippet": "citation context only"}
                           for number in range(index)]
                items: list[dict[str, Any]] = [{
                    "type": "gemini_text", "original_text": (
                    "Atlas Atlas Works", "Atlas Works", "Unbranded supplies"
                )[index], "sources": sources}]
                if category == "serp":
                    # All complete organic slots are unowned; title mentions vary
                    # and must not be counted as owned-organic presence.
                    items = [{"type": "organic", "rank_group": rank,
                              "rank_absolute": rank,
                              "url": f"https://other.invalid/{index}/{rank}",
                              "title": "Atlas listing" if index == 0 else "Supplies"}
                             for rank in range(1, 4)]
                payload = {"tasks": [{"status_code": 20000, "data": {
                    "keyword": "synthetic industrial supplies",
                    "language_code": "en", "location_code": "2344",
                    "device": "desktop", "os": "windows", "depth": 3,
                }, "result": [{"items": items, "sources": []}]}]}
                encoded = _dump(payload).encode("utf-8")
                digest = hashlib.sha256(encoded).hexdigest()
                context = {
                    "observation_id": identity, "request_id": f"req-{identity}",
                    "response_id": f"resp-{identity}", "raw_file_hash": digest,
                    "source_category": category, "collection_status": "available",
                    "collected_at": STAMP, "provider": "synthetic",
                    "engine_or_platform": "google" if category == "serp" else "gemini",
                    "model_name": None if category == "serp" else "synthetic-model",
                }
                con.execute("""
                    INSERT INTO bronze.api_requests
                        (request_id, run_id, source_category, provider, platform,
                         search_engine, model_name, request_status, created_at,
                        query_id, search_target_id, collection_window, metadata_json)
                    VALUES (?, ?, ?, 'synthetic', ?, ?, ?, 'completed', ?, ?, ?, ?, ?)
                """, [context["request_id"], f"run-{identity}", category,
                      "gemini" if category == "llm" else None,
                      "google" if category == "serp" else None,
                      context["model_name"], STAMP,
                      f"synthetic-{'query' if category == 'serp' else 'prompt'}",
                      f"synthetic-{category}-target", "synthetic-2026-10",
                      _dump({"is_synthetic": True, "synthetic_provenance": {
                          "fixture_id": identity, "request_id": context["request_id"],
                          "raw_file_hash": digest, "disclaimer": DISCLAIMER,
                          "origin": "generated offline; no external raw input",
                      }})])
                persist_features(con, enrich_features(context, payload, registry))
                # Generated payloads are stored as explicitly marked fixture
                # metadata, NOT as pretend production raw-file registrations.
                con.execute(
                    "INSERT INTO bronze.synthetic_fixture_registry VALUES (?, ?, ?, ?)",
                    [identity, True, DISCLAIMER, _dump({
                        "sha256": digest, "context": context, "payload": payload,
                        "independent_fixture_run": f"run-{identity}",
                    })],
                )


def _documents(database: Path, release: str) -> list[tuple[str, str, str]]:
    with duckdb.connect(str(database), read_only=True) as con:
        return con.execute(
            "SELECT kind, document_id, payload_json "
            "FROM presentation.platform_documents "
            "WHERE release_id=? ORDER BY kind, document_id", [release],
        ).fetchall()


def _assert_synthetic_documents(documents: list[tuple[str, str, str]]) -> None:
    """Validate publisher output; never repair or relabel frozen payloads."""
    required = {"metrics", "evidence", "comparisons", "opportunities"}
    seen = set()
    for kind, document_id, payload in documents:
        if kind not in required:
            continue
        seen.add(kind)
        row = json.loads(payload)
        if row.get("is_synthetic") is not True or not row.get("source_provenance"):
            raise ValueError(f"missing explicit synthetic trace: {kind}/{document_id}")
        if row.get("synthetic_metadata_conflict"):
            raise ValueError(f"conflicting synthetic trace: {kind}/{document_id}")
    if seen != required:
        raise ValueError(
            "missing synthetic document kinds: " + ", ".join(sorted(required - seen))
        )


def run_demo(project: Path, output: Path) -> dict[str, Any]:
    """Create a private fixture and two releases; truthfully report review gates.

    Returned report includes absolute paths, publisher manifests, review result,
    frozen-status checks and production health. No existing output is reusable.
    """
    project, output = _destination(Path(project), Path(output))
    output.mkdir(parents=True, exist_ok=False)
    database = output / DATABASE_NAME
    report: dict[str, Any] = {
        "is_synthetic": True, "disclaimer": DISCLAIMER, "project": str(project),
        "paths": {"output": str(output), "database": str(database),
                  "report": str(output / "acceptance_report.json")},
        "health": "blocked-on-production-registries",
        "production_blockers": ["no approved production brands",
                                "no approved category rules",
                                "no approved production query-prompt mappings"],
        "production_health_assessed": False,
        "validation": "execution report only; not full test-suite acceptance",
        "blockers": [], "fixture_observations": {"serp": 3, "llm": 3},
    }
    (output / "README.md").write_text(
        "# Synthetic V1 acceptance output\n\n" + DISCLAIMER + "\n\n"
        "Do not merge this warehouse or its approvals into production.\n"
        "Consult acceptance_report.json for actual review/freeze gates.\n",
        encoding="utf-8",
    )
    try:
        _seed(database)
        report["first_release"] = publish_v1(database, FIRST_RELEASE, minimum_runs=3)
        before = _documents(database, FIRST_RELEASE)
        _assert_synthetic_documents(before)
        cards = [json.loads(payload) for kind, _, payload in before
                 if kind == "opportunities"]
        if not cards:
            raise ValueError("synthetic fixture produced no opportunity")
        card = cards[0]
        opportunity_id = card.get("opportunity_id") or card["document_id"]
        report["opportunity_id"] = opportunity_id
        try:
            report["review"] = review_opportunity(
                database, opportunity_id, status="under_review",
                owner="synthetic-fixture-reviewer",
                notes="is_synthetic=true; scripted fixture decision, not a real review",
            )
        except ValueError as exc:
            report["blockers"].append("review interface: " + str(exc))
        report["second_release"] = publish_v1(database, SECOND_RELEASE, minimum_runs=3)
        second_documents = _documents(database, SECOND_RELEASE)
        _assert_synthetic_documents(second_documents)
        second_cards = [json.loads(payload) for kind, _, payload in
                second_documents if kind == "opportunities"]
        reviewed: dict[str, Any] = next((row for row in second_cards
                         if (row.get("opportunity_id") or row["document_id"])
                         == opportunity_id), {})
        report["checks"] = {
            "published_synthetic_provenance_complete": True,
            "first_release_unchanged": before == _documents(database, FIRST_RELEASE),
            "first_review_status": card.get("review_status"),
            "second_review_status": reviewed.get("review_status"),
            "review_status_frozen_in_new_release": (
                reviewed.get("review_status") == "under_review"
                and card.get("review_status") == "unreviewed"
                and "review" in report
            ),
        }
        if not report["checks"]["first_release_unchanged"]:
            report["blockers"].append("historical snapshot changed")
        if not report["checks"]["review_status_frozen_in_new_release"]:
            report["blockers"].append(
                "publisher does not freeze the recorded review status"
            )
    except Exception as exc:
        report["blockers"].append(f"{type(exc).__name__}: {exc}")
    report["status"] = "blocked" if report["blockers"] else "synthetic-contract-passed"
    (output / "acceptance_report.json").write_text(_dump(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path, required=True,
                        help="NEW directory under project data/exports")
    args = parser.parse_args(argv)
    try:
        report = run_demo(args.project, args.output)
    except (ValueError, OSError) as exc:
        print(_dump({"status": "blocked", "is_synthetic": True, "error": str(exc)}))
        return 2
    print(_dump(report))
    return 0 if report["status"] == "synthetic-contract-passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())