#!/usr/bin/env /opt/anaconda3/bin/python3
"""
Creates a team-level analog of scoring_plus: combines each team's offensive
rating and true shooting percentage with the league average for that season
to produce team_scoring_plus, team_pts_plus, and team_ts_plus, plus each
team's 1-30 (best-to-worst) rank within its season for those three metrics.
"""

import sqlite3
import pandas as pd

DB_PATH = "nba_stats.db"


def load_tables(db_path: str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        team_advanced_stats = pd.read_sql("SELECT * FROM team_advanced_stats", con)
        nba_advanced_averages = pd.read_sql("SELECT * FROM nba_advanced_averages", con)
    return team_advanced_stats, nba_advanced_averages


def compute_team_scoring_plus(
    team_advanced_stats: pd.DataFrame, nba_advanced_averages: pd.DataFrame
) -> pd.DataFrame:
    df = team_advanced_stats.merge(
        nba_advanced_averages[["season_end_year", "off_rating", "ast_pct", "ts_pct"]].rename(columns={
            "off_rating": "league_off_rating",
            "ast_pct": "league_ast_pct",
            "ts_pct": "league_ts_pct",
        }),
        on="season_end_year",
    )

    df["team_pts_plus"] = (df["off_rating"] / df["league_off_rating"]) * 100
    df["team_ts_plus"] = (df["ts_pct"] / df["league_ts_pct"]) * 100
    df["team_scoring_plus"] = (
        100
        + (0.765 * (df["team_ts_plus"] - 100))
        + (0.235 * (df["team_pts_plus"] - 100))
    )

    for col in ("team_scoring_plus", "team_pts_plus", "team_ts_plus"):
        df[f"{col}_rank"] = (
            df.groupby("season_end_year")[col].rank(method="min", ascending=False).astype(int)
        )

    return df[[
        "season_end_year", "team_id", "team_name", "gp", "w", "l", "w_pct",
        "off_rating", "ast_pct", "ts_pct",
        "league_off_rating", "league_ast_pct", "league_ts_pct",
        "team_scoring_plus", "team_pts_plus", "team_ts_plus",
        "team_scoring_plus_rank", "team_pts_plus_rank", "team_ts_plus_rank",
    ]]


def save_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql("team_scoring_plus", con, if_exists="replace", index=False)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_team_scoring_plus_team_season "
            "ON team_scoring_plus (team_id, season_end_year)"
        )
    print(f"Saved team_scoring_plus: {len(df)} rows -> {db_path}")


if __name__ == "__main__":
    team_advanced_stats, nba_advanced_averages = load_tables()
    team_scoring_plus_df = compute_team_scoring_plus(team_advanced_stats, nba_advanced_averages)
    save_to_sqlite(team_scoring_plus_df)
    print(team_scoring_plus_df.head())
