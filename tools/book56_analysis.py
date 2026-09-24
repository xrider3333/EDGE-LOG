"""
BOOK ROUND 56 - ROC / YR on the FRONTIER books (2026-09-24).

Owner ask: "take a look at our frontier models on EL that we've backtested, specifically the ones
with the best ROC/yr. try to improve those."

The FRONTIER books on EL, by ROC % / YR (net per year on a $100k account - EL's own definition):
  #397 FRONTIER (ORB #297 filters + ENGU-Q #335 + squeeze combined x3 + NOISE #304)  97.4 / 306
  #372 FRONTIER PENTA                                                                 91.8 / 284
  #367 QUAD 80.1 / 234 . #363 PAIR REPAIRED 53.5 / 181 . #324 TRIO 53.0 / 158 . #323 43.3 / 136 . #317 42.1 / 133
  (pre-lockbox %/yr / lockbox %/yr). #372 trails #397 on every measure, so #397 is the book to improve.

ROC / YR SCALES WITH CONTRACTS: doubling every leg doubles it AND the drawdown. So an improvement here
means MORE ROC / YR AT THE SAME DRAWDOWN. Every candidate is reported at its own size AND scaled
(micro contracts make 0.1-contract steps tradeable) so its PRE-LOCKBOX drawdown equals #397's - that
scale is fixed on the pre-lockbox stretch only and carried unchanged into the lockbox.

PRE-REGISTERED (written before any number below was computed):

TEST A - does RE-WEIGHTING the legs beat leaving them at 1/1/3/1, FORWARD, at equal risk?
  The book-level twin of ORB_META_WF.txt (re-optimising the ORB did not pay).
  Forward blocks: July-June years, Jul 2013 .. Jun 2025 (12 blocks); the lockbox year is reported
  on its own. At each block start, using ONLY the trailing 3 years of leg dailies:
   A1 SELECT: grid ORB {0.5,1,1.5} x ENGU-Q {0.5,1,1.5} x squeeze {1..6} x NOISE {0.5,1,1.5,2}
      (216 vectors); pick the best trailing MAR; scale so its trailing daily standard deviation
      equals 1/1/3/1's; round to 0.1 contract.
   A2 INVERSE-RISK RULE (no search): weight proportional to 1 / the leg's trailing daily standard
      deviation, scaled to 1/1/3/1's trailing daily standard deviation; round to 0.1.
   A3 NULL: 500 random grid vectors per block, scaled the same way -> forward percentile of A1.
  PASS for a weighting rule: more forward net than 1/1/3/1 in >= 8 of 12 blocks AND more total
  forward net AND a forward max drawdown no worse than 1.05x; A1 must also average above the null's
  50th percentile. If nothing passes, the weights stay frozen.

TEST C - a FIFTH leg at weight 0.5 or 1: ENGU-Q R2 on ES (run #370's champion) and the NQ 15m squeeze
  break (run #280's champion); and both at weight 1. House bar (BOOK.md s10 /
  tools/book_dd_attribution.bar_text): annualised MAR >= 1.05x #397, LOCKBOX drawdown within 5%,
  lockbox net >=; whole-run drawdown reported as a check. Plus calendar years 2011-2025: dominate /
  lose count vs #397 (book55c convention: dominate = more net and no deeper in-year drawdown).

REFERENCE ONLY: #396 (ORB #234 in the ORB slot) and the NOISE slot moved to run #382 (the live Webull
NOISE leg) - another session has the #382 swap queued as book jobs, so it is read here, not queued.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

D = os.environ.get("EDGELOG_BOOK56_DIR", r"C:\EdgeLog\_anatomy_cache\book56")   # leg table written by tools/book56_leg_dailies.py
LB_FROM = pd.Timestamp("2025-06-30")
W_FROM, W_TO = pd.Timestamp("2010-06-07"), pd.Timestamp("2026-06-30")
PRE_YRS = (LB_FROM - W_FROM).days / 365.25
LB_YRS = (W_TO - LB_FROM).days / 365.25
ACCT = 100_000.0
YEARS = list(range(2011, 2026))
RNG = np.random.default_rng(56)

BASE_KEYS = ["ORB297", "ENGUQ335", "TTM369", "NOISE304"]
BASE_W = np.array([1.0, 1.0, 3.0, 1.0])
GRID = [[0.5, 1.0, 1.5], [0.5, 1.0, 1.5], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], [0.5, 1.0, 1.5, 2.0]]


# ---------------------------------------------------------------- data
def load():
    raw = pd.read_csv(os.path.join(D, "leg_dailies.csv"), index_col="date", parse_dates=True).sort_index()
    raw = raw[(raw.index >= W_FROM) & (raw.index <= W_TO)]
    # every weekday is a day the account exists; add them so a standard deviation sees the flat days
    days = pd.bdate_range(W_FROM, W_TO).union(raw.index)
    X = raw.reindex(days).fillna(0.0)
    X.index.name = "date"
    ren = {"ORB_X": "ORB297", "ENGUQ_R2": "ENGUQ335"}      # the leg builder's keys -> the runs they belong to
    X = X.rename(columns=ren)
    meta = json.load(open(os.path.join(D, "legs.json"), encoding="utf-8"))
    meta = {ren.get(k, k): v for k, v in meta.items()}
    return X, meta


# ---------------------------------------------------------------- scoring
def max_dd(v):
    """Peak-to-trough on the cumulative curve, same convention as book_dd_attribution.score."""
    v = np.asarray(v, dtype=float)
    if not len(v):
        return 0.0
    c = np.cumsum(v)
    return float(-(c - np.maximum.accumulate(c)).min())


def max_dd_cols(M):
    """Column-wise max drawdown of a (days x books) matrix."""
    c = np.cumsum(M, axis=0)
    return -(c - np.maximum.accumulate(c, axis=0)).min(axis=0)


def stats(s):
    pre = s[s.index < LB_FROM]
    lb = s[s.index >= LB_FROM]
    out = {}
    for nm, z, yrs in (("pre", pre, PRE_YRS), ("lb", lb, LB_YRS)):
        net, dd = float(z.sum()), max_dd(z.values)
        out[nm + "_net"], out[nm + "_dd"] = net, dd
        out[nm + "_roc"] = net / yrs / ACCT * 100.0
        out[nm + "_mar"] = (net / yrs) / dd if dd > 0 else float("nan")
    return out


def yearly(s):
    rows = {}
    for y in range(2010, 2027):
        z = s[(s.index >= pd.Timestamp(f"{y}-01-01")) & (s.index < pd.Timestamp(f"{y + 1}-01-01"))]
        if len(z):
            rows[y] = (float(z.sum()), max_dd(z.values))
    return rows


def dominate_lose(a, b):
    """b vs a over the full calendar years: (dominates, loses, more-net years)."""
    ya, yb = yearly(a), yearly(b)
    dom = lose = more = 0
    for y in YEARS:
        na, da = ya.get(y, (0.0, 0.0))
        nb, db = yb.get(y, (0.0, 0.0))
        dom += (nb >= na and db <= da)
        lose += (nb < na and db > da)
        more += nb > na
    return dom, lose, more


def fmt_row(label, st, base=None, scale=None):
    r = (f"{label:44} ROC/yr {st['pre_roc']:6.1f}% | LB {st['lb_roc']:6.1f}% | DD ${st['pre_dd']:>7,.0f}"
         f" LB DD ${st['lb_dd']:>7,.0f} | MAR {st['pre_mar']:5.2f} LB MAR {st['lb_mar']:6.2f}")
    if scale is not None:
        r += f" | @same DD x{scale:.2f}: ROC {st['pre_roc'] * scale:6.1f}% LB {st['lb_roc'] * scale:6.1f}%"
    return r


def bar(base_st, st):
    c1 = st["pre_mar"] >= 1.05 * base_st["pre_mar"]
    c2 = st["lb_dd"] <= 1.05 * base_st["lb_dd"]
    c3 = st["lb_net"] >= base_st["lb_net"]
    return c1, c2, c3


# ---------------------------------------------------------------- test A
def grid_vectors():
    g = np.array(np.meshgrid(*GRID, indexing="ij")).reshape(4, -1).T
    return g


def trailing_select(T, G, sd_base):
    """A1 on one trailing window: best trailing MAR vector, scaled to the base's trailing std."""
    B = T @ G.T                                       # days x vectors
    yrs = max(len(T) / 261.0, 1e-9)
    dd = max_dd_cols(B)
    mar = np.where(dd > 0, (B.sum(axis=0) / yrs) / np.where(dd > 0, dd, 1), -np.inf)
    i = int(np.argmax(mar))
    v = G[i]
    sd = float((T @ v).std())
    k = sd_base / sd if sd > 0 else 1.0
    return np.round(k * v, 1), v, float(mar[i])


def inverse_risk(T, sd_base):
    sd_i = T.std(axis=0)
    raw = np.where(sd_i > 0, 1.0 / np.where(sd_i > 0, sd_i, 1), 0.0)
    sd = float((T @ raw).std())
    k = sd_base / sd if sd > 0 else 0.0
    return np.round(k * raw, 1)


def test_a(X, out):
    L = X[BASE_KEYS]
    G = grid_vectors()
    starts = [pd.Timestamp(f"{y}-07-01") for y in range(2013, 2025)]
    ends = starts[1:] + [LB_FROM]
    blocks = list(zip(starts, ends)) + [(LB_FROM, W_TO + pd.Timedelta(days=1))]
    rows, fwd = [], {"base": [], "A1": [], "A2": []}
    pct = []
    for bi, (t0, t1) in enumerate(blocks):
        tr = L[(L.index >= t0 - pd.DateOffset(years=3)) & (L.index < t0)].values
        fw = L[(L.index >= t0) & (L.index < t1)]
        F = fw.values
        sd_base = float((tr @ BASE_W).std())
        w1, v1, m1 = trailing_select(tr, G, sd_base)
        w2 = inverse_risk(tr, sd_base)
        nb, n1, n2 = float((F @ BASE_W).sum()), float((F @ w1).sum()), float((F @ w2).sum())
        db, d1, d2 = max_dd(F @ BASE_W), max_dd(F @ w1), max_dd(F @ w2)
        # A3 null: random grid vectors, each scaled to the base's trailing std
        idx = RNG.integers(0, len(G), 500)
        R = G[idx]
        sds = (tr @ R.T).std(axis=0)
        Rk = np.round(R * (sd_base / np.where(sds > 0, sds, 1))[:, None], 1)
        null_net = (F @ Rk.T).sum(axis=0)
        p = float((null_net < n1).mean() * 100)
        is_lb = t0 == LB_FROM
        if not is_lb:
            pct.append(p)
            fwd["base"].append(F @ BASE_W)
            fwd["A1"].append(F @ w1)
            fwd["A2"].append(F @ w2)
        rows.append(dict(block=f"{t0.date()}..{(t1 - pd.Timedelta(days=1)).date()}", lb=is_lb,
                         base_net=nb, base_dd=db, a1_w=list(map(float, w1)), a1_net=n1, a1_dd=d1,
                         a2_w=list(map(float, w2)), a2_net=n2, a2_dd=d2, a1_null_pct=p,
                         null_med=float(np.median(null_net))))
    df = pd.DataFrame(rows)
    out["A_blocks"] = rows
    print("\nTEST A - re-weighting, forward, at the base's trailing risk (weights = ORB / ENGU-Q / squeeze / NOISE)")
    for r in rows:
        tag = "  <- LOCKBOX" if r["lb"] else ""
        print(f"  {r['block']}  base ${r['base_net']:>9,.0f} dd {r['base_dd']:>7,.0f} | "
              f"A1 {str(r['a1_w']):24} ${r['a1_net']:>9,.0f} dd {r['a1_dd']:>7,.0f} (null pct {r['a1_null_pct']:3.0f}) | "
              f"A2 {str(r['a2_w']):24} ${r['a2_net']:>9,.0f} dd {r['a2_dd']:>7,.0f}{tag}")
    fb = df[~df.lb]
    res = {}
    for nm, col in (("A1", "a1"), ("A2", "a2")):
        wins = int((fb[col + "_net"] > fb["base_net"]).sum())
        tot, totb = float(fb[col + "_net"].sum()), float(fb["base_net"].sum())
        cdd = max_dd(np.concatenate(fwd[nm]))
        cddb = max_dd(np.concatenate(fwd["base"]))
        passed = wins >= 8 and tot > totb and cdd <= 1.05 * cddb and (nm != "A1" or np.mean(pct) > 50)
        res[nm] = dict(wins=wins, n=len(fb), fwd_net=tot, base_fwd_net=totb, fwd_dd=cdd, base_fwd_dd=cddb,
                       mean_null_pct=float(np.mean(pct)) if nm == "A1" else None, passed=bool(passed))
        print(f"  {nm}: beats 1/1/3/1 in {wins}/{len(fb)} forward blocks | forward net ${tot:,.0f} vs ${totb:,.0f}"
              f" | forward max DD ${cdd:,.0f} vs ${cddb:,.0f}"
              + (f" | mean null percentile {np.mean(pct):.0f}" if nm == "A1" else "")
              + f"  ->  {'PASS' if passed else 'FAIL'}")
    # weights the rules would set TODAY (trailing 3 years to the end of the data)
    tr = L[L.index >= W_TO - pd.DateOffset(years=3)].values
    sd_base = float((tr @ BASE_W).std())
    res["today_A1"] = list(map(float, trailing_select(tr, G, sd_base)[0]))
    res["today_A2"] = list(map(float, inverse_risk(tr, sd_base)))
    print(f"  weights the rules would set today: A1 {res['today_A1']}  A2 {res['today_A2']}  (base [1, 1, 3, 1])")
    out["A"] = res


# ---------------------------------------------------------------- main
def main():
    X, meta = load()
    out = {}
    # leg context
    pre = X[X.index < LB_FROM]
    print("LEGS (weight 1)")
    for k in X.columns:
        st = stats(X[k])
        print(f"  {k:16} trades {meta.get(k, {}).get('trades', '?'):>5} | pre ${st['pre_net']:>10,.0f} DD ${st['pre_dd']:>7,.0f}"
              f" MAR {st['pre_mar']:5.2f} | LB ${st['lb_net']:>9,.0f} DD ${st['lb_dd']:>7,.0f}")
    cor = pre[BASE_KEYS + [c for c in X.columns if c not in BASE_KEYS]].corr()
    print("\nDaily correlation, pre-lockbox (weekdays incl. flat days):")
    print(cor.round(2).to_string())
    out["corr"] = cor.round(3).to_dict()

    base = X[BASE_KEYS] @ BASE_W
    bst = stats(base)
    out["base"] = bst
    print("\n" + fmt_row("#397 FRONTIER as run (1/1/3/1)", bst))
    print("  scale dial (same book, more or fewer contracts): " + " | ".join(
        f"x{s:.1f}: ROC {bst['pre_roc'] * s:5.1f}% LB {bst['lb_roc'] * s:5.1f}% DD ${bst['pre_dd'] * s:,.0f}"
        for s in (0.5, 1.0, 1.5, 2.0)))

    cands = {}
    if "ORB234" in X:
        cands["REF #396 (ORB #234 in the ORB slot)"] = X[["ORB234", "ENGUQ335", "TTM369", "NOISE304"]] @ BASE_W
    if "NOISE_CT382" in X:
        cands["REF NOISE slot = #382 (live Webull leg)"] = X[["ORB297", "ENGUQ335", "TTM369", "NOISE_CT382"]] @ BASE_W
    for extra, nm in (("ENGUQ_ES370", "ENGU-Q on ES #370"), ("TTM_NQ15B_280", "NQ 15m squeeze #280")):
        if extra in X:
            for w in (0.5, 1.0):
                cands[f"C  + {nm} x{w:g}"] = base + w * X[extra]
    if "ENGUQ_ES370" in X and "TTM_NQ15B_280" in X:
        cands["C  + both x1"] = base + X["ENGUQ_ES370"] + X["TTM_NQ15B_280"]
    cands["hindsight: ORB x0.5 (recorded r52)"] = X[BASE_KEYS] @ np.array([0.5, 1, 3, 1])
    cands["hindsight: squeeze x4 (run #378 knob)"] = X[BASE_KEYS] @ np.array([1, 1, 4, 1])

    print("\nCANDIDATES vs #397 (bar: MAR >= 1.05x, LB DD within 5%, LB net >=; years dominate/lose of 15)")
    out["cands"] = {}
    for label, s in cands.items():
        st = stats(s)
        scale = bst["pre_dd"] / st["pre_dd"] if st["pre_dd"] > 0 else float("nan")
        c1, c2, c3 = bar(bst, st)
        dom, lose, more = dominate_lose(base, s)
        print(fmt_row(label, st, scale=scale))
        print(f"  {'':44} bar: MAR {'Y' if c1 else 'n'} LB-DD {'Y' if c2 else 'n'} LB-net {'Y' if c3 else 'n'}"
              f"  -> {'PASS' if (c1 and c2 and c3) else 'fail'} | years: dominates {dom}, loses {lose}, more net {more} of 15")
        out["cands"][label] = dict(st, scale=scale, bar=[bool(c1), bool(c2), bool(c3)], dom=dom, lose=lose, more=more)

    test_a(X, out)
    with open(os.path.join(D, "book56_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=float)
    print("\nwrote", os.path.join(D, "book56_results.json"))


if __name__ == "__main__":
    main()
