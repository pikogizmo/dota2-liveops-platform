# 🏗️ System Architecture & Engineering Runbook

## 1. The High-Level Stack
* **Compute (Local):** WSL2 (Ubuntu) + Python 3.11 + `uv` (Package Manager).
* **Compute (Cloud):** GitHub Actions (Serverless Runners).
* **Storage:** Neon PostgreSQL (Serverless, Autoscaling).
* **Orchestration:** GitHub Actions Cron (`.github/workflows/hourly_etl.yml`).
* **Transformation:** dbt Core (`dbt_analytics/`).

## 2. Data Flow Diagram
[API: OpenDota] -> [Python ETL Scripts] -> [Neon DB (Raw Schema)] -> [dbt (Staging Schema)] -> [dbt (Tests)] -> [Viz/ML Scripts] -> [GitHub Repo (README/Assets)]

## 3. The "Secret" Configuration Map
This is the most confusing part. Here is how the system authenticates.

### A. Local Development (Your Laptop)
* **File:** `.env` (in project root).
* **Status:** Gitignored (NEVER commit this).
* **Content:**
    ```ini
    DATABASE_URL="postgresql://neondb_owner:..."
    DBT_HOST="..."
    DBT_USER="..."
    DBT_PASSWORD="..."
    ```
* **How Python reads it:** `load_dotenv()` loads it into memory.
* **How dbt reads it:** You must run `export $(grep -v '^#' .env | xargs)` before running dbt debug commands, OR rely on `profiles.yml` logic.

### B. Production (GitHub Actions)
* **Location:** GitHub Repo -> Settings -> Secrets and variables -> Actions.
* **Secret Name:** `DATABASE_URL`.
* **How it works:** The YAML file injects this secret into the runner environment:
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