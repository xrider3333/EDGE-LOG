"""TTM SQUEEZE ROUND 13 - the stress harness that tries to kill the structural stop.

WHERE THIS PICKS UP
  Round 12b (tools/ttmsqz_r12b_entry_exit.py) found that swapping the incumbent's 1.5x ATR
  protective stop for a STRUCTURAL stop (the opposite side of the squeeze range that fired
  the trade, no buffer) beats the incumbent on profit factor, net and lockbox. That mechanism
  went through Auto-Validate as run #352 with the deep-squeeze 1.5x size tilt riding along
  (TTMSQZ_3_0_ES30SS.py / TTMSQZ_3_0_ES30SS20.py) and passed all six house gates - but the
  search walked to a looser verification length (16 instead of the pinned 20), nearly doubled
  the trade count, and pushed drawdown to $7,143 against a $5,004 cap. A re-run with gate_len
  pinned at 20 is queued. Adoption needs a second, independent thing regardless of how that
  comes back: the structural stop is ~76% wider per contract than the ATR stop it replaces
  ($1,041 vs $586 mean, worst observed $6,612), and a 16-year window that never punished a
  wider tail is one draw, not proof that the tail is safe.

  This file is that proof attempt. It does not re-run Auto-Validate, crown anything, queue
  anything, or touch index.html. It takes the three legs' CLOSED trade lists exactly as the
  engine produces them and asks what breaks them.

THE THREE LEGS (ES 30m RTH, pinned window, house cost 0.363 pts round trip, $50/pt, 1 base
contract, kc_mult 1.5, length 20, Bollinger 2.0, hourly squeeze-on verification len 20):
  A. incumbent crown   - TTMSQZ_3_0_ES30N.py   - 1.5x ATR stop, no size tilt
  B. book leg (control)- TTMSQZ_3_0_ES30T.py   - 1.5x ATR stop, + validated 1.5x deep-squeeze tilt
  C. structural stop   - TTMSQZ_3_0_ES30SS20.py- range-edge stop (buffer 0), + the same tilt
  All three share stop_atr n/a for C, eod_cutoff 1, gate_len 20 - the ONLY thing that differs
  between B and C is the protective stop; A isolates the tilt's own contribution.

THIS FILE'S OWN TRADE LOOP, AND WHY
  Exit REASON (stop / momentum-fade / session-close) and per-trade max-adverse-excursion are
  not exposed by the engine's return_trades output, so this file reuses the engine's causal
  fire/range/gate construction verbatim (squeeze_indicators, _htf_gate, _session_last_bar,
  imported unchanged from TTMSQZ_3_0.py) and re-derives the SAME three trade lists with its
  own loop, tagging every exit's reason as it goes. A REPRODUCTION CHECK below runs the real
  strategy files (ES30N / ES30T / ES30SS20) on the pinned cell and diffs n / net / DD / PF
  against this file's own loop before anything downstream is trusted.

WHAT COUNTS AS A FAIR STRESS, AND THE RULE THAT KEEPS IT HONEST
  Every stress in sections 2-3 re-prices CLOSED trades after the fact: it changes the exit
  price or exit-loss magnitude of trades that already happened, never which trades exist or
  when they entered/exited. A stop that is 76% wider changes which trades would exist under
  real slippage/gaps (a stopped-out trade frees the position for the next fire signal sooner)
  - that re-run question is NOT asked here, and mixing it into this file's numbers would be
  exactly the mistake the round-13 brief warns against. Section 5 is the one deliberate
  exception: it reconstructs ONE historical trade under a different (tighter) stop, which is
  what the brief itself asks for, and is clearly boxed off from the aggregate stress tables.

  The stress is applied ONLY to trades that exit via the STOP (not fade, not session-close),
  which is also why section 1 (how often is the stop actually hit) has to come first - it is
  the leverage every downstream number depends on.

No look-ahead anywhere: fire/gate/range arrays are read from bars closed at or before the
decision bar, entries fill at the next bar's open, and the same-bar-stop convention (a stop
crossed on the same bar as the fill is assumed hit, pessimistically) matches the engine.

Usage:  python tools/ttmsqz_r13_gap_stress.py
Output: tools/data/ttmsqz_r13_gap_stress.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6_r13")
t3 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "t3_r13")
es30n = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30N.py"), "es30n_r13")
es30t = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30T.py"), "es30t_r13")
es30ss20 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS20.py"), "es30ss20_r13")

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST["ES"], r6.MULT["ES"]
INST = "ES"
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r13_gap_stress.txt")

# ── the pinned cell, identical across all three legs except the stop ──────────────────────
CELL = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, gate_tf_min=60,
            gate_mode="sq_on", gate_len=20, gate_bars=2, gate_ratio=1.0, gate_fired_k=3,
            direction="both")
STOP_ATR = 1.5          # legs A and B
EOD_CUTOFF = 1
FADE_BARS = 1

# the validated deep-squeeze tilt (copied verbatim from TTMSQZ_3_0_ES30T.py / ES30SS.py)
TILT_MULT = 1.5
DEEP_THR = 0.85
TILT_TF_MIN = 60
TILT_LEN, TILT_BB, TILT_KC = 20, 2.0, 1.5

LEGS = ["A incumbent (ATR stop, no tilt)", "B book leg (ATR stop + tilt)",
        "C structural stop + tilt"]


# --------------------------------------------------------------------------------------
# shared causal setup - copied verbatim from TTMSQZ_3_0.run_backtest
# --------------------------------------------------------------------------------------
def _prep(df):
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float);  c = df["close"].values.astype(float)
    did = df["day_id"].values
    n = len(c)
    sq_on, mom, atr = t3.squeeze_indicators(h, l, c, CELL["length"], CELL["bb_mult"], CELL["kc_mult"])
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= CELL["min_sq_bars"])
    warm = CELL["length"] * 2 + 5
    fire[:warm] = False
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()
    gate_long, gate_short = t3._htf_gate(
        h, l, c, did, df["_dt"], CELL["gate_bars"], CELL["gate_tf_min"], CELL["gate_len"],
        CELL["bb_mult"], CELL["kc_mult"], CELL["gate_mode"], CELL["gate_fired_k"], CELL["gate_ratio"])
    last_bar = t3._session_last_bar(did, n)
    return dict(o=o, h=h, l=l, c=c, n=n, warm=warm, mom=mom, atr=atr, fire=fire,
                rng_hi=rng_hi, rng_lo=rng_lo, gate_long=gate_long, gate_short=gate_short,
                last_bar=last_bar)


def _deep_state(h, l, c, did, index):
    """Copied verbatim from TTMSQZ_3_0_ES30T.py. Boolean per base bar: is the last COMPLETE
    hourly bar's compression ratio <= DEEP_THR?"""
    n = len(c)
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
    bucket = (mins - first_of_day) // int(TILT_TF_MIN)
    grp = did.astype(np.int64) * 10000 + bucket.astype(np.int64)
    change = np.empty(n, bool); change[0] = True; change[1:] = grp[1:] != grp[:-1]
    gstart = np.flatnonzero(change)
    gend = np.append(gstart[1:], n) - 1
    hh = np.array([h[s:e + 1].max() for s, e in zip(gstart, gend)])
    ll = np.array([l[s:e + 1].min() for s, e in zip(gstart, gend)])
    cc = c[gend]
    s_ = pd.Series(cc)
    dev = s_.rolling(int(TILT_LEN)).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(int(TILT_LEN)).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((TILT_BB * dev) / (TILT_KC * atr)).to_numpy()
    warm = int(TILT_LEN) * 2 + 5
    j = np.searchsorted(gend, np.arange(n), side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(cc) - 1)
    r = np.where(ok, ratio[jj], np.nan)
    return np.isfinite(r) & (r <= float(DEEP_THR))


# --------------------------------------------------------------------------------------
# THE trade loop - mirrors TTMSQZ_3_0.run_backtest / TTMSQZ_3_0_ES30SS._simulate exactly,
# with exit REASON tagged (stop / fade / eod) and stop distance recorded at entry.
# --------------------------------------------------------------------------------------
def simulate(P, deep, stop_mode, tilt):
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    n, warm = P["n"], P["warm"]
    mom, atr = P["mom"], P["atr"]
    fire, rng_hi, rng_lo = P["fire"], P["rng_hi"], P["rng_lo"]
    gate_long, gate_short, last_bar = P["gate_long"], P["gate_short"], P["last_bar"]

    pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
    stop_px = None; cur_size = 1.0; cur_sdist = float("nan")
    fade_cnt = 0
    pending = None
    trades = []

    def book(exit_i, px, sd, ep, eb, reason, size, sdist):
        pnl = (px - ep) if sd > 0 else (ep - px)
        trades.append(dict(eb=int(eb), xb=int(exit_i), side=int(sd), entry_px=float(ep),
                            exit_px=float(px), pnl_pts=float(pnl), reason=reason,
                            size=float(size), stop_dist_pts=float(sdist)))

    for u in range(warm, n):
        eod = u == last_bar[u]

        if pending is not None:
            kind = pending["kind"]
            if kind == "exit":
                if pos != 0:
                    book(u, o[u], pos, entry_px, entry_bar, "fade", cur_size, cur_sdist)
                    pos = 0; stop_px = None
                pending = None
            else:  # "mkt"
                if pos == 0:
                    sd = pending["side"]; fb = pending["fire_bar"]
                    side = sd; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    if stop_mode == "atr":
                        stop_px = entry_px - sd * STOP_ATR * aa if (STOP_ATR > 0 and np.isfinite(aa)) else None
                    else:  # structural: opposite side of the FIRE bar's squeeze range, buffer 0
                        rh, rl = pending["rng_hi"], pending["rng_lo"]
                        stop_px = rl if sd > 0 else rh
                    cur_sdist = abs(entry_px - stop_px) if stop_px is not None else float("nan")
                    cur_size = TILT_MULT if (tilt and deep[fb]) else 1.0
                    pos = sd
                    if stop_px is not None and ((sd > 0 and l[u] <= stop_px) or (sd < 0 and h[u] >= stop_px)):
                        book(u, stop_px, pos, entry_px, entry_bar, "stop", cur_size, cur_sdist)
                        pos = 0; stop_px = None
                pending = None

        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                book(u, px, pos, entry_px, entry_bar, "stop", cur_size, cur_sdist)
                pos = 0; stop_px = None

        if eod:
            if pos != 0:
                book(u, c[u], pos, entry_px, entry_bar, "eod", cur_size, cur_sdist)
                pos = 0; stop_px = None
            pending = None
            continue

        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue

        if pos != 0:
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= FADE_BARS:
                pending = dict(kind="exit")
                continue

        if pos == 0 and pending is None and fire[u] and m != 0:
            sd = 1 if m > 0 else -1
            if sd > 0 and not gate_long[u]:
                continue
            if sd < 0 and not gate_short[u]:
                continue
            if last_bar[u] - u <= EOD_CUTOFF:
                continue
            pending = dict(kind="mkt", side=sd, fire_bar=u, rng_hi=rng_hi[u], rng_lo=rng_lo[u])

    t = pd.DataFrame(trades)
    # post-hoc max-adverse-excursion, in points, entry bar through exit bar inclusive -
    # NOT used to change any exit, only to report how far price moved against the position
    if len(t):
        mae = np.empty(len(t))
        for i, row in enumerate(t.itertuples()):
            seg_l = l[row.eb:row.xb + 1]; seg_h = h[row.eb:row.xb + 1]
            mae[i] = (row.entry_px - seg_l.min()) if row.side > 0 else (seg_h.max() - row.entry_px)
        t["mae_pts"] = mae
    return t


def usd_of(t, pnl_col="pnl_pts"):
    return t["size"].values * (t[pnl_col].values - COST) * MULT


def score_leg(t, df, pnl_col="pnl_pts"):
    if t is None or len(t) == 0:
        return None, None, None, None
    usd = usd_of(t, pnl_col)
    dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
    s = r6.score(usd, dates)
    lbmask = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
    sl = r6.score(usd[lbmask], np.array(dates)[lbmask]) if lbmask.any() else None
    return s, sl, usd, dates


def fmt_row(name, s, sl):
    if s is None:
        return "  %-30s  no trades" % name
    lb = ("{:,.0f} @ {:.2f} n{}".format(sl["net"], min(sl["pf"], 99), sl["n"]) if sl else "n/a")
    return "  %-30s %5d %7.2f %12s %9s | %s" % (
        name, s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]), lb)


HDR3 = "  %-30s %5s %7s %12s %9s | %s" % ("leg", "n", "PF", "net $", "DD $", "lockbox $ @ PF, n")


def main():
    t0 = time.time()
    L = []
    L.append("TTM SQUEEZE ROUND 13 - gap/slippage stress harness on the structural stop   %s"
             % time.strftime("%Y-%m-%d %H:%M"))
    L.append("ES 30m RTH, window %s..%s, lockbox from %s, house cost %.3f pts, mult %d, 1 base contract"
             % (DATE_FROM, DATE_TO, LB_FROM, COST, MULT))
    L.append("A = TTMSQZ_3_0_ES30N (1.5xATR stop, no tilt) | B = TTMSQZ_3_0_ES30T (1.5xATR stop + 1.5x")
    L.append("deep-squeeze tilt, the book leg) | C = TTMSQZ_3_0_ES30SS20 (structural range-edge stop,")
    L.append("buffer 0, gate_len pinned 20, + the same tilt). All three: kc_mult 1.5, gate_len 20,")
    L.append("eod_cutoff 1. Sections 2-3 re-price CLOSED trades (stop exits only) after the fact - they")
    L.append("do NOT re-run the strategy, so the trade LIST is fixed throughout each section; a wider")
    L.append("stop changing which trades exist is a different question, addressed separately (section 5).")

    df = r6.load(INST, "30m", "RTH")
    P = _prep(df)
    deep = _deep_state(P["h"], P["l"], P["c"], df["day_id"].values, df["_dt"])

    t_A = simulate(P, deep, stop_mode="atr", tilt=False)
    t_B = simulate(P, deep, stop_mode="atr", tilt=True)
    t_C = simulate(P, deep, stop_mode="structural", tilt=True)
    legs = {"A": t_A, "B": t_B, "C": t_C}

    # ====================================================================================
    # REPRODUCTION CHECK - this file's own loop vs the real strategy files
    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("REPRODUCTION CHECK - this file's loop vs the real strategy files on the pinned cell")
    L.append("=" * 100)
    L.append(HDR3)
    kw_common = dict(volumes=None, day_id=df["day_id"].values, index=df["_dt"], return_trades=True)
    checks = []
    r_a = es30n.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                             kc_mult=1.5, stop_atr=1.5, eod_cutoff=1, gate_len=20, **kw_common)
    r_b = es30t.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                             kc_mult=1.5, stop_atr=1.5, eod_cutoff=1, gate_len=20, **kw_common)
    r_c = es30ss20.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                                kc_mult=1.5, eod_cutoff=1, **kw_common)

    def _engine_score(res):
        if not res or not res.get("trades"):
            return None, None
        tr = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in res["trades"]],
                          columns=["eb", "xb", "pnl"])
        usd = (tr["pnl"].values - COST) * MULT
        dates = pd.DatetimeIndex(df["_dt"])[tr["xb"].values].date
        s = r6.score(usd, dates)
        lbmask = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
        sl = r6.score(usd[lbmask], np.array(dates)[lbmask]) if lbmask.any() else None
        return s, sl

    for lbl, res, mine in (("A engine (ES30N)", r_a, t_A), ("B engine (ES30T)", r_b, t_B),
                           ("C engine (ES30SS20)", r_c, t_C)):
        se, sle = _engine_score(res)
        L.append(fmt_row(lbl, se, sle))
    for lbl, t in (("A this file's loop", t_A), ("B this file's loop", t_B), ("C this file's loop", t_C)):
        s, sl, _, _ = score_leg(t, df)
        L.append(fmt_row(lbl, s, sl))

    def _match(se, mine_s, tol_n=0, tol_usd=5.0):
        if se is None or mine_s is None:
            return False
        return (se["n"] == mine_s["n"] and abs(se["net"] - mine_s["net"]) <= tol_usd
                and abs(se["dd"] - mine_s["dd"]) <= tol_usd)

    sA, slA, _, _ = score_leg(t_A, df); sB, slB, _, _ = score_leg(t_B, df); sC, slC, _, _ = score_leg(t_C, df)
    seA, _ = _engine_score(r_a); seB, _ = _engine_score(r_b); seC, _ = _engine_score(r_c)
    match = _match(seA, sA) and _match(seB, sB) and _match(seC, sC)
    L.append("  verdict: %s" % ("MATCH on n/net/DD for all three legs - trusting the exit-reason tags below"
                                if match else "MISMATCH - investigate before trusting anything below"))
    print("\n".join(L), flush=True)
    if not match:
        open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
        print("\nABORTED - reproduction mismatch. Wrote partial log to " + LOG)
        return

    # ====================================================================================
    # BASELINE (no stress) - all three legs
    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("BASELINE (no stress) - all three legs, this file's own trade list")
    L.append("=" * 100)
    L.append(HDR3)
    for name, t in zip(LEGS, (t_A, t_B, t_C)):
        s, sl, _, _ = score_leg(t, df)
        L.append(fmt_row(name, s, sl))
    print("\n".join(L[-5:]), flush=True)

    # ====================================================================================
    # 1. HOW OFTEN IS THE STOP ACTUALLY HIT
    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("1. HOW OFTEN THE STOP IS ACTUALLY HIT (count / share of exits / share of gross losses)")
    L.append("=" * 100)
    L.append("  %-30s %6s %10s %10s | %10s %10s | %10s %12s" % (
        "leg", "n", "stop n", "stop %", "fade n", "eod n", "gross loss $", "stop-loss %"))
    stop_stats = {}
    for name, key, t in zip(LEGS, "ABC", (t_A, t_B, t_C)):
        usd = usd_of(t)
        reason = t["reason"].values
        n = len(t)
        n_stop = int((reason == "stop").sum())
        n_fade = int((reason == "fade").sum())
        n_eod = int((reason == "eod").sum())
        gross_loss = float(-usd[usd < 0].sum())
        stop_loss = float(-usd[(usd < 0) & (reason == "stop")].sum())
        stop_share_loss = 100 * stop_loss / gross_loss if gross_loss > 0 else float("nan")
        stop_stats[key] = dict(n=n, n_stop=n_stop, gross_loss=gross_loss, stop_loss=stop_loss)
        L.append("  %-30s %6d %10d %9.1f%% | %10d %10d | %12s %11.1f%%" % (
            name, n, n_stop, 100 * n_stop / n, n_fade, n_eod,
            "{:,.0f}".format(gross_loss), stop_share_loss))
    L.append("")
    L.append("  concentration read: a stop that fires on a small share of exits but carries a large")
    L.append("  share of gross losses means the tail risk is concentrated in few trades, not spread -")
    L.append("  exactly the shape a 16-year window can fail to punish even once by chance.")
    for name, key in zip(LEGS, "ABC"):
        st = stop_stats[key]
        share_exits = 100 * st["n_stop"] / st["n"]
        share_loss = 100 * st["stop_loss"] / st["gross_loss"] if st["gross_loss"] > 0 else float("nan")
        L.append("    %s: stop exits are %.1f%% of trades but %.1f%% of gross losses (concentration x%.2f)"
                 % (name, share_exits, share_loss, (share_loss / share_exits) if share_exits > 0 else float("nan")))
    print("\n".join(L[-12:]), flush=True)

    # ====================================================================================
    # 2. SLIPPAGE ON STOP FILLS
    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("2. SLIPPAGE ON STOP FILLS - N points of adverse slippage added to every STOP exit only")
    L.append("   (fade and session-close exits are untouched at every level; fixed trade list throughout)")
    L.append("=" * 100)
    for slip in (0.0, 0.5, 1.0, 2.0, 4.0):
        L.append("")
        L.append("-- slippage %.1f pts/stop fill (%s/contract) --" % (slip, "${:,.0f}".format(slip * MULT)))
        L.append(HDR3)
        for name, t in zip(LEGS, (t_A, t_B, t_C)):
            pnl2 = t["pnl_pts"].values.copy()
            mask = (t["reason"] == "stop").values
            pnl2[mask] = pnl2[mask] - slip
            t2 = t.copy(); t2["pnl_pts"] = pnl2
            s, sl, _, _ = score_leg(t2, df)
            L.append(fmt_row(name, s, sl))
    print("\n".join(L[-24:]), flush=True)

    # fine-grained crossover: smallest slip (0.05 pt steps) where each pair's ranking flips
    def _sweep_slip(t, step=0.05, hi=10.0):
        out = []
        for slip in np.arange(0.0, hi + 1e-9, step):
            pnl2 = t["pnl_pts"].values.copy()
            mask = (t["reason"] == "stop").values
            pnl2[mask] = pnl2[mask] - slip
            t2 = t.copy(); t2["pnl_pts"] = pnl2
            s, sl, _, _ = score_leg(t2, df)
            out.append((slip, s["net"], s["pf"], (sl["net"] if sl else float("nan"))))
        return pd.DataFrame(out, columns=["slip", "net", "pf", "lb_net"])

    sw = {k: _sweep_slip(t) for k, t in zip("ABC", (t_A, t_B, t_C))}
    L.append("")
    L.append("  crossover search (0.05-pt steps, 0-10 pts) on stop-fill slippage:")
    for metric, col in (("whole-run net", "net"), ("whole-run PF", "pf"), ("lockbox net", "lb_net")):
        cb = sw["C"][col].values - sw["B"][col].values
        cross = None
        for i in range(1, len(cb)):
            if cb[i - 1] >= 0 and cb[i] < 0:
                cross = sw["C"]["slip"].values[i]; break
        L.append("    C vs B on %-14s: %s" % (metric,
                 ("C stays >= B through 10 pts of stop slippage" if cross is None
                  else "C drops below B at %.2f pts of stop slippage" % cross)))
        pf1 = None
        v = sw["C"]["pf"].values
        for i in range(1, len(v)):
            if v[i - 1] >= 1.0 and v[i] < 1.0:
                pf1 = sw["C"]["slip"].values[i]; break
        if metric == "whole-run PF":
            L.append("    C's own PF crosses 1.0 at %s" % (
                "%.2f pts of stop slippage" % pf1 if pf1 is not None else "> 10 pts (not reached)"))
        lbneg = None
        v = sw["C"]["lb_net"].values
        for i in range(1, len(v)):
            if v[i - 1] >= 0 and v[i] < 0:
                lbneg = sw["C"]["slip"].values[i]; break
        if metric == "lockbox net":
            L.append("    C's own lockbox net turns negative at %s" % (
                "%.2f pts of stop slippage" % lbneg if lbneg is not None else "> 10 pts (not reached)"))
    print("\n".join(L[-10:]), flush=True)

    # ====================================================================================
    # 3. GAP-THROUGH
    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("3. GAP-THROUGH - the LOSS on every stop exit scaled by a factor (fixed trade list throughout)")
    L.append("=" * 100)
    for factor in (1.0, 1.5, 2.0, 3.0):
        L.append("")
        L.append("-- gap-through factor %.1fx on stop-exit losses --" % factor)
        L.append(HDR3)
        for name, t in zip(LEGS, (t_A, t_B, t_C)):
            pnl2 = t["pnl_pts"].values.copy()
            mask = (t["reason"] == "stop").values & (pnl2 < 0)
            pnl2[mask] = pnl2[mask] * factor
            t2 = t.copy(); t2["pnl_pts"] = pnl2
            s, sl, _, _ = score_leg(t2, df)
            L.append(fmt_row(name, s, sl))
    print("\n".join(L[-20:]), flush=True)

    def _sweep_gap(t, step=0.05, hi=6.0):
        out = []
        for factor in np.arange(1.0, hi + 1e-9, step):
            pnl2 = t["pnl_pts"].values.copy()
            mask = (t["reason"] == "stop").values & (pnl2 < 0)
            pnl2[mask] = pnl2[mask] * factor
            t2 = t.copy(); t2["pnl_pts"] = pnl2
            s, sl, _, _ = score_leg(t2, df)
            out.append((factor, s["net"], s["pf"], (sl["net"] if sl else float("nan"))))
        return pd.DataFrame(out, columns=["factor", "net", "pf", "lb_net"])

    gw = {k: _sweep_gap(t) for k, t in zip("ABC", (t_A, t_B, t_C))}
    L.append("")
    L.append("  crossover search (0.05x steps, 1.0-6.0x) on stop-exit gap-through:")
    for metric, col in (("whole-run net", "net"), ("whole-run PF", "pf"), ("lockbox net", "lb_net")):
        cb = gw["C"][col].values - gw["B"][col].values
        cross = None
        for i in range(1, len(cb)):
            if cb[i - 1] >= 0 and cb[i] < 0:
                cross = gw["C"]["factor"].values[i]; break
        L.append("    C vs B on %-14s: %s" % (metric,
                 ("C stays >= B through 6.0x gap-through" if cross is None
                  else "C drops below B at a %.2fx gap-through factor" % cross)))
    v = gw["C"]["pf"].values
    pf1 = None
    for i in range(1, len(v)):
        if v[i - 1] >= 1.0 and v[i] < 1.0:
            pf1 = gw["C"]["factor"].values[i]; break
    L.append("    C's own PF crosses 1.0 at %s" % (
        "a %.2fx gap-through factor" % pf1 if pf1 is not None else "> 6.0x (not reached)"))
    v = gw["C"]["lb_net"].values
    lbneg = None
    for i in range(1, len(v)):
        if v[i - 1] >= 0 and v[i] < 0:
            lbneg = gw["C"]["factor"].values[i]; break
    L.append("    C's own lockbox net turns negative at %s" % (
        "a %.2fx gap-through factor" % lbneg if lbneg is not None else "> 6.0x (not reached)"))
    print("\n".join(L[-10:]), flush=True)

    # ====================================================================================
    # 4. THE REAL HISTORICAL TAIL
    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("4. THE REAL HISTORICAL TAIL - per leg, no stress applied (actual realized trades)")
    L.append("=" * 100)
    for name, key, t in zip(LEGS, "ABC", (t_A, t_B, t_C)):
        usd = usd_of(t)
        dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
        order = np.argsort(usd)
        L.append("")
        L.append("%s" % name)
        L.append("  five worst trades ($):")
        for i in order[:5]:
            row = t.iloc[i]
            L.append("    %s  exit %s  side %+d  reason %-5s  size %.1fx  %s"
                     % ("{:>10,.0f}".format(usd[i]), str(dates[i]), int(row["side"]),
                        row["reason"], row["size"], "$"))
        stop_mask = (t["reason"] == "stop").values
        if stop_mask.any():
            worst_stop_i = np.argmin(np.where(stop_mask, usd, np.inf))
            row = t.iloc[worst_stop_i]
            L.append("  worst STOP-exit trade: %s on %s (entry %.2f -> exit %.2f, size %.1fx)"
                     % ("{:,.0f}".format(usd[worst_stop_i]), str(dates[worst_stop_i]),
                        row["entry_px"], row["exit_px"], row["size"]))
        else:
            L.append("  worst STOP-exit trade: none (no stop exits)")
        avg_sdist_pts = float(np.nanmean(t["stop_dist_pts"].values))
        avg_sdist_usd = avg_sdist_pts * MULT
        L.append("  mean stop distance at entry: %.2f pts (%s/contract, n=%d entries)"
                 % (avg_sdist_pts, "${:,.0f}".format(avg_sdist_usd), len(t)))

    # largest overnight/session gap in the whole RTH window (open of session N+1 vs close of
    # session N's last bar) - a market-wide number, independent of any strategy or trade
    o_all, h_all, l_all, c_all = P["o"], P["h"], P["l"], P["c"]
    did_all = df["day_id"].values
    n_all = len(c_all)
    first_idx = np.zeros(0, int)
    boundaries = np.flatnonzero(np.diff(did_all) != 0)  # index of the LAST bar of each session except the last
    gaps = np.abs(o_all[boundaries + 1] - c_all[boundaries])
    worst_gap_i = int(np.argmax(gaps))
    worst_gap_pts = float(gaps[worst_gap_i])
    worst_gap_usd = worst_gap_pts * MULT
    worst_gap_date = str(pd.DatetimeIndex(df["_dt"])[boundaries[worst_gap_i] + 1].date())
    L.append("")
    L.append("  largest session-to-session gap in the whole window (open vs prior session's close,")
    L.append("  %d session boundaries checked): %.2f pts = %s on %s"
             % (len(boundaries), worst_gap_pts, "${:,.0f}".format(worst_gap_usd), worst_gap_date))
    L.append("  (this strategy is flat at every session close, so no trade in these legs was ever")
    L.append("  exposed to this gap directly - it is a plausibility check on how big ES gaps get,")
    L.append("  used below against each leg's stop cushion, not a trade this family ever held through)")
    for name, key, t in zip(LEGS, "ABC", (t_A, t_B, t_C)):
        avg_sdist_usd = float(np.nanmean(t["stop_dist_pts"].values)) * MULT
        ratio = worst_gap_usd / avg_sdist_usd if avg_sdist_usd > 0 else float("nan")
        verdict = "BIGGER than the cushion" if ratio > 1 else "smaller than the cushion"
        L.append("    %s: worst gap $%s is %.2fx the mean stop cushion $%s -> %s"
                 % (name, "{:,.0f}".format(worst_gap_usd), ratio, "{:,.0f}".format(avg_sdist_usd), verdict))
    print("\n".join(L[-30:]), flush=True)

    # ====================================================================================
    # 5. WORST-CASE RECONSTRUCTION - leg C's largest adverse move, repriced under leg B's stop
    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("5. WORST-CASE RECONSTRUCTION - leg C's largest adverse move against an open position,")
    L.append("   reconstructed under leg B's tighter (1.5x ATR) stop. This is a SINGLE-TRADE")
    L.append("   counterfactual (the brief's own request), not an aggregate re-price like sections 2-3 -")
    L.append("   it does NOT change the trade list, it re-simulates ONE historical trade's stop rule.")
    L.append("=" * 100)
    mae_i = int(np.argmax(t_C["mae_pts"].values))
    row = t_C.iloc[mae_i]
    eb, xb = int(row["eb"]), int(row["xb"])
    sd = int(row["side"]); ep = float(row["entry_px"]); size = float(row["size"])
    actual_pnl_pts = float(row["pnl_pts"])
    actual_usd = size * (actual_pnl_pts - COST) * MULT
    entry_date = str(pd.DatetimeIndex(df["_dt"])[eb].date())
    exit_date = str(pd.DatetimeIndex(df["_dt"])[xb].date())
    L.append("")
    L.append("  worst MAE trade in leg C: entered %s (bar %d), exited %s (bar %d), side %+d, entry %.2f"
             % (entry_date, eb, exit_date, xb, sd, ep))
    L.append("  max adverse excursion: %.2f pts (%s) - exit reason was '%s' at %.2f, actual result %s"
             % (float(row["mae_pts"]), "${:,.0f}".format(float(row["mae_pts"]) * MULT),
                row["reason"], float(row["exit_px"]), "${:,.0f}".format(actual_usd)))

    aa = P["atr"][eb - 1] if eb - 1 >= 0 else float("nan")
    tight_stop = ep - sd * STOP_ATR * aa if np.isfinite(aa) else None
    if tight_stop is None:
        L.append("  leg B's stop distance is undefined for this entry (ATR not finite) - no reconstruction possible")
    else:
        tight_dist_pts = abs(ep - tight_stop)
        hit_bar = None; hit_px = None
        o_, h_, l_ = P["o"], P["h"], P["l"]
        # same-bar-entry pessimism first
        if (sd > 0 and l_[eb] <= tight_stop) or (sd < 0 and h_[eb] >= tight_stop):
            hit_bar = eb; hit_px = tight_stop
        else:
            for u in range(eb + 1, xb + 1):
                if (sd > 0 and l_[u] <= tight_stop) or (sd < 0 and h_[u] >= tight_stop):
                    hit_bar = u
                    hit_px = min(o_[u], tight_stop) if sd > 0 else max(o_[u], tight_stop)
                    break
        L.append("  leg B's stop for this SAME entry would sit %.2f pts away (%s) at %.2f"
                 % (tight_dist_pts, "${:,.0f}".format(tight_dist_pts * MULT), tight_stop))
        if hit_bar is None:
            L.append("  that tighter stop is NEVER crossed between entry and leg C's own exit bar -")
            L.append("  under leg B's stop this same trade would have exited the same way leg C did:")
            L.append("  '%s' at %.2f, same result %s" % (row["reason"], float(row["exit_px"]),
                     "${:,.0f}".format(actual_usd)))
        else:
            counter_pnl_pts = (hit_px - ep) if sd > 0 else (ep - hit_px)
            counter_usd = size * (counter_pnl_pts - COST) * MULT
            hit_date = str(pd.DatetimeIndex(df["_dt"])[hit_bar].date())
            L.append("  under leg B's tighter stop this trade is stopped out on %s (bar %d) at %.2f:"
                     % (hit_date, hit_bar, hit_px))
            L.append("  reconstructed result %s  vs  leg C's actual result %s  (difference %s)"
                     % ("{:,.0f}".format(counter_usd), "{:,.0f}".format(actual_usd),
                        "{:+,.0f}".format(actual_usd - counter_usd)))
    print("\n".join(L[-14:]), flush=True)

    # ====================================================================================
    L.append("")
    L.append("=" * 100)
    L.append("elapsed %.0fs" % (time.time() - t0))
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\nwrote " + LOG)


if __name__ == "__main__":
    main()
