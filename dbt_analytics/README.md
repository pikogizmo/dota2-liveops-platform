# dbt Analytics

Transformation layer for the Dota 2 LiveOps pipeline. Converts raw JSON match data into analytics-ready views.

## Models

- `stg_match_summary` - One row per match with outcome stats
- `stg_picks_bans` - One row per draft event (pick/ban)

## Usage

```bash
export $(grep -v '^#' .env | xargs)
uv run dbt run --project-dir dbt_analytics
uv run dbt test --project-dir dbt_analytics
```
