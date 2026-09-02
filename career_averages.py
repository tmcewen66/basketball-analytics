#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Builds a career_averages table: one row per unique player (keyed by the
basketball-reference slug), summarizing their whole career in this dataset.

Per-game counting stats and the FG%/3P%/FT%/TS% shooting splits are computed
from career *totals* in basic_stats rather than by averaging each season's
per-game numbers, so heavier seasons naturally count for more. FGM% UAST is
weighted by each season's made field goals (from scoring_profile), and
Scoring+/TS+/PTS+ are weighted by each season's minutes played (from
scoring_plus), so a 3000-minute season outweighs a 1500-minute one. OWS and
OBPM (from advanced_stats) are summed across the career rather than averaged.
"""

import sqlite3

import numpy as np
import pandas as pd

DB_PATH = "nba_stats.db"


def load_tables(
    db_path: str = DB_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        basic_stats = pd.read_sql(
            "SELECT slug, season_end_year, name, games_played, minutes_played, points, assists, "
            "offensive_rebounds, defensive_rebounds, turnovers, steals, blocks, "
            "made_field_goals, attempted_field_goals, made_three_point_field_goals, "
            "attempted_three_point_field_goals, made_free_throws, attempted_free_throws "
            "FROM basic_stats",
            con,
        )
        scoring_profile = pd.read_sql(
            "SELECT slug, pct_uast_fgm, made_field_goals FROM scoring_profile", con
        )
        scoring_plus = pd.read_sql(
            "SELECT slug, scoring_plus, ts_plus, pts_plus, minutes_played FROM scoring_plus", con
        )
        advanced_stats = pd.read_sql(
            "SELECT slug, offensive_win_shares, offensive_box_plus_minus FROM advanced_stats", con
        )
    return basic_stats, scoring_profile, scoring_plus, advanced_stats


def _weighted_average(df: pd.DataFrame, value_col: str, weight_col: str) -> pd.Series:
    """Per-slug weighted average of value_col by weight_col; NaN where total weight is 0."""
    weighted_sum = (df[value_col] * df[weight_col]).groupby(df["slug"]).sum()
    weight_total = df[weight_col].groupby(df["slug"]).sum()
    return (weighted_sum / weight_total.replace(0, np.nan)).rename(value_col)


def compute_career_averages(
    basic_stats: pd.DataFrame,
    scoring_profile: pd.DataFrame,
    scoring_plus: pd.DataFrame,
    advanced_stats: pd.DataFrame,
) -> pd.DataFrame:
    basic_stats = basic_stats.sort_values(["slug", "season_end_year"]).copy()
    basic_stats["total_rebounds"] = basic_stats["offensive_rebounds"] + basic_stats["defensive_rebounds"]

    totals = basic_stats.groupby("slug").agg(
        player_name=("name", "last"),
        seasons_played=("season_end_year", "count"),
        games_played=("games_played", "sum"),
        minutes_played=("minutes_played", "sum"),
        points=("points", "sum"),
        assists=("assists", "sum"),
        total_rebounds=("total_rebounds", "sum"),
        offensive_rebounds=("offensive_rebounds", "sum"),
        turnovers=("turnovers", "sum"),
        steals=("steals", "sum"),
        blocks=("blocks", "sum"),
        made_field_goals=("made_field_goals", "sum"),
        attempted_field_goals=("attempted_field_goals", "sum"),
        made_three_point_field_goals=("made_three_point_field_goals", "sum"),
        attempted_three_point_field_goals=("attempted_three_point_field_goals", "sum"),
        made_free_throws=("made_free_throws", "sum"),
        attempted_free_throws=("attempted_free_throws", "sum"),
    )

    gp = totals["games_played"].replace(0, np.nan)
    totals["points_per_game"] = totals["points"] / gp
    totals["assists_per_game"] = totals["assists"] / gp
    totals["total_rebounds_per_game"] = totals["total_rebounds"] / gp
    totals["offensive_rebounds_per_game"] = totals["offensive_rebounds"] / gp
    totals["turnovers_per_game"] = totals["turnovers"] / gp
    totals["steals_per_game"] = totals["steals"] / gp
    totals["blocks_per_game"] = totals["blocks"] / gp
    totals["fgm_per_game"] = totals["made_field_goals"] / gp
    totals["fga_per_game"] = totals["attempted_field_goals"] / gp
    totals["three_pm_per_game"] = totals["made_three_point_field_goals"] / gp
    totals["three_pa_per_game"] = totals["attempted_three_point_field_goals"] / gp
    totals["ftm_per_game"] = totals["made_free_throws"] / gp
    totals["fta_per_game"] = totals["attempted_free_throws"] / gp
    totals["minutes_per_game"] = totals["minutes_played"] / gp

    totals["fg_percentage"] = (
        totals["made_field_goals"] / totals["attempted_field_goals"].replace(0, np.nan)
    )
    totals["three_point_percentage"] = (
        totals["made_three_point_field_goals"]
        / totals["attempted_three_point_field_goals"].replace(0, np.nan)
    )
    totals["ft_percentage"] = (
        totals["made_free_throws"] / totals["attempted_free_throws"].replace(0, np.nan)
    )
    totals["true_shooting_percentage"] = totals["points"] / (
        2 * (totals["attempted_field_goals"] + 0.44 * totals["attempted_free_throws"])
    ).replace(0, np.nan)

    uast_weighted = _weighted_average(scoring_profile, "pct_uast_fgm", "made_field_goals")
    scoring_plus_weighted = _weighted_average(scoring_plus, "scoring_plus", "minutes_played")
    ts_plus_weighted = _weighted_average(scoring_plus, "ts_plus", "minutes_played")
    pts_plus_weighted = _weighted_average(scoring_plus, "pts_plus", "minutes_played")
    ows_obpm_totals = advanced_stats.groupby("slug")[
        ["offensive_win_shares", "offensive_box_plus_minus"]
    ].sum()

    df = totals.join([
        uast_weighted, scoring_plus_weighted, ts_plus_weighted, pts_plus_weighted, ows_obpm_totals,
    ])
    df = df.reset_index()

    return df[[
        "slug", "player_name", "seasons_played", "games_played", "minutes_per_game",
        "points_per_game", "assists_per_game", "total_rebounds_per_game",
        "offensive_rebounds_per_game", "turnovers_per_game", "steals_per_game", "blocks_per_game",
        "fgm_per_game", "fga_per_game", "three_pm_per_game", "three_pa_per_game",
        "ftm_per_game", "fta_per_game",
        "fg_percentage", "three_point_percentage", "ft_percentage", "true_shooting_percentage",
        "pct_uast_fgm", "scoring_plus", "ts_plus", "pts_plus",
        "offensive_win_shares", "offensive_box_plus_minus",
    ]]


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("career_averages", con, if_exists="replace", index=False)
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_career_averages_slug ON career_averages (slug)"
        )
    print(f"Saved career_averages: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    basic_stats, scoring_profile, scoring_plus, advanced_stats = load_tables()
    career_averages_df = compute_career_averages(basic_stats, scoring_profile, scoring_plus, advanced_stats)
    save_to_sqlite(career_averages_df)
    print(career_averages_df.head())
