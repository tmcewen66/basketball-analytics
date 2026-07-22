#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Streamlit app for exploring player_profile: era-adjusted scoring metrics
(scoring+, pts+, ts+) alongside traditional counting stats, filterable by
season and scoring-title qualification.

Run with: /opt/anaconda3/bin/streamlit run player_profile_app.py
"""

import html
import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = "nba_stats.db"

st.set_page_config(page_title="NBA Scoring+ Explorer", layout="wide")


@st.cache_data
def load_player_profile(db_path: str = DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql("SELECT * FROM player_profile", con)
    df["qualified"] = df["qualified"].astype(bool)
    return df


def render_leaderboard(df: pd.DataFrame, metric_col: str, show_season: bool, n: int = 5) -> None:
    top = df.nlargest(n, metric_col).reset_index(drop=True)
    if top.empty:
        st.write("No qualified players.")
        return

    def label(row: pd.Series) -> str:
        name = html.escape(str(row["player_name"]))
        if show_season:
            return f"{name} <span style='opacity:0.6; font-weight:400;'>({row['season']})</span>"
        return name

    leader, rest = top.iloc[0], top.iloc[1:]

    lines = [
        f"<div style='font-size:1.9rem; font-weight:700; line-height:1.25;'>{label(leader)}</div>",
        f"<div style='font-size:1.3rem; font-weight:600; opacity:0.85; margin-bottom:0.5rem;'>"
        f"{round(leader[metric_col])}</div>",
    ]
    for rank, (_, row) in enumerate(rest.iterrows(), start=2):
        lines.append(
            f"<div style='font-size:0.9rem; padding:2px 0;'>"
            f"{rank}. {label(row)} — {round(row[metric_col])}</div>"
        )
    st.markdown("".join(lines), unsafe_allow_html=True)


df = load_player_profile()

st.title("NBA Scoring+ Explorer")

seasons_by_year = (
    df[["season_end_year", "season"]]
    .drop_duplicates()
    .sort_values("season_end_year", ascending=False)
)
season_choice = st.selectbox("Season", ["All Seasons"] + seasons_by_year["season"].tolist())

if season_choice == "All Seasons":
    filtered_df = df
else:
    filtered_df = df[df["season"] == season_choice]

qualified_df = filtered_df[filtered_df["qualified"]]
show_season_in_top = season_choice == "All Seasons"

leaders_label = "All-Time" if season_choice == "All Seasons" else season_choice
st.subheader(f"Top 5 — {leaders_label} (qualified players)")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Scoring+**")
    render_leaderboard(qualified_df, "scoring_plus", show_season_in_top)

with col2:
    st.markdown("**Pts+**")
    render_leaderboard(qualified_df, "pts_plus", show_season_in_top)

with col3:
    st.markdown("**TS+**")
    render_leaderboard(qualified_df, "ts_plus", show_season_in_top)

st.divider()

st.subheader("All Players")
qualified_only = st.checkbox("Show qualified players only", value=False)
search_term = st.text_input("Search player name")

table_source = qualified_df if qualified_only else filtered_df

if search_term:
    table_source = table_source[
        table_source["player_name"].str.contains(search_term, case=False, na=False)
    ]

table_df = (
    table_source[[
        "player_name", "age", "team_name", "season", "scoring_plus", "pts_plus", "ts_plus",
        "points_per_game", "per_100_pts", "true_shooting_percentage",
    ]]
    .rename(columns={
        "player_name": "Player",
        "age": "Age",
        "team_name": "Team",
        "season": "Season",
        "scoring_plus": "Scoring+",
        "pts_plus": "Pts+",
        "ts_plus": "TS+",
        "points_per_game": "PPG",
        "per_100_pts": "Pts/100",
        "true_shooting_percentage": "TS%",
    })
    .sort_values("Scoring+", ascending=False)
    .reset_index(drop=True)
)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Scoring+": st.column_config.NumberColumn(format="%d"),
        "Pts+": st.column_config.NumberColumn(format="%d"),
        "TS+": st.column_config.NumberColumn(format="%d"),
        "PPG": st.column_config.NumberColumn(format="%.1f"),
        "Pts/100": st.column_config.NumberColumn(format="%.1f"),
        "TS%": st.column_config.NumberColumn(format="%.3f"),
    },
)
