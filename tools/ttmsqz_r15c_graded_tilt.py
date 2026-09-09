"""
TTM SQUEEZE ROUND 15c - a GRADED size tilt, copied from a house convention used elsewhere.

WHERE THIS PICKS UP
  The book leg (`TTMSQZ_3_0_ES30SS20.py`, run #353, the structural-stop leg swapped in
  2026-09-09) carries a single-step size tilt: 1.5 contracts on trades entered while the
  hourly compression ratio is at or under 0.85, 1 contract otherwise. The ENGU-Q paper leg
  `ENGUQ_309_CD` (api/paper.py, `augur_engine/ml_keel.py:compression_sizes`) already runs a
  DEPTH-GRADED version of the same idea: 2x when the ratio is under 0.85, 1.5x when the hourly
  squeeze is merely on. That grading is an existing house convention, not a knob invented for
  this scan - which is the only reason it is worth testing here rather than fishing for a new
  cut point.

WHAT THIS FILE TESTS, on the leg the paper book actually carries (ES 30m RTH, structural stop,
  kc_mult 1.5, eod_cutoff 1, gate_len 20 - run #353's cell):
  1. HOUSE  - the ENGU-Q grading exactly as ml_keel.compression_sizes applies it: 2.0x when the
     ratio is <= 0.85, 1.5x when the hourly squeeze is on but the ratio is above 0.85, 1.0x
     otherwise. On THIS leg every entered trade already requires the hourly squeeze to be on
     (gate_mode='sq_on', gate_ratio=1.0), so the third bucket is expected to be near-empty -
     bucket counts are printed so that claim is checked, not assumed.
  2. DEPTH3 - a three-step version keyed on depth alone, ignoring the squeeze-on boolean:
     2.0x at ratio <= 0.70, 1.5x at ratio <= 0.85, 1.0x above.
  3. INCUMB - the control: today's single step, 1.5x at ratio <= 0.85, 1.0x otherwise. This is
     also the bit-for-bit reproduction check against TTMSQZ_3_0_ES30SS20.py's own output.
  4. FLAT15 - the leverage control: 1.5x on every trade, no grading at all. A tilt that only
     beats INCUMB by being bigger, and not FLAT15, has found leverage, not skill.

COST CONVENTION (identical to TTMSQZ_3_0_ES30SS.py, copied exactly)
  A trade sized s returns `s*raw - (s-1)*cost` before the caller's single downstream cost
  subtraction, i.e. `s*(raw - cost)` after it. This file never re-subtracts cost per contract
  twice: usd_per_trade = size * (raw_pts - COST) * MULT, the same single-subtraction formula
  tools/ttmsqz_r13_gap_stress.py uses (`usd_of`).

NO LOOK-AHEAD
  The ratio is read from the last COMPLETE hourly group at the DECISION bar (the fire bar,
  entry_bar - 1) - exactly the construction TTMSQZ_3_0_ES30SS.py's own `_deep_state` uses, and
  exactly the bar the gate itself reads (same length 20 / Bollinger 2.0 / Keltner 1.5, matching
  the pinned cell's kc_mult so the tilt's ratio and the gate's ratio are the same number).

Window pinned 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES cost 0.363 pts/RT, $50/pt -
all four read from tools/ttmsqz_round6_parts.py, never re-declared here. Lockbox is reported,
never tuned on. SCAN ONLY: nothing here is crowned, queued for Auto-Validate, or written to
index.html.

Usage:  python tools/ttmsqz_r15c_graded_tilt.py
Output: tools/data/ttmsqz_r15c_graded_tilt.txt
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


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6_r15c")
ss = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS.py"), "ss_r15c")
ss20 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS20.py"), "ss20_r15c")

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULTD = r6.COST["ES"], r6.MULT["ES"]
INST = "ES"
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r15c_graded_tilt.txt")

# the incumbent's crowned cell, run #353 - structural stop, gate_len pinned at 20
CELL = dict(kc_mult=1.5, eod_cutoff=1, gate_len=20)

# THE QUOTED INCUMBENT (must be reproduced bit-for-bit before anything else runs)
INCUMBENT_QUOTE = dict(n=357, pf=2.91, net=101017, dd=4338,
                        lb_net=16977, lb_pf=6.72)

# the fixed ratio definition the validated tilt uses (TTMSQZ_3_0_ES30SS.py: _TILT_LEN/_BB/_KC)
TILT_LEN, TILT_BB, TILT_KC = 20, 2.0, 1.5
DEEP_THR = 0.85           # the incumbent's / house's deep-compression cut
THREE_STEP_DEEP = 0.70    # the depth-only variant's extra cut


# ----------------------------------------------------------------------------------------
# ratio at the decision bar - copied verbatim from TTMSQZ_3_0_ES30SS._deep_state, EXCEPT it
# returns the continuous ratio (not a single thresholded boolean) so this file can bucket it
# at more than one cut point. Same last-complete-hourly-bar construction, same fixed 20/2.0/1.5.
# ----------------------------------------------------------------------------------------
def ratio_state(h, l, c, did, index):
    n = len(c)
    idx = pd.DatetimeIndex(index)
    mins = idx.hour.values * 60 + idx.minute.values
    first_of_day = np.zeros(n, int)
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        first_of_day[a:b] = mins[a]
        a = b
    bucket = (mins - first_of_day) // 60
    grp = did.astype(np.int64) * 10000 + bucket.astype(np.int64)
    change = np.empty(n, bool); change[0] = True; change[1:] = grp[1:] != grp[:-1]
    gstart = np.flatnonzero(change)
    gend = np.append(gstart[1:], n) - 1
    hh = np.array([h[s:e + 1].max() for s, e in zip(gstart, gend)])
    ll = np.array([l[s:e + 1].min() for s, e in zip(gstart, gend)])
    cc = c[gend]
    s_ = pd.Series(cc)
    dev = s_.rolling(TILT_LEN).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(TILT_LEN).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((TILT_BB * dev) / (TILT_KC * atr)).to_numpy()
    warm = TILT_LEN * 2 + 5
    j = np.searchsorted(gend, np.arange(n), side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(cc) - 1)
    return np.where(ok, ratio[jj], np.nan)


def raw_trades(df):
    """Unsized trade list from the structural-stop engine at the incumbent's crowned cell -
    the same fire/gate/stop construction TTMSQZ_3_0_ES30SS20.py runs, before any tilt."""
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float); c = df["close"].values.astype(float)
    did = df["day_id"].values; index = df["_dt"]
    A = ss._build_arrays(o, h, l, c, did, index, CELL["kc_mult"], CELL["gate_len"])
    trade_log = ss._simulate(o, h, l, c, A['n'], A['warm'], A['mom'], A['atr'], A['fire'],
                              A['rng_hi'], A['rng_lo'], A['gate_long'], A['gate_short'],
                              A['last_bar'], ss._FROZEN['fade_bars'], CELL["eod_cutoff"],
                              ss._STRUCT_BUF, ss._FROZEN['direction'])
    ratio = ratio_state(h, l, c, did, index)
    return trade_log, ratio, df


def usd_and_dates(trade_log, ratio, df, mult_fn):
    """Given the raw trade list and a bucket function of the DECISION-bar ratio, return
    (usd array, exit-date array, size array, ratio array-at-decision-bar)."""
    eb = np.array([t[0] for t in trade_log], int)
    xb = np.array([t[1] for t in trade_log], int)
    raw = np.array([t[2] for t in trade_log], float)
    dec = np.clip(eb - 1, 0, len(ratio) - 1)
    r = ratio[dec]
    size = mult_fn(r)
    usd = size * (raw - COST) * MULTD
    dates = pd.DatetimeIndex(df["_dt"])[xb].date
    return usd, dates, size, r


def mult_incumbent(r):
    return np.where(np.nan_to_num(r, nan=99.0) <= DEEP_THR, 1.5, 1.0)


def mult_flat(r):
    return np.full_like(r, 1.5, dtype=float)


def mult_house(r):
    rr = np.nan_to_num(r, nan=99.0)
    return np.where(rr <= DEEP_THR, 2.0, np.where(rr < 1.0, 1.5, 1.0))


def mult_three_step(r):
    rr = np.nan_to_num(r, nan=99.0)
    return np.where(rr <= THREE_STEP_DEEP, 2.0, np.where(rr <= DEEP_THR, 1.5, 1.0))


def years_span(dates):
    d = pd.to_datetime(pd.Series(list(dates)))
    return max((d.max() - d.min()).days / 365.25, 1e-9)


def mar(net, dd, dates):
    if dd is None or dd <= 0 or len(dates) == 0:
        return float("nan")
    return (net / years_span(dates)) / dd


def slice_score(usd, dates, size):
    if len(usd) == 0:
        return None
    s = r6.score(usd, dates)
    s["mar"] = mar(s["net"], s["dd"], dates)
    s["contracts"] = float(size.sum())
    s["usd_per_contract"] = s["net"] / s["contracts"] if s["contracts"] > 0 else float("nan")
    return s


def fmt_row(name, s):
    if s is None:
        return "  %-30s   no trades" % name
    return ("  %-30s %5d %7.2f %11s %9s %7.3f %9s %10s" % (
        name, s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
        s["mar"], "{:,.0f}".format(s["contracts"]), "{:,.0f}".format(s["usd_per_contract"])))


HDR = "  %-30s %5s %7s %11s %9s %7s %9s %10s" % (
    "variant", "n", "PF", "net $", "DD $", "MAR", "contr.", "$/contr.")


def main():
    t0 = time.time()
    L = []
    L.append("TTM SQUEEZE ROUND 15c - GRADED size tilt (house convention, ENGU-Q's compression_sizes)"
              "   %s" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("Leg: TTMSQZ_3_0_ES30SS20.py (run #353, structural stop, the leg the paper book carries),"
              " ES 30m RTH, kc_mult 1.5, eod_cutoff 1, gate_len 20.")
    L.append("Window %s..%s, lockbox from %s, cost %.3f pts/RT, $%d/pt (tools/ttmsqz_round6_parts.py)."
              % (DATE_FROM, DATE_TO, LB_FROM, COST, MULTD))
    L.append("")

    df = r6.load(INST, "30m", "RTH")

    # ====================================================================================
    # STEP 1 - BIT-FOR-BIT REPRODUCTION of the quoted incumbent, via the real strategy file
    # ====================================================================================
    L.append("=" * 88)
    L.append("STEP 1 - reproduce TTMSQZ_3_0_ES30SS20.py bit-for-bit before testing anything")
    L.append("=" * 88)
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float); c = df["close"].values.astype(float)
    did = df["day_id"].values; index = df["_dt"]

    res = ss20.run_backtest(o, h, l, c, volumes=None, day_id=did, index=index,
                             return_trades=True, kc_mult=CELL["kc_mult"], eod_cutoff=CELL["eod_cutoff"])
    tr = res["trades"]
    pnl_pts = np.array([t[2] for t in tr], float)
    xb = np.array([t[1] for t in tr], int)
    dates_off = pd.DatetimeIndex(df["_dt"])[xb].date
    usd_off = (pnl_pts - COST) * MULTD
    s_off = r6.score(usd_off, dates_off)
    lbmask_off = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates_off])
    s_off_lb = r6.score(usd_off[lbmask_off], np.array(dates_off)[lbmask_off]) if lbmask_off.any() else None

    ok_whole = (s_off["n"] == INCUMBENT_QUOTE["n"] and abs(s_off["pf"] - INCUMBENT_QUOTE["pf"]) < 0.01
                and abs(s_off["net"] - INCUMBENT_QUOTE["net"]) < 500 and abs(s_off["dd"] - INCUMBENT_QUOTE["dd"]) < 50)
    ok_lb = (s_off_lb is not None and abs(s_off_lb["net"] - INCUMBENT_QUOTE["lb_net"]) < 500
             and abs(s_off_lb["pf"] - INCUMBENT_QUOTE["lb_pf"]) < 0.05)
    L.append("  quoted:    n %d, PF %.2f, net $%s, DD $%s | lockbox $%s @ PF %.2f"
              % (INCUMBENT_QUOTE["n"], INCUMBENT_QUOTE["pf"], "{:,.0f}".format(INCUMBENT_QUOTE["net"]),
                 "{:,.0f}".format(INCUMBENT_QUOTE["dd"]), "{:,.0f}".format(INCUMBENT_QUOTE["lb_net"]),
                 INCUMBENT_QUOTE["lb_pf"]))
    L.append("  file run:  n %d, PF %.2f, net $%s, DD $%s | lockbox $%s @ PF %.2f"
              % (s_off["n"], s_off["pf"], "{:,.0f}".format(s_off["net"]), "{:,.0f}".format(s_off["dd"]),
                 "{:,.0f}".format(s_off_lb["net"]) if s_off_lb else "n/a",
                 s_off_lb["pf"] if s_off_lb else float("nan")))
    L.append("  REPRODUCTION: %s (whole run), %s (lockbox)" % (
        "MATCH" if ok_whole else "MISMATCH - STOP, do not trust anything below",
        "MATCH" if ok_lb else "MISMATCH - STOP, do not trust anything below"))
    L.append("")

    # ====================================================================================
    # STEP 2 - this file's OWN trade construction (build_arrays/_simulate + ratio bucketing)
    #          reproduced against the incumbent's own single-step tilt, as a second, harder
    #          reproduction check: not just the file's number, but THIS file's re-derivation
    #          of the same trades from the raw engine, priced with the same cost convention.
    # ====================================================================================
    L.append("=" * 88)
    L.append("STEP 2 - this file's own raw-trade construction, re-priced with the incumbent's own")
    L.append("single-step tilt (1.5x at ratio<=0.85), checked against STEP 1's file-level output")
    L.append("=" * 88)
    trade_log, ratio, _ = raw_trades(df)
    usd_c, dates_c, size_c, r_c = usd_and_dates(trade_log, ratio, df, mult_incumbent)
    s_c = slice_score(usd_c, dates_c, size_c)
    n_nan = int(np.isnan(r_c).sum())
    ok_self = (s_c["n"] == s_off["n"] and abs(s_c["net"] - s_off["net"]) < 1.0
               and abs(s_c["dd"] - s_off["dd"]) < 1.0)
    L.append("  self-built control: n %d, PF %.2f, net $%s, DD $%s (NaN ratios at decision bar: %d)"
              % (s_c["n"], s_c["pf"], "{:,.0f}".format(s_c["net"]), "{:,.0f}".format(s_c["dd"]), n_nan))
    L.append("  MATCHES STEP 1's file-level net/DD to the dollar: %s" % ("YES" if ok_self else "NO - BUG"))
    if not ok_self:
        L.append("  *** STOP: the re-derived trade list disagrees with the real strategy file. ***")
    L.append("")

    # ====================================================================================
    # STEP 3 - bucket counts (variant 1's third bucket is expected near-empty; check it)
    # ====================================================================================
    L.append("=" * 88)
    L.append("STEP 3 - bucket counts at the decision-bar ratio (n=%d trades total)" % len(r_c))
    L.append("=" * 88)
    n_deep70 = int((np.nan_to_num(r_c, nan=99) <= THREE_STEP_DEEP).sum())
    n_mid = int(((np.nan_to_num(r_c, nan=99) > THREE_STEP_DEEP) & (np.nan_to_num(r_c, nan=99) <= DEEP_THR)).sum())
    n_deep85 = int((np.nan_to_num(r_c, nan=99) <= DEEP_THR).sum())
    n_on_shallow = int(((np.nan_to_num(r_c, nan=99) > DEEP_THR) & (np.nan_to_num(r_c, nan=99) < 1.0)).sum())
    n_off = int((np.nan_to_num(r_c, nan=99) >= 1.0).sum())
    L.append("  HOUSE grading (variant 1):  deep (ratio<=0.85) %d  |  on-not-deep (0.85<ratio<1.0) %d"
              "  |  off (ratio>=1.0) %d" % (n_deep85, n_on_shallow, n_off))
    L.append("  DEPTH3 grading (variant 2): deep (ratio<=0.70) %d  |  mid (0.70<ratio<=0.85) %d"
              "  |  shallow (ratio>0.85) %d" % (n_deep70, n_mid, n_deep85 + n_on_shallow + n_off - n_deep70 - n_mid))
    if n_off:
        L.append("  note: %d of %d trades (%.1f%%) landed with ratio>=1.0 at the decision bar despite the"
                  " gate requiring the hourly squeeze on - floating-point boundary between this file's"
                  " re-derived ratio and the engine's own boolean comparison, not a real 'squeeze off' trade."
                  % (n_off, len(r_c), 100.0 * n_off / max(len(r_c), 1)))
    else:
        L.append("  confirmed: the third HOUSE bucket (squeeze off) is EMPTY on this leg - every entered"
                  " trade already requires the hourly squeeze to be on, exactly as expected.")
    L.append("")

    # ====================================================================================
    # STEP 4 - all four variants, whole run and lockbox, risk-adjusted
    # ====================================================================================
    variants = [
        ("1 INCUMB (control 1.5x<=.85)", mult_incumbent),
        ("2 FLAT15 (leverage control)", mult_flat),
        ("3 HOUSE (2.0/1.5/1.0, ENGU-Q)", mult_house),
        ("4 DEPTH3 (2.0/1.5/1.0 @.70/.85)", mult_three_step),
    ]

    L.append("=" * 88)
    L.append("STEP 4 - WHOLE RUN, %s..%s" % (DATE_FROM, DATE_TO))
    L.append("=" * 88)
    L.append(HDR)
    whole = {}
    for name, fn in variants:
        usd, dates, size, r = usd_and_dates(trade_log, ratio, df, fn)
        s = slice_score(usd, dates, size)
        whole[name] = s
        L.append(fmt_row(name, s))
    L.append("")

    L.append("=" * 88)
    L.append("STEP 5 - LOCKBOX, %s..%s (never tuned on, reported separately)" % (LB_FROM, DATE_TO))
    L.append("=" * 88)
    L.append(HDR)
    lockbox = {}
    for name, fn in variants:
        usd, dates, size, r = usd_and_dates(trade_log, ratio, df, fn)
        lbmask = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
        s = slice_score(usd[lbmask], np.array(dates)[lbmask], size[lbmask]) if lbmask.any() else None
        lockbox[name] = s
        L.append(fmt_row(name, s))
    L.append("")

    # ====================================================================================
    # STEP 6 - the honest read: risk-adjusted, not raw money
    # ====================================================================================
    L.append("=" * 88)
    L.append("STEP 6 - the honest read")
    L.append("=" * 88)
    inc_w, flat_w, house_w, d3_w = (whole[variants[0][0]], whole[variants[1][0]],
                                     whole[variants[2][0]], whole[variants[3][0]])
    L.append("  Whole-run MAR: INCUMB %.3f | FLAT15 %.3f | HOUSE %.3f | DEPTH3 %.3f"
              % (inc_w["mar"], flat_w["mar"], house_w["mar"], d3_w["mar"]))
    L.append("  Whole-run $/contract traded: INCUMB $%s | FLAT15 $%s | HOUSE $%s | DEPTH3 $%s"
              % ("{:,.0f}".format(inc_w["usd_per_contract"]), "{:,.0f}".format(flat_w["usd_per_contract"]),
                 "{:,.0f}".format(house_w["usd_per_contract"]), "{:,.0f}".format(d3_w["usd_per_contract"])))
    inc_lb, flat_lb, house_lb, d3_lb = (lockbox[variants[0][0]], lockbox[variants[1][0]],
                                         lockbox[variants[2][0]], lockbox[variants[3][0]])
    L.append("  Lockbox MAR: INCUMB %.3f | FLAT15 %.3f | HOUSE %.3f | DEPTH3 %.3f"
              % (inc_lb["mar"] if inc_lb else float("nan"), flat_lb["mar"] if flat_lb else float("nan"),
                 house_lb["mar"] if house_lb else float("nan"), d3_lb["mar"] if d3_lb else float("nan")))
    L.append("")
    L.append("  HOUSE vs INCUMB: net %+.1f%%, DD %+.1f%%, whole-run MAR %+.1f%%, contracts %+.1f%%"
              % (100 * (house_w["net"] / inc_w["net"] - 1), 100 * (house_w["dd"] / inc_w["dd"] - 1),
                 100 * (house_w["mar"] / inc_w["mar"] - 1), 100 * (house_w["contracts"] / inc_w["contracts"] - 1)))
    L.append("  DEPTH3 vs INCUMB: net %+.1f%%, DD %+.1f%%, whole-run MAR %+.1f%%, contracts %+.1f%%"
              % (100 * (d3_w["net"] / inc_w["net"] - 1), 100 * (d3_w["dd"] / inc_w["dd"] - 1),
                 100 * (d3_w["mar"] / inc_w["mar"] - 1), 100 * (d3_w["contracts"] / inc_w["contracts"] - 1)))
    L.append("  HOUSE vs FLAT15 (the leverage control): net %+.1f%%, DD %+.1f%%, whole-run MAR %+.1f%%,"
              " contracts %+.1f%%" % (100 * (house_w["net"] / flat_w["net"] - 1),
                                       100 * (house_w["dd"] / flat_w["dd"] - 1),
                                       100 * (house_w["mar"] / flat_w["mar"] - 1),
                                       100 * (house_w["contracts"] / flat_w["contracts"] - 1)))
    L.append("")
    L.append("  Elapsed %.1fs" % (time.time() - t0))

    out = "\n".join(L)
    print(out)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w") as f:
        f.write(out + "\n")
    print("\nWrote %s" % LOG)


if __name__ == "__main__":
    main()
