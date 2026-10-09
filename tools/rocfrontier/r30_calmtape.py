# CALMTAPE r1 (FRONTIER, book queue Q29) - a long ES leg held only on a CALM UPTREND (the one state Q28's map says the book lacks), judged against
# buy-and-hold ES at the SAME average exposure (MANAGER #125) and read as a seat on the S1 line. WF only; the lockbox is unread (every input is
# cut before 2025-06-30). Pre-registered: docs/PREREG_frontier_calmtape_2026-10-09.txt (LF sha below; committed and pushed before any number).
#   python r30_calmtape.py selftest   hand-made series: the states, the units, the open-fill P&L, costs, rolls, the twin, the holiday drop, the block
#                                     sampler, the family max, the MDE bisection; asserts every command is defined
#   python r30_calmtape.py dryload    inputs and counts only (sessions, rolls, holiday rows dropped, hold days, the S1 line's parity, the map share
#                                     under the final rule) - no leg P&L
#   python r30_calmtape.py power      the family null alone (random hold days; no cell P&L) -> calmtape_power.json, the MDE; commit the addendum next
#   python r30_calmtape.py stage_a    needs the committed power addendum: the two cells, their twins, the null, the bar (i)-(iii), the seat read
import hashlib, json, math, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.environ.get("EDGELOG_CALMTAPE_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\calmtape_r1")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))                                  # tools/ (power_line)
import numpy as np, pandas as pd
import r29_ranatomy as Q28                                                 # Q28's committed state functions - the map check's own
from power_line import roc30, power_line
os.environ["EDGELOG_RESMOM_R1"] = OUT                                      # r29 points r17's output at its folder on import; r17 (loaders only) writes here

TS = pd.Timestamp
PREREG = os.path.join(REPO, "docs", "PREREG_frontier_calmtape_2026-10-09.txt")
PREREG_SHA = "01da6b0060887f3c071c56b28e8870f96ae3511c200f44fdb3113f6bc2f127a5"
POWER_DOC = os.path.join(REPO, "docs", "PREREG_frontier_calmtape_2026-10-09_power.txt")
POWER_JSON = os.path.join(OUT, "calmtape_power.json")
PINS = {"vix": (Q28.PINS["cboe"][0], "9790df06b649df21d34ab7cb31a5ed5e4c3c71fcda33952d1f41e431cb4e2470", False),       # cboe_vol_daily.csv (Q28 / the map check)
        "line": (Q28.PINS["line"][0], "e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18", False),
        "r17": (os.path.join(HERE, "r17_resmom.py"), "3151ef0ac6229972e897cf26634b465d87d608f0bf026215ea371058a5001f7c", True),
        "r29": (os.path.join(HERE, "r29_ranatomy.py"), "84306a500dbaf6454d8bce1303672d1b0e7ccdef5743eea4be2b19937a343adf", True),
        "power_line": (os.path.join(os.path.dirname(HERE), "power_line.py"), "8bfc4982d377fb3be36a5ffa66ed131e565ee20cde5a768966a2444397ed7037", True)}
WF0, WF1 = Q28.WF0, Q28.WF1                                                # 2016-07-01 .. 2025-06-29 (the S1 line's WF)
LB0 = TS("2025-06-30")
YEARS = (WF1 - WF0).days / 365.25
C_RES = Q28.C_RES
MES = 5.0                                                                  # $ per ES point for one MES-equivalent unit
SIDE = 0.25 * MES + 1.25                                                   # one tick + $1.25 commission per MES side = $2.50
VIX_ON, W_MAX = 16.0, 2.0
BLOCK, N_DRAWS = 20, 500
SEEDS = {"CT1": 20261009, "CT2": 20261010}                                 # fixed streams, one per cell; draw j of both cells forms one family draw
CELLS = ("CT1", "CT2")
SEAT_WINDOW = (TS("2016-07-01"), TS("2018-06-29"))                         # 10ab's sizing window
SHARES = (0.25, 0.10)
ROLL_TOL = 0.01                                                            # ES points: a change in (raw - adj) bigger than this = a roll before that session


def pins(psha, extra=None):
    """the run log's first lines (run-before-main rule (3)): every pinned hash this run checked"""
    got = {k: Q28.sha_ok(*v) for k, v in PINS.items()}
    print(f"PINS: prereg LF sha256 {psha}; harness sha256 {hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}; "
          + "; ".join(f"{k} {v}" for k, v in got.items()) + (f"; power {extra}" if extra else ""), flush=True)
    return got


def prereg_ok():
    got = hashlib.sha256(open(PREREG, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
    if not PREREG_SHA or got != PREREG_SHA:
        raise SystemExit(f"refused: {PREREG} reads {got[:16]}..., the registered sha is {PREREG_SHA[:16] or 'not set'} (nothing computed)")
    return got


# ------------------------------------------------------------------ the rule
def cme_holidays(df):
    """CME US-holiday sessions of an ES 5m RTH master (stock market closed): the session's bars run complete from the 09:30 bar to a LAST bar
    starting 12:55 or 13:00 (the published CME schedule; house rule - LATESTRESS r1, VRPES edit 13). NYSE early closes (last bar 13:10 / 13:15) stay"""
    ix = df.index.tz_convert("US/Eastern")
    g = pd.DataFrame({"day": ix.tz_localize(None).normalize(), "hm": ix.hour * 60 + ix.minute}).groupby("day")["hm"]
    first, last, n = g.min(), g.max(), g.nunique()
    keep = (first == 570) & last.isin([775, 780]) & (n == (last - 570) // 5 + 1)
    return pd.DatetimeIndex(first.index[keep.to_numpy()])


def drop_holiday_rows(vix, holidays):
    """MANAGER #126 (2): VIX rows dated on a CME-holiday session are dropped before any state reads them"""
    return vix[~vix.index.isin(holidays)]


def states(days, c_adj, vix):
    """the state known at the OPEN of each session d (MANAGER #126 (1): computed from the closes of the session before - ES's 16:00 print and the
    CBOE VIX close - and acted on at d's first RTH bar open): up = ES's prior 16:00 print above the mean of the 200 prints through it
    (Q28.trend_state), v = the last VIX close before d (Q28.prior_value, holiday rows already dropped). -> (up bool, v float) on `days`"""
    t = Q28.trend_state(days, c_adj).to_numpy()
    v = Q28.prior_value(days, vix).to_numpy(float)
    return t == "up", v


def units(up, v):
    """the units held from session d's first RTH open to session d+1's: CT1 = 1 when up and v <= 16; CT2 = min(2, 16 / v) when up; 0 otherwise
    and wherever v is missing"""
    ok = np.isfinite(v) & (v > 0)
    vv = np.where(ok, v, 1.0)
    return {"CT1": np.where(up & ok & (vv <= VIX_ON), 1.0, 0.0),
            "CT2": np.where(up & ok, np.minimum(W_MAX, VIX_ON / vv), 0.0)}


def leg_pnl(after, gap, day, roll):
    """after[d] = units held from session d's open (filled at that open) to session d+1's open; gap[d] = o_adj[d] - c_adj[d-1] (the night into d),
    day[d] = c_adj[d] - o_adj[d] (roll-corrected points); roll[d] = a roll falls in the night into d. The stretch starts FLAT (before[0] = 0).
    -> daily $ marked at each 16:00 print: before[d] x MES x gap[d] + after[d] x MES x day[d], less SIDE x |after[d] - before[d]| (the trade at d's
    open), less 2 x SIDE x before[d] when the position held through the night rolls (a roll = two sides). before[d] = after[d-1]"""
    after = np.asarray(after, float)
    before = np.concatenate([[0.0], after[:-1]])
    return (MES * (before * np.nan_to_num(np.asarray(gap, float)) + after * np.nan_to_num(np.asarray(day, float)))
            - SIDE * np.abs(after - before) - 2.0 * SIDE * before * np.asarray(roll, float))


def block_mask(n, k, rng, block=BLOCK):
    """a random hold-day set of exactly k of n days built from whole `block`-session slots on a random phase (circular), the last chosen slot
    trimmed: clustered like a regime filter, the count exactly the cell's"""
    if k <= 0:
        return np.zeros(n, bool)
    nb = n // block
    m = -(-k // block)
    if m > nb:
        raise ValueError(f"block_mask: {k} hold days need {m} slots, only {nb} fit")
    o = int(rng.integers(0, block))
    pick = rng.permutation(nb)[:m]
    out = np.zeros(n, bool)
    for j, s in enumerate(pick):
        ln = block - (m * block - k if j == m - 1 else 0)
        out[(o + s * block + np.arange(ln)) % n] = True
    return out


def null_masks(n_hold, n, seed, draws=N_DRAWS):
    rng = np.random.default_rng(seed)
    return np.vstack([block_mask(n, n_hold, rng) for _ in range(draws)])


def null_paths(masks, w_hold, gap, day, roll):
    """(draws, n) daily $ of random hold-day sets (null_masks, the cell's own count) carrying the cell's own average units on a held day, with the
    cell's fills (at the opens) and costs (trades at block edges, two sides on a held roll); the stretch starts flat like the cell"""
    return np.vstack([leg_pnl(m.astype(float) * w_hold, gap, day, roll) for m in masks])


def family_max(leads):
    """{cell: (draws,) ROC leads over the twin} -> (draws,) the MAX over the cells per draw (draw j of every cell = one family draw)"""
    return np.max(np.vstack([np.asarray(leads[c], float) for c in CELLS]), axis=0)


def mde_drift(Y, twin_roc, bar, q, n_hold, hold_masks, years=YEARS):
    """the daily $ drift added on held days that lifts the q-th percentile of the null's ROC lead to `bar` (bisection) -> (drift $ a held day,
    $ a year). Y = (draws, n) null paths; hold_masks = (draws, n) bool"""
    def lead_q(dr):
        r = roc30(Y + dr * hold_masks, years)
        r = np.where(np.isnan(r), 1e12, r) - twin_roc                    # NaN = no drawdown at all (never a loss) = better than any bar
        return float(np.percentile(r, q))
    lo, hi = 0.0, 1.0
    if lead_q(lo) >= bar:
        return 0.0, 0.0
    while lead_q(hi) < bar and hi < 1e6:
        hi *= 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if lead_q(mid) < bar else (lo, mid)
    return hi, hi * n_hold / years


def jy_years(dates):
    """July-June year label of each date (2016 = 2016-07-01 .. 2017-06-30)"""
    d = pd.DatetimeIndex(dates)
    return np.where(d.month >= 7, d.year, d.year - 1)


def without_best_pct(x, pct=1.0):
    x = np.sort(np.asarray(x, float))
    k = int(math.ceil(len(x) * pct / 100.0))
    return float(x[:len(x) - k].sum())


# ------------------------------------------------------------------ inputs
def load_inputs():
    """ES prints (roll-corrected 09:30 open and 16:00 print for P&L; unadjusted 16:00 print for the roll and notional), the VIX closes with the
    CME-holiday rows dropped, the S1 line - each cut before LB0"""
    import r17_resmom as R17
    D15 = R17.D15
    es, meta = D15.load_es(LB0)
    hol = cme_holidays(es["raw"])
    pr = D15.A13.hedge_prints(es)
    pr = pr[np.isfinite(pr["c_adj"]) & np.isfinite(pr["c_raw"]) & np.isfinite(pr["o_adj"])]
    pr = pr[pr.index < LB0]
    days = pd.DatetimeIndex(pr.index)
    assert not days.isin(hol).any(), "a CME-holiday session carries a 16:00 print - look first"
    cb = pd.read_csv(PINS["vix"][0], parse_dates=["date"]).set_index("date").sort_index()
    v_all = cb["VIX_close"][cb.index < LB0].dropna()
    vix = drop_holiday_rows(v_all, hol)
    ca, oa = pr["c_adj"].to_numpy(float), pr["o_adj"].to_numpy(float)
    gap = np.concatenate([[np.nan], oa[1:] - ca[:-1]])
    day = ca - oa
    off = (pr["c_raw"] - pr["c_adj"]).to_numpy(float)
    roll = np.concatenate([[False], np.abs(np.diff(off)) > ROLL_TOL])
    Ld = pd.read_csv(PINS["line"][0], parse_dates=["date"]).set_index("date").sort_index()
    L = Ld["book_mtm"].to_numpy(float) + C_RES * Ld["RES"].to_numpy(float)
    SL = R17.M12.Stretch(L, Ld.index, None, WF0, WF1)
    fl = R17.M12.vmeas(SL.x[None, :], SL.years)
    print(f"ES masters {meta['raw']['filename']} / {meta['adj']['filename']}; {len(days):,} sessions with the 09:30 open and both 16:00 prints, "
          f"{days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}; {len(hol)} CME-holiday sessions; VIX {vix.index[0]:%Y-%m-%d} .. {vix.index[-1]:%Y-%m-%d}, "
          f"{len(v_all) - len(vix)} holiday rows dropped ({', '.join(f'{x:%Y-%m-%d}' for x in v_all.index[v_all.index.isin(hol)][:6])} ...); "
          f"opens on a fallback bar {int(pr['open_fb'].sum())}", flush=True)
    print(f"THE S1 LINE: ROC@30k {float(fl['roc'][0]):.2f}; R {len(SL.qual)} episodes / {SL.n_dd_days} days (want 121.06, 45 / 762)", flush=True)
    if not (abs(float(fl["roc"][0]) - 121.06) <= 0.01 and len(SL.qual) == 45 and SL.n_dd_days == 762):
        raise SystemExit("PARITY STOP (nothing judged)")
    up, v = states(days, pr["c_adj"], vix)
    wf = np.asarray((days >= WF0) & (days <= WF1))
    return {"days": days, "wf": wf, "gap": gap[wf], "day": day[wf], "roll": roll[wf], "after": {c: u[wf] for c, u in units(up, v).items()},
            "SL": SL, "es_meta": meta, "vix_last": vix.index[-1], "holiday_rows_dropped": int(len(v_all) - len(vix)), "n_holidays": int(len(hol))}


def cell_counts(I):
    """per cell on the WF: held days (units after the open > 0), average units (the twin's size), average units on a held day - counts, no P&L"""
    out = {}
    for c in CELLS:
        a = I["after"][c]
        h = a > 0
        out[c] = {"n_hold": int(h.sum()), "n_days": int(len(a)), "wbar": float(a.mean()), "w_hold": float(a[h].mean()) if h.any() else 0.0,
                  "changes": int((np.abs(np.diff(np.concatenate([[0.0], a]))) > 0).sum())}
    return out


def on_line(I, x_wf):
    """a WF daily $ array on the ES session calendar -> the same on the S1 line's dates (a line date without an ES session = $0)"""
    s = pd.Series(x_wf, index=I["days"][I["wf"]])
    return s.reindex(I["SL"].dates).fillna(0.0).to_numpy(float)


# ------------------------------------------------------------------ dryload
def dryload():
    psha = prereg_ok()
    pins(psha)
    t0 = time.time()
    I = load_inputs()
    d = I["days"][I["wf"]]
    yrs = pd.Series(I["roll"], index=d).groupby(jy_years(d)).sum()
    print(f"WF sessions {len(d):,}; rolls by July-June year {dict((int(k), int(v)) for k, v in yrs.items())}; VIX last row {I['vix_last']:%Y-%m-%d} (< {LB0:%Y-%m-%d})")
    for c, v in cell_counts(I).items():
        print(f"  {c}: held {v['n_hold']:,} of {v['n_days']:,} WF sessions; average units {v['wbar']:.4f} (the twin's size); {v['w_hold']:.4f} on a held day; {v['changes']:,} changes of units")
    SL = I["SL"]
    mask = np.asarray(SL.dd, bool)
    loss = float(SL.x[mask].sum())
    h1 = on_line(I, (I["after"]["CT1"] > 0).astype(float)) > 0
    print(f"MAP SHARE under the final rule (no leg P&L): the sessions CT1 holds after the open carry ${SL.x[mask & h1].sum():,.0f} of R's ${loss:,.0f} = "
          f"{SL.x[mask & h1].sum() / loss:.1%} (step 1 read 28.4%; the floor is 15%)")
    print(f"dryload OK ({time.time() - t0:.0f}s) - no leg P&L computed")


# ------------------------------------------------------------------ power (the family null alone)
def power():
    psha = prereg_ok()
    pins(psha)
    t0 = time.time()
    I = load_inputs()
    gap, day, roll = I["gap"], I["day"], I["roll"]
    n = len(day)
    cc = cell_counts(I)
    tw = {c: leg_pnl(np.full(n, cc[c]["wbar"]), gap, day, roll) for c in CELLS}
    troc = {c: float(roc30(tw[c][None, :], YEARS)[0]) for c in CELLS}
    HM = {c: null_masks(cc[c]["n_hold"], n, SEEDS[c]) for c in CELLS}
    Y = {c: null_paths(HM[c], cc[c]["w_hold"], gap, day, roll) for c in CELLS}
    lead = {c: roc30(Y[c], YEARS) - troc[c] for c in CELLS}
    M = family_max(lead)
    bar = float(np.nanpercentile(M, 95))
    res = {"prereg_sha256_lf": psha, "draws": N_DRAWS, "block": BLOCK, "seeds": SEEDS, "years": YEARS, "wf_sessions": n, "counts": cc,
           "family_max_p95": bar, "family_max_p50": float(np.nanpercentile(M, 50)), "cells": {}}
    print(f"FAMILY NULL ({N_DRAWS} draws a cell, blocks of {BLOCK}; the statistic = ROC@30k lead over the same-exposure twin, MAX over CT1 / CT2): "
          f"p95 of the max = {bar:.2f} points (p50 {res['family_max_p50']:.2f})")
    for c in CELLS:
        d50, y50 = mde_drift(Y[c], troc[c], bar, 50, cc[c]["n_hold"], HM[c])
        d80, y80 = mde_drift(Y[c], troc[c], bar, 20, cc[c]["n_hold"], HM[c])
        med = int(np.argsort(np.nan_to_num(lead[c]))[N_DRAWS // 2])
        pl = power_line(Y[c][med], tw[c], YEARS, block=BLOCK)
        r = {"null_lead_p50": float(np.nanpercentile(lead[c], 50)), "null_lead_p95": float(np.nanpercentile(lead[c], 95)),
             "mde_points_over_null_median": bar - float(np.nanpercentile(lead[c], 50)),
             "mde_drift_50": {"per_held_day": d50, "per_year": y50}, "mde_drift_80": {"per_held_day": d80, "per_year": y80}, "power_line_proxy": pl}
        res["cells"][c] = r
        print(f"  {c}: random holding's lead over the twin p50 {r['null_lead_p50']:.2f} / p95 {r['null_lead_p95']:.2f}; to clear {bar:.2f} a cell needs "
              f"{r['mde_points_over_null_median']:.2f} points over random holding - a timing edge of ${d50:,.2f} a held day (${y50:,.0f} a year) at 50% power, "
              f"${d80:,.2f} (${y80:,.0f} a year) at 80%")
        print(f"      house power line on the median null draw vs its twin (a proxy - no cell P&L): SD {pl['sd']:.2f}, 50% line {pl['line_5pct']:.2f}, 80% line {pl['line_80pct']:.2f}")
    os.makedirs(OUT, exist_ok=True)
    with open(POWER_JSON, "w") as f:
        json.dump(res, f, indent=1)
    print(f"written {POWER_JSON} sha256 {hashlib.sha256(open(POWER_JSON, 'rb').read()).hexdigest()} ({time.time() - t0:.0f}s) - no cell P&L computed; "
          f"commit {os.path.basename(POWER_DOC)} quoting that sha before stage_a")
    return res


def power_committed():
    """stage_a's gate: the power addendum is committed in the repo and quotes this power file's sha256"""
    if not (os.path.exists(POWER_JSON) and os.path.exists(POWER_DOC)):
        raise SystemExit(f"refused: run `power` and commit {os.path.basename(POWER_DOC)} first (the power line is committed before any cell P&L)")
    ph = hashlib.sha256(open(POWER_JSON, "rb").read()).hexdigest()
    if ph[:16] not in open(POWER_DOC, encoding="utf-8").read():
        raise SystemExit(f"refused: {os.path.basename(POWER_DOC)} does not quote the power file's sha256 {ph[:16]}...")
    r = subprocess.run(["git", "-C", REPO, "log", "-1", "--format=%H %ci", "--", os.path.relpath(POWER_DOC, REPO).replace(os.sep, "/")], capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        raise SystemExit(f"refused: {os.path.basename(POWER_DOC)} is not committed")
    return {"power_sha256": ph, "power_doc_commit": r.stdout.strip()}


# ------------------------------------------------------------------ Stage A
def figs(x, dates):
    from augur_engine.drawdowns import dd5
    x = np.asarray(x, float)
    q = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max())
    dn = math.sqrt(float(np.mean(np.minimum(x, 0.0) ** 2)))
    r5 = dd5(pd.Series(x, index=pd.DatetimeIndex(dates)))
    return {"roc30": float(roc30(x[None, :], YEARS)[0]), "sortino": float(np.mean(x) / dn * math.sqrt(252.0)) if dn > 0 else float("nan"), "dd": dd,
            "net_per_year": float(np.sum(x)) / YEARS, "dd5": float(r5["dd5_usd"]), "one_episode": bool(r5["one_episode"])}


def on_R(SL, xl):
    """a daily $ array on the line's dates -> ($ on R, $ per qualifying episode)"""
    mask = np.asarray(SL.dd, bool)
    return float(xl[mask].sum()), [float(xl[e["i0"]:e["it"] + 1].sum()) for e in SL.qual]


def stage_a():
    psha = prereg_ok()
    pgate = power_committed()
    pins(psha, pgate)
    t0 = time.time()
    I = load_inputs()
    P = json.load(open(POWER_JSON))
    d = I["days"][I["wf"]]
    gap, day, roll = I["gap"], I["day"], I["roll"]
    n = len(day)
    cc = cell_counts(I)
    assert cc == P["counts"], "the hold counts moved since the power line - look first"
    bar = P["family_max_p95"]
    SL = I["SL"]
    Lw = SL.x
    sw = (SL.dates >= SEAT_WINDOW[0]) & (SL.dates <= SEAT_WINDOW[1])
    es_d = MES * (np.nan_to_num(gap) + np.nan_to_num(day))
    res = {"prereg_sha256_lf": psha, "power": pgate, "family_max_p95": bar, "cells": {}}
    for c in CELLS:
        x = leg_pnl(I["after"][c], gap, day, roll)
        t = leg_pnl(np.full(n, cc[c]["wbar"]), gap, day, roll)
        fx, ft = figs(x, d), figs(t, d)
        lead = fx["roc30"] - ft["roc30"]
        xl, tl = on_line(I, x), on_line(I, t)
        xR, xper = on_R(SL, xl)
        tR, tper = on_R(SL, tl)
        kb = int(np.argmax(xper))
        jy = pd.Series(x).groupby(jy_years(d)).sum()
        pos_years = int((jy > 0).sum())
        wo1 = without_best_pct(x, 1.0)
        beta = float(np.polyfit(es_d, x, 1)[0])
        half = np.asarray(d < TS("2021-01-01"))
        halves = {nm: {"cell": float(roc30(x[m][None, :], (d[m][-1] - d[m][0]).days / 365.25)[0]),
                       "twin": float(roc30(t[m][None, :], (d[m][-1] - d[m][0]).days / 365.25)[0])} for nm, m in (("2016-07..2020-12", half), ("2021-01..2025-06", ~half))}
        ok_i = bool(lead > 0 and lead > bar)
        ok_ii = bool(xR > tR and (xR - xper[kb]) > (tR - tper[kb]))
        ok_iii = bool(pos_years >= 6 and wo1 > 0)
        seat = {}
        for sh in SHARES:
            sx, sr = float(np.std(xl[sw], ddof=1)), float(np.std(Lw[sw], ddof=1))
            cx = sh * sr / sx if sx > 0 else float("nan")
            seat[f"{sh:.2f}"] = {"c": cx, "line_plus": figs(Lw + cx * xl, SL.dates) if np.isfinite(cx) else None}
        worst = np.argsort(x)[:5]
        r = {"cell": fx, "twin": ft, "twin_units": cc[c]["wbar"], "lead": lead, "beats_null_p95": bool(lead > bar),
             "on_R": {"cell": xR, "twin": tR, "cell_without_best": xR - xper[kb], "twin_same_episode_out": tR - tper[kb],
                      "best_episode": [str(SL.dates[SL.qual[kb]["i0"]].date()), str(SL.dates[SL.qual[kb]["it"]].date())]},
             "years_positive": pos_years, "by_year": {int(k): float(v) for k, v in jy.items()}, "without_best_1pct": wo1, "beta_per_es_dollar": beta,
             "halves": halves, "worst_5_days": [[str(d[i].date()), float(x[i])] for i in worst], "seat_read": seat,
             "bar": {"i_overall": ok_i, "ii_on_R": ok_ii, "iii_robust": ok_iii}, "verdict": "PASS" if (ok_i and ok_ii and ok_iii) else "FAIL"}
        res["cells"][c] = r
        print(f"\n{c}: ROC@30k {fx['roc30']:.2f} (Sortino {fx['sortino']:.2f}, DD5 ${fx['dd5']:,.0f}, worst ${fx['dd']:,.0f}, ${fx['net_per_year']:,.0f}/yr) vs "
              f"twin at {cc[c]['wbar']:.3f} units {ft['roc30']:.2f} (DD5 ${ft['dd5']:,.0f}, worst ${ft['dd']:,.0f}); lead {lead:+.2f} vs the family null's p95 {bar:.2f} -> (i) {ok_i}")
        print(f"   on R: cell ${xR:,.0f} vs twin ${tR:,.0f}; the cell's best R episode out of both: ${xR - xper[kb]:,.0f} vs ${tR - tper[kb]:,.0f} -> (ii) {ok_ii}")
        print(f"   years positive {pos_years} of {len(jy)}; without its best 1% of days ${wo1:,.0f} -> (iii) {ok_iii}; beta {beta:.3f} per ES $ a unit; halves "
              + "; ".join(f"{k} {v['cell']:.1f} vs {v['twin']:.1f}" for k, v in halves.items()))
        print("   worst 5 days " + ", ".join(f"{a} ${b:,.0f}" for a, b in r["worst_5_days"]))
        for sh, s in seat.items():
            lp = s["line_plus"]
            print(f"   SEAT READ (report) share {sh}: c {s['c']:.3f} -> L + cX ROC {lp['roc30']:.2f} / DD5 ${lp['dd5']:,.0f} (L 121.06 / $34,392)" if lp else f"   SEAT READ share {sh}: no variance in the sizing window")
        print(f"   VERDICT {c}: {r['verdict']}")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "calmtape_stage_a.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(f"\nwritten {os.path.join(OUT, 'calmtape_stage_a.json')} ({time.time() - t0:.0f}s)")
    return res


# ------------------------------------------------------------------ selftest
def selftest():
    for fn in ("cme_holidays", "drop_holiday_rows", "states", "units", "leg_pnl", "block_mask", "null_masks", "null_paths", "family_max", "mde_drift",
               "load_inputs", "cell_counts", "on_line", "dryload", "power", "power_committed", "stage_a", "figs", "on_R"):
        assert callable(globals().get(fn)), f"command / helper {fn} is missing"
    d = pd.bdate_range("2020-01-01", periods=260)
    c = pd.Series(np.r_[np.full(200, 100.0), np.linspace(101, 120, 60)], index=d)
    vix = pd.Series(np.r_[np.full(230, 15.0), np.full(30, 20.0)], index=d)
    up, v = states(d, c, vix)
    assert not up[200] and up[201] and up[259], "the state at d's open reads the close before d (d[200]'s is d[199] = its mean -> not up)"
    assert np.isnan(v[0]) and v[230] == 15.0 and v[231] == 20.0, "VIX: the last close before d"
    u = units(up, v)
    assert u["CT1"][201] == 1.0 and u["CT1"][231] == 0.0 and u["CT1"][0] == 0.0
    assert u["CT2"][201] == min(2.0, 16.0 / 15.0) and abs(u["CT2"][231] - 0.8) < 1e-12 and u["CT2"][100] == 0.0
    assert units(np.array([True]), np.array([np.nan]))["CT2"][0] == 0.0 and units(np.array([True]), np.array([4.0]))["CT2"][0] == 2.0
    # open fills: 1 unit bought at d1's open, held through d2, sold at d3's open; ES nights +1 / +2 / -3, days +4 / -1 / +5; roll in the night into d2
    p = leg_pnl([0.0, 1.0, 1.0, 0.0], [np.nan, 1.0, 2.0, -3.0], [0.5, 4.0, -1.0, 5.0], [False, False, True, False])
    assert np.allclose(p, [0.0, 20.0 - 2.5, 10.0 - 5.0 - 5.0, -15.0 - 2.5]), p
    tw = leg_pnl(np.full(3, 0.5), [np.nan, 2.0, -1.0], [1.0, 1.0, 1.0], [False, True, False])
    assert np.allclose(tw, [2.5 - 1.25, 7.5 - 2.5, 0.0]), "the twin: bought at the first open, marked night + day, two sides a roll"
    bars = pd.DatetimeIndex([f"2024-01-15 {h}" for h in ("09:30", "09:35", "12:55")] + [f"2024-01-16 {h}" for h in ("09:30", "09:35", "15:55")]
                            + [f"2024-11-29 {h}" for h in ("09:30", "13:10")]).tz_localize("US/Eastern")
    full = pd.date_range("2024-01-15 09:30", "2024-01-15 12:55", freq="5min", tz="US/Eastern").append(bars[3:])
    hol = cme_holidays(pd.DataFrame({"close": 1.0}, index=full))
    assert list(hol) == [TS("2024-01-15")], hol
    assert len(cme_holidays(pd.DataFrame({"close": 1.0}, index=bars))) == 0, "a holiday session must run complete from 09:30"
    vx = pd.Series([13.0, 14.0, 15.0], index=pd.DatetimeIndex(["2024-01-12", "2024-01-15", "2024-01-16"]))
    assert list(drop_holiday_rows(vx, hol).index) == [TS("2024-01-12"), TS("2024-01-16")]
    assert Q28.prior_value(pd.DatetimeIndex(["2024-01-16"]), drop_holiday_rows(vx, hol)).iloc[0] == 13.0, "the holiday row never decides"
    rng = np.random.default_rng(1)
    for n, k in ((100, 37), (2270, 1030), (2270, 1800), (60, 0), (40, 40)):
        assert block_mask(n, k, rng).sum() == k, (n, k)
    m = block_mask(200, 60, np.random.default_rng(3))
    runs = np.diff(np.flatnonzero(np.diff(np.r_[0, m.astype(int), 0])))[::2]
    assert runs.max() >= 20, "blocks of 20 (adjacent slots may merge)"
    hm = null_masks(30, 200, 11, draws=5)
    assert hm.shape == (5, 200) and (hm.sum(axis=1) == 30).all() and (null_masks(30, 200, 11, draws=5) == hm).all(), "fixed stream"
    z = np.zeros(200)
    Y2 = null_paths(hm, 0.5, z, z, np.zeros(200, bool))
    edges = np.abs(np.diff(np.concatenate([np.zeros((5, 1)), hm.astype(float)], axis=1), axis=1)).sum(axis=1)
    assert np.allclose(Y2.sum(axis=1), -SIDE * 0.5 * edges), "flat ES: a null path pays one side per change of units"
    Y3 = null_paths(hm, 0.5, z, z, np.ones(200, bool))
    befores = np.concatenate([np.zeros((5, 1)), hm[:, :-1].astype(float)], axis=1).sum(axis=1)
    assert np.allclose(Y3.sum(axis=1) - Y2.sum(axis=1), -2.0 * SIDE * 0.5 * befores), "two sides on every roll held through the night"
    assert np.allclose(family_max({"CT1": [1.0, 5.0, np.nan], "CT2": [2.0, 3.0, 4.0]})[:2], [2.0, 5.0])
    assert list(jy_years(pd.DatetimeIndex(["2016-07-01", "2017-06-30", "2017-07-03"]))) == [2016, 2016, 2017]
    assert without_best_pct(np.arange(1.0, 101.0)) == float(np.arange(1.0, 100.0).sum())
    base = np.zeros((3, 10)) + np.array([[1.0, -1.0] * 5])
    dr, _ = mde_drift(base, 0.0, 5.0, 50, 10, np.ones((3, 10), bool), years=1.0)
    assert dr > 0 and abs(float(np.percentile(roc30(base + dr, 1.0), 50)) - 5.0) < 1e-6
    print("r30_calmtape selftest OK (states at the open from the prior closes, units, open-fill P&L with trade / roll costs, the twin, the CME-holiday drop, "
          "exact-count 20-session blocks on a fixed stream, null costs, the family max, July-June years, best 1%, the MDE bisection; every command defined)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    selftest()
    if cmd in ("dryload", "power", "stage_a"):
        globals()[cmd]()
    elif cmd != "selftest":
        raise SystemExit(f"unknown command {cmd}")
