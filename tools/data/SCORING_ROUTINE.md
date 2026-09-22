# End-of-day SCORE routine

Runs every weekday after the close as a scheduled Claude session. It fills the **SCORE** column
(TRADING LOG > HOME table and TRADES table) for every trade taken that day, futures and stocks
alike. A trade it cannot get price data for is marked **NA**, and the pill says why.

## Steps (the scheduled session follows these exactly)

1. Make a worktree: `python tools/wt.py new score-<YYYYMMDD>` and work inside it.
2. `python tools/score_day.py --days 3` - looks at today and the two sessions before it (so a
   missed day catches up), fetches and caches 1-minute bars, writes NA entries for trades with
   no data, and lists the trades to score in `tools/data/score_pending.json`.
3. Nothing listed as AUTHOR and no new NA -> stop. Nothing to ship.
4. For each pending trade, read its bars (`bars_et` = [time ET, open, high, low, close, volume])
   and append one object to `trades` in `tools/data/trade_scores.json`:
   - `sym, date, dir, entry_time, exit_time, entry, exit, qty` copied from the worksheet.
   - `"key_time": true` (one score per trade; required).
   - `interval: "1m"`, `breakout_candle` (HH:MM of the signal bar), `stop` (the structural
     stop: the signal bar low for a long, its high for a short).
   - `hold_from` only when the fill came at the close of the entry bar - set it to the next bar.
   - `setup` and `exec` factor lists using the rubric below; `overall` is roughly the average of
     the two totals; `summary` is 2-3 plain-English sentences, addressed to the trader.
   - Use the trade's own `notes`, `setup`, `grade` fields as context.
5. `python tools/trade_scores.py --apply`, then bump VERSION + prepend a one-line CHANGELOG
   note ("SCORES: n trades from <date> scored, m marked NA"), and
   `python C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\wt.py ship score-<YYYYMMDD>`.
6. Never delete anything in `tools/data/score_bars/` - once Yahoo ages a day out (~30 days for
   1m) the cache is the only copy.

## Rubric

Weights per side add to 100. Scores are integers from 0 to the weight. Notes are one short,
factual sentence with the actual prices.

**Stocks (momentum / gappers)**, the original rubric:
SETUP - Catalyst / RVOL 15, Front-side structure 20, Entry location 20, Risk definition 15,
R:R to a real level 10, Liquidity 10, Time of day 10.

**Futures (MES / MNQ / ES / NQ ...)**:
SETUP - Trend / context 20, Entry location 20, Risk definition 15, R:R to a real level 10,
Setup match (does it meet the tagged setup's rule, e.g. ENGU) 15, Liquidity / volatility 10,
Time of day 10.

**Execution (both)**: Entry timing 25, Risk control / MAE 25, Exit vs MFE 25, Sizing 15,
Plan adherence 10.

Exit vs MFE judges against what the tape offered in the next ~15 minutes, not only during the
hold, and says so in the note.
