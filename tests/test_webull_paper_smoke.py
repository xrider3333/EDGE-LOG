"""Unit tests for tools/webull_paper_smoke.py -- the Webull PAPER smoke-test tool.

Same discipline as tests/test_webull_orders.py: the Webull SDK is NEVER hit over the
network. Every PAPER-mode test monkeypatches OrderAdapter._build_client to return a
MagicMock in place of the real webull.core.client.ApiClient / TradeClient construction,
so even the real installed SDK package never signs a request or opens a socket. Every
cfg built here uses build_cfg(base_dir=..., paper_keys_path=...) pointed at tmp_path, so
this suite never touches anything under C:\\EdgeLog either.
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import webull_orders as WO           # noqa: E402
import tools.webull_paper_smoke as WS         # noqa: E402


# ── fixtures / helpers ────────────────────────────────────────────────────────────

def _write_keys(path, app_key="AK", app_secret="AS"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"app_key": app_key, "app_secret": app_secret}, f)


def _cfg(tmp_path, with_keys=True, app_key="AK", app_secret="AS"):
    keys_path = str(tmp_path / "paper_keys.json")
    if with_keys:
        _write_keys(keys_path, app_key, app_secret)
    cfg = WS.build_cfg(paper_keys_path=keys_path, base_dir=str(tmp_path / "smoke"))
    # Tests run at whatever wall-clock time they happen to execute at -- widen the
    # session window so the rail never blocks a test depending on time of day (same
    # fix tests/test_webull_orders.py's own _cfg() fixture applies for the same reason).
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    return cfg


def _json_mock(payload):
    m = MagicMock()
    m.json.return_value = payload
    return m


def _mock_client(accounts=None, balance_usd="1000000.00"):
    """A MagicMock standing in for webull.trade.trade_client.TradeClient, wired for
    account listing + balance (--check) and place/status/cancel/status (--order-test)."""
    if accounts is None:
        # account_class is what _account_id() selects on by default (purpose "stock"
        # wants INDIVIDUAL_CASH -- see api/webull_orders.py's DEFAULT_ACCOUNT_SELECT).
        accounts = [{"account_id": "ACCT1", "account_number": "PA123456789012",
                    "account_type": "CASH", "account_class": "INDIVIDUAL_CASH"}]
    client = MagicMock()
    client.account_v2.get_account_list.return_value = _json_mock({"data": accounts})
    client.account_v2.get_account_balance.return_value = _json_mock({
        "account_id": "ACCT1",
        "account_currency_assets": [{"currency": "USD", "total_cash": balance_usd,
                                     "balance": balance_usd}],
    })
    client.order_v3.place_order.return_value = _json_mock({"status": "SUBMITTED"})
    client.order_v3.get_order_detail.side_effect = [
        _json_mock({"status": "SUBMITTED"}),
        _json_mock({"status": "CANCELLED"}),
    ]
    client.order_v3.cancel_order.return_value = _json_mock({"status": "CANCELLED"})
    client.account_v2.get_account_position.return_value = _json_mock({"data": []})
    return client


def _real_order_detail_response(status, client_order_id):
    """The EXACT shape the real Webull PAPER sandbox returned for order status during
    the 2026-09-14 12:04 ET smoke test (ids redacted/replaced) -- a combo wrapper whose
    OWN top level carries only client_order_id/combo_order_id/combo_type, with the
    actual per-order status/filled_quantity/commission/fees nested one level down under
    "orders". The OLD _extract_order_status read the top level directly and always got
    None, which is what printed "FAIL -- order does not show CANCELLED after cancel
    (saw None)" even though the order genuinely went SUBMITTED -> CANCELLED."""
    return {
        "client_order_id": client_order_id, "combo_order_id": "SMOKE-COMBO-ID",
        "combo_type": "NORMAL",
        "orders": [{
            "client_order_id": client_order_id, "commission": {}, "entrust_type": "QTY",
            "fees": [], "filled_quantity": "0", "instrument_type": "EQUITY",
            "limit_price": "354.62", "order_id": "SMOKE-ORDER-ID", "order_type": "LIMIT",
            "place_time": "1789401892218", "place_time_at": "2026-09-14T16:04:52.218Z",
            "side": "BUY", "status": status, "support_trading_session": "CORE",
            "symbol": "QQQ", "time_in_force": "DAY", "total_quantity": "1",
        }],
    }


def _sandbox_host(_client):
    return WO.SANDBOX_TRADE_HOST


def _believed_dict_from_lines(lines):
    import ast
    prefix = "believed (this tool's own isolated ledger): "
    for l in lines:
        if l.startswith(prefix):
            return ast.literal_eval(l[len(prefix):])
    return {}


def _fixed_price():
    return 100.0, "2026-09-14 12:00:00"


def _use_mock_client(monkeypatch, client):
    monkeypatch.setattr(WO.OrderAdapter, "_build_client", lambda self, mode: client)


# ── build_cfg isolation ────────────────────────────────────────────────────────────

def test_build_cfg_never_points_at_edgelog_except_paper_keys(tmp_path):
    cfg = _cfg(tmp_path)
    assert str(tmp_path) in cfg["state_path"]
    assert str(tmp_path) in cfg["kill_file"]
    assert str(tmp_path) in cfg["arm_live_file"]
    assert str(tmp_path) in cfg["paper_token_dir"]
    assert str(tmp_path) in cfg["live_keys_path"]
    assert str(tmp_path) in cfg["live_token_dir"]
    assert cfg["mode"] == WO.MODE_PAPER
    assert cfg["rails"]["max_shares_per_leg"] == 1


# ── --check ────────────────────────────────────────────────────────────────────────

def test_check_missing_keys_exits_nonzero(tmp_path):
    cfg = _cfg(tmp_path, with_keys=False)
    lines = []
    rc = WS.cmd_check(cfg=cfg, out=lines.append)
    assert rc != 0
    assert any("credential" in l.lower() for l in lines)


def test_check_template_keys_exits_nonzero(tmp_path):
    cfg = _cfg(tmp_path, app_key="PASTE_APP_KEY_HERE", app_secret="PASTE_APP_SECRET_HERE")
    rc = WS.cmd_check(cfg=cfg, out=lambda *_: None)
    assert rc != 0


def test_check_rejected_keys_exits_nonzero(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = MagicMock()
    client.account_v2.get_account_list.side_effect = RuntimeError("401 INVALID_TOKEN")
    _use_mock_client(monkeypatch, client)
    rc = WS.cmd_check(cfg=cfg, out=lambda *_: None, sleep_fn=lambda *_: None)
    assert rc != 0


def test_check_no_accounts_exits_nonzero(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client(accounts=[])
    _use_mock_client(monkeypatch, client)
    rc = WS.cmd_check(cfg=cfg, out=lambda *_: None, sleep_fn=lambda *_: None)
    assert rc != 0


def test_check_happy_path_lists_accounts_and_masks_account_number(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)
    lines = []
    rc = WS.cmd_check(cfg=cfg, out=lines.append, sleep_fn=lambda *_: None)
    assert rc == 0, "\n".join(lines)
    joined = "\n".join(lines)
    assert "9012" in joined                       # last 4 of the account number
    assert "PA123456789012" not in joined          # full account number never printed
    assert "CASH" in joined
    assert "PAPER-LOOKING: yes" in joined


def test_check_flags_balance_that_does_not_look_like_paper(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client(balance_usd="4213.55")
    _use_mock_client(monkeypatch, client)
    lines = []
    rc = WS.cmd_check(cfg=cfg, out=lines.append, sleep_fn=lambda *_: None)
    assert rc == 0        # the balance mismatch is a warning, not a hard failure
    assert any("PAPER-LOOKING: NO" in l for l in lines)


# ── --order-test refusals ───────────────────────────────────────────────────────────

def test_order_test_refuses_when_not_paper(tmp_path):
    cfg = _cfg(tmp_path, with_keys=False)      # -> effective mode falls back to OFF
    lines = []
    rc = WS.cmd_order_test(cfg=cfg, out=lines.append)
    assert rc != 0
    assert any("PAPER" in l for l in lines)


def test_order_test_refuses_when_host_not_sandbox(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)
    lines = []
    rc = WS.cmd_order_test(cfg=cfg, out=lines.append, host_fn=lambda c: "api.webull.com")
    assert rc != 0
    assert any("sandbox" in l.lower() for l in lines)
    client.order_v3.place_order.assert_not_called()


def test_order_test_refuses_when_host_unresolvable(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)
    lines = []
    rc = WS.cmd_order_test(cfg=cfg, out=lines.append, host_fn=lambda c: None)
    assert rc != 0
    client.order_v3.place_order.assert_not_called()


# ── --order-test happy path ─────────────────────────────────────────────────────────

def test_order_test_happy_path_calls_in_order_exactly_once(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)

    lines = []
    rc = WS.cmd_order_test(cfg=cfg, out=lines.append, host_fn=_sandbox_host,
                           price_fn=_fixed_price, sleep_fn=lambda *_: None)
    assert rc == 0, "\n".join(lines)

    _ORDER_CALL_NAMES = {"order_v3.place_order", "order_v3.get_order_detail", "order_v3.cancel_order"}
    order_calls = [c[0] for c in client.mock_calls if c[0] in _ORDER_CALL_NAMES]
    assert order_calls == ["order_v3.place_order", "order_v3.get_order_detail",
                           "order_v3.cancel_order", "order_v3.get_order_detail"]
    assert client.order_v3.place_order.call_count == 1
    assert client.order_v3.cancel_order.call_count == 1
    assert client.order_v3.get_order_detail.call_count == 2
    assert any("PASS" in l for l in lines)


def test_order_test_parses_real_nested_v3_response_shape(tmp_path, monkeypatch):
    """Regression for the 2026-09-14 12:04 ET LIVE smoke test's actual FAIL: the real
    sandbox order-detail response nests status under orders[], not at the top level.
    Uses client.order_v3.get_order_detail's OWN (account_id, client_order_id) call args
    to build a response whose orders[0].client_order_id genuinely matches what was
    queried, exactly like the real endpoint -- not just a single-item list that happens
    to work via position-0 fallback."""
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)

    calls = {"n": 0}

    def _get_order_detail(account_id, client_order_id):
        calls["n"] += 1
        status = "SUBMITTED" if calls["n"] == 1 else "CANCELLED"
        return _json_mock(_real_order_detail_response(status, client_order_id))

    client.order_v3.get_order_detail.side_effect = _get_order_detail

    lines = []
    rc = WS.cmd_order_test(cfg=cfg, out=lines.append, host_fn=_sandbox_host,
                           price_fn=_fixed_price, sleep_fn=lambda *_: None)
    assert rc == 0, "\n".join(lines)
    assert not any("saw None" in l for l in lines), "\n".join(lines)
    assert any("PASS" in l for l in lines)

    # The isolated ledger must be back to flat (the OPEN belief reversed on the never-
    # filled order) -- same assertion as test_positions_empty_after_order_test_round_trip.
    lines2 = []
    WS.cmd_positions(cfg=cfg, out=lines2.append)
    believed = _believed_dict_from_lines(lines2)
    assert all(abs(p.get("qty", 0)) < 1e-9 for p in believed.values())


def test_order_test_limit_price_is_far_below_market(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)

    rc = WS.cmd_order_test(cfg=cfg, out=lambda *_: None, host_fn=_sandbox_host,
                           price_fn=lambda: (400.0, "2026-09-14 12:00:00"),
                           sleep_fn=lambda *_: None)
    assert rc == 0
    args, _ = client.order_v3.place_order.call_args
    account_id, new_orders = args
    limit_price = float(new_orders[0]["limit_price"])
    assert limit_price == pytest.approx(200.0)
    assert limit_price < 400.0 * 0.6          # comfortably below market, not a rounding wobble
    assert new_orders[0]["order_type"] == "LIMIT"
    assert new_orders[0]["time_in_force"] == "DAY"
    assert new_orders[0]["support_trading_session"] == "CORE"
    assert new_orders[0]["quantity"] == "1"
    assert new_orders[0]["symbol"] == "QQQ"


def test_order_test_uses_unique_smoke_prefixed_client_order_id(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)

    ids = []
    for _ in range(2):
        client.order_v3.get_order_detail.side_effect = [
            _json_mock({"status": "SUBMITTED"}), _json_mock({"status": "CANCELLED"})]
        rc = WS.cmd_order_test(cfg=cfg, out=lambda *_: None, host_fn=_sandbox_host,
                               price_fn=_fixed_price, sleep_fn=lambda *_: None)
        assert rc == 0
        args, _ = client.order_v3.place_order.call_args
        _, new_orders = args
        coid = new_orders[0]["client_order_id"]
        assert coid.startswith("SMOKE-")
        ids.append(coid)
    assert ids[0] != ids[1]        # a fresh id every run -- never hits the idempotency cache


def test_order_test_fails_if_final_status_not_cancelled(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    client.order_v3.get_order_detail.side_effect = [
        _json_mock({"status": "SUBMITTED"}), _json_mock({"status": "SUBMITTED"})]
    _use_mock_client(monkeypatch, client)
    lines = []
    rc = WS.cmd_order_test(cfg=cfg, out=lines.append, host_fn=_sandbox_host,
                           price_fn=_fixed_price, sleep_fn=lambda *_: None)
    assert rc != 0
    assert any("CANCELLED" in l for l in lines)


def test_order_test_stops_before_status_if_price_fetch_fails(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)

    def _boom():
        raise RuntimeError("no network")

    rc = WS.cmd_order_test(cfg=cfg, out=lambda *_: None, host_fn=_sandbox_host,
                           price_fn=_boom, sleep_fn=lambda *_: None)
    assert rc != 0
    client.order_v3.place_order.assert_not_called()


# ── --positions ─────────────────────────────────────────────────────────────────────

def test_positions_reports_off_mode_without_keys(tmp_path):
    cfg = _cfg(tmp_path, with_keys=False)
    lines = []
    rc = WS.cmd_positions(cfg=cfg, out=lines.append)
    assert rc == 0
    assert any("effective_mode=OFF" in l for l in lines)


def test_positions_empty_after_order_test_round_trip(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)

    rc = WS.cmd_order_test(cfg=cfg, out=lambda *_: None, host_fn=_sandbox_host,
                           price_fn=_fixed_price, sleep_fn=lambda *_: None)
    assert rc == 0

    lines = []
    rc2 = WS.cmd_positions(cfg=cfg, out=lines.append)
    assert rc2 == 0
    # place_stock_order marks belief optimistically on send; since the order never
    # filled, cmd_order_test reverses it (OPEN -> CLOSE) so every leg nets back to a
    # flat qty of 0 -- api.webull_orders.OrderAdapter never deletes the leg entry
    # itself, only zeroes it, so "empty" here means "no non-zero believed qty".
    believed = _believed_dict_from_lines(lines)
    assert all(abs(p.get("qty", 0)) < 1e-9 for p in believed.values())
    assert "broker (live sandbox query): {}" in "\n".join(lines)


# ── redaction ───────────────────────────────────────────────────────────────────────

def test_redact_masks_long_alnum_but_not_generic_pure_digit_id():
    # Deliberately NOT shaped like any real vendor key prefix (Stripe/AWS/GitHub/etc.)
    # -- GitHub's push-protection secret scanner flagged an earlier "sk_live_..." fixture
    # here as a live Stripe key and rejected the push, even though it was fake test data.
    # 2026-09-14: account_id is now ALWAYS redacted regardless of shape (see the two
    # tests below) -- this test covers a DIFFERENT long purely-numeric id (e.g. an
    # epoch-ish timestamp) that is not labelled account_id, which still stays readable.
    secret = "NOTAREALSECRETVALUE1234567890ABCDEFGHIJK"
    msg = f"401 rejected, x-app-key={secret}, place_time=1789401892218181648"
    out = WS._redact(msg)
    assert secret not in out
    assert "redacted" in out
    assert "1789401892218181648" in out      # a long purely-numeric id is not a secret


def test_redact_masks_account_id_even_when_purely_numeric():
    # "Redact all account_id values" is unconditional -- unlike a generic long numeric
    # id (above), account_id is redacted BY NAME regardless of digit-purity, so even a
    # hypothetical all-digit account_id can never slip through the way the real
    # mostly-digit one did (see the next test).
    msg = "401 rejected, account_id=863417315629211648"
    out = WS._redact(msg)
    assert "863417315629211648" not in out
    assert "redacted" in out


def test_redact_masks_mostly_digit_account_id_from_the_live_smoke_test(tmp_path):
    # Regression for the 2026-09-14 12:04 ET LIVE smoke test: one account_id printed
    # un-redacted because it was letters+digits, MOSTLY digits (one letter followed by
    # 18 digits, 19 characters) -- not pure-digit (so the old isdigit() exemption did
    # not apply to it) but also short of the OLD 24-character redaction floor, so it
    # matched nothing and printed in full. The account NUMBER's last-4 (a DIFFERENT
    # field, always pre-truncated by the caller before it ever reaches _redact) stays
    # readable exactly as before.
    account_id = "X123456789012345678"       # 1 letter + 18 digits = 19 chars
    msg = f"  [1] type=CASH  account_number=...1234  account_id={account_id}"
    out = WS._redact(msg)
    assert account_id not in out
    assert "redacted" in out
    assert "...1234" in out


def test_redact_masks_account_id_in_json_style_result_dict():
    # _safe_repr() renders adapter result dicts (place/cancel/status) via json.dumps --
    # confirms the by-name redaction also catches the `"account_id": "..."` shape that
    # style produces, not just this module's own `account_id=...` f-strings.
    rec = {"ok": True, "sent": True, "mode": "PAPER",
          "account_id": "X123456789012345678", "client_order_id": "SMOKE-abc"}
    msg = WS._safe_repr("      place result", rec)
    out = WS._redact(msg)
    assert "X123456789012345678" not in out
    assert "redacted" in out
    assert "SMOKE-abc" in out                # an unrelated short field stays untouched


def test_redact_leaves_file_paths_readable(tmp_path):
    # A real failure (test_check_missing_keys_exits_nonzero) surfaces the missing
    # file's path in the reason string -- that path must stay legible so the owner
    # knows what to go create, even though its underscore-joined basename is long.
    cfg = _cfg(tmp_path, with_keys=False)
    lines = []
    WS.cmd_check(cfg=cfg, out=lines.append)
    joined = "\n".join(lines)
    assert str(tmp_path) in joined
    assert "paper_keys.json" in joined
    assert "redacted" not in joined.lower()


def test_no_credential_strings_leak_from_sdk_errors(tmp_path, monkeypatch):
    # Deliberately NOT shaped like any real vendor key prefix (Stripe/AWS/GitHub/etc.)
    # -- GitHub's push-protection secret scanner flagged an earlier "sk_live_..." fixture
    # here as a live Stripe key and rejected the push, even though it was fake test data.
    secret = "NOTAREALSECRETVALUE1234567890ABCDEFGHIJK"
    cfg = _cfg(tmp_path, app_key="AK", app_secret="AS")
    client = MagicMock()
    client.account_v2.get_account_list.side_effect = RuntimeError(
        f"401 signed request rejected, x-app-key={secret}")
    _use_mock_client(monkeypatch, client)

    lines = []
    rc = WS.cmd_check(cfg=cfg, out=lines.append, sleep_fn=lambda *_: None)
    assert rc != 0
    joined = "\n".join(lines)
    assert secret not in joined
    assert "redacted" in joined.lower()


def test_no_credential_strings_in_happy_path_output(tmp_path, monkeypatch):
    # Long and fake, but deliberately NOT shaped like any real vendor key prefix -- see
    # the comment on the same pattern in test_redact_masks_long_alnum_but_not_pure_digits.
    app_key = "NOTAREALAPPKEY1234567890ABCDEFGHIJKLMNOP"
    app_secret = "NOTAREALAPPSECRET1234567890ABCDEFGHIJKLM"
    cfg = _cfg(tmp_path, app_key=app_key, app_secret=app_secret)
    client = _mock_client()
    _use_mock_client(monkeypatch, client)

    lines = []
    rc_check = WS.cmd_check(cfg=cfg, out=lines.append, sleep_fn=lambda *_: None)
    rc_order = WS.cmd_order_test(cfg=cfg, out=lines.append, host_fn=_sandbox_host,
                                 price_fn=_fixed_price, sleep_fn=lambda *_: None)
    rc_pos = WS.cmd_positions(cfg=cfg, out=lines.append)
    assert rc_check == 0 and rc_order == 0 and rc_pos == 0

    joined = "\n".join(lines)
    assert app_key not in joined
    assert app_secret not in joined
