"""Q34 ENGU-Q TIMING SPLIT (MANAGER #139 item 2) - a REPORT, walk-forward only, per the pre-data note bookq/PREDATA_Q34_ENGUQ_TIMING.txt
(LF sha256 f129c9ed...). Valuation exactly as Q31 (bookq/q31_drifttwin.py): NQ 1m ETH back-adjusted master, book UTC day stamps, $20 a point,
1.0 NQ while on; the always-on twin at the leg's time-average position (0.605) with the audited roll table's costs.
  PART A  always-on twin -> ENTRY-ONLY twin (the leg's entry bars, durations shuffled among its WF trades, cut at the next entry; 200 shuffles,
          seed 20261009, mean daily $) = ENTRY timing -> IN-POSITION twin (the real exits, at bar closes) = STOP-EXIT timing -> the leg = fills
  PART B  the same chain for an RTH-only executor that may hold overnight: a signal at a bar inside RTH (a regular session's 09:30-15:59 ET
          bars) fills at that bar's close; any other signal (overnight / pre-market / a CME-holiday session) fills at the OPEN of the next
          regular session's first RTH bar. An entry and exit that both land on the same open cancel (no trade, no cost).
Power lines BEFORE any lead (tools/power_line.py). 'Survives' = the executor keeps at least half of a component's $ a year.
    python q34_enguq_timing.py selftest   hand-made bars: the fills, the cancel, the shuffle's cut, the RTH map - no data
    python q34_enguq_timing.py run        the report
Bars are start-stamped (the 1m master's last bar before the CME break is 16:59, the first after it 18:00; RTH 5m runs 09:30-15:55)."""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
NOTE = os.path.join(BQ, "PREDATA_Q34_ENGUQ_TIMING.txt")
NOTE_SHA = "f129c9ed3a248268e7a912c6a54bbd6eb72d99a942ad4a94b2b4179fa7ea26b1"
ROLLS_SHA = "1cfe7b592e51ae0adc4fa1aa59951c1c20e097496e5799c762ab8a6483eae204"
F = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"
OUT = r"C:\EdgeLog\_anatomy_cache\q34"
D0, D1 = "2010-06-07", "2026-06-30"
N_SHUFFLES, SEED = 200, 20261009
RTH_LO, RTH_HI = 9 * 60 + 30, 15 * 60 + 59                         # first / last RTH 1m bar start, ET minutes
import numpy as np
import pandas as pd

lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------ pure pieces (selftested)
def holding_pnl(close, open_, fills):
    """fills = [(side, k, k_at_open, m, m_at_open)] -> (bar P&L in points, executed flags). A close entry at bar k earns bars k+1..; an open
    entry at k earns bar k from its open; a close exit at m earns through bar m; an open exit at m earns bar m up to its open. An open entry
    and an open exit on the same bar cancel."""
    n = len(close)
    dclose = np.zeros(n)
    dclose[1:] = np.diff(close)
    hold, adj, done = np.zeros(n + 1), np.zeros(n), []
    for side, k, ko, m, mo in fills:
        if ko and mo and m == k:
            done.append(False)
            continue
        s, e = (k if ko else k + 1), (m - 1 if mo else m)
        if e >= s:
            hold[s] += side
            hold[e + 1] -= side
        if ko:
            adj[k] -= side * (open_[k] - close[k - 1])
        if mo:
            adj[m] += side * (open_[m] - close[m - 1])
        done.append(True)
    return np.cumsum(hold[:n]) * dclose + adj, np.array(done, bool)


def rth_map(et_index, regular_dates):
    """et_index = the bars' ET timestamps (start-stamped), regular_dates = the regular sessions -> (in_rth bool per bar, nxt = the index of the
    next regular session's first RTH bar strictly after each bar, len(bars) if none)"""
    d = et_index.tz_localize(None).normalize() if et_index.tz is not None else et_index.normalize()
    hm = et_index.hour * 60 + et_index.minute
    in_rth = np.asarray(d.isin(regular_dates) & (hm >= RTH_LO) & (hm <= RTH_HI))
    prev = np.r_[False, in_rth[:-1]]
    newday = np.r_[True, np.asarray(d[1:] != d[:-1])]
    first = np.flatnonzero(in_rth & (~prev | newday))
    pos = np.searchsorted(first, np.arange(len(in_rth)), side="right")
    nxt = np.where(pos < len(first), first[np.minimum(pos, len(first) - 1)], len(in_rth))
    return in_rth, nxt


def executor_fills(entries, exits, in_rth, nxt, n, side=1):
    """signal bars -> executor fills (side, k, k_at_open, m, m_at_open); a fill past the data end is clipped to the last bar's close"""
    out = []
    for a, b in zip(entries, exits):
        k, ko = (a, False) if in_rth[a] else (nxt[a], True)
        m, mo = (b, False) if in_rth[b] else (nxt[b], True)
        if k >= n:
            k, ko = n - 1, False
        if m >= n:
            m, mo = n - 1, False
        out.append((side, int(k), ko, int(m), mo))
    return out


def shuffled_exits(entries, exits, shuffle_mask, rng, n):
    """the entry-only twin's exits: durations (exit - entry, in bars) permuted among the trades in `shuffle_mask`, each cut at the next entry"""
    entries, exits = np.asarray(entries), np.asarray(exits)
    dur = exits - entries
    d2 = dur.copy()
    ix = np.flatnonzero(shuffle_mask)
    d2[ix] = dur[ix][rng.permutation(len(ix))]
    nxt_entry = np.r_[entries[1:], n - 1]
    return np.minimum(np.minimum(entries + d2, nxt_entry), n - 1)


def selftest():
    close = np.array([100, 101, 103, 102, 105, 107], float)
    open_ = np.array([100, 100.5, 102, 103.5, 104, 106], float)
    p, ok = holding_pnl(close, open_, [(1, 1, False, 4, False)])
    assert np.allclose(p, [0, 0, 2, -1, 3, 0]) and ok.all(), p
    p, ok = holding_pnl(close, open_, [(1, 2, True, 4, True)])
    assert np.isclose(p.sum(), open_[4] - open_[2]) and np.allclose(p, [0, 0, 1, -1, 2, 0]), p
    p, ok = holding_pnl(close, open_, [(1, 3, True, 3, True)])
    assert not ok.any() and np.allclose(p, 0), "an open entry and exit on the same bar cancel"
    p, ok = holding_pnl(close, open_, [(1, 2, True, 2, False)])
    assert np.isclose(p.sum(), close[2] - open_[2])
    p, ok = holding_pnl(close, open_, [(1, 1, False, 3, True), (1, 3, True, 5, False)])
    assert np.isclose(p.sum(), close[5] - close[1]), "exit and re-entry on the same open = held straight through"
    ts = pd.DatetimeIndex(["2024-01-12 15:58", "2024-01-12 15:59", "2024-01-12 16:00", "2024-01-14 18:00", "2024-01-15 09:30",
                           "2024-01-15 10:00", "2024-01-16 08:00", "2024-01-16 09:30", "2024-01-16 16:30"]).tz_localize("US/Eastern")
    regular = pd.DatetimeIndex(["2024-01-12", "2024-01-16"])                           # 01-15 = a CME-holiday session (MLK day)
    rth, nxt = rth_map(ts, regular)
    assert rth.tolist() == [True, True, False, False, False, False, False, True, False], rth
    assert nxt.tolist() == [7, 7, 7, 7, 7, 7, 7, 9, 9], nxt
    f = executor_fills([2, 0], [7, 8], rth, nxt, len(ts))
    assert f == [(1, 7, True, 7, False), (1, 0, False, 8, False)], f
    f = executor_fills([3], [6], rth, nxt, len(ts))
    assert f == [(1, 7, True, 7, True)], "both signals before the 01-16 open land on the same open: cancel"
    rng = np.random.default_rng(1)
    e = shuffled_exits([0, 10, 12, 30], [5, 11, 20, 40], np.array([True, True, True, False]), rng, 50)
    assert (e <= np.r_[10, 12, 30, 49]).all() and e[3] == 40, e
    print("selftest PASS (fills, cancel, straight-through, RTH map with a holiday session, executor fills, the shuffle's cut)")


# ------------------------------------------------------------------ the report
def run():
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tools"))
    os.chdir(REPO)
    from api.book_shadow import BOOK463_LEGS
    from augur_engine import book
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import dd5
    from augur_engine.engine import run_backtest
    from power_line import power_line
    sys.path.insert(0, BQ)
    import seat_pipeline_final as SP

    rolls = os.path.join(REPO, "tools", "data", "rolls_NQ.csv")
    note_sha, rolls_sha = lf(NOTE), lf(rolls)
    print(f"PINS: pre-data note LF sha256 {note_sha}; script sha256 {hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}; "
          f"script LF sha256 {lf(__file__)}; rolls_NQ {rolls_sha}; line file {SP.LINE_FILE_SHA[:16]}", flush=True)
    if note_sha != NOTE_SHA or rolls_sha != ROLLS_SHA:
        raise SystemExit("refused: the note or the roll table is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)

    D = SP.load_pinned_daily(F, SP.LINE_FILE_SHA)
    B = SP.window(D["book_mtm"])
    L = SP.window(SP.line_L(D["book_mtm"], D["RES"]))
    SP.check_parity(B, "book463")
    SP.check_parity(L, "line_L")
    idx = B.index
    YRS = (SP.WF[1] - SP.WF[0]).days / 365.25
    leg = [l for l in BOOK463_LEGS if l["strategy"].startswith("ENGUQ")][0]
    COST_RT = float(leg["cost_pts"]) * 20.0
    tr, inf = book._leg_trades(dict(leg), D0, D1)
    d_, v_ = book._daily(inf.pop("_mtm_day", None) or tr)
    E = pd.Series(v_, index=pd.to_datetime(d_)).groupby(level=0).sum().reindex(idx).fillna(0.0)

    m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
    arr = load_master_arrays(m, date_from=D0, date_to=D1)
    res = run_backtest(leg["strategy"], arrays=arr, params=leg.get("params") or {}, cost_pts=float(leg["cost_pts"]), return_trades=True)
    trades = list(res["trades"])
    assert len(trades) == len(tr), (len(trades), len(tr))
    assert all(int(t[3]) == 1 for t in trades), "ENGU-Q is long-only"
    et = arr["index"]
    bd = pd.DatetimeIndex(np.asarray(et, dtype="datetime64[D]"))      # the book's UTC day stamp
    n = len(bd)
    close, open_ = np.asarray(arr["close"], float), np.asarray(arr["open"], float)
    A = np.array([int(t[0]) for t in trades])
    Bx = np.array([min(int(t[1]), n - 1) for t in trades])
    assert (Bx[:-1] <= A[1:]).all(), "the leg's trades overlap - look first"
    codes = idx.get_indexer(bd)
    keep = codes >= 0

    def daily(bar_pts, exit_bars, done):
        x = np.bincount(codes[keep], weights=bar_pts[keep] * 20.0, minlength=len(idx))
        c = np.bincount(codes[exit_bars[done]][codes[exit_bars[done]] >= 0], minlength=len(idx)) * COST_RT
        return pd.Series(x - c, index=idx)

    # Q31's in-position twin and W, rebuilt here as the parity check
    pos = np.zeros(n)
    for a, b in zip(A, Bx):
        pos[a:b] += 1
    wfb = np.asarray((bd >= SP.WF[0]) & (bd <= SP.WF[1]))
    W = float(pos[wfb].mean())
    assert abs(W - 0.605) < 0.0005, "W moved from Q31's 0.605 - look first"
    ip_pts, ip_done = holding_pnl(close, open_, [(1, a, False, b, False) for a, b in zip(A, Bx)])
    q31_bar = np.zeros(n)
    q31_bar[1:] = pos[:-1] * np.diff(close)
    assert np.allclose(ip_pts, q31_bar), "the fill engine does not reproduce Q31's in-position twin"
    IP = daily(ip_pts, Bx, ip_done)
    rt = pd.read_csv(rolls)
    roll_days = pd.DatetimeIndex(pd.to_datetime(rt["switch_sec"], unit="s", utc=True).dt.tz_localize(None).dt.normalize())
    dc = pd.Series(close, index=bd).groupby(level=0).last().diff()
    AO = (W * 20.0 * dc).reindex(idx).fillna(0.0)
    AO[AO.index.isin(roll_days)] -= W * COST_RT
    AO.iloc[0] = AO.iloc[0] - W * COST_RT
    wf_tr = np.asarray((bd[A] >= SP.WF[0]) & (bd[A] <= SP.WF[1]))
    print(f"ENGU-Q: {len(trades)} trades ({int(wf_tr.sum())} entered on the WF); W = {W:.4f}; in-position twin = Q31's (asserted)", flush=True)

    # the RTH executor's map: regular sessions = the NQ 5m RTH master's sessions less CME-holiday sessions (09:30 .. a last bar of 12:55/13:00)
    rm = find_master("NQ", "5m", "rth", "db_adj_rth")
    rarr = load_master_arrays(rm, date_from=D0, date_to=D1)
    rix = rarr["index"]
    g = pd.DataFrame({"day": rix.tz_localize(None).normalize(), "hm": rix.hour * 60 + rix.minute}).groupby("day")["hm"]
    first, last, cnt = g.min(), g.max(), g.nunique()
    hol = first.index[((first == 570) & last.isin([775, 780]) & (cnt == (last - 570) // 5 + 1)).to_numpy()]
    regular = first.index.difference(hol)
    assert regular[0] <= pd.Timestamp("2016-06-01"), "the RTH master starts after the WF - look first"
    in_rth, nxt = rth_map(et, regular)
    fx = executor_fills(A, Bx, in_rth, nxt, n)
    ipx_pts, ipx_done = holding_pnl(close, open_, fx)
    IPX = daily(ipx_pts, np.array([f[3] for f in fx]), ipx_done)
    ent_out, ex_out = ~in_rth[A], ~in_rth[Bx]
    print(f"regular sessions {len(regular):,} ({len(hol)} CME-holiday sessions out); WF trades: entries signalled outside RTH "
          f"{int((ent_out & wf_tr).sum())} of {int(wf_tr.sum())}, exits outside RTH {int((ex_out & wf_tr).sum())}; "
          f"trades that cancel under the executor {int((~ipx_done & wf_tr).sum())}", flush=True)

    # the entry-only twins (Part A and the executor's), mean over the shuffles
    rng = np.random.default_rng(SEED)
    eo_sum, eox_sum = np.zeros(len(idx)), np.zeros(len(idx))
    for k in range(N_SHUFFLES):
        b2 = shuffled_exits(A, Bx, wf_tr, rng, n)
        p, dn = holding_pnl(close, open_, [(1, a, False, b, False) for a, b in zip(A, b2)])
        eo_sum += daily(p, b2, dn).to_numpy()
        f2 = executor_fills(A, b2, in_rth, nxt, n)
        p, dn = holding_pnl(close, open_, f2)
        eox_sum += daily(p, np.array([f[3] for f in f2]), dn).to_numpy()
    EO = pd.Series(eo_sum / N_SHUFFLES, index=idx)
    EOX = pd.Series(eox_sum / N_SHUFFLES, index=idx)

    # ---- power first
    PL = {}
    for nm, a, b in (("leg vs RTH executor (pre-set)", E, IPX), ("entry-only vs in-position = EXIT (pre-set)", IP, EO),
                     ("always-on vs entry-only = ENTRY (added, disclosure)", EO, AO), ("in-position vs RTH executor = the delay (added)", IP, IPX),
                     ("RTH executor: entry-only vs in-position = EXIT under the executor (added)", IPX, EOX)):
        PL[nm] = power_line(a.to_numpy(float), b.to_numpy(float), YRS)
        print(f"POWER LINE {nm}: SD {PL[nm]['sd']:.2f}; 50% line {PL[nm]['line_5pct']:.2f}; 80% line {PL[nm]['line_80pct']:.2f} ROC points", flush=True)

    mL, sL = SP.episodes(L)

    def row(name, s):
        f = SP.figures(s)
        tot, wo, _ = SP.dollars_on(s, mL, sL)
        return {"line": name, "roc30": f["roc30"], "sortino": f["sortino"], "dd": f["dd"], "dd5": f["dd5"], "one_episode": f["one_episode"],
                "usd_year": f["net_per_year"], "on_R": tot, "on_R_without_best": wo}

    S = {"always-on": AO, "entry-only": EO, "in-position": IP, "leg": E, "exec entry-only": EOX, "exec leg": IPX}
    rows = [row(f"always-on twin {W:.3f} NQ", AO), row("entry-only twin (shuffled holds, mean of 200)", EO),
            row("in-position twin (the real exits at bar closes)", IP), row("ENGU-Q (the leg)", E),
            row("RTH executor: entry-only twin", EOX), row("RTH executor: the leg (delayed fills, overnight holds)", IPX),
            row("L (ENGU-Q in)", L)] + [row(f"L - ENGU-Q + {k}", L - E + v) for k, v in S.items() if k != "leg"] + [row("L without ENGU-Q", L - E)]
    for r in rows:
        print(f"  {r['line']:<58} ROC@30k {r['roc30']:7.2f}  DD5 ${r['dd5']:>8,.0f}{' (ONE EPISODE)' if r['one_episode'] else '              '}  "
              f"Sortino {r['sortino']:.3f}  worst ${r['dd']:>8,.0f}  ${r['usd_year']:>9,.0f}/yr  on R ${r['on_R']:>9,.0f}", flush=True)
    R = {r["line"]: r for r in rows}
    roc = {k: SP.figures(v)["roc30"] for k, v in S.items()}
    usd = {k: SP.figures(v)["net_per_year"] for k, v in S.items()}
    lead = roc["leg"] - roc["always-on"]
    comp = {"ENTRY timing": ("always-on", "entry-only", "exec entry-only", "always-on"),
            "STOP-EXIT timing": ("entry-only", "in-position", "exec leg", "exec entry-only")}
    reads = {}
    for nm, (a, b, bx, ax) in comp.items():
        pts, dol, ptsx, dolx = roc[b] - roc[a], usd[b] - usd[a], roc[bx] - roc[ax], usd[bx] - usd[ax]
        keeps = dolx / dol if dol > 0 else None
        surv = None if dol <= 0 else bool(dolx >= 0.5 * dol)
        reads[nm] = {"roc_pts": pts, "share_of_lead": pts / lead if lead else None, "usd_year": dol, "exec_roc_pts": ptsx, "exec_usd_year": dolx,
                     "exec_keeps": keeps, "survives": surv}
        print(f"{nm}: {pts:+.2f} ROC points ({(100 * pts / lead) if lead else float('nan'):.0f}% of the leg's {lead:+.2f}-point lead over always-on), "
              f"${dol:,.0f} a year; under the RTH executor {ptsx:+.2f} points, ${dolx:,.0f} a year -> "
              + ("nothing to survive (the component is not positive)" if surv is None else
                 f"{'SURVIVES' if surv else 'DOES NOT SURVIVE'} (keeps {100 * keeps:.0f}% of its $)"), flush=True)
    fills_pts, fills_usd = roc["leg"] - roc["in-position"], usd["leg"] - usd["in-position"]
    print(f"fills (the leg vs its in-position twin): {fills_pts:+.2f} ROC points, ${fills_usd:,.0f} a year", flush=True)
    d_lx = roc["leg"] - roc["exec leg"]
    line_lx = PL["leg vs RTH executor (pre-set)"]["line_5pct"]
    d_exit = roc["in-position"] - roc["entry-only"]
    line_exit = PL["entry-only vs in-position = EXIT (pre-set)"]["line_5pct"]
    v1 = (f"leg vs RTH executor: {d_lx:+.2f} ROC points against a line of {line_lx:.2f} - "
          + ("not distinguishable at this resolution" if abs(d_lx) < line_lx else ("the executor costs the leg" if d_lx > 0 else "the executor beats the leg")))
    v2 = (f"STOP-EXIT timing (in-position vs entry-only): {d_exit:+.2f} ROC points against a line of {line_exit:.2f} - "
          + ("not distinguishable at this resolution" if abs(d_exit) < line_exit else ("the exits add" if d_exit > 0 else "the exits subtract")))
    print("READ (pre-set wording):", v1, "|", v2)
    EP = {k: dd5(v)["episodes"] for k, v in (("leg", E), ("exec leg", IPX), ("L", L), ("L with the exec leg", L - E + IPX))}
    for k, v in EP.items():
        print(f"  worst 5 episodes, {k}: " + "; ".join(f"{e['peak']}->{e['trough']} ${e['depth']:,.0f}" for e in v), flush=True)
    yrs = np.where(idx.month >= 7, idx.year, idx.year - 1)
    for nm, x in (("leg minus RTH executor", E - IPX), ("in-position minus entry-only", IP - EO), ("entry-only minus always-on", EO - AO)):
        by = x.groupby(yrs).sum()
        print(f"{nm} by July-June year: " + ", ".join(f"{int(k)} ${v:,.0f}" for k, v in by.items()) + f"; positive in {int((by > 0).sum())} of {len(by)}")
    pd.DataFrame(S).to_csv(os.path.join(OUT, "q34_daily.csv"))
    json.dump({"note_sha256_lf": note_sha, "W": W, "power": PL, "rows": rows, "components": reads, "fills": {"roc_pts": fills_pts, "usd_year": fills_usd},
               "lead_over_always_on": lead, "verdict": [v1, v2], "episodes": EP,
               "counts": {"wf_trades": int(wf_tr.sum()), "entries_outside_rth": int((ent_out & wf_tr).sum()), "exits_outside_rth": int((ex_out & wf_tr).sum()),
                          "cancelled": int((~ipx_done & wf_tr).sum()), "regular_sessions": int(len(regular)), "holiday_sessions": int(len(hol))}},
              open(os.path.join(OUT, "q34_enguq_timing.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q34_enguq_timing.json"))


if __name__ == "__main__":
    {"selftest": selftest, "run": run}[sys.argv[1] if len(sys.argv) > 1 else "selftest"]()
