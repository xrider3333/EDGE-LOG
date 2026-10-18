"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_TOMRUSH_NQ PRE-WF Stage A (idea folder 20261016-2218-shelf34).
Built from the prereg QL_TOMRUSH_NQ_2026-10-17.md and plugin_v2.py.txt only; the lab's numbers_pre_wf.json / pre_wf_trades.csv /
sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read before this output's sha256 is posted.
(A) the plugin AS RUN (plugin_v2.py.txt, LF sha256 b57fa81a4bdf... = the prereg's hash) through the engine on the registry master;
(B) TTM's OWN implementation of the prereg's Mechanism text (ttm_armb_own_rule.py, frozen before the plugin was opened; its
    sha256 at freeze is pinned below and its blind pre-pass is in armb_blind_prepass.json); trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Usage: python ttm_verify_20261016-2218-shelf34.py [--prepass]   (--prepass = ARM B only, run before the plugin is read)
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-2218-shelf34/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-2218-shelf34"
sys.path.insert(0, REPO)
sys.path.insert(0, OUT)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
import ttm_armb_own_rule                                          # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261016-2218-shelf34"
PLUGIN = IDEA + "/plugin_v2.py.txt"
PIN_PLUGIN_PREFIX = "b57fa81a4bdf"
PIN_PLUGIN_FULL = "b57fa81a4bdfe01cc29fcd6648d46f24cc701c69545a3e824b423a341139194f"   # the prereg's Hashes line
PIN_CAL = "03f8ca7964cd22a5c10737c94128f02ddbfa031510c603ce34cfeba43e5b50b9"            # prereg's session_calendar hash
ARMB_FILE = OUT + "/ttm_armb_own_rule.py"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side on top of house (scalper stress; reported for completeness)
STOP_GRID = [None, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net_usd": float(x.sum()), "per_yr_usd": float(x.sum()) / yrs, "years": yrs, "max_dd": mdd,
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"), "dd5": float(r["dd5_usd"]),
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "dd5_n": int(r["n"]), "episodes_total": int(r["episodes_total"]), "new_high_ever": bool(np.max(eq) > 1e-9),
            "one_episode_reading": ("NOT TESTABLE" if (int(r["n"]) <= 1 or not np.max(eq) > 1e-9)
                                    else ("True" if r["one_episode"] else "False")),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts = np.asarray(pts_gross, float)
    usd = (pts - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"cost_pts_rt": cost, "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "gross_pts_per_trade": float(pts.mean()) if len(pts) else float("nan"),
              "net_usd_per_trade": float(usd.mean()) if len(usd) else float("nan")})
    return f


def load():
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1, "registry row"
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    return row[0], A, idx, idxn, days


def arm_b(A, idx, stop_frac):
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    return ttm_armb_own_rule.own_rule(o, h, l, c, np.asarray(A["day_id"]), idx, stop_frac=stop_frac)


def b_block(B, idxn, days):
    xb, gp = [t[1] for t in B], [t[5] for t in B]
    return {"house_cost": score(xb, gp, idxn, days, COST), "real_cost": score(xb, gp, idxn, days, REAL_COST),
            "stress_cost": score(xb, gp, idxn, days, STRESS_COST),
            "stopped": int(sum(1 for t in B if t[1] != int(np.flatnonzero(idxn.normalize() == idxn[t[0]].normalize())[-1])))}


def prepass():
    """ARM B only, before the plugin is opened: B at every stop_frac in STOP_GRID (the prereg text gives no stop_frac value)."""
    row, A, idx, idxn, days = load()
    res = {"armb_file_sha256": lf_sha(ARMB_FILE), "fingerprint": A.get("fingerprint"), "bars": int(len(idx)),
           "sessions": len(days), "grid": {}}
    flag = ttm_armb_own_rule.is_last_n_sessions_of_month(idx, 3, np.asarray(A["day_id"]))
    res["flagged_sessions"] = int(len(set(np.asarray(A["day_id"])[np.asarray(flag, bool)])))
    for sf in STOP_GRID:
        B = arm_b(A, idx, sf)
        res["grid"][str(sf)] = b_block(B, idxn, days)
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    open(os.path.join(OUT, "armb_blind_prepass.json"), "w", encoding="utf-8", newline="\n").write(s + "\n")
    print(s)
    print("prepass sha256", hashlib.sha256((s + "\n").encode()).hexdigest())


ARMB_SHA_AT_FREEZE = "0fc651007b3a800994512dfffda89d886a58727b8ac76294aa24634b13349e3d"   # before the plugin was opened
PREPASS_SHA = "54460f266454090ab53810befe9787cbecec4ef5cf9e7c6cbbc2514b4745c5bd"          # armb_blind_prepass.json bytes
B_STOP_FRAC = 2.0   # the ONE value the prereg text omits; taken from the plugin's DEFAULT_PARAMS after B was frozen


def main():
    sha = lf_sha(PLUGIN)
    plugin_pin_ok = sha.startswith(PIN_PLUGIN_PREFIX) and sha == PIN_PLUGIN_FULL
    assert plugin_pin_ok, "plugin pin"
    assert lf_sha(ARMB_FILE) == ARMB_SHA_AT_FREEZE, "arm B changed after freeze"
    pre_bytes = open(os.path.join(OUT, "armb_blind_prepass.json"), "rb").read()
    assert hashlib.sha256(pre_bytes).hexdigest() == PREPASS_SHA, "prepass changed"
    cal_sha = lf_sha(os.path.join(REPO, "augur_engine", "session_calendar.py"))
    row, A, idx, idxn, days = load()
    res = {"idea": "QL_TOMRUSH_NQ", "idea_folder": IDEA, "master": MASTER, "registry_id": row.get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": A.get("fingerprint"), "bars": int(len(idx)), "window": [str(days[0].date()), str(days[-1].date())],
           "sessions": len(days), "plugin": PLUGIN, "plugin_lf_sha256": sha, "plugin_pin_ok": bool(plugin_pin_ok),
           "session_calendar_lf_sha256": cal_sha, "session_calendar_pin_ok": cal_sha == PIN_CAL,
           "armb_file": ARMB_FILE, "armb_file_sha256_at_freeze": ARMB_SHA_AT_FREEZE, "armb_prepass_sha256": PREPASS_SHA,
           "costs_pts_rt": {"house": COST, "real": REAL_COST, "stress_house_plus_1tick_each_side": STRESS_COST},
           "mult_usd_per_pt": MULT}
    # ARM A: the plugin as run, file defaults, cost 0 in the engine
    m = types.ModuleType("ttm_ql_tomrush")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # (entry, exit, side, entry_px, gross)
    xa, ga = [t[1] for t in Ta], [t[4] for t in Ta]
    last_bar = {}
    did = np.asarray(A["day_id"])
    for i in np.r_[np.flatnonzero(np.diff(did)), len(did) - 1]:
        last_bar[int(did[i])] = int(i)
    res["arm_a"] = {"house_cost": score(xa, ga, idxn, days, COST), "real_cost": score(xa, ga, idxn, days, REAL_COST),
                    "stress_cost": score(xa, ga, idxn, days, STRESS_COST),
                    "engine_total_pnl_pts": float(r.get("total_pnl", float("nan"))), "engine_num_trades": int(r.get("num_trades", -1)),
                    "stopped": int(sum(1 for t in Ta if t[1] != last_bar[int(did[t[0]])])),
                    "sides": sorted(set(t[2] for t in Ta)),
                    "entries_not_at_session_bar0": int(sum(1 for t in Ta if t[0] > 0 and did[t[0] - 1] == did[t[0]])),
                    "entries_not_0930": int(sum(1 for t in Ta if (idxn[t[0]].hour, idxn[t[0]].minute) != (9, 30)))}
    # ARM B: TTM's own rule at stop_frac 2.0 (the frozen module; must equal the blind pre-pass row '2.0')
    B = arm_b(A, idx, B_STOP_FRAC)
    res["arm_b"] = b_block(B, idxn, days)
    pre = json.loads(pre_bytes.decode())
    pr = pre["grid"][str(B_STOP_FRAC)]   # the prepass row predates the dd5_n / NOT TESTABLE fields: compare its own keys
    res["arm_b"]["matches_blind_prepass_row"] = bool(pr["stopped"] == res["arm_b"]["stopped"] and all(
        all(abs(float(pr[cb][k]) - float(res["arm_b"][cb][k])) < 1e-9 if isinstance(pr[cb][k], float) else pr[cb][k] == res["arm_b"][cb][k]
            for k in pr[cb]) for cb in ("house_cost", "real_cost", "stress_cost")))
    res["arm_b"]["stop_frac_used"] = B_STOP_FRAC
    res["own_rule_reading"] = [
        "R1 calendar: house augur_engine.session_calendar.is_last_n_sessions_of_month(index, 3, day_id) (file LF sha = prereg pin); "
        "217 flagged tradable sessions (73 months x 3 minus the 2 data-hole sessions 2013-11-28, 2014-12-31)",
        "R2 entry: LONG at the OPEN of the session's first bar in the data (bar 0); every entry checked = 09:30; one per session; no short",
        "R3 ATR(14): simple mean of TRUE RANGE (max(h-l, |h-prev close|, |l-prev close|), prev close = previous bar in the data) over "
        "the 14 bars immediately before bar 0 (= the prior session's last 14 bars); not Wilder; not high-low",
        "R4 stop: entry - stop_frac x ATR, live from bar 0 (entry bar) intrabar on the low; a LATER bar opening at/below the stop books "
        "its open (gap-through), else the stop price; stop checked on the last bar too",
        "R5 exit: the session's last bar's CLOSE (the last bar in the data for that day_id: 15:55 on full days, earlier on short days)",
        "stop_frac: NOT in the prereg text -> B frozen with stop_frac as a parameter and run blind at None/0.5..3.0 "
        "(armb_blind_prepass.json); the headline B uses 2.0, the plugin DEFAULT_PARAMS value, read only after the freeze",
        "costs: house 0.533 pt RT, real 0.7825 pt RT, stress 1.033 pt RT (house + 1 tick each side; not a scalper, reported anyway); "
        "$20/pt; booked on the exit session's ET date; zero days kept on the master's 1550 sessions"]
    res["arm_b_blind_grid_house_cost"] = {k: {kk: v["house_cost"][kk] for kk in ("trades", "net_usd", "roc30", "dd5", "one_episode",
                                                                                 "dd_pct_peak", "sortino", "gross_pts_per_trade")}
                                          for k, v in pre["grid"].items()}
    # A vs B, trade for trade by (entry_bar, side)
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    res["a_vs_b"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both),
                     "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
                     "only_A": len(set(ka) - set(kb)), "only_B": len(set(kb) - set(ka)),
                     "same_entry_px": sum(1 for k in both if abs(ka[k][3] - kb[k][3]) < 1e-9),
                     "max_abs_gross_diff_pts": float(max([abs(ka[k][4] - kb[k][5]) for k in both] or [0.0])),
                     "first_only_A": [str(idxn[k[0]]) for k in sorted(set(ka) - set(kb))[:5]],
                     "first_only_B": [str(idxn[k[0]]) for k in sorted(set(kb) - set(ka))[:5]],
                     "first_diffs": [[str(idxn[k[0]]), str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                     for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5],
                     "first_trades_A": [[str(idxn[t[0]]), str(idxn[t[1]]), t[2], t[3], t[4]] for t in Ta[:3]]}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    path = os.path.join(OUT, "ttm_verify.json")
    open(path, "w", encoding="utf-8", newline="\n").write(s + "\n")
    print(s)
    print("output sha256", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    if "--prepass" in sys.argv:
        prepass()
    else:
        main()
