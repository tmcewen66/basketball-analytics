#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Builds a player_profile table that combines scoring_plus (era-adjusted
scoring metrics) with traditional per-game shooting splits from
derived_stats, for a single at-a-glance view of a player-season.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"


def load_tables(db_path: str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        scoring_plus = pd.read_sql(
            "SELECT slug, season_end_year, name, per_100_pts, true_shooting_percentage, "
            "pts_plus, ts_plus, scoring_plus, qualified FROM scoring_plus",
            con,
        )
        derived = pd.read_sql(
            "SELECT slug, season_end_year, age, positions, team, points_per_game, fg_percentage, "
            "three_point_percentage, ft_percentage, assists_per_game, total_rebounds_per_game, "
            "turnovers_per_game, steals_per_game, blocks_per_game FROM derived_stats",
            con,
        )
        per_100 = pd.read_sql(
            "SELECT slug, season_end_year, per_100_reb, per_100_ast, per_100_stl, per_100_blk, "
            "per_100_tov FROM per_100_stats",
            con,
        )
    return scoring_plus, derived, per_100


def compute_player_profile(scoring_plus: pd.DataFrame, derived: pd.DataFrame, per_100: pd.DataFrame) -> pd.DataFrame:
    df = scoring_plus.merge(derived, on=["slug", "season_end_year"])
    df = df.merge(per_100, on=["slug", "season_end_year"])
    df = df.rename(columns={"name": "player_name", "team": "team_name"})
    df["season"] = (df["season_end_year"] - 1).astype(str) + "-" + df["season_end_year"].astype(str)

    return df[[
        "player_name", "team_name", "season_end_year", "season", "slug",
        "scoring_plus", "pts_plus", "ts_plus", "per_100_pts", "true_shooting_percentage",
        "age", "positions", "points_per_game", "fg_percentage", "three_point_percentage", "ft_percentage",
        "assists_per_game", "total_rebounds_per_game", "turnovers_per_game", "steals_per_game", "blocks_per_game",
        "per_100_reb", "per_100_ast", "per_100_stl", "per_100_blk", "per_100_tov", "qualified",
    ]]


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("player_profile", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_profile_slug_season "
            "ON player_profile (slug, season_end_year)"
        )
    print(f"Saved player_profile: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    scoring_plus, derived, per_100 = load_tables()
    player_profile_df = compute_player_profile(scoring_plus, derived, per_100)
    save_to_sqlite(player_profile_df)
    print(player_profile_df.head())
