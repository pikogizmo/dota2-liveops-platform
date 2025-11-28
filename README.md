# 🛡️ Dota 2 LiveOps & Meta Intelligence Platform

![Status](https://img.shields.io/github/actions/workflow/status/pikogizmo/dota2-liveops-platform/hourly_etl.yml?label=Pipeline&style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square)
![Database](https://img.shields.io/badge/Postgres-Neon%20Serverless-00bfa5?style=flat-square)

A serverless, automated data pipeline that monitors the global Dota 2 professional meta in real-time. Built to demonstrate **modern data engineering patterns** (ELT, Idempotency, Infrastructure-as-Code).

## 🏗️ Architecture

**Stack:**
* **Orchestration:** GitHub Actions (Cron: Hourly)
* **Compute:** Python 3.11 + `uv` (Containerized)
* **Storage:** Neon PostgreSQL (Serverless)
* **Ingestion:** OpenDota API (Raw Layer)
* **ML:** Scikit-Learn (Logistic Regression)

**Data Flow:**
1.  **Ingest:** Python scripts fetch the last 100 pro matches every hour.
2.  **Load:** Data is Upserted (Idempotent) into the `raw.pro_matches` table in Postgres.
3.  **Monitor:** GitHub Actions provides logging and failure alerts.

## 📊 Live Meta Dashboard
The pipeline automatically generates and deploys an interactive dashboard to GitHub Pages.

> [!TIP]
> **Explore the Data**
> [**View Live Dashboard**](https://pikogizmo.github.io/dota2-liveops-platform/)
> *Real-time win rates, pick counts, meta trends, and hero synergies.*

![Meta Analysis](meta_snapshot.png)
*(Static snapshot. Visit the live dashboard for interactive data.)*

### Data Source & Frequency
* **Source:** OpenDota Public API
* **Update Frequency:** Hourly
* **Storage Strategy:** Raw JSONB retention for full replay parsing.

## 🛠️ Setup & Local Development

This project uses `uv` for lightning-fast dependency management.

```bash
# 1. Clone
git clone [https://github.com/pikogizmo/dota2-liveops-platform.git](https://github.com/pikogizmo/dota2-liveops-platform.git)
cd dota2-liveops-platform

# 2. Install Dependencies (Virtual Env is auto-created)
uv sync

# 3. Configure Secrets
# Create a .env file with your Neon Credentials:
# DATABASE_URL="postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require"

# 4. Run Pipelines Manually
uv run etl_heroes.py
uv run etl_matches.py