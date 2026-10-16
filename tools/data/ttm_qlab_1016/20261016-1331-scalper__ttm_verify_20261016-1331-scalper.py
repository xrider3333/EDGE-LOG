"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_NOISE2M_TREND (folder 20261016-1331-scalper) PRE-WF Stage A.
Built from C:/EdgeLog/qwen_lab/ideas/20261016-1331-scalper/QL_NOISE2M_TREND_2026-10-16.md (prereg) and plugin_v1.py.txt only;
the lab's numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT
read until this output's sha256 is posted to MANAGER.
(B) TTM's OWN implementation of the prereg's 'Mechanism' text, written BEFORE the plugin code was read;
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 441a4056706c... = the prereg's hash) through the engine on the pinned master;
trade-for-trade diff A vs B by (entry_bar, side), then exit bar / gross pts.
Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5, DD% from peak, Sortino;
at house cost 0.783 pt, real cost 0.7825 pt ($5.65 + 1 tick each side) and a +1-tick-each-side stress (house + 0.5 pt), x $20/pt.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-1331-scalper/."""
import hashlib
import inspect
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-1331-scalper"
OUT_JSON = os.path.join(OUT, "ttm_verify.json")
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261016-1331-scalper"
PLUGIN = IDEA + "/plugin_v1.py.txt"
PREREG = IDEA + "/QL_NOISE2M_TREND_2026-10-16.md"
PIN_PREFIX = "441a4056706c"
PIN_FULL_PREREG = "441a4056706cc78b514f0c3babee1dbb65fd03469869c0aa5604f703674b3508"
MASTER, D0, D1 = "NOADJ_NQ_2m_RTH.csv", "2010-06-07", "2016-06-30"
MULT = 20.0
HOUSE_COST = 0.783
REAL_COST = 0.25 * 2 + 5.65 / MULT       # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = HOUSE_COST + 0.5           # +1 tick each side on top of the house cost (short-hold scalper)
COSTS = {"house_cost": HOUSE_COST, "real_cost": REAL_COST, "stress_cost": STRESS_COST}

# --- TTM's reading of the prereg Mechanism (fixed BEFORE the plugin code was read) ---------------------------------------
OWN_N = 20          # N is not given in the text; TTM picks 20 (house ATR20 convention). Sensitivity N in {10,14,30} reported.
OWN_T = 6           # text: 'default 6 bars = 12 min'
OWN_STOP_MULT = 1.5  # text: 'Stop = 1.5x the band width'
OWN_RULE_READING = [
    "bars: NOADJ_NQ_2m_RTH.csv registry row (id 42), window 2010-06-07..2016-06-30 (ET dates), session = ET calendar day (day_id).",
    "band width w(k) = median of (high - low) over the N bars BEFORE the signal bar k (k-N..k-1), global bars (crosses sessions), N=20 "
    "(N is not stated in the text; 20 picked); no signal until N prior bars exist.",
    "band edges: the text names no centre; TTM centres the trailing band on the PREVIOUS bar's close: upper = close[k-1] + w, "
    "lower = close[k-1] - w ('trailing' = re-anchored every bar). A day-open centre was rejected as primary because the text adds a "
    "separate 'day's trend' filter, which a day-open-centred band would make redundant. The previous bar may be the prior session's "
    "last bar (no session reset stated).",
    "break: close[k] > upper -> up break; close[k] < lower -> down break (strict).",
    "day's trend: close[k] vs the session's first bar open; long needs close[k] > day open, short needs close[k] < day open (strict).",
    "entry at open of bar k+1; k+1 must be in the same session (a signal on the session's last bar is dropped).",
    "stop distance = 1.5 x w(k) (band width at the signal bar) from the entry price, fixed for the trade.",
    "stop: checked intrabar from the entry bar on (low <= stop long / high >= stop short fills at the stop); a bar after the entry bar "
    "that OPENS past the stop fills at its open; within a bar the stop is checked before the time exit.",
    "time stop: exit at the CLOSE of the T-th bar held counting the entry bar (bar k+T, T=6 -> 12 min after the entry open).",
    "flat by the session's last bar: if the time-stop bar is past the session's last bar, exit at the session's last bar close.",
    "one trade per session max: the first qualifying signal only; no further signals that session after it (win or lose).",
    "pts gross = side x (exit - entry); cost subtracted per trade afterwards; $ booked on the exit bar's ET date.",
]


def own_rule(o, h, l, c, day_id, N=OWN_N, T=OWN_T, stop_mult=OWN_STOP_MULT, anchor="prev_close", band_incl_k=False,
             session_reset=False):
    """The prereg's mechanism, written from its text (see OWN_RULE_READING). Primary = defaults. The keyword knobs only build the
    alternative-reading sensitivity rows (anchor in {'prev_close','day_open','median_hl','prev_hl'}, band_incl_k, session_reset).
    Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    n = len(c)
    rng = h - l
    if band_incl_k:
        w_all = pd.Series(rng).rolling(N).median().to_numpy()                 # bars k-N+1..k
        mh_all = pd.Series(h).rolling(N).median().to_numpy()
        ml_all = pd.Series(l).rolling(N).median().to_numpy()
    else:
        w_all = pd.Series(rng).rolling(N).median().shift(1).to_numpy()        # bars k-N..k-1
        mh_all = pd.Series(h).rolling(N).median().shift(1).to_numpy()
        ml_all = pd.Series(l).rolling(N).median().shift(1).to_numpy()
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        day_open = o[s]
        k0 = s + N if session_reset else s
        k0 = max(k0, 1)
        for k in range(k0, e - 1):                       # k+1 must exist inside the session
            if session_reset:
                w = float(np.median(rng[k - N + (1 if band_incl_k else 0):k + (1 if band_incl_k else 0)]))
            else:
                w = w_all[k]
            if not np.isfinite(w) or w <= 0:
                continue
            if anchor == "prev_close":
                if session_reset and k == s:
                    continue
                up, dn = c[k - 1] + w, c[k - 1] - w
            elif anchor == "day_open":
                up, dn = day_open + w, day_open - w
            elif anchor == "median_hl":
                up, dn = mh_all[k], ml_all[k]
                w = up - dn
                if not (np.isfinite(w) and w > 0):
                    continue
            elif anchor == "prev_hl":
                up, dn = h[k - 1] + w, l[k - 1] - w
            else:
                raise ValueError(anchor)
            if c[k] > up and c[k] > day_open:
                side = 1
            elif c[k] < dn and c[k] < day_open:
                side = -1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * stop_mult * w
            last = min(ent + T - 1, e - 1)
            xb, xp = last, c[last]
            for j in range(ent, last + 1):
                if j > ent and side * (o[j] - stop) <= 0:          # opens past the stop -> its open
                    xb, xp = j, o[j]
                    break
                hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
                if hit:
                    xb, xp = j, stop
                    break
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
            break                                                   # one trade per session
    return out


def replica_of_plugin_reading(o, h, l, c, day_id, bb=12, sm=1.5, mh=6):
    """WRITTEN AFTER the plugin was read (not part of the blind Arm B): TTM's own re-coding of the PLUGIN's reading of the text,
    to check that the engine path (roll handling, arrays, trade tuples) does not change the plugin's trades. Plugin choices:
    band window = the bb bars ENDING at the signal bar k (k-bb+1..k), inside the session only (k >= session start + bb, sessions
    of <= bb+3 bars skipped); band = median(close over the window) +/- 0.5 x median(high-low over the window); day trend =
    close[k] vs the session's first open; entry open[k+1] with k <= session end - 3; stop = 1.5 x width, gap-through books the
    open; time exit at the CLOSE of bar entry+mh (7 bars counting the entry bar), capped at the session's last bar."""
    n = len(c)
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for a, b in zip(starts, ends):
        if b - a <= bb + 3:
            continue
        for k in range(a + bb, b - 2):
            w = float(np.median(h[k - bb + 1:k + 1] - l[k - bb + 1:k + 1]))
            if w <= 0:
                continue
            ctr = float(np.median(c[k - bb + 1:k + 1]))
            tr = np.sign(c[k] - o[a])
            if tr > 0 and c[k] > ctr + 0.5 * w:
                side = 1
            elif tr < 0 and c[k] < ctr - 0.5 * w:
                side = -1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * sm * w
            last = min(ent + mh, b - 1)
            xb, xp = last, c[last]
            for j in range(ent, last + 1):
                if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                    xb, xp = j, (o[j] if side * (o[j] - stop) < 0 else stop)
                    break
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
            break
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
              "gross_per_trade_pts": float(pts.mean()), "cost_pts": float(cost),
              "avg_win_loss_usd": [float(usd[usd > 0].mean()) if (usd > 0).any() else float("nan"),
                                   float(-usd[usd <= 0].mean()) if (usd <= 0).any() else float("nan")]})
    return f


def score_all(exit_bars, pts, idxn, days):
    return {k: score(exit_bars, pts, idxn, days, v) for k, v in COSTS.items()}


def hold_stats(entry_bars, exit_bars):
    hb = np.asarray(exit_bars, int) - np.asarray(entry_bars, int) + 1
    return {"bars_held_mean": float(hb.mean()), "bars_held_median": float(np.median(hb)),
            "bars_held_counts": {str(int(v)): int((hb == v).sum()) for v in np.unique(hb)}}


def load():
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    assert idx[-1] < pd.Timestamp("2016-07-01", tz="US/Eastern"), "window must end before the WF start"
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    return row[0], A, idxn, days, o, h, l, c, np.asarray(A["day_id"])


def arm_b(o, h, l, c, day_id, idxn, days):
    B = own_rule(o, h, l, c, day_id)
    res = score_all([t[1] for t in B], [t[5] for t in B], idxn, days)
    res.update(hold_stats([t[0] for t in B], [t[1] for t in B]))
    alts = {}
    for name, kw in [("N10", {"N": 10}), ("N14", {"N": 14}), ("N30", {"N": 30}),
                     ("band_incl_signal_bar", {"band_incl_k": True}),
                     ("session_reset_band", {"session_reset": True}),
                     ("anchor_day_open", {"anchor": "day_open"}),
                     ("anchor_median_high_low", {"anchor": "median_hl"}),
                     ("anchor_prev_bar_high_low", {"anchor": "prev_hl"})]:
        Bx = own_rule(o, h, l, c, day_id, **kw)
        sx = score([t[1] for t in Bx], [t[5] for t in Bx], idxn, days, HOUSE_COST)
        alts[name] = {"knobs": kw, "trades": sx["trades"], "trades_per_yr": sx["trades_per_yr"], "roc30_house": sx["roc30"],
                      "net_usd_house": sx["net_usd"], "win_rate_house": sx["win_rate"], "one_episode": sx["one_episode"]}
    return B, res, alts


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_FULL_PREREG
    assert plugin_pin_ok, "plugin pin"
    row, A, idxn, days, o, h, l, c, day_id = load()
    res = {"idea": "QL_NOISE2M_TREND", "folder": IDEA, "prereg": PREREG, "prereg_lf_sha256": lf_sha(PREREG),
           "plugin": PLUGIN, "plugin_lf_sha256": pin, "plugin_pin_ok": bool(plugin_pin_ok),
           "master": MASTER, "registry_id": row.get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "bars": int(len(c)), "window": [str(days[0].date()), str(days[-1].date())], "sessions": int(len(days)),
           "first_bar": str(idxn[0]), "last_bar": str(idxn[-1]),
           "costs_pts": COSTS, "mult_usd_per_pt": MULT,
           "own_rule_reading": OWN_RULE_READING,
           "own_rule_source_sha256": hashlib.sha256(inspect.getsource(own_rule).encode()).hexdigest()}
    B, res["B_own_rule"], res["B_alt_readings_house_cost"] = arm_b(o, h, l, c, day_id, idxn, days)
    if os.environ.get("TTM_ARM_B_ONLY") == "1":
        print(json.dumps(res, indent=1, sort_keys=True, default=float))
        return
    # --- ARM A: the plugin through the engine --------------------------------------------------------------------------------
    m = types.ModuleType("ttm_ql_noise2m_trend")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # (entry, exit, side, entry_px, gross pts)
    res["A_plugin"] = score_all([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"].update(hold_stats([t[0] for t in Ta], [t[1] for t in Ta]))
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["engine_trade_tuple_len"] = int(len(T[0])) if T else 0
    res["A_plugin"]["sum_gross_pts"] = float(sum(t[4] for t in Ta))
    res["A_plugin"]["default_params"] = {k: (v if isinstance(v, (int, float, str, bool)) else str(v))
                                         for k, v in dict(getattr(m, "DEFAULT_PARAMS", {}) or {}).items()}
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
    # --- post-read check: TTM's own re-coding of the plugin's reading vs the engine's trades ---------------------------------
    R = replica_of_plugin_reading(o, h, l, c, day_id)
    kr = {(t[0], t[2]): t for t in R}
    br = sorted(set(ka) & set(kr))
    res["A_replica_post_read"] = {
        "note": "written AFTER reading the plugin; not blind; checks the engine path only",
        "trades": len(R), "same_entry_and_side_as_A": len(br), "only_A": len(set(ka) - set(kr)), "only_replica": len(set(kr) - set(ka)),
        "exact_same_exit_and_pts_as_A": sum(1 for k in br if ka[k][1] == kr[k][1] and abs(ka[k][4] - kr[k][5]) < 1e-6),
        "sum_gross_pts": float(sum(t[5] for t in R)),
        "first_mismatches": [[str(idxn[k[0]]), k[1]] for k in sorted(set(ka) ^ set(kr))[:5]]}
    R5 = replica_of_plugin_reading(o, h, l, c, day_id, mh=5)
    s5 = score([t[1] for t in R5], [t[5] for t in R5], idxn, days, HOUSE_COST)
    res["A_replica_post_read"]["exit_at_text_12min_mh5_house_cost"] = {
        "trades": s5["trades"], "roc30": s5["roc30"], "net_usd": s5["net_usd"], "win_rate": s5["win_rate"],
        "gross_per_trade_pts": s5["gross_per_trade_pts"], "one_episode": s5["one_episode"]}
    res["plugin_vs_text_notes"] = [
        "band lookback band_bars=12 (text gives no N; TTM blind pick was 20)",
        "band centre = median close of the window, edges = centre +/- 0.5 x width (text names no centre; TTM blind pick: previous "
        "close +/- 1.0 x width)",
        "band window includes the signal bar and resets each session (first signal bar = session bar 13)",
        "time stop exits at the close of bar entry+6 = 7 bars counting the entry bar = 14 min after the entry open; the text says "
        "'6 bars = 12 min' (off by one bar vs the text; TTM blind exit = close of bar entry+5)",
        "gap-through-stop books the open (matches the text); flat at the session's last bar (matches); one trade per session (matches)",
    ]
    s = json.dumps(res, indent=1, sort_keys=True, default=float) + "\n"
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print(s)
    print("output", OUT_JSON, "sha256", hashlib.sha256(open(OUT_JSON, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
