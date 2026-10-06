# V1.0 Data Science Validation Upgrade Brief

## Sports Footwear SEO × GEO Hidden Opportunity Platform

**Purpose:** Instruct a coding agent to add a rigorous data-science validation layer to the existing V1.0 platform without rebuilding or breaking the current system.

**Current state assumption:** V1.0 already includes the existing SERP + LLM data pipeline, Silver transformations, evidence extraction, Gold metrics, release snapshots, five dashboard views, evidence drill-down, opportunity hypotheses, review/status flow, documentation, and backup/recovery procedures.

**Primary rule:** Extend the current architecture incrementally. Do not replace verified V1.0 components unless a documented defect or incompatibility is proven.

---

# 1. Why Add Data Science Validation?

The present V1.0 platform can identify SEO and GEO signals, but a signal is not automatically a reliable market inefficiency or business opportunity. The data-science layer must quantify how much uncertainty, instability, sampling variation, seasonality, multiple-testing risk, and model sensitivity exist behind each result.

The upgrade adds six forms of value.

## 1.1 Separate real signals from random fluctuation

Examples:

- A brand mention rate of 45% based on 40 successful LLM runs is more credible than 50% based on four runs.
- A keyword growing for one month may reflect seasonality or noise rather than emerging demand.
- A SERP relevance gap observed once may disappear in the next snapshot.

Required outcome:

```text
metric value
+ sample size
+ uncertainty interval
+ data freshness
+ stability status
= interpretable evidence
```

## 1.2 Prevent false opportunities caused by mass scanning

The platform may compare many markets, needs, brands, prompts, models, features, and time periods. Running many statistical tests increases the probability of false discoveries. Discovery results must therefore record the test family and use an appropriate multiple-testing correction.

Required outcome:

```text
raw p-value
adjusted p-value
correction method
test family ID
number of simultaneous tests
```

For exploratory scanning, use Benjamini-Hochberg False Discovery Rate by default. Use Holm correction for a small set of high-consequence confirmatory comparisons.

## 1.3 Distinguish statistical significance from business importance

A small difference can be statistically detectable but commercially irrelevant. Every inferential comparison must include effect size, uncertainty, and a configured business-materiality threshold.

Required outcome:

```text
statistically_detectable
commercially_material
operationally_actionable
```

These are separate fields and must not be collapsed into one boolean.

## 1.4 Validate whether rankings are robust

The future opportunity score will combine demand, SERP, commerce, AI visibility, and trade components. Rankings may change when weights or normalization methods change. The platform must measure rank sensitivity before presenting an opportunity as robust.

Required outcome:

```text
median rank
rank interval
Top-5 inclusion probability
Top-10 inclusion probability
ranking robustness tier
```

## 1.5 Backtest whether earlier signals predicted later market movement

The platform must test historical releases without leaking future information. A useful model should outperform simple baselines such as search-volume-only and search-growth-only rankings.

Required outcome:

```text
Precision@K
Recall@K
NDCG@K
lift over random
lift over search-growth-only
out-of-time validation period
```

## 1.6 Make future V2.0 opportunities defensible

By V2.0, a published opportunity should be supported by:

```text
market attractiveness
+ market inefficiency strength
+ evidence confidence
+ ranking robustness
+ explicit limitations
```

The data-science layer does not prove that revenue will occur. It determines whether an external opportunity hypothesis is sufficiently supported for further validation or a controlled marketing experiment.

---

# 2. Scope of This Upgrade

Implement the following capabilities on top of V1.0:

1. Metric contracts and denominator validation
2. Descriptive statistics and missingness diagnostics
3. Confidence and credible intervals
4. Statistical comparison framework
5. Effect-size calculation
6. Multiple-testing correction
7. SEO/SERP stability analysis
8. LLM/GEO run stability analysis
9. Time-series trend and seasonality analysis
10. Score and rank sensitivity analysis
11. Historical backtesting
12. Validation status and publication gates
13. Data-science evidence in API and dashboard outputs
14. Reproducible analysis manifests

Do not implement at this stage:

- automatic campaign execution;
- causal claims without an approved experimental design;
- automatic website changes;
- automatic advertising changes;
- production Jev or other decision-model adoption;
- replacement of deterministic Gold logic with an LLM;
- rewriting the V1.0 pipeline from scratch.

---

# 3. Non-Negotiable Statistical Principles

## 3.1 No p-value-only decisions

Every statistical result must include:

- sample size;
- comparison definition;
- effect size;
- uncertainty interval;
- raw p-value when applicable;
- adjusted p-value when multiple tests are performed;
- assumptions and diagnostics;
- business-materiality threshold;
- data freshness;
- limitations.

## 3.2 No unsupported zeroes

Missing, empty, failed, unsupported, ineligible, and zero are different states.

Never convert:

```text
missing → 0
failed → 0
unsupported → 0
no successful runs → 0%
```

## 3.3 Predefine hypotheses

A confirmatory test must be registered before inspecting the final result. Exploratory findings must be labelled `exploratory` and cannot be presented as confirmed evidence.

## 3.4 Use the correct unit of analysis

Examples:

- LLM visibility: independent run, not response paragraph
- SERP analysis: snapshot or query-market-device unit
- Brand comparison: matched prompt-run pairs where possible
- Keyword time series: source month, not ingestion timestamp
- Citation analysis: qualified answer-run or citation event according to the metric contract

## 3.5 Preserve reproducibility

Every analysis must record:

```text
analysis_run_id
release_id
dataset_versions
metric_versions
code_commit
configuration_hash
random_seed
created_at
```

## 3.6 Never infer causality from correlation alone

Use the following evidence levels:

```text
descriptive_signal
statistically_supported_association
quasi_experimental_evidence
randomized_causal_evidence
```

V1.x opportunity results will normally remain at the first two levels.

---

# 4. Required Architecture

Add a new bounded context without replacing current V1.0 services:

```text
Existing verified releases
        ↓
Validation input contracts
        ↓
Statistical analysis engine
        ↓
Validation results store
        ↓
Publication gate
        ↓
Existing dashboard and evidence explorer
```

Suggested package structure:

```text
app/
  validation/
    contracts/
      metric_contract.py
      hypothesis_contract.py
      validation_result.py
    descriptive/
      summary.py
      missingness.py
      outliers.py
    inference/
      proportions.py
      continuous.py
      nonparametric.py
      bootstrap.py
      multiple_testing.py
      effect_size.py
    timeseries/
      trend.py
      seasonality.py
      change_points.py
      anomalies.py
    stability/
      llm_stability.py
      serp_stability.py
      cross_release.py
    sensitivity/
      weight_sensitivity.py
      rank_robustness.py
    backtesting/
      runner.py
      baselines.py
      ranking_metrics.py
    gates/
      publication_gate.py
      confidence_tier.py
    registry/
      hypothesis_registry.py
      method_registry.py
      experiment_registry.py
  api/
    validation.py
  db/
    migrations/
      validation/
tests/
  validation/
docs/
  data-science/
```

Use the existing project conventions where equivalent directories already exist. Do not duplicate infrastructure.

---

# 5. Phase A: Audit V1.0 Before Coding

The coding agent must first inspect the current implementation and produce:

```text
docs/data-science/V1_CURRENT_STATE_AUDIT.md
docs/data-science/METRIC_CONTRACT_INVENTORY.md
docs/data-science/DENOMINATOR_AUDIT.md
docs/data-science/VALIDATION_GAP_ANALYSIS.md
docs/data-science/DATA_SCIENCE_IMPLEMENTATION_PLAN.md
docs/adr/ADR-data-science-validation-layer.md
```

For every current KPI, document:

```text
metric_id
display_name
business_question
grain
numerator
denominator
eligible population
excluded population
source datasets
source fields
metric version
minimum sample requirement
missing-state behavior
current uncertainty method
current stability method
current publication rule
known limitations
```

Classify every metric:

```text
validated
valid_but_missing_uncertainty
valid_but_missing_stability
valid_but_missing_denominator_contract
requires_redefinition
unsupported
blocked
```

Do not modify production code during Phase A.

---

# 6. Phase B: Metric Contracts and Descriptive Statistics

## 6.1 Create a versioned Metric Contract

Minimum schema:

```yaml
metric_id: llm_brand_recommendation_rate
metric_version: 2.1.0
business_question: How often is a brand recommended in eligible answers?
grain: brand x prompt x provider x market x language x release
numerator: successful eligible runs where the brand is recommended
denominator: successful eligible answer-producing runs
minimum_denominator: 30
missing_policy: null
unsupported_policy: null
confidence_interval: wilson
publication_rule: denominator >= 30 and run_success_rate >= 0.75
```

## 6.2 Add descriptive output to every applicable KPI

Required fields:

```text
value
count
eligible_count
missing_count
failed_count
unsupported_count
mean
median
standard_deviation
interquartile_range
minimum
maximum
coefficient_of_variation
outlier_count
```

Only populate statistics that are meaningful for the metric type.

## 6.3 Required quality checks

- denominator is not zero;
- numerator is not greater than denominator;
- candidate records do not enter published denominators;
- failed runs do not enter successful-run denominators;
- unsupported contexts remain null;
- reruns do not duplicate counts;
- cross-release comparisons use compatible metric versions.

---

# 7. Phase C: Confidence Intervals and Uncertainty

## 7.1 Binary and proportion metrics

Examples:

- brand mention rate;
- recommendation rate;
- citation rate;
- organic presence rate;
- relevant SERP result ratio;
- answer success rate.

Default method:

```text
Wilson score interval at 95% confidence
```

Avoid normal approximation for small samples or extreme probabilities.

Required output:

```text
estimate
lower_bound
upper_bound
confidence_level
method
numerator
denominator
```

## 7.2 Median and irregular distributions

Use bootstrap intervals for:

- median price;
- price dispersion;
- seller count summaries;
- citation concentration;
- opportunity score uncertainty;
- rank stability.

Requirements:

```text
bootstrap_repetitions: 2000 by default
random_seed: recorded in run manifest
resampling_unit: explicitly configured
interval_method: percentile or BCa, documented per metric
```

## 7.3 Minimum sample rule

Suggested publication states:

```text
n < 10                 → insufficient
10 <= n < 30           → directional_only
n >= 30                → eligible_for_interval_reporting
```

These defaults must remain configurable and metric-specific.

---

# 8. Phase D: Hypothesis Testing Framework

Create a versioned Hypothesis Registry.

Minimum fields:

```text
hypothesis_id
opportunity_id or analysis_scope
hypothesis_type
exploratory_or_confirmatory
null_hypothesis
alternative_hypothesis
primary_metric
secondary_metrics
comparison_groups
unit_of_analysis
observation_window
minimum_effect_size
planned_method
assumptions
exclusion_rules
test_family_id
status
registered_at
```

## 8.1 Supported test families

Implement deterministic method selection with explicit diagnostics.

### Proportion comparisons

Use when comparing mention, recommendation, citation, presence, or relevance rates:

- two-proportion z-test when assumptions are satisfied;
- Fisher's exact test for sparse counts;
- chi-square test for larger contingency tables;
- McNemar test for paired binary outcomes.

### Continuous or ordinal comparisons

Use:

- Welch's t-test when suitable;
- Mann-Whitney U for independent non-normal groups;
- Wilcoxon signed-rank for paired non-normal observations;
- permutation test when distribution assumptions are unsuitable;
- bootstrap difference intervals.

### Equivalence and non-inferiority

Support equivalence testing when the business question is whether two results are practically similar, not merely different.

## 8.2 Test selector behavior

The test selector must:

1. inspect metric type;
2. inspect pairing;
3. inspect group count;
4. inspect sample size;
5. inspect distribution and sparsity diagnostics;
6. return the allowed method or `blocked`;
7. record why a method was selected;
8. never let an LLM select or execute the final statistical method.

---

# 9. Phase E: Multiple-Testing Control

## 9.1 Define test families

Examples:

```text
same release + same opportunity family + same primary metric
same market scan + same feature family
same GEO prompt set + same model comparison
```

## 9.2 Default corrections

```text
Exploratory opportunity discovery → Benjamini-Hochberg FDR
Confirmatory high-consequence comparisons → Holm
Single preregistered primary test → no correction, but document why
```

## 9.3 Required result fields

```text
raw_p_value
adjusted_p_value
alpha
fdr_q
correction_method
test_family_id
test_family_size
reject_null
```

Suggested defaults:

```text
Exploratory candidate flag: adjusted q <= 0.10
Publishable statistical support: adjusted q <= 0.05
```

These thresholds must be configurable and must not replace effect-size requirements.

---

# 10. Phase F: Effect Size and Materiality

Implement effect sizes appropriate to each comparison:

```text
Difference in proportions
Relative risk
Odds ratio
Cohen's d
Hedges' g
Cliff's delta
Rank-biserial correlation
Median difference
Percentage-point difference
```

Every result must return:

```text
effect_size_name
effect_size_value
effect_size_interval
materiality_threshold
commercially_material
```

Example:

```text
Brand A recommendation rate: 40%
Brand B recommendation rate: 45%
Difference: -5 percentage points
Adjusted p-value: 0.01
Configured materiality threshold: 15 percentage points

statistically_detectable = true
commercially_material = false
```

---

# 11. Phase G: SEO and SERP Stability

Add stability measures for repeated SERP snapshots.

Required analyses:

- URL churn;
- domain churn;
- rank movement;
- relevant-result ratio stability;
- brand dominance stability;
- marketplace dominance stability;
- SERP-feature appearance frequency;
- device and market consistency;
- release-to-release compatibility.

Suggested outputs:

```text
serp_volatility_score
url_retention_rate
domain_retention_rate
median_absolute_rank_change
relevance_ratio_interval
snapshot_count
stability_tier
```

Suggested tiers:

```text
high_stability
moderate_stability
low_stability
insufficient_snapshots
```

Do not publish a persistent SERP gap based on a single snapshot without clearly labelling it `single_observation`.

---

# 12. Phase H: LLM and GEO Stability

For every prompt × provider × model × market × language context, calculate:

- scheduled runs;
- successful runs;
- answer-producing runs;
- run success rate;
- brand mention rate and interval;
- recommendation rate and interval;
- citation rate and interval;
- first-mention position distribution;
- citation-domain share;
- answer similarity;
- citation-set similarity;
- between-run variance;
- between-day drift;
- between-model agreement.

Publication defaults:

```text
scheduled_runs = 40
successful_runs >= 30
run_success_rate >= 0.75
```

A run retry must preserve the logical run identity. A retry must not become a new independent observation.

Store:

```text
logical_run_id
attempt_id
run_number
retry_number
provider
model_version
prompt_version
market
language
status
```

---

# 13. Phase I: Time-Series Validation

Implement reusable functions for:

- rolling mean and median;
- exponential smoothing;
- seasonal comparison;
- year-over-year growth;
- trend slope;
- growth acceleration;
- change-point detection;
- anomaly detection;
- forecast intervals where suitable.

Applicable datasets:

```text
keyword search volume
SERP competition
commerce product count
median price
seller count
LLM mention and citation rates
trade imports and unit values
```

Required output:

```text
observed_growth
seasonally_adjusted_growth
trend_slope
trend_strength
growth_acceleration
change_point_detected
change_point_date
anomaly_score
history_length
```

Do not claim seasonally adjusted growth unless sufficient historical seasonal coverage exists.

---

# 14. Phase J: Score Sensitivity and Rank Robustness

The present or future opportunity score weights must be stored in versioned configuration.

Initial V2.0 target weights:

```text
Demand Momentum   30%
SERP Gap          20%
Commerce Gap      20%
AI Visibility Gap 15%
Trade Momentum    15%
```

## 14.1 One-at-a-time sensitivity

Adjust each component weight by ±5 percentage points and renormalize the remaining weights.

## 14.2 Monte Carlo weight simulation

Default:

```text
simulations: 10,000
weight constraints: configurable
random seed: recorded
```

For each opportunity return:

```text
base_rank
median_simulated_rank
rank_p05
rank_p95
top_5_probability
top_10_probability
score_standard_deviation
ranking_robustness
```

Suggested robustness labels:

```text
high: top_10_probability >= 0.80
medium: 0.50 <= top_10_probability < 0.80
low: top_10_probability < 0.50
```

Thresholds must remain configurable.

---

# 15. Phase K: Historical Backtesting

Build an out-of-time backtesting engine.

## 15.1 Prevent data leakage

For a historical cut-off date, use only evidence available on or before the cut-off.

Do not use:

- later release corrections unavailable at the time;
- future keyword volume;
- future SERPs;
- future commerce listings;
- future LLM responses;
- later trade releases.

## 15.2 Baselines

Compare the platform against:

```text
random ranking
search-volume-only
search-growth-only
CPC-only
current weighted model
```

## 15.3 Outcomes

A configurable later-period validation event may include:

- sustained demand growth;
- commerce assortment growth;
- seller-count growth;
- SERP competition growth;
- AI mention growth;
- citation growth;
- trade momentum improvement.

Do not combine outcome definitions without versioning.

## 15.4 Evaluation metrics

Return:

```text
Precision@5
Precision@10
Precision@20
Recall@K
NDCG@K
lift_over_random
lift_over_search_growth
Brier_score when probability outputs exist
backtest_window
outcome_version
```

Publication gate:

The complex model must demonstrate practical lift over at least the search-growth-only baseline before claims of improved opportunity detection are allowed.

---

# 16. Validation and Publication Status

Every opportunity or analytical result must receive one status:

```text
insufficient_data
exploratory_signal
directional_evidence
statistically_supported
commercially_material
robust_priority
blocked
```

Suggested logic:

```text
insufficient_data
→ sample or coverage gate failed

exploratory_signal
→ descriptive mismatch exists, no confirmatory support

directional_evidence
→ interval and repeated observations support direction, but test/materiality gate incomplete

statistically_supported
→ adjusted significance and assumptions pass

commercially_material
→ statistical support and configured effect-size threshold pass

robust_priority
→ materiality, evidence confidence, freshness and rank robustness pass
```

Do not use `proven` or `confirmed business opportunity` as a system status.

---

# 17. Database Additions

Add versioned tables or equivalent models:

```text
metric_contract
hypothesis_registry
validation_run
validation_result
multiple_test_family
effect_size_result
stability_result
time_series_result
sensitivity_run
sensitivity_result
backtest_run
backtest_result
publication_gate_result
analysis_run_manifest
```

Key requirements:

- immutable result rows after release;
- corrections create a new version;
- foreign keys to release, evidence, metric version, and opportunity;
- unique constraints preventing duplicate analysis runs;
- clear distinction between exploratory and confirmatory analyses.

---

# 18. API Additions

Suggested endpoints:

```text
GET  /api/v1/metrics/{metric_id}/contract
GET  /api/v1/opportunities/{opportunity_id}/validation
GET  /api/v1/opportunities/{opportunity_id}/stability
GET  /api/v1/opportunities/{opportunity_id}/sensitivity
GET  /api/v1/backtests/{backtest_id}
POST /api/v1/hypotheses
POST /api/v1/validation-runs
GET  /api/v1/validation-runs/{validation_run_id}
```

Mutation endpoints require authorization and audit logging.

A validation response must include:

```json
{
  "validation_status": "directional_evidence",
  "sample_size": 40,
  "estimate": 0.425,
  "interval": {
    "lower": 0.284,
    "upper": 0.581,
    "level": 0.95,
    "method": "wilson"
  },
  "effect_size": null,
  "raw_p_value": null,
  "adjusted_p_value": null,
  "commercially_material": null,
  "freshness_days": 3,
  "limitations": [
    "The result measures model responses, not consumer purchases."
  ]
}
```

Numeric values in this example are illustrative schema examples only and must not be used as production results.

---

# 19. Dashboard Changes

Do not add a completely separate dashboard unless necessary. Extend existing V1.0 pages.

## Overview

Add:

- evidence confidence;
- percentage of opportunities by validation status;
- unstable metric warnings;
- insufficient-data counts;
- release validation status.

## Need × Market Map

Add filters for:

- validation status;
- effect-size materiality;
- confidence tier;
- rank robustness;
- freshness.

## Brand Competition

Add:

- confidence intervals;
- paired comparison results;
- adjusted significance;
- effect sizes;
- model agreement.

## Evidence & Citation Explorer

Add:

- sample definition;
- denominator details;
- run success rate;
- citation stability;
- analysis manifest;
- method and version.

## Opportunity Queue

Add:

```text
validation status
confidence tier
commercial materiality
rank robustness
backtest support
next validation action
```

Avoid presenting p-values as the main UI element. Lead with effect size, interval, status, and business interpretation.

---

# 20. Automated Tests

## Unit tests

- Wilson interval against known cases;
- bootstrap determinism with fixed seed;
- effect-size calculations;
- Benjamini-Hochberg adjustment;
- Holm adjustment;
- test-selector routing;
- paired and unpaired comparison handling;
- minimum-sample gates;
- missing-state behavior;
- rank-robustness calculations;
- backtest leakage prevention.

## Property-based tests

- adjusted p-values remain within [0, 1];
- numerator never exceeds denominator;
- intervals remain in valid metric ranges;
- rerunning with the same manifest is idempotent;
- changing a random seed changes stochastic simulation but not deterministic metrics;
- unsupported contexts never become zero.

## Integration tests

- V1.0 release to validation results;
- new validation tables to API;
- API to dashboard;
- release immutability;
- retry and resume;
- rollback and backup recovery.

## Golden dataset tests

Create small labelled fixtures for:

- stable and unstable LLM mention rates;
- sparse citations;
- paired brand comparisons;
- seasonal keyword growth;
- SERP volatility;
- weight-sensitive rankings;
- deliberately leaked backtest data that must be rejected.

All synthetic fixtures must be labelled `is_synthetic = true`.

---

# 21. Security, Cost, and Governance

- Do not send raw sensitive data to an external model for statistical analysis.
- Statistical methods must run locally in deterministic code.
- Keep random seeds, configuration, and package versions in manifests.
- Add compute-budget limits for bootstrap and Monte Carlo jobs.
- Add timeout and cancellation controls.
- Cache results using release ID + method version + configuration hash.
- Require authorization for hypothesis registration and validation execution.
- Audit all publication-gate overrides.
- A human reviewer must approve changes to materiality thresholds, scoring weights, and publication rules.

---

# 22. Recommended Implementation Sequence

## DS0: V1.0 audit

Deliver the six audit and planning documents. No production changes.

## DS1: Metric contracts

Add grain, numerator, denominator, missing-state, and minimum-sample contracts.

## DS2: Uncertainty

Add descriptive statistics, Wilson intervals, bootstrap intervals, and UI disclosure.

## DS3: Stability

Add SERP and LLM/GEO stability metrics across releases and runs.

## DS4: Inference

Add hypothesis registry, method selector, effect sizes, and multiple-testing correction.

## DS5: Time series

Add seasonality, trend strength, change points, and anomaly diagnostics.

## DS6: Robustness

Add score sensitivity and rank-robustness simulation.

## DS7: Backtesting

Add leakage-safe historical validation and baseline comparison.

## DS8: Publication gates

Integrate validation status into the existing Opportunity Queue and release checks.

Each DS stage requires:

- migration plan;
- tests;
- documentation;
- acceptance record;
- rollback plan;
- no regression in existing V1.0 release values unless an approved metric-version change exists.

---

# 23. Coding Agent Start Prompt

Use this as the first instruction to the coding agent:

```text
You are extending an already completed V1.0 SEO × GEO platform.
Do not rebuild the platform and do not begin by writing production code.

First inspect the existing repository, schemas, release snapshots, metric definitions,
Gold models, evidence lineage, dashboard queries, tests and documentation.

Create:

- docs/data-science/V1_CURRENT_STATE_AUDIT.md
- docs/data-science/METRIC_CONTRACT_INVENTORY.md
- docs/data-science/DENOMINATOR_AUDIT.md
- docs/data-science/VALIDATION_GAP_ANALYSIS.md
- docs/data-science/DATA_SCIENCE_IMPLEMENTATION_PLAN.md
- docs/adr/ADR-data-science-validation-layer.md

For every current KPI, document its grain, numerator, denominator, eligible population,
exclusions, source datasets, metric version, minimum sample requirement, missing-state
behavior, uncertainty method, stability method, publication rule and limitations.

Classify each KPI as:

- validated
- valid_but_missing_uncertainty
- valid_but_missing_stability
- valid_but_missing_denominator_contract
- requires_redefinition
- unsupported
- blocked

Preserve existing verified V1.0 behavior. Do not modify raw data, old releases or published
Gold outputs. Do not make paid API calls. Do not fabricate data. Stop after the audit,
architecture decision and staged implementation plan are complete.
```

---

# 24. Coding Agent Implementation Prompt

After the audit is approved, use:

```text
Implement the approved Data Science Validation Layer incrementally on top of V1.0.

Order:
1. metric contracts and denominator validation;
2. descriptive statistics and missingness;
3. confidence intervals;
4. SERP and LLM stability;
5. hypothesis registry and statistical test selector;
6. effect sizes and business-materiality thresholds;
7. multiple-testing control;
8. time-series validation;
9. score sensitivity and rank robustness;
10. historical backtesting;
11. publication gates and dashboard integration.

Do not replace existing Gold metrics silently. Any changed metric requires a new metric
version, compatibility note, backfill plan and side-by-side validation against the existing
release.

Never use an LLM to execute a statistical test or select the final statistical method.
Method selection, assumption checks, calculations and publication gates must be deterministic,
versioned and tested.

Every inferential result must include sample size, effect size, uncertainty interval, raw and
adjusted p-values where applicable, assumptions, diagnostics, materiality threshold, freshness,
method version and limitations.

Never convert missing, failed or unsupported states to zero. Keep exploratory and confirmatory
analyses separate. Prevent future-data leakage in every backtest.

After each implementation stage, run unit, integration, property-based and regression tests;
produce an acceptance report and rollback plan; and stop if any critical test fails.
```

---

# 25. Acceptance Criteria

The data-science upgrade is accepted only when:

1. Every published KPI has a versioned metric contract.
2. Every rate exposes numerator, denominator, eligibility, sample size, and uncertainty.
3. Missing, failed, empty, unsupported, and zero remain distinct.
4. LLM retries do not create false independent observations.
5. SERP and LLM metrics expose stability status.
6. Inferential comparisons include effect size and uncertainty.
7. Multiple simultaneous tests use a recorded correction method.
8. Statistical significance and commercial materiality are separate.
9. Opportunity rankings expose sensitivity and robustness.
10. Backtests prevent future-data leakage.
11. The complex ranking is compared with simple baselines.
12. Existing V1.0 values remain reproducible for old releases.
13. Any revised metric uses a new version and side-by-side compatibility report.
14. Validation results are traceable to releases, evidence, code and configuration.
15. Dashboard users can see confidence, limitations, and next validation steps.
16. No result is labelled a proven or confirmed business opportunity.
17. Tests, security checks, compute-cost controls, documentation and rollback procedures pass.

---

# 26. Final Product Interpretation

After this upgrade, the platform should communicate results as:

```text
Detected market inefficiency signal
+ measured uncertainty
+ cross-release stability
+ statistical support
+ commercial materiality
+ ranking robustness
+ explicit limitations
= prioritized opportunity hypothesis
```

The platform must not communicate:

```text
statistically significant
= guaranteed business opportunity
```

The target outcome is not more impressive scores. The target outcome is a platform where a marketing manager can understand:

- what was observed;
- how large the gap is;
- how uncertain the result is;
- whether the signal persists;
- whether the ranking is sensitive to assumptions;
- whether similar historical signals were useful;
- what additional validation is required before action.

---

# 27. Reference Standards and Methods

Use primary statistical documentation and validated libraries. Relevant references include:

- NIST/SEMATECH e-Handbook of Statistical Methods: <https://www.itl.nist.gov/div898/handbook/>
- NIST Product and Process Comparisons: <https://www.itl.nist.gov/div898/handbook/prc/section1/prc1.htm>
- NIST Comparing Instruments, including hypothesis tests, confidence intervals, nonparametric procedures and equivalence testing: <https://www.nist.gov/publications/comparing-instruments>

Suggested Python libraries, subject to the existing dependency policy:

```text
scipy
statsmodels
numpy
pandas or polars
scikit-learn
ruptures for optional change-point detection
hypothesis for property-based testing
```

Pin dependency versions and record them in every analysis manifest.
