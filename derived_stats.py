#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Computes derived advanced stats from the basic_stats and advanced_stats tables
in nba_stats.db and writes them to a derived_stats table.

Add new calculations inside compute_derived_stats() — each column you create
will automatically be persisted to the database.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"


def load_tables(db_path: str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        basic = pd.read_sql("SELECT * FROM basic_stats", con)
        advanced = pd.read_sql("SELECT * FROM advanced_stats", con)
    return basic, advanced


def compute_derived_stats(
    basic: pd.DataFrame, advanced: pd.DataFrame
) -> pd.DataFrame:
    """
    Join basic and advanced stats, then compute derived columns.
    Add new metrics here — one line per stat.
    """
    # Merge on slug + season; suffixes handle duplicate column names (e.g. name, age)
    df = basic.merge(
        advanced,
        on=["slug", "season_end_year"],
        suffixes=("", "_adv"),
        how="inner",
    )

    gp = df["games_played"]
    mp = df["minutes_played"]  # season total minutes

    # --- Shooting ---
    df["fg_percentage"] = df["made_field_goals"] / df["attempted_field_goals"]
    df["three_point_percentage"] = (
        df["made_three_point_field_goals"] / df["attempted_three_point_field_goals"]
    )
    df["ft_percentage"] = df["made_free_throws"] / df["attempted_free_throws"]

    # Effective FG% = (FGM + 0.5 * 3PM) / FGA
    df["effective_fg_percentage"] = (
        df["made_field_goals"] + 0.5 * df["made_three_point_field_goals"]
    ) / df["attempted_field_goals"]

    # --- Per-36-minute rates (better for comparing players with different roles) ---
    counting_cols = [
        "points", "assists", "offensive_rebounds", "defensive_rebounds",
        "steals", "blocks", "turnovers", "personal_fouls",
    ]
    for col in counting_cols:
        df[f"{col}_per_36"] = df[col] / mp * 36

    df["total_rebounds_per_36"] = (
        df["offensive_rebounds"] + df["defensive_rebounds"]
    ) / mp * 36

    # --- Per-game convenience columns ---
    df["points_per_game"] = df["points"] / gp
    df["assists_per_game"] = df["assists"] / gp
    df["total_rebounds_per_game"] = (
        df["offensive_rebounds"] + df["defensive_rebounds"]
    ) / gp
    df["steals_per_game"] = df["steals"] / gp
    df["blocks_per_game"] = df["blocks"] / gp
    df["turnovers_per_game"] = df["turnovers"] / gp
    df["minutes_per_game"] = mp / gp

    # --- Assist-to-turnover ratio ---
    df["assist_to_turnover_ratio"] = df["assists"] / df["turnovers"]

    # --- Stock (steals + blocks per game) ---
    df["stocks_per_game"] = df["steals_per_game"] + df["blocks_per_game"]

    # --- Win Shares per game ---
    df["win_shares_per_game"] = df["win_shares"] / gp

    # Drop the duplicated metadata columns brought in by the merge suffix
    dup_cols = [c for c in df.columns if c.endswith("_adv")]
    df = df.drop(columns=dup_cols)

    return df


def save_derived_stats(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("derived_stats", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_derived_slug_season "
            "ON derived_stats (slug, season_end_year)"
        )
    print(f"Saved derived_stats: {len(df)} rows → {db_path}")


if __name__ == "__main__":
    print("Loading tables...")
    basic, advanced = load_tables()

    print("Computing derived stats...")
    derived = compute_derived_stats(basic, advanced)

    print(f"Derived columns added: {[c for c in derived.columns if c not in list(basic.columns) + list(advanced.columns)]}")

    save_derived_stats(derived)
    print("Done.")
