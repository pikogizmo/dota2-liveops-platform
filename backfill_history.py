"""
WARNING: Local execution only. Do not run in GitHub Actions due to timeouts.
"""

import time
import requests
import os
import json
import concurrent.futures
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Configuration
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
OPENDOTA_API_KEY = os.getenv("OPENDOTA_API_KEY")

# Constants
PATCH_START_TIME = 1765843200  # Dec 16, 2025 UTC - the start of 7.40
TARGET_PATCH_ID = 59

def get_db_engine():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment variables")
    return create_engine(DATABASE_URL)

def make_request_with_retry(url, params=None, max_retries=3):
    if params is None:
        params = {}
    if OPENDOTA_API_KEY:
        params['api_key'] = OPENDOTA_API_KEY
        
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params)
            
            if response.status_code == 429:
                wait_time = 60 * (2 ** attempt) # 60s, 120s, 240s
                print(f"⚠️ Rate limit hit (429). Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                continue
                
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            print(f"Error making request: {e}")
            return None
            
    print("❌ Max retries exceeded.")
    return None

def fetch_matches(less_than_match_id=None):
    url = "https://api.opendota.com/api/proMatches"
    params = {}
    if less_than_match_id:
        params['less_than_match_id'] = less_than_match_id
    
    return make_request_with_retry(url, params)

def save_matches(engine, matches):
    if not matches:
        return 0
        
    upsert_query = text("""
        INSERT INTO raw.pro_matches (
            match_id, start_time, raw_data
        ) VALUES (
            :match_id, to_timestamp(:start_time), :raw_data
        )
        ON CONFLICT (match_id) DO NOTHING;
    """)
    
    params = []
    for match in matches:
        params.append({
            'match_id': match.get('match_id'),
            'start_time': match.get('start_time'),
            'raw_data': json.dumps(match)
        })

    count = 0
    try:
        with engine.begin() as conn:
            result = conn.execute(upsert_query, params)
            count = len(params)
    except Exception as e:
        print(f"Error saving batch: {e}")
        
    return count

def fetch_match_details(match_id):
    url = f"https://api.opendota.com/api/matches/{match_id}"
    return make_request_with_retry(url)

def save_match_details(engine, match_data):
    if not match_data:
        return
    
    upsert_query = text("""
        INSERT INTO raw.match_details (match_id, raw_data) 
        VALUES (:match_id, :raw_data)
        ON CONFLICT (match_id) DO UPDATE SET raw_data = EXCLUDED.raw_data;
    """)
    
    try:
        with engine.begin() as conn:
            conn.execute(upsert_query, {
                'match_id': match_data['match_id'],
                'raw_data': json.dumps(match_data)
            })
    except Exception as e:
        print(f"Error saving details for match {match_data.get('match_id')}: {e}")

def main():
    engine = get_db_engine()
    
    print(f"Starting backfill for patch 7.40 (Start Time: {PATCH_START_TIME})")
    
    last_match_id = None
    valid_matches_found = []
    
    while True:
        print(f"Fetching batch starting from {last_match_id if last_match_id else 'latest'}...")
        matches = fetch_matches(last_match_id)
        
        if not matches:
            print("No more matches found or error occurred.")
            break
            
        batch_valid_matches = []
        stop_loop = False
        
        for match in matches:
            start_time = match.get('start_time', 0)
            if start_time >= PATCH_START_TIME:
                batch_valid_matches.append(match)
                valid_matches_found.append(match)
            else:
                stop_loop = True
                break
        
        if batch_valid_matches:
            count = save_matches(engine, batch_valid_matches)
            print(f"Processed {len(batch_valid_matches)} matches. Saved/Ignored successfully.")
            
        if stop_loop:
            print("Reached matches before patch start time. Stopping ingestion.")
            break
            
        if matches:
            last_match_id = matches[-1]['match_id']
        
        time.sleep(1.5)
        
    print(f"Total valid matches found: {len(valid_matches_found)}")
    
    # Hydration
    if valid_matches_found:
        response = input(f"Hydrate details for these {len(valid_matches_found)} matches? [y/N] ").strip().lower()
        if response == 'y':
            print("Hydrating match details...")
            
            # Batch check for existing matches
            match_ids = [m['match_id'] for m in valid_matches_found]
            existing_ids = set()
            
            print("Checking for existing match details...")
            chunk_size = 500
            for i in range(0, len(match_ids), chunk_size):
                chunk = match_ids[i:i + chunk_size]
                if not chunk: continue
                
                with engine.connect() as conn:
                    # Use ANY for array comparison which is cleaner in Postgres
                    result = conn.execute(
                        text("SELECT match_id FROM raw.match_details WHERE match_id = ANY(:ids)"), 
                        {"ids": chunk}
                    )
                    existing_ids.update(row[0] for row in result)
            
            matches_to_fetch = [m for m in valid_matches_found if m['match_id'] not in existing_ids]
            print(f"Found {len(matches_to_fetch)} matches missing details.")
            
            if not matches_to_fetch:
                print("All matches already hydrated.")
            else:
                def process_match(match):
                    match_id = match['match_id']
                    print(f"Fetching details for {match_id}...", end=" ", flush=True)
                    details = fetch_match_details(match_id)
                    if details:
                        save_match_details(engine, details)
                        print(f"Saved {match_id}.")
                    else:
                        print(f"Failed {match_id}.")

                # Use threading to speed up fetching
                max_workers = 10
                print(f"Starting concurrent fetch with {max_workers} threads...")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(process_match, m) for m in matches_to_fetch]
                    concurrent.futures.wait(futures)
                
    print("Done.")

if __name__ == "__main__":
    main()
