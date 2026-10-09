"""Webull ORDER adapter for EDGELOG strategies (api/webull_orders.py).

Lets a strategy place a stock/ETF order through Webull's OFFICIAL OpenAPI, in one of
three modes, DEFAULT OFF:

  OFF   -- records the would-be order to the local state file and logs it. Sends
           NOTHING over the network. This is the default with no config at all.
  PAPER -- targets Webull's sandbox/paper environment using a SEPARATE credentials
           file (default C:\\EdgeLog\\webull_paper_keys.json, overridable via
           EDGELOG_WEBULL_PAPER_KEYS so the cloud VM can point at its own copy). If
           that file is missing or still has the placeholder values, this logs ONE
           clear line naming exactly what the owner needs to do and no-ops -- it
           NEVER falls back to the live key file used by api/webull_sync.py.
  LIVE  -- requires BOTH cfg["mode"]=="LIVE" in the order config file AND a
           hand-created arm file (default C:\\EdgeLog\\webull_orders\\ARM_LIVE,
           overridable via EDGELOG_WEBULL_ARM_LIVE) to exist. If either is missing,
           behaves exactly like OFF and says why. Nothing in this module creates that
           arm file or flips a config to "LIVE" -- both are the owner's hand, always.

SANDBOX TARGETING (verified 2026-09-13 from the installed `webull` SDK's own source,
not from any live paper credentials -- none exist on this machine): the SDK ships
PRODUCTION hosts only (webull/core/data/endpoints.json: region "us" -> api.webull.com /
data-api.webull.com / events-api.webull.com), resolved by
webull.core.endpoint.local_config_regional_endpoint_resolver.LocalConfigRegionalEndpointResolver.
webull.core.client.ApiClient.add_endpoint(region_id, host, api_type) registers an
override in webull.core.endpoint.user_customized_endpoint_resolver.UserCustomizedEndpointResolver,
which webull.core.endpoint.default_endpoint_resolver.DefaultEndpointResolver consults
FIRST, before the file-based resolver -- so calling add_endpoint("us", <sandbox host>)
on the SAME region id used to build the client (region_id="us") is how this module
reaches the sandbox instead of production, with no SDK fork needed. Hosts per
developer.webull.com/apis/docs/sdk/ (2026-07-21 paper-trading announcement): trading
`api.sandbox.webull.com`, events `events-api.sandbox.webull.com`. Market-data sandbox
(`us-global-openapi.uat.webullbroker.com`) is NOT wired here -- this module only places
orders, it does not pull quotes.

ORDER CALLS USED (all real SDK calls, nothing hand-rolled -- verified by reading the
installed package under site-packages/webull, version pinned in api/requirements.txt
as webull-openapi-python-sdk): webull.trade.trade_client.TradeClient built on an
ApiClient exposes `.order_v3` (webull.trade.trade.v3.order_opration_v3.OrderOperationV3)
with place_order/preview_order/cancel_order/get_order_detail/get_order_history/
get_order_open, and `.account_v2` (webull.trade.trade.v2.account_info_v2.AccountV2) with
get_account_list/get_account_balance/get_account_position. Order/side/type/tif string
values are the `.name` of the SDK's own enums (webull.trade.common.order_side.OrderSide,
.order_type.OrderType, .order_tif.OrderTIF -- EasyEnum.__str__ returns .name, e.g.
str(OrderSide.BUY)=="BUY"), so this module validates against ORDER_SIDES/ORDER_TYPES/
ORDER_TIFS -- plain-string mirrors of those enums' members, kept near CLIENT_ORDER_ID_MAX
below -- rather than inventing values. Validation is done against the local mirrors, not
a live import of the enums themselves, so it works (and OFF mode stays import-free) even
where the `webull` package isn't installed at all -- see those constants' own comment.

ORDER API VERSION (switched 2026-09-13, per developer.webull.com/apis/docs -- the
current Trading API getting-started sample calls `order_v3`, not `order_v2`): v3's
place_order/preview_order take a SYMBOL-keyed order dict (combo_type="NORMAL",
client_order_id, symbol, instrument_type="EQUITY", market="US", order_type,
limit_price, quantity (as a STRING), support_trading_session="CORE", side,
time_in_force, entrust_type="QTY") -- there is no instrument_id to resolve first, so
_resolve_instrument_id()/`.trade_instrument` are no longer on the order-placement path
(kept, unused, as a record of how the older v2 path worked, in case a future v3 call
needs symbol resolution after all). cancel_order(account_id, client_order_id) and
get_order_detail(account_id, client_order_id) keep the same shape on v3. The installed
SDK is webull-openapi-python-sdk==2.0.12, which already ships order_v3 -- do NOT
upgrade the pinned SDK (api/webull_sync.py depends on the 2.0.12 API shape); PyPI's
latest is 3.0.0, noted here only so nobody "helpfully" bumps it later.
ORDER SIDE CAVEAT: the installed SDK's OrderSide enum has exactly three members --
BUY/SELL/SHORT, no COVER -- so closing a short position is sent as BUY (see
api/qqq_exec.py's _broker_side, the only caller that closes shorts); unverified against
a live sandbox fill since no paper credentials exist on this machine.
ORDER STATUS: could also be pushed via webull.trade.trade_events_client.
TradeEventsClient(app_key, app_secret, region).on_events_message + do_subscribe(
[account_id]) instead of polling get_order_detail. NOT wired here -- polling is
adequate for this first cut (status/reconcile are called on demand, not on a tight
loop) and avoids a second long-lived connection per mode; revisit if fill latency
against the shadow book's own price ever matters enough to justify it.

ORDER NETTING (2026-09-24, "three legs, one Webull account"). Every leg calling this
adapter (ORB/ENGUQ/NOISE, all trading QQQ) shares ONE Webull margin paper account, and
Webull holds exactly ONE position per symbol -- it has no idea a "leg" exists. Before
this, a leg's own SELL/SHORT/BUY request went straight to the broker as that literal
side, so two legs that disagreed (one long, one wanting short) collided: Webull refused
the second one with HTTP 417 (OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION -- "close your
existing long positions... before placing a short order"), and the book recorded a trade
Webull never held. place_stock_order (PAPER/LIVE only -- OFF never talks to a broker, so
there is nothing to net against) now plans the ACTUAL broker order(s) from the ACCOUNT's
current net position for that symbol (_account_net -- the sum of every leg's
broker_sent_positions, the same "what actually reached the broker" book reconcile()
trusts, never believed_positions) rather than the leg's own literal side:

  * a SELL-direction request (a long leg closing, or a short leg opening) sends SELL
    while the account has enough long to absorb it, SHORT once the account is at or
    below flat, and SPLITS into SELL-the-rest-of-the-long + SHORT-the-remainder when
    the requested qty would cross through zero;
  * a BUY-direction request (a long leg opening, or a short leg closing) sends a plain
    BUY, unless the account is short by less than the requested qty, in which case it
    SPLITS into BUY-to-flat + BUY-the-remainder.

See _plan_broker_parts for the exact boundary rules and GUESSED BEHAVIOUR below for why
splitting exists at all. Every per-leg protection (max_shares_per_leg, the nothing-to-
close guard, one_open_position_per_leg, the daily-loss/session/kill-file rails) is
evaluated ONCE, before any of this, against the leg's own requested qty exactly as
before -- netting only changes what gets SENT, never what gets ALLOWED. One
place_stock_order call is always ONE returned record (see its own docstring for the
`parts` field this adds), regardless of how many broker orders it took.

GUESSED BEHAVIOUR (no live sandbox to confirm against, per this module's own standing
disclaimer -- flagging per this feature's own build note): Webull's docs do not say
whether a single order that would cross an account from short to long (or long to
short) is accepted as one order or refused the way a same-direction crossing is
documented to be (the 417 above). This module assumes the WORSE case -- that crossing
zero in one order is never safe -- and always splits at the zero point instead of
finding out by sending the risky single order. If Webull actually accepts a
crossing order fine, this is one harmless extra API call per crossing event, not a
correctness bug.

RAILS (enforced inside this adapter in EVERY mode, including OFF -- a blocked order
is recorded with mode="BLOCKED" and never reaches the mode dispatch below it):
max shares per leg, max total believed position (shares, summed across legs), a daily
loss limit fed by the caller via update_daily_pnl(), a session time window, a kill
file (default C:\\EdgeLog\\webull_orders\\KILL, same pattern as api/qqq_exec.py's
KILL flatten switch), one open position per leg, and reconcile() -- comparing the
broker's live position (PAPER/LIVE) against the sum of this adapter's own lots that
actually reached the broker (see reconcile()'s own docstring for why that is NOT the
same as this module's "believed" bookkeeping). A mismatch, OR a failed/timed-out
position read (2026-09-14: this used to silently do nothing), halts all new entries
(CLOSE intents still pass) -- self-clearing once a LATER reconcile succeeds, or via a
fresh adapter/state file, same as before.

IDEMPOTENCY: client_order_id is derived deterministically from the caller's signal_id
(sanitized, or a stable sha1 if it doesn't fit Webull's 32-char field -- see
CLIENT_ORDER_ID_MAX) and every order
attempt (blocked, OFF, or sent) is persisted to a local JSON state file keyed by that
id BEFORE returning. A second call with the same signal_id -- including after a
process restart -- returns the cached record with duplicate=True and sends nothing.

FUTURES: staged, not wired. resolve_futures_contract() and place_futures_order() both
raise NotImplementedError with a message naming the real market-data endpoints that
would resolve a contract (webull.data.quotes.instrument.Instrument.get_futures_products
/ get_futures_instrument, category="US_FUTURES") and the reason it's disabled: Webull
futures orders do not support combo orders (OCO/OTO/OTOCO), so stop-loss/target exits
would have to be managed entirely in this adapter's own software before it's safe to
enable -- that exit-management logic does not exist yet. NOTE: the SDK's own
webull.trade.common.instrument_type.InstrumentType enum only defines
STOCK/ETF/UNIT/WARRANT/RIGHT/CALL_OPTION/PUT_OPTION -- it has no FUTURES member even
though webull.trade.common.category.Category does (US_FUTURES/HK_FUTURES) -- so a real
futures order would need instrument_type passed as a raw "FUTURES" string, not an enum
member. Recorded here so whoever enables futures later isn't surprised by it.

SECRETS: this module never reads, logs, or persists an app_key/app_secret/token value
anywhere in the state file or its own log lines -- only booleans ("credentials
present"), file paths, and order/rail metadata.
"""
import contextlib
import hashlib
import json
import math
import os
import re
import threading
import time
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:
    _NY = None

try:
    from . import market_calendar
except ImportError:   # loaded outside the api package (a tool or a baseline copy)
    import market_calendar

import logging
# Same reasoning as api/webull_sync.py: on any API error the SDK's client logger dumps
# the full signed request -- including x-app-key / x-access-token -- at ERROR level.
logging.getLogger("webull.core.client").setLevel(logging.CRITICAL)


# ── modes ───────────────────────────────────────────────────────────
MODE_OFF = "OFF"
MODE_PAPER = "PAPER"
MODE_LIVE = "LIVE"
_VALID_MODES = (MODE_OFF, MODE_PAPER, MODE_LIVE)


# ── EDGELOG_HOME (2026-09-13, "fill-in-the-blanks Oracle Cloud move") ───────────────
# Every path below used to be a bare C:\EdgeLog\... literal, which only made sense on
# the owner's Windows PC. EDGELOG_HOME is the one base directory a Linux VM sets
# differently; every specific-file env var (EDGELOG_WEBULL_PAPER_KEYS, etc.) still
# overrides its own default individually, exactly as before -- this only changes what
# the DEFAULT is when none of those are set. On Windows with EDGELOG_HOME unset, every
# path below is byte-identical to the old hardcoded literal (os.path.join with
# "C:\\EdgeLog" reproduces the same backslashed string).
def _default_edgelog_home():
    return r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog"


EDGELOG_HOME = os.environ.get("EDGELOG_HOME") or _default_edgelog_home()

# ── paths (every one overridable so the cloud VM can point at its own copies) ──
DEFAULT_CONFIG_PATH = os.environ.get("EDGELOG_WEBULL_ORDERS_CONFIG",
                                     os.path.join(EDGELOG_HOME, "webull_orders", "config.json"))
DEFAULT_PAPER_KEYS = os.environ.get("EDGELOG_WEBULL_PAPER_KEYS",
                                    os.path.join(EDGELOG_HOME, "webull_paper_keys.json"))
DEFAULT_PAPER_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_PAPER_TOKEN_DIR",
                                         os.path.join(EDGELOG_HOME, "webull_paper_token"))
DEFAULT_LIVE_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS",
                                   os.path.join(EDGELOG_HOME, "webull_keys.json"))  # same var as webull_sync.py
DEFAULT_LIVE_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR",
                                        os.path.join(EDGELOG_HOME, "webull_token"))
DEFAULT_ARM_LIVE_FILE = os.environ.get("EDGELOG_WEBULL_ARM_LIVE",
                                       os.path.join(EDGELOG_HOME, "webull_orders", "ARM_LIVE"))
DEFAULT_KILL_FILE = os.environ.get("EDGELOG_WEBULL_ORDERS_KILL",
                                   os.path.join(EDGELOG_HOME, "webull_orders", "KILL"))
DEFAULT_STATE_PATH = os.environ.get("EDGELOG_WEBULL_ORDERS_STATE",
                                    os.path.join(EDGELOG_HOME, "webull_orders", "state.json"))

# See the module docstring's SANDBOX TARGETING section for how these get wired in.
SANDBOX_REGION = "us"
SANDBOX_TRADE_HOST = "api.sandbox.webull.com"
SANDBOX_EVENTS_HOST = "events-api.sandbox.webull.com"

_PLACEHOLDERS = ("", "PASTE_APP_KEY_HERE", "PASTE_APP_SECRET_HERE")

DEFAULT_RAILS = {
    "max_shares_per_leg": 10,
    "max_total_position_shares": 50,
    "daily_loss_limit_usd": 200.0,
    "session_start": "09:30",   # NY local, HH:MM, inclusive
    "session_end": "16:00",
    "one_open_position_per_leg": True,
}

# ── account selection (2026-09-14, first LIVE paper smoke test) ────────────────────
# _account_id() used to take accts[0] from get_account_list() -- "whichever account
# Webull lists first". That is accidental, not deliberate: the smoke test's account
# list came back MARGIN Individual Margin, MARGIN Futures, CASH Individual Cash, CASH
# Events, CASH Crypto -- accts[0] would have placed a STOCK order against the Individual
# MARGIN account, not the Individual Cash one the owner actually wants funding stock
# orders, and a paper-account reset silently renumbers/reorders accounts on top of that.
# DEFAULT_ACCOUNT_SELECT names the account_class (see developer.webull.com/apis/docs/
# reference/account-list/ -- account_class possible values include INDIVIDUAL_CASH,
# INDIVIDUAL_MARGIN, FUTURES, CRYPTO, EVENTS_CASH) each order "purpose" should resolve
# to; cfg["account"] overrides this per-key (load_config() merges it like "rails").
# futures stays hard-disabled (place_futures_order raises before ever calling
# _account_id) -- the "futures" entry is here so the config shape is already right for
# whenever that changes, per this module's existing "staged, not wired" convention.
#
# STOCK MOVED CASH -> MARGIN (2026-09-23, owner: "switch it to the margin paper
# account"). A CASH account cannot hold short stock, and the QQQ book's legs are
# two-sided. The first short the cloud book ever signalled -- NOISE, 2026-09-23 10:10 ET,
# SHORT 10 QQQ -- came back HTTP 417 OPENAPI_GENERATE_NEW_SHORT_POSITION, "This order
# will generate new short stock positions, which do not match your account type", so the
# book held a short that Webull never did (the CLOSE was then correctly refused by the
# nothing-to-close guard). Every future short would have failed the same way: 22 entries
# since the cloud book went live, 21 long and that one. Paper accounts on this login:
# INDIVIDUAL_MARGIN ...HM55 (now used for stock, $1,000,000 and flat when switched) and
# INDIVIDUAL_CASH ...HLZ5 (previously used). Changing the shared default rather than one
# host's config file is deliberate -- the PC and the cloud box must resolve the SAME
# account or a failover would trade a different one.
DEFAULT_ACCOUNT_SELECT = {
    "stock": "INDIVIDUAL_MARGIN",
    "futures": "FUTURES",
}

FUTURES_NOT_ENABLED = (
    "Futures order routing is staged but NOT ENABLED: Webull futures orders do not "
    "support combo orders (OCO/OTO/OTOCO), so stop-loss/target exits would have to be "
    "managed entirely in this adapter's own software, and that logic does not exist "
    "yet. Contract resolution would use webull.data.quotes.instrument.Instrument."
    "get_futures_products / get_futures_instrument (category='US_FUTURES', e.g. MNQ "
    "front month) on the market-data client -- a separate host from order placement, "
    "not built here. Refusing."
)


# ── small helpers (kept local/self-contained -- this module owns no other file) ──

def _field(o, *names, default=None):
    """First non-empty value among candidate key names (Webull payload shapes vary)."""
    if not isinstance(o, dict):
        return default
    for n in names:
        v = o.get(n)
        if v not in (None, ""):
            return v
    return default


def _safe_response(resp):
    """SDK Response -> plain JSON. Never raises; a response we can't parse is
    returned as-is so the caller still gets SOMETHING back for logging."""
    try:
        return resp.json()
    except Exception:
        return resp


def _as_list(payload):
    if payload is None:
        return []
    if isinstance(payload, dict):
        for k in ("data", "items", "positions", "list"):
            if isinstance(payload.get(k), list):
                return payload[k]
        return [payload]
    if isinstance(payload, list):
        return payload
    return []


def _positions_from_response(resp):
    """Broker position payload -> {symbol: signed_qty}. Same defensive field-name
    matching style as api/webull_sync.py's fetch_positions/_open_positions."""
    out = {}
    for it in _as_list(_safe_response(resp)):
        if not isinstance(it, dict):
            continue
        sym = str(_field(it, "symbol", "ticker", "disSymbol", default="")).upper().strip()
        if not sym:
            continue
        try:
            q = float(_field(it, "quantity", "qty", "position", "shares", default=0) or 0)
        except (TypeError, ValueError):
            continue
        if "SHORT" in str(_field(it, "side", "position_side", "positionSide", default="")).upper():
            q = -abs(q)
        out[sym] = out.get(sym, 0.0) + q
    return {s: round(q, 4) for s, q in out.items() if abs(q) > 1e-9}


def _account_class(a):
    return str(_field(a, "account_class", "accountClass", default="")).upper()


def _account_label_key(a):
    """account_label normalized to look like an account_class value, e.g. "Individual
    Cash" -> "INDIVIDUAL_CASH" -- see developer.webull.com/apis/docs/reference/
    account-list/, whose documented account_label values map 1:1 onto its account_class
    enum this way (also: "Futures"->"FUTURES", "Events Cash"->"EVENTS_CASH"). Used only
    as a fallback when a response omits account_class outright."""
    label = _field(a, "account_label", "accountLabel", default="")
    return str(label).upper().replace(" ", "_")


def _account_last4(a):
    num = str(_field(a, "account_number", "accountNumber", "acctNumber", default="") or "")
    return num[-4:] if len(num) >= 4 else ""


def _describe_account(a):
    """Non-secret one-line description for error messages/logs -- class + last 4 of the
    account NUMBER only, never the full number (same last-4-only discipline as
    tools/webull_paper_smoke.py's --check output and its redaction rules)."""
    cls = _account_class(a) or _account_label_key(a) or "UNKNOWN_CLASS"
    return f"{cls}:...{_account_last4(a) or '????'}"


def _account_selector_key(purpose, cfg):
    """Canonical string identifying what THIS purpose's account selection is currently
    configured to pick -- either "last4:XXXX" or "class:SOME_CLASS". The single source
    of truth for both _select_account() (what to actually match on) and _account_id()'s
    disk-cache validity check (a cached id is trustworthy only for the exact selector it
    was resolved under) -- computing "the configured class" independently in two places
    was a real bug during review: it made the disk-cache fallback compare against the
    class-based default even when a last4 override was what actually chose the account,
    so removing/changing a last4 override could resurrect an id chosen under a
    completely different rule."""
    sel = cfg.get("account") if isinstance(cfg.get("account"), dict) else {}
    last4 = sel.get(f"{purpose}_last4")
    if last4:
        return f"last4:{str(last4)[-4:]}"
    want = str(sel.get(purpose) or DEFAULT_ACCOUNT_SELECT.get(purpose) or "").upper()
    return f"class:{want}"


def _select_account(accts, purpose, cfg):
    """Pick the one account in `accts` (get_account_list() items) this adapter should
    use for `purpose` ("stock" or "futures"). Raises RuntimeError -- never guesses --
    when nothing matches or more than one account does; see DEFAULT_ACCOUNT_SELECT's
    docstring comment for why accts[0] is never an acceptable fallback here."""
    kind, _, value = _account_selector_key(purpose, cfg).partition(":")
    if kind == "last4":
        matches = [a for a in accts if _account_last4(a) == value]
        basis = f"account_number ending {value}"
    else:
        want = value
        if not want:
            raise RuntimeError(f"no account class configured for purpose={purpose!r} and "
                               f"no default -- set cfg['account'][{purpose!r}]")
        matches = [a for a in accts if _account_class(a) == want]
        if not matches:
            # account_class was blank/absent on every row -- fall back to the
            # documented account_label, normalized (see _account_label_key).
            matches = [a for a in accts if _account_label_key(a) == want]
        basis = f"account_class={want!r}"
    if not matches:
        seen = ", ".join(sorted({_describe_account(a) for a in accts})) or "(none returned)"
        raise RuntimeError(f"no account matches {basis} (purpose={purpose!r}); accounts "
                           f"seen: {seen}")
    if len(matches) > 1:
        seen = ", ".join(sorted({_describe_account(a) for a in accts}))
        raise RuntimeError(f"{len(matches)} accounts match {basis} (purpose={purpose!r}), "
                           f"ambiguous -- narrow it with an explicit "
                           f"cfg['account']['{purpose}_last4']; accounts seen: {seen}")
    return matches[0]


# ── order-detail response parsing (2026-09-14, first LIVE paper smoke test) ────────
# Webull's v3 order endpoints (place_order/cancel_order/get_order_detail) return a
# COMBO-shaped payload -- client_order_id/combo_order_id/combo_type at the top level,
# with every actual per-order field (status, filled_quantity, filled_price, commission,
# fees, ...) nested one level down in an `orders` list. Verified two ways: the real
# sandbox order-status response captured during that smoke test, AND the documented
# schema at developer.webull.com/apis/docs/reference/order-detail/ (Get Order Detail),
# which lists `orders` as a REQUIRED object[] holding all of those fields -- the top
# level only carries client_order_id/combo_order_id/combo_type. A caller that reads
# top-level `status` directly (as tools/webull_paper_smoke.py's _extract_order_status
# used to) always gets None, because that key simply isn't there.
def _order_items(response):
    """The list of per-order dicts inside a v3 combo response, or [] if `response`
    isn't shaped that way (no "orders" key, or it isn't a list)."""
    if isinstance(response, dict):
        orders = response.get("orders")
        if isinstance(orders, list):
            return [o for o in orders if isinstance(o, dict)]
    return []


def _order_item(response, client_order_id=None):
    """The single per-order dict `response` is actually reporting on. Matches by
    client_order_id when given and present among response["orders"]; otherwise returns
    the first entry (this adapter only ever places single-order combos, so "first" is
    "the" order in every real call this module makes). Falls back to `response` itself
    (if a dict) when "orders" is absent/empty -- covers a response shape that predates
    this nesting, or an unrelated payload, so a caller still gets *something* to read
    top-level fields from instead of nothing."""
    items = _order_items(response)
    if items:
        if client_order_id is not None:
            for o in items:
                coid = _field(o, "client_order_id", "clientOrderId")
                if coid is not None and str(coid) == str(client_order_id):
                    return o
        return items[0]
    return response if isinstance(response, dict) else None


def order_status_fields(response, client_order_id=None):
    """{status, filled_quantity, filled_price, commission, fees} parsed out of a v3
    place/cancel/get_order_detail response -- see _order_item for how the right
    per-order dict is located first. Every value is returned exactly as Webull sent it
    (strings, mostly) -- callers cast. Never raises; a value genuinely not present in
    the payload comes back None.

    FIELD NAMES (verified 2026-09-14 against developer.webull.com/apis/docs/reference/
    order-detail/ -- the Get Order Detail schema -- and cross-checked against a real
    sandbox SUBMITTED/CANCELLED response captured the same day):
      status           -- one of PENDING/SUBMITTED/CANCELLED/FILLED/FAILED/
                           PARTIAL_FILLED.
      filled_quantity  -- string, e.g. "0" before anything fills.
      filled_price     -- string. Documented as "Average transaction price of the
                           filled quantity. If the order has not been executed yet,
                           this may be zero or null." THIS is the documented fill-price
                           field -- earlier code in this repo (api/qqq_exec.py's
                           _extract_broker_fill_price) guessed at avg_price/
                           avg_fill_price/avgFillPrice/etc. and never actually listed
                           "filled_price" (snake_case) among them, only camelCase
                           "filledPrice"; api/webull_sync.py's _order_to_fill (a
                           DIFFERENT endpoint, get_order_history) already happened to
                           include "filled_price" in its own candidate list. Kept as a
                           fallback below alongside those other guesses in case a
                           different endpoint/API version ever uses one of them.
      commission       -- OBJECT {actual_commission, receivable_commission}, NOT a
                           number -- e.g. {} before anything fills.
      fees             -- ARRAY of {type, actual_value, receivable_value} breakdown
                           entries, NOT a number -- e.g. [] before anything fills.
    """
    item = _order_item(response, client_order_id)
    if not isinstance(item, dict):
        return {"status": None, "filled_quantity": None, "filled_price": None,
               "commission": None, "fees": None}
    return {
        "status": _field(item, "status", "order_status", "orderStatus"),
        "filled_quantity": _field(item, "filled_quantity", "filledQuantity",
                                  "filled_qty", "filled"),
        "filled_price": _field(item, "filled_price", "filledPrice", "avg_price",
                               "avgPrice", "avg_filled_price", "avgFilledPrice",
                               "avg_fill_price", "avgFillPrice"),
        "commission": item.get("commission"),
        "fees": item.get("fees"),
    }


def fees_total(fields):
    """Sum the `fees`/`commission` shapes order_status_fields() returns into one float.
    fees is documented as a LIST of {actual_value, receivable_value, ...} breakdown
    entries; commission is a single {actual_commission, receivable_commission} object
    -- neither is a bare number, but a bare number is also accepted defensively (e.g. a
    different endpoint/version). Never raises; an unparseable entry is skipped, not
    fatal to the total."""
    total = 0.0
    fees = fields.get("fees") if isinstance(fields, dict) else None
    if isinstance(fees, list):
        for f in fees:
            if isinstance(f, dict):
                v = _field(f, "actual_value", "receivable_value", "value")
                try:
                    if v is not None:
                        total += abs(float(v))
                except (TypeError, ValueError):
                    pass
    elif fees is not None:
        try:
            total += abs(float(fees))
        except (TypeError, ValueError):
            pass
    commission = fields.get("commission") if isinstance(fields, dict) else None
    if isinstance(commission, dict):
        v = _field(commission, "actual_commission", "receivable_commission")
        try:
            if v is not None:
                total += abs(float(v))
        except (TypeError, ValueError):
            pass
    elif commission is not None:
        try:
            total += abs(float(commission))
        except (TypeError, ValueError):
            pass
    return round(total, 4)


# Webull's US stock order reference (developer.webull.com/apis/docs/trade-api/stock/, checked
# 2026-09-14): client_order_id "max 32 chars, must be unique per account". The 40 this used
# to allow comes from the SDK's HONG KONG order_operation.place_order docstring, not the US
# order_v3 path this module calls.
CLIENT_ORDER_ID_MAX = 32

# ── order enum mirrors (2026-09-14, "OFF mode must never import webull") ───────────
# place_stock_order() used to validate side/order_type/tif by importing the SDK's own
# webull.trade.common.order_side.OrderSide / order_type.OrderType / order_tif.OrderTIF
# enums UNCONDITIONALLY at the top of the method -- reached on EVERY call including
# OFF mode and every rails-only/BLOCKED path, contradicting this module's own docstring
# ("this module imports and validates against those enums") and the OFF-mode contract
# ("OFF mode never imports webull") a few lines below in this same file. On a box
# without the proprietary `webull` package installed (e.g. CI) that made OFF mode --
# the default, no-network path -- raise ModuleNotFoundError. These tuples are plain-
# string mirrors of each enum's `.name` values (EasyEnum.__str__ returns .name, e.g.
# str(OrderSide.BUY) == "BUY"), verified against the installed webull-openapi-python-sdk
# 2.0.12: OrderSide has BUY/SELL/SHORT (no COVER, see the module docstring's ORDER SIDE
# CAVEAT), OrderType has the 11 members below, OrderTIF has DAY/GTC/IOC. Validation
# against these never needs the real package -- only _build_client() (PAPER/LIVE only)
# and the SDK call sites inside the try block below still touch it.
ORDER_SIDES = ("BUY", "SELL", "SHORT")
ORDER_TYPES = ("MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_LIMIT", "TRAILING_STOP_LOSS",
               "ENHANCED_LIMIT", "AT_AUCTION", "AT_AUCTION_LIMIT", "ODD_LOT_LIMIT",
               "MARKET_ON_OPEN", "MARKET_ON_CLOSE")
ORDER_TIFS = ("DAY", "GTC", "IOC")


def _sanitize_client_order_id(signal_id):
    """Deterministic, idempotent client_order_id from a caller's signal_id: kept verbatim
    (non [A-Za-z0-9_-] characters mapped to "-") when it fits CLIENT_ORDER_ID_MAX, otherwise
    a stable hash of the raw id that fits exactly ("sig" + 29 hex = 32 characters,
    letters and digits only, the same shape as Webull's own uuid4().hex sample). The hash
    is taken over the RAW id, so two ids that only differ in mapped characters still get
    distinct values once they are hashed."""
    raw = str(signal_id)
    safe = "".join(c if (c.isascii() and c.isalnum()) or c in "-_" else "-" for c in raw)
    if 0 < len(safe) <= CLIENT_ORDER_ID_MAX:
        return safe
    return "sig" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:CLIENT_ORDER_ID_MAX - 3]


# ── ORDER NETTING (2026-09-24) -- see the module docstring's ORDER NETTING section for
# why this exists. Both helpers are pure/stateless (no self, no I/O) so the split
# arithmetic and the id scheme can be tested directly, with no adapter/state/SDK at all.

def _plan_broker_parts(net, direction, qty):
    """The broker order(s) that implement a `direction`-qty request for one symbol,
    given the ACCOUNT's current net position `net` for that symbol (see _account_net --
    the sum of every leg's broker_sent_positions, not this one leg's own belief).
    Returns a list of (side, qty) tuples, side in ORDER_SIDES, each qty a positive int,
    in the order they must be sent; a plain (unsplit) request comes back as a
    single-element list.

    `direction` is "SELL" for a SELL-direction request (a long leg closing, or a short
    leg opening -- both move the account toward more negative) or "BUY" for a
    BUY-direction request (a long leg opening, or a short leg closing -- both move it
    toward more positive). This is deliberately NOT the same thing as the leg's own
    literal side (SELL vs SHORT, BUY vs BUY) -- see the module docstring: Webull has one
    position per symbol, so what matters is only which way this request pushes it and
    by how much, never which of SELL/SHORT the leg itself asked for.

      SELL-direction qty:
        net >= qty       -> [("SELL", qty)]            -- enough long to absorb it
        net <= 0         -> [("SHORT", qty)]            -- already flat or short
        0 < net < qty    -> [("SELL", net), ("SHORT", qty - net)]   -- crosses zero

      BUY-direction qty:
        net < 0 and qty > -net -> [("BUY", -net), ("BUY", qty - (-net))]  -- crosses zero
        otherwise               -> [("BUY", qty)]

    See the module docstring's GUESSED BEHAVIOUR paragraph for why a crossing request is
    always split rather than sent as one order that happens to cross through zero."""
    qty = int(round(qty))
    if qty <= 0:
        return []
    if direction == "SELL":
        if net >= qty:
            return [("SELL", qty)]
        if net <= 0:
            return [("SHORT", qty)]
        net_i = int(round(net))
        return [("SELL", net_i), ("SHORT", qty - net_i)]
    # BUY-direction.
    if net < 0 and qty > -net:
        cover = int(round(-net))
        return [("BUY", cover), ("BUY", qty - cover)]
    return [("BUY", qty)]


def _part_client_order_id(base, index, total):
    """client_order_id for one broker part of a place_stock_order call. Returned AS-IS
    (`base`, the same id a non-split order has always used) when `total` <= 1 -- a leg
    event that does not collide with another leg's position sends the EXACT id it
    always has, byte for byte. A real split gets a distinct, deterministic id per part
    ("-1", "-2", ...) truncated to fit Webull's documented 32-character max (see
    CLIENT_ORDER_ID_MAX) -- `base` is already <= 32 chars (_sanitize_client_order_id's
    own contract), so trimming a couple of characters off it to make room for the
    suffix still leaves it effectively unique (the base is either the caller's own
    short id or a sha1 hash -- losing its last 2-3 hex digits does not create
    collisions in practice)."""
    if total <= 1:
        return base
    suffix = f"-{index}"
    return base[:max(0, CLIENT_ORDER_ID_MAX - len(suffix))] + suffix


# ── THE ORDER PATH NEVER GUESSES (2026-09-26, WEBULL_PAPER_TODO item 17) ─────────────
# Each broker part is in state["order_parts"] (by its own id) BEFORE it is sent, with
# `booked` (shares the books count) and `pending` (Webull's answer not known). Only a
# 4xx is "never placed" without a lookup; unclear = PENDING, outcome "UNKNOWN". A live
# part counts in FULL; only FILLED or dead-with-filled-qty sets its shares exactly.
UNKNOWN_LOOKUP_TRIES = 3            # lookups after a send that raised ...
UNKNOWN_LOOKUP_WINDOW_SEC = 10.0    # ... spread over about this long
SPLIT_FILL_POLL_TRIES = 5           # part 1 of a split must report FILLED ...
SPLIT_FILL_POLL_WINDOW_SEC = 10.0   # ... within about this long, or part 2 is not sent
SEND_LOOKUP_BUDGET_SEC = 15.0       # past this, one send starts no lookup AND sends no
                                    # later split part (returned NOT_SENT): qqq_exec gives it
                                    # 40 s, a started lookup + one part send need ~25 s of it
RECONCILE_PENDING_LOOKUPS = 1       # PENDING parts looked up per reconcile() pass ...
RECONCILE_PENDING_BUDGET_SEC = 4.0  # ... none started after the pass has run this long
ORDER_PART_KEEP_SEC = 7 * 24 * 3600.0
DEAD_STATUSES = ("REJECTED", "CANCELLED", "CANCELED", "FAILED")
LIVE_STATUSES = ("PENDING", "SUBMITTED", "PARTIAL_FILLED")
# END-OF-DAY INTERNAL CROSS (2026-09-28 review): a leg with an order part younger than
# this that Webull has not yet reported terminal (part["final_status"]) is left out of
# cross_legs_internally -- its acked order may still die unfilled. Matches qqq_exec's
# BROKER_RECONCILE_POST_ORDER_GRACE_SEC.
CROSS_FRESH_PART_SEC = 30.0
_HTTP_STATUS_RE = re.compile(r"HTTP(?: Status:)?\s*(\d{3})")

# ── RESTING ORDERS AND THE ORDER GATEWAY (2026-09-29, owner GO via MANAGER) ─────────
# ORB #314's stop -- and, opt-in, its 5R target inside ONE native OCO -- rests at Webull on
# the ONE netted QQQ account every leg shares. The paper probe of 2026-09-29
# (tools/webull_resting_probe.py, WEBULL_PAPER_TODO item 19) showed a resting BUY stop makes
# Webull refuse a SHORT stop with 417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER: a resting order
# blocks other orders on the symbol exactly like a pending market order does, and a pending
# closing order reserves the shares it would sell. So nothing is ever planned next to one:
#   (a) CANCEL-FIRST: place_stock_order (PAPER/LIVE) cancels every live resting record on
#       the symbol and drives it to a terminal Webull status before planning (a fill found
#       is booked first); a record still unresolved -> NOT_SENT, outcome RESTING_UNRESOLVED.
#       An EARLIER session's record whose fill stays undecided holds back only its own
#       leg's CLOSE (_stale_undecided: a DAY order that old cannot be working).
#   (b) PREVIOUS ORDER TERMINAL (cfg["gateway"]["prev_terminal"], default off): no order is
#       planned while an earlier part on the symbol is acked but not yet FILLED or dead at
#       Webull (the 09-28 15:59:01 refusal); a bounded poll, then NOT_SENT "busy".
# Both share RESTING_GATEWAY_BUDGET_SEC, inside the send's own SEND_LOOKUP_BUDGET_SEC.
# A resting order is planned from the confirmed account net as ONE part (never crossing
# zero), recorded PENDING in state["resting"] (and as a booked-0 part in
# state["order_parts"]) before it is sent, and booked ONLY from Webull's own FILLED /
# partial / dead-with-filled record -- never on the ack. Fills are handed to the caller
# through take_resting_events(). Cancelling one OCO leg left its sibling live on paper, so
# a group is always cancelled leg by leg and every leg confirmed terminal; after any
# resting fill the rest of its group is cancelled the same way.
RESTING_GATEWAY_BUDGET_SEC = 8.0     # cancel-confirm + previous-order poll, per send
RESTING_CANCEL_TRIES = 6             # lookup rounds after a cancel, spread over the window
RESTING_NOT_FOUND_GRACE_SEC = 10.0   # a send never acked + "not found" this long, and absent
                                     # from get_order_open -> never placed (_settle_absent)
# STUCK-RECORD ESCAPE (2026-09-29 review): a live record whose lookups give no clear answer
# (errors, 429s, "not found" on an acked order, dead without a filled quantity) for this
# long and this many tries, AND that a successful get_order_open read does not list, is
# settled by ONE positions read (_absent_position_verdict) -- never by its absence alone:
# get_order_open never lists a FILLED order, so "not listed" cannot tell "filled" from
# "gone" (2026-09-29 second review, major: a filled stop booked 0 let ORB's engine close
# go out as a second, opening order). Webull's position equal to the books without the
# order's fill -> dead with what the books count (one escape event, and re-arming waits
# for a reconcile that finds it still absent); equal to the books WITH its fill -> booked
# FILLED (or the matching part) with an inferred price-less event; anything else ->
# UNDECIDED: the record stays live, so the gateway keeps every QQQ order (ORB's close
# included) back, and one high push goes out. Re-read at most every
# RESTING_ABSENT_RECHECK_SEC.
RESTING_ESCAPE_AFTER_SEC = 120.0
RESTING_ESCAPE_MIN_TRIES = 3
RESTING_ABSENT_RECHECK_SEC = 20.0
RESTING_BOOT_BUDGET_SEC = 10.0       # boot_sweep starts no lookup / poll after this long
RESTING_RECONCILE_LOOKUPS = 2        # resting lookups per reconcile() pass (one OCO group)
RESTING_KEEP_SEC = 3 * 24 * 3600.0
RESTING_DEAD_STATUSES = DEAD_STATUSES + ("EXPIRED",)
PREV_TERMINAL_PENDING_MAX_SEC = 120.0   # an UNKNOWN part older than this no longer blocks
# PREVIOUS ORDER STILL WORKING (2026-09-29 second review): for the resting-arm refusal and
# the prev_terminal gateway, an acked non-resting part with no terminal answer recorded
# counts as working for this long (qqq_exec's 10-minute OPEN re-send window), not only for
# the end-of-day cross's CROSS_FRESH_PART_SEC: a market order Webull is still working after
# 30 s must not have a stop planned next to it from a net that assumes its fill. Fill
# capture (apply_order_outcome) and the prev_terminal lookups record the terminal answer.
RESTING_PREV_WORKING_SEC = 600.0
# RECONCILE, UNDECIDED (2026-09-29 second review): a positions difference that a live
# resting order's own unbooked fill would explain, while that order had no clear lookup in
# this pass, is "look it up first" -- no halt -- at most this many reconciles in a row.
RECONCILE_UNDECIDED_MAX = 3
HTTP_TOO_MANY_REQUESTS = 429
OPEN_ORDERS_PAGE_SIZE = 50
OPEN_ORDERS_MAX_PAGES = 5
DEFAULT_GATEWAY = {"prev_terminal": False}
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
# A resting order's id (resting_ids: qx<tid>P<n> / T<n> / K<n>). No other id this book sends
# ends in P/T/K + digits: its OPEN / CLOSE ids end in O / C (+ a reduce number), a split
# part in "-<n>", and a hashed id is lower-case hex.
RESTING_ID_RE = re.compile(r"^qx[A-Za-z0-9]+[PTK][0-9]+$")
# the boot sweep's "listed only" ids are remembered this long (one push per id, not per restart)
BOOT_LISTED_KEEP_SEC = 3 * 24 * 3600.0


def resting_ids(trade_id, n):
    """(stop id, target id, combo id) for re-arm `n` of a trade: qx<tid>P<n>, qx<tid>T<n>,
    qx<tid>K<n> -- the trade id with its separators removed, as api/qqq_exec.py's
    _broker_signal_id builds qx<tid>O / qx<tid>C (26-27 characters for ORB). One that would
    not fit Webull's 32 falls back to a stable hash of the trade id. Letters and digits
    only, so _sanitize_client_order_id passes each through unchanged."""
    n = int(n)
    base = "qx" + _NON_ALNUM_RE.sub("", str(trade_id))
    room = CLIENT_ORDER_ID_MAX - 1 - len(str(n))
    if len(base) > room:
        base = "qx" + hashlib.sha1(str(trade_id).encode("utf-8")).hexdigest()[:room - 2]
    return tuple(f"{base}{code}{n}" for code in "PTK")


def plan_resting_side(net, direction, qty):
    """The ONE broker side a resting `direction`-qty order takes on account net `net`
    (_plan_broker_parts restricted to one part), or None when it would cross zero -- a
    resting order is never split (both parts would have to trigger together):
      SELL-direction: net >= qty -> SELL (closing); net <= 0 -> SHORT (opening); else None.
      BUY-direction:  net <= -qty -> BUY (closing); net >= 0 -> BUY (opening); else None."""
    parts = _plan_broker_parts(net, "BUY" if str(direction).upper() == "BUY" else "SELL", qty)
    return parts[0][0] if len(parts) == 1 else None


def _px_str(v):
    """A price as Webull's v3 string (cents)."""
    return f"{float(v):.2f}"


def _to_px(v):
    """A positive finite price, or None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def _not_found_error(e):
    """True when a lookup exception says Webull has no such order."""
    text = str(e).upper()
    return "NOT_FOUND" in text or "NOT_EXIST" in text


def _all_order_items(response):
    """Every per-order dict in a v3 response: one combo ({"orders": [...]}), a list of
    combos, or a {"data"/"list": [...]} page of them (get_order_open)."""
    r = _safe_response(response)
    out = []
    combos = []
    if isinstance(r, dict):
        if isinstance(r.get("orders"), list):
            combos.append(r)
        for k in ("data", "list", "items"):
            if isinstance(r.get(k), list):
                combos.extend(r[k])
    elif isinstance(r, list):
        combos.extend(r)
    for c in combos:
        if isinstance(c, dict):
            out.extend(_order_items(c) or [c])
    return out


def _sleep(sec):
    """The one wait in the order path (a seam, so tests never really wait)."""
    time.sleep(sec)


def _norm_status(v):
    """Webull status -> "PARTIAL_FILLED" style, or None."""
    if not isinstance(v, str) or not v.strip():
        return None
    return re.sub(r"[\s\-]+", "_", v.strip().upper())


def _to_qty(v):
    """A non-negative finite share count, or None (missing / unreadable)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f >= 0 else None


def _http_status(e):
    """The HTTP status a send exception carries (its http_status attribute, else "HTTP
    NNN" / "HTTP Status: NNN" in its text) as an int, or None. Put on the part record
    (p["http_status"]) so qqq_exec judges a 4xx exactly as the adapter did."""
    code = getattr(e, "http_status", None)
    if code is None:
        m = _HTTP_STATUS_RE.search(str(e))
        code = m.group(1) if m else None
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def _definite_refusal(e):
    """True only for Webull's own synchronous 4xx -- a 5xx or timeout may have landed."""
    code = _http_status(e)
    return code is not None and 400 <= code < 500


def _terminal_qty(qty, status, filled):
    """Shares a terminal answer says landed (qty if FILLED, `filled` if dead), else None."""
    return qty if status == "FILLED" else filled if status in DEAD_STATUSES else None


def _conclusive(ans):
    """A lookup answer that settles an unclear send."""
    return (ans["status"] == "FILLED" or ans["status"] in LIVE_STATUSES
            or (ans["status"] in DEAD_STATUSES and ans["filled"] is not None))


def _now_ny():
    return datetime.now(_NY) if _NY else datetime.utcnow()


def _load_state(path):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return d
    except Exception:
        pass
    return {"orders": {}, "believed_positions": {}, "open_legs": {}, "daily_pnl": 0.0,
            "instrument_ids": {}, "account_ids": {},
            # RECONCILE HARDENING (2026-09-14): orders that actually reached the
            # broker (PAPER/LIVE, ok=True) -- deliberately SEPARATE from
            # believed_positions, which also absorbs OFF-mode would-be orders (see
            # reconcile()'s docstring for why that distinction matters).
            "broker_sent_positions": {}, "last_reconcile_at": None,
            "last_reconcile_result": None}


def load_paper_keys(path=None):
    """PAPER credentials only -- NEVER reads/returns the live key file. Returns
    {app_key, app_secret} or None (missing file / unfilled template)."""
    path = path or DEFAULT_PAPER_KEYS
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    ak = (cfg.get("app_key") or "").strip()
    sk = (cfg.get("app_secret") or "").strip()
    if ak in _PLACEHOLDERS or sk in _PLACEHOLDERS:
        return None
    return {"app_key": ak, "app_secret": sk}


def load_live_keys(path=None):
    """Owner's existing LIVE key (same file/env var api/webull_sync.py already uses).
    Only ever consulted when mode=LIVE AND the arm file exists -- see effective_mode()."""
    path = path or DEFAULT_LIVE_KEYS
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    ak = (cfg.get("app_key") or "").strip()
    sk = (cfg.get("app_secret") or "").strip()
    if ak in _PLACEHOLDERS or sk in _PLACEHOLDERS:
        return None
    return {"app_key": ak, "app_secret": sk}


def load_config(path=None):
    """Order-adapter config: {"mode": "OFF"|"PAPER"|"LIVE", "rails": {...}, ...}.
    Missing file -> full defaults, i.e. mode OFF. A malformed file is treated the
    same as missing (never raises -- this must never be the reason a strategy dies)."""
    path = path or DEFAULT_CONFIG_PATH
    cfg = {
        "mode": MODE_OFF,
        "rails": dict(DEFAULT_RAILS),
        "account": dict(DEFAULT_ACCOUNT_SELECT),
        "paper_keys_path": DEFAULT_PAPER_KEYS,
        "paper_token_dir": DEFAULT_PAPER_TOKEN_DIR,
        "live_keys_path": DEFAULT_LIVE_KEYS,
        "live_token_dir": DEFAULT_LIVE_TOKEN_DIR,
        "arm_live_file": DEFAULT_ARM_LIVE_FILE,
        "kill_file": DEFAULT_KILL_FILE,
        "state_path": DEFAULT_STATE_PATH,
        "futures_enabled": False,
        "gateway": dict(DEFAULT_GATEWAY),
    }
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                if user.get("mode"):
                    cfg["mode"] = str(user["mode"]).upper()
                if isinstance(user.get("rails"), dict):
                    cfg["rails"].update(user["rails"])
                if isinstance(user.get("account"), dict):
                    cfg["account"].update(user["account"])
                if isinstance(user.get("gateway"), dict):
                    cfg["gateway"].update(user["gateway"])
                for k in ("paper_keys_path", "paper_token_dir", "live_keys_path",
                          "live_token_dir", "arm_live_file", "kill_file", "state_path"):
                    if user.get(k):
                        cfg[k] = user[k]
                cfg["futures_enabled"] = bool(user.get("futures_enabled", False))
        except Exception:
            pass
    return cfg


# ── the adapter ─────────────────────────────────────────────────────

class OrderAdapter:
    """One instance per process is plenty -- it's stateless aside from the JSON file
    at cfg["state_path"] (loaded on construction, written after every mutating call)
    and a lazily-built, cached SDK client per mode."""

    def __init__(self, config=None, config_path=None, log=print):
        self.log = log
        self.cfg = config or load_config(config_path)
        self._state = _load_state(self._state_path())
        self._clients = {}          # mode -> TradeClient (lazy, only PAPER/LIVE)
        self._account_id_cache = {}  # mode -> account_id
        self._last_order = None
        self._last_error = None
        self._halted = False
        self._halt_reason = None
        # HALT SOURCE (2026-09-14, reconcile hardening): which mechanism raised the
        # current halt -- "kill_file" or "reconcile". A periodic reconcile() that
        # later succeeds must be able to self-clear a halt IT caused (see
        # reconcile()'s recovery branch) WITHOUT ever silently clearing a kill-file
        # halt, which only a fresh state file (or the file's removal, on the next
        # rails check) may lift.
        self._halt_source = None
        # LOCK (2026-09-14, reconcile hardening): reconcile() is now also invoked
        # from api/qqq_exec.py wrapped in a hard wall-clock timeout on its own
        # worker thread (see that module's _reconcile_with_timeout, mirroring the
        # same "SDK timeouts aren't always honoured" precaution already used for
        # Webull quote calls) -- a slow/hung call can be ABANDONED by the caller
        # while still running here in the background. Every method that mutates
        # self._state (and therefore calls _save_state) takes this lock so that
        # orphaned call can never race a place_stock_order()/reconcile() happening
        # on the tick loop's own thread and corrupt state.json.
        self._lock = threading.RLock()
        # place_stock_order calls running now (any thread): place_resting refuses while one
        # is, since a send lets the lock go during its waits (RESTING ORDERS, 2026-09-29)
        self._stock_sends = 0
        self._sends_lock = threading.Lock()
        # prev_terminal switched on for this process by the caller (set_prev_terminal)
        self._prev_terminal_override = None
        # resting ids whose place_order is on the wire right now (the lock is let go for
        # it): "not found" on one of them is never read as "never placed"
        self._resting_sending = set()
        if os.path.exists(self._kill_file()):
            self._halted = True
            self._halt_reason = "kill file present at " + self._kill_file()
            self._halt_source = "kill_file"

    # -- config path accessors --
    def _state_path(self):
        return self.cfg.get("state_path") or DEFAULT_STATE_PATH

    def _kill_file(self):
        return self.cfg.get("kill_file") or DEFAULT_KILL_FILE

    def _arm_file(self):
        return self.cfg.get("arm_live_file") or DEFAULT_ARM_LIVE_FILE

    def _paper_keys_path(self):
        return self.cfg.get("paper_keys_path") or DEFAULT_PAPER_KEYS

    def _live_keys_path(self):
        return self.cfg.get("live_keys_path") or DEFAULT_LIVE_KEYS

    def _save_state(self):
        path = self._state_path()
        try:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f)
            os.replace(tmp, path)
        except Exception as e:
            self.log(f"  [webull-orders] state save failed (non-fatal): {type(e).__name__}: {e}")

    # -- mode resolution --
    def requested_mode(self):
        m = str(self.cfg.get("mode") or MODE_OFF).upper()
        return m if m in _VALID_MODES else MODE_OFF

    def effective_mode(self):
        """(mode, reason). Only ever returns PAPER when paper creds are present, and
        LIVE when BOTH mode==LIVE in config AND the arm file exists -- every other
        combination degrades to OFF, loudly, via `reason`."""
        requested = self.requested_mode()
        if requested == MODE_LIVE:
            arm = self._arm_file()
            if not os.path.exists(arm):
                return MODE_OFF, (f"LIVE requested but arm file missing ({arm}) -- "
                                   "the owner must create that file by hand to arm live "
                                   "orders. Refusing; behaving as OFF.")
            if not load_live_keys(self._live_keys_path()):
                return MODE_OFF, (f"LIVE requested and armed, but no live credentials at "
                                   f"{self._live_keys_path()}. Refusing; behaving as OFF.")
            return MODE_LIVE, f"LIVE armed via {arm}"
        if requested == MODE_PAPER:
            if not load_paper_keys(self._paper_keys_path()):
                return MODE_OFF, (f"PAPER requested but no paper credentials at "
                                   f"{self._paper_keys_path()}. Owner action: enable Paper "
                                   "Trading access in the Webull OpenAPI developer portal, "
                                   "generate a SEPARATE sandbox app key/secret (not the live "
                                   f"one), and save {{\"app_key\":...,\"app_secret\":...}} to "
                                   f"that path. No order will be sent until it exists.")
            return MODE_PAPER, "PAPER credentials present"
        return MODE_OFF, "mode=OFF (default)"

    # -- SDK client (PAPER/LIVE only; OFF never imports webull) --
    def _build_client(self, mode):
        from webull.core.client import ApiClient
        from webull.trade.trade_client import TradeClient
        from webull.core.common import api_type
        if mode == MODE_PAPER:
            keys = load_paper_keys(self._paper_keys_path())
            token_dir = self.cfg.get("paper_token_dir") or DEFAULT_PAPER_TOKEN_DIR
        elif mode == MODE_LIVE:
            keys = load_live_keys(self._live_keys_path())
            token_dir = self.cfg.get("live_token_dir") or DEFAULT_LIVE_TOKEN_DIR
        else:
            return None
        if not keys:
            return None
        api = ApiClient(keys["app_key"], keys["app_secret"], SANDBOX_REGION,
                         token_check_duration_seconds=15, token_check_interval_seconds=5,
                         connect_timeout=10, timeout=25)
        if mode == MODE_PAPER:
            # Override the "us" region's host with the sandbox host -- see the module
            # docstring's SANDBOX TARGETING section. LIVE deliberately does NOT call
            # add_endpoint(), so it resolves to the SDK's normal production host.
            api.add_endpoint(SANDBOX_REGION, SANDBOX_TRADE_HOST, api_type.DEFAULT)
            api.add_endpoint(SANDBOX_REGION, SANDBOX_EVENTS_HOST, api_type.EVENTS)
        try:
            os.makedirs(token_dir, exist_ok=True)
            api.set_token_dir(token_dir)
        except Exception:
            pass
        # Same log-suppression trick as api/webull_sync.py: avoid the SDK's default
        # file/stream logger (which can dump signed-request headers on error) and its
        # per-process log-rotation race across the runner's worker fleet.
        api._file_logger_set = True
        logging.getLogger("webull.core").addHandler(logging.NullHandler())
        return TradeClient(api)

    def _client(self, mode):
        if mode not in (MODE_PAPER, MODE_LIVE):
            return None
        if mode not in self._clients:
            self._clients[mode] = self._build_client(mode)
        return self._clients[mode]

    def _account_id(self, mode, client, purpose="stock"):
        """Resolve the account_id to trade `purpose` ("stock" or "futures" -- futures
        never actually reaches here, see DEFAULT_ACCOUNT_SELECT) through DELIBERATE
        selection (cfg["account"][purpose] or an explicit cfg["account"][purpose +
        "_last4"] override, default DEFAULT_ACCOUNT_SELECT -- see _account_selector_key)
        -- never "whichever account Webull listed first". See the DEFAULT_ACCOUNT_SELECT
        module comment for why that used to be wrong.

        Caching: an in-memory hit (this process, this adapter instance) is trusted with
        no re-verification -- the account roster cannot change mid-process. Anything
        else (first call, or a fresh adapter instance/process) ALWAYS calls
        get_account_list() live and re-selects under the CURRENTLY configured selector,
        so a stale disk-cached id can never win just by existing: a config change or an
        account reset (which renumbers accounts, as happened during the 2026-09-14
        smoke test) is picked up on the very next call, automatically -- there is no
        separate "has it changed" check to maintain, because the source of truth is
        always the live list. The disk cache is consulted ONLY as a last resort if that
        live call itself fails (network/SDK error), and only when its stored selector
        still matches _account_selector_key() NOW -- any change (a different class, or a
        last4 override added/changed/removed) means the id must not be resurrected
        silently. `_select_account` raises a clear RuntimeError (never falls back to the
        disk cache) when the configured selector is missing or ambiguous among live
        accounts -- that is a real configuration problem, not a transient fetch failure.
        """
        cache_key = f"{mode}:{purpose}"
        if cache_key in self._account_id_cache:
            return self._account_id_cache[cache_key]

        selector = _account_selector_key(purpose, self.cfg)

        try:
            accts = [a for a in _as_list(_safe_response(client.account_v2.get_account_list()))
                    if isinstance(a, dict)]
        except Exception as e:
            cached = (self._state.get("account_ids") or {}).get(cache_key)
            if isinstance(cached, dict) and cached.get("account_id") and cached.get("selector") == selector:
                self.log(f"  [webull-orders] get_account_list failed ({type(e).__name__}: {e}); "
                        f"using last-known {purpose} account_id from disk cache ({selector})")
                self._account_id_cache[cache_key] = cached["account_id"]
                return cached["account_id"]
            raise RuntimeError(f"get_account_list failed and no usable disk cache for "
                               f"purpose={purpose!r} ({selector}): {type(e).__name__}: {e}") from e

        if not accts:
            raise RuntimeError("get_account_list returned no accounts")

        chosen = _select_account(accts, purpose, self.cfg)
        aid = _field(chosen, "account_id", "accountId", "id")
        if not aid:
            raise RuntimeError("could not read account_id from the matched account")

        self._account_id_cache[cache_key] = aid
        self._state.setdefault("account_ids", {})[cache_key] = {
            "account_id": aid, "selector": selector,
        }
        self._save_state()
        return aid

    def _resolve_instrument_id(self, client, symbol, market="US"):
        cache = self._state.setdefault("instrument_ids", {})
        key = f"{market}:{symbol}"
        if key in cache:
            return cache[key]
        resp = client.trade_instrument.get_trade_security_detail(
            symbol=symbol, market=market, instrument_super_type="EQUITY",
            instrument_type=None, strike_price=None, init_exp_date=None)
        data = _safe_response(resp)
        candidates = [data] + _as_list(data)
        iid = None
        for c in candidates:
            iid = _field(c, "instrument_id", "instrumentId", "id")
            if iid:
                break
        if not iid:
            raise RuntimeError(f"could not resolve instrument_id for {symbol} ({market})")
        cache[key] = iid
        self._save_state()
        return iid

    # -- rails --
    def _in_session_window(self, rails):
        """[session_start, session_end) NY, to the second (2026-09-28): the end is
        EXCLUSIVE, so a "16:00" end refuses an OPEN from 16:00:00 -- it used to compare
        whole minutes inclusively and let one through until 16:00:59, after the bell,
        where Webull refuses a market order (or an OPEN it took would sit overnight). An
        end of "23:59" or later still means the whole day (test and all-day configs)."""
        start, end = rails.get("session_start"), rails.get("session_end")
        if not start or not end:
            return True
        now = _now_ny()
        if not (start <= now.strftime("%H:%M")):
            return False
        if str(end) >= "23:59":
            return True
        return now.strftime("%H:%M:%S") < (str(end) + ":00" if len(str(end)) == 5 else str(end))

    def _believed_total_shares(self):
        return sum(abs(p.get("qty", 0)) for p in (self._state.get("believed_positions") or {}).values())

    def _check_rails(self, leg, qty, intent, remainder=False):
        rails = self.cfg.get("rails") or DEFAULT_RAILS
        # CLOSE (flattening) is checked FIRST and unconditionally passes -- a halted
        # adapter (kill file, reconcile mismatch) must still be able to flatten,
        # never trap the strategy in a position it can no longer exit.
        if intent == "CLOSE":
            return True, "close intents are never blocked by the entry rails"
        if os.path.exists(self._kill_file()):
            self._halted = True
            self._halt_reason = "kill file present at " + self._kill_file()
            self._halt_source = "kill_file"
        if self._halted:
            return False, f"halted: {self._halt_reason}"
        max_shares = int(rails.get("max_shares_per_leg", 0) or 0)
        if max_shares and qty > max_shares:
            return False, f"qty {qty} exceeds max_shares_per_leg {max_shares}"
        max_total = int(rails.get("max_total_position_shares", 0) or 0)
        if max_total:
            projected = self._believed_total_shares() + qty
            if projected > max_total:
                return False, f"projected total position {projected} exceeds max_total_position_shares {max_total}"
        limit = float(rails.get("daily_loss_limit_usd", 0) or 0)
        if limit and self._state.get("daily_pnl", 0.0) <= -abs(limit):
            return False, f"daily loss limit hit ({self._state.get('daily_pnl', 0.0):.2f} <= -{limit})"
        if not self._in_session_window(rails):
            return False, f"outside session window {rails.get('session_start')}-{rails.get('session_end')} NY"
        # `remainder`: the rest of this leg's OWN split OPEN (its part 1 opened the leg)
        if (rails.get("one_open_position_per_leg", True) and not remainder
                and leg in (self._state.get("open_legs") or {})):
            return False, f"leg {leg!r} already has an open position (one_open_position_per_leg)"
        return True, "rails ok"

    def _apply_intent_to_belief(self, leg, symbol, side, qty, intent):
        positions = self._state.setdefault("believed_positions", {})
        open_legs = self._state.setdefault("open_legs", {})
        signed = qty if side == "BUY" else -qty  # SELL and SHORT both reduce/short
        cur = positions.get(leg, {"symbol": symbol, "qty": 0})
        cur["qty"] = cur.get("qty", 0) + signed
        cur["symbol"] = symbol
        positions[leg] = cur
        if intent == "OPEN":
            open_legs[leg] = True
        elif abs(cur["qty"]) < 1e-9:
            open_legs.pop(leg, None)
        self._save_state()

    def _apply_intent_to_sent(self, leg, symbol, side, qty, account_id, intent):
        """Tracks ONLY orders that actually reached the broker with a successful ack.
        Called once per ACCEPTED broker part (ORDER NETTING, 2026-09-24 -- see
        place_stock_order and _plan_broker_parts) with that part's own side/qty, so a
        leg event split into several broker orders moves this book by exactly the
        parts that were accepted, never the whole requested qty when one part was
        refused. `side` here is the part's REAL broker-facing side (SELL/SHORT/BUY),
        which is why the sign below is exactly right even when it differs from the
        leg's own literal request. Kept as a SEPARATE dict from believed_positions
        (which also absorbs OFF-mode would-be orders, in one shot, from the leg's own
        requested qty) because both reconcile() and _account_net()'s own netting math
        must compare against what this adapter actually SENT the broker, not a belief
        that includes phantom OFF-mode fills -- comparing against believed_positions
        would false-positive the moment the config flips from OFF to PAPER/LIVE with
        any OFF-era belief still on the books. See reconcile()'s own docstring."""
        positions = self._state.setdefault("broker_sent_positions", {})
        signed = qty if side == "BUY" else -qty  # SELL and SHORT both reduce/short
        cur = positions.get(leg, {"symbol": symbol, "qty": 0, "account_id": account_id})
        cur["qty"] = cur.get("qty", 0) + signed
        cur["symbol"] = symbol
        cur["account_id"] = account_id
        positions[leg] = cur
        self._save_state()

    def apply_unacked_close_fill(self, leg, qty, lock_timeout=1.0, part_outcomes=None):
        """Books `qty` shares of a CLOSE for `leg` that FILLED at Webull even though the
        send itself came back not ok (a timeout, a dropped connection, a 5xx) -- the
        caller (api/qqq_exec.py's close re-send, FINAL CLOSE RE-SEND RULE 2026-09-26)
        learned it from Webull's own order record by id. place_stock_order never moves
        broker_sent_positions/believed_positions on that not-ok path, so without this
        the adapter would keep believing the leg holds shares already sold (false
        reconcile halts, a blocked next entry, phantom shares offered to a FLATTEN_BROKER
        orphan repair).

        Moves BOTH books for `leg` toward zero by `qty`, never past zero (a CLOSE can
        only shrink the leg; the netted account side is irrelevant to this leg's own
        book), and drops the leg from open_legs once its believed qty reaches zero.
        Takes the adapter lock with a bounded wait (a hung send holds it) -- returns None
        without touching anything when the lock is not free in time. Otherwise returns
        {"sent": n, "believed": m}, the shares actually taken off each book. Never
        raises.

        `part_outcomes` (2026-09-26): {order id: {"status", "filled"}} Webull verified.
        When every id is a recorded part, each is set EXACTLY to what landed (_book_part)
        instead of `qty`, so shares already booked are never taken off twice."""
        try:
            qty = abs(float(qty or 0))
        except (TypeError, ValueError):
            return None
        if qty <= 0 and not part_outcomes:
            return {"sent": 0, "believed": 0}
        if not self._lock.acquire(timeout=lock_timeout):
            return None
        try:
            outs = {_sanitize_client_order_id(c): v for c, v in (part_outcomes or {}).items() if c}
            parts = self._state.get("order_parts") or {}
            if outs and all(c in parts for c in outs):
                took = 0
                for c, v in outs.items():
                    filled = (parts[c]["qty"] if _norm_status((v or {}).get("status")) == "FILLED"
                              else _to_qty((v or {}).get("filled")))
                    if filled is not None:
                        took += self._book_part(c, filled, pending=False)
                return {"sent": took, "believed": took}
            if qty <= 0:
                return {"sent": 0, "believed": 0}
            applied = {}
            for book in ("broker_sent_positions", "believed_positions"):
                cur = (self._state.get(book) or {}).get(leg)
                held = float((cur or {}).get("qty", 0) or 0)
                take = min(qty, abs(held))
                if cur is not None and take > 0:
                    cur["qty"] = held - take if held > 0 else held + take
                applied["sent" if book == "broker_sent_positions" else "believed"] = take
            believed = (self._state.get("believed_positions") or {}).get(leg) or {}
            if abs(float(believed.get("qty", 0) or 0)) < 1e-9:
                (self._state.get("open_legs") or {}).pop(leg, None)
            self._save_state()
            return applied
        except Exception:
            return None
        finally:
            self._lock.release()

    # -- END-OF-DAY INTERNAL CROSS (2026-09-28) ------------------------------------------
    def cross_legs_internally(self, symbol, legs, lock_timeout=2.0,
                              fresh_part_sec=CROSS_FRESH_PART_SEC, trade_ids=None):
        """Offset opposite legs' shares against each other in the books, sending NOTHING.

        WHY (09-28 15:59:01, box qqq_exec.log). The end-of-day flatten closed ORB short 10
        and ENGUQ long 10 with one market order each, back to back. The account was flat
        at Webull all along (-10 + 10), so the right number of orders was zero. ORB's BUY
        10 went out first -- a buy-OPENING order on a flat account -- and was booked in
        full on its ack, so ENGUQ's SELL 10 was planned as a closing sell on a +10
        account; at Webull the buy was still pending on a flat account, the sell was a
        sell-OPENING order, and Webull refused it: 417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER (a
        pending buy-opening and a pending sell-opening order may not coexist on one
        symbol). close_retry re-sent it 5 s later, and the pair paid two spreads for no
        change in the account.

        Crossing first removes that class: every share one leg holds long against
        another leg's short is already flat at Webull, so both legs' broker books move
        toward zero by the crossed amount with no order at all. What is left is on ONE
        side of the account only (every remaining leg holds the side of the account's own
        net), so each remaining per-leg close is a plain closing order that can never
        cross zero, never split and never open anything -- no box-order refusal, whatever
        order they go out in and whether or not the earlier one has filled yet.

        `legs`: {leg: +1 | -1}, the side the caller's book holds for each leg it is about
        to close (long +1, short -1). Only legs that are really closing NOW: a lot held
        overnight (api/qqq_exec.py HOLD OVERNIGHT, 2026-10-09) is never passed at the
        flat_by flatten -- crossing a closing leg against it would close the held lot in
        these books with no order behind it. Its shares stay in broker_sent_positions
        (no daily reset), so the next morning's netting sees them through _account_net. A leg takes part only when broker_sent_positions
        holds shares for it on that same side, for `symbol`, it has no PENDING order part
        (its real position is not known yet -- it keeps its own verify-gated path), no
        order part younger than `fresh_part_sec` that Webull has not reported terminal
        (2026-09-28 review: an acked market order is booked in full before it fills, and
        one that then dies unfilled would leave crossed shares with no order behind them
        -- a KILL or BREAKER flatten seconds after a fresh entry), and its account id
        matches the others'. Legs are paired in name order, longs against
        shorts. broker_sent_positions and believed_positions move by exactly the crossed
        shares (their account-wide sums, which reconcile() compares with Webull, do not
        change), open_legs drops a leg whose belief reaches zero, and the cross is logged
        under state["internal_crosses"] -- with `trade_ids` ({leg: the caller's trade id},
        optional) on the record, so a caller that crashed before saving its own books can
        recognise the cross on a re-run (recent_internal_crosses).

        Returns {"crossed": {leg: shares}, "left": {leg: signed qty still held},
        "id": str} (crossed empty when nothing offsets), or None when the mode is not
        PAPER/LIVE or the lock is busy -- the caller then closes each leg as before.
        Never raises."""
        try:
            mode, _ = self.effective_mode()
            if mode not in (MODE_PAPER, MODE_LIVE):
                return None
            if not self._lock.acquire(timeout=lock_timeout):
                return None
        except Exception:
            return None
        try:
            want_symbol = str(symbol).upper()
            sent = self._state.get("broker_sent_positions") or {}
            pending_legs = {p.get("leg") for _, p in self._unsettled_parts(fresh_sec=fresh_part_sec)}
            # RESTING ORDERS (2026-09-29): a leg with a live resting order keeps its own
            # path -- its close goes through place_stock_order's cancel-first gateway, so
            # the resting order can never outlive the shares it protects.
            pending_legs |= {r.get("leg") for r in self._resting().values() if r.get("live")}
            eligible, account = {}, None
            for leg in sorted(legs or {}):
                sign = 1 if (legs[leg] or 0) > 0 else -1
                p = sent.get(leg)
                if not isinstance(p, dict) or str(p.get("symbol", "")).upper() != want_symbol:
                    continue
                qty = int(round(float(p.get("qty", 0) or 0)))
                if qty == 0 or (qty > 0) != (sign > 0) or leg in pending_legs:
                    continue
                acct = p.get("account_id")
                if acct is not None:
                    if account is None:
                        account = acct
                    elif acct != account:
                        continue
                eligible[leg] = qty
            longs = [[leg, q] for leg, q in eligible.items() if q > 0]
            shorts = [[leg, -q] for leg, q in eligible.items() if q < 0]
            crossed = {}
            i = j = 0
            while i < len(longs) and j < len(shorts):
                n = min(longs[i][1], shorts[j][1])
                crossed[longs[i][0]] = crossed.get(longs[i][0], 0) + n
                crossed[shorts[j][0]] = crossed.get(shorts[j][0], 0) + n
                longs[i][1] -= n
                shorts[j][1] -= n
                if longs[i][1] == 0:
                    i += 1
                if shorts[j][1] == 0:
                    j += 1
            cross_id = f"X{int(time.time() * 1000)}"
            left = {}
            for leg, n in crossed.items():
                sign = 1 if eligible[leg] > 0 else -1
                for book in ("broker_sent_positions", "believed_positions"):
                    cur = (self._state.get(book) or {}).get(leg)
                    if not isinstance(cur, dict):
                        continue
                    held = float(cur.get("qty", 0) or 0)
                    take = min(float(n), abs(held)) if (held > 0) == (sign > 0) else 0.0
                    cur["qty"] = held - take * sign
                left[leg] = float(sent[leg].get("qty", 0) or 0)
                believed = (self._state.get("believed_positions") or {}).get(leg) or {}
                if abs(float(believed.get("qty", 0) or 0)) < 1e-9:
                    (self._state.get("open_legs") or {}).pop(leg, None)
            if crossed:
                log_rows = self._state.setdefault("internal_crosses", [])
                log_rows.append({"id": cross_id, "ts": time.time(), "symbol": want_symbol,
                                 "account_id": account,
                                 "legs": {leg: (n if eligible[leg] > 0 else -n)
                                          for leg, n in crossed.items()},
                                 "trade_ids": {leg: str((trade_ids or {}).get(leg) or "")
                                               for leg in crossed}})
                del log_rows[:-20]
                self._save_state()
                self.log(f"  [webull-orders] INTERNAL CROSS {cross_id} {want_symbol}: " + ", ".join(
                    f"{leg} {'long' if eligible[leg] > 0 else 'short'} {n}"
                    for leg, n in sorted(crossed.items()))
                    + " -- already flat against each other at the broker, no order sent")
            return {"crossed": crossed, "left": left, "id": cross_id}
        except Exception as e:
            self.log(f"  [webull-orders] internal cross failed (legs close one by one): "
                     f"{type(e).__name__}: {e}")
            return None
        finally:
            self._lock.release()

    def recent_internal_crosses(self, max_age_sec=600.0, lock_timeout=1.0):
        """Copies of the internal_crosses records (newest last) no older than
        `max_age_sec`, with each leg's broker qty now ("sent_now": {leg: signed qty}).
        [] when there are none or the lock is busy. Never raises."""
        try:
            if not self._lock.acquire(timeout=lock_timeout):
                return []
        except Exception:
            return []
        try:
            cutoff = time.time() - float(max_age_sec)
            sent = self._state.get("broker_sent_positions") or {}
            out = []
            for rec in self._state.get("internal_crosses") or []:
                if not isinstance(rec, dict) or float(rec.get("ts") or 0) < cutoff:
                    continue
                copy = json.loads(json.dumps(rec))
                copy["sent_now"] = {leg: float((sent.get(leg) or {}).get("qty", 0) or 0)
                                    for leg in (rec.get("legs") or {})}
                out.append(copy)
            return out
        except Exception:
            return []
        finally:
            self._lock.release()

    # -- THE ORDER PATH NEVER GUESSES (see the module comment above UNKNOWN_LOOKUP_TRIES) --
    def _parts(self):
        return self._state.setdefault("order_parts", {})

    def _prune_parts(self):
        cutoff = time.time() - ORDER_PART_KEEP_SEC
        parts = self._parts()
        for coid in [c for c, p in parts.items() if float(p.get("ts") or 0) < cutoff]:
            parts.pop(coid, None)

    def _unsettled_parts(self, symbol=None, fresh_sec=CROSS_FRESH_PART_SEC,
                         pending_max_age=None, acked_only=False):
        """[(coid, part)] for the order parts Webull may still be working: PENDING (outcome
        not known; only while younger than `pending_max_age` when given), or younger than
        `fresh_sec` with no terminal answer recorded (an acked market order is booked in
        full before it fills). Resting parts are left out -- they have their own records
        and the cancel-first gateway. `symbol` narrows it to one symbol. `acked_only` (the
        resting callers, with their 10-minute window) also leaves out a part Webull refused
        outright (a 4xx: not pending, nothing booked, no terminal answer) -- it never
        reached Webull's book. The ONE test both cross_legs_internally and the
        previous-order-terminal gateway use. Caller holds the lock."""
        now_ts = time.time()
        want = str(symbol).upper() if symbol else None
        out = []
        for coid, p in (self._state.get("order_parts") or {}).items():
            if not isinstance(p, dict) or p.get("resting"):
                continue
            if want and str(p.get("symbol", "")).upper() != want:
                continue
            if (acked_only and not p.get("pending") and not p.get("final_status")
                    and not int(p.get("booked") or 0)):
                continue
            age = now_ts - float(p.get("ts") or 0)
            if ((p.get("pending") and (pending_max_age is None or age < pending_max_age))
                    or (not p.get("final_status") and age < fresh_sec)):
                out.append((coid, p))
        return out

    def _mark_final(self, coid, status):
        """Record Webull's TERMINAL answer (FILLED or dead) on part `coid` -- what
        cross_legs_internally trusts for a fresh part. Caller holds the lock."""
        part = self._parts().get(coid)
        if part is not None and status:
            part["final_status"] = status

    def _book_part(self, coid, target, pending=None):
        """Make the books count exactly `target` (0..qty) shares of part `coid`; returns
        the change. Idempotent. Caller holds the lock."""
        part = self._parts().get(coid)
        if not part:
            return 0
        target = max(0, min(int(round(target)), int(part["qty"])))
        delta = target - int(part.get("booked") or 0)
        if delta:
            leg, symbol = part["leg"], part["symbol"]
            signed = delta if part["side"] == "BUY" else -delta
            for book in ("believed_positions", "broker_sent_positions"):
                cur = self._state.setdefault(book, {}).setdefault(leg, {"symbol": symbol, "qty": 0})
                cur["qty"] = cur.get("qty", 0) + signed
                cur["symbol"] = symbol
                if book == "broker_sent_positions" and part.get("account_id"):
                    cur["account_id"] = part["account_id"]
            open_legs = self._state.setdefault("open_legs", {})
            if abs(self._state["believed_positions"][leg]["qty"]) > 1e-9:
                open_legs[leg] = True
            else:
                open_legs.pop(leg, None)
            part["booked"] = target
        if pending is not None:
            part["pending"] = pending
        self._save_state()
        return delta

    def _lookup_order(self, client, account_id, coid, detail=False):
        """Webull's record of one order -> {"status", "filled"}, or None when there is no
        clear answer. Never raises. `detail` (resting orders) adds "price" (filled_price)
        and "stop_price", and reads a "no such order" error as status NOT_FOUND."""
        try:
            resp = _safe_response(client.order_v3.get_order_detail(account_id, coid))
            item = _order_item(resp, coid)
            item_coid = _field(item, "client_order_id", "clientOrderId")
            if item_coid is not None and str(item_coid) != str(coid):
                return None
            fields = order_status_fields(resp, coid)
            status = _norm_status(fields.get("status"))
            if not status:
                return None
            out = {"status": status, "filled": _to_qty(fields.get("filled_quantity"))}
            if detail:
                out["price"] = _to_px(fields.get("filled_price"))
                out["stop_price"] = _to_px(_field(item, "stop_price", "stopPrice"))
            return out
        except Exception as e:
            if detail and _not_found_error(e):
                return {"status": "NOT_FOUND", "filled": None, "price": None, "stop_price": None}
            return None

    def _poll_order(self, client, account_id, coid, tries, window_sec, done, stop_at=None,
                    detail=False):
        """Up to `tries` lookups over about `window_sec`: the first answer `done` accepts,
        else the last one seen (or None). None started after `stop_at`. The adapter
        lock (held by the send) is let go for each wait + lookup, so a slow wait never
        blocks reconcile/status/fill capture; the part is on disk and the signal cached
        UNKNOWN first, and every booking after it is exact (_book_part)."""
        deadline = time.time() + window_sec
        last = None
        for i in range(max(1, tries)):
            if i and time.time() >= deadline:
                break
            wait = window_sec / max(1, tries) if i else 0.0
            if stop_at is not None and time.time() + wait >= stop_at:
                break   # the lookup would start past the send's budget
            try:
                self._lock.release()
                released = True
            except RuntimeError:
                released = False   # not held (a direct call): nothing to let go
            try:
                if wait:
                    _sleep(wait)
                ans = self._lookup_order(client, account_id, coid, detail=detail)
            finally:
                if released:
                    self._lock.acquire()
            if ans is not None:
                last = ans
                if done(ans):
                    return ans
        return last

    def _send_part(self, client, account_id, mode, leg, symbol, intent, side, qty,
                   part_coid, new_order, label, stop_at=None):
        """Send ONE broker part (PENDING on disk first). On an exception a 4xx is a
        refusal; else look it up: FILLED/live = sent, dead books its filled qty, unclear
        stays PENDING with outcome "UNKNOWN". Caller holds the lock."""
        self._parts()[part_coid] = {"leg": leg, "symbol": symbol, "side": side,
                                    "qty": int(qty), "intent": intent,
                                    "account_id": account_id, "ts": time.time(),
                                    "booked": 0, "pending": True}
        self._save_state()
        rec = {"side": side, "qty": qty, "client_order_id": part_coid, "sent": True,
               "response": None}
        try:
            resp = client.order_v3.place_order(account_id, [new_order])
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            self.log(f"  [webull-orders] {mode} place_order FAILED for {symbol} {side} {qty} "
                     f"(leg {leg}{label}): {reason}")
            rec["http_status"] = _http_status(e)
            if _definite_refusal(e):
                self._parts()[part_coid]["pending"] = False
                self._save_state()
                rec.update(ok=False, reason=reason)
                return rec
            ans = self._poll_order(client, account_id, part_coid, UNKNOWN_LOOKUP_TRIES,
                                   UNKNOWN_LOOKUP_WINDOW_SEC, _conclusive, stop_at=stop_at)
            st = ans["status"] if ans else None
            if st == "FILLED" or (st in DEAD_STATUSES and ans["filled"] is not None):
                self._mark_final(part_coid, st)
            if st == "FILLED" or st in LIVE_STATUSES:
                self._book_part(part_coid, qty, pending=False)
                rec.update(ok=True, resolved_by_lookup=st,
                           reason=f"send raised ({reason}) but Webull's own record shows it {st}")
            elif st in DEAD_STATUSES and ans["filled"] is not None:
                self._book_part(part_coid, ans["filled"], pending=False)
                rec.update(ok=False, outcome=st, filled=ans["filled"],
                           reason=f"{reason}; Webull's own record shows it {st} "
                                  f"({ans['filled']:g} of {qty} filled)")
            else:
                rec.update(ok=False, outcome="UNKNOWN",
                           reason=f"{reason}; Webull's own record could not confirm it "
                                  f"(status {st or 'unreadable'}) -- outcome UNKNOWN, kept PENDING")
            self.log(f"  [webull-orders] {part_coid} after lookup: {rec['reason']}")
            return rec
        self._apply_intent_to_belief(leg, symbol, side, qty, intent)
        self._apply_intent_to_sent(leg, symbol, side, qty, account_id, intent)
        self._parts()[part_coid].update(booked=int(qty), pending=False)
        try:
            if _norm_status(order_status_fields(_safe_response(resp), part_coid)
                            .get("status")) == "FILLED":
                self._mark_final(part_coid, "FILLED")
        except Exception:
            pass
        self._save_state()
        rec.update(ok=True, reason="", response=_safe_response(resp))
        return rec

    def _part_filled(self, client, account_id, prev, stop_at=None):
        """SPLIT SEQUENCING: True only once part `prev` reports FILLED (ack, lookup or a
        bounded poll). Dead: rolled back to what filled. Still working / no answer: kept
        in full, PENDING, and `prev` marked ok=False outcome "WORKING" so qqq_exec
        verifies it before any re-send. Caller holds the lock. Never raises."""
        try:
            if not prev.get("ok"):
                return False
            coid = prev["client_order_id"]
            ack = _norm_status(order_status_fields(prev.get("response"), coid).get("status"))
            if "FILLED" in (ack, prev.get("resolved_by_lookup")):
                self._mark_final(coid, "FILLED")
                return True
            ans = self._poll_order(client, account_id, coid, SPLIT_FILL_POLL_TRIES,
                                   SPLIT_FILL_POLL_WINDOW_SEC,
                                   lambda a: a["status"] == "FILLED" or a["status"] in DEAD_STATUSES,
                                   stop_at=stop_at)
            st = ans["status"] if ans else None
            if st == "FILLED":
                self._mark_final(coid, "FILLED")
                return True
            if st in DEAD_STATUSES and ans["filled"] is not None:
                self._mark_final(coid, st)
                self._book_part(coid, ans["filled"], pending=False)
                prev.update(ok=False, outcome=st, filled=ans["filled"],
                            reason=f"{st} at Webull ({ans['filled']:g} of {prev['qty']} "
                                   f"filled) -- books rolled back to the filled shares")
            else:
                self._parts()[coid]["pending"] = True
                self._save_state()
                prev.update(ok=False, outcome="WORKING",
                            reason=f"acked but not confirmed FILLED (status "
                                   f"{st or 'unreadable'}) -- still counted in full, pending")
            return False
        except Exception as e:
            self.log(f"  [webull-orders] split part check failed: {type(e).__name__}: {e}")
            return False

    def apply_order_outcome(self, signal_id, status, filled_quantity=None, lock_timeout=1.0):
        """Fill capture's hook: FILLED books the whole part, dead with a filled qty just
        that; anything else changes nothing. None when the books did not move,
        {"deferred": True} when the lock is busy, else {"leg", "intent", "status",
        "qty", "filled", "change" (< 0: shares that did not go through), "final"}."""
        try:
            coid = _sanitize_client_order_id(signal_id)
            st, filled = _norm_status(status), _to_qty(filled_quantity)
            if not self._lock.acquire(timeout=lock_timeout):
                return {"deferred": True}
            try:
                part = self._parts().get(coid)
                if part and part.get("resting"):
                    return None   # resting parts settle through their own records (_settle_resting)
                target = _terminal_qty(part["qty"], st, filled) if part else None
                if target is None:
                    if part and st in DEAD_STATUSES:
                        part["pending"] = True
                        self._save_state()
                    return None
                self._mark_final(coid, st)
                change = self._book_part(coid, target, pending=False)
                if not change:
                    return None
                self.log(f"  [webull-orders] {coid} ({part['leg']}) is {st} at Webull: books "
                         f"now count {part['booked']} of {part['qty']} share(s)")
                return {"leg": part["leg"], "intent": part.get("intent"), "status": st,
                        "qty": part["qty"], "filled": part["booked"], "change": change,
                        "final": True}
            finally:
                self._lock.release()
        except Exception:
            return None

    def _resolve_pending(self, client):
        """reconcile()'s PENDING pass (bounded count and time): FILLED or dead with a
        filled qty settles a part; anything else keeps it pending. Each book change is
        queued for take_part_events() so qqq_exec can push it. Never raises."""
        try:
            started = time.time()
            with self._lock:
                self._prune_parts()
                todo = sorted((float(p.get("checked_at") or 0), c, p.get("account_id"))
                              for c, p in self._parts().items() if p.get("pending"))
            for _, coid, acct in todo[:RECONCILE_PENDING_LOOKUPS]:
                if time.time() - started >= RECONCILE_PENDING_BUDGET_SEC:
                    break
                ans = self._lookup_order(client, acct, coid)
                with self._lock:
                    part = self._parts().get(coid)
                    if not part or not part.get("pending"):
                        continue
                    part["checked_at"] = time.time()
                    st = ans["status"] if ans else None
                    target = _terminal_qty(part["qty"], st, ans["filled"]) if ans else None
                    if target is not None:
                        self._mark_final(coid, st)
                    change = 0 if target is None else self._book_part(coid, target, pending=False)
                    if change:
                        self._state.setdefault("part_events", []).append(
                            {"client_order_id": coid, "leg": part["leg"],
                             "intent": part.get("intent"), "status": st, "qty": part["qty"],
                             "booked": part["booked"], "change": change})
                    self._save_state()
                    self.log(f"  [webull-orders] PENDING {coid} ({part['leg']}): "
                             f"{st or 'no clear answer'} -> books count {part['booked']} of "
                             f"{part['qty']}" + (", still pending" if part["pending"] else ""))
        except Exception as e:
            self.log(f"  [webull-orders] PENDING pass failed: {type(e).__name__}: {e}")

    def take_part_events(self, lock_timeout=1.0):
        """Hand over (and clear) _resolve_pending's book changes; [] if none or busy."""
        if not self._lock.acquire(timeout=lock_timeout):
            return []
        try:
            events = self._state.pop("part_events", None) or []
            if events:
                self._save_state()
            return events
        finally:
            self._lock.release()

    def booked_shares(self, client_order_ids):
        """Shares of these recorded parts the books count now (0 on any problem)."""
        try:
            parts = self._state.get("order_parts") or {}
            return sum(int((parts.get(_sanitize_client_order_id(c)) or {}).get("booked") or 0)
                       for c in client_order_ids or [] if c)
        except Exception:
            return 0

    def _account_net(self, symbol, account_id=None):
        """The account-level net position Webull actually holds (as far as this
        adapter's own record of what reached the broker goes) for `symbol` RIGHT NOW --
        the sum of every leg's broker_sent_positions qty for that symbol. This is what
        ORDER NETTING plans against (_plan_broker_parts): Webull has exactly one
        position per symbol shared by every leg trading it, so no single leg's own
        belief means anything to the broker -- only this sum is real, mirroring
        reconcile()'s own `sent` computation (broker_sent_positions, never
        believed_positions -- see _apply_intent_to_sent's docstring for why).

        `account_id`, when given, restricts the sum to lots sent under that SAME
        account (a lot recorded under a different one -- e.g. a stale entry from
        before an account reset -- must never be netted against a different account's
        real position), the same per-account discipline reconcile() already applies to
        this same dict."""
        sent = self._state.get("broker_sent_positions") or {}
        total = 0.0
        want_symbol = str(symbol).upper()
        for p in sent.values():
            if not isinstance(p, dict):
                continue
            if str(p.get("symbol", "")).upper() != want_symbol:
                continue
            if account_id is not None and p.get("account_id") not in (None, account_id):
                continue
            total += float(p.get("qty", 0) or 0)
        return total

    def update_daily_pnl(self, delta):
        """Caller (the strategy / a fills sync) reports realized+open P&L deltas here
        so the daily_loss_limit_usd rail has something to check against. This adapter
        does not sync fills itself."""
        with self._lock:
            self._state["daily_pnl"] = self._state.get("daily_pnl", 0.0) + float(delta)
            self._save_state()

    def reset_daily_pnl(self):
        with self._lock:
            self._state["daily_pnl"] = 0.0
            self._save_state()

    def _record_order(self, coid, record):
        self._state.setdefault("orders", {})[coid] = record
        self._save_state()

    # -- RESTING ORDERS AND THE ORDER GATEWAY (2026-09-29) -- see the module comment ------
    # state["resting"]: {client_order_id: record}, one record per leg of a group (a stop
    # alone, or the stop + target legs of one OCO), each also a booked-0 part in
    # state["order_parts"] (resting=True) so a fill moves the books through _book_part:
    #   leg, trade_id, symbol, kind ("stop" | "target"), group (the stop id, or the OCO's
    #   combo id), combo_id, n, side (as sent), qty, order_type, stop_price, limit_price,
    #   account_id, status, live (Webull may still fill it), pending (the send's answer is
    #   not known), acked, booked (shares the books count), filled_price, placed_at,
    #   checked_at, cancel_due, cancel_sent_at, final_status, settled_at.
    # Nothing here runs, and no key is written, until the first place_resting.
    def _resting(self):
        return self._state.get("resting") or {}

    def _prev_terminal_on(self):
        if self._prev_terminal_override is not None:
            return self._prev_terminal_override
        return bool((self.cfg.get("gateway") or {}).get("prev_terminal"))

    def set_prev_terminal(self, on):
        """Switch the previous-order-terminal gateway rule on (True) or off (False) for
        this adapter, whatever cfg["gateway"] says; None goes back to the config."""
        self._prev_terminal_override = None if on is None else bool(on)

    def _live_resting(self, symbol=None):
        want = str(symbol).upper() if symbol else None
        return [c for c, r in self._resting().items()
                if r.get("live") and (want is None or r.get("symbol") == want)]

    def _group_ids(self, coids):
        """Every record id in the groups `coids` belong to (both legs of an OCO)."""
        rest = self._resting()
        groups = {rest[c].get("group") for c in coids if c in rest}
        return [c for c, r in rest.items() if r.get("group") in groups]

    @contextlib.contextmanager
    def _lock_released(self):
        """Let the adapter lock go for a wait or a lookup (as _poll_order does)."""
        try:
            self._lock.release()
            released = True
        except RuntimeError:
            released = False   # not held (a direct call): nothing to let go
        try:
            yield
        finally:
            if released:
                self._lock.acquire()

    @staticmethod
    def _placed_day(rec):
        """The NY date the record was placed on, or None."""
        try:
            ts = float(rec.get("placed_at") or 0)
            return (datetime.fromtimestamp(ts, _NY) if _NY else datetime.utcfromtimestamp(ts)).date()
        except Exception:
            return None

    @classmethod
    def _session_over(cls, rec):
        """True once the NY session the record was placed in has closed
        (market_calendar.session_close_et: 16:00, 13:00 on a half day), when a DAY order
        reading CANCELLED/EXPIRED with no filled quantity is dead with 0."""
        now = _now_ny()
        placed = cls._placed_day(rec)
        if placed is not None and placed < now.date():
            return True
        try:
            close = market_calendar.session_close_et(now.date())
        except Exception:
            close = "16:00"
        return now.strftime("%H:%M") >= close

    @staticmethod
    def _note_unclear(rec, now, answer):
        """A lookup with no clear answer: counted toward the stuck-record escape."""
        rec["last_answer"] = answer or "no answer"
        rec.setdefault("unclear_since", now)
        rec["unclear_n"] = int(rec.get("unclear_n") or 0) + 1

    def _queue_escape(self, coid, rec, status, reason, source):
        """One resting event for a record settled WITHOUT Webull's own terminal record (a
        previous session's DAY order Webull no longer finds, or one absent from
        get_order_open after RESTING_ESCAPE_AFTER_SEC of unclear lookups -- in both cases
        only once a positions read showed it unfilled): change 0, escaped=True -- qqq_exec
        pushes it and asks for a reconcile. Re-arming is blocked (resting_blocked) until a
        reconcile agrees AND, for a record of this session, finds it still absent from
        get_order_open (state["resting_absent"]): an order Webull is still working but did
        not list must never get a second stop placed next to it (2026-09-29 second review).
        Caller holds the lock."""
        now = time.time()
        self._state.setdefault("resting_events", []).append({
            "client_order_id": coid, "leg": rec.get("leg"), "trade_id": rec.get("trade_id"),
            "symbol": rec.get("symbol"), "kind": rec.get("kind"), "group": rec.get("group"),
            "combo_id": rec.get("combo_id"), "side": rec.get("side"), "qty": rec.get("qty"),
            "status": status, "filled": int(rec.get("booked") or 0), "change": 0,
            "filled_price": None, "stop_price": rec.get("stop_price"),
            "limit_price": rec.get("limit_price"), "final": True, "source": source,
            "escaped": True, "reason": reason, "placed_at": rec.get("placed_at"), "ts": now})
        self._state["resting_blocked"] = (f"resting {coid} settled {status} without Webull's own "
                                          f"final record")
        if status != "EXPIRED":   # an earlier session's DAY order cannot still be working
            self._state.setdefault("resting_absent", {})[coid] = {
                "account_id": rec.get("account_id"), "at": now}
        self._save_state()
        self.log(f"  [webull-orders] RESTING {rec.get('kind')} {coid} ({rec.get('leg')}) "
                 f"settled {status} with 0 filled ({source}): {reason}")

    def _settle_resting(self, coid, ans, source, extra=None):
        """Apply one Webull answer to resting record `coid`: the books count exactly the
        shares Webull says filled (FILLED = all; a partial or a dead order its filled
        quantity; never the ack), the record is marked live or terminal, a fill is queued
        for take_resting_events (`extra` merged into that event), and after any fill every
        other live leg of the group is marked cancel_due. `ans` None (no answer at all),
        "not found" and a dead status without a filled quantity in session are unclear:
        counted (_note_unclear), the record stays live, and only _settle_absent's
        get_order_open + positions read settles it -- for an ACKED order placed on an
        earlier session "not found" makes it due for that read at once (expired_not_found).
        A working stop whose lookup shows another stop price than the record (a replace
        that did not take) takes Webull's price, so qqq_exec moves it again. Returns the
        change in booked shares. Caller holds the lock."""
        rec = self._resting().get(coid)
        if rec is None:
            return 0
        now = time.time()
        rec["checked_at"] = now
        if not ans:
            if rec.get("live"):
                self._note_unclear(rec, now, None)
                self._save_state()
            return 0
        st, filled = ans.get("status"), ans.get("filled")
        if st == "NOT_FOUND":
            placed = self._placed_day(rec)
            if rec.get("acked") and placed is not None and placed < _now_ny().date():
                # a DAY order from an earlier session Webull no longer finds: most likely
                # expired -- but a stop that FILLED before it aged out reads the same, so the
                # positions read in _settle_absent decides (2026-09-29 second review)
                rec["expired_not_found"] = str(placed)
            # "not found" alone never proves a send missed Webull (its index may lag):
            # _settle_absent checks get_order_open and the position first
            if rec.get("live"):
                self._note_unclear(rec, now, st)
            self._save_state()
            return 0
        dead = st in RESTING_DEAD_STATUSES or st in ("NOT_PLACED", "ABSENT")
        if st == "FILLED":
            target = rec["qty"]
        elif dead:
            target = filled if filled is not None else (0 if self._session_over(rec) else None)
        elif st in LIVE_STATUSES:
            target = filled if st == "PARTIAL_FILLED" and filled else None
        else:
            target = None
        terminal = st == "FILLED" or (dead and target is not None)
        prev_booked = int(rec.get("booked") or 0)
        prev_px = _to_px(rec.get("filled_price"))
        if st in LIVE_STATUSES:
            rec.update(status=st, live=True, pending=False, acked=True)
            for k in ("unclear_since", "unclear_n", "expired_not_found", "absent_undecided"):
                rec.pop(k, None)
            seen = _to_px(ans.get("stop_price"))
            mine = _to_px(rec.get("stop_price"))
            if rec.get("kind") == "stop" and seen is not None and mine is not None \
                    and abs(seen - mine) >= 0.005:
                # Webull works this stop at another price than the record says (a replace
                # that did not take): the record follows Webull, so the caller moves it again
                self.log(f"  [webull-orders] RESTING stop {coid} rests at {_px_str(seen)} at "
                         f"Webull, not {_px_str(mine)} -- record corrected")
                rec["stop_price"] = seen
        elif terminal:
            rec.update(status=st, live=False, pending=False, cancel_due=False,
                       final_status=st, settled_at=now)
            rec.pop("unclear_since", None)
            rec.pop("unclear_n", None)
            self._mark_final(coid, st)
        elif rec.get("live"):
            self._note_unclear(rec, now, st)   # unreadable or dead without a quantity: ask again
        change = 0
        if target is not None and (terminal or target > int(rec.get("booked") or 0)):
            change = self._book_part(coid, target, pending=False)
            rec["booked"] = int((self._parts().get(coid) or {}).get("booked") or 0)
        if ans.get("price"):
            rec["filled_price"] = ans["price"]
        if change:
            # Webull's filled_price is the whole order's average: a second step of a fill
            # (a partial, then the rest) is priced at ITS OWN shares' average (2026-09-29
            # second review), so the fill rows add up to Webull's average
            ev_px = rec.get("filled_price")
            new_px = _to_px(ans.get("price"))
            if change > 0 and prev_booked > 0 and prev_px is not None and new_px is not None:
                step_px = (new_px * int(rec["booked"]) - prev_px * prev_booked) / change
                if step_px > 0:
                    ev_px = round(step_px, 4)
            ev = {
                "client_order_id": coid, "leg": rec.get("leg"), "trade_id": rec.get("trade_id"),
                "symbol": rec.get("symbol"), "kind": rec.get("kind"), "group": rec.get("group"),
                "combo_id": rec.get("combo_id"), "side": rec.get("side"), "qty": rec.get("qty"),
                "status": st, "filled": rec["booked"], "change": change,
                "filled_price": ev_px, "stop_price": rec.get("stop_price"),
                "limit_price": rec.get("limit_price"), "final": terminal, "source": source,
                "placed_at": rec.get("placed_at"), "ts": now}
            ev.update(extra or {})
            self._state.setdefault("resting_events", []).append(ev)
            self.log(f"  [webull-orders] RESTING {rec.get('kind')} {coid} ({rec.get('leg')}) is "
                     f"{st} at Webull ({source}): books now count {rec['booked']} of "
                     f"{rec.get('qty')} share(s)")
        if int(rec.get("booked") or 0) > 0:
            for c in self._group_ids([coid]):
                if self._resting()[c].get("live"):
                    self._resting()[c]["cancel_due"] = True
        self._save_state()
        return change

    def _absent_check_due(self, coid, rec, now):
        """True when a live record may be settled by its absence from get_order_open: a
        send never acked whose lookups said "not found" past RESTING_NOT_FOUND_GRACE_SEC,
        or any record with no clear answer for RESTING_ESCAPE_AFTER_SEC and at least
        RESTING_ESCAPE_MIN_TRIES lookups. Never one whose place_order is still on the wire."""
        if not rec or not rec.get("live") or coid in self._resting_sending:
            return False
        if now - float(rec.get("absent_checked_at") or 0) < RESTING_ABSENT_RECHECK_SEC:
            return False   # an undecided positions read is not repeated every tick
        if rec.get("expired_not_found"):
            return True    # an earlier session's DAY order Webull no longer finds
        if (not rec.get("acked") and rec.get("last_answer") == "NOT_FOUND"
                and now - float(rec.get("placed_at") or 0) >= RESTING_NOT_FOUND_GRACE_SEC):
            return True
        since = rec.get("unclear_since")
        return (since is not None and int(rec.get("unclear_n") or 0) >= RESTING_ESCAPE_MIN_TRIES
                and now - float(since) >= RESTING_ESCAPE_AFTER_SEC)

    def _settle_absent(self, client, coids, source, opens=None):
        """The one way out for a live record Webull's order lookup cannot settle (see
        _absent_check_due): one get_order_open read (`opens` when the caller already has
        one; the lock is let go for the read). Listed and working = live (a clear answer,
        the streak resets). NOT listed proves only that Webull is not working it -- a
        FILLED order is never listed either -- so ONE positions read decides
        (_absent_position_verdict): unfilled -> dead with what the books already count
        (EXPIRED for an earlier session's DAY order, NOT_PLACED for a send never acked,
        else ABSENT) and one escape event; filled -> booked like Webull's own FILLED /
        partial record, its event marked inferred (no fill price); undecided -> nothing
        settled, the record stays live (the gateway keeps QQQ orders back) and one
        "undecided" event per record goes out. A failed read settles nothing. Returns the
        ids settled. Caller holds the lock."""
        now = time.time()
        cand = [c for c in coids if self._absent_check_due(c, self._resting().get(c), now)]
        if not cand:
            return []
        if opens is None:
            acct = (self._resting().get(cand[0]) or {}).get("account_id")
            with self._lock_released():
                opens = self.open_orders(account_id=acct)
        if opens is None:
            return []
        listed = {o.get("client_order_id"): o for o in opens}
        gone = []
        for c in cand:
            rec = self._resting().get(c)
            if not rec or not rec.get("live"):
                continue
            rec["absent_checked_at"] = now
            if c in listed:
                st = _norm_status(listed[c].get("status"))
                if st in LIVE_STATUSES:
                    self._settle_resting(c, {"status": st, "filled": _to_qty(
                        listed[c].get("filled_quantity")), "price": None}, source)
                continue
            gone.append(c)
        self._save_state()
        if not gone:
            return []
        verdict, why = self._absent_position_verdict(client, gone, set(listed))
        if verdict is None:
            for c in gone:
                rec = self._resting().get(c)
                if not rec or not rec.get("live"):
                    continue
                rec["absent_undecided"] = why
                if rec.get("undecided_alerted"):
                    continue
                rec["undecided_alerted"] = now
                self._state.setdefault("resting_events", []).append({
                    "client_order_id": c, "leg": rec.get("leg"), "trade_id": rec.get("trade_id"),
                    "symbol": rec.get("symbol"), "kind": rec.get("kind"), "group": rec.get("group"),
                    "combo_id": rec.get("combo_id"), "side": rec.get("side"), "qty": rec.get("qty"),
                    "status": rec.get("status"), "filled": int(rec.get("booked") or 0),
                    "change": 0, "filled_price": None, "stop_price": rec.get("stop_price"),
                    "limit_price": rec.get("limit_price"), "final": False, "source": source,
                    "undecided": True, "reason": why, "placed_at": rec.get("placed_at"),
                    "ts": now})
                self.log(f"  [webull-orders] \u26a0 RESTING {rec.get('kind')} {c} ({rec.get('leg')}) "
                         f"is not among Webull's open orders and its fill cannot be decided: "
                         f"{why} -- kept live, QQQ orders wait")
            self._save_state()
            return []
        done = []
        for c in gone:
            rec = self._resting().get(c)
            if not rec or not rec.get("live"):
                continue
            booked = int(rec.get("booked") or 0)
            add = int(verdict.get(c) or 0)
            if add:
                total = booked + add
                st = "FILLED" if total >= int(rec["qty"]) else "ABSENT"
                self._settle_resting(c, {"status": st, "filled": float(total), "price": None},
                                     source, extra={"inferred": True, "reason": why})
            else:
                st = ("EXPIRED" if rec.get("expired_not_found")
                      else "ABSENT" if rec.get("acked") else "NOT_PLACED")
                if rec.get("expired_not_found"):
                    lead = f"Webull no longer finds this DAY order from {rec['expired_not_found']}"
                elif rec.get("acked"):
                    lead = (f"no clear answer from Webull's order lookup for "
                            f"{now - float(rec.get('unclear_since') or now):.0f}s "
                            f"({rec.get('last_answer')})")
                else:
                    lead = "the send never got an answer and Webull does not find it"
                self._settle_resting(c, {"status": st, "filled": float(booked)}, source)
                self._queue_escape(c, rec, st, f"{lead}; not among its open orders, and {why}",
                                   source)
            done.append(c)
        return done

    def _absent_position_verdict(self, client, gone, listed=()):
        """({id: shares filled beyond what the books count}, why) for resting records Webull
        does not list as open (`gone`), from ONE positions read: the account net the books
        hold is compared with Webull's position. Equal -> every record unfilled ({id: 0});
        different by exactly what ONE record's unbooked remainder would move it (its side's
        sign, at most its remaining shares) -> that record filled that much. (None, why) --
        undecided -- when the read fails, another QQQ order part is still working, another
        live resting record is neither listed nor in `gone`, the books moved during the
        read, or the difference fits no single record. Caller holds the lock (let go for the
        read)."""
        recs = {c: self._resting()[c] for c in gone}
        symbols = {str(r.get("symbol") or "").upper() for r in recs.values()}
        accts = {r.get("account_id") for r in recs.values()}
        if len(symbols) != 1 or len(accts) != 1:
            return None, "the records span more than one symbol or account"
        symbol, acct = symbols.pop(), accts.pop()
        busy = self._unsettled_parts(symbol, fresh_sec=RESTING_PREV_WORKING_SEC,
                                     pending_max_age=PREV_TERMINAL_PENDING_MAX_SEC,
                                     acked_only=True)
        if busy:
            return None, (f"order {busy[0][0]} (leg {busy[0][1].get('leg')}) is not yet FILLED "
                          f"or dead at Webull, so its position cannot be compared")
        other = [c for c in self._live_resting(symbol) if c not in recs and c not in listed]
        if other:
            return None, f"resting order(s) {', '.join(other)} are unsettled too"
        before = self._account_net(symbol, acct)
        err, broker = None, None
        with self._lock_released():
            try:
                broker = _positions_from_response(client.account_v2.get_account_position(acct))
            except Exception as e:
                err = f"{type(e).__name__}: {e}"[:200]
        if broker is None:
            return None, f"Webull's position could not be read ({err})"
        if abs(self._account_net(symbol, acct) - before) > 1e-9 or \
                any(not (self._resting().get(c) or {}).get("live") for c in recs):
            return None, "the books moved during the position read"
        held = float(broker.get(symbol, 0.0))
        diff = held - before
        if abs(diff) < 1e-6:
            return {c: 0 for c in recs}, (f"Webull's {symbol} position {held:g} matches the "
                                          f"books without a fill")
        fits = []
        for c, r in recs.items():
            left = int(r.get("qty") or 0) - int(r.get("booked") or 0)
            sign = 1 if r.get("side") == "BUY" else -1
            if (diff * sign > 0 and abs(diff) <= left + 1e-6
                    and abs(abs(diff) - round(abs(diff))) < 1e-6):
                fits.append(c)
        if len(fits) == 1:
            n = int(round(abs(diff)))
            return ({c: (n if c == fits[0] else 0) for c in recs},
                    f"Webull's {symbol} position {held:g} is the books' {before:g} moved by "
                    f"{fits[0]}'s fill of {n} (inferred -- Webull's fill price unknown)")
        return None, (f"Webull's {symbol} position {held:g} vs the books' {before:g}: "
                      f"{diff:+g} is not " + ("one resting order's fill" if not fits else
                                              "attributable to a single leg of the group"))

    def _cancel_siblings_now(self, client, coid):
        """After a fill on `coid` (whole or partial): send the cancel of every live leg of
        its group still due one -- the rest of an OCO, and a part-filled leg itself -- in
        the SAME call, never the next resolve (2026-09-29 second review: a partial target
        fill must not leave the full-size stop working a tick longer). The next lookups
        confirm them. Caller holds the lock."""
        for c in self._group_ids([coid]):
            r = self._resting().get(c) or {}
            if r.get("live") and r.get("cancel_due") and not r.get("cancel_sent_at"):
                self._send_cancel(client, c)

    def _send_cancel(self, client, coid):
        """One cancel_order for resting record `coid` (its answer is only ever read from a
        lookup), with the adapter lock let go for the call. A cancel that raised leaves
        cancel_due set, so the next resolve_resting sends it again. Never raises."""
        rec = self._resting().get(coid)
        if rec is None:
            return
        err = None
        with self._lock_released():
            try:
                client.order_v3.cancel_order(rec.get("account_id"), coid)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"[:200]
        if err is None:
            rec.pop("cancel_error", None)
        else:
            rec["cancel_error"] = err
            self.log(f"  [webull-orders] cancel of resting {coid} raised ({err}) -- its "
                     f"lookup decides")
        rec["cancel_sent_at"] = time.time()
        rec["cancel_due"] = err is not None and bool(rec.get("live"))
        self._save_state()

    def _cancel_and_confirm(self, client, coids, window_sec, source, stop_at=None):
        """Cancel every live leg of the groups `coids` belong to (always BOTH legs of an
        OCO) and look each up, up to RESTING_CANCEL_TRIES rounds over about `window_sec`,
        until Webull reports it terminal; a fill found on the way is booked. Returns the
        ids still not terminal ([] = all settled). Caller holds the lock; it is let go
        for each wait and lookup round."""
        ids = [c for c in self._group_ids(coids) if self._resting()[c].get("live")]
        for c in ids:
            self._send_cancel(client, c)
        tries = RESTING_CANCEL_TRIES
        for i in range(tries):
            todo = [(c, self._resting()[c].get("account_id")) for c in ids
                    if self._resting().get(c, {}).get("live")]
            if not todo:
                break
            wait = window_sec / tries if i else 0.0
            if i and stop_at is not None and time.time() + wait >= stop_at:
                break
            if i == tries // 2:
                for c, _ in todo:   # halfway and still working: ask once more
                    self._send_cancel(client, c)
            with self._lock_released():
                if wait:
                    _sleep(wait)
                answers = [(c, self._lookup_order(client, acct, c, detail=True)) for c, acct in todo]
            for c, ans in answers:
                self._settle_resting(c, ans, source)
        # a record no lookup can settle is not left blocking every order for good
        self._settle_absent(client, [c for c in ids if self._resting().get(c, {}).get("live")],
                            source)
        return [c for c in ids if self._resting().get(c, {}).get("live")]

    def _await_prev_terminal(self, client, symbol, deadline):
        """PREVIOUS ORDER TERMINAL: look up every part on `symbol` Webull may still be
        working (_unsettled_parts, the same test the end-of-day cross uses) until it is
        FILLED or dead (booked exactly, like _resolve_pending, with a part event queued
        for a change). Returns "<id> (leg <leg>)" for the first one still working, else
        None. Caller holds the lock."""
        todo = sorted(self._unsettled_parts(symbol, fresh_sec=RESTING_PREV_WORKING_SEC,
                                            pending_max_age=PREV_TERMINAL_PENDING_MAX_SEC,
                                            acked_only=True),
                      key=lambda cp: float(cp[1].get("ts") or 0))
        for coid, p in todo:
            window = max(0.0, min(SPLIT_FILL_POLL_WINDOW_SEC, deadline - time.time()))
            ans = self._poll_order(client, p.get("account_id"), coid, SPLIT_FILL_POLL_TRIES,
                                   window, lambda a: _terminal_qty(1, a["status"], a["filled"])
                                   is not None, stop_at=deadline)
            part = self._parts().get(coid)
            if part is None:
                continue
            st = ans["status"] if ans else None
            target = _terminal_qty(part["qty"], st, ans["filled"]) if ans else None
            if target is None:
                return f"{coid} (leg {part.get('leg')}, {st or 'no answer'})"
            self._mark_final(coid, st)
            change = self._book_part(coid, target, pending=False)
            if change:
                self._state.setdefault("part_events", []).append(
                    {"client_order_id": coid, "leg": part["leg"], "intent": part.get("intent"),
                     "status": st, "qty": part["qty"], "booked": part["booked"],
                     "change": change})
                self._save_state()
        return None

    def _stale_undecided(self, rec):
        """True for a live resting record placed on an EARLIER NY session whose fill the
        positions read could not decide (absent_undecided). A DAY order from a previous
        session cannot still be working -- no 417 box-rule risk -- so it holds back only its
        own leg's CLOSE (the double-close risk), never the other legs' orders (2026-09-29
        third review: it used to hold every QQQ order, indefinitely)."""
        placed = self._placed_day(rec or {})
        return bool(rec and rec.get("live") and rec.get("absent_undecided")
                    and placed is not None and placed < _now_ny().date())

    def _order_gateway(self, mode, symbol, send_started, leg=None, intent=None):
        """place_stock_order's gateway: None when the order may be planned now, else
        {"outcome", "reason"} for a NOT_SENT record. A stale undecided record
        (_stale_undecided) is only re-checked (_settle_absent, rate-limited), never
        cancelled here, and holds back only `leg`'s own CLOSE. Caller holds the lock."""
        deadline = send_started + RESTING_GATEWAY_BUDGET_SEC
        live = self._live_resting(symbol)
        stale = [c for c in live if self._stale_undecided(self._resting().get(c))]
        if stale:
            client = self._client(mode)
            if client is not None:
                self._settle_absent(client, stale, "gateway")
            stale = [c for c in stale if self._stale_undecided(self._resting().get(c))]
            mine = [c for c in stale if self._resting()[c].get("leg") == leg
                    and str(intent or "").upper() == "CLOSE"]
            if mine:
                return {"outcome": "RESTING_UNRESOLVED",
                        "reason": f"busy: {leg}'s resting order(s) {', '.join(mine)} from an "
                                  f"earlier session may have filled (undecided) -- its close "
                                  f"waits; nothing sent"}
            live = [c for c in self._live_resting(symbol) if c not in stale]
            if not live and not self._prev_terminal_on():
                return None
        client = self._client(mode)
        if client is None:
            if live:
                return {"outcome": "RESTING_UNRESOLVED",
                        "reason": f"busy: {len(live)} resting order(s) on {symbol} and no "
                                  f"{mode} client to cancel them -- nothing sent"}
            return None
        if live:
            self.log(f"  [webull-orders] GATEWAY {symbol}: cancelling resting "
                     f"{', '.join(sorted(self._group_ids(live)))} before the next order")
            unresolved = self._cancel_and_confirm(client, live, max(0.0, deadline - time.time()),
                                                  "gateway", stop_at=deadline)
            unresolved = [c for c in unresolved or [] if c not in stale]
            still = [c for c in self._live_resting(symbol) if c not in stale]
            if unresolved or still:
                return {"outcome": "RESTING_UNRESOLVED",
                        "reason": f"busy: resting order(s) {', '.join(unresolved or still)} "
                                  f"not confirmed cancelled or filled at Webull -- nothing sent"}
        if self._prev_terminal_on():
            working = self._await_prev_terminal(client, symbol, deadline)
            if working:
                return {"outcome": "NOT_SENT",
                        "reason": f"busy: earlier order {working} not yet FILLED or dead at "
                                  f"Webull -- nothing sent"}
        return None

    def _closed_by_resting(self, leg, coid=None):
        """{client_order_id, kind, filled, filled_price, trade_id} for the resting order
        that closed `leg` at Webull, or None. A trade-id CLOSE (qx<tid>C...) matches only
        that trade's resting orders (qx<tid>P<n>/T<n>); any other id takes the leg's
        latest filled one, unless an OPEN for the leg went out after it. Caller holds the
        lock."""
        recs = [r for r in self._resting().values()
                if r.get("leg") == leg and int(r.get("booked") or 0) > 0]
        if not recs:
            return None
        same = [r for r in recs if coid and str(coid).startswith(
            str(r.get("client_order_id", ""))[:-(1 + len(str(r.get("n", ""))))] or "\0")]
        if not same and str(coid or "").startswith("qx"):
            return None   # a trade-id CLOSE for another trade than any resting order's
        last = max(same or recs, key=lambda r: float(r.get("placed_at") or 0))
        if not same and any(
                p.get("leg") == leg and p.get("intent") == "OPEN" and not p.get("resting")
                and float(p.get("ts") or 0) > float(last.get("placed_at") or 0)
                for p in self._parts().values()):
            return None
        return {"client_order_id": last.get("client_order_id"), "kind": last.get("kind"),
                "filled": int(last.get("booked") or 0), "filled_price": last.get("filled_price"),
                "trade_id": last.get("trade_id")}

    def _prune_resting(self):
        cutoff = time.time() - RESTING_KEEP_SEC
        rest = self._state.get("resting")
        if rest:
            for c in [c for c, r in rest.items()
                      if not r.get("live") and float(r.get("placed_at") or 0) < cutoff]:
                rest.pop(c, None)
        seq = self._state.get("resting_seq")
        if seq:
            for t in [t for t, v in seq.items() if float((v or {}).get("ts") or 0) < cutoff]:
                seq.pop(t, None)

    def resting_plan(self, symbol, direction, qty, leg=None, lock_timeout=1.0):
        """What place_resting would plan right now, with NO network: {"net" (account net
        on `symbol`), "side" (None = crossing, not rested), "leg_qty" (the leg's broker
        qty, when `leg` is given), "live" (resting ids on the symbol), "refusal" ([outcome,
        reason] place_resting would refuse with before planning, or None; only when `leg`
        is given)}. For the caller's log-only mode. Never raises; {"error"} when the lock
        stays busy for `lock_timeout` (a send is in flight)."""
        try:
            if not self._lock.acquire(timeout=lock_timeout):
                return {"net": None, "side": None, "live": [], "error": "adapter busy"}
            try:
                symbol = str(symbol).upper()
                direction = "BUY" if str(direction).upper() == "BUY" else "SELL"
                net = self._account_net(symbol)
                out = {"net": net, "side": plan_resting_side(net, direction, qty),
                       "live": self._live_resting(symbol)}
                if leg is not None:
                    out["leg_qty"] = float(((self._state.get("broker_sent_positions") or {})
                                            .get(leg) or {}).get("qty", 0) or 0)
                    refusal = self._resting_refusal(leg, symbol, direction, int(round(float(qty))))
                    out["refusal"] = list(refusal) if refusal else None
                return out
            finally:
                self._lock.release()
        except Exception as e:
            return {"net": None, "side": None, "live": [], "error": f"{type(e).__name__}: {e}"}

    def order_parts(self, leg=None, intent=None, lock_timeout=1.0):
        """Copies of the recorded order parts ({client_order_id, leg, symbol, side, qty,
        intent, booked, pending, final_status, resting, ts}), narrowed to `leg` / `intent`
        when given. No network. [] when the lock stays busy or on any problem -- the caller
        (api/qqq_exec.py's resting-stop arming rule: is ORB's entry confirmed FILLED?)
        reads an empty list as "not confirmed". Never raises."""
        try:
            if not self._lock.acquire(timeout=lock_timeout):
                return []
            try:
                out = []
                for coid, p in (self._state.get("order_parts") or {}).items():
                    if not isinstance(p, dict):
                        continue
                    if (leg is not None and p.get("leg") != leg) or \
                            (intent is not None and p.get("intent") != intent):
                        continue
                    out.append(dict(json.loads(json.dumps(p)), client_order_id=coid))
                return out
            finally:
                self._lock.release()
        except Exception:
            return []

    def _resting_refusal(self, leg, symbol, direction, qty):
        """(outcome, reason) when a resting order may not be placed now, else None. Caller
        holds the lock."""
        if self._stock_sends:
            return "BUSY", "a stock order is being sent -- re-arm after it"
        if self._state.get("resting_blocked"):
            return "BLOCKED", f"re-arming blocked until a reconcile agrees ({self._state['resting_blocked']})"
        if self._halted and self._halt_source == "reconcile":
            return "BLOCKED", f"halted by reconcile: {self._halt_reason}"
        live = self._live_resting(symbol)
        if live:
            return "BUSY", f"resting order(s) {', '.join(live)} already live on {symbol} (one group at a time)"
        working = self._unsettled_parts(symbol, fresh_sec=RESTING_PREV_WORKING_SEC,
                                        pending_max_age=PREV_TERMINAL_PENDING_MAX_SEC,
                                        acked_only=True)
        if working:
            return "BUSY", (f"order {working[0][0]} (leg {working[0][1].get('leg')}) not yet "
                            f"FILLED or dead at Webull")
        p = (self._state.get("broker_sent_positions") or {}).get(leg) or {}
        held = float(p.get("qty", 0) or 0) if str(p.get("symbol", "")).upper() == symbol else 0.0
        if (direction == "SELL" and held < qty - 1e-9) or (direction == "BUY" and held > -qty + 1e-9):
            return "NOT_SENT", (f"leg {leg!r} holds {held:g} at the broker -- a {direction}-direction "
                                f"resting order for {qty} would not close it")
        return None

    def place_resting(self, *, leg, trade_id, symbol, direction, qty, stop_price,
                      limit_price=None, last_price=None, account_id=None, tif="DAY"):
        """Rest `leg`'s protective exit at Webull: a STOP_LOSS at `stop_price`, or -- with
        `limit_price` -- ONE native OCO of that stop plus a LIMIT target under
        client_combo_order_id qx<tid>K<n> (both legs combo_type "OCO", same side and
        quantity). `direction` is the exit's direction ("SELL" closes a long leg, "BUY" a
        short one); the broker side is planned from the account net as ONE part
        (plan_resting_side) and a crossing one is never rested. qty must be what the leg
        holds at the broker. DAY, CORE session, stop/limit prices sent as cent strings.

        Refused with nothing sent (ok=False, sent=False, `outcome`): NOT_SENT (mode not
        PAPER/LIVE -- OFF never reaches Webull -- or the leg does not hold `qty`), BLOCKED
        (a reconcile halt or mismatch), BUSY (a stock order is being sent, a resting
        group is already live on the symbol, or an earlier order part is still working),
        CROSSING (the account net sits strictly between 0 and qty on the closing side),
        CROSSED (`last_price` is already through the stop -- the caller sends its market
        close -- or through the target: crossed="stop"/"target"). The adapter kill file
        does not refuse it: it is protection, like a CLOSE.

        Sent: the records are written PENDING first; outcome RESTING (ok=True, acked),
        REFUSED (a 4xx, http_status set), UNKNOWN (the send raised and no lookup settled
        it: the records stay live, so the next gateway cancels and confirms them), or
        FILLED/DEAD when a lookup after a failed send found it already done. Never booked
        on the ack. Returns {ok, sent, mode, outcome, reason, leg, trade_id, symbol,
        direction, side, qty, stop_price, limit_price, kind ("stop"|"oco"), n, group,
        combo_id, client_order_ids, net, crossed?, http_status?}. Raises ValueError only
        for malformed arguments; never for a broker problem."""
        direction = str(direction).upper()
        direction = "SELL" if direction in ("SELL", "SHORT") else direction
        if direction not in ("SELL", "BUY"):
            raise ValueError(f"direction must be SELL or BUY, got {direction!r}")
        tif = str(tif).upper()
        if tif not in ORDER_TIFS:
            raise ValueError(f"tif must be one of {ORDER_TIFS}, got {tif!r}")
        qty = int(round(float(qty)))
        stop = _to_px(stop_price)
        limit = None if limit_price is None else _to_px(limit_price)
        if qty <= 0 or stop is None or (limit_price is not None and limit is None):
            raise ValueError(f"bad resting order: qty={qty!r} stop={stop_price!r} limit={limit_price!r}")
        if limit is not None and ((direction == "SELL" and limit <= stop)
                                  or (direction == "BUY" and limit >= stop)):
            raise ValueError(f"target {limit} is not beyond the stop {stop} for a {direction} exit")
        symbol = str(symbol).upper()
        kind = "oco" if limit is not None else "stop"
        out = {"ok": False, "sent": False, "leg": leg, "trade_id": trade_id, "symbol": symbol,
               "direction": direction, "qty": qty, "stop_price": stop, "limit_price": limit,
               "kind": kind, "client_order_ids": [], "ts": time.time()}
        mode, why = self.effective_mode()
        out["mode"] = mode
        if mode not in (MODE_PAPER, MODE_LIVE):
            out.update(outcome="NOT_SENT", reason=f"resting orders need PAPER or LIVE (mode={mode}): {why}")
            return out
        send_started = time.time()
        with self._lock:
            refusal = self._resting_refusal(leg, symbol, direction, qty)
            client = None if refusal else self._client(mode)
            if refusal is None and client is None:
                refusal = ("NOT_SENT", f"no {mode} client ({why})")
            if refusal is None:
                try:
                    account_id = account_id or self._account_id(mode, client)
                except Exception as e:
                    refusal = ("NOT_SENT", f"account id: {type(e).__name__}: {e}")
            if refusal is None:
                net = self._account_net(symbol, account_id)
                side = plan_resting_side(net, direction, qty)
                out.update(net=net, side=side)
                lp = _to_px(last_price)
                if side is None:
                    refusal = ("CROSSING", f"account net {net:g} sits between 0 and {qty} on the "
                                           f"closing side -- a resting order would cross zero")
                elif lp is not None and (lp <= stop if direction == "SELL" else lp >= stop):
                    out["crossed"] = "stop"
                    refusal = ("CROSSED", f"last trade {lp:g} is already through the stop {stop:g}")
                elif lp is not None and limit is not None and (
                        lp >= limit if direction == "SELL" else lp <= limit):
                    out["crossed"] = "target"
                    refusal = ("CROSSED", f"last trade {lp:g} is already through the target {limit:g}")
            if refusal is not None:
                out.update(outcome=refusal[0], reason=refusal[1])
                self.log(f"  [webull-orders] RESTING {kind} for {leg} not placed: {refusal[1]}")
                return out
            self._prune_resting()
            self._prune_parts()
            seq = self._state.setdefault("resting_seq", {})
            n = int((seq.get(str(trade_id)) or {}).get("n") or 0) + 1
            seq[str(trade_id)] = {"n": n, "ts": time.time()}
            p_id, t_id, k_id = resting_ids(trade_id, n)
            group = k_id if kind == "oco" else p_id
            combo = "OCO" if kind == "oco" else "NORMAL"
            legs = [(p_id, "stop", "STOP_LOSS")] + ([(t_id, "target", "LIMIT")] if limit else [])
            orders = []
            for coid, leg_kind, otype in legs:
                o = {"combo_type": combo, "client_order_id": coid, "symbol": symbol,
                     "instrument_type": "EQUITY", "market": "US", "order_type": otype,
                     "quantity": str(qty), "support_trading_session": "CORE", "side": side,
                     "time_in_force": tif, "entrust_type": "QTY"}
                if otype == "STOP_LOSS":
                    o["stop_price"] = _px_str(stop)
                else:
                    o["limit_price"] = _px_str(limit)
                orders.append(o)
                now = time.time()
                self._state.setdefault("resting", {})[coid] = {
                    "client_order_id": coid, "leg": leg, "trade_id": trade_id, "symbol": symbol,
                    "kind": leg_kind, "group": group, "combo_id": k_id if kind == "oco" else None,
                    "n": n, "side": side, "qty": qty, "order_type": otype,
                    "stop_price": stop if otype == "STOP_LOSS" else None,
                    "limit_price": limit if otype == "LIMIT" else None,
                    "account_id": account_id, "status": "PENDING", "live": True, "pending": True,
                    "acked": False, "booked": 0, "placed_at": now}
                self._parts()[coid] = {"leg": leg, "symbol": symbol, "side": side, "qty": qty,
                                       "intent": "CLOSE", "account_id": account_id, "ts": now,
                                       "booked": 0, "pending": False, "resting": True}
            self._save_state()   # PENDING on disk before the send
            ids = [c for c, _, _ in legs]
            out.update(n=n, group=group, combo_id=k_id if kind == "oco" else None,
                       client_order_ids=ids, sent=True)
            # the lock is let go for the call (2026-09-29 review): a hung place_order must
            # not freeze every other adapter caller. The PENDING records are on disk, a
            # stock send meanwhile finds them live and its gateway cancels first, and
            # "not found" on an id still on the wire never reads as "never placed".
            self._resting_sending.update(ids)
            try:
                with self._lock_released():
                    if kind == "oco":
                        resp = client.order_v3.place_order(account_id, orders,
                                                           client_combo_order_id=k_id)
                    else:
                        resp = client.order_v3.place_order(account_id, orders)
            except Exception as e:
                self._resting_sending.difference_update(ids)
                reason = f"{type(e).__name__}: {e}"
                out["http_status"] = _http_status(e)
                if _definite_refusal(e):
                    for c in ids:
                        self._resting()[c].update(status="REFUSED", live=False, pending=False,
                                                  final_status="REFUSED", settled_at=time.time())
                        self._mark_final(c, "REFUSED")
                    self._save_state()
                    # a 429 is Webull's rate limit, not a verdict on the order: RATE_LIMITED,
                    # which the caller waits out without counting a failed try
                    limited = out["http_status"] == HTTP_TOO_MANY_REQUESTS
                    out.update(outcome="RATE_LIMITED" if limited else "REFUSED", reason=reason)
                    self._last_error = reason
                    self.log(f"  [webull-orders] RESTING {kind} {group} for {leg} "
                             f"{'RATE LIMITED' if limited else 'REFUSED'}: {reason}")
                    return out
                stop_at = send_started + SEND_LOOKUP_BUDGET_SEC
                for c in ids:
                    ans = self._poll_order(client, account_id, c, UNKNOWN_LOOKUP_TRIES,
                                           UNKNOWN_LOOKUP_WINDOW_SEC,
                                           lambda a: a["status"] != "NOT_FOUND", stop_at=stop_at,
                                           detail=True)
                    if ans is not None:
                        self._settle_resting(c, ans, "send")
                recs = [self._resting()[c] for c in ids]
                if any(r.get("pending") for r in recs):
                    outcome = "UNKNOWN"
                elif any(r.get("live") for r in recs):
                    outcome = "RESTING"
                else:
                    outcome = "FILLED" if any(int(r.get("booked") or 0) for r in recs) else "DEAD"
                out.update(ok=outcome == "RESTING", outcome=outcome,
                           reason=f"send raised ({reason}); Webull's own record: " + ", ".join(
                               f"{r['client_order_id']} {r.get('status')}" for r in recs))
                self.log(f"  [webull-orders] RESTING {kind} {group} for {leg}: {out['reason']}")
                return out
            self._resting_sending.difference_update(ids)
            resp = _safe_response(resp)
            for c in ids:
                st = _norm_status(order_status_fields(resp, c).get("status")) or "SUBMITTED"
                rec = self._resting()[c]
                if not rec.get("live"):
                    continue   # settled while the lock was let go (a gateway's cancel)
                rec.update(status=st if st in LIVE_STATUSES else "SUBMITTED", live=True,
                           pending=False, acked=True)
                if st not in LIVE_STATUSES:
                    rec["check_due"] = True   # the ack says more than "working": look it up
            self._save_state()
            desc = (f"{side} {qty} {symbol} stop {_px_str(stop)}"
                    + (f" / target {_px_str(limit)} (OCO)" if limit else ""))
            recs = [self._resting()[c] for c in ids]
            if any(r.get("live") for r in recs):
                out.update(ok=True, outcome="RESTING", reason=desc)
                self.log(f"  [webull-orders] RESTING {kind} {group} for {leg} placed: {desc}")
            else:
                # a gateway on another thread cancelled (or found filled) and settled the
                # group while place_order was on the wire (2026-09-29 second review): never
                # report "armed" for a group that is already dead
                outcome = "FILLED" if any(int(r.get("booked") or 0) for r in recs) else "DEAD"
                out.update(outcome=outcome, reason=f"{desc} -- settled {outcome} at Webull while "
                                                   f"the send was on the wire: " + ", ".join(
                                                       f"{r['client_order_id']} {r.get('status')}"
                                                       for r in recs))
                self.log(f"  [webull-orders] RESTING {kind} {group} for {leg}: {out['reason']}")
            return out

    def cancel_resting(self, *, group=None, client_order_id=None, trade_id=None, leg=None,
                       symbol=None, confirm=True, window_sec=RESTING_GATEWAY_BUDGET_SEC):
        """Cancel the live resting orders matching every filter given (none = all), always
        whole groups (both OCO legs, even when one leg is named). confirm=True looks each
        up until Webull reports it terminal (a fill found is booked and queued as an
        event); confirm=False only sends the cancels (the next resolve_resting or gateway
        confirms them). Returns {ok (every targeted leg terminal), mode, cancelled,
        filled, unresolved} (lists of ids). OFF never reaches Webull. Never raises."""
        out = {"ok": True, "cancelled": [], "filled": [], "unresolved": []}
        try:
            mode, why = self.effective_mode()
            out["mode"] = mode
            with self._lock:
                sel = [c for c in self._live_resting(symbol)
                       if (group is None or self._resting()[c].get("group") == group)
                       and (client_order_id is None or c == client_order_id)
                       and (trade_id is None or self._resting()[c].get("trade_id") == trade_id)
                       and (leg is None or self._resting()[c].get("leg") == leg)]
                if not sel:
                    return out
                ids = [c for c in self._group_ids(sel) if self._resting()[c].get("live")]
                client = self._client(mode) if mode in (MODE_PAPER, MODE_LIVE) else None
                if client is None:
                    out.update(ok=False, unresolved=ids,
                               reason=f"no {mode} client to cancel with ({why})")
                    return out
                if confirm:
                    unresolved = self._cancel_and_confirm(client, ids, window_sec, "cancel")
                else:
                    for c in ids:
                        self._send_cancel(client, c)
                    unresolved = ids
                for c in ids:
                    r = self._resting()[c]
                    if c in unresolved:
                        continue
                    (out["filled"] if int(r.get("booked") or 0) > 0 else out["cancelled"]).append(c)
                out.update(ok=not unresolved, unresolved=list(unresolved))
                return out
        except Exception as e:
            out.update(ok=False, reason=f"{type(e).__name__}: {e}")
            self.log(f"  [webull-orders] cancel_resting failed: {out['reason']}")
            return out

    def replace_resting(self, group, *, stop_price, last_price=None):
        """Move a live group's stop to `stop_price` (the breakeven move). replace_order on
        the stop leg first (proved on paper 2026-09-29), then ONE lookup: a fill found is
        booked and nothing new is placed. If the replace raises, or the lookup still shows
        the old price, the group is cancelled and confirmed and re-placed under a new n
        (place_resting, same leg/trade/direction/qty/target). `group` may be any id of the
        group. Returns {ok, outcome, group, reason, ...}: REPLACED, REARMED (with
        "placed": place_resting's record), FILLED, CROSSED (`last_price` already through
        the new stop: nothing changed, the caller sends its market close), NOT_LIVE, BUSY,
        UNRESOLVED (the cancel could not be confirmed), or place_resting's own refusal
        outcome after a cancel. Never raises for a broker problem."""
        new = _to_px(stop_price)
        if new is None:
            raise ValueError(f"bad stop price {stop_price!r}")
        mode, why = self.effective_mode()
        out = {"ok": False, "mode": mode, "stop_price": new}
        if mode not in (MODE_PAPER, MODE_LIVE):
            out.update(outcome="NOT_SENT", reason=f"resting orders need PAPER or LIVE (mode={mode}): {why}")
            return out
        with self._lock:
            ids = [c for c in self._group_ids([group] if group in self._resting() else
                                              [c for c, r in self._resting().items()
                                               if r.get("group") == group])]
            recs = {c: self._resting()[c] for c in ids}
            stop_id = next((c for c, r in recs.items() if r.get("kind") == "stop" and r.get("live")), None)
            if stop_id is None:
                out.update(outcome="NOT_LIVE", reason=f"no live resting stop in group {group!r}")
                return out
            rec = recs[stop_id]
            out["group"] = rec.get("group")
            direction = "BUY" if rec.get("side") == "BUY" else "SELL"
            lp = _to_px(last_price)
            if lp is not None and (lp <= new if direction == "SELL" else lp >= new):
                out.update(outcome="CROSSED", crossed="stop",
                           reason=f"last trade {lp:g} is already through the new stop {new:g}")
                return out
            if self._stock_sends:
                out.update(outcome="BUSY", reason="a stock order is being sent -- move it after")
                return out
            client = self._client(mode)
            if client is None:
                out.update(outcome="NOT_SENT", reason=f"no {mode} client ({why})")
                return out
            kw = {"client_combo_order_id": rec["combo_id"]} if rec.get("combo_id") else {}
            replaced, err, limited = True, None, False
            with self._lock_released():   # a hung replace must not hold the adapter lock
                try:
                    client.order_v3.replace_order(rec.get("account_id"), [{
                        "client_order_id": stop_id, "quantity": str(rec["qty"]),
                        "stop_price": _px_str(new)}], **kw)
                except Exception as e:
                    replaced, err = False, f"{type(e).__name__}: {e}"
                    limited = _http_status(e) == HTTP_TOO_MANY_REQUESTS
            if limited:
                # Webull's rate limit: the stop still rests at its old price -- no cancel (it
                # would be limited too), the caller moves it again after a wait
                out.update(outcome="RATE_LIMITED", group=rec.get("group"),
                           reason=f"replace of {stop_id} rate limited ({err}) -- the stop stays "
                                  f"at {_px_str(rec.get('stop_price') or 0)}")
                self.log(f"  [webull-orders] RESTING {out['reason']}")
                return out
            if replaced:
                with self._lock_released():
                    ans = self._lookup_order(client, rec.get("account_id"), stop_id, detail=True)
                self._settle_resting(stop_id, ans, "replace")
                if any(int(self._resting()[c].get("booked") or 0) for c in ids):
                    out.update(outcome="FILLED", reason=f"{stop_id} filled at Webull during the move")
                    return out
                if rec.get("live") and (ans is None or ans.get("stop_price") is None
                                        or abs(ans["stop_price"] - new) < 0.005):
                    rec.update(stop_price=new, replaced_at=time.time())
                    self._save_state()
                    out.update(ok=True, outcome="REPLACED", client_order_ids=ids,
                               reason=f"{stop_id} stop moved to {_px_str(new)}")
                    self.log(f"  [webull-orders] RESTING {out['reason']}")
                    return out
                err = (f"replace answered but Webull shows stop {ans.get('stop_price') if ans else None}"
                       if rec.get("live") else f"{stop_id} is {rec.get('status')} at Webull")
            self.log(f"  [webull-orders] RESTING replace of {stop_id} did not take ({err}) -- "
                     f"cancel and re-place")
            unresolved = self._cancel_and_confirm(client, ids, RESTING_GATEWAY_BUDGET_SEC, "replace")
            if unresolved:
                out.update(outcome="UNRESOLVED", reason=f"{', '.join(unresolved)} not confirmed "
                                                        f"cancelled -- nothing re-placed")
                return out
            if any(int(self._resting()[c].get("booked") or 0) for c in ids):
                out.update(outcome="FILLED", reason="filled at Webull during the cancel -- nothing re-placed")
                return out
            limit = next((r.get("limit_price") for r in recs.values() if r.get("kind") == "target"), None)
        # outside the lock: place_resting takes it once and lets it go for its own send
        placed = self.place_resting(leg=rec["leg"], trade_id=rec["trade_id"], symbol=rec["symbol"],
                                    direction=direction, qty=rec["qty"], stop_price=new,
                                    limit_price=limit, last_price=last_price,
                                    account_id=rec.get("account_id"))
        out.update(ok=bool(placed.get("ok")), placed=placed,
                   outcome="REARMED" if placed.get("ok") else placed.get("outcome"),
                   reason=f"cancelled and re-placed: {placed.get('reason')}")
        return out

    def resolve_resting(self, client_order_id=None):
        """One step of the live resting orders' lifecycle, for every tick while one lives:
        at most ONE get_order_detail (and one cancel_order, plus -- after a fill found --
        the cancels of the rest of its group, sent in this same call). Order of work: a leg
        marked cancel_due (a sibling filled, a reconcile mismatch) gets its cancel and the
        lookup; else `client_order_id` when given and live (the stream printed through
        its level); else a leg whose ack needs a look (check_due); else the live leg
        checked longest ago. A fill is booked and queued (take_resting_events). A leg no
        lookup could settle for RESTING_ESCAPE_AFTER_SEC gets one get_order_open read
        (_settle_absent). Network calls run with the adapter lock let go. Returns
        {"checked": id or None, "status", "change", "live": ids still live} or None when
        OFF. Never raises."""
        try:
            mode, _ = self.effective_mode()
            if mode not in (MODE_PAPER, MODE_LIVE):
                return None
            with self._lock:
                live = self._live_resting()
                if not live:
                    return {"checked": None, "status": None, "change": 0, "live": []}
                rest = self._resting()
                due = [c for c in live if rest[c].get("cancel_due")]
                pick = (min(due, key=lambda c: float(rest[c].get("checked_at") or 0)) if due
                        else client_order_id if client_order_id in live
                        else next((c for c in live if rest[c].get("check_due")), None)
                        or min(live, key=lambda c: float(rest[c].get("checked_at") or 0)))
                client = self._client(mode)
                if client is None:
                    return {"checked": None, "status": None, "change": 0, "live": live}
                if rest[pick].get("cancel_due"):
                    self._send_cancel(client, pick)
                rest[pick].pop("check_due", None)
                acct = rest[pick].get("account_id")
            ans = self._lookup_order(client, acct, pick, detail=True)
            with self._lock:
                change = self._settle_resting(pick, ans, "resolve")
                if change:
                    self._cancel_siblings_now(client, pick)
                for c in self._settle_absent(client, [pick], "resolve"):
                    if int((self._resting().get(c) or {}).get("booked") or 0):
                        self._cancel_siblings_now(client, c)
                return {"checked": pick, "status": ans["status"] if ans else None,
                        "change": change, "live": self._live_resting()}
        except Exception as e:
            self.log(f"  [webull-orders] resolve_resting failed: {type(e).__name__}: {e}")
            return {"checked": None, "status": None, "change": 0, "live": [], "error": str(e)}

    def take_resting_events(self, lock_timeout=1.0):
        """Hand over (and clear) the resting fills booked since the last call: [{client_
        order_id, leg, trade_id, symbol, kind, group, combo_id, side, qty, status, filled
        (shares booked for that order now), change (this event's shares), filled_price,
        stop_price, limit_price, final, source, ts}]. [] if none or the lock is busy."""
        if not self._lock.acquire(timeout=lock_timeout):
            return []
        try:
            events = self._state.pop("resting_events", None) or []
            if events:
                self._save_state()
            return events
        finally:
            self._lock.release()

    def resting_orders(self, symbol=None, live_only=True, lock_timeout=None):
        """Copies of the resting records (see the section comment above), live ones only
        by default. No network. With `lock_timeout`, None when the lock stays busy that
        long (the caller cannot tell "nothing rests" from "not readable now"). Never
        raises ([] on any other problem)."""
        try:
            if not self._lock.acquire(timeout=-1 if lock_timeout is None else lock_timeout):
                return None
            try:
                want = str(symbol).upper() if symbol else None
                return [json.loads(json.dumps(r)) for r in self._resting().values()
                        if (not live_only or r.get("live"))
                        and (want is None or r.get("symbol") == want)]
            finally:
                self._lock.release()
        except Exception:
            return []

    def requeue_resting_events(self, events, lock_timeout=1.0):
        """Put events taken by take_resting_events back at the front of the queue (the
        caller could not book them). False when the lock stays busy. Never raises."""
        try:
            if not events:
                return True
            if not self._lock.acquire(timeout=lock_timeout):
                return False
            try:
                self._state["resting_events"] = (list(events)
                                                 + (self._state.get("resting_events") or []))
                self._save_state()
                return True
            finally:
                self._lock.release()
        except Exception:
            return False

    def open_orders(self, symbol=None, account_id=None):
        """Webull's open (working) orders -- get_order_open, paged -- as [{client_order_id,
        symbol, side, order_type, status, quantity, filled_quantity, stop_price,
        limit_price, combo_type}], narrowed to `symbol` when given; [] when OFF (nothing
        is asked); None when the read failed. Never raises."""
        try:
            mode, _ = self.effective_mode()
            if mode not in (MODE_PAPER, MODE_LIVE):
                return []
            client = self._client(mode)
            if client is None:
                return None
            account_id = account_id or self._account_id(mode, client)
            seen, out, last = set(), [], None
            for _ in range(OPEN_ORDERS_MAX_PAGES):
                page = _all_order_items(client.order_v3.get_order_open(
                    account_id, page_size=OPEN_ORDERS_PAGE_SIZE, last_client_order_id=last))
                for it in page:
                    coid = _field(it, "client_order_id", "clientOrderId")
                    if coid is None or coid in seen:
                        continue
                    seen.add(coid)
                    out.append({"client_order_id": str(coid),
                                "symbol": str(_field(it, "symbol", "ticker", default="")).upper(),
                                "side": _field(it, "side"), "order_type": _field(it, "order_type"),
                                "status": _norm_status(_field(it, "status", "order_status")),
                                "quantity": _field(it, "quantity", "qty"),
                                "filled_quantity": _field(it, "filled_quantity"),
                                "stop_price": _field(it, "stop_price"),
                                "limit_price": _field(it, "limit_price"),
                                "combo_type": _field(it, "combo_type")})
                if len(page) < OPEN_ORDERS_PAGE_SIZE or not page:
                    break
                last = _field(page[-1], "client_order_id", "clientOrderId")
                if not last:
                    break
            want = str(symbol).upper() if symbol else None
            return [o for o in out if (want is None or o["symbol"] == want)
                    and o["status"] not in RESTING_DEAD_STATUSES + ("FILLED",)]
        except Exception as e:
            self.log(f"  [webull-orders] open orders read failed: {type(e).__name__}: {e}")
            return None

    def boot_sweep(self, symbols=("QQQ",), cancel_unknown=True, budget_sec=RESTING_BOOT_BUDGET_SEC,
                   no_cancel_reason="this host does not hold the lease",
                   cancel_resting_pattern=False):
        """Process start, before the boot reconcile: (1) one lookup per live resting record
        -- a fill is booked (and queued as an event), a terminal one dropped from the live
        set, a live one kept for the caller's first tick to re-verify against its lot
        (level, quantity, side) and cancel on any doubt; (2) open_orders(): a record no
        lookup settles is settled by it (_settle_absent: a send that never landed, or one
        stuck unclear for RESTING_ESCAPE_AFTER_SEC), and every open order on `symbols`
        this state does not know (not a resting record, not an order part -- a crash
        between send and save, or another host's order) is -- with `cancel_unknown` --
        cancelled, looked up until terminal, and entries are HALTED (halt source
        "reconcile", so a later reconcile that agrees lifts it). cancel_unknown=False (this
        host does not hold the cross-host lease, or qqq_exec runs log_only -- the caller's
        `no_cancel_reason`) only lists them -- except, with `cancel_resting_pattern`, an
        unknown order whose id is a resting id (RESTING_ID_RE: certainly this book's stop,
        left by a stop-mode host that crashed without standing down, 2026-09-29 review): that
        one is cancelled (and entries halted) like any unknown order under cancel_unknown.
        A listed-only id is remembered (state["boot_listed"], BOOT_LISTED_KEEP_SEC) so the
        caller pushes it once, not at every restart (`unknown_new`). No lookup or poll starts
        after `budget_sec`. Returns {ok, resolved: {id: status}, live: [ids], unknown:
        [{client_order_id, symbol, side, order_type, status}], unknown_unresolved: [ids],
        unknown_cancelled: [ids], unknown_new: [ids listed only and not listed before],
        open_orders_read: bool, cancelled_unknown: bool, reason} for the caller's push, or
        None when OFF. Never raises."""
        try:
            mode, _ = self.effective_mode()
            if mode not in (MODE_PAPER, MODE_LIVE):
                return None
            deadline = time.time() + float(budget_sec)
            out = {"ok": True, "resolved": {}, "live": [], "unknown": [],
                   "unknown_unresolved": [], "unknown_cancelled": [], "unknown_new": [],
                   "open_orders_read": False, "cancelled_unknown": bool(cancel_unknown),
                   "reason": ""}
            client = self._client(mode)
            if client is None:
                out.update(ok=False, reason=f"no {mode} client")
                return out
            with self._lock:
                self._prune_resting()
                todo = [(c, self._resting()[c].get("account_id")) for c in self._live_resting()]
            for c, acct in todo:
                if time.time() >= deadline:
                    break
                ans = self._lookup_order(client, acct, c, detail=True)
                with self._lock:
                    if self._settle_resting(c, ans, "boot"):
                        self._cancel_siblings_now(client, c)
                    out["resolved"][c] = self._resting()[c].get("status") if ans else None
            opens = self.open_orders()
            if opens is not None:
                with self._lock:
                    for c in self._settle_absent(client, self._live_resting(), "boot", opens=opens):
                        out["resolved"][c] = self._resting()[c].get("status")
            with self._lock:
                out["live"] = self._live_resting()
            if opens is None:
                out.update(ok=False, reason="open orders could not be read")
                return out
            out["open_orders_read"] = True
            wanted = {str(s).upper() for s in symbols or ()}
            with self._lock:
                known = set(self._resting()) | set(self._parts())
            unknown = [o for o in opens if o["symbol"] in wanted and o["client_order_id"] not in known]
            if not unknown:
                return out
            for o in unknown:
                out["unknown"].append({k: o.get(k) for k in
                                       ("client_order_id", "symbol", "side", "order_type", "status")})
            ids_txt = ", ".join(o["client_order_id"] for o in unknown)
            to_cancel = unknown if cancel_unknown else (
                [o for o in unknown if RESTING_ID_RE.match(str(o["client_order_id"]))]
                if cancel_resting_pattern else [])
            listed_only = [o for o in unknown if o not in to_cancel]
            if listed_only:
                with self._lock:
                    now = time.time()
                    seen = {c: t for c, t in (self._state.get("boot_listed") or {}).items()
                            if now - float(t or 0) < BOOT_LISTED_KEEP_SEC}
                    out["unknown_new"] = [o["client_order_id"] for o in listed_only
                                          if o["client_order_id"] not in seen]
                    for o in listed_only:
                        seen.setdefault(o["client_order_id"], now)
                    if seen != (self._state.get("boot_listed") or {}):
                        self._state["boot_listed"] = seen
                        self._save_state()
            if not to_cancel:
                reason = (f"boot sweep: {len(unknown)} open {'/'.join(sorted(wanted))} order(s) "
                          f"this state did not know ({ids_txt}) -- NOT cancelled: "
                          f"{no_cancel_reason}")
                out.update(ok=False, cancelled_unknown=False, reason=reason)
                self.log(f"  [webull-orders] {reason}")
                return out
            out["cancelled_unknown"] = True
            out["unknown_cancelled"] = [o["client_order_id"] for o in to_cancel]
            ids_txt = ", ".join(out["unknown_cancelled"])
            account_id = self._account_id(mode, client)
            for o in to_cancel:
                coid = o["client_order_id"]
                if time.time() >= deadline:
                    out["unknown_unresolved"].append(coid)
                    continue
                try:
                    client.order_v3.cancel_order(account_id, coid)
                except Exception as e:
                    self.log(f"  [webull-orders] boot sweep: cancel of unknown {coid} raised "
                             f"{type(e).__name__}: {e}")
                ans = self._poll_order(client, account_id, coid, RESTING_CANCEL_TRIES,
                                       max(0.0, min(RESTING_GATEWAY_BUDGET_SEC, deadline - time.time())),
                                       lambda a: _terminal_qty(1, a["status"], a["filled"]) is not None,
                                       stop_at=deadline)
                if not ans or _terminal_qty(1, ans["status"], ans["filled"]) is None:
                    out["unknown_unresolved"].append(coid)
            with self._lock:
                reason = (f"boot sweep: {len(to_cancel)} open {'/'.join(sorted(wanted))} order(s) "
                          f"this state did not know were cancelled at Webull ({ids_txt})"
                          + (f"; NOT confirmed: {', '.join(out['unknown_unresolved'])}"
                             if out["unknown_unresolved"] else "")
                          + (f"; listed only ({no_cancel_reason}): "
                             f"{', '.join(o['client_order_id'] for o in listed_only)}"
                             if listed_only else "")
                          + " -- entries halted until a reconcile agrees")
                if self._halt_source != "kill_file":   # never mask the owner's kill file
                    self._halted = True
                    self._halt_reason = reason
                    self._halt_source = "reconcile"
                self._save_state()
            out.update(ok=False, reason=reason)
            self.log(f"  [webull-orders] ⚠ {reason}")
            return out
        except Exception as e:
            self.log(f"  [webull-orders] boot sweep failed: {type(e).__name__}: {e}")
            return {"ok": False, "resolved": {}, "live": [], "unknown": [],
                    "unknown_unresolved": [], "unknown_cancelled": [], "unknown_new": [],
                    "open_orders_read": False,
                    "cancelled_unknown": bool(cancel_unknown),
                    "reason": f"{type(e).__name__}: {e}"}

    def _resolve_resting_pass(self, client, started):
        """reconcile()'s resting pass, FIRST and on its own budget (2026-09-29 second
        review: it used to follow the PENDING pass and share its time): up to
        RESTING_RECONCILE_LOOKUPS lookups of live resting legs (a cancel_due leg gets its
        cancel first), none started after RECONCILE_PENDING_BUDGET_SEC from `started`; a
        fill found sends the cancels of the rest of its group. Returns the ids Webull gave
        a clear answer for (working, FILLED or dead). Never raises."""
        seen = set()
        try:
            with self._lock:
                rest = self._resting()
                todo = sorted(((not rest[c].get("cancel_due"), float(rest[c].get("checked_at") or 0),
                                c, rest[c].get("account_id")) for c in self._live_resting()))
            for _, _, coid, acct in todo[:RESTING_RECONCILE_LOOKUPS]:
                if time.time() - started >= RECONCILE_PENDING_BUDGET_SEC:
                    break
                with self._lock:
                    if (self._resting().get(coid) or {}).get("cancel_due"):
                        self._send_cancel(client, coid)
                ans = self._lookup_order(client, acct, coid, detail=True)
                with self._lock:
                    if self._settle_resting(coid, ans, "reconcile"):
                        self._cancel_siblings_now(client, coid)
                    if ans and ans.get("status") != "NOT_FOUND":
                        seen.add(coid)
        except Exception as e:
            self.log(f"  [webull-orders] resting pass failed: {type(e).__name__}: {e}")
        return seen

    # -- public: stock/ETF orders --
    def place_stock_order(self, *, leg, signal_id, symbol, side, qty, intent="OPEN",
                          order_type="MARKET", limit_price=None, tif="DAY",
                          extended_hours=False, market="US", account_id=None,
                          instrument_id=None, remainder=False):
        """Idempotent on signal_id. Returns a record dict always (never raises for a
        blocked/no-op/OFF path -- only an unexpected SDK exception in PAPER/LIVE is
        caught and reported via record["error"], never propagated).

        Validates side/order_type/tif against the local ORDER_SIDES/ORDER_TYPES/
        ORDER_TIFS mirrors (see their module-level comment) rather than importing the
        SDK's enums here -- this runs on EVERY call, including OFF mode, so it must
        never be the thing that imports webull.

        ORDER NETTING (2026-09-24, PAPER/LIVE only -- see the module docstring's ORDER
        NETTING section): `side`/`qty` describe what THIS LEG wants, not necessarily
        what gets sent -- the actual broker order(s) are planned from the ACCOUNT's
        current net position for `symbol` (_account_net / _plan_broker_parts), because
        Webull holds one position per symbol shared by every leg. One call here is
        always ONE record, whatever that plan takes to execute: `record["parts"]` is a
        list of {side, qty, client_order_id, ok, sent, reason, response}, one per
        broker order actually attempted (length 1 for the common, non-colliding case --
        same client_order_id as always, see _part_client_order_id). `record["ok"]` is
        True only when EVERY part was accepted; a partial (some parts ok, some refused)
        sets `record["partial"] = True` and still moves broker_sent_positions/
        believed_positions by exactly the ACCEPTED parts, never the refused ones --
        never gated on the call's overall ok. `record["side"]`/`record["qty"]` keep
        their existing meaning (the leg's own request), even when the actual part(s)
        used a different broker-facing side (e.g. a leg's own "SELL" sent as SHORT
        because the account was already flat) -- read `record["parts"]` for what
        actually happened at the broker.

        NEVER GUESSES (2026-09-26, see UNKNOWN_LOOKUP_TRIES): an unclear part carries
        outcome "UNKNOWN" (so does the record). A split's later part goes only once the
        earlier one reports FILLED; otherwise it (or one refused with a 4xx) is listed
        in record["unsent_parts"] and kept in `parts` with sent=False. `remainder=True`
        re-sends a split OPEN's rest (the one-open-position rail allows it).

        GATEWAY (2026-09-29, see RESTING ORDERS AND THE ORDER GATEWAY): in PAPER/LIVE,
        after the rails and before planning, every live resting order on `symbol` is
        cancelled and confirmed terminal (a fill it had is booked first), and -- with
        cfg["gateway"]["prev_terminal"] -- an earlier part still working at Webull is
        waited for. When either cannot be settled inside RESTING_GATEWAY_BUDGET_SEC
        nothing is sent: ok=False, sent=False, busy=True, outcome "RESTING_UNRESOLVED"
        or "NOT_SENT" (the caller re-queues it: a CLOSE through close_retry, an OPEN as
        "busy"). A CLOSE whose leg the gateway (or an earlier resting fill) already
        closed at Webull sends nothing and returns ok=True, sent=False,
        closed_by_resting={client_order_id, kind, filled, filled_price, trade_id}. With
        no resting order recorded and prev_terminal off, none of this runs."""
        with self._sends_lock:
            self._stock_sends += 1
        try:
            return self._place_stock_order(
                leg=leg, signal_id=signal_id, symbol=symbol, side=side, qty=qty,
                intent=intent, order_type=order_type, limit_price=limit_price, tif=tif,
                extended_hours=extended_hours, market=market, account_id=account_id,
                instrument_id=instrument_id, remainder=remainder)
        finally:
            with self._sends_lock:
                self._stock_sends -= 1

    def _place_stock_order(self, *, leg, signal_id, symbol, side, qty, intent, order_type,
                           limit_price, tif, extended_hours, market, account_id,
                           instrument_id, remainder):
        """place_stock_order's body (see its docstring)."""
        side = str(side).upper()
        intent = str(intent).upper()
        order_type = str(order_type).upper()
        tif = str(tif).upper()
        if side not in ORDER_SIDES:
            raise ValueError(f"side must be one of {ORDER_SIDES}, got {side!r}")
        if order_type not in ORDER_TYPES:
            raise ValueError(f"order_type must be one of {ORDER_TYPES}, got {order_type!r}")
        if tif not in ORDER_TIFS:
            raise ValueError(f"tif must be one of {ORDER_TIFS}, got {tif!r}")
        if intent not in ("OPEN", "CLOSE"):
            raise ValueError(f"intent must be OPEN or CLOSE, got {intent!r}")

        send_started = time.time()   # SEND_LOOKUP_BUDGET_SEC counts from here (lock wait too)
        with self._lock:
            coid = _sanitize_client_order_id(signal_id)
            cached = (self._state.get("orders") or {}).get(coid)
            if cached is not None:
                self.log(f"  [webull-orders] duplicate signal {signal_id!r} -> "
                         f"client_order_id {coid} already recorded (mode={cached.get('mode')}); "
                         "not sending again")
                out = dict(cached)
                out["duplicate"] = True
                return out

            record = {"signal_id": signal_id, "leg": leg, "symbol": symbol, "side": side,
                      "qty": qty, "intent": intent, "order_type": order_type,
                      "limit_price": limit_price, "tif": tif, "client_order_id": coid,
                      "ts": time.time()}

            ok, reason = self._check_rails(leg, qty, intent, remainder=remainder)
            if not ok:
                record.update(mode="BLOCKED", ok=False, sent=False, reason=reason)
                self._record_order(coid, record)
                self._last_error = reason
                self.log(f"  [webull-orders] BLOCKED {symbol} {side} {qty} (leg {leg}): {reason}")
                return record

            mode, mode_reason = self.effective_mode()
            record["mode"] = mode

            if mode == MODE_OFF:
                record.update(ok=True, sent=False, reason=mode_reason)
                self._record_order(coid, record)
                self._apply_intent_to_belief(leg, symbol, side, qty, intent)
                self._last_order = record
                self.log(f"  [webull-orders] OFF -- recorded would-be order {symbol} {side} "
                         f"{qty} (leg {leg}, signal {signal_id}); nothing sent ({mode_reason})")
                return record

            # GATEWAY (2026-09-29): cancel-first, then previous-order-terminal -- see the
            # module comment RESTING ORDERS AND THE ORDER GATEWAY. Runs before the
            # nothing-to-close check so a resting fill it finds is booked first.
            if self._live_resting(symbol) or self._prev_terminal_on():
                held_back = self._order_gateway(mode, symbol, send_started, leg=leg,
                                                intent=intent)
                if held_back is not None:
                    record.update(mode=mode, ok=False, sent=False, busy=True, **held_back)
                    self._record_order(coid, record)
                    self._last_error = record["reason"]
                    self.log(f"  [webull-orders] NOT SENT {symbol} {side} {qty} (leg {leg}): "
                             f"{record['reason']}")
                    return record

            # NOTHING TO CLOSE (2026-09-21). A CLOSE goes to the broker only for shares
            # THIS adapter actually put there for this leg (broker_sent_positions, the
            # same book reconcile() trusts). On 2026-09-21 NOISE's buy was BLOCKED by a
            # reconcile halt while the shadow book still opened the lot, so when the book
            # later closed it the old code would have sent SELL 10 QQQ for shares Webull
            # never held -- a CLOSE skips every rail on purpose ("never trap a position"),
            # so nothing stood in the way. On the cash account that is refused at best;
            # wherever shorting is allowed it opens a short nobody tracks. A CLOSE larger
            # than what was sent is clamped to it for the same reason.
            if intent == "CLOSE":
                held = float(((self._state.get("broker_sent_positions") or {}).get(leg) or {})
                             .get("qty", 0) or 0)
                closes_long = side == "SELL"
                closed = (None if (closes_long and held > 1e-9) or (not closes_long and held < -1e-9)
                          else self._closed_by_resting(leg, coid))
                if closed:
                    # RESTING ORDERS (2026-09-29): the leg's resting stop/target already
                    # closed it at Webull -- nothing to send, and nothing went wrong.
                    record.update(mode=mode, ok=True, sent=False, closed_by_resting=closed,
                                  reason=f"already closed at Webull by the resting "
                                         f"{closed['kind']} {closed['client_order_id']} -- "
                                         f"no market close sent")
                    self._record_order(coid, record)
                    self._last_order = record
                    self.log(f"  [webull-orders] {symbol} {side} {qty} (leg {leg}): {record['reason']}")
                    return record
                if not ((closes_long and held > 1e-9) or (not closes_long and held < -1e-9)):
                    reason = (f"nothing to close at the broker for leg {leg!r}: no position "
                              f"this adapter sent is held there (sent qty {held:g}) -- its OPEN "
                              f"was blocked or failed, so this {side} would only open a new "
                              f"position")
                    record.update(mode="BLOCKED", ok=False, sent=False, reason=reason,
                                  nothing_to_close=True)
                    self._record_order(coid, record)
                    self._last_error = reason
                    self.log(f"  [webull-orders] NOT SENT {symbol} {side} {qty} (leg {leg}): {reason}")
                    return record
                if qty > abs(held) + 1e-9:
                    self.log(f"  [webull-orders] CLOSE {symbol} {side} {qty} (leg {leg}) clamped "
                             f"to {abs(held):g} -- only that much of this leg reached the broker")
                    record["qty_requested"] = qty
                    qty = int(round(abs(held)))
                    record["qty"] = qty

            client = self._client(mode)
            if client is None:
                record.update(ok=False, sent=False, reason=f"no {mode} client ({mode_reason})")
                self._record_order(coid, record)
                self._last_error = record["reason"]
                self.log(f"  [webull-orders] {mode} requested but no client -- {record['reason']}")
                return record

            try:
                account_id = account_id or self._account_id(mode, client)

                # ORDER NETTING (2026-09-24): plan the REAL broker order(s) for this
                # request from the account's current net position, not the leg's own
                # literal side -- see the module docstring's ORDER NETTING section and
                # _plan_broker_parts. direction collapses SELL/SHORT (both push the
                # account toward more negative) onto "SELL", and BUY (which always
                # pushes toward more positive, whether opening long or covering a
                # short) onto "BUY" -- see _plan_broker_parts for why that collapse is
                # exactly what Webull's single shared position needs.
                net_before = self._account_net(symbol, account_id)
                direction = "BUY" if side == "BUY" else "SELL"
                parts_plan = _plan_broker_parts(net_before, direction, qty)
                if not parts_plan:
                    # qty rounded to <= 0 (should not happen -- every real caller
                    # guards qty > 0 upstream; see api/qqq_exec.py's _mirror_to_broker)
                    # -- degrade to the pre-netting shape rather than sending nothing
                    # silently and calling it ok.
                    parts_plan = [(side, int(round(qty)))]

                # a crash from here on must never re-send this signal: cache UNKNOWN first
                self._prune_parts()
                self._record_order(coid, dict(record, ok=False, sent=True, outcome="UNKNOWN",
                                              reason="send in progress (process stopped mid-send?)"))
                parts = []
                stop_at = send_started + SEND_LOOKUP_BUDGET_SEC   # lookups AND later parts
                for i, (part_side, part_qty) in enumerate(parts_plan, start=1):
                    part_coid = _part_client_order_id(coid, i, len(parts_plan))
                    held = None
                    if parts and not self._part_filled(client, account_id, parts[-1], stop_at):
                        # SPLIT SEQUENCING: the rest assumes the earlier part went through.
                        held = f"part {i - 1} was not confirmed FILLED"
                    elif parts and time.time() >= stop_at:
                        # a late part 2 could run past qqq_exec's hard timeout (recorded
                        # under the base id a split never used): hand it back instead
                        held = f"the send's {SEND_LOOKUP_BUDGET_SEC:g} s budget ran out"
                    if held:
                        parts.append({"side": part_side, "qty": part_qty,
                                      "client_order_id": part_coid, "ok": False, "sent": False,
                                      "outcome": "NOT_SENT", "response": None,
                                      "reason": f"not sent: {held} -- returned for re-send"})
                        self.log(f"  [webull-orders] {mode} {symbol} {part_side} {part_qty} "
                                 f"(leg {leg}, part {i}/{len(parts_plan)}) NOT SENT: {held}")
                        continue
                    # v3 order dict (see module docstring, ORDER API VERSION): symbol-keyed,
                    # no instrument_id lookup needed. quantity/limit_price go over as
                    # STRINGS per the documented getting-started sample.
                    new_order = {
                        "combo_type": "NORMAL", "client_order_id": part_coid, "symbol": symbol,
                        "instrument_type": "EQUITY", "market": market, "order_type": order_type,
                        "quantity": str(part_qty), "support_trading_session": "CORE",
                        "side": part_side, "time_in_force": tif, "entrust_type": "QTY",
                    }
                    if order_type in ("LIMIT", "STOP_LOSS_LIMIT", "ENHANCED_LIMIT",
                                      "AT_AUCTION_LIMIT") and limit_price is not None:
                        new_order["limit_price"] = str(limit_price)
                    # books move per ACCEPTED part, inside _send_part (see _apply_intent_to_sent)
                    parts.append(self._send_part(
                        client, account_id, mode, leg, symbol, intent, part_side, part_qty,
                        part_coid, new_order,
                        f", part {i}/{len(parts_plan)}" if len(parts_plan) > 1 else "",
                        stop_at=stop_at))

                all_ok = all(p["ok"] for p in parts)
                record.update(ok=all_ok, sent=True, account_id=account_id, parts=parts)
                # a split's held-back parts, any Webull refused outright (4xx), and the
                # unfilled rest of one Webull killed (dead with a known filled qty)
                unsent = [{"side": p["side"], "client_order_id": p["client_order_id"],
                           "qty": p["qty"] - (int(round(p["filled"]))
                                              if p.get("outcome") in DEAD_STATUSES else 0)}
                          for p in parts if len(parts) > 1 and not p["ok"] and (
                              p.get("outcome") in (None, "NOT_SENT")
                              or (p.get("outcome") in DEAD_STATUSES
                                  and p.get("filled") is not None))]
                unsent = [u for u in unsent if u["qty"] > 0]
                if unsent:
                    record["unsent_parts"] = unsent
                if any(p.get("outcome") == "UNKNOWN" for p in parts):
                    record["outcome"] = "UNKNOWN"
                if not all_ok:
                    # Keep the status panel's "last error" honest: before netting, a failed
                    # place_order raised into the outer except below, which set _last_error;
                    # each part now catches its own failure, so record it here instead.
                    self._last_error = next((p["reason"] for p in parts if not p["ok"]), None)
                if len(parts) == 1:
                    # Exactly today's shape when there was nothing to net against.
                    record["response"] = parts[0]["response"]
                    if not all_ok:
                        record["error"] = parts[0]["reason"]
                        record["http_status"] = parts[0].get("http_status")
                else:
                    accepted_qty = sum(p["qty"] for p in parts if p["ok"])
                    detail = "; ".join(
                        f"{p['side']} {p['qty']}" + ("" if p["ok"] else f" REFUSED ({p['reason']})")
                        for p in parts)
                    record["reason"] = (f"netted against account position {net_before:g}: split "
                                        f"into {len(parts)} broker orders ({detail})")
                    if all_ok:
                        self.log(f"  [webull-orders] {mode} {symbol} {direction}-direction "
                                 f"{qty} (leg {leg}) split on account net {net_before:g}: {detail}")
                    else:
                        record["partial"] = accepted_qty > 0
                        self.log(f"  [webull-orders] {mode} PARTIAL for {symbol} (leg {leg}, "
                                 f"intent {intent}): {record['reason']}")
            except Exception as e:
                record.update(ok=False, sent=True, error=f"{type(e).__name__}: {e}")
                self._last_error = record["error"]
                self.log(f"  [webull-orders] {mode} place_order FAILED for {symbol} "
                         f"{side} {qty} (leg {leg}): {record['error']}")

            self._record_order(coid, record)
            self._last_order = record
            return record

    def preview_stock_order(self, *, symbol, side, qty, order_type="MARKET",
                            limit_price=None, market="US", account_id=None,
                            instrument_id=None):
        """Preview only exists against a live SDK client -- OFF has nothing to preview."""
        mode, reason = self.effective_mode()
        if mode not in (MODE_PAPER, MODE_LIVE):
            return {"ok": False, "reason": f"preview needs PAPER or LIVE (mode={mode}): {reason}"}
        client = self._client(mode)
        if client is None:
            return {"ok": False, "reason": f"no {mode} client"}
        try:
            account_id = account_id or self._account_id(mode, client)
            order = {"combo_type": "NORMAL", "symbol": symbol, "instrument_type": "EQUITY",
                    "market": market, "order_type": str(order_type).upper(),
                    "quantity": str(qty), "support_trading_session": "CORE",
                    "side": str(side).upper(), "time_in_force": "DAY", "entrust_type": "QTY"}
            if limit_price is not None:
                order["limit_price"] = str(limit_price)
            resp = client.order_v3.preview_order(account_id, [order])
            return {"ok": True, "mode": mode, "response": _safe_response(resp)}
        except Exception as e:
            return {"ok": False, "mode": mode, "reason": f"{type(e).__name__}: {e}"}

    def cancel_order(self, signal_id, account_id=None):
        coid = _sanitize_client_order_id(signal_id)
        mode, reason = self.effective_mode()
        if mode not in (MODE_PAPER, MODE_LIVE):
            return {"ok": False, "reason": f"cancel needs PAPER or LIVE (mode={mode}): {reason}"}
        client = self._client(mode)
        if client is None:
            return {"ok": False, "reason": f"no {mode} client"}
        try:
            account_id = account_id or self._account_id(mode, client)
            resp = client.order_v3.cancel_order(account_id, coid)
            return {"ok": True, "mode": mode, "response": _safe_response(resp)}
        except Exception as e:
            return {"ok": False, "mode": mode, "reason": f"{type(e).__name__}: {e}"}

    def order_status(self, signal_id, account_id=None):
        coid = _sanitize_client_order_id(signal_id)
        cached = (self._state.get("orders") or {}).get(coid)
        mode, reason = self.effective_mode()
        # client_order_id is always included below (added 2026-09-14) so a caller can
        # match the right entry inside a v3 response's orders[] -- see
        # order_status_fields() -- without having to re-derive coid itself.
        if mode not in (MODE_PAPER, MODE_LIVE):
            return cached or {"ok": False, "reason": f"no live query (mode={mode}): {reason}",
                              "client_order_id": coid}
        client = self._client(mode)
        if client is None:
            return cached or {"ok": False, "reason": f"no {mode} client", "client_order_id": coid}
        try:
            account_id = account_id or self._account_id(mode, client)
            resp = client.order_v3.get_order_detail(account_id, coid)
            return {"ok": True, "mode": mode, "response": _safe_response(resp), "cached": cached,
                   "client_order_id": coid}
        except Exception as e:
            return {"ok": False, "mode": mode, "reason": f"{type(e).__name__}: {e}",
                   "cached": cached, "client_order_id": coid}

    def positions(self, account_id=None):
        """{"believed": {...}, "broker": {...}|None, "mode": ...}. "believed" always
        comes from this adapter's own order history; "broker" is only populated when
        a live client can be built (PAPER/LIVE with credentials present)."""
        mode, _ = self.effective_mode()
        out = {"believed": self._state.get("believed_positions", {}), "broker": None, "mode": mode}
        client = self._client(mode) if mode in (MODE_PAPER, MODE_LIVE) else None
        if client is None:
            return out
        try:
            account_id = account_id or self._account_id(mode, client)
            resp = client.account_v2.get_account_position(account_id)
            out["broker"] = _positions_from_response(resp)
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
        return out

    def fail_closed(self, reason):
        """Shared fail-closed bookkeeping for "the broker position read could not be
        completed" -- called by reconcile()'s own except-branch below AND by an
        external hard-timeout wrapper (api/qqq_exec.py's _reconcile_with_timeout,
        which bounds the whole reconcile() call to a wall-clock limit the same way
        default_webull_quote bounds a quote call -- see that module's 2026-09-03
        postmortem on SDK timeouts not always being honoured). Halts new broker
        entries (CLOSE intents still pass, see _check_rails) until a LATER reconcile
        actually succeeds -- never raises."""
        with self._lock:
            now = time.time()
            self._halted = True
            self._halt_reason = reason
            self._halt_source = "reconcile"
            result = {"ok": False, "error": reason, "checked_at": now}
            self._state["last_reconcile_at"] = now
            self._state["last_reconcile_result"] = result
            self._save_state()
            self.log(f"  [webull-orders] RECONCILE READ FAILED -- halting new broker "
                     f"entries: {reason}")
            return result

    def reconcile(self, account_id=None, broker_positions_fn=None, resolve_pending=True):
        """Compare the broker's live position (PAPER/LIVE only) against the sum of
        THIS adapter's own lots that actually reached the broker with a successful ack
        -- broker_sent_positions, NOT believed_positions (which also absorbs OFF-mode
        would-be orders: comparing against that would false-positive the instant the
        config flips from OFF to PAPER/LIVE with any OFF-era belief still on record).

        FAIL-CLOSED (2026-09-14): a read failure (network error, timeout, no client)
        while mode is PAPER/LIVE is no longer treated as "nothing to report" -- it
        HALTS new broker entries via fail_closed() above, exactly like a genuine
        mismatch, because an unattended trial cannot tell "Webull is fine, no
        discrepancy" apart from "Webull could not be asked" unless both failure modes
        are treated the same way: assume the worse case and stop opening new real
        positions until a later reconcile actually succeeds. CLOSE intents always
        still pass (see _check_rails' unconditional CLOSE bypass) so a halt here can
        never trap the strategy in a position it cannot exit.

        RECOVERY: a subsequent reconcile() that both reads successfully AND matches
        clears the halt -- but ONLY when this adapter itself raised it (halt_source
        == "reconcile"); a kill-file halt is left completely alone.

        Returns None when there's no broker to reconcile against at all (OFF mode) --
        that is a legitimate no-network no-op, not a failure, see the OFF-mode test.

        `resolve_pending=False` skips the PENDING pass (qqq_exec does, while its own order
        lookups are timing out) so a slow lookup never eats the positions read's time.

        RESTING ORDERS (2026-09-29; second review): the resting pass runs FIRST, on its own
        budget, so a stop that filled since the last look is booked before the positions
        are compared. With resolve_pending=False it makes no lookup; a difference that a
        live resting order's own unbooked fill would explain, while that order had no clear
        answer in this pass, is then UNDECIDED (result "undecided": True, no halt either way,
        the order due a lookup) -- at most RECONCILE_UNDECIDED_MAX reconciles in a row, then
        it halts like any mismatch. A record settled by the stuck-record escape keeps
        re-arming blocked until one get_order_open read here still does not list it (one
        that it lists is live again, and due a cancel)."""
        mode, _ = self.effective_mode()
        if mode not in (MODE_PAPER, MODE_LIVE):
            return None
        seen, absent_open = set(), None
        try:
            if broker_positions_fn is not None:
                broker = broker_positions_fn()
            else:
                client = self._client(mode)
                if client is None:
                    return None
                account_id = account_id or self._account_id(mode, client)
                if resolve_pending and self._live_resting():
                    seen = self._resolve_resting_pass(client, time.time())
                # leftover PENDING parts next, so a fill Webull shows is compared too
                if resolve_pending:
                    self._resolve_pending(client)
                if self._state.get("resting_absent"):
                    absent_open = self.open_orders(account_id=account_id)
                broker = _positions_from_response(client.account_v2.get_account_position(account_id))
        except Exception as e:
            return self.fail_closed(f"can't read positions at Webull: {type(e).__name__}: {e}")

        with self._lock:
            sent_raw = self._state.get("broker_sent_positions", {})
            sent = {}
            for leg, p in sent_raw.items():
                # Per-account (2026-09-14): a lot sent under a DIFFERENT account_id
                # than the one this reconcile call just fetched positions for (e.g. a
                # stale entry from before an account reset) must never be folded into
                # THIS account's comparison.
                if account_id is not None and p.get("account_id") not in (None, account_id):
                    continue
                sym = str(p.get("symbol", "")).upper()
                if not sym:
                    continue
                sent[sym] = sent.get(sym, 0.0) + float(p.get("qty", 0) or 0)

            syms = set(broker) | set(sent)
            mismatches = [{"symbol": s, "broker": broker.get(s, 0.0), "shadow_sent": sent.get(s, 0.0)}
                         for s in sorted(syms) if abs(broker.get(s, 0.0) - sent.get(s, 0.0)) > 1e-6]
            ok = not mismatches
            now = time.time()
            self._recheck_absent(absent_open)
            undecided = self._reconcile_undecided(mismatches, seen, account_id) if not ok else None
            if undecided:
                n = int(self._state.get("reconcile_undecided_n") or 0) + 1
                self._state["reconcile_undecided_n"] = n
                self.log(f"  [webull-orders] reconcile UNDECIDED ({n} of "
                         f"{RECONCILE_UNDECIDED_MAX}): {undecided} -- looked up before any halt")
                result = {"ok": False, "undecided": True, "reason": undecided,
                          "mismatches": mismatches, "broker": broker, "shadow_sent": sent,
                          "account_id": account_id, "checked_at": now}
                # last_reconcile_result keeps the last real verdict (the web tab reads it)
                self._state["last_reconcile_undecided"] = result
                self._save_state()
                return result
            self._state.pop("reconcile_undecided_n", None)
            self._state.pop("last_reconcile_undecided", None)
            if not ok:
                reason = "reconcile mismatch vs Webull: " + "; ".join(
                    f"{m['symbol']} broker={m['broker']:g} shadow_sent={m['shadow_sent']:g}"
                    for m in mismatches)
                self._halted = True
                self._halt_reason = reason
                self._halt_source = "reconcile"
                self.log(f"  [webull-orders] \u26a0 RECONCILE MISMATCH -- halting new "
                         f"entries: {reason}")
            elif self._halt_source == "reconcile":
                self._halted = False
                self._halt_reason = None
                self._halt_source = None
                self.log("  [webull-orders] reconcile OK -- broker halt cleared")
            # RESTING ORDERS (2026-09-29): a real mismatch means the books are wrong, and
            # so is any resting order sized from them -- every one is marked cancel_due
            # (sent and confirmed by the next resolve_resting / gateway, never from here:
            # no network call under the lock) and re-arming is blocked until a reconcile
            # agrees again.
            cancel_now = self._live_resting() if not ok else []
            if cancel_now:
                self._state["resting_blocked"] = reason
                for c in cancel_now:
                    self._resting()[c]["cancel_due"] = True
                self.log(f"  [webull-orders] RECONCILE MISMATCH with resting order(s) live -- "
                         f"cancelling {', '.join(cancel_now)}; no re-arm until a reconcile agrees")
            elif ok and "resting_blocked" in self._state and not self._state.get("resting_absent"):
                self._state.pop("resting_blocked", None)
                self.log("  [webull-orders] reconcile OK -- resting orders may re-arm")
            result = {"ok": ok, "mismatches": mismatches, "broker": broker,
                     "shadow_sent": sent, "account_id": account_id, "checked_at": now}
            self._state["last_reconcile_at"] = now
            self._state["last_reconcile_result"] = result
            self._save_state()
            return result

    def _recheck_absent(self, opens):
        """reconcile()'s second look at the records the stuck-record escape settled
        (state["resting_absent"]): `opens` is one get_order_open read (None: not read or
        failed -> they stay, and re-arming stays blocked). Still not listed -> dropped; listed
        and working -> the record is live again (its fill so far booked) and due a cancel,
        so the gateway / next resolve takes it down before anything else is placed. Caller
        holds the lock."""
        absent = self._state.get("resting_absent") or {}
        if not absent or opens is None:
            return
        listed = {o.get("client_order_id"): o for o in opens}
        for c in list(absent):
            rec = self._resting().get(c)
            o = listed.get(c)
            st = _norm_status((o or {}).get("status"))
            if rec is not None and st in LIVE_STATUSES:
                was = rec.get("status")
                rec.update(live=True, acked=True, pending=False, cancel_due=True, status=st)
                for k in ("final_status", "settled_at", "unclear_since", "unclear_n",
                          "absent_checked_at"):
                    rec.pop(k, None)
                (self._parts().get(c) or {}).pop("final_status", None)
                self._settle_resting(c, {"status": st, "filled": _to_qty(
                    o.get("filled_quantity")), "price": None}, "reconcile")
                self.log(f"  [webull-orders] \u26a0 RESTING {c} settled {was} earlier IS still "
                         f"working at Webull -- live again, cancel due")
            absent.pop(c, None)
        if not absent:
            self._state.pop("resting_absent", None)
        self._save_state()

    def _reconcile_undecided(self, mismatches, seen, account_id):
        """The reason a positions difference is UNDECIDED rather than a mismatch (see
        reconcile), else None: every mismatched symbol has a live resting record with no
        clear lookup in this pass (`seen`) whose unbooked remainder, on its side's sign,
        covers the difference -- and fewer than RECONCILE_UNDECIDED_MAX reconciles in a row
        were undecided. Those records are marked check_due. Caller holds the lock."""
        if int(self._state.get("reconcile_undecided_n") or 0) >= RECONCILE_UNDECIDED_MAX:
            return None
        due, why = [], []
        for m in mismatches:
            recs = [(c, self._resting()[c]) for c in self._live_resting(m["symbol"])
                    if account_id is None
                    or self._resting()[c].get("account_id") in (None, account_id)]
            unseen = [c for c, _r in recs if c not in seen]
            if not unseen:
                return None
            diff = float(m["broker"]) - float(m["shadow_sent"])
            sides = {1 if r.get("side") == "BUY" else -1 for _c, r in recs}
            left = sum(int(r.get("qty") or 0) - int(r.get("booked") or 0) for _c, r in recs)
            if len(sides) != 1 or diff * sides.pop() <= 0 or abs(diff) > left + 1e-6:
                return None
            due.extend(unseen)
            why.append(f"{m['symbol']} broker={m['broker']:g} vs books {m['shadow_sent']:g}, "
                       f"within what resting {', '.join(unseen)} could have filled")
        for c in due:
            self._resting()[c]["check_due"] = True
        return "; ".join(why) or None

    # -- futures: staged, hard-disabled --
    def resolve_futures_contract(self, product_symbol, market="US"):
        """Would resolve `product_symbol` (e.g. 'MNQ') to its current front-month
        instrument via webull.data.quotes.instrument.Instrument.get_futures_products /
        get_futures_instrument(category='US_FUTURES') on a market-data client. Not
        wired -- raises unconditionally. See FUTURES_NOT_ENABLED / module docstring."""
        raise NotImplementedError(FUTURES_NOT_ENABLED)

    def place_futures_order(self, *args, **kwargs):
        raise NotImplementedError(FUTURES_NOT_ENABLED)

    def halt_state(self):
        """(halted, halt_source, halt_reason) -- no disk or network read, so a per-tick
        caller can ask every 5 s (api/qqq_exec.py: how soon to look at Webull again while
        halted, and whether an OPEN a halt blocked may be re-sent). halt_source is
        "reconcile" for this adapter's own mismatch / read-failure halt (it clears itself
        on a later matching reconcile) and "kill_file" for the owner's kill file."""
        return self._halted, self._halt_source, self._halt_reason

    # -- account equity, for the web tab's live positions/equity card (2026-09-23,
    # api/qqq_exec.py item 3 -- "since we are live with live pricing, can you show the
    # positions live? and potentially equity as well"). READ ONLY: no order, no state
    # mutation, no _save_state -- a pure account_v2.get_account_balance(account_id)
    # call against the SAME account THIS adapter already resolves/trades through for
    # "stock" (_account_id, DEFAULT_ACCOUNT_SELECT -- the paper MARGIN account since
    # 2026-09-23), via the identical account_v2.get_account_balance call
    # api/webull_sync.py's own fetch_balance uses for its separate, summed-across-every-
    # stock-account figure (a different, broader read for the journal's "Webull" pill,
    # unaffected by this addition).
    def get_stock_account_balance(self):
        """{account_id, net_liq, cash} for the stock-purpose account, or None if the
        adapter is OFF, has no client, or the call fails -- a read-only balance probe
        called every ~60s from a live tick loop must never raise into its caller."""
        try:
            mode, _reason = self.effective_mode()
            if mode not in (MODE_PAPER, MODE_LIVE):
                return None
            client = self._client(mode)
            if client is None:
                return None
            account_id = self._account_id(mode, client, purpose="stock")
            b = _safe_response(client.account_v2.get_account_balance(account_id))
            net_liq = _field(b, "total_net_liquidation_value", "net_liquidation",
                             "netLiquidation", default=None)
            cash = _field(b, "total_cash_balance", "cash_balance", "cashBalance", default=None)
            return {"account_id": account_id,
                   "net_liq": float(net_liq) if net_liq is not None else None,
                   "cash": float(cash) if cash is not None else None}
        except Exception as e:
            self.log(f"  [webull-orders] account balance read failed: {type(e).__name__}: {e}")
            return None

    # -- status, for the web tab (a function, not a UI edit) --
    def status(self):
        mode, reason = self.effective_mode()
        rails = self.cfg.get("rails") or DEFAULT_RAILS
        out = self._status_core(mode, reason, rails)
        # RESTING ORDERS (2026-09-29) -- only once there has been one, so the dict is
        # unchanged for a book that never rests an order
        if self._state.get("resting") or self._state.get("resting_blocked"):
            out["resting_live"] = [
                {k: r.get(k) for k in ("client_order_id", "leg", "trade_id", "kind", "group",
                                       "side", "qty", "stop_price", "limit_price", "status")}
                for r in self._resting().values() if r.get("live")]
            out["resting_blocked"] = self._state.get("resting_blocked")
        return out

    def _status_core(self, mode, reason, rails):
        return {
            "requested_mode": self.requested_mode(),
            "effective_mode": mode,
            "mode_reason": reason,
            "environment": "sandbox" if mode == MODE_PAPER else ("production" if mode == MODE_LIVE else None),
            "paper_credentials_present": bool(load_paper_keys(self._paper_keys_path())),
            "live_credentials_present": bool(load_live_keys(self._live_keys_path())),
            "live_armed": os.path.exists(self._arm_file()),
            "kill_file_present": os.path.exists(self._kill_file()),
            "halted": self._halted,
            "halt_reason": self._halt_reason,
            "last_order": self._last_order,
            "last_error": self._last_error,
            "daily_pnl": self._state.get("daily_pnl", 0.0),
            "open_legs": sorted((self._state.get("open_legs") or {}).keys()),
            "believed_positions": self._state.get("believed_positions", {}),
            "futures_enabled": bool(self.cfg.get("futures_enabled", False)),
            "rails": rails,
            # RECONCILE HARDENING (2026-09-14) -- new, additive fields only:
            "halt_source": self._halt_source,
            "last_reconcile_at": self._state.get("last_reconcile_at"),
            "last_reconcile_result": self._state.get("last_reconcile_result"),
            "broker_sent_positions": self._state.get("broker_sent_positions", {}),
            # NEVER GUESSES (2026-09-26): order ids whose outcome Webull has not settled
            "pending_parts": sorted(c for c, p in (self._state.get("order_parts") or {}).items()
                                    if p.get("pending")),
        }


def get_status(config=None, config_path=None, log=print):
    """Module-level convenience so a caller (e.g. a future web-tab status endpoint)
    doesn't need to know about the OrderAdapter class -- just the status dict."""
    return OrderAdapter(config=config, config_path=config_path, log=log).status()
