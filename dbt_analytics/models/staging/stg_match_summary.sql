{{ config(materialized='view') }}

with source as (
    select * from {{ source('dota_raw', 'match_details') }}
),

flattened as (
    select
        match_id,
        to_timestamp((raw_data ->> 'start_time')::double precision) as match_date,
        (raw_data ->> 'duration')::int as duration_seconds,
        (raw_data ->> 'radiant_win')::boolean as radiant_win,
        (raw_data ->> 'patch')::int as patch_id,
        ingested_at
    from source
)

select * from flattened