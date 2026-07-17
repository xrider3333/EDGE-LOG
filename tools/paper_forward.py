# tools/paper_forward.py — ENGU-Q paper-forward Phase 1: dual-leg signal tracker.
#
# LOGGING ONLY. No orders, no money, no broker calls. This tool runs the two
# deploy-config legs (ENGUQ 1m trendline-break + ORB 3.1 scale-out) as a full
# backtest against the current masters, then treats any trade whose entry is on
# or after PAPER_START as a "paper" (forward) signal and appends it to a durable,
# append-only CSV log outside the repo, plus rewrites a human-readable status
# page each run.
#
# HOW MASTERS GET REFRESHED (see status page "Data refresh" section for detail):
#   The always-on background runner (run_edgelog_hidden.vbs -> api.runner --watch)
#   is launched with --refresh-min 0, which explicitly DISABLES its master
#   auto-refresh — so masters do NOT self-update just because the runner is
#   running. To bring them current: open the Streamlit app (optimizer.py), which
#   runs auto_refresh_masters() on open (Yahoo + TradingView watch-folder ingest);
#   or headless or run tools/refresh_noadj_yahoo.py directly, which is the exact
#   script that extends the NOADJ_NQ_1m_RTH.csv / NOADJ_NQ_5m_RTH.csv masters
#   these two legs use (find_master() resolves to the 'db_noadj_rth' source for
#   both instrument+timeframe pairs; that source is what refresh_noadj_yahoo.py
#   targets: `source LIKE 'db_noadj%'`).
#
# VIX: no local VIX CSV exists anywhere in this repo or in Trading/ENGUQ_DB. The
# only VIX access found in this project (scratchpad enguq_vix_lab.py /
# taskB_vix.py, both one-off research scripts) pulls ^VIX from yfinance over the
# internet. Per this tool's design, it must NEVER fetch from the internet, so
# vix_close is always logged blank with a note. If a local VIX CSV shows up later
# (e.g. a master registered the normal AUGUR way), wire it into get_vix_close().
#
# CLI:  python tools/paper_forward.py [--dry-run]
import argparse
import os
import sys
import datetime as dt

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_strategies import ENGUQ_1M_1_0 as _engu_mod                 # noqa: E402
from augur_strategies import ORB_3_1 as _orb_mod                       # noqa: E402

# ── Config ───────────────────────────────────────────────────────────────────
PAPER_START = "2026-07-16"
REBASELINE_CUTOFF = "2026-07-01"   # parity re-check uses trades EXITING before this (human-facing label)
# The exact last bar of the pre-2026-07-17-backfill frozen masters that produced baseline_n/
# baseline_net below (NQ 1m/5m RTH masters were frozen mid-session at this timestamp, then
# extended through 2026-07-16 on 2026-07-17). A position still open exactly at this bar was
# captured in the frozen baseline as a SYNTHETIC mark-to-close there (run_backtest's own
# "still open at data end" fallback), not a real exit — see FREEZE-boundary handling in
# process_leg() below.
FREEZE_TS = pd.Timestamp("2026-06-30 10:50:00", tz="US/Eastern")
GAP_PCT_RULE = 0.02                # ENGUQ deployment rule: skip entries on a >2% gap session
COST_PTS = 0.533
MULT = 20.0

DB_DIR    = r"C:\Users\xride\OneDrive\Desktop\Trading\ENGUQ_DB"
LOG_CSV   = os.path.join(DB_DIR, "paper_forward_log.csv")
STATUS_MD = os.path.join(DB_DIR, "paper_forward_status.md")

LOG_COLUMNS = ["logged_at", "leg", "event", "entry_time", "entry_px", "stop_px",
               "exit_time", "exit_px", "pnl_pts", "pnl_usd", "vix_close", "note"]

VIX_NOTE = "vix_close n/a (no local VIX source found; internet fetch disallowed by design)"

# Deploy-config legs. Params are the exact deploy configs the owner locked in.
LEGS = {
    "ENGUQ_1M": dict(
        module=_engu_mod, instrument="NQ", timeframe="1m", session="rth",
        params=dict(buf_atr=0.9, ema_len=390, tl_len=48, stop_mult=1.0,
                    trail_frac=2.5, min_brk=1.3, vol_mult=0.8, atr_len=30,
                    act_R=2.5, breakeven_R=1.5),
        baseline_n=2048, baseline_net=474710.82,
        gap_rule=True,
    ),
    "ORB_31": dict(
        module=_orb_mod, instrument="NQ", timeframe="5m", session="rth",
        params=dict(or_bars=1, stop_frac=0.75, vol_filter=1.25,
                    partial_exit_R=0, trail_bars=5),
        baseline_n=4064, baseline_net=360640.26,
        gap_rule=False,
    ),
}

# 1:1 ORB x ENGU-Q blend baseline (book-baseline per owner; see memory
# edgelog-blend-hold.md) — used only to state an expected run-rate for comparison.
BLEND_NET_TOTAL = 835351.08
BLEND_START = "2010-06-07"
BLEND_END   = "2026-06-30"


# ── Data / VIX helpers ──────────────────────────────────────────────────────
def load_leg_master(cfg):
    m = find_master(cfg["instrument"], cfg["timeframe"], cfg["session"])
    if m is None:
        raise RuntimeError(
            f"no master registered for {cfg['instrument']} {cfg['timeframe']} "
            f"{cfg['session']} — run tools/refresh_noadj_yahoo.py or open optimizer.py "
            f"to build/refresh it before running paper_forward.py.")
    path = os.path.join(ROOT, "augur_uploads", m["filename"])
    if not os.path.exists(path):
        raise RuntimeError(f"master row found ({m['filename']}) but the CSV file is "
                            f"missing on disk at {path}.")
    arr = load_master_arrays(m)
    return m, arr


def get_vix_close(_date):
    """Best-effort local VIX lookup. No local source exists (see module docstring),
    so this always returns (None, note) and NEVER hits the network."""
    return None, VIX_NOTE


# ── Backtest + trade classification ─────────────────────────────────────────
def run_leg_backtest(cfg, arr):
    mod = cfg["module"]
    kwargs = dict(opens=arr["open"], highs=arr["high"], lows=arr["low"], closes=arr["close"],
                  volumes=arr["volume"], day_id=arr["day_id"], return_trades=True)
    kwargs.update(cfg["params"])
    return mod.run_backtest(**kwargs)


def _implied_exit_px(t):
    _entry_bar, _exit_bar, pnl, side, entry_px = t
    return entry_px + pnl if side > 0 else entry_px - pnl


def is_open_trade(t, closes):
    """True iff this trade tuple is really a still-open position marked-to-market
    at the last bar, rather than a genuine stop/target/EOD exit that happens to
    land on the last bar. Detected by: exit_bar is the very last bar AND the
    implied exit price equals that bar's close exactly (a real stop/EOD fill
    price only equals the raw close by pure coincidence; the engine's own
    "still open at data end" fallback path always uses c[-1] as the fill)."""
    _entry_bar, exit_bar, _pnl, _side, _entry_px = t
    n = len(closes)
    if exit_bar != n - 1:
        return False
    return abs(_implied_exit_px(t) - closes[-1]) < 1e-6


def reconstruct_stop(leg_name, cfg, arr, entry_bar):
    """Reconstruct the CURRENT live stop for an open position, replaying the
    strategy's own trail/breakeven logic bar-by-bar from entry to the last bar.
    Returns (stop_px_or_None, note)."""
    if leg_name == "ENGUQ_1M":
        o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
        p = cfg["params"]
        tl_len = int(p["tl_len"]); stop_mult = p["stop_mult"]; act_R = p["act_R"]
        trail_frac = p["trail_frac"]; breakeven_R = p.get("breakeven_R", 0.0)
        ep = c[entry_bar]
        swing_low = l[entry_bar - tl_len: entry_bar + 1].min()
        risk = ep - swing_low
        sl = ep - stop_mult * risk
        act = False
        n = len(c)
        # Mirrors ENGUQ_1M_1_0.run_backtest's position-management block exactly
        # (activate -> trail -> breakeven, evaluated in that order each bar). We
        # do not re-check the l[i]<=sl exit condition: the engine already told us
        # this position is still open through bar n-1, so it never fired.
        for i in range(entry_bar + 1, n):
            if h[i] - ep >= act_R * risk:
                act = True
            if act:
                sl = max(sl, h[i] - trail_frac * risk)
            if breakeven_R > 0 and (h[i] - ep) >= breakeven_R * risk:
                sl = max(sl, ep)
        return sl, ("stop reconstructed by replaying ENGUQ_1M_1_0's trail/breakeven "
                     "logic bar-by-bar from entry to the last bar.")
    # ORB_31 (and anything else): flat_eod=True in this leg's config always flattens
    # by session close, so the strategy itself has no "open position" concept — a
    # trade landing on the data boundary is a genuine (if data-truncated) EOD exit,
    # not a carry. is_open_trade() should never fire true for it; this is a defensive
    # fallback only.
    return None, ("no live-stop reconstruction implemented for this leg: its own "
                   "run_backtest always flattens positions by session close "
                   "(flat_eod=True), so an 'open at data end' reading would be a "
                   "backtest artifact, not a real carry.")


def compute_gap_sessions(arr):
    """Per-session RTH-open-vs-prior-RTH-close gap, computed straight from the
    master. Returns dict day_id -> {date, gap_pct, is_gap}."""
    day_id, opens, closes, idx = arr["day_id"], arr["open"], arr["close"], arr["index"]
    n = len(day_id)
    sessions = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        sessions.append((a, b))
        a = b
    out = {}
    prev_close = None
    for (a, b) in sessions:
        did = int(day_id[a])
        date = idx[a].date()
        sess_open = float(opens[a])
        if prev_close is not None and prev_close != 0:
            gap_pct = (sess_open - prev_close) / prev_close
        else:
            gap_pct = None
        out[did] = dict(date=date, gap_pct=gap_pct,
                         is_gap=bool(gap_pct is not None and abs(gap_pct) > GAP_PCT_RULE))
        prev_close = float(closes[b - 1])
    return out


# ── Row building ─────────────────────────────────────────────────────────────
def _fmt_ts(ts):
    return "" if ts is None else ts.isoformat()


def _fmt_num(x, nd=2):
    return "" if x is None else round(float(x), nd)


def build_row(logged_at, leg, event, entry_time=None, entry_px=None, stop_px=None,
              exit_time=None, exit_px=None, pnl_pts=None, pnl_usd=None, note=""):
    full_note = f"{note}; {VIX_NOTE}" if note else VIX_NOTE
    return {
        "logged_at": logged_at, "leg": leg, "event": event,
        "entry_time": _fmt_ts(entry_time), "entry_px": _fmt_num(entry_px),
        "stop_px": _fmt_num(stop_px),
        "exit_time": _fmt_ts(exit_time), "exit_px": _fmt_num(exit_px),
        "pnl_pts": _fmt_num(pnl_pts), "pnl_usd": _fmt_num(pnl_usd),
        "vix_close": "", "note": full_note,
    }


def process_leg(leg_name, cfg, logged_at):
    """Runs the backtest, self-checks parity, classifies trades, and returns a
    result dict consumed by both the CSV-row builder and the status page."""
    res = {"leg": leg_name, "cfg": cfg}
    try:
        master, arr = load_leg_master(cfg)
    except RuntimeError as e:
        res["error"] = str(e)
        return res
    res["master"] = master
    res["last_bar"] = arr["index"][-1]
    res["first_bar"] = arr["index"][0]

    r = run_leg_backtest(cfg, arr)
    if r is None or not r.get("trades"):
        res["error"] = "backtest returned no trades for this leg's deploy config."
        return res

    trades = r["trades"]
    closes = arr["close"]; idx = arr["index"]
    n = len(closes)

    raw_n = len(trades)
    raw_net = round(sum((t[2] - COST_PTS) * MULT for t in trades), 2)

    open_trade = trades[-1] if is_open_trade(trades[-1], closes) else None
    closed_trades = trades[:-1] if open_trade is not None else list(trades)

    # ── Mandatory self-check: parity vs the frozen deploy-config baseline ────
    parity_status = "OK"
    parity_detail = ""
    if raw_n == cfg["baseline_n"] and abs(raw_net - cfg["baseline_net"]) < 0.01:
        parity_status = "OK"
        parity_detail = f"raw totals match baseline exactly (n={raw_n}, net=${raw_net:,.2f})."
    else:
        # Trades fully resolved strictly before FREEZE_TS are directly comparable to the
        # frozen baseline. A trade STRADDLING that boundary (entry before FREEZE_TS, exit
        # at/after it — i.e. it was still open when the old masters were frozen) was folded
        # into baseline_n/baseline_net as a SYNTHETIC mark-to-close at the freeze bar, not a
        # real exit. Reconstruct that same synthetic value from the (unchanged) historical
        # close at FREEZE_TS so resolving that position with more data doesn't read as drift.
        pre_trades = [t for t in closed_trades if idx[t[1]] < FREEZE_TS]
        pre_n = len(pre_trades)
        pre_net = sum((t[2] - COST_PTS) * MULT for t in pre_trades)

        straddlers = [t for t in trades if idx[t[0]] < FREEZE_TS <= idx[t[1]]]
        freeze_note = ""
        if straddlers:
            try:
                freeze_pos = idx.get_loc(FREEZE_TS)
                freeze_close = float(closes[freeze_pos])
                for (entry_bar, _exit_bar, _pnl, side, entry_px) in straddlers:
                    synth_pnl = (freeze_close - entry_px) if side > 0 else (entry_px - freeze_close)
                    pre_n += 1
                    pre_net += (synth_pnl - COST_PTS) * MULT
                freeze_note = (f" ({len(straddlers)} trade(s) open exactly at the {FREEZE_TS} freeze "
                                f"boundary reconstructed as the frozen baseline's synthetic mark-to-close.)")
            except KeyError:
                freeze_note = (f" (WARNING: {len(straddlers)} straddling trade(s) at the freeze boundary "
                                f"but FREEZE_TS bar not found in current data — reconstruction skipped.)")
        pre_net = round(pre_net, 2)

        if pre_n == cfg["baseline_n"] and abs(pre_net - cfg["baseline_net"]) < 0.01:
            parity_status = "ROLLED"
            parity_detail = (f"raw totals changed (master extended: n={raw_n}, net=${raw_net:,.2f}) "
                              f"but the pre-existing trade set (resolved as of the {FREEZE_TS} freeze "
                              f"boundary) is UNCHANGED: n={pre_n}, net=${pre_net:,.2f} — matches frozen "
                              f"baseline (n={cfg['baseline_n']}, net=${cfg['baseline_net']:,.2f})."
                              f"{freeze_note} Baseline rolled forward cleanly; no drift in historical trades.")
        else:
            parity_status = "FAIL"
            parity_detail = (f"PARITY FAILURE. Frozen baseline: n={cfg['baseline_n']}, "
                              f"net=${cfg['baseline_net']:,.2f}. Current raw: n={raw_n}, "
                              f"net=${raw_net:,.2f}. Current pre-freeze-boundary subset: "
                              f"n={pre_n}, net=${pre_net:,.2f}.{freeze_note} Even the historical "
                              f"(pre-freeze) trades changed — this is NOT explained by simply extending "
                              f"the master with new bars. Possible causes: master data was revised/"
                              f"re-pulled, strategy file edited, or params drifted. Investigate "
                              f"before trusting this leg's paper log.")

    res.update(raw_n=raw_n, raw_net=raw_net, parity_status=parity_status,
               parity_detail=parity_detail)

    # ── Gap-skip sessions (ENGUQ only) ────────────────────────────────────────
    gap_map = {}
    if cfg["gap_rule"]:
        gap_map = compute_gap_sessions(arr)
    paper_start_ts = pd.Timestamp(PAPER_START, tz="US/Eastern")
    paper_start_date = paper_start_ts.date()
    gap_sessions_since_start = sorted(
        [v for v in gap_map.values() if v["date"] >= paper_start_date and v["is_gap"]],
        key=lambda v: v["date"])
    gap_flagged_days = {did for did, v in gap_map.items() if v["is_gap"]}
    res["gap_sessions_since_start"] = gap_sessions_since_start

    rows, skip_gap_rows = [], []
    paper_pnl_usd = 0.0
    paper_trade_count = 0

    if parity_status != "FAIL":
        for t in closed_trades:
            entry_bar, exit_bar, pnl, side, entry_px = t
            entry_time = idx[entry_bar]
            if entry_time < paper_start_ts:
                continue  # historical trade, not a paper-forward signal
            exit_time = idx[exit_bar]
            exit_px = entry_px + pnl if side > 0 else entry_px - pnl
            if cfg["gap_rule"] and int(arr["day_id"][entry_bar]) in gap_flagged_days:
                g = gap_map[int(arr["day_id"][entry_bar])]
                note = (f"SKIP_GAP: entry session {g['date']} RTH open gapped "
                        f"{g['gap_pct']*100:+.2f}% from prior session's RTH close "
                        f"(deployment rule skips |gap|>{GAP_PCT_RULE*100:.0f}%).")
                skip_gap_rows.append(build_row(logged_at, leg_name, "SKIP_GAP",
                                                entry_time=entry_time, entry_px=entry_px, note=note))
                continue
            pnl_usd = round((pnl - COST_PTS) * MULT, 2)
            rows.append(build_row(logged_at, leg_name, "EXIT",
                                   entry_time=entry_time, entry_px=entry_px,
                                   exit_time=exit_time, exit_px=exit_px,
                                   pnl_pts=pnl, pnl_usd=pnl_usd))
            paper_pnl_usd += pnl_usd
            paper_trade_count += 1

        # ── Open position (if any) ────────────────────────────────────────────
        open_row = None
        res["open_position"] = None
        if open_trade is not None:
            entry_bar, _exit_bar, pnl, _side, entry_px = open_trade
            entry_time = idx[entry_bar]
            stop_px, stop_note = reconstruct_stop(leg_name, cfg, arr, entry_bar)
            unreal_usd = round((pnl - COST_PTS) * MULT, 2)
            mark_note = (f"unrealized mark-to-last-close {pnl:+.2f} pts (${unreal_usd:+,.2f} "
                         f"informational, cost-model applied) as of {idx[-1]}. {stop_note}")
            is_carry_in = entry_time < paper_start_ts
            if is_carry_in:
                note = f"CARRY_IN: pre-existing open position at first paper-forward run; excluded from paper PnL. {mark_note}"
                open_row = build_row(logged_at, leg_name, "CARRY_IN",
                                      entry_time=entry_time, entry_px=entry_px, stop_px=stop_px,
                                      pnl_pts=pnl, pnl_usd=unreal_usd, note=note)
                res["open_position"] = dict(entry_time=entry_time, entry_px=entry_px,
                                             stop_px=stop_px, stop_note=stop_note,
                                             unreal_pnl_pts=pnl, unreal_pnl_usd=unreal_usd,
                                             is_carry_in=True)
            elif cfg["gap_rule"] and int(arr["day_id"][entry_bar]) in gap_flagged_days:
                g = gap_map[int(arr["day_id"][entry_bar])]
                note = (f"SKIP_GAP: open-position entry session {g['date']} RTH open gapped "
                        f"{g['gap_pct']*100:+.2f}% from prior session's RTH close "
                        f"(deployment rule skips |gap|>{GAP_PCT_RULE*100:.0f}%); voided, not tracked.")
                skip_gap_rows.append(build_row(logged_at, leg_name, "SKIP_GAP",
                                                entry_time=entry_time, entry_px=entry_px, note=note))
                # voided by the gap rule — not a real position, so not surfaced as "open"
            else:
                note = f"ENTRY: open paper-forward position. {mark_note}"
                open_row = build_row(logged_at, leg_name, "ENTRY",
                                      entry_time=entry_time, entry_px=entry_px, stop_px=stop_px,
                                      note=note)
                res["open_position"] = dict(entry_time=entry_time, entry_px=entry_px,
                                             stop_px=stop_px, stop_note=stop_note,
                                             unreal_pnl_pts=pnl, unreal_pnl_usd=unreal_usd,
                                             is_carry_in=False)
        if open_row is not None:
            rows.append(open_row)

    rows.extend(skip_gap_rows)
    res["rows"] = rows
    res["paper_pnl_usd"] = paper_pnl_usd
    res["paper_trade_count"] = paper_trade_count
    res["skip_gap_count"] = len(skip_gap_rows)
    return res


# ── CSV append (idempotent) ──────────────────────────────────────────────────
def _existing_keys():
    if not os.path.exists(LOG_CSV):
        return set()
    df = pd.read_csv(LOG_CSV, dtype=str).fillna("")
    return set(zip(df["leg"], df["event"], df["entry_time"], df["exit_time"]))


def append_rows(rows):
    existing = _existing_keys()
    new_rows = []
    for r in rows:
        key = (r["leg"], r["event"], r["entry_time"], r["exit_time"])
        if key in existing:
            continue
        new_rows.append(r)
        existing.add(key)
    if new_rows:
        os.makedirs(DB_DIR, exist_ok=True)
        file_exists = os.path.exists(LOG_CSV)
        pd.DataFrame(new_rows, columns=LOG_COLUMNS).to_csv(
            LOG_CSV, mode="a", header=not file_exists, index=False)
    return new_rows


def preview_new_rows(rows):
    existing = _existing_keys()
    return [r for r in rows if (r["leg"], r["event"], r["entry_time"], r["exit_time"]) not in existing]


# ── Status page ───────────────────────────────────────────────────────────────
def _sessions_behind(last_bar_date, today_date):
    next_day = last_bar_date + pd.Timedelta(days=1)
    if next_day > today_date:
        return 0
    return len(pd.bdate_range(next_day, today_date))


def write_status_page(results, run_ts):
    today = pd.Timestamp(run_ts.date())
    lines = []
    P = lines.append
    P(f"# ENGU-Q Paper-Forward Status — Phase 1 (logging only, no orders)")
    P("")
    P(f"Run at: {run_ts.isoformat(timespec='seconds')}  |  PAPER_START = {PAPER_START}")
    P("")
    P("## Data freshness")
    any_stale = False
    for leg_name, res in results.items():
        if res.get("error"):
            P(f"- **{leg_name}**: ERROR — {res['error']}")
            continue
        last_bar = res["last_bar"]
        last_date = pd.Timestamp(last_bar.date())
        behind = _sessions_behind(last_date, today)
        m = res["master"]
        stale_flag = ""
        if behind > 2:
            any_stale = True
            stale_flag = f"  ⚠ STALE — {behind} weekday session(s) behind today ({today.date()})"
        P(f"- **{leg_name}** ({m['filename']}, {m['instrument']} {m['timeframe']} {m['session']}): "
          f"last bar **{last_bar}**{stale_flag}")
    P("")
    P("### How masters get refreshed")
    P("The always-on background runner (`run_edgelog_hidden.vbs` -> `api.runner --watch`) is "
      "launched with `--refresh-min 0`, which **explicitly disables** its own master "
      "auto-refresh (comment in the VBS: \"AUGUR does its own on open\") — so masters do **not** "
      "self-update just because the runner is running in the background.")
    P("")
    P("To bring these two masters (`NOADJ_NQ_1m_RTH.csv`, `NOADJ_NQ_5m_RTH.csv`) current:")
    P("- Open the Streamlit app (`streamlit run optimizer.py`) — it runs `auto_refresh_masters()` "
      "on open (Yahoo pull + TradingView watch-folder ingest), or")
    P("- Headless equivalent: `python tools/refresh_noadj_yahoo.py` — this is the exact script "
      "that extends the `db_noadj_rth`-sourced masters `find_master()` resolves to for both legs "
      "(Yahoo `NQ=F`, free, keeps the recent tail current; 1m ~7 day history limit, 5m ~60 day).")
    P("")
    if any_stale:
        P("⚠ **At least one master is stale.** Refresh before trusting paper-forward output for "
          "recent sessions.")
        P("")

    P("## Open positions")
    any_open = False
    for leg_name, res in results.items():
        op = res.get("open_position")
        if not op:
            continue
        any_open = True
        kind = "CARRY_IN (pre-existing, excluded from paper PnL)" if op["is_carry_in"] else "ENTRY (paper-forward position)"
        stop_str = f"{op['stop_px']:.2f}" if op["stop_px"] is not None else "n/a"
        P(f"- **{leg_name}** — {kind}")
        P(f"  entry {op['entry_time']} @ {op['entry_px']:.2f}  |  current stop **{stop_str}**")
        if op["stop_px"] is None:
            P(f"  (stop not reconstructed: {op['stop_note']})")
        P(f"  unrealized mark-to-last-close: {op['unreal_pnl_pts']:+.2f} pts "
          f"(${op['unreal_pnl_usd']:+,.2f}, cost-model applied, informational only)")
    if not any_open:
        P("- none")
    P("")

    P("## Paper-to-date PnL (trades entered on/after PAPER_START only)")
    combined = 0.0
    combined_n = 0
    for leg_name, res in results.items():
        if res.get("error"):
            continue
        n = res.get("paper_trade_count", 0)
        usd = res.get("paper_pnl_usd", 0.0)
        combined += usd; combined_n += n
        P(f"- **{leg_name}**: {n} paper trade(s), net **${usd:,.2f}**")
    P(f"- **Combined**: {combined_n} paper trade(s), net **${combined:,.2f}**")
    P("")

    P("## Expected run-rate (for comparison)")
    blend_start = pd.Timestamp(BLEND_START); blend_end = pd.Timestamp(BLEND_END)
    months = (blend_end - blend_start).days / 30.4368
    monthly = BLEND_NET_TOTAL / months
    P(f"1:1 ORB x ENGU-Q blend backtest (book baseline): net **${BLEND_NET_TOTAL:,.2f}** over "
      f"{BLEND_START} -> {BLEND_END} ({months:.1f} months) ≈ **${monthly:,.0f}/month**. Paper-to-date "
      f"totals above are not yet meaningful until enough paper trades accumulate to compare against "
      f"this run-rate.")
    P("")

    P("## Gap-skip events (ENGUQ deployment rule)")
    P(f"Rule: skip (don't count as a paper trade) any ENGUQ entry occurring on a session whose RTH "
      f"open gaps more than {GAP_PCT_RULE*100:.0f}% (either direction) from the prior session's RTH "
      f"close, computed directly from the ENGUQ 1m RTH master.")
    any_gap = False
    for leg_name, res in results.items():
        if not res.get("cfg", {}).get("gap_rule"):
            continue
        sess = res.get("gap_sessions_since_start", [])
        if sess:
            any_gap = True
            for g in sess:
                P(f"- {leg_name}: {g['date']} gap {g['gap_pct']*100:+.2f}%")
        skc = res.get("skip_gap_count", 0)
        if skc:
            any_gap = True
            P(f"- {leg_name}: {skc} entry(ies) actually voided as SKIP_GAP this run (see log CSV).")
    if not any_gap:
        P(f"- none since {PAPER_START} (masters currently only cover through "
          f"{min(r['last_bar'].date() for r in results.values() if r.get('last_bar')) if any(r.get('last_bar') for r in results.values()) else 'n/a'})")
    P("")

    P("## VIX column status")
    P(f"- {VIX_NOTE}")
    P("  Every log row's `vix_close` is blank. The only VIX access found anywhere in this project "
      "(`scratchpad/enguq_vix_lab.py`, `taskB_vix.py` — one-off research scripts) pulls `^VIX` from "
      "yfinance over the internet; this tool is not allowed to do that, so there is currently no "
      "way to fill this column without adding a local VIX data source (e.g. a registered AUGUR "
      "master built from a downloaded CSV).")
    P("")

    P("## Self-check (parity vs frozen deploy-config baseline)")
    for leg_name, res in results.items():
        if res.get("error"):
            P(f"- **{leg_name}**: N/A — {res['error']}")
            continue
        P(f"- **{leg_name}**: **{res['parity_status']}** — {res['parity_detail']}")
    P("")

    P("## How to run this tool")
    P("```")
    P("python tools/paper_forward.py            # real run: appends to the log, rewrites this page")
    P("python tools/paper_forward.py --dry-run   # preview only: writes nothing")
    P("```")
    P("")
    P("Suggested (NOT installed) daily scheduling one-liner — Windows Task Scheduler, run once each "
      "morning after masters are refreshed:")
    P("```")
    P('schtasks /Create /TN "ENGUQ Paper-Forward" /TR "python C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG\\tools\\paper_forward.py" /SC DAILY /ST 09:45 /F')
    P("```")
    P("")

    os.makedirs(DB_DIR, exist_ok=True)
    with open(STATUS_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="ENGU-Q paper-forward Phase 1 signal logger (no orders).")
    ap.add_argument("--dry-run", action="store_true",
                     help="print what would be appended; write nothing (no CSV, no status page).")
    args = ap.parse_args()

    run_ts = dt.datetime.now()
    logged_at = run_ts.isoformat(timespec="seconds")

    results = {}
    any_fail = False
    for leg_name, cfg in LEGS.items():
        res = process_leg(leg_name, cfg, logged_at)
        results[leg_name] = res
        if res.get("error"):
            print(f"[{leg_name}] ERROR: {res['error']}")
            any_fail = True
        else:
            print(f"[{leg_name}] parity: {res['parity_status']} — {res['parity_detail']}")
            if res["parity_status"] == "FAIL":
                any_fail = True

    all_rows = []
    for leg_name, res in results.items():
        if res.get("error") or res.get("parity_status") == "FAIL":
            continue
        all_rows.extend(res.get("rows", []))

    if args.dry_run:
        would_add = preview_new_rows(all_rows)
        print(f"\n=== DRY RUN: {len(would_add)} row(s) WOULD be appended to {LOG_CSV} ===")
        for r in would_add:
            print(r)
        if not would_add:
            print("  (none — nothing new)")
        print("=== DRY RUN: no files written ===")
        return 1 if any_fail else 0

    new_rows = append_rows(all_rows)
    print(f"\nAppended {len(new_rows)} new row(s) to {LOG_CSV}")
    for r in new_rows:
        print(" ", r)

    write_status_page(results, run_ts)
    print(f"Status page written: {STATUS_MD}")

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
