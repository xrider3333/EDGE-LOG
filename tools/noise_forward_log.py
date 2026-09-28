"""tools/noise_forward_log.py -- READ-ONLY joiner for the NOISE FORWARD LOG (Custom ML's
pre-registered forward test, docs/PREREG_noise_shadow_forward_2026-09-28.md).

The signal engine writes one DECISION-TIME row per NOISE signal (api/noise_forward.py) into
<home>/cloud_signal/shadow/noise_forward_log.csv: signal id, decision time, side, the signal
bar, the flags every sizing arm reads, every arm's uncapped multiplier and share count, and
both KEEL states. This tool adds the FILL half from the order adapter's ledgers, by trade id,
and writes the per-signal table Custom ML scores:

  <home>/qqq_exec/trades.csv         the primary's closed book trade (shares, wanted, exit reason)
  <home>/qqq_exec/broker_orders.csv  the Webull order per side: outcome, reason, fill price
  <home>/qqq_exec/orders.csv         a REFUSED entry (breaker / feed / kill blocked)
  <home>/qqq_exec/state.json         an open lot, skipped signals (leg busy, other session),
                                     and partial-fill events
  <home>/cloud_signal/signals.csv    the primary's EXIT signal (time, price)
  <home>/cloud_signal/shadow/signals.csv  the #422 legs' EXIT signals (exit divergence)

PRIMARY STATUS -- did the primary's order really fill? The book (api/qqq_exec.py) opens its
lot and writes its trades.csv row whatever the broker side did, so a trades.csv row alone
says nothing about Webull. The status comes from broker_orders.csv's `outcome` per side:
  filled             both sides have a Webull fill price
  open               the entry filled at Webull; the lot is still open
  fill_pending       the entry was sent and accepted (OK) but no fill price was captured yet
  broker_blocked     the entry was never sent: a rail (halt / reconcile halt / kill file,
                     daily loss limit, per-leg or total-position cap, one open position per
                     leg, session window) or the cross-host lease gate -- mode BLOCKED
  broker_refused     sent and refused (a Webull 4xx), or the adapter call itself failed
  broker_unknown     an ambiguous send (timeout / 5xx / dropped connection): outcome unknown
  filled_book_only   the order adapter is OFF: a would-be order, nothing sent
  no_broker_order    the book traded it but broker_orders.csv has no row for its entry
  exit_<one of the above>  the entry filled at Webull, the exit did not (e.g. a CLOSE that
                     never filled: exit_fill_pending)
  refused / skipped / no_order_found   the book itself never opened a lot (orders.csv
                     REFUSED, a state.json skip event, or nothing found)
  n/a                a shadow-only signal: the primary never traded it
primary_status_detail names the reason, e.g. "halt: halted: reconcile mismatch ..." /
"total_cap: ..." / "lease: ..." / "http_4xx: ...". Only "filled" rows carry Webull dollars.

TIMES AND QUANTITIES. entry/exit_order_ts_et and entry_shares/exit_shares are the BOOK's lot
(trades.csv: qqq_exec's clock when it opened/closed the lot, and its share count).
entry/exit_broker_sent_ts_et and entry/exit_broker_shares are the Webull order row's own
send time and size. The order adapter records no Webull fill TIME (fill capture writes only
the price), so the send time is the closest record of it. entry/exit_filled_shares = the
sent shares of every priced order, except where a state.json broker event reports a partial
("N of M share(s) filled"), which gives the filled count instead.

DOLLARS. pnl_per_share = (exit fill - entry fill) x side on WEBULL fills, only when
primary_status is "filled"; pnl_usd_<arm> = that x base shares x the arm's UNCAPPED
multiplier (the pre-registered score) and pnl_usd_<arm>_capped = that x the arm's capped
shares. Any other closed book trade gets the BOOK's prices in pnl_per_share_book and
pnl_usd_<arm>_book instead -- never mixed into the Webull columns (the pre-registration
scores trades the primary did not fill separately). An arm is scored only when its own
leg has a row for the signal (arm legs: noise_forward.ARM_LEG) and its EXIT agrees with the
primary's: exit_divergence names each #422 leg whose EXIT signal is at another bar, side or
price (> half a cent), or is missing while the primary exited (or the reverse), and
arms_not_scored lists every arm left blank and why.

other_open_shares = the shares other legs' book lots held at the entry (closed trades.csv
rows and open state.json lots); total_cap_refused_arms = arms whose shares plus those would
pass max_total_shares. That APPROXIMATES the order rail, which checks the adapter's own
believed per-leg positions (orders it passed or recorded OFF, not blocked ones) plus the
order's quantity.

--backfill also rebuilds decision rows for primary entries the forward log does not have (the
days before it went live) from the signal ledgers and the 5m bar cache, with the same code the
engine uses; their KEEL metadata is read now, not at the decision (row_source says which).
A forward-log row that failed to build ("row failed: ..." in mult_check) is rebuilt the same
way and replaces its stub.

Reads only; writes only --out (stdout when omitted). Never touches Webull or the box.

Usage:  python tools/noise_forward_log.py [--home DIR] [--out CSV] [--since YYYY-MM-DD]
            [--backfill] [--forward-log F] [--signals F] [--shadow-signals F] [--ohlc-dir D]
            [--keel-dir D] [--orders F] [--trades F] [--broker-orders F] [--exec-state F]
            [--qqq-exec-config F] [--orders-config F]
"""
import argparse
import csv
import datetime as _dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import noise_forward as nf      # noqa: E402
from api import trade_id as _trade_id    # noqa: E402

EXEC_LEG = "NOISE"
REFUSED_MATCH_MIN = 15      # a REFUSED entry order within this many minutes of the entry bar
SENT_MODES = ("PAPER", "LIVE")
EXIT_PRICE_TOL = 0.005      # an EXIT ref_price this close is the same price (cloud_signal_stream)

FILL_COLS = (["primary_status", "primary_status_detail",
              "entry_order_ts_et", "entry_shares", "entry_shares_wanted", "entry_capped",
              "entry_shadow_px", "entry_broker_sent_ts_et", "entry_broker_shares",
              "entry_filled_shares", "entry_fill_px", "entry_broker_outcome",
              "exit_signal_time", "exit_signal_price",
              "exit_order_ts_et", "exit_shares", "exit_shadow_px", "exit_broker_sent_ts_et",
              "exit_broker_shares", "exit_filled_shares", "exit_fill_px", "exit_broker_outcome",
              "exit_reason", "exit_divergence",
              "pnl_per_share", "pnl_per_share_book",
              "other_open_shares", "total_cap_refused_arms", "arms_not_scored"]
             + [f"pnl_usd_{a}" for a in nf.ARMS] + [f"pnl_usd_{a}_capped" for a in nf.ARMS]
             + [f"pnl_usd_{a}_book" for a in nf.ARMS])
JOIN_COLS = ["row_source"] + list(nf.COLS) + FILL_COLS
# broker verdict -> primary_status (the entry side; an exit side is prefixed "exit_")
_STATUS = {"filled": "filled", "fill_pending": "fill_pending", "blocked": "broker_blocked",
           "refused": "broker_refused", "unknown": "broker_unknown",
           "off": "filled_book_only", "none": "no_broker_order"}
# the rail / gate a BLOCKED or REFUSED order's reason names (first match wins)
_REASON_KINDS = (("halted:", "halt"), ("kill file", "halt"),
                 ("max_total_position_shares", "total_cap"), ("max_shares_per_leg", "per_leg_cap"),
                 ("daily loss limit", "daily_loss"), ("outside session window", "session_window"),
                 ("one_open_position_per_leg", "one_open_position"),
                 ("nothing to close", "nothing_to_close"), ("lease", "lease"),
                 ("client (", "no_client"))
_HTTP_RE = re.compile(r"HTTP(?: Status:)?\s*(\d{3})")      # = webull_orders._HTTP_STATUS_RE
_PARTIAL_RE = re.compile(r"Webull reports (\S+) for order (\S+) -- (\S+) of (\S+) share")


def _tz():
    from api import cloud_signal as cs
    return cs._zi(cs.TZ)


def _alnum(s):
    return re.sub(r"[^A-Za-z0-9]", "", str(s or ""))


def _naive_et(iso):
    """An ISO time -> naive ET 'YYYY-MM-DD HH:MM:SS' (the order ledgers' own format)."""
    try:
        t = _dt.datetime.fromisoformat(str(iso))
    except ValueError:
        return ""
    if t.tzinfo is not None:
        t = t.astimezone(_tz()).replace(tzinfo=None)
    return t.strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


# ── inputs ───────────────────────────────────────────────────────────────────────────────
def input_paths(home, **over):
    """Every file this tool reads, laid out like <home> (EDGELOG_HOME / a box_backup copy);
    any keyword overrides one path."""
    cs_dir = os.path.join(home, "cloud_signal")
    q = os.path.join(home, "qqq_exec")
    p = {"forward_log": os.path.join(cs_dir, "shadow", nf.FORWARD_LOG_FILENAME),
         "signals": os.path.join(cs_dir, "signals.csv"),
         "shadow_signals": os.path.join(cs_dir, "shadow", "signals.csv"),
         "ohlc_dir": os.path.join(home, "ohlc"),
         "keel_dir": os.path.join(cs_dir, "keel"),
         "orders": os.path.join(q, "orders.csv"),
         "trades": os.path.join(q, "trades.csv"),
         "broker_orders": os.path.join(q, "broker_orders.csv"),
         "exec_state": os.path.join(q, "state.json"),
         "qqq_exec_config": os.path.join(q, "config.json"),
         "orders_config": os.path.join(home, "webull_orders", "config.json")}
    p.update({k: v for k, v in over.items() if v})
    return p


def _keel_cfg(keel_dir, leg):
    return {"version": "v12", "state_path": os.path.join(keel_dir, f"{leg}_v12_state.joblib"),
            "summary_path": os.path.join(keel_dir, f"{leg}_v12_summary.json")}


def backfill_rows(paths, logged_ids, since=None, now=None):
    """Decision rows for the entries in the signal ledgers the forward log lacks, built by
    api/noise_forward.build_rows with no grace (force) from the 5m cache in paths["ohlc_dir"]
    and the SHIPPED leg cfgs (their KEEL summaries read from paths["keel_dir"])."""
    from api import cloud_signal as cs
    live_legs = {nf.PRIMARY_LEG: dict(cs.CROWN_LEGS[nf.PRIMARY_LEG],
                                      keel=_keel_cfg(paths["keel_dir"], nf.PRIMARY_LEG))}
    shadow_legs = {k: dict(v) for k, v in cs.SHADOW_LEGS.items()}
    shadow_legs[nf.KEEL_LEG]["keel"] = _keel_cfg(paths["keel_dir"], nf.KEEL_LEG)
    ctx = nf.context(live_legs, shadow_legs, nf.book_caps(paths["qqq_exec_config"],
                                                         paths["orders_config"]))
    ctx["note"] = "; ".join(n for n in (ctx.get("note"), "backfill: rebuilt from the signal "
                                        "ledgers, KEEL metadata read at backfill time") if n)
    cache = {}

    def bars():
        if "df" not in cache:
            cache["df"] = cs.historical_bars("5m", {"ohlc_dir": paths["ohlc_dir"]})
        return cache["df"]
    now = now or _dt.datetime.now(tz=_tz())
    rows, _pending = nf.build_rows(nf.read_csv_rows(paths["signals"]),
                                   nf.read_csv_rows(paths["shadow_signals"]), bars, now, ctx,
                                   set(logged_ids), since or "0000-00-00", force=True)
    return rows


def decision_rows(paths, since=None, backfill=False, now=None):
    """The forward log's rows (row_source "forward_log") plus, with `backfill`, rebuilt rows
    (row_source "backfill") for entries it lacks and for its "row failed" stubs (the rebuilt
    row replaces the stub), entry date >= `since`, in entry order."""
    logged = [dict(r, row_source="forward_log") for r in nf.read_csv_rows(paths["forward_log"])]
    out = list(logged)
    if backfill:
        failed = {r.get("signal_id") for r in logged
                  if str(r.get("mult_check") or "").startswith(nf.ROW_FAILED)}
        rebuilt = [dict(r, row_source="backfill")
                   for r in backfill_rows(paths, {r.get("signal_id") for r in logged} - failed,
                                          since, now)]
        ids = {r.get("signal_id") for r in rebuilt}
        out = [r for r in out if r.get("signal_id") not in ids] + rebuilt
    if since:
        out = [r for r in out if str(r.get("entry_bar_time") or "")[:10] >= since]
    out.sort(key=lambda r: (str(r.get("entry_bar_time") or ""), str(r.get("signal_id") or "")))
    return out


# ── the fill half ────────────────────────────────────────────────────────────────────────
def _broker_rows(broker, sid, intent_code):
    """broker_orders.csv rows for one side of trade `sid` (api/qqq_exec._broker_signal_id:
    "qx" + the id's letters/digits + O/C, plus an optional resend/reduce suffix)."""
    base = "qx" + _alnum(sid) + intent_code
    return [b for b in broker if str(b.get("signal_id") or "") == base
            or re.fullmatch(re.escape(base) + r"R?\d+", str(b.get("signal_id") or ""))]


def _truthy(v):
    return str(v).strip().lower() == "true"


def _row_outcome(b):
    """A broker_orders.csv row's OK / REFUSED / BLOCKED / UNKNOWN (its `outcome` column; a
    row written before that column existed is read from ok/mode)."""
    o = str(b.get("outcome") or "").strip().upper()
    if o:
        return o
    if _truthy(b.get("ok")):
        return "OK"
    return "BLOCKED" if str(b.get("mode") or "").strip().upper() == "BLOCKED" else "REFUSED"


def reason_kind(reason):
    """The rail / gate / broker answer a not-OK order's reason names: halt, total_cap,
    per_leg_cap, daily_loss, session_window, one_open_position, nothing_to_close, lease,
    no_client, http_4xx / http_<code> (Webull's status) -- else "other"."""
    text = str(reason or "")
    low = text.lower()
    # Webull's own HTTP answer first: its message text can contain any rail word (a 417 reads
    # "... Please ..."), and the broker's verdict is what refused the order.
    m = _HTTP_RE.search(text)
    if m:
        code = int(m.group(1))
        return "http_4xx" if 400 <= code < 500 else f"http_{code}"
    for needle, kind in _REASON_KINDS:
        if re.search(r"(?<![a-z])" + re.escape(needle.lower()), low):
            return kind
    return "other"


def _partial_filled(b, events):
    """The filled share count a state.json broker event reports for this order ("Webull
    reports <status> for order <id> -- N of M share(s) filled"): N, "" when it says None,
    None when no event names the order."""
    ids = {str(b.get(k) or "").strip() for k in ("signal_id", "client_order_id")} - {""}
    for e in reversed(list(events or ())):
        m = _PARTIAL_RE.search(str(e.get("text") or ""))
        if m and m.group(2) in ids:
            v = nf._f(m.group(3))
            return "" if v is None else int(v)
    return None


def broker_side(rows, events=()):
    """One side's Webull record: {verdict, fill_px, sent_ts, shares, filled, reason, text}.
    verdict: "filled" (a fill price was captured; with several priced orders -- a resent
    remainder -- the price is their share-weighted mean and the counts add up),
    "fill_pending" (sent and accepted, no price yet), "off" (adapter OFF: every row a
    would-be order), "blocked" / "refused" / "unknown" (the latest row's outcome), "none"."""
    out = {"verdict": "none", "fill_px": None, "sent_ts": "", "shares": "", "filled": "",
           "reason": "", "text": ""}
    if not rows:
        return out
    parts = []
    for b in rows:
        reason = str(b.get("reason") or "").strip()
        parts.append(f"{_row_outcome(b)}: {reason[:120]}" if reason else _row_outcome(b))
    out["text"] = "; ".join(parts)
    priced = [b for b in rows if nf._f(b.get("broker_fill_px")) is not None]
    sent_ok = [b for b in rows if _row_outcome(b) == "OK" and _truthy(b.get("sent"))
               and str(b.get("mode") or "").upper() in SENT_MODES]
    if priced:
        filled, weights, known = 0, [], True
        for b in priced:
            sent = int(nf._f(b.get("shares")) or 0)
            part = _partial_filled(b, events)
            if part == "":
                known = False
            n = sent if part is None or part == "" else part
            filled += n
            weights.append((n, nf._f(b.get("broker_fill_px"))))
        total = sum(n for n, _ in weights)
        px = (sum(n * p for n, p in weights) / total) if total else weights[-1][1]
        out.update(verdict="filled", fill_px=round(px, 4), sent_ts=priced[-1].get("ts_et", ""),
                   shares=sum(int(nf._f(b.get("shares")) or 0) for b in priced),
                   filled=filled if known else "")
        return out
    if sent_ok:
        b = sent_ok[-1]
        out.update(verdict="fill_pending", sent_ts=b.get("ts_et", ""), shares=b.get("shares", ""),
                   reason=str(b.get("reason") or ""))
        return out
    last = rows[-1]
    out.update(sent_ts=last.get("ts_et", "") if _truthy(last.get("sent")) else "",
               shares=last.get("shares", ""), reason=str(last.get("reason") or ""))
    if all(str(b.get("mode") or "").upper() == "OFF" and _row_outcome(b) == "OK" for b in rows):
        out["verdict"] = "off"
    else:
        out["verdict"] = {"BLOCKED": "blocked", "REFUSED": "refused",
                          "UNKNOWN": "unknown"}.get(_row_outcome(last), "refused")
    return out


def _side_detail(side, prefix=""):
    """primary_status_detail for a side that did not fill."""
    v = side["verdict"]
    if v in ("blocked", "refused", "unknown"):
        return f"{prefix}{reason_kind(side['reason'])}: {side['reason'][:200]}"
    if v == "fill_pending":
        return f"{prefix}sent and accepted, no Webull fill price captured yet"
    if v == "off":
        return f"{prefix}order adapter OFF: a would-be order, nothing sent"
    if v == "none":
        return f"{prefix}no broker_orders.csv row"
    return ""


def _other_open_shares(trades, lots, at_ts):
    """Shares every OTHER leg's book lot held at `at_ts` (naive ET): closed trades.csv rows
    open then, plus lots still open in state.json that were opened by then."""
    n = 0
    for t in trades:
        if t.get("leg") == EXEC_LEG:
            continue
        if str(t.get("entry_ts") or "") <= at_ts < str(t.get("exit_ts") or "9999"):
            try:
                n += int(float(t.get("shares") or 0))
            except ValueError:
                pass
    for leg, lot in (lots or {}).items():
        if leg == EXEC_LEG or not isinstance(lot, dict):
            continue
        if str(lot.get("entry_ts") or "9999") <= at_ts:
            try:
                n += int(float(lot.get("shares_total") or 0))
            except (TypeError, ValueError):
                pass
    return n


def exit_divergence(decision, primary_exit, shadow_exits):
    """{leg: reason} for every #422 leg of this signal whose EXIT signal differs from the
    primary's: another bar (ref_time), side, or price (more than EXIT_PRICE_TOL); an exit
    where the primary has none yet, or none where the primary exited."""
    out = {}
    for tid in [t for t in str(decision.get("shadow_trade_ids") or "").split(";") if t]:
        p = _trade_id.parse(tid)
        leg = p["leg"] if p else tid
        x = shadow_exits.get(tid)
        if primary_exit is None and x is None:
            continue
        if primary_exit is None:
            out[leg] = f"{leg} exited {x.get('ref_time', '')} while the primary is still open"
        elif x is None:
            out[leg] = f"{leg} has no exit (primary exited {primary_exit.get('ref_time', '')})"
        else:
            diffs = []
            if str(x.get("ref_time") or "") != str(primary_exit.get("ref_time") or ""):
                diffs.append(f"bar {x.get('ref_time', '')} vs {primary_exit.get('ref_time', '')}")
            if str(x.get("side") or "") != str(primary_exit.get("side") or ""):
                diffs.append(f"side {x.get('side', '')} vs {primary_exit.get('side', '')}")
            xp, pp = nf._f(x.get("ref_price")), nf._f(primary_exit.get("ref_price"))
            if xp is None or pp is None or abs(xp - pp) > EXIT_PRICE_TOL + 1e-9:
                diffs.append(f"price {x.get('ref_price', '')} vs {primary_exit.get('ref_price', '')}")
            if diffs:
                out[leg] = f"{leg} exit " + ", ".join(diffs)
    return out


def join_fills(rows, paths):
    """Each decision row plus FILL_COLS from the order adapter's ledgers (see the module
    docstring). Never modifies the input rows."""
    orders = nf.read_csv_rows(paths["orders"])
    trades = nf.read_csv_rows(paths["trades"])
    broker = nf.read_csv_rows(paths["broker_orders"])
    signals = nf.read_csv_rows(paths["signals"])
    shadow_signals = nf.read_csv_rows(paths["shadow_signals"])
    state = _load_json(paths["exec_state"])
    by_tid = {t["trade_id"]: t for t in trades if t.get("trade_id")}

    def _exits(ledger):
        return {s["trade_id"]: s for s in ledger
                if str(s.get("event") or "").upper() == "EXIT" and s.get("trade_id")}
    exits, shadow_exits = _exits(signals), _exits(shadow_signals)
    events = state.get("events") or []
    lots = state.get("legs") or {}
    lot = lots.get(EXEC_LEG) or {}
    out = []
    for r in rows:
        j = dict(r)
        for c in FILL_COLS:
            j.setdefault(c, "")
        sid = str(r.get("signal_id") or "")
        if r.get("row_type") != "primary":
            j["primary_status"] = "n/a"
            j["primary_status_detail"] = "shadow-only signal: the primary did not trade it"
            out.append(j)
            continue
        x = exits.get(sid)
        if x:
            j["exit_signal_time"], j["exit_signal_price"] = x.get("ref_time", ""), x.get("ref_price", "")
        t = by_tid.get(sid)
        ent = broker_side(_broker_rows(broker, sid, "O"), events)
        ext = broker_side(_broker_rows(broker, sid, "C"), events)
        for pre, b in (("entry", ent), ("exit", ext)):
            j.update({f"{pre}_broker_outcome": b["text"], f"{pre}_broker_sent_ts_et": b["sent_ts"],
                      f"{pre}_broker_shares": b["shares"], f"{pre}_filled_shares": b["filled"],
                      f"{pre}_fill_px": "" if b["fill_px"] is None else b["fill_px"]})
        is_open = not t and lot.get("trade_id") == sid
        entry_ts = ""
        if t:
            entry_ts = t.get("entry_ts") or ""
            shares, wanted = t.get("shares") or "", t.get("shares_wanted") or ""
            j.update({"entry_order_ts_et": entry_ts, "entry_shares": shares,
                      "entry_shares_wanted": wanted, "entry_shadow_px": t.get("entry_px", ""),
                      "exit_order_ts_et": t.get("exit_ts", ""), "exit_shares": shares,
                      "exit_shadow_px": t.get("exit_px", ""), "exit_reason": t.get("exit_reason", "")})
            try:
                j["entry_capped"] = int(int(float(shares)) < int(float(wanted)))
            except ValueError:
                j["entry_capped"] = ""
        elif is_open:
            entry_ts = str(lot.get("entry_ts") or "")
            j.update({"entry_order_ts_et": entry_ts, "entry_shares": lot.get("shares_total", ""),
                      "entry_shares_wanted": lot.get("shares_wanted", ""),
                      "entry_shadow_px": lot.get("entry_px", "")})
        if t or is_open:
            if ent["verdict"] != "filled":
                j["primary_status"] = _STATUS[ent["verdict"]]
                j["primary_status_detail"] = _side_detail(ent) + ("; lot still open" if is_open else "")
            elif is_open:
                j["primary_status"] = "open"
            elif ext["verdict"] == "filled":
                j["primary_status"] = "filled"
            else:
                j["primary_status"] = "exit_" + _STATUS[ext["verdict"]]
                j["primary_status_detail"] = _side_detail(ext, "exit ")
        else:
            at = _naive_et(r.get("entry_bar_time"))
            until = ""
            if at:
                until = (_dt.datetime.strptime(at, "%Y-%m-%d %H:%M:%S")
                         + _dt.timedelta(minutes=REFUSED_MATCH_MIN)).strftime("%Y-%m-%d %H:%M:%S")
            refused = [o for o in orders if o.get("leg") == EXEC_LEG and o.get("action") == "ENTER"
                       and str(o.get("reason") or "").startswith("REFUSED")
                       and o.get("side") == r.get("side") and at <= str(o.get("ts_et") or "") <= until]
            desc = _trade_id.describe(sid, _tz())
            skipped = [e for e in events if desc in str(e.get("text") or "")]
            if refused:
                j["primary_status"] = "refused"
                j["primary_status_detail"] = refused[-1].get("reason", "")
                j["entry_order_ts_et"] = refused[-1].get("ts_et", "")
            elif skipped:
                j["primary_status"] = "skipped"
                j["primary_status_detail"] = "; ".join(f"{e.get('kind')}: {e.get('text')}" for e in skipped)
            else:
                j["primary_status"] = "no_order_found"
        # which arms may be scored at all: the arm's own leg traded this signal and exited
        # where the primary did
        div = exit_divergence(r, x, shadow_exits)
        j["exit_divergence"] = "; ".join(div.values())
        present = {nf.PRIMARY_LEG}
        for tid in str(r.get("shadow_trade_ids") or "").split(";"):
            p = _trade_id.parse(tid)
            if p:
                present.add(p["leg"])
        not_scored = {}
        for a in nf.ARMS:
            leg = nf.ARM_LEG[a]
            if leg not in present:
                not_scored[a] = f"no {leg} row"
            elif leg in div:
                not_scored[a] = "exit divergence"
        j["arms_not_scored"] = "; ".join(f"{a}: {why}" for a, why in not_scored.items())
        # the primary's per-share P&L -- Webull fills only, when both sides filled; the book's
        # prices in their own *_book columns -- and each scored arm's dollars on it
        side = -1.0 if str(r.get("side") or "").lower() == "short" else 1.0
        base = nf._f(r.get("base_shares")) or float(nf.DEFAULT_BASE_SHARES)
        if j["primary_status"] == "filled":
            pps = (ext["fill_px"] - ent["fill_px"]) * side
            j["pnl_per_share"] = round(pps, 6)
            for a in nf.ARMS:
                if a in not_scored:
                    continue
                m, sh = nf._f(r.get(f"m_{a}")), nf._f(r.get(f"sh_{a}"))
                j[f"pnl_usd_{a}"] = "" if m is None else round(pps * base * m, 4)
                j[f"pnl_usd_{a}_capped"] = "" if sh is None else round(pps * sh, 4)
        e_book, x_book = nf._f(j.get("entry_shadow_px")), nf._f(j.get("exit_shadow_px"))
        if t and e_book is not None and x_book is not None:
            pps_book = (x_book - e_book) * side
            j["pnl_per_share_book"] = round(pps_book, 6)
            for a in nf.ARMS:
                m = nf._f(r.get(f"m_{a}"))
                if a not in not_scored and m is not None:
                    j[f"pnl_usd_{a}_book"] = round(pps_book * base * m, 4)
        at_ts = entry_ts or _naive_et(r.get("entry_bar_time"))
        if at_ts:
            other = _other_open_shares(trades, lots, at_ts)
            j["other_open_shares"] = other
            total = nf._f(r.get("max_total_shares"))
            if total:
                j["total_cap_refused_arms"] = ",".join(
                    a for a in nf.ARMS if (nf._f(r.get(f"sh_{a}")) or 0) + other > total)
        out.append(j)
    return out


def write_csv(rows, fh):
    w = csv.DictWriter(fh, fieldnames=JOIN_COLS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in JOIN_COLS})


def build_table(paths, since=None, backfill=False, now=None):
    return join_fills(decision_rows(paths, since=since, backfill=backfill, now=now), paths)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=None,
                    help="EDGELOG_HOME-shaped folder to read (default: this host's EDGELOG_HOME)")
    ap.add_argument("--out", default=None, help="CSV to write (default: print to stdout)")
    ap.add_argument("--since", default=None, help="only signals entered on/after YYYY-MM-DD")
    ap.add_argument("--backfill", action="store_true",
                    help="also rebuild decision rows for primary entries the forward log lacks")
    for k in ("forward-log", "signals", "shadow-signals", "ohlc-dir", "keel-dir", "orders",
              "trades", "broker-orders", "exec-state", "qqq-exec-config", "orders-config"):
        ap.add_argument(f"--{k}", default=None)
    a = ap.parse_args(argv)
    from api import cloud_signal as cs
    over = {k.replace("-", "_"): getattr(a, k.replace("-", "_"))
            for k in ("forward-log", "signals", "shadow-signals", "ohlc-dir", "keel-dir", "orders",
                      "trades", "broker-orders", "exec-state", "qqq-exec-config", "orders-config")}
    paths = input_paths(a.home or cs.edgelog_home(), **over)
    rows = build_table(paths, since=a.since, backfill=a.backfill)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            write_csv(rows, f)
        print(f"{len(rows)} row(s) -> {a.out}")
    else:
        write_csv(rows, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
