import os
import requests
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String
from sqlalchemy.dialects.postgresql import insert, JSONB
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
OPENDOTA_API_KEY = os.getenv("OPENDOTA_API_KEY")
API_URL = "https://api.opendota.com/api/heroes"

def ingest_heroes():
    print("Starting hero ingestion...")

    try:
        params = {"api_key": OPENDOTA_API_KEY} if OPENDOTA_API_KEY else {}
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        heroes_data = response.json()
        print(f"Fetched {len(heroes_data)} heroes from API.")
    except Exception as e:
        print(f"API failure: {e}")
        return

    engine = create_engine(DATABASE_URL)
    metadata = MetaData(schema="raw")

    heroes_table = Table(
        'heroes', metadata,
        Column('hero_id', Integer, primary_key=True),
        Column('hero_name', String),
        Column('raw_data', JSONB)
    )

    rows_to_insert = []
    for hero in heroes_data:
        rows_to_insert.append({
            "hero_id": hero["id"],
            "hero_name": hero["localized_name"],
            "raw_data": hero
        })

    stmt = insert(heroes_table).values(rows_to_insert)
    
    do_update_stmt = stmt.on_conflict_do_update(
        index_elements=['hero_id'],
        set_={
            'hero_name': stmt.excluded.hero_name,
            'raw_data': stmt.excluded.raw_data,
        }
    )

    with engine.begin() as conn:
        result = conn.execute(do_update_stmt)
        print(f"Synced {result.rowcount} rows to raw.heroes.")

if __name__ == "__main__":
    ingest_heroes()