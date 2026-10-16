"""TTM (house verifier): BLIND stage-1 re-check of the Qwen Lab's QL_TOM_CALENDAR_NQ PRE-WF Stage A (idea 20261015-1438-shelf34).
Built from C:/EdgeLog/qwen_lab/ideas/20261015-1438-shelf34/QL_TOM_CALENDAR_NQ_2026-10-15.md (prereg) and plugin_v8.py.txt only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read until this
output's sha256 is posted to MANAGER.
(A) the plugin AS RUN (plugin_v8.py.txt, LF sha256 83b2429ee3c2... = the prereg's hash) through the engine on the pinned master, params None;
(B) TTM's OWN implementation of the prereg's Mechanism text (written before the plugin code was opened); trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1438-shelf34/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1438-shelf34"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261015-1438-shelf34"
PLUGIN = IDEA + "/plugin_v8.py.txt"
PIN_PREFIX = "83b2429ee3c2"
PIN_FULL = "83b2429ee3c2e77cfdca2bd7aa81f23b645bbcd32910269e66fe61f349122eea"   # prereg 'Hashes' line
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt

# Sessions the master does NOT hold but the exchange had SCHEDULED (for the ex-ante sensitivity only):
# Hurricane Sandy closures (unscheduled, 2012-10-29/30) and the master's data gaps vs the NYSE calendar.
SCHEDULED_NOT_IN_MASTER = ["2012-10-29", "2012-10-30", "2014-06-12", "2014-06-13", "2014-09-23", "2014-09-24", "2014-09-25",
                           "2014-12-31"]
# NYSE full-day holidays in the window (hand list) - for the NYSE-calendar sensitivity only.
NYSE_HOL = """2010-07-05 2010-09-06 2010-11-25 2010-12-24 2011-01-17 2011-02-21 2011-04-22 2011-05-30 2011-07-04 2011-09-05 2011-11-24
2011-12-26 2012-01-02 2012-01-16 2012-02-20 2012-04-06 2012-05-28 2012-07-04 2012-09-03 2012-10-29 2012-10-30 2012-11-22 2012-12-25
2013-01-01 2013-01-21 2013-02-18 2013-03-29 2013-05-27 2013-07-04 2013-09-02 2013-11-28 2013-12-25 2014-01-01 2014-01-20 2014-02-17
2014-04-18 2014-05-26 2014-07-04 2014-09-01 2014-11-27 2014-12-25 2015-01-01 2015-01-19 2015-02-16 2015-04-03 2015-05-25 2015-07-03
2015-09-07 2015-11-26 2015-12-25 2016-01-01 2016-01-18 2016-02-15 2016-03-25 2016-05-30""".split()


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def sessions(day_id):
    day_id = np.asarray(day_id)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(day_id)]
    return starts, ends


def last3_flags(dates, calendar=None):
    """dates: ET session dates (one per master session, ascending). calendar: the list of session dates that define 'the last 3
    trading days of the month' (default = the master's own day_id session dates, the prereg's literal 'determined by day_id session
    dates'). Returns a bool per master session: True when it is one of its calendar month's last 3 calendar sessions."""
    cal = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(calendar if calendar is not None else dates))))
    ym = cal.year * 12 + cal.month
    rank_from_end = pd.Series(np.ones(len(cal)), index=cal).groupby(np.asarray(ym)).cumsum()
    cnt = pd.Series(np.ones(len(cal)), index=cal).groupby(np.asarray(ym)).transform("sum")
    pick = set(cal[(cnt - rank_from_end).to_numpy() < 3])
    return np.array([pd.Timestamp(d) in pick for d in dates])


def own_rule(o, h, l, c, day_id, dates, calendar=None):
    """The prereg's Mechanism, written from its text (before the plugin code was read):
    on each of the last 3 trading days of each calendar month (calendar = the master's day_id session dates), buy 1 contract at the
    session's FIRST bar's open (09:30 ET bar, start-stamped) and sell at the session's LAST bar's close (15:55 bar = 16:00 ET close on a
    full day; the session's own last bar on a CME half-day). No stop, no target, no intrabar exit; one trade per qualifying session; flat
    overnight and on all other days. Long only. The decision uses only the exchange calendar (session dates), never a price.
    Returns (entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)."""
    starts, ends = sessions(day_id)
    flags = last3_flags(dates, calendar)
    out = []
    for s, e, f in zip(starts, ends, flags):
        if not f:
            continue
        ep, xp = float(o[s]), float(c[e - 1])
        out.append((int(s), int(e - 1), 1, ep, xp, xp - ep))
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


def score(entry_bars, exit_bars, pts_gross, idxn, days, cost):
    usd = (np.asarray(pts_gross, float) - cost) * MULT
    if len(usd) == 0:
        f = four(np.zeros(len(days)), days)
        f.update({"trades": 0, "trades_per_yr": 0.0, "win_rate": float("nan"), "net_pts_per_trade": float("nan"),
                  "net_usd_per_trade": float("nan"), "cost_pts": cost})
        return f
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "net_pts_per_trade": float(usd.mean() / MULT), "net_usd_per_trade": float(usd.mean()), "cost_pts": cost,
              "gross_pts_total": float(np.sum(pts_gross))})
    return f


def arm(entries, exits, pts, idxn, days):
    return {"house_cost": score(entries, exits, pts, idxn, days, COST), "real_cost": score(entries, exits, pts, idxn, days, REAL_COST)}


def main():
    sha = lf_sha(PLUGIN)
    pin_ok = sha.startswith(PIN_PREFIX) and sha == PIN_FULL
    assert pin_ok, "plugin pin"
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    assert idxn[-1] < pd.Timestamp("2016-07-01"), "window end before WF start"
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts, ends = sessions(day_id)
    sdates = idxn[starts].normalize()
    assert len(sdates) == len(days) and (sdates == days).all()
    res = {"idea": "QL_TOM_CALENDAR_NQ", "idea_folder": IDEA, "plugin": PLUGIN, "plugin_lf_sha256": sha, "plugin_pin_ok": bool(pin_ok),
           "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "data_fingerprint": A.get("fingerprint"), "bars": len(c), "window": [str(days[0].date()), str(days[-1].date())],
           "sessions": len(days), "half_day_sessions": int(np.sum((ends - starts) < 78)),
           "cost_house_pts": COST, "cost_real_pts": REAL_COST, "mult": MULT}

    res["own_rule_reading"] = [
        "trading days = the master's own day_id sessions (prereg: 'determined by day_id session dates'), so CME holiday half-sessions "
        "in the master (e.g. Memorial Day, Thanksgiving) COUNT as trading days and a master data gap (2014-12-31) does not",
        "calendar month = ET date of the session's first bar; a session qualifies when fewer than 3 later master sessions share its "
        "year-month (3 per month, 73 months, 219 trades)",
        "entry = open of the session's FIRST bar (the 09:30 start-stamped bar), filled at that open, no signal-bar delay (the decision "
        "is calendar-only, known before the session)",
        "exit = close of the session's LAST bar (15:55 bar = 16:00 ET on full days; the session's own last bar on half-days)",
        "long 1 contract, no stop, no target, no intrabar exit, flat overnight: each of the 3 days is its own trade",
        "the first (partial) month June 2010 and the last month June 2016 both end inside the window, so both get 3 trades",
        "only calendar knowledge is used; the master-session calendar differs from an ex-ante scheduled calendar on 3 trades (Sandy "
        "closure 2012-10-25/26 picked ex-post; 2014-12-26 picked because 2014-12-31 is a data gap) - see B_sensitivity"]

    # ---- ARM B: own rule (literal reading) + two calendar sensitivities
    B = own_rule(o, h, l, c, day_id, sdates)
    res["B_own_rule"] = arm([t[0] for t in B], [t[1] for t in B], [t[5] for t in B], idxn, days)
    cal_exante = sorted(set(sdates) | set(pd.to_datetime(SCHEDULED_NOT_IN_MASTER)))
    Bx = own_rule(o, h, l, c, day_id, sdates, calendar=cal_exante)
    bd = pd.bdate_range(D0, D1)
    cal_nyse = bd[~bd.isin(pd.to_datetime(NYSE_HOL))]
    Bn = own_rule(o, h, l, c, day_id, sdates, calendar=cal_nyse)
    keyB = {t[0] for t in B}
    res["B_sensitivity"] = {
        "exante_scheduled_calendar": {"what": "calendar = master sessions + Sandy closures + master data-gap days (what a trader knew in "
                                      "advance); a picked day the master lacks is skipped",
                                      "trades": len(Bx), "dropped_vs_B": [str(idxn[k].date()) for k in sorted(keyB - {t[0] for t in Bx})],
                                      "added_vs_B": [str(idxn[k].date()) for k in sorted({t[0] for t in Bx} - keyB)],
                                      **{k: {kk: v[kk] for kk in ("roc30", "net_usd", "max_dd", "dd5", "one_episode", "sortino", "trades")}
                                         for k, v in arm([t[0] for t in Bx], [t[1] for t in Bx], [t[5] for t in Bx], idxn, days).items()}},
        "nyse_calendar": {"what": "calendar = NYSE full-day sessions (hand holiday list); CME holiday half-sessions never count",
                          "trades": len(Bn), "dropped_vs_B": [str(idxn[k].date()) for k in sorted(keyB - {t[0] for t in Bn})],
                          "added_vs_B": [str(idxn[k].date()) for k in sorted({t[0] for t in Bn} - keyB)],
                          **{k: {kk: v[kk] for kk in ("roc30", "net_usd", "max_dd", "dd5", "one_episode", "sortino", "trades")}
                             for k, v in arm([t[0] for t in Bn], [t[1] for t in Bn], [t[5] for t in Bn], idxn, days).items()}}}

    # ---- ARM A: the plugin as run, through the engine, file defaults, cost 0 in the engine
    m = types.ModuleType("ttm_ql_tom_calendar")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # (entry_bar, exit_bar, side, entry_px, gross_pts)
    res["A_plugin"] = arm([t[0] for t in Ta], [t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["default_params"] = {k: v for k, v in getattr(m, "DEFAULT_PARAMS", {}).items()} if isinstance(
        getattr(m, "DEFAULT_PARAMS", None), dict) else None
    res["A_plugin"]["trades_list"] = [[str(idxn[t[0]]), str(idxn[t[1]]), t[2], t[3], round(t[4], 6)] for t in Ta]

    # ---- plugin diagnosis (read AFTER arm B was written): the tail test compares pos_in_block (0..bl-1) with the ABSOLUTE block end
    # index minus tl, so only block 0 (window sessions 18..20) can ever qualify; even with that fixed, 21-session blocks from the
    # window start are not calendar months. Shown: the fixed-block intent's trade count and its overlap with arm B.
    bl, tl = 21, 3
    nS = len(starts)
    fixed = [i for i in range(nS) if (i % bl) >= (min((i // bl + 1) * bl, nS) - (i // bl) * bl) - tl and ends[i] - starts[i] >= 2]
    fixed_bars = {int(starts[i]) for i in fixed}
    res["plugin_diagnosis"] = {
        "bug_line": "if pos_in_block >= block_end - tl:   (block_end is an absolute session index; pos_in_block is 0..bl-1)",
        "effect": "only the first 21-session block of the loaded window trades: sessions 18,19,20 -> 3 trades in the whole window",
        "mechanism_mismatch": "even fixed, the plugin uses fixed 21-session blocks counted from the window start, not the prereg's "
                              "calendar month (day_id session dates); blocks drift off month-end",
        "fixed_block_intent_trades": len(fixed), "fixed_block_intent_overlap_with_B": len(fixed_bars & keyB),
        "plugin_versions_v1_v8_same_lf_sha256": len({lf_sha(f"{IDEA}/plugin_v{v}.py.txt") for v in range(1, 9)}) == 1}

    # ---- A vs B
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    # A's entries vs B by SESSION (in case the plugin fills one bar later than the open)
    sess_of = np.repeat(np.arange(len(starts)), ends - starts)
    sa = {int(sess_of[t[0]]) for t in Ta}
    sb = {int(sess_of[t[0]]) for t in B}
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both), "only_A": len(set(ka) - set(kb)),
                     "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
                     "same_entry_session": len(sa & sb), "only_A_sessions": len(sa - sb), "only_B_sessions": len(sb - sa),
                     "first_only_A": [str(idxn[k[0]]) for k in sorted(set(ka) - set(kb))[:8]],
                     "first_only_B": [str(idxn[k[0]]) for k in sorted(set(kb) - set(ka))[:8]],
                     "first_exit_diffs": [[str(idxn[k[0]]), str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:8]}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    with open(os.path.join(OUT, "ttm_verify.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s + "\n")
    print(json.dumps({k: res[k] for k in ("A_vs_B",)}, indent=1, default=float))
    print("output sha256", hashlib.sha256((s + "\n").encode()).hexdigest())


if __name__ == "__main__":
    main()
