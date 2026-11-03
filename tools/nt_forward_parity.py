"""tools/nt_forward_parity.py -- E6/E10 NT side: forward paper (NinjaTrader DEMO fills) vs the book, per leg.

Read-only. Reuses tools/nt_fill_reconcile.py day by day (book = Firestore paper_trades shadow round trips,
broker = C:\\EdgeLog\\fills.csv DEMO7240108 rows) and rolls the days up per family (NOISE, ENGUQ):
  book_n / nt_n        round trips the book took / that NinjaTrader filled and matched
  fill_rate            nt_n / book_n (missed trades are a parity failure, not slippage)
  hit_book / hit_nt    win rate over the MATCHED trades, book pnl vs NT fill pnl
  avg_book / avg_nt    $ per matched trade at the contracts NinjaTrader sends
  slip_usd_per_trade   mean (NT - book) $ per matched trade; strays = NT fills with no book trade
  clock                forward clock: matched trades n/300 and days d/183 since the first matched day;
                       DUE when either is reached (then a written verdict)
avg R is not reported: the book's trade docs carry no stop (row 64), so R has no denominator yet.

  python tools/nt_forward_parity.py --since 2026-10-01            print + write C:\\EdgeLog\\parity\\nt_forward_parity.json
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nt_fill_reconcile as nfr                              # noqa: E402

OUT = r"C:\EdgeLog\parity\nt_forward_parity.json"
CLOCK_TRADES, CLOCK_DAYS = 300, 183


def rollup(reports):
    legs = {}
    for rep in reports:
        for key, rows in (("matched", rep.get("matched") or []), ("no_fill", rep.get("no_fill") or []),
                          ("orphan_fills", rep.get("orphan_fills") or [])):
            for x in rows:
                fam = nfr._family(x.get("leg"))
                L = legs.setdefault(fam, {"matched": [], "no_fill": 0, "strays": 0, "days": set()})
                if key == "matched":
                    L["matched"].append(x)
                    L["days"].add(rep["day"])
                elif key == "no_fill":
                    L["no_fill"] += 1
                else:
                    L["strays"] += 1
    out = {}
    for fam, L in sorted(legs.items()):
        m = L["matched"]
        priced = [x for x in m if x.get("broker_pnl") is not None and x.get("book_pnl") is not None]
        n, book_n = len(priced), len(m) + L["no_fill"]
        days = sorted(L["days"])
        span = (dt.date.today() - dt.date.fromisoformat(days[0])).days if days else 0
        mean = lambda v: round(sum(v) / len(v), 2) if v else None          # noqa: E731
        out[fam] = {
            "book_n": book_n, "nt_n": len(m), "priced_n": n, "missed": L["no_fill"], "strays": L["strays"],
            "fill_rate": round(len(m) / book_n, 3) if book_n else None,
            "hit_book": mean([1.0 if x["book_pnl"] > 0 else 0.0 for x in priced]),
            "hit_nt": mean([1.0 if x["broker_pnl"] > 0 else 0.0 for x in priced]),
            "avg_book": mean([x["book_pnl"] for x in priced]),
            "avg_nt": mean([x["broker_pnl"] for x in priced]),
            "slip_usd_per_trade": mean([x["broker_pnl"] - x["book_pnl"] for x in priced]),
            "first_day": days[0] if days else None,
            "clock": {"trades": f"{len(m)}/{CLOCK_TRADES}", "days": f"{span}/{CLOCK_DAYS}",
                      "due": len(m) >= CLOCK_TRADES or span >= CLOCK_DAYS},
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="2026-10-01")
    ap.add_argument("--until", help="default today")
    a = ap.parse_args(argv)
    d, end = dt.date.fromisoformat(a.since), dt.date.fromisoformat(a.until) if a.until else dt.date.today()
    reports = []
    while d <= end:
        if d.weekday() < 5:
            try:
                reports.append(nfr.run(d, nfr.read_book(d)))
            except Exception as e:                                       # one bad day never hides the rest
                print(f"{d}: skipped ({type(e).__name__}: {e})")
        d += dt.timedelta(days=1)
    res = {"built": dt.datetime.now().isoformat(timespec="seconds"), "since": a.since, "until": end.isoformat(),
           "source": "fills.csv DEMO7240108 vs Firestore paper_trades", "legs": rollup(reports)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    for fam, r in res["legs"].items():
        print(f"{fam}: book {r['book_n']}, NT matched {r['nt_n']} (missed {r['missed']}, strays {r['strays']}); "
              f"hit book {r['hit_book']} vs NT {r['hit_nt']}; $/trade book {r['avg_book']} vs NT {r['avg_nt']}; "
              f"slip {r['slip_usd_per_trade']}/trade; clock {r['clock']['trades']} trades, {r['clock']['days']} days")
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
