# Round 12 (2026-10-04): MDL r1 - the MINIMUM DETECTABLE LEG map for BOOK #463: what must a new leg (or a re-sizing of one) look like before it can lift
# #463 past the bars every lane is judged on - and so which hunts cannot matter, whatever they find?
# Pre-registered: tools/rocfrontier/PREREG_MDL_R1.txt (FINAL after the MANAGER review of 2026-10-04: n = 25 greyed, the re-sizing row, the docs/ one-pager;
# written before any synthetic leg was drawn). PREREG_SHA below is its LF-normalised sha256 and `run` refuses on a mismatch. Every rule, threshold and window
# is that file (+ the lane's brief); where both are silent the choice is marked CHOICE. Reuses r11_risk.py (import r11_risk as R11): the rule-U book records,
# R11.stats / underwater / unified, the WF / LB windows and the published reference numbers.
#   python r12_mdl.py selftest      offline unit checks of the generator and the measures on synthetic data (no files needed); ends with 'selftest ok'
#   python r12_mdl.py smoke DIR     the whole pipeline on a SYNTHETIC book (the sum of four random walks with drift, fixed seed) with a small grid and few
#                                   draws; writes to DIR (its name must contain 'smoke'); skips the book-reproduction check and leave-one-out; its numbers
#                                   mean nothing
#   python r12_mdl.py run           the real map: PREREG_SHA gate, then #463 from r11_risk.py's cache (build.json + records_U.npz), refused unless it
#                                   reproduces WF 93.81 / 3.816 and LB 155.54 / 4.150; then leave-one-out, the re-sizing row and the 1,120-cell map -> OUT
# Results go to OUT (outside git): cells.csv, draws.npz, map_<n>_<tails>_<vol>_<rhoout>.csv, thresholds.csv, seat_rule.json, leave_one_out.json (run only),
# resizing.json, meta.json, MAP.txt (the machine summary; the plain-words one-pager in docs/ is written from these files). Nothing here commits, pushes,
# queues a job or writes anywhere else.
import itertools, json, math, os, sys, time
import numpy as np, pandas as pd
import r11_risk as R11

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("EDGELOG_ROCFRONTIER_MDL", r"C:\EdgeLog\_anatomy_cache\rocfrontier\mdl_r1")
PREREG = os.path.join(HERE, "PREREG_MDL_R1.txt")
PREREG_SHA = "f0ffa10ca78a92fbbc0fc1d000c91f237f88977e052fd7a6ebaa1b2d7c0e0467"   # the FINAL prereg + pre-data addendum 1, LF-normalised (R11.sha_lf)
SEED, M_DRAWS = 20261004, 200
AXES = ("s", "rho_dd", "rho_out", "n", "tails", "vol")                 # the cell index = the position in itertools.product over these axes, in this order
GRID = {"s": (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0), "rho_dd": (-0.6, -0.3, 0.0, 0.3, 0.6), "rho_out": ("zero", "same"), "n": (25, 100, 250, 1000),
        "tails": ("normal", "t3"), "vol": ("const", "clustered")}       # 7 x 5 x 2 x 4 x 2 x 2 = 1,120 cells; rho_out 'same' = rho_dd
SMOKE_GRID = {"s": (0.5, 3.0), "rho_dd": (-0.6, 0.6), "rho_out": ("zero", "same"), "n": (25, 100, 250), "tails": ("normal", "t3"), "vol": ("const", "clustered")}
SMOKE_M, SMOKE_MIN_BIN = 20, 3                                         # smoke: few draws, so a bin needs only 3 draws (not MIN_BIN) to show a threshold
CS = (0.5, 1.0, 2.0)                                                   # a leg's size c x its unit, chosen by WF book ROC, frozen (ties -> the smaller c)
DELTAS = (0.25, 0.5, 1.0)                                              # the re-sizing row: a leg at 1 + delta, i.e. delta x its daily P&L added
BASE_WF_ROC, BAR_WF_SORT = 93.81, 3.816                                # #463's published WF numbers (= R11.P2_REF['unified']['WF'])
BAR_WF_ROC = 1.05 * BASE_WF_ROC                                        # the WF bar: +5% on the book's own ROC (= 98.5)
BAR_LB_ROC, BAR_LB_SORT = 155.54, 4.150                                # the LB bar: the book's own published LB numbers (= R11.P2_REF['unified']['LB'])
UNIT_VOL_DIV = 3.0                                                     # unit yearly volatility = the book's WF yearly volatility / 3
DD_DIV = 3.0                                                           # a qualifying episode is at least 1/3 as deep as the stretch's deepest
MIN_DD_DAYS, MIN_DD_WEEKS = 3, 3                                       # DD week = >= 3 DD days; rho_dd needs >= 3 DD weeks
G_WINDOW = 20                                                          # the clustered-volatility window (rows)
STRETCH_ID = {"WF": 0, "LB": 1}                                        # CHOICE: the third entry of each cell's RNG seed
WINDOWS = {"WF": (R11.WF0, R11.PRE_END), "LB": (R11.LB0, R11.LB1)}
ROC_EDGES = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 60.0, 80.0, 120.0, math.inf)     # standalone WF ROC @ $30k bins (+ a '<0' bin below)
RHO_EDGES = (-1.0, -0.45, -0.15, 0.15, 0.45, 1.0)                      # realised WF rho_dd bins
LEVELS, MIN_BIN = (0.5, 0.8), 30                                       # thresholds: P(pass) >= 50% / 80%, with >= 30 draws in the bin
GREY_BELOW = 50                                                        # CHOICE: greyed = n < 50 trades a year (< 50 sealed-year trades); only n = 25 in the grid
ROC_LABELS = ["<0"] + [f"{lo:g}-{hi:g}" for lo, hi in zip(ROC_EDGES[:-2], ROC_EDGES[1:-1])] + [f"{ROC_EDGES[-2]:g}+"]
ROC_LO = [-math.inf] + list(ROC_EDGES[:-1])
RHO_LABELS = [f"{lo:g}..{hi:g}" for lo, hi in zip(RHO_EDGES[:-1], RHO_EDGES[1:])]
DRAW_KEYS = ("roc_alone_wf", "sort_alone_wf", "ann_alone_wf", "mdd_alone_wf", "roc_alone_lb", "sort_alone_lb", "rho_wf", "rho_lb", "do_wf", "do_lb", "cstar",
             "roc_wf", "sort_wf", "roc_lb", "sort_lb", "d_roc_wf", "pass_wf", "pass_lb")
MED_KEYS = ("roc_alone_wf", "sort_alone_wf", "ann_alone_wf", "mdd_alone_wf", "rho_wf", "rho_lb", "do_wf", "do_lb", "d_roc_wf", "cstar")
SYN_SD, SYN_SHARE = (600.0, 500.0, 400.0, 500.0), (0.4, 0.3, 0.2, 0.1)   # smoke / tests: the four synthetic legs' daily sd (book ~1,000) and drift shares


# ------------------------------------------------------------------ io and the prereg gate
def _clean(o):
    """JSON-safe (CHOICE: strict JSON, readable by the web app and the docs tools): non-finite floats -> null, arrays -> lists."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (float, np.floating)) and not math.isfinite(o):
        return None
    return o


def save(out, name, obj):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, name), "w") as f:
        f.write(json.dumps(_clean(obj), indent=1, default=R11.js))


def write_text(path, lines):
    with open(path, "w", encoding="ascii") as f:                          # ASCII on purpose (the console and the box are cp1252)
        f.write(("\n".join(lines) + "\n").encode("ascii", "backslashreplace").decode("ascii"))


def check_prereg(path=None, want=None):
    path, want = path or PREREG, want or PREREG_SHA
    got = R11.sha_lf(path)
    if want == "TBD":
        raise SystemExit(f"refused: PREREG_SHA is 'TBD' - the prereg is not registered yet (the file hashes to {got})")
    if got != want:
        raise SystemExit(f"refused: {os.path.basename(path)} sha256 {got} is not the registered {want} - the plan changed after it was registered")


# ------------------------------------------------------------------ measures: vectorised twins of r11_risk.stats / underwater
def vmeas(Y, years):
    """Row-wise R11.stats of Y (draws x rows): net, yearly net (net / years), max drawdown (peak starts at 0), ROC @ $30k = 30 x yearly net / max
    drawdown and Sortino = mean / RMS(min(x, 0)) x sqrt(252); NaN exactly where R11.stats gives NaN."""
    Y = np.atleast_2d(np.asarray(Y, float))
    c = np.cumsum(Y, axis=1)
    mdd = (np.maximum.accumulate(np.maximum(c, 0.0), axis=1) - c).max(axis=1)      # the running peak of {0, c} = R11.ddpath
    dn = np.sqrt(np.mean(np.minimum(Y, 0.0) ** 2, axis=1))
    ann = c[:, -1] / years
    with np.errstate(divide="ignore", invalid="ignore"):
        roc = np.where(mdd > 0, 30.0 * ann / mdd, np.nan)
        sort = np.where(dn > 0, Y.mean(axis=1) / dn * math.sqrt(252.0), np.nan)
    return {"net": c[:, -1], "ann": ann, "mdd": mdd, "roc": roc, "sort": sort}


def vstats(Y, years):
    m = vmeas(Y, years)
    return m["roc"], m["sort"]


def pstats(x, dates):
    """One series' numbers in dollars and in ROC / Sortino (R11.stats), for the json files."""
    s = R11.stats(x, dates)
    return {"roc": s["roc"], "sort": s["sort"], "net": s["net"], "net_per_year": s["net"] / s["years"], "max_dd": s["max_dd"], "years": s["years"]}


def qualifying(episodes, T):
    """R11.underwater episodes (deepest first) -> the DD-day mask (rows i0 .. it of every episode at least 1/3 as deep as the deepest) and those episodes."""
    mask, keep = np.zeros(T, bool), []
    for e in episodes:
        if e["depth"] >= episodes[0]["depth"] / DD_DIV:
            mask[e["i0"]:e["it"] + 1] = True
            keep.append(e)
    return mask, keep


def week_ids(dates):
    """ISO (year, week) block number of every row; rows are in date order, so a week is one contiguous block (a year boundary can split a calendar week, never
    an ISO week)."""
    iso = pd.DatetimeIndex(dates).isocalendar()
    key = iso["year"].to_numpy("int64") * 100 + iso["week"].to_numpy("int64")
    return np.cumsum(np.concatenate([[True], key[1:] != key[:-1]])) - 1


def dd_week_rows(dates, dd):
    """The rows of every DD week (an ISO week with >= 3 of its index rows in the DD-day mask), in order, and each week's first position inside those rows."""
    wid = week_ids(dates)
    ndd = np.bincount(wid, weights=dd.astype(float))
    rows = np.flatnonzero(ndd[wid] >= MIN_DD_DAYS)
    w = wid[rows]
    starts = np.flatnonzero(np.concatenate([[True], w[1:] != w[:-1]])) if len(rows) else np.zeros(0, np.int64)
    return rows, starts


def regime_z(x, dd):
    """PREREG ADDENDUM 1 (2026-10-04, pre-data): z_t = (the book's P&L - its mean over the WHOLE stretch) / the std of its regime (DD days / other days).
    Centring on the stretch mean keeps the book's drawdown-day level in z (DD days sit below it), so rho_dd > 0 makes a leg LOSE while the book falls and
    rho_dd < 0 makes it EARN - the original within-regime centring removed that level and left DO flat across rho_dd. Scaling by the regime's own std keeps the
    daily correlation of a leg with z inside each regime exactly rho_r."""
    z = np.zeros(len(x))
    m0 = float(np.mean(x)) if len(x) else 0.0
    for m in (dd, ~dd):
        if m.sum() >= 2 and x[m].std() > 0:                               # CHOICE: population std (ddof 0); a regime with < 2 rows or no spread gets z = 0
            z[m] = (x[m] - m0) / x[m].std()
    return z


def trail_std(x):
    """The book's trailing 20-row std shifted one row (rows t-20 .. t-1; pandas ddof 1, as r11's R5); NaN until 20 rows exist."""
    return pd.Series(np.asarray(x, float)).shift(1).rolling(G_WINDOW, min_periods=G_WINDOW).std().to_numpy()      # CHOICE: sample std (pandas ddof 1), full 20-row window


def norm_g(gs):
    """The clustered-volatility path of one stretch: the trailing std / its mean over the stretch, NaN -> 1 (all 1 if the mean is unusable)."""
    m = float(np.nanmean(gs)) if np.isfinite(gs).any() else float("nan")
    if not (math.isfinite(m) and m > 0):
        return np.ones(len(gs))
    g = gs / m
    return np.where(np.isfinite(g), g, 1.0)


class Stretch:
    """The book on one stretch (WF or LB): its rows, drawdown episodes (R11.underwater, peak starting at 0 at the stretch start), the DD days of the
    qualifying episodes, the DD weeks, z and the two volatility paths. g_all = the whole book's trailing std (None -> clustered = constant); `dd` overrides the
    DD-day mask (tests only)."""

    def __init__(self, x_all, dates_all, g_all, lo, hi, dd=None):
        k = np.flatnonzero(np.asarray((dates_all >= lo) & (dates_all <= hi)))
        self.rows, self.T = k, len(k)
        self.x, self.dates = np.asarray(x_all, float)[k], dates_all[k]
        assert self.T >= 2 and self.dates.is_monotonic_increasing and self.dates.is_unique, "a stretch needs >= 2 rows in date order"
        self.stats = R11.stats(self.x, self.dates)
        self.years, self.net = self.stats["years"], self.stats["net"]
        self.episodes = R11.underwater(self.x, self.dates)
        self.dd, self.qual = qualifying(self.episodes, self.T)
        if dd is not None:
            self.dd = np.asarray(dd, bool)
        self.z = regime_z(self.x, self.dd)
        self.wk_rows, self.wk_starts = dd_week_rows(self.dates, self.dd)
        self.n_dd_weeks, self.n_dd_days = len(self.wk_starts), int(self.dd.sum())
        self.xw = np.add.reduceat(self.x[self.wk_rows], self.wk_starts) if self.n_dd_weeks else np.zeros(0)    # the book's weekly sums over the DD weeks
        self.dd_f = self.dd.astype(float)
        self.dd_loss = -float(self.x[self.dd].sum())                      # the book's loss over the DD days (> 0 whenever there is a qualifying episode)
        gs = np.full(self.T, np.nan) if g_all is None else np.asarray(g_all, float)[k]    # CHOICE: the trailing std comes from the WHOLE book, sliced to the stretch
        self.g = {"const": np.ones(self.T), "clustered": norm_g(gs)}


def stretch_info(S):
    return {"rows": S.T, "years": S.years, "net": S.net, "net_per_year": S.net / S.years, "roc": S.stats["roc"], "sort": S.stats["sort"],
            "deepest_depth": S.episodes[0]["depth"] if S.episodes else 0.0, "qualifying_episodes": len(S.qual), "dd_days": S.n_dd_days, "dd_weeks": S.n_dd_weeks}


def describe(name, S):
    i = stretch_info(S)
    return (f"{name}: {i['rows']} rows, {i['years']:.2f} yr, ROC {i['roc']:.2f} Sortino {i['sort']:.3f}, net ${i['net']:,.0f}, deepest drawdown ${i['deepest_depth']:,.0f}, "
            f"{i['qualifying_episodes']} qualifying episodes, {i['dd_days']} DD days, {i['dd_weeks']} DD weeks")


def window_coupling(S, V):
    """How the generator couples a leg to the book's deepest drawdown window (the L_win of the seat rule). z is standardised over ALL the stretch's DD days, so its
    sum Z over ONE window is not 0: a leg with rho_dd > 0 gains inside the window when Z > 0 and loses when Z < 0, whatever its drift. For a leg that trades every day
    at unit volatility V the correlation moves its expected P&L in the window by V / sqrt(252) x Z per unit of rho_dd, and its drift earns s x V x days / 252."""
    if not S.episodes:
        return None
    e = S.episodes[0]
    z = S.z[e["i0"]:e["it"] + 1]
    W = len(z)
    # addendum 1: a leg with rho_out = rho_dd = rho has mu re-centred by -sigma rho mean(z) over the stretch, so one unit of rho moves its expected P&L inside the
    # window by sigma (sum(z) - W mean(z)); with rho_out = 0 only the DD days enter the re-centring: sigma (sum(z) - W mean(z x dd))
    net_same = float(z.sum()) - W * float(np.mean(S.z))
    net_zero = float(z.sum()) - W * float(np.mean(S.z * S.dd_f))
    return {"window_days": W, "z_sum": float(z.sum()), "z_mean": float(z.mean()), "z_net_same": net_same, "z_net_zero": net_zero,
            "usd_per_unit_rho_daily_leg": V / math.sqrt(252.0) * net_same, "usd_per_unit_rho_daily_leg_zero": V / math.sqrt(252.0) * net_zero,
            "usd_drift_at_s1": V * W / 252.0, "window_depth": e["depth"],
            "z_sum_clustered": float((S.g["clustered"][e["i0"]:e["it"] + 1] * z).sum())}      # the clustered-volatility legs scale the correlation term by g_t


def coupling_line(name, c):
    if c is None:
        return f"{name} generator coupling: no drawdown on this stretch"
    gl = "GAINS" if c["usd_per_unit_rho_daily_leg"] > 0 else "LOSES"
    return (f"{name} generator coupling: deepest window {c['window_days']} days, sum of z over it {c['z_sum']:+.2f} (mean {c['z_mean']:+.3f} a day) -> for a daily leg at unit size "
            f"rho moves its P&L there by ${c['usd_per_unit_rho_daily_leg'] * 0.1:+,.0f} per +0.1 (rho_out = rho_dd; ${c['usd_per_unit_rho_daily_leg_zero'] * 0.1:+,.0f} with rho_out = 0) - "
            f"a positively correlated leg {gl} there; its drift at s = 1 earns ${c['usd_drift_at_s1']:,.0f} of the ${c['window_depth']:,.0f} depth")


def unit_vol(x_wf):
    """Unit yearly volatility V = the WF book's yearly volatility / 3 (used for BOTH stretches)."""
    return float(np.std(x_wf)) * math.sqrt(252.0) / UNIT_VOL_DIV           # CHOICE: population std (ddof 0) of the WF book's daily P&L


def realised(Y, S):
    """Realised rho_dd and DO of every row of Y against the stretch's book. rho_dd = Pearson correlation of the weekly sums (CHOICE: every row of the ISO week
    inside the stretch, not only its DD days) of the leg and of the book over the stretch's DD weeks; NaN under 3 DD weeks or when either side has no spread.
    DO = the leg's P&L over the DD days / the book's loss over them (NaN without a loss)."""
    Y = np.atleast_2d(np.asarray(Y, float))
    rho = np.full(len(Y), np.nan)
    if S.n_dd_weeks >= MIN_DD_WEEKS:
        w0 = np.add.reduceat(Y[:, S.wk_rows], S.wk_starts, axis=1)       # CHOICE: a weekly sum = every index row of the ISO week inside the stretch (the stretch's edge cuts a week)
        w = w0 - w0.mean(axis=1, keepdims=True)
        b = S.xw - S.xw.mean()
        sw, sb = (w * w).sum(axis=1), float(b @ b)
        ok = (sw > 1e-18 * (w0 * w0).sum(axis=1)) & (sb > 1e-18 * float(S.xw @ S.xw))    # CHOICE: 'no spread' = variance < 1e-18 of the sum of squares
        rho[ok] = np.clip((w[ok] @ b) / np.sqrt(sw[ok] * sb), -1.0, 1.0)
    do = (Y @ S.dd_f) / S.dd_loss if S.dd_loss > 0 else np.full(len(Y), np.nan)      # CHOICE: DO is NaN when the book has no loss over the DD days (no qualifying episode)
    return rho, do


# ------------------------------------------------------------------ the synthetic leg generator
def draw_e(rng, shape, tails):
    """Standard draws with unit variance: normal, or Student-t(3) / sqrt(3) (the variance of t(3) is 3)."""
    return rng.standard_t(3.0, size=shape) / math.sqrt(3.0) if tails == "t3" else rng.standard_normal(shape)


def gen_leg(z, dd, g, V, s, n, rho_dd, rho_out, tails, M, rng):
    """M synthetic legs over one stretch (prereg SYNTHETIC LEGS + addendum 1): active on a day with probability p = min(1, n / 252); then P&L = mu + sigma g_t
    (rho_r z_t + sqrt(1 - rho_r^2) e_t), rho_r = rho_dd on DD days and rho_out elsewhere; 0 on off days. sigma = V / sqrt(252 p); mu = s V / (252 p) - sigma x
    the stretch mean of g_t rho_r z_t (addendum 1: z keeps the drawdown level, so mu is re-centred to keep the leg's average on target)."""
    T = len(z)
    p = min(1.0, n / 252.0)
    sigma, mu = V / math.sqrt(252.0 * p), s * V / (252.0 * p)
    rho_r = np.where(dd, rho_dd, rho_out)
    mu -= sigma * float(np.mean(g * rho_r * z))                           # PREREG ADDENDUM 1: re-centred - the stretch-average P&L of an active day stays s V / (252 p)
    active = rng.random((M, T)) < p                                       # CHOICE: the active flags are drawn first, then e
    leg = draw_e(rng, (M, T), tails)
    leg *= np.sqrt(1.0 - rho_r ** 2)
    leg += rho_r * z
    leg *= sigma * g
    leg += mu
    leg *= active
    return leg


# ------------------------------------------------------------------ one cell: the draws, the book add, the realised measures
def pick_c(roc3):
    """Index into CS of the c with the highest WF ROC; a tie -> the smaller c (argmax takes the first); a NaN ROC never wins (all NaN -> the smallest c)."""
    return np.where(np.isnan(roc3), -np.inf, roc3).argmax(axis=0)         # CHOICE: a NaN ROC (no drawdown) never wins; argmax = the first max = the smaller c on a tie (CS ascending)


def eval_cell(SW, SL, V, cell, idx, M):
    """One grid cell: M synthetic legs on WF and on LB (same parameters, separate RNG streams [SEED, cell, stretch]), the book add at c in CS, c* frozen on
    the WF ROC, the realised measures of the unit-size leg (c = 1)."""
    s, rho_dd, rmode, n, tails, vol = cell
    rho_out = 0.0 if rmode == "zero" else rho_dd
    leg = {}
    for name, S in (("WF", SW), ("LB", SL)):
        leg[name] = gen_leg(S.z, S.dd, S.g[vol], V, s, n, rho_dd, rho_out, tails, M, np.random.default_rng([SEED, idx, STRETCH_ID[name]]))
    ev = {}
    aw, al = vmeas(leg["WF"], SW.years), vmeas(leg["LB"], SL.years)
    ev["roc_alone_wf"], ev["sort_alone_wf"], ev["ann_alone_wf"], ev["mdd_alone_wf"] = aw["roc"], aw["sort"], aw["ann"], aw["mdd"]
    ev["roc_alone_lb"], ev["sort_alone_lb"] = al["roc"], al["sort"]
    ev["rho_wf"], ev["do_wf"] = realised(leg["WF"], SW)
    ev["rho_lb"], ev["do_lb"] = realised(leg["LB"], SL)
    roc3, sort3 = np.empty((len(CS), M)), np.empty((len(CS), M))
    for i, c in enumerate(CS):
        roc3[i], sort3[i] = vstats(SW.x + c * leg["WF"], SW.years)
    ci, cols = pick_c(roc3), np.arange(M)
    ev["cstar"] = np.asarray(CS)[ci]
    ev["roc_wf"], ev["sort_wf"] = roc3[ci, cols], sort3[ci, cols]
    ev["roc_lb"], ev["sort_lb"] = vstats(SL.x + ev["cstar"][:, None] * leg["LB"], SL.years)
    ev["d_roc_wf"] = ev["roc_wf"] - BASE_WF_ROC
    ev["pass_wf"] = (ev["roc_wf"] >= BAR_WF_ROC) & (ev["sort_wf"] >= BAR_WF_SORT)       # CHOICE: a NaN never passes
    ev["pass_lb"] = (ev["roc_lb"] >= BAR_LB_ROC) & (ev["sort_lb"] >= BAR_LB_SORT)
    return ev


def cells_of(grid):
    return list(itertools.product(*(grid[a] for a in AXES)))


def nanmed(a):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if len(a) else float("nan")


def cell_row(idx, cell, ev):
    row = {"cell": idx, **dict(zip(AXES, cell)), "greyed": bool(cell[AXES.index("n")] < GREY_BELOW)}
    row.update({"p_pass_wf": float(ev["pass_wf"].mean()), "p_pass_wf_lb": float((ev["pass_wf"] & ev["pass_lb"]).mean()), "p_pass_lb": float(ev["pass_lb"].mean())})
    row.update({"med_" + k: nanmed(ev[k]) for k in MED_KEYS})
    return row


# ------------------------------------------------------------------ the maps: realised standalone ROC x realised rho_dd
def roc_bin(v):
    """Bin index of a standalone WF ROC: 0 = '<0', then [0,5) [5,10) ... [120,inf) = 1 .. 10."""
    v = np.asarray(v, float)
    return np.where(v < ROC_EDGES[0], 0, 1 + np.searchsorted(ROC_EDGES[1:-1], v, side="right"))     # CHOICE: bins are [lo, hi): an edge value belongs to the bin above


def rho_bin(v):
    """Bin index of a realised rho_dd: [-1,-0.45) [-0.45,-0.15) [-0.15,0.15) [0.15,0.45) [0.45,1] = 0 .. 4 (+1 itself is in the last bin)."""
    return np.searchsorted(RHO_EDGES[1:-1], np.asarray(v, float), side="right")     # CHOICE: [lo, hi) like the ROC bins, the last bin closed so +1 is in it


def map_key(cell):
    return (cell[AXES.index("n")], cell[AXES.index("tails")], cell[AXES.index("vol")], cell[AXES.index("rho_out")])


def map_name(key):
    return f"map_{key[0]}_{key[1]}_{key[2]}_{key[3]}"


def bin_tables(roc, rho, ann, mdd, pw, pb, pl):
    """Draws -> (ROC bins x rho_dd bins) counts: all, WF passes, WF-and-LB passes, LB passes, and the median unit-size yearly net / max drawdown in dollars of the
    draws in each bin. Draws with a NaN ROC or rho_dd are not binned (counted in 'unbinned')."""
    ok = np.isfinite(roc) & np.isfinite(rho)                              # CHOICE: the map bins on the WF values; a draw with no WF ROC or no WF rho_dd is not binned
    R, Q = len(ROC_LABELS), len(RHO_LABELS)
    flat = roc_bin(roc[ok]) * Q + rho_bin(rho[ok])
    cnt = lambda w: np.bincount(flat, weights=w, minlength=R * Q).reshape(R, Q)
    tab = {"n": cnt(None), "wf": cnt(pw[ok].astype(float)), "both": cnt(pb[ok].astype(float)), "lb": cnt(pl[ok].astype(float)), "unbinned": int((~ok).sum())}
    for name, v in (("med_ann", ann[ok]), ("med_mdd", mdd[ok])):
        med = np.full(R * Q, np.nan)
        for b in np.unique(flat):
            med[b] = nanmed(v[flat == b])
        tab[name] = med.reshape(R, Q)
    return tab


def map_frame(tab, key):
    rows = []
    for r, rl in enumerate(ROC_LABELS):
        for q, ql in enumerate(RHO_LABELS):
            n = tab["n"][r, q]
            p = lambda k: float(tab[k][r, q] / n) if n > 0 else float("nan")
            rows.append({"roc_bin": rl, "rho_dd_bin": ql, "draws": int(n), "pass_wf": int(tab["wf"][r, q]), "p_pass_wf": p("wf"), "pass_wf_lb": int(tab["both"][r, q]),
                         "p_pass_wf_lb": p("both"), "pass_lb": int(tab["lb"][r, q]), "p_pass_lb": p("lb"), "med_leg_net_usd": float(tab["med_ann"][r, q]),
                         "med_leg_maxdd_usd": float(tab["med_mdd"][r, q]), "greyed": bool(key[0] < GREY_BELOW)})
    return pd.DataFrame(rows)


def threshold_rows(key, tab, min_bin):
    """Per rho_dd bin: the smallest ROC bin whose P(pass) >= 50% and >= 80% (with >= min_bin draws in the bin), for the WF bars and for the WF AND LB bars, with the
    dollars: the bin's lower edge x $1,000 = a year at a $30k drawdown of the leg's own, and the bin's median unit-size yearly net and max drawdown."""
    n_, tails, vol, rm = key
    out = []
    for q, ql in enumerate(RHO_LABELS):
        # 'none' with bins_with_enough_draws = 0 means too few draws in the band to say, not that no leg gets there (n = 100 rarely realises a rho_dd beyond +-0.45)
        row = {"map": map_name(key), "n": n_, "tails": tails, "vol": vol, "rho_out": rm, "rho_dd_bin": ql, "greyed": bool(n_ < GREY_BELOW),
               "rho_bin_draws": int(tab["n"][:, q].sum()), "bins_with_enough_draws": int((tab["n"][:, q] >= min_bin).sum())}
        for tag in ("wf", "both"):                                        # CHOICE: the WF-AND-LB reading is written beside the WF one (prereg: 'same for the LB')
            for lev in LEVELS:
                pre = f"{tag}_p{round(lev * 100)}"
                hit = [r for r in range(len(ROC_LABELS)) if tab["n"][r, q] >= min_bin and tab[tag][r, q] / tab["n"][r, q] >= lev]
                b = hit[0] if hit else None                               # CHOICE: the first (smallest) qualifying bin; higher bins need not qualify too
                row[pre + "_bin"] = ROC_LABELS[b] if hit else "none"
                row[pre + "_roc_lo"] = ROC_LO[b] if hit else float("nan")
                row[pre + "_usd_at_30k"] = ROC_LO[b] * 1000.0 if hit else float("nan")     # ROC 1 point = $1,000 a year at a $30k drawdown of the leg's own
                row[pre + "_draws"] = int(tab["n"][b, q]) if hit else 0
                row[pre + "_p"] = float(tab[tag][b, q] / tab["n"][b, q]) if hit else float("nan")
                row[pre + "_leg_net_usd"] = float(tab["med_ann"][b, q]) if hit else float("nan")
                row[pre + "_leg_maxdd_usd"] = float(tab["med_mdd"][b, q]) if hit else float("nan")
        out.append(row)
    return out


def write_maps(dr, cells, out, min_bin):
    keys = [map_key(c) for c in cells]
    thr, unbinned = [], 0
    for key in dict.fromkeys(keys):
        sel = np.isin(dr["cell"], [i for i, k in enumerate(keys) if k == key])
        both = dr["pass_wf"][sel] & dr["pass_lb"][sel]
        tab = bin_tables(dr["roc_alone_wf"][sel], dr["rho_wf"][sel], dr["ann_alone_wf"][sel], dr["mdd_alone_wf"][sel], dr["pass_wf"][sel], both, dr["pass_lb"][sel])
        map_frame(tab, key).to_csv(os.path.join(out, map_name(key) + ".csv"), index=False)
        thr += threshold_rows(key, tab, min_bin)
        unbinned += tab["unbinned"]
    pd.DataFrame(thr).to_csv(os.path.join(out, "thresholds.csv"), index=False)
    return thr, unbinned


# ------------------------------------------------------------------ reference points: seat rule, leave-one-out, the re-sizing row
def seat_rule(stretches):
    """The first-order seat rule on the book's own deepest drawdown window of each stretch. d/dw of 30 x (A_B + w A_L) / (DD_B - w L_win) at w = 0 is > 0 iff
    A_L / A_B > -L_win / DD_B, so a leg must earn A_B x 1000 / DD_B a year for every $1,000 it loses inside the window (the deepest stays the deepest)."""
    out = {"rule": "a leg helps the book's ROC @ $30k at the margin iff A_L / A_B > -L_win / DD_B  (A = yearly net, L_win = the leg's P&L from the day after the peak "
                   "through the trough, DD_B = the book's depth of that drawdown)",
           "in_dollars": "the leg must earn more than A_B x 1000 / DD_B dollars a year for every $1,000 it loses inside the window (dollars_a_year_per_1000_lost); a "
                         "leg that gains inside the window needs less, and may even lose money",
           "in_percent": "the leg's yearly net as a share of the book's yearly net must exceed the share of the book's drawdown depth that the leg loses inside the "
                         "window (losing 10% of DD_B needs more than 10% of A_B a year). Because the stretch's max drawdown IS this window, A_B x 1000 / DD_B = "
                         "book ROC @ $30k x 1000 / 30 - the dollar figure restates the book's ROC; the window dates and depth are the new information"}
    for name, S in stretches.items():
        A_B = S.net / S.years
        rec = {"from": str(S.dates[0].date()), "to": str(S.dates[-1].date()), "years": S.years, "book_net": S.net, "yearly_net": A_B, "book_roc": S.stats["roc"],
               "book_sort": S.stats["sort"], "book_max_dd": S.stats["max_dd"], "qualifying_episodes": len(S.qual), "dd_days": S.n_dd_days, "dd_weeks": S.n_dd_weeks}
        if S.episodes:
            e = S.episodes[0]
            rec.update({"peak": e["peak"], "first_day": str(S.dates[e["i0"]].date()), "trough": e["trough"], "window_days": e["it"] - e["i0"] + 1, "depth": e["depth"],
                        "dollars_a_year_per_1000_lost": A_B * 1000.0 / e["depth"], "yearly_net_per_dollar_lost": A_B / e["depth"]})
        else:
            rec.update({"peak": None, "first_day": None, "trough": None, "window_days": 0, "depth": 0.0, "dollars_a_year_per_1000_lost": None, "yearly_net_per_dollar_lost": None})
        out[name] = rec
    return out


def leg_series(B, nlegs):
    return [np.asarray(B.Am_leg[k].T @ B.ones, float) for k in range(nlegs)]      # leg k's daily P&L (the book's own: closed + valued daily)


def reproduce(B, ref=None, tol=None):
    """Refuse (SystemExit) unless the book's WF and LB ROC and Sortino equal the published ones within R11.P2_TOL (the same test as r11's P2)."""
    ref, tol = ref or R11.P2_REF["unified"], tol or R11.P2_TOL
    got = {"WF": R11.unified(B, B.raw, R11.WF0, R11.PRE_END), "LB": R11.unified(B, B.raw, R11.LB0, R11.LB1)}
    for s in ("WF", "LB"):
        if not (abs(got[s]["roc"] - ref[s][0]) < tol[0] and abs(got[s]["sort"] - ref[s][1]) < tol[1]):
            raise SystemExit(f"refused: the book does not reproduce the published {s} numbers - got ROC {got[s]['roc']:.4f} / Sortino {got[s]['sort']:.5f}, "
                             f"published {ref[s][0]} / {ref[s][1]} (tolerance {tol[0]} / {tol[1]})")
    return got


def leave_one_out(B, legs_meta, windows=None):
    """Reference points on the map (reported, never judged): each of the book's legs added back to the other legs - ROC / Sortino and dollars of rest and of
    rest + leg, the leg's own standalone numbers, and its rho_dd and DO measured against REST's own drawdown weeks (rest = the book without the leg)."""
    windows = windows or WINDOWS
    dates, raw = B.index, np.asarray(B.raw, float)
    legs = leg_series(B, len(legs_meta))
    out = {"note": "rest = the book without leg k; rest_plus_leg = the whole book again; rho_dd / DO are the leg's, measured against REST's own qualifying drawdown "
                   "episodes and weeks; trades_a_year = the leg's trades closed inside the stretch / years (where it sits on the n axis of the map)", "book": {}, "legs": []}
    for name, (lo, hi) in windows.items():
        S = Stretch(raw, dates, None, lo, hi)
        out["book"][name] = pstats(raw[S.rows], S.dates)
    for k, meta in enumerate(legs_meta):
        rest = raw - legs[k]
        rec = {"k": k, "strategy": meta.get("strategy"), "instrument": meta.get("instrument")}
        for name, (lo, hi) in windows.items():
            S = Stretch(rest, dates, None, lo, hi)
            r = S.rows
            a, b, c = pstats(rest[r], S.dates), pstats(rest[r] + legs[k][r], S.dates), pstats(legs[k][r], S.dates)
            rho, do = realised(legs[k][r][None, :], S)
            inside = np.zeros(len(dates), bool)
            inside[r] = True
            rec[name] = {"rest": a, "rest_plus_leg": b, "gain_roc": b["roc"] - a["roc"], "gain_sort": b["sort"] - a["sort"],
                         "gain_net_per_year": b["net_per_year"] - a["net_per_year"], "gain_max_dd": b["max_dd"] - a["max_dd"], "leg_alone": c,
                         "rho_dd_vs_rest": float(rho[0]), "do_vs_rest": float(do[0]),
                         "leg_pnl_in_rest_dd_days": float(legs[k][r][S.dd].sum()), "rest_loss_in_dd_days": S.dd_loss,
                         "rest_deepest_drawdown": S.episodes[0]["depth"] if S.episodes else 0.0, "rest_dd_days": S.n_dd_days, "rest_dd_weeks": S.n_dd_weeks,
                         "trades_a_year": float(((B.leg == k) & inside[B.xrow]).sum() / S.years)}
        out["legs"].append(rec)
    return out


def resizing(B, legs_meta, windows=None, bars=None):
    """RE-SIZING ROW: for each of the book's legs k and delta in DELTAS the difference series d = delta x leg k's daily P&L (the leg at 1 + delta minus the leg at 1)
    added to the book at c = 1 (the delta IS the size - no c search): WF and LB ROC @ $30k and Sortino against the bars, the dollars, d's own standalone numbers
    and its rho_dd and DO against the BOOK's own DD weeks. `bars` = {"WF": (roc, sortino), "LB": (...)}, default the prereg's (tests may override)."""
    windows = windows or WINDOWS
    dates, raw = B.index, np.asarray(B.raw, float)
    legs = leg_series(B, len(legs_meta))
    bars = bars or {"WF": (BAR_WF_ROC, BAR_WF_SORT), "LB": (BAR_LB_ROC, BAR_LB_SORT)}
    S = {name: Stretch(raw, dates, None, lo, hi) for name, (lo, hi) in windows.items()}
    out = {"note": "d = delta x leg k's daily P&L added to the book at c = 1; clears = book + d meets the bar (ROC and Sortino); rho_dd / DO of d against the BOOK's own "
                   "DD weeks and episodes; d_alone is d on its own (its ROC does not depend on delta)",
           "deltas": list(DELTAS), "bars": {k: {"roc": v[0], "sort": v[1]} for k, v in bars.items()},
           "book": {n_: pstats(raw[St.rows], St.dates) for n_, St in S.items()}, "rows": []}
    for k, meta in enumerate(legs_meta):
        for delta in DELTAS:
            d = delta * legs[k]
            rec = {"k": k, "strategy": meta.get("strategy"), "instrument": meta.get("instrument"), "delta": delta, "size_after": 1.0 + delta}
            for name, St in S.items():
                r = St.rows
                base = out["book"][name]
                bd, alone = pstats(raw[r] + d[r], St.dates), pstats(d[r], St.dates)
                rho, do = realised(d[r][None, :], St)
                rec[name] = {"book_plus_d": bd, "bar": out["bars"][name], "clears": bool(bd["roc"] >= bars[name][0] and bd["sort"] >= bars[name][1]),
                             "gain_roc": bd["roc"] - base["roc"], "gain_sort": bd["sort"] - base["sort"], "gain_net_per_year": bd["net_per_year"] - base["net_per_year"],
                             "gain_max_dd": bd["max_dd"] - base["max_dd"], "d_alone": alone, "rho_dd": float(rho[0]), "do": float(do[0]),
                             "d_pnl_in_dd_days": float(d[r][St.dd].sum()), "book_loss_in_dd_days": St.dd_loss}
            rec["clears_both"] = bool(rec["WF"]["clears"] and rec["LB"]["clears"])
            out["rows"].append(rec)
    return out


# ------------------------------------------------------------------ MAP.txt: the machine summary (the docs/ one-pager is written from the files)
def phrase(lab, lo, few=False):
    if lab == "none":
        return "too few draws in the band to say" if few else "no leg on the grid"
    return "any ROC" if lo == -math.inf else f"ROC >= {lo:g}"


def resize_lines(rs):
    b = rs["book"]
    L = ["Re-sizing reference (the yardstick a tilt has to beat): a leg at 1 + delta = delta x its daily P&L added to the book at c = 1, no size search; same bars as above",
         f"  the book alone: WF ROC {b['WF']['roc']:.2f} / Sortino {b['WF']['sort']:.3f}, LB ROC {b['LB']['roc']:.2f} / Sortino {b['LB']['sort']:.3f}"]
    for r in rs["rows"]:
        w, l = r["WF"], r["LB"]
        L.append(f"  {r['strategy']} +{r['delta']:g}: WF ROC {w['book_plus_d']['roc']:.2f} / Sortino {w['book_plus_d']['sort']:.3f} -> {'clears' if w['clears'] else 'fails'}; "
                 f"LB ROC {l['book_plus_d']['roc']:.2f} / Sortino {l['book_plus_d']['sort']:.3f} -> {'clears' if l['clears'] else 'fails'}; rho_dd WF {w['rho_dd']:+.2f} LB "
                 f"{l['rho_dd']:+.2f}, DO WF {w['do']:+.2f} LB {l['do']:+.2f}; d alone ${w['d_alone']['net_per_year']:,.0f} a year, max drawdown ${w['d_alone']['max_dd']:,.0f}, "
                 f"ROC {w['d_alone']['roc']:.1f}")
    return L


def map_text(thr, seat, extras, ncells, M, label, min_bin=MIN_BIN):
    L = [f"MDL r1 - the minimum detectable leg map for BOOK #463 ({label}; r12_mdl.py; prereg sha256 {PREREG_SHA}; {ncells} cells x {M} draws, seed {SEED})",
         "A planning map, not a test. Synthetic legs are added to the book's daily P&L at 0.5x / 1x / 2x of a unit (yearly volatility = 1/3 of the book's WF volatility), "
         "the size frozen on the WF ROC.",
         "Standalone ROC = the leg's own 30 x yearly net / max drawdown, so ROC 20 = $20,000 a year at a $30k drawdown of the leg's own (1 point = $1,000 a year). "
         "rho_dd = how the leg moves with the book in the book's drawdown weeks.",
         "Each line below is one kind of leg. For each realised rho_dd band: the smallest standalone-ROC bin where the leg clears the WF bars (book ROC >= "
         f"{BAR_WF_ROC:.1f} and Sortino >= {BAR_WF_SORT}) in 50% / 80% of the draws; 'no leg on the grid' = no bin gets there; a bin needs >= {min_bin} draws.",
         f"The same read with the WF AND LB bars (LB: ROC >= {BAR_LB_ROC}, Sortino >= {BAR_LB_SORT}) is in thresholds.csv (the both_* columns); the LB is one year, so it "
         "sits beside the WF map, never instead of it.", ""]
    by = {}
    for r in thr:
        by.setdefault((r["n"], r["tails"], r["vol"], r["rho_out"]), []).append(r)
    words = {"normal": "normal tails", "t3": "fat (t3) tails", "const": "constant volatility", "clustered": "volatility clustered with the book's",
             "zero": "flat outside the drawdown weeks", "same": "moves with the book the same way all the time"}
    for nn in (100, 250):
        for tails, vol, rm in itertools.product(GRID["tails"], GRID["vol"], GRID["rho_out"]):
            rows = by.get((nn, tails, vol, rm))
            if rows is not None:
                L.append(f"n={nn} a year, {words[tails]}, {words[vol]}, leg {words[rm]}: " + " | ".join(
                    f"rho_dd {r['rho_dd_bin']}: 50% {phrase(r['wf_p50_bin'], r['wf_p50_roc_lo'], r['bins_with_enough_draws'] == 0)}, "
                    f"80% {phrase(r['wf_p80_bin'], r['wf_p80_roc_lo'], r['bins_with_enough_draws'] == 0)}" for r in rows))
    use = [r for r in thr if not r["greyed"] and r["bins_with_enough_draws"] > 0]
    few = sum(1 for r in thr if not r["greyed"] and r["bins_with_enough_draws"] == 0)
    if use:
        c = lambda col: sum(r[col] == "none" for r in use)
        L += ["", f"What no leg on the grid can do (n >= {GREY_BELOW} only; {len(use)} map x rho_dd-band combinations with a bin of >= {min_bin} draws, {few} more bands too sparse "
                  f"to say): no bin reaches 50% in {c('wf_p50_bin')} and 80% in {c('wf_p80_bin')} on the WF bars; with the WF AND LB bars: 50% in {c('both_p50_bin')}, "
                  f"80% in {c('both_p80_bin')} (thresholds.csv has them all)."]
    if any(r["greyed"] for r in thr):
        L.append(f"n = 25 trades a year is computed and written (greyed=True in cells.csv, the map files and thresholds.csv) but no sentence here uses it: a leg that trades "
                 f"25 times a year makes under {GREY_BELOW} sealed-year trades, and every Stage B needs {GREY_BELOW}.")
    L.append("")
    for name in ("WF", "LB"):
        s = seat[name]
        if s["dollars_a_year_per_1000_lost"] is None:
            L.append(f"Seat rule {name}: the book has no drawdown on this stretch.")
        else:
            L.append(f"Seat rule {name} (first order): the book's deepest drawdown {s['peak']} -> {s['trough']} cost ${s['depth']:,.0f} against a yearly net of "
                     f"${s['yearly_net']:,.0f}, so a leg helps at the margin only if it earns more than ${s['dollars_a_year_per_1000_lost']:,.0f} a year "
                     f"for every $1,000 it loses inside that window (a leg that gains inside the window needs less).")
    if extras.get("coupling"):
        L += ["", "Read the rho_dd axis with this (prereg addendum 1: z keeps the book's drawdown level, so a positively correlated leg loses while the book falls):"]
        L += [coupling_line(name, extras["coupling"][name]) for name in ("WF", "LB")]
    if extras.get("resizing"):
        L += [""] + resize_lines(extras["resizing"])
    if extras.get("refs"):
        L += [""] + ref_lines(extras["refs"])
    return L


# ------------------------------------------------------------------ reference points (prereg OUTPUTS: reported, never judged) - series built by r12_refs.py
REF_WF_ONLY = {"NQBRD_070"}                     # dead at Stage A with its lockbox SEALED: only its walk-forward exists and only WF is measured


def reference_points(B, refs_dir=None):
    """Each series in refs_dir (date, pnl; r12_refs.py) added to the book exactly as a synthetic leg is: c in CS chosen by WF book ROC (ties -> the smaller c),
    frozen for the LB; plus its standalone numbers and its rho_dd / DO against the book's own drawdown weeks. Seat swaps are difference series (r12_refs.py)."""
    refs_dir = refs_dir or os.path.join(OUT, "refs")
    if not os.path.isdir(refs_dir):
        return None
    dates, raw = B.index, np.asarray(B.raw, float)
    S = {name: Stretch(raw, dates, None, lo, hi) for name, (lo, hi) in WINDOWS.items()}
    meta = {}
    mp = os.path.join(refs_dir, "refs_meta.json")
    if os.path.exists(mp):
        with open(mp) as f:
            meta = json.load(f).get("meta", {})
    out = {"note": "a reference leg added to #463 at c x its own size, c in (0.5, 1, 2) chosen by WF book ROC then frozen; rho_dd / DO against #463's own DD weeks; "
                   "seat swaps (ORB #239 / #257, ENGU-Q S1 / S2) are DIFFERENCE series = the shadow book minus #463 at c = 1", "rows": []}
    for fn in sorted(os.listdir(refs_dir)):
        if not fn.endswith(".csv") or fn.startswith("leg_"):
            continue
        name = fn[:-4]
        df = pd.read_csv(os.path.join(refs_dir, fn))
        ser = pd.Series(df["pnl"].to_numpy(float), index=pd.to_datetime(df["date"])).groupby(level=0).sum()
        y = ser.reindex(dates).fillna(0.0).to_numpy(float)
        off = float(ser[~ser.index.isin(dates)].abs().sum())            # P&L on a day the book index does not carry (should be 0: the index is every business day)
        stretches = ("WF",) if name in REF_WF_ONLY else ("WF", "LB")
        rec = {"name": name, "meta": meta.get(name), "pnl_off_index": off, "stretches": list(stretches)}
        roc3 = []
        for c in CS:
            r = S["WF"].rows
            roc3.append(pstats(raw[r] + c * y[r], S["WF"].dates)["roc"])
        cstar = CS[int(pick_c(np.asarray(roc3, float)))]                  # the same size rule as the synthetic legs (shape (3,): argmax over the c axis)
        rec["cstar"] = cstar
        for nm in stretches:
            St = S[nm]
            r = St.rows
            bd, alone, base = pstats(raw[r] + cstar * y[r], St.dates), pstats(y[r], St.dates), pstats(raw[r], St.dates)
            rho, do = realised(y[r][None, :], St)
            bar = (BAR_WF_ROC, BAR_WF_SORT) if nm == "WF" else (BAR_LB_ROC, BAR_LB_SORT)
            rec[nm] = {"book_plus_leg": bd, "book": base, "clears": bool(bd["roc"] >= bar[0] and bd["sort"] >= bar[1]), "gain_roc": bd["roc"] - base["roc"],
                       "gain_sort": bd["sort"] - base["sort"], "leg_alone": alone, "rho_dd": float(rho[0]), "do": float(do[0]),
                       "leg_pnl_in_dd_days": float(y[r][St.dd].sum()), "book_loss_in_dd_days": St.dd_loss}
        out["rows"].append(rec)
    return out


def ref_lines(rf):
    L = ["Reference points (reported, never judged; r12_refs.py series added to #463 like a synthetic leg, size c frozen on the WF ROC):"]
    for r in rf["rows"]:
        w = r["WF"]
        t = (f"  {r['name']} (c = {r['cstar']:g}): alone ${w['leg_alone']['net_per_year']:,.0f} a year, max drawdown ${w['leg_alone']['max_dd']:,.0f}, ROC "
             f"{w['leg_alone']['roc']:.1f}; rho_dd WF {w['rho_dd']:+.2f}, DO WF {w['do']:+.2f}; book WF ROC {w['book_plus_leg']['roc']:.2f} / Sortino "
             f"{w['book_plus_leg']['sort']:.3f} -> {'clears' if w['clears'] else 'fails'}")
        if "LB" in r:
            l = r["LB"]
            t += (f"; LB ROC {l['book_plus_leg']['roc']:.2f} / Sortino {l['book_plus_leg']['sort']:.3f} -> {'clears' if l['clears'] else 'fails'}, rho_dd LB "
                  f"{l['rho_dd']:+.2f}, DO LB {l['do']:+.2f}")
        else:
            t += "; LB not read (sealed)"
        L.append(t)
    return L


# ------------------------------------------------------------------ the shared pipeline (run + smoke)
def build_stretches(x, dates):
    x = np.asarray(x, float)
    g_all = trail_std(x)
    SW, SL = (Stretch(x, dates, g_all, *WINDOWS[name]) for name in ("WF", "LB"))
    return SW, SL, unit_vol(SW.x)


def pipeline(x, dates, grid, M, out, min_bin=MIN_BIN, every=10, label="#463", extras=None):
    """cells.csv, draws.npz, the maps, thresholds.csv, seat_rule.json, meta.json and MAP.txt for the book x on `dates`; one cell at a time (bounded memory)."""
    t0 = time.time()
    os.makedirs(out, exist_ok=True)
    SW, SL, V = build_stretches(x, dates)
    cells = cells_of(grid)
    print(describe("WF", SW), flush=True)
    print(describe("LB", SL), flush=True)
    print(f"unit yearly volatility V = ${V:,.0f} (1/3 of the WF book's); {len(cells)} cells x {M} draws, seed {SEED}", flush=True)
    coupling = {"WF": window_coupling(SW, V), "LB": window_coupling(SL, V)}
    print(coupling_line("WF", coupling["WF"]), flush=True)
    print(coupling_line("LB", coupling["LB"]), flush=True)
    rows, acc = [], {k: [] for k in ("cell",) + DRAW_KEYS}
    for idx, cell in enumerate(cells):
        ev = eval_cell(SW, SL, V, cell, idx, M)
        rows.append(cell_row(idx, cell, ev))
        acc["cell"].append(np.full(M, idx, np.int32))
        for k in DRAW_KEYS:
            acc[k].append(ev[k])
        if (idx + 1) % every == 0 or idx + 1 == len(cells):
            el = time.time() - t0
            print(f"  cell {idx + 1}/{len(cells)}  {el:.0f}s  eta {el / (idx + 1) * (len(cells) - idx - 1):.0f}s  mean P(pass_wf) so far "
                  f"{np.mean([r['p_pass_wf'] for r in rows]):.3f}", flush=True)
    dr = {k: np.concatenate(v) for k, v in acc.items()}
    pd.DataFrame(rows).to_csv(os.path.join(out, "cells.csv"), index=False)
    np.savez_compressed(os.path.join(out, "draws.npz"), **dr)
    thr, unbinned = write_maps(dr, cells, out, min_bin)
    seat = seat_rule({"WF": SW, "LB": SL})
    save(out, "seat_rule.json", seat)
    extras = {**(extras or {}), "coupling": coupling}
    write_text(os.path.join(out, "MAP.txt"), map_text(thr, seat, extras, len(cells), M, label, min_bin))
    save(out, "meta.json", {"harness": "r12_mdl.py", "book": label, "prereg_sha256": PREREG_SHA, "seed": SEED, "draws_per_cell": M, "cells": len(cells), "grid": grid,
                            "min_bin": min_bin, "bars": {"WF": [BAR_WF_ROC, BAR_WF_SORT], "LB": [BAR_LB_ROC, BAR_LB_SORT]}, "unit_vol": V, "cs": CS,
                            "stretches": {"WF": stretch_info(SW), "LB": stretch_info(SL)}, "generator_coupling": coupling, "draws_not_binned": unbinned,
                            "reproduction": extras.get("reproduction"),
                            "seconds": time.time() - t0})
    print(f"pipeline done in {time.time() - t0:.0f}s; mean P(pass_wf) {np.mean([r['p_pass_wf'] for r in rows]):.3f}, WF and LB {np.mean([r['p_pass_wf_lb'] for r in rows]):.3f}; "
          f"{unbinned} of {len(dr['cell'])} draws not binned (NaN ROC or rho_dd)", flush=True)
    return {"thr": thr, "seat": seat, "cells": rows, "dr": dr, "unbinned": unbinned}


# ------------------------------------------------------------------ run: the real map
def run():
    check_prereg()
    legs_meta = R11.load_json("build.json")["legs"]
    B = R11.load_book("U", legs_meta)
    got = reproduce(B)
    print("book reproduces the published numbers: " + ", ".join(f"{s} ROC {got[s]['roc']:.3f} Sortino {got[s]['sort']:.4f}" for s in ("WF", "LB")), flush=True)
    save(OUT, "leave_one_out.json", leave_one_out(B, legs_meta))
    rs = resizing(B, legs_meta)
    save(OUT, "resizing.json", rs)
    rf = reference_points(B)
    if rf is not None:
        save(OUT, "refs.json", rf)
    pipeline(B.raw, B.index, GRID, M_DRAWS, OUT, extras={"resizing": rs, "reproduction": got, "refs": rf})


# ------------------------------------------------------------------ synthetic books (smoke and selftest only - no file, no real data)
def synth_legs(dates, seed=463):
    """Four synthetic legs = random walks with drift; the common drift is bisected so the WF book's ROC @ $30k is ~#463's 93.8 (the numbers still mean nothing)."""
    rng = np.random.default_rng(seed)
    noise = [rng.normal(0.0, sd, len(dates)) for sd in SYN_SD]
    w = np.asarray((dates >= R11.WF0) & (dates <= R11.PRE_END))
    yrs = (dates[w][-1] - dates[w][0]).days / 365.25
    base = np.sum(noise, axis=0)[w]
    lo, hi = 0.0, 4000.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if vstats(base + mid, yrs)[0][0] < BASE_WF_ROC else (lo, mid)       # NaN (no drawdown) -> too high
    return [nz + 0.5 * (lo + hi) * sh for nz, sh in zip(noise, SYN_SHARE)]


class FakeBook:
    """Just the attributes leave_one_out / resizing read from r11_risk.Book, built from synthetic leg series: index, raw, ones, Am_leg (diagonal matrices),
    leg and xrow (one row per synthetic trade)."""

    def __init__(self, legs, dates, seed=5):
        from scipy import sparse
        n = len(dates)
        self.index, self.ones = dates, np.ones(n)
        self.Am_leg = [sparse.diags(np.asarray(l, float)).tocsr() for l in legs]
        self.raw = np.sum(legs, axis=0)
        self.leg = np.concatenate([np.full(40 * (k + 1), k, np.int64) for k in range(len(legs))])
        self.xrow = np.random.default_rng(seed).integers(0, n, len(self.leg))


# ------------------------------------------------------------------ selftest
def hand_book():
    """12 whole ISO weeks from Mon 2020-01-06: weeks 1-3 +10 a day (the peak is row 14), weeks 4-6 -5 / -8 / -3 a day (the trough is row 29), weeks 7-12 +20."""
    dates = pd.bdate_range("2020-01-06", periods=60)
    x = np.concatenate([np.full(15, 10.0), np.repeat([-5.0, -8.0, -3.0], 5), np.full(30, 20.0)])
    return x, dates


def hand_stretch():
    x, dates = hand_book()
    return Stretch(x, dates, None, dates[0], dates[-1])


def naive_rho_do(y, x, dates, dd):
    """An independent implementation of rho_dd / DO (pandas groupby on ISO year-week) for the cross-check."""
    iso = pd.DatetimeIndex(dates).isocalendar()
    df = pd.DataFrame({"y": y, "x": x, "dd": dd, "yr": iso["year"].astype(int).to_numpy(), "wk": iso["week"].astype(int).to_numpy()})
    g = df.groupby(["yr", "wk"])
    ndd = g["dd"].sum()
    w = g[["y", "x"]].sum().loc[ndd[ndd >= MIN_DD_DAYS].index]
    rho = float(np.corrcoef(w["y"], w["x"])[0, 1]) if len(w) >= MIN_DD_WEEKS else float("nan")
    return rho, float(df.loc[df["dd"], "y"].sum() / -df.loc[df["dd"], "x"].sum())


def t_grid():
    cs = cells_of(GRID)
    assert len(cs) == 1120 and cs[0] == (0.25, -0.6, "zero", 25, "normal", "const") and cs[-1] == (3.0, 0.6, "same", 1000, "t3", "clustered")
    assert cs[1] == (0.25, -0.6, "zero", 25, "normal", "clustered") and cs[2][4] == "t3"          # the last axis moves fastest
    assert (BASE_WF_ROC, BAR_WF_SORT) == R11.P2_REF["unified"]["WF"] and (BAR_LB_ROC, BAR_LB_SORT) == R11.P2_REF["unified"]["LB"]
    assert map_key((1.0, 0.3, "same", 100, "t3", "clustered")) == (100, "t3", "clustered", "same") and map_name((100, "t3", "clustered", "same")) == "map_100_t3_clustered_same"
    assert abs(BAR_WF_ROC - 98.5005) < 1e-9 and len(PREREG_SHA) == 64 and STRETCH_ID["WF"] != STRETCH_ID["LB"]
    assert len(ROC_LABELS) == len(ROC_LO) == 11 and len(RHO_LABELS) == 5 and ROC_LABELS[0] == "<0" and ROC_LABELS[-1] == "120+"


def t_generator():
    rng = np.random.default_rng(1)
    T = 200_000
    dd = rng.random(T) < 0.20
    x = rng.standard_normal(T) * np.where(dd, 1500.0, 900.0) + np.where(dd, -40.0, 120.0)
    z, g, V = regime_z(x, dd), np.ones(T), unit_vol(x)
    assert abs(V - float(np.std(x)) * math.sqrt(252.0) / 3.0) < 1e-9                              # unit yearly volatility = the book's / 3
    for m in (dd, ~dd):                                                                           # addendum 1: centred on the stretch mean, scaled by the regime's std
        assert abs(z[m].std() - 1.0) < 1e-9 and abs(z[m].mean() - (x[m].mean() - x.mean()) / x[m].std()) < 1e-9
    assert z[dd].mean() < 0 < z[~dd].mean()                                                       # the drawdown days keep their level below the stretch mean
    gg = np.where(np.arange(T) % 2 == 0, 0.5, 1.5)                                               # a volatility path: the leg's spread follows g_t (n = 250, normal)
    leg = gen_leg(z, dd, gg, V, 1.0, 250, 0.0, 0.0, "normal", 4, rng)
    assert abs(leg[:, 1::2].std() / leg[:, 0::2].std() - 3.0) < 0.06
    for s in (1.0, 2.0):
        for rd, ro in ((-0.6, 0.3), (0.45, -0.15)):
            leg = gen_leg(z, dd, g, V, s, 250, rd, ro, "normal", 4, rng)
            sh = leg.mean(axis=1) / leg.std(axis=1) * math.sqrt(252.0)
            assert abs(sh.mean() / s - 1.0) < 0.10, (s, sh)                                      # realised yearly Sharpe within 10% of s
            assert abs(leg.std(axis=1).mean() * math.sqrt(252.0) / V - 1.0) < 0.03               # the unit yearly volatility is V
            act, zz = leg != 0, np.broadcast_to(z, leg.shape)
            for m, want in ((act & dd, rd), (act & ~dd, ro)):
                r = np.corrcoef(leg[m], zz[m])[0, 1]
                assert abs(r - want) < 0.03, (s, rd, ro, r, want)                                # daily correlation with z on active rows
    leg = gen_leg(z, dd, g, V, 1.0, 25, 0.0, 0.0, "normal", 2, rng)                              # p = 25 / 252: about 10% of the days are active
    assert abs((leg != 0).mean() - 25.0 / 252.0) < 0.003
    leg = gen_leg(z, dd, g, V, 1.0, 251, 0.0, 0.0, "normal", 4, rng)                              # p = 251 / 252, not 1: ~0.4% of the days are off
    assert abs((leg == 0).mean() - 1.0 / 252.0) < 0.0008 and (leg == 0).any()
    assert (gen_leg(z, dd, g, V, 1.0, 1000, 0.0, 0.0, "normal", 1, rng) != 0).all()              # n >= 252 trades every day (p capped at 1)
    # fewer trades a year: the realised Sharpe is s / sqrt(1 + (1 - p) s^2 / (252 p)) (the days off add variance the unit volatility does not count) - checks mu / sigma vs p
    for n in (25, 100):
        for s in (1.0, 2.0):
            p = n / 252.0
            leg = gen_leg(z, dd, g, V, s, n, -0.3, 0.0, "normal", 8, rng)
            sh = (leg.mean(axis=1) / leg.std(axis=1) * math.sqrt(252.0)).mean()
            want = s / math.sqrt(1.0 + (1.0 - p) * s * s / (252.0 * p))
            assert abs(sh / want - 1.0) < 0.05, (n, s, sh, want)


def t_helpers():
    g = norm_g(np.array([np.nan, 2.0, 4.0, 6.0]))
    assert np.allclose(g, [1.0, 0.5, 1.0, 1.5]) and np.allclose(norm_g(np.full(5, np.nan)), 1.0) and np.allclose(norm_g(np.zeros(5)), 1.0)
    x = np.random.default_rng(9).normal(0, 1, 60)
    t = trail_std(x)
    assert np.isnan(t[:20]).all() and abs(t[20] - np.std(x[:20], ddof=1)) < 1e-12 and abs(t[25] - np.std(x[5:25], ddof=1)) < 1e-12      # rows t-20 .. t-1
    dumped = json.dumps(_clean({"a": float("nan"), "b": np.float64("inf"), "c": [1.0, np.nan], "d": np.array([1.0, np.nan]), "e": (np.float64(2.5), True)}), default=R11.js)
    assert "NaN" not in dumped and "Infinity" not in dumped and json.loads(dumped) == {"a": None, "b": None, "c": [1.0, None], "d": [1.0, None], "e": [2.5, True]}
    S = hand_stretch()
    c = window_coupling(S, 252.0)
    assert c["window_days"] == 15 and abs(c["usd_drift_at_s1"] - 15.0) < 1e-12 and abs(c["usd_per_unit_rho_daily_leg"] - 252.0 / math.sqrt(252.0) * (S.z[15:30].sum() - 15 * S.z.mean())) < 1e-9
    assert "GAINS" in coupling_line("WF", c) or "LOSES" in coupling_line("WF", c)
    assert phrase("none", float("nan")) == "no leg on the grid" and phrase("<0", -math.inf) == "any ROC" and phrase("20-30", 20.0) == "ROC >= 20"
    assert phrase("none", float("nan"), True) == "too few draws in the band to say" and phrase("20-30", 20.0, True) == "ROC >= 20"


def t_t3():
    rng = np.random.default_rng(2)
    ss = nn = 0
    for _ in range(4):
        e = draw_e(rng, (2_000_000,), "t3")
        ss, nn = ss + float((e * e).sum()), nn + e.size
    # t(3) has no fourth moment, so a sample variance converges slowly: a fixed seed and 8e6 draws, paired with the robust check (median |t3| = 0.7649)
    assert abs(ss / nn - 1.0) < 0.03, ss / nn
    assert abs(np.median(np.abs(e)) * math.sqrt(3.0) / 0.7649 - 1.0) < 0.01
    assert abs(draw_e(rng, (2_000_000,), "normal").var() - 1.0) < 0.01


def t_offset():
    S = hand_stretch()
    assert S.dd[15:30].all() and not S.dd[:15].any() and not S.dd[30:].any() and S.n_dd_days == 15 and S.n_dd_weeks == 3 and abs(S.dd_loss - 80.0) < 1e-12
    for name, sign, want_do, want_rho in (("minus the book on DD days", -1.0, 1.0, -1.0), ("plus the book on DD days", 1.0, -1.0, 1.0)):
        leg = np.where(S.dd, sign * S.x, 0.0)
        rho, do = realised(leg[None, :], S)
        assert abs(do[0] - want_do) < 1e-12 and abs(rho[0] - want_rho) < 1e-12, (name, rho, do)
    rho, do = realised(np.zeros((1, S.T)), S)
    assert do[0] == 0.0 and np.isnan(rho[0])                                                     # a flat leg has no correlation
    # partial weeks: the weekly sums use every row of the week, so the correlation is no longer exactly -1 - and it must equal the independent implementation
    rng = np.random.default_rng(4)
    dates = pd.bdate_range("2018-01-01", periods=700)
    dd = np.zeros(700, bool)
    for a in rng.integers(0, 680, 25):
        dd[a:a + int(rng.integers(3, 15))] = True
    x = rng.normal(0, 100, 700) + np.where(dd, -30.0, 20.0)
    S = Stretch(x, dates, None, dates[0], dates[-1], dd=dd)
    Y = rng.normal(0, 50, (5, 700)) + 0.3 * x
    rho, do = realised(Y, S)
    for i in range(5):
        r2, d2 = naive_rho_do(Y[i], x, dates, dd)
        assert abs(rho[i] - r2) < 1e-10 and abs(do[i] - d2) < 1e-10, (i, rho[i], r2, do[i], d2)


def t_vstats():
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2018-01-01", periods=700)
    Y = np.vstack([rng.normal(30, 200, 700), rng.normal(-5, 100, 700), rng.standard_t(3, 700) * 80 + 20, np.abs(rng.normal(10, 5, 700)),
                   -np.abs(rng.normal(10, 5, 700)), np.zeros(700)])
    yrs = (dates[-1] - dates[0]).days / 365.25
    m = vmeas(Y, yrs)
    for i in range(len(Y)):
        r = R11.stats(Y[i], dates)
        for a, b in ((m["roc"][i], r["roc"]), (m["sort"][i], r["sort"]), (m["net"][i], r["net"]), (m["mdd"][i], r["max_dd"]), (m["ann"][i], r["net"] / r["years"])):
            assert (np.isnan(a) and np.isnan(b)) or abs(a - b) <= 1e-9 * max(abs(b), 1e-300) or a == b == 0.0, (i, a, b)
    assert np.isnan(m["roc"][3]) and np.isnan(m["sort"][3]) and np.isnan(m["roc"][5])             # no drawdown / no downside -> NaN, as R11.stats
    roc, sort = vstats(Y[:2], yrs)
    assert np.allclose(roc, m["roc"][:2]) and np.allclose(sort, m["sort"][:2])


def t_ctie():
    nan = np.nan
    roc3 = np.array([[5.0, 1, 3, 1, 3, nan, nan], [5.0, 7, 3, 2, 2, 4, nan], [5.0, 7, 1, 3, 1, 4, nan]])
    got = list(pick_c(roc3))
    assert got == [0, 1, 0, 2, 0, 1, 0], got               # all tie -> 0.5; 1 and 2 tie -> 1; 0.5 and 1 tie -> 0.5; clear winners; NaN never wins; all NaN -> 0.5
    assert [CS[i] for i in got] == [0.5, 1.0, 0.5, 2.0, 0.5, 1.0, 0.5]


def t_weeks():
    dates = pd.bdate_range("2020-03-02", periods=15)                      # Mon 2020-03-02 .. Fri 2020-03-20 = three whole ISO weeks
    dd = np.zeros(15, bool)
    dd[[3, 4]] = True                                                     # week 1: Thu + Fri = 2 DD days -> not a DD week
    dd[[5, 6, 7]] = True                                                  # week 2: Mon-Wed = 3 DD days -> a DD week
    dd[10:15] = True                                                      # week 3: all 5 -> a DD week
    rows, starts = dd_week_rows(dates, dd)
    assert list(rows) == list(range(5, 15)) and list(starts) == [0, 5]
    d2 = pd.bdate_range("2020-12-28", periods=10)                         # Mon 2020-12-28 .. Fri 2021-01-01 is ONE ISO week (2020-W53); then 2021-W01
    dd2 = np.zeros(10, bool)
    dd2[[2, 3, 4]] = True                                                 # Wed Dec 30, Thu Dec 31, Fri Jan 1: 3 DD days in one ISO week, 2 + 1 by calendar year
    rows2, starts2 = dd_week_rows(d2, dd2)
    assert list(rows2) == [0, 1, 2, 3, 4] and list(starts2) == [0]
    x = np.array([10, -9, 5, 10, -3, 20, -3.4, 30, -2.9, 30.0])           # episodes (depth): 9, 3, 3.4, 2.9 -> qualifying = depth >= 9 / 3: the first three
    S = Stretch(x, pd.bdate_range("2020-01-06", periods=10), None, pd.Timestamp("2020-01-06"), pd.Timestamp("2020-01-17"))
    assert list(np.flatnonzero(S.dd)) == [1, 4, 6] and len(S.qual) == 3 and abs(S.episodes[0]["depth"] - 9.0) < 1e-12      # DD days = i0 .. trough, not the recovery
    S = hand_stretch()
    assert S.episodes[0]["i0"] == 15 and S.episodes[0]["it"] == 29 and not S.dd[30:33].any()       # the recovery rows 30-32 are underwater but not DD days


def t_bins():
    assert list(roc_bin([-0.01, 0.0, 4.99, 5.0, 119.9, 120.0, 1e9, 30.0])) == [0, 1, 1, 2, 9, 10, 10, 6]
    assert list(rho_bin([-1.0, -0.45, -0.4499, -0.15, 0.0, 0.15, 0.4499, 0.45, 1.0])) == [0, 1, 1, 2, 2, 3, 3, 4, 4]
    R, Q = len(ROC_LABELS), len(RHO_LABELS)
    z = lambda: np.zeros((R, Q))
    tab = {"n": z(), "wf": z(), "both": z(), "lb": z(), "med_ann": z(), "med_mdd": z()}
    tab["n"][3, 2], tab["wf"][3, 2] = 40, 10                              # P 0.25
    tab["n"][4, 2], tab["wf"][4, 2] = 29, 29                              # P 1 but only 29 draws: not counted
    tab["n"][5, 2], tab["wf"][5, 2], tab["med_ann"][5, 2], tab["med_mdd"][5, 2] = 30, 15, 12345.0, 6789.0      # P 0.5 -> the 50% threshold
    tab["n"][6, 2], tab["wf"][6, 2] = 50, 45                              # P 0.9 -> the 80% threshold
    rows = threshold_rows((100, "t3", "clustered", "same"), tab, MIN_BIN)
    r = rows[2]
    assert r["rho_dd_bin"] == "-0.15..0.15" and r["wf_p50_bin"] == "20-30" and r["wf_p50_roc_lo"] == 20.0 and r["wf_p50_usd_at_30k"] == 20000.0 and r["wf_p50_draws"] == 30
    assert r["wf_p50_leg_net_usd"] == 12345.0 and r["wf_p50_leg_maxdd_usd"] == 6789.0 and r["wf_p80_bin"] == "30-40" and r["both_p50_bin"] == "none"
    assert np.isnan(r["both_p80_roc_lo"]) and r["greyed"] is False and all(x["wf_p50_bin"] == "none" for x in rows if x is not r)
    assert r["rho_bin_draws"] == 149 and r["bins_with_enough_draws"] == 3 and all(x["rho_bin_draws"] == 0 and x["bins_with_enough_draws"] == 0 for x in rows if x is not r)
    assert all(x["greyed"] for x in threshold_rows((25, "normal", "const", "zero"), tab, MIN_BIN))
    assert map_frame(tab, (25, "normal", "const", "zero"))["greyed"].all() and not map_frame(tab, (100, "normal", "const", "zero"))["greyed"].any()
    assert len(map_frame(tab, (100, "normal", "const", "zero"))) == R * Q
    nan = np.nan                                                          # draws with a NaN ROC or rho_dd are not binned
    t2 = bin_tables(np.array([10.0, nan, 50.0, 3.0, -2.0]), np.array([0.0, 0.0, nan, 0.9, -0.5]), np.array([1.0, 2, 3, 4, 5]), np.array([9.0, 8, 7, 6, 5]),
                    np.array([True, True, False, True, False]), np.array([True, False, False, False, False]), np.array([True, True, True, True, True]))
    assert t2["unbinned"] == 2 and t2["n"].sum() == 3 and t2["wf"].sum() == 2 and t2["both"].sum() == 1 and t2["lb"].sum() == 3
    assert t2["n"][roc_bin(10.0), rho_bin(0.0)] == 1 and t2["n"][0, rho_bin(-0.5)] == 1
    assert t2["med_ann"][roc_bin(3.0), rho_bin(0.9)] == 4.0 and t2["med_mdd"][roc_bin(10.0), rho_bin(0.0)] == 9.0


def t_text():
    def row(n, q, p50, p80, enough, greyed):
        r = {"map": map_name((n, "normal", "const", "zero")), "n": n, "tails": "normal", "vol": "const", "rho_out": "zero", "rho_dd_bin": RHO_LABELS[q], "greyed": greyed,
             "rho_bin_draws": 100, "bins_with_enough_draws": enough}
        for tag in ("wf", "both"):
            for lev, b in ((50, p50), (80, p80)):
                r[f"{tag}_p{lev}_bin"] = b
                r[f"{tag}_p{lev}_roc_lo"] = ROC_LO[ROC_LABELS.index(b)] if b != "none" else float("nan")
        return r
    thr = [row(25, 0, "none", "none", 3, True), row(25, 1, "none", "none", 3, True), row(100, 0, "10-15", "none", 3, False), row(100, 1, "none", "none", 0, False),
           row(250, 0, "<0", "20-30", 5, False)]
    seat = {"WF": {"dollars_a_year_per_1000_lost": 3127.0, "peak": "2020-01-24", "trough": "2020-02-14", "depth": 14950.0, "yearly_net": 46751.0},
            "LB": {"dollars_a_year_per_1000_lost": None}}
    L = map_text(thr, seat, {"coupling": {"WF": None, "LB": None}}, 5, 200, "TEST", 30)
    txt = "\n".join(L)
    assert not any(l.startswith("n=25 a year") for l in L) and sum(l.startswith("n=100 a year") for l in L) == 1 and sum(l.startswith("n=250 a year") for l in L) == 1
    assert "rho_dd -1..-0.45: 50% ROC >= 10, 80% no leg on the grid" in txt and "rho_dd -0.45..-0.15: 50% too few draws in the band to say" in txt
    assert "rho_dd -1..-0.45: 50% any ROC, 80% ROC >= 20" in txt and "a bin needs >= 30 draws" in txt
    assert ("(n >= 50 only; 2 map x rho_dd-band combinations with a bin of >= 30 draws, 1 more bands too sparse to say): no bin reaches 50% in 0 and 80% in 1 on the WF bars; "
            "with the WF AND LB bars: 50% in 0, 80% in 1") in txt                                           # the two greyed rows are in no count
    assert "n = 25 trades a year is computed and written" in txt and "under 50 sealed-year trades" in txt
    assert "Seat rule WF (first order): the book's deepest drawdown 2020-01-24 -> 2020-02-14 cost $14,950" in txt and "more than $3,127 a year for every $1,000" in txt
    assert "Seat rule LB: the book has no drawdown on this stretch." in txt and "WF generator coupling: no drawdown" in txt and "Re-sizing reference" not in txt
    assert "n = 25 trades a year" not in "\n".join(map_text(thr[2:], seat, {}, 3, 200, "TEST", 30))     # no greyed row -> no grey note


def t_seat():
    S = hand_stretch()
    rec = seat_rule({"WF": S})["WF"]
    A_B = S.net / S.years
    assert rec["peak"] == "2020-01-24" and rec["trough"] == "2020-02-14" and rec["first_day"] == "2020-01-27" and rec["window_days"] == 15 and abs(rec["depth"] - 80.0) < 1e-12
    assert abs(rec["dollars_a_year_per_1000_lost"] - A_B * 1000.0 / 80.0) < 1e-9 and abs(rec["yearly_net"] - A_B) < 1e-12
    # the derivative claim: a leg losing 8 inside the window (a tenth of its depth) must earn more than a tenth of the book's yearly net to lift the ROC
    base = vstats(S.x, S.years)[0][0]
    for mult, lifts in ((1.05, True), (0.95, False)):
        A_L = 0.1 * A_B * mult
        leg = np.full(S.T, (A_L * S.years + 8.0) / 45.0)
        leg[15:30] = -8.0 / 15.0
        assert abs(leg.sum() - A_L * S.years) < 1e-9
        assert (vstats(S.x + 1e-3 * leg, S.years)[0][0] > base) == lifts, mult


def t_reference():
    dates = pd.bdate_range("2010-06-07", "2026-06-30")
    B = FakeBook(synth_legs(dates), dates)
    metas = [{"strategy": f"LEG{k}", "instrument": "NQ"} for k in range(len(B.Am_leg))]
    assert np.allclose(B.raw, np.sum(leg_series(B, 4), axis=0))
    loo = leave_one_out(B, metas)
    for rec in loo["legs"]:
        k = rec["k"]
        leg = leg_series(B, 4)[k]
        for name, (lo, hi) in WINDOWS.items():
            u = R11.unified(B, B.raw, lo, hi)
            w = rec[name]
            assert abs(w["rest_plus_leg"]["roc"] - u["roc"]) < 1e-9 * abs(u["roc"]) and abs(w["rest_plus_leg"]["sort"] - u["sort"]) < 1e-9 * abs(u["sort"])
            assert abs(w["rest"]["net"] + w["leg_alone"]["net"] - u["net"]) < 1e-6 and w["trades_a_year"] > 0 and abs(w["rest_loss_in_dd_days"]) > 0
            k_ = np.asarray((dates >= lo) & (dates <= hi))
            assert abs(w["leg_alone"]["roc"] - R11.stats(leg[k_], dates[k_])["roc"]) < 1e-9 * abs(w["leg_alone"]["roc"])
            assert np.isfinite(w["rho_dd_vs_rest"]) and np.isfinite(w["do_vs_rest"])
            assert abs(w["gain_roc"] - (w["rest_plus_leg"]["roc"] - w["rest"]["roc"])) < 1e-9 and abs(w["gain_sort"] - (w["rest_plus_leg"]["sort"] - w["rest"]["sort"])) < 1e-9
            assert abs(w["gain_net_per_year"] - (w["rest_plus_leg"]["net_per_year"] - w["rest"]["net_per_year"])) < 1e-6
            assert abs(w["gain_max_dd"] - (w["rest_plus_leg"]["max_dd"] - w["rest"]["max_dd"])) < 1e-6
            Sr = Stretch(B.raw - leg, dates, None, lo, hi)                                    # rho_dd / DO against REST's own drawdown weeks, independent implementation
            r2, d2 = naive_rho_do(leg[k_], Sr.x, Sr.dates, Sr.dd)
            assert abs(w["rho_dd_vs_rest"] - r2) < 1e-10 and abs(w["do_vs_rest"] - d2) < 1e-10 and abs(w["leg_pnl_in_rest_dd_days"] - leg[k_][Sr.dd].sum()) < 1e-6
    rs = resizing(B, metas)
    assert len(rs["rows"]) == 4 * len(DELTAS) and rs["deltas"] == list(DELTAS)
    assert rs["bars"] == {"WF": {"roc": BAR_WF_ROC, "sort": BAR_WF_SORT}, "LB": {"roc": BAR_LB_ROC, "sort": BAR_LB_SORT}}
    for r in rs["rows"]:
        leg = leg_series(B, 4)[r["k"]]
        for name, (lo, hi) in WINDOWS.items():
            k_ = np.asarray((dates >= lo) & (dates <= hi))
            st = R11.stats(B.raw[k_] + r["delta"] * leg[k_], dates[k_])
            w = r[name]
            bar = (BAR_WF_ROC, BAR_WF_SORT) if name == "WF" else (BAR_LB_ROC, BAR_LB_SORT)
            assert abs(w["book_plus_d"]["roc"] - st["roc"]) < 1e-9 * abs(st["roc"]) and w["clears"] == bool(st["roc"] >= bar[0] and st["sort"] >= bar[1])
            assert abs(w["d_alone"]["roc"] - R11.stats(leg[k_], dates[k_])["roc"]) < 1e-9 * abs(w["d_alone"]["roc"])      # a re-sizing's own ROC is scale-free
            assert abs(w["gain_roc"] - (st["roc"] - R11.unified(B, B.raw, lo, hi)["roc"])) < 1e-9 and w["bar"] == rs["bars"][name]
            Sb = Stretch(B.raw, dates, None, lo, hi)                                          # rho_dd / DO of d against the BOOK's own drawdown weeks
            r2, d2 = naive_rho_do(r["delta"] * leg[k_], Sb.x, Sb.dates, Sb.dd)
            assert abs(w["rho_dd"] - r2) < 1e-10 and abs(w["do"] - d2) < 1e-10 and abs(w["book_loss_in_dd_days"] - Sb.dd_loss) < 1e-9
        assert r["clears_both"] == (r["WF"]["clears"] and r["LB"]["clears"]) and abs(r["size_after"] - 1.0 - r["delta"]) < 1e-12
    own = {s: (R11.unified(B, B.raw, *WINDOWS[s])["roc"], R11.unified(B, B.raw, *WINDOWS[s])["sort"]) for s in WINDOWS}
    assert set(reproduce(B, ref=own)) == {"WF", "LB"}
    assert set(reproduce(B, ref={s: (v[0] + 0.001, v[1] + 0.0001) for s, v in own.items()})) == {"WF", "LB"}                      # inside R11.P2_TOL
    for what, ref in (("the real numbers", None), ("a ROC 0.01 off", {s: (v[0] + 0.01, v[1]) for s, v in own.items()}),
                      ("a Sortino 0.002 off", {s: (v[0], v[1] + 0.002) for s, v in own.items()}), ("the LB 0.01 off", {"WF": own["WF"], "LB": (own["LB"][0] + 0.01, own["LB"][1])})):
        try:
            reproduce(B, ref=ref)
            raise AssertionError(f"reproduce must refuse a book with {what}")
        except SystemExit:
            pass
    # the Sortino half of the bars binds (the synthetic book's Sortino sits far above #463's 3.8, so the real bars would not show it): ROC bars low, Sortino bars at the median
    srt = {s: float(np.median([r[s]["book_plus_d"]["sort"] for r in rs["rows"]])) for s in WINDOWS}
    rs2 = resizing(B, metas, bars={s: (0.0, srt[s]) for s in WINDOWS})
    for s in WINDOWS:
        flags = [r[s]["clears"] for r in rs2["rows"]]
        assert any(flags) and not all(flags) and flags == [r[s]["book_plus_d"]["sort"] >= srt[s] for r in rs2["rows"]]
        assert rs2["bars"][s] == {"roc": 0.0, "sort": srt[s]}


def t_cell_oracle():
    """One cell's draws recomputed draw by draw: the same legs (same RNG streams), then r11_risk.stats and the independent rho / DO implementation as the oracle."""
    dates = pd.bdate_range("2010-06-07", "2026-06-30")
    x = np.sum(synth_legs(dates), axis=0)
    SW, SL, V = build_stretches(x, dates)
    cell, idx, M = (1.0, 0.3, "same", 100, "t3", "clustered"), 11, 6
    s, rho_dd, rmode, n, tails, vol = cell
    ev = eval_cell(SW, SL, V, cell, idx, M)
    legs = {name: gen_leg(S.z, S.dd, S.g[vol], V, s, n, rho_dd, rho_dd, tails, M, np.random.default_rng([SEED, idx, STRETCH_ID[name]])) for name, S in (("WF", SW), ("LB", SL))}
    close = lambda a, b: (np.isnan(a) and np.isnan(b)) or abs(a - b) <= 1e-9 * max(abs(b), 1e-300)
    for m in range(M):
        r3 = [R11.stats(SW.x + c * legs["WF"][m], SW.dates)["roc"] for c in CS]
        c = CS[int(np.argmax(r3))]                                                   # the first maximum = the smaller c on a tie
        w, l = R11.stats(SW.x + c * legs["WF"][m], SW.dates), R11.stats(SL.x + c * legs["LB"][m], SL.dates)
        a, b = R11.stats(legs["WF"][m], SW.dates), R11.stats(legs["LB"][m], SL.dates)
        assert ev["cstar"][m] == c and close(ev["roc_wf"][m], w["roc"]) and close(ev["sort_wf"][m], w["sort"])
        assert close(ev["roc_lb"][m], l["roc"]) and close(ev["sort_lb"][m], l["sort"])
        assert close(ev["roc_alone_wf"][m], a["roc"]) and close(ev["sort_alone_wf"][m], a["sort"]) and close(ev["ann_alone_wf"][m], a["net"] / a["years"])
        assert close(ev["mdd_alone_wf"][m], a["max_dd"])
        assert close(ev["roc_alone_lb"][m], b["roc"]) and close(ev["sort_alone_lb"][m], b["sort"])
        for nm, S in (("wf", SW), ("lb", SL)):
            r2, d2 = naive_rho_do(legs[nm.upper()][m], S.x, S.dates, S.dd)
            assert close(ev["rho_" + nm][m], r2) and close(ev["do_" + nm][m], d2), (m, nm, ev["rho_" + nm][m], r2)
        assert ev["pass_wf"][m] == bool(w["roc"] >= BAR_WF_ROC and w["sort"] >= BAR_WF_SORT) and ev["pass_lb"][m] == bool(l["roc"] >= BAR_LB_ROC and l["sort"] >= BAR_LB_SORT)
        assert close(ev["d_roc_wf"][m], w["roc"] - BASE_WF_ROC)
    assert len(set(ev["cstar"])) > 1                                                 # the size search is exercised (not always the same c)
    assert abs(V - float(np.std(SW.x)) * math.sqrt(252.0) / 3.0) < 1e-9              # V is the WF book's (for both stretches)
    # the window coupling (z does not sum to 0 over ONE window): a daily leg's expected P&L inside the deepest window moves by V / sqrt(252) x sum(z) per unit rho_dd
    c = window_coupling(SW, V)
    assert abs(c["z_sum"]) > 1.0 and c["window_days"] == SW.episodes[0]["it"] - SW.episodes[0]["i0"] + 1
    assert c["z_sum"] < 0 and c["usd_per_unit_rho_daily_leg"] < 0                    # addendum 1: the deepest window sits below the stretch mean - a positively correlated leg LOSES there
    e0 = SW.episodes[0]
    assert abs(c["z_sum_clustered"] - (SW.g["clustered"][e0["i0"]:e0["it"] + 1] * SW.z[e0["i0"]:e0["it"] + 1]).sum()) < 1e-9 and abs(c["z_sum_clustered"] - c["z_sum"]) > 1e-6
    win = lambda rho: gen_leg(SW.z, SW.dd, SW.g["const"], V, 1.0, 252, rho, rho, "normal", 2, np.random.default_rng(77))[:, e0["i0"]:e0["it"] + 1].sum(axis=1)
    assert np.allclose((win(0.5) - win(-0.5)) / c["usd_per_unit_rho_daily_leg"], 1.0, rtol=1e-6)    # same e, +0.5 vs -0.5 = one unit of rho: exactly sigma (sum(z) - W mean(z))
    # addendum 1, the point of the fix: on the same draws, DO falls as rho_dd rises (a leg correlated in the drawdowns loses in them) and the stretch mean stays on target
    dos, means = [], []
    for rd in (-0.6, -0.3, 0.0, 0.3, 0.6):
        Lg = gen_leg(SW.z, SW.dd, SW.g["const"], V, 1.0, 252, rd, 0.0, "normal", 400, np.random.default_rng(5))
        dos.append(float(np.median(realised(Lg, SW)[1])))
        means.append(float(Lg.mean()))
    assert all(a > b for a, b in zip(dos, dos[1:])), dos
    assert all(abs(m_ / (V / 252.0) - 1.0) < 0.05 for m_ in means), means
    # the Sortino halves of the pass flags bind (the synthetic book's Sortino is far above the real bars): patch the two Sortino bars to the draws' medians, then re-check
    old = (globals()["BAR_WF_SORT"], globals()["BAR_LB_SORT"], globals()["BAR_WF_ROC"], globals()["BAR_LB_ROC"])
    try:
        globals()["BAR_WF_ROC"], globals()["BAR_LB_ROC"] = 0.0, 0.0
        globals()["BAR_WF_SORT"], globals()["BAR_LB_SORT"] = float(np.median(ev["sort_wf"])), float(np.median(ev["sort_lb"]))
        ev2 = eval_cell(SW, SL, V, cell, idx, M)
        assert (ev2["pass_wf"] == (ev2["sort_wf"] >= BAR_WF_SORT)).all() and (ev2["pass_lb"] == (ev2["sort_lb"] >= BAR_LB_SORT)).all()
        assert ev2["pass_wf"].any() and not ev2["pass_wf"].all() and ev2["pass_lb"].any() and not ev2["pass_lb"].all()
    finally:
        globals()["BAR_WF_SORT"], globals()["BAR_LB_SORT"], globals()["BAR_WF_ROC"], globals()["BAR_LB_ROC"] = old


def t_determinism():
    dates = pd.bdate_range("2010-06-07", "2026-06-30")
    x = np.sum(synth_legs(dates), axis=0)
    SW, SL, V = build_stretches(x, dates)
    cell = (1.5, -0.3, "same", 100, "t3", "clustered")
    a, b, c = eval_cell(SW, SL, V, cell, 7, 30), eval_cell(SW, SL, V, cell, 7, 30), eval_cell(SW, SL, V, cell, 8, 30)
    assert all(np.array_equal(a[k], b[k], equal_nan=True) for k in DRAW_KEYS) and not np.array_equal(a["roc_alone_wf"], c["roc_alone_wf"])
    assert set(a["cstar"]) <= set(CS) and a["pass_wf"].dtype == bool and all(len(a[k]) == 30 for k in DRAW_KEYS)
    assert (a["pass_wf"] == ((a["roc_wf"] >= BAR_WF_ROC) & (a["sort_wf"] >= BAR_WF_SORT))).all()
    assert np.allclose(a["roc_wf"] - BASE_WF_ROC, a["d_roc_wf"])
    # a big edge lifts, no edge does not: the generator + evaluation are wired the right way round
    hi = eval_cell(SW, SL, V, (3.0, 0.0, "zero", 250, "normal", "const"), 1, 60)
    lo = eval_cell(SW, SL, V, (0.25, 0.0, "zero", 250, "normal", "const"), 1, 60)
    assert hi["pass_wf"].mean() > lo["pass_wf"].mean() and np.nanmedian(hi["roc_alone_wf"]) > np.nanmedian(lo["roc_alone_wf"])


def selftest():
    tests = [("grid, bars, cell order, bins", t_grid), ("generator: Sharpe, volatility, daily correlation with z, activity", t_generator), ("t(3) has unit variance", t_t3),
             ("DO = +1 and rho_dd = -1 for minus-the-book-on-DD-days; rho_dd / DO vs an independent implementation", t_offset),
             ("vectorised ROC / Sortino = r11_risk.stats", t_vstats),
             ("c* tie rule", t_ctie), ("DD-day / DD-week counting (ISO weeks, year boundary, 1/3 rule)", t_weeks), ("bins, thresholds, greyed flag", t_bins),
             ("MAP.txt sentences: greyed n = 25 never used, sparse bands called sparse, seat lines", t_text),
             ("seat rule: dollars and the derivative claim", t_seat), ("small helpers: clustered path, trailing std, strict json, coupling, phrases", t_helpers),
             ("leave-one-out, re-sizing row, reproduction gate on a fake book", t_reference),
             ("one cell recomputed draw by draw against r11_risk.stats (c*, frozen LB size, rho_dd, DO, bars)", t_cell_oracle),
             ("cells are reproducible and wired the right way round", t_determinism)]
    for name, fn in tests:
        t = time.time()
        fn()
        print(f"  ok  {name} ({time.time() - t:.1f}s)", flush=True)
    print("selftest ok", flush=True)


# ------------------------------------------------------------------ smoke: the whole pipeline on a SYNTHETIC book
def smoke(d):
    """The whole pipeline end to end on a synthetic book (four random walks with drift on business days 2010-06-07..2026-06-30, fixed seed) with SMOKE_GRID and
    SMOKE_M draws: cells, draws, maps, thresholds, seat rule, the re-sizing row and MAP.txt are written to DIR and read back; the book-reproduction check and
    leave-one-out are skipped (a synthetic book cannot match #463); then five full-size cells are timed. Its numbers mean nothing."""
    root = os.path.abspath(d)
    assert "smoke" in os.path.basename(root).lower() and not os.path.normcase(root).startswith(os.path.normcase(r"C:\EdgeLog")), \
        "smoke needs its own scratch folder (name contains 'smoke'), never a real cache"
    os.makedirs(root, exist_ok=True)
    t0 = time.time()
    # the prereg gate: refuses on 'TBD' and on a wrong hash, passes on the right one (a probe file in DIR), and the real prereg is the registered one
    probe = os.path.join(root, "prereg_probe.txt")
    with open(probe, "w", newline="") as f:
        f.write("probe\r\nfile\r\n")
    for want, ok in (("TBD", False), ("0" * 64, False), (R11.sha_lf(probe), True)):
        try:
            check_prereg(probe, want)
            got = True
        except SystemExit:
            got = False
        assert got == ok, f"smoke: the prereg gate must {'pass' if ok else 'refuse'} for {want[:8]}"
    check_prereg()
    # the synthetic book, its legs as a fake Book, the re-sizing row, then the shared pipeline
    dates = pd.bdate_range("2010-06-07", "2026-06-30")
    B = FakeBook(synth_legs(dates), dates)
    metas = [{"strategy": f"SYNLEG{k}", "instrument": "NQ"} for k in range(len(B.Am_leg))]
    rs = resizing(B, metas)
    save(root, "resizing.json", rs)
    res = pipeline(B.raw, B.index, SMOKE_GRID, SMOKE_M, root, min_bin=SMOKE_MIN_BIN, every=16, label="SYNTHETIC", extras={"resizing": rs})
    # read everything back
    ncell = len(cells_of(SMOKE_GRID))
    cells = pd.read_csv(os.path.join(root, "cells.csv"))
    assert len(cells) == ncell and cells["cell"].tolist() == list(range(ncell))
    for c in ("p_pass_wf", "p_pass_wf_lb", "p_pass_lb"):
        assert cells[c].between(0, 1).all()
    assert (cells["p_pass_wf_lb"] <= cells[["p_pass_wf", "p_pass_lb"]].min(axis=1) + 1e-12).all()
    assert (cells["greyed"] == (cells["n"] < GREY_BELOW)).all() and cells["greyed"].any() and not cells["greyed"].all()
    z = np.load(os.path.join(root, "draws.npz"))
    assert len(z["cell"]) == ncell * SMOKE_M and set(DRAW_KEYS) <= set(z.files) and z["pass_wf"].dtype == bool
    maps = sorted(f for f in os.listdir(root) if f.startswith("map_") and f.endswith(".csv"))
    nmaps = len({map_key(c) for c in cells_of(SMOKE_GRID)})
    assert len(maps) == nmaps == 24 and "map_100_t3_clustered_same.csv" in maps
    total = 0
    for f in maps:
        m = pd.read_csv(os.path.join(root, f))
        n_ = int(f.split("_")[1])
        assert len(m) == len(ROC_LABELS) * len(RHO_LABELS) and (m["greyed"] == (n_ < GREY_BELOW)).all()
        assert (m["pass_wf"] <= m["draws"]).all() and (m["pass_wf_lb"] <= m["pass_wf"]).all()
        total += int(m["draws"].sum())
    assert total + res["unbinned"] == ncell * SMOKE_M
    thr = pd.read_csv(os.path.join(root, "thresholds.csv"))
    assert len(thr) == nmaps * len(RHO_LABELS) and (thr["greyed"] == (thr["n"] < GREY_BELOW)).all() and thr["greyed"].any()
    found = int((thr["wf_p50_bin"] != "none").sum())
    seat = json.load(open(os.path.join(root, "seat_rule.json")))
    assert seat["WF"]["dollars_a_year_per_1000_lost"] > 0 and seat["WF"]["peak"] < seat["WF"]["trough"] and "rule" in seat
    rj = json.load(open(os.path.join(root, "resizing.json")))
    assert len(rj["rows"]) == len(metas) * len(DELTAS) and all(set(("WF", "LB", "clears_both")) <= set(r) for r in rj["rows"])
    txt = open(os.path.join(root, "MAP.txt"), "rb").read().decode("ascii")
    assert "n=100 a year" in txt and "n=250 a year" in txt and "n=25 a year" not in txt and "under 50 sealed-year trades" in txt
    assert "Seat rule WF" in txt and "Re-sizing reference" in txt
    assert "WF generator coupling" in txt and "LB generator coupling" in txt and "too few draws" in txt                       # the sparse extreme rho_dd bands are called sparse
    assert not os.path.exists(os.path.join(root, "leave_one_out.json")), "smoke must skip leave-one-out"
    json.load(open(os.path.join(root, "meta.json")))
    # a cell is reproducible from its index alone, and more edge lifts more
    SW, SL, V = build_stretches(B.raw, dates)
    j = 5
    ev = eval_cell(SW, SL, V, cells_of(SMOKE_GRID)[j], j, SMOKE_M)
    assert np.array_equal(z["roc_wf"][j * SMOKE_M:(j + 1) * SMOKE_M], ev["roc_wf"], equal_nan=True)
    assert cells[cells["s"] == 3.0]["p_pass_wf"].mean() > cells[cells["s"] == 0.5]["p_pass_wf"].mean()
    print(f"smoke grid: {ncell} cells x {SMOKE_M} draws, {nmaps} maps, {len(thr)} threshold rows ({found} with a 50% WF threshold); "
          f"smoke grid took {time.time() - t0:.1f}s", flush=True)
    # timing: 20 evenly spread full-size cells (M = 200) of the real grid on the synthetic book, never on the real one
    full = cells_of(GRID)
    picks = list(range(7, len(full), len(full) // 20))[:20]
    t1 = time.time()
    for i in picks:
        eval_cell(SW, SL, V, full[i], i, M_DRAWS)
    per = (time.time() - t1) / len(picks)
    print(f"timing: {len(picks)} full-size cells (200 draws) {time.time() - t1:.1f}s = {per:.3f}s a cell -> the {len(full)}-cell grid ~ {per * len(full):.0f}s of cell work "
          f"(+ the maps, a few seconds)", flush=True)
    print(f"SMOKE OK (synthetic numbers - meaningless); total {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if cmd == ["selftest"]:
        selftest()
    elif cmd == ["run"]:
        run()
    elif len(cmd) == 2 and cmd[0] == "smoke":
        smoke(cmd[1])
    else:
        print(__doc__ or "usage: r12_mdl.py selftest | smoke DIR | run")
        sys.exit(2)
