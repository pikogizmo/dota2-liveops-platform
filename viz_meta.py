import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from sqlalchemy import create_engine
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
    HAVING count(*) > 12  -- Only show heroes with decent sample size
    ORDER BY total_picks DESC;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    if df.empty:
        print("❌ Not enough data to plot yet!")
        return

    # --- A. Static Plot (Optimized for README) ---
    print("   ... Generating Static Image (Cleaned)")
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
    
    # Label Strategy: Top 20 Popular + Top 5 Highest Win Rate
    # This avoids the "collision" mess in the static image
    top_picks = df.nlargest(20, 'total_picks')['hero_name'].tolist()
    top_wins = df.nlargest(5, 'win_rate')['hero_name'].tolist()
    heroes_to_label = set(top_picks + top_wins)

    texts = []
    for i, row in df.iterrows():
        if row['hero_name'] in heroes_to_label:
            texts.append(plt.text(row['total_picks'], row['win_rate'], row['hero_name'], fontsize=9, fontweight='bold'))
    
    adjust_text(texts, arrowprops=dict(arrowstyle='-', color='gray', alpha=0.5))

    # Decoration
    plt.title(f"Dota 2 Pro Meta: Win Rate vs. Popularity (n={len(df)} heroes)", fontsize=16, fontweight='bold')
    plt.xlabel("Total Picks (Popularity)", fontsize=12)
    plt.ylabel("Win Rate %", fontsize=12)
    plt.axhline(50, color='red', linestyle='--', alpha=0.5, label="50% Win Rate")
    plt.legend()
    
    # Save Static
    output_file_static = "meta_snapshot.png"
    plt.savefig(output_file_static, dpi=300, bbox_inches='tight')
    print(f"✅ Static Chart saved to {output_file_static}")

    # --- B. Interactive Plot (Full Detail) ---
    print("   ... Generating Interactive HTML")
    fig = px.scatter(
        df,
        x="total_picks",
        y="win_rate",
        hover_name="hero_name",
        size="total_picks",
        color="win_rate",
        color_continuous_scale="RdYlGn",
        title=f"Dota 2 Pro Meta (Interactive) - n={len(df)} heroes",
        labels={"total_picks": "Total Picks", "win_rate": "Win Rate %"}
    )
    
    # Improve layout
    fig.update_layout(
        showlegend=False,
        height=800
    )
    
    output_file_html = "meta_snapshot.html"
    fig.write_html(output_file_html)
    print(f"✅ Interactive Chart saved to {output_file_html}")

if __name__ == "__main__":
    generate_meta_chart()