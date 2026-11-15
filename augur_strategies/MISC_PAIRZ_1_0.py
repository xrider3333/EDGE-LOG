# AUGUR-SOURCE: claude-review
"""MISC PAIRZ 1.0 - intraday z-score reversion of same-industry megacap pairs, $100k a leg, flat the same day.

Provenance: OPUS-HUNT round 7, strategy 76 (PAIRZ-INTRA), cell 76c
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S76: PREREG.md, RESULTS.md, s76_lib.py, s76_conf.py).
Defaults = cell 76c exactly: 76a's rule (z 2.0) with the opposite-sign exit check running through the 15:40 bar
and the time exit at the 15:50 bar's close (16:00). NOT A BLIND READ: the hunt read 76c on 2016-07..2025-06 (FAIL,
Route B missed: CONF-B 2023-25H1 net t 0.06; book lift inside the no-edge band) and 2017-04..2020-12 was the
proposer's selection stretch. The 76c exit overlaps strategy 23's 15:30 -> close window. This file exists so the
engine's Auto-Validate can judge it.

-- The rule -----------------------------------------------------------------------------
Universe: 39 frozen same-industry pairs (leg A / leg B) of 59 megacaps (`PAIRS`); `high_corr_only` keeps the 20
pairs whose 2017-04..2020-12 daily correlation was >= 0.80 (the hunt's 76d list, frozen from DISC only).
Bars: 10-minute bars 09:30 .. 15:50 from the side panel; a bar stamped T covers T..T+10 and is known at T+10.
Pair-day d is skipped if d or the session before is not FULL (half days, the day after one), either leg lacks its
d-1 15:50 bar, either leg has a corporate-action break (raw / split-adjusted daily close ratio moves > 0.5% from
d-1 to d, or a frozen spin-off ex-date), or a leg's d-1 15:50 close is > 8% off its split-adjusted daily close.
Before the open of d:
  anchor_X = leg X's d-1 15:50 close;
  u_s = ln(A 15:50 close s / s-1) - ln(B ...) on valid sessions; sigma_d = std (ddof 1) of the valid u over the
  `sigma_len` FULL sessions ending d-1, at least ceil(0.75 x sigma_len) of them valid;
  cost_X = 2 x `spread_cents` / P_X + 2 x `fee_bps` with P_X = raw daily close on d-1; the pair trades only when
  cost_A + cost_B <= `max_cost_bp`.
At the close of each bar j from 09:30 + `first_sig_offset` through 15:00: z_j = (ln(A_j / anchor_A) -
ln(B_j / anchor_B)) / sigma_d. ENTRY at the open of bar j+1 for the first j with |z_j| >= `z_entry`: z > 0 -> short
A / long B, z < 0 -> long A / short B, $`notional` a leg. One trade per pair per day.
EXIT at the open of bar k+1 for the first k after j (k <= the bar starting `flat_min` - 10 minutes after 15:00) whose
z_k x sign(z_j) <= `exit_z` (0 = the spread crossed back through zero); otherwise at the time exit: the open of the
bar `flat_min` minutes after 15:00, or the 15:50 bar's close when `flat_min` = 60. A pair-day missing any bar of
either leg from 09:30 through its exit bar gives no trade (no forward fill).

INFORMATION TIMES: anchors, sigma, the cost filter, the corporate-action and basis checks read d-1 or earlier
(sigma's rolling window is shifted one full session; P is d-1's raw close); z_j uses the close of bar j, known at
j+10, and the fill is the NEXT bar's open; the exit test uses a closed bar's z and fills at the next open. The
"bars present through the exit" check is the harness's no-forward-fill rule (a missing print voids the pair-day).

-- Data ---------------------------------------------------------------------------------
THE MASTER IS ONLY THE CLOCK (SPY 5m RTH, alpaca_split_rth). Prices come from the pinned side panel
    C:/EdgeLog/alpaca_cache/pairz_panel/pairz_panel_v1.npz   (built by tools/misc_pairz_panel.py)
with the harness's exact inputs (tbis_r3 / eodrev_u100 10m bars, siporb daily raw / split closes), 2016-01-04 ..
2026-06-30. No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.

-- Sizing and costs (INSIDE the plugin - job cost_pts 0, mult 1) --------------------------
PnL per leg = side x notional x (exit / entry - 1). Cost per leg per crossing = raw shares x `spread_cents` +
`fee_bps` x crossing notional (the hunt's model: 1 cent a share + 0.3 bp). Borrow 0, dividends not modelled
(intraday only). PnL is DOLLARS in the trade tuple's field 2; ONE trade a session = the sum of that day's pair
trades (entry bar = the day's first fill, exit bar = its last exit).

-- Auto-Validate ranges -------------------------------------------------------------------
z_entry / exit_z / sigma_len / max_cost_bp / flat_min / first_sig_offset / high_corr_only are OPEN; notional and
both cost knobs are pinned.
"""
import hashlib
import math
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC PAIRZ 1.0 · intraday z-score reversion of same-industry megacap pairs (opus hunt 76c)'
DESCRIPTION = ("39 same-industry megacap pairs: when the pair's move since yesterday's 15:50 close reaches z_entry "
               "daily sigmas, sell the rich leg and buy the cheap one ($100k a leg) at the next 10-minute open; exit "
               "when the spread crosses back (or at the flat time, default the 16:00 close). The SPY 5m master is "
               "the clock only; prices come from a pinned side panel. Costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "SPY", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/pairz_panel/pairz_panel_v1.npz"
PANEL_SHA256 = "774cfb758d2b335142a59eeeb1249b0c6a56a698c81c424ba10447c173d382cf"

PAIRS = [("MA", "V"), ("KO", "PEP"), ("HD", "LOW"), ("JPM", "BAC"), ("JPM", "C"), ("BAC", "C"), ("BAC", "WFC"),
         ("JPM", "WFC"), ("C", "WFC"), ("XOM", "CVX"), ("CVX", "COP"), ("XOM", "COP"), ("COP", "EOG"), ("MPC", "VLO"),
         ("SLB", "HAL"), ("NVDA", "AMD"), ("MSFT", "ORCL"), ("MRK", "PFE"), ("VZ", "T"), ("UNH", "CI"), ("UNH", "HUM"),
         ("GS", "MS"), ("WMT", "COST"), ("UPS", "FDX"), ("AMAT", "LRCX"), ("LRCX", "KLAC"), ("TXN", "ADI"),
         ("CSX", "UNP"), ("MO", "PM"), ("DAL", "UAL"), ("CAT", "DE"), ("TMO", "DHR"), ("PG", "KO"), ("JNJ", "PFE"),
         ("MCD", "SBUX"), ("AXP", "MA"), ("MS", "SCHW"), ("MET", "AIG"), ("USB", "WFC")]
# The hunt's 76d list: DISC (2017-04..2020-12) daily-correlation >= 0.80, frozen in PREREG.md before CONF.
PAIRS_CORR80 = [("MA", "V"), ("HD", "LOW"), ("JPM", "BAC"), ("JPM", "C"), ("BAC", "C"), ("BAC", "WFC"),
                ("JPM", "WFC"), ("C", "WFC"), ("XOM", "CVX"), ("CVX", "COP"), ("XOM", "COP"), ("COP", "EOG"),
                ("MPC", "VLO"), ("SLB", "HAL"), ("GS", "MS"), ("AMAT", "LRCX"), ("LRCX", "KLAC"), ("TXN", "ADI"),
                ("DAL", "UAL"), ("USB", "WFC")]
# Frozen spin-off ex-dates (the hunt's list + FDX's freight spin-off from the corporate-actions file, in the lockbox).
SPINOFF = {("PFE", 20201116), ("MRK", 20210603), ("T", 20220411), ("DHR", 20231002), ("FDX", 20260601)}

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "label": "Dollars a leg", "tooltip": "Fixed. Each pair trade is this many dollars long and short."},
    "spread_cents": {"default": 1.0, "min": 1.0, "max": 1.0, "step": 0.5, "type": "float",
                     "label": "Cost (cents a share a crossing)",
                     "tooltip": "Fixed: one cent a share on every entry and exit print (the hunt's cost)."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "step": 0.1, "type": "float",
                "label": "Fees (bp a crossing)", "tooltip": "Fixed: 0.3 bp of the crossing notional per leg."},
    "z_entry": {"hard_min": 1.0, "default": 2.0, "min": 1.5, "max": 3.0, "step": 0.25, "type": "float",
                "label": "Entry z (daily sigmas)",
                "tooltip": "Enter when the pair's move since yesterday's 15:50 close is at least this many daily sigmas."},
    "exit_z": {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.25, "type": "float",
               "label": "Exit z",
               "tooltip": "Exit at the next open once z (signed toward the trade) is back to this level. 0 = crossed zero."},
    "sigma_len": {"hard_min": 10, "default": 20, "min": 10, "max": 60, "step": 10, "type": "int",
                  "label": "Sigma window (full sessions)",
                  "tooltip": "Full sessions of daily spread changes in sigma, ending the session before; 75% must be valid."},
    "max_cost_bp": {"hard_min": 1.0, "default": 5.0, "min": 3.0, "max": 7.0, "step": 1.0, "type": "float",
                    "label": "Pair cost cap (bp round trip)",
                    "tooltip": "Trade a pair only when both legs' round-trip cost (cents at yesterday's price + fees) sum to at most this."},
    "flat_min": {"hard_min": 20, "default": 60, "min": 20, "max": 60, "step": 10, "type": "int",
                 "label": "Flat time (minutes after 15:00)",
                 "tooltip": "Time exit. 60 = the 16:00 close (cell 76c); 20 = the 15:20 open (cell 76a)."},
    "first_sig_offset": {"default": 0, "min": 0, "max": 30, "step": 10, "type": "int",
                         "label": "First signal bar (minutes after 09:30)",
                         "tooltip": "Earliest bar whose close can trigger; 0 = the 09:30 bar (fill 09:40)."},
    "high_corr_only": {"default": False, "type": "bool", "label": "Only the 20 high-correlation pairs",
                       "tooltip": "ON = the hunt's 76d list (2017-20 daily correlation >= 0.80). OFF = all 39 pairs."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 76c)": {"z_entry": [2.0], "exit_z": [0.0], "sigma_len": [20], "max_cost_bp": [5.0],
                                   "flat_min": [60], "first_sig_offset": [0], "high_corr_only": [False]},
    "Medium (the hunt's cells + neighbours)": {"z_entry": [1.5, 2.0, 2.5, 3.0], "exit_z": [0.0, 0.5],
                                               "sigma_len": [20, 40], "max_cost_bp": [4.0, 5.0, 6.0],
                                               "flat_min": [20, 40, 60], "first_sig_offset": [0, 10],
                                               "high_corr_only": [False, True]},
}

PNL_UNITS = "usd"

_NB = 39                     # 10m bars 09:30 .. 15:50
_J_LAST = 33                 # last signal bar: 15:00
_CACHE = {}                  # per-process: the panel, per-pair frames, daily PnL by config


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_PAIRZ_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        p = {"dates": z["dates"].astype("int64"), "names": [str(x) for x in z["names"]],
             "full": z["full"].astype(bool), "O": z["O"], "C": z["C"], "raw": z["raw"], "split": z["split"]}
    _CACHE["panel"] = p
    return p


def _prev(x, fill):
    """x shifted one session later (row d holds row d-1); row 0 = fill."""
    out = np.empty_like(x)
    out[0] = fill
    out[1:] = x[:-1]
    return out


def _pair_base(p, a, b):
    """Everything about pair (a, b) that does not depend on a parameter."""
    key = ("base", a, b)
    if key in _CACHE:
        return _CACHE[key]
    ix = {s: i for i, s in enumerate(p["names"])}
    ia, ib = ix[a], ix[b]
    full = p["full"]; dates = p["dates"]
    prev_full = _prev(full, False)
    with np.errstate(divide="ignore", invalid="ignore"):
        q = p["raw"] / p["split"]
        brk, mis = {}, {}
        for x, i in ((a, ia), (b, ib)):
            qx = q[:, i]
            qb = ~(np.abs(qx / _prev(qx, np.nan) - 1) <= 0.005)                  # NaN -> break
            so = np.array([(x, int(d)) in SPINOFF for d in dates])
            brk[x] = qb | so
            c1 = p["C"][:, i, -1].astype(np.float64)
            mis[x] = ~(np.abs(c1 / p["split"][:, i] - 1) <= 0.08)               # NaN -> mismatch
        ca = p["C"][:, ia, :].astype(np.float64); cb = p["C"][:, ib, :].astype(np.float64)
        oa = p["O"][:, ia, :].astype(np.float64); ob = p["O"][:, ib, :].astype(np.float64)
        anc_a = _prev(ca[:, -1], np.nan); anc_b = _prev(cb[:, -1], np.nan)       # d-1 15:50 closes
        mis_prev = _prev(mis[a] | mis[b], True)
        u = np.log(ca[:, -1] / anc_a) - np.log(cb[:, -1] / anc_b)
        uvalid = full & prev_full & np.isfinite(u) & ~brk[a] & ~brk[b] & ~(mis[a] | mis[b]) & ~mis_prev
        Pa = _prev(p["raw"][:, ia], np.nan); Pb = _prev(p["raw"][:, ib], np.nan)  # d-1 raw closes
        S = np.log(ca / anc_a[:, None]) - np.log(cb / anc_b[:, None])
    skip = (~full) | (~prev_full) | ~np.isfinite(anc_a) | ~np.isfinite(anc_b) | brk[a] | brk[b] | mis_prev
    pre_ok = ~skip & np.isfinite(Pa) & np.isfinite(Pb)
    complete = np.isfinite(oa) & np.isfinite(ob) & np.isfinite(ca) & np.isfinite(cb)
    cum_ok = np.cumprod(complete, axis=1).astype(bool)                            # bars 0..i all present
    cum_ok = np.concatenate([cum_ok, cum_ok[:, -1:]], axis=1)                     # index 39 = through bar 38
    pa = np.concatenate([oa, ca[:, -1:]], axis=1); pb = np.concatenate([ob, cb[:, -1:]], axis=1)
    out = {"u": np.where(uvalid, u, np.nan), "S": S, "pre_ok": pre_ok, "Pa": Pa, "Pb": Pb,
           "Ra": Pa / anc_a, "Rb": Pb / anc_b, "cum_ok": cum_ok, "pa": pa, "pb": pb}
    _CACHE[key] = out
    return out


def _sigma(p, base, L):
    """Std of the valid u over the L full sessions ending the full session BEFORE d (NaN off full days)."""
    full = p["full"]
    fidx = np.flatnonzero(full)
    mp = int(math.ceil(0.75 * int(L)))
    sd = pd.Series(base["u"][fidx]).rolling(int(L), min_periods=mp).std().shift(1).to_numpy()
    sig = np.full(len(full), np.nan)
    sig[fidx] = sd
    return sig


def _pair_trades(p, a, b, notional, spread_cents, fee_bps, z_entry, exit_z, sigma_len, max_cost_bp, flat_min,
                 first_sig_offset):
    """Trades of one pair for one config: arrays (row, fill index, exit index, gross $, cost $)."""
    base = _pair_base(p, a, b)
    skey = ("sigma", a, b, int(sigma_len))
    if skey not in _CACHE:
        _CACHE[skey] = _sigma(p, base, sigma_len)
    sigma = _CACHE[skey]
    cpx = 2.0 * float(spread_cents) / 100.0
    with np.errstate(divide="ignore", invalid="ignore"):
        cost_ex = (cpx / base["Pa"] + 2 * float(fee_bps) * 1e-4) + (cpx / base["Pb"] + 2 * float(fee_bps) * 1e-4)
        elig = base["pre_ok"] & np.isfinite(sigma) & (sigma > 0) & (cost_ex <= float(max_cost_bp) * 1e-4)
    rows = np.flatnonzero(elig)
    empty = (np.zeros(0, np.int64),) * 3 + (np.zeros(0),) * 2
    if len(rows) == 0:
        return empty
    z = base["S"][rows] / sigma[rows, None]
    j0 = int(first_sig_offset) // 10
    trig = np.isfinite(z) & (np.abs(z) >= float(z_entry))
    trig[:, :j0] = False
    trig[:, _J_LAST + 1:] = False
    has = trig.any(axis=1)
    rows = rows[has]; z = z[has]
    if len(rows) == 0:
        return empty
    js = np.argmax(trig[has], axis=1)
    n = len(rows); ar = np.arange(n)
    sj = np.sign(z[ar, js])
    tex = 39 if int(flat_min) >= 60 else 33 + int(flat_min) // 10      # fill index of the time exit
    kmax = tex - 1                                                        # last bar whose close can trigger the exit
    E = np.full(n, tex, np.int64)
    done = np.zeros(n, bool)
    for k in range(int(js.min()) + 1, kmax + 1):
        zk = z[:, k]
        hit = ~done & (k > js) & np.isfinite(zk) & (sj * zk <= float(exit_z))
        E[hit] = k + 1
        done |= hit
    ok = base["cum_ok"][rows, E]
    rows, js, E, sj = rows[ok], js[ok], E[ok], sj[ok]
    pa = base["pa"][rows]; pb = base["pb"][rows]
    m = np.arange(len(rows))
    ea, eb = pa[m, js + 1], pb[m, js + 1]
    xa, xb = pa[m, E], pb[m, E]
    side = -sj                                                            # +1 = long A / short B
    N = float(notional)
    gross = side * N * ((xa / ea - 1) - (xb / eb - 1))
    sha = N / (ea * base["Ra"][rows]); shb = N / (eb * base["Rb"][rows])
    c1 = float(spread_cents) / 100.0; f = float(fee_bps) * 1e-4
    cost = (2 * sha * c1 + f * N * (1 + xa / ea)) + (2 * shb * c1 + f * N * (1 + xb / eb))
    return rows, js + 1, E, gross, cost


def _daily(p, notional, spread_cents, fee_bps, z_entry, exit_z, sigma_len, max_cost_bp, flat_min, first_sig_offset,
           high_corr_only):
    """{yyyymmdd: (net $, first fill bar index, last exit bar index)} for one config, over every panel session."""
    key = ("day", float(notional), float(spread_cents), float(fee_bps), float(z_entry), float(exit_z), int(sigma_len),
           float(max_cost_bp), int(flat_min), int(first_sig_offset), bool(high_corr_only))
    if key not in _CACHE:
        nd = len(p["dates"])
        net = np.zeros(nd); cnt = np.zeros(nd, np.int64)
        f0 = np.full(nd, 99, np.int64); x1 = np.full(nd, -1, np.int64)
        for a, b in (PAIRS_CORR80 if high_corr_only else PAIRS):
            r, fi, ei, g, c = _pair_trades(p, a, b, notional, spread_cents, fee_bps, z_entry, exit_z, sigma_len,
                                           max_cost_bp, flat_min, first_sig_offset)
            np.add.at(net, r, g - c)
            np.add.at(cnt, r, 1)
            np.minimum.at(f0, r, fi)
            np.maximum.at(x1, r, ei)
        hit = np.flatnonzero(cnt > 0)
        _CACHE[key] = {int(p["dates"][i]): (float(net[i]), int(f0[i]), int(x1[i])) for i in hit}
    return _CACHE[key]


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 100000, spread_cents: float = 1.0, fee_bps: float = 0.3,
                 z_entry: float = 2.0, exit_z: float = 0.0, sigma_len: int = 20, max_cost_bp: float = 5.0,
                 flat_min: int = 60, first_sig_offset: int = 0, high_corr_only: bool = False,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None:
        return None
    p = _panel()
    if p is None:
        return None
    o = np.asarray(opens, float); c = np.asarray(closes, float)
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    date = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    minute = (idx.hour * 60 + idx.minute).to_numpy()
    days = _daily(p, notional, spread_cents, fee_bps, z_entry, exit_z, sigma_len, max_cost_bp, flat_min,
                  first_sig_offset, high_corr_only)
    trades = []
    cut = np.flatnonzero(np.diff(date) != 0) + 1
    starts = np.concatenate([[0], cut]); ends = np.concatenate([cut, [n]])
    for a, b in zip(starts, ends):
        if _stop_event is not None and _stop_event.is_set():
            return None
        v = days.get(int(date[a]))
        if v is None:
            continue
        m = minute[a:b]
        fm = 570 + 10 * v[1]                                   # the day's first fill (open of that minute)
        e = np.flatnonzero(m == fm)
        if v[2] >= 39:                                         # exit at the 16:00 close: the session's last bar
            if len(e) == 0 or m[-1] < 955:
                continue
            xb = b - 1
            xp = float(c[xb])
        else:                                                  # exit at the open of the bar starting at that minute
            xm = np.flatnonzero(m >= 570 + 10 * v[2])
            if len(e) == 0 or len(xm) == 0:
                continue
            xb = a + int(xm[0])
            xp = float(o[xb])
        eb = a + int(e[0])
        if xb < eb:
            continue
        trades.append((int(eb), int(xb), float(v[0]), 1, float(o[eb]), xp))
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    trades.sort(key=lambda t: (t[1], t[0]))
    pnl = np.array([t[2] for t in trades], float)
    w = pnl[pnl > 0]; ls = pnl[pnl < 0]
    gw = float(w.sum()); gl = float(-ls.sum())
    cum = np.cumsum(pnl)
    out = {"total_pnl": float(pnl.sum()), "num_trades": int(len(pnl)),
           "win_rate": float(100.0 * len(w) / len(pnl)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
           "avg_pnl": float(pnl.mean()), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     **params):
    """Every pair trade enters and leaves inside one session (flat by 16:00 at the latest), so no trade is ever
    held through a session close: one empty mark list per trade."""
    return [[] for _ in (trades or [])]
