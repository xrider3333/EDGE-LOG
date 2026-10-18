"""TTM (house verifier): BLIND stage-1 re-check of the Qwen Lab's QL_RANGECOMP_NQ PRE-WF Stage A (idea 20261017-1502-own).
Built from C:/EdgeLog/qwen_lab/ideas/20261017-1502-own/QL_RANGECOMP_NQ_2026-10-17.md and plugin_v2.py.txt only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read
until this output's sha256 is posted to MANAGER.
(B) TTM's OWN implementation of the prereg's Mechanism text - written BEFORE the plugin's code was opened. The prereg gives no
    default for entry_frac / stop_frac; its Data section says 'params = the file's DEFAULT_PARAMS defaults', so the knob VALUES
    (and only them) are read from the plugin's DEFAULT_PARAMS literal by ast, never by reading its logic.
(A) the plugin AS RUN (plugin_v2.py.txt, LF sha256 must start 0ca9d8877295 = the prereg's hash) through the engine on the registry
    master row; trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1502-own/."""
import ast
import hashlib
import inspect
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1502-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261017-1502-own/plugin_v2.py.txt"
PIN_PREFIX = "0ca9d8877295"
PIN_FULL_PREREG = "0ca9d8877295d816644c82b97b457f171496db65fc420c5b6800e33c1153fa21"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # house + 1 tick each side (reported for completeness; this idea is not a scalper)
TIME_STOP_BARS = 77                    # prereg timing contract (Qwen's stated input): exit at the CLOSE of entry bar + 77
WARMUP_PREREG = 12                     # Mechanism text: warmup_bars default 12 (= 10:30)
OWN_RULE_READING = [
    "knob values: the Mechanism text states warmup_bars default 12 but gives NO default for entry_frac / stop_frac; the prereg's "
    "Data section says params = the file's DEFAULT_PARAMS defaults, so those two VALUES were read from the DEFAULT_PARAMS literal "
    "by ast.literal_eval (entry_frac 0.1, stop_frac 0.15, warmup_bars 12 = the prereg's 12); the plugin's logic was not read",
    "bar 0 = the session's first bar (09:30 open, every session in the window); in-session index = position in the day_id run, "
    "equal to the clock index (0 intra-session hole bars in this window)",
    "running high / low = max(high[0..k]) / min(low[0..k]) with bar k INCLUDED; range_so_far from the same bars; <= 0 skips",
    "signal bars k >= warmup_bars (12, the 10:30 bar) - so the earliest fill is bar 13 (10:35 open), matching the prereg's "
    "first_signal_bar 13",
    "LONG: close[k] >= RH - entry_frac*range AND close[k] > open[0] (strict); SHORT: close[k] <= RL + entry_frac*range AND "
    "close[k] < open[0] (strict); open[0] = the session's first bar's open; the two are exclusive via the open[0] test",
    "fill at open[k+1]; a signal on the session's last bar has no k+1 and is not taken; first signal with a fillable k+1 = the "
    "session's one trade; no re-entry after a stop",
    "stop = entry_px -/+ stop_frac * range_so_far of the SIGNAL bar k (anchored at the fill price, not at the extreme); fixed for "
    "the trade",
    "stop checked intrabar from the entry bar itself (low <= stop long / high >= stop short books the stop price); on bars after "
    "the entry bar an open already through the stop books that open (gap-through); a stop touch on the last bar beats the close",
    "no target; exit at the session's last bar close (the session's last bar in the data: 78-bar days at 15:55, early-close / "
    "short days at their last bar); the contract's 77-bar time stop (close of entry bar + 77) is applied too but never binds "
    "(max hold 64 bars)",
    "booking: gross pts = side*(exit_px - entry_px), cost subtracted per trade, $ on the exit bar's ET session date",
]


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def own_rule(o, h, l, c, day_id, warmup_bars, entry_frac, stop_frac, time_stop_bars=TIME_STOP_BARS):
    """The prereg's Mechanism, written from its text (before the plugin code was read).
    Per session (day_id run; bar 0 = the session's first bar = 09:30 open; no intra-session holes in this window, so the
    positional in-session index equals the clock index the prereg reads):
      running_high[k] = max(high[0..k]), running_low[k] = min(low[0..k])  (bar k INCLUDED)
      at each bar k >= warmup_bars: rng = RH - RL; rng <= 0 -> skip
      LONG  if close[k] >= RH - entry_frac*rng AND close[k] > open[0]
      SHORT if close[k] <= RL + entry_frac*rng AND close[k] < open[0]
      the first such k with a bar k+1 in the same session fills at open[k+1]; one trade per session (first signal wins)
      stop = entry -/+ stop_frac*rng (rng of the signal bar k), checked intrabar from the entry bar itself; a bar AFTER the
      entry bar whose open is already through the stop books its open; else a touch books the stop price
      no target; exit at the session's last bar close, or at the close of entry bar + time_stop_bars if that comes first
      (never binds on a <=78-bar session with entry >= bar 13); a stop touch on the exit bar wins (intrabar before the close)
    Only bars <= k decide; the fill is bar k+1's open. Returns (entry_bar, exit_bar, side, entry_px, exit_px, pts gross, how)."""
    n = len(c)
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        rh = np.maximum.accumulate(h[s:e])
        rl = np.minimum.accumulate(l[s:e])
        o0 = o[s]
        for kk in range(warmup_bars, e - s - 1):          # kk = in-session index of the signal bar; kk+1 must exist
            rng = rh[kk] - rl[kk]
            if rng <= 0:
                continue
            k = s + kk
            if c[k] >= rh[kk] - entry_frac * rng and c[k] > o0:
                side = 1
            elif c[k] <= rl[kk] + entry_frac * rng and c[k] < o0:
                side = -1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * stop_frac * rng
            last = min(e - 1, ent + time_stop_bars)
            xb, xp, how = last, c[last], ("session_end" if last == e - 1 else "time_stop")
            for j in range(ent, last + 1):
                if j > ent and side * (o[j] - stop) <= 0:
                    xb, xp, how = j, o[j], "stop_gap_open"
                    break
                if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                    xb, xp, how = j, stop, "stop"
                    break
            out.append((ent, xb, side, float(ep), float(xp), float(side * (xp - ep)), how))
            break                                          # one trade per session
    return out


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
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts = np.asarray(pts_gross, float)
    usd = (pts - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"cost_pts": cost, "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "gross_pts_per_trade": float(pts.mean()) if len(usd) else float("nan"),
              "net_usd_per_trade": float(usd.mean()) if len(usd) else float("nan"),
              "avg_win_loss_usd": [float(usd[usd > 0].mean()), float(-usd[usd <= 0].mean())] if len(usd) else []})
    return f


def knob_defaults(path):
    """The knob VALUES only: DEFAULT_PARAMS literal read by ast (the plugin's logic is not read here)."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS" for t in node.targets):
            dp = ast.literal_eval(node.value)
            return {k: (v["default"] if isinstance(v, dict) else v) for k, v in dp.items()}, dp
    raise RuntimeError("no literal DEFAULT_PARAMS")


def main():
    res = {"idea": "QL_RANGECOMP_NQ", "idea_folder": "C:/EdgeLog/qwen_lab/ideas/20261017-1502-own",
           "stage": "1 - BLIND BUILD (lab numbers not read)", "own_rule_reading": OWN_RULE_READING,
           "cost_note": "house 0.533 pt, real 0.7825 pt (owner: $5.65 + 1 tick each side), stress house+0.5 pt reported for "
                        "completeness only - this idea holds to the session close, not a short-hold scalper"}
    sha = lf_sha(PLUGIN)
    res["plugin_lf_sha256"] = sha
    res["plugin_pin_ok"] = bool(sha.startswith(PIN_PREFIX))
    res["plugin_pin_full_match_prereg"] = bool(sha == PIN_FULL_PREREG)
    assert res["plugin_pin_ok"], "plugin pin"
    res["own_rule_source_sha256"] = hashlib.sha256(inspect.getsource(own_rule).encode()).hexdigest()

    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    pos = np.arange(len(c)) - np.repeat(starts, np.diff(np.r_[starts, len(c)]))
    slot = ((idxn.hour * 60 + idxn.minute) - 570) // 5
    res.update({"master": MASTER, "registry_id": row[0].get("id"),
                "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
                "data_fingerprint": A.get("fingerprint"), "bars": int(len(c)), "window": [str(days[0].date()), str(days[-1].date())],
                "sessions": int(len(days)), "intra_session_hole_bars": int((pos != np.asarray(slot)).sum())})

    kd, dp = knob_defaults(PLUGIN)
    res["knob_defaults_from_DEFAULT_PARAMS"] = kd
    res["DEFAULT_PARAMS_literal"] = dp
    wb = int(kd.get("warmup_bars", WARMUP_PREREG))
    res["warmup_matches_prereg_12"] = bool(wb == WARMUP_PREREG)

    # ---- ARM B: own rule (prereg warmup 12; entry_frac / stop_frac = the file's DEFAULT_PARAMS values) ----
    B = own_rule(o, h, l, c, day_id, WARMUP_PREREG, float(kd["entry_frac"]), float(kd["stop_frac"]))
    eb, xb = [t[0] for t in B], [t[1] for t in B]
    res["B_own_rule"] = {"house_cost": score(xb, [t[5] for t in B], idxn, days, COST),
                         "real_cost": score(xb, [t[5] for t in B], idxn, days, REAL_COST),
                         "stress_cost": score(xb, [t[5] for t in B], idxn, days, STRESS_COST),
                         "exit_how": {str(k): int(v) for k, v in pd.Series([t[6] for t in B]).value_counts().items()},
                         "sides": {"long": int(sum(t[2] > 0 for t in B)), "short": int(sum(t[2] < 0 for t in B))},
                         "earliest_entry_in_session_bar": int(pos[eb].min()) if B else None,
                         "entries_before_bar_13": int((pos[eb] < 13).sum()) if B else 0,
                         "max_bars_held": int(max(x - e for e, x in zip(eb, xb))) if B else None,
                         "gross_pts_total": float(sum(t[5] for t in B))}

    # ---- ARM A: the plugin through the engine ----
    m = types.ModuleType("ttm_ql_rangecomp")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]
    ea, xa = [t[0] for t in Ta], [t[1] for t in Ta]
    res["A_plugin"] = {"house_cost": score(xa, [t[4] for t in Ta], idxn, days, COST),
                       "real_cost": score(xa, [t[4] for t in Ta], idxn, days, REAL_COST),
                       "stress_cost": score(xa, [t[4] for t in Ta], idxn, days, STRESS_COST),
                       "engine_total_pnl_pts": float(r.get("total_pnl", float("nan"))),
                       "sides": {"long": int(sum(t[2] > 0 for t in Ta)), "short": int(sum(t[2] < 0 for t in Ta))},
                       "earliest_entry_in_session_bar": int(pos[ea].min()) if Ta else None,
                       "entries_before_bar_13": int((pos[ea] < 13).sum()) if Ta else 0,
                       "max_bars_held": int(max(x - e for e, x in zip(ea, xa))) if Ta else None,
                       "gross_pts_total": float(sum(t[4] for t in Ta)),
                       "trade_tuple_len": int(len(T[0])) if T else 0}

    # ---- A vs B ----
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    same_entry_px = sum(1 for k in both if abs(ka[k][3] - kb[k][3]) < 1e-9)
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both),
                     "exact_same_exit_and_pts": exact, "same_exit_bar": same_exit, "same_gross_pts": same_pts,
                     "same_entry_px": same_entry_px,
                     "only_A": len(set(ka) - set(kb)), "only_B": len(set(kb) - set(ka)),
                     "same_session_diff_entry": len({int(day_id[k[0]]) for k in set(ka) - set(kb)} &
                                                    {int(day_id[k[0]]) for k in set(kb) - set(ka)}),
                     "first_only_A": [[str(idxn[k[0]]), k[1], ka[k][4]] for k in sorted(set(ka) - set(kb))[:5]],
                     "first_only_B": [[str(idxn[k[0]]), k[1], kb[k][5]] for k in sorted(set(kb) - set(ka))[:5]],
                     "first_exit_or_pts_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                                 for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5],
                     "gross_pts_total_A_minus_B": float(sum(t[4] for t in Ta) - sum(t[5] for t in B))}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    b = (s + "\n").encode("utf-8")
    with open(os.path.join(OUT, "ttm_verify.json"), "wb") as f:
        f.write(b)
    print(s)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
