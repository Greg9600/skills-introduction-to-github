"""
Probability Engine
Uses historical run distributions and Poisson/normal modeling to estimate
the probability of various betting outcomes.
"""

import math
from typing import Optional


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) for Poisson(lam)."""
    return sum(_poisson_pmf(i, lam) for i in range(k + 1))


def _american_to_prob(american: int) -> float:
    """Convert American moneyline odds to implied probability."""
    if american > 0:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def _prob_to_american(prob: float) -> str:
    """Convert probability to American moneyline string."""
    prob = max(0.001, min(0.999, prob))
    if prob >= 0.5:
        return f"-{round((prob / (1 - prob)) * 100)}"
    return f"+{round(((1 - prob) / prob) * 100)}"


class ProbabilityEngine:
    """
    Computes betting probabilities for MLB games given team run statistics.
    """

    def __init__(self, stats_calculator):
        self.sc = stats_calculator

    # ------------------------------------------------------------------
    # Core: expected runs for a matchup
    # ------------------------------------------------------------------

    def _expected_runs(self, team_id: str, opp_id: Optional[str] = None) -> float:
        """
        Blend a team's average runs scored with the opponent's average runs allowed
        to produce a single expected-run lambda for that half of the game.
        Falls back to league average (4.5) if data is sparse.
        """
        LEAGUE_AVG = 4.5
        own_stats = self.sc.team_run_stats(team_id)
        opp_stats = self.sc.team_run_stats(opp_id) if opp_id else {}

        own_scored = own_stats.get("avg_runs_scored", LEAGUE_AVG)
        opp_allowed = opp_stats.get("avg_runs_allowed", LEAGUE_AVG)

        if opp_stats:
            # Blend: team's offense vs. opponent's defense, anchored to league avg
            return round((own_scored + opp_allowed) / 2, 3)
        return own_scored

    # ------------------------------------------------------------------
    # Over / Under
    # ------------------------------------------------------------------

    def over_under(
        self,
        home_id: str,
        away_id: str,
        line: float,
    ) -> dict:
        """
        Probability of combined runs going over / under the given line.
        Models each team's runs as Poisson(lambda), then convolves.
        Returns edge vs. a fair-market implied probability.
        """
        lam_home = self._expected_runs(home_id, away_id)
        lam_away = self._expected_runs(away_id, home_id)
        lam_total = lam_home + lam_away

        max_runs = int(lam_total * 3) + 20
        p_over = sum(
            _poisson_pmf(k, lam_total) for k in range(int(line) + 1, max_runs + 1)
        )
        # handle half-run lines
        if line % 1 == 0.5:
            p_over = sum(
                _poisson_pmf(k, lam_total)
                for k in range(math.ceil(line), max_runs + 1)
            )

        p_under = 1.0 - p_over
        p_push = _poisson_pmf(int(line), lam_total) if line % 1 == 0 else 0.0

        return {
            "line": line,
            "lam_home": lam_home,
            "lam_away": lam_away,
            "lam_total": round(lam_total, 2),
            "p_over": round(p_over, 4),
            "p_under": round(p_under, 4),
            "p_push": round(p_push, 4),
            "ml_over": _prob_to_american(p_over),
            "ml_under": _prob_to_american(p_under),
            "over_edge_vs_even": round((p_over - 0.5) * 100, 1),
        }

    # ------------------------------------------------------------------
    # Moneyline (team win probability)
    # ------------------------------------------------------------------

    def moneyline(self, home_id: str, away_id: str) -> dict:
        """
        Estimate win probability for each team using a Poisson matchup model.
        Iterates over all (home_runs, away_runs) combinations up to a max.
        """
        lam_home = self._expected_runs(home_id, away_id)
        lam_away = self._expected_runs(away_id, home_id)

        max_r = int(max(lam_home, lam_away) * 3) + 15
        p_home_win = 0.0
        p_away_win = 0.0
        p_tie = 0.0

        for h in range(max_r + 1):
            ph = _poisson_pmf(h, lam_home)
            for a in range(max_r + 1):
                pa = _poisson_pmf(a, lam_away)
                joint = ph * pa
                if h > a:
                    p_home_win += joint
                elif a > h:
                    p_away_win += joint
                else:
                    p_tie += joint

        # In baseball there are no ties — re-distribute tie prob proportionally
        if p_tie > 0:
            total_no_tie = p_home_win + p_away_win
            if total_no_tie > 0:
                p_home_win += p_tie * (p_home_win / total_no_tie)
                p_away_win += p_tie * (p_away_win / total_no_tie)

        return {
            "p_home_win": round(p_home_win, 4),
            "p_away_win": round(p_away_win, 4),
            "ml_home": _prob_to_american(p_home_win),
            "ml_away": _prob_to_american(p_away_win),
            "lam_home": lam_home,
            "lam_away": lam_away,
        }

    # ------------------------------------------------------------------
    # Run-line (spread)
    # ------------------------------------------------------------------

    def run_line(self, home_id: str, away_id: str, spread: float = 1.5) -> dict:
        """
        Probability that the favored team covers a run-line spread.
        spread: positive = home team giving runs (home favored)
                negative = home team getting runs (away favored)
        """
        lam_home = self._expected_runs(home_id, away_id)
        lam_away = self._expected_runs(away_id, home_id)

        max_r = int(max(lam_home, lam_away) * 3) + 15
        p_home_covers = 0.0  # home wins by > |spread|
        p_away_covers = 0.0  # away wins by > |spread| or home loses by any

        for h in range(max_r + 1):
            ph = _poisson_pmf(h, lam_home)
            for a in range(max_r + 1):
                pa = _poisson_pmf(a, lam_away)
                joint = ph * pa
                diff = h - a  # positive = home winning
                if diff > spread:
                    p_home_covers += joint
                elif diff < -spread:
                    p_away_covers += joint

        return {
            "spread": spread,
            "p_home_covers": round(p_home_covers, 4),
            "p_away_covers": round(p_away_covers, 4),
            "ml_home_covers": _prob_to_american(p_home_covers),
            "ml_away_covers": _prob_to_american(p_away_covers),
        }

    # ------------------------------------------------------------------
    # First-5-innings (F5) total
    # ------------------------------------------------------------------

    def first_five_innings(self, home_id: str, away_id: str, line: float) -> dict:
        """
        Estimate F5 over/under. Uses ~55% of full-game expected runs (pitchers
        dominate early; league average ~55% of runs in first 5).
        """
        FIRST_FIVE_FACTOR = 0.55
        lam_home_f5 = self._expected_runs(home_id, away_id) * FIRST_FIVE_FACTOR
        lam_away_f5 = self._expected_runs(away_id, home_id) * FIRST_FIVE_FACTOR
        lam_total = lam_home_f5 + lam_away_f5

        max_runs = int(lam_total * 3) + 15
        if line % 1 == 0.5:
            p_over = sum(_poisson_pmf(k, lam_total) for k in range(math.ceil(line), max_runs + 1))
        else:
            p_over = sum(_poisson_pmf(k, lam_total) for k in range(int(line) + 1, max_runs + 1))

        p_under = 1.0 - p_over

        return {
            "line_f5": line,
            "lam_f5_total": round(lam_total, 2),
            "p_over_f5": round(p_over, 4),
            "p_under_f5": round(p_under, 4),
            "ml_over_f5": _prob_to_american(p_over),
            "ml_under_f5": _prob_to_american(p_under),
        }

    # ------------------------------------------------------------------
    # Team total (single-team over/under)
    # ------------------------------------------------------------------

    def team_total(self, team_id: str, opp_id: str, line: float) -> dict:
        """Probability a specific team scores over/under their team total."""
        lam = self._expected_runs(team_id, opp_id)
        max_r = int(lam * 3) + 15

        if line % 1 == 0.5:
            p_over = sum(_poisson_pmf(k, lam) for k in range(math.ceil(line), max_r + 1))
        else:
            p_over = sum(_poisson_pmf(k, lam) for k in range(int(line) + 1, max_r + 1))

        p_under = 1.0 - p_over

        return {
            "line": line,
            "lam_team": round(lam, 2),
            "p_over": round(p_over, 4),
            "p_under": round(p_under, 4),
            "ml_over": _prob_to_american(p_over),
            "ml_under": _prob_to_american(p_under),
        }

    # ------------------------------------------------------------------
    # Value finder: compare our probability to sportsbook odds
    # ------------------------------------------------------------------

    def find_value(self, our_prob: float, book_odds: int) -> dict:
        """
        Compare our model probability vs. a sportsbook's implied probability.
        Returns edge percentage and whether it's a value bet.
        """
        implied = _american_to_prob(book_odds)
        edge = our_prob - implied
        ev = (our_prob * (1 / implied - 1)) - (1 - our_prob)  # per-unit EV at book price
        return {
            "our_probability": round(our_prob, 4),
            "book_odds": book_odds,
            "implied_probability": round(implied, 4),
            "edge_pct": round(edge * 100, 2),
            "expected_value": round(ev, 4),
            "is_value": edge > 0.02,  # at least 2% edge threshold
            "rating": "STRONG" if edge > 0.06 else ("LEAN" if edge > 0.02 else "PASS"),
        }
