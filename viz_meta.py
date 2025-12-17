import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import json
import uuid
from sqlalchemy import create_engine
from adjustText import adjust_text
from dotenv import load_dotenv
import tomllib

# Configuration
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

with open("patch_config.toml", "rb") as f:
    config = tomllib.load(f)

# Load current patch and history
CURRENT_PATCH = config["current_meta"]
PATCH_HISTORY = config.get("patch_history", [])

# Build list of all patches (current first, then history)
ALL_PATCHES = [CURRENT_PATCH] + PATCH_HISTORY

def get_engine():
    return create_engine(DATABASE_URL)

def clean_fig(fig):
    """Convert figure to dict and manually overwrite data arrays with lists to avoid bdata."""
    # 1. Start with Plotly's dict (contains bdata)
    d = fig.to_dict()
    
    # Helper to force pure python list
    def to_clean_list(val):
        if hasattr(val, 'tolist'):
            return val.tolist()
        if isinstance(val, (list, tuple)):
             # Ensure elements are not numpy scalars
             return [x.item() if hasattr(x, 'item') else x for x in val]
        return list(val)

    # 2. Overwrite known data arrays with clean lists from source figure
    for i, trace in enumerate(fig.data):
        # Helper to safely clean a field
        def clean_field(field_name):
            if hasattr(trace, field_name):
                val = getattr(trace, field_name)
                # If it's a sequence/array, force list
                if val is not None and not isinstance(val, (str, dict)):
                    try:
                        d['data'][i][field_name] = to_clean_list(val)
                    except:
                        pass # Valid for scalars or non-iterables
        
        clean_field('x')
        clean_field('y')
        clean_field('text')
        clean_field('customdata')
        
        # Marker color
        if hasattr(trace, 'marker') and trace.marker is not None:
             c = trace.marker.color
             if c is not None and hasattr(c, '__len__') and not isinstance(c, (str, bytes)):
                 if 'marker' not in d['data'][i]: d['data'][i]['marker'] = {}
                 d['data'][i]['marker']['color'] = to_clean_list(c)

    return d

def fig_to_html(fig):
    """Serialize figure to HTML manually to bypass Plotly binary optimization."""
    clean_dict = clean_fig(fig)
    div_id = "chart_" + str(uuid.uuid4()).replace("-", "")
    data_json = json.dumps(clean_dict['data'])
    layout_json = json.dumps(clean_dict['layout'])
    return f'''
    <div id="{div_id}" class="plotly-graph-div"></div>
    <script>
        Plotly.newPlot("{div_id}", {data_json}, {layout_json}, {{responsive: true}});
    </script>
    '''

def generate_patch_charts(engine, patch, is_current=False):
    """Generate all charts for a single patch. Returns dict of Plotly figure HTML strings."""
    patch_name = patch["patch_name"]
    start_ts = patch["start_timestamp"]
    
    # Use lower thresholds for current patch (less data available)
    min_picks = 3 if is_current else 12
    min_synergy_matches = 5 if is_current else 15
    end_ts = patch.get("end_timestamp")  # None for current patch
    
    # Date filter SQL
    if end_ts:
        date_filter = "match_date >= to_timestamp(%(start_ts)s) AND match_date <= to_timestamp(%(end_ts)s)"
        params = {"start_ts": start_ts, "end_ts": end_ts}
    else:
        date_filter = "match_date >= to_timestamp(%(start_ts)s)"
        params = {"start_ts": start_ts}
    
    # Fetch date range
    date_query = f"""
    SELECT min(match_date) as start_date, max(match_date) as end_date 
    FROM analytics.picks_bans 
    WHERE {date_filter}
    """
    with engine.connect() as conn:
        date_df = pd.read_sql(date_query, conn, params=params)
    
    if date_df['start_date'][0] is None:
        return None, f"No data for {patch_name}"
    
    start_date = pd.to_datetime(date_df['start_date'][0]).strftime('%b %d')
    end_date = pd.to_datetime(date_df['end_date'][0]).strftime('%b %d')
    date_label = f"({start_date} - {end_date})"
    
    # Fetch hero data
    hero_query = f"""
    SELECT 
        h.hero_name,
        count(*) as total_picks,
        round(avg(case when pb.is_winner then 1 else 0 end) * 100, 2) as win_rate
    FROM analytics.picks_bans pb
    JOIN raw.heroes h ON h.hero_id = pb.hero_id
    WHERE pb.is_pick IS TRUE
    AND {date_filter}
    GROUP BY h.hero_name
    HAVING count(*) > {min_picks}
    ORDER BY total_picks DESC;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(hero_query, conn, params=params)
    
    if df.empty:
        return None, f"Not enough data for {patch_name}"
    
    # Debug data stats
    print(f"[{patch_name}] Data Stats:")
    print(f"  Rows: {len(df)}")
    print(df[['total_picks', 'win_rate']].describe())
    
    charts = {}
    
    # --- Scatter Chart ---
    # Force float type to ensure Plotly handles it correctly
    df['win_rate'] = df['win_rate'].astype(float)
    df['total_picks'] = df['total_picks'].astype(int)
    
    # Pre-calculate hover text to avoid JS formatting issues
    df['scatter_hover'] = (
        "<b>" + df['hero_name'] + "</b><br>" +
        "Picks: " + df['total_picks'].astype(str) + "<br>" +
        "Win Rate: " + df['win_rate'].round(1).astype(str) + "%"
    )
    
    fig_scatter = px.scatter(
        df,
        x="total_picks",
        y="win_rate",
        color="win_rate",
        color_continuous_scale="RdYlGn",
        title=f"<b>Meta Scatter ({patch_name}): Win Rate vs. Popularity</b> {date_label}",
        labels={"total_picks": "Total Picks", "win_rate": "Win Rate"}
    )
    
    # Use pre-formatted text
    fig_scatter.update_traces(
        mode='markers',
        text=df['scatter_hover'],
        hovertemplate="%{text}<extra></extra>",
        marker=dict(size=12, line=dict(width=1, color='DarkSlateGrey'), opacity=0.8)
    )
    
    fig_scatter.update_layout(
        height=600, 
        showlegend=False, 
        autosize=True,
        margin=dict(l=50, r=50, t=80, b=50),
        xaxis_title="Total Picks",
        yaxis_title="Win Rate %"
    )
    charts['scatter'] = fig_to_html(fig_scatter)
    
    # --- Bar Chart (Top 10 Win Rate) ---
    top_10_win = df.nlargest(10, 'win_rate').copy()
    
    # Pre-calculate hover text
    top_10_win['bar_hover'] = (
        "<b>" + top_10_win['hero_name'] + "</b><br>" +
        "Win Rate: " + top_10_win['win_rate'].round(1).astype(str) + "%<br>" +
        "Picks: " + top_10_win['total_picks'].astype(str)
    )

    fig_bar = px.bar(
        top_10_win,
        x="hero_name",
        y="win_rate",
        color="win_rate",
        color_continuous_scale="RdYlGn",
        title=f"<b>Top 10 Highest Win Rate Heroes ({patch_name})</b> {date_label}",
        labels={"hero_name": "Hero", "win_rate": "Win Rate"}
    )
    
    fig_bar.update_traces(
        text=top_10_win['bar_hover'],
        hovertemplate="%{text}<extra></extra>"
    )
    
    fig_bar.update_layout(height=500, showlegend=False, autosize=True)
    fig_bar.update_yaxes(range=[0, 100])
    charts['bar'] = fig_to_html(fig_bar)
    
    # --- Model Weights Chart ---
    weights_file = "draft_weights.csv"
    if os.path.exists(weights_file):
        try:
            weights_df = pd.read_csv(weights_file)
            top_10 = weights_df.head(10)
            bottom_10 = weights_df.tail(10)
            combined_weights = pd.concat([top_10, bottom_10]).sort_values(by="coefficient")
            
            # Pre-calculate hover
            combined_weights['hover_text'] = (
                "<b>" + combined_weights['hero_name'] + "</b><br>" +
                "Impact: " + combined_weights['coefficient'].round(3).astype(str)
            )
            
            fig_weights = px.bar(
                combined_weights,
                x="coefficient",
                y="hero_name",
                orientation='h',
                color="coefficient",
                color_continuous_scale="RdYlGn",
                title=f"<b>Meta Impact: Hero Draft Weights ({patch_name})</b>",
                labels={"coefficient": "Draft Impact (Log Odds)", "hero_name": "Hero"}
            )
            fig_weights.update_layout(height=600, showlegend=False, autosize=True)
            fig_weights.update_traces(
                text=combined_weights['hover_text'],
                hovertemplate="%{text}<extra></extra>"
            )
            charts['weights'] = fig_to_html(fig_weights)
        except Exception as e:
            print(f"⚠️ Failed to generate weights chart: {e}")
    
    # --- Synergy Chart ---
    synergy_query = f"""
    SELECT 
        h1.hero_name || ' + ' || h2.hero_name as combo_name,
        count(*) as matches_played,
        round(avg(case when pb1.is_winner then 1 else 0 end) * 100, 2) as win_rate
    FROM analytics.picks_bans pb1
    JOIN analytics.picks_bans pb2 ON pb1.match_id = pb2.match_id AND pb1.team = pb2.team
    JOIN raw.heroes h1 ON h1.hero_id = pb1.hero_id
    JOIN raw.heroes h2 ON h2.hero_id = pb2.hero_id
    WHERE pb1.is_pick IS TRUE 
    AND pb2.is_pick IS TRUE
    AND pb1.hero_id < pb2.hero_id
    AND {date_filter.replace('match_date', 'pb1.match_date')}
    GROUP BY 1
    HAVING count(*) >= {min_synergy_matches}
    ORDER BY win_rate DESC
    LIMIT 15;
    """
    
    try:
        with engine.connect() as conn:
            synergy_df = pd.read_sql(synergy_query, conn, params=params)
            
        if not synergy_df.empty:
            synergy_df['win_rate'] = synergy_df['win_rate'].astype(float)
            synergy_df['matches_played'] = synergy_df['matches_played'].astype(int)
            
            synergy_df['hover_text'] = (
                "<b>" + synergy_df['combo_name'] + "</b><br>" +
                "Win Rate: " + synergy_df['win_rate'].round(1).astype(str) + "%<br>" +
                "Matches: " + synergy_df['matches_played'].astype(str)
            )
            
            fig_synergy = px.bar(
                synergy_df,
                x="win_rate",
                y="combo_name",
                orientation='h',
                color="win_rate",
                color_continuous_scale="RdYlGn",
                title=f"<b>Top 15 Best Hero Combos (Synergy)</b> {date_label}",
                labels={"win_rate": "Win Rate", "combo_name": "Hero Duo"}
            )
            fig_synergy.update_layout(height=600, showlegend=False, autosize=True)
            fig_synergy.update_yaxes(autorange="reversed")
            fig_synergy.update_traces(
                text=synergy_df['hover_text'],
                hovertemplate="%{text}<extra></extra>"
            )
            charts['synergy'] = fig_to_html(fig_synergy)
    except Exception as e:
        print(f"⚠️ Failed to generate synergy chart: {e}")
    
    return charts, date_label

def generate_static_chart(engine, patch):
    """Generate static PNG for current patch only."""
    patch_name = patch["patch_name"]
    start_ts = patch["start_timestamp"]
    
    date_query = """
    SELECT min(match_date) as start_date, max(match_date) as end_date 
    FROM analytics.picks_bans 
    WHERE match_date >= to_timestamp(%(start_ts)s)
    """
    with engine.connect() as conn:
        date_df = pd.read_sql(date_query, conn, params={"start_ts": start_ts})
    
    if date_df['start_date'][0] is None:
        print("❌ No data found for static chart!")
        return
    
    start_date = pd.to_datetime(date_df['start_date'][0]).strftime('%b %d')
    end_date = pd.to_datetime(date_df['end_date'][0]).strftime('%b %d')
    date_label = f"({start_date} - {end_date})"
    
    hero_query = """
    SELECT 
        h.hero_name,
        count(*) as total_picks,
        round(avg(case when pb.is_winner then 1 else 0 end) * 100, 2) as win_rate
    FROM analytics.picks_bans pb
    JOIN raw.heroes h ON h.hero_id = pb.hero_id
    WHERE pb.is_pick IS TRUE
    AND pb.match_date >= to_timestamp(%(start_ts)s)
    GROUP BY h.hero_name
    HAVING count(*) > 12
    ORDER BY total_picks DESC;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(hero_query, conn, params={"start_ts": start_ts})
    
    if df.empty:
        print("❌ Not enough data for static chart!")
        return
    
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

    plt.title(f"Dota 2 Pro Meta ({patch_name}): Win Rate vs. Popularity {date_label}\n(n={len(df)} heroes)", fontsize=16, fontweight='bold')
    plt.xlabel("Total Picks (Popularity)", fontsize=12)
    plt.ylabel("Win Rate %", fontsize=12)
    plt.axhline(50, color='red', linestyle='--', alpha=0.5, label="50% Win Rate")
    plt.legend()
    
    output_file = "meta_snapshot.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✅ Static Chart saved to {output_file}")

def generate_meta_chart():
    print("🎨 Generating Meta Snapshot...")
    
    engine = get_engine()
    
    # Generate static chart for current patch
    print("   ... Generating Static Image (Current Patch)")
    generate_static_chart(engine, CURRENT_PATCH)
    
    # Generate interactive report with tabs
    print("   ... Generating Interactive HTML Report")
    
    all_patch_data = []
    for i, patch in enumerate(ALL_PATCHES):
        is_current = (i == 0)  # First patch is current
        print(f"   ... Processing {patch['patch_name']}")
        charts, date_label = generate_patch_charts(engine, patch, is_current=is_current)
        if charts:
            all_patch_data.append({
                "patch": patch,
                "charts": charts,
                "date_label": date_label
            })
    
    if not all_patch_data:
        print("❌ No data available for any patch!")
        return
    
    # Build tabs HTML
    tabs_html = ""
    content_html = ""
    
    for i, data in enumerate(all_patch_data):
        patch_name = data["patch"]["patch_name"]
        is_active = "active" if i == 0 else ""
        patch_id = patch_name.replace(".", "_")
        
        # Tab button
        tabs_html += f'<button class="tab-btn {is_active}" onclick="openTab(event, \'{patch_id}\')">{patch_name}</button>\n'
        
        # Tab content
        display = "block" if i == 0 else "none"
        charts = data["charts"]
        
        content_html += f'''
        <div id="{patch_id}" class="tab-content" style="display: {display};">
            <div class="chart-container">{charts.get('scatter', '')}</div>
            <div class="chart-container">{charts.get('bar', '')}</div>
            {"<div class='chart-container'>" + charts.get('weights', '') + "</div>" if 'weights' in charts else ""}
            {"<div class='chart-container'>" + charts.get('synergy', '') + "</div>" if 'synergy' in charts else ""}
        </div>
        '''
    
    last_updated = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    current_patch_name = CURRENT_PATCH["patch_name"]
    
    html_content = f"""
    <html>
    <head>
        <title>Dota 2 Meta Report - Last Updated: {last_updated}</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{ font-family: sans-serif; margin: 20px; background-color: #f4f4f9; }}
            .chart-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; }}
            h1 {{ text-align: center; color: #333; }}
            .timestamp {{ text-align: center; color: #666; font-size: 0.9em; margin-bottom: 20px; }}
            
            /* Tab styles */
            .tab-container {{ display: flex; justify-content: center; margin-bottom: 20px; gap: 10px; }}
            .tab-btn {{
                padding: 12px 24px;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                background-color: #ddd;
                color: #333;
                transition: all 0.3s ease;
            }}
            .tab-btn:hover {{ background-color: #bbb; }}
            .tab-btn.active {{
                background-color: #2ecc71;
                color: white;
            }}
            .tab-content {{ display: none; }}
        </style>
    </head>
    <body>
        <h1>🛡️ Dota 2 Meta Report</h1>
        <div class="timestamp">Last Updated: {last_updated}</div>
        
        <div class="tab-container">
            {tabs_html}
        </div>
        
        {content_html}
        
        <script>
            function openTab(evt, patchId) {{
                // Hide all tab content
                var tabcontent = document.getElementsByClassName("tab-content");
                for (var i = 0; i < tabcontent.length; i++) {{
                    tabcontent[i].style.display = "none";
                }}
                
                // Remove active class from all tabs
                var tabbtns = document.getElementsByClassName("tab-btn");
                for (var i = 0; i < tabbtns.length; i++) {{
                    tabbtns[i].className = tabbtns[i].className.replace(" active", "");
                }}
                
                // Show selected tab and mark button as active
                document.getElementById(patchId).style.display = "block";
                evt.currentTarget.className += " active";
                
                // Trigger resize for Plotly charts (wait slightly for display:block to take effect)
                setTimeout(function() {{
                   window.dispatchEvent(new Event('resize'));
                }}, 50);
            }}
        </script>
    </body>
    </html>
    """
    
    output_file = "index.html"
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    print(f"✅ Interactive Report saved to {output_file}")

if __name__ == "__main__":
    generate_meta_chart()