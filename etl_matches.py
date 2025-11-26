import os
import requests
from sqlalchemy import create_engine, MetaData, Table, Column, BigInteger, DateTime
from sqlalchemy.dialects.postgresql import insert, JSONB  # <--- Moved JSONB here
from datetime import datetime
from dotenv import load_dotenv

# 1. Config
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
API_URL = "https://api.opendota.com/api/proMatches"

def ingest_pro_matches():
    print(f"🚀 [Match ETL] Starting job at {datetime.now()}...")

    # 2. Extract
    try:
        print("   -> Fetching latest matches from OpenDota...")
        response = requests.get(API_URL)
        response.raise_for_status()
        matches_data = response.json()
        print(f"   -> API returned {len(matches_data)} matches.")
    except Exception as e:
        print(f"❌ API Error: {e}")
        return

    # 3. Transform
    rows_to_insert = []
    for match in matches_data:
        rows_to_insert.append({
            "match_id": match["match_id"],
            "start_time": datetime.fromtimestamp(match["start_time"]),
            "raw_data": match
        })

    if not rows_to_insert:
        print("   -> No data to insert.")
        return

    # 4. Load
    engine = create_engine(DATABASE_URL)
    metadata = MetaData(schema="raw")
    
    matches_table = Table(
        'pro_matches', metadata,
        Column('match_id', BigInteger, primary_key=True),
        Column('start_time', DateTime),
        Column('raw_data', JSONB)
    )

    # Upsert Logic
    stmt = insert(matches_table).values(rows_to_insert)
    
    do_update_stmt = stmt.on_conflict_do_update(
        index_elements=['match_id'],
        set_={
            'raw_data': stmt.excluded.raw_data,
            'start_time': stmt.excluded.start_time
        }
    )

    try:
        with engine.begin() as conn:
            result = conn.execute(do_update_stmt)
            print(f"✅ [Match ETL] Success! Processed {result.rowcount} rows.")
    except Exception as e:
        print(f"❌ Database Error: {e}")

if __name__ == "__main__":
    ingest_pro_matches()