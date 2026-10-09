"""tools/shadow_legs_report.py -- READ-ONLY per-leg report of the Webull paper book's SHADOW
LEGS (owner 2026-09-28, api/cloud_signal.py SHADOW_LEGS) beside the live NOISE primary, so
the Custom ML chat and MANAGER can read the would-be trades without opening a CSV.

Reads, never writes:
  <home>/cloud_signal/shadow/signals.csv   the shadow ledger (api/cloud_signal.shadow_paths):
                                           NOISE_422_PLAIN, NOISE_422_FIXED, NOISE_422_KEEL,
                                           ENGUQ_335 -- no orders, ever
  <home>/cloud_signal/signals.csv          the live ledger, for the primary NOISE_382 (+KEEL)
                                           and, derived from the same rows, NOISE_382 plain
                                           (its size with the KEEL multiplier divided back out)
  <home>/cloud_signal/keel/*_summary.json  how fresh each learned KEEL state is

<home> is EDGELOG_HOME by default (the box: ~/edgelog), or --home: a folder laid out the
same way, e.g. one of tools/pull_box_ledgers.py's C:\\EdgeLog\\box_backup\\<stamp> copies.

P&L per closed trade, in dollars = (exit ref_price - entry ref_price) x side x base shares
(--base-shares, default 10, the book's base unit) x the trade's "size". A KEEL leg's "size"
column is ALREADY plugin size x keel_size (api/cloud_signal.py SIGNAL_COLS), so it is never
multiplied by keel_size a second time. These are SIGNAL prices (the bar the engine decided
on), not Webull fills -- the live primary's real fills live in qqq_exec/trades.csv; the
pre-registered scoring (docs/PREREG_noise_shadow_forward_2026-09-28.md) is the Custom ML
chat's job, this is the quick read. Open trades (an ENTRY with no EXIT yet) are counted,
never priced.

SEEDED trades (2026-10-07, MANAGER #87): a shadow leg that was already holding a trade when
it cold-started writes that trade's ENTRY at its own entry time and price with a reason that
starts "seeded=1" (api/cloud_signal.py SEED_OPEN_FORMAT). It is a real would-be trade and is
counted and priced like any other; "seeded" says how many of a leg's trades came that way.

Usage:  python tools/shadow_legs_report.py [--home DIR] [--since YYYY-MM-DD]
                                           [--base-shares 10] [--json]
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASE_SHARES = 10
SEEDED_TAG = "seeded=1"      # api/cloud_signal.py SEEDED_REASON_TAG
PRIMARY_LEG = "NOISE_382"
PRIMARY_PLAIN = "NOISE_382 plain (derived)"
KEEL_SUMMARY_LEGS = ("NOISE_382", "NOISE_422_KEEL")


def read_rows(path, strict=False):
    """Every row of a signals.csv as a dict; [] when the file is missing or unreadable.
    strict=True raises the OSError instead (api/qqq_exec.py's shadow_trades block, which
    says why it has no rows rather than showing an empty list as if the ledger were empty)."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        if strict:
            raise
        return []


def _f(x, default=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v


def pair_trades(rows, since=None):
    """{leg: [trade]} from ENTRY/EXIT rows paired by trade_id -- one trade per id, its
    ENTRY's side/price/size and its EXIT's price (None while still open). SEED rows and rows
    with no trade_id are skipped; a trade whose ENTRY is not in `rows` (an EXIT only) too.
    `since` (YYYY-MM-DD) keeps trades ENTERED on or after that date."""
    entries, exits = {}, {}
    for r in rows:
        ev = str(r.get("event") or "").strip().upper()
        tid = str(r.get("trade_id") or "").strip()
        if ev not in ("ENTRY", "EXIT") or not tid:
            continue
        key = (r.get("leg") or "", tid)
        (entries if ev == "ENTRY" else exits).setdefault(key, r)
    out = {}
    for (leg, tid), e in entries.items():
        if since and str(e.get("ref_time") or "")[:10] < since:
            continue
        x = exits.get((leg, tid))
        out.setdefault(leg, []).append({
            "trade_id": tid, "side": e.get("side") or "long",
            "entry_time": e.get("ref_time"), "entry_px": _f(e.get("ref_price")),
            "exit_time": (x or {}).get("ref_time"),
            "exit_px": _f((x or {}).get("ref_price")) if x else None,
            "size": _f(e.get("size"), 1.0) or 1.0,
            "keel_size": _f(e.get("keel_size")),
            "seeded": str(e.get("reason") or "").startswith(SEEDED_TAG),
        })
    for trades in out.values():
        trades.sort(key=lambda t: str(t["entry_time"]))
    return out


def trade_dollars(t, base_shares=BASE_SHARES, size=None):
    """Would-be $ P&L of one CLOSED trade, None while open. `size` overrides t["size"]."""
    if t["exit_px"] is None or t["entry_px"] is None:
        return None
    sign = -1.0 if str(t["side"]).lower() == "short" else 1.0
    s = t["size"] if size is None else size
    return (t["exit_px"] - t["entry_px"]) * sign * base_shares * s


def plain_twin(trades):
    """The same trades at their PLUGIN size only: size / keel_size where keel_size is set
    (the live NOISE_382 rows' KEEL multiplier divided back out -- arm A1 of the
    pre-registration). A row with no keel_size keeps its size."""
    out = []
    for t in trades:
        k = t.get("keel_size")
        out.append(dict(t, size=t["size"] / k if k else t["size"], keel_size=None))
    return out


def summarize(trades, base_shares=BASE_SHARES):
    pnls = [p for p in (trade_dollars(t, base_shares) for t in trades) if p is not None]
    wins = [p for p in pnls if p > 0]
    return {"trades": len(pnls), "open": len(trades) - len(pnls),
            "net_usd": round(sum(pnls), 2),
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else None,
            "largest_win_usd": round(max(pnls), 2) if pnls else None,
            "largest_loss_usd": round(min(pnls), 2) if pnls else None,
            "avg_size": round(sum(t["size"] for t in trades) / len(trades), 4) if trades else None,
            "seeded": sum(1 for t in trades if t.get("seeded"))}


def keel_freshness(home):
    """{leg: {"data_through", "built_at"}} from each learned KEEL leg's summary, {} fields
    None when a summary is missing (NOISE_422_KEEL before its first build)."""
    out = {}
    for leg in KEEL_SUMMARY_LEGS:
        p = os.path.join(home, "cloud_signal", "keel", f"{leg}_v12_summary.json")
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            out[leg] = {"data_through": s.get("data_through"), "built_at": s.get("built_at")}
        except (OSError, ValueError):
            out[leg] = {"data_through": None, "built_at": None}
    return out


def build_report(home, since=None, base_shares=BASE_SHARES, shadow_legs=None):
    """The whole report as a dict: {"legs": {name: summary}, "keel": ..., "ledgers": ...}.
    Shadow legs come from api/cloud_signal.SHADOW_LEGS (every one is listed, traded or
    not), plus any other leg found in the shadow ledger."""
    from api import cloud_signal as cs
    live_paths = cs._paths(home=home)
    spaths = cs.shadow_paths(live_paths)
    shadow = pair_trades(read_rows(spaths["signals_path"]), since=since)
    live = pair_trades(read_rows(live_paths["signals_path"]), since=since)
    primary = live.get(PRIMARY_LEG, [])
    legs = {f"{PRIMARY_LEG} (live primary)": summarize(primary, base_shares),
            PRIMARY_PLAIN: summarize(plain_twin(primary), base_shares)}
    names = list(cs.SHADOW_LEGS if shadow_legs is None else shadow_legs)
    names += sorted(k for k in shadow if k not in names)
    for leg in names:
        legs[leg] = summarize(shadow.get(leg, []), base_shares)
    return {"legs": legs, "keel": keel_freshness(home), "base_shares": base_shares,
            "since": since, "ledgers": {"shadow": spaths["signals_path"],
                                        "live": live_paths["signals_path"]}}


def _fmt(v, money=False):
    if v is None:
        return "-"
    if money:
        return f"{v:,.2f}"
    return str(v)


def print_report(rep):
    print(f"Shadow legs report -- base {rep['base_shares']} shares x size; signal prices, not fills"
          + (f"; trades entered since {rep['since']}" if rep["since"] else ""))
    print(f"  shadow ledger: {rep['ledgers']['shadow']}")
    print(f"  live ledger:   {rep['ledgers']['live']}")
    print()
    for leg, s in rep["legs"].items():
        wr = "-" if s["win_rate"] is None else f"{100 * s['win_rate']:.1f}%"
        print(f"{leg}")
        print(f"    trades {s['trades']} closed, {s['open']} open; would-be P&L "
              f"${_fmt(s['net_usd'], True)}; win rate {wr}; largest win "
              f"${_fmt(s['largest_win_usd'], True)}; largest loss ${_fmt(s['largest_loss_usd'], True)}"
              f"; average size {_fmt(s['avg_size'])}"
              + (f"; {s['seeded']} carried from the leg's cold start" if s.get("seeded") else ""))
    print()
    for leg, k in rep["keel"].items():
        print(f"KEEL state {leg}: trained through {k['data_through'] or '(no summary yet)'}"
              + (f", built {k['built_at']}" if k["built_at"] else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=None,
                    help="EDGELOG_HOME-shaped folder to read (default: this host's EDGELOG_HOME)")
    ap.add_argument("--since", default=None, help="only trades entered on/after YYYY-MM-DD")
    ap.add_argument("--base-shares", type=float, default=BASE_SHARES)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args(argv)
    from api import cloud_signal as cs
    rep = build_report(a.home or cs.edgelog_home(), since=a.since, base_shares=a.base_shares)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
