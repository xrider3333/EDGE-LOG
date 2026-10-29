"""tools/reconcile_core.py -- DAILY FILL RECONCILE, broker-agnostic core (B1-A, owner GO 2026-10-28).

Pure functions, no I/O, stdlib only. A broker READER (tools/webull_freshness.py's
webull_fill_inputs today; a PAPER-NT8 reader later) turns its own files into the two normalised
lists below, then calls reconcile(). Nothing here knows which broker it is.

INPUTS (one call = one session day `day`, a datetime.date; times are naive New York local
datetimes, both lists in the same clock):
  trades   the BOOK's closed round trips, every one the reader has (it may pass more than the
           day; reconcile() keeps those whose exit is on `day`):
             {"leg": str, "side": "long"|"short", "shares": float, "entry_ts": datetime,
              "exit_ts": datetime, "entry_px": float|None, "exit_px": float|None,
              "pnl": float|None (the book's own $, at the book's prices)}
           A partial close is several trades sharing one leg + entry_ts; they share ONE open order.
  orders   the BROKER's order rows, already stripped of rows the reader does not trust (a
           duplicate, a non-trading mode):
             {"ts": datetime, "leg": str, "intent": "OPEN"|"CLOSE", "side": str (BUY / SELL /
              SHORT, or long/short), "shares": float, "ok": bool, "fill_px": float|None}
           A FILL is a row with ok True and a fill_px. A row with ok False, or ok True and no
           fill_px, is a BAD ORDER (sent but refused / never filled).
  open_lots   the book's positions still open after the day ({"leg", "side", "shares",
           "entry_ts"}): an OPEN fill on `day` that belongs to one is not an orphan (a DIP lot
           held overnight).
  log_start   the oldest order row the broker log still holds (None = the log is empty or the
           reader cannot say). When it is later than everything the day needs (the open
           of each trade that closes on the day, plus tol), the answer is "cant_check": the
           log was trimmed, so a "missing" would be false.
  tol_sec  how far apart a book stamp and its broker row may be (default 30 s; they are 1-5 s).

PAIRING. For each closed trade: its CLOSE needs broker CLOSE fills of the same leg and
direction adding up to its shares; its OPEN (shared by the trades of one leg + entry_ts + side)
needs broker OPEN fills adding up to their shares -- the open may be days before `day` (DIP).
Rows are looked for in three passes: (1) the trade's own signal id (optional "open_sid" /
"close_sid" on the trade, matched against an order's optional "signal_id", a reduce number
and a re-send suffix R<n> allowed) at any time; (2) within tol of the book stamp, nearest
first; (3) late rows after the stamp -- an OPEN up to open_late_sec (a re-send), a CLOSE up to
the leg's next book close or the end of the day (close retries, a resting stop booked later,
an after-hours sell). The shares counted are capped at the book's (several close rows for one
lot = a partial resting fill + the market row carrying the lot's shares); the price is
averaged over the shares counted. ONE row bigger than the book's order (or OPEN rows past the
group's shares) = the extra shares are a stray fill. Direction: BUY is "up"; SELL and SHORT
are "down"; OPEN long / CLOSE short go up, OPEN short / CLOSE long go down. A row is used once.
A FILL is a row with ok True and either a fill_px or sent True (the price is captured later
and may never arrive: the pair is matched, broker_pnl None, counted in "unpriced").
NOT SEEN: a partial fill the broker row records at the requested shares (the CSV has no
filled-quantity column); the executor pages that one itself.

OUTPUT (reconcile -> dict):
  status      "no_trades" (nothing to compare), "clean" (all matched, slippage only),
              "missing" (anything unpaired), "cant_check" (log trimmed)
  matched     [{leg, side, shares, entry_ts, exit_ts, book_pnl, broker_pnl, slippage}]
              broker_pnl = (close fill - open fill) x shares, sign by side; slippage =
              broker_pnl - book_pnl (negative = Webull did worse than the book)
  no_fill     [{leg, side, shares, which ("open"/"close"/"both"), ts, missing_shares, usd}]
              book trades the broker lacks; usd = missing shares x the book's price (the $
              size Webull is off by)
  orphan_fills  [{leg, intent, side, shares, ts, px, usd, extra?}] broker fills on `day` with
              no book trade or open lot, or the extra shares of an oversized fill (extra True);
              usd = shares x px (the $ size of the stray order)
  bad_orders  [{leg, intent, side, shares, ts}] rows on `day` sent but refused or unfilled
  book_usd / broker_usd / slippage_usd   sums over matched (broker / slippage over the priced)
  unpriced    matched pairs whose Webull price never reached the log
  missing_usd sum of no_fill + orphan_fills usd
  reason      plain text for cant_check / no_trades
"""
import datetime as _dt
import re

DEFAULT_TOL_SEC = 30.0
DEFAULT_OPEN_LATE_SEC = 900.0     # a blocked OPEN is re-sent for up to ~15 min
_UP = {"BUY", "COVER", "BUY_TO_COVER"}
_DOWN = {"SELL", "SHORT", "SELL_SHORT"}


def direction(intent, side):
    """'up' / 'down' / None. `side` may be a broker side (BUY/SELL/SHORT) or a book side
    (long/short, read with `intent`)."""
    s = str(side or "").strip().upper()
    if s in _UP:
        return "up"
    if s in _DOWN:
        return "down"
    if s == "LONG":
        return book_direction(intent, "long")
    return None


def book_direction(intent, book_side):
    long_ = str(book_side or "").strip().lower() == "long"
    if str(intent).upper() == "OPEN":
        return "up" if long_ else "down"
    return "down" if long_ else "up"


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


_RESEND = re.compile(r"R\d+$")


def sid_matches(row_sid, base):
    """True when a broker row's signal_id is `base` (the trade's OPEN/CLOSE id), optionally
    with a reduce number and/or a re-send suffix R<n> (api/qqq_exec._broker_signal_id)."""
    if not base or not row_sid:
        return False
    s = _RESEND.sub("", str(row_sid).strip())
    if not s.startswith(base):
        return False
    rest = s[len(base):]
    return rest == "" or rest.isdigit()


def _take(orders, used, leg, intent, dirn, ts, shares, tol, sid=None, late_sec=0.0):
    """Unused fills of leg/intent/dirn for one book order of `shares`, in three passes until
    the shares are covered: (1) rows whose signal_id is the trade's own (any time: a re-send,
    a close retry, an after-hours sell), (2) rows within tol of ts, nearest first, (3) rows
    AFTER ts within late_sec (a late re-send, a resting stop booked later), oldest first.
    The shares taken are CAPPED at `shares` (the executor's market close row carries the
    lot's full shares even after a partial resting fill), and the price is averaged over the
    shares actually counted.
    -> {"idx", "got", "px" (None when any counted share has no price), "excess" (shares on
       the counted rows beyond `shares`), "rows"}."""
    def ok_row(i, o):
        return (i not in used and is_fill(o) and o.get("leg") == leg
                and str(o.get("intent")).upper() == intent
                and direction(intent, o.get("side")) == dirn)
    pool = [(i, o) for i, o in enumerate(orders) if ok_row(i, o)]
    order_ = []
    if sid:
        order_ += sorted((o["ts"], i) for i, o in pool if sid_matches(o.get("signal_id"), sid))
    order_ += sorted((abs((o["ts"] - ts).total_seconds()), i) for i, o in pool
                     if abs((o["ts"] - ts).total_seconds()) <= tol)
    if late_sec:
        order_ += sorted(((o["ts"] - ts).total_seconds(), i) for i, o in pool
                         if tol < (o["ts"] - ts).total_seconds() <= late_sec)
    got, cost, idx, priced, excess = 0.0, 0.0, [], True, 0.0
    for _k, i in order_:
        if i in idx:
            continue
        if got >= shares - 1e-9:
            break
        sh = abs(_f(orders[i].get("shares")) or 0.0)
        take = min(sh, shares - got)
        excess += sh - take
        idx.append(i)
        got += take
        px = orders[i].get("fill_px")
        if px is None:
            priced = False
        else:
            cost += take * px
    return {"idx": idx, "got": got, "excess": excess, "rows": len(idx),
            "px": (cost / got if got > 0 and priced else None)}


def is_fill(o):
    """A row Webull took: ok, and either a fill price or sent (the price is captured later
    and may never arrive -- the shares still traded)."""
    return bool(o.get("ok")) and (_f(o.get("fill_px")) is not None or bool(o.get("sent")))


def _px_of(t):
    return _f(t.get("exit_px")) or _f(t.get("entry_px")) or 0.0


def reconcile(day, trades, orders, open_lots=(), log_start=None, tol_sec=DEFAULT_TOL_SEC,
              open_late_sec=DEFAULT_OPEN_LATE_SEC):
    todays = sorted((t for t in trades if t.get("exit_ts") and t["exit_ts"].date() == day),
                    key=lambda t: t["exit_ts"])
    orders = sorted((dict(o, fill_px=_f(o.get("fill_px"))) for o in orders if o.get("ts")),
                    key=lambda o: o["ts"])
    day_orders = [i for i, o in enumerate(orders) if o["ts"].date() == day]
    rep = {"day": day.isoformat(), "status": "clean", "matched": [], "no_fill": [],
           "orphan_fills": [], "bad_orders": [], "book_usd": 0.0, "broker_usd": 0.0,
           "slippage_usd": 0.0, "missing_usd": 0.0, "unpriced": 0, "reason": "",
           "trades": len(todays), "orders": len(day_orders)}
    if not todays and not day_orders:
        rep.update(status="no_trades", reason="no trades and no orders on the day")
        return rep
    # the oldest order the day needs: the open of a trade closing today (days back for DIP),
    # and every book stamp on the day (an open of a lot still held included)
    need = [t["entry_ts"] for t in todays if t.get("entry_ts")] + [t["exit_ts"] for t in todays]
    need += [l["entry_ts"] for l in open_lots or () if l.get("entry_ts")
             and l["entry_ts"].date() == day]
    need_from = min(need) if need else None
    if log_start is None and need:
        log_start = _dt.datetime.max          # an empty log cannot prove anything
    if (need_from is not None and log_start is not None
            and log_start > need_from + _dt.timedelta(seconds=tol_sec)):
        rep.update(status="cant_check", reason="order log trimmed")
        return rep
    day_end = _dt.datetime.combine(day, _dt.time(23, 59, 59))

    used = set()
    opens = {}                                # (leg, entry_ts, side) -> [px, got_left]
    groups = {}
    for t in todays:
        groups.setdefault((t["leg"], t["entry_ts"], t["side"]), []).append(t)
    for key, ts in groups.items():
        leg, ets, side = key
        need_sh = sum(abs(_f(t.get("shares")) or 0.0) for t in ts)
        r = _take(orders, used, leg, "OPEN", book_direction("OPEN", side), ets, need_sh,
                  tol_sec, sid=ts[0].get("open_sid"), late_sec=open_late_sec)
        used.update(r["idx"])
        opens[key] = [r["px"], r["got"]]
        if r["excess"] > 1e-9:
            # Webull bought / sold short MORE than the book holds
            o = orders[r["idx"][-1]]
            px = o.get("fill_px") or _px_of(ts[0])
            rep["orphan_fills"].append({"leg": leg, "intent": "OPEN",
                                        "side": str(o.get("side") or "").upper(),
                                        "shares": r["excess"], "ts": _iso(o["ts"]), "px": px,
                                        "usd": round(r["excess"] * px, 2), "extra": True})
    for t in todays:
        sh = abs(_f(t.get("shares")) or 0.0)
        nxt = [u["exit_ts"] for u in todays if u["leg"] == t["leg"] and u["exit_ts"] > t["exit_ts"]]
        until = (min(nxt) - _dt.timedelta(seconds=tol_sec)) if nxt else day_end
        late = max(0.0, (until - t["exit_ts"]).total_seconds())
        r = _take(orders, used, t["leg"], "CLOSE", book_direction("CLOSE", t["side"]),
                  t["exit_ts"], sh, tol_sec, sid=t.get("close_sid"), late_sec=late)
        used.update(r["idx"])
        if r["excess"] > 1e-9 and r["rows"] == 1:
            # one close row bigger than the lot (several rows = a partial resting fill plus
            # the market close row carrying the lot's shares: not extra)
            o = orders[r["idx"][0]]
            px = o.get("fill_px") or _px_of(t)
            rep["orphan_fills"].append({"leg": t["leg"], "intent": "CLOSE",
                                        "side": str(o.get("side") or "").upper(),
                                        "shares": r["excess"], "ts": _iso(o["ts"]), "px": px,
                                        "usd": round(r["excess"] * px, 2), "extra": True})
        cpx, got_c = r["px"], r["got"]
        key = (t["leg"], t["entry_ts"], t["side"])
        opx, got_o = opens[key]
        share_o = min(sh, got_o)               # the open's shares shared out over the group
        opens[key][1] = max(0.0, got_o - sh)
        book = _f(t.get("pnl"))
        sign = 1.0 if str(t["side"]).lower() == "long" else -1.0
        miss_o, miss_c = sh - share_o, max(0.0, sh - got_c)
        if miss_o <= 1e-9 and miss_c <= 1e-9:
            if cpx is None or opx is None:
                bp = None                      # Webull traded; its price never reached the log
                rep["unpriced"] += 1
            else:
                bp = round((cpx - opx) * sign * sh, 2)
            bk = round(book, 2) if book is not None else bp
            rep["matched"].append({"leg": t["leg"], "side": t["side"], "shares": sh,
                                   "entry_ts": _iso(t["entry_ts"]), "exit_ts": _iso(t["exit_ts"]),
                                   "book_pnl": bk, "broker_pnl": bp,
                                   "slippage": (round(bp - bk, 2)
                                                if bp is not None and bk is not None else None)})
            continue
        which = "both" if miss_o > 1e-9 and miss_c > 1e-9 else ("open" if miss_o > 1e-9 else "close")
        miss = max(miss_o, miss_c)
        # the $ size of the shares Webull is off by (same yardstick as a stray fill)
        usd = _px_of(t) * miss
        rep["no_fill"].append({"leg": t["leg"], "side": t["side"], "shares": sh,
                               "which": which,
                               "ts": _iso(t["entry_ts"] if which == "open" else t["exit_ts"]),
                               "missing_shares": miss, "usd": round(usd, 2)})

    # OPEN fills on the day that belong to a lot the book still holds, or to a lot it opened
    # today and closed on a LATER day (a DIP lot: the 10-23 buys sold 10-27/10-28 read as stray
    # fills on 10-23 before this)
    later = [t for t in trades if t.get("entry_ts") and t["entry_ts"].date() == day
             and t.get("exit_ts") and t["exit_ts"].date() > day]
    for lot in list(open_lots or ()) + later:
        ets = lot.get("entry_ts")
        if not ets or ets.date() != day:
            continue
        r = _take(orders, used, lot.get("leg"), "OPEN", book_direction("OPEN", lot.get("side")),
                  ets, abs(_f(lot.get("shares")) or 0.0), tol_sec, sid=lot.get("open_sid"),
                  late_sec=open_late_sec)
        used.update(r["idx"])

    for i in day_orders:
        o = orders[i]
        if i in used:
            continue
        sh = abs(_f(o.get("shares")) or 0.0)
        base = {"leg": o.get("leg"), "intent": str(o.get("intent")).upper(),
                "side": str(o.get("side") or "").upper(), "shares": sh, "ts": _iso(o["ts"])}
        if is_fill(o):
            px = o.get("fill_px")
            rep["orphan_fills"].append(dict(base, px=px,
                                            usd=round(sh * (px or 0.0), 2)))
        else:
            rep["bad_orders"].append(base)

    priced = [m for m in rep["matched"] if m["broker_pnl"] is not None]
    rep["book_usd"] = round(sum(m["book_pnl"] or 0.0 for m in rep["matched"]), 2)
    rep["broker_usd"] = round(sum(m["broker_pnl"] for m in priced), 2)
    rep["slippage_usd"] = round(sum(m["slippage"] for m in priced
                                    if m["slippage"] is not None), 2)
    rep["missing_usd"] = round(sum(x["usd"] for x in rep["no_fill"] + rep["orphan_fills"]), 2)
    if rep["no_fill"] or rep["orphan_fills"]:
        rep["status"] = "missing"
    return rep


def _iso(d):
    return d.strftime("%Y-%m-%d %H:%M:%S") if d else None
