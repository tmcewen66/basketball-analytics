#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Creates a new statistic that attempts to combine a player's volume of scoring
(per-100-possessions points) with their efficiency (true shooting percentage)
relative to the league average for that season. This number is based on statistics
that are common in baseball such as ERA+ and OPS+, which compare a player's
performance to the league average and adjust for context.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"


def load_tables(
    db_path: str = DB_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        per_100 = pd.read_sql("SELECT season_end_year, slug, team_id, per_100_pts FROM per_100_stats", con)
        advanced = pd.read_sql("SELECT season_end_year, slug, name, true_shooting_percentage FROM advanced_stats", con)
        league_avg = pd.read_sql("SELECT season_end_year, league_avg_true_shooting_percentage FROM league_averages", con)
        nba_per_100_avg = pd.read_sql("SELECT season_end_year, per_100_pts FROM nba_per_100_averages", con)
        basic = pd.read_sql("SELECT season_end_year, slug, minutes_played FROM basic_stats", con)
        team_per_100 = pd.read_sql("SELECT season_end_year, team_id, gp FROM team_per_100_stats", con)
    return per_100, advanced, league_avg, nba_per_100_avg, basic, team_per_100


def compute_scoring_plus(
    per_100: pd.DataFrame,
    advanced: pd.DataFrame,
    league_avg: pd.DataFrame,
    nba_per_100_avg: pd.DataFrame,
    basic: pd.DataFrame,
    team_per_100: pd.DataFrame,
) -> pd.DataFrame:
    df = per_100.merge(advanced, on=["slug", "season_end_year"])
    df = df.merge(league_avg, on="season_end_year")
    df = df.merge(
        nba_per_100_avg.rename(columns={"per_100_pts": "league_avg_per_100_pts_per_player"}),
        on="season_end_year",
    )
    df["league_avg_per_100_pts_per_player"] /= 5.0

    df["pts_plus"] = df["per_100_pts"] / df["league_avg_per_100_pts_per_player"] * 100
    df["ts_plus"] = df["true_shooting_percentage"] / df["league_avg_true_shooting_percentage"] * 100
    df["scoring_plus"] = 100 + (0.765 * (df["ts_plus"] - 100)) + (0.235 * (df["pts_plus"] - 100))

    df = df.merge(basic, on=["slug", "season_end_year"])
    df = df.merge(team_per_100.rename(columns={"gp": "team_gp"}), on=["team_id", "season_end_year"])

    df["threshold"] = 1500 * (df["team_gp"] / 82)
    df["qualified"] = df["minutes_played"] >= df["threshold"]

    return df[[
        "season_end_year", "slug", "name", "per_100_pts", "true_shooting_percentage",
        "league_avg_per_100_pts_per_player", "league_avg_true_shooting_percentage",
        "pts_plus", "ts_plus", "scoring_plus",
        "team_gp", "minutes_played", "threshold", "qualified",
    ]]


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("scoring_plus", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_scoring_plus_slug_season "
            "ON scoring_plus (slug, season_end_year)"
        )
    print(f"Saved scoring_plus: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    per_100, advanced, league_avg, nba_per_100_avg, basic, team_per_100 = load_tables()
    scoring_plus_df = compute_scoring_plus(per_100, advanced, league_avg, nba_per_100_avg, basic, team_per_100)
    save_to_sqlite(scoring_plus_df)
    print(scoring_plus_df.head())
