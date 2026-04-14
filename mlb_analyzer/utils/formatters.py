"""
Console Formatter
Rich-based pretty printing for analysis outputs.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.text import Text


console = Console()


class ConsoleFormatter:

    def __init__(self):
        self.console = Console()

    def _rating_color(self, rating: str) -> str:
        return {"STRONG": "green", "LEAN": "yellow", "PASS": "red"}.get(rating, "white")

    # ------------------------------------------------------------------
    # Game card
    # ------------------------------------------------------------------

    def print_game_card(self, card: dict) -> None:
        self.console.print()
        self.console.print(
            Panel(f"[bold cyan]{card['matchup']}[/bold cyan]", title="MLB Betting Analysis", border_style="cyan")
        )

        # --- Moneyline ---
        ml_table = Table(title="Moneyline", box=box.ROUNDED, border_style="blue")
        ml_table.add_column("Team", style="bold")
        ml_table.add_column("Win Prob", justify="right")
        ml_table.add_column("Fair ML", justify="right")
        ml_table.add_column("Book ML", justify="right")
        ml_table.add_column("Edge", justify="right")
        ml_table.add_column("Rating", justify="center")

        for side in ("home", "away"):
            m = card["moneyline"][side]
            v = m.get("value") or {}
            edge_str = f"{v.get('edge_pct', 0):+.1f}%" if v else "N/A"
            rating = v.get("rating", "N/A") if v else "N/A"
            book_odds = str(v.get("book_odds", "N/A")) if v else "N/A"
            color = self._rating_color(rating)
            ml_table.add_row(
                m["team"],
                m["win_prob"],
                m["fair_ml"],
                book_odds,
                edge_str,
                f"[{color}]{rating}[/{color}]",
            )
        self.console.print(ml_table)

        # --- Run Line ---
        rl = card["run_line_1_5"]
        rl_table = Table(title="Run Line (±1.5)", box=box.ROUNDED, border_style="blue")
        rl_table.add_column("Side", style="bold")
        rl_table.add_column("Cover Prob", justify="right")
        rl_table.add_column("Fair ML", justify="right")
        matchup_parts = card["matchup"].split(" @ ")
        away_name = matchup_parts[0] if len(matchup_parts) > 1 else "Away"
        home_name = matchup_parts[1] if len(matchup_parts) > 1 else "Home"
        rl_table.add_row(f"{home_name} -1.5", rl["home_covers"], rl["home_ml"])
        rl_table.add_row(f"{away_name} +1.5", rl["away_covers"], rl["away_ml"])
        self.console.print(rl_table)

        # --- Totals ---
        gt = card["game_total"]
        f5 = card["first_5_innings"]
        tot_table = Table(title="Totals", box=box.ROUNDED, border_style="blue")
        tot_table.add_column("Market", style="bold")
        tot_table.add_column("Line", justify="right")
        tot_table.add_column("Exp.", justify="right")
        tot_table.add_column("Over %", justify="right")
        tot_table.add_column("Under %", justify="right")
        tot_table.add_column("Fair O ML", justify="right")
        tot_table.add_column("Fair U ML", justify="right")

        gt_edge = gt.get("over_value", {})
        gt_color = self._rating_color(gt_edge.get("rating", "PASS")) if gt_edge else "white"
        tot_table.add_row(
            f"[{gt_color}]Full Game[/{gt_color}]",
            str(gt["line"]),
            str(gt["expected_total"]),
            gt["over_prob"],
            gt["under_prob"],
            gt["fair_over_ml"],
            gt["fair_under_ml"],
        )
        tot_table.add_row(
            "First 5",
            str(f5["line"]),
            "—",
            f5["over_prob"],
            f5["under_prob"],
            f5["fair_over_ml"],
            f5["fair_under_ml"],
        )
        self.console.print(tot_table)

    # ------------------------------------------------------------------
    # Inning-by-inning preview
    # ------------------------------------------------------------------

    def print_inning_preview(self, rows: list[dict], home_name: str, away_name: str) -> None:
        self.console.print()
        t = Table(title="Inning-by-Inning Preview", box=box.ROUNDED, border_style="magenta")
        t.add_column("Inn", justify="center")
        t.add_column(f"{home_name[:10]} Exp R", justify="right")
        t.add_column(f"{away_name[:10]} Exp R", justify="right")
        t.add_column(f"{home_name[:10]} Score%", justify="right")
        t.add_column(f"{away_name[:10]} Score%", justify="right")
        t.add_column("Big Inn (3+R)%", justify="right")
        for r in rows:
            big_color = "green" if r["p_big_inning_3plus"] > 0.25 else "white"
            t.add_row(
                str(r["inning"]),
                f"{r['home_exp_runs']:.3f}",
                f"{r['away_exp_runs']:.3f}",
                f"{r['home_scoring_pct']*100:.1f}%",
                f"{r['away_scoring_pct']*100:.1f}%",
                f"[{big_color}]{r['p_big_inning_3plus']*100:.1f}%[/{big_color}]",
            )
        self.console.print(t)

    # ------------------------------------------------------------------
    # NRFI / YRFI
    # ------------------------------------------------------------------

    def print_nrfi(self, result: dict) -> None:
        self.console.print()
        t = Table(title="NRFI / YRFI", box=box.ROUNDED, border_style="yellow")
        t.add_column("Prop", style="bold")
        t.add_column("Probability", justify="right")
        t.add_column("Fair ML", justify="right")
        t.add_row("NRFI (No Run 1st Inn)", f"{result['p_nrfi']*100:.1f}%", result["ml_nrfi"])
        t.add_row("YRFI (Yes Run 1st Inn)", f"{result['p_yrfi']*100:.1f}%", result["ml_yrfi"])
        self.console.print(t)

    # ------------------------------------------------------------------
    # First score inning
    # ------------------------------------------------------------------

    def print_first_score(self, rows: list[dict]) -> None:
        self.console.print()
        t = Table(title="When Will First Run Score?", box=box.ROUNDED, border_style="yellow")
        t.add_column("Inning", justify="center")
        t.add_column("P(1st Run Here)", justify="right")
        t.add_column("Cumulative %", justify="right")
        for r in rows:
            color = "green" if r["p_first_run_here"] == max(x["p_first_run_here"] for x in rows) else "white"
            t.add_row(
                str(r["inning"]),
                f"[{color}]{r['p_first_run_here']*100:.1f}%[/{color}]",
                f"{r['cumulative_p_scored']*100:.1f}%",
            )
        self.console.print(t)

    # ------------------------------------------------------------------
    # Live win probability
    # ------------------------------------------------------------------

    def print_live_wp(self, result: dict, home_name: str, away_name: str) -> None:
        self.console.print()
        self.console.print(
            Panel(
                f"Inning [bold]{result['inning']}[/bold] ({result['half'].upper()}) | "
                f"Score: [bold]{result['score']}[/bold] | "
                f"Outs: {result['outs']} | "
                f"Runners: {result['runners'] or 'none'}",
                title="Live Game State",
                border_style="green",
            )
        )
        t = Table(title="Live Win Probability", box=box.ROUNDED, border_style="green")
        t.add_column("Team", style="bold")
        t.add_column("Win Prob", justify="right")
        t.add_column("Live ML", justify="right")
        t.add_column("Exp Runs Left", justify="right")

        t.add_row(
            home_name,
            f"[{'green' if result['p_home_win'] > result['p_away_win'] else 'red'}]{result['p_home_win']*100:.1f}%[/{'green' if result['p_home_win'] > result['p_away_win'] else 'red'}]",
            result["ml_home"],
            str(result["lam_home_remaining"]),
        )
        t.add_row(
            away_name,
            f"[{'green' if result['p_away_win'] > result['p_home_win'] else 'red'}]{result['p_away_win']*100:.1f}%[/{'green' if result['p_away_win'] > result['p_home_win'] else 'red'}]",
            result["ml_away"],
            str(result["lam_away_remaining"]),
        )
        self.console.print(t)

    # ------------------------------------------------------------------
    # Value prop scanner
    # ------------------------------------------------------------------

    def print_value_props(self, props: list[dict]) -> None:
        self.console.print()
        t = Table(title="Value Prop Scan", box=box.ROUNDED, border_style="cyan")
        t.add_column("Prop", style="bold")
        t.add_column("Our Prob", justify="right")
        t.add_column("Book ML", justify="right")
        t.add_column("Implied%", justify="right")
        t.add_column("Edge", justify="right")
        t.add_column("EV", justify="right")
        t.add_column("Rating", justify="center")
        for p in props:
            color = self._rating_color(p.get("rating", "PASS"))
            t.add_row(
                p["prop"],
                f"{p['our_probability']*100:.1f}%",
                str(p["book_odds"]),
                f"{p['implied_probability']*100:.1f}%",
                f"[{color}]{p['edge_pct']:+.1f}%[/{color}]",
                f"{p['expected_value']:+.3f}",
                f"[{color}]{p['rating']}[/{color}]",
            )
        if not props:
            self.console.print("[yellow]No value props found with current lines.[/yellow]")
        else:
            self.console.print(t)

    # ------------------------------------------------------------------
    # Box score linescore
    # ------------------------------------------------------------------

    def print_linescore(self, linescore_text: str) -> None:
        self.console.print()
        self.console.print(Panel(linescore_text, title="Linescore", border_style="white"))

    # ------------------------------------------------------------------
    # Today's games list
    # ------------------------------------------------------------------

    def print_games_list(self, games: list[dict]) -> None:
        self.console.print()
        t = Table(title="Today's MLB Games", box=box.ROUNDED, border_style="cyan")
        t.add_column("#", justify="right", style="dim")
        t.add_column("Game ID")
        t.add_column("Away")
        t.add_column("Home")
        t.add_column("Status")
        t.add_column("Score")

        for i, g in enumerate(games, 1):
            comps = g.get("competitions", [{}])
            comp = comps[0] if comps else {}
            competitors = comp.get("competitors", [])
            status = g.get("status", {}).get("type", {}).get("description", "—")
            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            home_name = home.get("team", {}).get("abbreviation", "?")
            away_name = away.get("team", {}).get("abbreviation", "?")
            home_score = home.get("score", "—")
            away_score = away.get("score", "—")
            t.add_row(
                str(i),
                g.get("id", "?"),
                away_name,
                home_name,
                status,
                f"{away_score} - {home_score}",
            )
        self.console.print(t)
