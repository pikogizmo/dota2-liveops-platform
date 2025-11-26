import os
import time
import requests
from sqlalchemy import create_engine, MetaData, Table, Column, BigInteger, DateTime, func, select
from sqlalchemy.dialects.postgresql import insert, JSONB
from datetime import datetime
from dotenv import load_dotenv

# 1. Config
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
API_URL = "https://api.opendota.com/api/proMatches"
MAX_RETRO_PAGES = 5  # Safety: Max 500 matches per run to prevent infinite loops

def get_db_max_match_id(engine, matches_table):
    """Finds the newest match_id we already have in the DB."""
    try:
        with engine.connect() as conn:
            # SELECT MAX(match_id) FROM raw.pro_matches
            query = select(func.max(matches_table.c.match_id))
            result = conn.execute(query).scalar()
            return result if result is not None else 0
    except Exception:
        # If table doesn't exist yet or is empty
        return 0

def ingest_pro_matches():
    print(f"🚀 [Match ETL] Starting robust ingestion job at {datetime.now()}...")
    
    engine = create_engine(DATABASE_URL)
    metadata = MetaData(schema="raw")
    
    # Define table reference
    matches_table = Table(
        'pro_matches', metadata,
        Column('match_id', BigInteger, primary_key=True),
        Column('start_time', DateTime),
        Column('raw_data', JSONB)
    )

    # 2. Get Baseline
    current_max_id = get_db_max_match_id(engine, matches_table)
    print(f"   -> Current Max Match ID in DB: {current_max_id}")

    # 3. Pagination Loop
    last_fetched_match_id = None # Used for pagination cursor
    pages_processed = 0
    total_inserted = 0

    while pages_processed < MAX_RETRO_PAGES:
        try:
            # Prepare API Params
            params = {}
            if last_fetched_match_id:
                params['less_than_match_id'] = last_fetched_match_id
            
            print(f"   -> Fetching Page {pages_processed + 1} (Cursor: {last_fetched_match_id})...", end=" ")
            
            response = requests.get(API_URL, params=params)
            response.raise_for_status()
            matches_data = response.json()
            
            if not matches_data:
                print("Empty response. Stopping.")
                break

            print(f"Got {len(matches_data)} matches.")

            # Transform
            rows_to_insert = []
            min_batch_id = float('inf')

            for match in matches_data:
                m_id = match["match_id"]
                min_batch_id = min(min_batch_id, m_id)
                
                rows_to_insert.append({
                    "match_id": m_id,
                    "start_time": datetime.fromtimestamp(match["start_time"]),
                    "raw_data": match
                })

            # Load (Upsert)
            stmt = insert(matches_table).values(rows_to_insert)
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['match_id'],
                set_={'raw_data': stmt.excluded.raw_data, 'start_time': stmt.excluded.start_time}
            )

            with engine.begin() as conn:
                result = conn.execute(do_update_stmt)
                total_inserted += result.rowcount

            # 4. Gap Check
            # If the OLDEST match in this batch is still NEWER than our DB max,
            # it means we have a gap. We must fetch the next page.
            # If min_batch_id <= current_max_id, we have overlapped with existing data. We are safe.
            
            if min_batch_id <= current_max_id:
                print("   ✅ Gap closed. Connected to existing history.")
                break
            
            # Prepare cursor for next loop (go older)
            last_fetched_match_id = min_batch_id
            pages_processed += 1
            
            # Rate limit politeness
            time.sleep(1)

        except Exception as e:
            print(f"\n❌ Error: {e}")
            break
            
    print(f"🏁 Job Complete. Synced {total_inserted} rows across {pages_processed + 1} pages.")

if __name__ == "__main__":
    ingest_pro_matches()