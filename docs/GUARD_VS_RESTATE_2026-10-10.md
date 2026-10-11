# Engine roll guard vs RESTATE_ROLL22 (DISC item B, MANAGER GO 10-10)

**Verdict:**
- The guard reproduces my restatement exactly on all 15 non-DIP runs.
- Its PLANNED line differs from mine only through those files' own roll-day skip.
- **One defect: the guard MIS-SIZES DIP 1.0 / 1.1 (NQDIP_1_0 / NQDIP_1_1).** Their PLANNED profit is 23-36% too low
  (#424: $716,000 vs $1,121,440 for the same 3,444 trades).
  - The files size contracts from the price level (`notional / price`). The guard feeds them the difference-adjusted
    series, where 2011 NQ reads about 2.7x raw.
- Live and paper are not affected.

Tool: `tools/roll_guard_probe.py` (main), all 22 specs (saved champion, window, cost, db_noadj_rth), output in
`C:\EdgeLog\_anatomy_cache\restate_roll\guard_part*.jsonl` and `guard_300.jsonl`, joined by `guard_reconcile.py`.

## 1. Probe RAW = my restated line, exactly (15 of 15 non-DIP)
Since 17279c26 the 25 detector copies import `rolls.seam_days`, the true calendar. So the probe's RAW line is the file
with the true seams on raw prices, which is my restatement's definition reached by a different route.
- It matches trade count and net to the dollar on TTIBS #161 #164 #165 #167 #168 #169 #170 #174 #201 #291 #300,
  GAPGO #329 #330 #399 and RSIDIV #163.
- Example: #300 is 703 trades / $385,776 on both.

## 2. PLANNED vs mine: non-DIP (roll-day skip only, 0 price moves)
On the planned path the file trades straight through the switches (no step to skip), so trades move only where the
file's own seam skip used to bite. The probe attributes every moved trade to that skip: 0 moves by price on all 14
difference files.

| run | mine (restated) | guard PLANNED | trades moved by the file's roll-day skip |
|---|---|---|---|
| TTIBS #300 | 703 / $385,776 | 698 / $414,094 (DD $48,156) | 93 |
| TTIBS #291 | 688 / $302,571 | 687 / $286,687 | 61 |
| TTIBS 1.0 (9 void runs) | e.g. #161 687 / $416,397 | 685 / $423,663 | 44-86 |
| GAPGO #329 | 1,875 / $187,548 | 1,901 / $186,185 | 26 |
| GAPGO #330 / #399 | 2,036 / $182,036 | 2,071 / $182,663 | 35 |
| RSIDIV #163 | 308 / $1,527,722 | the same: method "raw" (level-dependent), no crossings, not refused | - |

- These are two legitimate definitions. Mine keeps each file's own roll-day rule on the true roll days (MANAGER #65's
  PURE definition). The guard's drops the rule, because adjusted prices have no step.
- They differ by -5% to +7% of net. No crown changes either way: TTIBS #300 stays ahead of #291 under both.
- Note: the guard classes RSIDIV as "raw" (level-dependent). My 10-09 shift/scale test classed it "ratio" (x2 moved 0%
  of trades, 2012-18). The guard's whole-window test with its own C and k is the binding one. The result is the same
  either way here, because RSIDIV flattens before every switch.

## 3. PLANNED vs mine: DIP 1.0 / 1.1. THE DEFECT
| run | PURE (mine) | 1.2/1.3 twin | guard PLANNED | PLANNED / twin |
|---|---|---|---|---|
| #424 (1.1) | 3,404 / $1,121,941 | 3,444 / $1,121,440 | **3,444 / $716,000** | 0.64 |
| #401 (1.1) | 1,384 / $650,913 | 1,394 / $648,648 | 1,394 / $422,454 | 0.65 |
| #315 (1.1) | 1,517 / $649,849 | 1,526 / $651,018 | 1,526 / $435,701 | 0.67 |
| #423 (1.0) | 1,328 / $602,378 | 1,336 / $600,514 | 1,336 / $407,877 | 0.68 |
| #400 (1.0) | 1,303 / $511,182 | 1,315 / $510,369 | 1,315 / $327,426 | 0.64 |
| #307 (1.0) | 898 / $476,137 | 906 / $487,450 | 906 / $305,146 | 0.63 |
| #425 (1.0, ES) | 1,035 / $382,754 | 1,036 / $383,911 | 1,036 / $299,193 | 0.78 |

**The PLANNED trade set IS the twin's** (counts identical on all 7), but the profit is 22-37% short.

**#424 by year, PLANNED / twin:**
- 2011 0.36, 2012 0.40, 2013 0.45, 2015 0.49, 2017 0.58, 2019 0.65, 2021 0.89, 2023 0.88, 2026 1.00.
- That is the raw / back-adjusted price ratio (2011 NQ: about 2,270 raw vs about 6,000 adjusted). The contract count
  `max(1, round(notional / (price x 2)))` is computed from the ADJUSTED price.
- 1.2 / 1.3 size from `do_raw` and are ROLL_AWARE (run raw), so they are right.

**Why the guard misses it:** its method test compares TRADE TIMING under +C. DIP's signals are shift-invariant, so it
passes as "difference". But DIP's dollar P&L reads the level through its size. Re-pricing the entry / exit fields to
raw cannot fix a dollar P&L the file already computed.

**Who is affected:**
- Any research / runner / Auto-Validate run of NQDIP_1_0 or NQDIP_1_1 on an unadjusted NQ / ES master since 10-09 (and
  the roll stamp of any such saved run).
- **Not affected:**
  - the live and shadow DIP legs: QQQ, declared no-roll;
  - DIP_424K's KEEL training: a report-only tool, run raw;
  - FRONTIER Q37: its NQ arm is my PURE line, 3,404 trades, worst DD $98,294.93;
  - NQDIP 1.2-1.4;
  - the ETF DIP files.

**Fix options (guard owner's call):**
1. Treat a `PNL_UNITS = "usd"` file that is not ROLL_AWARE as level-reading. It then gets raw prices and the true seam
   calendar, so DIP 1.0 / 1.1, which hold across switches, are REFUSED with a pointer to their roll-aware twins
   1.2 / 1.3.
2. Or add the $ P&L to the invariance test, so a +C that changes dollars is not "difference".
   - On its own this lands DIP on "ratio". A ratio-adjusted series still inflates early levels, so the sizing stays
     wrong.
   - So option 1, refuse and point to the twin, is the correct fix.
