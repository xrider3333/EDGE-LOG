"""w121 TRAPFADE power gate, NQ 5m RTH db_noadj_rth, preWF 2010-06-07..2016-06-29, 1 contract.
Level = opening range 09:30-10:00 high/low. 10:00-12:30 ET: a bar trades past the level (poke), and within N=3 bars
(poke bar included) a bar CLOSES back inside -> fade at the next open. Stop = poke extreme (+1 tick), R = |entry-stop|.
One trade per session (first trap). Exits: HOLD = stop or session close; OPP = stop, the opposite OR side (limit, through
by a tick), or close. Random control (after-signal only): same session, same side, entry at a random bar AFTER the signal
bar up to 12:30, stop at the same R distance, same exits; 200 draws.
"""
import numpy as np
import pandas as pd
from augur_engine.data import find_master, load_master_arrays

N, COST, CO, PV, TICK = 3, 0.783, 0.283, 20.0, 0.25
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2016-06-29")
ix = pd.DatetimeIndex(A["index"]).tz_convert("America/New_York").tz_localize(None)
O, H, L, C = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
T_ = np.array(ix.strftime("%H:%M")); D = ix.normalize().values
st = np.r_[0, np.flatnonzero(D[1:] != D[:-1]) + 1]; en = np.r_[st[1:], len(D)]


def run(e, i1, side, R, opp, arm):
    ep = O[e]; stop = ep - side * R
    for b in range(e, i1):
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            px = stop if (side > 0 and O[b] > stop) or (side < 0 and O[b] < stop) else O[b]
            return side * (px - ep)
        if arm == "OPP" and ((side > 0 and H[b] >= opp + TICK) or (side < 0 and L[b] <= opp - TICK)):
            return side * (opp - ep)
    return side * (C[i1 - 1] - ep)


sig = []
for i0, i1 in zip(st, en):
    orb = np.flatnonzero(T_[i0:i1] < "10:00") + i0
    if len(orb) < 5:
        continue
    hi, lo = H[orb].max(), L[orb].min()
    w = [b for b in range(orb[-1] + 1, i1 - 1) if T_[b] <= "12:30"]
    for b in w:
        for side, poke in ((-1, H[b] > hi), (1, L[b] < lo)):
            if not poke:
                continue
            for k in range(b, min(b + N, i1 - 1)):
                back = C[k] < hi if side < 0 else C[k] > lo
                if back:
                    ext = (H[b:k + 1].max() + TICK) if side < 0 else (L[b:k + 1].min() - TICK)
                    e = k + 1; R = abs(O[e] - ext)
                    if R > 0 and (side < 0 and O[e] < ext or side > 0 and O[e] > ext):
                        sig.append((D[i0], side, e, i1, R, lo if side < 0 else hi, k))
                    break
            break
        if sig and sig[-1][0] == D[i0]:
            break
yrs = (pd.Timestamp("2016-06-29") - pd.Timestamp("2010-06-07")).days / 365.25
rs = np.random.default_rng(3)
print("signals %d (%.0f/yr), short %d long %d" % (len(sig), len(sig) / yrs, sum(s[1] < 0 for s in sig), sum(s[1] > 0 for s in sig)))
for arm in ("HOLD", "OPP"):
    g = np.array([run(e, i1, sd, R, opp, arm) for _, sd, e, i1, R, opp, _k in sig]); Rs = np.array([s[4] for s in sig])
    ctl = []
    for _ in range(200):
        gg = []
        for _, sd, e, i1, R, opp, k in sig:
            cand = [b for b in range(e + 1, i1 - 1) if T_[b] <= "12:30"]
            if cand:
                gg.append(run(rs.choice(cand), i1, sd, R, opp, arm))
        ctl.append(np.mean(gg))
    ctl = np.array(ctl)
    print("%s: gross %.3f pts/tr, gross/cost %.2f, win %.1f%%, mean R %.1f pts | after-signal random %.3f +/- %.3f, signal pctile %.0f%%" % (
        arm, g.mean(), g.mean() / COST, 100 * (g > 0).mean(), Rs.mean(), ctl.mean(), ctl.std(), 100 * (ctl < g.mean()).mean()))
    for c in (COST, CO):
        net = g - c; evr = (net / Rs).mean()
        dly = pd.Series(net * PV, index=pd.DatetimeIndex([s[0] for s in sig])).groupby(level=0).sum()
        yr = dly.groupby(dly.index.year).sum(); nb = len(dly) // 10
        blk = dly.values[: nb * 10].reshape(nb, 10).sum(1); se = np.std([rs.choice(blk, nb).sum() for _ in range(2000)]) / yrs
        print("   cost %.3f: net $%.0f/yr, t %.2f, EV R %.3f, years+ %d/%d" % (c, dly.sum() / yrs, dly.sum() / yrs / se, evr, (yr > 0).sum(), len(yr)))
