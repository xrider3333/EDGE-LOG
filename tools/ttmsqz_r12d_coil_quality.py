"""TTM Squeeze round 12d - does the SHAPE of the coil predict the trade, not just the fire?

Every version of this family treats a squeeze as a boolean and a fire as a fire: once the
bands go inside the channel it is "on", once they come back out it "fires", and every fire
is scored the same way. A trader does not read it that way - a three-bar squeeze that snaps
after a trend is a different setup from a twenty-bar squeeze sitting in a quiet range, and a
fire out of a coil that was still tightening is not the same release as one out of a coil
that had already started to loosen. This round measures five things about the COIL ITSELF,
on the crown's own 359 trades (ES 30m RTH, kc 1.5 / stop 1.5 ATR / eod 1 / gate 60m sq_on /
gate_len 20 / length 20 / bb 2.0 / min squeeze 1 / open fill / fade-1 exit):

  1. COIL LENGTH    - bars the base squeeze ran before the fire.
  2. COIL TIGHTNESS - the deepest compression reached during the coil, and the compression
                       still showing on the fire bar itself.
  3. COIL DIRECTION - was the compression ratio still falling into the fire (still
                       tightening) or already rising (already loosening) in its last bars.
  4. COIL RANGE     - the height of the squeeze range, in ATR - a narrow coil in a wide-ATR
                       market is not the same read as a narrow coil in a quiet one.
  5. WHAT CAME BEFORE - the move into the coil, in ATR, and whether the fire continues it
                       or fights it.

Every feature is read off the DECISION bar (the fire bar itself, one bar before the fill),
using only sq_on/mom/ratio/ATR values the engine itself already computes causally at that
bar - nothing here touches a trade's own exit or anything after its entry.

THE DISCIPLINE (this shop has burned itself on exactly this kind of per-trade slicing
before, see tools/ttmsqz_round6_parts.py and tools/ttmsqz_r12e_overnight.py): the
pre-lockbox trades are split 60/40 by time into a discovery half and a holdout half.
Thresholds are read off DISCOVERY ONLY, then frozen and applied unchanged to holdout and
to the lockbox. Every rule is reported on all three side by side. A rule that lives only in
discovery is labelled an artifact, not a finding. Buckets under ~40 trades are called
untestable, not promising. Nothing here is crowned, queued for validate, or pushed.

Log: tools/data/ttmsqz_r12d_coil_quality.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
r8 = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("r8", os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py")))
r8.__spec__.loader.exec_module(r8)
r6 = r8.r6
ttm3 = r8.ttm3
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r12d_coil_quality.txt")
CROWN = r8.CROWN          # length 20, bb 2.0, kc 1.5, min_sq_bars 1, entry open, fade-1, stop 1.5, eod 1, gate 60m sq_on
MIN_TESTABLE = 40         # this shop's rule of thumb: fewer trades than this = untestable


# ---------------------------------------------------------------------------------------
# feature computation - everything below is READ AT THE FIRE (decision) BAR, dbar = eb - 1.
# The engine (augur_strategies/TTMSQZ_3_0.py run_backtest) computes fire[u] from sq_on[u]/
# run_len[u-1] and fills at u+1's open, so dbar = eb-1 is exactly the bar the engine itself
# used to decide the trade - nothing here reaches past it.
# ---------------------------------------------------------------------------------------
def compute_features(df, t):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    length, bb_mult, kc_mult = CROWN["length"], CROWN["bb_mult"], CROWN["kc_mult"]
    sq_on, mom, atr = ttm3.squeeze_indicators(h, l, c, length, bb_mult, kc_mult)
    n = len(c)
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    basis = pd.Series(c).rolling(length).mean()
    dev = pd.Series(c).rolling(length).std(ddof=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((bb_mult * dev) / (kc_mult * pd.Series(atr))).to_numpy()

    dbar = t["eb"].values - 1
    side = t["side"].values
    m = len(dbar)
    k = run_len[dbar - 1]                       # 1. coil length: consecutive sq_on bars ending at dbar-1
    ratio_fire = ratio[dbar]                     # 2b. compression ratio on the fire bar itself (>=~1, just broke out)
    coil_min_ratio = np.full(m, np.nan)           # 2a. deepest compression reached during the coil
    coil_range_atr = np.full(m, np.nan)           # 4. squeeze-range height / ATR at the fire bar
    slope = np.full(m, np.nan)                   # 3. ratio trend in the coil's last bars (<=0 falling, >0 rising)
    prior_atr = np.full(m, np.nan)                # 5. move into the coil, in ATR (signed)
    N = 10                                        # lookback window for "what came before", in bars
    for idx in range(m):
        i, kk = int(dbar[idx]), int(k[idx])
        a = max(0, i - kk)                        # coil start = first sq_on bar of the run
        if i > a:
            coil_min_ratio[idx] = np.nanmin(ratio[a:i])
            if atr[i] > 0 and np.isfinite(atr[i]):
                coil_range_atr[idx] = (h[a:i].max() - l[a:i].min()) / atr[i]
        if kk >= 2:
            w = min(3, kk - 1)
            slope[idx] = ratio[i - 1] - ratio[i - 1 - w]
        a0 = max(0, a - N)
        aatr = atr[max(0, a - 1)]
        if a > a0 and np.isfinite(aatr) and aatr > 0:
            prior_atr[idx] = (c[a] - c[a0]) / aatr

    out = t.copy()
    out["k"] = k
    out["ratio_fire"] = ratio_fire
    out["coil_min_ratio"] = coil_min_ratio
    out["coil_range_atr"] = coil_range_atr
    out["slope"] = slope
    out["prior_atr"] = prior_atr
    with np.errstate(invalid="ignore"):
        out["agrees"] = np.where(np.isfinite(prior_atr), (np.sign(prior_atr) == side).astype(float), np.nan)
    return out


def stats(usd):
    if not len(usd):
        return None
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    return dict(n=len(usd), net=float(usd.sum()), pf=(gw / gl) if gl > 0 else 99.0, dd=dd,
                wr=float(100 * (usd > 0).mean()) if len(usd) else float("nan"))


def perm_p(usd, mask, n=5000, seed=42):
    mask = np.asarray(mask, bool)
    if mask.sum() < 2 or (~mask).sum() < 2:
        return float("nan")
    rng = np.random.default_rng(seed)
    obs = abs(usd[mask].mean() - usd[~mask].mean())
    lab = mask.copy()
    hits = 0
    for _ in range(n):
        rng.shuffle(lab)
        if abs(usd[lab].mean() - usd[~lab].mean()) >= obs:
            hits += 1
    return hits / n


def emit_bucket_table(L, title, values, usd, edges, labels):
    """Descriptive only, DISCOVERY trades - shows the shape before any rule is frozen."""
    L.append("")
    L.append("  %s (discovery only, descriptive)" % title)
    L.append("  %-22s %5s %6s %11s %10s %6s" % ("bucket", "n", "PF", "net $", "$/trade", "WR%"))
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        msk = (values >= lo) & (values < hi) if hi < np.inf else (values >= lo)
        s = stats(usd[msk])
        if s and s["n"] > 0:
            L.append("  %-22s %5d %6.2f %11s %10s %6.1f" % (
                lab, s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]),
                "{:,.0f}".format(s["net"] / s["n"]), s["wr"]))
        else:
            L.append("  %-22s %5d      -           -          -      -" % (lab, 0))


def main():
    L = ["TTM SQUEEZE ROUND 12d - the QUALITY of the coil, not just the fire   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "crown cell: ES 30m RTH, kc 1.5 / stop 1.5 ATR / eod 1 / gate 60m sq_on len 20 / length 20 / bb 2.0 /",
         "  min squeeze 1 / open fill / fade-1 exit -- 359 trades, $51,709, PF 2.12, DD $3,740, lockbox $4,992 PF 2.22",
         "window %s..%s, lockbox from %s, 0.363 pts/RT, 50 dollars/pt, one contract" % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM),
         "Discovery = first 60%% of pre-lockbox trades by time. Thresholds are read off discovery only, then",
         "frozen and applied unchanged to holdout and lockbox. Nothing here is crowned."]
    print("\n".join(L), flush=True)

    df = r6.load("ES", "30m", "RTH")
    t = r8.run_ttm(df, CROWN, "ES")
    assert len(t) == 359, "trade count drifted from the quoted crown (%d != 359) - stop and check" % len(t)
    feat = compute_features(df, t)
    usd = feat["usd"].values

    lb_mask = (feat["date"] >= pd.Timestamp(r6.LB_FROM)).to_numpy()
    pre_idx = np.flatnonzero(~lb_mask)             # trades already in time order (engine appends chronologically)
    cut = int(round(len(pre_idx) * 0.6))
    disc_mask = np.zeros(len(feat), bool); disc_mask[pre_idx[:cut]] = True
    hold_mask = np.zeros(len(feat), bool); hold_mask[pre_idx[cut:]] = True
    L.append("")
    L.append("  %d trades total: discovery %d, holdout %d, lockbox %d" % (
        len(feat), disc_mask.sum(), hold_mask.sum(), lb_mask.sum()))
    L.append("  (lockbox n=%d is well under the %d-trade testability floor this shop uses - shown for the record, not as evidence)"
             % (lb_mask.sum(), MIN_TESTABLE))

    # ---- descriptive bucket tables, discovery only (fulfils "in buckets" for length/tightness/range) ----
    d = feat[disc_mask]
    du = usd[disc_mask]
    emit_bucket_table(L, "1. COIL LENGTH (bars in the base squeeze before the fire)", d["k"].to_numpy(), du,
                      [1, 3, 8, 17, np.inf], ["1-2 bars", "3-7 bars", "8-16 bars", "17+ bars"])
    emit_bucket_table(L, "2a. COIL TIGHTNESS (deepest compression ratio reached in the coil, lower = tighter)",
                      d["coil_min_ratio"].to_numpy(), du,
                      [0, 0.65, 0.85, 1.0], ["<=0.65 (deep)", "0.65-0.85 (mid)", "0.85-1.0 (barely on)"])
    emit_bucket_table(L, "2b. COIL TIGHTNESS AT THE FIRE (ratio on the fire bar itself, how hard it broke)",
                      d["ratio_fire"].to_numpy(), du,
                      [1.0, 1.05, 1.2, np.inf], ["1.00-1.05 (narrow break)", "1.05-1.20 (mid)", "1.20+ (wide break)"])
    emit_bucket_table(L, "4. COIL RANGE (squeeze-range height / ATR at the fire bar)",
                      d["coil_range_atr"].to_numpy(), du,
                      [0, 1.75, 3.7, np.inf], ["<1.75 ATR (narrow)", "1.75-3.7 ATR (mid)", "3.7+ ATR (wide)"])

    # ---- freeze thresholds on discovery only, then build one binary rule per topic ----
    med_k = float(np.median(d["k"]))
    med_minratio = float(np.median(d["coil_min_ratio"]))
    med_firel = float(np.median(d["ratio_fire"]))
    med_range = float(np.median(d["coil_range_atr"]))
    L.append("")
    L.append("  frozen thresholds (discovery medians): coil length %.0f bars, min ratio %.3f, fire ratio %.3f, range %.2f ATR"
             % (med_k, med_minratio, med_firel, med_range))

    k = feat["k"].to_numpy()
    minr = feat["coil_min_ratio"].to_numpy()
    firer = feat["ratio_fire"].to_numpy()
    rng_ = feat["coil_range_atr"].to_numpy()
    slope = feat["slope"].to_numpy()
    agrees = feat["agrees"].to_numpy()

    have_slope = np.isfinite(slope)
    have_prior = np.isfinite(agrees)
    L.append("  coil direction is undefined for a 1-bar coil (k=1): %d of 359 trades excluded from rule 3"
             % int((~have_slope).sum()))
    L.append("  prior-move window unavailable at the very start of the tape: %d of 359 trades excluded from rule 6"
             % int((~have_prior).sum()))

    RULES = [
        ("1. long coil (>= %.0f bars)" % med_k, k >= med_k, np.ones(len(feat), bool)),
        ("2a. deep coil (min ratio <= %.3f)" % med_minratio, minr <= med_minratio, np.ones(len(feat), bool)),
        ("2b. wide breakout bar (fire ratio > %.3f)" % med_firel, firer > med_firel, np.ones(len(feat), bool)),
        ("3. still tightening into the fire (ratio falling)", slope <= 0, have_slope),
        ("4. narrow coil range (<= %.2f ATR)" % med_range, rng_ <= med_range, np.ones(len(feat), bool)),
        ("5. fire agrees with the move into the coil", agrees == 1.0, have_prior),
    ]

    HDRTXT = "  %-46s %-7s   %s" % ("", "", "------- discovery -------   -------- holdout --------   -------- lockbox --------")
    HDR = "  %-46s %-7s %5s %6s %9s %8s  %5s %6s %9s %8s  %5s %6s %9s %8s %7s" % (
        "rule", "shape", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "perm p")
    L.append("")
    L.append(HDRTXT)
    L.append(HDR)

    def emit(name, shape, u_d, u_h, u_l, p):
        cells = []
        for u in (u_d, u_h, u_l):
            s = stats(u)
            if s:
                cells += ["%5d" % s["n"], "%6.2f" % min(s["pf"], 99), "%9s" % "{:,.0f}".format(s["net"]),
                          "%8s" % "{:,.0f}".format(s["dd"])]
            else:
                cells += ["%5s" % "-", "%6s" % "-", "%9s" % "-", "%8s" % "-"]
        L.append("  %-46s %-7s %s %s %s %s  %s %s %s %s  %s %s %s %s %7s" % (
            name, shape, *cells, ("%.4f" % p) if p == p else "n/a"))
        print(L[-1], flush=True)

    base_d, base_h, base_l = usd[disc_mask], usd[hold_mask], usd[lb_mask]
    emit("ALL TRADES (the crown, unchanged)", "base", base_d, base_h, base_l, float("nan"))

    verdicts = []
    for name, flag, universe in RULES:
        flag = np.asarray(flag, bool) & universe
        rest = universe & ~flag
        dm, hm, lm = disc_mask & universe, hold_mask & universe, lb_mask & universe
        p_disc = perm_p(usd[dm], flag[dm])
        emit(name, "select", usd[dm & flag], usd[hm & flag], usd[lm & flag], p_disc)
        tilt = np.where(flag, 1.5 * usd, usd)
        emit("   same rule as a 1.5x size tilt", "tilt", tilt[dm], tilt[hm], tilt[lm], float("nan"))

        # verdict bookkeeping: does the gap in mean $/trade point the SAME way in all three slices,
        # with discovery AND holdout both resting on at least MIN_TESTABLE trades per side?
        def gap(mask_slice):
            f, r = usd[mask_slice & flag], usd[mask_slice & rest]
            if len(f) == 0 or len(r) == 0:
                return float("nan")
            return float(f.mean() - r.mean())
        gd, gh, gl = gap(disc_mask), gap(hold_mask), gap(lb_mask)
        testable_d = (flag & dm).sum() >= MIN_TESTABLE and (rest & dm).sum() >= MIN_TESTABLE
        testable_h = (flag & hm).sum() >= MIN_TESTABLE and (rest & hm).sum() >= MIN_TESTABLE
        same_sign = (gd == gd) and (gh == gh) and (np.sign(gd) == np.sign(gh)) and (np.sign(gd) != 0)
        survives = testable_d and testable_h and same_sign and p_disc == p_disc and p_disc < 0.05
        verdicts.append((name, p_disc, gd, gh, gl, testable_d, testable_h, survives))

    n_rules = len(RULES)
    bonf = 0.05 / n_rules
    L.append("")
    L.append("MULTIPLE COMPARISONS, stated before anyone reads a p-value: %d rules were tested here, so the" % n_rules)
    L.append("smallest honest threshold is 0.05 / %d = %.4f. Read the discovery p-value against THAT, not 0.05."
             % (n_rules, bonf))

    L.append("")
    L.append("VERDICT - survives only if the mean-$/trade gap points the same direction in discovery AND holdout,")
    L.append("both buckets clear the %d-trade testability floor, and discovery clears the raw p<0.05 bar (before" % MIN_TESTABLE)
    L.append("the Bonferroni correction above, which is the stricter bar a real finding should still be judged by):")
    any_survive = False
    for name, p_disc, gd, gh, gl, td, th, surv in verdicts:
        tag = "SURVIVES (discovery+holdout agree, both testable)" if surv else "does not survive"
        if surv:
            any_survive = True
            if p_disc >= bonf:
                tag += " -- but discovery p=%.4f misses the Bonferroni bar %.4f: treat as a lead, not a finding" % (p_disc, bonf)
        L.append("  %-46s disc gap %s$/trade  hold gap %s$/trade  lb gap %s$/trade  -> %s" % (
            name, "{:+,.0f}".format(gd) if gd == gd else "n/a",
            "{:+,.0f}".format(gh) if gh == gh else "n/a",
            "{:+,.0f}".format(gl) if gl == gl else "n/a", tag))
    L.append("")
    if any_survive:
        L.append("At least one rule survived discovery+holdout agreement on this pass - see above. None of it is a")
        L.append("crowning bar; the shop's bar for that is a fenced Auto-Validate, not a scan like this one.")
    else:
        L.append("NOTHING SURVIVES. Every rule either flips sign between discovery and holdout, or rests on a bucket")
        L.append("under the %d-trade floor, or both. This matches every previous structure hunt in this family:" % MIN_TESTABLE)
        L.append("the compression CHECK (hourly squeeze on/off, already in production) carries the real signal; how")
        L.append("the coil got there does not add anything measurable on 359 trades.")
    r8._lines_to(L, LOG)
    print("\nlog ->", LOG)


if __name__ == "__main__":
    main()
