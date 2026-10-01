"""SETUPS round 2 - triage driver (pre-registered in SETUPS_PREREG_R2.md section 4).

Runs the 40 pre-declared cells (5 filters x 2 exits x long/short x NQ/ES; min_win 5, stop buffer 0)
through CBUQ_PTS_1_0.py / CBDQ_PTS_1_0.py's own run_backtest on the roll-corrected FADJ_ 1-minute
24-hour masters over the SELECTION window only (2010-06-07 .. 2025-07-06), and scores every cell with
the round-1 house scorer (tools/setups_r1_triage.score - the round-37 score(), in dollars) at the house
cost (NQ 0.533 pts $20, ES 0.363 pts $50) and the stress cost (0.783 / 0.613).

A cell ADVANCES only if it passes the house bar at house cost, keeps PF >= 1.10 at the stress cost, and
at least 2 of its one-step neighbours keep PF >= 1.15 at house cost. Its neighbours are: the filter moved
to each of the other four, the exit flipped, min_win 10, stop_buf_atr 0.25. Neighbours are only run for
cells that pass the first two tests. Also reported, for information: each filter against its 'none' twin
(per root / side / exit), and for an advancing cell the NOISE #382 overlap (round 1's overlap test).

Nothing after 2025-07-06 is ever passed to a strategy: the FADJ arrays are sliced to the window the
moment they are read, and every cell asserts the last bar's ET date. No job is queued, nothing is written
to Firestore (the only Firestore access, for the overlap, is one READ of run #382).

    python tools/setups_r2_triage.py              (from anywhere; data is read from the shared checkout)
    python tools/setups_r2_triage.py --overlap-selftest     (dry run of the #382 overlap on the best cell; not an official result)
    -> tools/setups_r2_results/triage.csv, triage_summary.txt
"""
import os, sys, csv, time, json, sqlite3, itertools, importlib.util as ilu
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_REPO = ROOT if os.path.exists(os.path.join(ROOT, "augur_uploads", "FADJ_NQ_1m_ETH.csv")) \
    else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
sys.path.insert(1, HERE)

import setups_r1_triage as R1                                  # noqa: E402  the round-1 house scorer + costs

score = R1.score
INSTR = R1.INSTR                                              # NQ mult 20 cost 0.533 stress 0.783 / ES 50, 0.363, 0.613
FILTS = ["none", "trend", "open30", "ema3", "yhigh"]
EXITS = ["ride", "target"]
FILES = {1: "CBUQ_PTS_1_0.py", -1: "CBDQ_PTS_1_0.py"}
WIN_FROM, WIN_TO = "2010-06-07", "2025-07-06"
SPLIT = pd.Timestamp("2025-07-07")                            # first held-out day; no bar from here on may be used
OUTDIR = os.path.join(HERE, "setups_r2_results")
SOURCE = "db_fadj_eth"
BASE = dict(min_win=5, stop_buf_atr=0.0)

_MODS = {}


def _load_mod(fn):
    if fn not in _MODS:
        sp = ilu.spec_from_file_location("setups_r2_" + fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
        m = ilu.module_from_spec(sp)
        sp.loader.exec_module(m)
        _MODS[fn] = m
    return _MODS[fn]


def load_window(root):
    """FADJ 1m ETH arrays for `root`, sliced to the selection window before anything else sees them."""
    import augur_engine.data as D
    D.UPLOADS = os.path.join(DATA_REPO, "augur_uploads")
    m = dict(filename="FADJ_%s_1m_ETH.csv" % root, instrument=root, timeframe="1m", source=SOURCE, session="eth")
    a = D.load_master_arrays(m, date_from=WIN_FROM, date_to=WIN_TO)
    assert_window(a)
    return a


def assert_window(a):
    ix = pd.DatetimeIndex(a["index"])
    last = ix[-1].tz_localize(None) if ix.tz is not None else ix[-1]
    first = ix[0].tz_localize(None) if ix.tz is not None else ix[0]
    assert last < SPLIT, "a bar on or after 2025-07-07 reached the triage: %s" % ix[-1]
    assert first >= pd.Timestamp(WIN_FROM), "a bar before the window start reached the triage: %s" % ix[0]
    for k in ("open", "high", "low", "close", "volume"):
        assert len(a[k]) == len(ix)


def provenance(root):
    """The master's registry row (read only), so the result names the roll table it rests on."""
    try:
        con = sqlite3.connect("file:%s?mode=ro" % os.path.join(DATA_REPO, "optimizer_history.db").replace("\\", "/"), uri=True)
        row = con.execute("SELECT provenance FROM csv_files WHERE filename=? AND is_master=1",
                          ("FADJ_%s_1m_ETH.csv" % root,)).fetchone()
        con.close()
        p = json.loads(row[0]) if row and row[0] else {}
        return "%s: built %s, roll table %s sha %s, %s switches applied" % (
            root, p.get("built_at"), p.get("roll_table"), p.get("roll_table_sha"), p.get("switches_applied"))
    except Exception as e:                                    # registry unreadable: not fatal for the numbers
        return "%s: provenance unavailable (%s)" % (root, e)


def why_fail(h, cost, mult):
    """Which parts of the house bar a cell misses (empty = passes)."""
    if h["n"] == 0:
        return "no trades"
    f = []
    if h["pf"] < 1.25:
        f.append("PF %.2f<1.25" % h["pf"])
    if h["mar"] < 8:
        f.append("net/DD %.1f<8" % h["mar"])
    if h["n"] < 300:
        f.append("n %d<300" % h["n"])
    if h["folds8"] < 6:
        f.append("slices %d/8<6" % h["folds8"])
    if not (h["top10_pct"] < 90 and h["exnet"] > 0):
        f.append("top-10 share %s%% / net ex top-10 $%s" % (h["top10_pct"], format(h["exnet"], ",")))
    if h["per_trade"] < 2 * cost * mult:
        f.append("$/trade %.1f<%.1f" % (h["per_trade"], 2 * cost * mult))
    return "; ".join(f)


def run_cell(a, root, side, cell, role="triage", parent=""):
    """One backtest through the strategy file's own run_backtest, scored at house and stress cost."""
    assert_window(a)
    mod = _load_mod(FILES[side])
    t0 = time.time()
    r = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"], index=a["index"],
                         return_trades=True, **cell)
    secs = time.time() - t0
    tr = (r or {}).get("trades") or []
    pts = [t[2] for t in tr]
    holds = [t[1] - t[0] for t in tr]
    spec = INSTR[root]
    h = score(pts, holds, spec["cost"], spec["mult"])
    s = score(pts, holds, spec["stress"], spec["mult"])
    row = dict(role=role, parent=parent, root=root, side="long" if side == 1 else "short", file=FILES[side],
               filt=cell["filt"], exit_mode=cell["exit_mode"], min_win=cell["min_win"],
               stop_buf_atr=cell["stop_buf_atr"], secs=round(secs, 2), **h,
               stress_pf=s["pf"], stress_net=s["net"], stress_n=s["n"],
               alarm=int(h["n"] > 0 and (h["pf"] >= 2 or h["mar"] >= 20)),
               why=why_fail(h, spec["cost"], spec["mult"]), nb_ok="", advance="")
    return row, tr


def ckey(row):
    return (row["filt"], row["exit_mode"], row["min_win"], row["stop_buf_atr"])


def neighbours_of(cell):
    """One-step neighbours: the filter moved to each other filter, the exit flipped, min_win 10, buffer 0.25."""
    out = [("filter->" + f, dict(cell, filt=f)) for f in FILTS if f != cell["filt"]]
    out.append(("exit->" + [e for e in EXITS if e != cell["exit_mode"]][0],
                dict(cell, exit_mode=[e for e in EXITS if e != cell["exit_mode"]][0])))
    out.append(("min_win->10", dict(cell, min_win=10)))
    out.append(("stop_buf->0.25", dict(cell, stop_buf_atr=0.25)))
    return out


def run_root(root):
    """All 20 triage cells for one root (long then short), then the neighbours of every cell that passes
    the house bar at house cost with stress PF >= 1.10. Returns (rows, trades of advancing cells)."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    a = load_window(root)
    rows, done, trades = [], {}, {}
    for side in (1, -1):
        for filt in FILTS:
            for ex in EXITS:
                cell = dict(BASE, filt=filt, exit_mode=ex)
                row, tr = run_cell(a, root, side, cell)
                rows.append(row)
                done[(side,) + ckey(row)] = row
                trades[(side,) + ckey(row)] = tr
                print("%s %-5s %-6s %-6s n=%5d PF=%.3f net=%s stressPF=%.3f %s%s" % (
                    root, row["side"], filt, ex, row["n"], row["pf"], format(row["net"], ","), row["stress_pf"],
                    "PASS" if row["PASS"] else "fail", "  ALARM" if row["alarm"] else ""), flush=True)
    adv_trades = {}
    for side in (1, -1):
        for filt in FILTS:
            for ex in EXITS:
                par = done[(side, filt, ex, 5, 0.0)]
                if not (par["PASS"] and par["stress_pf"] >= 1.10):
                    continue
                cell = dict(BASE, filt=filt, exit_mode=ex)
                good, tot, notes = 0, 0, []
                for label, nc in neighbours_of(cell):
                    k = (side, nc["filt"], nc["exit_mode"], nc["min_win"], nc["stop_buf_atr"])
                    if k in done:
                        nrow = done[k]
                        # a neighbour that is itself one of the 20 triage cells is reported once there
                    else:
                        nrow, ntr = run_cell(a, root, side, nc, role="neighbour", parent="%s/%s" % (filt, ex))
                        rows.append(nrow)
                        done[k] = nrow
                    tot += 1
                    ok = int(nrow["n"] > 0 and nrow["pf"] >= 1.15)
                    good += ok
                    notes.append("%s PF=%.3f n=%d%s" % (label, nrow["pf"], nrow["n"], " ok" if ok else ""))
                par["nb_ok"] = "%d/%d" % (good, tot)
                par["advance"] = int(good >= 2)
                par["nb_detail"] = " | ".join(notes)
                print("%s %-5s %-6s %-6s PASSES -> neighbours %s  %s" % (root, par["side"], filt, ex, par["nb_ok"],
                      "ADVANCES" if par["advance"] else "no"), flush=True)
                if par["advance"]:
                    ix = pd.DatetimeIndex(a["index"])
                    adv_trades[(side, filt, ex)] = [(str(ix[int(t[0])].date()), int(t[3]), float(t[2])) for t in trades[(side, filt, ex, 5, 0.0)]]
    return rows, adv_trades


# ─────────────────────────────────────────────────────────────────────────────
# the NOISE #382 overlap (round 1's tools/setups_r1_overlap.py logic, restricted to the selection window)
# ─────────────────────────────────────────────────────────────────────────────
def crown_days(run_id=382):
    """(label, {date: side}) for a crown, re-run from its run doc over 2010-06-07..2025-07-06. One Firestore READ."""
    import augur_engine.data as D
    from augur_engine.engine import run_backtest as engine_backtest
    import queue_guard as QG
    D.UPLOADS = os.path.join(DATA_REPO, "augur_uploads")
    D.DB_PATH = os.path.join(DATA_REPO, "optimizer_history.db")
    kw, d = QG._guard_kwargs_from_run(run_id, os.path.join(DATA_REPO, "serviceAccount.json"))
    m = D.find_master(kw["instrument"], kw["timeframe"], kw["session"], kw["source"])
    arr = D.load_master_arrays(m, date_from=WIN_FROM, date_to=WIN_TO)
    assert_window(arr)
    idx = pd.DatetimeIndex(arr["index"])
    resolved, _, _ = QG.resolve_params(kw["strategy_file"], kw["params"])
    r = engine_backtest(kw["strategy_file"], arrays=arr, params=dict(resolved), cost_pts=kw["cost_pts"], return_trades=True)
    days = {}
    for t in (r or {}).get("trades") or []:
        days.setdefault(str(idx[int(t[0])].date()), int(t[3]) if len(t) > 3 else 0)
    return "#%d %s (%s %s)" % (run_id, d.get("strategy"), kw["instrument"], kw["timeframe"]), days


def overlap_lines(label, cell_trades, mult, crown):
    """cell_trades: [(date, side, pts)]; crown: (label, {date: side}). Round 1's three numbers."""
    clabel, cdays = crown
    df = pd.DataFrame(cell_trades, columns=["day", "side", "pts"])
    df["usd"] = df.pts * mult
    shared = df[df.day.isin(cdays)]
    same = int(sum(1 for _, r in shared.iterrows() if cdays.get(r.day) == r.side))
    flat = df[~df.day.isin(cdays)]
    own = df.usd.sum()
    share = flat.usd.sum() / own if own > 0 else float("nan")
    return ("%s vs crown %s: crown trades on %d days | shared days %d (%.0f%% of the cell's %d trades), same direction %d of %d "
            "(%.0f%% of shared) | cell on crown-flat days: %d trades, gross $%s = %.0f%% of its own gross"
            % (label, clabel, len(cdays), len(shared), 100 * len(shared) / max(1, len(df)), len(df), same, len(shared),
               100 * same / max(1, len(shared)), len(flat), format(round(flat.usd.sum()), ","), 100 * share))


# ─────────────────────────────────────────────────────────────────────────────
# reporting
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_row(r):
    return ("%-3s %-5s %-6s %-6s n=%5d PF=%5.3f net=$%9s net/DD=%6.2f slices=%d/8 top10=%4s%% exTop10=$%8s $/tr=%7.2f "
            "stressPF=%5.3f %s" % (r["root"], r["side"], r["filt"], r["exit_mode"], r["n"], r["pf"],
                                    format(r["net"], ","), min(r["mar"], 99.0), r["folds8"], r["top10_pct"],
                                    format(r["exnet"], ","), r["per_trade"], r["stress_pf"],
                                    "PASS" if r["PASS"] else "fail: " + r["why"]))


def summarise(rows, adv_trades, overlaps, secs):
    L = []
    tri = [r for r in rows if r["role"] == "triage"]
    L.append("SETUPS round 2 triage - SETUPS_PREREG_R2.md; window %s .. %s; FADJ 1m ETH; min_win 5, stop buffer 0" % (WIN_FROM, WIN_TO))
    for root in INSTR:
        L.append("master " + provenance(root))
    L.append("costs: NQ house 0.533 / stress 0.783 pts ($20); ES house 0.363 / stress 0.613 pts ($50). House bar: PF>=1.25, "
             "net/DD>=8, n>=300, >=6 of 8 slices positive, top-10 share<90% with positive net without them, $/trade>=2x cost.")
    L.append("")
    L.append("== the 40 cells (house cost) ==")
    for root in INSTR:
        for side in ("long", "short"):
            for ex in EXITS:
                for filt in FILTS:
                    r = [x for x in tri if x["root"] == root and x["side"] == side and x["filt"] == filt and x["exit_mode"] == ex][0]
                    L.append(_fmt_row(r) + ("  ALARM(PF>=2 or net/DD>=20)" if r["alarm"] else ""))
    npass = sum(r["PASS"] for r in tri)
    passing = [r for r in tri if r["PASS"] and r["stress_pf"] >= 1.10]
    L.append("")
    L.append("cells passing the house bar at house cost: %d of 40; of those with stress PF >= 1.10: %d" % (npass, len(passing)))
    L.append("")
    L.append("== neighbours of every cell that passed both tests ==")
    if not passing:
        L.append("(none - no cell passes the house bar at house cost with stress PF >= 1.10, so no neighbour is run)")
    for r in passing:
        L.append("%s %s %s/%s: neighbours with PF>=1.15 = %s -> %s" % (r["root"], r["side"], r["filt"], r["exit_mode"], r["nb_ok"],
                                                                     "ADVANCES" if r["advance"] else "does not advance"))
        for part in r.get("nb_detail", "").split(" | "):
            L.append("      " + part)
    adv = [r for r in tri if r["advance"] == 1]
    L.append("")
    L.append("ADVANCING CELLS: %s" % (", ".join("%s %s %s/%s" % (r["root"], r["side"], r["filt"], r["exit_mode"]) for r in adv) or "none"))
    if overlaps:
        L.append("")
        L.append("== NOISE #382 overlap, advancing cells ==")
        L.extend(overlaps)
    L.append("")
    L.append("== each filter against its 'none' twin (house cost; same root, side, exit) ==")
    for root in INSTR:
        for side in ("long", "short"):
            for ex in EXITS:
                rr = {x["filt"]: x for x in tri if x["root"] == root and x["side"] == side and x["exit_mode"] == ex}
                nn = rr["none"]
                L.append("%s %s %s: none n=%d PF=%.3f net=$%s" % (root, side, ex, nn["n"], nn["pf"], format(nn["net"], ",")))
                for f in FILTS[1:]:
                    x = rr[f]
                    beats = (x["pf"] > nn["pf"]) and (x["net"] > nn["net"])
                    L.append("    %-6s n=%5d PF=%.3f (%+.3f) net=$%9s (%+d) $/trade=%7.2f vs %7.2f  %s" % (
                        f, x["n"], x["pf"], x["pf"] - nn["pf"], format(x["net"], ","), x["net"] - nn["net"],
                        x["per_trade"], nn["per_trade"], "beats none on PF and net" if beats else "does not beat none on both"))
    L.append("")
    L.append("runtime %.1f s" % secs)
    return "\n".join(L)


def write_outputs(rows, summary):
    os.makedirs(OUTDIR, exist_ok=True)
    cols = ["role", "parent", "root", "side", "file", "filt", "exit_mode", "min_win", "stop_buf_atr", "n", "net", "pf", "dd",
            "mar", "win", "folds8", "top10_pct", "exnet", "per_trade", "hold_med", "PASS", "why", "stress_n", "stress_pf",
            "stress_net", "alarm", "nb_ok", "advance", "secs"]
    with open(os.path.join(OUTDIR, "triage.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUTDIR, "triage_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(summary + "\n")


def main():
    t0 = time.time()
    print("cells: 40 triage (5 filt x 2 exit x 2 sides x 2 roots), window %s..%s" % (WIN_FROM, WIN_TO), flush=True)
    rows, adv_trades = [], {}
    with ProcessPoolExecutor(max_workers=len(INSTR)) as ex:
        futs = {root: ex.submit(run_root, root) for root in INSTR}
        for root, f in futs.items():
            r, t = f.result()
            rows.extend(r)
            adv_trades.update({(root,) + k: v for k, v in t.items()})
    overlaps = []
    if adv_trades:
        try:
            crown = crown_days(382)
            for (root, side, filt, ex), tr in sorted(adv_trades.items()):
                overlaps.append(overlap_lines("%s %s %s/%s" % (root, "long" if side == 1 else "short", filt, ex), tr,
                                              INSTR[root]["mult"], crown))
        except BaseException as e:                              # the overlap is information; never lose the triage over it
            overlaps.append("NOISE #382 overlap unavailable: %r" % (e,))
    summary = summarise(rows, adv_trades, overlaps, time.time() - t0)
    write_outputs(rows, summary)
    print(summary)


def overlap_selftest():
    """Dry run of the overlap code path on the best-PF cell (NOT a result of the triage)."""
    root = "NQ"
    a = load_window(root)
    row, tr = run_cell(a, root, 1, dict(BASE, filt="yhigh", exit_mode="ride"))
    ix = pd.DatetimeIndex(a["index"])
    trades = [(str(ix[int(t[0])].date()), int(t[3]), float(t[2])) for t in tr]
    crown = crown_days(382)
    print(overlap_lines("SELFTEST NQ long yhigh/ride", trades, INSTR[root]["mult"], crown))


if __name__ == "__main__":
    if "--overlap-selftest" in sys.argv:
        overlap_selftest()
    else:
        main()
