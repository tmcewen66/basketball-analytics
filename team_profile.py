#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Builds team_profile: the team-level analog of player_profile, used by the
Streamlit app for team-related queries. Starts from team_scoring_plus and
adds shooting percentages from team_per_100_stats.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"


def load_tables(db_path: str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        team_scoring_plus = pd.read_sql("SELECT * FROM team_scoring_plus", con)
        team_per_100_stats = pd.read_sql(
            "SELECT team_id, season_end_year, per_100_fg_pct, per_100_fg3_pct, per_100_ft_pct "
            "FROM team_per_100_stats",
            con,
        )
        player_profile = pd.read_sql(
            "SELECT team_id, season_end_year, profile FROM player_profile", con
        )
    return team_scoring_plus, team_per_100_stats, player_profile


def compute_team_profile(
    team_scoring_plus: pd.DataFrame, team_per_100_stats: pd.DataFrame, player_profile: pd.DataFrame
) -> pd.DataFrame:
    df = team_scoring_plus.merge(
        team_per_100_stats.rename(columns={
            "per_100_fg_pct": "team_fg_pct",
            "per_100_fg3_pct": "team_3pt_pct",
            "per_100_ft_pct": "team_ft_pct",
        }),
        on=["team_id", "season_end_year"],
    )

    # A traded player's single player_profile row carries their final team's team_id,
    # so they're counted toward that team only, not every team they played for.
    profile_counts = (
        player_profile.groupby(["team_id", "season_end_year", "profile"])
        .size()
        .unstack("profile", fill_value=0)
        .rename(columns={"Finisher": "Finishers", "Balanced": "Balanced", "Creator": "Creators"})
        .reset_index()
    )
    for col in ("Finishers", "Balanced", "Creators"):
        if col not in profile_counts.columns:
            profile_counts[col] = 0

    df = df.merge(
        profile_counts[["team_id", "season_end_year", "Finishers", "Balanced", "Creators"]],
        on=["team_id", "season_end_year"],
        how="left",
    )
    df[["Finishers", "Balanced", "Creators"]] = (
        df[["Finishers", "Balanced", "Creators"]].fillna(0).astype(int)
    )

    return df


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("team_profile", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_team_profile_team_season "
            "ON team_profile (team_id, season_end_year)"
        )
    print(f"Saved team_profile: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    team_scoring_plus, team_per_100_stats, player_profile = load_tables()
    team_profile_df = compute_team_profile(team_scoring_plus, team_per_100_stats, player_profile)
    save_to_sqlite(team_profile_df)
    print(team_profile_df.head())
