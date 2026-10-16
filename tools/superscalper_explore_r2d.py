# SUPERSCALPER r2d (prereg docs/PREREG_tv_superscalper_r2d_paths_2026-10-16.md): the file-default run on NQ 2023 and 2024 cut by the
# engine's ENTRY PATH (MAIN / BOS / OB / RE / TRAP / OD) and side, at 0.706 and at +1 tick (0.956). Descriptive only.
# Reuses r2's harness (sha-checked) for the engine, master and four numbers; parity gate = r2b's 2023 total. OUR PORT, dev data only.
#   python tools/superscalper_explore_r2d.py
import hashlib, json, math, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_superscalper_r2d_paths_2026-10-16.md")
PREREG_LF_SHA = "e1868258e9381242be86bd93ad111eecd838b8ef28e2dfcb8a90b54300ebde72"
R2 = os.path.join(SHARED, "tools", "superscalper_explore_r2.py")
R2_LF_SHA = "26a2f9aab8f83ee3b058f4d9492e906d4f5484643eb4122be6f87eff29ecf9ab"
PORTS = [os.path.join(SHARED, "augur_strategies", "MISC_SUPERSCALPER_1_0.py"),
         r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\superscalp\augur_strategies\MISC_SUPERSCALPER_1_0.py"]
PORT_LF_SHA = "b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1"
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2d.json"
PATHS = ("MAIN", "BOS", "OB", "RE", "TRAP", "OD")
# parity gates (close_rule 'any', 0.706): r2b's 2023 and r2 E1's 2024. The win rate tells 'any' from 'fifo' (same totals,
# different per-trade pairing - and 'fifo' would book an exit against the OLDEST ticket's path, scrambling this split).
GATES = {"2023": dict(trades=2311, net=2005.9, win=0.5690), "2024": dict(trades=2633, net=1997.4, win=0.5853)}
COSTS = (("0.706", 0.706), ("+1 tick 0.956", 0.956))


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def trades(R, yr):
    """r2's Runner.trades, plus each trade's path, side and exit reason (same engine call, same master, same day calendar)."""
    m, a = R.arrays("NQ", yr)
    r = R.run_bt(R.port, arrays=a, master=m, params=dict(close_rule="any", intrabar="worst", _detail=True), cost_pts=0.0,
                 return_trades=True)
    rows = (r or {}).get("trade_detail") or []
    idx = pd.DatetimeIndex(a["index"])
    if idx.tz is None:
        idx = idx.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    day = pd.Series(idx.tz_convert("America/New_York").normalize().tz_localize(None))
    days = pd.DatetimeIndex(sorted(day.unique()))
    df = pd.DataFrame({"pnl": [x["pnl_pts"] for x in rows], "path": [x["path"] for x in rows],
                       "side": ["long" if x["side"] > 0 else "short" for x in rows],
                       "reason": [x["exit_reason"] for x in rows], "exit_day": [day.iloc[x["exit_bar"]] for x in rows]})
    return df, days


def pf_raw(g, cost):
    """net PF from unrounded sums (r2's stats() rounds to 4 dp before a hard threshold would read it)"""
    net = np.asarray(g, float) - cost
    lo = -net[net <= 0].sum()
    return float(net[net > 0].sum() / lo) if lo > 0 else float("inf")


def finite(x):
    """JSON-safe: non-finite floats become strings (a bare Infinity / NaN token is not valid JSON)"""
    if isinstance(x, dict):
        return {k: finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [finite(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else str(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def port_still(port):
    if lf_sha(port) != PORT_LF_SHA:
        sys.exit("refused: the port changed during the run (no longer LF sha %s) - nothing written" % PORT_LF_SHA)


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256", got, "OK" if got == PREREG_LF_SHA else "MISMATCH", flush=True)
    if got != PREREG_LF_SHA:
        sys.exit("refused: prereg is not the pinned one")
    if lf_sha(R2) != R2_LF_SHA:
        sys.exit("refused: r2 harness is not %s" % R2_LF_SHA)
    port = next((p for p in PORTS if os.path.exists(p) and lf_sha(p) == PORT_LF_SHA), None)
    if port is None:
        sys.exit("refused: no port with LF sha %s" % PORT_LF_SHA)
    sys.path.insert(0, os.path.dirname(R2))
    import superscalper_explore_r2 as X
    print("r2 harness OK; port", port, "OK; harness LF sha256", lf_sha(os.path.abspath(__file__)), flush=True)
    R = X.Runner(port)
    out = {}
    raw = {}
    for yname, yr in (("2023", X.Y23), ("2024", X.Y24)):
        d, days = trades(R, yr)
        port_still(port)
        G = GATES[yname]
        tot = round(float((d["pnl"] - 0.706).sum()), 1)
        win = float(((d["pnl"] - 0.706) > 0).mean())
        print("PARITY GATE %s 'any': %d trades, %.1f net pt, win %.4f (expected %d / %.1f / %.4f)" % (
            yname, len(d), tot, win, G["trades"], G["net"], G["win"]), flush=True)
        if len(d) != G["trades"] or abs(tot - G["net"]) > 0.05 or abs(win - G["win"]) > 0.0005:
            sys.exit("refused: parity gate failed for %s - not the r2/r2b port, tape and close rule" % yname)
        raw[yname] = d
        print("\nNQ %s: %d trades; paths %s" % (yname, len(d), d["path"].value_counts().to_dict()), flush=True)
        out[yname] = {"exit_mix": {p: d[d["path"] == p]["reason"].value_counts(normalize=True).round(3).to_dict()
                                   for p in sorted(d["path"].unique())}}
        for cname, cost in COSTS:
            X.COST["NQ"] = cost
            rows = {}
            for p in PATHS + tuple(sorted(set(d["path"]) - set(PATHS))):
                for s in ("long", "short"):
                    rows["%s %s" % (p, s)] = X.Runner.read(R, "NQ", d[(d["path"] == p) & (d["side"] == s)], days,
                                                           "%s %s %s @ %s" % (yname, p, s, cname))
                rows["%s both" % p] = X.Runner.read(R, "NQ", d[d["path"] == p], days, "%s %s both @ %s" % (yname, p, cname))
            for s in ("long", "short"):
                rows["ALL %s" % s] = X.Runner.read(R, "NQ", d[d["side"] == s], days, "%s ALL %s @ %s" % (yname, s, cname))
            out[yname][cname] = rows
        X.COST["NQ"] = 0.706

    port_still(port)

    def cell(y, k):
        p_, s_ = k.split(" ")
        d = raw[y]
        return d[(d["path"] == p_) & (d["side"] == s_)]["pnl"].values
    cells = ["%s %s" % (p, s) for p in PATHS for s in ("long", "short")]
    out["carry_test_unrounded"] = {k: {y: dict(trades=len(cell(y, k)), pf_0706=pf_raw(cell(y, k), 0.706),
                                               pf_0956=pf_raw(cell(y, k), 0.956)) for y in ("2023", "2024")} for k in cells}
    carry = [k for k in cells if all(v["pf_0706"] >= 1.10 and v["trades"] >= 100 and v["pf_0956"] > 1.0
                                     for v in out["carry_test_unrounded"][k].values())]
    out["carries_both_years"] = carry
    print("\nA path-side that carries it in BOTH years (PF >= 1.10, >= 100 trades each, PF > 1.00 at +1 tick):", carry or "none",
          flush=True)
    json.dump(finite(out), open(OUT, "w"), indent=1, default=str, allow_nan=False)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
