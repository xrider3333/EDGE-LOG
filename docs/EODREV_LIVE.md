# Strategy 23 live signal (MISC_EODREV_1_2, engine RUN #511) - data side

Owner GO 2026-11-14 via MANAGER: stage strategy 23 to Webull PAPER. This file covers the OPUS-HUNT half
(signal + panel, no broker code). The executor (entries, MOC exits, fallback, loss rail) is PAPER-WB's.

## What runs
| When (ET) | Command | Writes |
|---|---|---|
| nightly / any time before 15:00 | `python -m api.eodrev_live refresh` | live panel `eodrev_u100_panel_live.npz` (rebuilt from scratch from Alpaca SIP, ~10-15 min) |
| 15:21 (sleeps to it itself) | `python -m api.eodrev_live signal --out-dir <dir>` | `signal_YYYY-MM-DD.json`, atomic, by ~15:24 |

The live panel is a SEPARATE file. The engine's pinned research panel (`eodrev_u100_panel_v1.npz`, SHA-pinned in
the plugin) is never written.

## Hand-off file (agreed with PAPER-WB 2026-11-14)
```
{"date","asof_et":"15:20:00","written_et","strategy":"MISC_EODREV_1_2","run":511,"status":"OK"|"SKIP","reason",
 "k":3,"long":[{"sym","px","score","exch"} x3],"short":[same x3],"universe_n","scored_n","panel_date","panel_sha",
 "params":{"k":3,"period_len":60,"period_wt":1.5,"beta_len":180,"min_price":60}}
```
- `px` = the 15:20 reference price (Alpaca IEX real-time, last 1-minute close in 15:10-15:19). The executor sizes
  from its own 15:30 quote.
- SKIP (no trade, no alert): holiday / half day (no SPY bars 15:10-15:19), fewer than 12 names scored, stale panel
  (a completed session is missing between the panel's last day and today).
- PAPER-WB gate at 15:29: file missing / wrong date / stale = no trade + alert. Entries 15:30, MOC by 15:45
  (inside NYSE 15:50 and Nasdaq 15:55 cutoffs), MARKET fallback 15:58.

## Params = the RUN #511 engine pick
k 3 a side, habit 60 sessions at weight 1.5, beta 180 sessions, $60 floor on yesterday's raw close. NOT the
plugin file's defaults (k 5, 40, 1.0, 60, $40).

## Checks
- `tests/test_eodrev_live.py`: picks equal the plugin's own on the pinned panel (61 sampled sessions); fields known
  only after 15:20 cannot move the picks; a live row (panel cut at yesterday + 15:20 prices) equals the replay row;
  file fields.
- IEX vs SIP: `C:/EdgeLog/_anatomy_cache/opus_hunt1109/s23_iex_check.py` replays the last 40 sessions with IEX
  15:20 prices in place of the SIP 15:10-bar close and counts how many of the 6 picks stay the same.

## Known limits
- The universe is the point-in-time top-100 list per calendar year (`tools/data/eodrev_universe_pit100.json`).
  2027 needs a new list before Jan 2; until then the newest list is used.
- The exchange map (`tools/data/eodrev_exchanges.json`) is today's listing, not point-in-time.
- A split on the signal day: the signal drops any name more than 25 pct off its last panel close (listed in "dropped").
