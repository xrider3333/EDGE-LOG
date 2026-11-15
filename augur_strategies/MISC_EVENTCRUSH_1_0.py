# AUGUR-SOURCE: claude-review
"""MISC EVENTCRUSH 1.0 - short VIXY ($50,000) from the close before a scheduled FOMC / CPI / payroll day to the event close.

Provenance: OPUS-HUNT futures, strategy 94 (EVENTCRUSH, lens div-calendar), verdict cell 94a
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S94: PREREG.md, RESULTS.md, s94_lib.py, s94_run.py, trades_94a.csv,
series.pkl '94a'). Defaults = cell 94a exactly; `hedge` ON = the prereg's cell 94b, events "FOMC+EMP" = its cell 94c.
Mechanism (prereg): implied vol is bid into scheduled macro announcements and released once the number is out
(Ederington-Lee), so a short VIXY position held only across the announcement earns that release.
NOT A BLIND READ: the hunt read 2016-07-01..2025-06-30 once (271 trades, 30.1 a year, net +$70.9k at $50k), its
5m TUNE sketch read 2016-01..06, and the proposer's TUNE read was 2011-01..2016-06 (yfinance daily). Verdict under the
hunt's old strict bars: FAIL (Route A: EVAL-B 2021-25H1 net t +0.54, needs 2; Route B book add made the book worse:
lift -11.81 ROC@30k, P(lift) 0.37, 5 of 8 folds, inside the no-edge control band). It passes the owner's loose screen
(>= 20 trades a year, profitable in both halves, WF > 0 to be judged here). The 2025-07..2026-06 lockbox was never
read by the hunt. This file exists so the engine's Auto-Validate can judge it.

-- The rule (defaults = cell 94a) ------------------------------------------------------------------------------
1. Event days E = the dates of the selected release types (`events`, default FOMC + CPI + EMP) that are sessions of
   the frozen calendar. A release on a market holiday (CPI 2017-04-14, 2020-04-10; EMP 2021-04-02, 2023-04-07,
   2026-04-03 - Good Fridays) is dropped: no trade, no hold across it.
2. Blocks = maximal runs of consecutive sessions that are all in E; P = the session before the block's first day
   (never in E by construction). `block`: "hold" = one trade P -> the block's LAST day (94a); "first" = P -> the
   block's first day only; "single" = lone event days only (multi-day blocks are skipped). The hunt's window
   (2016-07 .. 2025-06) has 6 two-day blocks in 271: five are CPI and FOMC on consecutive days (2016-12-14/15 FOMC
   then CPI; 2018-06-12/13, 2022-12-13/14, 2023-06-13/14, 2023-12-12/13 CPI then FOMC) and one is FOMC then payrolls
   (2020-11-05/06).
3. ENTRY: short VIXY at the close of the last 5m bar of P starting at or before `entry_min` - 5 (default 960 = the
   16:00 close: the session's 15:55 bar, 12:55 on an early close; the master's 2019-08-12 stops at 15:35 and that bar
   is used, as the hunt did).
4. EXIT: buy back at the close of the last 5m bar of the exit day X starting at or before T - 5, with T = 16:00 when
   X carries an FOMC decision of the selected set (statement 14:00, press conference after it) and T = `exit_min`
   otherwise (CPI and payrolls print at 08:30, before the open; default 960 = the close).
5. One trade per block; trades never overlap (P of the next block comes after the last X). PnL is DOLLARS in the
   trade tuple's field 2, booked at the exit bar; side -1; entry / exit prices = the VIXY master closes.
A trade needs P's entry bar and X's exit bar in the job's bars. When X is the LAST session in the bars (a walk-forward
slice can end inside it), the exit bar must be the clock bar itself (start = T - 5), else no trade - a cut session is
never read as a full one.

INFORMATION TIMES (every input known at or before its print):
  * the event calendar is scheduled in advance (the Fed's meeting calendar a year or more ahead; BLS release
    schedules a year ahead). The exceptions are the autumn-2025 shutdown re-schedules inside the lockbox (CPI
    2025-10-24 and 2025-12-18, EMP 2025-11-20 and 2025-12-16): BLS announced each before its release day, but those
    announcement dates are not on disk and were not checked against P;
  * the session calendar (holidays, early closes) is the exchange's, known in advance; it decides whether the next
    session is also an event day, so the block (and the exit day X) is known at the entry print;
  * entry: the close of a bar that ends at the entry clock. Shares: at the 16:00 entry (default), N / P's official raw
    close (the closing print itself - the hunt's sizing); for an earlier entry clock, N / the entry bar's close in raw
    terms (master close x P's raw / split factor, a corporate-action constant for the day). Shares only feed the
    per-share cost;
  * exit: the close of a bar that ends at the exit clock; the exit share count uses X's raw / split factor (a reverse
    split takes effect at X's open);
  * hedge beta: OLS slope of VIXY on SPY daily split close-to-close returns over the 60 sessions ending at the close
    of the session BEFORE P (strictly before the entry print; no VIX, no same-day reading); the SPY prints are the
    last SPY 5m bar at or before the same clocks;
  * borrow accrues by calendar days P -> X.

-- Data -------------------------------------------------------------------------------------------------------
VIXY prices = the job's master: VIXY 5m RTH, source alpaca_split_rth (engine master id 141, split-adjusted; the
hunt's own bars). Gross = N x (1 - C(X) / C(P)) from those closes, a ratio, so the split adjustment cancels.
Everything else comes from the pinned side panel (sha256 checked on load)
    C:/EdgeLog/alpaca_cache/eventcrush_panel/eventcrush_panel_v1.npz   (built by tools/misc_eventcrush_panel.py)
= the session calendar (2,637 sessions 2016-01-04 .. 2026-06-30; the VIXY and SPY 5m masters and the four daily
files agree on every date), VIXY and SPY daily raw and split closes (C:/EdgeLog/alpaca_cache/etf_daily/
{VIXY,SPY}_1Day_{raw,split}.csv, parsed as s94_lib.read_daily) and SPY 5m RTH closes by bar (master id 112).
No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.
VIXY reverse splits inside the window (raw / split ratio steps): 2016-07-25 1:5, 2017-07-17 1:4, 2021-05-26 1:4,
2023-06-23 1:5, 2024-11-07 1:4; none 2024-11-08 .. 2026-06-30. One 2016-25 hold spans an ex-date (P 2024-11-06 ->
2024-11-07 FOMC: 4,371 shares in, 1,093 out; the exit cost is charged on 1,093).

EVENT CALENDAR (frozen below, 2016-01 .. 2026-06-30; the hunt read the same two files):
  * FOMC: tools/data/fomc_dates.txt - scheduled decision (statement) days only, collected 2026-07-17 from
    federalreserve.gov (fomchistorical<year>.htm for 2010-2020, fomccalendars.htm for 2021-2026, forward rows
    re-checked 2026-09-09); unscheduled meetings and notation votes excluded; 2020 has 7 (March 2020's scheduled
    meeting was cancelled for the 2020-03-15 emergency meeting, which is excluded). 83 days.
  * CPI and EMP (Employment Situation, payrolls): tools/data/bls_dates.txt in the shared checkout (untracked there),
    collected 2026-09-09 from bls.gov/schedule/<year>/home.htm one year at a time, all at 08:30 ET; includes the
    2013 and autumn-2025 shutdown moves and the early-July payrolls. 125 CPI days, 125 EMP days.
  Seven days carry both CPI and FOMC (2016-03-16, 2017-03-15, 2017-06-14, 2017-12-13, 2019-12-11, 2020-06-10,
  2024-06-12); none carry EMP with either.

-- Sizing and costs (INSIDE the plugin: job cost_pts 0, mult 1) -------------------------------------------------
N = `notional` ($50,000) of VIXY short a trade. Shares S as above; exit shares S x ratio(P) / ratio(X).
Per crossing: `cents_share` cents a share ($0.005) + `fee_bps` (0.3 bp) of that print's notional (entry N, exit
N x C(X) / C(P)); two crossings. BORROW: `borrow_pct` (10 % a year) x N x calendar days(P -> X) / 365 - the hunt's
flat guess; its stress case was 2x crossings and 2x borrow (20 % a year). Hedge leg (`hedge` ON, cell 94b): an SPY
position of SIGNED notional H = beta x N (beta < 0 -> short SPY), opened and closed at the same clocks; its PnL
H x (SPY(X) / SPY(P) - 1), the same crossing costs on SPY raw shares, and SPY borrow 0.5 % a year on |H| when the
SPY leg is short (the hunt's assumption; none when long). Dividends are not modelled (VIXY pays none; SPY's
quarterly ex-dividend drop shows in its split-only prices with no dividend credited to a long hedge or charged to a
short one - only on the few hedged holds that span an SPY ex-date; the hunt did the same).

-- BORROW / LOCATE RISK -------------------------------------------------------------------------------------------
The owner would short VIXY on Webull. VIXY borrow can be unavailable (no locate) or expensive (hard-to-borrow fees
far above 10 % a year), and recalls / buy-ins come on exactly the stress days this trade needs - volatility spikes,
when shorts in VIX products crowd and lenders pull shares; a 10 % intraday drop also puts the short-sale uptick rule
(SSR) on for that day and the next. THE BACKTEST ASSUMES EVERY SHORT IS LOCATED, FILLED AT THE CLOSE AND HELD AT THE
HUNT'S FLAT FEE: no failed locates, no recalls, no fee spikes, no SSR. Read every number here as an upper bound on
what Webull would have delivered.

-- Auto-Validate ranges -------------------------------------------------------------------------------------------
events (7: FOMC+CPI+EMP, FOMC+EMP, FOMC+CPI, CPI+EMP, FOMC, CPI, EMP) x entry_min 14:00 .. 16:00 every 30 min (5) x
exit_min 10:00 .. 16:00 every 30 min (13) x block (hold, first, single) x hedge (off, on) = 2,730 grid points, 94a
on the grid. notional, cents_share, fee_bps and borrow_pct are pinned. Fences: entry_min may auto-expand down to
12:00 (hard_min 720; 9 x 7 x 13 x 3 x 2 = 4,914 points at most) and never past 16:00; exit_min is fenced at its
range (10:00 .. 16:00); events and block are categorical.
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC EVENTCRUSH 1.0 · short VIXY into scheduled FOMC / CPI / payroll days (opus hunt 94a)'
DESCRIPTION = ("Short $50,000 of VIXY at the close of the session before a scheduled FOMC decision, CPI or payrolls "
               "day and buy it back at the close of the event day (back-to-back event days = one trade): implied "
               "vol is bid into the release and let go once it is out. Runs on the VIXY 5m master; the calendar, "
               "daily closes and the optional SPY hedge come from a pinned side panel. Costs and a 10%/yr borrow "
               "inside the plugin -> job cost_pts 0, mult 1. The backtest assumes every short is located.")

_AUGUR_MARKET = {"instrument": "VIXY", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/eventcrush_panel/eventcrush_panel_v1.npz"
PANEL_SHA256 = "399144f3ed57426ba119e698f4aee203f93a60225eb18f9fdd06f240ee803297"

# ---- the frozen event calendar, 2016-01 .. 2026-06-30 (sources in the docstring) ------------------------------
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
BLOCK_MODES = ("hold", "first", "single")

DEFAULT_PARAMS = {
    "notional": {"default": 50000, "min": 50000, "max": 50000, "hard_min": 50000, "hard_max": 50000, "step": 1,
                 "type": "int", "label": "Dollars short a trade",
                 "tooltip": "Fixed: $50,000 of VIXY sold short at the entry print (the hunt's N)."},
    "cents_share": {"default": 0.5, "min": 0.5, "max": 0.5, "hard_min": 0.5, "hard_max": 0.5, "step": 0.5,
                    "type": "float", "label": "Cost (cents a share a crossing)",
                    "tooltip": "Fixed: half a cent a raw share on the entry and on the exit (the hunt's $0.005)."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "hard_min": 0.3, "hard_max": 0.3, "step": 0.1,
                "type": "float", "label": "Fees (bp a crossing)",
                "tooltip": "Fixed: 0.3 bp of the crossing notional on the entry and on the exit."},
    "borrow_pct": {"default": 10.0, "min": 10.0, "max": 10.0, "hard_min": 10.0, "hard_max": 10.0, "step": 1.0,
                   "type": "float", "label": "VIXY borrow (% a year)",
                   "tooltip": "Fixed: 10% a year on the $50,000 short, per calendar day held (the hunt's flat "
                              "guess; its stress case is 20). Every short is assumed located."},
    "events": {"default": "FOMC+CPI+EMP", "type": "str", "options": list(EVENT_SETS),
               "label": "Event days (EMP = payrolls)",
               "tooltip": "Which scheduled releases make an event day. FOMC+CPI+EMP = cell 94a; FOMC+EMP = cell 94c."},
    "entry_min": {"default": 960, "min": 840, "max": 960, "step": 30, "hard_min": 720, "hard_max": 960,
                  "type": "int", "label": "Entry time on the session before (minute of day ET)",
                  "tooltip": "960 = the 16:00 close (cell 94a). Short at the close of the last 5m bar ending at "
                             "or before this time."},
    "exit_min": {"default": 960, "min": 600, "max": 960, "step": 30, "hard_min": 600, "hard_max": 960,
                 "type": "int", "label": "Exit time on a CPI / payroll day (minute of day ET)",
                 "tooltip": "960 = the 16:00 close (cell 94a). Buy back at the close of the last 5m bar ending at or "
                            "before this time. A trade whose exit day has an FOMC decision always exits at 16:00."},
    "block": {"default": "hold", "type": "str", "options": list(BLOCK_MODES),
              "label": "Back-to-back event days",
              "tooltip": "hold = one trade through the run to its last day (cell 94a); first = exit on the run's "
                         "first day; single = trade lone event days only."},
    "hedge": {"default": False, "type": "bool", "label": "Beta-hedge with SPY (cell 94b)",
              "tooltip": "ON adds an SPY position of signed notional beta x $50,000 (60-day daily beta, measured "
                         "up to the session before entry) on the same clocks; beta < 0 -> short SPY."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 94a)": {"events": ["FOMC+CPI+EMP"], "entry_min": [960], "exit_min": [960],
                                   "block": ["hold"], "hedge": [False]},
    "Medium (the hunt's cells + neighbours)": {"events": ["FOMC+CPI+EMP", "FOMC+EMP", "CPI+EMP"],
                                               "entry_min": [900, 960], "exit_min": [600, 720, 840, 960],
                                               "block": ["hold", "first"], "hedge": [False, True]},
}

PNL_UNITS = "usd"

_CLOSE_MIN = 960         # 16:00 ET
_OPEN_MIN = 570          # 09:30 ET
_BETA_LEN = 60           # daily returns in the hedge's beta
_SPY_BORROW = 0.005      # SPY borrow a year when the hedge leg is short (the hunt's assumption)
_CACHE = {}              # per-process: the panel and the bar clock (blocks and betas live in the panel)


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_EVENTCRUSH_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        p = _derive({k: z[k] for k in ("dates", "vixy_raw", "vixy_split", "spy_raw", "spy_split", "spy5")})
    _CACHE["panel"] = p
    return p


def _derive(p):
    """Add the fixed per-session series the trades read (a panel cut at an earlier date derives the same values)."""
    p = dict(p)
    p["memo"] = {}                                      # blocks and betas of THIS panel (a cut copy has its own)
    p["dates"] = np.asarray(p["dates"], np.int64)
    dt = pd.to_datetime(p["dates"].astype(str), format="%Y%m%d")
    p["daynum"] = ((dt - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).to_numpy().astype(np.int64)
    p["ratio_v"] = p["vixy_raw"] / p["vixy_split"]
    p["ratio_s"] = p["spy_raw"] / p["spy_split"]
    for k, s in (("ret_v", "vixy_split"), ("ret_s", "spy_split")):
        r = np.full(len(p[s]), np.nan)
        r[1:] = p[s][1:] / p[s][:-1] - 1
        p[k] = r
    return p


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


def _blocks(p, events, block):
    """[(row of P, row of the exit day X, X carries a selected FOMC decision)] on the panel calendar."""
    key = ("blocks", events, block)
    if key in p["memo"]:
        return p["memo"][key]
    cal = p["dates"]
    types = EVENT_SETS[events]
    ev = np.zeros(len(cal), bool)
    for t in types:
        ev |= np.isin(cal, EVENT_DAYS[t])
    fomc = np.isin(cal, EVENT_DAYS["FOMC"]) if "FOMC" in types else np.zeros(len(cal), bool)
    out = []
    n = len(cal)
    i = 0
    while i < n:
        if not ev[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and ev[j + 1]:                  # the next session's release schedule is known in advance
            j += 1
        if i >= 1 and j <= n - 2:                       # P exists; the run ends before the calendar does
            if block == "hold":
                out.append((i - 1, j, bool(fomc[j])))
            elif block == "first" or j == i:
                out.append((i - 1, i, bool(fomc[i])))
        i = j + 1
    p["memo"][key] = out
    return out


def _beta(p, i):
    """s94_run.beta_at(i): OLS slope of VIXY on SPY daily split returns over the 60 sessions ending at row i."""
    key = ("beta", int(i))
    if key in p["memo"]:
        return p["memo"][key]
    b = None
    if i - (_BETA_LEN - 1) >= 1:
        x = p["ret_s"][i - (_BETA_LEN - 1):i + 1]
        y = p["ret_v"][i - (_BETA_LEN - 1):i + 1]
        if np.isfinite(x).all() and np.isfinite(y).all():
            b = float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1))
    p["memo"][key] = b
    return b


def _spy_at(p, i, t_min):
    """SPY close of the last 5m bar of panel row i starting at or before t_min - 5 (NaN if none)."""
    k = (min(int(t_min), _CLOSE_MIN) - 5 - _OPEN_MIN) // 5
    if k < 0:
        return float("nan")
    seg = p["spy5"][i][:k + 1]
    ok = np.flatnonzero(np.isfinite(seg))
    return float(seg[ok[-1]]) if len(ok) else float("nan")


def _last_bar(minute, s, e, t_min):
    """Index of the last bar in [s, e) starting at or before t_min - 5, or -1."""
    k = s + int(np.searchsorted(minute[s:e], int(t_min) - 5, side="right")) - 1
    return k if k >= s else -1


def _trades(p, index, closes, notional=50000, cents_share=0.5, fee_bps=0.3, borrow_pct=10.0,
            events="FOMC+CPI+EMP", entry_min=960, exit_min=960, block="hold", hedge=False):
    """Every trade of one config on these bars: a list of dicts (bars, dates, prices, shares, gross, costs, net)."""
    date, minute = _clock(index)
    n = len(date)
    if n < 2:
        return []
    cut = np.flatnonzero(date[1:] != date[:-1]) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [n]])
    sdate = date[starts]
    N = float(notional)
    cps = float(cents_share) / 100.0
    fee = float(fee_bps) * 1e-4
    bor = float(borrow_pct) / 100.0
    t_in = int(entry_min)
    cl = np.asarray(closes, float)
    out = []
    for iP, iX, fomc_x in _blocks(p, events, block):
        dP, dX = int(p["dates"][iP]), int(p["dates"][iX])
        jP = int(np.searchsorted(sdate, dP))
        jX = int(np.searchsorted(sdate, dX))
        if jP >= len(sdate) or sdate[jP] != dP or jX >= len(sdate) or sdate[jX] != dX:
            continue
        t_out = _CLOSE_MIN if fomc_x else int(exit_min)
        e = _last_bar(minute, starts[jP], ends[jP], t_in)
        x = _last_bar(minute, starts[jX], ends[jX], t_out)
        if e < 0 or x < 0:
            continue
        if jX == len(sdate) - 1 and minute[x] != t_out - 5:
            continue                                    # the bars may stop inside X: never read a cut session
        c0, c1 = float(cl[e]), float(cl[x])
        if not (np.isfinite(c0) and np.isfinite(c1) and c0 > 0 and c1 > 0):
            continue
        rP, rX = float(p["ratio_v"][iP]), float(p["ratio_v"][iX])
        px_in = float(p["vixy_raw"][iP]) if t_in >= _CLOSE_MIN else c0 * rP
        sh = N / px_in
        sh_x = sh * rP / rX
        gross = N * (1 - c1 / c0)
        xnot = N * c1 / c0
        cross = (cps * sh + fee * N) + (cps * sh_x + fee * xnot)
        days = int(p["daynum"][iX] - p["daynum"][iP])
        borrow = bor * N * days / 365.0
        g_h = c_h = b_h = 0.0
        beta = H = s0 = s1 = float("nan")
        if hedge:
            beta = _beta(p, iP - 1)
            if beta is None:
                continue
            s0, s1 = _spy_at(p, iP, t_in), _spy_at(p, iX, t_out)
            if not (np.isfinite(s0) and np.isfinite(s1) and s0 > 0 and s1 > 0):
                continue
            H = beta * N                                # signed SPY notional: removes the short leg's beta
            g_h = H * (s1 / s0 - 1)
            spx_in = float(p["spy_raw"][iP]) if t_in >= _CLOSE_MIN else s0 * float(p["ratio_s"][iP])
            shs = abs(H) / spx_in
            c_h = ((cps * shs + fee * abs(H))
                   + (cps * shs * float(p["ratio_s"][iP]) / float(p["ratio_s"][iX]) + fee * abs(H) * s1 / s0))
            b_h = _SPY_BORROW * abs(H) * days / 365.0 if H < 0 else 0.0
        cost = cross + borrow + c_h + b_h
        out.append({"e": int(e), "x": int(x), "P": dP, "X": dX, "iP": int(iP), "iX": int(iX), "c0": c0, "c1": c1,
                    "shares": sh, "shares_exit": sh_x, "gross_vixy": gross, "gross_spy": g_h, "cross": cross,
                    "borrow": borrow, "cost_spy": c_h + b_h, "cost": cost, "net": gross + g_h - cost,
                    "beta": beta, "H": H, "s0": s0, "s1": s1, "days": days})
    return out


def _cfg_ok(events, entry_min, exit_min, block):
    try:
        return (events in EVENT_SETS and block in BLOCK_MODES
                and _OPEN_MIN + 5 <= int(entry_min) <= _CLOSE_MIN and int(entry_min) % 5 == 0
                and _OPEN_MIN + 5 <= int(exit_min) <= _CLOSE_MIN and int(exit_min) % 5 == 0)
    except (TypeError, ValueError):
        return False


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 50000, cents_share: float = 0.5, fee_bps: float = 0.3, borrow_pct: float = 10.0,
                 events: str = "FOMC+CPI+EMP", entry_min: int = 960, exit_min: int = 960, block: str = "hold",
                 hedge: bool = False,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None or len(index) != n:
        return None
    if not _cfg_ok(events, entry_min, exit_min, block):
        return None
    p = _panel()
    if p is None:
        return None
    if _stop_event is not None and _stop_event.is_set():
        return None
    rows = _trades(p, index, closes, notional=notional, cents_share=cents_share, fee_bps=fee_bps,
                   borrow_pct=borrow_pct, events=events, entry_min=entry_min, exit_min=exit_min, block=block,
                   hedge=bool(hedge))
    trades = [(r["e"], r["x"], float(r["net"]), -1, r["c0"], r["c1"]) for r in rows]
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
    """Each trade's open value in dollars at the last bar of every session it is held through before its exit
    session (P, and the first days of a held run): the VIXY short -N x (C(k) / C(entry) - 1), plus the SPY leg
    H x (SPY close(k) / SPY(entry) - 1) when hedged. One [(bar, usd), ...] list per trade, in trade order. Costs are
    left out - they land on the exit day with the rest of the closed P&L."""
    out = [[] for _ in (trades or [])]
    if not trades or index is None or len(index) != len(closes):
        return out
    p = _panel()
    if p is None:
        return out
    prm = {k: v["default"] for k, v in DEFAULT_PARAMS.items()}
    prm.update({k: v for k, v in params.items() if k in DEFAULT_PARAMS})
    if not _cfg_ok(prm["events"], prm["entry_min"], prm["exit_min"], prm["block"]):
        return out
    prm["hedge"] = bool(prm["hedge"])
    rows = {(r["e"], r["x"]): r for r in _trades(p, index, closes, **prm)}
    date, _ = _clock(index)
    last = np.flatnonzero(np.concatenate([date[1:] != date[:-1], [True]]))
    row_of = {int(d): i for i, d in enumerate(p["dates"])}
    cl = np.asarray(closes, float)
    N = float(prm["notional"])
    for j, t in enumerate(trades):
        r = rows.get((int(t[0]), int(t[1])))
        if r is None:
            continue
        held = last[(last >= r["e"]) & (last < r["x"])]
        marks = []
        for k in held:
            v = -N * (cl[k] / r["c0"] - 1)
            if prm["hedge"]:
                rk = row_of.get(int(date[k]))
                sk = _spy_at(p, rk, _CLOSE_MIN) if rk is not None else float("nan")
                v += r["H"] * (sk / r["s0"] - 1) if np.isfinite(sk) else 0.0
            marks.append((int(k), float(v)))
        out[j] = marks
    return out
