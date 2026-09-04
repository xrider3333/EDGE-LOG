"""NOISE — the ML gate as a SIZE TILT instead of a keep/skip CUT (the ORB item-171 test,
re-run on the strategy whose edge structure is known to differ).

THE PRE-REGISTRATION, fixed in writing BEFORE any cell is run (2026-09-02). Nothing below may
be changed after seeing a number; if a cell is impossible, drop it and say so.

WHY THIS TEST EXISTS. On 2026-08-10 this program pre-registered a gate-tilt bar and ran it —
but only on ORB (`tools/orb_gate_tilt.py`, docstring "ORB item 171", config ORB_3_0_ENS,
NQ 5m RTH). 0 of 12 tilt variants cleared, and the result was then written into the docs as
"ML-score size tilts are a DEAD family in this program (0/12 cleared)". NOISE was never tested.
The owner challenged the generalisation and is right to: the SAME log entry records NOISE moving
the OPPOSITE way to ORB when the look-ahead was fixed (ORB gated $348,256 -> $288,793, degraded;
NOISE $282,310 -> $294,327, improved, "since its edge structure differs from ORB's"), and ORB's
own margin was a whisker (flat MAR 27.6 vs best tilt 27.3).

CONFIG UNDER TEST: the crowned NOISE configuration, run #243 —
  NOISE_1_0.py params: lookback 44, band_mult_long 0.75, band_mult_short 1.5, exit_mode vwap,
  side Both, window all_day, flat_eod true, stop_mode bandwidth, stop_k 1.75,
  daytype_mode skip_bot_short, daytype_lo 0.20, vol_skip_pct 90.
  NQ, 5m, RTH, master db_noadj_rth, cost 0.533 pts round-turn, $20/pt, 1 contract base.
  Window 2010-06-07 -> 2026-08-12, lockbox from 2025-02-11 (SPENT — confirmatory only).

PROBABILITY: the SAME causal walk the gate uses — gate_trades at threshold 0 so nothing is
dropped and only the score is read; trained only on trades that closed before each entry;
warm-up trades have no score and take weight 1.0. This is `entry_features_causal`, the fixed
engine. Any run on pre-2026-08-10 leak-era scores is void.

SCHEMES — a-priori, copied verbatim from the ORB pre-registration, nothing fitted to the result:
  cut@50   w = 1 if p >= .50 else 0
  tier     w = 2.0 / 1.0 / 0.5 for p >= .55 / .45-.55 / < .45
  linear   w = clip(1 + 4*(p - .50), 0.25, 3.0)
MODELS: the engine's existing candidate set — logistic, rf, xgb, tree — so 4 models x 3 schemes
= 12 variants, the same 12 the ORB test ran. No shape shopping, no extra models.

CAPITAL MATCHING: every scheme is capital-matched to the flat size-1 risk budget, and the
matching constant is computed on the PRE-LOCKBOX slice ONLY, then applied unchanged to the
lockbox slice. A tilt that wins only by being bigger has not won.

THE BAR (identical to 2026-08-10, unchanged):
  A tilt is ADOPTED only if it beats flat size-1 on BOTH net $ AND MAR in the PRE-LOCKBOX
  window, AND ties-or-beats flat MAR on the lockbox slice.
  One shot. The lockbox is spent, so it is confirmatory only and may not be used to RANK.

WHAT WOULD FALSIFY THE "DEAD FAMILY" CLAIM: any of the 12 clearing all three legs. If one or
more do, the honest statement becomes "tilts are dead ON ORB and alive on NOISE", not "dead in
this program".
WHAT WOULD CONFIRM IT: 0 of 12 again, on a strategy whose edge structure is known to differ.

REQUIRED ALONGSIDE, reported whether or not anything clears:
  * the flat-size baseline's own net / MAR / DD / trades on both slices;
  * per variant: net, MAR, max DD, trades, average size, and the biggest single size;
  * the CONCENTRATION check this program applies to every size result — does any apparent gain
    survive removing the 10 best trades? A tilt whose edge is 10 trades is not an edge.
  * how much of any difference is simply that the tilt takes EVERY trade while the cut drops some.

--- end of pre-registration -------------------------------------------------------------------

IMPLEMENTATION NOTES (mechanics only; they change no term of the bar above).
  * Trade list comes from tools/noise_variant_research.run_variant (its parity against the real
    NOISE_1_0 engine is proven, and this module re-checks it at startup against
    NOISE_1_0.run_backtest on the exact config under test).
  * run_variant knob mapping for the #243 card: vol_skip_pct=90 -> rv_mode='skip_hi', rv_pct=90;
    flat_eod=True is unconditional in run_variant (STEP E), so the card matches.
  * "Risk" for capital matching is each trade's INITIAL stop distance in points, recomputed the
    way the strategy sets it (stop_k x band half-width at the fill bar) — the direct analogue of
    the opening-range risk tools/orb_gate_tilt.py uses.
  * Final size is capped at 3 contracts, the same rp-cap3 cap the ORB run applied; the cap bind
    count is printed so its effect is visible.
  * MAR here is raw net/|maxDD| (sizing.mar), exactly as the ORB run computed it, so the two
    tables are comparable cell for cell. Within one slice the years divisor is constant, so
    annualising would not change any ranking or any PASS/FAIL.

Usage:  python tools/noise_gate_tilt.py
"""
import sys, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.ml_gate import gate_trades, entry_features_causal    # noqa: E402
from augur_engine.sizing import mar                                    # noqa: E402
from noise_variant_research import run_variant, _session_bounds, _sigma_matrix   # noqa: E402

INST, TF, SESS, SOURCE = "NQ", "5m", "rth", "db_noadj_rth"
MULT = 20.0
FEE = 0.533                       # pts round-turn, per contract
DFROM, DTO = "2010-06-07", "2026-08-12"
LB_FROM = "2025-02-11"
CAP = 3.0

# run #243, the crowned NOISE card, verbatim (run_variant knob names).
CFG = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
           exit_mode="vwap", side="Both", window="all_day",
           stop_mode="bandwidth", stop_k=1.75,
           daytype_mode="skip_bot_short", daytype_lo=0.20,
           rv_mode="skip_hi", rv_pct=90.0)
# the same card in NOISE_1_0.run_backtest knob names, for the parity check
CFG_ENGINE = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
                  exit_mode="vwap", side="Both", window="all_day",
                  flat_eod=True, skip_holidays=False,
                  stop_mode="bandwidth", stop_k=1.75,
                  daytype_mode="skip_bot_short", daytype_lo=0.20,
                  vol_skip_pct=90.0)

MODELS = ("logistic", "rf", "xgb", "tree")


def _w_cut(p):
    return np.where(np.isnan(p), 1.0, (p >= 0.50).astype(float))


def _w_tier(p):
    w = np.where(p >= 0.55, 2.0, np.where(p >= 0.45, 1.0, 0.5))
    return np.where(np.isnan(p), 1.0, w)


def _w_linear(p):
    return np.where(np.isnan(p), 1.0, np.clip(1.0 + 4.0 * (p - 0.50), 0.25, 3.0))


SCHEMES = (("cut@50", _w_cut), ("tier", _w_tier), ("linear", _w_linear))


def _metrics(pnl_pts, size):
    """Net dollar metrics for one slice at the given per-trade contract sizes."""
    net = size * (pnl_pts - FEE) * MULT
    if not len(net):
        return None
    cum = np.cumsum(net)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(net[net > 0].sum()); gl = float(-net[net < 0].sum())
    live = size > 1e-9
    return {"net": float(net.sum()), "n": int(live.sum()),
            "pf": (gw / gl) if gl > 1e-9 else float("inf"),
            "dd": dd, "mar": mar(net.sum(), dd),
            "avg_sz": float(size[live].mean()) if live.any() else 0.0,
            "max_sz": float(size.max()),
            "net_arr": net}


def _ex_top(net, k=10):
    """Net after deleting this series' own k biggest single-trade dollar winners."""
    if len(net) <= k:
        return float("nan")
    s = np.sort(net)[::-1]
    return float(net.sum() - s[:k].sum())


def _trade_risk(trades, arrays, cfg):
    """Each trade's INITIAL stop distance in points, recomputed exactly as run_variant sets
    stop_level for stop_mode='bandwidth' at the fill bar."""
    o = np.asarray(arrays["open"], float); c = np.asarray(arrays["close"], float)
    did = np.asarray(arrays["day_id"]); n = len(c)
    sb = _session_bounds(did, n)
    sigma = _sigma_matrix(o, c, sb, int(cfg["lookback"]))
    sess_of = np.zeros(n, int)
    for si, (a, b) in enumerate(sb):
        sess_of[a:b] = si
    sk = float(cfg["stop_k"])
    bml, bms = float(cfg["band_mult_long"]), float(cfg["band_mult_short"])
    risk = np.full(len(trades), np.nan)
    for i, t in enumerate(trades):
        gi = int(t[0]); pos = int(t[3])
        si = sess_of[gi]
        a, _b = sb[si]
        k = gi - a
        prev_close = c[sb[si - 1][1] - 1] if si > 0 else np.nan
        ref_hi = max(o[a], prev_close); ref_lo = min(o[a], prev_close)
        s = sigma[si, k] if k < sigma.shape[1] else np.nan
        if np.isnan(s):
            continue
        risk[i] = sk * (ref_hi * bml * s) if pos > 0 else sk * (ref_lo * bms * s)
    bad = ~np.isfinite(risk) | (risk <= 0)
    if bad.any():
        fill = float(np.nanmedian(risk[~bad])) if (~bad).any() else 1.0
        risk[bad] = fill
    return np.maximum(risk, 1e-9), int(bad.sum())


def main():
    import pandas as pd
    m = find_master(INST, TF, SESS, SOURCE)
    if m is None:
        raise SystemExit("NO MASTER for %s/%s/%s/%s" % (INST, TF, SESS, SOURCE))
    arrays = load_master_arrays(m, DFROM, DTO)
    idx = arrays["index"]

    T = run_variant(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                    arrays.get("volume"), arrays["day_id"], **CFG)
    T = sorted(T, key=lambda t: int(t[0]))

    # -- parity: the research fork vs the real NOISE_1_0 plugin on THIS exact card --
    sys.path.insert(0, os.path.join(ROOT, "augur_strategies"))
    import importlib
    NZ = importlib.import_module("NOISE_1_0")
    eng = NZ.run_backtest(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                          volumes=arrays.get("volume"), day_id=arrays["day_id"],
                          return_trades=True, **CFG_ENGINE)
    gross = float(sum(t[2] for t in T))
    par_ok = (eng is not None and eng["num_trades"] == len(T)
              and abs(eng["total_pnl"] - gross) < 1e-6)
    print("=== NOISE gate-as-SIZE-TILT - pre-registered 2026-09-02 ===")
    print("config  run #243 card: lb44 / 0.75 / 1.5 / vwap / Both / all_day / bandwidth k1.75 /"
          " skip_bot_short lo0.20 / vol_skip 90")
    print("window  %s -> %s   master %s   cost %.3f pts RT   $%.0f/pt   base 1 contract"
          % (DFROM, DTO, m["filename"], FEE, MULT))
    print("parity  run_variant vs NOISE_1_0.run_backtest: %s  (engine n=%s pts=%.4f | "
          "fork n=%d pts=%.4f)"
          % ("PASS" if par_ok else "FAIL", eng and eng["num_trades"], eng and eng["total_pnl"],
             len(T), gross))
    if not par_ok:
        raise SystemExit("parity FAILED - refusing to report tilt numbers off an unproven fork")

    pnl = np.array([t[2] for t in T], float)
    risk, n_risk_fallback = _trade_risk(T, arrays, CFG)
    nb = len(idx)
    ts = np.array([idx[min(int(t[0]), nb - 1)] for t in T])

    lb_start = pd.Timestamp(LB_FROM)
    _tz = getattr(pd.Timestamp(idx[-1]), "tzinfo", None)
    if _tz is not None and lb_start.tzinfo is None:
        lb_start = lb_start.tz_localize(_tz)
    pre = ts < lb_start
    lb = ~pre
    print("trades  %d total  |  pre-lockbox %d  |  lockbox %d (from %s)  |  risk fallbacks %d"
          % (len(T), int(pre.sum()), int(lb.sum()), str(lb_start)[:10], n_risk_fallback))

    # -- baseline: flat 1 contract, every trade --
    flat = np.ones(len(T))
    base = {"pre": _metrics(pnl[pre], flat[pre]), "lb": _metrics(pnl[lb], flat[lb])}

    # -- score each model once (threshold 0 => nothing dropped, pure scoring walk) --
    feats = entry_features_causal(arrays)[0]
    probs = {}
    dropped_models = []
    for mdl in MODELS:
        try:
            g = gate_trades(arrays, [(int(t[0]), int(t[1]), float(t[2]) - FEE) for t in T],
                            model=mdl, threshold=0.0, min_history=30, refit_every=25,
                            seed=42, feats=feats)
        except Exception as e:                                     # noqa: BLE001
            print("  ! %-9s scoring raised %s: %s - 3 cells DROPPED" % (mdl, type(e).__name__, e))
            dropped_models.append(mdl); continue
        p = np.asarray(g.get("prob"), float) if g and g.get("prob") is not None else None
        if p is None or len(p) != len(T):
            print("  ! %-9s no usable causal scores - 3 cells DROPPED" % mdl)
            dropped_models.append(mdl); continue
        probs[mdl] = p
        print("  scored %-9s warm-up %4d  median p %.3f  scored-in-LB %d"
              % (mdl, int(np.isnan(p).sum()), np.nanmedian(p), int((~np.isnan(p))[lb].sum())))

    # -- table --
    hdr = ("\n%-9s%-9s | %12s%8s%11s%7s%7s%7s | %12s%8s%11s%6s%7s%7s"
           % ("model", "scheme", "PRE net $", "MAR", "PRE DD $", "n", "avgSz", "maxSz",
              "LB net $", "MAR", "LB DD $", "n", "avgSz", "maxSz"))
    print(hdr); print("-" * (len(hdr) - 1))
    b = base
    print("%-9s%-9s | %12s%8.1f%11s%7d%7.2f%7.2f | %12s%8.1f%11s%6d%7.2f%7.2f"
          % ("flat", "size 1", format(b["pre"]["net"], ",.0f"), b["pre"]["mar"],
             format(b["pre"]["dd"], ",.0f"), b["pre"]["n"], 1.0, 1.0,
             format(b["lb"]["net"], ",.0f"), b["lb"]["mar"],
             format(b["lb"]["dd"], ",.0f"), b["lb"]["n"], 1.0, 1.0))

    rows = []
    for mdl in MODELS:
        if mdl not in probs:
            continue
        p = probs[mdl]
        for name, fn in SCHEMES:
            w = fn(p)
            denom = float((w[pre] * risk[pre]).sum())
            if denom <= 1e-12:
                print("  ! %-9s%-9s zero deployed risk in PRE - cell DROPPED" % (mdl, name))
                continue
            k = float(risk[pre].sum()) / denom      # capital-match on PRE-LOCKBOX only
            raw = w * k
            size = np.minimum(raw, CAP)
            r = {"model": mdl, "scheme": name, "k": k,
                 "cap_hits": int((raw > CAP + 1e-12).sum()),
                 "pre": _metrics(pnl[pre], size[pre]), "lb": _metrics(pnl[lb], size[lb])}
            rows.append(r)
            print("%-9s%-9s | %12s%8.1f%11s%7d%7.2f%7.2f | %12s%8.1f%11s%6d%7.2f%7.2f"
                  % (mdl, name, format(r["pre"]["net"], ",.0f"), r["pre"]["mar"],
                     format(r["pre"]["dd"], ",.0f"), r["pre"]["n"],
                     r["pre"]["avg_sz"], r["pre"]["max_sz"],
                     format(r["lb"]["net"], ",.0f"), r["lb"]["mar"],
                     format(r["lb"]["dd"], ",.0f"), r["lb"]["n"],
                     r["lb"]["avg_sz"], r["lb"]["max_sz"]))

    # -- verdict against the pre-registered three-leg bar --
    print("\n--- THE BAR: (1) PRE net > flat  AND  (2) PRE MAR > flat  AND  (3) LB MAR >= flat ---")
    print("flat: PRE net %s  MAR %.2f   |   LB MAR %.2f"
          % (format(base["pre"]["net"], ",.0f"), base["pre"]["mar"], base["lb"]["mar"]))
    passed = []
    for r in rows:
        l1 = r["pre"]["net"] > base["pre"]["net"]
        l2 = r["pre"]["mar"] > base["pre"]["mar"]
        l3 = r["lb"]["mar"] >= base["lb"]["mar"]
        ok = l1 and l2 and l3
        if ok:
            passed.append(r)
        print("  %-9s%-9s L1 net %+11s %s | L2 MAR %+6.2f %s | L3 LB MAR %+6.2f %s  -> %s"
              % (r["model"], r["scheme"],
                 format(r["pre"]["net"] - base["pre"]["net"], ",.0f"), "ok" if l1 else "no",
                 r["pre"]["mar"] - base["pre"]["mar"], "ok" if l2 else "no",
                 r["lb"]["mar"] - base["lb"]["mar"], "ok" if l3 else "no",
                 "PASS" if ok else "FAIL"))
    print("\n%d of %d cells clear all three legs.%s"
          % (len(passed), len(rows),
             ("  (%d cells dropped: %s)" % (3 * len(dropped_models), ",".join(dropped_models)))
             if dropped_models else ""))

    # -- concentration: does any gain survive deleting the 10 best trades? --
    print("\n--- CONCENTRATION (PRE slice): net after deleting each series own 10 best trades ---")
    f10 = _ex_top(base["pre"]["net_arr"])
    print("  flat size 1   net %12s  ->  ex-top10 %12s" % (format(base["pre"]["net"], ",.0f"),
                                                           format(f10, ",.0f")))
    for r in rows:
        v10 = _ex_top(r["pre"]["net_arr"])
        d_all = r["pre"]["net"] - base["pre"]["net"]
        d_ex = v10 - f10
        print("  %-9s%-9s net %12s -> ex-top10 %12s   gain vs flat: all %+11s  ex-top10 %+11s  %s"
              % (r["model"], r["scheme"], format(r["pre"]["net"], ",.0f"), format(v10, ",.0f"),
                 format(d_all, ",.0f"), format(d_ex, ",.0f"),
                 "survives" if (d_all > 0 and d_ex > 0) else
                 ("top-10 only" if d_all > 0 else "no gain to test")))

    # -- coverage: how much of the cut-vs-tilt difference is just "the tilt takes every trade" --
    print("\n--- COVERAGE: cut@50 DROPS trades; tier/linear keep every trade (min weight > 0) ---")
    for mdl in MODELS:
        if mdl not in probs:
            continue
        p = probs[mdl]
        dropped = (~np.isnan(p)) & (p < 0.50)
        print("  %-9s cut@50 drops %4d of %d trades (PRE %d / LB %d); those trades are worth "
              "%s PRE and %s LB at flat size 1"
              % (mdl, int(dropped.sum()), len(T), int((dropped & pre).sum()),
                 int((dropped & lb).sum()),
                 format(float(((pnl[dropped & pre] - FEE) * MULT).sum()), ",.0f"),
                 format(float(((pnl[dropped & lb] - FEE) * MULT).sum()), ",.0f")))
    caps = sum(r["cap_hits"] for r in rows)
    print("\ncap: final size capped at %.0f contracts; it bound on %d of %d cell-trades."
          % (CAP, caps, len(rows) * len(T)))


if __name__ == "__main__":
    main()
