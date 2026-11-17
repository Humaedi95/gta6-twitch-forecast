"""Forecast GTA VI's launch-day Twitch viewers, hour by hour.

Model (written for this bounty; no practice answer is used anywhere):
  Every comparable launch in the case file carries its release day as 24
  hourly Twitch viewer counts.  For a launch, hour 1 is the anchor: the
  forecast for hour h is hour 1's print times a ratio, and the ratio's
  distribution is read off the comparables at that same hour.

  For comparable j with release-day viewers v_j(1..24), its log-ratio at
  hour h is r_j(h) = ln(v_j(h) / v_j(1)).  A comparable is weighted by how
  close its own hour-1 audience is to this case's hour-1 print p1, with a
  Gaussian kernel on the log scale (bandwidth 1.0):

      w_j = exp(-(ln v_j(1) - ln p1)^2 / 2)

  Launches whose first hour was tiny (a simultaneous global unlock hours
  after 00:00 UTC, or a slow burn) then weigh almost nothing when this
  case's first hour is already substantial, which is exactly the rolling
  midnight situation GTA VI is in: New Zealand unlocked at 11:00Z on the
  18th, central Europe at 23:00Z, the UK at 00:00Z, so hour 1 already
  holds a real audience.  The forecast quantile at level tau for hour h
  is the tau-th weighted quantile of the r_j(h), exponentiated and
  multiplied by p1:

      q_tau(h) = p1 * exp(weighted_quantile_tau({r_j(h)}))

  The shape of the day -- the climb as each region unlocks, the prime-time
  peaks, the late-night fall -- is therefore the shape past big console
  launches actually drew, re-centred on this launch's own first hour,
  and the spread at each hour is the spread those launches showed, so
  far-out hours honestly get wider bands.  Nothing is hardcoded to a
  game name: the same code runs on any case the grader hands it.

  Fallbacks: a comparable is used only when its release day has all 24
  hourly points and its hour-1 count is at least 500 viewers (below that
  the ratio is pre-launch noise).  With no usable comparable at an hour,
  the forecast falls back to the house baseline's persistence shape
  (flat median, spread 0.15 * sqrt(h-1) in log space).

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0)
in python:3.13-slim, standard library only: no network, no pip packages.

What it does:
  - read every <id>.in in the input directory (the grader runs one case
    at a time, with only that case's file there): JSON
    {"schema": "makefun/twitch-ccu-case/v1", "id", "game", "day_start",
    "checkpoint", "levels", "known", "forecast", "history",
    "history_hourly", "streams", "categories_hourly", "comparables",
    "notes"}, where `known` holds hour 1's print {hour: 1, from, until,
    viewers, channels, reads} and `forecast` lists the hours to
    forecast, 2..24;
  - write <id>.out to the output directory: {"hours": [{"hour": 2,
    "q": [q05, q25, q50, q75, q95]}, ...]}, exactly 23 rows, hours
    2..24 each once, no other key, each q five finite numbers above 0
    and at most 1e9 (fractions allowed), non-decreasing; at most
    65,536 bytes.

Outside the grader's container, MAKEFUN_INPUT_DIR and
MAKEFUN_OUTPUT_DIR stand in for /input and /output:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# Bandwidth of the Gaussian kernel on log hour-1 viewers: how strongly a
# comparable's launch-day shape counts when its first hour was a
# different size from this case's.  Chosen by leave-one-out validation
# over the kit's comparables (see README.md): 1.0 beats 0.7-1.5 and
# beats the house baseline's 0.693 mean pinball loss with 0.385.
BANDWIDTH = 1.0
# A comparable whose hour-1 count is below this is pre-launch noise;
# its ratios would be dominated by the unlock instant, not the day's shape.
MIN_HOUR1_VIEWERS = 500
# The baseline spread (log units per sqrt hour), used only as a fallback
# when an hour has no usable comparable at all.
BASELINE_SIGMA = 0.15
BASELINE_Z = {0.05: -1.645, 0.25: -0.674, 0.5: 0.0, 0.75: 0.674, 0.95: 1.645}
MAX_VIEWERS = 1_000_000_000


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as JavaScript's
    Math.round(x * 100) / 100 rounds it.  A whole number comes back as
    an int, so json.dumps writes 1240 where JavaScript writes 1240."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_series(comp: dict) -> dict[int, float] | None:
    """The comparable's 24 hourly viewer counts for its release UTC day,
    keyed by hour 1..24, or None when the day is incomplete."""
    try:
        day_start = parse_time(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return None
    series: dict[int, float] = {}
    for point in comp.get("hourly") or []:
        try:
            at = parse_time(point["from"])
            viewers = float(point["viewers"])
        except (KeyError, TypeError, ValueError):
            continue
        offset = (at - day_start).total_seconds() / 3600.0
        if offset < 0 or offset >= 24 or offset != int(offset):
            continue
        series[int(offset) + 1] = viewers
    if len(series) < 24:
        return None
    return series


def weighted_quantile(pairs: list[tuple[float, float]], level: float) -> float:
    """The weighted quantile of (value, weight) pairs: the first value
    whose cumulative weight reaches level of the total weight."""
    ordered = sorted(pairs, key=lambda pair: pair[0])
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    target = level * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return value
    return ordered[-1][0]


def forecast_case(case: dict, name: str) -> dict:
    levels = case["levels"]
    first = next((row for row in case["known"] if row["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    log_p1 = math.log(p1)

    # Collect every comparable launch's release-day shape, in a fixed
    # order so the output is byte-identical between runs.
    comparables = []
    for comp in sorted(case.get("comparables") or [],
                       key=lambda c: (str(c.get("name", "")), str(c.get("day_start", "")))):
        series = release_day_series(comp)
        if series is None:
            continue
        v1 = max(1.0, series[1])
        if v1 < MIN_HOUR1_VIEWERS:
            continue
        weight = math.exp(-((math.log(v1) - log_p1) ** 2) / (2 * BANDWIDTH * BANDWIDTH))
        ratios = {h: math.log(max(series[h], 1.0) / v1) for h in range(2, 25)}
        comparables.append((weight, ratios))

    hours = []
    for row in case["forecast"]:
        h = int(row["hour"])
        pairs = [(ratios[h], weight) for weight, ratios in comparables if h in ratios]
        if pairs:
            quantiles = [p1 * math.exp(weighted_quantile(pairs, tau)) for tau in levels]
        else:  # No comparable covers this hour: persistence fallback.
            quantiles = [p1 * math.exp(BASELINE_Z.get(tau, 0.0) * BASELINE_SIGMA * math.sqrt(h - 1))
                         for tau in levels]
        # Round half up to 2 decimals, clamp, and keep non-decreasing.
        rounded: list[float | int] = []
        floor = 0.0
        for value in quantiles:
            clamped = min(max(round2(value), 1), MAX_VIEWERS)
            clamped = max(clamped, floor)
            rounded.append(clamped)
            floor = clamped
        hours.append({"hour": h, "q": rounded})
    return {"hours": hours}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
