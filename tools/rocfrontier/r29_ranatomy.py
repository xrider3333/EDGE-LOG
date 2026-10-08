# R ANATOMY r1 (FRONTIER, book queue Q28) - what is LEFT in the S1 line's drawdown days R, by market state known at each day's open, and which
# of #463's legs (and the RESMOM seat) loses there. A MAP: no strategy is run, no weight is proposed, no look is added. WF only, lockbox unread.
# Pre-registered: docs/PREREG_frontier_ranatomy_2026-10-08.txt (sha below; committed and pushed before any number).
#   python r29_ranatomy.py selftest    hand-made series: the prior-close states, the 200-session mean, terciles, inversion, events, the sums
#   python r29_ranatomy.py run         the tables -> ranatomy.json (outside git)
import hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.environ.get("EDGELOG_RANATOMY_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\ranatomy_r1")
os.environ["EDGELOG_RESMOM_R1"] = OUT                                    # r17 is imported for its loaders only; anything it writes lands here
sys.path.insert(0, HERE)
import numpy as np, pandas as pd

TS = pd.Timestamp
PREREG = os.path.join(REPO, "docs", "PREREG_frontier_ranatomy_2026-10-08.txt")
PREREG_SHA = "8972ad42e9b2dda3e2dac989b41f10dabedb860526853f5353760a7747f6a57e"
PINS = {"cboe": (r"C:\EdgeLog\_research_cache\public_series\cboe_vol_daily.csv", "9790df06b649df21d34ab7cb31a5ed5e4c3c71fcda33952d1f41e431cb4e2470", False),
        "line": (r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv", "e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18", False),
        "fomc": (os.path.join(REPO, "tools", "data", "fomc_dates.txt"), "e27995e3040fd14e", True),
        "cpi": (os.path.join(REPO, "tools", "data", "cpi_dates.csv"), "f655dd989c5dcf39", True),
        "nfp": (os.path.join(REPO, "tools", "data", "nfp_dates.csv"), "e287e16ce229bcc8", True)}
WF0, WF1 = TS("2016-07-01"), TS("2025-06-29")
C_RES = 0.264
CRASH = (TS("2020-03-03"), TS("2020-03-27"))
TREND_N = 200


def sha_ok(path, want, lf):
    b = open(path, "rb").read()
    got = hashlib.sha256(b.replace(b"\r\n", b"\n") if lf else b).hexdigest()
    if not got.startswith(want):
        raise SystemExit(f"refused: {path} sha256 {got[:16]}... is not the pinned {want[:16]}... (nothing computed)")
    return got


def prereg_ok():
    got = hashlib.sha256(open(PREREG, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
    if not PREREG_SHA or got != PREREG_SHA:
        raise SystemExit(f"refused: {PREREG} reads {got[:16]}..., the registered sha is {PREREG_SHA[:16] or 'not set'} (nothing computed)")
    return got


# ------------------------------------------------------------------ the states (each known at the open of day d: built from closes strictly before d)
def prior_value(dates, series):
    """for each date in `dates`, the value of `series` (indexed by date) on its last row strictly before that date (NaN if none)"""
    s = series.dropna().sort_index()
    pos = np.searchsorted(s.index.values, pd.DatetimeIndex(dates).values, side="left") - 1
    v = np.where(pos >= 0, s.to_numpy(float)[np.maximum(pos, 0)], np.nan)
    return pd.Series(v, index=pd.DatetimeIndex(dates))


def trend_state(dates, close):
    """'up' when the prior close is above the mean of the last 200 closes up to and including it, 'down' when at or below, '' if fewer than 200"""
    c = close.dropna().sort_index()
    m = c.rolling(TREND_N, min_periods=TREND_N).mean()
    pc, pm = prior_value(dates, c), prior_value(dates, m)
    return pd.Series(np.where(pm.isna(), "", np.where(pc > pm, "up", "down")), index=pc.index)


def tercile_state(dates, level, lo, hi):
    """'low' / 'mid' / 'high' by the prior close against the two breakpoints (the WF stretch's terciles of the daily closes - stated as
    descriptive: the breakpoints use the whole stretch's distribution)"""
    p = prior_value(dates, level)
    return pd.Series(np.where(p.isna(), "", np.where(p <= lo, "low", np.where(p <= hi, "mid", "high"))), index=p.index)


def inversion_state(dates, vix, vix3m):
    r = prior_value(dates, vix / vix3m)
    return pd.Series(np.where(r.isna(), "", np.where(r >= 1.0, "inverted", "normal")), index=r.index)


def event_state(dates, sets):
    """the first matching event name (FOMC before CPI before NFP) on the day itself (scheduled, known in advance), else 'none'"""
    d = pd.DatetimeIndex(dates).normalize()
    out = np.array(["none"] * len(d), dtype=object)
    for nm in ("FOMC", "CPI", "NFP")[::-1]:
        out[np.isin(d.values, np.array(sorted(sets[nm]), dtype="datetime64[ns]"))] = nm
    return pd.Series(out, index=pd.DatetimeIndex(dates))


def table(state, mask, cols):
    """state (per day), mask (R days), cols {name: daily $} -> {class: {"R_days", "nonR_days", "R": {col: $}, "nonR": {col: $}}}"""
    out = {}
    for k in sorted(set(state)):
        sel = (state == k).to_numpy()
        out[str(k) or "(no state)"] = {"R_days": int((sel & mask).sum()), "nonR_days": int((sel & ~mask).sum()),
                                       "R": {c: float(v[sel & mask].sum()) for c, v in cols.items()},
                                       "nonR": {c: float(v[sel & ~mask].sum()) for c, v in cols.items()}}
    return out


def read_dates(path):
    rows = [l.split(",")[0].strip() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]
    return {TS(r) for r in rows if r[:2] in ("19", "20")}


# ------------------------------------------------------------------ run
def run():
    psha = prereg_ok()
    got = {k: sha_ok(*v) for k, v in PINS.items()}
    print(f"PINS: prereg LF sha256 {psha}; script sha256 {hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}; " + "; ".join(f"{k} {v[:16]}" for k, v in got.items()), flush=True)
    t0 = time.time()
    import r17_resmom as R17
    D15, M12 = R17.D15, R17.M12
    sys.path.insert(0, R17.R11.REPO if hasattr(R17, "R11") else REPO)
    from api.book_shadow import BOOK463_LEGS
    from augur_engine import book
    Ld = pd.read_csv(PINS["line"][0], parse_dates=["date"]).set_index("date").sort_index()
    idx = Ld.index
    B = Ld["book_mtm"].to_numpy(float)
    RES = Ld["RES"].to_numpy(float)
    L = B + C_RES * RES
    SL = M12.Stretch(L, idx, None, WF0, WF1)
    fl = M12.vmeas(SL.x[None, :], SL.years)
    print(f"THE S1 LINE: ROC@30k {float(fl['roc'][0]):.2f}; R {len(SL.qual)} episodes / {SL.n_dd_days} days (want 121.06, 45 / 762)", flush=True)
    if not (abs(float(fl["roc"][0]) - 121.06) <= 0.01 and len(SL.qual) == 45 and SL.n_dd_days == 762):
        raise SystemExit("PARITY STOP (nothing judged)")
    dates = SL.dates
    mask = np.asarray(SL.dd, bool)
    legs = {}
    for leg in BOOK463_LEGS:
        tr, inf = book._leg_trades(dict(leg), "2010-06-07", "2026-06-30")
        d_, v_ = book._daily(inf.pop("_mtm_day", None) or tr)
        n = leg["strategy"].split("_")[0]
        legs[n] = legs.get(n, 0.0) + pd.Series(v_, index=pd.to_datetime(d_)).groupby(level=0).sum().reindex(dates).fillna(0.0).to_numpy(float)
    cols = {"L": SL.x, **legs, "RES x 0.264": C_RES * pd.Series(RES, index=idx).reindex(dates).fillna(0.0).to_numpy(float)}
    gap = float(np.abs(sum(legs.values()) + cols["RES x 0.264"] - SL.x).max())
    assert gap <= 0.05, gap
    es, _ = D15.load_es(R17.S.LB0)
    a = es["adj"]["close"]
    esc = a.groupby(a.index.tz_convert("US/Eastern").normalize().tz_localize(None)).last()
    cb = pd.read_csv(PINS["cboe"][0], parse_dates=["date"]).set_index("date").sort_index()
    vix, v3m = cb["VIX_close"], cb["VIX3M_close"]
    wfv = vix[(vix.index >= WF0) & (vix.index <= WF1)]
    lo, hi = float(np.nanpercentile(wfv, 100 / 3)), float(np.nanpercentile(wfv, 200 / 3))
    ev = {"FOMC": read_dates(PINS["fomc"][0]), "CPI": read_dates(PINS["cpi"][0]), "NFP": read_dates(PINS["nfp"][0])}
    states = {"ES trend (prior close vs its 200-session mean)": trend_state(dates, esc),
              f"VIX level, prior close (WF terciles {lo:.1f} / {hi:.1f})": tercile_state(dates, vix, lo, hi),
              "VIX / VIX3M, prior close": inversion_state(dates, vix, v3m),
              "scheduled macro day": event_state(dates, ev)}
    keep = ~((dates >= CRASH[0]) & (dates <= CRASH[1]))
    res = {"prereg_sha256_lf": psha, "pins": got, "R_days": int(mask.sum()), "R_episodes": len(SL.qual), "vix_terciles": [lo, hi], "tables": {}}
    for nm, st in states.items():
        res["tables"][nm] = {"all": table(st, mask, cols), "without_2020-03": table(st[keep], mask[keep], {c: v[keep] for c, v in cols.items()})}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "ranatomy.json"), "w") as f:
        json.dump(res, f, indent=1)
    names = list(cols)
    for nm, t in res["tables"].items():
        print(f"\n{nm}  (R days / non-R days; $ on R by column; [without 2020-03 in brackets])")
        print("   class      " + "".join(f"{c:>14}" for c in names))
        for k, v in t["all"].items():
            w = t["without_2020-03"].get(k, {"R": {c: 0.0 for c in names}, "R_days": 0})
            print(f"   {k:<10} R {v['R_days']:>3}/{v['nonR_days']:>4} " + "".join(f"{v['R'][c]:>14,.0f}" for c in names))
            print(f"   {'':<10} [R {w['R_days']:>3}]    " + "".join(f"{w['R'][c]:>14,.0f}" for c in names))
    print(f"\nwritten {os.path.join(OUT, 'ranatomy.json')} ({time.time() - t0:.0f}s)")
    return res


# ------------------------------------------------------------------ selftest
def selftest():
    d = pd.bdate_range("2020-01-01", periods=260)
    c = pd.Series(np.r_[np.full(200, 100.0), np.linspace(101, 120, 60)], index=d)
    q = pd.DatetimeIndex([d[199], d[200], d[201], d[259]])
    t = trend_state(q, c)
    assert t.iloc[0] == "" and t.iloc[1] == "down" and t.iloc[2] == "up" and t.iloc[3] == "up", t.tolist()   # d[200]'s prior close is d[199]: 100 vs mean 100 -> down
    pv = prior_value(pd.DatetimeIndex([d[0], d[5]]), c)
    assert np.isnan(pv.iloc[0]) and pv.iloc[1] == 100.0, "strictly before the day"
    lv = pd.Series([10.0, 20.0, 30.0], index=d[:3])
    assert tercile_state(pd.DatetimeIndex([d[1], d[2], d[3]]), lv, 12.0, 25.0).tolist() == ["low", "mid", "high"]
    inv = inversion_state(pd.DatetimeIndex([d[1], d[2]]), pd.Series([20.0, 30.0], index=d[:2]), pd.Series([25.0, 25.0], index=d[:2]))
    assert inv.tolist() == ["normal", "inverted"]
    ev = event_state(pd.DatetimeIndex([d[3], d[4], d[5]]), {"FOMC": {d[3]}, "CPI": {d[3], d[4]}, "NFP": set()})
    assert ev.tolist() == ["FOMC", "CPI", "none"], ev.tolist()
    st = pd.Series(["a", "b", "a", "b"], index=d[:4])
    m = np.array([True, True, False, False])
    tb = table(st, m, {"x": np.array([1.0, 2.0, 3.0, 4.0])})
    assert tb["a"]["R"]["x"] == 1.0 and tb["a"]["nonR"]["x"] == 3.0 and tb["b"]["R_days"] == 1 and sum(v["R"]["x"] + v["nonR"]["x"] for v in tb.values()) == 10.0
    print("r29_ranatomy selftest OK (states from closes strictly before the day, the 200-session mean, terciles, inversion, event order, table sums)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    selftest()
    if cmd == "run":
        run()
