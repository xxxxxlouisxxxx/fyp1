# V1 tiny-date raw audit — actual execution

Executed 2026-10-06 using the project's .venv-monthly Python 3.12.12. Scope: raw folder date **2026-09-25**, not provider result date. Overall outcome: **partial real-raw validation; not production acceptance**. Earlier canceled audit attempts remain pending/unverified and are not counted as successful runs.

## Provenance boundary and cost inspection

- Inspected the existing [pipeline snapshot and dynamic runner](../src/geo_research/platform/pipeline.py) and [offline transform script](../scripts/transform_all_raw.py).
- `_snapshot` content-hashes selected raw files, registry CSVs, allowlisted code and the canonical warehouse; other raw/input/warehouse files receive size/mtime metadata guards only. Pipeline audit/run repeats snapshots; reconstruction also copies declared provenance into its private project.
- Metadata-only inspection found the canonical warehouse at **68,956,160 bytes**; the largest listed derived warehouse was **613,167,104 bytes**. This inspection does not establish why earlier attempts exceeded 200 seconds.
- This run did **not** invoke `_snapshot`, `audit_project` or `run_pipeline`. No canonical warehouse content hash, database connection or database copy was performed. The canonical provenance implementation remains unchanged.
- No new CLI flag/API parameter or source-code change was needed. Safe execution uses an isolated project containing no source database; the original dynamic `_runner(root)` loaded the existing implementation for the pure audit, and the original script received the isolated root for reconstruction. No script shim was created.
- `authoritative_context: unavailable` is explicitly recorded in the audit/verification artifacts. This is not equivalent to provenance-verified production acceptance.

## Pure audit and exact isolation

The original `runner.audit_raw(raw_root, date(2026, 9, 25))` was called directly. SHA-256 was computed for all ten selected source files before and after this call and compared against the audit hashes. Audit, copy, inventory and dbt-code preparation together took **37.938 seconds**; this is not a pure audit-only timing.

The new [run directory](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/direct_audit.json) contains a standalone working project with **exactly 10 byte-identical selected raw files plus 13 byte-identical registry CSVs**. No source warehouse, profiles, secrets, input tables or synthetic fixtures were copied. A separate dbt project contains copied SQL/YAML models, macros and dbt tests only.

| Audit finding | Actual result |
| --- | ---: |
| Selected files | 10 |
| Metadata / request / response / auxiliary | 3 / 3 / 3 / 1 |
| Valid canonical triples | 3 |
| Integrity-invalid responses | 0 |
| Invalid JSON files | 1 auxiliary |

The auxiliary response.pretty.json contains a UTF-8 BOM and is rejected by the existing strict JSON decoder. It remains `quarantined_auxiliary`, not a fourth response and not silently rewritten. All three canonical triples passed their manifest checksum/size checks. Full relative paths and SHA-256 values are in the direct audit artifact.

## Actual reconstruction

The original offline script ran with the isolated project and `raw_date=2026-09-25`, completing in **5.750 seconds**. No pipeline failure or source-code fix occurred.

| Request | Engine | Actual outcome |
| --- | --- | --- |
| 613914e9-cebd-498c-b519-2c16090f107a | Google | `provider_error`, code 40601, message “Task Handed.”; 0 parsed items |
| 93a9e1c1-c504-47df-a89c-7299d826da19 | Google | `available`, code 20000; 12 parsed items, 4 parser quarantine events |
| e160fc4d-a4eb-47cd-8bb0-8212a6a0d9d9 | ChatGPT | `available`, code 20000; 17 parsed items |

- Bronze requests/responses: **3 / 3**; Silver search/LLM observations: **2 / 1**; response-evidence observations: **3**.
- Transformation-quarantined responses: **0**; unsupported responses: **0**; parser quarantine events: **4**. Three transformed responses does not mean three successful provider answers.
- `raw_unchanged`, `all_files_accounted`, and `response_reconciliation`: **true**.
- `provenance_sources`: **empty**; reconciled context, authoritative query mappings and authoritative windows: **0**.
- Selected metadata contains request IDs but no query_id, search_target_id, collection_window, request_hash or deduplication_key. Those four Bronze identity/hash columns remain null; windows use explicitly labeled `raw-request:<request_id>` isolation. The Silver SERP non-null raw-request key is not an approved query mapping. CSV query/prompt registries do not authorize inferred raw-request associations.
- Approved brands, aliases, domains and active comparisons: **0**. Placeholder rows were excluded, not approved or replaced.

## Actual dbt verification

A [new credential-free profile](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/dbt_profile/profiles.yml) targets only the newly reconstructed database, schema analytics, one thread. Production profiles were neither read nor edited. `bootstrap_sanitized_fixture: false` was passed explicitly; the macro's guard was inspected.

The terminal invocation returned only dbt startup output without a conclusive result. Verification therefore used `dbtRunner().invoke` with the exact configured interpreter and the same isolated paths/options. Its recorded outcome is authoritative for this report; the terminal attempt is not claimed as successful.

- dbt **1.12.5**, duckdb adapter **1.11.0**.
- Invocation success: **true**, exception: **null**, elapsed **29.266 seconds**; recorded dbt execution **18.918 seconds**.
- **44 successful model/hook nodes and 382 passing tests**, no failed/error/skipped nodes. These are dbt results, not pytest results or a full production-data validation.
- All six Gold views and all three presentation metric views: **0 rows**. Empty views are expected with absent approved brands/comparisons and do not prove business metric completeness.
- New database size after build/export: **19,935,232 bytes**.
- Sanitized fixture request count: **0**; published releases: **0**.
- Existing `finalize_dbt_export` completed only after successful run_results verification, exporting the new analytics views. Summary reports `built_empty_no_approved_brands`, `dbt_run: true`, `publication: false`.

## Safety checks and remaining blockers

Final checks after reconstruction/dbt confirmed SHA-256 equality for all ten selected original raw files and their isolated copies, and all thirteen original registry CSVs and their isolated copies. No API calls, approvals or publication occurred. No canonical database content immutability claim is made: its contents were deliberately not hashed or read. Unselected input content was not audited or checksum-verified.

Production acceptance remains blocked by **unavailable authoritative raw-request context**, **no approved brand/domain registry**, **no active approved comparisons**, the preserved provider error, auxiliary quarantine and parser quarantine events. dbt's passing tests do not waive these limitations. No synthetic production claim is made.

## Evidence artifacts

- [Direct audit, per-file SHA-256 and source guards](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/direct_audit.json)
- [Verification, context limitations and Gold row counts](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/verification.json)
- [Conclusive dbt invocation](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/dbt_invocation.json)
- [dbt node/test results](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/dbt_project/target/run_results.json)
- [Finalized isolated reconstruction summary](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/working_project/data/exports/raw_date_20260925_20261006T110831_694037Z/summary.json)
- [Per-request outcomes and context](../data/exports/platform_v1_tiny_20260925_20261006T110817_672791Z/working_project/data/exports/raw_date_20260925_20261006T110831_694037Z/request_statuses.json)