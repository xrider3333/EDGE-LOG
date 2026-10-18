"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_VOLBREAK_NQ (folder 20261017-1607-scalper) PRE-WF Stage A.
Built from C:/EdgeLog/qwen_lab/ideas/20261017-1607-scalper/QL_VOLBREAK_NQ_2026-10-17.md (prereg) and plugin_v3.py.txt only;
the lab's numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / idea.json /
tools/qwen_lab.py are NOT read until this output's sha256 is posted to MANAGER.
(B) TTM's OWN implementation of the prereg's 'Mechanism' text, written and frozen BEFORE the plugin code was read
    (own_rule source sha256 in b_frozen_before_plugin_read.sha256.txt);
(A) the plugin AS RUN (plugin_v3.py.txt, LF sha256 c143c7f4b7f9... = the prereg's hash) through the engine on the pinned master;
trade-for-trade diff A vs B by (entry_bar, side), then exit bar / gross pts.
Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5, DD% from peak, Sortino;
at house cost 0.783 pt, real cost 0.7825 pt ($5.65 + 1 tick each side) and a +1-tick-each-side stress (house + 0.5 pt), x $20/pt.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1607-scalper/."""
import hashlib
import inspect
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1607-scalper"
OUT_JSON = os.path.join(OUT, "ttm_verify.json")
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1607-scalper"
PLUGIN = IDEA + "/plugin_v3.py.txt"
PREREG = IDEA + "/QL_VOLBREAK_NQ_2026-10-17.md"
PIN_PREFIX = "c143c7f4b7f9"
PIN_FULL_PREREG = "c143c7f4b7f9455b1479651be2eac238a5c0b1df3f366c9a34f20a08510549b9"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
MULT = 20.0
HOUSE_COST = 0.783
REAL_COST = 0.25 * 2 + 5.65 / MULT       # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = HOUSE_COST + 0.5           # +1 tick each side on top of the house cost (short-hold scalper)
COSTS = {"house_cost": HOUSE_COST, "real_cost": REAL_COST, "stress_cost": STRESS_COST}

# --- TTM's reading of the prereg Mechanism (fixed BEFORE the plugin code was read) ---------------------------------------
BLIND_WIDE_K = 1.5    # the text names the knob wide_k but gives NO value; TTM's blind pick (a 'wide day' = 1.5x the median)
BLIND_TRAIL_K = 2.0   # the text names the knob trail_k but gives NO value; TTM's blind pick (a 2-ATR trail)
OWN_RULE_READING = [
    "bars: NOADJ_NQ_5m_RTH.csv registry row, window 2010-06-07..2016-06-30 (ET dates); session = the master's day_id (ET day).",
    "in-session bar index = the prereg's convention (TTM #145): clock of the bar's OPEN, (minutes since 09:30)/5; bar 0 = 09:30.",
    "morning range = max(high) - min(low) over the session's bars 0..11 (opens 09:30..10:25, complete at 10:30 = 'high[0:12]'); "
    "a session with no bar in that clock span has no morning range (cannot qualify, not counted in later medians).",
    "trailing median = median of the morning ranges of the 20 PREVIOUS sessions (today excluded: 'trailing'); all 20 required, so "
    "the first 20 sessions of the window cannot qualify. Qualify iff morning range >= wide_k x trailing median (>=).",
    "ATR(14) 'computed on 5m closes': per-bar input = |close[i] - close[i-1]| (closes only, no high/low true range); Wilder "
    "smoothing ATR_i = (13 ATR_{i-1} + |dC_i|)/14; RESET each session (the text's k >= 14 is an in-session index, i.e. the ATR "
    "warm-up); seed = the mean |dC| over the session's first 14 closes (bars 0..13, 13 differences), value at bar 13; atr_k at "
    "bar k >= 14 includes bar k's own |dC_k| (the value 'at' bar k, known at its close).",
    "signal on a qualifying session: the first bar k with in-session index >= 14 and close[k] > close[k-1] + atr_k (long) or "
    "close[k] < close[k-1] - atr_k (short), strict; k+1 must exist inside the same session (a last-bar signal is dropped).",
    "entry = open of bar k+1 (the next bar in the session).",
    "stop: initial = entry - side x trail_k x atr_k (atr_k = the SIGNAL bar's ATR, as written, fixed for the trade); checked "
    "intrabar from the entry bar on (long: low <= stop, short: high >= stop) and fills at the stop; a bar after the entry bar that "
    "OPENS at/through the stop fills at its open; after the check, at each bar's close the stop trails: long stop = "
    "max(stop, close - trail_k x atr_k), short stop = min(stop, close + trail_k x atr_k) (ratchet only, never loosens).",
    "no target; flat at the session's last bar CLOSE if not stopped (the stop is checked on the last bar first).",
    "one trade per session: the first qualifying signal only; no re-entry that session.",
    "pts gross = side x (exit - entry); cost subtracted per trade afterwards; $ booked on the exit bar's ET date.",
    "knob values: the prereg's Data section says 'params = the file's DEFAULT_PARAMS defaults'; the Mechanism gives no wide_k / "
    "trail_k values, so B was frozen with blind picks wide_k 1.5, trail_k 2.0 (+ a grid), then, AFTER freezing and BEFORE reading "
    "the plugin's logic, only the plugin's DEFAULT_PARAMS literal was read and B re-run at those values (the B row diffed vs A).",
]


def session_bounds(day_id):
    n = len(day_id)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    return starts, ends


def own_atr(c, h, l, starts, ends, atr_n=14, atr_input="close_abs", atr_scope="session", seed_mode="closes14"):
    """Wilder ATR per TTM's reading. atr_input: 'close_abs' (|dC|) or 'true_range'; atr_scope: 'session' (reset each session)
    or 'global' (one series over the whole load); seed_mode: 'closes14' (seed from the first 14 closes = 13 diffs, value at
    bar 13) or 'diffs14' (seed = mean of the first 14 diffs, value at bar 14). NaN until seeded."""
    n = len(c)
    atr = np.full(n, np.nan)
    segs = list(zip(starts, ends)) if atr_scope == "session" else [(0, n)]
    for s, e in segs:
        if atr_input == "close_abs":
            x = np.full(e - s, np.nan)
            x[1:] = np.abs(np.diff(c[s:e]))
        else:
            pc = np.r_[np.nan, c[s:e - 1]]
            hh, ll = h[s:e], l[s:e]
            x = np.where(np.isnan(pc), hh - ll, np.maximum(hh, pc) - np.minimum(ll, pc))
        if atr_input == "close_abs":
            seed_at = atr_n - 1 if seed_mode == "closes14" else atr_n          # 13 diffs (bars 1..13) or 14 diffs (1..14)
            first = 1
        else:
            seed_at = atr_n - 1 if seed_mode == "closes14" else atr_n
            first = 0 if seed_mode == "closes14" else 1
        if e - s <= seed_at:
            continue
        a = float(np.mean(x[first:seed_at + 1]))
        atr[s + seed_at] = a
        for i in range(seed_at + 1, e - s):
            a = (a * (atr_n - 1) + x[i]) / atr_n
            atr[s + i] = a
    return atr


def own_rule(o, h, l, c, day_id, mins, wide_k=BLIND_WIDE_K, trail_k=BLIND_TRAIL_K, atr_n=14, med_n=20, morning_bars=12,
             k_min=14, atr_input="close_abs", atr_scope="session", seed_mode="closes14", trail_atr="signal",
             med_incl_today=False, index_mode="clock", no_filter=False):
    """The prereg's mechanism, written from its text (see OWN_RULE_READING). Primary = defaults. The keyword knobs only build the
    alternative-reading sensitivity rows. mins = minutes since midnight (ET) of each bar's OPEN.
    Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    starts, ends = session_bounds(day_id)
    if index_mode == "clock":
        sidx = ((mins - 570) // 5).astype(int)
    else:
        sidx = np.empty(len(c), int)
        for s, e in zip(starts, ends):
            sidx[s:e] = np.arange(e - s)
    atr = own_atr(c, h, l, starts, ends, atr_n=atr_n, atr_input=atr_input, atr_scope=atr_scope, seed_mode=seed_mode)
    mr = np.full(len(starts), np.nan)
    for d, (s, e) in enumerate(zip(starts, ends)):
        m = sidx[s:e] < morning_bars
        if m.any():
            mr[d] = float(np.max(h[s:e][m]) - np.min(l[s:e][m]))
    out = []
    hist = []                                            # valid morning ranges of previous sessions, in order
    for d, (s, e) in enumerate(zip(starts, ends)):
        today = mr[d]
        pool = hist[-med_n:] if not med_incl_today else (hist + ([today] if np.isfinite(today) else []))[-med_n:]
        qual = False
        if np.isfinite(today) and len(pool) >= med_n:
            qual = bool(today >= wide_k * float(np.median(pool)))
        if no_filter:
            qual = True
        if np.isfinite(today):
            hist.append(today)
        if not qual:
            continue
        for k in range(s + 1, e - 1):                    # k+1 must exist inside the session
            if sidx[k] < k_min or not np.isfinite(atr[k]):
                continue
            a = atr[k]
            if c[k] > c[k - 1] + a:
                side = 1
            elif c[k] < c[k - 1] - a:
                side = -1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * trail_k * a
            xb, xp = e - 1, c[e - 1]
            for j in range(ent, e):
                if j > ent and side * (o[j] - stop) <= 0:            # opens at/through the stop -> its open
                    xb, xp = j, o[j]
                    break
                if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                    xb, xp = j, stop
                    break
                aj = a if trail_atr == "signal" else (atr[j] if np.isfinite(atr[j]) else a)
                cand = c[j] - side * trail_k * aj
                stop = max(stop, cand) if side > 0 else min(stop, cand)
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
            break                                        # one trade per session
    return out


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
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts = np.asarray(pts_gross, float)
    usd = (pts - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    assert abs(s.sum() - usd.sum()) < 1e-6, "a trade exited off the session calendar"
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "net_per_trade_pts": float(pts.mean() - cost), "net_per_trade_usd": float(usd.mean()),
              "gross_per_trade_pts": float(pts.mean()), "cost_pts": float(cost), "gross_over_cost": float(pts.mean() / cost),
              "avg_win_loss_usd": [float(usd[usd > 0].mean()) if (usd > 0).any() else float("nan"),
                                   float(-usd[usd <= 0].mean()) if (usd <= 0).any() else float("nan")]})
    return f


def score_all(exit_bars, pts, idxn, days):
    return {k: score(exit_bars, pts, idxn, days, v) for k, v in COSTS.items()}


def hold_stats(entry_bars, exit_bars, sidx):
    eb = np.asarray(entry_bars, int)
    hb = np.asarray(exit_bars, int) - eb
    return {"bars_held_mean_exit_minus_entry": float(hb.mean()), "bars_held_median": float(np.median(hb)),
            "minutes_held_median": float(np.median(hb) * 5 + 5),
            "earliest_entry_session_bar": int(sidx[eb].min()), "entries_before_bar15": int((sidx[eb] < 15).sum()),
            "longs": None, "exit_on_session_last_bar": None}


def load():
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    assert idx[-1] < pd.Timestamp("2016-07-01", tz="US/Eastern"), "window must end before the WF start"
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    mins = np.asarray(idxn.hour * 60 + idxn.minute, int)
    return row[0], A, idxn, days, o, h, l, c, np.asarray(A["day_id"]), mins


def b_block(B, idxn, days, sidx, day_id):
    res = score_all([t[1] for t in B], [t[5] for t in B], idxn, days)
    hs = hold_stats([t[0] for t in B], [t[1] for t in B], sidx)
    starts, ends = session_bounds(day_id)
    last = set((ends - 1).tolist())
    hs["longs"] = int(sum(1 for t in B if t[2] > 0))
    hs["exit_on_session_last_bar"] = int(sum(1 for t in B if t[1] in last))
    res.update(hs)
    return res


def arm_b(o, h, l, c, day_id, mins, idxn, days, sidx, wide_k, trail_k, grid=True):
    B = own_rule(o, h, l, c, day_id, mins, wide_k=wide_k, trail_k=trail_k)
    res = b_block(B, idxn, days, sidx, day_id)
    res["knobs"] = {"wide_k": wide_k, "trail_k": trail_k, "atr_n": 14, "med_n": 20}
    alts = {}
    for name, kw in [("atr_true_range", {"atr_input": "true_range"}),
                     ("atr_global_continuous", {"atr_scope": "global"}),
                     ("atr_seed_14_diffs", {"seed_mode": "diffs14"}),
                     ("trail_current_atr", {"trail_atr": "current"}),
                     ("median_incl_today", {"med_incl_today": True}),
                     ("positional_bar_index", {"index_mode": "position"}),
                     ("no_wide_day_filter", {"no_filter": True})]:
        Bx = own_rule(o, h, l, c, day_id, mins, wide_k=wide_k, trail_k=trail_k, **kw)
        sx = score([t[1] for t in Bx], [t[5] for t in Bx], idxn, days, HOUSE_COST)
        alts[name] = {"knobs": kw, "trades": sx["trades"], "trades_per_yr": sx["trades_per_yr"], "roc30_house": sx["roc30"],
                      "net_usd_house": sx["net_usd"], "win_rate_house": sx["win_rate"], "one_episode": sx["one_episode"],
                      "gross_per_trade_pts": sx["gross_per_trade_pts"]}
    res["alt_readings_house_cost"] = alts
    if grid:
        g = {}
        for wk in (1.0, 1.25, 1.5, 2.0):
            for tk in (1.0, 1.5, 2.0, 3.0):
                Bx = own_rule(o, h, l, c, day_id, mins, wide_k=wk, trail_k=tk)
                sx = score([t[1] for t in Bx], [t[5] for t in Bx], idxn, days, HOUSE_COST)
                g["wide_k=%s,trail_k=%s" % (wk, tk)] = {"trades": sx["trades"], "trades_per_yr": sx["trades_per_yr"],
                                                         "roc30_house": sx["roc30"], "net_usd_house": sx["net_usd"],
                                                         "gross_per_trade_pts": sx["gross_per_trade_pts"],
                                                         "win_rate_house": sx["win_rate"]}
        res["knob_grid_house_cost"] = g
    return B, res


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_FULL_PREREG
    assert plugin_pin_ok, "plugin pin"
    row, A, idxn, days, o, h, l, c, day_id, mins = load()
    sidx = ((mins - 570) // 5).astype(int)
    starts, ends = session_bounds(day_id)
    res = {"idea": "QL_VOLBREAK_NQ", "folder": IDEA, "prereg": PREREG, "prereg_lf_sha256": lf_sha(PREREG),
           "plugin": PLUGIN, "plugin_lf_sha256": pin, "plugin_pin_ok": bool(plugin_pin_ok),
           "master": MASTER, "registry_id": row.get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "bars": int(len(c)), "window": [str(days[0].date()), str(days[-1].date())], "sessions": int(len(days)),
           "first_bar": str(idxn[0]), "last_bar": str(idxn[-1]),
           "sessions_first_bar_not_0930": int(sum(1 for s in starts if mins[s] != 570)),
           "sessions_with_bar_holes": int(sum(1 for s, e in zip(starts, ends) if (sidx[e - 1] - sidx[s] + 1) != (e - s))),
           "costs_pts": COSTS, "mult_usd_per_pt": MULT,
           "own_rule_reading": OWN_RULE_READING,
           "own_rule_source_sha256": hashlib.sha256((inspect.getsource(own_rule) + inspect.getsource(own_atr)).encode()).hexdigest()}
    B0, res["B_own_rule_blind_knobs"] = arm_b(o, h, l, c, day_id, mins, idxn, days, sidx, BLIND_WIDE_K, BLIND_TRAIL_K)
    if os.environ.get("TTM_ARM_B_ONLY") == "1":
        print(json.dumps(res, indent=1, sort_keys=True, default=float))
        return
    # --- ARM A: the plugin through the engine --------------------------------------------------------------------------------
    m = types.ModuleType("ttm_ql_volbreak_nq")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    dp = dict(getattr(m, "DEFAULT_PARAMS", {}) or {})
    res["plugin_default_params"] = {k: (v if isinstance(v, (int, float, str, bool)) else str(v)) for k, v in dp.items()}
    wk, tk = float(dp.get("wide_k", BLIND_WIDE_K)), float(dp.get("trail_k", BLIND_TRAIL_K))
    B, res["B_own_rule"] = arm_b(o, h, l, c, day_id, mins, idxn, days, sidx, wk, tk, grid=False)
    res["B_own_rule"]["note"] = "TTM's frozen own_rule at the plugin's DEFAULT_PARAMS knob values (the prereg defers values to the file)"
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # (entry, exit, side, entry_px, gross pts)
    res["A_plugin"] = score_all([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    hs = hold_stats([t[0] for t in Ta], [t[1] for t in Ta], sidx)
    hs["longs"] = int(sum(1 for t in Ta if t[2] > 0))
    hs["exit_on_session_last_bar"] = int(sum(1 for t in Ta if t[1] in set((ends - 1).tolist())))
    res["A_plugin"].update(hs)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["engine_trade_tuple_len"] = int(len(T[0])) if T else 0
    res["A_plugin"]["sum_gross_pts"] = float(sum(t[4] for t in Ta))
    meta = r.get("_meta", {}) or {}
    res["A_plugin"]["engine_meta_roll_stamp"] = str(meta.get("roll_stamp"))[:400] if meta.get("roll_stamp") is not None else None
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    a_days = {idxn[t[0]].normalize() for t in Ta}
    b_days = {idxn[t[0]].normalize() for t in B}
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both),
                     "only_A": len(set(ka) - set(kb)), "only_B": len(set(kb) - set(ka)),
                     "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact_same_exit_and_pts": exact,
                     "sessions_traded_A": len(a_days), "sessions_traded_B": len(b_days),
                     "sessions_traded_both": len(a_days & b_days),
                     "first_only_A": [[str(idxn[k[0]]), k[1]] for k in sorted(set(ka) - set(kb))[:8]],
                     "first_only_B": [[str(idxn[k[0]]), k[1]] for k in sorted(set(kb) - set(ka))[:8]],
                     "first_exit_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:8]}
    post = globals().get("post_read_checks")
    if post is not None:
        res.update(post(o, h, l, c, day_id, mins, idxn, days, sidx, Ta, ka, m))
    s = json.dumps(res, indent=1, sort_keys=True, default=float) + "\n"
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print(s)
    print("output", OUT_JSON, "sha256", hashlib.sha256(open(OUT_JSON, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
