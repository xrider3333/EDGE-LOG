# TV NEW-TYPE round 2 - three more new strategy TYPES on daily bars (DRAFT pre-registrations, 2026-10-05)

DRAFTS for MANAGER (standing order #28 queue of three; owner addendum #40 "lanes whose family is exhausted hunt new strategy
TYPES"). Round 1 (PAIRS, BAB, ONMOM) died at Stage A this morning (docs/TV_NEWTYPES_R1.md). Written before any number of any of
the three exists and before either new data file below has been fetched. Research names until something passes: **AUCTION**,
**COT**, **XASSET** (RUNBOARD rows under MISC by research id). Harness after review: `tools/tvnt2_triage.py`; results
`C:\EdgeLog\_anatomy_cache\tv_newtypes_r2\` + RESEARCH_LEDGER.md. Any change after the commit = a dated addendum.

## Why these three, and what is different from the dead list

Checked against the ledger, memory and today's lane preregs: no Treasury-auction, no futures-positioning (COT) and no cross-asset
signal test exists. Not repeats of: TREND r1 (each fund's OWN past return, dead 09-24), ROTATION / BAB (cross-sectional on past
return / beta), ORB NT3 SAFEHAVEN (intraday bonds and gold on equity-stress days - ORB's), FOMCWK / event days (Fed calendar on
NQ/ES), XGAP (single-stock gaps - FRONTIER/STRATEGY-BEATING's). Two of the three bring information the house has never used (the
Treasury's auction calendar; the CFTC's weekly positions).

## The map (docs/MDL_MAP_R1.md) - placed before drafting

- AUCTION trades Treasury funds on a supply calendar: no equity exposure, so rho_dd with #463 should sit near zero -> the line is
  ROC @ $30k >= 15 standalone. Plausible: the published 5-day pre-auction price concession on long bonds is of order 0.5-1 % of
  TLT, about 30 events a year per fund.
- COT is a long/short basket across 11 asset classes, risk-balanced: low rho_dd expected -> ROC >= 15.
- XASSET is directional on NQ/ES, so its drawdown-week sign is mixed (long in early 2020, short in 2022 by construction). The map
  needs ~30-40 at rho_dd >= 0.45, ~15 if rho_dd stays within +-0.15. Honest prior: the weakest of the three; it is drafted because
  2022 - the book's longest drawdown - is exactly where the published signal is short equities. A pass must clear the standalone
  bar; its seat is reported, never a pass route.

## Shared rules (all three; as round 1 unless stated)

- Every array cut before 2025-06-30 before any signal. EARLY = 2007-03-01 (2010-06-07 for NQ/ES futures) -> 2016-06-30, sign check;
  WF = 2016-07-01 -> 2025-06-29; LB sealed. $100,000 account, no compounding.
- Costs per side of notional: 2 bps SPY QQQ IWM TLT IEF GLD and the SPDR sectors; 5 bps SLV USO UUP FXA FXE FXY DBC TIP; NQ/ES
  futures $2.50 per micro per side + 1 tick slippage per side; stress = double. Borrow 0.25 %/yr on short fund notional.
- Yardstick, #463 reproduction (93.81 / 3.816 / $44,849), drawdown days, rho_dd and the realised beta reported per cell as round 1.
- HOUSE LINE #45 from the start: standalone Stage A decides; the book add is a REPORT at c = 0.25 x #463's daily std over the first
  two WF years / the cell's; Stage B = the leg's own sealed-year veto (one shared day, LOOKS r1: LB net > 0 on >= 50 trades and > 0
  without its biggest trade), the book add on that year reported only. A Stage-A pass -> RUNBOARD research row the same day + a
  written forward paper shadow (none of the three is an engine job type: two are baskets, XASSET reads TLT to trade NQ/ES).
- Power line printed per family (null 95th minus 50th). Zero passes = dead; the next draft is a new mechanism, never a re-tune.

## 1. AUCTION r1 - the Treasury auction supply cycle (Lou, Yan & Zhang 2013, RFS)

MECHANISM. Dealers must absorb large, scheduled Treasury supply. With limited risk-bearing capacity they need a price concession:
yields rise in the days before an auction and fall after it as the new issue is distributed to end investors. The calendar is
public, so the pattern is anticipated - and persists because arbitrage capital is limited and costly around auctions.
DATA (new; one fetch, sha256 printed): TreasuryDirect's public auctioned-securities record - for every NOTE and BOND auction since
2006: term, auction date, announcement date (no bills, TIPS or FRNs). 5-, 7- and 10-year auctions map to IEF; 20- and 30-year to
TLT (2- and 3-year dropped: SHY is excluded, IEF's duration is far longer). Fund closes as round 1 (Yahoo, one adjustment factor).
POSITIONS (per fund, close-to-close, because the calendar is known in advance and no price enters the signal): for each auction
day t on that fund, SHORT over the K sessions ending at t's close (in at the close of t-K-1 ... out at the close of t), LONG over
the K sessions after (close of t -> close of t+K). An auction is usable only if its announcement date is on or before the session
whose close opens the short; otherwise the short opens at the first close on or after the announcement. Overlaps: short beats long
(the next auction's concession dominates); one position per fund; notional $50,000 per fund. A trade = one contiguous position run.
CELLS: K = 3 and K = 5 (both funds pooled). Reported, never a pass route: the pre (short) and post (long) halves apart, IEF and
TLT apart, and a month-end row (long both funds over the last two sessions of each month - the index-extension demand of Hartley
& Schwarz 2019), because it lands near the end-of-month 2/5/7-year auctions.
NULL: every auction date moved by an independent random offset of 8-15 sessions (sign by coin), announcement lags kept, positions
rebuilt; statistic = MAX over the 2 cells of WF ROC @ $30k; 500 draws, seed 20261005.
STAGE A (WF, per cell): >= 100 trades; ROC @ $30k >= 15; PF >= 1.10; t >= 2.0 and ROC above the null's 95th; net > 0 at stress;
profitable without its biggest trade; BOTH funds net > 0 (the "without its best fund" veto with two funds); 6 of 9 July-June years;
net > 0 without 2020-02-15 .. 2020-04-30; EARLY net > 0.

## 2. COT r1 - hedging pressure across 11 futures markets, weekly (Bessembinder 1992; de Roon, Nijman & Veld 2000; Basu & Miffre 2013)

MECHANISM. Hedgers pay for insurance: when commercial hedgers are unusually net SHORT a market (producers locking in prices),
speculators who take the long side are paid a premium and the price drifts up; when hedgers are unusually net long, the reverse.
DATA (new; one fetch per year file, sha256 printed): the CFTC Commitments of Traders, legacy futures-only history: commercial long,
commercial short and open interest per market per week. Markets -> traded fund: E-mini S&P -> SPY, Nasdaq-100 mini -> QQQ, 10-year
note -> IEF, 30-year bond -> TLT, gold -> GLD, silver -> SLV, WTI crude -> USO, euro -> FXE, yen -> FXY, Australian dollar -> FXA,
dollar index -> UUP (11). TIMING: positions are as of Tuesday and released Friday 15:30 ET; the signal is used at the OPEN of the
first session after the release date - never at the Tuesday date. Holiday-delayed releases use their actual release date.
SIGNAL: HP = (commercial long - commercial short) / open interest; its percentile within that market's previous W weekly values.
LONG the 3 markets with the LOWEST percentile (hedgers most net short vs their own history), SHORT the 3 highest. Each position
sized to equal risk: $ notional = $1,000 / that fund's 60-session daily return std (from closes through the signal day), capped at
$50,000 per fund. Rebalance weekly at the open after release; held to the next rebalance.
CELLS: W = 52 and W = 156 weeks (2 cells). Controls, never a pass route: the opposite sign (the practitioner "follow the
commercials" reading, which is the same data read the other way) and the overlap with time-series momentum (share of weeks the
long set's own 12-1 month returns are positive - hedgers sell forward after rallies, so a COT pass that is just momentum would be
TREND r1 again, dead; reported, and a pass whose overlap exceeds 70 % is flagged to MANAGER before any shadow).
NULL: each week the 3 longs and 3 shorts drawn at random from the 11, same sizing and costs; statistic = MAX over the 2 cells of WF
ROC @ $30k; 500 draws, seed 20261005.
STAGE A (WF, per cell): >= 400 weekly rebalances; ROC @ $30k >= 15; PF (weekly) >= 1.10; t >= 2.0 and above the null's 95th; net
> 0 at stress; profitable without its best week AND without its best market; 6 of 9 years; net > 0 without 2020-02-15 .. 04-30;
EARLY net > 0.

## 3. XASSET r1 - bonds signal stocks: cross-asset time-series momentum on NQ and ES (Pitkajarvi, Suominen & Vaittinen 2020, JFE)

MECHANISM. Capital moves slowly between asset classes: a bond rally (falling discount rates, rising risk appetite of balanced
investors rebalancing) is followed by equity gains, and a bond sell-off by equity losses; the paper finds past bond returns
positively predict equity index returns across countries, beyond the equity's own momentum.
DATA (on hand): TLT closes (yahoo_adj) for the signal; NQ and ES futures from the back-adjusted RTH masters (db_adj_rth, 16:00
close) in POINTS, raw level (db_noadj_rth) only for sizing - per the house rule on adjusted masters.
SIGNAL (Friday close): TLT's return over the previous L sessions (skipping the most recent 5, the paper's skip). POSITION from
Monday's RTH open to the next Monday's open: LONG NQ and ES if the signal > 0, SHORT if < 0. Whole micros per instrument:
n = max(1, round($50,000 / (raw level x $2 for MNQ | $5 for MES))). Marked at every 16:00 close.
CELLS: L = 21 and L = 252 sessions (2 cells; NQ and ES pooled). Controls (both must be BEATEN on WF ROC @ $30k - the raw-twin
rule): the own-asset twin (same rule on each future's OWN past return - the dead daily-trend family) and buy-and-hold at the same
size. Reported: the bond-side mirror the paper also prints (TLT short when the equity's own L-return > 0), never a pass route.
NULL: the TLT signal series circularly shifted by a random offset of 252-2,000 sessions (keeps its persistence and long/short mix,
breaks its timing); statistic = MAX over the 2 cells of WF ROC @ $30k; 500 draws, seed 20261005.
STAGE A (WF, per cell): >= 400 weekly holdings; ROC @ $30k >= 15; PF (weekly) >= 1.10; t >= 2.0 and above the null's 95th; beats
the own-asset twin AND buy-and-hold; net > 0 at stress; profitable without its best week; BOTH NQ and ES net > 0; 6 of 9 years; net
> 0 without 2020-02-15 .. 04-30; EARLY net > 0. Seat report (never a gate): #463 drawdown-day dollars, without the best episode.

## How these could fool us

1. AUCTION: a few sharp rate shocks (2020-03, 2022) inside an event window can carry the book - the without-biggest-trade, 6-of-9
   and ex-2020 vetoes; the announcement-date rule keeps the calendar honest; Yahoo TLT/IEF closes vs the auction's 13:00 ET result
   time (the concession peaks around the result; the close is after it - a conservative choice, said here).
2. COT: legacy "commercials" in financial futures are dealers and asset managers, not producers - the mechanism is cleanest in
   commodities; per-market rows are reported. Report-date vs release-date confusion is the classic COT look-ahead - the harness
   asserts every signal date >= its release date. Contract-code changes (e.g. the E-mini and the 10-year renamed codes) are mapped
   by name and checked for gaps.
3. XASSET: an equity long most of the decade earns the equity premium whatever the signal - hence the buy-and-hold and own-asset
   twins must be beaten, and the null keeps the signal's long share. Futures back-adjustment: points only.
4. Three families x two cells; each family's null covers its own cells; the round is reported as three hypotheses.

## Addendum 1 (2026-10-05 09:05 MST, PRE-DATA - MANAGER review C:/EdgeLog/manager/reviews/tv_newtypes_r2_review_2026-10-05.md)

No number of any of the three exists and neither public file has been fetched. Folded in before Stage A:
0. DATA PROVENANCE: each public file is saved byte-for-byte as fetched (the raw JSON response) under C:\EdgeLog\_research_cache\
   with its URL, fetch time, size and sha256 recorded below under "Provenance" before Stage A runs; the harness parses the raw
   file; nothing is re-fetched into a result (a cache is a photograph).
1. AUCTION. (a) The offering amount of every auction is reported, and the P&L of each cell is split by SIZE TERCILE (terciles
   within each original term, pooled) - the concession should scale with supply; a pass whose top tercile does not out-earn its
   bottom tercile is flagged to MANAGER before any shadow. (b) EARLY CLOSES: an auction is skipped when any session of its
   window (the K sessions before through the K after) is a listed early-close session: the day after Thanksgiving, December 24,
   December 31, July 3 (each when it is a trading day) and the session before Good Friday. The count of skipped auctions is
   printed, and the all-auctions version as a report row. (c) The WF halves 2016-07..2019-12 and 2020-01..2025-06 are printed
   apart (the Fed's balance sheet changed who absorbs supply). (d) The month-end row stays report-only.
2. COT. (a) RELEASE TIMING: the CFTC does not publish its release calendar for 2006-2025 as one data file, so the harness uses a
   rule that is never earlier than any published release: a report is usable at the OPEN of the first session on or after its
   report date + 7 calendar days (the Tuesday after the normal Friday release, and after every holiday-shifted Monday release);
   the two government-shutdown backlogs are held longer - reports dated 2013-10-01..2013-11-26 usable from 2013-12-03, reports
   dated 2018-12-25..2019-03-05 usable from 2019-03-12 (the catch-up finished 2019-03-08). Cost: about one session of freshness
   vs the real release; never look-ahead. (b) CURRENCY CLUSTER: UUP, FXE and FXY are reported as one dollar bet - the share of
   weeks in which two or more of them express the SAME dollar direction (UUP long = long dollar; FXE / FXY long = short dollar)
   is printed beside the momentum-overlap flag; above 50 % is flagged to MANAGER with any pass. (c) The realised gross exposure
   per week (min / median / max) is printed.
3. XASSET. (a) NOISE's BONDLEAD r1 (intraday: the bond MORNING sets NQ's afternoon) and XASSET (weekly: TLT's past return sets
   the NQ/ES side) are the SAME cross-asset mechanism at two horizons: if both run, their daily-P&L correlation is reported, and
   if both pass they are ONE finding, not two. (b) If XASSET's seat is quoted, it must also beat its own-asset twin on #463's
   drawdown-day dollars (printed). (c) Rounding: n = max(1, round($50,000 / (raw level x $2 MNQ | $5 MES))) WHOLE micros,
   recomputed each week from the raw close before entry; the cost of changing n is charged like any trade.
4. All three: house line #45 as written; the power line per family is printed FIRST in each family's report.

## Provenance (addendum 1 item 0; fetched 2026-10-05 after MANAGER's go #47, before Stage A)

- treasury_auctions: 557,459 bytes, sha256 75e2f5e315fab14855a63f14097f50e4686dd49ba80d0f9de0267569298d785c, fetched 2026-10-05T08:59:43-07:00, saved unmodified as C:\EdgeLog\_research_cache\treasury_auctions_raw.json
  URL: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?fields=cusip,security_type,security_term,original_security_term,auction_date,announcemt_date,issue_date,reopening,offering_amt,inflation_index_security,floating_rate&filter=security_type:in:(Note,Bond),auction_date:gte:2005-01-01&sort=auction_date&page[size]=10000
- cot_legacy_futures: 3,649,702 bytes, sha256 6d24ca71cc9e201d6b7acc8fb768652b5586e6c580023806035eea2ee86fcae8, fetched 2026-10-05T08:59:44-07:00, saved unmodified as C:\EdgeLog\_research_cache\cot_legacy_futures_raw.json
  URL: https://publicreporting.cftc.gov/resource/6dca-aqww.json?%24select=market_and_exchange_names%2Creport_date_as_yyyy_mm_dd%2Ccftc_contract_market_code%2Copen_interest_all%2Ccomm_positions_long_all%2Ccomm_positions_short_all&%24where=cftc_contract_market_code+in%28%2713874A%27%2C%27209742%27%2C%27043602%27%2C%27020601%27%2C%27088691%27%2C%27084691%27%2C%27067651%27%2C%27099741%27%2C%27097741%27%2C%27232741%27%2C%27098662%27%29+AND+report_date_as_yyyy_mm_dd+%3E%3D+%272003-01-01T00%3A00%3A00%27&%24order=report_date_as_yyyy_mm_dd&%24limit=50000
- Checked before any signal: 1,905 note/bond auction rows (2005-); COT 13,625 rows, all 11 contract codes resolve to the
  intended markets by name (the renamed UST BOND / UST 10Y NOTE / WTI-PHYSICAL / NASDAQ MINI codes are continuous series).

## RESULTS - Stage A, walk-forward only (run 2026-10-05 08:59-09:10 MST, harness 615632e3; lockbox never loaded)

#463 reproduced 93.81 / 3.816 / $44,849 first. Data sha256 (first 16): fund caches as round 1, treasury_auctions 75e2f5e315fab148,
cot_legacy_futures 6d24ca71cc9e201d. 951 note/bond auctions (IEF 684 events, TLT 265; announcement lag median 6 days, max 8),
COT 11 markets x 1,172 weeks, futures 3,750 sessions each. Printout + JSON: `C:\EdgeLog\_anatomy_cache\tv_newtypes_r2\`.

**ALL THREE FAMILIES DEAD - 0 of 6 cells pass Stage A.**

- **AUCTION** (power line ~5 ROC points; null 95th 3.5). K 3: ROC @ $30k 3.7, net +$27.8k, DD $25.3k, PF 1.21, t 1.74, 6 of 9 years,
  EARLY +$20.6k. K 5: ROC 7.9, net +$35.5k, DD $14.9k, PF 1.25, t 1.997 (bar 2.0), 7 of 9 years, EARLY +$27.9k, stress +$23.0k,
  both halves positive (2016-19 +$10.9k, 2020-25 +$24.6k), both funds positive (TLT +$31.9k, IEF +$3.6k). Fails on ROC >= 15 (both
  cells) and t (both). THE NEAR-MISS OF THE DAY, and it looks like the published effect: the PRE-auction short carries it (+$34.7k;
  the post-auction long loses -$7.7k), the P&L rises with auction size (small -$0.9k, mid +$8.5k, large +$13.5k), it was positive
  in 2007-16 when TLT's drift ran against a short, and it beats the shifted-calendar null that keeps the same short exposure. It is
  real and too small: about $4k a year at a $15k drawdown, half the map's line. Early-close skips: 82 / 7 auctions (K 3), 119 / 22
  (K 5); all-auctions rows 2.9 / 8.7. Month-end row (report): 9.1, +$13.1k. Seat (K 3) +$17.7k over #463's drawdown episodes
  (+$11.1k without the best) but K 5 only +$3.2k (-$1.1k without the best): the seat is not stable across K.
- **COT** (power line ~3; null 95th 0.9). W 52: ROC -3.3, net -$195k, t -3.39; W 156: ROC -2.9, net -$184k, t -3.12; EARLY
  -$185k / -$191k. The hedging-pressure sign LOSES, clearly: before costs about -$94k over nine years (costs about $11k a year at
  ~$300k weekly gross), so the practitioner reading (follow the commercials - the control) makes about +$94k gross but still nets
  -$13k / -$24k after the same costs. SLV and USO lose most (-$63k / -$61k). Momentum overlap 0.55 / 0.63 (under the 70 % flag);
  currency cluster 0.51 / 0.44.
- **XASSET** (power line ~8; null 95th 10.9). L 21: ROC 0.3, net +$5.8k; L 252: ROC 2.3, net +$32.3k, t 0.65. Both lose to
  buy-and-hold at the same size (ROC 13.0, +$137k) - the TLT signal subtracts value from simply holding. L 252's seat is the
  mechanism's one bright spot (+$48.7k over #463's drawdown episodes vs the own-asset twin's -$38.1k; 2021-22 +$35.6k) but it
  pays for it in 2022-24 (-$38.0k). BONDLEAD correlation not computed (BONDLEAD has not run).

Book-add REPORTS (house line #45, gate nothing): AUCTION K 3 at c 1.70 prints 107.65 / 3.907 over #463 - on a leg failing Stage A,
on a seat that does not hold at K 5; not a finding. Everything else sits at or below #463.

What the round leaves for MANAGER (not proposed by the rule "zero passes = dead, never a re-tune"): the pre-auction TLT short is
the only mechanism of six this round with the published fingerprints (size scaling, out-of-period sign, both halves). On data
already read it can only ever be a FORWARD paper shadow with a bar written first - an owner / MANAGER call, not a lane decision.
