# -*- coding: utf-8 -*-
"""RUNNER2 r1 STAGE A - day 2 of a small-cap runner, short (docs/PREREG_runner2_r1_2026-10-06.md with AMENDMENT 0).

Research id MISC-RUNNER2-r1, lane DISCRECTIONALRY-TO-ALGO. Spec, implemented exactly: the RUNNER2 prereg (sections 2-14)
and the PMFAIL r1 prereg sections it points to (3 data, 4 S2 calendar map, 5 Rule 201 / halted into the close, 6 costs
and N*, 9 family null, 14 test M, 16 the one pull, 17 provenance). Where a body sentence and Amendment 0 disagree,
Amendment 0 governs.

  python tools/disc_runner2_r1_stageA.py --counts --manifest-sha HEX    section 11 step 1 + the count gate (bar 4). No P&L.
  python tools/disc_runner2_r1_stageA.py --power  --manifest-sha HEX    the coin-flip power line (SD and the 5% / 80% lines only)
  python tools/disc_runner2_r1_stageA.py --run    --manifest-sha HEX --null-sha HEX
                                                                  the real cells P and W, bars 1-12, verdict, reports

This harness computes NO null of its own (Amendment 0 Q4). PMFAIL r1's harness computes the ONE four-cell family null;
it imports this module's half: `null_context()` then `null_half(ctx)` (or `draw_once(rng, ctx)` interleaved with its own
draws), each RUNNER2 draw on its own default_rng(20261010). `family_summary(stats)` turns the (n, 4, 3) array into the
summary block this harness reads back with `read_null()` (contract in NULL_CONTRACT below).

Shared mechanics (Day, halt_info, bars5, walk, halted_close_exit, side_cost, unit_net, shares_at, solve_nstar, the
statistics, verdict, write_once) are importable by PMFAIL's harness: this module never imports PMFAIL's, so there is no
cycle.

Data: the photographed daily cache and calendar through tools/disc_gapper_namedays.py (the ONE builder; its csv must
re-hash to the posted e9ca777a...), MANAGER's one pull under C:\\EdgeLog\\alpaca_cache\\disc_gapper (manifest.jsonl +
bars\\<SYM>_<DATE>.json + quotes\\<SYM>_<DATE>_runner2_marks.json, the layout of C:\\EdgeLog\\manager\\_scripts\\
disc_gapper_pull.py), the book files under _anatomy_cache. Every input is sha256-checked before anything is computed;
nothing on or after 2025-06-30 is read except the two named exceptions (the uncut last-bar DATE; name_change rows).
This module opens no socket and imports no requests / alpaca_rate / key loader at import time.
"""
import argparse
import hashlib
import io
import json
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for _p in (HERE, os.path.join(HERE, "rocfrontier")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import power_line as PL  # noqa: E402   numpy / pandas / argparse only

REGISTERED_NAME = "tools/disc_runner2_r1_stageA.py"     # the prereg's registered harness path (header line 56; PMFAIL s.9)
PREREG_R2 = "PREREG_runner2_r1_2026-10-06.md"
PREREG_PM = "PREREG_pmfail_r1_2026-10-06.md"
PREREG_SHA_LF = {PREREG_R2: "eda8954ed206957b5bc7a7bc0a51110061912a4f8e0c7bc7f313cc3cf117356d",
                 PREREG_PM: "18a009f09f1922541de346b6ee45cb32bc82cacd2c151028ec4dc7b8b6815550"}

# ------------------------------------------------------------------ windows (section 7: Y = 3,285 / 365.25)
CUT = pd.Timestamp("2025-06-30")
WF0, WF1 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")
YEARS = (WF1 - WF0).days / 365.25
WF_YEARS = tuple(f"{y}-{(y + 1) % 100:02d}" for y in range(2016, 2025))
BUCKETS = ("lt5", "5to20")
DELISTED_BEFORE = pd.Timestamp("2026-06-01")
HALVES = ((WF0, pd.Timestamp("2021-12-31")), (pd.Timestamp("2022-01-01"), WF1))
X20 = (pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-30"))
Y2021 = (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31"))
Y2022 = (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31"))
VOL_END = pd.Timestamp("2018-07-01")       # c over 2016-07-01 .. 2018-06-30
# The NYSE 13:00 half days of tools/import_alpaca_stocks.py lines 139-145 (asserted equal in load_env; copied so that
# importing this module does not import `requests`).
EARLY_CLOSE_DATES = frozenset({
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23",
    "2018-12-24", "2019-07-03", "2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24",
    "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29",
    "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27",
    "2026-12-24", "2027-11-26"})

# ------------------------------------------------------------------ minutes after ET midnight (bar START stamps)
PRE0, RTH0, RTH1, RTH1_HALF = 240, 570, 960, 780
NMIN = RTH1 - PRE0                          # 720 slots: minutes 04:00 .. 15:59
WIN_CLOSE0, WIN_CLOSE1 = 585, 840           # 5m close times 09:45 .. 14:00 (k = 2 .. 53)
ENTRY_SPAN = 5                              # entry bar starts in [B close, B close + 4 min]
HALT_K, HALT_K4 = 5, 4
EPS = 1e-9                                  # price-vs-level comparisons (stops, SSR); VWAP comparisons are exact
TICK = 0.01
W_MULT = 1.5
SSR_FRAC = 0.90
THIN_SHARE = 0.10
MARKS = ("09:45", "10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00")

# ------------------------------------------------------------------ size, cost, locate (section 7 / PMFAIL s.6)
GRID = np.arange(5000.0, 500000.0 + 1.0, 500.0)
DD_TARGET = 30000.0
CAP_FRAC = 0.01
SCALE_FREE_N = 5000.0
COMM, HALF_TICK, STRESS_ADD = 0.0035, 0.005, 0.01
LOC_BASE, LOC_STRESS = 0.01, 0.02
PRIOR_H50 = {"lt5": 0.0050, "5to20": 0.0025}
PRIOR_H75 = {b: 2.0 * v for b, v in PRIOR_H50.items()}
BUCKET_MIN = 20
FIXED_NOTIONALS = (5000.0, 10000.0, 25000.0, 50000.0, 100000.0, 250000.0, 500000.0)
STOP_EDGES = (0.02, 0.05, 0.10, 0.20)
STOP_LABELS = ("0-2", "2-5", "5-10", "10-20", ">20")
COST_BPS = (0.0, 10.0, 25.0, 50.0, 100.0)
COST_LOC = (0.0, 0.005, 0.01, 0.02)

# ------------------------------------------------------------------ bars, null, power (sections 9, 10)
COUNT_MEAN, COUNT_MIN, THIN_YEAR = 50.0, 100, 25
NULL_DRAWS, SEED_NULL_R2, SEED_NULL_PM, MAX_TRIES = 500, 20261010, 20261006, 21
SEED_COIN, POWER_SEED, POWER_BLOCK, POWER_DRAWS = 20261006, 20261005, 20, 1000
BOOK_ADD_SEED, VOL_SHARE = 20261005, 0.25
BOOK_FACTS, LINE_FACTS, BOOK_REF_BARS = (93.81, 3.816), (120.82, 3.916), (98.50, 3.816)
R_DAYS, R_EPIS, DD_DAYS, DD_EPIS, BOOK_N = 762, 45, 460, 28, 2626
PCTS = (("p50", 50.0), ("p95", 95.0), ("p97.5", 97.5))
STATS3 = ("roc30", "t", "rsum")

# ------------------------------------------------------------------ pinned inputs (section 4)
SHA = {
    "daily_raw.parquet": "fa42412d579ae673815bea25e1c14f9c87a93904af779ccffb03333c8e1bdccd",
    "daily_split.parquet": "083f8c23d1d62cf7bda99d5c9a6373130c336ac605f57db5eeac832504281f6d",
    "assets.csv": "b85928ff655a883dd3eb44d8d96b3b745ffe2f5f0e0ca0991485895f5e960991",
    "siporb_cache_manifest": "380b05f2e0c4dfa32faabf2c86311f869d7371d3810a801bbf8a6c1f9ade4b78",
    "corporate_actions_wide.csv": "e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5",
    "residual_days.csv": "bfe64d87a2cf6fd569181ffae9092317653844126de075fe64844430ac189f60",
    "a2.json": "0c27cb47fe245cd8fbbcc1bc3eb0881ea0edefba74d45b7821a059dc7e4c9214",
    "line.csv": "98f3edc743625b3742f13a972cab35178658feaa7f506e56e27f77f56e9c38ad",
    "episodes.csv": "ebfb67c03a258a0d4efe73a20a2c7027fd5eb3d25403f17d8e071cb4626a9af4",
    "book463_daily.csv": "d1543735b5408f50be5971089e00a800f8e510af3d4a63678ff8939f41277dff",
    "VIX_History.csv": "6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a",
    "namedays_r1.csv": "e9ca777ae11a24b592d8760482f5e4e0ccdc5e1e072cfbe910787d86b47f5e8c",
}
NAMEDAYS_SHA = SHA["namedays_r1.csv"]
PROBE_ENDPOINTS = ("1Day", "5Min", "1Min", "quotes")

# Every reading this harness pins where the prereg text leaves a choice: (quoted prereg line, the reading). Filed into
# counts.json and stage_a.json so the record carries them.
INTERPRETATIONS = (
    ("header: 'Harness (written only after GO): `tools/disc_runner2_r1_stageA.py`'",
     "this file is the registered path (renamed from the builder's runner2_r1_stageA.py before any number); PMFAIL's "
     "harness imports it as disc_runner2_r1_stageA"),
    ("s.9: 'take P's real entry schedule on Omega (same entry bars, E, shares at P's N*)'",
     "P's N* is solved from P's real-direction drawdown, which the power line must precede; the coin-flip leg solves "
     "its own N* with the same solver on its own series (lane clarification, filed before any number)"),
    ("s.11 step 1: '... the spread statistics; cap binding at N*. Then the count gate.'",
     "the count step prints cap binding at fixed notionals $5k..$500k (no N* exists before P&L); the at-N* capacity "
     "line prints in --run"),
    ("s.5: 'Each night held adds one locate charge.'",
     "nights = market sessions from D2 to the booking session; locate charges = 1 + nights; a stress-priced exit "
     "booked on D2+1 is 1 night, one booked on D2 (D2+1 on or after the cut) is 0"),
    ("s.6: 'exit at the open of the NEXT present 1m bar; if none comes before 16:00, the halted-into-close rule'",
     "the next present bar may start inside 15:55-15:59"),
    ("s.6: 'any D2 regular 1m low from 09:30 up to B's close time <= 0.9 x c(D1)'",
     "1m bars starting 09:30 .. B close time - 1 minute (B's own minutes included); level comparisons use a 1e-9 "
     "tolerance, VWAP comparisons are exact"),
    ("s.6: 'Cell W (neighbour): S_W = E + 1.5 x (S - E)'",
     "W is not rounded (PMFAIL's S2 says 'rounded up to the cent'; RUNNER2's W does not)"),
    ("s.9: 'if blocked, redraw without replacement up to 20 times'",
     "per draw and Omega session (Omega sorted by date, symbol): perm = rng.permutation(n candidate bars); the first "
     "eligible bar among perm[:21] (the first draw + 20 redraws); none = no null trade (counted)"),
    ("s.9: 'the family MAX over the four cells ... of ROC30, of t, and of the R-sum'",
     "a NaN statistic (t with sd 0) counts as -inf in the max and is counted; percentiles are numpy linear"),
    ("s.10 bar 7: 'Net > 0 at stress cost (stress spread + 2% locate)'",
     "reading L (bar 11 binds reading N on its own)"),
    ("s.10 bar 12: 'have net > 0 at stress cost and PF >= 1.05'",
     "net at stress cost; PF on the subset's base-cost trade nets (the judged cost of bar 3); the stress PF prints "
     "beside it"),
    ("s.10 bars 8-9: 'Net > 0 without its best day, AND net > 0 without its best trade' / meme windows",
     "the judged daily series by exit session: minus its largest day; minus the largest trade net; windows drop "
     "daily rows by exit session"),
    ("s.4: 'a name-day whose mark requests are all refused (after retries) takes its bucket's prior h50'",
     "the pull saves no marks file when ANY mark is refused, so such a name-day has no served value on file: it takes "
     "the prior h50, flagged (all-refused and some-refused counted apart); it counts toward the bucket's n"),
    ("s.9 OPEN2: 'SSR-at-open sessions skipped, and printed with the Rule-201-legal fill'",
     "OPEN2's legal fill = a short limit at the 09:30 open + $0.01 posted at 09:30, filled at the limit if a bar "
     "starting 09:30..09:34 has high >= limit + $0.01; OPEN2 has no stop, so its halted-into-close stress price is "
     "the last pre-halt close"),
    ("s.6 legal fill: '... then the cell's stop and exit'",
     "judged from the fill bar inclusive (its own high counts against the stop: conservative); no resume-bar rule for "
     "a resting limit; E >= S is no trade"),
    ("s.5: 'every halt rule also reruns with 4'",
     "the 4-minute reading reruns the schedule (resume-bar rule) and the exits with k = 4, re-priced at P's N*"),
    ("s.4 / PMFAIL s.17: 'each printing \"SAME MAPPING\"', logged in the manifest",
     "the harness refuses unless the probe text (manifest records whose kind starts with 'probe', plus an optional "
     "--probe-log file whose sha256 is stamped, as the PMFAIL harness accepts) holds a SAME MAPPING line for each of "
     "1Day, 5Min, 1Min and quotes"),
    ("s.4: 'Every response page is saved byte for byte, with its sha256, in a manifest'",
     "single-page bar files are checked against their page sha; merged multi-page bar files and marks files carry no "
     "file-level sha in the manifest, so their sha256 is recorded into the stamp (later modes refuse if it moves)"),
    ("s.9 VIX: 'P&L by prior-day VIX tercile (cut points = terciles over the WF stretch)'",
     "the last CBOE close dated before D2; cut points = the 33.33 / 66.67 linear percentiles of closes "
     "2016-07-01..2025-06-29"),
    ("s.7: 'break-even locate (the % a trade that takes net to zero) per price bucket'",
     "base spread + commission held; locate solved: net(locate 0) / sum(shares x E x (1 + nights))"),
    ("s.7: 'stop-distance buckets (S - E) / E of 0-2 / 2-5 / 5-10 / 10-20 / > 20%'",
     "[0,2) [2,5) [5,10) [10,20] (20,inf)"),
    ("s.11: 'Parity is asserted first: #463 WF 93.81 / 3.816; L 120.82 / 3.916'",
     "the statistics rounded to the printed digits equal the printed figures"),
    ("s.4: 'A bar with v = 0 is treated as missing.'",
     "bars with v <= 0 or a price <= 0 are dropped at load (counted, expected 0); identical duplicates dropped "
     "(counted), conflicting duplicates refuse"),
    ("s.6: 'The entry bar is the first present 1m bar with start in [B close time, B close time + 4 min]'",
     "block reasons in order: no_signal, ssr_active, no_fill_bar, resume_bar, E_ge_S"),
    ("s.10 bar 1: 'that sum without the leg's 3 best R days > 0'",
     "the R-day sum after dropping the 3 largest daily values among R's days (leg on the book index, appended days "
     "are not R days)"),
    ("s.9 power: 'Each trade gets a fair-coin direction from default_rng(20261006)'",
     "rng.choice([-1.0, 1.0], size=n) over P's fills sorted by (D2, symbol): -1 short, +1 long"),
    ("s.8 condition 4: 'a reverse split took effect on a session in [D2 - 60 calendar days, D2 - 1 day]'",
     "sessions dated in that closed range; (i) F / F' > 1.005 recomputed on the listed symbols (parity with the "
     "builder's S1 asserted); (ii) calendar reverse_split rows through the name_change chain; (iii) the builder's "
     "registered test M (its calibration decides price-only vs volume form)"),
    ("s.8: 'delisted = last daily bar before 2026-06-01, the date read from the uncut cache'",
     "a (symbol, date)-only read of daily_raw.parquet with no date filter; inactive = every assets.csv row inactive; "
     "ambiguous = mixed rows; shortable / easy_to_borrow None when the rows disagree; reused = listed twice"),
    ("s.10 bars 5 / 8 / 9: years and windows",
     "per-year nets and the meme / best-day reads book on the exit session; fill counts (bar 4) by D2"),
)

NULL_CONTRACT = """null.json (written by PMFAIL r1's harness, tools/pmfail_r1_stageA.py mode_null; read here by read_null):
  {"seeds": {"pmfail": 20261006, "runner2": 20261010}, "draws": 500, "percentile_method": "linear",
   "cells": ["pm_primary", "pm_neighbour", "r2_P", "r2_W"], "statistics": ["roc30", "t", "rsum"],
   "omega": {"n": ctx.omega_n, "sha256": ctx.omega_sha256}   (= RUNNER2 counts.json omega.sha256 / omega_sha256),
   "runner2_harness": "<file name>", "runner2_harness_sha256_lf": <sha256_lf of this file>,
   "summary": {"max4" | "pmfail_max2" | "runner2_max2": {"roc30" | "t" | "rsum": {"p50", "p95", "p97.5"}},
               "notion_b_roc30": {...}, "nan_cells": n}}       (= family_summary(stats) here)
null.sha256 next to it in sha256sum format; the lane posts the hex; `--run --null-sha HEX` checks the bytes.
PMFAIL calls null_context(photo=..., book=...) -> ctx (.omega_sha256, .omega_n) and null_half(ctx, n=500,
seed=20261010) -> ((n, 2, 3) array [draw, P / W, roc30 / t / rsum], {name: per-draw list})."""


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
        return sha256_bytes(f.read().replace(b"\r\n", b"\n"))


def home():
    return os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def out_dir():
    return os.path.join(home(), "_anatomy_cache", "disc_runner2_r1")


def pm_dir():
    return os.path.join(home(), "_anatomy_cache", "disc_pmfail_r1")


def pull_root():
    return os.path.join(home(), "alpaca_cache", "disc_gapper")


def clean(o):
    """json-safe: numpy scalars -> python, NaN / inf -> None, Timestamps -> YYYY-MM-DD, tuples -> lists"""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [clean(v) for v in o.tolist()]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, pd.Timestamp):
        return f"{o:%Y-%m-%d}"
    return o


def dumps(obj):
    return (json.dumps(clean(obj), indent=1, sort_keys=True) + "\n").encode("utf-8")


def write_once(path, data):
    """a filed output is never overwritten with different bytes (identical bytes: no-op)"""
    if os.path.exists(path):
        with open(path, "rb") as f:
            if f.read() == data:
                return path
        refuse(f"{path} is on file with different bytes - outputs are filed once")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def csv_bytes(df):
    return df.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode("utf-8")


def wf_year_of(d):
    d = pd.Timestamp(d)
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def hm(m):
    return None if m is None else f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def stop_bucket(d):
    if d < STOP_EDGES[0]:
        return STOP_LABELS[0]
    if d < STOP_EDGES[1]:
        return STOP_LABELS[1]
    if d < STOP_EDGES[2]:
        return STOP_LABELS[2]
    if d <= STOP_EDGES[3]:
        return STOP_LABELS[3]
    return STOP_LABELS[4]


def is_half_day(d):
    return f"{pd.Timestamp(d):%Y-%m-%d}" in EARLY_CLOSE_DATES


# ================================================================== one name-day of 1m bars (section 4 stamps)
@dataclass
class Day:
    """1m bars of one session on a dense minute axis (slot i = minute 240 + i; minute = START of the bar, ET)."""
    date: pd.Timestamp
    rth1: int
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    vw: np.ndarray
    present: np.ndarray
    info: dict = field(default_factory=dict)
    _cache: dict = field(default_factory=dict, repr=False)

    def nxt(self):
        """nxt[i] = the first present slot >= i (or -1)"""
        if "nxt" not in self._cache:
            out = np.full(NMIN + 1, -1, np.int64)
            for i in range(NMIN - 1, -1, -1):
                out[i] = i if self.present[i] else out[i + 1]
            self._cache["nxt"] = out
        return self._cache["nxt"]

    def reg(self):
        """(cummax regular high, cummin regular low) over present bars 09:30..m, per slot (NaN / inf before any bar)"""
        if "reg" not in self._cache:
            a, b = RTH0 - PRE0, self.rth1 - PRE0
            hh = np.where(self.present, self.h, -np.inf)
            ll = np.where(self.present, self.l, np.inf)
            cmh = np.full(NMIN, -np.inf)
            cml = np.full(NMIN, np.inf)
            cmh[a:b] = np.maximum.accumulate(hh[a:b])
            cml[a:b] = np.minimum.accumulate(ll[a:b])
            self._cache["reg"] = (cmh, cml)
        return self._cache["reg"]


def make_day(date, m, o, h, l, c, v, vw=None):
    """arrays of 1m bars (minute of START, ET) -> Day. Bars with v <= 0, a price <= 0 or a non-finite field are dropped
    and counted (s.4: 'A bar with v = 0 is treated as missing'); a minute outside 04:00..15:59 is dropped and counted;
    identical duplicates dropped (counted); conflicting duplicates refuse."""
    date = pd.Timestamp(date).normalize()
    m = np.asarray(m, np.int64)
    cols = [np.asarray(x, float) for x in (o, h, l, c, v)]
    vwa = np.full(len(m), np.nan) if vw is None else np.asarray(vw, float)
    info = {"bars_in": int(len(m)), "dropped_v_le_0": 0, "dropped_price_le_0": 0, "dropped_outside_window": 0,
            "dropped_identical_duplicate": 0}
    ok = np.ones(len(m), bool)
    out_w = (m < PRE0) | (m >= RTH1)
    info["dropped_outside_window"] = int(out_w.sum())
    ok &= ~out_w
    vbad = ~np.isfinite(cols[4]) | (cols[4] <= 0)
    info["dropped_v_le_0"] = int((vbad & ok).sum())
    ok &= ~vbad
    pbad = np.zeros(len(m), bool)
    for x in cols[:4]:
        pbad |= ~np.isfinite(x) | (x <= 0)
    info["dropped_price_le_0"] = int((pbad & ok).sum())
    ok &= ~pbad
    arrs = {k: np.full(NMIN, np.nan) for k in ("o", "h", "l", "c", "v", "vw")}
    seen = {}
    for j in np.flatnonzero(ok):
        i = int(m[j]) - PRE0
        rec = (cols[0][j], cols[1][j], cols[2][j], cols[3][j], cols[4][j], vwa[j])
        if i in seen:
            prev = seen[i]
            if all((a == b) or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))
                   for a, b in zip(prev, rec)):
                info["dropped_identical_duplicate"] += 1
                continue
            refuse(f"conflicting duplicate 1m bars at {hm(m[j])} on {date:%Y-%m-%d}")
        seen[i] = rec
        for k, val in zip(("o", "h", "l", "c", "v", "vw"), rec):
            arrs[k][i] = val
    present = np.isfinite(arrs["v"]) & (arrs["v"] > 0)
    rth1 = RTH1_HALF if is_half_day(date) else RTH1
    return Day(date, rth1, arrs["o"], arrs["h"], arrs["l"], arrs["c"], arrs["v"], arrs["vw"], present, info)


def et_minutes(t, date):
    """Alpaca `t` (UTC RFC-3339, bar START) -> ET minute after midnight. Refuses a stamp with seconds, or an ET date
    other than the requested session."""
    ts = pd.to_datetime(pd.Series(list(t), dtype=object), utc=True)
    et = ts.dt.tz_convert("America/New_York")
    if len(et) and ((et.dt.second != 0) | (et.dt.microsecond != 0) | (et.dt.nanosecond != 0)).any():
        refuse(f"a 1m bar stamp with nonzero seconds on {pd.Timestamp(date):%Y-%m-%d}")
    d = et.dt.tz_localize(None).dt.normalize()
    if len(d) and (d != pd.Timestamp(date).normalize()).any():
        refuse(f"a 1m bar whose ET date is not the requested session {pd.Timestamp(date):%Y-%m-%d}")
    return (et.dt.hour * 60 + et.dt.minute).to_numpy(np.int64)


def day_from_records(recs, date):
    """served bar dicts (t, o, h, l, c, v, n, vw) -> Day"""
    if not recs:
        return make_day(date, [], [], [], [], [], [], [])
    m = et_minutes([r.get("t") for r in recs], date)

    def col(k):
        return [np.nan if r.get(k) is None else r.get(k) for r in recs]
    return make_day(date, m, col("o"), col("h"), col("l"), col("c"), col("v"), col("vw"))


# ================================================================== the photograph (MANAGER's one pull)
@dataclass
class BarsResult:
    status: str             # ok / empty / missing / refused
    feed: str
    day: object


class Photograph:
    """MANAGER's pull (C:\\EdgeLog\\manager\\_scripts\\disc_gapper_pull.py layout): manifest.jsonl, bars\\SYM_DATE.json
    (one served body, or the pages merged as {"bars": {SYM: [...]}, "pages": n}), quotes\\SYM_DATE_runner2_marks.json
    ({"marks": {HH:MM: served body}}). The manifest's own sha256 is the photograph's id and must equal the value MANAGER
    names. verify() runs before any bar is parsed."""

    def __init__(self, root=None, manifest_sha=None, namedays_sha=NAMEDAYS_SHA, require_probe=True, probe_log=None):
        self.root = root or pull_root()
        self.manifest_sha = manifest_sha
        self.manifest_sha256 = manifest_sha                 # the PMFAIL harness's attribute name
        self.namedays_sha = namedays_sha
        self.require_probe = require_probe
        self.probe_log = probe_log
        self.verified = False
        self.status = {}
        self.mark_status = {}
        self.stamp = {}
        self.feed = "sip"
        self._cache = {}

    def _bars_path(self, sym, date):
        return os.path.join(self.root, "bars", f"{sym}_{date}.json")

    def _marks_path(self, sym, date):
        return os.path.join(self.root, "quotes", f"{sym}_{date}_runner2_marks.json")

    def verify(self, bars_rows, mark_rows):
        """bars_rows / mark_rows: iterables of (symbol, 'YYYY-MM-DD') this harness will read."""
        mpath = os.path.join(self.root, "manifest.jsonl")
        if not self.manifest_sha:
            refuse("no manifest sha256 named (--manifest-sha): the photograph's id is MANAGER's value")
        if not os.path.exists(mpath):
            refuse(f"pull manifest not on file: {mpath}")
        with open(mpath, "rb") as f:
            data = f.read()
        got = sha256_bytes(data)
        if got != self.manifest_sha:
            refuse(f"manifest.jsonl hashes to {got}, MANAGER named {self.manifest_sha}")
        recs = []
        for ln in data.splitlines():
            if ln.strip():
                try:
                    recs.append(json.loads(ln))
                except ValueError:
                    refuse("manifest.jsonl holds a line that is not json")
        heads = [r for r in recs if r.get("kind") == "run_header"]
        if not heads or any(h.get("list_sha256") != self.namedays_sha for h in heads):
            refuse(f"the manifest does not cite namedays_r1.csv {self.namedays_sha} in every run header")
        lines = [json.dumps(r) for r in recs if str(r.get("kind", "")).startswith("probe")]
        probe_sha = None
        if self.probe_log:
            with open(self.probe_log, "rb") as f:
                pb = f.read()
            probe_sha = sha256_bytes(pb)
            lines += pb.decode("utf-8", "replace").splitlines()
        probe = {ep: any(ep.lower() in ln.lower() and "SAME MAPPING" in ln for ln in lines) for ep in PROBE_ENDPOINTS}
        missing_probe = [ep for ep in PROBE_ENDPOINTS if not probe.get(ep)]
        if self.require_probe and missing_probe:
            refuse("the FB/META probe is not logged as SAME MAPPING for " + ", ".join(missing_probe)
                   + " (in the manifest or the named probe log; PMFAIL r1 section 17: any other result stops the pull)")
        by_bars, by_marks = {}, {}
        feeds = set()
        for r in recs:
            k = r.get("kind", "")
            if k == "bars":
                by_bars.setdefault((r.get("symbol"), r.get("date")), []).append(r)
            elif k == "quotes_runner2_mark":
                by_marks.setdefault((r.get("symbol"), r.get("date")), []).append(r)
            if k == "bars" or str(k).startswith("quotes"):
                u = str(r.get("url", ""))
                if "feed=sip" in u:
                    feeds.add("sip")
                elif "feed=iex" in u:
                    feeds.add("iex")
                else:
                    feeds.add("unnamed")
        if "unnamed" in feeds:
            refuse("a bars / quotes request in the manifest does not name its feed (an unnamed feed can default to IEX)")
        self.feed = "iex" if "iex" in feeds else "sip"
        counts = {"ok": 0, "missing": 0, "refused": 0}
        files = {}
        for sym, date in sorted(set(bars_rows)):
            if pd.Timestamp(date) >= CUT:
                refuse(f"a bar request on or after 2025-06-30 ({sym} {date})")
            rr = by_bars.get((sym, date))
            if not rr:
                refuse(f"photograph incomplete: no manifest record for bars {sym} {date}")
            p = self._bars_path(sym, date)
            ok200 = [r for r in rr if r.get("status") == 200 and os.path.basename(str(r.get("file") or "")) ==
                     os.path.basename(p)]
            if os.path.exists(p):
                if not ok200:
                    refuse(f"bars file {p} has no status-200 record in the manifest")
                fsha = sha256_file(p)
                single = [r for r in ok200 if int(r.get("pages") or 1) == 1]
                if single:
                    if fsha != single[-1].get("sha256"):
                        refuse(f"bars file {p} hashes to {fsha}, the manifest page says {single[-1].get('sha256')}")
                else:
                    files[os.path.basename(p)] = fsha              # merged pages: file sha recorded into the stamp
                st = "ok"
            else:
                st = "refused" if any(r.get("status") == 403 for r in rr) else "missing"
            self.status[(sym, date)] = st
            counts[st] += 1
        mcounts = {"ok": 0, "refused_all": 0, "refused_some": 0}
        for sym, date in sorted(set(mark_rows)):
            p = self._marks_path(sym, date)
            rr = by_marks.get((sym, date))
            if os.path.exists(p):
                st = "ok"
                files[os.path.basename(p)] = sha256_file(p)
            elif not rr:
                refuse(f"photograph incomplete: no manifest record for the marks of {sym} {date}")
            else:
                st = "refused_all" if all(r.get("status") != 200 for r in rr) else "refused_some"
            self.mark_status[(sym, date)] = st
            mcounts[st] += 1
        self.stamp = {"manifest_sha256": got, "manifest_bytes": len(data), "records": len(recs), "feed": self.feed,
                      "probe": {ep: bool(probe.get(ep)) for ep in PROBE_ENDPOINTS}, "probe_log_sha256": probe_sha,
                      "bars": counts, "marks": mcounts,
                      "unpaged_file_sha256": dict(sorted(files.items()))}
        self.verified = True
        return self.stamp

    def bars(self, sym, date):
        date = f"{pd.Timestamp(date):%Y-%m-%d}"
        if not self.verified:
            refuse("bars read before the photograph was verified")
        key = (sym, date)
        if key in self._cache:
            return self._cache[key]
        st = self.status.get(key)
        if st is None:
            refuse(f"bars {sym} {date} are not on the verified list")
        if st != "ok":
            res = BarsResult(st, self.feed, None)
        else:
            with open(self._bars_path(sym, date), "rb") as f:
                body = json.loads(f.read())
            b = body.get("bars")
            recs = (b.get(sym) or []) if isinstance(b, dict) else (b or [])
            day = day_from_records(recs, date)
            res = BarsResult("ok" if day.present.any() else "empty", self.feed, day)
        self._cache[key] = res
        return res

    def marks(self, sym, date):
        """-> (status, {mark: (bp, ap, t_ns) or None}, served_desc_all)"""
        date = f"{pd.Timestamp(date):%Y-%m-%d}"
        st = self.mark_status.get((sym, date))
        if st is None:
            refuse(f"marks {sym} {date} are not on the verified list")
        if st != "ok":
            return st, {}, None
        with open(self._marks_path(sym, date), "rb") as f:
            obj = json.loads(f.read())
        vals, desc = parse_marks(obj, sym, date)
        return "ok", vals, desc


def parse_marks(obj, sym, date):
    """{"marks": {HH:MM: body}} -> ({mark: (bp, ap, t_ns) or None}, all marks served by sort=desc). The NBBO in force at
    m = the last quote in [m - 60 s, m]."""
    out, desc = {}, True
    marks = obj.get("marks") or {}
    for mk in MARKS:
        body = marks.get(mk) or {}
        if "note" in body:
            desc = False
        qs = body.get("quotes")
        lst = (qs.get(sym) if isinstance(qs, dict) else qs) or []
        m_ns = pd.Timestamp(f"{date} {mk}:00", tz="America/New_York").value
        best = None
        for q in lst:
            try:
                t_ns = pd.Timestamp(q.get("t")).value
            except (ValueError, TypeError):
                continue
            if m_ns - 60_000_000_000 <= t_ns <= m_ns and (best is None or t_ns >= best[2]):
                best = (q.get("bp"), q.get("ap"), t_ns)
        out[mk] = best
    return out, desc


def mark_value(vals):
    """name-day half-spread: median of (ap - bp) / (ap + bp) over valid marks (drop no quote, bp <= 0, ap <= 0, ap <= bp)"""
    hs = []
    for mk in MARKS:
        q = vals.get(mk)
        if q is None:
            continue
        bp, ap = q[0], q[1]
        if bp is None or ap is None or not (bp > 0 and ap > 0 and ap > bp):
            continue
        hs.append((ap - bp) / (ap + bp))
    return float(np.median(hs)) if hs else None


def bucket_spreads(values):
    """values: {bucket: [(value, refused_flag), ...]} -> {bucket: h50, h75, n, refused, source}. A bucket with fewer than
    20 name-day values uses the priors; a refused day already carries its bucket's prior h50."""
    out = {}
    for b in BUCKETS:
        vs = [v for v, _ in values.get(b, []) if v is not None]
        nref = sum(1 for _, r in values.get(b, []) if r)
        if len(vs) >= BUCKET_MIN:
            out[b] = {"h50": float(np.percentile(vs, 50)), "h75": float(np.percentile(vs, 75)), "n": len(vs),
                      "refused_days_at_prior": nref, "source": "measured"}
        else:
            out[b] = {"h50": PRIOR_H50[b], "h75": PRIOR_H75[b], "n": len(vs), "refused_days_at_prior": nref,
                      "source": "priors (fewer than 20 name-day values)"}
    return out


# ================================================================== session mechanics (sections 4-6)
@dataclass
class HaltInfo:
    runs: list
    resume: set
    halted_close: bool


def halt_info(day, k=HALT_K):
    """runs of >= k consecutive regular minutes (09:30..close-1) with no present bar; a run may start at 09:30 or reach
    the close. resume = the minute of the first present bar after each run. halted_close = no bar in the exit window."""
    a, b = RTH0 - PRE0, day.rth1 - PRE0
    reg = day.present[a:b]
    runs, i, n = [], 0, len(reg)
    while i < n:
        if reg[i]:
            i += 1
            continue
        j = i
        while j < n and not reg[j]:
            j += 1
        if j - i >= k:
            runs.append((RTH0 + i, RTH0 + j))
        i = j
    resume = {e for _, e in runs if e < day.rth1}
    hc = not day.present[day.rth1 - 5 - PRE0: day.rth1 - PRE0].any()
    return HaltInfo(runs, resume, hc)


@dataclass
class Bar5:
    k: int
    start: int
    close_t: int
    o: float
    h: float
    l: float
    c: float
    v: float
    last_m: int


def bars5(day):
    """regular 5m bars from 1m (anchored 09:30): o first present open, h max, l min, c LAST present close, v sum; a 5m bar
    with no present 1m bar does not exist; known at start + 5 ('close time')."""
    out = []
    for k in range((day.rth1 - RTH0) // 5):
        a = RTH0 + 5 * k
        i = a - PRE0
        pres = day.present[i:i + 5]
        if not pres.any():
            continue
        js = np.flatnonzero(pres)
        out.append(Bar5(k, a, a + 5, float(day.o[i + js[0]]), float(np.max(day.h[i:i + 5][pres])),
                        float(np.min(day.l[i:i + 5][pres])), float(day.c[i + js[-1]]), float(np.sum(day.v[i:i + 5][pres])),
                        a + int(js[-1])))
    return out


def vwap_curve(day):
    """VWAP through each regular minute (anchored 09:30, present bars only, premarket excluded): p = vw, or (h+l+c)/3
    when vw is missing or <= 0. -> (vwap per slot, n fallback bars, n bars)"""
    a, b = RTH0 - PRE0, day.rth1 - PRE0
    pres = day.present[a:b]
    good = np.isfinite(day.vw[a:b]) & (day.vw[a:b] > 0)
    p = np.where(good, day.vw[a:b], (day.h[a:b] + day.l[a:b] + day.c[a:b]) / 3.0)
    pv = np.where(pres, p * day.v[a:b], 0.0)
    vv = np.where(pres, day.v[a:b], 0.0)
    cpv, cv = np.cumsum(pv), np.cumsum(vv)
    out = np.full(NMIN, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[a:b] = np.where(cv > 0, cpv / cv, np.nan)
    return out, int((pres & ~good).sum()), int(pres.sum())


def find_signal(b5, vw, nocross=False):
    """the FIRST 5m bar with close time in [09:45, 14:00], c5 < VWAP, and `seen_above` set by a strictly EARLIER 5m bar
    (c5 >= VWAP). NOCROSS (report): the first close below VWAP in the window, no cross required."""
    seen = False
    for b in b5:
        if b.close_t > WIN_CLOSE1:
            break
        x = vw[b.last_m - PRE0]
        if WIN_CLOSE0 <= b.close_t and b.c < x and (seen or nocross):
            return b
        if b.c >= x:
            seen = True
    return None


def candidate_eval(day, b, c1, hinfo):
    """the entry rules at 5m bar b -> (status, entry_m, E, S). status: filled / ssr_active / no_fill_bar / resume_bar /
    E_ge_S. S = the max regular high through b's last present 1m bar + $0.01."""
    cmh, cml = day.reg()
    ct = b.close_t
    if cml[ct - 1 - PRE0] <= SSR_FRAC * c1 + EPS:
        return "ssr_active", None, None, None
    nx = day.nxt()
    j = int(nx[ct - PRE0])
    if j < 0 or j + PRE0 > ct + ENTRY_SPAN - 1 or j + PRE0 >= day.rth1:
        return "no_fill_bar", None, None, None
    em = j + PRE0
    if em in hinfo.resume:
        return "resume_bar", em, None, None
    E = float(day.o[j])
    S = float(cmh[b.last_m - PRE0]) + TICK
    if E >= S - EPS:
        return "E_ge_S", em, E, S
    return "filled", em, E, S


@dataclass
class DaySig:
    ev: object
    bars_status: str
    status: str                  # filled / no_bars / no_signal / ssr_active / no_fill_bar / resume_bar / E_ge_S
    sig: object = None           # Bar5
    entry_m: int = None
    E: float = None
    S: float = None
    W: float = None
    ssr_open: bool = None
    ssr_0400: bool = None
    halts: object = None
    vw_fallback: int = 0
    vw_bars: int = 0
    pm_vol: float = None


def r2_day(day, ev, halt_k=HALT_K, nocross=False):
    """section 6 on one D2 session -> DaySig (no exit, no P&L)"""
    c1 = ev.c1
    hi = halt_info(day, halt_k)
    vw, nfb, nb = vwap_curve(day)
    pm = float(np.nansum(np.where(day.present[:RTH0 - PRE0], day.v[:RTH0 - PRE0], 0.0)))
    i930 = RTH0 - PRE0
    ssr_open = bool(day.present[i930] and day.l[i930] <= SSR_FRAC * c1 + EPS)
    out = DaySig(ev, "ok", "no_signal", halts=hi, vw_fallback=nfb, vw_bars=nb, pm_vol=pm, ssr_open=ssr_open)
    B = find_signal(bars5(day), vw, nocross)
    if B is None:
        return out
    out.sig = B
    lows = np.where(day.present[:B.close_t - PRE0], day.l[:B.close_t - PRE0], np.inf)
    out.ssr_0400 = bool(lows.size and lows.min() <= SSR_FRAC * c1 + EPS)
    st, em, E, S = candidate_eval(day, B, c1, hi)
    out.status, out.entry_m, out.E, out.S = st, em, E, S
    if st == "filled":
        out.W = E + W_MULT * (S - E)
    return out


def walk(day, entry_m, stop, side, reading):
    """stop judging on 1m bars from the entry bar through the bar starting close-6 (15:54), then the exit window.
    side -1 short / +1 long (mirrored). -> (px, minute, reason, last pre-halt close). reasons: stop_open, stop_level
    (reading L), stop_next (reading N), exit_1555, halted_close (px None)."""
    a, b = entry_m - PRE0, day.rth1 - 5 - PRE0
    pres = day.present[a:b]
    with np.errstate(invalid="ignore"):
        if side < 0:
            thr = pres & (day.o[a:b] >= stop - EPS)
            tch = pres & (day.h[a:b] >= stop - EPS)
        else:
            thr = pres & (day.o[a:b] <= stop + EPS)
            tch = pres & (day.l[a:b] <= stop + EPS)
    hit = thr | tch
    if hit.any():
        j = int(np.argmax(hit))
        i = a + j
        if thr[j]:
            return float(day.o[i]), i + PRE0, "stop_open", None
        if reading == "L":
            return float(stop), i + PRE0, "stop_level", None
        nx = day.nxt()
        k = int(nx[i + 1]) if i + 1 < NMIN else -1
        if k >= 0 and k + PRE0 < day.rth1:
            return float(day.o[k]), k + PRE0, "stop_next", None
        return None, None, "halted_close", float(day.c[i])
    w0, w1 = day.rth1 - 5 - PRE0, day.rth1 - PRE0
    win = day.present[w0:w1]
    if win.any():
        i = w0 + int(np.argmax(win))
        return float(day.o[i]), i + PRE0, "exit_1555", None
    seg = day.present[a:w1]
    last = a + int(np.flatnonzero(seg)[-1])
    return None, None, "halted_close", float(day.c[last])


def halted_close_exit(ev, stop, last_close, side):
    """s.5: the raw open of the first daily-cache bar within the next 10 market sessions after D2; stress price
    max(stop, last pre-halt close) (min for a long; the last close when there is no stop) when there is none, it falls
    on or after the cut, or an S1 / S1c / test M flag sits on any session from D2+1 through it. -> (px, booking date,
    nights, priced_by)"""
    flagged = False
    for k in range(len(ev.nxt_dates)):
        flagged = flagged or bool(ev.nxt_flag[k])
        px = ev.nxt_open[k]
        if px is not None and np.isfinite(px) and px > 0:
            if flagged:
                break
            return float(px), pd.Timestamp(ev.nxt_dates[k]), k + 1, "next_open"
    if stop is None:
        px = float(last_close)
    else:
        px = max(float(stop), float(last_close)) if side < 0 else min(float(stop), float(last_close))
    why = "stress_split" if flagged else ("stress_cut" if ev.nxt_reaches_cut else "stress_no_bar")
    if ev.next_session is not None and pd.Timestamp(ev.next_session) < CUT:
        return px, pd.Timestamp(ev.next_session), 1, why
    return px, pd.Timestamp(ev.d2), 0, why


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


@dataclass
class Exit:
    px: float
    minute: int
    reason: str
    date: pd.Timestamp
    nights: int
    priced_by: str
    on_resume: bool = False


def exit_for(day, ev, entry_m, stop, side, reading, hinfo=None):
    px, m, reason, last = walk(day, entry_m, stop, side, reading)
    if reason == "halted_close":
        px, d, nights, how = halted_close_exit(ev, stop, last, side)
        return Exit(px, None, reason, d, nights, how)
    onr = bool(reason == "stop_open" and hinfo is not None and m in hinfo.resume)
    return Exit(px, m, reason, pd.Timestamp(ev.d2), 0, "intraday", onr)


def legal_fill(day, ct, c5, S):
    """Rule-201-legal fill (report): a short limit at c5 + $0.01 posted at ct, filled at the limit only if a 1m bar
    starting in [ct, ct + 5) has high >= limit + $0.01. -> (fill minute, E) or (None, None); E >= S is no trade."""
    lim = round(c5 + TICK, 10)
    for m in range(ct, min(ct + ENTRY_SPAN, day.rth1)):
        i = m - PRE0
        if day.present[i] and day.h[i] >= lim + TICK - EPS:
            if S is not None and lim >= S - EPS:
                return None, None
            return m, lim
    return None, None


# ================================================================== costs, size, statistics (section 7)
def side_cost(px, h50, h75, stress):
    """per side, $ a share: base max(h50 x p, $0.005) + $0.0035; stress max(h75 x p, $0.005) + $0.01 + $0.0035"""
    px = np.asarray(px, float)
    if stress:
        return np.maximum(h75 * px, HALF_TICK) + STRESS_ADD + COMM
    return np.maximum(h50 * px, HALF_TICK) + COMM


def unit_net(E, X, side, h50, h75, stress, nights, locate=None):
    """per-share net: gross - entry and exit cost - locate (shorts only: 1% base / 2% stress of E, once + once a night)"""
    E, X, nights = np.asarray(E, float), np.asarray(X, float), np.asarray(nights, float)
    side = np.asarray(side, float)
    gross = np.where(side < 0, E - X, X - E)
    cost = side_cost(E, h50, h75, stress) + side_cost(X, h50, h75, stress)
    loc = (LOC_STRESS if stress else LOC_BASE) if locate is None else locate
    return gross - cost - np.where(side < 0, loc * E * (1.0 + nights), 0.0)


def shares_at(N, adv, E):
    """floor(min(N, 0.01 x ADV$) / E)"""
    return np.floor(np.minimum(N, CAP_FRAC * np.asarray(adv, float)) / np.asarray(E, float) + 1e-9)


@dataclass
class NStar:
    n: float
    shares: np.ndarray
    maxdd: float
    crossed: bool


def _compress(day_idx):
    order = np.argsort(np.asarray(day_idx), kind="stable")
    u, starts = np.unique(np.asarray(day_idx)[order], return_index=True)
    return order, u, starts


def solve_nstar(E, adv, unit, day_idx, grid=GRID, target=DD_TARGET, chunk=64):
    """the smallest N on the $500 grid from $5,000 whose maxDD (peak from $0) >= $30,000; $500,000 if none. A scan,
    never a bisection: maxDD(N) is not monotone once the 1% cap binds."""
    E, adv, unit = np.asarray(E, float), np.asarray(adv, float), np.asarray(unit, float)
    if len(E) == 0:
        return NStar(float(grid[-1]), np.zeros(0), 0.0, False)
    order, _u, starts = _compress(day_idx)
    cap = CAP_FRAC * adv
    for c0 in range(0, len(grid), chunk):
        g = grid[c0:c0 + chunk]
        sh = np.floor(np.minimum(g[None, :], cap[:, None]) / E[:, None] + 1e-9)
        D = np.add.reduceat((sh * unit[:, None])[order], starts, axis=0)
        cum = np.cumsum(D, axis=0)
        peak = np.maximum.accumulate(np.vstack([np.zeros((1, D.shape[1])), cum]), axis=0)[1:]
        dd = (peak - cum).max(axis=0)
        hit = np.flatnonzero(dd >= target)
        if len(hit):
            j = int(hit[0])
            return NStar(float(g[j]), sh[:, j].copy(), float(dd[j]), True)
    sh = shares_at(grid[-1], adv, E)
    return NStar(float(grid[-1]), sh, maxdd(daily_series(sh, unit, day_idx, int(np.max(day_idx)) + 1)), False)


def daily_series(shares, unit, day_idx, n_days):
    """trade nets summed on their exit session (sorted, reduceat: the solver's summation order), zeros elsewhere"""
    out = np.zeros(n_days)
    if len(shares) == 0:
        return out
    order, u, starts = _compress(day_idx)
    out[u] = np.add.reduceat((np.asarray(shares, float) * np.asarray(unit, float))[order], starts)
    return out


def maxdd(x):
    cum = np.cumsum(np.asarray(x, float))
    if not len(cum):
        return 0.0
    return float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())


def roc30(x):
    """30 x (net / Y) / max(maxDD, 30,000), Y = 8.994 fixed"""
    return 30.0 * (float(np.sum(x)) / YEARS) / max(maxdd(x), DD_TARGET)


def roc_uncapped(x):
    d = maxdd(x)
    return 30.0 * (float(np.sum(x)) / YEARS) / d if d > 0 else None


def tstat(x):
    x = np.asarray(x, float)
    if len(x) < 2:
        return float("nan")
    sd = float(np.std(x, ddof=1))
    return float(np.mean(x) / (sd / math.sqrt(len(x)))) if sd > 0 else float("nan")


def sortino(x):
    x = np.asarray(x, float)
    dn = float(np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))) if len(x) else 0.0
    return float(np.mean(x) / dn * math.sqrt(252)) if dn > 0 else float("nan")


def pf(nets):
    nets = np.asarray(nets, float)
    w, lo = float(nets[nets > 0].sum()), float(-nets[nets < 0].sum())
    return w / lo if lo > 0 else (float("inf") if w > 0 else float("nan"))


def years_positive(daily, sessions, trade_dates):
    """July-June years with net > 0; a year with no trades is not positive"""
    ys = np.array([wf_year_of(d) for d in sessions])
    traded = {wf_year_of(d) for d in trade_dates}
    per = {y: float(np.sum(np.asarray(daily)[ys == y])) for y in WF_YEARS}
    pos = [y for y in WF_YEARS if y in traded and per[y] > 0]
    return len(pos), per


def count_gate(per_year_counts):
    n = int(sum(per_year_counts.values()))
    rate = n / YEARS
    return {"n": n, "n_per_year": rate, "mean_ge_50": bool(rate >= COUNT_MEAN), "n_ge_100": bool(n >= COUNT_MIN),
            "pass": bool(rate >= COUNT_MEAN and n >= COUNT_MIN), "per_year": dict(per_year_counts),
            "thin_years_under_25": [y for y in WF_YEARS if per_year_counts.get(y, 0) < THIN_YEAR],
            "rule": "n / 8.994 >= 50 AND n >= 100 (MANAGER #41 Q3); a miss is recorded and the run continues"}


def verdict(bars, count_key=4):
    """PASS = every bar holds; RESEARCH ROW = only the count bar misses; FAIL otherwise"""
    miss = [k for k, v in bars.items() if not v]
    if not miss:
        return "PASS"
    if miss == [count_key]:
        return "RESEARCH ROW"
    return "FAIL"


# ================================================================== the book (#463, L, R days, episodes)
@dataclass
class Book:
    index: pd.DatetimeIndex
    mtm: np.ndarray
    line: np.ndarray
    legs: dict
    res_c: np.ndarray
    inR: np.ndarray
    r_episodes: list
    dd_episodes: list
    dd_mask: np.ndarray
    parity: dict = field(default_factory=dict)


def book_stats(x, years=YEARS):
    x = np.asarray(x, float)
    d = maxdd(x)
    return {"roc": 30.0 * (float(x.sum()) / years) / d if d > 0 else float("nan"), "sort": sortino(x), "net": float(x.sum()),
            "maxdd": d}


def book_parity(st, facts, name):
    if not (round(st["roc"], 2) == facts[0] and round(st["sort"], 3) == facts[1]):
        refuse(f"{name} PARITY FAILED: ROC {st['roc']:.4f} Sortino {st['sort']:.5f}, expected {facts[0]} / {facts[1]}")
    return True


def episode_mask(index, eps):
    """inclusive [start, end] ranges on an index"""
    u = np.zeros(len(index), bool)
    for s, e in eps:
        u |= np.asarray((index >= pd.Timestamp(s)) & (index <= pd.Timestamp(e)))
    return u


def load_book(anat=None):
    anat = anat or os.path.join(home(), "_anatomy_cache")
    p_book = os.path.join(anat, "rocfrontier", "r4", "book463_daily.csv")
    q19 = os.path.join(anat, "q19")
    paths = {"book463_daily.csv": p_book, "residual_days.csv": os.path.join(q19, "residual_days.csv"),
             "line.csv": os.path.join(q19, "line.csv"), "a2.json": os.path.join(q19, "a2.json"),
             "episodes.csv": os.path.join(q19, "episodes.csv")}
    raw = {}
    for k, p in paths.items():
        with open(p, "rb") as f:
            raw[k] = f.read()
        if sha256_bytes(raw[k]) != SHA[k]:
            refuse(f"{k} hashes to {sha256_bytes(raw[k])}, section 4 pins {SHA[k]}")
    b = pd.read_csv(io.BytesIO(raw["book463_daily.csv"]), parse_dates=["date"])
    b = b[(b["date"] >= WF0) & (b["date"] < CUT)].reset_index(drop=True)
    idx = pd.DatetimeIndex(b["date"])
    if len(idx) != BOOK_N:
        refuse(f"the #463 WF index has {len(idx)} rows, not {BOOK_N}")
    mtm = b["mtm"].to_numpy(float)
    st_b = book_stats(mtm)
    book_parity(st_b, BOOK_FACTS, "#463")
    ln = pd.read_csv(io.BytesIO(raw["line.csv"]), parse_dates=["date"])
    if len(ln) != len(idx) or not (pd.DatetimeIndex(ln["date"]) == idx).all():
        refuse("line.csv dates are not #463's WF index")
    if float(np.abs(ln["book"].to_numpy(float) - mtm).max()) > 0.01:
        refuse("line.csv book is not book463_daily mtm within $0.01")
    line = ln["line"].to_numpy(float)
    st_l = book_stats(line)
    book_parity(st_l, LINE_FACTS, "L")
    r = pd.read_csv(io.BytesIO(raw["residual_days.csv"]), parse_dates=["date"])
    if len(r) != len(idx) or not (pd.DatetimeIndex(r["date"]) == idx).all():
        refuse("residual_days.csv dates are not #463's WF index")
    inR = r["in_R"].astype(str).str.lower().map({"true": True, "false": False})
    if inR.isna().any() or int(inR.sum()) != R_DAYS:
        refuse(f"residual_days.csv in_R sums to {inR.sum()}, not {R_DAYS}")
    inR = inR.to_numpy(bool)
    a2 = json.loads(raw["a2.json"].decode("utf-8"))
    r_eps = [(pd.Timestamp(s), pd.Timestamp(e)) for s, e in a2["line_episodes"]]
    if len(r_eps) != R_EPIS or not (episode_mask(idx, r_eps) == inR).all():
        refuse("a2.json line_episodes are not R's 45 inclusive episodes = in_R")
    ep = pd.read_csv(io.BytesIO(raw["episodes.csv"]))
    dd_eps = list(zip(pd.to_datetime(ep["start"]), pd.to_datetime(ep["end"])))
    ddm = episode_mask(idx, dd_eps)
    if len(dd_eps) != DD_EPIS or int(ddm.sum()) != DD_DAYS:
        refuse(f"episodes.csv: {len(dd_eps)} episodes / {int(ddm.sum())} days, expected {DD_EPIS} / {DD_DAYS}")
    legs = {f"L{i}": b[f"L{i}_mtm"].to_numpy(float) for i in range(4)}
    return Book(idx, mtm, line, legs, ln["res_c"].to_numpy(float), inR, r_eps, dd_eps, ddm,
                {"book463": st_b, "L": st_l})


def to_book(daily, sessions, book):
    """reindex onto the book index with fill 0, appending leg dates not in it -> (extended index, leg, book mtm, L,
    inR, appended count)"""
    s = pd.Series(np.asarray(daily, float), index=pd.DatetimeIndex(sessions))
    s = s[s != 0.0]
    extra = s.index.difference(book.index)
    ext = book.index.union(extra)
    leg = s.reindex(ext, fill_value=0.0).to_numpy()
    pos = ext.get_indexer(book.index)
    bm = np.zeros(len(ext))
    bm[pos] = book.mtm
    ll = np.zeros(len(ext))
    ll[pos] = book.line
    ir = np.zeros(len(ext), bool)
    ir[pos] = book.inR
    return ext, leg, bm, ll, ir, int(len(extra))


def rsum(leg, inR):
    return float(np.sum(np.asarray(leg)[np.asarray(inR)]))


def rsum_ex3(leg, inR):
    v = np.sort(np.asarray(leg)[np.asarray(inR)])
    return float(v[:-3].sum()) if len(v) > 3 else 0.0


def vol_c(leg_ext, book_ext_mtm, ext_index):
    m = np.asarray((ext_index >= WF0) & (ext_index < VOL_END))
    sl = float(np.std(np.asarray(leg_ext)[m], ddof=1)) if m.sum() > 1 else 0.0
    sb = float(np.std(np.asarray(book_ext_mtm)[m], ddof=1)) if m.sum() > 1 else 0.0
    return VOL_SHARE * sb / sl if sl > 0 else 0.0


# ================================================================== events and the environment
@dataclass
class Event:
    symbol: str
    d2: pd.Timestamp
    wf_year: str
    bucket: str
    c0: float
    c1: float
    l1: float
    adv: float
    v2: float
    o2: float
    nxt_dates: tuple
    nxt_open: tuple
    nxt_flag: tuple
    next_session: object
    nxt_reaches_cut: bool = False
    registered: bool = True
    band_d0_only: bool = True
    carry_kept: bool = True
    carry: bool = False
    s2prime: bool = False
    quotes: bool = False
    pmfail_event: bool = False
    flags: dict = field(default_factory=dict)
    nxt_sc: tuple = ()
    nxt_m: tuple = ()

    @property
    def key(self):
        return (f"{self.d2:%Y-%m-%d}", self.symbol)


@dataclass
class Env:
    events: list               # runner2_d2 rows (the loosest reading), sorted by (D2, symbol)
    nonevents: list            # runner2_nonevent rows (the placebo sample)
    sessions: pd.DatetimeIndex  # WF market sessions 2016-07-01..2025-06-29 (the daily cache's dates)
    photo: object
    book: object
    vix: object = None
    builder_counts: dict = field(default_factory=dict)
    input_stamp: dict = field(default_factory=dict)
    bad_name_dropped: int = 0

    def sess_ix(self):
        if not hasattr(self, "_six"):
            self._six = {d: i for i, d in enumerate(self.sessions)}
        return self._six


def assert_no_half_day(events):
    bad = [e.key for e in events if e.registered and is_half_day(e.d2)]
    if bad:
        refuse(f"a registered D2 falls on a half day ({bad[:3]}): section 2 filter 1 skips half days")


def omega_of(sigs):
    rows = sorted(s.ev.key for s in sigs if s.status == "filled")
    return rows, sha256_bytes("".join(f"{d},{s}\n" for d, s in rows).encode("utf-8"))


def scan(env, events, halt_k=HALT_K, nocross=False):
    out = []
    for ev in events:
        r = env.photo.bars(ev.symbol, ev.d2)
        if r.status != "ok":
            out.append(DaySig(ev, r.status, "no_bars"))
            continue
        s = r2_day(r.day, ev, halt_k, nocross)
        out.append(s)
    return out


def spread_table(env):
    """RUNNER2's own day-2 quotes sample: name-day values per bucket -> h50 / h75 (s.4, s.7)"""
    vals, info = {b: [] for b in BUCKETS}, {"days": 0, "valid_days": 0, "no_valid_mark": 0, "refused_all": 0,
                                            "refused_some": 0, "served_desc_all": 0, "asc_fallback_days": 0}
    for ev in [e for e in env.events if e.registered and e.quotes]:
        info["days"] += 1
        st, mv, desc = env.photo.marks(ev.symbol, ev.d2)
        if st != "ok":
            info[st] += 1
            vals[ev.bucket].append((PRIOR_H50[ev.bucket], True))
            continue
        info["served_desc_all" if desc else "asc_fallback_days"] += 1
        v = mark_value(mv)
        if v is None:
            info["no_valid_mark"] += 1
            continue
        info["valid_days"] += 1
        vals[ev.bucket].append((v, False))
    return {"buckets": bucket_spreads(vals), "info": info}


# ================================================================== the counts step (section 11 step 1)
def _year_bucket():
    return {y: {"lt5": 0, "5to20": 0, "all": 0} for y in WF_YEARS}


def _inc(d, y, b, k=1):
    d[y][b] += k
    d[y]["all"] += k


def counts_payload(env, sigs, sigs4, spreads, stamp):
    reg = [s for s in sigs if s.ev.registered]
    ev_by = _year_bucket()
    bars_st = {y: {"ok": 0, "empty": 0, "missing": 0, "refused": 0} for y in WF_YEARS}
    reasons = ("no_bars", "no_signal", "ssr_active", "no_fill_bar", "resume_bar", "E_ge_S", "filled")
    blocks = {y: {r: 0 for r in reasons} for y in WF_YEARS}
    ssr = {y: {"at_open": 0, "intraday_before_B": 0, "carry_over_removed": 0, "reading_0400_blocks": 0} for y in WF_YEARS}
    half_hours, stop_d = {}, {k: 0 for k in STOP_LABELS}
    thin = _year_bucket()
    thin_n = _year_bucket()
    vwf, vwn = 0, 0
    fills_by = {y: 0 for y in WF_YEARS}
    hc_fills = {y: 0 for y in WF_YEARS}
    for s in reg:
        y, b = s.ev.wf_year, s.ev.bucket
        _inc(ev_by, y, b)
        bars_st[y][s.bars_status if s.status == "no_bars" else "ok"] += 1
        blocks[y][s.status] += 1
        if s.status == "no_bars":
            continue
        ssr[y]["at_open"] += int(bool(s.ssr_open))
        ssr[y]["intraday_before_B"] += int(s.status == "ssr_active")
        if s.sig is not None and s.ssr_0400 and s.status != "ssr_active":
            ssr[y]["reading_0400_blocks"] += 1
        vwf += s.vw_fallback
        vwn += s.vw_bars
        _inc(thin_n, y, b)
        if s.ev.v2 and s.ev.v2 > 0 and s.pm_vol < THIN_SHARE * s.ev.v2:
            _inc(thin, y, b)
        if s.sig is not None:
            hh = hm(RTH0 + 30 * ((s.sig.close_t - RTH0) // 30))
            half_hours[hh] = half_hours.get(hh, 0) + 1
        if s.status == "filled":
            fills_by[y] += 1
            stop_d[stop_bucket((s.S - s.E) / s.E)] += 1
            hc_fills[y] += int(s.halts.halted_close)
    for e in env.events:
        if e.carry_kept and e.carry:
            ssr[e.wf_year]["carry_over_removed"] += 1
    run_len = {"4": 0, "5": 0, "6-9": 0, "10": 0, "11-30": 0, ">30": 0}
    runs4_tod, runs_per_session = {}, {}
    lost5 = sum(1 for s in reg if s.status == "resume_bar")
    lost4 = sum(1 for s in sigs4 if s.ev.registered and s.status == "resume_bar")
    for s in sigs4:
        if not s.ev.registered or s.status == "no_bars":
            continue
        n5 = 0
        for a, e in s.halts.runs:
            L = e - a
            key = "4" if L == 4 else "5" if L == 5 else "6-9" if L <= 9 else "10" if L == 10 else "11-30" if L <= 30 else ">30"
            run_len[key] += 1
            n5 += int(L >= HALT_K)
            if L == 4:
                t = hm(RTH0 + 30 * ((a - RTH0) // 30))
                runs4_tod[t] = runs4_tod.get(t, 0) + 1
        runs_per_session[str(n5)] = runs_per_session.get(str(n5), 0) + 1
    fl = [s for s in reg if s.status == "filled"]
    cap_fixed = {f"{int(N)}": (float(np.mean([CAP_FRAC * s.ev.adv < N for s in fl])) if fl else None)
                 for N in FIXED_NOTIONALS}
    delisted = {y: {"n": 0, "delisted_last_bar_before_2026_06_01": 0, "inactive_all_rows": 0, "ambiguous_mixed_rows": 0}
                for y in WF_YEARS}
    rev = {y: {"s1_reverse": 0, "calendar_reverse": 0, "test_m": 0, "any": 0, "all_three": 0, "exactly_one": 0}
           for y in WF_YEARS}
    for s in reg:
        f, y = s.ev.flags, s.ev.wf_year
        d = delisted[y]
        d["n"] += 1
        d["delisted_last_bar_before_2026_06_01"] += int(bool(f.get("delisted")))
        d["inactive_all_rows"] += int(bool(f.get("inactive")))
        d["ambiguous_mixed_rows"] += int(bool(f.get("ambiguous")))
        a, c, m = bool(f.get("rev_s1")), bool(f.get("rev_cal")), bool(f.get("rev_m"))
        r = rev[y]
        r["s1_reverse"] += a
        r["calendar_reverse"] += c
        r["test_m"] += m
        r["any"] += int(a or c or m)
        r["all_three"] += int(a and c and m)
        r["exactly_one"] += int(a + c + m == 1)
    omega, osha = omega_of(reg)
    gate = count_gate(fills_by)
    overlap = schedule_overlap(env, fl)
    return {
        "stamp": stamp,
        "interpretations": [{"prereg": q, "reading": r} for q, r in INTERPRETATIONS],
        "builder": env.builder_counts,
        "registered_events": {"by_year_bucket": ev_by, "total": sum(v["all"] for v in ev_by.values()),
                              "bars_status_by_year": bars_st, "feed": env.photo.feed},
        "signals": {"by_year": blocks, "trigger_half_hour": dict(sorted(half_hours.items())),
                    "block_order": list(reasons[1:-1])},
        "ssr_by_year": ssr,
        "halts": {"run_lengths_k4_scan": run_len, "runs_ge5_per_session": dict(sorted(runs_per_session.items())),
                  "four_minute_runs_by_half_hour": dict(sorted(runs4_tod.items())),
                  "signals_lost_to_resume_bar_k5": lost5, "signals_lost_to_resume_bar_k4": lost4,
                  "fills_with_empty_exit_window_by_year": hc_fills},
        "stop_distance": stop_d,
        "premarket_thinness": {"share_under_10pct": {y: {b: (thin[y][b] / thin_n[y][b] if thin_n[y][b] else None)
                                                          for b in ("lt5", "5to20", "all")} for y in WF_YEARS},
                               "n": thin_n, "thin": thin},
        "vwap_fallback": {"bars": vwn, "fallback": vwf, "share": (vwf / vwn if vwn else None)},
        "delisted_by_year": delisted,
        "reverse_split_60d_by_year": rev,
        "bad_name_recheck_dropped": int(env.bad_name_dropped),
        "spreads": spreads,
        "cap_binding_at_fixed_notional": cap_fixed,
        "count_gate": gate,
        "omega": {"n": len(omega), "sha256": osha},
        "omega_sha256": osha,
        "schedule_overlap": overlap,
    }


def schedule_overlap(env, fills):
    """section 11 step 3, schedule-level (entry sessions, before any P&L): fills inside R's 762 days and #463's 460 days;
    share of fill days with each #463 leg's mtm nonzero and with RES nonzero; D2 sessions that are PMFAIL event days"""
    days = sorted({s.ev.d2 for s in fills})
    out = {"fill_days": len(days), "fills_on_pmfail_event_days": int(sum(s.ev.pmfail_event for s in fills))}
    B = env.book
    if B is None or not days:
        return out
    pos = B.index.get_indexer(pd.DatetimeIndex(days))
    ok = pos >= 0
    p = pos[ok]
    out["fill_days_not_on_book_index"] = int((~ok).sum())
    out["fill_days_in_R"] = int(B.inR[p].sum())
    out["fill_days_in_463_drawdown_days"] = int(B.dd_mask[p].sum())
    out["share_fill_days_leg_mtm_nonzero"] = {k: float(np.mean(v[p] != 0)) if len(p) else None for k, v in B.legs.items()}
    out["share_fill_days_res_nonzero"] = float(np.mean(B.res_c[p] != 0)) if len(p) else None
    return out


def schedule_frame(sigs):
    rows = []
    for s in sigs:
        if s.status != "filled":
            continue
        e = s.ev
        rows.append({"symbol": e.symbol, "d2": f"{e.d2:%Y-%m-%d}", "wf_year": e.wf_year, "bucket": e.bucket,
                     "signal_close": hm(s.sig.close_t), "entry_time": hm(s.entry_m), "E": s.E, "S": s.S, "W": s.W,
                     "adv": e.adv, "c1": e.c1,
                     "flags": ";".join(k for k, v in sorted(e.flags.items()) if v is True)})
    cols = ["symbol", "d2", "wf_year", "bucket", "signal_close", "entry_time", "E", "S", "W", "adv", "c1", "flags"]
    return pd.DataFrame(rows, columns=cols)


def stamp_core(env):
    return {"harness": {"file": "tools/" + os.path.basename(__file__), "sha256_lf": sha256_lf(os.path.abspath(__file__)),
                        "registered_name": REGISTERED_NAME},
            "inputs": env.input_stamp, "photograph": env.photo.stamp}


def _meta():
    try:
        import pyarrow
        pa = pyarrow.__version__
    except ImportError:
        pa = None
    return {"versions": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__, "pyarrow": pa}}


def _read_filed(path, what):
    if not os.path.exists(path):
        refuse(f"{what} is not on file ({path}): run the earlier mode first")
    with open(path, "rb") as f:
        return json.loads(f.read())


def _check_stamp(filed, env, what):
    now = clean(stamp_core(env))
    if filed.get("stamp") != now:
        refuse(f"{what}'s stamp differs from this run's (harness, inputs or photograph moved since it was filed)")


def mode_counts(env, out=None, write=True):
    out = out or out_dir()
    reg = [e for e in env.events if e.registered]
    assert_no_half_day(reg)
    sigs = scan(env, reg, HALT_K)
    sigs4 = scan(env, reg, HALT_K4)
    spreads = spread_table(env)
    payload = counts_payload(env, sigs, sigs4, spreads, stamp_core(env))
    print_counts(payload)
    if write:
        body = dict(payload)
        body["meta"] = _meta()
        write_once(os.path.join(out, "counts.json"), dumps(body))
        write_once(os.path.join(out, "schedule.csv"), csv_bytes(schedule_frame(sigs)))
    return payload, sigs


def print_counts(p):
    print("RUNNER2 r1 COUNTS (section 11 step 1; no P&L)")
    print(f"  feed {p['registered_events']['feed']}; registered events {p['registered_events']['total']}")
    print("  " + " ".join(f"{y}:{p['count_gate']['per_year'].get(y, 0)}" for y in WF_YEARS))
    tot = {}
    for y, v in p["signals"]["by_year"].items():
        for k, n in v.items():
            tot[k] = tot.get(k, 0) + n
    print("  outcomes: " + ", ".join(f"{k} {v}" for k, v in tot.items()))
    g = p["count_gate"]
    print(f"  COUNT GATE (bar 4): n {g['n']}  n/yr {g['n_per_year']:.2f}  mean>=50 {g['mean_ge_50']}  n>=100 "
          f"{g['n_ge_100']}  thin(<25) {g['thin_years_under_25'] or 'none'}  -> {'PASS' if g['pass'] else 'MISS (run continues)'}")
    sp = p["spreads"]["buckets"]
    print("  spreads: " + "; ".join(f"{b} h50 {v['h50']:.4%} h75 {v['h75']:.4%} n {v['n']} ({v['source']})" for b, v in sp.items()))
    print(f"  omega {p['omega']['n']} sessions sha256 {p['omega']['sha256']}")


# ================================================================== the cells (P and W) and the trades
def _spread_for(spreads, b):
    v = spreads["buckets"][b]
    return v["h50"], v["h75"]


def trade_rows(env, sigs, spreads, stop_of="S", readings=("L", "N"), side_of=None):
    """filled DaySigs -> per-trade frame: exits for each reading, per-share nets at base and stress cost, the exit
    session index. side_of: None = short; else an array of +-1 (the coin-flip leg)."""
    six = env.sess_ix()
    recs = []
    fl = [s for s in sigs if s.status == "filled"]
    for i, s in enumerate(fl):
        ev = s.ev
        day = env.photo.bars(ev.symbol, ev.d2).day
        side = -1.0 if side_of is None else float(side_of[i])
        if stop_of == "S":
            stop = s.S if side < 0 else s.E - (s.S - s.E)
        elif stop_of == "W":
            stop = s.W
        else:
            stop = stop_of(s)
        h50, h75 = _spread_for(spreads, ev.bucket)
        r = {"symbol": ev.symbol, "d2": ev.d2, "wf_year": ev.wf_year, "bucket": ev.bucket, "c1": ev.c1, "adv": ev.adv,
             "signal_close": None if s.sig is None else s.sig.close_t, "entry_m": s.entry_m, "E": s.E,
             "stop": stop, "side": side, "ev": ev, "sig": s}
        for rd in readings:
            x = exit_for(day, ev, s.entry_m, stop, side, rd, s.halts)
            if x.date not in six:
                refuse(f"exit session {x.date} of {ev.symbol} {ev.d2:%Y-%m-%d} is not a WF session")
            r[f"X_{rd}"], r[f"xm_{rd}"], r[f"why_{rd}"] = x.px, x.minute, x.reason
            r[f"xd_{rd}"], r[f"nights_{rd}"], r[f"how_{rd}"], r[f"onres_{rd}"] = x.date, x.nights, x.priced_by, x.on_resume
            r[f"ix_{rd}"] = six[x.date]
            for st in (False, True):
                r[f"u_{rd}_{'stress' if st else 'base'}"] = float(unit_net(s.E, x.px, side, h50, h75, st, x.nights,
                                                                           locate=None if side < 0 else 0.0))
            r[f"u_{rd}_gross"] = float((s.E - x.px) if side < 0 else (x.px - s.E))
        recs.append(r)
    return pd.DataFrame(recs)


@dataclass
class Cell:
    name: str
    tr: pd.DataFrame
    nstar: object
    shares: np.ndarray
    daily: np.ndarray


def make_cell(env, name, tr, nstar=None):
    nd = len(env.sessions)
    if len(tr) == 0:
        return Cell(name, tr, NStar(float(GRID[-1]), np.zeros(0), 0.0, False), np.zeros(0), np.zeros(nd))
    E, adv = tr["E"].to_numpy(float), tr["adv"].to_numpy(float)
    if nstar is None:
        ns = solve_nstar(E, adv, tr["u_L_base"].to_numpy(float), tr["ix_L"].to_numpy(np.int64))
    else:
        ns = NStar(float(nstar), shares_at(float(nstar), adv, E), 0.0, False)
    sh = shares_at(ns.n, adv, E)
    if (sh < 1).any():
        refuse(f"{name}: a trade sizes to 0 shares at N = {ns.n:,.0f} (ADV$ floor should prevent it)")
    d = daily_series(sh, tr["u_L_base"].to_numpy(float), tr["ix_L"].to_numpy(np.int64), nd)
    return Cell(name, tr, ns, sh, d)


def series(env, cell, reading="L", cost="base"):
    if len(cell.tr) == 0:
        return np.zeros(len(env.sessions))
    return daily_series(cell.shares, cell.tr[f"u_{reading}_{cost}"].to_numpy(float),
                        cell.tr[f"ix_{reading}"].to_numpy(np.int64), len(env.sessions))


def nets(cell, reading="L", cost="base", mask=None):
    if len(cell.tr) == 0:
        return np.zeros(0)
    x = cell.shares * cell.tr[f"u_{reading}_{cost}"].to_numpy(float)
    return x if mask is None else x[np.asarray(mask)]


def judged_stats(env, x):
    return {"net": float(np.sum(x)), "roc30": roc30(x), "maxdd": maxdd(x), "t": tstat(x), "sortino": sortino(x)}


def subset_cell(env, cell, mask):
    tr = cell.tr[np.asarray(mask)].reset_index(drop=True)
    return Cell(cell.name, tr, cell.nstar, cell.shares[np.asarray(mask)],
                daily_series(cell.shares[np.asarray(mask)], tr["u_L_base"].to_numpy(float), tr["ix_L"].to_numpy(np.int64),
                             len(env.sessions)) if len(tr) else np.zeros(len(env.sessions)))


# ================================================================== the family null (RUNNER2's half; PMFAIL computes it)
@dataclass
class NullCtx:
    keys: list
    elig: list            # per Omega session: bool array over candidate bars
    uP: list
    uW: list
    E: list
    ixP: list
    ixW: list
    adv: np.ndarray
    n_days: int
    inR_day: np.ndarray
    omega_sha: str
    sessions: object = None

    @property
    def omega_sha256(self):           # the PMFAIL harness reads these two names into null.json
        return self.omega_sha

    @property
    def omega_n(self):
        return len(self.keys)


def build_null_ctx(env, sigs, spreads):
    """Omega = sessions where cell P (reading L) filled a real trade (the schedule alone). Per session: every present 5m
    bar with close time in [09:45, 14:00]; eligible = the entry rules hold (entry bar within 4 minutes, not a resume
    bar, no SSR at that bar, E < S); per eligible bar the reading-L, base-cost per-share net for P (S) and W (1.5x)."""
    keys, osha = omega_of(sigs)
    by = {s.ev.key: s for s in sigs}
    six = env.sess_ix()
    elig, uP, uW, EE, ixP, ixW, adv = [], [], [], [], [], [], []
    for k in keys:
        s = by[k]
        ev = s.ev
        day = env.photo.bars(ev.symbol, ev.d2).day
        h50, h75 = _spread_for(spreads, ev.bucket)
        cands = [b for b in bars5(day) if WIN_CLOSE0 <= b.close_t <= WIN_CLOSE1]
        el = np.zeros(len(cands), bool)
        up, uw, ee, ip, iw = (np.full(len(cands), np.nan) for _ in range(5))
        for j, b in enumerate(cands):
            st, em, E, S = candidate_eval(day, b, ev.c1, s.halts)
            if st != "filled":
                continue
            el[j] = True
            ee[j] = E
            for stop, uu, ii in ((S, up, ip), (E + W_MULT * (S - E), uw, iw)):
                x = exit_for(day, ev, em, stop, -1.0, "L", s.halts)
                uu[j] = float(unit_net(E, x.px, -1.0, h50, h75, False, x.nights))
                ii[j] = six[x.date]
        elig.append(el)
        uP.append(up)
        uW.append(uw)
        EE.append(ee)
        ixP.append(ip)
        ixW.append(iw)
        adv.append(ev.adv)
    B = env.book
    inR_day = np.zeros(len(env.sessions), bool)
    if B is not None:
        pos = B.index.get_indexer(env.sessions)
        inR_day = np.where(pos >= 0, B.inR[np.clip(pos, 0, None)], False)
    return NullCtx(keys, elig, uP, uW, EE, ixP, ixW, np.asarray(adv, float), len(env.sessions), inR_day, osha)


def _cell_stats(E, adv, u, ix, n_days, inR_day):
    """one null cell at its own N*: (roc30, t, rsum) from the compressed daily series"""
    if len(E) == 0:
        return np.array([0.0, np.nan, 0.0]), float(GRID[-1])
    ns = solve_nstar(E, adv, u, ix)
    sh = shares_at(ns.n, adv, E)
    d = daily_series(sh, u, ix, n_days)
    return np.array([roc30(d), tstat(d), float(d[inR_day].sum())]), ns.n


def draw_once(rng, ctx):
    """ONE RUNNER2 draw: per Omega session (date, symbol order) one rng.permutation of its candidate bars; the first
    eligible bar among the first 21 (the draw + up to 20 redraws without replacement), else no null trade. The same
    bar serves P and W. -> ((2, 3) array [P, W] x [roc30, t, rsum], info)"""
    pick_s, pick_j = [], []
    none = 0
    for si, el in enumerate(ctx.elig):
        n = len(el)
        perm = rng.permutation(n)
        tries = perm[:MAX_TRIES]
        ok = el[tries]
        if ok.any():
            pick_s.append(si)
            pick_j.append(int(tries[int(np.argmax(ok))]))
        else:
            none += 1
    E = np.array([ctx.E[s][j] for s, j in zip(pick_s, pick_j)], float)
    adv = ctx.adv[np.asarray(pick_s, np.int64)] if pick_s else np.zeros(0)
    out, ns = np.zeros((2, 3)), []
    for c, (U, IX) in enumerate(((ctx.uP, ctx.ixP), (ctx.uW, ctx.ixW))):
        u = np.array([U[s][j] for s, j in zip(pick_s, pick_j)], float)
        ix = np.array([IX[s][j] for s, j in zip(pick_s, pick_j)], np.int64)
        out[c], n = _cell_stats(E, adv, u, ix, ctx.n_days, ctx.inR_day)
        ns.append(n)
    return out, {"trades": len(pick_s), "no_null_trade": none, "nstar": ns}


def null_half(ctx, n=NULL_DRAWS, seed=SEED_NULL_R2):
    """RUNNER2's half of the family null: n draws on default_rng(seed) -> ((n, 2, 3) array, {name: per-draw list})"""
    rng = np.random.default_rng(seed)
    arr = np.zeros((n, 2, 3))
    info = {"trades": [], "no_null_trade": [], "nstar_P": [], "nstar_W": []}
    for i in range(n):
        arr[i], inf = draw_once(rng, ctx)
        info["trades"].append(inf["trades"])
        info["no_null_trade"].append(inf["no_null_trade"])
        info["nstar_P"].append(inf["nstar"][0])
        info["nstar_W"].append(inf["nstar"][1])
    return arr, info


def family_summary(stats):
    """stats (n, 4, 3): cells [pm_primary, pm_neighbour, r2_P, r2_W] x [roc30, t, rsum] -> the null.json summary block,
    in the PMFAIL harness's key names (max4 / pmfail_max2 / runner2_max2, notion_b_roc30, nan_cells). NaN -> -inf in the
    max (counted); numpy linear percentiles."""
    a = np.asarray(stats, float)
    nan = np.isnan(a)
    b = np.where(nan, -np.inf, a)
    blocks = {"max4": b.max(axis=1), "pmfail_max2": b[:, :2].max(axis=1), "runner2_max2": b[:, 2:].max(axis=1)}
    out = {}
    for name, m in blocks.items():
        out[name] = {st: {lab: float(np.percentile(m[:, k], q)) for lab, q in PCTS} for k, st in enumerate(STATS3)}
    out["notion_b_roc30"] = {lab: out[lab]["roc30"]["p95"] - out[lab]["roc30"]["p50"] for lab in blocks}
    out["nan_cells"] = int(nan.sum())
    return out


def _null_omega(nl):
    om = nl.get("omega") or {}
    return om.get("sha256") or om.get("runner2_sha256")


def _null_harness(nl):
    return nl.get("runner2_harness_sha256_lf") or (nl.get("harness") or {}).get("runner2_sha256_lf")


def _null_leg(sm):
    return sm.get("runner2_max2") or sm.get("r2_max2") or {}


def read_null(path, expected_sha, own_omega_sha, own_harness_sha=None):
    """PMFAIL's null.json: the bytes must hash to the posted sha; seeds (20261006, 20261010), 500 draws, RUNNER2's
    Omega sha and this harness's LF sha as filed (omega.sha256 / runner2_harness_sha256_lf, the PMFAIL harness's keys).
    -> the parsed null (copied into stage_a.json)"""
    if not expected_sha:
        refuse("no null sha256 named (--null-sha): the lane posts null.sha256 to MANAGER first")
    if not os.path.exists(path):
        refuse(f"the family null is not on file ({path}): PMFAIL r1's harness writes it")
    with open(path, "rb") as f:
        data = f.read()
    got = sha256_bytes(data)
    if got != expected_sha.lower():
        refuse(f"null.json hashes to {got}, the posted sha256 is {expected_sha}")
    nl = json.loads(data.decode("utf-8"))
    if nl.get("seeds") != {"pmfail": SEED_NULL_PM, "runner2": SEED_NULL_R2}:
        refuse(f"null.json seeds {nl.get('seeds')} are not pmfail 20261006 / runner2 20261010")
    if nl.get("draws") != NULL_DRAWS:
        refuse(f"null.json has {nl.get('draws')} draws, not {NULL_DRAWS}")
    if _null_omega(nl) != own_omega_sha:
        refuse("null.json was drawn on a different RUNNER2 Omega than this harness's counts.json")
    own = own_harness_sha or sha256_lf(os.path.abspath(__file__))
    if _null_harness(nl) != own:
        refuse("null.json was drawn with a different RUNNER2 harness than this file")
    sm = nl.get("summary") or {}
    for blk, d in (("max4", sm.get("max4") or {}), ("runner2_max2", _null_leg(sm))):
        for st in STATS3:
            for lab, _q in PCTS:
                v = (d.get(st) or {}).get(lab)
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    refuse(f"null.json summary {blk}.{st}.{lab} missing")
    return {"sha256": got, **nl}


def null_context(env=None, manifest_sha=None, counts_path=None, photo=None, book=None, probe_log=None):
    """for PMFAIL r1's harness (`null_context(photo=..., book=...)`): RUNNER2's own sha-checked environment on the same
    photograph (photo.manifest_sha256 / photo.probe_log are read; `book` is not used: this module loads the same pinned
    book files itself), its Omega sha asserted equal to RUNNER2's filed counts.json. -> NullCtx (.omega_sha256, .omega_n)"""
    if env is None:
        ms = manifest_sha or getattr(photo, "manifest_sha256", None)
        env = load_env(ms, probe_log=probe_log or getattr(photo, "probe_log", None))
    del book
    p = counts_path or os.path.join(out_dir(), "counts.json")
    filed = _read_filed(p, "RUNNER2 counts.json")
    _check_stamp(filed, env, "RUNNER2 counts.json")
    reg = [e for e in env.events if e.registered]
    sigs = scan(env, reg, HALT_K)
    spreads = spread_table(env)
    ctx = build_null_ctx(env, sigs, spreads)
    if ctx.omega_sha != (filed.get("omega") or {}).get("sha256"):
        refuse("the recomputed RUNNER2 Omega differs from the filed counts.json")
    return ctx


# ================================================================== power line (section 9)
def mode_power(env, out=None):
    out = out or out_dir()
    filed = _read_filed(os.path.join(out, "counts.json"), "counts.json")
    _check_stamp(filed, env, "counts.json")
    reg = [e for e in env.events if e.registered]
    sigs = scan(env, reg, HALT_K)
    _om, osha = omega_of(sigs)
    if osha != filed["omega"]["sha256"]:
        refuse("the recomputed Omega differs from counts.json")
    spreads = filed["spreads"]
    fl = sorted([s for s in sigs if s.status == "filled"], key=lambda s: s.ev.key)
    rng = np.random.default_rng(SEED_COIN)
    sides = rng.choice(np.array([-1.0, 1.0]), size=len(fl)) if fl else np.zeros(0)
    tr = trade_rows(env, fl, spreads, "S", ("L",), side_of=sides)
    coin = make_cell(env, "coin", tr)                      # its own N* (see INTERPRETATIONS[1])
    B = env.book
    ext, leg, bm, _ll, _ir, appended = to_book(coin.daily, env.sessions, B)
    c = vol_c(leg, bm, ext)
    dd = maxdd(leg)
    k30 = DD_TARGET / dd if dd > 0 else 0.0
    files = {}
    for name, x in (("coinflip_daily.csv", leg), ("book463_wf.csv", bm), ("cand_c.csv", bm + c * leg),
                    ("cand_30k.csv", bm + k30 * leg)):
        df = pd.DataFrame({"date": [f"{d:%Y-%m-%d}" for d in ext], "pnl_usd": x})
        files[name] = write_once(os.path.join(out, name), csv_bytes(df))
    res = {}
    for lab, cand in (("vol_c", "cand_c.csv"), ("own_dd_30k", "cand_30k.csv")):
        r = PL.main(["--cand", files[cand], "--twin", files["book463_wf.csv"], "--from", f"{WF0:%Y-%m-%d}",
                     "--to", f"{WF1:%Y-%m-%d}", "--date-col", "date", "--pnl-col", "pnl_usd", "--block", str(POWER_BLOCK),
                     "--draws", str(POWER_DRAWS), "--seed", str(POWER_SEED)])
        res[lab] = {"sd": r["sd"], "line_5pct": r["line_5pct"], "line_80pct": r["line_80pct"], "draws": r["draws"],
                    "days": r["days"], "years": r["years"]}
    payload = {"stamp": clean(stamp_core(env)), "coinflip": {"seed": SEED_COIN, "trades": int(len(tr)),
                                                            "sizing": "the coin leg's own N* (INTERPRETATIONS[1])"},
               "k": {"vol_c": c, "own_dd_30k": k30}, "appended_days": appended, "lines": res}
    write_once(os.path.join(out, "power.json"), dumps(payload))
    print("POWER (coin-flip leg on P's schedule; SD and lines only)")
    for lab, r in res.items():
        print(f"  {lab}: SD {r['sd']:.2f}  5% line {r['line_5pct']:.2f}  80% line {r['line_80pct']:.2f}")
    return payload


# ================================================================== the real run (sections 9-11, 14)
def bars_check(env, P, W, nl):
    """section 10 bars 1-12 on P's judged series (reading L, base cost, N*) unless the bar says otherwise"""
    sm = nl["summary"]
    p95 = {st: sm["max4"][st]["p95"] for st in STATS3}
    d = P.daily
    ext, leg, bm, ll, ir, _ap = to_book(d, env.sessions, env.book)
    roc, t = roc30(d), tstat(d)
    rs, rs3 = rsum(leg, ir), rsum_ex3(leg, ir)
    nt = nets(P)
    n = int(len(P.tr))
    per = {y: int((P.tr["wf_year"] == y).sum()) if n else 0 for y in WF_YEARS}
    gate = count_gate(per)
    ypos, per_net = years_positive(d, env.sessions, list(P.tr["xd_L"]) if n else [])
    stress = series(env, P, "L", "stress")
    rN = series(env, P, "N", "base")
    sess = env.sessions

    def without(lo, hi):
        return float(d[np.asarray((sess < lo) | (sess > hi))].sum())
    hi5 = (P.tr["c1"] >= 5.0).to_numpy() if n else np.zeros(0, bool)
    ns5_stress = nets(P, "L", "stress", hi5) if n else np.zeros(0)
    ns5_base = nets(P, "L", "base", hi5) if n else np.zeros(0)
    earner = bool(roc >= 5 and rs > 0 and rs3 > 0 and rs > p95["rsum"])
    vals = {
        1: {"roc30": roc, "route": "own" if roc >= 15 else ("earner" if earner else "none"), "rsum": rs, "rsum_ex3": rs3,
            "null_p95_rsum": p95["rsum"]},
        2: {"roc30": roc, "null_p95_roc30": p95["roc30"]},
        3: {"pf": pf(nt)},
        4: gate,
        5: {"years_positive": ypos, "per_year_net": per_net},
        6: {"t": t, "null_p95_t": p95["t"]},
        7: {"stress_net": float(stress.sum())},
        8: {"net_without_best_day": float(d.sum() - (d.max() if len(d) else 0.0)),
            "net_without_best_trade": float(nt.sum() - (nt.max() if len(nt) else 0.0))},
        9: {"net_without_2020_02_15_04_30": without(*X20), "net_without_2020_2021": without(*Y2021)},
        10: {"w_net": float(W.daily.sum())},
        11: {"reading_n_net": float(rN.sum())},
        12: {"n": int(hi5.sum()), "stress_net": float(ns5_stress.sum()), "pf_base": pf(ns5_base), "pf_stress": pf(ns5_stress)},
    }
    ok = {
        1: bool(roc >= 15 or earner),
        2: bool(roc > p95["roc30"]),
        3: bool(vals[3]["pf"] >= 1.05),
        4: bool(gate["pass"]),
        5: bool(ypos >= 6),
        6: bool(t >= 2.0 and t > p95["t"]),
        7: bool(vals[7]["stress_net"] > 0),
        8: bool(vals[8]["net_without_best_day"] > 0 and vals[8]["net_without_best_trade"] > 0),
        9: bool(vals[9]["net_without_2020_02_15_04_30"] > 0 and vals[9]["net_without_2020_2021"] > 0),
        10: bool(vals[10]["w_net"] > 0),
        11: bool(vals[11]["reading_n_net"] > 0),
        12: bool(vals[12]["n"] > 0 and vals[12]["stress_net"] > 0 and vals[12]["pf_base"] >= 1.05),
    }
    return ok, vals


def report_row(env, name, tr, nstar_from=None):
    """a reported row: sized at its own N* and at the $5,000 scale-free figure (or at a named N*)"""
    if len(tr) == 0:
        return {"name": name, "n": 0}
    c = make_cell(env, name, tr, nstar_from)
    sh5 = np.floor(SCALE_FREE_N / tr["E"].to_numpy(float) + 1e-9)
    d5 = daily_series(sh5, tr["u_L_base"].to_numpy(float), tr["ix_L"].to_numpy(np.int64), len(env.sessions))
    nt = nets(c)
    return {"name": name, "n": int(len(tr)), "nstar": c.nstar.n, "net": float(c.daily.sum()), "roc30": roc30(c.daily),
            "t": tstat(c.daily), "pf": pf(nt), "stress_net": float(series(env, c, "L", "stress").sum()),
            "net_5k_uncapped": float(d5.sum()), "roc_5k_uncapped": roc_uncapped(d5)}


def open2_rows(env, regs, spreads):
    """OPEN2: short at D2's 09:30 1m open, no stop, exit X; no 09:30 bar = no trade; SSR-at-open skipped (legal fill
    printed)"""
    six = env.sess_ix()
    rows, legal, skipped = [], [], {"no_0930_bar": 0, "ssr_at_open": 0, "no_bars": 0}
    for ev in regs:
        r = env.photo.bars(ev.symbol, ev.d2)
        if r.status != "ok":
            skipped["no_bars"] += 1
            continue
        day = r.day
        i = RTH0 - PRE0
        if not day.present[i]:
            skipped["no_0930_bar"] += 1
            continue
        h50, h75 = _spread_for(spreads, ev.bucket)
        ssr = bool(day.l[i] <= SSR_FRAC * ev.c1 + EPS)
        if ssr:
            skipped["ssr_at_open"] += 1
            m, E = legal_fill(day, RTH0, float(day.o[i]), None)
            if m is None:
                continue
            em, target = m, legal
        else:
            em, E, target = RTH0, float(day.o[i]), rows
        px, xm, why, last = walk(day, em, np.inf, -1.0, "L")
        if why == "halted_close":
            px, d, nights, how = halted_close_exit(ev, None, last, -1.0)
        else:
            d, nights, how = ev.d2, 0, "intraday"
        rec = {"symbol": ev.symbol, "d2": ev.d2, "wf_year": ev.wf_year, "bucket": ev.bucket, "c1": ev.c1, "adv": ev.adv,
               "entry_m": em, "E": E, "X_L": px, "why_L": why, "xd_L": d, "ix_L": six[pd.Timestamp(d)], "nights_L": nights,
               "how_L": how, "xm_L": xm, "ev": ev}
        for st in (False, True):
            rec[f"u_L_{'stress' if st else 'base'}"] = float(unit_net(E, px, -1.0, h50, h75, st, nights))
        rec["u_L_gross"] = E - px
        target.append(rec)
    return pd.DataFrame(rows), pd.DataFrame(legal), skipped


def ssr_rows(env, sigs, spreads):
    """SSR report: every SSR-active signal (carry-over sessions included) with the Rule-201-legal fill, cell P's stop"""
    six = env.sess_ix()
    out = []
    for s in sigs:
        if s.sig is None or s.status == "no_bars":
            continue
        carry = s.ev.carry
        if not (s.status == "ssr_active" or carry):
            continue
        day = env.photo.bars(s.ev.symbol, s.ev.d2).day
        cmh, _cml = day.reg()
        S = float(cmh[s.sig.last_m - PRE0]) + TICK
        m, E = legal_fill(day, s.sig.close_t, s.sig.c, S)
        if m is None:
            continue
        x = exit_for(day, s.ev, m, S, -1.0, "L", None)
        h50, h75 = _spread_for(spreads, s.ev.bucket)
        rec = {"symbol": s.ev.symbol, "d2": s.ev.d2, "wf_year": s.ev.wf_year, "bucket": s.ev.bucket, "c1": s.ev.c1,
               "adv": s.ev.adv, "signal_close": s.sig.close_t, "entry_m": m, "E": E, "stop": S, "X_L": x.px,
               "why_L": x.reason, "xd_L": x.date, "ix_L": six[x.date], "nights_L": x.nights, "how_L": x.priced_by,
               "xm_L": x.minute, "carry_over": carry, "ev": s.ev}
        for st in (False, True):
            rec[f"u_L_{'stress' if st else 'base'}"] = float(unit_net(E, x.px, -1.0, h50, h75, st, x.nights))
        rec["u_L_gross"] = E - x.px
        out.append(rec)
    return pd.DataFrame(out)


TRADE_COLS = ["symbol", "d2", "exit_date", "signal_close_time", "entry_time", "E", "S", "shares", "notional", "exit_time",
              "X", "exit_reason", "gross", "cost", "locate", "net", "net_N", "flags"]


def _hm_or_none(m):
    if m is None or (isinstance(m, float) and math.isnan(m)):
        return None
    return hm(m)


def trades_csv(cell):
    """section 14's trade rows (reading L, base cost, the cell's shares; net_N = reading N at the same shares)"""
    if cell is None or len(cell.tr) == 0:
        return pd.DataFrame(columns=TRADE_COLS)
    tr, sh = cell.tr, cell.shares
    E = tr["E"].to_numpy(float)
    gross = sh * tr["u_L_gross"].to_numpy(float)
    net = sh * tr["u_L_base"].to_numpy(float)
    loc = sh * LOC_BASE * E * (1.0 + tr["nights_L"].to_numpy(float))
    sc = tr["signal_close"] if "signal_close" in tr.columns else [None] * len(tr)
    stop = tr["stop"].to_numpy(float) if "stop" in tr.columns else np.full(len(tr), np.nan)
    fl = []
    for ev, why in zip(tr["ev"], tr["why_L"]):
        f = [k for k, v in sorted(ev.flags.items()) if v is True]
        if why == "halted_close":
            f.append("halted_close")
        fl.append(";".join(f))
    return pd.DataFrame({
        "symbol": tr["symbol"].to_numpy(), "d2": [f"{pd.Timestamp(d):%Y-%m-%d}" for d in tr["d2"]],
        "exit_date": [f"{pd.Timestamp(d):%Y-%m-%d}" for d in tr["xd_L"]],
        "signal_close_time": [_hm_or_none(m) for m in sc], "entry_time": [_hm_or_none(m) for m in tr["entry_m"]],
        "E": E, "S": stop, "shares": sh, "notional": sh * E, "exit_time": [_hm_or_none(m) for m in tr["xm_L"]],
        "X": tr["X_L"].to_numpy(float), "exit_reason": tr["why_L"].to_numpy(), "gross": gross, "cost": gross - net - loc,
        "locate": loc, "net": net,
        "net_N": sh * tr["u_N_base"].to_numpy(float) if "u_N_base" in tr.columns else np.full(len(tr), np.nan),
        "flags": fl}, columns=TRADE_COLS)


def daily_csv(env, d):
    return pd.DataFrame({"date": [f"{x:%Y-%m-%d}" for x in env.sessions], "pnl_usd": d})


def event_path(env, P, regs, open2):
    """mean / median short mark in bps of E by minute from entry 0..+390 (held at the exit after it), -30..-1 before
    entry; the D2 premarket path (1m close / c(D1) - 1) over all registered sessions with bars; the same for OPEN2"""
    rows = []

    def path(tr):
        taus = np.arange(-30, 391)
        M = np.full((len(tr), len(taus)), np.nan)
        for r_i, r in enumerate(tr.itertuples(index=False)):
            day = env.photo.bars(r.symbol, r.d2).day
            cf = pd.Series(np.where(day.present, day.c, np.nan)).ffill().to_numpy()
            xm = r.xm_L if r.xm_L is not None and not (isinstance(r.xm_L, float) and math.isnan(r.xm_L)) else day.rth1
            for j, tau in enumerate(taus):
                m = int(r.entry_m) + int(tau)
                if tau >= 0 and m >= xm:
                    M[r_i, j] = (r.E - r.X_L) / r.E * 1e4
                elif PRE0 <= m < day.rth1 and np.isfinite(cf[m - PRE0]):
                    M[r_i, j] = (r.E - cf[m - PRE0]) / r.E * 1e4
        return taus, M
    for kind, tr in (("P", P.tr), ("OPEN2", open2)):
        if len(tr) == 0:
            continue
        taus, M = path(tr)
        for j, tau in enumerate(taus):
            col = M[:, j][np.isfinite(M[:, j])]
            rows.append({"kind": kind, "tau": int(tau), "mean_bps": float(col.mean()) if len(col) else None,
                         "median_bps": float(np.median(col)) if len(col) else None, "n": int(len(col))})
    pm = []
    for ev in regs:
        r = env.photo.bars(ev.symbol, ev.d2)
        if r.status != "ok":
            continue
        cf = pd.Series(np.where(r.day.present, r.day.c, np.nan)).ffill().to_numpy()[:RTH0 - PRE0]
        pm.append(cf / ev.c1 - 1.0)
    if pm:
        A = np.vstack(pm)
        for j in range(A.shape[1]):
            col = A[:, j][np.isfinite(A[:, j])]
            rows.append({"kind": "premarket", "tau": int(PRE0 + j), "mean_bps": float(col.mean() * 1e4) if len(col) else None,
                         "median_bps": float(np.median(col) * 1e4) if len(col) else None, "n": int(len(col))})
    return pd.DataFrame(rows, columns=["kind", "tau", "mean_bps", "median_bps", "n"])


def cost_curve(P):
    tr, sh = P.tr, P.shares
    if len(tr) == 0:
        return {}
    E, X = tr["E"].to_numpy(float), tr["X_L"].to_numpy(float)
    nights = tr["nights_L"].to_numpy(float)
    gross = sh * (E - X)
    notional2 = float((sh * (E + X)).sum())
    locbase = sh * E * (1.0 + nights)
    grid = {}
    for bps in COST_BPS:
        for loc in COST_LOC:
            net = gross - sh * (E + X) * bps / 1e4 - loc * locbase
            grid[f"{bps:g}bps_loc{loc * 100:g}%"] = float(net.sum())
    be = {f"loc{loc * 100:g}%": (float((gross - loc * locbase).sum()) / notional2 * 1e4 if notional2 > 0 else None)
          for loc in (0.0, 0.01)}
    base0 = sh * tr["u_L_base"].to_numpy(float) + LOC_BASE * locbase
    bel = {}
    for b in BUCKETS:
        m = (tr["bucket"] == b).to_numpy()
        den = float(locbase[m].sum())
        bel[b] = float(base0[m].sum()) / den * 100.0 if den > 0 else None
    return {"grid_net": grid, "break_even_bps_a_side": be, "break_even_locate_pct_by_bucket": bel}


def capacity(env, P):
    tr, sh = P.tr, P.shares
    if len(tr) == 0:
        return {}
    E = tr["E"].to_numpy(float)
    notional = sh * E
    cap_binds = (CAP_FRAC * tr["adv"].to_numpy(float) < P.nstar.n)
    ent_dv, stop_dv = [], []
    for r in tr.itertuples(index=False):
        day = env.photo.bars(r.symbol, r.d2).day
        i = int(r.entry_m) - PRE0
        p = day.vw[i] if np.isfinite(day.vw[i]) and day.vw[i] > 0 else day.c[i]
        ent_dv.append(day.v[i] * p)
        if r.why_L in ("stop_open", "stop_level") and r.xm_L is not None:
            k = int(r.xm_L) - PRE0
            pk = day.vw[k] if np.isfinite(day.vw[k]) and day.vw[k] > 0 else day.c[k]
            stop_dv.append(day.v[k] * pk)
    per_day = tr.assign(notional=notional).groupby("d2").agg(names=("symbol", "size"), gross=("notional", "sum"))
    conc = 0
    for d2, g in tr.groupby("d2"):
        ev = []
        for r in g.itertuples(index=False):
            end = r.xm_L if r.xm_L is not None and not (isinstance(r.xm_L, float) and math.isnan(r.xm_L)) else RTH1
            ev += [(int(r.entry_m), 1), (int(end), -1)]
        cur = 0
        for _m, dlt in sorted(ev, key=lambda z: (z[0], z[1])):
            cur += dlt
            conc = max(conc, cur)
    return {"nstar": P.nstar.n, "cap_binds_share": float(cap_binds.mean()),
            "median_entry_bar_dollar_volume_over_notional": float(np.median(np.asarray(ent_dv) / notional)),
            "median_stop_bar_dollar_volume_over_notional": (float(np.median(np.asarray(stop_dv) /
                                                                             notional[tr["why_L"].isin(["stop_open", "stop_level"]).to_numpy()]))
                                                            if stop_dv else None),
            "max_names_one_session": int(per_day["names"].max()), "max_gross_short_notional_one_session": float(per_day["gross"].max()),
            "max_concurrent_positions": int(conc)}


def book_add(env, d):
    B = env.book
    ext, leg, bm, ll, _ir, appended = to_book(d, env.sessions, B)
    years = (ext[-1] - ext[0]).days / 365.25
    c = vol_c(leg, bm, ext)
    idx = PL.stationary_indices(len(ext), 1000, 20, np.random.default_rng(BOOK_ADD_SEED))
    out = {"c": c, "appended_days": appended, "rows": []}
    for lab, k in (("c", c), ("0.5c", 0.5 * c), ("2c", 2 * c), ("judged ($30k own DD at N*)", 1.0)):
        for base_name, base in (("#463", bm), ("L", ll)):
            cand = base + k * leg
            st = book_stats(cand, years)
            lead = PL.roc30(cand[idx], years) - PL.roc30(base[idx], years)
            lead = lead[np.isfinite(lead)]
            p5 = float(np.percentile(lead, 5)) if len(lead) else float("nan")
            row = {"size": lab, "k": k, "base": base_name, "roc": st["roc"], "sortino": st["sort"], "p5": p5}
            if base_name == "#463" and lab == "c":
                row["lifts_the_book"] = bool(st["roc"] >= BOOK_REF_BARS[0] and st["sort"] >= BOOK_REF_BARS[1] and p5 > 0)
            out["rows"].append(row)
    return out


def corr_report(env, d):
    B = env.book
    ext, leg, _bm, _ll, ir, _ap = to_book(d, env.sessions, B)
    pos = ext.get_indexer(B.index)
    out = {}
    for name, v in list(B.legs.items()) + [("RES", B.res_c)]:
        x = np.zeros(len(ext))
        x[pos] = v
        for lab, m in (("all", np.ones(len(ext), bool)), ("R", ir)):
            a, b = leg[m], x[m]
            out[f"{name}_{lab}"] = (float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and a.std() > 0 and b.std() > 0 else None)
    return out


def episodes_report(env, d):
    B = env.book
    ext, leg, _bm, _ll, _ir, _ap = to_book(d, env.sessions, B)
    s = pd.Series(leg, index=ext)
    return {"R_45": [{"start": a, "end": b, "pnl": float(s[(s.index >= a) & (s.index <= b)].sum())} for a, b in B.r_episodes],
            "dd463_28": [{"start": a, "end": b, "pnl": float(s[(s.index >= a) & (s.index <= b)].sum())} for a, b in B.dd_episodes]}


def concentration(env, P):
    d, nt = P.daily, nets(P)
    tot = float(d.sum())
    sess = env.sessions

    def wo(lo, hi):
        return float(d[np.asarray((sess < lo) | (sess > hi))].sum())
    worst = P.tr.assign(net=nt).sort_values("net").head(10) if len(nt) else pd.DataFrame()
    return {"top10_share_trades": (float(np.sort(nt)[-10:].sum()) / tot if tot else None),
            "top10_share_days": (float(np.sort(d)[-10:].sum()) / tot if tot else None),
            "no_2020": wo(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31")), "no_2020_21": wo(*Y2021),
            "no_2022": wo(*Y2022),
            "worst10": [{"symbol": r.symbol, "d2": r.d2, "net": r.net, "exit_reason": r.why_L} for r in worst.itertuples()]}


def per_year_report(env, P, sigs):
    out = {}
    nt = nets(P)
    for y in WF_YEARS:
        m = (P.tr["wf_year"] == y).to_numpy() if len(P.tr) else np.zeros(0, bool)
        sy = [s for s in sigs if s.ev.wf_year == y and s.ev.registered]
        out[y] = {"trades": int(m.sum()), "net": float(nt[m].sum()) if len(nt) else 0.0, "pf": pf(nt[m]) if len(nt) else None,
                  "mean_notional": float((P.shares[m] * P.tr["E"].to_numpy(float)[m]).mean()) if m.sum() else None,
                  "ssr_skips": int(sum(s.status == "ssr_active" for s in sy)),
                  "delisted_share": (float(np.mean([bool(s.ev.flags.get("delisted")) for s in sy])) if sy else None)}
    return out


def halves_report(env, d):
    out = {}
    for lo, hi in HALVES:
        m = np.asarray((env.sessions >= lo) & (env.sessions <= hi))
        x = d[m]
        out[f"{lo:%Y-%m-%d}..{hi:%Y-%m-%d}"] = {"net": float(x.sum()), "t": tstat(x), "maxdd": maxdd(x)}
    return out


def vix_report(env, P):
    v = env.vix
    if v is None or len(P.tr) == 0:
        return None
    wf = v[(v.index >= WF0) & (v.index <= WF1)]
    q1, q2 = np.percentile(wf.to_numpy(float), [100 / 3, 200 / 3])
    nt = nets(P)
    lab = []
    for d2 in P.tr["d2"]:
        prev = v[v.index < pd.Timestamp(d2)]
        x = float(prev.iloc[-1]) if len(prev) else float("nan")
        lab.append("low" if x <= q1 else "mid" if x <= q2 else "high" if math.isfinite(x) else "none")
    lab = np.array(lab)
    return {"cuts": [float(q1), float(q2)], "by_tercile": {k: {"n": int((lab == k).sum()), "net": float(nt[lab == k].sum())}
                                                           for k in ("low", "mid", "high", "none")}}


def _primary_rows(df):
    """PMFAIL's primary cell, reading L (column values matched case-insensitively; absent columns keep every row)"""
    m = np.ones(len(df), bool)
    if "cell" in df.columns:
        m &= df["cell"].astype(str).str.lower().isin(["primary", "pm_primary"]).to_numpy()
    if "reading" in df.columns:
        m &= (df["reading"].astype(str).str.upper() == "L").to_numpy()
    return df[m]


def _corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def pmfail_link(env, P):
    """PMFAIL link (report, s.11): the same name-day overlap of filled trades (joint P&L, correlation, the combined
    position against one 1% cap, the second locate a shared position would not pay), PMFAIL D1 trades followed by a
    RUNNER2 D2 trade on the same name, and the daily P&L correlation. Reads PMFAIL r1's trades.csv / daily.csv."""
    tp, dp = os.path.join(pm_dir(), "trades.csv"), os.path.join(pm_dir(), "daily.csv")
    if not os.path.exists(tp):
        return {"status": "PMFAIL trades.csv not on file"}
    pm = _primary_rows(pd.read_csv(tp))
    if not len(P.tr):
        return {"status": "no RUNNER2 trades"}
    E = P.tr["E"].to_numpy(float)
    r2 = pd.DataFrame({"symbol": P.tr["symbol"].to_numpy(), "date": [f"{pd.Timestamp(d):%Y-%m-%d}" for d in P.tr["d2"]],
                       "net_r2": nets(P), "notional_r2": P.shares * E, "adv": P.tr["adv"].to_numpy(float),
                       "locate_r2": P.shares * E * LOC_BASE})
    pmx = pm.rename(columns={"net": "net_pm", "notional": "notional_pm"})
    pmx = pmx[[c for c in ("symbol", "date", "net_pm", "notional_pm") if c in pmx.columns]]
    same = r2.merge(pmx, on=["symbol", "date"])
    out = {"same_name_day": {"n": int(len(same))}}
    if len(same):
        out["same_name_day"].update({
            "joint_net": float((same["net_r2"] + same["net_pm"]).sum()), "corr": _corr(same["net_r2"], same["net_pm"]),
            "combined_over_one_1pct_cap": int(((same["notional_r2"] + same.get("notional_pm", 0.0)) > CAP_FRAC * same["adv"]).sum()),
            "second_locate_usd": float(np.minimum(same["locate_r2"], LOC_BASE * same.get("notional_pm", 0.0)).sum())})
    six = env.sess_ix()
    prev = []
    for sym, d2, n2 in zip(r2["symbol"], P.tr["d2"], r2["net_r2"]):
        i = six.get(pd.Timestamp(d2))
        if i:
            prev.append((sym, f"{env.sessions[i - 1]:%Y-%m-%d}", n2))
    pmk = {(s, d): n for s, d, n in zip(pm["symbol"], pm["date"], pm.get("net", pd.Series([np.nan] * len(pm))))}
    pairs = [(n2, pmk[(s, d)]) for s, d, n2 in prev if (s, d) in pmk]
    out["pmfail_d1_then_runner2_d2"] = {"n": len(pairs), "corr": _corr([a for a, _ in pairs], [b for _, b in pairs])}
    if os.path.exists(dp):
        dd = _primary_rows(pd.read_csv(dp))
        s = pd.Series(dd["pnl_usd"].to_numpy(float), index=pd.to_datetime(dd["date"])).groupby(level=0).sum()
        out["daily_corr"] = _corr(P.daily, s.reindex(env.sessions, fill_value=0.0).to_numpy())
    return out


def mode_run(env, null_sha, out=None, null_path=None):
    out = out or out_dir()
    filed = _read_filed(os.path.join(out, "counts.json"), "counts.json")
    _check_stamp(filed, env, "counts.json")
    pw = _read_filed(os.path.join(out, "power.json"), "power.json")
    _check_stamp(pw, env, "power.json")
    payload, sigs = mode_counts(env, out, write=False)
    a = {k: v for k, v in clean(payload).items()}
    b = {k: v for k, v in filed.items() if k != "meta"}
    if a != b:
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        refuse(f"the recomputed counts differ from the filed counts.json in {diff}")
    nl = read_null(null_path or os.path.join(pm_dir(), "null.json"), null_sha, filed["omega"]["sha256"])
    spreads = filed["spreads"]
    regs = [e for e in env.events if e.registered]
    fl = [s for s in sigs if s.status == "filled"]
    trP = trade_rows(env, fl, spreads, "S")
    trW = trade_rows(env, fl, spreads, "W")
    P, W = make_cell(env, "P", trP), make_cell(env, "W", trW)
    ok, vals = bars_check(env, P, W, nl)
    v = verdict(ok, 4)
    # ---- reports (never cells)
    reports = {}
    sigs_nc = scan(env, regs, HALT_K, nocross=True)
    reports["NOCROSS"] = report_row(env, "NOCROSS", trade_rows(env, sigs_nc, spreads, "S", ("L",)))
    o2, o2legal, o2skip = open2_rows(env, regs, spreads)
    reports["OPEN2"] = {**report_row(env, "OPEN2", o2), "skipped": o2skip,
                        "ssr_legal_fill": report_row(env, "OPEN2_legal", o2legal, P.nstar.n)}
    carry_events = [e for e in env.events if e.carry_kept and e.carry]
    sig_carry = scan(env, carry_events, HALT_K)
    ssr_tr = ssr_rows(env, sigs + sig_carry, spreads)
    reports["SSR_legal_fill"] = report_row(env, "SSR", ssr_tr, P.nstar.n)
    reports["reading_N"] = {"P_net": float(series(env, P, "N", "base").sum()), "W_net": float(series(env, W, "N", "base").sum()),
                            "P_stress_net_N": float(series(env, P, "N", "stress").sum())}
    sigs4 = scan(env, regs, HALT_K4)
    tr4 = trade_rows(env, sigs4, spreads, "S", ("L",))
    reports["halt_4_minute"] = report_row(env, "P_k4", tr4, P.nstar.n)
    subsets = {}
    ft = P.tr
    if len(ft):
        fls = [r.flags for r in ft["ev"]]
        masks = {
            "c1_ge_5": (ft["c1"] >= 5).to_numpy(),
            "c1_lt_5": (ft["c1"] < 5).to_numpy(),
            "active_shortable_today": np.array([f.get("inactive") is False and f.get("ambiguous") is False and f.get("shortable") is True for f in fls]),
            "active_not_shortable_today": np.array([f.get("inactive") is False and f.get("ambiguous") is False and f.get("shortable") is False for f in fls]),
            "revsplit_flagged": np.array([bool(f.get("rev_s1") or f.get("rev_cal") or f.get("rev_m")) for f in fls]),
            "not_revsplit_flagged": np.array([not (f.get("rev_s1") or f.get("rev_cal") or f.get("rev_m")) for f in fls]),
            "delisted": np.array([bool(f.get("delisted")) for f in fls]),
            "active_listed": np.array([not f.get("delisted") for f in fls]),
            "reused_ticker": np.array([bool(f.get("reused")) for f in fls]),
            "without_reused": np.array([not f.get("reused") for f in fls]),
            "without_halted_close": (ft["why_L"] != "halted_close").to_numpy(),
            "s2prime_on": np.array([not r.s2prime for r in ft["ev"]]),
        }
        for k, m in masks.items():
            c = subset_cell(env, P, m)
            subsets[k] = {"n": int(m.sum()), "net": float(c.daily.sum()), "stress_net": float(nets(P, "L", "stress", m).sum()),
                          "pf": pf(nets(P, "L", "base", m))}
        hc = (ft["why_L"] != "halted_close").to_numpy()
        cP = subset_cell(env, P, hc)
        subsets["bars_7_9_without_halted_close"] = {"stress_net": float(nets(P, "L", "stress", hc).sum()),
                                                     "net_without_best_day": float(cP.daily.sum() - cP.daily.max()),
                                                     "net_without_2020_2021": float(cP.daily[np.asarray((env.sessions < Y2021[0]) | (env.sessions > Y2021[1]))].sum())}
    reports["splits"] = subsets
    plc = scan(env, env.nonevents, HALT_K)
    reports["placebo"] = report_row(env, "placebo", trade_rows(env, plc, spreads, "S", ("L",)))
    reports["VIX"] = vix_report(env, P)
    band = [e for e in env.events if e.band_d0_only]
    sig_band = scan(env, band, HALT_K)
    reports["band_on_c_d0_only"] = report_row(env, "band_c_d0", trade_rows(env, sig_band, spreads, "S", ("L",)), P.nstar.n)
    if len(ft):
        hcx = ft[ft["why_L"] == "halted_close"]
        reports["halted_close"] = {"by_year": hcx.groupby("wf_year").size().to_dict(),
                                   "by_pricing": hcx.groupby("how_L").size().to_dict()}
        hpos = np.flatnonzero((ft["why_L"] == "halted_close").to_numpy())
        items = []
        for i in hpos:
            ev = ft["ev"].iloc[i]
            res = split_cap(ev.nxt_open, ev.nxt_sc, ev.nxt_m, float(ft["X_L"].iloc[i]), -1.0)
            items.append((res, ft["how_L"].iloc[i] == "stress_split", P.shares[i]))
        reports["halted_close"]["split_cap_L"] = split_cap_report(items)
        reports["stop_exit_on_resume_bar_open"] = int(ft["onres_L"].sum())
    reports["concentration"] = concentration(env, P)
    # ---- diagnostics
    ep = event_path(env, P, regs, o2)
    sh5 = np.floor(SCALE_FREE_N / P.tr["E"].to_numpy(float) + 1e-9) if len(P.tr) else np.zeros(0)
    d5 = daily_series(sh5, P.tr["u_L_base"].to_numpy(float), P.tr["ix_L"].to_numpy(np.int64), len(env.sessions)) \
        if len(P.tr) else np.zeros(len(env.sessions))
    stage = {
        "cells": {"P": judged_stats(env, P.daily), "W": judged_stats(env, W.daily)},
        "n_star": {"P": P.nstar.n, "W": W.nstar.n, "P_crossed": P.nstar.crossed, "W_crossed": W.nstar.crossed},
        "checks": {str(k): {"pass": ok[k], "value": vals[k]} for k in sorted(ok)},
        "verdict": v,
        "reports": reports,
        "halves": halves_report(env, P.daily),
        "per_year": per_year_report(env, P, sigs),
        "cost_curve": cost_curve(P),
        "capacity": capacity(env, P),
        "episodes_R": episodes_report(env, P.daily),
        "corr": corr_report(env, P.daily),
        "book_add": book_add(env, P.daily),
        "overlap": filed.get("schedule_overlap"),
        "pmfail_link": pmfail_link(env, P),
        "info": {"P_uncapped_5k": {"net": float(d5.sum()), "roc": roc_uncapped(d5)},
                 "feed": env.photo.feed,
                 "interpretations": [{"prereg": q, "reading": r} for q, r in INTERPRETATIONS],
                 "power_notion_b": nl["summary"].get("notion_b_roc30") or nl["summary"].get("notion_b"),
                 "binding_max4_p95": {st: nl["summary"]["max4"][st]["p95"] for st in STATS3},
                 "bonferroni_runner2_p97_5": {st: _null_leg(nl["summary"])[st]["p97.5"] for st in STATS3}},
        "shas": clean(stamp_core(env)),
        "null": nl,
        "power": pw.get("lines"),
    }
    tr_nc = trade_rows(env, sigs_nc, spreads, "S")
    for name, df in (("trades_P.csv", trades_csv(P)), ("trades_W.csv", trades_csv(W)),
                     ("trades_OPEN2.csv", trades_csv(make_cell(env, "OPEN2", o2) if len(o2) else None)),
                     ("trades_NOCROSS.csv", trades_csv(make_cell(env, "NOCROSS", tr_nc) if len(tr_nc) else None)),
                     ("trades_SSR.csv", trades_csv(make_cell(env, "SSR", ssr_tr, P.nstar.n) if len(ssr_tr) else None))):
        write_once(os.path.join(out, name), csv_bytes(df))
    write_once(os.path.join(out, "daily_P.csv"), csv_bytes(daily_csv(env, P.daily)))
    write_once(os.path.join(out, "daily_W.csv"), csv_bytes(daily_csv(env, W.daily)))
    write_once(os.path.join(out, "event_path.csv"), csv_bytes(ep))
    write_once(os.path.join(out, "stage_a.json"), dumps(stage))
    print(f"RUNNER2 r1 STAGE A: verdict {v}")
    for k in sorted(ok):
        print(f"  bar {k:>2}: {'PASS' if ok[k] else 'FAIL'}  {json.dumps(clean(vals[k]))[:160]}")
    return stage


# ================================================================== the real environment (sha-checked inputs)
def _builder():
    try:
        import disc_gapper_namedays as NB
    except ImportError:
        refuse("tools/disc_gapper_namedays.py is not in this checkout (commit b9107d45): rebase onto a main that has it")
    return NB


def verify_preregs(docs=None):
    docs = docs or os.path.join(REPO, "docs")
    got = {}
    for n, want in PREREG_SHA_LF.items():
        g = sha256_lf(os.path.join(docs, n))
        if g != want:
            refuse(f"{n} (LF) hashes to {g}, the amended text is {want} (Amendment 1 must be in this checkout)")
        got[n] = g
    return got


def load_vix(path=None):
    path = path or os.path.join(home(), "_research_cache", "public_series", "cboe", "VIX_History.csv")
    with open(path, "rb") as f:
        data = f.read()
    if sha256_bytes(data) != SHA["VIX_History.csv"]:
        refuse(f"VIX_History.csv hashes to {sha256_bytes(data)}, section 4 pins {SHA['VIX_History.csv']}")
    v = pd.read_csv(io.BytesIO(data))
    v.columns = [c.strip().upper() for c in v.columns]
    v["DATE"] = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    v = v[v["DATE"] <= WF1].set_index("DATE")["CLOSE"].astype(float)
    return v


def load_env(manifest_sha, require_probe=True, probe_log=None):
    """every input sha-checked, the builder re-run and its csv re-hashed, then the per-name-day daily context"""
    import pyarrow.parquet as pq
    import import_alpaca_stocks as IAS
    if set(IAS.EARLY_CLOSE_DATES) != set(EARLY_CLOSE_DATES):
        refuse("EARLY_CLOSE_DATES here differ from tools/import_alpaca_stocks.py")
    import r5_siporb as S5
    pre = verify_preregs()
    NB = _builder()
    inputs = NB.verify_inputs()
    hm_ = os.path.join(home(), "alpaca_cache")
    assets_p = os.path.join(hm_, "siporb", "assets.csv")
    nd_p = os.path.join(hm_, "disc_gapper", "namedays_r1.csv")
    nd_sha_p = os.path.join(hm_, "disc_gapper", "namedays_r1.sha256")
    for k, p in (("assets.csv", assets_p), ("namedays_r1.csv", nd_p)):
        if sha256_file(p) != SHA[k]:
            refuse(f"{k} does not hash to {SHA[k]}")
    with open(nd_sha_p, "rb") as f:
        if f.read().decode("utf-8").split()[0] != NAMEDAYS_SHA:
            refuse("namedays_r1.sha256 does not carry the posted sha")
    res = NB.build(NB.read_daily(NB.RAW_PATH, ("symbol", "date", "o", "l", "c", "v")),
                   NB.read_daily(NB.SPLIT_PATH, ("symbol", "date", "o", "c")), NB.read_calendar(NB.CA_PATH))
    data = NB.csv_bytes(res.rows)
    if sha256_bytes(data) != NAMEDAYS_SHA:
        refuse("the builder no longer reproduces namedays_r1.csv byte for byte")
    rows = res.rows
    days, allsyms = res.days, res.syms
    sel = rows[(rows["runner2_d2"] == 1) | (rows["runner2_nonevent"] == 1)]
    syms = sorted(set(sel["symbol"]))
    cols = pd.Index(allsyms).get_indexer(syms)
    flt = [("date", "<", CUT.to_pydatetime()), ("symbol", "in", syms)]
    raw = pq.read_table(NB.RAW_PATH, columns=["symbol", "date", "o", "l", "c", "v"], filters=flt).to_pandas()
    spl = pq.read_table(NB.SPLIT_PATH, columns=["symbol", "date", "o", "c"], filters=flt).to_pandas()
    raw["symbol"], spl["symbol"] = raw["symbol"].astype(str), spl["symbol"].astype(str)
    G, EX, _gi = NB._grid(raw, days, syms, ("o", "l", "c", "v"))
    GS, _ex2, _gi2 = NB._grid(spl, days, syms, ("o", "c"))
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = (G["o"] / GS["o"]) / NB.shift(G["c"] / GS["c"], 1)
        known = np.isfinite(ratio) & (ratio > 0)
        S1 = known & (np.abs(ratio - 1.0) > NB.S1_TOL)
        S1rev = known & (ratio > 1.0 + NB.S1_TOL)
    if not (S1 == res.masks["S1"][:, cols]).all():
        refuse("the recomputed S1 differs from the builder's on the listed symbols")
    ca = NB.read_calendar(NB.CA_PATH)
    CALrev, _ = NB.calendar_splits(ca[ca["type"].isin(["reverse_split", "name_change"])], days, syms)
    M = res.masks["M"][:, cols]
    CAL = res.masks["CAL"][:, cols]
    unc = pq.read_table(NB.RAW_PATH, columns=["symbol", "date"], filters=[("symbol", "in", syms)]).to_pandas()
    last_bar = unc.groupby(unc["symbol"].astype(str))["date"].max()
    a = pd.read_csv(assets_p, dtype=str, keep_default_na=False)
    a_by = {s: g for s, g in a.groupby("symbol")}
    bad = 0
    for s in syms:
        for r in (a_by.get(s, pd.DataFrame()).itertuples() if s in a_by else []):
            if S5.why_not(s, r.name, r.exchange) is not None:
                bad += 1
                break
    O, L, C, V = G["o"], G["l"], G["c"], G["v"]
    T = len(days)
    dix = {d: i for i, d in enumerate(days)}
    six = {s: j for j, s in enumerate(syms)}
    rreg, rloose = res.masks["r_reg"][:, cols], res.masks["r_loose"][:, cols]

    def ctx_row(rec, is_event):
        t, j = dix[pd.Timestamp(rec.date)], six[rec.symbol]
        c0, c1, l1 = C[t - 2, j], C[t - 1, j], L[t - 1, j]
        adv = float(np.mean(C[t - 21:t - 1, j] * V[t - 21:t - 1, j]))
        if not np.isfinite(adv):
            refuse(f"ADV$ undefined for {rec.symbol} {rec.date}")
        nd, no, nf, nsc, nm = [], [], [], [], []
        for k in range(1, 11):
            if t + k >= T:
                break
            nd.append(days[t + k])
            no.append(float(O[t + k, j]) if EX[t + k, j] else float("nan"))
            nf.append(bool(S1[t + k, j] or CAL[t + k, j] or M[t + k, j]))
            nsc.append(bool(S1[t + k, j] or CAL[t + k, j]))
            nm.append(bool(M[t + k, j]))
        lo, hi = days[t] - pd.Timedelta(days=60), days[t] - pd.Timedelta(days=1)
        w = np.asarray((days >= lo) & (days <= hi))
        g = a_by.get(rec.symbol)
        st = set(g["status"]) if g is not None else set()
        shortv = set(g["shortable"]) if g is not None else set()
        etb = set(g["easy_to_borrow"]) if g is not None else set()
        flags = {"rev_s1": bool(S1rev[w, j].any()), "rev_cal": bool(CALrev[w, j].any()), "rev_m": bool(M[w, j].any()),
                 "delisted": bool(pd.Timestamp(last_bar[rec.symbol]) < DELISTED_BEFORE),
                 "inactive": bool(st and st == {"inactive"}), "ambiguous": bool(len(st) > 1),
                 "shortable": (None if len(shortv) != 1 else next(iter(shortv)) == "True"),
                 "easy_to_borrow": (None if len(etb) != 1 else next(iter(etb)) == "True"),
                 "reused": bool(g is not None and len(g) > 1)}
        carry = bool(l1 <= SSR_FRAC * c0)
        band1 = bool(1.0 <= c1 <= 20.0)
        m_d1 = bool(M[t - 1, j])
        reg = bool(rreg[t, j]) if is_event else False
        if is_event and reg != (bool(rloose[t, j]) and band1 and not m_d1 and not carry):
            refuse(f"registered-set parity failed on {rec.symbol} {rec.date}")
        g2 = np.array([O[t, j] / c1])
        return Event(rec.symbol, days[t], rec.wf_year, rec.price_bucket, float(c0), float(c1), float(l1), adv,
                     float(V[t, j]), float(O[t, j]), tuple(nd), tuple(no), tuple(nf),
                     days[t + 1] if t + 1 < T else None, bool(t + 10 >= T), reg,
                     bool(is_event and not m_d1 and not carry), bool(is_event and band1 and not m_d1), carry,
                     bool(NB.big_whole(g2, inverse=True)[0]), bool(rec.quotes_runner2 == 1), bool(rec.pmfail_event == 1),
                     flags, tuple(nsc), tuple(nm))
    events = [ctx_row(r, True) for r in rows[rows["runner2_d2"] == 1].itertuples(index=False)]
    nonev = [ctx_row(r, False) for r in rows[rows["runner2_nonevent"] == 1].itertuples(index=False)]
    if sum(e.registered for e in events) != int(res.masks["r_reg"].sum()):
        refuse("registered events on the list differ from the builder's r_reg")
    sessions = days[(days >= WF0) & (days <= WF1)]
    photo = Photograph(pull_root(), manifest_sha, NAMEDAYS_SHA, require_probe, probe_log)
    photo.verify([(e.symbol, f"{e.d2:%Y-%m-%d}") for e in events + nonev],
                 [(e.symbol, f"{e.d2:%Y-%m-%d}") for e in events if e.registered and e.quotes])
    book = load_book()
    vix = load_vix()
    bc = res.counts
    builder_counts = {"runner2": bc["runner2"], "test_m_calibration": bc["test_m_calibration"],
                      "count_bar_daily_cache": bc["count_bar"]["runner2"], "m_keeps_volume": res.m_keeps_volume}
    stamp = {"preregs_sha256_lf": pre, "daily_and_calendar": inputs["sha256"], "siporb_manifest": inputs["siporb_manifest_sha256"],
             "pinned": {k: SHA[k] for k in ("assets.csv", "residual_days.csv", "a2.json", "line.csv", "episodes.csv",
                                            "book463_daily.csv", "VIX_History.csv", "namedays_r1.csv")},
             "builder_sha256_lf": sha256_lf(os.path.join(HERE, "disc_gapper_namedays.py"))}
    return Env(events, nonev, sessions, photo, book, vix, builder_counts, stamp, bad)


def main(argv=None):
    ap = argparse.ArgumentParser(description="RUNNER2 r1 Stage A (docs/PREREG_runner2_r1_2026-10-06.md)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--counts", action="store_true")
    g.add_argument("--power", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--manifest-sha", required=True, help="the pull manifest's sha256 as MANAGER names it")
    ap.add_argument("--null-sha", help="the posted sha256 of PMFAIL r1's null.json (--run)")
    ap.add_argument("--probe-log", help="the FB/META probe log when it is not in the manifest (sha256 stamped)")
    a = ap.parse_args(argv)
    env = load_env(a.manifest_sha, probe_log=a.probe_log)
    if a.counts:
        return mode_counts(env)[0]
    if a.power:
        return mode_power(env)
    return mode_run(env, a.null_sha)


if __name__ == "__main__":
    main()
