CREATE OR REPLACE VIEW analytics.picks_bans AS
SELECT 
    d.match_id,
    m.match_date,
    m.patch_id,
    (pb.item ->> 'hero_id')::int as hero_id,
    (pb.item ->> 'is_pick')::boolean as is_pick,
    (pb.item ->> 'order')::int as draft_order, 
    (pb.item ->> 'team')::int as team,
    CASE 
        WHEN (pb.item ->> 'team')::int = 0 AND m.radiant_win IS TRUE THEN TRUE
        WHEN (pb.item ->> 'team')::int = 1 AND m.radiant_win IS FALSE THEN TRUE
        ELSE FALSE
    END as is_winner
FROM raw.match_details d
JOIN analytics.match_summary m ON d.match_id = m.match_id
CROSS JOIN LATERAL jsonb_array_elements(d.raw_data -> 'picks_bans') as pb(item);