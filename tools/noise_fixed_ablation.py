"""NOISE 09-27 'fixed' package, leave-one-out inside BOOK #463 - Stage A (walk-forward only; the lockbox is never read).
Pre-registration: docs/PREREG_noise_fixed_ablation_2026-10-05.md (+ addendum 2026-10-05, MANAGER #58/#60, NOISE #59).

The package (ml_keel.compression_sizes with v12's fixed settings, no model) on top of #422's own sizes: KEEL's 60-minute
squeeze x1.5, Friday x1.5, FOMC pre-statement x0.5, cap 3 (never binds). Each arm re-sizes #463's NOISE leg and is
judged inside the book against its OWN twin = the NOISE leg scaled to the same mean size (plain extra NOISE). Nulls:
1,000 shuffles of each arm's own multipliers (all arms; the power line), the four weekday placebos for Friday, and 200
time-shifts (>= 60 sessions) of the squeeze flag. The book is built only to 2025-06-29 (no lockbox-era day exists).

    python tools/noise_fixed_ablation.py power    (step 1: the minimum detectable lead per arm, no arm P&L read)
    python tools/noise_fixed_ablation.py run      (step 2: the arms, after POWER.txt is committed)
    (cwd = the shared checkout; EDGELOG_ROOT = it)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_hedge_tilt as H                                          # noqa: E402  same leg runs + book convention

H.W1 = "2025-06-29"                                                   # NOISE #59 (C): build nothing past the WF end
OUT = r"C:\EdgeLog\custom_ml\fixed_ablation"
N_SHUF, N_SHIFT, SHIFT_LO, SHIFT_HI, SEED = 1000, 200, 60, 250, 20261005
PCT = 100 * (1 - 0.05 / 3)                                            # 95% over the three singles
SINGLES = ("squeeze", "Friday", "FOMC")
ARMS = ("P", "P-squeeze", "P-Friday", "P-FOMC") + SINGLES


def setup():
    from augur_engine import book, ml_keel as K
    from augur_engine.data import find_master, load_master_arrays
    import keel_422_stack_check as S
    from api.book_shadow import BOOK463_LEGS
    L_n = [l for l in BOOK463_LEGS if l["strategy"].startswith("NOISE")][0]

    # ---- #463 valued daily to 2025-06-29, exactly as api.book_shadow.book463_valued_daily, NOISE kept apart ----
    days, parts = pd.bdate_range(H.W0, H.W1), {}
    for leg in BOOK463_LEGS:
        tr, inf = book._leg_trades(dict(leg), H.W0, H.W1)
        assert inf.get("source") == leg["source"] and not inf.get("mtm_error"), (leg["strategy"], inf)
        d, v = book._daily(inf.pop("_mtm_day", None) or tr)
        s = pd.Series(v, index=pd.to_datetime(d)).groupby(level=0).sum()
        days = days.union(s.index)
        parts[leg["strategy"]] = s
    book_s = sum(s.reindex(days).fillna(0.0) for s in parts.values())
    other = (book_s - parts[L_n["strategy"]].reindex(days).fillna(0.0)).to_numpy()

    # ---- the identical NOISE leg run ----
    Tn, rn, idx_n, _, _, trn_book, _ = H.run_leg(L_n)
    A = load_master_arrays(find_master(L_n["instrument"], L_n["timeframe"], L_n["session"], L_n.get("source")),
                           date_from=H.W0, date_to=H.W1)
    ent = np.array([int(t[0]) for t in Tn])
    assert (np.diff(ent) >= 0).all(), "engine order is not entry order (compression_sizes sorts by entry)"
    v_book = np.array([v for _, v in trn_book])
    pos = days.get_indexer(pd.to_datetime([d for d, _ in trn_book]).normalize())
    assert (pos >= 0).all()
    s422 = np.asarray(S.plugin_sizes(rn, len(Tn)), float)
    t_n = pd.DatetimeIndex(idx_n[ent])
    wf = np.asarray((t_n >= H.WF0) & (t_n <= H.WF1 + pd.Timedelta(days=1)))

    def book_with(mult):
        return pd.Series(other + np.bincount(pos, weights=v_book * mult, minlength=len(days)), index=days)

    assert np.abs(book_with(np.ones(len(Tn))).to_numpy() - book_s.to_numpy()).max() < 0.01, "NOISE is not intraday"
    base = H.roc_sortino(book_s, H.WF0, H.WF1)
    assert abs(base[0] - 93.81) < 0.01 and abs(base[1] - 3.816) < 0.001, f"#463 parity failed: {base}"

    # ---- arm sizes, and the per-bar pieces the nulls rebuild ----
    ev = dict(K.CFG["v12"]["event"])
    dow = {k: v for k, v in K.CFG["v12"]["dow"].items() if k != "cap"}
    cap = float(K.CFG["v12"]["comp"]["cap"])
    spec = {"P": (1.5, dow, ev), "P-squeeze": (1.0, dow, ev), "P-Friday": (1.5, None, ev), "P-FOMC": (1.5, dow, None),
            "squeeze": (1.5, None, None), "Friday": (1.0, dow, None), "FOMC": (1.0, None, ev)}
    sizes = {k: np.asarray(K.compression_sizes(A, Tn, mult=mu, dow=d, cap=cap, event=e), float)
             for k, (mu, d, e) in spec.items()}
    F, names = K.keel_features(A)
    bar_t = H.naive_et(A["index"])
    flag = pd.Series(F[:, names.index("sq60_on")] > 0, index=bar_t)
    E = np.clip(ent, 0, len(F) - 1)
    assert (np.where(flag.to_numpy()[E], 1.5, 1.0) == sizes["squeeze"]).all(), "squeeze rebuild differs"
    wd = bar_t[E].dayofweek
    assert (np.where(wd == 4, 1.5, 1.0) == sizes["Friday"]).all(), "Friday rebuild differs"
    return dict(book_with=book_with, base=base, wf=wf, s422=s422, sizes=sizes, flag=flag, t_e=bar_t[E], wd=wd,
                days=days)


def make_lead(X):
    wf, s422, book_with = X["wf"], X["s422"], X["book_with"]

    def lead(m, lo=H.WF0, hi=H.WF1, drop=None):
        c = float((m[wf] * s422[wf]).mean() / s422[wf].mean())
        a = H.roc_sortino(book_with(m), lo, hi, drop)
        t = H.roc_sortino(book_with(np.full(len(m), c)), lo, hi, drop)
        return a, t, c
    return lead


def shuffle_null(m, lead, wf, rng):
    wv, out = np.flatnonzero(wf), []
    for _ in range(N_SHUF):
        mm = m.copy()
        mm[wv] = m[wv][rng.permutation(len(wv))]
        (a, _), (t, _), _ = lead(mm)
        out.append(a - t)
    return np.array(out)


def shift_null(X, lead, rng):
    """Squeeze flag read k sessions later at the same time of day, wrapped inside the WF sessions (>= 60 sessions,
    longer than any squeeze spell): keeps the duty cycle, breaks the timing. Non-WF trades keep their size."""
    flag, t_e, wf, m0 = X["flag"], X["t_e"], X["wf"], X["sizes"]["squeeze"]
    sess = pd.DatetimeIndex(sorted(set(flag.index.normalize())))
    sess = sess[(sess >= H.WF0) & (sess <= H.WF1)]
    pos = {d: i for i, d in enumerate(sess)}
    d = t_e[wf].normalize()
    i = np.array([pos[x] for x in d])
    tod = t_e[wf] - d
    out = []
    for _ in range(N_SHIFT):
        k = int(rng.integers(SHIFT_LO, SHIFT_HI + 1))
        f = flag.reindex(sess[(i + k) % len(sess)] + tod).fillna(False).to_numpy(bool)
        mm = m0.copy()
        mm[wf] = np.where(f, 1.5, 1.0)
        (a, _), (t, _), _ = lead(mm)
        out.append(a - t)
    return np.array(out)


def power():
    X = setup()
    lead = make_lead(X)
    rng = np.random.default_rng(SEED)
    lines = [f"#463 parity, built to {H.W1}: WF ROC@$30k {X['base'][0]:.2f}  Sortino {X['base'][1]:.3f} (93.81 / 3.816)",
             "POWER LINE - nulls only, no arm's own P&L read. Minimum detectable WF ROC lead over the twin:"]
    nulls = {}
    for name in ARMS:
        nulls[name] = z = shuffle_null(X["sizes"][name], lead, X["wf"], rng)
        lines.append(f"  {name:10s} own-size shuffle (1,000): 50th {np.median(z):+.2f}  95th {np.percentile(z, 95):+.2f}"
                     f"  {PCT:.1f}th {np.percentile(z, PCT):+.2f}")
    nulls["squeeze_shift"] = z = shift_null(X, lead, np.random.default_rng(SEED + 1))
    lines.append(f"  squeeze time-shift (200, 60..250 sessions): 50th {np.median(z):+.2f}  95th {np.percentile(z, 95):+.2f}")
    lines.append("Expectation stated now (MANAGER #58): real leads of NOISE r70's size (~3 ROC points in the book) may sit"
                 " inside these nulls and then cannot be told from luck.")
    txt = "\n".join(lines)
    print(txt)
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "POWER.txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame({k: pd.Series(v) for k, v in nulls.items()}).to_csv(os.path.join(OUT, "nulls.csv"), index=False)


def dd_window(x, lo, hi):
    """(peak day, trough day) of the worst drawdown of daily series x inside [lo, hi]."""
    s = x[(x.index >= lo) & (x.index <= hi)]
    q = s.cumsum()
    trough = (q.cummax() - q).idxmax()
    head = q[:trough]
    return (head.idxmax() if head.max() > 0 else s.index[0]), trough


def run():
    assert os.path.exists(os.path.join(OUT, "POWER.txt")), "run `power` first and commit POWER.txt"
    X = setup()
    lead, wf, sizes, base = make_lead(X), X["wf"], X["sizes"], X["base"]
    nulls = pd.read_csv(os.path.join(OUT, "nulls.csv"))
    rows, verdicts = [], {}
    for name in ARMS:
        m = sizes[name]
        (ra, sa), (rt, st), c = lead(m)
        (rna, _), (rnt, _), _ = lead(m, drop=(H.COVID0, H.COVID1))
        (rba, _), (rbt, _), _ = lead(m, H.BLOCK0, H.BLOCK1)
        pk, tr = dd_window(X["book_with"](np.full(len(m), c)), H.WF0, H.WF1)
        (rxa, _), (rxt, _), _ = lead(m, drop=(pk, tr))
        yrs = []
        for y in range(2016, 2025):
            lo, hi = pd.Timestamp(f"{y}-07-01"), pd.Timestamp(f"{y + 1}-06-30")
            (ya, _), (yt, _), _ = lead(m, lo, hi)
            yrs.append(ya - yt)
        z = nulls[name].dropna().to_numpy()
        rows.append(dict(arm=name, c=c, tilted=int((m[wf] != 1.0).sum()), roc=ra, sortino=sa, twin_roc=rt,
                         twin_sortino=st, lead_roc=ra - rt, lead_sortino=sa - st, no2020_lead=rna - rnt,
                         block_lead=rba - rbt, twin_dd=f"{pk.date()}..{tr.date()}", exdd_lead=rxa - rxt,
                         years_won=int(sum(d > 0 for d in yrs)), shuf_pct=float(100 * (z < ra - rt).mean()),
                         shuf_cut=float(np.percentile(z, PCT)), **{f"y{2016 + i}": d for i, d in enumerate(yrs)}))
    R = pd.DataFrame(rows).set_index("arm")

    # Friday's calendar null: Mon..Thu x1.5, each vs its own twin
    wk = {}
    for d, lab in enumerate(("Mon", "Tue", "Wed", "Thu")):
        (a, _), (t, _), _ = lead(np.where(X["wd"] == d, 1.5, 1.0))
        wk[lab] = a - t
    shift = nulls["squeeze_shift"].dropna().to_numpy()
    for name in SINGLES:
        r = R.loc[name]
        bars = {
            "1 beats twin AND #463 on WF ROC + Sortino": r.roc > r.twin_roc and r.sortino > r.twin_sortino
            and r.roc > base[0] and r.sortino > base[1],
            "2 without Feb-Apr 2020 beats twin": r.no2020_lead > 0,
            "3 beats twin in >= 6 of 9 WF years": r.years_won >= 6,
            "4 2011-01..2016-06 block beats twin (untuned for NOISE, not blind)": r.block_lead > 0,
            f"5 WF ROC lead above own-size shuffle {PCT:.1f}th pct": r.lead_roc > r.shuf_cut,
            "6 >= 100 tilted WF trades": r.tilted >= 100,
        }
        if name == "Friday":
            bars["7 beats all four weekday placebos (Mon..Thu x1.5)"] = r.lead_roc > max(wk.values())
        if name == "squeeze":
            bars["8 WF ROC lead above time-shift 95th pct"] = r.lead_roc > np.percentile(shift, 95)
        verdicts[name] = {k: bool(v) for k, v in bars.items()}

    P = R.loc["P"]
    p_bar1 = bool(P.roc > P.twin_roc and P.sortino > P.twin_sortino and P.roc > base[0] and P.sortino > base[1])
    lines = [open(os.path.join(OUT, "POWER.txt"), encoding="utf-8").read().rstrip(), "",
             "arm         c      tilted  ROC   Sort  | twin ROC Sort | lead ROC  Sort  | no-2020 | 2011-16 | ex twin-DD "
             "window            | years | shuffle pct"]
    for k, r in R.iterrows():
        lines.append(f"{k:10s} {r.c:.4f} {int(r.tilted):5d}  {r.roc:5.1f} {r.sortino:4.2f} | {r.twin_roc:5.1f} "
                     f"{r.twin_sortino:4.2f}   | {r.lead_roc:+5.2f} {r.lead_sortino:+6.3f} | {r.no2020_lead:+6.2f}  | "
                     f"{r.block_lead:+6.2f}  | {r.exdd_lead:+6.2f} {r.twin_dd} | {int(r.years_won)}/9   | {r.shuf_pct:5.1f}")
    lines += ["", "leave-one-out drop in P's lead over its twin (ROC / Sortino; positive = the part helps inside P):"]
    for part in SINGLES:
        q = R.loc[f"P-{part}"]
        lines.append(f"  {part:8s} {P.lead_roc - q.lead_roc:+6.2f} / {P.lead_sortino - q.lead_sortino:+6.3f}")
    lines += ["", "weekday placebos (lead over own twin): " + ", ".join(f"{k} {v:+.2f}" for k, v in wk.items())
              + f" | Friday {R.loc['Friday'].lead_roc:+.2f}",
              f"squeeze time-shift null 95th {np.percentile(shift, 95):+.2f} | squeeze {R.loc['squeeze'].lead_roc:+.2f}",
              "", f"P inside the book beats twin AND #463 on WF ROC + Sortino: {p_bar1}"]
    if not p_bar1:
        lines.append("OWNER LINE: the 09-27 package's standalone 109-vs-85 walk-forward gain was extra size, not aim - "
                     "inside BOOK #463 it does not beat plain extra NOISE plus #463 at the same average size.")
    for name in SINGLES:
        lines.append(f"\n{name}:")
        lines += [f"  [{'PASS' if v else 'fail'}] {k}" for k, v in verdicts[name].items()]
        lines.append(f"  -> {name}: " + ("CARRIES - forward sub-arm via the NOISE lane (paired stop, 50 trades)"
                                          if all(verdicts[name].values()) else "does not carry (dead as a book re-sizing)"))
    lines.append("\nSTAGE A: " + (", ".join(n for n in SINGLES if all(verdicts[n].values())) or "no part carries")
                 + " (lockbox never read; no variants; single-arm bars cannot credit a combination-only squeeze effect)")
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "STAGE_A.txt"), "w", encoding="utf-8").write(txt + "\n")
    R.to_csv(os.path.join(OUT, "arms.csv"))
    return verdicts


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "power":
        power()
    elif mode == "run":
        run()
    else:
        raise SystemExit("usage: noise_fixed_ablation.py power | run")
