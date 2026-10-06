# V1 platform acceptance — synthetic verification, not production sign-off

Updated 2026-10-06 after latest runner, provenance and dashboard fixes.
**Production V1 acceptance blocked; human owner sign-off not recorded.**
Replaces earlier pending/105-test statements with observed results, without
upgrading invented approvals to production approval.

## Current evidence and results

See [final verification](platform_v1_verification.md),
[final_v2 report](../data/exports/v1_acceptance_final_v2/acceptance_report.json),
[actual tiny-date audit](platform_v1_audit_report.md) and
[scoped quality/legacy baseline](platform_quality_verification_20261006.md).

| Verification | Current result | Boundary |
| --- | --- | --- |
| Exact monthly Python pytest, `-o addopts= -q` | **339 passed / 94.04 seconds / exit 0** | Runner and two scanner regressions included; no new coverage percentage |
| Scoped Ruff | Exit 0, all checks passed | Sources/scripts/tests listed in final verification |
| Strict scoped mypy, silent imports | Exit 0, **9 direct source files** | Not whole-project typing; imported legacy 42-error baseline unresolved |
| Source secret scanner | **Exit 1, two candidate files** | Path-only output; safe human disposition required |
| Final_v2 contract | Passed, two completed releases | Invented Atlas/Atlas Works/atlas.invalid, not production health assessment |
| Frozen provenance | 6 evidence, 1 opportunity, 11 metrics, 2 comparisons explicitly synthetic with provenance | New edition only, old snapshots unchanged |
| Review/history | First unreviewed, next under_review; report freeze/unchanged checks true | Scripted fixture decision, not real analyst review |
| Live UI | Five views, evidence and expanded opportunity card verified without visible exceptions | Not exhaustive UI or production coverage |
| Read-only snapshot | Synthetic DB byte hash unchanged across current load | No canonical warehouse baseline claim |
| Server | Health 200 `ok`, current page final_v2 | No restart/task launch verification |
| Real dbt | Earlier isolated 44 successful nodes + 382 passing tests | Tiny-date only, empty Gold/presentation, no publication; not rerun |

Fixture: **3 SERP + 3 LLM**. Each release: coverage 9, metrics 11 (7 available),
comparisons 2 (2 matched), evidence 6, opportunities 1, registry documents 9.
Minimum fixture runs 3; distinct synthetic IDs do not prove real independence.
Version platform-v1.1.0-feature-v2-textual. Published synthetic provenance complete
and first-release unchanged checks true. Status synthetic-contract-passed,
production health assessed false, health blocked-on-production-registries.

## Open the final edition

Open **http://localhost:8501/**, choose **Workspace → V1 Platform** (fresh sessions
default Legacy), set **Existing DuckDB warehouse** to:

D:/FYP (2)/FYP (2)/FYP/FYP/FYP/FYP/FYP/FYP/data/exports/v1_acceptance_final_v2/synthetic_platform.duckdb

Press Enter; use **Current pointer**, confirm **synthetic-v1-reviewed**.
Inspect Overview · Data Readiness, Need × Market, Brand Competition, Evidence &
Citation Explorer and Opportunity Queue. Evidence/cards show synthetic labels;
cards include frozen review owner/notes, supporting counts/rates, evidence IDs
and caveats. UI cannot execute, review, collect, repair or publish.

[Task](../.vscode/tasks.json) now defaults to final_v2 on future startup; only
the database segment changed. Running server still has old environment default,
overridden by current explicit sidebar input. No restart performed. Server does
not persist automatically after terminal/editor closure.

## Requirements tracking — implemented versus partial

| Checkpoint / requirement | Implemented and verified | Partial / blocked / unverified |
| --- | --- | --- |
| V0.1 foundation/reconstruction | Package/migrations/registry boundaries, audit/manifests, selected hashes, tiny-date isolated reconciliation | No whole-raw audit; authoritative context and actual approved production registries/mappings absent |
| V0.1 efficient invalidation | Conservative compatibility/reuse, runner dataclass import and cleanup tests | Alias-scoped efficient rebuild absent; normalize/evidence coupled; size/mtime-only outside-scope guard not checksum assurance |
| V0.2 evidence | Feature-v2 extraction, separate answer/owned-citation channels, distinct denominators/runs, hash/JSON-path lineage | All-provider/locale/data coverage and independent-trial validation unverified; unsupported absence unknown |
| V0.2 comparisons | Complete supported textual gap in percentage points; owned-organic pattern kept separate | Matched locale/window not controlled intent equivalence, personalization, demand or causality |
| V1.0 publication/reviews | Atomic completed-only snapshots, six document kinds, current slot/historical selector, next-release review freeze and unchanged old snapshot | Real human approval absent; no rollback/current-pointer CLI mutation command; synthetic publication not production publication |
| V1.0 read-only five-view UI | Five final_v2 live views, recorded provenance, recursive evidence, expanded hypothesis cards | Fresh default Legacy; exhaustive UI/production acceptance pending |
| V1.0 agent | Definition/frontmatter previously parsed | Actual VS Code discovery/invocation unverified |
| V1.0 quality/security/operations | 339 Python tests, scoped lint/direct typing, local server health | Legacy typing, secret candidates, security/cost/recovery/deployment approvals open |
| Business validation | Hypotheses-only, missing-demand/manual-review boundaries | No demand/traffic/conversion/revenue/ROI/recommendation KPI, temporal stability or HHI accepted |

This consolidates the existing version-traceability table rather than inventing
completed requirements. Approved invented fixture rows must never be copied to
production registries or combined with production metrics.

## Reproduction, rollback and operational boundaries

[Demo](../scripts/platform_acceptance_demo.py): mandatory `--output`, optional
`--project` defaulting to project root. Use exact monthly interpreter and package
or PYTHONPATH=src with a **new directory strictly under data/exports**. Existing
outputs/databases and escaped/protected paths refused before initialization.
Never rerun into final_v2 or patch frozen documents. Interrupted outputs retained;
retry with a new directory. Outputs are fixture DB, execution report and disclaimer.

Existing migrations/registry/enrichment/persistence, two `publish_v1` calls and
one scripted `review_opportunity` call are real interfaces, but inputs/identity
and approval remain invented. Request metadata records synthetic flags/provenance;
analytics consumes source records, not UI inference. No production raw, APIs or
dbt bootstrap used. IDs/metrics deterministic, timestamps/UUIDs/DB bytes not.
Exit 0 accepts synthetic contract only, not production health.

Operational audit/run are separate, may read selected real inputs, and do not
automatically publish. No whole-production run here. Evidence-only requires
compatible upstream; stage names do not imply independently optimized rebuilding.
Review appends governance history, affecting next publication only; workflow
states are not evidence of business outcomes.

For consumer historical selection choose **Completed platform release →
synthetic-v1-acceptance** in this DB; not pointer mutation or warehouse rollback.
No rollback/current-pointer command implemented. Never edit snapshots/raw to
manufacture success. Stop incompatible writers before opening a selected DB.
This verification made no production writes, APIs or server restart.

## Genuine remaining gates

1. Human-approved brands/domains/aliases/categories/mappings/comparisons and
   authoritative raw-request context with actual reviewer evidence.
2. All-data/provider/locale and whole-raw content validation. Tiny-date audit is
   partial; provider error, quarantines and unavailable context remain. Metadata
   inventory/canceled audits do not pass whole-data acceptance.
3. Actual agent discovery/invocation, efficient alias-scoped rebuild, legacy
   typing remediation and applicable recovery/operational validation.
4. Safe disposition of source scan candidates in the
   [implementation document](../HKTDC_External_Data_API_Implementation.md) and
   [settings tests](../tests/unit/test_settings.py), no candidate values disclosed
   or automatic allowlisting. Source scan excludes .env/data/logs/dependencies/
   binaries and is not comprehensive security assurance.
5. Human security/cost/recovery/deployment approval and owner sign-off with
   reviewer/date/decision/evidence; real commercial and independent-trial evidence.

**No whole V1 production acceptance is granted by this document.**# V1 platform acceptance — synthetic contract, not production sign-off

## Scope and acceptance status

The offline demo uses **invented Atlas / Atlas Works identity and atlas.invalid
domain**. `is_synthetic=true` is explicit in the report, generated README and
frozen registry metadata. Fixture `approved` rows authorize this isolated test
only: they are **not a real brand/domain/mapping review**. Never copy them to
production registries or combine this warehouse with production metrics.

This document records implemented interfaces and remaining gates, not a claim
that V1 is done or that all tests passed. **The main integrator verified 105 tests
passed.** This is the reported scoped result, not full regression acceptance or
a post-formatting rerun. No terminal commands were executed for this fix task.
Full regression, lint, dbt and browser verification remain **pending**.

The recorded synthetic run is
[acceptance_report.json](../data/exports/v1_acceptance_20261006/acceptance_report.json):
`status='synthetic-contract-passed'`, no synthetic blockers, and both releases
completed. Each release records **6 evidence responses, 10 metrics, 1 matched
comparison and 1 exploratory hypothesis**. The real review interface persisted
the scripted `under_review` decision; the first release remains `unreviewed` and
unchanged, and the next release freezes `under_review`. The earlier identity and
review-freezing integration blockers are resolved for this recorded fixture.
No frozen documents were patched to manufacture success.

These are counts from this report, not a permanently fixed metric contract.
Additional metrics may change the final report; record the final run's actual
counts and evidence before sign-off. Synthetic success grants **no production
approval**; production health was not assessed and production registry gates
remain blocked.

## Reproduce the isolated demo

Use the installed package environment from the existing README setup. From the
project root, run (choose a **new** output directory for each attempt):

```powershell
uv run python scripts/platform_acceptance_demo.py --project 'd:\FYP (2)\FYP (2)\FYP\FYP\FYP\FYP\FYP\FYP' --output data/exports/synthetic_v1_acceptance_20261006
```

CLI: `--output` is mandatory; `--project` defaults to the script's project root.
Relative output paths resolve against `--project`, not the current directory.
Only a new directory strictly beneath that project's data/exports is allowed.
Existing directories/databases, raw, warehouse, configuration, escaped resolved
paths and database-valued outputs are refused before initialization. Re-running
the same output refuses overwrite (exit 2), rather than appending duplicate data.
Do not select an old export/release directory. Interrupted outputs are retained
for inspection; retry with a different directory, not an overwrite switch.

Python interface: `run_demo(project: Path, output: Path) -> dict`; CLI
`main(argv: list[str] | None) -> int`. Imports use the installed `geo_research`
package, with no script-level src path injection. It calls:

- `DuckDBStore(database).initialize()` for existing migrations 001–009;
- `load_brand_registry(connection)`, `enrich_features(context, payload, registry)`
  and `persist_features(connection, evidence)` for real feature extraction;
- `publish_v1(database, 'synthetic-v1-acceptance', minimum_runs=3)`;
- `review_opportunity(database, opportunity_id, status='under_review',
  owner='synthetic-fixture-reviewer', notes=...)` — a scripted synthetic decision;
- `publish_v1(database, 'synthetic-v1-reviewed', minimum_runs=3)`.

There are three SERP and three LLM observations with distinct request, response,
observation and run IDs; fixed collection time, explicit window, query/prompt
identities, provider, engine/platform/model, locale, device/OS and JSON-path/hash
lineage. Invented request/result envelopes are generated in memory. LLM answer
mentions vary across two positive and one negative observation; owned citations
vary across zero, one and two. SERP title mentions do not count as owned organic
slots; all organic slots are unowned, giving an exploratory comparison hypothesis.
Distinct fixture runs are **not evidence of real statistical independence**.

Generated payloads/hash/context remain in the synthetic fixture registry. There
are no pretend production raw-file rows or external raw-file links; no production
raw is read, copied or changed. No dbt bootstrap, collection, API call or old
release mutation occurs. The demo is deterministic in inputs, IDs and extracted
metrics, not byte-identical DuckDB files: migration/publication/review timestamps
and review UUIDs are generated by existing interfaces.

Outputs inside the chosen directory:

- synthetic_platform.duckdb — disposable fixture warehouse, both platform releases;
- acceptance_report.json — absolute paths, manifests/counts/hashes, attempted
  review, first/second frozen statuses, snapshot equality checks and blockers;
- README.md — synthetic provenance and non-production disclaimer.

Exit 0 means only the synthetic contract gates passed. Exit 2 means blocked or
invalid invocation; inspect the report. `health='blocked-on-production-registries'`
always remains separate from synthetic success. Production health is **not audited
by this script**; the report explicitly says `production_health_assessed=false`.
The listed known production blockers are no approved brands, no approved category
rules and no approved query/prompt mappings; independently re-audit before any
production publication. Neither synthetic approval nor a completed synthetic
release removes those blockers.

## Existing operational CLI (separate from the demo)

Use fresh isolated outputs; replace the database and opportunity identifiers with
the actual report values. Audit/run may read production inputs intentionally;
they are **not called by the synthetic demo**. Assess is read-only. Publish/review
write only the explicitly selected database; never point these examples at an
old production warehouse without owner approval.

```powershell
uv run geo-research platform audit --project . --output data/exports/v1_audit_20261006
uv run geo-research platform run --project . --output data/exports/v1_run_20261006 --stage normalize --stage evidence
uv run geo-research platform assess --database data/exports/synthetic_v1_acceptance_20261006/synthetic_platform.duckdb
uv run geo-research platform publish --database data/exports/synthetic_v1_acceptance_20261006/synthetic_platform.duckdb --release-id synthetic-v1-manual --minimum-runs 3
uv run geo-research platform review --database data/exports/synthetic_v1_acceptance_20261006/synthetic_platform.duckdb --opportunity-id '<actual opportunity_id>' --status under_review --owner synthetic-fixture-reviewer --notes 'is_synthetic=true; fixture-only decision'
```

Audit/run accept optional `--raw-date YYYY-MM-DD`; run also accepts repeated
`--stage normalize|evidence` and `--previous-manifest PATH`. Evidence-only requires
a fully compatible prior upstream. Invalidation is conservative: the legacy runner
couples normalization and evidence, and incompatible inputs require a full coupled
rebuild. **Scoped invalidation optimization is not implemented**; stage names do
not imply independently optimized rebuilding. These commands do not automatically
publish. Review appends governance history, does not approve collection/jobs or
perform commercial action. Current accepted states: draft, under_review, approved,
rejected, snoozed, completed; a state is not proof of measured business outcomes.

## Read-only Streamlit and rollback

```powershell
$env:GEO_DASHBOARD_DB = 'd:\FYP (2)\FYP (2)\FYP\FYP\FYP\FYP\FYP\FYP\data\exports\synthetic_v1_acceptance_20261006\synthetic_platform.duckdb'
uv run python -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

The launcher defaults to **Legacy explorer** to preserve the existing workflow.
**V1 Platform is opt-in**: setting `GEO_DASHBOARD_DB` to a demo warehouse does not
automatically switch the workspace or approve the data. Choose **Workspace →
V1 Platform**, verify the warehouse and completed release, then inspect the five
Research views. For the recorded run above, select the disposable warehouse in
data/exports/v1_acceptance_20261006 rather than the example rerun directory.

1. Overview · Data Readiness — frozen coverage, manifest and registries;
2. Need × Market — recorded instrument/locale metrics, not measured demand;
3. Brand Competition — observed feature metrics, not recommendation quality;
4. Evidence & Citation Explorer — excerpts, matches, citations and lineage;
5. Opportunity Queue — hypotheses and frozen review status, not actionable scores.

`load_platform_snapshot(database: Path, release_id: str | None = None)` reads
presentation platform metadata/documents in one read-only transaction. Its six
document frames serve the five UI views; the demo does not create five SQL views.
The current selector follows only slot `current` pointing at a completed release;
there is no implicit newest-release fallback or live-table recomputation.

For consumer rollback choose **Completed platform release →
synthetic-v1-acceptance** (or an explicit earlier completed production release in
the correct production database). Keep the historical warehouse and release
available. This is explicit historical selection, not a pointer mutation. A
rollback/current-pointer CLI command is **not implemented**. Do not edit snapshot
rows or raw data to simulate rollback. The UI cannot publish, review, repair or
collect; stop any incompatible writer before opening the read-only database.

## Version traceability

| Checkpoint | Implemented interfaces | Partial / blocked / not demonstrated |
| --- | --- | --- |
| V0.1 foundation | Installed Python/src package, migration boundary, registries, platform audit, isolated runner manifests, input hashes and conservative reuse | Production approved brand/category/mapping governance missing; normalize/evidence still coupled; scoped invalidation optimization absent; synthetic demo does not validate production audit/rebuild |
| V0.2 evidence and metrics | Real v2 enrichment; separate answer mention and owned citation channels; per-feature coverage/null semantics; distinct response denominators and known run counts; explicit query/prompt/context eligibility; hash/JSON-path evidence | No controlled independent-trial validation, expected collection completeness, semantic need, demand or causal validation; recommendation/negative-context extraction not validated; this fixture is not full adapter/dbt acceptance |
| V1.0 platform | Atomic immutable completed platform snapshots, six document kinds, opt-in read-only five-view UI with legacy default, explicit old-release picker, additive review command; synthetic identity and next-release review freezing confirmed | Full regression/lint/dbt/browser and final sign-off pending; production publication blocked; no pointer rollback command |

No opportunity score, demand, conversion, traffic, expected revenue or ROI is
supplied. Recommendation and negative-context interpretation are unvalidated,
so **no recommendation KPI** is accepted. HHI concentration and temporal stability
are **unavailable / not implemented** in this acceptance scope. Three observations
in one synthetic window cannot establish temporal stability. Partial/unsupported
absence remains unknown, never a fabricated zero. Matching locale/window and an
approved fixture pair do not validate real intent equivalence or personalization.

## Verification handoff (recorded results and pending gates)

```powershell
uv run pytest tests/unit/test_platform_demo.py --no-cov
uv run pytest tests/unit/test_platform_analytics.py tests/unit/test_platform_pipeline.py tests/unit/test_platform_dashboard.py --no-cov
```

The new tests cover two real publications, current/historical read-only loads,
schemas consumed by all five views, mention denominators/distinct runs, existing
migrations, explicit synthetic registry markers, no raw registrations, protected
output refusal and unchanged bytes on read/overwrite refusal. They check that
missing review integration is reported as blocked; they **do not treat that
blocked result as successful review-freeze acceptance**.

| Verification | Exit code | Actual result / evidence |
| --- | --- | --- |
| Main integrator's scoped test verification | Not supplied | 105 tests passed as reported by main; not a full regression or post-formatting rerun |
| Synthetic demo invocation | Not separately recorded | [Recorded report](../data/exports/v1_acceptance_20261006/acceptance_report.json): synthetic-contract-passed, no blockers; completed synthetic-v1-acceptance and synthetic-v1-reviewed; each has 6 evidence responses / 10 metrics / 1 matched comparison / 1 hypothesis |
| First snapshot unchanged after review/second publication | Report check: true | first_release_unchanged=true; first_review_status=unreviewed |
| Review persisted and second snapshot freezes new status | Report check: true | Scripted review status and second_review_status=under_review; review_status_frozen_in_new_release=true |
| Full regression suite | Pending | Full-suite results and any post-fix rerun still required |
| Lint | Pending | Supplied E501 findings wrapped; final lint run still required |
| dbt | Pending | Build/test evidence still required |
| Browser | Pending | Interactive five-view/demo walkthrough still required |
| Production approved registries and mapping review | Blocked | Separate real reviewer evidence required |
| Security/cost/recovery review and final approval | Pending | Reviewer, date, decision and evidence required |

Owner sign-off: **not recorded**. This document is not final V1 acceptance.