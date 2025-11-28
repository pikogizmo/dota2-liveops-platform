import os
import requests
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String
from sqlalchemy.dialects.postgresql import insert, JSONB
from dotenv import load_dotenv

# 1. Setup & Config
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
API_URL = "https://api.opendota.com/api/heroes"

def ingest_heroes():
    print("🚀 Starting Hero Ingestion...")

    # 2. Extract (Fetch from API)
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        heroes_data = response.json()
        print(f"📦 Fetched {len(heroes_data)} heroes from API.")
    except Exception as e:
        print(f"❌ API Failure: {e}")
        return

    # 3. Connect to DB
    engine = create_engine(DATABASE_URL)
    metadata = MetaData(schema="raw")

    # Define the table target (reflection ensures we match the DB)
    # We define it explicitly here to access the column objects for the upsert logic
    heroes_table = Table(
        'heroes', metadata,
        Column('hero_id', Integer, primary_key=True),
        Column('hero_name', String),
        Column('raw_data', JSONB)
    )

    # 4. Prepare the Payload
    # We map the API JSON to our Table Columns
    rows_to_insert = []
    for hero in heroes_data:
        rows_to_insert.append({
            "hero_id": hero["id"],
            "hero_name": hero["localized_name"],
            "raw_data": hero  # Dump the whole JSON object here
        })

    # 5. Load (The Upsert Logic)
    # This reads: "Insert these rows. If hero_id exists, update the name and data instead."
    stmt = insert(heroes_table).values(rows_to_insert)
    
    do_update_stmt = stmt.on_conflict_do_update(
        index_elements=['hero_id'], # The Primary Key
        set_={
            'hero_name': stmt.excluded.hero_name,
            'raw_data': stmt.excluded.raw_data,
            # We don't touch 'ingested_at' so we know when the original record was created,
            # OR we could update it to track 'last_updated'. Let's leave it for now.
        }
    )

    with engine.begin() as conn:
        result = conn.execute(do_update_stmt)
        print(f"✅ Success! Synced {result.rowcount} rows to raw.heroes.")

if __name__ == "__main__":
    ingest_heroes()