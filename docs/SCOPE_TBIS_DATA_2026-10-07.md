# SCOPE: data quality - every master and cache, its holes, seams and split risk (TBIS lane, 2026-10-07)

Owner standing-order addendum 2 (2026-10-05) asked every lane for a scoping doc; MANAGER assigned TBIS the DATA scope
(inbox #33, #36): every master and research cache, its seams, holes, split flags and re-adjustment risk, and a fix order
under the master-write guard. TTIBS itself is parked (NQ and ES are one bet; r2 ETF and r3 hedged-stock variants dead).
This doc is a found-list with severity, not a pre-registration. Evidence files are in `C:\EdgeLog\_research_cache\split_qa\`.

## 1. What was checked (2026-10-04 .. 10-07)

- **121 registered masters** (`optimizer_history.db`, csv_files). 43 intraday NQ/ES masters (27 RTH, 16 ETH, 1m to 60m) were
  scanned bar by bar for incomplete sessions, duplicates, extra bars, missing weekdays and long gaps
  (`master_inventory_20261007.csv`, `master_holes_20261007.csv`).
- **56 Alpaca split-adjusted library masters** (5m, 30m, 1D) and **every Alpaca research cache** under `C:\EdgeLog\alpaca_cache`
  (tbis_r3, ttm_r20c, etf_daily, siporb, nqbrd) for splits the feed left unadjusted, with `tools/alpaca_split_scan.py`.
- **Yahoo vs Alpaca daily closes** for the funds both hold (Q9 cross-check, `q9_fund_xcheck_*_20261007.csv`).

## 2. Found-list, by severity

| # | Severity | What | Where | Status |
|---|----------|------|-------|--------|
| D1 | HIGH | Alpaca's `adjustment=split` left GE's 1-for-8 reverse split (2021-08-02) unadjusted; a 10-minute strategy booked a fake +$139k trade. The vendor has since corrected it, so caches pulled before 10-04 are on the old basis. | TBIS r3 (corrected in its driver), TTM r20c `GE_30m_split_rth.csv` | Re-pull, don't patch (ELwA 10-05). TTM told; its FAIL stands. |
| D2 | HIGH | Alpaca **1Day CLOSES are not the official close on stress days**. SPY 2020-03-12: Alpaca 255.24, official 248.11, Alpaca's own 10-minute session close 248.10 (+2.9%). 7 SPY days > 0.5% in 2016-2026 (2018-12-24, 2020-03-09/12/16/18/24, 2025-04-09). The 1Day OPENS are clean (max 0.06%). | `alpaca_cache\etf_daily\*_1Day_*.csv`, any 1D master | Close-based signals or marks should rebuild the close from regular-session intraday bars or use Yahoo. STRATEGY-BEATING: open-to-open fills, money unaffected; caveat stated. |
| D3 | MEDIUM | The loader's split guard (`split_like_gaps`) is **blind on daily bars stamped at midnight**: Alpaca 1D masters sit at 00:00 ET, outside the regular-session window, so every day is skipped and a missed split would pass `upsert_master` silently. | `tools/import_alpaca_stocks.py` | Reported to ELwA. `alpaca_split_scan.py` re-stamps such rows to 12:00 ET; all 56 library masters scan clean today. |
| D4 | MEDIUM | SIPORB `daily_split.parquet`: 369 whole-ratio overnight gaps, **64 with volume moving by about the inverse ratio = likely missed splits or ADR ratio changes** (e.g. CUZ 2019-06-17, a real 1-for-4). | `alpaca_cache\siporb` | Excluded by rule in SIPORB / ATTN / DDW (STRATEGY-BEATING #29). |
| D5 | MEDIUM | **One-minute masters and the TradingView-sourced 5m RTH masters have a July 2026 hole**: no sessions 2026-07-01 .. 08-05 (1m ETH, tv 5m RTH ids 23/26), and 2026-06-30 is a partial session (tv 5m: 16 of 78 bars; ES 1m RTH: 80 of 390). The roll-corrected 5m and 30m RTH masters (63/73/61) are complete. Known for NQ 1m since 08-13 (memory: 1m data hole); new here: it also covers the ES 1m and tv 5m masters, and the 10-05 owner decision moved paper ENGU-Q to the 1m roll-corrected master, so the ENGU-Q forward restatement crosses it. | ids 15-18, 23, 26, 30, 34, 58-59, 66-67 | Only NinjaTrader history can fill it (asked PAPER-NT8). Until then the ENGU-Q restatement must mark July 2026 as no-data, not zero-trade. |
| D6 | MEDIUM | ES and NQ **2020-02-28 and 2020-06-30 are truncated at the source** in every variant (02-28: 89 of 390 RTH minutes, last bar 10:58 ET; 06-30: 41). Nothing in the house can rebuild them. No TTM #459 trade touches either day. | all NQ/ES intraday masters | Asked PAPER-NT8 for those two sessions from Tradovate history; otherwise documented holes. |
| D7 | LOW | Weekday sessions missing in nearly every NQ/ES master: 2014-06-12/13, 2014-09-23..25, 2014-12-31; gaps of 4.7 days at 2012-10-26 (Hurricane Sandy, real closure) and 2014-06-11. | all NQ/ES masters (shared source) | Document. Sandy is a real closure; the 2014 days are source holes. |
| D8 | LOW | NQBRD `open_bars.csv` is entirely unadjusted (29 real splits show). | `alpaca_cache\nqbrd` | Harmless: NQBRD compares same-day bars only (STRATEGY-BEATING #29). NQBRD is dead anyway. |
| D9 | LOW | QQQ 5m master (id 50, `nt_noadj_rth`) has a bad row dated 1970-01-03, so its registered date_from is wrong. | master_655b1244.csv | Fix under the write guard: drop the row, keep every other row. |
| D10 | INFO | Yahoo files are **total return** (dividend-adjusted): `nonequity_close.csv` and the yahoo_adj masters TLT/IWM/QQQ/SPY. They differ from price-only series by the dividend on ex-dates (SPY ~0.5% quarterly). GLD pays none. | `_research_cache`, yahoo_adj masters | Expected; say "total return" when comparing with Alpaca or futures. |
| D11 | INFO | Alpaca re-adjusts history at query time: a cache is a photograph of the vendor on the day it was pulled. Provenance receipts (7fae8eeb) record time and content hash. | all Alpaca caches | Re-pull rather than patch; cite the receipt. |

| D12 | LOW-MEDIUM | QQQ 5m NT master (id 50): the 09:30 bar is an exact copy of the 09:25 bar on 63 of 75 days, the 15:55 bar is missing on 11 days, it has a NaN 1970 row, and it is stale since 2026-09-23. The Webull QQQ book does NOT read it (PAPER-WB); it came from a 09-01 NinjaTrader export. | master_655b1244.csv | Owner to be named (NT data side); no patch until then. |
| D13 | MEDIUM (FIXED 3a42a6c5) | An ADJ twin kept a provisional tail: ADJ_NQ_5m_RTH 10-07 15:55 had volume 2,645 vs the true 14,755. The bar had closed; the feed had not finished reporting it, and the ADJ build ran before the refresh that restated it. ELwA's fix applies feed restatements of recent bars and keeps the twins in step. Re-checked 10-09: 0 volume mismatches on all 19 twins, newest bars agree. | ADJ/FADJ masters | Fixed; re-check after any refresher change. |
| D14 | LOW | The 60m RTH masters hold back the NEWEST session's last bar (15:30-16:00) until the next build; it fills in a day later. | ids 46, 48, 64, 75 | Matters only to a live reader of 60m bars. |

**Roll-seam audit (10-08):** the 19 ADJ/FADJ masters step exactly at the roll table's 66 real switches, by the table's
offsets, with no stray steps in 16 years. The only bars whose open/high/low/close shift is not uniform are the bars that
contain a switch (the builder's synthetic in-bar roll bars). **Fresh-pull check (10-08):** all 63 recorded Alpaca 1Day
series re-pulled; 61 unchanged, and SPY's difference is a receipt taken before that day's extended session ended plus a
63-share volume revision - no historical price was restated. **ES 2020 holes (10-09, MANAGER #44):** 2020-02-28 and
2020-06-30 are real full sessions truncated in every ES/NQ master; they leave 4 undefined daily returns (02-28, 03-02,
06-30, 07-01). Yahoo's ES=F close is the 17:00 CME close, not 16:00, so it cannot fill them; NinjaTrader 1-minute history
is queued (PAPER-NT8), and daily-return harnesses skip the undefined pairs meanwhile.

Checked and clean: 0 duplicate timestamps and 0 extra-bar sessions in all 43 intraday masters; the ADJ, FADJ and NOADJ variants
share identical timestamps (their holes are the same); etf_daily split files have no split-like gaps; all 56 Alpaca
split-adjusted library masters scan clean (price-only and with the volume test).

## 3. Fix order under the master-write guard

1. **D5 / D6 (data holes in the futures masters)** - the only ones that touch adopted-book legs or the paper record. Wait for
   PAPER-NT8's answer on Tradovate history. If it reaches back, splice the missing sessions into the NOADJ masters with the
   atomic, refuse-to-lose-rows writer, rebuild the ADJ/FADJ twins from the roll table, and re-run the TTM #459 parity
   (355 trades, $72,716) and the ENGU-Q #335 parity as regressions. If it does not, keep them as documented holes and make
   the ENGU-Q forward restatement print July 2026 as "no data".
2. **D3 (guard blind on daily bars)** - ELwA's call, in `split_like_gaps`.
3. **D9 (QQQ 5m 1970 row)** - one-row drop under the guard.
4. **D1 / D4** - handled by re-pull and by exclusion rules; re-run `tools/alpaca_split_scan.py` after every Alpaca pull.
5. **D2** - a convention note for anyone using Alpaca daily closes.

## 4. Standing checks (what keeps this from recurring)

- `python tools/alpaca_split_scan.py` after any Alpaca pull (research caches), `--library` for registered masters; flags go to
  a dated file in `C:\EdgeLog\_research_cache\split_qa\` and to the owning lane and MANAGER.
- The master inventory and holes scan (this doc's section 1) should be re-run monthly or after any master rebuild; today's
  output is the baseline to diff against.
