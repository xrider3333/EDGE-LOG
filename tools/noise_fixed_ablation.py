"""NOISE 09-27 'fixed' package, leave-one-out inside BOOK #463 - Stage A (walk-forward only; the lockbox is never read).
Pre-registration: docs/PREREG_noise_fixed_ablation_2026-10-05.md.

The package (ml_keel.compression_sizes with v12's fixed settings, no model) on top of #422's own sizes: KEEL's 60-minute
squeeze x1.5, Friday x1.5, FOMC pre-statement x0.5, cap 3 (never binds). Each arm re-sizes #463's NOISE leg and is
judged inside the book against its OWN twin = the NOISE leg scaled to the same mean size (plain extra NOISE); the
singles also against 1,000 shuffles of their own multipliers (aim, not shape) and the RISK r1 checks.

    python tools/noise_fixed_ablation.py      (run with cwd = the shared checkout; EDGELOG_ROOT = it)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_hedge_tilt as H                                          # noqa: E402  same leg runs + book convention

OUT = r"C:\EdgeLog\custom_ml\fixed_ablation"
N_SHUF, SEED = 1000, 20261005
PCT = 100 * (1 - 0.05 / 3)                                            # 95% over the three singles
SINGLES = ("squeeze", "Friday", "FOMC")


def arms_sizes(A, T):
    from augur_engine import ml_keel as K
    ev = dict(K.CFG["v12"]["event"])
    dow = {k: v for k, v in K.CFG["v12"]["dow"].items() if k != "cap"}
    cap = float(K.CFG["v12"]["comp"]["cap"])
    spec = {
        "P": (1.5, dow, ev), "P-squeeze": (1.0, dow, ev), "P-Friday": (1.5, None, ev), "P-FOMC": (1.5, dow, None),
        "squeeze": (1.5, None, None), "Friday": (1.0, dow, None), "FOMC": (1.0, None, ev),
    }
    return {k: np.asarray(K.compression_sizes(A, T, mult=mu, dow=d, cap=cap, event=e), float)
            for k, (mu, d, e) in spec.items()}


def main():
    import bookline_paired_stop as BL
    import keel_422_stack_check as S
    from api.book_shadow import BOOK463_LEGS
    from augur_engine.data import find_master, load_master_arrays
    os.makedirs(OUT, exist_ok=True)
    L_n = [l for l in BOOK463_LEGS if l["strategy"].startswith("NOISE")][0]

    # ---- the identical #463 NOISE leg run + parity ----
    Tn, rn, idx_n, _, _, trn_book, _ = H.run_leg(L_n)
    A = load_master_arrays(find_master(L_n["instrument"], L_n["timeframe"], L_n["session"], L_n.get("source")),
                           date_from=H.W0, date_to=H.W1)
    ent = np.array([int(t[0]) for t in Tn])
    assert (np.diff(ent) >= 0).all(), "engine order is not entry order (compression_sizes sorts by entry)"
    usd = np.array([float(t[2]) for t in Tn]) * float(L_n["mult"]) * float(L_n.get("weight", 1))
    assert np.allclose([v for _, v in trn_book], usd, atol=0.01)
    s422 = np.asarray(S.plugin_sizes(rn, len(Tn)), float)
    t_n = pd.DatetimeIndex(idx_n[ent])

    days = pd.bdate_range(H.W0, H.W1)
    M = {}
    for leg in BOOK463_LEGS:
        c, m = BL.leg_series(leg)
        M[leg["strategy"]] = m
        days = days.union(c.index).union(m.index)
    book = sum(s.reindex(days).fillna(0.0) for s in M.values())
    noise_d = M[L_n["strategy"]].reindex(days).fillna(0.0)
    other = (book - noise_d).to_numpy()
    pos = days.get_indexer(pd.to_datetime([d for d, _ in trn_book]).normalize())
    assert (pos >= 0).all()
    v_book = np.array([v for _, v in trn_book])

    def book_with(mult):
        return pd.Series(other + np.bincount(pos, weights=v_book * mult, minlength=len(days)), index=days)

    assert np.abs(book_with(np.ones(len(Tn))).to_numpy() - book.to_numpy()).max() < 0.01, "NOISE is not intraday"
    base = H.roc_sortino(book, H.WF0, H.WF1)
    wf = np.asarray((t_n >= H.WF0) & (t_n <= H.WF1 + pd.Timedelta(days=1)))

    def c_of(m):
        return float((m[wf] * s422[wf]).mean() / s422[wf].mean())

    def lead(m, lo=H.WF0, hi=H.WF1, drop=None):
        c = c_of(m)
        a = H.roc_sortino(book_with(m), lo, hi, drop)
        t = H.roc_sortino(book_with(np.full(len(m), c)), lo, hi, drop)
        return a, t, c

    sizes = arms_sizes(A, Tn)
    rng = np.random.default_rng(SEED)
    rows, verdicts, shuf = [], {}, {}
    for name, m in sizes.items():
        (ra, sa), (rt, st), c = lead(m)
        (rna, _), (rnt, _), _ = lead(m, drop=(H.COVID0, H.COVID1))
        (rba, _), (rbt, _), _ = lead(m, H.BLOCK0, H.BLOCK1)
        yrs = []
        for y in range(2016, 2025):
            lo, hi = pd.Timestamp(f"{y}-07-01"), pd.Timestamp(f"{y + 1}-06-30")
            (ya, _), (yt, _), _ = lead(m, lo, hi)
            yrs.append(ya - yt)
        n_t = int((m[wf] != 1.0).sum())
        row = dict(arm=name, c=c, tilted=n_t, roc=ra, sortino=sa, twin_roc=rt, twin_sortino=st, lead_roc=ra - rt,
                   lead_sortino=sa - st, no2020_lead=rna - rnt, block_lead=rba - rbt, years_won=int(sum(d > 0 for d in yrs)),
                   **{f"y{2016 + i}": d for i, d in enumerate(yrs)})
        if name in SINGLES:
            leads, wv = [], np.flatnonzero(wf)
            for _ in range(N_SHUF):
                mm = m.copy()
                mm[wv] = m[wv][rng.permutation(len(wv))]
                (a, _), (t, _), _ = lead(mm)
                leads.append(a - t)
            shuf[name] = leads = np.array(leads)
            row.update(shuf_p50=float(np.median(leads)), shuf_cut=float(np.percentile(leads, PCT)),
                       shuf_pct=float(100 * (leads < ra - rt).mean()))
            bars = {
                "1 beats twin AND #463 on WF ROC + Sortino": ra > rt and sa > st and ra > base[0] and sa > base[1],
                "2 without Feb-Apr 2020 beats twin": rna > rnt,
                "3 beats twin in >= 6 of 9 WF years": row["years_won"] >= 6,
                "4 2011-01..2016-06 block beats twin": rba > rbt,
                f"5 WF ROC lead above shuffle {PCT:.1f}th pct": (ra - rt) > row["shuf_cut"],
                "6 >= 100 tilted WF trades": n_t >= 100,
            }
            verdicts[name] = {k: bool(v) for k, v in bars.items()}
        rows.append(row)
    R = pd.DataFrame(rows).set_index("arm")
    P = R.loc["P"]

    lines = [f"#463 parity, WF {H.WF0.date()}..{H.WF1.date()}: ROC@$30k {base[0]:.1f}  Sortino {base[1]:.2f}  "
             f"(reference 93.8 / 3.82)", "",
             "arm         c       tilted  ROC   Sortino | twin ROC Sortino | lead ROC Sortino | no-2020 lead | "
             "2011-16 lead | years won"]
    for k, r in R.iterrows():
        lines.append(f"{k:10s} {r.c:.4f} {int(r.tilted):6d}  {r.roc:5.1f} {r.sortino:5.2f}  | {r.twin_roc:5.1f} "
                     f"{r.twin_sortino:5.2f}   | {r.lead_roc:+6.2f} {r.lead_sortino:+6.3f}  | {r.no2020_lead:+6.2f}"
                     f"       | {r.block_lead:+6.2f}       | {int(r.years_won)}/9")
    lines += ["", "leave-one-out drop in P's lead over its twin (ROC / Sortino; positive = the part helps inside P):"]
    for part in SINGLES:
        q = R.loc[f"P-{part}"]
        lines.append(f"  {part:8s} {P.lead_roc - q.lead_roc:+6.2f} / {P.lead_sortino - q.lead_sortino:+6.3f}")
    lines += ["", f"P inside the book: beats twin AND #463 on WF ROC + Sortino = "
              f"{bool(P.roc > P.twin_roc and P.sortino > P.twin_sortino and P.roc > base[0] and P.sortino > base[1])}"]
    for name in SINGLES:
        r = R.loc[name]
        lines.append(f"\n{name}: shuffle lead median {r.shuf_p50:+.2f}, {PCT:.1f}th pct {r.shuf_cut:+.2f}, "
                     f"arm at the {r.shuf_pct:.1f}th pct")
        lines += [f"  [{'PASS' if v else 'fail'}] {k}" for k, v in verdicts[name].items()]
        lines.append(f"  -> {name}: " + ("CARRIES - forward shadow via the NOISE lane (paired stop, 50 trades)"
                                          if all(verdicts[name].values()) else "does not carry (dead as a book re-sizing)"))
    lines.append("\nSTAGE A: " + (", ".join(n for n in SINGLES if all(verdicts[n].values())) or "no part carries")
                 + " (lockbox never read; no variants)")
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "STAGE_A.txt"), "w", encoding="utf-8").write(txt + "\n")
    R.to_csv(os.path.join(OUT, "arms.csv"))
    pd.DataFrame(shuf).to_csv(os.path.join(OUT, "shuffles.csv"), index=False)
    return verdicts


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
