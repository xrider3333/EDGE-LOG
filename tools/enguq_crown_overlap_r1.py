"""ENGU-Q crown overlap - does crown #335 already take the owner's pullback-break shape?

THE QUESTION, AND THE NUMBER THIS TOOL REFUSES TO PRODUCE.  The owner's 11-04 shape is ES 5m;
crown #335 is NQ 1m.  A single "ES-versus-NQ overlap percentage" across two tapes would be a
fabricated number, and prereg section 6 pre-committed not to produce one.  Two separate
measurements are honest, and they are reported as two:

  A  SAME INSTRUMENT, SAME TIMEFRAME.  #335's own NQ entries, NQ resampled to 5m from the very
     master #335 ran on, against each r2 entry arm computed on that 5m frame.  This answers
     "does the crown already take this shape?" on one tape with no translation.
  B  CROSS INSTRUMENT, TIME ONLY.  How often an ES 5m pullback-break signal falls in the same
     5-minute slot as a #335 NQ entry.  Reported as CO-OCCURRENCE IN TIME and labelled as such:
     ES and NQ are ~0.9 correlated, so a high number here means the index moved, not that the
     two strategies agree.

AND A BASE RATE BESIDE EVERY OVERLAP, because a cell that fires on 8% of all bars will "cover"
about 8% of anybody's entries by chance.  Each row carries coverage, the cell's own base rate on
the same bars, and the LIFT between them.  A lift near 1.0 is coincidence, however large the
coverage looks.

#335's PARAMETERS COME FROM THE RUN, NOT THE FILE.  The file's DEFAULT_PARAMS defaults and run
#335's champion are different numbers (house rule FILE DEFAULTS != RUN), so the champion dict is
read from the stored run doc and printed in full before anything is measured.

Pre-lockbox only: the stretch ends at the same 2025-06-30 as r2, so no lockbox is read here.

    python tools/enguq_crown_overlap_r1.py --selftest
    python tools/enguq_crown_overlap_r1.py
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# A DATA-READING DRIVER RUNS AGAINST THE SHARED CHECKOUT (BACKTEST_SPEED.md).  augur_engine
# resolves augur_uploads / augur_strategies from its OWN package location, not from the working
# directory, so a worktree's engine looks for masters inside the worktree - where the gitignored
# data does not exist, and find_master quietly returns None.  When this file is run from a
# worktree, the shared checkout therefore goes to the FRONT of sys.path so the engine, the
# masters, the strategy files and the r2 primitives all come from one place.  Nothing is written
# there and nothing is committed there.
SHARED_CHECKOUT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
if not os.path.isdir(os.path.join(_ROOT, "augur_uploads")) and os.path.isdir(SHARED_CHECKOUT):
    sys.path.insert(0, SHARED_CHECKOUT)

from tools.enguq_pullback_break_r2 import (            # noqa: E402  the r2 definitions themselves
    ATR_LEN, K_TICKS, N_DRIFT, D_ATR, BODY_RATIOS, SLOPE_WINDOWS,
    atr, body_ratio, drift_run_tolerant, drift_slope, net_decline, usd,
)

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
CROWN_RUN = "335"
CROWN_FILE = "ENGUQ_1M_ETH_R2_1_0.py"
CROWN_COST = 0.533                       # the run's own stored cost, on its own noadj basis
PRE_LOCKBOX_TO = "2025-06-30"
CROWN_FROM = "2010-06-07"                # the run's own date_from
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_crown_overlap_r1"
# serviceAccount.json is gitignored and therefore absent from a worktree too, so the admin
# credential is read from the same SHARED_CHECKOUT above.  It is never copied in, never committed.


def _lift(cov, base):
    """Coverage over base rate.  None when the base rate is zero - a lift is not defined there
    and a large coverage against a zero base would otherwise print as infinity."""
    return None if not base else cov / base


# ------------------------------------------------------------------ the r2 entry arms, one frame
def entry_cells(o, h, lo, c, tsi):
    """Every r2 entry arm as a boolean mask on THIS 5m frame.

    Lifted from tools/enguq_pullback_break_r2.py main() and calling that module's own primitives,
    so the arm definitions cannot drift between the two tools.  The ONE thing deliberately left
    out is the next-bar-open fill and the exits: this tool measures where a signal FIRES, not
    what it earns.
    """
    n = len(c)
    trade_date = (tsi + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    codes, uniq = pd.factorize(trade_date)

    rth = (tsi.hour * 60 + tsi.minute >= 9 * 60 + 30) & (tsi.hour * 60 + tsi.minute <= 15 * 60 + 30)
    sma200 = pd.Series(c).rolling(200).mean().shift(1).to_numpy()
    higher_close = np.zeros(n, bool)
    higher_close[1:] = (c[1:] > c[:-1]) & (c[1:] > o[1:])
    atr20 = atr(h, lo, c, ATR_LEN)

    cells = []
    for k in K_TICKS:
        run = drift_run_tolerant(c, k)
        nd = net_decline(c, run)
        for ndrift in N_DRIFT:
            for d in D_ATR:
                for br_min in BODY_RATIOS:
                    br = body_ratio(o, h, lo, c, ndrift)
                    sig = ((run >= ndrift) & higher_close & rth
                           & ~np.isnan(sma200) & ~np.isnan(atr20) & ~np.isnan(nd)
                           & (nd >= d * atr20))
                    if br_min > 0:
                        sig &= (br >= br_min)
                    cells.append(("D1' k=%dt N>=%d d=%.1f %s"
                                  % (k, ndrift, d, "b2" if br_min else "B0"), sig))
    for w in SLOPE_WINDOWS:
        sl = drift_slope(c, w)
        for d in D_ATR:
            for br_min in BODY_RATIOS:
                br = body_ratio(o, h, lo, c, w)
                sig = (higher_close & rth & ~np.isnan(sma200) & ~np.isnan(atr20) & ~np.isnan(sl)
                       & (sl <= -(d * atr20) / w))
                if br_min > 0:
                    sig &= (br >= br_min)
                cells.append(("D2' w=%d d=%.1f %s" % (w, d, "b2" if br_min else "B0"), sig))
    del codes, uniq
    return cells, rth


# ------------------------------------------------------------------ 1m -> 5m, one tape
def to_5m(df):
    """5-minute bars from a 1-minute frame, clock-aligned, left-labelled.

    Resampled from the SAME master #335 ran on rather than loaded from a separate 5m master, so
    the crown's entries and the arm signals cannot disagree because two files were spliced
    differently.  Empty bins (the ETH maintenance break, holidays) are dropped, not forward
    filled - a bar that did not trade must not become a signal bar.
    """
    g = df.set_index("ts").resample("5min", label="left", closed="left")
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(),
                        "low": g["low"].min(), "close": g["close"].last(),
                        "bars": g["close"].count()})
    out = out[out["bars"] > 0].drop(columns="bars")
    return out.reset_index()


def slot_5m(ts):
    """The clock-aligned 5-minute slot a timestamp falls in - the join key for both measurements."""
    return pd.DatetimeIndex(ts).floor("5min")


# ------------------------------------------------------------------ selftest
def selftest():
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  MISMATCH: " + name)

    ts = pd.date_range("2024-03-01 09:30", periods=20, freq="1min", tz="America/New_York")
    df = pd.DataFrame({"ts": ts, "open": np.arange(20, dtype=float),
                       "high": np.arange(20, dtype=float) + 1,
                       "low": np.arange(20, dtype=float) - 1,
                       "close": np.arange(20, dtype=float) + 0.5})
    f = to_5m(df)
    chk("20 one-minute bars make 4 five-minute bars", len(f) == 4)
    chk("the 5m open is the FIRST minute's open", f["open"].iloc[0] == 0.0)
    chk("the 5m close is the LAST minute's close", f["close"].iloc[0] == 4.5)
    chk("the 5m high is the max of the five", f["high"].iloc[0] == 5.0)
    chk("the 5m low is the min of the five", f["low"].iloc[0] == -1.0)
    chk("the label is the bin's LEFT edge", f["ts"].iloc[0] == ts[0])

    df2 = pd.concat([df.iloc[:5], df.iloc[15:]], ignore_index=True)
    f2 = to_5m(df2)
    chk("an empty 5-minute bin is DROPPED, never forward filled", len(f2) == 2)

    chk("the slot key floors to the 5-minute boundary",
        slot_5m([pd.Timestamp("2024-03-01 09:33", tz="America/New_York")])[0]
        == pd.Timestamp("2024-03-01 09:30", tz="America/New_York"))

    chk("a cell that fires on every bar has lift 1.0", abs(_lift(1.0, 1.0) - 1.0) < 1e-12)
    chk("coverage with a zero base rate has NO lift", _lift(0.3, 0.0) is None)
    chk("lift is coverage over base rate", abs(_lift(0.20, 0.05) - 4.0) < 1e-12)

    # the arms must actually fire on a synthetic pullback-then-break, and must NOT fire
    # outside RTH - the two mistakes that would make every overlap number meaningless
    n = 600
    tsx = pd.date_range("2024-03-01 09:30", periods=n, freq="5min", tz="America/New_York")
    c = np.concatenate([np.linspace(100.0, 120.0, n - 40), np.linspace(120.0, 112.0, 30),
                        np.linspace(112.5, 118.0, 10)])
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + 0.5
    lo_ = np.minimum(o, c) - 0.5
    cells, rth = entry_cells(o, h, lo_, c, pd.DatetimeIndex(tsx))
    # 54 arms are BUILT; r2 REPORTED 53 of them, because one cell fell under the
    # 50-trades-a-year floor on the ES tape.  The floor is a reporting gate, not part of
    # an arm's definition, so it is not applied here - this tool measures where signals
    # fire, and a thin arm's overlap is still a fact about the arm.
    chk("54 entry arms are built (r2 reported 53 after its trade-count floor)",
        len(cells) == 54)
    chk("no arm fires outside RTH", all(not (sig & ~rth).any() for _, sig in cells))
    chk("at least one arm fires on a pullback-then-break", any(sig.any() for _, sig in cells))

    print("selftest: %d checks PASS, %d MISMATCH" % (ok, fail))
    return 0 if fail == 0 else 1


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    os.makedirs(OUT, exist_ok=True)
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        cert = "serviceAccount.json"
        if not os.path.exists(cert):
            cert = os.path.join(SHARED_CHECKOUT, "serviceAccount.json")
        firebase_admin.initialize_app(credentials.Certificate(cert))
    db = firestore.client()
    run = db.collection("users").document(UID).collection("runs").document(CROWN_RUN).get()
    if not run.exists:
        print("run #%s not in the store - cannot pin the crown's parameters" % CROWN_RUN)
        return 2
    rd = run.to_dict()
    champ = rd["best_params"]
    print("CROWN #%s  file %s  basis %s  cost %s" % (CROWN_RUN, rd.get("strategy"),
                                                     rd.get("data_source"), rd.get("cost_pts")))
    print("  run window %s .. %s   stored trades %s" % (rd.get("date_from"), rd.get("date_to"),
                                                        rd.get("best_trades")))
    print("  CHAMPION PARAMS, read from the run doc, NOT the file's defaults:")
    print("  " + json.dumps(champ, sort_keys=True))
    print("  stretch here: %s .. %s  (pre-lockbox, the same cut r2 used)"
          % (CROWN_FROM, PRE_LOCKBOX_TO))

    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest

    m = find_master("NQ", "1m", "eth", rd.get("data_source"))
    print("\nNQ master %s" % m["filename"])
    arrays = load_master_arrays(m, CROWN_FROM, PRE_LOCKBOX_TO)
    out = run_backtest(CROWN_FILE, arrays=arrays, params=champ, cost_pts=CROWN_COST,
                       return_trades=True)
    trades = out.get("trades") or []
    print("#335 entries on the pre-lockbox stretch: %s" % usd(len(trades)))
    if not trades:
        print("no crown entries - nothing to overlap")
        return 2

    nq1 = pd.DataFrame({"ts": pd.DatetimeIndex(arrays["index"]),
                        "open": arrays["open"], "high": arrays["high"],
                        "low": arrays["low"], "close": arrays["close"]})
    if nq1["ts"].dt.tz is None:
        nq1["ts"] = nq1["ts"].dt.tz_localize("America/New_York")
    ent_bar = np.array([int(t[0]) for t in trades], int)
    ent_bar = ent_bar[(ent_bar >= 0) & (ent_bar < len(nq1))]
    ent_slot = pd.DatetimeIndex(sorted(set(slot_5m(nq1["ts"].to_numpy()[ent_bar]))))
    print("  they fall in %s distinct 5-minute slots" % usd(len(ent_slot)))

    nq5 = to_5m(nq1)
    print("NQ resampled to 5m from that same master: %s bars" % usd(len(nq5)))
    tsi5 = pd.DatetimeIndex(nq5["ts"])
    cells_nq, rth5 = entry_cells(nq5["open"].to_numpy(float), nq5["high"].to_numpy(float),
                                 nq5["low"].to_numpy(float), nq5["close"].to_numpy(float), tsi5)

    # The base rate is measured on the bars an r2 arm could fire on at all: RTH 5m bars, which is
    # the window every arm is restricted to.  The crown trades 24 hours, so its out-of-RTH entries
    # are reported and then excluded from the denominator rather than counted as misses.
    on_rth = pd.DatetimeIndex(tsi5[rth5])
    ent_in_rth = ent_slot.intersection(on_rth)
    print("  of those, %s are RTH 5m slots (every r2 arm is RTH only; the crown trades 24h)"
          % usd(len(ent_in_rth)))
    denom = len(ent_in_rth)
    base_denom = int(rth5.sum())

    rows = []
    print("\nA. SAME INSTRUMENT, SAME TIMEFRAME - #335's own NQ entries vs each r2 arm on NQ 5m")
    print("   cover %% = share of the crown's RTH entry slots the arm also fires on.")
    print("   base %% = the arm's own share of all RTH 5m bars.  LIFT near 1.00 is coincidence.")
    print(format("cell", "<30") + format("fires", ">8") + format("base %", ">8")
          + format("cover %", ">9") + format("lift", ">7") + format("of arm %", ">10"))
    for name, sig in cells_nq:
        sig_slot = pd.DatetimeIndex(tsi5[sig])
        both = len(sig_slot.intersection(ent_in_rth))
        base = sig.sum() / base_denom if base_denom else 0.0
        cov = both / denom if denom else 0.0
        of_arm = both / len(sig_slot) if len(sig_slot) else 0.0
        li = _lift(cov, base)
        rows.append({"cell": name, "fires": int(sig.sum()), "base_pct": round(base * 100, 3),
                     "cover_pct": round(cov * 100, 3), "lift": None if li is None else round(li, 2),
                     "of_arm_pct": round(of_arm * 100, 3), "both": both})
        print(format(name, "<30") + format(usd(sig.sum()), ">8")
              + format(format(base * 100, ".2f"), ">8")
              + format(format(cov * 100, ".2f"), ">9")
              + format("-" if li is None else format(li, ".2f"), ">7")
              + format(format(of_arm * 100, ".2f"), ">10"))

    # ---------------------------------------------------------- B. co-occurrence in TIME only
    from tools.enguq_pullback_break_r2 import load_es
    es, es_rows = load_es()
    es = es[(es["ts"] <= pd.Timestamp(PRE_LOCKBOX_TO + " 18:00", tz="America/New_York"))
            & (es["ts"] >= pd.Timestamp(CROWN_FROM + " 00:00", tz="America/New_York"))]
    tsi_es = pd.DatetimeIndex(es["ts"])
    cells_es, _ = entry_cells(es["open"].to_numpy(float), es["high"].to_numpy(float),
                              es["low"].to_numpy(float), es["close"].to_numpy(float), tsi_es)
    print("\nB. CROSS INSTRUMENT, TIME ONLY - this is CO-OCCURRENCE IN TIME, NOT agreement.")
    print("   ES and NQ are ~0.9 correlated: a high number here means THE INDEX MOVED.")
    print(format("cell", "<30") + format("ES fires", ">10") + format("same slot", ">11")
          + format("of ES %", ">9") + format("of #335 %", ">11"))
    co = []
    for name, sig in cells_es:
        sl = pd.DatetimeIndex(tsi_es[sig])
        both = len(sl.intersection(ent_slot))
        a_ = both / len(sl) if len(sl) else 0.0
        b_ = both / len(ent_slot) if len(ent_slot) else 0.0
        co.append({"cell": name, "es_fires": int(sig.sum()), "same_slot": both,
                   "of_es_pct": round(a_ * 100, 3), "of_crown_pct": round(b_ * 100, 3)})
        print(format(name, "<30") + format(usd(sig.sum()), ">10") + format(usd(both), ">11")
              + format(format(a_ * 100, ".2f"), ">9") + format(format(b_ * 100, ".2f"), ">11"))

    doc = {"crown_run": CROWN_RUN, "champion": champ, "basis": rd.get("data_source"),
           "stretch": [CROWN_FROM, PRE_LOCKBOX_TO],
           "crown_entries": len(trades), "crown_slots": len(ent_slot),
           "crown_slots_rth": denom, "nq_5m_bars": len(nq5), "nq_5m_rth_bars": base_denom,
           "es_bars": int(len(es)),
           "same_instrument": rows, "co_occurrence_time_only": co}
    p = os.path.join(OUT, "overlap.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("\nwrote " + p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
