# DDW r1 - drawdown-week earners, family 1 = LIQUIDITY PROVISION in US stocks, leaning in when markets are stressed: L1 = weekly reversal (rank on the week's last close, fill at the next open),
# L2 = no-news gap fade (09:35 fill, closing exit); cells L1-F, L1-S, L2-F, L2-S (S = every position x k_t, ES's volatility ratio). A leg for BOOK #463 that must EARN WHILE #463 FALLS.
# Pre-registered: tools/rocfrontier/PREREG_DDW_R1.txt (canonical LF sha256 7a8dbbfa...6117; MANAGER + TV + ORB reviewed, final 2026-10-05 with MANAGER's XGAP edits 2 / 4 and #48, written before any number of this family exists).
# Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE. Bracketed tags ([O3], [M2], [T2] ...) name the review edits that are folded into it.
#   python r15_ddw.py selftest    hand-made worlds: universe timing, split-safe marks, fills / exits / costs / borrow, news, hygiene windows, large-move check, null, DO / rho_dd vs MDL r1, Stage B refusals
#   python r15_ddw.py smoke DIR   offline end-to-end on a SYNTHETIC world (r5_siporb's fake Alpaca, a fake ES master, a fake #463, a fake TBIS file); DIR's name must contain 'smoke'
#   python r15_ddw.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - sessions, universe sizes, eligible names, hygiene, coverage, ES holes (a WARNING when one blinds L2's betas) - never a price, return or P&L
#   python r15_ddw.py stage_a     WF Stage A + A2 + the reports -> ddw_stageA.json (+ ddw_audit_candidates.csv), PRE-LOCKBOX ONLY (every input is cut to dates < 2025-06-30 when it is read)
#   python r15_ddw.py stage_b     Stage B (lockbox, ONCE, on the one sealed-year day): refuses unless a Stage A + A2 pass with a complete audit is on file, ATTN's Stage A is judged and SIPORB is read-or-dead;
#                                 the pass is the LEG's standalone veto, the book add at the frozen c is only reported
# Reads (never writes) the SIPORB cache through r5_siporb, the ES 5m RTH masters through augur_engine.data, the #463 book through r11_risk, DO / rho_dd through r12_mdl and the shared helpers of
# r13_attn - imported, never copied. Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else.
import contextlib, hashlib, io, json, math, os, subprocess, sys, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r5_siporb as S        # Data (days, syms, raw open, ATR, registered splits, gap-scan flags, the 09:30 bar, Relative Volume), read_long, roll14, missed_split_flags, the fake Alpaca of its smoke
import r11_risk as R11       # the #463 book (records -> Book), stats (house ROC @ $30k / Sortino), underwater, the windows and the reference numbers
import r12_mdl as M12        # Stretch (#463's qualifying drawdowns, DD days / weeks) and realised (rho_dd, DO): the MDL r1 definitions, exactly
import r13_attn as A13       # ATTN's shared helpers: assert_cut, align / fill, load_data, load_463, book_check / book_rows, ceil_pct, breadth, siporb_state, nq_prints, the fakes

TS = pd.Timestamp
OUT = os.environ.get("EDGELOG_DDW_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\ddw_r1")        # results, outside git
PREREG = os.path.join(HERE, "PREREG_DDW_R1.txt")
PREREG_SHA = "e2d946ad9ceafde2e31433017030fb9be1fca2ea0893b17e5583945e961afad7"                 # canonical (LF) sha256 of the pre-registration as final on 2026-10-05 (with the c-by-volatility and leg-only-veto edits)
TBIS_CSV = r"C:\EdgeLog\_research_cache\split_qa\siporb_split_flags_voltest.csv"                # TBIS's volume-tested split flags (symbol, day, price_ratio, vol_ratio, split_like)
MANIFEST_PREFIX = "380b05f2"                                                                    # the SIPORB cache photograph the pre-registration names (never mixed with a re-pull)
WF0, PRE_END, LB0, LB1 = A13.WF0, A13.PRE_END, A13.LB0, A13.LB1          # WF = positions EXITED 2016-07-01 .. 2025-06-29; LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, TOL = A13.BOOK_WF, A13.BOOK_LB, A13.TOL                # #463's unified-convention ROC@30k / Sortino: 93.81 / 3.816 and 155.54 / 4.150, and the match tolerance
DEEPEST_WF = 44849.0                                                     # #463's deepest WF drawdown (prereg [T5]); the harness refuses unless it reproduces to the dollar
DD_REF = {"episodes": 28, "days": 460, "weeks": 92, "by_year": {2019: 45, 2020: 30, 2021: 52, 2022: 107, 2023: 100, 2024: 71, 2025: 55}}   # prereg [T5]: #463's own DD structure, printed before any cell number
NREP, SEED = 500, 20261004
A2_WIN = (TS("2016-07-01"), TS("2018-06-29"))                           # STAGE A2: c is set on the first two WF years ...
A2_TARGET, A2_REPORT = 0.25, (0.5, 2.0)                                  # ... so that c x the cell's daily std = 25% of #463's over them; the book at 0.5c and 2c is reported, never judged
CELLS = ("L1-F", "L1-S", "L2-F", "L2-S")
YEARS = A13.YEARS                                                        # the nine July-June WF years 2016-17 .. 2024-25
X20 = R11.X20                                                            # 2020-02-15 .. 2020-04-30 (RISK r1's check window)
EP20 = (TS("2020-03-03"), TS("2020-03-27"))                              # the qualifying episode whose DD days run 2020-03-03 .. 03-27 (prereg (d) [O11])
DD_YEARS = tuple(range(2019, 2026))                                      # the seven calendar years that hold qualifying DD days
ES_D0 = "2014-01-01"                                                     # CHOICE: ES is loaded from 2014 so k_t (a 20-session std against the median of the last 252 of those) exists from the first 2016 session (masters start 2010)
SPEC = {"univ": 500, "px_min": 10.0, "dv_n": 20, "vol_min": 1_000_000.0, "atr_min": 0.50, "look": 14, "split_n": 14,        # the universe: 500 largest by 20-session $ volume, price >= $10, filters 2-3, no split
        "news_x": 3.0, "news_n": 20,                                                                                    # news proxy: a session with volume >= 3x the name's previous 20-session mean
        "ret_n": 5, "hyg_lead": 5, "l1_n": 25, "l1_slot": 4000.0,                                                       # L1: 5-session return, hygiene starts 5 sessions before the ranking window, 25 a side, $4,000 each
        "l2_n": 20, "l2_slot": 5000.0, "gap_min": 0.01, "rv_max": 2.0, "beta_n": 60,                                    # L2: 20 a side, $5,000 each, |adjusted gap| >= 1%, Relative Volume < 2, 60-session beta
        "xchk_l1": 0.25, "xchk_l2": 0.20, "xchk_vol": 0.25, "xchk_floor": 0.25, "squeeze": 0.30, "es_rv_n": 20, "es_med_n": 252,
        "es_rv_min": 18, "es_med_min": 200, "k_lo": 0.5, "k_hi": 2.0,
        "beta_min": 55}          # PREREG ADDENDUM 1 (2026-10-05, pre-data): 55 of the 60 sessions, ES-hole sessions skipped. Was: the registered beta rule was 'all 60 present' (beta_min = beta_n = 60: ONE undefined ES return in the window leaves every name without a beta). beta_min < 60 is an opt-in tolerance - ES
        #                          sessions with no return are dropped from the regression for every name while >= beta_min sessions remain - NOT registered: the dryload found two holes in the ES masters (2020-02-28, 2020-06-30)
COST_BPS, STRESS_BPS = 5.0, (10.0, 20.0)                                 # L1: a side, of the notional (entry and exit); L2's closing exit; stress 10 and 20
ADV_BPS, ADV_STRESS = 10.0, 20.0                                         # L2's adverse fill at the 09:35 price: a buy that far above it, a sell that far below (its ENTRY cost [O7]); stress 20
L2_STRESS = ((ADV_STRESS, 10.0), (ADV_STRESS, 20.0))                     # L2 stress rows (entry, exit) bps: the first stress and the "also report 20/20" row
BORROW, BORROW_STRESS, K_STRESS = 0.0025, (0.01, 0.03), 1.5             # short notional a year; stress rates apply on sessions with k_t > 1.5 [M3]
SQUEEZE_RATE = 0.20                                                      # [O5] a squeezed winner (L1 short, signal > +30%) pays 20% a year in the stress row
SQ_WEEKS = (("GME / AMC squeeze, 2021-01-22 .. 01-29", "2021-01-22", "2021-01-29"), ("HTZ, June 2020", "2020-06-01", "2020-06-30"))
AUDIT_N = 50                                                             # [O3 (ii)] the largest single-name P&L contributors audited by hand
RULES = {"n": 100, "l1_reb": 26, "l2_days": 60, "cov": 0.98, "net_pos": True, "null": True, "stress": True, "do_null": True, "rho_null": True, "do_pos": True, "rho_neg": True, "dd_years": 4, "ex_episode": True,
         "years": 6, "ex2020": True,
         "exbest": True, "best_pct": 1, "twin": True, "a2_roc": 1.05 * BOOK_WF[0], "a2_sort": BOOK_WF[1], "b_n": 50, "b_l1_reb": 26, "b_l2_days": 30, "b_roc": BOOK_LB[0], "b_sort": BOOK_LB[1]}
        # CHOICE: A2's bar is 1.05 x 93.81 as a formula (98.5005), not its rounding 98.5 (ATTN's reading)
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest / k_t do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = ("split", "gap", "tbis", "jump")                                   # data-hygiene reasons [T2], in the order a position's first reason is attributed


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


def committed_state():
    """the committed blob of the pre-registration against PREREG_SHA: 'match' | 'differs' | 'untracked' (not committed yet - the lead commits before the real run) | 'unknown' (no git here)"""
    try:
        rel = os.path.basename(PREREG)
        if subprocess.run(["git", "-C", HERE, "ls-files", "--error-unmatch", rel], capture_output=True, timeout=60).returncode != 0:
            return "untracked"
        blob = subprocess.run(["git", "-C", HERE, "show", f"HEAD:./{rel}"], capture_output=True, timeout=60)
        if blob.returncode != 0:
            return "untracked"
        return "match" if hashlib.sha256(blob.stdout.replace(b"\r\n", b"\n")).hexdigest() == PREREG_SHA else "differs"
    except Exception:
        return "unknown"


def prereg_ok():
    """the frozen spec this file implements must still be the final one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob when
    there is one; until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_DDW_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_DDW_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    st = committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_DDW_R1.txt differs from the registered sha - the file on disk is not the file in git (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_DDW_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                              "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + every harness it imports numbers from (r5_siporb's Data / read_long, r11's book and stats, r12's DO / rho_dd, r13's helpers) + the
    shared half-day list; Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "siporb_sha256": R11.sha_lf(S.__file__), "r11_sha256": R11.sha_lf(R11.__file__), "r12_sha256": R11.sha_lf(M12.__file__),
            "r13_sha256": R11.sha_lf(A13.__file__), "early_close": sorted(S.EARLY_CLOSE_DATES)}


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct


def dump(obj, name):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=1, default=R11.js)


def file_sha(path):
    """LF-normalised sha256 of a text file; None when it does not exist"""
    return R11.sha_lf(path) if os.path.exists(path) else None


def manifest_sha():
    p = os.path.join(S.OUT, "siporb_cache_manifest.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p)).get("manifest_sha256")
    except Exception:
        return None


# ------------------------------------------------------------------ rolling helpers (S.roll14's rule for any window: the PREVIOUS n sessions, NaN unless all n are present)
def shift1(a):
    out = np.full(a.shape, np.nan)
    out[1:] = a[:-1]
    return out


def roll_prev(a, n):
    """mean of the previous n sessions (rows t-n .. t-1), NaN unless all n are present: r5_siporb.roll14 for any n (n = 14 equals it - the selftest asserts it)"""
    return pd.DataFrame(a).rolling(n, min_periods=n).mean().shift(1).to_numpy()


def prev_any(flag, n):
    """True where the flag fell on any of the previous n sessions (rows t-n .. t-1): 'no registered split in the 14 sessions before f'"""
    return pd.DataFrame(np.asarray(flag, np.float32)).rolling(n, min_periods=1).max().shift(1).fillna(0.0).to_numpy() > 0


def universe_mask(Cl, Vv, atr, chg, sp=None):
    """(T, S) bool: the names tradable at session t, from sessions BEFORE t only [M6]: prior raw close >= $10; mean raw dollar volume of the previous 20 sessions, all 20 present; mean volume of the previous 14
    sessions >= 1,000,000 shares and ATR14 > $0.50 (r5_siporb's roll14 / atr, each row already ending at t-1); no registered split in the 14 sessions before t; then the 500 largest by that dollar
    volume (ties: symbol order). CHOICE: the filters come first and the 500 largest are taken among the names that pass, so the universe is 500 names whenever 500 pass (ranking first and filtering
    after would leave about 450, and 'both sides always 25' needs a full set). CHOICE: 'no split in the 14 sessions before t' is rows t-14 .. t-1 (S's own window also counts t itself; a split ON the
    fill session is a hygiene removal instead - the prereg's 'from 5 sessions before the ranking window through the exit')"""
    sp = sp or SPEC
    T, Sn = Cl.shape
    with np.errstate(invalid="ignore"):
        dvn = roll_prev(Cl * Vv, sp["dv_n"])
        vn = roll_prev(Vv, sp["look"])
        cond = (shift1(Cl) >= sp["px_min"]) & np.isfinite(dvn) & (vn >= sp["vol_min"]) & (atr > sp["atr_min"]) & ~prev_any(chg, sp["split_n"])
    U = np.zeros((T, Sn), bool)
    for t in range(T):
        c = np.flatnonzero(cond[t])
        if len(c) > sp["univ"]:
            c = c[np.lexsort((c, -dvn[t, c]))[:sp["univ"]]]
        U[t, c] = True
    return U


# ------------------------------------------------------------------ ES: the stress gauge (k_t) and the opening gap's market part
def load_es(t_end):
    """the ES 5m RTH masters, raw (unadjusted: levels) and roll-corrected (price changes), -> ({'raw': df, 'adj': df} of open / close on the tz-aware bar-START index, their registry rows); r13_attn.load_nq
    for ES. Every array is cut to bars BEFORE t_end (midnight US/Eastern) and asserted so, whatever load_master_arrays hands back"""
    data = A13.data_mod()
    cut = TS(t_end).tz_localize("US/Eastern")
    d1 = str((TS(t_end) - pd.Timedelta(days=1)).date())
    out, meta = {}, {}
    for tag, src in (("raw", A13.SRC_RAW), ("adj", A13.SRC_ADJ)):
        m = data.find_master("ES", "5m", "rth", src)
        if m is None or m.get("source") != src:
            refuse(f"refused: no {src} ES 5m RTH master (nothing computed)")
        a = data.load_master_arrays(m, ES_D0, d1)
        ix = pd.DatetimeIndex(a["index"])
        keep = np.asarray(ix < cut)
        df = pd.DataFrame({k: np.asarray(a[k], float)[keep] for k in ("open", "close")}, index=ix[keep])
        if not len(df):
            refuse(f"refused: the {src} ES master has no bar before the cut (nothing computed)")
        assert_cut(f"ES {src}", df.index, cut)
        out[tag], meta[tag] = df, {k: m.get(k) for k in ("id", "source", "filename")}
    return out, meta


def es_prints(df):
    """one ES master -> a frame by session date: open = the 09:35 price = the CLOSE of the bar that starts 09:30, close = the 16:00 print = the close of the 15:55 bar (12:55 on an NYSE half day). CHOICE: it is
    r13_attn.nq_prints run on a frame whose 'open' column carries each bar's close, so the fallbacks are exactly NQ's: no 15:55 bar -> the close of the last bar that starts 15:30 .. 15:50; no 09:30 bar ->
    the close of the first bar that starts before 10:00; none -> NaN (that session has no print and is counted)"""
    return A13.nq_prints(pd.DataFrame({"open": df["close"], "close": df["close"]}, index=df.index))


def es_k(pa, pr, days, sp=None):
    """k_t for every stock session: RV20_t = the sample std (ddof 1) of ES's 20 daily returns before t (sessions t-20 .. t-1; a return = (roll-corrected 16:00 change) / the prior UNADJUSTED 16:00 print),
    k_t = RV20_t / the median of RV20 over the previous 252 sessions, clipped to [0.5, 2.0]; known at the prior close. CHOICE: computed on ES's OWN calendar (the sessions with both 16:00 prints) so the
    252-session history may start before the stock calendar does, then read at the stock session by position (the ES sessions before t; a stock session ES lacks gets the value its place in the
    calendar implies - every input is still before t); CHOICE: RV20 needs >= 18 of its 20 returns and the median >= 200 of its 252 values, else NaN"""
    sp = sp or SPEC
    ca, cr = pa["close"].dropna(), pr["close"].dropna()
    idx = ca.index.intersection(cr.index)
    n = len(idx)
    ca, cr = ca.reindex(idx).to_numpy(float), cr.reindex(idx).to_numpy(float)
    ret = np.full(n + 1, np.nan)                                                   # position n = a virtual session after the last, so a date past the last ES session still gets k
    if n > 1:
        with np.errstate(invalid="ignore", divide="ignore"):
            ret[1:n] = (ca[1:] - ca[:-1]) / cr[:-1]
    rv = pd.Series(ret).shift(1).rolling(sp["es_rv_n"], min_periods=sp["es_rv_min"]).std(ddof=1)
    med = rv.shift(1).rolling(sp["es_med_n"], min_periods=sp["es_med_min"]).median()
    kk = (rv / med).clip(sp["k_lo"], sp["k_hi"]).to_numpy()
    return kk[idx.searchsorted(pd.DatetimeIndex(days), side="left")]


def es_series(days, pa, pr):
    """the ES prints on the stock sessions (D.days): e5 = the roll-corrected 09:35 price, c16a / c16r = the roll-corrected / unadjusted 16:00 print, ret_t = (c16a_t - c16a_(t-1)) / c16r_(t-1) (the
    market's daily return), gap_t = (e5_t - c16a_(t-1)) / c16r_(t-1) (the market's opening gap by 09:35: roll-corrected change over the UNADJUSTED level), k_t. NaN where a print is missing"""
    g = lambda s: s.reindex(days).to_numpy(float)
    e5, c16a, c16r = g(pa["open"]), g(pa["close"]), g(pr["close"])
    ret, gap = np.full(len(days), np.nan), np.full(len(days), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        ret[1:] = (c16a[1:] - c16a[:-1]) / c16r[:-1]
        gap[1:] = (e5[1:] - c16a[:-1]) / c16r[:-1]
    return SimpleNamespace(e5=e5, c16a=c16a, c16r=c16r, ret=ret, gap=gap, k=es_k(pa, pr, days))


# ------------------------------------------------------------------ the TBIS flags and the hand audit
def load_tbis(t_end):
    """TBIS's volume-tested split flags (symbol, day, price_ratio, vol_ratio, split_like), cut to day < t_end AT READ TIME and asserted. CHOICE: EVERY listed symbol-day is a flag, split_like or not
    (the lead's brief; the more conservative removal). Refuses when the file is missing - the data hygiene cannot be run without it"""
    if not os.path.exists(TBIS_CSV):
        refuse(f"refused: the TBIS volume-tested flag file is missing ({TBIS_CSV}) - the data hygiene [T2] cannot be run without it (nothing computed, lockbox NOT read)")
    df = pd.read_csv(TBIS_CSV, dtype={"symbol": str}, keep_default_na=False, na_values=[""])
    miss = [c for c in ("symbol", "day", "price_ratio", "vol_ratio", "split_like") if c not in df.columns]
    if miss:
        refuse(f"refused: the TBIS flag file lacks the column(s) {miss} (nothing computed)")
    df["day"] = pd.to_datetime(df["day"])
    df = df[df["day"] < TS(t_end)].reset_index(drop=True)
    assert_cut("TBIS flags", df["day"], t_end)
    return df


def tbis_array(days, syms, df):
    """(T, S) bool of the flagged symbol-days that exist in this data -> (array, how many rows matched)"""
    arr = np.zeros((len(days), len(syms)), bool)
    if df is None or not len(df):
        return arr, 0
    row = pd.DatetimeIndex(days).get_indexer(pd.DatetimeIndex(df["day"]))
    col = pd.Index(syms).get_indexer(df["symbol"].astype(str))
    ok = (row >= 0) & (col >= 0)
    arr[row[ok], col[ok]] = True
    return arr, int(ok.sum())


def read_audit(path=None):
    """OUT\\ddw_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame (+ leg), or None when there is no file yet. [O3 (ii)] a data_event row removes that name-period from the cell AND the
    null before anything is computed. CHOICE: the date is the position's FILL date (L1: the session after the rank session) or the session itself (L2) - exactly the 'date' of ddw_audit_candidates.csv; a row
    names a CELL but a data event belongs to the name-period, so it covers both cells of that leg. Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "ddw_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: ddw_audit.csv lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: ddw_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    df["leg"] = df["cell"].str[:2]
    return df


def asset_status(path=None):
    """symbol -> 'active' | 'inactive' from the SIPORB asset list (today's status: a name that later went inactive is a survivorship fact, not a point-in-time one)"""
    p = path or S.path_of("assets.csv")
    if not os.path.exists(p):
        return {}
    a = pd.read_csv(p, dtype=str, keep_default_na=False)
    return dict(zip(a["symbol"], a["status"]))


# ------------------------------------------------------------------ the world: base arrays on D.days x the names that are ever in the universe, plus everything derived from them
class World:
    """days, syms, and (T, S) arrays: raw open Od / close Cl / volume Vv, the split factor F (raw / split-adjusted OPEN), the universe U, registered splits chg, gap-scan flags msplit, TBIS flags, the 09:30 bar's close
    C5 and Relative Volume RV; es = the ES prints (ret, gap, k per session). derive() adds the split-safe prices (Ao, Ac = raw / F), daily returns Rn, the raw overnight ratio Rg, the news flags (NW, NWU)
    and the hygiene tallies; aud1 / aud2 (the hand audit's data events, L1 / L2) start empty"""
    def __init__(self, days, syms, Od, Cl, Vv, F, U, chg, msplit, tbis, C5, RV, es, o5days=()):
        self.days, self.syms, self.T, self.S = pd.DatetimeIndex(days), np.asarray(syms), len(days), len(syms)
        self.Od, self.Cl, self.Vv, self.F, self.U, self.chg, self.msplit, self.tbis, self.C5, self.RV, self.es = Od, Cl, Vv, F, U, chg, msplit, tbis, C5, RV, es
        self.o5days = list(o5days)
        self.derive()
        self.aud1, self.aud2, self.aud_hit = np.zeros((self.T, self.S), bool), np.zeros((self.T, self.S), bool), set()

    def derive(self):
        sp = SPEC
        with np.errstate(invalid="ignore", divide="ignore"):
            self.Ao, self.Ac = self.Od / self.F, self.Cl / self.F              # split-safe prices: raw / F, F per session from the open ratio
            self.Rn = self.Ac / shift1(self.Ac) - 1.0                          # split-safe daily close-to-close returns (the beta's regressand)
            self.Rg = self.Od / shift1(self.Cl)                                # the raw overnight ratio: the open over the prior raw close (the gap scan's R)
            self.m20 = roll_prev(self.Vv, sp["news_n"])                        # the news baseline: mean volume of the previous 20 sessions, all present
            fin = np.isfinite(self.m20) & np.isfinite(self.Vv)
            self.NW = fin & (self.Vv >= sp["news_x"] * self.m20)               # news proxy: a session with volume >= 3x the name's previous 20-session mean
            self.NWU = ~fin                                                    # no baseline: news unknown (counted, and excluded from a no-news book)
            jump = np.isfinite(self.Rg) & (np.abs(self.Rg - 1.0) > 0.5) & ~self.chg      # a raw overnight gap beyond +-50% with no split-factor change (spin-off / bad print)
        self.fl = (self.chg, self.msplit, self.tbis, jump)                      # the four hygiene reasons, in HYG's order
        self.hcs = [np.vstack([np.zeros((1, self.S), np.int32), np.cumsum(f, axis=0, dtype=np.int32)]) for f in self.fl]
        k = np.asarray(self.es.k, float)
        self.k, self.kz = k, np.where(np.isfinite(k), k, 0.0)                   # CHOICE: an S position needs k_t; undefined k = no position (zero notional), never a silent 1.0

    def hyg(self, a, b, cols):
        """(4, n) bool: which hygiene reasons fall on a session in rows a .. b (inclusive) for the names `cols`"""
        a, b = max(int(a), 0), min(int(b), self.T - 1)
        if b < a:
            return np.zeros((4, len(cols)), bool)
        return np.stack([(h[b + 1, cols] - h[a, cols]) > 0 for h in self.hcs])

    def betas(self, t, cols):
        """OLS slope of each name's split-safe daily returns on ES's over the 60 sessions t-60 .. t-1, all 60 present for the name AND for ES (else NaN) - the registered rule (SPEC beta_min = 60). With the opt-in
        beta_min < 60 the sessions on which ES's return is undefined are dropped from the regression for every name, provided at least beta_min sessions remain; a NAME still needs every remaining session"""
        n = SPEC["beta_n"]
        out = np.full(len(cols), np.nan)
        if t < n + 1:
            return out
        keep = np.isfinite(self.es.ret[t - n:t])
        if keep.sum() < SPEC["beta_min"]:
            return out
        m = self.es.ret[t - n:t][keep]
        R = self.Rn[t - n:t][keep][:, cols]
        ok = np.isfinite(R).all(axis=0)
        mc = m - m.mean()
        den = float(mc @ mc)
        if not den > 0 or not ok.any():
            return out
        Rok = R[:, ok]
        out[ok] = (mc @ (Rok - Rok.mean(axis=0))) / den
        return out


def es_blind(W):
    """the L2 sessions on which NO name can have a beta because of ES alone: fewer than beta_min of the 60 previous ES returns are defined (a hole in the ES master blinds the 60 sessions after it under the registered
    all-present rule). -> (T,) bool, and the dates of the sessions whose ES return is undefined (the first session has none by construction)"""
    n, r = SPEC["beta_n"], np.asarray(W.es.ret, float)
    good = np.r_[0, np.cumsum(np.isfinite(r))]
    cnt = np.full(W.T, -1)
    for t in range(n + 1, W.T):
        cnt[t] = good[t] - good[t - n]
    holes = np.flatnonzero(~np.isfinite(r))
    return cnt < SPEC["beta_min"], W.days[holes[holes > 0]]


def release(D):
    """free what this harness never reads again from an r5_siporb.Data once the World is built (the big (T, S) arrays); the sessions, o5days and the coverage already taken stay"""
    for a in ("Od", "atr", "chg", "sw", "P", "msplit", "mexp", "mflags", "need", "O5", "H5", "L5", "C5", "V5", "RV"):
        if hasattr(D, a):
            delattr(D, a)


def load_daily(D, t_end):
    """the raw close, raw volume and the split factor on D.days x D.syms, re-read from the two daily caches (r5_siporb.read_long cuts them to dates < t_end at read time; Data deletes them after use).
    F = raw open / split-adjusted open (SIPORB's split factor)"""
    shape = (len(D.days), len(D.syms))
    raw = S.read_long("raw", t_end)
    assert_cut("daily_raw", raw["date"], t_end)
    ax = A13.align(D, raw)
    Cl, Vv = A13.fill(shape, raw["c"].to_numpy(float), ax), A13.fill(shape, raw["v"].to_numpy(float), ax)
    del raw
    spl = S.read_long("split", t_end)
    assert_cut("daily_split", spl["date"], t_end)
    Os = A13.fill(shape, spl["o"].to_numpy(float), A13.align(D, spl))
    del spl
    with np.errstate(invalid="ignore", divide="ignore"):
        F = D.Od / Os
    return Cl, Vv, F


def build_world(D, t_end, es_frames, tbis_df, sp=None):
    """r5_siporb.Data (cut at t_end) + the re-read arrays + ES + TBIS -> World on the names that are ever in the universe (the other columns are dropped: nothing downstream can use them, and the
    (T, S) arrays shrink by a large factor). The universe is computed on every name first, then the columns are cut"""
    sp = sp or SPEC
    Cl, Vv, F = load_daily(D, t_end)
    U = universe_mask(Cl, Vv, D.atr, D.chg, sp)
    cols = np.flatnonzero(U.any(axis=0))
    sub = lambda a: np.ascontiguousarray(a[:, cols])
    syms = D.syms[cols]
    tb, nmatch = tbis_array(D.days, syms, tbis_df)
    pa, pr = es_prints(es_frames["adj"]), es_prints(es_frames["raw"])
    W = World(D.days, syms, sub(D.Od), sub(Cl), sub(Vv), sub(F), sub(U), sub(D.chg), sub(D.msplit), tb, sub(D.C5), sub(D.RV), es_series(D.days, pa, pr), D.o5days)
    W.tbis_rows = (0 if tbis_df is None else len(tbis_df), nmatch)
    W.es_cov = {"adj_prints": pa, "raw_prints": pr}
    return W


# ------------------------------------------------------------------ the large-move cross-check [O3 (i)] and the attribution of a name's first removal
def xchk_tests(R, vr, fchg, sp=None):
    """the three tests on a move: R = its raw price ratio (open / prior close), vr = its volume ratio, fchg = the split factor moved over the window. (1) the raw and split-adjusted series disagree (a factor
    change); (2) R is a whole ratio - r5_siporb.missed_split_flags's own rule (|R - 1| > 25%, within 2% of a whole k or 1/k, k <= 50); (3) the move's volume jumps by about the inverse of its price ratio
    (|vr x R - 1| <= 0.25 - TBIS's volume test). CHOICE: (3) needs a move of at least 25% (the gap scan's floor, and every TBIS candidate is one): below it a price ratio near 1 makes vr x R just vr, so
    the test would flag every ordinary high-volume day. -> (f1, f2, f3) bool arrays; a position 'disagrees' when any fires"""
    sp = sp or SPEC
    R = np.asarray(R, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        f2 = S.missed_split_flags(R[:, None], np.zeros((len(R), 1), bool))[:, 0]
        f3 = np.isfinite(R) & np.isfinite(vr) & (np.abs(R - 1.0) > sp["xchk_floor"]) & (np.abs(vr * R - 1.0) <= sp["xchk_vol"])
    return np.asarray(fchg, bool), f2, f3


def attribute(reasons, n):
    """the index of the FIRST reason that removes each of n names (-1 = it survives every one); reasons = [(label, bool array)] in the order they are applied"""
    first = np.full(n, -1)
    for q, (_, m) in enumerate(reasons):
        first = np.where((first < 0) & np.asarray(m, bool), q, first)
    return first


def tally(cnt, reasons, first):
    for q, (label, _) in enumerate(reasons):
        cnt[label] += int((first == q).sum())
    cnt["pool"] += int((first == -1).sum())


# ------------------------------------------------------------------ L1: the weekly reversal [M1, T4, O1, O2]
def l1_schedule(days):
    """(rank rows r, fill rows f = r + 1, exit rows x): the rank session is each ISO week's last session, the fill is the NEXT session's official open (so the print that makes the signal is never the fill
    price - the skip that removes bid-ask bounce, ORB B1), and a position is held to the NEXT rebalance's fill (the following week's first opening print). x = -1: the next rebalance's fill is past the
    stage's data (unresolved: out of the cell AND the null, counted). A rank session with no session after it cannot fill and is not a rebalance"""
    iso = pd.DatetimeIndex(days).isocalendar()
    key = iso["year"].to_numpy("int64") * 100 + iso["week"].to_numpy("int64")
    last = np.flatnonzero(np.r_[key[1:] != key[:-1], True])
    r = last[last + 1 < len(days)]
    f = r + 1
    return r, f, np.r_[f[1:], -1]


def l1_xchk(W, r, cols, big):
    """the cross-check for the names cols[big] (|signal| > 25%): the move's session = the one of the 5 ranking sessions with the largest |raw open / prior raw close - 1|; its volume ratio = that session's raw volume over
    the mean of the 20 sessions before it. -> (fail (n,), parts (3, n) = the three tests)"""
    sp = SPEC
    n5 = sp["ret_n"]
    fail, parts = np.zeros(len(cols), bool), np.zeros((3, len(cols)), bool)
    if not big.any():
        return fail, parts
    bc = cols[big]
    G = W.Rg[r - n5 + 1:r + 1][:, bc]
    dev = np.where(np.isfinite(G), np.abs(G - 1.0), -1.0)
    j = dev.argmax(axis=0)
    ar = np.arange(len(bc))
    Rs = np.where(dev[j, ar] >= 0, G[j, ar], np.nan)
    srow = r - n5 + 1 + j
    with np.errstate(invalid="ignore", divide="ignore"):
        vr = W.Vv[srow, bc] / W.m20[srow, bc]
        fch = W.chg[r - n5 + 1:r + 1][:, bc].any(axis=0) | (np.abs(W.F[r, bc] / W.F[r - n5, bc] - 1.0) > 0.01)
    p = np.stack(xchk_tests(Rs, vr, fch, sp))
    parts[:, big] = p
    fail[big] = p.any(axis=0)
    return fail, parts


def unit_path(O, C, f, x, cols):
    """one long of $1 per name over rows f .. x on the price source (O, C): split-safe (Ao, Ac) or naive raw (Od, Cl). Entry at the open of f, a mark at every close of rows f .. x-1 (a missing bar CARRIES the
    last mark), exit at the open of x. A name with no open at x has STOPPED PRINTING [O6]: it exits at its last mark (carried) and `st` says so. -> G (n, H) = gross daily P&L per $1 (column h = row f+h; the
    last column is the exit session: exit open - prior close), ve = exit value per $1 of entry, st, mk (n, H) = the mark at the PRIOR close of each row (borrow's base)"""
    n, H = len(cols), x - f + 1
    of = O[f, cols]
    M = np.empty((H, n))
    M[0] = of
    M[1:] = C[f:x, cols]
    ix = np.where(np.isfinite(M), np.arange(H)[:, None], 0)
    np.maximum.accumulate(ix, axis=0, out=ix)
    M = M[ix, np.arange(n)[None, :]]
    ox = O[x, cols]
    st = ~np.isfinite(ox)
    xv = np.where(st, M[H - 1], ox)
    G = np.empty((n, H))
    with np.errstate(invalid="ignore", divide="ignore"):
        G[:, :H - 1] = (M[1:] - M[:-1]).T / of[:, None]
        G[:, H - 1] = (xv - M[H - 1]) / of
        return SimpleNamespace(G=G, ve=xv / of, st=st, mk=(M / of).T)


def l1_units(W, f, x, cols, naive=None):
    """unit_path on the split-safe series; the names flagged `naive` (the look-ahead variant [O3]: a flag fell INSIDE the hold, after the decision, and the position is kept) on the raw series instead"""
    ua = unit_path(W.Ao, W.Ac, f, x, cols)
    if naive is None or not naive.any():
        return ua
    ur, m = unit_path(W.Od, W.Cl, f, x, cols), naive[:, None]
    return SimpleNamespace(G=np.where(m, ur.G, ua.G), ve=np.where(naive, ur.ve, ua.ve), st=np.where(naive, ur.st, ua.st), mk=np.where(m, ur.mk, ua.mk))


def l1_cfg(bps=COST_BPS, borrow=(BORROW, None), lose100=False, squeeze=False):
    return {"bps": bps, "borrow": borrow, "lose100": lose100, "squeeze": squeeze}


def l1_pnl(U, idx, side, cfg, kt=None, sq=None):
    """per $1 of ENTRY notional, the daily P&L (n, H) of the positions `idx` (side +1 long / -1 short) over rows f .. x: the gross marks (U.G), cfg['bps'] of the notional at the fill and of the exit value at the
    exit, and for shorts the borrow: rate / 252 x the prior close's mark on every session after the fill session (CHOICE: the night before each of rows f+1 .. x; the weekend counts once), the base rate
    0.25% a year, the stress rate replacing it on sessions with k_t > 1.5 [M3]. lose100: a LONG in a name that stopped printing is valued at 0 - its last mark is lost and nothing is sold, so no exit cost [O6].
    sq: the shorts that pay the squeezed-winner rate (20% a year) all hold [O5]"""
    G, ve, st, mk = U.G[idx], U.ve[idx], U.st[idx], U.mk[idx]
    n, H = G.shape
    P = side * G
    c = cfg["bps"] * 1e-4
    P[:, 0] -= c
    cost = c * ve
    if side > 0 and cfg.get("lose100"):
        P[:, H - 1] = np.where(st, -mk[:, H - 1], P[:, H - 1])
        cost = np.where(st, 0.0, cost)
    P[:, H - 1] -= cost
    if side < 0:
        base, stress = cfg["borrow"]
        rate = np.full((n, H), base)
        if stress is not None and kt is not None:
            with np.errstate(invalid="ignore"):
                rate = np.where((np.asarray(kt) > K_STRESS)[None, :], stress, rate)
        if sq is not None and cfg.get("squeeze"):
            rate[np.asarray(sq, bool), :] = SQUEEZE_RATE
        P[:, 1:] -= rate[:, 1:] / 252.0 * mk[:, 1:]
    return P


def l1_one(W, r, f, x, post_mode, news_mode, units=True):
    """one rebalance: the universe at the fill session f (sessions < f only), the ranking return through the rank close r, every removal in order, the pool, the 25 / 25 picks and their paths -> (rec, counts).
    post_mode 'remove' = the registered reading: a hygiene flag ANYWHERE in the window (5 sessions before the ranking window through the exit) removes the name BEFORE the ranking, so a flagged jumper never
    takes a slot (this uses the hold's future - the look-ahead removal [O3] - and is the verdict); 'naive' = only flags known at the decision (rows <= r) remove, a name flagged INSIDE the hold (rows r+1 .. x)
    stays in the pool at its naive raw P&L. news_mode 'exclude' = the book; 'only' = the twin made of the news-excluded names (Chan 2003: their reversal should be weaker) - report only"""
    sp = SPEC
    n5, nn = sp["ret_n"], sp["l1_n"]
    uni = np.flatnonzero(W.U[f])
    rec = SimpleNamespace(r=r, f=f, x=x, traded=False, pool=np.zeros(0, np.int64), sig=np.zeros(0), naive=np.zeros(0, bool), nu=len(uni))
    cnt = Counter()
    cnt["rebalances"] += 1
    cnt["universe"] += len(uni)
    if not len(uni):
        cnt["empty"] += 1
        return rec, cnt
    with np.errstate(invalid="ignore", divide="ignore"):
        sig = W.Ac[r, uni] / W.Ac[r - n5, uni] - 1.0
    m_sig = np.isfinite(sig)
    dm = sig - (float(np.mean(sig[m_sig])) if m_sig.any() else 0.0)             # CHOICE: the signal is the return minus the universe mean (over the finite ones); ranks do not change, the 25% / 30% tests read it
    m_fill = np.isfinite(W.Ao[f, uni])                                          # CHOICE: a name with no open (or no factor) at the fill session cannot be filled: not eligible, counted
    nr = slice(r - n5 + 1, r + 1)
    news, nunk = W.NW[nr][:, uni].any(axis=0), W.NWU[nr][:, uni].any(axis=0)   # a news session among the 5 ranking sessions; CHOICE: no 20-session baseline = news unknown = excluded from a no-news book
    bad_news = (nunk | news) if news_mode == "exclude" else (nunk | ~news)
    pre = W.hyg(r - (n5 - 1) - sp["hyg_lead"], r, uni)                          # flags from 5 sessions before the ranking window through the decision (the rank close)
    post = W.hyg(r + 1, x, uni)                                                 # flags inside the hold: the fill session through the exit session
    pre_any, post_any = pre.any(axis=0), post.any(axis=0)
    base = m_sig & m_fill & ~bad_news
    big = base & (np.abs(dm) > sp["xchk_l1"])
    xf, parts = l1_xchk(W, r, uni, big)
    aud = W.aud1[f, uni]
    W.aud_hit.update(("L1", f, int(c)) for c in uni[aud])
    reasons = [("no_signal", ~m_sig), ("no_fill", ~m_fill), ("news_unknown", nunk), ("news" if news_mode == "exclude" else "not_news", news if news_mode == "exclude" else ~news)]
    reasons += [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)] + [("xchk", xf)] + [(f"post_{h}", post[q]) for q, h in enumerate(HYG)] + [("audit", aud)]
    tally(cnt, reasons, attribute(reasons, len(uni)))
    cnt["xchk_checked"] += int(big.sum())
    for q in range(3):
        cnt[f"xchk_f{q + 1}"] += int(parts[q].sum())
    cnt["xchk_disagree"] += int(xf.sum())
    pool_k = base & ~pre_any & ~xf & ~aud
    pool = (pool_k & ~post_any) if post_mode == "remove" else pool_k
    pidx = np.flatnonzero(pool)
    rec.pool, rec.sig = uni[pidx], dm[pidx]
    rec.naive = post_any[pidx] if post_mode == "naive" else np.zeros(len(pidx), bool)
    if len(pidx) >= 2 * nn:                                                     # CHOICE: a rebalance trades only when both sides can be filled to 25 (>= 50 eligible names)
        o = np.lexsort((rec.pool, rec.sig))                                     # ascending signal, ties by symbol order: the 25 lowest are the longs, the 25 highest the shorts
        rec.long, rec.short, rec.traded = o[:nn], o[::-1][:nn], True
        if units:                                                               # (dryload builds the pools only to count them: no path, no P&L)
            rec.U = l1_units(W, f, x, rec.pool, rec.naive)
    else:
        cnt["small_pool"] += 1
    return rec, cnt


def l1_build(W, lo, hi, post_mode="remove", news_mode="exclude", units=True):
    """every L1 rebalance whose position EXITS inside [lo, hi] (CHOICE: a position belongs to the stretch its exit session falls in, as the house stretches are written; its marks before the stretch's first
    row fall outside the series - at most the first week - and a position whose exit is past the stage's data is unresolved: out of the cell AND the null, counted) -> Leg(kind, recs, cnt by fill year)"""
    r_all, f_all, x_all = l1_schedule(W.days)
    recs, cnt = [], defaultdict(Counter)
    for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()):
        if x < 0:
            cnt[int(W.days[f].year)]["unresolved"] += 1
            continue
        if not (lo <= W.days[x] <= hi) or r < SPEC["ret_n"]:
            continue
        rec, c = l1_one(W, r, f, x, post_mode, news_mode, units)
        recs.append(rec)
        cnt[int(W.days[f].year)].update(c)
    return SimpleNamespace(kind="L1", recs=recs, cnt=cnt)


def l1_cell(W, L, kind, cfg, side=0, drop_sq=False, pos=False):
    """a cell's daily P&L on the stock sessions (T,), the positions held per row, and (pos=True) the per-position table. F: $4,000 a name; S: x k at the FILL session, held all week (shares fixed); a rebalance whose
    k is undefined holds nothing in S. side +1 / -1: the long or the short book alone. drop_sq: the squeezed-winner variant that drops the L1 shorts whose signal exceeds +30% [O5]"""
    T = W.T
    x, cnt, n_pos, n_units, rows = np.zeros(T), np.zeros(T), 0, 0, []
    for ri, rec in enumerate(L.recs):
        if not rec.traded:
            continue
        notional = SPEC["l1_slot"] * (1.0 if kind == "F" else W.kz[rec.f])
        if not notional > 0:
            continue
        kt = W.k[rec.f:rec.x + 1]
        tot, n = np.zeros(rec.x - rec.f + 1), 0
        for sd, idx in ((1, rec.long), (-1, rec.short)):
            if side and sd != side:
                continue
            if drop_sq and sd < 0:
                idx = idx[rec.sig[idx] <= SPEC["squeeze"]]
            if not len(idx):
                continue
            P = l1_pnl(rec.U, idx, sd, cfg, kt, (rec.sig[idx] > SPEC["squeeze"]) if sd < 0 else None)
            tot += P.sum(axis=0)
            n += len(idx)
            if pos:
                rows.append((np.full(len(idx), ri), rec.pool[idx], np.full(len(idx), sd), notional * P.sum(axis=1), rec.sig[idx]))
        x[rec.f:rec.x + 1] += notional * tot
        cnt[rec.f:rec.x + 1] += n
        n_pos, n_units = n_pos + n, n_units + 1
    tab = None
    if pos:
        tab = SimpleNamespace(**{k: (np.concatenate([r_[q] for r_ in rows]) if rows else np.zeros(0)) for q, k in enumerate(("rec", "col", "side", "pnl", "sig"))})
    return SimpleNamespace(x=x, cnt=cnt, n_pos=n_pos, n_units=n_units, pos=tab)


# ------------------------------------------------------------------ L2: the no-news gap fade [T1, O1]
def l2_one(W, t, post_mode, news_mode):
    """one session t: the universe (sessions < t only) with a 09:30 bar, Relative Volume < 2 (and no news session on t-1 - CHOICE from the prereg's 'also': a news proxy is a volume session >= 3x its baseline OR a 09:30
    Relative Volume >= 2), a beta, the raw gap = 09:35 price / prior raw close (split-safe) - 1, the ADJUSTED gap = raw gap - beta x ES's gap; the 20 most negative are longs, the 20 most positive shorts,
    only |adjusted gap| >= 1%, and the session trades only if both sides fill all 20. Hygiene window: CHOICE rows t-6 .. t, the ranking window being t-1 .. t; flags on rows t-6 .. t-1 are known at the decision, the
    flags ON session t are the hold's (day-level facts - the day's volume, TBIS - are not all known at 09:35). post_mode / news_mode as in l1_one"""
    sp = SPEC
    nn = sp["l2_n"]
    uni = np.flatnonzero(W.U[t])
    rec = SimpleNamespace(t=t, traded=False, pool=np.zeros(0, np.int64), adj=np.zeros(0), raw=np.zeros(0), beta=np.zeros(0), ratio=np.zeros(0), naive=np.zeros(0, bool), nu=len(uni))
    cnt = Counter()
    cnt["sessions"] += 1
    cnt["universe"] += len(uni)
    esg = W.es.gap[t] if t >= 1 else np.nan
    if not len(uni):
        cnt["empty"] += 1
        return rec, cnt
    if not np.isfinite(esg):
        cnt["no_es"] += 1
        return rec, cnt
    c5, rv = W.C5[t, uni], W.RV[t, uni]
    has5, has_rv = np.isfinite(c5), np.isfinite(rv)
    with np.errstate(invalid="ignore"):
        news = (rv >= sp["rv_max"]) | W.NW[t - 1, uni]                          # RV >= 2, or a news session on the prior day
    nunk = W.NWU[t - 1, uni]
    beta = W.betas(t, uni)
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = (c5 / W.F[t, uni]) / W.Ac[t - 1, uni] - 1.0                       # split-safe: both prices on the same adjusted basis
        adj = raw - beta * esg
        ratio = W.Cl[t, uni] / c5                                               # the official close over the 09:35 price (both raw, one session: split-free)
    m_price = np.isfinite(raw) & np.isfinite(ratio)                             # CHOICE: a name with no daily close / factor on t cannot exit or be measured: not eligible, counted
    bad_news = news if news_mode == "exclude" else ~news
    base = has5 & has_rv & ~nunk & ~bad_news & np.isfinite(beta) & m_price
    big = base & (np.abs(raw) > sp["xchk_l2"])
    xf, parts = np.zeros(len(uni), bool), np.zeros((3, len(uni)), bool)
    if big.any():
        bc = uni[big]
        with np.errstate(invalid="ignore", divide="ignore"):
            R35 = c5[big] / W.Cl[t - 1, bc]                                     # the raw 09:35 price over the prior raw close: what an unadjusted split would show
            fch = W.chg[t, bc] | (np.abs(W.F[t, bc] / W.F[t - 1, bc] - 1.0) > 0.01)
        p = np.stack(xchk_tests(R35, rv[big], fch, sp))                         # for L2 the 09:30 Relative Volume stands in for the volume ratio
        parts[:, big] = p
        xf[big] = p.any(axis=0)
    pre = W.hyg(t - 1 - sp["hyg_lead"], t - 1, uni)
    post = W.hyg(t, t, uni)
    pre_any, post_any = pre.any(axis=0), post.any(axis=0)
    aud = W.aud2[t, uni]
    W.aud_hit.update(("L2", t, int(c)) for c in uni[aud])
    reasons = [("no_open5", ~has5), ("no_rv", ~has_rv), ("news_unknown", nunk), ("news" if news_mode == "exclude" else "not_news", bad_news), ("no_beta", ~np.isfinite(beta)), ("no_price", ~m_price)]
    reasons += [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)] + [("xchk", xf)] + [(f"post_{h}", post[q]) for q, h in enumerate(HYG)] + [("audit", aud)]
    tally(cnt, reasons, attribute(reasons, len(uni)))
    cnt["xchk_checked"] += int(big.sum())
    for q in range(3):
        cnt[f"xchk_f{q + 1}"] += int(parts[q].sum())
    cnt["xchk_disagree"] += int(xf.sum())
    pool_k = base & ~pre_any & ~xf & ~aud
    pool = (pool_k & ~post_any) if post_mode == "remove" else pool_k
    pidx = np.flatnonzero(pool)
    rec.pool, rec.adj, rec.raw, rec.beta, rec.ratio = uni[pidx], adj[pidx], raw[pidx], beta[pidx], ratio[pidx]
    rec.naive = post_any[pidx] if post_mode == "naive" else np.zeros(len(pidx), bool)
    if len(pidx) >= 2 * nn:
        o = np.lexsort((rec.pool, rec.adj))                                     # ascending adjusted gap, ties by symbol order
        lg, sh = o[:nn], o[::-1][:nn]
        if rec.adj[lg].max() <= -sp["gap_min"] and rec.adj[sh].min() >= sp["gap_min"]:   # only |adjusted gap| >= 1%, and both sides must fill all 20
            rec.long, rec.short, rec.traded = lg, sh, True
        else:
            cnt["thin_side"] += 1
    else:
        cnt["small_pool"] += 1
    return rec, cnt


def l2_build(W, lo, hi, post_mode="remove", news_mode="exclude"):
    """every L2 session in [lo, hi] -> Leg(kind, recs, cnt by year)"""
    recs, cnt = [], defaultdict(Counter)
    for t in range(1, W.T):
        if not (lo <= W.days[t] <= hi):
            continue
        rec, c = l2_one(W, t, post_mode, news_mode)
        recs.append(rec)
        cnt[int(W.days[t].year)].update(c)
    return SimpleNamespace(kind="L2", recs=recs, cnt=cnt)


def l2_pnl(ratio, side, adv_bps, ex_bps):
    """per $1 of notional at the 09:35 price: a buy fills at 09:35 x (1 + adverse), a sell at 09:35 x (1 - adverse) - that IS the entry cost [O7] - and the position exits at the official close C_t = ratio x the 09:35
    price, paying ex_bps of the exit value. long: ratio - 1 - adverse - cost x ratio; short: 1 - ratio - adverse - cost x ratio. Fractional shares: the notional is dollar-exact"""
    return side * (np.asarray(ratio, float) - 1.0) - adv_bps * 1e-4 - ex_bps * 1e-4 * np.asarray(ratio, float)


def l2_cell(W, L, kind, cfg, side=0, pos=False):
    """a cell's daily P&L on the stock sessions (T,), the positions held per row, and the per-position table: $5,000 a name (F) or x k_t (S); cfg = (entry adverse bps, exit bps)"""
    T = W.T
    x, cnt, n_pos, n_units, rows = np.zeros(T), np.zeros(T), 0, 0, []
    for ri, rec in enumerate(L.recs):
        if not rec.traded:
            continue
        notional = SPEC["l2_slot"] * (1.0 if kind == "F" else W.kz[rec.t])
        if not notional > 0:
            continue
        tot, n = 0.0, 0
        for sd, idx in ((1, rec.long), (-1, rec.short)):
            if side and sd != side:
                continue
            v = l2_pnl(rec.ratio[idx], sd, cfg[0], cfg[1])
            tot += float(v.sum())
            n += len(idx)
            if pos:
                rows.append((np.full(len(idx), ri), rec.pool[idx], np.full(len(idx), sd), notional * v, rec.adj[idx]))
        x[rec.t] += notional * tot
        cnt[rec.t] += n
        n_pos, n_units = n_pos + n, n_units + 1
    tab = None
    if pos:
        tab = SimpleNamespace(**{k: (np.concatenate([r_[q] for r_ in rows]) if rows else np.zeros(0)) for q, k in enumerate(("rec", "col", "side", "pnl", "sig"))})
    return SimpleNamespace(x=x, cnt=cnt, n_pos=n_pos, n_units=n_units, pos=tab)


# ------------------------------------------------------------------ the family-aware null [O4]
def draw_order(rng, nreps, n_pool, m):
    """nreps ORDERED uniform samples of m of n_pool names without replacement: the m smallest of n_pool i.i.d. uniform keys, in key order - so the first n of a sample and the rest are two DISJOINT uniform samples
    (CHOICE: a draw's longs and shorts never share a name; a name in both would net to nothing but cost)"""
    if not 0 < m <= n_pool:
        raise ValueError(f"cannot draw {m} of {n_pool}")
    return np.argsort(rng.random((nreps, n_pool)), axis=1)[:, :m]


def null_l1(W, L, nreps, rng):
    """per draw and per rebalance the cell traded: 25 longs and 25 shorts replaced by names drawn uniformly without replacement from that rebalance's eligible pool (same hygiene, news exclusion, sizing, fills,
    costs, borrow); the F and S cells use the same draw (S = F x k at the fill session). -> (accF, accS) (nreps, T) base-cost P&L by stock session"""
    nn, T = SPEC["l1_n"], W.T
    accF, accS = np.zeros((nreps, T)), np.zeros((nreps, T))
    cfg = l1_cfg()
    for rec in L.recs:
        if not rec.traded:
            continue
        idx = np.arange(len(rec.pool))
        kt = W.k[rec.f:rec.x + 1]
        PL, PS = l1_pnl(rec.U, idx, 1, cfg, kt), l1_pnl(rec.U, idx, -1, cfg, kt)
        o = draw_order(rng, nreps, len(idx), 2 * nn)
        g = SPEC["l1_slot"] * (PL[o[:, :nn]].sum(axis=1) + PS[o[:, nn:]].sum(axis=1))
        accF[:, rec.f:rec.x + 1] += g
        accS[:, rec.f:rec.x + 1] += W.kz[rec.f] * g
    return accF, accS


def null_l2(W, L, nreps, rng):
    """the same for L2: on every session the cell traded, 20 + 20 names drawn from that session's pool (NOT the |adjusted gap| >= 1% rule - that is the selection), base-cost P&L by stock session"""
    nn, T = SPEC["l2_n"], W.T
    accF, accS = np.zeros((nreps, T)), np.zeros((nreps, T))
    for rec in L.recs:
        if not rec.traded:
            continue
        vl, vs = l2_pnl(rec.ratio, 1, ADV_BPS, COST_BPS), l2_pnl(rec.ratio, -1, ADV_BPS, COST_BPS)
        o = draw_order(rng, nreps, len(rec.pool), 2 * nn)
        g = SPEC["l2_slot"] * (vl[o[:, :nn]].sum(axis=1) + vs[o[:, nn:]].sum(axis=1))
        accF[:, rec.t] += g
        accS[:, rec.t] += W.kz[rec.t] * g
    return accF, accS


# ------------------------------------------------------------------ onto #463's index, statistics, the seat measure (DO / rho_dd), the null's statistics
def to_B(x, rows, nb):
    """a series on the stock sessions (T,) -> #463's index (nb,): each session maps to one row, so this is an assignment (A13.book_rows refuses a session the book does not have)"""
    out = np.zeros(nb)
    out[rows] = x
    return out


def cell_stats(B, xB, cntB, lo, hi, run, years=YEARS):
    """one stretch [lo, hi] of a cell's daily series xB with cntB positions held per row. ROC @ $30k / Sortino / max drawdown: r11_risk.stats on the daily series (peak from 0, years = last - first row / 365.25 -
    the house yardstick); the July-June breadth; net without Feb 15 - Apr 30 2020; net without the best 1% of DAYS (the rows that hold a position) and without the best 1% of NAME-periods (L1: a weekly
    position; L2: a name-day - ceil like r13_attn.ceil_pct). The position-level numbers come from run.pos (the table of the stretch's positions, base cost) when it has one"""
    k = B.mask(lo, hi)
    xs, ds, cs = xB[k], B.index[k], cntB[k]
    st = R11.stats(xs, ds) or {}
    nan = float("nan")
    nets, npos = A13.breadth(xs, ds, years)
    keep = ~((ds >= X20[0]) & (ds <= X20[1]))
    days = xs[cs > 0]
    md = ceil_pct(len(days), RULES["best_pct"])
    out = {"n_pos": int(run.n_pos), "n_units": int(run.n_units), "net": float(xs.sum()), "years": st.get("years", nan), "max_dd": st.get("max_dd", nan), "roc": st.get("roc", nan),
           "sortino": st.get("sort", nan), "by_year": nets, "years_pos": int(npos), "net_ex2020": float(xs[keep].sum()), "days": int(len(days)), "best_days_n": int(md),
           "net_ex_best_days": float(xs.sum() - (np.sort(days)[::-1][:md].sum() if len(days) else 0.0))}
    pp = None if getattr(run, "pos", None) is None else np.asarray(run.pos.pnl, float)
    if pp is not None:
        mp = ceil_pct(len(pp), RULES["best_pct"])
        top = np.sort(pp)[::-1]
        out.update({"net_pos": float(pp.sum()), "best_pos_n": int(mp), "net_ex_best_pos": float(pp.sum() - top[:mp].sum()), "top_pos": float(top[0]) if len(pp) else nan,
                    "net_ex_top_pos": float(pp.sum() - (top[0] if len(pp) else 0.0))})
    return out


def seat_measure(S12, xB):
    """the cell's place on the MDL map against #463's qualifying drawdowns on the WF stretch, EXACTLY MDL r1's definitions (r12_mdl.realised on its Stretch): DO = the cell's P&L over the DD days / #463's loss over
    them; rho_dd = the correlation of weekly sums over the DD weeks. [O11] plus DO year by year (each DD day in its calendar year; a year in which #463 did not lose over its DD days has no DO - NaN, never
    positive) and DO without the episode whose DD days run 2020-03-03 .. 03-27"""
    x = np.asarray(xB, float)[S12.rows]
    rho, do = M12.realised(x[None, :], S12)
    yr, bk = S12.dates.year.to_numpy(), S12.x
    by = {}
    for y in DD_YEARS:
        m = S12.dd & (yr == y)
        loss = -float(bk[m].sum())
        by[y] = {"dd_days": int(m.sum()), "cell": float(x[m].sum()), "book_loss": loss, "DO": float(x[m].sum()) / loss if m.any() and loss > 0 else float("nan")}
    ex = S12.dd & ~((S12.dates >= EP20[0]) & (S12.dates <= EP20[1]))
    loss = -float(bk[ex].sum())
    return {"rho_dd": float(rho[0]), "DO": float(do[0]), "by_year": by, "years_pos": int(sum(1 for v in by.values() if v["DO"] > 0)), "DO_ex_episode": float(x[ex].sum()) / loss if loss > 0 else float("nan"),
            "dd_days": int(S12.n_dd_days), "dd_weeks": int(S12.n_dd_weeks)}


def null_cell(S12, acc, rows, nb):
    """a leg's null series (nreps, T) on the stock sessions -> the WF stretch's ROC @ $30k, rho_dd and DO of every draw (r12_mdl's vectorised twins of r11_risk.stats and the seat measure)"""
    Y = np.zeros((acc.shape[0], nb))
    Y[:, rows] = acc
    Y = Y[:, S12.rows]
    m = M12.vmeas(Y, S12.years)
    rho, do = M12.realised(Y, S12)
    return m["roc"], rho, do


def pctl(a, q):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return float(np.percentile(a, q)) if len(a) else float("nan")


def null_summary(per_cell):
    """[O4] per draw over the 4 cells: the MAX WF ROC @ $30k, the MAX WF DO, the MIN WF rho_dd (a cell that has the family's best draw is compared with the best of 4 random cells) -> p5 / p50 / p95 of each"""
    roc = np.fmax.reduce(np.vstack([v[0] for v in per_cell.values()]), axis=0)
    rho = np.fmin.reduce(np.vstack([v[1] for v in per_cell.values()]), axis=0)
    do = np.fmax.reduce(np.vstack([v[2] for v in per_cell.values()]), axis=0)
    mk = lambda a: {"p5": pctl(a, 5), "p50": pctl(a, 50), "p95": pctl(a, 95), "finite": int(np.isfinite(a).sum())}
    return {"draws": int(len(roc)), "seed": SEED, "roc_max": mk(roc), "do_max": mk(do), "rho_min": mk(rho)}


# ------------------------------------------------------------------ Stage A's checks (a) - (f) and A2
def judge_cell(cell, st, net_stress, seat, nul, twin):
    """(a) >= 100 name-periods AND >= 26 weekly rebalances (L1) / >= 60 traded sessions (L2) [M4]; (b) net > 0 at the base AND the first stress costs (L1: 5 and 10 bps a side; L2: entry 10 / exit 5 and entry 20 / exit 10)
    [O1, O7]; (c) WF ROC @ $30k above the null's 95th percentile (max over cells); (d) THE FAMILY'S POINT - DO above the null's 95th percentile (max over cells) AND rho_dd below its 5th (min over cells) AND DO > 0
    AND rho_dd < 0 AND [O11] DO > 0 in >= 4 of the 7 years AND DO > 0 without the 2020-03 episode; (e) positive in >= 6 of the 9 July-June years, net > 0 without Feb 15 - Apr 30 2020, profitable without its best 1% of
    days AND of name-periods; (f) [T3] an S cell beats its F twin on ROC AND Sortino. (g), the hand audit, is separate: audit_complete"""
    R, leg = RULES, cell[:2]
    units, ulab = (R["l1_reb"], "weekly rebalances") if leg == "L1" else (R["l2_days"], "traded sessions")
    nan = float("nan")
    chk = {f"name-periods>={R['n']}": st["n_pos"] >= R["n"], f"{ulab}>={units}": st["n_units"] >= units, "net>0 at base costs": (st["net"] > 0) if R["net_pos"] else True,
           "net>0 at the first stress costs": (net_stress > 0) if R["stress"] else True,
           "ROC>null p95": (st["roc"] > nul["roc_max"]["p95"]) if R["null"] else True,
           "DO>null p95": (seat["DO"] > nul["do_max"]["p95"]) if R["do_null"] else True, "rho_dd<null p5": (seat["rho_dd"] < nul["rho_min"]["p5"]) if R["rho_null"] else True,
           "DO>0": (seat["DO"] > 0) if R["do_pos"] else True, "rho_dd<0": (seat["rho_dd"] < 0) if R["rho_neg"] else True, f"DO>0 in >={R['dd_years']} of 7 years": seat["years_pos"] >= R["dd_years"],
           "DO>0 without the 2020-03 episode": (seat["DO_ex_episode"] > 0) if R["ex_episode"] else True,
           f"positive in >={R['years']} of 9 July-June years": st["years_pos"] >= R["years"], "net>0 without Feb 15 - Apr 30 2020": (st["net_ex2020"] > 0) if R["ex2020"] else True,
           "profitable without its best 1% of days": (st["net_ex_best_days"] > 0) if R["exbest"] else True,
           "profitable without its best 1% of name-periods": (st["net_ex_best_pos"] > 0) if R["exbest"] else True}
    if cell.endswith("S"):
        chk["S beats its F twin on ROC and Sortino"] = ((st["roc"] > twin["roc"]) and (st["sortino"] > twin["sortino"])) if R["twin"] else True
    return {k: bool(v) for k, v in chk.items()}


def book_at(B, xB, c, lo, hi):
    """#463's daily series + c x the cell's on [lo, hi]: ROC @ $30k / Sortino / net / max drawdown (r11_risk.stats, the house yardstick)"""
    k = B.mask(lo, hi)
    s = R11.stats((np.asarray(B.raw, float) + c * np.asarray(xB, float))[k], B.index[k]) or {}              # r11_risk.stats gives None for fewer than 2 rows: NaN here, never an exception
    nan = float("nan")
    return {"c": float(c), "roc": s.get("roc", nan), "sortino": s.get("sort", nan), "net": s.get("net", nan), "max_dd": s.get("max_dd", nan)}


def a2_cell(B, xB):
    """STAGE A2 (WF): BOOK #463 + c x the cell >= 1.05 x 93.81 (98.5005) with Sortino >= 3.816, where c is set by VOLATILITY, never picked on returns (MANAGER's XGAP review, edit 2): c = 25% x the std of #463's daily
    P&L over its index rows 2016-07-01 .. 2018-06-29 / the std of the cell's daily P&L (c = 1) on the same rows - so c x the cell's std over that window is exactly 25% of the book's. CHOICE: sample std (ddof 1;
    the ratio does not depend on it), over EVERY index row of the window (a row the cell holds nothing on is a zero day); a cell with no spread there (or no row) has no c: A2 fails, with the reason. The book at
    0.5c and 2c is reported, never judged. -> the A2 record: c, both stds, the window, the verdict, the two reported books"""
    k = B.mask(*A2_WIN)
    nan = float("nan")
    sb = float(np.std(np.asarray(B.raw, float)[k], ddof=1)) if k.sum() > 1 else nan
    sc = float(np.std(np.asarray(xB, float)[k], ddof=1)) if k.sum() > 1 else nan
    out = {"window": [f"{A2_WIN[0]:%Y-%m-%d}", f"{A2_WIN[1]:%Y-%m-%d}"], "rows": int(k.sum()), "target": A2_TARGET, "std_book": sb, "std_cell": sc, "c": nan, "pass": False, "roc": nan, "sortino": nan, "net": nan,
           "at_half_c": None, "at_double_c": None, "needs": {"roc": RULES["a2_roc"], "sortino": RULES["a2_sort"]}}
    if not (np.isfinite(sb) and np.isfinite(sc) and sb > 0 and sc > 0):
        out["error"] = "no c: the cell (or the book) has no spread over the window"
        return out
    c = A2_TARGET * sb / sc
    at = book_at(B, xB, c, WF0, PRE_END)
    out.update({"c": c, "roc": at["roc"], "sortino": at["sortino"], "net": at["net"], "max_dd": at["max_dd"], "pass": bool(at["roc"] >= RULES["a2_roc"] and at["sortino"] >= RULES["a2_sort"]),
                "at_half_c": book_at(B, xB, A2_REPORT[0] * c, WF0, PRE_END), "at_double_c": book_at(B, xB, A2_REPORT[1] * c, WF0, PRE_END)})
    return out


# ------------------------------------------------------------------ the hand audit [O3 (ii)]: the 50 largest single-name contributors, what the audit file says about them
def candidate_rows(W, L, cell, run, tbis_df, status, n=AUDIT_N):
    """the n largest single-name P&L contributors of a cell (CHOICE: 'contributors' = the largest GAINS, P&L descending - the name-periods that carry the profit; a fake loss only works against a pass, a fake gain
    for it) with what the hand audit needs: symbol, date (L1: the FILL session; L2: the session - the key ddw_audit.csv uses), exit, side, $, signal, the raw / split-adjusted move over the ranking window and the
    split factor's ratio across the position's whole life, the largest raw overnight move in the hold, TBIS's rows for the symbol in the window, the asset status, the hygiene reasons in the window"""
    p = run.pos
    if p is None or not len(p.pnl):
        return []
    sel = np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n]
    tb = None if tbis_df is None or not len(tbis_df) else tbis_df
    rows = []
    for rank, i in enumerate(sel, 1):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        if L.kind == "L1":
            a, f, x = rec.r - SPEC["ret_n"], rec.f, rec.x
            w0 = rec.r - (SPEC["ret_n"] - 1) - SPEC["hyg_lead"]
            raw_mv, adj_mv = W.Cl[rec.r, col] / W.Cl[a, col] - 1.0, W.Ac[rec.r, col] / W.Ac[a, col] - 1.0
            fr, d0, d1, hold = W.F[x, col] / W.F[a, col], W.days[f], W.days[x], (f, x)
        else:
            t = rec.t
            w0 = t - 1 - SPEC["hyg_lead"]
            raw_mv, adj_mv = W.C5[t, col] / W.Cl[t - 1, col] - 1.0, rec.raw[int(np.flatnonzero(rec.pool == col)[0])]
            fr, d0, d1, hold = W.F[t, col] / W.F[t - 1, col], W.days[t], W.days[t], (t, t)
            x = t
        gaps = W.Rg[hold[0]:hold[1] + 1, col]
        gaps = gaps[np.isfinite(gaps)]
        big = float(gaps[np.argmax(np.abs(gaps - 1.0))]) if len(gaps) else float("nan")
        sym = str(W.syms[col])
        ptb = [None, None, None]
        if tb is not None:
            m = tb[(tb["symbol"].astype(str) == sym) & (tb["day"] >= W.days[max(w0, 0)]) & (tb["day"] <= W.days[x])]
            if len(m):
                ptb = [float(m["price_ratio"].iloc[0]), float(m["vol_ratio"].iloc[0]) if pd.notna(m["vol_ratio"].iloc[0]) else float("nan"), str(m["split_like"].iloc[0])]
        fl = W.hyg(max(w0, 0), x, np.array([col]))[:, 0]
        rows.append({"cell": cell, "rank": rank, "symbol": sym, "date": f"{d0:%Y-%m-%d}", "exit": f"{d1:%Y-%m-%d}", "side": "long" if p.side[i] > 0 else "short", "pnl": float(p.pnl[i]),
                     "signal": float(p.sig[i]), "raw_move": float(raw_mv), "adj_move": float(adj_mv), "factor_ratio": float(fr), "max_overnight_raw_ratio_in_hold": big,
                     "tbis_price_ratio": ptb[0], "tbis_vol_ratio": ptb[1], "tbis_split_like": ptb[2], "asset_status": status.get(sym, "unknown"),
                     "flags_in_window": "+".join(h for h, v in zip(HYG, fl) if v)})
    return rows


def audit_status(cands, audit):
    """per cell: how many of the listed top-50 contributors appear in ddw_audit.csv (CHOICE: by symbol + date + LEG - a data event belongs to the name-period, so a row for L1-F also covers L1-S's listing of
    it); audit_complete = every listed one does"""
    have = set() if audit is None else set(zip(audit["symbol"], audit["date"].dt.strftime("%Y-%m-%d"), audit["leg"]))
    out = {}
    for cell, rows in cands.items():
        n = sum((r["symbol"], r["date"], cell[:2]) in have for r in rows)
        out[cell] = {"listed": len(rows), "audited": int(n), "audit_complete": bool(len(rows) > 0 and n == len(rows))}
    return out


# ------------------------------------------------------------------ one reading of Stage A: legs -> cells -> stress rows -> null -> checks -> A2
def run_cell(W, L, cell, cfg, **kw):
    """a cell's run through its leg's engine (cfg: an l1_cfg dict for L1, (entry bps, exit bps) for L2)"""
    kind = cell[3]
    return l1_cell(W, L, kind, cfg, **kw) if cell[:2] == "L1" else l2_cell(W, L, kind, cfg, **{k: v for k, v in kw.items() if k != "drop_sq"})


def evaluate(W, B, S12, rows, post_mode, nreps, vcode=0, full=False):
    """one reading of Stage A on the WF stretch. post_mode 'remove' = the REGISTERED reading (a hygiene flag inside the hold removes the position before the ranking), 'naive' = the look-ahead variant [O3]
    (those positions are kept at their naive raw P&L); both run the same code, so a flip between them is the data hygiene's doing. nreps > 0 draws the null (vcode picks its random streams). full = also the
    reports' rows (sides apart, borrow / squeeze / survivorship stress, the audit lists' positions). -> (summary, objects: legs, runs, series)"""
    lo, hi = WF0, PRE_END
    legs = {"L1": l1_build(W, lo, hi, post_mode), "L2": l2_build(W, lo, hi, post_mode)}
    runs, series, summ = {}, {}, {}

    def stat(run):
        xB, cB = to_B(run.x, rows, B.n), to_B(run.cnt, rows, B.n)
        return cell_stats(B, xB, cB, lo, hi, run), xB, cB

    for cell in CELLS:
        leg, L = cell[:2], legs[cell[:2]]
        cfgs = {"base": l1_cfg(), **{f"{b:g} bps": l1_cfg(bps=b) for b in STRESS_BPS}} if leg == "L1" else {"base": (ADV_BPS, COST_BPS), **{f"{a:g}/{c:g} bps": (a, c) for a, c in L2_STRESS}}
        first = "10 bps" if leg == "L1" else f"{L2_STRESS[0][0]:g}/{L2_STRESS[0][1]:g} bps"
        base = run_cell(W, L, cell, cfgs["base"], pos=True)
        st, xB, cB = stat(base)
        runs[cell], series[cell] = base, (xB, cB)
        stress = {nm: stat(run_cell(W, L, cell, cfg))[0] for nm, cfg in cfgs.items() if nm != "base"}
        c = {"base": st, "stress": stress, "first_stress": first, "seat": seat_measure(S12, xB)}
        if full:
            c["sides"] = {nm: stat(run_cell(W, L, cell, cfgs["base"], side=sd))[0] for nm, sd in (("long side only", 1), ("short side only", -1))}
            if leg == "L1":
                ex = {"borrow 1% on k>1.5 sessions": run_cell(W, L, cell, l1_cfg(borrow=(BORROW, BORROW_STRESS[0]))), "borrow 3% on k>1.5 sessions": run_cell(W, L, cell, l1_cfg(borrow=(BORROW, BORROW_STRESS[1]))),
                      "squeezed winners (short signal > +30%) pay 20% a year": run_cell(W, L, cell, l1_cfg(squeeze=True)), "squeezed winners dropped": run_cell(W, L, cell, l1_cfg(), drop_sq=True),
                      "longs that stop printing valued at -100%": run_cell(W, L, cell, l1_cfg(lose100=True))}
                c["extra"] = {nm: stat(r)[0] for nm, r in ex.items()}
                sh = to_B(run_cell(W, L, cell, l1_cfg(), side=-1).x, rows, B.n)
                shq = to_B(run_cell(W, L, cell, l1_cfg(squeeze=True), side=-1).x, rows, B.n)
                c["short_side_weeks"] = {lab: {"base": float(sh[(B.index >= a) & (B.index <= b)].sum()), "squeezed_20pct": float(shq[(B.index >= a) & (B.index <= b)].sum())} for lab, a, b in SQ_WEEKS}
        summ[cell] = c
    nul = None
    if nreps:
        r1, r2 = np.random.default_rng([SEED, 1, vcode]), np.random.default_rng([SEED, 2, vcode])
        acc = dict(zip(CELLS, null_l1(W, legs["L1"], nreps, r1) + null_l2(W, legs["L2"], nreps, r2)))
        nul = null_summary({cell: null_cell(S12, acc[cell], rows, B.n) for cell in CELLS})
    for cell in CELLS:
        c = summ[cell]
        twin = summ[cell[:3] + "F"]["base"] if cell.endswith("S") else None
        if nul is not None:
            c["checks"] = judge_cell(cell, c["base"], c["stress"][c["first_stress"]]["net"], c["seat"], nul, twin)
            c["PASS"] = bool(all(c["checks"].values()))
        c["A2"] = a2_cell(B, series[cell][0])
    return {"variant": post_mode, "cells": summ, "null": nul}, SimpleNamespace(legs=legs, runs=runs, series=series)


# ------------------------------------------------------------------ the reports (never a pass route)
def es_beta(B, S12, W, rows, xB, lags=5):
    """the realised beta to ES: the OLS slope (with a constant) of the cell's daily $ P&L on ES's daily return (the market's daily return from the 16:00 prints), on #463's DD days, on all the days of its DD weeks and
    on every WF day; $ per 1.00 of ES return (/ 100 = $ per 1% ES move), Newey-West t. CHOICE: P&L on ES's same-session return (a dollar beta, not a book beta)"""
    re = np.full(B.n, np.nan)
    re[rows] = W.es.ret
    r, x = re[S12.rows], np.asarray(xB, float)[S12.rows]
    wk = np.zeros(len(x), bool)
    wk[S12.wk_rows] = True
    out = {}
    for lab, m in (("DD days", S12.dd), ("DD weeks (every day of them)", wk), ("all WF days", np.ones(len(x), bool))):
        mm = m & np.isfinite(r)
        if mm.sum() < lags + 3 or not np.ptp(r[mm]) > 0:
            out[lab] = {"n": int(mm.sum()), "usd_per_1.00_es": float("nan"), "usd_per_1pct_es": float("nan"), "t_nw": float("nan")}
            continue
        b, t = R11.ols_nw(x[mm], np.column_stack([np.ones(mm.sum()), r[mm]]), lags)
        out[lab] = {"n": int(mm.sum()), "usd_per_1.00_es": float(b[1]), "usd_per_1pct_es": float(b[1]) / 100.0, "t_nw": float(t[1])}
    return out


def episodes_table(S12, xB):
    """each qualifying #463 drawdown: its dates, depth and the cell's P&L over its DD days"""
    x = np.asarray(xB, float)[S12.rows]
    return [{"peak": e["peak"], "first_dd_day": f"{S12.dates[e['i0']]:%Y-%m-%d}", "trough": e["trough"], "depth": e["depth"], "dd_days": int(e["it"] - e["i0"] + 1),
             "book_pnl": float(S12.x[e["i0"]:e["it"] + 1].sum()), "cell_pnl": float(x[e["i0"]:e["it"] + 1].sum())} for e in S12.qual]


def survivorship(W, L1, status):
    """[O6] L1: by EXIT year, the positions whose name stopped printing before the exit (they exit at their last print) split long / short, and the share of LONG positions in names the asset list now calls inactive"""
    by, nl, nin = defaultdict(Counter), 0, 0
    for rec in L1.recs:
        if not rec.traded:
            continue
        y = int(W.days[rec.x].year)
        for lab, idx in (("long", rec.long), ("short", rec.short)):
            by[y][f"{lab}_positions"] += len(idx)
            by[y][f"{lab}_stopped"] += int(rec.U.st[idx].sum())
        syms = W.syms[rec.pool[rec.long]]
        nl += len(syms)
        nin += sum(status.get(str(s), "") == "inactive" for s in syms)
    return {"by_exit_year": {y: dict(c) for y, c in sorted(by.items())}, "long_positions": nl, "long_in_inactive_names": nin, "share_long_in_inactive_names": nin / nl if nl else float("nan")}


def l2_exposure(W, L2, S12, rows, B):
    """L2's net dollar exposure and its beta to ES on every traded session: net $ = (longs - shorts) x notional (0 by construction: equal dollars, 20 a side), beta-weighted $ = notional x (sum of the longs' betas
    - the shorts'), and the day's ES return. -> (summary by year, the daily table)"""
    tab = []
    for rec in L2.recs:
        if not rec.traded:
            continue
        t = rec.t
        bl, bs = float(rec.beta[rec.long].sum()), float(rec.beta[rec.short].sum())
        tab.append({"date": f"{W.days[t]:%Y-%m-%d}", "long_n": len(rec.long), "short_n": len(rec.short), "net_usd_F": SPEC["l2_slot"] * (len(rec.long) - len(rec.short)),
                    "gross_usd_F": SPEC["l2_slot"] * (len(rec.long) + len(rec.short)), "beta_usd_F": SPEC["l2_slot"] * (bl - bs), "k": float(W.k[t]), "beta_usd_S": SPEC["l2_slot"] * W.kz[t] * (bl - bs),
                    "es_return": float(W.es.ret[t])})
    df = pd.DataFrame(tab)
    if not len(df):
        return {"traded_days": 0}, df
    df["year"] = df["date"].str[:4]
    by = {y: {"days": int(len(g)), "beta_usd_F_mean": float(g["beta_usd_F"].mean()), "beta_usd_F_sd": float(g["beta_usd_F"].std(ddof=0)), "beta_usd_F_min": float(g["beta_usd_F"].min()),
              "beta_usd_F_max": float(g["beta_usd_F"].max()), "net_usd_max_abs": float(g["net_usd_F"].abs().max())} for y, g in df.groupby("year")}
    return {"traded_days": int(len(df)), "beta_usd_F_mean": float(df["beta_usd_F"].mean()), "beta_usd_F_sd": float(df["beta_usd_F"].std(ddof=0)), "net_usd_F_max_abs": float(df["net_usd_F"].abs().max()),
            "by_year": by}, df.drop(columns="year")


def reports(W, B, S12, rows, legs, runs, series, summ, tbis_df, status, legs_meta):
    """everything the prereg's REPORTED paragraph lists, for the registered reading: the realised beta to ES in #463's drawdown weeks FIRST [M2], each cell's $ inside every qualifying episode, its place on the
    MDL map, the correlation with each #463 leg, the news-excluded names' own reversal (the twin book: Chan 2003 says weaker), the long and short sides apart, borrow / squeeze / survivorship, L2's exposure by
    day, the hygiene and large-move counts by reason and year, the 20 largest name-period gains (dates!), the cache manifest"""
    lo, hi = WF0, PRE_END
    rep = {"beta_to_es": {}, "episodes": {}, "map_point": {}, "corr_with_legs": {}, "news_twin": {}, "top20_gains": {}}
    cands = {}
    for cell in CELLS:
        xB = series[cell][0]
        rep["beta_to_es"][cell] = es_beta(B, S12, W, rows, xB)
        rep["episodes"][cell] = episodes_table(S12, xB)
        c = summ[cell]
        rep["map_point"][cell] = {"standalone_roc_30k": c["base"]["roc"], "rho_dd": c["seat"]["rho_dd"], "DO": c["seat"]["DO"]}
        rep["corr_with_legs"][cell] = A13.corrs(B, xB, legs_meta, lo, hi)
        cands[cell] = candidate_rows(W, legs[cell[:2]], cell, runs[cell], tbis_df, status)
        rep["top20_gains"][cell] = cands[cell][:20]
    for leg, slot in (("L1", SPEC["l1_slot"]), ("L2", SPEC["l2_slot"])):
        Ln = l1_build(W, lo, hi, "remove", "only") if leg == "L1" else l2_build(W, lo, hi, "remove", "only")
        run = run_cell(W, Ln, leg + "-F", l1_cfg() if leg == "L1" else (ADV_BPS, COST_BPS), pos=True)
        xn, cn = to_B(run.x, rows, B.n), to_B(run.cnt, rows, B.n)
        mine = runs[leg + "-F"]
        mean_bps = lambda r_: float(1e4 * r_.pos.pnl.sum() / (len(r_.pos.pnl) * slot)) if r_.pos is not None and len(r_.pos.pnl) else float("nan")
        rep["news_twin"][leg] = {"news_only_book": {**cell_stats(B, xn, cn, lo, hi, run), "mean_bps_per_name_period": mean_bps(run)}, "no_news_book": {"n_pos": summ[leg + "-F"]["base"]["n_pos"],
                                 "net": summ[leg + "-F"]["base"]["net"], "mean_bps_per_name_period": mean_bps(mine)},
                                 "note": "the same rules on the names the news proxy EXCLUDED (volume >= 3x its baseline in the ranking window / 09:30 Relative Volume >= 2 or a news session on t-1); weaker reversal expected"}
    rep["survivorship"] = survivorship(W, legs["L1"], status)
    rep["l2_exposure"], expo = l2_exposure(W, legs["L2"], S12, rows, B)
    rep["hygiene_counts_by_year"] = {leg: {y: dict(c) for y, c in sorted(legs[leg].cnt.items())} for leg in ("L1", "L2")}
    rep["manifest_sha256"] = manifest_sha()
    return rep, cands, expo


# ------------------------------------------------------------------ the book, its drawdown structure, the audit applied to the world
def book_checks(B):
    """#463 on the WF stretch: ROC / Sortino against 93.81 / 3.816 (A13.book_check), and the structure the prereg printed before any cell number [T5]: deepest drawdown $44,849, 28 qualifying episodes, 460 DD
    days, 92 DD weeks, the DD days by calendar year, and the episode whose DD days run 2020-03-03 .. 03-27 -> (book check, DD structure, M12.Stretch)"""
    bk = A13.book_check(B, WF0, PRE_END, BOOK_WF)
    S12 = M12.Stretch(B.raw, B.index, None, WF0, PRE_END)
    yr = S12.dates.year.to_numpy()
    dd = {"deepest": float(S12.episodes[0]["depth"]) if S12.episodes else float("nan"), "episodes": len(S12.qual), "days": int(S12.n_dd_days), "weeks": int(S12.n_dd_weeks),
          "by_year": {int(y): int((S12.dd & (yr == y)).sum()) for y in sorted(set(yr[S12.dd]))},
          "episode_2020": any(S12.dates[e["i0"]] == EP20[0] and S12.dates[e["it"]] == EP20[1] for e in S12.qual)}
    dd["ok"] = bool(abs(dd["deepest"] - DEEPEST_WF) < 1.0 and (dd["episodes"], dd["days"], dd["weeks"]) == (DD_REF["episodes"], DD_REF["days"], DD_REF["weeks"]) and dd["by_year"] == DD_REF["by_year"]
                    and dd["episode_2020"])
    return bk, dd, S12


def apply_audit(W, audit):
    """put the audit's data_event rows on the world as removals (L1 by fill session, L2 by session). A data_event row that matches no session or no name of this data refuses: a mistyped row must not silently
    do nothing. -> counts"""
    W.aud1[:] = False
    W.aud2[:] = False
    W.aud_hit.clear()
    if audit is None:
        return {"rows": 0, "keep": 0, "data_event": 0}
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    ev = (audit["verdict"] == "data_event").to_numpy()
    bad = np.flatnonzero(ev & ((di < 0) | (ci < 0)))
    if len(bad):
        refuse(f"refused: ddw_audit.csv data_event line(s) {[int(i) + 2 for i in bad][:10]} match no session or no name of this data (the date is the FILL session for L1, the session for L2; the symbol must be one "
               "the universe ever held) - fix the file (nothing computed, lockbox NOT read)")
    for i in np.flatnonzero(ev):
        (W.aud1 if audit["leg"].iat[i] == "L1" else W.aud2)[di[i], ci[i]] = True
    return {"rows": int(len(audit)), "keep": int((~ev).sum()), "data_event": int(ev.sum())}


def unused_audit_rows(W, audit):
    """data_event rows that removed nothing in the registered build (the name was not in that day's universe): reported, so a wrong date cannot pass unnoticed"""
    if audit is None:
        return []
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    return [f"{audit['symbol'].iat[i]} {audit['date'].iat[i]:%Y-%m-%d} {audit['cell'].iat[i]}" for i in range(len(audit))
            if audit["verdict"].iat[i] == "data_event" and (audit["leg"].iat[i], int(di[i]), int(ci[i])) not in W.aud_hit]


# ------------------------------------------------------------------ printing
def row(cell, c):
    s, q = c["base"], c["seat"]
    return (f"{cell:<5} positions {s['n_pos']:>6,} units {s['n_units']:>5,} net ${s['net']:>11,.0f} ROC@30k {s['roc']:>8.1f} Sortino {s['sortino']:>6.2f} maxDD ${s['max_dd']:>9,.0f} | "
            f"DO {q['DO']:>+7.3f} rho_dd {q['rho_dd']:>+6.3f} DO>0 in {q['years_pos']}/7 yrs, ex-2020-03 {q['DO_ex_episode']:>+7.3f}")


def print_cells(res, audit_st=None, title="registered"):
    nul = res["null"]
    print(f"  null ({nul['draws']} draws, seed {nul['seed']}, max / min over the 4 cells): ROC@30k p50 {nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f}; DO p50 {nul['do_max']['p50']:+.3f} p95 {nul['do_max']['p95']:+.3f}; "
          f"rho_dd p50 {nul['rho_min']['p50']:+.3f} p5 {nul['rho_min']['p5']:+.3f}")
    for cell in CELLS:
        c = res["cells"][cell]
        fails = [k for k, v in c["checks"].items() if not v]
        s2 = ", ".join(f"{k} net ${v['net']:,.0f}" for k, v in c["stress"].items())
        print("  " + row(cell, c))
        print(f"        stress: {s2}; by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items()))
        a2 = c["A2"]
        a2s = (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over {a2['window'][0]} .. {a2['window'][1]}): book ROC@30k {a2['roc']:.2f} Sortino {a2['sortino']:.3f} "
               f"(needs {RULES['a2_roc']:.4f} / {RULES['a2_sort']}) -> {'PASS' if a2['pass'] else 'FAIL'}; reported, never judged: at 0.5c ROC {a2['at_half_c']['roc']:.2f}, at 2c ROC {a2['at_double_c']['roc']:.2f}"
               if a2.get("at_half_c") else f"{a2.get('error', 'no c')} -> FAIL")
        print(f"        Stage A {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}; A2: {a2s}" + ("" if audit_st is None else f"; audit {audit_st[cell]['audited']}/{audit_st[cell]['listed']} of the top-{AUDIT_N} "
              f"listed -> {'COMPLETE' if audit_st[cell]['audit_complete'] else 'incomplete'}"))


def print_counts(label, cnt):
    keys = [k for k in ("universe", "no_signal", "no_fill", "no_open5", "no_rv", "news_unknown", "news", "no_beta", "no_price") + tuple(f"pre_{h}" for h in HYG) + ("xchk",) + tuple(f"post_{h}" for h in HYG) + ("audit", "pool")
            if any(k in c for c in cnt.values())]
    print(f"  {label} name-removals by calendar year, each name counted once at its FIRST reason (columns: " + " / ".join(keys) + ")")
    for y, c in sorted(cnt.items()):
        print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in keys) + f"   [sessions/rebalances {c.get('rebalances', c.get('sessions', 0))}, unresolved {c.get('unresolved', 0)}, small pool {c.get('small_pool', 0)}, "
              f"thin side {c.get('thin_side', 0)}, no ES {c.get('no_es', 0)}; cross-check: checked {c.get('xchk_checked', 0)}, factor {c.get('xchk_f1', 0)} / whole-ratio {c.get('xchk_f2', 0)} / volume {c.get('xchk_f3', 0)}, "
              f"disagree {c.get('xchk_disagree', 0)}]")


def es_hole_report(W, lo=None, hi=None):
    """the holes in the ES masters and what the beta rule makes of them on the stretch [lo, hi] (default WF) -> (the printed line, the record for the stage's file). An ES session with no 16:00 print has no return (and the
    next session no opening gap); under the registered all-present beta rule that leaves L2 without a beta for ANY name on each of the 60 sessions after it. Found by the dryload (2020-02-28 and 2020-06-30 are such
    sessions in the house ES masters), so it is printed as a WARNING by dryload and Stage A (and printed and stored by Stage B for the lockbox), never silently absorbed. Holes listed: those that can reach the
    stretch (from 60 sessions before it)"""
    lo, hi = (WF0 if lo is None else lo), (PRE_END if hi is None else hi)
    blind, holes = es_blind(W)
    sel = np.asarray((W.days >= lo) & (W.days <= hi))
    first = max(int(np.searchsorted(W.days, lo)) - SPEC["beta_n"], 0)
    holes = holes[(holes >= W.days[first]) & (holes <= hi)]
    wb = blind & sel
    by = {int(y): int(n) for y, n in sorted(Counter(W.days[wb].year).items())}
    rec = {"stretch": [f"{lo:%Y-%m-%d}", f"{hi:%Y-%m-%d}"], "undefined_es_return_sessions": [f"{d:%Y-%m-%d}" for d in holes], "beta_min": SPEC["beta_min"], "beta_n": SPEC["beta_n"],
           "l2_blind_sessions": int(wb.sum()), "l2_blind_by_year": by, "sessions": int(sel.sum())}
    what = f"the ES return is undefined on {len(holes)} sessions that reach it ({', '.join(rec['undefined_es_return_sessions'][:12])})" if len(holes) else "no session that reaches it has an undefined ES return"
    txt = (f"ES holes ({rec['stretch'][0]} .. {rec['stretch'][1]}): {what}; with the beta rule 'at least {SPEC['beta_min']} of the previous {SPEC['beta_n']} ES returns' L2 has no beta for ANY name on "
           f"{int(wb.sum())} of {int(sel.sum()):,} sessions" + (f" (by year: {by})" if by else ""))
    return ("WARNING - " if wb.any() else "") + txt, rec


# ------------------------------------------------------------------ dryload: counts only
def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS: sessions, symbols, universe sizes, L2 sessions with enough eligible names, open5 coverage, hygiene removals by reason, TBIS rows matched, ES print
    coverage, where k_t starts, the ES holes and the L2 sessions they blind (a WARNING). No price, return or P&L is printed - the L1 / L2 pools are built only to count what they hold"""
    prereg_ok()
    t0 = time.time()
    D = A13.load_data(S.LB0)
    cov, cy = A13.coverage(D, WF0, PRE_END), S.coverage_by_year(D)
    nfull, nd = len(D.syms), len(D.days)
    tbis = load_tbis(S.LB0)
    es_frames, es_meta = load_es(S.LB0)
    full_match = tbis_array(D.days, D.syms, tbis)[1]
    W = build_world(D, S.LB0, es_frames, tbis)
    release(D)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch; symbols: {nfull:,} in the cache after SIPORB's price / volume floor, "
          f"{W.S:,} ever in the universe")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    print(f"open5: day files on {cov['with_open5']:,} of {cov['sessions']:,} WF sessions ({cov['share']:.1%}; needs >= {RULES['cov']:.0%}); name-days passing SIPORB's filters 1-3 that have the 09:30 bar, by year: "
          + "  ".join(f"{y}: {v['share']:.1%}" for y, v in cy.items()))
    L1 = l1_build(W, WF0, PRE_END, "remove", "exclude", units=False)
    L2 = l2_build(W, WF0, PRE_END, "remove", "exclude")
    pool_ok = defaultdict(lambda: [0, 0])
    for rec in L2.recs:
        c = pool_ok[int(W.days[rec.t].year)]
        c[1] += 1
        c[0] += int(len(rec.pool) >= 2 * SPEC["l2_n"])
    print("L2: sessions whose eligible pool (before the |adjusted gap| >= 1% rule - no gap value is read) holds at least 2 x 20 names, by year: " + "; ".join(f"{y}: {a}/{b}" for y, (a, b) in sorted(pool_ok.items())))
    print(f"L1: rebalances with a pool of at least 2 x 25 names: {sum(r.traded for r in L1.recs):,} of {len(L1.recs):,} whose position exits in WF")
    print_counts("L1", L1.cnt)
    print_counts("L2", L2.cnt)
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    pa, pr = W.es_cov["adj_prints"], W.es_cov["raw_prints"]
    e = W.es
    print(f"ES prints on the {W.T:,} stock sessions: 09:35 price {int(np.isfinite(e.e5).sum()):,}, 16:00 adj {int(np.isfinite(e.c16a).sum()):,}, 16:00 raw {int(np.isfinite(e.c16r).sum()):,}; fallback bars: "
          f"{int((pa['close_hm'] != pa['last']).sum())} closes / {int((pa['open_hm'] != 570).sum())} opens (adj master), {int((pr['close_hm'] != pr['last']).sum())} closes (raw master); "
          f"ES return defined on {int(np.isfinite(e.ret).sum()):,} sessions, ES opening gap on {int(np.isfinite(e.gap).sum()):,}")
    fin = np.flatnonzero(np.isfinite(W.k))
    print(f"k_t: defined from {W.days[fin[0]]:%Y-%m-%d} on ({len(fin):,} of {W.T:,} sessions); undefined on {int((~np.isfinite(W.k[wf])).sum())} WF sessions" if len(fin) else "k_t: undefined everywhere")
    print(es_hole_report(W)[0])
    print(f"cache manifest sha256: {manifest_sha()}")
    pm = peak_mb()
    print(f"dryload took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))


def sibling_note(cell, a2_roc):
    """SIBLING RULE (prereg, 2026-10-05, MANAGER's XGAP review edit 4): XGAP r1 (the Nasdaq-100 members' firm-specific overnight gaps faded 09:35 -> close) is a close relative of L2. If an L2 cell and an XGAP cell
    both reach Stage B, only the higher A2 book ROC of the two is read on the one sealed-year day - one look for one hypothesis. CHOICE: this harness has no XGAP input (its numbers live in another harness's
    file), so it cannot ENFORCE the rule; it names the number the lead compares against XGAP's before the sealed-year day, and says plainly that it did not check. An L1 cell has no registered sibling"""
    if cell[:2] != "L2":
        return f"SIBLING RULE: not engaged - {cell} is an L1 cell and the registered sibling (XGAP) is L2's relative"
    return (f"SIBLING RULE (NOT checked here - this harness cannot see XGAP): if an XGAP cell also reached Stage B, only the higher A2 book ROC of the two is read on the one sealed-year day; "
            f"{cell}'s A2 book ROC is {a2_roc:.2f} - compare it with XGAP's before that day")


# ------------------------------------------------------------------ Stage A
def stage_a():
    if os.path.exists(os.path.join(OUT, "ddw_stageB_READ.flag")):                          # CHOICE: once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse("Stage A refused: Stage B has already read the lockbox - Stage A is frozen (ddw_stageB_READ.flag)")
    pok = prereg_ok()
    B, legs_meta = A13.load_463()                                                          # the book first: cheap, and a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}, the 2020-03-03 .. 03-27 episode {'found' if dd['episode_2020'] else 'NOT FOUND'}")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (the prereg's [T5] facts) - fix the input first (nothing computed)")
    msha = manifest_sha()
    print(f"SIPORB cache manifest sha256: {msha} (registered: {MANIFEST_PREFIX}...)")
    if CHECK_BOOK and not (msha and msha.startswith(MANIFEST_PREFIX)):
        refuse("Stage A refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (a re-pull must never be mixed in) - nothing computed")
    print("order of reads: SIPORB's Stage A is " + ("on file" if os.path.exists(os.path.join(S.OUT, "siporb_stageA.json")) else "NOT on file yet") + "; ATTN's Stage A is "
          + ("on file" if os.path.exists(os.path.join(A13.OUT, "attn_stageA.json")) else "NOT on file yet") + " (all three Stage A runs come before any Stage B)")
    t0 = time.time()
    D = A13.load_data(S.LB0)                                                               # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    cov, cy = A13.coverage(D, WF0, PRE_END), S.coverage_by_year(D)
    print(f"open5 present on {cov['with_open5']:,} of {cov['sessions']:,} WF sessions ({cov['share']:.1%}; needs >= {RULES['cov']:.0%}); SIPORB's name-day coverage by year (report): "
          + "  ".join(f"{y}: {v['share']:.1%}" for y, v in cy.items()))
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stageA": None, "candidate": None, "pending_audit": None,
           "book_check": bk, "dd_structure": dd, "coverage": cov, "name_day_coverage_by_year": cy, "manifest_sha256": msha}
    if not cov["share"] >= RULES["cov"]:
        print("Stage A is NOT judged: the 09:30 bar files are missing for too many WF sessions - run SIPORB's open5 pull first (ddw_stageA.json written, judged false)")
        dump(out, "ddw_stageA.json")
        return out
    tbis = load_tbis(S.LB0)
    es_frames, es_meta = load_es(S.LB0)
    audit = read_audit()
    W = build_world(D, S.LB0, es_frames, tbis)
    release(D)
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    kmiss = int((~np.isfinite(W.k[wf])).sum())
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in the universe, k_t undefined on {kmiss} WF sessions; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    if CHECK_BOOK and kmiss:
        refuse(f"Stage A refused: k_t (ES's volatility ratio) is undefined on {kmiss} WF sessions - the prereg says it is defined for every session from 2016 on; the ES masters do not reach back far enough (nothing computed)")
    hole_txt, out["es_holes"] = es_hole_report(W)
    print(hole_txt)
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, "ddw_audit.csv"))
    print(f"audit file: " + ("none yet - every cell's audit is incomplete" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the null)"))
    rows = A13.book_rows(B, W)
    t1 = time.time()
    resR, objR = evaluate(W, B, S12, rows, "remove", NREP, 0, full=True)
    print(f"registered reading done ({time.time() - t1:.0f}s: legs, cells, stress rows and {NREP} null draws)", flush=True)
    unused = unused_audit_rows(W, audit)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing (the name was not in that day's universe): {unused[:5]}")
    t1 = time.time()
    resK, objK = evaluate(W, B, S12, rows, "naive", NREP, 1, full=False)
    print(f"look-ahead reading done ({time.time() - t1:.0f}s)", flush=True)
    rep, cands, expo = reports(W, B, S12, rows, objR.legs, objR.runs, objR.series, resR["cells"], tbis, asset_status(), legs_meta)
    ast = audit_status(cands, audit)
    cells = resR["cells"]
    for cell in CELLS:
        cells[cell]["audit"] = ast[cell]
    would = {c: bool(cells[c]["PASS"] and cells[c]["A2"]["pass"]) for c in CELLS}
    passing = [c for c in CELLS if would[c] and ast[c]["audit_complete"]]
    pending = [c for c in CELLS if would[c] and not ast[c]["audit_complete"]]
    cand = max(passing, key=lambda c: cells[c]["A2"]["roc"]) if passing else None
    flips = {c: {"stageA": bool(resK["cells"][c]["PASS"]) != bool(cells[c]["PASS"]), "A2": bool(resK["cells"][c]["A2"]["pass"]) != bool(cells[c]["A2"]["pass"])} for c in CELLS}
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame([r for c in CELLS for r in cands[c]]).to_csv(os.path.join(OUT, "ddw_audit_candidates.csv"), index=False)
    expo.to_csv(os.path.join(OUT, "ddw_L2_exposure_by_day.csv"), index=False)
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - the REGISTERED reading (a hygiene flag inside the hold removes the position)")
    print_cells(resR, ast)
    print(f"  look-ahead reading (positions with a flag INSIDE the hold kept at naive raw P&L) [O3]: null ROC p95 {resK['null']['roc_max']['p95']:.1f}, DO p95 {resK['null']['do_max']['p95']:+.3f}, rho_dd p5 {resK['null']['rho_min']['p5']:+.3f}")
    for cell in CELLS:
        k = resK["cells"][cell]
        print(f"    {cell}: {row(cell, k)[6:]} | Stage A {'PASS' if k['PASS'] else 'FAIL'}, A2 {'PASS' if k['A2']['pass'] else 'FAIL'}"
              + ("   *** FLIPS the registered verdict ***" if any(flips[cell].values()) else "   (same verdicts)"))
    b = rep["beta_to_es"]
    print("  realised beta to ES (the cell's daily $ P&L on ES's daily return, $ per 1% ES move; DD days / DD weeks / all WF days): " + "; ".join(
        f"{c} {b[c]['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b[c]['all WF days']['usd_per_1pct_es']:+,.0f}" for c in CELLS))
    print_counts("L1 (registered)", objR.legs["L1"].cnt)
    print_counts("L2 (registered)", objR.legs["L2"].cnt)
    for leg in ("L1", "L2"):
        t = rep["news_twin"][leg]
        print(f"  news-excluded names' own reversal, {leg}: mean {t['news_only_book']['mean_bps_per_name_period']:+.1f} bps a name-period over {t['news_only_book']['n_pos']:,} (net ${t['news_only_book']['net']:,.0f}) vs the no-news book "
              f"{t['no_news_book']['mean_bps_per_name_period']:+.1f} bps over {t['no_news_book']['n_pos']:,}")
    sv = rep["survivorship"]
    print(f"  survivorship: {sv['long_in_inactive_names']:,} of {sv['long_positions']:,} L1 long positions ({sv['share_long_in_inactive_names']:.1%}) are in names the asset list calls inactive; L2 traded {rep['l2_exposure'].get('traded_days', 0):,} sessions")
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell, with dates) -> {os.path.join(OUT, 'ddw_audit_candidates.csv')}; write ddw_audit.csv (symbol, date, cell, verdict keep|data_event, note) and run stage_a again")
    judged = not pending
    out.update({"judged": bool(judged), "pending_audit": pending, "audit_sha256": asha, "audit": aud_n, "audit_data_events_without_effect": unused,
                "stageA": {"cells": cells, "null": resR["null"], "would_pass_before_audit": would, "pass_cells": passing},
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"],
                               "a2_book_roc": cells[cand]["A2"]["roc"]} if cand else None), "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"]} for c in CELLS},
                "look_ahead_reading": {"null": resK["null"], "cells": {c: {"PASS": resK["cells"][c]["PASS"], "A2_pass": resK["cells"][c]["A2"]["pass"], "base": resK["cells"][c]["base"], "seat": resK["cells"][c]["seat"],
                                                                          "checks": resK["cells"][c]["checks"]} for c in CELLS}, "flips": flips},
                "reports": rep, "es_masters": es_meta})
    dump(out, "ddw_stageA.json")
    if cand:
        print(f"DDW Stage A: PASS - cell {cand} (A2: c x{cells[cand]['A2']['c']:.4g} set by volatility, book ROC@30k {cells[cand]['A2']['roc']:.2f}) clears every bar with its audit complete; passing cells {passing} "
              "(the highest A2 book ROC goes to Stage B, the others are reported). Stage B may run ONCE, on the one sealed-year day, after SIPORB's and ATTN's Stage A.")
        print(sibling_note(cand, cells[cand]["A2"]["roc"]))
    elif pending:
        print(f"DDW Stage A: NOT YET JUDGED - {pending} clear every bar but the hand audit of their {AUDIT_N} largest contributors is incomplete (judged: false in ddw_stageA.json, so ATTN's Stage B stays shut).")
    else:
        print("DDW Stage A: FAIL - no cell passes (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]['checks'].items() if not v) + ("" if not cells[c]["PASS"] else " - A2 fails") for c in CELLS)
              + ") - family 1 is dead; the lockbox stays sealed.")
    if out["es_holes"]["l2_blind_sessions"]:
        print("NOTE for the verdict - " + hole_txt.replace("WARNING - ", "", 1))                    # the holes are in the Stage A file too: ddw_stageA.json -> es_holes
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read
def b_units(cell):
    """Stage B's breadth bar by leg: L1 >= 26 weekly rebalances, L2 >= 30 traded sessions [M4] -> (the bar, its label)"""
    return (RULES["b_l1_reb"], "weekly rebalances") if cell[:2] == "L1" else (RULES["b_l2_days"], "traded sessions")


def b_checks(cell, leg):
    """STAGE B's pass, MANAGER #48: the LEG's standalone veto and nothing else - >= 50 name-periods AND the leg's breadth bar (b_units), net > 0, net > 0 without its top name-period. It takes no book number: the book
    add on the lockbox year is a report, so it cannot be in this verdict. A NaN fails every comparison it enters -> {check name: bool}"""
    units, ulab = b_units(cell)
    return {f"leg name-periods>={RULES['b_n']}": bool(leg["n_pos"] >= RULES["b_n"]), f"leg {ulab}>={units}": bool(leg["n_units"] >= units), "leg net>0": bool(leg["net"] > 0),
            "leg net>0 without its top name-period": bool(leg["net_ex_top_pos"] > 0)}


def stage_b():
    """STAGE B (LB, once, on the one sealed-year day) - MANAGER #48: the sealed year is the LEG's standalone veto: >= 50 name-periods AND L1 >= 26 weekly rebalances / L2 >= 30 traded sessions [M4], net > 0, and
    > 0 without its top name-period. The book add on that year (#463 + c x the cell at Stage A's frozen c) is computed, printed and stored as book_add_reported - it is NEVER part of the pass (#463's sealed year
    has already judged 71 candidate books). A surviving leg goes to a computed no-order forward shadow (Stage C); the forward record decides any book add (owner call)"""
    pa = os.path.join(OUT, "ddw_stageA.json")
    sa = json.load(open(pa)) if os.path.exists(pa) else {}
    cand = sa.get("candidate")
    cres = ((sa.get("stageA") or {}).get("cells") or {}).get(cand.get("cell") if isinstance(cand, dict) else None) or {}
    if not (sa.get("judged") is True and isinstance(cand, dict) and cres.get("PASS") is True and (cres.get("A2") or {}).get("pass") is True and (cres.get("audit") or {}).get("audit_complete") is True):
        refuse("Stage B refused: no Stage A + A2 pass with a complete audit is on file - the lockbox stays sealed.")
    flag = os.path.join(OUT, "ddw_stageB_READ.flag")
    if os.path.exists(flag):
        refuse("Stage B refused: the lockbox was already read once (ddw_stageB_READ.flag)")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "ddw_audit.csv")):
        refuse("Stage B refused: ddw_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell = cand["cell"]
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or not (math.isfinite(c) and c > 0):                                  # c is a volatility ratio now: any positive number is a frozen size, but NaN / 0 / missing is a broken file
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / size c {cand.get('c')} is not one of {CELLS} / a positive number (lockbox NOT read)")
    ap = os.path.join(A13.OUT, "attn_stageA.json")                                             # the order of reads: every Stage A of the three runs first (the sealed-year day, M5)
    attn = json.load(open(ap)) if os.path.exists(ap) else {}
    if attn.get("judged") is not True:
        refuse("Stage B refused: ATTN's Stage A is not on file and judged - the sealed year opens only after every Stage A of SIPORB, ATTN and DDW has run (order of reads; lockbox NOT read)")
    state = A13.siporb_state()
    if state is None:
        refuse("Stage B refused: SIPORB's lockbox has not been read and SIPORB has not failed before it - the sealed year opens only after SIPORB's (order of reads); lockbox NOT read")
    print(f"order of reads: SIPORB is '{state}'; ATTN's Stage A is judged")
    print(sibling_note(cell, cres["A2"]["roc"]))
    B, legs_meta = A13.load_463()                                                              # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = A13.book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    msha = manifest_sha()
    if CHECK_BOOK and not (msha and msha.startswith(MANIFEST_PREFIX) and msha == sa.get("manifest_sha256")):
        refuse("Stage B refused: the SIPORB cache manifest is not the one Stage A ran on (a re-pull must never be mixed in) - lockbox NOT read")
    D = A13.load_data(S.END)
    cov, cy = A13.coverage(D, LB0, LB1), S.coverage_by_year(D)
    print(f"open5 present on {cov['with_open5']:,} of {cov['sessions']:,} lockbox sessions ({cov['share']:.1%}; needs >= {RULES['cov']:.0%})")
    if not cov["share"] >= RULES["cov"]:                                                       # CHOICE: Stage A's gate applied to the lockbox BEFORE the one read (ATTN's Stage B does the same)
        refuse("Stage B refused: the 09:30 bar files are missing for too many lockbox sessions - fix the pull first (lockbox NOT read)")
    tbis = load_tbis(S.END)
    es_frames, es_meta = load_es(S.END)
    audit = read_audit()
    W = build_world(D, S.END, es_frames, tbis)
    release(D)
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = es_hole_report(W, LB0, LB1)                                           # the ES holes that reach the lockbox (L2's betas under the registered rule): printed and stored with the read
    legs = {"L1": l1_build(W, WF0, PRE_END), "L2": l2_build(W, WF0, PRE_END)}                  # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    for cc in CELLS:
        run = run_cell(W, legs[cc[:2]], cc, l1_cfg() if cc[:2] == "L1" else (ADV_BPS, COST_BPS))
        xw = to_B(run.x, rows, B.n)
        st, ref = cell_stats(B, xw, to_B(run.cnt, rows, B.n), WF0, PRE_END, run), sa["parity"][cc]
        print(f"WF re-read on Stage B's data: {cc} positions {st['n_pos']:,} (Stage A {ref['n_pos']:,}), net ${st['net']:,.0f} (Stage A ${ref['net']:,.0f})")
        if st["n_pos"] != ref["n_pos"] or st["n_units"] != ref["n_units"] or abs(st["net"] - ref["net"]) > max(1.0, 1e-6 * abs(ref["net"])):
            refuse(f"Stage B refused: the WF numbers of {cc} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
        if cc == cell:
            c2 = a2_cell(B, xw)["c"]
            print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from the first two WF years on Stage B's data")
            if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
                refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    L = l1_build(W, LB0, LB1) if cell[:2] == "L1" else l2_build(W, LB0, LB1)                   # CHOICE (ATTN's order, r10_spread's): the whole LB result is computed, nothing shown, BEFORE the flag
    run = run_cell(W, L, cell, l1_cfg() if cell[:2] == "L1" else (ADV_BPS, COST_BPS), pos=True)
    xB, cB = to_B(run.x, rows, B.n), to_B(run.cnt, rows, B.n)
    leg = cell_stats(B, xB, cB, LB0, LB1, run)
    r = book_at(B, xB, c, LB0, LB1)                                                            # the book add at the FROZEN c - c is never re-set on the sealed year
    would = bool(r["roc"] >= RULES["b_roc"] and r["sortino"] >= RULES["b_sort"])
    ulab = b_units(cell)[1]
    chk = b_checks(cell, leg)
    ok = all(chk.values())                                                                     # MANAGER #48: the pass is the LEG's veto - the book add below is a report and is not in this line
    add = {"c": c, "roc": r["roc"], "sortino": r["sortino"], "net": r["net"], "max_dd": r["max_dd"], "reference": {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}, "would_have_cleared": would,
           "note": "reported, never a pass (MANAGER #48): the forward record decides any book add (owner call)"}
    cnt = {y: dict(v) for y, v in sorted(L.cnt.items())}
    text = json.dumps({"cell": cell, "c": c, "siporb": state, "book_check": bk, "coverage": cov, "es_masters": es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add,
                       "es_holes_lb": hole_rec, "hygiene_counts_by_year": cnt, "top_name_periods": candidate_rows(W, L, cell, run, tbis, asset_status(), 20), **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                        # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell}: positions {leg['n_pos']:,}, {ulab} {leg['n_units']:,}, net ${leg['net']:,.0f}, ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; its top name-period ${leg['top_pos']:,.0f}, net without it ${leg['net_ex_top_pos']:,.0f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} -> would "
              f"{'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}")
        print("DDW Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id (no run # exists for a stock basket); "
                                 "the book add above is a report - the forward record decides any book add, and opening any account is the owner's decision (owner call)." if ok else
                                 "FAIL - the leg is vetoed by its sealed year: DDW r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "ddw_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: a toy world with planted events, and plain-python recounts of every position (independent of the vectorised builders)
@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries for a block and put them back (the self-tests and the smoke shrink the universe and the sides; nothing stays patched)"""
    old = dict(SPEC)
    SPEC.update(kw)
    try:
        yield
    finally:
        SPEC.clear()
        SPEC.update(old)


def jump_at(Od, Cl, C5, j, row, ratio):
    """plant a one-night move in name j: from `row` on every raw price is scaled so that the raw open of `row` over the raw close before it is exactly `ratio`"""
    s = ratio * Cl[row - 1, j] / Od[row, j]
    Od[row:, j] *= s
    Cl[row:, j] *= s
    C5[row:, j] *= s


def toy_world(seed=1, T=150, Sn=16):
    """150 sessions (Mon 2024-01-01 on: ISO weeks are 5 clean sessions) x 16 random-walk names (run it with spec(univ=16): every name is in the universe), with every rule's case planted by hand - where:
    N00 a registered 2-for-1 split at row 70 (factor moves, raw prices halve); N01 an unadjusted x4 at row 90 flagged by the gap scan; N02 a TBIS flag at row 100; N03 a genuine +60% gap at row 110 (no ratio
    fit: the +-50% rule); N04 stops printing at row 120; N05 no close bar at row 83 (the mark carries); N06 a news session (volume x5) at row 40; N07 no news baseline for sessions 50-52; N08 a -35% gap at
    row 77 with volume 1.54x its baseline (vol x price = 1: the volume test fires); N09 the same gap at row 87 with volume 2.2x (no); N10 a -49.5% gap at row 97 NOT in the gap scan's flags (the whole-ratio
    test fires); N11 audit data event at fill 85; N12 a -34% slide over rows 105-109 while the split factor drifts 2% (the factor test fires); L2: N13 Relative Volume 2.5 on row 100, N14 a news session on row 101, N15
    no 09:30 bar on row 103, N09 a -28% gap at row 130 with Relative Volume 1.39 (the L2 volume test fires)"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=T)
    syms = np.array([f"N{j:02d}" for j in range(Sn)])
    Cl = 40.0 * (1.0 + 0.04 * np.arange(Sn)) * np.exp(np.cumsum(rng.normal(0.0, 0.012, (T, Sn)), axis=0))
    Od = np.vstack([Cl[0], Cl[:-1]]) * (1.0 + rng.normal(0.0, 0.012, (T, Sn)))
    Vv = rng.uniform(2.0e6, 4.0e6, (T, Sn)) * (1.0 + 0.1 * np.arange(Sn))
    F, chg, ms, tb = np.ones((T, Sn)), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool)
    C5 = Od * (1.0 + rng.normal(0.0, 0.012, (T, Sn)))
    RV = rng.uniform(0.6, 1.6, (T, Sn))
    atr = np.full((T, Sn), 2.0)
    jump_at(Od, Cl, C5, 0, 70, 0.5)
    F[:70, 0], F[70:, 0], chg[70, 0] = 2.0, 1.0, True                                        # N00: the registered split (Alpaca's convention: F = raw / split-adjusted open is 2 before a 2-for-1, 1 after)
    jump_at(Od, Cl, C5, 1, 90, 4.0)
    ms[90, 1] = True                                                                         # N01: a split Alpaca never adjusted
    tb[100, 2] = True                                                                        # N02
    jump_at(Od, Cl, C5, 3, 110, 1.6)                                                         # N03
    for a in (Od, Cl, C5, Vv, F, RV):
        a[120:, 4] = np.nan                                                                  # N04: stops printing
    Cl[83, 5] = np.nan                                                                       # N05
    Vv[40, 6] *= 5.0                                                                         # N06
    Vv[32, 7] = np.nan                                                                       # N07
    jump_at(Od, Cl, C5, 8, 77, 0.65)
    Vv[77, 8] = Vv[57:77, 8].mean() / 0.65                                                   # N08: vol x price = 1
    jump_at(Od, Cl, C5, 9, 87, 0.65)
    Vv[87, 9] = Vv[67:87, 9].mean() * 2.2                                                    # N09: vol x price = 1.43
    jump_at(Od, Cl, C5, 10, 97, 0.505)                                                       # N10: a whole ratio (1/2 within 2%, no jump flag) the scan did not flag
    for q in range(105, 110):                                                                # N12: a slide of -8% a session ...
        Cl[q:, 12] *= 0.92
        Od[q:, 12] *= 0.92
        C5[q:, 12] *= 0.92
    F[106:, 12] = 1.02                                                                       # ... and a 2% factor drift that the chg flag did not catch
    RV[100, 13] = 2.5                                                                        # L2 plants
    Vv[101, 14] *= 5.0
    C5[103, 15], RV[103, 15] = np.nan, np.nan
    jump_at(Od, Cl, C5, 9, 130, 0.72)
    C5[130, 9] = Od[130, 9]
    RV[130, 9] = 1.0 / 0.72
    es = SimpleNamespace(e5=None, c16a=None, c16r=None, ret=rng.normal(0.0, 0.01, T), gap=rng.normal(0.0, 0.004, T), k=np.clip(rng.lognormal(0.0, 0.4, T), 0.5, 2.0))
    es.ret[0], es.gap[0] = np.nan, np.nan
    U = universe_mask(Cl, Vv, atr, chg, SPEC)
    W = World(days, syms, Od, Cl, Vv, F, U, chg, ms, tb, C5, RV, es)
    W.atr = atr
    return W


def brute_flags(W, s, j):
    """the four hygiene reasons on session s for name j, plain python"""
    chg, ms, tb = bool(W.chg[s, j]), bool(W.msplit[s, j]), bool(W.tbis[s, j])
    R = W.Od[s, j] / W.Cl[s - 1, j] if s >= 1 else float("nan")
    return (chg, ms, tb, bool(math.isfinite(R) and abs(R - 1.0) > 0.5 and not chg))


def brute_news(W, s, j):
    """(news, unknown) for session s, plain python: volume >= 3x the mean of the 20 sessions before it, all present"""
    prev = [W.Vv[q, j] for q in range(s - SPEC["news_n"], s)] if s >= SPEC["news_n"] else [float("nan")]
    if not all(math.isfinite(v) for v in prev) or not math.isfinite(W.Vv[s, j]):
        return False, True
    return bool(W.Vv[s, j] >= SPEC["news_x"] * sum(prev) / SPEC["news_n"]), False


def brute_whole(R):
    """r5_siporb's gap-scan rule on one ratio: |R - 1| > 25% and within 2% of a whole k or 1/k, k in 2..50"""
    return bool(math.isfinite(R) and abs(R - 1.0) > 0.25 and any(abs(R / k - 1.0) <= 0.02 or abs(R * k - 1.0) <= 0.02 for k in range(2, 51)))


def brute_xchk(W, j, rows, vr_of, f1):
    """the three tests, plain python. rows = the sessions whose overnight ratio R = open / prior close competes for 'the move' (the largest |R - 1|); vr_of(s) = that session's volume ratio; f1 = the factor test"""
    best, bs = -1.0, None
    for s in rows:
        R = W.Od[s, j] / W.Cl[s - 1, j]
        if math.isfinite(R) and abs(R - 1.0) > best:
            best, bs = abs(R - 1.0), s
    if bs is None:
        return (False, False, False)
    R, vr = W.Od[bs, j] / W.Cl[bs - 1, j], vr_of(bs)
    return (bool(f1), brute_whole(R), bool(abs(R - 1.0) > SPEC["xchk_floor"] and math.isfinite(vr) and abs(vr * R - 1.0) <= SPEC["xchk_vol"]))


def brute_l1_path(W, f, x, j, sd, naive, bps=COST_BPS, borrow=(BORROW, None), kt=None, lose100=False, sq=False):
    """one L1 position's daily P&L per $1 of entry over rows f .. x, plain python: marks carried over a missing bar, exit at the open of x (a name with no open there stopped printing: exits at its last mark),
    bps a side, borrow on the nights before rows f+1 .. x"""
    adj = (lambda a, s: a[s, j]) if naive else (lambda a, s: a[s, j] / W.F[s, j])
    entry = adj(W.Od, f)
    marks = [entry]
    for s in range(f, x):
        c = adj(W.Cl, s)
        marks.append(c if math.isfinite(c) else marks[-1])
    ox = adj(W.Od, x)
    stopped = not math.isfinite(ox)
    exitv = marks[-1] if stopped else ox
    out = []
    for h in range(x - f + 1):
        g = (marks[h + 1] - marks[h]) / entry if h < x - f else (exitv - marks[-1]) / entry
        p = sd * g
        if h == 0:
            p -= bps * 1e-4
        if h == x - f:
            if sd > 0 and lose100 and stopped:
                p = -marks[-1] / entry
            else:
                p -= bps * 1e-4 * exitv / entry
        if sd < 0 and h >= 1:
            rate = borrow[0]
            if borrow[1] is not None and kt is not None and kt[h] > K_STRESS:
                rate = borrow[1]
            if sq:
                rate = SQUEEZE_RATE
            p -= rate / 252.0 * marks[h] / entry
        out.append(p)
    return out, stopped


def brute_l1(W, lo, hi, post_mode="remove", news_mode="exclude"):
    """every L1 rebalance whose position exits in [lo, hi], plain python end to end (the schedule from the ISO weeks of consecutive sessions, the universe taken from W.U, every other rule re-implemented
    with loops): [{r, f, x, pool: {col: (signal, naive)}, long: [cols], short: [cols], counts}]"""
    sp, n5, nn = SPEC, SPEC["ret_n"], SPEC["l1_n"]
    key = [W.days[i].isocalendar()[:2] for i in range(W.T)]
    ranks = [i for i in range(W.T - 1) if key[i] != key[i + 1]]
    recs = []
    for k, r in enumerate(ranks):
        f, x = r + 1, (ranks[k + 1] + 1 if k + 1 < len(ranks) else -1)
        if x < 0 or not (lo <= W.days[x] <= hi) or r < n5:
            continue
        uni = [j for j in range(W.S) if W.U[f, j]]
        sig = {}
        for j in uni:
            a, b = W.Cl[r, j] / W.F[r, j], W.Cl[r - n5, j] / W.F[r - n5, j]
            sig[j] = a / b - 1.0
        fin = [v for v in sig.values() if math.isfinite(v)]
        mean = sum(fin) / len(fin) if fin else 0.0
        pool, cnt = {}, Counter()
        for j in uni:
            if not math.isfinite(sig[j]):
                continue
            if not math.isfinite(W.Od[f, j] / W.F[f, j]):
                continue
            nw = [brute_news(W, s, j) for s in range(r - n5 + 1, r + 1)]
            news, unk = any(a for a, _ in nw), any(b for _, b in nw)
            if unk or (news if news_mode == "exclude" else not news):
                continue
            pre = any(any(brute_flags(W, s, j)) for s in range(max(r - (n5 - 1) - sp["hyg_lead"], 0), r + 1))
            post = any(any(brute_flags(W, s, j)) for s in range(r + 1, x + 1))
            dm = sig[j] - mean
            xf = False
            if abs(dm) > sp["xchk_l1"]:
                cnt["xchk_checked"] += 1
                vr_of = lambda s, j=j: W.Vv[s, j] / (sum(W.Vv[q, j] for q in range(s - sp["news_n"], s)) / sp["news_n"]) if s >= sp["news_n"] else float("nan")
                fch = bool(W.chg[r - n5 + 1:r + 1, j].any() or abs(W.F[r, j] / W.F[r - n5, j] - 1.0) > 0.01)
                parts = brute_xchk(W, j, range(r - n5 + 1, r + 1), vr_of, fch)
                for q in range(3):
                    cnt[f"xchk_f{q + 1}"] += int(parts[q])
                xf = any(parts)
                cnt["xchk_disagree"] += int(xf)
            if pre or xf or W.aud1[f, j]:
                continue
            if post and post_mode == "remove":
                continue
            pool[j] = (dm, bool(post and post_mode == "naive"))
        rec = {"r": r, "f": f, "x": x, "pool": pool, "long": [], "short": [], "counts": cnt}
        if len(pool) >= 2 * nn:
            order = sorted(pool, key=lambda j: (pool[j][0], j))
            rec["long"], rec["short"] = order[:nn], order[::-1][:nn]
        recs.append(rec)
    return recs


def brute_beta(W, t, j):
    """the OLS slope of name j's split-safe daily returns on ES's over sessions t-60 .. t-1, plain python; None unless all 60 are present for both (the registered rule: SPEC beta_min = 60). With beta_min < 60 the
    sessions on which ES's return is undefined are left out of the regression (for every name) while at least beta_min remain; the name still needs every remaining session"""
    n = SPEC["beta_n"]
    if t < n + 1:
        return None
    sess = [s for s in range(t - n, t) if math.isfinite(W.es.ret[s])]
    if len(sess) < SPEC["beta_min"]:
        return None
    ys = [(W.Cl[s, j] / W.F[s, j]) / (W.Cl[s - 1, j] / W.F[s - 1, j]) - 1.0 for s in sess]
    ms = [W.es.ret[s] for s in sess]
    if not all(math.isfinite(v) for v in ys + ms):
        return None
    n = len(sess)
    my, mm = sum(ys) / n, sum(ms) / n
    var = sum((m - mm) ** 2 for m in ms)
    return sum((m - mm) * (y - my) for m, y in zip(ms, ys)) / var if var > 0 else None


def brute_l2(W, lo, hi, post_mode="remove", news_mode="exclude"):
    """every L2 session in [lo, hi], plain python: [{t, pool: {col: (adjusted gap, raw gap, beta, ratio)}, long, short}]"""
    sp, nn = SPEC, SPEC["l2_n"]
    recs = []
    for t in range(1, W.T):
        if not (lo <= W.days[t] <= hi):
            continue
        esg, pool = W.es.gap[t], {}
        rec = {"t": t, "pool": pool, "long": [], "short": [], "counts": Counter()}
        recs.append(rec)
        if not math.isfinite(esg):
            continue
        for j in [j for j in range(W.S) if W.U[t, j]]:
            c5, rv = W.C5[t, j], W.RV[t, j]
            if not (math.isfinite(c5) and math.isfinite(rv)):
                continue
            nw, unk = brute_news(W, t - 1, j)
            news = bool(rv >= sp["rv_max"] or nw)
            if unk or (news if news_mode == "exclude" else not news):
                continue
            beta = brute_beta(W, t, j)
            raw = (c5 / W.F[t, j]) / (W.Cl[t - 1, j] / W.F[t - 1, j]) - 1.0
            ratio = W.Cl[t, j] / c5
            if beta is None or not (math.isfinite(raw) and math.isfinite(ratio)):
                continue
            xf = False
            if abs(raw) > sp["xchk_l2"]:
                R35 = c5 / W.Cl[t - 1, j]
                f1 = bool(W.chg[t, j] or abs(W.F[t, j] / W.F[t - 1, j] - 1.0) > 0.01)
                f2 = brute_whole(R35)
                f3 = bool(abs(R35 - 1.0) > sp["xchk_floor"] and abs(rv * R35 - 1.0) <= sp["xchk_vol"])
                xf = f1 or f2 or f3
                rec["counts"]["xchk_checked"] += 1
                rec["counts"]["xchk_disagree"] += int(xf)
            pre = any(any(brute_flags(W, s, j)) for s in range(max(t - 1 - sp["hyg_lead"], 0), t))
            post = any(brute_flags(W, t, j))
            if pre or xf or W.aud2[t, j] or (post and post_mode == "remove"):
                continue
            pool[j] = (raw - beta * esg, raw, beta, ratio)
        if len(pool) >= 2 * nn:
            order = sorted(pool, key=lambda j: (pool[j][0], j))
            lg, sh = order[:nn], order[::-1][:nn]
            if max(pool[j][0] for j in lg) <= -sp["gap_min"] and min(pool[j][0] for j in sh) >= sp["gap_min"]:
                rec["long"], rec["short"] = lg, sh
    return recs


# ------------------------------------------------------------------ selftest: hand-made worlds, no files, no data
def close(a, b, tol=1e-9):
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=tol, atol=1e-12, equal_nan=True))


def compare_l1(W, L, Bz, tag):
    """the vectorised L1 build against the plain-python recount: the schedule, every pool (names, signals, naive flags), the 25 / 25 picks, the cross-check counts, and the daily path of EVERY pool name under
    five costings (base, 10 bps, the 3% borrow stress with k_t, longs at -100%, squeezed winners)"""
    assert len(L.recs) == len(Bz), (tag, len(L.recs), len(Bz))
    cfgs = (("base", l1_cfg(), {}), ("10 bps", l1_cfg(bps=10.0), {"bps": 10.0}), ("borrow 3%", l1_cfg(borrow=(BORROW, 0.03)), {"borrow": (BORROW, 0.03), "k": True}),
            ("lose100", l1_cfg(lose100=True), {"lose100": True}), ("squeeze", l1_cfg(squeeze=True), {"sq": True}))
    n_paths = 0
    for rec, b in zip(L.recs, Bz):
        assert (rec.r, rec.f, rec.x) == (b["r"], b["f"], b["x"]), tag
        assert rec.pool.tolist() == sorted(b["pool"]), (tag, rec.r, rec.pool.tolist(), sorted(b["pool"]))
        assert close(rec.sig, [b["pool"][j][0] for j in rec.pool]) and rec.naive.tolist() == [b["pool"][j][1] for j in rec.pool], (tag, rec.r)
        assert rec.traded == bool(b["long"]), (tag, rec.r)
        if not rec.traded:
            continue
        assert rec.pool[rec.long].tolist() == b["long"] and rec.pool[rec.short].tolist() == b["short"], (tag, rec.r)
        kt = W.k[rec.f:rec.x + 1]
        for nm, cfg, kw in cfgs:
            for sd in (1, -1):
                idx = np.arange(len(rec.pool))
                P = l1_pnl(rec.U, idx, sd, cfg, kt, rec.sig > SPEC["squeeze"] if sd < 0 else None)
                for i, j in enumerate(rec.pool):
                    want, _ = brute_l1_path(W, rec.f, rec.x, int(j), sd, bool(rec.naive[i]), bps=kw.get("bps", COST_BPS), borrow=kw.get("borrow", (BORROW, None)), kt=kt if kw.get("k") else None,
                                            lose100=kw.get("lose100", False), sq=bool(kw.get("sq") and rec.sig[i] > SPEC["squeeze"]))
                    assert close(P[i], want), (tag, nm, rec.r, int(j), sd, P[i], want)
                    n_paths += 1
    vc, bc = Counter(), Counter()
    for c in L.cnt.values():
        vc.update(c)
    for b in Bz:
        bc.update(b["counts"])
    for k in ("xchk_checked", "xchk_f1", "xchk_f2", "xchk_f3", "xchk_disagree"):
        assert vc[k] == bc[k], (tag, k, vc[k], bc[k])
    return n_paths


def compare_l2(W, L, Bz, tag):
    """the vectorised L2 build against the plain-python recount: pools (adjusted gap, raw gap, beta, ratio), the 20 / 20 picks, the cross-check counts, and every pool name's P&L at (10, 5), (20, 10), (20, 20)"""
    assert len(L.recs) == len(Bz), (tag, len(L.recs), len(Bz))
    n_paths = 0
    for rec, b in zip(L.recs, Bz):
        assert rec.t == b["t"] and rec.pool.tolist() == sorted(b["pool"]), (tag, rec.t, rec.pool.tolist(), sorted(b["pool"]))
        for q, key in enumerate(("adj", "raw", "beta", "ratio")):
            assert close(getattr(rec, key), [b["pool"][j][q] for j in rec.pool]), (tag, rec.t, key)
        assert rec.traded == bool(b["long"]), (tag, rec.t)
        if rec.traded:
            assert rec.pool[rec.long].tolist() == b["long"] and rec.pool[rec.short].tolist() == b["short"], (tag, rec.t)
            for a, c in ((ADV_BPS, COST_BPS), (20.0, 10.0), (20.0, 20.0)):
                for sd in (1, -1):
                    got = l2_pnl(rec.ratio, sd, a, c)
                    want = [sd * (b["pool"][j][3] - 1.0) - a * 1e-4 - c * 1e-4 * b["pool"][j][3] for j in rec.pool]
                    assert close(got, want), (tag, rec.t, a, c, sd)
                    n_paths += len(want)
    vc, bc = Counter(), Counter()
    for c in L.cnt.values():
        vc.update(c)
    for b in Bz:
        bc.update(b["counts"])
    for k in ("xchk_checked", "xchk_disagree"):
        assert vc[k] == bc[k], (tag, k, vc[k], bc[k])
    return n_paths


def series_check(W, L1, L2, B1, B2):
    """the cells' daily series equal the sum of the recount's position paths booked on rows f .. x (F: $4,000 / $5,000 a name; S: x k)"""
    for kind in ("F", "S"):
        x1 = np.zeros(W.T)
        for rec, b in zip(L1.recs, B1):
            if not b["long"]:
                continue
            nt = SPEC["l1_slot"] * (1.0 if kind == "F" else W.kz[rec["f"] if isinstance(rec, dict) else rec.f])
            for sd, js in ((1, b["long"]), (-1, b["short"])):
                for j in js:
                    x1[b["f"]:b["x"] + 1] += nt * np.array(brute_l1_path(W, b["f"], b["x"], j, sd, b["pool"][j][1])[0])
        assert close(l1_cell(W, L1, kind, l1_cfg()).x, x1), f"L1-{kind} series"
        x2 = np.zeros(W.T)
        for b in B2:
            if not b["long"]:
                continue
            nt = SPEC["l2_slot"] * (1.0 if kind == "F" else W.kz[b["t"]])
            for sd, js in ((1, b["long"]), (-1, b["short"])):
                for j in js:
                    x2[b["t"]] += nt * (sd * (b["pool"][j][3] - 1.0) - ADV_BPS * 1e-4 - COST_BPS * 1e-4 * b["pool"][j][3])
        assert close(l2_cell(W, L2, kind, (ADV_BPS, COST_BPS)).x, x2), f"L2-{kind} series"


def t_constants():
    assert (NREP, SEED, CELLS) == (500, 20261004, ("L1-F", "L1-S", "L2-F", "L2-S")) and YEARS == tuple(range(2016, 2025)) and DD_YEARS == tuple(range(2019, 2026))
    assert (A2_WIN, A2_TARGET, A2_REPORT) == ((TS("2016-07-01"), TS("2018-06-29")), 0.25, (0.5, 2.0)) and "CS" not in globals(), "c is set by volatility on the first two WF years: there is no grid of sizes left to pick from"
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX)
    assert (BOOK_WF, BOOK_LB, TOL, DEEPEST_WF) == ((93.81, 3.816), (155.54, 4.15), (0.006, 0.0006), 44849.0) and sum(DD_REF["by_year"].values()) == DD_REF["days"] == 460 and DD_REF["episodes"] == 28
    assert DD_REF["weeks"] == 92 and EP20 == (TS("2020-03-03"), TS("2020-03-27")) and X20 == (TS("2020-02-15"), TS("2020-04-30"))
    want = {"univ": 500, "px_min": 10.0, "dv_n": 20, "vol_min": 1e6, "atr_min": 0.5, "look": 14, "split_n": 14, "news_x": 3.0, "news_n": 20, "ret_n": 5, "hyg_lead": 5, "l1_n": 25, "l1_slot": 4000.0, "l2_n": 20,
            "l2_slot": 5000.0, "gap_min": 0.01, "rv_max": 2.0, "beta_n": 60, "xchk_l1": 0.25, "xchk_l2": 0.20, "xchk_vol": 0.25, "xchk_floor": 0.25, "squeeze": 0.30, "es_rv_n": 20, "es_med_n": 252, "k_lo": 0.5,
            "k_hi": 2.0}
    assert {k: SPEC[k] for k in want} == want and SPEC["beta_min"] == 55 and SPEC["beta_n"] == 60, "SPEC is the prereg (addendum 1: the beta needs 55 of the 60 sessions, ES holes skipped)"
    assert (COST_BPS, STRESS_BPS, ADV_BPS, ADV_STRESS, L2_STRESS, BORROW, BORROW_STRESS, K_STRESS, SQUEEZE_RATE, AUDIT_N) == (5.0, (10.0, 20.0), 10.0, 20.0, ((20.0, 10.0), (20.0, 20.0)), 0.0025, (0.01, 0.03), 1.5, 0.20, 50)
    assert (RULES["n"], RULES["l1_reb"], RULES["l2_days"], RULES["cov"], RULES["dd_years"], RULES["years"], RULES["best_pct"], RULES["b_n"], RULES["b_l1_reb"], RULES["b_l2_days"], RULES["b_roc"], RULES["b_sort"]) == \
        (100, 26, 60, 0.98, 4, 6, 1, 50, 26, 30, 155.54, 4.15) and abs(RULES["a2_roc"] - 98.5005) < 1e-9 and RULES["a2_sort"] == 3.816 and CHECK_BOOK is True and HYG == ("split", "gap", "tbis", "jump")
    assert ES_D0 == "2014-01-01" and MANIFEST_PREFIX == "380b05f2" and TBIS_CSV.endswith("siporb_split_flags_voltest.csv") and (os.environ.get("EDGELOG_DDW_R1") or OUT.lower().endswith("ddw_r1"))
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        assert prereg_ok()["verified"] is True and len(stamp()["harness_sha256"]) == 64 and "2023-11-24" in stamp()["early_close"] and set(stamp()) >= {"siporb_sha256", "r11_sha256", "r12_sha256", "r13_sha256"}
    assert A13.SRC_RAW == "db_noadj_rth" and A13.SRC_ADJ == "db_adj_rth"


def t_universe():
    """filters and timing: the universe at session t is a function of sessions BEFORE t only"""
    rng = np.random.default_rng(7)
    T, Sn = 45, 7
    Cl, Vv = np.full((T, Sn), 50.0), np.full((T, Sn), 2e6)
    Cl *= 1.0 + 0.001 * np.arange(Sn)                                      # dollar volume rises with the column: name 6 is the largest
    atr, chg = np.full((T, Sn), 1.0), np.zeros((T, Sn), bool)
    Cl[29, 1] = 9.9                                                        # N1: prior close under $10 at t = 30 only
    Cl[15, 2] = np.nan                                                     # N2: a missing session inside the 20-session dollar-volume window for t = 16 .. 35
    Vv[:, 3] = 0.9e6                                                       # N3: mean volume under 1,000,000
    atr[:, 4] = 0.4                                                        # N4: ATR under $0.50
    chg[20, 5] = True                                                      # N5: a registered split at row 20: out for t = 21 .. 34 (the 14 sessions before t)
    U = universe_mask(Cl, Vv, atr, chg, SPEC)
    assert U[30].tolist() == [True, False, False, False, False, False, True] and not U[:20].any(), U[30].tolist()
    assert U[20, 5] and not U[21, 5] and not U[34, 5] and U[35, 5], "split window = the 14 sessions BEFORE t (t itself is hygiene's)"
    assert U[31, 1] and not U[30, 1] and not U[35, 2] and U[36, 2], "price >= $10 on the prior close; a missing dollar-volume session blocks the next 20 sessions"
    Cg, Vg, ag, cg = Cl.copy(), Vv.copy(), atr.copy(), chg.copy()          # garbage on every BASE row from 30 on (the ATR array is derived: its row t already ends at t-1, so row 31 on is garbage): U[:31] cannot change
    Cg[30:], Vg[30:], cg[30:], ag[31:] = rng.uniform(1, 500, Cg[30:].shape), rng.uniform(1, 9e6, Vg[30:].shape), True, 0.01
    assert (universe_mask(Cg, Vg, ag, cg, SPEC)[:31] == U[:31]).all(), "universe(t) uses only sessions < t"
    with spec(univ=3):
        dv = np.array([5e8, 4e8, 3e8, 3e8, 1e8, 1e8, 1e8])                  # dollar volume at $50: volumes 10M .. 2M shares (all pass the 1M floor)
        args = (np.tile(dv / 50.0, (T, 1)), np.full((T, Sn), 1.0), np.zeros((T, Sn), bool))
        assert universe_mask(np.full((T, Sn), 50.0), *args, SPEC)[30].tolist() == [True, True, True, False, False, False, False], "the 3 largest; a tie for third goes to the lower column"
        c0 = np.full((T, Sn), 50.0)
        c0[:, 0] = 5.0                                                     # the largest name is under $10: the filters come FIRST, so the next three fill the universe
        assert universe_mask(c0, *args, SPEC)[30].tolist() == [False, True, True, True, False, False, False]
    x = rng.normal(0, 1, (60, 5))
    x[rng.random(x.shape) < 0.1] = np.nan
    assert close(roll_prev(x, 14), S.roll14(x)) and (prev_any(np.eye(1, 30, 5, dtype=bool).T.repeat(2, axis=1), 14)[:, 0].nonzero()[0] == np.arange(6, 20)).all()
    assert np.isnan(roll_prev(x, 14)[:14]).all() and np.isfinite(roll_prev(np.ones((20, 1)), 14)[14:]).all(), "NaN until 14 sessions exist, then the mean of the PREVIOUS 14"


def t_marks_and_costs():
    """unit_path / l1_pnl on hand numbers: marks, a carried missing bar, a name that stops printing, costs, borrow, the stress rates, -100%, the squeeze; l2_pnl: adverse fills"""
    O = np.array([[10.0, 10.0, 10.0], [10.0, 10.0, 10.0], [11.0, 11.0, 11.0], [12.0, 12.0, 12.0], [13.0, 13.0, np.nan]])
    C = np.array([[10.5, 10.5, 10.5], [10.8, 10.8, 10.8], [11.5, np.nan, 11.5], [12.5, 12.5, 12.5], [13.5, 13.5, 13.5]])
    u = unit_path(O, C, 1, 4, np.array([0, 1, 2]))                           # entry = the open of row 1 (10), closes of rows 1, 2, 3, exit = the open of row 4
    assert close(u.G[0], [0.08, 0.07, 0.10, 0.05]) and close(u.G[1], [0.08, 0.0, 0.17, 0.05]) and close(u.G[2], [0.08, 0.07, 0.10, 0.0]), u.G
    assert u.st.tolist() == [False, False, True] and close(u.ve, [1.3, 1.3, 1.25]) and close(u.mk[1], [1.0, 1.08, 1.08, 1.25]), (u.ve, u.mk)
    one = np.array([0])
    c5 = 5e-4
    assert close(l1_pnl(u, one, 1, l1_cfg(), None)[0], [0.08 - c5, 0.07, 0.10, 0.05 - c5 * 1.3]), "a long: gross marks, 5 bps of the notional in, 5 bps of the exit value out"
    br = lambda h, m: 0.0025 / 252.0 * m
    assert close(l1_pnl(u, one, -1, l1_cfg(), None)[0], [-0.08 - c5, -0.07 - br(1, 1.08), -0.10 - br(2, 1.15), -0.05 - c5 * 1.3 - br(3, 1.25)]), "a short pays borrow on the prior close's mark, nothing on the fill session"
    kt = np.array([1.0, 2.0, 1.0, 1.6])
    sh = l1_pnl(u, one, -1, l1_cfg(borrow=(BORROW, 0.03)), kt)[0]
    assert close(sh, [-0.08 - c5, -0.07 - 0.03 / 252.0 * 1.08, -0.10 - br(2, 1.15), -0.05 - c5 * 1.3 - 0.03 / 252.0 * 1.25]), "the stress rate replaces the base on sessions with k_t > 1.5 (kt = 1.0 / 2.0 / 1.0 / 1.6)"
    assert close(l1_pnl(u, one, -1, l1_cfg(bps=20.0), None)[0][[0, 3]], [-0.08 - 20e-4, -0.05 - 20e-4 * 1.3 - br(3, 1.25)]), "20 bps a side"
    two = np.array([2])
    assert close(l1_pnl(u, two, 1, l1_cfg(), None)[0], [0.08 - c5, 0.07, 0.10, 0.0 - c5 * 1.25]), "stopped printing: exits at the last mark, the exit is still paid (base)"
    assert close(l1_pnl(u, two, 1, l1_cfg(lose100=True), None)[0], [0.08 - c5, 0.07, 0.10, -1.25]), "stress: a long in a name that stopped printing is valued at 0 - the last mark (1.25 of entry) is lost, nothing is sold"
    assert close(l1_pnl(u, two, -1, l1_cfg(lose100=True), None)[0], l1_pnl(u, two, -1, l1_cfg(), None)[0]), "-100% is for longs only"
    sq = l1_pnl(u, one, -1, l1_cfg(squeeze=True), None, np.array([True]))[0]
    assert close(sq, [-0.08 - c5, -0.07 - 0.20 / 252.0 * 1.08, -0.10 - 0.20 / 252.0 * 1.15, -0.05 - c5 * 1.3 - 0.20 / 252.0 * 1.25]) and close(l1_pnl(u, one, -1, l1_cfg(squeeze=True), None, np.array([False])), l1_pnl(u, one, -1, l1_cfg(), None))
    # a split inside the hold: raw prices halve at row 3 (F: 2 -> 1, Alpaca's convention). Split-safe the position is up 2%; the naive raw P&L shows -49%
    Os = np.array([10.0, 10.0, 10.0, 5.1, 5.1])
    Cs = np.array([10.0, 10.0, 10.1, 5.1, 5.1])
    Fs = np.array([2.0, 2.0, 2.0, 1.0, 1.0])
    adj, raw = unit_path((Os / Fs)[:, None], (Cs / Fs)[:, None], 1, 4, np.array([0])), unit_path(Os[:, None], Cs[:, None], 1, 4, np.array([0]))
    assert abs(adj.G[0].sum() - 0.02) < 1e-12 and abs(raw.G[0].sum() - (5.1 / 10.0 - 1.0)) < 1e-12, (adj.G, raw.G)
    r = np.array([1.02])
    assert close(l2_pnl(r, 1, 10.0, 5.0), 0.02 - 0.001 - 0.0005 * 1.02) and close(l2_pnl(r, -1, 10.0, 5.0), -0.02 - 0.001 - 0.0005 * 1.02) and close(l2_pnl(r, 1, 20.0, 20.0), 0.02 - 0.002 - 0.002 * 1.02)
    assert close(l2_pnl(np.array([1.0]), 1, 10.0, 5.0), -0.0015) and close(l2_pnl(np.array([1.0]), -1, 10.0, 5.0), -0.0015), "a flat day costs the adverse fill and the exit cost on BOTH sides"
    # a buy fills at 09:35 x (1 + 10 bps): 100 shares' worth ($5,000 / 50.00 = 100) filled at 50.05 and sold at 51.00 earns 100 x (51.00 - 50.05) less 5 bps of 5,100
    n, p5, cl = 5000.0, 50.0, 51.0
    assert abs(n * l2_pnl(np.array([cl / p5]), 1, 10.0, 5.0)[0] - ((n / p5) * (cl - p5 * 1.001) - 5e-4 * (n / p5) * cl)) < 1e-9
    assert abs(n * l2_pnl(np.array([cl / p5]), -1, 10.0, 5.0)[0] - ((n / p5) * (p5 * 0.999 - cl) - 5e-4 * (n / p5) * cl)) < 1e-9


def t_a2():
    """STAGE A2 (MANAGER's XGAP review, edit 2): c is set by VOLATILITY, never picked on returns: c = 25% x std(#463's daily P&L) / std(the cell's daily P&L at c = 1) over the index rows 2016-07-01 .. 2018-06-29.
    Proved on a synthetic book: the identity (c x the cell's std over the window = exactly 25% of the book's - the number returned and printed by selftest), what c does and does not depend on, the two
    reported books, the pass bar (>= 98.5005 and Sortino >= 3.816, the book at c alone), the cells that have no c, book_at"""
    me = sys.modules[__name__]
    rng = np.random.default_rng(31)
    ix = pd.bdate_range("2016-07-01", "2026-06-30")                                         # the lockbox rows are in the index: A2 must never read them
    book = rng.normal(35.0, 650.0, len(ix))
    mk = lambda raw: SimpleNamespace(index=ix, raw=raw, n=len(ix), mask=lambda lo, hi: np.asarray((ix >= lo) & (ix <= hi)))
    B = mk(book)
    win, wd = B.mask(*A2_WIN), pd.bdate_range("2016-07-01", "2018-06-29")
    assert win.sum() == len(wd) and ix[win][0] == TS("2016-07-01") and ix[win][-1] == TS("2018-06-29"), "the window is the first two WF years, both end days inside it"
    cell = rng.normal(5.0, 120.0, len(ix))
    a2 = a2_cell(B, cell)
    c = a2["c"]
    sb, sc = float(np.std(book[win], ddof=1)), float(np.std(cell[win], ddof=1))
    assert c > 0 and abs(c - A2_TARGET * sb / sc) <= 1e-12 * c and abs(a2["std_book"] - sb) <= 1e-12 * sb and abs(a2["std_cell"] - sc) <= 1e-12 * sc, "c = 25% x std(#463) / std(the cell) on the window"
    assert a2["window"] == ["2016-07-01", "2018-06-29"] and a2["rows"] == int(win.sum()) and a2["target"] == 0.25 and a2["needs"] == {"roc": RULES["a2_roc"], "sortino": RULES["a2_sort"]}
    ratio = float(np.std(c * cell[win], ddof=1) / np.std(book[win], ddof=1))
    assert abs(ratio - 0.25) < 1e-12 and abs(np.std(c * cell[win]) / np.std(book[win]) - 0.25) < 1e-12, "c x the cell's std over the window = exactly 25% of #463's (either ddof)"
    # the cell = the book (or its mirror image): c is 0.25 whatever the sign
    assert abs(a2_cell(B, book)["c"] - 0.25) < 1e-12 and abs(a2_cell(B, -book)["c"] - 0.25) < 1e-12
    # c depends on the cell's VOLATILITY over the window - not on its sign or mean (its returns), not on anything outside the window; it halves when the cell doubles
    assert abs(a2_cell(B, 2.0 * cell)["c"] - c / 2.0) <= 1e-12 * c and abs(a2_cell(B, -cell)["c"] - c) <= 1e-12 * c and abs(a2_cell(B, cell + 5000.0)["c"] - c) <= 1e-9 * c, "no sign, no mean, 1/size"
    spike = lambda d, v=1e6: np.where(np.asarray(ix == TS(d)), v, 0.0)
    assert a2_cell(B, cell + spike("2018-07-02"))["c"] == c and a2_cell(B, cell + spike("2025-06-26"))["c"] == c, "a day after the window changes nothing"
    for d_ in ("2016-07-01", "2018-06-29"):
        assert a2_cell(B, cell + spike(d_))["c"] < 0.5 * c, f"the window's end day {d_} is inside it"
    assert a2_cell(mk(np.where(ix >= TS("2018-07-02"), 10.0 * book, book)), cell)["c"] == c, "#463's own days after the window do not enter c"
    book3 = book.copy()
    book3[0] += 1e6
    assert a2_cell(mk(book3), cell)["c"] > 2.0 * c, "nor do they leave it: the book's first row is in the window"
    # the book at c, 0.5c and 2c on the WF stretch: explicit sums, the yardstick r11_risk.stats; the three are different books, only the first is judged
    wf = B.mask(WF0, PRE_END)
    for rec, m in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
        want = R11.stats((book + m * c * cell)[wf], ix[wf])
        assert abs(rec["c"] - m * c) <= 1e-12 * c and abs(rec["roc"] - want["roc"]) < 1e-9 and abs(rec["sortino"] - want["sort"]) < 1e-9 and abs(rec["net"] - want["net"]) < 1e-6, (m, rec)
    assert a2["at_double_c"]["roc"] > a2["roc"] > a2["at_half_c"]["roc"], "this fixture's cell has positive drift: more of it, more ROC"
    lb = np.asarray(ix >= LB0)                                                           # wild P&L on the lockbox rows (book and cell): the whole A2 record is untouched - A2 is a WF-only judgement
    assert a2_cell(mk(np.where(lb, 50.0 * book - 1e5, book)), np.where(lb, 50.0 * cell + 1e5, cell)) == a2, "A2 never reads the lockbox"
    # the verdict: the book at c alone, ROC >= the bar AND Sortino >= the bar, ties pass; a bar that only the 0.5c / 2c book clears is not cleared
    for bar_r, bar_s, want in ((a2["roc"], a2["sortino"], True), (a2["roc"] + 1e-9, a2["sortino"], False), (a2["roc"], a2["sortino"] + 1e-9, False), (a2["roc"] - 1.0, a2["sortino"] - 1.0, True)):
        with patched(me, RULES={**RULES, "a2_roc": bar_r, "a2_sort": bar_s}):
            r_ = a2_cell(B, cell)
        assert r_["pass"] is want and r_["c"] == c and r_["needs"] == {"roc": bar_r, "sortino": bar_s}, (bar_r, bar_s, want)
    with patched(me, RULES={**RULES, "a2_roc": a2["at_double_c"]["roc"], "a2_sort": -1e9}):
        assert a2_cell(B, cell)["pass"] is False, "the 2c book clears this bar, the judged book (c) does not: the reported books are never judged"
    assert abs(RULES["a2_roc"] - 1.05 * 93.81) < 1e-9 and RULES["a2_sort"] == 3.816 and a2["pass"] is False, "the real bar (98.5005 / 3.816): a coin-flip cell on a coin-flip book does not clear it"
    # the cells that have no c: no P&L at all, a constant, P&L only after the window, a book with no spread - A2 fails, with the reason, and nothing is reported
    for nm, x_ in (("no P&L", np.zeros(len(ix))), ("a constant", np.full(len(ix), 17.0)), ("only after the window", np.where(ix >= TS("2018-07-02"), cell, 0.0))):
        r_ = a2_cell(B, x_)
        assert math.isnan(r_["c"]) and r_["pass"] is False and "no c" in r_["error"] and r_["at_half_c"] is None and r_["at_double_c"] is None and math.isnan(r_["roc"]), nm
    r_ = a2_cell(mk(np.zeros(len(ix))), cell)
    assert math.isnan(r_["c"]) and r_["pass"] is False and "no c" in r_["error"], "a book with no spread has no c either"
    one = a2_cell(B, spike("2017-01-03", 100.0))                                          # a cell that trades ONE day of the window still has a c (a large one: its spread is small)
    assert math.isfinite(one["c"]) and one["c"] > 20.0 and abs(one["c"] * one["std_cell"] - 0.25 * one["std_book"]) <= 1e-12 * one["std_book"]
    # book_at on its own: [lo, hi] inclusive, c x the series, and an empty slice is NaN (never an exception)
    k = B.mask(TS("2020-01-02"), TS("2020-06-30"))
    ba = book_at(B, cell, 2.5, TS("2020-01-02"), TS("2020-06-30"))
    want = R11.stats((book + 2.5 * cell)[k], ix[k])
    assert ba["c"] == 2.5 and abs(ba["roc"] - want["roc"]) < 1e-9 and abs(ba["sortino"] - want["sort"]) < 1e-9 and ba["net"] == float((book + 2.5 * cell)[k].sum()) and ba["max_dd"] == want["max_dd"]
    assert math.isnan(book_at(B, cell, 1.0, TS("2030-01-01"), TS("2030-02-01"))["roc"])
    return ratio


def t_stage_b_checks():
    """STAGE B's pass (MANAGER #48) is the LEG's standalone veto: each of the four checks broken alone fails exactly itself, the breadth bar differs by leg (L1 26 weekly rebalances, L2 30 traded sessions), the
    bars are inclusive, a NaN fails, and the verdict has no input for the book add"""
    ok_leg = {"n_pos": 80, "n_units": 40, "net": 1000.0, "net_ex_top_pos": 400.0}
    for cell in CELLS:
        chk = b_checks(cell, ok_leg)
        assert len(chk) == 4 and all(chk.values()), (cell, chk)
    for cell in CELLS:
        l1 = cell[:2] == "L1"
        names = {"n_pos": "leg name-periods>=50", "n_units": "leg weekly rebalances>=26" if l1 else "leg traded sessions>=30", "net": "leg net>0", "net_ex_top_pos": "leg net>0 without its top name-period"}
        for key, bad in (("n_pos", 49), ("n_pos", 0), ("n_units", 25 if l1 else 29), ("n_units", 0), ("net", 0.0), ("net", -1.0), ("net", float("nan")), ("net_ex_top_pos", 0.0), ("net_ex_top_pos", -1.0),
                         ("net_ex_top_pos", float("nan"))):
            chk = b_checks(cell, {**ok_leg, key: bad})
            assert [k for k, v in chk.items() if not v] == [names[key]], (cell, key, bad, chk)
        assert all(b_checks(cell, {**ok_leg, "n_pos": 50, "n_units": 26 if l1 else 30}).values()), "the bars are inclusive"
    assert b_units("L1-S") == (26, "weekly rebalances") and b_units("L2-F") == (30, "traded sessions")
    import inspect
    assert list(inspect.signature(b_checks).parameters) == ["cell", "leg"], "no book argument: the book add cannot be part of the pass"


def t_beta_holes():
    """L2's beta and the holes in the ES masters. The registered rule is 'all 60 present' (SPEC beta_min = 60): ONE undefined ES return in the 60-session window leaves every name without a beta. The opt-in tolerance
    (beta_min < 60) drops the ES-hole sessions from the regression for every name while >= beta_min remain; a NAME with a hole of its own still has no beta. Both against the plain-python OLS; es_blind and
    es_hole_report say where the registered rule blinds L2"""
    me = sys.modules[__name__]
    bm_reg = SPEC["beta_min"]
    assert bm_reg == 55, "prereg addendum 1 (2026-10-05): the beta needs 55 of the 60 sessions"
    with spec(univ=16, l1_n=3, l2_n=3, beta_min=60):                                     # the strict all-60 rule first (the rule before addendum 1)
        W = toy_world()
        t, allc = 130, np.arange(W.S)
        ref = W.betas(t, allc)
        with spec(beta_min=bm_reg):                                                   # addendum 1: one ES hole no longer blinds L2; five still leave 55
            for holes in ([100], [71, 100, 129, 80, 90]):
                W5 = toy_world()
                W5.es.ret[holes] = np.nan
                assert np.isfinite(W5.betas(t, allc)).sum() == np.isfinite(ref).sum(), holes
            W5.es.ret[[101]] = np.nan
            assert np.isnan(W5.betas(t, allc)).all(), "six ES holes leave 54 of 60: no beta"
        assert SPEC["beta_min"] == SPEC["beta_n"] == 60 and np.isfinite(ref).sum() >= 12 and np.isnan(ref[5]), "registered: all 60 present; N05's own missing close (row 83) leaves it without a beta"
        for holes in ([100], [71, 100, 129], [70, 71, 72, 73, 74]):                      # rows inside the window t-60 .. t-1 = 70 .. 129
            W2 = toy_world()
            W2.es.ret[holes] = np.nan
            assert np.isnan(W2.betas(t, allc)).all() and all(brute_beta(W2, t, j) is None for j in range(W2.S)), "registered: one hole blinds every name"
            for bm in (60, 59, 58, 57, 56, 55, 50):
                with spec(beta_min=bm):
                    got, ok = W2.betas(t, allc), (60 - len(holes) >= bm)
                    assert np.isfinite(got).any() == ok and (not ok or (np.isfinite(got).sum() == np.isfinite(ref).sum() and np.isnan(got[5]))), (holes, bm)
                    for j in range(W2.S):
                        bb = brute_beta(W2, t, j)
                        assert (bb is None and not np.isfinite(got[j])) or (bb is not None and abs(bb - got[j]) < 1e-9), (holes, bm, j)
        # the planted slope is recovered EXACTLY when the hole sessions are dropped (a name that is 1.5 x ES on every session that has an ES return)
        W2 = toy_world()
        e = np.random.default_rng(4).normal(0.0, 0.01, W2.T)
        e[0] = np.nan
        W2.Cl[1:, 3] = W2.Cl[0, 3] * np.cumprod(1.0 + 1.5 * e[1:])
        W2.derive()
        W2.es.ret[:] = e
        W2.es.ret[[80, 81]] = np.nan
        assert np.isnan(W2.betas(100, np.array([3]))[0])
        with spec(beta_min=58):
            assert abs(W2.betas(100, np.array([3]))[0] - 1.5) < 1e-9 and np.isnan(W2.betas(100, np.array([5]))[0])
        with spec(beta_min=59):
            assert np.isnan(W2.betas(100, np.array([3]))[0]), "58 valid pairs are not 59"
        # es_blind / es_hole_report: holes at rows 62 and 125 blind the 60 sessions after each under the registered rule (the windows' edges are past the warm-up, so an off-by-one shows); with beta_min 57 only the warm-up is blind
        W3 = toy_world()
        W3.es.ret[[62, 125]] = np.nan
        blind, hd = es_blind(W3)
        want = np.array([tt < 61 or any(tt - 60 <= h <= tt - 1 for h in (62, 125)) for tt in range(W3.T)])
        assert (blind == want).all() and list(hd) == [W3.days[62], W3.days[125]]
        txt, rec = es_hole_report(W3)
        wf = (W3.days >= WF0) & (W3.days <= PRE_END)
        assert txt.startswith("WARNING - ES holes") and rec["undefined_es_return_sessions"] == [f"{W3.days[62]:%Y-%m-%d}", f"{W3.days[125]:%Y-%m-%d}"] and rec["l2_blind_sessions"] == int((want & wf).sum()), (txt, rec)
        assert rec["l2_blind_by_year"] == {2024: int((want & wf).sum())} and rec["beta_min"] == 60 and rec["sessions"] == int(wf.sum()) and rec["stretch"] == ["2016-07-01", "2025-06-29"]
        # a stretch of its own (Stage B's lockbox): only the holes that can reach it are listed (rows 70 .. 129 are the windows of the sessions from row 130 on: the hole at 62 cannot), only its sessions are counted
        t0, t1 = W3.days[130], W3.days[149]
        txt2, rec2 = es_hole_report(W3, t0, t1)
        assert rec2["undefined_es_return_sessions"] == [f"{W3.days[125]:%Y-%m-%d}"] and rec2["l2_blind_sessions"] == int(want[130:150].sum()) == 20 and rec2["sessions"] == 20 and rec2["stretch"] == [f"{t0:%Y-%m-%d}", f"{t1:%Y-%m-%d}"], rec2
        assert txt2.startswith("WARNING - ES holes (2024-") and "20 of 20 sessions" in txt2
        txt3, rec3 = es_hole_report(W3, W3.days[100], W3.days[121])                         # rows 100 .. 121: windows 40 .. 120 hold the hole at 62 (and not 125): blind on 100 .. 121 (hole 62 is in every window up to row 122)
        assert rec3["undefined_es_return_sessions"] == [f"{W3.days[62]:%Y-%m-%d}"] and rec3["l2_blind_sessions"] == 22, rec3
        with spec(beta_min=57):                                                           # two holes leave 58 of 60 returns: not blind past the warm-up (the toy's first 61 sessions have no full window; they sit in WF here)
            b57 = es_blind(W3)[0]
            assert (b57 == np.array([tt < 61 for tt in range(W3.T)])).all() and es_hole_report(W3)[1]["l2_blind_sessions"] == 61
            t4, r4 = es_hole_report(W3, t0, t1)
            assert r4["l2_blind_sessions"] == 0 and not t4.startswith("WARNING"), (t4, r4)


def t_pipeline():
    """the vectorised L1 / L2 builds against the plain-python recount on the toy world, in every reading (registered / look-ahead, no-news / news-only), then the planted cases one by one"""
    with spec(univ=16, l1_n=3, l2_n=3):
        W = toy_world()
        W.aud1[85, 11] = True                                                              # N11: a hand-audit data event at fill session 85 (L1) ...
        W.aud2[120, 12] = True                                                             # ... and N12 on L2's session 120
        lo, hi = W.days[0], W.days[-1]
        n = 0
        for pm in ("remove", "naive"):
            for nm in ("exclude", "only"):
                L1, L2 = l1_build(W, lo, hi, pm, nm), l2_build(W, lo, hi, pm, nm)
                n += compare_l1(W, L1, brute_l1(W, lo, hi, pm, nm), f"L1 {pm}/{nm}") + compare_l2(W, L2, brute_l2(W, lo, hi, pm, nm), f"L2 {pm}/{nm}")
                if (pm, nm) == ("remove", "exclude"):
                    series_check(W, L1, L2, brute_l1(W, lo, hi, pm, nm), brute_l2(W, lo, hi, pm, nm))
                    Lr1, Lr2 = L1, L2
                if (pm, nm) == ("naive", "exclude"):
                    Lk1, Lk2 = L1, L2
        assert sum(r.traded for r in Lr1.recs) >= 20 and sum(r.traded for r in Lr2.recs) >= 20, "the toy world trades"
        by = lambda L, key: {getattr(r, key): r for r in L.recs}
        r1, k1, r2, k2 = by(Lr1, "r"), by(Lk1, "r"), by(Lr2, "t"), by(Lk2, "t")
        cols = lambda r: r.pool.tolist()
        # N00, the registered 2-for-1 at row 70: a flag at the exit session / at the fill session is a look-ahead removal; two weeks later the universe itself drops the name
        for key in (64, 69):
            assert 0 not in cols(r1[key]) and 0 in cols(k1[key]) and k1[key].naive[cols(k1[key]).index(0)], f"split inside the hold ({key})"
        assert 0 not in cols(r1[74]) and 0 not in cols(k1[74]) and not W.U[75, 0] and W.U[70, 0], "no registered split in the 14 sessions BEFORE the fill session: the universe drops the name at 75"
        i0 = cols(k1[64]).index(0)                                                           # the naive raw path shows the split as a -50% loss, the registered split-safe one does not
        sp_safe, naive = unit_path(W.Ao, W.Ac, 65, 70, np.array([0])), k1[64].U
        assert abs(naive.G[i0].sum() - (W.Od[70, 0] / W.Od[65, 0] - 1.0)) < 1e-12 and naive.G[i0].sum() < -0.35 and abs(sp_safe.G[0].sum()) < 0.2 and abs(
            sp_safe.G[0].sum() - (W.Ao[70, 0] / W.Ao[65, 0] - 1.0)) < 1e-12, (naive.G[i0].sum(), sp_safe.G[0].sum())
        # N01 (gap scan) at 90: post-flag for the weeks ending at 90 / starting at 90, pre-flag after; N02 (TBIS) at 100; N03 (the +-50% rule) at 110
        for col, row in ((1, 90), (2, 100), (3, 110)):
            for r_ in (row - 6, row - 1):                                                    # the exit session / the fill session of the week
                assert col not in cols(r1[r_]) and col in cols(k1[r_]) and k1[r_].naive[cols(k1[r_]).index(col)], (col, row, r_)
            assert col not in cols(r1[row + 4]) and col not in cols(k1[row + 4]), "a flag inside the window BEFORE the decision removes the name in both readings"
            assert col in cols(r1[row + 14]) and col in cols(k1[row + 14]), "past the hygiene window (it starts nine sessions before the ranking day) the flag is out of reach and the name is back, in both readings"
        # N04 stops printing at row 120: exits at its last mark in the week ending there, and has no fill the week after
        i4 = cols(r1[114]).index(4)
        assert r1[114].U.st[i4] and abs(r1[114].U.G[i4, -1]) < 1e-15 and 4 not in cols(r1[119]), "stopped printing: exit at the last mark; no open at the fill session = not eligible"
        # N05 misses the close of row 83: the mark carries inside the week 80 .. 85
        i5 = cols(r1[79]).index(5)
        assert r1[79].U.G[i5, 3] == 0.0 and r1[79].U.G[i5, 4] != 0.0, "a missing close: a zero day, the whole gap on the next"
        # N06 has a news session at row 40: out of a no-news book in the week ranked at 44, in the news-only twin, back in the week after
        assert 6 not in cols(r1[44]) and 6 in cols(r1[49])
        with_news = by(l1_build(W, lo, hi, "remove", "only"), "r")
        assert 6 in cols(with_news[44]) and 6 not in cols(with_news[49]), "the twin made of the news-excluded names"
        # N07 has no news baseline for the ranking sessions 50-52: unknown, excluded from both
        assert 7 not in cols(r1[54]) and 7 not in cols(with_news[54])
        # the large-move cross-check: N08 (vol x price = 1) at the week ranked at 79, N10 (a whole ratio) at 99, N12 (a factor drift) at 109 are removed - N09 (vol x price = 1.43) at 89 stays and is the best long
        for c, r_ in ((8, 79), (10, 99), (12, 109)):
            assert c not in cols(r1[r_]) and c not in cols(k1[r_]), (c, r_)
        assert 9 in cols(r1[89]) and 9 in r1[89].pool[r1[89].long].tolist(), "a genuine -35% move with ordinary volume is the family's best long"
        tot = Counter()
        for c in Lr1.cnt.values():
            tot.update(c)
        assert tot["xchk_f1"] >= 1 and tot["xchk_f2"] >= 1 and tot["xchk_f3"] >= 1 and tot["xchk_disagree"] >= 3, dict(tot)
        # the audit: N11 at fill 85 is gone from the cell and the pool (and counted), in every reading
        assert 11 not in cols(r1[84]) and 11 not in cols(k1[84]) and tot["audit"] >= 1 and ("L1", 85, 11) in W.aud_hit
        # L2: N13's Relative Volume 2.5, N14's news session the day before, N15's missing 09:30 bar, the volume-confirmed -28% gap of N09 at 130, the TBIS flag of N02 at 100 (kept by the look-ahead reading)
        assert 13 not in cols(r2[100]) and 14 not in cols(r2[102]) and 15 not in cols(r2[103]) and 9 not in cols(r2[130]) and 9 not in cols(k2[130]), "L2's removals"
        with_news2 = by(l2_build(W, lo, hi, "remove", "only"), "t")
        assert 13 in cols(with_news2[100]) and 14 in cols(with_news2[102]), "the news-only twin of L2"
        assert 2 not in cols(r2[100]) and 2 in cols(k2[100]) and 2 not in cols(r2[103]) and 2 not in cols(k2[103]), "L2: a flag ON session t is the hold's, one before it is known"
        assert 12 not in cols(r2[120]) and 12 not in cols(k2[120]), "the audit removes from L2 too"
        # the gap floor and the sides rule: the session trades only if every selected adjusted gap is beyond the floor and both sides fill (here: 2 a side, a 2% floor, so the rule binds on the toy's wide gaps)
        with spec(gap_min=0.0, l2_n=2):
            L2a = l2_build(W, lo, hi, "remove", "exclude")
        with spec(gap_min=0.02, l2_n=2):
            L2g = l2_build(W, lo, hi, "remove", "exclude")
            assert 0 < sum(r.traded for r in L2g.recs) < sum(r.traded for r in L2a.recs) and all(
                (r.adj[r.long] <= -0.02).all() and (r.adj[r.short] >= 0.02).all() for r in L2g.recs if r.traded), "only |adjusted gap| >= the floor"
            assert sum(r.traded for r in L2g.recs) >= 5 and Counter(c_ for c in L2g.cnt.values() for c_, v in c.items() for _ in range(v))["thin_side"] > 0
            compare_l2(W, L2g, brute_l2(W, lo, hi), "L2 2%")
        # every L1 rebalance sits in its stretch by EXIT session; one whose exit is past the data is unresolved and counted
        late = l1_build(W, W.days[100], W.days[-1])
        assert all(W.days[r.x] >= W.days[100] for r in late.recs) and late.cnt[2024]["unresolved"] == 1 and late.recs[-1].x == W.T - 5 and late.recs[-1].r == W.T - 11, "the last Friday's position has no next fill: unresolved, counted, not a rebalance"
        rr, ff, xx = l1_schedule(W.days)
        assert xx[-1] == -1 and (xx[:-1] == ff[1:]).all() and (ff == rr + 1).all() and ff[0] == 5 and W.days[rr[0]].day_name() == "Friday" and ff[-1] < W.T
        for rec in Lr1.recs:                                                                 # stretch membership by exit date
            assert lo <= W.days[rec.x] <= hi
        sub = l1_build(W, W.days[50], W.days[80])
        assert [W.days[r.x] for r in sub.recs] == [d for d in W.days[xx[xx >= 0]] if W.days[50] <= d <= W.days[80] and rr[list(xx).index(W.days.get_loc(d))] >= 5]
        # the K reading differs from the registered one only by the in-hold names (more names in the pool, never fewer)
        for a, b in zip(Lr1.recs, Lk1.recs):
            assert set(a.pool.tolist()) <= set(b.pool.tolist())
        # betas against the plain-python OLS, NaN on a missing session, the planted slope recovered exactly
        for t in (70, 100, 130):
            got = W.betas(t, np.arange(W.S))
            for j in range(W.S):
                bb = brute_beta(W, t, j)
                assert (bb is None and not np.isfinite(got[j])) or (bb is not None and abs(bb - got[j]) < 1e-9), (t, j)
        W2 = toy_world()
        W2.Cl[1:, 3] = W2.Cl[0, 3] * np.cumprod(1.0 + 1.5 * W2.es.ret[1:])
        W2.derive()
        assert abs(W2.betas(100, np.array([3]))[0] - 1.5) < 1e-9, "beta = the slope of the name's return on ES's"
        W2.es.ret[80] = np.nan
        with spec(beta_min=60):
            assert np.isnan(W2.betas(100, np.array([3]))[0]) and np.isfinite(W2.betas(150, np.array([3]))[0]), "the strict all-60 rule: a missing ES return inside the window: no beta"
        assert abs(W2.betas(100, np.array([3]))[0] - 1.5) < 1e-9, "addendum 1 (55 of 60): one missing ES return is skipped and the slope is kept"
    return n


def t_null():
    with spec(univ=16, l1_n=3, l2_n=3):
        W = toy_world()
        lo, hi = W.days[0], W.days[-1]
        L1, L2 = l1_build(W, lo, hi), l2_build(W, lo, hi)
        d = draw_order(np.random.default_rng(1), 200, 10, 6)
        assert d.shape == (200, 6) and (d >= 0).all() and (d < 10).all() and all(len(set(r)) == 6 for r in d.tolist()) and (draw_order(np.random.default_rng(1), 200, 10, 6) == d).all(), "no repeats, seeded"
        assert (np.sort(d[:, :3], axis=1) != np.sort(d[:, 3:], axis=1)).any() and all(not set(r[:3]) & set(r[3:]) for r in d.tolist()), "longs and shorts of a draw are disjoint"
        d = draw_order(np.random.default_rng(2), 60000, 10, 6)
        assert np.abs(np.bincount(d.ravel(), minlength=10) / 60000.0 - 0.6).max() < 0.01 and np.abs(np.bincount(d[:, 0], minlength=10) / 60000.0 - 0.1).max() < 0.01 and np.abs(
            np.bincount(d[:, 5], minlength=10) / 60000.0 - 0.1).max() < 0.01, "every name is in 6 of 10 draws, and any position of the ordered sample is uniform"
        try:
            draw_order(np.random.default_rng(1), 5, 4, 5)
            raise AssertionError("cannot draw more names than the pool holds")
        except ValueError:
            pass
        # the null's draws are uniform subsets of each rebalance's pool: the mean total P&L is the exact expectation, nn x (mean long path + mean short path) per rebalance
        a1, b1 = null_l1(W, L1, 400, np.random.default_rng(5))
        exp = 0.0
        for rec in L1.recs:
            if rec.traded:
                idx = np.arange(len(rec.pool))
                kt = W.k[rec.f:rec.x + 1]
                exp += SPEC["l1_slot"] * SPEC["l1_n"] * float(l1_pnl(rec.U, idx, 1, l1_cfg(), kt).mean(axis=0).sum() + l1_pnl(rec.U, idx, -1, l1_cfg(), kt).mean(axis=0).sum())
        tot = a1.sum(axis=1)
        assert abs(tot.mean() - exp) < 4.5 * tot.std() / math.sqrt(len(tot)), (tot.mean(), exp, tot.std())
        a2, b2 = null_l2(W, L2, 400, np.random.default_rng(5))
        exp = sum(SPEC["l2_slot"] * SPEC["l2_n"] * float(l2_pnl(r.ratio, 1, ADV_BPS, COST_BPS).mean() + l2_pnl(r.ratio, -1, ADV_BPS, COST_BPS).mean()) for r in L2.recs if r.traded)
        tot = a2.sum(axis=1)
        assert abs(tot.mean() - exp) < 4.5 * tot.std() / math.sqrt(len(tot)), (tot.mean(), exp, tot.std())
        assert (null_l1(W, L1, 20, np.random.default_rng(9))[0] == null_l1(W, L1, 20, np.random.default_rng(9))[0]).all() and not (
            null_l1(W, L1, 20, np.random.default_rng(9))[0] == null_l1(W, L1, 20, np.random.default_rng(10))[0]).all(), "seeded"
        # the F and S cells of a leg use the SAME draw: S = F x k (k constant here, so exactly), and an undefined k means no position
        W.kz[:] = 2.5
        a, b = null_l1(W, L1, 30, np.random.default_rng(3))
        assert close(b, 2.5 * a)
        a, b = null_l2(W, L2, 30, np.random.default_rng(3))
        assert close(b, 2.5 * a)
        W.kz[:] = 0.0
        assert not null_l1(W, L1, 5, np.random.default_rng(3))[1].any() and not l1_cell(W, L1, "S", l1_cfg()).x.any() and l1_cell(W, L1, "F", l1_cfg()).x.any(), "k undefined = no S position"
        # a null draw only ever holds names of that rebalance's pool, so a hygiene-removed name can never be drawn: with a pool of exactly 2 x nn the draw IS the pool
        with spec(l1_n=1):
            Wt = toy_world()
            Lt = l1_build(Wt, Wt.days[0], Wt.days[-1])
            for rec in Lt.recs:
                if rec.traded and len(rec.pool) == 2:
                    o = draw_order(np.random.default_rng(1), 50, 2, 2)
                    assert (np.sort(o, axis=1) == [0, 1]).all()


def t_stats():
    """DO / rho_dd are MDL r1's (against r12_mdl's independent implementation), the year and ex-episode tests, the null's statistics, the cell statistics, the checks one by one"""
    rng = np.random.default_rng(11)
    ix = pd.bdate_range("2016-07-01", "2025-06-27")
    book = rng.normal(35.0, 650.0, len(ix))
    book[(ix >= "2020-03-03") & (ix <= "2020-03-27")] -= 900.0                          # a deep episode in March 2020 so the ex-episode test has something to remove
    B = SimpleNamespace(index=ix, raw=book, n=len(ix), mask=lambda lo, hi: np.asarray((ix >= lo) & (ix <= hi)))
    S12 = M12.Stretch(book, ix, None, WF0, PRE_END)
    leg = -0.4 * book + rng.normal(10.0, 300.0, len(ix))
    sm = seat_measure(S12, leg)
    rho, do = M12.naive_rho_do(leg[S12.rows], book[S12.rows], S12.dates, S12.dd)
    assert abs(sm["rho_dd"] - rho) < 1e-9 and abs(sm["DO"] - do) < 1e-9, (sm["rho_dd"], rho, sm["DO"], do)
    yr = S12.dates.year.to_numpy()
    for y in DD_YEARS:
        m = S12.dd & (yr == y)
        loss = -book[S12.rows][m].sum()
        assert abs(sm["by_year"][y]["DO"] - (leg[S12.rows][m].sum() / loss if m.any() and loss > 0 else float("nan"))) < 1e-9 or (math.isnan(sm["by_year"][y]["DO"]) and not (m.any() and loss > 0))
    ex = S12.dd & ~((S12.dates >= "2020-03-03") & (S12.dates <= "2020-03-27"))
    assert abs(sm["DO_ex_episode"] - leg[S12.rows][ex].sum() / -book[S12.rows][ex].sum()) < 1e-9 and sm["years_pos"] == sum(v["DO"] > 0 for v in sm["by_year"].values())
    # a leg that earns ONLY inside the March 2020 episode has DO > 0 but no DO without it; one that earns only outside has the opposite
    ep = np.asarray((ix >= "2020-03-03") & (ix <= "2020-03-27"))
    in_dd = np.isin(np.arange(len(ix)), S12.rows[S12.dd])                                # the index rows that are #463's DD days
    inside = np.where(ep, 500.0, 0.0)
    a, b = seat_measure(S12, inside), seat_measure(S12, -inside + 1e-9)
    assert a["DO"] > 0 and abs(a["DO_ex_episode"]) < 1e-12 and b["DO"] < 0
    outside = np.where(in_dd & ~ep, 80.0, 0.0)
    c = seat_measure(S12, outside)
    assert c["DO_ex_episode"] > 0 and c["DO"] > 0
    z = seat_measure(S12, np.zeros(len(ix)))
    assert z["DO"] == 0.0 and z["years_pos"] == 0 and not (z["DO"] > 0), "no P&L, no earning"
    # the null's statistics: max ROC, max DO, min rho_dd over the 4 cells, then the percentiles
    acc = [rng.normal(5, 100, (40, len(ix))) for _ in range(4)]
    pc = {c_: null_cell(S12, np.asarray(a_), np.arange(len(ix)), len(ix)) for c_, a_ in zip(CELLS, acc)}
    ns = null_summary(pc)
    mx = np.max(np.vstack([pc[c_][0] for c_ in CELLS]), axis=0)
    assert abs(ns["roc_max"]["p95"] - np.percentile(mx, 95)) < 1e-9 and abs(ns["rho_min"]["p5"] - np.percentile(np.min(np.vstack([pc[c_][1] for c_ in CELLS]), axis=0), 5)) < 1e-9 and ns["draws"] == 40
    for q in range(5):
        r_, rho_, do_ = null_cell(S12, acc[0][q:q + 1], np.arange(len(ix)), len(ix))
        s_ = R11.stats(acc[0][q][S12.rows], S12.dates)
        n_, d_ = M12.naive_rho_do(acc[0][q][S12.rows], book[S12.rows], S12.dates, S12.dd)
        assert abs(r_[0] - s_["roc"]) < 1e-9 and abs(rho_[0] - n_) < 1e-9 and abs(do_[0] - d_) < 1e-9, "the vectorised twins equal r11 / r12's scalar code"
    # cell_stats on a hand series
    ds = pd.bdate_range("2017-01-02", periods=8)
    Bs = SimpleNamespace(index=ds, n=8, mask=lambda lo, hi: np.asarray((ds >= lo) & (ds <= hi)))
    xs, cs = np.array([100.0, -50.0, 0.0, 200.0, -150.0, 50.0, 0.0, -50.0]), np.array([2, 1, 0, 1, 3, 1, 0, 1])
    pos = SimpleNamespace(pnl=np.array([300.0, 50.0, -10.0, -240.0, 0.0]))
    st = cell_stats(Bs, xs, cs, ds[0], ds[-1], SimpleNamespace(n_pos=5, n_units=3, pos=pos))
    s0 = R11.stats(xs, ds)
    assert st["net"] == 100.0 and abs(st["roc"] - s0["roc"]) < 1e-12 and abs(st["sortino"] - s0["sort"]) < 1e-12 and st["max_dd"] == s0["max_dd"] == 150.0 and st["days"] == 6 and st["best_days_n"] == 1
    assert st["net_ex_best_days"] == 100.0 - 200.0 and st["best_pos_n"] == 1 and st["net_pos"] == 100.0 and st["net_ex_best_pos"] == -200.0 and st["top_pos"] == 300.0 and st["net_ex_top_pos"] == -200.0
    assert st["years_pos"] == 1 and st["by_year"][2016] == 100.0 and st["by_year"][2017] == 0.0 and st["n_pos"] == 5 and st["n_units"] == 3
    d20 = pd.bdate_range("2020-02-03", periods=80)
    B20 = SimpleNamespace(index=d20, n=80, mask=lambda lo, hi: np.asarray((d20 >= lo) & (d20 <= hi)))
    x20 = np.where((d20 >= "2020-02-15") & (d20 <= "2020-04-30"), 100.0, -1.0)
    s20 = cell_stats(B20, x20, np.ones(80), d20[0], d20[-1], SimpleNamespace(n_pos=0, n_units=0, pos=None))
    assert abs(s20["net_ex2020"] - (-1.0 * (80 - ((d20 >= "2020-02-15") & (d20 <= "2020-04-30")).sum()))) < 1e-9 and s20["net"] > 0 > s20["net_ex2020"], "net without Feb 15 - Apr 30 2020"
    assert [ceil_pct(n_, 1) for n_ in (0, 1, 99, 100, 101, 250, 700, 701)] == [0, 1, 1, 1, 2, 3, 7, 8]
    # the checks, one by one: a passing cell, then each condition broken alone
    st_ok = {"n_pos": 500, "n_units": 100, "net": 1000.0, "roc": 40.0, "sortino": 2.0, "years_pos": 7, "net_ex2020": 500.0, "net_ex_best_days": 300.0, "net_ex_best_pos": 200.0}
    se_ok = {"DO": 0.30, "rho_dd": -0.50, "years_pos": 6, "DO_ex_episode": 0.1}
    nul = {"roc_max": {"p95": 30.0}, "do_max": {"p95": 0.2}, "rho_min": {"p5": -0.4}}
    twin = {"roc": 35.0, "sortino": 1.5}
    ok = judge_cell("L1-S", st_ok, 100.0, se_ok, nul, twin)
    assert all(ok.values()) and len(ok) == 16, ok
    assert len(judge_cell("L1-F", st_ok, 100.0, se_ok, nul, None)) == 15 and len(judge_cell("L2-F", st_ok, 100.0, se_ok, nul, None)) == 15
    breaks = [("name-periods>=100", dict(st=dict(n_pos=99))), ("weekly rebalances>=26", dict(st=dict(n_units=25))), ("net>0 at base costs", dict(st=dict(net=0.0))),
              ("net>0 at the first stress costs", dict(stress=0.0)), ("ROC>null p95", dict(st=dict(roc=30.0), twin=dict(roc=20.0))), ("DO>null p95", dict(se=dict(DO=0.2))), ("rho_dd<null p5", dict(se=dict(rho_dd=-0.4))),
              ("DO>0", dict(se=dict(DO=-0.01), nul=dict(do_max={"p95": -0.5}))), ("rho_dd<0", dict(se=dict(rho_dd=0.01), nul=dict(rho_min={"p5": 0.5}))), ("DO>0 in >=4 of 7 years", dict(se=dict(years_pos=3))),
              ("DO>0 without the 2020-03 episode", dict(se=dict(DO_ex_episode=0.0))), ("positive in >=6 of 9 July-June years", dict(st=dict(years_pos=5))),
              ("net>0 without Feb 15 - Apr 30 2020", dict(st=dict(net_ex2020=0.0))), ("profitable without its best 1% of days", dict(st=dict(net_ex_best_days=-1.0))),
              ("profitable without its best 1% of name-periods", dict(st=dict(net_ex_best_pos=-1.0))), ("S beats its F twin on ROC and Sortino", dict(twin=dict(roc=40.0))),
              ("S beats its F twin on ROC and Sortino", dict(twin=dict(sortino=2.0)))]
    for name, kw in breaks:
        r_ = judge_cell("L1-S", {**st_ok, **kw.get("st", {})}, kw.get("stress", 100.0), {**se_ok, **kw.get("se", {})}, {**nul, **kw.get("nul", {})}, {**twin, **kw.get("twin", {})})
        assert [k for k, v in r_.items() if not v] == [name], (name, [k for k, v in r_.items() if not v])
    assert not judge_cell("L2-F", {**st_ok, "n_units": 59}, 1.0, se_ok, nul, None)["traded sessions>=60"] and judge_cell("L2-F", {**st_ok, "n_units": 60}, 1.0, se_ok, nul, None)["traded sessions>=60"]
    nanst = judge_cell("L1-F", {**st_ok, "roc": float("nan")}, 1.0, {**se_ok, "rho_dd": float("nan")}, nul, None)
    assert not nanst["ROC>null p95"] and not nanst["rho_dd<null p5"] and not nanst["rho_dd<0"], "a NaN never passes"
    # A2 has its own test (t_a2): c is set by volatility now, so there is nothing left to tie-break here
    base = R11.stats(book[S12.rows], S12.dates)
    big = a2_cell(B, np.where(in_dd, 2000.0, 0.0) + rng.normal(0.0, 30.0, len(ix)))        # a leg that earns on every one of the book's DD days (plus a little noise, so it has a spread in the A2 window)
    assert math.isfinite(big["c"]) and big["c"] > 0 and big["roc"] > base["roc"] and big["pass"] is True, "a leg that earns while #463 falls lifts the book past the A2 bar"


def t_es():
    """the ES prints, k_t, the ES gap / return formulas, the TBIS file, the audit file"""
    def mk(spec_):
        ts, o, c = [], [], []
        for day, hms in spec_.items():
            for hm in hms:
                ts.append(TS(day) + pd.Timedelta(minutes=hm))
                o.append(1000.0 + hm)
                c.append(1001.0 + hm)
        return pd.DataFrame({"open": o, "close": c}, index=pd.DatetimeIndex(ts).tz_localize("US/Eastern"))
    full, half = list(range(570, 960, 5)), list(range(570, 780, 5)) + [840]
    pt = es_prints(mk({"2024-03-04": full, "2024-11-29": half, "2024-03-05": [m for m in full if m != 955], "2024-03-06": [m for m in full if m != 570], "2024-03-07": list(range(600, 905, 5))}))
    assert pt.loc["2024-03-04", "open"] == 1571.0 and pt.loc["2024-03-04", "close"] == 1956.0, "09:35 price = the CLOSE of the 09:30 bar; the 16:00 print = the close of the 15:55 bar"
    assert pt.loc["2024-11-29", "close"] == 1776.0 and pt.loc["2024-11-29", "open"] == 1571.0, "half day: the 12:55 bar, not the 14:00 print"
    assert pt.loc["2024-03-05", "close"] == 1951.0 and pt.loc["2024-03-06", "open"] == 1576.0 and pt.loc["2024-03-06", "open_hm"] == 575 and TS("2024-03-07") not in pt.index, "NQ's fallbacks, for ES"
    # series: a roll between sessions 1 and 2 (the raw print jumps 30 points, the roll-corrected one does not)
    days = pd.DatetimeIndex(["2024-03-04", "2024-03-05", "2024-03-06"])
    pa = pd.DataFrame({"open": [5010.0, 5025.0, 5040.0], "close": [5000.0, 5020.0, 5030.0]}, index=days)          # roll-corrected: 09:35 price ('open'), 16:00 print ('close')
    pr = pd.DataFrame({"open": [4510.0, 4525.0, 4570.0], "close": [4500.0, 4520.0, 4560.0]}, index=days)           # raw: the same, +30 from the roll on the 6th
    es = es_series(days, pa, pr)
    assert np.isnan(es.ret[0]) and abs(es.ret[1] - (5020.0 - 5000.0) / 4500.0) < 1e-15 and abs(es.ret[2] - (5030.0 - 5020.0) / 4520.0) < 1e-15, "return = roll-corrected change / the prior UNADJUSTED print"
    assert abs(es.gap[1] - (5025.0 - 5000.0) / 4500.0) < 1e-15 and abs(es.gap[2] - (5040.0 - 5020.0) / 4520.0) < 1e-15, "gap = (09:35 - the prior 16:00, roll-corrected) / the prior unadjusted 16:00"
    # k_t on a constructed history: 300 quiet sessions (returns +-1%), then 300 volatile (+-4%), then 200 quiet again
    n = 800
    sd = np.r_[np.full(300, 0.01), np.full(300, 0.04), np.full(200, 0.01)]
    ret = sd * np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    ret[0] = np.nan
    px = 4000.0 * np.nancumprod(1.0 + np.nan_to_num(ret))
    ed = pd.bdate_range("2020-01-01", periods=n)
    fr = pd.DataFrame({"open": px, "close": px}, index=ed)
    # the prints are the same series raw and roll-corrected here, so ES's own return is (px_t - px_(t-1)) / px_(t-1)
    k = es_k(fr, fr, ed)
    rets = np.r_[np.nan, px[1:] / px[:-1] - 1.0]
    rv = pd.Series(np.r_[rets, np.nan]).shift(1).rolling(20, min_periods=18).std(ddof=1).to_numpy()
    med = pd.Series(rv).shift(1).rolling(252, min_periods=200).median().to_numpy()
    want = np.clip(rv / med, 0.5, 2.0)[:n]
    assert close(k, want) and np.isnan(k[:219]).all() and np.isfinite(k[219:]).all(), "k is first defined at the 220th session (>= 18 returns, then >= 200 RV20 values)"
    # quiet against a quiet median: 1; the first volatile weeks against a quiet median: clipped at 2; deep into the volatile regime the median has caught up: back to ~1; quiet again against a volatile median: clipped at 0.5
    assert abs(k[250] - 1.0) < 1e-9 and k[330] == 2.0 and abs(k[450] - 1.0) < 1e-9 and k[640] == 0.5, (k[250], k[330], k[450], k[640])
    assert np.nanmax(k) == 2.0 and np.nanmin(k) == 0.5, "clipped to [0.5, 2.0]"
    # the same history read on a different stock calendar: a stock session ES lacks gets the value its place implies; a session after the last ES session gets the virtual one; every input is before t
    sess = pd.DatetimeIndex([ed[300], ed[300] + pd.Timedelta(hours=12), ed[-1] + pd.Timedelta(days=3)])
    kk = es_k(fr, fr, sess)
    assert abs(kk[0] - k[300]) < 1e-15 and abs(kk[1] - k[301]) < 1e-15 and np.isfinite(kk[2]), "by position in the ES calendar"
    fr2 = fr.copy()
    fr2.iloc[250:, :] = fr2.iloc[250:, :] * 1.37                                                # a 37% jump on session 250 (a quiet stretch): k_t up to session 250 cannot know, the 20 sessions after it do
    k2 = es_k(fr2, fr2, ed)
    assert close(k2[:251], k[:251]) and (k2[251:271] == 2.0).all() and close(k[251:271], 1.0), "k_t at t uses only sessions before t"
    kb = es_k(fr, fr, ed)
    fr3 = fr.copy()
    fr3.iloc[500:, :] = 1.0
    assert close(es_k(fr3, fr3, ed)[:501], kb[:501]), "k_t at t uses only sessions before t: changing the future changes nothing"


def t_files():
    """the TBIS file (cut at read time, missing = refusal), the audit file (read, applied, status), the audit candidates' bookkeeping"""
    import shutil, tempfile
    root = tempfile.mkdtemp(prefix="ddw_selftest_")
    me = sys.modules[__name__]
    try:
        tb = os.path.join(root, "tbis.csv")
        open(tb, "w").write("symbol,day,price_ratio,vol_ratio,split_like\nAAA,2024-03-04,0.5,2.1,True\nNA,2024-03-05,2.0,0.4,False\nBBB,2025-06-27,0.25,3.9,True\nBBB,2025-06-30,0.25,4.0,True\nCCC,2025-07-01,3.0,,False\n")
        with patched(me, TBIS_CSV=tb):
            df = load_tbis(S.LB0)
            assert df["symbol"].tolist() == ["AAA", "NA", "BBB"] and df["day"].max() == TS("2025-06-27"), "cut at read time; the ticker 'NA' is not a missing value"
            assert len(load_tbis(S.END)) == 5 and df["day"].max() < S.LB0
        with patched(me, TBIS_CSV=os.path.join(root, "missing.csv")):
            try:
                load_tbis(S.LB0)
                raise AssertionError("a missing TBIS file must refuse")
            except SystemExit as e:
                assert "TBIS" in str(e)
        open(tb, "w").write("symbol,day\nAAA,2024-03-04\n")
        with patched(me, TBIS_CSV=tb):
            try:
                load_tbis(S.LB0)
                raise AssertionError("a TBIS file without its columns must refuse")
            except SystemExit as e:
                assert "lacks the column" in str(e)
        days = pd.DatetimeIndex(["2024-03-04", "2024-03-05", "2024-03-06"])
        arr, nm = tbis_array(days, np.array(["AAA", "BBB", "NA"]), pd.DataFrame({"symbol": ["AAA", "NA", "ZZZ", "AAA"], "day": pd.to_datetime(["2024-03-04", "2024-03-05", "2024-03-05", "2024-03-09"])}))
        assert nm == 2 and arr[0, 0] and arr[1, 2] and arr.sum() == 2, "only a listed symbol-day that exists in this data"
        # the audit file
        W = toy_world()
        ap = os.path.join(root, "ddw_audit.csv")
        assert read_audit(ap) is None
        open(ap, "w").write(f"symbol,date,cell,verdict,note\nN11,{W.days[85]:%Y-%m-%d},L1-F,data_event,split\nN01,{W.days[90]:%Y-%m-%d},l1-s,KEEP,fine\nN12,{W.days[120]:%Y-%m-%d},L2-S,data_event,bad print\n")
        au = read_audit(ap)
        assert au["leg"].tolist() == ["L1", "L1", "L2"] and au["verdict"].tolist() == ["data_event", "keep", "data_event"] and au["cell"].tolist() == ["L1-F", "L1-S", "L2-S"]
        cnt = apply_audit(W, au)
        assert cnt == {"rows": 3, "keep": 1, "data_event": 2} and W.aud1[85, 11] and W.aud2[120, 12] and W.aud1.sum() == 1 and W.aud2.sum() == 1, "a data_event row removes the name-period (L1: by fill session)"
        assert apply_audit(W, None)["rows"] == 0 and not W.aud1.any() and not W.aud2.any()
        for bad in (f"N11,{W.days[85]:%Y-%m-%d},L1-F,maybe,x\n", f"N11,not-a-date,L1-F,keep,x\n", f"N11,{W.days[85]:%Y-%m-%d},L3-F,keep,x\n", f",{W.days[85]:%Y-%m-%d},L1-F,keep,x\n"):
            open(ap, "w").write("symbol,date,cell,verdict,note\n" + bad)
            try:
                read_audit(ap)
                raise AssertionError("an unreadable audit row must refuse")
            except SystemExit as e:
                assert "line(s) [2]" in str(e)
        open(ap, "w").write("symbol,date\nN11,2024-01-01\n")
        try:
            read_audit(ap)
            raise AssertionError("an audit file without its columns must refuse")
        except SystemExit as e:
            assert "lacks the column" in str(e)
        for sym, d in (("ZZZ", W.days[85]), ("N11", pd.Timestamp("2024-01-06"))):                  # a data_event row that matches no name / no session must not silently do nothing
            open(ap, "w").write(f"symbol,date,cell,verdict,note\n{sym},{d:%Y-%m-%d},L1-F,data_event,x\n")
            try:
                apply_audit(W, read_audit(ap))
                raise AssertionError("a data_event row that matches nothing must refuse")
            except SystemExit as e:
                assert "match no session or no name" in str(e)
        open(ap, "w").write(f"symbol,date,cell,verdict,note\nN11,{W.days[85]:%Y-%m-%d},L1-F,data_event,x\nN05,{W.days[85]:%Y-%m-%d},L1-F,data_event,never in that day's universe? it is\n")
        au = read_audit(ap)
        apply_audit(W, au)
        assert unused_audit_rows(W, au) == [f"N11 {W.days[85]:%Y-%m-%d} L1-F", f"N05 {W.days[85]:%Y-%m-%d} L1-F"], "no build has run yet: both rows are unused until a build hits them"
        # audit_status: by symbol + date + LEG (a row for L1-F also covers L1-S's listing)
        cands = {"L1-F": [{"symbol": "N11", "date": f"{W.days[85]:%Y-%m-%d}"}], "L1-S": [{"symbol": "N11", "date": f"{W.days[85]:%Y-%m-%d}"}, {"symbol": "N01", "date": "2024-01-01"}], "L2-F": [{"symbol": "N11", "date": f"{W.days[85]:%Y-%m-%d}"}],
                 "L2-S": []}
        st = audit_status(cands, au)
        assert st["L1-F"] == {"listed": 1, "audited": 1, "audit_complete": True} and st["L1-S"] == {"listed": 2, "audited": 1, "audit_complete": False} and st["L2-F"]["audited"] == 0 and st["L2-S"]["audit_complete"] is False
        assert audit_status(cands, None)["L1-F"]["audit_complete"] is False
        st_ = os.path.join(root, "assets.csv")
        open(st_, "w").write("symbol,name,exchange,status,tradable,shortable,easy_to_borrow\nAAA,a,NYSE,active,True,True,True\nNA,b,NYSE,inactive,False,True,True\n")
        assert asset_status(st_) == {"AAA": "active", "NA": "inactive"} and asset_status(os.path.join(root, "none.csv")) == {}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_stage_b_refusals():
    """every Stage B refusal that needs no data, none of which may write the flag: no pass on file (each broken piece), the flag already there, a changed spec / harness / audit, ATTN not judged, SIPORB neither read nor dead"""
    import shutil, tempfile
    root = tempfile.mkdtemp(prefix="ddw_selftest_")
    me = sys.modules[__name__]
    try:
        out, attn, sip = os.path.join(root, "out"), os.path.join(root, "attn"), os.path.join(root, "siporb")
        for p in (out, attn, sip):
            os.makedirs(p)
        flag = os.path.join(out, "ddw_stageB_READ.flag")
        good = {"judged": True, "prereg_sha256_lf": PREREG_SHA, **stamp(), "audit_sha256": None, "candidate": {"cell": "L2-F", "c": 0.8317},
                "stageA": {"cells": {"L2-F": {"PASS": True, "A2": {"pass": True}, "audit": {"audit_complete": True}}}}, "parity": {}}

        def must(frag, sa=None, **kw):
            json.dump(good if sa is None else sa, open(os.path.join(out, "ddw_stageA.json"), "w"))
            try:
                with contextlib.redirect_stdout(io.StringIO()), patched(me, OUT=out, **kw):
                    stage_b()
                raise AssertionError(f"Stage B must refuse ({frag})")
            except SystemExit as e:
                assert frag in str(e), (frag, str(e))
                assert not os.path.exists(flag) or frag == "already read", "a refused Stage B must not burn the lockbox"
        with patched(A13, OUT=attn), patched(S, OUT=sip):
            ap = os.path.join(out, "ddw_stageA.json")
            try:                                                                                    # nothing on file at all
                with patched(me, OUT=out):
                    stage_b()
                raise AssertionError("no file")
            except SystemExit as e:
                assert "no Stage A + A2 pass" in str(e)
            mut = lambda f: (lambda d: (f(d), d)[1])(json.loads(json.dumps(good)))
            for nm, sa in (("not judged", mut(lambda d: d.update(judged=False))), ("no candidate", mut(lambda d: d.update(candidate=None))), ("unknown cell", mut(lambda d: d.update(candidate={"cell": "L9-F", "c": 1}))),
                           ("Stage A fail", mut(lambda d: d["stageA"]["cells"]["L2-F"].update(PASS=False))), ("A2 fail", mut(lambda d: d["stageA"]["cells"]["L2-F"]["A2"].update(**{"pass": False}))),
                           ("audit incomplete", mut(lambda d: d["stageA"]["cells"]["L2-F"]["audit"].update(audit_complete=False))), ("a pending audit", mut(lambda d: d.update(judged=None)))):
                must("no Stage A + A2 pass", sa)
            open(flag, "w").write("x")
            must("already read", good)
            os.remove(flag)
            with patched(me, PREREG_SHA="0" * 64):
                must("DIFFERS", good)
            must("another pre-registration", mut(lambda d: d.update(prereg_sha256_lf="0" * 64)))
            for nm, edit in (("harness", lambda d: d.update(harness_sha256="0" * 64)), ("early close", lambda d: d.update(early_close=d["early_close"][1:])), ("r12", lambda d: d.update(r12_sha256="0" * 64)),
                             ("r13", lambda d: d.pop("r13_sha256")), ("no stamp", lambda d: [d.pop(k) for k in stamp()])):
                must("different harness version", mut(edit))
            must("not the file Stage A ran with", mut(lambda d: d.update(audit_sha256="0" * 64)))
            ok_audit = open(os.path.join(out, "ddw_audit.csv"), "w")
            ok_audit.write("symbol,date,cell,verdict,note\n")
            ok_audit.close()
            sha = file_sha(os.path.join(out, "ddw_audit.csv"))
            with_audit = mut(lambda d: d.update(audit_sha256=sha))
            for badc in (0.0, -1.0, None, "abc", float("nan"), float("inf")):                  # c is a volatility ratio now: any positive number is a frozen size; NaN / 0 / negative / missing / text is a broken file
                must("positive number", mut(lambda d, b=badc: d.update(audit_sha256=sha, candidate={"cell": "L2-F", "c": b})))
            must("not one of", mut(lambda d: d.update(audit_sha256=sha, candidate={"cell": "L1-X", "c": 0.8317}, stageA={"cells": {"L1-X": {"PASS": True, "A2": {"pass": True}, "audit": {"audit_complete": True}}}})))
            must("ATTN's Stage A is not on file and judged", with_audit)                              # a size off any grid (0.8317) is a good size: the next refusal is ATTN's
            assert sibling_note("L1-F", 120.0).startswith("SIBLING RULE: not engaged") and "NOT checked here" in sibling_note("L2-S", 123.456) and "123.46" in sibling_note("L2-S", 123.456)
            must("ATTN's Stage A is not on file and judged", with_audit)                              # no attn file
            json.dump({"judged": False}, open(os.path.join(attn, "attn_stageA.json"), "w"))
            must("ATTN's Stage A is not on file and judged", with_audit)                              # not judged
            json.dump({"judged": True}, open(os.path.join(attn, "attn_stageA.json"), "w"))
            must("SIPORB's lockbox has not been read", with_audit)                                    # SIPORB neither read nor dead
            json.dump({"judged": True, "stageA": {"PASS": True}, "A2": {"pass": True}}, open(os.path.join(sip, "siporb_stageA.json"), "w"))
            must("SIPORB's lockbox has not been read", with_audit)                                    # SIPORB passed but has not read: not a verdict
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cut():
    """Stage A asks for data cut at 2025-06-30 and refuses a session on/after it (the loaders and the book are stubbed; nothing real is read); the manifest and the book gates"""
    seen = {}

    def stub(t_end, open5=True):
        assert t_end == S.LB0, "Stage A must ask for data cut at 2025-06-30"
        seen["t"] = t_end
        return SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27", "2025-06-30"]))
    me = sys.modules[__name__]
    S12 = SimpleNamespace(qual=[])
    okbk = ({"roc": 0.0, "sortino": 0.0, "ref": [0, 0], "ok": True}, {"deepest": 0.0, "episodes": 0, "days": 0, "weeks": 0, "by_year": {}, "episode_2020": True, "ok": True}, S12)
    with patched(S, Data=stub), patched(A13, load_463=lambda: (SimpleNamespace(), [])), patched(me, book_checks=lambda B: okbk, manifest_sha=lambda: MANIFEST_PREFIX + "0" * 56):
        try:
            with contextlib.redirect_stdout(open(os.devnull, "w")):
                stage_a()
            raise AssertionError("Stage A must refuse a session on/after the cut")
        except SystemExit as e:
            assert "on/after the cut" in str(e) and seen["t"] == S.LB0, (str(e), seen)
        for mf, frag in ((lambda: None, "manifest is missing"), (lambda: "ffff" + "0" * 60, "not the registered photograph")):
            with patched(me, manifest_sha=mf):
                try:
                    with contextlib.redirect_stdout(open(os.devnull, "w")):
                        stage_a()
                    raise AssertionError("Stage A must refuse the wrong manifest")
                except SystemExit as e:
                    assert frag in str(e)
        with patched(me, book_checks=lambda B: ({"roc": 1.0, "sortino": 1.0, "ref": [0, 0], "ok": False}, okbk[1], S12)):
            try:
                with contextlib.redirect_stdout(open(os.devnull, "w")):
                    stage_a()
                raise AssertionError("a book that does not reproduce must refuse")
            except SystemExit as e:
                assert "do not reproduce" in str(e)
        with patched(me, book_checks=lambda B: (okbk[0], {**okbk[1], "ok": False}, S12)):
            try:
                with contextlib.redirect_stdout(open(os.devnull, "w")):
                    stage_a()
                raise AssertionError("a DD structure that does not match the prereg must refuse")
            except SystemExit as e:
                assert "do not reproduce" in str(e)
        import tempfile
        root = tempfile.mkdtemp(prefix="ddw_selftest_")
        try:
            open(os.path.join(root, "ddw_stageB_READ.flag"), "w").write("x")
            with patched(me, OUT=root):
                try:
                    stage_a()
                    raise AssertionError("Stage A is frozen once the lockbox has been read")
                except SystemExit as e:
                    assert "Stage A is frozen" in str(e)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
    # book_checks on a synthetic book that does not match the registered structure: ok False, with the numbers
    ix = pd.bdate_range("2016-07-01", "2025-06-27")
    rng = np.random.default_rng(2)
    Bf = SimpleNamespace(index=ix, raw=rng.normal(30.0, 600.0, len(ix)), n=len(ix), mask=lambda lo, hi: np.asarray((ix >= lo) & (ix <= hi)))
    bk, dd, S12b = book_checks(Bf)
    assert bk["ok"] is False and dd["ok"] is False and dd["days"] == S12b.n_dd_days and dd["episodes"] == len(S12b.qual) and set(dd["by_year"]) <= set(DD_YEARS) | set(range(2016, 2019))


def selftest():
    """rules on hand-made worlds: the constants as registered, the universe (filters, timing, ties), marks / costs / borrow / stress on hand numbers, the vectorised builds against a plain-python recount in every reading
    with each planted case, the null (uniform, seeded, disjoint, same draw), DO / rho_dd against MDL r1's, the year and ex-episode tests, the checks one by one, the ES prints and k_t, the TBIS and audit files,
    the Stage B refusals, the cut"""
    t_constants()
    t_universe()
    t_marks_and_costs()
    n = t_pipeline()
    t_null()
    t_stats()
    ratio = t_a2()
    t_stage_b_checks()
    t_beta_holes()
    t_es()
    t_files()
    t_stage_b_refusals()
    t_cut()
    print(f"A2 proof: c x the cell's daily std over 2016-07-01 .. 2018-06-29 = {ratio:.12f} of #463's (the registered 25%), the same c whatever the cell's sign, mean or outside-window days; c = 25% x std(#463) / std(cell), set by volatility, never picked")
    print(f"selftest ok: constants as registered, universe timing / filters / ties, split-safe marks and costs on hand numbers, {n:,} pool-name paths and every pool / pick / cross-check count equal a plain-python recount "
          "in the registered, look-ahead and news-only readings (planted splits, flags, news, stops, carries, large moves, audit), the null (uniform, seeded, disjoint, same draw F / S), DO / rho_dd = MDL r1's, "
          "year / ex-episode DO, cell statistics, every check broken alone, A2's volatility-set c (identity, invariances, window ends, 0.5c / 2c books, the bar, no-c cells), ES prints / k_t / gap, TBIS + audit files, "
          "Stage B's leg-only pass (each check alone, L1 26 / L2 30, inclusive, NaN), L2's beta with holes in the ES masters (registered all-present rule, the opt-in tolerance, es_blind), Stage B refusals (a size off any grid is a good size), the cut")


# ------------------------------------------------------------------ smoke: an offline end-to-end run on a SYNTHETIC world (every number means nothing)
class ESFake(A13.NQFake):
    """synthetic ES 5-minute RTH masters on the synthetic sessions: r13_attn's fake futures master (a continuous path, raw = path + the rolls' gaps so far, roll-corrected = path + 5000, a half day, a session with no
    15:55 bar, one with no 09:30 bar, one with no bar at all; leaky = load_master_arrays ignores date_to, so only load_es's own cut stands between Stage A and the later bars) answering to ES's registry calls"""
    def install(self):
        data, w = A13.data_mod(), self

        def find(instrument, timeframe, session=None, source=None):
            assert (instrument, timeframe, session) == ("ES", "5m", "rth") and source in (A13.SRC_RAW, A13.SRC_ADJ), (instrument, timeframe, session, source)
            return {"id": 33 if source == A13.SRC_RAW else 63, "instrument": instrument, "timeframe": timeframe, "session": session, "source": source, "filename": "SMOKE"}

        def arrays(master, date_from=None, date_to=None):
            idx, o, c = w.tab["raw" if master["source"] == A13.SRC_RAW else "adj"]
            keep = np.ones(len(idx), bool)
            if date_from:
                keep &= np.asarray(idx >= TS(date_from, tz="US/Eastern"))
            if date_to and not w.leaky:
                keep &= np.asarray(idx < TS(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
            return {"index": idx[keep], "open": o[keep], "close": c[keep], "meta": master}
        data.find_master, data.load_master_arrays = find, arrays


def smoke_refusal(root):
    """A13.smoke_refusal's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, ATTN's OUT, the #463 records) + this harness's OUT"""
    why = A13.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds DDW OUT"
    except ValueError:
        pass
    return None


def rec_of(L, row):
    """the L1 rebalance whose hold (fill .. exit) contains session `row`"""
    return next(r for r in L.recs if r.f <= row <= r.x)


def smoke(*a):
    import re, shutil, tempfile
    global OUT, CHECK_BOOK, TBIS_CSV, NREP
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "ddw_smoke"))
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    me, data = sys.modules[__name__], A13.data_mod()
    keep = dict(OUT=OUT, CHECK_BOOK=CHECK_BOOK, TBIS_CSV=TBIS_CSV, NREP=NREP, RULES=dict(RULES), SPEC=dict(SPEC), R11_OUT=R11.OUT, A13_OUT=A13.OUT, S=(S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY,
                S._http_get), es=(data.find_master, data.load_master_arrays))
    t_start = time.time()
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    OUT, R11.OUT, A13.OUT = os.path.join(root, "out"), os.path.join(root, "r11"), os.path.join(root, "attn_out")
    S.OUT, S.CACHE, S.BOOK = os.path.join(root, "siporb_out"), os.path.join(root, "cache"), os.path.join(root, "r4", "book463_daily.csv")
    for p in (OUT, R11.OUT, A13.OUT, S.OUT):
        os.makedirs(p)
    TBIS_CSV = os.path.join(root, "tbis.csv")
    S.SMOKE, S.PACE, S.BACKOFF, S.RETRY = True, 0.0, 0.0, 0.0
    CHECK_BOOK = False                                                                     # off in smoke only: its synthetic book / manifest / ES history cannot reproduce the real registered facts
    NREP = 100                                                                             # CHOICE: the smoke draws 100, not 500, for speed (the real constant is asserted by selftest)
    inside = lambda p: os.path.commonpath([os.path.realpath(p), os.path.realpath(root)]) == os.path.realpath(root)
    assert all(inside(p) for p in (OUT, R11.OUT, A13.OUT, S.OUT, S.CACHE, TBIS_CSV)), "every path the smoke writes is inside the smoke dir"
    quiet = lambda: contextlib.redirect_stdout(io.StringIO())
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    SM = dict(univ=30, l1_n=5, l2_n=4, gap_min=0.0)                                        # the synthetic market has ~35 names: the real sides (25 / 20 of 500) cannot exist in it
    try:
        SPEC.update(SM)
        spans = (("2015-11-02", "2015-12-31"), ("2016-01-04", "2016-03-31"), ("2016-06-13", "2016-07-15"), ("2023-10-02", "2023-12-29"), ("2024-01-02", "2024-06-28"),
                 ("2025-04-01", "2025-06-27"), ("2025-06-30", "2025-08-29"))              # warm-up, 2016 H1, around the WF start, WF pieces, lockbox days: the cut has something to cut
        days = pd.DatetimeIndex(sorted(set().union(*[pd.bdate_range(x, y) for x, y in spans])))
        t0 = time.time()
        fk = S.Fake(days)
        S._http_get = fk.handle
        print(f"synthetic market: {len(fk.names)} names x {len(days)} sessions built in {time.time() - t0:.0f}s")
        t0 = time.time()
        with quiet():
            S.assets(); S.daily(); S.open5()                                                # r5_siporb's own pulls through its fake transport: the synthetic daily + 09:30 caches
        print(f"synthetic SIPORB cache pulled through r5_siporb ({fk.n:,} requests, {time.time() - t0:.0f}s)")
        es_cal = days.union(pd.bdate_range("2015-05-01", "2015-10-30"))                       # CHOICE: ES history (the real masters start in 2010) reaches back before the synthetic stock sessions, so k_t is defined from March 2016 and
        esf = ESFake(es_cal)                                                                 # the S cells hold positions in the A2 window (2016-07-01 ..): c needs a cell with a spread there
        esf.install()
        A13.smoke_book()
        json.dump({"manifest_sha256": MANIFEST_PREFIX + "0" * 56, "files": 0}, open(os.path.join(S.OUT, "siporb_cache_manifest.json"), "w"))
        open(TBIS_CSV, "w").write("symbol,day,price_ratio,vol_ratio,split_like\nS18,2024-04-22,4.0,0.25,True\nSPL,2024-03-15,0.5,2.1,True\nS05,2024-02-13,0.5,1.0,False\nZZZZ,2024-02-14,0.5,2.0,True\n"
                                  "S07,2025-07-01,0.5,2.0,True\n")
        # ---- the planted cases, through the real loaders and the real arrays
        with quiet():
            D = A13.load_data(S.LB0)
        cov0, cy0 = A13.coverage(D, WF0, PRE_END), S.coverage_by_year(D)
        assert cov0["share"] == 1.0 and all(v["share"] == 1.0 for v in cy0.values()), "every synthetic session has its 09:30 file"
        es_frames, es_meta = load_es(S.LB0)
        cut = TS(S.LB0).tz_localize("US/Eastern")
        assert es_frames["raw"].index.max() < cut and es_frames["adj"].index.max() < cut and esf.tab["raw"][0].max() >= cut, "the ES loader hands back bars past the cut (leaky) and load_es's own cut removes them"
        tbis = load_tbis(S.LB0)
        assert tbis["day"].max() < S.LB0 and len(tbis) == 4 and len(load_tbis(S.END)) == 5, "the TBIS flag on the lockbox day is cut at read time"
        with quiet():
            W = build_world(D, S.LB0, es_frames, tbis)
        raw_l, spl_l = S.read_long("raw", S.LB0), S.read_long("split", S.LB0)
        release(D)
        ix, T = list(W.syms), W.T
        di = lambda s: W.days.get_loc(TS(s))
        # the arrays equal the long daily frames (an independent look-up, 300 name-days)
        rl, sl = raw_l.assign(symbol=raw_l["symbol"].astype(str)).set_index(["symbol", "date"]), spl_l.assign(symbol=spl_l["symbol"].astype(str)).set_index(["symbol", "date"])
        pick = np.random.default_rng(3).choice(len(rl), 300, replace=False)
        n_chk = 0
        for q in pick:
            (sym, d), r_ = rl.index[q], rl.iloc[q]
            if sym in ix and d in W.days:
                c_, t_ = ix.index(sym), W.days.get_loc(d)
                assert W.Cl[t_, c_] == r_["c"] and W.Od[t_, c_] == r_["o"] and W.Vv[t_, c_] == r_["v"] and abs(W.F[t_, c_] - r_["o"] / sl.loc[(sym, d), "o"]) < 1e-12, (sym, d)
                n_chk += 1
        assert n_chk > 100 and W.days.max() < S.LB0 and W.es.k.shape == (T,)
        spl_k = ix.index("SPL")
        assert W.chg[di("2024-03-15"), spl_k] and abs(W.F[di("2024-03-14"), spl_k] - 2.0) < 1e-3 and abs(W.F[di("2024-03-15"), spl_k] - 1.0) < 1e-3, "the registered split: F 2 -> 1 (Alpaca's convention)"
        assert W.fl[1][di("2024-04-22"), ix.index("S18")] and not W.chg[:, ix.index("S18")].any(), "S18's x4 was never adjusted: only the gap scan sees it"
        assert W.fl[3][di("2024-05-14"), ix.index("S23")] and not W.fl[1][di("2024-05-14"), ix.index("S23")], "S23's genuine +60% gap: the +-50% rule, not a whole ratio"
        assert W.tbis[di("2024-04-22"), ix.index("S18")] and W.tbis[di("2024-03-15"), spl_k] and W.tbis.sum() == 3 and W.tbis_rows == (4, 3), "TBIS: listed rows that exist in this data (ZZZZ is not a cached name)"
        # the ES prints on the stock sessions: the half day, the fallbacks, the 09:35 price = the close of the 09:30 bar, the roll night, the missing session
        pa, pr = W.es_cov["adj_prints"], W.es_cov["raw_prints"]
        idx_a, o_a, c_a = esf.tab["adj"]
        b930 = lambda d_: float(c_a[np.asarray((idx_a.tz_localize(None).normalize() == TS(d_)) & (idx_a.hour * 60 + idx_a.minute == 570))][0]) - 5000.0
        assert np.isclose(pa.loc["2023-11-24", "close"] - 5000.0, esf.p_close[TS("2023-11-24")]) and pa.loc["2023-11-24", "close_hm"] == pa.loc["2023-11-24", "last"] == 775, "the half day's 12:55 bar"
        assert pa.loc["2024-01-17", "close_hm"] != pa.loc["2024-01-17", "last"] and pa.loc["2024-02-08", "open_hm"] != 570 and TS("2024-03-05") not in pa.index, "the planted missing bars use the fallback rules / leave no print"
        assert np.isclose(pa.loc["2024-02-14", "open"] - 5000.0, b930("2024-02-14")), "the 09:35 price is the CLOSE of the bar that starts 09:30 (not its open)"
        i = di("2023-12-15")
        assert np.isclose((pr.loc["2023-12-15", "open"] - pr.loc["2023-12-14", "close"]) - (pa.loc["2023-12-15", "open"] - pa.loc["2023-12-14", "close"]), 30.0), "the raw gap carries the 30-point roll, the roll-corrected one does not"
        assert np.isclose(W.es.gap[i], (pa.loc["2023-12-15", "open"] - pa.loc["2023-12-14", "close"]) / pr.loc["2023-12-14", "close"]) and abs(W.es.gap[i]) < 0.02, "the market's gap: roll-corrected change over the unadjusted level"
        assert np.isclose(W.es.ret[i], (pa.loc["2023-12-15", "close"] - pa.loc["2023-12-14", "close"]) / pr.loc["2023-12-14", "close"])
        assert np.isnan(W.es.gap[di("2024-03-05")]) and np.isnan(W.es.gap[di("2024-03-06")]) and np.isnan(W.es.ret[di("2024-03-05")]), "no ES bar on 2024-03-05: that session's gap and the next one's are undefined"
        fin = np.flatnonzero(np.isfinite(W.k))
        es_days = pa.index.intersection(pr.index)
        assert len(fin) and W.days[fin[0]] == es_days[219], "k_t is first defined at the 220th ES session"
        assert (W.k[np.isfinite(W.k)] >= 0.5).all() and (W.k[np.isfinite(W.k)] <= 2.0).all()
        # L1 / L2 against the plain-python recount on the REAL arrays, in both readings, then the planted names
        lo, hi = W.days[0], W.days[-1]
        Lr1, Lr2, Lk1 = l1_build(W, WF0, PRE_END), l2_build(W, WF0, PRE_END), l1_build(W, WF0, PRE_END, "naive")
        n_paths = compare_l1(W, Lr1, brute_l1(W, WF0, PRE_END), "smoke L1") + compare_l1(W, Lk1, brute_l1(W, WF0, PRE_END, "naive"), "smoke L1 K")
        n_paths += compare_l2(W, Lr2, brute_l2(W, WF0, PRE_END), "smoke L2") + compare_l2(W, l2_build(W, WF0, PRE_END, "naive"), brute_l2(W, WF0, PRE_END, "naive"), "smoke L2 K")
        series_check(W, Lr1, Lr2, brute_l1(W, WF0, PRE_END), brute_l2(W, WF0, PRE_END))
        ntr1, ntr2 = sum(r.traded for r in Lr1.recs), sum(r.traded for r in Lr2.recs)
        assert ntr1 > 20 and ntr2 > 100, (ntr1, ntr2)
        ca = lambda L, k: sum(c.get(k, 0) for c in L.cnt.values())
        assert ca(Lr2, "no_es") >= 2, "the sessions with no ES print are counted, not traded"
        # SPL's split inside the hold of the week ranked 2024-03-08, S18's x4 on the fill session of the week ranked 04-19, S23's +60% inside the hold of the week ranked 05-10
        by_rank = lambda L, d_: next(r for r in L.recs if W.days[r.r] == TS(d_))
        for nm, rank_day in (("SPL", "2024-03-08"), ("S18", "2024-04-19"), ("S23", "2024-05-10")):
            c_, rr_, kk_ = ix.index(nm), by_rank(Lr1, rank_day), by_rank(Lk1, rank_day)
            assert c_ not in rr_.pool.tolist(), (nm, "removed in the registered reading")
            if c_ in kk_.pool.tolist():
                assert kk_.naive[kk_.pool.tolist().index(c_)], (nm, "kept at its naive raw P&L")
        k3 = by_rank(Lk1, "2024-03-08")
        if spl_k in k3.pool.tolist():
            q_ = k3.pool.tolist().index(spl_k)
            safe = unit_path(W.Ao, W.Ac, k3.f, k3.x, np.array([spl_k]))
            assert abs(k3.U.G[q_].sum() - (W.Od[k3.x, spl_k] / W.Od[k3.f, spl_k] - 1.0)) < 1e-12 and k3.U.G[q_].sum() < -0.3 and abs(safe.G[0].sum()) < 0.3, "SPL: the naive raw P&L shows the split as a loss"
        dl = rec_of(Lr1, di("2024-05-29"))
        if ix.index("DLST") in dl.pool.tolist():
            assert dl.U.st[dl.pool.tolist().index(ix.index("DLST"))], "DLST stopped printing inside the week: it exits at its last mark"
        assert ix.index("DLST") not in rec_of(Lr1, di("2024-06-04")).pool.tolist(), "no open at the fill session: not eligible"
        print(f"planted cases ok through the real arrays: split-safe marks, SPL / S18 / S23 / DLST in both readings, the ES prints / fallbacks / roll night / half day / missing session, k_t's start, TBIS and the cut; "
              f"{n_paths:,} pool-name paths and every pool / pick equal a plain-python recount ({ntr1} L1 weeks, {ntr2} L2 sessions traded)")
        # ---- Stage A, end to end
        t0 = time.time()
        sa = os.path.join(OUT, "ddw_stageA.json")
        with patched(me, PREREG_SHA="0" * 64):
            try:
                stage_a()
                raise AssertionError("a changed pre-registration must refuse Stage A")
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
        txt = buf.getvalue()
        print(txt.rstrip())
        assert out["judged"] is True and out["candidate"] is None and out["pending_audit"] == [] and os.path.exists(sa) and all(d < "2025-06-30" for d in dates_of(txt)), "Stage A printed a lockbox date"
        cells = out["stageA"]["cells"]
        assert not any(c["PASS"] for c in cells.values()) and set(cells) == set(CELLS) and out["stageA"]["null"]["draws"] == NREP and out["look_ahead_reading"]["null"]["draws"] == NREP
        bl_, hd_ = es_blind(W)                                                              # the ES holes (no bar at all on 2024-03-05): printed as a WARNING and stored; the registered all-present rule blinds L2's betas for 60 sessions after them
        wf_ = (W.days >= WF0) & (W.days <= PRE_END)
        eh = out["es_holes"]
        assert eh["undefined_es_return_sessions"] == [f"{d:%Y-%m-%d}" for d in hd_] and "2024-03-05" in eh["undefined_es_return_sessions"], eh
        # prereg addendum 1 (55 of 60): the one-day hole leaves 58 returns in every window, so L2 is NOT blind and no WARNING is printed (the strict all-60 rule would blind it - t_beta_holes)
        assert eh["l2_blind_sessions"] == int((bl_ & wf_).sum()) == 0 and "WARNING - ES holes" not in txt and eh["beta_min"] == 55 and eh["sessions"] == int(wf_.sum()), eh
        assert sum(eh["l2_blind_by_year"].values()) == eh["l2_blind_sessions"], eh
        assert eh["stretch"] == ["2016-07-01", "2025-06-29"]
        # dryload on the synthetic world: counts only, no lockbox date, the ES-hole line, and nothing written
        before = sorted(os.listdir(OUT))
        buf_d = io.StringIO()
        with contextlib.redirect_stdout(buf_d):
            dryload()
        td = buf_d.getvalue()
        assert sorted(os.listdir(OUT)) == before and "universe size per session by year" in td and "ES holes (" in td and "WARNING - ES holes" not in td and "k_t: defined from" in td and "L1: rebalances with a pool" in td
        assert all(d < "2025-06-30" for l in td.splitlines() if "cut to dates <" not in l for d in dates_of(l)), "dryload printed a lockbox date"
        assert not re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]", td), "dryload printed an outcome"
        print("dryload ok on the synthetic world: counts only, one ES-hole WARNING line, no lockbox date, nothing written")
        B_, S12_ = A13.load_463()[0], None
        mw, rows_ = B_.mask(*A2_WIN), A13.book_rows(B_, W)
        for cell in CELLS:                                                                  # A2: c is set by VOLATILITY on the real window, through the real arrays - and recounted here from the book file and a fresh run of the cell
            a2 = cells[cell]["A2"]
            run_ = run_cell(W, Lr1 if cell[:2] == "L1" else Lr2, cell, l1_cfg() if cell[:2] == "L1" else (ADV_BPS, COST_BPS))
            sb_, sc_ = float(np.std(B_.raw[mw], ddof=1)), float(np.std(to_B(run_.x, rows_, B_.n)[mw], ddof=1))
            assert a2["window"] == ["2016-07-01", "2018-06-29"] and a2["rows"] == int(mw.sum()) == len(pd.bdate_range("2016-07-01", "2018-06-29")) and a2["target"] == 0.25, (cell, a2)
            assert math.isfinite(a2["c"]) and a2["c"] > 0 and abs(a2["std_book"] - sb_) <= 1e-9 * sb_ and abs(a2["std_cell"] - sc_) <= 1e-9 * sc_ and sc_ > 0, (cell, a2["c"], a2["std_cell"], sc_)
            assert abs(a2["c"] * a2["std_cell"] - 0.25 * a2["std_book"]) <= 1e-12 * a2["std_book"] and abs(a2["c"] - 0.25 * sb_ / sc_) <= 1e-9 * a2["c"], cell
            assert a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"] and "error" not in a2, cell
        cd = pd.read_csv(os.path.join(OUT, "ddw_audit_candidates.csv"))
        assert set(cd["cell"]) == set(CELLS) and cd.groupby("cell").size().max() <= AUDIT_N and cd["date"].max() < "2025-06-30" and cd["exit"].max() < "2025-06-30" and {"symbol", "date", "pnl", "signal",
               "factor_ratio", "tbis_price_ratio", "asset_status", "flags_in_window"} <= set(cd.columns), "the audit candidates: dates before the cut"
        for cell in CELLS:
            assert (cd[cd["cell"] == cell]["pnl"].diff().dropna() <= 1e-9).all(), "largest gains first"
        assert pd.read_csv(os.path.join(OUT, "ddw_L2_exposure_by_day.csv"))["net_usd_F"].abs().max() < 1e-9, "L2 is dollar-neutral by construction"
        try:
            stage_b()
            raise AssertionError("Stage B must refuse after a Stage A fail")
        except SystemExit as e:
            assert "no Stage A + A2 pass" in str(e) and not os.path.exists(os.path.join(OUT, "ddw_stageB_READ.flag"))
        print("--- the coverage gate: half of the 2023-24 sessions lose their 09:30 file -> not judged")
        o5 = sorted(f for f in os.listdir(S.path_of("open5")) if f[:4] in ("2023", "2024"))
        hold = {f: open(S.path_of("open5", f), "rb").read() for f in o5[::2]}
        for f in hold:
            os.remove(S.path_of("open5", f))
        with quiet():
            out = stage_a()
        assert not out["judged"] and out["coverage"]["share"] < RULES["cov"] and out["stageA"] is None and json.load(open(sa))["judged"] is False
        for f, b in hold.items():
            open(S.path_of("open5", f), "wb").write(b)
        print("--- every bar waived (null / stress / DO / years / breadth switched off): every cell passes - but without the hand audit the run is NOT judged")
        waive = dict(n=1, l1_reb=1, l2_days=1, net_pos=False, do_pos=False, rho_neg=False, null=False, stress=False, do_null=False, rho_null=False, dd_years=0, ex_episode=False, years=0, ex2020=False, exbest=False, twin=False, a2_roc=-1e9, a2_sort=-1e9,
                     b_n=1, b_l1_reb=1, b_l2_days=1, b_roc=-1e9, b_sort=-1e9)
        RULES.update(waive)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = stage_a()
        txt = buf.getvalue()
        print(txt.rstrip())
        cells = out["stageA"]["cells"]
        assert all(c["PASS"] and c["A2"]["pass"] and not c["audit"]["audit_complete"] for c in cells.values()) and out["judged"] is False and out["candidate"] is None and out["pending_audit"] == list(CELLS)
        assert all(d < "2025-06-30" for d in dates_of(txt)) and "NOT YET JUDGED" in txt, "Stage A printed a lockbox date"
        for expect in ("no Stage A + A2 pass",):
            try:
                stage_b()
                raise AssertionError("Stage B must refuse a pending audit")
            except SystemExit as e:
                assert expect in str(e), str(e)
        # ---- the hand audit: write 'keep' for every listed contributor -> judged, a candidate (the highest A2 book ROC), the audit's sha on file
        print("--- the hand audit: every listed top-50 contributor 'keep' -> judged, a Stage B candidate")
        ap = os.path.join(OUT, "ddw_audit.csv")
        cd = pd.read_csv(os.path.join(OUT, "ddw_audit_candidates.csv"))
        pd.DataFrame({"symbol": cd["symbol"], "date": cd["date"], "cell": cd["cell"], "verdict": "keep", "note": "smoke: nothing found"}).to_csv(ap, index=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = stage_a()
        txt = buf.getvalue()
        print("\n".join(l for l in txt.splitlines() if l.startswith(("audit file", "DDW Stage A", "SIBLING RULE")) or "audit " in l and "COMPLETE" in l))
        cells = out["stageA"]["cells"]
        assert out["judged"] is True and out["pending_audit"] == [] and all(c["audit"]["audit_complete"] for c in cells.values()) and out["candidate"] is not None and out["audit_sha256"] == file_sha(ap)
        cand = out["candidate"]["cell"]
        assert cand == max(CELLS, key=lambda c: cells[c]["A2"]["roc"]) and out["stageA"]["pass_cells"] == list(CELLS), "the highest A2 book ROC wins; ties -> CELLS order"
        ca2 = cells[cand]["A2"]
        assert out["candidate"] == {"cell": cand, "c": ca2["c"], "std_book": ca2["std_book"], "std_cell": ca2["std_cell"], "window": ["2016-07-01", "2018-06-29"], "a2_book_roc": ca2["roc"]} and ca2["c"] > 0, "the frozen size travels with its two stds and the window"
        assert "SIBLING RULE" in txt and ("NOT checked here" in txt if cand[:2] == "L2" else "not engaged" in txt), "the sibling reminder is printed (L2 cells only)"
        assert {k: out.get(k) for k in stamp()} == stamp() and out["prereg_sha256_lf"] == PREREG_SHA and len(out["parity"]) == 4 and out["manifest_sha256"] == MANIFEST_PREFIX + "0" * 56
        flips = out["look_ahead_reading"]["flips"]
        assert set(flips) == set(CELLS) and set(out["reports"]["beta_to_es"]["L2-F"]) == {"DD days", "DD weeks (every day of them)", "all WF days"} and "L1" in out["reports"]["news_twin"]
        B_, S12_ = A13.load_463()[0], None
        S12_ = M12.Stretch(B_.raw, B_.index, None, WF0, PRE_END)
        assert all(len(out["reports"]["episodes"][c]) == len(S12_.qual) for c in CELLS) and "L1" in out["reports"]["hygiene_counts_by_year"]
        # a data_event on the candidate's largest contributor: it leaves the cell AND the null, the run is computed again, the NEW top-50 is unaudited -> pending again
        top = pd.read_csv(os.path.join(OUT, "ddw_audit_candidates.csv"))
        top = top[top["cell"] == cand].iloc[0]
        au = pd.read_csv(ap)
        au.loc[(au["symbol"] == top["symbol"]) & (au["date"] == top["date"]), "verdict"] = "data_event"
        au.to_csv(ap, index=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out2 = stage_a()
        cd2 = pd.read_csv(os.path.join(OUT, "ddw_audit_candidates.csv"))
        leg_ = cand[:2]
        assert out2["audit"]["data_event"] >= 1 and not any((cd2["symbol"] == top["symbol"]) & (cd2["date"] == top["date"]) & (cd2["cell"].str[:2] == leg_)), "the removed name-period is gone from the leg's cells"
        assert out2["stageA"]["cells"][cand]["base"]["n_pos"] <= cells[cand]["base"]["n_pos"] and out2["audit_sha256"] != out["audit_sha256"]
        print(f"audit data_event on {top['symbol']} {top['date']} ({cand}'s largest gain, ${top['pnl']:,.0f}): removed from the cell and the null; positions {cells[cand]['base']['n_pos']} -> {out2['stageA']['cells'][cand]['base']['n_pos']}; "
              f"net ${cells[cand]['base']['net']:,.0f} -> ${out2['stageA']['cells'][cand]['base']['net']:,.0f}; audit complete again: {out2['judged']}")
        cd2 = pd.read_csv(os.path.join(OUT, "ddw_audit_candidates.csv"))
        au = pd.read_csv(ap)
        extra = pd.DataFrame({"symbol": cd2["symbol"], "date": cd2["date"], "cell": cd2["cell"], "verdict": "keep", "note": "smoke"})
        pd.concat([au, extra]).drop_duplicates(["symbol", "date", "cell"]).to_csv(ap, index=False)
        with quiet():
            out = stage_a()
        assert out["judged"] is True and out["candidate"] is not None, "complete again after the new listing is audited"
        cand, c = out["candidate"]["cell"], out["candidate"]["c"]
        print(f"Stage A ran end to end in {time.time() - t0:.0f}s; candidate {cand} at c = x{c:g}")
        # ---- Stage B: the refusal paths, then the one read
        print("--- Stage B refusal paths: ATTN not judged, SIPORB not read yet, SIPORB's Stage A not a verdict, a stale stamp, a changed spec, a changed audit file, a drifted manifest, a book that does not reproduce LB, "
              "a drifted WF; none may write the flag")
        flag = os.path.join(OUT, "ddw_stageB_READ.flag")

        def must_refuse(frag, burned=False):
            try:
                with quiet():
                    stage_b()
                raise AssertionError(f"Stage B must refuse ({frag})")
            except SystemExit as e:
                assert frag in str(e), (frag, str(e))
                assert burned or not os.path.exists(flag), "a refused Stage B must not burn the lockbox"
        must_refuse("ATTN's Stage A is not on file and judged")
        attn = os.path.join(A13.OUT, "attn_stageA.json")
        json.dump({"judged": False}, open(attn, "w"))
        must_refuse("ATTN's Stage A is not on file and judged")
        json.dump({"judged": True}, open(attn, "w"))
        must_refuse("has not been read")
        sip = os.path.join(S.OUT, "siporb_stageA.json")
        for body in ({"judged": False, "stageA": None, "A2": None}, {"judged": True, "stageA": {"PASS": True}, "A2": {"pass": False, "error": "book check mismatch"}}, {"judged": True, "stageA": {"PASS": True}, "A2": None},
                     {"judged": True, "stageA": {"PASS": True}, "A2": {"pass": True}}):
            json.dump(body, open(sip, "w"))
            must_refuse("has not been read")                                                # not judged / A2 could not be judged / A2 not run / SIPORB passed but has not read: not a verdict
        os.remove(sip)
        open(os.path.join(S.OUT, "siporb_stageB_READ.flag"), "w").write("x")                # SIPORB's lockbox is 'read'
        assert A13.siporb_state() == "read"
        js0 = open(sa).read()
        for edit in (lambda j: j.update(harness_sha256="0" * 64), lambda j: j.update(early_close=j["early_close"][1:]), lambda j: j.update(r13_sha256="0" * 64), lambda j: [j.pop(k) for k in stamp()]):
            j = json.loads(js0)
            edit(j)
            json.dump(j, open(sa, "w"))
            must_refuse("different harness version")
        j = json.loads(js0)
        j["prereg_sha256_lf"] = "0" * 64
        json.dump(j, open(sa, "w"))
        must_refuse("another pre-registration")
        for edit in (lambda j: j["stageA"]["cells"][j["candidate"]["cell"]]["A2"].update(**{"pass": False}), lambda j: j["stageA"]["cells"][j["candidate"]["cell"]].update(PASS=False), lambda j: j.update(judged=False),
                     lambda j: j.update(candidate=None), lambda j: j["stageA"]["cells"][j["candidate"]["cell"]]["audit"].update(audit_complete=False)):
            j = json.loads(js0)
            edit(j)
            json.dump(j, open(sa, "w"))
            must_refuse("no Stage A + A2 pass")
        open(sa, "w").write(js0)
        for badc in (0.0, -1.0, float("nan"), None):                                        # c is a volatility ratio: any positive number is a frozen size, a broken one is a refusal before anything loads
            j = json.loads(js0)
            j["candidate"]["c"] = badc
            json.dump(j, open(sa, "w"))
            must_refuse("positive number")
        open(sa, "w").write(js0)
        with patched(me, PREREG_SHA="0" * 64):
            must_refuse("DIFFERS")
        au0 = open(ap).read()
        open(ap, "a").write("ZZZ,2016-01-04,L1-F,keep,a changed audit file\n")
        must_refuse("not the file Stage A ran with")
        open(ap, "w").write(au0)
        okbk = lambda B, lo, hi, ref: {"roc": 0.0, "sortino": 0.0, "ref": list(ref), "ok": True}
        with patched(me, manifest_sha=lambda: "ffffffff" + "0" * 56), patched(A13, book_check=okbk):
            CHECK_BOOK = True
            try:
                must_refuse("not the one Stage A ran on")                                       # a drifted cache manifest (the LB book check is stubbed to pass so the manifest one is reached)
            finally:
                CHECK_BOOK = False
        j = json.loads(js0)
        j["parity"][cand]["net"] += 1e6
        json.dump(j, open(sa, "w"))
        must_refuse("do not reproduce on Stage B's data")                                       # the WF numbers drifted since Stage A
        j = json.loads(js0)
        j["candidate"]["c"] *= 1.0001
        json.dump(j, open(sa, "w"))
        must_refuse("volatility-set size c")                                                    # the frozen size is recomputed from the first two WF years on Stage B's data: a drift of 1 in 10,000 stops it
        open(sa, "w").write(js0)
        CHECK_BOOK = True
        must_refuse("do not reproduce its LB numbers")
        CHECK_BOOK = False
        print("--- Stage B, the one read (SIPORB's READ flag stands in for its lockbox, a judged ATTN file for ATTN's Stage A): the flag after the load and the checks, the verdict, a second read refused")
        cap, real_cs = {}, cell_stats

        def tap(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):                                     # sees the lockbox call of the one read: keeps the cell's daily series, to recompute the book add independently
            st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
            if lo_ == LB0:
                cap["x"] = np.array(xk)
            return st_
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(me, cell_stats=tap):
            ok = stage_b()
        txt_b = buf.getvalue()
        print(txt_b.rstrip())
        sb = json.load(open(os.path.join(OUT, "ddw_stageB.json")))
        assert os.path.exists(flag) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c and sb["siporb"] == "read" and sb["coverage"]["share"] >= RULES["cov"] and sb["leg"]["n_pos"] > 0
        assert {k: sb.get(k) for k in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA, "Stage B's file carries the stamp"
        units, ulab = (RULES["b_l1_reb"], "weekly rebalances") if cand[:2] == "L1" else (RULES["b_l2_days"], "traded sessions")
        eb = sb["es_holes_lb"]                                                               # the ES holes that reach the lockbox are printed and stored with the read (none here: the synthetic holes are far before it)
        assert eb["stretch"] == ["2025-06-30", "2026-06-30"] and eb["l2_blind_sessions"] == 0 and eb["undefined_es_return_sessions"] == [] and eb["sessions"] == 45 and "ES holes (2025-06-30 .. 2026-06-30)" in txt_b, eb
        assert set(sb["checks"]) == {f"leg name-periods>={RULES['b_n']}", f"leg {ulab}>={units}", "leg net>0", "leg net>0 without its top name-period"} and ok is all(sb["checks"].values()), "the pass is the LEG's veto: four checks, no book"
        add, mb = sb["book_add_reported"], B_.mask(LB0, LB1)                                # the book add on the lockbox at the FROZEN c: reported (and stored), recomputed here from the book file and the captured series
        want = R11.stats((B_.raw + c * cap["x"])[mb], B_.index[mb])
        assert add["c"] == c and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["sortino"] - want["sort"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6 and abs(add["max_dd"] - want["max_dd"]) < 1e-9, add
        assert add["reference"] == {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]} and add["would_have_cleared"] is bool(want["roc"] >= RULES["b_roc"] and want["sort"] >= RULES["b_sort"]) and "never a pass" in add["note"]
        assert "book add, REPORTED and never part of the pass" in txt_b and ("PASS - the leg survives" in txt_b) is ok and ("FAIL - the leg is vetoed" in txt_b) is not ok, "the printout says what the book add is"
        if ok:
            assert "FORWARD SHADOW" in txt_b and "the book add above is a report" in txt_b
        # the pass is the leg's veto ALONE: the same read again (the smoke dir only - on the real OUT the flag is exclusive-create) with the leg forced to pass and the book add's bar forced to miss, then the leg forced
        # to fail and the bar forced to clear. The verdict follows the leg in both, the book add is reported in both and its numbers do not move
        def reread(leg_ok, book_ok):
            os.remove(flag)
            os.remove(os.path.join(OUT, "ddw_stageB.json"))

            def forced(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):
                st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                if lo_ == LB0:
                    st_ = {**st_, "n_pos": 10 ** 6 if leg_ok else 0, "n_units": 10 ** 6 if leg_ok else 0, "net": 1e6 if leg_ok else -1e6, "net_ex_top_pos": 1e6 if leg_ok else -1e6}
                return st_
            keep_bar = (RULES["b_roc"], RULES["b_sort"])
            RULES["b_roc"], RULES["b_sort"] = (-1e9, -1e9) if book_ok else (1e9, 1e9)
            b_ = io.StringIO()
            try:
                with contextlib.redirect_stdout(b_), patched(me, cell_stats=forced):
                    ok_ = stage_b()
            finally:
                RULES["b_roc"], RULES["b_sort"] = keep_bar
            return ok_, json.load(open(os.path.join(OUT, "ddw_stageB.json"))), b_.getvalue()
        for leg_ok, book_ok in ((True, False), (False, True)):
            ok2, sb2, t2 = reread(leg_ok, book_ok)
            assert ok2 is leg_ok and sb2["pass"] is leg_ok and all(sb2["checks"].values()) is leg_ok and sb2["book_add_reported"]["would_have_cleared"] is book_ok, (leg_ok, book_ok, sb2["checks"])
            assert abs(sb2["book_add_reported"]["roc"] - add["roc"]) < 1e-9 and sb2["book_add_reported"]["c"] == c and os.path.exists(flag), "the book add is the same sum whatever the verdict"
            assert ("PASS - the leg survives" in t2) is leg_ok and ("FAIL - the leg is vetoed" in t2) is not leg_ok and ("FORWARD SHADOW" in t2) is leg_ok
            print(f"  leg forced {'to pass' if leg_ok else 'to fail'}, book-add bar forced {'to clear' if book_ok else 'to miss'}: Stage B {'PASS' if ok2 else 'FAIL'}, would_have_cleared {sb2['book_add_reported']['would_have_cleared']} - the verdict is the leg's")
        must_refuse("already read", burned=True)
        try:
            stage_a()
            raise AssertionError("Stage A must be frozen once the lockbox has been read")
        except SystemExit as e:
            assert "Stage A is frozen" in str(e)
        # the commands that never touch data
        try:
            main(["bogus"])
        except SystemExit:
            pass
        pm = peak_mb()
        print("Stage B refused before the flag in every case above, wrote the flag only after the load and the checks, and refused a second read")
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline")
    finally:
        OUT, CHECK_BOOK, TBIS_CSV, NREP = keep["OUT"], keep["CHECK_BOOK"], keep["TBIS_CSV"], keep["NREP"]
        RULES.clear()
        RULES.update(keep["RULES"])
        SPEC.clear()
        SPEC.update(keep["SPEC"])
        R11.OUT, A13.OUT = keep["R11_OUT"], keep["A13_OUT"]
        S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get = keep["S"]
        data.find_master, data.load_master_arrays = keep["es"]


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r15_ddw.py selftest | smoke DIR | dryload | stage_a | stage_b   (stage_a runs after SIPORB's and ATTN's Stage A are planned; stage_b only on the one sealed-year day, after every Stage A of the three runs)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
