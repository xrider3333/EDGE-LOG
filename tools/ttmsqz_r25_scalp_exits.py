"""TTM round 25 - PnL scatter + scalp (profit-target) exits on TTM #459 (owner order 10-12 via MANAGER #104).

The #459 file (TTMSQZ_3_0_ES30SSOF2.py) runs its trades through the structural-stop module's `_simulate`. This driver
loads its own copy of the chain and swaps that function for `t_simulate` below - the same loop line for line as the
round-22 copy with its rule off - plus (a) a per-trade record of MFE / MAE / hold / exit kind and (b) an optional profit
target: a resting limit at entry +/- k x R, where R = |entry - initial structural stop|. Fill rules, all conservative:
the stop is tested before the target in the same bar (both touched in one bar = the stop); a bar that OPENS beyond the
target fills at the open; on the entry bar the target can fill only if the bar's range reaches it (stop first, as above).
With no target the copy must reproduce the twin to the trade.

  python tools/ttmsqz_r25_scalp_exits.py design   IS ONLY (2010-06-07 .. 2016-06-29, #459's tuning stretch): scatter + targets
  python tools/ttmsqz_r25_scalp_exits.py nowork   IS ONLY: the causal 'not working' exit (out after bar N if < +0.25R)
  python tools/ttmsqz_r25_scalp_exits.py wfscatter  DESCRIPTIVE WF scatter (no variant run on WF), read after both lines closed

RESULT 2026-10-12 (owner order via MANAGER #104): both exit lines CLOSED AT DRAFT by the power-first gate - every
variant loses money on the tuning years, and WF could only detect >= ~$500-900 a year per contract. No WF variant run,
no lockbox. Log: tools/data/ttmsqz_r25_scalp_exits.txt.

OWNER OVERRIDE 2026-10-12 (MANAGER #107: "what was the roc/yr on those tested"): `wfcells` runs every cell on WF
2016-06-30 .. 2025-06-30 (lockbox still not read), at the real and the house cost. Log: tools/data/ttmsqz_r25_wf_cells.txt.
Every cell is below #459 on ROC, Sortino and money.
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

SHARED = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
os.chdir(SHARED)
sys.path.insert(0, SHARED)
sys.path.insert(0, os.path.join(SHARED, "tools"))
from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.drawdowns import dd5 as house_dd5, dd_pct_peak  # noqa: E402


def _imp(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


L459 = _imp("TTMSQZ_3_0_ES30SSOF2_r25", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2.py"))
SS = L459._so._ss
ORIG = SS._simulate
PARAMS = dict(kc_mult=1.5, eod_cutoff=1, gate_len=20)
MULT = 50.0
COST_HOUSE = 0.363                       # pts per round trip = $5.65 commission + 1 tick in total (house ES convention)
COST_REAL = 0.25 * 2 + 5.65 / MULT       # owner's rule: commission + 1 tick slippage EACH side = 0.613 pts
D0, IS_END, WF0, WF_END = "2010-06-07", "2016-06-29", "2016-06-30", "2025-06-30"
REC = []


def make_sim(k=None, nowork=None):
    """k = profit target in R (None = no target). Appends one dict per trade to REC (cleared by run())."""
    def t_simulate(o, h, l, c, n, warm, mom, atr, fire, rng_hi, rng_lo, gate_long, gate_short,
                   last_bar, fade_bars, eod_cutoff, struct_buf, direction):
        pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
        stop_px = None; tgt = None
        fade_cnt = 0
        pending = None
        trade_log = []
        risk = 0.0; hi_x = lo_x = 0.0

        def _book(exit_i, px, sd, ep, eb, kind):
            p = (px - ep) if sd > 0 else (ep - px)
            trade_log.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(px)))
            mfe = (hi_x - ep) if sd > 0 else (ep - lo_x)
            mae = (ep - lo_x) if sd > 0 else (hi_x - ep)
            REC.append(dict(eb=int(eb), xb=int(exit_i), side=int(sd), ep=float(ep), xp=float(px), pts=float(p),
                            risk=float(risk), mfe=float(max(mfe, p, 0.0)), mae=float(max(mae, -p, 0.0)),
                            hold=int(exit_i - eb), kind=kind))

        def _touch(u):
            nonlocal hi_x, lo_x
            hi_x = max(hi_x, h[u]); lo_x = min(lo_x, l[u])

        for u in range(warm, n):
            eod = u == last_bar[u]
            if pending is not None:
                kind = pending[0]
                if kind == "exit":
                    if pos != 0:
                        hi_x = max(hi_x, o[u]); lo_x = min(lo_x, o[u])
                        _book(u, o[u], pos, entry_px, entry_bar, "fade")
                        pos = 0; stop_px = None
                    pending = None
                else:
                    if pos == 0:
                        side = pending[1]; rh, rl = pending[2], pending[3]
                        pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                        stop_px = (rl - struct_buf) if side > 0 else (rh + struct_buf)
                        risk = abs(entry_px - stop_px)
                        tgt = (entry_px + side * k * risk) if (k is not None and risk > 0) else None
                        hi_x = lo_x = entry_px
                        if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                                   (side < 0 and h[u] >= stop_px)):
                            _touch(u)
                            px = min(o[u], stop_px) if side > 0 else max(o[u], stop_px)
                            _book(u, px, pos, entry_px, entry_bar, "stop")
                            pos = 0; stop_px = None
                        elif tgt is not None and ((side > 0 and h[u] >= tgt) or (side < 0 and l[u] <= tgt)):
                            _touch(u)
                            _book(u, tgt, pos, entry_px, entry_bar, "target")
                            pos = 0; stop_px = None
                    pending = None

            if pos != 0 and u > entry_bar and stop_px is not None:
                if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                    _touch(u)
                    px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                    _book(u, px, pos, entry_px, entry_bar, "stop")
                    pos = 0; stop_px = None
                elif tgt is not None and ((pos > 0 and h[u] >= tgt) or (pos < 0 and l[u] <= tgt)):
                    _touch(u)
                    px = max(o[u], tgt) if pos > 0 else min(o[u], tgt)
                    _book(u, px, pos, entry_px, entry_bar, "target")
                    pos = 0; stop_px = None

            if pos != 0 and u > entry_bar:
                _touch(u)
            elif pos != 0 and u == entry_bar:
                _touch(u)

            if eod:
                if pos != 0:
                    _book(u, c[u], pos, entry_px, entry_bar, "eod")
                    pos = 0; stop_px = None
                pending = None
                continue

            m, m1 = mom[u], mom[u - 1]
            if not (np.isfinite(m) and np.isfinite(m1)):
                continue

            if pos != 0 and nowork is not None and (u - entry_bar) == nowork[0] - 1 and risk > 0:
                best = (hi_x - entry_px) if pos > 0 else (entry_px - lo_x)
                if best < nowork[1] * risk:
                    pending = ("exit",)
                    continue

            if pos != 0:
                fading = (m < m1) if pos > 0 else (m > m1)
                fade_cnt = fade_cnt + 1 if fading else 0
                if fade_cnt >= fade_bars:
                    pending = ("exit",)
                    continue

            if pos == 0 and pending is None and fire[u] and m != 0:
                sd = 1 if m > 0 else -1
                if direction == "long" and sd < 0:
                    continue
                if direction == "short" and sd > 0:
                    continue
                if sd > 0 and not gate_long[u]:
                    continue
                if sd < 0 and not gate_short[u]:
                    continue
                if last_bar[u] - u <= eod_cutoff:
                    continue
                pending = ("mkt", sd, rng_hi[u], rng_lo[u])
        return trade_log
    return t_simulate


def run(arr, sim):
    REC.clear()
    SS._simulate = sim
    try:
        r = L459.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"], day_id=arr["day_id"],
                              index=arr["index"], return_trades=True, **PARAMS)
    finally:
        SS._simulate = ORIG
    return r["trades"], list(REC)


def frame(rec, idx):
    D = pd.DataFrame(rec)
    D["entry"] = idx[D.eb.to_numpy()]
    D["exit_day"] = idx[D.xb.to_numpy()].normalize()
    D["mfe_R"] = np.where(D.risk > 0, D.mfe / D.risk, np.nan)
    D["mae_R"] = np.where(D.risk > 0, D.mae / D.risk, np.nan)
    D["pts_R"] = np.where(D.risk > 0, D.pts / D.risk, np.nan)
    return D


def four(D, cost, d0, d1, cal):
    """Yardstick on the stretch's zero-filled daily series (exit day): ROC@30k, DD5, DD% from peak, Sortino, + trade stats."""
    S = D[(D.entry >= pd.Timestamp(d0)) & (D.entry < pd.Timestamp(d1) + pd.Timedelta(days=1))]
    usd = (S.pts - cost) * MULT
    rows = cal[(cal >= pd.Timestamp(d0)) & (cal <= max(pd.Timestamp(d1), S.exit_day.max() if len(S) else pd.Timestamp(d1)))]
    s = pd.Series(usd.to_numpy(), index=S.exit_day).groupby(level=0).sum().reindex(rows, fill_value=0.0)
    cum = np.r_[0.0, s.cumsum().to_numpy()]
    dd = float((np.maximum.accumulate(cum) - cum).max())
    yrs = (pd.Timestamp(d1) - pd.Timestamp(d0)).days / 365.25
    neg = np.minimum(s.to_numpy(), 0.0)
    dsd = np.sqrt((neg ** 2).mean())
    w, lo = usd[usd > 0], usd[usd <= 0]
    return dict(n=len(S), net=float(usd.sum()), roc=30.0 * (usd.sum() / yrs) / dd if dd > 0 else float("nan"),
                dd=dd, dd5=float(house_dd5(s)["dd5_usd"]), ddpk=float(dd_pct_peak(s, start=100_000)),
                sortino=float(s.mean() / dsd * np.sqrt(252)) if dsd > 0 else float("nan"),
                win=float((usd > 0).mean() * 100) if len(usd) else float("nan"),
                aw=float(w.mean()) if len(w) else 0.0, al=float(-lo.mean()) if len(lo) else 0.0, s=s)


def fmt(x):
    return ("n %3d  net $%8s  ROC@30k %6.2f  DD5 $%6s  DD%%pk %5.1f%%  Sortino %5.2f | win %5.1f%%  avg win $%5s / avg loss $%5s (x%.2f)"
            % (x["n"], format(round(x["net"]), ","), x["roc"], format(round(x["dd5"]), ","), x["ddpk"], x["sortino"], x["win"],
               format(round(x["aw"]), ","), format(round(x["al"]), ","), x["aw"] / x["al"] if x["al"] else float("nan")))


def load():
    arr = load_master_arrays(find_master("ES", "30m", "rth", "db_adj_rth"), date_from=D0, date_to=WF_END)
    idx = pd.DatetimeIndex(arr["index"])
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    cal = pd.DatetimeIndex(sorted(set(idx.normalize())))
    return arr, idx, cal


def design():
    arr, idx, cal = load()
    twin = run(arr, ORIG)[0]
    tr0, rec0 = run(arr, make_sim(None))
    same = len(twin) == len(tr0) and all(tuple(a) == tuple(b) for a, b in zip(twin, tr0))
    print("PARITY copy (no target) == #459 twin to the trade: %s (%d trades through %s)" % (same, len(twin), WF_END))
    if not same:
        raise SystemExit("parity failed")
    D = frame(rec0, idx)
    I = D[D.entry <= pd.Timestamp(IS_END)]
    print("\n=== DESIGN READ - IS ONLY (%s .. %s, #459's tuning stretch): %d trades ===" % (D0, IS_END, len(I)))
    for lab, cost in (("house cost 0.363 pt", COST_HOUSE), ("real cost 0.613 pt", COST_REAL)):
        print("  #459 as is, %-19s %s" % (lab, fmt(four(D, cost, D0, IS_END, cal))))
    net = (I.pts - COST_REAL) * MULT
    win, los = I[net > 0], I[net <= 0]
    print("\n  SCATTER (IS, real cost): winners %d, losers %d" % (len(win), len(los)))
    q = [0.1, 0.25, 0.5, 0.75, 0.9]
    print("  MFE in R   winners q10/25/50/75/90: %s" % " / ".join("%.2f" % v for v in win.mfe_R.quantile(q)))
    print("  MFE in R   losers  q10/25/50/75/90: %s" % " / ".join("%.2f" % v for v in los.mfe_R.quantile(q)))
    print("  MAE in R   winners q10/25/50/75/90: %s" % " / ".join("%.2f" % v for v in win.mae_R.quantile(q)))
    print("  final in R winners q10/25/50/75/90: %s" % " / ".join("%.2f" % v for v in win.pts_R.quantile(q)))
    for t in (0.25, 0.5, 0.75, 1.0):
        print("  losers that were >= +%.2fR first: %3d of %d (%.0f%%); winners that reached it: %d of %d" % (
            t, int((los.mfe_R >= t).sum()), len(los), 100 * (los.mfe_R >= t).mean(), int((win.mfe_R >= t).sum()), len(win)))
    print("  give-back (MFE - final, pts) winners median %.2f / losers median %.2f; R median %.2f pts" % (
        (win.mfe - win.pts).median(), (los.mfe - los.pts).median(), I.risk.median()))
    print("  hold bars median winners %d / losers %d; corr(net, hold) %.2f; exit kinds %s" % (
        win.hold.median(), los.hold.median(), np.corrcoef(net, I.hold)[0, 1], I.kind.value_counts().to_dict()))
    print("  by MFE bucket (R): n / win%% / mean net $")
    for a, b in ((0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 99)):
        B = I[(I.mfe_R >= a) & (I.mfe_R < b)]
        nb = (B.pts - COST_REAL) * MULT
        print("    [%.2f, %.2f): %3d / %5.1f%% / %+7.0f" % (a, b, len(B), 100 * (nb > 0).mean() if len(B) else float("nan"),
                                                       nb.mean() if len(B) else float("nan")))
    print("\n  TARGET WHAT-IFS (IS only; same fires, the loop re-runs so an early exit can free a later entry):")
    base = four(D, COST_REAL, D0, IS_END, cal)
    for k in (0.25, 0.5, 0.75, 1.0, 1.5):
        _, rk = run(arr, make_sim(k))
        Dk = frame(rk, idx)
        x = four(Dk, COST_REAL, D0, IS_END, cal)
        diff = (x["s"] - base["s"].reindex(x["s"].index, fill_value=0.0))
        print("  k %.2fR  %s | targets hit %d | daily diff sd $%.0f" % (
            k, fmt(x), int((Dk[Dk.entry <= pd.Timestamp(IS_END)].kind == "target").sum()), diff.std(ddof=1)))
    print("\n  POWER: WF = %d trading years; MDE ($/yr, 80%% power, 2-sided 5%%) = 2.8 x daily-diff sd x sqrt(252) / sqrt(years)" % 9)



def nowork_design():
    arr, idx, cal = load()
    _, rec0 = run(arr, make_sim(None))
    base = four(frame(rec0, idx), COST_REAL, D0, IS_END, cal)
    print("IS twin  %s" % fmt(base))
    for N in (2, 3, 4):
        for thr in (0.25,):
            _, rk = run(arr, make_sim(None, (N, thr)))
            Dk = frame(rk, idx)
            x = four(Dk, COST_REAL, D0, IS_END, cal)
            diff = (x["s"] - base["s"].reindex(x["s"].index, fill_value=0.0))
            mde = 2.8 * diff.std(ddof=1) * np.sqrt(252) / np.sqrt(9)
            print("N %d thr %.2fR %s | daily diff sd $%.0f -> WF MDE ~$%.0f/yr; IS gain $%.0f/yr" % (
                N, thr, fmt(x), diff.std(ddof=1), mde, (x["net"] - base["net"]) / 6.06))



def wf_scatter():
    """Descriptive WF scatter of #459 (no exit variant is run on WF)."""
    arr, idx, cal = load()
    _, rec = run(arr, make_sim(None))
    D = frame(rec, idx)
    W = D[(D.entry >= pd.Timestamp(WF0)) & (D.entry <= pd.Timestamp(WF_END))]
    print("WF %s .. %s: %d trades" % (WF0, WF_END, len(W)))
    for lab, cost in (("house", COST_HOUSE), ("real", COST_REAL)):
        print("  #459 WF %-5s %s" % (lab, fmt(four(D, cost, WF0, WF_END, cal))))
    net = (W.pts - COST_REAL) * MULT
    win, los = W[net > 0], W[net <= 0]
    q = [0.1, 0.25, 0.5, 0.75, 0.9]
    print("  MFE R winners: %s" % " / ".join("%.2f" % v for v in win.mfe_R.quantile(q)))
    print("  MFE R losers : %s" % " / ".join("%.2f" % v for v in los.mfe_R.quantile(q)))
    for a, b in ((0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 99)):
        B = W[(W.mfe_R >= a) & (W.mfe_R < b)]
        nb = (B.pts - COST_REAL) * MULT
        print("    MFE [%.2f, %.2f)R: %3d / win %5.1f%% / sum $%+8.0f" % (a, b, len(B), 100 * (nb > 0).mean(), nb.sum()))
    top = net.sort_values(ascending=False)
    print("  top 10%% of trades = %.0f%% of net" % (100 * top.head(max(1, len(top) // 10)).sum() / net.sum()))



def wf_cells():
    """OWNER OVERRIDE 10-12: every r25 cell on WF, real and house cost (lockbox not read)."""
    arr, idx, cal = load()
    cells = [("#459 twin (as traded)", None, None)] + [("target +%.2fR" % k, k, None) for k in (0.25, 0.5, 0.75, 1.0, 1.5)] + \
            [("not working by bar %d" % nn, None, (nn, 0.25)) for nn in (2, 3, 4)]
    for lab, cost in (("REAL COST 0.613 pt (commission + 1 tick each side)", COST_REAL), ("house cost 0.363 pt", COST_HOUSE)):
        print("\n=== WF %s .. %s, %s ===" % (WF0, WF_END, lab))
        base = None
        for name, k, nw in cells:
            _, rk = run(arr, make_sim(k, nw))
            x = four(frame(rk, idx), cost, WF0, WF_END, cal)
            base = base or x
            print("  %-24s %s | $/yr %+6.0f vs twin" % (name, fmt(x), (x["net"] - base["net"]) / 9.0))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "design"
    if mode == "design":
        design()
    elif mode == "nowork":
        nowork_design()
    elif mode == "wfscatter":
        wf_scatter()
    elif mode == "wfcells":
        wf_cells()
    else:
        raise SystemExit("closed at draft - no Stage A")
