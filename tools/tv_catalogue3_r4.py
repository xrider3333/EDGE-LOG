# TV CATALOGUE 3 r4 (MANAGER #189, prereg C:/EdgeLog/manager/prereg/PREREG_tv_catalogue3_r4_2026-11-06.md). PRE-WF rows only.
# Our reading of three public script descriptions, not the Pine source.
import json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import superscalper_validate_read as R
import superscalper_regime_r3 as S

OUT = r"C:\EdgeLog\_research_cache\tv_scalp\catalogue3_r4.json"
TICK, SLIP, CUT = 0.25, 0.25, "2016-06-30"


def load(tf):
    from augur_engine.data import find_master, load_master_arrays
    m = find_master("NQ", tf, "rth", "db_noadj_rth")
    a = load_master_arrays(m, date_from="2010-06-06", date_to=CUT)
    dd = R.bar_dates(a["index"])
    day = np.asarray(dd.codes if hasattr(dd, "codes") else a["day_id"])
    o, h, l, c, v = (np.asarray(a[k], float) for k in ("open", "high", "low", "close", "volume"))
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    cal = pd.to_datetime(pd.Series(dd.uniq))
    return dict(o=o, h=h, l=l, c=c, v=v, day=day, dd=dd, atr=atr, cal=pd.DatetimeIndex(cal[cal.dt.dayofweek < 5]), master=m.get("filename"))


def vwap_signals(D, kind):
    h, l, c, v, day = (D[k] for k in ("h", "l", "c", "v", "day"))
    g = pd.Series(day)
    tp = (h + l + c) / 3
    vw = (pd.Series(tp * v).groupby(g).cumsum() / pd.Series(v).groupby(g).cumsum()).to_numpy()
    sdv = pd.Series(c).rolling(20).std(ddof=0).to_numpy()
    up, dn = vw + 2 * sdv, vw - 2 * sdv
    p = np.roll(c, 1)
    xo = lambda y: (c > y) & (p <= np.roll(y, 1))
    xu = lambda y: (c < y) & (p >= np.roll(y, 1))
    if kind == "MR":
        s = xo(dn) * 1 - xu(up) * 1
    elif kind == "TF":
        s = xo(up) * 1 - xu(dn) * 1
    else:
        s = xo(vw) * 1 - xu(vw) * 1
    s[np.r_[True, day[1:] != day[:-1]]] = 0
    return s.astype(int)


def pivot_signals(D):
    h, l, c = D["h"], D["l"], D["c"]
    n, s, ph, pl = len(c), np.zeros(len(c), int), np.nan, np.nan
    for i in range(7, n):
        j = i - 3
        if h[j] == h[j - 3:i + 1].max():
            ph = h[j]
        if l[j] == l[j - 3:i + 1].min():
            pl = l[j]
        if ph == ph and c[i] > ph and c[i - 1] <= ph:
            s[i] = 1
        elif pl == pl and c[i] < pl and c[i - 1] >= pl:
            s[i] = -1
    return s


def orb_signals(D, nbars=3):
    o, h, l, c, day = (D[k] for k in ("o", "h", "l", "c", "day"))
    s, sl = np.zeros(len(c), int), np.full(len(c), np.nan)
    start = np.r_[0, np.flatnonzero(day[1:] != day[:-1]) + 1, len(c)]
    for a, b in zip(start[:-1], start[1:]):
        if b - a <= nbars:
            continue
        hi, lo = h[a:a + nbars].max(), l[a:a + nbars].min()
        for i in range(a + nbars, b - 1):
            if min(o[i], c[i]) > hi:
                s[i], sl[i] = 1, l[i]
                break
            if max(o[i], c[i]) < lo:
                s[i], sl[i] = -1, h[i]
                break
    return s, sl


def walk(D, sig, arm, stop_of, reverse=False):
    o, h, l, c, day, dd = (D[k] for k in ("o", "h", "l", "c", "day", "dd"))
    n, i, out = len(c), 20, []
    while i < n - 1:
        sd = sig[i]
        if not sd or day[i + 1] != day[i]:
            i += 1
            continue
        e = i + 1
        if arm == "L":
            lim = c[i]
            if not (l[e] <= lim - TICK if sd > 0 else h[e] >= lim + TICK):
                i += 1
                continue
            fill, slips = (min(o[e], lim) if sd > 0 else max(o[e], lim)), 0
        else:
            fill, slips = o[e], 1
        st, tg = stop_of(i, sd, fill)
        if st is None:
            i += 1
            continue
        j, nxt = e, None
        while True:
            if j > e and ((o[j] <= st) if sd > 0 else (o[j] >= st)):
                xp, sl_ = o[j], 1
                break
            if (l[j] <= st) if sd > 0 else (h[j] >= st):
                xp, sl_ = st, 1
                break
            if (h[j] >= tg + TICK) if sd > 0 else (l[j] <= tg - TICK):
                xp, sl_ = tg, 0
                break
            if j + 1 >= n or day[j + 1] != day[e]:
                xp, sl_ = c[j], 1
                break
            if reverse and sig[j] == -sd:
                xp, sl_, nxt = o[j + 1], 1, j
                j += 1
                break
            j += 1
        out.append(dict(xday=dd[j], gross=float((xp - fill) * sd), slip=SLIP * (slips + sl_)))
        i = nxt if nxt is not None else max(j, i + 1)
    return pd.DataFrame(out)


def read(g, cal):
    g["xday"] = pd.to_datetime(g.xday)
    yrs = (cal[-1] - cal[0]).days / 365.25
    res = dict(trades_yr=round(len(g) / yrs, 1), gross_pt=round(float(g.gross.mean()), 3), power=bool(len(g) / yrs >= 50))
    edges = pd.date_range(cal[0], cal[-1] + pd.Timedelta(days=1), periods=9)
    for name, cost, extra in (("house", 0.783, 0), ("comm", 0.283, 0), ("real", 0.283, 1)):
        p = pd.DataFrame(dict(xday=g.xday, pts=g.gross - extra * g.slip - S.RUN_COST))
        rw = S.row(p, cal, cost, "pre-WF")
        net = (p.pts + S.RUN_COST - cost) * S.MULT
        rw["folds"] = [round(float(net[(p.xday >= edges[i]) & (p.xday < edges[i + 1])].sum())) for i in range(8)]
        rw["folds_pos"] = sum(f > 0 for f in rw["folds"])
        res[name] = rw
    f, r = res["real"]["four"], res["real"]
    res["clears"] = bool(res["power"] and g.gross.mean() - (0.283 + g.slip.mean()) >= 0 and f["roc30"] > 0 and not f["one_episode"]
                         and r["folds_pos"] >= 5 and (r["top5_share"] or 9) < 0.5)
    return res


def main():
    D5, D1 = load("5m"), load("1m")

    def atr_stop(D, sl, tp):
        def f(i, sd, fill):
            a = D["atr"][i]
            return (None, None) if not a > 0 else (fill - sd * sl * a, fill + sd * tp * a)
        return f
    os5, osl = orb_signals(D5)

    def orb_stop(i, sd, fill):
        r = (fill - osl[i]) * sd
        return (None, None) if r <= 0 else (osl[i], fill + sd * 6 * r)
    res = dict(masters=[D5["master"], D1["master"]])
    cells = [("VWAP_BAND_MR", D5, vwap_signals(D5, "MR"), atr_stop(D5, 1, 2), False), ("VWAP_BAND_TF", D5, vwap_signals(D5, "TF"), atr_stop(D5, 1, 2), False),
             ("VWAP_BAND_VC", D5, vwap_signals(D5, "VC"), atr_stop(D5, 1, 2), False), ("PIVOT_BREAK_1M", D1, pivot_signals(D1), atr_stop(D1, 1, 9), True),
             ("OPEN930_BODY", D5, os5, orb_stop, False)]
    for name, D, sig, stop, rev in cells:
        for arm in "ML":
            k = "%s_%s" % (name, arm)
            res[k] = read(walk(D, sig, arm, stop, rev), D["cal"])
            r = res[k]
            print(name, arm, r["trades_yr"], r["gross_pt"], round(r["real"]["four"]["roc30"], 2), r["real"]["folds_pos"], r["clears"], flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print("DONE")


if __name__ == "__main__":
    main()
