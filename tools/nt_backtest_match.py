"""Match the NinjaTrader self-dumped BACKTEST blotters against the EDGELOG paper trades,
and publish the result so the PAPER trade list can mark each row.

WHY THIS EXISTS (owner 2026-08-26: "if trades match in NT, then annotate that in the
trade list. like EL has a check so NT should").

The trade list already carried an NT pill, but it could only ever read the nightly
reconcile, which matches against LIVE demo FILLS. Live fills only exist for the hours
NinjaTrader was actually up and only for the legs it actually trades, so the pill read
"NT ?" on essentially every historical row -- it looked broken because it had nothing to
say.

A second, independent source of truth already existed and was going unused: each strategy
writes its own backtest blotter to C:\\EdgeLog\\nt_backtest on State.Terminated (see
tools/nt/EdgeLogNOISE.cs DumpBlotter). That is NinjaTrader running the SAME config over
the SAME history, which is exactly the question "did NinjaTrader see this trade too".

So this reads those dumps and answers it. It is deliberately a DIFFERENT claim from a
live fill and the UI renders it differently:
    NT ✓  a live demo fill matched this trade      (nightly reconcile, strongest)
    NT ≈  NinjaTrader's backtest produced it       (this tool)
    NT ✗  the engine signalled it and NT did not
    NT ?  nothing has checked this date

TWO TIMESTAMP OFFSETS, both undone here (same as tools/reconcile_nt_dump.py):
  1. The dump writes UTC, so the PC's timezone never enters into it.
  2. NinjaTrader stamps a bar at its CLOSE; the AUGUR engine stamps at its OPEN. So an NT
     entry on the 09:45 bar is the engine's 09:40 bar. --bar-min subtracts one bar width.

A KNOWN, EXPECTED DIFFERENCE, stated so nobody reads it as a fault: the engine enters AT
the signal bar's close, while NinjaTrader's market order placed on that close fills at the
NEXT bar's open. So NT entries legitimately sit one bar later at a slightly different
price. The tolerance below is sized for that, not to paper over disagreement.

Run:  python tools/nt_backtest_match.py            # newest dump per config
      python tools/nt_backtest_match.py --dry-run  # print, publish nothing
"""
import argparse
import csv
import datetime as dt
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DUMP_DIR = r"C:\EdgeLog\nt_backtest"
DEFAULT_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

# Which paper leg a dump describes is decided by its CONFIG, never by its filename: two
# EdgeLogNOISE dumps written minutes apart are the crown and its control, and the only
# thing separating them is the header's filter flags. Each rule is (strategy, {header
# key: required value}) -> leg key.
CONFIG_RULES = [
    ("EdgeLogNOISE",   {"skipBotShort": "True",  "volSkipOn": "True"},  "NOISE_SBS_V90"),
    ("EdgeLogNOISE",   {"skipBotShort": "False", "volSkipOn": "False"}, "NOISE_225"),
    # The #226 ETH config: this is the leg the parity row was built to reproduce. It is
    # archived on the board (replaced by #265 on 08-21) but its trades still show.
    ("EdgeLogENGUQ1m", {"tlLen": "170", "emaLen": "1380"},              "ENGUQ"),
    ("EdgeLogORB230",  {},                                              "ORB"),
]

# Entry-time tolerance. The engine fills at the signal close and NinjaTrader at the next
# bar's open, so one bar of drift is EXPECTED, not slack: 5m legs get 6 minutes, 1m legs
# get 2. Anything looser would start pairing unrelated trades.
TOL_MIN = {"1m": 2, "5m": 6}


def _read_dump(path):
    head, rows = {}, []
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        body = []
        for line in fh:
            if line.startswith("#"):
                for k, v in re.findall(r"(\w+)=([^\s]+)", line[1:]):
                    head[k] = v
            else:
                body.append(line)
    for r in csv.DictReader(body):
        try:
            rows.append({
                "entry": dt.datetime.strptime(r["entry_utc"], "%Y-%m-%d %H:%M:%S")
                                   .replace(tzinfo=dt.timezone.utc),
                "entry_px": float(r["entry_px"]),
                "exit_px": float(r["exit_px"]),
                "pnl": float(r["pnl_usd"]),
                "side": int(r["side"]),
            })
        except Exception:
            continue
    return head, rows


def _leg_for(head):
    strat = head.get("strategy", "")
    for s, need, leg in CONFIG_RULES:
        if s != strat:
            continue
        if all(str(head.get(k)) == v for k, v in need.items()):
            return leg
    return None


def _bar_minutes(head):
    b = str(head.get("bars", ""))
    m = re.search(r"Minute-(\d+)", b)
    return int(m.group(1)) if m else 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--cred", default=os.path.join(ROOT, "serviceAccount.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # newest dump per (strategy, resolved leg) -- an older run of the same config is
    # superseded, but a DIFFERENT config in the same strategy file is its own answer.
    best = {}
    for path in sorted(glob.glob(os.path.join(DUMP_DIR, "*.csv"))):
        head, rows = _read_dump(path)
        leg = _leg_for(head)
        if not leg or not rows:
            continue
        mtime = os.path.getmtime(path)
        if leg not in best or mtime > best[leg][0]:
            best[leg] = (mtime, path, head, rows)

    if not best:
        print("no usable dumps in " + DUMP_DIR)
        return 1

    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(a.cred))
    db = firestore.client()
    col = db.collection("users").document(a.uid).collection("paper_trades")

    out, summary = {}, []
    for leg, (_mt, path, head, rows) in sorted(best.items()):
        bar = _bar_minutes(head)
        tol = dt.timedelta(minutes=TOL_MIN.get("1m" if bar == 1 else "5m", 6))
        # NT stamps at bar close; the engine stamps at bar open.
        nt = [dict(r, entry=r["entry"] - dt.timedelta(minutes=bar)) for r in rows]

        paper = []
        for d in col.where("leg", "==", leg).stream():
            t = d.to_dict() or {}
            iso = t.get("entryIso")
            if not iso:
                continue
            try:
                e = dt.datetime.fromisoformat(iso).astimezone(dt.timezone.utc)
            except Exception:
                continue
            paper.append({"iso": iso, "e": e, "px": t.get("entry_px")})

        if not paper:
            continue
        # Only judge inside the window the dump actually covers. Outside it NinjaTrader
        # was never asked, and calling that a miss would be a lie.
        lo, hi = min(r["entry"] for r in nt), max(r["entry"] for r in nt)
        used, matched, missed = set(), 0, 0
        for p in paper:
            if not (lo <= p["e"] <= hi):
                continue                      # not covered by this backtest window
            pick, bestd = None, None
            for i, r in enumerate(nt):
                if i in used:
                    continue
                d_ = abs((p["e"] - r["entry"]).total_seconds())
                if d_ <= tol.total_seconds() and (bestd is None or d_ < bestd):
                    pick, bestd = i, d_
            if pick is None:
                out[p["iso"]] = {"leg": leg, "matched": False}
                missed += 1
            else:
                used.add(pick)
                r = nt[pick]
                out[p["iso"]] = {"leg": leg, "matched": True,
                                 "nt_entry": r["entry"].strftime("%Y-%m-%d %H:%M"),
                                 "nt_entry_px": r["entry_px"], "nt_pnl_usd": r["pnl"],
                                 "drift_min": int(bestd // 60)}
                matched += 1
        nt_only = len(nt) - len(used)
        summary.append((leg, matched, missed, nt_only, os.path.basename(path),
                        lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))

    print("%-16s %7s %7s %8s  %-24s %s" %
          ("LEG", "MATCH", "ENG-ONLY", "NT-ONLY", "DUMP", "WINDOW"))
    for leg, m, miss, nto, f, lo, hi in summary:
        print("%-16s %7d %7d %8d  %-24s %s..%s" % (leg, m, miss, nto, f[:24], lo, hi))

    if a.dry_run:
        print("\n--dry-run: publishing nothing (%d rows would be written)" % len(out))
        return 0

    doc = {"rows": out,
           "built_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
           "legs": {s[0]: {"matched": s[1], "engine_only": s[2], "nt_only": s[3],
                           "dump": s[4], "from": s[5], "to": s[6]} for s in summary}}
    (db.collection("users").document(a.uid).collection("meta")
       .document("nt_backtest_match").set(doc))
    print("\npublished meta/nt_backtest_match - %d trade rows" % len(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
