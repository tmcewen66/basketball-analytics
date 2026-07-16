#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Fetches per-100-possessions stats for every NBA player and team from
2000-01 through 2025-26 using the nba_api package and saves them to
SQLite database tables 'per_100_stats' and 'team_per_100_stats' in
nba_stats.db.

Rebuilds the BR-to-NBA slug mapping (br_to_nba_mapping.py) afterward, since
saving per_100_stats replaces the table and drops its slug column. Requires
basic_stats (from brdatascraping.py) to already be populated.
"""

import sqlite3
import time
import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats

import br_to_nba_mapping

DB_PATH = "nba_stats.db"
TABLE_NAME = "per_100_stats"
TEAM_TABLE_NAME = "team_per_100_stats"
REQUEST_DELAY_SECONDS = 3

SEASONS = list(range(2001, 2027))  # 2000-01 through 2025-26

# Stat columns that get the per_100_ prefix; everything else is just lowercased
_PER_100_STAT_COLS = {
    "MIN", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT",
    "FTM", "FTA", "FT_PCT", "OREB", "DREB", "REB", "AST", "TOV",
    "STL", "BLK", "BLKA", "PF", "PFD", "PTS", "PLUS_MINUS",
    "NBA_FANTASY_PTS", "WNBA_FANTASY_PTS",
}


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        col: f"per_100_{col.lower()}" if col.upper() in _PER_100_STAT_COLS else col.lower()
        for col in df.columns
    })


def _season_str(end_year: int) -> str:
    return f"{end_year - 1}-{str(end_year)[-2:]}"


def fetch_season(end_year: int) -> pd.DataFrame:
    df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=_season_str(end_year),
        per_mode_detailed="Per100Possessions",
        timeout=60,
    ).get_data_frames()[0]
    df.insert(0, "season_end_year", end_year)
    return df


def fetch_all_seasons(seasons: list = SEASONS) -> pd.DataFrame:
    frames = []
    for year in seasons:
        print(f"Fetching {_season_str(year)}...", end=" ", flush=True)
        try:
            df = fetch_season(year)
            print(f"{len(df)} players")
            frames.append(df)
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)
    return pd.concat(frames, ignore_index=True)


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH):
    df = _rename_columns(df)
    with sqlite3.connect(db_path) as con:
        df.to_sql(TABLE_NAME, con, if_exists="replace", index=False)
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_per100_player_season "
            f"ON {TABLE_NAME} (player_id, season_end_year)"
        )
    print(f"Saved {len(df)} rows to {db_path} table '{TABLE_NAME}'.")


def fetch_team_season(end_year: int) -> pd.DataFrame:
    df = leaguedashteamstats.LeagueDashTeamStats(
        season=_season_str(end_year),
        per_mode_detailed="Per100Possessions",
        timeout=60,
    ).get_data_frames()[0]
    df.insert(0, "season_end_year", end_year)
    return df


def fetch_all_team_seasons(seasons: list = SEASONS) -> pd.DataFrame:
    frames = []
    for year in seasons:
        print(f"Fetching {_season_str(year)} teams...", end=" ", flush=True)
        try:
            df = fetch_team_season(year)
            print(f"{len(df)} teams")
            frames.append(df)
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)
    return pd.concat(frames, ignore_index=True)


def save_team_stats_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH):
    df = _rename_columns(df)
    with sqlite3.connect(db_path) as con:
        df.to_sql(TEAM_TABLE_NAME, con, if_exists="replace", index=False)
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_team_per100_team_season "
            f"ON {TEAM_TABLE_NAME} (team_id, season_end_year)"
        )
    print(f"Saved {len(df)} rows to {db_path} table '{TEAM_TABLE_NAME}'.")


if __name__ == "__main__":
    master_df = fetch_all_seasons()
    save_to_sqlite(master_df)
    print(f"Done. {master_df['season_end_year'].nunique()} seasons loaded.")

    print("\nRebuilding BR-to-NBA slug mapping...")
    br_to_nba_mapping.main()

    team_master_df = fetch_all_team_seasons()
    save_team_stats_to_sqlite(team_master_df)
    print(f"Done. {team_master_df['season_end_year'].nunique()} seasons of team stats loaded.")
