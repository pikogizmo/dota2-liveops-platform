import os
import time
import requests
from sqlalchemy import create_engine, text, MetaData, Table, Column, BigInteger
from sqlalchemy.dialects.postgresql import insert, JSONB
from dotenv import load_dotenv

# 1. Config
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
API_BASE_URL = "https://api.opendota.com/api/matches"
DELAY_SECONDS = 1.0  # Polite delay to avoid rate limits
BATCH_SIZE = 20      # How many matches to process per run

def ingest_match_details():
    print("🚀 [Details ETL] Starting job...")
    
    engine = create_engine(DATABASE_URL)
    
    # 2. Identify Missing Matches
    # Logic: Find IDs in 'pro_matches' that are NOT yet in 'match_details'
    query = text(f"""
        SELECT p.match_id 
        FROM raw.pro_matches p
        LEFT JOIN raw.match_details d ON p.match_id = d.match_id
        WHERE d.match_id IS NULL
        ORDER BY p.start_time DESC
        LIMIT {BATCH_SIZE};
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query)
        # Convert list of tuples [(123,), (456,)] to list of ints [123, 456]
        missing_ids = [row[0] for row in result]
    
    if not missing_ids:
        print("✅ [Details ETL] Up to date. No new matches to fetch.")
        return

    print(f"📦 Found {len(missing_ids)} matches needing details. Processing batch...")

    # 3. Loop and Fetch
    metadata = MetaData(schema="raw")
    details_table = Table(
        'match_details', metadata,
        Column('match_id', BigInteger, primary_key=True),
        Column('raw_data', JSONB)
    )

    processed_count = 0
    
    for match_id in missing_ids:
        try:
            print(f"   -> Fetching details for {match_id}...", end=" ", flush=True)
            
            # Call API
            url = f"{API_BASE_URL}/{match_id}"
            response = requests.get(url)
            
            # Handle Rate Limits (429)
            if response.status_code == 429:
                print("⚠️ Rate Limit Hit! Stopping batch early.")
                break
            
            # Allow 404s (sometimes matches get deleted), just skip them
            if response.status_code == 404:
                print("❌ Match not found (404). Skipping.")
                continue

            response.raise_for_status()
            data = response.json()
            
            # Insert immediately (one by one is safer for large blobs)
            stmt = insert(details_table).values(
                match_id=match_id,
                raw_data=data
            ).on_conflict_do_nothing() 
            
            with engine.begin() as conn:
                conn.execute(stmt)
                
            print("Done. ✅")
            processed_count += 1
            
            # Sleep to respect API limits
            time.sleep(DELAY_SECONDS)
            
        except Exception as e:
            print(f"❌ Failed: {e}")

    print(f"🏁 [Details ETL] Batch complete. Processed {processed_count}/{len(missing_ids)} matches.")

if __name__ == "__main__":
    ingest_match_details()