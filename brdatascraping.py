#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Fetches basic and advanced NBA player season totals from Basketball-Reference
for all seasons from 2000-01 through 2025-26.

Results are stored in two dicts keyed by season_end_year:
    basic_dfs[2024]    -> DataFrame for the 2023-24 season, indexed by slug
    advanced_dfs[2024] -> DataFrame for the 2023-24 season, indexed by slug
"""

import sqlite3
import time
import pandas as pd
from basketball_reference_web_scraper import client

SEASONS = list(range(2001, 2027))  # 2000-01 through 2025-26
REQUEST_DELAY_SECONDS = 3
DB_PATH = "nba_stats.db"

BASIC_NUMERIC_COLS = [
    "games_played", "games_started", "minutes_played",
    "made_field_goals", "attempted_field_goals",
    "made_three_point_field_goals", "attempted_three_point_field_goals",
    "made_free_throws", "attempted_free_throws",
    "offensive_rebounds", "defensive_rebounds",
    "assists", "steals", "blocks", "turnovers", "personal_fouls", "points",
]

# Cumulative columns that get divided by games_played to produce per-game stats
PER_GAME_COLS = [
    "minutes_played",
    "made_field_goals", "attempted_field_goals",
    "made_three_point_field_goals", "attempted_three_point_field_goals",
    "made_free_throws", "attempted_free_throws",
    "offensive_rebounds", "defensive_rebounds",
    "assists", "steals", "blocks", "turnovers", "personal_fouls", "points",
]


def _aggregate_basic(df: pd.DataFrame) -> pd.DataFrame:
    """
    For traded players, basic stats have one row per team with no combined row.
    Sum the numeric columns, take first value for metadata, and build a 'teams'
    column listing every team played for that season (e.g. "DALLAS MAVERICKS/MIAMI HEAT").
    """
    meta = df.groupby("slug")[["name", "positions", "age"]].first()
    teams = df.groupby("slug")["team"].apply(lambda x: "/".join(t.value for t in x))
    numeric = df.groupby("slug")[BASIC_NUMERIC_COLS].sum()
    return meta.join(teams).join(numeric)


def _dedupe_advanced(df: pd.DataFrame) -> pd.DataFrame:
    """
    For traded players, advanced stats include a combined row (is_combined_totals=True)
    alongside per-team rows. Keep only the combined row for traded players so each
    slug appears exactly once.
    """
    counts = df.groupby("slug")["slug"].transform("count")
    traded_mask = counts > 1
    keep = (~traded_mask) | (df["is_combined_totals"] == True)
    return df[keep].drop(columns=["is_combined_totals"]).set_index("slug")


def fetch_all_seasons(seasons=SEASONS):
    """
    Returns (basic_dfs, advanced_dfs) — two dicts of DataFrames, each keyed
    by season_end_year and indexed by player slug.
    """
    basic_dfs = {}
    advanced_dfs = {}

    for year in seasons:
        season_label = f"{year - 1}-{str(year)[-2:]}"
        print(f"Fetching {season_label}...", end=" ", flush=True)

        basic_rows = client.players_season_totals(season_end_year=year)
        basic_df = pd.DataFrame(basic_rows)
        basic_dfs[year] = _aggregate_basic(basic_df)
        time.sleep(REQUEST_DELAY_SECONDS)

        adv_rows = client.players_advanced_season_totals(
            season_end_year=year, include_combined_values=True
        )
        adv_df = pd.DataFrame(adv_rows)
        advanced_dfs[year] = _dedupe_advanced(adv_df)
        time.sleep(REQUEST_DELAY_SECONDS)

        print(
            f"basic={len(basic_dfs[year])} players, "
            f"advanced={len(advanced_dfs[year])} players"
        )

    return basic_dfs, advanced_dfs


def _prepare_for_db(dfs_dict: dict, serialize_team: bool = False) -> pd.DataFrame:
    """
    Concatenates a {season_end_year: DataFrame} dict into one flat DataFrame
    ready for SQLite. Serializes enum columns to strings.
    """
    frames = []
    for year, df in dfs_dict.items():
        df = df.reset_index()  # slug back to column
        df.insert(1, "season_end_year", year)
        df["positions"] = df["positions"].apply(
            lambda p: "/".join(x.value for x in p)
        )
        if serialize_team and "team" in df.columns:
            df["team"] = df["team"].apply(
                lambda t: t.value if t is not None else None
            )
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _compute_per_game(basic_master: pd.DataFrame) -> pd.DataFrame:
    """
    Derives per-game stats by dividing cumulative counting stats by games_played.
    Metadata and games_played/games_started are carried over unchanged.
    """
    pg = basic_master.copy()
    pg[PER_GAME_COLS] = pg[PER_GAME_COLS].div(pg["games_played"], axis=0)
    return pg


def save_to_sqlite(basic_dfs: dict, advanced_dfs: dict, db_path: str = DB_PATH):
    basic_master = _prepare_for_db(basic_dfs, serialize_team=False)
    advanced_master = _prepare_for_db(advanced_dfs, serialize_team=True)
    per_game_master = _compute_per_game(basic_master)

    with sqlite3.connect(db_path) as con:
        basic_master.to_sql("basic_stats", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_basic_slug_season "
            "ON basic_stats (slug, season_end_year)"
        )

        advanced_master.to_sql("advanced_stats", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_advanced_slug_season "
            "ON advanced_stats (slug, season_end_year)"
        )

        per_game_master.to_sql("per_game_stats", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_per_game_slug_season "
            "ON per_game_stats (slug, season_end_year)"
        )

    print(
        f"\nSaved to {db_path}: "
        f"basic_stats={len(basic_master)} rows, "
        f"advanced_stats={len(advanced_master)} rows, "
        f"per_game_stats={len(per_game_master)} rows"
    )


if __name__ == "__main__":
    basic_dfs, advanced_dfs = fetch_all_seasons()
    save_to_sqlite(basic_dfs, advanced_dfs)
    print(f"\nDone. {len(basic_dfs)} seasons loaded and saved to {DB_PATH}.")
