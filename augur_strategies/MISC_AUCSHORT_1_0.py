# AUGUR-SOURCE: claude-review
"""MISC AUCSHORT 1.0 - short the matching bond ETF ($300,000) on Treasury coupon-auction mornings, 09:35 -> 12:55 ET.

Provenance: OPUS-HUNT futures, strategy 135 (AUCDAY-AM), verdict cell 135a, and 151 part A (the book seat at 3 units)
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S135: PREREG.md, RESULTS.md, s135_eval.py, trades.csv, series.pkl;
audit S135/verify_lookahead/VERIFY.md: independent re-implementation, 492 = 492 trades to $0.000000, verdict NOT
REFUTED WITH WARNINGS). Mechanism (prereg): the auction supply concession (Lou, Yan, Zhang 2013) - dealers pre-hedge
scheduled coupon supply by selling duration into the 13:00 ET auction close, so the matching bond fund drifts down
through the auction morning. Direction fixed by the hypothesis: SHORT.
What the hunt read, per ONE $100,000 unit, 2016-07-01 .. 2025-06-30: 492 trades (54.7 a year; IEF 324, TLT 168), gross
+4.25 bp a trade against 1.53 bp cost, net +$13,417 ($1,491 a year), max drawdown about $3.4k. Placebo (the audit):
random non-auction mornings, same count per year and fund, 500 draws - the real net sits at the 99.6th percentile on
2019-01 .. 2025-06 and at the 100th on the whole window (the tester's shifted-calendar null: 99.4th).
WARNINGS (read them before believing the number):
  * NOT A BLIND READ. 2016-07 .. 2018-12 was the proposer's EXPLORE window (seen; +$1,058 of the $13,417); the hunt
    JUDGED 2019-01 .. 2025-06 (+$12,359, net t 1.82; halves 1.93 / 0.86). The house ledger (2.70) already held
    auction-day close-to-close returns, so the judged window was partly seen too.
  * ABOUT HALF THE PROFIT IS CALENDAR 2019 ($6,879 of the judged $12,359); the ten best trades are $11,096; win rate
    49.9 pct. Verdict under the strict bars: Route A FAIL, Route B (book add) MISSED - it is a SCREEN-PASS under the
    owner's loose screen only.
  * SMALL EDGE: about $4,474 a year at the $300,000 seat (3 x $1,491), drawdown about $10k. Cost is 36 pct of gross.
  * SAME MORNINGS AS THE EVENT SLEEVE forward shadow leg A: one seat, never count the two as two edges.
  * CAPITAL: a $300,000 intraday short needs about $75,000 of day-trade buying power (4:1) and a locate; no borrow
    fee accrues (opened and covered inside one session).
  * The ZN futures version of this morning failed on cost; the edge exists only at the ETF's cost.
  * 5 of the 492 trades are 2- / 3-Year note sales that reopened an old 5 / 7 / 10-Year CUSIP (the fund map reads the
    ORIGINAL term, as the harness of record does): 2017-04-25, 2017-10-24, 2019-03-26, 2019-04-23, 2019-11-05, net +$85.
  * Auction close time is not in the source file: 13:00 ET assumed (an 11:30 ET auction day covers after the result).
  * Entry timing matters: a 09:40 entry keeps 80 pct, 09:45 69 pct of the judged net (audit). IEF fill bars are thin
    on 6 (entry) / 28 (exit) of 324 days at $100k; at $300k the open print will not fill the order at one price.
The 2025-07 .. 2026-06 lockbox was never read by the hunt or by this file's builder.
This file exists so the engine's Auto-Validate can judge the rule.

-- The rule (the prereg's; nothing here is tuned) -----------------------------------------------------------------
1. Auction days: the frozen calendar below - Treasury Notes and Bonds, not inflation-indexed, not floating-rate, by
   ORIGINAL security term: 5 / 7 / 10-Year -> IEF, 20 / 30-Year -> TLT. Several auctions for one fund on one day = ONE
   trade for that fund; IEF and TLT on the same day = two trades (no such day exists through 2026-10).
2. Days dropped (exchange calendar, known in advance): (i) NYSE early-close sessions, (ii) the last session before a
   full-day NYSE closure; and (iii) days where the fund lacks a full session (a 09:35 bar, a 12:55 bar and a 15:55
   last bar) or a prior raw close. An auction on a dropped day gets no trade - never rolled to another day.
3. SELL SHORT at the OPEN of the 5m bar stamped 09:35 ET; BUY TO COVER at the OPEN of the bar stamped 12:55 ET, the
   same session. No stop, no target, no filter, no overnight hold. `funds` picks both funds (135a), IEF only or TLT
   only (the hunt's THIN side cell 135b).
TRADE <-> BARS: entry bar = the job's 09:35 bar, exit bar = the job's 12:55 bar of the same session; a trade needs the
session whole inside the job's bars (09:35 bar, 12:55 bar, last bar 15:55), so a walk-forward slice that starts after
09:35 or ends before the 15:55 bar of an auction day takes no trade for it - a slice edge never opens a trade late or
closes it early. Every trade opens and closes inside one session: mark_open_trades returns no marks.

INFORMATION TIMES (every input known at or before the 09:35 entry print):
  * WHICH DAYS TRADE comes only from the frozen point-in-time auction calendar and the exchange calendar. The calendar
    is a LATER pull (2026-10-05) of Treasury's record, so an auction is used only when its ANNOUNCEMENT date is on or
    before the session before the auction day (knowable by the prior close; the harness used announcement < auction
    date - the tighter rule changes none of its 492 trades: every kept announcement leads its auction by 4 to 8
    calendar days). The test is applied twice: when the table was frozen, and again at run time against the panel's
    own session list (_knowable). Two rows fail it and are NOT in the table (announcement date = auction date in the
    file): 10-Year 2019-06-21, 20-Year 2021-12-02. Not verifiable here: that no auction was moved after it was
    announced (needs the original announcements).
  * the exchange calendar (early closes, closures) is the NYSE's, published in advance; the one unscheduled closure in
    the window (2025-01-09, announced 2024-12-30) drops the auction day before it, 2025-01-08, as the harness did.
  * shares and cost: floor(N / the PRIOR session's RAW close) - yesterday's print.
  * the entry price is the 09:35 bar's open (the bar starts at the decision time; a calendar rule has no signal bar).
  * the 12:55 print is read for the P&L ONLY. The one fact about the rest of the session used before that is whether
    the session is whole (bar times, rule iii) - a clock fact, never a price; 0 of the hunt's auction days failed it.
tests/test_misc_aucshort.py scrambles everything known only after the entry print and checks that no trade moves, and
that four broken variants (shares from the 12:55 price; a day skipped when the morning went against the short; a
calendar row announced after the entry; a TLT entry read from the 09:40 bar) are caught.

-- Data ----------------------------------------------------------------------------------------------------------
THE JOB'S MASTER = TLT 5m RTH, source alpaca_split_rth (engine master id 114, master_296d3997.csv, 2016-01-04 ..
2026-06-30, 2,637 sessions; neither fund split in the window and the tape is not dividend-adjusted, so prices are
traded prices): the bar clock of every trade AND the entry / exit prices of the TLT trades. TLT prices are read from
the job's own bars, not the panel, on purpose: the master is the fund, so the engine trades the tape it was handed
(a re-pulled master shows in the result instead of hiding behind a stale panel); tools/misc_aucshort_parity.py checks
the bars equal the panel's TLT columns on every traded day. What the master cannot carry comes from the pinned side
panel (sha256 checked)
    C:/EdgeLog/alpaca_cache/aucshort_panel/aucshort_panel_v1.npz   (built by tools/misc_aucshort_panel.py)
= the session calendar; `calskip` (rules i / ii, an exchange-calendar code per session); IEF's 09:35 and 12:55 opens
and its full-session flag from the IEF 5m RTH alpaca_split_rth master (id 76), built as s135_eval.py's load(); and
both funds' prior RAW closes (C:/EdgeLog/alpaca_cache/etf_daily/<F>_1Day_raw.csv, shifted one session).
No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.

AUCTION CALENDAR (frozen below, 2016-01-13 .. 2026-10-08, 602 rows: IEF 395, TLT 207). Source:
C:/EdgeLog/_research_cache/treasury_auctions_raw.json, pulled 2026-10-05 from Treasury's public auction query (1,905
rows 2005-01-12 .. 2026-10-08). Filter (tools/misc_aucshort_panel.py --calendar prints these strings): security_type
Note / Bond, inflation_index_security No, floating_rate No, original_security_term 5 / 7 / 10 / 20 / 30-Year,
announcemt_date <= the NYSE session before auction_date. Token = auction date : announcement date : original term in
years. The JSON is never read at run time.

-- Sizing and costs (INSIDE the plugin: job cost_pts 0, mult 1) --------------------------------------------------
N = `notional` ($300,000, the book seat = 3 of the hunt's $100,000 units) a trade. px = the prior raw close, shares =
floor(N / px), gross = shares x (open 09:35 - open 12:55). Cost = 2 x (`cents_share` cents x shares + `fee_bps` bp x
px x shares) = 2 x (0.5 c a share + 0.3 bp), priced on the prior raw close (the hunt's formula; about 1.5 bp a round
trip). Net = gross - cost, DOLLARS in the trade tuple's field 2; side -1; entry / exit prices = the two opens of the
traded fund. The harness used fractional shares on the entry print (gross = -N x (o1255 / o935 - 1)); floor(N / prior
raw close) shares make the dollars short at 09:35 = shares x o935, a few tenths of a pct off N either way, plus under
one share lost at the floor - tools/misc_aucshort_parity.py shows the fractional replica matching trades.csv and the
size of that gap.

-- Auto-Validate ranges ------------------------------------------------------------------------------------------
OPEN: funds (both, IEF_only, TLT_only) = 3 grid points; both = cell 135a, TLT_only = cell 135b. The entry and exit
clocks are the prereg's and are not knobs, and no knob was added to pad the grid. PINNED (min = max = hard bounds):
notional, cents_share, fee_bps. No numeric knob is open, so nothing can auto-expand.
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC AUCSHORT 1.0 · short IEF / TLT on Treasury coupon-auction mornings 09:35 -> 12:55 (opus hunt 135a)'
DESCRIPTION = ("On Treasury coupon-auction days short $300,000 of the matching bond fund (5/7/10-Year -> IEF, "
               "20/30-Year -> TLT) at the open of the 09:35 ET bar and cover at the open of the 12:55 ET bar: the "
               "auction supply concession. Days come from a frozen point-in-time auction calendar. Runs on the TLT 5m "
               "master (the clock, and TLT's prices); IEF prices and prior raw closes come from a pinned side panel. "
               "Costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "TLT", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/aucshort_panel/aucshort_panel_v1.npz"
PANEL_SHA256 = "f21ead08c279dc22a8947514bea0a0501577e83dfeb6d5c86507456f3eafdf50"   # built 2026-11-18, 2,637 sessions
PANEL_KEYS = ("dates", "calskip", "TLT_o935", "TLT_o1255", "TLT_full", "TLT_prevraw",
              "IEF_o935", "IEF_o1255", "IEF_full", "IEF_prevraw")

# ---- the frozen point-in-time auction calendar (source, pull date and filter in the docstring) ---------------------
# token = auction yyyymmdd : announcement yyyymmdd : original term in years
_TLT_AUCTIONS = (
    "20160114:20160107:30 20160211:20160203:30 20160310:20160303:30 20160414:20160407:30 20160512:20160504:30 "
    "20160609:20160602:30 20160713:20160707:30 20160811:20160803:30 20160913:20160908:30 20161013:20161006:30 "
    "20161110:20161102:30 20161213:20161208:30 20170112:20170105:30 20170209:20170201:30 20170309:20170302:30 "
    "20170412:20170406:30 20170511:20170503:30 20170613:20170608:30 20170713:20170706:30 20170810:20170802:30 "
    "20170913:20170907:30 20171012:20171005:30 20171109:20171101:30 20171212:20171207:30 20180111:20180104:30 "
    "20180208:20180131:30 20180313:20180308:30 20180412:20180405:30 20180510:20180502:30 20180612:20180607:30 "
    "20180712:20180705:30 20180809:20180801:30 20180913:20180906:30 20181011:20181004:30 20181107:20181031:30 "
    "20181213:20181206:30 20190110:20190103:30 20190207:20190130:30 20190313:20190307:30 20190411:20190404:30 "
    "20190509:20190501:30 20190613:20190606:30 20190711:20190703:30 20190808:20190731:30 20190912:20190905:30 "
    "20191010:20191003:30 20191107:20191030:30 20191212:20191205:30 20200109:20200102:30 20200213:20200205:30 "
    "20200312:20200305:30 20200408:20200402:30 20200513:20200506:30 20200520:20200514:20 20200611:20200604:30 "
    "20200617:20200611:20 20200709:20200702:30 20200722:20200716:20 20200813:20200805:30 20200819:20200813:20 "
    "20200910:20200903:30 20200915:20200910:20 20201008:20201001:30 20201021:20201015:20 20201112:20201104:30 "
    "20201118:20201112:20 20201210:20201203:30 20201221:20201217:20 20210113:20210107:30 20210120:20210114:20 "
    "20210211:20210203:30 20210217:20210211:20 20210311:20210304:30 20210316:20210311:20 20210413:20210408:30 "
    "20210421:20210415:20 20210513:20210505:30 20210519:20210513:20 20210610:20210603:30 20210615:20210610:20 "
    "20210713:20210708:30 20210721:20210715:20 20210812:20210804:30 20210818:20210812:20 20210909:20210902:30 "
    "20210921:20210916:20 20211013:20211007:30 20211020:20211014:20 20211110:20211103:30 20211117:20211110:20 "
    "20211209:20211202:30 20211221:20211216:20 20220113:20220106:30 20220119:20220113:20 20220210:20220202:30 "
    "20220216:20220210:20 20220310:20220303:30 20220323:20220317:20 20220413:20220407:30 20220420:20220414:20 "
    "20220512:20220504:30 20220518:20220512:20 20220609:20220602:30 20220622:20220616:20 20220713:20220707:30 "
    "20220720:20220714:20 20220811:20220803:30 20220817:20220811:20 20220913:20220908:30 20220920:20220915:20 "
    "20221013:20221006:30 20221019:20221013:20 20221110:20221102:30 20221116:20221110:20 20221213:20221208:30 "
    "20221221:20221215:20 20230112:20230105:30 20230118:20230112:20 20230209:20230201:30 20230215:20230209:20 "
    "20230309:20230302:30 20230321:20230316:20 20230413:20230406:30 20230419:20230413:20 20230511:20230503:30 "
    "20230517:20230511:20 20230613:20230608:30 20230621:20230615:20 20230713:20230706:30 20230719:20230713:20 "
    "20230810:20230802:30 20230823:20230817:20 20230913:20230907:30 20230919:20230914:20 20231012:20231005:30 "
    "20231018:20231012:20 20231109:20231101:30 20231120:20231116:20 20231212:20231207:30 20231220:20231214:20 "
    "20240111:20240104:30 20240117:20240111:20 20240208:20240131:30 20240221:20240215:20 20240313:20240307:30 "
    "20240319:20240314:20 20240411:20240404:30 20240417:20240411:20 20240509:20240501:30 20240522:20240516:20 "
    "20240613:20240606:30 20240618:20240613:20 20240711:20240703:30 20240717:20240711:20 20240808:20240731:30 "
    "20240821:20240815:20 20240912:20240905:30 20240917:20240912:20 20241010:20241003:30 20241023:20241017:20 "
    "20241106:20241030:30 20241120:20241114:20 20241212:20241205:30 20241217:20241212:20 20250108:20250102:30 "
    "20250122:20250116:20 20250213:20250205:30 20250219:20250213:20 20250313:20250306:30 20250318:20250313:20 "
    "20250410:20250403:30 20250416:20250410:20 20250508:20250430:30 20250521:20250515:20 20250612:20250605:30 "
    "20250616:20250612:20 20250710:20250703:30 20250723:20250717:20 20250807:20250730:30 20250820:20250814:20 "
    "20250911:20250904:30 20250916:20250911:20 20251009:20251002:30 20251022:20251016:20 20251113:20251105:30 "
    "20251119:20251113:20 20251211:20251204:30 20251217:20251211:20 20260113:20260108:30 20260121:20260115:20 "
    "20260212:20260204:30 20260218:20260212:20 20260312:20260305:30 20260317:20260312:20 20260409:20260402:30 "
    "20260422:20260416:20 20260513:20260506:30 20260520:20260514:20 20260611:20260604:30 20260616:20260611:20 "
    "20260709:20260702:30 20260722:20260716:20 20260813:20260805:30 20260819:20260813:20 20260910:20260903:30 "
    "20260915:20260910:20 20261008:20261001:30 "
)
_IEF_AUCTIONS = (
    "20160113:20160107:10 20160127:20160121:5 20160128:20160121:7 20160210:20160203:10 20160223:20160218:5 "
    "20160224:20160218:5 20160226:20160218:7 20160309:20160303:10 20160329:20160324:5 20160330:20160324:7 "
    "20160413:20160407:10 20160426:20160421:5 20160428:20160421:7 20160511:20160504:10 20160525:20160519:5 "
    "20160526:20160519:7 20160608:20160602:10 20160621:20160616:5 20160622:20160616:7 20160712:20160707:10 "
    "20160726:20160721:5 20160728:20160721:7 20160810:20160803:10 20160824:20160818:5 20160825:20160818:7 "
    "20160912:20160908:10 20160927:20160922:5 20160928:20160922:7 20161012:20161006:10 20161026:20161020:5 "
    "20161027:20161020:7 20161109:20161102:10 20161122:20161117:5 20161123:20161117:7 20161212:20161208:10 "
    "20161228:20161222:5 20161229:20161222:7 20170111:20170105:10 20170125:20170119:5 20170126:20170119:7 "
    "20170208:20170201:10 20170222:20170216:5 20170223:20170216:7 20170308:20170302:10 20170328:20170323:5 "
    "20170329:20170323:7 20170411:20170406:10 20170425:20170420:7 20170426:20170420:5 20170427:20170420:7 "
    "20170510:20170503:10 20170524:20170518:5 20170525:20170518:7 20170612:20170608:10 20170627:20170622:5 "
    "20170628:20170622:7 20170712:20170706:10 20170726:20170720:5 20170727:20170720:7 20170809:20170802:10 "
    "20170828:20170824:5 20170829:20170824:7 20170912:20170907:10 20170927:20170921:5 20170928:20170921:7 "
    "20171011:20171005:10 20171024:20171019:5 20171025:20171019:5 20171026:20171019:7 20171108:20171101:10 "
    "20171127:20171122:7 20171128:20171122:7 20171211:20171207:10 20171227:20171221:7 20171228:20171221:7 "
    "20180110:20180104:10 20180124:20180118:5 20180125:20180118:7 20180207:20180131:10 20180221:20180215:5 "
    "20180222:20180215:7 20180312:20180308:10 20180327:20180322:5 20180328:20180322:7 20180411:20180405:10 "
    "20180425:20180419:5 20180426:20180419:7 20180509:20180502:10 20180523:20180517:5 20180524:20180517:7 "
    "20180611:20180607:10 20180627:20180621:5 20180628:20180621:7 20180711:20180705:10 20180725:20180719:5 "
    "20180726:20180719:7 20180808:20180801:10 20180828:20180823:5 20180829:20180823:7 20180912:20180906:10 "
    "20180925:20180920:5 20180927:20180920:7 20181010:20181004:10 20181024:20181018:5 20181025:20181018:7 "
    "20181106:20181031:10 20181127:20181121:5 20181128:20181121:7 20181212:20181206:10 20181226:20181220:5 "
    "20181227:20181220:7 20190109:20190103:10 20190128:20190124:5 20190129:20190124:7 20190206:20190130:10 "
    "20190225:20190221:5 20190226:20190221:7 20190312:20190307:10 20190326:20190321:7 20190327:20190321:7 "
    "20190328:20190321:7 20190410:20190404:10 20190423:20190418:7 20190424:20190418:5 20190425:20190418:7 "
    "20190508:20190501:10 20190528:20190523:7 20190529:20190523:7 20190612:20190606:10 20190626:20190620:5 "
    "20190627:20190620:7 20190710:20190703:10 20190724:20190718:5 20190725:20190718:7 20190807:20190731:10 "
    "20190828:20190822:5 20190829:20190822:7 20190911:20190905:10 20190925:20190919:5 20190926:20190919:7 "
    "20191009:20191003:10 20191023:20191017:5 20191024:20191017:7 20191105:20191030:10 20191106:20191030:10 "
    "20191126:20191121:5 20191127:20191121:7 20191210:20191205:10 20191224:20191219:5 20191226:20191219:7 "
    "20200108:20200102:10 20200127:20200123:5 20200128:20200123:7 20200212:20200205:10 20200226:20200220:5 "
    "20200227:20200220:7 20200311:20200305:10 20200325:20200319:5 20200326:20200319:7 20200407:20200402:10 "
    "20200427:20200423:5 20200428:20200423:7 20200512:20200506:10 20200527:20200521:5 20200528:20200521:7 "
    "20200609:20200604:10 20200624:20200618:5 20200625:20200618:7 20200708:20200702:10 20200727:20200723:5 "
    "20200728:20200723:7 20200812:20200805:10 20200826:20200820:5 20200827:20200820:7 20200909:20200903:10 "
    "20200923:20200917:5 20200924:20200917:7 20201007:20201001:10 20201028:20201022:5 20201029:20201022:7 "
    "20201110:20201104:10 20201123:20201119:5 20201124:20201119:7 20201209:20201203:10 20201228:20201224:5 "
    "20201229:20201224:7 20210112:20210107:10 20210126:20210121:5 20210128:20210121:7 20210210:20210203:10 "
    "20210224:20210218:5 20210225:20210218:7 20210310:20210304:10 20210324:20210318:5 20210325:20210318:7 "
    "20210412:20210408:10 20210426:20210422:5 20210427:20210422:7 20210512:20210505:10 20210526:20210520:5 "
    "20210527:20210520:7 20210609:20210603:10 20210623:20210617:5 20210624:20210617:7 20210712:20210708:10 "
    "20210727:20210722:5 20210729:20210722:7 20210811:20210804:10 20210825:20210819:5 20210826:20210819:7 "
    "20210908:20210902:10 20210927:20210923:5 20210928:20210923:7 20211012:20211007:10 20211027:20211021:5 "
    "20211028:20211021:7 20211109:20211103:10 20211122:20211118:5 20211123:20211118:7 20211208:20211202:10 "
    "20211228:20211223:5 20211229:20211223:7 20220112:20220106:10 20220125:20220120:7 20220127:20220120:7 "
    "20220209:20220202:10 20220223:20220217:5 20220224:20220217:7 20220309:20220303:10 20220328:20220324:5 "
    "20220329:20220324:7 20220412:20220407:10 20220427:20220421:5 20220428:20220421:7 20220511:20220504:10 "
    "20220525:20220519:5 20220526:20220519:7 20220608:20220602:10 20220627:20220623:5 20220628:20220623:7 "
    "20220712:20220707:10 20220726:20220721:5 20220728:20220721:7 20220810:20220803:10 20220824:20220818:5 "
    "20220825:20220818:7 20220912:20220908:10 20220927:20220922:5 20220928:20220922:7 20221012:20221006:10 "
    "20221026:20221020:5 20221027:20221020:7 20221109:20221102:10 20221121:20221117:5 20221122:20221117:7 "
    "20221212:20221208:10 20221228:20221222:5 20221229:20221222:7 20230111:20230105:10 20230125:20230119:5 "
    "20230126:20230119:7 20230208:20230201:10 20230222:20230216:5 20230223:20230216:7 20230308:20230302:10 "
    "20230328:20230323:5 20230329:20230323:7 20230412:20230406:10 20230426:20230420:5 20230427:20230420:7 "
    "20230510:20230503:10 20230524:20230518:5 20230525:20230518:7 20230612:20230608:10 20230627:20230622:5 "
    "20230628:20230622:7 20230712:20230706:10 20230725:20230720:5 20230727:20230720:7 20230809:20230802:10 "
    "20230828:20230824:5 20230829:20230824:7 20230912:20230907:10 20230927:20230921:5 20230928:20230921:7 "
    "20231011:20231005:10 20231025:20231019:5 20231026:20231019:7 20231108:20231101:10 20231127:20231122:5 "
    "20231128:20231122:7 20231211:20231207:10 20231227:20231221:5 20231228:20231221:7 20240110:20240104:10 "
    "20240124:20240118:5 20240125:20240118:7 20240207:20240131:10 20240226:20240222:5 20240227:20240222:7 "
    "20240312:20240307:10 20240326:20240321:5 20240327:20240321:7 20240410:20240404:10 20240424:20240418:5 "
    "20240425:20240418:7 20240508:20240501:10 20240528:20240523:5 20240529:20240523:7 20240611:20240606:10 "
    "20240626:20240620:5 20240627:20240620:7 20240710:20240703:10 20240724:20240718:5 20240725:20240718:7 "
    "20240807:20240731:10 20240828:20240822:5 20240829:20240822:7 20240911:20240905:10 20240925:20240919:5 "
    "20240926:20240919:7 20241009:20241003:10 20241028:20241024:5 20241029:20241024:7 20241105:20241030:10 "
    "20241126:20241121:5 20241127:20241121:7 20241211:20241205:10 20241224:20241219:5 20241226:20241219:7 "
    "20250107:20250102:10 20250127:20250123:5 20250128:20250123:7 20250212:20250205:10 20250225:20250220:7 "
    "20250226:20250220:7 20250312:20250306:10 20250326:20250320:5 20250327:20250320:7 20250409:20250403:10 "
    "20250423:20250417:5 20250424:20250417:7 20250506:20250430:10 20250528:20250522:5 20250529:20250522:7 "
    "20250611:20250605:10 20250625:20250618:5 20250626:20250618:7 20250709:20250703:10 20250728:20250724:5 "
    "20250729:20250724:7 20250806:20250730:10 20250827:20250821:5 20250828:20250821:7 20250910:20250904:10 "
    "20250924:20250918:5 20250925:20250918:7 20251008:20251002:10 20251027:20251023:5 20251028:20251023:7 "
    "20251112:20251105:10 20251125:20251120:5 20251126:20251120:7 20251209:20251204:10 20251223:20251218:5 "
    "20251224:20251218:7 20260112:20260108:10 20260126:20260122:5 20260127:20260122:5 20260129:20260122:7 "
    "20260211:20260204:10 20260225:20260219:5 20260226:20260219:7 20260311:20260305:10 20260325:20260319:5 "
    "20260326:20260319:7 20260408:20260402:10 20260427:20260423:5 20260428:20260423:7 20260512:20260506:10 "
    "20260527:20260521:5 20260528:20260521:7 20260610:20260604:10 20260624:20260618:5 20260625:20260618:7 "
    "20260708:20260702:10 20260727:20260723:5 20260728:20260723:7 20260812:20260805:10 20260826:20260820:5 "
    "20260827:20260820:7 20260909:20260903:10 20260923:20260917:5 20260924:20260917:7 20261007:20261001:10 "
)


def _rows(txt, fund):
    out = []
    for tok in txt.split():
        a, n, t = tok.split(":")
        out.append((int(a), int(n), fund, int(t)))
    return tuple(sorted(out))


AUCTIONS = {"IEF": _rows(_IEF_AUCTIONS, "IEF"), "TLT": _rows(_TLT_AUCTIONS, "TLT")}
FUND_SETS = {"both": ("IEF", "TLT"), "IEF_only": ("IEF",), "TLT_only": ("TLT",)}

DEFAULT_PARAMS = {
    "notional": {"default": 300000, "min": 300000, "max": 300000, "hard_min": 300000, "hard_max": 300000, "step": 1,
                 "type": "int", "label": "Dollars a trade",
                 "tooltip": "Fixed: shares = floor($300,000 / the prior raw close) - the book seat, 3 of the hunt's "
                            "$100,000 units."},
    "cents_share": {"default": 0.5, "min": 0.5, "max": 0.5, "hard_min": 0.5, "hard_max": 0.5, "step": 0.5,
                    "type": "float", "label": "Cost (cents a share a side)",
                    "tooltip": "Fixed: half a cent a share on the entry and again on the exit (the hunt's $0.005)."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "hard_min": 0.3, "hard_max": 0.3, "step": 0.1,
                "type": "float", "label": "Fees (bp a side)",
                "tooltip": "Fixed: 0.3 bp of the prior-raw-close notional on the entry and again on the exit."},
    "funds": {"default": "both", "type": "str", "options": list(FUND_SETS),
              "label": "Funds traded",
              "tooltip": "both = IEF on 5/7/10-Year auction days and TLT on 20/30-Year days (cell 135a). IEF_only / "
                         "TLT_only = one side (TLT_only = the hunt's thin side cell 135b)."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 135a)": {"funds": ["both"]},
    "Medium (135a and each fund alone)": {"funds": ["both", "IEF_only", "TLT_only"]},
}

PNL_UNITS = "usd"

_OPEN_MIN = 570          # 09:30 ET, minute of day: the first RTH 5m bar
_ENTRY_MIN = 575         # the bar stamped 09:35 ET
_EXIT_MIN = 775          # the bar stamped 12:55 ET
_LAST_SLOT = 955         # 15:55 ET: the last RTH 5m bar of a full session
_CACHE = {}              # per-process: the panel and the bar clock


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_AUCSHORT_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        p = _derive({k: z[k] for k in PANEL_KEYS})
    _CACHE["panel"] = p
    return p


def _derive(p):
    """Typed copies of the panel arrays plus an empty memo (a panel cut at an earlier date derives the same rows)."""
    out = {"dates": np.asarray(p["dates"], np.int64), "calskip": np.asarray(p["calskip"], np.int64), "memo": {}}
    for f in ("TLT", "IEF"):
        for k in ("o935", "o1255", "prevraw"):
            out["%s_%s" % (f, k)] = np.asarray(p["%s_%s" % (f, k)], np.float64)
        out["%s_full" % f] = np.asarray(p["%s_full" % f], np.int64)
    return out


def _clock(index):
    """ET calendar date (yyyymmdd) and minute of day of every bar. The engine hands slices of one master, so the
    largest index seen is converted once and later slices of it are cut from that copy."""
    idx = pd.DatetimeIndex(index)
    ns = idx.asi8
    tz = str(idx.tz)
    c = _CACHE.get("clock")
    n = len(ns)
    if c is not None and c[0] == tz and n:
        a = int(np.searchsorted(c[1], ns[0]))
        if a + n <= len(c[1]) and np.array_equal(c[1][a:a + n], ns):
            return c[2][a:a + n], c[3][a:a + n]
    loc = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    date = (loc.year * 10000 + loc.month * 100 + loc.day).to_numpy().astype(np.int64)
    minute = (loc.hour * 60 + loc.minute).to_numpy().astype(np.int64)
    if (c is None or n > len(c[1])) and n and bool(np.all(ns[1:] > ns[:-1])):
        _CACHE["clock"] = (tz, ns.copy(), date, minute)
    return date, minute


def _sessions(date, minute):
    """Sessions of the bars: (first bar, end bar (exclusive), yyyymmdd, last minute, RTH flag). A session is RTH when
    every bar starts inside 09:30 .. 15:55 ET; anything else (the contract test's 24-hour tape, an ETH feed) is never
    traded."""
    n = len(date)
    cut = np.flatnonzero(date[1:] != date[:-1]) + 1
    starts = np.concatenate([[0], cut]).astype(np.int64)
    ends = np.concatenate([cut, [n]]).astype(np.int64)
    lo = np.minimum.reduceat(minute, starts)
    hi = np.maximum.reduceat(minute, starts)
    return starts, ends, date[starts], minute[ends - 1], (lo >= _OPEN_MIN) & (hi <= _LAST_SLOT)


def _knowable(p, i, announced):
    """True when an auction on panel row i was announced on or before the session before it (row i - 1): knowable by
    the prior close. Row 0 has no prior session."""
    return i >= 1 and int(announced) <= int(p["dates"][i - 1])


def _auction_rows(p, fund):
    """[(panel row, announcement yyyymmdd, term years)] of the fund's auction days that are panel sessions, one entry
    a day (the first auction of a fund-day gives the labels). An auction on a day that is not a session has no row,
    so it gets no trade (never rolled). Calendar facts only."""
    key = ("rows", fund)
    if key not in p["memo"]:
        dates = p["dates"]
        out, seen = [], set()
        for a, n, _, t in AUCTIONS[fund]:
            i = int(np.searchsorted(dates, a))
            if i >= len(dates) or int(dates[i]) != a or a in seen:
                continue
            seen.add(a)
            out.append((i, int(n), int(t)))
        p["memo"][key] = out
    return p["memo"][key]


def _sizing_px(p, fund, i):
    """The share-count and cost price of a trade on panel row i: the fund's PRIOR session's raw close."""
    return float(p["%s_prevraw" % fund][i])


def _entry_px(opens, e):
    """A TLT trade's entry price: the open of the job's 09:35 bar (the entry print itself)."""
    return float(opens[e])


def _cfg_ok(funds):
    return isinstance(funds, str) and funds in FUND_SETS


def _trades(p, index, opens, notional=300000, cents_share=0.5, fee_bps=0.3, funds="both", fractional=False):
    """Every trade of one config on these bars: a list of dicts (bars, date, fund, prices, shares, gross, cost, net),
    in (day, fund) order. fractional=True is the harness's sizing (N / the entry print, not a whole share count): used
    by the parity tool and the tests only, never by run_backtest."""
    if not _cfg_ok(funds):
        return []
    date, minute = _clock(index)
    if len(date) < 2:
        return []
    starts, ends, sdate, lmin, rth = _sessions(date, minute)
    if len(sdate) > 1 and not bool(np.all(sdate[1:] > sdate[:-1])):
        return []                                       # bars out of time order: never guess at sessions
    N = float(notional)
    cps = round(float(cents_share) / 100.0, 12)          # dollars a share a side
    fee = round(float(fee_bps) * 1e-4, 12)               # fraction of the prior-raw-close notional a side
    dates = p["dates"]
    out = []
    for fund in FUND_SETS[funds]:
        for i, announced, term in _auction_rows(p, fund):
            if int(p["calskip"][i]) != 0:
                continue                                # rule i / ii: early close, or the session before a closure
            if not _knowable(p, i, announced):
                continue                                # not announced by the prior session's close
            dD = int(dates[i])
            j = int(np.searchsorted(sdate, dD))
            if j >= len(sdate) or int(sdate[j]) != dD or not rth[j]:
                continue                                # not an RTH session of these bars
            if int(lmin[j]) != _LAST_SLOT:
                continue                                # the bars stop inside the session: never read as whole
            s, n1 = int(starts[j]), int(ends[j])
            m = minute[s:n1]
            e = s + int(np.searchsorted(m, _ENTRY_MIN))
            x = s + int(np.searchsorted(m, _EXIT_MIN))
            if e >= n1 or x >= n1 or int(minute[e]) != _ENTRY_MIN or int(minute[x]) != _EXIT_MIN:
                continue                                # no 09:35 or no 12:55 bar on the clock
            px = _sizing_px(p, fund, i)
            if fund == "TLT":
                p_in = _entry_px(opens, e)              # the job's own bars
                p_out = float(opens[x])                 # the 12:55 print: the P&L only
            else:
                if int(p["IEF_full"][i]) != 1:
                    continue                            # rule iii on IEF's own session
                p_in = float(p["IEF_o935"][i])
                p_out = float(p["IEF_o1255"][i])        # the 12:55 print: the P&L only
            if not (np.isfinite(px) and np.isfinite(p_in) and np.isfinite(p_out) and px > 0 and p_in > 0
                    and p_out > 0):
                continue
            if fractional:
                sh = N / p_in
                gross = -N * (p_out / p_in - 1.0)
                cost = 2.0 * (cps / px + fee) * N
            else:
                sh = float(np.floor(N / px))
                if sh < 1:
                    continue
                gross = sh * (p_in - p_out)
                cost = 2.0 * (cps * sh + fee * px * sh)
            out.append({"e": e, "x": x, "D": dD, "fund": fund, "row": i, "announced": announced, "term": term,
                        "px": px, "shares": sh, "p_in": p_in, "p_out": p_out, "gross": gross, "cost": cost,
                        "net": gross - cost})
    out.sort(key=lambda r: (r["D"], r["fund"]))
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 300000, cents_share: float = 0.5, fee_bps: float = 0.3, funds: str = "both",
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None or len(index) != n:
        return None
    if not _cfg_ok(funds):
        return None
    date, minute = _clock(index)
    if not bool(_sessions(date, minute)[4].any()):
        return None                                     # no RTH session in these bars: the panel is never opened
    p = _panel()
    if p is None:
        return None
    if _stop_event is not None and _stop_event.is_set():
        return None
    rows = _trades(p, index, opens, notional=notional, cents_share=cents_share, fee_bps=fee_bps, funds=funds)
    trades = [(r["e"], r["x"], float(r["net"]), -1, float(r["p_in"]), float(r["p_out"])) for r in rows]
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    trades.sort(key=lambda t: (t[1], t[0]))
    pnl = np.array([t[2] for t in trades], float)
    w = pnl[pnl > 0]
    ls = pnl[pnl < 0]
    gw = float(w.sum())
    gl = float(-ls.sum())
    cum = np.cumsum(pnl)
    out = {"total_pnl": float(pnl.sum()), "num_trades": int(len(pnl)),
           "win_rate": float(100.0 * len(w) / len(pnl)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
           "avg_pnl": float(pnl.mean()), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None, **params):
    """Every trade opens at 09:35 and is covered at 12:55 of the SAME session: nothing is ever held through a session
    close, so there is no mark. One empty list per trade, in trade order."""
    return [[] for _ in (trades or [])]
