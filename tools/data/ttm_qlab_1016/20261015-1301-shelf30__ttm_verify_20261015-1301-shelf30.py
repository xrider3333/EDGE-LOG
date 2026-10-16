"""TTM (house verifier): BLIND stage-1 re-check of the Qwen Lab's QL_GAMMA_ORB PRE-WF Stage A (idea 20261015-1301-shelf30).
Built from C:/EdgeLog/qwen_lab/ideas/20261015-1301-shelf30/QL_GAMMA_ORB_2026-10-15.md (the prereg) and plugin_v1.py.txt only;
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read
until this output's sha256 is posted to MANAGER.
(B) TTM's OWN implementation of the prereg's Mechanism text, written BEFORE the plugin source was opened (own_rule below);
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 49fc27d828e6... = the prereg's hash) through the engine on the pinned master;
trade-for-trade diff A vs B. Both scored by TTM's own booking: $ on the exit session (ET date), zero days kept; ROC@30k, DD5,
DD% from peak, Sortino. Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1301-shelf30/.
Usage: python ttm_verify_20261015-1301-shelf30.py [--b-only]   (--b-only = freeze Arm B before the plugin is read)."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1301-shelf30"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261015-1301-shelf30"
PLUGIN = IDEA + "/plugin_v1.py.txt"
PREREG = IDEA + "/QL_GAMMA_ORB_2026-10-15.md"
PIN_PREFIX = "49fc27d828e6"
PIN_PREREG_FULL = "49fc27d828e6991c634d02ab39f394006ea18bb22d436a491b165a1fc5fee822"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt RT
STRESS_COST = COST + 0.5               # +1 tick each side on top of house cost
RANGE_BARS, LOOKBACK = 6, 20           # prereg Mechanism defaults

OWN_RULE_READING = [
    "session = a run of equal day_id (ET calendar day) in the registry master; a = the session's first bar",
    "opening range = bars a..a+5 (first 6 bars); range high = max(high), range low = min(low) over those bars; range = high - low",
    "threshold = median of the opening ranges of the 20 PRIOR sessions (today excluded); every prior session with >= 6 bars counts "
    "(narrow, wide, zero-range days alike); fewer than 20 prior sessions in the loaded window -> no trade (warm-up, first 20 sessions of 2010-06-07..)",
    "arm if range >= threshold (inclusive); skip if range <= 0; skip if the session has < 8 bars (6 OR bars + a signal bar + a fill bar)",
    "signal = the FIRST bar k >= a+6 whose close > range high (long) or close < range low (short), strict inequalities; only bars k "
    "whose k+1 is in the same session are scanned (a breakout on the session's last bar = no trade); only the first breakout counts, "
    "a failed/stopped breakout is not re-entered (one trade per session)",
    "fill at bar k+1's open",
    "stop (PRIMARY) = the explicit formula entry - side*0.5*range (half the opening range from the fill price); the words 'range "
    "midpoint' are read as a label for that formula; a VARIANT with the true midpoint (range high + range low)/2 is also reported",
    "stop checked intrabar from the entry bar on (long: low <= stop, short: high >= stop) and filled AT the stop; from the bar after "
    "entry, a bar that opens at/past the stop books its open; variant only: if the fill opens already past the true midpoint, exit at that open",
    "no take-profit; otherwise flat at the session's last bar CLOSE",
    "no look-ahead: OR, threshold and signal use only bars <= k; the fill is k+1's open; exits use only the bar being traded",
]


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def own_rule(o, h, l, c, day_id, range_bars=RANGE_BARS, lookback=LOOKBACK, stop_mode="formula"):
    """The prereg's Mechanism, written from its text (see OWN_RULE_READING). Returns
    [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    hist = []
    out = []
    for s, e in zip(starts, ends):
        if e - s < range_bars:                    # cannot form the opening range: not a range sample, no trade
            continue
        hi = float(h[s:s + range_bars].max())
        lo = float(l[s:s + range_bars].min())
        rg = hi - lo
        prior = hist[-lookback:]
        hist.append(rg)
        if len(prior) < lookback:
            continue
        thr = float(np.median(prior))
        if rg <= 0 or rg < thr or e - s < range_bars + 2:
            continue
        side, k = 0, -1
        for kk in range(s + range_bars, e - 1):   # k+1 must be in the session
            if c[kk] > hi:
                side, k = 1, kk
                break
            if c[kk] < lo:
                side, k = -1, kk
                break
        if side == 0:
            continue
        ent = k + 1
        ep = float(o[ent])
        stop = ep - side * 0.5 * rg if stop_mode == "formula" else 0.5 * (hi + lo)
        xb, xp = e - 1, float(c[e - 1])
        for j in range(ent, e):
            if j > ent or stop_mode != "formula":
                if side * (o[j] - stop) <= 0:     # opens at/past the stop -> books the open
                    xb, xp = j, float(o[j])
                    break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, float(stop)
                break
        out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep))))
    return out


def recon_plugin_warmup(o, h, l, c, day_id, range_bars=RANGE_BARS, lookback=LOOKBACK):
    """POST-READ reconciliation, written AFTER b_freeze.json (NOT part of the blind Arm B): own_rule with ONLY the threshold
    window swapped for the plugin's warm-up reading (last <= 20 prior sessions, sessions with <= 6 bars count as 0, zero ranges
    dropped, needs >= 3 non-zero priors). Everything else is own_rule unchanged."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    hist = []
    out = []
    for s, e in zip(starts, ends):
        if e - s <= range_bars:
            hist.append(0.0)
            continue
        hi = float(h[s:s + range_bars].max())
        lo = float(l[s:s + range_bars].min())
        rg = hi - lo
        prior = np.array(hist[-lookback:], float)
        hist.append(rg)
        prior = prior[prior > 0]
        if len(prior) < 3:
            continue
        thr = float(np.median(prior))
        if rg <= 0 or rg < thr or e - s < range_bars + 2:
            continue
        side, k = 0, -1
        for kk in range(s + range_bars, e - 1):
            if c[kk] > hi:
                side, k = 1, kk
                break
            if c[kk] < lo:
                side, k = -1, kk
                break
        if side == 0:
            continue
        ent = k + 1
        ep = float(o[ent])
        stop = ep - side * 0.5 * rg
        xb, xp = e - 1, float(c[e - 1])
        for j in range(ent, e):
            if j > ent and side * (o[j] - stop) <= 0:
                xb, xp = j, float(o[j])
                break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
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
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"cost_pts": cost, "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "avg_win_loss": [float(usd[usd > 0].mean()) if (usd > 0).any() else float("nan"),
                               float(-usd[usd <= 0].mean()) if (usd <= 0).any() else float("nan")]})
    return f


def arm_scores(exit_bars, pts, idxn, days):
    return {"house_cost": score(exit_bars, pts, idxn, days, COST),
            "real_cost": score(exit_bars, pts, idxn, days, REAL_COST),
            "stress_cost": score(exit_bars, pts, idxn, days, STRESS_COST),
            "gross_pts_total": float(np.sum(pts))}


def trades_sha(rows):
    return hashlib.sha256(json.dumps([list(r) for r in rows]).encode()).hexdigest()


def load():
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1, "registry master row"
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    assert idx[-1] < pd.Timestamp("2016-07-01", tz="US/Eastern"), "window ends before the WF start"
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    return row[0], A, idxn, days, o, h, l, c, np.asarray(A["day_id"])


def b_block(B, idxn, days):
    d = arm_scores([t[1] for t in B], [t[5] for t in B], idxn, days)
    d["long_short"] = [sum(1 for t in B if t[2] > 0), sum(1 for t in B if t[2] < 0)]
    d["trades_sha256"] = trades_sha(B)
    return d


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_PREREG_FULL
    row, A, idxn, days, o, h, l, c, day_id = load()
    B = own_rule(o, h, l, c, day_id)
    Bv = own_rule(o, h, l, c, day_id, stop_mode="midpoint")
    if "--b-only" in sys.argv:
        snap = {"B_trades": len(B), "B_trades_sha256": trades_sha(B), "Bv_trades": len(Bv), "Bv_trades_sha256": trades_sha(Bv),
                "own_rule_src_sha256": hashlib.sha256(open(__file__, "rb").read().replace(b"\r\n", b"\n")).hexdigest()}
        s = json.dumps(snap, indent=1, sort_keys=True)
        open(os.path.join(OUT, "b_freeze.json"), "w", encoding="utf-8", newline="\n").write(s + "\n")
        print(s)
        return
    res = {"idea": "QL_GAMMA_ORB", "idea_folder": IDEA, "prereg": PREREG, "plugin": PLUGIN, "plugin_lf_sha256": pin,
           "plugin_pin_ok": bool(plugin_pin_ok), "master": MASTER, "registry_id": row.get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "bars": int(len(c)), "window": [str(days[0].date()), str(days[-1].date())], "sessions": int(len(days)),
           "instrument": "NQ", "mult": MULT, "costs_pts": {"house": COST, "real": REAL_COST, "stress": STRESS_COST},
           "own_rule_reading": OWN_RULE_READING}
    assert plugin_pin_ok, "plugin pin"
    m = types.ModuleType("ttm_ql_gamma_orb")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]   # (entry, exit, side, entry_px, pts)
    res["A_plugin"] = arm_scores([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["long_short"] = [sum(1 for t in Ta if t[2] > 0), sum(1 for t in Ta if t[2] < 0)]
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["trades_sha256"] = trades_sha(Ta)
    res["B_own_rule"] = b_block(B, idxn, days)
    res["B_variant_true_midpoint_stop"] = b_block(Bv, idxn, days)

    def diff(Ta, B):
        ka = {(t[0], t[2]): t for t in Ta}
        kb = {(t[0], t[2]): t for t in B}
        both = sorted(set(ka) & set(kb))
        same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
        same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
        exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
        same_epx = sum(1 for k in both if abs(ka[k][3] - kb[k][3]) < 1e-6)
        return {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both), "only_A": len(set(ka) - set(kb)),
                "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
                "same_entry_px": same_epx,
                "first_only_A": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), ka[k][4]] for k in sorted(set(ka) - set(kb))[:5]],
                "first_only_B": [[str(idxn[k[0]]), k[1], str(idxn[kb[k][1]]), kb[k][5]] for k in sorted(set(kb) - set(ka))[:5]],
                "first_exit_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                     for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5]}

    res["A_vs_B"] = diff(Ta, B)
    res["A_vs_B"]["all_only_A"] = [[str(idxn[k[0]]), k[1], str(idxn[{(t[0], t[2]): t for t in Ta}[k][1]]),
                                    {(t[0], t[2]): t for t in Ta}[k][4]]
                                   for k in sorted({(t[0], t[2]) for t in Ta} - {(t[0], t[2]) for t in B})]
    res["A_vs_B_variant"] = diff(Ta, Bv)
    sess_start = pd.Series(day_id).groupby(day_id).size()
    first20_last_day = str(days[min(LOOKBACK, len(days)) - 1].date()) if len(sess_start) >= LOOKBACK else None
    res["A_vs_B"]["warmup_note"] = ("own_rule needs 20 prior sessions: no B trade before session 21; session 20 of the window = "
                                    + str(first20_last_day))
    R = recon_plugin_warmup(o, h, l, c, day_id)
    res["POST_READ_reconciliation"] = {
        "note": "written AFTER b_freeze.json and after the plugin source was read; NOT the blind Arm B. own_rule with only the "
                "plugin's warm-up threshold reading swapped in.",
        "b_freeze": json.load(open(os.path.join(OUT, "b_freeze.json"), encoding="utf-8")),
        "b_freeze_harness_copy": os.path.join(OUT, "b_freeze_harness_copy.py.txt"),
        "A_vs_recon": diff(Ta, R),
        "recon_house_cost_roc30": score([t[1] for t in R], [t[5] for t in R], idxn, days, COST)["roc30"],
        "plugin_vs_prereg_text": [
            "warm-up: plugin uses the last min(idx,20) prior sessions, drops zero ranges, arms with >= 3 non-zero priors; the prereg "
            "text says 'median of the last 20 sessions' (TTM: full 20 required) -> the 8 extra A trades, all on 2010-06-10..2010-06-30 (warm-up; their gross sum -24.75 pts = the A-B gross gap)",
            "zero-range prior sessions dropped from the median window (not in the text; no effect here)",
            "breakout scan k in range(a+6, b-2): a first breakout on the session's second-to-last bar (fill on the last bar) is "
            "skipped AND the session gets no trade; text allows it (0 such sessions in this window: only_B = 0)",
            "session too short: plugin skips sessions with <= 8 bars (TTM: < 8); no effect here",
            "stop = entry - side*0.5*range (formula), gap-through books the open: identical to TTM's primary reading",
        ]}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    b = (s + "\n").encode("utf-8")
    with open(os.path.join(OUT, "ttm_verify.json"), "wb") as f:
        f.write(b)
    print(s)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
