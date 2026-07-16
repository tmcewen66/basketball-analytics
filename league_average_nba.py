#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Computes league-average stats per season from the team_per_100_stats and
team_advanced_stats tables (nbadatascraping.py) and saves them to new
nba_per_100_averages and nba_advanced_averages tables in nba_stats.db.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"

# Team identifiers and *_rank columns aren't meaningful once averaged league-wide
_EXCLUDE_COLS = {"team_id", "team_name", "season_end_year", "gp", "w", "l", "w_pct"}


def load_team_stats(table_name: str, db_path: str = DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql(f"SELECT * FROM {table_name}", con)


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


def save_to_sqlite(df: pd.DataFrame, table_name: str, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql(table_name, con, if_exists="replace", index=False)
        con.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_season "
            f"ON {table_name} (season_end_year)"
        )
    print(f"Saved {table_name}: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    per_100_averages_df = compute_league_averages(load_team_stats("team_per_100_stats"))
    save_to_sqlite(per_100_averages_df, "nba_per_100_averages")
    print(per_100_averages_df)

    advanced_averages_df = compute_league_averages(load_team_stats("team_advanced_stats"))
    save_to_sqlite(advanced_averages_df, "nba_advanced_averages")
    print(advanced_averages_df)
