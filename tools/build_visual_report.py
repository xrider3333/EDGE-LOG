"""
NOISE 1.0 visual report — data build script.

REPO IS READ-ONLY: only reads optimizer_history.db (sqlite SELECT) and augur_uploads/
CSVs via the existing augur_engine data layer. Writes only into SCRATCH.

Run: python -B build_noise_report_data.py

PROMOTED FROM SCRATCHPAD 2026-08-08 (see docs/VISUAL_TRADE_REPORT.md) — copied verbatim
from a session scratchpad so it survives temp-dir wipes (tools/, this file's new home,
is git-tracked; the scratchpad is not). NOT YET adapted to run from the repo as-is:
  - ROOT / SCRATCH below are still the original session's absolute paths — update SCRATCH
    to a real output dir before re-running.
  - This script only writes the JSON data file (noise_visual_data.json / STEP 12 below).
    The actual chart-drawing code (SVG helpers + the reusable candlestickChart() function)
    lives in the <script> block of the shipped output, docs/samples/noise_visual_report.html
    — that file was produced by a separate template+assemble step (report_template.html +
    assemble_html.py, a straight string-substitution of the JSON into a template) that was
    NOT promoted into the repo, because its output (the rendered HTML, with the JS inlined)
    already is. See docs/VISUAL_TRADE_REPORT.md §"What exists today" for the full pipeline
    and exactly which files this covers.
"""
import os
import sys
import json
import time
import importlib.util
from datetime import date, datetime

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
SCRATCH = r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\2201ed1b-ca34-4985-8d9f-b4f68390f690\scratchpad"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.engine import run_backtest as eng_bt   # noqa: E402
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

# import tools/noise_research.py by path (no __init__.py in tools/)
_spec = importlib.util.spec_from_file_location("noise_research", os.path.join(ROOT, "tools", "noise_research.py"))
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)

def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)

SOURCE = "db_noadj_rth"
INSTRUMENT = "NQ"
TIMEFRAME = "5m"
SESSION = "rth"
FEE = 0.533
MULT = 20.0
DATE_TO_GATE = "2025-06-29"
DATE_TO_FULL = "2026-06-30"
LOCKBOX_START = "2025-06-30"

FROZEN = dict(lookback=14, band_mult_long=1.5, band_mult_short=1.5,
              exit_mode="vwap", side="Both", window="all_day",
              flat_eod=True, skip_holidays=False)
FROZEN_NR = dict(lookback=14, band_mult_long=1.5, band_mult_short=1.5,
                  exit_mode="vwap", side="Both", window="all_day")

EXPECTED_GATE = dict(n=3147, net=254382.98, pf=1.3110, dd=-31239.80)

# ─────────────────────────────────────────────────────────────────────────
log("=" * 70)
log("STEP 0 — locate master")
master = find_master(INSTRUMENT, TIMEFRAME, SESSION, SOURCE)
if master is None:
    log("ABORT: no master found for NQ/5m/rth/db_noadj_rth")
    sys.exit(1)
log("master file: %s" % master.get("filename"))

# ─────────────────────────────────────────────────────────────────────────
log("STEP 1 — SANITY GATE (pre-lockbox, date_to=%s) via augur_engine.engine.run_backtest + NOISE_1_0.py plugin" % DATE_TO_GATE)
t0 = time.time()
r_gate = eng_bt("NOISE_1_0.py", instrument=INSTRUMENT, timeframe=TIMEFRAME, session=SESSION,
                 source=SOURCE, cost_pts=FEE, date_to=DATE_TO_GATE, params=FROZEN)
log("  eng_bt elapsed %.1fs" % (time.time() - t0))
if r_gate is None:
    log("ABORT: gate backtest returned None")
    sys.exit(1)
n_gate = r_gate["num_trades"]
net_gate = r_gate["total_pnl"] * MULT
pf_gate = r_gate["profit_factor"]
dd_gate = r_gate["max_drawdown"] * MULT
log("  got:      n=%d net=$%s PF=%.4f DD=$%s" % (n_gate, format(net_gate, ",.2f"), pf_gate, format(dd_gate, ",.2f")))
log("  expected: n=%d net=$%s PF=%.4f DD=$%s" % (EXPECTED_GATE["n"], format(EXPECTED_GATE["net"], ",.2f"),
                                                    EXPECTED_GATE["pf"], format(EXPECTED_GATE["dd"], ",.2f")))
gate_pass = (n_gate == EXPECTED_GATE["n"] and abs(net_gate - EXPECTED_GATE["net"]) < 1.0
             and abs(pf_gate - EXPECTED_GATE["pf"]) < 0.001 and abs(dd_gate - EXPECTED_GATE["dd"]) < 1.0)
log("  ENGINE (NOISE_1_0.py via augur_engine.engine) GATE: %s" % ("PASS" if gate_pass else "FAIL"))

# cross-check via tools/noise_research.py on the same sliced window
arrays_gate = load_master_arrays(master, date_from=None, date_to=DATE_TO_GATE)
trades_gate_gross, sigma_gate, sess_bounds_gate, fell_back_gate = nr.run_noise2(
    arrays_gate["open"], arrays_gate["high"], arrays_gate["low"], arrays_gate["close"],
    arrays_gate.get("volume"), arrays_gate["day_id"], **FROZEN_NR)
m_gate2 = nr.backtest_metrics(trades_gate_gross, FEE, MULT)
n_gate2 = m_gate2["num_trades"]; net_gate2 = m_gate2["net_usd"]; pf_gate2 = m_gate2["profit_factor"]; dd_gate2 = m_gate2["max_drawdown_usd"]
log("  cross-check tools/noise_research.py: n=%d net=$%s PF=%.4f DD=$%s (fell_back=%s)" %
    (n_gate2, format(net_gate2, ",.2f"), pf_gate2, format(dd_gate2, ",.2f"), fell_back_gate))
parity_pass = (n_gate2 == n_gate and abs(net_gate2 - net_gate) < 1.0 and abs(pf_gate2 - pf_gate) < 0.001 and abs(dd_gate2 - dd_gate) < 1.0)
log("  PARITY (engine plugin vs tools/noise_research.py): %s" % ("PASS" if parity_pass else "FAIL"))

if not (gate_pass and parity_pass):
    log("ABORT — SANITY GATE FAILED. Not proceeding to build the report.")
    sys.exit(1)
log("SANITY GATE: PASS (both engines agree, matches checkpoint numbers exactly)")

# ─────────────────────────────────────────────────────────────────────────
log("=" * 70)
log("STEP 2 — FULL HISTORY load + backtest, date_to=%s (source PINNED db_noadj_rth)" % DATE_TO_FULL)
t0 = time.time()
arrays = load_master_arrays(master, date_from=None, date_to=DATE_TO_FULL)
O = arrays["open"]; H = arrays["high"]; L = arrays["low"]; C = arrays["close"]
V = arrays.get("volume"); DID = arrays["day_id"]; IDX = arrays["index"]
n_bars = len(C)
log("  loaded arrays: %d bars, %s -> %s" % (n_bars, IDX[0], IDX[-1]))

trades_full_gross, sigma_full, sess_bounds_full, fell_back_full = nr.run_noise2(
    O, H, L, C, V, DID, **FROZEN_NR)
log("  run_noise2 elapsed %.1fs, gross trades=%d, sessions=%d, fell_back=%s" %
    (time.time() - t0, len(trades_full_gross), len(sess_bounds_full), fell_back_full))
m_full = nr.backtest_metrics(trades_full_gross, FEE, MULT)
net_trades_full = m_full["trades_net"]   # [(entry_bar, exit_bar, pnl_pts_net, pos, entry_px), ...] sorted by entry_bar
log("  FULL: n=%d net=$%s PF=%.4f DD=$%s" %
    (m_full["num_trades"], format(m_full["net_usd"], ",.2f"), m_full["profit_factor"], format(m_full["max_drawdown_usd"], ",.2f")))

# cross-check against the house engine plugin over the SAME full window (extra parity, best-effort)
r_full_eng = eng_bt("NOISE_1_0.py", instrument=INSTRUMENT, timeframe=TIMEFRAME, session=SESSION,
                     source=SOURCE, cost_pts=FEE, date_to=DATE_TO_FULL, params=FROZEN)
if r_full_eng:
    n_full_eng = r_full_eng["num_trades"]; net_full_eng = r_full_eng["total_pnl"] * MULT
    log("  cross-check via engine plugin (full window): n=%d net=$%s" % (n_full_eng, format(net_full_eng, ",.2f")))
    full_parity = (n_full_eng == m_full["num_trades"] and abs(net_full_eng - m_full["net_usd"]) < 1.0)
    log("  FULL-WINDOW PARITY: %s" % ("PASS" if full_parity else "FAIL (non-fatal, using tools/noise_research.py numbers)"))

# ─────────────────────────────────────────────────────────────────────────
log("STEP 3 — build per-trade records (entry/exit timestamps+prices)")
log("  NOTE: exit price is reconstructed via cost-inversion (exit = entry +/- (net_pnl+cost_pts)),")
log("  which is the EXACT fill price the engine's sim used (see run_noise2 _simulate_session:")
log("  pnl = (ex_px-entry_px) if long else (entry_px-ex_px), so ex_px inverts exactly). A naive")
log("  is-this-the-last-bar-of-session=>close heuristic is WRONG: a VWAP-cross signal from the")
log("  PENULTIMATE bar's close can defer its fill to the last bar's OPEN (STEP A fires before")
log("  STEP E's EOD-close backstop) -- verified this the hard way (one trade showed an 85.5pt")
log("  mismatch under the heuristic; the reconstructed price matched that bar's OPEN exactly).")

# last-bar-of-session lookup: used only as an informational QA check below, never authoritative.
last_bar_of_session = np.zeros(n_bars, dtype=bool)
for (a, b) in sess_bounds_full:
    last_bar_of_session[b - 1] = True

records = []
qa_mismatches = 0
for (entry_bar, exit_bar, pnl_pts_net, pos, entry_px) in net_trades_full:
    entry_time = IDX[entry_bar]
    exit_time = IDX[exit_bar]
    side = "long" if pos > 0 else "short"
    gross = float(pnl_pts_net) + FEE
    exit_px = float(entry_px) + gross if pos > 0 else float(entry_px) - gross
    # QA (informational only): reconstructed exit price should equal either that bar's
    # OPEN or its CLOSE (the only two possible fill prices under vwap-exit, no boundary mode).
    ok = (abs(exit_px - float(O[exit_bar])) < 0.02) or (abs(exit_px - float(C[exit_bar])) < 0.02)
    if not ok:
        qa_mismatches += 1
    pnl_usd = float(pnl_pts_net) * MULT
    records.append({
        "entry_bar": int(entry_bar), "exit_bar": int(exit_bar),
        "entry_time": entry_time, "exit_time": exit_time,
        "entry_date": entry_time.date(), "side": side,
        "entry_px": round(float(entry_px), 2), "exit_px": round(exit_px, 2),
        "pnl_pts": round(float(pnl_pts_net), 4), "pnl_usd": round(pnl_usd, 2),
        "holding_bars": int(exit_bar - entry_bar),
        "session_idx": int(DID[entry_bar]),
    })
log("  QA: exit price matches bar OPEN or CLOSE for %d/%d trades (mismatches=%d)" %
    (len(records) - qa_mismatches, len(records), qa_mismatches))
log("  total records built: %d" % len(records))
if qa_mismatches:
    log("  WARNING: %d trades' exit price matched neither OPEN nor CLOSE of the exit bar." % qa_mismatches)

# ─────────────────────────────────────────────────────────────────────────
log("STEP 4 — split pre-lockbox vs sealed-year")
pre_trades = [t for t in records if t["entry_date"] <= date.fromisoformat(DATE_TO_GATE)]
sealed_trades = [t for t in records if date.fromisoformat(LOCKBOX_START) <= t["entry_date"] <= date.fromisoformat(DATE_TO_FULL)]
log("  pre-lockbox: n=%d (expected 3147)" % len(pre_trades))
log("  sealed-year: n=%d (expected 242)" % len(sealed_trades))
pre_net = sum(t["pnl_usd"] for t in pre_trades)
sealed_net = sum(t["pnl_usd"] for t in sealed_trades)
log("  pre-lockbox net=$%s (expected $254,382.98)" % format(pre_net, ",.2f"))
log("  sealed-year net=$%s" % format(sealed_net, ",.2f"))

if len(pre_trades) != EXPECTED_GATE["n"] or abs(pre_net - EXPECTED_GATE["net"]) > 1.0:
    log("WARNING: pre-lockbox subset of the full-history run does not exactly match the gate run. Investigate before trusting downstream charts.")

save_checkpoint = dict(
    gate=dict(n=n_gate, net=net_gate, pf=pf_gate, dd=dd_gate, pass_=gate_pass, parity_pass=parity_pass),
    pre_n=len(pre_trades), pre_net=pre_net, sealed_n=len(sealed_trades), sealed_net=sealed_net,
)
with open(os.path.join(SCRATCH, "_gate_checkpoint.json"), "w") as f:
    json.dump(save_checkpoint, f, indent=2, default=str)

log("STEP 1-4 DONE.")


# ─────────────────────────────────────────────────────────────────────────
def iso(ts):
    return ts.isoformat()


def summarize(trades):
    n = len(trades)
    if n == 0:
        return dict(n=0, net_usd=0.0, pf=None, win_rate=0.0, max_dd_usd=0.0, mar=None,
                    avg_win=0.0, avg_loss=0.0, wins=0, losses=0)
    pnls = [t["pnl_usd"] for t in trades]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    gw = sum(wins); gl = -sum(losses)
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    net = sum(pnls)
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    dd = float((cum - peak).min()) if len(cum) else 0.0
    mar = (net / abs(dd)) if abs(dd) > 1e-9 else None
    return dict(n=n, net_usd=round(net, 2), pf=round(pf, 4) if np.isfinite(pf) else None,
                win_rate=round(100.0 * len(wins) / n, 2), max_dd_usd=round(dd, 2),
                mar=round(mar, 4) if mar is not None else None,
                avg_win=round(np.mean(wins), 2) if wins else 0.0,
                avg_loss=round(np.mean(losses), 2) if losses else 0.0,
                wins=len(wins), losses=len(losses))


log("STEP 5 — headline stats (pre-lockbox vs sealed-year)")
headline_pre = summarize(pre_trades)
headline_sealed = summarize(sealed_trades)
log("  pre-lockbox: %s" % headline_pre)
log("  sealed-year: %s" % headline_sealed)

# ─────────────────────────────────────────────────────────────────────────
log("STEP 6 — full-history equity curve + drawdown (downsampled to <=1500 pts)")
all_sorted = records  # already sorted by entry_bar == chronological
n_all = len(all_sorted)
pnl_arr = np.array([t["pnl_usd"] for t in all_sorted])
cum_arr = np.cumsum(pnl_arr)
peak_arr = np.maximum.accumulate(cum_arr)
dd_arr = cum_arr - peak_arr

lockbox_start_i = next((i for i, t in enumerate(all_sorted) if t["entry_date"] >= date.fromisoformat(LOCKBOX_START)), n_all)
log("  first sealed-year trade at sequence index %d / %d" % (lockbox_start_i, n_all))

# markers: worst sealed-year trade + all-time worst trade
sealed_worst = min(sealed_trades, key=lambda t: t["pnl_usd"])
alltime_worst = min(all_sorted, key=lambda t: t["pnl_usd"])
log("  sealed-year worst trade: %s $%.2f  (task said -$7,005.66 on 2026-06-25)" % (sealed_worst["entry_date"], sealed_worst["pnl_usd"]))
log("  all-time worst trade:    %s $%.2f  (task said -$15,465.66 on 2025-04-07)" % (alltime_worst["entry_date"], alltime_worst["pnl_usd"]))
worst_i = next(i for i, t in enumerate(all_sorted) if t is sealed_worst)
alltime_worst_i = next(i for i, t in enumerate(all_sorted) if t is alltime_worst)

MAX_PTS = 1500
if n_all <= MAX_PTS:
    keep_idx = list(range(n_all))
else:
    stride_idx = set(int(x) for x in np.linspace(0, n_all - 1, MAX_PTS).round().astype(int))
    # always keep exact special points: start, end, lockbox boundary, dd trough/peak, both worst-trade markers
    dd_trough_i = int(np.argmin(dd_arr))
    peak_i = int(np.argmax(cum_arr))
    for extra in (0, n_all - 1, lockbox_start_i, max(lockbox_start_i - 1, 0), dd_trough_i, peak_i, worst_i, alltime_worst_i):
        stride_idx.add(int(extra))
    keep_idx = sorted(stride_idx)
log("  equity curve points kept: %d (of %d trades)" % (len(keep_idx), n_all))

equity_full_points = [{"i": i, "date": str(all_sorted[i]["entry_date"]), "cum": round(float(cum_arr[i]), 2)} for i in keep_idx]
drawdown_full_points = [{"i": i, "date": str(all_sorted[i]["entry_date"]), "dd": round(float(dd_arr[i]), 2)} for i in keep_idx]

# ─────────────────────────────────────────────────────────────────────────
log("STEP 7 — sealed-year equity curve (full resolution, 242 pts)")
sealed_pnl = np.array([t["pnl_usd"] for t in sealed_trades])
sealed_cum = np.cumsum(sealed_pnl)
equity_sealed_points = [{"i": i, "date": str(sealed_trades[i]["entry_date"]), "cum": round(float(sealed_cum[i]), 2)}
                         for i in range(len(sealed_trades))]

log("STEP 8 — sealed-year monthly net $ (2025-07 -> 2026-06)")
months = pd.period_range("2025-07", "2026-06", freq="M")
sealed_monthly = []
for p in months:
    key = str(p)
    net = sum(t["pnl_usd"] for t in sealed_trades if t["entry_time"].strftime("%Y-%m") == key)
    sealed_monthly.append({"month": key, "net_usd": round(net, 2)})
log("  %s" % sealed_monthly)

log("STEP 9 — per-year net $ (2010-2026), full history")
years = sorted(set(t["entry_time"].year for t in all_sorted))
per_year = []
for y in years:
    net = sum(t["pnl_usd"] for t in all_sorted if t["entry_time"].year == y)
    n_y = sum(1 for t in all_sorted if t["entry_time"].year == y)
    per_year.append({"year": y, "net_usd": round(net, 2), "n": n_y})
log("  years: %s" % years)

log("STEP 10 — where it trades (full history)")
# (a) entry time-of-day histogram, 5-min buckets 09:30-16:00
buckets = []
tt = pd.Timestamp("2000-01-01 09:30:00")
end_tt = pd.Timestamp("2000-01-01 16:00:00")
while tt <= end_tt:
    buckets.append(tt.strftime("%H:%M"))
    tt += pd.Timedelta(minutes=5)
bucket_count = {b: 0 for b in buckets}
bucket_sum = {b: 0.0 for b in buckets}
for t in all_sorted:
    hm = t["entry_time"].strftime("%H:%M")
    if hm in bucket_count:
        bucket_count[hm] += 1
        bucket_sum[hm] += t["pnl_usd"]
    else:
        log("  WARNING: entry time %s outside 09:30-16:00 bucket range" % hm)
tod_histogram = [{"bucket": b, "count": bucket_count[b],
                   "net_usd": round(bucket_sum[b], 2),
                   "avg_usd": round(bucket_sum[b] / bucket_count[b], 2) if bucket_count[b] else 0.0}
                  for b in buckets]

# (b) long vs short
long_trades = [t for t in all_sorted if t["side"] == "long"]
short_trades = [t for t in all_sorted if t["side"] == "short"]
long_short = {
    "long": {"n": len(long_trades), "net_usd": round(sum(t["pnl_usd"] for t in long_trades), 2),
             "win_rate": round(100.0 * sum(1 for t in long_trades if t["pnl_usd"] > 0) / len(long_trades), 2) if long_trades else 0.0},
    "short": {"n": len(short_trades), "net_usd": round(sum(t["pnl_usd"] for t in short_trades), 2),
              "win_rate": round(100.0 * sum(1 for t in short_trades if t["pnl_usd"] > 0) / len(short_trades), 2) if short_trades else 0.0},
}
log("  long/short: %s" % long_short)

# (c) holding time histogram (bars), cap tail at 20+
hold_cap = 20
hold_count = {i: 0 for i in range(hold_cap + 1)}
for t in all_sorted:
    hb = min(t["holding_bars"], hold_cap)
    hold_count[hb] += 1
holding_hist = [{"bars": (str(i) if i < hold_cap else "%d+" % hold_cap), "count": hold_count[i]} for i in range(hold_cap + 1)]

# (d) trade pnl distribution histogram, $500 wide bins
bin_w = 500.0
pnl_all = np.array([t["pnl_usd"] for t in all_sorted])
lo = np.floor(pnl_all.min() / bin_w) * bin_w
hi = np.ceil(pnl_all.max() / bin_w) * bin_w
edges = np.arange(lo, hi + bin_w, bin_w)
counts, _ = np.histogram(pnl_all, bins=edges)
pnl_hist = [{"lo": round(float(edges[i]), 2), "hi": round(float(edges[i + 1]), 2), "count": int(counts[i])}
            for i in range(len(counts))]
log("  pnl histogram bins: %d (width $%.0f, range $%.0f..$%.0f)" % (len(pnl_hist), bin_w, lo, hi))

log("STEP 5-10 DONE.")


# ─────────────────────────────────────────────────────────────────────────
log("=" * 70)
log("STEP 11 — price-action panels: pick 6 representative SEALED-YEAR trades")

sealed_sorted_pnl = sorted(sealed_trades, key=lambda t: t["pnl_usd"])
biggest_loser = sealed_sorted_pnl[0]
biggest_winner = sealed_sorted_pnl[-1]
winners = sorted([t for t in sealed_trades if t["pnl_usd"] > 0], key=lambda t: t["pnl_usd"])
losers = sorted([t for t in sealed_trades if t["pnl_usd"] < 0], key=lambda t: t["pnl_usd"])  # most-negative first

nw = len(winners)
mid_w = nw // 2
w_idx = sorted({max(0, min(nw - 1, mid_w - 1)), max(0, min(nw - 1, mid_w))})
median_winners = [winners[i] for i in w_idx][:2]
if len(median_winners) < 2 and nw >= 2:
    median_winners = winners[mid_w - 1:mid_w + 1]

nl = len(losers)
mid_l = nl // 2
l_idx = sorted({max(0, min(nl - 1, mid_l - 1)), max(0, min(nl - 1, mid_l))})
median_losers = [losers[i] for i in l_idx][:2]
if len(median_losers) < 2 and nl >= 2:
    median_losers = losers[mid_l - 1:mid_l + 1]

log("  biggest winner:  %s %s $%.2f" % (biggest_winner["entry_date"], biggest_winner["side"], biggest_winner["pnl_usd"]))
log("  biggest loser:   %s %s $%.2f" % (biggest_loser["entry_date"], biggest_loser["side"], biggest_loser["pnl_usd"]))
log("  n winners=%d (median idx %s), n losers=%d (median idx %s)" % (nw, w_idx, nl, l_idx))
for w in median_winners:
    log("  median winner:   %s %s $%.2f" % (w["entry_date"], w["side"], w["pnl_usd"]))
for l_ in median_losers:
    log("  median loser:    %s %s $%.2f" % (l_["entry_date"], l_["side"], l_["pnl_usd"]))

chosen = [
    ("biggest_winner", biggest_winner),
    ("biggest_loser", biggest_loser),
    ("median_winner_1", median_winners[0]),
    ("median_winner_2", median_winners[1]),
    ("median_loser_1", median_losers[0]),
    ("median_loser_2", median_losers[1]),
]
# dedupe safety (shouldn't trigger with 242 sealed trades / ~90 winners / ~150 losers)
seen_ids = set()
for cat, t in chosen:
    key = (t["entry_bar"], t["exit_bar"])
    if key in seen_ids:
        log("  WARNING: duplicate trade chosen for category %s — %s" % (cat, t))
    seen_ids.add(key)

panels = []
for cat, tr in chosen:
    si = tr["session_idx"]
    a, b = sess_bounds_full[si]
    m = b - a
    sigma_row = sigma_full[si, :]
    prev_close = float(C[sess_bounds_full[si - 1][1] - 1])
    ref_hi = max(float(O[a]), prev_close)
    ref_lo = min(float(O[a]), prev_close)
    with np.errstate(invalid="ignore"):
        UB = ref_hi * (1.0 + 1.5 * sigma_row[:m])
        LB = ref_lo * (1.0 - 1.5 * sigma_row[:m])
    typical = (H[a:b] + L[a:b] + C[a:b]) / 3.0
    cum_tpv = np.cumsum(typical * V[a:b])
    cum_v = np.cumsum(V[a:b])
    with np.errstate(invalid="ignore", divide="ignore"):
        VWAP = cum_tpv / cum_v

    bars = []
    for k in range(m):
        bars.append({
            "t": iso(IDX[a + k]), "o": round(float(O[a + k]), 2), "h": round(float(H[a + k]), 2),
            "l": round(float(L[a + k]), 2), "c": round(float(C[a + k]), 2), "v": float(V[a + k]),
        })
    ub_list = [None if np.isnan(x) else round(float(x), 2) for x in UB]
    lb_list = [None if np.isnan(x) else round(float(x), 2) for x in LB]
    vwap_list = [None if np.isnan(x) else round(float(x), 2) for x in VWAP]

    entry_local = tr["entry_bar"] - a
    exit_local = tr["exit_bar"] - a
    # verification: entry/exit price should equal the bar's open (or close, for exit)
    ok_entry = abs(bars[entry_local]["o"] - tr["entry_px"]) < 0.02
    ok_exit = (abs(bars[exit_local]["o"] - tr["exit_px"]) < 0.02) or (abs(bars[exit_local]["c"] - tr["exit_px"]) < 0.02)
    if not (ok_entry and ok_exit):
        log("  WARNING panel %s: marker/bar price mismatch (entry ok=%s, exit ok=%s)" % (cat, ok_entry, ok_exit))

    panels.append({
        "category": cat,
        "date": str(tr["entry_date"]),
        "side": tr["side"],
        "entry_time": iso(tr["entry_time"]), "exit_time": iso(tr["exit_time"]),
        "entry_px": tr["entry_px"], "exit_px": tr["exit_px"],
        "pnl_usd": tr["pnl_usd"], "pnl_pts": tr["pnl_pts"],
        "holding_bars": tr["holding_bars"],
        "session_open": iso(IDX[a]), "session_close": iso(IDX[b - 1]),
        "entry_bar_local": entry_local, "exit_bar_local": exit_local,
        "bars": bars, "ub": ub_list, "lb": lb_list, "vwap": vwap_list,
    })
    log("  panel built: %-16s %s %-5s entry %s@%.2f -> exit %s@%.2f  net $%.2f  (%d bars in session)" %
        (cat, tr["entry_date"], tr["side"], tr["entry_time"].strftime("%H:%M"), tr["entry_px"],
         tr["exit_time"].strftime("%H:%M"), tr["exit_px"], tr["pnl_usd"], m))

log("STEP 11 DONE — %d panels built." % len(panels))

# ─────────────────────────────────────────────────────────────────────────
log("=" * 70)
log("STEP 12 — assemble final JSON")

out = {
    "meta": {
        "generated_at": datetime.now().isoformat(),
        "strategy": "NOISE 1.0",
        "engine": "tools/noise_research.py run_noise2 (cross-validated against augur_engine.engine.run_backtest + augur_strategies/NOISE_1_0.py)",
        "instrument": INSTRUMENT, "timeframe": TIMEFRAME, "session": SESSION, "source": SOURCE,
        "cost_pts": FEE, "mult_usd_per_pt": MULT,
        "config": FROZEN,
        "date_range_full": {"from": str(IDX[0].date()), "to": str(IDX[-1].date())},
        "gate_date_to": DATE_TO_GATE, "lockbox_start": LOCKBOX_START, "lockbox_end": DATE_TO_FULL,
        "note": "Lockbox is SPENT (this sealed-year read is a one-shot, pre-registered). NOISE 1.0 has NO hard stop — the vwap exit is the only risk control.",
    },
    "sanity_gate": {
        "pass": bool(gate_pass and parity_pass),
        "engine_result": {"n": n_gate, "net_usd": round(net_gate, 2), "pf": round(pf_gate, 4), "max_dd_usd": round(dd_gate, 2)},
        "research_script_result": {"n": n_gate2, "net_usd": round(net_gate2, 2), "pf": round(pf_gate2, 4), "max_dd_usd": round(dd_gate2, 2)},
        "expected": EXPECTED_GATE,
    },
    "headline": {"pre_lockbox": headline_pre, "sealed_year": headline_sealed},
    "equity_full": {"points": equity_full_points, "n_trades_total": n_all,
                     "lockbox_start_index": lockbox_start_i, "downsampled": n_all > MAX_PTS},
    "drawdown_full": {"points": drawdown_full_points},
    "markers": {
        "sealed_worst": {"date": str(sealed_worst["entry_date"]), "pnl_usd": sealed_worst["pnl_usd"],
                          "seq_index": worst_i, "side": sealed_worst["side"],
                          "entry_time": iso(sealed_worst["entry_time"]), "exit_time": iso(sealed_worst["exit_time"])},
        "alltime_worst": {"date": str(alltime_worst["entry_date"]), "pnl_usd": alltime_worst["pnl_usd"],
                           "seq_index": alltime_worst_i, "side": alltime_worst["side"],
                           "entry_time": iso(alltime_worst["entry_time"]), "exit_time": iso(alltime_worst["exit_time"])},
    },
    "equity_sealed": {"points": equity_sealed_points},
    "sealed_monthly": sealed_monthly,
    "per_year": per_year,
    "tod_histogram": tod_histogram,
    "long_short": long_short,
    "holding_hist": holding_hist,
    "pnl_hist": pnl_hist,
    "panels": panels,
    "schema_notes": {
        "equity_full.points[].cum": "chart 1 — full-history equity curve (cumulative net $, x = trade sequence)",
        "drawdown_full.points[].dd": "chart 1 — underwater sub-pane beneath the equity curve",
        "equity_full.lockbox_start_index": "chart 1 — x-index where the LOCKBOX YEAR shading begins",
        "markers.sealed_worst / markers.alltime_worst": "chart 1 — the two labelled worst-trade dots",
        "equity_sealed.points[].cum": "chart 2 — sealed-year-only equity curve (242 trades, full resolution)",
        "sealed_monthly": "chart 2 — sealed-year monthly net $ bars (2025-07 .. 2026-06)",
        "per_year": "chart 3 — per-year net $ bars (2010-2026)",
        "tod_histogram": "chart 4a — entry time-of-day histogram (count bars) + avg $/trade line overlay",
        "long_short": "chart 4b — long vs short counts/net $",
        "holding_hist": "chart 4c — holding-time-in-bars histogram",
        "pnl_hist": "chart 4d — trade PnL distribution histogram",
        "panels[]": "charts 5.1-5.6 — one candlestick session panel per chosen sealed-year trade (bars/ub/lb/vwap/entry-exit markers)",
    },
}

json_path = os.path.join(SCRATCH, "noise_visual_data.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1, default=str)
sz = os.path.getsize(json_path)
log("  wrote %s (%.1f KB)" % (json_path, sz / 1024.0))

log("ALL STEPS DONE.")
log("=" * 70)
log("SUMMARY")
log("  sanity gate: %s" % ("PASS" if out["sanity_gate"]["pass"] else "FAIL"))
log("  pre-lockbox: n=%d net=$%s PF=%s DD=$%s" % (headline_pre["n"], format(headline_pre["net_usd"], ",.2f"), headline_pre["pf"], format(headline_pre["max_dd_usd"], ",.2f")))
log("  sealed-year: n=%d net=$%s PF=%s DD=$%s" % (headline_sealed["n"], format(headline_sealed["net_usd"], ",.2f"), headline_sealed["pf"], format(headline_sealed["max_dd_usd"], ",.2f")))
log("  6 chosen panels:")
for p in panels:
    log("    %-16s %s %-5s $%s" % (p["category"], p["date"], p["side"], format(p["pnl_usd"], ",.2f")))
