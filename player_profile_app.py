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
    """Maps a uast_rating to its Finisher/Balanced/Creator color: blue/gray/orange."""
    if rating <= -2:
        return "#2a78d6"  # diverging blue pole -> Finisher
    elif rating <= 1:
        return "#6b6a66"  # neutral midpoint -> Balanced
    else:
        return "#c2703b"  # burnt orange -> Creator


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


PROFILE_COLORS = {"Finisher": "#2a78d6", "Balanced": "#6b6a66", "Creator": "#c2703b"}
PLAYER1_COLOR = "#c9a227"  # gold
PLAYER2_COLOR = "#1a8a8a"  # teal


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def season_range_label(season_end_years) -> str:
    return f"{min(season_end_years) - 1}-{max(season_end_years)}"


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


def color_plus_metric(value) -> str:
    color = "#1a7a3c" if value >= 100 else "#c0392b"  # green / red
    return f"color: {color}"


SCORING_PLUS_NEUTRAL_RGB = (201, 200, 194)  # #c9c8c2, matches the app's other neutral grays
SCORING_PLUS_GREEN_RGB = (26, 122, 60)      # #1a7a3c
SCORING_PLUS_RED_RGB = (192, 57, 43)        # #c0392b


def scoring_plus_gradient_color(value: float, min_val: float, max_val: float) -> str:
    """Diverging red<->neutral<->green scale centered at 100 (league average).

    Darkest red at min_val, darkest green at max_val, neutral gray at exactly 100.
    """
    if value >= 100:
        span = max(max_val - 100, 1e-9)
        t = min(max((value - 100) / span, 0.0), 1.0)
        target = SCORING_PLUS_GREEN_RGB
    else:
        span = max(100 - min_val, 1e-9)
        t = min(max((100 - value) / span, 0.0), 1.0)
        target = SCORING_PLUS_RED_RGB
    rgb = tuple(
        round(SCORING_PLUS_NEUTRAL_RGB[i] + (target[i] - SCORING_PLUS_NEUTRAL_RGB[i]) * t)
        for i in range(3)
    )
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def render_top_nav(current_page: str) -> None:
    st.title("NBA Scoring+ Explorer")
    choice = st.pills(
        "Navigation",
        ["Home", "Compare"],
        default=current_page,
        key="top_nav_pills",
        label_visibility="collapsed",
    )
    if choice == "Home" and current_page != "Home":
        st.switch_page(home_page)
    elif choice == "Compare" and current_page != "Compare":
        st.switch_page(compare_page)
    st.divider()


def render_home(df: pd.DataFrame) -> None:
    render_top_nav("Home")

    # Scatter-click selection defers clearing the search/season widgets to here,
    # before they're instantiated below — Streamlit forbids writing to a widget's
    # session_state key later in the same run once that widget has been created.
    if st.session_state.pop("_reset_home_filters", False):
        st.session_state.player_search_term = ""
        st.session_state.season_choice = "All Seasons"

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
        selected_name = df.loc[df["player_id"] == st.session_state.selected_player_id]["player_name"].iloc[0]
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
        selected_name = df.loc[df["player_id"] == selected_player_id]["player_name"].iloc[0]
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

    styled_table_df = (
        table_df.style
        .format({
            "Scoring+": "{:.0f}",
            "PTS+": "{:.0f}",
            "TS+": "{:.0f}",
            "PPG": "{:.1f}",
            "PTS per 100": "{:.1f}",
            "TS%": "{:.3f}",
            "FGM% UAST": "{:.3f}",
        })
        .map(color_plus_metric, subset=["Scoring+", "PTS+", "TS+"])
    )

    st.dataframe(
        styled_table_df,
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

    title_col, dropdown_col = st.columns([3, 1])
    plot_choice = dropdown_col.selectbox(
        "Scatter plot",
        ["FGM% UAST vs Scoring+", "TS+ vs PTS+"],
        key="home_scatter_choice",
        label_visibility="collapsed",
    )
    title_col.subheader(plot_choice)

    if selected_player_id is not None:
        selected_name = df.loc[df["player_id"] == selected_player_id]["player_name"].iloc[0]
        plot_caption = f"{selected_name} {'Qualified' if qualified_only else 'All'} Seasons"
    else:
        filter_qualifier_text = "Qualified Players" if qualified_only else "All Players"
        if season_choice == "All Seasons":
            plot_caption = f"{filter_qualifier_text} {season_range_label(league_source['season_end_year'].unique())} Seasons"
        else:
            plot_caption = f"{filter_qualifier_text} {season_choice} Seasons"
    title_col.caption(plot_caption)

    def handle_scatter_click(scatter_event) -> None:
        clicked_points = scatter_event.get("selection", {}).get("points", []) if scatter_event else []
        if clicked_points:
            customdata = clicked_points[0].get("customdata")
            if customdata:
                clicked_player_id = customdata[0]
                if clicked_player_id != st.session_state.selected_player_id:
                    st.session_state.selected_player_id = clicked_player_id
                    st.session_state["_reset_home_filters"] = True
                    st.rerun()

    if plot_choice == "FGM% UAST vs Scoring+":
        scatter_fig = px.scatter(
            table_source,
            x="pct_uast_fgm",
            y="scoring_plus",
            color="profile",
            color_discrete_map=PROFILE_COLORS,
            hover_name="player_name",
            labels={"pct_uast_fgm": "FGM% UAST", "scoring_plus": "Scoring+", "profile": "Scoring Profile"},
            custom_data=["player_id", "season"],
        )
        scatter_fig.add_hline(y=100, line_dash="dash", line_color="#898781")

        qualifier_text = "Qualified Players"

        # The average line always compares against scoring-title-qualified players,
        # regardless of the "Show qualified players only" checkbox.
        if selected_player_id is not None and season_choice == "All Seasons":
            # Compare against the league across the selected player's whole career span,
            # not just their (possibly few) qualified seasons.
            career_seasons = df.loc[df["player_id"] == selected_player_id]["season_end_year"].unique()
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
        scatter_fig.update_traces(
            marker=dict(size=8, opacity=0.75),
            hovertemplate=(
                "<b>%{hovertext}</b> (%{customdata[1]})<br>"
                "FGM% UAST: %{x:.3f}<br>Scoring+: %{y:.0f}<extra></extra>"
            ),
            selector=dict(mode="markers"),
        )

        scatter_event = st.plotly_chart(
            scatter_fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key="scatter_chart",
        )
        handle_scatter_click(scatter_event)

    else:
        x_max_dev = (league_source["ts_plus"] - 100).abs().max() if not league_source.empty else 10
        y_max_dev = (league_source["pts_plus"] - 100).abs().max() if not league_source.empty else 10
        x0, x1 = 100 - x_max_dev * 1.1, 100 + x_max_dev * 1.1
        y0, y1 = 100 - y_max_dev * 1.1, 100 + y_max_dev * 1.1

        if not table_source.empty:
            min_val = table_source["scoring_plus"].min()
            max_val = table_source["scoring_plus"].max()
        else:
            min_val = max_val = 100
        marker_colors = [
            scoring_plus_gradient_color(v, min_val, max_val) for v in table_source["scoring_plus"]
        ]

        scatter_fig = px.scatter(
            table_source,
            x="ts_plus",
            y="pts_plus",
            hover_name="player_name",
            custom_data=["player_id", "season", "scoring_plus"],
            labels={"ts_plus": "TS+", "pts_plus": "PTS+"},
        )
        scatter_fig.update_traces(
            marker=dict(size=8, opacity=0.85, color=marker_colors, line=dict(width=0)),
            hovertemplate=(
                "<b>%{hovertext}</b> (%{customdata[1]})<br>"
                "Scoring+: %{customdata[2]:.0f}<br>"
                "PTS+: %{y:.0f}<br>"
                "TS+: %{x:.0f}<extra></extra>"
            ),
        )
        scatter_fig.add_hline(y=100, line_dash="dash", line_color="#898781")
        scatter_fig.add_vline(x=100, line_dash="dash", line_color="#898781")
        scatter_fig.update_xaxes(range=[x0, x1])
        scatter_fig.update_yaxes(range=[y0, y1])

        scatter_event = st.plotly_chart(
            scatter_fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key="scatter_chart_ts_pts",
        )
        handle_scatter_click(scatter_event)


# --- Compare page -----------------------------------------------------------

# (column, label, kind) in display order. `kind` drives both formatting and
# whether the value is eligible for the bold-if-higher comparison.
COMPARE_ROWS = [
    ("player_name", "Player", "str"),
    ("team_abbreviation", "Team", "str"),
    ("season", "Season", "str"),
    ("age", "Age", "int"),
    ("positions", "Position", "title"),
    ("games_played", "GP", "int_cmp"),
    ("minutes_per_game", "MPG", "num1"),
    ("scoring_plus", "Scoring+", "num0"),
    ("pts_plus", "PTS+", "num0"),
    ("ts_plus", "TS+", "num0"),
    ("points_per_game", "PPG", "num1"),
    ("per_100_pts", "PTS per 100", "num1"),
    ("fg_percentage", "FG%", "num3"),
    ("three_point_percentage", "3P%", "num3"),
    ("true_shooting_percentage", "TS%", "num3"),
    ("pct_uast_fgm", "FGM% UAST", "num3"),
]
COMPARABLE_KINDS = {"num0", "num1", "num3", "int_cmp"}


def format_compare_value(kind: str, value) -> str:
    if kind == "str":
        return html.escape(str(value))
    if kind == "title":
        return html.escape(str(value).title())
    if kind in ("int", "int_cmp"):
        return f"{int(value)}"
    if kind == "num0":
        return f"{value:.0f}"
    if kind == "num1":
        return f"{value:.1f}"
    if kind == "num3":
        return f"{value:.3f}"
    return html.escape(str(value))


def player_search_widget(df: pd.DataFrame, key_prefix: str, label: str) -> int | None:
    sel_key = f"{key_prefix}_selected_id"
    search_key = f"{key_prefix}_search"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = None

    search_term = st.text_input(label, key=search_key)

    if search_term and st.session_state[sel_key] is not None:
        selected_name = df.loc[df["player_id"] == st.session_state[sel_key]]["player_name"].iloc[0]
        if search_term.lower() not in selected_name.lower():
            st.session_state[sel_key] = None

    if search_term and st.session_state[sel_key] is None:
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
            for _, row in suggestions.iterrows():
                suggestion_label = f"{row['player_name']} {row['career_start'] - 1}-{row['career_end']}"
                if st.button(suggestion_label, key=f"{key_prefix}_suggest_{row['player_id']}"):
                    st.session_state[sel_key] = row["player_id"]
                    st.rerun()

    selected_id = st.session_state[sel_key]
    if selected_id is not None:
        selected_name = df.loc[df["player_id"] == selected_id]["player_name"].iloc[0]
        name_col, clear_col = st.columns([4, 1])
        name_col.caption(f"Showing: **{selected_name}**")
        if clear_col.button("Clear", key=f"{key_prefix}_clear"):
            st.session_state[sel_key] = None
            st.rerun()
    return selected_id


def player_season_widget(df: pd.DataFrame, player_id: int, key_prefix: str) -> str | None:
    seasons = (
        df[df["player_id"] == player_id][["season_end_year", "season"]]
        .drop_duplicates()
        .sort_values("season_end_year", ascending=False)
    )
    # Keyed by player_id so switching players never leaves a stale selection
    # that isn't in the new options list.
    return st.selectbox("Season", seasons["season"].tolist(), key=f"{key_prefix}_season_{player_id}")


def render_compare_table(row: pd.Series | None, other_row: pd.Series | None, accent_color: str) -> str:
    bg_color = hex_to_rgba(accent_color, 0.10)
    if row is None:
        return (
            f"<div style='opacity:0.6; padding:0.75rem; background-color:{bg_color}; "
            f"border-radius:10px;'>Select a player and season above.</div>"
        )

    lines = [
        f"<table style='width:100%; border-collapse:collapse; background-color:{bg_color};'>"
    ]
    for col, label, kind in COMPARE_ROWS:
        value_display = format_compare_value(kind, row[col])
        bold = (
            kind in COMPARABLE_KINDS
            and other_row is not None
            and row[col] > other_row[col]
        )
        weight = "700" if bold else "400"
        lines.append(
            "<tr>"
            "<td style='padding:4px 10px; border-bottom:1px solid rgba(128,128,128,0.25); opacity:0.7;'>"
            f"{label}</td>"
            f"<td style='padding:4px 10px; border-bottom:1px solid rgba(128,128,128,0.25); font-weight:{weight};'>"
            f"{value_display}</td>"
            "</tr>"
        )

    profile_color = uast_color(row["uast_rating"])
    lines.append(
        "<tr>"
        "<td style='padding:4px 10px; border-bottom:1px solid rgba(128,128,128,0.25); opacity:0.7;'>"
        "Scoring Profile</td>"
        f"<td style='padding:4px 10px; border-bottom:1px solid rgba(128,128,128,0.25); "
        f"color:{profile_color}; font-weight:700;'>"
        f"{html.escape(str(row['profile']))}</td>"
        "</tr>"
    )
    lines.append(
        "<tr>"
        "<td colspan='2' style='padding:8px 10px;'>"
        f"<img src='{uast_number_line_svg(row['uast_rating'])}' style='width:100%; height:auto; display:block;' />"
        "</td>"
        "</tr>"
    )
    lines.append("</table>")
    return "".join(lines)


def render_compare_scatter(
    df: pd.DataFrame, p1_row: pd.Series | None, p2_row: pd.Series | None, plot_choice: str
) -> None:
    qualified_df = df[df["qualified"]]

    if plot_choice == "FGM% UAST vs Scoring+":
        x_col, y_col = "pct_uast_fgm", "scoring_plus"
        x_label, y_label = "FGM% UAST", "Scoring+"
        x_fmt, y_fmt = ":.3f", ":.0f"
    else:
        x_col, y_col = "ts_plus", "pts_plus"
        x_label, y_label = "TS+", "PTS+"
        x_fmt, y_fmt = ":.0f", ":.0f"

    scatter_fig = go.Figure()
    scatter_fig.add_hline(y=100, line_dash="dash", line_color="#898781")

    # Fixed axis ranges matching Home's default view (All Seasons, qualified players only)
    # so the plot doesn't jump around as different players/seasons are compared.
    y_max_dev = (qualified_df[y_col] - 100).abs().max()
    y0, y1 = 100 - y_max_dev * 1.1, 100 + y_max_dev * 1.1
    scatter_fig.update_yaxes(range=[y0, y1], title=y_label)

    if plot_choice == "FGM% UAST vs Scoring+":
        x_min, x_max = qualified_df[x_col].min(), qualified_df[x_col].max()
        x_pad = (x_max - x_min) * 0.05
        scatter_fig.update_xaxes(range=[x_min - x_pad, x_max + x_pad], title=x_label)

        vline_x = qualified_df[x_col].mean()
        season_text = season_range_label(qualified_df["season_end_year"].unique())
        hover_label = f"League avg FGM% UAST: {vline_x:.3f}<br>{season_text} (Qualified Players)"
        scatter_fig.add_trace(go.Scatter(
            x=[vline_x] * 50,
            y=np.linspace(y0, y1, 50),
            mode="lines",
            line=dict(dash="dash", color="#898781"),
            hoverinfo="text",
            hovertext=hover_label,
            showlegend=False,
        ))
    else:
        x_max_dev = (qualified_df[x_col] - 100).abs().max()
        x0, x1 = 100 - x_max_dev * 1.1, 100 + x_max_dev * 1.1
        scatter_fig.update_xaxes(range=[x0, x1], title=x_label)
        scatter_fig.add_vline(x=100, line_dash="dash", line_color="#898781")

    for row, color in [(p1_row, PLAYER1_COLOR), (p2_row, PLAYER2_COLOR)]:
        if row is None:
            continue
        scatter_fig.add_trace(go.Scatter(
            x=[row[x_col]],
            y=[row[y_col]],
            mode="markers",
            marker=dict(size=13, color=color, line=dict(width=1.5, color="white")),
            name=f"{row['player_name']} ({row['season']})",
            hovertemplate=(
                f"<b>{html.escape(str(row['player_name']))}</b> ({row['season']})<br>"
                f"{x_label}: %{{x{x_fmt}}}<br>{y_label}: %{{y{y_fmt}}}<extra></extra>"
            ),
        ))

    scatter_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(scatter_fig, use_container_width=True, key=f"compare_scatter_chart_{plot_choice}")


def render_compare(df: pd.DataFrame) -> None:
    render_top_nav("Compare")
    st.subheader("Compare Players")

    search_col1, search_col2 = st.columns(2)

    with search_col1:
        st.subheader("Player 1")
        p1_id = player_search_widget(df, "cmp1", "Search player name")
        p1_row = None
        if p1_id is not None:
            p1_season = player_season_widget(df, p1_id, "cmp1")
            p1_row = df[(df["player_id"] == p1_id) & (df["season"] == p1_season)].iloc[0]

    with search_col2:
        st.subheader("Player 2")
        p2_id = player_search_widget(df, "cmp2", "Search player name")
        p2_row = None
        if p2_id is not None:
            p2_season = player_season_widget(df, p2_id, "cmp2")
            p2_row = df[(df["player_id"] == p2_id) & (df["season"] == p2_season)].iloc[0]

    st.divider()

    table_col1, scatter_col, table_col2 = st.columns([1, 1.6, 1])
    with table_col1:
        st.markdown(render_compare_table(p1_row, p2_row, PLAYER1_COLOR), unsafe_allow_html=True)
    with scatter_col:
        plot_choice = st.selectbox(
            "Scatter plot",
            ["FGM% UAST vs Scoring+", "TS+ vs PTS+"],
            key="compare_scatter_choice",
            label_visibility="collapsed",
        )
        render_compare_scatter(df, p1_row, p2_row, plot_choice)
    with table_col2:
        st.markdown(render_compare_table(p2_row, p1_row, PLAYER2_COLOR), unsafe_allow_html=True)


df = load_player_profile()

home_page = st.Page(lambda: render_home(df), title="Home", url_path="home", default=True)
compare_page = st.Page(lambda: render_compare(df), title="Compare", url_path="compare")

st.navigation([home_page, compare_page], position="hidden").run()
