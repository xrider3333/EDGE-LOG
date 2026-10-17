"""CTXSHORT r1 harness (DISC, owner item via MANAGER #111 / GO #112, 2026-10-17) - see docs/PREREG_disc_ctxshort_r1_2026-10-17.md.

The owner's CBD / ENGD shorts as a frozen NQ 1-minute scan WITH the context filter his three should-have-traded
signals share (docs/SHOULD_HAVE_TRADED_2026-10-12_14_16.md). Walk-forward years only; no outcome is read on a lockbox
day. The answer key (the owner's 3 design dates + the journal's real CBD / ENGD futures trades, all 2026) is checked
AFTER the WF read, flags only.

Stages (in this order, one run):
  -  selftest on synthetic bars (bar stamps, trail, CBD at 09:45, E2 same-bar breakeven); stops on a failure
  0  prereg LF sha256 check (stops on a mismatch), master pins, census (no outcomes) + power line
  1  WF outcomes per exit rule at NQ cost, + cost stresses, splits, crown-shadow checks (NOISE #382, ORB #314)
  2  answer key: does the frozen rule fire at the owner's signals (NQ for NQ/MNQ, ES for MES), flags only

    python tools/disc_ctxshort_r1.py [--out C:\\EdgeLog\\_anatomy_cache\\ctxshort_r1]
Reads masters (registry of the shared checkout when this checkout has none) and the crowns' run docs (read-only);
writes only under --out.
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(ROOT, "optimizer_history.db")
DATA_REPO = ROOT if (os.path.exists(_DB) and os.path.getsize(_DB) > 0) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, DATA_REPO)
sys.path.insert(1, os.path.join(DATA_REPO, "tools"))
PREREG = os.path.join(ROOT, "docs", "PREREG_disc_ctxshort_r1_2026-10-17.md")
EXPECT_PREREG_SHA = "a53b1256efa7cfd5c761d320098972b4128afe2d44cb0f85bf7779a6ede4d384"      # frozen 2026-10-17; the run stops if the prereg's LF sha256 differs

ET = "America/New_York"
WF0, WF1 = "2016-07-01", "2025-06-29"           # BOOK.md: WF 2016-07-01..2025-06-29, LB from 2025-06-30
HALVES = (("2016-07-01", "2020-12-31"), ("2021-01-01", "2025-06-29"))
WARM0 = "2016-03-01"
MASTERS = {"NQ": ("ADJ_NQ_1m_ETH.csv", 66), "ES": ("ADJ_ES_1m_ETH.csv", 58)}
WIN0, WIN1 = 9 * 60 + 45, 11 * 60 + 29          # signal bar START minute 09:45..11:29 ET
RTH0, RTH1 = 9 * 60 + 30, 15 * 60 + 59
STUB_LAST = 13 * 60 + 10                        # a session whose last RTH bar starts before 13:10 is a holiday stub
BODY_X, VOL_X, LOOKBACK = 2.0, 1.5, 10
BASE_N, BASE_ATR_K = 15, 4.0
ENGD_N, LH_N = 3, 10
MAX_PER_DAY = 2
COST_NQ, COST_MNQ, TICK = 0.783, 1.44, 0.25
PV_NQ, R_USD = 20.0, 500.0
PRIOR_R = 0.10
SD_ASSUMED = {"E1": 1.4, "E2": 1.6, "E3": 4.0}
PRIMARY = "E2"
T_PRIMARY, T_SECONDARY = 2.0, 2.4
AV_TRADES_YR, AV_ROC = 50.0, 15.0
SEED = 20261017
CROWNS = (382, 314)
OWNER_MISSED = [("NQ", "2026-10-12", "10:06", "CBD design example"), ("NQ", "2026-10-14", "09:57", "ENGD design example"),
                ("NQ", "2026-10-16", "10:51", "ENGD design example")]
ROOT_OF = {"MES": "ES", "ES": "ES", "MNQ": "NQ", "NQ": "NQ"}
CME_FULL_2025_26 = ('2025-01-01', '2025-01-09', '2025-01-20', '2025-02-17', '2025-04-18', '2025-05-26', '2025-06-19',
                    '2025-07-04', '2025-09-01', '2025-11-27', '2025-12-25', '2026-01-01', '2026-01-19', '2026-02-16',
                    '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07')   # = tools/point_score.py
TRADE_COLS = ["sig_i", "day", "sig_time", "entry_t", "kind", "entry", "stop", "R_pts", "exit", "exit_time", "gross_pts", "R"]


def lf_sha256(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def _minute(ix):
    return np.asarray(ix.hour * 60 + ix.minute)


def answer_key_list():
    """The owner's 3 design dates + the journal's real futures CBD / ENGD trades, one row per distinct signal."""
    out = list(OWNER_MISSED); seen = set()
    j = json.load(open(os.path.join(ROOT, "tools", "data", "setup_journal.json"), encoding="utf-8"))
    for t in j.get("trades", []):
        lab, sym = str(t.get("label", "")).upper(), str(t.get("sym")).upper()
        if lab in ("CBD", "ENGD") and t.get("asset") == "futures" and ROOT_OF.get(sym):
            k = (ROOT_OF[sym], str(t["date"]), t.get("signal_candle"))
            if k in seen:
                continue
            seen.add(k)
            out.append(k + ("%s real (journal n%s)" % (lab, t.get("n")),))
    return out


# ---------------------------------------------------------------- data
def load_1m(root, date_from, date_to):
    """ETH 1m bars (context source) and their 09:30-15:59 slice (signals, C1, trades). Master pinned by filename + id."""
    from augur_engine.data import list_masters, load_master_arrays
    fn, mid = MASTERS[root]
    ms = [x for x in list_masters() if x.get("filename") == fn]
    if len(ms) != 1 or int(ms[0]["id"]) != mid:
        sys.exit("MASTER PIN FAILED for %s: registry %s gives %s (want id %d)" % (fn, DATA_REPO, [x.get("id") for x in ms], mid))
    A = load_master_arrays(ms[0], date_from=date_from, date_to=date_to)
    ix = pd.DatetimeIndex(A["index"]); ix = ix.tz_convert(ET) if ix.tz is not None else ix.tz_localize(ET)
    eth = pd.DataFrame({"o": A["open"], "h": A["high"], "l": A["low"], "c": A["close"], "v": A["volume"]}, index=ix).astype(float)
    mn = _minute(eth.index)
    rth = eth[(mn >= RTH0) & (mn <= RTH1)].copy()
    rth["day"] = rth.index.date
    info = {"filename": fn, "id": mid, "source": ms[0].get("source"), "eth_rows": int(len(eth)), "rth_rows": int(len(rth)),
            "first": str(eth.index[0]), "last": str(eth.index[-1]), "fingerprint": A.get("fingerprint"), "registry": DATA_REPO}
    return eth, rth, info


def regular_days(rth, extra_holidays=()):
    """Regular sessions: last RTH bar starts at or after 13:10 (early closes end 13:14) and not a listed CME holiday."""
    last_min = pd.Series(_minute(rth.index), index=rth.index).groupby(rth["day"].values).max()
    hol = set(pd.to_datetime(list(CME_FULL_2025_26) + list(extra_holidays)).date)
    return set(d for d, m in last_min.items() if m >= STUB_LAST and d not in hol)


def bars_tf(eth, minutes):
    """Clock-anchored bars of `minutes` from 1m ETH bars (UTC floor = ET floor: whole-hour offsets). index = start (ET)."""
    key = eth.index.tz_convert("UTC").floor("%dmin" % minutes)
    g = eth.groupby(key)
    b = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "v": g.v.sum()})
    b.index = pd.DatetimeIndex(b.index).tz_convert(ET)
    b["end"] = b.index + pd.Timedelta(minutes=minutes)
    return b


def _asof(times, b, cols):
    k = b[["end"] + cols].sort_values("end").reset_index(drop=True)
    q = pd.DataFrame({"t": times}).reset_index(drop=True)
    return pd.merge_asof(q, k, left_on="t", right_on="end", direction="backward")


def context(eth, rth, regular):
    """Per RTH 1m bar: C1-C4 from ETH 5m / 30m bars that ENDED by the 1m bar's close; C1 vs the prior regular close."""
    out = pd.DataFrame(index=rth.index)
    close_t = rth.index + pd.Timedelta(minutes=1)
    for tf in (5, 30):
        b = bars_tf(eth, tf)
        b["sma200"] = b.c.rolling(200, min_periods=200).mean()
        b["ema20"] = b.c.ewm(span=20, adjust=False).mean()
        b["ema20_prev"] = b.ema20.shift(1)
        b["red3"] = ((b.c < b.o).astype(float).rolling(3).sum() == 3).astype(float)
        m = _asof(close_t, b, ["sma200", "ema20", "ema20_prev", "red3"])
        for col in ("sma200", "ema20", "ema20_prev", "red3"):
            out["%s_%d" % (col, tf)] = m[col].to_numpy()
    dclose = rth.groupby("day").c.last()
    reg = sorted(d for d in dclose.index if d in regular)
    prev_reg = {}
    j = -1
    for d in dclose.index:                      # the last REGULAR session strictly before d
        while j + 1 < len(reg) and reg[j + 1] < d:
            j += 1
        prev_reg[d] = dclose[reg[j]] if j >= 0 else np.nan
    out["prev_close"] = rth["day"].map(prev_reg).to_numpy(dtype=float)
    c = rth.c.to_numpy()
    out["C1"] = c < out.prev_close
    out["C2"] = (c < out.sma200_5) & (c < out.sma200_30)
    out["C3"] = (out.ema20_5 < out.ema20_prev_5) & (c < out.ema20_5) & (out.ema20_30 < out.ema20_prev_30) & (c < out.ema20_30)
    out["C4"] = out.red3_30 == 1.0
    out["regular"] = rth["day"].isin(regular).to_numpy()
    out["CTX"] = out.C1 & out.C2 & out.C3 & out.C4 & out.regular
    return out


def triggers(rth):
    """Per RTH 1m bar: CBD / ENGD flags (each reads only bars closed at or before this bar's close, same session)."""
    o, h, l, c, v = (rth[k].to_numpy() for k in ("o", "h", "l", "c", "v"))
    day = rth["day"].to_numpy()
    body = np.abs(c - o)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    tr[0] = h[0] - l[0]
    s_body = pd.Series(body).shift(1).rolling(LOOKBACK).mean().to_numpy()
    s_vol = pd.Series(v).shift(1).rolling(LOOKBACK).mean().to_numpy()
    atr14 = pd.Series(tr).shift(1).rolling(14).mean().to_numpy()
    lo_base = pd.Series(l).shift(1).rolling(BASE_N).min().to_numpy()
    hi_base = pd.Series(h).shift(1).rolling(BASE_N).max().to_numpy()
    lo3 = pd.Series(l).shift(1).rolling(ENGD_N).min().to_numpy()
    hi10 = pd.Series(h).shift(1).rolling(LH_N).max().to_numpy()
    cum_hi = pd.Series(h).groupby(day).cummax().to_numpy()
    sess_hi_before = np.r_[np.full(LH_N + 1, np.nan), cum_hi[:-(LH_N + 1)]]          # session high through bar i-11
    same_base = np.r_[np.zeros(BASE_N, bool), day[BASE_N:] == day[:-BASE_N]]          # bar i-15 in this session
    same_lh = np.r_[np.zeros(LH_N + 1, bool), day[LH_N + 1:] == day[:-(LH_N + 1)]]    # bar i-11 in this session
    mn = _minute(rth.index)
    in_win = (mn >= WIN0) & (mn <= WIN1)
    t0 = (c < o) & (body >= BODY_X * s_body) & (v >= VOL_X * s_vol) & in_win
    cbd = t0 & same_base & (c < lo_base) & ((hi_base - lo_base) <= BASE_ATR_K * atr14)
    engd = t0 & same_lh & (c < lo3) & (hi10 < sess_hi_before)
    return pd.DataFrame({"T0": t0, "CBD": cbd, "ENGD": engd, "atr14": atr14}, index=rth.index)


def five_min_high_trail(eth, rth):
    """For each RTH 1m bar i: the max high of the last five ETH 5m bars that ENDED by bar i's open."""
    b = bars_tf(eth, 5)
    b["hi5"] = b.h.rolling(5, min_periods=5).max()
    return _asof(rth.index, b, ["hi5"]).hi5.to_numpy()


# ---------------------------------------------------------------- trades
def simulate(rth, sig, cbd, engd, trail5, rule):
    """One exit rule; one position at a time; at most MAX_PER_DAY entries a session; shorts; points per contract."""
    if not (len(sig) == len(cbd) == len(engd) == len(trail5) == len(rth)):
        raise ValueError("simulate: array lengths differ")
    o, h, l, c = (rth[k].to_numpy() for k in ("o", "h", "l", "c"))
    day = rth["day"].to_numpy(); n = len(rth)
    last_of_day = np.r_[day[1:] != day[:-1], True]
    trades = []; busy_until = -1; per_day = {}
    for i in np.flatnonzero(sig):
        if i <= busy_until or i + 1 >= n or last_of_day[i]:        # a signal on a trade's exit bar is not taken
            continue
        if per_day.get(day[i], 0) >= MAX_PER_DAY:
            continue
        e = i + 1; entry = o[e]; stop = h[i]; R = stop - entry
        if not R > 0:                                              # the open is at or above the signal high: skipped
            continue
        per_day[day[i]] = per_day.get(day[i], 0) + 1
        tgt = entry - 2.0 * R
        half_done = False; half_px = None; cur_stop = stop; k = e; exit_px = None
        while True:
            if h[k] >= cur_stop:                                   # stop first; a gap through fills at the open
                exit_px = o[k] if o[k] >= cur_stop else cur_stop
                break
            if rule in ("E1", "E2") and not half_done and l[k] <= tgt:
                if rule == "E1":
                    exit_px = tgt; break
                half_done = True; half_px = tgt; cur_stop = min(cur_stop, entry)
                if h[k] >= cur_stop:                               # breakeven touched on the half bar: runner out at entry
                    exit_px = cur_stop; break
            if rule == "E2" and half_done and not last_of_day[k]:
                t = trail5[k + 1]
                if np.isfinite(t):
                    cur_stop = min(cur_stop, t)
            if last_of_day[k]:
                exit_px = c[k]; break
            k += 1
        pts = 0.5 * (entry - half_px) + 0.5 * (entry - exit_px) if (rule == "E2" and half_done) else entry - exit_px
        kind = "BOTH" if (cbd[i] and engd[i]) else ("CBD" if cbd[i] else ("ENGD" if engd[i] else None))
        if kind is None:
            raise ValueError("simulate: signal %d is neither CBD nor ENGD" % i)
        trades.append({"sig_i": int(i), "day": str(day[i]), "sig_time": rth.index[i].strftime("%H:%M"),
                       "entry_t": rth.index[e], "kind": kind, "entry": float(entry), "stop": float(stop), "R_pts": float(R),
                       "exit": float(exit_px), "exit_time": rth.index[k].strftime("%H:%M"), "gross_pts": float(pts),
                       "R": float(pts / R)})
        busy_until = k
    return pd.DataFrame(trades, columns=TRADE_COLS)


def daily(tr, sessions, cost, unit):
    """unit 'usd': (gross - cost) x $20 a point, 1 contract; unit 'R': net R x R_USD (fixed risk a trade)."""
    if tr.empty:
        return pd.Series(0.0, index=sessions)
    p = (tr.gross_pts - cost) * PV_NQ if unit == "usd" else (tr.gross_pts - cost) / tr.R_pts * R_USD
    return p.groupby(pd.to_datetime(tr.day)).sum().reindex(sessions, fill_value=0.0)


def boot_t(d):
    if len(d) <= 40 or d.std() == 0:
        return None
    rng = np.random.default_rng(SEED); x = d.to_numpy(); m = len(x); nb = int(np.ceil(m / 20))
    bs = [x[np.concatenate([np.arange(a, a + 20) for a in rng.integers(0, m - 19, nb)])[:m]].mean() for _ in range(2000)]
    return float(x.mean() / np.std(bs))


def read(tr, sessions, cost, lo=WF0, hi=WF1):
    from augur_engine.drawdowns import four_numbers
    t = tr[(tr.day >= lo) & (tr.day <= hi)]
    ss = sessions[(sessions >= pd.Timestamp(lo)) & (sessions <= pd.Timestamp(hi))]
    du, dr = daily(t, ss, cost, "usd"), daily(t, ss, cost, "R")
    fu, fr = four_numbers(du), four_numbers(dr)
    yrs = (ss[-1] - ss[0]).days / 365.25
    netp = t.gross_pts - cost
    return {"trades": int(len(t)), "trades_yr": len(t) / yrs if yrs else None, "net_usd": float(du.sum()),
            "roc30": fu.get("roc30"), "dd5": fu.get("dd5_usd"), "dd_pct_peak": fu.get("dd_pct_peak"), "sortino": fu.get("sortino"),
            "one_episode": fu.get("one_episode"),
            "R_curve": {"net_usd": float(dr.sum()), "roc30": fr.get("roc30"), "dd5": fr.get("dd5_usd"),
                        "dd_pct_peak": fr.get("dd_pct_peak"), "sortino": fr.get("sortino"), "one_episode": fr.get("one_episode")},
            "win_rate": float((netp > 0).mean()) if len(t) else None,
            "avg_win_pts": float(netp[netp > 0].mean()) if (netp > 0).any() else None,
            "avg_loss_pts": float(netp[netp <= 0].mean()) if (netp <= 0).any() else None,
            "mean_R_gross": float(t.R.mean()) if len(t) else None,
            "mean_R_net": float((netp / t.R_pts).mean()) if len(t) else None,
            "gross_pts_per_trade": float(t.gross_pts.mean()) if len(t) else None,
            "boot_t_R": boot_t(dr), "boot_t_usd": boot_t(du)}


def crown_trades(run_id, date_from, date_to):
    """A crown's own trades (its run doc: strategy, params, master, cost - the queue_guard loader), with ET times."""
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    import queue_guard as QG
    kw, d = QG._guard_kwargs_from_run(run_id, os.path.join(DATA_REPO, "serviceAccount.json"))
    m = find_master(kw["instrument"], kw["timeframe"], kw["session"], kw["source"])
    A = load_master_arrays(m, date_from=date_from, date_to=date_to)
    ix = pd.DatetimeIndex(A["index"]); ix = ix.tz_convert(ET) if ix.tz is not None else ix.tz_localize(ET)
    resolved, _, _ = QG.resolve_params(kw["strategy_file"], kw["params"])
    r = run_backtest(kw["strategy_file"], arrays=A, params=dict(resolved), cost_pts=kw["cost_pts"], return_trades=True)
    tf = pd.Timedelta(minutes=int(str(kw["timeframe"]).rstrip("m")))
    rows = [(ix[int(t[0])], ix[int(t[1])] + tf, int(t[3])) for t in (r or {}).get("trades") or []]
    ct = pd.DataFrame(rows, columns=["t_in", "t_out", "side"])
    ct["day"] = ct.t_in.dt.date.astype(str)
    return ct, {"run": run_id, "strategy": kw["strategy_file"], "master": m.get("filename"), "id": m.get("id"),
                "cost_pts": kw["cost_pts"], "trades": int(len(ct))}


def shadow_block(t_wf, sessions, crowns):
    """Precedent (tools/setups_r1_overlap.py): on EACH crown's flat days the rule nets > 0 and >= 30% of its own net."""
    own = float(((t_wf.gross_pts - COST_NQ) * PV_NQ).sum())
    blk = {"own_net_usd": own, "crowns": {}}
    ok_all = True
    for rid, ct in crowns.items():
        cdays = set(ct.day)
        sdays, ldays = set(ct[ct.side < 0].day), set(ct[ct.side > 0].day)
        flat = t_wf[~t_wf.day.isin(cdays)]
        fnet = float(((flat.gross_pts - COST_NQ) * PV_NQ).sum())
        ok = fnet > 0 and own > 0 and fnet >= 0.30 * own
        ok_all &= ok
        shorts = ct[ct.side < 0]
        ins = np.zeros(len(t_wf), bool)
        if len(shorts) and len(t_wf):
            ti = pd.DatetimeIndex(shorts.t_in).asi8; to = pd.DatetimeIndex(shorts.t_out).asi8
            order = np.argsort(ti); ti, to = ti[order], to[order]
            for j, et in enumerate(pd.DatetimeIndex(t_wf.entry_t).asi8):
                p = np.searchsorted(ti, et, side="right") - 1
                ins[j] = p >= 0 and to[:p + 1].max() > et
        blk["crowns"][rid] = {
            "flat_day_trades": int(len(flat)), "flat_day_net_usd": fnet, "flat_share_of_own": (fnet / own) if own > 0 else None,
            "passes": bool(ok),
            "trades_on_short_days": int(t_wf.day.isin(sdays).sum()),
            "trades_on_long_only_days": int((t_wf.day.isin(ldays) & ~t_wf.day.isin(sdays)).sum()),
            "trades_on_flat_days": int(len(flat)),
            "entry_inside_open_short_share": float(ins.mean()) if len(t_wf) else None,
            "read_short_days": read(t_wf[t_wf.day.isin(sdays)], sessions, COST_NQ),
            "read_long_only_days": read(t_wf[t_wf.day.isin(ldays) & ~t_wf.day.isin(sdays)], sessions, COST_NQ),
            "read_flat_days": read(flat, sessions, COST_NQ)}
    alld = set().union(*[set(ct.day) for ct in crowns.values()])
    blk["read_both_crowns_flat"] = read(t_wf[~t_wf.day.isin(alld)], sessions, COST_NQ)
    blk["shadow"] = not ok_all
    return blk


# ---------------------------------------------------------------- verdicts
def verdicts(rules, power):
    out = {}
    for rule, blk in rules.items():
        b = blk["NQ cost"]
        g = {"gross_above_cost": (b["gross_pts_per_trade"] if b["gross_pts_per_trade"] is not None else -1e9) > COST_NQ,
             "roc_above_0": (b["roc30"] if b["roc30"] is not None else -1e9) > 0,
             "not_one_episode": not bool(b["one_episode"]),
             "trades_ge_100": b["trades"] >= 100,
             "both_halves_positive": all(blk[k]["net_usd"] > 0 for k in blk if k.startswith("half "))}
        shadow = bool(blk["shadow"]["shadow"])
        t_need = T_PRIMARY if rule == PRIMARY else T_SECONDARY
        t_ok = (b["boot_t_R"] if b["boot_t_R"] is not None else -1e9) >= t_need
        if not all(g.values()):
            v = "FAIL"
        elif shadow:
            v = "CROWN SHADOW"
        elif t_ok:
            v = "PASS - EDGE"
        else:
            v = "PASS - MANAGER's bar, edge not shown"
        route = None
        if v == "PASS - EDGE":
            route = ("Auto-Validate candidate" if (b["trades_yr"] or 0) >= AV_TRADES_YR and (b["roc30"] or 0) >= AV_ROC
                     else "discretionary aid (below the Auto-Validate trade-rate / MDL bar)")
        elif v in ("PASS - MANAGER's bar, edge not shown", "CROWN SHADOW"):
            route = "discretionary aid"
        out[rule] = dict(g, verdict=v, route=route, noise_shadow=shadow, t_R=b["boot_t_R"], t_needed=t_need,
                         role="primary" if rule == PRIMARY else "secondary", power=power[rule]["label"],
                         note=("underpowered: a FAIL reads 'not shown', not 'dead'" if power[rule]["label"] == "UNDERPOWERED" else None))
    n_pass = sum(1 for r in out.values() if r["verdict"].startswith("PASS"))
    passing = [r for r in out if out[r]["verdict"].startswith("PASS")]
    forward = PRIMARY if PRIMARY in passing else (max(passing, key=lambda r: out[r]["t_R"] or -1e9) if passing else None)
    out["_summary"] = {"passes": "%d of 3" % n_pass, "goes_forward": forward}
    return out


# ---------------------------------------------------------------- selftest (synthetic bars only)
def selftest():
    days = pd.bdate_range("2015-03-02", periods=3)
    idx = pd.DatetimeIndex([pd.Timestamp(d.date().isoformat() + " 00:00", tz=ET) + pd.Timedelta(minutes=m)
                            for d in days for m in range(0, 1440) if not (17 * 60 <= m < 18 * 60)])
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 0.1, len(idx)))
    eth = pd.DataFrame({"o": c, "h": c + 0.2, "l": c - 0.2, "c": c, "v": 100.0}, index=idx)
    b5, b30 = bars_tf(eth, 5), bars_tf(eth, 30)
    d1 = days[1].date().isoformat()
    assert b5.loc[d1 + " 09:30"].end == pd.Timestamp(d1 + " 09:35", tz=ET), "5m 09:30 bar must end 09:35"
    assert b30.loc[d1 + " 09:30"].end == pd.Timestamp(d1 + " 10:00", tz=ET), "30m 09:30 bar must end 10:00"
    eth.loc[d1 + " 12:37", "h"] = 500.0                      # inside the 12:35-12:40 5m bar
    mn = _minute(eth.index); rth = eth[(mn >= RTH0) & (mn <= RTH1)].copy(); rth["day"] = rth.index.date
    tr5 = pd.Series(five_min_high_trail(eth, rth), index=rth.index)
    assert tr5[d1 + " 13:00"] == 500.0 and tr5[d1 + " 12:40"] == 500.0, "trail must read the 12:35 5m bar from 12:40"
    assert tr5[d1 + " 12:39"] < 500.0, "trail must not read a 5m bar before it ends"
    assert tr5[d1 + " 13:04"] == 500.0 and tr5[d1 + " 13:05"] < 500.0, "trail holds the last five ended 5m bars only"
    # CBD can fire at 09:45 (base 09:30-09:44)
    x = rth.copy()
    blk = (x.day == days[2].date())
    m2 = _minute(x.index)
    base = blk & (m2 >= RTH0) & (m2 < WIN0)
    x.loc[base, ["o", "c"]] = 100.0; x.loc[base, "h"] = 100.5; x.loc[base, "l"] = 99.5
    sbar = blk & (m2 == WIN0)
    x.loc[sbar, "o"] = 100.0; x.loc[sbar, "c"] = 95.0; x.loc[sbar, "h"] = 100.1; x.loc[sbar, "l"] = 94.9; x.loc[sbar, "v"] = 1000.0
    x.loc[base, "o"] = 100.05
    tg = triggers(x)
    assert bool(tg.CBD[sbar].iloc[0]), "CBD must be able to fire at 09:45"
    # E2: breakeven touched on the half bar exits the runner at entry
    ix = pd.date_range(d1 + " 10:00", periods=6, freq="1min", tz=ET)
    s = pd.DataFrame({"o": [100, 100, 99, 95, 95, 95], "h": [104, 101, 99.5, 101, 96, 96], "l": [99, 99, 98, 89, 94, 94],
                      "c": [100, 100, 99, 95, 95, 95], "v": 1.0}, index=ix, dtype=float); s["day"] = s.index.date
    sig = np.array([True, False, False, False, False, False]); f = np.zeros(6, bool)
    t2 = simulate(s, sig, sig, f, np.full(6, np.nan), "E2")
    # entry 100 (bar 1 open), stop 104, R 4, target 92: bar 3 low 89 hits the target, high 101 >= breakeven 100
    assert len(t2) == 1 and t2.exit.iloc[0] == 100.0 and abs(t2.gross_pts.iloc[0] - 4.0) < 1e-9, t2.to_dict("records")
    e = simulate(s, np.zeros(6, bool), f, f, np.full(6, np.nan), "E1")
    assert list(e.columns) == TRADE_COLS and e.empty
    print("selftest OK (bar stamps, 5m trail timing, CBD at 09:45, E2 same-bar breakeven, empty trade frame)")


# ---------------------------------------------------------------- main
def _f(x, nd=1):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else ("%.*f" % (nd, x))


def _line(lab, x):
    r = x["R_curve"]
    return ("   %-34s trades %4d  net $%9.0f  ROC %s  DD5 $%s  DD%% %s  Sortino %s | R-curve ROC %s  DD5 $%s  DD%% %s  Sortino %s" % (
        lab, x["trades"], x["net_usd"], _f(x["roc30"]), _f(x["dd5"], 0), _f(x["dd_pct_peak"], 2), _f(x["sortino"], 2),
        _f(r["roc30"]), _f(r["dd5"], 0), _f(r["dd_pct_peak"], 2), _f(r["sortino"], 2)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"C:\EdgeLog\_anatomy_cache\ctxshort_r1")
    ap.add_argument("--selftest-only", action="store_true")
    a = ap.parse_args(argv)
    selftest()
    if a.selftest_only:
        return
    sha = lf_sha256(PREREG)
    print("prereg LF sha256", sha, "| harness LF sha256", lf_sha256(os.path.abspath(__file__)))
    if EXPECT_PREREG_SHA is None or sha != EXPECT_PREREG_SHA:
        sys.exit("PREREG HASH MISMATCH (or not frozen) - stopping")
    os.makedirs(a.out, exist_ok=True)
    res = {"prereg_sha256": sha}
    # ---------- Stage 0: pins, census + power line (no outcomes) ----------
    eth, rth, info = load_1m("NQ", WARM0, WF1)
    res["master"] = info
    print("master", info)
    regular = regular_days(rth)
    stubs = sorted(set(rth["day"]) - regular)
    print("holiday stubs / short sessions excluded from signals:", len(stubs), [str(d) for d in stubs][:40])
    b5 = bars_tf(eth, 5); first = rth.index[0].date().isoformat()
    assert b5.loc[first + " 09:30"].end == pd.Timestamp(first + " 09:35", tz=ET)
    ctx, trg = context(eth, rth, regular), triggers(rth)
    cbd = (ctx.CTX & trg.CBD).to_numpy(); engd = (ctx.CTX & trg.ENGD).to_numpy(); sig = cbd | engd
    wf = np.asarray((rth.index >= pd.Timestamp(WF0, tz=ET)) & (rth.index < pd.Timestamp(WF1, tz=ET) + pd.Timedelta(days=1)))
    cen = pd.DataFrame({"year": rth.index.year, "day": rth["day"].values, "CTX_bar": ctx.CTX.to_numpy(),
                        "CBD_only": cbd & ~engd, "ENGD_only": engd & ~cbd, "BOTH": cbd & engd, "signal": sig,
                        "bare_CBD": trg.CBD.to_numpy(), "bare_ENGD": trg.ENGD.to_numpy()})[wf]
    yr = cen.groupby("year")[["CBD_only", "ENGD_only", "BOTH", "signal", "bare_CBD", "bare_ENGD"]].sum()
    yr["ctx_sessions"] = cen[cen.CTX_bar].groupby("year").day.nunique()
    capped = cen.groupby("day").signal.sum().clip(upper=MAX_PER_DAY)
    yr["capped_signals"] = capped.groupby(pd.DatetimeIndex(pd.to_datetime(capped.index)).year).sum()
    print("\nSTAGE 0 CENSUS (WF signal bars, context on; no outcomes):"); print(yr.fillna(0).astype(int).to_string())
    n_cap = int(capped.sum()); wf_sessions = sorted(d for d in set(cen.day) if d in regular)
    yrs = (pd.Timestamp(WF1) - pd.Timestamp(WF0)).days / 365.25
    print("signals %d (CBD only %d, ENGD only %d, BOTH %d); capped at %d a session: %d = %.1f a year (upper bound on trades)" % (
        cen.signal.sum(), cen.CBD_only.sum(), cen.ENGD_only.sum(), cen.BOTH.sum(), MAX_PER_DAY, n_cap, n_cap / yrs))
    power = {}
    for rule, sd in SD_ASSUMED.items():
        mde = 2.8 * sd / np.sqrt(max(n_cap, 1))
        lab = "powered" if PRIOR_R >= mde else "UNDERPOWERED"
        power[rule] = {"n_capped": n_cap, "sd_assumed_R": sd, "mde_R_80pct": float(mde), "prior_R": PRIOR_R, "label": lab}
        print("power line %s: n %d -> MDE %.3f R (80%%, SD %.1f R) vs prior %.2f R -> %s" % (rule, n_cap, mde, sd, PRIOR_R, lab))
    res["census"] = yr.fillna(0).astype(int).reset_index().to_dict("records"); res["power"] = power
    res["wf_regular_sessions"] = len(wf_sessions)
    # ---------- Stage 1: WF outcomes ----------
    sessions = pd.DatetimeIndex(pd.to_datetime([str(d) for d in sorted(set(rth["day"]) & regular)]))
    trail5 = five_min_high_trail(eth, rth)
    crowns, cinfo = {}, {}
    for rid in CROWNS:
        crowns[rid], cinfo[rid] = crown_trades(rid, "2015-01-01", WF1)
        crowns[rid] = crowns[rid][(crowns[rid].day >= WF0) & (crowns[rid].day <= WF1)]
    res["crowns"] = cinfo; print("crowns", cinfo)
    res["rules"] = {}
    for rule in ("E1", "E2", "E3"):
        tr = simulate(rth, sig, cbd, engd, trail5, rule)
        tr.to_csv(os.path.join(a.out, "trades_%s.csv" % rule), index=False)
        t_wf = tr[(tr.day >= WF0) & (tr.day <= WF1)]
        blk = {"NQ cost": read(t_wf, sessions, COST_NQ), "NQ cost +1 tick a side": read(t_wf, sessions, COST_NQ + 2 * TICK),
               "MNQ cost": read(t_wf, sessions, COST_MNQ)}
        for lo, hi in HALVES:
            blk["half %s..%s" % (lo, hi)] = read(t_wf, sessions, COST_NQ, lo, hi)
        blk["ex Feb-Apr 2020"] = read(t_wf[~((t_wf.day >= "2020-02-01") & (t_wf.day <= "2020-04-30"))], sessions, COST_NQ)
        blk["ex top 3 trades"] = read(t_wf.drop(t_wf.nlargest(3, "gross_pts").index), sessions, COST_NQ)
        blk["any CBD (CBD + BOTH)"] = read(t_wf[t_wf.kind.isin(["CBD", "BOTH"])], sessions, COST_NQ)
        blk["any ENGD (ENGD + BOTH)"] = read(t_wf[t_wf.kind.isin(["ENGD", "BOTH"])], sessions, COST_NQ)
        blk["BOTH"] = read(t_wf[t_wf.kind == "BOTH"], sessions, COST_NQ)
        blk["shadow"] = shadow_block(t_wf, sessions, crowns)
        res["rules"][rule] = blk
        b = blk["NQ cost"]
        print("\n== %s (%s)  trades %d (%.1f/yr)  net $%.0f  ROC@30k %s  DD5 $%s  DD%% %s  Sortino %s  one-episode %s" % (
            rule, "primary" if rule == PRIMARY else "secondary", b["trades"], b["trades_yr"] or 0, b["net_usd"], _f(b["roc30"]),
            _f(b["dd5"], 0), _f(b["dd_pct_peak"], 2), _f(b["sortino"], 2), b["one_episode"]))
        print("   gross %s pts/trade vs cost %.3f | win %s%%  avg win %s / avg loss %s pts | mean R gross %s net %s | boot t R %s  $ %s" % (
            _f(b["gross_pts_per_trade"], 2), COST_NQ, _f(100 * b["win_rate"] if b["win_rate"] is not None else None, 0),
            _f(b["avg_win_pts"]), _f(b["avg_loss_pts"]), _f(b["mean_R_gross"], 3), _f(b["mean_R_net"], 3),
            _f(b["boot_t_R"], 2), _f(b["boot_t_usd"], 2)))
        for lab in [k for k in blk if k not in ("shadow",)]:
            print(_line(lab, blk[lab]))
        sh = blk["shadow"]
        for rid, cr in sh["crowns"].items():
            print("   crown #%d: on its short days %d, long-only days %d, flat days %d trades; entries inside an open short %s%%;"
                  " flat-day net $%.0f = %s of own -> %s" % (rid, cr["trades_on_short_days"], cr["trades_on_long_only_days"],
                  cr["trades_on_flat_days"], _f(100 * cr["entry_inside_open_short_share"] if cr["entry_inside_open_short_share"] is not None else None, 0),
                  cr["flat_day_net_usd"], _f(cr["flat_share_of_own"], 2), "pass" if cr["passes"] else "FAIL"))
            for k in ("read_short_days", "read_long_only_days", "read_flat_days"):
                print(_line("#%d %s" % (rid, k[5:]), cr[k]))
        print(_line("both crowns flat", sh["read_both_crowns_flat"]))
    res["verdicts"] = verdicts(res["rules"], power)
    print("\nVERDICTS:", json.dumps(res["verdicts"], indent=1, default=str))
    # ---------- Stage 2: answer key (flags only) ----------
    res["answer_key"] = answer_key()
    json.dump(res, open(os.path.join(a.out, "ctxshort_r1_result.json"), "w"), indent=1, default=str)


def answer_key():
    print("\nSTAGE 2 ANSWER KEY (frozen rule, 2026 bars, flags only, AFTER the WF read):")
    rows = []
    key = answer_key_list()
    for root in ("NQ", "ES"):
        keys = [k for k in key if k[0] == root]
        if not keys:
            continue
        eth, rth, info = load_1m(root, "2025-11-01", "2026-10-16")
        regular = regular_days(rth)
        ctx, trg = context(eth, rth, regular), triggers(rth)
        for _, d, t, lab in keys:
            day = rth[rth["day"].astype(str) == d]
            if day.empty:
                rows.append({"root": root, "date": d, "label": lab, "note": "no bars"}); print(root, d, lab, "no bars"); continue
            hh, mm = (int(x) for x in str(t).split(":"))
            reachable = WIN0 <= hh * 60 + mm <= WIN1
            fires = [{"time": i.strftime("%H:%M"), "kind": "BOTH" if (trg.CBD[i] and trg.ENGD[i]) else ("CBD" if trg.CBD[i] else "ENGD"),
                      "ctx": bool(ctx.CTX[i]), "flags": {c: bool(ctx[c][i]) for c in ("C1", "C2", "C3", "C4")}}
                     for i in day.index if (trg.CBD[i] or trg.ENGD[i])]
            near = lambda f: abs((pd.Timestamp(d + " " + f["time"]) - pd.Timestamp(d + " " + t)).total_seconds()) <= 300
            hit = [f for f in fires if f["ctx"] and near(f)]
            trig_only = [f for f in fires if not f["ctx"] and near(f)]
            at = day.index[_minute(day.index) == hh * 60 + mm]
            flags_at = {c: bool(ctx[c][at[0]]) for c in ("C1", "C2", "C3", "C4", "CTX")} if len(at) else None
            rows.append({"root": root, "date": d, "label": lab, "owner_candle": t, "reachable": reachable,
                         "rule_fired_within_5min": hit, "trigger_only_within_5min": trig_only, "flags_at_owner_candle": flags_at})
            print(root, d, lab, t, "| reachable by construction" if reachable else "| NOT reachable (outside 09:45-11:29)",
                  "| rule fired within 5 min:", [(f["time"], f["kind"]) for f in hit],
                  "| trigger only (context off):", [(f["time"], f["kind"]) for f in trig_only], "| flags at the candle:", flags_at)
    return rows


if __name__ == "__main__":
    main()
