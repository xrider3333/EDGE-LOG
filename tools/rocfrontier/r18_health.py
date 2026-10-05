"""BOOK HEALTH r1 (round 18, 2026-10-05): is the ADOPTED book #463's forward (paper) record still the book its walk-forward described?

THE QUESTION. #463 was adopted on its walk-forward stretch (WF, 2016-07-01..2025-06-29) and its lockbox year. From 2026-09-28 it trades on
paper, one daily $ figure a day. Every day the owner wants, this harness asks: does that forward record so far look like a draw from the
WF distribution - in its drift (H1), in the depth of its drawdown for the length observed (H2) - and are its legs firing at their WF rate
(H3)? And, before any forward row is read: if the edge halved or vanished tomorrow, how many trading days until H1 says so? It never asks
whether the book is good: ROC / Sortino of the forward record belong to the registered forward reads and nothing here computes them.

THE REFERENCE (calibrate). The WF rows of the book's own valued-daily $ series (r11_risk.py's records, loaded through r14_looks.load_records
with r11's READY and hashes checked; the rows must reproduce the recorded WF 93.81 / 3.816 / $44,849): mu0 = their mean per row, sigma0 =
their sample sd, and per leg (ORB, ENGU-Q, TTM, NOISE) the closed trades per row, a trade on its exit row. The null is a circular block
bootstrap of those rows: NDRAW draws of 756 rows, block BLOCK, numpy default_rng(SEED), the $ row and its four leg counts drawn TOGETHER,
built in chunks of CHUNK draws; every horizon (252 / 504 / 756 rows) reads the first n rows of the same draws.

THE MONITORS.
  H1 DECAY (primary): on z_t = (x_t - mu0) / sigma0 the one-sided CUSUM for a fall in the mean, C_t = max(0, C_(t-1) - z_t - k), C_0 = 0,
     with the textbook reference value k = delta / 2 for the fall that matters most, the whole edge vanishing: delta = mu0 / sigma0, so
     k = K_FRACTION x mu0 / sigma0, computed at calibrate and stored. The chart then drifts DOWN by k a row while the book earns its WF mean and
     UP by k a row when it earns nothing; a fixed k = 0.5 (a one-sigma fall) would drift down even at zero edge whenever mu0 / sigma0 < 0.5,
     which is #463's case. ALARM once C_t has reached h1 on any forward row; h1 is the smallest H_GRID value at which at most FA_LEVEL of the
     null draws alarm within 252 rows, and it must sit strictly below the grid's top (else calibrate refuses). H1 has no WARN state.
  H1b ZERO (report only): the same CUSUM with mu0 replaced by zero (is the book earning anything), the same calibrated k, its own h1b.
  H2 DRAWDOWN (primary): the forward record's current depth below its running peak (peak starting at zero) against the null distribution of
     the MAXIMUM drawdown over the first n rows, n = the rows observed so far: ALARM at or above the DD_ALARM_Q quantile, WARN at or above
     DD_WARN_Q, else OK. Beside it: the share of null paths of this length with a deeper drawdown (a p-value-like figure, not a test), and
     the WF worst ($44,849) and lockbox worst ($49,855) as context - the lockbox is never re-read.
  H3 FIRING (report only): per leg, closed trades so far against the WF rate x rows: the Poisson 2.5 / 97.5 % band and the block-bootstrap
     band from the same draws; UNDER / OVER outside the bootstrap band. It never alarms.
  JOINT (calibration only): the share of null draws alarming on H1 or H2 within 252 rows - the pair's false-alarm rate.
  POWER (calibration only): null draws shifted row by row to a forward mean of 0.5 x / 0 x / -0.5 x mu0 -> the share H1 alarms on within
     252 / 504 / 756 rows and the median / 90th-percentile day of first alarm, taken over ALL draws with a never-alarmed draw counted as
     beyond the horizon (a quantile past 756 prints ">756", json null); deviations from mu0 scaled by SCALE_ALT -> the share H2 alarms on
     within 252 rows. The headline: "if #463 stopped earning tomorrow, H1 would alarm after a median of N trading days".

THE READING RULES.
  * The only forward figures printed are the CUSUM values, the current drawdown depth and the trade counts. No ROC, no Sortino, no net.
  * The only words about the book are the monitor states OK / WARN / ALARM (and within / UNDER / OVER for H3). Never a verdict.
  * An ALARM is an owner question via MANAGER, never automatic; a WARN is logged; the harness changes nothing. H1 does not un-alarm: once
    C_t has reached h1 the alarm stands on every later read until the owner has acted (a reset is an owner decision, outside this file).
  * A forward row dated on or before WF1 (2025-06-29) or before --from is refused: a backtest row is pretending to be forward. --from
    defaults to FORWARD_FROM_DEFAULT and can only move the start LATER; an earlier --from is refused (it could admit lockbox rows).
  * The forward csv is one row per WEEKDAY, a holiday as a 0 row - the reference's own row convention (Book.index is every weekday), so
    n forward rows line up with the first n rows of a null draw. A missing weekday between two rows, a non-increasing date, a weekend
    date and a missing pnl are refused.
  * The registered horizon is 756 forward rows; more rows observed are refused - a longer record is r2's question.

COMMANDS (results go to OUT, outside git; nothing here commits, pushes, queues a job or touches the box's caches from a smoke):
  python r18_health.py calibrate                          reference + null draws + thresholds + power table -> calibration.json, null.npz,
                                                          CALIBRATION.txt, READY (refused while PREREG_SHA is 'TBD' or the prereg changed)
  python r18_health.py read CSV [--from D] [--asof D]     the forward csv (date, pnl, optional n_ORB n_ENGUQ n_TTM n_NOISE) -> HEALTH_<asof>.txt
                                                          and health_<asof>.json (refused without READY, on a sha mismatch or on a bad row)
  python r18_health.py smoke DIR                          offline synthetic world (DIR's name must contain 'smoke', never under C:\\EdgeLog);
                                                          its numbers mean nothing
Pre-registered: tools/rocfrontier/PREREG_HEALTH_R1.txt - PREREG_SHA below is that file's canonical-LF sha256 (R11.sha_lf), 'TBD' until it is
registered. Every rule, seed, grid and threshold is that file; where it is silent the choice is marked CHOICE.
"""
import csv, json, math, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r11_risk as R11
import r14_looks as R14

OUT = os.environ.get("EDGELOG_ROCFRONTIER_HEALTH", r"C:\EdgeLog\_anatomy_cache\rocfrontier\health_r1")
PREREG = os.path.join(HERE, "PREREG_HEALTH_R1.txt")
PREREG_SHA = "TBD"                                           # canonical-LF sha256 of PREREG_HEALTH_R1.txt, written in before calibrate runs
WF0, WF1 = "2016-07-01", "2025-06-29"                        # the walk-forward window; reference rows = Book.index within it, inclusive
WF_REF = (93.81, 3.816, 44849.0)                             # the recorded WF roc / Sortino / worst drawdown the reference rows must reproduce
LB_WORST_DD = 49855.0                                        # lockbox worst drawdown, printed as context only (already public; never re-read)
FORWARD_FROM_DEFAULT = "2026-09-28"                          # first forward day of the adopted book's paper line
BLOCK = 21                                                   # bootstrap block, rows (the house's three-week block)
NDRAW = 20000                                                # null draws (smoke thins to 400)
SEED = 20261021
HORIZONS = (252, 504, 756)                                   # one, two, three years of forward rows; 756 is the registered horizon
K_FRACTION = 0.5                                             # k = K_FRACTION x delta, delta = mu0 / sigma0 (the whole edge vanishing): the textbook k = delta / 2
H_GRID = np.round(np.arange(0.5, 60.0 + 1e-9, 0.25), 2)      # candidate CUSUM thresholds (0.5..60: a null drifting down by only k a row needs room; delta 0.15 sits near 23)
FA_LEVEL = 0.05                                              # per monitor, per 252 forward rows
DD_ALARM_Q, DD_WARN_Q = 0.99, 0.95
ALTS = (0.5, 0.0, -0.5)                                      # forward mean as a multiple of the WF mean, for the power table
SCALE_ALT = 1.5                                              # forward dispersion multiple, for H2's detection table
LEGS = ("ORB", "ENGU-Q", "TTM", "NOISE")
COUNT_COLS = {"ORB": ("n_ORB",), "ENGU-Q": ("n_ENGUQ", "n_ENGU-Q"), "TTM": ("n_TTM",), "NOISE": ("n_NOISE",)}
HMAX = max(HORIZONS)
CHUNK = 2500                                                 # draws built per chunk (bounds memory)
BAND_Q = (0.025, 0.975)                                      # H3's bands
LADDER_Q = np.round(np.linspace(0.0, 1.0, 1001), 3)          # CHOICE: the null max-drawdown cdf is kept per n to 0.001 (the 'deeper' share)
CHECK_REFS = True        # a real calibrate holds the reference rows to the recorded WF figures; only smoke() switches it (a synthetic world cannot match)
SMOKE_TBD_OK = False     # only smoke() tolerates PREREG_SHA == "TBD"
MANAGER = "owner question via MANAGER, never automatic"


def asc(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")        # console and files stay ASCII (cp1252 on the box)


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(json.dumps(obj, indent=1, default=R11.js))


def _ready_path():
    return os.path.join(OUT, "READY")


def check_prereg(path=None, want=None):
    """The prereg's canonical-LF sha against the registered PREREG_SHA; 'TBD' refuses unless smoke() set SMOKE_TBD_OK."""
    path, want = path or PREREG, want or PREREG_SHA
    got = R11.sha_lf(path) if os.path.isfile(path) else None
    if want == "TBD":
        if SMOKE_TBD_OK:
            return got or "TBD"
        raise SystemExit("refused: PREREG_SHA is 'TBD' - the prereg is not registered yet "
                         + (f"(the file hashes to {got})" if got else f"({os.path.basename(path)} is not on disk)"))
    if got is None:
        raise SystemExit(f"refused: {os.path.basename(path)} is not on disk - the registered plan is missing")
    if got != want:
        raise SystemExit(f"refused: {os.path.basename(path)} sha256 {got} is not the registered {want} - the plan changed after it was registered")
    return got


def load_records():
    """#463's records through r14 (r11's READY + hashes checked): (Book, legs meta, record hashes). smoke() rebinds this name to a stub."""
    return R14.load_records()


# ------------------------------------------------------------------ the reference: WF rows, mu0 / sigma0, per-leg counts
def wf_rows(B):
    d = pd.DatetimeIndex(B.index)
    return np.flatnonzero(np.asarray((d >= pd.Timestamp(WF0)) & (d <= pd.Timestamp(WF1))))


def leg_counts(B, meta, rows):
    """Closed trades per row and LEGS family (a trade sits on its EXIT row, r14's rule) on `rows`: ((len(rows), 4) ints, meta families)."""
    n = len(B.index)
    C = np.zeros((n, len(LEGS)), np.int64)
    fams = []
    for j, m in enumerate(meta):
        f = R14.fam(m["strategy"])
        if f not in LEGS:
            raise SystemExit(f"refused: leg {j} {m['strategy']} maps to family {f!r}, not one of {LEGS}")
        fams.append(f)
        sel = np.asarray(B.leg) == j
        np.add.at(C[:, LEGS.index(f)], np.asarray(B.xrow)[sel], 1)
    return C[rows], fams


def reference(B, meta):
    rows = wf_rows(B)
    if len(rows) < 10 * BLOCK:
        raise SystemExit(f"refused: only {len(rows)} reference rows inside {WF0}..{WF1}")
    x = np.asarray(B.raw, float)[rows]
    if not np.isfinite(x).all():
        raise SystemExit("refused: a reference row is not finite")
    C, fams = leg_counts(B, meta, rows)
    mu0, sigma0 = float(x.mean()), float(x.std(ddof=1))                   # CHOICE: sample sd (ddof 1), as r14's calibration
    if not sigma0 > 0:
        raise SystemExit("refused: the reference rows have no dispersion")
    if not mu0 > 0:
        raise SystemExit("refused: the WF mean is not positive - k = delta / 2 needs an edge to watch")
    k = K_FRACTION * mu0 / sigma0                                            # the CUSUM reference value: half the fall to zero edge, sigma0 units
    u = R11.unified(B, B.raw, pd.Timestamp(WF0), pd.Timestamp(WF1))        # the recorded WF figures, re-asserted on load (prereg REFERENCE)
    ok = abs(u["roc"] - WF_REF[0]) < R11.P2_TOL[0] and abs(u["sort"] - WF_REF[1]) < R11.P2_TOL[1] and abs(u["dd"] - WF_REF[2]) < 1.0
    if CHECK_REFS and not ok:
        raise SystemExit(f"refused: the WF rows give roc {u['roc']:.3f} sort {u['sort']:.4f} dd {u['dd']:,.0f}, not the recorded "
                         f"{WF_REF[0]} / {WF_REF[1]} / {WF_REF[2]:,.0f} - reconcile with r11_risk.py parity first")
    return {"x": x, "counts": C, "mu0": mu0, "sigma0": sigma0, "k": k, "n_rows": int(len(x)), "fams": fams,
            "first": str(pd.Timestamp(B.index[rows[0]]).date()), "last": str(pd.Timestamp(B.index[rows[-1]]).date()),
            "trades_wf": {f: int(C[:, i].sum()) for i, f in enumerate(LEGS)}, "rate": {f: float(C[:, i].sum() / len(x)) for i, f in enumerate(LEGS)},
            "wf_figures": {"roc": u["roc"], "sort": u["sort"], "dd": u["dd"], "net": u["net"], "as_recorded": bool(ok), "checked": CHECK_REFS}}


# ------------------------------------------------------------------ the null draws and the monitor arithmetic
def block_starts(rng, n_src, ndraw, nrows=HMAX, block=BLOCK):
    """One uniform circular start per block per draw: (ndraw, ceil(nrows / block)) ints - the whole draw set, a few MB."""
    return rng.integers(n_src, size=(ndraw, -(-nrows // block))).astype(np.int32)


def expand(starts, n_src, nrows=HMAX, block=BLOCK):
    """Block starts -> row indices (draws, nrows): contiguous slices of the source, wrapping around its end, laid end to end and trimmed."""
    s = np.asarray(starts, np.int64)
    idx = (s[:, :, None] + np.arange(block)[None, None, :]) % n_src
    return idx.reshape(s.shape[0], -1)[:, :nrows]


def cusum(z, k):
    """The one-sided lower CUSUM path C_t = max(0, C_(t-1) - z_t - k), C_0 = 0, k the calibrated reference value (always passed, never a default):
    a 1-D z -> its path; a (draws, T) z -> every path (loop over t, numpy over draws)."""
    z = np.asarray(z, float)
    Z = z[None, :] if z.ndim == 1 else z
    C = np.zeros_like(Z)
    c = np.zeros(Z.shape[0])
    for t in range(Z.shape[1]):
        c = np.maximum(0.0, c - Z[:, t] - k)
        C[:, t] = c
    return C[0] if z.ndim == 1 else C


def first_cross(C, h):
    """The 1-based row at which each path first reaches h (0 = never)."""
    hit = np.atleast_2d(np.asarray(C, float)) >= h
    return np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, 0)


def ddpath_rows(X):
    """r11.ddpath on every row of X (peak starts at 0)."""
    c = np.cumsum(np.asarray(X, float), axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.zeros((c.shape[0], 1)), c], axis=1), axis=1)[:, 1:]
    return peak - c


def h_search(cmax, level=FA_LEVEL):
    """The smallest H_GRID value at which the share of draws whose max CUSUM reaches it is <= level (None when no grid value does), + the shares."""
    cmax = np.asarray(cmax, float)
    fa = np.array([float(np.mean(cmax >= h)) for h in H_GRID])
    i = np.flatnonzero(fa <= level)
    return (float(H_GRID[i[0]]) if len(i) else None), fa


def h_interior(h, name):
    """The threshold must sit strictly below the grid's top (None or the top value refuses - widening H_GRID is a prereg change, not a run-time
    choice); the bottom value is accepted and printed. Returns True when h is the bottom value."""
    if h is None or h >= float(H_GRID[-1]):
        raise SystemExit(f"refused: {name} {'is not on' if h is None else 'sits at the top of'} H_GRID ({H_GRID[0]}..{H_GRID[-1]}) - the null's CUSUM "
                         f"excursions outrun the registered grid at the {FA_LEVEL} level; widening it is a prereg change, not a run-time choice")
    bottom = bool(h <= float(H_GRID[0]))
    if bottom:
        print(f"note: {name} sits at the bottom of H_GRID ({H_GRID[0]}) - the null's false-alarm share is already under {FA_LEVEL} there", flush=True)
    return bottom


def h2_state(depth, q95, q99):
    """ALARM at or above the 99th-percentile null max drawdown for this length, WARN at or above the 95th; no drawdown is never a state (CHOICE)."""
    if depth > 0 and depth >= q99:
        return "ALARM"
    if depth > 0 and depth >= q95:
        return "WARN"
    return "OK"


def h3_flag(obs, lo, hi):
    return "UNDER" if obs < lo else "OVER" if obs > hi else "within"


def poisson_band(lam, q=BAND_Q):
    """(lo, hi): the smallest counts whose Poisson(lam) cdf reaches q[0] and q[1] (log-space pmf, no scipy); lam <= 0 -> (0, 0)."""
    lam = float(lam)
    if lam <= 0:
        return 0, 0
    k, logp, cdf, lo = 0, -lam, 0.0, None
    llam, cap = math.log(lam), lam + 20.0 * math.sqrt(lam) + 100.0
    while True:
        cdf += math.exp(logp)
        if lo is None and cdf >= q[0]:
            lo = k
        if cdf >= q[1] or k > cap:
            return (lo if lo is not None else k), k
        k += 1
        logp += llam - math.log(k)


def q_sorted(S, p):
    """np.quantile's default linear rule on columns already sorted along axis 0: S (N, m), p scalar or (k,) -> (m,) or (k, m)."""
    S = np.asarray(S)
    N = S.shape[0]
    pos = np.atleast_1d(np.asarray(p, float)) * (N - 1)
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, N - 1)
    w = (pos - lo)[:, None]
    out = S[lo] * (1.0 - w) + S[hi] * w
    return out if np.ndim(p) else out[0]


def pass_null(ref, starts):
    """One pass over the draws in chunks: each draw's max CUSUM within 252 rows (vs mu0 and vs 0), its running max drawdown at every n
    (float64, exact for the hand checks) and its cumulative leg counts at every n (small ints) - the only arrays kept across chunks."""
    x, Cn, mu0, s0, k, n = ref["x"], ref["counts"], ref["mu0"], ref["sigma0"], ref["k"], ref["n_rows"]
    nd = starts.shape[0]
    cdt = np.int16 if int(Cn.max()) * HMAX < 32000 else np.int32
    cmax, cmax0 = np.zeros(nd), np.zeros(nd)
    MDD = np.zeros((nd, HMAX), np.float64)
    CUM = np.zeros((nd, HMAX, len(LEGS)), cdt)
    for s in range(0, nd, CHUNK):
        idx = expand(starts[s:s + CHUNK], n)
        X = x[idx]
        cmax[s:s + CHUNK] = cusum((X[:, :252] - mu0) / s0, k).max(axis=1)
        cmax0[s:s + CHUNK] = cusum(X[:, :252] / s0, k).max(axis=1)
        MDD[s:s + CHUNK] = np.maximum.accumulate(ddpath_rows(X), axis=1)
        CUM[s:s + CHUNK] = np.cumsum(Cn[idx], axis=1)
    return {"cmax252": cmax, "cmax252_zero": cmax0, "MDD": MDD, "CUM": CUM}


def dd_tables(MDD):
    """Per n (prefix length): the DD_WARN_Q / DD_ALARM_Q quantiles of the null max drawdown and its cdf ladder at LADDER_Q (sorted once)."""
    S = np.sort(np.asarray(MDD, np.float64), axis=0)
    q = q_sorted(S, [DD_WARN_Q, DD_ALARM_Q])
    return q[0], q[1], q_sorted(S, LADDER_Q).T.astype(np.float32)


def count_bands(CUM):
    """Per n and leg: the bootstrap band of the cumulative count - lo = the BAND_Q[0] quantile rounded down to a draw, hi = the BAND_Q[1]
    quantile rounded up (np.quantile's 'lower' / 'higher' rules; CHOICE, the band is widened to whole trades)."""
    lo, hi = np.zeros(CUM.shape[1:], np.int64), np.zeros(CUM.shape[1:], np.int64)
    N = CUM.shape[0]
    for j in range(CUM.shape[2]):
        S = np.sort(CUM[:, :, j], axis=0)
        lo[:, j] = S[int(math.floor(BAND_Q[0] * (N - 1)))]
        hi[:, j] = S[int(math.ceil(BAND_Q[1] * (N - 1)))]
    return lo, hi


def share_deeper(ladder, n, depth):
    """The share of null paths of n rows whose max drawdown exceeds `depth`, from the stored cdf ladder (to 0.001)."""
    row = np.asarray(ladder)[n - 1]
    return float(1.0 - np.searchsorted(row, depth, side="right") / len(row))


def pass_power(ref, starts, h1, h1b, q99):
    """The second pass over the SAME draws, once h1 is known: the first-alarm row of H1 at every ALTS shift (and unshifted), of H1b
    unshifted, and whether H2 reaches ALARM within 252 rows unshifted and at SCALE_ALT dispersion."""
    x, mu0, s0, k, n = ref["x"], ref["mu0"], ref["sigma0"], ref["k"], ref["n_rows"]
    nd = starts.shape[0]
    alts = (1.0,) + tuple(ALTS)
    first = {a: np.zeros(nd, np.int64) for a in alts}
    first0, h2_null, h2_scale = np.zeros(nd, np.int64), np.zeros(nd, bool), np.zeros(nd, bool)
    q = np.asarray(q99, float)[:252]
    for s in range(0, nd, CHUNK):
        idx = expand(starts[s:s + CHUNK], n)
        X = x[idx]
        for a in alts:
            first[a][s:s + CHUNK] = first_cross(cusum((X + (a - 1.0) * mu0 - mu0) / s0, k), h1)
        first0[s:s + CHUNK] = first_cross(cusum(X / s0, k), h1b)
        dd = ddpath_rows(X[:, :252])
        h2_null[s:s + CHUNK] = ((dd > 0) & (dd >= q)).any(axis=1)
        dd = ddpath_rows(mu0 + SCALE_ALT * (X[:, :252] - mu0))
        h2_scale[s:s + CHUNK] = ((dd > 0) & (dd >= q)).any(axis=1)
    return {"first": first, "first_zero": first0, "h2_null": h2_null, "h2_scale": h2_scale}


def day_quantile(first, q):
    """The q-quantile of the first-alarm day over ALL draws, a never-alarmed draw counted as beyond the horizon: the smallest day d with
    share(first alarm <= d) >= q (np.quantile's inverted_cdf rule on the days with +inf for 'never'); None when fewer than a share q of the
    draws alarm within HMAX rows (printed '>756', json null)."""
    f = np.asarray(first)
    al = np.sort(f[f > 0])
    need = max(1, int(math.ceil(q * len(f) - 1e-9)))
    return float(al[need - 1]) if len(al) >= need else None


def alarm_summary(first):
    f = np.asarray(first)
    return {"share": {str(H): float(np.mean((f > 0) & (f <= H))) for H in HORIZONS}, "n_alarm_756": int((f > 0).sum()), "n_draws": int(len(f)),
            "median_day": day_quantile(f, 0.5), "p90_day": day_quantile(f, 0.9)}


def dfmt(d):
    return f">{HMAX}" if d is None else f"{d:.0f}"


# ------------------------------------------------------------------ calibrate
def calibrate():
    t0 = time.time()
    psha = check_prereg()
    if os.path.exists(_ready_path()):                     # any earlier READY is revoked before a new reference is computed (r11's rule)
        os.remove(_ready_path())
    B, meta, hashes = load_records()
    ref = reference(B, meta)
    print(f"reference: {ref['n_rows']} WF rows {ref['first']}..{ref['last']}; mu0 ${ref['mu0']:,.2f}/row, sigma0 ${ref['sigma0']:,.2f}/row; "
          f"WF roc {ref['wf_figures']['roc']:.3f} sort {ref['wf_figures']['sort']:.4f} dd {ref['wf_figures']['dd']:,.0f} "
          f"({'as recorded' if ref['wf_figures']['as_recorded'] else 'NOT the recorded figures - smoke only'}); legs "
          + ", ".join(f"{f} {ref['trades_wf'][f]} ({ref['rate'][f]:.3f}/row)" for f in LEGS), flush=True)
    print(f"CUSUM reference value k = {K_FRACTION} x mu0/sigma0 = {K_FRACTION} x {ref['mu0'] / ref['sigma0']:.4f} = {ref['k']:.4f} sigma0 units a row "
          f"(drift -k while the book earns mu0, +k at zero edge)", flush=True)
    rng = np.random.default_rng(SEED)
    starts = block_starts(rng, ref["n_rows"], NDRAW)
    t1 = time.time()
    nul = pass_null(ref, starts)
    h1, fa1 = h_search(nul["cmax252"])
    h1_bottom = h_interior(h1, "h1")
    h1b, fa1b = h_search(nul["cmax252_zero"])
    h1b_bottom = h_interior(h1b, "h1b")
    q95, q99, ladder = dd_tables(nul["MDD"])
    lo, hi = count_bands(nul["CUM"])
    t2 = time.time()
    pw = pass_power(ref, starts, h1, h1b, q99)
    t3 = time.time()
    power = {str(a): alarm_summary(f) for a, f in pw["first"].items()}
    h1_252 = (pw["first"][1.0] > 0) & (pw["first"][1.0] <= 252)
    zero = power["0.0"]
    headline = (f"if #463 stopped earning tomorrow, H1 would alarm after a median of {dfmt(zero['median_day'])} trading days "
                f"(90% of such paths within {dfmt(zero['p90_day'])} days; {zero['share']['252']:.1%} alarm within a year, "
                f"{zero['share']['756']:.1%} within three)")
    cal = {"prereg_sha256": PREREG_SHA, "prereg_file_sha256": psha, "records": hashes, "seed": SEED, "ndraw": NDRAW, "block": BLOCK, "chunk": CHUNK,
           "horizons": list(HORIZONS), "wf": {"from": WF0, "to": WF1, "first_row": ref["first"], "last_row": ref["last"], "n_rows": ref["n_rows"],
                                                "figures": ref["wf_figures"], "recorded": list(WF_REF)},
           "mu0": ref["mu0"], "sigma0": ref["sigma0"], "leg_order": ref["fams"],
           "legs": {f: {"trades_wf": ref["trades_wf"][f], "rate_per_row": ref["rate"][f]} for f in LEGS},
           "H1": {"k": ref["k"], "k_fraction": K_FRACTION, "delta": ref["mu0"] / ref["sigma0"], "h1": h1, "h1_at_grid_bottom": h1_bottom,
                  "fa_level": FA_LEVEL, "fa_at_h1_252": float(fa1[np.flatnonzero(H_GRID == h1)[0]]),
                  "fa_grid": [[float(h), float(v)] for h, v in zip(H_GRID, fa1)], "null": power["1.0"]},
           "H1b": {"k": ref["k"], "h1b": h1b, "h1b_at_grid_bottom": h1b_bottom, "fa_level": FA_LEVEL, "fa_at_h1b_252": float(fa1b[np.flatnonzero(H_GRID == h1b)[0]]),
                   "null": alarm_summary(pw["first_zero"]), "report_only": True},
           "H2": {"warn_q": DD_WARN_Q, "alarm_q": DD_ALARM_Q, "q95": q95.tolist(), "q99": q99.tolist(), "ladder_q": LADDER_Q.tolist(),
                  "null_share_alarm_252": float(pw["h2_null"].mean()), "wf_worst_dd": ref["wf_figures"]["dd"], "lb_worst_dd_context": LB_WORST_DD},
           "H3": {"band_q": list(BAND_Q), "boot_lo": {f: lo[:, i].tolist() for i, f in enumerate(LEGS)}, "boot_hi": {f: hi[:, i].tolist() for i, f in enumerate(LEGS)},
                  "report_only": True},
           "joint": {"share_alarm_252": float((h1_252 | pw["h2_null"]).mean()), "h1_only": float(h1_252.mean()), "h2_only": float(pw["h2_null"].mean())},
           "power": {"H1": {str(a): power[str(a)] for a in ALTS}, "H1_null": power["1.0"],
                     "H2": {"scale": SCALE_ALT, "share_alarm_252": float(pw["h2_scale"].mean()), "null_share_alarm_252": float(pw["h2_null"].mean())}},
           "headline": headline, "seconds": {"null_pass": round(t2 - t1, 1), "power_pass": round(t3 - t2, 1), "total": round(time.time() - t0, 1)}}
    save("calibration.json", cal)
    np.savez_compressed(os.path.join(OUT, "null.npz"), starts=starts, cmax252=nul["cmax252"], cmax252_zero=nul["cmax252_zero"],
                        mdd_ladder=ladder, ladder_q=LADDER_Q)
    lines = calibration_lines(cal)
    with open(os.path.join(OUT, "CALIBRATION.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(_ready_path(), "w") as f:
        f.write(json.dumps({"sha256": {n: R11._sha_file(os.path.join(OUT, n)) for n in ("calibration.json", "null.npz")}, "prereg_sha256": PREREG_SHA,
                            "records": hashes, "seed": SEED, "ndraw": NDRAW, "k": ref["k"], "h1": h1, "h1b": h1b}, indent=1, default=R11.js))
    print("\n".join(lines), flush=True)
    return cal


def calibration_lines(c):
    H1, H1b, H2, H3, J, P, w = c["H1"], c["H1b"], c["H2"], c["H3"], c["joint"], c["power"], c["wf"]
    out = [f"BOOK HEALTH r1 - CALIBRATION of #463's monitors on its WF rows {w['from']}..{w['to']} ({w['n_rows']} rows): "
           f"mu0 ${c['mu0']:,.2f}/row, sigma0 ${c['sigma0']:,.2f}/row",
           f"prereg sha256 {c['prereg_sha256']}; records {str(c['records'].get('records_U.npz', ''))[:16]}...; null {c['ndraw']:,} circular block-bootstrap "
           f"draws of {HMAX} rows, block {c['block']}, seed {c['seed']}, chunks of {c['chunk']}",
           f"WF figures on these rows: roc {w['figures']['roc']:.3f} sort {w['figures']['sort']:.4f} worst dd ${w['figures']['dd']:,.0f} "
           f"(recorded {w['recorded'][0]} / {w['recorded'][1]} / ${w['recorded'][2]:,.0f}: {'as recorded' if w['figures']['as_recorded'] else 'NOT matched - smoke only'})",
           "legs (closed trades per WF row): " + ", ".join(f"{f} {c['legs'][f]['rate_per_row']:.3f} ({c['legs'][f]['trades_wf']:,} trades)" for f in LEGS),
           f"H1 DECAY: k = {H1['k_fraction']} x mu0/sigma0 = {H1['k']:.4f} (delta {H1['delta']:.4f}), h1 = {H1['h1']:.2f}"
           + (" (at the grid's bottom)" if H1["h1_at_grid_bottom"] else "")
           + f" (null share alarming within 252 rows {H1['fa_at_h1_252']:.4f} at the {H1['fa_level']} level; "
           f"within 504 {H1['null']['share']['504']:.4f}, within 756 {H1['null']['share']['756']:.4f})",
           f"H1b ZERO (report only): same k {H1b['k']:.4f}, h1b = {H1b['h1b']:.2f}" + (" (at the grid's bottom)" if H1b["h1b_at_grid_bottom"] else "")
           + f" (null share within 252 rows {H1b['fa_at_h1b_252']:.4f}; within 756 {H1b['null']['share']['756']:.4f})",
           "H2 DRAWDOWN: null max drawdown q95 / q99 by length: " + "; ".join(f"{n} rows ${H2['q95'][n - 1]:,.0f} / ${H2['q99'][n - 1]:,.0f}" for n in (21, 63, 126, 252, 504, 756))
           + f"; null share in ALARM at least once within 252 rows {H2['null_share_alarm_252']:.4f}; context: WF worst ${H2['wf_worst_dd']:,.0f}, "
           f"lockbox worst ${H2['lb_worst_dd_context']:,.0f} (printed, never re-read)",
           "H3 FIRING (report only): bootstrap 2.5 / 97.5 % bands of closed trades at 252 rows: "
           + ", ".join(f"{f} [{H3['boot_lo'][f][251]}, {H3['boot_hi'][f][251]}] (Poisson {list(poisson_band(c['legs'][f]['rate_per_row'] * 252))})" for f in LEGS),
           f"JOINT: share of null draws alarming on H1 or H2 within 252 rows {J['share_alarm_252']:.4f} (H1 {J['h1_only']:.4f}, H2 {J['h2_only']:.4f})",
           f"POWER H1 at h1 {H1['h1']:.2f} (forward mean as a multiple of the WF mean mu0 ${c['mu0']:,.2f}/row):",
           f"  {'alt':>5s} {'mean $/row':>11s} {'within 252':>11s} {'within 504':>11s} {'within 756':>11s} {'median day':>11s} {'p90 day':>8s}"]
    for a in ("1.0",) + tuple(str(x) for x in ALTS):
        p = P["H1_null"] if a == "1.0" else P["H1"][a]
        out.append(f"  {a:>5s} {float(a) * c['mu0']:>11,.2f} {p['share']['252']:>11.4f} {p['share']['504']:>11.4f} {p['share']['756']:>11.4f} "
                   f"{dfmt(p['median_day']):>11s} {dfmt(p['p90_day']):>8s}" + ("   (the null: false alarms)" if a == "1.0" else ""))
    out += [f"POWER H2 at dispersion x{P['H2']['scale']}: share of draws in ALARM at least once within 252 rows {P['H2']['share_alarm_252']:.4f} "
            f"(null {P['H2']['null_share_alarm_252']:.4f})",
            f"HEADLINE: {c['headline']}",
            "not claimed: one realised history (the block bootstrap keeps three-week structure, not regimes); the false-alarm rate in a volatility "
            "regime the WF never saw is unknown; a CUSUM tuned for the whole edge vanishing (k = delta / 2) is slower on a half-edge fall (the 0.5 row says how slow)",
            f"wall time: null pass {c['seconds']['null_pass']}s, power pass {c['seconds']['power_pass']}s, total {c['seconds']['total']}s"]
    return [asc(x) for x in out]


# ------------------------------------------------------------------ read: the forward csv against the calibration
def read_forward(path, frm=None, asof=None):
    """The forward csv -> (dates, pnl, {leg: counts} for the count columns present); every refusal lives here."""
    if not os.path.isfile(path):
        raise SystemExit(f"refused: forward csv not found: {path}")
    df = pd.read_csv(path)
    cols = {str(c).strip(): c for c in df.columns}
    for c in ("date", "pnl"):
        if c not in cols:
            raise SystemExit(f"refused: forward csv lacks column '{c}' (expected date, pnl, optional n_ORB n_ENGUQ n_TTM n_NOISE)")
    raw = df[cols["date"]].astype(str).str.strip()
    d = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
    if d.isna().any():
        i = int(np.flatnonzero(d.isna().to_numpy())[0])
        raise SystemExit(f"refused: row {i + 1} date {raw.iloc[i]!r} is not YYYY-MM-DD")
    d = pd.DatetimeIndex(d)
    try:
        frm, wf1 = pd.Timestamp(frm or FORWARD_FROM_DEFAULT), pd.Timestamp(WF1)
        asof = pd.Timestamp(asof) if asof else None
    except (ValueError, TypeError) as ex:
        raise SystemExit(f"refused: bad --from / --asof date ({ex})")
    if frm < pd.Timestamp(FORWARD_FROM_DEFAULT):
        raise SystemExit(f"refused: --from {frm.date()} is earlier than the registered forward start {FORWARD_FROM_DEFAULT} - --from can only move "
                         "the start later (an earlier start could admit lockbox rows)")
    if (d <= wf1).any():
        raise SystemExit(f"refused: row dated {d[d <= wf1][0].date()} is on or before WF1 {WF1} - a backtest row is pretending to be forward")
    if (d < frm).any():
        raise SystemExit(f"refused: row dated {d[d < frm][0].date()} is before the forward start {frm.date()} - a backtest row is pretending to be forward")
    if (d.dayofweek >= 5).any():
        raise SystemExit(f"refused: row dated {d[d.dayofweek >= 5][0].date()} is a weekend day")
    if len(d) > 1 and not (np.diff(d.values.astype('datetime64[D]')).astype(int) > 0).all():
        i = int(np.flatnonzero(~(np.diff(d.values.astype('datetime64[D]')).astype(int) > 0))[0])
        raise SystemExit(f"refused: dates are not strictly increasing at row {i + 2} ({d[i].date()} then {d[i + 1].date()})")
    gaps = pd.bdate_range(d[0], d[-1]).difference(d)                      # one row per weekday, a holiday as a 0 row (the reference's convention)
    if len(gaps):
        g = gaps[0]
        raise SystemExit(f"refused: weekday {g.date()} is missing between {d[d < g][-1].date()} and {d[d > g][0].date()} - the forward record is one row "
                         "per weekday (a holiday is a 0 row), the reference's own row convention, or n runs short of the null's prefix")
    pnl = pd.to_numeric(df[cols["pnl"]], errors="coerce").to_numpy(float)
    if not np.isfinite(pnl).all():
        i = int(np.flatnonzero(~np.isfinite(pnl))[0])
        raise SystemExit(f"refused: row {i + 1} ({d[i].date()}) has no pnl")
    counts = {}
    for f in LEGS:
        for name in COUNT_COLS[f]:
            if name in cols:
                v = pd.to_numeric(df[cols[name]], errors="coerce").to_numpy(float)
                if not np.isfinite(v).all() or (v < 0).any() or (v != np.round(v)).any():
                    raise SystemExit(f"refused: column {name} must hold whole non-negative closed-trade counts on every row")
                counts[f] = v.astype(np.int64)
                break
    if asof is not None:
        keep = np.asarray(d <= asof)
        if not keep.any():
            raise SystemExit(f"refused: no forward row on or before --asof {asof.date()}")
        d, pnl = d[keep], pnl[keep]
        counts = {f: v[keep] for f, v in counts.items()}
    if len(d) == 0:
        raise SystemExit("refused: the forward csv has no rows")
    if len(d) > HMAX:
        raise SystemExit(f"refused: {len(d)} forward rows observed - the registered horizon of {HMAX} rows is spent; a longer record is a new "
                         "registration (r2), not a read through this one")
    return d, pnl, counts


def load_calibration():
    """READY + the sha of every file it recorded + the prereg it was made under -> (calibration dict, the null ladder, READY)."""
    rp = _ready_path()
    if not os.path.exists(rp):
        raise SystemExit(f"refused: READY is missing under {OUT} - run calibrate first")
    with open(rp) as f:
        ready = json.loads(f.read() or "{}")
    shas = ready.get("sha256") or {}
    for name in ("calibration.json", "null.npz"):
        p = os.path.join(OUT, name)
        if name not in shas or not os.path.isfile(p) or R11._sha_file(p) != shas[name]:
            raise SystemExit(f"refused: {name} does not match the sha READY recorded - run calibrate again")
    if ready.get("prereg_sha256") != PREREG_SHA:
        raise SystemExit("refused: the prereg changed after calibration - run calibrate again")
    with open(os.path.join(OUT, "calibration.json")) as f:
        cal = json.load(f)
    z = np.load(os.path.join(OUT, "null.npz"))
    return cal, z["mdd_ladder"], ready


def monitors(cal, ladder, dates, pnl, counts):
    """The three monitors (and H1b) on the observed forward rows; states only, no verdict."""
    n = len(pnl)
    mu0, s0 = cal["mu0"], cal["sigma0"]
    h1, h1b, k = cal["H1"]["h1"], cal["H1b"]["h1b"], cal["H1"]["k"]
    C, C0 = cusum((pnl - mu0) / s0, k), cusum(pnl / s0, k)
    f1, f0 = int(first_cross(C, h1)[0]), int(first_cross(C0, h1b)[0])
    H1 = {"statistic": float(C[-1]), "max": float(C.max()), "threshold": h1, "k": k, "rows": n, "state": "ALARM" if f1 else "OK",
          "first_alarm_row": f1 or None, "first_alarm_date": str(dates[f1 - 1].date()) if f1 else None}
    H1b = {"statistic": float(C0[-1]), "max": float(C0.max()), "threshold": h1b, "k": k, "rows": n, "state": "ALARM" if f0 else "OK",
           "first_alarm_row": f0 or None, "first_alarm_date": str(dates[f0 - 1].date()) if f0 else None, "report_only": True}
    dd = R11.ddpath(pnl)
    depth = float(dd[-1])
    q95, q99 = np.asarray(cal["H2"]["q95"], float), np.asarray(cal["H2"]["q99"], float)
    earlier = np.flatnonzero((dd[:n] > 0) & (dd[:n] >= q99[:n]))
    H2 = {"statistic": depth, "q95": float(q95[n - 1]), "q99": float(q99[n - 1]), "rows": n, "state": h2_state(depth, q95[n - 1], q99[n - 1]),
          "share_deeper_this_length": share_deeper(ladder, n, depth), "share_deeper_252": share_deeper(ladder, 252, depth),
          "alarm_rows_so_far": int(len(earlier)), "first_alarm_date": str(dates[earlier[0]].date()) if len(earlier) else None,
          "context_wf_worst_dd": cal["H2"]["wf_worst_dd"], "context_lb_worst_dd": cal["H2"]["lb_worst_dd_context"]}
    H3 = {}
    for f in LEGS:
        rate = cal["legs"][f]["rate_per_row"]
        lo, hi = int(cal["H3"]["boot_lo"][f][n - 1]), int(cal["H3"]["boot_hi"][f][n - 1])
        row = {"supplied": f in counts, "rows": n, "rate_per_row": rate, "expected": rate * n, "poisson_band": list(poisson_band(rate * n)),
               "bootstrap_band": [lo, hi], "report_only": True}
        if f in counts:
            obs = int(counts[f].sum())
            row.update({"closed_trades": obs, "flag": h3_flag(obs, lo, hi)})
        H3[f] = row
    return {"H1": H1, "H1b": H1b, "H2": H2, "H3": H3}


def health_lines(r):
    H1, H1b, H2, H3 = r["H1"], r["H1b"], r["H2"], r["H3"]
    n = r["rows"]
    out = [f"BOOK HEALTH r1 - #463 forward record through {r['asof']}: H1 DECAY {H1['state']}; H2 DRAWDOWN {H2['state']}; H3 FIRING report only",
           f"rows observed: {n} forward rows {r['first']}..{r['last']}, one row per weekday with a holiday as a 0 row (from {r['from']}; "
           f"registered horizon {HMAX}, {HMAX - n} rows left); "
           f"reference WF {r['wf']['from']}..{r['wf']['to']} ({r['wf']['n_rows']} rows), mu0 ${r['mu0']:,.2f}/row, sigma0 ${r['sigma0']:,.2f}/row",
           f"calibration sha256 {r['calibration_sha256'][:16]}... (READY); prereg sha256 {r['prereg_sha256']}; null {r['ndraw']:,} draws, seed {r['seed']}",
           f"H1 DECAY: CUSUM C_n = {H1['statistic']:.3f} after {n} rows (k {H1['k']:.4f}, threshold h1 {H1['threshold']:.2f}, max so far {H1['max']:.3f}) -> {H1['state']}"
           + (f" (first reached on {H1['first_alarm_date']}, row {H1['first_alarm_row']}) - {MANAGER}" if H1["state"] == "ALARM" else ""),
           f"H1b ZERO (report only): CUSUM against a zero mean C_n = {H1b['statistic']:.3f} (threshold h1b {H1b['threshold']:.2f}, max so far {H1b['max']:.3f}) -> {H1b['state']}"
           + (f" (first reached on {H1b['first_alarm_date']}, row {H1b['first_alarm_row']})" if H1b["state"] == "ALARM" else ""),
           "H1b reading: with the same k, H1b asks whether the book is losing at half its backtest edge or worse",
           f"H2 DRAWDOWN: current depth ${H2['statistic']:,.0f} below the running peak after {n} rows; null max drawdown over {n} rows q95 ${H2['q95']:,.0f}, "
           f"q99 ${H2['q99']:,.0f} -> {H2['state']}" + (f" - {MANAGER}" if H2["state"] == "ALARM" else " (logged)" if H2["state"] == "WARN" else ""),
           f"H2 context: share of backtest paths this length with a deeper drawdown {H2['share_deeper_this_length']:.3f} (over a full 252-row year "
           f"{H2['share_deeper_252']:.3f}); ALARM rows so far {H2['alarm_rows_so_far']}" + (f" (first {H2['first_alarm_date']})" if H2["first_alarm_date"] else "")
           + f"; WF worst ${H2['context_wf_worst_dd']:,.0f}, lockbox worst ${H2['context_lb_worst_dd']:,.0f} (context, never re-read)"]
    for f in LEGS:
        h = H3[f]
        pb, bb = h["poisson_band"], h["bootstrap_band"]
        if h["supplied"]:
            out.append(f"H3 FIRING {f:6s}: {h['closed_trades']} closed trades in {n} rows; WF rate {h['rate_per_row']:.3f}/row -> expected {h['expected']:.1f}; "
                       f"Poisson band [{pb[0]}, {pb[1]}]; bootstrap band [{bb[0]}, {bb[1]}] -> {h['flag']} (report only, never alarms)")
        else:
            out.append(f"H3 FIRING {f:6s}: counts not supplied; WF rate {h['rate_per_row']:.3f}/row -> expected {h['expected']:.1f} in {n} rows; "
                       f"Poisson band [{pb[0]}, {pb[1]}]; bootstrap band [{bb[0]}, {bb[1]}] (report only, never alarms)")
    out.append("reading: an ALARM is " + MANAGER + "; a WARN is logged; every other forward figure belongs to the registered forward reads, not to this file")
    return [asc(x) for x in out]


def read(path, frm=None, asof=None):
    check_prereg()
    cal, ladder, ready = load_calibration()
    dates, pnl, counts = read_forward(path, frm, asof)
    r = monitors(cal, ladder, dates, pnl, counts)
    stamp = str(dates[-1].date())
    r.update({"asof": stamp, "rows": int(len(pnl)), "first": str(dates[0].date()), "last": stamp, "from": str(pd.Timestamp(frm or FORWARD_FROM_DEFAULT).date()),
              "csv": os.path.abspath(path), "csv_sha256": R11._sha_file(path), "wf": {k: cal["wf"][k] for k in ("from", "to", "n_rows")},
              "mu0": cal["mu0"], "sigma0": cal["sigma0"], "ndraw": cal["ndraw"], "seed": cal["seed"], "prereg_sha256": cal["prereg_sha256"],
              "calibration_sha256": ready["sha256"]["calibration.json"], "states": {"H1": r["H1"]["state"], "H2": r["H2"]["state"], "H3": "report only"},
              "supplied_counts": sorted(counts)})
    save(f"health_{stamp}.json", r)
    lines = health_lines(r)
    with open(os.path.join(OUT, f"HEALTH_{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return r


def write_forward_csv(path, dates, pnl, counts=None):
    """A forward csv in the paper lane's layout (date, pnl, n_ORB, n_ENGUQ, n_TTM, n_NOISE); counts may be None or a {leg: array}."""
    names = {"ORB": "n_ORB", "ENGU-Q": "n_ENGUQ", "TTM": "n_TTM", "NOISE": "n_NOISE"}
    legs = [f for f in LEGS if counts and f in counts]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "pnl"] + [names[f] for f in legs])
        for i, (d, v) in enumerate(zip(dates, pnl)):
            w.writerow([str(pd.Timestamp(d).date()), f"{float(v):.2f}"] + [int(counts[f][i]) for f in legs])
    return path


# ------------------------------------------------------------------ smoke: a synthetic book, no r11 records, never a real cache
SMOKE_LEG_NAMES = ("ORB_3_6_C2.py", "ENGUQ_1M_ETH_R2_1_0.py", "TTMSQZ_3_0_ES30SSOF2.py", "NOISE_1_8_CT304H.py")   # named like BOOK463_LEGS
SMOKE_RATES = (0.8, 0.3, 0.4, 1.2)                                                                             # closed trades per row per leg


class _StubBook:
    """The four attributes the reference needs of r11's Book: index, raw (valued-daily $ per row), leg and xrow per trade."""

    def __init__(self, index, raw, leg, xrow):
        self.index, self.raw, self.leg, self.xrow = index, raw, leg, xrow


def smoke_world(seed=7):
    """Weekday rows 2016-03..2025-09 (the WF window inside): daily $ = edge + sigma_day x t(4) noise, sigma_day a persistent log-vol process
    (r11_risk.smoke's idea); per-leg Poisson closed-trade counts on each row. Its numbers mean nothing."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2016-03-01", "2025-09-30")
    n = len(index)
    lv = np.zeros(n)
    for i in range(1, n):
        lv[i] = 0.985 * lv[i - 1] + rng.normal(0.0, 0.12)
    raw = 300.0 + 400.0 * np.exp(lv) * rng.standard_t(4, n)
    legs, xrows = [], []
    for j, r in enumerate(SMOKE_RATES):
        c = rng.poisson(r, n)
        rows = np.repeat(np.arange(n), c)
        legs.append(np.full(len(rows), j, np.int64))
        xrows.append(rows)
    return _StubBook(index, raw, np.concatenate(legs), np.concatenate(xrows)), [{"strategy": s} for s in SMOKE_LEG_NAMES]


def _expect_refusal(fn, why, match=None):
    try:
        fn()
    except SystemExit as ex:
        assert match is None or match in str(ex), f"smoke: {why}: refused for another reason: {ex}"
        return str(ex)
    raise AssertionError(f"smoke: {why}: must refuse")


def smoke(d):
    """No box data: a synthetic Book-like reference (load_records rebound to a stub), OUT = DIR/health, NDRAW 400, the TBD prereg tolerated;
    then calibrate, three forward csvs (at the WF mean; at -1.5 x mu0; with a planted loss streak), the refusals, and h1 / q99 / the count
    band re-done by hand from the saved block starts. Prints SMOKE PASS. Its numbers mean nothing."""
    global OUT, NDRAW, SMOKE_TBD_OK, CHECK_REFS, load_records
    root = os.path.abspath(d)
    assert "smoke" in os.path.basename(root).lower() and not os.path.normcase(root).startswith(os.path.normcase(r"C:\EdgeLog")), \
        "smoke needs its own scratch folder (name contains 'smoke'), never a real cache"
    os.makedirs(root, exist_ok=True)
    saved = (OUT, NDRAW, SMOKE_TBD_OK, CHECK_REFS, load_records)
    t0 = time.time()
    B, meta = smoke_world()
    hashes = {"records_U.npz": "smoke", "records_S.npz": "smoke", "build.json": "smoke"}
    try:
        OUT, NDRAW, CHECK_REFS = os.path.join(root, "health"), 400, False
        load_records = lambda: (B, meta, hashes)
        SMOKE_TBD_OK = False                                   # the TBD prereg refuses calibrate and read outside the smoke tolerance
        _expect_refusal(calibrate, "calibrate with PREREG_SHA TBD", "TBD")
        SMOKE_TBD_OK = True
        probe = os.path.join(root, "prereg_probe.txt")
        with open(probe, "w") as f:
            f.write("probe\r\n")
        for want, ok in (("0" * 64, False), (R11.sha_lf(probe), True)):
            try:
                check_prereg(probe, want)
                assert ok, "smoke: check_prereg must refuse a wrong sha"
            except SystemExit:
                assert not ok, "smoke: check_prereg must pass the right sha"
        cal = calibrate()
        h1 = cal["H1"]["h1"]
        assert h1 is not None and np.isfinite(h1) and h1 in H_GRID, h1
        assert cal["H1"]["fa_at_h1_252"] <= FA_LEVEL, cal["H1"]["fa_at_h1_252"]        # exact: h_search guarantees it
        assert abs(cal["H1"]["k"] - K_FRACTION * cal["mu0"] / cal["sigma0"]) < 1e-12 and cal["H1b"]["k"] == cal["H1"]["k"]
        z0 = cal["power"]["H1"]["0.0"]
        assert z0["share"]["756"] >= 0.5 and z0["median_day"] is not None and np.isfinite(z0["median_day"]), z0   # +k a row at zero edge: it gets there
        assert cal["power"]["H1_null"]["share"]["252"] == cal["H1"]["fa_at_h1_252"], "smoke: the two passes disagree on the same draws"
        assert cal["wf"]["n_rows"] == len(pd.bdate_range(WF0, WF1)) and not cal["wf"]["figures"]["as_recorded"]
        # h1, q99[40] and the ORB band at 40 rows re-done by hand from the saved block starts (R11.ddpath row by row, no shared code path)
        z = np.load(os.path.join(OUT, "null.npz"))
        rows = wf_rows(B)
        x, Cn = np.asarray(B.raw, float)[rows], leg_counts(B, meta, rows)[0]
        idx = expand(z["starts"], len(x))
        assert idx.shape == (NDRAW, HMAX) and (idx[:, 1:BLOCK] == (idx[:, :1] + np.arange(1, BLOCK)) % len(x)).all()
        cm = np.array([cusum((x[i[:252]] - cal["mu0"]) / cal["sigma0"], cal["H1"]["k"]).max() for i in idx])
        assert np.allclose(cm, z["cmax252"])
        fa = [np.mean(cm >= h) for h in H_GRID]
        assert h1 == float(H_GRID[next(k for k, v in enumerate(fa) if v <= FA_LEVEL)])
        md40 = np.array([R11.ddpath(x[i[:40]]).max() for i in idx])
        assert abs(float(np.quantile(md40, DD_ALARM_Q)) - cal["H2"]["q99"][39]) < 1e-6 and abs(float(np.quantile(md40, DD_WARN_Q)) - cal["H2"]["q95"][39]) < 1e-6
        c40 = np.array([Cn[i[:40], 0].sum() for i in idx])
        assert cal["H3"]["boot_lo"]["ORB"][39] == int(np.quantile(c40, BAND_Q[0], method="lower")) and cal["H3"]["boot_hi"]["ORB"][39] == int(np.quantile(c40, BAND_Q[1], method="higher"))
        assert all(a <= b for a, b in zip(cal["H2"]["q99"], cal["H2"]["q99"][1:])) and all(a <= b for a, b in zip(cal["H2"]["q95"], cal["H2"]["q99"]))
        # a forward record at the WF mean: no H1 alarm (seed 1), every H3 count supplied
        mu0, s0 = cal["mu0"], cal["sigma0"]
        r1 = np.random.default_rng(1)
        d120 = pd.bdate_range(FORWARD_FROM_DEFAULT, periods=120)
        pnl = np.round(mu0 + s0 * r1.standard_t(4, 120) / math.sqrt(2.0), 2)          # cents, as the csv carries them
        counts = {f: r1.poisson(cal["legs"][f]["rate_per_row"], 120) for f in LEGS}
        f_null = write_forward_csv(os.path.join(root, "forward_null.csv"), d120, pnl, counts)
        res = read(f_null)
        assert res["H1"]["state"] != "ALARM" and res["rows"] == 120 and all(res["H3"][f]["supplied"] for f in LEGS)
        assert res["H1"]["statistic"] == float(cusum((pnl - mu0) / s0, cal["H1"]["k"])[-1])
        for name in (f"HEALTH_{res['asof']}.txt", f"health_{res['asof']}.json", "CALIBRATION.txt", "calibration.json", "null.npz", "READY"):
            assert os.path.exists(os.path.join(OUT, name)), name
        txt = open(os.path.join(OUT, f"HEALTH_{res['asof']}.txt"), encoding="utf-8").read()
        txt.encode("ascii")
        open(os.path.join(OUT, "CALIBRATION.txt"), encoding="utf-8").read().encode("ascii")
        assert not re.search(r"\b(roc|sortino|net|champion|candidate|verdict|pass|fail|dead|parked)\b", txt, re.I), "smoke: a forward read must print no verdict word"
        res_asof = read(f_null, asof=str(d120[59].date()))
        assert res_asof["rows"] == 60 and res_asof["asof"] == str(d120[59].date())
        # the forward mean shifted to -1.5 x mu0 for 200 rows: H1 ALARM, the line ends with the MANAGER sentence
        d200 = pd.bdate_range(FORWARD_FROM_DEFAULT, periods=200)
        pnl = np.round(-1.5 * mu0 + s0 * r1.standard_t(4, 200) / math.sqrt(2.0), 2)
        f_shift = write_forward_csv(os.path.join(root, "forward_shift.csv"), d200, pnl)
        res = read(f_shift)
        assert res["H1"]["state"] == "ALARM" and res["H1"]["first_alarm_row"] and not res["H3"]["ORB"]["supplied"]
        txt = open(os.path.join(OUT, f"HEALTH_{res['asof']}.txt"), encoding="utf-8").read().splitlines()
        assert any(l.startswith("H1 DECAY") and l.endswith(MANAGER) for l in txt)
        # a planted streak of 3 x sigma0 daily losses: H2 WARN or ALARM
        d72 = pd.bdate_range(FORWARD_FROM_DEFAULT, periods=72)
        pnl = np.round(np.concatenate([mu0 + s0 * r1.standard_t(4, 60) / math.sqrt(2.0), np.full(12, -3.0 * s0)]), 2)
        f_streak = write_forward_csv(os.path.join(root, "forward_streak.csv"), d72, pnl)
        res = read(f_streak)
        assert res["H2"]["state"] in ("WARN", "ALARM"), res["H2"]
        assert abs(res["H2"]["statistic"] - float(R11.ddpath(pnl)[-1])) < 1e-9
        # refusals: a backtest row; before --from; 757 rows; a NaN pnl; READY missing
        f_bad = write_forward_csv(os.path.join(root, "forward_bad.csv"), pd.bdate_range(WF1, periods=3), [1.0, 2.0, 3.0])
        _expect_refusal(lambda: read(f_bad), "a row on WF1", "pretending to be forward")
        f_early = write_forward_csv(os.path.join(root, "forward_early.csv"), pd.bdate_range("2026-09-21", periods=3), [1.0, 2.0, 3.0])
        _expect_refusal(lambda: read(f_early), "a row before --from", "pretending to be forward")
        _expect_refusal(lambda: read(f_early, frm="2026-09-21"), "--from before the registered start", "earlier than the registered")
        f_gap = write_forward_csv(os.path.join(root, "forward_gap.csv"), [pd.Timestamp("2026-09-28"), pd.Timestamp("2026-09-29"), pd.Timestamp("2026-10-01")], [1.0, 2.0, 3.0])
        _expect_refusal(lambda: read(f_gap), "a missing weekday", "weekday 2026-09-30 is missing")
        f_long = write_forward_csv(os.path.join(root, "forward_long.csv"), pd.bdate_range(FORWARD_FROM_DEFAULT, periods=HMAX + 1), np.full(HMAX + 1, mu0))
        _expect_refusal(lambda: read(f_long), "757 rows", "horizon")
        with open(os.path.join(root, "forward_nan.csv"), "w") as f:
            f.write("date,pnl\n2026-09-28,10\n2026-09-29,\n")
        _expect_refusal(lambda: read(os.path.join(root, "forward_nan.csv")), "a NaN pnl", "no pnl")
        os.rename(_ready_path(), _ready_path() + ".bak")
        _expect_refusal(lambda: read(f_null), "READY missing", "READY")
        os.rename(_ready_path() + ".bak", _ready_path())
        print(f"SMOKE PASS (k {cal['H1']['k']:.4f}, h1 {h1:.2f}, h1b {cal['H1b']['h1b']:.2f}, {cal['headline']} - meaningless; {time.time() - t0:.0f}s)", flush=True)
    finally:
        OUT, NDRAW, SMOKE_TBD_OK, CHECK_REFS, load_records = saved


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if cmd == ["calibrate"]:
        calibrate()
    elif len(cmd) >= 2 and cmd[0] == "read":
        opts, rest = {}, cmd[2:]
        while rest:
            if rest[0] in ("--from", "--asof") and len(rest) >= 2:
                opts[rest[0][2:]] = rest[1]
                rest = rest[2:]
            else:
                print("usage: r18_health.py read CSV [--from YYYY-MM-DD] [--asof YYYY-MM-DD]")
                sys.exit(2)
        read(cmd[1], frm=opts.get("from"), asof=opts.get("asof"))
    elif len(cmd) == 2 and cmd[0] == "smoke":
        smoke(cmd[1])
    else:
        print("usage: r18_health.py calibrate | read CSV [--from D] [--asof D] | smoke DIR")
        sys.exit(2)
