"""One-off, idempotent backfill for the QQQ SHADOW adapter's NT-parity feature
(api/qqq_exec.py feature 1 -- see its module docstring).

The two trades.csv rows recorded on 2026-09-03 (ORB and NOISE, entry 12:30 / exit
15:58 ET) predate the NT-parity columns, so they carry no nt_entry_exec_id /
nt_exit_exec_id / etc. This script fills those columns in by joining each row to its
real NinjaTrader fill in C:\\EdgeLog\\fills.csv (matched by leg + exec_id, hand-verified
against the recorded shadow orders -- see JOIN below), and marks both rows
nt_reconstructed=1 so `_trade_parity` always reports their parity_note as
"reconstructed" -- they must never be mistaken for a live-captured parity check.

Also seeds the one historical feed-uptime day (2026-09-03, the NinjaTrader hang) into
state.json's rolling `feed_days` map, since that outage happened before the feed-uptime
feature existed and would otherwise silently read as a normal, valid day.

Never edits a forward-test record silently (repo rule): dry-run by default, --apply
writes for real, a trades.csv.pre-backfill backup is written before any change, and a
dated entry is appended to corrections.log. Idempotent: running twice with --apply is a
safe no-op the second time (both rows already carry nt_entry_exec_id and the
feed_days seed already exists).

Run:
    python tools/qqq_exec_backfill_parity.py            # dry run, prints before/after
    python tools/qqq_exec_backfill_parity.py --apply     # writes for real
"""
import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe          # noqa: E402
from api import nt_sync                 # noqa: E402

OUT_DIR = qe.OUT_DIR
TRADES_CSV = qe.TRADES_CSV
ORDERS_CSV = qe.ORDERS_CSV
STATE_PATH = qe.STATE_PATH
CORRECTIONS_LOG = os.path.join(OUT_DIR, "corrections.log")
FILLS_PATH = nt_sync.DEFAULT_FILLS

TARGET_DAY = "2026-09-03"

# Hand-verified joins: each entry exec id's fills.csv price matches the shadow's
# recorded ENTER order nq_px exactly (29498.25 for both legs); each exit exec id is the
# real NT "Exit on session close" fill that landed ~1-2 min after the shadow's flat_by
# rail had already force-closed the lot off the live NQ feed (hence "reconstructed" --
# the shadow trade itself was NOT priced off this exact fill).
JOIN = {
    "ORB": {"entry_exec_id": "24e9f9b1912d4e5dab87dfc01adb1a65",
            "exit_exec_id": "2b91c4aa64594269a38bd47faaf779f7", "nt_qty": 2},
    "NOISE": {"entry_exec_id": "459311891613_1",
              "exit_exec_id": "459311891630_1", "nt_qty": 13},
}

# 2026-09-03 feed-uptime seed (feature 2): the NinjaTrader hang lost roughly the first
# 3 hours of the session (market window opens 09:25 ET; the day's first shadow order
# wasn't until 12:30 ET -- see orders.csv). Represented as synthetic 5s-tick counts over
# the 09:25-16:05 window (400 min = 4800 ticks) so it derives through the same
# uptime_pct/stale_min formula as a live-recorded day. This is the best that is
# knowable after the fact (nt_recover.log has since rotated past that date) -- honestly
# marked as reconstructed via its `note`.
FEED_SEED_DAY = "2026-09-03"
FEED_SEED = {
    "ticks": 4800, "stale_ticks": 2220,          # -> uptime_pct 0.5375, stale_min 185.0
    "first_tick_et": "12:30", "last_tick_et": "16:00",
    "note": "reconstructed from the recovery log -- feed was down ~185 min after the "
            "open while NinjaTrader was restarting; the adapter's first shadow fill "
            "that day was 12:30 ET",
}


def _fill_by_exec_id(fills, exec_id):
    for f in fills:
        if f["exec_id"] == exec_id:
            return f
    return None


def _ratio_from_orders(orders, leg, action, day):
    for o in orders:
        if o.get("leg") == leg and o.get("action") == action and str(o.get("ts_et") or "")[:10] == day:
            try:
                nq, qqq = float(o["nq_px"]), float(o["qqq_px"])
                if qqq:
                    return round(nq / qqq, 6)
            except Exception:
                continue
    return None


def _read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    a = ap.parse_args()
    mode = "APPLY" if a.apply else "DRY RUN"

    if not os.path.exists(TRADES_CSV):
        print(f"no trades.csv at {TRADES_CSV} -- nothing to backfill")
        return 1

    rows = _read_rows(TRADES_CSV)
    orders = _read_rows(ORDERS_CSV)
    fills = nt_sync.parse_fills(FILLS_PATH)
    for f in fills:
        f["dt"] = nt_sync._to_ny(f["dt"])

    targets = [r for r in rows if r.get("leg") in JOIN
               and str(r.get("entry_ts") or "")[:10] == TARGET_DAY]
    if not targets:
        print(f"[trades.csv] no {TARGET_DAY} ORB/NOISE rows found -- nothing to backfill "
             f"(already migrated away, or trades.csv trimmed past them)")
    already_done = [r for r in targets if str(r.get("nt_entry_exec_id") or "").strip()]

    print(f"=== {mode}: tools/qqq_exec_backfill_parity.py ===")
    print(f"trades.csv: {TRADES_CSV}")
    print(f"target rows found: {len(targets)}, already backfilled: {len(already_done)}\n")

    changed_any = False
    new_rows = []
    log_lines = []
    for r in rows:
        leg = r.get("leg")
        if r not in targets:
            new_rows.append(r)
            continue
        if str(r.get("nt_entry_exec_id") or "").strip():
            print(f"[{leg}] already backfilled -- skipped (idempotent)")
            new_rows.append(r)
            continue
        j = JOIN[leg]
        ef = _fill_by_exec_id(fills, j["entry_exec_id"])
        xf = _fill_by_exec_id(fills, j["exit_exec_id"])
        if ef is None or xf is None:
            print(f"[{leg}] WARN: could not find matching NT fill(s) in fills.csv -- skipped")
            new_rows.append(r)
            continue

        before = dict(r)
        after = dict(r)
        after["nt_entry_exec_id"] = ef["exec_id"]
        after["nt_entry_ts"] = ef["dt"].strftime("%Y-%m-%d %H:%M:%S")
        after["nt_entry_px"] = ef["price"]
        after["nt_exit_exec_id"] = xf["exec_id"]
        after["nt_exit_ts"] = xf["dt"].strftime("%Y-%m-%d %H:%M:%S")
        after["nt_exit_px"] = xf["price"]
        after["nt_qty"] = j["nt_qty"]
        ratio_entry = _ratio_from_orders(orders, leg, "ENTER", TARGET_DAY)
        ratio_exit = _ratio_from_orders(orders, leg, "EXIT", TARGET_DAY)
        after["ratio_at_entry"] = ratio_entry if ratio_entry is not None else ""
        after["ratio_at_exit"] = ratio_exit if ratio_exit is not None else ""
        after["nt_reconstructed"] = "1"

        parity_before = qe._trade_parity(before)
        parity_after = qe._trade_parity(after)

        print(f"[{leg}] BEFORE: nt_entry_exec_id={before.get('nt_entry_exec_id') or '(none)'} "
             f"nt_exit_exec_id={before.get('nt_exit_exec_id') or '(none)'} "
             f"parity={parity_before}")
        print(f"[{leg}] AFTER:  nt_entry_exec_id={after['nt_entry_exec_id']} "
             f"nt_entry_px={after['nt_entry_px']} nt_entry_ts={after['nt_entry_ts']}  "
             f"nt_exit_exec_id={after['nt_exit_exec_id']} nt_exit_px={after['nt_exit_px']} "
             f"nt_exit_ts={after['nt_exit_ts']}  ratio_at_entry={after['ratio_at_entry']} "
             f"ratio_at_exit={after['ratio_at_exit']}")
        print(f"[{leg}] AFTER parity: {parity_after}\n")

        log_lines.append(
            f"  {leg}: nt_entry_exec_id -> {after['nt_entry_exec_id']} "
            f"(px {after['nt_entry_px']} @ {after['nt_entry_ts']}); "
            f"nt_exit_exec_id -> {after['nt_exit_exec_id']} "
            f"(px {after['nt_exit_px']} @ {after['nt_exit_ts']}); "
            f"ratio_at_entry={after['ratio_at_entry']} ratio_at_exit={after['ratio_at_exit']}; "
            f"parity_note={parity_after.get('parity_note')}")
        new_rows.append(after)
        changed_any = True

    # feed_days seed (feature 2) -----------------------------------------------------
    state = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            print(f"WARN: could not read state.json ({type(e).__name__}: {e}) -- "
                 f"feed_days seed skipped")
            state = None
    feed_days = (state or {}).get("feed_days") or {}
    seed_already = FEED_SEED_DAY in feed_days
    print(f"[feed_days] {FEED_SEED_DAY} seed already present: {seed_already}")
    if not seed_already:
        print(f"[feed_days] would seed: {FEED_SEED}")

    if not a.apply:
        print(f"\nDRY RUN -- no files written. Re-run with --apply to write "
             f"{'trades.csv + state.json' if (changed_any or not seed_already) else '(nothing to change)'}.")
        return 0

    if not changed_any and seed_already:
        print("\nAPPLY: nothing to change (already fully backfilled) -- idempotent no-op.")
        return 0

    ts = datetime.now().strftime("%Y%m%d")
    log_entry = [f"\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ET  "
                f"tools/qqq_exec_backfill_parity.py --apply"]

    if changed_any:
        backup = TRADES_CSV + ".pre-backfill"
        if not os.path.exists(backup):
            shutil.copy2(TRADES_CSV, backup)
            print(f"backup written: {backup}")
        else:
            print(f"backup already exists, left as-is: {backup}")
        with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=qe.TRADE_COLS)
            w.writeheader()
            for r in new_rows:
                w.writerow({c: r.get(c, "") for c in qe.TRADE_COLS})
        print(f"trades.csv rewritten with NT-parity columns for {TARGET_DAY}")
        log_entry.append("reason: feature-1 NT-parity backfill for the 2026-09-03 "
                         "ORB/NOISE rows (joined to real fills.csv exec ids)")
        log_entry.extend(log_lines)

    if not seed_already and state is not None:
        state.setdefault("feed_days", {})[FEED_SEED_DAY] = dict(FEED_SEED)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp, STATE_PATH)
        print(f"state.json feed_days seeded for {FEED_SEED_DAY}")
        log_entry.append(f"reason: feature-2 feed-uptime seed for {FEED_SEED_DAY} "
                         f"({FEED_SEED['note']})")

    if len(log_entry) > 1:
        with open(CORRECTIONS_LOG, "a", encoding="utf-8") as f:
            f.write("\n".join(log_entry) + "\n")
        print(f"corrections.log updated: {CORRECTIONS_LOG}")

    print("\nAPPLY complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
