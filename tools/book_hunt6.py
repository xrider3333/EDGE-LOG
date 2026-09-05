"""BOOK HUNT 6 -- pooled-portfolio study of the three live families.

Question: does ANY pooled book (union of legs' trades, one contract each) beat the best
single strategy on the board on BOTH EV R (best single ~0.9, ENGU-Q #310) AND R/YR
(best single ~62, ENGU-Q #249)?

Arithmetic note (stated up front so the numbers can be checked against it): a pooled
book's net is the sum of its legs' nets and its trade count is the sum of counts, so
    EV R(book) = net/n / avg_loss(book)
is a trade-weighted blend of the legs -- pooling can raise R/YR (more trades per year)
but cannot lift EV R above the best leg UNLESS the legs' average-loss sizes differ
(avg-loss mixing: a leg with big wins and tiny losses pooled with a leg whose losses
are large gets a book avg_loss dominated by the large-loss leg, and the ratio can land
anywhere). The driver checks this explicitly for every book.

Legs (one contract each, 0.533 pts/RT, $20/pt), all on the COMMON WINDOW
entries 2010-06-07 .. 2026-06-30 (ENGU-Q's 1-minute master has a hole after
2026-06-30); lockbox = entries >= 2025-06-30.
    ORB  #234 crown        ORB_3_6.py           NQ 5m RTH
    ORB  F8080 (#298)      ORB_3_6.py           NQ 5m RTH
    NOISE #243 crown       NOISE_1_0.py         NQ 5m RTH
    NOISE #305             NOISE_1_0.py         NQ 5m RTH
    ENGU-Q #310 (EV R)     ENGUQ_1M_ETH_LIM_1_0 NQ 1m ETH
    ENGU-Q #249 (R/YR)     ENGUQ_1M_ETH_LIM_1_0 NQ 1m ETH

Books scored: every leg alone, every pair, every one-per-family triple (8), plus the
"current crowns" baseline #234 + #243 + #249.

Max drawdown is measured on the pooled equity curve ordered by EXIT time (a trade's
P&L lands when it closes). Rolling-12-month robustness and the lockbox split use the
ENTRY time (matches tools/orb_hunt3.robustness and every prior hunt). Daily-PnL
correlations bucket each trade's $ on its EXIT date and correlate the two legs over
the union of days either leg traded (0 on days a leg was flat).

Run:  python tools/book_hunt6.py [out.json]
"""
import os
import sys
import json
import itertools
import importlib.util

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
# augur_engine.data resolves the master DB relative to its own package, and a worktree
# has no optimizer_history.db of its own -> import the ENGINE from the primary checkout
# (read-only data access) while strategies + tools come from this checkout.
sys.path.insert(0, ROOT)
sys.path.insert(0, MAIN)

from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from tools.orb_hunt5 import bars as bars5m                        # noqa: E402
from tools.orb_hunt3 import robustness                            # noqa: E402

COST, MULT = 0.533, 20.0
WIN_FROM, WIN_TO, LB_FROM = "2010-06-07", "2026-06-30", "2025-06-30"
YEARS = (pd.Timestamp(WIN_TO) - pd.Timestamp(WIN_FROM)).days / 365.25

ORB_234 = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, breakout_buf=0.25,
               close_confirm=True, partial_exit_R=0.0, trail_bars=0, target_R=5.5,
               be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7, flat_eod=True,
               skip_holidays=True)
ORB_F8080 = dict(ORB_234, atr_filter=0.8, vpace_filter=0.8)
NOISE_243 = {"band_mult_long": 0.75, "band_mult_short": 1.5, "confirm_bars": 1,
             "daytype_hi": 0.8, "daytype_lo": 0.2, "daytype_mode": "skip_bot_short",
             "exit_mode": "vwap", "flat_eod": True, "lookback": 44, "side": "Both",
             "skip_holidays": False, "stop_k": 1.75, "stop_mode": "bandwidth",
             "vol_skip_pct": 90.0, "window": "all_day"}
NOISE_305 = {"band_mult_long": 0.75, "band_mult_short": 1.25, "confirm_bars": 4,
             "daytype_hi": 0.6, "daytype_lo": 0.25, "daytype_mode": "skip_bot_short",
             "exit_mode": "vwap", "flat_eod": True, "lookback": 51, "side": "Both",
             "skip_holidays": False, "stop_k": 1.25, "stop_mode": "bandwidth",
             "vol_skip_pct": 99.0, "window": "all_day"}
ENG_310 = {"act_R": 3.0, "atr_len": 44, "breakeven_R": 1.5, "buf_atr": 1.0, "ema_len": 420,
           "limit_atr": 0.7, "min_brk": 0.4, "regime_len": 5, "stop_mult": 1.7,
           "tl_len": 238, "trail_frac": 4.0, "vol_mult": 0.8}
ENG_249 = {"act_R": 2.5, "atr_len": 106, "breakeven_R": 1.5, "buf_atr": 0.9, "ema_len": 1380,
           "limit_atr": 0.5, "min_brk": 1.3, "regime_len": 0, "stop_mult": 1.0,
           "tl_len": 170, "trail_frac": 2.5, "vol_mult": 0.8}

LEGS = [
    ("ORB#234",   "ORB",   "ORB_3_6.py",               ORB_234),
    ("ORB#F8080", "ORB",   "ORB_3_6.py",               ORB_F8080),
    ("NOISE#243", "NOISE", "NOISE_1_0.py",             NOISE_243),
    ("NOISE#305", "NOISE", "NOISE_1_0.py",             NOISE_305),
    ("ENGU#310",  "ENGU",  "ENGUQ_1M_ETH_LIM_1_0.py",  ENG_310),
    ("ENGU#249",  "ENGU",  "ENGUQ_1M_ETH_LIM_1_0.py",  ENG_249),
]
FAMILIES = ["ORB", "NOISE", "ENGU"]


def strat(fname):
    spec = importlib.util.spec_from_file_location(fname[:-3],
                                                  os.path.join(ROOT, "augur_strategies", fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_ENG = None


def bars1m():
    global _ENG
    if _ENG is None:
        _ENG = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                                  date_from=None, date_to=WIN_TO)
    return _ENG


def _naive(idx):
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    return idx


def leg_trades(name, fam, fname, params):
    """-> DataFrame(entry, exit, pnl) in $ after cost, clipped to the common window."""
    mod = strat(fname)
    if fam == "ENGU":
        a = bars1m()
        r = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                             day_id=a["day_id"], index=a["index"], return_trades=True, **params)
        idx = _naive(a["index"])
    else:
        b = bars5m()
        r = mod.run_backtest(b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
                             day_id=b["day_id"], return_trades=True, **params)
        idx = _naive(b["index"])
    tr = (r or {}).get("trades") or []
    df = pd.DataFrame({
        "entry": [idx[int(t[0])] for t in tr],
        "exit":  [idx[int(t[1])] for t in tr],
        "pnl":   [(float(t[2]) - COST) * MULT for t in tr],
    })
    lo, hi = pd.Timestamp(WIN_FROM), pd.Timestamp(WIN_TO) + pd.Timedelta(days=1)
    df = df[(df.entry >= lo) & (df.entry < hi)].reset_index(drop=True)
    df["leg"] = name
    return df


def metrics(df):
    """All book metrics on a (entry, exit, pnl) frame. DD on EXIT-ordered curve."""
    d = df.pnl.values
    n = len(d)
    if n == 0:
        return None
    net = float(d.sum())
    by_exit = df.sort_values(["exit", "entry"]).pnl.values
    cum = np.cumsum(by_exit)
    dd = float(abs((cum - np.maximum.accumulate(cum)).min()))
    by_entry = df.sort_values(["entry", "exit"]).pnl.values
    cum_e = np.cumsum(by_entry)
    dd_entry = float(abs((cum_e - np.maximum.accumulate(cum_e)).min()))
    gp, gl = float(d[d > 0].sum()), float(abs(d[d < 0].sum()))
    pf = gp / gl if gl > 0 else float("inf")
    losses = d[d < 0]
    avg_loss = float(abs(losses.mean())) if len(losses) else float("nan")
    ev_r = (net / n) / avg_loss if avg_loss and avg_loss > 0 else float("nan")
    tpy = n / YEARS
    lb = df[df.entry >= pd.Timestamp(LB_FROM)]
    rob = robustness(df.entry.values, d)
    return dict(n=int(n), net=net, dd=dd, dd_entry_ordered=dd_entry,
                pf=float(pf), win_rate=float(100.0 * (d > 0).mean()),
                avg_loss=avg_loss, avg_win=float(d[d > 0].mean()) if (d > 0).any() else 0.0,
                ev_r=float(ev_r), trades_yr=float(tpy), r_yr=float(ev_r * tpy),
                lb_n=int(len(lb)), lb_net=float(lb.pnl.sum()),
                roll12_win=rob["win_pct"], roll12_worst=rob["worst"], roll12_median=rob["median"],
                mar_ann=(net / YEARS) / dd if dd > 0 else float("inf"),
                years=YEARS)


def daily(df):
    return df.groupby(df.exit.dt.normalize()).pnl.sum()


def main(out_path=None):
    legs = {}
    for name, fam, fname, params in LEGS:
        df = leg_trades(name, fam, fname, params)
        legs[name] = (fam, df)
        m = metrics(df)
        print(f"{name:<11} n={m['n']:5d} net=${m['net']:10,.0f} DD=${m['dd']:8,.0f} "
              f"PF={m['pf']:.3f} EVR={m['ev_r']:.3f} R/YR={m['r_yr']:6.1f} LB=${m['lb_net']:8,.0f}",
              flush=True)

    # correlation matrix (daily $ by exit date, union of active days, 0 when flat)
    names = [l[0] for l in LEGS]
    D = pd.concat({k: daily(v[1]) for k, v in legs.items()}, axis=1).fillna(0.0)
    corr = D.corr()

    books = []

    def add(label, members):
        df = pd.concat([legs[k][1] for k in members]).sort_values(["entry", "exit"])
        m = metrics(df)
        m["name"], m["legs"] = label, list(members)
        m["leg_ev_r"] = {k: metrics(legs[k][1])["ev_r"] for k in members}
        m["leg_avg_loss"] = {k: metrics(legs[k][1])["avg_loss"] for k in members}
        m["ev_r_exceeds_best_leg"] = bool(m["ev_r"] > max(m["leg_ev_r"].values()) + 1e-12)
        if len(members) > 1:
            m["pair_corr"] = {f"{a}|{b}": float(corr.loc[a, b])
                              for a, b in itertools.combinations(members, 2)}
        books.append(m)

    for k in names:
        add(k, [k])
    for a, b in itertools.combinations(names, 2):
        add(f"{a}+{b}", [a, b])
    fam_members = {f: [l[0] for l in LEGS if l[1] == f] for f in FAMILIES}
    for trip in itertools.product(*[fam_members[f] for f in FAMILIES]):
        add("+".join(trip), list(trip))
    # baseline is one of the 8 triples already; tag it
    for m in books:
        m["baseline"] = m["legs"] == ["ORB#234", "NOISE#243", "ENGU#249"]

    best_single_evr = max(m["ev_r"] for m in books if len(m["legs"]) == 1)
    best_single_ryr = max(m["r_yr"] for m in books if len(m["legs"]) == 1)
    for m in books:
        m["beats_best_single_both"] = bool(len(m["legs"]) > 1 and m["ev_r"] > best_single_evr
                                           and m["r_yr"] > best_single_ryr)

    hdr = (f"{'book':<34} {'n':>5} {'net':>10} {'DD':>8} {'PF':>6} {'EVR':>6} {'R/YR':>6} "
           f"{'LB':>9} {'r12w':>5} {'r12worst':>9} {'MARa':>6}")

    def line(m):
        return (f"{m['name']:<34} {m['n']:>5} {m['net']:>10,.0f} {m['dd']:>8,.0f} {m['pf']:>6.3f} "
                f"{m['ev_r']:>6.3f} {m['r_yr']:>6.1f} {m['lb_net']:>9,.0f} {m['roll12_win']:>5.1f} "
                f"{m['roll12_worst']:>9,.0f} {m['mar_ann']:>6.2f}")

    for key in ("r_yr", "ev_r"):
        print(f"\n=== ranked by {key} ===\n{hdr}")
        for m in sorted(books, key=lambda x: -x[key]):
            print(line(m))

    print("\n=== daily-PnL correlation (exit date) ===")
    print(corr.round(3).to_string())
    print(f"\nbest single EV R {best_single_evr:.3f}, best single R/YR {best_single_ryr:.1f}")
    winners = [m["name"] for m in books if m["beats_best_single_both"]]
    print("books beating best single on BOTH:", winners or "NONE")
    odd = [m["name"] for m in books if len(m["legs"]) > 1 and m["ev_r_exceeds_best_leg"]]
    print("books whose EV R exceeds every leg (avg-loss mixing):", odd or "NONE")

    out = dict(window=dict(date_from=WIN_FROM, date_to=WIN_TO, lockbox_from=LB_FROM, years=YEARS),
               cost_pts=COST, mult=MULT,
               dd_ordering="pooled equity ordered by EXIT time (dd_entry_ordered also given)",
               corr_method="daily $ by EXIT date, union of active days, 0 when flat",
               legs={l[0]: dict(family=l[1], strategy=l[2], params=l[3]) for l in LEGS},
               correlation={a: {b: float(corr.loc[a, b]) for b in names} for a in names},
               best_single=dict(ev_r=best_single_evr, r_yr=best_single_ryr),
               books=books)
    if out_path:
        with open(out_path, "w") as f:
            json.dump(out, f, indent=1, default=float)
        print("saved", out_path)
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
