import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine, text
from adjustText import adjust_text
from dotenv import load_dotenv

# 1. Config
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def generate_meta_chart():
    print("🎨 Generating Meta Snapshot...")
    
    # 2. Fetch Data (The same logic as your SQL View)
    engine = create_engine(DATABASE_URL)
    
    query = """
    SELECT 
        h.hero_name,
        count(*) as total_picks,
        round(avg(case when pb.is_winner then 1 else 0 end) * 100, 2) as win_rate
    FROM analytics.picks_bans pb
    JOIN raw.heroes h ON h.hero_id = pb.hero_id
    WHERE pb.is_pick IS TRUE
    GROUP BY h.hero_name
    HAVING count(*) > 5  -- Only show heroes with decent sample size
    ORDER BY total_picks DESC;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    if df.empty:
        print("❌ Not enough data to plot yet!")
        return

    # 3. Plotting Setup
    plt.figure(figsize=(12, 8))
    sns.set_style("darkgrid")
    
    # Scatter Plot
    sns.scatterplot(
        data=df, 
        x="total_picks", 
        y="win_rate", 
        s=100, 
        color="#2ecc71", 
        edgecolor="black", 
        alpha=0.7
    )
    
    # 4. Add Labels (Smartly)
    texts = []
    for i, row in df.iterrows():
        texts.append(plt.text(row['total_picks'], row['win_rate'], row['hero_name'], fontsize=9))
    
    adjust_text(texts, arrowprops=dict(arrowstyle='-', color='gray', alpha=0.5))

    # 5. Decoration
    plt.title(f"Dota 2 Pro Meta: Win Rate vs. Popularity (n={len(df)} heroes)", fontsize=16, fontweight='bold')
    plt.xlabel("Total Picks (Popularity)", fontsize=12)
    plt.ylabel("Win Rate %", fontsize=12)
    plt.axhline(50, color='red', linestyle='--', alpha=0.5, label="50% Win Rate")
    plt.legend()
    
    # 6. Save
    output_file = "meta_snapshot.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✅ Chart saved to {output_file}")

if __name__ == "__main__":
    generate_meta_chart()