# 🏗️ System Architecture & Engineering Runbook

## 1. High-Level Stack
* **Compute (Local):** WSL2 (Ubuntu) + Python 3.11 + `uv` (Package Manager).
* **Compute (Cloud):** GitHub Actions (Serverless Runners).
* **Storage:** Neon PostgreSQL (Serverless, Autoscaling).
* **Orchestration:** GitHub Actions Cron (`.github/workflows/hourly_etl.yml`).
* **Transformation:** dbt Core (`dbt_analytics/`).
* **Presentation:** GitHub Pages (Static Hosting).

## 2. Data Flow Diagram
[API: OpenDota] -> [Python ETL Scripts] -> [Neon DB (Raw Schema)] -> [dbt (Staging Schema)] -> [Viz Scripts] -> [GitHub Pages (Dashboard)]

## 3. Configuration & Authentication

### A. Local Development
* **File:** `.env` (in project root).
* **Status:** Gitignored.
* **Content:**
    ```ini
    DATABASE_URL="postgresql://neondb_owner:..."
    DBT_HOST="..."
    DBT_USER="..."
    DBT_PASSWORD="..."
    ```
* **Usage:** `load_dotenv()` loads variables into memory for Python scripts. For dbt, variables must be exported to the environment.

### B. Production (GitHub Actions)
* **Location:** GitHub Repo Secrets.
* **Secret Name:** `DATABASE_URL`.
* **Usage:** Injected into the runner environment via workflow configuration:
    ```yaml
    env:
      DATABASE_URL: ${{ secrets.DATABASE_URL }}
    ```

## 4. Key Engineering Patterns

### Idempotency (Upsert)
* **Problem:** If the pipeline runs twice, we don't want duplicate matches.
* **Solution:** We use `stmt.on_conflict_do_update(index_elements=['match_id'])`.
* **Where:** `etl_matches.py` and `etl_match_details.py`.

### Gap-Filling (Pagination)
* **Problem:** If the pipeline crashes for 4 hours, we miss data.
* **Solution:** The script checks `MAX(match_id)` in the DB. If the API returns matches *newer* than our DB max, it keeps fetching older pages until the gap is closed.
* **Where:** `etl_matches.py`.

### The "Left Join" To-Do List
* **Problem:** How do we track which matches need detailed parsing?
* **Solution:** We select matches present in `pro_matches` but NULL in `match_details`.
* **Where:** `etl_match_details.py`.

## 5. Troubleshooting Cheat Sheet

**Scenario: "Connection Refused"**
* **Cause:** Password changed, or Neon project paused.
* **Fix:** Check Neon Console. Check `.env` locally. Check GitHub Secrets for Prod.

**Scenario: "Pipeline Green, but No New Data"**
* **Cause:** OpenDota API might be stale or Rate Limited (429).
* **Check:** Look at GitHub Action logs. If "Rate Limit Hit", wait 1 hour.

**Scenario: "dbt Error: Relation does not exist"**
* **Cause:** You changed a table name in Raw but didn't update the dbt `source` or `model`.
* **Fix:** Update `dbt_analytics/models/sources.yml` or the `.sql` files.

## 6. Command Reference

# Update dependencies
uv sync

# Run ETL manually
uv run etl_heroes.py
uv run etl_matches.py
uv run etl_match_details.py

# dbt Workflow
export $(grep -v '^#' .env | xargs)  # Load secrets
uv run dbt run --project-dir dbt_analytics
uv run dbt test --project-dir dbt_analytics