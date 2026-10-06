# SCOPE - DISCRECTIONALRY-TO-ALGO lane (journal setups as a mechanism space), DRAFT for MANAGER review (2026-10-06)

Standing-order addendum 2 (owner 10-05: "have all other strategies test more; push and scope out deeply this time"), via
MANAGER #35 / #36. The lane scopes its domain first, then works it as a queue of three live preregs. No return of any
candidate below has been read. The only numbers computed for this draft are session COUNTS (VIX states, stock gap days),
read-only, with the file named. Each item becomes its own prereg, reviewed by MANAGER.
Data column: H = held, P = public no-key (docs/PUBLIC_DATA_CATALOG.md; "P?" = public but not catalogued), M = needs a
MANAGER pull. Research ids stay under MISC until something passes. Every number cites a file or is marked as a prior.

## Where the lane stands

- SETUPS r1 (SETUPS_PREREG.md, 516 cells): 1 cell passed triage. Its validate, CBU-Q #427, FAILED 5 of 7 gates (LB 80
  trades, PF 0.85). 74% of its trades fell on NOISE #382 days, and it lost $61,806 on NOISE-flat days (setups/ALGO_SCOPE.md).
- r2, the point-score leads (SETUPS_PREREG_R2.md): 0 of 40, dead at triage; 68% on #382 days.
- r3, CBU rules v1 (SETUPS_PREREG_R3_CBU_V1.md): 1 of 16 cells advanced. Validate #481 FAILED 5 of 7 (ES PF 0.73; PBO 0.63,
  the chance its chosen cell was overfit; ROC @ $30k WF +37.8 vs LB -40.1 on 61 trades). 84% of its trades fell on #382
  days, 97% of them the same way, and it lost on NOISE-flat days.
- So CBU-Q was a NOISE #382 shadow three times, and CBU is ALERT-only (CBU ALERT 1.0: ~2.75 alerts a day NQ+ES, 9 of 13
  examples). ENGU, EBU, CBD and ENGD have no edge as written rules.
- The 9-point score has no link to R: Spearman +0.03 (CI -0.25..+0.31, 53 trades); ps1.2 -0.007 (CI -0.286..+0.265, 54
  trades) (docs/POINT_SCORE_BACKFILL_2026-09-30.md).
- The lane holds no live backtest prereg today.

## What the evidence says about where to look

1. **The 1m NQ/ES plain-rule versions of his setups are mined out, and they mostly shadow NOISE.** Rounds 37-38 went 0 of 59
   ("do not re-test 1m fixed-target scalps"). Legacy ENGU 1.1/1.3 is dead under honest fills, July ENGU-Q went 0 of 312, the
   box scan found nothing, and SETUPS r1-r3 are above. Re-sizing, re-filtering or re-exiting the same trades is closed too
   (ledger 2.1, 2.3; filters on crowns die out of sample).
2. **A lead on 18 trades, not an edge.** The 45 labelled futures trades made +$227.61 at a mean +0.11 R. The 18 signals from
   09:30-09:59 made +$232.12 (+0.283 R), more than the whole net (recomputed from tools/data/setup_journal.json, 10-06
   reader). Median holds are 1-2.5 minutes, below what 1m bars can judge (SIPORB lesson, 2.60), and the open is ORB's and
   NOISE's ground. The 10s capture (~45-50 clean RTH sessions per root) cannot carry a walk-forward, so any burst-level idea
   is forward-only.
3. **He selects a day type, but the book's losses are not shown to be a range-day story.**
   - CBU fires at a new high on days already above the premarket and prior-day highs (new high 7 of 9, above PDH 10 of 11);
     ENGU fires inside the range (new high 2 of 16) (ALGO_SCOPE). NOISE #382/#422 and ORB #314 already take the trend-day
     side, which is CBU-Q's 74-84%.
   - #463's residual drawdowns (R) are driven by ENGU-Q (corr 0.68), ORB (0.58) and NOISE (0.49) (ledger 2.79). ENGU-Q #335
     gave back 46% of the book's episode losses (C:/EdgeLog/manager/assess_1005/ASSESSMENT_TOP_MODELS_2026-10-05.md line
     236). No house file measures #463's P&L by day type, so "range days are where the book bleeds" is a prior, not a finding.
   - State-conditioned fades were tested and died: REVERT r1 loses before cost (t -3.6 NQ, -5.9 ES; 2.38); r38 CHOP-FADE (a
     1m range-compression state) went 0 of 20 with its round (BACKTESTING_STACK.md line 1887); VWAP_FADE_2_0 added a regime
     gate and still failed (PARAM_LIBRARY.md line 310; BACKTESTING_STACK.md line 720); "Chop is not identifiable before
     entry" (ORB.md line 980).
   - So the lane looks in two places: (a) a different information set for the day type, on NQ/ES (only BALANCE and
     GEXREV survive the cross-check, both weak); (b) his own stock habitat, small-cap premarket gappers, a different market
     and clock where the house holds no result (no small-cap or gapper row in RESEARCH_LEDGER.md). ALGO_SCOPE Track C
     parked stock CBU only for want of small-cap intraday data; the Alpaca keys were saved 2026-10-02
     (docs/ALPACA_STOCK_BARS.md line 154).
4. **The literature is analogy, not evidence.**
   - Candle and engulfing rules had no after-cost edge on intraday index futures (Fock, Klein & Zwergel 2005; Duvinage,
     Mazza & Petitjean 2013).
   - Intraday momentum is real (Gao, Han, Li & Zhou 2018; Baltussen, Da, Lammers & Martens 2021), and it is NOISE's trade.
   - The reversal papers cited below are on single stocks, daily horizons or cross-sections. None shows an after-cost
     effect on index futures or on small-cap intraday trades.
   - House-measured index reversal: +0.2 NQ / +0.1 ES points a trade gross, against 0.53 / 0.36 of cost (2.41).
5. **Map consequence (docs/MDL_MAP_R1.md).** Another NQ/ES momentum leg needs ~$40k a year; an uncorrelated leg ~$15k a year
   (ROC ~15 at $30k); a leg that earns while the book falls helps at almost any positive return.
   - Earner route, binding window: own WF ROC @ $30k >= 5 AND positive over R = 45 episodes / 762 days of L = #463 + 0.264
     x RES, incremental over L (ledger 2.79; the 10-05 assessment, line 26: "a new leg on another clock and market").
   - Reported, not binding: #463's 460 WF drawdown days (2.68, 2.75) and the worst drawdown 2020-03-02..03-27 ($44,849),
     the episode that sets the $30k scaling (2.80).
   - Market-stress gates are closed as seats: crisis hedges answer March 2020 only (2.59, 2.64; docs/SCOPE_TV_2026-10-05.md
     point 1). A VIX- or GEX-state leg here must clear the standalone bars (docs/SCOPE_NOISE_2026-10-05.md, A3 precedent).
   - Standing order 10-04 item 4 (docs/SCOPE_TV_2026-10-05.md line 83): an idea that cannot plausibly earn ROC >= 15 at a
     $30k drawdown of its own is not drafted, unless an earner prior is argued in dollars.

## Candidate mechanisms, ranked (map placement and expected size are PRIORS, stated before any return)

**Bottom line.** The space yields three draftable items, all at low odds: the prior chance that at least one passes Stage
A is ~13%. Two need one MANAGER pull and a habitat ruling; the third needs an ownership ruling. Ranks 4-10 complete the
map and are NOT drafted. Ranks 1, 3, 4 and 6-9 share one habitat and one pull, so they are correlated: if rank 1 dies on
cost, they die with it.

Ranking rule: the prior chance of clearing the bars (standalone ROC @ $30k >= 15, or the earner route on R), then data
readiness. Each prior is judgment written before any return: a ROC range at $30k, its median, P(ROC >= 5), P(ROC >= 15).

| Rank | Mechanism + citation | Owner setup it comes from | Data | Dead-list cross-check | Map placement / expected size (prior) |
|---|---|---|---|---|---|
| 1 | **PMFAIL** - the small-cap gapper's failed premarket high, short. On an event day (counts below), short the first 5m close back below the premarket high (04:00-09:29) after price traded above it, 09:35-11:00; stop above the day's high so far; out at 15:55; size capped at 1% of the prior 20-day dollar volume (prior rule). Attention buying overprices and reverses (Barber & Odean 2008 RFS; Barber, Huang, Odean & Schwarz 2022 JF); high-attention stocks open high and fall back during the day (Berkman, Koch, Tuttle & Zhang 2012 JFQA); short-sale limits slow the correction (Miller 1977 JF) | His stock CBU: sub-$5 movers bought on premarket base breaks, 9 of 12 signals 08:01-09:29 (setups/CBU.md trade times). His long side lost: 12 trades, -$133.56, -0.45 R; three of seven losers went out at or through the breakout candle's low (CBU.md lines 14, 21); the 18 sheet-only trades sum to -$17.85 (CBU.md sheet table from line 1709, summed). Grounding, not evidence | M: 1m bars 04:00-16:00 for the event days via MANAGER's Alpaca wrapper (raw, pulled once, photographed), plus quotes on a sample of days for spreads. H: the counts (daily cache) and XBRL shares (float split) | SIPORB 2.60 (>$5 stocks in play, a TWO-sided opening-range breakout; edge under a cent a share; its next-bar reading t 0.29); XGAP 2.63 (NDX members' gaps faded 09:35 to close: gross ~0 either way); DDW L2 2.62 (large-cap no-news gap fade loses at a 10 bps fill); ATTN 2.61. None traded sub-$20 gappers of >= 20% or a failed-premarket-high trigger. The strike: three adjacent stock fades had gross ~0, and spreads are wider here | Standalone; small-cap idiosyncratic, prior rho with #463 ~0. ROC -15..25, median 0; P(>=5) 20%, P(>=15) 8%; P(Stage A pass) ~6%, prior t median ~0.5. Cost decides: gross must clear a round trip of ~0.5-1% plus a locate (priors; the house holds no spread or borrow data for these names). On R: may earn in 2022's speculative unwind, may lose in 2020-21 squeezes (prior) |
| 2 | **BALANCE** - the range-day VWAP fade, with NOISE's own state as the classifier. If NQ has made no #304 core band break (5m close) by 12:00, fade 5m closes stretched from VWAP back toward it; stop at the band edge; out at VWAP or 15:55. Moves inside the noise area are noise (Zarattini, Aziz & Barbon 2024); short-lived order imbalances revert (Grossman & Miller 1988 JF, an analogy) | ENGU bought inside the range (new high 2 of 16, ALGO_SCOPE line 88); EBU midday near 0 R; his day-type notes "TP early bc daily bearish", "BEAR DAY so tight SL" | H: NQ 5m RTH NOADJ id 37 (NOISE bands never run on an ADJ master, 2.71); ES id 33 as a transfer report | Dead: REVERT r1 (2.38, loses before cost); VWAP (VWAP_FADE_1_0 / 2_0, FAIL / weak, BACKTESTING_STACK.md line 720; 2.0 was regime-gated, PARAM_LIBRARY.md line 310; VWAP family closed, MISC_SWEEP.md line 119); r38 CHOP-FADE, a range-compression state, 0 of 20 (BACKTESTING_STACK.md line 1887); MISC 10 o'clock fade (MISC_SWEEP.md line 76); hourly mean reversion pooled PF 1.00 (MISC_SWEEP.md Screen 2). What differs, in one line: the state is whether the crown's own trigger has fired by noon, not a price shape (r38) or a higher-timeframe trend (VWAP_FADE_2_0). Against it: ORB.md line 980. STRATEGY-BEATING's 10-05 scope calls NQ/ES intraday closed (line 17); this line is the only claimed escape | Earner route only (the standalone tail is under 15). ROC -8..8, median -1; P(>=5) 10%, P(>=15) <2%. Gross needed: well above 0.533 NQ pt a trade (1.20 on MNQ, tools/rocfrontier/PREREG_RISK_R1.txt line 105), against a house-measured reversal of +0.2 to +0.5 points (2.41). NOT an earner by construction: the stop sits where NOISE enters, so it loses on whipsaw-break days that NOISE also loses on (first breaks in multi-break sessions lose ~$205 a trade, 2.82). R-sum prior: median ~$0; P(above the family null's 95th percentile) ~5%. P(Stage A pass) ~4%, prior t median ~0 |
| 3 | **RUNNER2** - day 2 of a small-cap runner, short. The session after a >= +40% close (filters as rank 1), short the first 5m close below VWAP, 09:45-14:00; stop above the day-2 high so far; out at 15:55. Short-run reversal is concentrated in illiquid stocks, where costs are also highest (Avramov, Chordia & Goyal 2006 JF); reversal is the return to providing liquidity (Nagel 2012 RFS). Daily-horizon analogies | His habitat only: the names he trades are day-1 runners (XHG ran from ~1.20 to 18 premarket before his 6.67 buy; CBU.md line 1332). No journal trade is a day-2 trade, so the grounding is thin | M: the same pull (day-2 bars). H: the counts | DDW L1 2.62 (weekly reversal in the 500 largest: long beta in a crash, dead); STRATEGY-BEATING's RESREV row (1-month residual reversal, wrong drawdown sign); XGAP / ATTN as rank 1. None traded the day after a small-cap runner | Standalone. ROC -15..20, median -1; P(>=5) 15%, P(>=15) 5%; P(Stage A pass) ~4%, prior t median ~0.3. Counts are thin early (41 and 55 in 2016-17 and 2017-18, ceilings), so the 6-of-9-years bar is at risk. Cost and locate as rank 1 |
| 4 | **BACKSIDE** - his CBD on the gapper's back side, short. On rank 1's event days, after a morning high set before 10:30, short the first 5m close below a consolidation low once price is under VWAP, 11:00-15:00; stop above the consolidation high; out at 15:55. Attention fades through the day (Barber & Odean 2008; Berkman et al. 2012) | CBD, his consolidation breakdown (4 futures trades, +$21.15; setups/README.md); HOWL "made lower highs" after his 08:21 buy (CBU.md line 1478) | M: the same pull | The >$5 version (old INPLAYBACK) is dropped below: XGAP 2.63 and DDW L2 2.62 show gross ~0 in large and mid caps. This keeps only his habitat | Standalone; rank 1's later-clock sibling, correlated with it. ROC -15..15, median -2; P(>=15) 3%. NOT DRAFTED before rank 1's verdict |
| 5 | **GEXREV** - dealer gamma as the day-type switch, reversion arm only, ES primary. When the prior day's dealer gamma exposure (GEX: a vendor estimate of options dealers' net gamma) sits in the top tercile of its trailing 252 sessions, fade 5m closes stretched from VWAP inside the NOISE band; out at VWAP, the band edge or 15:55. Long-gamma hedgers sell rallies and buy dips (Barbon & Buraschi 2020, strongest in the least liquid names; Ni, Pearson, Poteshman & White 2021 RFS, single stocks); short gamma is the momentum side (Baltussen et al. 2021 JFE). Analogies for index futures | ENGU absorption inside the range; his CBU / ENGU split read as the two sides of one switch | P?: an S&P GEX series (for ES) or an NDX one (for NQ); none is catalogued. PARKED: the owner parked a GEX idea on 2026-08-15 (memory: not to be built unprompted), so his go comes first | Every unconditional fade above is dead; none was conditioned on gamma (the house holds no options data). Expiry-day pinning (Golez & Jackwerth 2012) is a 12-day-a-year effect and is not cited as support | Standalone only (a market-state gate). Flat in March 2020 by design, so ~0 on that R episode. ROC -6..12, median 1; P(>=15) 3%. Each $1k a year from a leg flat in March 2020 adds ~0.67 book ROC (30 x 1,000 / 44,849; MDL_MAP_R1.md line 10), under every power line (10.3 and up, MDL_MAP_R1.md). At most one trade a day on a third of sessions (~84 a year) before the stretch filter, so counts after the filter come first and any year under 50 drops it. Whether same-day-expiry (0DTE) options changed what daily GEX means is a prior; the 2022-25 half is reported |
| 6 | **LOWFLOAT** - low-float gappers that hold, long. On rank 1's event days, when shares outstanding (the last XBRL filing before the day) are under 20M (a prior cut) and price holds above the premarket high at 10:00, buy the 10:00 bar's close; stop under the premarket high; out at 15:55. A small float with short-sale limits lets prices run above value (Hong, Scheinkman & Xiong 2006 JF; Miller 1977) | His sheet's float column: NRGV 2.45M "good!", MLEC 0.5M, DRCT 1.27M (CBU.md sheet table) | H: XBRL shares frames (catalog row 3; C:\EdgeLog\_research_cache\xbrl_frames). M: the same pull | SIPORB (continuation in >$5 stocks in play, under a cent a share). No float test in the house | Standalone; long, no borrow. ROC -15..15, median -3; P(>=15) 3%; 2020-21 could carry it alone. Shares outstanding is only a proxy for float. NOT DRAFTED; a reported split inside rank 1 |
| 7 | **PMBREAK** - his premarket base break, long. 08:00-09:25, a 1m close above a premarket base on >= 3x the 10-bar mean volume (his CBU volume read, CBU.md line 18); stop under the base; out by 09:45. Breaks of salient levels fire clustered stops (Osler 2005 JIMF); pre-open price discovery is slow (Barclay & Hendershott 2003 RFS) | His exact stock CBU (9 of 12 signals premarket) | M: the same pull (premarket bars) | SIPORB (RTH, >$5). His own record on it is negative (rank 1's grounding) | Standalone; long, no borrow. ROC -20..15, median -4; P(>=15) 2%. Premarket spreads are the widest of the day (prior). NOT DRAFTED; rank 1 reports its continuation mirror |
| 8 | **FLUSHBUY** - his ENGU after the gapper's morning flush, long. On rank 1's event days, after a >= 15% drop from the morning high (a prior cut), buy the first 5m engulfing close back above VWAP; stop under the flush low; out at 15:55. Buyers of last resort are paid for liquidity (Grossman & Miller 1988; Nagel 2012) | ENGU, his most-traded setup (17 futures trades, +$107.25; ALGO_SCOPE line 88); one stock ENGU +$3.60 (setups/README.md) | M: the same pull | VWAP trend pullback PF 1.01 (MISC_SWEEP.md line 104); EMAPB 27 of 27 cells lose (BOOKMARKS.md line 81); legacy ENGU dead under honest fills. All on NQ/ES; none on small caps | Standalone; long. ROC -20..15, median -4; P(>=15) 2%. NOT DRAFTED |
| 9 | **OPENPRINT** - short the gapper at the opening print, unconditional; out at 15:55. Berkman et al. 2012's "hidden cost of buying at the open" in its plainest form | His fills at the open (EHGO bought 09:32 after the 09:29 breakout candle; CBU.md line 1126) | M: the same pull | XGAP 2.63 ran this on NDX members (09:35 to close): gross ~0 | Standalone. ROC -20..15, median -3; P(>=15) 3%. Registered inside PMFAIL r1 as its unconditional control (reported); never its own prereg |
| 10 | **DISPERSE** - Nasdaq-100 dispersion at 10:00 as a range / trend classifier for the BALANCE fade: low average correlation = a stock-specific day, when the index pins. Average correlation as a market state: Pollet & Wilson 2010 JFE, monthly. No intraday precedent found | The same CBU-vs-ENGU day-type split | H: nqbrd open_bars (5m 09:30-10:00, point-in-time members, 2016-06..2025-06, unadjusted; split days dropped) | NQBRD 2.48 used breadth DIRECTION, and it only repeated opening momentum. This uses dispersion SIZE, never a direction | Earner route only. ROC -4..6, median 0; P(>=5) 5%. A REPORTED split inside BALANCE r1, never a cell, so it does not raise BALANCE's family null. NOT DRAFTED alone |

**Counts for ranks 1 and 3 (no returns).** Read-only on 2026-10-06 from C:\EdgeLog\alpaca_cache\siporb\daily_raw.parquet
(SIPORB's raw daily cache: 6,596 US symbols, active and delisted, 2016-01..2026-06). Filters: prior close $1-$20; prior
20-session mean dollar volume >= $1M; whole-ratio split-like jumps removed. Per July-June WF year, 2016-17..2024-25:
- Rank 1 event days (open >= +20% over the prior close): 103 / 154 / 168 / 450 / 677 / 330 / 258 / 329 / 629 (3,098, ~344 a
  year), on 81-222 sessions a year. Calendar 2020-21 holds 1,250 of them (40%). Prior close >= $5 only: 49 / 73 / 81 / 186
  / 315 / 172 / 111 / 155 / 245.
- Rank 3 day-2 sessions (day-1 close >= +40%): 41 / 55 / 52 / 195 / 260 / 137 / 143 / 161 / 349 (1,393, ~155 a year).
- Both are ceilings before the trigger; the official open stands in for the premarket gap.

Owned elsewhere (not claimed here):
- NOISE lane: NOISE on funds, IWM and QQQ; the TLT noise-area fade (A4); HALFHOUR, ROUND, BONDLEAD.
- ORB lane: 08:30 MACRO830 and SAFEHAVEN (NT1 / NT3), and the expiry-week tilt.
- ENGU-Q lane: trendline-break covering (ENGU-Q #335's trigger), its anatomy and its daily-trend twin.
- TTM lane: compression and squeeze breakouts (hunts paused).
- STRATEGY-BEATING: NQ/ES intraday and overnight (MANAGER #30, 10-04; its 10-05 scope calls them closed), and stock events
  (EDRIFT, EAP, NEWISSUE, NETISS, SHORTINT, BUYBACK, IVOL; share issuance and offerings).
- FRONTIER: 52-week high, stock BAB, quality.
- TV: Form 4; market-state seats.
- Delta at crown entries: NOISE r64, the ORB shadow, Custom ML orderflow r1, the REVERT r1 absorption shadow (absorption at
  failed day extremes on the 10s tape), TTM r20a.
- Exits and sizing on each crown: that crown's own lane.

## Dropped on the map before ranking (no draft)

- **PANIC** (old rank 3: buy the capitulation bar on high-VIX days, NQ below its NOISE lower band). Too few sessions, and the
  wrong map row. Prior-close VIX >= 25: 0 / 6 / 11 / 88 / 81 / 82 / 63 / 0 / 22 sessions per July-June WF year (353, ~39 a
  year, two years at zero). VIX >= its trailing-252 80th percentile: 6 / 72 / 52 / 77 / 6 / 89 / 19 / 8 / 117 (446, ~50 a
  year, four years under 20). Both are ceilings before the band and bar conditions; calendar 2020 and 2022 hold 290 of the
  353 (82%). Counted read-only 10-06 from C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv. It is also long NQ
  on the book's stress days (MANAGER's ANNPREM ruling, docs/PREREG_orb_newtypes_r1_2026-10-05.md line 112) and a
  market-stress gate (closed: 2.59, 2.64, SCOPE_TV point 1). Its trigger is REVERT r1's failed-new-low fade (2.38) behind a
  VIX gate, and 2.17 found no extreme-volatility reversal. DIP #433/#452 and ORB's NT3 SAFEHAVEN trade the same days.
- **BOXSWING** (old rank 4: his 2024-25 multi-session box breakout on 5m). The same trade as ENGU-Q #335 (a volume-spike
  breakout of recent structure above a long average, held across sessions); its 5m port drops PF 1.33 to 1.11 (MISC r22,
  MISC_SWEEP.md line 204). The turtle 20/10 breakout is dead (MISC r17, MISC_SWEEP.md line 73). Its knobs (N 84/252, 1.85R)
  came from his tracker, which is the answer key.
- **GAPFILL** (old rank 6: NQ bounce at the prior close after a gap fill). Its long sits where NOISE goes short on a gap-up day
  (the lower band anchors at the prior close, augur_strategies/NOISE_1_0.py lines 576-581). Its seed was an exploratory split
  the backfill flags as luck-prone ("Exploratory only", POINT_SCORE_BACKFILL_2026-09-30.md). MISC GAPFADE 1.0
  (BACKTESTING_STACK.md lines 474-495) and MISC r16 OOPS (best MAR of 2.09, MISC_SWEEP.md line 27) are dead. A standalone
  prior of 0-5 cannot reach 15.
- **INPLAYBACK** (old rank 7: the back side of >$5 stocks in play). The held habitat (siporb min1_top: price > $5,
  PREREG_ALPACA_R1.txt lines 22-23) is not his; his cited trades were sub-$5 and premarket (HOWL 08:20, XHG 08:44). Same-name
  intraday fades there show gross ~0 (XGAP 2.63, DDW L2 2.62). His habitat's version is BACKSIDE (rank 4).
- **PREMKT** (old rank 10: mega-cap premarket base break on tbis_r3 10-minute bars). Its whole prior (ROC 0-4) is under the
  line, the bars are coarse for 1m breaks, and XGAP and ATTN are dead in the same names.
- **BURST10S and LEVEL10S** (old ranks 8-9). Not legs: ~45-50 clean 10s sessions a root cannot carry a walk-forward.
  BURST10S trades the 1-2 minute horizon rounds 37-38 closed; it survives only as a forward tag (bridge item 2). LEVEL10S's
  bounce arm is the REVERT r1 absorption shadow's ground (2.38), PDH/PDL fades are dead (below), and its notes came from
  sub-$5 stock trades (FATN, PRSO; CBU.md sheet table), not NQ/ES.
- **GAPDOWN** (the small-cap gap-down bounce, his ENGU absorption): news-driven moves drift rather than revert (Chan 2003
  JFE) and no small-cap news filter is held; it is long small caps on stress opens (the ANNPREM ruling); DDW L2's gap fade
  lost at a 10 bps fill in large caps.
- CBU / ENGU / EBU / CBD / ENGD as 1m NQ/ES rules (any filter, base, volume or exit): dead three times; CBU-Q is the NOISE
  #382 shadow.
- The same setups on 5m NQ/ES (round 1's wave 2, never run): NOISE IS the 5m trend-day break. NOISE 2m (#334) was the crown
  re-expressed: 81% shared days, 98% same direction (BOOKMARKS.md line 356; NOISE.md line 1538).
- The same setups on QQQ/SPY shares: there is no gross edge to save. Rounds 37-38 fixed-target cells were flat at ZERO cost.
- Short-gamma last-half-hour continuation (Baltussen et al. 2021; his 15:30-15:50 trades): it fires on a minority of
  sessions (a prior; the only figure seen is a blog's), and it is NOISE's held-to-close trade. The unconditional version is
  dead (2.14, 2.5).
- FOMC 14:00 bursts and FOMC-minutes days: ~16 days a year (8 meetings + 8 minutes, a calendar count) cannot reach 50 LB
  trades. The FOMC 2pm breakout had 19 triggers in 15 years (2.5).
- 08:30 data burst (07-15, unlabelled): ORB's NT1 MACRO830 owns it.
- Closing-imbalance flow at 15:50: every price-only version is dead (2.14, 2.41, MISC MOC fade at MISC_SWEEP.md line 38,
  last-hour momentum), and the imbalance feed is paid.
- Monthly OPEX strike pinning (Golez & Jackwerth 2012): 12 days a year. ROUND (2.73) already covers the round-strike proxy.
- PDL reclaim / failed breakdown (EBU 06-26) and PDH rejection: fades of day extremes are dead (2.38; challenger round 8
  SWEEP, best MAR of 2.78, BACKTESTING_STACK.md line 2790; MISC pivot fade, MISC_SWEEP.md line 38; PDX at PF <= 1.14,
  BACKTESTING_STACK.md line 283).
- VWAP pullback buys on trend days (ENGU 05-21): VWAP trend pullback PF 1.01 (MISC_SWEEP.md line 104), and the VWAP family is
  closed (line 119). Re-entries are NOISE's ground (r50).
- First pullback after the open drive (ENGU 09:30-10:00): challenger PULLBACK, best MAR of 2.2 (BACKTESTING_STACK.md line
  306); EMAPB lost in 27 of 27 cells (BOOKMARKS.md line 81).
- Opening drive out of the premarket range (the CBU 09:30 candle): RELAY (BACKTESTING_STACK.md line 366), MISC DRIVE (failed
  walk-forward, PARAM_LIBRARY.md line 307), the round 37 open drive, GAPGO and NOISE r67 are all dead.
- Trendline-break short covering (EBU): ENGU-Q #335's trigger; its short mirror is dead (2.19).
- "Should have held" / breakeven at +1R then ride: dead on ORB r64, NOISE r68 and TTM r22; exits are not the lever (2.3).
- "Genuine" volume spike vs the same minute of prior sessions, and breakout-bar relative volume: ENGU-Q H-D failed; ORB r65
  is dead.
- Multi-timeframe 200 SMA or the daily HH/HL point as a standalone trend leg: daily trend and fund TSMOM are dead (2.58), and
  DIP is parked. As a tag: see the bridge.
- A slower ENGU (30m / hourly pullbacks): hourly mean reversion pooled PF 1.00 (MISC_SWEEP.md Screen 2); the candle
  literature is negative.
- Next-day continuation after a CBU trend day: the overnight seat is closed (2.75), and DAILYFADE is dead (2.68).
- Panic-state reversal at the DAILY horizon: DAILYFADE 0 of 8 (2.68). The intraday version (PANIC) is dropped above.
- NQ-ES divergence at his signal: ES confirmation is dead (2.42); SPREAD r1 and r2 are dead.
- Stocks, the stocks-in-play front-side breakout with a wider stop: SIPORB's habitat (2.60); its edge is under a cent a share.
- Stocks, halt-resume (OFAL): one journal trade and no halt history at intraday resolution.
- Stocks, large-cap 1m CBU / ENGU: large-cap intraday is dead on cost (SIPORB, XGAP, DDW L2), and TTM on stocks is dead (r20c).
- Stocks, offerings sold into a spike: share issuance is STRATEGY-BEATING's ground (NETISS, NEWISSUE).

## Proposed queue (three preregs to write next, after MANAGER reviews this doc)

Ranks 1-3. Work order: BALANCE first (held data), then PMFAIL and RUNNER2 (one pull). Their prior chances of passing Stage
A are ~6%, ~4% and ~4%, so the expected result is three fails; MANAGER decides whether these odds earn the slots.

**Rulings needed before any draft:**
- (a) The small-cap gapper habitat for this lane. It is the owner's own habitat, and no lane has tested it; the adjacent
  dead results are house rows 2.60-2.63.
- (b) BALANCE on NQ RTH. MANAGER #30 gave NQ/ES intraday to STRATEGY-BEATING, whose 10-05 scope calls it closed. BALANCE's
  one-line escape is in its row. If MANAGER rejects it, slot 2 stays empty.
- Fallback inside the lane's own ground, needing no other lane: the forward CBU alert log with his marks (bridge item 2). It
  is a forward log, not a backtest.
- If (a) and (b) are both ruled out, the lane has no backtest shot in its own ground, says so (as TV's Addendum B did), and
  takes cross-lane work (standing order item 6).

**Shared rules:**
- **House line #45.** The standalone Stage A bars alone decide. The book-add is a REPORT, sized by volatility: c = 0.25 x
  #463's daily P&L SD over 2016-07-01..2018-06-30 / the leg's SD over the same days. It is judged at c and reported at 0.5c,
  2c and as a $30k-own-DD twin, against #463 and incremental over L (#463 + 0.264 x RES = 120.82 / 3.916).
- **Stage A is walk-forward ONLY:** WF 2016-07-01..2025-06-29, arrays cut before 2025-06-30, no lockbox read.
- **Bars:** standalone ROC @ $30k >= 15, OR the earner route:
  - ROC >= 5, with the leg's sum over R's 762 days > 0, still > 0 without its 3 best days there, and above the family null's
    95th percentile; #463's 460 drawdown days are printed as a report;
  - PF >= 1.05; >= 100 WF trades and >= 50 a year; >= 6 of 9 July-June years positive;
  - t >= 2.0 and above the family-null 95th percentile;
  - net > 0 at stress cost, and > 0 without its best day and without its best trade;
  - net > 0 without 2020-02-15..04-30 (no-2022 is reported); for the stock legs, net > 0 without calendar 2020-21 also
    binds; EARLY 2010-06..2016-06 > 0 for BALANCE only (stock bars start 2016-01); neighbours positive.
- **FIRST, before any real-direction run:**
  - the counts (printed above for ranks 1 and 3);
  - the power line, from a coin-flip leg on the primary's real trade schedule (tools/power_line.py, at c and at $30k own DD);
  - the overlap test on crown-flat days vs NOISE #382/#422, ORB #314, ENGU-Q #335 and TTM #459 (3 ES), plus RES.
- **After the verdict:**
  - PASS: a plugin with harness parity, then a window-pinned Auto-Validate (900 trials), whose own lockbox is the leg's
    first look (MANAGER #40), and a RUNBOARD row the same day.
  - FAIL: dead, no variants, and a ledger row.

1. **BALANCE r1** (rank 2): held data only.
   - Needs first, before any return: (i) sessions per year with no #304 band break by 12:00; (ii) from #304's held WF trade
     list, those days split three ways: no NOISE break all day, a later break that wins, a later break that loses at VWAP.
     BALANCE's P&L is later reported in the same three groups, with its co-loss share beside the R-day sum.
   - Cells: 1 classifier x 2 stretch thresholds on NQ; ES as a transfer report (the ES holes of 2020-02-28 and 2020-06-30
     skipped). DISPERSE is a reported split, never a cell. Family null: a coin-flip side on the real schedule, plus the max
     R-day sum.
2. **PMFAIL r1** (rank 1): needs ruling (a) and one M pull.
   - The pull: 1m bars 04:00-16:00 for the ~3,100 event name-days plus a same-size sample of non-event days, and quotes on a
     sample of event days for spreads; raw, pulled once, photographed, never patched.
   - Locate: no borrow data is held, so it is stressed at 1% and 2% of notional a trade. The >= $5 cell is reported, since
     many brokers do not lend sub-$5 names (a prior).
   - Cells: the primary and one stop neighbour. Reported, never cells: the unconditional open short (rank 9), the
     continuation mirror (rank 7), >= $5 only, and the float split (rank 6). Family null: the trigger moved to random bars on
     the same event days.
3. **RUNNER2 r1** (rank 3): the same ruling and pull (day-2 bars).
   - Cells: the primary and one stop neighbour; the unconditional day-2 open short is reported. Overlap with PMFAIL is
     printed (same names).

Parked, not queued: GEXREV (rank 5) needs the owner's go via MANAGER and an S&P GEX series catalogued by TV's scout (start
date, publication time, restatement policy). Then it runs on ES, with counts after the stretch filter first.

The only data ask is the one gapper pull.

## The point-score-to-algo bridge

What the evidence allows:
- The score has no link to R on his trades (above), and round 2 turned its leads into a rule that went 0 of 40.
- Filters mined from tables die (ledger 2.1: 20 of 21 skip rules were regime artifacts; 2.2: 0 features promoted; 2.82:
  no filter, size or setting comes from anatomy tables).
- So the score never becomes a tuned filter, gate or size. Its honest uses are below.

1. **A label, not a gate.** Stamp ps1.2 on every crown signal and every CBU alert at the SIGNAL bar: the last bar closed
   at the decision, never the fill bar (19 of 46 journal "signals" were the still-forming entry minute;
   POINT_SCORE_BACKFILL). Store it; never act on it.
2. **The forward labelled set** (the lane's own fallback; needs no other lane).
   - CBU alerts are scored at the alert bar. Alerts bunch: a median of 1 a day but 9 or more on the busiest tenth (the
     up-trend days), with an alert on 52% of days (SETUPS_PREREG_R3_CBU_V1.md section 8), and NQ and ES fire together. So
     power is counted in alert-DAYS (~130 a year, NQ and ES pooled), not in alerts.
   - Inside an alert, the alert's own context forces point 7 (above yesterday's high) and so points 5-6; points 3-4 nearly
     (the alert uses 200 EMAs, the score 200 SMAs) (SETUPS_PREREG_R3_CBU_V1.md lines 366-370). The score varies mainly on
     points 1-2 and 8-9.
   - Each alert gets his mark: TOOK (an EL trade within the alert minute +/- 1); SHOULD HAVE TRADED (the missed feed; one
     entry so far, 2026-09-30 MNQ 09:59); NOT TAKEN.
   - One read: does his mark add R beyond the alert (marked minus unmarked mean R, blocked by day)? The old second read,
     "does the score rank R inside the alerts", is dropped: its mechanical outcomes can be replayed today
     (tools/cbu_v1_alerts.py replays every session), so it would re-test round 2's ground, not wait for new data.
   - Journal trades stay the answer key (Path A), never training data and never in any lockbox. His A+/A/B grades are
     given after the trade, so they are reported and never used as inputs. The 2024-25 tracker has no entry times.
   - Forward tags, not legs: the one-sided 10s burst after an alert (old BURST10S) is stored on the alert log. Nothing reads
     it before ~12 months of 10s history (ALGO_SCOPE Track C).
3. **What a read needs** (80% power, two-sided 5%):
   - Marked vs unmarked at equal group sizes: a 0.5 SD gap needs ~63 a group, 0.3 SD ~174, 0.2 SD ~392.
   - The marked group sets the clock. CBU is 12 of his 45 labelled futures trades from 04-07 to 09-24 (setups/README.md),
     ~2 a month; at the alert's in-sample recall of 9 of 13, ~1.5 TOOK marks a month. So 63 takes ~3.5 years, and the read
     is not taken before then.
   - For the journal itself: Spearman rho 0.30 needs ~85 trades, 0.20 ~194, 0.10 ~783 (the standard Fisher-z sample size).
     At ~8 labelled futures trades a month, his journal reaches 194 in ~2 years.
4. **PS-TAG: a REPORT offered to the NOISE lane, not a prereg slot.** Does the frozen score rank the R of trades the house
   already takes?
   - It can change no algo: filters and re-sizes on NOISE are closed (2.1; NOISE r70's gain sat inside the noise of one
     walk-forward, 2.53), and forward reads cannot decide either (BOOK.md 10y, Q16). It only decides whether the score stays
     a journal aid. MANAGER may fold it into the NOISE #422 anatomy (2.82).
   - Host: the NOISE #304 core trades, WF 2016-07-01..2025-06-29, NQ (2,797 trades; 2.82).
   - Constant points: NOISE's bands anchor at the max / min of the open and the prior close (augur_strategies/NOISE_1_0.py
     lines 576-581). So every long closes above yesterday's close and low, and every short below yesterday's close and high:
     points 5-6 (longs) and 6-7 (shorts) are always hit. Point 1 (10s) has no history. The score uses the six informative
     points: 2-4, 8-9, plus 7 (longs) or 5 (shorts).
   - Seen reads: NOISE round 47 read the 200-bar mean on NOISE trades at the signal bar (PF 1.039, "no candidate"; NOISE.md
     lines 875-889); the feature board scored distance to yesterday's high and the prior close's place in its range (2.2, 0
     promoted); the #422 anatomy tagged side x 200-day state (2.82). New here: points 8-9 (largest body / volume since the
     low) and the composite.
   - Scored on the last 1m bar closed at the NOISE signal bar's close: masters are start-stamped, so for a 5m bar starting
     at t that is the 1m bar starting at t+4.
   - Statistic (frozen): Spearman(score %, R), with R = P&L / initial risk at unit size. Secondary: top half vs bottom half
     at the WF median.
   - Null: 1,000 within-year shuffles of scores across trades, seed 20261005. Pass = rho above the null's 95th percentile
     AND the same sign in 2016-21 and 2022-25. Detectable rho at 80% power on 2,797 trades: ~0.05.
   - A fail retires the score as an algo input; it stays a journal aid. The NOISE lane signs off first, since it reads
     NOISE trades.

## Diagnostics every Stage A in this lane prints (addendum 2 item 2)

- The power line first, then the family null's 95th percentile, before the cell.
- Event-time path:
  - futures legs: mean R by minute from entry, 0..+390;
  - stock legs: the same, plus -30..0 before the signal and the premarket path from 04:00.
- Regime halves 2016-21 / 2022-25.
- Cost curve, with the break-even cost printed:
  - futures: gross, house cost (NQ 0.533 / ES 0.363 pt RT; MNQ 1.20 / MES 0.63, PREREG_RISK_R1.txt line 105), then +1 and
    +2 ticks a side;
  - stocks: 0 / 10 / 25 / 50 / 100 bps a side (the brief's 0/5/10/20 widened, since small-cap spreads are wider; a prior),
    and for shorts a locate of 0 / 0.5 / 1 / 2% of notional a trade.
- Per-year (July-June) rows; P&L in each of R's 45 episodes (binding) and in #463's drawdown episodes (report); correlation
  with each #463 leg and with RES, overall and inside R's days.
- Long and short apart; the top-10 share of net (trades and days); net without the best day and without the best trade.
- Overlap with crowns: shared days, same-direction share and net on each crown's flat days, for ORB #314, NOISE #382/#422,
  ENGU-Q #335 and TTM #459 (3 ES). For stock legs, daily P&L correlation with each crown and RES. BALANCE's
  opposite-direction share vs NOISE is read through the three-group day split, not as a hedge.
- No-2020 (2020-02-15..04-30) and no-2022 reads; no-2020-21 for the stock legs.
- Data notes:
  - the 2014-06-12/13 hole; roll handling for any level that spans sessions; the 2026 summer hole is outside the WF window;
  - the ES 5m RTH masters are incomplete on 2020-02-28 (18 of 78 bars) and 2020-06-30 (9 of 78); both sessions are skipped,
    as DDW did (tools/rocfrontier/PREREG_DDW_R1.txt, addendum 1);
  - stock bars are raw: split-like jumps flagged (split_like_gaps, tools/import_alpaca_stocks.py) and reverse splits listed
    by hand; Alpaca re-adjusts between pulls, so pull once, photograph, never patch.

## What could fool us

- **A classifier that peeks.** The NOISE band comes from prior sessions only; "unbroken by 12:00" uses only bars closed by
  12:00; GEX is the prior day's value and its tercile the trailing 252 sessions; float is the last filing before the day;
  gap filters use prior-day data plus the open itself.
- **Fade luck.** A1 says fades die, so a positive fade cell is more likely luck than usual. The family null covers every
  cell, and no cell is added after a number exists.
- **Meme years.** 40% of the gap events fall in calendar 2020-21, so the no-2020-21 read binds for the stock legs.
- **Tradability.** A result that needs sub-$5 shorts nobody will lend is not tradable; the >= $5 cell is reported beside it.
- **Tight stops on 1m bars.** 1m bars cannot judge tight stops (SIPORB, 2.60): stops are judged from the next bar, and both
  readings print.
- **GEX restatement.** A vendor GEX that is restated or back-filled would leak. Photograph it once and never patch.
- **Reading a classifier failure as a verdict on his eye.** A failed proxy does not refute his day-type read; it only says
  this proxy of it does not pay.
