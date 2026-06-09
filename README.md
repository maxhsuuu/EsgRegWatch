# ESGRegWatch

**Monetizing ESG Regulation and Carbon-Fee Data for Taiwan Enterprises**

> Big Data Systems — Spring 2026 | National Taiwan University  
> GitHub: *[replace with your repository URL]*  
> Live demo: *[replace with your deployment URL, if deployed]*

---

## What This Is

ESGRegWatch turns fragmented Taiwan ESG and carbon-fee regulatory announcements into a searchable, deadline-oriented intelligence product. It ingests official public sources (FSC, MOENV, TWSE, CCA), extracts structured entities (deadlines, fee rates, emission scopes), and delivers them through a searchable dashboard with customer impact summaries.

This repository is the course prototype demonstrating the full end-to-end pipeline:

```
Source list → Ingestion → Raw storage → Processing → Structured search → Dashboard
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate demand evidence (documents the validation methodology)
python scripts/validate_demand.py

# 3. Fetch live documents from official sources
python scripts/ingest.py

# 4. Build the SQLite index
python scripts/build_index.py

# 5. Launch the dashboard
streamlit run app.py
```

If official sources are unreachable, step 3 can be skipped — the system falls back to the curated seed dataset in `data/seed_documents.jsonl`.

---

## Repository Structure

```
esgregwatch/
├── app.py                          # Streamlit dashboard (delivery layer)
├── requirements.txt
├── data/
│   ├── sources_registry.json       # Seed list of official data sources
│   ├── seed_documents.jsonl        # Curated documents with full provenance
│   ├── raw/
│   │   └── fetched_documents.jsonl # Output of ingest.py (append-only)
│   └── processed/
│       ├── esgregwatch.sqlite      # Output of build_index.py
│       └── demand_evidence.json    # Output of validate_demand.py
└── scripts/
    ├── ingest.py                   # Ingestion pipeline
    ├── build_index.py              # Processing & index builder
    └── validate_demand.py          # Demand validation data collector
```

---

## System Architecture

```
┌─────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│   Data Sources       │    │     Ingestion         │    │   Raw Storage         │
│                     │    │                      │    │                      │
│  FSC press releases │    │  Airflow daily jobs  │    │  Object store        │
│  TWSE announcements │───►│  requests +          │───►│  (S3 / MinIO)        │
│  MOENV regulations  │    │  BeautifulSoup       │    │  Versioned HTML/PDF   │
│  IFRS profiles      │    │  PDF text extract    │    │  + source metadata   │
└─────────────────────┘    │  Kafka (at scale)    │    └──────────┬───────────┘
                           └──────────────────────┘               │
                                                                   ▼
┌─────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│   Delivery           │    │   Processing          │    │   Warehouse           │
│                     │    │                      │    │                      │
│  Web dashboard      │    │  Entity extraction   │    │  PostgreSQL          │
│  Email/LINE alerts  │◄───│  (fee, deadline,     │◄───│  + OpenSearch        │
│  PDF briefs         │    │   scope, authority)  │    │  + pgvector          │
│  REST API           │    │  TF-IDF / LLM summ.  │    │                      │
└─────────────────────┘    └──────────────────────┘    └──────────────────────┘
                                      │
                           ┌──────────▼───────────┐
                           │   Monitoring          │
                           │  Airflow logs        │
                           │  Quality checks      │
                           └──────────────────────┘
```

---

## Data Sources

All sources are official public sources — no scraping of private or proprietary data.

| ID | Authority | URL | Category |
|----|-----------|-----|----------|
| moenv_carbon_fee_2024 | Ministry of Environment | [link](https://www.moenv.gov.tw/en/news/press-releases/31552.html) | carbon_fee |
| cca_carbon_fee_fund | Climate Change Administration | [link](https://www.cca.gov.tw/en/affairs/carbon-fee-fund/2301.html) | carbon_fee |
| fsc_ifrs_s1s2_2025 | Financial Supervisory Commission | [link](https://www.fsc.gov.tw/en/) | disclosure_standard |
| twse_sustainability_2025 | Taiwan Stock Exchange | [link](https://cgc.twse.com.tw/) | reporting_deadline |

Each fetched record stores: `source_id`, `url`, `authority`, `retrieved_at`, `document_hash`, `text`, `http_status` — enabling full audit trail.

---

## Reproducing Demand Validation

Run `python scripts/validate_demand.py` to regenerate `data/processed/demand_evidence.json`.

This file documents the public-data acquisition process used to validate demand:
1. **Regulatory timeline** — key deadlines extracted from official announcements
2. **Market size** — 1,029 listed companies (TWSE, Sep 2025)
3. **WTP model** — time-savings logic: 10 hrs/month × NT$1,500/hr = NT$15,000 value > NT$12,000 basic plan price

---

## Deployment (Bonus)

To deploy on Streamlit Community Cloud:
1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo and set `app.py` as the main file
4. The app will run `build_index.py` on startup if the DB is not present

---

## Production Design Notes

The prototype uses SQLite and in-process TF-IDF for simplicity. The production design described in the report uses:

- **Apache Airflow** for orchestration (DAG-based, retries, alerting)
- **PostgreSQL** as the structured document store
- **OpenSearch / pgvector** for semantic search
- **Apache Spark** for batch processing of thousands of sustainability reports
- **Kafka** for low-latency alerts on high-priority regulatory updates

The biggest cost driver at scale is **human review of high-impact summaries**, not compute.
