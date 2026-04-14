# MLB Betting Analyzer

A command-line tool that pulls live and historical MLB game data from ESPN's
public API, builds Poisson-based run-distribution models, and outputs detailed
betting probabilities across a wide range of markets.

---

## Features

| Market | Command |
|---|---|
| Today's games | `games` |
| Moneyline, Run Line, Game Total | `analyze` |
| Per-inning scoring breakdown | `innings` |
| NRFI / YRFI (1st inning) | `nrfi` |
| Live in-game win probability | `live` |
| Team total (over/under) | `team-total` |
| Value prop scanner | `value` |
| Box score linescore | `boxscore` |

**What the model does**

- Fetches the last N days of MLB games from ESPN's public API
- Builds per-team offensive (runs scored) and defensive (runs allowed) distributions
- Models each team's run output as a Poisson random variable
- For a matchup, blends each team's offense against the opponent's defense
- Iterates over all (home_runs, away_runs) combinations to compute exact win/loss probabilities
- Computes over/under probabilities for full game, first 5 innings, and team totals
- For live games, scales expected runs by the fraction of the game remaining
- Detects value vs. sportsbook lines by comparing model probability to implied probability

---

## Installation

```bash
pip install -r requirements.txt
```

Python 3.10+ required.

---

## Usage

### List today's games

```bash
python main.py games
```

### Full pre-game analysis

```bash
# Bare minimum — just team names and a total line
python main.py analyze --home "yankees" --away "red sox" --total 9.0

# With sportsbook lines to find value
python main.py analyze \
  --home "dodgers" --away "giants" \
  --total 8.5 \
  --home-ml -160 --away-ml +135

# Use more history (30 days instead of default 14)
python main.py analyze --home "astros" --away "rangers" --total 8.0 --days 30
```

**Output includes:**
- Moneyline win probabilities (model vs. sportsbook)
- Run-line cover probabilities (±1.5)
- Full game O/U and First-5 O/U
- Per-inning expected runs and scoring percentage
- NRFI / YRFI
- When the first run is most likely to score

---

### Per-inning breakdown

```bash
python main.py innings --home "cubs" --away "cardinals"
```

---

### NRFI / YRFI

```bash
python main.py nrfi --home "mets" --away "phillies"
```

---

### Live in-game win probability

Feed in the current game state and get updated win probabilities:

```bash
python main.py live \
  --home "braves" --away "padres" \
  --home-runs 3 --away-runs 1 \
  --inning 7 --half top \
  --outs 1 \
  --runners "1B,2B"
```

---

### Team total

```bash
python main.py team-total \
  --team "angels" --opp "mariners" \
  --line 4.5 \
  --over-odds -115 --under-odds -105
```

---

### Value prop scanner

Compare model probabilities against your sportsbook's lines:

```bash
python main.py value \
  --home "houston astros" --away "texas rangers" \
  --total 8.5 \
  --home-ml -145 --away-ml +125 \
  --home-team-total 4.5 \
  --away-team-total 4.0
```

Bets are rated **STRONG** (>6% edge), **LEAN** (2–6% edge), or **PASS**.

---

### Box score

```bash
# Get the game ID from `python main.py games` first
python main.py boxscore 401696792
```

---

## Team Name Examples

The tool fuzzy-matches team names against ESPN data, so any of these work:

```
yankees          New York Yankees     NYY
dodgers          Los Angeles Dodgers  LAD
red sox          Boston Red Sox       BOS
cubs             Chicago Cubs         CHC
```

---

## Disclaimer

This tool is for informational and educational purposes only. It uses a
simplified Poisson model — real sports betting involves substantial risk.
Past performance does not guarantee future results. Always gamble responsibly.
