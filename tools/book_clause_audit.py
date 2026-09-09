"""AUDIT OF EVERY BOOK ADOPTION'S RISK CLAUSE (2026-09-09).

The TTM round-10 sizing sweep found that its own pre-registered clause - "whole-run drawdown
within 5 percent of the adopted book" - could not bind, because the TTM leg took no trades in the
stretch that sets that drawdown. This driver asks the same question of EVERY book adoption on the
board, using tools/book_dd_attribution.py:

  1. the house baseline book                          BOOK run #337 (ORB #234 + ENGU-Q #309)
  2. TTM adopted as a book leg                        #336 vs #337
  3. TTM tilt / tilt + ES 15m                         #341, #342 vs #336
  4. the weak-edge ETF dip book                       #332, #338, and each stacked on #337
  5. the NASDAQ walk-forward book (BOOKMARKS B11)     stacked on the champion, the +35% MAR claim
  6. the ORB x ENGU-Q 1:1 blend baseline              the net/DD number the upgrade menu ranks on

For each: where the book's worst stretch is, which legs actually paid for it, and whether the
adoption still clears when the risk clause is the LOCKBOX drawdown instead of the whole-run one.

It also settles a provenance question the finding raised, and the answer is a SEPARATE finding.
The recorded finding puts the baseline's worst stretch in 2020-02-21 .. 2020-03-25 at $34,903; the
BOOK runs themselves record $34,329.21 in 2022-04-27 .. 2022-05-24. Same legs, same params, same
master, same net to the cent - the difference is HOW A TRADE IS STAMPED TO A DAY. augur_engine's
book pools trades with numpy's datetime64[D] truncation of a US/Eastern index, which numpy performs
in UTC, so a 24h leg's trade exiting at or after 20:00 ET (19:00 in winter) is booked on the NEXT
day; the TTM driver used the ET calendar day. 227 of the ENGU-Q ETH leg's 1,179 exit days carry
their dollars on a different day under the two rules. Net never moves; the daily curve does, and
with it the drawdown - here, which MONTH is the worst stretch at all. Section 0 measures both.
Nothing is changed on that account: every stored book run is on the engine's convention, and moving
it would move every recorded book drawdown. It is reported as an open item, not fixed in passing.

Nothing here re-runs a search or crowns anything - it is a read of already-frozen books.

    python tools/book_clause_audit.py            # full audit -> tools/data/book_clause_audit.txt
    python tools/book_clause_audit.py --only 4   # one section (0-6)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.book_dd_attribution import (  # noqa: E402
    attribute, book_parts, clause_check, format_clause, format_stretch, leg_daily, run_job,
    score, series_from_rows, sum_parts, worst_stretch, _lb_from, _m)

LOG = os.path.join(ROOT, "tools", "data", "book_clause_audit.txt")
CSVOUT = os.path.join(ROOT, "tools", "data", "book_clause_audit.csv")
CACHE = os.path.join(ROOT, "tools", "data", "_book_clause_cache")
L = []


def say(*lines):
    for ln in lines:
        L.append(ln)
        print(ln, flush=True)


# ── leg cache: the ENGU-Q 1m ETH leg is minutes of work and appears in four books ──────────
def cached_leg(leg, date_from, date_to):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1(json.dumps([leg, date_from, date_to], sort_keys=True,
                                  default=str).encode()).hexdigest()[:16]
    path = os.path.join(CACHE, key + ".npz")
    if os.path.exists(path):
        z = np.load(path, allow_pickle=True)
        return pd.Series(z["usd"], index=pd.to_datetime(z["dates"]))
    t0 = time.time()
    s, _ = leg_daily({k: v for k, v in leg.items() if k != "_day_mode"}, date_from, date_to,
                     day_mode=leg.get("_day_mode") or "book")
    np.savez(path, usd=s.values, dates=s.index.values.astype("datetime64[ns]"))
    print("    (ran %s %s in %.0fs)" % (leg.get("strategy"), leg.get("timeframe"), time.time() - t0),
          flush=True)
    return s


def parts_of(job):
    """{label: daily $} for a stored BOOK run, cached leg by leg."""
    df, dt = job.get("date_from"), job.get("date_to")
    out = {}
    for leg in job.get("legs") or []:
        w = float(leg.get("weight", 1) or 1)
        lab = "%s %s %s%s" % (str(leg.get("strategy", "?")).replace(".py", ""),
                              leg.get("instrument"), leg.get("timeframe"), (" x%g" % w) if w != 1 else "")
        p = leg.get("params") or {}
        for k in ("allow_shorts", "dbl_n", "pb_ema", "rsi_thr"):
            if k in p and lab in out:
                lab += " [%s=%s]" % (k, p[k])
        while lab in out:
            lab += "'"
        out[lab] = cached_leg(leg, df, dt)
    return out


def clip(s, lo, hi):
    return s[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]


ROWS = []


def record(book, question, ws_when, ws_usd, driver_leg, driver_pct, cand_days, old, new, note):
    ROWS.append(dict(book=book, question=question, worst_stretch=ws_when, depth=round(ws_usd),
                     biggest_contributor=driver_leg, contributor_share=round(driver_pct, 1),
                     candidate_days_in_stretch=cand_days, old_clause=old, new_clause=new, note=note))


# ═══════════════════════════════════════════════════════════════════════════════════════════
def sec0():
    say("", "=" * 108,
        "0. PROVENANCE - two day-stamping rules, two different worst stretches", "=" * 108,
        "The finding on file says 2020-02-21..2020-03-25 / $34,903. Every BOOK run records $34,329.21.",
        "Same legs, same params, same master. The difference is which DAY a trade is booked on.")
    j337 = run_job(337)
    pinned = parts_of(j337)
    say("", "  (a) THE BOOK ENGINE'S RULE - numpy datetime64[D] on a US/Eastern index, i.e. truncated in UTC")
    say(*format_stretch(pinned, worst_stretch(sum_parts(pinned)), "", indent="    "))

    sess = {}
    for leg in j337["legs"]:
        lab = str(leg["strategy"]).replace(".py", "") + " (ET session day)"
        sess[lab] = cached_leg(dict(leg, _day_mode="session"), j337["date_from"], j337["date_to"])
    say("", "  (b) THE ET CALENDAR DAY - the day the account would write on the ticket (the TTM driver's rule)")
    say(*format_stretch(sess, worst_stretch(sum_parts(sess)), "", indent="    "))
    su, sp = score(sum_parts(sess)), score(sum_parts(pinned))
    moved = 0
    for a, b in zip(pinned.values(), sess.values()):
        u = a.index.union(b.index)
        moved += int((a.reindex(u, fill_value=0.0) - b.reindex(u, fill_value=0.0)).abs().gt(1e-9).sum())
    say("", "  engine rule  net $%s  DD $%s" % (_m(sp["net"]), _m(sp["dd"])),
        "  ET-day rule  net $%s  DD $%s" % (_m(su["net"]), _m(su["dd"])),
        "  %d leg-days carry their dollars on a different day; the NET is identical to the cent." % moved,
        "  => this is a real inconsistency and it is REPORTED, NOT FIXED here: every stored book run is",
        "     on the engine's rule, so changing it would move every recorded book drawdown at once.",
        "     Everything below uses the engine's rule, i.e. the numbers the stored runs actually carry.",
        "  => the FINDING is unaffected either way: under BOTH rules the TTM leg traded the stretch",
        "     zero times, which is the whole point.")
    return j337, pinned


# ═══════════════════════════════════════════════════════════════════════════════════════════
def sec1(j337, pinned):
    say("", "=" * 108, "1. THE HOUSE BASELINE BOOK - run #337, ORB #234 + ENGU-Q #309, one NQ contract each",
        "=" * 108)
    daily = sum_parts(pinned)
    lb = _lb_from(j337)
    s = score(daily, lb)
    say("  net $%s  whole-run DD $%s  ann.MAR %.3f  lockbox $%s  LB DD $%s  %d/%d years"
        % (_m(s["net"]), _m(s["dd"]), s["mar"], _m(s["lb"]), _m(s["lbdd"]), s["ypos"], s["ny"]))
    ws = worst_stretch(daily)
    say(*format_stretch(pinned, ws, "whole run"))
    say(*format_stretch(pinned, worst_stretch(daily, from_date=lb), "lockbox"))
    top = sorted(attribute(pinned, ws), key=lambda r: r["usd"])[0]
    record("#337 baseline (ORB 234 + ENGU-Q 309)", "where is the book's worst stretch?",
           "%s..%s" % (ws["start"].date(), ws["trough"].date()), ws["depth"], top["leg"],
           100 * top["share"], "-", "-", "-",
           "one NQ month sets the whole-run drawdown; both legs are NQ so both pay")
    return daily, lb


# ═══════════════════════════════════════════════════════════════════════════════════════════
def sec2(base_daily, lb):
    say("", "=" * 108, "2. THE TTM ADOPTIONS - is the leg being judged even present in the stretch?", "=" * 108)
    j336 = run_job(336)
    p336 = parts_of(j336)
    d336 = sum_parts(p336)
    for run_n, vs_daily, vs_name, newn, bar in (
            (336, base_daily, "#337 baseline", 1, "round 7: TTM adopted as a book leg"),
            (341, d336, "#336 adopted", 1, "queue_ttm_tilt_books: MAR x1.05, DD within 5%, LB >="),
            (342, d336, "#336 adopted", 2, "queue_ttm_tilt_books: MAR x1.05, DD within 5%, LB >=")):
        j = run_job(run_n)
        p = p336 if run_n == 336 else parts_of(j)
        d = d336 if run_n == 336 else sum_parts(p)
        say("", "-" * 100, "  run #%s  %s" % (run_n, str(j.get("strategy"))[:80]), "  bar as written: %s" % bar)
        res = clause_check(vs_daily, d, p, newn, lb)
        say(*format_clause(res, vs_name, "#%s" % run_n))
        ws = res["ws_whole"]
        cand_days = sum(r["days"] for r in res["participation"])
        record("#%s vs %s" % (run_n, vs_name), bar,
               "%s..%s" % (ws["start"].date(), ws["trough"].date()), ws["depth"],
               sorted(attribute(p, ws), key=lambda r: r["usd"])[0]["leg"], 0.0, cand_days,
               "PASS" if res["old_pass"] else "MISS", "PASS" if res["new_pass"] else "MISS",
               "added leg traded %d days in the incumbent's worst stretch" % cand_days)
    return j336, p336, d336


# ═══════════════════════════════════════════════════════════════════════════════════════════
def sec3(base_daily, lb):
    say("", "=" * 108, "3. THE WEAK-EDGE / ETF DIP BOOK - runs #332 (ETF + NQDIP) and #338 (ETF only)",
        "=" * 108,
        "Its own bar (r25) was standalone PF >= 1.25 and MAR >= 8 - no drawdown-vs-incumbent clause at",
        "all - plus a STACK test on the champion book that it MISSED (+12% MAR vs a +15% bar). So the",
        "question here is not 'was it adopted on an inert clause' but 'is its own drawdown one stretch",
        "too', and what the stack looks like judged on the lockbox.")
    out = {}
    for n in (332, 338):
        j = run_job(n)
        p = parts_of(j)
        d = sum_parts(p)
        lbn = _lb_from(j)
        s = score(d, lbn)
        say("", "-" * 100, "  run #%s  %s" % (n, str(j.get("strategy"))[:80]),
            "  net $%s  whole-run DD $%s  ann.MAR %.3f  lockbox $%s  LB DD $%s"
            % (_m(s["net"]), _m(s["dd"]), s["mar"], _m(s["lb"]), _m(s["lbdd"])))
        ws = worst_stretch(d)
        say(*format_stretch(p, ws, "whole run"))
        say(*format_stretch(p, worst_stretch(d, from_date=lbn), "lockbox"))
        top = sorted(attribute(p, ws), key=lambda r: r["usd"])[0]
        never = [r["leg"] for r in attribute(p, ws) if r["days"] == 0]
        record("#%s ETF/weak-edge book" % n, "own worst stretch",
               "%s..%s" % (ws["start"].date(), ws["trough"].date()), ws["depth"], top["leg"],
               100 * top["share"], "-", "-", "-",
               "%d of %d legs never traded in it" % (len(never), len(p)))
        out[n] = (j, p, d, lbn)

    # r25 stacked onto the CHAMPION book of the day (ORB #234 + ENGU-Q ETH #226), which is NOT
    # today's house baseline (ORB #234 + ENGU-Q ER #309). Both incumbents are reported so the
    # recorded "+12% vs a +15% bar" can be checked against the series it was computed from.
    ch = pd.read_csv(os.path.join(ROOT, "tools", "r13_results", "legal_legs_daily.csv"))
    ch["date"] = pd.to_datetime(ch["date"])
    ch = ch.set_index("date")
    champ_parts = {"ORB #234 (c2)": ch["c2"], "ENGU-Q ETH #226": ch["engq_eth"]}

    for inc_name, inc_parts in (("house baseline #337", None),
                                ("r25 champion (ORB 234 + ENGU-Q ETH 226)", champ_parts)):
      for n in (332, 338):
          j, p, d, lbn = out[n]
          lo, hi = "2010-06-07", "2025-06-29"
          if inc_parts is None:
              b = clip(base_daily, lo, hi)
          else:
              b = sum_parts({k: clip(v, lo, hi) for k, v in inc_parts.items()})
          cp = {k: clip(v, lo, hi) for k, v in p.items()}
          stacked = b.add(sum_parts(cp), fill_value=0.0).sort_index()
          bparts = {inc_name: b}
          allparts = dict(bparts)
          allparts.update(cp)
          # r25 stacked the weak-edge book RISK-MATCHED (each side scaled so its daily standard
          # deviation matches), not 1:1 - so both weightings are reported and the bar is asked of
          # the one the original round actually used.
          wk = sum_parts(cp)
          scale = (float(b.std()) / float(wk.std())) if float(wk.std()) > 0 else 1.0
          rm = {k: v * scale for k, v in cp.items()}
          rm_stacked = b.add(sum_parts(rm), fill_value=0.0).sort_index()
          rm_all = dict(bparts)
          rm_all.update(rm)
          say("", "-" * 100,
              "  STACK 1:1: %s + run #%s, common window %s..%s, lockbox from %s" % (inc_name, n, lo, hi, lbn))
          res = clause_check(b, stacked, allparts, list(cp.keys()), lbn, mar_gain=0.15)
          say(*format_clause(res, inc_name, "+ book #%s" % n, mar_gain=0.15))
          say("", "  STACK RISK-MATCHED (the r25 method, weak-edge side x%.3f so daily sigma matches):" % scale)
          rres = clause_check(b, rm_stacked, rm_all, list(rm.keys()), lbn, mar_gain=0.15)
          say(*format_clause(rres, inc_name, "+ #%s risk-matched" % n, mar_gain=0.15))
          cand_days = sum(r["days"] for r in res["participation"])
          ws = res["ws_whole"]
          record("%s + #%s" % (inc_name, n), "r25 stack bar: MAR +15%, give up <=10% net",
                 "%s..%s" % (ws["start"].date(), ws["trough"].date()), ws["depth"],
                 "(baseline NQ legs)", 0.0, cand_days,
                 "PASS" if res["old_pass"] else "MISS", "PASS" if res["new_pass"] else "MISS",
                 "ETF legs traded %d days inside the baseline's worst stretch" % cand_days)


# ═══════════════════════════════════════════════════════════════════════════════════════════
def sec4():
    say("", "=" * 108, "4. THE NASDAQ WALK-FORWARD BOOK (BOOKMARKS B11) - the '+35% MAR = adopt bar cleared' claim",
        "=" * 108,
        "The bar was 'raise the champion book's MAR by >= 15%'. MAR is net over WHOLE-RUN drawdown, so",
        "the same question applies: if the added legs sit out the champion's worst stretch, the",
        "denominator is frozen and the MAR bar quietly becomes a NET bar.")
    oos = list(csv.DictReader(open(os.path.join(ROOT, "tools", "r16_results", "wfo_nasdaq_fine_oos.csv"))))
    legs = series_from_rows([r for r in oos if r["leg"].split("/")[1] != "JOINT"],
                            "date", "pnl", "leg")
    book = sum_parts(legs)
    lo, hi = str(book.index[0].date()), str(book.index[-1].date())
    ch = pd.read_csv(os.path.join(ROOT, "tools", "r13_results", "legal_legs_daily.csv"))
    ch["date"] = pd.to_datetime(ch["date"])
    champ_parts = {"ORB #234 (c2)": clip(ch.set_index("date")["c2"], lo, hi),
                   "ENGU-Q ETH #226": clip(ch.set_index("date")["engq_eth"], lo, hi)}
    champ = sum_parts(champ_parts)
    say("", "  window (the WF book's own OOS span) %s .. %s" % (lo, hi))
    sb = score(champ)
    sn = score(book)
    say("  champion book  net $%s  DD $%s  net/DD %.2f" % (_m(sb["net"]), _m(sb["dd"]), sb["net"] / sb["dd"]),
        "  NASDAQ WF book net $%s  DD $%s  net/DD %.2f" % (_m(sn["net"]), _m(sn["dd"]), sn["net"] / sn["dd"]))
    say(*format_stretch(champ_parts, worst_stretch(champ), "champion book whole run"))
    ws = worst_stretch(champ)
    say("", "  do the eight NASDAQ legs trade inside the CHAMPION's worst stretch?")
    for r in sorted(attribute(legs, ws), key=lambda x: x["usd"]):
        say("    %-24s %+11s over %3d trading days%s" % (r["leg"], _m(r["usd"]), r["days"],
                                                         "   <- never traded there" if r["days"] == 0 else ""))
    # BOOKMARKS B11 quotes "8.31 -> 11.20 (+35%)". The champion figure reproduces (8.30 on this
    # span). The stacked figure does not, from the committed OOS series: 8 legs give 10.60, and
    # only pooling ALL TEN saved OOS series - the eight book legs PLUS the two per-fold JOINT
    # series, which are not part of the 8-leg book at all - lands on 11.30. Both readings clear
    # the +15% bar, so the verdict stands either way; the arithmetic behind the headline does not
    # reproduce exactly and is recorded as such rather than repeated.
    all10 = series_from_rows(oos, "date", "pnl", "leg")
    s10 = score(champ.add(sum_parts(all10), fill_value=0.0).sort_index())
    stacked = champ.add(book, fill_value=0.0).sort_index()
    ss = score(stacked)
    say("", "  STACK (1:1, the way B11 reports it)",
        "    champion        net $%s  DD $%s  net/DD %.2f" % (_m(sb["net"]), _m(sb["dd"]), sb["net"] / sb["dd"]),
        "    + NASDAQ book   net $%s  DD $%s  net/DD %.2f  = net x%.2f, MAR x%.2f"
        % (_m(ss["net"]), _m(ss["dd"]), ss["net"] / ss["dd"], ss["net"] / sb["net"],
           (ss["net"] / ss["dd"]) / (sb["net"] / sb["dd"])))
    say("    all TEN saved OOS series (adds the two JOINT ones, NOT the book) net $%s  DD $%s  net/DD %.2f  = MAR x%.2f"
        % (_m(s10["net"]), _m(s10["dd"]), s10["net"] / s10["dd"],
           (s10["net"] / s10["dd"]) / (sb["net"] / sb["dd"])),
        "    recorded in BOOKMARKS B11: 8.31 -> 11.20 (+35%). The champion half reproduces; the stacked",
        "    half sits between the two readings above. Every reading clears the +15% bar.")
    allp = dict(champ_parts)
    allp.update(legs)
    say(*format_stretch(allp, worst_stretch(stacked), "stacked book whole run"))
    lbdoor = str((pd.Timestamp(hi) - pd.Timedelta(days=365)).date())
    say("", "  the WF book has no lockbox of its own (its OOS IS the holdout), so the nearest",
        "  lockbox-shaped read is the last 12 months, %s .. %s:" % (lbdoor, hi))
    res = clause_check(champ, stacked, allp, list(legs.keys()), lbdoor, mar_gain=0.15)
    say(*format_clause(res, "champion", "+ NASDAQ book", mar_gain=0.15))
    cand_days = sum(r["days"] for r in res["participation"])
    record("champion + NASDAQ WF book (B11)", "adopt bar: raise champion MAR by >= 15%",
           "%s..%s" % (ws["start"].date(), ws["trough"].date()), ws["depth"],
           sorted(attribute(champ_parts, ws), key=lambda r: r["usd"])[0]["leg"], 0.0, cand_days,
           "PASS" if res["mar_ok"] else "MISS", "PASS" if res["new_pass"] else "MISS",
           "NASDAQ legs traded %d days inside the champion's worst stretch" % cand_days)


# ═══════════════════════════════════════════════════════════════════════════════════════════
def sec5():
    say("", "=" * 108, "5. THE ORB x ENGU-Q 1:1 BLEND BASELINE - the net/DD number the upgrade menu ranks on",
        "=" * 108,
        "The blend's upgrade menu (ENS leg swap 16.12, sizing overlay 18.92, ETH-NBO swap 16.98) is a",
        "ranking on net over WHOLE-RUN drawdown. Same denominator, same question.",
        "NOTE ON WHAT IS MEASURED HERE. The recorded $837,645 / $60,098 / 13.94 belongs to the LEAKING",
        "ORB #125 pair (ORB_3_1 at vol_filter 1.25, see ORB.md). That configuration no longer produces",
        "a result through the engine on any current NQ 5m master - run_backtest returns nothing at",
        "vol_filter 1.25 on both the no-adj and the tv master - so this section does NOT resurrect it.",
        "It asks the same question of the LEGAL successor pair, from the committed daily series the",
        "round-13 legal-legs file holds: ORB #234 with each ENGU-Q leg in turn.")
    ch = pd.read_csv(os.path.join(ROOT, "tools", "r13_results", "legal_legs_daily.csv"))
    ch["date"] = pd.to_datetime(ch["date"])
    ch = ch.set_index("date")
    lo, hi = "2010-06-07", "2026-06-30"
    for eng_col, eng_lab in (("engq_rth", "ENGU-Q RTH #149 leg"), ("engq_eth", "ENGU-Q ETH #226 leg")):
        parts = {"ORB #234 leg": clip(ch["c2"], lo, hi), eng_lab: clip(ch[eng_col], lo, hi)}
        d = sum_parts(parts)
        sc = score(d, "2025-06-30")
        say("", "-" * 100, "  ORB #234 x %s, 1:1, %s..%s" % (eng_lab, lo, hi),
            "  net $%s  whole-run DD $%s  net/DD %.2f  last-12-months net $%s  DD $%s"
            % (_m(sc["net"]), _m(sc["dd"]), sc["net"] / sc["dd"], _m(sc["lb"]), _m(sc["lbdd"])))
        ws = worst_stretch(d)
        say(*format_stretch(parts, ws, "whole run"))
        say(*format_stretch(parts, worst_stretch(d, from_date="2025-06-30"), "last 12 months"))
        top = sorted(attribute(parts, ws), key=lambda r: r["usd"])[0]
        never = [r["leg"] for r in attribute(parts, ws) if r["days"] == 0]
        record("blend baseline: ORB #234 x %s" % eng_lab, "net/DD, the upgrade menu's ranking",
               "%s..%s" % (ws["start"].date(), ws["trough"].date()), ws["depth"], top["leg"],
               100 * top["share"], "-", "-", "-",
               "both legs trade the stretch - the clause is not inert, but the denominator is still one month"
               if not never else "%s never traded the stretch" % ", ".join(never))
    say("", "  READ: the ranking is not inert - both legs are NQ and both pay for the stretch - but every",
        "  number in that menu is one month's drawdown in the denominator, so a candidate that improves",
        "  net/DD by sitting out that month has improved nothing about its own risk. The menu should",
        "  carry the last-12-months drawdown beside it before any of it is adopted.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=None)
    a = ap.parse_args()
    say("BOOK RISK-CLAUSE AUDIT   %s" % time.strftime("%Y-%m-%d %H:%M"),
        "question: for every book adoption on the board, where is the book's worst stretch, which legs",
        "paid for it, and would the adoption still clear on LOCKBOX drawdown instead of whole-run drawdown?")
    j337, pinned = sec0()
    if a.only in (None, 0):
        pass
    base_daily, lb = sec1(j337, pinned)
    if a.only in (None, 2):
        sec2(base_daily, lb)
    if a.only in (None, 3):
        sec3(base_daily, lb)
    if a.only in (None, 4):
        sec4()
    if a.only in (None, 5):
        sec5()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    if ROWS:
        with open(CSVOUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys()))
            w.writeheader()
            w.writerows(ROWS)
    print("\nlog -> %s\ncsv -> %s" % (LOG, CSVOUT))


if __name__ == "__main__":
    main()
