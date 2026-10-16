"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_GAMMA_MOM PRE-WF Stage A (idea folder 20261015-1212-shelf30).
Built from C:/EdgeLog/qwen_lab/ideas/20261015-1212-shelf30/QL_GAMMA_MOM_2026-10-15.md and the plugin file only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read
until this output's sha256 is posted.
(B) TTM's OWN implementation of the prereg's Mechanism text (written BEFORE the plugin code was read);
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 cb3017465f33... = the prereg's hash) through the engine on the pinned master;
trade-for-trade diff A vs B. Both scored by TTM's own booking: $ on the exit session, zero days kept; ROC@30k, DD5, DD% from
peak, Sortino; house cost 0.533 pt, real cost 0.7825 pt, stress (house + 0.5 pt).
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1212-shelf30/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1212-shelf30"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261015-1212-shelf30/plugin_v1.py.txt"
PIN_PREFIX = "cb3017465f33"
PIN_FULL = "cb3017465f3309d49616364cb722b0f76509e8f5036ea416fb945b2894214ceb"   # the prereg's Hashes line
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side over house cost

OWN_RULE_READING = [
    "opening range (OR) = the session's first 6 bars of the master (positional, by day_id), OR high = max(high), OR low = min(low), range = OR high - OR low",
    "'trailing 20-session median range' = median of the OR ranges (same 6-bar quantity) of the 20 PRIOR sessions, today excluded; sessions with < 20 prior sessions in the loaded window do not trade (no warm-up outside the window)",
    "wide-range day = range > 1.5 x that median (strict >)",
    "breakout search starts at the 7th bar (first bar after the OR); signal = first bar whose close > OR high (long) or close < OR low (short), strict; whichever side comes first is the session's only signal",
    "entry = next bar's open; the signal bar must not be the session's last bar (the entry bar must be in the same session); if the first breakout is on the last bar there is no trade",
    "stop = entry fill price -/+ 1.0 x OR range (distance measured from the fill, not from the range edge); no target",
    "stop checked intrabar from the entry bar on (low <= stop long / high >= stop short fills AT the stop); a later bar that OPENS beyond the stop fills at its open (gap-through books the open)",
    "otherwise flat at the close of the session's last bar",
    "one trade per session; no re-entry after a stop",
]


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def own_rule(o, h, l, c, day_id):
    """The prereg's Mechanism, written from its text (see OWN_RULE_READING). Uses only bars <= the signal bar for the signal and
    the entry bar's open for the fill. Returns (entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    ranges = []
    out = []
    for s, e in zip(starts, ends):
        if e - s < 6:
            ranges.append(np.nan)          # a session shorter than the OR has no OR
            continue
        orh = float(h[s:s + 6].max())
        orl = float(l[s:s + 6].min())
        rng = orh - orl
        prior = ranges[-20:]
        ranges.append(rng)
        if len(prior) < 20 or np.any(np.isnan(prior)):
            continue
        med = float(np.median(prior))
        if not rng > 1.5 * med:
            continue
        side = 0
        k = s + 6
        while k < e:
            if c[k] > orh:
                side = 1
                break
            if c[k] < orl:
                side = -1
                break
            k += 1
        if side == 0 or k >= e - 1:        # no breakout, or breakout on the last bar (no next bar in session)
            continue
        ent = k + 1
        ep = float(o[ent])
        stop = ep - side * 1.0 * rng
        xb, xp = e - 1, float(c[e - 1])
        for j in range(ent, e):
            if j > ent and side * (o[j] - stop) <= 0:
                xb, xp = j, float(o[j])
                break
            hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
            if hit:
                xb, xp = j, float(stop)
                break
        out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep))))
    return out


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net_usd": float(x.sum()), "per_yr": float(x.sum()) / yrs, "years": yrs, "max_dd": mdd,
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"), "dd5": float(r["dd5_usd"]),
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    usd = (np.asarray(pts_gross, float) - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, dtype=np.int64)].normalize()).groupby(level=0).sum()
    s = s.reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"cost_pts": cost, "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "avg_win_loss": [float(usd[usd > 0].mean()) if (usd > 0).any() else float("nan"),
                               float(-usd[usd <= 0].mean()) if (usd <= 0).any() else float("nan")]})
    return f


def three_costs(xb, pts, idxn, days):
    return {"house_cost": score(xb, pts, idxn, days, COST), "real_cost": score(xb, pts, idxn, days, REAL_COST),
            "stress_cost": score(xb, pts, idxn, days, STRESS_COST)}


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_FULL
    assert plugin_pin_ok, "plugin pin"
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    assert days[-1] < pd.Timestamp("2016-07-01"), "window must end before the WF start"
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    assert np.all(np.diff(day_id) >= 0), "day_id must be non-decreasing (session index = day_id)"
    res = {"idea": "QL_GAMMA_MOM", "folder": "20261015-1212-shelf30", "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": A.get("fingerprint"), "bars": len(c), "window": [str(days[0].date()), str(days[-1].date())],
           "sessions": len(days), "plugin_lf_sha256": pin, "plugin_pin_ok": bool(plugin_pin_ok),
           "own_rule_reading": OWN_RULE_READING,
           "costs_pts": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT}

    # ARM B: own rule
    B = own_rule(o, h, l, c, day_id)
    res["B_own_rule"] = three_costs([t[1] for t in B], [t[5] for t in B], idxn, days)

    # ARM A: the plugin through the engine
    m = types.ModuleType("ttm_ql_gamma_mom")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # entry, exit, side, entry_px, gross pts
    res["A_plugin"] = three_costs([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["sum_gross_pts"] = float(sum(t[4] for t in Ta))
    res["B_own_rule"]["sum_gross_pts"] = float(sum(t[5] for t in B))

    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both),
                     "only_A": len(set(ka) - set(kb)), "only_B": len(set(kb) - set(ka)),
                     "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
                     "first_only_A": [[str(idxn[k[0]]), k[1], ka[k][4]] for k in sorted(set(ka) - set(kb))[:5]],
                     "first_only_B": [[str(idxn[k[0]]), k[1], kb[k][5]] for k in sorted(set(kb) - set(ka))[:5]],
                     "first_exit_diffs": [[str(idxn[k[0]]), str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5]}
    # why each plugin-only trade exists (diagnosed AFTER the diff, from the same arrays): session index / OR range / median
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(c)]
    rngs = np.array([h[a:a + 6].max() - l[a:a + 6].min() if b - a >= 6 else np.nan for a, b in zip(starts, ends)])
    why = []
    for k in sorted(set(ka) - set(kb)):
        si = int(day_id[k[0]])
        prior = rngs[max(0, si - 20):si]
        med = float(np.median(prior))
        reason = ("warm-up: plugin trades with only %d prior sessions (its fallback median over >= 5); prereg says trailing 20" % si
                  if si < 20 else
                  ("tie: range == 1.5 x median exactly; plugin skips only range < 1.5 x median (>=), own rule needs strict >"
                   if abs(rngs[si] - 1.5 * med) < 1e-9 else "other"))
        why.append([str(idxn[k[0]].date()), si, float(rngs[si]), med, reason, ka[k][4]])
    res["A_vs_B"]["only_A_reasons"] = why
    res["A_vs_B"]["only_A_gross_pts_sum"] = float(sum(ka[k][4] for k in set(ka) - set(kb)))
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    path = os.path.join(OUT, "ttm_verify.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(s + "\n")
    print("output", path, "sha256", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
