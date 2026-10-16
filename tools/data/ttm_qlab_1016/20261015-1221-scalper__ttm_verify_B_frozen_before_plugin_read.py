"""TTM (house verifier): BLIND stage-1 re-check of the Qwen Lab's QL_MOMDRIVE PRE-WF Stage A (idea 20261015-1221-scalper).
Built from C:/EdgeLog/qwen_lab/ideas/20261015-1221-scalper/QL_MOMDRIVE_2026-10-15.md (Mechanism text) and the plugin file only;
the lab's numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are
NOT read until this output's sha256 is posted to MANAGER.
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 8ae66698... = the prereg's hash) through the engine on the pinned master;
(B) TTM's OWN implementation of the prereg's Mechanism text, written BEFORE the plugin code was read (own_rule below);
the only plugin-derived input to B is the compress_k VALUE, read programmatically from the file's DEFAULT_PARAMS because the
prereg says params = the file's DEFAULT_PARAMS and gives no number for compress_k. Trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1221-scalper/."""
import hashlib
import inspect
import itertools
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1221-scalper"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261015-1221-scalper"
PLUGIN = IDEA + "/plugin_v1.py.txt"
PREREG = IDEA + "/QL_MOMDRIVE_2026-10-15.md"
PIN_PREFIX = "8ae666985859"
PIN_PREREG_FULL = "8ae66698585945cd3a61c0d79a58cb406202866865b4c03b045dd642929ea0fa"
MASTER, D0, D1 = "NOADJ_NQ_2m_RTH.csv", "2010-06-07", "2016-06-30"
MULT = 20.0
COST = 0.783                            # house short-hold basis (prereg)
REAL_COST = 0.25 * 2 + 5.65 / MULT      # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt on NQ
STRESS_COST = COST + 0.5                # scalper stress: + 1 tick each side on top of the house cost


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def atr14(h, l, c, true_range=True):
    """ATR(14) at every bar k = simple mean of the last 14 bars' range (bars k-13..k, global, crossing sessions).
    true_range: TR = max(h-l, |h-c[k-1]|, |l-c[k-1]|); else plain h-l. NaN until 14 bars with a prior close exist (k >= 14)."""
    n = len(c)
    rng = h - l
    if true_range:
        pc = np.r_[np.nan, c[:-1]]
        tr = np.fmax(rng, np.fmax(np.abs(h - pc), np.abs(l - pc)))
        tr[0] = rng[0]
    else:
        tr = rng.copy()
    cs = np.r_[0.0, np.cumsum(tr)]
    out = np.full(n, np.nan)
    k = np.arange(14, n)
    out[k] = (cs[k + 1] - cs[k - 13]) / 14.0
    return out


def own_rule(o, h, l, c, day_id, compress_k, true_range=True, stop_atr="current", ratchet=False, or_bars=12, stop_mult=2.0):
    """QL_MOMDRIVE Mechanism, written from the prereg text alone (primary reading = the defaults):
    - session = the master's day_id (RTH 09:30-16:00, 2m start-stamped bars); opening range = session bars 0..11;
      range_high = max(high), range_low = min(low) over them; range = range_high - range_low.
    - quiet iff range <= compress_k x ATR(14) measured at session bar 11 (the opening range's last bar).
    - signal: the FIRST session bar >= 12 (and not the session's last bar) whose CLOSE is > range_high (long) or < range_low
      (short), strict; only in a quiet session. Entry at the next bar's OPEN.
    - chandelier stop for bar j (uses only bars <= j-1): long = (highest close over entry..j-1) - 2 x ATR; short = (lowest close
      over entry..j-1) + 2 x ATR; on the entry bar no close exists yet, so the reference is the entry price.
      ATR = ATR(14) of bar j-1 (stop_atr='current', chandelier-style rolling) or of the signal bar ('signal').
      ratchet=False: the formula as written (may loosen if ATR rises); ratchet=True: the stop never moves against the trade.
    - exit: bar j > entry OPENING through the stop books that open; else a bar trading through the stop books the stop
      (checked from the entry bar on); else the session's last bar close. One trade per session max (no re-entry).
    Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    n = len(c)
    atr = atr14(h, l, c, true_range)
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        if e - s < or_bars + 2:                       # need the opening range, a signal bar and an entry bar
            continue
        k_or = s + or_bars - 1
        a_or = atr[k_or]
        if not np.isfinite(a_or):
            continue
        rh = h[s:k_or + 1].max()
        rl = l[s:k_or + 1].min()
        if not (rh - rl <= compress_k * a_or):
            continue
        sig, side = -1, 0
        for k in range(k_or + 1, e - 1):              # the entry bar k+1 must be in the same session
            if c[k] > rh:
                sig, side = k, 1
                break
            if c[k] < rl:
                sig, side = k, -1
                break
        if sig < 0:
            continue
        ent = sig + 1
        ep = o[ent]
        a_sig = atr[sig]
        ref = ep
        stop_prev = None
        xb, xp = e - 1, c[e - 1]
        for j in range(ent, e):
            a = atr[j - 1] if stop_atr == "current" else a_sig
            stop = ref - side * stop_mult * a
            if ratchet and stop_prev is not None:
                stop = max(stop, stop_prev) if side > 0 else min(stop, stop_prev)
            stop_prev = stop
            if j > ent and side * (o[j] - stop) <= 0:
                xb, xp = j, o[j]
                break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, stop
                break
            ref = c[j] if j == ent else (max(ref, c[j]) if side > 0 else min(ref, c[j]))
        out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
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
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else None, "dd5": float(r["dd5_usd"]),
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else None}


def score(exit_bars, pts_gross, idxn, days, cost):
    usd = (np.asarray(pts_gross, float) - cost) * MULT
    if len(usd) == 0:
        return {"trades": 0}
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "avg_win_usd": float(usd[usd > 0].mean()) if (usd > 0).any() else None,
              "avg_loss_usd": float(-usd[usd <= 0].mean()) if (usd <= 0).any() else None,
              "cost_pts": cost})
    return f


def three(xb, pts, idxn, days):
    return {"house_cost": score(xb, pts, idxn, days, COST), "real_cost": score(xb, pts, idxn, days, REAL_COST),
            "stress_cost": score(xb, pts, idxn, days, STRESS_COST)}


def diff(Ta, B, idxn):
    """Ta rows (entry, exit, side, entry_px, gross); B rows (entry, exit, side, entry_px, exit_px, gross)."""
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    return {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both), "only_A": len(set(ka) - set(kb)),
            "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
            "first_only_A": [[str(idxn[k[0]]), k[1]] for k in sorted(set(ka) - set(kb))[:5]],
            "first_only_B": [[str(idxn[k[0]]), k[1]] for k in sorted(set(kb) - set(ka))[:5]],
            "first_exit_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                 for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5]}


def main():
    sha = lf_sha(PLUGIN)
    plugin_pin_ok = sha.startswith(PIN_PREFIX) and sha == PIN_PREREG_FULL
    assert plugin_pin_ok, "plugin pin"
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    assert idxn[-1] < pd.Timestamp("2016-07-01"), "window must end before the WF start"
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res = {"idea": "QL_MOMDRIVE", "idea_folder": IDEA, "prereg": PREREG, "prereg_lf_sha256": lf_sha(PREREG),
           "plugin": PLUGIN, "plugin_lf_sha256": sha, "plugin_pin_ok": plugin_pin_ok,
           "master": MASTER, "registry_id": row[0].get("id"), "master_source": row[0].get("source"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": str(A.get("fingerprint")), "bars": len(c), "window": [str(days[0].date()), str(days[-1].date())],
           "sessions": len(days), "costs_pts": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT,
           "own_rule_source_sha256": hashlib.sha256(inspect.getsource(own_rule).encode()).hexdigest(),
           "atr14_source_sha256": hashlib.sha256(inspect.getsource(atr14).encode()).hexdigest()}
    m = types.ModuleType("ttm_ql_momdrive")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    dp = dict(getattr(m, "DEFAULT_PARAMS", {}) or {})
    res["plugin_default_params"] = {k: (v if isinstance(v, (int, float, str, bool)) or v is None else str(v)) for k, v in dp.items()}
    ck = [v for kk, v in dp.items() if "compress" in kk.lower()]
    assert len(ck) == 1, ("compress_k default not found", dp)
    compress_k = float(ck[0])
    res["B_compress_k_from_file_default"] = compress_k
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]
    res["A_plugin"] = three([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["gross_pts_sum"] = float(sum(t[4] for t in Ta))
    res["A_plugin"]["trade_tuple_len"] = len(T[0]) if T else 0
    B = own_rule(o, h, l, c, day_id, compress_k)
    res["B_own_rule"] = three([t[1] for t in B], [t[5] for t in B], idxn, days)
    res["B_own_rule"]["gross_pts_sum"] = float(sum(t[5] for t in B))
    res["A_vs_B"] = diff(Ta, B, idxn)
    # blind alternates of the ambiguous choices (all built before reading the plugin code); secondary, for locating diffs
    alts = {}
    for tr, sa, rc in itertools.product([True, False], ["current", "signal"], [False, True]):
        name = f"tr={int(tr)}|stop_atr={sa}|ratchet={int(rc)}"
        Bv = own_rule(o, h, l, c, day_id, compress_k, true_range=tr, stop_atr=sa, ratchet=rc)
        d = diff(Ta, Bv, idxn)
        hc = score([t[1] for t in Bv], [t[5] for t in Bv], idxn, days, COST)
        alts[name] = {"B_trades": d["B_trades"], "same_entry_and_side": d["same_entry_and_side"], "exact": d["exact"],
                      "only_A": d["only_A"], "only_B": d["only_B"], "house_roc30": hc.get("roc30"), "house_net_usd": hc.get("net_usd")}
    res["B_alternates_vs_A"] = alts
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    b = (s + "\n").encode("utf-8")
    open(os.path.join(OUT, "ttm_verify.json"), "wb").write(b)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
