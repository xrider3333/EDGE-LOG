"""THE SEAT PIPELINE - one shared definition of how a new basket leg (a "seat") is read over the RESMOM line (BOOK.md 10ab / Q19, MANAGER
assessment 10-05 order 5b; the line restated under hygiene rule S1, BOOK.md 10ai). STRATEGY-BEATING, CUSTOM-ML, TV and FRONTIER import this so
every seat is reported over L the same way.

Pure functions only: no import-time work, no paths, no argv. Every window and size is an argument with a documented default; a pinned
input file is checked against the sha the CALLER's prereg names (load_pinned_daily raises on a mismatch), and check_parity() refuses a
line that does not reproduce its registered figures to the stated precision - so a silently swapped file fails instead of answering.

DEFINITIONS (verbatim from FRONTIER's q19_a2.py, Q19 addendum 2):
  * figures: on a daily P&L series over [start, end] - net a year = sum / years, years = (end - start).days / 365.25; worst drawdown on
    the running sum with the peak starting at 0 before the first row; ROC at $30k = 30 x (net a year) / worst drawdown (= 30 x MAR);
    Sortino = mean / RMS(min(x, 0)) x sqrt(252). DD5 (owner rule 10-07) from augur_engine.drawdowns beside every ROC.
  * episodes (the HOUSE rule, MDL r1 / DDW r1 [T5]): peak-to-trough episodes of the daily equity (peak from 0 at the start) at least
    min_fraction (1/3) as deep as the deepest; their days = the day after each peak through its trough.
  * L = book + c_res x RES (c_res = 0.264).
  * a seat X is sized by volatility: c_X x X's daily SD over a stated window = share x the reference line's daily SD over the same window
    (10ab: window 2016-07-01..2018-06-29, share 0.25; Q20 proposed 0.10 - shape-only map).
  * the incremental earner reading: X's dollars on R (L's drawdown days) > 0, also without X's best R episode, and above the random-name
    null's 95th percentile on R; corr(X, RES) on all days and on R.

    from augur_engine import seat_pipeline as SP
    D = SP.load_pinned_daily(path, "e204dd53419a22bc")               # the caller's prereg names the sha
    SP.check_parity(SP.window(SP.line_L(D["book_mtm"], D["RES"])), "line_L")
    r = SP.seat_read(x, D["book_mtm"], D["RES"], draws=null_draws)
"""
import hashlib
import math

import numpy as np
import pandas as pd

from augur_engine.drawdowns import dd5

WF = (pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"))          # the walk-forward stretch (rows by #463's UTC day stamps)
SEAT_WINDOW = (pd.Timestamp("2016-07-01"), pd.Timestamp("2018-06-29"))  # 10ab's sizing window
C_RES = 0.264
MIN_FRACTION = 1.0 / 3.0
# The registered parity (module data, so a change to the arithmetic OR the input fails): (ROC at $30k, Sortino, worst drawdown $) on the WF,
# to the precision check_parity() holds them to, and the house episode counts (episodes, drawdown days). line_L = the S1-RESTATED line
# (MANAGER #127; STRATEGY-BEATING's resmom_cells_daily_wf_close.csv, sha256 e204dd53419a22bc..., ledger 2.99); the registered 120.82
# (bed7bf8b) and the 'keep' 120.95 (86721fda) readings are superseded. book463 = the same file's book_mtm column (#463, WF).
LINE_FILE_SHA = "e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18"
PARITY = {"book463": (93.8056, 3.81650, 44848.66), "line_L": (121.0602, 3.92580, 36526.13)}
PARITY_EPISODES = {"book463": (28, 460), "line_L": (45, 762)}
PARITY_TOL = (0.00005, 0.000005, 0.005)                                 # half a unit in the last stated digit


def load_pinned_daily(path, expect_sha, date_col="date"):
    """Read a pinned daily CSV (a date column + value columns) after checking its sha256 (of the file's bytes) starts with expect_sha (a full
    hash or a prefix of at least 8 hex characters). Raises ValueError on a mismatch - the expected sha belongs to the caller's prereg."""
    if not expect_sha or len(expect_sha) < 8:
        raise ValueError("load_pinned_daily: pass the prereg's sha256 (at least 8 hex characters)")
    with open(path, "rb") as f:
        got = hashlib.sha256(f.read()).hexdigest()
    if not got.startswith(expect_sha.lower()):
        raise ValueError(f"load_pinned_daily: {path} sha256 {got[:16]}... is not the pinned {expect_sha[:16]}...")
    return pd.read_csv(path, parse_dates=[date_col]).set_index(date_col).sort_index()


def window(series, start=WF[0], end=WF[1]):
    s = pd.Series(series)
    return s[(s.index >= start) & (s.index <= end)]


def max_drawdown(x):
    """Worst drawdown in $ of the running sum of x, the peak starting at 0 before the first row."""
    q = np.cumsum(np.asarray(x, float))
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def sortino(x):
    x = np.asarray(x, float)
    dn = math.sqrt(float(np.mean(np.minimum(x, 0.0) ** 2))) if len(x) else 0.0
    return float(x.mean() / dn * math.sqrt(252.0)) if dn > 0 else float("nan")


def figures(series, start=WF[0], end=WF[1]):
    """-> {"roc30", "sortino", "dd", "net_per_year", "dd5", "one_episode"} of a daily P&L series over [start, end] (rows outside are ignored)."""
    w = window(series, start, end)
    x = w.to_numpy(float)
    yrs = (end - start).days / 365.25
    d = max_drawdown(x)
    npy = float(x.sum()) / yrs
    r5 = dd5(w) if len(w) else {"dd5_usd": 0.0, "one_episode": False}
    return {"roc30": npy * 30.0 / d if d > 0 else float("nan"), "sortino": sortino(x), "dd": d, "net_per_year": npy,
            "dd5": float(r5["dd5_usd"]), "one_episode": bool(r5["one_episode"])}


def episodes(series, min_fraction=MIN_FRACTION):
    """The house drawdown episodes of a daily P&L series (already cut to its stretch) -> (mask, spans): mask[i] True on the drawdown days;
    spans = [(first_row, last_row, depth $)] in time order, first_row = the day after the peak, last_row = the trough."""
    v = np.asarray(pd.Series(series).to_numpy(float))
    eq = np.concatenate([[0.0], np.cumsum(v)])
    raw, pk, tr = [], 0, 0
    for k in range(1, len(eq)):
        if eq[k] > eq[pk]:
            if tr > pk:
                raw.append((pk, tr, eq[pk] - eq[tr]))
            pk = tr = k
        elif eq[k] < eq[tr]:
            tr = k
    if tr > pk:
        raw.append((pk, tr, eq[pk] - eq[tr]))
    mask = np.zeros(len(v), bool)
    if not raw:
        return mask, []
    thr = max(d for _, _, d in raw) * min_fraction
    spans = [(p, t - 1, float(d)) for p, t, d in raw if d >= thr]
    for a, b, _ in spans:
        mask[a:b + 1] = True
    return mask, spans


def check_parity(series, name, start=WF[0], end=WF[1], parity=None, counts=None, tol=PARITY_TOL):
    """Refuse (ValueError) unless the daily series reproduces PARITY[name] (ROC at $30k, Sortino, worst drawdown) to within tol and its house
    episode / drawdown-day counts COMPUTED from the data equal PARITY_EPISODES[name]. -> the figures (for the caller's log)."""
    want = (parity or PARITY)[name]
    f = figures(series, start, end)
    got = (f["roc30"], f["sortino"], f["dd"])
    bad = [f"{k} {g!r} vs {w}" for k, g, w, t in zip(("roc30", "sortino", "dd"), got, want, tol) if not abs(g - w) <= t]
    mask, spans = episodes(window(series, start, end))
    wc = (counts or PARITY_EPISODES)[name]
    if (len(spans), int(mask.sum())) != tuple(wc):
        bad.append(f"episodes {len(spans)} / {int(mask.sum())} days vs {wc[0]} / {wc[1]}")
    if bad:
        raise ValueError(f"check_parity({name}): " + "; ".join(bad))
    return f


def line_L(book_mtm, res, c_res=C_RES):
    """L = book + c_res x RES on the book's index (RES missing on a book row counts as 0)."""
    b = pd.Series(book_mtm)
    return b + c_res * pd.Series(res).reindex(b.index).fillna(0.0)


def seat_size(x, ref, share=0.25, start=SEAT_WINDOW[0], end=SEAT_WINDOW[1]):
    """c_X such that c_X x the daily SD (ddof 1) of seat x over [start, end] = share x the reference line's daily SD over the same window.
    Both series on the same index; rows where x does not exist yet should be 0 (10ab's convention)."""
    sx = float(np.std(window(x, start, end).to_numpy(float), ddof=1))
    sr = float(np.std(window(ref, start, end).to_numpy(float), ddof=1))
    return share * sr / sx if sx > 0 else float("nan")


def dollars_on(x, mask, spans=None):
    """X's $ on the masked days, and (spans given) without X's best episode -> (total, without_best, best_span_index or None)."""
    v = np.asarray(pd.Series(x).to_numpy(float))
    tot = float(v[mask].sum())
    if not spans:
        return tot, tot, None
    per = [float(v[a:b + 1].sum()) for a, b, _ in spans]
    k = int(np.argmax(per))
    return tot, tot - per[k], k


def null_on_mask(draws, mask, q=(5, 50, 95)):
    """draws (n_draws, T) of random-name books on the same rows as the mask -> {p5, p50, p95} of their $ on the masked days. The caller
    generates the draws with its own seeded engine (the null is the seat family's, never shared)."""
    d = np.asarray(draws, float)[:, np.asarray(mask, bool)].sum(axis=1)
    return {f"p{int(p)}": float(np.percentile(d, p)) for p in q}


def seat_read(x, book_mtm, res, start=WF[0], end=WF[1], shares=(0.25, 0.10), c_res=C_RES, draws=None, min_fraction=MIN_FRACTION):
    """The whole incremental read of seat x over L on [start, end] (all three series on the book's index; draws, if given, (n, T) on the
    same index cut to the same rows as window()). -> dict: the line, the book add at each share (with DD5), R's size, X's $ on R with and
    without its best R episode, the null on R, corr(X, RES) all days / on R, and the earner flag (on R > 0, > 0 without the best, > the
    null's p95)."""
    L = window(line_L(book_mtm, res, c_res), start, end)
    X = window(pd.Series(x).reindex(pd.Series(book_mtm).index).fillna(0.0), start, end)
    R = window(pd.Series(res).reindex(pd.Series(book_mtm).index).fillna(0.0), start, end)
    mask, spans = episodes(L, min_fraction)
    out = {"line": figures(L, start, end), "R_days": int(mask.sum()), "R_episodes": len(spans), "book_add": {}}
    for sh in shares:
        c = seat_size(X, L, sh)
        out["book_add"][f"{sh:.2f}"] = {"c": c, "line_plus": figures(L + c * X, start, end) if np.isfinite(c) else None}   # None: X has no variance in the sizing window
    tot, wo, k = dollars_on(X, mask, spans)
    out.update({"x_on_R": tot, "x_on_R_without_best": wo, "best_R_episode": None if k is None else spans[k][:2],
                "corr_RES_all": float(np.corrcoef(X, R)[0, 1]), "corr_RES_on_R": float(np.corrcoef(X[mask], R[mask])[0, 1])})
    if draws is not None:
        out["null_on_R"] = null_on_mask(draws, mask)
        out["earner"] = bool(tot > 0 and wo > 0 and tot > out["null_on_R"]["p95"])
    return out
