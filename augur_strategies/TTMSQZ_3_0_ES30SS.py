"""
TTMSQZ 3.0 ES30SS — the ES30T neighbourhood with a STRUCTURAL protective stop.

WHY THIS EXISTS (round 12b entry/stop/exit scan, tools/ttmsqz_r12b_entry_exit.py, 2026-09-09)
  Round 12b held the family's one durable finding (the hourly squeeze-on verification) fixed
  and varied entry/stop/exit mechanics instead of the squeeze/gate knobs every prior round
  searched. Four of its five families (pullback entry, time exit, ATR trail, scale-out) were
  flat or worse. The one that cleared BOTH gates the family uses (whole-run profit factor AND
  lockbox net, both >= the incumbent) was the STRUCTURAL STOP: instead of a stop at entry +/-
  1.5x ATR, the stop sits at the OPPOSITE side of the squeeze range that produced the fire
  (+/- a small buffer), unchanged entry (next-open) and exit (1-bar momentum fade).

  Scan on the pinned window (2010-06-07..2026-06-30, ES 30m RTH, 0.363 pts a round trip),
  buffers 0 / 0.5 / 1.0 all landed close together and all beat the incumbent:
    incumbent (1.5x ATR stop):  n 359, PF 2.12, net $51,709, DD $3,740, lockbox $4,992 @ PF 2.22
    structural, buffer 0.00:    n 357, PF 2.70, net $73,720, DD $3,642, lockbox $11,710 @ PF 5.38
    structural, buffer 0.50:    n 357, PF 2.72, net $73,970, DD $3,492, lockbox $11,660 @ PF 5.36
    structural, buffer 1.00:    n 357, PF 2.68, net $73,083, DD $3,617, lockbox $11,610 @ PF 5.35

  THE HONEST CAVEAT THE SCAN ALSO RECORDED: the structural stop is materially WIDER than the
  ATR stop it replaces — mean per-contract distance $1,033 vs $586 (76% wider, 360 fires). A
  wider stop cuts fewer trades early, which is why PF/net/lockbox all improve, but it also
  means a bigger loss on whichever trade eventually DOES hit it, and this window's realized
  drawdown does not prove that tail is safe — it only proves the window never punished it.
  Verify this file's own tail with tools/parity_es30ss.py before trusting it further than that.

WHY BUFFER 0.00, NOT 0.50 OR 1.00 (this file's own choice — the scan itself was indifferent)
  The scan found the three buffers indistinguishable in aggregate (PF 2.68-2.72, lockbox PF
  5.35-5.38) — nothing in the numbers picks one. Given the stop is already 76% wider than the
  incumbent's ATR stop, adding a buffer on top only widens the tail further for no measured
  benefit. Buffer 0.00 is the MOST CONSERVATIVE of the three precisely because it adds nothing
  beyond the structural level itself — it is the floor of how wide this mechanism can be, not
  a tuned pick among the three. Frozen as `_STRUCT_BUF`, not exposed as a knob.

`stop_atr` IS NOW INERT AND IS NOT A DECLARED KNOB HERE
  The structural stop does not read stop_atr at all — the range-edge level supersedes it
  entirely rather than blending with it. Declaring it as a searchable knob would let
  Auto-Validate search a dial that changes nothing, so it is left out of DEFAULT_PARAMS and
  out of `_ADMISSIBLE`. A stray stop_atr kwarg is accepted (via **kw) and silently ignored so
  an old job config does not crash the file; it just does nothing. The other three knobs
  run #299 / ES30T searched — kc_mult, eod_cutoff, gate_len — are unchanged and still searched.

FROZEN MECHANISM UNCHANGED FROM ES30T / run #299
  Same hourly squeeze-on verification (gate_tf_min 60, gate_mode sq_on, gate_len searched),
  same Carter squeeze/fire/fade-exit construction, same validated 1.5x deep-squeeze size tilt
  (multiplier 1.5, threshold 0.85, ratio read at fixed length 20 / Bollinger 2.0 / Keltner 1.5,
  copied verbatim from TTMSQZ_3_0_ES30T.py). Only the protective stop changes.

WHY THIS FILE REIMPLEMENTS THE TRADE LOOP INSTEAD OF WRAPPING TTMSQZ_3_0.run_backtest
  ES30T's deep-squeeze tilt is a pure post-hoc re-sizing of trades the engine already
  produced, so it can call TTMSQZ_3_0.run_backtest unchanged and rescale the pnl afterward. A
  different STOP changes exit bars and exit prices themselves, which cannot be fixed up after
  the fact — the trade path has to be simulated with the new stop live from the start. So this
  file reuses the engine's fire/range/gate construction verbatim (squeeze_indicators,
  _htf_gate, _session_last_bar, imported unchanged from TTMSQZ_3_0.py) and only overrides the
  one piece that has to change: the trade loop's stop level. entry_fill is frozen to "open"
  (as ES30T freezes it), so the range-break resting-order path in the engine is not
  reproduced here — it would be dead code, since no admissible config ever reaches it.

COST CONVENTION (identical to ES30T)
  A trade sized s returns `s*raw - (s-1)*cost`, so after the caller's single downstream cost
  subtraction the trade is worth `s*(raw - cost)`. The job MUST carry cost_pts 0.363 (ES) or
  the sizing is mispriced.

Engine = TTMSQZ_3_0.py (squeeze_indicators, _htf_gate, _session_last_bar reused unchanged).
Control = TTMSQZ_3_0_ES30T.py, the paper leg — same window, same master, same costs, same
lockbox. Reproduced against the round-12b scan by tools/parity_es30ss.py; SCAN ONLY until
that parity check and the wider-tail question are both settled — nothing here is crowned,
queued for Auto-Validate, or written to index.html by this file.
"""
import os
from importlib import util as _u

import numpy as np
import pandas as pd

_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0.py"))
_t3 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t3)

# Exactly ES30T's frozen set (entry_fill open, fade exit, hourly sq_on gate). stop_atr is
# deliberately ABSENT — the structural stop replaces it, it does not read it.
_FROZEN = {'length': 20, 'bb_mult': 2.0, 'min_sq_bars': 1, 'entry_fill': 'open',
           'exit_mode': 'fade', 'fade_bars': 1, 'gate_tf_min': 60, 'gate_mode': 'sq_on',
           'gate_fired_k': 3, 'gate_bars': 2, 'gate_ratio': 1.0, 'direction': 'both'}

# THE ONE CHANGE — frozen, not searched (see docstring "WHY BUFFER 0.00").
_STRUCT_BUF = 0.0           # points added beyond the squeeze range edge; 0 = the range edge itself

# THE TILT — fixed, a priori, not searched (copied verbatim from TTMSQZ_3_0_ES30T.py).
_TILT_MULT = 1.5            # contracts on a deep-squeeze entry (1.0 otherwise)
_DEEP_THR = 0.85            # the house "deep compression" threshold (ml_keel.compression_sizes)
_TILT_TF_MIN = 60           # the verifying frame, in minutes
_TILT_LEN, _TILT_BB, _TILT_KC = 20, 2.0, 1.5    # fixed ratio definition (see docstring)
_COST_PTS = 0.363           # ES round trip in points — must match the job's cost_pts


def _deep_state(highs, lows, closes, day_id, index):
    """Boolean per base bar: is the last COMPLETE hourly bar's compression ratio <= _DEEP_THR?

    Copied verbatim from TTMSQZ_3_0_ES30T.py — same session-anchored construction as
    TTMSQZ_3_0._htf_gate's dial branch: base bars are grouped by minutes-since-session-open
    // 60, a group's state becomes readable on its last base bar's close, and bar u reads the
    latest group that has completed by u."""
    h = np.asarray(highs, float); l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    did = np.asarray(day_id)
    idx = pd.DatetimeIndex(index)
    mins = idx.hour.values * 60 + idx.minute.values
    first_of_day = np.zeros(n, int)
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        first_of_day[a:b] = mins[a]
        a = b
    bucket = (mins - first_of_day) // int(_TILT_TF_MIN)
    grp = did.astype(np.int64) * 10000 + bucket.astype(np.int64)
    change = np.empty(n, bool); change[0] = True; change[1:] = grp[1:] != grp[:-1]
    gstart = np.flatnonzero(change)
    gend = np.append(gstart[1:], n) - 1
    hh = np.array([h[s:e + 1].max() for s, e in zip(gstart, gend)])
    ll = np.array([l[s:e + 1].min() for s, e in zip(gstart, gend)])
    cc = c[gend]
    s_ = pd.Series(cc)
    dev = s_.rolling(int(_TILT_LEN)).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(int(_TILT_LEN)).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((_TILT_BB * dev) / (_TILT_KC * atr)).to_numpy()
    warm = int(_TILT_LEN) * 2 + 5
    j = np.searchsorted(gend, np.arange(n), side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(cc) - 1)
    r = np.where(ok, ratio[jj], np.nan)
    return np.isfinite(r) & (r <= float(_DEEP_THR))


def _rescore(trades):
    """Metrics from a sized trade list (copied verbatim from TTMSQZ_3_0_ES30T.py)."""
    pnls = np.array([t[2] for t in trades], float)
    if not len(pnls):
        return None
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    return {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
        "trades": trades,
    }


def _build_arrays(o, h, l, c, did, index, kc_mult, gate_len):
    """The fire/range/gate/last-bar arrays, built EXACTLY the way TTMSQZ_3_0.run_backtest
    builds them (same helper functions, same order), so the only thing that can differ from
    the incumbent downstream is the stop. length/bb_mult/min_sq_bars/gate_tf_min/gate_mode/
    gate_fired_k/gate_bars/gate_ratio come from `_FROZEN`; kc_mult and gate_len are searched."""
    n = len(c)
    length, bb_mult = _FROZEN['length'], _FROZEN['bb_mult']
    min_sq_bars = _FROZEN['min_sq_bars']
    sq_on, mom, atr = _t3.squeeze_indicators(h, l, c, length, bb_mult, kc_mult)
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= min_sq_bars)
    warm = length * 2 + 5
    fire[:warm] = False
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()
    gate_long, gate_short = _t3._htf_gate(
        h, l, c, did, index, _FROZEN['gate_bars'], _FROZEN['gate_tf_min'], gate_len,
        bb_mult, kc_mult, _FROZEN['gate_mode'], _FROZEN['gate_fired_k'], _FROZEN['gate_ratio'])
    last_bar = _t3._session_last_bar(did, n)
    return dict(n=n, warm=warm, mom=mom, atr=atr, fire=fire, rng_hi=rng_hi, rng_lo=rng_lo,
                gate_long=gate_long, gate_short=gate_short, last_bar=last_bar)


def _simulate(o, h, l, c, n, warm, mom, atr, fire, rng_hi, rng_lo, gate_long, gate_short,
              last_bar, fade_bars, eod_cutoff, struct_buf, direction):
    """TTMSQZ_3_0.run_backtest's own trade loop (open-fill / fade-exit / flat-at-close
    branches, same same-bar-stop pessimism), with ONE change: the protective stop is set at
    entry from the fire bar's squeeze range (opposite side, +/- struct_buf) instead of from
    stop_atr * ATR. The range is captured on the pending order at the FIRE bar (closed-bar
    information only) and is static once the trade is open — it does not trail."""
    pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
    stop_px = None
    fade_cnt = 0
    pending = None   # ("exit",) or ("mkt", side, rng_hi_at_fire, rng_lo_at_fire)
    trade_log = []   # (entry_bar, exit_bar, pnl_pts, side, entry_px, exit_px)

    def _book(exit_i, px, sd, ep, eb):
        p = (px - ep) if sd > 0 else (ep - px)
        trade_log.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(px)))

    for u in range(warm, n):
        eod = u == last_bar[u]

        # 1. resolve any pending order
        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar)
                    pos = 0; stop_px = None
                pending = None
            else:  # "mkt"
                if pos == 0:
                    side = pending[1]; rh, rl = pending[2], pending[3]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    # THE ONE CHANGE: opposite side of the ORIGINAL fire-bar squeeze range,
                    # +/- a frozen buffer, instead of entry -/+ stop_atr * ATR.
                    stop_px = (rl - struct_buf) if side > 0 else (rh + struct_buf)
                    # conservative same-bar stop (mirrors the engine's own audited convention):
                    # the fill bar's own range can take out the protective stop; assume it does.
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar)
                        pos = 0; stop_px = None
                pending = None

        # 2. in-position stop check (bars after the entry bar only)
        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar)
                pos = 0; stop_px = None

        # 3. session close
        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar)
                pos = 0; stop_px = None
            pending = None
            continue

        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue

        # 4. fade exit (delayed one bar, matching the engine's own "exit" pending kind)
        if pos != 0:
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",)
                continue

        # 5. new entries
        if pos == 0 and pending is None and fire[u] and m != 0:
            sd = 1 if m > 0 else -1
            if direction == "long" and sd < 0:
                continue
            if direction == "short" and sd > 0:
                continue
            if sd > 0 and not gate_long[u]:
                continue
            if sd < 0 and not gate_short[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            pending = ("mkt", sd, rng_hi[u], rng_lo[u])

    return trade_log


# ── THE NEIGHBOURHOOD IS BINDING (same 3 of ES30T's 4 knobs; stop_atr dropped — inert) ──
# Auto-Validate widens a strategy's declared min/max when the optimum sits near an edge.
# That is right for an open search and fatal for a fenced one, so admissibility is enforced
# HERE, where nothing can widen it, and an out-of-set configuration is refused rather than
# clamped.
_ADMISSIBLE = {'kc_mult': [1.25, 1.5, 1.75], 'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        v = kw[k]
        if not any(abs(float(v) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, **kw):
    """Run #299's neighbourhood, structural stop instead of the ATR stop, deep-squeeze
    entries still sized 1.5.

    `index` is named explicitly because the fire/gate construction and the tilt both read
    the clock. An out-of-set configuration is REFUSED (None), never clamped. A stray
    `stop_atr` in kw is accepted and ignored — it does nothing now (see module docstring)."""
    if not _in_neighbourhood(kw):
        return None
    if day_id is None or index is None:
        return None          # no clock, no honest gate/tilt/range-anchoring
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 300:
        return None
    did = np.asarray(day_id)
    if len(did) != n:
        return None

    kc_mult = float(kw.get('kc_mult', 1.5))
    eod_cutoff = int(kw.get('eod_cutoff', 1))
    gate_len = int(kw.get('gate_len', 20))

    A = _build_arrays(o, h, l, c, did, index, kc_mult, gate_len)
    trade_log = _simulate(o, h, l, c, A['n'], A['warm'], A['mom'], A['atr'], A['fire'],
                          A['rng_hi'], A['rng_lo'], A['gate_long'], A['gate_short'],
                          A['last_bar'], _FROZEN['fade_bars'], eod_cutoff, _STRUCT_BUF,
                          _FROZEN['direction'])
    if not trade_log:
        return None

    deep = _deep_state(highs, lows, closes, day_id, index)
    nn = len(deep)
    out = []
    for t in trade_log:
        eb = int(t[0])
        d = bool(deep[min(max(eb - 1, 0), nn - 1)])      # the DECISION bar, one before the fill
        s = float(_TILT_MULT) if d else 1.0
        pnl = s * float(t[2]) - (s - 1.0) * float(_COST_PTS)
        out.append((eb, int(t[1]), pnl) + tuple(t[3:]))
    return _rescore(out)


squeeze_indicators = _t3.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 3.0 ES30SS · ES 30m Carter neighbourhood + structural stop + 1.5x deep-squeeze tilt'
DESCRIPTION = ("Run #299's neighbourhood with the round-12b structural stop: the protective stop sits "
               "at the opposite side of the squeeze range that produced the fire (buffer 0, frozen), "
               "instead of 1.5x ATR. stop_atr is retired — it is superseded, not searched. The deep-"
               "squeeze 1.5x size tilt from ES30T is unchanged. Only kc_mult, eod_cutoff and gate_len "
               "vary; caveat: the structural stop is materially wider per-trade than the ATR stop it "
               "replaces (see docstring) — this is a scan finding under file-level test, not crowned.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}

DEFAULT_PARAMS = {
    'kc_mult': {'default': 1.5, 'min': 1.25, 'max': 1.75, 'step': 0.25, 'type': 'float',
                'label': 'Keltner ATR multiplier',
                'tooltip': 'Pocket value 1.5; one step either side, as in run 299.'},
    'eod_cutoff': {'default': 1, 'min': 1, 'max': 5, 'step': 2, 'type': 'int',
                   'label': 'No entries inside the last N bars of the session',
                   'tooltip': 'Run 299 chose 1; the set keeps 3 and 5.'},
    'gate_len': {'default': 20, 'min': 16, 'max': 24, 'step': 4, 'type': 'int',
                 'label': 'Verification squeeze length',
                 'tooltip': 'Length of the hourly squeeze that verifies each entry. Pocket value 20.'},
}

PARAM_GRID_PRESETS = {
    "Short  (ES 30m structural-stop neighbourhood)": {
        'kc_mult': [1.25, 1.5, 1.75], 'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]},
}
