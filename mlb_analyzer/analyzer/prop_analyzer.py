"""
Prop Analyzer
Evaluates common MLB betting props:
  - Moneyline, run-line, game total (O/U)
  - First 5 innings
  - Team total
  - NRFI / YRFI (No / Yes Run First Inning)
  - Innings with score (when will teams score)
  - Value detection vs. sportsbook lines
"""

from typing import Optional
from .probability_engine import _poisson_pmf, _poisson_cdf, _prob_to_american, _american_to_prob


class PropAnalyzer:
    """
    High-level prop analysis combining the probability engine with
    easy-to-read summaries and value ratings.
    """

    def __init__(self, probability_engine, stats_calculator):
        self.pe = probability_engine
        self.sc = stats_calculator

    # ------------------------------------------------------------------
    # Full game card
    # ------------------------------------------------------------------

    def full_game_card(
        self,
        home_id: str,
        away_id: str,
        home_name: str = "Home",
        away_name: str = "Away",
        total_line: float = 8.5,
        book_home_ml: Optional[int] = None,
        book_away_ml: Optional[int] = None,
        book_total: Optional[float] = None,
    ) -> dict:
        """
        Returns a complete pre-game betting analysis card.
        """
        ml = self.pe.moneyline(home_id, away_id)
        ou = self.pe.over_under(home_id, away_id, total_line)
        rl = self.pe.run_line(home_id, away_id, 1.5)
        f5 = self.pe.first_five_innings(home_id, away_id, (total_line * 0.55))

        # Sportsbook value analysis
        home_value = (
            self.pe.find_value(ml["p_home_win"], book_home_ml)
            if book_home_ml
            else None
        )
        away_value = (
            self.pe.find_value(ml["p_away_win"], book_away_ml)
            if book_away_ml
            else None
        )
        over_value = (
            self.pe.find_value(ou["p_over"], -110)  # standard juice
            if not book_total
            else self.pe.find_value(ou["p_over"], -110)
        )

        return {
            "matchup": f"{away_name} @ {home_name}",
            "moneyline": {
                "home": {
                    "team": home_name,
                    "win_prob": f"{ml['p_home_win']*100:.1f}%",
                    "fair_ml": ml["ml_home"],
                    "value": home_value,
                },
                "away": {
                    "team": away_name,
                    "win_prob": f"{ml['p_away_win']*100:.1f}%",
                    "fair_ml": ml["ml_away"],
                    "value": away_value,
                },
            },
            "run_line_1_5": {
                "home_covers": f"{rl['p_home_covers']*100:.1f}%",
                "away_covers": f"{rl['p_away_covers']*100:.1f}%",
                "home_ml": rl["ml_home_covers"],
                "away_ml": rl["ml_away_covers"],
            },
            "game_total": {
                "line": total_line,
                "expected_total": ou["lam_total"],
                "over_prob": f"{ou['p_over']*100:.1f}%",
                "under_prob": f"{ou['p_under']*100:.1f}%",
                "fair_over_ml": ou["ml_over"],
                "fair_under_ml": ou["ml_under"],
                "over_value": over_value,
            },
            "first_5_innings": {
                "line": round(total_line * 0.55, 1),
                "over_prob": f"{f5['p_over_f5']*100:.1f}%",
                "under_prob": f"{f5['p_under_f5']*100:.1f}%",
                "fair_over_ml": f5["ml_over_f5"],
                "fair_under_ml": f5["ml_under_f5"],
            },
            "model_expected_runs": {
                "home": ml["lam_home"],
                "away": ml["lam_away"],
                "total": ou["lam_total"],
            },
        }

    # ------------------------------------------------------------------
    # NRFI / YRFI
    # ------------------------------------------------------------------

    def nrfi_yrfi(self, home_id: str, away_id: str) -> dict:
        """
        No Run First Inning (NRFI) / Yes Run First Inning (YRFI).
        Uses 1st-inning historical scoring rates when available,
        otherwise falls back to weighted Poisson estimate.
        """
        FIRST_INN_WEIGHT = 0.128  # ~12.8% of runs score in inning 1

        home_stats = self.sc.inning_run_distribution(home_id)
        away_stats = self.sc.inning_run_distribution(away_id)

        lam_home_full = self.pe._expected_runs(home_id, away_id)
        lam_away_full = self.pe._expected_runs(away_id, home_id)

        lam_home_1st = home_stats.get(1, {}).get("avg_runs", lam_home_full * FIRST_INN_WEIGHT)
        lam_away_1st = away_stats.get(1, {}).get("avg_runs", lam_away_full * FIRST_INN_WEIGHT)

        # P(NRFI) = P(home scores 0 in 1st) * P(away scores 0 in 1st)
        p_home_0 = _poisson_pmf(0, lam_home_1st)
        p_away_0 = _poisson_pmf(0, lam_away_1st)
        p_nrfi = p_home_0 * p_away_0
        p_yrfi = 1 - p_nrfi

        return {
            "p_nrfi": round(p_nrfi, 4),
            "p_yrfi": round(p_yrfi, 4),
            "ml_nrfi": _prob_to_american(p_nrfi),
            "ml_yrfi": _prob_to_american(p_yrfi),
            "home_1st_inn_lam": round(lam_home_1st, 3),
            "away_1st_inn_lam": round(lam_away_1st, 3),
        }

    # ------------------------------------------------------------------
    # When will teams score? (inning-by-inning first-score probability)
    # ------------------------------------------------------------------

    def first_score_inning(self, home_id: str, away_id: str) -> list[dict]:
        """
        For each inning, estimate the probability that the FIRST run of the
        game (either team) is scored in that inning.
        """
        FIRST_INN_WEIGHT = 0.128

        home_stats = self.sc.inning_run_distribution(home_id)
        away_stats = self.sc.inning_run_distribution(away_id)

        lam_home_full = self.pe._expected_runs(home_id, away_id)
        lam_away_full = self.pe._expected_runs(away_id, home_id)

        from .inning_analyzer import INNING_RUN_WEIGHTS

        rows = []
        p_no_score_yet = 1.0
        for inning in range(1, 10):
            weight = INNING_RUN_WEIGHTS.get(inning, 0.111)
            lam_h = home_stats.get(inning, {}).get("avg_runs", lam_home_full * weight)
            lam_a = away_stats.get(inning, {}).get("avg_runs", lam_away_full * weight)

            p_no_run_this_inn = _poisson_pmf(0, lam_h) * _poisson_pmf(0, lam_a)
            p_first_score_here = p_no_score_yet * (1 - p_no_run_this_inn)
            p_no_score_yet *= p_no_run_this_inn

            rows.append({
                "inning": inning,
                "p_first_run_here": round(p_first_score_here, 4),
                "cumulative_p_scored": round(1 - p_no_score_yet, 4),
            })
        return rows

    # ------------------------------------------------------------------
    # Team total
    # ------------------------------------------------------------------

    def team_total_card(
        self,
        team_id: str,
        opp_id: str,
        team_name: str,
        line: float,
        book_over_odds: int = -110,
        book_under_odds: int = -110,
    ) -> dict:
        result = self.pe.team_total(team_id, opp_id, line)
        over_value = self.pe.find_value(result["p_over"], book_over_odds)
        under_value = self.pe.find_value(result["p_under"], book_under_odds)

        return {
            "team": team_name,
            "line": line,
            "expected_runs": result["lam_team"],
            "over_prob": f"{result['p_over']*100:.1f}%",
            "under_prob": f"{result['p_under']*100:.1f}%",
            "fair_over_ml": result["ml_over"],
            "fair_under_ml": result["ml_under"],
            "over_value": over_value,
            "under_value": under_value,
        }

    # ------------------------------------------------------------------
    # Prop scanner: find best value props across all given lines
    # ------------------------------------------------------------------

    def scan_value_props(
        self,
        home_id: str,
        away_id: str,
        home_name: str,
        away_name: str,
        book_lines: dict,
    ) -> list[dict]:
        """
        Scan multiple props against sportsbook lines and return ranked value bets.

        book_lines expected keys (all optional):
            home_ml, away_ml, total, home_total, away_total, runline_home, runline_away
        """
        value_bets = []

        # --- Moneyline ---
        ml = self.pe.moneyline(home_id, away_id)
        if "home_ml" in book_lines:
            v = self.pe.find_value(ml["p_home_win"], book_lines["home_ml"])
            v["prop"] = f"{home_name} ML"
            v["direction"] = "win"
            value_bets.append(v)
        if "away_ml" in book_lines:
            v = self.pe.find_value(ml["p_away_win"], book_lines["away_ml"])
            v["prop"] = f"{away_name} ML"
            v["direction"] = "win"
            value_bets.append(v)

        # --- Game Total ---
        if "total" in book_lines:
            line_val, over_odds, under_odds = book_lines["total"]
            ou = self.pe.over_under(home_id, away_id, line_val)
            v_over = self.pe.find_value(ou["p_over"], over_odds)
            v_over["prop"] = f"Total OVER {line_val}"
            v_over["direction"] = "over"
            value_bets.append(v_over)
            v_under = self.pe.find_value(ou["p_under"], under_odds)
            v_under["prop"] = f"Total UNDER {line_val}"
            v_under["direction"] = "under"
            value_bets.append(v_under)

        # --- Team Totals ---
        if "home_total" in book_lines:
            ht_line, ht_over_odds, ht_under_odds = book_lines["home_total"]
            tt = self.pe.team_total(home_id, away_id, ht_line)
            v = self.pe.find_value(tt["p_over"], ht_over_odds)
            v["prop"] = f"{home_name} Team Total OVER {ht_line}"
            value_bets.append(v)
            v2 = self.pe.find_value(tt["p_under"], ht_under_odds)
            v2["prop"] = f"{home_name} Team Total UNDER {ht_line}"
            value_bets.append(v2)

        if "away_total" in book_lines:
            at_line, at_over_odds, at_under_odds = book_lines["away_total"]
            tt = self.pe.team_total(away_id, home_id, at_line)
            v = self.pe.find_value(tt["p_over"], at_over_odds)
            v["prop"] = f"{away_name} Team Total OVER {at_line}"
            value_bets.append(v)

        # Sort by edge descending, filter to value bets only
        value_bets.sort(key=lambda x: x.get("edge_pct", 0), reverse=True)
        return value_bets
