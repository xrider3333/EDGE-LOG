"""tools/webull_paper_smoke.py -- a SAFE smoke test for the Webull PAPER (sandbox) rails.

Three independent, opt-in steps:

  --check        (default) Load PAPER credentials via api.webull_orders' own loader,
                 build the sandbox client the SAME way the order adapter does, list the
                 sandbox accounts, and print each account's type and the LAST 4
                 characters of its account number only. Also prints a best-effort read
                 of each account's cash balance so you can confirm it looks like a
                 $1,000,000 PAPER account, not a live one. Exits non-zero if keys are
                 missing/still the unfilled template, if Webull rejects them, or if no
                 accounts come back.

  --order-test   Places ONE 1-share QQQ LIMIT BUY through api.webull_orders.OrderAdapter
                 in PAPER mode, priced at 50% of a fresh reference price (so it cannot
                 fill), DAY time-in-force, CORE session -- then queries its status,
                 cancels it, and confirms the cancel took. Refuses outright (no order
                 sent) unless the adapter's effective mode for this run is PAPER AND the
                 client's registered host is confirmed to be the sandbox host.

  --positions    Prints this tool's believed positions and (if a client can be built) the
                 broker's own reported positions -- should both be empty after a test.

SAFETY / ISOLATION (read before changing any path below)
----------------------------------------------------------
The owner's live processes (NinjaTrader bridge, qqq_exec shadow feed, the runner) may be
using C:\\EdgeLog\\ at the same moment this tool runs. This tool touches exactly ONE file
under C:\\EdgeLog\\: the PAPER credentials file (api.webull_orders.DEFAULT_PAPER_KEYS,
normally C:\\EdgeLog\\webull_paper_keys.json), read-only, through the adapter's own
load_paper_keys() loader -- which is the whole point of the tool and is never printed.
Everything else the adapter would normally point at C:\\EdgeLog\\webull_orders\\ for
(state.json, config.json, KILL, ARM_LIVE) or C:\\EdgeLog\\ for (live keys/token dir) is
overridden in-process (see build_cfg()) to an isolated directory under the OS temp dir,
so this tool can never race a live adapter instance over the same state file, never
reads the live KILL switch or live webull_keys.json, and never writes the persisted
adapter config. Rails are still fully enforced (max_shares_per_leg is pinned to 1 here
as an extra belt-and-suspenders cap on top of the hardcoded qty=1 order below).

The reference price for --order-test comes from yfinance (free, keyless, touches
nothing under C:\\EdgeLog) rather than api.qqq_exec.default_webull_quote(), which is
otherwise "the repo's free QQQ snapshot path" but authenticates against the LIVE
C:\\EdgeLog\\webull_keys.json to do it -- exactly the live file this tool must not open.
yfinance is the OTHER existing free-QQQ-price path in this repo (the QQQ leg of
api.qqq_exec.default_ratio_calibration), reused directly here instead of through that
function because it also drags in a local NQ 10s-bar file this tool has no reason to
depend on.

Every line this tool prints is passed through _redact() before printing, and app_key /
app_secret are never read into a variable this module prints -- see load_paper_keys()'s
own docstring in api/webull_orders.py ("this module never reads, logs, or persists an
app_key/app_secret/token value anywhere").

USAGE
-----
  python tools/webull_paper_smoke.py                # same as --check
  python tools/webull_paper_smoke.py --check
  python tools/webull_paper_smoke.py --order-test
  python tools/webull_paper_smoke.py --positions
  python tools/webull_paper_smoke.py --check --order-test --positions   # combinable

Exit code is 0 only if every requested step passed.
"""
import argparse
import json
import os
import pathlib
import re
import sys
import tempfile
import time
import uuid

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from api import webull_orders as WO  # noqa: E402


SMOKE_LEG = "SMOKE_QQQ"
SMOKE_SYMBOL = "QQQ"
LIMIT_PRICE_FRACTION = 0.5          # "far below market" -- half of the reference price
RATE_LIMIT_SLEEP_SEC = 1.5          # Webull sandbox: be a good citizen between calls
PAPER_BALANCE_EXPECTED = 1_000_000.0


class SmokeRefusal(Exception):
    """A safety precondition wasn't met. The message is already plain-language and
    redaction-safe -- callers print str(e) as-is."""


# ── redaction (never let a secret reach the terminal) ─────────────────────────────

# Long runs of letters/digits/- are how app keys, access tokens, and signed-request
# hashes look. Deliberately does NOT include "_": real-world error text tends to embed
# file paths and env-var-style names (C:\EdgeLog\_paper_keys.json,
# EDGELOG_WEBULL_PAPER_KEYS) that are long only because of underscore-joined words, and
# those are not secrets -- redacting them made a refusal message unreadable (it hid the
# very path the owner needs to go fix) without making anything safer, since a real
# secret's high-entropy payload is already a long run on its own without needing an
# underscore to reach the length threshold. Purely-numeric runs (account_id, epoch
# timestamps) are also left readable -- they're routing identifiers, not secrets. Still
# intentionally broad otherwise: over-redacting a harmless long id is cosmetic,
# under-redacting a token is not.
_REDACT_RE = re.compile(r'(?<![A-Za-z0-9])[A-Za-z0-9\-]{24,}(?![A-Za-z0-9])')


def _redact(text):
    """Mask likely secrets in `text` (a str or an Exception). Applied to every line this
    tool prints and to every caught exception, so a secret can never reach the terminal
    even if some future SDK error message embeds one -- api/webull_orders.py notes the
    SDK's own client logger does exactly that on certain errors, which is why it also
    silences that logger at import time."""
    if isinstance(text, BaseException):
        s = f"{type(text).__name__}: {text}"
    else:
        s = str(text)

    def _mask(m):
        tok = m.group(0)
        return tok if tok.isdigit() else f"<redacted:{len(tok)}ch>"

    return _REDACT_RE.sub(_mask, s)


def _p(out, msg):
    out(_redact(msg))


def _safe_repr(label, d):
    try:
        s = json.dumps(d, default=str, sort_keys=True)
    except Exception:
        s = repr(d)
    return f"{label}: {s}"


# ── isolated config (see module docstring's SAFETY / ISOLATION section) ───────────

def _default_smoke_dir():
    return (os.environ.get("EDGELOG_WEBULL_SMOKE_DIR")
            or os.path.join(tempfile.gettempdir(), "edgelog_webull_paper_smoke"))


def build_cfg(paper_keys_path=None, base_dir=None):
    """An in-process OrderAdapter config for THIS TOOL only -- never written to disk, and
    never touches the persisted adapter config file. mode is force-set to PAPER here,
    not read from anywhere. Every path except paper_keys_path is isolated under
    base_dir (default: the OS temp dir) instead of C:\\EdgeLog, so this tool cannot race
    or interfere with a live adapter instance. paper_keys_path defaults to the adapter's
    real default (C:\\EdgeLog\\webull_paper_keys.json) -- reading THAT file via
    WO.load_paper_keys() is the one sanctioned live-file touch this tool makes."""
    base_dir = base_dir or _default_smoke_dir()
    cfg = WO.load_config(os.path.join(base_dir, "__edgelog_smoke_no_such_config__.json"))
    cfg["mode"] = WO.MODE_PAPER
    cfg["paper_keys_path"] = paper_keys_path or WO.DEFAULT_PAPER_KEYS
    cfg["paper_token_dir"] = os.path.join(base_dir, "paper_token")
    cfg["state_path"] = os.path.join(base_dir, "state.json")
    cfg["kill_file"] = os.path.join(base_dir, "KILL_never_created")
    cfg["arm_live_file"] = os.path.join(base_dir, "ARM_LIVE_never_created")
    cfg["live_keys_path"] = os.path.join(base_dir, "live_keys_never_created.json")
    cfg["live_token_dir"] = os.path.join(base_dir, "live_token_never_created")
    cfg["rails"]["max_shares_per_leg"] = 1
    cfg["rails"]["max_total_position_shares"] = 1
    return cfg


def _make_adapter(cfg, out):
    return WO.OrderAdapter(config=cfg, log=lambda msg: _p(out, msg))


# ── sandbox host introspection (defense-in-depth assertion for --order-test) ──────

def _resolve_host(client):
    """Best-effort read-back of the host currently registered for this client's DEFAULT
    api_type -- introspects the same UserCustomizedEndpointResolver entry that
    api.webull_orders.OrderAdapter._build_client()'s add_endpoint() call writes for
    PAPER mode (see that module's SANDBOX TARGETING docstring section). Returns the host
    string, or None if it can't be determined -- callers must treat None as "sandbox NOT
    confirmed", never as "assume sandbox"."""
    try:
        from webull.core.common import api_type as _api_type
        from webull.core.endpoint.resolver_endpoint_request import ResolveEndpointRequest
        api_client = client.order_v3.client
        return api_client._endpoint_resolver.resolve(
            ResolveEndpointRequest(api_client.get_region_id(), _api_type.DEFAULT))
    except Exception:
        return None


def _assert_paper_and_sandbox(adapter, host_fn=None):
    """Refuse (raise SmokeRefusal) unless BOTH hold: the adapter's effective mode for
    this run is PAPER, and the client's registered host resolves to the sandbox host.
    Returns (client, host) on success. Nothing is sent before this returns."""
    host_fn = host_fn or _resolve_host
    mode, reason = adapter.effective_mode()
    if mode != WO.MODE_PAPER:
        raise SmokeRefusal(f"REFUSED -- effective mode is {mode}, not PAPER ({reason}). "
                           "Nothing was sent.")
    client = adapter._client(WO.MODE_PAPER)
    if client is None:
        raise SmokeRefusal("REFUSED -- mode is PAPER but no sandbox client could be built. "
                           "Nothing was sent.")
    host = host_fn(client)
    if host != WO.SANDBOX_TRADE_HOST:
        raise SmokeRefusal(f"REFUSED -- could not confirm the sandbox host (resolved "
                           f"{host!r}, expected {WO.SANDBOX_TRADE_HOST!r}). Nothing was sent.")
    return client, host


# ── reference price (see module docstring for why this is yfinance, not Webull) ───

def latest_qqq_price():
    """Latest QQQ trade price from yfinance. Returns (price: float, asof: str). Raises
    RuntimeError on any failure -- callers must refuse to guess a limit price rather
    than fall back to a stale or fabricated number."""
    import yfinance as yf
    tkr = yf.Ticker("QQQ")
    df = tkr.history(period="1d", interval="1m", prepost=False, auto_adjust=False)
    if df is None or not len(df):
        df = tkr.history(period="5d", interval="1d", prepost=False, auto_adjust=False)
    if df is None or not len(df):
        raise RuntimeError("yfinance returned no QQQ bars at all (network issue or data gap)")
    price = float(df.iloc[-1]["Close"])
    if not (price > 0):
        raise RuntimeError(f"yfinance QQQ price looked invalid: {price!r}")
    ts = df.index[-1]
    asof = ts.strftime("%Y-%m-%d %H:%M:%S%z") if hasattr(ts, "strftime") else str(ts)
    return price, asof


# ── response parsing (defensive field-name matching, same style as api/webull_orders.py) ──

def _extract_order_status(status_result):
    """status_result is an api.webull_orders.OrderAdapter.order_status() return value."""
    if not isinstance(status_result, dict):
        return None
    resp = status_result.get("response")
    if resp is None:
        cached = status_result.get("cached")
        return WO._field(cached, "status", "order_status", "orderStatus") if isinstance(cached, dict) else None
    items = WO._as_list(resp)
    item = items[0] if items else (resp if isinstance(resp, dict) else None)
    if not isinstance(item, dict):
        return None
    return WO._field(item, "status", "order_status", "orderStatus")


def _extract_balance_usd(payload):
    """Best-effort total cash from a get_account_balance() response. Field names
    (account_currency_assets[].total_cash / .balance, keyed by currency) verified
    against Webull's own account-balance API reference. Returns a float or None if the
    shape doesn't match anything expected -- never raises."""
    try:
        data = payload
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            data = data["data"]
        item = data[0] if isinstance(data, list) and data else data
        if not isinstance(item, dict):
            return None
        assets = item.get("account_currency_assets")
        if isinstance(assets, list) and assets:
            usd = next((a for a in assets if isinstance(a, dict)
                       and str(a.get("currency", "")).upper() == "USD"), assets[0])
            if isinstance(usd, dict):
                v = usd.get("total_cash", usd.get("balance"))
                if v is not None:
                    return float(v)
        v = item.get("total_cash", item.get("balance"))
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _looks_like_paper_balance(value):
    """True/False/None (unknown). Tolerance is generous (5%, floor $1000) since a
    balance can drift a little from live paper trading between checks."""
    if value is None:
        return None
    tolerance = max(1000.0, PAPER_BALANCE_EXPECTED * 0.05)
    return abs(float(value) - PAPER_BALANCE_EXPECTED) <= tolerance


# ── --check ─────────────────────────────────────────────────────────────────────

def cmd_check(cfg=None, out=print, sleep_fn=time.sleep):
    cfg = cfg or build_cfg()
    adapter = _make_adapter(cfg, out)
    mode, reason = adapter.effective_mode()
    _p(out, f"requested PAPER -> effective_mode={mode} ({reason})")
    if mode != WO.MODE_PAPER:
        _p(out, "FAIL -- paper credentials are missing, still the unfilled template, or "
                "otherwise unusable (see reason above). Nothing was sent to Webull.")
        return 1

    client = adapter._client(WO.MODE_PAPER)
    if client is None:
        _p(out, "FAIL -- credentials are present but no sandbox client could be built.")
        return 1

    host = _resolve_host(client)
    _p(out, f"sandbox host resolves to: {host or 'UNKNOWN'} (expected {WO.SANDBOX_TRADE_HOST})")

    try:
        resp = client.account_v2.get_account_list()
        accounts = WO._as_list(WO._safe_response(resp))
    except Exception as e:
        _p(out, f"FAIL -- Webull rejected the account-list call: {_redact(e)}")
        return 1

    accounts = [a for a in accounts if isinstance(a, dict)]
    if not accounts:
        _p(out, "FAIL -- the sandbox returned zero paper accounts. Check the Webull "
                "PaperTrade dashboard.")
        return 1

    _p(out, f"{len(accounts)} paper account(s) returned:")
    balances = []
    for i, a in enumerate(accounts):
        acct_id = WO._field(a, "account_id", "accountId", "id", default="?")
        acct_num = str(WO._field(a, "account_number", "accountNumber", "acctNumber", default="") or "")
        acct_type = WO._field(a, "account_type", "accountType", default="?")
        last4 = acct_num[-4:] if len(acct_num) >= 4 else "????"
        _p(out, f"  [{i + 1}] type={acct_type}  account_number=...{last4}  account_id={acct_id}")

        if i > 0:
            sleep_fn(RATE_LIMIT_SLEEP_SEC)
        try:
            bresp = client.account_v2.get_account_balance(acct_id)
            bal = _extract_balance_usd(WO._safe_response(bresp))
            balances.append(bal)
            if bal is not None:
                _p(out, f"      cash balance: ${bal:,.2f}")
            else:
                _p(out, "      cash balance: could not be read from the response")
        except Exception as e:
            _p(out, f"      cash balance: unavailable ({_redact(e)})")
            balances.append(None)

    verdicts = [_looks_like_paper_balance(b) for b in balances]
    known = [v for v in verdicts if v is not None]
    if known and all(known):
        _p(out, "PAPER-LOOKING: yes -- balance(s) are consistent with the $1,000,000 "
                "paper default.")
    elif known and any(v is False for v in known):
        _p(out, "PAPER-LOOKING: NO -- at least one balance does NOT look like the "
                "$1,000,000 paper default. STOP and confirm this is the sandbox, not a "
                "live account, before running --order-test.")
    else:
        _p(out, "PAPER-LOOKING: inconclusive (could not read a balance to compare).")

    _p(out, "PASS -- paper credentials work and the sandbox returned account(s).")
    return 0


# ── --order-test ────────────────────────────────────────────────────────────────

def cmd_order_test(cfg=None, out=print, price_fn=None, host_fn=None, sleep_fn=None):
    cfg = cfg or build_cfg()
    price_fn = price_fn or latest_qqq_price
    sleep_fn = sleep_fn or time.sleep
    adapter = _make_adapter(cfg, out)

    try:
        client, host = _assert_paper_and_sandbox(adapter, host_fn=host_fn)
    except SmokeRefusal as e:
        _p(out, str(e))
        return 1
    _p(out, f"[ok] effective mode is PAPER, sandbox host confirmed ({host})")

    try:
        price, asof = price_fn()
    except Exception as e:
        _p(out, f"REFUSED -- could not get a reference QQQ price ({_redact(e)}); "
                "refusing to guess a limit price.")
        return 1

    limit_price = round(price * LIMIT_PRICE_FRACTION, 2)
    _p(out, f"reference QQQ price ${price:.2f} (as of {asof}) -> SMOKE limit BUY @ "
            f"${limit_price:.2f} ({LIMIT_PRICE_FRACTION:.0%} of market, cannot fill)")
    if not (0 < limit_price < price):
        _p(out, f"REFUSED -- computed limit price {limit_price} is not safely below "
                f"reference price {price}.")
        return 1

    signal_id = f"SMOKE-{uuid.uuid4().hex[:16]}"
    _p(out, f"[1/4] place_stock_order: leg={SMOKE_LEG} {SMOKE_SYMBOL} BUY 1 LIMIT "
            f"{limit_price} DAY CORE (signal {signal_id})")
    rec = adapter.place_stock_order(leg=SMOKE_LEG, signal_id=signal_id, symbol=SMOKE_SYMBOL,
                                    side="BUY", qty=1, intent="OPEN", order_type="LIMIT",
                                    limit_price=limit_price, tif="DAY")
    _p(out, _safe_repr("      place result", rec))
    if not (rec.get("ok") and rec.get("sent") and rec.get("mode") == WO.MODE_PAPER):
        _p(out, "FAIL -- the order was not actually sent in PAPER mode; stopping before "
                "status/cancel.")
        return 1

    sleep_fn(RATE_LIMIT_SLEEP_SEC)
    _p(out, "[2/4] order_status (pre-cancel)")
    st1 = adapter.order_status(signal_id)
    _p(out, _safe_repr("      status result", st1))

    sleep_fn(RATE_LIMIT_SLEEP_SEC)
    _p(out, "[3/4] cancel_order")
    can = adapter.cancel_order(signal_id)
    _p(out, _safe_repr("      cancel result", can))
    if not can.get("ok"):
        _p(out, f"FAIL -- cancel call did not report ok: {_redact(can.get('reason'))}")
        return 1

    sleep_fn(RATE_LIMIT_SLEEP_SEC)
    _p(out, "[4/4] order_status (post-cancel, confirming CANCELLED)")
    st2 = adapter.order_status(signal_id)
    _p(out, _safe_repr("      status result", st2))
    final_status = _extract_order_status(st2)
    if str(final_status).upper() != "CANCELLED":
        _p(out, f"FAIL -- order does not show CANCELLED after cancel (saw {final_status!r}) "
                "-- verify manually on the Webull PaperTrade dashboard before trusting "
                "this leg is flat.")
        return 1

    # The order never filled, so undo the OPEN belief place_stock_order recorded at send
    # time (this adapter marks belief optimistically on send, not on fill -- see
    # api/webull_orders.py's place_stock_order). Keeps a later --positions read clean and
    # keeps one_open_position_per_leg from blocking a repeat run of this same tool.
    adapter._apply_intent_to_belief(SMOKE_LEG, SMOKE_SYMBOL, "SELL", 1, intent="CLOSE")
    _p(out, "PASS -- placed, queried, cancelled, and confirmed CANCELLED. No shares were bought.")
    return 0


# ── --positions ─────────────────────────────────────────────────────────────────

def cmd_positions(cfg=None, out=print):
    cfg = cfg or build_cfg()
    adapter = _make_adapter(cfg, out)
    mode, reason = adapter.effective_mode()
    _p(out, f"effective_mode={mode} ({reason})")
    result = adapter.positions()
    _p(out, f"believed (this tool's own isolated ledger): {result.get('believed')}")
    if result.get("broker") is not None:
        _p(out, f"broker (live sandbox query): {result.get('broker')}")
    elif result.get("error"):
        _p(out, f"broker query failed: {_redact(result['error'])}")
    else:
        _p(out, "broker: not queried (mode is not PAPER/LIVE)")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(prog="webull_paper_smoke.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="Load paper keys, list sandbox accounts (default).")
    ap.add_argument("--order-test", action="store_true", dest="order_test",
                    help="Place, query, and cancel one unfillable 1-share QQQ limit order.")
    ap.add_argument("--positions", action="store_true",
                    help="Print paper positions (believed + broker); should be empty.")
    args = ap.parse_args(argv)
    if not (args.check or args.order_test or args.positions):
        args.check = True

    rc = 0
    if args.check:
        print("=== --check ===")
        rc = max(rc, cmd_check())
    if args.order_test:
        print("=== --order-test ===")
        rc = max(rc, cmd_order_test())
    if args.positions:
        print("=== --positions ===")
        rc = max(rc, cmd_positions())
    print(f"OVERALL: {'PASS' if rc == 0 else 'FAIL'}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
