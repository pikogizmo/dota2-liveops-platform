"""
WARNING: Local execution only. Do not run in GitHub Actions due to timeouts.
"""

import time
import requests
import os
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Configuration
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Constants
PATCH_START_TIME = 1759363200  # Oct 2, 2025 UTC - the start of 7.39e
TARGET_PATCH_ID = 58

def get_db_engine():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment variables")
    return create_engine(DATABASE_URL)

def fetch_matches(less_than_match_id=None):
    url = "https://api.opendota.com/api/proMatches"
    params = {}
    if less_than_match_id:
        params['less_than_match_id'] = less_than_match_id
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching matches: {e}")
        return []

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
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching details for match {match_id}: {e}")
        return None

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
    
    print(f"Starting backfill for patch 7.39e (Start Time: {PATCH_START_TIME})")
    
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
            
            # Check which ones are missing
            match_ids = [m['match_id'] for m in valid_matches_found]

            for match in valid_matches_found:
                match_id = match['match_id']
                
                # Check if exists
                exists = False
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT 1 FROM raw.match_details WHERE match_id = :match_id"), {"match_id": match_id})
                    if result.fetchone():
                        exists = True
                
                if exists:
                    print(f"Match {match_id} details already exist. Skipping.")
                    continue
                
                print(f"Fetching details for {match_id}...")
                details = fetch_match_details(match_id)
                if details:
                    save_match_details(engine, details)
                
                time.sleep(1.5)
                
    print("Done.")

if __name__ == "__main__":
    main()
