# AUGUR-SOURCE: claude-review
"""MISC GLDMACRO 1.0 - long GLD ($250,000) from the close before a scheduled CPI / payroll / FOMC day to that day's close.

Provenance: OPUS-HUNT futures, strategy 97 (GLD-MACRODAY, lens div-literature), verdict cell 97a
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S97: PREREG.md, RESULTS.md, s97_lib.py, s97_eval.py, trades_97a.csv,
series.pkl '97a'). Defaults = cell 97a exactly; `entry` release_open with `events` CPI+EMP = the prereg's report-only
cell 97b. Mechanism (prereg): the announcement premium (Savor-Wilson 2013, Ai-Bansal 2018) - risk premia for scheduled
macro news are earned on release days, and gold, priced off real rates and inflation news, carries that release risk
with no designed index exposure. Same release calendar as strategy 94 (MISC_EVENTCRUSH_1_0.py, short VIXY into the
same days).
NOT A BLIND READ: the asset was chosen on the proposer's TUNE scan (2010-06 .. 2016-06: GLD on these days n 188,
+8.4 bp a day, t 0.95, picked after TLT, the papers' asset, came out wrong-signed); the hunt read TUNE (look only) and
then EVAL 2016-07-01 .. 2025-06-30 once: 277 trades (30.8 a year), +12.1 bp net a trade, +$84,083 at $250k a trade,
net t 1.26 / 1.65 in the two halves (2016H2-2020 / 2021-2025H1), 9 of 10 calendar years positive, control gate passed
narrowly (the 97.5th percentile of 200 random non-release draws). Verdict under the old strict bars: FAIL (Route A: t
under 2 in both halves, THIN at 30.8 trades a year; Route B book add: P(lift) 0.716 < 0.95, 4 of 8 folds < 6). It
passes the owner's loose screen (owner_screen_1114_fixed: 31 trades a year, $9.3k a year, leg max DD $18.8k) with
warnings t 1.3/1.7 and one episode (its ten best days out-earn its whole net). Cell 97b (09:30 -> close on CPI and
payroll days) was DEAD (-$3.2k): whatever premium there is sits in the overnight hold into the 08:30 print. The
2025-07 .. 2026-06 lockbox was never read by the hunt. This file exists so the engine's Auto-Validate can judge it.

-- The rule (defaults = cell 97a) --------------------------------------------------------------------------------
1. Release days D = the dates of the selected release types (`events`, default FOMC + CPI + EMP) that are GLD
   sessions. A release on a market holiday (CPI 2017-04-14, 2020-04-10; payrolls 2021-04-02, 2023-04-07, 2026-04-03:
   Good Fridays) gets no trade - never rolled to another day. Two release types on one date = one trade.
2. `entry` prior_close (97a): BUY at the official close of D-1 = the GLD session immediately before D (13:00 on a half
   day), SELL at D's official close (the half-day close when D is a half day: 2025-07-03, in the lockbox).
   `entry` release_open (97b): BUY the open of D's 09:30 bar, SELL the close of D's last RTH 5m bar (15:55; 12:55).
3. Back-to-back release sessions (D and D+1) are SEPARATE trades, each charged a full round trip; the exit and
   re-entry at D's close are not netted (the hunt's rule; 17 such pairs in 2010-25).
TRADE <-> SESSIONS (a prior-close trade holds across ONE night). Its entry bar is D-1's last 5m bar in the job's bars
(the bar whose close is the closing print) and its exit bar is D's last 5m bar; its P&L lands on D (the exit bar).
The engine files a trade under the stretch its ENTRY bar is in (warm starts keep the trades that enter inside a
stretch, the lockbox included), so this one belongs to D-1's stretch; mark_open_trades values it at 0 at that entry
bar (bought at that close; costs land on the exit day). A trade needs D-1's last bar and the whole of D inside the
bars: a walk-forward slice that ends at D-1 or inside D, or starts after D-1's close, takes no trade for that D - a
slice edge never closes a trade early or opens it late (at most one trade lost per slice edge). A release-open trade
lives inside session D.
THE EXIT PRINT NEVER SELECTS THE ENTRY: which days trade comes from the frozen calendar and the session calendar only;
the entry bar is found from D-1's own bars; shares from D-1's raw close (or from D's opening print). D's official
close, D's bars after the entry print and D's raw close are read for the P&L only. The one fact about D used before
that is whether D's session is whole inside the job's bars - a clock fact (bar times), never a price.
tests/test_misc_gldmacro.py scrambles everything known only after the entry print and checks that no trade moves, and
that three broken variants (shares from D's raw close; a day skipped when D closes down; a release-open trade bought
at the 09:35 bar's open) are caught.

INFORMATION TIMES (every input known at or before its print):
  * the release calendar is scheduled in advance (the Fed's meeting calendar a year or more ahead; BLS release
    schedules a year ahead). The exceptions are the re-scheduled BLS dates inside the lockbox (the autumn-2025
    shutdown: CPI 2025-10-24 and 2025-12-18, payrolls 2025-11-20 and 2025-12-16; payrolls 2026-02-11, the file's
    catch-up date): BLS announced each before the new date, but those announcement dates are not on disk and were
    not checked against D-1's close;
  * the session calendar (holidays, half days) is the exchange's, known in advance; it fixes D-1 and D's closing time;
  * entry: D-1's official close (an MOC fill) / D's 09:30 opening print. Shares = floor(N / D-1's raw close) - the
    closing print itself, the hunt's sizing (live sizing would read a pre-close price; ~0 effect) - or
    floor(N / the 09:30 open) for release_open;
  * exit: D's official close / the close of D's last RTH 5m bar.

-- Data ---------------------------------------------------------------------------------------------------------
THE JOB'S MASTER = GLD 5m RTH, source alpaca_split_rth (engine master id 79, master_90ca117d.csv, 2016-01-04 ..
2026-06-30, 2,637 sessions; GLD never split, so split-adjusted = traded prices): the bar clock of every trade and the
prices of release_open (the bars cell 97b read). prior_close prices come from the pinned side panel (sha256 checked)
    C:/EdgeLog/alpaca_cache/gldmacro_panel/gldmacro_panel_v1.npz   (built by tools/misc_gldmacro_panel.py)
= the session calendar 2016-01-04 .. 2026-06-30 (the yahoo_adj 1d master, the 5m master and GLD_1Day_raw.csv agree on
every date), `close` = the yahoo_adj GLD 1d master's closes (engine master id 52: the hunt's return prices), `raw` =
C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv closes (the hunt's share-count price for every D-1 in 2016+), and
`last_min` = the minute of each session's last 5m bar in the master (15:55; 12:55 on the 21 half days; 2019-08-12
stops at 15:25 - the D-1 of CPI 2019-08-13, whose entry bar is that 15:25 bar and whose price is the official close).
No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.
Known data limits (the hunt's own): the alpaca raw close is off the official close on 2020-03-12 (+179 bp) and
2020-03-16 (-288 bp), neither the D-1 of a release day, and on 2020-05-11 (+12.5 bp), the D-1 of CPI 2020-05-12,
where it moves that trade's share count by under 0.2 pct. Raw sets shares and cost only, never the return.

EVENT CALENDAR (frozen below, 2016-01 .. 2026-06-30; identical, list for list, to MISC_EVENTCRUSH_1_0.py's; the hunt
read the same two files):
  * FOMC: tools/data/fomc_dates.txt - scheduled decision (statement) days only, collected 2026-07-17 from
    federalreserve.gov (fomchistorical<year>.htm for 2010-2020, fomccalendars.htm for 2021-2026); unscheduled
    meetings and notation votes excluded; 2020 has 7 (the March 2020 scheduled meeting was cancelled). 83 days.
  * CPI and EMP (Employment Situation, payrolls): tools/data/bls_dates.txt in the shared checkout (untracked there),
    collected 2026-09-09 from bls.gov/schedule/<year>/home.htm one year at a time, all at 08:30 ET; includes the
    autumn-2025 shutdown moves and the early-July payrolls. 125 CPI days, 125 EMP days.
  Seven days carry both CPI and FOMC (2016-03-16, 2017-03-15, 2017-06-14, 2017-12-13, 2019-12-11, 2020-06-10,
  2024-06-12): one trade each.

-- Sizing and costs (INSIDE the plugin: job cost_pts 0, mult 1) --------------------------------------------------
N = `notional` ($250,000) a trade. prior_close: px = D-1's raw close, shares = floor(N / px), gross = shares x px x
(close(D) / close(D-1) - 1) on the official closes. release_open: px = the 09:30 open, shares = floor(N / px), gross
= shares x (exit - px). Cost = 2 x (`cents_share` cents x shares + `fee_bps` bp x px x shares) = 2 x (0.5 c a share +
0.3 bp), both sides charged on the entry notional (the hunt's formula; about 1.25 bp a trade). Net = gross - cost,
DOLLARS in the trade tuple's field 2; side +1; entry / exit prices = the two official closes (or the open and the
exit bar's close). The hunt's 97c (double cost, +$75,449 on EVAL) is a stress read outside the pinned range:
cents_share 1.0 with fee_bps 0.6 reproduce it (tools/misc_gldmacro_parity.py checks it).

-- Auto-Validate ranges ------------------------------------------------------------------------------------------
OPEN: events (7: FOMC+CPI+EMP, FOMC+EMP, FOMC+CPI, CPI+EMP, FOMC, CPI, EMP - the prereg's "sub-calendar") x entry
(prior_close, release_open - its "intraday clock", cell 97b) = 14 grid points; 97a and 97b both on the grid. The rule
is small and the grid stays small on purpose: the prereg names one exit clock (D's close) and no hedge, so neither is
a knob, and no knob was added to pad the grid. PINNED (min = max = hard bounds): notional, cents_share, fee_bps. No
numeric knob is open, so nothing can auto-expand.
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC GLDMACRO 1.0 · long GLD into scheduled CPI / payroll / FOMC days (opus hunt 97a)'
DESCRIPTION = ("Buy $250,000 of GLD at the official close of the session before a scheduled CPI, payrolls or FOMC "
               "decision day and sell it at that day's official close (back-to-back release days = separate trades, "
               "each charged a round trip): the announcement premium. Runs on the GLD 5m master (the clock, and the "
               "prices of the release-day-open variant); the official and raw daily closes come from a pinned side "
               "panel. Costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "GLD", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/gldmacro_panel/gldmacro_panel_v1.npz"
PANEL_SHA256 = "PIN-AFTER-BUILD"            # set to the sha256 tools/misc_gldmacro_panel.py prints

# ---- the frozen release calendar, 2016-01 .. 2026-06-30 (sources in the docstring) ---------------------------------
_FOMC_DAYS = (
    "20160127 20160316 20160427 20160615 20160727 20160921 20161102 20161214 "
    "20170201 20170315 20170503 20170614 20170726 20170920 20171101 20171213 "
    "20180131 20180321 20180502 20180613 20180801 20180926 20181108 20181219 "
    "20190130 20190320 20190501 20190619 20190731 20190918 20191030 20191211 "
    "20200129 20200429 20200610 20200729 20200916 20201105 20201216 "
    "20210127 20210317 20210428 20210616 20210728 20210922 20211103 20211215 "
    "20220126 20220316 20220504 20220615 20220727 20220921 20221102 20221214 "
    "20230201 20230322 20230503 20230614 20230726 20230920 20231101 20231213 "
    "20240131 20240320 20240501 20240612 20240731 20240918 20241107 20241218 "
    "20250129 20250319 20250507 20250618 20250730 20250917 20251029 20251210 "
    "20260128 20260318 20260429 20260617 ")
_CPI_DAYS = (
    "20160120 20160219 20160316 20160414 20160517 20160616 20160715 20160816 20160916 20161018 20161117 20161215 "
    "20170118 20170215 20170315 20170414 20170512 20170614 20170714 20170811 20170914 20171013 20171115 20171213 "
    "20180112 20180214 20180313 20180411 20180510 20180612 20180712 20180810 20180913 20181011 20181114 20181212 "
    "20190111 20190213 20190312 20190410 20190510 20190612 20190711 20190813 20190912 20191010 20191113 20191211 "
    "20200114 20200213 20200311 20200410 20200512 20200610 20200714 20200812 20200911 20201013 20201112 20201210 "
    "20210113 20210210 20210310 20210413 20210512 20210610 20210713 20210811 20210914 20211013 20211110 20211210 "
    "20220112 20220210 20220310 20220412 20220511 20220610 20220713 20220810 20220913 20221013 20221110 20221213 "
    "20230112 20230214 20230314 20230412 20230510 20230613 20230712 20230810 20230913 20231012 20231114 20231212 "
    "20240111 20240213 20240312 20240410 20240515 20240612 20240711 20240814 20240911 20241010 20241113 20241211 "
    "20250115 20250212 20250312 20250410 20250513 20250611 20250715 20250812 20250911 20251024 20251218 "
    "20260113 20260213 20260311 20260410 20260512 20260610 ")
_EMP_DAYS = (
    "20160108 20160205 20160304 20160401 20160506 20160603 20160708 20160805 20160902 20161007 20161104 20161202 "
    "20170106 20170203 20170310 20170407 20170505 20170602 20170707 20170804 20170901 20171006 20171103 20171208 "
    "20180105 20180202 20180309 20180406 20180504 20180601 20180706 20180803 20180907 20181005 20181102 20181207 "
    "20190104 20190201 20190308 20190405 20190503 20190607 20190705 20190802 20190906 20191004 20191101 20191206 "
    "20200110 20200207 20200306 20200403 20200508 20200605 20200702 20200807 20200904 20201002 20201106 20201204 "
    "20210108 20210205 20210305 20210402 20210507 20210604 20210702 20210806 20210903 20211008 20211105 20211203 "
    "20220107 20220204 20220304 20220401 20220506 20220603 20220708 20220805 20220902 20221007 20221104 20221202 "
    "20230106 20230203 20230310 20230407 20230505 20230602 20230707 20230804 20230901 20231006 20231103 20231208 "
    "20240105 20240202 20240308 20240405 20240503 20240607 20240705 20240802 20240906 20241004 20241101 20241206 "
    "20250110 20250207 20250307 20250404 20250502 20250606 20250703 20250801 20250905 20251120 20251216 "
    "20260109 20260211 20260306 20260403 20260508 20260605 ")


def _days(txt):
    return np.array(sorted({int(x) for x in txt.split()}), dtype=np.int64)


EVENT_DAYS = {"FOMC": _days(_FOMC_DAYS), "CPI": _days(_CPI_DAYS), "EMP": _days(_EMP_DAYS)}
EVENT_SETS = {"FOMC+CPI+EMP": ("FOMC", "CPI", "EMP"), "FOMC+EMP": ("FOMC", "EMP"), "FOMC+CPI": ("FOMC", "CPI"),
              "CPI+EMP": ("CPI", "EMP"), "FOMC": ("FOMC",), "CPI": ("CPI",), "EMP": ("EMP",)}
ENTRY_MODES = ("prior_close", "release_open")

DEFAULT_PARAMS = {
    "notional": {"default": 250000, "min": 250000, "max": 250000, "hard_min": 250000, "hard_max": 250000, "step": 1,
                 "type": "int", "label": "Dollars a trade",
                 "tooltip": "Fixed: shares = floor($250,000 / the entry-side price), the hunt's size."},
    "cents_share": {"default": 0.5, "min": 0.5, "max": 0.5, "hard_min": 0.5, "hard_max": 0.5, "step": 0.5,
                    "type": "float", "label": "Cost (cents a share a side)",
                    "tooltip": "Fixed: half a cent a share on the entry and again on the exit (the hunt's $0.005)."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "hard_min": 0.3, "hard_max": 0.3, "step": 0.1,
                "type": "float", "label": "Fees (bp a side)",
                "tooltip": "Fixed: 0.3 bp of the entry notional on the entry and again on the exit (the hunt's)."},
    "events": {"default": "FOMC+CPI+EMP", "type": "str", "options": list(EVENT_SETS),
               "label": "Release days (EMP = payrolls)",
               "tooltip": "Which scheduled releases make a trade day. FOMC+CPI+EMP = cell 97a; CPI+EMP = the days of "
                          "cell 97b."},
    "entry": {"default": "prior_close", "type": "str", "options": list(ENTRY_MODES),
              "label": "Entry clock",
              "tooltip": "prior_close = buy the official close of the session before the release day, sell the "
                         "release day's official close (cell 97a). release_open = buy the release day's 09:30 open, "
                         "sell the close of its last 5m bar (cell 97b)."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 97a)": {"events": ["FOMC+CPI+EMP"], "entry": ["prior_close"]},
    "Medium (cells 97a / 97b and the one-release calendars)": {
        "events": ["FOMC+CPI+EMP", "CPI+EMP", "FOMC", "CPI", "EMP"], "entry": ["prior_close", "release_open"]},
}

PNL_UNITS = "usd"

_OPEN_MIN = 570          # 09:30 ET, minute of day: the first RTH 5m bar
_LAST_SLOT = 955         # 15:55 ET: the last RTH 5m bar of a full session
_CACHE = {}              # per-process: the panel and the bar clock (release rows live in the panel's memo)


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_GLDMACRO_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        p = _derive({k: z[k] for k in ("dates", "close", "raw", "last_min")})
    _CACHE["panel"] = p
    return p


def _derive(p):
    """Typed copies of the panel arrays plus an empty memo (a panel cut at an earlier date derives the same rows)."""
    return {"dates": np.asarray(p["dates"], np.int64), "close": np.asarray(p["close"], np.float64),
            "raw": np.asarray(p["raw"], np.float64), "last_min": np.asarray(p["last_min"], np.int64), "memo": {}}


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
    """Sessions of the bars: (first bar, end bar (exclusive), yyyymmdd, first minute, last minute, RTH flag). A session
    is RTH when every bar starts inside 09:30 .. 15:55 ET; anything else (the contract test's 24-hour tape, an ETH
    feed) is never traded."""
    n = len(date)
    cut = np.flatnonzero(date[1:] != date[:-1]) + 1
    starts = np.concatenate([[0], cut]).astype(np.int64)
    ends = np.concatenate([cut, [n]]).astype(np.int64)
    lo = np.minimum.reduceat(minute, starts)
    hi = np.maximum.reduceat(minute, starts)
    return starts, ends, date[starts], minute[starts], minute[ends - 1], (lo >= _OPEN_MIN) & (hi <= _LAST_SLOT)


def _event_rows(p, events):
    """Panel rows of the release days D of the selected types. A release on a day that is not a GLD session has no
    row, so it gets no trade (never rolled)."""
    key = ("rows", events)
    if key not in p["memo"]:
        ev = np.zeros(len(p["dates"]), bool)
        for t in EVENT_SETS[events]:
            ev |= np.isin(p["dates"], EVENT_DAYS[t])
        p["memo"][key] = np.flatnonzero(ev)
    return p["memo"][key]


def _prior_close_terms(p, i):
    """(return base, sizing price) of the prior-close trade on release row i: D-1's official close and D-1's raw
    close, both known at D-1's closing print (the entry)."""
    return float(p["close"][i - 1]), float(p["raw"][i - 1])


def _open_terms(opens, e):
    """Entry and sizing price of the release-open trade: the open of D's 09:30 bar (the opening print itself)."""
    return float(opens[e])


def _cfg_ok(events, entry):
    return isinstance(events, str) and events in EVENT_SETS and isinstance(entry, str) and entry in ENTRY_MODES


def _trades(p, index, opens, closes, notional=250000, cents_share=0.5, fee_bps=0.3, events="FOMC+CPI+EMP",
            entry="prior_close"):
    """Every trade of one config on these bars: a list of dicts (bars, dates, prices, shares, gross, cost, net)."""
    if not _cfg_ok(events, entry):
        return []
    date, minute = _clock(index)
    if len(date) < 2:
        return []
    starts, ends, sdate, fmin, lmin, rth = _sessions(date, minute)
    if len(sdate) > 1 and not bool(np.all(sdate[1:] > sdate[:-1])):
        return []                                       # bars out of time order: never guess at sessions
    N = float(notional)
    cps = round(float(cents_share) / 100.0, 12)          # dollars a share a side
    fee = round(float(fee_bps) * 1e-4, 12)               # fraction of the entry notional a side
    dates = p["dates"]
    out = []
    for i in _event_rows(p, events):
        i = int(i)
        dD = int(dates[i])
        jD = int(np.searchsorted(sdate, dD))
        if jD >= len(sdate) or int(sdate[jD]) != dD or not rth[jD]:
            continue                                    # D is not an RTH session of these bars
        if int(lmin[jD]) < int(p["last_min"][i]):
            continue                                    # the bars stop inside D: a cut session is never read as whole
        x = int(ends[jD] - 1)                           # D's last bar: its close is D's closing print
        if entry == "prior_close":
            jP = jD - 1
            if i < 1 or jP < 0 or int(sdate[jP]) != int(dates[i - 1]) or not rth[jP]:
                continue                                # D-1 = the panel's previous session, and it must be in the bars
            e = int(ends[jP] - 1)                       # D-1's last bar: the entry is its closing print
            c0, px = _prior_close_terms(p, i)
            c1 = float(p["close"][i])                   # D's official close: the P&L only
            if not (np.isfinite(c0) and np.isfinite(c1) and np.isfinite(px) and c0 > 0 and c1 > 0 and px > 0):
                continue
            sh = float(np.floor(N / px))
            gross = sh * px * (c1 / c0 - 1.0)
            p_in, p_out, d_in = c0, c1, int(dates[i - 1])
        else:
            if int(fmin[jD]) != _OPEN_MIN:
                continue                                # no 09:30 bar in these bars: no opening print to buy
            e = int(starts[jD])
            px = _open_terms(opens, e)
            p_out = float(closes[x])                    # D's last bar close: the P&L only
            if not (np.isfinite(px) and np.isfinite(p_out) and px > 0 and p_out > 0):
                continue
            sh = float(np.floor(N / px))
            gross = sh * (p_out - px)
            p_in, d_in = px, dD
        if sh < 1:
            continue
        cost = 2.0 * (cps * sh + fee * px * sh)
        out.append({"e": e, "x": x, "D": dD, "entry_day": d_in, "row": i, "px": px, "shares": sh, "p_in": p_in,
                    "p_out": p_out, "gross": gross, "cost": cost, "net": gross - cost})
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 250000, cents_share: float = 0.5, fee_bps: float = 0.3,
                 events: str = "FOMC+CPI+EMP", entry: str = "prior_close",
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None or len(index) != n:
        return None
    if not _cfg_ok(events, entry):
        return None
    date, minute = _clock(index)
    if not bool(_sessions(date, minute)[5].any()):
        return None                                     # no RTH session in these bars: the panel is never opened
    p = _panel()
    if p is None:
        return None
    if _stop_event is not None and _stop_event.is_set():
        return None
    rows = _trades(p, index, opens, closes, notional=notional, cents_share=cents_share, fee_bps=fee_bps,
                   events=events, entry=entry)
    trades = [(r["e"], r["x"], float(r["net"]), 1, float(r["p_in"]), float(r["p_out"])) for r in rows]
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
    """A prior-close trade is held through ONE session close - its entry bar, D-1's last bar - where it is worth
    exactly 0 (bought at that very close; costs land on the exit day with the rest of its P&L). A release-open trade
    opens and closes inside session D: no mark. One [(bar, usd), ...] list per trade, in trade order. Without an
    index every trade whose exit bar is later than its entry bar gets the 0 mark (the book ignores marks of a trade
    that enters and exits on one day)."""
    date = None
    if index is not None and len(index) == len(closes):
        date, _ = _clock(index)
    out = []
    for t in trades or []:
        e, x = int(t[0]), int(t[1])
        if x <= e:
            out.append([])
        elif date is not None and 0 <= e < len(date) and 0 <= x < len(date) and date[e] == date[x]:
            out.append([])
        else:
            out.append([(e, 0.0)])
    return out
