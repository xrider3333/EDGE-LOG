r"""TEST 240 part B (owner 10-31, MANAGER #132) - days when ORB #314 AND NOISE #382 BOTH gave back > 50% of their MFE, and
what the NQ tape did late in those days. Descriptive, not a verdict: each late-day trait is printed beside its base rate on
every other day both legs traded.

Trades: the two WF chains as test 238 rebuilt them (tools/orb_t74_giveback.chain, tools/noise_t74_giveback.chain), NQ 5m RTH
db_noadj_rth, both cut at their optimize ends - the lockbox is never loaded. Window: 2022-01-01 .. 2025-07-15 (NOISE's
optimize end, the later of the two chains' common end).
Giveback > 50% (fixed before computing): MFE > 0 and (MFE - final) / MFE > 0.5, final = the trade's raw points before cost.
A "both" day = each leg has at least one such trade that session.

Late-day tape (NQ 5m session, AFTER the fact - it describes the day, it is not a tradable filter):
  last_hour_ret   close - the 15:00 bar's open, as % of the 15:00 open
  last_hour_range last-hour high - low, as a share of the whole day's range
  close_vs_vwap   (close - session VWAP) / day range
  close_loc       (close - low) / (high - low)
  day_range_x     day range / mean range of the prior 20 sessions

    python tools/orb_t240_both_giveback.py   -> C:\EdgeLog\_anatomy_cache\t240_both_orb\{both_days.csv, traits.csv}
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_t74_giveback as nz  # noqa: E402
import orb_t74_giveback as ob  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t240_both_orb"
D0, D1 = pd.Timestamp("2022-01-01"), pd.Timestamp("2025-07-15")


def leg_days(mod, name):
    tr, A, idx, meta = mod.chain()
    p = mod.paths(tr, A)
    p["day"] = [idx[e].normalize() for e in p.e]
    p = p[(p.day >= D0) & (p.day <= D1)].copy()
    p["give_frac"] = np.where(p.mfe > 0, (p.mfe - p.raw) / p.mfe, np.nan)
    p["gb50"] = (p.mfe > 0) & (p.give_frac > 0.5)
    p["leg"] = name
    return p, A, idx


def tape(A, idx):
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    v = np.asarray(A.get("volume"), float) if A.get("volume") is not None else np.ones(len(c))
    df = pd.DataFrame(dict(o=o, h=h, l=l, c=c, v=v), index=idx)
    df["tp"] = (df.h + df.l + df.c) / 3
    rows = {}
    for d, g in df.groupby(df.index.normalize()):
        hi, lo, cl = g.h.max(), g.l.min(), g.c.iloc[-1]
        rng = hi - lo
        lh = g[g.index.time >= pd.Timestamp("15:00").time()]
        vw = float((g.tp * g.v).sum() / g.v.sum()) if g.v.sum() > 0 else float(g.tp.mean())
        rows[d] = dict(day_range=rng,
                       last_hour_ret=100 * (cl / lh.o.iloc[0] - 1) if len(lh) else np.nan,
                       last_hour_range=(lh.h.max() - lh.l.min()) / rng if len(lh) and rng > 0 else np.nan,
                       close_vs_vwap=(cl - vw) / rng if rng > 0 else np.nan,
                       close_loc=(cl - lo) / rng if rng > 0 else np.nan)
    t = pd.DataFrame(rows).T.sort_index()
    t["day_range_x"] = t.day_range / t.day_range.shift(1).rolling(20, min_periods=10).mean()
    return t


def main():
    os.makedirs(OUT, exist_ok=True)
    orb, A, idx = leg_days(ob, "ORB")
    noi, _, _ = leg_days(nz, "NOISE")
    T = tape(A, idx)
    both_traded = sorted(set(orb.day) & set(noi.day))
    gb = sorted(set(orb.day[orb.gb50]) & set(noi.day[noi.gb50]))
    rows = []
    for d in gb:
        for leg in (orb, noi):
            for _, r in leg[(leg.day == d) & leg.gb50].iterrows():
                rows.append(dict(day=d.date(), leg=r.leg, side="long" if r.side > 0 else "short", mfe=round(r.mfe, 2),
                                 final=round(r.raw, 2), giveback=round(r.giveback, 2), give_pct=round(100 * r.give_frac),
                                 **{k: round(float(T.at[d, k]), 3) for k in ("last_hour_ret", "last_hour_range",
                                                                               "close_vs_vwap", "close_loc", "day_range_x")}))
    B = pd.DataFrame(rows)
    B.to_csv(os.path.join(OUT, "both_days.csv"), index=False)
    keys = ["last_hour_ret", "last_hour_range", "close_vs_vwap", "close_loc", "day_range_x"]
    on, off = T.loc[gb, keys], T.loc[[d for d in both_traded if d not in set(gb)], keys]
    # signed versions: the trait measured in the ORB trade's favour (a giveback day should move AGAINST the trade late)
    od = orb.groupby("day").side.first()
    fav = lambda s, days: (s.loc[days] * od.reindex(days).to_numpy())
    tr = pd.DataFrame({"both-giveback days (n=%d)" % len(gb): on.median(),
                       "other both-traded days (n=%d)" % len(off): off.median()})
    tr.loc["last_hour_ret in ORB's direction"] = [fav(T.last_hour_ret, gb).median(), fav(T.last_hour_ret, list(off.index)).median()]
    tr.loc["close_vs_vwap in ORB's direction"] = [fav(T.close_vs_vwap, gb).median(), fav(T.close_vs_vwap, list(off.index)).median()]
    tr.to_csv(os.path.join(OUT, "traits.csv"))
    rate = lambda leg: leg.groupby("day").gb50.any()
    ro, rn = rate(orb), rate(noi)
    com = ro.index.intersection(rn.index)
    p_o, p_n = ro.loc[com].mean(), rn.loc[com].mean()
    pd.set_option("display.width", 220)
    print("window %s .. %s | days both legs traded %d | both gave back >50%%: %d (%.0f%%) | if independent: %.0f%% "
          "(ORB %.0f%% x NOISE %.0f%% of their shared days)" % (D0.date(), D1.date(), len(both_traded), len(gb),
                                                                100 * len(gb) / max(1, len(both_traded)), 100 * p_o * p_n,
                                                                100 * p_o, 100 * p_n))
    print(B.to_string(index=False))
    print(tr.round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
