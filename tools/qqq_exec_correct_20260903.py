r"""One-off, auditable repair of the two 2026-09-03 QQQ shadow trades.

WHY. Before v73.469, api/qqq_exec.py marked and CLOSED open lots at the lot's ENTRY
NQ price instead of the live one (_mark_and_check_breaker / _close_all both passed
`lot["last_nq_px"] or lot["nq_entry_px"]`). The first two shadow trades ever recorded
-- ORB and NOISE, opened 2026-09-03 12:30 ET and flattened by the 15:58 EOD rail --
were therefore booked at their own entry price: pnl -$0.10 each (pure slippage), when
NQ had actually risen 24.50 points in their favour.

WHAT THIS DOES. Reprices ONLY those two EOD exits at the real NQ 10s close at/just
before the flatten (29522.75 @ 2026-09-03 15:58:00 ET, from C:\EdgeLog\ohlc_addon\
NQ_10s.csv), through the same ratio and the same slippage rule the fixed code uses, and
rewrites the matching rows of trades.csv and orders.csv in place. Every other row is
copied through untouched. A before/after record is appended to corrections.log so the
edit is never silent. Idempotent: re-running finds nothing to correct.

Run with the runner STOPPED (it appends to these files every 5s during RTH).
Usage: python tools/qqq_exec_correct_20260903.py [--apply]   (default: dry run)
"""
import argparse, csv, os, shutil
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:
    NY = None

DIR = os.environ.get("EDGELOG_QQQ_EXEC_DIR", r"C:\EdgeLog\qqq_exec")
TRADES = os.path.join(DIR, "trades.csv")
ORDERS = os.path.join(DIR, "orders.csv")
LOG = os.path.join(DIR, "corrections.log")
NQ10S = (r"C:\EdgeLog\ohlc_addon\NQ_10s.csv", r"C:\EdgeLog\ohlc\NQ_10s.csv")

EXIT_TS = "2026-09-03 15:58:05"
SLIP = 0.01
TARGETS = [("ORB", "2026-09-03 12:30:18"), ("NOISE", "2026-09-03 12:30:16")]


def nq_close_at(ts_et):
    target = datetime.strptime(ts_et, "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY).timestamp()
    for path in NQ10S:
        if not os.path.exists(path):
            continue
        best = None
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    t = float(row["time"]); c = float(row["close"])
                except Exception:
                    continue
                if t <= target and (best is None or t > best[1]):
                    best = (c, t)
        if best:
            return best
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the files (default: dry run)")
    a = ap.parse_args()

    nq_exit, nq_ts = nq_close_at(EXIT_TS)
    if nq_exit is None:
        raise SystemExit("no NQ 10s close found for " + EXIT_TS)
    print(f"NQ close used for the exit: {nq_exit} @ "
          f"{datetime.fromtimestamp(nq_ts, NY).strftime('%F %T')} ET")

    trades = list(csv.DictReader(open(TRADES, encoding="utf-8", newline="")))
    orders = list(csv.DictReader(open(ORDERS, encoding="utf-8", newline="")))
    changes = []

    for t in trades:
        key = (t["leg"], t["entry_ts"])
        if key not in TARGETS or t["exit_ts"] != EXIT_TS:
            continue
        entry_fill = float(t["entry_px"])
        entry_raw = entry_fill - SLIP                      # long entry paid +slip
        nq_entry = None
        for o in orders:
            if o["leg"] == t["leg"] and o["action"] == "ENTER" and o["ts_et"] == t["entry_ts"]:
                nq_entry = float(o["nq_px"])
        if nq_entry is None:
            print(f"  !! no ENTER order row for {key}, skipped"); continue
        ratio = nq_entry / entry_raw                        # the ratio actually used that day
        exit_raw = nq_exit / ratio
        exit_fill = round(exit_raw - SLIP, 4)               # long exit sells, slip against us
        shares = int(float(t["shares"]))
        pnl = round((exit_fill - entry_fill) * shares, 2)
        if abs(float(t["pnl"]) - pnl) < 0.005:
            print(f"  {t['leg']}: already correct, skipping"); continue
        changes.append((t["leg"], dict(t), {"exit_px": f"{exit_fill}", "pnl": f"{pnl}",
                                            "nq_pnl_points": f"{round(nq_exit - nq_entry, 2)}"}))
        print(f"  {t['leg']}: ratio {ratio:.4f} | exit ${float(t['exit_px']):.4f} -> "
              f"${exit_fill:.4f} | pnl ${float(t['pnl']):.2f} -> ${pnl:.2f}")

    if not changes:
        print("nothing to correct."); return
    if not a.apply:
        print("\nDRY RUN -- re-run with --apply to write."); return

    for f in (TRADES, ORDERS):
        shutil.copy2(f, f + ".pre-correction")
    for leg, before, after in changes:
        for t in trades:
            if t["leg"] == leg and t["entry_ts"] == before["entry_ts"] and t["exit_ts"] == EXIT_TS:
                t.update(after)
        for o in orders:
            if o["leg"] == leg and o["action"] == "EXIT" and o["ts_et"] == EXIT_TS:
                o["qqq_px"] = after["exit_px"]
                o["nq_px"] = f"{nq_exit}"
    for path, rows in ((TRADES, trades), (ORDERS, orders)):
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now(NY).strftime('%F %T')} ET  "
                f"tools/qqq_exec_correct_20260903.py\n")
        f.write(f"reason: pre-v73.469 bug closed lots at their ENTRY NQ price; repriced the "
                f"2026-09-03 EOD exits at the real NQ close {nq_exit} @ 15:58:00 ET\n")
        for leg, before, after in changes:
            f.write(f"  {leg}: exit_px {before['exit_px']} -> {after['exit_px']}, "
                    f"pnl {before['pnl']} -> {after['pnl']}, "
                    f"nq_pnl_points {before['nq_pnl_points']} -> {after['nq_pnl_points']}\n")
    print(f"\napplied. backups: *.pre-correction, audit trail: {LOG}")


if __name__ == "__main__":
    main()
