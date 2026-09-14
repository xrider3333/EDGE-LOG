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
  leg    the signal engine's leg key (letters, digits, underscore only -- anything else is
         refused rather than rewritten, so two legs can never be folded into one id)
  time   the ENTRY BAR's own timestamp, converted to UTC, truncated to whole seconds
  side   L = long, S = short

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

ASSUMES ONE POSITION PER LEG: two different trades of one leg cannot share an entry bar and
side unless a strategy pyramids. None of the crowned plugins do, and the executor itself
holds at most one lot per leg.
"""
import re
from datetime import datetime, timezone

_LEG_RE = re.compile(r"^[A-Za-z0-9_]+$")
_ID_RE = re.compile(r"^([A-Za-z0-9_]+)-(\d{8}T\d{6}Z)-([LS])$")
_SIDE_CODE = {"long": "L", "short": "S", "l": "L", "s": "S"}
_CODE_SIDE = {"L": "long", "S": "short"}


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


def make(leg, entry_time, side, default_tz=None):
    """The canonical trade id for (leg, entry bar time, side), or None when any part is
    unusable. Never raises -- a caller that gets None must treat the trade as having NO
    identity (the executor refuses to act on it), never invent one.

    `entry_time`: aware datetime, pandas Timestamp, or ISO-8601 string with an offset.
    `default_tz`: the zone a NAIVE `entry_time` is in; omitted -> a naive time is refused."""
    leg = str(leg or "").strip()
    if not _LEG_RE.match(leg):
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
    return f"{leg}-{stamp}-{code}"


def parse(trade_id):
    """{"leg", "entry_utc" (aware datetime), "side" ("long"/"short")} or None."""
    m = _ID_RE.match(str(trade_id or "").strip())
    if not m:
        return None
    try:
        entry = datetime.strptime(m.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return {"leg": m.group(1), "entry_utc": entry, "side": _CODE_SIDE[m.group(3)]}


def is_valid(trade_id):
    return parse(trade_id) is not None


def describe(trade_id, tz=None):
    """Short human text for logs and the tab's event timeline, e.g.
    "NOISE_304 long entered 2026-09-03 11:00 ET". Falls back to the raw id."""
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
    return f"{p['leg']} {p['side']} entered {when.strftime('%Y-%m-%d %H:%M')} {label}"
