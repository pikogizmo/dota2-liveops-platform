import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, StratifiedKFold
from dotenv import load_dotenv
import tomllib

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

with open("patch_config.toml", "rb") as f:
    config = tomllib.load(f)

ALL_PATCHES = [config["current_meta"]] + config.get("patch_history", [])


def build_features(raw_df):
    """
    Build feature matrix using differential encoding.
    Each hero gets +1 if on radiant, -1 if on dire.
    """
    heroes = sorted(raw_df['hero_id'].unique())
    grouped = raw_df.groupby('match_id')
    
    data = []
    labels = []
    
    for match_id, group in grouped:
        radiant = set(group[group['team'] == 0]['hero_id'])
        dire = set(group[group['team'] == 1]['hero_id'])
        
        row = {}
        for h in heroes:
            if h in radiant:
                row[str(h)] = 1
            elif h in dire:
                row[str(h)] = -1
            else:
                row[str(h)] = 0
        
        data.append(row)
        labels.append(1 if group.iloc[0]['radiant_win'] else 0)
    
    X = pd.DataFrame(data).fillna(0)
    y = np.array(labels)
    
    return X, y, heroes


def train_for_patch(patch):
    """
    Trains an ensemble model for a specific patch.
    Outputs hero coefficients showing impact on win probability.
    """
    patch_name = patch['patch_name']
    start_ts = patch['start_timestamp']
    end_ts = patch.get('end_timestamp')
    patch_id = patch['patch_id']
    
    print(f"\nTraining model for patch {patch_name}...")
    engine = create_engine(DATABASE_URL)

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

    if raw_df.empty or len(raw_df['match_id'].unique()) < 50:
        print(f"Insufficient training data for {patch_name}.")
        return

    n_matches = len(raw_df['match_id'].unique())
    print(f"   -> Building features from {n_matches} matches...")
    X, y, heroes = build_features(raw_df)
    print(f"   -> Feature matrix: {X.shape[0]} samples, {X.shape[1]} heroes")

    # Ensemble classifier
    xgb = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, random_state=42, eval_metric='logloss', verbosity=0
    )
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=5, random_state=42, n_jobs=-1
    )
    gb = GradientBoostingClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.1, random_state=42
    )
    lr = LogisticRegression(max_iter=2000, C=0.5, random_state=42)

    ensemble = VotingClassifier(
        estimators=[('xgb', xgb), ('rf', rf), ('gb', gb), ('lr', lr)],
        voting='soft'
    )

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    print("   -> Testing classifiers...")
    for name, clf in [('XGBoost', xgb), ('RandomForest', rf), ('GradientBoosting', gb), ('LogisticReg', lr)]:
        scores = cross_val_score(clf, X, y, cv=cv, scoring='accuracy')
        print(f"      {name}: {scores.mean():.2%} (±{scores.std():.2%})")
    
    ensemble_scores = cross_val_score(ensemble, X, y, cv=cv, scoring='accuracy')
    print(f"   => Ensemble Accuracy: {ensemble_scores.mean():.2%} (±{ensemble_scores.std():.2%})")

    # Train LR for coefficient extraction (interpretable hero weights)
    lr.fit(X, y)
    
    name_query = "SELECT hero_id, hero_name FROM raw.heroes"
    with engine.connect() as conn:
        names_df = pd.read_sql(name_query, conn)
    id_to_name = dict(zip(names_df.hero_id, names_df.hero_name))

    coefs = lr.coef_[0]
    weights_df = pd.DataFrame([
        {'hero_name': id_to_name.get(int(col), col), 'coefficient': coefs[i]}
        for i, col in enumerate(X.columns)
    ])
    weights_df = weights_df.sort_values(by='coefficient', ascending=False)
    
    output_file = f"draft_weights_{patch_id}.csv"
    weights_df.to_csv(output_file, index=False)
    print(f"   -> Draft weights saved to {output_file}")

    print("\n-- TOP RADIANT ADVANTAGE HEROES --")
    print(weights_df.head(5).to_string(index=False))
    print("\n-- TOP DIRE ADVANTAGE HEROES --")
    print(weights_df.tail(5).to_string(index=False))


if __name__ == "__main__":
    for patch in ALL_PATCHES:
        train_for_patch(patch)