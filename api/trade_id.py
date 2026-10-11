"""api/trade_id.py -- the ONE stable identity of a strategy trade.

Shared by the signal engine and the executor so both sides compute it the same way:
  * api/cloud_signal.py keys its own emitted-trade memory by it and writes it onto every
    ENTRY and EXIT row of signals.csv (the `trade_id` column, appended last);
  * api/qqq_exec.py stores it on the open shadow lot, closes a lot ONLY with the EXIT row
    that carries the same id, and derives the broker's client_order_id from it.

WHY (2026-09-14, tools/qqq_failover_sim.py scenario F). EXIT rows used to carry no entry
identity -- their ref_time is the EXIT bar -- so the executor closed whatever lot was open
on that leg. A CLI replay that wrote into the live ledger left behind an EXIT for a
2026-09-03 NOISE trade, which the live engine re-emitted at 09:31 ET on 2026-09-14; no lot
happened to be open. Had one been, today's lot would have closed at the old trade's price.

FORMAT   <leg>-<YYYYMMDD>T<HHMMSS>Z-<L|S>        e.g.  NOISE_304-20260903T150000Z-L
         <leg>-<YYYYMMDD>T<HHMMSS>Z-<L|S>-<SLOT> e.g.  DIP_424K-20261009T133000Z-L-RSI
  leg    the signal engine's leg key (letters, digits, underscore only -- anything else is
         refused rather than rewritten, so two legs can never be folded into one id)
  time   the ENTRY BAR's own timestamp, converted to UTC, truncated to whole seconds
  side   L = long, S = short
  slot   OPTIONAL (2026-10-09, DIP #424 shadow legs): the position slot inside a leg whose
         strategy holds several positions at once -- [A-Z0-9]{1,12}, anything else is refused
         (no id), never rewritten. Only a caller that passes `slot` gets one: every id made
         without it is byte-identical to the format above.

DELIBERATELY NOT IN IT
  entry price  Webull and yfinance bars for the same minute can disagree by a cent, and
               the bar cache can hold either; the same trade must keep the same id.
  wall clock   emitted_at / the time a lot opened differ per host and per process.
  row number   every host writes its own ledger; row N on one is not row N on another.

UTC, NOT EASTERN. Every engine timestamp already carries its UTC offset, so the conversion
needs no time-zone database and a Windows PC and a Linux VM cannot disagree about it. A
naive timestamp (no offset) is only accepted when the caller names the zone it means.

The id only uses [A-Za-z0-9_-], so api/webull_orders.py's client_order_id sanitizer leaves
it unchanged (no lossy character mapping between two different ids).

BROKER ORDER IDS (2026-10-10, DIP #424 live leg, OWNER GO MANAGER #115) -- broker_signal_base
below is the ONE place a trade id becomes the Webull client_order_id base ("qx" + the id's
letters and digits + O/C), shared by api/qqq_exec.py (_broker_signal_id), tools/qqq_reprice.py
and tools/qqq_bars_publish.py so the three can never derive different ids for one order. An id
WITHOUT a slot is byte-identical to the rule it always was. An id whose slot is a DIP mechanism
carries a ONE-character slot code instead of the slot name (BROKER_SLOT_CODES: RSI R, DBL D,
PB P, CAP C, IBS I, STREAK S, GAPDN G) -- qxDIP42420261013T133000ZLRO, 27 characters for every
mechanism. With the slot NAME, STREAK made 32 (Webull's documented max): its resends R1-R3 went
over and were hashed, and a split order trims its base to 30 characters before "-<n>", so
STREAK's OPEN and CLOSE part ids both became "...LSTREA-1" and the adapter's idempotency cache
answered the CLOSE with the OPEN's record (the CLOSE never sent). At 27 a resend is 29, a split
part of a resend 31: nothing is hashed or trimmed and OPEN / CLOSE stay distinct. A slot that is
not a known mechanism keeps the old rule (letters and digits of the whole id).

ONE POSITION PER LEG -- UNLESS THE LEG NAMES A SLOT: two different trades of one leg cannot
share an entry bar and side unless a strategy pyramids. None of the crowned plugins do, and
the executor itself holds at most one lot per leg. The one exception is the DIP #424 shadow
legs (api/cloud_signal.py SHADOW_LEGS, no orders): NQDIP_1_1.py runs seven dip mechanisms
side by side, each with its own position, and up to seven of them fill at the same session
open -- so each of those trades carries its mechanism as the slot ("-RSI", "-DBL", ...).
"""
import re
from datetime import datetime, timezone

_LEG_RE = re.compile(r"^[A-Za-z0-9_]+$")
_ID_RE = re.compile(r"^([A-Za-z0-9_]+)-(\d{8}T\d{6}Z)-([LS])(?:-([A-Z0-9]{1,12}))?$")
_SLOT_RE = re.compile(r"^[A-Z0-9]{1,12}$")
_SIDE_CODE = {"long": "L", "short": "S", "l": "L", "s": "S"}
_CODE_SIDE = {"L": "long", "S": "short"}
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")
# DIP #424's seven mechanisms (api/cloud_signal.DIP_MECHS order, NQDIP_1_1.py:286-287) -> the
# one-character code a broker order id carries for that slot (see BROKER ORDER IDS above).
# The keys are also the live leg's slots: api/qqq_exec.py maps slot X to exec leg DIP_<X>.
BROKER_SLOT_CODES = {"RSI": "R", "DBL": "D", "PB": "P", "CAP": "C", "IBS": "I",
                     "STREAK": "S", "GAPDN": "G"}
_INTENT_CODE = {"OPEN": "O", "CLOSE": "C"}


def _as_aware_datetime(value, default_tz=None):
    """datetime (pandas Timestamp included) or ISO-8601 string -> aware datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        if default_tz is None:
            return None
        dt = dt.replace(tzinfo=default_tz)
    return dt


def make(leg, entry_time, side, default_tz=None, slot=None):
    """The canonical trade id for (leg, entry bar time, side), or None when any part is
    unusable. Never raises -- a caller that gets None must treat the trade as having NO
    identity (the executor refuses to act on it), never invent one.

    `entry_time`: aware datetime, pandas Timestamp, or ISO-8601 string with an offset.
    `default_tz`: the zone a NAIVE `entry_time` is in; omitted -> a naive time is refused.
    `slot`: None (every leg but DIP #424's) -> exactly the id this always made; else the
    position slot ([A-Z0-9]{1,12}, e.g. "RSI"), appended as "-RSI" -- anything else is None."""
    leg = str(leg or "").strip()
    if not _LEG_RE.match(leg):
        return None
    if slot is not None and not _SLOT_RE.fullmatch(str(slot)):     # fullmatch: never "RSI" + newline
        return None
    code = _SIDE_CODE.get(str(side or "").strip().lower())
    if code is None:
        return None
    dt = _as_aware_datetime(entry_time, default_tz=default_tz)
    if dt is None:
        return None
    try:
        stamp = dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except (OverflowError, ValueError, OSError):
        return None
    if slot is not None:
        return f"{leg}-{stamp}-{code}-{slot}"
    return f"{leg}-{stamp}-{code}"


def parse(trade_id):
    """{"leg", "entry_utc" (aware datetime), "side" ("long"/"short"), "slot" (None unless
    the id carries one)} or None."""
    m = _ID_RE.match(str(trade_id or "").strip())
    if not m:
        return None
    try:
        entry = datetime.strptime(m.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return {"leg": m.group(1), "entry_utc": entry, "side": _CODE_SIDE[m.group(3)],
            "slot": m.group(4)}


def is_valid(trade_id):
    return parse(trade_id) is not None


def broker_id_body(trade_id):
    """The letters and digits of `trade_id` a broker order id carries (see BROKER ORDER IDS):
    the whole id with its separators removed -- except a DIP mechanism slot, which becomes its
    one-character code (BROKER_SLOT_CODES). Never raises; "" for no id."""
    s = str(trade_id or "")
    p = parse(s)
    code = BROKER_SLOT_CODES.get((p or {}).get("slot") or "")
    if p is None or code is None:
        return _NON_ALNUM.sub("", s)
    m = _ID_RE.match(s.strip())
    return (_NON_ALNUM.sub("", m.group(1)) + m.group(2) + m.group(3) + code)


def broker_signal_base(trade_id, intent):
    """The broker signal id base for one side of a trade: "qx" + broker_id_body + the intent
    code (OPEN "O", CLOSE "C", any other intent its first letter, upper-cased). Every caller --
    api/qqq_exec.py _broker_signal_id, tools/qqq_reprice.py, tools/qqq_bars_publish.py -- goes
    through here. Never raises."""
    it = str(intent or "").upper()
    return "qx" + broker_id_body(trade_id) + _INTENT_CODE.get(it, it[:1])


def describe(trade_id, tz=None):
    """Short human text for logs and the tab's event timeline, e.g.
    "NOISE_304 long entered 2026-09-03 11:00 ET" (a slot id adds " [RSI]"). Falls back to
    the raw id."""
    p = parse(trade_id)
    if p is None:
        return str(trade_id or "(no trade id)")
    when = p["entry_utc"]
    label = "UTC"
    if tz is not None:
        try:
            when = when.astimezone(tz)
            label = "ET"
        except Exception:
            pass
    return (f"{p['leg']} {p['side']} entered {when.strftime('%Y-%m-%d %H:%M')} {label}"
            + (f" [{p['slot']}]" if p.get("slot") else ""))
