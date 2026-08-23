"""
ORB HUNT ROUND 4 (2026-08-22) — owner: "test more variations".

Two studies, both destined for COMPARE > STUDIES:

A. DOES THE CROWN TRAVEL? Run #234's config verbatim (no re-fit) on other markets,
   bar sizes and the 24-hour session. Pure diagnostics / reference rows — a config
   tuned on NQ 5m RTH is NOT re-tuned per market, so weak numbers here are expected
   and honest, not failures. Where the bar size changes, or_bars is scaled to keep
   the SAME 10-minute opening range (that duration is the strategy; the bar size only
   changes the granularity of the close-confirm and the exits).

B. EXIT MANAGEMENT ROUND 2 (ORB_3_9.py): re-entry after a real stop-out loss,
   time-based breakeven arm, and a breakeven lock above entry. One-at-a-time on the
   crown base. PRE-REGISTERED GATE (round 3's, unchanged, written before running):
   adopt-worthy only if roll12 win >= 72.7% AND worst roll12 >= -$22,050 AND
   sliced LB >= $88,943 — i.e. beat run #234 on all three robustness legs.

    python tools/orb_hunt4.py travel
    python tools/orb_hunt4.py exits
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, score, IS_END, LB_END          # noqa: E402
from tools.orb_hunt3 import INCUMBENT, measure, robustness       # noqa: E402

GATE = dict(win_pct=72.7, worst=-22050.0, lb_net=88943.0)

# instrument -> (cost_pts round-turn, $/pt). Same constants as ORB.md / t5_runboard.
COSTS = {"NQ": (0.533, 20.0), "ES": (0.363, 50.0)}


def load_master(fname, eth=False):
    """Load any NOADJ master. ETH sessions start 18:00 ET, so the session id uses the
    TRADE date (timestamp + 6h), not the calendar date — otherwise the 'opening range'
    would be the bars just after midnight."""
    df = pd.read_csv(os.path.join(ROOT, "augur_uploads", fname))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    sess = (df["_dt"] + pd.Timedelta(hours=6)).dt.date if eth else df["_dt"].dt.date
    df["day_id"] = pd.factorize(sess)[0]
    return dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                volume=df["volume"].values.astype(float) if "volume" in df.columns else None,
                day_id=df["day_id"].values, index=pd.DatetimeIndex(df["_dt"]))


def run_on(fname, params, inst, eth=False, strategy="ORB_3_6.py"):
    """#weights one config on one master; returns IS/LB/FULL dicts + roll12."""
    b = load_master(fname, eth=eth)
    mod = strat(strategy)
    cost, mult = COSTS[inst]
    r = mod.run_backtest(b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
                         day_id=b["day_id"], return_trades=True, **params)
    tr = (r or {}).get("trades") or []
    if not tr:
        return None
    idx = b["index"]
    ie = pd.Timestamp(IS_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(IS_END)
    le = pd.Timestamp(LB_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(LB_END)
    keep = [t for t in tr if idx[t[0]] <= le]
    raw = [t[2] for t in keep]
    dts = [idx[t[0]] for t in keep]
    pnl = [(x - cost) * mult for x in raw]
    f = score(raw, mult=mult, cost=cost)
    return dict(full=f,
                is_net=sum(p for d, p in zip(dts, pnl) if d <= ie),
                lb_net=sum(p for d, p in zip(dts, pnl) if d > ie),
                rob=robustness([d.tz_localize(None) for d in dts], pnl))


def pline(label, m):
    if m is None:
        print("%-42s NO TRADES" % label); return
    f, r = m["full"], m["rob"]
    print("%-42s n=%-5d IS $%9s  LB $%8s | TOT $%9s DD $%8s MAR %5.2f PF %5.3f | "
          "roll12 win %5.1f%% worst $%9s" % (
              label[:42], f["n"], format(int(m["is_net"]), ","), format(int(m["lb_net"]), ","),
              format(int(f["net"]), ","), format(int(f["dd"]), ","), min(f["mar"], 99),
              min(f["pf"], 9.999), r["win_pct"], format(int(r["worst"]), ",")))
    sys.stdout.flush()


# ── Study A: does the crown travel? ──────────────────────────────────────────────
TRAVEL = [
    ("NQ 5m RTH (the crown itself)", "NOADJ_NQ_5m_RTH.csv", "NQ", False, dict(INCUMBENT)),
    ("ES 5m RTH, config verbatim", "NOADJ_ES_5m_RTH.csv", "ES", False, dict(INCUMBENT)),
    ("NQ 15m RTH (OR = 2 bars = 30min)", "NOADJ_NQ_15m_RTH.csv", "NQ", False, dict(INCUMBENT)),
    ("NQ 2m RTH (OR = 5 bars = 10min)", "NOADJ_NQ_2m_RTH.csv", "NQ", False, dict(INCUMBENT, or_bars=5)),
    ("NQ 1m RTH (OR = 10 bars = 10min)", "NOADJ_NQ_1m_RTH.csv", "NQ", False, dict(INCUMBENT, or_bars=10)),
    ("NQ 5m ETH 24h (OR = 18:00 open)", "NOADJ_NQ_5m_ETH.csv", "NQ", True, dict(INCUMBENT)),
    ("ES 5m ETH 24h, config verbatim", "NOADJ_ES_5m_ETH.csv", "ES", True, dict(INCUMBENT)),
]


def sweep_travel():
    print("STUDY A — run #234's config, NO re-fit, other markets/bars/sessions")
    print("(weak rows are EXPECTED and honest: nothing here was tuned for its market)\n")
    for label, fname, inst, eth, p in TRAVEL:
        pline(label, run_on(fname, p, inst, eth=eth))


# ── Study B: exit management round 2 ─────────────────────────────────────────────
def sweep_exits():
    import importlib.util as ilu
    # parity first: all knobs off == ORB_3_6 crown, bit-identical trade tuples
    m6 = strat("ORB_3_6.py"); m9 = strat("ORB_3_9.py")
    from tools.orb_hunt import run as run5m
    _, t6, _ = run5m("ORB_3_6.py", INCUMBENT, None, LB_END)
    _, t9, _ = run5m("ORB_3_9.py", INCUMBENT, None, LB_END)
    same = len(t6) == len(t9) and all(a[:4] == b[:4] for a, b in zip(t6, t9))
    print("PARITY knobs-off vs ORB_3_6: %s (%d vs %d trades)" % ("IDENTICAL" if same else "*** DIFFERS ***", len(t6), len(t9)))
    if not same:
        sys.exit(1)
    print("\nPRE-REGISTERED GATE: roll12 win >= %.1f%% AND worst >= $%s AND LB >= $%s\n"
          % (GATE["win_pct"], format(int(GATE["worst"]), ","), format(int(GATE["lb_net"]), ",")))
    base = measure("ORB_3_9.py", dict(INCUMBENT))
    from tools.orb_hunt3 import line
    print(line("crown #234 (all round-4 knobs off)", base))
    rows = []
    for label, p in (
        [("reenter after stop x%d" % n, dict(INCUMBENT, reenter_stop=n)) for n in (1, 2)] +
        [("arm BE after %d bars" % n, dict(INCUMBENT, be_after_bars=n)) for n in (6, 12, 18, 24)] +
        [("BE lock +%.2fR" % f, dict(INCUMBENT, be_lock_frac=f)) for f in (0.05, 0.1, 0.2, 0.3)] +
        [("lock +0.1R & arm 18 bars", dict(INCUMBENT, be_lock_frac=0.1, be_after_bars=18))]
    ):
        m = measure("ORB_3_9.py", p)
        ok = (m and m["rob"]["win_pct"] >= GATE["win_pct"] and m["rob"]["worst"] >= GATE["worst"]
              and m["lb_net"] >= GATE["lb_net"])
        print(("GATE-PASS " if ok else "          ") + line(label, m))
        rows.append((label, p, m, ok))
    passed = [r for r in rows if r[3]]
    print("\n%d of %d cleared the pre-registered gate" % (len(passed), len(rows)))


SWEEPS = {"travel": sweep_travel, "exits": sweep_exits}

if __name__ == "__main__":
    SWEEPS[sys.argv[1] if len(sys.argv) > 1 else "travel"]()
