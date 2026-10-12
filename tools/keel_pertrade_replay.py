"""tools/keel_pertrade_replay.py -- the trade-by-trade proof that PER-TRADE live KEEL equals the backtest walk
(owner 10-12 via MANAGER #102: "live = backtest exactly"; PAPER-WB builds the per-trade push).

WHAT IT CHECKS. The backtest the owner adopted is keel_walk over run #382's NQ trades (the Auto-Validate KEEL
row). The live scorer holds a state and, under the per-trade design, appends each NQ #382 trade the moment it
closes (augur_engine.ml_keel.keel_append_trade) and scores every new entry against that state
(keel_score_from_state, cross_series=True). This replays exactly that on the real NQ history:

    state = keel_build_state(trades before --from)          # the nightly state of that morning
    for each trade k from --from, in entry order:
        live_k  = keel_score_from_state(state, NQ arrays, entry bar, its NQ feature row)   # what live would size
        state   = keel_append_trade(state, row, pnl, entry, exit)                         # the push after it closes
    compare live_k with keel_walk(...)["size"][k] for EVERY trade.

It also prints what the NIGHTLY design (today's live: state rebuilt once per night) gives for the same trades,
so the per-trade fix is shown closing a real gap, not a theoretical one.

USAGE (read-only: writes only the CSV under --out; never touches C:\\EdgeLog\\cloud_signal):
    python tools/keel_pertrade_replay.py                    # whole history from the first trade
    python tools/keel_pertrade_replay.py --from 2025-07-16  # start from that morning's nightly state
Exit code 0 = every trade exact (|diff| <= 1e-12), 1 = any mismatch.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from augur_engine import ml_keel as K  # noqa: E402
import keel_live_state as L  # noqa: E402

TOL = 1e-12


def replay(arrays, trades, version="v12", start_k=0, feats=None, log=print):
    """Per-trade replay from trade index `start_k`. Returns a DataFrame with one row per replayed trade:
    walk size, per-trade live size, nightly live size, and their differences."""
    feats = feats if feats is not None else K.keel_features(arrays)
    F = feats[0]
    kw = K.keel_walk(arrays, trades, feats=feats, version=version)
    T = kw["trades"]
    idx = pd.DatetimeIndex(arrays["index"])
    days = idx.normalize()
    state = K.keel_build_state(arrays, T[:start_k], feats=feats, version=version)
    nightly = state
    rows = []
    for k in range(start_k, len(T)):
        e, x, p = T[k]
        day = days[e]
        if k > start_k and day != days[T[k - 1][0]]:
            nightly = state                      # a new session: the nightly state = everything closed before it
        live, diag = K.keel_score_from_state(state, arrays, e, x_row=F[e:e + 1], cross_series=True)
        night, _ = K.keel_score_from_state(nightly, arrays, e, x_row=F[e:e + 1], cross_series=True)
        walk = float(kw["size"][k])
        rows.append({"k": k, "entry_ts": idx[e], "exit_ts": idx[min(x, len(idx) - 1)], "pnl": p,
                     "walk_size": walk, "live_size": live, "nightly_size": night,
                     "diff_live": live - walk, "diff_nightly": night - walk,
                     "same_day_2nd": bool(k > 0 and days[T[k - 1][0]] == day),
                     "trust": diag.get("trust"), "t_fast": diag.get("t_fast"), "z": diag.get("z")})
        state = K.keel_append_trade(state, F[e:e + 1], p, entry_bar=e, exit_bar=x)
        if (k - start_k) % 500 == 0:
            log(f"[keel-pertrade] {k - start_k + 1} of {len(T) - start_k} trades replayed")
    return pd.DataFrame(rows), kw


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", default="NOISE_382")
    ap.add_argument("--nq-file", default=None)
    ap.add_argument("--from", dest="date_from", default=None,
                    help="start the per-trade replay at the first trade entered on/after this date (ET)")
    ap.add_argument("--out", default=r"C:\EdgeLog\custom_ml\keel_pertrade")
    a = ap.parse_args()

    leg = L.resolve_leg(a.leg)
    nq_file = a.nq_file or L._default_nq_file()
    arrays, _dropped = L.load_nq_arrays(nq_file, date_from=L._leg_date_from(leg))
    trades, _res = L.run_nq_backtest(arrays, leg=leg)
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in trades], key=lambda t: t[0])
    overl = sum(1 for i in range(1, len(T)) if T[i - 1][1] >= T[i][0])
    print(f"[keel-pertrade] {leg['leg_key']}: {len(T)} NQ trades, {overl} overlap/same-bar pairs "
          f"(the append contract needs 0)")
    start_k = 0
    if a.date_from:
        idx = pd.DatetimeIndex(arrays["index"])
        t0 = pd.Timestamp(a.date_from).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(a.date_from)
        start_k = next((i for i, t in enumerate(T) if idx[t[0]] >= t0), len(T))
    df, _kw = replay(arrays, T, version=leg["version"], start_k=start_k)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"replay_{leg['leg_key']}.csv")
    df.to_csv(path, index=False)
    exact = int((df.diff_live.abs() <= TOL).sum())
    n2 = int(df.same_day_2nd.sum())
    nd_off = df.diff_nightly.abs() > TOL
    print(f"[keel-pertrade] replayed {len(df)} trades from {df.entry_ts.iloc[0]} (k={start_k})")
    print(f"[keel-pertrade] PER-TRADE live vs walk: exact {exact} of {len(df)}; max |diff| "
          f"{df.diff_live.abs().max():.3g}")
    print(f"[keel-pertrade] NIGHTLY  live vs walk: differ on {int(nd_off.sum())} trades "
          f"(same-day 2nd+ entries {n2}; of the differing, {int((nd_off & df.same_day_2nd).sum())} are 2nd+); "
          f"mean |diff| where differing {df.diff_nightly.abs()[nd_off].mean() if nd_off.any() else 0:.3f}x")
    print(f"[keel-pertrade] wrote {path}")
    sys.exit(0 if exact == len(df) and overl == 0 else 1)


if __name__ == "__main__":
    main()
