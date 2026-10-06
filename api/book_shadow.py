"""Nightly SHADOW lines on the adopted BOOK #463 (FRONTIER lane; owner GO via MANAGER, 2026-09-29).

The VT line rides beside the adopted book figure in the paper report and is NEVER the book figure.
Since 2026-10-02 (377f0f67) the paper report books a trade's money on the US/Eastern day it CLOSES, so the nightly
VT figure = that day's multiplier x the exit-day book figure: a live MONITOR, not the tradable VT line, which sizes
each trade at the multiplier of its ENTRY day. The forward read computes that from the per-trade paper records,
each trade at the multiplier stored in its entry day's report (pre-registration: docs/PREREG_frontier_shadows_
2026-09-29.txt, correction paragraph).

VT  volatility-targeted #463 (book round 62, V2): every trade entering on day D is sized
    m(D) = clip(REF / vol20, 0.5, 2.0) rounded to 0.1, where vol20 is the std of #463's valued-daily
    book P&L over the 20 index days before D and REF the median of vol20 over the 250 index days
    before that. The series is rebuilt each night by the house book engine from #463's job legs,
    starting three years before D - enough warm-up that the recent year matches the full-history
    series (checked when this shipped). Tradable line = each trade x m(its entry day D).

AG  agreement tilt - RETIRED 2026-10-01 (owner GO via MANAGER #48); last in the 10-01 report. Its in-sample
    evidence was a same-bar look-ahead (bar labels, not fills); on fill times the trades it tilted read
    PF 1.35 vs 1.38 for the rest. History: BOOK.md 10p / 10r; the code is in git before this commit.

Everything here is fail-soft: the caller wraps each block, and a failure reports an error string
instead of a number. Nothing here places an order.
"""
import numpy as np
import pandas as pd

# #463's job legs, copied verbatim from its book job (EmzbSsewQJ6TjEaaO4ea). ENGU-Q books its
# 24-hour cost (0.783) and every leg pins its master, exactly as the adopted run did.
BOOK463_LEGS = [
    {"strategy": "ORB_3_6_C2.py", "instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_adj_rth",
     "cost_pts": 0.533, "mult": 20, "weight": 1,
     "params": {"skip_holidays": True, "breakout_buf": 0.25, "vpace_filter": 0.7, "close_confirm": True, "flat_eod": True,
                "or_bars": 2, "stop_frac": 2.0, "be_after_R": 1.0, "trail_bars": 0, "target_R": 5.5, "partial_exit_R": 0.0,
                "trade_mode": "First-candle dir", "atr_filter": 0.7}},
    {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "instrument": "NQ", "timeframe": "1m", "session": "eth", "source": "db_adj_eth",
     "cost_pts": 0.783, "mult": 20, "weight": 1,
     "params": {"buf_atr": 0.3, "tl_len": 206, "trail_frac": 2.5, "breakeven_R": 2.0, "atr_len": 52, "act_R": 1.5, "ema_len": 220,
                "limit_atr": 0.55, "er_len": 100, "stop_mult": 1.0, "regime_len": 10, "min_brk": 1.6, "vol_mult": 1.1, "er_th": 0.0}},
    {"strategy": "TTMSQZ_3_0_ES30SSOF2.py", "instrument": "ES", "timeframe": "30m", "session": "rth", "source": "db_adj_rth",
     "cost_pts": 0.363, "mult": 50, "weight": 3, "params": {"eod_cutoff": 1, "kc_mult": 1.5}},
    {"strategy": "NOISE_1_8_CT304H.py", "instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_noadj_rth",
     "cost_pts": 0.533, "mult": 20, "weight": 1, "params": {"tilt_mult": 1.75, "gate_len": 20, "gate_ratio": 1.15}},
]

VT_LOOKBACK, VT_REF, VT_LO, VT_HI = 20, 250, 0.5, 2.0
VT_WARMUP_DAYS = 3 * 366
VT_MAX_LAG_BDAYS = 1                  # one missing business day tolerated (a holiday); two stops the line



def vt_multipliers(M):
    """Round 62 V2 on a valued-daily book series indexed by day; value at D uses only days before D."""
    vol = M.shift(1).rolling(VT_LOOKBACK, min_periods=VT_LOOKBACK).std()
    ref = vol.shift(1).rolling(VT_REF, min_periods=VT_REF // 2).median()
    return (ref / vol).clip(VT_LO, VT_HI).round(1).fillna(1.0)


def book463_valued_daily(date_from, date_to, data_through=None):
    """#463's valued-daily book P&L, built the way the book job builds it (UTC day stamps kept).

    Refuses (raises) rather than returning a quietly different series: the engine falls back to
    another master when the pinned one is missing, and to exit-day stamps when daily valuation
    fails - either would change the volatility signal without any error (09-30 review). When a
    dict is passed as `data_through`, each leg's last master bar date is recorded in it.
    """
    from augur_engine import book
    days = pd.bdate_range(date_from, date_to)
    parts = []
    for leg in BOOK463_LEGS:
        tr, inf = book._leg_trades(dict(leg), date_from, date_to)
        if inf.get("source") != leg["source"]:
            raise ValueError(f"{leg['strategy']} ran on source {inf.get('source')!r}, pinned {leg['source']!r}")
        if inf.get("mtm_error"):
            raise ValueError(f"{leg['strategy']} daily valuation failed: {inf['mtm_error']}")
        if data_through is not None:
            m = book.find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
            arr = book.load_master_arrays(m, date_from=(pd.Timestamp(date_to) - pd.Timedelta(days=20)).strftime("%Y-%m-%d"))
            idx = pd.to_datetime(arr["index"])
            data_through[leg["strategy"]] = str(idx.max().date()) if len(idx) else None
        marks = inf.pop("_mtm_day", None) or tr
        d, v = book._daily(marks)
        s = pd.Series(v, index=pd.to_datetime(d)).groupby(level=0).sum() if len(d) else pd.Series(dtype=float)
        days = days.union(s.index)
        parts.append(s)
    return sum(s.reindex(days).fillna(0.0) for s in parts)


def vt_multiplier_for(day):
    """(m, info) for trades entering on `day`."""
    D = pd.Timestamp(day).normalize()
    if D.tzinfo is not None:
        D = D.tz_localize(None)
    thru = {}
    M = book463_valued_daily((D - pd.Timedelta(days=VT_WARMUP_DAYS)).strftime("%Y-%m-%d"), D.strftime("%Y-%m-%d"), thru)
    lag = stale_lag(thru, D)
    if max(lag.values()) > VT_MAX_LAG_BDAYS:
        # Missing days read as $0 and shrink the 20-day volatility, which pushes m toward 2.0 with no
        # error at all (09-30 review) - so a master more than one business day behind stops the line.
        raise ValueError(f"stale master data (business days behind D-1): {lag}")
    if D not in M.index:
        M = M.reindex(M.index.union(pd.DatetimeIndex([D]))).fillna(0.0)
    m = vt_multipliers(M)
    before = M[(M.index < D) & (M != 0)]
    return float(m.loc[D]), {"signal_through": str(before.index.max().date()) if len(before) else None,
                             "data_through": thru, "lag_bdays": lag,
                             "vol20": _round(M.shift(1).rolling(VT_LOOKBACK).std().loc[D])}


def stale_lag(data_through, D):
    """Business days each leg's master is behind D-1 (0 = has D-1; a holiday costs 1)."""
    out = {}
    for k, v in data_through.items():
        if v is None:
            out[k] = 99
            continue
        last = pd.Timestamp(v)
        out[k] = max(0, len(pd.bdate_range(last + pd.Timedelta(days=1), D - pd.Timedelta(days=1))))
    return out


def _round(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 2)


def vt_block(book_pnl, day):
    m, info = vt_multiplier_for(day)
    return {"pnl_usd": m * float(book_pnl), "multiplier": m, **info, "base_run": 463,
            "rule": "m = clip(median vol20 of the prior 250 days / vol20, 0.5, 2.0), rounded 0.1 (book round 62 V2)",
            "name": "SHADOW VT (monitor: today's multiplier x the exit-day book figure): #463 sized by its own 20-day volatility vs its trailing year"}


# Weighted sums of existing paper legs (each leg's exit-day figure x weight, the book line's own convention).
# Every entry here was written to its forward bar BEFORE its first forward day - see its "prereg".
SUM_SHADOWS = {
    "book_shadow_q4": {
        "weights": {"ORB_R6": 1.0, "ENGUQ_335_S1": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
        "name": "SHADOW Q4: #463 with ORB #314 and the ENGU-Q cash-session gate (S1)",
        "prereg": "C:/EdgeLog/_anatomy_cache/bookq/PREREG_BOOKQ.txt Q4 (post-hoc; forward read after 12 months)",
        "from": "2026-10-01",
    },
    "book_shadow_orb314": {
        "weights": {"ORB_R6": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
        "name": "SHADOW ORB314: #463 with the ORB crown #314 in the ORB seat (book run #473)",
        "prereg": "C:/EdgeLog/_anatomy_cache/bookq/PREREG_BOOKQ.txt Q1a FORWARD SHADOW (MANAGER GO 09-30; read after 12 months)",
        "from": "2026-10-01",
    },
    "book_shadow_orb239": {
        "weights": {"ORB_239": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
        "name": "SHADOW ORB239: #463 with ORB #239 (breakeven 0.8 R) in the ORB seat (book run #478)",
        "prereg": "C:/EdgeLog/_anatomy_cache/bookq/PREREG_BOOKQ.txt Q6 FORWARD SHADOW (owner: shadow first, 09-30; read after 12 months)",
        "from": "2026-10-01",
    },
    "book_shadow_noise125": {
        "weights": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.25},
        "name": "SHADOW NOISE125: #463 with the NOISE leg at 1.25x (= the book + 0.25 x NOISE_422; not independent of the NOISE_422 read)",
        "prereg": "docs/PREREG_frontier_noise125_2026-10-05.txt (Q8; owner standing order + MANAGER GO 10-04; read once after 12 months)",
        "from": "2026-10-06",
    },
    "book_shadow_nottm": {
        "weights": {"ORB": 1.0, "ENGUQ_335": 1.0, "NOISE_422": 1.0},
        "name": "SHADOW NOTTM: #463 without the TTM leg (= the book - 3 x TTM_299_SSOF2; not independent of the TTM leg's own record)",
        "prereg": "docs/PREREG_frontier_nottm_2026-10-05.txt (Q22; MANAGER assessment 10-05 order 5a(i); harm monitor under the paired stops)",
        "from": "2026-10-06",
    },
}


def sum_blocks(leg_reports):
    out = {}
    for key, spec in SUM_SHADOWS.items():
        w = spec["weights"]
        out[key] = {"pnl_usd": sum(float((leg_reports.get(k) or {}).get("pnl_usd") or 0.0) * x for k, x in w.items()),
                    "weights": dict(w), "missing": [k for k in w if k not in leg_reports],
                    "name": spec["name"], "prereg": spec["prereg"], "from": spec["from"], "base_run": 463}
    return out
