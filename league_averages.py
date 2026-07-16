#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Computes league-average True Shooting % per season from the basic_stats
table in nba_stats.db.

TS% = PTS / (2 * (FGA + 0.44 * FTA)), aggregated league-wide (not averaged
per-player) so it matches Basketball-Reference's published league averages.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"

LEAGUE_AVG_TS_QUERY = """
SELECT season_end_year,
    SUM(points) * 1.0 / (2.0 * (SUM(attempted_field_goals) + 0.44 * SUM(attempted_free_throws))) AS league_avg_ts_pct
FROM basic_stats
GROUP BY season_end_year
"""


def compute_league_avg_ts(db_path: str = DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql_query(LEAGUE_AVG_TS_QUERY, con)


if __name__ == "__main__":
    league_avg_ts_df = compute_league_avg_ts()
    pd.set_option("display.max_rows", None)
    print(league_avg_ts_df)
