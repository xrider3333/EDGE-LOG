# ROLL_AUDIT: contract-roll handling in the backtest evidence and the live/paper stack (final, 2026-09-25)

**Status: audit only.** Nothing was changed in the repo, Firestore, the runner, the gate service, the cloud box or any broker. No strategy file and no paper or live leg was touched.

**How this audit was made**
- **Round 1 (the draft).** Every number comes from a read-only local re-run through the strategy file's own `run_backtest`, with OMP_NUM_THREADS=1 and at most 2 processes. Each "before" figure was first checked against the saved run, book or document, and matches to the cent unless noted. Scripts are in `C:\EdgeLog\_anatomy_cache\rollaudit\work\<group>\`.
- **Completeness critic.** A separate agent listed missed code, the 2026 data tail, paper and live exposure, and internal contradictions (`critic.md`).
- **Round 2.** Five threads looked into the claims: the 2026 data tail, the paper record, live exposure, the round 16-18 harnesses, and house infrastructure. Two verifiers rechecked each thread with their own code. One reproduced the numbers; the other tested other explanations. Scripts are in `...\work2\<thread>\` and `...\work2\verify-<thread>-<lens>\`.
- **Firestore.** Round 1 made 20 read-only document reads. Round 2 made 23 more, all projected (paper record 14, plus 6 by its verifier; live exposure 2, plus 1). Nothing was written.
- **Housekeeping.**
  - A round-1 verifier briefly wrote `saved_runs.json` into the shared checkout root. It was moved out at once and was never tracked.
  - In round 2, importing `r16_misc_triage` created the gitignored `tools/__pycache__/r16_misc_triage.cpython-313.pyc` in the shared checkout.
  - Two files the audit relies on are not tracked in git: `augur_strategies/ENGUDQ_1M_ETH_1_0.py` and `tools/EdgeLogOHLCAddon.cs`.

**Verification legend** (used throughout)
- **V**: re-run independently by a second agent with its own code, and matched.
- **M**: measured by one agent whose "before" exactly reproduced the saved run, book, paper document or live log, but not re-run by a second agent.
- **I**: inferred from code, config, logs or file coverage, and not re-run.
- **SUPERSEDED**: a draft "est." figure that placed the June 2026 switch at 06-14 18:10 ET with offsets of 210.5-229.5 (NQ) and 49.5-54.4 (ES). The switch actually sits inside the 06-15 03:30 ET bar on NQ and the 05:30 ET bar on ES, at about +293 / +64 points (see 2.7). A corrected figure is given only where a verifier confirmed it; every other one is marked *to be recomputed*.
- **method-dependent**: the corrected figure changes with the correction method (additive, ratio or forward adjustment). The range is given.

---

## 1. The short version

- **No real-money order was affected.** NinjaTrader trades a demo account and Webull runs in paper mode. Two demo/paper sizing paths do learn from the unadjusted NQ data: the NinjaTrader ML gate and KEEL.
  - Correcting every roll would have turned one demo take into a skip: 09-22, 11 MNQ, +$2,612.50.
  - It would also have made one Webull paper order one share smaller.
  - Both changes sit inside the models' own seed noise. (V)
- **The September 2026 roll has already put fake trades into the paper record.** The data feed switched from the September to the December contract inside the 09-14 11:30 ET bar: NQ +304.5 points in one minute, of which about +295 is contract carry. On corrected prices these trades disappear (V except where marked):
  - the 09-14 NOISE long: -$980.66 per contract on 15 legs, -$17,855 in total. That it disappears is V on 5 legs ($5,656.63) and M on 4 ($4,468.22). The six SBS_V90_K6-K12 legs ($7,730.21) were never re-run, so for them it is inferred (I; 4.5.4);
  - the 09-16 ORB and ORB_R6 losers: -$1,930.66 and -$2,410.66;
  - part of ENGUQ_335's 09-14..09-16 loss: -$8,177 recorded, -$2,983 to -$6,197 corrected across offsets 288-300 (M). Most of it goes only at offsets 295-297.75 (-$2,983); the NT-style argument for that offset comes from one verifier, and the reproduce verifier did not confirm it as the corrected figure.
- **The three current books lose 8.0-8.5% once every leg is corrected, and all stay PASS 8/8.**
  - #396: $1,790,319 → $1,640,039.
  - #397: $1,773,541 → $1,623,261.
  - Adopted #366: $1,685,715 → $1,550,996.
  - Pre-lockbox drawdowns rise 12-22% (#396: $36,562 → $43,967). All of the rise comes from one new TTM short on 2020-03-17. (V)
- **ENGU-Q carries most of the change.** The #335 leg falls from $603,381 to $499,155 (-17%).
  - Only $38,985 of that is money booked across switches.
  - The rest is a different sequence of trades. One March 2023 entry dominates it: a stale regime average let it through just after a roll. It was a real five-month hold worth $65,121; on corrected prices it and a -$2,286 trade in the same window are replaced by 52 smaller trades worth $11,677.
  - ES #370 falls from $381,313 to $341,487. (V)
- **The draft's June 2026 estimates used the wrong time and too small an offset.** The June switch is inside the 06-15 03:30 (NQ) and 05:30 (ES) bars, at about +293 / +64 points. The 06-14 18:10 jump is a real weekend gap. Repaired properly (V):
  - the #335 leg loses another $5,860, not $4.2-4.6k;
  - ES #370 and #377 lose about $6.8k each;
  - #381 gains $6.3k and still fails.
  - Every other "est." figure must be recomputed.
- **TTM, NOISE and ORB.**
  - TTM legs lose 7-13% (#369: $135,884 → $121,491, V), and their lockboxes do not move.
  - NOISE moves about 1% (M).
  - ORB backtests are identical (V). But a roll inside a session does reach ORB: the 09-14 splice let the 09-16 paper losers through its volatility filter.
- **The house roll detector is wrong on every data type.**
  - On RTH data it finds 19 of 64 NQ and 16 of 64 ES switches, and flags about 33 news gaps instead.
  - On 24-hour data the switch happens inside a session, where the detector cannot see it.
  - The copy used in the round 16-18 harnesses catches 22 of 61 switches and deletes whole overnight gaps from held trades. (V)
- **No crown or PASS/FAIL verdict flips.** Four research findings do flip (V):
  - r18b's "every overnight stop level is worse": 1.0-1.5x ATR stops are a wash, and only 0.5x hurts.
  - r36 TRAVEL's triage pass.
  - The superseded July ENGU-Q run #152.
  - BOOKMARKS B7: PB20 long MAR 4.59 → 2.95. The best honest cell of that round is DBL7 long, at 5.58.
- **Two book choices lose evidence, and DIP drawdowns are understated.**
  - #396 over #366 now wins only the held-back year. The calendar-year test goes from 6 wins / 1 loss to 5 / 3 (M).
  - #397 trails #379 by 19% on the selection stretch in each of the three corrected states computed for #379 (TTM alone, TTM+NOISE, all three), against 1.4% before (M). The ENGU-Q-only state was not computed for #379.
  - DIP on ES #425's drawdown is $66,592-$68,714, not $54,016 (V).
  - Books #417-#419 ran four of their legs with no parameters. The TTM defaults reproduce the intended TTM leg exactly, so only the ORB, ENGU-Q and NOISE legs differ.
- **The data after 2026-06-05 and the house checks need repair before any re-validation.** (V)
  - The tail comes from Yahoo. It has two in-bar splices, a 37-day hole in the 1-minute masters and a missing Labor Day session.
  - The data-health roll check reports nothing today.
  - The registered "adjusted" 5-minute masters use a stale offset (about $248 of fake P&L per NQ roll since 2022) and stop adjusting after 2026-03-16.
  - 254 saved runs contain the June splice (M: one agent's classification; only the 281 and 13 counts are V); none reaches September.

### Urgent (live/paper)

These round-2 findings act on running systems today. None of them touches real money.

1. **The paper record for 09-14..09-16 holds fake trades (4.5.4).**
   - Shadow trades are re-upserted every night from the unadjusted master, so they stay until the master tail is repaired.
   - The 09-15 daily report is write-once. It still shows a blend of -$84,279 and a book of -$10,544.28. A second artifact that night explains about $48.3k of the blend: September-contract NT bars were appended after the December master (4.5.5). The other roughly $36k is post-splice ENGU-Q trades (4.5.4). (V)
2. **Both artifacts will recur at the December 2026 roll (expiry 12-18) unless fixed first.** That needs two things (see 6.6):
   - a contract check in the shadow loader, so it refuses NT capture bars on a different contract from the master;
   - a table row for the roll.
   - Also, any trailing-stop long open across an in-bar splice gets a fake stop-out. #381 in June is the worked example (3.2). (V)
3. **NOISE paper legs keep reading the 09-14 +1% bar** in their 40- and 44-session band windows until about 11-09 (NOISE_304) and 11-13 (SBS_V90); these end dates rest on one verifier (M). ORB's 5-session effect has already cleared (V).
4. **The NinjaTrader ML gate (demo account only)** is refit every night on the unadjusted master, which contains the splice.
   - The roll effect is small (4.5.2).
   - Round 2 also found non-roll defects that moved more demo money than the roll did. Route these to the NT8 paper lane. (V except where marked)
     - The 09-22 take was scored on an incomplete bar; with the complete bar it is a skip.
     - The four 09-23 timeouts were the service's own 1.2-1.6 s rebuilds against NinjaTrader's 300 ms timeout (M: this link rests on one verifier). They let four ungated 3-MNQ shorts through, for -$1,150.50 (this total was independently recomputed from fills.csv).
     - The gate's price series went stale during roll week.
5. **KEEL (sizing for Webull NOISE on paper)** differs by 0 or 1 share today. The forward risk: the cloud box reports live credentials present, and the Webull go-live plan uses 1-3 shares. At a 1-share base a 1.5 multiplier rounds to 2 shares, but 1.43 rounds to 1. (V)
6. **The ENGUQ_ER_H gate model feeds paper rows.** It is refit on the NQ 1-minute 24-hour unadjusted master, the one most exposed to splices and the July hole. It feeds `tools/qqq_paper.py`'s ENGUQ_149 rows (paper only). (M)
7. **The reconcile tool maps NT8 fills to the wrong leg.** `api/paper_reconcile.py:73` maps NT8 'EQ' fills to ENGUQ_ER, although EdgeLogENGUQ1m has run the #335 settings since 09-08. So the 09-16 fills show as live-only under ENGUQ_ER, and ENGUQ_335's matching trades as shadow-only. (V)
8. **Auto-refresh keeps appending raw data to the "adjusted" 5-minute masters.** Every refresh appends raw Yahoo bars to the four registered twins, so the June and September 2026 splices sit unadjusted in them. (V)

---

## 2. The defect, measured

### 2.1 What the house detector does

`detect_roll_seams(day_open, day_close, day_ts, ratio_th=2.5, abs_th=15, base_win=60, pre_days=12, post_days=2)` is copied into about 20 files: TTIBS 1.0-1.3, NQDIP 1.0/1.1, RSIDIV, SUPERTREND 3.0, GAPGO/TRAVEL/GAPFADE, ONDRIFT and the round-13 TV ports.

- **How it picks a seam.** For each roll window (from 12 days before to 2 days after the third Wednesday of Mar/Jun/Sep/Dec), it takes the single day with the largest |day open - prior day close|. That day counts as the seam if the gap is at least 15 points and at least 2.5 times the 60-day median gap.
- **What the files do with it.** Depending on the file, they go flat the day before the seam, block fills, skip the day, or drop that night's gap from P&L.
- **A second, unwindowed variant** lives in `tools/r16_misc_triage.py`, `r17_misc_triage.py`, `r18_misc_triage.py` and `r18b_ondrift_stop.py`. It flags any day of the year that passes the same size tests (see 5.2).

### 2.2 Accuracy by data type

Ground truth is `switches_NQ.csv` / `switches_ES.csv`: 64 switches per root, 2010-06 to 2026-03, rebuilt from the raw per-contract Databento files with the masters' own stitch rule. Source: `detector_accuracy.json`.

| Root / feed | Switches on a day boundary | Inside a day | Caught | Missed | Days flagged | False flags |
|---|---|---|---|---|---|---|
| NQ 5m RTH (db_noadj_rth) | 64 | 0 | 19 | 45 | 52 | 33 |
| NQ 1m RTH | 64 | 0 | 19 | 45 | 53 | 34 |
| ES 5m RTH | 64 | 0 | 16 | 48 | 49 | 33 |
| ES 1m RTH | 64 | 0 | 16 | 48 | 49 | 33 |
| NQ 1m 24h, midnight days (engine day_id) | 9 | 55 | 4 | 5 (+55 unreachable) | 27 | 23 |
| NQ 1m 24h, 18:00 ET sessions | 9 | 55 | 3 | 6 (+55 unreachable) | 32 | 29 |
| ES 1m 24h, midnight days | 11 | 53 | 6 | 5 (+53 unreachable) | 14 | 8 |
| ES 1m 24h, 18:00 ET sessions | 11 | 53 | 8 | 3 (+53 unreachable) | 18 | 10 |

The groups' own run windows give consistent figures:
- **Triage window 2010-06 to 2025-06 (61 switches):** NQ 5m RTH 16 caught / 45 missed / 32 false flags; ES 13 / 48 / 31.
- **Windows to 2026-07/08 (65 switches, including June 2026):** NQ 20 / 45 / 32; ES 17 / 48 / 31. On RTH masters the June 2026 switch falls between the 06-12 and 06-15 sessions, so the house detector's 06-15 flag lands on the right day (2.7).
- **2022 onward, when the carry is large:** it still misses 7 of 17 NQ switches: 2022-03-14, 2022-09-12, 2022-12-12, 2023-03-13, 2024-03-11, 2024-09-16 and 2025-03-18.

### 2.3 Why news gaps beat the carry

- **Before 2022 the carry was too small to see.** The mean |offset| in 2010-21 was about 9.5 points on NQ and 6 on ES. That is under the 15-point floor and smaller than routine overnight gaps, so in each window either a news gap wins or nothing is flagged.
- **From 2022 the carry is large, but it is mixed with the real overnight move.** The mean |offset| in 2022-26 is about 182 points on NQ and 45 on ES. The gap on a switch night is carry plus real move, and the two often partly cancel.
  - Example: on 2024-03-11 the carry was +248.75, but the observed gap was only +184 because the market fell 64.75 overnight.
  - A bigger news gap in the same window then wins: 2024-03-18 (+225), Fed day 2024-09-19 (+468.5, beating the 2024-09-16 switch), and 2025-03-10 (beating 2025-03-17).
- **False flags remove the best news-gap days.** Because the detector picks the largest gap, each false flag deletes the quarter's biggest news-gap day. For gap strategies (GAPGO) those are their best days. For position holders, the flagged gap is effectively the trade's own outcome, which is a small piece of foresight.
- **It is blind for the first 60 sessions of any window loaded on its own.** The 60-session median baseline does not exist yet, so a cold lockbox or walk-forward fold never sees its first roll.
  - TTIBS #300's lockbox missed the Sep 2025 switch, and one trade booked +$4,745 from it.
  - RSIDIV #163's lockbox missed the same switch (+$18,980).

### 2.4 The 24-hour case

- **Where the switch sits.** On the unadjusted 24-hour masters, the vendor switches contracts at 00:00 UTC: 19:00 ET in summer, 20:00 ET in winter. That is inside the 18:00 ET session for 55 of 64 NQ switches and 53 of 64 ES switches. Only switches at a Sunday 18:00 reopen fall on a day boundary.
- **Why the detector cannot see them.** The engine's `day_id` is the ET calendar (midnight) date on every master. The detector only compares one day's open with the prior day's close, so a jump in the middle of a "day" is invisible. What it flags instead are weekend and Monday news gaps. On r32's midnight-day feed, all 23 flags were Sundays.
- **A day-level guard is not enough on 24-hour data**, even with the correct switch days. A position opened on the morning of the switch day still rides through the 19:00/20:00 ET switch. A safe guard must work bar by bar: go flat on the last old-contract bar and block fills until the first new-contract bar.
- **At an in-bar splice even that is not enough.** The bar holds both contracts, so its high and low are not tradable prices. It must be rebuilt, flagged and kept out of fills (6.2).
- **RTH masters.**
  - All 64 raw switches per root fall between sessions: the last close before the seam equals the old contract's 15:59 close, and the seam-day open equals the new contract's 09:30 open. A day-level rule is correct there.
  - The June 2026 switch also falls between RTH sessions.
  - **The September 2026 switch does not.** It sits inside the 09-14 11:30 ET bar on RTH and 24-hour masters alike (2.7).

### 2.5 How much fake P&L a missed switch books

- **The mechanism.** A position held across a switch books side × contract offset, at $20/pt on NQ and $50/pt on ES.
- **NQ.** Offsets in 2022-26 are large and positive, e.g. +296.5 on 2024-12-16. In 2022-25 they ranged from about +76 to +297 points, roughly $1.5k-$6k per NQ contract. So long holders book fake gains and shorts book fake losses.
- **ES.** Offsets in 2022-26 are +18 to +65 points. Early-era ES offsets were negative, so a long ES holder booked fake losses then. DIP on ES #425 booked -$9,686 on 75 missed crossings.

### 2.6 Ground truth and helper caveats

- **The switch table matches the masters.** (V)
  - All 64 switches per root land on an exact master bar.
  - The RTH masters carry the same stitch as the 24-hour master: 99.98% of NQ bars and 100% of ES bars are identical, and the bars on either side of every switch match.
  - After Panama back-adjustment, the mean jump at switch bars falls from 59.8 to 6.1 points on NQ and from 18.4 to 2.0 on ES. What remains is real weekend gaps at Sunday-reopen switches, such as 2020-03-15 (+109.5) and 2020-06-14 (-106).
- **The offset definition is the right one.** Each switch's `contract_offset` is new close minus old close at the last common minute before the switch. At the 19:00/20:00 ET switches it matches the unadjusted master's own one-bar jump to within 0.40 points on NQ (n=55) and 0.12 on ES (n=53). (V; see 5.4 for why the registered twins differ.)
- **The raw Databento files end on 2026-06-05.** The two `inferred_after_raw_end` rows in switches_*.csv are wrong: the June row has the wrong time, and the September row is a weekend gap. See 2.7.
- **Helper caveats.**
  - `RL.true_detector` returned the Friday for a Thursday 19:00/20:00 switch on midnight-day 24-hour data. The critic confirmed this in the code, and it was **fixed in rollaudit_lib on 2026-09-25**. The section-5 figures that used the old helper on midnight-day 24-hour data predate the fix and were not re-run; all of them are closed research.
  - RL's between-days mapping would mis-map a Sunday switch that falls before a Monday holiday. No such case exists in the data.
  - `RL.adjusted_arrays` shifts only bars that start before the switch, so it cannot repair a bar that holds both contracts. With a table row at 2026-09-14 11:30, the adjusted bar opens 291.5 points below the prior close and shows a fake -292 low (ES -66.75). Shifting the bar as old-contract instead creates a fake +290 body. (V)
  - `tools/rocfrontier/make_daily.py` stamps days at midnight, which moves the detector's +2-day window edge. For June 2025 it flags 2025-06-20 (a +372 news gap) instead of the real 2025-06-16 switch (+216). NQ: 18 caught / 48 missed / 34 false. ES: 17 / 49 / 34.
  - The SETUPS heuristic (`setup_kit.contract_switch_sessions`, which looks for the largest jump at the 00:00 UTC bar or the session-open bar) catches 37 of 64 NQ and 48 of 64 ES switches. Since 2022 its only material miss is 2026-03-15 (NQ +210.5, ES +49.5).
  - The draft's proposed tail rule used the same idea. It would miss both 2026 splices (0 of 2, V) and pick the real weekend gaps instead (06-14 18:10, 09-13 18:10). In a house-style window it also picks the 2026-03-08 weekend gap (-226) over the true 2026-03-15 switch. On the material-carry quarters of 2022-26 it scores 14/16 on NQ and 14/16 on ES (M).

### 2.7 The data tail after 2026-06-05 (round 2)

The draft's picture of the tail was wrong and is replaced here. It said the June switch was inferred at 06-14 18:10, the 09-13 switch was untrusted, the jumps at 06-08, 08-06 and 09-08 were unexplained, and every lockbox carried "$4-12k of roll uncertainty".

**Who built the tail (M/I).**
- **To 2026-06-05 16:59:** `tools/stitch_noadj.py` from databento_raw, with a volume-based roll rule.
- **From 06-07/06-08:** Yahoo NQ=F / ES=F.
  - Written by `optimizer.auto_refresh_masters` (run from `api/augur_refresh.py`). Autorefresh is on for all 8 db_noadj 1m/5m masters and the twins; it pulls 7 days and Yahoo wins overlaps.
  - Also by `tools/refresh_noadj_yahoo.py`, which reaches back 60 days on 5m and 7 days on 1m.
  - Prices match the NT capture on 80-99% of minutes, but volumes only 18-92%, so the tail is not built from the capture.
  - The `yahoo` source label marks only the latest 7-day overwrite; it is not a provenance boundary.
  - The Yahoo attribution for 09-14 is inferred: the rows are labelled `existing`, and runner.log lacks that day's refresh lines because of encoding errors.
- **Exception: NQ 1m and 5m RTH for 07-01..07-16** are exact aggregates of the NT capture (100% of OHLCV, V). The writer is unidentified but ran on 2026-07-17 (dated by `.bak-20260717` files).
- **Other RTH masters.** 30m and 60m RTH were resampled from 5m RTH on 2026-08-23 and end 06-30. 15m RTH is a Yahoo refresh to 06-30. 2m RTH was resampled from 1m on 08-05 and ends 07-16.
- **NT 10s masters** (`master_b1335b7e` NQ, `master_c279374a` ES) come from the chart indicator (EdgeLogOHLCExport writes `C:\EdgeLog\ohlc`, imported by `tools/import_nt_ohlc.py`). The NT add-on writes a different file, `C:\EdgeLog\ohlc_addon`.
- `master_b3bf23b6` (NQ 1m, built from the NT capture, 06-23 to 08-13) has no June or September switch (M).

**Events in the tail** (1m 24-hour masters unless noted; the "Roll?" column says whether the event is a contract switch)

| When (ET) | Masters | What it is | Size NQ / ES | Roll? | Status |
|---|---|---|---|---|---|
| 06-05 16:59 → 06-08 00:00 | 1m 24h | Databento-to-Yahoo hand-off; the Sunday 06-07 evening session is missing (the 5m 24h master has it) | +383.25 / +48.75 | No (June contract on both sides) | V |
| 06-05 15:59 → 06-08 09:30 | RTH | Same hand-off; a real weekend move | real move | No | V |
| 06-14 18:10 | 24h | Real June-contract weekend gap; 18:00-18:09 missing; the 18:10 bars have volume 0 | +412.00 / +65.25 | No | V |
| **06-15 03:30 (NQ), 05:30 (ES)** | 1m and 5m 24h | **In-bar splice, June → Sep.** NQ bar O 30,252.00 / H 30,546.50 / L 30,242.50 / C 30,545.75, volume 13,914 against an hourly median of 76. ES bar 7,521.50 → 7,586.50, volume 3,323 against 306. 5m bodies +311.00 / +63.00 | offset ≈ +293 / ≈ +64 | **Yes** | V |
| **06-12 15:59 → 06-15 09:30** | Every RTH master (1m, 5m, 30m, 2m, 15m, 60m, TV twins) | **Clean switch between sessions** | gap +982.75 (≈ +293 carry + ≈ +690 real) / +165.5 (≈ +64 + ≈ +101.5) | **Yes** | V |
| 06-18 23:58 → 06-21 18:00 | 1m 24h | Juneteenth; all of 06-19 missing | +70.50 / +6.50 | No | V |
| 06-30 10:49 → 08-06 00:09 | 1m 24h, NQ and ES | 37-day hole (877.3 h) | -780.75 / +237.75 | No | V |
| 07-16 15:59 → 08-06 09:30 | NQ 1m RTH | Hole (07-01..07-16 patched from the NT capture) | +121.25 | No | V |
| 06-30 10:49 → 08-06 09:30 | ES 1m RTH | Hole | +226.50 | No | V |
| n/a | Unadjusted 5m (24h and RTH) | **No July hole.** Back-filled; the splice thread credits Yahoo's 60-day 5m reach, while the house-infra thread found the rows equal the NT capture. The writer is not settled | n/a | n/a | V (no hole) |
| 06-30 → 08-05 | All four registered 5m twins | Hole: adc172d2 -797.5, 1a196c0f +235.0, 00c66966 -1,029.0, a85a0438 +223.75 | n/a | No | M |
| 07-02 23:55 → 07-05 18:00 | 5m 24h | July 3 holiday gap (the capture has no data 07-02 17:00 → 07-05 18:00 either) | +162.25 / +8.00 | No | M |
| 07-28 01:15 | NQ 5m 24h | Bad Yahoo bar: O = H = 28,190 against the capture's 27,947.5; the 01:10 bar is missing | spurious ≈ +242 | No | M |
| 09-04 16:59 → 09-08 00:00 | 1m and 5m 24h | Labor Day session and Monday-evening reopen missing; the move is real | +177.50 / +0.50 | No | V |
| 09-11 → 09-13 18:10 | 24h | Real Sep-contract weekend gap (the "inferred 09-13 18:10" row). The capture shows -394.0 / -51.5 over the same weekend | -384.50 / -50.00 | No | V |
| **09-14 11:30** | **Every Yahoo-fed NQ/ES 1m and 5m master, 24h and RTH, plus the four twins (16 masters)** | **In-bar splice, Sep → Dec.** NQ 1m O 29,077.00 / H 29,383.50 / L 29,076.00 / C 29,381.50, volume 8,361 (+304.5). NQ 5m close 29,454.50 (+377.5 body). ES 1m +68.75. ES 5m close 7,691.50 (+79.5) | offset ≈ +295 / ≈ +67.75 | **Yes** | V |
| 09-15 16:00:40 → 16:00:50 | NT 10s capture masters (chart indicator) | Clean switch | +292.5 / +67.0 | Yes | V |
| 09-15 09:16:50 → 09:18:10 | ES 10s capture | 9 back-filled rows on the Dec contract | +68.0 then -68.0 | Excursion | V |
| 09-10 13:28:00 → 13:28:20 | NT add-on file (read by paper) | Switch at the capture restart after an outage | NQ +289.5; ES +65.75 inside the 13:28:00 row | Yes | V (NQ), M (ES) |

**Offsets (V).**
- **June 2026:** NQ ≈ **+293** (288-300); ES ≈ **+64** (61-66). Sources:
  - the raw June-to-Sep contract spread on 06-01..06-05 (+0.967% NQ, +0.826% ES);
  - the one-step daily futures/ETF ratio change (+0.951% NQ/QQQ, +0.861% ES/SPY);
  - the NQ/ES minute-ratio steps (+0.98% at 03:30 with ES flat, -0.87% at 05:30 with NQ flat).
  - The daily ratio proves there is exactly one step. The minute data proves the timing. The house-infra thread's independent estimates (+298 ± 5, +65.5 ± 1) overlap.
- **September 2026:** NQ ≈ **+295** (median of master minus capture, n=1,630; p5 288.0, p95 300.25). It drifts from about 300 on the afternoon of 09-14 to 288-290 on 09-15. ES ≈ **+67.75** (66.5-68.25).

**Historical switch timing (M).** All 128 raw switches came 4-8 days before the third-Friday expiry, always between 18:00 and 20:02 ET. The 2026 splices are also 4 days before expiry, but at times no historical switch used. The Yahoo tail rolls mid-session on the Monday of expiry week.

**Which saved runs are touched.**
- 281 runs end after 2026-06-05; the latest date_to is 2026-08-24, so **no saved run reaches the September splice** (V).
- Classification (M):
  - 13 early ORB CSV runs end 06-08..06-11. They contain only the change of data feed, no switch (count V).
  - 14 runs are ETF-only.
  - The other **254 contain the June switch in both the whole window and the 12-month lockbox**:
    - 27 ENGU-Q runs on 1m 24-hour masters, and 36 books through an ENGU-Q 1m 24-hour leg (including starred #366 and #396/#397), take it as the in-bar splice.
    - 169 runs and 5 books use RTH masters only. For them the switch falls between sessions, and only trades held from 06-12 to 06-15 book it. Intraday ORB, NOISE and TTM see it only through indicators that read the gap.
  - #295 (ES 1m 24h to 08-24), #345 and #360 (NQ 1m RTH to 08-12) also cross the July hole.
  - 17 July-era runs (the rest of the 254) have an unknown session: #125, 136, 137, 143, 144, 146, 148, 149, 152, 156, 157, 158, 162, 163, 169, 170, 216.

---

## 3. Per family

### 3.1 Overview

| Family (files) | Feed / masters actually run on | Roll handling | Holds across a switch? | Exposure | Effect on crowned / starred / book / paper runs |
|---|---|---|---|---|---|
| **ENGU-Q 24h** (ENGUQ_1M_ETH_R2, ER, ER25, FROZEN, 1_0, LIM, LIM50, LIM20, REG5, ER_RYR, ERW, NBO, TRAIL, COOLDOWN, CD5, R3, R4, R5, SEL, …) | NQ/ES 1m **24h** db_noadj_eth | **None.** No detector; `day_id` is ignored | Yes. Long only, no end-of-day flat (#335 leg: median 5.5 h, 24% multi-day, longest 142.7 days) | **Material** | #335, #370, #226, #309, #265, #249 and every ENGU-Q book leg lose 10-22%. The June 2026 in-bar splice adds about -$5.9k per NQ crossing (3.2) |
| **ENGU-Q RTH** (ENGUQ_1M_1_0, 149F, CTX, ALT, ENS, 5M) | NQ/ES 1m/2m/5m RTH db_noadj_rth | None | Yes. Held overnight, so every switch night is crossed | **Material** | #227 (evidence for QQQ ENGUQ_149; leg of books #261/#262/#318) -23% (3.2) |
| **TTM** (TTMSQZ_3_0_ES30SSOF2 #369, SS20 #353, SSO #368, SSF2 #364, SS #352, ES30N #299, ES30T #340) | ES 30m RTH db_noadj_rth | None. Flat by the close, but the squeeze, ATR, hourly gate and open-bar tilt all read across the roll gap | No (0 of 354 trades cross a day) | **Material** (signals) | #369 -10.6%, #353 -9.1%. Lockboxes and folds unchanged (3.3) |
| **NOISE** (NOISE_1_0 core; #382, #304, #243, #422) | NQ 5m RTH db_noadj_rth | None. The prior close in the bands reads across sessions | No | Low in backtests; an in-session splice contaminates the bands for 40-44 sessions (4.5) | About ±1%. Lockboxes, drawdowns and folds unchanged (3.4) |
| **ORB** (all ORB_* incl. #314, #257, #239, #234, #297) | NQ 5m RTH db_noadj_rth | None needed between sessions | No | **None in backtests**; an in-session splice reaches its volatility filter | Trade lists bit-identical on back-adjusted data (V). The 09-14 splice enabled 09-16 paper losers (4.5) |
| **TTIBS** 1.0-1.3 | NQ 5m RTH db_noadj_rth (#162 on the back-adjusted tv twin) | House detector: go flat the day before a flagged seam and block fills there | Yes. Every #300 trade is held overnight (median 2 sessions) | Material (book leg #419), no flip | #300 lockbox $25,359 → $16,499 (back-adjusted $23,325). #162's twin carries a stale offset (5.4). TTIBS is closed (3.5) |
| **DIP** (NQDIP_1_0, NQDIP_1_1) | NQ/ES 5m RTH db_noadj_rth; QQQ runs on yahoo_adj (no detector) | House detector, **plus the whole seam-night gap is dropped** | Yes. Multi-day longs, no stop | **Material** (drawdowns) | #425 and #307 drawdowns 23-29% too small; FAIL runs #315/#400/#401 too. Verdicts hold (3.6) |
| **GAPGO** (GAPGO_1_0, GAPGO_TRAVEL_1_0, GAPFADE_1_0) | NQ 5m RTH db_noadj_rth | Detector gates entries; a missed switch flips the gap's sign | No (intraday) | Low | #330/#399/#329 FAILs stand (M) |
| **RSIDIV** (RSIDIV_1_0) | NQ/ES RTH db_noadj_rth only | House detector | Yes (days to months) | Low | #163 FAIL cannot flip (M) |
| **SUPERTREND** 3.0 | NQ/ES 1m/5m RTH (r13 triage only) | House detector | Yes (always in the market, 46% of trades overnight) | Low | No saved run. Dead 0/24 (M) |
| **MISC round-13 ports** (BBRSI, GOLDX, FLAWLESS, AOSTOCH, EMAX, HULL, ICHIHULL, MACD200, MACDRSI, PMAX) + ONDRIFT | NQ/ES 1m/5m RTH (r13 triage/deeptune) | House detector | Mostly yes | Low | No saved runs. All dead (M) |
| **MISC rounds 16-18** (r16/r17/r18/r18b harness cells) | NQ 5m RTH (r18b stops on NQ 1m 24h) | Unwindowed variant (2.1) plus whole-gap deletion | Yes (r17, r18) | Research only | 0/30, 0/16 and the ONDRIFT retraction stand; B7 figures and the r18b stop finding are wrong (5.2) |
| **CBU-Q / SETUPS** (CBUQ_1M_1_0 etc. on setup_kit) | NQ 1m 24h db_noadj_eth | setup_kit heuristic blanks the prior-day level | No (inside RTH) | Low | #427 FAIL; the crowned config reads no cross-switch price |
| **OVERNIGHT**, ENGU-Q short mirror (ENGUDQ, untracked file), **RFML** (GAINZ_RF), legacy **ENGU** | RTH / 24h, no saved db_noadj verdict runs | None | Yes | Low | Already dead; correcting cannot flip them (M; see 3.8 for a sign fix) |
| VWAP, REVERT, EMAPB, DRIVE, ORB_FADE | RTH / CSV | Flat by the close (defaults) | No | Low | No verdicts at stake |
| ETFDIP, quarantined SUPERTREND 1/2, ENGU_1_2_1, REPLAY | ETF yahoo_adj / none | n/a | n/a | None | n/a |

### 3.2 ENGU-Q

**Mechanism.** The ENGU-Q files have no roll handling at all, so a switch reaches the results in three ways.
- **Booked offset.** A position open across a switch books the contract offset. Its trail and breakeven also ratchet off the jumped high, and the gap-honest stop fills at the jumped open.
- **Stale entry filters.** For 1-3 days after an upward roll, the regime SMA (regime_len × 390 bars), the EMA and the trendline still hold old-contract prices, so extra longs get through.
  - Example: the #335 entry at 2023-03-13 11:03, just after the +122.75-point switch. Its signal-bar close sat 29 points above the regime average on raw data, but 65 points below it on corrected data.
  - It was a real hold to 2023-08-03 worth $65,121 (and itself crossed the June 2023 switch).
  - The corrected run replaces it and a -$2,286 trade in the same between-switch window ($62,835 for the two) with 52 smaller trades worth $11,677, a delta of -$51,158.
  - So the #335 leg's -$104,226 is $38,985 of booked offset plus about $65k of changed trades, and that one entry's window accounts for about $47.6k of the second part: the -$51,158 delta less the $3,565 of booked offset already counted in the $38,985. The draft's phrase "fake breakout entries" overstated this.
- **Fake stops at an in-bar splice (round 2, V).** `ENGUQ_1M_ETH_R5_1_0.py:272-282` raises the trailing stop from the bar's high before checking the low, and fills at the open when the open is below the stop.
  - On the June 2026 splice bar, #381's long had its trail lifted by the bar's Dec-contract high (30,546.5). It was then "stopped" at the bar's June-contract open (30,252.000), a price at which no such stop could have filled.
  - Repaired, the trade holds to 06-16 10:19.
  - Any trailing-stop long open across the 09-14 11:30 bar is exposed to the same effect.

**Why back-adjusting is a valid fix here, and how far it was tested.** ENGU-Q reads only price differences and levels relative to its own history, so a constant shift should not change its trades.
- Over the full 2010-06 to 2026-06 window, shifts of +5,000, -1,000 and +3,144.25 (the cumulative offset) give identical trades for the #335 leg (R2 file defaults) and for #370 (M, harness-misc).
- A +5,000 shift over the same full window also leaves TTM #369/#353 and ORB #297/#234 unchanged (M, book_impact).
- The verifier's check across the other ENGU-Q files used a +3,144.25 shift over 2021-01..2026-06 only, one run per distinct file, with champion or best params only (V for that scope).
- The draft's "all 24 ENGU-Q files, +5000" overstated this. Test 10 in 6.8 closes the gap.

| Run (role) | Before | After (back-adjusted; June 2026 not adjusted) | Booked offset | Status |
|---|---|---|---|---|
| **#335 book/paper leg**: R2 file defaults, cost 0.783. This is the ENGU-Q leg of #366/#396/#397/#339/#365/#373/#375/#378/#379 and the NT8/shadow ENGUQ_335 evidence | 1,949 tr / $603,381 / PF 1.694 / DD $41,889. Opt $515,590. LB (by entry) 118 tr / $87,790 | 2,053 tr / $499,155 / PF 1.534 / DD $44,205. Opt $418,426. LB 116 tr / $80,729 (est. ~$76,139: SUPERSEDED, see the June table) | 36 tr / $38,985 ($34,240 before the LB, $4,745 inside) | V |
| **#335 validate champion** (starred crown run; paper ENGUQ_335_VC), cost 0.533 | Whole 1,344 tr / $541,330 / PF 1.820 / DD $66,569. IS 870 tr / $281,131 / PF 2.261. Cold LB 129 tr / $58,163 / PF 1.531 / DD $47,779 | Whole 1,387 tr / $476,435 / PF 1.699 / DD $70,817. IS 874 / $277,828 / PF 2.234. Cold LB 148 / $43,468 / PF 1.366 / DD $57,729. The June est. ($38,878-$39,258, and the $35,228 "whole +412 is carry" bound) is SUPERSEDED; the +412 is a real weekend gap. Cold LB to be recomputed | 46 tr / $51,600 | V |
| **#370** ENGU-Q on ES, PASS, cost 0.4 | 681 tr / $381,313 / PF 2.459 / DD $13,402. Cold LB 67 / $25,372 / PF 1.614. LB by entry 16 tr / $34,960 | 747 tr / $341,487 / PF 2.187 / DD $15,444. Cold LB 69 / $17,261 / PF 1.406 (June est. $10,436 SUPERSEDED; to be recomputed). LB by entry $34,960 is unchanged by back-adjusting; with the June splice repaired it is **$28,136** (V, round 2; equal to the draft's est.) | 35 tr / $24,862, all before the LB | V |
| #377 (same ES cell, cost 0.6), WEAK | $374,503. Cold LB $24,702 / PF 1.591 | $334,017. Cold LB $16,571 / PF 1.385 (June est. $9,726 SUPERSEDED) | 35 tr / $24,862 | M |
| **#226** starred former crown (FROZEN), documented control | Run (0.533) $434,721 / PF 1.332; cold LB $90,338. Book leg (0.783) 2,843 tr / $420,506 | Run $343,583 / PF 1.250; cold LB $76,451 (est. $72,241 SUPERSEDED). Book leg $328,888 | 45 tr / $47,050 | M (book-leg before V) |
| **#309** (paper control ENGUQ_309) | $591,267 / PF 1.655 / DD $48,900. Cold LB $82,448 | $494,275 / PF 1.515 / DD $51,299. Cold LB $75,304 (est. $71,094 SUPERSEDED) | 36 tr / $43,865 | M |
| **#265** (paper ENGUQ_ER / ENGUQ_ER_H) | $486,053 / PF 1.596. Cold LB $135,983 | $418,006 / PF 1.495. Cold LB $113,468 (est. $109,258 SUPERSEDED) | 34 tr / $35,625 | M |
| **#249** (paper ENGUQ_L50) | $513,014 / PF 1.401. Cold LB $112,088 | $407,010 / PF 1.300. Cold LB $84,142 (est. $79,932 SUPERSEDED) | 44 tr / $47,155 | M |
| **#227** (149F; QQQ Webull ENGUQ_149 evidence; RTH leg of #261/#262/#318) | Run $453,532 / PF 1.385 / DD $65,635. Cold LB $66,262 / PF 1.313. Book leg 2,048 tr / $477,521 | Run $350,542 / PF 1.275 / DD $87,683. Cold LB $59,278 / PF 1.281 (est. $55,068 used offset 210.5 against about 293: SUPERSEDED). Book leg $374,531 | 44 tr / $38,095 | V |
| #384 (WEAK, archived) | $596,112 | $542,164 | $47,290 | M |
| #198 (PASS; its as-run file predates commit 6da54db) | $657,334 / PF 2.242. Cold LB $53,792 | $514,401 / PF 1.893. Cold LB $36,382 | 43 tr / $59,815 | V. The -$142,933 is mostly **one** open trade (2025-04-07 entry marked at the window end: $255,974 raw vs $97,479 adjusted) |
| Other research runs: #310, #248, #326, #320, #328, #235, #247, #283, #286, #380, #402, #376/#383, #381, #182/#183/#188, #223, #224, #232, #196, #190 | See `work\enguq\impact2\results.json` | Net falls 4-22%. Every cold LB keeps its sign | 20-58 tr / $22k-$63k each | M |

**June 2026 splice repaired alone (round 2).** The June bars are repaired at their real time (06-15 03:30 NQ / 05:30 ES) at +293 / +64, on the raw runs. Bars before the splice are shifted by the offset; in the splice bar only the open and low are shifted.

| Run | Raw before | June repair | Status |
|---|---|---|---|
| #335 leg (R2 defaults, 0.783) | 1,949 tr / $603,380.51. LB by entry 118 / $87,790.16 | **-$5,860** on both: $597,520.51 / $81,930.16. Range -$5,760 (+288) to -$6,000 (+300) | V |
| #335 champion (0.533) | 1,344 tr / $541,329.56. Whole-run LB by entry $49,811.93 | -$5,860, so LB by entry $43,951.93. Cold LB to be recomputed | V |
| #370 (ES) | 681 tr / $381,313. LB by entry $34,960.04 | **-$6,824.36** (offset $3,150 plus about $3,675 from 4 changed trades; the same at offsets 61-66). LB by entry $28,135.68 | V |
| #377 (ES) | $374,503 | -$6,844.36 | V |
| #381 (FAIL) | 2,550 tr / $417,511.44. LB by entry 190 / -$23,312.59 | **+$6,305.14** (2,546 tr). LB by entry -$17,007.46. FAIL stands. The raw run's crosser was the fake stop-out described above | V |
| 17 other NQ crossers (#226, 235, 247, 248, 249, 265, 283, 284, 286, 309, 326, 328, 376, 380, 383, 384, 402) | n/a | About -$5,840 each at +292, on whole and LB by entry (-$5,720 to -$6,000 across +286..+300) | M |
| #198 / #310 / #313 | n/a | -$2,886 (a change of trades) / whole -$5,840, LB $0 / whole -$11,192 | M |
| #320 / #407 | n/a | +$10 / $0 (they enter at 06-15 07:13 / 07:26, after the splice) | M |
| #295 (ES, WEAK, leg of #312) | n/a | Whole -$3,150. Its 2025-04-07 to 2026-08-24 trade also spans the July hole, which is not repaired | M |

- These deltas are measured on the raw runs. Adding them to the back-adjusted figures above was not tested, so combined figures are **to be recomputed**. The exception is #370's LB by entry, which back-adjusting does not change, so $28,136 stands.
- No run has an entry between 06-14 18:10 and 06-15 03:30. The draft's crosser test therefore picked the right trades for every ENGU-Q run except #381 (M).

**Other ENGU-Q notes:**
- **The leg-parameter trap.** The books' "ENGU-Q 335" leg is ENGUQ_1M_ETH_R2_1_0.py on the file's `DEFAULT_PARAMS` (1,949 trades), not #335's saved best_params (1,344 trades at 0.533). Passing *empty* params silently falls back to the function's internal defaults instead, which is #226's cell (2,843 trades / $420,506.12). That is what happened in #417/#418/#419 (see 4.4).
- **The July-era RTH validates (#143-#158) cannot be reproduced.** Trade counts match, but their saved P&L predates the 2026-07-12 gap-honest stop change. The after-figures above for those runs are computed on today's file.

### 3.3 TTM

**Mechanism.** TTM is flat by every close, so it never books an offset. But its squeeze, ATR, momentum, hourly gate and open-bar tilt all roll across sessions.
- On the day after a switch, the carry looks like an opening gap. It can trigger a fake squeeze fire that the open-bar tilt then sizes up.
- All 19 trades that differ between raw and adjusted data start 0-2 business days after a true switch (up to 4.7 calendar days).
- The largest removed trades are roll-day longs: 2022-12-12 +$1,769, 2023-09-11 +$1,098 and 2024-06-17 +$5,837.
- One losing short appears on the adjusted data: 2020-03-17, -$2,468 per unit. It appears for any 2020-03 ES offset from -8 to -33.25 (the true offset is -12.0), so it is not a rounding artifact.

| Run (role) | Before | After (back-adjusted ES 30m) | Status |
|---|---|---|---|
| **#369** (book leg ×3 of #396/#397/#371/#378/#379/#417/#419; paper TTM_299_SSOF2) | 354 tr / $135,884 / PF 3.117 / DD $4,634 / MAR 1.83. Opt 339 / $113,146. Cold LB 15 / $22,885 / PF 9.94. Folds 7/8 | 355 / $121,491 / PF 2.789 / DD $5,300 / MAR 1.43. Opt 340 / $98,753. **LB unchanged.** Folds 7/8 | V |
| **#353** (leg ×3 of adopted #366, #361, #365, #373, #375, #418; paper TTM_299_SS / SSL) | 357 / $101,017 / PF 2.907 / DD $4,338 / MAR 1.45. Cold LB 15 / $17,098 | 358 / $91,810 / PF 2.651 / DD $4,982 / MAR 1.15. **LB unchanged.** Folds 7/8 | V |
| #368, #364 (PASS parents) | Opt $113,723 / $84,344 | Opt $101,882 / $73,156. LB and folds unchanged | M |
| #352, #299 (= #289), #340 (older legs; paper TTM_299 / TTM_299_T) | $109,651 / $51,709 / $69,884 | $101,914 (cold LB $22,025 → $20,832, still PF 2.64) / $44,995 / $62,026 | M |
| **Book leg effect** | #369 ×3 $407,653; #353 ×3 $303,050 | $364,473 (-$43,180, V); $275,430 (-$27,620, M) | |

- **Ranking.** #369 still beats #368 on MAR (1.43 vs 1.31).
- **Pre-registered drawdown caps** still pass when corrected figures are compared with corrected figures. #368's corrected $5,913 drawdown would fail only against the *uncorrected* leg drawdown.
- **June 2026.** The ES 30m RTH master sees the June switch between sessions (+165.5 gap, about +64 of it carry). A check at the superseded +54.4 changed no TTM trade (M). It was not re-checked at +64.

### 3.4 NOISE and ORB

**NOISE.** It is flat by every close, and the only cross-session price it reads is the prior close in its bands. The bands are percent-of-price, so NOISE is **not** shift-invariant: a +5,000 shift changes the P&L of 157 trades of #304, removes 320, adds 334 and moves net from $405,980 to $386,481; back-adjusted data is not a valid test for it.
- It was measured instead with a 2-line scratch patch that adds the true offset to the prior close on the 64 post-switch sessions. An unpatched copy of the patch gives identical trades.
- Round 2 confirmed on the live chain that a Panama back-adjust is the wrong fix for NOISE. It changes 16 years of band history and anything trained on it. A forward adjustment (or the prior-close fix) is right (V; 4.5).

| Run | Before | After | Status |
|---|---|---|---|
| **#382** (Webull paper = #304 re-sized) | 4,825 tr / $604,706 / PF 1.392 / DD $28,203. Cold LB 239 / $79,939 | $603,284 with the prior-close fix; $611,338 / PF 1.396 once the squeeze tilt is also computed on adjusted bars. DD and LB unchanged; folds 8/8 | M (method V) |
| **#304** (book leg of #366/#396/#397) | $413,255 / PF 1.368 | $410,380. LB unchanged. Book leg to 2026-06-30: $405,980 → $403,106 (V) | M / V |
| **#243** (starred) | $380,745 | $376,560. LB unchanged. Selection-stretch DD $18,425 → $18,745 (whole-run DD unchanged) | M |
| #422 | $538,787 | $538,162. Selection DD $17,616 → $19,255 with the prior-close fix only, $17,041 with the squeeze fix | M |
| 40 NOISE lockboxes (#202-#420) | 38 of 40 reproduce exactly | Only #202/#203 (-$2.7k) and #405 (-$5.0k) move. All stay positive with PF > 1 | M |

- **June 2026.** The prior-close fix covered the 64 raw switches only. The June 2026 gap (NQ +982.75 at 06-15 09:30, about +293 of it carry) is uncorrected in every NOISE run and lockbox that contains it. The draft's June check used 229.5 and is SUPERSEDED; to be recomputed at +293.
- NOISE #345 and #360 (PASS, NQ 1m RTH to 2026-08-12) also cross the capture patch and the 07-16 → 08-06 hole. Not re-run.

**ORB crowns.** #314 (2,299 tr / $397,150), #257 (2,751 / $416,382), #239 (2,607 / $394,864), #234 and #297 give bit-identical trade lists on back-adjusted data, so they are immune to rolls between sessions (V).
- They are **not** immune to a splice inside a session. ORB's volatility filter reads the 5-session average range. The 09-14 bar raised that session's range from 430.75 to 725.75, which let losing 09-16 trades through on ORB, ORB_R6 and its clones (V; 4.5.4). The effect lasts about 5 sessions.

### 3.5 TTIBS (closed 2026-09-24)

All TTIBS runs were on NQ 5m RTH, except #162, which ran on the back-adjusted tv twin. The detector caught 20 of 65 switches on the #300 window, with 32 false flags.

| Run | Before | After (true switch days) | Status |
|---|---|---|---|
| **#300** (PASS 6/6; BOOK #419 leg) | Whole 707 / $393,623 / PF 1.516 / DD $55,435. Cold LB 39 / $25,359 / PF 1.191 | 703 / $385,776 / PF 1.501 / DD $55,435. Cold LB 39 / $16,499 / PF 1.124; back-adjusted 38 / $23,325 / PF 1.208 | V |
| **BOOK #419** | 10,902 tr / $1,973,282 / PF 1.437 / DD $77,832. LB $348,243 | $1,965,435 / PF 1.435 / DD $72,104. LB unchanged. 8/8 | V |
| #291 (FAIL) | Cold LB -$47,905 | Unchanged (FAIL stands) | V |
| #201 and other TTIBS_1_0 runs (void: look-ahead close fill) | #201 $419,288 | $409,288. All cold lockboxes identical | V (#201, #167, #169) |

- **Where #300's movement comes from.** 28 house-detector trades booked $10,815 of offset, mostly Dec 2022, Mar 2023 and Mar 2024. The lockbox drops by $8,860 ($25,359 → $16,499). Only $4,745 of that is the Sep 2025 offset, carried by one trade (2025-09-10 to 09-15) across the switch the detector missed because of its 60-session blind spot. About $4,115 comes from the true-day guard forcing an exit before a real 09-12 → 09-15 move. Back-adjusted with no guard the lockbox is $23,325, a drop of only $2,034, so the $16,499 overstates the roll's effect on #300.
- **#300 and 2026 (contradiction resolved).** The draft said both that no #300 trade crosses the June switch (4.2) and that a 2026-06-05 → 06-11 trade (+$6,179) crosses the end of the raw data (here). Both are true.
  - That trade crosses the change of data feed from Databento to Yahoo. The master is on the June contract on both sides, so no switch is involved (V, 2.7).
  - The June switch on the RTH master falls between 06-12 15:59 and 06-15 09:30. Both detectors flag 06-15, and no #300 trade is open across it.
- **#162** ran on the tv twin, which uses a stale offset definition: on average +$248 of fake P&L per NQ crossing since 2022 (5.4). It still carries that roll residue. Not re-run.
- **Not re-run:** TTIBS_1_0 PASS runs #161, #164 and #165 (void anyway, look-ahead close fill).
- **The closure decision stands.** But the closure numbers in BACKTESTING_STACK.md (2026-09-24) come from #419, which ran four legs with no parameters (see 4.4; its TTM defaults reproduce #369, so only the ORB, ENGU-Q and NOISE legs differ). Rebuilt with #396's real legs (V):
  - Adding TTIBS #300 raises pre-lockbox net from $1,483,223 to $1,858,429.
  - Drawdown rises from $36,562 to $68,852 (+88%), and lockbox drawdown from $27,506 to $48,074.
  - The roll fix changes only the net (-$7,847).

### 3.6 DIP

**Two separate RTH defects.**
- **(1) Detector errors.** It caught 20 of 65 NQ and 17 of 65 ES switches.
- **(2) The whole seam-night gap is dropped.** The file removes the whole overnight gap on every flagged night, real move included. That hid real Covid losses:
  - ES 2020-03-09: a -208.5-point gap was falsely flagged, erasing $13,344 of loss on #425.
  - NQ 2020-03-16: the switch was correctly caught, but the whole -560.5-point limit-down gap was dropped when the offset was only -12.75. That hid most of $13,801 on #307.

**Versions compared.** A = as shipped. C = true switch days, removing only the offset. D = back-adjusted prices, no detector, re-sized at the real entry price.

| Run | A (before) | C | D | Status |
|---|---|---|---|---|
| **DIP on ES #425** (PASS 6/6, candidate book leg) | 1,026 tr / $366,126 / PF 1.70 / **DD $54,016**. Warm LB 75 / $24,874 / PF 1.90 / DD $11,157 | 1,027 / $376,373 / PF 1.70 / **DD $68,714**. LB 75 / $27,965 / PF 2.13 / DD $8,626 | 1,036 / $380,047* / PF 1.70 / **DD $66,592**. LB 74 / $21,545 / PF 1.82 / DD $10,374 | V |
| **#307** (PASS, DIP-1) | 907 / $479,321 / PF 1.80 / **DD $44,824**. Cold LB 30 / $5,920 / PF 1.24 | 900 / $464,722 / PF 1.75 / **DD $57,970**. LB unchanged | 909 / $488,016 / PF 1.78 / **DD $57,970**. LB $10,436 / PF 1.46 | V |
| **#423** (WEAK, PBO only) | $585,617 / PF 1.81 / DD $36,497. Warm LB 95 / $25,284 / PF 1.56 / DD $12,557 | $580,953 / PF 1.78 / DD $47,505. LB $28,183 / PF 1.64 | $595,865 / PF 1.82 / DD $39,458. LB $24,813 / PF 1.57 / **DD $14,848** | V |
| #424 (NQDIP_1_1, WEAK) | $1,116,128 / DD $116,916. Warm LB 248 / $78,038 | $1,115,782 / DD $102,917. LB $86,735 | $1,119,897 / DD $97,503. LB $81,242 | V |
| #400 (NQDIP_1_0, FAIL) | 1,313 / $506,519 / DD $48,820. Cold LB 100 / $16,152 / PF 1.248 | $514,033 / DD $52,782. LB $18,592 / PF 1.296 | $512,901 / DD $52,397. LB 99 / $10,868 / PF 1.169 | M |
| #401 (NQDIP_1_1, FAIL) | 1,389 / $666,980 / DD $53,925. Cold LB 111 / $26,606 / PF 1.389 | $645,387 / DD $77,381. LB $32,988 / PF 1.527 | $648,766 / DD $74,813. LB 109 / $33,332 / PF 1.584 | M |
| #315 (NQDIP_1_1, FAIL) | 1,501 / $618,762 / DD $44,897. Cold LB 0 trades | $619,942 / DD $54,963. LB 0 trades | $642,823 / DD $54,963. LB 0 trades | M |
| Book DIP leg (#307 params, to 2026-06-30) | 899 / $476,028. Share of the Feb-Mar 2020 worst stretch: -$42,204 | $461,429; -$49,872 | $484,723; -$49,872 | V |

\*A second verifier who also blocks fills on the 2026-06-15 seam gets $380,446. The $399 gap comes from that implementation choice.

- **Net is not the robust effect; drawdown is.** Net moves -3% to +4%, and its sign depends on the method (#307: -$14,599 in C but +$8,695 in D). The drawdown increase is the same in C and D.
- **The FAIL verdicts of #315/#400/#401 were not re-judged.** Their drawdowns rise the same way.
- **Every DIP lockbox touches the post-2026-06-05 feed.**
  - All versions drop the whole June 2026 RTH gap (NQ +982.75 / ES +165.5). Round 2 split it into about +293 / +64 of carry and **about +690 / +101.5 points of real move**, so dropping it deletes a real gain from any long held across 06-12 → 06-15.
  - The DIP group measured the add-back at the superseded offsets (229.5 / 54.4): +$6,223 (#425), +$12,052 (#307), +$6,026 (#423) and +$9,039 (#424).
  - At the round-2 offsets the real move is smaller, so these are to be recomputed.
  - The draft's "in the lockbox's favour" was backwards: the shipped lockboxes are understated by that amount, not flattered.
- `tests/test_dip_open_marks.py` (lines 102-123) is parametrized on NQDIP_1_0 and 1_1 only. An NQDIP_1_2 fork must be *added* to it; the existing test does not have to change (V).

### 3.7 Low-exposure families (group-measured, M)

| Family / run | Before → after (true detector; back-adjusted where shown) | Verdict |
|---|---|---|
| GAPGO #330 / #399 | Selection $205,545 / PF 1.33 → $221,215 / PF 1.357 (adj. $220,299). Lockbox -$39,179 → -$39,179 (adj. -$39,455) | FAIL stands |
| GAPGO TRAVEL #329 | Selection $189,606 → $203,471. Lockbox -$15,923 → -$15,923 (adj. -$13,650) | FAIL stands |
| GAPFADE (no runs) | Moves under $0.5k | Dead |
| RSIDIV #163 | Whole $1,674,559 → $1,527,722 (-8.8%). Lockbox $542,247 → $515,764. ES transfer PF 2.85 → 2.35 | FAIL cannot flip (the sample gate needs 330 IS trades; the corrected full window has 296) |
| SUPERTREND 3.0 | Best cell MAR 4.84 → 4.91 (adj. 4.82) | Dead 0/24 |
| ONDRIFT | MAR 5.24 → 5.47 true detector with a raw-close trend filter (adj. 5.13). Round 2: back-adjusted, no skip 5.09 (V); back-adjusted plus true-night skip 4.86 (V, one verifier). See 5.2 | Dead |
| BBRSI best cell | MAR 7.42 → 7.64 (adj. 8.25), n=184 < 300 | Dead (sample gate) |
| GOLDX best cell | MAR 4.30 → 1.34 (adj. 1.86) | Dead, and more so |
| FLAWLESS / AOSTOCH | 1.73 → 1.93 / 1.47; AOSTOCH about 0 | Dead |
| EMAX closest miss (20/100 long) | MAR 7.82 → 6.61 (adj. 6.31) | Dead, further from the bar |
| HULL / ICHIHULL / MACDRSI best | 2.89 → 2.93; 5.83 → 5.48; 1.91 → 1.78 | Dead |
| MACD200 published | +$30,858 → -$4,444 (adj. +$12,486): about half its profit was roll offset | Dead |
| PMAX | NQ best 6.29 → 5.43. ES best 5.00 → 7.14 (adj. 7.06) | Dead (ES not the deciding set) |
| CBU-Q #427 | Not re-run. The crowned config uses only the premarket level, 1m ATR and volume | FAIL stands |

**Two detector-independent defects**, relevant only if these files are revived:
- ICHIHULL's prior-day "confidence" filter and dollar stop/target read raw prices across a switch.
- MACD200's resting stop orders keep old-contract price levels across a missed switch.

### 3.8 Numbers the verifiers corrected or qualified

*Round 1:*
1. **ENGU-Q lockboxes include the June 2026 switch.** The draft's "$4,210-$4,590 lower" and the #370/#377 cold-LB estimates are SUPERSEDED (see the June table in 3.2).
2. **#370 booked offset** is $24,862 (not $24,865). The **#339 ES leg** stitch is $17,125 (claimed $17,128).
3. **The #335 path decomposition.** The same-path stitch is $29,805 on 24 trades (claimed $29,340). "$62.8k" is the between-switch window; the single trade is $65,121.
4. **DIP sign conventions.**
   - On #425's 20 caught crossings a $1,671 **loss** was hidden, not a gain.
   - The real gaps deleted on false-flag nights were net **gains**: +$680.50 (#425) and +$3,462 (#307).
   - The 2020-03 NQ offset is -12.75, not "-12". The #307 window has 32 false flags, not "about 31".
5. **DIP #423**: the D lockbox drawdown worsens from $12,557 to $14,848. This was not in the original claim.
6. **Stitch sign bug in the "holders" side table** (short trades were booked as long):
   - RFML / GAINZ_RF ES: the true stitch is **-$10,475** (not +$18,825), so net-minus-stitch is -$180,746.
   - Legacy ENGU_1_3_4 NQ: **-$6,505** (not +$6,505), so -$80,089.
   - No verdict is affected; both are dead.
7. **TTIBS details.**
   - #167's -$20,960 is about half stitch ($9,995) and half a change of trades.
   - On #169 the forced exit before each switch itself costs about $9.4k; the back-adjusted run gives only -$5,420.
   - #167's pre-lockbox drawdown rises from $46,273 to $54,978.
8. **#397 vs #379 "19%"**: #397's selection n/DD is 19% *below* #379's. Put the other way, #379 is about 24% above. See item 13 for like-for-like states.
9. **RESEARCH_LEDGER 1.15** gives #370's prior as 30 crossings, but seam_leg's own output is 20.

*Round 2:*

10. **Shift invariance.** The full-window +5,000 test covered the #335 leg and #370 (plus TTM #369/#353 and ORB #297/#234). The all-file check used +3,144.25 over 2021-01..2026-06 with champion params only (3.2).
11. **"Fake breakout entries"** overstated it. The $65,121 trade was a real 5-month hold that a stale regime filter admitted, and the -17% is a change of trades dominated by that one entry (3.2).
12. **#300 June** is not a contradiction (3.5).
13. **#397 vs #379 was not a mixed-state comparison in the end.** The sweep-holders group did compute #379 in four states: raw, TTM alone, TTM+NOISE and all three fixes (M, parity exact with the stored book). The ENGU-Q-only state was not computed:
    - All three fixes: #379 selection n/DD 40.05 against #397's 32.32 (#397 19.3% below). Held-back year 10.76 against 11.55 (#397 still ahead).
    - TTM+NOISE fixed: 42.97 against 34.69 (19.3%).
    - TTM fixed alone: 43.05 against 34.76 (19.3%).
    - Raw: 44.35 against 43.72 (1.4%).
    - The draft's "combined figure not computed" was wrong.
14. **The book55c calendar-year test is M** (harness-misc, one agent). Its "5 wins / 3 losses" corrects ENGU-Q and TTM but not NOISE. See 4.3.
15. **ENGUQ_335_VC's weekend exit** is -$7,815.66 (not -$7,821), and it is a real loss (4.5.4).
16. **#381's June crosser.** The draft's harness summary flagged it at "~$4,210" (`work/enguq/impact2/summary.txt:103`), but no published table deducted it. The correct effect is +$6,305 (3.2).
17. **#370's June LB-by-entry estimate** ($28,136) was right despite the wrong time and offset: the change of trades dominates, and the result is the same at ES offsets 61-66.
18. **r18.** The skip removed 466 nights, not 441 (441 = 2,982 - 2,541). The fake carry left in the retracted pass is +$5,840 on 25 nights, not the investigator's +$13,938, of which about $8.1k was a sample change (5.2).
19. **Critic claims refuted:**
    - `pine/TTIBS_1_0.pine` has comments only, no detector code.
    - `tests/test_dip_open_marks.py` needs extending, not changing.
    - NOISE_H_RF did not take the 09-14 trade; its gate refused it.
    - ORB is not unaffected in paper; it was hit through its volatility filter.
    - `find_master` picks by session, not "24-hour first", and the 150-day warm-up applies only to some shadow legs (4.5.5).
    - The masters do not "match the capture tick for tick": prices mostly do, volumes do not (2.7).

---

## 4. What changes

### 4.1 Crowns and ranking: nothing changes

- **ENGU-Q.** #335 stays the ENGU-Q crown. Its order against #309, #226, #265 and #249 is the same on net, PF and the validate lockbox. #407's PF lead over the #335 cell widens from +0.02 to +0.12, which decides nothing. #381 stays FAIL after the June repair (lockbox by entry -$23,313 → -$17,007, V).
- **TTM.** #369 stays best.
- **ORB.** Unchanged: #314 (Webull), #257 (starred), #239.
- **NOISE.** #382 moves +1.1% (M).
- **DIP.** DIP on ES #425 stays PASS.
- **TTIBS.** Stays closed.
- **Starred runs** #243, #257, #335 and #366 all keep their status.

### 4.2 Verdicts

Every crowned, starred, book and paper PASS keeps a positive cold lockbox with PF ≥ 1. The lockbox rule is net > 0 and PF ≥ 1.

| Run | Cold lockbox before → after (June 2026 not adjusted) | June 2026 (round 2) |
|---|---|---|
| #335 champion | $58,163 / PF 1.531 → $43,468 / PF 1.366 | Cold LB to be recomputed. The June repair moves the whole-run lockbox-by-entry by -$5,860 (V) |
| #370 | $25,372 / PF 1.614 → $17,261 / PF 1.406 | Cold LB to be recomputed (the whole-run repair is -$6,824, V). LB by entry $28,136 (V) |
| #227 | $66,262 / PF 1.313 → $59,278 / PF 1.281 | To be recomputed (the est. used offset 210.5 against about 293) |
| #300 | $25,359 / PF 1.191 → $16,499 / PF 1.124 (true switch days; back-adjusted with no guard $23,325 / PF 1.208, so the roll itself moves it only -$2,034; see 3.5) | n/a. No #300 trade is open across 06-12 → 06-15; the 06-05 → 06-11 trade crosses only the feed change |
| #369 / #353 | Unchanged | Unchanged at +54.4 (M); not re-checked at +64 |
| #425 (warm) | PF 1.90 → 2.13 (C) / 1.82 (D) | Every version drops the whole June gap; the real-move add-back is to be recomputed (3.6) |

- **Other verdicts.** #291, #381, #330/#399, #329 and #163 remain FAIL. WEAK runs stay WEAK.
- **The only lockbox flip** is #152, a superseded July ENGU-Q PASS that was never deployed and cannot be reproduced. On today's file its lockbox goes from +$15,119 to -$11,904 (PF 0.943). #144's July lockbox is already negative on today's file.
- **Not re-run for any crown:** walk-forward folds (except the fixed-champion proxy for TTIBS/TTM/NOISE), PBO, DSR and WFE. None of these sits near its bar after 2-17% net changes, but that is not proven.

### 4.3 Books #366, #396 and #397

All figures cover 2010-06-07 to 2026-06-30, with the lockbox from 2025-06-30. "Pre" is the pre-lockbox selection stretch, and n/DD is net divided by max drawdown. June 2026 is not adjusted in any column.

| Book | Before: whole / pre n/DD (DD) / LB net (n/DD) | ENGU-Q fix only | TTM + NOISE fix only | All three fixes |
|---|---|---|---|---|
| **#366** adopted, starred | $1,685,715 / 38.18 ($36,562) / $289,811 (10.33) | $1,581,489 / 35.52 ($36,562) / $282,750 (10.07) | $1,655,222 / 33.42 ($40,854) / $289,811 (10.33) | $1,550,996 / 31.04 ($40,854) / $282,750 (10.07) |
| **#396** recommended | $1,790,319 / 40.57 ($36,562) / $307,096 (11.16) | $1,686,093 / 37.91 ($36,562) / $300,034 (10.91) | $1,744,265 / 32.69 ($43,967) / $307,096 (11.16) | $1,640,039 / 30.48 ($43,967) / $300,034 (10.91) |
| **#397** frontier | $1,773,541 / 43.72 ($33,567) / $306,042 (12.07) | $1,669,315 / 40.82 ($33,567) / $298,981 (11.55) | $1,727,487 / 34.69 ($40,971) / $306,042 (12.07) | $1,623,261 / 32.32 ($40,971) / $298,981 (11.55) |
| #379 (for comparison) | $1,773,184 / 44.35 ($33,350) / $294,142 (11.02) | n/a | $1,727,129 / 42.97 ($33,350) / $294,142 (11.02) | $1,622,903 / 40.05 ($33,350) / $287,081 (10.76) |

- **Verification.** #366/#396/#397 are all V, except #366's TTM+NOISE and all-three columns, which are M and follow arithmetically from V leg deltas. #379 is M.
- **All 8/8 PASS in every variant.**
- **Pre-lockbox open-marked (valued-daily) drawdown** was not in the draft. Round 2 re-derived it independently, and it matches the house reading to the dollar (V):

  | Book | Before | All three fixes | ENGU-Q fix alone |
  |---|---|---|---|
  | #366 | $37,444 | $41,736 (+11.5%) | $37,444 |
  | #396 | $37,444 | $44,849 (+19.8%) | $37,444 |
  | #397 | $34,449 | $41,853 (+21.5%) | $34,449 |

  - The worst stretch is 2020-03-02 to 2020-03-27 in every variant, and open marks add $882 over the closed drawdown.
  - With ET-session-day stamps the figures are $36,649 → $40,941 / $44,054 / $41,058 (M).
  - The lockbox open-marked drawdown is $49,855 in every variant. It sits in 2026-06-18..06-26, just after the June splice, and was not re-checked with the splice repaired.
- **June 2026.** The draft's "~$4,210-$4,590 lower" is SUPERSEDED.
  - The #335 leg's June repair is -$5,860 on both whole run and lockbox (V, measured on the raw leg), so books through that leg should fall by about that much more.
  - Their TTM and NOISE legs also carry the uncorrected June RTH gap (not quantified).
  - Combined book figures are to be recomputed.

**Why the drawdowns rise.** The whole pre-lockbox drawdown increase in all three books is one new TTM short on 2020-03-17, inside the Feb-Mar 2020 worst stretch. It costs 3 × -$2,468 = -$7,404 with #369 (#396/#397) and 3 × -$1,431 = -$4,292 with #353 (#366) (V).

**Decisions whose evidence weakens (owner calls, no automatic flip):**
- **#396 over #366.** It was "better on both stretches".
  - Corrected, #366 is slightly ahead on the selection stretch (31.04 vs 30.48).
  - #396 still wins the held-back year: $300,034 / PF 1.585 vs $282,750 / PF 1.550 (10.91 vs 10.07).
  - **Book55c calendar-year test (M):**

    | Correction state | #396 vs #366 wins / losses |
    |---|---|
    | Before | 6 / 1 |
    | ENGU-Q fixed | 7 / 1 |
    | TTM fixed alone | 4 / 3 |
    | ENGU-Q and TTM fixed (NOISE not fixed in this test) | 5 / 3 |

    #397 vs #396 goes from 6 / 4 to 7 / 4.
  - The squeeze swap earns more net in 11 of 15 years, not 13 (M).
- **#397 over #379.** The held-back-year ranking is unchanged (11.55 vs 10.76, all fixes). But on the selection stretch #397 now trails #379 by 19% in each of the three corrected states computed for #379 (32.32 vs 40.05 all fixes; 34.69 vs 42.97 TTM+NOISE; 34.76 vs 43.05 TTM alone), against 1.4% before; the ENGU-Q-only state was not computed for #379. #379's worst stretch is May 2022, which the correction does not touch (M).

### 4.4 Other books

| Book | Before → after | Status |
|---|---|---|
| #339 (ENGU-Q NQ + ES) | $831,955 → $704,959 (-15.3%). LB $137,136 → $126,934. Open-marked DD $77,880 → $84,447. PASS 8/8. The June est. (LB about $120.2k) is SUPERSEDED; to be recomputed | V |
| #312 (#226 leg + ES #295) | $711,259 → $586,144. Slices 7/8 → 6/8, still at the PASS floor. #295 also crosses the July hole (not repaired) | M |
| #347 (#226 leg) | $793,811 → $702,192. Slices 8/8 → 7/8 | M |
| #371, #361, #337, #317 (#309 leg); #365, #375, #372, #363, #323 (#335 leg); #262 (RTH leg) | Each loses its ENGU-Q leg delta (-$96,992 / -$104,226 / -$103,706 / -$102,989). All stay PASS | M |
| #311, #346, #348 (DIP #307 leg) | Drawdown +$7,668 (#311: $114,107 → $121,775). PASS 8/8. B11 MISSes deepen (#311 MAR ratio ×1.008 → ×0.93-0.95) | M (leg V) |
| #332 | DD $73,194 → $75,755 (C). The r25 gates still hold | M |
| **#417, #418, #419** | **Not a roll issue.** The job docs carry no params for the ORB, ENGU-Q, TTM and NOISE legs, so they ran at the function defaults (ENGU-Q = #226's cell, 2,843 tr / $420,506). The TTM defaults reproduce the intended TTM leg exactly (354 tr / $407,653 = #369 ×3 in #417/#419; 357 tr / $303,050 = #353 ×3 in #418), so only the ORB, ENGU-Q and NOISE legs actually differ. They are not "#396/#366 + X". Roll fixes: #417 $1,785,603 → $1,749,055; #418 → $1,660,012; #419 as in 3.5 | V (params finding) |
| #238, #324, #351, #287, #288 | Not reproduced (one leg's params cannot be recovered locally, or the leg is ML-gated). Leg-delta bounds only | n/a |

### 4.5 Paper and live legs

This section replaces the draft's "live execution is not affected". What round 2 verified is below, no stronger and no weaker.

#### 4.5.1 Real money

- **No real-money order is exposed to the unadjusted data.** (V)
  - NinjaTrader's strategies trade the Tradovate demo account DEMO7240108. `bridge.json` lists only DEMO7240108 and Sim101. The real account 1810769 is refused in compiled bridge code, and its fills are manual (no signal name).
  - In NinjaTrader's database, EdgeLogNOISE and EdgeLogENGUQ1m are on DEMO7240108; EdgeLogORB230 and the three PAR instances are on Sim101.
  - Webull orders go through `api/webull_orders` in PAPER mode on the PC config. The cloud box's broker block reads: requested and effective PAPER, sandbox, live_armed false, **live_credentials_present true**. `qqq_exec` reports mode SHADOW.
- **NinjaTrader's own signals do not read EDGE-LOG prices.** They come from NinjaTrader's own chart series (merge policy MergeBackAdjusted). EdgeLogENGUQ1m reads and writes only its own position file. The only path from EDGE-LOG unadjusted data to an NT order is EdgeLogNOISE's call to the ML gate. (V)
- **Not affected (V):**
  - The QQQ signal engine (`api/cloud_signal.py`): entries and exits come only from QQQ bars (Webull history and Yahoo QQQ). There is no `find_master` or NOADJ reference in cloud_signal, qqq_paper or qqq_exec. ORB_R6 and ENGUQ_335 on QQQ have no NQ input at all.
  - `qqq_exec`'s nq_ratio pricing reads the NT 10s capture, and only for NT-sourced fills; the box runs signal_source `engine`.
  - `tools/nt_rollover.py` reads no market data; it edits the NT workspace, the database and the bridge. It rolled EdgeLogNOISE (MNQ) and EdgeLogENGUQ1m (NQ) to 12-26 on 2026-09-15.

#### 4.5.2 Where the unadjusted data does reach a demo or paper order

**(a) The NinjaTrader ML gate (`api/gate_live.py`, port 8392).**
- **What it trains on.** Its artifacts are refit every night on the leg's own backtest, over `find_master(inst, tf, session)` (NOADJ_NQ_5m_RTH for the NOISE legs, NOADJ_NQ_1m_ETH for ENGUQ_ER_H) plus the NT 10s capture ticks. The 09-14 splice put a fake long (09-14 11:45-15:55, -49.03 points) into its training set. (V)
- **Who asks it.**
  - The service scores 6 legs, but NinjaTrader only ever asks for NOISE_H_RF: EdgeLogNOISE.cs is the only strategy with a gate address (300 ms timeout).
  - ENGUQ_ER_H.pkl is also read, by `tools/qqq_paper.py`, which writes its probability and size onto the ENGUQ_149 rows of the QQQ paper blotter (paper only; M).
  - The other four artifacts go nowhere.
- **Calls 09-11..09-25: 9.** 1 ORDERED (09-22 09:45 ET, p=0.5704, 11 MNQ, filled 30,906.5 → 31,025.25 = **+$2,612.50 demo**), 1 SKIPPED (09-23 10:15, p=0.5442), and 7 fail-opens at base quantity 3 (3 bar mismatches on 09-16 ×2 and 09-21; 4 timeouts on 09-23). (V)
- **No scored decision ever used the distorted September bars.** NinjaTrader made no gate calls on 09-14 or 09-15. The service's series was stale on 09-14/09-15, and both 09-16 calls failed open. On those bars the features were far off (prior-day distance features by up to 18.8 ATR). (V)
- **Replays reproduce the served model exactly** (5,658 trades, max probability difference 0.0). Corrected replays:

| Decision | Logged | September splice fixed | Earlier 64 switches fixed | All fixed | Seeds 43-62 (raw / all fixed) |
|---|---|---|---|---|---|
| 09-22 09:45 take, 11 MNQ | 0.5704 | 0.5690, still takes 11 | 0.5247, skip | 0.5227, skip | takes in 19 / 12 of 20 |
| 09-23 10:15 skip | 0.5442 | 0.5509, would take 10 MNQ (margin 0.0009) | 0.5159 | 0.5133 | takes in 3 / 2 of 20 |

- **Money on demo.**
  - Under the full correction, the 09-22 take becomes a skip, worth about **-$1.9k to -$2.6k** on demo. The two verifiers model NT's next ask differently: -$2,038 via the stale partial bar then a 10:00 fail-open, or -$1,907.50 via a 09:50 fail-open. The investigator's -$590 end assumed complete bars the service did not have.
  - The flip is driven by the 64 earlier switches, not the September splice, and it is seed-fragile.
  - The September-only 09-23 "take" exists only on the incomplete bar the service held (complete bar: 0.5483, skip). Had it fired, it would have lost -$1,840, against the -$823.50 that the actual next-bar fail-open lost. (V)
- **Non-roll defects found along the way (V except where marked).** They moved more demo money than the roll did.
  - **Incomplete-bar scoring.** The capture file lags the bar close by 40-50 s. The 09-22 take was scored on a 09:40 bar missing its last 50 s; with the complete bar the raw model gives 0.5473, a skip. The same lag probably affects every decision.
  - **Timeouts caused by the service.** All four 09-23 timeouts coincide with the service's "live window RESET" rebuilds of 1.2-1.6 s. The late answers were all skips (0.525, 0.531, 0.522, 0.537), so four ungated 3-MNQ shorts went through for -$1,150.50. The link to the rebuilds and the late answers rest on one verifier (M); the -$1,150.50 total was independently recomputed from fills.csv.
  - **Stale series.** The 5m series froze during roll week (09-14 scored 09-11 15:55 all day; 09-15 scored 09-14 15:55; 09-16 was stuck at 09-15 15:55). It froze again on 09-22 on a partial 09:45 bar for the rest of the session.

**(b) KEEL v12 on the cloud box (Webull NOISE_382 share sizing, paper).**
- **What it trains on.** It is rebuilt nightly by `tools/keel_live_state.py` on NOISE #382 over NOADJ_NQ_5m_RTH, from 2010-06-07 with a floating date_to. The box's published state (4,861 trades, trained through 09-25) matches the rebuild from the PC master exactly (same sha256 as the last push). The fake 09-14 long is in its training set, and removing the splice also restores a 09-16 14:05 long the fake move had suppressed. (V)
- **Live entries so far: two, both on 09-25.** Shares = round(10 × size). (V)

| State | 09:40 entry | 12:10 entry |
|---|---|---|
| Raw (as traded) | 1.5 → 15 shares | 1.5 → 15 shares |
| September splice fixed | 1.5 | 1.5 |
| All switches fixed (June +294) | 1.4326 → 14 shares (+$1.62 on paper) | 1.4936 → 15 shares |
| June uncorrected / June +412 | 1.4192 (14) / 1.4725 (15) | n/a |
| All fixed, seeds 43 or 44 | 1.5 (15) | 1.5 (15) |

  So the effect is 0 or 1 share.
- **Tonight's state (for 09-28).** Raw is exactly neutral (learned factor 1.0, member trusts 0). Fully corrected at the live seed it is a tilt with trust 0.033, about ±5% per unit of score. (V)
- **Forward risk (V).** The box reports live credentials present. If Webull live is armed at the planned 1-3 shares, a 5% tilt changes share counts: at a 1-share base, 1.5 rounds to 2 and 1.43 to 1.
- **Also noted (M).**
  - On raw data at seed 42, KEEL was in shade mode (sizes 0.5-1.5) at every nightly cut from 09-10 to 09-21. It went neutral only after 09-22's trades.
  - The box's published trade rows leave keel_size blank even for KEEL-scored trades, so the web tab cannot tell "KEEL 1.0" from "no KEEL".

**(c) Engine-side paper legs.** The 39 shadow legs in `api/paper.py` read the unadjusted masters (21 NQ 5m RTH, 11 NQ 1m 24h, 7 ES 30m RTH). They produce paper records only, no orders (M). See 4.5.4.

#### 4.5.3 Timeline of the September 2026 roll on the paper side (V unless noted)

- **09-10 13:28 ET.** The NT add-on file rolls to Dec at its restart after a 19.3 h outage. Paper probably never used it, because it picks the NT file with the later last bar (4.5.5).
- **09-14 from 08:45 ET.** The NT capture is stale. At 11:30 the Yahoo-fed masters splice Sep → Dec inside one bar. Shadow NOISE legs go long 11:45-15:55. NinjaTrader is down and takes no trades.
- **09-15.** NinjaTrader runs on the Sep contract (strategies realtime from about 09:41 ET) with no fills. The chart capture rolls at 16:00:50 ET. The strategies roll to 12-26 around 17:10 ET. That night's shadow run appends Sep-contract capture bars after the Dec master.
- **09-15 ~23:45 → 09-16 08:26 ET.** The NinjaTrader side is asleep, then hung; nt_recover kills it at 08:26 (M).
- **09-16.** NT8 fills on real NQ/MNQ 12-26 contracts:
  - ENGU-Q (EQ): 13:59, 14:06 and 14:43 longs, -$1,020 - $1,795 - $3,390 = **-$6,205**.
  - NOISE (NZ): 11:55 and 14:05 longs on 3 MNQ each, -$283.50 and -$262.50 gross, both ungated fail-opens.

#### 4.5.4 Paper legs already hit by the September 2026 roll: recorded vs corrected

- **Recorded** = the Firestore paper docs and reports; the replay of `api/paper.run_shadow` reproduced every doc and report value read to the cent.
- **Corrected** = the splice back-adjusted at offsets 288-300.
- For ungated legs the additive, ratio and forward methods agree within $80. Gated legs are method-dependent, because a constant added to 16 years of history changes level-based gate features (ATR ÷ close).

| Leg | Recorded (raw) | Corrected | Status |
|---|---|---|---|
| NOISE family, 09-14 11:45-15:55 long (-49.03 pts) | -$980.66 per contract; 15 legs; **-$17,855.07** in total (NOISE_304, SBS_V90, C15G, C15, NOISE_225, K6 -$980.66 each; K -$970.48; T -$924.45; K7 -$1,185.80; K8/K9/K11/K12 -$1,390.94; SBS_V90_H -$1,592.63; NOISE_H -$1,733.99) | Gone under every proper correction tried (additive 288/295/300, ratio, forward) on the 9 legs that were re-run. The six K6-K12 legs (K6, K7, K8, K9, K11, K12; $7,730.21) were never re-run, so their disappearance is inferred | V on 5 legs (NOISE_304, SBS_V90, C15G, NOISE_225, NOISE_H: $5,656.63); M on 4 (C15, SBS_V90_H/_T/_K: $4,468.22); I on K6-K12 |
| NOISE_304, window 09-14..09-25 | $6,334.44 (16 tr) | $5,247.46 (19; additive and forward) / $5,197.46 (ratio). **Lower**: the splice had widened the bands and suppressed 4 later losers, incl. 09-16 14:05 (-$895.66), which NT8's real NOISE took | V |
| NOISE_SBS_V90 / C15G / C15 | $5,720.10 | $4,533.78. The "$4,963.78 at offset 300" was an additive artifact | V (SBS_V90, C15G), M (C15) |
| NOISE_225 | $5,720.10 | $4,533.78 | M |
| NOISE_H (gated) | $14,989.10 (12 tr) | About $16,245-$16,250 (forward/ratio, 12 tr). The investigator's $31,650.45 was an additive artifact | V (method-dependent) |
| NOISE_H_RF (gated; NT8's leg) | **No 09-14 trade** (0 signals; its gate refused). Window $28,042.61 | Indeterminate: $24,014-$34,133 by method. Robust: a corrected-only 09-16 14:05 long, size 3.57-3.64, -$3,202 to -$3,259, which NT8 also took | V (method-dependent) |
| NOISE_SBS_V90_H / _T / _K | $9,467.62 / $5,461.38 / $5,751.70 | $8,163-$8,293 / $4,130-$4,551 (additive -$138.76 is an artifact) / $4,530-$4,548 | M (one verifier) |
| ORB | 09-16 09:45 long **-$1,930.66**; window $8,200.38 | Trade gone at every offset and method; $10,131.04 | V |
| ORB_R6 | 09-16 14:10 long **-$2,410.66**; window $11,720.38 | Gone; $14,131.04 | V |
| ORB_R6_C15 / C15F / C15FE | -$2,410.66 each; C15F $11,949.72 | Gone; C15F $14,360.38 | V (C15F), M (others) |
| ORB_H | 09-16 09:45 -$2,912.38; window $12,377.63 | Gone; $15,258-$15,359 | M (one verifier) |
| ENGUQ_335, 09-14..09-16 | **-$8,176.77** (8 tr) | **-$2,982.64** at 295-297.75, which also matches one verifier's reconstruction of what NinjaTrader's chart would show. -$4,098.48 at 288-292.5; -$6,197.49 at 300 | V for the figure at each offset; M for -$2,982.64 as the corrected figure (the reproduce verifier did not confirm it) |
| ENGUQ_335, window 09-14..09-25 | $18,423.59 | $25,032-$28,533, dominated by one post-roll long still open and marked at a volume-1 Yahoo bar (09-25 17:00) | V |
| ENGUQ_309, 09-14..09-16 | **-$6,025.36** | -$3,998.55 (295, NT-style) to -$5,730.77 (300); -$5,445.94 at 288. Window from 09-14: $20,575.00 → $25,498.95-$27,517.36 | V |
| ENGUQ_335_VC | 09-15 trades -$1,433.47 and -$10.66 (-$1,444.13); window from 09-08 $18,657.34 | Both 09-15 trades gone at every offset; $20,022-$20,101. Its **-$7,815.66** exit (09-11 → 09-13 18:10) is a **real** Sep-contract weekend-gap loss and is unchanged | V |
| ENGUQ_L50 | -$9,596.79 weekend-gap exit (real); window $10,979.35 | $10,869.30 (additive 295) / $10,908.57 (NT-style) | M |
| ENGUQ_ER | 09-15 -$2,370.66 and +$969.34 | Both gone; net +$1,401.32 at every offset. ENGUQ_ER_H recorded 0 trades on 09-15 | M |
| TTM, 7 legs | Their ES tail (the NT capture, Sep until 09-15 16:00) had a +86.5 gap at 09-15/16, of which +67.75 is carry | Identical trade lists raw and corrected; only TTM_299_SSL traded (+$481.85 on 09-25) | M |
| Book (ORB + ENGUQ_309 + 3× TTM), 09-14..09-16 by entry | -$7,956.02 | -$3,998.55 (295) to -$5,730.77 (300) | Derived from V legs |

- **Paper reports.**
  - The 09-14 report shows a blend of -$17,863 (the NOISE family plus ENGUQ_L50's -$8.02).
  - The **09-15 report** shows a blend of **-$84,279** and a book of **-$10,544.28**. That night's run appended Sep-contract NT capture bars after the Dec master's last bar (18 on 1m, 3 on 5m), a fake drop of about 293 points.
    - It marked ENGUQ_309's 06:01 trade at -$8,246.79 (final doc: -$1,532.13) for 309 and its six gated clones (K, K9, CD, CDE, CDE2, C15).
    - NOISE_304 and NOISE_225 took a fake 15:50 short (-$350.66 each), NOISE_H -$620.03. All were pruned later.
    - Those tail marks explain about $48.3k of the blend: 7 × $6,714.66 of fake mark on the 06:01 trade, plus -$350.66 × 2 and -$620.03 on NOISE. The remaining roughly $36k is post-splice ENGU-Q trades: the 01:53 trade at -$2,297.49 × 7, the 06:01 trade's final -$1,532.13 × 7, ENGUQ_335 -$4,036.55, VC -$1,444.13, ER -$2,370.66 and L50 -$1,296.25. The book's -$10,544.28 is the tail-marked 06:01 trade (-$8,246.79) plus the 01:53 trade (-$2,297.49).
  - Reports are write-once for these legs, so the 09-15 document still shows the artifact. Replayed exactly (V).
- **Offsets and NT8.** The corrected ENGU-Q figures move by several thousand dollars inside the measured offset band. The NT8 fills cannot pick an offset: the NT side was asleep or hung through the 09-16 05:44 signal, and EdgeLogENGUQ1m never opens a position on replayed history (M). On this argument -$2,982.64 is the best-supported ENGUQ_335 figure, but the argument comes from one verifier (M) and the reproduce verifier did not confirm it, so the corrected range stays -$2,982.64 to -$6,197.49.
- **Structural reporting gaps (V).**
  - Daily reports count only entries dated on the report day at run time, so ETH entries made after the ~16:15 ET run never appear in any report. For example, ENGUQ_335's 09-14 16:56 trade (-$902.62) is in the trade docs but in no report.
  - `C:\EdgeLog\fills.csv` has demo fills from 08-11 to 09-03 but none from 09-04 to 09-15, so it is not a complete ledger. The nightly reports' live blocks are the record for 09-14/09-15 (0 fills).

#### 4.5.5 How the shadow legs got the splice (V)

- **Master lookup.** `api/paper.py:1934` calls `find_master(inst, tf, session)` with the leg's session. ENGU-Q (eth) gets NOADJ_NQ_1m_ETH, NOISE and ORB (rth) get NOADJ_NQ_5m_RTH, and TTM gets NOADJ_ES_30m_RTH (ES 30m ends 06-30, so its tail is the NT capture). These are the same sources the crowns were validated on, so passing a source would change nothing.
- **Warm-up.** The 150-day warm-up (`:1724`) applies only to ENGUQ_335, _VC, _309, _L50 and the TTM legs. NOISE, ORB and all gated legs load from 2010-06-07.
- **The tail.** The runner tops up the masters from Yahoo NQ=F/ES=F every 30 minutes (`api/runner.py:2514`, `tools/refresh_noadj_yahoo.py`). Paper then appends NT capture bars strictly after the master's last bar. `_ticks_path` (`paper.py:1727-1768`) picks whichever NT 10s file has the later last bar: the add-on file or `C:\EdgeLog\ohlc`. The chart file runs 24 hours and stayed on Sep until 09-15 16:00:40, which is how Sep bars landed after a Dec master on 09-15.

#### 4.5.6 Backtest evidence behind the paper legs

The backtest evidence shrinks, but every leg stays profitable and their order holds (June 2026 not adjusted):

| Paper leg | Evidence run: before → after |
|---|---|
| NT8 / shadow ENGUQ_335, Webull book leg | #335 leg $603,381 / PF 1.694 → $499,155 / PF 1.534 (V) |
| ENGUQ_335_VC | #335 champion $541,330 → $476,435; cold LB $58,163 → $43,468 (V) |
| ENGUQ_309 | #309 $591,267 → $494,275 (M) |
| ENGUQ_ER / ENGUQ_ER_H | #265 $486,053 → $418,006 (M). The ER_H gate model was trained on the raw data |
| ENGUQ_L50 | #249 $513,014 → $407,010 (M) |
| ENGUQ_149 (Webull QQQ) | #227 $453,532 → $350,542; DD $65,635 → $87,683 (+34%) (V) |
| TTM_299_SSOF2 / TTM_299_SS, SSL / TTM_299, TTM_299_T | #369 / #353 / #299, #340: -7% to -13%, lockboxes unchanged |
| NOISE #382 (Webull) | $604,706 → $611,338 (M) |
| ORB #314 (Webull) | Unchanged (V) |

### 4.6 Documents that now quote wrong numbers

- **RESEARCH_LEDGER row 1.15** (source: seam_leg.py). Only 20 of its 52 NQ "stitches" were real switch bars.

  | Leg | Ledger says | Exact |
  |---|---|---|
  | #335 leg | 23 crossings, $39,580 ($26,595 before the lockbox / $12,985 in it) | 36 crossings, $38,985 ($34,240 / $4,745). June 2026 adds about $5.9k (V) |
  | #370 | $33,912, "a third of its lockbox year" | 35 crossings, $24,862, none in the entry-split lockbox |

  The full losses including changed trades are larger: -$104,226 and -$39,826.
- **BACKTESTING_STACK.md.**
  - The 2026-09-24 TTIBS entry quotes the default-params book #419 ($77,832, PF 1.42, net/DD 20.9). The correct figures are in 3.5.
  - Line 1921 ("441"; "the 18b stop finding stands").
  - Line 1923 (r17 PB20 figures; "roll seams handled").
  - Line 1924 (r16 PIVOT 6.0 → 5.85; trivial).
- **BOOKMARKS.md.**
  - B22 (TRAVEL triage pass was a false-flag artifact), B21 (the "gap 0.35 dies" plateau), B6 (CAP buy/5d), B1 (withdrawn; the r25 pass depends on seam treatment).
  - **B7 (line 23):** every figure and the "why it failed" text. Honest: 201 / $150,017 / PF 1.50 / MAR 2.95, worst trade -$46,651 in 2025. The best honest cell is DBL7 long.
  - **Line 31:** r18b stops "only hurt". Tier 3 steers later designs with the wrong rule.
- **MISC_SWEEP.md.**
  - Line 18: the detector label "GAPFADE-calibrated" (it is unwindowed; the r17 docstring at line 14 has the same label).
  - Lines 25-33 (OOPS and PAIRS rows), 63-87 (the r17 table, the gap row and "no fake jump"), 131-133 ("441"), 140-141 (18b).
  - "Contract-roll days book no fake jump" is false: 39 of 61 switches still book raw carry.
- **index.html.** Line ~25396 (r17 STUDIES text), rows 543-546 around lines 25446-25455, and changelog line 1181 (r18b "every stop level hurts").
- **TV_SWEEP.md** 4.2 (EMAX closest miss 7.82 → 6.61), 13.1 (BBRSI) and 13.8 (GOLDX 4.30 was inflated).
- **DIP run cards** for #425 and #307 (drawdowns).
- **Outside the repo:** the auto-memory note on KEEL live mixes two builds. "Trust 0, t_fast -0.195" matches data through 09-22 (4,855 trades); the box's current state is 4,861 trades through 09-25 with t_fast -0.343 (M).

The round-2 document line numbers above are M (one agent's read).

---

## 5. Harnesses, other roll logic and house infrastructure

### 5.1 Harnesses (closed research rounds)

**Scope.** No harness feeds the detector 24-hour sessions except r32 RELEASE, where the skip turned out to be a no-op. r18b is the one exception of a different kind: it checks stops on NQ 1m 24-hour bars across the 19:00/20:00 switch (5.2).
- ONDRIFT's detector copy is the shared import for r20, r21, r23, r25, r32, r32b, r33, r33b, r34, r35, r36, r36b, r38_scalpers, wfo_daily_dips, wfo_intraday_mr and rocfrontier/make_daily.
- BBRSI's copy feeds ttmsqz_round3_daily. GAPGO's copy feeds r37 and r38_scalp2m.
- r16/r17/r18/r18b carry their own unwindowed variant.

**Method.** Every harness below was re-run unchanged except for the seam call. Each house-detector run reproduced the saved output exactly, or within about 1% where the Yahoo ETF masters had since been refreshed. All are M except seam_leg, the DIP harnesses and r17/r18/r18b, which are V. Figures computed with `RL.true_detector` on midnight-day 24-hour data predate its 2026-09-25 fix and were not re-run.

| Harness | What the seams touch | Result | Flip? |
|---|---|---|---|
| r13 triage / deeptune (SUPERTREND, RSIDIV, MISC ports) | Skip / go flat on RTH | 0 pass in every variant | No |
| **r16** (OOPS, PIVOT, NR4, SESSBRK, MOC, B0, PAIRS) | Unwindowed skip (632 flags); other roll exposures unhandled | 31/31 cells reproduce. OOPS best MAR 2.09 → 2.17 adjusted (3.24 raw with a true-day skip); PIVOT 6.03 → 5.85; NR4 3.22 → 3.21; SESSBRK Asia slightly less negative; MOC and B0 bit-identical; PAIRS 0.14 → 0.71 (+$30,840; Panama on a log ratio is approximate) | No (0/30), M |
| **r17** (PB20, DBL7, RSI2, DONCH, GAPGO, R1030) | Unwindowed skip plus whole-gap deletion inside held trades | B7 PB20 long MAR 4.59 → 2.95 honest; best honest cell DBL7 long 5.58; no cell reaches MAR 8 (5.2) | No (0/16); B7 wrong |
| **r18** (ONDRIFT) | Unwindowed night skip | Retraction stands; honest uptrend MAR 5.09 (back-adjusted) / 4.86 (back-adjusted plus true-night skip) | No |
| **r18b** (ONDRIFT stops) | Same skip; stop checked on 24-hour bars across the switch against an RTH entry | "Every stop level strictly worse" refuted: 1.0-1.5x ATR a wash, only 0.5x hurts | **Finding flips** |
| r20 | RTH seams; nights skipped on NQ 1m 24h; gap drop | 18-24 overnight long slice $41,746 → $28,529 (true detector) / $27,661 (adj.): about $22-27k was fake carry. B6 $238,892 / PF 1.81 → $196,683 / PF 1.62 (adj. $253,668 / PF 1.74) | No |
| r21 | Soup / prior-day levels; cell A = ENGU-Q on ES 24h (no detector) | Cell A PF 1.125 → 1.103 net of $17,812 stitch (1.081 adj.), still under the 1.15 bar. Its follow-up is #295 | No |
| r23 | Breakouts on raw closes | Best cell $55,286 → $58,636 (true) / $1,332 (adj.): the profit was a raw-price roll artifact | No (dead) |
| r25 | Dip legs; champion column = #226 config | Standalone MAR 8.08 → 8.61 (true; PB20L drops out) / **7.92 adj. (fail)**. The champion reference books $47,050 of offsets | Only on adjusted prices; moot (B1 withdrawn) |
| r25b | Same | K1 10.31 → 9.53-10.09 PASS; K2 fail; K5 still MISS | No |
| r32 RELEASE (**the only 24h use**) | All 23 flags are Sundays already dropped; trades intraday | Unchanged | No |
| r32 VALUE AREA / r32b WEEKLY-OR / r34 | Prior-day VA / weekly holds / day skips | Weekly-OR gets worse ($149,819 → $119,781) | No |
| r33 / r33b OVNGO (GAPGO seed) | Gap filter | NB gap0.15 PASS strengthens: $151,024 / PF 1.341 / n/DD 9.06 → $170,942 / PF 1.387 / 9.62. "0.35 dies" weakens (PF 1.215 → 1.288) | No |
| r35 | Gap / fill cells | 13/13 fail both ways | No |
| **r36** | Day skips; ONRANGE overnight range on 24h data | **T-TRAVEL 1000/k0.3 triage PASS n/DD 8.08 → 6.09 (true) / 6.08 (no skip): FAIL.** It rested on the 2020-09-08 false flag. Its descendant #329 had already failed its lockbox | **Yes** (dead family) |
| r36b | Pooling analysis | "Pooling beats either leg" reverses: 8.78 pooled vs GAPGO 9.62 | Claim reverses |
| r37 / r38 2m / r38 scalpers | Day skips; prior-day high/low | 0/39, 0/28, 0/20 both ways | No |
| seam_leg (ledger 1.15) | Estimated stitches from house seams | See 4.6 | Figures wrong |
| nqdip_transfer_es | DIP file plus control | ES crown TRANSFERS in all modes (true days ×2.10, 10/15, exactly on the bar). The defaults cell flips to TRANSFERS on adjusted prices only (9/15 → 10/15); it drove no decision | Defaults cell only |
| nqdip_beta_check | Same | ×2.07 → ×2.00-2.12; conclusion stands | No |
| wfo_daily_dips (+ books, wfo_nasdaq_fine B11) | Gap drop, fill blocking | Screen-1 NQ+QQQ near miss 7.29 → 7.91 (true) / 6.80 (adj.) against the bar of 8 | No |
| wfo_intraday_mr | Same | Pooled PF 1.004 → 1.036/1.040; dead | No |
| ttmsqz_round3_daily | Go flat / block | Best cell $154,961 / PF 1.74 → $105,849 / PF 1.47; dead | No |
| make_daily consumers (ledger 2.16 / 2.18 / 2.19) | Seam column | Crash-short and short-mirror stay dead; the rebal output is byte-identical | No |

**Found with no roll handling, not re-run (M):**
- `tools/r22_misc_triage.py`: cell C is an ENGU-Q 5m port on NQ 5m 24h, held across switches, and PULLTRIG reads prior-day levels. Back-adjusting would lower cell C's PF of 1.11 further, so "ENGU-Q needs 1m" cannot flip.
- `tools/r14_overnight_check.py`: its prior-close-to-09:30 reference includes switch nights. Its 02:00-03:00 window cannot contain the switch.

**Still not audited:** `tools/intraday_diag.py` (its "overnight premium" is probably inflated the same way OVERNIGHT is) and the travel diagnostic in `tools/orb_hunt4.py`.

### 5.2 Rounds 16-18 in detail (round 2)

**The unwindowed variant** (`r17_misc_triage.py` `_seams` lines 80-89; the same in r16:81-91, r18:55-60,75 and r18b:39-44,52,59). It flags every day of the year whose gap is at least 15 points and at least 2.5 times the median: **632 of 3,868 days**. It catches only **22 of the 61** real switches (8 of 14 since 2022), so 39 switches still book raw carry. All 61 fall strictly between RTH sessions. (V)

**r17** (`_signed`, lines 104-119, deletes the whole overnight gap from multi-day holds on every flagged day). My own loop reproduces all 10 multi-day cells to the cent (V).
- **B7 as shipped:** PB20 long 168 / $150,654.12 / PF 1.8795 / DD $32,855.66 / MAR 4.585.
- **B7 honest** (back-adjusted, no seams): 201 / $150,017.34 / PF 1.5004 / DD $50,776.32 / **MAR 2.954**. With a 0.25-point roll cost per switch: $149,932 / MAR 2.953.
- **True switch days plus the house gap-drop:** 193 / $97,912.62 / PF 1.3165 / MAR 2.10. This is not an honest benchmark: it still deletes the real-move part of every switch-night gap.
- **What the gap-drop did.**
  - On PB20 long it deleted 189 gap-days inside holds, only 6 of them real switches, removing $31,545 of net overnight losses ($25,350 of it on non-switch nights).
  - Its worst trade (2025-02-24 to 03-11) is -$46,650.66 on honest prices and shows as -$32,855.66 shipped, which is exactly the reported DD. B7's "-$23k 2022 hold" (-$23,360.66) was only the second-worst even in the shipped run.
  - The bias depends on the cell (M). Running the same gap-drop on back-adjusted data:
    - it inflates PB20 long (MAR 5.24 vs 2.95) and DONCH 20/10 (4.12 vs 0.64);
    - it deflates RSI2 thr10/long (1.06 vs 3.99) and DBL7 long (3.86 vs 5.58).
- **Best honest cell:** DBL7 long, 155 / $174,002.70 / PF 1.8236 / DD $31,201.32 / MAR 5.577. Next is RSI2 thr10/both at 4.38. RSI2 thr10/long goes 1.43 → 3.99 and DONCH 20/10 3.16 → 0.64. No cell reaches MAR 8, so **0/16 stands**.
- GAPGO stays negative in every treatment: the honest gap0.5% cell is 1,360 / -$33,698 / PF 0.971 (M). R1030 does not use seams.

**r18** (V): exact parity on all 5 ONDRIFT cells, and the retraction stands.
- The skip removed **466** of 3,007 raw uptrend nights, not "441".
- The retracted $282,478 pass also held **+$5,840** of fake carry from 25 switch nights the skip missed (237.5 points of it on 2024-09-16). With that removed the cell is 2,541 / $276,638 / PF 1.486 / MAR 14.29.
- **Honest uptrend cell:**
  - Back-adjusted, no skip: 3,009 / $216,069 / PF 1.200 / DD $42,491 / MAR 5.09.
  - Back-adjusted plus a true-night skip: 2,965 / $211,708 / PF 1.199 / MAR 4.86.
  - The investigator's 5.43 used a raw-close 200-day trend filter.
- No other ONDRIFT cell passes in any treatment.

**r18b** (V): exact parity on all 4 stop cells.
- 25 of the 2,541 shipped nights cross an unskipped switch, and the stop fires on 6 / 1 / 1 of them (0.5x / 1.0x / 1.5x ATR). The switch crossing did not drive the result; the foresight sample did, by removing the big-gap nights, which are where stops pay.
- **Honest stop grid**, back-adjusted RTH and 24h, no skip:

  | Stop | Net | PF | MAR |
  |---|---|---|---|
  | None | $216,069 | 1.200 | 5.09 |
  | 0.5x ATR | $157,544 | 1.151 | 4.62 |
  | 1.0x ATR | $222,854 | 1.208 | 5.01 |
  | 1.5x ATR | $217,805 | 1.202 | 5.13 |

  - Wide stops cut the worst night from -$20,001 to -$8,251 / -$9,858.
  - With a true-night skip added: none $211,708 / 4.86; 1.0x $219,312 / 4.81; 1.5x $215,526 / 4.95.
- **The correct reading:** a 0.5x stop hurts, and 1.0-1.5x is a wash. It is better on net and PF, with MAR within ±0.1 either way. "Every stop level strictly worse" is refuted. No verdict flips: ONDRIFT is dead at MAR about 5 either way.

### 5.3 Other roll or gap logic found by the whole-repo search (M)

| Location | What it does | Effect |
|---|---|---|
| `augur_engine/analytics.py:1696-1765` `_within_session_mask` | Drops returns across day boundaries, but on 24h masters the 00:00 UTC switch bar stays in | Report tail fit and 19:00/20:00 seasonality contaminated (display only) |
| `augur_engine/context.py:153-181,237` `gap_pct` | Includes the carry on switch days (about +1% on 2022+ NQ) | Feeds trade-context and ML-gate features; not quantified |
| `tools/setup_journal.py:882-888,1004-1015` | Blanks prior-day features when a gap above 0.6% falls in a roll window | Journal pages only |
| `tools/rocfrontier/flow_scan.py:32` | Drops moves of 400+ points as "stitches"; no switch falls in its windows, so it drops only real moves | Scan only (dead hunt) |
| `tools/rocfrontier/hod_scan.py:14-17` | Drops bars over 12× the rolling median as stitches; catches big 2022+ switch bars and real spikes, misses small old offsets | Scan only |
| `tools/orb_round3_batch1.py:67-70` `in_roll_week` | Descriptive ORB bucket | None (ORB is immune between sessions) |
| `tools/qqq_paper.py:454` `session_gap_flags` | QQQ gap-skip rule | None (ETF, no roll) |
| `tools/r60_noise_fresh_tail.py:5` | Excludes Yahoo rows after 09-16 | Aware of the September splice |
| `TTMSQZ_1_0.py:30`, `pine/TTIBS_1_0.pine:69-75,91`, queue_gapgo / travel_validate descriptions | Comments only (the pine port "deliberately does NOT replicate the seam logic") | None |

### 5.4 House infrastructure (round 2)

**Data-health roll check** (`augur_engine/data_quality.py:183-246` `roll_seam_check`). **It reports nothing today.** (V)
- **The pairing gate fails for every master.** `_find_sibling` (lines 155-180) pairs each unadjusted master with its adjusted twin only when registry row counts are within ±0.5%. It returns no sibling for any NQ/ES master:
  - The four 5m pairs miss by 0.62-0.63%: NQ 5m RTH 321,802 vs 319,791; ES 5m RTH 321,805 vs 319,793; NQ 5m 24h 1,144,059 vs 1,136,974; ES 5m 24h 1,145,886 vs 1,138,800.
  - The rows found only in the unadjusted masters are exactly 2026-06-30 10:50 → 2026-08-05 (2,011 / 2,012 / 7,085 / 7,086).
  - The 1m, 2m, 15m, 30m and 60m unadjusted masters have no twin at all, and `nt_` masters are excluded by design.
  - So the health summary, synced to Firestore meta at `api/runner.py:1259`, adds no roll note and cannot WARN.
- **Even with the gate bypassed** it would miss the 2026 tail.
  - It finds the twins' own steps: NQ RTH 57 seams, 0 false, 64/64 switches carrying a step; ES RTH 62 seams, 63/64.
  - Twin and unadjusted master are identical after 2026-03-16, so the June and September 2026 carries are invisible.
  - Its missing-quarter scan (9/66 on NQ RTH, 13.6%) stays under the 25% WARN floor.
  - The NQ 24h pair adds 1 false seam: 2026-06-07 18:10, the feed seam.
- Its `_boundary_gaps` comment (lines 139-142) already documents the 24-hour mid-session switch.

**Book engine** (`augur_engine/book.py`).
- **`_leg_trades` (lines 66-83) falls back silently.** It tries (session, source), then the implied session, then ('eth', None), then ('rth', None). An RTH leg pinned to a source that is not registered therefore runs on 24-hour unadjusted data (V):
  - NQ 5m RTH pinned `db_adj_rth` resolves to NQ 5m ETH no-adj, and ES 5m RTH does the same.
  - NQ 1m RTH pinned `db_adj_rth` resolves to NQ 1m ETH no-adj.
  - ES 30m RTH pinned `db_adj_rth` resolves to ES 30m RTH no-adj; NQ 1m eth pinned `db_adj_eth` resolves to NQ 1m ETH no-adj; NQ 30m RTH pinned `tv` resolves to no-adj.
  - This is latent today: every #366/#396/#397 leg pins `db_noadj_*` and resolves to its own master. It must raise before any adjusted master is registered.
- **`_mtm_increments` (lines 238-322)** marks open trades at the close of whatever arrays the leg ran on. On unadjusted data an open long's mark jumps by the offset on the switch day. That is not a separate defect: on back-adjusted arrays the marks come out right with no code change. An independent marking matches the house reading to the dollar (V).

**The registered back-adjusted 5m twins.** They are `master_00c66966` (NQ 5m RTH, tv), `master_a85a0438` (ES 5m RTH, tv), `master_adc172d2` (NQ 5m 24h, yahoo) and `master_1a196c0f` (ES 5m 24h, merged). The provenance does not name the builder, but every RTH step equals `tools/stitch_databento.py`'s `_back_adjust` offset, 64/64 on both roots (V).
- **Days.** They step at 64/64 NQ and 63/64 ES switches, on the same days as switches_*.csv. The ES miss (2017-12-07) is where the stitcher's offset is exactly 0.00; the true offset is +2.5.
- **Why the step sizes differ.** `_back_adjust` (lines 121-126) measures the spread at `common.max()`, the *last* overlapping minute of the two contracts. That is 09:29 ET on the old contract's expiry Friday (60 of 64 NQ switches), a median 7.56 days after the switch, so it measures a later, stale spread. The audit's `contract_offset` (ground_truth.py) uses the last common minute *before* the switch and reproduces switches_*.csv 64/64.
- **The audit's definition is the right one.** At the 19:00/20:00 switches the master's own one-bar jump equals `contract_offset` to within 0.40 points on NQ and 0.12 on ES. The stitcher's definition is off by 8.64 and 2.20 (10.28 / 2.22 under a stricter "previous bar one minute earlier" selection).
- **So the twins leave a fake jump at every roll.**
  - NQ, 2022 on (n=17): offset minus twin step averages +12.40 points (mean absolute 18.22), about **+$248 of fake P&L per NQ crossing** (-$445 to +$710). Examples: 2024-12-16 296.50 vs 265.75; 2025-09-14 237.25 vs 208.50; 2022-03-13 1.25 vs -34.25.
  - ES: +2.18 points (mean absolute 4.97), about +$109 per crossing (-$325 to +$512.5).
  - The critic's "±$250 definitional spread in the audit's stitch dollars" is therefore not uncertainty in this audit's figures. It is error in the twins. Runs on the tv twins (TTIBS #162) still carry roll residue.
- **They stop adjusting after 2026-03-16.**
  - The last step is 2026-03-15 20:00 (NQ +204.0, ES +49.5). After that, twin minus unadjusted master is 0 on 8,556 of 8,561 NQ bars. So the June and September 2026 splices are raw in the "adjusted" data, and every auto-refresh appends more raw Yahoo bars.
  - They also lack 2026-06-30 → 08-05, and they differ from the unadjusted masters at the 06-05 16:55 feed seam (NQ +197.25, ES +32.5; M).
- **They cannot be reused as the `db_adj` masters.** The one-line fix to the stitcher: take the last common minute strictly before the first new-contract bar, `common[common < switch].max()`.

**NT capture add-on** (`tools/EdgeLogOHLCAddon.cs`, untracked). It picks the contract only when a capture starts (FrontMonth at StartNext, expiry minus 8 days), so it rolls only when it restarts: 09-10 13:28 ET after an outage. It writes no contract field. (V for code and roll; the ES detail is M)

---

## 6. Proposed fix (NOT applied; owner approval needed)

This replaces the draft's section 6. The facts the design rests on are verified (sections 2.6, 2.7, 4.5 and 5.4). The design itself is a proposal.

### 6.1 One committed roll table

- **`tools/build_roll_table.py`** builds `rolls_NQ.csv` / `rolls_ES.csv` with ground_truth.py's rule: the max-volume contract per UTC day, forward only. The offset is new minus old close at the last common minute strictly before the switch. This reproduces switches_*.csv 64/64 (V).
- **Columns:**
  - `root`;
  - `old` / `new` contract with full expiry year (instrument_id, so decades cannot collide);
  - `switch_sec` (UTC start of the first new-contract bar);
  - `offset_pts` and `offset_sec` (the minute the offset was measured);
  - `kind`: reopen, mid_session or in_bar;
  - `source`: databento_raw, nt_capture, cross_root or capture_spread;
  - `status`: exact, estimated or unknown;
  - `offset_ci_pts`.
- **Explicit NOT-roll rows** for the tail events that look like rolls: the 06-08 00:00 feed seam, the 06-14 18:10 and 09-13 18:10 weekend gaps, the 08-06 00:09 end of the hole, and Labor Day 09-08. Each hole is recorded as its own event.
- The two `inferred_after_raw_end` rows in switches_*.csv are replaced by the tail rows in 6.3.

### 6.2 One module: `augur_engine/rolls.py`

- **`roll_map(arrays, root)`** maps the table onto each array's own bar grid. The masters' grids differ (2.7). It returns:
  - `switch_bar`: the first bar starting at or after `switch_sec`;
  - `mixed_bar`: set when bar_start < switch_sec < bar_start + tf, or when kind = in_bar, propagated to coarser bars;
  - `day_seam`: a drop-in for `detect_roll_seams`, with no 60-session warm-up;
  - `session_seam` (for 18:00 sessions), the `offsets` and the `status`.
- **`adjust(arrays, root)`**: Panama back-adjustment with the table offsets.
  - A mixed bar is rebuilt as O' = O + offset, C unchanged, H = max(O', C), L = min(O', C). It is flagged synthetic and carries a `no_fill` mask.
  - This avoids the fake -292-point low that `RL.adjusted_arrays` leaves on the 09-14 bar, and the fake trailing-stop exit seen on #381.
- **`guard_masks()`**: flat on the last old-contract bar, and no entries until the first clean new-contract bar.
- **`stitch_usd()`**: the offset each trade books, for audits.

### 6.3 The 2026 tail rows

| Root | Switch (ET) | kind | source | offset | status |
|---|---|---|---|---|---|
| NQ | 2026-06-15 03:30 | in_bar | cross_root | +293 (288-300) | estimated |
| ES | 2026-06-15 05:30 | in_bar | cross_root | +64 (61-66) | estimated |
| NQ | 2026-09-14 11:30 | in_bar | capture_spread | +295 (288-300.25) | estimated |
| ES | 2026-09-14 11:30 | in_bar | capture_spread | +67.75 (66.5-68.25) | estimated |

- On RTH masters the June rows map to the clean boundary 06-12 15:59 → 06-15 09:30. The September rows are mixed bars on every master.
- The house-infra thread's central estimates (+298 ± 5 / +65.5 ± 1 for June, +297.5 / +68.0 for Sept) lie inside these bands.
- **Repair order:**
  1. Re-pull Databento for 2026-06..09 to get the exact switch and offset.
  2. If that is not possible, use a contract-labelled NT capture.
  3. Failing both, keep `status=estimated` and make callers stay flat across the switch.
- **Holes are repaired per master**, never treated as rolls: the 1m 24h 06-30 → 08-06 hole, the NQ 1m RTH 07-16 → 08-06 hole, the ES 1m RTH 06-30 → 08-06 hole, the twins' July gap, Labor Day, the missing 06-07 Sunday, and the bad 07-28 01:15 NQ 5m bar.

### 6.4 Future rolls

1. **Authoritative source.** The NT add-on writes the contract name (`instr.FullName`) on every row, or a roll log line on every start. It captures **both** the front and the next contract from expiry minus 12 days to expiry. The switch is then the first UTC day on which the next contract outtrades the front one (the masters' own rule), with an exact offset from the minute before.
2. **Cross-feed check.** A step of about one carry in the rolling median of master minus capture shows which feed rolled and when. This worked exactly for September 2026.
3. **Calendar prior.** Use the window [expiry - 10 days, expiry - 1 day]. If the window closes with no row, the status becomes `unknown`, callers go flat and data health WARNs.
4. **Alarm only, not a detector.** Flag a contiguous bar with |Δclose| ≥ 0.5 × the carry prior and ≥ 10 local SD, cross-checked against the other root.
   - On 2022-26 it found 14/16 NQ and 11/16 ES switches plus both 2026 splices (M).
   - It mis-picks CPI/NFP 08:30 bars when the carry is small, and it misses Sunday-reopen switches.
   - A bar counts as mixed when the switch falls strictly inside it; or when the gap is about 0, the body is about the carry and the other root did not move; or when the capture spread steps inside it.

### 6.5 How strategies use it (the draft's 6(b), corrected)

- **Shift-invariant files run on the adjusted master.** This covers ENGU-Q, TTM and ORB, with no strategy-file edit, and fixes both P&L and the stale-filter entries.
  - The full-window +5,000 shift test covered only the #335 leg, #370, TTM #369/#353 and ORB #297/#234. The other ENGU-Q files were checked at +3,144.25 over 2021-01..2026-06 with champion params. Test 10 must run on each file's real params over the full window before that file is declared adjusted-safe.
- **Alternative for live parity.** At each switch either:
  - re-base the position (add the offset to the entry, stop, trail and every rolling indicator's history), or
  - exit on the last old-contract bar and re-enter on the first new-contract bar. That costs one extra round trip per crossing, about $0.8k over #335's 36-46 crossings.
- **Percent-based files cannot use a Panama back-adjust.** Use the table offsets instead.
  - NOISE: add the offset to the prior close on post-switch sessions (a 2-line change in the core), or equivalently use a forward adjustment.
  - DIP: subtract only the offset in `chain()` and `mark_open_trades`, never the whole gap. This needs a new fork, NQDIP_1_2, which must be added to `tests/test_dip_open_marks.py`.
- **ML-gated legs and KEEL** must be retrained on corrected data with a *named* method (forward adjustment or the prior-close fix). An additive shift of 16 years of history changes level-based gate features (V, 4.5.4).
- **Day-level guards** (TTIBS, RSIDIV, SUPERTREND, MISC ports) use `day_seam` from the table. On 24-hour data the guard works bar by bar, and mixed bars are never filled.

### 6.6 House-infrastructure fixes

- **Rebase `data_quality.roll_seam_check` on the table** instead of row-count parity. An adjusted master's steps must equal the table offsets and cover the last row.
- **Make `book._leg_trades` raise on a missing source pin** before any `db_adj_*` master is registered.
- **Fix `stitch_databento._back_adjust`**: `common[common < switch].max()`. Do not reuse the current twins as the adjusted masters. Register new `db_adj_eth` / `db_adj_rth` masters built from the table, and keep the unadjusted masters as they are.
- **Shadow paper loader (`api/paper.py`).**
  - Refuse to append NT capture bars whose contract differs from the master's last bar. That needs the add-on or chart indicator to label the contract (6.4).
  - Apply the table before the December 2026 roll (expiry 12-18).
- **Replace `setup_kit.contract_switch_sessions`** before SETUPS round 2.
- **Replace every per-file `detect_roll_seams` copy and the r16-r18 unwindowed variant**, in new forks only.

### 6.7 Files needing owner approval, and runs to re-validate

- **Crowned or live files, none changed:**
  - ENGUQ_1M_ETH_R2_1_0.py (#335, #370, NT8 ENGUQ_335), ER, FROZEN, ER25, LIM50, 149F / ENGUQ_1M_1_0: **no edit needed.** Re-run them on the adjusted masters once test 10 passes for each.
  - TTMSQZ_3_0_ES30SSOF2 (#369) and ES30SS20 (#353): no edit; re-validate on adjusted ES 30m RTH.
  - NOISE_1_0.py core (the live #382 chain): optional prior-close fix.
  - NQDIP_1_0.py (#425, #307): new fork NQDIP_1_2 only.
  - TTIBS_1_3 (closed): fork only if revived.
  - `setup_kit.py`; `api/paper.py` (tail guard and table); `api/gate_live.py` and `tools/keel_live_state.py` (retrain source); `augur_engine/data_quality.py`; `augur_engine/book.py`; `tools/stitch_databento.py`; `tools/EdgeLogOHLCAddon.cs` (contract field; also track it in git).
- **Prerequisite:** repair the 2026 tail or add the estimated rows first. Every lockbox that ends after 2026-06-05 contains the June splice.
- **Re-validate after the adjusted masters exist.** Queue these outside market hours, and restart the runner (if registering a new master needs it) only after 16:00 ET:
  1. ENGU-Q #335 (NQ 1m, 12-month lockbox from 2025-06-30, cost 0.533, 900 trials) and #370 (ES 1m, cost 0.4).
  2. TTM #369 and #353 (ES 30m RTH, their saved settings).
  3. DIP on ES #425 and #423 on NQDIP_1_2 (400 warm days, 900 trials, lockbox from 2025-08-24).
  4. Books #366, #396 and #397 with all corrected legs; then #379, #371, #378, #339 and #417-#419 (with their real params); plus the book55c calendar-year test with NOISE also corrected.
  5. Restate evidence for the paper controls #309, #226, #265, #249 and #227 (backtests, not full validates). Refit the ENGUQ_ER_H gate, the NT gate artifacts and KEEL on corrected data.
  6. NOISE #345/#360 and ENGU-Q #295 (July hole).
  7. Optionally #300 and #162 (TTIBS is closed).

### 6.8 Tests

1. The table has 64 raw rows per root, and offsets recomputed from databento_raw equal the stored ones exactly.
2. At the 19:00/20:00 mid-session switches, mean |master 1m jump - offset| ≤ 1.0 on NQ and ≤ 0.5 on ES (today 0.40 / 0.12). The stitcher's last-overlap definition must **fail** this test (8.64 / 2.20).
3. RTH: for all 64, close[s-1] equals the old contract's 15:59 close and open[s] equals the new contract's 09:30 open.
4. 24-hour: `switch_bar` equals the 1m ETH master index 64/64. A Thursday 20:00 switch maps to the correct midnight day and 18:00 session. Include a synthetic Monday-holiday case.
5. Cold start: a window starting 5 sessions before a switch still finds it. The house detector fails this.
6. The 2026-09-14 11:30 1m bar, and the 5m and 30m RTH bars containing it, are flagged mixed. After `adjust()`, no bar within ±30 of a switch has |open - previous close| > 5 local SD. Mixed bars are `no_fill`.
7. Tail rows: 06-15 03:30 NQ, 06-15 05:30 ES and 09-14 11:30 both are rolls; 06-14 18:10 and 09-13 18:10 are **not** rolls.
8. Holes are reported per master.
9. An array past an expiry with no table row gives status `unknown` and a flat guard.
10. A +5,000 shift over the full window, with each file's real params, gives identical trades for every file declared adjusted-safe.
11. Data health: the adjusted master's steps equal the table offsets and cover the last row. This fails today on all three counts: the offset definition, ES 2017-12-07, and nothing after 2026-03-16.
12. A book leg pinned to an unregistered source raises. Today it silently resolves to NQ 5m ETH unadjusted.
13. No new strategy file defines its own seam detector.
14. Capture replay: contract-labelled rows give a switch and offset equal to master minus capture within 3 points.
15. The shadow loader refuses a capture tail on a different contract from the master (added from 4.5.5).
16. A book job refuses a leg without params (the #417-#419 trap).
17. `tests/test_dip_open_marks.py` is parametrized on NQDIP_1_2 as well.

---

## 7. Open questions and owner calls

1. **Build the roll table, the module and the adjusted masters, and run the re-validations in 6.7?** This is heavy runner work, done outside market hours.
2. **The 2026 data tail (data lane).**
   - Re-pull Databento for 2026-06..09 if possible; otherwise use the estimated rows with flat guards.
   - Repairing the master tail will also rewrite the shadow paper history for 09-14..09-16, because shadow trades are re-upserted every night.
   - Decide how to annotate the write-once 09-14 and 09-15 paper reports.
3. **Before the December 2026 roll (expiry 12-18):** the shadow-loader contract guard and the table rows. Without them, the same fake trades recur.
4. **#396 vs #366.** Keep #396 as the recommendation? Its corrected edge is the held-back year only. Re-run the book55c year test with every leg corrected first.
5. **#397 vs #379.** On the selection stretch #397 now trails by 19% in each of the three corrected states computed for #379 (the ENGU-Q-only state was not computed); it still leads the held-back year.
6. **DIP on ES #425.** Restate its drawdown ($54.0k → $66.6-68.7k) before it is weighed as a book leg, and approve the NQDIP_1_2 fork.
7. **NOISE prior-close fix and retraining.** The fix touches the live #382 chain (about ±1%). Retraining KEEL and the NT gate on corrected data should use a named method.
8. **NT gate non-roll defects** (incomplete-bar scoring, rebuild timeouts, stale series). Route to the NT8 paper lane; they moved more demo money than the roll.
9. **Webull live arming.** KEEL sizes from unadjusted data. At a 1-3 share base, a 5% tilt changes share counts. Settle this before live is armed.
10. **Reconcile mapping.** `paper_reconcile.py:73` maps EQ to ENGUQ_ER, while NT runs the #335 settings.
11. **The ENGUQ_ER_H gate model** was trained on raw data and feeds the QQQ paper ENGUQ_149 rows. Refit it?
12. **#417/#418/#419.** Re-run them with real leg params, and add the params guard to book jobs?
13. **#370 concentration.** One trade (2025-04-09 to 2026-03-22, 347 days) books $72,964, about 19% of net, and holds all of #370's lockbox-dated stitch.
14. **Walk-forward, PBO and DSR** were not re-run for any crown. The full validates in 6.7 would settle that.
15. **Document corrections** listed in 4.6: RESEARCH_LEDGER 1.15; BACKTESTING_STACK (the 2026-09-24 TTIBS entry and lines 1921/1923/1924); BOOKMARKS B1/B6/B7/B21/B22 and line 31; MISC_SWEEP; TV_SWEEP 4.2/13.1/13.8; the index.html r17/r18b rows; the DIP cards.

---

**Script and output locations** (`C:\EdgeLog\_anatomy_cache\rollaudit\`):
- **Round 1 groups** (`work\`): `ttibs\`, `dip\`, `rsidiv\`, `supertrend\`, `gapgo\`, `misc-a\`, `misc-b\`, `enguq\` (`impact2\results.json`, `summary.txt`), `sweep-holders\` (`impact\`, including `books_run1.log` with #379), `harness-r20-25\`, `harness-r32-34\`, `harness-r35-38\`, `harness-misc\` (`shift_check_*.json`, `book_impact.log`, `book_years.log`).
- **Round 1 verifiers:** `verify-ttibs-*`, `verify-dip-*`, `verify-enguq-*` (incl. `verify-enguq-method\v5_const_all.py`), `verify-sweep-holders-*`, `verify-harness-misc-*`.
- **Critic:** `critic.md`, `work\critic-completeness\`.
- **Round 2** (`work2\`): `splice2026\`, `paper-hit\`, `live-exposure\`, `variants-r16-r18\`, `house-infra\`, each with `verify-<thread>-reproduce\` and `verify-<thread>-alternative\` (r16-r18: reproduce only).
- **Ground truth:** `switches_NQ.csv`, `switches_ES.csv` (the two `inferred_after_raw_end` rows are wrong; see 2.7), `detector_accuracy.json`, `ground_truth.py`, `rollaudit_lib.py` (true_detector fixed 2026-09-25).