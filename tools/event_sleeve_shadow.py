"""
EVENT SLEEVE forward shadow scorer - docs/PREREG_event_sleeve_forward_2026-10-11.md (sections 1-6). No orders, no broker:
it reads house data only and writes under C:\\EdgeLog\\event_sleeve\\.

    python tools/event_sleeve_shadow.py parity                       # rebuild each part's WF trades from its source, vs the ledger
    python tools/event_sleeve_shadow.py constants [--force]          # section 3 scale factors + section 5 harm bar -> addendum1_constants.json
    python tools/event_sleeve_shadow.py forward --since YYYY-MM-DD   # score trades ENTERED after --since (stale parts are REFUSED)

The three parts and the harnesses they are imported from (logic is imported, never re-written; the few pieces that are not
importable are COPIED verbatim and say so where they sit):
  A  AUCTION K5     tools/tvnt2_triage.py (+ tvnt1_triage.py): IEF + TLT, short t-6 close -> t close, long t -> t+5, the
                    announcement rule, early-close skips, 2 bps a side + 0.25 %/yr borrow. Source unit: $50,000 per fund.
  B  MONTH-END ES   tools/rocfrontier/rebal_scan.py run(): K 5, |SPY - TLT month-to-date| >= 2 %, exit at the month's last
                    close, roll seam removed. Source unit: 1 ES contract ($50 a point).
  C  08:30 FADE NQ  tools/orb_nt1_macro830.py (+ orb_nt_common.py): the fade mirror of the NQ "every release day" cell, entry at
                    the 08:35 bar open AGAINST m, exit at the 09:59 bar close, 0.533 pt. Source unit: 1 NQ contract ($20 a point).

Conventions (stated once):
  * The section-3 stretch is 2016-07-16..2025-06-30 as the prereg writes it; a trade counts when it lies wholly inside it
    (entry >= start and exit <= end). SD is the sample SD (ddof 1); scale = 1000 / SD, so one risk unit = $1,000 of SD.
  * ES cost: the PREREG fixes 0.363 pt (section 1B). rebal_scan.run's own default - what produced ledger 2.18 - is 0.533 pt.
    parity uses the source's 0.533 (to reproduce 2.18); constants / forward use the prereg's 0.363; both SDs are printed.
  * Staleness: a part whose newest input is more than 3 business days (Mon-Fri, holidays not removed) before today is
    REFUSED with its reason - never scored from stale data and never filled from another source.
  * Forward trades only count once they cannot change: part A when its exit is 2K+1 sessions inside the fund data and before
    the auction calendar's fetch date; part B when its month is closed in all three inputs; part C when the master holds bars
    past 10:00 ET of the day. A release day with any 1-minute bar missing in 08:29..09:59 is SKIPPED and written to
    forward_skips.csv; once there it stays skipped (no later fill from another source).
  * The forward P&L uses the frozen scale factors in addendum1_constants.json; the scorer never recomputes them.
"""
import argparse
import contextlib
import datetime
import hashlib
import io
import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"              # the shared checkout: the master registry lives there
OUT_DIR = os.environ.get("EDGELOG_EVENT_SLEEVE", r"C:\EdgeLog\event_sleeve")
CONSTANTS_FILE = "addendum1_constants.json"
PREREG = "docs/PREREG_event_sleeve_forward_2026-10-11.md"

SD_WINDOW = (pd.Timestamp("2016-07-16"), pd.Timestamp("2025-06-30"))   # prereg section 3, as written
RISK_UNIT = 1000.0
STALE_BDAYS = 3
HARM = dict(n_draws=20000, seed=20261011, sharpe_mu=0.64, sharpe_sd=0.30, trades_per_year=55, n_trades=50, tails="t3", pct=5.0)

K_AUC = 5
ES_MULT, K_ME, TH_ME = 50.0, 5, 0.02
ES_COST_PREREG, ES_COST_SOURCE = 0.363, 0.533
NQ_MKT = "NQ"
BLS_FILE = os.path.join(SHARED, "tools", "data", "bls_dates.txt")   # untracked in git: it lives in the shared checkout only

# headline numbers as the ledger / source docs print them
REF = {
    "A": dict(label="AUCTION K5 WF (docs/TV_NEWTYPES_R2.md RESULTS, ledger 2.70)", net=35500.0, t=1.997, years_pos=7, pf=1.25,
              roc30=7.9, dd=14900.0),
    "B": dict(label="MONTH-END ES K5 2% pre-lockbox (ledger 2.18)", n=133, pf=2.27, years="12/16"),
    "C": dict(label="NT1 FADE mirror NQ WF (ledger 2.95)", n=210, net=37066.0, mean=177.0, t=1.77),
}
PARTS = ("A", "B", "C")
PART_NAME = {"A": "AUCTION K5", "B": "MONTH-END ES", "C": "08:30 FADE NQ"}
SOURCE_UNIT = {"A": "$50,000 notional per fund (IEF / TLT)", "B": "1 ES contract ($50/pt)", "C": "1 NQ contract ($20/pt)"}


# ================================================================================================ pure pieces (tested)
def trade_sd(pnls):
    """Sample SD (ddof 1) of per-trade dollars."""
    x = np.asarray(pnls, float)
    if len(x) < 2:
        raise ValueError("need at least two trades for an SD")
    return float(np.std(x, ddof=1))


def scale_factor(pnls, risk_unit=RISK_UNIT):
    """Prereg section 3: the factor that makes the per-trade SD equal one risk unit ($1,000)."""
    sd = trade_sd(pnls)
    if not sd > 0:
        raise ValueError("per-trade SD is zero")
    return risk_unit / sd


def in_window(entry, exit_, window=SD_WINDOW):
    """A trade lies wholly inside the section-3 stretch (scalars or Series)."""
    return (pd.to_datetime(entry) >= window[0]) & (pd.to_datetime(exit_) <= window[1])


def bdays_behind(end, today):
    """Business days (Mon-Fri) from `end` up to, not including, `today`: Fri -> next Wed = 3."""
    e, t = pd.Timestamp(end).date(), pd.Timestamp(today).date()
    return int(np.busday_count(e, t)) if e < t else 0


def staleness(ends, today, max_bdays=STALE_BDAYS):
    """ends: {input name: last date held}. Returns (ok, reason, worst_lag). One stale input refuses the whole part."""
    lags = {k: bdays_behind(v, today) for k, v in ends.items()}
    bad = {k: v for k, v in lags.items() if v > max_bdays}
    if bad:
        why = "; ".join("%s ends %s (%d business days before %s)" % (k, pd.Timestamp(ends[k]).date(), v, pd.Timestamp(today).date())
                        for k, v in sorted(bad.items()))
        return False, "stale input (> %d business days): %s" % (max_bdays, why), max(bad.values())
    return True, "inputs current: " + "; ".join("%s %s" % (k, pd.Timestamp(v).date()) for k, v in sorted(ends.items())), \
        max(lags.values()) if lags else 0


def draw_unit_noise(rng, shape, tails):
    """The house unit-variance draw used by MAPCHECK-F's generator (tools/rocfrontier/r12_mdl.py draw_e: t3 / sqrt(3))."""
    sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
    from r12_mdl import draw_e
    return draw_e(rng, shape, tails)


def harm_threshold(n_draws=HARM["n_draws"], seed=HARM["seed"], sharpe_mu=HARM["sharpe_mu"], sharpe_sd=HARM["sharpe_sd"],
                   trades_per_year=HARM["trades_per_year"], n_trades=HARM["n_trades"], tails=HARM["tails"], pct=HARM["pct"]):
    """Prereg section 5: prior-predictive cumulative P&L (risk units) of an n_trades sleeve. Per draw: yearly Sharpe ~
    Normal(mu, sd); per-trade P&L = unit-SD noise (t3 / sqrt 3) + Sharpe / sqrt(trades a year). Draw order is fixed: all
    Sharpes first, then the (n_draws x n_trades) noise block. Returns (pct-th percentile, summary dict)."""
    rng = np.random.default_rng(seed)
    sharpe = rng.normal(sharpe_mu, sharpe_sd, size=n_draws)
    noise = draw_unit_noise(rng, (n_draws, n_trades), tails)
    cum = (noise + (sharpe / math.sqrt(trades_per_year))[:, None]).sum(axis=1)
    thr = float(np.percentile(cum, pct))
    return thr, dict(threshold=thr, pct=pct, mean=float(cum.mean()), median=float(np.median(cum)), sd=float(cum.std(ddof=1)),
                     p1=float(np.percentile(cum, 1)), p10=float(np.percentile(cum, 10)))


def runs(pos):
    """(i, j, side) of every contiguous non-zero run - the same walk as tvnt2_triage.pos_pnl's trade loop, which does not
    return the run's start; used only to stamp each source trade with its entry."""
    out, i, n = [], 0, len(pos)
    while i < n:
        if pos[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and pos[j + 1] == pos[i]:
            j += 1
        out.append((i, j, float(pos[i])))
        i = j + 1
    return out


def auction_settled(exit_idx, n, cal_idx, K=K_AUC):
    """A part-A run is final once (1) every auction that could touch it has its whole early-close window inside the data
    (an auction at most K sessions after the exit can still merge with it; its window ends K later) and (2) it ends before the
    session the auction calendar was fetched on (an auction announced later can only open a short after that session)."""
    return (exit_idx + 2 * K + 1 <= n - 1) and (exit_idx <= cal_idx - 1)


def complete_months(index, last_date):
    """Sessions of the months that are closed by `last_date` (a later session exists): the open month is dropped, so
    rebal_scan.run never mistakes the newest session for a month-end."""
    idx = pd.DatetimeIndex(index)
    keep = idx[idx <= pd.Timestamp(last_date)]
    if not len(keep):
        return keep
    open_month = keep[-1].to_period("M")
    return keep[keep.to_period("M") < open_month]


def parse_bls(path=BLS_FILE):
    """tools/data/bls_dates.txt -> DataFrame(series, date, time). Comment lines start with '#'."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            ser, d, t = s.split("|")
            rows.append(dict(series=ser.strip(), date=pd.Timestamp(d.strip()), time=t.strip()))
    return pd.DataFrame(rows)


def release_days(bls):
    """Prereg 1C: CPI and payroll (EMP) days at 08:30 ET; a day carrying any other release time is skipped."""
    b = bls[bls.series.isin(["CPI", "EMP"])]
    bad = set(b[b.time != "08:30"].date)
    return sorted(set(b[b.time == "08:30"].date) - bad)


def fade_day(o, c, day, mult, cost):
    """Part C on one release day from START-stamped 1-minute bars (o, c: Series on a tz-aware Eastern index).
    m = close(08:34) / close(08:29) - 1; enter at the 08:35 open AGAINST m; exit at the 09:59 close; cost in points a round
    trip. Returns (row, None) or (None, reason). Every bar 08:29..09:59 must exist (prereg section 6)."""
    tz = c.index.tz
    need = pd.date_range(pd.Timestamp("%s 08:29" % pd.Timestamp(day).date(), tz=tz), periods=91, freq="1min")
    if not need.isin(c.index).all():
        return None, "incomplete 08:29-09:59 bars (%d of 91)" % int(need.isin(c.index).sum())
    c0, c1, en, ex = float(c[need[0]]), float(c[need[5]]), float(o[need[6]]), float(c[need[-1]])
    m = c1 / c0 - 1.0
    if m == 0:
        return None, "zero move"
    side = -1.0 if m > 0 else 1.0                     # the FADE: against m
    return dict(date=pd.Timestamp(day), m=m, side=side, entry_px=en, exit_px=ex,
                pnl=side * (ex - en) * mult - cost * mult), None


def sha256_lf(path):
    """sha256 of a text file with CRLF normalised to LF (the house 'LF sha256')."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ================================================================================================ source imports (lazy)
def _shared_on_path():
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)


def _imp_auction():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import tvnt1_triage as T1
    import tvnt2_triage as T2
    return T1, T2


def _imp_rebal():
    """rebal_scan runs its 72-cell scan at import (it prints lockbox columns); the house reuses it this way (rebal_book.py
    imports it for run()). Its printout is swallowed here so no lockbox number reaches the screen."""
    p = os.path.join(HERE, "rocfrontier")
    if p not in sys.path:
        sys.path.insert(0, p)
    _shared_on_path()
    if "rebal_scan" in sys.modules:
        return sys.modules["rebal_scan"]
    with contextlib.redirect_stdout(io.StringIO()):
        import rebal_scan as R
    return R


def _imp_nt1():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import orb_nt_common as NC          # sets cwd to the shared checkout and puts it on sys.path (as the source runs)
    import orb_nt1_macro830 as NT1
    return NC, NT1


def _data():
    _shared_on_path()
    from augur_engine.data import find_master, load_master_arrays
    return find_master, load_master_arrays


def master_last_bar(inst, tf, session, source):
    """Last bar of a registered master, read from the file's tail (no full load). Returns an Eastern Timestamp."""
    find_master, _ = _data()
    from augur_engine.paths import UPLOADS
    m = find_master(inst, tf, session, source)
    if m is None:
        raise SystemExit("no master registered for %s %s %s %s" % (inst, tf, session, source))
    p = os.path.join(UPLOADS, m["filename"])
    with open(p, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 8192))
        last = f.read().decode("utf-8", "replace").strip().splitlines()[-1]
    return pd.Timestamp(int(float(last.split(",")[0])), unit="s", tz="UTC").tz_convert("US/Eastern")


def _day(ts):
    t = pd.Timestamp(ts)
    return (t.tz_convert("US/Eastern").tz_localize(None) if t.tzinfo else t).normalize()


# ================================================================================================ part A - AUCTION K5
def auction_trades(C, ev, early, K=K_AUC):
    """The K cell of tvnt2_triage.auction_cell (both funds, both halves, early-close skips), one fund at a time so each trade
    keeps its entry. Entry = the close the position opens at (interval i runs close i-1 -> close i)."""
    _, T2 = _imp_auction()
    rows = []
    for f in ("IEF", "TLT"):
        pos = T2.auction_pos(len(C), T2.keep_events(ev[f], K, early), K)
        _, tr = T2.pos_pnl(C, f, pos)
        rr = runs(pos)
        assert len(rr) == len(tr), "run walk disagrees with pos_pnl"
        for (i, j, s), (x, p, g) in zip(rr, tr):
            assert C.index[j] == x and g == f
            rows.append(dict(part="A", instrument=f, entry=C.index[max(i - 1, 0)], exit=x, side=s, pnl=float(p), i=i, j=j))
    return pd.DataFrame(rows).sort_values(["exit", "instrument"]).reset_index(drop=True)


def auction_trade_daily(C, row):
    """One trade's daily P&L by the source's own convention (tvnt2_triage.pos_pnl on that run alone: the entry side's cost
    lands on the first holding day, the exit side's on the next session)."""
    _, T2 = _imp_auction()
    pos = np.zeros(len(C))
    pos[int(row["i"]): int(row["j"]) + 1] = row["side"]
    d, _ = T2.pos_pnl(C, row["instrument"], pos)
    return d[d != 0]


def load_fund_closes_fwd():
    """ADAPTED from tools/tvnt1_triage.py load() - the same four research-cache files for the session calendar and IEF,
    and the same TLT yahoo_adj master - read WITHOUT the 2025-06-30 cut and date_to (forward use). Only IEF and TLT kept."""
    T1, _ = _imp_auction()
    so = pd.read_csv(os.path.join(T1.CACHE, "sector_open.csv"), index_col=0, parse_dates=True)
    sc = pd.read_csv(os.path.join(T1.CACHE, "sector_close.csv"), index_col=0, parse_dates=True)
    no = pd.read_csv(os.path.join(T1.CACHE, "nonequity_open.csv"), index_col=0, parse_dates=True)
    nc = pd.read_csv(os.path.join(T1.CACHE, "nonequity_close.csv"), index_col=0, parse_dates=True)
    O = pd.concat([so, no], axis=1)
    C = pd.concat([sc, nc], axis=1)
    find_master, load_master_arrays = _data()
    A = load_master_arrays(find_master("TLT", "1d", "rth", "yahoo_adj"))
    ix = pd.DatetimeIndex(A["index"]).tz_localize(None).normalize()
    O["TLT"] = pd.Series(np.asarray(A["open"], float), index=ix)
    C["TLT"] = pd.Series(np.asarray(A["close"], float), index=ix)
    O = O.sort_index()
    C = C.sort_index().reindex(O.index)
    return C[["IEF", "TLT"]]


def auction_calendar_fetch_date():
    _, T2 = _imp_auction()
    try:
        with open(T2.PROV_FILE) as f:
            at = json.load(f)["treasury_auctions"]["fetched_at"]
        return pd.Timestamp(at[:10])
    except (OSError, KeyError, ValueError):
        return pd.Timestamp(datetime.date.fromtimestamp(os.path.getmtime(T2.AUC_FILE)))


def part_a_ends():
    T1, _ = _imp_auction()
    nc = pd.read_csv(os.path.join(T1.CACHE, "nonequity_close.csv"), index_col=0, parse_dates=True)
    return {"IEF close (research cache nonequity_close.csv)": nc["IEF"].last_valid_index(),
            "TLT close (yahoo_adj 1d master)": _day(master_last_bar("TLT", "1d", "rth", "yahoo_adj")),
            "auction calendar (treasury_auctions_raw.json fetch)": auction_calendar_fetch_date()}


def part_a_source():
    """Exactly the source's run: tvnt1_triage.load() (cut 2025-06-30), tvnt2_triage.load_auctions, early_sessions."""
    T1, T2 = _imp_auction()
    _, C, _ = T1.load()
    ev, info = T2.load_auctions(C.index)
    early = T2.early_sessions(C.index)
    return C, ev, early, info


def part_a_forward(since, ends):
    _, T2 = _imp_auction()
    C = load_fund_closes_fwd()
    last = min(pd.Timestamp(ends["IEF close (research cache nonequity_close.csv)"]),
               pd.Timestamp(ends["TLT close (yahoo_adj 1d master)"]))
    C = C[C.index <= last]
    old_cut = T2.CUT
    try:
        T2.CUT = pd.Timestamp("2262-01-01")       # load_auctions cuts at the module CUT; forward reads every auction held
        ev, _ = T2.load_auctions(C.index)
    finally:
        T2.CUT = old_cut
    early = T2.early_sessions(C.index)
    tr = auction_trades(C, ev, early)
    cal = int(np.searchsorted(C.index.values, np.datetime64(auction_calendar_fetch_date()), side="right")) - 1
    ok = np.array([auction_settled(int(j), len(C), cal) for j in tr.j])
    fwd = tr[(tr.entry > pd.Timestamp(since)) & ok].copy()
    pending = int(((tr.entry > pd.Timestamp(since)) & ~ok).sum())
    daily = {}
    for _, r in fwd.iterrows():
        for d, v in auction_trade_daily(C, r).items():
            daily[d] = daily.get(d, 0.0) + float(v)
    fwd["detail"] = ""
    return fwd, pd.Series(daily, dtype=float).sort_index(), dict(pending=pending)


# ================================================================================================ part B - MONTH-END ES
def monthend_trades(R, DD, cost):
    T = R.run(DD, ES_MULT, K_ME, TH_ME, 0, cost)
    return pd.DataFrame(dict(part="B", instrument="ES", entry=T.entry, exit=T.exit, side=T.side, pnl=T.usd.astype(float),
                             detail=["spread %+.4f" % s for s in T.spread]))


def monthend_trade_daily(DD, T, cost, mult=ES_MULT):
    """COPIED from tools/rocfrontier/rebal_book.py leg_daily() (its loop body, verbatim; not importable: that module runs its
    book study at import). The trade table T is passed in instead of calling run() again."""
    c = DD.c; gap = DD.o - DD.c.shift(1); seam = DD.seam; dates = DD.index
    s = pd.Series(0.0, index=dates)
    for _, t in T.iterrows():
        di = dates.get_loc(t.entry); xi = dates.get_loc(t.exit)
        s.iloc[di] -= cost * mult                              # cost booked at entry
        for j in range(di + 1, xi + 1):
            ch = c.iloc[j] - c.iloc[j - 1]
            if seam.iloc[j]: ch -= gap.iloc[j]; s.iloc[j] -= cost * mult
            s.iloc[j] += t.side * ch * mult
    return s[s != 0]


def es_daily_from_master(date_to=None):
    """COPIED from tools/rocfrontier/make_daily.py (its per-instrument body, ES only, returned instead of written). Since
    2026-10-08 detect_roll_seams IS augur_engine.rolls.seam_days (ONDRIFT_1_0 imports it under that name), which needs the
    engine's roll context around the call - added here, nothing else changed."""
    find_master, load_master_arrays = _data()
    from augur_engine.rolls import roll_context, seam_days as detect_roll_seams
    A = load_master_arrays(find_master("ES", "5m", "rth", "db_noadj_rth"), date_from="2009-06-01", date_to=date_to)
    df = pd.DataFrame({"o": A["open"], "h": A["high"], "l": A["low"], "c": A["close"], "v": A["volume"]}, index=A["index"])
    df["d"] = df.index.tz_localize(None).normalize()
    D = df.groupby("d").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"), n=("o", "size"))
    with roll_context("ES", A["index"], 300):
        seams = detect_roll_seams(D["o"].values, D["c"].values, list(D.index))
    D["seam"] = False
    D.iloc[seams, D.columns.get_loc("seam")] = True
    return D


def part_b_ends():
    return {"SPY close (yahoo_adj 1d master)": _day(master_last_bar("SPY", "1d", "rth", "yahoo_adj")),
            "TLT close (yahoo_adj 1d master)": _day(master_last_bar("TLT", "1d", "rth", "yahoo_adj")),
            "ES 5m RTH (db_noadj_rth master)": _day(master_last_bar("ES", "5m", "rth", "db_noadj_rth"))}


def part_b_forward(since, ends):
    R = _imp_rebal()
    DD = es_daily_from_master()
    keep = complete_months(DD.index, min(pd.Timestamp(v) for v in ends.values()))
    DD = DD.loc[keep]
    T = monthend_trades(R, DD, ES_COST_PREREG)
    fwd = T[T.entry > pd.Timestamp(since)].copy()
    daily = monthend_trade_daily(DD, fwd, ES_COST_PREREG) if len(fwd) else pd.Series(dtype=float)
    return fwd, daily, dict(pending=0, months_through=str(keep[-1].date()) if len(keep) else None)


# ================================================================================================ part C - 08:30 FADE NQ
def nt1_rows(mk=NQ_MKT, source="db_adj_eth"):
    """COPIED from tools/orb_nt1_macro830.py main() (the per-market trade loop, verbatim; main() builds the rows inline and
    returns nothing). Same master (1m ETH db_adj_eth), same calendar files, same window."""
    NC, NT1 = _imp_nt1()
    find_master, load_master_arrays = _data()
    mult, cost = NT1.MKT[mk]
    STRESS = NT1.STRESS
    days = sorted(set(pd.read_csv(os.path.join(SHARED, "tools/data/cpi_dates.csv"), comment="#").date)
                  | set(pd.read_csv(os.path.join(SHARED, "tools/data/nfp_dates.csv"), comment="#").date))
    days = [pd.Timestamp(d) for d in days if "2010-06-07" <= d <= NC.WF[1]]
    A = load_master_arrays(find_master(mk, "1m", "eth", source), date_from="2010-06-01", date_to=NC.WF[1])
    idx = pd.DatetimeIndex(A["index"])
    o = pd.Series(np.asarray(A["open"], float), index=idx)
    c = pd.Series(np.asarray(A["close"], float), index=idx)
    out, skipped = [], 0
    for d in days:
        ts = lambda hm: pd.Timestamp("%s %s" % (d.date(), hm), tz=idx.tz)
        try:
            c0, c1, en, ex = c[ts("08:29")], c[ts("08:34")], o[ts("08:35")], c[ts("09:59")]
        except KeyError:
            skipped += 1
            continue
        m = c1 - c0                                  # points
        if m == 0:
            skipped += 1
            continue
        g = (ex - en) * mult
        side = 1.0 if m > 0 else -1.0
        out.append(dict(date=d, m=m, g=g, side=side, usd=side * g - cost * mult,
                        usd_stress=side * g - (cost + STRESS) * mult, cost=cost * mult))
    T = pd.DataFrame(out).sort_values("date").reset_index(drop=True)
    return T, skipped, (o, c)


def fade_trades_from_rows(T):
    """The source's reported fade mirror: f = -side x g - cost (orb_nt1_macro830.main, last loop)."""
    f = -T.side * T.g - T.cost
    return pd.DataFrame(dict(part="C", instrument=NQ_MKT, entry=T.date, exit=T.date, side=-T.side, pnl=f.astype(float),
                             detail=["m %+.2f pt" % x for x in T.m]))


def part_c_ends():
    return {"NQ 1m ETH (db_noadj_eth master)": _day(master_last_bar("NQ", "1m", "eth", "db_noadj_eth"))}


def load_skips(out_dir):
    p = os.path.join(out_dir, "forward_skips.csv")
    if os.path.exists(p):
        return pd.read_csv(p, parse_dates=["day"])
    return pd.DataFrame(columns=["part", "day", "reason", "first_seen"])


def part_c_forward(since, ends, out_dir, today):
    _, NT1 = _imp_nt1()
    find_master, load_master_arrays = _data()
    mult, cost = NT1.MKT[NQ_MKT]
    bls = parse_bls()
    cal_end = bls.date.max()
    days = [d for d in release_days(bls) if pd.Timestamp(since) < d <= pd.Timestamp(today)]
    upcoming = [d for d in release_days(bls) if d > max(pd.Timestamp(since), pd.Timestamp(today))]
    last_bar = master_last_bar("NQ", "1m", "eth", "db_noadj_eth")
    notes = []
    if cal_end < pd.Timestamp(today):
        notes.append("LOGGED: bls_dates.txt ends %s - part C does not trade after it until the next schedule is added"
                     % cal_end.date())
    start = (pd.Timestamp(since) - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    A = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), date_from=start)
    idx = pd.DatetimeIndex(A["index"])
    o = pd.Series(np.asarray(A["open"], float), index=idx)
    c = pd.Series(np.asarray(A["close"], float), index=idx)
    prior = load_skips(out_dir)
    prior_c = set(pd.to_datetime(prior[prior.part == "C"].day)) if len(prior) else set()
    rows, new_skips, pending = [], [], 0
    for d in days:
        if pd.Timestamp("%s 10:00" % d.date(), tz="US/Eastern") > last_bar:
            pending += 1                                   # the master has not reached this day's exit yet
            continue
        if d in prior_c:
            continue                                       # skipped once = skipped for good
        r, why = fade_day(o, c, d, mult, cost)
        if r is None:
            new_skips.append(dict(part="C", day=d, reason=why, first_seen=str(pd.Timestamp(today).date())))
            continue
        rows.append(dict(part="C", instrument=NQ_MKT, entry=d, exit=d, side=r["side"], pnl=r["pnl"],
                         detail="m %+.5f entry %.2f exit %.2f" % (r["m"], r["entry_px"], r["exit_px"])))
    fwd = pd.DataFrame(rows, columns=["part", "instrument", "entry", "exit", "side", "pnl", "detail"])
    daily = fwd.groupby("exit").pnl.sum() if len(fwd) else pd.Series(dtype=float)
    return fwd, daily, dict(pending=pending, new_skips=new_skips, skipped_total=len(prior_c) + len(new_skips),
                            next_release=str(upcoming[0].date()) if upcoming else None, calendar_end=str(cal_end.date()),
                            notes=notes)


# ================================================================================================ modes
def _pct(a, b):
    return 100.0 * (a - b) / abs(b) if b else float("nan")


def mode_parity():
    print("EVENT SLEEVE parity - each part rebuilt by its own source harness (WF / pre-lockbox only; no lockbox number printed)\n")
    ok_all = True
    rows = []

    # ---- A
    T1, T2 = _imp_auction()
    C, ev, early, info = part_a_source()
    d, tr = T2.auction_cell(C, ev, K_AUC, early=early)
    w = T1.judge(d, tr, *T1.WF)
    tA = auction_trades(C, ev, early)
    wfA = tA[(tA.exit >= T1.WF[0]) & (tA.exit <= T1.WF[1])]
    assert abs(wfA.pnl.sum() - sum(p for (x, p, g) in tr if T1.WF[0] <= x <= T1.WF[1])) < 1e-6
    r = REF["A"]
    okA = abs(_pct(w["net"], r["net"])) <= 1.0 and abs(_pct(w["t"], r["t"])) <= 1.0 and w["years_pos"] == r["years_pos"]
    rows.append(("A", r["label"], "net $%.0f  t %.3f  yrs+ %d/9  PF %.2f  ROC %.1f  DD $%.0f" % (
        r["net"], r["t"], r["years_pos"], r["pf"], r["roc30"], r["dd"]),
        "net $%.0f  t %.3f  yrs+ %d/9  PF %.2f  ROC %.1f  DD $%.0f  (n %d)" % (
        w["net"], w["t"], w["years_pos"], w["pf"], w["roc30"], w["dd"], w["n"]), okA))
    print("A auctions:", {k: info[k] for k in ("rows", "events", "announce_lag_days")},
          "| skipped early-close:", {f: len(ev[f]) - len(T2.keep_events(ev[f], K_AUC, early)) for f in ev})

    # ---- B
    R = _imp_rebal()
    TB = R.run(R.E, ES_MULT, K_ME, TH_ME)                       # the source's call: default cost 0.533
    pre = TB[TB.entry < "2025-06-30"]
    wb = pre.usd
    pf = wb[wb > 0].sum() / max(-wb[wb < 0].sum(), 1)
    by = pre.groupby(pre.entry.dt.year).usd.sum()
    print("B source summary line (rebal_scan.summ on the pre-lockbox rows only):")
    R.summ(pre, "ES K=5 th=0.02 +0d")
    r = REF["B"]
    okB = len(pre) == r["n"] and abs(_pct(pf, r["pf"])) <= 1.0 and "%d/%d" % ((by > 0).sum(), len(by)) == r["years"]
    rows.append(("B", r["label"], "n %d  PF %.2f  yrs+ %s" % (r["n"], r["pf"], r["years"]),
                 "n %d  PF %.2f  yrs+ %d/%d  net $%.0f" % (len(pre), pf, (by > 0).sum(), len(by), wb.sum()), okB))

    # ---- C
    NC, NT1 = _imp_nt1()
    TC, skipped, _ = nt1_rows()
    W = TC[(TC.date >= pd.Timestamp(NC.WF[0])) & (TC.date <= pd.Timestamp(NC.WF[1]))]
    f = -W.side * W.g - W.cost
    r = REF["C"]
    okC = len(W) == r["n"] and abs(_pct(f.sum(), r["net"])) <= 1.0 and abs(_pct(NC.tstat(f), r["t"])) <= 1.0
    rows.append(("C", r["label"], "n %d  net $%.0f  mean $%.0f  t %.2f" % (r["n"], r["net"], r["mean"], r["t"]),
                 "n %d  net $%.0f  mean $%.0f  t %.2f" % (len(W), f.sum(), f.mean(), NC.tstat(f)), okC))
    print("C NQ: %d release days traded 2010-06..2025-06, %d skipped (missing bars or zero move)" % (len(TC), skipped))

    print("\n%-2s %-58s | %-55s | %s" % ("", "source / ledger", "rebuilt", "match"))
    for p, lab, a, b, ok in rows:
        print("%-2s %-58s | %s\n%-2s %-58s | %-55s | %s" % (p, lab, a, "", "", b, "OK (within 1%)" if ok else "MISMATCH"))
        ok_all &= ok

    # ---- forward builders on the already-read WF stretch (does the forward code path rebuild the source's trades?)
    print("\nForward-builder checks (WF / pre-lockbox data only):")
    CF = load_fund_closes_fwd()
    CF = CF[CF.index < T1.CUT]
    same = CF.index.equals(C.index) and np.allclose(CF.values, C[["IEF", "TLT"]].values, equal_nan=True)
    print("  A forward loader cut at 2025-06-30 == the source's closes: %s" % same)
    DF = es_daily_from_master(date_to="2025-06-30")
    E0 = R.E[R.E.index <= "2025-06-30"]
    common = DF.index.intersection(E0.index)
    print("  B ES daily from the master vs the source's cached file: %d vs %d sessions, closes equal on %d, seams %d vs %d "
          "(differ on %d days - the 09-24 cache used the retired day-level seam detector; unequal closes = master filled since)" % (
              len(DF), len(E0), int((DF.c.reindex(common) == E0.c.reindex(common)).sum()), int(DF.seam.sum()), int(E0.seam.sum()),
              int((DF.seam.reindex(common) != E0.seam.reindex(common)).sum())))
    tb_f = monthend_trades(R, DF, ES_COST_SOURCE)
    tb_f = tb_f[tb_f.entry < "2025-06-30"]
    print("  B trades from the master-built frame: n %d (source %d), same entries %s, net $%.0f (source $%.0f)" % (
        len(tb_f), len(pre), list(tb_f.entry) == list(pre.entry), tb_f.pnl.sum(), wb.sum()))
    wf_bls = [d for d in release_days(parse_bls()) if pd.Timestamp(NC.WF[0]) <= d <= pd.Timestamp(NC.WF[1])]
    src_cal = _src_calendar(NC)
    find_master, load_master_arrays = _data()
    A = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), date_from=NC.WF[0], date_to=NC.WF[1])
    idx = pd.DatetimeIndex(A["index"])
    o = pd.Series(np.asarray(A["open"], float), index=idx)
    c = pd.Series(np.asarray(A["close"], float), index=idx)
    fr, fsk = [], 0
    for d in wf_bls:
        rr, why = fade_day(o, c, d, NT1.MKT[NQ_MKT][0], NT1.MKT[NQ_MKT][1])
        if rr is None:
            fsk += 1
        else:
            fr.append(rr)
    FR = pd.DataFrame(fr)
    both = FR.merge(pd.DataFrame(dict(date=W.date, src_side=-W.side.values, src_pnl=f.values)), on="date")
    print("  C forward builder on NOADJ 1m + bls_dates.txt + every-bar rule, WF: %d trades (%d skipped) vs source %d; "
          "%d common days, side agrees on %d, net $%.0f vs source $%.0f on those days" % (
              len(FR), fsk, len(W), len(both), int((both.side == both.src_side).sum()), both.pnl.sum(), both.src_pnl.sum()))
    print("  C calendars, WF: bls_dates.txt 08:30 CPI/EMP days %d vs the source's cpi+nfp csv days %d (bls only %d, csv only %d)" % (
        len(wf_bls), len(src_cal), len(set(wf_bls) - set(src_cal)), len(set(src_cal) - set(wf_bls))))
    print("\nPARITY: %s" % ("ALL THREE PARTS REPRODUCE" if ok_all else "MISMATCH - stop and report; nothing is tuned to match"))
    return ok_all


def _src_calendar(NC):
    days = sorted(set(pd.read_csv(os.path.join(SHARED, "tools/data/cpi_dates.csv"), comment="#").date)
                  | set(pd.read_csv(os.path.join(SHARED, "tools/data/nfp_dates.csv"), comment="#").date))
    return [pd.Timestamp(d) for d in days if NC.WF[0] <= d <= NC.WF[1]]


def section3_trades():
    """Each part's own WF trades, as its source builds them, with the prereg's ES cost for B."""
    C, ev, early, _ = part_a_source()
    tA = auction_trades(C, ev, early)
    R = _imp_rebal()
    tB = {cost: monthend_trades(R, R.E, cost) for cost in (ES_COST_PREREG, ES_COST_SOURCE)}
    TC, _, _ = nt1_rows()
    tC = fade_trades_from_rows(TC)
    return tA, tB, tC


def mode_constants(force=False, out_dir=OUT_DIR):
    tA, tB, tC = section3_trades()
    win = lambda t: t[in_window(t.entry, t.exit)] if len(t) else t
    sel = {"A": win(tA), "B": win(tB[ES_COST_PREREG]), "C": win(tC)}
    cost = {"A": "2 bps a side + 0.25 %/yr borrow on shorts (tvnt1_triage.bps / BORROW)",
            "B": "%.3f pt a round trip (prereg 1B) + one more per roll seam held (rebal_scan.run)" % ES_COST_PREREG,
            "C": "0.533 pt a round trip (orb_nt1_macro830.MKT['NQ'])"}
    parts = {}
    print("EVENT SLEEVE - ADDENDUM 1 constants (prereg section 3: one risk unit = $%.0f per-trade SD over %s..%s)\n" % (
        RISK_UNIT, SD_WINDOW[0].date(), SD_WINDOW[1].date()))
    for p in PARTS:
        t = sel[p]
        sd = trade_sd(t.pnl)
        parts[p] = dict(name=PART_NAME[p], source_unit=SOURCE_UNIT[p], cost=cost[p], n_trades=int(len(t)),
                        first_entry=str(pd.Timestamp(t.entry.min()).date()), last_exit=str(pd.Timestamp(t.exit.max()).date()),
                        sd_usd=round(sd, 2), scale=round(RISK_UNIT / sd, 6), trades_per_year=round(len(t) / ((SD_WINDOW[1] - SD_WINDOW[0]).days / 365.25), 1))
        print("  %s %-14s n %4d  per-trade SD $%9.2f  scale %.6f x (%s)  ~%.1f trades/yr" % (
            p, PART_NAME[p], len(t), sd, RISK_UNIT / sd, SOURCE_UNIT[p], parts[p]["trades_per_year"]))
    alt = win(tB[ES_COST_SOURCE])
    parts["B"]["sd_usd_at_source_cost_0533"] = round(trade_sd(alt.pnl), 2)
    print("    (B at the source's own 0.533 pt: n %d, SD $%.2f, scale %.6f - reported, not used)" % (
        len(alt), trade_sd(alt.pnl), RISK_UNIT / trade_sd(alt.pnl)))
    tbm = win(monthend_trades(_imp_rebal(), es_daily_from_master(date_to="2025-06-30"), ES_COST_PREREG))
    parts["B"]["sd_usd_on_todays_master"] = round(trade_sd(tbm.pnl), 2)
    print("    (B on today's ES master instead of the source's 09-24 cache: n %d, SD $%.2f - reported, not used)" % (
        len(tbm), trade_sd(tbm.pnl)))
    pooled = sum(parts[p]["trades_per_year"] for p in PARTS)
    print("    trades a year over the stretch: %s -> pooled %.1f (the prereg and the harm bar assume 55: A ~24, B ~8, C ~23)%s" % (
        ", ".join("%s %.1f" % (p, parts[p]["trades_per_year"]) for p in PARTS), pooled,
        "  ** FLAG: pooled rate differs from 55 by > 20 % - for the lane / MANAGER, not changed here" if abs(pooled / 55 - 1) > 0.2 else ""))
    thr, summ = harm_threshold()
    print("\nSection 5 harm bar: %d draws, seed %d, Sharpe ~ N(%.2f, %.2f), %d trades/yr, t3 tails, %d trades" % (
        HARM["n_draws"], HARM["seed"], HARM["sharpe_mu"], HARM["sharpe_sd"], HARM["trades_per_year"], HARM["n_trades"]))
    print("  cumulative P&L at 50 trades (risk units): mean %.3f  median %.3f  SD %.3f  p1 %.3f  p10 %.3f" % (
        summ["mean"], summ["median"], summ["sd"], summ["p1"], summ["p10"]))
    print("  CLOSE threshold (5th percentile): %.4f risk units = $%.0f at the frozen scale" % (thr, thr * RISK_UNIT))
    T1, T2 = _imp_auction()
    data = {"treasury_auctions_raw.json": sha256_file(T2.AUC_FILE),
            "nonequity_close.csv": sha256_file(os.path.join(T1.CACHE, "nonequity_close.csv")),
            "ES_daily_rth.csv (rebal_scan cache)": sha256_file(os.path.join(_imp_rebal().CACHE, "ES_daily_rth.csv"))}
    doc = dict(prereg=PREREG, addendum=1, generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               scorer="tools/event_sleeve_shadow.py", scorer_sha256_lf=sha256_lf(os.path.abspath(__file__)),
               risk_unit_usd=RISK_UNIT, sd_window=[str(SD_WINDOW[0].date()), str(SD_WINDOW[1].date())],
               sd_rule="sample SD (ddof 1) of per-trade $ over trades wholly inside the window (entry >= start, exit <= end)",
               parts=parts, harm=dict(HARM, threshold_risk_units=round(thr, 6), distribution=summ,
                                      rule="CLOSE the sleeve if cumulative forward P&L (risk units) at 50 trades < threshold"),
               data_sha256=data)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, CONSTANTS_FILE)
    if os.path.exists(path) and not force:
        with open(path) as f:
            old = json.load(f)
        same = old.get("parts") == json.loads(json.dumps(parts)) and \
            old.get("harm", {}).get("threshold_risk_units") == doc["harm"]["threshold_risk_units"]
        if not same:
            print("\nREFUSED: %s exists with different constants (frozen once written; --force only before the freeze)" % path)
            return doc
        print("\n%s exists with the same constants - left unchanged" % path)
        return doc
    with open(path, "w") as f:
        json.dump(doc, f, indent=1, default=str)
    print("\nwritten %s  (scorer LF sha256 %s)" % (path, doc["scorer_sha256_lf"]))
    return doc


def mode_forward(since, out_dir=OUT_DIR):
    since = pd.Timestamp(since)
    today = pd.Timestamp(datetime.date.today())
    path = os.path.join(out_dir, CONSTANTS_FILE)
    if not os.path.exists(path):
        raise SystemExit("REFUSED: %s missing - run `constants` first (the forward read uses the frozen scale only)" % path)
    with open(path) as f:
        consts = json.load(f)
    scale = {p: float(consts["parts"][p]["scale"]) for p in PARTS}
    print("EVENT SLEEVE forward shadow - trades ENTERED after %s, today %s, frozen scales %s (constants sha %s)\n" % (
        since.date(), today.date(), {p: round(v, 6) for p, v in scale.items()}, sha256_file(path)[:16]))
    enders = {"A": part_a_ends, "B": part_b_ends, "C": part_c_ends}
    runners = {"A": lambda e: part_a_forward(since, e), "B": lambda e: part_b_forward(since, e),
               "C": lambda e: part_c_forward(since, e, out_dir, today)}
    trades, dailies, status, new_skips = [], {}, {}, []
    for p in PARTS:
        ends = enders[p]()
        ok, why, _ = staleness(ends, today)
        if not ok:
            print("PART %s %-14s REFUSED - %s" % (p, PART_NAME[p], why))
            status[p] = dict(status="REFUSED", reason=why, ends={k: str(pd.Timestamp(v).date()) for k, v in ends.items()})
            continue
        t, d, info = runners[p](ends)
        t = t.copy()
        t["scale"] = scale[p]
        t["pnl_usd_unit_sized"] = t.pnl * scale[p]
        t["pnl_risk_units"] = t.pnl_usd_unit_sized / RISK_UNIT
        trades.append(t)
        dailies[p] = d * scale[p]
        new_skips += info.pop("new_skips", [])
        status[p] = dict(status="SCORED", reason=why, n_trades=int(len(t)), pnl_usd_unit_sized=round(float(t.pnl_usd_unit_sized.sum()), 2),
                         ends={k: str(pd.Timestamp(v).date()) for k, v in ends.items()}, **info)
        print("PART %s %-14s scored - %d trades, $%.2f unit-sized (%.3f risk units); %s%s" % (
            p, PART_NAME[p], len(t), t.pnl_usd_unit_sized.sum(), t.pnl_risk_units.sum(), why,
            "".join("; %s %s" % (k, v) for k, v in info.items() if k in ("pending", "skipped_total", "months_through", "next_release"))))
        for n in info.get("notes", []):
            print("      " + n)
    cols = ["part", "instrument", "entry", "exit", "side", "pnl", "scale", "pnl_usd_unit_sized", "pnl_risk_units", "detail"]
    T = pd.concat(trades, ignore_index=True)[cols] if trades else pd.DataFrame(columns=cols)
    T = T.rename(columns={"pnl": "pnl_usd_source_unit"}).sort_values(["entry", "part"]).reset_index(drop=True)
    D = pd.DataFrame({p: dailies.get(p, pd.Series(dtype=float)) for p in PARTS}).fillna(0.0).sort_index()
    D["total"] = D.sum(axis=1)
    D.index.name = "date"
    os.makedirs(out_dir, exist_ok=True)
    T.to_csv(os.path.join(out_dir, "forward_trades.csv"), index=False, float_format="%.6f")
    D.to_csv(os.path.join(out_dir, "forward_daily.csv"), float_format="%.6f")
    if new_skips:
        prior = load_skips(out_dir)
        sk = pd.concat([prior, pd.DataFrame(new_skips)], ignore_index=True) if len(prior) else pd.DataFrame(new_skips)
        sk.to_csv(os.path.join(out_dir, "forward_skips.csv"), index=False)
    with open(os.path.join(out_dir, "forward_status.json"), "w") as f:
        json.dump(dict(run_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), since=str(since.date()),
                       today=str(today.date()), constants_sha256=sha256_file(path), parts=status), f, indent=1, default=str)
    n = len(T)
    cum = float(T.pnl_risk_units.sum()) if n else 0.0
    print("\nSLEEVE: %d forward trades, cumulative %.3f risk units; harm read at %d trades (CLOSE below %.3f)" % (
        n, cum, HARM["n_trades"], consts["harm"]["threshold_risk_units"]))
    print("written %s (forward_trades.csv, forward_daily.csv, forward_status.json%s)" % (out_dir, ", forward_skips.csv" if new_skips else ""))
    return T, D, status


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("parity")
    c = sub.add_parser("constants")
    c.add_argument("--force", action="store_true", help="overwrite an existing addendum1_constants.json (before the freeze only)")
    f = sub.add_parser("forward")
    f.add_argument("--since", required=True, help="score trades ENTERED strictly after this date (YYYY-MM-DD)")
    a = ap.parse_args(argv)
    if a.mode == "parity":
        return 0 if mode_parity() else 2
    if a.mode == "constants":
        mode_constants(force=a.force)
        return 0
    mode_forward(a.since)
    return 0


if __name__ == "__main__":
    sys.exit(main())
