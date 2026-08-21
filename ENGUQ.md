# ENGU-Q — status, results & open work

> Living handoff doc, same shape as `ORB.md` / `NOISE.md`.
> **Created 2026-08-20** (Claude Code). Background: memory `engu-q-project`,
> forward-test wiring in `PAPER_TRADING.md`.

The deployed config is the **frozen clock-scaled #149 transfer, ETH-scaled (#226)** —
`augur_strategies/ENGUQ_1M_ETH_FROZEN_1_0.py`, every knob pinned:

```
tl_len 170 · ema_len 1380 · atr_len 106 · buf_atr 0.9 · vol_mult 0.8
stop_mult 1.0 · act_R 2.5 · trail_frac 2.5 · min_brk 1.3 · breakeven_R 1.5
regime_len 0 (OFF)
```

It is **long only** (`DIRECTION = "LONG"`): a green candle breaking a descending trendline
of recent lower highs, above the trend EMA, on a volume spike; stop at the swing low;
trailing exit.

---

## §1 — ⚠ THE EDGE IS A HANDFUL OF TRADES (measured 2026-08-20) — READ BEFORE JUDGING A DRAWDOWN

<a id="concentration"></a>

**This is the section to point a session at.** Measured on the deployed #226 config over
NQ 1m ETH, 2018-01-01 → 2026-08-20, n = 1,515 trades, cost 0.533 pts, 1 contract.

### 1.1 The concentration

| measure | value |
|---|---|
| net (2018+) | $358,368 |
| win rate | **27.0%** |
| average trade | +0.168 R |
| **top 10 winners** | **$295,811 = 83% of all net profit** |
| **top 30 winners** | **178% of net** — i.e. every other trade *combined* is negative |
| max drawdown | $50,420 |

**This is not a plateau of winning trades. It is a lottery-ticket distribution.** Owner
2026-08-20, on being shown the numbers: *"idk why we didnt catch that. that doesnt seem
like a platue of winning trades to me."* He is right that it was never surfaced — every
report we had graded it on net / PF / MAR, and all three look healthy while the shape
underneath is this skewed.

**Consequences that follow directly, and should be stated whenever this strategy is discussed:**

- A long run of losers is the *normal* state, not evidence of breakage. Over 2018+,
  **47% of all 6-trade windows contain 5 or more losers.** Streaks of 6+ losers occurred
  63 times; the record is **21 in a row**.
- Any forward-test window short enough to miss a top-10 winner will look like a losing
  strategy, *whether or not anything is wrong*. Paper trading started 2026-08-11 — far too
  short a window to contain one.
- The usual pre-registered bars (net/DD, PF) have very wide confidence intervals on a
  distribution this skewed. See memory `edgelog-netdd-unreliable`.

### 1.2 What is NOT wrong (all checked trade by trade, 2026-08-20)

- **The stop is never violated.** Every single losing trade closes at exactly **−1.00 R**.
  No gap-throughs beyond the modelled open-fill rule, no runaway losses.
- **Big-dollar losses are big *stops*, not broken stops.** Size is always 1 contract while
  stop distance ranges ~29–485 pts, so risk per trade ranges **$585 – $9,716** (median
  $870, p90 $2,878). Record single loss: −$9,716 on 2026-03-23 against a 485-pt stop.
- **August 2026 was a good month in risk terms and a bad one in dollars**: −$6,772 but
  **+3.29 R** total, averaging +0.235 R against the +0.168 R all-time average. All four
  winners had small stops; the two largest-stop trades (207 pt, 233 pt) both lost. That
  mismatch is the entire month. Context: NQ fell 30,338 → 29,207 (−3.7%) over 8/17–8/20.
- Position in the distribution as of 2026-08-20: last-14-trade net at the **17th
  percentile** of all 14-trade windows, last-30 at the **15th**. Below average, inside
  normal. Equity peaked 2026-06-11; drawdown since is $40,932 of a $50,420 record.

### 1.3 Sizing is NOT the answer — do not re-propose it

Equalizing dollar risk per trade is the obvious reaction to §1.2 and it **measures worse**.
Capital-matched (mean size = 1 contract), rolling-median risk parity capped at 3×, same
window:

| rule | net | max DD | MAR |
|---|---|---|---|
| 1 contract (deployed) | $358,368 | $50,420 | **7.11** |
| rolling risk-parity, cap 3× | $155,869 | $29,905 | 5.21 |

It halves the drawdown and cuts the profit by more. The reason is §1.1: the edge lives in
the **big-stop** trades — stops ≥120 pts are 209 trades carrying **$259,410 of the
$358,368 net** — and de-levering them removes the thing that pays. This is a *second*,
independent reason on top of the earlier global-rp rejection (`BACKTESTING_STACK.md`
2026-07-23, "DEAD/REJECTED: S2", where global normalization also de-levered the modern
era). Related memory: `edgelog-transfer-sweep-2026-08`.

Note the one honest caveat: at 1 contract the strategy cannot express risk equalization at
all on NQ. A 233-pt stop is $4,670 minimum. Sizing DOWN would need MNQ micros; sizing UP is
a separate, un-pre-registered question.

### 1.4 OPEN WORK — the regime filter has never been tested on this config

`regime_len` is **pinned to 0 (off)** in the deployed file, so the only trend gate is
`close > EMA(1380)` — on 1m ETH bars that is roughly **one day** of trend. In a multi-day
slide with sharp intraday bounces, price pops back above a one-day EMA repeatedly and the
strategy buys every bounce. That is exactly the 8/17–8/20 pattern.

Owner 2026-08-20: *"we will ahe to try it with thte filter on."* **This is the sanctioned
next test.** Unlike sizing, it has never been run on the #226 ETH config.

What to do, and what to pre-register BEFORE running it:

- **FIRST, fix a mis-scaling — verified 2026-08-20.** `run_backtest` computes the regime
  window as `rb = regime_len * 390`, commented *"390 RTH bars/day"*
  (`ENGUQ_1M_ETH_1_0.py`, in the `if int(regime_len) > 0:` block). This ETH file scaled
  `ema_len` / `tl_len` / `atr_len` by ~×3.54 for the 24h tape but **left this 390 alone**,
  so on ETH bars `regime_len=20` is really ~5.7 days, not 20. Any regime sweep run as-is
  is sweeping the wrong lengths. Either pass ETH-scaled values knowingly, or fix the
  constant to ~1,380 — and say which in the pre-registration.
- Grid used elsewhere in the file's presets: `[0, 20, 30, 50, 75]`.
- Pre-register the bar before running, in this file, with a date. The house standard is a
  lockbox-held improvement, not an in-sample one — and given §1.1, judge on **PF and the
  lockbox slice**, not net/DD.
- Expect a filter to *cut* net: it will remove bounce-buying in downtrends but also remove
  some of the top-10 winners, which is where all the money is. The interesting outcome is
  a drawdown reduction that costs less than proportional profit.
- Matched control: the deployed `regime_len 0` run over the identical window. Pin
  `date_from`/`date_to` to the baseline — see memory `edgelog-rerun-window-pinning`.

Reproduce the §1 numbers: load `find_master('NQ','1m','eth')` from 2018-01-01,
`run_backtest(..., return_trades=True)` with the pinned params above; each trade tuple is
`(entry_bar, exit_bar, pnl_pts, 1, entry_px)` and per-trade risk is
`entry_px - low[entry_bar-170 : entry_bar+1].min()`.

---

## §2 — Forward test

Two legs run side by side on the PAPER board, as a matched pair:

- **ENGU-Q RAW** — the #226 config above, live from 2026-08-17.
- **ENGU-Q · LIMIT 0.50** — identical in every knob; the only difference is that it rests a
  limit order 0.50 ATR below the signal close and drops the trade if it does not fill
  within ten bars. Live from 2026-08-18. It **fails** the pre-registered net-per-drawdown
  bar (8.32 vs 8.62) because entering lower against the same stop widens risk. Candidate,
  not a winner.

Both are engine-side; NinjaTrader runs RAW only (`EdgeLogENGUQ1m` on DEMO7240108). See
`PAPER_TRADING.md` and memory `edgelog-paper-trading`.

---

## §3 — Changelog

- **2026-08-20** — File created. §1 written after the owner asked why ENGU-Q RAW was
  "hitting a lot of losses recently": the answer is §1.1, the answer is *not* a fault, and
  the sanctioned follow-up is §1.4.
