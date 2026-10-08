# -*- coding: utf-8 -*-
"""PS-TAG r1 - does the frozen point score (ps1.2) rank the R of NOISE #304's WF trades? A REPORT
(docs/REPORT_pstag_r1_2026-10-07.md; MANAGER #39, NOISE #50). No NOISE rule changes either way.

  python tools/pstag_r1.py --power    trade-set parity with the #422 anatomy, R parity with #304's stops, coverage,
                                      the constant-point check and the null's p95s (shuffles only; no real rho)
  python tools/pstag_r1.py            the read (needs --power's null.json and reproduces it)

Trades: NOISE #304 through BALANCE r1's harness (load_master / frozen / build_bands / run_304: exact parity with
NOISE422_raw_trades.csv). Signal bar = fill bar - 1. R = unit points after the house cost / #304's own stop distance at
the fill (1.75 x the band's distance from its reference, NOISE_1_0.py lines 628-633), checked against the stop level
the engine logged on every stopped trade. Score: tools/point_score.py's vectorised path (Bars.full), 200 SMA, on the
1m bar starting at the signal bar's start + 4 min (the last 1m bar closed at the signal close); score % over the six
informative points (spec section 2).
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import balance_r1_stageA as B                                         # noqa: E402
import point_score as PS                                              # noqa: E402

W0, W1, H2 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"), pd.Timestamp("2022-01-01")
SEED, DRAWS = 20261005, 1000
HISTORY_FROM = "2016-01-01"
N_TRADES = 2797
INFORMATIVE = {"LONG": ("ma200_1m", "ma200_5m", "ma200_30m", "y_high", "big_body", "big_vol"),
               "SHORT": ("ma200_1m", "ma200_5m", "ma200_30m", "y_low", "big_body", "big_vol")}
CONSTANT = {"LONG": ("y_low", "y_close"), "SHORT": ("y_close", "y_high")}
STOP_RULES = ("low<=stop", "high>=stop", "open<stop", "open>stop")
OUTDIR = os.path.join(B.ANAT, "pstag_r1")
LOG = os.path.join(HERE, "r37_results", "pstag_r1.txt")
_lines = []


def say(s=""):
    print(s, flush=True)
    _lines.append(str(s))


# ================================================================== trades and R
def jy(d):
    """July-June WF year label: 2016 = 2016-07-01 .. 2017-06-30"""
    d = pd.Timestamp(d)
    return d.year if d.month >= 7 else d.year - 1


def trades():
    P = B.frozen()
    if P.get("stop_mode") != "bandwidth" or float(P.get("stop_k")) != 1.75:
        raise SystemExit("#304's _FROZEN is not the bandwidth stop k = 1.75 - abort")
    A = B.load_master("NQ")
    S = B.build_bands(A, P)
    tr = B.run_304(A, P, S)
    tr = tr[(tr.signal_date >= W0) & (tr.signal_date <= W1)].reset_index(drop=True)
    if len(tr) != N_TRADES:
        raise SystemExit("%d WF trades, not %d - abort" % (len(tr), N_TRADES))
    si = tr.si.to_numpy()
    e0 = tr.entry_idx.to_numpy()
    o0 = S.o[S.a[si]]
    ref_hi = np.maximum(o0, S.prev_close[si])
    ref_lo = np.minimum(o0, S.prev_close[si])
    k = float(P["stop_k"])
    lng = tr.side.to_numpy() > 0
    risk = np.where(lng, k * (S.UB[e0] - ref_hi), k * (ref_lo - S.LB[e0]))
    if not (np.isfinite(risk).all() and (risk > 0).all()):
        raise SystemExit("a WF trade has no positive stop distance - abort")
    # R parity: every stopped trade's logged stop level sits exactly `risk` from its fill
    nstop, worst = 0, 0.0
    for i, d in enumerate(tr.dec):
        ex = d["exit"]
        if ex.get("rule") in STOP_RULES:
            lvl = float(ex["level"])
            dist = (tr.entry_px[i] - lvl) if lng[i] else (lvl - tr.entry_px[i])
            worst = max(worst, abs(dist - risk[i]))
            nstop += 1
    if nstop == 0 or worst > 1e-6:
        raise SystemExit("stop-distance parity failed (%d stopped trades, max |diff| %.3g) - abort" % (nstop, worst))
    cost, mult = B.INST["NQ"]["cost"], B.INST["NQ"]["mult"]
    tr["net_pts"] = tr.raw_pts - cost
    tr["unit_usd"] = tr.net_pts * mult
    tr["risk_pts"] = risk
    tr["R"] = tr.net_pts / risk
    tr["signal_start"] = S.ts[tr.signal_idx.to_numpy()]
    tr["jy"] = [jy(d) for d in tr.signal_date]
    tr["half"] = np.where(tr.signal_date < H2, "H1", "H2")
    per = tr.groupby("si").size()
    tr["session_type"] = np.where(tr.si.map(per).to_numpy() == 1, "single", "multi")
    return tr, dict(n_stopped=nstop, stop_parity_max=worst)


def anatomy_parity(tr):
    """the trade set equals tools/noise_r422_anatomy.py build()'s, trade for trade (date, side, unit $ to the cent)"""
    import noise_r422_anatomy as NA
    T = NA.build()
    a = sorted(zip(pd.to_datetime(T.date).dt.strftime("%Y-%m-%d"), T.side, np.round(T.unit.to_numpy(float), 2)))
    b = sorted(zip(tr.signal_date.dt.strftime("%Y-%m-%d"), np.where(tr.side > 0, "long", "short"),
                   np.round(tr.unit_usd.to_numpy(float), 2)))
    if len(a) != len(b) or a != b:
        diff = len(set(a) ^ set(b))
        raise SystemExit("trade set differs from the #422 anatomy's build(): %d vs %d trades, %d keys apart - abort"
                         % (len(a), len(b), diff))
    return len(a)


# ================================================================== scores
def scores(tr):
    bars = PS.load_bars("NQ", history_from=HISTORY_FROM)
    t = np.asarray(bars.t, np.int64)
    sig = pd.DatetimeIndex(tr.signal_start)
    want = np.array([PS._epoch(x + pd.Timedelta(minutes=4)) for x in sig], np.int64)
    first = np.array([PS._epoch(x) for x in sig], np.int64)
    pos = np.searchsorted(t, want, side="right") - 1                 # latest 1m start <= t + 4 min
    ok = (pos >= 0) & (t[np.clip(pos, 0, None)] >= first)             # ... and inside [t, t + 4]
    exact = ok & (t[np.clip(pos, 0, None)] == want)
    out = pd.DataFrame(index=tr.index)
    out["bar_ok"], out["bar_exact"] = ok, exact
    keys = PS.KEYS
    for side, lab in (("LONG", 1), ("SHORT", -1)):
        f = bars.full(side)
        m = (tr.side.to_numpy() == lab)
        for kk in keys:
            hit = np.asarray(f[kk]["hit"], float)
            na = np.asarray(f[kk]["na"])
            col = np.full(len(tr), np.nan)
            cna = np.full(len(tr), "", dtype=object)
            sel = m & ok
            col[sel] = hit[pos[sel]]
            cna[sel] = [PS._REASONS[c] or "" for c in na[pos[sel]]]
            if kk + "_hit" in out:
                out.loc[sel, kk + "_hit"] = col[sel]
                out.loc[sel, kk + "_na"] = cna[sel]
            else:
                out[kk + "_hit"], out[kk + "_na"] = col, cna
    inf = np.full(len(tr), np.nan)
    nn = np.zeros(len(tr), int)
    for i, s in enumerate(tr.side.to_numpy()):
        if not ok[i]:
            continue
        v = np.array([out.at[i, k + "_hit"] for k in INFORMATIVE["LONG" if s > 0 else "SHORT"]], float)
        nn[i] = int(np.isfinite(v).sum())
        if nn[i]:
            inf[i] = np.nansum(v) / nn[i]
    out["n_informative"] = nn
    out["score_pct"] = inf
    return out


# ================================================================== statistics
def ranks(x):
    return pd.Series(x).rank(method="average").to_numpy()


def spearman(x, y):
    if len(x) < 3:
        return np.nan
    a, b = ranks(x), ranks(y)
    if a.std() == 0 or b.std() == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def null_rho(score, r, groups, draws=DRAWS, seed=SEED):
    """1,000 within-group shuffles of the scores (rank form: the score ranks are permuted inside each group)"""
    rs, rr = ranks(score), ranks(r)
    rr = (rr - rr.mean()) / rr.std()
    rng = np.random.default_rng(seed)
    gi = [np.flatnonzero(groups == g) for g in sorted(set(groups))]
    out = np.empty(draws)
    for d in range(draws):
        p = rs.copy()
        for ix in gi:
            p[ix] = p[ix[rng.permutation(len(ix))]]
        p = (p - p.mean()) / p.std()
        out[d] = float(np.mean(p * rr))
    return out


def null_block(D):
    """the null for every read: all, single, multi (each within July-June year), with its own seed offset"""
    res = {}
    for j, (name, m) in enumerate((("all", np.ones(len(D), bool)), ("single", D.session_type.to_numpy() == "single"),
                                   ("multi", D.session_type.to_numpy() == "multi"))):
        sub = D[m]
        nr = null_rho(sub.score_pct.to_numpy(), sub.R.to_numpy(), sub.jy.to_numpy(), seed=SEED + j)
        res[name] = {"n": int(len(sub)), "p50": float(np.percentile(nr, 50)), "p95": float(np.percentile(nr, 95)),
                     "p05": float(np.percentile(nr, 5)), "sd": float(nr.std())}
    return res


# ================================================================== modes
def build():
    tr, rpar = trades()
    n_an = anatomy_parity(tr)
    sc = scores(tr)
    D = pd.concat([tr.drop(columns=["dec"]), sc], axis=1)
    return D, rpar, n_an


def print_frame(D, rpar, n_an):
    say("PS-TAG r1 - NOISE #304 WF trades x the point score ps1.2 (REPORT; docs/REPORT_pstag_r1_2026-10-07.md)")
    say("  trades: %d WF (signal %s .. %s); = the #422 anatomy's build() trade for trade (%d)" % (
        len(D), D.signal_date.min().date(), D.signal_date.max().date(), n_an))
    say("  R parity: %d stopped trades sit exactly 1.75 x band width from the fill (max |diff| %.2g pts)" % (
        rpar["n_stopped"], rpar["stop_parity_max"]))
    say("  risk (pts): median %.1f, 5%%-95%% %.1f .. %.1f; single-trade sessions %d trades (%.0f%%), %.0f%% of unit $" % (
        D.risk_pts.median(), D.risk_pts.quantile(.05), D.risk_pts.quantile(.95), (D.session_type == "single").sum(),
        100 * (D.session_type == "single").mean(),
        100 * D.unit_usd[D.session_type == "single"].sum() / D.unit_usd.sum()))
    say("  1m bar: %d at signal start + 4 min, %d earlier inside the 5m bar, %d none" % (
        D.bar_exact.sum(), (D.bar_ok & ~D.bar_exact).sum(), (~D.bar_ok).sum()))
    say("  scored: %d of %d (no informative point: %d); informative points per trade: %s" % (
        D.score_pct.notna().sum(), len(D), (D.bar_ok & (D.n_informative == 0)).sum(),
        dict(sorted(D.n_informative.value_counts().items()))))
    say("  NA by point (count / top reason):")
    for k in PS.KEYS:
        na = D[k + "_na"].fillna("")
        top = na[na != ""].value_counts()
        say("    %-10s %5d  %s" % (k, int((na != "").sum()), (top.index[0] if len(top) else "")))
    say("  constant points (must be ~100% hit; never in the score):")
    for side, lab in (("LONG", 1), ("SHORT", -1)):
        sub = D[D.side == lab]
        say("    %-5s %s" % (side, "  ".join("%s %.4f" % (k, np.nanmean(sub[k + "_hit"])) for k in CONSTANT[side])))
    say("  score %% distribution: %s" % dict(sorted(D.score_pct.round(3).value_counts().items())))


def mode_power():
    D, rpar, n_an = build()
    print_frame(D, rpar, n_an)
    S = D[D.score_pct.notna()].reset_index(drop=True)
    nb = null_block(S)
    say("\nNULL (1,000 within-July-June-year shuffles of the score; seed %d; no real rho computed):" % SEED)
    for k, v in nb.items():
        say("  %-7s n %5d  p05 %+.4f  p50 %+.4f  p95 %+.4f  sd %.4f" % (k, v["n"], v["p05"], v["p50"], v["p95"], v["sd"]))
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "null.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "draws": DRAWS, "null": nb, "n_scored": int(len(S))}, f, indent=1)
    write_log("power")


def mode_read():
    p = os.path.join(OUTDIR, "null.json")
    if not os.path.exists(p):
        raise SystemExit("run --power first (null.json missing) - abort")
    saved = json.load(open(p, encoding="utf-8"))
    D, rpar, n_an = build()
    print_frame(D, rpar, n_an)
    S = D[D.score_pct.notna()].reset_index(drop=True)
    nb = null_block(S)
    for k in nb:
        if abs(nb[k]["p95"] - saved["null"][k]["p95"]) > 1e-12 or nb[k]["n"] != saved["null"][k]["n"]:
            raise SystemExit("the null differs from --power's null.json (%s) - abort" % k)
    rho = spearman(S.score_pct, S.R)
    h = {hh: spearman(S.score_pct[S.half == hh], S.R[S.half == hh]) for hh in ("H1", "H2")}
    passed = bool(rho > nb["all"]["p95"] and np.sign(h["H1"]) == np.sign(h["H2"]) and np.sign(h["H1"]) == np.sign(rho))
    say("\nREAD")
    say("  PRIMARY Spearman(score %%, R) = %+.4f  vs null p95 %+.4f  (n %d)" % (rho, nb["all"]["p95"], len(S)))
    say("  halves: H1 2016-07..2021-12 %+.4f (n %d)  H2 2022-01..2025-06 %+.4f (n %d)" % (
        h["H1"], (S.half == "H1").sum(), h["H2"], (S.half == "H2").sum()))
    say("  VERDICT: %s" % ("PASS - the score stays a label on crown signals (never a gate or size)" if passed else
                           "FAIL - the score retires as an algo input; it stays a journal aid"))
    med = float(S.score_pct.median())
    top, bot = S[S.score_pct > med], S[S.score_pct <= med]
    say("  secondary: score above the WF median %.3f: n %d mean R %+.3f | at or below: n %d mean R %+.3f" % (
        med, len(top), top.R.mean(), len(bot), bot.R.mean()))
    say("\nREPORTED (never a verdict)")
    for k in ("single", "multi"):
        sub = S[S.session_type == k]
        say("  %-6s sessions: rho %+.4f vs its null p95 %+.4f (n %d, mean R %+.3f)" % (
            k, spearman(sub.score_pct, sub.R), nb[k]["p95"], len(sub), sub.R.mean()))
    say("  Spearman(score %%, unit $) = %+.4f" % spearman(S.score_pct, S.unit_usd))
    say("  per point (hit rate; mean R hit / miss):")
    for side, lab in (("LONG", 1), ("SHORT", -1)):
        sub = S[S.side == lab]
        for kk in INFORMATIVE[side]:
            hv = sub[kk + "_hit"]
            say("    %-5s %-10s hit %.3f  R hit %+.3f  miss %+.3f  (n %d / %d)" % (
                side, kk, np.nanmean(hv), sub.R[hv == 1].mean(), sub.R[hv == 0].mean(), (hv == 1).sum(), (hv == 0).sum()))
    say("  per July-June year (n, rho):")
    say("    " + "  ".join("%d %d %+.3f" % (y, len(g), spearman(g.score_pct, g.R)) for y, g in S.groupby("jy")))
    os.makedirs(OUTDIR, exist_ok=True)
    keep = [c for c in D.columns if c not in ("dec",)]
    D[keep].to_csv(os.path.join(OUTDIR, "trades_scored.csv"), index=False)
    write_log("read")


def write_log(mode):
    os.makedirs(OUTDIR, exist_ok=True)
    txt = "\n".join(_lines) + "\n"
    with open(os.path.join(OUTDIR, "report_%s.txt" % mode), "w", encoding="utf-8") as f:
        f.write(txt)
    if mode == "read":
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "w", encoding="utf-8", newline="\n") as f:
            f.write(txt)


def main(argv=None):
    ap = argparse.ArgumentParser(description="PS-TAG r1 report")
    ap.add_argument("--power", action="store_true")
    a = ap.parse_args(argv)
    mode_power() if a.power else mode_read()


if __name__ == "__main__":
    main()
