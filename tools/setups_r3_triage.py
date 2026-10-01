"""SETUPS round 3 / CBU rules v1 - Test 2, the outcome triage (SETUPS_PREREG_R3_CBU_V1.md sections 4 and 4a).

Runs the 16 cells (base {any, held} x window {am, day} x exit {ride, be2r} x root {NQ, ES}; vol_mult 1.5,
range_atr 1.2, body_atr 0.7) through augur_strategies/CBUQ_2_0.py's own run_backtest on the roll-corrected
FADJ_ 1-minute 24-hour masters over the SELECTION window only (2010-06-07 .. 2025-07-06), and scores each cell
with the house scorer (tools/setups_r1_triage.score) in MICRO dollars: MNQ 1.20 points a round trip at $2
(stress 1.45), MES 0.63 at $5 (stress 0.88).

A cell ADVANCES only if it passes the house bar at house cost, keeps PF >= 1.10 at stress cost, and at least 2
of its 7 one-step neighbours keep PF >= 1.15 at house cost. Neighbours (section 4a): base flipped, window
flipped, exit flipped, vol_mult 1.25 and 2.0, range_atr 1.0 and 1.4. Neighbours are only run for cells that
pass the first two tests. The NOISE #382 overlap (round 1's test) is reported for every cell that passes the
house bar.

Nothing after 2025-07-06 is ever passed to the strategy (round 2's load_window slices and asserts the window).
No job is queued and nothing is written to Firestore; the overlap READS run #382 once.

    python tools/setups_r3_triage.py
    -> C:\\EdgeLog\\_anatomy_cache\\setups_r3_results\\triage.csv, triage_summary.txt
"""
import csv
import importlib.util as ilu
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(1, HERE)

import setups_r1_triage as R1                                  # noqa: E402  the house scorer
import setups_r2_triage as R2                                  # noqa: E402  window loader + NOISE #382 overlap

score = R1.score
FILE = "CBUQ_2_0.py"
INSTR = {"NQ": dict(mult=2.0, cost=1.20, stress=1.45, micro="MNQ"),
         "ES": dict(mult=5.0, cost=0.63, stress=0.88, micro="MES")}
BASES, WINDOWS, EXITS = ("any", "held"), ("am", "day"), ("ride", "be2r")
THRESH = dict(vol_mult=1.5, range_atr=1.2, body_atr=0.7)
OUTDIR = r"C:\EdgeLog\_anatomy_cache\setups_r3_results"
_MOD = []


def _mod():
    if not _MOD:
        sp = ilu.spec_from_file_location("setups_r3_cbuq2", os.path.join(ROOT, "augur_strategies", FILE))
        m = ilu.module_from_spec(sp)
        sp.loader.exec_module(m)
        _MOD.append(m)
    return _MOD[0]


def cells():
    return [dict(THRESH, base=b, window=w, exit_mode=e) for b in BASES for w in WINDOWS for e in EXITS]


def neighbours_of(cell):
    flip = lambda seq, x: [y for y in seq if y != x][0]
    return [("base->" + flip(BASES, cell["base"]), dict(cell, base=flip(BASES, cell["base"]))),
            ("window->" + flip(WINDOWS, cell["window"]), dict(cell, window=flip(WINDOWS, cell["window"]))),
            ("exit->" + flip(EXITS, cell["exit_mode"]), dict(cell, exit_mode=flip(EXITS, cell["exit_mode"]))),
            ("vol 1.25", dict(cell, vol_mult=1.25)), ("vol 2.0", dict(cell, vol_mult=2.0)),
            ("range 1.0", dict(cell, range_atr=1.0)), ("range 1.4", dict(cell, range_atr=1.4))]


def ckey(c):
    return (c["base"], c["window"], c["exit_mode"], c["vol_mult"], c["range_atr"], c["body_atr"])


def why_fail(h, cost, mult):
    return R2.why_fail(h, cost, mult)


def run_cell(a, root, cell, role="triage", parent=""):
    R2.assert_window(a)
    t0 = time.time()
    r = _mod().run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"], index=a["index"],
                            return_trades=True, **cell)
    secs = time.time() - t0
    tr = (r or {}).get("trades") or []
    pts = [t[2] for t in tr]
    holds = [t[1] - t[0] for t in tr]
    spec = INSTR[root]
    h = score(pts, holds, spec["cost"], spec["mult"])
    s = score(pts, holds, spec["stress"], spec["mult"])
    ix = pd.DatetimeIndex(a["index"])
    days = len(set(ix[[int(t[0]) for t in tr]].date)) if tr else 0
    row = dict(role=role, parent=parent, root=root, micro=spec["micro"], base=cell["base"], window=cell["window"],
               exit_mode=cell["exit_mode"], vol_mult=cell["vol_mult"], range_atr=cell["range_atr"],
               body_atr=cell["body_atr"], secs=round(secs, 2), trade_days=days,
               gross_pts=round(float(np.sum(pts)), 2) if pts else 0.0, **h,
               stress_pf=s["pf"], stress_net=s["net"], alarm=int(h["n"] > 0 and (h["pf"] >= 2 or h["mar"] >= 20)),
               why=why_fail(h, spec["cost"], spec["mult"]), nb_ok="", advance="", nb_detail="")
    return row, tr


def run_root(root):
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    a = R2.load_window(root)
    rows, done, trades = [], {}, {}
    for cell in cells():
        row, tr = run_cell(a, root, cell)
        rows.append(row)
        done[ckey(cell)] = row
        trades[ckey(cell)] = tr
        print("%s %-4s %-3s %-4s n=%5d PF=%.3f net=$%s stressPF=%.3f %s%s" % (
            root, cell["base"], cell["window"], cell["exit_mode"], row["n"], row["pf"], format(row["net"], ","),
            row["stress_pf"], "PASS" if row["PASS"] else "fail", "  ALARM" if row["alarm"] else ""), flush=True)
    ix = pd.DatetimeIndex(a["index"])
    passing_trades = {}
    for cell in cells():
        par = done[ckey(cell)]
        if par["PASS"]:
            passing_trades[ckey(cell)] = [(str(ix[int(t[0])].date()), 1, float(t[2])) for t in trades[ckey(cell)]]
        if not (par["PASS"] and par["stress_pf"] >= 1.10):
            continue
        good, notes = 0, []
        for label, nc in neighbours_of(cell):
            k = ckey(nc)
            if k not in done:
                nrow, _ = run_cell(a, root, nc, role="neighbour", parent="%s/%s/%s" % (cell["base"], cell["window"], cell["exit_mode"]))
                rows.append(nrow)
                done[k] = nrow
            nrow = done[k]
            ok = int(nrow["n"] > 0 and nrow["pf"] >= 1.15)
            good += ok
            notes.append("%s PF=%.3f n=%d%s" % (label, nrow["pf"], nrow["n"], " ok" if ok else ""))
        par["nb_ok"] = "%d/7" % good
        par["advance"] = int(good >= 2)
        par["nb_detail"] = " | ".join(notes)
    return rows, passing_trades


def holiday_audit(root):
    """Sessions in the window whose regular bars end before 13:14 that are NOT listed holidays (information:
    the holiday list is calendar knowledge; this shows what it leaves in)."""
    a = R2.load_window(root)
    ix = pd.DatetimeIndex(a["index"])
    if ix.tz is not None:
        ix = ix.tz_convert("America/New_York").tz_localize(None)
    m = ix.hour * 60 + ix.minute
    rth = (m >= 570) & (m < 960)
    last = pd.Series(m[rth], index=ix[rth].normalize()).groupby(level=0).max()
    hol = set(str(np.datetime64(int(x), "D")) for x in _mod()._holidays())
    short = [str(d.date()) for d, v in last.items() if v < 13 * 60 + 14]
    return [d for d in short if d not in hol], [d for d in short if d in hol]


def _fmt(r):
    return ("%-3s %-4s %-3s %-4s n=%5d days=%4d PF=%5.3f net=$%8s net/DD=%6.2f slices=%d/8 top10=%4s%% exTop10=$%7s "
            "$/tr=%6.2f stressPF=%5.3f %s" % (r["root"], r["base"], r["window"], r["exit_mode"], r["n"], r["trade_days"],
                                               r["pf"], format(r["net"], ","), min(r["mar"], 99.0), r["folds8"],
                                               r["top10_pct"], format(r["exnet"], ","), r["per_trade"], r["stress_pf"],
                                               "PASS" if r["PASS"] else "fail: " + r["why"]))


def summarise(rows, overlaps, audits, secs):
    tri = [r for r in rows if r["role"] == "triage"]
    L = ["SETUPS round 3 (CBU rules v1) triage - SETUPS_PREREG_R3_CBU_V1.md s.4/4a; window %s .. %s; FADJ 1m ETH; "
         "vol 1.5x, range 1.2 ATR, body 0.7 ATR" % (R2.WIN_FROM, R2.WIN_TO)]
    for root in INSTR:
        L.append("master " + R2.provenance(root))
    L.append("costs (micro): MNQ 1.20 / stress 1.45 pts at $2; MES 0.63 / stress 0.88 pts at $5. House bar: PF>=1.25, "
             "net/DD>=8, n>=300, >=6 of 8 slices positive, top-10 share<90% with positive net without them, "
             "$/trade>=2x cost.")
    for root, (left_in, listed) in audits.items():
        L.append("%s sessions ending before 13:14: %d listed holidays (no decisions), %d not listed (left in): %s"
                 % (root, len(listed), len(left_in), ", ".join(left_in[:12]) + (" ..." if len(left_in) > 12 else "")))
    L.append("")
    L.append("== the 16 cells (house cost) ==")
    for r in tri:
        L.append(_fmt(r) + ("  ALARM(PF>=2 or net/DD>=20)" if r["alarm"] else ""))
    npass = sum(r["PASS"] for r in tri)
    two = [r for r in tri if r["PASS"] and r["stress_pf"] >= 1.10]
    L.append("")
    L.append("cells passing the house bar at house cost: %d of 16; of those with stress PF >= 1.10: %d" % (npass, len(two)))
    for r in two:
        L.append("  %s %s/%s/%s neighbours with PF>=1.15 = %s -> %s" % (r["root"], r["base"], r["window"], r["exit_mode"],
                                                                      r["nb_ok"], "ADVANCES" if r["advance"] else "does not advance"))
        for part in r["nb_detail"].split(" | "):
            L.append("      " + part)
    adv = [r for r in tri if r["advance"] == 1]
    L.append("")
    L.append("ADVANCING CELLS: %s" % (", ".join("%s %s/%s/%s" % (r["root"], r["base"], r["window"], r["exit_mode"]) for r in adv) or "none"))
    if overlaps:
        L.append("")
        L.append("== NOISE #382 overlap, cells passing the house bar ==")
        L.extend(overlaps)
    L.append("")
    L.append("== ride vs be2r, same root/base/window (house cost) ==")
    for root in INSTR:
        for b in BASES:
            for w in WINDOWS:
                rr = {x["exit_mode"]: x for x in tri if x["root"] == root and x["base"] == b and x["window"] == w}
                L.append("%s %-4s %-3s ride PF=%.3f net=$%s | be2r PF=%.3f net=$%s" % (
                    root, b, w, rr["ride"]["pf"], format(rr["ride"]["net"], ","), rr["be2r"]["pf"], format(rr["be2r"]["net"], ",")))
    L.append("")
    L.append("runtime %.1f s" % secs)
    return "\n".join(L)


def main():
    t0 = time.time()
    print("cells: 16 triage (base x window x exit x root), window %s..%s" % (R2.WIN_FROM, R2.WIN_TO), flush=True)
    rows, passing = [], {}
    with ProcessPoolExecutor(max_workers=len(INSTR)) as ex:
        futs = {root: ex.submit(run_root, root) for root in INSTR}
        auds = {root: ex.submit(holiday_audit, root) for root in INSTR}
        for root, f in futs.items():
            r, p = f.result()
            rows.extend(r)
            passing.update({(root,) + k: v for k, v in p.items()})
        audits = {root: f.result() for root, f in auds.items()}
    overlaps = []
    if passing:
        try:
            crown = R2.crown_days(382)
            for key, tr in sorted(passing.items()):
                root = key[0]
                overlaps.append(R2.overlap_lines("%s %s/%s/%s" % (root, key[1], key[2], key[3]), tr, INSTR[root]["mult"], crown))
        except BaseException as e:
            overlaps.append("NOISE #382 overlap unavailable: %r" % (e,))
    summary = summarise(rows, overlaps, audits, time.time() - t0)
    os.makedirs(OUTDIR, exist_ok=True)
    cols = ["role", "parent", "root", "micro", "base", "window", "exit_mode", "vol_mult", "range_atr", "body_atr", "n",
            "trade_days", "gross_pts", "net", "pf", "dd", "mar", "win", "folds8", "top10_pct", "exnet", "per_trade",
            "hold_med", "PASS", "why", "stress_pf", "stress_net", "alarm", "nb_ok", "advance", "nb_detail", "secs"]
    with open(os.path.join(OUTDIR, "triage.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUTDIR, "triage_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(summary + "\n")
    print(summary)


if __name__ == "__main__":
    main()
