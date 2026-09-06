#!/usr/bin/env python3
"""
tools/qqq_reprice.py -- re-price QQQ SHADOW round-trips at REAL QQQ prices.

WHY. api/qqq_exec.py records every shadow trade's entry_px/exit_px using a three-way
pricing fallback (see its module docstring): a live Webull quote when available, else
an NQ-fill-price / (QQQ:NQ ratio) synthetic price, else skipped. In practice the
Webull quote path has no market-data entitlement (confirmed 2026-09-02), so every fill
today is priced off the NQ ratio -- never a real QQQ print. This tool answers "what
would this trade actually have filled at on QQQ" by pulling free delayed yfinance
1-minute bars for the real symbol and comparing.

This is a READ-ONLY analysis tool. It never touches C:\\EdgeLog\\qqq_exec\\trades.csv
(the adapter appends to that file live, from a different process, on its own tick
loop -- writing to it here would race that writer and corrupt a live-owned file). It
writes only to a SIDECAR, C:\\EdgeLog\\qqq_exec\\reprice.csv, keyed by (leg, entry_ts),
so it can be re-run any time without duplicating work.

BAR-CLOSE CONVENTION (read this before changing the pricing logic). A shadow fill has
a wall-clock timestamp with seconds, e.g. entry_ts "2026-09-03 12:30:16". yfinance's
1-minute bars are labelled by the bar's OPEN time and span [label, label+1min), e.g.
the bar labelled "12:30:00" covers 12:30:00-12:30:59. We do NOT know at what second
within that bar a real retail order would actually have printed -- the adapter's own
fill (on NQ) landed somewhere inside it too. Rather than guess an intra-bar fill price
(which would silently assume execution quality we can't back up), we conservatively
price BOTH the entry and the exit at that bar's CLOSE. This is deliberately the same
convention for entry and exit (no directional bias from "entry uses open, exit uses
close" or similar), and it is a real, tradeable price the market actually printed in
that minute -- just not necessarily the exact second of the fill. If the bar containing
the timestamp is missing (a rare yfinance/Yahoo gap), we fall back to the nearest bar
within 3 minutes and note it; beyond 3 minutes we skip the trade rather than fabricate
a price.

SLIPPAGE CONVENTION. The re-priced P&L is not simply (real_exit - real_entry) * dir *
shares -- that would price a fill with ZERO execution cost, which the real adapter
(and any real broker) never gets. We charge the adapter's own configured
slippage_per_share (config.json) once per side of the round trip (entry AND exit),
against the trader always -- a round trip always crosses the spread twice, regardless
of side:
    slippage_total = 2 * slippage_per_share * shares
    real_pnl = (real_exit_px - real_entry_px) * dir * shares - slippage_total
where dir = +1 for a long lot, -1 for a short lot (mirrors _record_trade in
api/qqq_exec.py). This is separate from slip_entry_ps/slip_exit_ps below, which
measure something else: how far the adapter's ALREADY-RECORDED (ratio-derived)
entry_px/exit_px sat from the real market price -- i.e. how much the synthetic pricing
itself was off, not a hypothetical execution cost.
    slip_entry_ps = real_entry_px - entry_px      (signed, $/share)
    slip_exit_ps  = real_exit_px  - exit_px       (signed, $/share)

CLI:
    python tools/qqq_reprice.py                 dry run (default) -- prints the table,
                                                  writes nothing
    python tools/qqq_reprice.py --apply         writes new sidecar rows
    python tools/qqq_reprice.py --apply --force re-computes + overwrites rows that are
                                                  already in the sidecar
    python tools/qqq_reprice.py --summary-json  prints a one-line JSON summary (see
                                                  summary_json()) after the normal output
    python tools/qqq_reprice.py --selftest      offline arithmetic/sign self-test
                                                  against a synthetic trades.csv + fake
                                                  bars -- no network, no real files
"""
import argparse
import csv
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _NY = None

OUT_DIR = os.environ.get("EDGELOG_QQQ_EXEC_DIR", r"C:\EdgeLog\qqq_exec")
TRADES_CSV = os.path.join(OUT_DIR, "trades.csv")
SIDECAR_CSV = os.path.join(OUT_DIR, "reprice.csv")
CONFIG_PATH = os.path.join(OUT_DIR, "config.json")

SIDECAR_COLS = ["leg", "entry_ts", "exit_ts", "real_entry_px", "real_exit_px",
                "real_pnl", "slip_entry_ps", "slip_exit_ps", "repriced_at",
                "source", "note"]

DEFAULT_SLIPPAGE_PER_SHARE = 0.01
NEAREST_BAR_TOLERANCE_MIN = 3
# yfinance only carries 1m bars for roughly the trailing 30 days; used only to print a
# clearer note before even attempting the network call, not to enforce a hard cutoff
# (Yahoo's own response is the actual authority -- an empty frame is still handled).
YF_1M_LOOKBACK_DAYS = 30


def _now_et():
    return datetime.now(_NY) if _NY else datetime.utcnow()


def _parse_ts(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")


def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else str(x)


# -- config --------------------------------------------------------------------------
def load_slippage_per_share(config_path=None, log=print):
    path = config_path or CONFIG_PATH
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        val = cfg.get("slippage_per_share", DEFAULT_SLIPPAGE_PER_SHARE)
        return float(val)
    except Exception as e:
        log(f"[qqq-reprice] could not read slippage_per_share from {path} "
            f"({type(e).__name__}: {e}) -- using default {DEFAULT_SLIPPAGE_PER_SHARE}")
        return DEFAULT_SLIPPAGE_PER_SHARE


# -- trades.csv / sidecar I/O ---------------------------------------------------------
def read_trades(trades_csv=None):
    path = trades_csv or TRADES_CSV
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    # every row in trades.csv is a CLOSED round trip -- the adapter only appends here
    # from _record_trade, which runs at exit time.
    return [r for r in rows if (r.get("entry_ts") or "").strip() and
            (r.get("exit_ts") or "").strip()]


def read_sidecar(sidecar_csv=None):
    path = sidecar_csv or SIDECAR_CSV
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {(r["leg"], r["entry_ts"]): r for r in rows}


def write_sidecar(existing, new_or_updated, sidecar_csv=None, log=print):
    """existing: dict key -> row (already on disk, in original order-ish).
    new_or_updated: dict key -> row to add/overwrite.
    Rewrites the whole file (small, capped by trade volume) so overwritten keys
    (via --force) land in place rather than duplicating."""
    path = sidecar_csv or SIDECAR_CSV
    merged = dict(existing)
    merged.update(new_or_updated)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SIDECAR_COLS)
        w.writeheader()
        for row in merged.values():
            w.writerow({c: row.get(c, "") for c in SIDECAR_COLS})
    os.replace(tmp, path)
    log(f"[qqq-reprice] wrote {len(merged)} row(s) -> {path}")


# -- bar fetch -------------------------------------------------------------------------
class NetworkUnavailable(Exception):
    pass


def fetch_day_bars(day_str, log=print):
    """Return a dict {datetime (naive, ET wall-clock, minute-floored): close_price} for
    QQQ 1m bars on the given ET calendar date ("YYYY-MM-DD"), or None if Yahoo simply
    has no bars for that date (holiday/weekend/beyond its 1m window -- NOT an error).
    Raises NetworkUnavailable if the fetch itself could not be attempted/completed."""
    try:
        import yfinance as yf
    except Exception as e:
        raise NetworkUnavailable(f"yfinance not importable: {type(e).__name__}: {e}")

    start = day_str
    end_dt = datetime.strptime(day_str, "%Y-%m-%d") + timedelta(days=1)
    end = end_dt.strftime("%Y-%m-%d")
    try:
        df = yf.Ticker("QQQ").history(start=start, end=end, interval="1m",
                                       prepost=False)
    except Exception as e:
        # yfinance wraps requests/urllib errors in its own exception types depending on
        # version; treat ANY failure to fetch as "network unavailable" per spec --
        # there is no other reason a single-day 1m request would raise.
        raise NetworkUnavailable(f"{type(e).__name__}: {e}")

    if df is None or df.empty:
        return None

    idx = df.index
    try:
        if idx.tz is not None:
            if _NY is not None:
                idx = idx.tz_convert(_NY)
        # else: naive index, already ET (older yfinance) -- leave as-is.
    except Exception:
        pass

    out = {}
    for ts, close in zip(idx, df["Close"].tolist()):
        naive = ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts
        out[naive.replace(second=0, microsecond=0)] = float(close)
    return out


def _nearest_bar_close(bars, ts, tolerance_min=NEAREST_BAR_TOLERANCE_MIN):
    """bars: dict of minute-floored datetime -> close. ts: exact datetime (with
    seconds) to locate. Returns (close_px, note) or (None, note) if nothing within
    tolerance. note is "" for an exact-bar hit, else describes the fallback."""
    minute = ts.replace(second=0, microsecond=0)
    if minute in bars:
        return bars[minute], ""
    best_dt, best_diff = None, None
    for bar_dt in bars:
        diff = abs((bar_dt - minute).total_seconds())
        if best_diff is None or diff < best_diff:
            best_dt, best_diff = bar_dt, diff
    if best_dt is not None and best_diff <= tolerance_min * 60:
        mins = best_diff / 60.0
        return bars[best_dt], f"nearest bar {mins:.1f} min away"
    return None, f"no bar within {tolerance_min} min -- skipped"


# -- core repricing ---------------------------------------------------------------------
def reprice_one(trade, bars_by_day, slippage_per_share, fetch_errors, cutoff_date,
                 log=print):
    """Returns a sidecar row dict, or None if this trade could not be repriced (with
    the reason already logged / carried in fetch_errors for the day it needed)."""
    leg = trade["leg"]
    entry_ts = _parse_ts(trade["entry_ts"])
    exit_ts = _parse_ts(trade["exit_ts"])
    entry_px = float(trade["entry_px"])
    exit_px = float(trade["exit_px"])
    side = (trade.get("side") or "long").strip().lower()
    shares = float(trade["shares"])
    dir_mult = 1 if side == "long" else -1

    entry_day = entry_ts.strftime("%Y-%m-%d")
    exit_day = exit_ts.strftime("%Y-%m-%d")

    notes = []

    if entry_day < cutoff_date:
        return _skip_row(trade, "beyond 30-day window")

    bars_entry = bars_by_day.get(entry_day)
    bars_exit = bars_by_day.get(exit_day)
    if bars_entry is None:
        reason = fetch_errors.get(entry_day, "no bars returned for that day")
        return _skip_row(trade, reason)
    if bars_exit is None:
        reason = fetch_errors.get(exit_day, "no bars returned for that day")
        return _skip_row(trade, reason)

    real_entry_px, note_e = _nearest_bar_close(bars_entry, entry_ts)
    real_exit_px, note_x = _nearest_bar_close(bars_exit, exit_ts)
    if note_e:
        notes.append(f"entry: {note_e}")
    if note_x:
        notes.append(f"exit: {note_x}")
    if real_entry_px is None or real_exit_px is None:
        return _skip_row(trade, "; ".join(notes) or "no bar within tolerance -- skipped")

    slippage_total = 2.0 * slippage_per_share * shares
    real_pnl = round((real_exit_px - real_entry_px) * dir_mult * shares - slippage_total, 2)
    slip_entry_ps = round(real_entry_px - entry_px, 4)
    slip_exit_ps = round(real_exit_px - exit_px, 4)

    return {
        "leg": leg,
        "entry_ts": trade["entry_ts"],
        "exit_ts": trade["exit_ts"],
        "real_entry_px": round(real_entry_px, 4),
        "real_exit_px": round(real_exit_px, 4),
        "real_pnl": real_pnl,
        "slip_entry_ps": slip_entry_ps,
        "slip_exit_ps": slip_exit_ps,
        "repriced_at": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "yfinance_1m",
        "note": "; ".join(notes),
        # not written to sidecar, kept for the printed table only:
        "_ratio_entry_px": entry_px, "_ratio_exit_px": exit_px,
        "_ratio_pnl": float(trade.get("pnl") or 0.0), "_skipped": False,
    }


def _skip_row(trade, note):
    return {
        "leg": trade["leg"], "entry_ts": trade["entry_ts"], "exit_ts": trade["exit_ts"],
        "real_entry_px": "", "real_exit_px": "", "real_pnl": "",
        "slip_entry_ps": "", "slip_exit_ps": "",
        "repriced_at": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "yfinance_1m", "note": note,
        "_ratio_entry_px": float(trade.get("entry_px") or 0.0),
        "_ratio_exit_px": float(trade.get("exit_px") or 0.0),
        "_ratio_pnl": float(trade.get("pnl") or 0.0), "_skipped": True,
    }


# -- reporting ---------------------------------------------------------------------------
def print_table(rows, log=print):
    if not rows:
        log("[qqq-reprice] nothing to report.")
        return
    hdr = (f"{'leg':<7}{'entry_ts':<21}{'ratio px (en/ex)':<20}{'real px (en/ex)':<20}"
           f"{'slip en/ex ps':<16}{'ratio pnl':>10}{'real pnl':>10}  note")
    log(hdr)
    log("-" * len(hdr))
    for r in rows:
        if r["_skipped"]:
            log(f"{r['leg']:<7}{r['entry_ts']:<21}{'--':<20}{'--':<20}{'--':<16}"
                f"{r['_ratio_pnl']:>10.2f}{'--':>10}  {r['note']}")
            continue
        ratio_px = f"{r['_ratio_entry_px']:.4f}/{r['_ratio_exit_px']:.4f}"
        real_px = f"{r['real_entry_px']:.4f}/{r['real_exit_px']:.4f}"
        slip_px = f"{r['slip_entry_ps']:+.4f}/{r['slip_exit_ps']:+.4f}"
        log(f"{r['leg']:<7}{r['entry_ts']:<21}{ratio_px:<20}{real_px:<20}{slip_px:<16}"
            f"{r['_ratio_pnl']:>10.2f}{r['real_pnl']:>10.2f}  {r['note']}")

    priced = [r for r in rows if not r["_skipped"]]
    if priced:
        slips = [abs(r["slip_entry_ps"]) for r in priced] + \
                [abs(r["slip_exit_ps"]) for r in priced]
        mean_slip = sum(slips) / len(slips)
        max_slip = max(slips)
        ratio_pnl_total = sum(r["_ratio_pnl"] for r in priced)
        real_pnl_total = sum(r["real_pnl"] for r in priced)
        log("-" * len(hdr))
        log(f"priced {len(priced)}/{len(rows)}  mean |slip|/share={mean_slip:.4f}  "
            f"max |slip|/share={max_slip:.4f}  ratio-pnl total={ratio_pnl_total:.2f}  "
            f"real-pnl total={real_pnl_total:.2f}  diff={real_pnl_total - ratio_pnl_total:+.2f}")
    else:
        log(f"priced 0/{len(rows)} -- nothing successfully repriced this run.")


def summary_json(all_trades, sidecar_after, log=print):
    total = len(all_trades)
    priced_rows = [r for r in sidecar_after.values() if (r.get("real_pnl") or "") != ""]
    covered = len(priced_rows)
    slips = []
    for r in priced_rows:
        for k in ("slip_entry_ps", "slip_exit_ps"):
            try:
                slips.append(abs(float(r[k])))
            except Exception:
                pass
    out = {
        "covered": covered,
        "total": total,
        "coverage_pct": round(100.0 * covered / total, 2) if total else 0.0,
        "mean_slip_ps": round(sum(slips) / len(slips), 4) if slips else None,
        "last_run": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
    }
    log(json.dumps(out))
    return out


# -- main ---------------------------------------------------------------------------------
def run(trades_csv=None, sidecar_csv=None, config_path=None, apply=False, force=False,
        do_summary_json=False, log=print):
    trades = read_trades(trades_csv)
    if not trades:
        log(f"[qqq-reprice] no closed trades found in "
            f"{trades_csv or TRADES_CSV} -- nothing to do.")
        if do_summary_json:
            summary_json([], {}, log=log)
        return 0

    existing = read_sidecar(sidecar_csv)
    slippage_per_share = load_slippage_per_share(config_path, log=log)

    cutoff_date = (_now_et() - timedelta(days=YF_1M_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    to_process = []
    for t in trades:
        key = (t["leg"], t["entry_ts"])
        if key in existing and not force:
            continue
        to_process.append(t)

    if not to_process:
        log(f"[qqq-reprice] {len(trades)} closed trade(s), all already in "
            f"{sidecar_csv or SIDECAR_CSV} -- nothing new (pass --force to redo).")
        if do_summary_json:
            summary_json(trades, existing, log=log)
        return 0

    days_needed = set()
    for t in to_process:
        days_needed.add(_parse_ts(t["entry_ts"]).strftime("%Y-%m-%d"))
        days_needed.add(_parse_ts(t["exit_ts"]).strftime("%Y-%m-%d"))

    bars_by_day = {}
    fetch_errors = {}
    for day in sorted(days_needed):
        if day < cutoff_date:
            fetch_errors[day] = "beyond 30-day window"
            bars_by_day[day] = None
            continue
        try:
            bars_by_day[day] = fetch_day_bars(day, log=log)
            if bars_by_day[day] is None:
                fetch_errors[day] = "no bars returned for that day (holiday/weekend/gap)"
        except NetworkUnavailable as e:
            log(f"[qqq-reprice] network/data source unavailable ({e}) -- "
                f"sidecar left untouched, exiting cleanly.")
            return 0

    computed = {}
    report_rows = []
    for t in to_process:
        row = reprice_one(t, bars_by_day, slippage_per_share, fetch_errors,
                           cutoff_date, log=log)
        report_rows.append(row)
        if not row["_skipped"]:
            computed[(row["leg"], row["entry_ts"])] = row

    print_table(report_rows, log=log)

    if apply and computed:
        write_sidecar(existing, computed, sidecar_csv, log=log)
        merged = dict(existing)
        merged.update(computed)
    elif apply:
        log("[qqq-reprice] --apply given but nothing new could be priced -- "
            "sidecar untouched.")
        merged = existing
    else:
        log(f"[qqq-reprice] DRY RUN -- would write {len(computed)} row(s) to "
            f"{sidecar_csv or SIDECAR_CSV} (pass --apply to write).")
        merged = dict(existing)
        merged.update(computed)

    if do_summary_json:
        summary_json(trades, merged, log=log)
    return 0


# -- self-test ------------------------------------------------------------------------------
def _selftest():
    """Fully offline: builds a temp trades.csv, a fake bars_by_day (bypassing the
    network fetch entirely), and checks the arithmetic + slippage sign directly against
    reprice_one(). Also checks idempotency (second call with same key already in
    sidecar is skipped) and the --force override path at the run() level using a
    monkeypatched fetch."""
    ok = True

    def check(name, cond):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"[selftest] {status}: {name}")

    # -- 1. direct arithmetic on reprice_one, long side ------------------------------
    # Dates are deliberately computed relative to "now" (a few days back) rather than
    # hardcoded, so this test keeps passing the cutoff-date check regardless of when
    # it's run -- only test 5 below needs a date guaranteed to be OLDER than "now".
    recent_day = (_now_et() - timedelta(days=3)).strftime("%Y-%m-%d")
    trade_long = {"leg": "NOISE", "entry_ts": f"{recent_day} 12:30:16",
                  "exit_ts": f"{recent_day} 15:58:05", "side": "long", "shares": "5",
                  "entry_px": "719.2731", "exit_px": "719.8505", "pnl": "2.89"}
    recent_dt = datetime.strptime(recent_day, "%Y-%m-%d")
    bars_by_day = {
        recent_day: {recent_dt.replace(hour=12, minute=30): 720.00,
                     recent_dt.replace(hour=15, minute=58): 721.00},
    }
    row = reprice_one(trade_long, bars_by_day, slippage_per_share=0.01,
                       fetch_errors={}, cutoff_date="2000-01-01", log=lambda *a: None)
    check("long: not skipped", row["_skipped"] is False)
    check("long: real_entry_px == bar close (720.00)", row["real_entry_px"] == 720.00)
    check("long: real_exit_px == bar close (721.00)", row["real_exit_px"] == 721.00)
    # slip_entry_ps = real(720.00) - recorded(719.2731) = 0.7269
    check("long: slip_entry_ps sign/value",
          abs(row["slip_entry_ps"] - 0.7269) < 1e-6)
    check("long: slip_exit_ps sign/value",
          abs(row["slip_exit_ps"] - (721.00 - 719.8505)) < 1e-6)
    # real_pnl = (721.00-720.00)*1*5 - 2*0.01*5 = 5.0 - 0.1 = 4.90
    check("long: real_pnl arithmetic + slippage subtracted",
          abs(row["real_pnl"] - 4.90) < 1e-9)

    # -- 2. short side flips the direction multiplier --------------------------------
    trade_short = dict(trade_long, side="short")
    row_s = reprice_one(trade_short, bars_by_day, slippage_per_share=0.01,
                         fetch_errors={}, cutoff_date="2000-01-01", log=lambda *a: None)
    # real_pnl = (721.00-720.00)*(-1)*5 - 0.1 = -5.0 - 0.1 = -5.10
    check("short: direction multiplier flips sign of price pnl",
          abs(row_s["real_pnl"] - (-5.10)) < 1e-9)
    # slip_entry_ps / slip_exit_ps are direction-agnostic (pure price differences)
    check("short: slip_entry_ps unaffected by side",
          row_s["slip_entry_ps"] == row["slip_entry_ps"])

    # -- 3. slippage always REDUCES pnl regardless of direction ----------------------
    row_noslip = reprice_one(trade_long, bars_by_day, slippage_per_share=0.0,
                              fetch_errors={}, cutoff_date="2000-01-01",
                              log=lambda *a: None)
    check("slippage strictly reduces long real_pnl vs zero-slippage",
          row["real_pnl"] < row_noslip["real_pnl"])
    row_s_noslip = reprice_one(trade_short, bars_by_day, slippage_per_share=0.0,
                                fetch_errors={}, cutoff_date="2000-01-01",
                                log=lambda *a: None)
    check("slippage strictly reduces short real_pnl vs zero-slippage",
          row_s["real_pnl"] < row_s_noslip["real_pnl"])

    # -- 4. nearest-bar fallback within tolerance, and beyond it ----------------------
    bars_gap = {recent_day: {recent_dt.replace(hour=12, minute=32): 722.0,
                              recent_dt.replace(hour=15, minute=58): 721.0}}
    row_fb = reprice_one(trade_long, bars_gap, slippage_per_share=0.01,
                          fetch_errors={}, cutoff_date="2000-01-01", log=lambda *a: None)
    check("nearest-bar fallback (2 min away, within 3 min tolerance) used",
          row_fb["_skipped"] is False and row_fb["real_entry_px"] == 722.0)
    check("fallback noted", "nearest bar" in row_fb["note"])

    bars_far = {recent_day: {recent_dt.replace(hour=12, minute=40): 723.0,
                              recent_dt.replace(hour=15, minute=58): 721.0}}
    row_far = reprice_one(trade_long, bars_far, slippage_per_share=0.01,
                           fetch_errors={}, cutoff_date="2000-01-01",
                           log=lambda *a: None)
    check("beyond 3-min tolerance -> skipped", row_far["_skipped"] is True)
    check("beyond-tolerance note text", "no bar within" in row_far["note"])

    # -- 5. cutoff date -> beyond-window skip -----------------------------------------
    day_after_recent = (recent_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    row_old = reprice_one(trade_long, bars_by_day, slippage_per_share=0.01,
                           fetch_errors={}, cutoff_date=day_after_recent,
                           log=lambda *a: None)
    check("older than cutoff -> beyond-window skip",
          row_old["_skipped"] is True and "30-day" in row_old["note"])

    # -- 6. end-to-end run() idempotency using a temp trades.csv + monkeypatched fetch --
    with tempfile.TemporaryDirectory() as td:
        trades_csv = os.path.join(td, "trades.csv")
        sidecar_csv = os.path.join(td, "reprice.csv")
        config_path = os.path.join(td, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"slippage_per_share": 0.01}, f)
        with open(trades_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["leg", "entry_ts", "exit_ts", "side",
                                               "shares", "entry_px", "exit_px", "pnl"])
            w.writeheader()
            w.writerow({"leg": "NOISE", "entry_ts": f"{recent_day} 12:30:16",
                        "exit_ts": f"{recent_day} 15:58:05", "side": "long", "shares": "5",
                        "entry_px": "719.2731", "exit_px": "719.8505", "pnl": "2.89"})

        real_fetch = fetch_day_bars

        def fake_fetch(day, log=print):
            return bars_by_day.get(day)

        globals()["fetch_day_bars"] = fake_fetch
        try:
            silent = lambda *a: None
            run(trades_csv, sidecar_csv, config_path, apply=True, force=False,
                do_summary_json=False, log=silent)
            after_first = read_sidecar(sidecar_csv)
            check("apply wrote exactly 1 sidecar row", len(after_first) == 1)

            mtime_before = os.path.getmtime(sidecar_csv)
            run(trades_csv, sidecar_csv, config_path, apply=True, force=False,
                do_summary_json=False, log=silent)
            mtime_after = os.path.getmtime(sidecar_csv)
            check("second --apply run is a no-op (idempotent, no rewrite)",
                  mtime_before == mtime_after)

            run(trades_csv, sidecar_csv, config_path, apply=True, force=True,
                do_summary_json=False, log=silent)
            after_force = read_sidecar(sidecar_csv)
            check("--force overwrites the same key rather than duplicating",
                  len(after_force) == 1)
        finally:
            globals()["fetch_day_bars"] = real_fetch

    print(f"[selftest] {'ALL PASS' if ok else 'SOME FAILED'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the sidecar (default: dry run)")
    ap.add_argument("--force", action="store_true",
                     help="re-price + overwrite trades already in the sidecar")
    ap.add_argument("--summary-json", action="store_true", dest="summary_json",
                     help="print a one-line JSON summary after the table")
    ap.add_argument("--trades-csv", default=None, help="override trades.csv path")
    ap.add_argument("--sidecar", default=None, help="override reprice.csv path")
    ap.add_argument("--config", default=None, help="override config.json path")
    ap.add_argument("--selftest", action="store_true",
                     help="offline arithmetic/idempotency self-test, no network/real files")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    try:
        sys.exit(run(args.trades_csv, args.sidecar, args.config, apply=args.apply,
                      force=args.force, do_summary_json=args.summary_json))
    except Exception as e:
        print(f"[qqq-reprice] unexpected error: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(0)  # never crash noisily; this is a read-only analysis aid


if __name__ == "__main__":
    main()
