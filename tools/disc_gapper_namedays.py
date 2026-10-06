# disc_gapper_namedays.py - the ONE name-day builder of the shared PMFAIL r1 / RUNNER2 r1 pull (MANAGER #41 GO WITH EDITS).
#
# Spec, implemented exactly and nothing else:
#   docs/PREREG_pmfail_r1_2026-10-06.md   section 16 (THE ONE PULL SPEC: file, columns, roles, draw procedure, seeds, hash;
#                                         Amendment 0: the IEX twin is DROPPED, so the list carries no IEX column), section 4
#                                         (PMFAIL's event filter and split removal S1 / S2, the S3p / S3v reports), section 5
#                                         (the carry-over Rule 201 proxy), section 14 (test M and its calibration), section 3
#                                         (the photographed inputs and their sha256), section 21 (the counts file).
#   docs/PREREG_runner2_r1_2026-10-06.md  section 2 (RUNNER2's day-2 event, filters 1-7, the reported readings) and section 4
#                                         (its loosest reading = runner2_d2, its sampled roles).
#
# Reads ONLY the photographed daily cache (C:\EdgeLog\alpaca_cache\siporb\daily_raw.parquet; daily_split.parquet for the
# split factor F alone, as section 3 says) and the wide corporate-actions calendar - each sha256-checked against section 3
# and its manifest before anything is read - cut to dates < 2025-06-30 AT READ TIME. Never an intraday bar, never a quote,
# never a return: the output is a list of name-days and counts.
#
#   python tools/disc_gapper_namedays.py --dry-run     counts only, no file written
#   python tools/disc_gapper_namedays.py [--out PATH]  writes namedays_r1.csv, namedays_r1.sha256 (sha256sum format) and
#                                                      namedays_r1_counts.json next to it (default C:\EdgeLog\alpaca_cache\disc_gapper)
#
# The pull starts only when the lane posts the csv's sha256 and MANAGER runs it through the wrapper (MANAGER #41). A csv
# already on file with DIFFERENT bytes is never overwritten: a list is photographed once.
import argparse
import hashlib
import json
import os
import sys
import warnings
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "rocfrontier")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from import_alpaca_stocks import (EARLY_CLOSE_DATES, SPLIT_GAP_MIN, SPLIT_RATIO_TOL, SPLIT_VOLUME_TOL,  # noqa: E402
                                  _median)
import r5_siporb as S  # noqa: E402   the house universe rules (BAD_NAME / symbol shape) and the k <= 50 split-ratio range

# ------------------------------------------------------------------ inputs (section 3), pinned
CACHE_DIR = r"C:\EdgeLog\alpaca_cache\siporb"
RAW_PATH = os.path.join(CACHE_DIR, "daily_raw.parquet")
SPLIT_PATH = os.path.join(CACHE_DIR, "daily_split.parquet")
MANIFEST_PATH = r"C:\EdgeLog\_anatomy_cache\rocfrontier\alpaca_r1\siporb_cache_manifest.json"
CA_PATH = r"C:\EdgeLog\alpaca_cache\xgap\corporate_actions_wide.csv"
CA_MANIFEST_PATH = r"C:\EdgeLog\alpaca_cache\xgap\corporate_actions_wide_manifest.json"
OUT_DEFAULT = r"C:\EdgeLog\alpaca_cache\disc_gapper\namedays_r1.csv"
SHA_RAW = "fa42412d579ae673815bea25e1c14f9c87a93904af779ccffb03333c8e1bdccd"
SHA_SPLIT = "083f8c23d1d62cf7bda99d5c9a6373130c336ac605f57db5eeac832504281f6d"
SHA_MANIFEST = "380b05f2e0c4dfa32faabf2c86311f869d7371d3810a801bbf8a6c1f9ade4b78"     # the manifest's own manifest_sha256 field
SHA_CA = "e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5"
PREREGS = ("PREREG_pmfail_r1_2026-10-06.md", "PREREG_runner2_r1_2026-10-06.md")

# ------------------------------------------------------------------ windows
WF0, WF1, CUT = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"), pd.Timestamp("2025-06-30")   # every array cut to < CUT
YEARS = (WF1 - WF0).days / 365.25                                                                     # 3,285 / 365.25 = 8.994
WF_YEARS = tuple(f"{y}-{(y + 1) % 100:02d}" for y in range(2016, 2025))                             # 2016-17 .. 2024-25 (July-June)
BUCKETS = ("lt5", "5to20")                                                                            # lt5 = P < $5, 5to20 = P >= $5

# ------------------------------------------------------------------ PMFAIL section 4 / RUNNER2 section 2
P_LO, P_HI = 1.00, 20.00
ADV_MIN, ADV_N = 1_000_000.0, 20
GAP_MIN = 1.20                      # PMFAIL: O / P >= 1.20
RUN_MIN = 1.40                      # RUNNER2: c(D1) / c(D0) >= 1.40
S1_TOL = 0.005                      # |F / F' - 1| > 0.005
SSR_FRAC = 0.90                     # carry-over Rule 201: l(t-1) <= 0.9 x c(t-2)
SPLIT_TYPES = ("forward_split", "reverse_split", "unit_split", "stock_dividend")
KMAX = S.MS_KMAX                    # whole ratios k = 2..50 (r5_siporb's missed-split scan range; split_like_gaps stops at 20)
M_CATCH = 0.90                      # test M keeps its volume clause only if it catches >= 90% of vendor-known reverse splits
FLAT_PM = (0.95, 1.05)              # nonevent: 0.95 <= O / P < 1.05
FLAT_R2 = (0.95, 1.05)              # runner2_nonevent: 0.95 <= c(D1) / c(D0) <= 1.05

# ------------------------------------------------------------------ the list (section 16)
COLUMNS = ("symbol", "date", "wf_year", "price_bucket", "pmfail_event", "runner2_d2", "nonevent", "runner2_nonevent",
           "quotes_pmfail", "quotes_runner2")
ROLES = COLUMNS[4:]
SEEDS = {"nonevent": 20261006, "runner2_nonevent": 20261009, "quotes_pmfail": 20261007, "quotes_runner2": 20261008}
QUOTES_N = 10


def refuse(msg):
    raise SystemExit("REFUSED: " + msg + " (nothing computed, no file written)")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha256_lf(path):
    """LF-normalised sha256 of a text file (the house form for code and preregs); None if missing"""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------ loading (sha-checked, cut at read)
def verify_inputs(raw_path=RAW_PATH, split_path=SPLIT_PATH, manifest_path=MANIFEST_PATH, ca_path=CA_PATH,
                  ca_manifest_path=CA_MANIFEST_PATH):
    """Section 3: every input hashes to the registered sha256 AND the manifest that photographed it says the same.
    SIPORB's cache manifest: its manifest_sha256 field = 380b05f2..., key_files carry the two daily files' sha256.
    The calendar's manifest (r16_xgap's capull, tag wide) carries the csv's sha256. Any mismatch refuses."""
    for p in (raw_path, split_path, manifest_path, ca_path, ca_manifest_path):
        if not os.path.exists(p):
            refuse(f"input not on file: {p}")
    try:
        man = json.load(open(manifest_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        refuse(f"SIPORB cache manifest unreadable ({e})")
    if man.get("manifest_sha256") != SHA_MANIFEST:
        refuse(f"SIPORB cache manifest_sha256 is {man.get('manifest_sha256')}, section 3 registers {SHA_MANIFEST}")
    kf = man.get("key_files") or {}
    got = {}
    for name, path, want in (("daily_raw.parquet", raw_path, SHA_RAW), ("daily_split.parquet", split_path, SHA_SPLIT)):
        listed = (kf.get(name) or {}).get("sha256")
        if listed != want:
            refuse(f"the manifest lists {name} as {listed}, section 3 registers {want}")
        got[name] = sha256_file(path)
        if got[name] != want:
            refuse(f"{name} on disk hashes to {got[name]}, section 3 and the manifest register {want}")
    try:
        cman = json.load(open(ca_manifest_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        refuse(f"calendar manifest unreadable ({e})")
    listed = (cman.get("sha256") or {}).get("corporate_actions_wide.csv")
    if listed != SHA_CA:
        refuse(f"the calendar manifest lists corporate_actions_wide.csv as {listed}, section 3 registers {SHA_CA}")
    got["corporate_actions_wide.csv"] = sha256_file(ca_path)
    if got["corporate_actions_wide.csv"] != SHA_CA:
        refuse(f"corporate_actions_wide.csv hashes to {got['corporate_actions_wide.csv']}, section 3 registers {SHA_CA}")
    return {"sha256": got, "siporb_manifest_sha256": man.get("manifest_sha256"), "siporb_manifest_path": manifest_path,
            "calendar_manifest_sha256_file": sha256_file(ca_manifest_path), "calendar_start": cman.get("start"),
            "calendar_end": cman.get("end")}


def read_daily(path, cols):
    """one daily parquet, only `cols`, cut to date < 2025-06-30 AT READ TIME (pyarrow filter; asserted)"""
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=list(cols), filters=[("date", "<", CUT.to_pydatetime())], read_dictionary=["symbol"])
    df = t.to_pandas()
    if len(df) and not pd.Timestamp(df["date"].max()) < CUT:
        refuse(f"{os.path.basename(path)}: input not cut at {CUT:%Y-%m-%d}")
    return df


def read_calendar(path=CA_PATH):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# ------------------------------------------------------------------ small array helpers (rows = sessions, columns = symbols)
def shift(a, k):
    """out[t] = a[t - k]: the value k market sessions before t (NaN / False where there is none)"""
    fill = np.nan if a.dtype.kind == "f" else False
    out = np.full(a.shape, fill, dtype=a.dtype)
    if k < a.shape[0]:
        out[k:] = a[:a.shape[0] - k]
    return out


def prior_mean(a, n):
    """out[t] = mean of a over the n sessions BEFORE t (t-n .. t-1), NaN unless all n are present; summed in a fixed order"""
    acc = np.zeros(a.shape)
    for k in range(1, n + 1):
        if k < a.shape[0]:
            acc[k:] += a[:a.shape[0] - k]
    acc[:n] = np.nan
    return acc / n


def window_all(ex, w):
    """out[t] = ex is True on every one of rows t-w+1 .. t"""
    cnt = np.zeros(ex.shape, np.int32)
    for k in range(w):
        if k < ex.shape[0]:
            cnt[k:] += ex[:ex.shape[0] - k]
    return cnt == w


def window_any(m, w):
    """out[t] = m is True on any of rows t-w+1 .. t"""
    out = np.zeros(m.shape, bool)
    for k in range(w):
        if k < m.shape[0]:
            out[k:] |= m[:m.shape[0] - k]
    return out


def near_whole(r, inverse=False):
    """r within 2% of a whole k = 2..50 (|r / k - 1| <= 0.02); inverse=True also of 1/k (|r x k - 1| <= 0.02)"""
    out = np.zeros(r.shape, bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        for k in range(2, KMAX + 1):
            out |= np.abs(r / k - 1.0) <= SPLIT_RATIO_TOL
            if inverse:
                out |= np.abs(r * k - 1.0) <= SPLIT_RATIO_TOL
    return out


def big_whole(r, inverse=False):
    """|r - 1| >= 0.25 AND r within 2% of a whole ratio (the price clause of S3p / S2' / test M; test M adds r > 1)"""
    with np.errstate(invalid="ignore"):
        big = np.isfinite(r) & (np.abs(r - 1.0) >= SPLIT_GAP_MIN)
    out = np.zeros(r.shape, bool)
    idx = np.nonzero(big)
    out[idx] = near_whole(r[idx], inverse=inverse)
    return out


def prior_nanmedian_at(V, ti, si, n=20):
    """median of the daily volume over the n sessions before (ti, si), over the bars present; NaN if none"""
    if not len(ti):
        return np.zeros(0)
    rows = ti[:, None] - np.arange(n, 0, -1)[None, :]
    vals = V[np.clip(rows, 0, None), si[:, None]]
    vals = np.where(rows >= 0, vals, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(vals, axis=1)


def wf_year_index(days):
    """(T,) int: 0..8 = the July-June WF year of a session in 2016-07-01..2025-06-29, -1 outside"""
    y = np.where(days.month >= 7, days.year, days.year - 1) - 2016
    inside = (days >= WF0) & (days <= WF1)
    return np.where(inside, y, -1).astype(np.int64)


# ------------------------------------------------------------------ the calendar (section 4, S2; RUNNER2 S1c)
def _date(x):
    x = (x or "").strip()
    if not x:
        return None
    try:
        t = pd.Timestamp(x)
    except (ValueError, TypeError):
        return None
    return None if pd.isna(t) else t.normalize()


def map_symbol(sym, ex, nc_by_old):
    """section 4 S2 (as amended): 'follow name_change rows (old_symbol -> new_symbol), each dated on or after the previous hop
    (the action's ex_date for the first hop), earliest first, until none is left'. Chained, not fixed at the action's date:
    tickers are reused (FISV 2018-03-20 stays FISV via FI 2023 -> FISV 2025, never the old FI's 2021 rename to XPRO). A name
    change acts on its ex_date, else its process_date (the wide file's name_change rows carry no ex_date; r16_xgap's rule).
    Ties on one date: new_symbol order. A row is followed at most once (no loop). -> (today's ticker, hops)"""
    cur, d, used, hops = sym, ex, set(), 0
    while True:
        nxt = None
        for dt, new, rid in nc_by_old.get(cur, ()):
            if dt >= d and rid not in used:
                nxt = (dt, new, rid)
                break                                   # the list is sorted (date, new_symbol, row): the first hit is the earliest
        if nxt is None:
            return cur, hops
        used.add(nxt[2])
        cur, d, hops = nxt[1], nxt[0], hops + 1


def calendar_splits(ca, days, syms, ex_mask=None):
    """-> (CAL (T, S) bool: a forward_split / reverse_split / unit_split / stock_dividend of the symbol-mapped name has ex_date = that
    session, info). unit_split rows join on new_symbol. Split-type rows with ex_date on/after 2025-06-30 are dropped at read (counted);
    name_change rows of ANY date are kept: they are the identity table to today's ticker and carry no price."""
    T, NS = len(days), len(syms)
    cal = np.zeros((T, NS), bool)
    df = ca.copy()
    for c in ("type", "symbol", "old_symbol", "new_symbol", "ex_date", "process_date"):
        if c not in df.columns:
            refuse(f"the calendar has no column {c}")
        df[c] = df[c].fillna("").astype(str).str.strip()
    nc_by_old, nc_info = {}, {"rows": 0, "usable": 0, "unusable_blank_or_undated_or_self": 0, "dated_on_or_after_cut_kept": 0}
    ncd = df[df["type"] == "name_change"]
    for rid, old, new, ex, proc in zip(ncd.index, ncd["old_symbol"], ncd["new_symbol"], ncd["ex_date"], ncd["process_date"]):
        nc_info["rows"] += 1
        dt = _date(ex) or _date(proc)
        if not old or not new or dt is None or old == new:
            nc_info["unusable_blank_or_undated_or_self"] += 1
            continue
        nc_info["usable"] += 1
        nc_info["dated_on_or_after_cut_kept"] += int(dt >= CUT)
        nc_by_old.setdefault(old, []).append((dt, new, int(rid)))
    for v in nc_by_old.values():
        v.sort()
    day_ix = {d: i for i, d in enumerate(days)}
    sym_ix = {s: j for j, s in enumerate(syms)}
    by = {}
    sp = df[df["type"].isin(SPLIT_TYPES)]
    for typ, sym, new, ex_s in zip(sp["type"], sp["symbol"], sp["new_symbol"], sp["ex_date"]):
        src = new if typ == "unit_split" else sym
        ex = _date(ex_s)
        yr = str(ex.year) if ex is not None else "n/a"
        c = by.setdefault(typ, {}).setdefault(yr, {"rows": 0, "unusable_no_symbol_or_ex_date": 0, "dropped_at_cut": 0,
                                                   "renamed": 0, "matched": 0, "matched_with_bar": 0,
                                                   "unmatched_name": 0, "unmatched_session": 0})
        c["rows"] += 1
        if not src or ex is None:
            c["unusable_no_symbol_or_ex_date"] += 1
            continue
        if ex >= CUT:
            c["dropped_at_cut"] += 1
            continue
        final, hops = map_symbol(src, ex, nc_by_old)
        c["renamed"] += int(hops > 0)
        j, i = sym_ix.get(final), day_ix.get(ex)
        if j is None:
            c["unmatched_name"] += 1
        elif i is None:
            c["unmatched_session"] += 1
        else:
            c["matched"] += 1
            cal[i, j] = True
            if ex_mask is not None and ex_mask[i, j]:
                c["matched_with_bar"] += 1
    return cal, {"name_change": nc_info, "split_types": by}


# ------------------------------------------------------------------ the build (pure: frames in, list + counts out)
def _cut(df):
    """the cut at 2025-06-30, without a copy when the frame was already cut at read -> (frame, rows dropped)"""
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.assign(date=pd.to_datetime(df["date"]))
    keep = (df["date"] < CUT).to_numpy()
    n = int((~keep).sum())
    return (df.loc[keep] if n else df), n


def _sym_cols(series, syms):
    sidx = pd.Index(syms)
    if isinstance(series.dtype, pd.CategoricalDtype):
        m = sidx.get_indexer(series.cat.categories.astype(str))
        codes = series.cat.codes.to_numpy()
        return np.where(codes >= 0, m[np.clip(codes, 0, None)], -1)
    return sidx.get_indexer(series.astype(str))


def _symbols(series):
    if isinstance(series.dtype, pd.CategoricalDtype):
        used = np.unique(series.cat.codes.to_numpy())
        used = used[used >= 0]
        return sorted(str(x) for x in series.cat.categories[used])
    return sorted(set(series.astype(str)))


def _grid(df, days, syms, cols):
    """long frame -> {col: (T, S) float array}, presence mask; a duplicated (symbol, date) keeps its last row (counted)"""
    t = days.get_indexer(pd.DatetimeIndex(pd.to_datetime(df["date"])))
    s = _sym_cols(df["symbol"], syms)
    ok = (t >= 0) & (s >= 0)
    t, s = t[ok], s[ok]
    key = t.astype(np.int64) * len(syms) + s
    last = ~pd.Series(key).duplicated(keep="last").to_numpy()
    dups = int((~last).sum())
    t, s = t[last], s[last]
    out = {}
    for c in cols:
        a = np.full((len(days), len(syms)), np.nan)
        a[t, s] = df[c].to_numpy(float)[ok][last]
        out[c] = a
    ex = np.zeros((len(days), len(syms)), bool)
    ex[t, s] = True
    return out, ex, {"rows_placed": int(len(t)), "rows_off_grid": int((~ok).sum()), "duplicates_dropped_keep_last": dups}


def _count(mask, yidx, bk):
    """(9, 3) counts of a (T, S) mask by WF year x bucket (lt5, 5to20, na)"""
    out = np.zeros((len(WF_YEARS), 3), np.int64)
    ti, si = np.nonzero(mask)
    y = yidx[ti]
    ok = y >= 0
    np.add.at(out, (y[ok], bk[ti[ok], si[ok]]), 1)
    return out


def _cjson(c):
    by_year = {WF_YEARS[i]: {"lt5": int(c[i, 0]), "5to20": int(c[i, 1]), "na": int(c[i, 2]), "all": int(c[i].sum())}
               for i in range(len(WF_YEARS))}
    tot = c.sum(axis=0)
    return {"by_year": by_year, "total": {"lt5": int(tot[0]), "5to20": int(tot[1]), "na": int(tot[2]), "all": int(tot.sum())}}


def draw_stratum(pool_t, pool_s, n, rng):
    """section 16's draw on ONE stratum: pool sorted by (date, symbol); if len(pool) <= n take all (the generator is not
    called), else idx = rng.choice(len(pool), size=n, replace=False); take pool rows at sorted(idx). -> (t, s) arrays"""
    order = np.lexsort((pool_s, pool_t))            # days ascending = date order; syms sorted = symbol order (asserted in build)
    pt, ps = pool_t[order], pool_s[order]
    if len(pt) <= n:
        return pt, ps
    idx = rng.choice(len(pt), size=n, replace=False)
    idx = np.sort(idx)
    return pt[idx], ps[idx]


def draw_role(pools, n_by, seed):
    """a fresh generator per role; strata in order wf_year ascending, lt5 then 5to20. pools / n_by keyed (year index, bucket index)"""
    rng = np.random.default_rng(seed)
    out_t, out_s = [], []
    for yi in range(len(WF_YEARS)):
        for bi in range(len(BUCKETS)):
            pt, ps = pools[(yi, bi)]
            t, s = draw_stratum(pt, ps, int(n_by[(yi, bi)]), rng)
            out_t.append(t)
            out_s.append(s)
    return np.concatenate(out_t).astype(np.int64), np.concatenate(out_s).astype(np.int64)


def strata(mask, yidx, bk):
    """{(year index, bucket index): (t, s)} of a mask's cells inside the WF window, lt5 / 5to20 only"""
    ti, si = np.nonzero(mask)
    y, b = yidx[ti], bk[ti, si]
    return {(yi, bi): (ti[(y == yi) & (b == bi)], si[(y == yi) & (b == bi)])
            for yi in range(len(WF_YEARS)) for bi in range(len(BUCKETS))}


def build(raw, split, ca, verbose=False):
    """raw: symbol, date, o, l, c, v (raw daily bars); split: symbol, date, o, c (split-adjusted, used ONLY for F); ca: the
    wide calendar (dtype str). -> SimpleNamespace(rows = the list as a DataFrame in COLUMNS order, sorted by date then symbol,
    counts = everything printed / filed, masks, pools, n_by, days, syms)."""
    say = print if verbose else (lambda *a, **k: None)
    n_in = len(raw)
    raw, n_cut = _cut(raw)                                                         # every array is cut before anything is computed
    split, _n = _cut(split)
    if len(raw) and not raw["date"].max() < CUT:
        refuse("raw input not cut")
    days = pd.DatetimeIndex(sorted(raw["date"].unique()))                         # section 4: the session calendar = the distinct dates
    syms_all = _symbols(raw["symbol"])
    shape_drop = [s for s in syms_all if S.why_not(s, "", "NYSE") is not None]   # r5_siporb's symbol-shape rules (BAD_NAME needs names: see notes)
    syms = [s for s in syms_all if s not in set(shape_drop)]
    if syms != sorted(syms) or not days.is_monotonic_increasing:
        refuse("internal: symbols / sessions not sorted")
    if any(ch in s for s in syms for ch in ',"\r\n'):
        refuse("a symbol holds a csv delimiter")
    T, NS = len(days), len(syms)
    say(f"grid: {NS:,} symbols x {T:,} sessions ({days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}); "
        f"{len(shape_drop)} symbols dropped by the shape rules (expected 0)")
    gs, _exs, sginfo = _grid(split, days, syms, ("o", "c"))
    del split, _exs
    g, EX, ginfo = _grid(raw, days, syms, ("o", "l", "c", "v"))
    del raw
    O, L, C, V = g["o"], g["l"], g["c"], g["v"]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = O / gs["o"]                                                        # F = raw / split-adjusted open on t
        del gs["o"]
        ratio /= shift(C / gs["c"], 1)                                             # F' = raw / split close on the session before
        del gs
        s1_known = np.isfinite(ratio) & (ratio > 0)
        S1 = s1_known & (np.abs(ratio - 1.0) > S1_TOL)                             # |F / F' - 1| > 0.005
        S1rev = s1_known & (ratio > 1.0 + S1_TOL)                                  # F / F' > 1.005: a reverse split
    del ratio, g

    yidx = wf_year_index(days)
    wf_row = yidx >= 0
    half_row = np.array([f"{d:%Y-%m-%d}" in EARLY_CLOSE_DATES for d in days])
    Cp1, Cp2 = shift(C, 1), shift(C, 2)
    P = Cp1                                                                        # the raw close of the market session before t
    with np.errstate(invalid="ignore", divide="ignore"):
        adv_ok = prior_mean(C * V, ADV_N) >= ADV_MIN                               # ADV$[t] over t-20 .. t-1, all 20 bars present
        bk = np.where(np.isnan(P), 2, np.where(P < 5.0, 0, 1)).astype(np.int8)    # 0 lt5, 1 5to20, 2 na (no prior close)
        band_p = (P >= P_LO) & (P <= P_HI)
        gr = O / P                                                                 # PMFAIL O / P; = g2 = o(D2) / c(D1) for RUNNER2; = g of test M on u
        carry = shift(L, 1) <= SSR_FRAC * Cp2                                      # carry-over Rule 201 into t (known before 04:00)
    del O, L
    CAL, cal_info = calendar_splits(ca, days, syms, EX)

    # ---- test M (PMFAIL section 14; RUNNER2 S2 on u = D1) and its calibration
    mprice = big_whole(gr) & (gr > 1.0)
    mt, ms = np.nonzero(mprice)
    med = prior_nanmedian_at(V, mt, ms, 20)
    with np.errstate(invalid="ignore", divide="ignore"):
        prod = gr[mt, ms] * V[mt, ms] / med
    mvol = np.zeros((T, NS), bool)
    mvol[mt, ms] = (prod >= 1.0 / SPLIT_VOLUME_TOL) & (prod <= SPLIT_VOLUME_TOL)
    cal_pop = mprice & S1rev & wf_row[:, None]
    n_cal, n_catch = int(cal_pop.sum()), int((cal_pop & mvol).sum())
    rate = (n_catch / n_cal) if n_cal else None
    m_keeps_volume = bool(rate is not None and rate >= M_CATCH)                    # 'Catch rate >= 0.90: M stands as written; else ... price only'
    M = mvol if m_keeps_volume else mprice
    mcal = {"population": "S1 reverse-split sessions (F / F' > 1.005) in 2016-07-01..2025-06-29 whose g = o(u) / c(u-1) is a whole ratio (g > 1, |g - 1| >= 0.25, within 2% of k = 2..50)",
            "n": n_cal, "caught_by_volume_clause": n_catch, "catch_rate": rate, "threshold": M_CATCH,
            "decision": "M stands as written (volume clause kept)" if m_keeps_volume else "M drops the volume clause (price only); the volume reading is reported",
            "by_year": {WF_YEARS[i]: {"n": int(cal_pop[yidx == i].sum()), "caught": int((cal_pop & mvol)[yidx == i].sum())} for i in range(len(WF_YEARS))},
            "m_flags_wf_price_only": int((mprice & wf_row[:, None]).sum()), "m_flags_wf_with_volume": int((mvol & wf_row[:, None]).sum()),
            "shared": "one test, one calibration: PMFAIL condition 4 (iii) and RUNNER2 filter 6 (S2) both read it"}

    # ---- PMFAIL (section 4)
    base = EX & wf_row[:, None]
    with np.errstate(invalid="ignore"):
        gap = gr >= GAP_MIN
        flat_pm = (gr >= FLAT_PM[0]) & (gr < FLAT_PM[1])
    pm_steps, cur = [], base
    for name, m in (("bar_on_t", base), ("p_band_1_20", band_p), ("adv_1m_prior20", adv_ok), ("gap_open_1.20", gap),
                    ("s1_vendor_split", ~S1), ("s2_calendar_split", ~CAL), ("carry_ssr", ~carry)):
        cur = cur & m
        pm_steps.append((name, cur))
    pm_event = base & band_p & adv_ok & gap & ~S1 & ~CAL                         # pmfail_event: events + the carry-over-SSR days
    pm_reg = pm_event & ~carry                                                     # section 4's registered event days
    pm_flat = base & band_p & adv_ok & flat_pm & ~S1 & ~CAL & ~carry               # every section-4 filter except the gap, 0.95 <= O/P < 1.05
    s3p = pm_reg & big_whole(gr, inverse=True)
    s3v = np.zeros((T, NS), bool)
    s3v_fallback = 0
    for t, s in zip(*np.nonzero(s3p)):
        n_after = min(t + 20, T) - t                                               # sessions t..t+19 that exist before the cut
        if n_after < 10:
            s3v[t, s], s3v_fallback = True, s3v_fallback + 1
            continue
        ma, mb = _median(V[t:t + 20, s].tolist()), _median(V[max(0, t - 20):t, s].tolist())
        if ma is None or mb is None:
            s3v[t, s] = True                                                       # split_like_gaps: no volume to judge by -> the price test
            continue
        prod_v = gr[t, s] * ma / mb
        s3v[t, s] = (1.0 / SPLIT_VOLUME_TOL) <= prod_v <= SPLIT_VOLUME_TOL

    # ---- RUNNER2 (section 2); row t = D2, t-1 = D1, t-2 = D0
    r_base = EX & wf_row[:, None]
    not_half = ~half_row[:, None] & np.ones((1, NS), bool)
    bars22 = window_all(EX, 22)                                                    # D0-19 .. D0, D1, D2 = rows t-21 .. t
    c0, c1 = Cp2, Cp1
    with np.errstate(invalid="ignore", divide="ignore"):
        rr = c1 / c0
        run = rr >= RUN_MIN
        band0 = (c0 >= P_LO) & (c0 <= P_HI)
        band1 = (c1 >= P_LO) & (c1 <= P_HI)
        flat_r2 = (rr >= FLAT_R2[0]) & (rr <= FLAT_R2[1])
    adv_r = shift(adv_ok, 1)                                                       # ADV$ over D0-19 .. D0 = ADV$[D1]
    s1_r = S1 | shift(S1, 1)                                                       # S1 on D1 or D2
    cal_r = CAL | shift(CAL, 1)                                                    # S1c on D1 or D2
    m_r = shift(M, 1)                                                              # S2 = test M on u = D1
    r_steps, cur = [], r_base
    for name, m in (("bar_on_d2", r_base), ("not_half_day", not_half), ("bars_d0m19_to_d2", bars22), ("run_1.40", run),
                    ("band_c_d0", band0), ("band_c_d1", band1), ("adv_1m_d0m19_d0", adv_r), ("s1_vendor_d1_d2", ~s1_r),
                    ("s1c_calendar_d1_d2", ~cal_r), ("s2_test_m_d1", ~m_r), ("carry_ssr", ~carry)):
        cur = cur & m
        r_steps.append((name, cur))
    r_core = r_base & not_half & bars22 & adv_r & ~s1_r & ~cal_r
    r_reg = r_core & run & band0 & band1 & ~m_r & ~carry                           # RUNNER2's registered events
    r_loose = r_core & run & band0                                                 # band on c(D0) only, S1 + S1c only, carry SSR kept
    r_flat = r_core & flat_r2 & band0 & band1 & ~m_r & ~carry                      # every section-2 filter except the run, 0.95..1.05
    # 'half days are skipped as day 2 and counted': the runs the skip removes = every other filter passed, D2 on a half day
    half_core = r_base & half_row[:, None] & bars22 & adv_r & ~s1_r & ~cal_r & run & band0
    half_skipped = {"registered_rule": _cjson(_count(half_core & band1 & ~m_r & ~carry, yidx, bk)),
                    "loosest_reading": _cjson(_count(half_core, yidx, bk)),
                    "name_days_with_a_bar_on_a_half_day_d2": int((r_base & ~not_half).sum())}
    # widened reading: S1 / S1c over D0-19 .. D2 (both known before D2's open); test M over D0-19 .. D1 only - M on D2 would
    # read v(D2), the full-day volume of the trade session, when the volume clause is kept (a look-ahead)
    wide = window_any(S1 | CAL, 22) | shift(window_any(M, 21), 1)
    readings = {"registered": r_reg, "band_on_c_d0_only": r_core & run & band0 & ~m_r & ~carry,
                "whole_ratio_guard_without_volume": r_core & run & band0 & band1 & ~shift(mprice, 1) & ~carry,
                "test_m_with_volume": r_core & run & band0 & band1 & ~shift(mvol, 1) & ~carry,
                "s2prime_on": r_reg & ~big_whole(gr, inverse=True),
                "splits_widened_s1_s1c_d0m19_to_d2_m_d0m19_to_d1": r_reg & ~wide,
                "carry_ssr_kept": r_core & run & band0 & band1 & ~m_r,
                "loosest_runner2_d2": r_loose}
    del C, V, Cp1, Cp2, gr, rr

    # ---- roles, in order (section 16)
    roles = {"pmfail_event": pm_event, "runner2_d2": r_loose}
    earlier = pm_event | r_loose
    n_pm = {k: int(v) for k, v in _strata_counts(pm_reg, yidx, bk).items()}
    n_r2 = {k: int(v) for k, v in _strata_counts(r_reg, yidx, bk).items()}
    pools = {"nonevent": strata(pm_flat & ~earlier, yidx, bk)}
    t_, s_ = draw_role(pools["nonevent"], n_pm, SEEDS["nonevent"])
    roles["nonevent"] = _mask(t_, s_, T, NS)
    earlier = earlier | roles["nonevent"]
    pools["runner2_nonevent"] = strata(r_flat & ~earlier, yidx, bk)
    t_, s_ = draw_role(pools["runner2_nonevent"], n_r2, SEEDS["runner2_nonevent"])
    roles["runner2_nonevent"] = _mask(t_, s_, T, NS)
    q10 = {k: QUOTES_N for k in n_pm}
    pools["quotes_pmfail"] = strata(pm_reg, yidx, bk)
    t_, s_ = draw_role(pools["quotes_pmfail"], q10, SEEDS["quotes_pmfail"])
    roles["quotes_pmfail"] = _mask(t_, s_, T, NS)
    pools["quotes_runner2"] = strata(r_reg, yidx, bk)
    t_, s_ = draw_role(pools["quotes_runner2"], q10, SEEDS["quotes_runner2"])
    roles["quotes_runner2"] = _mask(t_, s_, T, NS)
    assert not (roles["quotes_pmfail"] & ~pm_reg).any() and not (roles["quotes_runner2"] & ~r_reg).any()
    assert not (roles["nonevent"] & (pm_event | r_loose)).any()
    assert not (roles["runner2_nonevent"] & (pm_event | r_loose | roles["nonevent"])).any()

    anyrole = np.zeros((T, NS), bool)
    for r in ROLES:
        anyrole |= roles[r]
    ti, si = np.nonzero(anyrole)                                                   # row-major = sorted by date, then symbol
    if (bk[ti, si] > 1).any() or (yidx[ti] < 0).any():
        refuse("internal: a listed name-day has no prior close or lies outside the WF window")
    rows = pd.DataFrame({"symbol": np.asarray(syms, dtype=object)[si], "date": [f"{d:%Y-%m-%d}" for d in days[ti]],
                         "wf_year": np.asarray(WF_YEARS, dtype=object)[yidx[ti]],
                         "price_bucket": np.asarray(BUCKETS, dtype=object)[bk[ti, si]]})
    for r in ROLES:
        rows[r] = roles[r][ti, si].astype(np.int64)
    rows = rows.sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)
    rows = rows[list(COLUMNS)]

    counts = {
        "inputs": {"raw_rows_in": int(n_in), "raw_rows_dropped_at_cut": int(n_cut),
                   "raw_grid": ginfo, "split_grid": sginfo, "cut": f"{CUT:%Y-%m-%d}", "wf": [f"{WF0:%Y-%m-%d}", f"{WF1:%Y-%m-%d}"],
                   "sessions": T, "first_session": f"{days[0]:%Y-%m-%d}" if T else None, "last_session": f"{days[-1]:%Y-%m-%d}" if T else None,
                   "wf_sessions": int(wf_row.sum()), "symbols": NS, "symbols_dropped_by_shape_rules": shape_drop, "years": YEARS},
        "calendar": cal_info,
        "test_m_calibration": mcal,
        "pmfail": {"survivors_in_order": {n: _cjson(_count(m, yidx, bk)) for n, m in pm_steps},
                   "pmfail_event_role": _cjson(_count(pm_event, yidx, bk)), "registered": _cjson(_count(pm_reg, yidx, bk)),
                   "carry_ssr_removed": _cjson(_count(pm_event & carry, yidx, bk)),
                   "s1_unknown_among_gap_survivors": int((base & band_p & adv_ok & gap & ~s1_known).sum()),
                   "report_s3p_price_only": _cjson(_count(s3p, yidx, bk)),
                   "report_s3v_volume_lookahead": _cjson(_count(s3v, yidx, bk)), "s3v_fell_back_to_s3p": int(s3v_fallback)},
        "runner2": {"survivors_in_order": {n: _cjson(_count(m, yidx, bk)) for n, m in r_steps},
                    "half_day_d2_skipped": half_skipped, "registered": _cjson(_count(r_reg, yidx, bk)),
                    "readings": {k: _cjson(_count(v, yidx, bk)) for k, v in readings.items()},
                    "test_m_registered_form": ("with_volume (= readings.test_m_with_volume)" if m_keeps_volume else
                                               "price_only (= readings.whole_ratio_guard_without_volume)"),
                    "links": {"runner2_d2_also_pmfail_event": int((r_loose & pm_event).sum()),
                              "runner2_d2_not_pmfail_event": int((r_loose & ~pm_event).sum()),
                              "registered_both_legs": int((r_reg & pm_reg).sum())}},
        "roles": {r: _cjson(_count(roles[r], yidx, bk)) for r in ROLES},
        "pools": {r: {f"{WF_YEARS[y]}/{BUCKETS[b]}": int(len(v[0])) for (y, b), v in pools[r].items()} for r in pools},
        "seeds": dict(SEEDS), "quotes_per_stratum": QUOTES_N,
        "rows": int(len(rows)),
        "count_bar": {leg: _bar(_count(m, yidx, bk)) for leg, m in (("pmfail", pm_reg), ("runner2", r_reg))},
    }
    masks = {"pm_event": pm_event, "pm_reg": pm_reg, "pm_flat": pm_flat, "r_loose": r_loose, "r_reg": r_reg, "r_flat": r_flat,
             "s3p": s3p, "s3v": s3v, "M": M, "mprice": mprice, "mvol": mvol, "CAL": CAL, "S1": S1, **roles}
    return SimpleNamespace(rows=rows, counts=counts, masks=masks, pools=pools, n_by={"pmfail": n_pm, "runner2": n_r2},
                           days=days, syms=syms, m_keeps_volume=m_keeps_volume)


def _strata_counts(mask, yidx, bk):
    c = _count(mask, yidx, bk)
    return {(yi, bi): int(c[yi, bi]) for yi in range(len(WF_YEARS)) for bi in range(len(BUCKETS))}


def _mask(t, s, T, NS):
    m = np.zeros((T, NS), bool)
    m[t, s] = True
    return m


def _bar(c):
    """the 9-year mean count bar (MANAGER #41 Q3) read on daily-cache registered events (the bar itself reads FILLED trades)"""
    per = {WF_YEARS[i]: int(c[i].sum()) for i in range(len(WF_YEARS))}
    n = int(c.sum())
    return {"per_year": per, "n": n, "n_per_year": n / YEARS, "mean_ge_50": bool(n / YEARS >= 50), "n_ge_100": bool(n >= 100),
            "thin_years_under_25": [y for y, v in per.items() if v < 25]}


# ------------------------------------------------------------------ output
def csv_bytes(rows):
    """UTF-8, LF, header row, no index column, the section-16 column order"""
    if list(rows.columns) != list(COLUMNS):
        refuse("internal: column order")
    lines = [",".join(COLUMNS)]
    for rec in rows.itertuples(index=False, name=None):
        lines.append(",".join(str(x) for x in rec))
    return ("\n".join(lines) + "\n").encode("utf-8")


def sha_line(data, name):
    """sha256sum format: hex, two spaces, file name, LF"""
    return f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("utf-8")


def out_paths(out):
    stem = os.path.splitext(out)[0]
    return {"csv": out, "sha": stem + ".sha256", "counts": stem + "_counts.json"}


def _atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def lib_versions():
    """the library versions the draws ran under (numpy's Generator promises no cross-version stream for choice, NEP 19)"""
    try:
        import pyarrow
        pa = pyarrow.__version__
    except ImportError:
        pa = None
    return {"python": sys.version, "numpy": np.__version__, "pandas": pd.__version__, "pyarrow": pa}


def write_outputs(res, out, info=None):
    """csv + sha256 + counts json. A csv already on file with different bytes is NEVER overwritten (refused before any write)."""
    p = out_paths(out)
    data = csv_bytes(res.rows)
    if os.path.exists(p["csv"]):
        with open(p["csv"], "rb") as f:
            if f.read() != data:
                refuse(f"{p['csv']} is on file with different bytes - a list is photographed once; remove it by hand only if "
                       "its sha256 was never posted")
    os.makedirs(os.path.dirname(os.path.abspath(p["csv"])), exist_ok=True)
    _atomic(p["csv"], data)
    sl = sha_line(data, os.path.basename(p["csv"]))
    _atomic(p["sha"], sl)
    repo = os.path.dirname(HERE)
    meta = {"csv": os.path.abspath(p["csv"]), "csv_sha256": hashlib.sha256(data).hexdigest(), "csv_bytes": len(data),
            "builder": os.path.abspath(__file__), "builder_sha256_lf": sha256_lf(os.path.abspath(__file__)),
            "preregs_sha256_lf": {n: sha256_lf(os.path.join(repo, "docs", n)) for n in PREREGS},
            "inputs_verified": info, "versions": lib_versions(), "built": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")}
    _atomic(p["counts"], json.dumps({"meta": meta, **res.counts}, indent=1, default=_js).encode("utf-8"))
    return p, sl.decode("utf-8").strip()


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


# ------------------------------------------------------------------ printing
def _table(title, header, rows, w0=None):
    w0 = w0 or max([len(r[0]) for r in rows] + [4])
    print(title)
    print(" " * w0 + "".join(f"{h:>9}" for h in header))
    for lab, vals in rows:
        print(f"{lab:<{w0}}" + "".join(f"{v:>9}" for v in vals))


def print_report(res):
    c = res.counts
    i = c["inputs"]
    print(f"\nsessions {i['sessions']:,} ({i['first_session']} .. {i['last_session']}), WF sessions {i['wf_sessions']:,}, symbols {i['symbols']:,}; "
          f"raw rows dropped at the cut {i['raw_rows_dropped_at_cut']:,}; duplicates dropped {i['raw_grid']['duplicates_dropped_keep_last']}; "
          f"shape-rule drops {len(i['symbols_dropped_by_shape_rules'])}")
    hdr = list(WF_YEARS) + ["total"]
    for leg, key in (("PMFAIL", "pmfail"), ("RUNNER2", "runner2")):
        surv = c[key]["survivors_in_order"]
        for b in ("all", "lt5", "5to20"):
            _table(f"\n{leg} filter survivors in order, bucket {b} (bucket = raw close of the session before; 'na' only before the band)",
                   hdr, [(n, [v["by_year"][y][b] for y in WF_YEARS] + [v["total"][b]]) for n, v in surv.items()])
    pm = c["pmfail"]
    rows = [("carry_ssr_removed", pm["carry_ssr_removed"]), ("report_s3p", pm["report_s3p_price_only"]), ("report_s3v_lookahead", pm["report_s3v_volume_lookahead"])]
    _table("\nPMFAIL: carry-over SSR days removed from the registered set (listed as pmfail_event); S3p / S3v among registered events (reports, never removed)", hdr,
           [(n, [v["by_year"][y]["all"] for y in WF_YEARS] + [v["total"]["all"]]) for n, v in rows])
    print(f"  S1 not computable among gap survivors (no split bar): {pm['s1_unknown_among_gap_survivors']}; S3v fell back to S3p: {pm['s3v_fell_back_to_s3p']}")
    r2 = c["runner2"]
    _table("\nRUNNER2 readings (reported counts, never the event set)", hdr,
           [(n, [v["by_year"][y]["all"] for y in WF_YEARS] + [v["total"]["all"]]) for n, v in r2["readings"].items()])
    hs = r2["half_day_d2_skipped"]
    _table("\nRUNNER2 runs skipped because D2 is a half day (every other filter passed)", hdr,
           [(n, [hs[n]["by_year"][y]["all"] for y in WF_YEARS] + [hs[n]["total"]["all"]]) for n in ("registered_rule", "loosest_reading")])
    print(f"  name-days with a bar on a half-day D2 (all names, not runs): {hs['name_days_with_a_bar_on_a_half_day_d2']}; "
          f"test M registered form: {r2['test_m_registered_form']}; links: {r2['links']}")
    m = c["test_m_calibration"]
    print(f"\ntest M calibration (shared by both legs): {m['caught_by_volume_clause']} of {m['n']} vendor-known reverse splits with a whole-ratio g "
          f"caught by the volume clause = {('%.3f' % m['catch_rate']) if m['catch_rate'] is not None else 'undefined'} (bar {m['threshold']}) -> {m['decision']}")
    cal = c["calendar"]
    print(f"calendar: name_change rows {cal['name_change']['rows']:,} (usable {cal['name_change']['usable']:,})")
    for typ, by in cal["split_types"].items():
        tot = {k: sum(v[k] for v in by.values()) for k in next(iter(by.values()))}
        print(f"  {typ}: " + ", ".join(f"{k} {v:,}" for k, v in tot.items()))
    print("\nper-role rows by wf_year and price_bucket (lt5 / 5to20 / all)")
    print(" " * 18 + "".join(f"{y:>16}" for y in WF_YEARS) + f"{'total':>16}")
    for r in ROLES:
        v = c["roles"][r]
        cells = [f"{v['by_year'][y]['lt5']}/{v['by_year'][y]['5to20']}/{v['by_year'][y]['all']}" for y in WF_YEARS]
        cells.append(f"{v['total']['lt5']}/{v['total']['5to20']}/{v['total']['all']}")
        print(f"{r:<18}" + "".join(f"{x:>16}" for x in cells))
    print(f"rows in the list: {c['rows']:,}")
    print(f"\nregistered events per July-June year against the 9-year mean count bar (n / {YEARS:.3f} >= 50 and n >= 100; the bar reads FILLED trades, these are the daily-cache ceilings)")
    for leg in ("pmfail", "runner2"):
        b = c["count_bar"][leg]
        print(f"  {leg:<8}" + "".join(f"{b['per_year'][y]:>9}" for y in WF_YEARS) + f"   n {b['n']:,}  n/yr {b['n_per_year']:.1f}  "
              f"mean>=50 {b['mean_ge_50']}  n>=100 {b['n_ge_100']}  thin(<25) {b['thin_years_under_25'] or 'none'}")


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="PMFAIL r1 / RUNNER2 r1 name-day list (PREREG_pmfail_r1 section 16)")
    ap.add_argument("--out", default=OUT_DEFAULT, help="the csv path (sha256 and counts json land next to it)")
    ap.add_argument("--dry-run", action="store_true", help="counts only, no file")
    a = ap.parse_args(argv)
    info = verify_inputs()
    print("inputs verified against section 3 and their manifests: " + ", ".join(f"{k} {v[:12]}..." for k, v in info["sha256"].items()), flush=True)
    print("versions: " + ", ".join(f"{k} {v.split()[0] if v else v}" for k, v in lib_versions().items()), flush=True)
    # the frames are handed straight to build (no reference kept here), so the uncut long tables are freed once gridded
    res = build(read_daily(RAW_PATH, ("symbol", "date", "o", "l", "c", "v")), read_daily(SPLIT_PATH, ("symbol", "date", "o", "c")),
                read_calendar(CA_PATH), verbose=True)
    print_report(res)
    if a.dry_run:
        print("\nDRY RUN - no file written")
        return res
    p, line = write_outputs(res, a.out, info)
    print(f"\nwrote {p['csv']} ({len(res.rows):,} rows), {p['sha']}, {p['counts']}\n{line}")
    return res


if __name__ == "__main__":
    main()
