import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from dotenv import load_dotenv

# 1. Config
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def train_and_predict():
    print("🧠 Starting Model Training...")
    engine = create_engine(DATABASE_URL)

    # 2. Fetch Training Data (Pivot Table)
    # We need: Match ID, Radiant Win, and the list of heroes on each team
    query = """
    SELECT 
        m.match_id,
        m.radiant_win,
        pb.hero_id,
        pb.team -- 0 for Radiant, 1 for Dire
    FROM analytics.match_summary m
    JOIN analytics.picks_bans pb ON m.match_id = pb.match_id
    WHERE pb.is_pick IS TRUE;
    """
    
    with engine.connect() as conn:
        raw_df = pd.read_sql(query, conn)

    if raw_df.empty:
        print("❌ Not enough data to train!")
        return

    # 3. Feature Engineering (The "Pivot")
    # We want 1 row per match. Columns = Hero IDs. Values = 1 (Radiant), -1 (Dire)
    print(f"   -> Processing {len(raw_df)} pick events...")
    
    matches = raw_df['match_id'].unique()
    heroes = raw_df['hero_id'].unique()
    heroes.sort()
    
    data = []
    labels = []
    
    # This loop is slow for big data, but fine for <10k matches
    # (For production, we would do this pivot in SQL or Matrix math)
    grouped = raw_df.groupby('match_id')
    
    for match_id, group in grouped:
        # Create a zero vector for all known heroes
        row = {h: 0 for h in heroes}
        
        # Fill in +1 for Radiant, -1 for Dire
        for _, pick in group.iterrows():
            if pick['team'] == 0:
                row[pick['hero_id']] = 1
            else:
                row[pick['hero_id']] = -1
        
        data.append(row)
        # Target: 1 if Radiant Won, 0 if Dire Won
        labels.append(1 if group.iloc[0]['radiant_win'] else 0)

    X = pd.DataFrame(data).fillna(0)
    y = np.array(labels)

    print(f"   -> Dataset shape: {X.shape}")

    # Create a mapping dictionary: {1: 'Anti-Mage', 14: 'Pudge', ...}
    # We query the DB for this
    name_query = "SELECT hero_id, hero_name FROM raw.heroes"
    with engine.connect() as conn:
        names_df = pd.read_sql(name_query, conn)
    id_to_name = dict(zip(names_df.hero_id, names_df.hero_name))

    # 4. Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 5. Train Model
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)

    # 6. Evaluate
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"🎯 Model Accuracy: {acc:.2%}")

    # 7. Interactive Prediction
    print("\n🔮 -- PREDICTION TIME --")
    coefs = pd.Series(model.coef_[0], index=X.columns).sort_values(ascending=False)

    print("🏆 Top 5 'Win Conditions' (Radiant):")
    for hero_id, weight in coefs.head(5).items():
        name = id_to_name.get(hero_id, f"Unknown ({hero_id})")
        print(f"   {name:<20} : {weight:+.4f}")
        
    print("\n💀 Top 5 'Loss Conditions' (Radiant):")
    for hero_id, weight in coefs.tail(5).items():
        name = id_to_name.get(hero_id, f"Unknown ({hero_id})")
        print(f"   {name:<20} : {weight:+.4f}")

if __name__ == "__main__":
    train_and_predict()