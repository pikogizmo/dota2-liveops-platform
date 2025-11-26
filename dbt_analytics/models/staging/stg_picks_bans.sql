{{ config(materialized='view') }}

with details as (
    -- Get the raw JSON
    select * from {{ source('dota_raw', 'match_details') }}
),

summary as (
    -- Get the cleaned metadata from our previous model
    -- dbt builds a "Dependency Graph" here
    select * from {{ ref('stg_match_summary') }}
),

picks_parsed as (
    select 
        d.match_id,
        s.match_date,
        s.patch_id,
        
        -- Extract fields from the JSON array object
        (pb.item ->> 'hero_id')::int as hero_id,
        (pb.item ->> 'is_pick')::boolean as is_pick,
        (pb.item ->> 'order')::int as draft_order, 
        (pb.item ->> 'team')::int as team, -- 0 = Radiant, 1 = Dire
        
        -- Calculate Winner Logic
        CASE 
            WHEN (pb.item ->> 'team')::int = 0 AND s.radiant_win IS TRUE THEN TRUE
            WHEN (pb.item ->> 'team')::int = 1 AND s.radiant_win IS FALSE THEN TRUE
            ELSE FALSE
        END as is_winner

    from details d
    -- Join to our clean summary model
    join summary s on d.match_id = s.match_id
    -- The Array Explosion
    cross join lateral jsonb_array_elements(d.raw_data -> 'picks_bans') as pb(item)
)

select * from picks_parsed