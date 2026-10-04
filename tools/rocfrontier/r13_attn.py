# ATTN r1 - the overnight attention premium: buy each day's "stocks in play" (the SIPORB selection, known at 09:35 ET) at the closing print, sell them at the next session's opening
# print, hedge the basket short NQ over the same night; a leg for BOOK #463 (Barber & Odean 2008; Berkman, Koch, Tuttle & Zhang 2012; Lou, Polk & Skouras 2019).
# Pre-registered: tools/rocfrontier/PREREG_ATTN_R1.txt (canonical LF sha256 39a259ec...7804, MANAGER-reviewed 2026-10-04, written before any overnight return of these stocks was
# computed). Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE.
#   python r13_attn.py selftest    hand-made worlds: split-safe P&L, gap-scan removal, unpriceable exits, the hedge and its per-name split, the null, stamping, the statistics, the cut
#   python r13_attn.py smoke DIR   offline end-to-end on a SYNTHETIC world (r5_siporb's fake Alpaca, a fake NQ master, a fake #463 book); DIR's name must contain 'smoke'
#   python r13_attn.py stage_a     WF Stage A + A2 + the reports -> attn_stageA.json, PRE-LOCKBOX ONLY (every input is cut to dates < 2025-06-30 when it is read); runs AFTER SIPORB's Stage A
#   python r13_attn.py stage_b     Stage B (lockbox, once): refuses unless Stage A + A2 passed under this exact file AND SIPORB's lockbox has been read (or SIPORB died before it)
# Reads (never writes) the SIPORB cache through r5_siporb (Data, read_long, roll14), the NQ 5m RTH masters through augur_engine.data and the #463 book through r11_risk.
# Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else.
import contextlib, io, json, math, os, sys, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r5_siporb as S        # SIPORB's Data (filters 1-3, the 09:30 bar, top20, the gap scan), read_long, roll14, the cache readers, the fake Alpaca of its smoke - imported, never copied
import r11_risk as R11       # the #463 book (records -> Book), stats, underwater, ols_nw, the windows and the reference numbers - imported, never copied

TS = pd.Timestamp
OUT = os.environ.get("EDGELOG_ATTN_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\attn_r1")      # results, outside git
PREREG = os.path.join(HERE, "PREREG_ATTN_R1.txt")
PREREG_SHA = "39a259ecd677a3ce46ad8979e451a21af05026b763749a106b12ba23d5307804"                  # canonical (LF) sha256 of the pre-registration as committed
WF0, PRE_END, LB0, LB1 = R11.WF0, R11.PRE_END, R11.LB0, R11.LB1    # WF = exits [2016-07-01, 2025-06-29], LB = exits [2025-06-30, 2026-06-30] INCLUSIVE (the house close-day rule); cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, TOL = R11.P2_REF["unified"]["WF"], R11.P2_REF["unified"]["LB"], R11.P2_TOL    # #463's unified-convention ROC@30k / Sortino (93.81 / 3.816, 155.54 / 4.150) and the match tolerance
SLOT, PX_MIN, ADV_MIN = 5000.0, 5.0, 5_000_000.0           # $5,000 a name; 09:35 price >= $5; 14-session mean raw close x volume >= $5m
COST_BPS, STRESS_BPS = 5.0, (10.0, 20.0)                   # of the notional, a side (entry notional, exit value); the hedge's 0.533 pts is separate
EXIT_WINDOW = 10                                           # an exit with no bar at t+1: the first raw open in sessions t+2 .. t+11
NQ_X, NQ_PTS = 20.0, 0.533                                 # $ a point; round-trip cost in points a contract, pro rata
NREP, SEED = 500, 20261004
CS = (0.5, 1.0, 2.0)
YEARS = tuple(range(2016, 2025))                           # the nine July-June years 2016-17 .. 2024-25
SRC_RAW, SRC_ADJ, NQ_D0 = "db_noadj_rth", "db_adj_rth", "2016-06-01"   # the NQ masters; CHOICE: loaded from 2016-06-01 (the first night's session), cut at the stage's cut
NIGHT0 = TS("2016-06-01")      # CHOICE: nights are computed from the first one that exits on/after this date (a month before WF); a night is judged by the date it is BOOKED, so the margin changes no number
RULES = {"n": 100, "cov": 0.98, "roc": 15.0, "pf": 1.10, "t": 2.0, "nw_lags": 5, "null": True, "stress": True, "stress_bps": 10.0, "exbest": True, "best_pct": 1, "years": 6,
         "a2_roc": 1.05 * BOOK_WF[0], "a2_sort": BOOK_WF[1], "b_n": 50, "b_roc": BOOK_LB[0], "b_sort": BOOK_LB[1]}   # CHOICE: A2's bar is 1.05 x 93.81 as a formula (98.5005), not its rounding 98.5
CHECK_BOOK = True       # refuse to judge if the #463 records do not reproduce its numbers; a real run always checks (only smoke() may switch it)
WHY = ("traded", "price", "adv", "shares", "factor", "gap", "cut")     # why a top-20 name is out, first failing rule: 09:35 price, ADV$, no whole share, no split factor, gap scan, window cut by the stage
NORMAL, LATER, NONE, CUT = 0, 1, 2, 3                       # exit kinds: open of t+1 | first later open | none within the window (-100%) | window runs past the stage's data (unresolved)


# ------------------------------------------------------------------ guards: the prereg, the cut, the stamp
def refuse(msg):
    raise SystemExit(msg)


def prereg_ok():
    """the frozen spec this file implements must still be the committed one (a changed spec = a new file, r2): a missing or changed file refuses Stage A and B"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_ATTN_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_ATTN_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_ATTN_R1.txt sha256 matches the registered one")
    return True


def stamp():
    """the version a stage ran with: this file's LF sha256 + the shared half-day list, like SIPORB's stamp (Stage B refuses on any change). CHOICE: also r5_siporb.py's and r11_risk.py's - Data, read_long,
    stats and the book loader decide the numbers, so a change to either after Stage A must send it through Stage A again"""
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "siporb_sha256": R11.sha_lf(S.__file__), "r11_sha256": R11.sha_lf(R11.__file__),
            "early_close": sorted(S.EARLY_CLOSE_DATES)}


def assert_cut(label, dates, cut):
    """nothing on/after the stage's cut may be in memory (Stage A: 2025-06-30, Stage B: 2026-07-01); `dates` = anything with .max()"""
    if len(dates) == 0:
        return
    mx, c = TS(dates.max()), TS(cut)
    if mx.tzinfo is not None and c.tzinfo is None:
        c = c.tz_localize(mx.tzinfo)
    if not mx < c:
        refuse(f"refused: {label} holds a date on/after the cut {TS(cut):%Y-%m-%d} (nothing computed)")


def dump(obj, name):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=1, default=R11.js)


def peak_mb():
    try:
        import psutil
        return psutil.Process().memory_info().peak_wset / 2 ** 20
    except Exception:
        return None


@contextlib.contextmanager
def patched(mod, **kw):
    """swap module attributes for a block and put them back (the self-tests and the smoke stub the loaders; nothing stays patched)"""
    old = {k: getattr(mod, k) for k in kw}
    for k, v in kw.items():
        setattr(mod, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(mod, k, v)


# ------------------------------------------------------------------ the arrays one run needs, aligned on D.days x D.syms
def align(D, df):
    """(session row, symbol column, keep) of every row of a long daily frame on D.days x D.syms - the axes idiom of r5_siporb.Data"""
    m = pd.Index(D.syms).get_indexer(df["symbol"].cat.categories.astype(str))[df["symbol"].cat.codes.to_numpy()]
    d = D.days.get_indexer(pd.DatetimeIndex(df["date"]))
    ok = (m >= 0) & (d >= 0)
    return d[ok], m[ok], ok


def fill(shape, vals, ax):
    a = np.full(shape, np.nan)
    a[ax[0], ax[1]] = vals[ax[2]]
    return a


def load_data(t_end):
    """r5_siporb.Data cut at t_end (S.LB0 for Stage A, S.END for Stage B): filters 1-3, the 09:30 bar, Relative Volume, the gap scan; asserted to hold no session on/after the cut"""
    D = S.Data(t_end, open5=True)
    assert_cut("sessions", D.days, t_end)
    return D


def slim(D):
    """free what this harness never reads again - H5, L5, V5 and atr are four T x S float arrays r5_siporb.Data keeps (only the coverage report above reads V5); called right after it"""
    for a in ("H5", "L5", "V5", "atr", "need", "mexp"):
        if hasattr(D, a):
            delattr(D, a)


def load_arrays(D, t_end):
    """the raw close, ADV$ and the split factor on D.days x D.syms, re-read from the two daily caches (r5_siporb.read_long cuts them to dates < t_end at read time; Data deletes
    them after use). ADV$ = S.roll14 of raw close x volume (mean of the previous 14 sessions, all 14 present); F = raw open / split-adjusted open (SIPORB's split factor)"""
    shape = (len(D.days), len(D.syms))
    raw = S.read_long("raw", t_end)
    assert_cut("daily_raw", raw["date"], t_end)
    ax = align(D, raw)
    Cl = fill(shape, raw["c"].to_numpy(float), ax)
    dv = fill(shape, raw["c"].to_numpy(float) * raw["v"].to_numpy(float), ax)
    del raw
    adv = S.roll14(dv)
    del dv
    spl = S.read_long("split", t_end)
    assert_cut("daily_split", spl["date"], t_end)
    Os = fill(shape, spl["o"].to_numpy(float), align(D, spl))
    del spl
    with np.errstate(invalid="ignore", divide="ignore"):
        F = D.Od / Os
    return Cl, adv, F


class World:
    """D (an r5_siporb.Data: days, syms, P, RV, C5, O5, Od, msplit, top20), Cl (raw close), adv (ADV$), F (split factor), hedge (per night: hr = the NQ hedge's P&L per $ of basket cost, delta = the
    roll-corrected overnight change in points, px = the unadjusted 16:00 price; NaN = no hedge that night)"""
    def __init__(self, D, Cl, adv, F, hedge):
        self.D, self.Cl, self.adv, self.F, self.hedge = D, Cl, adv, F, hedge


# ------------------------------------------------------------------ the NQ hedge: 16:00 print of session t -> 09:30 print of t+1
def data_mod():
    from augur_engine import data
    return data


def load_nq(t_end):
    """the NQ 5m RTH masters (roll-corrected for the hedge's P&L, unadjusted for its notional) -> ({'raw': df, 'adj': df} of open / close on the tz-aware bar-START index, their registry rows), every
    array cut to bars BEFORE t_end (midnight US/Eastern) and asserted so, whatever load_master_arrays hands back"""
    data = data_mod()
    cut = TS(t_end).tz_localize("US/Eastern")
    d1 = str((TS(t_end) - pd.Timedelta(days=1)).date())
    out, meta = {}, {}
    for tag, src in (("raw", SRC_RAW), ("adj", SRC_ADJ)):
        m = data.find_master("NQ", "5m", "rth", src)
        if m is None or m.get("source") != src:
            refuse(f"refused: no {src} NQ 5m RTH master (nothing computed)")
        a = data.load_master_arrays(m, NQ_D0, d1)
        ix = pd.DatetimeIndex(a["index"])
        keep = np.asarray(ix < cut)
        df = pd.DataFrame({k: np.asarray(a[k], float)[keep] for k in ("open", "close")}, index=ix[keep])
        if not len(df):
            refuse(f"refused: the {src} NQ master has no bar before the cut (nothing computed)")
        assert_cut(f"NQ {src}", df.index, cut)
        out[tag], meta[tag] = df, {k: m.get(k) for k in ("id", "source", "filename")}
    return out, meta


def nq_prints(df):
    """one NQ master -> a frame by session date: the 09:30 print (open of the 09:30 bar) and the 16:00 print (close of the 15:55 bar; the 12:55 bar on an NYSE half day, S.EARLY_CLOSE_DATES).
    CHOICE fallbacks: no 15:55 bar -> the close of the last bar that starts 15:30 .. 15:50 (12:30 .. 12:50 on a half day); no 09:30 bar -> the open of the first bar that starts before 10:00;
    none -> NaN (that night is unhedged in H and counted). Bars with a non-positive or non-finite price do not count; a duplicated bar: the later row wins"""
    ix = df.index
    hm = ix.hour.to_numpy() * 60 + ix.minute.to_numpy()
    day = pd.DatetimeIndex(ix.tz_localize(None).normalize())
    half = np.asarray(day.isin(pd.DatetimeIndex(sorted(S.EARLY_CLOSE_DATES))))
    last = np.where(half, S.EARLY_CLOSE_MIN, 960) - 5                                    # start of the session's last bar: 15:55, or 12:55 on a half day
    o, c = df["open"].to_numpy(float), df["close"].to_numpy(float)
    good = np.isfinite(o) & np.isfinite(c) & (o > 0) & (c > 0)
    g = pd.DataFrame({"day": day, "hm": hm, "o": o, "c": c, "last": last})
    op = g[good & (hm >= 570) & (hm < 600)].sort_values(["day", "hm"], kind="stable").groupby("day").first()
    cl = g[good & (hm >= last - 25) & (hm <= last)].sort_values(["day", "hm"], kind="stable").groupby("day").last()
    return pd.DataFrame({"open": op["o"], "open_hm": op["hm"], "close": cl["c"], "close_hm": cl["hm"], "last": cl["last"]})


def hedge_prints(nq):
    """the two masters' prints on one frame: o_adj / c_adj (roll-corrected: the hedge's P&L), c_raw (unadjusted: its notional), and the sessions that needed a fallback bar (the adj master's)"""
    pa, pr = nq_prints(nq["adj"]), nq_prints(nq["raw"])
    t = pd.DataFrame({"o_adj": pa["open"], "c_adj": pa["close"], "c_raw": pr["close"]}).sort_index()
    t["open_fb"] = (pa["open_hm"].notna() & (pa["open_hm"] != 570)).reindex(t.index, fill_value=False)
    t["close_fb"] = (pa["close_hm"].notna() & (pa["close_hm"] != pa["last"])).reindex(t.index, fill_value=False)
    return t


def hedge_returns(days, pr):
    """-> SimpleNamespace(hr, delta, px), each (T,): night i = session i -> i+1. delta = the roll-corrected open of i+1 minus the roll-corrected 16:00 print of i; px = the UNADJUSTED 16:00 print of i;
    hr = - (delta + 0.533) / px = the hedge's P&L per $ of basket cost: contracts = cost / (px x 20), short, P&L = - contracts x 20 x delta - contracts x 0.533 x 20. NaN where a print is missing"""
    T = len(days)
    g = pr.reindex(days)
    c_adj, o_adj, c_raw = (g[k].to_numpy(float) for k in ("c_adj", "o_adj", "c_raw"))
    delta = np.full(T, np.nan)
    delta[:-1] = o_adj[1:] - c_adj[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        hr = np.where(c_raw > 0, -(delta + NQ_PTS) / c_raw, np.nan)
    return SimpleNamespace(hr=hr, delta=delta, px=c_raw)


# ------------------------------------------------------------------ one night, every symbol
def night(W, i):
    """session i -> the next session, for every symbol. A name is tradable when it passes filters 1-3 (P), its 09:35 price is >= $5 (the 09:30 bar's close; CHOICE: the raw open when there is no
    09:30 bar), its ADV$ >= $5m (NaN = not), it has a whole share at the raw close (CHOICE: a close above $5,000 or no close = no position) and a split factor on the day (CHOICE: without one
    the exit cannot be made split-safe). Exit: the raw open of i+1 x F_i / F_(i+1); none (or no split factor that day) -> the first such open in sessions i+2 .. i+11, booked that day; none in the
    window -> kind NONE (-100%, booked on i+1: CHOICE), or kind CUT when the window runs past the stage's data (CHOICE: unresolved, out of the set AND the null, counted). A name whose exit symbol-day is flagged
    by the gap scan (D.msplit) is out of both.  -> elig (the null's universe), why (code in WHY), N (entry cost), Vx (exit value), J (booking row), K (kind)"""
    D, T = W.D, len(W.D.days)
    nsym = len(D.syms)
    with np.errstate(invalid="ignore", divide="ignore"):
        px = np.where(np.isfinite(D.C5[i]), D.C5[i], D.Od[i])
        sh = np.floor(SLOT / W.Cl[i] + 1e-9)
        c_px, c_adv, c_sh, c_f = px >= PX_MIN, W.adv[i] >= ADV_MIN, sh >= 1.0, np.isfinite(W.F[i])
    cand = np.flatnonzero(D.P[i] & c_px & c_adv & c_sh & c_f)
    j = np.full(len(cand), -1, np.int64)
    for k in range(i + 1, min(i + 2 + EXIT_WINDOW, T)):                                    # sessions t+1 .. t+11
        hit = (j < 0) & np.isfinite(D.Od[k, cand]) & np.isfinite(W.F[k, cand])
        j[hit] = k
    found = j >= 0
    full = i + 1 + EXIT_WINDOW <= T - 1                                                    # every session t+1 .. t+11 is in the stage's data
    kind = np.where(found, np.where(j == i + 1, NORMAL, LATER), NONE if full else CUT).astype(np.int8)
    booked = np.where(found, j, i + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        vx = sh[cand] * D.Od[booked, cand] * W.F[i, cand] / W.F[booked, cand]
    vx = np.where(found, vx, np.where(kind == NONE, 0.0, np.nan))
    gap = np.zeros(len(cand), bool)
    gap[found] = D.msplit[j[found], cand[found]]
    keep = ~gap & (kind != CUT)
    why = np.zeros(nsym, np.int8)
    for code, c in ((4, c_f), (3, c_sh), (2, c_adv), (1, c_px)):                           # the first failing rule wins: price, ADV$, shares, factor
        why[~c] = code
    why[cand[gap]], why[cand[kind == CUT]] = 5, 6
    N, Vx, J, K = np.full(nsym, np.nan), np.full(nsym, np.nan), np.full(nsym, -1, np.int64), np.full(nsym, -1, np.int8)
    N[cand], Vx[cand], J[cand], K[cand] = sh[cand] * W.Cl[i, cand], vx, booked, kind
    elig = np.zeros(nsym, bool)
    elig[cand[keep]] = True
    return SimpleNamespace(elig=elig, why=why, N=N, Vx=Vx, J=J, K=K)


def draw_subsets(rng, n, k, nreps):
    """nreps uniform random k-subsets of range(n), without replacement: the k smallest of n i.i.d. uniform keys; (nreps, k) positions"""
    if not 0 < k <= n:
        raise ValueError(f"cannot draw {k} of {n}")
    return rng.random((nreps, n)).argpartition(k - 1, axis=1)[:, :k]


def run_nights(W, nreps=0, seed=SEED):
    """every night from NIGHT0: the attention set (D.top20, then the drops - not replaced - and the gap-scan removals), its name-nights, and (nreps > 0) the random-pick null: each night the same
    number of names drawn from that night's tradable universe (same sizing, exits, costs, hedge). -> att (name-night arrays: i night row, j booking row, s symbol, N, Vx, K kind), acc (nreps x T:
    each draw's hedged P&L booked by session row, base cost), cnt (counters by exit session row), gaps (the attention set's gap-scan removals at the raw R), kn (names traded per night)"""
    D, T = W.D, len(W.D.days)
    rng = np.random.default_rng(seed)
    first = max(int(D.days.searchsorted(NIGHT0)) - 1, 0)
    cols = {c: [] for c in ("i", "j", "s", "N", "Vx", "K")}
    cnt, gaps, kn = defaultdict(Counter), [], np.zeros(T, int)                             # cnt: by the night's exit session row
    acc = np.zeros((nreps, T)) if nreps else None
    for i in range(first, T - 1):
        nt = night(W, i)
        t20 = D.top20(i)
        w20 = nt.why[t20]
        c = cnt[i + 1]
        c["top20"] += len(t20)
        c["gap_universe"] += int((nt.why == 5).sum())                                      # the gap scan's removals across the whole tradable universe (the null's side)
        for code in range(1, len(WHY)):
            c[WHY[code]] += int((w20 == code).sum())
        for s in t20[w20 == 5]:                                                            # report only: the attention set's removed nights, at the raw R and the P&L a naive book would show
            r = float(D.Od[nt.J[s], s] / W.Cl[i, s])
            gaps.append((i, int(nt.J[s]), int(s), r, float(nt.N[s] * (r - 1.0))))
        att = t20[w20 == 0]
        k = len(att)
        kn[i] = k
        if not k:
            continue
        hr = float(W.hedge.hr[i])
        hedged = bool(np.isfinite(hr))
        hr0 = hr if hedged else 0.0                                                        # CHOICE: a night with no NQ print is unhedged in H (counted)
        for name, v in (("i", np.full(k, i)), ("j", nt.J[att]), ("s", att), ("N", nt.N[att]), ("Vx", nt.Vx[att]), ("K", nt.K[att])):
            cols[name].append(v)
        c["traded"] += k
        c["nights"] += 1
        c["later"] += int((nt.K[att] == LATER).sum())
        c["none"] += int((nt.K[att] == NONE).sum())
        c["unhedged_nights"] += 0 if hedged else 1
        with np.errstate(invalid="ignore"):
            c["split_nights"] += int((np.abs(W.F[nt.J[att], att] / W.F[i, att] - 1.0) > 0.01).sum())
        if nreps:                                                                          # (a night with no name draws nothing: CHOICE, it consumes no random numbers)
            pool = np.flatnonzero(nt.elig)
            cs = pool[draw_subsets(rng, len(pool), k, nreps)]
            n_, v_, bj = nt.N[cs], nt.Vx[cs], nt.J[cs]
            h = (v_ - n_) - COST_BPS * 1e-4 * (n_ + v_) + n_ * hr0                          # per-name hedged P&L (the hedge is linear in the basket cost)
            main = bj == i + 1
            acc[:, i + 1] += np.where(main, h, 0.0).sum(axis=1)
            if not main.all():
                r_, c_ = np.nonzero(~main)
                np.add.at(acc, (r_, bj[r_, c_]), h[r_, c_])
    att = {c: np.concatenate(v) if v else np.zeros(0) for c, v in cols.items()}
    for c in ("i", "j", "s", "K"):
        att[c] = att[c].astype(np.int64)
    return SimpleNamespace(att=att, acc=acc, cnt=cnt, gaps=gaps, kn=kn)


# ------------------------------------------------------------------ P&L, daily series, statistics
def name_pnl(A, hr, bps, hedged=True, alt0=False):
    """P&L of each name-night: exit value - entry cost - bps a side of both notionals, plus (hedged) its cost share of the night's hedge (N x hr; no NQ print = no hedge). CHOICE: a -100% exit has
    exit value 0, so it pays the 5 bps on the entry only (nothing is sold). alt0 (reported beside it): the same exit valued at a 0% loss, exit value = entry cost, paying both sides"""
    N, Vx = A["N"], A["Vx"]
    if alt0:
        Vx = np.where(A["K"] == NONE, N, Vx)
    p = (Vx - N) - bps * 1e-4 * (N + Vx)
    if hedged:
        h = hr[A["i"]]
        p = p + N * np.where(np.isfinite(h), h, 0.0)
    return p


def book_rows(B, D):
    """the row of the #463 index that each session of D.days is stamped on (a P&L is stamped on its EXIT session: Friday -> Monday is stamped on Monday)"""
    r = B.index.get_indexer(D.days)
    if (r < 0).any():
        refuse("refused: a session is not on the #463 index (nothing computed)")
    return r


def series(A, p, rows, nb):
    """name-night P&L -> (daily P&L on the #463 index, name-nights booked per row)"""
    r = rows[A["j"]]
    return np.bincount(r, weights=p, minlength=nb), np.bincount(r, minlength=nb)


def ceil_pct(n, pct):
    return -(-n * pct // 100)                                    # ceil(n x pct / 100) in integers (0.01 * 700 is not exact in floating point)


def jy(dates):
    d = pd.DatetimeIndex(dates)
    return d.year.to_numpy().astype(int) - (d.month.to_numpy() < 7).astype(int)    # July-June year: 2017-06-30 is 2016-17, 2017-07-03 is 2017-18


def breadth(x, dates, years=YEARS):
    """net by July-June year and how many are > 0 (a year that nets exactly 0, or has no night, is not positive)"""
    y = jy(dates)
    nets = {int(v): float(np.asarray(x)[y == v].sum()) for v in years}
    return nets, sum(1 for v in nets.values() if v > 0)


def nw_t(x, lags=None):
    """t of the mean of x, Newey-West (Bartlett) standard error with `lags` lags - r11_risk.ols_nw on a constant"""
    lags = RULES["nw_lags"] if lags is None else lags
    x = np.asarray(x, float)
    if len(x) <= lags + 1 or not np.ptp(x) > 0:
        return float("nan")
    return float(R11.ols_nw(x, np.ones((len(x), 1)), lags)[1][0])


def leg_stats(B, x, cnt, lo, hi, years=YEARS):
    """one stretch [lo, hi] (inclusive, on the #463 index) of a daily P&L series x with cnt name-nights booked per row. ROC@30k / Sortino / max drawdown: r11_risk.stats on the daily series (peak from
    0, years = last - first row / 365.25). PF, t (NW, 5 lags), the best-1%-nights removal and the July-June breadth: on the NIGHTLY series = the rows with >= 1 name-night booked (CHOICE: the
    prereg names the nightly series, not its index - here the exit sessions, stamped like the P&L, so a weekend night is one night)"""
    k = B.mask(lo, hi)
    xs, ds, cs = x[k], B.index[k], cnt[k]
    st = R11.stats(xs, ds) or {}
    nx = xs[cs > 0]
    gw, gl = float(nx[nx > 0].sum()), float(-nx[nx < 0].sum())
    m = ceil_pct(len(nx), RULES["best_pct"])
    top = float(np.sort(nx)[::-1][:m].sum()) if len(nx) else 0.0
    nets, npos = breadth(xs, ds, years)
    nan = float("nan")
    return {"stock_nights": int(cs.sum()), "nights": int(len(nx)), "net": float(xs.sum()), "years": st.get("years", nan), "max_dd": st.get("max_dd", nan), "roc": st.get("roc", nan),
            "sortino": st.get("sort", nan), "pf": (gw / gl if gl > 0 else float("inf")) if gw > 0 or gl > 0 else nan, "t": nw_t(nx), "net_ex_best": float(nx.sum()) - top, "best_n": int(m), "years_pos": int(npos), "by_year": nets}


def best_c(roc, cs=CS):
    """best c by WF book ROC@30k, ties -> the smaller c; a NaN ROC never wins"""
    v = {c: (float("-inf") if not np.isfinite(roc[c]) else float(roc[c])) for c in cs}
    return min(cs, key=lambda c: (-v[c], c))


def book_add(B, x, lo, hi):
    """#463's daily series + c x the leg's, per c in CS: ROC@30k, Sortino, net, max drawdown on [lo, hi]"""
    k = B.mask(lo, hi)
    out = {}
    for c in CS:
        s = R11.stats((B.raw + c * x)[k], B.index[k])
        out[c] = {"roc": s["roc"], "sortino": s["sort"], "net": s["net"], "max_dd": s["max_dd"]}
    return out


def book_check(B, lo, hi, ref):
    u = R11.unified(B, B.raw, lo, hi)
    return {"roc": u["roc"], "sortino": u["sort"], "ref": list(ref), "ok": bool(abs(u["roc"] - ref[0]) < TOL[0] and abs(u["sort"] - ref[1]) < TOL[1])}


def seat(B, x, lo, hi):
    """the SEAT measure on [lo, hi]: #463's qualifying drawdowns (R11.underwater episodes at least 1/3 as deep as the deepest; days = the day after the peak .. the trough), the DD weeks (ISO weeks with
    >= 3 index rows inside a qualifying drawdown), rho_dd = correlation of the weekly sums (leg, #463) over the DD weeks (needs >= 3), DO = the leg's P&L over the qualifying days / #463's loss over them.
    CHOICE: a weekly sum is over the whole ISO week's rows inside the stretch; the DD weeks are counted on the union of the qualifying drawdowns' days"""
    k = B.mask(lo, hi)
    book, leg, ds = B.raw[k], np.asarray(x)[k], B.index[k]
    eps = R11.underwater(book, ds)
    if not eps:
        return None
    q = [e for e in eps if e["depth"] >= eps[0]["depth"] / 3.0]
    inq = np.zeros(len(book), bool)
    for e in q:
        inq[e["i0"]:e["it"] + 1] = True
    iso = ds.isocalendar()
    wk = iso["year"].to_numpy().astype(int) * 100 + iso["week"].to_numpy().astype(int)
    _, inv = np.unique(wk, return_inverse=True)
    ddw = np.bincount(inv, weights=inq.astype(float)) >= 3
    lw, bw = np.bincount(inv, weights=leg)[ddw], np.bincount(inv, weights=book)[ddw]
    with np.errstate(invalid="ignore", divide="ignore"):
        rho = float(np.corrcoef(lw, bw)[0, 1]) if ddw.sum() >= 3 else float("nan")
    loss = -float(book[inq].sum())
    return {"deepest": eps[0]["depth"], "qualifying": [{k_: e[k_] for k_ in ("depth", "peak", "trough", "end")} for e in q], "dd_days": int(inq.sum()), "dd_weeks": int(ddw.sum()),
            "rho_dd": rho, "DO": float(leg[inq].sum()) / loss if loss > 0 else float("nan")}


def corrs(B, x, legs, lo, hi):
    """daily correlation of the leg with #463 and with each of its legs (B.Am_leg[k].T @ B.ones) over [lo, hi]"""
    k = B.mask(lo, hi)

    def r(a, b):
        with np.errstate(invalid="ignore", divide="ignore"):
            return float(np.corrcoef(a, b)[0, 1]) if np.ptp(a) > 0 and np.ptp(b) > 0 else float("nan")
    out = {"book": r(np.asarray(x)[k], B.raw[k])}
    for q, leg in enumerate(legs):
        out[f"{q}:{leg['strategy']}"] = r(np.asarray(x)[k], (B.Am_leg[q].T @ B.ones)[k])
    return out


def coverage(D, lo, hi):
    """prereg: open5 present on >= 98% of the stretch's sessions. CHOICE: read as the share of sessions with a day file in the open5 cache (the brief's reading); SIPORB's name-day coverage by year
    (every year >= 98% of the name-days passing filters 1-3) is reported beside it, not gated"""
    days = D.days[(D.days >= lo) & (D.days <= hi)]
    have = set(D.o5days)
    n5 = sum(f"{d:%Y-%m-%d}" in have for d in days)
    return {"sessions": int(len(days)), "with_open5": int(n5), "share": n5 / len(days) if len(days) else float("nan")}


# ------------------------------------------------------------------ the reports (never a pass route)
def by_group(A, p, grp, inw, names):
    out = {}
    for g, nm in names:
        m = inw & (grp == g)
        n = int(m.sum())
        out[nm] = {"n": n, "net": float(p[m].sum()), "mean_bps": float(1e4 * np.mean(p[m] / A["N"][m])) if n else float("nan"), "share_pos": float(np.mean(p[m] > 0)) if n else float("nan")}
    return out


def mnq_variants(W, A, rows, B, lo, hi, years=YEARS):
    """the hedge in whole MNQ (0.1 NQ): the basket's contracts rounded to a tenth, booked with the basket's hedge on the exit session; beside the same hedge unrounded. CHOICE: costs both ways -
    the registered 0.533 pts pro rata, and the micro's own $2.40 round trip (r11_risk.MICRO_RT)"""
    T = len(W.D.days)
    Ni = np.bincount(A["i"], weights=A["N"], minlength=T)
    with np.errstate(invalid="ignore", divide="ignore"):
        cont = Ni / (W.hedge.px * NQ_X)
    ok = np.isfinite(W.hedge.delta) & np.isfinite(cont) & (Ni > 0)
    base, cnt = series(A, name_pnl(A, W.hedge.hr, COST_BPS, hedged=False), rows, B.n)
    cu = np.where(ok, cont, 0.0)
    micros = np.round(cu * 10.0)
    dl = np.nan_to_num(W.hedge.delta)
    variants = {"unrounded": -cu * NQ_X * dl - cu * NQ_PTS * NQ_X,
                "rounded, 0.533 pts pro rata": -(micros / 10.0) * NQ_X * dl - (micros / 10.0) * NQ_PTS * NQ_X,
                "rounded, MNQ $2.40 a micro": -(micros / 10.0) * NQ_X * dl - micros * R11.MICRO_RT["NQ"]}
    out = {"avg_micros_a_night": float(micros[ok].mean()) if ok.any() else float("nan")}
    for nm, hp in variants.items():
        x = base + np.bincount(rows[np.flatnonzero(ok) + 1], weights=hp[ok], minlength=B.n)
        s = leg_stats(B, x, cnt, lo, hi, years)
        out[nm] = {k: s[k] for k in ("net", "roc", "sortino", "pf", "t")}
    return out


def reports(B, legs, W, R, rows, lo, hi, bps=COST_BPS):
    """cell U; the same names' next-day open-to-close return; the split by first-candle direction and by session t's close vs open; correlations; the hedge in whole MNQ; the cost / alternative-exit
    cells; the seat measure; gap-scan removals, unpriceable name-nights and unhedged nights by exit year. Everything on [lo, hi] (inclusive, by the booking date).
    -> (the report dict, H's daily series, name-nights booked per row, H's P&L per name-night, the mask of the name-nights booked in [lo, hi])"""
    D, A, hr = W.D, R.att, W.hedge.hr
    ys = YEARS if lo == WF0 else tuple(range(int(jy([lo])[0]), int(jy([hi])[0]) + 1))      # the July-June years the stretch touches (the nine WF years for WF)
    dt = D.days[A["j"]]
    inw = np.asarray((dt >= lo) & (dt <= hi))
    pH = name_pnl(A, hr, bps)
    xH, cnt = series(A, pH, rows, B.n)
    xU, _ = series(A, name_pnl(A, hr, bps, hedged=False), rows, B.n)
    cells = {"H": leg_stats(B, xH, cnt, lo, hi, ys), "U": leg_stats(B, xU, cnt, lo, hi, ys)}
    for b in STRESS_BPS:
        cells[f"H {b:g} bps"] = leg_stats(B, series(A, name_pnl(A, hr, b), rows, B.n)[0], cnt, lo, hi, ys)
    cells["H, -100% exits valued at 0%"] = leg_stats(B, series(A, name_pnl(A, hr, bps, alt0=True), rows, B.n)[0], cnt, lo, hi, ys)
    cells["U, -100% exits valued at 0%"] = leg_stats(B, series(A, name_pnl(A, hr, bps, hedged=False, alt0=True), rows, B.n)[0], cnt, lo, hi, ys)
    i, j, s = A["i"], A["j"], A["s"]
    with np.errstate(invalid="ignore", divide="ignore"):
        d5, dd = np.sign(D.C5[i, s] - D.O5[i, s]), np.sign(W.Cl[i, s] - D.Od[i, s])
        oc = W.Cl[j, s] / D.Od[j, s] - 1.0
        ov = A["Vx"] / A["N"] - 1.0
    m = inw & (A["K"] == NORMAL) & np.isfinite(oc)
    w, nan = A["Vx"][m], float("nan")
    r_oc = {"n": int(m.sum()), "overnight_mean_bps": float(1e4 * ov[m].mean()) if m.any() else nan, "open_to_close_mean_bps": float(1e4 * oc[m].mean()) if m.any() else nan,
            "open_to_close_value_weighted_bps": float(1e4 * (oc[m] * w).sum() / w.sum()) if m.any() else nan, "open_to_close_share_pos": float(np.mean(oc[m] > 0)) if m.any() else nan}
    yrs = defaultdict(Counter)                                                             # the counters of the nights that EXIT inside [lo, hi], by exit year
    for rw, c in R.cnt.items():
        if lo <= D.days[rw] <= hi:
            yrs[int(D.days[rw].year)].update(c)
    gl = [{"night": f"{D.days[gi]:%Y-%m-%d}", "symbol": str(D.syms[gs]), "R": gr, "naive_pnl_at_raw_R": gp} for (gi, gj, gs, gr, gp) in R.gaps if lo <= D.days[gj] <= hi]
    flagged = D.msplit.sum(axis=1)
    sel = np.asarray((D.days >= lo) & (D.days <= hi))
    fy = {int(y): int(flagged[np.asarray(D.days.year == y) & sel].sum()) for y in sorted(set(D.days[sel].year))}
    tn = sum(c.get("traded", 0) for c in yrs.values()) / max(sum(c.get("nights", 0) for c in yrs.values()), 1)
    return {"cells": cells, "names_per_night": tn, "open_to_close": r_oc, "by_first_candle": by_group(A, pH, d5, inw, ((1.0, "up"), (-1.0, "down"), (0.0, "flat"))),
            "by_session_close_vs_open": by_group(A, pH, dd, inw, ((1.0, "up"), (-1.0, "down"), (0.0, "flat"))),
            "corr_daily": {"H": corrs(B, xH, legs, lo, hi), "U": corrs(B, xU, legs, lo, hi)}, "seat": {"H": seat(B, xH, lo, hi), "U": seat(B, xU, lo, hi)},
            "mnq_rounding": mnq_variants(W, A, rows, B, lo, hi, ys),
            "gap_scan": {"flagged_symbol_days_by_year": fy, "attention_nights_removed_n": len(gl), "attention_nights_removed": gl[:200]},
            "counts_by_exit_year": {y: dict(c) for y, c in sorted(yrs.items())}}, xH, cnt, pH, inw


# ------------------------------------------------------------------ printing
def row(name, s):
    return (f"{name:<28} stock-nights {s['stock_nights']:>6,} nights {s['nights']:>5,} net ${s['net']:>11,.0f} ROC@30k {s['roc']:>8.1f} PF {s['pf']:>5.2f} t {s['t']:>5.2f} "
            f"Sortino {s['sortino']:>6.2f} years+ {s['years_pos']}")


def print_reports(rep):
    print("  " + row("H (hedged, 5 bps)", rep["cells"]["H"]))
    print("  " + row("U (unhedged, report)", rep["cells"]["U"]))
    for nm, c in rep["cells"].items():
        if nm not in ("H", "U"):
            print(f"  {nm:<34} net ${c['net']:>11,.0f} ROC@30k {c['roc']:>8.1f}")
    print("  H net by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}: ${v:,.0f}" for y, v in rep["cells"]["H"]["by_year"].items()) + f"; {rep['names_per_night']:.1f} names a night on average")
    o = rep["open_to_close"]
    print(f"  same names, next day open->close ({o['n']:,} name-nights priced at the open): mean {o['open_to_close_mean_bps']:+.1f} bps (value weighted {o['open_to_close_value_weighted_bps']:+.1f}, "
          f"{o['open_to_close_share_pos']:.0%} up) vs overnight {o['overnight_mean_bps']:+.1f} bps")
    for key, lab in (("by_first_candle", "first 5-min candle"), ("by_session_close_vs_open", "session t close vs open")):
        if any(v["n"] for v in rep[key].values()):
            print(f"  H by {lab}: " + "; ".join(f"{k} n {v['n']:,} net ${v['net']:,.0f} mean {v['mean_bps']:+.1f} bps" for k, v in rep[key].items() if v["n"]))
    print("  daily correlation of H with #463 and its legs: " + ", ".join(f"{k} {v:+.3f}" for k, v in rep["corr_daily"]["H"].items()))
    sh = rep["seat"]["H"]
    if sh:
        print(f"  seat (H): {len(sh['qualifying'])} qualifying drawdowns, {sh['dd_weeks']} DD weeks, rho_dd {sh['rho_dd']:+.3f}, DO {sh['DO']:+.3f} (+ = it earns while the book falls)")
    mq = rep["mnq_rounding"]
    print(f"  hedge in whole MNQ (avg {mq['avg_micros_a_night']:.1f} micros a night): " + "; ".join(f"{k} ROC {v['roc']:.1f}" for k, v in mq.items() if isinstance(v, dict)))
    g = rep["gap_scan"]
    print(f"  gap scan: attention-set nights removed {g['attention_nights_removed_n']}; flagged symbol-days by year " + " ".join(f"{y}:{n}" for y, n in g["flagged_symbol_days_by_year"].items()))
    keys = ("top20", "price", "adv", "shares", "factor", "gap", "cut", "traded", "later", "none", "split_nights", "unhedged_nights", "gap_universe")
    print("  by exit year: " + " / ".join(keys) + " (top-20 names; dropped for price, ADV$, shares, factor; gap scan; unresolved at the cut; traded; later-open exits; -100% exits; split nights; "
          "unhedged nights; the gap scan's removals in the whole tradable universe)")
    for y, c in rep["counts_by_exit_year"].items():
        print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in keys))


# ------------------------------------------------------------------ the pipeline shared by Stage A and Stage B
def build(D, t_end, nreps):
    """the re-read arrays, the NQ hedge and every night on a Data already cut at t_end (S.LB0 for Stage A, S.END for Stage B) -> (World, nights result, NQ master rows)"""
    t0 = time.time()
    Cl, adv, F = load_arrays(D, t_end)
    nq, meta = load_nq(t_end)
    pr = hedge_prints(nq)
    del nq
    W = World(D, Cl, adv, F, hedge_returns(D.days, pr))
    print(f"arrays + hedge ready ({time.time() - t0:.0f}s); NQ prints on {int(pr['c_raw'].notna().sum()):,} sessions, fallback bars on {int(pr['close_fb'].sum())} closes / {int(pr['open_fb'].sum())} opens", flush=True)
    t0 = time.time()
    R = run_nights(W, nreps, SEED)
    print(f"nights done ({time.time() - t0:.0f}s): {int((R.kn > 0).sum()):,} nights with names, {len(R.att['i']):,} name-nights" + (f", {nreps} null draws" if nreps else ""), flush=True)
    return W, R, meta


def load_463():
    """BOOK #463's rule-U records (r11_risk's build) -> (Book, legs)"""
    legs = R11.load_json("build.json")["legs"]
    return R11.load_book("U", legs), legs


def judge_a(h, cov, p95, net_stress):
    R = RULES
    return {f"stock-nights>={R['n']}": h["stock_nights"] >= R["n"], f"open5 sessions>={R['cov']:.0%}": cov["share"] >= R["cov"], f"ROC@30k>={R['roc']:g}": h["roc"] >= R["roc"],
            f"PF>={R['pf']:g}": h["pf"] >= R["pf"], f"t>={R['t']:g}": h["t"] >= R["t"], "ROC>null p95": (h["roc"] > p95) if R["null"] else True,
            f"net>0 at {R['stress_bps']:g} bps": (net_stress > 0) if R["stress"] else True, "profitable without its best 1% of nights": (h["net_ex_best"] > 0) if R["exbest"] else True,
            f"positive in >={R['years']} of 9 years": h["years_pos"] >= R["years"]}


def stage_a():
    if os.path.exists(os.path.join(OUT, "attn_stageB_READ.flag")):                         # CHOICE: once the lockbox has been read Stage A is frozen (a re-run could change c* or the verdict after the fact)
        refuse("Stage A refused: Stage B has already read the lockbox - Stage A is frozen (attn_stageB_READ.flag)")
    pok = prereg_ok()
    B, legs = load_463()                                                                   # the book first: cheap, and a book that does not reproduce stops everything
    bk = book_check(B, WF0, PRE_END, BOOK_WF)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage A refused: the #463 records do not reproduce its WF numbers - fix the input first (nothing computed)")
    print("order of reads: SIPORB's Stage A is " + ("on file" if os.path.exists(os.path.join(S.OUT, "siporb_stageA.json")) else "NOT on file yet - ATTN's Stage A is meant to run after it"))
    t0 = time.time()
    D = load_data(S.LB0)                                                                   # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    cov, cy = coverage(D, WF0, PRE_END), S.coverage_by_year(D)
    print(f"open5 present on {cov['with_open5']:,} of {cov['sessions']:,} WF sessions ({cov['share']:.1%}; needs >= {RULES['cov']:.0%}); SIPORB's name-day coverage by year (report): "
          + "  ".join(f"{y}: {v['share']:.1%}" for y, v in cy.items()))
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok, **stamp(), "judged": False, "A2": None, "book_check": bk, "coverage": cov, "name_day_coverage_by_year": cy}
    if not cov["share"] >= RULES["cov"]:
        print("Stage A is NOT judged: the 09:30 bar files are missing for too many WF sessions - run SIPORB's open5 pull first (numbers in attn_stageA.json)")
        dump(out, "attn_stageA.json")
        return out
    slim(D)
    W, R, out["nq_masters"] = build(D, S.LB0, NREP)
    rows = book_rows(B, D)
    rep, xH, cnt, pH, inw = reports(B, legs, W, R, rows, WF0, PRE_END)
    h = rep["cells"]["H"]
    k = B.mask(WF0, PRE_END)
    accB = np.zeros((NREP, B.n))
    accB[:, rows] = R.acc
    nul = np.array([R11.stats(accB[r][k], B.index[k])["roc"] for r in range(NREP)])
    fin = nul[np.isfinite(nul)]
    p95 = float(np.percentile(fin, 95)) if len(fin) else float("nan")
    null = {"draws": NREP, "seed": SEED, "finite": int(len(fin)), "p50": float(np.percentile(fin, 50)) if len(fin) else float("nan"), "p95": p95, "mean": float(fin.mean()) if len(fin) else float("nan"),
            "real_percentile": float(np.mean(fin < h["roc"]) * 100) if len(fin) else float("nan")}
    chk = judge_a(h, cov, p95, rep["cells"][f"H {RULES['stress_bps']:g} bps"]["net"])
    ok = all(chk.values())
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({cov['sessions']:,} sessions)")
    print_reports(rep)
    print(f"  random-pick null ({NREP} draws, seed {SEED}): median ROC {null['p50']:.1f}, 95th percentile {p95:.1f}, mean {null['mean']:.1f}; H sits at the {null['real_percentile']:.0f}th percentile")
    print("  Stage A checks: " + ", ".join(kk + (" ok" if v else " FAIL") for kk, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
    by_c = book_add(B, xH, WF0, PRE_END)                                                   # CHOICE: A2 is computed (informational) even when Stage A failed; a pass needs both
    cb = best_c({c: v["roc"] for c, v in by_c.items()})
    base = R11.stats(B.raw[k], B.index[k])
    a2ok = bool(by_c[cb]["roc"] >= RULES["a2_roc"] and by_c[cb]["sortino"] >= RULES["a2_sort"])
    for c, v in by_c.items():
        print(f"  #463 + H x{c:g}: WF ROC@30k {v['roc']:.2f} Sortino {v['sortino']:.3f} net ${v['net']:,.0f}")
    print(f"A2: #463 alone WF ROC@30k {base['roc']:.2f}; best c x{cb:g} gives {by_c[cb]['roc']:.2f} (needs {RULES['a2_roc']:.4f}) Sortino {by_c[cb]['sortino']:.3f} (needs {RULES['a2_sort']}) -> "
          f"{'PASS' if a2ok else 'FAIL'}" + ("" if ok else " (Stage A failed: informational)"))
    out.update({"judged": True, "stageA": {"H": h, "null": null, "checks": chk, "PASS": bool(ok)}, "A2": {"c": cb, "pass": bool(a2ok), "by_c": {f"{c:g}": v for c, v in by_c.items()},
                "book_wf": {"roc": base["roc"], "sortino": base["sort"]}}, "reports": rep})
    dump(out, "attn_stageA.json")
    if ok and a2ok:
        print(f"ATTN Stage A: PASS and A2: PASS - the hedged overnight basket clears every bar and adds to #463 at c = x{cb:g} (frozen). Stage B may run once, after SIPORB's lockbox has been read.")
    elif ok:
        print("ATTN Stage A: PASS but A2: FAIL - the leg is real on its own but does not lift #463 enough; ATTN stops here, the lockbox stays sealed.")
    else:
        print("ATTN Stage A: FAIL (" + ", ".join(kk for kk, v in chk.items() if not v) + ") - ATTN is dead; the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


def siporb_state():
    """'read' = SIPORB's lockbox has been read (its READ flag); 'dead' = SIPORB's Stage A or A2 recorded a failing verdict, so it never reaches its lockbox (an A2 that 'could not be judged'
    carries an error key and is not a verdict); None = neither yet"""
    if os.path.exists(os.path.join(S.OUT, "siporb_stageB_READ.flag")):
        return "read"
    p = os.path.join(S.OUT, "siporb_stageA.json")
    if os.path.exists(p):
        try:
            sa = json.load(open(p))
        except Exception:
            return None
        if sa.get("judged") is True:
            if (sa.get("stageA") or {}).get("PASS") is False:
                return "dead"
            a2 = sa.get("A2")
            if isinstance(a2, dict) and a2.get("pass") is False and "error" not in a2:
                return "dead"
    return None


def stage_b():
    pa = os.path.join(OUT, "attn_stageA.json")
    sa = json.load(open(pa)) if os.path.exists(pa) else {}
    if not (sa.get("judged") is True and (sa.get("stageA") or {}).get("PASS") is True and (sa.get("A2") or {}).get("pass") is True):
        refuse("Stage B refused: no Stage A + A2 pass on file - the lockbox stays sealed.")
    flag = os.path.join(OUT, "attn_stageB_READ.flag")
    if os.path.exists(flag):
        refuse("Stage B refused: the lockbox was already read once (attn_stageB_READ.flag)")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    c = float(sa["A2"]["c"])
    if c not in CS:
        refuse(f"Stage B refused: the frozen c {c} is not one of {CS} (lockbox NOT read)")
    state = siporb_state()
    if state is None:
        refuse("Stage B refused: SIPORB's lockbox has not been read and SIPORB has not failed before it - ATTN's sealed year opens only after SIPORB's (order of reads); lockbox NOT read")
    print(f"order of reads: SIPORB is '{state}'")
    B, legs = load_463()                                                                   # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    D = load_data(S.END)
    cov = coverage(D, LB0, LB1)
    print(f"open5 present on {cov['with_open5']:,} of {cov['sessions']:,} lockbox sessions ({cov['share']:.1%}; needs >= {RULES['cov']:.0%})")
    if not cov["share"] >= RULES["cov"]:     # CHOICE: the Stage A gate applied to the lockbox BEFORE the one read (SIPORB's Stage B does the same)
        refuse("Stage B refused: the 09:30 bar files are missing for too many lockbox sessions - fix the pull first (lockbox NOT read)")
    slim(D)
    W, R, meta = build(D, S.END, 0)                                                        # no null in Stage B
    rows = book_rows(B, D)
    wf, a0 = reports(B, legs, W, R, rows, WF0, PRE_END)[0]["cells"]["H"], sa["stageA"]["H"]    # CHOICE: Stage A's WF numbers must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    print(f"WF re-read on Stage B's data: stock-nights {wf['stock_nights']:,} (Stage A {a0['stock_nights']:,}), H net ${wf['net']:,.0f} (Stage A ${a0['net']:,.0f}); only the nights whose exit window Stage A's cut truncated may differ")
    if abs(wf["net"] - a0["net"]) > max(50.0, 0.01 * abs(a0["net"])) or abs(wf["stock_nights"] - a0["stock_nights"]) > max(5, 0.02 * a0["stock_nights"]):
        refuse("Stage B refused: the WF numbers do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    rep, xH, cnt, pH, inw = reports(B, legs, W, R, rows, LB0, LB1)                         # CHOICE (r10_spread's order): the whole LB result is computed, nothing shown, BEFORE the flag
    by_c = book_add(B, xH, LB0, LB1)
    leg = rep["cells"]["H"]
    best = float(pH[inw].max()) if inw.any() else float("nan")
    r = by_c[c]
    chk = {f"book ROC@30k>={RULES['b_roc']:g}": bool(r["roc"] >= RULES["b_roc"]), f"book Sortino>={RULES['b_sort']:g}": bool(r["sortino"] >= RULES["b_sort"]),
           f"leg stock-nights>={RULES['b_n']}": bool(leg["stock_nights"] >= RULES["b_n"]), "leg net>0": bool(leg["net"] > 0),
           "leg net>0 without its best stock-night": bool(leg["net"] - best > 0)}
    ok = all(chk.values())
    text = json.dumps({"c": c, "siporb": state, "book_check": bk, "coverage": cov, "nq_masters": meta, "H": leg, "book_add": {f"{k:g}": v for k, v in by_c.items()}, "best_stock_night": best,
                       "checks": chk, "pass": bool(ok), "reports": rep, **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                    # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once)")
        print(f"  #463 + H x{c:g}: LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f}; the leg's best stock-night ${best:,.0f}, net without it ${leg['net'] - best:,.0f}")
        print_reports(rep)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print("ATTN Stage B: " + ("PASS - a written forward paper shadow (Webull paper) is the next step, with its own bar and an owner call." if ok else "FAIL - ATTN is dead; ledger + memory."))
    with open(flag, "x") as f:                                                             # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "attn_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ selftest: hand-made worlds, no files, no data
def mini_world():
    """16 sessions (Mon 2024-03-04 on: Fri -> Mon nights are rows 4 -> 5, 9 -> 10, 14 -> 15) x 9 names built by hand; every name passes P with RV >= 1, so the top-20 is all nine in this order.
    AAA steady (+1% overnight); SPL a 2-for-1 split between rows 2 and 3 (raw 100 -> 51, adjusted 50 -> 51: the true move is +2%); GAP flagged by the gap scan at row 3; LAT no bar at rows 3 and 4,
    open 31 at row 5; NON no bar from row 3 on; LOW 09:35 price 4.90; THN ADV$ 4.9m; BIG a $6,000 close (no whole share); NOF no split factor at row 2"""
    T, names = 16, ["AAA", "SPL", "GAP", "LAT", "NON", "LOW", "THN", "BIG", "NOF"]
    n = len(names)
    days = pd.bdate_range("2024-03-04", periods=T)
    Od, Cl, F, adv, C5 = np.full((T, n), 50.5), np.full((T, n), 50.0), np.ones((T, n)), np.full((T, n), 6e6), np.full((T, n), 50.0)
    Cl[:3, 1], Cl[3:, 1], Od[:3, 1], Od[3, 1], Od[4:, 1], F[:3, 1] = 100.0, 50.0, 100.0, 51.0, 50.0, 2.0
    Cl[:, 2], Od[:, 2], Od[3, 2] = 20.0, 20.0, 80.0
    Cl[:, 3], Od[:, 3], Od[3:5, 3], Od[5, 3] = 30.0, 30.5, np.nan, 31.0
    Cl[3:5, 3], F[3:5, 3] = np.nan, np.nan
    Cl[:, 4], Od[:, 4] = 40.0, 40.5
    Od[3:, 4], Cl[3:, 4], F[3:, 4] = np.nan, np.nan, np.nan
    Cl[:, 5], Od[:, 5], C5[:, 5] = 6.0, 6.0, 4.9
    adv[:, 6] = 4.9e6
    Cl[:, 7], Od[:, 7], C5[:, 7] = 6000.0, 6000.0, 6000.0
    F[2, 8] = np.nan
    msplit = np.zeros((T, n), bool)
    msplit[3, 2] = True
    D = SimpleNamespace(days=days, syms=np.array(names), P=np.ones((T, n), bool), RV=np.tile(3.0 - 0.1 * np.arange(n), (T, 1)), C5=C5, O5=C5.copy(), Od=Od, msplit=msplit,
                        o5days=[f"{d:%Y-%m-%d}" for d in days])
    D.top20 = lambda i: S.Data.top20(D, i)
    return World(D, Cl, adv, F, SimpleNamespace(hr=np.zeros(T), delta=np.zeros(T), px=np.full(T, 20000.0)))


def only_row(W, i):
    """the mini world with P true only on session row i, so only that night has an attention set"""
    W.D.P = np.zeros_like(W.D.P)
    W.D.P[i] = True
    return W


def selftest():
    """rules on hand-made worlds: constants as registered, split-safe P&L, gap-scan removal from the set AND the null, the unpriceable rule, the hedge sign and its per-name split, the null's draws,
    stamping on the exit day across a weekend, the statistics (ROC / PF / t / best 1% / July-June breadth), the c* tie rule, the seat measure, the NQ prints, the cut"""
    assert (NREP, SEED, SLOT, PX_MIN, ADV_MIN, COST_BPS, STRESS_BPS, EXIT_WINDOW, NQ_X, NQ_PTS, CS) == (500, 20261004, 5000.0, 5.0, 5e6, 5.0, (10.0, 20.0), 10, 20.0, 0.533, (0.5, 1.0, 2.0))
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX) and YEARS == tuple(range(2016, 2025))
    assert (BOOK_WF, BOOK_LB, TOL) == ((93.81, 3.816), (155.54, 4.15), (0.006, 0.0006)) and abs(RULES["a2_roc"] - 98.5005) < 1e-9 and RULES["a2_sort"] == 3.816 and RULES["nw_lags"] == 5
    assert (RULES["n"], RULES["cov"], RULES["roc"], RULES["pf"], RULES["t"], RULES["stress_bps"], RULES["best_pct"], RULES["years"], RULES["b_n"], RULES["b_roc"], RULES["b_sort"]) == \
        (100, 0.98, 15.0, 1.10, 2.0, 10.0, 1, 6, 50, 155.54, 4.15) and CHECK_BOOK is True and (SRC_RAW, SRC_ADJ) == ("db_noadj_rth", "db_adj_rth")
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        assert prereg_ok() is True and len(stamp()["harness_sha256"]) == 64 and "2023-11-24" in stamp()["early_close"], "the committed pre-registration sits next to this file"
    # 1. one night, every rule: split-safe exit across a 2-for-1 split, the gap flag, later open, no open in the window, the four drops
    W = only_row(mini_world(), 2)
    nt = night(W, 2)
    assert nt.elig.tolist() == [True, True, False, True, True, False, False, False, False], nt.elig.tolist()
    assert nt.why.tolist() == [0, 0, 5, 0, 0, 1, 2, 3, 4], nt.why.tolist()
    assert nt.N[0] == 5000.0 and nt.Vx[0] == 5050.0 and nt.K[0] == NORMAL and nt.J[0] == 3, "100 shares x 50.5"
    assert nt.N[1] == 5000.0 and abs(nt.Vx[1] - 5100.0) < 1e-9 and nt.K[1] == NORMAL, "2-for-1: 50 shares x 51 x F_t 2 / F_t+1 1 = +2%, the true move (a naive book shows -49%)"
    assert nt.K[3] == LATER and nt.J[3] == 5 and nt.N[3] == 4980.0 and abs(nt.Vx[3] - 166 * 31.0) < 1e-9, "no open at t+1, t+2: the open of t+3 (166 shares x 31), booked on that day"
    assert nt.K[4] == NONE and nt.Vx[4] == 0.0 and nt.J[4] == 3 and nt.N[4] == 5000.0, "no open in sessions t+1 .. t+11: -100%, booked on t+1"
    assert nt.K[2] == NORMAL and not nt.elig[2] and nt.why[2] == 5, "a flagged gap symbol-day is out"
    assert nt.why[7] == 3 and np.isnan(nt.N[7]) and nt.why[8] == 4 and nt.why[6] == 2 and nt.why[5] == 1, "no whole share, no split factor, ADV$ under $5m, 09:35 price under $5"
    pool = np.flatnonzero(nt.elig)                                                                   # the null's pool is the tradable universe: the flagged name is not in it
    assert 2 not in pool.tolist() and pool.tolist() == [0, 1, 3, 4]
    d = draw_subsets(np.random.default_rng(1), len(pool), 3, 200)
    assert d.shape == (200, 3) and (d >= 0).all() and (d < 4).all() and all(len(set(r)) == 3 for r in d.tolist()) and (draw_subsets(np.random.default_rng(1), 4, 3, 200) == d).all(), "no repeats, seeded"
    fr = np.bincount(draw_subsets(np.random.default_rng(2), 10, 3, 60000).ravel(), minlength=10) / 60000.0
    assert np.abs(fr - 0.3).max() < 0.01, fr                                                         # uniform: every name is in 3 of 10 draws
    W2 = only_row(mini_world(), 14)                                                                  # a night whose window runs past the stage's data: unresolved (CUT), out of the set and the pool
    W2.D.Od[15, 0] = np.nan
    nt2 = night(W2, 14)
    assert nt2.why[0] == 6 and nt2.K[0] == CUT and not nt2.elig[0] and nt2.elig[1] and nt2.K[1] == NORMAL and nt2.J[1] == 15, "t+1 = the last session: AAA has no open there and no window left"
    # 2. the whole run on that night: attention set, hedge, null (k = pool, so every draw is the attention set), the unhedged night
    W.hedge.hr[2] = 0.002
    R = run_nights(W, nreps=20, seed=7)
    A = R.att
    assert A["i"].tolist() == [2, 2, 2, 2] and A["s"].tolist() == [0, 1, 3, 4] and A["j"].tolist() == [3, 3, 5, 3] and A["K"].tolist() == [NORMAL, NORMAL, LATER, NONE]
    assert R.kn.tolist() == [0, 0, 4] + [0] * 13 and dict(R.cnt[3]) == {"top20": 9, "price": 1, "adv": 1, "shares": 1, "factor": 1, "gap": 1, "cut": 0, "traded": 4, "nights": 1, "later": 1, "none": 1,
                                                                          "split_nights": 1, "unhedged_nights": 0, "gap_universe": 1}, dict(R.cnt[3])
    pn = lambda N_, V_, hr_: (V_ - N_) - 5e-4 * (N_ + V_) + N_ * hr_
    want = np.array([pn(5000.0, 5050.0, .002), pn(5000.0, 5100.0, .002), pn(4980.0, 166 * 31.0, .002), pn(5000.0, 0.0, .002)])
    assert np.allclose(name_pnl(A, W.hedge.hr, 5.0), want) and np.allclose(name_pnl(A, W.hedge.hr, 5.0, hedged=False), want - np.array([5000.0, 5000.0, 4980.0, 5000.0]) * .002)
    assert np.isclose(name_pnl(A, W.hedge.hr, 5.0, alt0=True)[3], pn(5000.0, 5000.0, .002)) and np.isclose(name_pnl(A, W.hedge.hr, 5.0)[3], -5000.0 - 2.5 + 10.0), "-100%: lose the position + 5 bps on entry"
    assert len(R.gaps) == 1 and R.gaps[0][2] == 2 and R.gaps[0][1] == 3 and abs(R.gaps[0][3] - 4.0) < 1e-12 and abs(R.gaps[0][4] - 5000.0 * 3.0) < 1e-9, "the removed night is reported at its raw R = 80 / 20"
    rows = np.arange(16)                                                                             # stand-in for the #463 index: row = session row
    x, cn = series(A, name_pnl(A, W.hedge.hr, 5.0), rows, 16)
    assert cn.tolist() == [0, 0, 0, 3, 0, 1] + [0] * 10 and np.isclose(x[3], want[0] + want[1] + want[3]) and np.isclose(x[5], want[2]) and x[2] == 0.0
    assert np.allclose(R.acc, x[None, :]), "with k = the pool every draw IS the attention set: the null and the attention path price a night the same way"
    W.hedge.hr[2] = np.nan
    R = run_nights(W, nreps=0)
    assert R.cnt[3]["unhedged_nights"] == 1 and np.allclose(name_pnl(R.att, W.hedge.hr, 5.0), name_pnl(R.att, W.hedge.hr, 5.0, hedged=False)), "no NQ print: unhedged, counted"
    R = run_nights(W, nreps=5, seed=7)
    xu, _ = series(R.att, name_pnl(R.att, W.hedge.hr, 5.0, hedged=False), rows, 16)
    assert np.isfinite(R.acc).all() and np.allclose(R.acc, xu[None, :]), "an unhedged night is unhedged in the null too (no NaN leaks into a draw)"
    # 3. stamping on the exit day across a weekend: the night Friday row 4 -> Monday row 5 is booked on Monday
    W3 = only_row(mini_world(), 4)
    B3 = SimpleNamespace(index=pd.DatetimeIndex(["2024-03-01"]).append(W3.D.days), n=17)
    r3 = book_rows(B3, W3.D)
    R3 = run_nights(W3, 0)
    x3, c3 = series(R3.att, name_pnl(R3.att, W3.hedge.hr, 5.0), r3, 17)
    assert W3.D.days[4].day_name() == "Friday" and W3.D.days[5].day_name() == "Monday" and (R3.att["i"] == 4).all() and (R3.att["j"] == 5).all() and len(R3.att["i"]) == 4
    assert c3[1 + 5] == 4 and c3[1 + 4] == 0 and x3[1 + 4] == 0.0 and B3.index[1 + 5] == TS("2024-03-11"), "stamped on Monday"
    # 4. the hedge: sign, magnitude, missing prints, and the per-name decomposition equals the basket hedge
    days = pd.DatetimeIndex(["2024-03-04", "2024-03-05", "2024-03-06"])
    pr = pd.DataFrame({"o_adj": [14990.0, 14950.0, 15100.0], "c_adj": [15000.0, np.nan, 15050.0], "c_raw": [20000.0, np.nan, 20050.0]}, index=days)
    h = hedge_returns(days, pr)
    assert h.delta[0] == -50.0 and h.px[0] == 20000.0 and np.isclose(h.hr[0], -(-50.0 + 0.533) / 20000.0) and h.hr[0] > 0, "NQ down 50 overnight (roll-corrected): the short hedge earns"
    assert np.isnan(h.hr[1]) and np.isnan(h.hr[2]), "no 16:00 print on session 1; the last session has no night"
    pr2 = pr.copy(); pr2.loc[days[1], ["o_adj", "c_adj", "c_raw"]] = [np.nan, 14960.0, 19960.0]
    h2 = hedge_returns(days, pr2)
    assert np.isnan(h2.hr[0]) and np.isfinite(h2.hr[1]), "no 09:30 print on session 1: the night before it is unhedged"
    up = hedge_returns(days[:2], pd.DataFrame({"o_adj": [0.0, 15100.0], "c_adj": [15000.0, 0.0], "c_raw": [20000.0, 0.0]}, index=days[:2]))
    assert up.delta[0] == 100.0 and up.hr[0] < 0 and np.isclose(up.hr[0], -100.533 / 20000.0), "NQ up 100: the hedge loses, and the cost is on top"
    Ns = np.array([5000.0, 4980.0, 4990.0, 5010.0])
    contracts = Ns.sum() / (20000.0 * 20.0)
    basket = -contracts * 20.0 * h.delta[0] - contracts * 0.533 * 20.0
    assert np.isclose(basket, (Ns * h.hr[0]).sum()) and np.isclose(basket, contracts * (1000.0 - 10.66)), "the basket's hedge = the sum of the names' cost shares"
    # 5. NQ prints: the 15:55 / 12:55 close, the fallbacks, no extended-hours print on a half day
    def mk(spec):
        ts, o, c = [], [], []
        for day, hms in spec.items():
            for hm in hms:
                ts.append(TS(day) + pd.Timedelta(minutes=hm)); o.append(1000.0 + hm); c.append(1001.0 + hm)
        return pd.DataFrame({"open": o, "close": c}, index=pd.DatetimeIndex(ts).tz_localize("US/Eastern"))
    full, half = list(range(570, 960, 5)), list(range(570, 780, 5)) + [840]
    pt = nq_prints(mk({"2024-03-04": full, "2024-11-29": half, "2024-03-05": [m for m in full if m != 955], "2024-03-06": [m for m in full if m != 570],
                       "2024-03-07": list(range(600, 905, 5)), "2024-03-08": [m for m in full if m < 930]}))
    assert pt.loc["2024-03-04", "open"] == 1570.0 and pt.loc["2024-03-04", "close"] == 1956.0 and pt.loc["2024-03-04", "close_hm"] == 955 == pt.loc["2024-03-04", "last"]
    assert pt.loc["2024-11-29", "close"] == 1776.0 and pt.loc["2024-11-29", "close_hm"] == 775 == pt.loc["2024-11-29", "last"], "half day: the 12:55 bar, not the 14:00 print"
    assert pt.loc["2024-03-05", "close"] == 1951.0 and pt.loc["2024-03-05", "close_hm"] == 950, "no 15:55 bar: the last bar from 15:30"
    assert pt.loc["2024-03-06", "open"] == 1575.0 and pt.loc["2024-03-06", "open_hm"] == 575, "no 09:30 bar: the first bar before 10:00"
    assert TS("2024-03-07") not in pt.index, "no bar before 10:00 and none from 15:30: the session has no print at all"
    assert np.isnan(pt.loc["2024-03-08", "close"]) and pt.loc["2024-03-08", "open"] == 1570.0, "the last bar is 15:25: too early to stand in for the 16:00 print"
    # 6. statistics on a hand-made stretch: [100, -50, 0, 200, -150, 50, 0, -50]; nights = rows with a name-night booked
    ix = pd.bdate_range("2017-01-02", periods=8)
    Bs = SimpleNamespace(index=ix, n=8, mask=lambda lo, hi: np.asarray((ix >= lo) & (ix <= hi)), raw=np.zeros(8))
    xs, cs = np.array([100.0, -50.0, 0.0, 200.0, -150.0, 50.0, 0.0, -50.0]), np.array([2, 1, 0, 1, 3, 1, 0, 1])
    s = leg_stats(Bs, xs, cs, ix[0], ix[-1])
    yrs = (ix[-1] - ix[0]).days / 365.25
    assert s["stock_nights"] == 9 and s["nights"] == 6 and abs(s["net"] - 100) < 1e-9 and abs(s["max_dd"] - 150) < 1e-9 and abs(s["roc"] - 30 * (100 / yrs) / 150) < 1e-9, s
    assert abs(s["pf"] - 350 / 250) < 1e-12 and abs(s["sortino"] - (100 / 8) / math.sqrt(27500 / 8) * math.sqrt(252)) < 1e-9 and s["best_n"] == 1 and abs(s["net_ex_best"] - (100 - 200)) < 1e-9, s
    assert s["years_pos"] == 1 and abs(s["by_year"][2016] - 100) < 1e-9 and s["by_year"][2017] == 0.0, "Jan 2017 is in the July-June year 2016-17"
    rr = np.random.default_rng(3).normal(5.0, 40.0, 300)                                                # Newey-West t against a plain-python Bartlett estimate, 5 lags
    e = rr - rr.mean()
    Sv = float(e @ e) + sum(2 * (1 - L / 6.0) * float(e[L:] @ e[:-L]) for L in range(1, 6))
    assert abs(nw_t(rr) - rr.mean() * len(rr) / math.sqrt(Sv)) < 1e-9 and math.isnan(nw_t([1.0, 2.0])) and math.isnan(nw_t(np.ones(50)))
    # 7. the best 1% of nights: ceil(0.01 x nights), in integers
    assert [ceil_pct(n, 1) for n in (0, 1, 99, 100, 101, 250, 700, 701)] == [0, 1, 1, 1, 2, 3, 7, 8]
    ixl = pd.bdate_range("2020-01-01", periods=250)
    Bl = SimpleNamespace(index=ixl, n=250, mask=lambda lo, hi: np.asarray((ixl >= lo) & (ixl <= hi)))
    xl = np.random.default_rng(4).normal(1.0, 10.0, 250)
    sl = leg_stats(Bl, xl, np.ones(250, int), ixl[0], ixl[-1])
    assert sl["best_n"] == 3 and abs(sl["net_ex_best"] - (xl.sum() - np.sort(xl)[-3:].sum())) < 1e-9 and sl["nights"] == 250
    # 8. breadth on July-June years
    dts = pd.DatetimeIndex(["2017-06-30", "2017-07-03", "2018-06-29", "2018-07-02", "2019-01-02"])
    nets, npos = breadth(np.array([5.0, 7.0, -9.0, 3.0, 1.0]), dts)
    assert nets[2016] == 5.0 and nets[2017] == -2.0 and nets[2018] == 4.0 and npos == 2 and len(nets) == 9, nets
    assert breadth(np.array([5.0, -5.0]), pd.DatetimeIndex(["2017-07-03", "2018-06-29"]))[1] == 0, "a year that nets exactly 0 is not positive"
    assert jy(pd.DatetimeIndex(["2016-07-01", "2017-06-30", "2025-06-27"])).tolist() == [2016, 2016, 2024]
    # 9. c* tie rule: the best WF book ROC, ties -> the smaller c, NaN never wins
    nan = float("nan")
    assert best_c({0.5: 100.0, 1.0: 100.0, 2.0: 99.0}) == 0.5 and best_c({0.5: 90.0, 1.0: 100.0, 2.0: 100.0}) == 1.0 and best_c({0.5: nan, 1.0: 80.0, 2.0: nan}) == 1.0
    assert best_c({0.5: nan, 1.0: nan, 2.0: nan}) == 0.5 and best_c({0.5: 1.0, 1.0: 2.0, 2.0: 3.0}) == 2.0
    # 10. the seat measure: 8 ISO weeks, odd weeks +6 a day, even weeks -4 / -3 / -2 / -1 a day (drawdowns 20 / 15 / 10 / 5: the last is under 1/3 of 20); the leg = -0.5 x the book in weeks 2, 4, 6
    ix8 = pd.bdate_range("2024-01-01", periods=40)
    bk8 = np.concatenate([np.full(5, 6.0) if w % 2 == 0 else np.full(5, -[4.0, 3.0, 2.0, 1.0][w // 2]) for w in range(8)])
    lg8 = np.where(np.isin(np.arange(40) // 5, (1, 3, 5)), -0.5 * bk8, 0.25)
    B8 = SimpleNamespace(index=ix8, n=40, raw=bk8, mask=lambda lo, hi: np.asarray((ix8 >= lo) & (ix8 <= hi)))
    st8 = seat(B8, lg8, ix8[0], ix8[-1])
    assert len(st8["qualifying"]) == 3 and st8["dd_days"] == 15 and st8["dd_weeks"] == 3 and abs(st8["rho_dd"] + 1.0) < 1e-9 and abs(st8["DO"] - 0.5) < 1e-9 and abs(st8["deepest"] - 20.0) < 1e-9, st8
    assert seat(SimpleNamespace(index=ix8[:5], raw=np.ones(5), mask=lambda lo, hi: np.ones(5, bool)), np.ones(5), ix8[0], ix8[-1]) is None, "no drawdown, no seat"
    bk2 = np.array([5.0, 5, 5, 5, 5, -3, -3, 0, 0, 0, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5])                    # a drawdown that spans only 2 days of its week is not a DD week
    B2 = SimpleNamespace(index=ix8[:20], raw=bk2, mask=lambda lo, hi: np.ones(20, bool))
    st2 = seat(B2, np.ones(20), ix8[0], ix8[19])
    assert st2["dd_days"] == 2 and st2["dd_weeks"] == 0 and math.isnan(st2["rho_dd"]) and abs(st2["DO"] - 2 / 6.0) < 1e-9, st2
    # 11. the cut: no date on/after the stage's cut can enter
    assert_cut("x", pd.DatetimeIndex(["2025-06-26", "2025-06-27"]), S.LB0)
    assert_cut("nq", pd.DatetimeIndex(["2025-06-27 15:55"]).tz_localize("US/Eastern"), S.LB0)
    for bad in ("2025-06-30", "2026-01-02"):
        try:
            assert_cut("x", pd.DatetimeIndex(["2025-06-27", bad]), S.LB0); raise AssertionError("a date on/after the cut must be refused")
        except SystemExit:
            pass
    try:
        assert_cut("nq", pd.DatetimeIndex(["2025-06-30 09:30"]).tz_localize("US/Eastern"), S.LB0); raise AssertionError("a bar on the cut day must be refused")
    except SystemExit:
        pass
    # 12. Stage A asks for data cut at 2025-06-30 and refuses a session on/after it (the loaders and the book are stubbed; nothing real is read)
    seen = {}
    def stub(t_end, open5=True):
        assert t_end == S.LB0, "Stage A must ask for data cut at 2025-06-30"
        seen["t"] = t_end
        return SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27", "2025-06-30"]))
    me = sys.modules[__name__]
    with patched(S, Data=stub), patched(me, load_463=lambda: (SimpleNamespace(), []), book_check=lambda *a, **k: {"roc": 0.0, "sortino": 0.0, "ref": [0, 0], "ok": True}):
        try:
            with contextlib.redirect_stdout(open(os.devnull, "w")):
                stage_a()
            raise AssertionError("Stage A must refuse a session on/after the cut")
        except SystemExit as e:
            assert "on/after the cut" in str(e) and seen["t"] == S.LB0, (str(e), seen)
    print("selftest ok: constants as registered, split-safe exit across a 2-for-1 split, gap-scan removal (set and null), later-open / -100% / unresolved exits, the drops, the hedge (sign, size, per-name = "
          "basket, missing prints), the null (uniform, seeded, k = pool reproduces the attention set), exit-day stamping across a weekend, NQ prints and fallbacks, ROC / PF / NW t / best 1% / "
          "July-June breadth, the c* tie rule, the seat measure, the cut")


# ------------------------------------------------------------------ smoke: an offline end-to-end run on a SYNTHETIC world (every number means nothing)
class NQFake:
    """synthetic NQ 5-minute RTH masters (unadjusted + roll-corrected twins) on the synthetic sessions: a continuous path p, raw = p + the rolls' gaps so far, adj = p + 5000 (so the overnight change
    of adj is the true one and raw's carries the roll gap). Planted: a half day (2023-11-24, bars to 12:55), no 15:55 bar (2024-01-17), no 09:30 bar (2024-02-08), no bar at all (2024-03-05).
    leaky: load_master_arrays ignores date_to, so only load_nq's own cut stands between Stage A and the later bars"""
    ROLLS = {"2023-12-15": 30.0, "2024-02-20": -25.0, "2025-04-17": 18.0}

    def __init__(self, days, leaky=True):
        rng = np.random.default_rng(23)
        self.leaky, self.p_open, self.p_close, self.raw_open, self.raw_close = leaky, {}, {}, {}, {}      # per session: the used bars' continuous-path open / close (NaN = no bars), + the raw ones
        parts = {"raw": ([], [], []), "adj": ([], [], [])}
        p, gsum = 15500.0, 0.0
        for d in days:
            ds = f"{d:%Y-%m-%d}"
            gsum += self.ROLLS.get(ds, 0.0)
            o0 = p * (1 + rng.normal(0, 0.004))
            cc = o0 * np.cumprod(1 + rng.normal(0, 0.0007, 78))
            oo = np.r_[o0, cc[:-1]]
            slots = np.arange(42 if ds == "2023-11-24" else 78)
            if ds == "2024-01-17":
                slots = slots[slots != 77]
            if ds == "2024-02-08":
                slots = slots[slots != 0]
            if ds == "2024-03-05":
                slots = slots[:0]
            self.p_open[d], self.p_close[d] = (oo[slots[0]], cc[slots[-1]]) if len(slots) else (np.nan, np.nan)
            self.raw_open[d], self.raw_close[d] = self.p_open[d] + gsum, self.p_close[d] + gsum
            ts = pd.DatetimeIndex(d + pd.Timedelta(minutes=570) + pd.to_timedelta(5 * slots, unit="m"))
            for tag, off in (("raw", gsum), ("adj", 5000.0)):
                parts[tag][0].append(ts); parts[tag][1].append(oo[slots] + off); parts[tag][2].append(cc[slots] + off)
            p = cc[-1]
        self.tab = {tag: (pd.DatetimeIndex(np.concatenate([np.asarray(t, dtype="datetime64[ns]") for t in v[0]])).tz_localize("US/Eastern"), np.concatenate(v[1]), np.concatenate(v[2]))
                    for tag, v in parts.items()}

    def install(self):
        data, w = data_mod(), self

        def find(instrument, timeframe, session=None, source=None):
            assert (instrument, timeframe, session) == ("NQ", "5m", "rth") and source in (SRC_RAW, SRC_ADJ), (instrument, timeframe, session, source)
            return {"id": 37 if source == SRC_RAW else 73, "instrument": instrument, "timeframe": timeframe, "session": session, "source": source, "filename": "SMOKE"}

        def arrays(master, date_from=None, date_to=None):
            idx, o, c = w.tab["raw" if master["source"] == SRC_RAW else "adj"]
            keep = np.ones(len(idx), bool)
            if date_from:
                keep &= np.asarray(idx >= TS(date_from, tz="US/Eastern"))
            if date_to and not w.leaky:
                keep &= np.asarray(idx < TS(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
            return {"index": idx[keep], "open": o[keep], "close": c[keep], "meta": master}
        data.find_master, data.load_master_arrays = find, arrays


def brute_att(D, raw, spl, first):
    """an independent plain-python recount of every attention name-night from the LONG daily frames (not the arrays): the drops, shares, ADV$, the split factor, the exit search, the gap flag, the
    split-safe exit value. Shares only D's own P / RV / C5 / msplit / Od (r5_siporb's). -> [(night row, symbol column, N, Vx, booking row, kind)]"""
    T = len(D.days)
    r = {k: g.set_index("date") for k, g in raw.groupby("symbol", observed=True)}
    q = {k: g.set_index("date") for k, g in spl.groupby("symbol", observed=True)}
    fac = lambda sym, d: r[sym]["o"].get(d, np.nan) / q[sym]["o"].get(d, np.nan)
    out = []
    for i in range(first, T - 1):
        for c in D.top20(i):
            sym, d = str(D.syms[c]), D.days[i]
            px = D.C5[i, c] if np.isfinite(D.C5[i, c]) else D.Od[i, c]
            dv = [r[sym]["c"].get(x, np.nan) * r[sym]["v"].get(x, np.nan) for x in D.days[max(i - 14, 0):i]]
            close = r[sym]["c"].get(d, np.nan)
            if not (px >= 5.0 and len(dv) == 14 and np.all(np.isfinite(dv)) and np.mean(dv) >= 5e6 and math.floor(5000.0 / close + 1e-9) >= 1 and np.isfinite(fac(sym, d))):
                continue
            sh = math.floor(5000.0 / close + 1e-9)
            j = next((k for k in range(i + 1, min(i + 12, T)) if np.isfinite(D.Od[k, c]) and np.isfinite(fac(sym, D.days[k]))), -1)
            if j < 0:
                if i + 11 <= T - 1:
                    out.append((i, c, sh * close, 0.0, i + 1, NONE))                       # no open in t+1 .. t+11: -100%; a window cut by the stage's data is out
                continue
            if D.msplit[j, c]:
                continue
            out.append((i, c, sh * close, sh * D.Od[j, c] * fac(sym, d) / fac(sym, D.days[j]), j, NORMAL if j == i + 1 else LATER))
    return out


def smoke_book():
    """a synthetic BOOK #463 written as r11_risk's own files (records_U.npz + build.json) into R11.OUT: four legs of one-day trades on random business days"""
    rng = np.random.default_rng(5)
    bd = pd.bdate_range(R11.W0, R11.W1)
    legs = [{"strategy": nm, "instrument": "NQ", "mult": 20.0, "weight": 1.0, "cost_pts": 0.533} for nm in ("ORB", "NOISE", "TTM", "ENGUQ")]
    ent, clo, leg = [], [], []
    for k in range(4):
        sel = bd[rng.random(len(bd)) < 0.3]
        ent.append(np.asarray(sel, dtype="datetime64[D]")); clo.append(rng.normal(40.0, 700.0, len(sel))); leg.append(np.full(len(sel), k, np.int64))
    ent, clo, leg = np.concatenate(ent), np.concatenate(clo), np.concatenate(leg)
    os.makedirs(R11.OUT, exist_ok=True)
    np.savez_compressed(os.path.join(R11.OUT, "records_U.npz"), entry=ent.astype("int64"), exit=ent.astype("int64"), closed=clo, leg=leg, inc_d=ent.astype("int64"), inc_v=clo,
                        inc_t=np.arange(len(clo), dtype=np.int64), fsize=np.ones(len(clo)))
    R11.save("build.json", {"legs": legs, "P1_pass": True})


def smoke_refusal(root):
    """S.smoke_refusal's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog) + this harness's OUT and R11's"""
    why = S.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    for n, q in (("ATTN OUT", OUT), ("the #463 records folder", R11.OUT)):
        try:
            if os.path.commonpath([real(root), real(q)]) == real(root):
                return f"smoke refused: {root} is or holds {n}"
        except ValueError:
            pass
    return None


def smoke(*a):
    import re, shutil, tempfile
    global OUT, CHECK_BOOK
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "attn_smoke"))
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    me, data = sys.modules[__name__], data_mod()
    keep = dict(OUT=OUT, CHECK_BOOK=CHECK_BOOK, RULES=dict(RULES), R11_OUT=R11.OUT, S=(S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get), nq=(data.find_master, data.load_master_arrays))
    t_start = time.time()
    shutil.rmtree(root, ignore_errors=True); os.makedirs(root)
    OUT, R11.OUT = os.path.join(root, "out"), os.path.join(root, "r11")
    S.OUT, S.CACHE, S.BOOK = os.path.join(root, "siporb_out"), os.path.join(root, "cache"), os.path.join(root, "r4", "book463_daily.csv")
    for p in (OUT, R11.OUT, S.OUT):
        os.makedirs(p)
    S.SMOKE, S.PACE, S.BACKOFF, S.RETRY = True, 0.0, 0.0, 0.0
    CHECK_BOOK = False                                                                     # the book check is off in smoke only: its synthetic book cannot reproduce #463
    inside = lambda p: os.path.commonpath([os.path.realpath(p), os.path.realpath(root)]) == os.path.realpath(root)
    assert all(inside(p) for p in (OUT, R11.OUT, S.OUT, S.CACHE)), "every path the smoke writes is inside the smoke dir"
    quiet = lambda: contextlib.redirect_stdout(io.StringIO())
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    try:
        spans = (("2015-11-02", "2015-12-31"), ("2016-01-04", "2016-03-31"), ("2016-06-13", "2016-07-15"), ("2023-10-02", "2023-12-29"), ("2024-01-02", "2024-06-28"),
                 ("2025-04-01", "2025-06-27"), ("2025-06-30", "2025-08-29"))              # warm-up, 2016 H1, around the WF start, WF pieces, lockbox days: the cut has something to cut
        days = pd.DatetimeIndex(sorted(set().union(*[pd.bdate_range(x, y) for x, y in spans])))
        t0 = time.time(); fk = S.Fake(days); S._http_get = fk.handle
        print(f"synthetic market: {len(fk.names)} names x {len(days)} sessions built in {time.time() - t0:.0f}s")
        t0 = time.time()
        with quiet():
            S.assets(); S.daily(); S.open5()                                                # r5_siporb's own pulls through its fake transport: the synthetic daily + 09:30 caches
        print(f"synthetic SIPORB cache pulled through r5_siporb ({fk.n:,} requests, {time.time() - t0:.0f}s)")
        nqf = NQFake(days); nqf.install()
        smoke_book()
        # ---- the planted cases, through the real Data / arrays / hedge
        with quiet():
            D = load_data(S.LB0)
        Cl, adv, F = load_arrays(D, S.LB0)
        nq, meta = load_nq(S.LB0)
        cut = TS(S.LB0).tz_localize("US/Eastern")
        assert nq["raw"].index.max() < cut and nq["adj"].index.max() < cut and nqf.tab["raw"][0].max() >= cut, "the NQ loader hands back bars past the cut (leaky) and load_nq's own cut removes them"
        pr = hedge_prints(nq)
        hd = hedge_returns(D.days, pr)
        W = World(D, Cl, adv, F, hd)
        ix, T = list(D.syms), len(D.days)
        di = lambda s: D.days.get_loc(TS(s))
        assert not pr.loc["2023-11-24", "close_fb"] and np.isclose(pr.loc["2023-11-24", "c_adj"] - 5000.0, nqf.p_close[TS("2023-11-24")]), "half day: the 12:55 bar's close, no fallback"
        assert pr.loc["2024-01-17", "close_fb"] and pr.loc["2024-02-08", "open_fb"] and TS("2024-03-05") not in pr.index, "the planted missing bars use the fallback rules / leave no print"
        i = di("2024-01-17")
        assert np.isclose(hd.delta[i], nqf.p_open[TS("2024-01-18")] - nqf.p_close[TS("2024-01-17")]) and np.isclose(hd.px[i], nqf.raw_close[TS("2024-01-17")]), "the overnight change over a fallback close"
        i = di("2023-12-15") - 1
        d0, d1 = D.days[i], TS("2023-12-15")
        assert np.isclose(hd.delta[i], nqf.p_open[d1] - nqf.p_close[d0]) and np.isclose(nqf.raw_open[d1] - nqf.raw_close[d0] - hd.delta[i], 30.0), \
            "a roll night: the hedge reads the roll-corrected change, the raw one carries the 30-point roll gap"
        assert np.isnan(hd.hr[di("2024-03-05") - 1]) and np.isnan(hd.hr[di("2024-03-05")]), "no NQ bar on 2024-03-05: both nights touching it are unhedged"

        def force(i_, s_, f):                                                              # run f with name s_ forced into the filters on session i_ (the synthetic name may not pass them)
            keep_p = D.P[i_, s_]; D.P[i_, s_] = True
            try:
                return f()
            finally:
                D.P[i_, s_] = keep_p
        spl = S.read_long("split", S.LB0); spl["symbol"] = spl["symbol"].astype(str)         # an independent read of the split-adjusted bars: the true move across SPL's 2-for-1
        sp = spl[spl["symbol"] == "SPL"].set_index("date")
        i, k = di("2024-03-14"), ix.index("SPL")
        nt = force(i, k, lambda: night(W, i))
        true = sp.loc[TS("2024-03-15"), "o"] / sp.loc[TS("2024-03-14"), "c"]
        assert nt.elig[k] and nt.K[k] == NORMAL and abs(nt.Vx[k] / nt.N[k] - true) < 2e-3 and abs(true - 1) < 0.2, "split-safe across SPL's 2-for-1: the exit value is the true move"
        i, k = di("2024-05-31"), ix.index("DLST")
        nt = force(i, k, lambda: night(W, i))
        assert nt.elig[k] and nt.K[k] == NONE and nt.Vx[k] == 0.0 and nt.J[k] == i + 1, "a delisted name: no open in the next 10 sessions = -100%"
        i, k = di("2024-04-19"), ix.index("S18")
        nt = force(i, k, lambda: night(W, i))
        assert D.msplit[di("2024-04-22"), k] and not nt.elig[k] and nt.why[k] == 5, "S18's unadjusted x4 on 2024-04-22: the night ending there is removed"
        k = ix.index("S01")
        o_keep = D.Od[T - 1, k]; D.Od[T - 1, k] = np.nan
        nt = force(T - 2, k, lambda: night(W, T - 2))
        D.Od[T - 1, k] = o_keep
        assert nt.K[k] == CUT and nt.why[k] == 6 and not nt.elig[k], "no open on the last session of the stage's data and no window left: unresolved"
        print("planted cases ok through the real arrays: split-safe exit, delisted name (-100%), the missed split's night removed, unresolved at the cut, the NQ prints / fallbacks / roll night / half day")
        # ---- every exit kind forced into the real flow (the planted names are pushed to the top of the day's Relative Volume), then an independent recount of every attention name-night
        for nm, ds in (("DLST", "2024-05-31"), ("SPL", "2024-03-14"), ("S18", "2024-04-19"), ("S05", "2024-02-13")):
            D.P[di(ds), ix.index(nm)], D.RV[di(ds), ix.index(nm)] = True, 1e3
        D.Od[di("2024-02-14"), ix.index("S05")] = np.nan                                  # S05: no open at t+1 -> the open of t+2, booked that day
        R = run_nights(W, 0)
        raw_l, spl_l = S.read_long("raw", S.LB0), S.read_long("split", S.LB0)
        first = max(int(D.days.searchsorted(NIGHT0)) - 1, 0)
        bf = brute_att(D, raw_l, spl_l, first)
        a_ = R.att
        mine = list(zip(a_["i"].tolist(), a_["s"].tolist(), a_["N"].tolist(), a_["Vx"].tolist(), a_["j"].tolist(), a_["K"].tolist()))
        assert len(mine) == len(bf) > 2000 and [m[:2] + m[4:] for m in mine] == [b[:2] + b[4:] for b in bf] and np.allclose([m[2:4] for m in mine], [b[2:4] for b in bf], rtol=1e-9, atol=1e-6),             "the vectorised attention set equals an independent recount from the long daily frames"
        kinds = {nm: [m[5] for m in mine if m[0] == di(ds) and m[1] == ix.index(nm)] for nm, ds in (("DLST", "2024-05-31"), ("SPL", "2024-03-14"), ("S05", "2024-02-13"), ("S18", "2024-04-19"))}
        assert kinds == {"DLST": [NONE], "SPL": [NORMAL], "S05": [LATER], "S18": []}, kinds
        assert any(g_[2] == ix.index("S18") and abs(g_[3] - 4.0) < 0.1 for g_ in R.gaps), "S18's removed night is reported at its raw R (about 4)"
        j5 = [m for m in mine if m[0] == di("2024-02-13") and m[1] == ix.index("S05")][0]
        assert D.days[j5[4]] == TS("2024-02-15"), "booked on the day it exits, not on the missing t+1"
        # the null: a draw is a uniform random k-subset of each night's pool, so the draws' mean total P&L is the sum over nights of k x the pool's mean per-name P&L
        Rn, exp = run_nights(W, 300, SEED), 0.0
        for i in range(first, T - 1):
            if Rn.kn[i]:
                nt = night(W, i); pool = np.flatnonzero(nt.elig); h0 = hd.hr[i] if np.isfinite(hd.hr[i]) else 0.0
                exp += Rn.kn[i] * np.mean((nt.Vx[pool] - nt.N[pool]) - 5e-4 * (nt.N[pool] + nt.Vx[pool]) + nt.N[pool] * h0)
        tot = Rn.acc.sum(axis=1)
        assert abs(tot.mean() - exp) < 4 * tot.std() / np.sqrt(len(tot)), (tot.mean(), exp, tot.std())
        assert (run_nights(W, 20, SEED).acc == run_nights(W, 20, SEED).acc).all(), "the null is seeded"
        print(f"independent recount ok: {len(mine):,} attention name-nights equal a plain-python recount from the long daily frames (kinds forced: -100%, split-safe, later open, gap-scan removal); "
              f"the null's mean total P&L ${tot.mean():,.0f} vs its exact expectation ${exp:,.0f}")
        # ---- Stage A, end to end
        t0 = time.time()
        sa = os.path.join(OUT, "attn_stageA.json")
        with patched(me, PREREG_SHA="0" * 64):
            try:
                stage_a(); raise AssertionError("a changed pre-registration must refuse Stage A")
            except SystemExit as e:
                assert "DIFFERS" in str(e) and not os.path.exists(sa)
        CHECK_BOOK = True
        try:
            with quiet():
                stage_a()
            raise AssertionError("a book that does not reproduce #463 must refuse Stage A")
        except SystemExit as e:
            assert "do not reproduce" in str(e) and not os.path.exists(sa)
        CHECK_BOOK = False
        print("--- Stage A, every bar as registered (the synthetic world cannot pass them): the FAIL path")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = stage_a()
        txt = buf.getvalue(); print(txt.rstrip())
        assert out["judged"] and not out["stageA"]["PASS"] and os.path.exists(sa) and all(d < "2025-06-30" for d in dates_of(txt)), "Stage A printed a lockbox date"
        try:
            stage_b(); raise AssertionError("Stage B must refuse after a Stage A fail")
        except SystemExit as e:
            assert "no Stage A + A2 pass" in str(e) and not os.path.exists(os.path.join(OUT, "attn_stageB_READ.flag"))
        print("--- the coverage gate: half of the 2023-24 sessions lose their 09:30 file -> not judged")
        o5 = sorted(f for f in os.listdir(S.path_of("open5")) if f[:4] in ("2023", "2024"))
        hold = {f: open(S.path_of("open5", f), "rb").read() for f in o5[::2]}
        for f in hold:
            os.remove(S.path_of("open5", f))
        with quiet():
            out = stage_a()
        assert not out["judged"] and out["coverage"]["share"] < RULES["cov"] and out["A2"] is None and json.load(open(sa))["judged"] is False
        for f, b in hold.items():
            open(S.path_of("open5", f), "wb").write(b)
        print("--- every bar waived (null / stress / best 1% / breadth switched off): the PASS path, A2, the stamp")
        RULES.update(n=1, roc=-1e9, pf=0.0, t=-1e9, null=False, stress=False, exbest=False, years=0, a2_roc=-1e9, a2_sort=-1e9, b_n=1, b_roc=-1e9, b_sort=-1e9)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = stage_a()
        txt = buf.getvalue(); print(txt.rstrip())
        assert out["judged"] and out["stageA"]["PASS"] and out["A2"]["pass"] and out["A2"]["c"] in CS and all(d < "2025-06-30" for d in dates_of(txt)), "Stage A printed a lockbox date"
        js = json.load(open(sa))
        assert {k: js.get(k) for k in stamp()} == stamp() and js["prereg_sha256_lf"] == PREREG_SHA and js["stageA"]["null"]["draws"] == NREP and js["stageA"]["H"]["stock_nights"] > 0, "the stamp"
        assert set(js["reports"]["cells"]) >= {"H", "U", "H 10 bps", "H 20 bps"} and any("ORB" in k for k in js["reports"]["corr_daily"]["H"]), "the report cells and the leg correlations are in the file"
        assert js["stageA"]["H"]["stock_nights"] == sum(v.get("traded", 0) for v in js["reports"]["counts_by_exit_year"].values()) > 0, "every name-night booked in the stretch is counted once by its exit year"
        print(f"Stage A ran end to end in {time.time() - t0:.0f}s")
        # ---- Stage B: the refusal paths, then the one read
        print("--- Stage B refusal paths: SIPORB not read yet, SIPORB's Stage A not a verdict, a stale stamp, a changed spec, a book that does not reproduce LB; none may write the flag")
        flag = os.path.join(OUT, "attn_stageB_READ.flag")

        def must_refuse(frag, burned=False):
            try:
                with quiet():
                    stage_b()
                raise AssertionError(f"Stage B must refuse ({frag})")
            except SystemExit as e:
                assert frag in str(e), (frag, str(e))
                assert burned or not os.path.exists(flag), "a refused Stage B must not burn the lockbox"
        must_refuse("has not been read")
        sip = os.path.join(S.OUT, "siporb_stageA.json")
        for body in ({"judged": False, "stageA": None, "A2": None}, {"judged": True, "stageA": {"PASS": True}, "A2": {"pass": False, "error": "book check mismatch"}},
                     {"judged": True, "stageA": {"PASS": True}, "A2": None}, {"judged": True, "stageA": {"PASS": True}, "A2": {"pass": True}}):
            json.dump(body, open(sip, "w")); must_refuse("has not been read")              # not judged / A2 could not be judged / A2 not run / SIPORB passed but has not read: not a verdict
        assert siporb_state() is None
        json.dump({"judged": True, "stageA": {"PASS": False}, "A2": None}, open(sip, "w")); assert siporb_state() == "dead"
        json.dump({"judged": True, "stageA": {"PASS": True}, "A2": {"pass": False}}, open(sip, "w")); assert siporb_state() == "dead"
        os.remove(sip); open(os.path.join(S.OUT, "siporb_stageB_READ.flag"), "w").write("x"); assert siporb_state() == "read"
        js0 = open(sa).read()
        for edit in (lambda j: j.update(harness_sha256="0" * 64), lambda j: j.update(early_close=j["early_close"][1:]), lambda j: [j.pop(k) for k in stamp()]):
            j = json.loads(js0); edit(j); json.dump(j, open(sa, "w")); must_refuse("different harness version")
        j = json.loads(js0); j["prereg_sha256_lf"] = "0" * 64; json.dump(j, open(sa, "w")); must_refuse("another pre-registration")
        for edit in (lambda j: j["A2"].update(**{"pass": False}), lambda j: j["stageA"].update(PASS=False), lambda j: j.update(judged=False)):
            j = json.loads(js0); edit(j); json.dump(j, open(sa, "w")); must_refuse("no Stage A + A2 pass")
        open(sa, "w").write(js0)
        with patched(me, PREREG_SHA="0" * 64):
            must_refuse("DIFFERS")
        j = json.loads(js0); j["stageA"]["H"]["net"] += 1e6; json.dump(j, open(sa, "w")); must_refuse("do not reproduce on Stage B's data")      # the WF numbers drifted since Stage A
        open(sa, "w").write(js0)
        CHECK_BOOK = True
        must_refuse("do not reproduce its LB numbers")
        CHECK_BOOK = False
        print("--- Stage B, the one read (SIPORB's READ flag stands in for its lockbox): the flag after the load and the checks, the verdict, a second read refused")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = stage_b()
        print(buf.getvalue().rstrip())
        sb = json.load(open(os.path.join(OUT, "attn_stageB.json")))
        assert os.path.exists(flag) and sb["pass"] == ok and sb["c"] == out["A2"]["c"] and sb["siporb"] == "read" and sb["coverage"]["share"] >= RULES["cov"] and sb["H"]["stock_nights"] > 0
        assert {k: sb.get(k) for k in stamp()} == stamp(), "Stage B's file carries the stamp"
        must_refuse("already read", burned=True)
        try:
            stage_a(); raise AssertionError("Stage A must be frozen once the lockbox has been read")
        except SystemExit as e:
            assert "Stage A is frozen" in str(e)
        pm = peak_mb()
        print("Stage B refused before the flag in every case above, wrote the flag only after the load and the checks, and refused a second read")
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline")
    finally:
        OUT, CHECK_BOOK = keep["OUT"], keep["CHECK_BOOK"]
        RULES.clear(); RULES.update(keep["RULES"])
        R11.OUT = keep["R11_OUT"]
        S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get = keep["S"]
        data.find_master, data.load_master_arrays = keep["nq"]


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r13_attn.py selftest | smoke DIR | stage_a | stage_b   (stage_a runs after SIPORB's Stage A; stage_b only after SIPORB's lockbox has been read)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
