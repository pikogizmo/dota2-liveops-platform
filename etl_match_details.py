import os
import time
import requests
from sqlalchemy import create_engine, text, MetaData, Table, Column, BigInteger
from sqlalchemy.dialects.postgresql import insert, JSONB
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
API_BASE_URL = "https://api.opendota.com/api/matches"
DELAY_SECONDS = 1.2
BATCH_SIZE = 60

def ingest_match_details():
    """
    Identifies matches missing detailed replay data (picks/bans, items)
    and fetches them incrementally.
    """
    print("🚀 [Details ETL] Job started...")
    
    engine = create_engine(DATABASE_URL)
    
    # Identify gaps in the match_details table
    query = text(f"""
        SELECT p.match_id 
        FROM raw.pro_matches p
        LEFT JOIN raw.match_details d ON p.match_id = d.match_id
        WHERE d.match_id IS NULL
        ORDER BY p.start_time DESC
        LIMIT {BATCH_SIZE};
    """)
    
    with engine.connect() as conn:
        missing_ids = [row[0] for row in conn.execute(query)]
    
    if not missing_ids:
        print("✅ System up to date.")
        return

    print(f"📦 Batch processing {len(missing_ids)} matches...")

    metadata = MetaData(schema="raw")
    details_table = Table(
        'match_details', metadata,
        Column('match_id', BigInteger, primary_key=True),
        Column('raw_data', JSONB)
    )

    processed_count = 0
    
    for match_id in missing_ids:
        try:
            print(f"   -> Processing {match_id}...", end=" ", flush=True)
            
            response = requests.get(f"{API_BASE_URL}/{match_id}")
            
            if response.status_code == 429:
                print("⚠️ Rate limit reached. Aborting batch.")
                break
            
            if response.status_code == 404:
                print("❌ Match not found/expired.")
                continue

            response.raise_for_status()
            
            stmt = insert(details_table).values(
                match_id=match_id,
                raw_data=response.json()
            ).on_conflict_do_nothing()
            
            with engine.begin() as conn:
                conn.execute(stmt)
                
            print("Done.")
            processed_count += 1
            time.sleep(DELAY_SECONDS)
            
        except Exception as e:
            print(f"❌ Failed: {e}")

    print(f"🏁 Batch complete: {processed_count}/{len(missing_ids)} processed.")

if __name__ == "__main__":
    ingest_match_details()