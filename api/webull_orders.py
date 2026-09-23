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
import hashlib
import json
import os
import threading
import time
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:
    _NY = None

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
        start, end = rails.get("session_start"), rails.get("session_end")
        if not start or not end:
            return True
        return start <= _now_ny().strftime("%H:%M") <= end

    def _believed_total_shares(self):
        return sum(abs(p.get("qty", 0)) for p in (self._state.get("believed_positions") or {}).values())

    def _check_rails(self, leg, qty, intent):
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
        if rails.get("one_open_position_per_leg", True) and leg in (self._state.get("open_legs") or {}):
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

    # -- public: stock/ETF orders --
    def place_stock_order(self, *, leg, signal_id, symbol, side, qty, intent="OPEN",
                          order_type="MARKET", limit_price=None, tif="DAY",
                          extended_hours=False, market="US", account_id=None,
                          instrument_id=None):
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
        actually happened at the broker."""
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

            ok, reason = self._check_rails(leg, qty, intent)
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

                parts = []
                for i, (part_side, part_qty) in enumerate(parts_plan, start=1):
                    part_coid = _part_client_order_id(coid, i, len(parts_plan))
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
                    try:
                        resp = client.order_v3.place_order(account_id, [new_order])
                        part_rec = {"side": part_side, "qty": part_qty,
                                   "client_order_id": part_coid, "ok": True, "sent": True,
                                   "reason": "", "response": _safe_response(resp)}
                    except Exception as e:
                        part_rec = {"side": part_side, "qty": part_qty,
                                   "client_order_id": part_coid, "ok": False, "sent": True,
                                   "reason": f"{type(e).__name__}: {e}", "response": None}
                        self.log(f"  [webull-orders] {mode} place_order FAILED for {symbol} "
                                 f"{part_side} {part_qty} (leg {leg}"
                                 + (f", part {i}/{len(parts_plan)}" if len(parts_plan) > 1 else "")
                                 + f"): {part_rec['reason']}")
                    parts.append(part_rec)
                    # Apply belief/sent bookkeeping per ACCEPTED part, immediately -- a
                    # part refused later in the same call must never roll back a part
                    # that already succeeded, and a part accepted later must still
                    # count even if an earlier one in this same call was refused. See
                    # _apply_intent_to_sent's docstring.
                    if part_rec["ok"]:
                        self._apply_intent_to_belief(leg, symbol, part_side, part_qty, intent)
                        self._apply_intent_to_sent(leg, symbol, part_side, part_qty,
                                                   account_id, intent)

                all_ok = all(p["ok"] for p in parts)
                record.update(ok=all_ok, sent=True, account_id=account_id, parts=parts)
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

    def reconcile(self, account_id=None, broker_positions_fn=None):
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
        that is a legitimate no-network no-op, not a failure, see the OFF-mode test."""
        mode, _ = self.effective_mode()
        if mode not in (MODE_PAPER, MODE_LIVE):
            return None
        try:
            if broker_positions_fn is not None:
                broker = broker_positions_fn()
            else:
                client = self._client(mode)
                if client is None:
                    return None
                account_id = account_id or self._account_id(mode, client)
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
            result = {"ok": ok, "mismatches": mismatches, "broker": broker,
                     "shadow_sent": sent, "account_id": account_id, "checked_at": now}
            self._state["last_reconcile_at"] = now
            self._state["last_reconcile_result"] = result
            self._save_state()
            return result

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

    # -- status, for the web tab (a function, not a UI edit) --
    def status(self):
        mode, reason = self.effective_mode()
        rails = self.cfg.get("rails") or DEFAULT_RAILS
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
        }


def get_status(config=None, config_path=None, log=print):
    """Module-level convenience so a caller (e.g. a future web-tab status endpoint)
    doesn't need to know about the OrderAdapter class -- just the status dict."""
    return OrderAdapter(config=config, config_path=config_path, log=log).status()
