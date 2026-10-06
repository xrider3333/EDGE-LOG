# PREREG - RUNNER2 r1 (day 2 of a small-cap runner, short; SCOPE_DISC rank 3) - DRAFT for MANAGER review (2026-10-06)

Written before any intraday bar of the habitat was pulled (SCOPE_DISC 87ac032c, MANAGER #39). No return of any kind has
been read. The only numbers below are session COUNTS from the daily cache, or figures already published in house docs.
Research id: **MISC-RUNNER2-r1** (stays under MISC until something passes). Lane: DISCRECTIONALRY-TO-ALGO.
Harness (written only after GO): `tools/disc_runner2_r1_stageA.py`. Code waits for GO; this draft may go on main
labelled DRAFT. Revised 2026-10-06 after the instrument / rules / tradable review, before any pull.

**Shared pull.** RUNNER2 shares PMFAIL r1's single pull
(`C:\Users\xride\AppData\Local\EdgeLog-worktrees\disc-gapper\docs\PREREG_pmfail_r1_2026-10-06.md`). The one pull spec
(list file, roles, draws, fetch windows, probes) is written once, in PMFAIL r1 section 16; section 4 here restates
RUNNER2's part of it. The two drafts agree on feed, windows, fields, mapping, halts, SSR, the reverse-split flag, sizing,
costs and the PASS route; nothing is left for MANAGER to reconcile. The pull does not start before both preregs are
written.

**Disclosure.** The author has seen the owner's 12 stock CBU charts (setups/CBU.md). They are dated 2026-07-07..09-04,
after the cache end and outside every test window. None is recorded as a day-2 trade, and all 12 are longs. The 18
sheet-only trades (2025-11-11..2026-03-10) fall inside the unread stock sealed year (2025-06-30..2026-06-30). If that
year is ever read for this leg, those 18 name-days are excluded (precedent: ALGO_SCOPE.md lines 148-151).

## 1. Question and mechanism

Does shorting day 2 of a small-cap runner (a stock that closed at least 40% up) earn after costs, once the day-2 tape
gives back its VWAP, at the size the capacity cap allows? The judged population is signals not under Rule 201 (section 6).

- **Barber, Huang, Odean & Schwarz (2022, JF; SSRN 3715077).** After Robinhood herding events, the decline sits in day
  +1..+5 OPEN-TO-CLOSE returns, not overnight. Extreme events: day +1 open-to-close -1.23% against an insignificant
  -0.18% overnight. The effect holds only in caps under $1B, holds on quote midpoints, and is strongest after March 2020.
  - It is the a-priori source of the 40% threshold: the extreme-herding group's mean day-0 return is +41.86%.
  - It supports the UNCONDITIONAL day-2 short. The VWAP trigger is not in the paper; it is reported against that
    control (section 9).
- **Berkman, Koch, Tuttle & Zhang (2012, JFQA).** Attention measured on the PRIOR day predicts a high open and an
  open-to-close reversal the next day, strongest in about the first hour, in hard-to-value, costly-to-arbitrage names.
  Its largest published intraday reversal (0.4-0.7%) is about this leg's round-trip cost.
- **Barber & Odean (2008, RFS).** Shows only that individuals BUY attention-grabbing stocks. It does not test returns;
  the reversal is a conjecture (p. 813). It is cited here for the mechanism (who buys), not for size or horizon. (This
  corrects SCOPE_DISC row 1's wording.)
- **Miller (1977, JF).** Short-sale limits let prices reflect the optimists. The same limits (locates, Rule 201) make
  the short costly. It explains why the effect could exist, not why the trade nets out.
- **Avramov, Chordia & Goyal (2006, JF); Nagel (2012, RFS).** Short-run reversal is largest in illiquid names and is the
  return to providing liquidity. Avramov et al. find it is smaller than likely costs: this is cost counter-evidence.
  Nagel's reversal applies to non-informational moves, while +40% small-cap runs are mostly news or promotion (Chan 2003:
  news moves drift).

**What differs from the dead rows (RESEARCH_LEDGER.md lines 102-105):**
- **ATTN 2.61** is the key line. In the house's only measurement of this horizon, the next-day open-to-close of SIPORB's
  stocks in play (over $5 and $5M ADV, chosen by relative volume in either direction) was -1.5 bps, about zero.
  RUNNER2 instead trades day 2 after a >= +40% close at a $1-$20 price with $1M ADV, short only, on a VWAP trigger with
  a stop.
- **DDW L1 2.62.** A weekly reversal in the 500 largest no-news names, dollar-neutral: +$94,528 at 5 bps, break-even at
  10 bps, long beta in a crash. RUNNER2 holds one day, is short only and single-name, and does not exclude news.
- **XGAP 2.63** traded day 0 of large-cap gaps (gross about zero). RUNNER2 trades the session after a small-cap run.
- **RESREV** (SCOPE_STRATEGY-BEATING) is a parked prior, not a dead result.

**Prior (written before any return; SCOPE_DISC row 3).** ROC -15..20, median -1; P(ROC >= 5) 15%, P(ROC >= 15) 5%;
P(Stage A pass) ~4%; prior t median ~0.3.

**Dollar prior** (standing order 10-04 item 4; arithmetic, not data):
- Assume ~90 trades a year at $5,000, with a per-trade SD of ~$350. The annual SD is then ~$3,300 and the own drawdown
  ~$4-5k, so a $30k own drawdown means ~6-7.5x, ~$30-37k a trade, where the 1% cap binds often: ROC is judged at the
  capped size N* (section 7).
- ROC 15 then needs ~$2.2k a year net at $5,000, about $25 a trade: 0.5% of notional net. At $5, base cost on the fallback
  priors is ~0.64% round trip + 1% locate, so that is ~2.1% gross.
- So the trigger must do about as well as BHOS's published unconditional day +1 effect, after cost. Plausible, unlikely.

## 2. Universe and event filter (exact)

**Source:** `C:\EdgeLog\alpaca_cache\siporb\daily_raw.parquet`. Columns symbol, date (ET session date at midnight), o, h,
l, c, v. Raw (unadjusted), SIP. 11,449,264 rows, 6,596 symbols, 2016-01-04..2026-06-30.
- **Universe:** every symbol in the cache, active and delisted, as SIPORB's pull built it (r5_siporb.py universe code;
  BAD_NAME regex lines 85-86). RUNNER2 adds no share-type filter of its own. The harness re-applies r5_siporb's share-type
  filter to assets.csv names and prints the count dropped (expected 0).
- **Market calendar:** the distinct dates in the cache (2,637 sessions). Half days (EARLY_CLOSE_DATES,
  tools/import_alpaca_stocks.py lines 139-145) are skipped as day 2 and counted.
- **Cut:** cache rows dated on or after 2025-06-30 are dropped on load, before anything is computed. One exception:
  condition 3 reads each symbol's last-bar DATE from the uncut cache (no price or volume).

**Days.** For symbol s, D2 is the trade session; D1 is the market session before it (the run day) and D0 the one before
that. All prices and volumes below are raw daily-cache values. Daily volume includes extended-hours trades (house count
check: 2-14% above the regular-session 1m sum); daily h / l are regular-session values (PMFAIL r1 section 3).

**A day-2 session (s, D2) is an event when ALL hold:**
1. **WF window:** 2016-07-01 <= D2 <= 2025-06-29, and D2 is not a half day.
2. **Bars present:** s has a daily bar on every one of the 20 sessions D0-19..D0, and on D1 and D2.
3. **The run:** c(D1) / c(D0) >= 1.40.
4. **Price band:** $1.00 <= c(D0) <= $20.00 AND $1.00 <= c(D1) <= $20.00.
   - The band on c(D0) is "filters as rank 1" on the run day.
   - The band on c(D1) is the day-2 prior close: spread, tick and locate depend on the price actually traded.
5. **Liquidity:** ADV$ = mean of c(t) x v(t) over t = D0-19..D0 >= $1,000,000.
6. **Split removal.** None of the following:
   - **(S1) Vendor split** on D1 or D2 (PMFAIL r1's S1). For session t, F = raw open / split-adjusted open on t, and
     F' = raw close / split close on the session before t (daily_split.parquet). Split session if |F / F' - 1| > 0.005.
     F / F' > 1 means a reverse split; < 1 a forward split.
   - **(S1c) Calendar split** on D1 or D2 (PMFAIL r1's S2): a forward_split, reverse_split, unit_split or stock_dividend
     row in corporate_actions_wide.csv, symbol-mapped to today's ticker through the name_change chain and unit_split
     joined on new_symbol, exactly as PMFAIL r1 section 4.
   - **(S2) Unrecorded split on D1** = PMFAIL r1's test M (section 14 there) on u = D1: g = o(D1) / c(D0) > 1,
     |g - 1| >= 0.25, g within 2% of a whole k = 2..50, and g x v(D1) / median(v over D0-19..D0) within [1/1.6, 1.6]. This
     one-day form is NOT TBIS's 20-session test (that reads D1..D1+19, after the trade). Its calibration (catch rate on
     vendor-known splits, >= 0.90 or the volume clause is dropped and reported) runs in the builder before the pull.
7. **No carry-over Rule 201:** l(D1) > 0.9 x c(D0) (section 6; known before 04:00 on D2). Removed sessions are counted.

**Why this split rule.** Dollar volume (c x v) does not change across a split. A split corrupts the quantities computed
on D1: the +40% ratio and the band. A missed split ON D2 cannot fake the run; the D2 trade uses D2 bars only, so its P&L
is honest; it can only mis-set the SSR reference and the bucket, so its price-only test S2' (|g2 - 1| >= 0.25, g2 =
o(D2) / c(D1) within 2% of k or 1/k, k = 2..50) is a REPORT (it selects on move size), in line with PMFAIL r1's S3p.
- The scope's plain whole-ratio guard removes real runners whose move lands near +100% or +200%: in a first pass, 74 of
  ~2,057 run candidates, 62 of them on >= 10x volume. The volume clause keeps those, because a real split moves volume
  inversely to price.
- k runs to 50 because split_like_gaps stops at 20 and sub-$5 reverse splits run 1:25..1:100 (SIPORB's scan uses k <= 50).
- daily_split is a mixed 10-03/10-04 photograph from before the GE re-adjustment. It is used ONLY for F, to detect split
  sessions, never for prices. A stale base level does not hide an F step.

**Counts.**
- The builder prints the exact count under this rule first, each filter's survivors in order, per July-June WF year
  2016-17..2024-25. Earlier readings, each with a different and partly undeclared split rule:
  - Scope (SCOPE_DISC line 98): 41 / 55 / 52 / 195 / 260 / 137 / 143 / 161 / 349 = 1,393 (band on c(D0), plain
    whole-ratio guard).
  - Reader, band on both closes: 47 / 62 / 65 / 258 / 321 / 184 / 171 / 211 / 459 = 1,778.
  - Reader, band on c(D0) only: 53 / 75 / 72 / 277 / 368 / 208 / 193 / 232 / 503 = 1,981.
- **Reported counts, never the event set:** band on c(D0) only; the scope's whole-ratio guard without the volume test;
  S2' on; S1/S1c/S2 widened to the 20-session window D0-19..D2; carry-over SSR kept.
- **Links to PMFAIL:** 170 of 1,981 day-2 sessions are also PMFAIL event days (D2 open >= +20% over c(D1)), so both legs
  can short the same name on the same session; 908 of 1,985 runs opened >= +20% on D1 (linked across days). The same
  name-day overlap of filled trades prints (section 11).

## 3. MANAGER condition 1 - THE FEED (named)

- **Historical bars: feed=sip** (the consolidated tape) for every bar the rules read.
  - MANAGER #39 (1) says the free Alpaca feed is IEX-only. House evidence says that holds for REAL-TIME data only.
  - Historical bars on the free plan come from SIP: SIPORB's 19.96M 1m rows came back with feed=sip;
    docs\ALPACA_STOCK_BARS.md lines 16-20 and tools/import_alpaca_stocks.py lines 4-7 state it; MANAGER's 10-02 key check
    returned status 200 on a SIP bars request (memory alpaca-stock-bars-staged.md; status codes only, no quotes).
  - Every request names feed=sip explicitly. An unsubscribed account that omits `feed` defaults to IEX.
  - The wrapper logs the feed in every receipt. A refused sip request is never silently replaced; the fallback is
    below.
- **IEX is named for two uses.**
  - (a) The live constraint. A forward or live line on the free plan sees only IEX in real time (SIP arrives 15 minutes
    late). So a live VWAP and 5m close would be IEX-built.
  - (b) A diagnostic twin: every runner2_d2 row is also pulled on feed=iex, 1m, 04:00-15:59 (PMFAIL r1 section 16).
- **Printed, before any P&L, over all event day-2 sessions:**
  - Condition 1 as worded: the share of sessions whose IEX 04:00-09:29 volume is under 10% of the daily cache's D2 volume;
    the same share with SIP.
  - IEX volume as a share of SIP volume, premarket and regular session apart;
  - the share of sessions where the all-IEX primary trigger (IEX VWAP and 5m closes) fires on the same 5m bar as SIP's;
  - the median |IEX VWAP - SIP VWAP| in bps at the SIP signal bar.
  - Read: Stage A judges the SIP test; these bound the gap to a free-plan live line, move no bar, and ride on the verdict.
- RUNNER2 does not use the premarket high, so the IEX-understated-high problem does not touch its trigger. It does touch
  VWAP and the 5m closes, which is why the primary feed is SIP.
- **Fallback, as in PMFAIL r1:** if the SIP request is refused (403), or MANAGER rules IEX at review, every rule runs
  unchanged on feed=iex and the result is labelled IEX throughout. Spreads stay on SIP quotes or the priors, never IEX
  quotes. The lane's view: a VWAP built on ~2.5% of volume is a different instrument, so an IEX verdict speaks only for an
  IEX-fed live line.

## 4. Bar source, the shared pull, and provenance

**RUNNER2's part of the one pull spec (PMFAIL r1 section 16 governs; restated here):**
- **File:** `C:\EdgeLog\alpaca_cache\disc_gapper\namedays_r1.csv`, built by tools/disc_gapper_namedays.py (the only builder;
  RUNNER2 has no list mode). One row per (symbol, date); price_bucket = lt5 / 5to20 from c(D1). RUNNER2's 0/1 columns:
  - **runner2_d2:** every day-2 session under the LOOSEST reported reading (band on c(D0) only, S1 and S1c removal only,
    carry-over SSR kept), so every reported reading has bars: ~2,000 name-days, ~1,800 not already pmfail_event.
  - **runner2_nonevent:** the placebo's matched sample: per (wf_year, price_bucket) stratum, as many rows as the registered
    events, from (s, D2) passing every section-2 filter except the run, with 0.95 <= c(D1) / c(D0) <= 1.05, in no earlier
    role. default_rng(20261009).
  - **quotes_runner2:** 10 registered events per stratum (all if fewer; at most 180). default_rng(20261008).
  - Draws follow PMFAIL r1 section 16's procedure exactly (fresh generator per role; strata wf_year ascending, lt5 then
    5to20; pool sorted by (date, symbol); rng.choice(len(pool), size=n, replace=False); rows at sorted(idx)).
  - No date on or after 2025-06-30. If MANAGER rules the per-year count reading (bar 4), these columns are all 0.
- **Bars:** GET https://data.alpaca.markets/v2/stocks/bars, timeframe=1Min, feed=sip, adjustment=raw, sort=asc,
  limit=10000, no `asof` (today's ticker, as the daily cache: FB history sits under META), 04:00:00-15:59:59 ET on every
  row; the same with feed=iex on runner2_d2 rows. The pull first runs the FB/META probe on 1Day, 5Min, 1Min feed=iex and
  quotes, each printing "SAME MAPPING" (PMFAIL r1 section 17).
- **Fields stored per bar:** t, o, h, l, c, v, n, vw.
- **Stamps:**
  - `t` is UTC at the bar's START. Convert with the tz database to America/New_York; minute m = minutes after ET
    midnight.
  - The premarket is 04:00-09:29; the regular session is 09:30-15:59.
  - Alpaca returns NO bar for a minute with no trade. A bar with v = 0 is treated as missing.
- **5m bars from 1m:** bar k (k = 0..77) starts at 09:30 + 5k and covers the 1m bars starting in [start, start + 5 min).
  - o = the first present 1m open; h = the max high; l = the min low; c = the LAST present 1m close; v = the sum.
  - A 5m bar with no present 1m bar does not exist.
  - A 5m bar is known at start + 5 min (its "close time").
- **Quotes (quotes_runner2 rows):** at each mark m of 09:45, 10:00, 10:30, 11:00, 11:30, 12:00, 13:00, 14:00 ET, GET
  https://data.alpaca.markets/v2/stocks/quotes, one symbol, feed=sip, start = m - 60 s, end = m, sort=desc, limit=1.
  - **Statistic:** the NBBO in force at m (the last quote at or before m). hs = (ap - bp) / (ap + bp). Drop marks with no
    quote in the minute, ap <= 0, bp <= 0 or ap <= bp.
    - Name-day value = the median hs over that session's valid marks.
    - Per price bucket b (lt5: c(D1) < $5; 5to20: c(D1) >= $5), h50(b) and h75(b) = the median and 75th percentile of
      the name-day values: PMFAIL r1's in-force rule and aggregation, at RUNNER2's marks.
    - A bucket with fewer than 20 name-day values uses the fallback priors (section 7), as in PMFAIL r1.
  - MANAGER confirms with a probe that the plan serves historical SIP quotes (and sort=desc). If not, costs stay at the
    priors (section 7).

**Provenance:**
- **One pull** through MANAGER's wrapper (`C:\EdgeLog\manager\_scripts\with_alpaca_keys.py` runs the fetch script).
  - Keys come from augur_engine\alpaca_keys.py.
  - alpaca_rate.wait() is called before EVERY request (180 a minute, shared by the account), and the script is added to
    tests\test_alpaca_rate.py's wiring list.
  - Retries follow r5_siporb._get. Output goes to a research cache outside git; library masters are never registered.
- **The photograph:**
  - Every response page is saved byte for byte, with its sha256, in a manifest. The manifest's sha256 is the
    photograph's id.
  - Bar pages also get pull_provenance receipts. Quote pages cannot: content_hash covers OHLCV only.
- **Never patched.** A request still failing after retries is listed in the manifest as missing and counted as "no
  bars". It is never filled later. A re-pull is a new photograph and needs a MANAGER line, and every number is re-run.
  Alpaca re-adjusts between pulls (memory edgelog-alpaca-split-gap.md); raw bars are requested so the adjustment cannot
  move.
- **Pinned inputs.** The harness re-hashes every input and stops on any mismatch. All hashes print into stage_a.json:
  - daily_raw.parquet fa42412d579ae673815bea25e1c14f9c87a93904af779ccffb03333c8e1bdccd
  - daily_split.parquet 083f8c23d1d62cf7bda99d5c9a6373130c336ac605f57db5eeac832504281f6d
  - assets.csv b85928ff655a883dd3eb44d8d96b3b745ffe2f5f0e0ca0991485895f5e960991 (cache manifest 380b05f2e0c4dfa32faabf2c86311f869d7371d3810a801bbf8a6c1f9ade4b78)
  - corporate_actions_wide.csv e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5
  - q19 residual_days.csv bfe64d87a2cf6fd569181ffae9092317653844126de075fe64844430ac189f60
  - q19 a2.json 0c27cb47fe245cd8fbbcc1bc3eb0881ea0edefba74d45b7821a059dc7e4c9214
  - q19 line.csv 98f3edc743625b3742f13a972cab35178658feaa7f506e56e27f77f56e9c38ad
  - q19 episodes.csv ebfb67c03a258a0d4efe73a20a2c7027fd5eb3d25403f17d8e071cb4626a9af4
  - book463_daily.csv d1543735b5408f50be5971089e00a800f8e510af3d4a63678ff8939f41277dff
  - VIX_History.csv 6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a
  - namedays_r1.csv (its posted sha256) and the new pull's manifest

## 5. MANAGER condition 2 - HALTS (shared with PMFAIL r1)

- **Definition.** A halt is a run of >= 5 consecutive regular-session minutes (09:30-15:59) with no present 1m bar. This
  restates MANAGER's "zero-volume bars", because Alpaca returns no bar for a minute with no trade.
  - A run may start at 09:30 (a delayed open) or reach the close.
  - The **resume bar** is the first present bar after a run.
  - Thin minutes cannot be told apart from real halts without a halt feed. Both count.
- **No entry on the resume bar.** If the entry bar (section 6) is a resume bar, that name-day has no trade.
- **A stop jumped by a halt** fills at the resume bar's open: the bar opens at or through the stop.
- **Halted into the close.** No present bar in the exit window 15:55-15:59 is, by the definition above, a halt run open at
  the close. Exit at the raw open of s's first daily-cache bar within the next 10 market sessions after D2 (ATTN r1's rule,
  PREREG_ATTN_R1.txt line 44), in both readings. Stress price instead, max(the cell's stop, the last pre-halt 1m close),
  when no such bar exists, it falls on or after 2025-06-30, or an S1 / S1c split or test M falls on any session from
  D2+1 through it. Booked on the exit session (a stress-priced exit on D2's next market session, or on D2 if that is
  on or after 2025-06-30). Each night held adds one locate charge. Flagged halted_close and counted by year; bars 7-9
  also print without these trades (report).
- **Both stop readings print**, stop-at-level (L) and next-bar (N), defined in section 6.
- **4-minute reading (report):** a single 5-minute LULD pause that starts mid-minute leaves only 4 empty whole minutes, so
  every halt rule also reruns with 4; 4-minute runs print by time of day.
- **Printed:**
  - halt runs per session;
  - run lengths: 4 / 5 / 6-9 / 10 / 11-30 / > 30 minutes (a single LULD pause shows as 4 or 5);
  - signals lost to resume-bar entries;
  - stop exits on a resume-bar open;
  - halted-into-close exits, by year and by how they were priced.

## 6. Trigger, entry, stop, exit (exact)

All on D2, from SIP raw 1m bars.

- **VWAP**, anchored at 09:30 and computed after each present regular-session 1m bar j:
  VWAP_j = sum(p_i x v_i) / sum(v_i) over present bars i from 09:30 through j.
  - p_i is the bar's `vw`; (h + l + c) / 3 when vw is missing or <= 0. The share of fallback bars is printed.
  - The premarket is excluded: it is thin and feed-specific.
  - VWAP at a 5m bar = VWAP through that 5m bar's last present 1m bar.
- **Trigger (primary).** Scan the 5m bars k = 0, 1, 2, ... in time order, keeping a flag `seen_above`.
  - Set `seen_above` when a 5m close >= its VWAP.
  - The signal bar B is the FIRST 5m bar that meets all three:
    - its close time is in [09:45, 14:00] (k = 2..53);
    - c5(B) < VWAP(B);
    - `seen_above` was set by a strictly earlier 5m bar.
  - **Why the cross is required:** without it, every name already below VWAP at 09:45 becomes the unconditional open
    short delayed by 15 minutes, and the primary collapses into its own control. The no-cross version is reported.
  - **Why 09:45:** the end of LULD's doubled-band opening window; VWAP after one or two bars is only those bars.
  - **Why 14:00:** it leaves ~2 hours of the open-to-close horizon BHOS measure, and stays clear of the doubled closing
    bands from 15:35.
  - Berkman puts the reversal in the first hour, which this window partly misses. Trigger times print by half hour (a
    count).
- **Entry (short), at the next bar's open.** The entry bar is the first present 1m bar with start in
  [B close time, B close time + 4 min].
  - E = that bar's open (raw).
  - No trade if any of these holds; each is counted:
    - no such bar;
    - the entry bar is a resume bar (section 5);
    - Rule 201 is active at the signal (below);
    - E >= S (the open is already through the stop).
  - **One trade per name per day.** Only the first signal counts. A blocked signal does not re-arm.
- **Rule 201 (SSR), shared with PMFAIL r1.** Rule 201 is triggered only by regular-session (09:30-16:00)
  last-sale-eligible prints, then applies for the rest of that day and all of the next, premarket included (SEC Rule 201
  FAQ 1.1, 1.2, 2.1). Proxy, both halves regular-session, reference = the prior official close (daily cache):
  - carry-over: l(D1) <= 0.9 x c(D0). Known before 04:00 on D2, so such sessions leave the event set (section 2, item 7).
  - same day: any D2 regular 1m low from 09:30 up to B's close time <= 0.9 x c(D1).
  - Primary = skip, no re-arm: the modelled fill is a marketable short, which Rule 201 bars at or below the national best
    bid.
  - Printed per year before the count gate: SSR at the open (the 09:30 1m low; reader count ~458 of 1,902 sessions open
    at <= 0.9 x c(D1)), intraday SSR before B, carry-over removals, and the 04:00 reading (premarket lows included, an
    over-mark).
  - Report: the Rule-201-legal fill on every SSR-active signal, carry-over sessions included: a short limit at c5(B) +
    $0.01 posted at B's close time, filled at the limit only if a 1m bar starting in [B close time, B close time + 5 min)
    has high >= limit + $0.01; no fill = no trade; then the cell's stop and exit, base and stress cost.
- **Stop levels**, fixed at the fill and never moved:
  - **Cell P (primary):** S = the max 1m high on D2 from 09:30 through B's last present 1m bar, + $0.01. This is the
    day-2 regular-session high so far.
  - **Cell W (neighbour):** S_W = E + 1.5 x (S - E). It is wider only.
    - It scales with the trade's own risk, so it works across $1-$20 names. A % of price ignores structure, and ATR on
      event days is dominated by the event itself.
    - Why wider: 1m bars mis-judge tight stops (2.60: 48% hit inside the fill bar), and a distance under one LULD band
      is often jumped by a pause. This is the house one-step-neighbour form.
- **Stop judging**, on 1m bars from the entry bar through the bar starting 15:54:
  - **Reading L (primary).** If a bar opens >= stop, exit at its open (this covers resume bars). Else, if its high
    >= stop, exit at the stop.
    - The entry bar is included: the fill is at its open, the first trade of that bar, so any later high comes after
      entry. This is why SIPORB's fill-bar ambiguity does not arise here.
  - **Reading N (next-bar).** If a bar opens >= stop, exit at its open. Else, if its high >= stop, exit at the open of
    the NEXT present 1m bar; if none comes before 16:00, the halted-into-close rule.
- **Exit:** X = the open of the first present 1m bar starting in 15:55-15:59 ("out at 15:55"). If none, the
  halted-into-close rule (section 5) applies.

## 7. Size, costs, locate, daily P&L, ROC @ $30k

- **Size at notional N.**
  - shares = floor( min(N, 0.01 x ADV$) / E ), ADV$ = mean of c(t) x v(t) over D0-19..D0 (the filter's window; the run
    day D1 is not in it).
  - No compounding. Precedents: ATTN and XGAP at fixed notional.
  - Fixed-risk sizing is rejected: it would blow size up on exactly the tight, badly judged stops.
  - There is no limit on concurrent names. Printed: the max concurrent positions, the max gross notional on a day, and
    the stop-distance buckets (S - E) / E of 0-2 / 2-5 / 5-10 / 10-20 / > 20% (counts).
- **Judged size N* (shared with PMFAIL r1 section 6):** the smallest N on a $500 grid from $5,000 whose maxDD (that
  series, reading L, base cost) >= $30,000; $500,000 if none. Each cell, and each null draw, solves its own N*. Shares
  are then fixed; every other reading of that cell re-prices the same shares. Every bar reads the series at N*.
- **Capacity line (report, at N*):** the share of trades where the cap binds; median entry-bar and stop-bar 1m dollar
  volume against the trade notional; the most names and the most gross short notional on one session.
- **Costs per side, per share, at price p** (p = E on entry, X on exit). This is PMFAIL r1's cost model, with h50 / h75
  taken from RUNNER2's own day-2 quotes sample (section 4). The bucket b is set by c(D1).
  - **Base:** max(h50(b) x p, $0.005) + $0.0035.
  - **Stress:** max(h75(b) x p, $0.005) + $0.01 + $0.0035.
  - **Fallback priors** if quotes cannot be pulled, or a bucket has fewer than 20 name-day values: h50 = 0.50% (lt5) /
    0.25% (5to20), and h75 = double those.
  - The floor is half a tick ($0.005), a mechanical limit: 50 bps a side at $1, 10 at $5. The $0.0035 is the house
    commission (SIPORB).
  - On the fallback priors, the base round trip at $5 is ~64 bps.
- **Locate:** a percentage of entry notional (shares x E) per trade. **Primary 1%; stress 2%** (scope: "stressed at 1% and
  2%"; same as PMFAIL r1). One more charge per night a halted-into-close trade is held.
  - No house borrow data exists. Alpaca's shortable / easy_to_borrow flags are today's, not point-in-time: they are
    printed as a split among active names, never used as a filter.
- **Trade P&L:** shares x (E - X) - entry cost - exit cost - locate.
- **Daily P&L:**
  - The sum of trade P&L booked on its exit session, over every market session in 2016-07-01..2025-06-29, with $0 on
    sessions without one. The leg is flat each night except halted-into-close holds, so daily equals closed-trade P&L.
  - ET session date = UTC date for exits between 09:30 and 16:00 ET.
  - **Joining to #463:** reindex onto book463_daily.csv's index with fill 0, appending leg dates not in it
    (tvnt1_triage.py lines 271-273).
- **ROC @ $30k (judged)** = 30 x (net / Y) / max(maxDD, 30,000) at N*: net a year in $k at a $30k own drawdown, under the
  1% cap.
  - Y = (2025-06-29 - 2016-07-01).days / 365.25 = 3,285 / 365.25 = 8.994 (q19_a2.py convention).
  - maxDD = max over days of (running peak - cumulative P&L), with both starting at $0 on 2016-07-01.
  - The uncapped scale-free figure at $5,000, 30 x (net / Y) / maxDD, prints beside it; maxDD = 0 there means undefined.
- **Other statistics** (on the judged series):
  - Sortino = mean(d) / sqrt(mean(min(d, 0)^2)) x sqrt(252), over all WF sessions.
  - t = mean(d) / (sd(d, ddof = 1) / sqrt(n)), over all WF sessions, zeros included.
  - PF = gross winning trades / |gross losing trades|, on net-of-cost trade P&L.
- **Cost curve** (pure bps, no floor, no commission): 0 / 10 / 25 / 50 / 100 bps a side x locate 0 / 0.5 / 1 / 2%.
  - Break-even bps a side = (net at 0 bps) / (sum of entry and exit notional) x 10^4, printed at locate 0 and 1%;
    break-even locate (the % a trade that takes net to zero) per price bucket.
  - The 0 and 10 bps rows sit below what a marketable order can pay on sub-$5 names. They are gross references.

## 8. MANAGER conditions 3 and 4 - SURVIVORSHIP and the REVERSE-SPLIT FLAG (shared with PMFAIL r1)

**Condition 3 - survivorship.**
- The universe comes from the daily cache WITH delisted names. Shared definitions: inactive = every assets.csv row for the
  symbol inactive (1,002 cached symbols; 1,094 if any row counts); the 92 cached symbols with mixed rows print as
  ambiguous, for status and shortable flags alike; delisted = last daily bar before 2026-06-01, the date read from the
  uncut cache (section 2's one exception): 1,014 symbols.
- Printed per WF year, before any P&L: the delisted share of event day-2 sessions, under both definitions.
- **The hole, stated:**
  - The exchange filter used TODAY's listing. 16,297 inactive names now on OTC are absent for their whole history, so a
    runner that later fell to OTC is missing. (The other 1,152 names dropped are active OTC listings.)
  - The 66 X_DELISTED names have no bars, and 454 universe symbols have no daily bar at all.
  - Prior: names that later collapse are disproportionately losers, so their absence likely biases AGAINST the short.
    The intraday direction is unknown.
- **Reused tickers:** 98 symbols are listed twice in assets.csv, so a series may splice two companies. Their event
  sessions are flagged, kept, and reported with and without.

**Condition 4 - reverse split in the prior 60 days.**
- A day-2 session is FLAGGED if a reverse split took effect on a session in [D2 - 60 calendar days, D2 - 1 day], from any
  of: (i) an S1 session with F / F' > 1.005 (all names); (ii) a calendar reverse_split row, symbol-mapped (floor names
  only, from 2016-06-01); (iii) PMFAIL r1's test M on that session (all names; catches splits the vendor missed).
- The three sources print with their agreement. Flagged sessions stay in the primary; P&L is reported with and without
  them. The flag counts per year print before any P&L.
- The split-gap guard is not shipped for research caches, so the harness runs S1/S1c/S2/M itself.

## 9. Cells, reported rows, family null, power line

**Judged cells (exactly two).** Both use reading L, base cost, SSR skip, the section 2 event set, sized at their N*.
- **P:** stop above the day-2 high so far.
- **W:** the same signal and entry, stop at 1.5 x P's distance.

**Reported, never cells.** Each uses P's rules except where stated:
- **OPEN2:** the unconditional day-2 opening-print short. Short at the open of D2's 09:30 1m bar, no stop, exit X. A
  missing 09:30 bar means no trade (counted). SSR-at-open sessions skipped, and printed with the Rule-201-legal fill.
  This is the literature's own measurement.
- **NOCROSS:** the first 5m close below VWAP in the window, with no cross required.
- **SSR:** the SSR-active signals with the Rule-201-legal fill (section 6), at base and stress cost.
- **Reading N** for P and W; the 4-minute halt reading.
- **Splits:** c(D1) >= $5 only (binds in bar 12); shortable-today vs not among active names; reverse-split-flagged vs
  not; delisted vs active; reused tickers; halted-into-close trades out; S2' on.
- **Placebo:** the trigger on the runner2_nonevent sample (section 4), matched to RUNNER2's events.
- **VIX:** P&L by prior-day VIX tercile (cut points = terciles over the WF stretch; Nagel's prior).
- **Band reading:** band on c(D0) only.

**Family null:**
- **Sessions:** Omega = the sessions where cell P (reading L) filled a real trade. Omega comes from the signal schedule
  alone, before any P&L.
- **Draws:** 500, numpy default_rng(20261006) (PMFAIL r1's count and seed; its own generator).
- **Each draw, for each session in Omega:**
  - draw one 5m bar uniformly from the session's present 5m bars with close time in [09:45, 14:00];
  - apply the same entry rules (present entry bar within 4 minutes, not a resume bar, no SSR at that bar, E < S);
  - if blocked, redraw without replacement up to 20 times; otherwise that session has no null trade (counted).
- The same random bar serves both cells, with S = the high so far at that bar + $0.01 and W = 1.5x. Reading L, base cost,
  the halted-into-close rule, each draw sized at its own N*.
- **Statistics per draw:** the family MAX over {P, W} of ROC30, of t, and of the R-sum (section 10).
- **Printed:** p50, p95 and p97.5.
  - The 95th binds, as the scope says.
  - PMFAIL and RUNNER2 are one hypothesis family (attention reversal, one pull, linked names). So the 97.5th (Bonferroni
    for two legs; XGAP precedent) prints beside it: MANAGER review item.

**Power line**, written and run BEFORE the real direction (tools/power_line.py):
- **The coin-flip leg:** take P's real entry schedule on Omega (same entry bars, E, shares at P's N*). Each trade gets a
  fair-coin direction from default_rng(20261006).
  - A short keeps stop S.
  - A long gets stop E - (S - E), judged with the mirrored L rules.
  - Exit X, base cost; locate on shorts only.
- **At c:** c = 0.25 x SD(#463 daily mtm) / SD(coin leg), over 2016-07-01..2018-06-30, with the leg reindexed onto the
  book index, fill 0.
  - Run: `python tools/power_line.py --cand <#463 + c x coin>.csv --twin <#463>.csv --from 2016-07-01 --to 2025-06-29
    --block 20 --draws 1000 --seed 20261005`.
- **At $30k own DD:** the same, with coin x 30,000 / DD_coin.
- **Printed:** SD, line_5pct, line_80pct for both. Also the family null's p95 - p50 of the max ROC30 (the other house
  power notion).

## 10. Stage A bars (WF 2016-07-01..2025-06-29 ONLY; no lockbox read; stock bars start 2016-01, so no EARLY read)

House line #45: the standalone bars alone decide. All bars apply to cell P's judged series at N*, reading L, base cost,
SSR skip, unless a bar says otherwise.

1. **Return.** ROC @ $30k (judged) >= 15, OR the earner route. The earner route needs ROC >= 5 AND all three of:
   - the leg's P&L summed over R's 762 days (in_R = True in residual_days.csv) > 0;
   - that sum without the leg's 3 best R days > 0;
   - that sum above the null p95 of the family-max R-sum.
2. **Beats the null.** ROC @ $30k is above the family null's 95th percentile of the max ROC30.
3. **PF >= 1.05.**
4. **Trade count.** >= 100 WF trades AND >= 50 filled trades in EVERY July-June year (the scope's reading, SCOPE_DISC
   line 85), unless MANAGER rules in writing before GO that ">= 50 a year" means a 9-year mean (>= 450) house-wide. The
   lane does not choose. Under the per-year reading RUNNER2 r1 is FAIL on counts from the daily cache before any pull:
   the 2016-17 event ceiling is 47 (reader count, band on both closes), and trades cannot exceed events.
5. **Years.** >= 6 of 9 July-June years with net > 0. A year with no trades is not positive.
6. **t >= 2.0** on the daily series AND above the family null's 95th percentile of the max t.
7. **Stress.** Net > 0 at stress cost (stress spread + 2% locate).
8. **Concentration.** Net > 0 without its best day, AND net > 0 without its best trade.
9. **Meme years.** Net > 0 without 2020-02-15..04-30, AND net > 0 without calendar 2020-2021 (binding for stock legs).
10. **Neighbour.** Cell W net > 0.
11. **Reading N.** Cell P net > 0 on reading N (added here; MANAGER review item).
12. **Tradable subset.** The trades with c(D1) >= $5 have net > 0 at stress cost and PF >= 1.05 (SCOPE_DISC line 336: a
    result that needs sub-$5 shorts nobody will lend is not tradable).

**Count gate:** bar 4 is checked on filled-trade COUNTS before any P&L is computed, and first on event counts from the
daily cache before the pull. If it fails, RUNNER2 r1 is recorded FAIL on counts and no return is computed.

## 11. Order of work and diagnostics

**First, before any real-direction number:**
1. Counts: events per year under each reading, each filter's survivors; delisted share; reverse-split flags by source;
   SSR counts (at the open, intraday, carry-over); triggers and fills per year with the block reasons; halts and
   halted-into-close exits; trigger times by half hour; stop-distance buckets; the feed diagnostics; the spread
   statistics; cap binding at N*. Then the count gate.
2. The power line, then the family null's p95 / p97.5.
3. **Overlap:**
   - With PMFAIL (same names): D2 sessions that are PMFAIL event days; the same name-day overlap of filled trades (both
     legs short one name on one session), their joint P&L and P&L correlation, and on those name-days the combined
     position against one 1% cap and one locate; PMFAIL D1 trades followed by RUNNER2 D2 trades.
   - With the book: for each #463 leg (book463_daily.csv L0..L3_mtm, in api/book_shadow.py BOOK463_LEGS order: ORB,
     ENGU-Q, TTM, NOISE), the share of RUNNER2 trade days on which that leg's mtm is nonzero; the same for RES
     (line.csv res_c); trade days inside R's 762 days and #463's 460 drawdown days.

**Then the real cells, with these diagnostics (all reported):**
- **Event-time path:**
  - the short's mean and median mark in bps of E, by minute from entry 0..+390 (held at the exit value after the exit);
  - -30..0 minutes before the signal;
  - the D2 premarket path from 04:00 (1m close / c(D1) - 1) over all event sessions;
  - the same for OPEN2.
- **Regime halves:** 2016-07-01..2021-12-31 and 2022-01-01..2025-06-29.
- **Per July-June year:** trades, net, PF, mean notional, SSR skips, delisted share.
- **R's 45 episodes** (a2.json line_episodes): P&L in each. #463's 28 episodes / 460 days (episodes.csv) as a report.
- **Correlation:** daily P&L vs each #463 leg and vs RES (line.csv res_c), on all days and on R days.
- **Book add (#45, report):**
  - c from P's judged series as in section 9; (#463 + c x leg) vs #463 and (L + c x leg) vs L, at c, 0.5c, 2c and the
    $30k-own-DD twin (the judged series).
  - Parity is asserted first: #463 WF 93.81 / 3.816; L 120.82 / 3.916.
  - "Lifts the book" = >= 98.50 / 3.816 with paired-bootstrap p5 > 0. It decides only whether a forward BOOK shadow
    line opens.
- **Short only:** the long side is not traded. OPEN2 and the coin-flip leg are the comparisons.
- **Concentration and stress reads:**
  - top-10 share of net, by trades and by days;
  - net without the best day and without the best trade;
  - no-2020, no-2020-21 and no-2022 reads;
  - the 10 worst trades (squeeze tails).
- **Cost curve, break-even bps and break-even locate** (section 7); the capacity line.
- **PMFAIL link:** the same-name P&L link across consecutive days (a PMFAIL D1 trade vs a RUNNER2 D2 trade), the same
  name-day overlap above, and the daily P&L correlation between the two legs.

## 12. What could fool us

- **The trigger selects on the path.** The cross-then-below rule is a price-path condition. The family null keeps the
  sessions and randomizes the bar, and OPEN2 shows what the day alone gives.
- **Squeeze tails.** BHOS's day-0 open-to-close is right-skewed (extreme events: mean +9.15%, median -0.83%). Halts and
  open-through gaps let a short lose past its stop. Reading N, the halted-into-close rule and the worst-10 list show it.
- **Meme years.** BHOS is strongest after March 2020. The no-2020-21 read binds.
- **Survivorship** (section 8). OTC-fallen names are absent.
- **Feed.** The backtest is SIP. A free-plan live line is IEX. The IEX twin sizes the gap. The owner's chart highs
  differ from any vendor's (XHG reads ~18 on his chart vs 16.42 on Yahoo, CBU.md line 1332).
- **Halts vs thin minutes.** The halt rule cannot tell them apart. Both count, and the run-length table shows the mix.
- **Splits.** An unrecorded reverse split can fake a +40% close. S1/S1c/S2 plus the 60-day flag guard it; S2's volume
  clause is calibrated before the pull; residual risk is reported.
- **Tradability.**
  - The modelled fill assumes a locate exists. Many brokers do not lend sub-$5 names: bar 12 binds on c(D1) >= $5, and
    shortable-today among active names prints.
  - Rule 201 removes a quarter of D2 sessions or more (SSR at the open); the judged population is the rest, and the
    legal-fill report shows the others.
  - Level-stop fills are optimistic in a squeeze; reading N binds.
  - Size beyond the 1% cap is not judged (N*).
- **Volume definition.** Daily-cache volume includes extended hours, so the $1M ADV floor is slightly looser than an
  RTH figure.
- **Linked legs.** PMFAIL and RUNNER2 share names across days and on some sessions within a day. A pass in both is not
  two independent results.
- **Thin early years.** 47-65 sessions a year in 2016-19 before the trigger; bar 4's reading decides whether the leg is
  testable at all.
- **Owner's journal.** It grounds the habitat ($1-$20, under 20M shares), not the direction or the horizon. All his
  trades are long, and the hold to 15:55 is the literature's.

## 13. PASS / FAIL (shared with PMFAIL r1 section 20)

- **PASS** = every bar in section 10 holds. The engine has no multi-stock job type (PREREG_ALPACA_R1.txt line 48), so the
  registered route, pending MANAGER's ruling before GO, is SIPORB's Stage C form: a forward no-order shadow line with its
  own bar and an owner call, computed on SIP 15 minutes late or IEX real time (section 3's gap), with the broker and
  locate source named by MANAGER before any order (Alpaca shorts easy-to-borrow names only; WEBULL_GO_LIVE.md 2.3). A
  plugin with harness parity and a window-pinned Auto-Validate (900 trials) replace it only if a stock job type is built
  first. Stage B: a one-read veto on the sealed stock year 2025-06-30..2026-06-30, through its own MANAGER pull, excluding
  the 18 sheet name-days. A RUNBOARD row the same day, and a ledger row.
- **FAIL** (any bar, including the count gate): dead. No variants, no re-cut of the window, stop, band or trigger. A
  ledger row and a RUNBOARD research row.
  - A FAIL here does not reopen any dead row (2.60-2.63). It says this proxy of the habitat does not pay.

## 14. Files the driver writes

Output directory: `C:\EdgeLog\_anatomy_cache\disc_runner2_r1\` (outside git). Modes run in order: --counts, --power, --run.
The name-day list is written by tools/disc_gapper_namedays.py (PMFAIL r1 section 16).

- **--counts:** `counts.json` (every count in section 11 step 1, including the feed and spread diagnostics). No P&L.
- **--power:**
  - `coinflip_daily.csv`, `book463_wf.csv`, `cand_c.csv`, `cand_30k.csv` (columns date, pnl_usd; inputs to
    power_line.py);
  - `power.json`;
  - `null.json` (p50 / p95 / p97.5 of the family max ROC30, t and R-sum; draws; seed; Omega size; blocked counts);
  - `null_draws.csv`.
- **--run:**
  - `trades_P.csv`, `trades_W.csv`, `trades_OPEN2.csv`, `trades_NOCROSS.csv`, `trades_SSR.csv`. One row per trade:
    symbol, d2, exit_date, signal_close_time, entry_time, E, S, shares, notional, exit_time, X, exit_reason, gross, cost,
    locate, net, net_N, flags.
  - `daily_P.csv`, `daily_W.csv` (date, pnl_usd).
  - `event_path.csv`.
  - `stage_a.json`, with keys: cells, n_star, checks (bars 1-12, each true/false with its value), verdict, reports,
    halves, per_year, cost_curve, capacity, episodes_R, corr, book_add, overlap, pmfail_link, info, shas, null, power.

## 15. MANAGER review items (choices this draft makes that the scope left open or worded differently)

1. Feed = sip for history; IEX pulled on every event row as the live-gap twin (condition 1 restated). Fallback as PMFAIL
   r1; spreads never from IEX quotes.
2. Halt = >= 5 missing 1m bars (condition 2 restated); the 4-minute reading is reported. Halted into the close: next
   daily open within 10 sessions, else a stress price; booked on the exit session; one locate a night.
3. The VWAP trigger requires a prior 5m close at or above VWAP. The no-cross version is reported.
4. The price band is on both c(D0) and c(D1). The split rule is S1 + S1c (symbol-mapped) + S2 (test M, calibrated) on
   D1..D2; S2' (D2, price only) is a report.
5. SSR: regular-session proxy (SEC FAQ 1.1-1.2); carry-over removes the session; same-day SSR signals are skipped; the
   legal-fill reading is reported.
6. ">= 50 a year": the scope's per-year reading unless MANAGER rules the 9-year mean house-wide. Under per-year, RUNNER2
   r1 is FAIL on counts before the pull.
7. Reading N binds as net > 0; bar 6 includes the null's p95 of t; bar 12 binds on c(D1) >= $5.
8. ROC is judged at the capped size N*; the uncapped figure is reported.
9. The null's 97.5th percentile prints beside the binding 95th.
10. Costs and locate follow PMFAIL r1. RUNNER2's spreads come from its own day-2 quote sample, NBBO in force at 8 marks.
11. Stage B/C routing for a stock leg (section 13), identical in both preregs.
12. Option, per the literature: make OPEN2 a judged cell in place of the stop neighbour W. Not taken here, since the
    scope names W.
