#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Computes league-average per-100-possession stats per season from the
team_per_100_stats table (nbadatascraping.py) and saves them to a new
nba_per_100_averages table in nba_stats.db.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"

# Team identifiers and *_rank columns aren't meaningful once averaged league-wide
_EXCLUDE_COLS = {"team_id", "team_name", "season_end_year"}


def load_team_stats(db_path: str = DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql("SELECT * FROM team_per_100_stats", con)


def compute_league_averages(team_stats: pd.DataFrame) -> pd.DataFrame:
    stat_cols = [
        col for col in team_stats.columns
        if col not in _EXCLUDE_COLS and not col.endswith("_rank")
    ]
    return (
        team_stats.groupby("season_end_year")[stat_cols]
        .mean()
        .reset_index()
    )


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("nba_per_100_averages", con, if_exists="replace", index=False)
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_nba_per_100_averages_season "
            "ON nba_per_100_averages (season_end_year)"
        )
    print(f"Saved nba_per_100_averages: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    team_stats = load_team_stats()
    league_averages_df = compute_league_averages(team_stats)
    save_to_sqlite(league_averages_df)
    print(league_averages_df)
