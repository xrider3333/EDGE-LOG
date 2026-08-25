"""NOISE crown parity — analysis of the 2026-08-24 engine-vs-NinjaTrader backtest.

Compares four blotters over the same window (NT chart: 525 days of MNQ 5m,
EDGELOG RTH 0930-1600, non-back-adjusted; engine: NOADJ_NQ_5m_RTH master):

  engine CROWN  (run #243 config: 44/0.75/1.5/vwap/k1.75 + skip_bot_short 0.20 + vol_skip 90)
  engine BASE   (same core, both filters off)
  NT CROWN      (EdgeLogNOISEPAR dump, SkipBotShort+VolSkipOn true)
  NT BASE       (same row, both knobs false)

and answers the leak question at the DAY level: which sessions did each side's
filters veto, do the two implementations agree, and is any disagreement a logic
error (one side wrong against the raw OHLC) or a data difference at the
percentile/threshold boundary (MNQ chart bars vs NQ master bars)?

Run: python tools/nt_noise_parity_analyze.py --crown <dump.csv> --base <dump.csv>
     (defaults: the 2026-08-24 dumps in C:\\EdgeLog\\nt_backtest)
"""
import argparse
import importlib.util
import os
import sys
from collections import defaultdict

import numpy as np

# The engine + master registry live in the working checkout (optimizer_history.db is
# not part of the git tree, so a fresh worktree has no master index) — allow override.
ROOT = os.environ.get("EDGELOG_ROOT",
                      os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.reconcile import edgelog_blotter, match  # noqa: E402
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

DUMP_DIR = r"C:\EdgeLog\nt_backtest"
FROM, TO = "2025-03-17", "2026-08-19"
CORE = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
            stop_mode="bandwidth", stop_k=1.75)
CROWN = dict(CORE, daytype_mode="skip_bot_short", daytype_lo=0.2, vol_skip_pct=90.0)


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dates(trades):
    return sorted({t.entry_dt.date() for t in trades})


def by_date(trades):
    d = defaultdict(list)
    for t in trades:
        d[t.entry_dt.date()].append(t)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crown", default="EdgeLogNOISE_20260824-164825.csv")
    ap.add_argument("--base", default="EdgeLogNOISE_20260824-164930.csv")
    ap.add_argument("--tol-min", type=int, default=2)
    a = ap.parse_args()

    rnd = _mod(os.path.join(ROOT, "tools", "reconcile_nt_dump.py"), "rnd")
    nz = _mod(os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py"), "nz")

    nt_crown, hdr_c = rnd.read_dump(os.path.join(DUMP_DIR, a.crown), 5)
    nt_base, hdr_b = rnd.read_dump(os.path.join(DUMP_DIR, a.base), 5)
    assert "skipBotShort=True" in hdr_c.get("lookback", "") and "volSkipOn=True" in hdr_c["lookback"], hdr_c
    assert "skipBotShort=False" in hdr_b.get("lookback", "") and "volSkipOn=False" in hdr_b["lookback"], hdr_b

    eng_crown, meta = edgelog_blotter("NOISE_1_0.py", "NQ", "5m", "rth", CROWN,
                                      date_from=FROM, date_to=TO, cost_pts=0.0, mult=20)
    eng_base, _ = edgelog_blotter("NOISE_1_0.py", "NQ", "5m", "rth", CORE,
                                  date_from=FROM, date_to=TO, cost_pts=0.0, mult=20)

    lo = min(t.entry_dt for t in eng_crown)
    hi = max(t.entry_dt for t in eng_crown)
    nt_crown = [t for t in nt_crown if lo <= t.entry_dt <= hi]
    nt_base = [t for t in nt_base if lo <= t.entry_dt <= hi]

    # ── engine-side filter flags, computed straight from the master ──────────
    master = find_master("NQ", "5m", "rth")
    arr = load_master_arrays(master, date_from=FROM, date_to=TO)
    h, l, c = arr["high"], arr["low"], arr["close"]
    did = np.asarray(arr["day_id"])
    idx = arr["index"]
    sb = nz._session_bounds(did, len(c))
    vol_pct = nz._vol_percentile(h, l, c, sb)
    dt_pos = nz._daytype_pos(h, l, c, sb)
    import pandas as pd
    sess_date = [pd.Timestamp(idx[a_]).date() for a_, b_ in sb]
    eng_vol_veto = {sess_date[i] for i in range(len(sb))
                    if not np.isnan(vol_pct[i]) and vol_pct[i] >= 90.0}
    eng_short_veto = {sess_date[i] for i in range(len(sb))
                      if not np.isnan(dt_pos[i]) and dt_pos[i] <= 0.2}

    # ── NT-side veto days, inferred: base traded, crown did not ─────────────
    nb, nc = by_date(nt_base), by_date(nt_crown)
    nt_all_veto = {d for d in nb if d not in nc}
    nt_short_veto_obs = {d for d in nb
                         if any(t.side < 0 for t in nb[d])
                         and d in nc and not any(t.side < 0 for t in nc[d])}
    eb_, ec_ = by_date(eng_base), by_date(eng_crown)
    eng_all_veto_obs = {d for d in eb_ if d not in ec_}
    eng_short_veto_obs = {d for d in eb_
                          if any(t.side < 0 for t in eb_[d])
                          and d in ec_ and not any(t.side < 0 for t in ec_[d])}

    print(f"window: {lo} -> {hi}   master {meta['master']}")
    print(f"trades: engine crown {len(eng_crown)} | NT crown {len(nt_crown)} | "
          f"engine base {len(eng_base)} | NT base {len(nt_base)}")

    # ── reconcile both pairs ────────────────────────────────────────────────
    for label, ea, na in (("CROWN", eng_crown, nt_crown), ("BASE ", eng_base, nt_base)):
        pairs, ua, ub = match(ea, na, 0, a.tol_min)
        ident = [(x, y) for x, y, _ in pairs if x.exit_dt == y.exit_dt]
        print(f"\n[{label}] matched {len(pairs)}/{max(len(ea), len(na))}  "
              f"exit-bar-identical {len(ident)}  "
              f"pnl gap on identical ${sum(y.pnl_usd - x.pnl_usd for x, y in ident):,.0f}  "
              f"unmatched eng {len(ua)} / NT {len(ub)}")
        if label.strip() == "CROWN":
            crown_ua, crown_ub = ua, ub

    base_pairs, base_ua, base_ub = match(eng_base, nt_base, 0, a.tol_min)
    base_mm_days = {t.entry_dt.date() for t in base_ua} | {t.entry_dt.date() for t in base_ub}

    # ── filter agreement ────────────────────────────────────────────────────
    print("\n== FILTER-DAY AGREEMENT (the leak question) ==")
    print(f"engine vol-veto sessions (flag): {len(eng_vol_veto)}  "
          f"| observable (base traded, crown empty): eng {len(eng_all_veto_obs)} vs NT {len(nt_all_veto)}")
    print(f"engine short-veto sessions (flag): {len(eng_short_veto)}  "
          f"| observable short-only vetoes: eng {len(eng_short_veto_obs)} vs NT {len(nt_short_veto_obs)}")
    d1 = sorted(nt_all_veto ^ eng_all_veto_obs)
    d2 = sorted(nt_short_veto_obs ^ eng_short_veto_obs)
    print(f"all-entry veto disagreements: {d1 if d1 else 'NONE'}")
    print(f"short-veto disagreements:     {d2 if d2 else 'NONE'}")
    for d in d1:
        si = sess_date.index(d)
        print(f"  {d}: eng vol_pct={vol_pct[si]:.2f} (veto iff >=90) | "
              f"eng base {len(eb_.get(d, []))} tr, eng crown {len(ec_.get(d, []))} tr, "
              f"NT base {len(nb.get(d, []))} tr, NT crown {len(nc.get(d, []))} tr")
    for d in d2:
        si = sess_date.index(d)
        print(f"  {d}: eng dt_pos={dt_pos[si]:.4f} (veto iff <=0.2) | "
              f"NT base shorts {sum(1 for t in nb.get(d, []) if t.side < 0)}, "
              f"NT crown shorts {sum(1 for t in nc.get(d, []) if t.side < 0)}")

    # ── classify crown mismatches ───────────────────────────────────────────
    print("\n== CROWN MISMATCH CLASSIFICATION ==")
    filt_dis = set(d1) | set(d2)
    cnt = defaultdict(int)
    rows = []
    for src, lst in (("eng", crown_ua), ("NT ", crown_ub)):
        for t in lst:
            d = t.entry_dt.date()
            if d in filt_dis:
                cls = "FILTER DISAGREEMENT"
            elif d in base_mm_days:
                cls = "core/data (mismatch exists in BASE run too)"
            else:
                cls = "filter-side cascade (day matched in BASE, differs only with filters on)"
            cnt[cls] += 1
            rows.append((src, t.entry_dt, t.side, t.pnl_usd, cls))
    for r in sorted(rows, key=lambda r: r[1]):
        print(f"  [{r[0]}] {r[1]}  side={r[2]:+d}  pnl${r[3]:>9,.0f}  {r[4]}")
    print("\ncounts:", dict(cnt))

    # ── boundary audit helper: percentile detail for chosen days ────────────
    print("\n== VETO-DAY BOUNDARY DETAIL (for the hand audit) ==")
    interesting = sorted(filt_dis) + sorted(eng_vol_veto)[:0]
    for d in interesting:
        si = sess_date.index(d)
        a_, b_ = sb[si - 1]
        print(f"  {d}: prior sess {sess_date[si-1]} H={h[a_:b_].max():.2f} L={l[a_:b_].min():.2f} "
              f"C={c[b_-1]:.2f} (H-L)/C={(h[a_:b_].max()-l[a_:b_].min())/c[b_-1]:.5f} "
              f"pct={vol_pct[si]:.2f} dt_pos={dt_pos[si]:.4f}")


if __name__ == "__main__":
    main()
