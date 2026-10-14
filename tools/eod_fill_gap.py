#!/usr/bin/env python3
"""tools/eod_fill_gap.py -- the END-OF-DAY FILL GAP log: every end-of-day exit of the live
QQQ book beside the engine's own end-of-day price, so the gap can be MEASURED, not guessed
(MANAGER #152, from ORB COSTSTRESS r1: live ORB_R6 on Webull trails the engine by about
$0.19/sh a round trip on 5 trades, all of it on the exit -- the executor sells ~15:59 while
the engine prices its 15:55 bar).

A MEASUREMENT LOG ONLY. It reads the box's ledgers and its bar cache; the one file it
writes is its own <exec_dir>/eod_fill_gap.csv (default <EDGELOG_HOME>/qqq_exec/). It never
changes trading, order timing, or any existing file -- the live exit time stays where it is.
tools/qqq_bars_publish.py calls write_for_home() after its own work (16:10 and 09:20 ET,
edgelog-qqq-bars.timer); it can also be run by hand.

ONE ROW PER EOD EXIT: every closed lot in qqq_exec/trades.csv whose exit_reason starts with
"EOD" ("EOD (px: live_stream)", the older bare "EOD", "EOD settle (backtest)"), all history,
oldest exit first:
  day, leg, trade_id, side, shares, exit_ts, exit_reason
                      straight from trades.csv (exit_ts = New York wall clock)
  book_exit_px        trades.csv exit_px -- the book's own price at the flatten
  broker_fill_px      Webull's fill for the trade's CLOSE: broker_orders.csv rows joined on
                      the trade's broker signal id with any R<n> resend / X partial-cross
                      suffix stripped (the join tools/qqq_bars_publish.py uses), the
                      share-weighted price of every row that reached Webull and FILLED (OK).
                      Blank when none did, or while a filled row has no price captured yet.
                      An internally crossed (NETTED) row never reached Webull: not counted.
  engine_exit_px, engine_exit_bar, engine_exit_emitted_at, engine_exit_reason
                      the engine's EXIT row for the same trade_id in cloud_signal/signals.csv
                      (the last one wins): ref_price, ref_time (the bar's START) and
                      emitted_at as New York wall clock, and its reason ("eod_settle" = the
                      engine's post-close end-of-day exit). Blank when the engine wrote no
                      EXIT for the trade, or the trade has no id.
  bar_1555_open, bar_1555_close
                      the session's LAST 5-minute bar in the bar cache the engine traded on
                      (<EDGELOG_HOME>/ohlc/QQQ_5m.csv -- the same file, and the same reader,
                      tools/qqq_bars_publish.py charts): 15:55, or 12:55 on a half day
                      (api/market_calendar.session_close_et).
  close_1600          that last bar's close, i.e. the session's closing price (named for
                      the usual 16:00 close; 13:00 on a half day).
  fill_vs_engine      $/share, POSITIVE = live did WORSE than the engine for that side:
                      long (a sell) engine - fill, short (a buy) fill - engine, where fill =
                      broker_fill_px when there is one, else book_exit_px (px_source says
                      which). Blank when either price is missing, and when the engine's exit
                      bar is not that same session's last bar: the engine held the trade on
                      or left it at another bar (an ENGU-Q trade the book flattened at 15:59
                      that the engine carried for days), so the gap would not be the EOD gap.
  fill_vs_close_1600  the same sign rule against close_1600.
  px_source           "broker" or "book".

RE-RUNS ARE IDEMPOTENT: the whole file is rebuilt each run and replaced atomically (tmp +
os.replace); two runs on the same inputs write the same bytes. A row whose last bar is not
in the cache yet is written with the bar fields blank and filled on a later run. The
ledgers are trimmed at the top (trades.csv to its newest 500 rows, broker_orders.csv to
2000, by api/qqq_exec.py), so history must outlive them: a row of the previous file whose
exit is older than trades.csv's oldest row is kept as it was, and a field that reads blank
now but had a value last time (its source row was trimmed away) keeps that value, the gaps
recomputed from it. A ledger read that looks torn twice (api/qqq_exec.py rewrites a
trimmed file in place) writes nothing this run.

NEVER RAISES from main(): unreadable inputs are logged and it exits 0 (1 only on bad
arguments). Log lines are plain ASCII, prefixed "[eod-gap]".

USAGE
    python tools/eod_fill_gap.py [--home DIR] [--exec-dir DIR] [--ohlc-dir DIR]
                                 [--signals PATH] [--dry-run]
"""
import argparse
import csv
import io
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from api import market_calendar as _cal  # noqa: E402  (stdlib only)
from tools import qqq_bars_publish as _qb  # noqa: E402  (its ledger, signal and bar readers)

OUT_NAME = "eod_fill_gap.csv"
COLS = ["day", "leg", "trade_id", "side", "shares", "exit_ts", "exit_reason", "book_exit_px",
        "broker_fill_px", "engine_exit_px", "engine_exit_bar", "engine_exit_emitted_at",
        "bar_1555_open", "bar_1555_close", "close_1600", "fill_vs_engine",
        "fill_vs_close_1600", "px_source", "engine_exit_reason"]
# fields read from a source that is trimmed over time: a value once seen is kept
CARRY = ("broker_fill_px", "engine_exit_px", "engine_exit_bar", "engine_exit_emitted_at",
         "engine_exit_reason", "bar_1555_open", "bar_1555_close", "close_1600")
BAR_MIN = 5
REASON_MAX = 80


# -- small helpers -----------------------------------------------------------------------
def _fmt(x):
    """A number as the file writes it: at most 4 decimals, no trailing zeros, "" for None."""
    if x is None:
        return ""
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def is_eod_exit(trade):
    return str(trade.get("exit_reason") or "").strip().upper().startswith("EOD")


def last_bar_minute(day):
    """Minutes after midnight (New York) of the session's last 5-minute bar START:
    15:55, or 12:55 on a half day."""
    hh, mm = _cal.session_close_et(day).split(":")
    return int(hh) * 60 + int(mm) - BAR_MIN


def signed_gap(side, fill, ref):
    """$/share, POSITIVE = the fill was WORSE than `ref` for this side's exit (a long
    sells: ref - fill; a short buys: fill - ref). None when either price is missing."""
    if fill is None or ref is None:
        return None
    s = str(side or "").strip().lower()
    if s == "long":
        return ref - fill
    if s == "short":
        return fill - ref
    return None


def broker_exit_fill(rows):
    """Webull's share-weighted fill over a trade's CLOSE rows that reached Webull and
    filled (qqq_bars_publish.row_outcome == "OK"), or None: no such row, or one of them
    has no price captured yet (never half a price)."""
    tot_sh, tot_px = 0.0, 0.0
    for r in rows or []:
        if _qb.row_outcome(r) != "OK":
            continue
        px = _qb._num(r.get("broker_fill_px"))
        if px is None:
            return None
        sh = _qb._num(r.get("shares"))
        sh = sh if sh and sh > 0 else 1.0
        tot_sh += sh
        tot_px += px * sh
    return tot_px / tot_sh if tot_sh else None


def _key(row):
    return (str(row.get("leg") or ""), str(row.get("trade_id") or ""),
            str(row.get("exit_ts") or ""))


# -- the rows ----------------------------------------------------------------------------
def build_row(trade, brokers, sigs, bars_5m):
    """One EOD exit -> {col: value} (numbers as floats, None for blank), or None when the
    row cannot be placed on a day (no exit_ts)."""
    exit_ts = _qb.to_et_str(trade.get("exit_ts"))
    if not exit_ts:
        return None
    day = exit_ts[:10]
    tid = str(trade.get("trade_id") or "").strip()
    side = str(trade.get("side") or "").strip().lower()
    row = {c: None for c in COLS}
    row.update({"day": day, "leg": str(trade.get("leg") or ""), "trade_id": tid,
                "side": side, "shares": _qb._num(trade.get("shares")), "exit_ts": exit_ts,
                "exit_reason": str(trade.get("exit_reason") or "").strip(),
                "book_exit_px": _qb._num(trade.get("exit_px"))})
    if tid:
        row["broker_fill_px"] = broker_exit_fill(brokers.get(_qb.signal_id_base(tid, "CLOSE")))
        ex = (sigs.get(tid) or {}).get("EXIT")
        if ex:
            row["engine_exit_px"] = _qb._num(ex.get("ref_price"))
            row["engine_exit_bar"] = _qb.to_et_str(ex.get("ref_time"))
            row["engine_exit_emitted_at"] = _qb.to_et_str(ex.get("emitted_at"))
            row["engine_exit_reason"] = str(ex.get("reason") or "").strip()[:REASON_MAX] or None
    try:
        want = last_bar_minute(day)
    except ValueError:
        want = None
    bar = next((b for b in bars_5m.get(day, []) if b[0] == want), None)
    if bar is not None:
        row["bar_1555_open"], row["bar_1555_close"] = bar[1], bar[4]
        row["close_1600"] = bar[4]
    return row


def _as_text(row):
    return {c: (_fmt(v) if isinstance(v, float) else ("" if v is None else str(v)))
            for c, v in row.items()}


def engine_exit_at_close(row):
    """True when the engine's exit bar is the session's last bar of the row's own day."""
    try:
        m = last_bar_minute(row.get("day"))
    except (TypeError, ValueError):
        return False
    return str(row.get("engine_exit_bar") or "") == f"{row.get('day')} {_qb._hhmm(m)}:00"


def _finish(row):
    """Pick the fill and compute both gaps from the (text) row's prices."""
    num = {c: _qb._num(row.get(c)) for c in ("broker_fill_px", "book_exit_px",
                                             "engine_exit_px", "close_1600")}
    if num["broker_fill_px"] is not None:
        fill, src = num["broker_fill_px"], "broker"
    else:
        fill, src = num["book_exit_px"], "book"
    row["px_source"] = src
    engine = num["engine_exit_px"] if engine_exit_at_close(row) else None
    row["fill_vs_engine"] = _fmt(signed_gap(row.get("side"), fill, engine))
    row["fill_vs_close_1600"] = _fmt(signed_gap(row.get("side"), fill, num["close_1600"]))
    return row


def build_rows(trades, broker_rows, signal_rows, bars_5m, prior=None):
    """Every EOD exit as text rows (COLS), oldest exit first -- see the module docstring
    (RE-RUNS) for how `prior` (the previous file's rows) is merged in."""
    brokers = _qb.broker_by_base(broker_rows)
    sigs = _qb.signals_by_trade(signal_rows)
    old = {_key(r): r for r in prior or []}
    out = {}
    for t in trades:
        if not is_eod_exit(t):
            continue
        r = build_row(t, brokers, sigs, bars_5m)
        if r is None:
            continue
        r = _as_text(r)
        p = old.get(_key(r))
        if p:
            for c in CARRY:
                if not r.get(c) and p.get(c):
                    r[c] = p[c]
        out[_key(r)] = _finish(r)
    # the ledger was trimmed at the top: keep what it no longer holds
    first = min((x for x in (_qb.to_et_str(t.get("exit_ts")) for t in trades) if x), default=None)
    for k, p in old.items():
        if k not in out and (first is None or str(p.get("exit_ts") or "") < first):
            out[k] = _finish({c: str(p.get(c) or "") for c in COLS})
    return [out[k] for k in sorted(out, key=lambda k: (k[2], k[0], k[1]))]


# -- files -------------------------------------------------------------------------------
def output_path(paths):
    return os.path.join(os.path.dirname(paths["trades"]), OUT_NAME)


def to_csv_text(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS)
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in COLS})
    return buf.getvalue()


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def write_for_home(home=None, paths=None, log=print, dry_run=False, sleep=time.sleep):
    """Rebuild <exec_dir>/eod_fill_gap.csv from the ledgers under `home` (or the explicit
    `paths`, qqq_bars_publish.default_paths' shape). Returns the rows (written unless
    `dry_run`), or None when an input could not be read -- logged, nothing written."""
    paths = paths or _qb.default_paths(home)
    out_path = output_path(paths)
    if not os.path.isfile(paths["trades"]):
        log(f"[eod-gap] no trades.csv at {paths['trades']} -- nothing written")
        return None
    try:
        trades = _qb.read_ledger(paths["trades"], sleep=sleep)
        broker_rows = _qb.read_ledger(paths["broker_orders"], sleep=sleep)
        signal_rows = _qb._read_csv(paths["signals"])
        bars_5m = _qb.load_bars(paths["bars"]["5m"])
    except _qb.LedgerUnreliable as e:
        log(f"[eod-gap] ledger read looks mid-rewrite ({e}) -- {OUT_NAME} left as it was; "
            f"the next run retries")
        return None
    except (OSError, ValueError, csv.Error) as e:
        log(f"[eod-gap] could not read an input ({type(e).__name__}: {e}) -- "
            f"{OUT_NAME} left as it was")
        return None
    try:
        prior = _qb._read_csv(out_path)
    except (OSError, ValueError, csv.Error) as e:
        log(f"[eod-gap] previous {OUT_NAME} unreadable ({type(e).__name__}: {e}) -- "
            f"rebuilt from the ledgers alone")
        prior = []
    rows = build_rows(trades, broker_rows, signal_rows, bars_5m, prior=prior)
    waiting = sum(1 for r in rows if not r.get("close_1600"))
    if dry_run:
        log(f"[eod-gap] DRY RUN {len(rows)} EOD exit row(s), {waiting} without their "
            f"last bar yet -- nothing written")
        return rows
    write_atomic(out_path, to_csv_text(rows))
    log(f"[eod-gap] wrote {len(rows)} EOD exit row(s) to {out_path} ({waiting} without "
        f"their last bar yet)")
    return rows


# -- CLI ---------------------------------------------------------------------------------
def main(argv=None, out=None):
    out = out or sys.stdout

    def log(s):
        print(s, file=out)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=None, help="EDGELOG_HOME (default: env, else ~/edgelog)")
    ap.add_argument("--exec-dir", default=None, help="qqq_exec dir (default: <home>/qqq_exec)")
    ap.add_argument("--ohlc-dir", default=None, help="bar cache dir (default: <home>/ohlc)")
    ap.add_argument("--signals", default=None, help="signals.csv (default: <home>/cloud_signal)")
    ap.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 1
    try:
        paths = _qb.default_paths(a.home, a.ohlc_dir, a.exec_dir, a.signals)
        rows = write_for_home(paths=paths, log=log, dry_run=a.dry_run)
        if a.dry_run and rows is not None:
            out.write(to_csv_text(rows))
    except Exception as e:  # noqa: BLE001 -- a measurement log never fails its caller
        log(f"[eod-gap] failed ({type(e).__name__}: {e}) -- nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
