# GEO Research Platform

Local-first research tooling for preserved SERP and generative-engine evidence.
The repository now includes guarded collection, DuckDB migrations, dbt evidence
models, platform audit/run/assessment/publication/review interfaces and a read-only
Streamlit V1 platform. Implementation availability is not production acceptance:
approved production brand/category/comparison registries and recorded end-to-end
sign-off remain gates. See [V1 acceptance and operations](docs/platform_v1_acceptance.md)
for version traceability, known blockers and historical-release recovery.

## Local Setup

Prerequisites: Python 3.12 and `uv`.

```powershell
uv python install 3.12
uv sync --all-groups
Copy-Item .env.example .env
```

Populate `.env` locally only when credentials are available. Do not place credentials in YAML files, tests, fixtures, or Git.

## Validation

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run geo-research version
uv run geo-research config-check
uv run geo-research paths
git status --short
```

The `config-check` command reports non-secret configuration only. It does not print credential values.

## Synthetic V1 Acceptance Demo

After the existing setup, from the project root:

```powershell
uv run python scripts/platform_acceptance_demo.py --project 'd:\FYP (2)\FYP (2)\FYP\FYP\FYP\FYP\FYP\FYP' --output data/exports/synthetic_v1_acceptance_20261006
```

Use a new output directory under data/exports; existing outputs and protected
raw/warehouse paths are refused. The [demo script](scripts/platform_acceptance_demo.py)
generates six invented observations through real feature extraction in a new
isolated database and publishes two synthetic snapshots. All fixture approval
and scripted review metadata are `is_synthetic`, **not real production review**.
It does not read/copy production raw or change production registries/old releases.

The report exposes review-identity/frozen-status integration blockers rather than
fabricating success; blocked gates return exit 2. Production health remains
blocked-on-production-registries, regardless of synthetic results. No scores,
demand, recommendation KPI or ROI are validated. Actual test results and final
acceptance are pending the main integrator's execution and sign-off.

For Streamlit launch, choose **V1 Platform** and the synthetic warehouse; for
rollback choose an explicit old completed release, not an unimplemented pointer
command. Full commands, interfaces, safeguards and pending results are in
[docs/platform_v1_acceptance.md](docs/platform_v1_acceptance.md).