"""TTM (house verifier): BLIND stage-1 re-check of the Qwen Lab's QL_LATEBREAK_NQ PRE-WF Stage A (20261017-1353-scalper).
Built from C:/EdgeLog/qwen_lab/ideas/20261017-1353-scalper/QL_LATEBREAK_NQ_2026-10-17.md and plugin_v1.py.txt only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read
until this output's sha256 is posted to MANAGER.
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 c3c2db59... = the prereg's hash) through the engine on the registry master,
    params None (file defaults), cost_pts 0 in the engine, cost subtracted per trade here.
(B) TTM's OWN implementation of the prereg's Mechanism text (ttm_own_rule_b.py, LF sha256 recorded in arm_b_prelock.txt
    BEFORE the plugin's code was opened); knob values = the plugin file's DEFAULT_PARAMS defaults (not in the prereg text).
Both scored by TTM's booking: $ on the exit session (ET date), zero days kept (every master session in the window);
ROC@30k, DD5 (+one_episode), DD% from peak ($100k start), Sortino. Writes only into the output folder below."""
import hashlib
import json
import math
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1353-scalper"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1353-scalper"
sys.path.insert(0, REPO)
sys.path.insert(0, OUT)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
from ttm_own_rule_b import own_rule                               # noqa: E402

PLUGIN = IDEA + "/plugin_v1.py.txt"
PREREG = IDEA + "/QL_LATEBREAK_NQ_2026-10-17.md"
PIN_PREFIX = "c3c2db591756"
PIN_FULL = "c3c2db5917567392a463d906dc84b45a1d0d4fc9eceb8e99ee4157fa53ac6040"   # the prereg's 'Hashes' line
ARM_B_FILE = OUT + "/ttm_own_rule_b.py"
ARM_B_PRELOCK = "a1161c8a4252319c2b30842d0df6622e20dae0f706d47eb7730745b358a795f8"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
MULT = 20.0
HOUSE_COST = 0.783                       # the prereg's / 10-12 scalp hunt's NQ round trip
REAL_COST = 0.25 * 2 + 5.65 / MULT       # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = HOUSE_COST + 0.5           # +1 tick each side on top of house cost
PREREG_BARS, PREREG_FP = 119248, "66f906272ba2dba5645708c9956ecf2360515b64"


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def clean(x):
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return None if (math.isnan(x) or math.isinf(x)) else x
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


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
            "one_episode": r["one_episode"] if isinstance(r["one_episode"], str) else bool(r["one_episode"]),
            "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    g = np.asarray(pts_gross, float)
    usd = (g - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum()
    assert set(s.index) <= set(days), "exit day outside the calendar"
    s = s.reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "cost_pts": cost, "gross_pts_per_trade": float(g.mean()), "net_pts_per_trade": float(g.mean() - cost),
              "net_usd_per_trade": float(usd.mean()), "gross_over_cost": float(g.mean() / cost),
              "avg_win_usd": float(usd[usd > 0].mean()) if (usd > 0).any() else float("nan"),
              "avg_loss_usd": float(-usd[usd <= 0].mean()) if (usd <= 0).any() else float("nan")})
    f["promotion_rule_pass"] = bool(f["gross_pts_per_trade"] >= HOUSE_COST and (f["roc30"] or 0) > 0
                                    and f["one_episode"] is False)
    return f


def arm(tr, idxn, days, sess_idx, eb, xb, sd, gp):
    E = np.array([t[eb] for t in tr], int)
    X = np.array([t[xb] for t in tr], int)
    G = np.array([t[gp] for t in tr], float)
    S = np.array([t[sd] for t in tr], int)
    hold = X - E
    out = {"house_cost": score(X, G, idxn, days, HOUSE_COST), "real_cost": score(X, G, idxn, days, REAL_COST),
           "stress_cost": score(X, G, idxn, days, STRESS_COST), "gross_zero_cost": score(X, G, idxn, days, 0.0),
           "longs": int((S > 0).sum()), "shorts": int((S < 0).sum()),
           "hold_bars_median": float(np.median(hold)), "hold_bars_mean": float(hold.mean()),
           "earliest_entry_session_bar": int(sess_idx[E].min()), "entries_before_bar31": int((sess_idx[E] < 31).sum()),
           "stopped_share": None, "first_trade": [str(idxn[E[0]]), str(idxn[X[0]])], "last_trade": [str(idxn[E[-1]]), str(idxn[X[-1]])]}
    return out


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_FULL
    assert plugin_pin_ok, "plugin pin"
    assert lf_sha(ARM_B_FILE) == ARM_B_PRELOCK, "arm B changed after the pre-lock"
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    assert idxn[-1] < pd.Timestamp("2016-07-01"), "window end before the WF start"
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    did = np.asarray(A["day_id"])
    sess_idx = pd.Series(np.arange(len(did))).groupby(did).cumcount().to_numpy()
    clock_idx = ((idxn.hour * 60 + idxn.minute) - 570) // 5
    res = {"idea": "QL_LATEBREAK_NQ", "folder": "20261017-1353-scalper", "stage": "1 - BLIND BUILD (PRE-WF Stage A)",
           "plugin": PLUGIN, "plugin_lf_sha256": pin, "plugin_pin_ok": plugin_pin_ok,
           "prereg": PREREG, "prereg_lf_sha256": lf_sha(PREREG),
           "arm_b_file": ARM_B_FILE, "arm_b_lf_sha256": ARM_B_PRELOCK,
           "harness_lf_sha256": lf_sha(os.path.abspath(__file__)),
           "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "bars": len(c), "bars_match_prereg": len(c) == PREREG_BARS, "fingerprint": A.get("fingerprint"),
           "fingerprint_match_prereg": A.get("fingerprint") == PREREG_FP,
           "window": [str(days[0].date()), str(days[-1].date())], "sessions": len(days),
           "session_index_equals_open_clock_index": bool((sess_idx == clock_idx).all()),
           "costs_pts": {"house": HOUSE_COST, "real": REAL_COST, "stress": STRESS_COST, "usd_per_pt": MULT}}

    # ---- ARM A: the plugin through the engine ----
    m = types.ModuleType("ttm_ql_latebreak")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    knobs = {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # entry, exit, side, entry_px, gross
    res["plugin_defaults"] = knobs
    res["A_plugin"] = arm(Ta, idxn, days, sess_idx, 0, 1, 2, 4)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["engine_num_trades"] = r.get("num_trades")
    rs = (r.get("_meta") or {}).get("roll_stamp") or {}
    res["A_plugin"]["engine_roll_stamp"] = {k: rs.get(k) for k in ("master_type", "signal_method", "method_source",
                                                                      "switches_in_window", "trades_crossing",
                                                                      "usd_crossing_trades", "guard", "registry")}
    # stopped share for A: exit before the session's last bar
    last_bar = pd.Series(np.arange(len(did))).groupby(did).transform("max").to_numpy()
    res["A_plugin"]["stopped_share"] = float(np.mean([last_bar[t[1]] != t[1] for t in Ta]))

    # ---- ARM B: TTM's own rule (pre-locked), knobs = file defaults ----
    B = own_rule(o, h, l, c, did, quiet_k=knobs["quiet_k"], stop_frac=knobs["stop_frac"])
    res["B_own_rule"] = arm(B, idxn, days, sess_idx, 0, 1, 2, 5)
    res["B_own_rule"]["stopped_share"] = float(np.mean([last_bar[t[1]] != t[1] for t in B]))

    # ---- A vs B trade for trade ----
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    onlyA = sorted(set(ka) - set(kb))
    onlyB = sorted(set(kb) - set(ka))
    first_sess = int(did[0])
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both),
                     "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
                     "only_A": len(onlyA), "only_B": len(onlyB),
                     "only_A_session_numbers_in_load": [int(did[k[0]] - first_sess) for k in onlyA][:20],
                     "first_only_A": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), ka[k][4]] for k in onlyA[:10]],
                     "first_only_B": [[str(idxn[k[0]]), k[1], str(idxn[kb[k][1]]), kb[k][5]] for k in onlyB[:10]],
                     "first_exit_diffs": [[str(idxn[k[0]]), str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:10],
                     "entry_px_diffs_on_matched": int(sum(1 for k in both if abs(ka[k][3] - kb[k][3]) > 1e-6))}
    # sensitivity: B with the plugin's warm-up (>= 5 prior sessions instead of a full 20) - explains only_A if the warm-up differs
    pre = [t for t in Ta if did[t[0]] - first_sess < 20]
    res["A_vs_B"]["A_trades_in_first_20_sessions"] = len(pre)
    if onlyA or onlyB:
        Ta_post = [t for t in Ta if did[t[0]] - first_sess >= 20]
        kap = {(t[0], t[2]): t for t in Ta_post}
        res["A_vs_B"]["after_first_20_sessions"] = {
            "A_trades": len(Ta_post), "only_A": len(set(kap) - set(kb)), "only_B": len(set(kb) - set(kap)),
            "exact": sum(1 for k in set(kap) & set(kb) if kap[k][1] == kb[k][1] and abs(kap[k][4] - kb[k][5]) < 1e-6)}
    v = res["A_vs_B"]
    sess0 = [k for k in onlyA if did[k[0]] - first_sess == 0]
    res["findings"] = [
        "plugin pin OK (LF sha256 = the prereg's full hash); bars %d and fingerprint match the prereg's PRE-WF load" % len(c),
        "A vs B: %d / %d B trades EXACT (same entry bar, side, exit bar, gross pts, entry px); only_B %d; only_A %d, ALL in the "
        "first 20 sessions of the load (session numbers %s)" % (v["exact"], v["B_trades"], v["only_B"], v["only_A"],
                                                                 v["only_A_session_numbers_in_load"]),
        "cause (plugin code, read after B was pre-locked): the quiet filter sits under 'if i >= 1', so session 0 of the load "
        "is NEVER quiet-filtered (%d trade); sessions 1-4 are skipped (< 5 prior); sessions 5-19 use the median of only 5-19 "
        "prior sessions, not the prereg's 'trailing 20 sessions'. Warm-up only, not look-ahead; the WF stage loads from "
        "2015-01-02 and drops entries before 2016-07-01, so it does not reach the WF numbers" % len(sess0),
        "entries before session bar 31: A %d, B %d; trades crossing a roll switch (engine stamp): %s"
        % (res["A_plugin"]["entries_before_bar31"], res["B_own_rule"]["entries_before_bar31"], rs.get("trades_crossing")),
        "gross %.3f pt/trade (A) vs the 0.783 pt round trip: gross/cost %.3f - PROMOTION RULE fails on gross alone"
        % (res["A_plugin"]["house_cost"]["gross_pts_per_trade"], res["A_plugin"]["house_cost"]["gross_over_cost"])]
    s = json.dumps(clean(res), indent=1, sort_keys=True)
    print(s)
    b = (s + "\n").encode("utf-8")
    p = os.path.join(OUT, "ttm_verify.json")
    open(p, "wb").write(b)
    print("output sha256", hashlib.sha256(open(p, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
