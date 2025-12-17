import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from dotenv import load_dotenv
import tomllib

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Load config
with open("patch_config.toml", "rb") as f:
    config = tomllib.load(f)

# Construct list of all patches (current + history)
ALL_PATCHES = [config["current_meta"]] + config.get("patch_history", [])

def train_for_patch(patch):
    """
    Trains a Logistic Regression model for a specific patch.
    """
    patch_name = patch['patch_name']
    start_ts = patch['start_timestamp']
    end_ts = patch.get('end_timestamp') # None for current
    patch_id = patch['patch_id']
    
    print(f"🧠 Training model for patch {patch_name}...")
    engine = create_engine(DATABASE_URL)

    # Date filter logic
    if end_ts:
        date_clause = "m.match_date >= to_timestamp(%(start_ts)s) AND m.match_date <= to_timestamp(%(end_ts)s)"
        params = {"start_ts": start_ts, "end_ts": end_ts}
    else:
        date_clause = "m.match_date >= to_timestamp(%(start_ts)s)"
        params = {"start_ts": start_ts}

    query = f"""
    SELECT m.match_id, m.radiant_win, pb.hero_id, pb.team
    FROM analytics.match_summary m
    JOIN analytics.picks_bans pb ON m.match_id = pb.match_id
    WHERE pb.is_pick IS TRUE
    AND {date_clause};
    """
    
    with engine.connect() as conn:
        raw_df = pd.read_sql(query, conn, params=params)

    if raw_df.empty:
        print(f"❌ Insufficient training data for {patch_name}.")
        return

    # Pivot data for one-hot encoding
    print(f"   -> Feature engineering on {len(raw_df)} draft events...")
    
    matches = raw_df['match_id'].unique()
    heroes = sorted(raw_df['hero_id'].unique())
    
    data, labels = [], []
    grouped = raw_df.groupby('match_id')
    
    for _, group in grouped:
        row = {h: 0 for h in heroes}
        for _, pick in group.iterrows():
            row[pick['hero_id']] = 1 if pick['team'] == 0 else -1
        
        data.append(row)
        labels.append(1 if group.iloc[0]['radiant_win'] else 0)

    X = pd.DataFrame(data).fillna(0)
    y = np.array(labels)

    # Hero name lookup
    name_query = "SELECT hero_id, hero_name FROM raw.heroes"
    with engine.connect() as conn:
        names_df = pd.read_sql(name_query, conn)
    id_to_name = dict(zip(names_df.hero_id, names_df.hero_name))

    # Train model
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)

    # Evaluate accuracy
    acc = accuracy_score(y_test, model.predict(X_test))
    print(f"🎯 Model Accuracy: {acc:.2%}")

    # Analyze feature importance
    print("\n🔮 -- DRAFT WEIGHT ANALYSIS --")
    coefs = pd.Series(model.coef_[0], index=X.columns)
    
    # Create DataFrame for export
    weights_df = pd.DataFrame({
        'hero_name': [id_to_name.get(h_id, str(h_id)) for h_id in coefs.index],
        'coefficient': coefs.values
    })
    
    weights_df = weights_df.sort_values(by='coefficient', ascending=False)
    
    output_file = f"draft_weights_{patch_id}.csv"
    weights_df.to_csv(output_file, index=False)
    print(f"✅ Draft weights saved to {output_file}")

    print("🏆 Top 5 Radiant Advantages:")
    print(weights_df.head(5))
    
    print("\n💀 Top 5 Radiant Disadvantages:")
    print(weights_df.tail(5))

if __name__ == "__main__":
    for patch in ALL_PATCHES:
        train_for_patch(patch)