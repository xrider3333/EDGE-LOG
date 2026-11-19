"""tools/qqq_orders_first_replay.py -- ORDERS FIRST proof (2026-11-18): replays cached
sessions through api.cloud_signal_stream.run_stream_aware_step twice -- OLD order (stream
extras, then step()) and NEW order (step() first, extras after, on the pre-step snapshot)
-- in two throwaway stores, and diffs the order-driving rows of signals.csv.

A synthetic stream hand-off (the REST bar itself, connected/fresh) is published at every
5m boundary so the extras really run their dry engine runs (ORB + NOISE incl. KEEL):
  scenario "split": stream bar at B+0.5 s (REST not usable yet), REST decided at B+1.5 s
  scenario "same" : stream and REST both first seen at B+1.5 s (the pre-step snapshot path)

Offline only (fetch=False, isolated_paths copies) -- never touches the live ledger.
api/qqq_exec.py is unchanged, so identical signal rows => identical orders (signal, side,
qty via size/keel_size/shares, price via ref_price/stop/target).

Usage: python tools/qqq_orders_first_replay.py 2026-11-11 2026-11-12 ... [--scenario both]
Exit 0 = 0 diffs.
"""
import argparse
import csv
import datetime as _dt
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import cloud_signal as cs                     # noqa: E402
from api import cloud_signal_stream as css             # noqa: E402
from api import webull_stream as ws                    # noqa: E402

DRY_RUNS = [0]
_real_dry = css._dry_run_decision


def _counted_dry(*a, **k):
    DRY_RUNS[0] += 1
    return _real_dry(*a, **k)


css._dry_run_decision = _counted_dry

ORDER_COLS = ("leg", "event", "side", "ref_time", "ref_price", "shares", "reason",
              "trade_id", "size", "keel_size", "stop_px", "target_px")


def _old_order(now, paths):
    """The pre-2026-11-18 run_stream_aware_step body, verbatim in effect."""
    css._run_stream_extras(now, cs.CROWN_LEGS, paths, lambda *a, **k: None)
    return cs.step(now=now, legs=cs.CROWN_LEGS, paths=paths, fetch=False, warnings={})


def _new_order(now, paths):
    return css.run_stream_aware_step(now=now, paths=paths, fetch=False, warnings={},
                                     log=lambda *a, **k: None)


def _publish(paths, df, bar_start_epoch):
    row = df[df["time"] == bar_start_epoch]
    if not len(row):
        return
    r = row.iloc[0]
    payload = {"time": int(bar_start_epoch), "open": float(r["open"]), "high": float(r["high"]),
               "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"]),
               "connected": True, "fresh": True, "bars_since_connect": 99}
    path = ws.closed_bar_handoff_path("5m", home=paths["home"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _run(day, runner, scenario):
    paths = cs.isolated_paths()
    try:
        df = cs.historical_bars("5m", paths)
        tz = cs._zi(cs.TZ)
        d = _dt.date.fromisoformat(day)
        t = _dt.datetime.combine(d, cs.RTH_OPEN, tzinfo=tz) + _dt.timedelta(minutes=5)
        end = _dt.datetime.combine(d, cs.RTH_CLOSE, tzinfo=tz)
        out = []
        while t <= end:
            bar_start = int(t.timestamp()) - 300
            if scenario == "split":
                _publish(paths, df, bar_start)
                out += runner(t + _dt.timedelta(seconds=0.5), paths)
            else:
                _publish(paths, df, bar_start)
            out += runner(t + _dt.timedelta(seconds=1.5), paths)
            t += _dt.timedelta(minutes=5)
        with open(paths["signals_path"], encoding="utf-8", newline="") as f:
            rows = [tuple(r.get(c, "") for c in ORDER_COLS) for r in csv.DictReader(f)] \
                if os.path.exists(paths["signals_path"]) else []
        shadow = css._load_shadow(paths)
        return rows, shadow
    finally:
        shutil.rmtree(paths["home"], ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("days", nargs="+")
    ap.add_argument("--scenario", choices=("split", "same", "both"), default="both")
    a = ap.parse_args(argv)
    scen = ("split", "same") if a.scenario == "both" else (a.scenario,)
    total_rows = total_diffs = 0
    for day in a.days:
        for sc in scen:
            DRY_RUNS[0] = 0
            old, _ = _run(day, _old_order, sc)
            d_old = DRY_RUNS[0]
            DRY_RUNS[0] = 0
            new, _ = _run(day, _new_order, sc)
            d_new = DRY_RUNS[0]
            n_ord = sum(1 for r in old if r[1] in ("ENTRY", "EXIT", "LEVELS"))
            diffs = [(i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]
            if len(old) != len(new):
                diffs.append(("len", len(old), len(new)))
            total_rows += n_ord
            total_diffs += len(diffs)
            print(f"{day} {sc:5s}: rows old={len(old)} new={len(new)} "
                  f"order rows={n_ord} diffs={len(diffs)} dry runs old={d_old} new={d_new}")
            for x in diffs[:5]:
                print("   DIFF", x)
    print(f"TOTAL order rows compared={total_rows} diffs={total_diffs}")
    return 0 if total_diffs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
