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
str(OrderSide.BUY)=="BUY"), so this module imports and validates against those enums
rather than inventing values.

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

RAILS (enforced inside this adapter in EVERY mode, including OFF -- a blocked order
is recorded with mode="BLOCKED" and never reaches the mode dispatch below it):
max shares per leg, max total believed position (shares, summed across legs), a daily
loss limit fed by the caller via update_daily_pnl(), a session time window, a kill
file (default C:\\EdgeLog\\webull_orders\\KILL, same pattern as api/qqq_exec.py's
KILL flatten switch), one open position per leg, and reconcile() -- comparing the
broker's live positions (PAPER mode) against what this adapter BELIEVES it holds from
its own order history; a mismatch halts all new entries (CLOSE intents still pass)
until the owner clears it by restarting the adapter's state.

IDEMPOTENCY: client_order_id is derived deterministically from the caller's signal_id
(sanitized, or a stable sha1 if it doesn't fit Webull's 40-char field) and every order
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


def _sanitize_client_order_id(signal_id):
    """Deterministic, idempotent client_order_id from a caller's signal_id. Webull
    caps this field at 40 chars (see webull.trade.trade.order_operation.OrderOperation.
    place_order docstring) -- fall back to a stable hash when the raw id doesn't fit."""
    raw = str(signal_id)
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in raw)
    if 0 < len(safe) <= 40:
        return safe
    return "sig-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:35]


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
            "instrument_ids": {}, "account_ids": {}}


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
        if os.path.exists(self._kill_file()):
            self._halted = True
            self._halt_reason = "kill file present at " + self._kill_file()

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

    def _account_id(self, mode, client):
        if mode in self._account_id_cache:
            return self._account_id_cache[mode]
        cached = (self._state.get("account_ids") or {}).get(mode)
        if cached:
            self._account_id_cache[mode] = cached
            return cached
        accts = _as_list(_safe_response(client.account_v2.get_account_list()))
        if not accts:
            raise RuntimeError("get_account_list returned no accounts")
        aid = _field(accts[0], "account_id", "accountId", "id")
        if not aid:
            raise RuntimeError("could not read account_id from get_account_list response")
        self._account_id_cache[mode] = aid
        self._state.setdefault("account_ids", {})[mode] = aid
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

    def update_daily_pnl(self, delta):
        """Caller (the strategy / a fills sync) reports realized+open P&L deltas here
        so the daily_loss_limit_usd rail has something to check against. This adapter
        does not sync fills itself."""
        self._state["daily_pnl"] = self._state.get("daily_pnl", 0.0) + float(delta)
        self._save_state()

    def reset_daily_pnl(self):
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
        caught and reported via record["error"], never propagated)."""
        from webull.trade.common.order_side import OrderSide
        from webull.trade.common.order_type import OrderType
        from webull.trade.common.order_tif import OrderTIF

        side = str(side).upper()
        intent = str(intent).upper()
        order_type = str(order_type).upper()
        tif = str(tif).upper()
        if side not in (m.name for m in OrderSide):
            raise ValueError(f"side must be one of {[m.name for m in OrderSide]}, got {side!r}")
        if order_type not in (m.name for m in OrderType):
            raise ValueError(f"order_type must be one of {[m.name for m in OrderType]}, got {order_type!r}")
        if tif not in (m.name for m in OrderTIF):
            raise ValueError(f"tif must be one of {[m.name for m in OrderTIF]}, got {tif!r}")
        if intent not in ("OPEN", "CLOSE"):
            raise ValueError(f"intent must be OPEN or CLOSE, got {intent!r}")

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

        client = self._client(mode)
        if client is None:
            record.update(ok=False, sent=False, reason=f"no {mode} client ({mode_reason})")
            self._record_order(coid, record)
            self._last_error = record["reason"]
            self.log(f"  [webull-orders] {mode} requested but no client -- {record['reason']}")
            return record

        try:
            account_id = account_id or self._account_id(mode, client)
            # v3 order dict (see module docstring, ORDER API VERSION): symbol-keyed, no
            # instrument_id lookup needed. quantity/limit_price go over as STRINGS per
            # the documented getting-started sample.
            new_order = {
                "combo_type": "NORMAL", "client_order_id": coid, "symbol": symbol,
                "instrument_type": "EQUITY", "market": market, "order_type": order_type,
                "quantity": str(qty), "support_trading_session": "CORE", "side": side,
                "time_in_force": tif, "entrust_type": "QTY",
            }
            if order_type in ("LIMIT", "STOP_LOSS_LIMIT", "ENHANCED_LIMIT", "AT_AUCTION_LIMIT") \
                    and limit_price is not None:
                new_order["limit_price"] = str(limit_price)
            resp = client.order_v3.place_order(account_id, [new_order])
            record.update(ok=True, sent=True, account_id=account_id,
                          response=_safe_response(resp))
        except Exception as e:
            record.update(ok=False, sent=True, error=f"{type(e).__name__}: {e}")
            self._last_error = record["error"]
            self.log(f"  [webull-orders] {mode} place_order FAILED for {symbol} "
                     f"{side} {qty} (leg {leg}): {record['error']}")

        self._record_order(coid, record)
        if record.get("ok"):
            self._apply_intent_to_belief(leg, symbol, side, qty, intent)
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
        if mode not in (MODE_PAPER, MODE_LIVE):
            return cached or {"ok": False, "reason": f"no live query (mode={mode}): {reason}"}
        client = self._client(mode)
        if client is None:
            return cached or {"ok": False, "reason": f"no {mode} client"}
        try:
            account_id = account_id or self._account_id(mode, client)
            resp = client.order_v3.get_order_detail(account_id, coid)
            return {"ok": True, "mode": mode, "response": _safe_response(resp), "cached": cached}
        except Exception as e:
            return {"ok": False, "mode": mode, "reason": f"{type(e).__name__}: {e}", "cached": cached}

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

    def reconcile(self, account_id=None, broker_positions_fn=None):
        """Compare broker positions (PAPER/LIVE only) against this adapter's belief.
        A mismatch halts all future OPEN intents (CLOSE still passes) until the state
        file is cleared -- a fresh OrderAdapter with a fresh state file un-halts.
        Returns None when there's no broker to reconcile against (OFF, or no client)."""
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
            self.log(f"  [webull-orders] reconcile fetch failed: {type(e).__name__}: {e}")
            return None

        believed_raw = self._state.get("believed_positions", {})
        believed = {}
        for leg, p in believed_raw.items():
            sym = str(p.get("symbol", "")).upper()
            if not sym:
                continue
            believed[sym] = believed.get(sym, 0.0) + float(p.get("qty", 0) or 0)

        syms = set(broker) | set(believed)
        mismatches = [{"symbol": s, "broker": broker.get(s, 0.0), "believed": believed.get(s, 0.0)}
                     for s in sorted(syms) if abs(broker.get(s, 0.0) - believed.get(s, 0.0)) > 1e-6]
        ok = not mismatches
        if not ok:
            self._halted = True
            self._halt_reason = f"reconcile mismatch: {mismatches}"
            self.log(f"  [webull-orders] \u26a0 RECONCILE MISMATCH -- halting new entries: {mismatches}")
        return {"ok": ok, "mismatches": mismatches, "broker": broker, "believed": believed,
               "checked_at": time.time()}

    # -- futures: staged, hard-disabled --
    def resolve_futures_contract(self, product_symbol, market="US"):
        """Would resolve `product_symbol` (e.g. 'MNQ') to its current front-month
        instrument via webull.data.quotes.instrument.Instrument.get_futures_products /
        get_futures_instrument(category='US_FUTURES') on a market-data client. Not
        wired -- raises unconditionally. See FUTURES_NOT_ENABLED / module docstring."""
        raise NotImplementedError(FUTURES_NOT_ENABLED)

    def place_futures_order(self, *args, **kwargs):
        raise NotImplementedError(FUTURES_NOT_ENABLED)

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
        }


def get_status(config=None, config_path=None, log=print):
    """Module-level convenience so a caller (e.g. a future web-tab status endpoint)
    doesn't need to know about the OrderAdapter class -- just the status dict."""
    return OrderAdapter(config=config, config_path=config_path, log=log).status()
