#!/usr/bin/env /opt/anaconda3/bin/python3
import re
import sqlite3
import unicodedata

DB_PATH = "nba_stats.db"


_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv)\b")
_CHAR_MAP = str.maketrans({"ı": "i", "İ": "i", "ß": "ss"})

# Manual slug → player_id overrides for players whose names differ fundamentally
# between Basketball-Reference and NBA.com (nicknames, abbreviations, middle names)
_MANUAL_OVERRIDES: dict[str, int] = {
    "murraro01": 2436,    # Ronald Murray → Flip Murray
    "medvest01": 2098,    # Stanislav Medvedenko → Slava Medvedenko
    "sweetmi01": 2552,    # Mike Sweetney → Michael Sweetney
    "favervi01": 203543,  # Vítor Luiz Faverani → Vitor Faverani
    "weathcl01": 221,     # Clarence Weatherspoon → Clar. Weatherspoon
    "balad01":   1642380, # Adama-Alpha Bal → Adama Bal
    "reynoca01": 1629244, # Cameron Reynolds → Cam Reynolds
    "cuiyo01":   1642385, # Cui Yongxi → Cui Cui
    "demineg01": 1642856, # Egor Dёmin → Egor Dëmin
    "seungha01": 2775,    # Ha Seung-Jin → Ha Ha
    "kutluib01": 2825,    # Ibo Kutluay → Ibrahim Kutluay
    "austiis01": 1134,    # Isaac Austin → Ike Austin
    "fontais01": 1829,    # Isaac Fontaine → Ike Fontaine
    "tayloje03": 203106,  # Jeff Taylor → Jeffery Taylor
    "hurtma01":  1630562, # Matthew Hurt → Matt Hurt
    "creekmi01": 1628249, # Mitch Creek → Mitchell Creek
    "richano01": 2369,    # Norm Richardson → Norman Richardson
    "jetereu01": 200817,  # Eugene Jeter → Pooh Jeter
    "hollaro01": 1641842, # Ron Holland → Ronald Holland II
    "nembhrj01": 1630612, # RJ Nembhard Jr. → Ruben Nembhard Jr.
    "smithst01": 120,     # Steve Smith → Steven Smith
    "yuesu01":   201180,  # Sun Yue → Sun Sun
    "scotttr01": 1630286, # Tre Scott → Trevon Scott
    "edwarvi01": 1629053, # Vince Edwards → Vincent Edwards
    "huntevi01": 1626205, # Vince Hunter → Vincent Hunter
}


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/suffixes/punctuation for cross-source name matching."""
    if not name:
        return ""
    # Manual substitutions before NFKD (characters that don't decompose to ASCII)
    name = name.translate(_CHAR_MAP)
    # Decompose accented chars (é → e + combining accent), then drop non-ASCII
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z\s]", "", name)   # remove anything that isn't a letter or space
    name = re.sub(r"\s+", " ", name).strip()
    # Strip generational suffixes (NBA and BR are inconsistent about Jr/Sr/II/III/IV)
    name = _SUFFIX_RE.sub("", name).strip()
    return name


def _create_tables(conn):
    conn.execute("DROP TABLE IF EXISTS br_nba_mapping")
    conn.execute("DROP TABLE IF EXISTS br_players")
    conn.execute("DROP TABLE IF EXISTS nba_players")
    conn.execute("""
        CREATE TABLE br_players (
            slug      TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            from_year INTEGER NOT NULL,
            to_year   INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE nba_players (
            player_id INTEGER PRIMARY KEY,
            name      TEXT NOT NULL,
            from_year INTEGER NOT NULL,
            to_year   INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE br_nba_mapping (
            slug      TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL,
            name      TEXT NOT NULL
        )
    """)
    conn.commit()


def build_br_players_table(conn):
    conn.execute("""
        INSERT OR REPLACE INTO br_players (slug, name, from_year, to_year)
        SELECT slug,
               MAX(name),
               MIN(season_end_year),
               MAX(season_end_year)
        FROM basic_stats
        GROUP BY slug
    """)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM br_players").fetchone()[0]
    print(f"br_players: {count} rows")


def build_nba_players_table(conn):
    conn.execute("""
        INSERT OR REPLACE INTO nba_players (player_id, name, from_year, to_year)
        SELECT PLAYER_ID,
               MAX(PLAYER_NAME),
               MIN(season_end_year),
               MAX(season_end_year)
        FROM per_100_stats
        GROUP BY PLAYER_ID
    """)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM nba_players").fetchone()[0]
    print(f"nba_players: {count} rows")


def build_mapping_table(conn):
    # For each BR slug, pick the NBA player with the most career-year overlap.
    # MIN(player_id) breaks ties deterministically.
    conn.execute("""
        INSERT INTO br_nba_mapping (slug, player_id, name)
        WITH matches AS (
            SELECT br.slug,
                   nba.player_id,
                   br.name,
                   MIN(br.to_year, nba.to_year) - MAX(br.from_year, nba.from_year) AS overlap
            FROM br_players  br
            JOIN nba_players nba
              ON normalize_name(br.name) = normalize_name(nba.name)
             AND MAX(br.from_year, nba.from_year) <= MIN(br.to_year, nba.to_year)
        )
        SELECT slug,
               MIN(player_id),
               name
        FROM matches
        GROUP BY slug
        HAVING overlap = MAX(overlap)
    """)
    conn.commit()

    # Apply manual overrides for players with fundamentally different names
    for slug, player_id in _MANUAL_OVERRIDES.items():
        already = conn.execute("SELECT 1 FROM br_nba_mapping WHERE slug=?", (slug,)).fetchone()
        if not already:
            br_name = conn.execute("SELECT name FROM br_players WHERE slug=?", (slug,)).fetchone()
            if br_name:
                conn.execute(
                    "INSERT OR IGNORE INTO br_nba_mapping (slug, player_id, name) VALUES (?, ?, ?)",
                    (slug, player_id, br_name[0]),
                )
    conn.commit()

    total     = conn.execute("SELECT COUNT(*) FROM br_nba_mapping").fetchone()[0]
    unmatched = conn.execute("""
        SELECT COUNT(*) FROM br_players
        WHERE slug NOT IN (SELECT slug FROM br_nba_mapping)
    """).fetchone()[0]

    print(f"br_nba_mapping: {total} rows matched")
    if unmatched:
        print(f"  Note: {unmatched} BR slugs had no NBA match (likely below per_100_stats minimum)")
        for row in conn.execute("""
            SELECT slug, name FROM br_players
            WHERE slug NOT IN (SELECT slug FROM br_nba_mapping)
        """):
            print(f"    unmatched: {row}")


def _ensure_slug_column(conn):
    # nbadatascraping.py rebuilds per_100_stats with if_exists="replace" on every
    # run, which drops this column since the nba_api source data has no slug —
    # re-add it here so this script works regardless of table state.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(per_100_stats)")}
    if "slug" not in cols:
        conn.execute("ALTER TABLE per_100_stats ADD COLUMN slug TEXT")
        conn.commit()


def main(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.create_function("normalize_name", 1, normalize_name)
    _create_tables(conn)
    build_br_players_table(conn)
    build_nba_players_table(conn)
    build_mapping_table(conn)

    # Refresh slug column in per_100_stats from the updated mapping
    _ensure_slug_column(conn)
    conn.execute("""
        UPDATE per_100_stats
        SET slug = (
            SELECT slug FROM br_nba_mapping
            WHERE player_id = per_100_stats.PLAYER_ID
        )
    """)
    conn.commit()
    nulls = conn.execute("SELECT COUNT(*) FROM per_100_stats WHERE slug IS NULL").fetchone()[0]
    print(f"per_100_stats.slug refreshed — {nulls} rows still NULL (no BR counterpart)")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
