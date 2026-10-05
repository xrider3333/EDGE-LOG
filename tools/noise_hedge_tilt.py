"""NOISE hedge tilt inside BOOK #463 - Stage A (walk-forward only; the lockbox is never read).
Pre-registration: docs/PREREG_noise_hedge_tilt_2026-10-04.md (+ addendum 2026-10-05, f6a98a51).

Every NOISE #422 trade is kept and re-sized from BOOK STATE at its fill: 1.5x when it is SHORT while the ENGU-Q leg
holds an open long, 0.5x when it is LONG on top of that open long, 1.0x otherwise. Judged inside #463 against plain
extra NOISE at the same average size (c matched on size), against the median placebo book (ENGU-Q's position
calendar circularly shifted inside the walk-forward), and on the RISK r1 checks.

    python tools/noise_hedge_tilt.py          (run with cwd = the shared checkout; EDGELOG_ROOT = it)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

W0, W1 = "2010-06-07", "2026-06-30"                               # book_q.py's window for every leg
WF0, WF1 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")
BLOCK0, BLOCK1 = pd.Timestamp("2011-01-01"), pd.Timestamp("2016-06-30")
COVID0, COVID1 = pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")
HEDGE, STACK, FLAT = 1.5, 0.5, 1.0
N_PLACEBO, SEED, SHIFT_LO, SHIFT_HI = 200, 20261004, 20, 250
OUT = r"C:\EdgeLog\custom_ml\hedge_tilt"


def naive_et(ix):
    ix = pd.DatetimeIndex(ix)
    return ix.tz_convert("US/Eastern").tz_localize(None) if ix.tz is not None else ix


def run_leg(leg):
    """The identical #463 leg run: book._leg_trades' own master resolution, window and cost; returns the raw engine
    trades, the arrays' Eastern index, open/close, and book._leg_trades' (exit_day, $) list for parity."""
    from augur_engine import book
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    tr_book, info = book._leg_trades(dict(leg), W0, W1)
    m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg.get("source"))
    assert m is not None, leg
    A = load_master_arrays(m, date_from=W0, date_to=W1)
    r = run_backtest(leg["strategy"], arrays=A, params=leg.get("params") or {},
                     cost_pts=float(leg.get("cost_pts", 0) or 0), return_trades=True)
    T = list(r["trades"])
    usd = np.array([float(t[2]) for t in T]) * float(leg["mult"]) * float(leg.get("weight", 1))
    assert len(tr_book) == len(T), (leg["strategy"], len(tr_book), len(T))
    assert abs(sum(v for _, v in tr_book) - usd.sum()) < 1.0, (leg["strategy"], sum(v for _, v in tr_book), usd.sum())
    return T, r, naive_et(A["index"]), np.asarray(A["open"], float), np.asarray(A["close"], float), tr_book, info


def fill_at_open(T, O, C):
    return np.array([abs(float(t[4]) - O[int(t[0])]) <= abs(float(t[4]) - C[int(t[0])]) for t in T], dtype=bool)


def engu_intervals(T, idx, O, C):
    """[(fill, exit_start)] of ENGU-Q longs, Eastern. Fill = entry bar open if filled at the open, else bar end
    (label + 1 min); exit placed at the exit bar's START (an exit in the decision minute counts as flat)."""
    side = np.array([float(t[3]) for t in T])
    assert (side > 0).all(), f"ENGU-Q short entries found: {(side <= 0).sum()} - write the symmetric rule first"
    op = fill_at_open(T, O, C)
    ent = idx[[int(t[0]) for t in T]] + pd.to_timedelta(np.where(op, 0, 1), unit="min")
    ext = idx[[min(int(t[1]), len(idx) - 1) for t in T]]
    return np.array(ent, dtype="datetime64[ns]"), np.array(ext, dtype="datetime64[ns]")


def open_at(t_noise, e_fill, e_exit):
    """Boolean per NOISE decision time: some ENGU-Q long has fill <= t and exit bar start > t."""
    order = np.argsort(e_fill)
    ef, ex = e_fill[order], e_exit[order]
    run_max_exit = np.maximum.accumulate(ex)                      # intervals sorted by fill
    k = np.searchsorted(ef, t_noise, side="right") - 1            # last interval with fill <= t
    out = np.zeros(len(t_noise), dtype=bool)
    ok = k >= 0
    out[ok] = run_max_exit[k[ok]] > t_noise[ok]
    return out


def multipliers(side, eopen):
    return np.where(eopen & (side < 0), HEDGE, np.where(eopen & (side > 0), STACK, FLAT))


def roc_sortino(M, lo, hi, drop=None):
    """Unified convention: valued-daily net and drawdown inside the stretch, years = (last - first) / 365.25."""
    x = M[(M.index >= lo) & (M.index <= hi)]
    if drop is not None:
        x = x[~((x.index >= drop[0]) & (x.index <= drop[1]))]
    yrs = (x.index.max() - x.index.min()).days / 365.25
    q = np.cumsum(x.values)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max())
    dn = np.sqrt(np.mean(np.minimum(x.values, 0.0) ** 2))
    return 30.0 * (x.sum() / yrs) / dd if dd > 0 else float("nan"), float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def daily(pairs):
    from augur_engine import book
    d, v = book._daily(pairs)
    return pd.Series(v, index=pd.to_datetime(d)).groupby(level=0).sum() if len(d) else pd.Series(dtype=float)


def main():
    import bookline_paired_stop as BL
    import keel_422_stack_check as S
    from api.book_shadow import BOOK463_LEGS
    os.makedirs(OUT, exist_ok=True)
    L_n = [l for l in BOOK463_LEGS if l["strategy"].startswith("NOISE")][0]
    L_e = [l for l in BOOK463_LEGS if l["strategy"].startswith("ENGUQ")][0]

    # ---- the identical leg runs + parity ----
    Tn, rn, idx_n, On, Cn, trn_book, _ = run_leg(L_n)
    Te, _, idx_e, Oe, Ce, _, _ = run_leg(L_e)
    usd_n = np.array([float(t[2]) for t in Tn]) * float(L_n["mult"]) * float(L_n.get("weight", 1))
    assert np.allclose([v for _, v in trn_book], usd_n, atol=0.01), "NOISE book order differs from the engine order"
    op_n = fill_at_open(Tn, On, Cn)
    t_n = np.array(idx_n[[int(t[0]) for t in Tn]], dtype="datetime64[ns]")   # NOISE fill = decision time
    side_n = np.array([1.0 if float(t[3]) > 0 else -1.0 for t in Tn])
    s422 = np.asarray(S.plugin_sizes(rn, len(Tn)), float)
    e_fill, e_exit = engu_intervals(Te, idx_e, Oe, Ce)

    # ---- book series ----
    days = pd.bdate_range(W0, W1)
    M = {}
    for leg in BOOK463_LEGS:
        c, m = BL.leg_series(leg)
        M[leg["strategy"]] = m
        days = days.union(c.index).union(m.index)
    book = sum(s.reindex(days).fillna(0.0) for s in M.values())
    noise_d = M[L_n["strategy"]].reindex(days).fillna(0.0)
    assert abs(noise_d.sum() - usd_n.sum()) < 1.0
    other = book - noise_d
    base = roc_sortino(book, WF0, WF1)

    def book_with(mult_vec):
        nd = daily([(d, v * mm) for (d, v), mm in zip(trn_book, mult_vec)]).reindex(days).fillna(0.0)
        return other + nd

    wf_tr = (t_n >= np.datetime64(WF0)) & (t_n <= np.datetime64(WF1 + pd.Timedelta(days=1)))

    def arm_and_twin(eopen):
        m = multipliers(side_n, eopen)
        c = float((m[wf_tr] * s422[wf_tr]).mean() / s422[wf_tr].mean())
        return book_with(m), book_with(np.full(len(m), c)), m, c

    eopen = open_at(t_n, e_fill, e_exit)
    B_arm, B_twin, m_arm, c_arm = arm_and_twin(eopen)

    # ---- placebos: ENGU-Q calendar circularly shifted by k sessions, wrapped inside the WF window ----
    sess = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(idx_e).normalize())))
    sess = sess[(sess >= WF0) & (sess <= WF1)]
    N = len(sess)
    pos = {d: i for i, d in enumerate(sess)}
    wf_e = (e_fill >= np.datetime64(WF0)) & (e_exit <= np.datetime64(WF1 + pd.Timedelta(days=1)))

    def shift(ts, k):
        t = pd.DatetimeIndex(ts)
        d = t.normalize()
        i = np.array([pos.get(x, -1) for x in d])
        j = (i + k) % N
        return np.array(sess[j] + (t - d), dtype="datetime64[ns]"), i

    rng = np.random.default_rng(SEED)
    pl = []
    for _ in range(N_PLACEBO):
        k = int(rng.integers(SHIFT_LO, SHIFT_HI + 1))
        f2, i1 = shift(e_fill[wf_e], k)
        x2, i2 = shift(e_exit[wf_e], k)
        keep = (i1 >= 0) & (i2 >= 0) & (x2 > f2)                    # intervals that wrap across the seam are dropped
        eo = open_at(t_n, f2[keep], x2[keep]) & wf_tr
        Ba, Bt, _, cp = arm_and_twin(eo)
        ra, sa = roc_sortino(Ba, WF0, WF1)
        rt, st = roc_sortino(Bt, WF0, WF1)
        rna, _ = roc_sortino(Ba, WF0, WF1, drop=(COVID0, COVID1))
        rnt, _ = roc_sortino(Bt, WF0, WF1, drop=(COVID0, COVID1))
        pl.append(dict(k=k, c=cp, lead_roc=ra - rt, lead_sort=sa - st, lead_roc_no2020=rna - rnt))
    pl = pd.DataFrame(pl)

    # ---- the bars ----
    ra, sa = roc_sortino(B_arm, WF0, WF1)
    rt, st = roc_sortino(B_twin, WF0, WF1)
    rna, _ = roc_sortino(B_arm, WF0, WF1, drop=(COVID0, COVID1))
    rnt, _ = roc_sortino(B_twin, WF0, WF1, drop=(COVID0, COVID1))
    rba, _ = roc_sortino(B_arm, BLOCK0, BLOCK1)
    rbt, _ = roc_sortino(B_twin, BLOCK0, BLOCK1)
    years = []
    for y in range(2016, 2025):
        lo, hi = pd.Timestamp(f"{y}-07-01"), pd.Timestamp(f"{y + 1}-06-30")
        years.append(roc_sortino(B_arm, lo, hi)[0] > roc_sortino(B_twin, lo, hi)[0])
    med = pl.median(numeric_only=True)
    p95 = float(np.percentile(pl.lead_roc, 95))
    n_tilted = int(((m_arm != FLAT) & wf_tr).sum())
    bars = {
        "1 beats twin AND #463 on WF ROC + Sortino, and lead > median placebo": bool(
            ra > rt and ra > base[0] and sa > st and sa > base[1]
            and (ra - rt) > med.lead_roc and (sa - st) > med.lead_sort),
        "2 no Feb-Apr 2020: beats twin, lead > median placebo": bool(rna > rnt and (rna - rnt) > med.lead_roc_no2020),
        "3 beats twin in >= 6 of 9 WF years": bool(sum(years) >= 6),
        "4 untuned 2011-01..2016-06 block beats twin": bool(rba > rbt),
        "5 WF ROC lead above placebo 95th pct": bool((ra - rt) > p95),
        "6 >= 100 tilted WF trades": bool(n_tilted >= 100),
    }
    verdict = all(bars.values())

    # ---- attribution (reported regardless) ----
    st_lab = np.where(eopen, np.where(side_n < 0, "hedge (short, ENGU-Q long)", "stacked (long, ENGU-Q long)"),
                      np.where(side_n < 0, "flat short", "flat long"))
    att = pd.DataFrame({"state": st_lab[wf_tr], "usd": usd_n[wf_tr]}).groupby("state").usd.agg(["count", "mean", "sum"])

    lines = [
        f"#463 parity, WF {WF0.date()}..{WF1.date()}: ROC@$30k {base[0]:.1f}  Sortino {base[1]:.2f}  (reference 93.8 / 3.82)",
        f"arm  WF ROC {ra:.1f} Sortino {sa:.2f} | twin (plain extra NOISE x{c_arm:.4f}) ROC {rt:.1f} Sortino {st:.2f}",
        f"lead over twin: ROC {ra - rt:+.2f}  Sortino {sa - st:+.3f} | placebo median ROC {med.lead_roc:+.2f} Sortino "
        f"{med.lead_sort:+.3f}; placebo ROC lead 5th/50th/95th pct {np.percentile(pl.lead_roc, 5):+.2f} / "
        f"{med.lead_roc:+.2f} / {p95:+.2f}; arm's percentile {100 * (pl.lead_roc < ra - rt).mean():.1f}",
        f"no Feb-Apr 2020: arm {rna:.1f} vs twin {rnt:.1f} (lead {rna - rnt:+.2f}; placebo median {med.lead_roc_no2020:+.2f})",
        f"WF years arm > twin: {sum(years)}/9 {years}",
        f"2011-01..2016-06 block: arm {rba:.1f} vs twin {rbt:.1f}",
        f"tilted WF trades {n_tilted}; WF NOISE trades {int(wf_tr.sum())}",
        "WF NOISE $ per trade by state:\n" + att.round(1).to_string(),
    ] + [f"  [{'PASS' if v else 'fail'}] {k}" for k, v in bars.items()] + [
        "STAGE A VERDICT: " + ("PASS -> MANAGER for the lockbox step" if verdict else "FAIL - dead, no variants (registered)")]
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "STAGE_A.txt"), "w", encoding="utf-8").write(txt + "\n")

    # ---- POST-HOC (reviews #54 / #55 arrived after the addendum froze; reported, never change the verdict) ----
    post = []
    # MANAGER #54: side-matched twin = 1.5x every short, 0.5x every long regardless of ENGU-Q, rescaled to c_arm
    m_side = np.where(side_n < 0, HEDGE, STACK)
    m_side = m_side * c_arm / float((m_side[wf_tr] * s422[wf_tr]).mean() / s422[wf_tr].mean())
    rs_, ss_ = roc_sortino(book_with(m_side), WF0, WF1)
    post.append(f"side-matched twin (all shorts x{m_side[side_n < 0][0]:.3f}, all longs x{m_side[side_n > 0][0]:.3f}): "
                f"WF ROC {rs_:.1f} Sortino {ss_:.2f} | arm lead over it ROC {ra - rs_:+.2f} Sortino {sa - ss_:+.3f}")
    # ORB #55 (2): placebo minimum shift above the longest ENGU-Q hold
    hold_days = (pd.DatetimeIndex(e_exit[wf_e]).normalize() - pd.DatetimeIndex(e_fill[wf_e]).normalize()).days
    rng2, pl60 = np.random.default_rng(SEED), []
    for _ in range(N_PLACEBO):
        k = int(rng2.integers(60, SHIFT_HI + 1))
        f2, i1 = shift(e_fill[wf_e], k)
        x2, i2 = shift(e_exit[wf_e], k)
        keep = (i1 >= 0) & (i2 >= 0) & (x2 > f2)
        Ba, Bt, _, _ = arm_and_twin(open_at(t_n, f2[keep], x2[keep]) & wf_tr)
        pl60.append(roc_sortino(Ba, WF0, WF1)[0] - roc_sortino(Bt, WF0, WF1)[0])
    pl60 = np.array(pl60)
    post.append(f"longest WF ENGU-Q hold {int(hold_days.max())} calendar days; placebos with shift 60..250 sessions: "
                f"ROC lead 5th/50th/95th {np.percentile(pl60, 5):+.2f} / {np.median(pl60):+.2f} / "
                f"{np.percentile(pl60, 95):+.2f}; arm's percentile {100 * (pl60 < ra - rt).mean():.1f}")
    # ORB #55 (1): tilted-minus-twin $ inside ENGU-Q's 5 biggest winning holds and 5 biggest give-backs
    usd_e = np.array([float(t[2]) for t in Te]) * float(L_e["mult"]) * float(L_e.get("weight", 1))
    ef, ex, ue = e_fill[wf_e], e_exit[wf_e], usd_e[wf_e]
    gap = (m_arm - c_arm) * usd_n
    for lab, sel in (("5 biggest ENGU-Q winners", np.argsort(-ue)[:5]), ("5 biggest ENGU-Q losers", np.argsort(ue)[:5])):
        rows = [f"{pd.Timestamp(ef[i]).date()} ENGU-Q ${ue[i]:+,.0f}: NOISE tilt-minus-twin "
                f"${gap[(t_n >= ef[i]) & (t_n < ex[i])].sum():+,.0f}" for i in sel]
        post.append(lab + ":\n    " + "\n    ".join(rows))
    # ORB #55 (3): power - ENGU-Q-long-state NOISE trades inside #463's WF drawdown episodes
    eps = [("2020-02-01", "2020-04-30"), ("2022-01-01", "2022-12-31"), ("2025-01-01", "2025-06-29")]
    for a, b in eps:
        k = (t_n >= np.datetime64(a)) & (t_n <= np.datetime64(pd.Timestamp(b) + pd.Timedelta(days=1)))
        post.append(f"DD episode {a}..{b}: NOISE trades {int(k.sum())}, with ENGU-Q long {int((k & eopen).sum())} "
                    f"(hedge {int((k & eopen & (side_n < 0)).sum())}); tilt-minus-twin ${gap[k].sum():+,.0f}")
    ptxt = "POST-HOC (cannot change the verdict)\n" + "\n".join(post)
    print(ptxt)
    open(os.path.join(OUT, "POSTHOC.txt"), "w", encoding="utf-8").write(ptxt + "\n")
    pl.to_csv(os.path.join(OUT, "placebos.csv"), index=False)
    pd.DataFrame({"t_fill": t_n, "side": side_n, "s422": s422, "engu_open": eopen, "m": m_arm, "usd": usd_n,
                  "fill_at_open": op_n}).to_csv(os.path.join(OUT, "noise_trades.csv"), index=False)
    return verdict


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
