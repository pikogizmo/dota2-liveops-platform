import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from sqlalchemy import create_engine
from adjustText import adjust_text
from dotenv import load_dotenv

# Configuration
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def generate_meta_chart():
    print("🎨 Generating Meta Snapshot...")
    
    engine = create_engine(DATABASE_URL)
    
    # Fetch date range
    print("   ... Fetching Date Range")
    date_query = "SELECT min(match_date) as start_date, max(match_date) as end_date FROM analytics.picks_bans"
    with engine.connect() as conn:
        date_df = pd.read_sql(date_query, conn)
    
    if date_df['start_date'][0] is None:
        print("❌ No data found in database!")
        return

    start_date = pd.to_datetime(date_df['start_date'][0]).strftime('%b %d')
    end_date = pd.to_datetime(date_df['end_date'][0]).strftime('%b %d')
    date_label = f"({start_date} - {end_date})"
    
    # Fetch hero data
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

    # Generate static plot
    print("   ... Generating Static Image")
    plt.figure(figsize=(12, 8))
    sns.set_style("darkgrid")
    
    sns.scatterplot(
        data=df, 
        x="total_picks", 
        y="win_rate", 
        s=100, 
        color="#2ecc71", 
        edgecolor="black", 
        alpha=0.7
    )
    
    top_picks = df.nlargest(20, 'total_picks')['hero_name'].tolist()
    top_wins = df.nlargest(5, 'win_rate')['hero_name'].tolist()
    heroes_to_label = set(top_picks + top_wins)

    texts = []
    for i, row in df.iterrows():
        if row['hero_name'] in heroes_to_label:
            texts.append(plt.text(row['total_picks'], row['win_rate'], row['hero_name'], fontsize=9, fontweight='bold'))
    
    adjust_text(texts, arrowprops=dict(arrowstyle='-', color='gray', alpha=0.5))

    plt.title(f"Dota 2 Pro Meta: Win Rate vs. Popularity {date_label}\n(n={len(df)} heroes)", fontsize=16, fontweight='bold')
    plt.xlabel("Total Picks (Popularity)", fontsize=12)
    plt.ylabel("Win Rate %", fontsize=12)
    plt.axhline(50, color='red', linestyle='--', alpha=0.5, label="50% Win Rate")
    plt.legend()
    
    output_file_static = "meta_snapshot.png"
    plt.savefig(output_file_static, dpi=300, bbox_inches='tight')
    print(f"✅ Static Chart saved to {output_file_static}")

    # Generate interactive report
    print("   ... Generating Interactive HTML Report")
    
    # Calculate standard error
    df['p'] = df['win_rate'] / 100
    df['std_error'] = np.sqrt((df['p'] * (1 - df['p'])) / df['total_picks']) * 100 # Convert back to percentage

    # Scatter Chart
    fig_scatter = px.scatter(
        df,
        x="total_picks",
        y="win_rate",
        hover_name="hero_name",
        size="total_picks",
        color="win_rate",
        color_continuous_scale="RdYlGn",
        title=f"<b>Meta Scatter: Win Rate vs. Popularity</b> {date_label}",
        labels={"total_picks": "Total Picks", "win_rate": "Win Rate %"}
    )
    fig_scatter.update_layout(height=600, showlegend=False)

    # Bar Chart (Top 10 Win Rate)
    top_10_win = df.nlargest(10, 'win_rate')
    
    fig_bar = px.bar(
        top_10_win,
        x="hero_name",
        y="win_rate",
        hover_data=["total_picks"],
        color="win_rate",
        color_continuous_scale="RdYlGn",
        title=f"<b>Top 10 Highest Win Rate Heroes</b> {date_label}",
        labels={"hero_name": "Hero", "win_rate": "Win Rate %", "total_picks": "Total Picks"}
    )
    fig_bar.update_layout(height=500, showlegend=False)
    fig_bar.update_yaxes(range=[0, 100])

    # 3. Model Weights Chart (Horizontal Bar)
    print("   ... Generating Model Weights Chart")
    weights_file = "draft_weights.csv"
    fig_weights_html = ""
    
    if os.path.exists(weights_file):
        try:
            weights_df = pd.read_csv(weights_file)
            
            # Get Top 10 and Bottom 10
            top_10 = weights_df.head(10)
            bottom_10 = weights_df.tail(10)
            combined_weights = pd.concat([top_10, bottom_10]).sort_values(by="coefficient")
            
            fig_weights = px.bar(
                combined_weights,
                x="coefficient",
                y="hero_name",
                orientation='h',
                color="coefficient",
                color_continuous_scale="RdYlGn",
                title="<b>Meta Impact: Hero Draft Weights (Last 30 Days)</b>",
                labels={"coefficient": "Draft Impact (Log Odds)", "hero_name": "Hero"}
            )
            fig_weights.update_layout(height=600, showlegend=False)
            fig_weights_html = f'<div class="chart-container">{fig_weights.to_html(full_html=False, include_plotlyjs=False)}</div>'
            
        except Exception as e:
            print(f"⚠️ Failed to generate weights chart: {e}")
    else:
        print("⚠️ draft_weights.csv not found. Skipping model chart.")

    # Combine into HTML
    output_file_html = "index.html"
    last_updated = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(output_file_html, 'w') as f:
        f.write(f"""
        <html>
        <head>
            <title>Dota 2 Meta Report {date_label} - Last Updated: {last_updated}</title>
            <style>
                body {{ font-family: sans-serif; margin: 20px; background-color: #f4f4f9; }}
                .chart-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; }}
                h1 {{ text-align: center; color: #333; }}
                .timestamp {{ text-align: center; color: #666; font-size: 0.9em; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1>🛡️ Dota 2 Meta Report {date_label}</h1>
            <div class="timestamp">Last Updated: {last_updated}</div>
            <div class="chart-container">
                {fig_scatter.to_html(full_html=False, include_plotlyjs='cdn')}
            </div>
            <div class="chart-container">
                {fig_bar.to_html(full_html=False, include_plotlyjs=False)} 
            </div>
            {fig_weights_html}
        </body>
        </html>
        """)
        
    print(f"✅ Interactive Report saved to {output_file_html}")

if __name__ == "__main__":
    generate_meta_chart()