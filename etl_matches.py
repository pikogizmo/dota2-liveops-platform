import os
import time
import requests
from requests.exceptions import RequestException
from sqlalchemy import create_engine, MetaData, Table, Column, BigInteger, DateTime, func, select
from sqlalchemy.dialects.postgresql import insert, JSONB
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OPENDOTA_API_KEY = os.getenv("OPENDOTA_API_KEY")
API_URL = "https://api.opendota.com/api/proMatches"
MAX_RETRO_PAGES = 5

def get_db_max_match_id(engine, matches_table):
    """Retrieves the highest match_id currently stored to ensure gapless ingestion."""
    try:
        with engine.connect() as conn:
            query = select(func.max(matches_table.c.match_id))
            result = conn.execute(query).scalar()
            return result if result is not None else 0
    except SQLAlchemyError:
        return 0

def ingest_pro_matches():
    """
    Fetches pro match history from OpenDota.
    Uses pagination to bridge gaps between the last stored match and the live API feed.
    """
    print(f"🚀 [Match ETL] Job started at {datetime.now()}")
    
    engine = create_engine(DATABASE_URL)
    metadata = MetaData(schema="raw")
    
    matches_table = Table(
        'pro_matches', metadata,
        Column('match_id', BigInteger, primary_key=True),
        Column('start_time', DateTime),
        Column('raw_data', JSONB)
    )

    current_max_id = get_db_max_match_id(engine, matches_table)
    print(f"   -> Latest stored match_id: {current_max_id}")

    last_fetched_match_id = None
    pages_processed = 0
    total_inserted = 0

    while pages_processed < MAX_RETRO_PAGES:
        try:
            params = {'less_than_match_id': last_fetched_match_id} if last_fetched_match_id else {}
            if OPENDOTA_API_KEY:
                params['api_key'] = OPENDOTA_API_KEY
            
            response = requests.get(API_URL, params=params)
            response.raise_for_status()
            matches_data = response.json()
            
            if not matches_data:
                break

            # Transform & Upsert
            rows_to_insert = [
                {
                    "match_id": m["match_id"],
                    "start_time": datetime.fromtimestamp(m["start_time"]),
                    "raw_data": m
                }
                for m in matches_data
            ]
            
            # Determine the oldest match in this batch for pagination cursor
            min_batch_id = min(m["match_id"] for m in matches_data)

            stmt = insert(matches_table).values(rows_to_insert)
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['match_id'],
                set_={'raw_data': stmt.excluded.raw_data, 'start_time': stmt.excluded.start_time}
            )

            with engine.begin() as conn:
                result = conn.execute(do_update_stmt)
                total_inserted += result.rowcount

            # Integrity Check: Stop if we overlap with existing data
            if min_batch_id <= current_max_id:
                print("   ✅ Gap closed. Connected to existing history.")
                break
            
            last_fetched_match_id = min_batch_id
            pages_processed += 1
            time.sleep(1) # Rate limit compliance

        except RequestException as e:
            print(f"❌ API error during ingestion: {e}")
            break
        except SQLAlchemyError as e:
            print(f"❌ Database error during ingestion: {e}")
            break
        except (KeyError, ValueError) as e:
            print(f"❌ Data parsing error: {e}")
            break
            
    print(f"🏁 Job Complete. Synced {total_inserted} rows across {pages_processed + 1} pages.")

if __name__ == "__main__":
    ingest_pro_matches()