# HKTDC Sports Footwear External Data MVP

## Coding Agent Implementation Specification

**Scope:** Implement an external-data opportunity intelligence pipeline without HKTDC supplier, buyer, CRM, exhibition, or business-matching data.

**Primary sources:** DataForSEO and UN Comtrade.

**Business users:** Marketing managers, SEO/GEO analysts, market intelligence teams, ecommerce analysts, and campaign planners.

---

## 1. Product objective

Build an **External Market Opportunity Radar** that helps a marketing manager answer:

1. Which sports-footwear needs, features, customer problems, and markets are gaining demand?
2. Which search opportunities have weak or incomplete search-result supply?
3. Which products, brands, sellers, specifications, and price bands are visible in each market?
4. Which brands and sources are recommended or cited by ChatGPT and Gemini?
5. Which markets have import momentum that supports digital demand signals?
6. Which opportunities should receive content, SEO, GEO, paid-search, ecommerce, or market-research resources?

The system must **not** claim confirmed buyer demand, supplier readiness, actual retail sell-through, business-matching conversion, or revenue opportunity.

---

## 2. Required technology

Use the following default stack unless the repository already defines alternatives:

- Python 3.12+
- `httpx` for HTTP requests
- `pydantic` for request, response, and configuration models
- `tenacity` for retry with exponential backoff
- `polars` or `pandas` for transformations
- `pyarrow` for Parquet
- PostgreSQL for normalized Silver and Gold tables
- Object storage for immutable Bronze JSON
- `dbt-core` for Silver-to-Gold SQL transformations
- Prefect or Apache Airflow for orchestration
- Great Expectations or Soda Core for data-quality checks
- `pytest`, `pytest-asyncio`, and `respx` for tests
- Docker and Docker Compose for local execution

Do not store API credentials in source code. Read credentials from environment variables or a managed secret store.

---

## 3. Environment variables

```bash
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
UN_COMTRADE_API_KEY=
DATABASE_URL=postgresql+psycopg://user:password@host:5432/opportunity_intelligence
BRONZE_PATH=s3://bucket/bronze
DEFAULT_TIMEZONE=UTC
LOG_LEVEL=INFO
```

Create `.env.example`. Never commit `.env`.

---

## 4. Repository structure

```text
app/
  config.py
  logging.py
  cli.py
  clients/
    dataforseo.py
    un_comtrade.py
  models/
    common.py
    keyword.py
    serp.py
    commerce.py
    llm.py
    trade.py
  pipelines/
    keyword_discovery.py
    keyword_monitoring.py
    serp_validation.py
    google_shopping.py
    amazon.py
    llm_visibility.py
    trade_validation.py
    opportunity_scoring.py
  transforms/
    taxonomy.py
    product_normalization.py
    entity_resolution.py
    metrics.py
  storage/
    bronze.py
    postgres.py
    parquet.py
  orchestration/
    weekly_flow.py
    monthly_flow.py
    llm_40_loop_flow.py
  quality/
    checks.py
sql/
  ddl/
  dbt/
tests/
configs/
  markets.yaml
  keywords.yaml
  prompts.yaml
  hs_codes.yaml
Dockerfile
docker-compose.yml
pyproject.toml
README.md
.env.example
```

---

## 5. Shared ingestion contract

Every API response must be written to Bronze before transformation.

Required metadata:

```json
{
  "source_system": "dataforseo",
  "endpoint": "/v3/dataforseo_labs/google/keyword_overview/live",
  "request_id": "uuid",
  "batch_id": "uuid",
  "request_payload": {},
  "requested_at": "ISO-8601 UTC",
  "received_at": "ISO-8601 UTC",
  "http_status": 200,
  "vendor_status_code": 20000,
  "vendor_status_message": "Ok.",
  "attempt": 1,
  "duration_ms": 1000,
  "estimated_cost": null,
  "raw_payload": {}
}
```

Bronze partition example:

```text
bronze/source=dataforseo/dataset=keyword_overview/year=2026/month=10/day=06/batch_id=<uuid>.json.gz
```

Requirements:

- Preserve raw payloads without deleting vendor fields.
- Hash canonical request parameters to support idempotency.
- Redact credentials and authorization headers from logs.
- Record empty but successful responses separately from failures.
- Send failed tasks to a dead-letter table after retry exhaustion.

---

## 6. DataForSEO client

Base URL:

```text
https://api.dataforseo.com
```

Authentication: HTTP Basic Authentication using `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`.

Implement:

```python
class DataForSEOClient:
    async def post_live(self, endpoint: str, tasks: list[dict]) -> dict: ...
    async def post_task(self, endpoint: str, tasks: list[dict]) -> list[str]: ...
    async def get_task(self, endpoint: str, task_id: str) -> dict: ...
    async def get_tasks_ready(self, endpoint: str) -> dict: ...
```

Client behavior:

- Use connection pooling.
- Apply configurable concurrency limits.
- Retry HTTP 429, 500, 502, 503, and 504.
- Inspect both HTTP status and DataForSEO task status.
- Do not retry permanent validation errors.
- Persist task IDs immediately after Standard task creation.
- Prefer Standard task endpoints for scheduled bulk collection.
- Use Live endpoints for development, interactive requests, or small controlled runs.

---

## 7. Keyword APIs

### 7.1 Keyword discovery: Keyword Ideas

Endpoint:

```http
POST /v3/dataforseo_labs/google/keyword_ideas/live
```

Schedule: monthly.

Input configuration:

```yaml
keywords:
  - running shoes
  - trail running shoes
  - basketball shoes
  - pickleball shoes
location_name: United Kingdom
language_code: en
limit: 1000
```

Collect:

- keyword
- location and language
- search volume
- monthly searches
- CPC
- paid competition and level
- keyword difficulty
- main and foreign intent
- SERP information
- keyword properties

Purpose: discover adjacent categories and concepts that do not necessarily contain the seed phrase.

### 7.2 Long-tail discovery: Keyword Suggestions

Endpoint:

```http
POST /v3/dataforseo_labs/google/keyword_suggestions/live
```

Schedule: monthly for selected seed terms.

Collect the same commercial and demand fields as Keyword Ideas.

Purpose: discover long-tail queries containing the seed, such as feature, problem, consumer, and use-case modifiers.

### 7.3 Recurring monitoring: Keyword Overview

Endpoint:

```http
POST /v3/dataforseo_labs/google/keyword_overview/live
```

Schedule: weekly for the approved tracking universe.

Request example:

```json
[
  {
    "keywords": [
      "wide toe box running shoes",
      "waterproof trail shoes women",
      "pickleball shoes for flat feet"
    ],
    "location_name": "United Kingdom",
    "language_code": "en",
    "include_clickstream_data": true
  }
]
```

Collect:

- keyword
- search volume
- monthly searches
- clickstream search volume when available
- CPC
- competition
- competition level
- top-of-page bid range
- keyword difficulty
- search intent
- SERP information
- average backlink information

Create `fact_keyword_monthly` with one row per keyword, market, language, source month, and collection batch.

Derived measures:

```text
mom_growth = current_volume / previous_month_volume - 1
yoy_growth = current_volume / prior_year_volume - 1
acceleration = recent_3m_growth - previous_3m_growth
commercial_value = percentile_rank(cpc) * intent_weight
seasonality = coefficient_of_variation(monthly_searches)
```

Do not fabricate missing values. Preserve `null` and add a missingness reason.

---

## 8. Google SERP API

Use Google Organic SERP Advanced.

Standard pattern:

```http
POST /v3/serp/google/organic/task_post
GET  /v3/serp/google/organic/task_get/advanced/{task_id}
```

Optional interactive pattern:

```http
POST /v3/serp/google/organic/live/advanced
```

Request example:

```json
[
  {
    "keyword": "wide toe box trail running shoes",
    "location_name": "United Kingdom",
    "language_code": "en",
    "device": "desktop",
    "os": "windows",
    "depth": 20,
    "calculate_rectangles": true,
    "tag": "weekly_serp_uk"
  }
]
```

Create:

### `fact_serp_snapshot`

- snapshot_id
- keyword_id
- market
- language
- device and OS
- collection time
- result count
- check URL
- item types

### `fact_serp_result`

- snapshot_id
- result type
- rank group
- rank absolute
- pixel position when returned
- domain
- URL
- title
- description
- breadcrumb
- rating, review count, price, and merchant when returned
- feature flags for organic, paid, Shopping, image, video, People Also Ask, featured snippet, forum, and local result

Transformations:

- Normalize domains to registrable domains.
- Classify source type: brand, retailer, marketplace, publisher, forum, video, social, or other.
- Classify page type: product, category, article, comparison, review, homepage, or unknown.
- Calculate semantic relevance to the keyword taxonomy.
- Track new, lost, and moved URLs between snapshots.

Metrics:

- relevant result ratio
- brand dominance
- marketplace dominance
- weak-domain ratio
- local-language gap
- product-page gap
- SERP feature coverage
- SERP volatility

Default depth: Top 20. Use Top 50 only for shortlisted opportunities.

---

## 9. Google Shopping APIs

### 9.1 Product search

```http
POST /v3/merchant/google/products/task_post
GET  /v3/merchant/google/products/task_get/advanced/{task_id}
```

Collect:

- product ID
- data document ID
- GID
- title and description
- result rank
- seller and domain
- product URL and image URL
- price and currency
- rating and review count
- delivery information

### 9.2 Product details

```http
POST /v3/merchant/google/product_info/task_post
GET  /v3/merchant/google/product_info/task_get/advanced/{task_id}
```

Input must use product identifiers returned by Product Search.

Collect:

- title, brand, description, and images
- specifications
- variations
- rating and review count
- product features
- seller information returned in product details

Extract sport-footwear attributes:

- sport
- target consumer
- width
- available size range
- upper material
- midsole material
- outsole material
- waterproof claim
- carbon-plate claim
- arch-support claim
- weight
- sustainability claim

Store original text and normalized value. Add extraction confidence and extraction method.

### 9.3 Sellers

```http
POST /v3/merchant/google/sellers/task_post
GET  /v3/merchant/google/sellers/task_get/advanced/{task_id}
```

Collect:

- seller name and URL
- base price
- total price
- shipping price and details
- currency
- special offers
- purchase details
- seller rating when returned

Metrics:

- unique product count
- unique merchant count
- brand result share
- median and interquartile price
- price dispersion
- discount rate
- local-seller ratio
- specification coverage
- feature availability gap

Use weekly snapshots for shortlisted queries. Use daily snapshots only for a small watchlist.

---

## 10. Amazon Merchant APIs

### 10.1 Products

```http
POST /v3/merchant/amazon/products/task_post
GET  /v3/merchant/amazon/products/task_get/advanced/{task_id}
```

Collect:

- ASIN
- ranking
- title
- product and image URLs
- price and currency
- rating and review count
- seller
- sponsored flag
- Prime, Best Seller, and Amazon Choice indicators when returned
- delivery information

### 10.2 ASIN variations

```http
POST /v3/merchant/amazon/asin/task_post
GET  /v3/merchant/amazon/asin/task_get/advanced/{task_id}
```

Use this endpoint to map size, colour, and other variations to parent products. Prevent variation ASINs from being counted as independent product models.

### 10.3 Sellers

```http
POST /v3/merchant/amazon/sellers/task_post
GET  /v3/merchant/amazon/sellers/task_get/advanced/{task_id}
```

Collect:

- seller ID and name
- condition
- item price
- shipping price
- currency
- seller rating
- fulfilment
- buy-box indicator when returned
- delivery date or delivery text

Important limitation: do not build the MVP around the Amazon Reviews endpoint if vendor documentation marks that endpoint unavailable. Treat listing review count and rating as marketplace signals, not direct review-text access or actual sales.

---

## 11. LLM visibility APIs

### 11.1 ChatGPT

```http
POST /v3/ai_optimization/chat_gpt/llm_scraper/live/advanced
```

### 11.2 Gemini

Use the current DataForSEO Gemini LLM Scraper endpoint exposed to the account. Keep the provider and endpoint in configuration rather than hard-coding it throughout the pipeline.

Prompt configuration:

```yaml
prompts:
  - prompt_id: wide_fit_recommendation_uk
    text: What are the best running shoe brands for women with wide feet in the UK?
    category: product_recommendation
    market: United Kingdom
    language_code: en
    weekly: true
    monthly_runs: 40
```

Persist every run separately:

- experiment ID
- batch ID
- prompt ID
- run number
- platform
- model/version when returned
- market and language
- timestamp
- raw response
- response elements
- citations and links
- search queries when returned
- task cost and latency
- status

Extract:

- brands
- products
- retailers
- publishers and source domains
- product attributes
- recommendation flag
- mention order
- citation position
- positive, neutral, or negative context
- competitor co-mentions

Metrics:

```text
mention_rate = runs_containing_brand / successful_runs
citation_rate = runs_citing_brand_or_domain / successful_runs
recommendation_rate = recommendation_runs / successful_runs
mean_mention_position = average(first_mention_position)
answer_stability = mean_pairwise_similarity(responses)
source_share = citations_to_domain / all_citations
```

For the monthly 40-loop, issue 40 independent API calls for each prompt, model, market, and language. Do not duplicate one response 40 times. Store failed runs and calculate metrics using successful-run denominators while separately reporting success rate.

---

## 12. UN Comtrade APIs

Base URL:

```text
https://comtradeapi.un.org
```

### 12.1 Data availability

Use the official data-availability endpoint before requesting new trade periods.

```text
data/v1/getDa
```

Use preview endpoints only for development or small validation requests.

### 12.2 Final trade data

```text
data/v1/get
```

Initial scope:

- type: goods
- frequency: monthly and annual
- classification: HS
- trade flow: imports
- partners: world and key sourcing countries
- HS families: 6402, 6403, and 6404, refined to valid six-digit lines after HS-revision review

Collect:

- period
- reporter and partner codes/descriptions
- second partner when used
- flow code and description
- classification
- commodity code and description
- aggregation level
- customs and transport codes when returned
- primary trade value
- net and gross weight
- quantity and unit
- alternate quantity and unit
- reported/aggregate flags
- publication and revision metadata

Create a versioned HS mapping table. Do not equate broad HS 6404 data directly with running, basketball, trail, or pickleball shoes.

Metrics:

- import value and quantity
- month-on-month and year-on-year growth
- three-year CAGR for annual data
- average customs unit value
- sourcing-country share
- Herfindahl-Hirschman concentration index
- search-to-trade divergence

---

## 13. Taxonomy

Create controlled dimensions for:

```text
sport: running, trail_running, basketball, tennis, pickleball, football, hiking, cross_training
consumer: women, men, children, seniors, beginners, competitive_athletes
feature: wide_fit, carbon_plate, waterproof, arch_support, lightweight, slip_resistant, sustainable_material
pain_point: flat_feet, toe_pressure, heel_slip, wet_grip, durability, breathability, sizing_inconsistency
use_case: long_distance, humid_weather, wet_weather, standing_all_day, race_day, daily_training
price_band: market-specific configurable ranges
```

Store vendor text separately from normalized taxonomy values.

---

## 14. Gold opportunity model

Create `fact_opportunity_score` at the level:

```text
market × language × keyword_cluster × sport × feature × scoring_date
```

Initial score:

```text
30% demand momentum
20% SERP supply gap
20% commerce gap
15% AI visibility gap
15% trade momentum
```

Implementation requirements:

- Normalize each component within comparable market/category groups.
- Winsorize extreme metrics.
- Require minimum evidence coverage before publishing a total score.
- Publish component values and evidence dates.
- Add `confidence_tier`: high, medium, low, or insufficient.
- Add `data_freshness_days` for every component.
- Do not output a commercial-value estimate unless a defensible model and labelled assumptions exist.

Suggested publication gate:

```text
At least 4 of 5 components available
Keyword history >= 6 months
At least 10 SERP results collected
At least 10 commerce listings or explicit low-supply flag
LLM successful runs >= 30 for monthly probability metrics
Trade data no older than the latest available reporting period
```

---

## 15. Orchestration

### Weekly flow

```text
load approved keyword universe
→ keyword overview
→ compute demand triggers
→ SERP Advanced for triggered keywords
→ Google Shopping Products for triggered keywords
→ weekly ChatGPT and Gemini prompts
→ transform and quality-check
→ refresh marketing outputs
```

### Monthly flow

```text
keyword ideas and suggestions
→ taxonomy classification and deduplication
→ shortlist approval rules
→ Product Info and Sellers for selected products
→ Amazon Products, ASIN and Sellers
→ LLM 40-loop
→ UN Comtrade availability and final data
→ opportunity score refresh
```

### Trigger example

Run expensive downstream APIs only when at least two are true:

- three-month search growth is at least 15%
- intent is commercial or transactional
- CPC is above the market/category median
- query belongs to a newly discovered cluster
- relevant SERP result ratio is below 50%
- commerce listing count is below category threshold

Make every threshold configurable.

---

## 16. Data quality tests

Implement tests for:

- unique primary keys
- non-null source, request ID, batch ID, and collection timestamp
- accepted country, language, currency, and device values
- price greater than or equal to zero
- ratings within vendor-supported ranges
- rank greater than zero
- monthly search dates continuous where data exists
- no accidental duplication of Amazon variations
- valid HS code length and classification version
- LLM run number unique within experiment batch
- successful-run denominator recorded for LLM rates
- stale-data alerts
- unexpected API response-schema change
- request cost and task count anomaly

Fail the pipeline only for critical contract errors. Quarantine malformed records and continue processing unaffected tasks.

---

## 17. Observability

Log and expose:

- requests by source and endpoint
- successful, empty, failed, retried, and quarantined tasks
- API latency
- estimated and reported cost
- records received and records published
- schema-change alerts
- data freshness
- monthly 40-loop completion rate
- pipeline duration
- trigger conversion from keyword universe to expensive validation

Create alerts for:

- authentication failure
- vendor status failure
- 429 rate limiting
- cost above daily budget
- response volume falling by more than 50% versus baseline
- missing weekly or monthly partitions
- LLM successful-run rate below 75%

---

## 18. Security and governance

- Restrict secret access to runtime identities.
- Encrypt data in transit and at rest.
- Avoid storing unnecessary cookies, session identifiers, or personal information.
- Respect vendor licences and terms.
- Store provenance and permitted-use fields.
- Keep raw responses access-controlled.
- Add configurable retention controls.
- Make dashboard outputs traceable to source records.

---

## 19. Coding-agent acceptance criteria

The coding agent is finished only when:

1. `docker compose up` starts PostgreSQL and the application.
2. A CLI command can run one market end to end.
3. Each API client has mocked unit tests.
4. Standard task submission and polling are idempotent.
5. Bronze JSON and normalized Parquet/PostgreSQL outputs are produced.
6. Weekly and monthly flows can resume after interruption.
7. Data-quality checks run automatically.
8. Opportunity component scores can be recalculated from stored evidence.
9. Every published opportunity includes source, evidence date, limitations, and confidence tier.
10. README contains setup, commands, schemas, troubleshooting, expected costs, and backfill instructions.

Example CLI:

```bash
python -m app.cli discover-keywords --market GB --language en
python -m app.cli monitor-keywords --market GB --language en --date 2026-10-06
python -m app.cli validate-serp --market GB --triggered-only
python -m app.cli collect-shopping --market GB --triggered-only
python -m app.cli run-llm-weekly --market GB
python -m app.cli run-llm-batch --prompt-id wide_fit_recommendation_uk --runs 40
python -m app.cli collect-trade --reporter 826 --period 2025 --hs 6402,6403,6404
python -m app.cli build-gold --as-of 2026-10-06
```

---

## 20. Reference documentation

- DataForSEO Keyword Overview: <https://docs.dataforseo.com/v3/dataforseo_labs-google-keyword_overview-live/>
- DataForSEO Keyword Ideas: <https://docs.dataforseo.com/v3/dataforseo_labs-google-keyword_ideas-live/>
- DataForSEO Keyword Suggestions: <https://docs.dataforseo.com/v3/dataforseo_labs-google-keyword_suggestions-live/>
- DataForSEO Google SERP overview: <https://docs.dataforseo.com/v3/serp-google-organic-overview/>
- DataForSEO SERP Live Advanced: <https://docs.dataforseo.com/v3/serp-se-type-live-advanced/>
- DataForSEO Merchant API: <https://docs.dataforseo.com/v3/merchant-api-overview/>
- DataForSEO Google Shopping: <https://docs.dataforseo.com/v3/merchant-google-overview/>
- DataForSEO Amazon Merchant: <https://docs.dataforseo.com/v3/merchant-amazon-overview/>
- DataForSEO LLM Scraper: <https://docs.dataforseo.com/v3/ai_optimization-llm_scraper-overview/>
- DataForSEO ChatGPT LLM Scraper: <https://docs.dataforseo.com/v3/ai_optimization-chat_gpt-llm_scraper-live-advanced/>
- UN Comtrade API: <https://uncomtrade.org/docs/un-comtrade-api/>
- UN Comtrade portal: <https://comtradeplus.un.org/>
