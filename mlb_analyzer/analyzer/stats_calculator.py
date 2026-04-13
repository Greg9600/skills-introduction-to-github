"""
Stats Calculator
Aggregates historical game data into team-level and matchup-level statistics.
"""

from collections import defaultdict
from typing import Optional


class StatsCalculator:
    """
    Processes a list of completed game summaries and produces aggregate
    offensive/defensive/pitching statistics used by the probability engine.
    """

    def __init__(self):
        # team_id -> list of game dicts
        self._games: dict[str, list[dict]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_games(self, games: list[dict], fetcher) -> None:
        """
        Given a list of ESPN event objects (from the scoreboard), fetch each
        full summary and store parsed stats per team.
        """
        import time
        for event in games:
            game_id = event.get("id")
            if not game_id:
                continue
            try:
                summary = fetcher.get_game_summary(game_id)
                linescore = fetcher.parse_linescore(summary)
                self._store(game_id, summary, linescore)
                time.sleep(0.15)
            except RuntimeError:
                continue

    def _store(self, game_id: str, summary: dict, linescore: dict) -> None:
        header = summary.get("header", {})
        comps = header.get("competitions", [{}])
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors", [])

        for c in competitors:
            side = c.get("homeAway", "home")
            opp_side = "away" if side == "home" else "home"
            team_id = c.get("team", {}).get("id", "")
            if not team_id:
                continue

            own = linescore.get(side, {})
            opp = linescore.get(opp_side, {})

            record = {
                "game_id": game_id,
                "side": side,
                "team_name": c.get("team", {}).get("displayName", ""),
                "opp_team": opp.get("name", ""),
                "runs_scored": own.get("R", 0),
                "runs_allowed": opp.get("R", 0),
                "hits": own.get("H", 0),
                "errors": own.get("E", 0),
                "innings": own.get("innings", []),
                "won": own.get("R", 0) > opp.get("R", 0),
            }
            self._games[team_id].append(record)

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def team_run_stats(self, team_id: str) -> dict:
        """
        Returns:
            avg_runs_scored, avg_runs_allowed, std_runs_scored,
            win_pct, games_played, over_5_5_pct, over_7_5_pct, over_9_5_pct
        """
        records = self._games.get(team_id, [])
        if not records:
            return {}

        scored = [r["runs_scored"] for r in records]
        allowed = [r["runs_allowed"] for r in records]
        totals = [s + a for s, a in zip(scored, allowed)]
        wins = sum(1 for r in records if r["won"])

        import statistics
        n = len(records)
        return {
            "games": n,
            "avg_runs_scored": round(sum(scored) / n, 3),
            "avg_runs_allowed": round(sum(allowed) / n, 3),
            "std_runs_scored": round(statistics.stdev(scored) if n > 1 else 0, 3),
            "avg_total": round(sum(totals) / n, 3),
            "win_pct": round(wins / n, 3),
            "over_5_5_pct": round(sum(1 for t in totals if t > 5.5) / n, 3),
            "over_7_5_pct": round(sum(1 for t in totals if t > 7.5) / n, 3),
            "over_9_5_pct": round(sum(1 for t in totals if t > 9.5) / n, 3),
        }

    def inning_run_distribution(self, team_id: str) -> dict[int, dict]:
        """
        For each inning (1-9), return:
            avg_runs, scoring_pct (probability team scores ≥1 run that inning)
        """
        records = self._games.get(team_id, [])
        inning_data: dict[int, list[int]] = defaultdict(list)
        for r in records:
            for idx, runs in enumerate(r["innings"][:9], start=1):
                inning_data[idx].append(runs)

        result = {}
        for inning, runs_list in inning_data.items():
            n = len(runs_list)
            avg = sum(runs_list) / n if n else 0
            scoring_pct = sum(1 for x in runs_list if x > 0) / n if n else 0
            result[inning] = {
                "avg_runs": round(avg, 3),
                "scoring_pct": round(scoring_pct, 3),
                "samples": n,
            }
        return result

    def matchup_history(self, team_id_a: str, team_id_b: str) -> list[dict]:
        """Return all recorded games between two teams."""
        records_a = self._games.get(team_id_a, [])
        team_b_names = {r["team_name"] for r in self._games.get(team_id_b, [])}
        return [r for r in records_a if r["opp_team"] in team_b_names]

    def all_team_ids(self) -> list[str]:
        return list(self._games.keys())

    def run_totals_list(self, team_id: str) -> list[int]:
        records = self._games.get(team_id, [])
        return [r["runs_scored"] + r["runs_allowed"] for r in records]

    def scored_list(self, team_id: str) -> list[int]:
        return [r["runs_scored"] for r in self._games.get(team_id, [])]

    def allowed_list(self, team_id: str) -> list[int]:
        return [r["runs_allowed"] for r in self._games.get(team_id, [])]
