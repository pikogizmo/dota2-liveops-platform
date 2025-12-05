{{ config(materialized='view') }}

with details as (
    select * from {{ source('dota_raw', 'match_details') }}
),

summary as (
    select * from {{ ref('stg_match_summary') }}
),

picks_parsed as (
    select 
        d.match_id,
        s.match_date,
        s.patch_id,
        (pb.item ->> 'hero_id')::int as hero_id,
        (pb.item ->> 'is_pick')::boolean as is_pick,
        (pb.item ->> 'order')::int as draft_order, 
        (pb.item ->> 'team')::int as team,
        
        CASE 
            WHEN (pb.item ->> 'team')::int = 0 AND s.radiant_win IS TRUE THEN TRUE
            WHEN (pb.item ->> 'team')::int = 1 AND s.radiant_win IS FALSE THEN TRUE
            ELSE FALSE
        END as is_winner

    from details d
    join summary s on d.match_id = s.match_id
    cross join lateral jsonb_array_elements(d.raw_data -> 'picks_bans') as pb(item)
)

select * from picks_parsed