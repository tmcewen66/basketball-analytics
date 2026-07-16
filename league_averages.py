#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Scrapes the NBA league-average per-100-possession stats table from
Basketball-Reference. The whole history lives on one page, so this fetches
it once and keeps the seasons from 2000-01 onward.

Source: https://www.basketball-reference.com/leagues/NBA_stats_per_poss.html
"""

import io
import sqlite3
import pandas as pd
import requests

URL = "https://www.basketball-reference.com/leagues/NBA_stats_per_poss.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; nba-stats-research/1.0)"}
DB_PATH = "nba_stats.db"
FIRST_SEASON_END_YEAR = 2001  # 2000-01 season

COLUMN_MAP = {
    "Season": "season_label",
    "Age": "average_age",
    "Ht": "average_height",
    "Wt": "average_weight",
    "G": "games_played",
    "FG": "per_100_fgm",
    "FGA": "per_100_fga",
    "3P": "per_100_fg3m",
    "3PA": "per_100_fg3a",
    "FT": "per_100_ftm",
    "FTA": "per_100_fta",
    "ORB": "per_100_oreb",
    "DRB": "per_100_dreb",
    "TRB": "per_100_reb",
    "AST": "per_100_ast",
    "STL": "per_100_stl",
    "BLK": "per_100_blk",
    "TOV": "per_100_tov",
    "PF": "per_100_pf",
    "PTS": "per_100_pts",
    "FG%": "fg_percentage",
    "3P%": "three_point_percentage",
    "FT%": "ft_percentage",
    "Pace": "pace",
    "eFG%": "effective_fg_percentage",
    "TOV%": "turnover_percentage",
    "ORB%": "offensive_rebound_percentage",
    "FT/FGA": "ft_per_fga",
    "ORtg": "offensive_rating",
    "TS%": "true_shooting_percentage",
}

NUMERIC_COLS = [c for c in COLUMN_MAP.values() if c not in ("season_label", "average_height")]


def fetch_league_averages() -> pd.DataFrame:
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    df = pd.read_html(io.StringIO(resp.text), attrs={"id": "stats-Regular-Season"})[0]
    df.columns = [col[1] for col in df.columns]  # drop the multi-index group labels

    # Repeated header rows and pre-merger BAA seasons are interspersed in the table
    df = df[df["Lg"] == "NBA"].drop(columns=["Rk", "Lg"])
    df = df.rename(columns=COLUMN_MAP)

    df["season_end_year"] = df["season_label"].str.slice(0, 4).astype(int) + 1
    df = df[df["season_end_year"] >= FIRST_SEASON_END_YEAR]

    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_values("season_end_year").reset_index(drop=True)


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("league_averages", con, if_exists="replace", index=False)
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_league_averages_season "
            "ON league_averages (season_end_year)"
        )
    print(f"Saved league_averages: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    league_averages_df = fetch_league_averages()
    save_to_sqlite(league_averages_df)
    print(league_averages_df[["season_end_year", "true_shooting_percentage", "pace", "offensive_rating"]])
