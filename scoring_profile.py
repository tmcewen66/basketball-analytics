#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Builds a scoring_profile table that classifies each player-season by how much
of their scoring comes unassisted (pct_uast_fgm from scoring_splits), relative
to that season's qualified-player distribution. Qualification mirrors the
made-field-goals-based threshold from scoring_profile_analysis.ipynb, prorated
by team games played the same way scoring_plus.py prorates its minutes
threshold. The uast_bin/uast_rating/profile columns reproduce the percentile
binning developed in that notebook.
"""

import sqlite3
import numpy as np
import pandas as pd

DB_PATH = "nba_stats.db"
NUM_BINS = 9
FULL_SEASON_MADE_FIELD_GOAL_THRESHOLD = 300  # NBA's standard for the FG% leaderboard


def load_tables(db_path: str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        scoring_splits = pd.read_sql(
            "SELECT season_end_year, slug, player_id, player_name, team_id, "
            "team_abbreviation, age, gp, pct_uast_fgm FROM scoring_splits",
            con,
        )
        basic = pd.read_sql(
            "SELECT slug, season_end_year, made_field_goals FROM basic_stats",
            con,
        )
        team_per_100 = pd.read_sql(
            "SELECT season_end_year, team_id, team_name, gp FROM team_per_100_stats",
            con,
        )
    return scoring_splits, basic, team_per_100


def compute_season_cutoffs(qualified: pd.DataFrame, num_bins: int = NUM_BINS) -> pd.DataFrame:
    percentile_fractions = [i / num_bins for i in range(1, num_bins)]
    cutoffs = (
        qualified.groupby("season_end_year")["pct_uast_fgm"]
        .quantile(percentile_fractions)  # type: ignore[arg-type]
        .unstack()
    )
    cutoffs.columns = [f"{p * 100:.2f}_percentile" for p in percentile_fractions]
    return cutoffs.reset_index()


def compute_scoring_profile(
    scoring_splits: pd.DataFrame, basic: pd.DataFrame, team_per_100: pd.DataFrame
) -> pd.DataFrame:
    df = scoring_splits.merge(basic, on=["slug", "season_end_year"])
    df = df.merge(team_per_100.rename(columns={"gp": "team_gp"}), on=["team_id", "season_end_year"])

    df["age"] = df["age"].astype(float)
    df["threshold"] = FULL_SEASON_MADE_FIELD_GOAL_THRESHOLD * (df["team_gp"] / 82)
    df["qualified"] = df["made_field_goals"] >= df["threshold"]

    cutoffs_df = compute_season_cutoffs(df[df["qualified"]])
    cutoff_cols = [c for c in cutoffs_df.columns if c != "season_end_year"]

    # Look up each row's season cutoffs, keeping order aligned with df so the
    # comparisons below can be done position-wise instead of by index label.
    season_cutoffs = df[["season_end_year"]].merge(cutoffs_df, on="season_end_year", how="left")

    # A value exactly on a cutoff falls into the lower bin (bin edges are exclusive on the low end).
    df["uast_bin"] = 1 + sum(
        (df["pct_uast_fgm"].values > season_cutoffs[col].values).astype(int)  # type: ignore
        for col in cutoff_cols
    )
    # Centers bin 5 (the middle bin) at 0, running from -4 (bin 1) to 4 (bin 9).
    df["uast_rating"] = df["uast_bin"] - 5
    df["profile"] = np.select(
        [df["uast_rating"] <= -2, df["uast_rating"] <= 1],
        ["Finisher", "Balanced"],
        default="Creator",
    )

    return df[[
        "season_end_year", "slug", "player_id", "player_name", "team_id", "team_abbreviation",
        "team_name", "age", "gp", "team_gp", "pct_uast_fgm", "made_field_goals", "threshold",
        "qualified", "uast_bin", "uast_rating", "profile",
    ]]


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("scoring_profile", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_scoring_profile_slug_season "
            "ON scoring_profile (slug, season_end_year)"
        )
    print(f"Saved scoring_profile: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    scoring_splits, basic, team_per_100 = load_tables()
    scoring_profile_df = compute_scoring_profile(scoring_splits, basic, team_per_100)
    save_to_sqlite(scoring_profile_df)
    print(scoring_profile_df.head())
