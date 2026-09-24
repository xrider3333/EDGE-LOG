# End-of-day SCORE routine

Runs every weekday after the close as a scheduled Claude session (task "EDGE LOG · end-of-day
trade scores"). It fills the **SCORE** column (TRADING LOG > HOME table and TRADES table) for every
trade taken that day, futures and stocks alike. A trade with no price data is marked **NA**, and
the pill says why.

The session runs unattended, so it uses exactly ONE script and writes exactly ONE file. The shared
checkout's `.claude/settings.json` gives standing permission for those two things and nothing else.
Any other command stalls the run on an approval prompt nobody is there to click (the 2026-09-22
and 09-23 runs stalled that way on their first command).

## Steps (the scheduled session follows these exactly)

1. `python tools/score_routine.py start`
   - `RESULT: NOTHING TO SCORE` - done.
   - `RESULT: NA ONLY n` - go to step 3.
   - `RESULT: AUTHOR n` - go to step 2.

   Behind the scenes: a fresh worktree off origin/main, `tools/score_day.py --days 3` (today and the
   two sessions before it, so a missed day catches up), bars fetched and cached, NA entries written,
   and the trades to score copied to `tools/data/score_inbox/pending.json`.
2. Read `tools/data/score_inbox/pending.json` and write `tools/data/score_inbox/scored.json`: a JSON
   list with ONE object per pending trade, holding only these fields:
   - `date`, `sym`, `entry_time` copied from the pending trade, plus `trade_id` when it has one.
     They pair the score with its trade; every other fact (prices, times, size, direction) is
     copied by the script, so do not repeat them.
   - `breakout_candle`: HH:MM Eastern of the signal bar (a time that appears in `bars_et`).
   - `stop`: the structural stop - the signal bar low for a long, its high for a short.
   - `hold_from` (optional): only when the fill came at the close of the entry bar - the next bar.
   - `px_offset` (optional): only when the trade was on a different contract month than the bars.
   - `setup` and `exec`: lists of `{"label", "weight", "score", "note"}` - exactly the rubric rows
     below, in that order; `score` a whole number from 0 to the weight; `note` one short factual
     sentence with real prices and times from the bars.
   - `overall`: a whole number, roughly the average of the setup and exec totals.
   - `summary`: 2-3 plain-English sentences addressed to the trader ("you").

   `bars_et` rows are `[time ET, open, high, low, close, volume]`. When the journal logged another
   clock, `shift_min` is set and `et_entry_time` / `et_exit_time` are the real Eastern times - read
   the bars there. Use the trade's own `notes`, `setup` and `grade` as context.
3. `python tools/score_routine.py finish` - checks every score (any `FIX:` line names what to
   correct in scored.json; fix it and run finish again), writes the scores and NA entries, bakes
   them into index.html, bumps VERSION, adds the CHANGELOG line, ships to main and removes the
   worktree. It rebuilds the change on the newest main before every push attempt, so another
   session pushing at the same moment only costs a retry. `RESULT: SHIPPED vX` when done.

`python tools/score_routine.py abort` throws a run away; its inbox files are kept under
`tools/data/score_inbox/_aborted/`.

**Proving the permissions without publishing anything:** `start --selftest` builds one fake trade
(a copy of the real 2026-09-22 MNQ trade, id SELFTEST) from committed data; write scored.json for
it, then `finish --dry-run` runs every step except the commit and push.

Never delete anything in `tools/data/score_bars/` - once Yahoo ages a day out (~30 days for 1m)
the cache is the only copy.

## Data sources

Bars come from Yahoo 1m (~30 days), then the local unadjusted ES / NQ 1-minute masters in
augur_uploads for futures (any age, except their Jul 1 - Aug 5 2026 gap), then Yahoo 5m (~60 days)
for stocks. `python tools/score_day.py --all` re-checks the whole journal.

## Rubric

Weights per side add to 100. Scores are whole numbers from 0 to the weight. Notes are one short,
factual sentence with the actual prices.

**Stocks (momentum / gappers)** - SETUP rows, in order:
Catalyst / RVOL 15, Front-side structure 20, Entry location 20, Risk definition 15,
R:R to a real level 10, Liquidity 10, Time of day 10.

**Futures (MES / MNQ / ES / NQ ...)** - SETUP rows, in order:
Trend / context 20, Entry location 20, Risk definition 15, R:R to a real level 10,
Setup match 15 (does it meet the tagged setup's rule, e.g. ENGU), Liquidity / volatility 10,
Time of day 10.

**Execution (both)** - EXEC rows, in order:
Entry timing 25, Risk control / MAE 25, Exit vs MFE 25, Sizing 15, Plan adherence 10.

Exit vs MFE judges against what the tape offered in the next ~15 minutes, not only during the
hold, and says so in the note.
