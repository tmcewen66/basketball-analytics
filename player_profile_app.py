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

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


PROFILE_COLORS = {"Finisher": "#2a78d6", "Balanced": "#6b6a66", "Creator": "#a13939"}


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
season_choice = st.selectbox(
    "Season", ["All Seasons"] + seasons_by_year["season"].tolist(), key="season_choice"
)

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
qualified_only = st.checkbox("Show qualified players only", value=True)

if "selected_player_id" not in st.session_state:
    st.session_state.selected_player_id = None

search_term = st.text_input("Search player name", key="player_search_term")

if search_term and st.session_state.selected_player_id is not None:
    selected_name = df.loc[df["player_id"] == st.session_state.selected_player_id, "player_name"].iloc[0]
    if search_term.lower() not in selected_name.lower():
        st.session_state.selected_player_id = None

if search_term and st.session_state.selected_player_id is None:
    suggestions = (
        df[df["player_name"].str.contains(search_term, case=False, na=False)]
        .groupby(["player_id", "player_name"])["season_end_year"]
        .agg(["min", "max", "count"])
        .reset_index()
        .rename(columns={"min": "career_start", "max": "career_end", "count": "seasons_played"})
        .sort_values(["seasons_played", "player_name"], ascending=[False, True])
        .head(5)
    )
    if suggestions.empty:
        st.caption("No players found.")
    else:
        suggestion_cols = st.columns(len(suggestions))
        for col, (_, row) in zip(suggestion_cols, suggestions.iterrows()):
            label = f"{row['player_name']} {row['career_start'] - 1}-{row['career_end']}"
            if col.button(label, key=f"suggest_{row['player_id']}"):
                st.session_state.selected_player_id = row["player_id"]
                st.rerun()

selected_player_id = st.session_state.selected_player_id
if selected_player_id is not None:
    selected_name = df.loc[df["player_id"] == selected_player_id, "player_name"].iloc[0]
    name_col, clear_col = st.columns([4, 1])
    name_col.caption(f"Showing: **{selected_name}**")
    if clear_col.button("Clear selection"):
        st.session_state.selected_player_id = None
        st.rerun()

league_source = qualified_df if qualified_only else filtered_df

table_source = league_source
if selected_player_id is not None:
    table_source = table_source[table_source["player_id"] == selected_player_id]

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
]]
if selected_player_id is not None:
    table_df = table_df.sort_values("Season", ascending=True).reset_index(drop=True)
else:
    table_df = table_df.sort_values("Scoring+", ascending=False).reset_index(drop=True)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Player": st.column_config.TextColumn(width="medium"),
        "Scoring+": st.column_config.NumberColumn(format="%d", width="small"),
        "PTS+": st.column_config.NumberColumn(format="%d", width="small"),
        "TS+": st.column_config.NumberColumn(format="%d", width="small"),
        "PPG": st.column_config.NumberColumn(format="%.1f", width="small"),
        "PTS per 100": st.column_config.NumberColumn(format="%.1f", width="small"),
        "TS%": st.column_config.NumberColumn(format="%.3f", width="small"),
        "FGM% UAST": st.column_config.NumberColumn(format="%.3f", width="small"),
        "UAST Rating": st.column_config.ImageColumn(width="medium"),
        "Scoring Profile": st.column_config.ImageColumn(width="medium"),
    },
)

st.divider()

st.subheader("FGM% UAST vs. Scoring+")


def season_range_label(season_end_years) -> str:
    return f"{min(season_end_years) - 1}-{max(season_end_years)}"


if selected_player_id is not None:
    selected_name = df.loc[df["player_id"] == selected_player_id, "player_name"].iloc[0]
    plot_caption = f"{selected_name} {'Qualified' if qualified_only else 'All'} Seasons"
else:
    filter_qualifier_text = "Qualified Players" if qualified_only else "All Players"
    if season_choice == "All Seasons":
        plot_caption = f"{filter_qualifier_text} {season_range_label(league_source['season_end_year'].unique())} Seasons"
    else:
        plot_caption = f"{filter_qualifier_text} {season_choice} Seasons"
st.caption(plot_caption)

scatter_fig = px.scatter(
    table_source,
    x="pct_uast_fgm",
    y="scoring_plus",
    color="profile",
    color_discrete_map=PROFILE_COLORS,
    hover_name="player_name",
    hover_data={"season": True, "pct_uast_fgm": ":.3f", "scoring_plus": ":.0f", "profile": False},
    labels={"pct_uast_fgm": "FGM% UAST", "scoring_plus": "Scoring+", "profile": "Scoring Profile"},
    custom_data=["player_id"],
)
scatter_fig.add_hline(y=100, line_dash="dash", line_color="#898781")

qualifier_text = "Qualified Players"

# The average line always compares against scoring-title-qualified players,
# regardless of the "Show qualified players only" checkbox.
if selected_player_id is not None and season_choice == "All Seasons":
    # Compare against the league across the selected player's whole career span,
    # not just their (possibly few) qualified seasons.
    career_seasons = df.loc[df["player_id"] == selected_player_id, "season_end_year"].unique()
    vline_source = qualified_df[qualified_df["season_end_year"].isin(career_seasons)]
    season_text = season_range_label(career_seasons)
elif season_choice != "All Seasons":
    vline_source = qualified_df
    season_text = season_choice
else:
    vline_source = qualified_df
    season_text = season_range_label(qualified_df["season_end_year"].unique())

y_max_dev = (league_source["scoring_plus"] - 100).abs().max() if not league_source.empty else 10
y0, y1 = 100 - y_max_dev * 1.1, 100 + y_max_dev * 1.1
scatter_fig.update_yaxes(range=[y0, y1])

if not league_source.empty:
    x_min, x_max = league_source["pct_uast_fgm"].min(), league_source["pct_uast_fgm"].max()
    x_pad = (x_max - x_min) * 0.05
    scatter_fig.update_xaxes(range=[x_min - x_pad, x_max + x_pad])

if not vline_source.empty:
    vline_x = vline_source["pct_uast_fgm"].mean()
    hover_label = f"League avg FGM% UAST: {vline_x:.3f}<br>{season_text} ({qualifier_text})"
    scatter_fig.add_trace(go.Scatter(
        x=[vline_x] * 50,
        y=np.linspace(y0, y1, 50),
        mode="lines",
        line=dict(dash="dash", color="#898781"),
        hoverinfo="text",
        hovertext=hover_label,
        showlegend=False,
    ))
scatter_fig.update_traces(marker=dict(size=8, opacity=0.75), selector=dict(mode="markers"))

scatter_event = st.plotly_chart(
    scatter_fig,
    use_container_width=True,
    on_select="rerun",
    selection_mode="points",
    key="scatter_chart",
)

clicked_points = scatter_event.selection.points if scatter_event else []
if clicked_points:
    customdata = clicked_points[0].get("customdata")
    if customdata:
        clicked_player_id = customdata[0]
        if clicked_player_id != st.session_state.selected_player_id:
            st.session_state.selected_player_id = clicked_player_id
            st.session_state.player_search_term = ""
            st.session_state.season_choice = "All Seasons"
            st.rerun()
