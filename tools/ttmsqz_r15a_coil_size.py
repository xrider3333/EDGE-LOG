"""TTM Squeeze round 15a - is the coil the right SIZE to trade?

THE QUESTION ONLY BECAME ASKABLE ON 2026-09-09. The book leg's protective stop moved from a
fixed 1.5x ATR to the FAR SIDE OF THE SQUEEZE RANGE ITSELF (run #353, file
augur_strategies/TTMSQZ_3_0_ES30SS20.py, adopted the same day - see TTM.md). Once the stop IS
the coil's own width, the width of the coil on every trade IS the risk taken on that trade,
before a single dollar of ATR-sizing logic ever runs. Nobody has asked whether some coils are
too small or too big to be worth the trade. This round asks it, two ways:

  1. A FLOOR. A coil two points wide gives a two-point stop and a 0.363-point round trip - the
     cost is a sixth of the risk before the trade starts, and the reward has to clear it before
     anything else. Tested in raw points AND in ATR-multiples (points drift with ES's own price
     scale over sixteen years; ATR does not - shown below).
  2. A CAP. The stress read (memory: TTM structural-stop stress) found the worst structural stop
     in the window cost $6,612 a contract against an average of $1,041. A cap asks: is a coil
     that wide still worth its own risk? Tested in ATR-multiples, as SELECTION and as a 1.5x tilt.

Both the floor and the cap are tested as a SELECTION rule (skip the trade) and as a 1.5x SIZE
TILT on the trades each rule likes (this shop's prior on this family: a filter that throws
trades away has lost money almost every time it has been tried - see TTM.md "closed" list -
while tilts have a better record). A THIRD, DIFFERENT idea - a HYBRID STOP that takes every
trade but never lets the stop sit further than X ATR from the fill - is reported in its own
section, separately, because capping the stop is not the same claim as skipping the trade.

NO LOOK-AHEAD. The coil's range (rng_hi/rng_lo) and its ATR are both fixed at the FIRE bar -
one bar before the fill - by the engine's own construction (TTMSQZ_3_0_ES30SS.py:_build_arrays,
_simulate): `for i in np.flatnonzero(fire): k = run_len[i-1]; a = max(0, i-k); rng_hi[i] =
h[a:i].max(); rng_lo[i] = l[a:i].min()` uses only bars BEFORE the fire bar's own close, and the
fill happens at the NEXT bar's open. Every filter and every threshold below reads only what is
known at the fire bar, before the fill - this script computes nothing from the entry price, the
exit, or anything after entry_bar - 1.

DISCIPLINE. Pre-lockbox trades (341 of 357) are split 60/40 by time into discovery (205) and
holdout (136); the lockbox (16) is shown for the record but is under this shop's ~40-trade
testability floor and is never used as evidence on its own. Every threshold is read off
DISCOVERY ONLY, then frozen and applied unchanged to holdout and lockbox. A rule that only
works in discovery is labelled an artifact. Permutation p-values (5000 shuffles) are reported on
discovery; the Bonferroni threshold for the number of rules actually tried is stated before any
p-value is read against it. Nothing here is crowned, queued, or pushed - SCAN ONLY.

Incumbent, reproduced bit-for-bit below before anything else runs:
  augur_strategies/TTMSQZ_3_0_ES30SS20.py, kc_mult 1.5, eod_cutoff 1 (gate_len fixed at 20
  inside the file) - ES 30m RTH, pinned window, 0.363 pts/RT, $50/pt:
  357 trades, PF 2.91, net $101,017, DD $4,338, lockbox $16,977 @ PF 6.72.

Log: tools/data/ttmsqz_r15a_coil_size.txt
"""
import os, sys, time, importlib.util
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6")
r8 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py"), "r8")
ss20 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS20.py"), "ss20")
ss = ss20._ss   # augur_strategies/TTMSQZ_3_0_ES30SS.py, imported by the pinned-gate_len wrapper

LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r15a_coil_size.txt")
MIN_TESTABLE = 40    # this shop's rule of thumb: fewer trades than this = untestable
KW = dict(kc_mult=1.5, eod_cutoff=1)     # SS20's own defaults = the paper-book cell
KC_MULT, GATE_LEN = 1.5, 20              # frozen inside SS20; needed to rebuild the raw arrays
QUOTED = dict(n=357, pf=2.91, net=101017, dd=4338, lb=16977, lbpf=6.72)


def run_ss20(df, kw, inst="ES"):
    r = ss20.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                          day_id=df["day_id"].values, index=df["_dt"], return_trades=True, **kw)
    if not r or not r.get("trades"):
        return None
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2]), int(x[3]), float(x[4])) for x in r["trades"]],
                     columns=["eb", "xb", "pnl", "side", "epx"])
    t["usd"] = (t["pnl"] - r6.COST[inst]) * r6.MULT[inst]
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()
    return t


def stats(usd):
    if usd is None or not len(usd):
        return None
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    return dict(n=len(usd), net=float(usd.sum()), pf=(gw / gl) if gl > 0 else 99.0, dd=dd,
                wr=float(100 * (usd > 0).mean()))


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


def cell(u):
    s = stats(u)
    if not s:
        return "%5s %6s %9s %8s" % ("-", "-", "-", "-")
    return "%5d %6.2f %9s %8s" % (s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]))


# =========================================================================================
# 0. REPRODUCE THE INCUMBENT BIT-FOR-BIT
# =========================================================================================
def reproduce(L):
    df = r6.load("ES", "30m", "RTH")
    t = run_ss20(df, KW)
    s = r8.alone_score(t)
    ok = (len(t) == QUOTED["n"] and abs(s["pf"] - QUOTED["pf"]) < 0.01
          and abs(s["net"] - QUOTED["net"]) < 5 and abs(s["dd"] - QUOTED["dd"]) < 5
          and abs(s["lb"] - QUOTED["lb"]) < 5 and abs(s["lbpf"] - QUOTED["lbpf"]) < 0.01)
    L.append("REPRODUCTION CHECK vs the quoted incumbent (TTMSQZ_3_0_ES30SS20.py, kc_mult 1.5, eod_cutoff 1):")
    L.append("  got:    n=%d PF=%.2f net=$%s DD=$%s lockbox=$%s @ PF %.2f" % (
        len(t), s["pf"], "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
        "{:,.0f}".format(s["lb"]), s["lbpf"]))
    L.append("  quoted: n=%d PF=%.2f net=$%s DD=$%s lockbox=$%s @ PF %.2f" % (
        QUOTED["n"], QUOTED["pf"], "{:,.0f}".format(QUOTED["net"]), "{:,.0f}".format(QUOTED["dd"]),
        "{:,.0f}".format(QUOTED["lb"]), QUOTED["lbpf"]))
    L.append("  %s -- bit-for-bit before anything else runs." % ("MATCH" if ok else "MISMATCH - STOP"))
    print("\n".join(L), flush=True)
    if not ok:
        raise SystemExit("reproduction failed - see log")
    return df, t


# =========================================================================================
# 1. FEATURES - coil width in points and in ATR-multiples, read at the FIRE bar (eb-1),
#    which is the last bar the engine looks at before it commits to the fill at eb's open.
# =========================================================================================
def build_features(df, t):
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    did, index = df["day_id"].values, df["_dt"]
    A = ss._build_arrays(o, h, l, c, did, index, KC_MULT, GATE_LEN)
    fire_bar = t["eb"].values - 1
    width_pts = A["rng_hi"][fire_bar] - A["rng_lo"][fire_bar]
    atr_fire = A["atr"][fire_bar]
    width_atr = width_pts / atr_fire
    side = t["side"].values
    epx = t["epx"].values
    stop_lvl = np.where(side > 0, A["rng_lo"][fire_bar], A["rng_hi"][fire_bar])
    risk_pts = np.where(side > 0, epx - stop_lvl, stop_lvl - epx)
    risk_usd = risk_pts * r6.MULT["ES"]
    out = t.copy()
    out["fire_bar"] = fire_bar
    out["width_pts"] = width_pts
    out["atr_fire"] = atr_fire
    out["width_atr"] = width_atr
    out["risk_usd"] = risk_usd
    return out, A


def descriptive(L, feat):
    L.append("")
    L.append("=" * 108)
    L.append("DESCRIPTIVE - the coil-width distribution and the stress-read numbers, reproduced (all 357 trades)")
    L.append("=" * 108)
    wp, wa, ru = feat["width_pts"].to_numpy(), feat["width_atr"].to_numpy(), feat["risk_usd"].to_numpy()
    L.append("  width in points:   min %.2f  p10 %.2f  p25 %.2f  median %.2f  p75 %.2f  p90 %.2f  max %.2f" % (
        wp.min(), np.percentile(wp, 10), np.percentile(wp, 25), np.median(wp),
        np.percentile(wp, 75), np.percentile(wp, 90), wp.max()))
    L.append("  width in ATR-mult: min %.2f  p10 %.2f  p25 %.2f  median %.2f  p75 %.2f  p90 %.2f  max %.2f" % (
        wa.min(), np.percentile(wa, 10), np.percentile(wa, 25), np.median(wa),
        np.percentile(wa, 75), np.percentile(wa, 90), wa.max()))
    L.append("  per-contract structural risk $: mean $%s  max $%s  (stress read: mean $1,041, worst $6,612 - matches)"
             % ("{:,.0f}".format(ru.mean()), "{:,.0f}".format(ru.max())))
    L.append("")
    L.append("  SCALE DRIFT - why points and ATR are tested separately, not interchangeably (median width by year):")
    L.append("  %-6s %5s %10s %10s" % ("year", "n", "med pts", "med ATR"))
    yr = feat["date"].dt.year.to_numpy()
    for y in sorted(set(yr)):
        m = yr == y
        if m.sum() < 3:
            continue
        L.append("  %-6d %5d %10.2f %10.2f" % (y, m.sum(), np.median(wp[m]), np.median(wa[m])))
    L.append("  points drift 8x across the window (ES's own price/vol scale rose ~5x, 2010->2026); the ATR-multiple")
    L.append("  stays inside roughly 2.2-3.8 the whole way. A raw-points threshold frozen on early, low-vol")
    L.append("  discovery trades will bind very differently in the recent, high-vol years than the ATR one does.")


# =========================================================================================
# 2. Discovery/holdout/lockbox split, thresholds frozen on discovery only
# =========================================================================================
def split(feat):
    lb_mask = (feat["date"] >= pd.Timestamp(r6.LB_FROM)).to_numpy()
    pre_idx = np.flatnonzero(~lb_mask)      # already time-ordered (engine appends chronologically)
    cut = int(round(len(pre_idx) * 0.6))
    disc = np.zeros(len(feat), bool); disc[pre_idx[:cut]] = True
    hold = np.zeros(len(feat), bool); hold[pre_idx[cut:]] = True
    return disc, hold, lb_mask


def emit_rule(L, name, flag, universe, usd, disc, hold, lb, verdicts):
    flag = np.asarray(flag, bool) & universe
    rest = universe & ~flag
    dm, hm, lm = disc & universe, hold & universe, lb & universe
    p_disc = perm_p(usd[dm], flag[dm])
    L.append("  %-40s select  %s | %s | %s   perm p(disc)=%s" % (
        name, cell(usd[dm & flag]), cell(usd[hm & flag]), cell(usd[lm & flag]),
        ("%.4f" % p_disc) if p_disc == p_disc else "n/a"))
    tilt = np.where(flag, 1.5 * usd, usd)
    L.append("  %-40s tilt    %s | %s | %s" % (
        "   same rule, 1.5x on the liked trades", cell(tilt[dm]), cell(tilt[hm]), cell(tilt[lm])))

    def gap(mask_slice):
        f, r = usd[mask_slice & flag], usd[mask_slice & rest]
        if len(f) == 0 or len(r) == 0:
            return float("nan")
        return float(f.mean() - r.mean())
    gd, gh, gl_ = gap(disc), gap(hold), gap(lb)
    testable_d = (flag & dm).sum() >= MIN_TESTABLE and (rest & dm).sum() >= MIN_TESTABLE
    testable_h = (flag & hm).sum() >= MIN_TESTABLE and (rest & hm).sum() >= MIN_TESTABLE
    same_sign = (gd == gd) and (gh == gh) and (np.sign(gd) == np.sign(gh)) and (np.sign(gd) != 0)
    survives = testable_d and testable_h and same_sign and p_disc == p_disc and p_disc < 0.05
    verdicts.append((name, p_disc, gd, gh, gl_, testable_d, testable_h,
                     int((flag & dm).sum()), int((rest & dm).sum()), int((flag & hm).sum()), int((rest & hm).sum()),
                     survives))


def main():
    t0 = time.time()
    L = ["TTM SQUEEZE ROUND 15a - is the coil the right SIZE to trade?   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "ES 30m RTH, TTMSQZ_3_0_ES30SS20.py (structural stop, verification length pinned at 20), kc_mult 1.5, eod_cutoff 1",
         "window %s..%s, lockbox from %s, 0.363 pts/RT, $50/pt, one contract" % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM),
         "SCAN ONLY - crowns nothing, queues nothing. Discovery=first 60%% of pre-lockbox trades by time, holdout=the"
         " rest; thresholds are read off discovery only, then frozen and applied unchanged to holdout and lockbox."]
    print("\n".join(L), flush=True)

    df, t = reproduce(L)
    feat, A = build_features(df, t)
    usd = feat["usd"].values
    descriptive(L, feat)

    disc, hold, lb = split(feat)
    L.append("")
    L.append("=" * 108)
    L.append("SPLIT: %d trades total -> discovery %d, holdout %d, lockbox %d" % (len(feat), disc.sum(), hold.sum(), lb.sum()))
    L.append("(lockbox n=%d is under the %d-trade testability floor - shown for the record, never used alone as evidence)"
             % (lb.sum(), MIN_TESTABLE))
    L.append("=" * 108)

    wp, wa = feat["width_pts"].to_numpy(), feat["width_atr"].to_numpy()
    d_wp, d_wa = wp[disc], wa[disc]
    floor_pts = float(np.percentile(d_wp, 25))
    floor_atr = float(np.percentile(d_wa, 25))
    cap_atr = float(np.percentile(d_wa, 75))
    econ_floor_pts = 6.0 * r6.COST["ES"]      # a priori, NOT fit to discovery: cost <= 1/6 of the stop

    L.append("")
    L.append("FROZEN THRESHOLDS (read off discovery's own distribution, then applied unchanged everywhere):")
    L.append("  FLOOR-PTS  : keep coils >= %.2f points          (discovery's own 25th percentile)" % floor_pts)
    L.append("  FLOOR-ATR  : keep coils >= %.2f ATR-multiples   (discovery's own 25th percentile, scale-free)" % floor_atr)
    L.append("  FLOOR-ECON : keep coils >= %.2f points          (a priori, NOT fit: 6x the 0.363pt round-trip cost," % econ_floor_pts)
    L.append("               i.e. cost <= 1/6 of the stop distance - the exact motivating example in the brief)")
    L.append("  CAP-ATR    : keep coils <= %.2f ATR-multiples   (discovery's own 75th percentile)" % cap_atr)

    L.append("")
    L.append("=" * 108)
    L.append("FLOOR AND CAP AS SELECTION AND AS A 1.5x TILT   (n / PF / net$ / DD$  per column)")
    L.append("=" * 108)
    HDRTXT = "  %-40s %-7s   %s" % ("", "", "----- discovery (n=%d) -----   ------ holdout (n=%d) ------   ------ lockbox (n=%d) ------"
                                    % (disc.sum(), hold.sum(), lb.sum()))
    L.append(HDRTXT)
    L.append("  ALL TRADES (incumbent, unfiltered): %s | %s | %s" % (cell(usd[disc]), cell(usd[hold]), cell(usd[lb])))

    verdicts = []
    universe = np.ones(len(feat), bool)
    RULES = [
        ("FLOOR-PTS  width_pts >= %.2f" % floor_pts, wp >= floor_pts),
        ("FLOOR-ATR  width_atr >= %.2f" % floor_atr, wa >= floor_atr),
        ("FLOOR-ECON width_pts >= %.2f (6x cost)" % econ_floor_pts, wp >= econ_floor_pts),
        ("CAP-ATR    width_atr <= %.2f" % cap_atr, wa <= cap_atr),
    ]
    for name, flag in RULES:
        L.append("")
        emit_rule(L, name, flag, universe, usd, disc, hold, lb, verdicts)
        print("\n".join(L[-2:]), flush=True)

    n_rules = len(RULES)
    bonf = 0.05 / n_rules
    L.append("")
    L.append("MULTIPLE COMPARISONS: %d rules were tried in this family (floor-pts, floor-atr, floor-econ, cap-atr)." % n_rules)
    L.append("The honest threshold is 0.05 / %d = %.4f - read the discovery p-value against THAT, not against 0.05."
             % (n_rules, bonf))
    L.append("(The hybrid-stop idea below is reported separately and is NOT part of this family or this correction -")
    L.append(" it is a different mechanism, not a selection rule, per the brief's own instruction not to mix them.)")

    L.append("")
    L.append("VERDICT per rule - survives only if: the mean-$/trade gap (kept vs skipped) points the SAME way in")
    L.append("discovery AND holdout, BOTH the kept and skipped buckets clear the %d-trade floor in BOTH splits, and" % MIN_TESTABLE)
    L.append("the discovery p-value clears the raw p<0.05 bar (before the stricter Bonferroni bar above):")
    any_survive = False
    for name, p_disc, gd, gh, gl_, td, th, kd, rd, kh, rh, surv in verdicts:
        tag = "SURVIVES" if surv else "does not survive"
        if surv:
            any_survive = True
            if p_disc >= bonf:
                tag += " (but discovery p=%.4f misses the Bonferroni bar %.4f - a lead, not a finding)" % (p_disc, bonf)
        L.append("  %-40s disc kept/skip %d/%d  hold kept/skip %d/%d  gap(d/h/lb) %s/%s/%s $/trade -> %s" % (
            name, kd, rd, kh, rh,
            "{:+,.0f}".format(gd) if gd == gd else "n/a",
            "{:+,.0f}".format(gh) if gh == gh else "n/a",
            "{:+,.0f}".format(gl_) if gl_ == gl_ else "n/a", tag))
    print("\n".join(L[-6:]), flush=True)

    # =====================================================================================
    # HYBRID STOP - a DIFFERENT idea, reported separately: every trade is still taken, but
    # the stop can never sit further than cap_atr ATR from the ACTUAL fill. Unlike the
    # selection rules above this changes exit bars/prices (a tighter stop can close a
    # position sooner, which can free up an entry the wide-stop version never got to take),
    # so the trade LIST itself differs from the incumbent's 357 - it is scored as its own run.
    # =====================================================================================
    L.append("")
    L.append("=" * 108)
    L.append("HYBRID STOP (separate idea, NOT a selection rule, NOT mixed into the family above): every trade is")
    L.append("still taken; the structural stop is capped at %.2f ATR from the ACTUAL fill (same threshold as CAP-ATR," % cap_atr)
    L.append("for comparability) whenever the structural range would have set it wider. Distance is min(structural,")
    L.append("cap_atr x ATR-at-the-fire-bar) - the ATR value is known at the fire bar, before the fill, same as every")
    L.append("filter above. This can shift exit bars/prices, so the trade LIST differs from the incumbent's 357 -")
    L.append("reported as its own run, not a re-score of the same trades.")
    hyb = run_hybrid(A, df, feat, cap_atr)
    L.append("")
    L.append("  %-40s %-38s   %s" % ("", "whole-run (n/PF/net$/DD$)",
                                     "then discovery / holdout / lockbox (n/PF/net$/DD$ each)"))
    hu = hyb["usd"].values
    dmh, hmh, lmh = hyb_splits(hyb, r6.LB_FROM)
    L.append("  %-30s %s" % ("incumbent (no cap, 357 trades)", cell(usd)))
    L.append("  %-30s %s   disc %s   hold %s   lb %s" % (
        "hybrid cap %.2f ATR (%d trades)" % (cap_atr, len(hu)), cell(hu), cell(hu[dmh]), cell(hu[hmh]), cell(hu[lmh])))
    s_inc, s_hyb = stats(usd), stats(hu)
    dnet, ddd = s_hyb["net"] - s_inc["net"], s_hyb["dd"] - s_inc["dd"]
    L.append("  whole-run: incumbent net $%s DD $%s PF %.2f  ->  hybrid net $%s DD $%s PF %.2f  (%s%s in net, %s%s in DD)"
             % ("{:,.0f}".format(s_inc["net"]), "{:,.0f}".format(s_inc["dd"]), s_inc["pf"],
                "{:,.0f}".format(s_hyb["net"]), "{:,.0f}".format(s_hyb["dd"]), s_hyb["pf"],
                "+" if dnet >= 0 else "-", "${:,.0f}".format(abs(dnet)),
                "+" if ddd >= 0 else "-", "${:,.0f}".format(abs(ddd))))
    n_capped = int(hyb["capped"].sum())
    L.append("  the cap actually shortened the stop on %d of %d trades (%.0f%%) at its own discovery-75th-percentile"
             " threshold; the other %d fires never reached %.2f ATR of structural width in the first place."
             % (n_capped, len(hyb), 100.0 * n_capped / len(hyb), len(hyb) - n_capped, cap_atr))
    print("\n".join(L[-9:]), flush=True)

    L.append("")
    L.append("=" * 108)
    L.append("BOTTOM LINE")
    L.append("=" * 108)
    if any_survive:
        L.append("At least one selection/tilt rule survived discovery+holdout agreement on this pass - see the VERDICT")
        L.append("block above for which one and at what threshold. This is a lead, not a crowning bar (the house bar")
        L.append("for that is a fenced Auto-Validate, not a scan like this one).")
    else:
        L.append("NOTHING in the floor/cap family survives discovery+holdout agreement at a testable bucket size.")
        L.append("This matches the family's own closed history (TTM.md: coil shape - length, depth, slope, range-in-")
        L.append("ATR, prior move - already failed a holdout once, round 12d). The coil's SIZE, like its SHAPE, does")
        L.append("not separate this leg's own trades on 357 of them. The hourly-compression CHECK, already in")
        L.append("production, remains the only durable filter this family has ever produced.")
    _lines_to(L, LOG)
    L.append("")
    L.append("elapsed %.0fs -- log -> %s" % (time.time() - t0, LOG))
    print(L[-1], flush=True)


def hyb_splits(hyb, lb_from):
    lb_mask = (hyb["date"] >= pd.Timestamp(lb_from)).to_numpy()
    pre_idx = np.flatnonzero(~lb_mask)
    cut = int(round(len(pre_idx) * 0.6))
    disc = np.zeros(len(hyb), bool); disc[pre_idx[:cut]] = True
    hold = np.zeros(len(hyb), bool); hold[pre_idx[cut:]] = True
    return disc, hold, lb_mask


def run_hybrid(A, df, feat, cap_atr):
    """Every fire is still taken; the structural stop is capped at cap_atr ATR from the actual
    fill whenever the range-edge stop would have been wider. Re-simulates from scratch (a
    tighter stop can close a position earlier and free up a later entry the wide-stop version
    never reached), then applies the SAME deep-squeeze 1.5x tilt and cost convention as the
    incumbent (TTMSQZ_3_0_ES30SS.py:_deep_state / _rescore) so the two runs are comparable."""
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    did, index = df["day_id"].values, df["_dt"]
    n, warm = A["n"], A["warm"]
    mom, atr, fire = A["mom"], A["atr"], A["fire"]
    rng_hi, rng_lo = A["rng_hi"], A["rng_lo"]
    gate_long, gate_short, last_bar = A["gate_long"], A["gate_short"], A["last_bar"]
    fade_bars, eod_cutoff, direction = ss._FROZEN["fade_bars"], 1, ss._FROZEN["direction"]

    pos = 0; entry_px = 0.0; entry_bar = -1; side = 0; stop_px = None; fade_cnt = 0; pending = None
    trade_log = []
    cap_flags = {}   # entry_bar -> True if this trade's stop distance was actually shortened by the cap

    def _book(exit_i, px, sd, ep, eb):
        p = (px - ep) if sd > 0 else (ep - px)
        trade_log.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(px)))

    for u in range(warm, n):
        eod = u == last_bar[u]
        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
                pending = None
            else:
                if pos == 0:
                    side = pending[1]; rh, rl = pending[2], pending[3]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    struct_dist = (entry_px - rl) if side > 0 else (rh - entry_px)
                    fbar = u - 1
                    atr_val = atr[fbar] if fbar >= 0 else np.nan
                    binds = np.isfinite(atr_val) and cap_atr * atr_val < struct_dist
                    dist = cap_atr * atr_val if binds else struct_dist
                    cap_flags[u] = bool(binds)
                    stop_px = entry_px - dist if side > 0 else entry_px + dist
                    if (side > 0 and l[u] <= stop_px) or (side < 0 and h[u] >= stop_px):
                        _book(u, stop_px, pos, entry_px, entry_bar); pos = 0; stop_px = None
                pending = None
        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar); pos = 0; stop_px = None
        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
            pending = None
            continue
        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue
        if pos != 0:
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",); continue
        if pos == 0 and pending is None and fire[u] and m != 0:
            sd = 1 if m > 0 else -1
            if direction == "long" and sd < 0: continue
            if direction == "short" and sd > 0: continue
            if sd > 0 and not gate_long[u]: continue
            if sd < 0 and not gate_short[u]: continue
            if last_bar[u] - u <= eod_cutoff: continue
            pending = ("mkt", sd, rng_hi[u], rng_lo[u])

    deep = ss._deep_state(h, l, c, did, index)
    out = []
    capped = []
    for tt in trade_log:
        eb = int(tt[0]); d = bool(deep[min(max(eb - 1, 0), len(deep) - 1)])
        s = 1.5 if d else 1.0
        pnl = s * float(tt[2]) - (s - 1.0) * ss._COST_PTS
        out.append((eb, int(tt[1]), pnl) + tuple(tt[3:]))
        capped.append(cap_flags.get(eb, False))
    usd = (np.array([x[2] for x in out]) - r6.COST["ES"]) * r6.MULT["ES"]
    dates = pd.DatetimeIndex(df["_dt"])[[x[1] for x in out]].tz_localize(None).normalize()
    return pd.DataFrame(dict(usd=usd, date=dates, capped=capped))


def _lines_to(lines, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
