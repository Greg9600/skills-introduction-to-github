#!/usr/bin/env python3
"""
MLB Betting Analyzer
====================
A command-line tool that pulls live and historical MLB data from ESPN,
builds statistical run-distribution models, and outputs betting probabilities
for moneylines, totals, run lines, NRFI/YRFI, team totals, and more.

Usage examples
--------------
# Show today's games
python main.py games

# Full pre-game analysis for Yankees (home) vs Red Sox (away)
python main.py analyze --home "yankees" --away "red sox" --total 9.0

# Inning-by-inning preview
python main.py innings --home "dodgers" --away "giants"

# NRFI / YRFI
python main.py nrfi --home "cubs" --away "cardinals"

# Live win probability
python main.py live --home "mets" --away "braves" \\
    --home-runs 3 --away-runs 1 --inning 7 --half top --outs 1

# Scan for value vs. sportsbook lines
python main.py value --home "astros" --away "rangers" \\
    --total 8.5 --home-ml -145 --away-ml +125
"""

import sys
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from analyzer.data_fetcher import ESPNDataFetcher
from analyzer.stats_calculator import StatsCalculator
from analyzer.probability_engine import ProbabilityEngine
from analyzer.inning_analyzer import InningAnalyzer
from analyzer.prop_analyzer import PropAnalyzer
from utils.formatters import ConsoleFormatter

console = Console()


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------

def _setup(home_query: str, away_query: str, days: int = 14):
    """Fetch data and wire up all components."""
    fetcher = ESPNDataFetcher()
    sc = StatsCalculator()
    pe = ProbabilityEngine(sc)
    ia = InningAnalyzer(sc, pe)
    pa = PropAnalyzer(pe, sc)
    fmt = ConsoleFormatter()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Resolving team IDs...", total=None)
        home_id = fetcher.find_team_id(home_query)
        away_id = fetcher.find_team_id(away_query)
        if not home_id or not away_id:
            console.print(
                f"[red]Could not resolve team IDs for '{home_query}' or '{away_query}'.[/red]\n"
                "Try using the full city name (e.g. 'new york yankees', 'los angeles dodgers')."
            )
            sys.exit(1)

        progress.update(task, description=f"Fetching last {days} days of games...")
        recent = fetcher.get_recent_games(days=days)

        progress.update(task, description="Ingesting game data (this may take a moment)...")
        sc.ingest_games(recent, fetcher)

    return fetcher, sc, pe, ia, pa, fmt, home_id, away_id


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """MLB Betting Analyzer — powered by ESPN data."""
    pass


# ---- Today's games -------------------------------------------------------

@cli.command()
@click.option("--date", default=None, help="Date in YYYYMMDD format (default: today)")
def games(date):
    """List today's (or a specified date's) MLB games."""
    fetcher = ESPNDataFetcher()
    fmt = ConsoleFormatter()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
        t = p.add_task("Fetching scoreboard...")
        game_list = fetcher.get_scoreboard(date)
    fmt.print_games_list(game_list)
    if not game_list:
        console.print("[yellow]No games found for the selected date.[/yellow]")


# ---- Full pre-game analysis ----------------------------------------------

@cli.command()
@click.option("--home", required=True, help="Home team name or abbreviation")
@click.option("--away", required=True, help="Away team name or abbreviation")
@click.option("--total", default=8.5, show_default=True, type=float, help="Game total line")
@click.option("--home-ml", default=None, type=int, help="Sportsbook home moneyline (e.g. -145)")
@click.option("--away-ml", default=None, type=int, help="Sportsbook away moneyline (e.g. +125)")
@click.option("--days", default=14, show_default=True, help="Days of history to load")
def analyze(home, away, total, home_ml, away_ml, days):
    """Full pre-game betting analysis card."""
    fetcher, sc, pe, ia, pa, fmt, home_id, away_id = _setup(home, away, days)

    home_name = home.title()
    away_name = away.title()

    card = pa.full_game_card(
        home_id, away_id,
        home_name=home_name,
        away_name=away_name,
        total_line=total,
        book_home_ml=home_ml,
        book_away_ml=away_ml,
    )
    fmt.print_game_card(card)

    # Also print inning preview
    inning_rows = ia.inning_by_inning_preview(home_id, away_id)
    fmt.print_inning_preview(inning_rows, home_name, away_name)

    # NRFI / YRFI
    nrfi = pa.nrfi_yrfi(home_id, away_id)
    fmt.print_nrfi(nrfi)

    # First score timing
    first_score = pa.first_score_inning(home_id, away_id)
    fmt.print_first_score(first_score)


# ---- Innings deep-dive ----------------------------------------------------

@cli.command()
@click.option("--home", required=True)
@click.option("--away", required=True)
@click.option("--days", default=14, show_default=True)
def innings(home, away, days):
    """Per-inning run-scoring probability breakdown."""
    fetcher, sc, pe, ia, pa, fmt, home_id, away_id = _setup(home, away, days)
    rows = ia.inning_by_inning_preview(home_id, away_id)
    fmt.print_inning_preview(rows, home.title(), away.title())

    first_score = pa.first_score_inning(home_id, away_id)
    fmt.print_first_score(first_score)


# ---- NRFI / YRFI ----------------------------------------------------------

@cli.command()
@click.option("--home", required=True)
@click.option("--away", required=True)
@click.option("--days", default=14, show_default=True)
def nrfi(home, away, days):
    """No Run First Inning (NRFI) / Yes Run First Inning (YRFI) probability."""
    fetcher, sc, pe, ia, pa, fmt, home_id, away_id = _setup(home, away, days)
    result = pa.nrfi_yrfi(home_id, away_id)
    fmt.print_nrfi(result)


# ---- Live win probability -------------------------------------------------

@cli.command()
@click.option("--home", required=True)
@click.option("--away", required=True)
@click.option("--home-runs", required=True, type=int)
@click.option("--away-runs", required=True, type=int)
@click.option("--inning", required=True, type=int)
@click.option("--half", required=True, type=click.Choice(["top", "bottom"]))
@click.option("--outs", default=0, show_default=True, type=int)
@click.option("--runners", default="", help="Comma-separated bases occupied, e.g. '1B,2B'")
@click.option("--days", default=14, show_default=True)
def live(home, away, home_runs, away_runs, inning, half, outs, runners, days):
    """Live in-game win probability given current game state."""
    fetcher, sc, pe, ia, pa, fmt, home_id, away_id = _setup(home, away, days)
    runner_list = [r.strip() for r in runners.split(",") if r.strip()] if runners else []
    result = ia.live_win_probability(
        home_runs=home_runs,
        away_runs=away_runs,
        current_inning=inning,
        half=half,
        home_id=home_id,
        away_id=away_id,
        outs=outs,
        runners=runner_list,
    )
    fmt.print_live_wp(result, home.title(), away.title())


# ---- Value prop scanner ---------------------------------------------------

@cli.command()
@click.option("--home", required=True)
@click.option("--away", required=True)
@click.option("--total", default=8.5, show_default=True, type=float)
@click.option("--home-ml", default=None, type=int)
@click.option("--away-ml", default=None, type=int)
@click.option("--home-team-total", default=None, type=float, help="Home team run total line")
@click.option("--away-team-total", default=None, type=float, help="Away team run total line")
@click.option("--over-odds", default=-110, show_default=True, type=int, help="Standard over juice")
@click.option("--under-odds", default=-110, show_default=True, type=int, help="Standard under juice")
@click.option("--days", default=14, show_default=True)
def value(home, away, total, home_ml, away_ml, home_team_total, away_team_total,
          over_odds, under_odds, days):
    """Scan multiple props and surface the best value vs. sportsbook lines."""
    fetcher, sc, pe, ia, pa, fmt, home_id, away_id = _setup(home, away, days)

    book_lines = {"total": (total, over_odds, under_odds)}
    if home_ml:
        book_lines["home_ml"] = home_ml
    if away_ml:
        book_lines["away_ml"] = away_ml
    if home_team_total:
        book_lines["home_total"] = (home_team_total, over_odds, under_odds)
    if away_team_total:
        book_lines["away_total"] = (away_team_total, over_odds, under_odds)

    props = pa.scan_value_props(
        home_id, away_id,
        home_name=home.title(),
        away_name=away.title(),
        book_lines=book_lines,
    )
    fmt.print_value_props(props)


# ---- Team total -----------------------------------------------------------

@cli.command("team-total")
@click.option("--team", required=True, help="Team to analyze")
@click.option("--opp", required=True, help="Opponent team")
@click.option("--line", required=True, type=float, help="Team total run line (e.g. 4.5)")
@click.option("--over-odds", default=-110, type=int)
@click.option("--under-odds", default=-110, type=int)
@click.option("--days", default=14, show_default=True)
def team_total(team, opp, line, over_odds, under_odds, days):
    """Analyze a specific team's run total prop."""
    fetcher = ESPNDataFetcher()
    sc = StatsCalculator()
    pe = ProbabilityEngine(sc)
    pa = PropAnalyzer(pe, sc)
    fmt = ConsoleFormatter()

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
        t = p.add_task("Resolving teams...")
        team_id = fetcher.find_team_id(team)
        opp_id = fetcher.find_team_id(opp)
        if not team_id or not opp_id:
            console.print("[red]Could not resolve one or both team names.[/red]")
            sys.exit(1)
        p.update(t, description="Fetching game history...")
        recent = fetcher.get_recent_games(days=days)
        p.update(t, description="Ingesting data...")
        sc.ingest_games(recent, fetcher)

    card = pa.team_total_card(team_id, opp_id, team.title(), line, over_odds, under_odds)

    from rich.table import Table
    from rich import box
    tbl = Table(title=f"{card['team']} Team Total", box=box.ROUNDED, border_style="cyan")
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value", justify="right")
    tbl.add_row("Line", str(card["line"]))
    tbl.add_row("Model Expected Runs", str(card["expected_runs"]))
    tbl.add_row("Over Probability", card["over_prob"])
    tbl.add_row("Under Probability", card["under_prob"])
    tbl.add_row("Fair Over ML", card["fair_over_ml"])
    tbl.add_row("Fair Under ML", card["fair_under_ml"])
    if card.get("over_value"):
        v = card["over_value"]
        tbl.add_row("Over Edge", f"{v['edge_pct']:+.1f}%")
        tbl.add_row("Over Rating", v["rating"])
    console.print(tbl)


# ---- Game summary (box score) --------------------------------------------

@cli.command("boxscore")
@click.argument("game_id")
def boxscore(game_id):
    """Show box score linescore for a completed or in-progress game."""
    fetcher = ESPNDataFetcher()
    fmt = ConsoleFormatter()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
        t = p.add_task("Fetching game summary...")
        summary = fetcher.get_game_summary(game_id)
        linescore = fetcher.parse_linescore(summary)

    from analyzer.inning_analyzer import InningAnalyzer
    from analyzer.stats_calculator import StatsCalculator
    from analyzer.probability_engine import ProbabilityEngine
    ia = InningAnalyzer(StatsCalculator(), ProbabilityEngine(StatsCalculator()))
    text = ia.format_linescore_table(linescore)
    fmt.print_linescore(text)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
