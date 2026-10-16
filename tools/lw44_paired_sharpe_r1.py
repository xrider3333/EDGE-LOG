"""LW44 PAIRED SHARPE r1 (ORB lane, 2026-10-16; reading shelf No. 44, MANAGER #96) - the Ledoit-Wolf (2008) paired Sharpe-difference test
(augur_engine/sharpe_diff.py) on the house's recent claimed lifts and keep-decisions, candidate vs baseline on the same rows.
Frozen in docs/PREREG_lw44_paired_sharpe_r1_2026-10-16.md. In a real run this harness first checks the note's, the test module's and every
input file's sha256 and stops on any mismatch. Only cached daily series are read (pre-walk-forward and already-read walk-forward rows); no
engine run, no lockbox row.

    python tools/lw44_paired_sharpe_r1.py --parity     (build every pair; print each side's ROC @ $30k, Sortino, day count - no Sharpe, no test)
    python tools/lw44_paired_sharpe_r1.py [--out result.json]
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = os.path.join(HERE, "docs", "PREREG_lw44_paired_sharpe_r1_2026-10-16.md")
SDMOD = os.path.join(HERE, "augur_engine", "sharpe_diff.py")
NOTE_SHA = "30b2a66c5abe5d8c7a21fdb18bdf14bc88f4908e22d91997b1e6e0a0177b399d"
SD_SHA = "704559490f7b3dd1c393c9b8ccdd5333321ddd4ff5269ea55246570a5e3af894"
PINNED_MODS = {"augur_engine/book_sizing.py": "7c87cb0968896c0f0bd0cc94338a5bab8617661b032718273599b61669acb24f", "augur_engine/drawdowns.py": "e31a8404cdb170cec3463be868e3bcaecb2ab38194a73df6c061746cd2f569d5"}
C = r"C:\EdgeLog\_anatomy_cache"
BL = r"C:\EdgeLog\book_legs"
CM = r"C:\EdgeLog\custom_ml"
INPUTS = {                                                  # every file build() reads -> its sha256 (raw bytes), frozen in the note
    "book463": os.path.join(C, r"rocfrontier\r4\book463_daily.csv"),
    "resmom_close": os.path.join(C, r"rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"),
    "q34": os.path.join(C, r"q34\q34_daily.csv"),
    "q9": os.path.join(C, r"q9\daily.csv"),
    "r70": os.path.join(CM, "noise_r70_sidetilt_wf_daily_diff.csv"),
    "ttm458_keel": os.path.join(BL, "TTM458_keel_daily.csv"),
    "ttm458_raw": os.path.join(BL, "TTM458_raw_daily.csv"),
    "orb314": os.path.join(C, r"frontier_combo\legs\X_orb314_raw.csv"),
    "orb234": os.path.join(C, r"frontier_combo\legs\B_orb234.csv"),
    "orb239": os.path.join(C, r"rocfrontier\mdl_r1\refs\leg_ORB_239.csv"),
    "noise304": os.path.join(C, r"frontier_combo\legs\B_noise304.csv"),
    "noise382": os.path.join(C, r"frontier_combo\legs\X_noise382_raw.csv"),
    "noise422": os.path.join(C, r"frontier_combo\legs\X_noise422_raw.csv"),
    "noise422_fixed": os.path.join(BL, "NOISE422_fixed_daily.csv"),
    "noise422_rawbl": os.path.join(BL, "NOISE422_raw_daily.csv"),
    "records_U": os.path.join(C, r"rocfrontier\r11\records_U.npz"),
    "q43": os.path.join(C, r"q43\q43_noise_daily.csv"),
    "q37": os.path.join(C, r"q37\q37_daily.csv"),
    "q36": os.path.join(C, r"q36\q36_daily.csv"),
    "keel382": os.path.join(C, r"keel_parity\pertrade_full\replay_NOISE_382.csv"),
}
INPUT_SHA = {                                              # filled at freeze (raw-byte sha256)
    "book463": "d1543735b5408f50be5971089e00a800f8e510af3d4a63678ff8939f41277dff",
    "resmom_close": "e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18",
    "q34": "d03ef890d7146598d91639fc91a75088559e3784eb8c1437ffe1f29534245b3a",
    "q9": "4ef06f5c8d95a1946dfe445a3a2b0118b0667341a0e7b4d36cc1dfb0dc5078ef",
    "r70": "2b27c7b9c2c624e86eb47ce6ee08809eaf5740cf95b9b5d7b6b2cc3179b048a2",
    "ttm458_keel": "04fe514f38121c3af6f67e0d67b248b85d9d5b625fbf96862fe7997f6fce5c30",
    "ttm458_raw": "46fdb3f34fbd13e09f32697cf89533a657b120653c4ea30f633d422e75950635",
    "orb314": "993901498c0851f06f342180bc29f5a765717f27eec2ccce496917f8f1cd7b54",
    "orb234": "20deecf7cd29a2431c96c9b33ebed12aa521082bacc2eecebbadeccd8c6ef29b",
    "orb239": "2e3964a8d65777f1886543df962ec5a65d0961f38f4cd496056f4c0f5a639eb3",
    "noise304": "0c4e30b972a4c0111e6e61b76fb6b7d8c00bd0b6b15c6dad1c32ddf3a1955fe8",
    "noise382": "41126b857af3b884bc4812993c8cb29bdfd0067d6508acf987e6b5678519fb53",
    "noise422": "7e6cb0e03da219e8829aa35300b5df0a528bcb831c9bf7d1835663c998cac78a",
    "noise422_fixed": "57d4d272bcaf2f73c3fc0456fde852837bbb7ec1de303dcd9c95b23124df7dc4",
    "noise422_rawbl": "c51b0a20e806dd543157798972ed87eec371264bea0cdce4b1e506dfb3982646",
    "records_U": "d1774ccf0adc7c9a2a3fb20d99673ddfb4568b63ed7b6875ab08bd5138de8ee2",
    "q43": "6593f22e84983ef71198853c59927661a6321050039b7f501b4c91585ac6e4ba",
    "q37": "7de64c400cfe5b53a5b14ee89a0cbd15cbfedb482528d2cf00a4989323a086f5",
    "q36": "4612ca2a367c7cce8a4bbcb0258b565be02a78115a45f27dee633c598ae61f86",
    "keel382": "4a6b4a3f9021689fbadad7b1843169f49625ccad380fcf3aaf6c37ec40369c42",
}
PRE0, PRE1 = "2010-06-07", "2016-06-30"
BWF0, BWF1 = "2016-07-01", "2025-06-29"                     # the book's walk-forward
NWF0, NWF1 = "2016-06-30", "2025-07-15"                     # NOISE runs' own walk-forward (#304 / #382 / #422)
B_MAIN, B_SENS, M, SEED, ALPHA = 20, (5, 60), 4999, 7, 0.05
PARITY_TOL = 0.1                                           # ROC points vs the frozen reproduction; a miss drops the pair


def lf_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def raw_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def roc_sortino(x):
    """house convention (tools/noise_hedge_tilt.roc_sortino): years = (last - first) / 365.25, drawdown from a 0 start"""
    yrs = (x.index.max() - x.index.min()).days / 365.25
    q = np.cumsum(x.to_numpy(float))
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max())
    dn = math.sqrt(float(np.mean(np.minimum(x.to_numpy(float), 0.0) ** 2)))
    return (30.0 * (float(x.sum()) / yrs) / dd if dd > 0 else float("nan"), float(x.mean()) / dn * math.sqrt(252) if dn > 0 else float("nan"), dd)


def four(x):
    """ROC @ $30k, DD5 and DD % from peak at the size whose worst drawdown is $30k (account from $100k), Sortino; also DD5 and DD % at the
    series' own size, so the book pairs can be checked against the ledger rows"""
    from augur_engine.drawdowns import dd5, dd_pct_peak
    roc, so, dd = roc_sortino(x)
    k = 30000.0 / dd if dd > 0 else 1.0
    d5 = dd5(x)
    return {"roc30": round(roc, 2), "dd5_at_30k": round(float(d5["dd5_usd"]) * k, 0), "one_episode": bool(d5["one_episode"]),
            "dd_pct_peak_at_30k": round(float(dd_pct_peak(x * k, start=100000.0)), 2), "sortino": round(so, 3),
            "dd5_own": round(float(d5["dd5_usd"]), 0), "dd_pct_peak_own": round(float(dd_pct_peak(x, start=100000.0)), 2)}


def _csv(path, col, date_col=None):
    d = pd.read_csv(path)
    dc = date_col or d.columns[0]
    return pd.Series(d[col].to_numpy(float), index=pd.to_datetime(d[dc]).dt.normalize()).groupby(level=0).sum()


def _on(s, idx):
    return s.reindex(idx).fillna(0.0)


def _bcal(lo="2010-06-07", hi="2026-06-30"):
    return pd.bdate_range(lo, hi)


# ---------------------------------------------------------------- the pairs (frozen in the prereg) ----------------------------------------
def build():
    bk = pd.read_csv(INPUTS["book463"])
    bk.index = pd.to_datetime(bk["date"]).dt.normalize()
    bk = bk.groupby(level=0).sum(numeric_only=True)
    I = bk.index
    mtm = bk["mtm"]
    L = {k: bk["L%d_mtm" % k] for k in range(4)}
    fc = lambda key: _on(_csv(INPUTS[key], "pnl_usd", "date"), I)                 # noqa: E731  sparse leg on the book calendar
    rm = pd.read_csv(INPUTS["resmom_close"])
    rm.index = pd.to_datetime(rm["date"]).dt.normalize()
    Lres = rm["book_mtm"] + 0.264 * rm["RES"]
    q34 = pd.read_csv(INPUTS["q34"])
    q34.index = pd.to_datetime(q34["date"]).dt.normalize()
    P = []

    def add(pid, grp, row, fam, claim, cand, base, w0, w1, expect, pre=False):
        P.append({"id": pid, "grp": grp, "row": row, "fam": fam, "claim": claim, "cand": cand, "base": base, "w": (w0, w1), "expect": expect,
                  "pre": pre})

    # ---- LIFT: the ledger claimed the candidate better on its WF rows, or the house adopted / crowned it or opened a forward line on it ----
    add("P01", "LIFT", "2.175", "TTM/BOOK", "#463 with TTM (kept) vs #463 without TTM", mtm, mtm - L[2], BWF0, BWF1, (93.81, 99.56), pre=True)
    q36 = pd.read_csv(INPUTS["q36"])
    q36.index = pd.to_datetime(q36["date"]).dt.normalize()
    add("P05", "LIFT", "2.133", "ENGU-Q", "ENGU-Q on QQQ: NQ #335 signals filled on QQQ (B) vs the leg run on QQQ bars (A)", q36["B"], q36["A"], BWF0,
        BWF1, (28.42, 19.91))
    add("P07", "LIFT", "2.76/2.99", "BOOK", "RESMOM line L = #463 + 0.264 RES vs #463", Lres, rm["book_mtm"], BWF0, BWF1, (121.06, 93.81))
    from augur_engine.book_sizing import vt_multipliers
    z = np.load(INPUTS["records_U"], allow_pickle=True)
    day = lambda a: pd.to_datetime(np.asarray(a, "int64"), unit="D")                                     # noqa: E731
    vi = _bcal().union(pd.DatetimeIndex(day(z["inc_d"])).unique())
    vi = vi[vi <= pd.Timestamp(BWF1)]                                       # nothing after the WF end enters the multipliers
    keep = np.asarray(day(z["inc_d"]) <= pd.Timestamp(BWF1))
    inc_d, inc_v, inc_t = day(z["inc_d"])[keep], z["inc_v"][keep], z["inc_t"][keep]
    raw = pd.Series(inc_v, index=inc_d).groupby(level=0).sum().reindex(vi).fillna(0.0)
    mlt = vt_multipliers(raw)
    me = mlt.reindex(day(z["entry"][inc_t])).to_numpy()
    if np.isnan(me).any():
        raise SystemExit("P12: a trade's entry day is not on the V2 calendar")
    v2 = pd.Series(inc_v * me, index=inc_d).groupby(level=0).sum().reindex(vi).fillna(0.0)
    add("P12", "LIFT", "2.32/2.47", "BOOK", "V2 vol target on #463 vs #463 raw (rule-U records)", v2, raw, BWF0, BWF1, (117.81, 93.81), pre=True)
    tk, tr = fc("ttm458_keel"), fc("ttm458_raw")
    add("P13", "LIFT", "KEEL458 (adopt449) / 10p", "TTM/BOOK", "KEEL line: #463 with TTM #458 x KEEL v12 vs its RAW twin #468", mtm - L[2] + tk,
        mtm - L[2] + tr, "2016-07-27", BWF1, (119.66, 113.84), pre=True)
    add("P14", "LIFT", "2.44 Q1a", "ORB/BOOK", "#473: ORB #314 in the ORB seat vs #463", mtm - L[0] + fc("orb314"), mtm, BWF0, BWF1, (125.55, 93.81),
        pre=True)
    o239 = _on(_csv(INPUTS["orb239"], "pnl", "date"), I)
    add("P15", "LIFT", "2.44 Q6", "ORB/BOOK", "#478: ORB #239 (BE 0.8) in the ORB seat vs #463", mtm - L[0] + o239, mtm, BWF0, BWF1, (101.76, 93.81),
        pre=True)
    add("P16", "LIFT", "2.51 / 10t Q8", "NOISE/BOOK", "NOISE x1.25 forward line vs #463", mtm + 0.25 * L[3], mtm, BWF0, BWF1, (99.83, 93.81), pre=True)
    add("P18", "LIFT", "2.26 as re-read 10r Q2ctx", "NOISE/BOOK", "#463 (NOISE #422 seat) vs #471 (NOISE #304 in the seat)", mtm,
        mtm - L[3] + fc("noise304"), BWF0, BWF1, (93.81, 85.12), pre=True)
    kr = pd.read_csv(INPUTS["keel382"])
    kd = pd.to_datetime(kr["entry_ts"].str.slice(0, 10))
    nb = _bcal()
    kc = _on(pd.Series(kr["pnl"].to_numpy(float) * 20.0 * kr["walk_size"].to_numpy(float), index=kd).groupby(level=0).sum(), nb)
    kb = _on(pd.Series(kr["pnl"].to_numpy(float) * 20.0, index=kd).groupby(level=0).sum(), nb)
    add("P02", "LIFT", "2.160", "NOISE", "#382 + KEEL v12 (live) vs raw #382 (10-14 master)", kc, kb, NWF0, NWF1, (82.90, 80.63), pre=True)
    nl = lambda key: _on(_csv(INPUTS[key], "pnl_usd", "date"), nb)                                     # noqa: E731
    add("P19", "LIFT", "NOISE r61", "NOISE", "crown #422 vs #382", nl("noise422"), nl("noise382"), NWF0, NWF1, (84.65, 80.20), pre=True)
    add("P20", "LIFT", "2.8", "NOISE", "#382 compression size tilt vs #304", nl("noise382"), nl("noise304"), NWF0, NWF1, (80.20, 66.01), pre=True)
    add("P22", "LIFT", "README_ml_legs_NOISE 09-27", "NOISE", "NOISE #422 + KEEL v12 fixed package vs raw #422", nl("noise422_fixed"),
        nl("noise422_rawbl"), NWF0, NWF1, (109.05, 84.65), pre=True)
    add("P21", "LIFT", "ORB 09-05", "ORB", "crown #314 vs #234", nl("orb314"), nl("orb234"), BWF0, BWF1, (35.82, 34.49), pre=True)

    q37 = pd.read_csv(INPUTS["q37"])
    q37.index = pd.to_datetime(q37.iloc[:, 0]).dt.normalize()
    add("P04", "LIFT", "2.134 (Q37 QQQ arm)", "DIP", "DIP #424 on QQQ: fixed size (adopted; DIP_424F live) vs KEEL v12 sizing", q37["QQQ F fixed at s_bar"],
        q37["QQQ KEEL v12 (today's walk)"], "2017-08-07", "2025-08-24", (21.32, 19.47))

    # ---- KEEP: the house reported a null or rejected a challenger; candidate = the side the house KEPT ----
    q43 = pd.read_csv(INPUTS["q43"])
    q43.index = pd.to_datetime(q43.iloc[:, 0]).dt.normalize()
    add("P03", "KEEP", "2.171", "NOISE(QQQ)", "Webull NOISE seat kept: NOISE_382 vs the #422 file (challenger) on QQQ", q43["S382"], q43["S422"],
        "2017-08-07", BWF1, (83.14, 73.15))
    add("P06", "KEEP", "2.127", "ENGU-Q/BOOK", "ENGU-Q seat in L (kept) vs its always-on drift twin (not distinguishable)", Lres,
        Lres - q34["leg"] + q34["always-on"], BWF0, BWF1, (121.06, 96.41))
    add("P08", "KEEP", "2.81 (S1 re-read)", "ENGU-Q/BOOK", "ENGU-Q x1.00 in L (kept) vs the x0.75 rung", Lres,
        Lres - 0.25 * L[1].reindex(Lres.index).fillna(0.0), BWF0, BWF1, (121.06, 126.10))
    q9 = pd.read_csv(INPUTS["q9"])
    q9.index = pd.to_datetime(q9.iloc[:, 0]).dt.normalize()
    add("P09", "KEEP", "2.58", "BOOK", "#463 (kept) vs #463 + TREND seat (FAILED Stage A)", q9["book463"], q9["book463"] + q9["trend_primary"], BWF0,
        BWF1, (93.81, 106.36), pre=True)
    r70 = _on(_csv(INPUTS["r70"], "diff_usd", "date"), I)
    add("P11", "KEEP", "2.53", "NOISE/BOOK", "plain NOISE (kept; size-matched twin c 1.135) vs r70 NOISE shorts x1.5 (DEAD)", mtm + 0.135 * L[3], mtm + r70,
        BWF0, BWF1, (97.10, 100.54))
    add("P17", "KEEP", "2.30 / 10n", "TTM/BOOK", "#463 (kept, decided on the spent lockbox) vs #468 (TTM #458)", mtm, mtm - L[2] + tr, BWF0, BWF1,
        (93.81, 113.27), pre=True)
    return P


CLUSTERS = [("P06", "P07", "P08"), ("P13", "P17"), ("P14", "P21"), ("P18", "P19", "P20"), ("P02", "P22")]


def cut(s, w0, w1):
    s = s.astype(float)
    return s[(s.index >= pd.Timestamp(w0)) & (s.index <= pd.Timestamp(w1))]


def paired(p, w0, w1):
    x, y = cut(p["cand"], w0, w1), cut(p["base"], w0, w1)
    if x.isna().any() or y.isna().any():
        raise SystemExit("%s: NaN in a side (misaligned build)" % p["id"])
    ix = x.index.union(y.index)
    return x.reindex(ix).fillna(0.0), y.reindex(ix).fillna(0.0)


def reading(grp, t):
    lo, hi = t["ci_boot"]
    if grp == "LIFT":
        return "SURVIVES" if (t["diff"] > 0 and t["p_boot"] < ALPHA) else ("REVERSED" if hi < 0 else "NOT SHOWN")
    return "CONFIRMS THE KEEP" if (t["diff"] > 0 and t["p_boot"] < ALPHA) else ("DISAGREES" if hi < 0 else "AGREES (no difference)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
    ap.add_argument("--parity", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    got = lf_sha(NOTE) if os.path.exists(NOTE) else "missing"
    print("PIN note LF sha256 %s (frozen %s); test module %s (frozen %s); harness %s" % (got, NOTE_SHA, lf_sha(SDMOD), SD_SHA,
          lf_sha(os.path.abspath(__file__))), flush=True)
    if not a.parity:
        if got != NOTE_SHA or lf_sha(SDMOD) != SD_SHA:
            raise SystemExit("refused: the prereg note or the test module is not the frozen one (nothing computed)")
        badm = [k for k, v in PINNED_MODS.items() if lf_sha(os.path.join(HERE, *k.split("/"))) != v]
        if badm:
            raise SystemExit("refused: pinned modules changed since the freeze: %s (nothing computed)" % badm)
        bad = [k for k, f in INPUTS.items() if raw_sha(f) != INPUT_SHA.get(k)]
        if bad:
            raise SystemExit("refused: input files changed since the freeze: %s (nothing computed)" % bad)
        a.out = a.out or os.path.join(C, "lw44", "lw44_r1_result.json")
    sys.path.insert(0, a.repo)
    sys.path.insert(0, HERE)
    from augur_engine.sharpe_diff import sharpe_diff_test
    pairs = build()
    res, kept = {"pairs": []}, []
    for p in pairs:
        w0, w1 = p["w"]
        x, y = paired(p, w0, w1)
        rx, ry = roc_sortino(x), roc_sortino(y)
        ex = p["expect"]
        ok = all(e is None or abs(r - e) <= PARITY_TOL for r, e in ((rx[0], ex[0]), (ry[0], ex[1])))
        rec = {"id": p["id"], "grp": p["grp"], "row": p["row"], "fam": p["fam"], "claim": p["claim"], "window": [w0, w1], "days": int(len(x)),
               "roc_cand": round(rx[0], 2), "roc_base": round(ry[0], 2), "sortino_cand": round(rx[1], 3), "sortino_base": round(ry[1], 3),
               "expect": ex, "parity_ok": ok}
        print("%s %-4s %-11s %-74s days %d  cand ROC %.2f / Sortino %.3f  base ROC %.2f / Sortino %.3f (expect %s) %s" % (p["id"], p["grp"],
              p["fam"], p["claim"][:74], len(x), rx[0], rx[1], ry[0], ry[1], ex, "PARITY OK" if ok else "PARITY MISS -> dropped"), flush=True)
        res["pairs"].append(rec)
        if a.parity or not ok:
            continue
        rec["corr"] = round(float(np.corrcoef(x, y)[0, 1]), 4)
        rec["four_cand"], rec["four_base"] = four(x), four(y)
        t = sharpe_diff_test(x.to_numpy(), y.to_numpy(), b=B_MAIN, M=M, alpha=ALPHA, seed=SEED)
        rec["test"] = {k: (round(v, 4) if isinstance(v, float) else [round(u, 4) for u in v] if isinstance(v, list) else v) for k, v in t.items()}
        rec["mde80"] = round(2.8 * t["se_hac"], 4)
        rec["sens"] = {}
        for b in B_SENS:
            s = sharpe_diff_test(x.to_numpy(), y.to_numpy(), b=b, M=M, alpha=ALPHA, seed=SEED)
            rec["sens"][str(b)] = {"p_boot": round(s["p_boot"], 4), "ci_boot": [round(u, 4) for u in s["ci_boot"]]}
        rec["reading"] = reading(p["grp"], t)
        T = rec["test"]
        print("    SR cand %.3f base %.3f diff %+.4f | boot 95%% %s p %.4f | HAC 95%% %s p %.4f | MDE80 %.3f | b5 p %.4f b60 p %.4f | corr %.4f | %s" % (
            T["sr_x"], T["sr_y"], T["diff"], T["ci_boot"], T["p_boot"], T["ci_hac"], T["p_hac"], rec["mde80"], rec["sens"]["5"]["p_boot"],
            rec["sens"]["60"]["p_boot"], rec["corr"], rec["reading"]), flush=True)
        for side in ("cand", "base"):
            f = rec["four_" + side]
            print("    four %s: ROC %s | DD5 $%s | DD%% %s | Sortino %s%s  (own size: DD5 $%s, DD%% %s)" % (side, f["roc30"], f["dd5_at_30k"],
                  f["dd_pct_peak_at_30k"], f["sortino"], " (1 ep)" if f["one_episode"] else "", f["dd5_own"], f["dd_pct_peak_own"]), flush=True)
        if p["pre"]:
            pe = min(pd.Timestamp(w0) - pd.Timedelta(days=1), pd.Timestamp(PRE1)).strftime("%Y-%m-%d")
            xp, yp = paired(p, PRE0, pe)
            if len(xp) > 3 * B_MAIN and float(np.std(xp.to_numpy() - yp.to_numpy())) > 0 and xp.std() > 0 and yp.std() > 0:
                s = sharpe_diff_test(xp.to_numpy(), yp.to_numpy(), b=B_MAIN, M=M, alpha=ALPHA, seed=SEED)
                rec["pre_wf"] = {"window": [PRE0, pe], "days": int(len(xp)), "sr_cand": round(s["sr_x"], 3), "sr_base": round(s["sr_y"], 3),
                                 "diff": round(s["diff"], 4), "p_boot": round(s["p_boot"], 4), "ci_boot": [round(u, 4) for u in s["ci_boot"]],
                                 "four_cand": four(xp), "four_base": four(yp)}
                q = rec["pre_wf"]
                print("    pre-WF %s..%s (%d rows, report only): SR %.3f vs %.3f diff %+.4f 95%% %s p %.4f | cand ROC %s DD5 $%s DD%% %s Sortino %s"
                      " | base ROC %s DD5 $%s DD%% %s Sortino %s" % (PRE0, pe, q["days"], q["sr_cand"], q["sr_base"], q["diff"], q["ci_boot"],
                      q["p_boot"], q["four_cand"]["roc30"], q["four_cand"]["dd5_at_30k"], q["four_cand"]["dd_pct_peak_at_30k"],
                      q["four_cand"]["sortino"], q["four_base"]["roc30"], q["four_base"]["dd5_at_30k"], q["four_base"]["dd_pct_peak_at_30k"],
                      q["four_base"]["sortino"]), flush=True)
        kept.append(rec)
    if not a.parity:
        lifts = [r for r in kept if r["grp"] == "LIFT"]
        order = sorted(lifts, key=lambda r: r["test"]["p_boot"])
        m = len(order)
        holm = set()
        for i, r in enumerate(order):                       # Holm step-down on the two-sided bootstrap p over the LIFT pairs tested
            if r["test"]["p_boot"] <= ALPHA / (m - i):
                holm.add(r["id"])
            else:
                break
        for r in lifts:
            r["survives_holm"] = bool(r["reading"] == "SURVIVES" and r["id"] in holm)
        res["lift_tested"] = m
        res["survive"] = sorted(r["id"] for r in lifts if r["reading"] == "SURVIVES")
        res["survive_holm"] = sorted(r["id"] for r in lifts if r["survives_holm"])
        res["reversed"] = sorted(r["id"] for r in lifts if r["reading"] == "REVERSED")
        res["keep"] = {r["id"]: r["reading"] for r in kept if r["grp"] == "KEEP"}
        res["dropped_parity"] = sorted(r["id"] for r in res["pairs"] if not r["parity_ok"])
        res["clusters"] = {"+".join(c): [r["id"] for r in lifts if r["id"] in c and r["reading"] == "SURVIVES"] for c in CLUSTERS}
        print("LIFT pairs tested %d: SURVIVE %d %s; after Holm %d %s; REVERSED %s; NOT SHOWN = the rest" % (m, len(res["survive"]), res["survive"],
              len(res["survive_holm"]), res["survive_holm"], res["reversed"]), flush=True)
        print("KEEP pairs: %s" % res["keep"], flush=True)
        print("clusters (survivors): %s; dropped on parity: %s" % (res["clusters"], res["dropped_parity"]), flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, default=str)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
