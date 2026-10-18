"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_QUIETBREAK_NQ (idea folder 20261017-1555-own) PRE-WF Stage A.
Built from the folder's prereg QL_QUIETBREAK_NQ_2026-10-17.md and the plugin file only; the lab's numbers_pre_wf.json /
pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read until this output's
sha256 is posted to MANAGER.
(A) the plugin AS RUN (plugin_v2.py.txt, LF sha256 9d8a2e5e563a... = the prereg's hash) through the engine on the pinned master;
(B) TTM's OWN implementation of the prereg's 'Mechanism' text, written BEFORE the plugin code was read; trade-for-trade diff.
Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1555-own/."""
import hashlib
import inspect
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1555-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261017-1555-own/plugin_v2.py.txt"
PREREG = "C:/EdgeLog/qwen_lab/ideas/20261017-1555-own/QL_QUIETBREAK_NQ_2026-10-17.md"
PIN_PREFIX = "9d8a2e5e563a"
PIN_FULL_PREREG = "9d8a2e5e563af81b99db7ad87ceb2a124ec95d4e7b7f3c98b48a0883bbbd75f6"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side over house cost (reported although this is NOT a short-hold scalper)


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def own_rule(o, h, l, c, day_id, quiet_k=1.0, lookback=20, morning_bars=12):
    """The prereg's Mechanism, written from its text BEFORE reading the plugin code.
    Per session (day_id run): morning range MR = max(high[0:12]) - min(low[0:12]) over the session's first 12 bars (positional;
    every session in this window starts 09:30 with 12 full morning bars). Quiet filter: MR <= quiet_k x median(MR of the
    `lookback` sessions immediately BEFORE this one in the loaded data) - today excluded; a session with fewer than `lookback`
    prior sessions in the window does not trade. quiet_k is not given in the Mechanism text: 1.0 (at or below the trailing
    median = 'compressed'). Signal: the FIRST bar k >= 12 whose close > morning high (long) or < morning low (short) - strict;
    only that first break is used. Entry at bar k+1's open, k+1 must be in the same session (a first break on the session's
    last bar = no trade). Exit at the close of the session's last bar in the data (no stop, no target). One trade per session.
    Uses only bars <= k for the decision, the open of k+1 for the fill. Returns (entry_bar, exit_bar, side, entry_px, exit_px,
    gross_pts)."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    mr = np.array([h[s:s + morning_bars].max() - l[s:s + morning_bars].min() if e - s >= morning_bars else np.nan
                   for s, e in zip(starts, ends)])
    out = []
    for i, (s, e) in enumerate(zip(starts, ends)):
        if i < lookback or e - s < morning_bars or not np.isfinite(mr[i]):
            continue
        prior = mr[i - lookback:i]
        if not np.all(np.isfinite(prior)):
            continue
        if not mr[i] <= quiet_k * float(np.median(prior)):
            continue
        mh = h[s:s + morning_bars].max()
        ml = l[s:s + morning_bars].min()
        for k in range(s + morning_bars, e):
            side = 1 if c[k] > mh else (-1 if c[k] < ml else 0)
            if side == 0:
                continue
            if k + 1 < e:
                ent, xb = k + 1, e - 1
                ep, xp = float(o[ent]), float(c[xb])
                out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep))))
            break                                 # first break only; one trade per session
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
    pts_gross = np.asarray(pts_gross, float)
    usd = (pts_gross - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"cost_pts_rt": cost, "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "gross_per_trade_pts": float(pts_gross.mean()) if len(usd) else float("nan"),
              "gross_over_cost": float(pts_gross.mean() / cost) if len(usd) else float("nan"),
              "net_per_trade_usd": float(usd.mean()) if len(usd) else float("nan"),
              "avg_win_loss_usd": [float(usd[usd > 0].mean()) if (usd > 0).any() else float("nan"),
                                   float(-usd[usd <= 0].mean()) if (usd <= 0).any() else float("nan")]})
    return f


def arm(exits, pts, idxn, days):
    return {"house_cost": score(exits, pts, idxn, days, COST), "real_cost": score(exits, pts, idxn, days, REAL_COST),
            "stress_cost": score(exits, pts, idxn, days, STRESS_COST)}


def DIAGNOSTICS(o, h, l, c, day_id, idxn, days, Ta, m):
    """Added AFTER the blind build (own_rule above is unchanged: its source is checked against the frozen copy
    ttm_verify_blind_build_frozen.py.txt). Reading the plugin: it uses the trailing median over the up-to-`lookback` prior
    sessions with a minimum of 5 (prev.size >= 5), so it trades in the window's first 20 sessions where own_rule (full 20 prior
    sessions) does not. Check: the A-only trades all sit in sessions 5..19 of the window, and A without them == B exactly."""
    import ast
    frozen = open(os.path.join(OUT, "ttm_verify_blind_build_frozen.py.txt"), encoding="utf-8").read()
    fn = [x for x in ast.parse(frozen).body if isinstance(x, ast.FunctionDef) and x.name == "own_rule"][0]
    own_unchanged = ast.get_source_segment(frozen, fn).strip() == inspect.getsource(own_rule).strip()
    st = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    sess_of = np.searchsorted(st, np.arange(len(c)), side="right") - 1
    B = own_rule(o, h, l, c, day_id)
    kb = {(t[0], t[2]) for t in B}
    only_a = [t for t in Ta if (t[0], t[2]) not in kb]
    a_post = [t for t in Ta if sess_of[t[0]] >= 20]
    same = sorted((t[0], t[1], t[2], round(t[4], 6)) for t in a_post) == sorted((t[0], t[1], t[2], round(t[5], 6)) for t in B)
    return {"own_rule_unchanged_vs_frozen_blind_copy": bool(own_unchanged),
            "plugin_warmup_rule": "median over up to `lookback` prior sessions, needs >= 5 (prev.size >= 5); own_rule needs the full 20",
            "only_A_session_indices": sorted(int(sess_of[t[0]]) for t in only_a),
            "only_A_gross_pts": [t[4] for t in only_a], "only_A_gross_pts_sum": float(sum(t[4] for t in only_a)),
            "A_from_session_20_equals_B_exactly": bool(same), "A_from_session_20_trades": len(a_post),
            "plugin_other_skips": "sessions < 14 bars (none here: min 24), median <= 0, morning range <= 0 (none)"}


def main():
    sha = lf_sha(PLUGIN)
    pin_ok = sha.startswith(PIN_PREFIX) and sha == PIN_FULL_PREREG
    assert pin_ok, "plugin pin"
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    assert days[-1] < pd.Timestamp("2016-07-01")
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res = {"idea": "QL_QUIETBREAK_NQ", "folder": "20261017-1555-own", "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": A.get("fingerprint"), "bars": len(c), "window": [str(days[0].date()), str(days[-1].date())],
           "sessions": len(days), "plugin": PLUGIN, "plugin_lf_sha256": sha, "plugin_pin_ok": bool(pin_ok),
           "prereg_lf_sha256": lf_sha(PREREG), "own_rule_src_sha256": hashlib.sha256(inspect.getsource(own_rule).encode()).hexdigest(),
           "costs_pts_rt": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT,
           "blind_build_frozen_copy_sha256": hashlib.sha256(open(os.path.join(OUT, "ttm_verify_blind_build_frozen.py.txt"), "rb").read()).hexdigest()}
    # ARM B (own rule, blind)
    B = own_rule(o, h, l, c, day_id)
    res["B_own_rule"] = arm([t[1] for t in B], [t[5] for t in B], idxn, days)
    # ARM A (plugin through the engine)
    m = types.ModuleType("ttm_ql_quietbreak")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # entry, exit, side, entry_px, gross pts
    res["A_plugin"] = arm([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["engine_trade_tuple_len"] = len(T[0]) if T else 0
    res["A_plugin"]["default_params"] = {k: (v if isinstance(v, (int, float, str, bool)) else str(v))
                                         for k, v in dict(getattr(m, "DEFAULT_PARAMS", {}) or {}).items()}
    # A vs B
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    ent_a = {t[0] for t in Ta}
    ent_b = {t[0] for t in B}
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both),
                     "same_entry_bar_any_side": len(ent_a & ent_b),
                     "only_A": len(set(ka) - set(kb)), "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit,
                     "same_gross_pts": same_pts, "exact_same_exit_and_pts": exact,
                     "first_only_A": [[str(idxn[k[0]]), k[1]] for k in sorted(set(ka) - set(kb))[:8]],
                     "first_only_B": [[str(idxn[k[0]]), k[1]] for k in sorted(set(kb) - set(ka))[:8]],
                     "first_exit_diffs": [[str(idxn[k[0]]), str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:8]}
    # A's own entry-time profile (contract check: earliest in-session bar)
    st = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    sess_start = st[np.searchsorted(st, np.arange(len(c)), side="right") - 1]
    res["A_plugin"]["min_in_session_entry_bar"] = int(min(t[0] - sess_start[t[0]] for t in Ta)) if Ta else None
    res["B_own_rule"]["min_in_session_entry_bar"] = int(min(t[0] - sess_start[t[0]] for t in B)) if B else None
    res["A_plugin"]["exit_at_session_last_bar"] = int(sum(1 for t in Ta if t[1] + 1 == len(c) or day_id[t[1] + 1] != day_id[t[1]]))
    diag = globals().get("DIAGNOSTICS")
    if diag:
        res["diagnostics_after_blind_build"] = diag(o, h, l, c, day_id, idxn, days, Ta, m)
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    path = os.path.join(OUT, "ttm_verify.json")
    open(path, "w", encoding="utf-8", newline="\n").write(s + "\n")
    print("output sha256", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
