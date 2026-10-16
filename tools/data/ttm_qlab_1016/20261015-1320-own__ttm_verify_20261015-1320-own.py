"""TTM (house verifier): BLIND stage-1 re-check of Qwen Lab idea QL_VWAPREVERT_NQ, SECOND run (plugin v2, LF sha256 dbcf3008...),
idea folder C:/EdgeLog/qwen_lab/ideas/20261015-1320-own/.
Built from that folder's prereg (QL_VWAPREVERT_NQ_2026-10-15.md) and plugin_v2.py.txt only; the lab's numbers_pre_wf.json /
pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read before this output's
sha256 is posted to MANAGER.
(B) TTM's OWN implementation of the prereg 'Mechanism' text (written BEFORE the plugin code was read), pure function over the
    registry master's arrays;
(A) the plugin AS RUN through the engine on the pinned master (registry row by filename), params None, cost 0 in the engine;
trade-for-trade diff A vs B. Both scored by TTM's booking: $ on the EXIT session (ET date), zero days kept, calendar = every
session of the master in the window; ROC@30k, DD5 (+one-episode), DD% from peak ($100k), Sortino; house cost 0.533 pt, real
cost 0.7825 pt (owner rule: $5.65 commission + 1 tick each side), stress = house + 0.5 pt (1 extra tick each side).
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1320-own/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1320-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261015-1320-own"
PLUGIN = IDEA + "/plugin_v2.py.txt"
PREREG = IDEA + "/QL_VWAPREVERT_NQ_2026-10-15.md"
PIN_PREFIX = "dbcf3008fb4b"
PIN_FULL = "dbcf3008fb4bd7279edf796e24e21f73f88cf0962fdc0074fd4c1ed9ceb9e942"   # the prereg's 'Hashes' line
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
MULT = 20.0
COST = 0.533                              # house RTH round trip, NQ
REAL_COST = 0.25 * 2 + 5.65 / MULT        # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5                  # scalper stress: house + 1 tick each side = 1.033 pt


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------------
# ARM B - written from the prereg's Mechanism text ONLY, before the plugin code was opened.
# Text: "At each bar k (k >= 25), compute: (1) session VWAP = sum(close[session_start..k]) / (k - session_start + 1) ...
# (2) ATR20 = mean of (high[i]-low[i]) over bars k-19..k. If close[k] > VWAP + 2.5*ATR20, enter SHORT at bar k+1's open. If
# close[k] < VWAP - 2.5*ATR20, enter LONG at bar k+1's open. Stop: 1.0*ATR20 against entry (intrabar, gap-through books the
# open). Target: 1.5*ATR20 in favor (intrabar, gap-through books the open). Flat at session's last bar. One trade per session
# (first signal wins)."
# Choices (most literal reading), see READING below.
# ---------------------------------------------------------------------------------------------------------------------------
READING = [
    "k is the GLOBAL bar index of the loaded window (the text writes VWAP with k - session_start + 1, so k and session_start are "
    "the same global index); 'k >= 25' is therefore a global warm-up that only touches the window's first session.",
    "session = one ET calendar day of the RTH master (engine day_id); session_start = that day's first bar.",
    "VWAP proxy = plain mean of close[session_start..k] (inclusive), exactly the text's formula; no volume.",
    "ATR20 = mean(high - low) over GLOBAL bars k-19..k inclusive (may reach back into the prior session early in a day); "
    "plain range, not true range, as written.",
    "signal on bar k's close, strict inequalities (> VWAP + 2.5*ATR20 -> short, < VWAP - 2.5*ATR20 -> long); entry at bar k+1's "
    "open; bar k+1 must be in the SAME session (a signal on the session's last bar is not taken - the text also says flat at the "
    "session's last bar).",
    "stop and target distances use ATR20 of the signal bar k, fixed for the trade, measured from the ENTRY price (k+1's open).",
    "intrabar checks start ON the entry bar k+1 (its high/low after the open); on every later bar a gap through a level books "
    "that bar's open (stop gap or target gap); if stop and target are both touched inside one bar the STOP wins (the text gives "
    "no order; stop-first is the conservative reading).",
    "flat at the session's last bar = exit at that bar's CLOSE if neither level was hit (levels are still checked intrabar on the "
    "last bar first).",
    "one trade per session: the first bar k whose close crosses a band is the only entry of that day; after the exit nothing "
    "re-enters that day; signals while in the trade are ignored.",
    "1 contract, no ML, no other filter; the window and master are the prereg's (2010-06-07..2016-06-30, NOADJ_NQ_5m_RTH.csv).",
]


def own_rule(o, h, l, c, day_id, warm_in_session=False):
    """Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]. Uses only bars <= k for the signal and the levels,
    and bar j's open/high/low/close only while bar j is being traded (no look-ahead).
    warm_in_session=True is the ALTERNATIVE reading (k counted from session_start: k - session_start >= 25), a sensitivity only."""
    n = len(c)
    rng = h - l
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    out = []
    for s, e in zip(starts, ends):
        csum = 0.0
        for k in range(s, e):
            csum += c[k]                                     # running sum of close[session_start..k]
            if warm_in_session:
                if k - s < 25:
                    continue
            elif k < 25:
                continue
            if k + 1 >= e:                                   # entry bar must be in the same session
                break
            vw = csum / (k - s + 1)
            atr = rng[k - 19:k + 1].mean()
            if c[k] > vw + 2.5 * atr:
                side = -1
            elif c[k] < vw - 2.5 * atr:
                side = 1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * 1.0 * atr
            tgt = ep + side * 1.5 * atr
            xb, xp = e - 1, c[e - 1]                         # default: flat at the session's last bar close
            for j in range(ent, e):
                if j > ent:                                  # gap through a level books this bar's open
                    if side * (o[j] - stop) <= 0:
                        xb, xp = j, o[j]
                        break
                    if side * (o[j] - tgt) >= 0:
                        xb, xp = j, o[j]
                        break
                stop_hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
                tgt_hit = (h[j] >= tgt) if side > 0 else (l[j] <= tgt)
                if stop_hit:                                 # stop first when both inside one bar
                    xb, xp = j, stop
                    break
                if tgt_hit:
                    xb, xp = j, tgt
                    break
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
            break                                            # one trade per session
    return out


# ---------------------------------------------------------------------------------------------------------------------------
# yardstick
# ---------------------------------------------------------------------------------------------------------------------------
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
            "dd5_n": int(r["n"]), "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts_gross = np.asarray(pts_gross, float)
    usd = (pts_gross - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    assert abs(s.sum() - usd.sum()) < 1e-6, "a trade exit day fell outside the session calendar"
    f = four(s.to_numpy(), days)
    f.update({"cost_pts": float(cost), "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "gross_win_rate": float((pts_gross > 0).mean()) if len(usd) else float("nan"),
              "net_per_trade_pts": float(usd.mean() / MULT) if len(usd) else float("nan"),
              "net_per_trade_usd": float(usd.mean()) if len(usd) else float("nan"),
              "gross_pts_total": float(pts_gross.sum()),
              "avg_win_loss_usd": [float(usd[usd > 0].mean()) if (usd > 0).any() else float("nan"),
                                   float(-usd[usd <= 0].mean()) if (usd <= 0).any() else float("nan")]})
    return f


def arm(exit_bars, pts, idxn, days):
    return {"house_cost": score(exit_bars, pts, idxn, days, COST),
            "real_cost": score(exit_bars, pts, idxn, days, REAL_COST),
            "stress_cost": score(exit_bars, pts, idxn, days, STRESS_COST)}


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_FULL
    assert plugin_pin_ok, "plugin pin %s" % pin
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res = {"idea": "QL_VWAPREVERT_NQ", "idea_folder": IDEA, "run": "second run, plugin v2",
           "plugin": PLUGIN, "plugin_lf_sha256": pin, "plugin_pin_ok": bool(plugin_pin_ok), "prereg": PREREG,
           "prereg_lf_sha256": lf_sha(PREREG),
           "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "bars": int(len(c)), "fingerprint": A.get("fingerprint"), "window": [str(days[0].date()), str(days[-1].date())],
           "sessions": int(len(days)), "first_bar": str(idx[0]), "last_bar": str(idx[-1]),
           "costs_pts": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT,
           "booking": "$ on the exit session (ET date), zero days kept, calendar = every session of the master in the window",
           "own_rule_reading": READING}
    # ---- ARM B (own rule)
    B = own_rule(o, h, l, c, day_id)
    res["B_own_rule"] = arm([t[1] for t in B], [t[5] for t in B], idxn, days)
    res["B_own_rule"]["exits"] = _exit_mix(B, day_id, idxn)
    Balt = own_rule(o, h, l, c, day_id, warm_in_session=True)
    alt = score([t[1] for t in Balt], [t[5] for t in Balt], idxn, days, COST)
    res["B_alt_reading_warmup_in_session"] = {"note": "sensitivity only: k - session_start >= 25 instead of global k >= 25",
                                              "trades": alt["trades"], "trades_per_yr": alt["trades_per_yr"],
                                              "roc30_house": alt["roc30"], "net_usd_house": alt["net_usd"],
                                              "one_episode_house": alt["one_episode"]}
    # ---- ARM A (plugin through the engine)
    m = types.ModuleType("ttm_ql_vwaprevert_v2")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # (entry, exit, side, entry_px, gross)
    res["A_plugin"] = arm([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["gross_pts_sum_from_trades"] = float(sum(t[4] for t in Ta))
    res["A_plugin"]["trade_tuple_len"] = int(len(T[0])) if T else 0
    res["A_plugin"]["exits"] = _exit_mix([(t[0], t[1], t[2], t[3], None, t[4]) for t in Ta], day_id, idxn)
    # ---- diff
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    same_entry_px = sum(1 for k in both if abs(ka[k][3] - kb[k][3]) < 1e-9)
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both),
                     "same_entry_px": same_entry_px, "same_exit_bar": same_exit, "same_gross_pts": same_pts,
                     "exact_same_exit_and_pts": exact, "only_A": len(set(ka) - set(kb)), "only_B": len(set(kb) - set(ka)),
                     "same_entry_bar_opposite_side": len({k[0] for k in ka} & {k[0] for k in kb}) - len(both),
                     "gross_pts_diff_on_matched_sum": float(sum(ka[k][4] - kb[k][5] for k in both)),
                     "first_only_A": [[str(idxn[k[0]]), k[1], ka[k][4]] for k in sorted(set(ka) - set(kb))[:8]],
                     "first_only_B": [[str(idxn[k[0]]), k[1], kb[k][5]] for k in sorted(set(kb) - set(ka))[:8]],
                     "first_exit_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:8]}
    # where each unmatched trade comes from: signal bar k (global), its place in the session, the session's bar count
    sess_len = np.bincount(day_id)
    sess_start = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]

    def _why(entry_bar):
        k = entry_bar - 1
        d = int(day_id[entry_bar])
        return {"entry": str(idxn[entry_bar]), "signal_bar_global_k": int(k), "signal_bar_in_session": int(k - sess_start[d]),
                "session_bars": int(sess_len[d])}
    res["A_vs_B"]["unmatched_detail"] = {"only_A": [_why(k[0]) for k in sorted(set(ka) - set(kb))],
                                         "only_B": [_why(k[0]) for k in sorted(set(kb) - set(ka))]}
    res["A_vs_B"]["unmatched_gross_pts"] = {"only_A": float(sum(ka[k][4] for k in set(ka) - set(kb))),
                                            "only_B": float(sum(kb[k][5] for k in set(kb) - set(ka)))}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    data = (s + "\n").encode("utf-8")
    with open(os.path.join(OUT, "ttm_verify.json"), "wb") as fh:
        fh.write(data)
    print(s)
    print("output sha256", hashlib.sha256(data).hexdigest())


def _exit_mix(tr, day_id, idxn):
    """Count exits by kind, from bar positions only: same-session-last-bar vs earlier; hold in bars."""
    if not tr:
        return {}
    ends = {}
    for i, d in enumerate(day_id):
        ends[int(d)] = i
    last = sum(1 for t in tr if t[1] == ends[int(day_id[t[1]])])
    hold = np.array([t[1] - t[0] for t in tr], float)
    cross = sum(1 for t in tr if day_id[t[0]] != day_id[t[1]])
    return {"exit_on_session_last_bar": int(last), "exit_before_last_bar": int(len(tr) - last),
            "cross_session_trades": int(cross), "hold_bars_median": float(np.median(hold)),
            "hold_bars_mean": float(hold.mean()), "longs": int(sum(1 for t in tr if t[2] > 0)),
            "shorts": int(sum(1 for t in tr if t[2] < 0))}


if __name__ == "__main__":
    main()
