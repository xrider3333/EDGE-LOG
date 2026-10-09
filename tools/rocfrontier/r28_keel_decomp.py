# r28 - KEEL DECOMPOSITION on run #424 (MANAGER #146 (3) / #147; the owner's KEEL question: Kim-Tse-Wald + Nagel 2025).
# Specification: docs/PREREG_KEEL_DECOMP_424_2026-10-09.md + its ADDENDUM 1 (canonical LF sha256 NOTE_SHA below; witness branch
# prereg/sb-keel-decomp-424). REPORT ONLY - nothing is adopted, written to Firestore, or traded. WF trades only; the lockbox is
# never read (KEEL's family lockbox is spent). Firestore is READ (the run doc, for the guard and the windows), never written.
#   python C:\EdgeLog\_anatomy_cache\bookq\run_shared.py tools/rocfrontier/r28_keel_decomp.py selftest   fakes only
#   python C:\EdgeLog\_anatomy_cache\bookq\run_shared.py tools/rocfrontier/r28_keel_decomp.py run        the real run
# (run_shared.py loads the SHARED checkout's augur_engine first - the worktree registry trap.)
# Readings (the note's numbering): 1 RAW, 2 KEEL v12 (today's walk, A2), 3 F fixed twin at s_bar, 4 FT fixed tilts only, 5 LO
# learned part only (shade included, A9), 6 M Nagel trailing-P&L momentum twin (A4, A5), 7 P1 = M reversed (a re-solved), 8 P2 =
# KEEL re-walked on the sign-flipped series (F_flip at P2's own mean, A8). Lists: PURE (primary) and SAVED (second column, A1).
import copy, hashlib, json, os, sys, time
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(HERE))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
NOTE = os.path.join(WT, "docs", "PREREG_KEEL_DECOMP_424_2026-10-09.md")
NOTE_SHA = "3957f762f3203c310992cc02a01418570c89325d536e9b6469150ce2d2b0e987"      # canonical LF: the note + ADDENDUM 1
OUT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\keel424"
LISTS = {"PURE": r"C:\EdgeLog\_anatomy_cache\restate_roll\dip424_pure_trades.csv",
         "SAVED": r"C:\EdgeLog\_anatomy_cache\restate_roll\dip424_saved_trades.csv"}
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
RUN = 424
SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth"}
VERSION = "v12"
N_MOM, MIN_RESOLVED = 20, 100          # A4: the trailing window (resolved trades, exit order) and the warm-up (resolved trades)
CLIP = (0.5, 2.0)                      # [6] the clip MANAGER named
B_MAX, B_FALLBACK = 20.0, 0.5          # A5: b searched on [0, B_MAX]; KEEL's base slope if mean AND sd cannot both be matched
N_PERM, BLOCK = 2000, 20               # A6
SEED_PLAIN, SEED_BLOCK = 20261009, 20261010
COST_PT_RT, USD_PT_MNQ, NOTIONAL = 0.783, 2.0, 100000.0      # A10: NQDIP_1_1's own cost (inside the plugin)


def say(*a):
    print(*a, flush=True)


def lf_sha(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------ statistics (r11_risk.stats, the house's unified convention; A7)
def stats(x, dates):
    x = np.asarray(x, float)
    c = np.cumsum(x)
    dd = np.maximum.accumulate(np.concatenate([[0.0], c]))[1:] - c
    yrs = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    net, mdd = float(x.sum()), float(dd.max())
    dn = float(np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)))
    ann = net / yrs if yrs > 0 else float("nan")
    return {"net": net, "usd_year": ann, "max_dd": mdd, "roc": 30.0 * ann / mdd if mdd > 0 else float("nan"),
            "sortino": float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")}


def daily(pnl, exit_day, days):
    """book each trade's $ on its EXIT session -> one value per row of `days` (zero days included)"""
    s = pd.Series(np.asarray(pnl, float)).groupby(np.asarray(exit_day)).sum()
    return s.reindex(days, fill_value=0.0).to_numpy()


def reading(name, sizes, r, exit_day, days, s_bar=None):
    from augur_engine.drawdowns import dd5
    w = np.asarray(sizes, float)
    x = daily(w * np.asarray(r, float), exit_day, days)
    st = stats(x, days)
    d5 = dd5(pd.Series(x, index=days))
    by_year = pd.Series(x, index=days).groupby(pd.DatetimeIndex(days).year).sum().round(2)
    out = {"name": name, **st, "dd5": float(d5["dd5_usd"]), "one_episode": bool(d5["one_episode"]),
           "size_mean": float(w.mean()), "size_sd": float(w.std()), "size_min": float(w.min()), "size_max": float(w.max()),
           "by_year": {int(k): float(v) for k, v in by_year.items()}}
    if s_bar is not None:
        out["timing"] = timing(w, r, s_bar)
    return out


def timing(sizes, r, s_bar):
    """the TIMING component: sum (s_i - s_bar) x r_i (the Kim-Tse-Wald split's non-leverage part)"""
    return float(np.sum((np.asarray(sizes, float) - s_bar) * np.asarray(r, float)))


def perm_null(sizes, r, seed, block=None, n=N_PERM):
    """A6: timing of n shuffles of the reading's OWN sizes across the WF trades (mean kept, alignment destroyed); a fresh generator
    per call; block = permute whole runs of `block` consecutive trades (entry order), the partial last run kept as its own block"""
    w, rr = np.asarray(sizes, float), np.asarray(r, float)
    m = w.mean()
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    if block:
        blocks = [w[c:c + block] for c in range(0, len(w), block)]
        for k in range(n):
            out[k] = np.sum((np.concatenate([blocks[j] for j in rng.permutation(len(blocks))]) - m) * rr)
    else:
        for k in range(n):
            out[k] = np.sum((rng.permutation(w) - m) * rr)
    return out


def null_line(sizes, r):
    s_bar = float(np.mean(sizes))
    t = timing(sizes, r, s_bar)
    a = perm_null(sizes, r, SEED_PLAIN)
    b = perm_null(sizes, r, SEED_BLOCK, block=BLOCK)
    return {"timing": t, "plain_p95": float(np.percentile(a, 95)), "plain_pct": float((a < t).mean() * 100),
            "block_p95": float(np.percentile(b, 95)), "block_pct": float((b < t).mean() * 100)}


# ------------------------------------------------------------------ A4: the Nagel momentum signal (causal)
def momentum_z(E, X, r):
    """per trade (entry order): resolved for i = exit bar strictly before i's entry bar, ordered by exit bar (ties: entry order).
    R_k = sum of r over resolved trades k-19 .. k; m_i = R_K; sd_i = sd (ddof 1) of R_20 .. R_K; z_i = m_i / sd_i; 0 while K < 100"""
    E, X, r = np.asarray(E), np.asarray(X), np.asarray(r, float)
    order = np.argsort(X, kind="stable")
    xs, rs = X[order], r[order]
    roll = pd.Series(rs).rolling(N_MOM).sum().to_numpy()
    z = np.zeros(len(E))
    for i in range(len(E)):
        k = int(np.searchsorted(xs, E[i], side="left"))
        if k < MIN_RESOLVED:
            continue
        hist = roll[N_MOM - 1:k]
        sd = float(np.std(hist, ddof=1)) if len(hist) > 1 else 0.0
        z[i] = roll[k - 1] / sd if sd > 0 else 0.0
    return z


def clip_sizes(a, b, z):
    return np.clip(a + b * z, CLIP[0], CLIP[1])


def solve_a(b, z, target_mean):
    lo, hi = -50.0, 50.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if clip_sizes(mid, b, z).mean() < target_mean:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def calibrate(z, target_mean, target_sd):
    """A5: b >= 0 on [0, B_MAX] and a such that M's WF sizes have the target mean AND sd inside the clip; else b = B_FALLBACK, mean only"""
    def sd_at(b):
        a = solve_a(b, z, target_mean)
        return clip_sizes(a, b, z).std(), a
    if sd_at(B_MAX)[0] < target_sd:
        return solve_a(B_FALLBACK, z, target_mean), B_FALLBACK, False
    lo, hi = 0.0, B_MAX
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if sd_at(mid)[0] < target_sd:
            lo = mid
        else:
            hi = mid
    b = 0.5 * (lo + hi)
    return sd_at(b)[1], b, True


# ------------------------------------------------------------------ KEEL parts
def keel_parts(arrays, T, ML):
    """v12's walk, and the SAME walk with the a-priori tilts off (= the learned part L, shade included): the tilts are applied after
    the loop and never feed the ledgers, so L is exact; asserted by rebuilding v12's size from L"""
    feats = ML.keel_features(arrays)                                                   # (F, names), computed once for every walk
    kw = ML.keel_walk(arrays, T, feats=feats, version=VERSION)
    cfg = copy.deepcopy(ML.CFG[VERSION])
    for k in ("dow", "comp", "event"):
        cfg.pop(k, None)
    ML.CFG["_r28_learned"] = cfg
    try:
        kl = ML.keel_walk(arrays, T, feats=feats, version="_r28_learned")
    finally:
        ML.CFG.pop("_r28_learned", None)
    assert np.array_equal(kw["E"], kl["E"]) and np.allclose(np.nan_to_num(kw["z"]), np.nan_to_num(kl["z"]))
    L = kl["size"]
    v = ML.CFG[VERSION]
    idx = pd.DatetimeIndex(arrays["index"]); E = kw["E"]
    wd = idx[np.clip(E, 0, len(idx) - 1)].dayofweek
    s = np.minimum(L * np.array([float(v["dow"].get(str(int(w)), 1.0)) for w in wd]), float(v["dow"].get("cap", 3.0)))
    F, names = feats                                                                  # keel_walk returns "X" = the EXIT bars, not the features
    on = np.asarray(F)[np.clip(E, 0, len(F) - 1)][:, list(names).index(v["comp"]["feature"])] > 0
    s = np.minimum(np.where(on, s * float(v["comp"]["mult"]), s), float(v["comp"].get("cap", 3.0)))
    s = np.where(ML.pre_statement_mask(arrays, E, v["event"].get("cut_hour", 14)), s * float(v["event"].get("mult", 0.5)), s)
    assert np.allclose(s, kw["size"], atol=1e-12), "v12's size is not event(comp(dow(L)))"
    nonshade = np.clip(1.0 + float(v["K"]) * kl["trust"] * np.nan_to_num(kl["z"]), float(v["LO"]), float(v["HI"]))
    shade = ~np.isclose(L, nonshade, atol=1e-12)                                      # A9
    FT = ML.fixed_tilt_sizes_v12(arrays, E)
    return kw, L, FT, shade, feats


# ------------------------------------------------------------------ A1: a trade file -> keel_walk's (entry bar, exit bar, pnl)
def load_list(path, arrays):
    df = pd.read_csv(path)
    wall = pd.DatetimeIndex(arrays["index"]).tz_localize(None)
    pos = pd.Series(np.arange(len(wall)), index=wall)
    e = pd.to_datetime(df["entry"]); x = pd.to_datetime(df["exit"])
    miss = (~e.isin(wall)).sum() + (~x.isin(wall)).sum()
    if miss:
        sys.exit(f"refused: {miss} entry/exit time(s) of {os.path.basename(path)} match no master bar start exactly (nothing computed)")
    T = sorted(zip(pos[e].to_numpy().astype(int), pos[x].to_numpy().astype(int), df["pnl"].astype(float)), key=lambda t: t[0])
    return [(int(a), int(b), float(c)) for a, b, c in T]


# ------------------------------------------------------------------ the decomposition on one list
def decompose(arrays, T, wf0, wf1, ML):
    wall = pd.DatetimeIndex(arrays["index"]).tz_localize(None); nb = len(wall)
    kw, L, FT, shade, feats = keel_parts(arrays, T, ML)
    E = np.asarray(kw["E"], int)
    Xb = np.array([t[1] for t in kw["trades"]], int)
    r = np.asarray(kw["P"], float)
    ent = wall[np.clip(E, 0, nb - 1)]
    exd = wall[np.clip(Xb, 0, nb - 1)].normalize()
    wf = np.asarray((ent >= pd.Timestamp(wf0)) & (ent < pd.Timestamp(wf1)))                              # A7
    sess = pd.DatetimeIndex(sorted(set(wall.normalize())))
    days = sess[(sess >= pd.Timestamp(wf0)) & (sess <= exd[wf].max())]
    rw, xw = r[wf], exd[wf]
    o = np.asarray(arrays["open"], float)[np.clip(E, 0, nb - 1)][wf]
    unit_cost = COST_PT_RT * USD_PT_MNQ * np.round(NOTIONAL / (o * USD_PT_MNQ))                         # A10: $ cost at size 1
    S = kw["size"][wf]
    s_bar = float(S.mean())
    res = {"n_all": int(len(r)), "n_wf": int(wf.sum()), "s_bar": s_bar, "s_sd": float(S.std()),
           "trust_on_wf": float((kw["trust"][wf] > 0).mean()), "shade_share_wf": float(shade[wf].mean()),
           "avg_size_pre_all": None, "readings": {}, "gross": {}, "nulls": {}}
    R, G = res["readings"], res["gross"]
    ft = FT[wf] * (s_bar / FT[wf].mean())
    lo = L[wf] * (s_bar / L[wf].mean())
    z = momentum_z(E, Xb, r)[wf]
    a, b, both = calibrate(z, s_bar, float(S.std()))
    m_sizes = clip_sizes(a, b, z)
    a1 = solve_a(-b, z, s_bar)
    p1 = clip_sizes(a1, -b, z)
    sizes = {"RAW": np.ones(wf.sum()), "KEEL": S, "F": np.full(wf.sum(), s_bar), "FT": ft, "LO": lo, "M": m_sizes, "P1": p1}
    names = {"RAW": "RAW", "KEEL": "KEEL v12 (today's walk)", "F": "F fixed at s_bar", "FT": "FT fixed tilts only",
             "LO": "LO learned part only", "M": "M Nagel momentum", "P1": "P1 momentum reversed"}
    for k, w in sizes.items():
        R[k] = reading(names[k], w, rw, xw, days, None if k == "RAW" else s_bar)
        G[k] = reading(names[k] + " (approx. gross)", w, rw + unit_cost, xw, days, None if k == "RAW" else s_bar)
    res["momentum"] = {"a": a, "b": b, "mean_and_sd_matched": both, "a_p1": a1,
                       "corr_keel_dev_z": float(np.corrcoef(S - s_bar, z)[0, 1]) if z.std() > 0 else float("nan"),
                       "ols_keel_on_z": float(np.polyfit(z, S, 1)[0]) if z.std() > 0 else float("nan"),
                       "z_zero_share_wf": float((z == 0).mean())}
    Tf = [(e, x, -p) for (e, x, p) in kw["trades"]]                                                     # [8] P2
    kf = ML.keel_walk(arrays, Tf, feats=feats, version=VERSION)
    assert np.array_equal(kf["E"], kw["E"])
    Sf = kf["size"][wf]
    R["RAW_flip"] = reading("RAW on the flipped series", np.ones(wf.sum()), -rw, xw, days)
    R["P2"] = reading("P2 KEEL on the flipped series", Sf, -rw, xw, days, float(Sf.mean()))
    R["F_flip"] = reading("F_flip at P2's own mean", np.full(wf.sum(), float(Sf.mean())), -rw, xw, days)
    res["p2"] = {"s_bar_flip": float(Sf.mean()), "trust_on_wf_flip": float((kf["trust"][wf] > 0).mean())}
    res["split"] = {"keel_minus_raw": R["KEEL"]["net"] - R["RAW"]["net"], "leverage": (s_bar - 1.0) * R["RAW"]["net"],
                    "timing": R["KEEL"]["timing"], "timing_ft": R["FT"]["timing"], "timing_lo": R["LO"]["timing"],
                    "interaction": R["KEEL"]["timing"] - R["FT"]["timing"] - R["LO"]["timing"]}
    for k in ("KEEL", "FT", "LO", "M", "P1"):
        res["nulls"][k] = null_line(sizes[k], rw)
    res["nulls"]["P2"] = null_line(Sf, -rw)
    res["mean_unit_cost"] = float(unit_cost.mean())
    return res


def report(both, doc_keel):
    P, S = both["PURE"], both["SAVED"]
    say(f"KEEL's doc row (09-24, another master build): avg size {doc_keel.get('avg_size')}, trust-on {doc_keel.get('trust_on')} - a figure, not a parity target (A2)")
    say(f"{'':10s}{'PURE (primary)':>62s} | {'SAVED (roll defect)':>40s}")
    say(f"  WF trades {P['n_wf']:,} of {P['n_all']:,} | {S['n_wf']:,} of {S['n_all']:,}; s_bar {P['s_bar']:.3f} (sd {P['s_sd']:.3f}) | {S['s_bar']:.3f} ({S['s_sd']:.3f}); "
        f"trust on {P['trust_on_wf']*100:.1f}% | {S['trust_on_wf']*100:.1f}%; shade {P['shade_share_wf']*100:.1f}% | {S['shade_share_wf']*100:.1f}%; mean unit cost ${P['mean_unit_cost']:.2f}")

    def line(x):
        tm = f" timing {x['timing']:+10,.0f}" if "timing" in x else " " * 18
        return (f"ROC {x['roc']:6.1f} / DD5 {x['dd5']:>8,.0f}{'*' if x['one_episode'] else ' '} net {x['net']:>11,.0f} ({x['usd_year']:>9,.0f}/yr) "
                f"Sort {x['sortino']:5.2f}{tm}")
    say("WITH COSTS (as computed; A10)                       * = driven by one episode")
    for k in ("RAW", "KEEL", "F", "FT", "LO", "M", "P1", "RAW_flip", "P2", "F_flip"):
        say(f"  {k:8s} {P['readings'][k]['name'][:30]:30s} {line(P['readings'][k])} | {line(S['readings'][k])}")
    say("WITHOUT COSTS (approximate gross: the plugin's 0.783 pt x $2 x micros added back at each reading's size; rolls not added back)")
    for k in ("RAW", "KEEL", "F", "FT", "LO", "M", "P1"):
        say(f"  {k:8s} {'':30s} {line(P['gross'][k])} | {line(S['gross'][k])}")
    for lab, x in (("PURE", P), ("SAVED", S)):
        sp, m = x["split"], x["momentum"]
        say(f"{lab} KIM-TSE-WALD SPLIT: KEEL - RAW {sp['keel_minus_raw']:+,.0f} = leverage {sp['leverage']:+,.0f} + timing {sp['timing']:+,.0f}; "
            f"timing = fixed tilts {sp['timing_ft']:+,.0f} + learned {sp['timing_lo']:+,.0f} + interaction {sp['interaction']:+,.0f}")
        say(f"{lab} NAGEL: M a {m['a']:.3f} b {m['b']:+.3f} (mean+sd matched: {m['mean_and_sd_matched']}); P1 a {m['a_p1']:.3f}; corr(KEEL size dev, z) "
            f"{m['corr_keel_dev_z']:+.3f}; OLS slope of KEEL size on z {m['ols_keel_on_z']:+.3f}; z = 0 on {m['z_zero_share_wf']*100:.1f}% of WF trades")
        for k, v in x["nulls"].items():
            say(f"  {lab} null {k:5s} timing {v['timing']:+11,.0f}: plain p95 {v['plain_p95']:+11,.0f} (pct {v['plain_pct']:5.1f}) | "
                f"20-trade blocks p95 {v['block_p95']:+11,.0f} (pct {v['block_pct']:5.1f})")
    say("A3: KEEL's design (schedule, fast window, shade, tilts) was chosen 09-06..09-09 on NOISE / ORB / ENGU-Q NQ walks over 2010-26 - "
        "IN-SAMPLE for its design on #424's WF years (out-of-family: DIP was not used)")


# ------------------------------------------------------------------ the real run
def run():
    if lf_sha(NOTE) != NOTE_SHA:
        sys.exit(f"refused: the note's LF sha256 {lf_sha(NOTE)} is not the registered {NOTE_SHA}")
    sys.path.insert(0, SHARED)
    import firebase_admin
    from firebase_admin import credentials, firestore
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine import ml_keel as ML
    say(f"augur_engine from {sys.modules['augur_engine'].__file__}; note LF {NOTE_SHA[:16]}")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(SHARED, "serviceAccount.json")))
    d = firestore.client().collection("users").document(UID).collection("runs").document(str(RUN)).get().to_dict()   # READ ONLY
    gv = d["gate_validate"]
    wf0, wf1 = gv["wf_range"]; lb = gv["lockbox_from"]
    t0 = time.time()
    arr = load_master_arrays(find_master(d["instrument"], d["timeframe"], SESSION[d["data_source"]], d["data_source"]),
                             date_from=d.get("date_from"), date_to=d.get("date_to"))
    lists = {k: load_list(p, arr) for k, p in LISTS.items()}
    wall = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    sv = lists["SAVED"]
    pre = np.array([wall[t[0]] < pd.Timestamp(lb) for t in sv])
    n_pre, net_pre = int(pre.sum()), float(np.asarray([t[2] for t in sv])[pre].sum())
    doc = gv["ungated_pre"]
    ok = n_pre == int(doc["num_trades"]) and abs(net_pre - doc["total_pnl"]) <= 0.005 * max(1.0, abs(doc["total_pnl"]))
    say(f"#{RUN} {d['strategy']} {d['instrument']} {d['timeframe']} {d['date_from']}..{d['date_to']}; WF {wf0}..{wf1}; lists PURE {len(lists['PURE']):,} / "
        f"SAVED {len(sv):,} trades; A1 guard (SAVED's pre-lockbox block vs the doc's ungated pre): {'MATCH' if ok else 'MISMATCH'} ({n_pre} vs {doc['num_trades']}) "
        f"[{time.time()-t0:.0f}s]")
    if not ok:
        sys.exit("refused: the saved list does not reproduce the doc's ungated pre block - nothing computed")
    both = {}
    for k, T in lists.items():
        t1 = time.time()
        both[k] = decompose(arr, T, wf0, wf1, ML)
        say(f"  {k} decomposed in {time.time()-t1:.0f}s")
    report(both, gv.get("keel") or {})
    os.makedirs(OUT, exist_ok=True)
    out = {"run": RUN, "note_sha256_lf": NOTE_SHA, "harness_sha256_lf": lf_sha(__file__), "wf": [wf0, wf1], "lockbox_from_not_read": lb,
           "lists": {k: {"path": p, "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()} for k, p in LISTS.items()},
           "doc_keel": {k: (gv.get("keel") or {}).get(k) for k in ("version", "avg_size", "trust_on")}, **both}
    p = os.path.join(OUT, "keel_decomp_424.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1, default=float)
    say(f"-> {p}")


# ------------------------------------------------------------------ selftest (fakes only: no Firestore, no master)
def selftest():
    rng = np.random.default_rng(1)
    r = rng.normal(0.1, 1.0, 500); s = np.clip(1.25 + 0.4 * rng.normal(size=500), 0.5, 2.0)
    sb = s.mean()
    assert abs((np.sum(s * r) - np.sum(r)) - ((sb - 1) * np.sum(r) + timing(s, r, sb))) < 1e-9          # leverage + timing identity
    days = pd.bdate_range("2020-01-01", periods=500)
    a1, a2 = stats(r, days), stats(1.25 * r, days)
    assert abs(a1["roc"] - a2["roc"]) < 1e-9 and abs(a1["sortino"] - a2["sortino"]) < 1e-9             # a constant size cancels
    E = np.arange(0, 3000, 10); X = E + rng.integers(1, 40, len(E)); rr = rng.normal(size=len(E))
    z = momentum_z(E, X, rr)
    for j in (150, 200, 250):                                                                          # causal: only exits before entry
        rr2 = rr.copy(); rr2[X >= E[j]] += 100.0
        assert momentum_z(E, X, rr2)[j] == z[j], "momentum_z read a trade that had not exited"
    k_first = int(np.argmax(np.searchsorted(np.sort(X), E, side="left") >= MIN_RESOLVED))
    assert (z[:k_first] == 0).all() and z[k_first] != 0                                               # warm-up = 100 resolved trades
    zz = rng.normal(size=2000)
    a, b, ok = calibrate(zz, 1.25, 0.3)
    w = clip_sizes(a, b, zz)
    assert ok and b >= 0 and abs(w.mean() - 1.25) < 1e-6 and abs(w.std() - 0.3) < 1e-4
    a, b, ok = calibrate(zz, 1.25, 5.0)
    assert not ok and b == B_FALLBACK and abs(clip_sizes(a, b, zz).mean() - 1.25) < 1e-6
    a1_ = solve_a(-0.3, zz, 1.25); assert abs(clip_sizes(a1_, -0.3, zz).mean() - 1.25) < 1e-6       # P1's a is re-solved
    nl = null_line(np.full(300, 1.25), rng.normal(size=300))
    assert nl["timing"] == 0.0
    w = np.arange(45, dtype=float); bl = [w[c:c + BLOCK] for c in range(0, len(w), BLOCK)]
    assert [len(x) for x in bl] == [20, 20, 5]                                                         # the partial last block is kept
    # load_list: exact bar-start matching, refusal on a miss
    import tempfile
    idx = pd.date_range("2020-01-02 09:30", periods=50, freq="5min", tz="US/Eastern")
    arrs = {"index": idx}
    fd, p = tempfile.mkstemp(suffix=".csv"); os.close(fd)
    pd.DataFrame({"entry": ["2020-01-02 09:35:00", "2020-01-02 09:30:00"], "exit": ["2020-01-02 10:00:00", "2020-01-02 09:50:00"],
                  "pnl": [1.0, -2.0]}).to_csv(p, index=False)
    assert load_list(p, arrs) == [(0, 4, -2.0), (1, 6, 1.0)]
    pd.DataFrame({"entry": ["2020-01-02 09:33:00"], "exit": ["2020-01-02 10:00:00"], "pnl": [1.0]}).to_csv(p, index=False)
    try:
        load_list(p, arrs); raise AssertionError("a time off the bar grid was accepted")
    except SystemExit:
        pass
    os.remove(p)
    say("selftest ok: leverage/timing identity, ROC scale-free, causal momentum z + 100-trade warm-up, calibration (both, fallback, "
        "P1 re-solve), null, partial block kept, exact bar mapping + refusal")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"selftest": selftest, "run": run}.get(cmd, lambda: sys.exit("usage: r28_keel_decomp.py selftest | run"))()
