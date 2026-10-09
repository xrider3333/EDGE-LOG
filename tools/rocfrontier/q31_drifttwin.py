"""Q31 DRIFT TWIN for ENGU-Q (MANAGER #128 item 2; Huang, Li, Wang & Zhou 2020) - a REPORT, walk-forward only, per the pre-data note v2
(bookq/PREDATA_Q31_DRIFTTWIN_ENGUQ.txt; MANAGER #130, ENGUQ #131 / #132 folded). Rows: the leg; the ALWAYS-ON twin (constant W = the leg's
time-average position on the WF bars, asserted 0.605); the IN-POSITION twin (1.0 NQ on exactly the bars the leg holds); the beta twin 0.443
(disclosure). All valued like the leg's daily curve (NQ 1m ETH back-adjusted master, book UTC day stamps, $20 a point); rolls from
tools/data/rolls_NQ.csv; net and gross of costs; power lines BEFORE any lead; worst-5 episode tables."""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
os.chdir(REPO)
import numpy as np
import pandas as pd
from api.book_shadow import BOOK463_LEGS
from augur_engine import book
from augur_engine.data import find_master, load_master_arrays
from augur_engine.drawdowns import dd5
from augur_engine.engine import run_backtest
from power_line import power_line

BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
sys.path.insert(0, BQ)
import seat_pipeline_final as SP

NOTE = os.path.join(BQ, "PREDATA_Q31_DRIFTTWIN_ENGUQ.txt")
NOTE_SHA = "06c3f4fc0b00af4928dbde48bd054f71b7801d7949f1674d47c7c82c2aa9b385"
ROLLS = os.path.join(REPO, "tools", "data", "rolls_NQ.csv")
ROLLS_SHA = "1cfe7b592e51ae0adc4fa1aa59951c1c20e097496e5799c762ab8a6483eae204"
F = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"
OUT = r"C:\EdgeLog\_anatomy_cache\q31"
W_BETA = 0.443                                                     # ENGUQ's ETH-marked beta (disclosure only)
D0, D1 = "2010-06-07", "2026-06-30"
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
os.makedirs(OUT, exist_ok=True)
note_sha, rolls_sha = lf(NOTE), lf(ROLLS)
print(f"PINS: pre-data note LF sha256 {note_sha}; script sha256 {hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}; rolls_NQ {rolls_sha}; "
      f"line file {SP.LINE_FILE_SHA[:16]}", flush=True)
if note_sha != NOTE_SHA or rolls_sha != ROLLS_SHA:
    raise SystemExit("refused: the note or the roll table is not the frozen one (nothing computed)")

D = SP.load_pinned_daily(F, SP.LINE_FILE_SHA)
B = SP.window(D["book_mtm"])
L = SP.window(SP.line_L(D["book_mtm"], D["RES"]))
SP.check_parity(B, "book463")
SP.check_parity(L, "line_L")
idx = B.index
YRS = (SP.WF[1] - SP.WF[0]).days / 365.25
leg = [l for l in BOOK463_LEGS if l["strategy"].startswith("ENGUQ")][0]
COST_RT = float(leg["cost_pts"]) * 20.0                           # the leg's round trip, $ a contract
tr, inf = book._leg_trades(dict(leg), D0, D1)
d_, v_ = book._daily(inf.pop("_mtm_day", None) or tr)
E = pd.Series(v_, index=pd.to_datetime(d_)).groupby(level=0).sum().reindex(idx).fillna(0.0)

m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
arr = load_master_arrays(m, date_from=D0, date_to=D1)
res = run_backtest(leg["strategy"], arrays=arr, params=leg.get("params") or {}, cost_pts=float(leg["cost_pts"]), return_trades=True)
trades = list(res["trades"])
assert len(trades) == len(tr), (len(trades), len(tr))
days_idx = np.asarray(arr["index"], dtype="datetime64[D]")         # the book's UTC day stamp (augur_engine.book's convention)
bd = pd.DatetimeIndex(days_idx)
n = len(bd)
close = np.asarray(arr["close"], float)
pos = np.zeros(n)
exit_day = []
for t in trades:
    a, b = int(t[0]), min(int(t[1]), n - 1)
    pos[a:b] += int(t[3])                                          # held at the closes of bars a .. b-1
    exit_day.append(bd[b])
wfb = np.asarray((bd >= SP.WF[0]) & (bd <= SP.WF[1]))
W = float(pos[wfb].mean())
print(f"ENGU-Q: {len(trades)} trades, all long: {all(int(t[3]) == 1 for t in trades)}; time-average position on the WF bars W = {W:.4f}", flush=True)
assert abs(W - 0.605) < 0.0005, "W moved from the note's 0.605 - look first"
cost_leg = pd.Series(COST_RT, index=pd.DatetimeIndex(exit_day)).groupby(level=0).sum().reindex(idx).fillna(0.0)
n_wf_trades = int(sum(1 for x in exit_day if SP.WF[0] <= x <= SP.WF[1]))

# rolls: the audited table's switch times, on the book UTC day
rt = pd.read_csv(ROLLS)
roll_days = pd.DatetimeIndex(pd.to_datetime(rt["switch_sec"], unit="s", utc=True).dt.tz_localize(None).dt.normalize())
wf_rolls = int(((roll_days >= SP.WF[0]) & (roll_days <= SP.WF[1])).sum())
lastc = pd.Series(close, index=bd).groupby(level=0).last()
dc = lastc.diff()


def always_on(w, gross=False):
    x = (w * 20.0 * dc).reindex(idx).fillna(0.0)
    if not gross:
        x[x.index.isin(roll_days)] -= w * COST_RT
        x.iloc[0] = x.iloc[0] - w * COST_RT                            # the entry (and its eventual exit)
    return x


bar = np.zeros(n)
bar[1:] = pos[:-1] * np.diff(close) * 20.0                         # bar i's move earned by the position held at bar i-1's close
inpos_gross = pd.Series(bar, index=bd).groupby(level=0).sum().reindex(idx).fillna(0.0)
inpos = inpos_gross - cost_leg
E_gross = E + cost_leg
T2, T2g, T4 = always_on(W), always_on(W, True), always_on(W_BETA)
print(f"twin rows: W {W:.4f} NQ always-on ({wf_rolls} rolls on the WF, table {len(rt)} switches); in-position 1.0 NQ on the leg's bars "
      f"({n_wf_trades} WF round trips); beta twin {W_BETA}", flush=True)

# ---- power first: the minimum detectable leads, before any lead is printed
PL = {}
for nm, a, b in (("L vs L' (always-on twin in ENGU-Q's place)", L, L - E + T2), ("leg vs always-on twin", E, T2), ("leg vs in-position twin", E, inpos)):
    PL[nm] = power_line(a.to_numpy(float), b.to_numpy(float), YRS)
    print(f"POWER LINE {nm}: SD {PL[nm]['sd']:.2f}; 50% line {PL[nm]['line_5pct']:.2f}; 80% line {PL[nm]['line_80pct']:.2f} ROC points", flush=True)

mL, sL = SP.episodes(L)
m463, s463 = SP.episodes(B)


def row(name, s, mask=mL, spans=sL):
    f = SP.figures(s)
    tot, wo, _ = SP.dollars_on(s, mask, spans)
    return {"line": name, "roc30": f["roc30"], "sortino": f["sortino"], "dd": f["dd"], "dd5": f["dd5"], "one_episode": f["one_episode"],
            "usd_year": f["net_per_year"], "on_R": tot, "on_R_without_best": wo}


rows = [row("1 ENGU-Q (the leg), net", E), row("1 ENGU-Q, gross of costs", E_gross),
        row(f"2 always-on twin {W:.3f} NQ, net", T2), row("2 always-on twin, gross", T2g),
        row("3 in-position twin (1.0 NQ on the leg's bars), net", inpos), row("3 in-position twin, gross", inpos_gross),
        row(f"4 beta twin {W_BETA} NQ (disclosure), net", T4),
        row("L (ENGU-Q in)", L), row("L' = L - ENGU-Q + always-on twin", L - E + T2), row("L'' = L - ENGU-Q + in-position twin", L - E + inpos),
        row("L without ENGU-Q (A3)", L - E),
        row("#463", B, m463, s463), row("#463 - ENGU-Q + always-on twin", B - E + T2, m463, s463), row("#463 without ENGU-Q", B - E, m463, s463)]
for r in rows:
    print(f"  {r['line']:<52} ROC@30k {r['roc30']:7.2f}  DD5 ${r['dd5']:>8,.0f}{' (ONE EPISODE)' if r['one_episode'] else '              '}  Sortino {r['sortino']:.3f}  "
          f"worst ${r['dd']:>8,.0f}  ${r['usd_year']:>9,.0f}/yr  on R ${r['on_R']:>9,.0f} (w/o best ${r['on_R_without_best']:>9,.0f})", flush=True)
EP = {}
for nm, s in (("leg", E), ("always-on twin", T2), ("in-position twin", inpos), ("L", L), ("L'", L - E + T2)):
    EP[nm] = dd5(s)["episodes"]
    print(f"  worst 5 episodes, {nm}: " + "; ".join(f"{e['peak']}->{e['trough']} ${e['depth']:,.0f}" for e in EP[nm]), flush=True)
yrs = np.where(idx.month >= 7, idx.year, idx.year - 1)
by2, by3 = (E - T2).groupby(yrs).sum(), (E - inpos).groupby(yrs).sum()
print("leg minus always-on twin by July-June year: " + ", ".join(f"{int(k)} ${v:,.0f}" for k, v in by2.items()) + f"; leg ahead in {int((by2 > 0).sum())} of {len(by2)}")
print("leg minus in-position twin by July-June year: " + ", ".join(f"{int(k)} ${v:,.0f}" for k, v in by3.items()) + f"; leg ahead in {int((by3 > 0).sum())} of {len(by3)}")
Lr, Lpr = rows[7]["roc30"], rows[8]["roc30"]
lead = Lr - Lpr
line = PL["L vs L' (always-on twin in ENGU-Q's place)"]["line_5pct"]
if abs(lead) < line:
    verdict = f"not distinguishable at this resolution: L - L' = {lead:+.2f} ROC points, MDE {line:.2f}"
elif Lpr >= Lr:
    verdict = f"ENGU-Q's seat adds nothing over a constant-exposure NQ holding at its average exposure (L' - L = {-lead:+.2f}, MDE {line:.2f})"
else:
    verdict = f"ENGU-Q beats a constant-exposure NQ holding by {lead:.2f} ROC points on L (${rows[7]['usd_year'] - rows[8]['usd_year']:,.0f} a year; MDE {line:.2f})"
print("READ (pre-set wording):", verdict)
json.dump({"note_sha256_lf": note_sha, "W": W, "W_beta": W_BETA, "wf_rolls": wf_rolls, "wf_round_trips_leg": n_wf_trades, "power": PL, "rows": rows,
           "episodes": EP, "leg_minus_always_on_by_year": {int(k): float(v) for k, v in by2.items()},
           "leg_minus_in_position_by_year": {int(k): float(v) for k, v in by3.items()}, "verdict": verdict},
          open(os.path.join(OUT, "q31_drifttwin.json"), "w"), indent=1, default=float)
print("wrote", os.path.join(OUT, "q31_drifttwin.json"))
