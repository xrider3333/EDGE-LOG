#!/usr/bin/env python3
"""
NOISE HUNT ROUND 5 (2026-08-27) — STUDY A: DOES THE CROWN TRAVEL?

Owner ask while away: "do more testing while im away. new / better params / versions
of this."  "this" = the live NOISE configuration, run #243, on the NinjaTrader demo
since 2026-08-26.

THE CLAIM (pre-registered in full BEFORE any cell was run)
----------------------------------------------------------
Run #243's edge is a property of the NOISE mechanism rather than of the NQ 5m RTH bar
grid, so the same configuration — nothing re-fitted, not one knob touched — keeps a
recognisable edge on other bar sizes and on the 24-hour session.

THE BAR (judged on the SELECTION WINDOW ONLY, 2010-06-07 -> 2025-02-10, all four legs)

  L1  profit factor        PF   >= 1.20      NOISE's standing promotion bar (also leg 1
                                             of the 2026-08-22 ES-native pre-reg).
                                             Base cell measures 1.420.
  L2  risk-adjusted return MAR  >= 8.69      exactly HALF the base cell's own measured
                                             selection-window MAR of 17.38.
  L3  edge above the costs $/trade >= 2x the cell's own round-turn cost
                                             = $21.32 on RTH cells (0.533 pts x $20)
                                             = $31.32 on ETH cells (0.783 pts x $20).
                                             Base cell measures $78.97/trade.
  L4  breadth              >= 9 of 16 selection-window calendar years net positive
                                             (leg 3 of the 2026-08-22 ES-native pre-reg).

A cell TRAVELS only if ALL FOUR legs pass.  NET DOLLARS ARE REPORTED AND ARE NOT A LEG —
trade counts fall structurally with bar size (a session offers ~11 candidate entry bars
at 30m against 78 at 5m), so ranking cells on total dollars would measure the bar grid,
not the mechanism.

NOT MEASURABLE (printed as a dash with a reason — never a zero, never a failure):
  * fewer than 200 selection-window trades. The crown's own SPENT lockbox holds 424
    trades and NOISE.md already calls that read "a pass, but a thin one".
  * RAGGEDNESS GATE: fewer than 90% of the cell's sessions at the modal bar count
    (early-close sessions excluded from the denominator).  MEASURED 2026-08-27: this
    fires on ALL FOUR ETH cells (22.2% / 37.1% / 44.4% / 62.8% at modal), not on ETH 1m
    alone as the pre-registration expected — that expectation was arithmetic on a
    WITHIN-80%-OF-MODAL reading (98.9-99.7% on the ETH cells), which is a far looser
    statistic than the gate's own binding text.  Both are printed; the GATE is the
    at-modal number.  Consequence, as pre-registered: the ETH arm's failures land only
    in flagged cells, so THE ETH ARM IS VOID AS MECHANISM EVIDENCE — it says the
    24-hour session cannot be judged on these masters, not that the mechanism died
    there.  Every RTH cell passes the gate at 99.8-100%.  sigma is indexed by BAR
    ORDINAL WITHIN THE SESSION, so on ragged sessions ordinal k is a different clock
    time on different days and a failure there cannot be told apart from a data
    artifact.  A flagged cell prints its numbers, is flagged, and CANNOT ALONE CARRY A
    MECHANISM VERDICT.

READ THIS FIRST — the bar-size trap this round was commissioned to handle DOES NOT EXIST.
`lookback=44` counts SESSIONS, not bars (NOISE_1_0.py:141 labels it verbatim "Noise
lookback (sessions)"; _sigma_matrix averages AD[si-lookback:si, :] over the previous 44
SESSIONS at the same bar ordinal).  44 sessions is 44 sessions at 1m and at 30m.  A
"clock-matched" second reading (lookback 220/110/73/44/22/15/7) would be a FABRICATED
axis and is NOT run.  Every other knob in #243 is session-counted or scale-free:
vol_skip_pct ranks the prior session's (H-L)/C over 252 sessions; daytype_lo reads the
prior session's close-in-range; stop_k and band_mult_* scale the band; window='all_day',
confirm_bars=1 and time_stop_bars=0 make the three genuinely bar-counted knobs inert.
The REAL bar-size confound is sigma's ordinal indexing — handled by the raggedness gate
above rather than left to be discovered in the results.

RESCUE DIAGNOSTIC (declared now, NON-PROMOTING).  Any cell that FAILS the bar is re-run
at lookback in {22, 88} — half and double the crown's session depth — purely to separate
"the mechanism does not work at this bar size" from "44 sessions is the wrong reference
depth at this bar size".  A RESCUE CELL CAN NEVER PRODUCE A "TRAVELS" VERDICT.

ATTRIBUTION CONTROL on every cell: the same cell with BOTH FILTERS OFF (the NOISE_225
core), exactly as the 2026-08-24 NT parity study ran its BASE control.  Never a
candidate — it is what tells the reader whether a failing cell failed the MECHANISM or
failed the FILTERS.

WINDOWS
  SELECTION  2010-06-07 -> 2025-02-10  (run #231's saved validate.windows.optimize).
             EVERY LEG OF THE BAR IS JUDGED HERE AND NOWHERE ELSE.
  IS / WF    one CONTINUOUS backtest over the selection window, cut at the calendar
             instant 2016-04-29 13:50 ET (last IS trade; first WF trade 2016-05-02
             13:50 ET) — #231's own is_rng/wf_rng cut resolved to an instant so every
             cell is cut at the SAME POINT IN TIME.  IS $ + WF $ = selection total.
  LB         2025-02-11 -> 2026-08-12.  SPENT.  CONFIRMATORY ONLY, read once after every
             verdict above is written, NEVER used to rank, order or select any cell.
             Both house conventions printed side by side (fresh pass and continuous
             slice).  The lockbox is treated as SPENT FOR THE NON-5m CELLS TOO — a
             different bar size is a different VIEW OF THE SAME TAPE ON THE SAME MARKET
             DAYS, not new data, and reading a 15m or 30m 2025-26 slice as untouched
             holdout would be lockbox shopping through a side door.

COSTS       RTH cells 0.533 pts round-turn x $20/pt (tools/noise_variant_research.py).
            ETH cells 0.783 pts round-turn x $20/pt (comm 0.283 + the 0.5-pt Globex
            slippage of the 2026-07-14 round-6 GLOBEX precedent; the same constant
            tools/r14_overnight_check.py and tools/r16_misc_triage.py use).  The 0.533
            reading is printed beside each ETH row as a sensitivity column LABELLED
            "not the bar".

ETH SESSIONS  augur_engine.load_master_arrays factorizes day_id on the ET CALENDAR DATE,
            which would cut the Globex session at midnight and make 18:00-24:00 its own
            six-hour "session".  Every ETH cell therefore uses tools/orb_hunt4.py's
            idiom — session id = (timestamp + 6h).date — so the session is the TRADE
            DATE.  Required implementation detail, not an option.

REPRODUCTION GATES — nothing prints unless all pass.
  G1  base cell, filters ON  : 4,054 trades / $320,130 / DD $18,425 (selection window)
  G2  base cell, filters OFF : 5,113 / $277,123.31 / DD $19,482.27
  G3  continuous-run equivalence: the selection-window slice of a full-window run equals
      a run stopped at 2025-02-10 to the cent (the strategy is fully causal, so this must
      hold; it is what licenses one run per cell instead of two)
  G4  resampler parity: the harness's session-anchored resampler, fed the registered 1m
      RTH master and asked for 5m, must reproduce the registered 5m RTH master's bars —
      >= 99% of session-bars identical on open/high/low/close to the tick.  If this fails
      every harness-resampled cell is DROPPED and the round runs only on registered
      masters.

NO RUNNER JOB IS QUEUED BY THIS STUDY UNDER ANY OUTCOME.  The runner is not restarted.
No data master is imported, refreshed or registered.  Local library calls only.

    python tools/noise_hunt5.py travel              # the whole study
    python tools/noise_hunt5.py travel --cells rth  # RTH ladder only
    python tools/noise_hunt5.py travel --cells eth  # ETH ladder only
    python tools/noise_hunt5.py --gate              # reproduction gates only
"""
import os
import sys
import argparse
from collections import Counter

import numpy as np
import pandas as pd

# The master-CSV registry (optimizer_history.db + augur_uploads/) lives only in the
# shared checkout, not in a git worktree. EDGELOG_DATA_ROOT lets this script run from a
# worktree against the real data; unset, it resolves to its own checkout as usual.
EDGELOG_ROOT = os.environ.get("EDGELOG_DATA_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(EDGELOG_ROOT, "tools"), EDGELOG_ROOT):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from noise_variant_research import run_variant, CHAMPION               # noqa: E402

# ── windows (all pinned to run #231's saved validate.windows) ────────────────────
OPT_TO = "2025-02-10"          # selection-window end
LB_FROM, LB_TO = "2025-02-11", "2026-08-12"
IS_CUT = "2016-04-29 13:50"    # last IS trade; first WF trade 2016-05-02 13:50 ET

# ── costs (house constants, unchanged) ───────────────────────────────────────────
COST_RTH, COST_ETH, MULT = 0.533, 0.783, 20.0

# ── the pre-registered bar ───────────────────────────────────────────────────────
BAR_PF, BAR_MAR, BAR_DPT_MULT, BAR_YEARS = 1.20, 8.69, 2.0, 9
MIN_TRADES = 200               # below this: NOT MEASURABLE
RAGGED_MIN = 0.90              # >=90% of sessions at the modal bar count
EARLY_CLOSE_HOUR = 15          # a session whose last bar is before 15:00 ET is a half-day

# ── the subject: run #243, verbatim, in the research harness's vocabulary ────────
# NOISE_1_0's `vol_skip_pct` knob == the harness's rv_mode='skip_hi' + rv_pct.
CROWN = dict(CHAMPION, daytype_mode="skip_bot_short", daytype_lo=0.20, daytype_hi=0.80,
             rv_mode="skip_hi", rv_pct=90.0)
CORE = dict(CHAMPION)          # attribution control: both filters OFF (= NOISE_225)

# banked selection-window reference numbers (NOISE.md, 2026-08-17 campaign table)
G1 = (4054, 320130.0, 18425.0)          # crown, filters on
G2 = (5113, 277123.31, 19482.27)        # core,  filters off

_ARR = {}


# ═════════════════════════════════════════════════════════════════════════════════
# metrics — identical math to tools/noise_campaign_table.stats, with the cost and
# the calendar-year breakdown the pre-registered bar needs. MaxDD PRINTED POSITIVE.
# ═════════════════════════════════════════════════════════════════════════════════
def stats(seq, mult=MULT):
    """seq = [(entry_datetime, net_pnl_points), ...] in time order."""
    if not seq:
        return None
    p = [x[1] for x in seq]
    gw = sum(x for x in p if x > 0)
    gl = -sum(x for x in p if x < 0)
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    cum = peak = mdd = 0.0
    for x in p:
        cum += x
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    net = sum(p) * mult
    dd = abs(mdd) * mult
    pyear = {}
    for dt, v in seq:
        y = int(dt.year)
        pyear[y] = pyear.get(y, 0.0) + v * mult
    return dict(n=len(p), net=net, pf=pf, dd=dd,
                mar=(net / dd) if dd > 1e-9 else float("inf"),
                win=100.0 * sum(1 for x in p if x > 0) / len(p),
                dpt=net / len(p), pyear=pyear,
                pos_years=sum(1 for v in pyear.values() if v > 0), n_years=len(pyear))


def net_seq(arr, params, cost):
    tr = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                     arr.get("volume"), arr["day_id"], **params)
    idx = arr["index"]
    return [(idx[t[0]], t[2] - cost) for t in tr]


def _ts(s, idx):
    t = pd.Timestamp(s)
    tz = getattr(idx, "tz", None)
    return t.tz_localize(tz) if (tz is not None and t.tzinfo is None) else t


# ═════════════════════════════════════════════════════════════════════════════════
# data
# ═════════════════════════════════════════════════════════════════════════════════
def load_rth(tf):
    """Registered RTH master. day_id = ET calendar date, which IS the session for RTH."""
    m = find_master("NQ", tf, "rth", "db_noadj_rth")
    if m is None:
        return None, None
    arr = load_master_arrays(m, date_from=None, date_to=LB_TO)
    return dict(arr), m


def load_eth(tf):
    """Registered ETH master, loaded with tools/orb_hunt4.py's session idiom:
    session id = (timestamp + 6h).date, so the Globex session is the TRADE DATE and
    not two pieces cut at midnight."""
    m = find_master("NQ", tf, "eth", "db_noadj_eth")
    if m is None:
        return None, None
    path = os.path.join(EDGELOG_ROOT, "augur_uploads", m["filename"])
    df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close", "volume"])
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[df["_dt"] < pd.Timestamp(LB_TO, tz="US/Eastern") + pd.Timedelta(days=1)]
    df = df.reset_index(drop=True)
    sess = (df["_dt"] + pd.Timedelta(hours=6)).dt.date
    return dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                volume=df["volume"].values.astype(float),
                day_id=pd.factorize(sess)[0].astype("int64"),
                index=pd.DatetimeIndex(df["_dt"])), m


def _session_offset_minutes(idx, eth):
    """Minutes since the SESSION's own open — 09:30 ET for RTH, 18:00 ET for ETH."""
    if eth:
        s = idx + pd.Timedelta(hours=6)          # 18:00 ET -> 00:00 of the trade date
        return np.asarray(s.hour) * 60 + np.asarray(s.minute)
    return np.asarray(idx.hour) * 60 + np.asarray(idx.minute) - 570


def resample(arr, k_min, eth):
    """Session-anchored OHLCV resample (o=first h=max l=min c=last v=sum).  Buckets are
    CLOCK buckets measured from the session open, not bar-ordinal buckets, so a missing
    bar cannot slide the whole rest of the session onto the wrong grid."""
    idx = arr["index"]
    off = _session_offset_minutes(idx, eth)
    did = np.asarray(arr["day_id"], dtype=np.int64)
    key = did * 100000 + (off // int(k_min))
    change = np.empty(len(key), bool)
    change[0] = True
    change[1:] = key[1:] != key[:-1]
    starts = np.flatnonzero(change)
    ends = np.append(starts[1:], len(key))
    return dict(open=arr["open"][starts], close=arr["close"][ends - 1],
                high=np.maximum.reduceat(arr["high"], starts),
                low=np.minimum.reduceat(arr["low"], starts),
                volume=np.add.reduceat(arr["volume"], starts),
                day_id=did[starts], index=idx[starts])


def slice_arr(arr, date_from=None, date_to=None):
    idx = arr["index"]
    m = np.ones(len(idx), bool)
    if date_from:
        m &= np.asarray(idx >= _ts(date_from, idx))
    if date_to:
        m &= np.asarray(idx < _ts(date_to, idx) + pd.Timedelta(days=1))
    out = {k: (v[m] if isinstance(v, np.ndarray) else v) for k, v in arr.items()
           if k != "index"}
    out["index"] = idx[m]
    return out


def raggedness(arr):
    """(frac_at_modal, modal_bars, n_sessions, n_early_close) over the SELECTION window.
    Early-close sessions (last bar before 15:00 ET) are excluded from the denominator —
    every NQ RTH master carries the same 127-128 of them."""
    a = slice_arr(arr, None, OPT_TO)
    idx, did = a["index"], np.asarray(a["day_id"])
    if len(idx) == 0:
        return None
    change = np.empty(len(did), bool)
    change[0] = True
    change[1:] = did[1:] != did[:-1]
    starts = np.flatnonzero(change)
    ends = np.append(starts[1:], len(did))
    counts = ends - starts
    last_hour = np.asarray(idx[ends - 1].hour)
    early = last_hour < EARLY_CLOSE_HOUR
    full = counts[~early]
    if len(full) == 0:
        return None
    modal, at_modal = Counter(full.tolist()).most_common(1)[0]
    # `frac` IS THE PRE-REGISTERED GATE: fraction of full sessions AT the modal bar
    # count. `near80` is a DIAGNOSTIC ONLY, printed beside it because the
    # pre-registration's expectation of where the flag would fire ("ETH 1m only") was
    # computed from a within-80%-of-modal reading, which is a much looser statistic
    # than the gate's own text. Reporting both keeps the two apart; the GATE is `frac`.
    return dict(frac=at_modal / len(full), modal=modal, n_sess=len(counts),
                near80=float(np.mean(full >= 0.8 * modal)),
                n_under80=int(np.sum(full < 0.8 * modal)),
                n_early=int(early.sum()), n_full=len(full))


# ═════════════════════════════════════════════════════════════════════════════════
# one cell
# ═════════════════════════════════════════════════════════════════════════════════
def evaluate(arr, params, cost):
    """One CONTINUOUS run over the whole master; every stretch sliced out of it, plus
    the FRESH lockbox pass the engine's own lockbox convention uses."""
    full = net_seq(arr, params, cost)
    idx = arr["index"]
    opt_end = _ts(OPT_TO, idx) + pd.Timedelta(days=1)
    cut = _ts(IS_CUT, idx)
    lb0 = _ts(LB_FROM, idx)
    opt = [t for t in full if t[0] < opt_end]
    lb_fresh = net_seq(slice_arr(arr, LB_FROM, LB_TO), params, cost)
    return dict(OPT=stats(opt), IS=stats([t for t in opt if t[0] <= cut]),
                WF=stats([t for t in opt if t[0] > cut]),
                LBC=stats([t for t in full if t[0] >= lb0]),
                LBF=stats(lb_fresh), TOTAL=stats(full))


def verdict(s, cost, ragged):
    """The four pre-registered legs.  Returns (label, legs dict, reason-if-not-measurable)."""
    if s is None or s["n"] < MIN_TRADES:
        n = 0 if s is None else s["n"]
        return "NOT MEASURABLE", None, "only %d selection-window trades (<%d)" % (n, MIN_TRADES)
    legs = {
        "L1 PF>=%.2f" % BAR_PF: s["pf"] >= BAR_PF,
        "L2 MAR>=%.2f" % BAR_MAR: s["mar"] >= BAR_MAR,
        "L3 $/tr>=%.2f" % (BAR_DPT_MULT * cost * MULT): s["dpt"] >= BAR_DPT_MULT * cost * MULT,
        "L4 yrs>=%d" % BAR_YEARS: s["pos_years"] >= BAR_YEARS,
    }
    lab = "TRAVELS" if all(legs.values()) else "FAILS"
    if ragged is not None and ragged["frac"] < RAGGED_MIN:
        lab += " (RAGGED-FLAGGED)"
    return lab, legs, None


# ═════════════════════════════════════════════════════════════════════════════════
# cell list
# ═════════════════════════════════════════════════════════════════════════════════
# (key, label, session, how-to-build, note)
CELLS = [
    ("1m-RTH",  "NQ 1m  RTH", "rth", ("master", "1m"),          "native master id 35"),
    ("2m-RTH",  "NQ 2m  RTH", "rth", ("master", "2m"),          "registered resample of id 35, ends 2026-07-16"),
    ("3m-RTH",  "NQ 3m  RTH", "rth", ("resample", "1m", 3),     "HARNESS-RESAMPLED 1m->3m"),
    ("5m-RTH",  "NQ 5m  RTH", "rth", ("master", "5m"),          "BASE CELL - native master id 37"),
    ("10m-RTH", "NQ 10m RTH", "rth", ("resample", "5m", 10),    "HARNESS-RESAMPLED 5m->10m"),
    ("15m-RTH", "NQ 15m RTH", "rth", ("master", "15m"),         "registered, ends 2026-06-30"),
    ("30m-RTH", "NQ 30m RTH", "rth", ("master", "30m"),         "registered, ends 2026-06-30"),
    ("60m-RTH", "NQ 60m RTH", "rth", ("master", "60m"),         "registered, ends 2026-06-30"),
    ("1m-ETH",  "NQ 1m  ETH", "eth", ("master", "1m"),          "native master id 34 - raggedness flag EXPECTED here"),
    ("5m-ETH",  "NQ 5m  ETH", "eth", ("master", "5m"),          "native master id 36 - the 24-hour session"),
    ("15m-ETH", "NQ 15m ETH", "eth", ("resample", "5m", 15),    "HARNESS-RESAMPLED 5m ETH->15m"),
    ("30m-ETH", "NQ 30m ETH", "eth", ("resample", "5m", 30),    "HARNESS-RESAMPLED 5m ETH->30m"),
]


def get_arr(session, spec):
    """Build (or fetch) one cell's arrays.  Returns (arrays, master_row_or_None)."""
    kind = spec[0]
    if kind == "master":
        key = (session, spec[1])
        if key not in _ARR:
            _ARR[key] = load_eth(spec[1]) if session == "eth" else load_rth(spec[1])
        return _ARR[key]
    src, k = spec[1], spec[2]
    base, m = get_arr(session, ("master", src))
    if base is None:
        return None, None
    key = (session, "%dm-from-%s" % (k, src))
    if key not in _ARR:
        _ARR[key] = (resample(base, k, session == "eth"), m)
    return _ARR[key]


# ═════════════════════════════════════════════════════════════════════════════════
# reproduction gates
# ═════════════════════════════════════════════════════════════════════════════════
def gates(verbose=True):
    ok = True
    arr, _ = get_arr("rth", ("master", "5m"))
    if arr is None:
        print("  G1/G2/G3  NO MASTER for NQ/5m/rth/db_noadj_rth"); return False
    sel = slice_arr(arr, None, OPT_TO)

    for name, params, (en, enet, edd) in (("G1 crown filters-ON", CROWN, G1),
                                          ("G2 core  filters-OFF", CORE, G2)):
        s = stats(net_seq(sel, params, COST_RTH))
        good = s["n"] == en and abs(s["net"] - enet) < 1.0 and abs(s["dd"] - edd) < 1.0
        ok &= good
        if verbose:
            print("  %-22s n=%-5d net=$%-11s DD=$%-10s  %s" % (
                name, s["n"], format(s["net"], ",.2f"), format(s["dd"], ",.2f"),
                "PASS" if good else "FAIL (exp n=%d net=%.2f dd=%.2f)" % (en, enet, edd)))

    # G3 — the selection-window slice of a full-window run == a run stopped at OPT_TO
    a = stats(net_seq(sel, CROWN, COST_RTH))
    b = evaluate(arr, CROWN, COST_RTH)["OPT"]
    good = (a["n"] == b["n"] and abs(a["net"] - b["net"]) < 0.01
            and abs(a["dd"] - b["dd"]) < 0.01)
    ok &= good
    if verbose:
        print("  %-22s slice n=%d net=$%s | stop-at-OPT_TO n=%d net=$%s  %s" % (
            "G3 causality/slice", b["n"], format(b["net"], ",.2f"), a["n"],
            format(a["net"], ",.2f"), "PASS" if good else "FAIL"))

    # G4 — resampler parity: registered 1m -> 5m must reproduce the registered 5m master
    one, _ = get_arr("rth", ("master", "1m"))
    five = arr
    if one is None:
        print("  G4 resampler parity   NO 1m MASTER — every harness-resampled cell DROPPED")
        return False
    rs = resample(one, 5, False)
    a = pd.DataFrame({"o": rs["open"], "h": rs["high"], "l": rs["low"], "c": rs["close"]},
                     index=rs["index"])
    b = pd.DataFrame({"o": five["open"], "h": five["high"], "l": five["low"],
                      "c": five["close"]}, index=five["index"])
    b = b[b.index <= a.index.max()]
    j = b.join(a, how="left", rsuffix="_r")
    same = ((j["o"] == j["o_r"]) & (j["h"] == j["h_r"]) & (j["l"] == j["l_r"])
            & (j["c"] == j["c_r"])).sum()
    frac = same / len(j) if len(j) else 0.0
    good = frac >= 0.99
    ok &= good
    if verbose:
        print("  %-22s %s of %s registered 5m bars reproduced to the tick = %.3f%%  %s" % (
            "G4 resampler parity", format(int(same), ","), format(len(j), ","),
            100 * frac, "PASS" if good else "FAIL — harness-resampled cells DROPPED"))
    return bool(ok), bool(good)


# ═════════════════════════════════════════════════════════════════════════════════
# printing
# ═════════════════════════════════════════════════════════════════════════════════
HDR = ("%-26s %6s %12s %7s %11s %7s %7s %10s %6s" %
       ("", "n", "net $", "PF", "maxDD $", "net/DD", "win %", "$/trade", "yrs+"))


def row(label, s):
    if s is None:
        return "%-26s %6s %12s %7s %11s %7s %7s %10s %6s" % (
            label, "-", "-", "-", "-", "-", "-", "-", "-")
    return "%-26s %6d %12s %7.3f %11s %7.2f %7.1f %10s %4d/%-2d" % (
        label, s["n"], format(s["net"], ",.0f"), min(s["pf"], 99.999),
        format(s["dd"], ",.0f"), min(s["mar"], 999.99), s["win"],
        format(s["dpt"], ",.2f"), s["pos_years"], s["n_years"])


def run_travel(which="all"):
    print(__doc__.split("    python tools/noise_hunt5.py")[0].rstrip())
    print("\n" + "=" * 118)
    print("REPRODUCTION GATES")
    print("=" * 118)
    ok, resampler_ok = gates()
    if not ok and not resampler_ok:
        print("\nGATE FAILURE — nothing printed. (House rule: nothing prints unless the gates pass.)")
        return
    if not ok:
        print("\nGATE FAILURE on a banked reference — nothing printed.")
        return

    cells = [c for c in CELLS
             if which == "all" or (which == "rth" and c[2] == "rth")
             or (which == "eth" and c[2] == "eth")]

    results, dropped = [], []
    base = None
    print("\n" + "=" * 118)
    print("STUDY A — run #243 VERBATIM on other bar sizes and on the 24-hour session.")
    print("Selection window 2010-06-07 -> %s. NOTHING is re-fitted. Net $ is REPORTED, "
          "not a leg." % OPT_TO)
    print("=" * 118)

    for key, label, sess, spec, note in cells:
        if spec[0] == "resample" and not resampler_ok:
            dropped.append((label, "harness-resampled and G4 failed"))
            continue
        arr, m = get_arr(sess, spec)
        if arr is None:
            dropped.append((label, "NO MASTER — cell dropped, no substitute market used"))
            continue
        cost = COST_ETH if sess == "eth" else COST_RTH
        rg = raggedness(arr)
        cov = "%s -> %s" % (arr["index"][0].date(), arr["index"][-1].date())

        print("\n%s  [%s]" % (label, note))
        print("   coverage %s | %d sessions | modal %d bars/session | GATE %.1f%% of full "
              "sessions AT modal (%d early-close excluded)%s"
              % (cov, rg["n_sess"], rg["modal"], 100 * rg["frac"], rg["n_early"],
                 "   *** RAGGEDNESS GATE FAILED ***" if rg["frac"] < RAGGED_MIN else ""))
        print("   [diag, NOT the gate] %.1f%% of full sessions within 80%% of modal; "
              "%d sessions below that" % (100 * rg["near80"], rg["n_under80"]))
        print("   cost %.3f pts round-turn x $%.0f/pt   L3 threshold $%.2f/trade"
              % (cost, MULT, BAR_DPT_MULT * cost * MULT))
        print("   " + HDR)

        ev = evaluate(arr, CROWN, cost)
        evc = evaluate(arr, CORE, cost)
        print("   " + row("#243 CROWN  selection", ev["OPT"]))
        print("   " + row("     .. IS  (to 2016-04)", ev["IS"]))
        print("   " + row("     .. WF  (2016-05 on)", ev["WF"]))
        print("   " + row("CORE filters-off  [attr]", evc["OPT"]))
        if sess == "eth":
            alt = evaluate(arr, CROWN, COST_RTH)["OPT"]
            print("   " + row("  ^ crown @0.533 (NOT BAR)", alt))

        v, legs, why = verdict(ev["OPT"], cost, rg)
        if legs is None:
            print("   VERDICT: %s — %s" % (v, why))
        else:
            print("   VERDICT: %-22s  %s" % (v, "  ".join(
                "%s %s" % (k, "PASS" if b else "FAIL") for k, b in legs.items())))
        results.append((key, label, sess, arr, cost, rg, ev, evc, v, legs))
        if key == "5m-RTH":
            base = (ev, evc)
        sys.stdout.flush()

    # ── summary against the base cell ────────────────────────────────────────────
    print("\n" + "=" * 118)
    print("SUMMARY — every row read against the base cell (#243 crown, selection window)")
    print("=" * 118)
    print(HDR + "  verdict")
    for key, label, sess, arr, cost, rg, ev, evc, v, legs in results:
        print(row(label + (" *BASE*" if key == "5m-RTH" else ""), ev["OPT"]) + "  " + v)
    if base is not None:
        b = base[0]["OPT"]
        print("\nbase cell reference: PF %.3f | MAR %.2f | $/trade %.2f | %d/%d years positive"
              % (b["pf"], b["mar"], b["dpt"], b["pos_years"], b["n_years"]))

    # ── rescue diagnostic ────────────────────────────────────────────────────────
    failed = [r for r in results if r[8].startswith("FAILS")]
    if failed:
        print("\n" + "=" * 118)
        print("RESCUE DIAGNOSTIC (pre-declared, NON-PROMOTING — a rescue cell can NEVER "
              "produce a TRAVELS verdict).")
        print("Failing cells only, lookback 22 and 88: does 44 sessions turn out to be the "
              "wrong reference DEPTH at this bar size?")
        print("=" * 118)
        print(HDR)
        for key, label, sess, arr, cost, rg, ev, evc, v, legs in failed:
            print("%-26s   (lookback 44 above)" % label)
            for lb in (22, 88):
                s = evaluate(arr, dict(CROWN, lookback=lb), cost)["OPT"]
                tag = "  [would clear all 4 legs]" if (
                    s and s["n"] >= MIN_TRADES and s["pf"] >= BAR_PF and s["mar"] >= BAR_MAR
                    and s["dpt"] >= BAR_DPT_MULT * cost * MULT
                    and s["pos_years"] >= BAR_YEARS) else ""
                print(row("   lookback %-3d [diag]" % lb, s) + tag)
            sys.stdout.flush()

    # ── lockbox, read ONCE, after every verdict above is written ─────────────────
    print("\n" + "=" * 118)
    print("LOCKBOX 2025-02-11 -> 2026-08-12 — SPENT. CONFIRMATORY ONLY. Read once, AFTER "
          "every verdict above.")
    print("Not used to rank, order or select any cell. A different bar size is a different "
          "VIEW OF THE SAME TAPE")
    print("on the same market days — not new data — so the lockbox is spent for the non-5m "
          "cells too.")
    print("=" * 118)
    print("%-26s %28s   %28s" % ("", "LB fresh pass", "LB continuous slice"))
    print("%-26s %6s %12s %7s   %6s %12s %7s" % ("", "n", "net $", "PF", "n", "net $", "PF"))
    for key, label, sess, arr, cost, rg, ev, evc, v, legs in results:
        f, c = ev["LBF"], ev["LBC"]
        def _c(s):
            return ("%6d %12s %7.3f" % (s["n"], format(s["net"], ",.0f"), min(s["pf"], 99.999))
                    if s else "%6s %12s %7s" % ("-", "-", "-"))
        print("%-26s %s   %s" % (label, _c(f), _c(c)))

    if dropped:
        print("\nDROPPED CELLS (never silently substituted with another market):")
        for label, why in dropped:
            print("  %-26s %s" % (label, why))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep", nargs="?", default="travel", choices=["travel"])
    ap.add_argument("--cells", default="all", choices=["all", "rth", "eth"])
    ap.add_argument("--gate", action="store_true", help="reproduction gates only")
    a = ap.parse_args()
    if a.gate:
        ok, _ = gates()
        sys.exit(0 if ok else 1)
    run_travel(a.cells)
