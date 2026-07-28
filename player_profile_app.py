#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Streamlit app for exploring player_profile: era-adjusted scoring metrics
(scoring+, pts+, ts+) alongside traditional counting stats, filterable by
season and scoring-title qualification.

Run with: /opt/anaconda3/bin/streamlit run player_profile_app.py
"""

import base64
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


def uast_color(rating: float) -> str:
    """Maps a uast_rating to its Finisher/Balanced/Creator color: blue/gray/dark red."""
    if rating <= -2:
        return "#2a78d6"  # diverging blue pole -> Finisher
    elif rating <= 1:
        return "#6b6a66"  # neutral midpoint -> Balanced
    else:
        return "#a13939"  # dark red -> Creator


def uast_number_line_svg(rating: float) -> str:
    """Renders a -4..4 number line with a dot marking `rating`, as a base64 SVG data URI."""
    width, height = 170, 30
    left_pad, right_pad = 15, 15
    axis_y = 12
    min_v, max_v = -4, 4

    def x_for(v: float) -> float:
        return left_pad + (v - min_v) / (max_v - min_v) * (width - left_pad - right_pad)

    ticks = "".join(
        f'<line x1="{x_for(v):.1f}" y1="{axis_y - 3}" x2="{x_for(v):.1f}" y2="{axis_y + 3}" '
        f'stroke="#c3c2b7" stroke-width="1"/>'
        f'<text x="{x_for(v):.1f}" y="{axis_y + 12}" font-size="8" fill="#898781" '
        f'text-anchor="middle" font-family="system-ui, -apple-system, Segoe UI, sans-serif">{v}</text>'
        for v in range(min_v, max_v + 1)
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<line x1="{x_for(min_v):.1f}" y1="{axis_y}" x2="{x_for(max_v):.1f}" y2="{axis_y}" '
        f'stroke="#c3c2b7" stroke-width="1"/>'
        f"{ticks}"
        f'<circle cx="{x_for(rating):.1f}" cy="{axis_y}" r="4" fill="{uast_color(rating)}" '
        f'stroke="#ffffff" stroke-width="2"/>'
        f"</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def scoring_profile_badge_svg(profile: str, rating: float) -> str:
    """Renders `profile` as bold text colored to match its uast_rating, as a base64 SVG data URI."""
    width, height = 76, 20
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<text x="2" y="15" font-size="13" font-weight="700" fill="{uast_color(rating)}" '
        f'font-family="system-ui, -apple-system, Segoe UI, sans-serif">{html.escape(profile)}</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


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

table_df = table_source[[
    "player_name", "team_abbreviation", "season", "scoring_plus", "pts_plus", "ts_plus",
    "points_per_game", "per_100_pts", "true_shooting_percentage", "pct_uast_fgm",
    "uast_rating", "profile",
]].rename(columns={
    "player_name": "Player",
    "team_abbreviation": "Team",
    "season": "Season",
    "scoring_plus": "Scoring+",
    "pts_plus": "PTS+",
    "ts_plus": "TS+",
    "points_per_game": "PPG",
    "per_100_pts": "PTS per 100",
    "true_shooting_percentage": "TS%",
    "pct_uast_fgm": "FGM% UAST",
    "profile": "Scoring Profile",
})
table_df["UAST Rating"] = table_df["uast_rating"].apply(uast_number_line_svg)
table_df["Scoring Profile"] = [
    scoring_profile_badge_svg(profile, rating)
    for profile, rating in zip(table_df["Scoring Profile"], table_df["uast_rating"])
]
table_df = table_df[[
    "Player", "Team", "Season", "Scoring+", "PTS+", "TS+", "PPG", "PTS per 100", "TS%",
    "FGM% UAST", "UAST Rating", "Scoring Profile",
]].sort_values("Scoring+", ascending=False).reset_index(drop=True)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Player": st.column_config.TextColumn(width="large"),
        "Scoring+": st.column_config.NumberColumn(format="%d"),
        "PTS+": st.column_config.NumberColumn(format="%d"),
        "TS+": st.column_config.NumberColumn(format="%d"),
        "PPG": st.column_config.NumberColumn(format="%.1f"),
        "PTS per 100": st.column_config.NumberColumn(format="%.1f"),
        "TS%": st.column_config.NumberColumn(format="%.3f"),
        "FGM% UAST": st.column_config.NumberColumn(format="%.3f"),
        "UAST Rating": st.column_config.ImageColumn(width="medium"),
        "Scoring Profile": st.column_config.ImageColumn(width="small"),
    },
)
