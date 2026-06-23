# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python project for building season-adjusted advanced NBA analytics. Data is sourced from Basketball-Reference via the `basketball_reference_web_scraper` package (v4.15.4, by jaebradley).

## Python Environment

**Always use Anaconda Python**, not the system Python 3.11:
```bash
/opt/anaconda3/bin/python3 brdatascraping.py
```
The package is installed in `/opt/anaconda3/lib/python3.12/site-packages`. Running with the system `python3` will fail with `ModuleNotFoundError`.

## Key Package: basketball_reference_web_scraper

Import and usage:
```python
from basketball_reference_web_scraper import client

# Basic season totals (season_end_year: 2024 = 2023-24 season)
rows = client.players_season_totals(season_end_year=2024)

# Advanced stats (PER, TS%, WS, BPM, VORP, etc.)
rows = client.players_advanced_season_totals(season_end_year=2024, include_combined_values=True)

# Search for a player
results = client.search(term="LeBron James")
```

Other available client methods: `player_box_scores`, `regular_season_player_box_scores`, `playoff_player_box_scores`, `team_box_scores`, `standings`, `season_schedule`, `play_by_play`.

## Git Workflow

After completing any meaningful piece of work, commit and push to GitHub so progress is never lost. This project is not yet a git repo — initialize and push before doing anything else if that hasn't been done.

- Commit after each logical unit of work (new feature, bug fix, schema change, etc.)
- Write clear, descriptive commit messages that explain what changed and why
- Push to GitHub after every commit — don't let commits pile up locally
- Never leave the repo in a broken state before pushing

## Rate Limiting

Always add a delay between requests (`time.sleep(3)` minimum) — Basketball-Reference will block rapid scraping. The `REQUEST_DELAY_SECONDS` constant in `brdatascraping.py` controls this.

## Traded Players

`include_combined_values=True` in `players_advanced_season_totals` retains the combined-season row for players traded mid-season alongside their per-team rows. Filter on `team` to deduplicate when needed.
