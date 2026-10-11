# DIP #424 fixed 1.245x: pre-live parity of the Webull signal path (DISC verifier, MANAGER GO 10-10)

**Verdict: PARITY on everything testable before the live build exists.**
- The live signal path (main's `api/dip_live.py` + `cloud_signal` DIP_424F config) reproduces #424's rules on QQQ
  exactly.
- Its open-position probe equals a plain full run on every one of 600 sessions.
- On 5m-built sessions it reproduces FRONTIER's Q37 research number to the cent.
- **One known, expected difference:** history from the official daily bar vs 5m-built bars changes some individual
  trades but not the total.
- **Still to do on Paper-WB's build when it lands:** the order layer (6 shares a lot, 7 lots, gross cap 85, the
  -$800 entry-block rail) and a re-run of both scripts on that worktree.

## What was checked
1. **Settings.** `DIP_424_PARAMS` equals #424's stored validate champion on all 27 keys. `best_params` equals the champion.
   - The strategy is NQDIP_1_1.py, unchanged. `asset="ETF"`, so roll seams are never used; the roll restatement does
     not apply to the QQQ leg.
   - Note: the champion's `streak_n = 0` is below the file's declared minimum of 2. With 0, STREAK buys every close
     above the 400-day trend while flat, and holds up to 4 days. It is #424 as run, so the live leg matches it. It is
     flagged only because it is the trend-beta slot.
2. **The open-position probe (seven single-mechanism passes + 32 pads at 1000x)** vs one plain full run with every
   mechanism on (`probe_parity.py`).
   - **Window:** every session L from 2023-11-09 to 2026-04-02 (600 sessions), on Alpaca QQQ daily.
   - **Result: 0 mismatches.** At every L, the probe's set of trades equals the full run's trades entered by L, with
     those exiting after L marked open. Each trade is compared on entry, exit-or-open, entry price and exit price.
   - Run at data end, the probe correctly reports a trade the plain run drops: the file drops a position still open
     when the data ends. That is why L stops 60 sessions short.
3. **The stitched daily series** (`stitch_parity.py`; a scratch box home with QQQ_1d = Alpaca daily and QQQ_5m = the
   Alpaca 5m master for 2026 H1, read through the LIVE loader `historical_bars -> closed_arrays -> build_daily_series`).
   - It is READY: 2,514 rows from 1d + 123 from 5m. Calibration: close 0.85 bp, open 0.00 bp, over 122 overlap sessions.
   - **5m-built vs official daily:** open / high / low are identical (median 0 bp). Close: median 0.86 bp, max 13 bp
     (the closing auction vs the last 5m bar).
   - **What the close source does to signals:** over the whole 2016-26 window, 17% of individual trades change (an exit
     day or an entry moves near a threshold), but the total does not.
     - Common window 2017-08-07 .. 2025-08-24: $629,059 on 5m-built closes vs $611,630 on official closes (+2.8%).
     - The live leg's recent sessions come from 5m, which is the research definition (Q37).
4. **Q37 anchor.** The same file on Alpaca 5m-built QQQ sessions reproduces Q37's QQQ RAW reading exactly: 1,995 trades,
   1,782 in its window, net $629,059.40.
5. **Fixed 1.245 (a check, not a re-decision; the owner's call).** The size enters only at recording, through
   `_keel_const_size`, so it can never change a signal. 1.245 is inside the guard (<= KEEL_CONST_MAX_SIZE 3.0, so it
   never falls back to 1.0). DIP_424F's trades are DIP_424K's trades by construction: the same `dip_positions`.
6. **The PC's QQQ_5m.csv (the Webull / yfinance capture) has a torn row on line 2** (time 75, close empty).
   - The live loader drops it: 87 complete sessions, the first on 2026-06-08.
   - Worth a look on the BOX's copy: a torn row that kept a close would date a 1969 session and read as a HOLE (the leg
     would sit NOT READY). The guard fails safe, but silently, apart from the once-a-day log.

## To run on Paper-WB's build (Monday, before the dry run)
```
set DIP_PARITY_REPO=C:\Users\xride\AppData\Local\EdgeLog-worktrees\<their worktree>
python C:\EdgeLog\_anatomy_cache\dip_parity\probe_parity.py 600
python C:\EdgeLog\_anatomy_cache\dip_parity\stitch_parity.py
```
Then check the order layer on the build itself:
- shares per lot x lots;
- the gross cap;
- the -$800 entry-block rail;
- that a live DIP entry carries the same slot ids and the 09:30-open reference as the shadow.
