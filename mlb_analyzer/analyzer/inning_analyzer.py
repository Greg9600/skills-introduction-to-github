"""
Inning Analyzer
Deep per-inning breakdown: scoring probabilities, run distributions,
comeback potential, and live in-game state analysis.
"""

import math
from typing import Optional
from .probability_engine import _poisson_pmf, _poisson_cdf, _prob_to_american


# League-wide average fraction of runs scored per inning (innings 1-9)
# Based on historical MLB data (slightly higher in early innings due to lineup order)
INNING_RUN_WEIGHTS = {
    1: 0.128,
    2: 0.108,
    3: 0.113,
    4: 0.110,
    5: 0.107,
    6: 0.109,
    7: 0.107,
    8: 0.107,
    9: 0.111,
}


class InningAnalyzer:
    """
    Per-inning scoring analysis and live in-game probability updates.
    """

    def __init__(self, stats_calculator, probability_engine):
        self.sc = stats_calculator
        self.pe = probability_engine

    # ------------------------------------------------------------------
    # Pre-game inning breakdown
    # ------------------------------------------------------------------

    def inning_by_inning_preview(self, home_id: str, away_id: str) -> list[dict]:
        """
        For each inning 1-9, estimate:
          - P(home scores), P(away scores)
          - Expected runs home, expected runs away
          - P(inning is high-scoring: >=3 runs combined)
        """
        lam_home_full = self.pe._expected_runs(home_id, away_id)
        lam_away_full = self.pe._expected_runs(away_id, home_id)

        # Pull historical inning distributions if available
        home_inning_dist = self.sc.inning_run_distribution(home_id)
        away_inning_dist = self.sc.inning_run_distribution(away_id)

        rows = []
        for inning in range(1, 10):
            weight = INNING_RUN_WEIGHTS.get(inning, 0.111)

            # Use historical inning data when available, else fall back to weighted full-game
            home_avg = home_inning_dist.get(inning, {}).get("avg_runs", lam_home_full * weight)
            away_avg = away_inning_dist.get(inning, {}).get("avg_runs", lam_away_full * weight)
            home_score_pct = home_inning_dist.get(inning, {}).get(
                "scoring_pct", 1 - _poisson_pmf(0, home_avg)
            )
            away_score_pct = away_inning_dist.get(inning, {}).get(
                "scoring_pct", 1 - _poisson_pmf(0, away_avg)
            )

            lam_combined = home_avg + away_avg
            p_big_inning = sum(_poisson_pmf(k, lam_combined) for k in range(3, 20))

            rows.append({
                "inning": inning,
                "home_exp_runs": round(home_avg, 3),
                "away_exp_runs": round(away_avg, 3),
                "home_scoring_pct": round(home_score_pct, 3),
                "away_scoring_pct": round(away_score_pct, 3),
                "p_big_inning_3plus": round(p_big_inning, 3),
            })
        return rows

    # ------------------------------------------------------------------
    # Live in-game state
    # ------------------------------------------------------------------

    def live_win_probability(
        self,
        home_runs: int,
        away_runs: int,
        current_inning: int,
        half: str,           # "top" or "bottom"
        home_id: str,
        away_id: str,
        outs: int = 0,
        runners: Optional[list[str]] = None,  # ["1B"], ["1B","2B"], etc.
    ) -> dict:
        """
        Estimate real-time win probability given the current game state.

        Uses the remaining expected runs model: for each team, multiply their
        per-game lambda by the fraction of game remaining.
        """
        innings_played_home = current_inning - 1 + (1 if half == "bottom" else 0)
        innings_played_away = current_inning - 1 + (1 if half in ("bottom", "end") else 0)

        # Fraction of game remaining (rough: 9 innings each side)
        frac_remaining_home = max(0, (9 - innings_played_home) / 9)
        frac_remaining_away = max(0, (9 - innings_played_away) / 9)

        # Adjust for outs within current inning
        out_adjustment = (3 - outs) / 3
        if half == "top":
            frac_remaining_away = max(0, frac_remaining_away - (1 / 9) * (1 - out_adjustment))
        else:
            frac_remaining_home = max(0, frac_remaining_home - (1 / 9) * (1 - out_adjustment))

        lam_home_full = self.pe._expected_runs(home_id, away_id)
        lam_away_full = self.pe._expected_runs(away_id, home_id)

        lam_home_rem = lam_home_full * frac_remaining_home
        lam_away_rem = lam_away_full * frac_remaining_away

        deficit = home_runs - away_runs  # positive = home leading

        # Compute P(home wins) by iterating over remaining run combinations
        max_r = int(max(lam_home_rem, lam_away_rem) * 3) + 15
        p_home_win = 0.0
        p_away_win = 0.0
        p_tie = 0.0

        for h in range(max_r + 1):
            ph = _poisson_pmf(h, lam_home_rem)
            for a in range(max_r + 1):
                pa = _poisson_pmf(a, lam_away_rem)
                joint = ph * pa
                final_diff = deficit + h - a
                if final_diff > 0:
                    p_home_win += joint
                elif final_diff < 0:
                    p_away_win += joint
                else:
                    p_tie += joint

        # Redistribute ties
        total_no_tie = p_home_win + p_away_win
        if p_tie > 0 and total_no_tie > 0:
            p_home_win += p_tie * (p_home_win / total_no_tie)
            p_away_win += p_tie * (p_away_win / total_no_tie)

        # Runner adjustment: runners on base increase scoring probability
        runner_boost = 0.0
        if runners:
            runner_boost = len(runners) * 0.01  # small boost per runner on base
            if half == "top":
                p_away_win = min(0.99, p_away_win + runner_boost)
                p_home_win = max(0.01, 1 - p_away_win)
            else:
                p_home_win = min(0.99, p_home_win + runner_boost)
                p_away_win = max(0.01, 1 - p_home_win)

        return {
            "inning": current_inning,
            "half": half,
            "score": f"Away {away_runs} - Home {home_runs}",
            "outs": outs,
            "runners": runners or [],
            "p_home_win": round(p_home_win, 4),
            "p_away_win": round(p_away_win, 4),
            "ml_home": _prob_to_american(p_home_win),
            "ml_away": _prob_to_american(p_away_win),
            "lam_home_remaining": round(lam_home_rem, 2),
            "lam_away_remaining": round(lam_away_rem, 2),
        }

    # ------------------------------------------------------------------
    # Comeback / blowout probability
    # ------------------------------------------------------------------

    def comeback_probability(
        self,
        trailing_team_lam_remaining: float,
        leading_team_lam_remaining: float,
        deficit: int,
    ) -> dict:
        """
        Probability that the trailing team overcomes a given run deficit.
        """
        max_r = int(max(trailing_team_lam_remaining, leading_team_lam_remaining) * 3) + 20
        p_comeback = 0.0

        for t in range(max_r + 1):
            pt = _poisson_pmf(t, trailing_team_lam_remaining)
            for l in range(max_r + 1):
                pl = _poisson_pmf(l, leading_team_lam_remaining)
                if t - l >= deficit:
                    p_comeback += pt * pl

        return {
            "deficit": deficit,
            "p_comeback": round(p_comeback, 4),
            "ml_comeback": _prob_to_american(p_comeback),
        }

    # ------------------------------------------------------------------
    # Score-by-inning summary (for a completed or live game)
    # ------------------------------------------------------------------

    def format_linescore_table(self, linescore: dict) -> str:
        """Return a text table of the inning-by-inning score."""
        home = linescore.get("home", {})
        away = linescore.get("away", {})
        home_inn = home.get("innings", [])
        away_inn = away.get("innings", [])
        n = max(len(home_inn), len(away_inn), 9)

        header = "     " + "".join(f" {i+1:2}" for i in range(n)) + " | R   H  E"
        away_row = (
            f"{away.get('name','Away'):5s}"
            + "".join(f" {v:2}" if i < len(away_inn) else "  -" for i, v in enumerate(away_inn[:n]))
            + f" | {away.get('R',0):2}  {away.get('H',0):2}  {away.get('E',0):2}"
        )
        home_row = (
            f"{home.get('name','Home'):5s}"
            + "".join(f" {v:2}" if i < len(home_inn) else "  -" for i, v in enumerate(home_inn[:n]))
            + f" | {home.get('R',0):2}  {home.get('H',0):2}  {home.get('E',0):2}"
        )
        return "\n".join([header, "-" * len(header), away_row, home_row])
