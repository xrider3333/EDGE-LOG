# -*- coding: utf-8 -*-
r"""PMFAIL r1 STAGE A - the small-cap gapper's failed premarket high, short (docs/PREREG_pmfail_r1_2026-10-06.md,
AMENDMENT 0 included; LF sha256 pinned below). This file also computes the ONE four-cell family null of PMFAIL r1 and
RUNNER2 r1 (prereg section 9; RUNNER2 r1 section 9), importing RUNNER2's per-draw routine from its own harness.

Modes, run in this order (each refuses unless the earlier files exist with a matching stamp):
  python tools/pmfail_r1_stageA.py --counts  --manifest M --photo-sha HEX [--probe-log P]   step 1 (no exit walk, no P&L)
  python tools/pmfail_r1_stageA.py --overlap                                                 step 2 (needs RUNNER2's counts)
  python tools/pmfail_r1_stageA.py --power   --manifest M --photo-sha HEX [--probe-log P]   step 3 (coin flips; SD + lines only)
  python tools/pmfail_r1_stageA.py --null    --manifest M --photo-sha HEX [--probe-log P]   step 4 (the four-cell family null)
  python tools/pmfail_r1_stageA.py --run     --manifest M --photo-sha HEX [--probe-log P]   the real run (bars 1-10, verdict)
Outputs: %EDGELOG_HOME%\_anatomy_cache\disc_pmfail_r1\ (counts.json, schedule.csv, overlap.json, power.json + its csvs,
null.json, null_draws.csv, null.sha256, trades.csv, daily.csv, stage_a.json, one <mode>.txt log per mode).
No network: this file sends no request and imports no HTTP library, key loader or rate limiter (EARLY_CLOSE_DATES is read
from tools/import_alpaca_stocks.py's source with ast). The photograph is read from disk only. load_inputs() imports the
name-day builder, which imports import_alpaca_stocks (and so requests); nothing here calls it, so this file is not on
tests/test_alpaca_rate.py's wiring list.

THE SHARED CORE. The loader, the halt / 5m-bar / stop-walk / halted-into-the-close mechanics, costs, N*, the statistics,
the book and the verdict live HERE (one file, as the task names it); RUNNER2's harness imports them from this module
(`import pmfail_r1_stageA as PM`). This module imports RUNNER2's harness only inside --null, so there is no import cycle.
RUNNER2's module: tools/runner2_r1_stageA.py (the task's name) or tools/disc_runner2_r1_stageA.py (the prereg's registered
name, PMFAIL section 9 / RUNNER2 header and section 14); exactly one of the two may exist, else --null refuses. Interface
it must provide: null_context(photo=..., book=...) -> ctx with .omega_sha256 and .omega_n; null_half(ctx, n=500,
seed=20261010) -> (array (n, 2, 3) = [draw, cell P / W, stat ROC30 / t / R-sum], info dict of per-draw lists).

INTERPRETATIONS of the prereg (each pinned here before any number; the quoted text is the prereg's):
 1. Photograph id. "The manifest's sha256 is the photograph's id" (RUNNER2 s.4) = sha256 of the manifest FILE's bytes
    (manifest.jsonl as the wrapper writes it: a run_header row, then one row per PAGE fetched - kind, symbol, date, url,
    status, bytes, sha256, file, pages | mark), passed as --photo-sha. Its run_header rows must cite namedays_r1.csv's
    sha256 e9ca777a.... A request = its rows (kind, symbol, date, mark); its status = its LAST row's: 200 = served (an
    empty page = 'empty'); 403 = 'refused' (the SIP refusal; a feed=iex row is labelled IEX); else 'missing' ("counted as
    no bars"). A bars file named by ONE row of equal size is pinned: its sha256 must equal the row's (every bars file, else
    REFUSED). The wrapper re-serialises every quotes / marks file (one page or several), so the manifest pins its
    pages but never the file - even when the sizes match by chance (NRXP 2021-07-23 close, 36 bytes both): each such
    file is hashed into the photograph's 'unpinned digest', which every later step must reproduce.
 2. "each endpoint must print 'SAME MAPPING'" (s.17): the probe text (manifest rows whose kind starts with 'probe', or
    --probe-log) must hold a line with 1Min and SAME MAPPING and a line with quotes and SAME MAPPING, else REFUSED.
 3. Page files: the JSON of one request (a page, a list of pages, or {"pages": [...]}); bars under "bars" and quotes
    under "quotes", each a list or a {symbol: list} map (the multi-symbol endpoint). A marks file shared by the 8 marks
    must be a {mark: pages} map (optionally under "marks"). Any other shape REFUSES (never read as an empty day).
 4. Stamps: "Alpaca `t` is UTC RFC-3339 at the bar's START" -> tz database -> America/New_York; minute m = hour x 60 +
    minute; a stamp with nonzero seconds or an ET date other than the requested session REFUSES. Bars with v <= 0 or a
    price <= 0 are dropped and counted ("a v = 0 bar is a halt", s.12); identical duplicates dropped and counted,
    conflicting duplicates REFUSE. "Every array is cut to dates < 2025-06-30": a request dated on or after it REFUSES.
 5. "Sessions ... 09:30..12:59 on the EARLY_CLOSE_DATES": bars from 13:00 on a half day belong to no session (ignored);
    stops judged through 12:54, exit window [12:55, 13:00).
 6. Resume bar: the first present bar after >= 5 consecutive absent regular minutes ("A run from 09:30 (delayed open)
    ... counts"). "the 4-minute reading (every halt rule rerun with 4)": the threshold enters only the resume-bar entry
    skip (and the null's eligibility); "a bar opening >= stop exits at its open" already covers a halt-jumped stop at any
    run length, and the exit window is five minutes in both readings.
 7. "No present bar in the exit window ... halted into the close": exit at the raw open of the first daily bar in the next
    10 market sessions; nights held = market sessions from t to the exit session (locate charges = 1 + nights). A
    stress-priced exit books on t's next market session (nights 1), or on t when that is on or after 2025-06-30 (nights
    0). "it falls on or after 2025-06-30": the cut calendar ends 2025-06-27, so a window running past it with no bar
    found is stress-priced. Flags S1 / S2 (calendar) / test M are read on sessions t+1 .. the exit session inclusive.
    A stopless control (OPENPRINT) takes the last pre-halt close as its stress price (max(stop, close) with no stop).
 8. "the max regular 1m high from 09:30 through that bar's last minute > PMH" and "close < PMH": both strict, 1e-9
    tolerance. "any regular 1m low from 09:30 through the signal bar's last minute <= 0.9 x P": inclusive, 1e-9.
    "S2 = entry + 1.5 x (S1 - entry), rounded up to the cent" = ceil(x x 100 - 1e-9) / 100. Skip order counted:
    no_bars, no_pmh, no_signal, ssr_active, no_fill_bar, resume_bar, entry_ge_S1.
 9. Rule-201-legal fill (report): filled at the limit on the first bar in [end, end + 5) with high >= limit + $0.01; that
    fill bar's own high counts against the stop (the conservative SIPORB form; its open does not); a limit >= S1 is no
    trade. On a carry-over SSR day every signal is SSR-active.
10. PMBREAK (report): the same fill-bar, resume-bar (5 minutes) and open-through-stop skips as the short; no SSR skip (a
    long); no locate. OPENPRINT: SSR-at-open = the first regular bar's low <= 0.9 x P.
11. Counts step: "halted-into-close exits" is printed as fills whose exit window is empty (no exit walk is called before
    the P&L run; under reading L a stop exit never reaches the window, so this is the ceiling); the trade-level count
    prints in --run. Signals by entry half-hour = the half-hour of the signal end.
12. Power line: the coin-flip leg solves its OWN N* with the same solver (its shares cannot wait for the primary's real
    N*, which needs a real-direction run); long = stop entry - (S1 - entry), mirrored reading L, no locate; coin
    default_rng(20261006).choice([-1.0, 1.0]) over the schedule sorted by (date, symbol): -1 short, +1 long.
13. The null (s.9): years ascending; pool sorted by (date, symbol); if len(pool) <= n_y take all (shortfall counted, no
    generator call), else idx = rng.choice(len(pool), n_y, replace=False); then over the days at sorted(idx) one
    rng.integers(len(eligible)) each. n_y = the primary's filled trades in that July-June year (by entry date). A NaN
    statistic counts as -inf in a max (counted). Percentiles: numpy linear. Notion (b) = p95 - p50 of the max ROC.
14. R-sum without its 3 best R days = the sum over R's 762 days after dropping the 3 largest daily values there.
15. Bar 10 "net > 0 at stress cost and PF >= 1.05": net at stress cost, PF at the judged (primary) cost, both reading L
    (the stress PF prints beside it). Years in bar 4 and per-year nets are by booking (exit) session; fill counts by
    entry date.
16. LOWFLOAT: shares rebased by F(filed) / F(t) with F(t) taken on the session BEFORE t (known before the open; S1 removed
    any split on t itself).
17. Overlap (step 2) trade days = fill (entry) dates. RUNNER2 link in --run: the PMFAIL side only (counts and PMFAIL's
    P&L on linked name-days); the joint P&L prints in RUNNER2's --run, which comes after this one.
18. Reported rows (OPENPRINT, PMBREAK, placebo, SSR legal, subsets) print at their own N* and at the $5,000 scale-free
    figure. A spread name-day served with no valid second has no value (counted), unlike a refused one (prior h50).
"""
import argparse
import hashlib
import importlib
import json
import math
import os
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for _p in (os.path.join(HERE, "rocfrontier"), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import power_line as PL  # noqa: E402


def _early_close_dates():
    """tools/import_alpaca_stocks.py's EARLY_CLOSE_DATES (prereg s.3: lines 139-145), read from its source with ast so this
    module never imports that file's requests / key / pace modules (the builder, called in load_inputs, does)"""
    import ast
    with open(os.path.join(HERE, "import_alpaca_stocks.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "EARLY_CLOSE_DATES" for t in node.targets):
            return frozenset(ast.literal_eval(node.value))
    raise SystemExit("REFUSED: EARLY_CLOSE_DATES not found in tools/import_alpaca_stocks.py")


EARLY_CLOSE_DATES = _early_close_dates()

TS = pd.Timestamp
ET = "America/New_York"

# ------------------------------------------------------------------ windows (s.3, s.6)
WF0, WF1, CUT = TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30")
YEARS = (WF1 - WF0).days / 365.25                                   # 3,285 / 365.25 = 8.994
WF_YEARS = tuple(f"{y}-{(y + 1) % 100:02d}" for y in range(2016, 2025))
BUCKETS = ("lt5", "5to20")

# ------------------------------------------------------------------ session minutes (minutes after ET midnight)
PRE0, RTH0, RTH1, RTH1_HALF = 240, 570, 960, 780
NM = RTH1 - PRE0                                                     # 720 minutes, 04:00 .. 15:59
EXIT_WIN = 5
WIN_K0, WIN_K1 = 1, 17                                               # 5m bars starting 09:35 .. 10:55
HALT_K, HALT_K4 = 5, 4
SSR_FRAC = 0.90
CENT = 0.01
TOL = 1e-9

# ------------------------------------------------------------------ size, costs, locate (s.6)
GRID = np.arange(5000.0, 500000.0 + 1.0, 500.0)
DD_TARGET = 30000.0
CAP_FRAC = 0.01
N_SCALEFREE = 5000.0
COMM, HALF_TICK, STRESS_ADD = 0.0035, 0.005, 0.01
LOCATE, LOCATE_STRESS = 0.01, 0.02
H50_PRIOR = {"lt5": 0.0050, "5to20": 0.0025}
BUCKET_MIN = 20
CAP_NOTIONALS = (5000, 10000, 25000, 50000, 100000, 250000, 500000)
COST_BPS = (0, 10, 25, 50, 100)
COST_LOC = (0.0, 0.005, 0.01, 0.02)

# ------------------------------------------------------------------ null, power, bars (s.9, s.10, s.15)
NULL_DRAWS, SEED_PM, SEED_R2, SEED_COIN, SEED_BOOT = 500, 20261006, 20261010, 20261006, 20261005
BOOT_DRAWS, BOOT_BLOCK = 1000, 20
PCTS = (50.0, 95.0, 97.5)
PCT_METHOD = "linear"
STATS = ("roc30", "t", "rsum")
COUNT_MEAN, COUNT_MIN, THIN = 50.0, 100, 25
BAR_ROC, BAR_EARN, BAR_PF, BAR_T, BAR_YEARS = 15.0, 5.0, 1.05, 2.0, 6
X20 = (TS("2020-02-15"), TS("2020-04-30"))
X2021 = (TS("2020-01-01"), TS("2021-12-31"))
X2020 = (TS("2020-01-01"), TS("2020-12-31"))
X2022 = (TS("2022-01-01"), TS("2022-12-31"))
HALVES = ((TS("2016-07-01"), TS("2021-12-31")), (TS("2022-01-01"), WF1))
VOL_END, VOL_SHARE = TS("2018-07-01"), 0.25
BOOK_FACTS, LINE_FACTS = (93.81, 3.816), (120.82, 3.916)
PARITY_TOL = (0.006, 0.0006)
R_DAYS, R_EPIS, DD_DAYS, DD_EPIS = 762, 45, 460, 28
DELIST_BEFORE = TS("2026-06-01")
REVSPLIT_DAYS = 60
LOWFLOAT_CUT = 20_000_000
PATH_LO, PATH_HI = -30, 390
CELLS = ("primary", "neighbour")
READINGS = ("L", "N")

# ------------------------------------------------------------------ pinned shas (s.3; the namedays list; the preregs)
NAMEDAYS_SHA = "e9ca777ae11a24b592d8760482f5e4e0ccdc5e1e072cfbe910787d86b47f5e8c"
PREREG_NAMES = {"pmfail": "PREREG_pmfail_r1_2026-10-06.md", "runner2": "PREREG_runner2_r1_2026-10-06.md"}
PREREG_SHA_LF = {"pmfail": "18a009f09f1922541de346b6ee45cb32bc82cacd2c151028ec4dc7b8b6815550",
                 "runner2": "eda8954ed206957b5bc7a7bc0a51110061912a4f8e0c7bc7f313cc3cf117356d"}
INPUT_SHAS = {
    "assets.csv": "b85928ff655a883dd3eb44d8d96b3b745ffe2f5f0e0ca0991485895f5e960991",
    "residual_days.csv": "bfe64d87a2cf6fd569181ffae9092317653844126de075fe64844430ac189f60",
    "line.csv": "98f3edc743625b3742f13a972cab35178658feaa7f506e56e27f77f56e9c38ad",
    "a2.json": "0c27cb47fe245cd8fbbcc1bc3eb0881ea0edefba74d45b7821a059dc7e4c9214",
    "episodes.csv": "ebfb67c03a258a0d4efe73a20a2c7027fd5eb3d25403f17d8e071cb4626a9af4",
    "book463_daily.csv": "d1543735b5408f50be5971089e00a800f8e510af3d4a63678ff8939f41277dff",
    "shares_asfiled_wide.csv": "02387a4f1140c41872a7b46cf6b9657abec90ef90d09a0a2ee47ff882c2f4433",
    "xbrl_shares_frames.csv": "bba7f8737680b7330c74055699b9195b33f10610cf86b3e5c48ba30c7ddadf82",
}
R2_MODULES = ("disc_runner2_r1_stageA",)


# ================================================================== paths (resolved at call time: tests point EDGELOG_HOME at tmp)
def home():
    return os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def out_dir():
    return os.path.join(home(), "_anatomy_cache", "disc_pmfail_r1")


def r2_out_dir():
    return os.path.join(home(), "_anatomy_cache", "disc_runner2_r1")


def input_paths():
    h = home()
    q19 = os.path.join(h, "_anatomy_cache", "q19")
    return {"assets.csv": os.path.join(h, "alpaca_cache", "siporb", "assets.csv"),
            "residual_days.csv": os.path.join(q19, "residual_days.csv"), "line.csv": os.path.join(q19, "line.csv"),
            "a2.json": os.path.join(q19, "a2.json"), "episodes.csv": os.path.join(q19, "episodes.csv"),
            "book463_daily.csv": os.path.join(h, "_anatomy_cache", "rocfrontier", "r4", "book463_daily.csv"),
            "shares_asfiled_wide.csv": os.path.join(h, "_research_cache", "xbrl_companyfacts", "shares_asfiled_wide.csv"),
            "xbrl_shares_frames.csv": os.path.join(h, "_research_cache", "xbrl_frames", "xbrl_shares_frames.csv"),
            "namedays_r1.csv": os.path.join(h, "alpaca_cache", "disc_gapper", "namedays_r1.csv"),
            "namedays_r1.sha256": os.path.join(h, "alpaca_cache", "disc_gapper", "namedays_r1.sha256"),
            "daily_raw.parquet": os.path.join(h, "alpaca_cache", "siporb", "daily_raw.parquet")}


def docs_dir():
    return os.path.join(REPO, "docs")


# ================================================================== small helpers
def refuse(msg):
    raise SystemExit("REFUSED: " + msg + " (nothing computed past this point)")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha256_lf(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def ceil_cent(x):
    return math.ceil(x * 100.0 - 1e-9) / 100.0


def wf_year_index(d):
    d = TS(d)
    if d < WF0 or d > WF1:
        return -1
    return (d.year if d.month >= 7 else d.year - 1) - 2016


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, float):
        return None if not math.isfinite(o) else o
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return f"{o:%Y-%m-%d}"
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _clean(o):
    """JSON-safe copy: NaN / inf -> None, numpy -> python (so a re-read compares equal)"""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(float(o)) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return f"{o:%Y-%m-%d}"
    return o


def json_bytes(obj):
    return (json.dumps(_clean(obj), indent=1, sort_keys=True, default=_js) + "\n").encode("utf-8")


def _atomic(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_once(path, data):
    """a filed step is photographed once: different bytes on file are never overwritten (refused before any write)"""
    if os.path.exists(path):
        with open(path, "rb") as f:
            if f.read() == data:
                return path
        refuse(f"{path} is on file with different bytes - a filed step is never overwritten")
    _atomic(path, data)
    return path


def write_file(path, data):
    _atomic(path, data)
    return path


def csv_bytes(df):
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


def versions():
    try:
        import pyarrow
        pa = pyarrow.__version__
    except ImportError:
        pa = None
    return {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__, "pyarrow": pa}


def hm(m):
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}" if m is not None else ""


class Tee:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "w", encoding="utf-8", newline="\n")
        self.o = sys.stdout

    def write(self, s):
        self.o.write(s)
        self.f.write(s)

    def flush(self):
        self.o.flush()
        self.f.flush()

    def close(self):
        self.f.close()


# ================================================================== preregs
def check_preregs(ddir=None):
    """both preregs, LF-normalised, must hash to the AMENDMENT-1 texts this harness implements"""
    ddir = ddir or docs_dir()
    got = {}
    for k, name in PREREG_NAMES.items():
        p = os.path.join(ddir, name)
        got[k] = sha256_lf(p)
        if got[k] != PREREG_SHA_LF[k]:
            refuse(f"{name} LF sha256 is {got[k]}, this harness implements {PREREG_SHA_LF[k]} (AMENDMENT 1) - "
                   "rebase the worktree onto the main that carries it")
    return got


# ================================================================== the photograph (the pull's manifest + raw pages)
def _feed_of(url):
    try:
        q = parse_qs(urlparse(url or "").query)
        return (q.get("feed") or [None])[0]
    except ValueError:
        return None


class Bars1m(SimpleNamespace):
    """status: ok | empty | missing | refused; feed: sip | iex | None; df: m, o, h, l, c, v, n, vw; dq: drop counts"""


class Quotes(SimpleNamespace):
    """status: ok | empty | missing | refused; df: t_ns (UTC ns), bp, ap - stable-sorted by t_ns (ties keep served order)"""


def parse_pages(obj, field, symbol, where=""):
    """raw pages -> list of records of one symbol. Accepted shapes: a page {field: [...] or {sym: [...]}}, a list of pages,
    {"pages": [...]} (each page may also sit under "body"). A file in which no page carries `field` REFUSES (a misread
    layout must never read as an empty day)."""
    if isinstance(obj, dict) and "pages" in obj and isinstance(obj["pages"], list):
        pages = obj["pages"]
    elif isinstance(obj, list):
        pages = obj
    else:
        pages = [obj]
    out, seen = [], False
    if isinstance(obj, list) and not obj:
        return out
    for pg in pages:
        if isinstance(pg, dict) and "body" in pg and isinstance(pg["body"], (dict, list, str)):
            pg = pg["body"]
            if isinstance(pg, str):
                pg = json.loads(pg)
        if not isinstance(pg, dict) or field not in pg:
            continue
        seen = True
        v = pg[field]
        if v is None:
            continue
        if isinstance(v, dict):
            other = [k for k in v if k != symbol]
            if other and symbol not in v:
                refuse(f"{where}: page keyed by {other[:3]}, not {symbol}")
            v = v.get(symbol) or []
        if not isinstance(v, list):
            refuse(f"{where}: '{field}' is not a list")
        out.extend(v)
    if not seen:
        refuse(f"{where}: no page carries '{field}' - unknown page layout")
    return out


def frame_1m(records, date, where=""):
    """Alpaca 1Min records -> DataFrame m, o, h, l, c, v, n, vw (sorted by m, unique m) + data-quality counts"""
    date = TS(date).normalize()
    if date >= CUT:
        refuse(f"{where}: a session on or after {CUT:%Y-%m-%d} is in the photograph")
    dq = {"rows": len(records), "dropped_v_le_0": 0, "dropped_price_le_0": 0, "dropped_dup_identical": 0,
          "dropped_outside_0400_1559": 0}
    cols = ["m", "o", "h", "l", "c", "v", "n", "vw"]
    if not records:
        return pd.DataFrame({c: pd.Series(dtype=float) for c in cols}).astype({"m": "int64"}), dq
    df = pd.DataFrame(records)
    for c in ("t", "o", "h", "l", "c", "v"):
        if c not in df.columns:
            refuse(f"{where}: bar field '{c}' missing")
    ts = pd.DatetimeIndex(pd.to_datetime(df["t"], utc=True, format="ISO8601")).tz_convert(ET)
    if ((ts.second != 0) | (ts.microsecond != 0) | (ts.nanosecond != 0)).any():
        refuse(f"{where}: a bar stamp with nonzero seconds")
    if (ts.normalize().tz_localize(None) != date).any():
        refuse(f"{where}: a bar stamped on an ET date other than {date:%Y-%m-%d}")
    out = pd.DataFrame({"m": (ts.hour * 60 + ts.minute).to_numpy(np.int64),
                        "o": df["o"].astype(float).to_numpy(), "h": df["h"].astype(float).to_numpy(),
                        "l": df["l"].astype(float).to_numpy(), "c": df["c"].astype(float).to_numpy(),
                        "v": df["v"].astype(float).to_numpy(),
                        "n": df["n"].astype(float).to_numpy() if "n" in df.columns else np.full(len(df), np.nan),
                        "vw": df["vw"].astype(float).to_numpy() if "vw" in df.columns else np.full(len(df), np.nan)})
    inside = (out["m"] >= PRE0) & (out["m"] < RTH1)
    dq["dropped_outside_0400_1559"] = int((~inside).sum())
    out = out[inside]
    badv = ~(out["v"] > 0)
    dq["dropped_v_le_0"] = int(badv.sum())
    out = out[~badv]
    badp = ~((out["o"] > 0) & (out["h"] > 0) & (out["l"] > 0) & (out["c"] > 0))
    dq["dropped_price_le_0"] = int(badp.sum())
    out = out[~badp]
    dup = out.duplicated(keep="first")
    dq["dropped_dup_identical"] = int(dup.sum())
    out = out[~dup]
    if out["m"].duplicated().any():
        refuse(f"{where}: two different bars stamped on one minute")
    return out.sort_values("m", kind="mergesort").reset_index(drop=True), dq


def frame_quotes(records, where=""):
    if not records:
        return pd.DataFrame({"t_ns": pd.Series(dtype="int64"), "bp": pd.Series(dtype=float), "ap": pd.Series(dtype=float)})
    df = pd.DataFrame(records)
    for c in ("t", "bp", "ap"):
        if c not in df.columns:
            refuse(f"{where}: quote field '{c}' missing")
    t = pd.DatetimeIndex(pd.to_datetime(df["t"], utc=True, format="ISO8601")).asi8
    out = pd.DataFrame({"t_ns": t.astype(np.int64), "bp": df["bp"].astype(float).to_numpy(),
                        "ap": df["ap"].astype(float).to_numpy()})
    return out.sort_values("t_ns", kind="mergesort").reset_index(drop=True)


class Photograph:
    """The pull, read from disk only: manifest.jsonl (a run_header row, then one row per request: kind, symbol, date,
    url, fetched_utc, status, bytes, sha256, file, pages | mark) and the raw page files it names."""

    def __init__(self, manifest_path, manifest_sha256, probe_log=None, namedays_sha256=NAMEDAYS_SHA):
        self.manifest_path = os.path.abspath(manifest_path)
        self.root = os.path.dirname(self.manifest_path)
        self.manifest_sha256 = manifest_sha256
        self.probe_log = probe_log
        self.namedays_sha256 = namedays_sha256
        self.rows = {}
        self.headers = []
        self.verified = None
        self.dq = {}

    def _file(self, f):
        return f if os.path.isabs(f) else os.path.join(self.root, f)

    def verify(self, full=True):
        if not os.path.exists(self.manifest_path):
            refuse(f"manifest not on file: {self.manifest_path}")
        with open(self.manifest_path, "rb") as f:
            raw = f.read()
        got = sha256_bytes(raw)
        if got != self.manifest_sha256:
            refuse(f"the manifest hashes to {got}, MANAGER named {self.manifest_sha256}")
        rows, probes = [], []
        for i, line in enumerate(raw.decode("utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except ValueError:
                refuse(f"manifest line {i + 1} is not JSON")
            k = str(o.get("kind", ""))
            if k == "run_header":
                self.headers.append(o)
            elif k.startswith("probe"):
                probes.append(o)
            else:
                rows.append(o)
        if not self.headers:
            refuse("the manifest has no run_header row")
        for h in self.headers:
            if h.get("list_sha256") != self.namedays_sha256:
                refuse(f"a run_header cites list sha256 {h.get('list_sha256')}, not namedays_r1.csv's {self.namedays_sha256}")
        text = "\n".join(json.dumps(p, sort_keys=True) for p in probes)
        probe_sha = None
        if self.probe_log:
            with open(self.probe_log, "rb") as f:
                pb = f.read()
            probe_sha = sha256_bytes(pb)
            text += "\n" + pb.decode("utf-8", "replace")
        lines = text.splitlines()
        for what in ("1Min", "quotes"):
            if not any(what.lower() in ln.lower() and "SAME MAPPING" in ln for ln in lines):
                refuse(f"no FB/META probe line with '{what}' and 'SAME MAPPING' in the manifest or the probe log")
        by = {}
        for o in rows:
            for c in ("kind", "symbol", "date", "status"):
                if c not in o:
                    refuse(f"a manifest request row has no '{c}'")
            if TS(o["date"]) >= CUT:
                refuse(f"a request dated {o['date']} (on or after {CUT:%Y-%m-%d}) is in the photograph")
            key = (o["kind"], o["symbol"], o["date"], o.get("mark"))
            by.setdefault(key, []).append(o)
        # one row per PAGE (a quotes window spans pages; each row names the request's one file): the request's status
        # is its last row's; its served rows must name one file and one feed (a refused sip row then an iex row is the
        # s.11 403 fallback and passes)
        final, paged = {}, 0
        for key, lst in by.items():
            served = [o for o in lst if int(o["status"]) == 200]
            if len({o.get("file") for o in served}) > 1 or len({_feed_of(o.get("url")) for o in served}) > 1:
                refuse(f"request {key} has served rows naming several files or feeds")
            final[key] = lst[-1]
            paged += int(len(lst) > 1)
        self.rows = final
        files, nbytes, multi, unpinned = 0, 0, 0, {}
        if full:
            by_file = {}
            for o in rows:
                if int(o["status"]) == 200 and o.get("file"):
                    by_file.setdefault(o["file"], []).append(o)
            for fname, lst in by_file.items():
                p = self._file(fname)
                if not os.path.exists(p):
                    refuse(f"photographed file missing: {p}")
                size = os.path.getsize(p)
                # only a one-page bars file is the served body byte for byte; the pull always re-serialises quotes
                # and marks files (a one-page quotes file can match its page's size by chance: NRXP 2021-07-23 close)
                if len(lst) == 1 and lst[0]["kind"] == "bars" and int(lst[0].get("bytes", -1)) == size:
                    if sha256_file(p) != lst[0].get("sha256"):
                        refuse(f"{p}: sha256 differs from the manifest")
                elif any(o["kind"] == "bars" for o in lst):
                    refuse(f"{p}: a bars file the manifest does not pin byte for byte ({size} bytes, rows "
                           f"{[o.get('bytes') for o in lst]})")
                else:
                    # quotes / marks: the rows pin each PAGE, the file is the wrapper's own serialisation of them; its
                    # sha256 goes into the photograph's digest, which every later step must reproduce
                    unpinned[os.path.relpath(p, self.root).replace("\\", "/")] = sha256_file(p)
                files += 1
                nbytes += size
                multi += int(len(lst) > 1)
        status = {}
        feeds = {}
        for key, o in final.items():
            st = int(o["status"])
            lab = "200" if st == 200 else ("403" if st == 403 else "other")
            status.setdefault(key[0], {}).setdefault(lab, 0)
            status[key[0]][lab] += 1
            fd = _feed_of(o.get("url")) or "none"
            feeds.setdefault(key[0], {}).setdefault(fd, 0)
            feeds[key[0]][fd] += 1
        digest = (sha256_bytes("".join(f"{v}  {k}\n" for k, v in sorted(unpinned.items())).encode("utf-8"))
                  if full else None)
        self.verified = {"manifest": self.manifest_path, "manifest_sha256": got, "probe_log_sha256": probe_sha,
                         "run_headers": len(self.headers), "requests": len(final), "request_rows": len(rows),
                         "requests_with_several_page_rows": paged, "files_verified": files, "bytes_verified": nbytes,
                         "files_named_by_several_rows": multi, "files_pinned_by_row": files - len(unpinned),
                         "files_unpinned_hashed": len(unpinned), "unpinned_digest": digest,
                         "status_by_kind": status, "feed_by_kind": feeds, "full": bool(full)}
        return self.verified

    def stamp(self):
        return {"manifest_sha256": self.manifest_sha256, "namedays_sha256": self.namedays_sha256,
                "verified": self.verified}

    def _load(self, kind, symbol, date, field, mark=None):
        key = (kind, symbol, f"{TS(date):%Y-%m-%d}", mark)
        o = self.rows.get(key)
        if o is None:
            return "missing", None, None
        st = int(o["status"])
        if st == 403:
            return "refused", _feed_of(o.get("url")), None
        if st != 200:
            return "missing", _feed_of(o.get("url")), None
        with open(self._file(o["file"]), "rb") as f:
            obj = json.loads(f.read().decode("utf-8"))
        return "ok", _feed_of(o.get("url")), parse_pages(obj, field, symbol, where=f"{kind} {symbol} {key[2]}")

    def bars(self, symbol, date):
        st, feed, rec = self._load("bars", symbol, date, "bars")
        if st != "ok":
            return Bars1m(status=st, feed=feed, df=None, dq=None)
        df, dq = frame_1m(rec, date, where=f"bars {symbol} {TS(date):%Y-%m-%d}")
        return Bars1m(status="ok" if len(df) else "empty", feed=feed, df=df, dq=dq)

    def quotes(self, symbol, date, kind="quotes_pmfail_am"):
        st, feed, rec = self._load(kind, symbol, date, "quotes")
        if st != "ok":
            return Quotes(status=st, feed=feed, df=None)
        df = frame_quotes(rec, where=f"{kind} {symbol} {TS(date):%Y-%m-%d}")
        return Quotes(status="ok" if len(df) else "empty", feed=feed, df=df)

    def marks(self, symbol, date, marks=("09:45", "10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00"),
              kind="quotes_runner2_mark"):
        """RUNNER2's marks -> {mark: Quotes}; a file shared by several marks must be a {mark: pages} map"""
        out = {}
        for mk in marks:
            key = (kind, symbol, f"{TS(date):%Y-%m-%d}", mk)
            o = self.rows.get(key)
            if o is None:
                out[mk] = Quotes(status="missing", feed=None, df=None)
                continue
            st = int(o["status"])
            if st != 200:
                out[mk] = Quotes(status="refused" if st == 403 else "missing", feed=_feed_of(o.get("url")), df=None)
                continue
            with open(self._file(o["file"]), "rb") as f:
                obj = json.loads(f.read().decode("utf-8"))
            if isinstance(obj, dict) and "marks" in obj and isinstance(obj["marks"], dict):
                obj = obj["marks"]
            if isinstance(obj, dict) and mk in obj:
                obj = obj[mk]
            elif isinstance(obj, dict) and any(k in obj for k in marks):
                refuse(f"{kind} {symbol} {key[2]}: the marks file has no entry for {mk}")
            rec = parse_pages(obj, "quotes", symbol, where=f"{kind} {symbol} {key[2]} {mk}")
            df = frame_quotes(rec)
            out[mk] = Quotes(status="ok" if len(df) else "empty", feed=_feed_of(o.get("url")), df=df)
        return out


# ================================================================== one name-day's 1m bars (dense over 04:00 .. 15:59)
class Day:
    def __init__(self, df, date):
        self.date = TS(date).normalize()
        self.half = f"{self.date:%Y-%m-%d}" in EARLY_CLOSE_DATES
        self.rth1 = RTH1_HALF if self.half else RTH1
        A = {k: np.full(NM, np.nan) for k in ("o", "h", "l", "c", "v", "vw")}
        if df is not None and len(df):
            m = df["m"].to_numpy(np.int64)
            ok = (m >= PRE0) & (m < self.rth1)                  # a half day's bars from 13:00 on belong to no session
            idx = m[ok] - PRE0
            for k in A:
                if k in df.columns:
                    A[k][idx] = df[k].to_numpy(float)[ok]
        self.o, self.h, self.l, self.c, self.v, self.vw = (A[k] for k in ("o", "h", "l", "c", "v", "vw"))
        self.pres = np.flatnonzero(np.isfinite(self.o))

    def first_in(self, m0, m1):
        a = int(np.searchsorted(self.pres, m0 - PRE0))
        if a < len(self.pres) and self.pres[a] < m1 - PRE0:
            return int(self.pres[a]) + PRE0
        return None

    def gap_before(self, m):
        """consecutive absent REGULAR minutes immediately before minute m (a run from 09:30 counts)"""
        a = int(np.searchsorted(self.pres, m - PRE0))
        prev = int(self.pres[a - 1]) + PRE0 if a > 0 else None
        if prev is None or prev < RTH0:
            return m - RTH0
        return m - prev - 1

    def is_resume(self, m, k=HALT_K):
        return self.gap_before(m) >= k

    def hmax(self, m0, m1):
        seg = self.h[max(m0 - PRE0, 0):max(m1 - PRE0, 0)]
        return float(np.nanmax(seg)) if np.isfinite(seg).any() else None

    def lmin(self, m0, m1):
        seg = self.l[max(m0 - PRE0, 0):max(m1 - PRE0, 0)]
        return float(np.nanmin(seg)) if np.isfinite(seg).any() else None

    def bar5(self, k):
        """regular 5m bar k (anchored 09:30) from its present 1m bars; None if it has none"""
        s = RTH0 + 5 * k
        e = min(s + 5, self.rth1)
        if s >= self.rth1:
            return None
        seg = np.arange(s - PRE0, e - PRE0)
        p = seg[np.isfinite(self.o[seg])]
        if not len(p):
            return None
        return SimpleNamespace(k=k, start=s, end=s + 5, o=float(self.o[p[0]]), h=float(np.max(self.h[p])),
                               l=float(np.min(self.l[p])), c=float(self.c[p[-1]]), v=float(np.sum(self.v[p])),
                               last_m=int(p[-1]) + PRE0)

    def halt_runs(self, k=HALT_K):
        """[(start minute, length, resume minute or None)] of runs >= k absent regular minutes (from 09:30 / to the close)"""
        r0, r1 = RTH0 - PRE0, self.rth1 - PRE0
        absent = ~np.isfinite(self.o[r0:r1])
        if not absent.any():
            return []
        d = np.diff(np.concatenate([[0], absent.astype(np.int8), [0]]))
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        out = []
        for s, e in zip(starts, ends):
            if e - s >= k:
                res = self.first_in(e + RTH0, self.rth1)
                out.append((int(s) + RTH0, int(e - s), res))
        return out

    def exit_window_empty(self):
        return self.first_in(self.rth1 - EXIT_WIN, self.rth1) is None

    def dollar_vol(self, m):
        i = m - PRE0
        p = self.vw[i] if np.isfinite(self.vw[i]) and self.vw[i] > 0 else (self.h[i] + self.l[i] + self.c[i]) / 3.0
        return float(p * self.v[i])

    def close_ffill(self):
        c = pd.Series(self.c).ffill().to_numpy()
        return c


# ================================================================== the PMFAIL signal (s.5)
def pm_signal(day, P, k_halt=HALT_K):
    s = SimpleNamespace(skip=None, pmh=None, k=None, end=None, c5=None, m_entry=None, E=None, S1=None, S2=None, hod=None,
                        ssr_same=None, ssr_0400=None)
    pre = day.h[:RTH0 - PRE0]
    if not np.isfinite(pre).any():
        s.skip = "no_pmh"
        return s
    pmh = float(np.nanmax(pre))
    s.pmh = pmh
    for k in range(WIN_K0, WIN_K1 + 1):
        b = day.bar5(k)
        if b is None:
            continue
        mh = day.hmax(RTH0, b.end)
        if b.c < pmh - TOL and mh is not None and mh > pmh + TOL:
            s.k, s.end, s.c5 = k, b.end, b.c
            break
    if s.k is None:
        s.skip = "no_signal"
        return s
    lo = day.lmin(RTH0, s.end)
    s.ssr_same = bool(lo is not None and lo <= SSR_FRAC * P + TOL)
    lo4 = day.lmin(PRE0, s.end)
    s.ssr_0400 = bool(lo4 is not None and lo4 <= SSR_FRAC * P + TOL)
    s.hod = max(pmh, day.hmax(RTH0, s.end))
    s.S1 = s.hod + CENT
    if s.ssr_same:
        s.skip = "ssr_active"
        return s
    me = day.first_in(s.end, s.end + 5)
    if me is None:
        s.skip = "no_fill_bar"
        return s
    s.m_entry, s.E = me, float(day.o[me - PRE0])
    if day.is_resume(me, k_halt):
        s.skip = "resume_bar"
        return s
    if s.E >= s.S1 - TOL:
        s.skip = "entry_ge_S1"
        return s
    s.S2 = ceil_cent(s.E + 1.5 * (s.S1 - s.E))
    return s


SKIPS = ("no_bars", "no_pmh", "no_signal", "ssr_active", "no_fill_bar", "resume_bar", "entry_ge_S1")


# ================================================================== the stop walk (s.5; shared with RUNNER2)
def walk(day, m_entry, stop, side, reading, first_bar_high_only=False):
    """-> SimpleNamespace(px, m, reason, last_close). side -1 short / +1 long. Stops are judged from the entry bar through
    the last bar starting before the exit window; reason stop_open | stop_level | stop_next | exit_1555 | halted_close
    (px None; last_close = the last pre-halt 1m close)."""
    pres = day.pres
    i0 = int(np.searchsorted(pres, m_entry - PRE0))
    i1 = int(np.searchsorted(pres, day.rth1 - EXIT_WIN - PRE0))
    i2 = int(np.searchsorted(pres, day.rth1 - PRE0))
    seg = pres[i0:i1]
    if len(seg):
        if side < 0:
            ho = day.o[seg] >= stop - TOL
            hh = day.h[seg] >= stop - TOL
        else:
            ho = day.o[seg] <= stop + TOL
            hh = day.l[seg] <= stop + TOL
        if first_bar_high_only and seg[0] == m_entry - PRE0:
            ho[0] = False
        hit = ho | hh
        if hit.any():
            j = int(np.argmax(hit))
            mm = int(seg[j])
            if ho[j]:
                return SimpleNamespace(px=float(day.o[mm]), m=mm + PRE0, reason="stop_open", last_close=None)
            if reading == "L":
                return SimpleNamespace(px=float(stop), m=mm + PRE0, reason="stop_level", last_close=None)
            nxt = pres[i0 + j + 1:i2]
            if len(nxt):
                return SimpleNamespace(px=float(day.o[nxt[0]]), m=int(nxt[0]) + PRE0, reason="stop_next", last_close=None)
            return SimpleNamespace(px=None, m=mm + PRE0, reason="halted_close", last_close=float(day.c[mm]))
    win = pres[i1:i2]
    if len(win):
        return SimpleNamespace(px=float(day.o[win[0]]), m=int(win[0]) + PRE0, reason="exit_1555", last_close=None)
    before = pres[:i1]
    before = before[before >= RTH0 - PRE0]
    lc = float(day.c[before[-1]]) if len(before) else None
    return SimpleNamespace(px=None, m=None, reason="halted_close", last_close=lc)


def halted_close_exit(ev, stop, last_close, side):
    """s.5 'Halted into the close' -> (px, exit session, nights, priced_by). ev.nxt = [(date, raw open or NaN, flagged)]
    for the market sessions after t in the cut calendar (at most 10); ev.t_next = t's next market session or None."""
    found, flagged = None, False
    for j, (d, o, fl) in enumerate(ev.nxt[:10], start=1):
        flagged = flagged or bool(fl)
        if o is not None and np.isfinite(o):
            found = (j, d, float(o))
            break
    if found is not None and not flagged:
        return found[2], TS(found[1]), found[0], "next_open"
    if found is not None:
        how = "stress_flag"
    elif len(ev.nxt) < 10:
        how = "stress_cut"
    else:
        how = "stress_no_bar"
    if stop is None or not np.isfinite(stop):
        px = float(last_close)
    else:
        px = max(float(stop), float(last_close)) if side < 0 else min(float(stop), float(last_close))
    if ev.t_next is not None and TS(ev.t_next) < CUT:
        return px, TS(ev.t_next), 1, how
    return px, TS(ev.date), 0, how


def split_cap(opens, sc_flags, m_flags, X, side):
    """TTM #55 / #56 (registered, not a leak): a halted-into-close exit is stress-priced when a split flag (S1 / calendar /
    test M) sits on a session up to the first served open of its 10-session window. -> None when no open is served; else
    the first open, whether a flag fired through it, whether test M ALONE fired, and whether that open would have cost
    the trade more than its stress price X (the cap TTM asked to count)."""
    sc = m = False
    for o, f_sc, f_m in zip(opens, sc_flags, m_flags):
        sc, m = sc or bool(f_sc), m or bool(f_m)
        if o is not None and np.isfinite(o) and o > 0:
            return {"open": float(o), "flagged": bool(sc or m), "m_only": bool(m and not sc),
                    "worse": bool(o > X if side < 0 else o < X), "gap": float(o - X)}
    return None


def split_cap_report(items):
    """items: (split_cap result or None, priced as a split, shares) per halted-into-close trade -> the counts TTM asked for"""
    out = {"halted_close": 0, "priced_as_split": 0, "split_with_open_served": 0, "split_by_test_M_alone": 0,
           "open_worse_than_stress_price": 0, "worse_and_test_M_alone": 0, "usd_capped_at_judged_shares": 0.0}
    for res, as_split, sh in items:
        out["halted_close"] += 1
        if not as_split:
            continue
        out["priced_as_split"] += 1
        if res is None or not res["flagged"]:
            continue
        out["split_with_open_served"] += 1
        out["split_by_test_M_alone"] += int(res["m_only"])
        if res["worse"]:
            out["open_worse_than_stress_price"] += 1
            out["worse_and_test_M_alone"] += int(res["m_only"])
            out["usd_capped_at_judged_shares"] += float(sh) * abs(res["gap"])
    out["usd_capped_at_judged_shares"] = round(out["usd_capped_at_judged_shares"], 2)
    return out


def resolve(day, ev, m_entry, E, stop, side, reading, first_bar_high_only=False):
    ex = walk(day, m_entry, stop, side, reading, first_bar_high_only)
    if ex.reason != "halted_close":
        return SimpleNamespace(E=float(E), X=ex.px, m_entry=m_entry, m_exit=ex.m, reason=ex.reason, nights=0,
                               book_date=TS(ev.date), priced_by="intraday", halted=False, stop=stop, side=side)
    px, bd, nights, how = halted_close_exit(ev, stop, ex.last_close, side)
    return SimpleNamespace(E=float(E), X=px, m_entry=m_entry, m_exit=ex.m, reason="halted_close", nights=nights,
                           book_date=bd, priced_by=how, halted=True, stop=stop, side=side)


# ================================================================== costs, size, N* (s.6)
def side_cost(px, h, stress=False):
    px = np.asarray(px, float)
    return np.maximum(np.asarray(h, float) * px, HALF_TICK) + COMM + (STRESS_ADD if stress else 0.0)


def unit_parts(E, X, side, nights, h50, h75, locate_on=True):
    """per-share gross, primary cost, stress cost, primary locate, stress locate (locate on shorts only)"""
    E, X, side, nights = (np.asarray(a, float) for a in (E, X, side, nights))
    gross = np.where(side < 0, E - X, X - E)
    cp = side_cost(E, h50) + side_cost(X, h50)
    cs = side_cost(E, h75, True) + side_cost(X, h75, True)
    on = (side < 0) & bool(locate_on) if np.ndim(locate_on) == 0 else (side < 0) & np.asarray(locate_on, bool)
    lp = np.where(on, LOCATE * E * (1.0 + nights), 0.0)
    ls = np.where(on, LOCATE_STRESS * E * (1.0 + nights), 0.0)
    return gross, cp, cs, lp, ls


def shares_at(N, adv, E):
    return np.floor(np.minimum(float(N), CAP_FRAC * np.asarray(adv, float)) / np.asarray(E, float) + 1e-9)


def maxdd_of(d):
    cum = np.cumsum(np.asarray(d, float))
    if not len(cum):
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    return float((peak - cum).max())


def solve_nstar(E, adv, unit, sess, grid=GRID, target=DD_TARGET, chunk=50):
    """s.6: the smallest N on the grid whose maxDD (peak from $0) >= target; the last grid point if none. A SCAN, never a
    bisection: maxDD(N) is not monotone once the 1% cap binds. -> (N*, shares, maxDD at N*)"""
    E, adv, unit, sess = (np.asarray(a) for a in (E, adv, unit, sess))
    if not len(E):
        return float(grid[-1]), np.zeros(0), 0.0
    us, inv = np.unique(sess, return_inverse=True)
    cap = CAP_FRAC * adv.astype(float)
    last = None
    for c0 in range(0, len(grid), chunk):
        g = grid[c0:c0 + chunk]
        sh = np.floor(np.minimum(g[None, :], cap[:, None]) / E.astype(float)[:, None] + 1e-9)
        pnl = sh * unit.astype(float)[:, None]
        d = np.zeros((len(us), len(g)))
        np.add.at(d, inv, pnl)
        cum = np.cumsum(d, axis=0)
        peak = np.maximum.accumulate(np.vstack([np.zeros((1, len(g))), cum]), axis=0)[1:]
        dd = (peak - cum).max(axis=0)
        hit = np.flatnonzero(dd >= target - 1e-9)
        if hit.size:
            j = int(hit[0])
            return float(g[j]), sh[:, j], float(dd[j])
        last = (float(g[-1]), sh[:, -1], float(dd[-1]))
    return last


# ================================================================== statistics (s.6)
def roc30(net, dd):
    return 30.0 * (net / YEARS) / max(dd, DD_TARGET)


def tstat(d):
    d = np.asarray(d, float)
    if len(d) < 2:
        return float("nan")
    sd = d.std(ddof=1)
    return float(d.mean() / sd * math.sqrt(len(d))) if sd > 0 else float("nan")


def sortino(d):
    d = np.asarray(d, float)
    dn = math.sqrt(float(np.mean(np.minimum(d, 0.0) ** 2))) if len(d) else 0.0
    return float(d.mean() / dn * math.sqrt(252)) if dn > 0 else float("nan")


def pf_of(nets):
    nets = np.asarray(nets, float)
    w, l = nets[nets > 0].sum(), -nets[nets < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))


def r_sums(d, inR_cal, n_r=R_DAYS):
    """R-sum = the leg's daily P&L over R's days; without its 3 best R days = drop the 3 largest values there"""
    v = np.asarray(d, float)[inR_cal]
    v = np.concatenate([v, np.zeros(max(n_r - len(v), 0))])
    s = float(v.sum())
    ex3 = float(np.sort(v)[:-3].sum()) if len(v) > 3 else float("nan")
    return s, ex3


def series_stats(d, inR_cal):
    d = np.asarray(d, float)
    net, dd = float(d.sum()), maxdd_of(d)
    rs, rs3 = r_sums(d, inR_cal)
    return {"net": net, "maxdd": dd, "roc30": roc30(net, dd), "t": tstat(d), "sortino": sortino(d), "rsum": rs,
            "rsum_ex3": rs3}


def scale_free(E, unit, sess, n_cal):
    """the uncapped scale-free figure at $5,000: 30 x (net / years) / maxDD (undefined when maxDD = 0)"""
    sh = np.floor(N_SCALEFREE / np.asarray(E, float) + 1e-9)
    d = np.bincount(np.asarray(sess, np.int64), weights=sh * np.asarray(unit, float), minlength=n_cal)
    dd = maxdd_of(d)
    return float(30.0 * (d.sum() / YEARS) / dd) if dd > 0 else float("nan")


def r11_stats(x, dates):
    """tools/rocfrontier/r11_risk.py stats (unified convention: years from the index, peak from $0) - ROC and Sortino"""
    x = np.asarray(x, float)
    dd = maxdd_of(x)
    yrs = (TS(dates[-1]) - TS(dates[0])).days / 365.25
    dn = math.sqrt(float(np.mean(np.minimum(x, 0.0) ** 2)))
    return {"net": float(x.sum()), "max_dd": dd, "years": yrs,
            "roc": 30.0 * (x.sum() / yrs) / dd if dd > 0 else float("nan"),
            "sort": float(x.mean() / dn * math.sqrt(252)) if dn > 0 else float("nan")}


def years_positive(d_cal, wf, book_dates):
    """bar 4: July-June years (2016-17 .. 2024-25) with net > 0 on the booked daily series; a year with no trades is not
    positive. -> (count, net by year, trades by year)"""
    yi_cal = np.array([wf_year_index(x) for x in wf])
    d_cal = np.asarray(d_cal, float)
    net = {WF_YEARS[i]: float(d_cal[yi_cal == i].sum()) for i in range(len(WF_YEARS))}
    byi = [wf_year_index(b) for b in book_dates]
    trades = {WF_YEARS[i]: int(sum(1 for y in byi if y == i)) for i in range(len(WF_YEARS))}
    return int(sum(1 for y in WF_YEARS if trades[y] > 0 and net[y] > 0)), net, trades


def verdict(bars, count_key):
    """PASS = every bar holds; RESEARCH ROW = only the count bar misses; FAIL = anything else"""
    miss = [k for k, v in bars.items() if not v]
    if not miss:
        return "PASS"
    if miss == [count_key]:
        return "RESEARCH ROW"
    return "FAIL"


def count_gate(per_year):
    n = int(sum(per_year.values()))
    return {"n": n, "years": YEARS, "n_per_year": n / YEARS, "mean_ge_50": bool(n / YEARS >= COUNT_MEAN),
            "n_ge_100": bool(n >= COUNT_MIN), "pass": bool(n / YEARS >= COUNT_MEAN and n >= COUNT_MIN),
            "per_year": {y: int(per_year.get(y, 0)) for y in WF_YEARS},
            "thin_years_under_25": [y for y in WF_YEARS if per_year.get(y, 0) < THIN]}


def pcts(x):
    x = np.asarray(x, float)
    return {f"p{p:g}": float(np.percentile(x, p, method=PCT_METHOD)) for p in PCTS}


# ================================================================== spreads (s.6; quotes or priors)
def et_ns(date, hh, mm, ss=0):
    return TS(f"{TS(date):%Y-%m-%d} {hh:02d}:{mm:02d}:{ss:02d}", tz=ET).tz_convert("UTC").value


def spread_window(q, date, t0, t1):
    """median over whole seconds t0..t1 (ET, inclusive) of the NBBO in force (the last quote at or before the second);
    seconds with no quote yet, bid <= 0 or ask <= bid are skipped. None when no second is valid."""
    if q is None or not len(q):
        return None
    s0 = et_ns(date, *t0)
    s1 = et_ns(date, *t1)
    secs = s0 + np.arange((s1 - s0) // 1_000_000_000 + 1, dtype=np.int64) * 1_000_000_000
    t = q["t_ns"].to_numpy(np.int64)
    j = np.searchsorted(t, secs, side="right") - 1
    j = j[j >= 0]
    if not len(j):
        return None
    bp, ap = q["bp"].to_numpy(float)[j], q["ap"].to_numpy(float)[j]
    ok = (bp > 0) & (ap > bp)
    if not ok.any():
        return None
    return float(np.median((ap[ok] - bp[ok]) / (ap[ok] + bp[ok])))


AM_WIN, CLOSE_WIN = ((9, 40, 0), (11, 5, 0)), ((15, 50, 0), (15, 59, 59))


def bucket_spreads(values, refused):
    """values: {bucket: [name-day values]}; refused: {bucket: n refused name-days} -> each takes the prior h50 (counted
    toward n). A bucket with fewer than 20 values uses the priors (h75 = 2 x h50)."""
    out = {}
    for b in BUCKETS:
        v = list(values.get(b, [])) + [H50_PRIOR[b]] * int(refused.get(b, 0))
        if len(v) < BUCKET_MIN:
            out[b] = {"h50": H50_PRIOR[b], "h75": 2.0 * H50_PRIOR[b], "n": len(v), "source": "priors",
                      "refused_take_prior": int(refused.get(b, 0))}
        else:
            out[b] = {"h50": float(np.percentile(v, 50, method=PCT_METHOD)),
                      "h75": float(np.percentile(v, 75, method=PCT_METHOD)), "n": len(v), "source": "quotes",
                      "refused_take_prior": int(refused.get(b, 0))}
    return out


# ================================================================== inputs (real data; tests build the same namespace)
def import_builder():
    try:
        return importlib.import_module("disc_gapper_namedays")
    except ImportError as e:
        refuse(f"tools/disc_gapper_namedays.py is not importable ({e}) - the worktree must sit on a main with b9107d45")


def verify_extra_inputs():
    p = input_paths()
    got = {}
    for name, want in INPUT_SHAS.items():
        if not os.path.exists(p[name]):
            refuse(f"input not on file: {p[name]}")
        got[name] = sha256_file(p[name])
        if got[name] != want:
            refuse(f"{name} hashes to {got[name]}, the prereg registers {want}")
    with open(p["namedays_r1.csv"], "rb") as f:
        nd = f.read()
    got["namedays_r1.csv"] = sha256_bytes(nd)
    if got["namedays_r1.csv"] != NAMEDAYS_SHA:
        refuse(f"namedays_r1.csv hashes to {got['namedays_r1.csv']}, the posted list is {NAMEDAYS_SHA}")
    with open(p["namedays_r1.sha256"], encoding="utf-8") as f:
        line = f.read().strip()
    if line != f"{NAMEDAYS_SHA}  namedays_r1.csv":
        refuse(f"namedays_r1.sha256 reads '{line}'")
    return got


def _grid(df, days, syms, cols):
    t = days.get_indexer(pd.DatetimeIndex(pd.to_datetime(df["date"])))
    s = pd.Index(syms).get_indexer(df["symbol"].astype(str))
    ok = (t >= 0) & (s >= 0)
    t, s = t[ok], s[ok]
    key = t.astype(np.int64) * len(syms) + s
    last = ~pd.Series(key).duplicated(keep="last").to_numpy()
    out = {}
    for c in cols:
        a = np.full((len(days), len(syms)), np.nan)
        a[t[last], s[last]] = df[c].to_numpy(float)[ok][last]
        out[c] = a
    return out


def _shift(a, k):
    out = np.full(a.shape, np.nan if a.dtype.kind == "f" else False, dtype=a.dtype)
    if k < a.shape[0]:
        out[k:] = a[:a.shape[0] - k]
    return out


def build_context(raw, split, days, syms_full, masks, calrev_full, last_bar, assets, events_idx, roles):
    """Per listed name-day context from the cut daily cache (pure: frames in).
    raw: symbol, date, o, l, c, v of the LISTED symbols; split: symbol, date, o, c; days: the cut session calendar;
    syms_full / masks / calrev_full: the builder's grid; last_bar: {symbol: last daily-bar date, UNCUT};
    assets: assets.csv frame; events_idx: [(ti, symbol)]; roles: matching role labels. -> list of SimpleNamespace."""
    syms = sorted({s for _, s in events_idx})
    T = len(days)
    g = _grid(raw, days, syms, ("o", "l", "c", "v"))
    gs = _grid(split, days, syms, ("o", "c"))
    O, C, V = g["o"], g["c"], g["v"]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = (O / gs["o"]) / _shift(C / gs["c"], 1)
        known = np.isfinite(ratio) & (ratio > 0)
        S1sub = known & (np.abs(ratio - 1.0) > 0.005)
        S1rev = known & (ratio > 1.005)
        F = C / gs["c"]
    cols = pd.Index(syms_full).get_indexer(syms)
    if (cols < 0).any():
        refuse("a listed symbol is not on the builder's grid")
    if not np.array_equal(S1sub, masks["S1"][:, cols]):
        refuse("the recomputed S1 differs from the builder's S1 mask (F / F' parity)")
    flag = (masks["S1"] | masks["CAL"] | masks["M"])[:, cols]
    flag_sc = (masks["S1"] | masks["CAL"])[:, cols]
    Msub = masks["M"][:, cols]
    CALrev = calrev_full[:, cols]
    a = assets.copy()
    a["symbol"] = a["symbol"].astype(str)
    a_by = {s: grp for s, grp in a.groupby("symbol")}
    sidx = {s: j for j, s in enumerate(syms)}
    out = []
    for (ti, sym), role in zip(events_idx, roles):
        j = sidx[sym]
        t = days[ti]
        P = C[ti - 1, j] if ti >= 1 else np.nan
        w = C[max(ti - 20, 0):ti, j] * V[max(ti - 20, 0):ti, j]
        adv = float(w.mean()) if ti >= 20 and np.isfinite(w).all() else float("nan")
        nxt = [(days[u], float(O[u, j]) if np.isfinite(O[u, j]) else float("nan"), bool(flag[u, j]))
               for u in range(ti + 1, min(ti + 11, T))]
        nxt_sc = [bool(flag_sc[u, j]) for u in range(ti + 1, min(ti + 11, T))]
        nxt_m = [bool(Msub[u, j]) for u in range(ti + 1, min(ti + 11, T))]
        lo_i = int(np.searchsorted(days, t - pd.Timedelta(days=REVSPLIT_DAYS)))
        src = {"s1": bool(S1rev[lo_i:ti, j].any()), "cal": bool(CALrev[lo_i:ti, j].any()), "m": bool(Msub[lo_i:ti, j].any())}
        grp = a_by.get(sym)
        if grp is None:
            asx = {"in_assets": False, "inactive": None, "mixed": None, "shortable_active": None, "reused": False}
        else:
            stt = grp["status"].astype(str).str.lower()
            allact, allin = bool((stt == "active").all()), bool((stt == "inactive").all())
            sh = grp["shortable"].astype(str).str.lower() == "true"
            asx = {"in_assets": True, "inactive": allin, "mixed": not (allact or allin),
                   "shortable_active": (bool(sh.all()) if allact else None), "reused": bool(len(grp) > 1)}
        lb = last_bar.get(sym)
        ev = SimpleNamespace(symbol=sym, date=t, ti=ti, yi=wf_year_index(t), role=role,
                             wf_year=WF_YEARS[wf_year_index(t)] if wf_year_index(t) >= 0 else None,
                             bucket=None if not np.isfinite(P) else ("lt5" if P < 5.0 else "5to20"),
                             P=float(P), adv=adv, O_day=float(O[ti, j]), V_day=float(V[ti, j]),
                             nxt=nxt, nxt_sc=nxt_sc, nxt_m=nxt_m, t_next=days[ti + 1] if ti + 1 < T else None,
                             flags={"revsplit60": any(src.values()), "rs_sources": src,
                                    "delisted": bool(lb is not None and TS(lb) < DELIST_BEFORE),
                                    "s3p": bool(masks["s3p"][ti, cols[j]]), "s3v": bool(masks["s3v"][ti, cols[j]]),
                                    **asx},
                             F_prev=float(F[ti - 1, j]) if ti >= 1 else float("nan"), quotes=False)
        out.append(ev)
    return out, {"S1_parity_columns": int(len(syms)), "F": F, "days": days, "syms": syms}


def lowfloat_buckets(events, asfiled_path, frames_path, Fctx):
    """LOWFLOAT (report): dei EntityCommonStockSharesOutstanding (else us-gaap CommonStockSharesOutstanding), latest
    `filed` strictly before t; as-filed file first, frames by CIK otherwise; x F(filed) / F(t) (F(t) on the session before t)"""
    want = ("dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding")

    def _read(path, cols):
        df = pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False)[cols]
        df = df[df["concept"].isin(want) & (df["filed"].str.len() > 0) & (df["val"].str.len() > 0)]
        return df.assign(filed=pd.to_datetime(df["filed"], errors="coerce"), val=pd.to_numeric(df["val"], errors="coerce")) \
                 .dropna(subset=["filed", "val"])

    def _cik(x):
        x = str(x).strip()
        return str(int(x)) if x.isdigit() else x
    af = _read(asfiled_path, ["cik", "symbols", "concept", "val", "filed"])
    fr = _read(frames_path, ["concept", "cik", "val", "filed", "ticker_now"])
    by_sym, cik_of = {}, {}
    for cik, syms_s, con, val, filed in af.itertuples(index=False, name=None):
        for s in str(syms_s).replace(";", ",").replace("|", ",").replace(" ", ",").split(","):
            s = s.strip().upper()
            if s:
                by_sym.setdefault(s, []).append((con, TS(filed), float(val)))
                cik_of.setdefault(s, _cik(cik))
    by_cik = {}
    for con, cik, val, filed, tick in fr.itertuples(index=False, name=None):
        k = _cik(cik)
        by_cik.setdefault(k, []).append((con, TS(filed), float(val)))
        if tick:
            cik_of.setdefault(str(tick).strip().upper(), k)
    days, syms, F = Fctx["days"], Fctx["syms"], Fctx["F"]
    sidx = {s: j for j, s in enumerate(syms)}
    rebased_none = 0
    for ev in events:
        facts = by_sym.get(ev.symbol, [])
        pick = _latest(facts, ev.date, want)
        if pick is None:
            pick = _latest(by_cik.get(cik_of.get(ev.symbol, ""), []), ev.date, want)
        if pick is None:
            ev.flags["lowfloat"] = "unknown"
            continue
        filed, val = pick
        fi = int(np.searchsorted(days, filed, side="right")) - 1
        j = sidx[ev.symbol]
        ff = F[fi, j] if fi >= 0 else np.nan
        fp = ev.F_prev
        if np.isfinite(ff) and np.isfinite(fp) and ff > 0 and fp > 0:
            factor = ff / fp
        else:
            factor, rebased_none = 1.0, rebased_none + 1       # no split bar to rebase by: as filed (counted)
        ev.flags["lowfloat"] = "lt20m" if val * factor < LOWFLOAT_CUT else "ge20m"
    return {"not_rebased": rebased_none}


def _latest(facts, t, order):
    for con in order:
        c = [(f, v) for k, f, v in facts if k == con and f < t]
        if c:
            return max(c, key=lambda x: x[0])
    return None


def load_book():
    """book463_daily.csv cut to [2016-07-01, 2025-06-30), its mtm; L = q19 line.csv `line`; R = residual_days in_R (762,
    = the union of a2.json's 45 line_episodes); #463's 28 episodes (episodes.csv, inclusive: 460 days). Parity asserted."""
    p = input_paths()
    bk = pd.read_csv(p["book463_daily.csv"], parse_dates=["date"])
    bk = bk[(bk["date"] >= WF0) & (bk["date"] < CUT)].reset_index(drop=True)
    idx = pd.DatetimeIndex(bk["date"])
    st = r11_stats(bk["mtm"].to_numpy(float), idx)
    if not (abs(st["roc"] - BOOK_FACTS[0]) < PARITY_TOL[0] and abs(st["sort"] - BOOK_FACTS[1]) < PARITY_TOL[1]):
        refuse(f"BOOK #463 parity: ROC {st['roc']:.4f} Sortino {st['sort']:.5f}, not {BOOK_FACTS}")
    ln = pd.read_csv(p["line.csv"], parse_dates=["date"])
    ln = ln[(ln["date"] >= WF0) & (ln["date"] < CUT)].reset_index(drop=True)
    if len(ln) != len(idx) or not (pd.DatetimeIndex(ln["date"]) == idx).all():
        refuse("line.csv dates are not #463's WF index row for row")
    L = ln["line"].to_numpy(float)
    sl = r11_stats(L, idx)
    if not (abs(sl["roc"] - LINE_FACTS[0]) < PARITY_TOL[0] and abs(sl["sort"] - LINE_FACTS[1]) < PARITY_TOL[1]):
        refuse(f"L parity: ROC {sl['roc']:.4f} Sortino {sl['sort']:.5f}, not {LINE_FACTS}")
    rd = pd.read_csv(p["residual_days.csv"], parse_dates=["date"])
    rd = rd[rd["date"] < CUT]
    if len(rd) != len(idx) or not (pd.DatetimeIndex(rd["date"]) == idx).all():
        refuse("residual_days.csv dates are not #463's WF index row for row")
    inR = rd["in_R"].astype(str).str.lower().map({"true": True, "false": False})
    if inR.isna().any() or int(inR.sum()) != R_DAYS:
        refuse(f"residual_days in_R sums to {inR.sum()}, not {R_DAYS}")
    inR = inR.to_numpy(bool)
    with open(p["a2.json"], encoding="utf-8") as f:
        a2 = json.load(f)
    r_eps = [(TS(s), TS(e)) for s, e in a2["line_episodes"]]
    u = np.zeros(len(idx), bool)
    for s, e in r_eps:
        u |= np.asarray((idx >= s) & (idx <= e))
    if len(r_eps) != R_EPIS or not np.array_equal(u, inR):
        refuse("a2.json line_episodes are not 45 inclusive ranges whose union is in_R")
    ep = pd.read_csv(p["episodes.csv"])
    dd_eps = [(TS(s), TS(e)) for s, e in zip(ep["start"], ep["end"])]
    ddm = np.zeros(len(idx), bool)
    for s, e in dd_eps:
        ddm |= np.asarray((idx >= s) & (idx <= e))
    if len(dd_eps) != DD_EPIS or int(ddm.sum()) != DD_DAYS:
        refuse(f"episodes.csv: {len(dd_eps)} episodes / {int(ddm.sum())} days, expected {DD_EPIS} / {DD_DAYS}")
    legs = {c: bk[c].to_numpy(float) for c in ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm")}
    return SimpleNamespace(index=idx, mtm=bk["mtm"].to_numpy(float), legs=legs, L=L, res_c=ln["res_c"].to_numpy(float),
                           inR=inR, r_eps=r_eps, dd_eps=dd_eps, dd_days=ddm,
                           years=(idx[-1] - idx[0]).days / 365.25,
                           parity={"book": {"roc": st["roc"], "sortino": st["sort"], "dd": st["max_dd"]},
                                   "L": {"roc": sl["roc"], "sortino": sl["sort"]},
                                   "line_book_vs_mtm_max_abs": float(np.abs(ln["book"].to_numpy(float) - bk["mtm"].to_numpy(float)).max())})


def siporb_top20(events):
    """share of event days in SIPORB's top 20 (r5_siporb's selection on its photographed cache); report only"""
    try:
        import r5_siporb as S5
        D = S5.Data(CUT)
        out = set()
        for d in sorted({ev.date for ev in events}):
            i = D.days.get_indexer([d])[0]
            if i >= 0:
                for s in D.syms[D.top20(i)]:
                    out.add((d, str(s)))
        return out, None
    except Exception as e:  # report only: a failure here is printed, never judged
        return None, f"{type(e).__name__}: {e}"


def load_inputs(verbose=True):
    """everything the modes need from the photographed daily cache and the book files (sha-checked; cut at read)"""
    say = print if verbose else (lambda *a, **k: None)
    preregs = check_preregs()
    NB = import_builder()
    info = NB.verify_inputs()
    extra = verify_extra_inputs()
    say("inputs verified: " + ", ".join(f"{k} {v[:12]}" for k, v in {**info["sha256"], **extra}.items()), flush=True)
    res = NB.build(NB.read_daily(NB.RAW_PATH, ("symbol", "date", "o", "l", "c", "v")),
                   NB.read_daily(NB.SPLIT_PATH, ("symbol", "date", "o", "c")), NB.read_calendar(NB.CA_PATH))
    if sha256_bytes(NB.csv_bytes(res.rows)) != NAMEDAYS_SHA:
        refuse("the builder's list today does not hash to the posted namedays_r1.csv")
    ca = NB.read_calendar(NB.CA_PATH)
    calrev, _ = NB.calendar_splits(ca[ca["type"].isin(["reverse_split", "name_change"])], res.days, res.syms)
    m = res.masks
    ti_r, si_r = np.nonzero(m["pm_reg"])
    ti_c, si_c = np.nonzero(m["pm_event"] & ~m["pm_reg"])
    ti_n, si_n = np.nonzero(m["nonevent"])
    idx = ([(int(t), res.syms[s]) for t, s in zip(ti_r, si_r)] + [(int(t), res.syms[s]) for t, s in zip(ti_c, si_c)]
           + [(int(t), res.syms[s]) for t, s in zip(ti_n, si_n)])
    roles = ["reg"] * len(ti_r) + ["carry"] * len(ti_c) + ["nonevent"] * len(ti_n)
    syms = sorted({s for _, s in idx})
    p = input_paths()
    raw = read_listed(NB.RAW_PATH, ["symbol", "date", "o", "l", "c", "v"], syms)
    split = read_listed(NB.SPLIT_PATH, ["symbol", "date", "o", "c"], syms)
    last_bar = last_bar_dates(NB.RAW_PATH, syms)
    assets = pd.read_csv(p["assets.csv"], dtype=str, keep_default_na=False)
    events, fctx = build_context(raw, split, res.days, res.syms, m, calrev, last_bar, assets, idx, roles)
    qmask = m["quotes_pmfail"]
    scol = {s: j for j, s in enumerate(res.syms)}
    for ev in events:
        ev.quotes = bool(ev.role == "reg" and qmask[ev.ti, scol[ev.symbol]])
        if ev.role == "reg" and not (ev.O_day / ev.P >= 1.20 - 1e-12):
            refuse(f"{ev.symbol} {ev.date:%Y-%m-%d}: O / P < 1.20 on a registered event (builder parity)")
    lf_info = lowfloat_buckets(events, p["shares_asfiled_wide.csv"], p["xbrl_shares_frames.csv"], fctx)
    top, top_err = siporb_top20([e for e in events if e.role == "reg"])
    wf = res.days[(res.days >= WF0) & (res.days <= WF1)]
    book = load_book()
    say(f"context: {len(events):,} name-days ({sum(e.role == 'reg' for e in events):,} registered); S1 parity on "
        f"{fctx['S1_parity_columns']:,} symbols; LOWFLOAT {lf_info}; book parity {book.parity}", flush=True)
    return SimpleNamespace(days=res.days, wf=wf, events=events, builder_counts={"pmfail": res.counts["pmfail"],
                           "test_m_calibration": res.counts["test_m_calibration"]}, m_keeps_volume=res.m_keeps_volume,
                           shas={**info["sha256"], **extra}, preregs=preregs, book=book, top20=top, top20_error=top_err,
                           lowfloat_info=lf_info)


def read_listed(path, cols, syms, cut=True):
    """a targeted pyarrow read of the photographed daily parquet: only `cols`, only the listed symbols, cut at read"""
    import pyarrow.parquet as pq
    flt = [("symbol", "in", list(syms))]
    if cut:
        flt.append(("date", "<", CUT.to_pydatetime()))
    df = pq.read_table(path, columns=list(cols), filters=flt).to_pandas()
    if cut and len(df) and not TS(df["date"].max()) < CUT:
        refuse(f"{os.path.basename(path)} not cut at {CUT:%Y-%m-%d}")
    return df


def last_bar_dates(path, syms):
    """condition 3's named exception: each listed symbol's last daily-bar DATE from the UNCUT cache (no price, no volume)"""
    unc = read_listed(path, ["symbol", "date"], syms, cut=False)
    return {str(k): TS(v) for k, v in unc.groupby(unc["symbol"].astype(str))["date"].max().items()}


# ================================================================== per-day scan (signals; trades only when asked)
def day_bars(photo, ev):
    b = photo.bars(ev.symbol, ev.date)
    day = Day(b.df, ev.date) if b.status in ("ok", "empty") else None
    return b, day


def null_candidates(day, ev, pmh):
    """the eligible window bars of one event day (exists; fill bar not a resume bar; not SSR-active; fill open < S1) with
    both cells' reading-L exits -> list of dicts"""
    out = []
    for k in range(WIN_K0, WIN_K1 + 1):
        b = day.bar5(k)
        if b is None:
            continue
        lo = day.lmin(RTH0, b.end)
        if lo is not None and lo <= SSR_FRAC * ev.P + TOL:
            continue
        me = day.first_in(b.end, b.end + 5)
        if me is None or day.is_resume(me, HALT_K):
            continue
        S1 = max(pmh, day.hmax(RTH0, b.end)) + CENT
        E = float(day.o[me - PRE0])
        if E >= S1 - TOL:
            continue
        S2 = ceil_cent(E + 1.5 * (S1 - E))
        t1 = resolve(day, ev, me, E, S1, -1, "L")
        t2 = resolve(day, ev, me, E, S2, -1, "L")
        out.append({"k": k, "E": E, "S1": S1, "S2": S2, "X1": t1.X, "n1": t1.nights, "b1": t1.book_date,
                    "X2": t2.X, "n2": t2.nights, "b2": t2.book_date})
    return out


def ssr_legal(day, ev, sig, cell):
    """Rule-201-legal fill (report): short limit at c5 + $0.01 posted at the signal end; filled at the limit only if a bar
    starting in [end, end + 5) has high >= limit + $0.01; then the cell's stop and exit (reading L)"""
    if sig.k is None:
        return None
    limit = sig.c5 + CENT
    mf = None
    for m in range(sig.end, sig.end + 5):
        i = m - PRE0
        if np.isfinite(day.o[i]) and day.h[i] >= limit + CENT - TOL:
            mf = m
            break
    if mf is None or limit >= sig.S1 - TOL:
        return None
    stop = sig.S1 if cell == "primary" else ceil_cent(limit + 1.5 * (sig.S1 - limit))
    return resolve(day, ev, mf, limit, stop, -1, "L", first_bar_high_only=True)


def pmbreak(day, ev, pmh):
    """continuation mirror (report): long at the next 1m open after the first window 5m close > PMH; stop = the regular
    low so far - $0.01; reading L; no locate"""
    if pmh is None:
        return None
    for k in range(WIN_K0, WIN_K1 + 1):
        b = day.bar5(k)
        if b is not None and b.c > pmh + TOL:
            me = day.first_in(b.end, b.end + 5)
            if me is None or day.is_resume(me, HALT_K):
                return None
            stop = day.lmin(RTH0, b.end) - CENT
            E = float(day.o[me - PRE0])
            if E <= stop + TOL:
                return None
            return resolve(day, ev, me, E, stop, +1, "L")
    return None


def openprint(day, ev):
    """OPENPRINT (report): short at the open of the first regular bar; no stop; 15:55 exit; SSR-at-open skipped"""
    m0 = day.first_in(RTH0, day.rth1)
    if m0 is None:
        return None, "no_bar"
    if day.l[m0 - PRE0] <= SSR_FRAC * ev.P + TOL:
        return None, "ssr_open"
    return resolve(day, ev, m0, float(day.o[m0 - PRE0]), float("inf"), -1, "L"), None


def scan_day(photo, ev, trades=False, null=False, paths=False, keep_day=False):
    b, day = day_bars(photo, ev)
    r = SimpleNamespace(ev=ev, status=b.status, feed=b.feed, dq=b.dq, day=None)
    if day is None:
        r.sig5 = r.sig4 = SimpleNamespace(skip="no_bars", k=None, pmh=None, ssr_same=None, ssr_0400=None)
        r.runs4 = r.runs5 = []
        r.exit_empty = None
        r.thin = None
        r.ssr_open = None
        r.open_match = None
        r.cands = []
        return r
    r.sig5 = pm_signal(day, ev.P, HALT_K)
    r.sig4 = pm_signal(day, ev.P, HALT_K4)
    r.runs4 = day.halt_runs(HALT_K4)
    r.runs5 = [x for x in r.runs4 if x[1] >= HALT_K]
    r.exit_empty = day.exit_window_empty()
    pv = float(np.nansum(day.v[:RTH0 - PRE0]))
    r.thin = (pv / ev.V_day) if ev.V_day and np.isfinite(ev.V_day) and ev.V_day > 0 else None
    i930 = RTH0 - PRE0
    r.ssr_open = None if not np.isfinite(day.l[i930]) else bool(day.l[i930] <= SSR_FRAC * ev.P + TOL)
    r.open_match = None if not np.isfinite(day.o[i930]) else bool(abs(day.o[i930] - ev.O_day) <= CENT + TOL)
    r.cands = []
    if keep_day:
        r.day = day
    if trades:
        r.day = day
        s = r.sig5
        r.t = {}
        if s.skip is None:
            for cell, stop in (("primary", s.S1), ("neighbour", s.S2)):
                for rd in READINGS:
                    r.t[(cell, rd)] = resolve(day, ev, s.m_entry, s.E, stop, -1, rd)
            r.entry_dvol = day.dollar_vol(s.m_entry)
            tr = r.t[("primary", "L")]
            r.stop_dvol = day.dollar_vol(tr.m_exit) if tr.reason in ("stop_open", "stop_level") else None
        r.op, r.op_skip = openprint(day, ev)
        r.pb = pmbreak(day, ev, s.pmh)
        r.legal = {}
        carry = ev.role == "carry"
        if s.k is not None and (s.skip == "ssr_active" or (carry and s.skip in (None, "no_fill_bar", "resume_bar", "entry_ge_S1", "ssr_active"))):
            for cell in CELLS:
                r.legal[cell] = ssr_legal(day, ev, s, cell)
        if paths:
            r.cff = day.close_ffill()
    if null and r.sig5.pmh is not None and ev.role == "reg":
        r.cands = null_candidates(day, ev, r.sig5.pmh)
    return r


def scan(photo, events, roles=("reg",), trades=False, null=False, paths=False, verbose=True, keep_day=False):
    say = print if verbose else (lambda *a, **k: None)
    sel = [ev for ev in events if ev.role in roles]
    sel.sort(key=lambda e: (e.date, e.symbol))
    out = []
    for i, ev in enumerate(sel):
        out.append(scan_day(photo, ev, trades=trades, null=null, paths=paths, keep_day=keep_day))
        if verbose and i % 500 == 0:
            say(f"  scanned {i + 1:,} of {len(sel):,} name-days", flush=True)
    return out


def schedule_frame(scans):
    rows = []
    for r in scans:
        s, ev = r.sig5, r.ev
        if s.skip is not None or r.ev.role != "reg":
            continue
        rows.append({"symbol": ev.symbol, "date": f"{ev.date:%Y-%m-%d}", "wf_year": ev.wf_year, "bucket": ev.bucket,
                     "signal_end": hm(s.end), "entry_m": int(s.m_entry), "E": s.E, "S1": round(s.S1, 6), "S2": s.S2,
                     "P": ev.P, "adv": ev.adv, "revsplit60": int(ev.flags.get("revsplit60", False)),
                     "reused": int(bool(ev.flags.get("reused"))), "delisted": int(bool(ev.flags.get("delisted"))),
                     "s3p": int(bool(ev.flags.get("s3p"))), "s3v": int(bool(ev.flags.get("s3v"))),
                     "lowfloat": ev.flags.get("lowfloat", "unknown")})
    cols = ["symbol", "date", "wf_year", "bucket", "signal_end", "entry_m", "E", "S1", "S2", "P", "adv", "revsplit60",
            "reused", "delisted", "s3p", "s3v", "lowfloat"]
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)


# ================================================================== the counts (step 1; recomputed and asserted in --run)
def _by_year(items):
    out = {y: 0 for y in WF_YEARS}
    for y in items:
        if y in out:
            out[y] += 1
    return out


def spreads_from_quotes(photo, events):
    vals, refused, check = {b: [] for b in BUCKETS}, {b: 0 for b in BUCKETS}, {b: [] for b in BUCKETS}
    info = {"name_days": 0, "served": 0, "refused_or_missing": 0, "served_no_valid_second": 0}
    for ev in sorted([e for e in events if e.quotes], key=lambda e: (e.date, e.symbol)):
        info["name_days"] += 1
        q = photo.quotes(ev.symbol, ev.date, "quotes_pmfail_am")
        if q.status in ("refused", "missing"):
            refused[ev.bucket] += 1
            info["refused_or_missing"] += 1
        else:
            info["served"] += 1
            v = spread_window(q.df, ev.date, *AM_WIN)
            if v is None:
                info["served_no_valid_second"] += 1
            else:
                vals[ev.bucket].append(v)
        qc = photo.quotes(ev.symbol, ev.date, "quotes_pmfail_close")
        if qc.status == "ok":
            v = spread_window(qc.df, ev.date, *CLOSE_WIN)
            if v is not None:
                check[ev.bucket].append(v)
    sp = bucket_spreads(vals, refused)
    chk = {b: ({"median": float(np.median(check[b])), "p75": float(np.percentile(check[b], 75)), "n": len(check[b])}
               if check[b] else {"median": None, "p75": None, "n": 0}) for b in BUCKETS}
    return sp, chk, info


def compute_counts(inp, scans, spreads, spread_check, spread_info, photo_stamp):
    reg = [r for r in scans if r.ev.role == "reg"]
    c = {}
    c["builder"] = inp.builder_counts
    c["m_keeps_volume"] = bool(inp.m_keeps_volume)
    ev_by = {y: {"lt5": 0, "5to20": 0} for y in WF_YEARS}
    for r in reg:
        ev_by[r.ev.wf_year][r.ev.bucket] += 1
    c["event_days_registered"] = ev_by
    st, feeds, dq = {}, {}, {"dropped_v_le_0": 0, "dropped_price_le_0": 0, "dropped_dup_identical": 0,
                             "dropped_outside_0400_1559": 0}
    for r in reg:
        st[r.status] = st.get(r.status, 0) + 1
        feeds[str(r.feed)] = feeds.get(str(r.feed), 0) + 1
        if r.dq:
            for k in dq:
                dq[k] += int(r.dq.get(k, 0))
    c["bars"] = {"status": st, "feed": feeds, "data_quality": dq,
                 "label": "SIP" if set(feeds) <= {"sip", "None"} else ("IEX" if set(feeds) <= {"iex", "None"} else "MIXED")}
    sig = [r for r in reg if r.sig5.k is not None]
    c["signals_by_year"] = _by_year(r.ev.wf_year for r in sig)
    hh = {}
    for r in sig:
        lab = hm((r.sig5.end // 30) * 30)
        hh[lab] = hh.get(lab, 0) + 1
    c["signals_by_signal_end_half_hour"] = dict(sorted(hh.items()))
    c["skips"] = {k: _by_year(r.ev.wf_year for r in reg if r.sig5.skip == k) for k in SKIPS}
    c["ssr"] = {"at_open_0930_low_by_year": _by_year(r.ev.wf_year for r in reg if r.ssr_open),
                "no_0930_bar": int(sum(1 for r in reg if r.status in ("ok", "empty") and r.ssr_open is None)),
                "intraday_signal_ssr_active_by_year": _by_year(r.ev.wf_year for r in sig if r.sig5.ssr_same),
                "reading_0400_by_year": _by_year(r.ev.wf_year for r in sig if r.sig5.ssr_0400),
                "event_days_by_year": _by_year(r.ev.wf_year for r in reg),
                "signals_by_year": c["signals_by_year"]}
    lens = {"4": 0, "5": 0, "6-9": 0, "10": 0, "11-30": 0, ">30": 0}
    by_hh4 = {}
    for r in reg:
        for s0, n, _res in r.runs4:
            key = "4" if n == 4 else "5" if n == 5 else "6-9" if n <= 9 else "10" if n == 10 else "11-30" if n <= 30 else ">30"
            lens[key] += 1
            if n == 4:
                lab = hm((s0 // 30) * 30)
                by_hh4[lab] = by_hh4.get(lab, 0) + 1
    c["halts"] = {"run_lengths": lens, "four_minute_runs_by_half_hour": dict(sorted(by_hh4.items())),
                  "event_days_with_a_5min_halt": int(sum(1 for r in reg if r.runs5)),
                  "signals_lost_to_resume_entry": int(sum(1 for r in reg if r.sig5.skip == "resume_bar")),
                  "four_minute_reading_resume_skips": int(sum(1 for r in reg if r.sig4.skip == "resume_bar"))}
    fills = [r for r in reg if r.sig5.skip is None]
    per_year = _by_year(r.ev.wf_year for r in fills)
    c["fills_by_year"] = per_year
    c["fills_by_bucket"] = {b: int(sum(1 for r in fills if r.ev.bucket == b)) for b in BUCKETS}
    c["fills_four_minute_reading"] = int(sum(1 for r in reg if r.sig4.skip is None))
    c["exit_window_empty_among_fills_by_year"] = _by_year(r.ev.wf_year for r in fills if r.exit_empty)
    sd = {"lt2": 0, "2-5": 0, "5-10": 0, "10-20": 0, "ge20": 0}
    for r in fills:
        x = (r.sig5.S1 - r.sig5.E) / r.sig5.E
        sd["lt2" if x < 0.02 else "2-5" if x < 0.05 else "5-10" if x < 0.10 else "10-20" if x < 0.20 else "ge20"] += 1
    c["stop_distance"] = sd
    thin = {y: {b: [0, 0] for b in BUCKETS} for y in WF_YEARS}
    for r in reg:
        if r.thin is not None:
            thin[r.ev.wf_year][r.ev.bucket][1] += 1
            thin[r.ev.wf_year][r.ev.bucket][0] += int(r.thin < 0.10)
    c["condition1_premarket_thinness_under_10pct"] = {y: {b: {"thin": v[0], "n": v[1]} for b, v in d.items()} for y, d in thin.items()}
    c["condition3"] = {"delisted_by_year": _by_year(r.ev.wf_year for r in reg if r.ev.flags.get("delisted")),
                       "inactive_by_year": _by_year(r.ev.wf_year for r in reg if r.ev.flags.get("inactive")),
                       "ambiguous_mixed_by_year": _by_year(r.ev.wf_year for r in reg if r.ev.flags.get("mixed")),
                       "reused_ticker_event_days": int(sum(1 for r in reg if r.ev.flags.get("reused"))),
                       "event_days_by_year": _by_year(r.ev.wf_year for r in reg)}
    src = {"s1": 0, "cal": 0, "m": 0}
    agree = {}
    for r in reg:
        s = r.ev.flags.get("rs_sources", {})
        for k in src:
            src[k] += int(bool(s.get(k)))
        key = "+".join(k for k in ("s1", "cal", "m") if s.get(k)) or "none"
        agree[key] = agree.get(key, 0) + 1
    c["condition4_revsplit60"] = {"flagged_by_year": _by_year(r.ev.wf_year for r in reg if r.ev.flags.get("revsplit60")),
                                  "by_source": src, "agreement": dict(sorted(agree.items()))}
    c["lowfloat"] = {k: int(sum(1 for r in reg if r.ev.flags.get("lowfloat", "unknown") == k)) for k in ("lt20m", "ge20m", "unknown")}
    if inp.top20 is None:
        c["siporb_top20_share"] = {"share": None, "error": inp.top20_error}
    else:
        n20 = sum(1 for r in reg if (r.ev.date, r.ev.symbol) in inp.top20)
        c["siporb_top20_share"] = {"in_top20": int(n20), "event_days": len(reg), "share": n20 / len(reg) if reg else None}
    c["spreads"] = spreads
    c["spreads_close_side_check"] = spread_check
    c["spreads_info"] = spread_info
    c["cap_binding_fixed_notional"] = {str(N): (float(np.mean([CAP_FRAC * r.ev.adv < N for r in fills])) if fills else None)
                                       for N in CAP_NOTIONALS}
    c["count_gate"] = count_gate(per_year)
    c["photograph"] = photo_stamp
    return c


# ================================================================== stamps and the step chain
def core_stamp(inp, photo=None):
    ver = (getattr(photo, "verified", None) or {}) if photo else {}
    return {"harness": os.path.basename(__file__), "harness_sha256_lf": sha256_lf(os.path.abspath(__file__)),
            "preregs_sha256_lf": dict(PREREG_SHA_LF), "inputs_sha256": dict(sorted(inp.shas.items())),
            "namedays_sha256": NAMEDAYS_SHA, "photograph_manifest_sha256": photo.manifest_sha256 if photo else None,
            "photograph_unpinned_digest": ver.get("unpinned_digest"), "versions": versions()}


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def require(step, inp, photo=None):
    """an earlier step's file must exist and carry this run's stamp (photograph compared when both have one)"""
    names = {"counts": "counts.json", "overlap": "overlap.json", "power": "power.json", "null": "null.json"}
    p = os.path.join(out_dir(), names[step])
    if not os.path.exists(p):
        refuse(f"step '{step}' has not been filed ({p})")
    got = _read_json(p).get("stamp") or {}
    now = core_stamp(inp, photo)
    for k in ("harness_sha256_lf", "preregs_sha256_lf", "inputs_sha256", "namedays_sha256", "versions"):
        if _clean(got.get(k)) != _clean(now[k]):
            refuse(f"step '{step}' was filed under a different {k}")
    if photo is not None and got.get("photograph_manifest_sha256") not in (None, photo.manifest_sha256):
        refuse(f"step '{step}' was filed on a different photograph")
    if photo is not None and got.get("photograph_manifest_sha256") is not None and \
            got.get("photograph_unpinned_digest") != now["photograph_unpinned_digest"]:
        refuse(f"step '{step}' was filed on different quote / mark files (the photograph's unpinned digest moved)")
    return _read_json(p)


# ================================================================== trade tables, sizing, series
def trade_table(scans, key, spreads, wf):
    """rows = fills (in scan order) of one (cell, reading) -> dict of arrays with per-share primary / stress nets"""
    rs = [r for r in scans if getattr(r, "t", None) and key in r.t]
    return _table([r.t[key] for r in rs], [r.ev for r in rs], spreads, wf, rs)


def _table(trs, evs, spreads, wf, rs=None, locate_on=True):
    n = len(trs)
    E = np.array([t.E for t in trs], float)
    X = np.array([t.X for t in trs], float)
    side = np.array([t.side for t in trs], float)
    nights = np.array([t.nights for t in trs], float)
    h50 = np.array([spreads[e.bucket]["h50"] for e in evs], float)
    h75 = np.array([spreads[e.bucket]["h75"] for e in evs], float)
    gross, cp, cs, lp, ls = unit_parts(E, X, side, nights, h50, h75, locate_on) if n else (np.zeros(0),) * 5
    bi = wf.get_indexer(pd.DatetimeIndex([t.book_date for t in trs])) if n else np.zeros(0, np.int64)
    if n and (bi < 0).any():
        refuse("a trade books on a session outside the WF calendar")
    return {"n": n, "E": E, "X": X, "side": side, "nights": nights, "adv": np.array([e.adv for e in evs], float),
            "bucket": np.array([e.bucket for e in evs], object), "date": pd.DatetimeIndex([e.date for e in evs]),
            "symbol": np.array([e.symbol for e in evs], object), "book": pd.DatetimeIndex([t.book_date for t in trs]),
            "bi": bi.astype(np.int64), "gross": gross, "cost_p": cp, "cost_s": cs, "loc_p": lp, "loc_s": ls,
            "unit_p": gross - cp - lp, "unit_s": gross - cs - ls, "reason": np.array([t.reason for t in trs], object),
            "priced_by": np.array([t.priced_by for t in trs], object), "halted": np.array([t.halted for t in trs], bool),
            "m_entry": np.array([t.m_entry for t in trs], object), "m_exit": np.array([t.m_exit for t in trs], object),
            "stop": np.array([t.stop for t in trs], float), "evs": evs, "trs": trs, "rs": rs}


def sub(T, mask):
    mask = np.asarray(mask, bool)
    out = {}
    for k, v in T.items():
        if k == "n":
            continue
        if isinstance(v, (np.ndarray, pd.DatetimeIndex)) and len(v) == len(mask):
            out[k] = v[mask]
        elif isinstance(v, list) and len(v) == len(mask):
            out[k] = [x for x, m in zip(v, mask) if m]
        else:
            out[k] = v
    out["n"] = int(mask.sum())
    return out


def daily_of(pnl, bi, n):
    return np.bincount(np.asarray(bi, np.int64), weights=np.asarray(pnl, float), minlength=n)


def leg_report(T, wf, inR_cal, shares=None, unit="unit_p"):
    """a reported row: its own N* (reading L, primary cost unless the table says otherwise) and the $5,000 figure"""
    if T["n"] == 0:
        return {"n": 0}
    if shares is None:
        N, sh, _dd = solve_nstar(T["E"], T["adv"], T["unit_p"], T["bi"])
    else:
        N, sh = None, shares
    pnl = sh * T[unit]
    d = daily_of(pnl, T["bi"], len(wf))
    st = series_stats(d, inR_cal)
    return {"n": T["n"], "N_star": N, "net": st["net"], "maxdd": st["maxdd"], "roc30": st["roc30"], "t": st["t"],
            "pf": pf_of(pnl), "rsum": st["rsum"], "net_stress": float((sh * T["unit_s"]).sum()),
            "scale_free_roc_at_5k": scale_free(T["E"], T[unit], T["bi"], len(wf))}


# ================================================================== book joins (s.6, s.18)
def join_book(d_cal, wf, book):
    """leg daily (WF stock calendar) -> the book index with fill 0, leg days not in it appended (counted)"""
    s = pd.Series(np.asarray(d_cal, float), index=wf)
    s = s[s != 0]
    idx = book.index.union(s.index)
    j = s.reindex(idx, fill_value=0.0)
    appended = int((~s.index.isin(book.index)).sum())
    return j, appended


def inR_calendar(wf, book):
    return np.asarray(wf.isin(book.index[book.inR]))


def book_add(leg_cal, wf, book):
    """house line #45 (report): c = 0.25 x sd(#463 mtm) / sd(leg) over 2016-07-01 .. 2018-06-30 on the book index; rows at
    c, 0.5c, 2c and the judged series; (#463 + k x leg) vs #463 and (L + k x leg) vs L; paired bootstrap p5 each"""
    j, appended = join_book(leg_cal, wf, book)
    B = pd.Series(book.mtm, index=book.index).reindex(j.index, fill_value=0.0)
    Ls = pd.Series(book.L, index=book.index).reindex(j.index, fill_value=0.0)
    early = np.asarray((j.index >= WF0) & (j.index < VOL_END))
    sl = float(np.std(j.to_numpy()[early], ddof=1))
    c = VOL_SHARE * float(np.std(B.to_numpy()[early], ddof=1)) / sl if sl > 0 else float("nan")
    years = book.years
    out = {"c": c, "appended_days": appended, "rows": {}}
    idxs = PL.stationary_indices(len(j), BOOT_DRAWS, BOOT_BLOCK, np.random.default_rng(SEED_BOOT))
    for lab, k in (("c", c), ("0.5c", 0.5 * c), ("2c", 2 * c), ("judged", 1.0)):
        if not np.isfinite(k):
            continue
        row = {}
        for base_lab, base in (("book463", B.to_numpy()), ("L", Ls.to_numpy())):
            cand = base + k * j.to_numpy()
            st = r11_stats(cand, j.index)
            lead = PL.roc30(cand[idxs], years) - PL.roc30(base[idxs], years)
            lead = lead[np.isfinite(lead)]
            row[base_lab] = {"roc": st["roc"], "sortino": st["sort"],
                             "p5_lead": float(np.percentile(lead, 5)) if len(lead) else None}
        out["rows"][lab] = {"k": k, **row}
    return out


# ================================================================== modes
def _schedule_sha(df):
    return sha256_bytes(csv_bytes(df))


def mode_counts(inp, photo, verbose=True):
    say = print if verbose else (lambda *a, **k: None)
    scans = scan(photo, inp.events, roles=("reg",), verbose=verbose)
    sp, chk, info = spreads_from_quotes(photo, inp.events)
    counts = compute_counts(inp, scans, sp, chk, info, photo.stamp())
    sched = schedule_frame(scans)
    counts["schedule_sha256"] = _schedule_sha(sched)
    counts["stamp"] = core_stamp(inp, photo)
    od = out_dir()
    write_once(os.path.join(od, "schedule.csv"), csv_bytes(sched))
    write_once(os.path.join(od, "counts.json"), json_bytes(counts))
    print_counts(counts, say)
    return counts, sched


def print_counts(c, say=print):
    say("\nPMFAIL r1 STEP 1 - COUNTS (no exit walk, no P&L)")
    say(f"  bars: {c['bars']['status']}  feed {c['bars']['feed']}  label {c['bars']['label']}  dropped {c['bars']['data_quality']}")
    hdr = " ".join(f"{y:>8}" for y in WF_YEARS)
    say(f"  {'':34}{hdr}")
    for lab, d in (("registered event days", {y: sum(v.values()) for y, v in c["event_days_registered"].items()}),
                   ("signals", c["signals_by_year"]), ("filled primary trades", c["fills_by_year"])):
        say(f"  {lab:34}" + " ".join(f"{d[y]:>8}" for y in WF_YEARS))
    for k, d in c["skips"].items():
        say(f"  skip {k:29}" + " ".join(f"{d[y]:>8}" for y in WF_YEARS))
    for k in ("at_open_0930_low_by_year", "intraday_signal_ssr_active_by_year", "reading_0400_by_year"):
        d = c["ssr"][k]
        say(f"  SSR {k[:30]:30}" + " ".join(f"{d[y]:>8}" for y in WF_YEARS))
    say(f"  signals by signal-end half hour: {c['signals_by_signal_end_half_hour']}")
    say(f"  halts: {c['halts']}")
    say(f"  stop distance (S1 - E) / E: {c['stop_distance']}; exit window empty among fills: "
        f"{sum(c['exit_window_empty_among_fills_by_year'].values())}")
    say(f"  condition 3: delisted {sum(c['condition3']['delisted_by_year'].values())}, inactive "
        f"{sum(c['condition3']['inactive_by_year'].values())}, ambiguous {sum(c['condition3']['ambiguous_mixed_by_year'].values())}")
    say(f"  condition 4 (reverse split in the prior 60 days): {c['condition4_revsplit60']['by_source']} agreement "
        f"{c['condition4_revsplit60']['agreement']}")
    say(f"  LOWFLOAT: {c['lowfloat']}; SIPORB top-20 share: {c['siporb_top20_share']}")
    for b, v in c["spreads"].items():
        say(f"  spreads {b}: h50 {v['h50']:.5f} h75 {v['h75']:.5f} n {v['n']} ({v['source']}; refused -> prior {v['refused_take_prior']})")
    say(f"  close-side check: {c['spreads_close_side_check']}; {c['spreads_info']}")
    say(f"  cap binding at fixed notionals: {c['cap_binding_fixed_notional']}")
    g = c["count_gate"]
    say(f"  COUNT GATE (bar 3, the 9-year mean): n {g['n']}  n / {YEARS:.3f} = {g['n_per_year']:.2f}  >= 50 {g['mean_ge_50']}"
        f"  >= 100 {g['n_ge_100']}  -> {'PASS' if g['pass'] else 'MISS (recorded; the run continues: RESEARCH ROW or FAIL)'}"
        f"; thin years (< 25): {g['thin_years_under_25'] or 'none'}")


def load_r2():
    found = [n for n in R2_MODULES if os.path.exists(os.path.join(HERE, n + ".py"))]
    if not found:
        refuse("RUNNER2's harness is not on file (tools/runner2_r1_stageA.py or tools/disc_runner2_r1_stageA.py)")
    if len(found) > 1:
        refuse(f"both {found} exist - one RUNNER2 harness only")
    mod = importlib.import_module(found[0])
    for fn in ("null_context", "null_half"):
        if not callable(getattr(mod, fn, None)):
            refuse(f"{found[0]} has no {fn}()")
    return mod, os.path.abspath(mod.__file__)


def read_r2_schedule():
    p = os.path.join(r2_out_dir(), "schedule.csv")
    pc = os.path.join(r2_out_dir(), "counts.json")
    if not (os.path.exists(p) and os.path.exists(pc)):
        refuse(f"RUNNER2's count step is not filed ({pc}, {p})")
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    dcol = "date" if "date" in df.columns else ("d2" if "d2" in df.columns else None)
    if dcol is None or "symbol" not in df.columns:
        refuse("RUNNER2's schedule.csv has no symbol / date (d2) columns")
    return set(zip(df["symbol"], pd.to_datetime(df[dcol]).dt.normalize())), _read_json(pc)


def mode_overlap(inp, verbose=True):
    say = print if verbose else (lambda *a, **k: None)
    counts = require("counts", inp)
    sched = pd.read_csv(os.path.join(out_dir(), "schedule.csv"), dtype={"symbol": str}, keep_default_na=False)
    with open(os.path.join(out_dir(), "schedule.csv"), "rb") as f:
        if sha256_bytes(f.read()) != counts["schedule_sha256"]:
            refuse("schedule.csv does not hash to the schedule_sha256 filed in counts.json")
    r2, r2c = read_r2_schedule()
    bk = inp.book
    tdays = pd.DatetimeIndex(sorted(set(pd.to_datetime(sched["date"]))))
    R = set(bk.index[bk.inR])
    DD = set(bk.index[bk.dd_days])
    legs = {k: set(bk.index[v != 0]) for k, v in bk.legs.items()}
    pm = set(zip(sched["symbol"], pd.to_datetime(sched["date"])))
    nxt = {}
    for d0, d1 in zip(inp.days[:-1], inp.days[1:]):
        nxt[d0] = d1
    link = sum(1 for s, d in pm if (s, nxt.get(d)) in r2)
    o = {"trade_days": len(tdays), "in_R_762": int(sum(d in R for d in tdays)),
         "in_463_drawdown_460": int(sum(d in DD for d in tdays)),
         "shared_with_463_legs_nonzero_mtm": {k: int(sum(d in v for d in tdays)) for k, v in legs.items()},
         "same_name_day_with_runner2_fills": int(len(pm & r2)), "pmfail_fills": len(pm), "runner2_fills": len(r2),
         "pmfail_t_then_runner2_next_session_same_name": int(link),
         "runner2_counts_stamp_omega": (r2c.get("omega_sha256") if isinstance(r2c, dict) else None),
         "stamp": core_stamp(inp)}
    write_file(os.path.join(out_dir(), "overlap.json"), json_bytes(o))
    say(f"\nPMFAIL r1 STEP 2 - OVERLAP: {o}")
    return o


def coin_trades(scans):
    """the coin-flip leg on the primary's schedule: same name-days, entry bars and E; side by default_rng(20261006)"""
    fills = sorted([r for r in scans if r.ev.role == "reg" and r.sig5.skip is None], key=lambda r: (r.ev.date, r.ev.symbol))
    coin = np.random.default_rng(SEED_COIN).choice([-1.0, 1.0], size=len(fills))
    trs, evs = [], []
    for r, side in zip(fills, coin):
        s = r.sig5
        day = Day(None, r.ev.date) if r.day is None else r.day
        stop = s.S1 if side < 0 else s.E - (s.S1 - s.E)
        trs.append(resolve(day, r.ev, s.m_entry, s.E, stop, int(side), "L"))
        evs.append(r.ev)
    return trs, evs, coin


def mode_power(inp, photo, verbose=True):
    say = print if verbose else (lambda *a, **k: None)
    counts = require("counts", inp, photo)
    require("overlap", inp)
    scans = scan(photo, inp.events, roles=("reg",), trades=False, verbose=verbose, keep_day=True)
    sched = schedule_frame(scans)
    if _schedule_sha(sched) != counts["schedule_sha256"]:
        refuse("the recomputed schedule differs from the filed one")
    trs, evs, coin = coin_trades(scans)
    T = _table(trs, evs, counts["spreads"], inp.wf)
    N, sh, dd = solve_nstar(T["E"], T["adv"], T["unit_p"], T["bi"])
    d = daily_of(sh * T["unit_p"], T["bi"], len(inp.wf))
    j, _app = join_book(d, inp.wf, inp.book)
    B = pd.Series(inp.book.mtm, index=inp.book.index).reindex(j.index, fill_value=0.0)
    early = np.asarray((j.index >= WF0) & (j.index < VOL_END))
    sl = float(np.std(j.to_numpy()[early], ddof=1))
    c = VOL_SHARE * float(np.std(B.to_numpy()[early], ddof=1)) / sl if sl > 0 else float("nan")
    ddc = maxdd_of(j.to_numpy())
    k30 = 30000.0 / ddc if ddc > 0 else float("nan")
    od = out_dir()
    dates = [f"{x:%Y-%m-%d}" for x in j.index]
    write_file(os.path.join(od, "coinflip_daily.csv"), csv_bytes(pd.DataFrame({"date": dates, "pnl_usd": j.to_numpy()})))
    write_file(os.path.join(od, "book463_wf.csv"), csv_bytes(pd.DataFrame({"date": dates, "pnl_usd": B.to_numpy()})))
    out = {"n_trades": T["n"], "coin_long": int((coin > 0).sum()), "coin_short": int((coin < 0).sum()), "lines": {}}
    for lab, k, fn in (("vol_c", c, "cand_c.csv"), ("own_dd_30k", k30, "cand_30k.csv")):
        if not np.isfinite(k):
            out["lines"][lab] = None
            continue
        write_file(os.path.join(od, fn), csv_bytes(pd.DataFrame({"date": dates, "pnl_usd": B.to_numpy() + k * j.to_numpy()})))
        r = PL.main(["--cand", os.path.join(od, fn), "--twin", os.path.join(od, "book463_wf.csv"), "--from", "2016-07-01",
                     "--to", "2025-06-29", "--date-col", "date", "--pnl-col", "pnl_usd", "--block", str(BOOT_BLOCK),
                     "--draws", str(BOOT_DRAWS), "--seed", str(SEED_BOOT)])
        out["lines"][lab] = {"k": k, "sd": r["sd"], "line_5pct": r["line_5pct"], "line_80pct": r["line_80pct"],
                             "draws": r["draws"], "days": r["days"], "years": r["years"]}
    out["stamp"] = core_stamp(inp, photo)
    write_file(os.path.join(od, "power.json"), json_bytes(out))
    say(f"\nPMFAIL r1 STEP 3 - POWER LINE (coin-flip leg, {T['n']} trades at its own N*; no real direction computed)")
    for lab, v in out["lines"].items():
        if v:
            say(f"  {lab:10} k {v['k']:.4f}: SD {v['sd']:.1f}  5% line {v['line_5pct']:.1f}  80% line {v['line_80pct']:.1f}")
    return out


# ------------------------------------------------------------------ the family null (s.9)
def pm_null_context(scans, inp, spreads, n_y):
    pools = {yi: [] for yi in range(len(WF_YEARS))}
    for r in sorted([r for r in scans if r.ev.role == "reg" and r.cands], key=lambda r: (r.ev.date, r.ev.symbol)):
        pools[r.ev.yi].append(r)
    E, adv, u1, u2, b1, b2, start, cnt = [], [], [], [], [], [], {}, {}
    off = 0
    for yi in pools:
        for r in pools[yi]:
            start[id(r)] = off
            cnt[id(r)] = len(r.cands)
            for cd in r.cands:
                h50, h75 = spreads[r.ev.bucket]["h50"], spreads[r.ev.bucket]["h75"]
                g1, cp1, _cs, lp1, _ls = unit_parts([cd["E"]], [cd["X1"]], [-1], [cd["n1"]], [h50], [h75])
                g2, cp2, _cs2, lp2, _ls2 = unit_parts([cd["E"]], [cd["X2"]], [-1], [cd["n2"]], [h50], [h75])
                E.append(cd["E"])
                adv.append(r.ev.adv)
                u1.append(float(g1[0] - cp1[0] - lp1[0]))
                u2.append(float(g2[0] - cp2[0] - lp2[0]))
                b1.append(cd["b1"])
                b2.append(cd["b2"])
                off += 1
    bi1 = inp.wf.get_indexer(pd.DatetimeIndex(b1)) if b1 else np.zeros(0, np.int64)
    bi2 = inp.wf.get_indexer(pd.DatetimeIndex(b2)) if b2 else np.zeros(0, np.int64)
    if (np.asarray(bi1) < 0).any() or (np.asarray(bi2) < 0).any():
        refuse("a null trade books outside the WF calendar")
    return SimpleNamespace(pools=pools, start=start, cnt=cnt, E=np.array(E, float), adv=np.array(adv, float),
                           u=(np.array(u1, float), np.array(u2, float)), bi=(np.asarray(bi1, np.int64), np.asarray(bi2, np.int64)),
                           n_y=n_y, n_cal=len(inp.wf), inR_cal=inR_calendar(inp.wf, inp.book))


def pm_null_half(ctx, n=NULL_DRAWS, seed=SEED_PM):
    """PMFAIL's half of the family null: default_rng(seed); per year as many event days as the primary has trades, then
    one eligible bar per day; both cells sized at the draw's own N*. -> (n, 2, 3) [draw, primary / neighbour, ROC30 / t /
    R-sum], info"""
    rng = np.random.default_rng(seed)
    out = np.full((n, 2, 3), np.nan)
    info = {"nstar_primary": [], "nstar_neighbour": [], "n_trades": [], "shortfall": []}
    for i in range(n):
        gi, short = [], 0
        for yi in range(len(WF_YEARS)):
            pool, ny = ctx.pools[yi], int(ctx.n_y.get(yi, 0))
            if ny <= 0:
                continue
            if len(pool) <= ny:
                pick = np.arange(len(pool))
                short += ny - len(pool)
            else:
                pick = np.sort(rng.choice(len(pool), size=ny, replace=False))
            for j in pick:
                r = pool[int(j)]
                gi.append(ctx.start[id(r)] + int(rng.integers(ctx.cnt[id(r)])))
        gi = np.asarray(gi, np.int64)
        for c in (0, 1):
            N, sh, _dd = solve_nstar(ctx.E[gi], ctx.adv[gi], ctx.u[c][gi], ctx.bi[c][gi])
            d = daily_of(sh * ctx.u[c][gi], ctx.bi[c][gi], ctx.n_cal)
            st = series_stats(d, ctx.inR_cal)
            out[i, c] = (st["roc30"], st["t"], st["rsum"])
            info["nstar_primary" if c == 0 else "nstar_neighbour"].append(N)
        info["n_trades"].append(int(len(gi)))
        info["shortfall"].append(int(short))
    return out, info


def null_summary(four):
    """four: (n, 4, 3). max4 elementwise over the 4 cells, max2 per leg; NaN counts as -inf (counted)"""
    nan_n = int(np.isnan(four).sum())
    f = np.where(np.isnan(four), -np.inf, four)
    max4, pm2, r22 = f.max(axis=1), f[:, :2].max(axis=1), f[:, 2:].max(axis=1)
    summ = {}
    for lab, a in (("max4", max4), ("pmfail_max2", pm2), ("runner2_max2", r22)):
        summ[lab] = {s: pcts(a[:, j]) for j, s in enumerate(STATS)}
    summ["notion_b_roc30"] = {lab: summ[lab]["roc30"]["p95"] - summ[lab]["roc30"]["p50"]
                              for lab in ("max4", "pmfail_max2", "runner2_max2")}
    summ["nan_cells"] = nan_n
    return summ, max4, pm2, r22


def mode_null(inp, photo, r2=None, verbose=True, n=NULL_DRAWS):
    say = print if verbose else (lambda *a, **k: None)
    counts = require("counts", inp, photo)
    require("overlap", inp)
    require("power", inp, photo)
    read_r2_schedule()
    scans = scan(photo, inp.events, roles=("reg",), null=True, verbose=verbose)
    sched = schedule_frame(scans)
    if _schedule_sha(sched) != counts["schedule_sha256"]:
        refuse("the recomputed schedule differs from the filed one")
    n_y = {yi: int(counts["fills_by_year"][y]) for yi, y in enumerate(WF_YEARS)}
    ctx = pm_null_context(scans, inp, counts["spreads"], n_y)
    pm_arr, pm_info = pm_null_half(ctx, n, SEED_PM)
    mod, mpath = r2 if r2 is not None else load_r2()
    ctx2 = mod.null_context(photo=photo, book=inp.book)
    r2_arr, r2_info = mod.null_half(ctx2, n=n, seed=SEED_R2)
    r2_arr = np.asarray(r2_arr, float)
    if r2_arr.shape != (n, 2, 3):
        refuse(f"RUNNER2's null half has shape {r2_arr.shape}, not ({n}, 2, 3)")
    four = np.concatenate([pm_arr, r2_arr], axis=1)
    summ, max4, pm2, r22 = null_summary(four)
    cols = {"draw": np.arange(n)}
    for ci, cell in enumerate(("pm_primary", "pm_neighbour", "r2_P", "r2_W")):
        for j, s in enumerate(STATS):
            cols[f"{cell}_{s}"] = four[:, ci, j]
    for lab, a in (("max4", max4), ("pm_max2", pm2), ("r2_max2", r22)):
        for j, s in enumerate(STATS):
            cols[f"{lab}_{s}"] = a[:, j]
    cols["pm_nstar_primary"] = pm_info["nstar_primary"]
    cols["pm_nstar_neighbour"] = pm_info["nstar_neighbour"]
    cols["pm_n_trades"] = pm_info["n_trades"]
    cols["pm_shortfall"] = pm_info["shortfall"]
    for k, v in (r2_info or {}).items():
        if isinstance(v, (list, np.ndarray)) and len(v) == n:
            cols[f"r2_{k}"] = list(v)
    draws = pd.DataFrame(cols)
    od = out_dir()
    write_once(os.path.join(od, "null_draws.csv"), csv_bytes(draws))
    nj = {"summary": summ, "draws": n, "seeds": {"pmfail": SEED_PM, "runner2": SEED_R2},
          "percentile_method": PCT_METHOD, "statistics": list(STATS), "cells": ["pm_primary", "pm_neighbour", "r2_P", "r2_W"],
          "omega": {"n": getattr(ctx2, "omega_n", None), "sha256": getattr(ctx2, "omega_sha256", None)},
          "pmfail_schedule_sha256": counts["schedule_sha256"],
          "pmfail_pool_sizes": {WF_YEARS[yi]: len(v) for yi, v in ctx.pools.items()}, "pmfail_n_y": {WF_YEARS[k]: v for k, v in n_y.items()},
          "pmfail_shortfall_total": int(sum(pm_info["shortfall"])),
          "runner2_harness": os.path.basename(mpath), "runner2_harness_sha256_lf": sha256_lf(mpath),
          "null_draws_csv_sha256": sha256_bytes(csv_bytes(draws)), "stamp": core_stamp(inp, photo)}
    data = json_bytes(nj)
    write_once(os.path.join(od, "null.json"), data)
    write_once(os.path.join(od, "null.sha256"), f"{sha256_bytes(data)}  null.json\n".encode("utf-8"))
    say("\nPMFAIL r1 STEP 4 - THE FOUR-CELL FAMILY NULL (500 draws; PMFAIL seed 20261006, RUNNER2 seed 20261010)")
    for lab in ("max4", "pmfail_max2", "runner2_max2"):
        say(f"  {lab:13} " + "  ".join(f"{s} p50 {summ[lab][s]['p50']:.3f} p95 {summ[lab][s]['p95']:.3f} p97.5 {summ[lab][s]['p97.5']:.3f}"
                                    for s in STATS))
    say(f"  notion (b) p95 - p50 of the max ROC30: {summ['notion_b_roc30']}; NaN cells counted as -inf: {summ['nan_cells']}")
    say(f"  null.json sha256 {sha256_bytes(data)} (post to MANAGER; RUNNER2 --run --null-sha reads it)")
    return nj, draws


def verify_null_file(expected_sha, omega_sha=None, r2_harness_path=None, path=None):
    """for RUNNER2's --run: null.json must hash to the posted value, carry seeds (20261006, 20261010) and 500 draws, the
    reader's own Omega sha and the reader's own harness sha. -> the parsed null.json"""
    path = path or os.path.join(out_dir(), "null.json")
    if not os.path.exists(path):
        refuse(f"the family null is not filed ({path})")
    with open(path, "rb") as f:
        data = f.read()
    if sha256_bytes(data) != expected_sha:
        refuse(f"null.json hashes to {sha256_bytes(data)}, not the posted {expected_sha}")
    nj = json.loads(data.decode("utf-8"))
    if nj.get("seeds") != {"pmfail": SEED_PM, "runner2": SEED_R2} or nj.get("draws") != NULL_DRAWS:
        refuse("null.json seeds / draw count are not (20261006, 20261010) / 500")
    if omega_sha is not None and (nj.get("omega") or {}).get("sha256") != omega_sha:
        refuse("null.json was drawn on a different RUNNER2 Omega")
    if r2_harness_path is not None and nj.get("runner2_harness_sha256_lf") != sha256_lf(r2_harness_path):
        refuse("null.json was drawn by a different RUNNER2 harness")
    return nj


# ------------------------------------------------------------------ the real run
def event_path(T, scans_by_key, wf):
    """mean / median short mark in bps of entry by minute -30..+390 around entry (held at the exit value after exit)"""
    taus = np.arange(PATH_LO, PATH_HI + 1)
    M = np.full((T["n"], len(taus)), np.nan)
    for i in range(T["n"]):
        r = T["rs"][i]
        cff = r.day.close_ffill()
        E = T["E"][i]
        me = int(T["m_entry"][i])
        mx = T["m_exit"][i]
        X = T["X"][i]
        mm = me + taus
        pos = np.clip(mm - PRE0, 0, NM - 1)
        p = np.where((mm >= PRE0), cff[pos], np.nan)
        v = (E - p) / E * 1e4
        held = (E - X) / E * 1e4
        if mx is not None:
            v = np.where(mm >= int(mx), held, v)
        M[i] = v
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mean, med = np.nanmean(M, axis=0), np.nanmedian(M, axis=0)
    return {"tau": taus.tolist(), "mean_bps": mean.tolist(), "median_bps": med.tolist(), "n": T["n"]}


def mode_run(inp, photo, verbose=True):
    say = print if verbose else (lambda *a, **k: None)
    counts = require("counts", inp, photo)
    require("overlap", inp)
    power = require("power", inp, photo)
    nj = require("null", inp, photo)
    with open(os.path.join(out_dir(), "null.json"), "rb") as f:
        nsha = sha256_bytes(f.read())
    with open(os.path.join(out_dir(), "null.sha256"), encoding="utf-8") as f:
        if f.read().split()[0] != nsha:
            refuse("null.json does not match null.sha256")
    scans = scan(photo, inp.events, roles=("reg", "carry", "nonevent"), trades=True, verbose=verbose)
    reg = [r for r in scans if r.ev.role == "reg"]
    sp, chk, info = spreads_from_quotes(photo, inp.events)
    re_counts = compute_counts(inp, reg, sp, chk, info, photo.stamp())
    sched = schedule_frame(reg)
    re_counts["schedule_sha256"] = _schedule_sha(sched)
    filed = {k: v for k, v in counts.items() if k != "stamp"}
    if _clean(json.loads(json_bytes(re_counts).decode("utf-8"))) != _clean(filed):
        refuse("the recomputed counts differ from the filed counts.json")
    spreads = counts["spreads"]
    wf, bk = inp.wf, inp.book
    n_cal = len(wf)
    inR_cal = inR_calendar(wf, bk)
    tabs = {(c, rd): trade_table(reg, (c, rd), spreads, wf) for c in CELLS for rd in READINGS}
    cells = {}
    for c in CELLS:
        TL, TN = tabs[(c, "L")], tabs[(c, "N")]
        N, sh, dd = solve_nstar(TL["E"], TL["adv"], TL["unit_p"], TL["bi"])
        if TL["n"] and (sh < 1).any():
            refuse(f"{c}: a trade sizes to zero shares at N*")
        ser = {"L": daily_of(sh * TL["unit_p"], TL["bi"], n_cal), "L_stress": daily_of(sh * TL["unit_s"], TL["bi"], n_cal),
               "N": daily_of(sh * TN["unit_p"], TN["bi"], n_cal), "N_stress": daily_of(sh * TN["unit_s"], TN["bi"], n_cal)}
        cells[c] = {"N_star": N, "shares": sh, "dd_at_nstar": dd, "series": ser, "TL": TL, "TN": TN,
                    "stats": {k: series_stats(v, inR_cal) for k, v in ser.items()},
                    "pf": pf_of(sh * TL["unit_p"]), "pf_stress": pf_of(sh * TL["unit_s"]),
                    "scale_free_roc_at_5k": scale_free(TL["E"], TL["unit_p"], TL["bi"], n_cal)}
    P = cells["primary"]
    TL, sh = P["TL"], P["shares"]
    st = P["stats"]["L"]
    net_trades = sh * TL["unit_p"]
    dL = P["series"]["L"]
    years_pos, year_net, year_trades = years_positive(dL, wf, TL["book"])
    s95 = nj["summary"]["max4"]
    best_day = float(dL.max()) if len(dL) else 0.0
    best_trade = float(net_trades.max()) if len(net_trades) else 0.0

    def net_without(lo, hi):
        m = np.asarray((wf >= lo) & (wf <= hi))
        return float(dL[~m].sum())
    hi5 = TL["bucket"] == "5to20"
    T5 = sub(TL, hi5)
    sh5 = sh[hi5]
    stress5 = float((sh5 * T5["unit_s"]).sum())
    pf5 = pf_of(sh5 * T5["unit_p"])
    earner = (st["roc30"] >= BAR_EARN and st["rsum"] > 0 and st["rsum_ex3"] > 0 and st["rsum"] > s95["rsum"]["p95"])
    bars = {
        "1_return": bool(st["roc30"] >= BAR_ROC or earner),
        "2_pf": bool(P["pf"] >= BAR_PF),
        "3_count": bool(counts["count_gate"]["pass"]),
        "4_years": bool(years_pos >= BAR_YEARS),
        "5_t_and_null": bool(st["t"] >= BAR_T and st["t"] > s95["t"]["p95"] and st["roc30"] > s95["roc30"]["p95"]),
        "6_stress_L_and_N": bool(P["stats"]["L_stress"]["net"] > 0 and P["stats"]["N_stress"]["net"] > 0),
        "7_without_best_day_and_trade": bool(st["net"] - best_day > 0 and st["net"] - best_trade > 0),
        "8_meme_years": bool(net_without(*X20) > 0 and net_without(*X2021) > 0),
        "9_neighbour": bool(cells["neighbour"]["stats"]["L"]["net"] > 0),
        "10_tradable_p_ge_5": bool(stress5 > 0 and pf5 >= BAR_PF),
    }
    vd = verdict(bars, "3_count")
    dd_set = set(bk.index[bk.dd_days])
    sum463 = float(sum(v for d, v in zip(wf, dL) if d in dd_set))       # s.15 bar 1: "#463's 460 days print as a report"
    values = {"1_return": {"roc30": st["roc30"], "route": "ROC" if st["roc30"] >= BAR_ROC else ("earner" if earner else "neither"),
                           "rsum": st["rsum"], "rsum_ex3": st["rsum_ex3"], "null_p95_max4_rsum": s95["rsum"]["p95"],
                           "report_sum_over_463_drawdown_460_days": sum463},
              "2_pf": P["pf"], "3_count": counts["count_gate"], "4_years": {"positive": years_pos, "net": year_net, "trades": year_trades},
              "5_t_and_null": {"t": st["t"], "null_p95_max4_t": s95["t"]["p95"], "roc30": st["roc30"], "null_p95_max4_roc30": s95["roc30"]["p95"]},
              "6_stress_L_and_N": {"L": P["stats"]["L_stress"]["net"], "N": P["stats"]["N_stress"]["net"]},
              "7_without_best_day_and_trade": {"net": st["net"], "best_day": best_day, "best_trade": best_trade},
              "8_meme_years": {"without_2020-02-15..04-30": net_without(*X20), "without_2020-21": net_without(*X2021)},
              "9_neighbour": cells["neighbour"]["stats"]["L"]["net"],
              "10_tradable_p_ge_5": {"n": T5["n"], "net_stress": stress5, "pf": pf5, "pf_stress": pf_of(sh5 * T5["unit_s"])}}
    reports = run_reports(scans, reg, cells, spreads, wf, inR_cal, nj)
    diags = run_diagnostics(reg, cells, wf, bk, inR_cal, inp)
    od = out_dir()
    rows = []
    for c in CELLS:
        for rd in READINGS:
            T = tabs[(c, rd)]
            shc = cells[c]["shares"]
            for i in range(T["n"]):
                ev, tr = T["evs"][i], T["trs"][i]
                s = T["rs"][i].sig5
                rows.append({"symbol": ev.symbol, "date": f"{ev.date:%Y-%m-%d}", "exit_date": f"{tr.book_date:%Y-%m-%d}",
                             "cell": c, "reading": rd, "signal_end": hm(s.end), "entry_time": hm(tr.m_entry),
                             "entry": tr.E, "stop": tr.stop, "exit_time": hm(tr.m_exit) if tr.m_exit is not None else "",
                             "exit": tr.X, "exit_reason": tr.reason, "priced_by": tr.priced_by, "nights": tr.nights,
                             "shares": shc[i], "notional": shc[i] * tr.E, "gross": shc[i] * T["gross"][i],
                             "cost": shc[i] * T["cost_p"][i], "locate": shc[i] * T["loc_p"][i], "net": shc[i] * T["unit_p"][i],
                             "net_stress": shc[i] * T["unit_s"][i], "ssr": int(bool(s.ssr_same)),
                             "resume": int(tr.reason == "stop_open" and T["rs"][i].day.is_resume(int(tr.m_exit), HALT_K)),
                             "halted_close": int(tr.halted), "revsplit": int(bool(ev.flags.get("revsplit60"))),
                             "reused": int(bool(ev.flags.get("reused"))), "delisted": int(bool(ev.flags.get("delisted"))),
                             "bucket": ev.bucket})
    write_file(os.path.join(od, "trades.csv"), csv_bytes(pd.DataFrame(rows)))
    drows = []
    for c in CELLS:
        for lab, d in cells[c]["series"].items():
            nz = np.flatnonzero(d)
            for i in nz:
                drows.append({"date": f"{wf[i]:%Y-%m-%d}", "cell": c, "reading": lab, "pnl_usd": float(d[i])})
    write_file(os.path.join(od, "daily.csv"), csv_bytes(pd.DataFrame(drows, columns=["date", "cell", "reading", "pnl_usd"])))
    out = {"verdict": vd, "bars": bars, "bar_values": values,
           "cells": {c: {"N_star": cells[c]["N_star"], "dd_at_nstar": cells[c]["dd_at_nstar"], "pf": cells[c]["pf"],
                         "pf_stress": cells[c]["pf_stress"], "scale_free_roc_at_5k": cells[c]["scale_free_roc_at_5k"],
                         "stats": cells[c]["stats"], "n": cells[c]["TL"]["n"]} for c in CELLS},
           "null": nj["summary"], "null_sha256": nsha, "power": power.get("lines"), "reports": reports,
           "diagnostics": diags, "feed_label": counts["bars"]["label"],
           "prereg_sha256_lf": dict(PREREG_SHA_LF), "stamp": core_stamp(inp, photo)}
    write_file(os.path.join(od, "stage_a.json"), json_bytes(out))
    say("\nPMFAIL r1 STAGE A (WF 2016-07-01 .. 2025-06-29; no lockbox read)")
    say(f"  primary: N* ${P['N_star']:,.0f}  n {TL['n']}  net ${st['net']:,.0f}  maxDD ${st['maxdd']:,.0f}  ROC@30k {st['roc30']:.2f}"
        f"  t {st['t']:.2f}  PF {P['pf']:.3f}  R-sum ${st['rsum']:,.0f}  ($5k scale-free ROC {P['scale_free_roc_at_5k']:.2f})")
    nb = cells["neighbour"]
    say(f"  neighbour: N* ${nb['N_star']:,.0f}  net ${nb['stats']['L']['net']:,.0f}  ROC@30k {nb['stats']['L']['roc30']:.2f}")
    for k, v in bars.items():
        say(f"  bar {k:30} {'PASS' if v else 'FAIL'}  {values[k]}")
    say(f"  VERDICT: {vd}  (feed {counts['bars']['label']}; premarket thinness print in counts.json)")
    return out


def run_reports(scans, reg, cells, spreads, wf, inR_cal, nj):
    P = cells["primary"]
    TL, sh = P["TL"], P["shares"]
    rep = {}

    def subset(mask, lab):
        mask = np.asarray(mask, bool)
        T = sub(TL, mask)
        rep[lab] = leg_report(T, wf, inR_cal, shares=sh[mask])
        T2 = sub(TL, ~mask)
        rep[lab + "_without"] = leg_report(T2, wf, inR_cal, shares=sh[~mask])

    fl = lambda k: np.array([bool(e.flags.get(k)) for e in TL["evs"]], bool)
    subset(TL["bucket"] == "5to20", "p_ge_5")
    for k in ("revsplit60", "reused", "delisted", "s3p", "s3v"):
        subset(fl(k), k)
    subset(TL["halted"], "halted_close")
    for lf in ("lt20m", "ge20m", "unknown"):
        rep["lowfloat_" + lf] = leg_report(sub(TL, np.array([e.flags.get("lowfloat", "unknown") == lf for e in TL["evs"]])),
                                           wf, inR_cal, shares=sh[np.array([e.flags.get("lowfloat", "unknown") == lf for e in TL["evs"]])])
    act = np.array([e.flags.get("shortable_active") is not None for e in TL["evs"]], bool)
    sho = np.array([e.flags.get("shortable_active") is True for e in TL["evs"]], bool)
    rep["shortable_among_active"] = leg_report(sub(TL, act & sho), wf, inR_cal, shares=sh[act & sho])
    rep["not_shortable_among_active"] = leg_report(sub(TL, act & ~sho), wf, inR_cal, shares=sh[act & ~sho])
    # the 4-minute halt reading: the fills that survive the 4-minute resume skip, at the same shares
    k4 = np.array([r.sig4.skip is None for r in TL["rs"]], bool)
    rep["four_minute_halt_reading"] = leg_report(sub(TL, k4), wf, inR_cal, shares=sh[k4])
    rep["reading_N"] = P["stats"]["N"]
    # OPENPRINT, PMBREAK, SSR legal, placebo: own N* and the $5k figure
    op = [r for r in reg if getattr(r, "op", None) is not None]
    rep["OPENPRINT"] = leg_report(_table([r.op for r in op], [r.ev for r in op], spreads, wf), wf, inR_cal)
    rep["OPENPRINT_skips"] = {"ssr_open": int(sum(1 for r in reg if getattr(r, "op_skip", None) == "ssr_open")),
                              "no_bar": int(sum(1 for r in reg if getattr(r, "op_skip", None) == "no_bar"))}
    pb = [r for r in reg if getattr(r, "pb", None) is not None]
    rep["PMBREAK"] = leg_report(_table([r.pb for r in pb], [r.ev for r in pb], spreads, wf, locate_on=False), wf, inR_cal)
    for c in CELLS:
        lg = [r for r in scans if r.ev.role in ("reg", "carry") and getattr(r, "legal", {}).get(c) is not None]
        rep[f"SSR_legal_{c}"] = leg_report(_table([r.legal[c] for r in lg], [r.ev for r in lg], spreads, wf), wf, inR_cal)
        rep[f"SSR_legal_{c}"]["carry_over_days"] = int(sum(1 for r in lg if r.ev.role == "carry"))
    ne = [r for r in scans if r.ev.role == "nonevent" and getattr(r, "t", None)]
    for c in CELLS:
        rep[f"placebo_nonevent_{c}"] = leg_report(_table([r.t[(c, "L")] for r in ne], [r.ev for r in ne], spreads, wf), wf, inR_cal)
    rep["bonferroni"] = {"family_p95_max4": {s: nj["summary"]["max4"][s]["p95"] for s in STATS},
                         "pmfail_p97.5_max2": {s: nj["summary"]["pmfail_max2"][s]["p97.5"] for s in STATS},
                         "runner2_p97.5_max2": {s: nj["summary"]["runner2_max2"][s]["p97.5"] for s in STATS}}
    rep["stop_exits_on_resume_open"] = int(sum(1 for i in range(TL["n"]) if TL["reason"][i] == "stop_open"
                                               and TL["rs"][i].day.is_resume(int(TL["m_exit"][i]), HALT_K)))
    # bars 6-8 without the halted-into-close trades (s.5: "bars 6-8 also print without these trades")
    keep = ~TL["halted"]
    TN = P["TN"]
    dLk = daily_of(sh[keep] * TL["unit_p"][keep], TL["bi"][keep], len(wf))
    nk = sh[keep] * TL["unit_p"][keep]

    def _wo(lo, hi):
        return float(dLk[~np.asarray((wf >= lo) & (wf <= hi))].sum())
    rep["bars_6_8_without_halted_close"] = {
        "n": int(keep.sum()), "stress_L": float((sh[keep] * TL["unit_s"][keep]).sum()),
        "stress_N": float((sh[keep] * TN["unit_s"][keep]).sum()),
        "net_without_best_day": float(dLk.sum() - (dLk.max() if len(dLk) else 0.0)),
        "net_without_best_trade": float(nk.sum() - (nk.max() if len(nk) else 0.0)),
        "without_2020-02-15..04-30": _wo(*X20), "without_2020-21": _wo(*X2021)}
    rep["halted_close_by_year_and_pricing"] = {}
    for i in range(TL["n"]):
        if TL["halted"][i]:
            k = f"{TL['evs'][i].wf_year}/{TL['priced_by'][i]}"
            rep["halted_close_by_year_and_pricing"][k] = rep["halted_close_by_year_and_pricing"].get(k, 0) + 1
    for rd, T_ in (("L", TL), ("N", P["TN"])):
        if T_["n"] != TL["n"]:
            refuse(f"reading {rd} holds {T_['n']} trades, reading L {TL['n']}: the judged shares do not line up")
        items = []
        for i in range(T_["n"]):
            if T_["halted"][i]:
                ev = T_["evs"][i]
                res = split_cap([o for _, o, _ in ev.nxt[:10]], ev.nxt_sc[:10], ev.nxt_m[:10], T_["X"][i], T_["side"][i])
                items.append((res, T_["priced_by"][i] == "stress_flag", sh[i]))
        rep[f"halted_close_split_cap_{rd}"] = split_cap_report(items)
    return rep


def run_diagnostics(reg, cells, wf, bk, inR_cal, inp):
    P = cells["primary"]
    TL, TN, sh = P["TL"], P["TN"], P["shares"]
    dL = P["series"]["L"]
    dg = {}
    dg["event_path_L"] = event_path(TL, None, wf)
    dg["event_path_N"] = event_path(TN, None, wf)
    # premarket path from 04:00, price / P by minute, traded vs untraded event days
    acc = {"traded": [np.zeros(RTH0 - PRE0), np.zeros(RTH0 - PRE0)], "untraded": [np.zeros(RTH0 - PRE0), np.zeros(RTH0 - PRE0)]}
    for r in reg:
        if r.day is None:
            continue
        cff = r.day.close_ffill()[:RTH0 - PRE0] / r.ev.P
        k = "traded" if r.sig5.skip is None else "untraded"
        ok = np.isfinite(cff)
        acc[k][0][ok] += cff[ok]
        acc[k][1][ok] += 1
    dg["premarket_path_price_over_P"] = {k: (np.where(v[1] > 0, v[0] / np.maximum(v[1], 1), np.nan)).tolist() for k, v in acc.items()}
    om = [r.open_match for r in reg if r.open_match is not None]
    dg["daily_open_vs_0930_open_within_1c"] = {"share": float(np.mean(om)) if om else None, "n": len(om)}
    hv = {}
    for lo, hi in HALVES:
        m = np.asarray((wf >= lo) & (wf <= hi))
        hv[f"{lo:%Y-%m-%d}..{hi:%Y-%m-%d}"] = {"net_L": float(dL[m].sum()), "net_N": float(P["series"]["N"][m].sum())}
    dg["halves"] = hv
    py = {}
    notional = sh * TL["E"]
    for i, y in enumerate(WF_YEARS):
        m = np.array([wf_year_index(b) == i for b in TL["book"]], bool)
        trad = float((sh[m] * (TL["E"][m] + TL["X"][m])).sum())
        py[y] = {"trades": int(m.sum()), "net": float((sh[m] * TL["unit_p"][m]).sum()),
                 "mean_notional": float(notional[m].mean()) if m.any() else None,
                 "realised_cost_bps": float((sh[m] * TL["cost_p"][m]).sum() / trad * 1e4) if trad > 0 else None,
                 "locate": float((sh[m] * TL["loc_p"][m]).sum())}
    dg["per_year"] = py
    j, appended = join_book(dL, wf, bk)
    jj = j.to_numpy()
    eps = {}
    for lab, lst in (("R_45", bk.r_eps), ("book463_28", bk.dd_eps)):
        eps[lab] = [{"start": f"{s:%Y-%m-%d}", "end": f"{e:%Y-%m-%d}",
                     "pnl": float(jj[np.asarray((j.index >= s) & (j.index <= e))].sum())} for s, e in lst]
    dg["episodes"] = eps
    dg["appended_days"] = appended
    base = {**{k: pd.Series(v, index=bk.index) for k, v in bk.legs.items()}, "res_c": pd.Series(bk.res_c, index=bk.index)}
    Rset = pd.Series(bk.inR, index=bk.index).reindex(j.index, fill_value=False).to_numpy()
    corr = {}
    for k, s in base.items():
        s2 = s.reindex(j.index, fill_value=0.0).to_numpy()
        with np.errstate(all="ignore"):
            corr[k] = {"all": float(np.corrcoef(jj, s2)[0, 1]) if jj.std() > 0 and s2.std() > 0 else None,
                       "R_days": (float(np.corrcoef(jj[Rset], s2[Rset])[0, 1])
                                  if Rset.any() and jj[Rset].std() > 0 and s2[Rset].std() > 0 else None)}
    dg["correlation"] = corr
    nets = sh * TL["unit_p"]
    tot = float(nets.sum())
    dg["top10_share_of_net"] = {"trades": float(np.sort(nets)[::-1][:10].sum() / tot) if tot else None,
                                "days": float(np.sort(dL)[::-1][:10].sum() / tot) if tot else None}
    dg["without"] = {lab: float(dL[~np.asarray((wf >= lo) & (wf <= hi))].sum())
                     for lab, (lo, hi) in (("2020", X2020), ("2020-21", X2021), ("2022", X2022))}
    # cost curve (pure bps a side, no floor, no commission) x locate, at the primary's N* shares, reading L
    cc = {}
    tradN = sh * (TL["E"] + TL["X"])
    locN = sh * TL["E"] * (1.0 + TL["nights"])
    g = sh * TL["gross"]
    for b in COST_BPS:
        for lc in COST_LOC:
            cc[f"{b}bps/{lc:.3%}"] = float((g - tradN * b / 1e4 - locN * lc).sum())
    be = {f"locate_{lc:.0%}": float((g - locN * lc).sum() / tradN.sum() * 1e4) if tradN.sum() > 0 else None for lc in (0.0, 0.01)}
    bel = {}
    for b in BUCKETS:
        m = TL["bucket"] == b
        den = float(locN[m].sum())
        bel[b] = float((sh[m] * (TL["gross"][m] - TL["cost_p"][m])).sum() / den) if den > 0 else None
    dg["cost_curve"] = {"net_by_bps_a_side_and_locate": cc, "break_even_bps_a_side": be, "break_even_locate_by_bucket": bel}
    # capacity at N*
    cap_bind = float(np.mean(P["N_star"] > CAP_FRAC * TL["adv"])) if TL["n"] else None
    edv = np.array([getattr(r, "entry_dvol", np.nan) for r in TL["rs"]], float)
    sdv = np.array([r.stop_dvol if getattr(r, "stop_dvol", None) is not None else np.nan for r in TL["rs"]], float)
    per_day = pd.DataFrame({"d": TL["date"], "n": 1, "g": notional}).groupby("d").sum() if TL["n"] else pd.DataFrame({"n": [], "g": []})
    dg["capacity"] = {"cap_binds_share": cap_bind,
                      "median_entry_bar_dollar_volume": float(np.nanmedian(edv)) if np.isfinite(edv).any() else None,
                      "median_stop_bar_dollar_volume": float(np.nanmedian(sdv)) if np.isfinite(sdv).any() else None,
                      "median_trade_notional": float(np.median(notional)) if TL["n"] else None,
                      "most_names_one_session": int(per_day["n"].max()) if len(per_day) else 0,
                      "most_gross_short_notional_one_session": float(per_day["g"].max()) if len(per_day) else 0.0}
    dg["book_add"] = book_add(dL, wf, bk)
    # RUNNER2 link (PMFAIL side; the joint P&L prints in RUNNER2's --run)
    try:
        r2, _ = read_r2_schedule()
        nxt = dict(zip(inp.days[:-1], inp.days[1:]))
        same = np.array([(TL["symbol"][i], TL["date"][i]) in r2 for i in range(TL["n"])], bool)
        link = np.array([(TL["symbol"][i], nxt.get(TL["date"][i])) in r2 for i in range(TL["n"])], bool)
        dg["runner2_link"] = {"same_name_day_fills": int(same.sum()), "pnl_on_same_name_days": float(nets[same].sum()),
                              "pmfail_t_runner2_next_session": int(link.sum()), "pnl_on_linked": float(nets[link].sum())}
    except SystemExit as e:
        dg["runner2_link"] = {"error": str(e)}
    return dg


# ================================================================== CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="PMFAIL r1 Stage A (docs/PREREG_pmfail_r1_2026-10-06.md)")
    g = ap.add_mutually_exclusive_group(required=True)
    for m in ("counts", "overlap", "power", "null", "run"):
        g.add_argument(f"--{m}", action="store_true")
    ap.add_argument("--manifest", help="the pull's manifest.jsonl")
    ap.add_argument("--photo-sha", help="the manifest's sha256 as MANAGER named it")
    ap.add_argument("--probe-log", default=None, help="a text file holding the FB/META probe lines, if not in the manifest")
    a = ap.parse_args(argv)
    mode = next(m for m in ("counts", "overlap", "power", "null", "run") if getattr(a, m))
    tee = Tee(os.path.join(out_dir(), f"{mode}.txt"))
    sys.stdout = tee
    try:
        inp = load_inputs()
        if mode == "overlap":
            return mode_overlap(inp)
        if not (a.manifest and a.photo_sha):
            refuse("--manifest and --photo-sha are required for this mode")
        photo = Photograph(a.manifest, a.photo_sha, a.probe_log)
        print(f"photograph verified: {photo.verify(full=True)}", flush=True)
        return {"counts": mode_counts, "power": mode_power, "null": mode_null, "run": mode_run}[mode](inp, photo)
    finally:
        sys.stdout = tee.o
        tee.close()


if __name__ == "__main__":
    main()
