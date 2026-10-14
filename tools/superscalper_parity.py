"""SUPERSCALPER parity harness - the MISC_SUPERSCALPER_1_0 port vs TradingView's own trades.

Two jobs:

  export   run the port on NQ 1m ETH (db_noadj_eth) for a date window and write its trade
           list to CSV: signal / entry / exit bar times in America/New_York, side, entry
           path, entry / exit price, exit reason, points, the ticket's stop and target.
           Refuses any window that reaches the lockbox (on or after 2025-06-30).

  compare  read a TradingView trade export and match TV trades to port trades by side +
           entry time (same minute, or +/-1 bar), then print ONLY match statistics:
             share of TV trades matched, share of port trades matched,
             entry / exit price median absolute difference in ticks (raw, and with TV's
             2-tick slippage taken back out), exit-reason agreement, and the correlation
             of per-trade P&L on matched pairs.
           It never prints or writes the port's own totals, P&L, win rate or drawdown, and
           never writes the port's trade list - the run stays in memory. A TV file inside
           the lockbox year is accepted only for the coordinator's comparison window
           2026-03-26 .. 2026-04-22, and only that window of NQ data is loaded.

TV files understood:
  * the published-trades file (columns trade, side, exit_time, entry_time, exit_price,
    entry_price, qty, net_pnl_usd; times like "Mar 29, 2026, 18:47"; a row whose exit_time
    is "Open" is skipped);
  * TradingView's "List of Trades" export (columns 'Trade #', 'Type', 'Signal',
    'Date/Time', 'Price USD', 'Contracts', 'Profit USD'; two rows per trade).
  TV times are read in --tv-tz (default America/Chicago, the CME chart's exchange zone);
  each TV entry time is the bar whose OPEN filled the order.

Data: needs a checkout with the master registry. Run it from the shared checkout, or pass
--data-root (or set EDGELOG_ROOT) to point at one; the port file itself always comes from
the repo this tool lives in.

  python tools/superscalper_parity.py export --from 2024-06-01 --to 2024-06-30 --out port.csv
  python tools/superscalper_parity.py compare --tv superscalper_tv_trades_published.csv
  python tools/superscalper_parity.py compare --tv ... --score-from 2026-04-06
"""
import argparse
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRATEGY = os.path.join(HERE, "augur_strategies", "MISC_SUPERSCALPER_1_0.py")
LOCKBOX_FIRST_DAY = "2025-06-30"                       # this date and later = lockbox
TV_LOCKBOX_WINDOW = ("2026-02-27", "2026-04-22")       # warm-up from 02-27 (indicators need ~4 sessions; TV trades start 03-29)
TICK = 0.25
TV_SLIP_TICKS = 2


def _engine(data_root):
    root = data_root or os.environ.get("EDGELOG_ROOT") or HERE
    root = os.path.abspath(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.dont_write_bytecode = True
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays
    return run_backtest, find_master, load_master_arrays, root


def _parse_params(items):
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        out[k.strip()] = v.strip()
    return out


def run_port(date_from, date_to, params, data_root=None):
    """The port on NQ 1m ETH for [date_from, date_to] -> (detail rows, bar index, feeds info)."""
    run_backtest, find_master, load_master_arrays, root = _engine(data_root)
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    if m is None:
        raise SystemExit("no NQ 1m ETH db_noadj_eth master in the registry under %s - run from the "
                         "shared checkout or pass --data-root" % root)
    arrays = load_master_arrays(m, date_from=date_from, date_to=date_to)
    p = dict(params)
    p["_detail"] = True
    res = run_backtest(STRATEGY, arrays=arrays, master=m, params=p, cost_pts=0.0,
                       return_trades=True)
    rows = (res or {}).get("trade_detail") or []
    return rows, arrays["index"], find_master


def _fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M")


# ── export ───────────────────────────────────────────────────────────────────

def cmd_export(a):
    if a.date_to >= LOCKBOX_FIRST_DAY or a.date_from >= LOCKBOX_FIRST_DAY:
        raise SystemExit("refused: export window reaches the lockbox (%s and later)" % LOCKBOX_FIRST_DAY)
    rows, idx, _fm = run_port(a.date_from, a.date_to, _parse_params(a.param), a.data_root)
    et = idx.tz_convert("America/New_York")
    out = a.out
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trade", "side", "path", "signal_time_et", "entry_time_et", "exit_time_et",
                    "entry_price", "exit_price", "exit_reason", "pnl_pts", "ticket_sl", "ticket_tp"])
        for k, r in enumerate(sorted(rows, key=lambda r: (r["entry_bar"], r["exit_bar"])), 1):
            w.writerow([k, "Long" if r["side"] > 0 else "Short", r["path"],
                        _fmt(et[r["signal_bar"]]), _fmt(et[r["entry_bar"]]), _fmt(et[r["exit_bar"]]),
                        "%.2f" % r["entry_price"], "%.2f" % r["exit_price"], r["exit_reason"],
                        "%.4f" % r["pnl_pts"], "%.2f" % r["ticket_sl"], "%.2f" % r["ticket_tp"]])
    print("wrote %d port trades (%s .. %s) to %s" % (len(rows), a.date_from, a.date_to, out))


# ── compare ──────────────────────────────────────────────────────────────────

def read_tv(path, tz):
    """TV trades -> list of dicts: side, entry_ts, exit_ts (UTC pandas Timestamps), prices, pnl."""
    import pandas as pd
    df = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in df.columns}
    trades = []

    def num(x):
        return float(str(x).replace(",", "").replace("+", "").replace("$", "").strip())

    if "entry_time" in cols and "exit_time" in cols:
        for _, r in df.iterrows():
            if str(r[cols["exit_time"]]).strip().lower() == "open":
                continue
            ent = pd.to_datetime(str(r[cols["entry_time"]]), format="%b %d, %Y, %H:%M")
            ext = pd.to_datetime(str(r[cols["exit_time"]]), format="%b %d, %Y, %H:%M")
            trades.append({
                "side": 1 if str(r[cols["side"]]).strip().lower().startswith("l") else -1,
                "entry_ts": ent.tz_localize(tz).tz_convert("UTC"),
                "exit_ts": ext.tz_localize(tz).tz_convert("UTC"),
                "entry_price": num(r[cols["entry_price"]]), "exit_price": num(r[cols["exit_price"]]),
                "pnl": num(r[cols["net_pnl_usd"]]) if "net_pnl_usd" in cols else float("nan")})
        return trades
    tcol = cols.get("trade #") or cols.get("trade")
    typ = cols.get("type")
    dtc = cols.get("date/time") or cols.get("date and time")
    pcol = next((cols[c] for c in cols if c.startswith("price")), None)
    prof = next((cols[c] for c in cols if c.startswith("profit") or c.startswith("net p")), None)
    if not (tcol and typ and dtc and pcol):
        raise SystemExit("unrecognised TV trade file columns: %s" % list(df.columns))
    for tid, g in df.groupby(tcol):
        ent = g[g[typ].astype(str).str.lower().str.startswith("entry")]
        ext = g[g[typ].astype(str).str.lower().str.startswith("exit")]
        if ent.empty or ext.empty:
            continue
        if str(ext.iloc[0][dtc]).strip().lower() in ("open", "", "nan"):
            continue
        e0 = ent.iloc[0]; x0 = ext.iloc[0]
        trades.append({
            "side": 1 if "long" in str(e0[typ]).lower() else -1,
            "entry_ts": pd.to_datetime(str(e0[dtc])).tz_localize(tz).tz_convert("UTC"),
            "exit_ts": pd.to_datetime(str(x0[dtc])).tz_localize(tz).tz_convert("UTC"),
            "entry_price": num(e0[pcol]), "exit_price": num(x0[pcol]),
            "pnl": num(x0[prof]) if prof else float("nan")})
    return trades


def _median(xs):
    xs = sorted(x for x in xs if x == x)
    if not xs:
        return float("nan")
    k = len(xs) // 2
    return xs[k] if len(xs) % 2 else 0.5 * (xs[k - 1] + xs[k])


def _pearson(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x == x and y == y]
    if len(pairs) < 3:
        return float("nan")
    mx = sum(p[0] for p in pairs) / len(pairs)
    my = sum(p[1] for p in pairs) / len(pairs)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else float("nan")


def tv_exit_reason(t, p):
    """TV lists no exit reason. Read it off the matched port exit order's levels when TV's
    exit sits on them (a limit fills at its price, a stop up to TV's slippage beyond it),
    else from the sign of TV's gross move (targets sit above entry for longs, stops below)."""
    sd = t["side"]
    x = t["exit_price"]
    tp, sl = p.get("x_tp", float("nan")), p.get("x_sl", float("nan"))
    if tp == tp and abs(x - tp) <= 0.5 * TICK:
        return "limit"
    if sl == sl and -0.5 * TICK <= sd * (sl - x) <= (TV_SLIP_TICKS + 0.5) * TICK:
        return "stop"
    return "limit" if sd * (x - t["entry_price"]) > 0 else "stop"


def match(tv, port, tol_s=60):
    """Greedy one-to-one: each TV trade (in time order) takes the unmatched port trade of
    the same side whose entry is closest in time, within +/- tol_s (same minute or 1 bar)."""
    used = set()
    pairs = []
    by_side = {1: [], -1: []}
    for j, p in enumerate(port):
        by_side[p["side"]].append(j)
    for i, t in enumerate(sorted(range(len(tv)), key=lambda i: tv[i]["entry_ts"])):
        te = tv[t]["entry_ts"].value // 10 ** 9
        best = None
        for j in by_side[tv[t]["side"]]:
            if j in used:
                continue
            dt = abs(port[j]["entry_epoch"] - te)
            if dt <= tol_s and (best is None or dt < best[0]):
                best = (dt, j)
        if best is not None:
            used.add(best[1])
            pairs.append((t, best[1]))
    return pairs


def cmd_compare(a):
    import pandas as pd
    tv = read_tv(a.tv, a.tv_tz)
    if not tv:
        raise SystemExit("no closed TV trades in %s" % a.tv)
    first = min(t["entry_ts"] for t in tv).tz_convert("America/New_York")
    last = max(t["exit_ts"] for t in tv).tz_convert("America/New_York")
    d_from = (first - pd.Timedelta(days=30)).strftime("%Y-%m-%d")   # warm-up; scoring starts at the first TV entry
    d_to = (last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    lockbox = d_to >= LOCKBOX_FIRST_DAY or first.strftime("%Y-%m-%d") >= LOCKBOX_FIRST_DAY
    if lockbox:
        lo, hi = TV_LOCKBOX_WINDOW
        if first.strftime("%Y-%m-%d") < lo or last.strftime("%Y-%m-%d") > hi:
            raise SystemExit("refused: TV trades fall in the lockbox outside the allowed comparison "
                             "window %s .. %s" % TV_LOCKBOX_WINDOW)
        d_from = max(d_from, lo)
        d_to = min(d_to, hi)
    rows, idx, _fm = run_port(d_from, d_to, _parse_params(a.param), a.data_root)
    epoch = (idx.tz_convert("UTC").as_unit("ns").asi8 // 10 ** 9)
    port = [{"side": r["side"], "entry_epoch": int(epoch[r["entry_bar"]]),
             "entry_price": r["entry_price"], "exit_price": r["exit_price"],
             "reason": r["exit_reason"], "pnl": r["pnl_pts"],
             "x_sl": r.get("exit_order_sl", float("nan")),
             "x_tp": r.get("exit_order_tp", float("nan"))} for r in rows]
    if a.score_from:                      # score after the indicators' warm-up only
        cut = pd.Timestamp(a.score_from, tz="America/New_York")
        tv = [t for t in tv if t["entry_ts"] >= cut]
        if not tv:
            raise SystemExit("no TV trades on or after --score-from %s" % a.score_from)
    t_lo = min(t["entry_ts"] for t in tv).value // 10 ** 9 - 60
    t_hi = max(t["entry_ts"] for t in tv).value // 10 ** 9 + 60
    port = [p for p in port if t_lo <= p["entry_epoch"] <= t_hi]
    pairs = match(tv, port)

    e_raw, e_adj, x_raw, x_adj, agree, tv_pnl, port_pnl = [], [], [], [], [], [], []
    for ti, pj in pairs:
        t = tv[ti]; p = port[pj]; sd = t["side"]
        e_raw.append(abs(t["entry_price"] - p["entry_price"]) / TICK)
        e_adj.append(abs(t["entry_price"] - sd * TV_SLIP_TICKS * TICK - p["entry_price"]) / TICK)
        tv_reason = tv_exit_reason(t, p)
        x_raw.append(abs(t["exit_price"] - p["exit_price"]) / TICK)
        tv_x = t["exit_price"] + (sd * TV_SLIP_TICKS * TICK if tv_reason == "stop" else 0.0)
        x_adj.append(abs(tv_x - p["exit_price"]) / TICK)
        agree.append(1.0 if tv_reason == p["reason"] else 0.0)
        tv_pnl.append(t["pnl"]); port_pnl.append(p["pnl"])

    n_tv = len(tv); n_m = len(pairs)
    print("SUPERSCALPER parity - match statistics only (data %s .. %s%s%s)"
          % (d_from, d_to, ", lockbox comparison window" if lockbox else "",
             ", scored from %s" % a.score_from if a.score_from else ""))
    print("  TV closed trades                       : %d" % n_tv)
    print("  matched pairs (side + entry +/-1 bar)  : %d" % n_m)
    print("  share of TV trades matched             : %.1f%%" % (100.0 * n_m / n_tv))
    print("  share of port trades matched           : %s" % (
        "%.1f%%" % (100.0 * n_m / len(port)) if port else "n/a (port has no trades in the span)"))
    if n_m:
        print("  entry price median |diff| ticks        : %.2f raw, %.2f with TV's %d-tick slippage removed"
              % (_median(e_raw), _median(e_adj), TV_SLIP_TICKS))
        print("  exit price median |diff| ticks         : %.2f raw, %.2f with TV's stop slippage removed"
              % (_median(x_raw), _median(x_adj)))
        print("  exit-reason agreement                  : %.1f%%  (TV reason inferred: its exit at the "
              "port exit order's target = limit, at its stop +/-%d ticks = stop, else the sign of "
              "TV's gross move)" % (100.0 * sum(agree) / n_m, TV_SLIP_TICKS))
        print("  per-trade P&L correlation (Pearson)    : %.3f  (TV net USD vs port gross points, "
              "%d pairs)" % (_pearson(tv_pnl, port_pnl), n_m))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="run the port and write its trade list (pre-lockbox only)")
    ex.add_argument("--from", dest="date_from", required=True)
    ex.add_argument("--to", dest="date_to", required=True)
    ex.add_argument("--out", required=True)
    ex.add_argument("--param", action="append", help="knob=value (repeatable)")
    ex.add_argument("--data-root", default=None)
    cp = sub.add_parser("compare", help="match a TradingView trade export (stats only)")
    cp.add_argument("--tv", required=True)
    cp.add_argument("--tv-tz", default="America/Chicago")
    cp.add_argument("--score-from", default=None,
                    help="YYYY-MM-DD (ET): score only trades entered on/after this date - the "
                         "port starts cold at the first loaded bar (4h EMA21 needs ~4 sessions)")
    cp.add_argument("--param", action="append", help="knob=value (repeatable)")
    cp.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    (cmd_export if a.cmd == "export" else cmd_compare)(a)


if __name__ == "__main__":
    main()
