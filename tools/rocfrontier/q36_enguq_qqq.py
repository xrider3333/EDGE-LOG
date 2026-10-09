"""Q36 ENGU-Q #335 ON REAL QQQ PRINTS UNDER THE WEBULL EXECUTOR (MANAGER #141 item 1) - a REPORT, walk-forward only, per the pre-data note
bookq/PREDATA_Q36_ENGUQ_QQQ.txt. Rows: LEG (ENGU-Q #335 on NQ), B (NQ #335's signals executed on QQQ 1m prints: a signal at a minute QQQ
prints fills at that bar's close, any other at the next QQQ bar's open; held overnight; same-open entry+exit cancel), B-NQ (Q34's executor
leg on NQ prices), A (the paper leg as it runs: #335's settings on the QQQ 1m tape itself, valued through augur_engine.book). All at S
shares = one NQ contract's notional. Power lines BEFORE any lead.
    python q36_enguq_qqq.py selftest   the NQ-minute -> QQQ-fill map on hand-made stamps (no data)
    python q36_enguq_qqq.py run        the report"""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
NOTE = os.path.join(BQ, "PREDATA_Q36_ENGUQ_QQQ.txt")
NOTE_SHA = "7655fbbe8390f599f3435b4a26aab6f9a9cf50508a81b31c962fa0c50dddd1da"
QQQ_SHA = "bdca25959ad8c6113c600b6b0e9dc63660792329359ff88f3f3b79c2bc720545"
Q34_DAILY = r"C:\EdgeLog\_anatomy_cache\q34\q34_daily.csv"
F = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"
OUT = r"C:\EdgeLog\_anatomy_cache\q36"
D0, D1 = "2010-06-07", "2026-06-30"
COST_SH_RT = 0.02                                                   # $ a share a round trip ($0.01 a side, the paper book's)
import numpy as np
import pandas as pd

sys.path.insert(0, BQ)
from q34_enguq_timing import holding_pnl                            # noqa: E402  (selftested in Q34)

lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def qqq_fill(nq_ns, qqq_ns):
    """NQ signal minute stamps (int ns) -> (QQQ bar index, at_open): the QQQ bar with the SAME start stamp fills at its close; otherwise the
    first QQQ bar strictly after the stamp fills at its open. len(qqq) when none is left."""
    pos = np.searchsorted(qqq_ns, nq_ns, side="left")
    same = (pos < len(qqq_ns)) & (qqq_ns[np.minimum(pos, len(qqq_ns) - 1)] == nq_ns)
    return pos, ~same


def selftest():
    q = pd.DatetimeIndex(["2024-01-12 15:58", "2024-01-12 15:59", "2024-01-16 09:30", "2024-01-16 09:31"]).tz_localize("US/Eastern")
    n = pd.DatetimeIndex(["2024-01-12 15:59", "2024-01-12 16:30", "2024-01-15 10:00", "2024-01-16 09:31", "2024-01-16 09:31:30"]).tz_localize("US/Eastern")
    pos, at_open = qqq_fill(n.asi8, q.asi8)
    assert pos.tolist() == [1, 2, 2, 3, 4] and at_open.tolist() == [False, True, True, False, True], (pos, at_open)
    print("selftest PASS (same-minute close fill, overnight / holiday to the next 09:30 open, past the end)")


def run():
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tools"))
    os.chdir(REPO)
    from api.book_shadow import BOOK463_LEGS
    from api.paper import ENGUQ_335
    from augur_engine import book
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import dd5
    from augur_engine.engine import run_backtest
    from power_line import power_line
    import seat_pipeline_final as SP

    qm = find_master("QQQ", "1m", "rth", "alpaca_split_rth")
    qpath = os.path.join(REPO, "augur_uploads", qm["filename"])
    note_sha, q_sha = lf(NOTE), sha(qpath)
    print(f"PINS: note LF {note_sha}; script LF {lf(__file__)}; QQQ 1m master {qm['filename']} sha256 {q_sha}; q34_daily {sha(Q34_DAILY)}; "
          f"line file {SP.LINE_FILE_SHA[:16]}", flush=True)
    if note_sha != NOTE_SHA or q_sha != QQQ_SHA:
        raise SystemExit("refused: the note or the QQQ file is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)
    D = SP.load_pinned_daily(F, SP.LINE_FILE_SHA)
    Bk = SP.window(D["book_mtm"])
    L = SP.window(SP.line_L(D["book_mtm"], D["RES"]))
    SP.check_parity(Bk, "book463")
    SP.check_parity(L, "line_L")
    idx = Bk.index
    YRS = (SP.WF[1] - SP.WF[0]).days / 365.25
    leg = [l for l in BOOK463_LEGS if l["strategy"].startswith("ENGUQ")][0]
    assert dict(leg["params"]) == {k: v for k, v in dict(ENGUQ_335).items() if k in leg["params"]}, "paper ENGUQ_335 != #463's ENGU-Q"

    # S: one NQ contract's notional in QQQ shares (raw NQ / QQQ daily closes, median over the WF)
    nr = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2016-06-01", date_to="2025-06-29")
    qa_all = load_master_arrays(qm, date_from="2016-01-01", date_to=D1)
    nqc = pd.Series(np.asarray(nr["close"], float), index=nr["index"].tz_localize(None).normalize()).groupby(level=0).last()
    qqc = pd.Series(np.asarray(qa_all["close"], float), index=qa_all["index"].tz_localize(None).normalize()).groupby(level=0).last()
    ratio = (nqc / qqc).dropna()
    ratio = ratio[(ratio.index >= SP.WF[0]) & (ratio.index <= SP.WF[1])]
    S = int(round(20.0 * float(ratio.median())))
    print(f"S = {S} QQQ shares per NQ contract (raw NQ / QQQ ratio over the WF: median {ratio.median():.3f}, 1-99% "
          f"{ratio.quantile(0.01):.3f}..{ratio.quantile(0.99):.3f}); QQQ bars {len(qa_all['close']):,}", flush=True)

    # LEG
    tr, inf = book._leg_trades(dict(leg), D0, D1)
    d_, v_ = book._daily(inf.pop("_mtm_day", None) or tr)
    E = pd.Series(v_, index=pd.to_datetime(d_)).groupby(level=0).sum().reindex(idx).fillna(0.0)
    m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
    arr = load_master_arrays(m, date_from=D0, date_to=D1)
    res = run_backtest(leg["strategy"], arrays=arr, params=leg.get("params") or {}, cost_pts=float(leg["cost_pts"]), return_trades=True)
    trades = list(res["trades"])
    assert len(trades) == len(tr)
    nts = arr["index"]
    n = len(nts)
    Aen = np.array([int(t[0]) for t in trades])
    Aex = np.array([min(int(t[1]), n - 1) for t in trades])
    wf_tr = np.asarray((nts[Aen].tz_localize(None).normalize() >= SP.WF[0]) & (nts[Aen].tz_localize(None).normalize() <= SP.WF[1]))

    # B: NQ's signals executed on QQQ prints
    qts = qa_all["index"]
    qn = len(qts)
    qc, qo = np.asarray(qa_all["close"], float), np.asarray(qa_all["open"], float)
    ke, eo = qqq_fill(nts[Aen].asi8, qts.asi8)
    kx, xo = qqq_fill(nts[Aex].asi8, qts.asi8)
    fills = []
    for k, ko, mm, mo in zip(ke, eo, kx, xo):
        k, ko = (qn - 1, False) if k >= qn else (int(k), bool(ko))
        mm, mo = (qn - 1, False) if mm >= qn else (int(mm), bool(mo))
        fills.append((float(S), k, ko, mm, mo))
    bp, done = holding_pnl(qc, qo, fills)
    qday = pd.DatetimeIndex(np.asarray(qts, dtype="datetime64[D]"))            # the book's UTC day (RTH bars: = the ET date)
    codes = idx.get_indexer(qday)
    keep = codes >= 0
    xb = np.array([f[3] for f in fills])
    Bq = pd.Series(np.bincount(codes[keep], weights=bp[keep], minlength=len(idx)), index=idx)
    cc = codes[xb[done]]
    Bq = Bq - pd.Series(np.bincount(cc[cc >= 0], minlength=len(idx)) * COST_SH_RT * S, index=idx)
    print(f"B: WF trades {int(wf_tr.sum())}; entries filled at a QQQ close {int((~eo & wf_tr).sum())}, at the next open {int((eo & wf_tr).sum())}; "
          f"cancelled (same open) {int((~done & wf_tr).sum())}", flush=True)
    q34 = pd.read_csv(Q34_DAILY, index_col=0, parse_dates=True)
    BNQ = q34["exec leg"].reindex(idx).fillna(0.0)

    # A: the paper leg as it runs, on the QQQ tape
    qleg = {"strategy": leg["strategy"], "instrument": "QQQ", "timeframe": "1m", "session": "rth", "source": "alpaca_split_rth",
            "cost_pts": COST_SH_RT, "mult": float(S), "weight": 1, "params": dict(leg["params"])}
    tra, infa = book._leg_trades(dict(qleg), "2016-01-01", D1)
    da, va = book._daily(infa.pop("_mtm_day", None) or tra)
    Aq = pd.Series(va, index=pd.to_datetime(da)).groupby(level=0).sum().reindex(idx).fillna(0.0)
    ra = run_backtest(leg["strategy"], arrays=qa_all, params=dict(leg["params"]), cost_pts=COST_SH_RT, return_trades=True)
    at = list(ra["trades"])
    a_days = pd.DatetimeIndex([qts[int(t[0])].tz_localize(None).normalize() for t in at])
    a_wf = (a_days >= SP.WF[0]) & (a_days <= SP.WF[1])
    nq_days = set(nts[Aen[wf_tr]].tz_localize(None).normalize())
    print(f"A: WF trades {int(a_wf.sum())} (NQ leg {int(wf_tr.sum())}); A's WF entries on a session where NQ #335 also entered: "
          f"{int(sum(d in nq_days for d in a_days[a_wf]))}", flush=True)

    # ---- power first
    PL = {}
    for nm, a, b in (("leg vs B (QQQ executor)", E, Bq), ("leg vs A (paper leg as it runs)", E, Aq), ("A vs B", Aq, Bq)):
        PL[nm] = power_line(a.to_numpy(float), b.to_numpy(float), YRS)
        print(f"POWER LINE {nm}: SD {PL[nm]['sd']:.2f}; 50% line {PL[nm]['line_5pct']:.2f}; 80% line {PL[nm]['line_80pct']:.2f} ROC points", flush=True)
    mL, sL = SP.episodes(L)

    def row(name, s):
        f = SP.figures(s)
        tot, wo, _ = SP.dollars_on(s, mL, sL)
        return {"line": name, "roc30": f["roc30"], "sortino": f["sortino"], "dd": f["dd"], "dd5": f["dd5"], "one_episode": f["one_episode"],
                "usd_year": f["net_per_year"], "on_R": tot}

    Sx = {"leg": E, "B": Bq, "B-NQ": BNQ, "A": Aq}
    rows = [row("ENGU-Q #335 on NQ (the leg)", E), row("B: NQ signals executed on QQQ", Bq), row("B-NQ: the same executor on NQ prices (Q34)", BNQ),
            row("A: the paper leg as it runs (QQQ tape)", Aq), row("L (ENGU-Q in)", L)] + \
           [row(f"L - ENGU-Q + {k}", L - E + v) for k, v in Sx.items() if k != "leg"] + [row("L without ENGU-Q", L - E)]
    for r in rows:
        print(f"  {r['line']:<46} ROC@30k {r['roc30']:7.2f}  DD5 ${r['dd5']:>8,.0f}{' (ONE EPISODE)' if r['one_episode'] else '              '}  "
              f"Sortino {r['sortino']:.3f}  worst ${r['dd']:>8,.0f}  ${r['usd_year']:>9,.0f}/yr", flush=True)
    fig = {k: SP.figures(v) for k, v in Sx.items()}
    reads = []
    for k, pl in (("B", "leg vs B (QQQ executor)"), ("A", "leg vs A (paper leg as it runs)")):
        d = fig["leg"]["roc30"] - fig[k]["roc30"]
        keeps = fig[k]["net_per_year"] / fig["leg"]["net_per_year"]
        line = PL[pl]["line_5pct"]
        w = "not distinguishable at this resolution" if abs(d) < line else ("the QQQ executor costs the leg" if d > 0 else "beats the leg")
        reads.append(f"{k} keeps {100 * keeps:.0f}% of the leg's $ a year at the same notional; ROC {fig[k]['roc30']:.2f} vs {fig['leg']['roc30']:.2f} "
                     f"({-d:+.2f} against a line of {line:.2f}): {w}")
    dab = fig["A"]["roc30"] - fig["B"]["roc30"]
    reads.append(f"A vs B: {dab:+.2f} ROC points against a line of {PL['A vs B']['line_5pct']:.2f}; QQQ price effect alone (B minus B-NQ) "
                 f"{fig['B']['roc30'] - fig['B-NQ']['roc30']:+.2f} points, ${fig['B']['net_per_year'] - fig['B-NQ']['net_per_year']:,.0f} a year")
    for r in reads:
        print("READ (pre-set wording):", r)
    yrs = np.where(idx.month >= 7, idx.year, idx.year - 1)
    for nm, x in (("leg minus B", E - Bq), ("leg minus A", E - Aq), ("B minus B-NQ", Bq - BNQ)):
        by = x.groupby(yrs).sum()
        print(f"{nm} by July-June year: " + ", ".join(f"{int(k)} ${v:,.0f}" for k, v in by.items()) + f"; positive in {int((by > 0).sum())} of {len(by)}")
    EP = {k: dd5(v)["episodes"] for k, v in Sx.items()}
    for k, v in EP.items():
        print(f"  worst 5 episodes, {k}: " + "; ".join(f"{e['peak']}->{e['trough']} ${e['depth']:,.0f}" for e in v), flush=True)
    pd.DataFrame(Sx).to_csv(os.path.join(OUT, "q36_daily.csv"))
    json.dump({"note_sha256_lf": note_sha, "qqq_sha256": q_sha, "S": S, "power": PL, "rows": rows, "reads": reads, "episodes": EP},
              open(os.path.join(OUT, "q36_enguq_qqq.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q36_enguq_qqq.json"))


if __name__ == "__main__":
    {"selftest": selftest, "run": run}[sys.argv[1] if len(sys.argv) > 1 else "selftest"]()
