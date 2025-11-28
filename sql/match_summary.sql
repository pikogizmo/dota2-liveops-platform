CREATE OR REPLACE VIEW analytics.match_summary AS
SELECT 
    m.match_id,
    to_timestamp((m.raw_data ->> 'start_time')::double precision) as match_date,
    (m.raw_data ->> 'duration')::int as duration_seconds,
    (m.raw_data ->> 'radiant_win')::boolean as radiant_win,
    (m.raw_data ->> 'patch')::int as patch_id,
    m.ingested_at
FROM raw.match_details m;