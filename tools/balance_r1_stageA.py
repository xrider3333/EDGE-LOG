# -*- coding: utf-8 -*-
"""BALANCE r1 STAGE A - NQ range-day VWAP fade on no-NOISE-break-by-noon days (docs/PREREG_balance_r1_2026-10-06.md).

A BALANCE day is a trading session on which no close of any bar stamped 09:35 .. 11:55 broke #304's own noise band
(NOISE_1_0 with NOISE_1_8_CT304's _FROZEN core). From the 11:55 close to the 15:25 close, a close stretched at least x of
the room from NOISE's session VWAP to the band edge is faded toward VWAP: fill at the next open, exit at the next open
after a close at or through VWAP (TARGET) or after any raw band break (STOP / OPP-BREAK, the live band), flat at the
15:55 close. One position at a time; re-entry only after a TARGET. 1 NQ, $20 a point, 0.533 points a round trip.

Cells: B1 (PRIMARY) x >= 1/2 and B2 x >= 2/3. ES is a transfer report. The band twins of B1 (lookback 20 / 40 / 60,
multipliers 1.0 / 1.0) are reports (AMENDMENT 0 item 4). Nothing after 2025-06-29 is ever in memory.

  python tools/balance_r1_stageA.py --counts         counts and the three-way split BEFORE any exit is run (section 4)
  python tools/balance_r1_stageA.py --power          the power lines, the family null p95s and the overlap test (5-7)
  python tools/balance_r1_stageA.py                  Stage A (sections 8-9; ES transfer report)
  python tools/balance_r1_stageA.py --prereg-hashes  print the prereg hashes the harness pins (reads no data)

Every mode first runs: the prereg check, the master loads and cut asserts, #463's parity, L's parity, R, the band
build and the binding parity with #304 (trades, band / VWAP values at its decision bars, eligible first breaks).
"""
import hashlib
import io
import json
import math
import os
import re
import sys
import warnings
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
import halfhour_r1_stageA as HH                                       # noqa: E402  (book, own stats, sizing, worst window)
import power_line as PL                                               # noqa: E402
import r11_risk as R11                                                # noqa: E402  (sha_lf)

# ------------------------------------------------------------------ frozen constants (prereg sections 3, 5, 6, 8)
CUT_S = "2025-06-29"
CUT = pd.Timestamp(CUT_S)
CUT_MSG = "a bar after 2025-06-29 is in memory - abort"
D0 = "2010-06-07"
WF0, WF1 = pd.Timestamp("2016-07-01"), CUT
EARLY1 = pd.Timestamp("2016-06-30")
MASTERS = {"NQ": (37, "NOADJ_NQ_5m_RTH.csv"), "ES": (33, "NOADJ_ES_5m_RTH.csv")}
TTM_MASTER = (61, "ADJ_ES_30m_RTH.csv")              # registry row 61 = ES 30m rth db_adj_rth (read-only lookup, 10-06)
INST = {"NQ": dict(mult=20.0, cost=0.533, stress=1.533), "ES": dict(mult=50.0, cost=0.363, stress=1.363)}
CELLS = (("B1", 6), ("B2", 8))                       # stretch threshold in twelfths: 6/12 = 1/2, 8/12 = 2/3
OPEN_HM, NOON_LAST, SIG_FIRST, SIG_LAST, LAST_HM = 570, 715, 715, 925, 955   # stamps, minutes after midnight ET
TWINS = (("twin20", 20), ("twin40", 40), ("twin60", 60))    # B1's band twins: lookback, multipliers 1.0 / 1.0
SEED_NULL, SEED_BOOT, DRAWS, BLOCK = 20261006, 20261005, 1000, 20
N_PARITY, N_INDEX, N_SUNDAY, N_WF_SWITCHES = 2797, 2626, 280, 36
R_DAYS, R_EPIS, DD_DAYS, DD_EPIS = 762, 45, 460, 28
RES_W = 0.264
BOOK_FACTS, LINE_FACTS = (93.81, 3.816), (120.82, 3.916)
BOOK_REF_BARS = (98.50, 3.816)
LINE_BAR = (126.86, 3.916)    # the prereg's printed bar (section 8: 1.05 x 120.82 = 126.86), rounded as 98.50 is
X20 = (pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-30"))
WORST = (pd.Timestamp("2020-03-02"), pd.Timestamp("2020-03-27"))    # #463's worst WF drawdown: peak day, trough day
HALVES = ((pd.Timestamp("2016-07-01"), pd.Timestamp("2021-12-31")), (pd.Timestamp("2022-01-01"), CUT))
# Section 9 cost curve, points a round trip per full contract, keyed by instrument ("ES gets the same rows"): gross 0,
# house, +1 tick a side, the micro contract per full-contract equivalent (MNQ 1.20 / MES 0.63, r11_risk MICRO_RT;
# PREREG_RISK_R1 line 105) and +2 ticks a side (= the stress cost).
COST_CURVE = {"NQ": (("gross 0", 0.0), ("house", 0.533), ("+1 tick a side", 1.033), ("MNQ", 1.20),
                     ("+2 ticks a side", 1.533)),
              "ES": (("gross 0", 0.0), ("house", 0.363), ("MES", 0.63), ("+1 tick a side", 0.863),
                     ("+2 ticks a side", 1.363))}
VW_SIGMA = 2.0
DISP_COVER, DISP_WIN, DISP_MIN, DISP_EDGES = 0.80, 252, 60, (33.3, 66.7)
TAUS = np.arange(0, 391, 5)
STOP, TARGET, OPP, FLAT = "STOP", "TARGET", "OPP-BREAK", "FLAT"
EXITS = (TARGET, STOP, OPP, FLAT)

# The Auto-Validate search, declared before any number (AMENDMENT 0 item 6; section 11): 4 x 2 = 8 configs, never a
# pinned file; window pinned to WF, 900 trials, lockbox veto-only. Default = the passing cell's stretch, last fill 15:30.
AV_SPACE = {
    "stretch_12ths": {"default": 6, "min": 6, "max": 9, "step": 1, "type": "int",
                      "label": "stretch threshold in twelfths (6 = 1/2 = B1, 7 = 7/12, 8 = 2/3 = B2, 9 = 3/4)"},
    "last_fill_min": {"default": 360, "min": 330, "max": 360, "step": 30, "type": "int",
                      "label": "last fill, minutes after 09:30 (330 = 15:00, signal 14:55; 360 = 15:30, signal 15:25)"},
}

# ------------------------------------------------------------------ paths (inputs read-only; data from the shared checkout)
EDGELOG_HOME = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
ANAT = os.path.join(EDGELOG_HOME, "_anatomy_cache")
CACHE = os.environ.get("EDGELOG_BALANCE_R1") or os.path.join(ANAT, "balance_r1")
Q19 = os.path.join(ANAT, "q19")
RESID_CSV = os.path.join(Q19, "residual_days.csv")
LINE_CSV = os.path.join(Q19, "line.csv")
A2_JSON = os.path.join(Q19, "a2.json")
EPIS_CSV = os.path.join(Q19, "episodes.csv")
RES_CSV = os.path.join(ANAT, "rocfrontier", "resmom_r1", "resmom_cells_daily_wf.csv")
LEGS_DIR = os.path.join(EDGELOG_HOME, "book_legs")
OPEN_BARS = os.path.join(EDGELOG_HOME, "alpaca_cache", "nqbrd", "open_bars.csv")
ROLLS_CSV = os.path.join(ROOT, "tools", "data", "rolls_%s.csv")
NDX_CSV = os.path.join(ROOT, "tools", "data", "ndx_members.csv")
PREREG = os.path.join(REPO, "docs", "PREREG_balance_r1_2026-10-06.md")
OUTDIR = os.path.join(HERE, "r37_results")
OUTFILE = {"counts": "balance_r1_stageA_counts.txt", "power": "balance_r1_stageA_power.txt", "run": "balance_r1_stageA.txt"}
RESID_SHA = "bfe64d87a2cf6fd569181ffae9092317653844126de075fe64844430ac189f60"   # sha256 of the BYTES (prereg bar 2)
RES_SHA = "bed7bf8b98d201894471cd3e72bd146bb87260c6cc8d1ac54b8167f923d41819"     # r18_divrun.py REF_SHA (bytes)
# Pinned on the GO text (prereg with AMENDMENT 0, MANAGER #40). Sections 3, 6 and 8 may never change (abort); the
# whole-file hash may change with AMENDMENT 1 (reported). `--prereg-hashes` prints both for re-pinning at the GO commit.
PREREG_GO_SHA_LF = "6c066a395a811febec07984282fb874f1e3aab9cd84a1fc9b4bff6ddafaab200"
PREREG_SECTIONS_SHA = "db495f4dcbab5f819e97e65f13999287d5e0f4b6c51aba7b018a7426f9969ace"

MODE = None          # "counts" | "power" | "run"; set by main() only


def sig_last_for(last_fill_min):
    """The Auto-Validate last-fill knob -> the last signal-bar stamp (minutes after midnight): 360 -> 925 (15:25)."""
    return OPEN_HM + int(last_fill_min) - 5


# ================================================================== small helpers
class Tee:
    """Mirror stdout into tools/r37_results/<mode file>."""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "w", encoding="utf-8")
        self.o = sys.stdout

    def write(self, s):
        self.o.write(s)
        self.f.write(s)

    def flush(self):
        self.o.flush()
        self.f.flush()

    def close(self):
        self.f.close()


def _require_run(what):
    """Anything that prints a real BALANCE net, PF or R-sum runs only in the real run."""
    if MODE != "run":
        raise RuntimeError("%s prints real BALANCE direction and runs only in the real run (MODE=%r)" % (what, MODE))


def fm(v):
    if v is None or not np.isfinite(v):
        return "nan"
    return ("-$" if v < 0 else "$") + format(int(round(abs(v))), ",")


def f2(v, d=2):
    return "nan" if v is None or not np.isfinite(v) else ("%." + str(d) + "f") % v


def sha_bytes(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def naive(ix):
    ix = pd.DatetimeIndex(ix)
    return ix.tz_convert("US/Eastern").tz_localize(None) if ix.tz is not None else ix


def jy(dates):
    """July-June year Y of each date: Y-07-01 <= date < (Y+1)-07-01."""
    d = pd.DatetimeIndex(dates)
    return np.where(d.month >= 7, d.year, d.year - 1)


def jy_label(y):
    return "2010-06 warm-up" if y == 2009 else "%d-%02d" % (y, (y + 1) % 100)


def strategy(name):
    from augur_engine.strategies import load_strategy
    return load_strategy(name)


def noise_mod():
    return strategy("NOISE_1_0.py")


# ================================================================== prereg (sections 3, 6 and 8 frozen)
def prereg_sections(text, nums=(3, 6, 8)):
    """{n: the text of '## n. ...' up to the next '## ' heading}, LF-normalised."""
    out, cur = {}, None
    for ln in text.replace("\r\n", "\n").split("\n"):
        if ln.startswith("## "):
            mm = re.match(r"^## (\d+)\. ", ln)
            cur = int(mm.group(1)) if mm else None
        if cur in nums:
            out.setdefault(cur, []).append(ln)
    if set(out) != set(nums):
        raise SystemExit("prereg: sections %s not all found (found %s) - abort" % (nums, sorted(out)))
    return {k: "\n".join(v).rstrip("\n") for k, v in out.items()}


def sections_sha(text):
    sec = prereg_sections(text)
    return hashlib.sha256("\n\x00\n".join(sec[k] for k in (3, 6, 8)).encode("utf-8")).hexdigest()


def prereg_hashes(path=None):
    path = path or PREREG
    with open(path, "rb") as f:
        text = f.read().decode("utf-8")
    return {"sha256_lf": R11.sha_lf(path), "sections_3_6_8_sha256": sections_sha(text)}


def prereg_check(path=None, go_sha=None, sec_sha=None):
    """Abort if sections 3, 6 or 8 differ from the GO text; report (never abort) a whole-file change (AMENDMENT 1)."""
    path = path or PREREG
    go_sha = PREREG_GO_SHA_LF if go_sha is None else go_sha
    sec_sha = PREREG_SECTIONS_SHA if sec_sha is None else sec_sha
    h = prereg_hashes(path)
    if h["sections_3_6_8_sha256"] != sec_sha:
        raise SystemExit("prereg: sections 3, 6 or 8 changed after GO (%s, pinned %s) - abort"
                         % (h["sections_3_6_8_sha256"], sec_sha))
    h["go_sha256_lf"] = go_sha
    h["whole_file_changed_since_go"] = h["sha256_lf"] != go_sha
    return h


# ================================================================== loading and cuts (section 3.1)
def assert_cut_index(ix):
    ix = pd.DatetimeIndex(ix)
    if len(ix) and naive(ix)[-1].normalize() > CUT:
        raise SystemExit(CUT_MSG)


def load_master(inst, tf="5m", source="db_noadj_rth", expect=None):
    """Registry id / filename / source asserted; nothing after 2025-06-29; volume present and finite."""
    expect = expect or MASTERS[inst]
    m = find_master(inst, tf, "rth", source)
    if m is None:
        raise SystemExit("no %s %s rth %s master registered - abort" % (inst, tf, source))
    if int(m.get("id", -1)) != expect[0] or m.get("filename") != expect[1] or m.get("source") != source:
        raise SystemExit("%s %s master is id %s / %s / %s, expected id %d / %s / %s - abort" % (
            inst, tf, m.get("id"), m.get("filename"), m.get("source"), expect[0], expect[1], source))
    if source.startswith("db_adj") and tf == "5m":
        raise SystemExit("NOISE bands never run on an ADJ master (ledger 2.71) - abort")
    A = load_master_arrays(m, date_from=D0, date_to=CUT_S)
    assert_cut_index(A["index"])
    if tf == "5m":
        v = A.get("volume")
        if v is None or not np.isfinite(np.asarray(v, float)).all():
            raise SystemExit("%s master volume missing or not finite - abort" % inst)
    return A


def cut(df, cols, name, verbose=True):
    """Keep rows on or before 2025-06-29 in EVERY named column; print the drop; assert the max."""
    keep = np.ones(len(df), bool)
    for c in cols:
        keep &= (pd.DatetimeIndex(pd.to_datetime(df[c])).normalize() <= CUT)
    out = df[keep].reset_index(drop=True)
    for c in cols:
        if len(out) and pd.Timestamp(pd.to_datetime(out[c]).max()).normalize() > CUT:
            raise SystemExit("cut failed on %s.%s - abort" % (name, c))
    if verbose:
        print("  cut %-24s %7d rows kept, %5d dropped (on or after 2025-06-30)" % (name, len(out), len(df) - len(out)))
    return out


def load_rolls(inst, path=None):
    """Real switches (kind != not_a_roll), naive ET switch_et, cut to the WF end; offset kept for the data notes."""
    path = path or ROLLS_CSV % inst
    r = pd.read_csv(path)
    r = r[r["kind"].astype(str) != "not_a_roll"].copy()
    r["switch_et"] = pd.to_datetime(r["switch_et"])
    r = r[r["switch_et"].dt.normalize() <= CUT].sort_values("switch_et").reset_index(drop=True)
    return r[["switch_et", "offset_pts", "kind", "old", "new"]]


def load_crown(name, path=None):
    """A crown trade file -> entry / exit (naive ET), side +-1, unit_usd = pnl_usd / size; cut on BOTH stamps.
    NOISE files are naive ET (stamps 09:30-15:55 asserted); ORB / ENGU-Q stamps carry offsets and are converted."""
    path = path or os.path.join(LEGS_DIR, "%s_raw_trades.csv" % name)
    df = pd.read_csv(path)
    if name.startswith("NOISE"):
        e0, e1 = pd.to_datetime(df["entry_time"]), pd.to_datetime(df["exit_time"])
        if e0.dt.tz is not None or e1.dt.tz is not None:
            raise SystemExit("%s: NOISE stamps must be naive US/Eastern - abort" % name)
        for s in (e0, e1):
            hm = s.dt.hour * 60 + s.dt.minute
            if not ((hm >= OPEN_HM) & (hm <= LAST_HM)).all():
                raise SystemExit("%s: a NOISE stamp outside 09:30-15:55 - abort" % name)
    else:
        e0 = pd.to_datetime(df["entry_time"], utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None)
        e1 = pd.to_datetime(df["exit_time"], utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None)
    side = df["side"].astype(str).str.lower().map({"long": 1, "short": -1})
    if side.isna().any():
        raise SystemExit("%s: unreadable side - abort" % name)
    out = pd.DataFrame({"entry": e0, "exit": e1, "side": side.astype(int), "pnl_usd": df["pnl_usd"].astype(float),
                        "size": df["size"].astype(float)})
    out["unit_usd"] = out["pnl_usd"] / out["size"]
    straddle = int(((out["entry"].dt.normalize() <= CUT) & (out["exit"].dt.normalize() > CUT)).sum())
    out = cut(out, ["entry", "exit"], name)
    if straddle:
        print("    %s: %d trade(s) entered on or before 2025-06-29 and exited after it - dropped (the exit is lockbox "
              "information)" % (name, straddle))
    return out


def load_R(bdays, path=None, a2_path=None):
    """in_R aligned to #463's WF index: sha pinned, dates row for row, 762 days, = the union of a2's 45 episodes."""
    path = path or RESID_CSV
    with open(path, "rb") as f:
        data = f.read()
    sha = hashlib.sha256(data).hexdigest()
    if sha != RESID_SHA:
        raise SystemExit("residual_days.csv sha256 %s is not the pinned %s - abort" % (sha, RESID_SHA))
    df = pd.read_csv(io.BytesIO(data))
    dates = pd.DatetimeIndex(pd.to_datetime(df["date"]))
    if dates.max() > CUT:
        raise SystemExit("residual_days.csv has a row after 2025-06-29 - abort")
    if len(dates) != len(bdays) or not (dates == pd.DatetimeIndex(bdays)).all():
        raise SystemExit("residual_days.csv dates are not #463's WF index row for row - abort")
    inR = df["in_R"].astype(str).str.lower().map({"true": True, "false": False})
    if inR.isna().any() or int(inR.sum()) != R_DAYS:
        raise SystemExit("residual_days.csv in_R sums to %s, not %d - abort" % (inR.sum(), R_DAYS))
    inR = pd.Series(inR.to_numpy(bool), index=pd.DatetimeIndex(bdays))
    with open(a2_path or A2_JSON, encoding="utf-8") as f:
        a2 = json.load(f)
    eps = [(pd.Timestamp(s), pd.Timestamp(e)) for s, e in a2["line_episodes"]]
    if len(eps) != R_EPIS:
        raise SystemExit("a2.json has %d line episodes, not %d - abort" % (len(eps), R_EPIS))
    if max(e for _, e in eps) > CUT:
        raise SystemExit("a2.json has a line episode after 2025-06-29 - abort")
    u = np.zeros(len(bdays), bool)
    for s, e in eps:
        u |= np.asarray((inR.index >= s) & (inR.index <= e))
    if not (u == inR.to_numpy()).all():
        raise SystemExit("the union of a2.json line_episodes is not in_R - abort")
    if abs(float(a2.get("c_res", RES_W)) - RES_W) > 1e-12:
        raise SystemExit("a2.json c_res is not 0.264 - abort")
    return inR, eps, a2


def load_episodes(bdays, path=None):
    """#463's 28 drawdown episodes (inclusive day ranges, 460 days)."""
    ep = pd.read_csv(path or EPIS_CSV)
    s, e = pd.to_datetime(ep["start"]), pd.to_datetime(ep["end"])
    if e.max() > CUT:
        raise SystemExit("episodes.csv has an episode after 2025-06-29 - abort")
    eps = list(zip(s, e))
    u = np.zeros(len(bdays), bool)
    for a, b in eps:
        u |= np.asarray((bdays >= a) & (bdays <= b))
    if len(eps) != DD_EPIS or int(u.sum()) != DD_DAYS:
        raise SystemExit("episodes.csv: %d episodes / %d days, expected %d / %d - abort" % (len(eps), u.sum(), DD_EPIS, DD_DAYS))
    return eps, u


def load_L(B, path=None, line_path=None):
    """RES pinned by the sha of its bytes, dates = #463's WF index, book_mtm = B within $1 (r18_divrun REF_BOOK_ATOL:
    book_mtm is rounded text from the 2010-06-07 .. 2026-06-30 book build, B is the .. 2025-06-29 build); line.csv's
    own columns are checked against the RES file to the cent (q19_a2.py writes book = book_mtm, line = book + 0.264 x
    RES); L = B + 0.264 x RES; parity ROC 120.82 / Sortino 3.916."""
    path = path or RES_CSV
    with open(path, "rb") as f:
        data = f.read()
    sha = hashlib.sha256(data).hexdigest()
    if sha != RES_SHA:
        raise SystemExit("RES file sha256 %s is not the pinned %s - abort" % (sha, RES_SHA))
    df = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    dates = pd.DatetimeIndex(pd.to_datetime(df["date"].astype(str).str.strip().str[:10], format="%Y-%m-%d"))
    bdays = pd.DatetimeIndex(B.index)
    if dates.max() > CUT:
        raise SystemExit("RES file has a row after 2025-06-29 - abort")
    if len(dates) != len(bdays) or not (dates == bdays).all():
        raise SystemExit("RES file dates are not #463's WF index row for row - abort")
    bm = df["book_mtm"].to_numpy(float)
    dmax = float(np.abs(bm - B.to_numpy(float)).max())
    if dmax > 1.0:
        raise SystemExit("RES file book_mtm (book build to 2026-06-30) differs from #463 (book463_valued_daily to "
                         "2025-06-29) by $%.2f, over the house $1 - abort" % dmax)
    RES = pd.Series(df["RES"].to_numpy(float), index=bdays)
    L = pd.Series(B.to_numpy(float) + RES_W * RES.to_numpy(), index=bdays)
    ln = pd.read_csv(line_path or LINE_CSV)
    ld = pd.DatetimeIndex(pd.to_datetime(ln["date"]))
    if len(ld) != len(bdays) or not (ld == bdays).all():
        raise SystemExit("line.csv dates are not #463's WF index - abort")
    if float(np.abs(ln["book"].to_numpy(float) - bm).max()) > 0.01:
        raise SystemExit("line.csv book is not the RES file's book_mtm within $0.01 - abort")
    if float(np.abs(ln["line"].to_numpy(float) - (bm + RES_W * RES.to_numpy())).max()) > 0.01:
        raise SystemExit("line.csv line is not book_mtm + 0.264 x RES within $0.01 - abort")
    st = HH.own(L.to_numpy(), bdays)
    if not (abs(st["roc"] - LINE_FACTS[0]) < 0.05 and abs(st["sort"] - LINE_FACTS[1]) < 0.005):
        raise SystemExit("L PARITY FAILED: ROC %.3f Sortino %.4f - abort" % (st["roc"], st["sort"]))
    line = pd.Series(ln["line"].to_numpy(float), index=bdays)
    return L, RES, line, st, dmax


def index_checks(B):
    bdays = pd.DatetimeIndex(B.index)
    if len(bdays) != N_INDEX:
        raise SystemExit("#463 WF index has %d rows, not %d - abort" % (len(bdays), N_INDEX))
    sund = int((bdays.dayofweek == 6).sum())
    if sund != N_SUNDAY:
        raise SystemExit("#463 WF index has %d UTC-Sunday rows, not %d - abort" % (sund, N_SUNDAY))
    years = (bdays[-1] - bdays[0]).days / 365.25
    if abs(years - 8.994) > 5e-4:
        raise SystemExit("years %.4f is not 8.994 - abort" % years)
    p0, p1 = HH.worst_window(B)
    if pd.Timestamp(p0) != WORST[0] or pd.Timestamp(p1) != WORST[1]:
        raise SystemExit("#463's worst WF drawdown is %s .. %s, not 2020-03-02 .. 2020-03-27 - abort" % (p0, p1))
    return bdays, years, sund


def book_leg_dailies(bdays, B):
    """#463's four legs valued daily, exactly the book463_valued_daily loop (api/book_shadow.py lines 58-85), per leg;
    their sum must be B on every WF row (within $0.01)."""
    from augur_engine import book
    from api.book_shadow import BOOK463_LEGS
    out = {}
    for leg in BOOK463_LEGS:
        tr, inf = book._leg_trades(dict(leg), D0, CUT_S)
        if inf.get("source") != leg["source"]:
            raise SystemExit("%s ran on source %r, pinned %r - abort" % (leg["strategy"], inf.get("source"), leg["source"]))
        if inf.get("mtm_error"):
            raise SystemExit("%s daily valuation failed: %s - abort" % (leg["strategy"], inf["mtm_error"]))
        marks = inf.pop("_mtm_day", None) or tr
        d, v = book._daily(marks)
        s = pd.Series(v, index=pd.to_datetime(d)).groupby(level=0).sum() if len(d) else pd.Series(dtype=float)
        key = next(k for k in ("ORB", "ENGUQ", "TTM", "NOISE") if leg["strategy"].startswith(k))
        out[key] = s.reindex(bdays, fill_value=0.0)
    tot = sum(out.values())
    gap = float(np.abs(tot.to_numpy() - B.to_numpy()).max())
    if gap > 0.01:
        raise SystemExit("per-leg dailies do not sum to #463 (max gap $%.4f) - abort" % gap)
    return out


# ================================================================== the #304 band, re-typed (section 3.2)
def frozen():
    P = dict(strategy("NOISE_1_8_CT304.py")._FROZEN)
    if not (P["lookback"] == 40 and P["band_mult_long"] == 0.75 and P["band_mult_short"] == 1.5):
        raise SystemExit("_FROZEN is not lookback 40 / 0.75 / 1.5 - abort")
    return P


def twin_params(P, lookback):
    return dict(P, lookback=int(lookback), band_mult_long=1.0, band_mult_short=1.0)


def build_bands(A, P, NZ=None):
    """Per bar: si, k, stamp minutes hm; per session: bounds, m, prev_close, has_1555, warm; flat UB / LB / V (NaN in
    warm-up), vol_pct and dt_pos from NOISE_1_0's own helpers. Float operations in the engine's exact order (lines
    570-581, 600-606, 777). Warm-up and roll sessions still feed sigma and prev_close."""
    NZ = NZ or noise_mod()
    if P.get("skip_holidays", False):
        raise SystemExit("skip_holidays must be off (it is in _FROZEN) - abort")
    o, h = np.asarray(A["open"], float), np.asarray(A["high"], float)
    lo, c = np.asarray(A["low"], float), np.asarray(A["close"], float)
    v = np.asarray(A["volume"], float)
    did = np.asarray(A["day_id"])
    n = len(c)
    ts = naive(A["index"])
    hm = np.asarray(ts.hour * 60 + ts.minute, int)
    bounds = NZ._session_bounds(did, n)
    lb, bml, bms = int(P["lookback"]), float(P["band_mult_long"]), float(P["band_mult_short"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        sigma = NZ._sigma_matrix(o, c, bounds, lb)
        # _vol_percentile / _daytype_pos (beyond section 3.2's two helpers) feed ONLY the #304-eligible crosswalk and the
        # QUIET sub-split, never a band, label or trade; eligible parity checks them on every session (AMENDMENT 1 note)
        vol_pct = NZ._vol_percentile(h, lo, c, bounds)
        dt_pos = NZ._daytype_pos(h, lo, c, bounds)
    ns = len(bounds)
    UB, LB, V = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    si_a, k_a = np.empty(n, int), np.empty(n, int)
    a_a, b_a = np.array([a for a, _ in bounds], int), np.array([b for _, b in bounds], int)
    prev_close = np.full(ns, np.nan)
    warm = np.zeros(ns, bool)
    has1555 = np.zeros(ns, bool)
    pc = None
    for si, (a, b) in enumerate(bounds):
        m = b - a
        si_a[a:b] = si
        k_a[a:b] = np.arange(m)
        has1555[si] = bool((hm[a:b] == LAST_HM).any())
        if pc is not None:
            prev_close[si] = pc
        if pc is None or si < lb:
            warm[si] = True
            pc = c[b - 1]
            continue
        so, sh, sl, sc, sv = o[a:b], h[a:b], lo[a:b], c[a:b], v[a:b]
        ref_hi = max(so[0], pc)
        ref_lo = min(so[0], pc)
        sigma_row = sigma[si, :]
        with np.errstate(invalid="ignore"):
            UB[a:b] = ref_hi * (1.0 + bml * sigma_row[:m])
            LB[a:b] = ref_lo * (1.0 - bms * sigma_row[:m])
        typical = (sh + sl + sc) / 3.0
        cum_tpv = np.cumsum(typical * sv)
        cum_v = np.cumsum(sv)
        with np.errstate(invalid="ignore", divide="ignore"):
            V[a:b] = cum_tpv / cum_v
        pc = sc[-1]
    dates = ts[a_a].normalize()
    S = SimpleNamespace(o=o, h=h, l=lo, c=c, v=v, did=did, n=n, ts=ts, hm=hm, si=si_a, k=k_a, bounds=bounds, ns=ns,
                        a=a_a, b=b_a, m=b_a - a_a, dates=pd.DatetimeIndex(dates), prev_close=prev_close, warm=warm,
                        has1555=has1555, last_hm=hm[b_a - 1], first_hm=hm[a_a], UB=UB, LB=LB, V=V, vol_pct=vol_pct,
                        dt_pos=dt_pos, P=dict(P), lookback=lb)
    S.x, S.E, S.side, S.D = stretch(c, V, UB, LB)
    return S


def raw_break(S):
    """brk[i]: k >= 1 and C > UB or C < LB (strict; NaN never breaks); brk_side +1 above UB, -1 below LB."""
    with np.errstate(invalid="ignore"):
        up = (S.k >= 1) & (S.c > S.UB)
        dn = (S.k >= 1) & (S.c < S.LB)
    return up | dn, np.where(up, 1, np.where(dn, -1, 0))


def roll_sessions(S, switches):
    """Per session: the first session whose first bar is stamped after a switch_et. Also [(switch, offset, date)]."""
    roll = np.zeros(S.ns, bool)
    first = S.ts[S.a]
    notes = []
    for r in switches.itertuples():
        j = int(np.searchsorted(first.values, np.datetime64(pd.Timestamp(r.switch_et)), side="right"))
        if j < S.ns:
            roll[j] = True
            notes.append((pd.Timestamp(r.switch_et), float(r.offset_pts), S.dates[j], j))
    return roll, notes


def trading_mask(S, roll):
    """Trading sessions = has a 15:55 bar, minus warm-up and roll sessions; their last bar is 15:55 (asserted)."""
    t = S.has1555 & ~S.warm & ~roll
    if (S.last_hm[t] != LAST_HM).any():
        raise SystemExit("a trading session's last bar is not 15:55 - abort")
    return t


def classify(S, mask, brk):
    """BALANCE: a session in `mask` with no raw break on any bar with k >= 1 and stamp <= 11:55 (bars closed by noon)."""
    early = brk & (S.hm <= NOON_LAST)
    cnt = np.bincount(S.si[early], minlength=S.ns)
    return np.asarray(mask, bool) & (cnt == 0)


def eligible_first_break(S, brk_side, P):
    """#304's STEP D on a flat session: the first k in 1 .. m-2 with a raw break that its gates do not block (vol skip at
    the 95th percentile blocks the session; skip_bot_short blocks shorts when dt_pos <= 0.2). Absolute index or -1."""
    if not (int(P.get("confirm_bars", 1)) == 1 and P.get("window", "all_day") == "all_day"
            and P.get("side", "Both") == "Both"):
        raise SystemExit("eligible_first_break mirrors confirm_bars 1 / all_day / Both only - abort")
    vsp = float(P.get("vol_skip_pct", 0.0))
    mode = P.get("daytype_mode", "off")
    dlo = float(P.get("daytype_lo", 0.2))
    if mode not in ("off", "skip_bot_short"):
        raise SystemExit("daytype_mode %r not mirrored - abort" % mode)
    out = np.full(S.ns, -1, int)
    for si in range(S.ns):
        if S.warm[si]:
            continue
        if vsp > 0 and np.isfinite(S.vol_pct[si]) and S.vol_pct[si] >= vsp:
            continue
        bshort = mode == "skip_bot_short" and np.isfinite(S.dt_pos[si]) and S.dt_pos[si] <= dlo
        a, m = int(S.a[si]), int(S.m[si])
        seg = brk_side[a + 1:a + m - 1]
        ok = (seg == 1) | ((seg == -1) & (not bshort))
        j = np.flatnonzero(ok)
        if len(j):
            out[si] = a + 1 + int(j[0])
    return out


def run_304(A, P, S, NZ=None):
    """NOISE_1_0.run_backtest with _FROZEN (or a twin's settings), trades + decision records."""
    NZ = NZ or noise_mod()
    r = NZ.run_backtest(A["open"], A["high"], A["low"], A["close"], volumes=A["volume"], day_id=A["day_id"],
                        return_trades=True, return_decisions=True, **P)
    if not r or not r.get("trades"):
        raise SystemExit("NOISE_1_0 returned no trades - abort")
    tr, dec = r["trades"], r.get("decisions")
    if dec is None or len(dec) != len(tr):
        raise SystemExit("NOISE_1_0 decision records missing or misaligned (%s vs %d) - abort"
                         % (None if dec is None else len(dec), len(tr)))
    e0 = np.array([int(t[0]) for t in tr])
    e1 = np.array([int(t[1]) for t in tr])
    df = pd.DataFrame({"entry_idx": e0, "exit_idx": e1, "raw_pts": [float(t[2]) for t in tr],
                       "side": [int(np.sign(t[3])) for t in tr], "entry_px": [float(t[4]) for t in tr]})
    df["signal_idx"] = e0 - 1
    df["si"] = S.si[e0]
    df["entry_stamp"] = S.ts[e0]
    df["exit_stamp"] = S.ts[e1]
    df["signal_date"] = S.ts[e0 - 1].normalize()
    df["exit_rule"] = [d["exit"]["rule"] for d in dec]
    df["dec"] = dec
    df["unit_usd"] = np.nan
    return df


def exit_class(rule):
    if rule in ("close<vwap", "close>vwap"):
        return "VWAP"
    if rule in ("open<stop", "low<=stop", "open>stop", "high>=stop"):
        return "STOP"
    if rule == "session_last_bar":
        return "FLAT"
    raise SystemExit("unknown #304 exit rule %r - abort" % rule)


def _nn(v):
    return np.nan if v is None else float(v)


def trade_parity(tr304, f, wf=True):
    """(a) #304's trades with signal dates in WF equal the crown file's WF rows (entry, exit, side) in order."""
    t = tr304[(tr304.signal_date >= WF0) & (tr304.signal_date <= WF1)] if wf else tr304
    fd = f["entry"].dt.normalize()
    q = (f[(fd >= WF0) & (fd <= WF1)] if wf else f).sort_values(["entry", "exit"], kind="stable")
    if len(t) != len(q):
        raise SystemExit("#304 parity: %d engine trades vs %d file rows in WF - abort" % (len(t), len(q)))
    for i, (r, s) in enumerate(zip(t.itertuples(), q.itertuples())):
        if r.entry_stamp != s.entry or r.exit_stamp != s.exit or r.side != s.side:
            raise SystemExit("#304 parity: trade %d differs - engine %s .. %s side %d vs file %s .. %s side %d - abort" % (
                i, r.entry_stamp, r.exit_stamp, r.side, s.entry, s.exit, s.side))
    return t.index, q


def band_parity(S, tr, rows=None, tol=1e-9):
    """(b) at every entry-decision and exit-decision bar of `rows`, the driver's UB / LB / V equal the record's
    upper / lower / vwap within tol (None <-> NaN). -> (bars checked, max |difference|)."""
    rows = tr if rows is None else rows
    nb, mx = 0, 0.0
    for r in rows.itertuples():
        for side in ("entry", "exit"):
            rec = r.dec[side]
            i = int(rec["bar"])
            for key, arr in (("upper", S.UB), ("lower", S.LB), ("vwap", S.V)):
                a, b = _nn(rec[key]), float(arr[i])
                if np.isnan(a) != np.isnan(b):
                    raise SystemExit("band parity: %s at bar %d (%s, %s) is %s in the record and %s in the driver - abort"
                                     % (key, i, S.ts[i], side, a, b))
                if not np.isnan(a):
                    d = abs(a - b)
                    mx = max(mx, d)
                    if d > tol:
                        raise SystemExit("band parity: %s at bar %d (%s, %s) differs by %.3g - abort" % (key, i, S.ts[i], side, d))
            nb += 1
    return nb, mx


def eligible_parity(S, elig, tr):
    """(c) on every loaded session, eligible_first_break + 1 = #304's first entry; no eligible break = no trade."""
    first = tr.groupby("si")["entry_idx"].min()
    for si in range(S.ns):
        e = int(elig[si])
        t = int(first.get(si, -1))
        if (e < 0 and t >= 0) or (e >= 0 and t != e + 1):
            raise SystemExit("eligible-break parity: session %s (si %d) eligible break %d, #304 first entry %d - abort"
                             % (S.dates[si].date(), si, e, t))
    return S.ns


def parity_304(ctx, f422=None):
    """All three parity asserts; the WF trades get the file's unit $ when the file is given."""
    info = {}
    wfmask = (ctx.tr304.signal_date >= WF0) & (ctx.tr304.signal_date <= WF1)
    if f422 is not None:
        ix, q = trade_parity(ctx.tr304, f422)
        if len(ix) != N_PARITY:
            raise SystemExit("#304 parity: %d WF trades, not %d - abort" % (len(ix), N_PARITY))
        ctx.tr304.loc[ix, "unit_usd"] = q["unit_usd"].to_numpy()
        info["matched"] = len(ix)
    else:
        w = ctx.tr304[wfmask]
        ctx.tr304.loc[w.index, "unit_usd"] = ctx.mult * w["raw_pts"] - ctx.mult * ctx.cost
        info["matched"] = None
    info["wf_trades"] = int(wfmask.sum())
    info["bars"], info["max_diff"] = band_parity(ctx.S, ctx.tr304, ctx.tr304[wfmask])
    info["sessions"] = eligible_parity(ctx.S, ctx.elig, ctx.tr304)
    return info


def prepare(inst, P):
    A = load_master(inst)
    S = build_bands(A, P)
    brk, brk_side = raw_break(S)
    sw = load_rolls(inst)
    nwf = int(((sw["switch_et"].dt.normalize() >= WF0) & (sw["switch_et"].dt.normalize() <= WF1)).sum())
    if nwf != N_WF_SWITCHES:
        raise SystemExit("%s: %d roll switches in WF, not %d - abort" % (inst, nwf, N_WF_SWITCHES))
    roll, notes = roll_sessions(S, sw)
    trading = trading_mask(S, roll)
    balance = classify(S, trading, brk)
    lead = np.arange(S.ns) < S.lookback                                 # section 3.1 warm-up, asserted at run time
    if S.lookback != 40 or not (S.warm == lead).all() or (trading & lead).any() or (balance & lead).any():
        raise SystemExit("%s: warm-up is not exactly the first 40 sessions, or one is trading / BALANCE - abort" % inst)
    elig = eligible_first_break(S, brk_side, P)
    tr304 = run_304(A, P, S)
    return SimpleNamespace(inst=inst, A=A, S=S, P=P, brk=brk, brk_side=brk_side, switches=sw, roll=roll, roll_notes=notes,
                           trading=trading, balance=balance, elig=elig, tr304=tr304, n_wf_switches=nwf, **INST[inst])


def assert_balance_on_index(ctx, bdays):
    """Section 3.8: every WF BALANCE session date (traded or not) is on #463's WF day index, before any count prints."""
    d = pd.DatetimeIndex(ctx.S.dates[ctx.balance])
    d = d[(d >= WF0) & (d <= WF1)]
    miss = ~d.isin(pd.DatetimeIndex(bdays))
    if miss.any():
        raise SystemExit("%s: WF BALANCE session dates not on #463's day index: %s - abort" % (
            ctx.inst, [str(x.date()) for x in d[miss][:5]]))
    return len(d)


# ================================================================== signals and the trade (sections 3.6, 3.7)
def stretch(C, V, UB, LB):
    """x, E, side, D. Short when C > V (E = UB, x = (C-V)/(UB-V)); long when C < V (E = LB, x = (V-C)/(V-LB));
    no signal (x NaN, side 0) when C == V, the denominator is <= 0 or any input is NaN."""
    C, V, UB, LB = (np.atleast_1d(np.asarray(z, float)) for z in (C, V, UB, LB))
    x, E = np.full(C.shape, np.nan), np.full(C.shape, np.nan)
    side = np.zeros(C.shape, int)
    with np.errstate(invalid="ignore", divide="ignore"):
        fin = np.isfinite(C) & np.isfinite(V) & np.isfinite(UB) & np.isfinite(LB)
        ds, dl = UB - V, V - LB
        okS = fin & (C > V) & (ds > 0)
        okL = fin & (C < V) & (dl > 0)
        x[okS] = (C[okS] - V[okS]) / ds[okS]
        x[okL] = (V[okL] - C[okL]) / dl[okL]
        side[okS], side[okL] = -1, 1
        E[okS], E[okL] = UB[okS], LB[okL]
        D = np.abs(E - V)
    return x, E, side, D


def first_signals(S, mask, brk, thr, sig_first=SIG_FIRST, sig_last=SIG_LAST):
    """Per session in `mask`: the first bar with stamp in [sig_first, sig_last], no raw break on bars 1 .. k, and
    x >= thr -> (absolute index or -1, side). Exit-independent (the first signal is always taken flat)."""
    cs = np.cumsum(brk.astype(int))
    start = np.where(S.a > 0, cs[np.maximum(S.a - 1, 0)], 0)
    cb = cs - start[S.si]
    with np.errstate(invalid="ignore"):
        ok = (np.asarray(mask, bool)[S.si] & (S.hm >= sig_first) & (S.hm <= sig_last) & (cb == 0)
              & (S.x >= thr) & (S.k <= S.m[S.si] - 2))
    idx, sd = np.full(S.ns, -1, int), np.zeros(S.ns, int)
    w = np.flatnonzero(ok)
    if len(w):
        u, f = np.unique(S.si[w], return_index=True)
        idx[u] = w[f]
        sd[u] = S.side[w[f]]
    return idx, sd


def sim_session(o, c, UB, LB, V, hm, is_balance, thr, sig_first=SIG_FIRST, sig_last=SIG_LAST):
    """One session, positional bars k = 0 .. m-1 -> trades (dicts, session-relative). Per bar k:
    A. fill a pending exit at o[k], then a pending entry at o[k];
    B. in a position (from the fill bar's close on): a raw break on the entry's edge -> STOP; on the opposite edge ->
       TARGET (opp_band) if C is at or through V, else OPP-BREAK; else C at or through V -> TARGET. A stop or target at
       the last bar exits at its close; otherwise it fills at the next open. FLAT at the last bar's close;
    C. any raw break closes the day for new entries;
    D. a signal at C[k] (fill o[k+1]) if: BALANCE, the day still open, flat with no exit pending, stamp in
       [sig_first, sig_last], x >= thr, and k is not the last bar."""
    o, c, UB, LB, V = (np.asarray(z, float) for z in (o, c, UB, LB, V))
    hm = np.asarray(hm, int)
    m = len(c)
    x, E, sd, D = stretch(c, V, UB, LB)
    kk = np.arange(m)
    with np.errstate(invalid="ignore"):
        up = (kk >= 1) & (c > UB)
        dn = (kk >= 1) & (c < LB)
    trades = []
    pos, cur, pend_entry, pend_exit, closed, order = 0, None, None, None, False, 0

    def _close(k, px, ex_hm, held_end_hm, reason, opp, close_exit):
        cur.update(exit_k=k, exit=float(px), exit_hm=int(ex_hm), held_end_hm=int(held_end_hm), reason=reason,
                   opp_band=bool(opp), close_exit=bool(close_exit), gross=float(cur["side"] * (px - cur["entry"])),
                   exit_min=int(held_end_hm if close_exit else ex_hm) - cur["fill_hm"])
        trades.append(cur)

    for k in range(m):
        last = k == m - 1
        if pend_exit is not None:                                              # A
            _close(k, o[k], hm[k], hm[k], pend_exit[0], pend_exit[1], False)
            pos, cur, pend_exit = 0, None, None
        if pend_entry is not None and pos == 0:
            s = pend_entry
            order += 1
            e = float(o[k])
            cur = dict(sig_k=s, fill_k=k, sig_hm=int(hm[s]), fill_hm=int(hm[k]), side=int(sd[s]), entry=e,
                       E=float(E[s]), V_sig=float(V[s]), D=float(D[s]), x=float(x[s]), R0=abs(float(E[s]) - e),
                       beyond=bool(e >= E[s]) if sd[s] < 0 else bool(e <= E[s]), order=order, marks=[])
            pos, pend_entry = int(sd[s]), None
        if pos != 0:                                                           # B
            cur["marks"].append((int(hm[k]) + 5 - cur["fill_hm"], float(pos * (c[k] - cur["entry"]))))
            reason, opp = None, False
            through = (pos < 0 and c[k] <= V[k]) or (pos > 0 and c[k] >= V[k])      # NaN V -> False
            if up[k] or dn[k]:
                if (pos < 0 and up[k]) or (pos > 0 and dn[k]):
                    reason = STOP
                elif through:
                    reason, opp = TARGET, True
                else:
                    reason = OPP
            elif through:
                reason = TARGET
            if reason is not None:
                if last:
                    _close(k, c[k], hm[k], hm[k] + 5, reason, opp, True)
                    pos, cur = 0, None
                else:
                    pend_exit = (reason, opp)
            elif last:
                _close(k, c[k], hm[k], hm[k] + 5, FLAT, False, True)
                pos, cur = 0, None
        if up[k] or dn[k]:                                                     # C
            closed = True
        if (is_balance and not closed and pos == 0 and pend_exit is None and pend_entry is None and not last
                and sig_first <= hm[k] <= sig_last and x[k] >= thr):            # D (x NaN -> False)
            pend_entry = k
    return trades


TRADE_COLS = ["session", "signal_stamp", "fill_stamp", "exit_stamp", "side", "entry", "exit", "E", "V", "D", "x", "R0",
              "exit_reason", "gross_pts", "net_usd"]
EXTRA_COLS = ["stretch", "held_end", "order", "opp_band", "beyond", "close_exit", "stress_usd", "si", "sig_i", "fill_i",
              "exit_i", "sig_hm", "fill_hm", "exit_hm", "exit_min", "marks"]


def simulate(S, balance, thr, cost, mult, stress, sig_last=SIG_LAST):
    """All BALANCE sessions (WF and EARLY tagged) -> trades. Forbidden in --counts."""
    if MODE == "counts":
        raise RuntimeError("simulate() is forbidden in --counts (no BALANCE exit runs before --power)")
    rows = []
    for si in np.flatnonzero(balance):
        a, b = int(S.a[si]), int(S.b[si])
        for t in sim_session(S.o[a:b], S.c[a:b], S.UB[a:b], S.LB[a:b], S.V[a:b], S.hm[a:b], True, thr,
                             SIG_FIRST, sig_last):
            ex = S.ts[a + t["exit_k"]]
            rows.append({"session": S.dates[si], "signal_stamp": S.ts[a + t["sig_k"]], "fill_stamp": S.ts[a + t["fill_k"]],
                         "exit_stamp": ex, "held_end": ex + pd.Timedelta(minutes=5) if t["close_exit"] else ex,
                         "side": t["side"], "entry": t["entry"], "exit": t["exit"], "E": t["E"], "V": t["V_sig"],
                         "D": t["D"], "x": t["x"], "R0": t["R0"], "exit_reason": t["reason"], "gross_pts": t["gross"],
                         "order": t["order"], "opp_band": t["opp_band"], "beyond": t["beyond"],
                         "close_exit": t["close_exit"], "si": int(si), "sig_i": a + t["sig_k"], "fill_i": a + t["fill_k"],
                         "exit_i": a + t["exit_k"], "sig_hm": t["sig_hm"], "fill_hm": t["fill_hm"],
                         "exit_hm": t["exit_hm"], "exit_min": t["exit_min"], "marks": t["marks"]})
    df = pd.DataFrame(rows, columns=[c for c in TRADE_COLS + EXTRA_COLS if c not in ("net_usd", "stress_usd", "stretch")])
    g = df["gross_pts"].astype(float)
    df["net_usd"] = mult * g - mult * cost
    df["stress_usd"] = mult * g - mult * stress
    sess = pd.DatetimeIndex(df["session"]) if len(df) else pd.DatetimeIndex([])
    df["stretch"] = np.where((sess >= WF0) & (sess <= WF1), "WF", np.where(sess < WF0, "EARLY", "OUT"))
    if (df["stretch"] == "OUT").any():
        raise SystemExit("a BALANCE trade after 2025-06-29 - abort")
    return df


def daily(tr, idx, col="net_usd"):
    """Net $ by session date on idx (0 elsewhere); every session date must be on idx."""
    idx = pd.DatetimeIndex(idx)
    if len(tr) == 0:
        return pd.Series(0.0, index=idx)
    s = tr.groupby("session")[col].sum()
    s.index = pd.DatetimeIndex(s.index)
    miss = ~s.index.isin(idx)
    if miss.any():
        raise SystemExit("BALANCE session dates not on the day index: %s - abort" % list(s.index[miss][:5]))
    return s.reindex(idx, fill_value=0.0)


# ================================================================== statistics (section 8)
def own(x, dates):
    st = HH.own(np.asarray(x, float), pd.DatetimeIndex(dates)) if len(x) >= 2 else None
    return st or {"net": float(np.sum(x)), "roc": float("nan"), "sort": float("nan"), "max_dd": float("nan")}


def t_stat_vals(v):
    v = np.asarray(v, float)
    if len(v) < 2:
        return float("nan")
    sd = float(v.std(ddof=1))
    return float(v.mean() / (sd / np.sqrt(len(v)))) if sd > 0 else float("nan")


def t_stat(tr):
    """t over the session nets of the sessions with at least one trade (ddof 1)."""
    return t_stat_vals(tr.groupby("session")["net_usd"].sum().to_numpy()) if len(tr) else float("nan")


def r_sum(x, inR):
    return float(np.asarray(x, float)[np.asarray(inR, bool)].sum())


def r_sum_ex3(x, inR):
    v = np.sort(np.asarray(x, float)[np.asarray(inR, bool)])
    return float(v[:-3].sum()) if len(v) > 3 else 0.0


def pf(net):
    net = np.asarray(net, float)
    neg = -net[net < 0].sum()
    return float(net[net > 0].sum() / neg) if neg > 0 else (float("inf") if (net > 0).any() else float("nan"))


def july_june(x, bdays, years=range(2016, 2025)):
    x, b = np.asarray(x, float), pd.DatetimeIndex(bdays)
    return [float(x[(b >= pd.Timestamp(y, 7, 1)) & (b < pd.Timestamp(y + 1, 7, 1))].sum()) for y in years]


def ex_window(x, bdays, lo, hi):
    b = pd.DatetimeIndex(bdays)
    return float(np.asarray(x, float)[~((b >= lo) & (b <= hi))].sum())


def early_index(S, trading):
    return pd.DatetimeIndex(S.dates[np.asarray(trading, bool) & (S.dates <= EARLY1)])


def summarize(tr, bdays, inR, years, eidx):
    wf, early = tr[tr.stretch == "WF"], tr[tr.stretch == "EARLY"]
    x = daily(wf, bdays).to_numpy()
    st = own(x, bdays)
    xe = daily(early, eidx).to_numpy()
    n = len(wf)
    return SimpleNamespace(
        tr=tr, wf=wf, early=early, x=x, st=st, n=n, net=float(x.sum()), pf=pf(wf["net_usd"]), t=t_stat(wf),
        rs=r_sum(x, inR), rs3=r_sum_ex3(x, inR), gross=float(wf["gross_pts"].mean()) if n else float("nan"),
        yrs=july_june(x, bdays), nyr=[int(v) for v in july_june(daily(wf.assign(one=1.0), bdays, "one"), bdays)],
        stress=float(wf["stress_usd"].sum()), early_net=float(early["net_usd"].sum()), early_n=len(early),
        early_st=own(xe, eidx), best_day=float(x.max()) if len(x) else float("nan"),
        best_trade=float(wf["net_usd"].max()) if n else float("nan"), x11=ex_window(x, bdays, *X20),
        x22=float(x[pd.DatetimeIndex(bdays).year != 2022].sum()), years=years)


def bars13(c, other_net, p95):
    """The 13 Stage A bars (section 8) -> [(no, label, ok, value)]."""
    yp = sum(v > 0 for v in c.yrs)
    nb, nt = c.net - c.best_day, c.net - c.best_trade
    return [
        (1, "own WF ROC@$30k >= 5", c.st["roc"] >= 5, f2(c.st["roc"])),
        (2, "R-sum (762 R days) > 0", c.rs > 0, fm(c.rs)),
        (3, "R-sum without its 3 best R days > 0", c.rs3 > 0, fm(c.rs3)),
        (4, "R-sum > family null p95 of max R-sum (%s)" % fm(p95["rsum"]), c.rs > p95["rsum"], fm(c.rs)),
        (5, "PF >= 1.05", c.pf >= 1.05, f2(c.pf, 3)),
        (6, ">= 100 WF trades and >= 50 a year", c.n >= 100 and c.n / c.years >= 50, "%d (%.1f/yr)" % (c.n, c.n / c.years)),
        (7, ">= 6 of 9 July-June years net > 0", yp >= 6, "%d/9" % yp),
        (8, "t >= 2.0 and > family null p95 of max t (%s)" % f2(p95["t"]), c.t >= 2.0 and c.t > p95["t"], f2(c.t)),
        (9, "net > 0 at stress cost", c.stress > 0, fm(c.stress)),
        (10, "net > 0 without best day and without best trade", nb > 0 and nt > 0, "%s / %s" % (fm(nb), fm(nt))),
        (11, "net > 0 without 2020-02-15 .. 2020-04-30", c.x11 > 0, fm(c.x11)),
        (12, "EARLY net > 0 (2010-06-07 .. 2016-06-30)", c.early_net > 0, fm(c.early_net)),
        (13, "neighbour cell WF net > 0", other_net > 0, fm(other_net)),
    ]


# ================================================================== family null and power (sections 5, 6)
def power_coin(n, seed=SEED_NULL):
    return np.random.default_rng(seed).choice([-1, 1], size=n)


def null_coins(sizes, draws=DRAWS, seed=SEED_NULL):
    """One rng; for draw d = 1 .. draws, the cells in family order (B1 then B2): rng.choice([-1, 1], size=n_cell)."""
    rng = np.random.default_rng(seed)
    for d in range(draws):
        yield d, [rng.choice([-1, 1], size=n) for n in sizes]


def family_null(cells, nd, inR, years, cost_usd, draws=DRAWS, seed=SEED_NULL):
    """cells: [(name, gross_usd, day_idx)] in family order. Trade net = coin x gross $ - cost; statistics per draw and
    cell: own ROC@$30k (PL.roc30), t over trade days, R-sum; family max per draw; p95 = np.percentile(..., 95)."""
    inR = np.asarray(inR, bool)
    X = {nm: np.zeros((draws, nd)) for nm, _, _ in cells}
    T = {nm: np.full(draws, np.nan) for nm, _, _ in cells}
    RS = {nm: np.zeros(draws) for nm, _, _ in cells}
    tdays = {nm: np.unique(di) for nm, _, di in cells}
    for d, coins in null_coins([len(g) for _, g, _ in cells], draws, seed):
        for (nm, g, di), cn in zip(cells, coins):
            x = np.bincount(di, weights=cn * g - cost_usd, minlength=nd) if len(g) else np.zeros(nd)
            X[nm][d] = x
            T[nm][d] = t_stat_vals(x[tdays[nm]])
            RS[nm][d] = x[inR].sum()
    ROC = {nm: PL.roc30(X[nm], years) for nm in X}
    stack = lambda D: np.nan_to_num(np.vstack([D[nm] for nm, _, _ in cells]), nan=-1e18)
    mx = {"roc": stack(ROC).max(axis=0), "t": stack(T).max(axis=0), "rsum": stack(RS).max(axis=0)}
    p95 = {k: float(np.percentile(v, 95)) for k, v in mx.items()}
    b1 = cells[0][0]
    maxima = pd.DataFrame({"draw": np.arange(1, draws + 1), "max_roc": mx["roc"], "max_t": mx["t"], "max_rsum": mx["rsum"]})
    return {"p95": p95, "sd_rsum_B1": float(np.std(RS[b1], ddof=1)), "maxima": maxima}


def power(wf, B, L, bdays, years, mult=20.0, cost=0.533):
    """Coin-flip leg on B1's real WF schedule: net = coin x (exit - entry) x 20 - 10.66; three power lines."""
    coin = power_coin(len(wf))
    tc = wf.assign(net_usd=coin * (wf["exit"].to_numpy(float) - wf["entry"].to_numpy(float)) * mult - mult * cost)
    x = daily(tc, bdays).to_numpy()
    xv, c = HH.vol_scaled(x, B, bdays)
    xd, dd = HH.scaled(x)
    tw = 30000.0 / dd if dd > 0 else float("nan")
    Bv, Lv = B.to_numpy(float), L.to_numpy(float)
    lines = {"book_c": PL.power_line(Bv + xv, Bv, years), "book_twin": PL.power_line(Bv + xd, Bv, years),
             "line_c": PL.power_line(Lv + xv, Lv, years)}
    return {"n": int(len(wf)), "c": float(c), "twin": float(tw), "lines": lines}


def print_power(pw, nl):
    lab = {"book_c": "#463 + c x coin vs #463", "book_twin": "#463 + $30k-twin x coin vs #463", "line_c": "L + c x coin vs L"}
    size = {"book_c": pw["c"], "book_twin": pw["twin"], "line_c": pw["c"]}
    print("POWER LINES (coin-flip sides on B1's real WF schedule, %d trades; seed %d; block %d, %d draws, seed %d)" % (
        pw["n"], SEED_NULL, BLOCK, DRAWS, SEED_BOOT))
    for k in ("book_c", "book_twin", "line_c"):
        r = pw["lines"][k]
        print("  %-34s x%.3f NQ: SD of the ROC@$30k lead %.2f; 5%% line %.2f; 80%% line %.2f" % (
            lab[k], size[k], r["sd"], r["line_5pct"], r["line_80pct"]))
    print("FAMILY NULL (B1 + B2, %d draws, one rng seed %d, B1 then B2 per draw; trade net = coin x gross $ - cost)" % (
        DRAWS, SEED_NULL))
    print("  p95 of the family max: t %.3f; R-sum %s; own ROC@$30k %.2f (report). Null SD of B1's R-sum %s" % (
        nl["p95"]["t"], fm(nl["p95"]["rsum"]), nl["p95"]["roc"], fm(nl["sd_rsum_B1"])))
    print("  (the power coin equals the null's first B1 draw: same seed, same first call - documented, harmless)")


def book_add(x, B, L, bdays, years):
    """REPORT (house line #45): #463 + s x and L + s x at c, 0.5c, 2c and the $30k twin; paired bootstrap p5 of the lead.
    Judged at c on the incremental L row: ROC >= 126.86, Sortino >= 3.916, p5 > 0 -> forward BOOK shadow line."""
    _require_run("book_add")
    x = np.asarray(x, float)
    _, c = HH.vol_scaled(x, B, bdays)
    _, dd = HH.scaled(x)
    tw = 30000.0 / dd if dd > 0 else float("nan")
    idx = PL.stationary_indices(len(x), DRAWS, BLOCK, np.random.default_rng(SEED_BOOT))
    rows, shadow = [], False
    for lab, s in (("c", c), ("0.5c", 0.5 * c), ("2c", 2 * c), ("$30k twin", tw)):
        for base_name, base in (("#463", B.to_numpy(float)), ("L", L.to_numpy(float))):
            if not np.isfinite(s):
                continue
            cand = base + s * x
            st = own(cand, bdays)
            lead = PL.roc30(cand[idx], years) - PL.roc30(base[idx], years)
            lead = lead[np.isfinite(lead)]
            p5 = float(np.percentile(lead, 5)) if len(lead) else float("nan")
            ref = BOOK_REF_BARS if base_name == "#463" else LINE_BAR
            ok = st["roc"] >= ref[0] and st["sort"] >= ref[1] and p5 > 0
            rows.append((lab, base_name, s, st["roc"], st["sort"], p5, ok))
            if lab == "c" and base_name == "L":
                shadow = bool(ok)
    return rows, shadow


# ================================================================== overlap (section 7)
def held_minutes(intervals, dates):
    """{date: int8[390]} side held by RTH clock minute (09:30 = 0), half-open [start, end), clipped to 09:30-16:00;
    multi-day holds fill every listed session in between. Minutes held by both sides = 2. -> (map, overlapping holds)."""
    dates = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(dates))))
    out = {d: np.zeros(390, np.int8) for d in dates}
    nover, prev_end = 0, None
    for s, e, sd in sorted(intervals, key=lambda t: t[0]):
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        if prev_end is not None and s < prev_end:
            nover += 1
        prev_end = e if prev_end is None or e > prev_end else prev_end
        if e <= s:
            continue
        i0 = dates.searchsorted(s.normalize(), "left")
        i1 = dates.searchsorted((e - pd.Timedelta(1, "ns")).normalize(), "right")
        for d in dates[i0:i1]:
            r0 = d + pd.Timedelta(minutes=OPEN_HM)
            a, b = max(s, r0), min(e, d + pd.Timedelta(minutes=960))
            if b <= a:
                continue
            m0 = int(math.ceil((a - r0).total_seconds() / 60.0))
            m1 = int(math.ceil((b - r0).total_seconds() / 60.0))
            seg = out[d][m0:m1]
            seg[(seg != 0) & (seg != sd)] = 2
            seg[seg == 0] = int(sd)
    return out, nover


def crown_intervals(df, close_end=True):
    """(entry, exit, side); an exit stamped 15:55 is that bar's close, so it ends at 16:00 (NOISE, ORB)."""
    ex = pd.Series(pd.to_datetime(df["exit"]).to_numpy(), index=df.index)
    if close_end:
        add = np.where((ex.dt.hour * 60 + ex.dt.minute).to_numpy() == LAST_HM, 5, 0)
        ex = ex + pd.Series(pd.to_timedelta(add, unit="m"), index=df.index)
    return list(zip(pd.to_datetime(df["entry"]), ex, df["side"].astype(int)))


def ttm_intervals(trades, index):
    """TTM #459: [stamp(e0), stamp(e1) + 30 min), side = sign(t[3])."""
    ts = naive(index)
    return [(ts[int(t[0])], ts[int(t[1])] + pd.Timedelta(minutes=30), int(np.sign(t[3]))) for t in trades]


def ttm_trades():
    from augur_engine.engine import run_backtest as eng_bt
    from api.book_shadow import BOOK463_LEGS
    leg = [l for l in BOOK463_LEGS if l["strategy"] == "TTMSQZ_3_0_ES30SSOF2.py"][0]
    A30 = load_master("ES", "30m", "db_adj_rth", TTM_MASTER)
    r = eng_bt(strategy(leg["strategy"]), arrays=A30, params=leg["params"], cost_pts=leg["cost_pts"], return_trades=True)
    return ttm_intervals(r.get("trades") or [], A30["index"])


def balance_intervals(wf):
    return list(zip(wf["fill_stamp"], wf["held_end"], wf["side"].astype(int)))


def overlap(wf, crowns):
    """Per crown: share of BALANCE trade sessions that are crown-flat, share flat for all crowns, share of BALANCE's
    held minutes the crown also holds, and the same-side share of those. NOISE #382 / #422 overlap must be 0."""
    dates = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(wf["session"]))))
    bal, _ = held_minutes(balance_intervals(wf), dates)
    rows, flat_all, flats = [], np.ones(len(dates), bool), {}
    hb = int(sum((bal[d] != 0).sum() for d in dates))
    for name, iv in crowns.items():
        cm, nover = held_minutes(iv, dates)
        flat = np.array([not cm[d].any() for d in dates], bool)
        flats[name] = pd.Series(flat, index=dates)
        flat_all &= flat
        both = int(sum(((bal[d] != 0) & (cm[d] != 0)).sum() for d in dates))
        same = int(sum(((bal[d] != 0) & ((cm[d] == bal[d]) | (cm[d] == 2))).sum() for d in dates))
        rows.append({"crown": name, "sessions": len(dates), "crown_flat_share": float(flat.mean()) if len(dates) else np.nan,
                     "held_minutes": hb, "overlap_minutes": both, "overlap_share": both / hb if hb else np.nan,
                     "same_side_share": same / both if both else np.nan, "overlapping_holds_in_crown": nover})
        if name.startswith("NOISE") and both != 0:
            raise SystemExit("overlap with %s is %d minutes, must be 0 by construction - a bug, abort" % (name, both))
    flats["ALL"] = pd.Series(flat_all, index=dates)
    rows.append({"crown": "ALL FIVE FLAT", "sessions": len(dates), "crown_flat_share": float(flat_all.mean()) if len(dates)
                 else np.nan, "held_minutes": hb, "overlap_minutes": np.nan, "overlap_share": np.nan,
                 "same_side_share": np.nan, "overlapping_holds_in_crown": np.nan})
    return pd.DataFrame(rows), flats


def load_crowns_for_overlap():
    cr = {}
    for nm in ("NOISE382", "NOISE422", "ORB314"):
        cr[nm] = crown_intervals(load_crown(nm))
    cr["ENGUQ335"] = crown_intervals(load_crown("ENGUQ335"), close_end=False)
    cr["TTM459"] = ttm_trades()
    return cr


# ================================================================== day groups (section 4 (ii)) and diagnostics
SUBS = ("QUIET no raw break all day", "QUIET break blocked by #304's gates", "QUIET break only on the last bar",
        "BREAK-WIN", "BREAK-LOSS VWAP", "BREAK-LOSS STOP", "BREAK-LOSS FLAT")
SCOPE = {"QUIET no raw break all day": "scope: no NOISE break all day", "BREAK-WIN": "scope: a later break that wins",
         "BREAK-LOSS VWAP": "scope: a later break that loses at VWAP"}


def split3(S, balance, brk_side, tr304, L, inR, P):
    """Every WF BALANCE day -> QUIET / BREAK-WIN / BREAK-LOSS by #304's FIRST trade that session (unit $ > 0 wins), with
    the QUIET sub-split (asserted to explain every QUIET day) and BREAK-LOSS by #304's exit class."""
    vsp, dlo = float(P.get("vol_skip_pct", 0.0)), float(P.get("daytype_lo", 0.2))
    by = {si: g.sort_values("entry_idx") for si, g in tr304.groupby("si")}
    rows = []
    for si in np.flatnonzero(balance):
        d = S.dates[si]
        if not (WF0 <= d <= WF1):
            continue
        a, m = int(S.a[si]), int(S.m[si])
        g = by.get(si)
        if g is not None and len(g):
            f = g.iloc[0]
            if S.hm[int(f["signal_idx"])] < 720:
                raise SystemExit("#304's first signal on BALANCE day %s is before 12:00 - abort" % d.date())
            if not np.isfinite(f["unit_usd"]):
                raise SystemExit("#304 trade on %s has no unit $ - abort" % d.date())
            grp = "BREAK-WIN" if f["unit_usd"] > 0 else "BREAK-LOSS"
            ec = exit_class(f["exit_rule"])
            sub = grp if grp == "BREAK-WIN" else "BREAK-LOSS " + ec
            u = float(g["unit_usd"].sum())
        else:
            grp, ec, u = "QUIET", "", 0.0
            ks = np.flatnonzero(brk_side[a:a + m] != 0)
            if len(ks) == 0:
                sub = SUBS[0]
            elif (ks <= m - 2).any():
                kk = ks[ks <= m - 2]
                vol_blk = vsp > 0 and np.isfinite(S.vol_pct[si]) and S.vol_pct[si] >= vsp
                short_blk = (np.isfinite(S.dt_pos[si]) and S.dt_pos[si] <= dlo
                             and bool((brk_side[a + kk] == -1).all()))
                if not (vol_blk or short_blk):
                    raise SystemExit("QUIET day %s has a raw break at k <= m-2 that #304's gates do not explain - abort"
                                     % d.date())
                sub = SUBS[1]
            else:
                sub = SUBS[2]
        rows.append({"date": d, "si": int(si), "group": grp, "sub": sub, "exit_304": ec, "unit_304": u,
                     "L": float(L.get(d, np.nan)), "inR": bool(inR.get(d, False))})
    sp = pd.DataFrame(rows, columns=["date", "si", "group", "sub", "exit_304", "unit_304", "L", "inR"])
    q = sp[sp.group == "QUIET"]
    if q["sub"].isin(SUBS[:3]).sum() != len(q):
        raise SystemExit("QUIET sub-split does not sum to QUIET - abort")
    return sp


def group_masks(sp):
    out = [("QUIET", sp.group == "QUIET")]
    out += [("  " + s + (" [%s]" % SCOPE[s] if s in SCOPE else ""), sp["sub"] == s) for s in SUBS[:3]]
    out += [("BREAK-WIN" + " [%s]" % SCOPE["BREAK-WIN"], sp.group == "BREAK-WIN"), ("BREAK-LOSS", sp.group == "BREAK-LOSS")]
    out += [("  " + s + (" [%s]" % SCOPE[s] if s in SCOPE else ""), sp["sub"] == s) for s in SUBS[4:]]
    out += [("ALL WF BALANCE days", np.ones(len(sp), bool))]
    return out


def coloss_table(sp):
    """#304 and L figures only: days, days in R, L net, L losing $, #304 unit net, #304 losing unit $ (session level)."""
    rows = []
    for lab, mk in group_masks(sp):
        g = sp[np.asarray(mk, bool)]
        rows.append((lab, len(g), int(g.inR.sum()), float(g.L.sum()), float(g.L[g.L < 0].sum()),
                     float(g.unit_304.sum()), float(g.unit_304[g.unit_304 < 0].sum())))
    allL = float(sp.L[sp.L < 0].sum())
    blL = float(sp.L[(sp.L < 0) & (sp.group == "BREAK-LOSS")].sum())
    return rows, (blL / allL + 0.0 if allL else float("nan"))


def drift_matrix(S, mask):
    """M[f, e] = mean over the masked sessions of P[e] / P[f] - 1; slots 0..77 = 09:30 .. 15:55 opens, 78 = 15:55 close."""
    ss = np.flatnonzero(mask)
    P = np.full((len(ss), 79), np.nan)
    for j, si in enumerate(ss):
        a, b = int(S.a[si]), int(S.b[si])
        sl = (S.hm[a:b] - OPEN_HM) // 5
        ok = (sl >= 0) & (sl < 78)
        P[j, sl[ok]] = S.o[a:b][ok]
        lst = np.flatnonzero(S.hm[a:b] == LAST_HM)
        if len(lst):
            P[j, 78] = S.c[a + lst[0]]
    M = np.full((79, 79), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for f in range(78):
            M[f, f + 1:] = np.nanmean(P[:, f + 1:] / P[:, [f]] - 1.0, axis=0)
    return M


def drift(wf, M):
    """Drift control: gross minus side x the mean clock move between the same stamps x entry; side shares."""
    if not len(wf):
        return None
    f = ((wf["fill_hm"].to_numpy() - OPEN_HM) // 5).astype(int)
    e = np.where(wf["close_exit"].to_numpy(bool), 78, (wf["exit_hm"].to_numpy() - OPEN_HM) // 5).astype(int)
    dpts = wf["side"].to_numpy() * M[f, e] * wf["entry"].to_numpy(float)
    held = (wf["held_end"] - wf["fill_stamp"]).dt.total_seconds().to_numpy() / 60.0
    lg = wf["side"].to_numpy() > 0
    return {"long_share_trades": float(lg.mean()), "long_share_minutes": float(held[lg].sum() / held.sum()),
            "gross_pts": float(wf["gross_pts"].mean()), "drift_pts": float(np.nanmean(dpts)),
            "adj_gross_pts": float(np.nanmean(wf["gross_pts"].to_numpy() - dpts))}


def event_path(wf):
    ok = wf[(wf["R0"] > 0) & ~wf["beyond"].astype(bool)]
    if not len(ok):
        return np.full(len(TAUS), np.nan)
    M = np.empty((len(ok), len(TAUS)))
    for j, t in enumerate(ok.itertuples()):
        mins = np.array([0] + [mm for mm, _ in t.marks], float)
        vals = np.array([0.0] + [p / t.R0 for _, p in t.marks])
        row = vals[np.searchsorted(mins, TAUS, side="right") - 1]
        row[TAUS >= t.exit_min] = t.gross_pts / t.R0
        M[j] = row
    return M.mean(axis=0)


def disperse(path=None, ndx=None):
    """DISP = the cross-sectional SD (ddof 1) of Nasdaq-100 members' 09:30-open to 09:55-close returns; a day counts
    when >= 80% of that month's members have both prices; tercile by percentile (strict <) among the DISP values of the
    prior 252 SESSIONS (every day in the cut file; a day the guard drops is a session with no value), >= 60 values
    needed, else 'unlabelled'; edges 33.3 / 66.7. -> (labels on the counted days, sessions without a DISP value)."""
    from build_ndx_members import members_on
    raw = pd.read_csv(path or OPEN_BARS, usecols=["symbol", "t", "o", "c", "day"])
    raw = raw[pd.to_datetime(raw["day"]) <= CUT]
    if pd.to_datetime(raw["day"]).max() > CUT:
        raise SystemExit("open_bars cut failed - abort")
    t = pd.to_datetime(raw["t"], utc=True).dt.tz_convert("US/Eastern")
    raw = raw.assign(hm=t.dt.hour * 60 + t.dt.minute)
    o = raw[raw.hm == 570].set_index(["day", "symbol"])["o"]
    c = raw[raw.hm == 595].set_index(["day", "symbol"])["c"]
    j = pd.concat([o, c], axis=1, join="inner").dropna()
    ret = j["c"] / j["o"] - 1.0
    disp = ret.groupby(level=0).std(ddof=1)
    n = ret.groupby(level=0).size()
    need = {}
    for d in n.index:
        if d[:7] not in need:
            need[d[:7]] = len(members_on(d, path=ndx or NDX_CSV))
    ok = np.array([k >= DISP_COVER * need[d[:7]] - 1e-9 for d, k in n.items()], bool)
    disp = disp[ok]
    disp.index = pd.DatetimeIndex(pd.to_datetime(disp.index))
    cal = pd.DatetimeIndex(sorted(pd.to_datetime(raw["day"]).unique()))     # the session calendar
    v = disp.reindex(cal).to_numpy(float)
    pct = np.full(len(v), np.nan)
    for i in np.flatnonzero(np.isfinite(v)):
        prior = v[max(0, i - DISP_WIN):i]
        prior = prior[np.isfinite(prior)]
        if len(prior) >= DISP_MIN:
            pct[i] = 100.0 * np.mean(prior < v[i])
    lab = np.where(np.isnan(pct), "unlabelled", np.where(pct < DISP_EDGES[0], "low", np.where(pct < DISP_EDGES[1], "mid", "high")))
    keep = np.isfinite(v)
    return pd.Series(lab[keep], index=cal[keep]), int((~keep).sum())


def vwapfade_x(S, wf):
    vw, vwsd, _, _ = strategy("VWAP_FADE_1_0.py")._session_vwap(S.h, S.l, S.c, S.v, S.did, S.n)
    i = wf["sig_i"].to_numpy(int)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(vwsd[i] > 0, np.abs(S.c[i] - vw[i]) / vwsd[i], np.nan)
    return z


def corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _pfn(s):
    return "n %4d  net %10s  PF %s" % (len(s), fm(float(s.sum())), f2(pf(s), 3))


def diagnostics(name, c, W, ctx, extra=None):
    """Section 9, printed in order (a report, never a bar)."""
    _require_run("diagnostics")
    wf, bdays, inR, x = c.wf, W.bdays, W.inR.to_numpy(), c.x
    print("\n---- SECTION 9 DIAGNOSTICS: %s %s (n %d WF trades) ----" % (ctx.inst, name, len(wf)))
    ep = event_path(wf)
    print("  event-time path, mean R by minute from entry (0 .. 390, step 5; frozen at realised R after exit):")
    for i in range(0, len(TAUS), 13):
        print("    " + "  ".join("%3d:%+.2f" % (TAUS[j], ep[j]) for j in range(i, min(i + 13, len(TAUS)))))
    for lo, hi in HALVES:
        k = (bdays >= lo) & (bdays <= hi)
        g = wf[(wf.session >= lo) & (wf.session <= hi)]
        print("  regime %s .. %s: %s  own ROC@$30k %s" % (lo.date(), hi.date(), _pfn(g["net_usd"]),
                                                          f2(own(x[k], bdays[k])["roc"])))
    gsum, n = float(wf["gross_pts"].sum()), len(wf)
    print("  cost curve (%s points a round trip -> net): " % ctx.inst + "; ".join(
        "%s %.3f -> %s" % (lab, cc, fm(ctx.mult * gsum - ctx.mult * cc * n)) for lab, cc in COST_CURVE[ctx.inst])
          + "; break-even cost %s pts (= mean gross)" % f2(gsum / n if n else np.nan, 3))
    fy = jy(wf["session"]) if n else np.array([])
    for y in range(2016, 2025):
        g = wf[fy == y]
        print("  year %s: %s  long %d / short %d" % (jy_label(y), _pfn(g["net_usd"]), int((g.side > 0).sum()),
                                                     int((g.side < 0).sum())))
    for lab, eps in (("R episode", W.R_eps), ("#463 episode", W.D_eps)):
        vals = ["%s..%s %s" % (s.date(), e.date(), fm(float(x[(bdays >= s) & (bdays <= e)].sum()))) for s, e in eps]
        print("  %s P&L (%d):" % (lab, len(eps)))
        for i in range(0, len(vals), 4):
            print("    " + " | ".join(vals[i:i + 4]))
    legs = dict(W.legs)
    legs["RES"] = W.RES
    print("  correlations, all WF days: " + ", ".join("%s %s" % (k, f2(corr(x, v.to_numpy()), 3)) for k, v in legs.items()))
    print("  correlations, R days:      " + ", ".join("%s %s" % (k, f2(corr(x[inR], v.to_numpy()[inR]), 3))
                                                    for k, v in legs.items()))
    rok = (wf["R0"] > 0) & ~wf["beyond"].astype(bool)
    for lab, mk in (("long", wf.side > 0), ("short", wf.side < 0)):
        g = wf[mk]
        gr = g[rok[mk]]
        print("  %-5s %s  mean realised R %s" % (lab, _pfn(g["net_usd"]), f2(float((gr.gross_pts / gr.R0).mean()) if len(gr) else np.nan, 3)))
    tot = float(wf["net_usd"].sum())
    t10 = float(np.sort(wf["net_usd"].to_numpy())[-10:].sum()) if n else np.nan
    d10 = float(np.sort(x)[-10:].sum())
    print("  concentration: top-10 trades %s of net (%s); top-10 days %s (%s); net without best day %s, without best "
          "trade %s" % (f2(t10 / tot if tot else np.nan, 3), fm(t10), f2(d10 / tot if tot else np.nan, 3), fm(d10),
                        fm(tot - float(x.max())), fm(tot - (float(wf["net_usd"].max()) if n else 0.0))))
    print("  exits (R0 <= 0 or a fill at / beyond the band: %d trades kept in P&L, left out of R):" % int((~rok).sum()))
    for r in EXITS:
        g = wf[wf.exit_reason == r]
        gr = g[rok[wf.exit_reason == r]]
        print("    %-9s share %s  P&L %10s  hit (gross > 0) %s  mean realised R %s%s" % (
            r, f2(len(g) / n if n else np.nan, 3), fm(float(g.net_usd.sum())),
            f2(float((g.gross_pts > 0).mean()) if len(g) else np.nan, 3),
            f2(float((gr.gross_pts / gr.R0).mean()) if len(gr) else np.nan, 3),
            ("  (opposite-band TARGETs %d)" % int(g.opp_band.sum())) if r == TARGET else ""))
    tps = wf.groupby("session").size().value_counts().sort_index() if n else pd.Series(dtype=int)
    print("  trades per session: " + ", ".join("%d: %d" % (k, v) for k, v in tps.items()))
    for lab, mk in (("1st", wf.order == 1), ("2nd", wf.order == 2), ("3rd+", wf.order >= 3)):
        print("    net by order %-4s %s" % (lab, _pfn(wf[mk]["net_usd"])))
    if extra is not None and "sp" in extra:
        day_groups(wf, extra["sp"], W)
    if n:
        q1, q2 = np.quantile(wf["D"], [1 / 3, 2 / 3])
        for lab, mk in (("D <= %.2f" % q1, wf.D <= q1), ("%.2f < D <= %.2f" % (q1, q2), (wf.D > q1) & (wf.D <= q2)),
                        ("D > %.2f" % q2, wf.D > q2)):
            print("  room tercile %-22s %s" % (lab, _pfn(wf[mk]["net_usd"])))
    z = vwapfade_x(ctx.S, wf)
    big = z >= VW_SIGMA
    print("  VWAP_FADE crosswalk: %s of entries at >= 2.0 vwsigma; their net %s" % (
        f2(float(big.mean()) if n else np.nan, 3), fm(float(wf["net_usd"][big].sum()))))
    if W.disp is not None:
        lab = W.disp.reindex(pd.DatetimeIndex(wf["session"])).fillna("unlabelled").to_numpy()
        print("  DISPERSE split: " + "; ".join("%s %s" % (k, _pfn(wf["net_usd"][lab == k]))
                                               for k in ("low", "mid", "high", "unlabelled")))
    print("  no-2020 (without 2020-02-15 .. 04-30) net %s; no-2022 (without calendar 2022) net %s" % (fm(c.x11), fm(c.x22)))
    data_notes(ctx, c)


def day_groups(wf, sp, W):
    """BALANCE's trades, net and PF per day group / sub-row; the co-loss shares vs #304 and vs L, all WF and inside R."""
    m = sp.set_index("date")
    sess = wf.groupby("session")["net_usd"].sum()
    sess.index = pd.DatetimeIndex(sess.index)
    for lab, mk in group_masks(sp):
        ds = set(pd.DatetimeIndex(sp["date"][np.asarray(mk, bool)]))
        g = wf[pd.DatetimeIndex(wf["session"]).isin(ds)]
        print("  day group %-62s %s" % (lab, _pfn(g["net_usd"])))
    los = sess[sess < 0]
    grp = m["group"].reindex(los.index)
    Lv = W.line.reindex(los.index)                                       # L = q19/line.csv column line (section 4)
    inr = W.inR.reindex(los.index).fillna(False).to_numpy(bool)
    for lab, sel in (("all WF days", np.ones(len(los), bool)), ("inside R", inr)):
        l = los[sel]
        a = float(np.abs(l).sum())
        bl = float(np.abs(l[(grp[sel] == "BREAK-LOSS").to_numpy()]).sum())
        lv = float(np.abs(l[(Lv[sel] < 0).to_numpy()]).sum())
        print("  co-loss share (%s): vs #304 %s $ / %s count; vs L %s $ / %s count (losing sessions %d)" % (
            lab, f2(bl / a if a else np.nan, 3), f2(float((grp[sel] == "BREAK-LOSS").mean()) if len(l) else np.nan, 3),
            f2(lv / a if a else np.nan, 3), f2(float((Lv[sel] < 0).mean()) if len(l) else np.nan, 3), len(l)))


def data_notes(ctx, c):
    S = ctx.S
    print("  data notes (%s):" % ctx.inst)
    lab = classify(S, S.has1555 & ~S.warm & ctx.roll, ctx.brk)
    for y in range(2009, 2025):
        rows = [r for r in ctx.roll_notes if jy([r[2]])[0] == y]
        if rows:
            print("    rolls %s: " % jy_label(y) + "; ".join("%s (%+.2f) -> %s %s" % (
                sw.strftime("%Y-%m-%d %H:%M"), off, d.date(), "BALANCE-labelled" if lab[j] else "not BALANCE") for sw, off, d, j in rows))
    for d in ("2014-06-12", "2014-06-13"):
        print("    %s %s in master" % (d, "PRESENT" if pd.Timestamp(d) in set(S.dates) else "absent"))
    for d in ("2014-06-16", "2020-03-02", "2020-07-01"):
        j = np.flatnonzero(S.dates == pd.Timestamp(d))
        if len(j) and j[0] > 0:
            p = j[0] - 1
            print("    %s prev_close = %s's last bar (%s)" % (d, S.dates[p].date(), S.ts[S.b[p] - 1].strftime("%H:%M")))
    short = np.flatnonzero(ctx.trading & (S.m < 78))
    print("    trading sessions with missing bars (bands stay positional): %d - %s" % (
        len(short), ", ".join("%s m=%d" % (S.dates[s].date(), S.m[s]) for s in short) or "none"))
    aff = c.tr[c.tr.si.isin(short)] if len(c.tr) else c.tr
    for t in aff.itertuples():
        print("      affected trade %s %s fill %s exit %s %s side %+d" % (
            t.stretch, t.session.date(), t.fill_stamp.strftime("%H:%M"), t.exit_stamp.strftime("%H:%M"), t.exit_reason,
            t.side))
    live = ~S.warm[S.si]
    nanv = np.isnan(S.V) & live
    print("    zero-volume bars %d; NaN-VWAP bars in banded sessions %d (in %d sessions)" % (
        int((S.v == 0).sum()), int(nanv.sum()), len(np.unique(S.si[nanv]))))


# ================================================================== counts tables (section 4)
def counts_table(ctx, fs, roll_bal, rfs, elig_nb):
    S = ctx.S
    Y = jy(S.dates)
    rows = []
    for y in range(2009, 2025):
        sel = Y == y
        r = {"year": jy_label(y), "stretch": "WARMUP" if y == 2009 else ("WF" if y >= 2016 else "EARLY"),
             "sessions_loaded": int(sel.sum()), "with_1555": int((sel & S.has1555).sum()),
             "warmup_excluded": int((sel & S.has1555 & S.warm).sum()),
             "roll_excluded": int((sel & S.has1555 & ~S.warm & ctx.roll).sum()), "trading": int((sel & ctx.trading).sum()),
             "balance": int((sel & ctx.balance).sum()), "roll_balance_labelled": int((sel & roll_bal).sum()),
             "elig_304_nobreak_by_noon": int((sel & elig_nb).sum())}
        for nm, _ in CELLS:
            r["roll_first_" + nm] = int((sel & (rfs[nm][0] >= 0)).sum())
        for nm, _ in CELLS:
            idx, sd = fs[nm]
            r[nm + "_first"] = int((sel & (idx >= 0)).sum())
            r[nm + "_long"] = int((sel & (idx >= 0) & (sd > 0)).sum())
            r[nm + "_short"] = int((sel & (idx >= 0) & (sd < 0)).sum())
        rows.append(r)
    df = pd.DataFrame(rows)
    num = [c for c in df.columns if c not in ("year", "stretch")]
    tot = []
    for lab in ("WF", "EARLY"):
        t = df[df.stretch == lab][num].sum()
        tot.append(dict(year="TOTAL " + lab, stretch=lab, **{k: int(v) for k, v in t.items()}))
    return pd.concat([df, pd.DataFrame(tot)], ignore_index=True)


def print_counts_table(df):
    cols = [("year", "%-16s"), ("sessions_loaded", "%6s"), ("with_1555", "%6s"), ("warmup_excluded", "%5s"),
            ("roll_excluded", "%5s"), ("trading", "%6s"), ("balance", "%6s"), ("roll_balance_labelled", "%5s"),
            ("roll_first_B1", "%5s"), ("roll_first_B2", "%5s"), ("elig_304_nobreak_by_noon", "%6s"),
            ("B1_first", "%6s"), ("B1_long", "%5s"), ("B1_short", "%5s"), ("B2_first", "%6s"), ("B2_long", "%5s"),
            ("B2_short", "%5s")]
    hdr = ["year", "loaded", "15:55", "warm", "roll", "trade", "BAL", "rBAL", "rB1", "rB2", "x304", "B1 1st", "B1 L",
           "B1 S", "B2 1st", "B2 L", "B2 S"]
    print("  " + " ".join(f % h for (_, f), h in zip(cols, hdr)))
    for d in df.to_dict("records"):
        print("  " + " ".join(f % d[c] for c, f in cols))


def split_by_year(sp):
    out = []
    for y in range(2016, 2025):
        g = sp[jy(sp["date"]) == y] if len(sp) else sp
        r = {"year": jy_label(y)}
        for lab in ("QUIET", "BREAK-WIN", "BREAK-LOSS"):
            h = g[g.group == lab]
            r[lab] = len(h)
            r[lab + "_304_unit_net"] = float(h.unit_304.sum())
        for s in SUBS:
            r[s] = int((g["sub"] == s).sum())
        out.append(r)
    return pd.DataFrame(out)


# ================================================================== output files
def write_csv(df, name):
    os.makedirs(CACHE, exist_ok=True)
    df.to_csv(os.path.join(CACHE, name), index=False)


def write_trades(tr, tag, bdays):
    cols = TRADE_COLS + ["stretch", "held_end", "order", "opp_band", "beyond", "stress_usd"]
    write_csv(tr[cols], "trades_%s.csv" % tag)
    x = daily(tr[tr.stretch == "WF"], bdays)
    write_csv(pd.DataFrame({"date": x.index.strftime("%Y-%m-%d"), "net_usd": x.to_numpy()}), "daily_%s.csv" % tag)


def manifest(W, extra):
    files = {"NQ_5m_master": os.path.join(ROOT, "augur_uploads", MASTERS["NQ"][1]),
             "ES_5m_master": os.path.join(ROOT, "augur_uploads", MASTERS["ES"][1]),
             "ES_30m_master": os.path.join(ROOT, "augur_uploads", TTM_MASTER[1]),
             "rolls_NQ": ROLLS_CSV % "NQ", "rolls_ES": ROLLS_CSV % "ES", "residual_days": RESID_CSV, "line": LINE_CSV,
             "a2": A2_JSON, "episodes": EPIS_CSV, "resmom_cells_daily_wf": RES_CSV, "open_bars": OPEN_BARS,
             "ndx_members": NDX_CSV}
    for nm in ("NOISE422", "NOISE382", "ORB314", "ENGUQ335"):
        files[nm] = os.path.join(LEGS_DIR, "%s_raw_trades.csv" % nm)
    out = {"inputs": {k: {"path": p, "sha256": sha_bytes(p)} for k, p in files.items()},
           "prereg": W.prereg, "harness_sha256_lf": R11.sha_lf(os.path.abspath(__file__)),
           "auto_validate_space": AV_SPACE, "seeds": {"null": SEED_NULL, "bootstrap": SEED_BOOT}}
    out.update(extra)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)


# ================================================================== the modes
def header(W):
    print("BALANCE r1 STAGE A (%s) - prereg sha256(LF) %s; sections 3/6/8 %s (pinned; %s since GO)" % (
        MODE, W.prereg["sha256_lf"][:16], W.prereg["sections_3_6_8_sha256"][:16],
        "CHANGED" if W.prereg["whole_file_changed_since_go"] else "unchanged"))
    print("  Auto-Validate space (declared, AMENDMENT 0 item 6): " + "; ".join(
        "%s int %d..%d step %d" % (k, v["min"], v["max"], v["step"]) for k, v in AV_SPACE.items())
          + " = 8 configs, window pinned to WF, 900 trials, lockbox veto-only; default = the passing cell's stretch, "
            "last fill 360 (15:30)")


def print_parity(W):
    nq = W.nq
    for inst, ctx in (("NQ", nq),):
        S = ctx.S
        print("  master %s: id %d %s (db_noadj_rth), %d bars, %d sessions, %s .. %s" % (
            inst, MASTERS[inst][0], MASTERS[inst][1], S.n, S.ns, S.ts[0], S.ts[-1]))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f (93.81 / 3.816); index %d rows, %d UTC-Sunday, years %.4f" % (
        W.ref["roc"], W.ref["sort"], len(W.bdays), W.sund, W.years))
    print("  L = #463 + 0.264 x RES parity: ROC@30k %.2f  Sortino %.3f (120.82 / 3.916); RES book_mtm max |diff| $%.4f" % (
        W.Lst["roc"], W.Lst["sort"], W.Ldiff))
    print("  R: %d days in %d episodes (sha pinned; = a2.json union); #463 drawdown days %d in %d episodes" % (
        int(W.inR.sum()), len(W.R_eps), int(W.ddmask.sum()), len(W.D_eps)))
    pi = W.par
    print("  NOISE #304 parity (NOISE_1_0 + _FROZEN on master 37): %d of %d WF trades matched NOISE422_raw_trades.csv; "
          "band / VWAP at %d decision bars, max |diff| %.3g; eligible first break = #304's first entry on %d of %d "
          "sessions, 0 mismatches" % (pi["matched"], N_PARITY, pi["bars"], pi["max_diff"], pi["sessions"], nq.S.ns))
    print("  rolls NQ: %d switches to the cut (%d in WF), %d roll sessions (%d in WF)" % (
        len(nq.switches), nq.n_wf_switches, int(nq.roll.sum()), int((nq.roll & (nq.S.dates >= WF0)).sum())))


def setup():
    W = SimpleNamespace()
    W.prereg = prereg_check()
    header(W)
    P = frozen()
    W.P = P
    W.B, W.ref = HH.book()
    W.bdays, W.years, W.sund = index_checks(W.B)
    W.L, W.RES, W.line, W.Lst, W.Ldiff = load_L(W.B)
    W.inR, W.R_eps, W.a2 = load_R(W.bdays)
    W.D_eps, W.ddmask = load_episodes(W.bdays)
    W.f422 = load_crown("NOISE422")
    W.nq = prepare("NQ", P)
    assert_balance_on_index(W.nq, W.bdays)
    W.par = parity_304(W.nq, W.f422)
    W.eidx = early_index(W.nq.S, W.nq.trading)
    print_parity(W)
    return W


def mode_counts(W):
    nq = W.nq
    S = nq.S
    fs = {nm: first_signals(S, nq.balance, nq.brk, k / 12.0) for nm, k in CELLS}
    roll_bal = classify(S, S.has1555 & ~S.warm & nq.roll, nq.brk)
    rfs = {nm: first_signals(S, roll_bal, nq.brk, k / 12.0) for nm, k in CELLS}
    e_hm = np.where(nq.elig >= 0, S.hm[np.maximum(nq.elig, 0)], 99999)
    elig_nb = nq.trading & (e_hm > NOON_LAST)
    df = counts_table(nq, fs, roll_bal, rfs, elig_nb)
    print("\n(i) SESSIONS PER JULY-JUNE YEAR (stamp-based, cut load; supersedes the drafting 914 / 1,078 everywhere - "
          "MANAGER #40 item 7)")
    print("  loaded = sessions in the array; 15:55 = with a 15:55 bar; warm / roll = of those, left out; trade = trading "
          "sessions; BAL = BALANCE days; rBAL = BALANCE-labelled roll sessions (never traded) and rB1 / rB2 their first "
          "signals; x304 = #304-eligible no-break-by-noon days (crosswalk, never a cell); B1 / B2 = sessions with a "
          "FIRST signal, by side")
    print_counts_table(df)
    sp = split3(S, nq.balance, nq.brk_side, nq.tr304, W.line, W.inR, nq.P)
    yb = split_by_year(sp)
    print("\n(ii) THREE-WAY SPLIT OF WF BALANCE DAYS by #304's held trades (NOISE422_raw_trades.csv, unit $ = pnl_usd / "
          "size; #304 figures, not BALANCE)")
    for d in yb.to_dict("records"):
        print("  %s  QUIET %3d (#304 unit net %10s)  BREAK-WIN %3d (#304 %10s)  BREAK-LOSS %3d (#304 %10s)" % (
            d["year"], d["QUIET"], fm(d["QUIET_304_unit_net"]), d["BREAK-WIN"], fm(d["BREAK-WIN_304_unit_net"]),
            d["BREAK-LOSS"], fm(d["BREAK-LOSS_304_unit_net"])))
    print("  sub-rows per year: " + " / ".join(SUBS))
    for d in yb.to_dict("records"):
        print("    %s  %s" % (d["year"], "  ".join("%4d" % d[s] for s in SUBS)))
    rows, share = coloss_table(sp)
    print("  CO-LOSS EXPOSURE (WF BALANCE days; L = q19/line.csv column line; #304 losing unit $ at session level):")
    print("    %-66s %5s %5s %12s %12s %12s %12s" % ("group", "days", "inR", "L net", "L losing", "#304 net", "#304 losing"))
    for lab, nd, nr, ln, ll, un, ul in rows:
        print("    %-66s %5d %5d %12s %12s %12s %12s" % (lab, nd, nr, fm(ln), fm(ll), fm(un), fm(ul)))
    print("  SHARE of L's losing $ on WF BALANCE days that falls on BREAK-LOSS days: %s" % f2(share, 3))
    write_csv(df.merge(yb, on="year", how="left"), "counts_by_year.csv")
    write_csv(sp[["date", "group", "exit_304"]].assign(date=pd.DatetimeIndex(sp["date"]).strftime("%Y-%m-%d"))
              .rename(columns={"exit_304": "first_304_exit"}), "split3_days.csv")
    print("\n(no BALANCE exit was run; total trades, re-entries and trades per session print only in the real run)")


def run_cells(W, ctx, sig_last=SIG_LAST):
    out = {}
    for nm, k in CELLS:
        tr = simulate(ctx.S, ctx.balance, k / 12.0, ctx.cost, ctx.mult, ctx.stress, sig_last)
        out[nm] = summarize(tr, W.bdays, W.inR.to_numpy(), W.years, early_index(ctx.S, ctx.trading))
    return out


def power_block(W, cells):
    b1 = cells["B1"].wf
    pw = power(b1, W.B, W.L, W.bdays, W.years)
    nl = family_null([(nm, 20.0 * cells[nm].wf["gross_pts"].to_numpy(float),
                       W.bdays.get_indexer(pd.DatetimeIndex(cells[nm].wf["session"]))) for nm, _ in CELLS],
                     len(W.bdays), W.inR.to_numpy(), W.years, 20.0 * 0.533)
    return pw, nl


def res_on_first(W, nq):
    out = {}
    los_all = float(W.RES[W.RES < 0].sum())
    for nm, k in CELLS:
        idx, _ = first_signals(nq.S, nq.balance, nq.brk, k / 12.0)
        d = pd.DatetimeIndex(nq.S.dates[idx >= 0])
        d = d[(d >= WF0) & (d <= WF1)]
        r = W.RES.reindex(d)
        if r.isna().any():
            raise SystemExit("a first-signal session is not on the RES index - abort")
        out[nm] = {"sessions": len(d), "res_sum": float(r.sum()), "res_losing": float(r[r < 0].sum()),
                   "share_of_res_wf_losing": float(r[r < 0].sum() / los_all) if los_all else float("nan"),
                   "share_of_wf_days": len(d) / len(W.bdays)}
    return out


OVERLAP_POWER_COLS = ["crown", "crown_flat_share", "overlap_share", "same_side_share", "overlapping_holds_in_crown"]


def print_overlap(ov_by_cell):
    """Section 7 rows in --power: shares only (no session or trade counts - those print in the real run, bar 6)."""
    for nm, ov in ov_by_cell.items():
        print("  OVERLAP %s (WF schedule; positions by RTH clock minute, half-open):" % nm)
        for r in ov.itertuples(index=False):
            print("    %-14s crown-flat %s  held-minute overlap %s  same side %s  overlapping holds %s" % (
                r.crown, f2(r.crown_flat_share, 3), f2(r.overlap_share, 3), f2(r.same_side_share, 3),
                r.overlapping_holds_in_crown))


def mode_power(W):
    nq = W.nq
    cells = {}
    for nm, k in CELLS:
        tr = simulate(nq.S, nq.balance, k / 12.0, nq.cost, nq.mult, nq.stress)
        cells[nm] = SimpleNamespace(wf=tr[tr.stretch == "WF"])
    b1 = cells["B1"].wf
    pw, nl = power_block(W, cells)
    print("")
    print_power(pw, nl)                         # prints B1's n, disclosed in section 5; per-year counts wait (bar 6)
    crowns = load_crowns_for_overlap()
    ovs = {nm: overlap(cells[nm].wf, crowns)[0][OVERLAP_POWER_COLS] for nm, _ in CELLS}
    print_overlap(ovs)
    print("  NOISE #382 / #422 held overlap = 0 minutes on both cells (asserted)")
    rs = res_on_first(W, nq)
    for nm, r in rs.items():
        print("  RES on %s first-signal WF sessions (%d, %s of WF days): sum %s, losing %s = %s of RES's WF losing $" % (
            nm, r["sessions"], f2(r["share_of_wf_days"], 3), fm(r["res_sum"]), fm(r["res_losing"]),
            f2(r["share_of_res_wf_losing"], 3)))
    write_csv(nl["maxima"], "null_maxima.csv")
    write_csv(pd.concat([ov.assign(cell=nm) for nm, ov in ovs.items()]), "overlap.csv")
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "power.json"), "w", encoding="utf-8") as f:
        json.dump({"B1_n": len(b1), "power": pw, "null": {"p95": nl["p95"], "sd_rsum_B1": nl["sd_rsum_B1"]},
                   "res_first_signal": rs},
                  f, indent=1, default=float)
    print("\n(no real direction was computed for display)")


def _close(a, b, rel=1e-9):
    return abs(float(a) - float(b)) <= rel * max(1.0, abs(float(a)), abs(float(b)))


def check_power_json(pw, nl):
    path = os.path.join(CACHE, "power.json")
    if not os.path.exists(path):
        raise SystemExit("power.json is not on file - run --power first - abort")
    with open(path, encoding="utf-8") as f:
        pj = json.load(f)
    ok = pj["B1_n"] == pw["n"] and _close(pj["power"]["c"], pw["c"])
    for k in ("book_c", "book_twin", "line_c"):
        for q in ("sd", "line_5pct", "line_80pct"):
            ok &= _close(pj["power"]["lines"][k][q], pw["lines"][k][q])
    for q in ("t", "rsum", "roc"):
        ok &= _close(pj["null"]["p95"][q], nl["p95"][q])
    ok &= _close(pj["null"]["sd_rsum_B1"], nl["sd_rsum_B1"])
    if not ok:
        raise SystemExit("the recomputed power lines / null p95s differ from power.json - abort")


def print_cell(nm, c, tag=""):
    _require_run("print_cell")
    print("  %-8s n %5d (%5.1f/yr)  net %10s  PF %s  DD %9s  own ROC@$30k %6s  Sortino %5s  t %5s  R-sum %9s  "
          "R-sum ex-3 %9s  gross %s pt/trade  years + %d/9  stress net %10s  EARLY net %10s (n %d, own ROC@$30k %s)%s" % (
              nm, c.n, c.n / c.years, fm(c.net), f2(c.pf, 3), fm(c.st["max_dd"]), f2(c.st["roc"]), f2(c.st["sort"]),
              f2(c.t), fm(c.rs), fm(c.rs3), f2(c.gross, 3), sum(v > 0 for v in c.yrs), fm(c.stress), fm(c.early_net),
              c.early_n, f2(c.early_st["roc"]), tag))
    nyr = [int((jy(c.wf["session"]) == y).sum()) for y in range(2016, 2025)] if c.n else [0] * 9
    print("           per July-June year: " + ", ".join("%s n %d %s" % (jy_label(y), k, fm(v))
                                                       for y, k, v in zip(range(2016, 2025), nyr, c.yrs)))
    if c.n:
        reent = int((c.wf.order >= 2).sum())
        tps = c.wf.groupby("session").size()
        print("           total trades %d; re-entries %d; sessions with a trade %d; trades per session mean %.2f max %d" % (
            c.n, reent, len(tps), float(tps.mean()), int(tps.max())))


def reports(nm, c, W):
    _require_run("reports")
    x, bdays = c.x, W.bdays
    w = np.asarray((bdays > WORST[0]) & (bdays <= WORST[1]))
    ww = np.sort(x[w])
    ex3 = float(ww[:-3].sum()) if len(ww) > 3 else float("nan")
    no20 = float(x[bdays.year != 2020].sum())
    epsum = [float(x[(bdays >= s) & (bdays <= e)].sum()) for s, e in W.R_eps]
    print("  %s REPORTS: #463's 460 drawdown days %s; HALFHOUR form 2020-03-03 .. 03-27 %s, without its 3 best days %s; "
          "net without calendar 2020 %s; R-sum without its best R episode %s" % (
              nm, fm(float(x[W.ddmask].sum())), fm(float(ww.sum())), fm(ex3), fm(no20),
              fm(c.rs - max(epsum)) if epsum else "nan"))
    dr = drift(c.wf, W.drift_M)
    if dr:
        print("  %s DRIFT CONTROL: long share %s of trades, %s of held minutes; gross %s pt/trade, side x mean clock move "
              "%s pt/trade, drift-adjusted gross %s pt/trade (net %s)" % (
                  nm, f2(dr["long_share_trades"], 3), f2(dr["long_share_minutes"], 3), f2(dr["gross_pts"], 3),
                  f2(dr["drift_pts"], 3), f2(dr["adj_gross_pts"], 3),
                  fm(20.0 * (dr["adj_gross_pts"] - 0.533) * c.n)))


def twin_build(W):
    """B1's band twins, built and simulated (no printing): [(name, lookback, trades, summary)]."""
    nq = W.nq
    out = []
    for nm, lb in TWINS:
        Pt = twin_params(W.P, lb)
        St = build_bands(nq.A, Pt)
        bt, _ = raw_break(St)
        bal = classify(St, nq.trading & ~St.warm, bt)
        tr = simulate(St, bal, 0.5, nq.cost, nq.mult, nq.stress)
        c = summarize(tr, W.bdays, W.inR.to_numpy(), W.years, early_index(St, nq.trading & ~St.warm))
        out.append((nm, lb, tr, c))
    return out


def twin_rows(b1, built):
    _require_run("twin_rows")
    flips = []
    for nm, lb, tr, c in built:
        flip = (c.net > 0) != (b1.net > 0)
        flips.append(flip)
        print_cell("%s" % nm, c, "  [lookback %d, 1.0 / 1.0; report, no verdict]%s" % (lb, "  SIGN FLIP vs B1" if flip else ""))
    return any(flips)


def stage_verdict(verdict):
    """{cell: bars13 rows} -> (passed, count_only), read by bar NUMBER: a pass clears all 13 bars; a count-only cell
    fails bar 6 and nothing else (section 8; MANAGER #40 item 5)."""
    passed, count_only = [], []
    for nm, _ in CELLS:
        nos = sorted(no for no, _, _, _ in verdict[nm])
        if nos != list(range(1, 14)):
            raise SystemExit("verdict for %s does not hold bars 1..13 (%s) - abort" % (nm, nos))
        fails = [no for no, _, ok, _ in verdict[nm] if not ok]
        if not fails:
            passed.append(nm)
        elif fails == [6]:
            count_only.append(nm)
    return passed, count_only


def av_space_for(win):
    """The declared Auto-Validate space with section 11's default: the passing cell's stretch (None when none passed)."""
    av = json.loads(json.dumps(AV_SPACE))
    av["stretch_12ths"]["default"] = dict(CELLS)[win] if win else None
    return av


def mode_run(W):
    nq = W.nq
    cells = run_cells(W, nq)
    pw, nl = power_block(W, cells)
    check_power_json(pw, nl)
    # Every load, parity assert and build that can abort runs HERE, before any real direction prints, so an abort
    # forces only a clean re-run: #463's legs, the drift matrix, DISP, the crowns, the NQ day groups, ES (load, parity,
    # day groups, cells; a report, never a bar) and the band twins.
    W.legs = book_leg_dailies(W.bdays, W.B)
    W.drift_M = drift_matrix(nq.S, nq.trading & (nq.S.dates >= WF0))
    W.disp, disp_drop = disperse()
    crowns = load_crowns_for_overlap()
    sp = split3(nq.S, nq.balance, nq.brk_side, nq.tr304, W.line, W.inR, nq.P)
    es = es_prepare(W)
    built = twin_build(W)
    print("")
    print_power(pw, nl)
    print("  (recomputed and equal to power.json)")
    print("\nCELLS (WF 2016-07-01 .. 2025-06-29, 1 NQ, house cost 0.533; stress 1.533)")
    for nm, _ in CELLS:
        print_cell(nm, cells[nm], "  PRIMARY" if nm == "B1" else "")
    print("\nBAND TWINS OF B1 (AMENDMENT 0 item 4; settings fit on no return; reports, never bars or cells)")
    fragile = twin_rows(cells["B1"], built)
    verdict = {}
    for nm, _ in CELLS:
        other = [o for o, _ in CELLS if o != nm][0]
        bs = bars13(cells[nm], cells[other].net, nl["p95"])
        verdict[nm] = bs
        print("\nBARS %s" % nm)
        for no, lab, ok, val in bs:
            print("  %2d %-62s %-4s %s" % (no, lab, "PASS" if ok else "FAIL", val))
        reports(nm, cells[nm], W)
        rows, shadow = book_add(cells[nm].x, W.B, W.L, W.bdays, W.years)
        for lab, base, s, roc, so, p5, ok in rows:
            print("  BOOK-ADD REPORT %-9s x%.3f NQ on %-4s ROC@30k %7s Sortino %6s bootstrap p5 %+8s  (%s %s)" % (
                lab, s, base, f2(roc), f2(so, 3), f2(p5), "clears" if ok else "below",
                "98.50 / 3.816 / p5 > 0" if base == "#463" else "126.86 / 3.916 / p5 > 0"))
        print("  BOOK-ADD at c on L (judged): %s -> %s" % ("yes" if shadow else "no",
                                                         "a forward BOOK shadow line is also opened (MANAGER #70 gate)"
                                                         if shadow else "no shadow line"))
    passed, count_only = stage_verdict(verdict)
    win = passed[0] if passed else None
    print("")
    if passed:
        print("STAGE A: PASS (%s)%s -> plugin to harness parity, then the window-pinned 900-trial Auto-Validate the same "
              "day (8 configs declared; lockbox veto-only)" % (
                  win, " - FRAGILE: B1's WF net sign flips on a band twin; only the Auto-Validate lockbox can clear it"
                  if fragile else ""))
    elif count_only:
        print("STAGE A: FAIL - %s fails bar 6 (count) alone and clears the other 12 bars -> RESEARCH ROW on the RUNBOARD "
              "(as TTM r24), not a pass, no variants" % count_only[0])
    else:
        print("STAGE A: FAIL - dead, no variants")
    # the verdict's files are on disk before any section 9 report runs (a report failure cannot hide the verdict)
    for nm, _ in CELLS:
        write_trades(cells[nm].tr, "NQ_" + nm, W.bdays)
    for nm, _, tr, _ in built:
        write_trades(tr, "NQ_B1_" + nm, W.bdays)
    manifest(W, {"verdict": {"passed": passed, "count_only": count_only, "fragile": bool(fragile)},
                 "auto_validate_space": av_space_for(win)})
    print("\n(section 9 diagnostics and the ES transfer report follow; reports, never bars)")
    for nm, _ in CELLS:
        diagnostics(nm, cells[nm], W, nq, {"sp": sp})
    print("  DISPERSE: %d sessions without a DISP value (the 80%% coverage guard)" % disp_drop)
    print("\nPOST-RUN overlap P&L")
    for nm, _ in CELLS:
        ov, flats = overlap(cells[nm].wf, crowns)
        sess = cells[nm].wf.groupby("session")["net_usd"].sum()
        sess.index = pd.DatetimeIndex(sess.index)
        print("  %s net on crown-flat days: " % nm + "; ".join(
            "%s %s" % (k, fm(float(sess[v.reindex(sess.index).to_numpy(bool)].sum()))) for k, v in flats.items()))
    es_report(W, es)


def es_prepare(W):
    """ES transfer, the part that can abort (run before any real direction prints): master 33, rolls_ES, the band
    build, parity (b) / (c) against NOISE_1_0, the day-index assert, the day groups and both cells. No printing."""
    es = prepare("ES", W.P)
    assert_balance_on_index(es, W.bdays)
    es.par = parity_304(es)
    # day groups on ES use the ES NOISE_1_0 (#304 settings) run's own trades, unit $ = 50 x points - 50 x 0.363
    es.sp = split3(es.S, es.balance, es.brk_side, es.tr304, W.line, W.inR, es.P)
    es.cells = run_cells(W, es)
    return es


def es_report(W, es):
    """ES transfer REPORT: $50 a point, cost 0.363, stress 1.363; cell rows, files, then section 9 rows. Never a bar."""
    _require_run("es_report")
    pi, cells = es.par, es.cells
    print("\n==== ES TRANSFER REPORT (master 33, $50 a point, cost 0.363, stress 1.363; report only) ====")
    print("  ES band / VWAP parity at %d #304 decision bars (max |diff| %.3g); eligible first break on %d sessions, "
          "0 mismatches; %d roll switches (%d in WF)" % (pi["bars"], pi["max_diff"], pi["sessions"], len(es.switches),
                                                         es.n_wf_switches))
    for nm, _ in CELLS:
        print_cell("ES " + nm, cells[nm])
    for nm, _ in CELLS:
        write_trades(cells[nm].tr, "ES_" + nm, W.bdays)
    for nm, _ in CELLS:
        diagnostics(nm, cells[nm], W, es, {"sp": es.sp})
    return cells


def main(argv):
    global MODE
    if "--prereg-hashes" in argv:
        print(json.dumps(prereg_hashes(), indent=1))
        return
    MODE = "counts" if "--counts" in argv else ("power" if "--power" in argv else "run")
    os.environ["AUGUR_TRIAL_CACHE"] = "1"
    tee = Tee(os.path.join(OUTDIR, OUTFILE[MODE]))
    sys.stdout = tee
    try:
        W = setup()
        {"counts": mode_counts, "power": mode_power, "run": mode_run}[MODE](W)
    finally:
        sys.stdout = tee.o
        tee.close()


if __name__ == "__main__":
    main(sys.argv[1:])
