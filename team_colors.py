#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Loads teamcolors.csv into a DataFrame of team primary/secondary colors.
"""

import sqlite3

import pandas as pd

CSV_PATH = "teamcolors.csv"
DB_PATH = "nba_stats.db"


def load_team_colors(csv_path: str = CSV_PATH) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("team_colors", con, if_exists="replace", index=False)


if __name__ == "__main__":
    team_colors_df = load_team_colors()
    print(team_colors_df)
    save_to_sqlite(team_colors_df)
