# PREREG - PMFAIL r1 (the small-cap gapper's failed premarket high, short; SCOPE_DISC rank 1) - DRAFT for MANAGER review (2026-10-06)

**Written before any intraday bar of the habitat was pulled** (SCOPE_DISC 87ac032c, accepted at MANAGER #39). No PMFAIL return,
no control return and no signal on any intraday bar has been computed or read. The only numbers here are daily-cache counts
and file hashes. Lane: DISCRECTIONALRY-TO-ALGO. Research id **PMFAIL**, family **MISC** (RUNBOARD rows under MISC by research
id). Shares one Alpaca pull with RUNNER2 r1 (docs/PREREG_runner2_r1_2026-10-06.md); the one pull spec is section 16 here.
Code waits for GO; this draft may sit on main labelled DRAFT. Revised 2026-10-06 after the instrument / rules / tradable
review, before any pull.

## 1. Question and mechanism

On a small-cap gap-up day, when the regular session trades above the premarket high and then closes a 5m bar back below it,
does a short held to 15:55 earn after spread, commission and locate, at the size the capacity cap allows? The judged
population is signals not under Rule 201 (section 5).
- Who buys: individual investors are net buyers of attention-grabbing stocks (Barber & Odean 2008 RFS). That paper shows the
  buying only; the reversal is its conjecture (p. 813), not a result. Cited for the mechanism, never for size or horizon.
- The reversal: stocks with high prior attention open high and fall from the open to the close, mostly in the first hour,
  most in hard-to-arbitrage names (Berkman, Koch, Tuttle & Zhang 2012 JFQA; their attention is measured the day BEFORE, so
  a same-day short is an extension). Robinhood herding events fall over days +1..+5, open to close, caps under $1B (Barber,
  Huang, Odean & Schwarz 2022 JF). That paper does not support a day-0 short, and its day-0 open-to-close is right-skewed
  (mean +3.43%, median -0.06%): squeeze tails are expected.
- Why it could persist: short-sale limits slow the correction (Miller 1977 JF). The same limits make the short costly.
- Journal grounding (setups/CBU.md), stated honestly: all 12 of the owner's stock trades are LONGS held a median of about
  6.5 minutes; none is a short or a premarket-high failure. They lost $133.56, but IPST alone (a 10:59 regular-session
  signal) lost $164; his 9 premarket-signal longs made +$39.69 at a mean -0.23 R. The 15:55 hold comes from the literature,
  not from him. PMFAIL is the inverse of his setup, not "stock CBU" (ALGO_SCOPE Track C endorses no short).
- Disclosure: the author has read CBU.md, which charts those 12 trades (2026-07-07..09-04, after every test window). No
  trigger was checked on them. His 18 sheet trades (2025-11-11..2026-03-10) sit in the unread sealed stock year; any read of
  that year excludes those name-days.

What differs from the dead list:
- SIPORB 2.60: both breakout directions of the first 5m range on the top-20 relative-volume names opening above $5, 10%-of-ATR
  stop (WF -$164,793; next-bar reading t 0.29). PMFAIL: short only, selected by a >= +20% open over a $1-$20 prior close, a
  failed-premarket-high trigger, a structural stop. SIPORB surely held some $5-$20 gappers; the overlap count prints.
- XGAP 2.63: unconditional 09:35-to-close fade of NDX firm-specific gaps, gross ~0 either way. That is OPENPRINT's ground, so
  OPENPRINT stays a reported control here.
- DDW L2 2.62: no-news large-cap gap fade, loses at a 10 bps fill. PMFAIL trades exactly the news/attention gaps L2
  excluded because news moves drift (Chan 2003): counter-evidence, stated as such.
- ATTN 2.61: held overnight (+7.0 bps a night); PMFAIL is flat every night except halted-into-close exits (section 5).

## 2. Prior and map placement

- Standalone small-cap idiosyncratic leg; prior correlation with #463 ~0.
- Prior: ROC @ $30k -15..25, median 0; P(ROC >= 5) 20%, P(ROC >= 15) 8%; P(Stage A pass) ~6%; prior t median ~0.5.
- Map: a new leg must make >= $15k a year at a $30k drawdown of its own (ROC 15; docs/MDL_MAP_R1.md line 5), or take the
  earner route on R, judged at the size the 1% cap allows (section 6). Cost decides: gross must clear a round trip of
  ~0.5-1% plus a locate (priors).

## 3. Data

- **Daily cache (photographed, read-only):** C:\EdgeLog\alpaca_cache\siporb\
  - daily_raw.parquet sha256 fa42412d579ae673815bea25e1c14f9c87a93904af779ccffb03333c8e1bdccd (symbol, date, o, h, l, c, v;
    11,449,264 rows, 6,596 symbols, 2016-01-04..2026-06-30; date = ET session date at midnight).
  - daily_split.parquet sha256 083f8c23d1d62cf7bda99d5c9a6373130c336ac605f57db5eeac832504281f6d (used only for the split
    factor; a mixed 10-03/10-04 photograph from before the vendor's GE re-adjustment).
  - assets.csv sha256 b85928ff655a883dd3eb44d8d96b3b745ffe2f5f0e0ca0991485895f5e960991. Manifest
    C:\EdgeLog\_anatomy_cache\rocfrontier\alpaca_r1\siporb_cache_manifest.json (manifest_sha256
    380b05f2e0c4dfa32faabf2c86311f869d7371d3810a801bbf8a6c1f9ade4b78) lists the same three; all three re-hashed 2026-10-06 and match.
  - Daily volume includes extended-hours prints (1.02-1.14x the regular 1m sum); daily h / l are regular-session values
    (TBIS extended-hours check: the daily high equals the regular high on 34,630 of 35,233 days with a higher
    extended-hours print).
- **Corporate actions:** C:\EdgeLog\alpaca_cache\xgap\corporate_actions_wide.csv sha256
  e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5. Covers only the 5,367 SIPORB-floor names, from 2016-06-01.
- **Shares (float split only):** C:\EdgeLog\_research_cache\xbrl_companyfacts\shares_asfiled_wide.csv sha256
  02387a4f1140c41872a7b46cf6b9657abec90ef90d09a0a2ee47ff882c2f4433 (point-in-time, floor names only), else
  C:\EdgeLog\_research_cache\xbrl_frames\xbrl_shares_frames.csv sha256
  bba7f8737680b7330c74055699b9195b33f10610cf86b3e5c48ba30c7ddadf82 (last-filed, all filers, map by CIK).
- **Book files (C:\EdgeLog\_anatomy_cache\):**
  - rocfrontier\r4\book463_daily.csv sha256 d1543735b5408f50be5971089e00a800f8e510af3d4a63678ff8939f41277dff (mtm, legs
    L0..L3_mtm; UTC day stamps; cut to < 2025-06-30 first).
  - q19\residual_days.csv sha256 bfe64d87a2cf6fd569181ffae9092317653844126de075fe64844430ac189f60 (in_R True on 762 rows).
  - q19\line.csv sha256 98f3edc743625b3742f13a972cab35178658feaa7f506e56e27f77f56e9c38ad (line, book, res_c).
  - q19\a2.json sha256 0c27cb47fe245cd8fbbcc1bc3eb0881ea0edefba74d45b7821a059dc7e4c9214 (the 45 line_episodes).
  - q19\episodes.csv sha256 ebfb67c03a258a0d4efe73a20a2c7027fd5eb3d25403f17d8e071cb4626a9af4 (#463's 28 episodes / 460 days;
    re-hashed 2026-10-06).
- **Intraday bars and quotes:** the new pull, section 16 (SIP 1m bars on every row; see condition 1).
- **Stamps:** Alpaca `t` is UTC RFC-3339 at the bar's START. Convert with the tz database to America/New_York. The 1m bar
  "09:30" covers 09:30:00-09:30:59 and is known at 09:31:00. (Opposite of the NT 10s end-stamp rule.)
- **Sessions:** premarket = 1m bars starting 04:00..09:29. Regular = bars starting 09:30..15:59, or 09:30..12:59 on the
  EARLY_CLOSE_DATES of tools/import_alpaca_stocks.py (lines 139-145). A minute with no trade has no bar.
- **5m bars, built from 1m:** regular-session 5m bar k (anchored 09:30) holds the 1m bars starting 09:30+5k..09:34+5k.
  o = open of its earliest present 1m bar, h = max high, l = min low, c = close of its latest present 1m bar, v = sum. A 5m
  bar with no 1m bar does not exist. It is known at its end (start + 5 min).
- **VWAP (diagnostics only; PMFAIL's rule does not use it; same definition as RUNNER2 r1):** anchored 09:30;
  VWAP(m) = sum(vw x v) / sum(v) over regular 1m bars starting 09:30..m; a bar with vw missing uses (h + l + c) / 3.
- **Every array is cut to dates < 2025-06-30 before anything is computed.** The pull covers 2016-07-01..2025-06-29 only.
  One exception: condition 3 reads each symbol's last-bar DATE from the uncut cache (no price or volume).

## 4. Universe and event filter

- Universe: every symbol in daily_raw.parquet (SIPORB's: Alpaca active + inactive assets on NYSE/NASDAQ/AMEX/ARCA/BATS by
  today's listing, PREREG_ALPACA_R1.txt lines 21-25; share-type exclusions = the BAD_NAME regex of
  tools/rocfrontier/r5_siporb.py lines 85-86 and its symbol-shape rules).
- Session calendar: the distinct dates in daily_raw.parquet. For name s on session t (2016-07-01..2025-06-29):
  - P = raw close of s on the market session before t; O = raw open of s on t (the official opening print).
  - ADV$ = mean of (raw close x raw daily volume) over the 20 market sessions before t; s needs a bar on each, else no event.
  - **Event day** if 1.00 <= P <= 20.00, ADV$ >= 1,000,000, O / P >= 1.20, t is not removed as a split (S1, S2), and t
    carries no Rule 201 over from the session before (section 5; known before 04:00).
- **Split removal (both known before the open).** Day t is removed if:
  - S1, a split Alpaca knows: F = raw open / split-adjusted open on t, F' = raw close / split close on the session before;
    |F / F' - 1| > 0.005.
  - S2, the calendar: corporate_actions_wide.csv has a forward_split, reverse_split, unit_split or stock_dividend for s with
    ex_date = t, after mapping each action's symbol to today's ticker: follow name_change rows (old_symbol -> new_symbol)
    with ex_date >= the action's ex_date, earliest first, until none is left. unit_split rows join on new_symbol (all 241
    have a blank symbol). Matched / unmatched counts per type and year print in counts.json.
- A missed split ON t (no vendor or calendar record) is not removed: the trade uses t's prices only, so its P&L is honest
  on a day that is not a real gap. Two reports print the days each would remove, their count by year and their naive P&L
  (ATTN r1 addendum 2 form):
  - S3p, price only (causal): |O/P - 1| >= 0.25 and O/P within 2% of n or 1/n, n = 2..50. It selects on move size (first
    pass: ~32 of ~3,433 gap candidates, 19 on >= 10x volume).
  - S3v, TBIS's volume test, LOOK-AHEAD (label kept): S3p and (O/P) x (median daily volume over t..t+19 / median over
    t-20..t-1) within 0.625..1.6 (split_like_gaps of tools/import_alpaca_stocks.py, n to 50). Never reads a session on or
    after 2025-06-30; with fewer than 10 such sessions in t..t+19 it falls back to S3p.
- **Counts so far (no returns):** scope 3,098 event days by July-June WF year 2016-17..2024-25 = 103 / 154 / 168 / 450 / 677
  / 330 / 258 / 329 / 629 (scope's whole-ratio guard), 40% in calendar 2020-21; prior close >= $5 only 1,387. Reader recount
  of this section's price / ADV$ / gap filters, no split or SSR removal: 3,401 (3,404 if ADV$ uses the name's own last 20
  bars). The 3,276 / 3,051 figures of the first draft came from an unrecorded rule and are withdrawn. Carry-over SSR marks
  ~721 of the 3,401 (reader count). First pass: median 2 names a session, max 30. Before the pull the builder prints the
  survivors of each filter in order (P band, ADV$, gap, S1, S2, carry SSR) by year and price bucket.

## 5. Trade rules (one trade per name per day, short only)

- **Premarket high PMH:** max high of the 1m bars starting 04:00..09:29 on t. No premarket bar: no PMH, no trade (counted).
- **Trigger window:** regular 5m bars starting 09:35, 09:40, ..., 10:55 (closing 09:40..11:00).
- **Signal:** the FIRST 5m bar in the window whose close < PMH while the max regular 1m high from 09:30 through that bar's
  last minute > PMH. One signal per name-day; if it cannot be traded, the day has no trade (no second signal).
- **Entry:** short at the open of the first 1m bar starting in [signal end, signal end + 5 min). No trade (each counted) if:
  no such bar; it is a halt resume bar (condition 2); the signal is SSR-active; the entry open >= S1.
- **Rule 201 (SSR), shared with RUNNER2 r1.** Rule 201 is triggered only by regular-session (09:30-16:00) last-sale-eligible
  prints, then applies for the rest of that day and all of the next, premarket included (SEC Rule 201 FAQ 1.1, 1.2, 2.1).
  Proxy, both halves regular-session, reference = the prior official close (daily cache):
  - carry-over: the daily low of the session before t <= 0.9 x the close two sessions before. Known before 04:00, so
    such days leave the event set (section 4), counted by year.
  - same day: any regular 1m low from 09:30 through the signal bar's last minute <= 0.9 x P.
  - The judged cells SKIP SSR-active signals, no re-arm: the modelled fill is a marketable short, which Rule 201 bars at or
    below the national best bid.
  - Reports: the SSR-at-open share (09:30 1m low) and the intraday share by year, printed before the count gate; the 04:00
    reading (premarket lows included, an over-mark); and the Rule-201-legal fill on every SSR-active signal, carry-over
    days included: a short limit at the signal 5m close + $0.01 posted at the signal end, filled at the limit only if a 1m
    bar starting in [signal end, signal end + 5 min) has high >= limit + $0.01; no fill = no trade; then the cell's stop
    and exit.
- **Stop (fixed from entry, never moved):** S1 = HOD + $0.01, HOD = max(PMH, every regular 1m high from 09:30 through the
  signal bar). Neighbour: S2 = entry + 1.5 x (S1 - entry), rounded up to the cent. An entry open >= S1 is no trade in both
  cells (counted; not a trade for bars 2-3 or the null's counts).
- **Stop judging** (1m bars from the entry bar through the last bar starting before 15:55; 12:55 on half days):
  - Reading L, stop at level (judged): a bar opening >= stop exits at its open; else a bar with high >= stop exits at the
    stop. The entry is the bar's first print, so checking the entry bar involves no intrabar guess.
  - Reading N, next bar (reported; binds in the stress bar): a bar opening >= stop exits at its open; else a bar with
    high >= stop exits at the open of the next present 1m bar (none before 16:00: halted into the close).
  - A stop jumped by a halt exits at the resume bar's open, in both readings.
- **Exit (15:55):** buy at the open of the first present 1m bar starting in [15:55, 16:00) ([12:55, 13:00) on half days).
  None: halted into the close.
- **Halted into the close (shared with RUNNER2 r1).** No present bar in the exit window is, by condition 2's definition, a
  halt run open at the close. Exit at the raw open of s's first daily-cache bar within the next 10 market sessions (ATTN
  r1's rule, PREREG_ATTN_R1.txt line 44), in both readings. Stress price instead, max(the cell's stop, the last pre-halt 1m
  close), when no such bar exists, it falls on or after 2025-06-30, or an S1 / S2 split or test M (section 14) falls on
  any session from t+1 through it. Booked on the exit session (a stress-priced exit on t's next market session, or on t
  if that is on or after 2025-06-30). Each night held adds one locate charge. Flagged halted_close and counted by year;
  bars 6-8 also print without these trades (report).

## 6. Size, costs, locate, daily P&L and ROC @ $30k

- **Size at notional N:** shares = floor(min(N, 0.01 x ADV$) / entry), ADV$ from section 4 (sessions before t). No
  compounding.
- **Judged size N* (shared with RUNNER2 r1):** the smallest N on a $500 grid from $5,000 whose maxDD (that series, reading
  L, primary cost) >= $30,000; $500,000 if none. Each cell, and each null draw, solves its own N*. Shares are then fixed;
  every other reading of that cell re-prices the same shares. Every bar reads the series at N* (the judged series).
- **ROC @ $30k (judged)** = 30 x (net / years) / max(maxDD, 30,000) at N*: net a year in $k at a $30k own drawdown, under
  the 1% cap. maxDD on the cumulative daily P&L with the peak starting at $0; years = (2025-06-29 - 2016-07-01).days /
  365.25 = 3,285 / 365.25. The uncapped scale-free figure at $5,000 (30 x (net / years) / maxDD) prints beside it.
- **Capacity line (report, at N*):** share of trades where the cap binds; median entry-bar and stop-bar 1m dollar volume
  against the trade notional; the most names and the most gross short notional on one session.
- **Price bucket b:** lt5 = P < $5, 5to20 = P >= $5.
- **Spread base (shared with RUNNER2 r1; set from quotes BEFORE the P&L harness runs; section 16):** SIP NBBO quotes only,
  never IEX quotes, whatever feed the bars use. On each quotes_pmfail name-day, the NBBO in force at each whole second
  09:40:00..11:05:00 ET (skip bid <= 0, ask <= bid, or no quote yet); half-spread = (ask - bid) / (ask + bid); name-day
  value = median over seconds. h50(b), h75(b) = the median and 75th percentile of name-day values in bucket b. Used for
  both sides; the same statistic over 15:50:00..15:59:59 prints as a check on the exit side. A bucket with fewer than 20
  name-day values, or no quotes at all: h50 = 0.50% (lt5) / 0.25% (5to20), h75 = double (priors).
- **Per side, $ a share:** primary = max(h50(b) x price, $0.005) + $0.0035; stress = max(h75(b) x price, $0.005) + $0.01 +
  $0.0035. Half a tick is the floor: 50 bps a side at $1, 10 at $5.
- **Locate (no borrow data held):** primary 1% of entry notional a trade; stress 2%; one more charge per night held.
- **Trade net** = shares x (entry - exit) - shares x (cost side at entry + cost side at exit) - locate.
- **Daily P&L:** the sum of net booked that session (the exit session), $0 on every other session of the WF calendar
  (all daily-cache sessions 2016-07-01..2025-06-29). Session date = UTC date for 09:30-16:00 ET exits, so it joins #463's
  UTC-stamped index directly: reindex onto the book index with fill 0, appending leg days not in it.
- **Also:** Sortino = mean(daily) / sqrt(mean(min(daily, 0)^2)) x sqrt(252); t = mean / sd(ddof 1) x sqrt(n) over every
  WF session including zeros; PF = sum of winning trade nets / |sum of losing trade nets|.
- **Cost curve (report):** all-in 0 / 10 / 25 / 50 / 100 bps a side x locate 0 / 0.5 / 1 / 2%; break-even bps a side
  printed at locate 0 and 1%; break-even locate (the % a trade that takes net to zero) per price bucket. The 0 and 10 bps
  rows are below half a tick on sub-$5 names: gross references only.

## 7. The two cells

- **PRIMARY (judged): stop S1 = the day's high so far + $0.01.** A priori: the high is the level whose break says the
  failure failed and the squeeze resumed; it is the scope's own stop and needs no parameter.
- **NEIGHBOUR: stop S2 = entry + 1.5 x (S1 - entry).** A priori: a fraction of the trade's own risk is scale-free across
  $1-$20 names (a % of price ignores structure; ATR on event days is the event itself). Wider, not tighter: 1m bars misjudge
  tight stops (SIPORB: 48% hit inside the fill bar), and a stop under one LULD band (10%/20%) is often jumped by a pause.
- Same signal, entry, exit and costs. No cell is added after any number exists.

## 8. Reported, never cells

- OPENPRINT (rank 9): short every event day at the open of the first regular 1m bar (after a delayed open, the resume
  print); no stop; 15:55 exit; SSR-active at the open skipped; same size rule, costs, locate.
- Continuation mirror (PMBREAK, rank 7): long at the next 1m open after the first window 5m close > PMH; stop = the regular
  low so far - $0.01 (reading L); 15:55 exit; no locate.
- P >= $5 only (binds in bar 10).
- Float split (LOWFLOAT, rank 6): shares outstanding < 20M / >= 20M / unknown. Value = the dei EntityCommonStockSharesOutstanding
  fact (else us-gaap CommonStockSharesOutstanding) with the latest `filed` strictly before t; as-filed file first, frames
  file by CIK otherwise; rebased by the split factor: shares x F(filed) / F(t), F = raw / split close. Shares outstanding is
  only a proxy for float.
- Without: reverse-split-flagged days (condition 4); reused-ticker days (98 symbols listed twice in assets.csv; ~45 event
  days); delisted names; halted-into-close trades. With: the Rule-201-legal SSR fill (section 5); the S3p and S3v split
  readings (section 4); the 4-minute halt reading (section 12).
- Shortable today vs not, among names whose assets.csv rows are all active (today's Alpaca flag, a 10-03 snapshot; Alpaca
  shorts easy-to-borrow names only; inactive and ambiguous names apart): report only, never a filter.
- Placebo: the PMFAIL rules on the nonevent sample (section 16).
- The two-leg (with RUNNER2) Bonferroni reading: the null's 97.5th percentile beside the 95th.

## 9. Family null

- 500 draws, numpy.random.default_rng(20261006). Each draw: for each July-June year, pick as many event days as the primary
  has trades that year, uniformly without replacement from that year's event days with a PMH and >= 1 eligible bar; on
  each, one bar uniformly from its eligible window 5m bars (exists; has a fill bar that is not a halt resume bar; not
  SSR-active; fill-bar open < that bar's S1).
- Then the real rules from that bar on: entry at the next 1m open, S1 = max(PMH, regular high so far) + $0.01, S2 = 1.5x,
  reading L, primary costs and locate, 15:55 exit and the halted-into-close rule, sized at the draw's own N*.
- It keeps the habitat, the count, the year mix, the short side and the stops; it removes the failed-premarket-high
  condition (both day choice and timing).
- Statistics per draw: the max over the 2 cells of ROC @ $30k, of t, and of the sum over R's 762 days. p50 / p95 / p97.5
  print. Notion (b) power = p95 - p50 of the max-cell ROC.

## 10. Power line, count gate and what prints first

Before any real-direction run, in order, and filed to MANAGER:
1. Counts (counts.json): event days by year and bucket (registered rule, each filter's survivors, S3p, S3v); signals by year
   and by entry half-hour; skips (no PMH, no fill bar, resume bar, SSR-active at the open and intraday, immediate
   stop-through); filled trades of the primary by year; halts; halted-into-close exits; stop distance (S1 - entry) / entry
   in < 2 / 2-5 / 5-10 / 10-20 / >= 20%; conditions 1, 3 and 4 prints; LOWFLOAT buckets; share of event days in SIPORB's
   top 20 (r5_siporb's selection on its photographed cache).
   **Count gate:** bar 3 is checked here on filled-trade counts, before any P&L. A miss records PMFAIL r1 FAIL on counts and
   no return is computed.
2. Schedule overlap: trade days inside R's 762 days and #463's 460 drawdown days; shared days with each crown's trade days;
   same name-day overlap with RUNNER2 r1's filled trades.
3. Power line, notion (a), tools/power_line.py: a coin-flip leg on the primary's real schedule (same name-days, entry bars
   and shares at the primary's N*; side by default_rng(20261006); short = the primary rules; long = stop at
   entry - (S1 - entry), no locate; 15:55 exit; primary costs). cand = #463 mtm + k x coin-flip daily, twin = #463 mtm,
   with k = the vol c (section 18's formula applied to the coin-flip leg) and k = 30,000 / the coin-flip leg's own DD.
   `python tools/power_line.py --cand cand.csv --twin twin.csv --from 2016-07-01 --to 2025-06-29 --date-col date --pnl-col
   pnl_usd --block 20 --draws 1000 --seed 20261005`. It prints the SD and the 5% / 80% lines only.
4. The family null's p50 / p95 / p97.5 and notion (b).
Only then the real run.

## 11. MANAGER condition 1 - NAME THE FEED

- Registered: **feed=sip** for every bar the rules read. #39's premise ("the free feed is IEX-only") holds for REAL-TIME data.
  House evidence says free-plan HISTORY is full SIP: SIPORB's 19.96M 1m rows came back feed=sip; every repo caller passes
  feed=sip; docs\ALPACA_STOCK_BARS.md lines 16-20 states the plan (its line 154: no live call had been made from the repo);
  MANAGER's 10-02 key check returned status 200 on a SIP bars request (memory alpaca-stock-bars-staged.md; status codes
  only, no quotes). Omitting `feed` can default to IEX, so the pull names it and logs it per request.
- If the wrapper's SIP request is refused (403), or MANAGER rules IEX at review: every rule runs unchanged on feed=iex, and
  event days with no IEX premarket bar have no PMH and are skipped (counted). Spreads stay on SIP quotes or the priors.
- Printed, on every event day (IEX 1m bars 04:00-15:59 are pulled on every event row, section 16):
  - #39's test as worded: the share of event days whose IEX 04:00-09:29 1m volume is under 10% of the daily cache's volume;
    the same share on SIP; IEX / SIP volume, premarket and regular apart.
  - The IEX twin: share of days with IEX PMH < SIP PMH and the median gap in %; the share whose signal bar would differ,
    twice, labelled: all-IEX (PMH, 5m closes, HOD and stop from IEX bars) and hybrid (IEX PMH on SIP regular bars).
- Read: Stage A judges the SIP test. These prints bound how far a free-plan live line (IEX in real time, SIP 15 minutes
  late) departs from it; they move no bar, and the verdict line carries them.
- The owner's chart high differs from any vendor's (XHG ~18 on his chart vs 16.42 on Yahoo; CBU.md line 1332).

## 12. MANAGER condition 2 - HALTS

- Alpaca serves NO bar for a minute with no trade (r5_siporb.py line 505), so #39's "zero-volume bars" is read as: a run of
  >= 5 consecutive regular-session minutes each with no 1m bar or a v = 0 bar is a halt (shared with RUNNER2 r1). A run from
  09:30 (delayed open) or to the close counts. The resume bar is the first bar after the run.
- No entry on the resume bar (no trade, counted). A stop jumped by a halt fills at the resume bar's open. Halted into the
  close: section 5. Both stop readings (L and N) print.
- A single 5-minute LULD pause that starts mid-minute leaves only 4 empty whole minutes. Threshold 5 stays as ruled; the
  4-minute reading (every halt rule rerun with 4) is reported, and 4-minute runs print by time of day. No-trade lulls in
  thin names also read as halts; the time-of-day print shows it.

## 13. MANAGER condition 3 - SURVIVORSHIP

- The universe is the daily cache WITH delisted names (kept under their last Alpaca symbol; renamed names under today's
  ticker, e.g. FB's history under META). Shared definitions with RUNNER2 r1: delisted = last daily bar before 2026-06-01,
  the date read from the uncut cache (section 3's one exception); inactive = every assets.csv row for the symbol inactive
  (1,002 cached symbols); the 92 cached symbols with mixed rows print as ambiguous, for status and shortable flags alike.
  Printed: both shares of event days per July-June year.
- Stated hole: the exchange filter used TODAY's listing, so 16,297 inactive assets now on OTC are absent for their whole
  history; 66 X_DELISTED names and 454 universe names have no daily bar. Small caps that fell from Nasdaq to OTC are missing.
  The sign of the bias on an intraday short is unknown (prior).
- Reused tickers (98 symbols, one series may splice two companies) are flagged; a without-them reading prints.

## 14. MANAGER condition 4 - REVERSE SPLITS (flag shared with RUNNER2 r1)

- A name is FLAGGED on t if a reverse split falls on a session in [t - 60 calendar days, t - 1 day], from any of:
  (i) an S1 step with F / F' > 1.005; (ii) a calendar reverse_split ex_date, symbol-mapped as in section 4; (iii) test M.
- **Test M (missed split, causal):** session u is flagged when g = o(u) / c(u-1) > 1 has |g - 1| >= 0.25, g within 2% of a
  whole k = 2..50, and g x v(u) / median(v over the 20 sessions before u) within [1/1.6, 1.6] (a one-day form known at u's
  close, NOT TBIS's 20-session test). Calibration before the pull: on every S1 reverse-split session (F / F' > 1.005)
  in the WF window whose g is a whole ratio, the share the volume clause also flags prints (catch rate). Catch rate
  >= 0.90: M stands as written; else M drops the volume clause (price only) and the volume reading is reported.
- Flagged days stay in the cells; counts print by year with the agreement of the three sources, and the cells print
  without them (report). The split-gap guard is not shipped; the calendar covers only floor names from 2016-06-01, so
  sub-$5-only names rely on (i) and (iii).

## 15. Stage A bars (WF 2016-07-01..2025-06-29 only, no lockbox read; the primary's judged series at N*, reading L, primary cost unless stated)

1. ROC @ $30k (judged) >= 15, OR the earner route: ROC >= 5 AND the daily P&L summed over R's 762 days > 0 AND still > 0
   without its 3 best R days AND above the null's p95 of the max-cell R-sum. (#463's 460 days print as a report.)
2. PF >= 1.05.
3. >= 100 WF trades and >= 50 filled trades in EVERY July-June year (the scope's reading, SCOPE_DISC line 85), unless
   MANAGER rules in writing before GO that ">= 50 a year" means a 9-year mean (>= 450) house-wide (Q3). Checked by the count
   gate (section 10); a year with < 50 event days fails it from the daily cache, before the pull.
4. >= 6 of 9 July-June years net positive (2016-17 = 2016-07-01..2017-06-30, ..., 2024-25 ends 2025-06-29).
5. t >= 2.0, and both t and ROC above the null's 95th percentile of the family max.
6. Net > 0 at stress cost (h75 spread + $0.01 + 2% locate) under BOTH stop readings L and N.
7. Net > 0 without its best day, and without its best trade.
8. Net > 0 without 2020-02-15..2020-04-30, and without calendar 2020-21 (2020-01-01..2021-12-31; binding for stock legs).
9. The neighbour cell's net > 0.
10. Tradable subset: the trades with P >= $5 have net > 0 at stress cost and PF >= 1.05 (SCOPE_DISC line 336: a result that
    needs sub-$5 shorts nobody will lend is not tradable).

## 16. THE ONE PULL SPEC (shared; RUNNER2 r1 section 4 mirrors it)

- **Builder:** tools/disc_gapper_namedays.py, after GO, the only builder, from the photographed daily cache and the
  corporate-actions file (shas in section 3), dates 2016-07-01..2025-06-29 only. The pull does not start before PMFAIL r1
  and RUNNER2 r1 are both written and MANAGER has ruled Q3 (a leg that fails bar 3 from the daily cache has its columns all
  0).
- **File** C:\EdgeLog\alpaca_cache\disc_gapper\namedays_r1.csv: one row per (symbol, date); a name-day in several roles is
  one row. Columns, in order: symbol, date (YYYY-MM-DD, ET session), wf_year (2016-17..2024-25), price_bucket (lt5 / 5to20,
  from the raw close of the market session before date), pmfail_event, runner2_d2, nonevent, runner2_nonevent,
  quotes_pmfail, quotes_runner2 (each 0/1). UTF-8, LF, header row, sorted by date then symbol, no index column.
- **Roles, built in this order:**
  - pmfail_event: section 4's event days plus the carry-over-SSR days section 4 removes (the SSR report reads them).
  - runner2_d2: RUNNER2 r1's day-2 sessions under its loosest reported reading (RUNNER2 section 4), so every reported
    reading has bars.
  - nonevent: per (wf_year, price_bucket) stratum, as many rows as section 4's registered events. Pool = name-days passing
    every section-4 filter except the gap, with 0.95 <= O/P < 1.05, and in no earlier role. default_rng(20261006).
  - runner2_nonevent: per stratum, as many rows as RUNNER2's registered events. Pool = (s, D2) passing every RUNNER2
    section-2 filter except the run, with 0.95 <= c(D1) / c(D0) <= 1.05, in no earlier role. default_rng(20261009).
  - quotes_pmfail: 10 per stratum from section 4's registered events (up to 180). default_rng(20261007).
  - quotes_runner2: 10 per stratum from RUNNER2's registered events (up to 180). default_rng(20261008).
  - **Draw procedure (every sampled role):** a fresh generator per role; strata in order wf_year ascending, lt5 then 5to20;
    pool sorted by (date, symbol); if len(pool) <= n take all, else idx = rng.choice(len(pool), size=n, replace=False);
    take pool rows at sorted(idx).
- **What the pull fetches (no asof anywhere; times ET, sent as UTC RFC-3339):**
  - Every row: GET https://data.alpaca.markets/v2/stocks/bars, timeframe=1Min, adjustment=raw, feed=sip, sort=asc,
    limit=10000, 04:00:00-15:59:59 (bars starting 04:00..15:59). Fields kept as served: t, o, h, l, c, v, n, vw.
  - Rows with pmfail_event or runner2_d2 = 1: the same request with feed=iex.
  - quotes_pmfail rows: GET https://data.alpaca.markets/v2/stocks/quotes, feed=sip, sort=asc, limit=10000, every page,
    09:30:00-11:10:00 and 15:50:00-16:00:00.
  - quotes_runner2 rows: at each mark m of 09:45, 10:00, 10:30, 11:00, 11:30, 12:00, 13:00, 14:00, the same endpoint with
    feed=sip, start = m - 60 s, end = m, sort=desc, limit=1 (the NBBO in force at m; if desc is refused, the window asc and
    its last quote).
- **Hash:** namedays_r1.sha256 next to it, `sha256sum` format (hex, two spaces, file name), posted to MANAGER's inbox with
  per-role counts by wf_year. The pull's manifest cites this sha.

## 17. Data provenance

- ONE pull through MANAGER's wrapper (C:\EdgeLog\manager\_scripts\with_alpaca_keys.py loading the keys; the fetch script
  calls alpaca_rate.wait() before every request and is added to tests\test_alpaca_rate.py). First, the FB/META probe of
  r5_siporb.py (2019-01-02; it tests 1Day and 5Min only) extended to 1Min feed=iex bars and to /v2/stocks/quotes feed=sip:
  each endpoint must print "SAME MAPPING" (FB history under META), logged in the manifest; any other result stops the pull.
  Then a 3-name-day probe (premarket bars present, feed echoed, quote pages per name-day, sort=desc served).
- Raw pages saved byte for byte with sha256; pull_provenance receipts for bars; a manifest (file, bytes, sha256) with its
  own sha. Research cache outside git; never library masters.
- Photographed once, never patched. A missing name-day stays missing (counted). A re-pull is a new photograph that MANAGER
  names; the verdict reads one photograph only. The driver checks every input sha against section 3 and the manifest
  before computing and refuses on a mismatch.

## 18. Diagnostics (reported with the verdict, both stop readings)

- Event-time path: mean short P&L in bps of entry by minute, -30..+390 around entry; the premarket path from 04:00 (price
  / P by minute) for traded and untraded event days; daily open vs the 09:30 1m open within 1 cent (share).
- Halves 2016-07-01..2021-12-31 / 2022-01-01..2025-06-29; per July-June year: trades, net, mean notional, realised cost bps.
- P&L in each of R's 45 episodes and #463's 28 (episodes.csv); correlation of daily P&L with #463's legs (book463_daily
  L0..L3_mtm) and RES (line.csv res_c), all days and on R's days.
- RUNNER2 link: the same-name link across days (PMFAIL name traded day 2 next session); the same name-day overlap of
  filled trades (both legs short one name on one session), their joint P&L and P&L correlation; on those name-days the
  combined position against one 1% cap and one locate.
- Top-10 share of net (trades and days); without best day / best trade; no-2020, no-2020-21, no-2022.
- Cost curve, break-even bps and break-even locate (section 6); the capacity line.
- Book add (house line #45, report): c = 0.25 x sd(#463 mtm) / sd(leg), both over 2016-07-01..2018-06-30 on the book index;
  (#463 + c x leg) vs #463 (93.81 / 3.816), and (L + c x leg) vs L = #463 + 0.264 x RES (120.82 / 3.916); at c, 0.5c, 2c
  and the $30k-own-DD twin (the judged series); paired bootstrap p5 for each.

## 19. What could fool us

- Squeeze tails: event-day returns are right-skewed, so a short can look fine until one name doubles; top-10 shares, the
  best-trade bar, reading N and the halted-into-close rule cover it.
- Meme years: 40% of events are in 2020-21; that read binds.
- Tradability: sub-$5 names may be unlendable (bar 10 binds on P >= $5); shortable flags are today's only; locate is a
  guess (1% / 2%; break-even locate prints). Size beyond the 1% cap is not judged (N*).
- Feed: the test sees SIP; a live free-plan line sees IEX in real time (condition 1's twin).
- Halts vs lulls: missing-bar runs mix LULD pauses with no-trade minutes (condition 2's prints).
- Splits: a missed split on t stays in (honest P&L, diluted event set); S1 relies on a pre-correction split file; S3p / S3v
  print both ways.
- Survivorship: the OTC hole and today's-ticker mapping (condition 3).
- Peeking: PMH uses bars before 09:30; HOD and the trigger only bars closed by the signal; SSR only regular prints known
  then; float only filings strictly before t; the 1% cap and ADV$ only prior sessions; split removal only actions public
  before the open. S3v reads t..t+19 and is a labelled look-ahead report.
- The null shares the short side: it tests the trigger, not "short gappers"; OPENPRINT is that control.
- Reading a failure as a verdict on his eye: this tests the inverse of his setup, not his setup.

## 20. PASS / FAIL and what follows (shared with RUNNER2 r1)

- **PASS** = bars 1-10 all hold. The engine has no multi-stock job type (PREREG_ALPACA_R1.txt line 48), so the registered
  route, pending MANAGER's ruling before GO (Q6), is SIPORB's Stage C form: a forward no-order shadow line with its own bar
  and an owner call, computed on SIP 15 minutes late or IEX real time (condition 1's gap), with the broker and locate
  source named by MANAGER before any order (Alpaca shorts easy-to-borrow names only; WEBULL_GO_LIVE.md 2.3). A plugin with
  harness parity and a window-pinned Auto-Validate (900 trials) replace it only if a stock job type is built first. Stage
  B: a one-read veto on the sealed stock year 2025-06-30..2026-06-30, through its own MANAGER pull, excluding the 18 sheet
  name-days. A RUNBOARD row the same day.
- **FAIL** = any bar misses, including the count gate: dead, no variants, a ledger row and a RUNBOARD research row under
  MISC (PMFAIL).

## 21. Files the driver writes

- tools/pmfail_r1_stageA.py (after GO). Outputs in C:\EdgeLog\_anatomy_cache\disc_pmfail_r1\:
  - counts.json (step 1), overlap.json (step 2), power.json (step 3), null.json (500 draws x 3 statistics);
  - stage_a.json: bars, verdict, N*, reports, diagnostics, the sha256 of every input and of this prereg (LF-normalised);
  - trades.csv: symbol, date, exit_date, cell, reading, signal_end, entry_time, entry, stop, exit_time, exit, shares,
    notional, gross, cost, locate, net, flags (ssr, resume, halted_close, revsplit, reused, delisted, bucket);
  - daily.csv: date, cell, reading, pnl_usd; coinflip_daily.csv (the power-line input).
- tools/disc_gapper_namedays.py writes namedays_r1.csv, namedays_r1.sha256 and namedays_r1_counts.json (section 16), with
  the filter-survivor counts and test M's calibration for both legs.

## 22. Questions for MANAGER (before GO)

- Q1: confirm feed=sip (condition 1), with feed=iex as the stated fallback.
- Q2: halt threshold 5 as ruled, the 4-minute reading reported: confirm.
- Q3: ">= 50 a year": every year (the scope's reading, registered by default) or a 9-year mean, ruled house-wide. The lane
  does not choose.
- Q4: the 97.5th-percentile two-leg reading stays a report, or binds?
- Q5: confirm the free plan serves historical SIP quotes (and sort=desc); else the cost priors in section 6 apply.
- Q6: the stock-leg PASS route (section 20), written identically into both preregs.
