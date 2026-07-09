# reconcile.py — CLI for blotter reconciliation: EDGELOG vs TradingView / NinjaTrader.
#
# The reconciliation CORE now lives in augur_engine/reconcile.py (importable by the runner,
# the web app, and the tests). This file is the command-line front-end: it reads exported
# CSVs off disk, runs the engine, prints a per-trade diff + a diagnosis, and can auto-pick
# the newest CSV from your Downloads folder (the Chrome-export flow).
#
# HOW TO RUN
#   1) Export the trade list: TradingView → Strategy Tester → "List of Trades" → download;
#      or NinjaTrader → Strategy Analyzer → "Trades" → right-click → Export. (RTH, 5m,
#      Back-adjustment OFF, volume filter 0 for an exact ORB cross-check.)
#   2) python tools/reconcile.py --strategy ORB_3_0.py --inst NQ --from 2026-05-01 \
#          --to 2026-05-29 --cost-pts 0.283 --tv auto --hint trade
#
#   --tv/--nt auto  = newest CSV in Downloads.   --self-test = prove it with no file.
#   --from/--to     = window (clips BOTH sides).  --cost-pts = per-round-turn cost on EDGELOG.
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# The whole reconciliation engine — imported so `python tools/reconcile.py` and the tests
# (which do `import reconcile`) see the same objects the web runner uses.
from augur_engine.reconcile import (  # noqa: E402
    Trade, MULT, CAND_OFFSETS_MIN, _num, _to_dt, _find_col, _find_pnl,
    parse_tv_df, parse_nt_df, parse_tv_text, parse_nt_text, clip_window,
    best_offset, match, diagnose, _rth_flag, build_result, edgelog_blotter,
    run_reconcile, is_false_wick,
)

# Default ORB config used by tools/xcheck_orb.py — so `--strategy ORB_3_0.py` just works.
DEFAULT_ORB = dict(or_bars=3, trade_mode="Both", stop_frac=0.75, vol_filter=0.0,
                   breakout_buf=0.0, target_R=0.0, flat_eod=True)


def _read_csv_flexible(path):
    """Read a CSV whatever the delimiter/encoding (BOM, ; , or tab)."""
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc)
        except Exception:
            continue
    return pd.read_csv(path)


def parse_tv(path, mult):
    """File-based TradingView parser (CLI). Core: augur_engine.reconcile.parse_tv_df."""
    trades, meta = parse_tv_df(_read_csv_flexible(path), mult)
    meta["file"] = os.path.basename(path)
    return trades, meta


def parse_nt(path, mult):
    """File-based NinjaTrader parser (CLI). Core: augur_engine.reconcile.parse_nt_df."""
    trades, meta = parse_nt_df(_read_csv_flexible(path), mult)
    meta["file"] = os.path.basename(path)
    return trades, meta


# ── Text rendering (CLI) — reuses the structured result from the core ────────────
def _fmt_dt(ts):
    return ts.strftime("%Y-%m-%d %H:%M") if ts is not None else "—"


def render(a, a_meta, b, b_meta, offset_min, tol_min):
    """Human-readable report for the CLI, plus the summary dict (for --self-test)."""
    res = build_result(a, a_meta, b, b_meta, offset_min, tol_min)
    s = res["summary"]
    a_label, b_label = res["a_source"], res["b_source"]
    L = []
    P = L.append
    P(f"# Reconciliation: {a_label}  ↔  {b_label}")
    P("")
    P(f"{a_label}: {a_meta.get('strategy','?')} on {a_meta.get('instrument','?')} "
      f"{a_meta.get('timeframe','')} {a_meta.get('session','')} | master {a_meta.get('master','?')} "
      f"| window {a_meta.get('window',('?','?'))[0]} → {a_meta.get('window',('?','?'))[1]}")
    P(f"{b_label}: {b_meta.get('file','?')} | columns used: {b_meta.get('cols','?')}")
    P("")
    P("## Summary")
    P(f"  trades         {a_label}={len(a):<5} {b_label}={len(b):<5} matched={s['matched']}  "
      f"unmatched: {a_label}={s['unmatched_a']} {b_label}={s['unmatched_b']}")
    if s["total_a"] is not None and s["total_b"] is not None:
        P(f"  total PnL ($)  {a_label}={s['total_a']:>11,.2f}  {b_label}={s['total_b']:>11,.2f}  "
          f"Δ={s['total_delta']:>+11,.2f}")
    if offset_min:
        P(f"  tz offset applied to {a_label}: {offset_min:+d} min ({offset_min/60:+g}h)")
    P("")
    P("## Diagnosis")
    for d in res["diagnosis"]:
        P(f"  [{d['tag']}] {d['msg']}")
    P("")
    P("## Matched trades (entry-time aligned)")
    hdr = f"  {'#':>3} {a_label[:4]+' entry':<17} {'side':>4} {'in$':>10} {'Δt(m)':>6} {'Δpnl$':>9} {'Δin_px':>8}"
    P(hdr)
    P("  " + "-" * (len(hdr) - 2))
    for r in res["matched"]:
        sflag = "!" if r["flip"] else ""
        P(f"  {r['n']:>3} {r['entry']:<17} {r['side']+sflag:>4} "
          f"{(r['a_pnl'] if r['a_pnl'] is not None else float('nan')):>10,.2f} "
          f"{r['dt_min']:>6.0f} "
          f"{(r['dpnl'] if r['dpnl'] is not None else float('nan')):>9,.2f} "
          f"{(r['dpx'] if r['dpx'] is not None else float('nan')):>8.2f}")
    for label, key in ((a_label, "unmatched_a"), (b_label, "unmatched_b")):
        if res[key]:
            P("")
            P(f"## Unmatched in {label}")
            for u in res[key][:30]:
                fw = "  ← false-wick (engine takes the intrabar touch; TV needs a close-confirm)" if u.get("false_wick") else ""
                P(f"  {u['entry']}  side={u['side']:+d}  "
                  f"pnl$={u['pnl'] if u['pnl'] is not None else float('nan'):,.2f}{fw}")
    return "\n".join(L), s


# ── Downloads auto-pick + params ────────────────────────────────────────────────
def _downloads_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads")


def resolve_export(path_arg, hint=""):
    """'auto'/'downloads'/'latest' → newest .csv in Downloads (optionally name-filtered)."""
    if not path_arg:
        return None
    if path_arg.lower() in ("auto", "downloads", "latest"):
        d = _downloads_dir()
        cands = [os.path.join(d, f) for f in os.listdir(d)
                 if f.lower().endswith(".csv") and (not hint or hint.lower() in f.lower())]
        if not cands:
            raise SystemExit(f"No .csv in {d}" + (f" matching '{hint}'" if hint else "") + ".")
        newest = max(cands, key=os.path.getmtime)
        print(f"  (auto-picked newest Downloads CSV: {os.path.basename(newest)})")
        return newest
    return path_arg


def parse_params(s):
    """'or_bars=3,stop_frac=0.75,flat_eod=True' → typed dict."""
    out = {}
    for kv in (s or "").split(","):
        kv = kv.strip()
        if not kv or "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if v.lower() in ("true", "false"):
            out[k] = (v.lower() == "true")
        else:
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
    return out


def run_self_test(tol_min):
    """No external file: forge a TV export from the EDGELOG ORB blotter (+4h tz, −$5.66 fee)
    and confirm the tool recovers both."""
    print("SELF-TEST — synthetic TV export from the EDGELOG ORB blotter (+4h tz, −$5.66 fee)\n")
    a, a_meta = edgelog_blotter("ORB_3_0.py", "NQ", "5m", "rth", DEFAULT_ORB,
                                date_from="2026-05-01", date_to="2026-05-29", cost_pts=0.0)
    if not a:
        print("no EDGELOG trades in the window"); return
    b = [Trade(entry_dt=t.entry_dt + pd.Timedelta(hours=4),
               exit_dt=(t.exit_dt + pd.Timedelta(hours=4)) if t.exit_dt is not None else None,
               side=t.side, qty=t.qty, entry_px=t.entry_px, exit_px=t.exit_px,
               pnl_usd=(t.pnl_usd - 5.66) if t.pnl_usd is not None else None) for t in a]
    b_meta = {"source": "TradingView", "file": "<synthetic>", "num_trades": len(b), "cols": {"pnl": "synthetic"}}
    off = best_offset(a, b, tol_min)
    report, summ = render(a, a_meta, b, b_meta, off, tol_min)
    print(report)
    ok = (off == 240 and summ["matched"] == len(a) and summ["unmatched_a"] == 0 and summ["unmatched_b"] == 0)
    print("\nSELF-TEST", "PASS ✅" if ok else "CHECK ⚠️",
          f"(offset={off}m expected +240, matched={summ['matched']}/{len(a)})")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows cp1252 chokes on → σ Δ ✅
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Reconcile EDGELOG backtest trades vs TradingView / NinjaTrader.")
    ap.add_argument("--strategy", default="ORB_3_0.py")
    ap.add_argument("--inst", default="NQ")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--session", default="rth")
    ap.add_argument("--from", dest="date_from", default=None)
    ap.add_argument("--to", dest="date_to", default=None)
    ap.add_argument("--params", default=None, help="k=v,k=v (defaults to ORB config)")
    ap.add_argument("--cost-pts", type=float, default=0.0)
    ap.add_argument("--tv", default=None, help="TV 'List of Trades' CSV, or 'auto' = newest in Downloads")
    ap.add_argument("--nt", default=None, help="NinjaTrader trades CSV, or 'auto' = newest in Downloads")
    ap.add_argument("--hint", default="", help="substring to bias the 'auto' Downloads pick")
    ap.add_argument("--tol-min", type=float, default=10.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        run_self_test(args.tol_min)
        return
    if not (args.tv or args.nt):
        raise SystemExit("Give at least one of --tv / --nt (or --self-test).")

    params = parse_params(args.params) if args.params else (
        DEFAULT_ORB.copy() if args.strategy.upper().startswith("ORB") else {})
    mult = MULT.get(args.inst.upper(), 1)
    a, a_meta = edgelog_blotter(args.strategy, args.inst, args.tf, args.session, params,
                                date_from=args.date_from, date_to=args.date_to,
                                cost_pts=args.cost_pts, mult=mult)
    print(f"EDGELOG: {len(a)} trades | {a_meta['master']} | window "
          f"{a_meta['window'][0]} → {a_meta['window'][1]}\n")
    reports = []
    for path_arg, parser in ((args.tv, parse_tv), (args.nt, parse_nt)):
        if not path_arg:
            continue
        path = resolve_export(path_arg, hint=args.hint)
        if not os.path.exists(path):
            print(f"!! file not found: {path}"); continue
        b, b_meta = parser(path, mult)
        b = clip_window(b, args.date_from, args.date_to)
        b_meta["num_trades"] = len(b)
        off = best_offset(a, b, args.tol_min)
        report, _ = render(a, a_meta, b, b_meta, off, args.tol_min)
        print(report); print("\n" + "=" * 78 + "\n")
        reports.append(report)
    if args.out and reports:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(("\n\n" + "=" * 78 + "\n\n").join(reports))
        print(f"report written → {args.out}")


if __name__ == "__main__":
    main()
