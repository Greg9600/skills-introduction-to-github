"""
ESPN MLB Data Fetcher
Pulls live and historical game data from ESPN's public API.
"""

import time
import requests
from datetime import datetime, timedelta
from typing import Optional


BASE = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
CORE = "https://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb"
SUMMARY_URL = f"{BASE}/summary"
SCOREBOARD_URL = f"{BASE}/scoreboard"
TEAMS_URL = f"{BASE}/teams"


class ESPNDataFetcher:
    """Fetches MLB game data from ESPN's public API."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MLB-Analyzer/1.0"})

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"ESPN API error ({url}): {exc}") from exc

    # ------------------------------------------------------------------
    # Scoreboard / game listings
    # ------------------------------------------------------------------

    def get_scoreboard(self, date: Optional[str] = None) -> list[dict]:
        """
        Return a list of game summaries for a given date (YYYYMMDD).
        Defaults to today.
        """
        params = {}
        if date:
            params["dates"] = date
        data = self._get(SCOREBOARD_URL, params)
        return data.get("events", [])

    def get_recent_games(self, days: int = 7) -> list[dict]:
        """Return all games from the last N days."""
        games = []
        for offset in range(days, -1, -1):
            d = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
            try:
                games.extend(self.get_scoreboard(d))
                time.sleep(0.2)
            except RuntimeError:
                pass
        return games

    # ------------------------------------------------------------------
    # Full game detail (box score + play-by-play)
    # ------------------------------------------------------------------

    def get_game_summary(self, game_id: str) -> dict:
        """Return the full ESPN summary for a specific game."""
        return self._get(SUMMARY_URL, {"event": game_id})

    # ------------------------------------------------------------------
    # Team helpers
    # ------------------------------------------------------------------

    def get_all_teams(self) -> list[dict]:
        data = self._get(TEAMS_URL)
        sports = data.get("sports", [])
        leagues = sports[0].get("leagues", []) if sports else []
        return leagues[0].get("teams", []) if leagues else []

    def find_team_id(self, name: str) -> Optional[str]:
        """Fuzzy-match a team name/abbreviation to its ESPN team id."""
        name_lower = name.lower()
        for entry in self.get_all_teams():
            t = entry.get("team", {})
            candidates = [
                t.get("displayName", ""),
                t.get("shortDisplayName", ""),
                t.get("abbreviation", ""),
                t.get("name", ""),
                t.get("location", ""),
            ]
            if any(name_lower in c.lower() for c in candidates if c):
                return t.get("id")
        return None

    def get_team_schedule(self, team_id: str) -> list[dict]:
        url = f"{BASE}/teams/{team_id}/schedule"
        data = self._get(url)
        return data.get("events", [])

    # ------------------------------------------------------------------
    # Parsed convenience methods
    # ------------------------------------------------------------------

    def parse_linescore(self, summary: dict) -> dict:
        """
        Extract inning-by-inning run totals from a game summary.
        Returns:
            {
              "home": {"name": str, "innings": [runs, ...], "R": int, "H": int, "E": int},
              "away": {"name": str, "innings": [runs, ...], "R": int, "H": int, "E": int},
            }
        """
        header = summary.get("header", {})
        competitions = header.get("competitions", [{}])
        comp = competitions[0] if competitions else {}
        competitors = comp.get("competitors", [])

        result = {}
        for c in competitors:
            side = c.get("homeAway", "home")
            team_name = c.get("team", {}).get("displayName", "Unknown")
            linescores = c.get("linescores", [])
            innings = [ls.get("displayValue", "0") for ls in linescores]
            innings_int = []
            for v in innings:
                try:
                    innings_int.append(int(v))
                except ValueError:
                    innings_int.append(0)

            # Totals come from the score object
            runs = 0
            try:
                runs = int(c.get("score", "0"))
            except ValueError:
                pass

            result[side] = {
                "name": team_name,
                "innings": innings_int,
                "R": runs,
                "H": 0,
                "E": 0,
            }

        # Hits & errors live in the boxscore
        boxscore = summary.get("boxscore", {})
        for team_entry in boxscore.get("teams", []):
            side = team_entry.get("homeAway", "")
            stats = {s["name"]: s["displayValue"] for s in team_entry.get("statistics", [])}
            if side in result:
                try:
                    result[side]["H"] = int(stats.get("hits", "0"))
                except ValueError:
                    pass
                try:
                    result[side]["E"] = int(stats.get("errors", "0"))
                except ValueError:
                    pass

        return result

    def parse_batting_stats(self, summary: dict) -> dict:
        """
        Return per-player batting stats keyed by homeAway side.
        Each entry: list of {name, AB, R, H, HR, RBI, BB, K, AVG}
        """
        result = {"home": [], "away": []}
        boxscore = summary.get("boxscore", {})
        for team_entry in boxscore.get("players", []):
            side = team_entry.get("homeAway", "")
            players_data = team_entry.get("statistics", [{}])
            if not players_data:
                continue
            stat_names = [s.get("abbreviation", "") for s in players_data[0].get("labels", [])]
            for athlete_entry in players_data[0].get("athletes", []):
                name = athlete_entry.get("athlete", {}).get("displayName", "?")
                vals = athlete_entry.get("stats", [])
                stat_dict = dict(zip(stat_names, vals))
                result.setdefault(side, []).append({"name": name, **stat_dict})
        return result

    def parse_pitching_stats(self, summary: dict) -> dict:
        """
        Return per-pitcher stats keyed by homeAway side.
        Each entry: {name, IP, H, R, ER, BB, K, ERA}
        """
        result = {"home": [], "away": []}
        boxscore = summary.get("boxscore", {})
        for team_entry in boxscore.get("players", []):
            side = team_entry.get("homeAway", "")
            stats_sections = team_entry.get("statistics", [])
            for section in stats_sections:
                if section.get("type", "") != "pitching":
                    continue
                stat_names = [s.get("abbreviation", "") for s in section.get("labels", [])]
                for athlete_entry in section.get("athletes", []):
                    name = athlete_entry.get("athlete", {}).get("displayName", "?")
                    vals = athlete_entry.get("stats", [])
                    stat_dict = dict(zip(stat_names, vals))
                    result.setdefault(side, []).append({"name": name, **stat_dict})
        return result

    def get_plays(self, game_id: str) -> list[dict]:
        """Return play-by-play entries for a game."""
        summary = self.get_game_summary(game_id)
        return summary.get("plays", [])
