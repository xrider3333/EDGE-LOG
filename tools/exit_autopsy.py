"""EXIT AUTOPSY — per crowned strategy leg, is the EXIT the lever?

For each crowned leg this pulls the crowned parameter set from its Firestore job
doc (or, for a pinned card with no doc on file, the plugin's own DEFAULT_PARAMS),
re-runs the strategy locally on its own window with return_trades=True, and reads
each trade's Maximum Favourable / Adverse Excursion (MFE/MAE, in points, from the
highs/lows strictly between the entry and exit bars) alongside the realised PnL.

The question this answers is narrow and deliberately not "is the strategy good":
winners that only ever capture a small fraction of their best available move, or
losers that were routinely up 1R before turning into losses, both say the EXIT
RULE is where the improvement lives. Winners with high capture and losers that
rarely see 1R say the opposite — the exit is already close to the ceiling and any
future work belongs in the ENTRY.

R unit (site convention): the leg's own average LOSING trade in dollars, computed
on the pre-lockbox slice only — the same denominator the board's EV R uses.

Usage:
    python tools/exit_autopsy.py            # all six legs
    python tools/exit_autopsy.py --quick     # skip ENGU-Q (slow: 1m ETH, 16 years)

Output:
    docs/exit_autopsy.json   (schema fixed — a web page is built against it)
    docs/EXIT_AUTOPSY.md     (15-25 plain-English lines)

Caching: each leg's rich trade list (+ the bars needed to rebuild MAE/MFE) is
pickled to tools/_exit_cache/<legkey>.pkl so a re-run (e.g. after tweaking the
markdown) does not re-run the engine.
"""
import argparse
import importlib.util
import inspect
import json
import os
import pickle
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UP = os.path.join(ROOT, "augur_uploads")
CRED = os.path.join(SHARED, "serviceAccount.json")
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
CACHE_DIR = os.path.join(os.environ.get("EDGELOG_CACHE_DIR") or (r"C:\EdgeLog\_anatomy_cache" if os.path.isdir(r"C:\EdgeLog") else os.path.join(ROOT, "tools", "_anatomy_cache")), "exit")

# house convention used everywhere on the board for NQ 5m/1m one-contract runs
# (tools/ttmsqz_round6_parts.py COST/MULT) — used as the fallback for ORB_234,
# which has no Firestore doc (a pinned card; the memory rule is: pin only in
# DEFAULT_PARAMS, run it with params={} so the plugin's own signature defaults win).
HOUSE_COST_PTS = {"NQ": 0.533, "ES": 0.363}
HOUSE_MULT = {"NQ": 20.0, "ES": 50.0}

LEGS = [
    dict(key="ORB_314", family="ORB", label="ORB #314 (crown)",
         file="ORB_3_6_R6.py", run=314, doc_id="2VCld7X1YRqQlQa25AM5"),
    dict(key="ORB_234", family="ORB", label="ORB #234 (crown, pinned card)",
         file="ORB_3_6_C2.py", run=234, doc_id=None,
         instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
         cost_pts=HOUSE_COST_PTS["NQ"], mult=HOUSE_MULT["NQ"],
         date_from="2010-06-07", date_to="2026-06-30", lockbox_from="2025-07-01"),
    dict(key="NOISE_243", family="NOISE", label="NOISE #243 (crown, paper leg)",
         file="NOISE_1_1_SBS_V90.py", run=243, doc_id="9cr6rtZPZng2HIiLxH3K"),
    dict(key="NOISE_316", family="NOISE", label="NOISE #316",
         file="NOISE_1_1_LB51.py", run=316, doc_id="8ktC5qWGwXgVfeN5d92w"),
    dict(key="ENGUQ_309", family="ENGUQ", label="ENGU-Q #309 (crown)",
         file="ENGUQ_1M_ETH_ER_1_0.py", run=309, doc_id="KPbrQdTZBP32CFjwF1Ns", slow=True),
    dict(key="NQDIP_307", family="NQDIP", label="NQDIP #307",
         file="NQDIP_1_0.py", run=307, doc_id="8zkU44lPUNRtKR5IMWR2"),
]


# ── Firestore (single .get() per doc — never .stream(), the 50k reads/day cap) ──

def fetch_doc(doc_id):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(CRED))
    db = firestore.client()
    snap = db.collection("users").document(UID).collection("backtests").document(doc_id).get()
    return snap.to_dict() or {}


# ── plugin loading + master bars (pattern lifted from tools/ttmsqz_round6_parts.py) ──

def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def load_plugin(fn):
    path = os.path.join(ROOT, "augur_strategies", fn)
    if not os.path.exists(path):
        path = os.path.join(SHARED, "augur_strategies", fn)
    return _mod(path, fn.replace(".py", "_x"))


def load_bars(inst, tf, session, date_from, date_to):
    """Master bars with _dt (bar open) and _end (bar close = when it becomes knowable).
    ETH runs 18:00 -> 17:00 next day, so the trading DAY rolls at 18:00 ET."""
    fn = "NOADJ_%s_%s_%s.csv" % (inst, tf, session.upper())
    path = os.path.join(UP, fn)
    if not os.path.exists(path):
        path = os.path.join(SHARED, "augur_uploads", fn)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(date_from).date())
            & (df["_dt"].dt.date <= pd.Timestamp(date_to).date())].reset_index(drop=True)
    df["_end"] = df["_dt"] + pd.Timedelta(minutes=int(tf[:-1]))
    d = (df["_dt"] + pd.Timedelta(hours=6)).dt.date if session.upper() == "ETH" else df["_dt"].dt.date
    df["day_id"] = pd.factorize(d)[0]
    return df


# ── leg resolution: Firestore doc -> run params, window, cost/mult ──

def resolve_leg(meta):
    """Fill in instrument/timeframe/session/source/cost_pts/mult/window/params from
    the Firestore doc, or from the meta dict itself when doc_id is None (ORB_234's
    pinned card — no doc on file, run the plugin's own DEFAULT_PARAMS defaults)."""
    out = dict(meta)
    if meta.get("doc_id"):
        d = fetch_doc(meta["doc_id"])
        strat_file = d.get("strategy") or meta["file"]
        if strat_file != meta["file"]:
            print("  WARNING: doc strategy=%r != expected %r" % (strat_file, meta["file"]))
        out["instrument"] = d.get("instrument", "NQ")
        out["timeframe"] = d.get("timeframe", "5m")
        out["session"] = (d.get("session") or "rth").lower()
        out["source"] = d.get("source", "")
        out["cost_pts"] = float(d.get("cost_pts") or 0.0)
        out["mult"] = float(d.get("mult") or 1.0)
        out["date_from"] = d.get("date_from")
        out["date_to"] = d.get("date_to")
        lb_months = d.get("lockbox_months")
        out["lockbox_months"] = lb_months
        if lb_months:
            out["lockbox_from"] = str((pd.Timestamp(out["date_to"]) -
                                        pd.DateOffset(months=int(lb_months))).date())
        else:
            out["lockbox_from"] = out["date_to"]
        result = (d.get("result") or {})
        best_params = result.get("best_params") or {}
        out["params"] = dict(best_params)
        out["params_source"] = "best_params"
        gv = (result.get("gate_validate") or {}).get("ungated_full") or {}
        out["_ungated_full"] = gv
    else:
        # pinned card, no doc — DEFAULT_PARAMS defaults win (memory: a pinned card
        # pins only in DEFAULT_PARAMS; params={} runs the plugin's own defaults).
        out["params"] = {}
        out["params_source"] = "DEFAULT_PARAMS (no Firestore doc for this pinned card)"
        out["_ungated_full"] = {}
    return out


# ── running the strategy locally with the crowned params ──

def run_leg(meta):
    plugin = load_plugin(meta["file"])
    df = load_bars(meta["instrument"], meta["timeframe"], meta["session"],
                    meta["date_from"], meta["date_to"])
    params = meta["params"]
    if not params:
        params = {k: v["default"] for k, v in getattr(plugin, "DEFAULT_PARAMS", {}).items()}
        if meta["params_source"].startswith("DEFAULT_PARAMS"):
            meta["params"] = params  # record what actually ran

    sig = inspect.signature(plugin.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sig.values())
    call_kw = dict(params) if hk else {k: v for k, v in params.items() if k in sig}
    extra = {}
    if "volumes" in sig or hk:
        extra["volumes"] = df["volume"].values if "volume" in df else None
    if "day_id" in sig or hk:
        extra["day_id"] = df["day_id"].values
    if "index" in sig or hk:
        extra["index"] = df["_dt"]

    r = plugin.run_backtest(df["open"].values, df["high"].values, df["low"].values,
                             df["close"].values, return_trades=True, **extra, **call_kw)
    if not r or not r.get("trades"):
        raise RuntimeError("no trades for %s" % meta["key"])
    return df, r["trades"]


# ── tuple normalisation + MFE/MAE (points), the mae_mfe shape from augur_engine/analytics.py ──

def normalize_trades(trades, opens):
    """Return a list of dicts {eb, xb, pnl, side, epx} in bar-index order. Every
    plugin here already emits (entry_bar, exit_bar, pnl, side, entry_px[, ...]) —
    a real 5+ field tuple — so side_source is "tuple" for all six legs; the
    long-only inference fallback stays in for a plugin that ever ships a bare
    3-tuple (mirrors augur_engine/analytics.py's own mae_mfe guard)."""
    out = []
    tuple_based = trades and isinstance(trades[0], (list, tuple)) and len(trades[0]) >= 5
    for t in trades:
        eb, xb, pnl = int(t[0]), int(t[1]), float(t[2])
        if tuple_based:
            side = int(t[3]); epx = float(t[4])
        else:
            side = 1  # inferred: every plugin in this batch without side is long-only
            epx = float(opens[eb])
        out.append(dict(eb=eb, xb=xb, pnl=pnl, side=side, epx=epx))
    side_source = "tuple" if tuple_based else "inferred:long-only"
    return out, side_source


def mfe_mae_points(trade, highs, lows):
    a, b = max(0, min(trade["eb"], trade["xb"])), min(len(highs) - 1, max(trade["eb"], trade["xb"]))
    if b < a:
        return 0.0, 0.0, 0
    hi = float(np.max(highs[a:b + 1])); lo = float(np.min(lows[a:b + 1]))
    hi_i = a + int(np.argmax(highs[a:b + 1])); lo_i = a + int(np.argmin(lows[a:b + 1]))
    if trade["side"] >= 0:
        mae = lo - trade["epx"]; mfe = hi - trade["epx"]; peak_bar = hi_i
    else:
        mae = trade["epx"] - hi; mfe = trade["epx"] - lo; peak_bar = lo_i
    return mfe, mae, peak_bar


def nqdip_dollars_per_pt(entry_px, notional):
    """NQDIP sizes to constant notional in whole MNQ micros ($2/pt each) — see
    augur_strategies/NQDIP_1_0.py `size()`. Point excursions (MFE/MAE from raw
    highs/lows) need this per-trade conversion; the plugin's own `pnl` field is
    already dollars (job cost_pts=0, mult=1 by the plugin's own contract)."""
    k = max(1, int(round(float(notional) / (entry_px * 2.0))))
    return k * 2.0


def enrich(meta, df, raw_trades):
    trades, side_source = normalize_trades(raw_trades, df["open"].values)
    highs, lows = df["high"].values, df["low"].values
    is_nqdip = meta["key"] == "NQDIP_307"
    notional = float(meta["params"].get("notional", 100000)) if is_nqdip else None
    mult = meta["mult"]; cost_pts = meta["cost_pts"]
    dates = pd.DatetimeIndex(df["_dt"])
    rows = []
    for t in trades:
        mfe_pts, mae_pts, peak_bar = mfe_mae_points(t, highs, lows)
        dpp = nqdip_dollars_per_pt(t["epx"], notional) if is_nqdip else mult
        mfe_usd = mfe_pts * dpp
        mae_usd = mae_pts * dpp
        final_usd = (t["pnl"] - cost_pts) * mult if not is_nqdip else t["pnl"]
        eb, xb = t["eb"], t["xb"]
        held = max(1, xb - eb)
        peak_frac = float(np.clip((peak_bar - eb) / held, 0.0, 1.0))
        rows.append(dict(
            eb=eb, xb=xb, held=held, side=t["side"],
            mfe_usd=mfe_usd, mae_usd=mae_usd, final_usd=final_usd,
            peak_frac=peak_frac,
            exit_date=dates[min(xb, len(dates) - 1)],
        ))
    return pd.DataFrame(rows), side_source


# ── measures ──

def _q(a, p):
    return float(np.percentile(a, p)) if len(a) else float("nan")


def _med(a):
    return float(np.median(a)) if len(a) else float("nan")


def block(tr, r_unit_usd, window_years, rnd=3):
    n = len(tr)
    if n == 0:
        empty_hold = [dict(bucket=str(i + 1), bars_lo=0, bars_hi=0, n=0,
                            mfe_r_med=0.0, final_r_med=0.0, win_pct=0.0) for i in range(10)]
        return dict(n=0,
                     winners=dict(n=0, mfe_r_med=0.0, mfe_r_p25=0.0, mfe_r_p75=0.0,
                                  mae_r_med=0.0, capture_med=0.0, capture_p25=0.0),
                     losers=dict(n=0, mfe_r_med=0.0, mae_r_med=0.0,
                                 share_reached_0_5r=0.0, share_reached_1r=0.0),
                     hold_curve=empty_hold,
                     peak_timing=dict(med_peak_frac=0.0, share_peak_first_half=0.0),
                     give_back=dict(med_r=0.0, usd_per_year=0.0))

    mfe_r = tr["mfe_usd"].values / r_unit_usd
    mae_r = tr["mae_usd"].values / r_unit_usd
    final_r = tr["final_usd"].values / r_unit_usd

    win_mask = tr["final_usd"].values > 0
    win = tr[win_mask]; lose = tr[~win_mask]
    win_mfe_r = win["mfe_usd"].values / r_unit_usd
    win_mae_r = win["mae_usd"].values / r_unit_usd
    win_final_usd = win["final_usd"].values
    win_mfe_usd = win["mfe_usd"].values
    cap = np.divide(win_final_usd, win_mfe_usd, out=np.zeros_like(win_final_usd),
                     where=win_mfe_usd > 1e-9)

    lose_mfe_r = lose["mfe_usd"].values / r_unit_usd
    lose_mae_r = lose["mae_usd"].values / r_unit_usd

    winners = dict(n=int(len(win)), mfe_r_med=round(_med(win_mfe_r), rnd),
                   mfe_r_p25=round(_q(win_mfe_r, 25), rnd), mfe_r_p75=round(_q(win_mfe_r, 75), rnd),
                   mae_r_med=round(_med(win_mae_r), rnd),
                   capture_med=round(_med(cap), rnd) if len(cap) else 0.0,
                   capture_p25=round(_q(cap, 25), rnd) if len(cap) else 0.0)
    losers = dict(n=int(len(lose)), mfe_r_med=round(_med(lose_mfe_r), rnd),
                  mae_r_med=round(_med(lose_mae_r), rnd),
                  share_reached_0_5r=round(float(np.mean(lose_mfe_r >= 0.5)) if len(lose_mfe_r) else 0.0, rnd),
                  share_reached_1r=round(float(np.mean(lose_mfe_r >= 1.0)) if len(lose_mfe_r) else 0.0, rnd))

    # hold-time deciles: rank-sort by bars held, split into 10 ~equal-count buckets
    order = np.argsort(tr["held"].values, kind="stable")
    buckets = np.array_split(order, 10)
    hold_curve = []
    for i, idx in enumerate(buckets):
        if len(idx) == 0:
            hold_curve.append(dict(bucket=str(i + 1), bars_lo=0, bars_hi=0, n=0,
                                    mfe_r_med=0.0, final_r_med=0.0, win_pct=0.0))
            continue
        held_b = tr["held"].values[idx]
        hold_curve.append(dict(
            bucket=str(i + 1), bars_lo=int(held_b.min()), bars_hi=int(held_b.max()),
            n=int(len(idx)), mfe_r_med=round(_med(mfe_r[idx]), rnd),
            final_r_med=round(_med(final_r[idx]), rnd),
            win_pct=round(float(100.0 * np.mean(win_mask[idx])), rnd)))

    peak_timing = dict(
        med_peak_frac=round(_med(win["peak_frac"].values), rnd) if len(win) else 0.0,
        share_peak_first_half=round(float(np.mean(win["peak_frac"].values <= 0.5)), rnd) if len(win) else 0.0)

    give_back_r = mfe_r - final_r
    give_back_usd_total = float(np.sum(tr["mfe_usd"].values - tr["final_usd"].values))
    give_back = dict(med_r=round(_med(give_back_r), rnd),
                      usd_per_year=round(give_back_usd_total / window_years, 1) if window_years > 0 else 0.0)

    return dict(n=int(n), winners=winners, losers=losers, hold_curve=hold_curve,
                peak_timing=peak_timing, give_back=give_back)


def make_read(pre):
    """Conservative: only call the exit a lever when losers frequently reach >=1R
    AND winners' capture is low. Otherwise the exit is close to the ceiling."""
    cap = pre["winners"]["capture_med"]
    reach1r = pre["losers"]["share_reached_1r"]
    is_lever = (cap <= 0.55) and (reach1r >= 0.30)
    verb = "IS a lever" if is_lever else "is not where the money is"
    return "winners keep %.0f%% of their best move and %.0f%% of losers were ever up 1R, so the exit %s." % (
        100 * cap, 100 * reach1r, verb), is_lever


# ── per-leg pipeline (cached) ──

def process_leg(meta_in, refresh=False):
    key = meta_in["key"]
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, "%s.pkl" % key)
    if os.path.exists(cache_path) and not refresh:
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        print("  [%s] cache hit (%d trades)" % (key, len(cached["tr"])))
        return cached

    print("[%s] resolving Firestore doc / pinned defaults..." % key)
    meta = resolve_leg(meta_in)
    print("  params: %s" % json.dumps(meta["params"], default=str))
    print("  window: %s .. %s  lockbox from %s  (%s %s %s)" % (
        meta["date_from"], meta["date_to"], meta["lockbox_from"],
        meta["instrument"], meta["timeframe"], meta["session"]))

    print("  running strategy locally...")
    df, raw_trades = run_leg(meta)
    print("  %d raw trades" % len(raw_trades))

    tr, side_source = enrich(meta, df, raw_trades)
    meta["side_source"] = side_source

    cached = dict(meta=meta, tr=tr)
    with open(cache_path, "wb") as f:
        pickle.dump(cached, f)
    return cached


# ── output ──

def build_leg_json(cached):
    meta, tr = cached["meta"], cached["tr"]
    lb_from = pd.Timestamp(meta["lockbox_from"])
    is_lb = tr["exit_date"] >= lb_from.tz_localize("US/Eastern")
    pre_tr, lb_tr = tr[~is_lb], tr[is_lb]

    pre_losers = pre_tr[pre_tr["final_usd"] <= 0]
    r_unit_usd = float(-pre_losers["final_usd"].mean()) if len(pre_losers) else float("nan")
    if not (r_unit_usd == r_unit_usd) or r_unit_usd <= 0:  # NaN or non-positive guard
        losers_all = tr[tr["final_usd"] <= 0]
        r_unit_usd = float(-losers_all["final_usd"].mean()) if len(losers_all) else 1.0

    date_from = pd.Timestamp(meta["date_from"]); date_to = pd.Timestamp(meta["date_to"])
    pre_years = max((lb_from - date_from).days / 365.25, 1e-9)
    lb_years = max((date_to - lb_from).days / 365.25, 1e-9)

    pre_block = block(pre_tr, r_unit_usd, pre_years)
    lb_block = block(lb_tr, r_unit_usd, lb_years)
    read, is_lever = make_read(pre_block)

    got_net = float(tr["final_usd"].sum())
    ungated = meta.get("_ungated_full") or {}
    expected_net = None
    if ungated:
        pts_or_usd = float(ungated.get("total_pnl", 0.0))
        expected_net = pts_or_usd if meta["key"] == "NQDIP_307" else pts_or_usd * meta["mult"]
    ok = True if expected_net is None else bool(abs(got_net - expected_net) <= max(1000.0, 0.03 * abs(expected_net)))

    return dict(
        key=meta["key"], family=meta["family"], label=meta["label"], file=meta["file"],
        run=meta.get("run"), instrument=meta["instrument"], timeframe=meta["timeframe"],
        session=meta["session"], window=[meta["date_from"], meta["date_to"]],
        lockbox_from=meta["lockbox_from"], side_source=meta["side_source"],
        r_unit_usd=round(r_unit_usd, 2),
        parity=dict(expected_net=round(expected_net, 2) if expected_net is not None else None,
                    got_net=round(got_net, 2), ok=ok),
        pre=pre_block, lb=lb_block, read=read, _is_lever=is_lever,
    )


def build_markdown(legs_json):
    lines = []
    lines.append("# EXIT AUTOPSY")
    lines.append("")
    lines.append("Per crowned strategy leg: how far trades went in favour (MFE) and against (MAE)")
    lines.append("while open, how much of the favourable move winners actually kept, and how often")
    lines.append("losers were first up a meaningful amount. R = the leg's own average losing trade")
    lines.append("in dollars, pre-lockbox — the same denominator the board's EV R uses.")
    lines.append("")
    levers = [l for l in legs_json if l["_is_lever"]]
    not_levers = [l for l in legs_json if not l["_is_lever"]]
    lines.append("**Exit is a lever on:** " + (", ".join(l["label"] for l in levers) if levers else "none of the six"))
    lines.append("**Exit is not the lever on:** " + (", ".join(l["label"] for l in not_levers) if not_levers else "none"))
    lines.append("")
    for l in legs_json:
        p = l["parity"]
        parity_note = "parity n/a (no doc to check against)" if p["expected_net"] is None else (
            "parity OK" if p["ok"] else "PARITY MISMATCH (expected $%s, got $%s)" % (
                "{:,.0f}".format(p["expected_net"]), "{:,.0f}".format(p["got_net"])))
        lines.append("## %s" % l["label"])
        lines.append("- %s %s %s, window %s..%s, lockbox from %s. side from %s. %s." % (
            l["instrument"], l["timeframe"], l["session"], l["window"][0], l["window"][1],
            l["lockbox_from"], l["side_source"], parity_note))
        lines.append("- R unit (avg losing trade, pre-lockbox) = $%s" % "{:,.0f}".format(l["r_unit_usd"]))
        lines.append("- Pre-lockbox (n=%d): winners capture %.0f%% of MFE (p25 %.0f%%), losers reach "
                      "0.5R %.0f%% of the time and 1R %.0f%% of the time." % (
                          l["pre"]["n"], 100 * l["pre"]["winners"]["capture_med"],
                          100 * l["pre"]["winners"]["capture_p25"],
                          100 * l["pre"]["losers"]["share_reached_0_5r"],
                          100 * l["pre"]["losers"]["share_reached_1r"]))
        lines.append("- Give-back (a perfect-exit ceiling, NOT achievable): %.2fR median, ~$%s/yr pre-lockbox." % (
            l["pre"]["give_back"]["med_r"], "{:,.0f}".format(l["pre"]["give_back"]["usd_per_year"])))
        if l["lb"]["n"]:
            lines.append("- Lockbox (n=%d, small sample): winners capture %.0f%%, losers reach 1R %.0f%% of the time." % (
                l["lb"]["n"], 100 * l["lb"]["winners"]["capture_med"], 100 * l["lb"]["losers"]["share_reached_1r"]))
        lines.append("- Read: %s" % l["read"])
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip ENGU-Q (slow: 1m ETH, 16 years)")
    ap.add_argument("--refresh", action="store_true", help="ignore the pickle cache")
    a = ap.parse_args()

    legs_to_run = [l for l in LEGS if not (a.quick and l.get("slow"))]
    legs_json = []
    for meta_in in legs_to_run:
        cached = process_leg(meta_in, refresh=a.refresh)
        lj = build_leg_json(cached)
        legs_json.append(lj)
        p = lj["parity"]
        print("  [%s] parity: expected=%s got=%.0f ok=%s  read: %s" % (
            lj["key"], p["expected_net"], p["got_net"], p["ok"], lj["read"]))

    out = dict(generated=datetime.now(timezone.utc).isoformat(),
               version=1,
               r_note="R = the average losing trade in dollars, pre-lockbox",
               legs=[{k: v for k, v in lj.items() if k != "_is_lever"} for lj in legs_json])

    out_json = os.path.join(ROOT, "docs", "exit_autopsy.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nwrote", out_json)

    md = build_markdown(legs_json)
    out_md = os.path.join(ROOT, "docs", "EXIT_AUTOPSY.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    print("wrote", out_md)


if __name__ == "__main__":
    main()
