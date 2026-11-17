[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Humaedi95/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Humaedi95/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

# GTA VI Twitch CCU Forecast

Forecasts how many people watch Grand Theft Auto VI live on Twitch in
each hour of its release day (2026-11-19 UTC), from everything recorded
up to the end of hour 1 — as five quantiles (5%, 25%, 50%, 75%, 95%) per
hour, for hours 2–24. Entry for make.fun's
[Forecast GTA VI's launch-day Twitch viewers hour by hour](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
bounty ($250 in USDC).

## The model

`main.py` (Python 3.13, standard library only, no network) reads the
case file, anchors on hour 1's print, and borrows the day's shape from
the 38–42 past big console launches shipped in the case as comparables:

- Each comparable contributes its release day as 24 hourly viewer
  counts. Its log-ratio at hour *h*, `ln(viewers(h) / viewers(1))`,
  is one vote for how hour *h* relates to hour 1.
- A comparable is weighted by how close its own hour-1 audience is to
  this case's hour-1 print, with a Gaussian kernel on the log scale
  (bandwidth 1.0). Launches whose first hour was tiny — a simultaneous
  global unlock hours after midnight UTC, or a slow burn — weigh almost
  nothing when this case's first hour is already substantial, which is
  exactly GTA VI's rolling-midnight situation (New Zealand unlocked at
  11:00Z on the 18th, central Europe at 23:00Z, the UK at 00:00Z).
- The forecast quantile at level τ for hour *h* is the τ-th weighted
  quantile of those log-ratios, exponentiated and multiplied by hour 1's
  print. The climb as each region unlocks, the prime-time peaks (hours
  19–22) and the late-night fall are therefore the shapes past launches
  actually drew, re-centred on this launch's own first hour — and the
  spread at each hour is the spread those launches showed, so far-out
  hours honestly get wider bands. Nothing is hardcoded to a game name.

## Local validation

The kit ships no practice answers (the practice is graded server-side),
so the model was validated by leave-one-out over the 34 usable
comparables in each practice case file: each comparable in turn played
the case (hour 1 known, hours 2–24 scored against its real counts),
with the other 33 as its comparables. Mean pinball loss on the log
scale:

| | model | house baseline |
|---|---|---|
| mean loss | **0.385** | 0.693 |
| median loss | **0.248** | 0.300 |
| beats baseline | 29 / 34 launches | — |

Bandwidth 1.0 was picked on this same leave-one-out test (0.7: 0.389,
1.2: 0.387, 1.5: 0.415); widening the tails further made it worse.
On the four practice cases the forecast medians peak at 1.34×–3.31×
hour 1's print in hours 19–22. Output is deterministic: two runs on
the same case write byte-identical files, and every output passes the
format checks (23 rows, 5 non-decreasing quantiles each, all positive,
≤ 65,536 bytes).

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Entered on [make.fun](https://make.fun/?ref=spg1d5j0&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards
