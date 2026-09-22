"""api/qqq_exec.py's ENGINE-vs-BROKER parity (feature #56, 2026-09-22).

WHY. The QQQ/Webull paper book's config runs signal_source="engine" -- there is no
NinjaTrader fill for the OLD _trade_parity/_parity_summary to compare against, so every
row read "insufficient NT fill data to check parity" and index.html's parityChip
painted that non-empty note red on every single trade (owner: "why are we comparing to
NT... for parity shouldn't it just be EL OHLC values to Webull?"). _trade_parity /
_parity_summary are UNCHANGED by this feature -- these tests cover the NEW, separate
read: the engine's own booked price vs the best broker-side truth available (a real
Webull fill, else the tape-repriced price), with an explicit "not checked" state that
is never treated as a failure.

No network, no real EDGELOG_HOME: every test builds its own trades.csv-shaped row
dicts and broker_orders.csv-shaped lookup dicts by hand (or via the real
_broker_signal_id, so the derived ids are guaranteed identical to production).
"""
from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731


# ── helpers ──────────────────────────────────────────────────────────────────────────

def _trade_id(leg="ORB", stamp="20260921T093100Z", side="L"):
    return f"{leg}-{stamp}-{side}"


def _engine_row(trade_id, side="long", shares="10", entry_px="700.0", exit_px="705.0",
                pnl="50.0", signal_source="engine", **extra):
    row = {"leg": "ORB", "trade_id": trade_id, "side": side, "shares": shares,
          "entry_px": entry_px, "exit_px": exit_px, "pnl": pnl,
          "signal_source": signal_source}
    row.update(extra)
    return row


def _broker_row(trade_id, intent, broker_fill_px, ok=True, resend=0):
    """One broker_orders.csv-shaped row, using the REAL _broker_signal_id so it groups
    under exactly the key production code would derive."""
    signal_id = qe._broker_signal_id(None, None, intent, trade_id=trade_id)
    if resend:
        signal_id = f"{signal_id}R{resend}"
    return {"signal_id": signal_id, "leg": "ORB", "intent": intent,
           "ok": "True" if ok else "False", "sent": "True",
           "broker_fill_px": "" if broker_fill_px is None else str(broker_fill_px)}


def _by_base(*rows):
    return qe._broker_orders_by_base(list(rows))


# ── _broker_trade_parity: webull fill path ──────────────────────────────────────────

def test_webull_fill_used_and_ok_within_tolerance():
    tid = _trade_id()
    row = _engine_row(tid, pnl="49.70")
    by_base = _by_base(_broker_row(tid, "OPEN", 700.02), _broker_row(tid, "CLOSE", 704.99))
    out = qe._broker_trade_parity(row, by_base, log=NOOP)
    assert out["broker_entry_source"] == "webull_fill"
    assert out["broker_exit_source"] == "webull_fill"
    assert out["broker_parity_source"] == "webull_fill"
    assert out["broker_slip_entry_ps"] == 0.02
    assert out["broker_slip_exit_ps"] == -0.01
    assert out["broker_parity_ok"] is True
    assert out["broker_parity_note"] == ""


def test_webull_fill_genuine_mismatch_fails_and_says_why():
    """A discrepancy far beyond plausible QQQ slippage (a bad print / mismatched fill,
    not ordinary execution slippage) must still read as a genuine parity failure --
    the owner's ask was to stop false-flagging NORMAL trades, not to stop flagging
    real ones."""
    tid = _trade_id()
    row = _engine_row(tid, pnl="50.0")  # engine believes it made $50
    by_base = _by_base(_broker_row(tid, "OPEN", 650.00), _broker_row(tid, "CLOSE", 705.00))
    out = qe._broker_trade_parity(row, by_base, log=NOOP)
    assert out["broker_parity_ok"] is False
    assert "tracking error" in out["broker_parity_note"]
    assert out["broker_track_err_usd"] == -500.0


def test_broker_fill_ignored_when_order_row_not_ok():
    """A BLOCKED/failed broker order still has a signal_id row, but no real fill --
    must fall through to the next source (here, nothing else available -> not checked)
    rather than trusting a price that was never actually paid."""
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(_broker_row(tid, "OPEN", 700.02, ok=False),
                      _broker_row(tid, "CLOSE", 704.99, ok=False))
    out = qe._broker_trade_parity(row, by_base, log=NOOP)
    assert out["broker_parity_ok"] is None
    assert out["broker_entry_source"] is None


# ── _broker_trade_parity: reprice (tape) fallback ───────────────────────────────────

def test_reprice_fallback_used_when_no_broker_order_at_all():
    tid = _trade_id()
    row = _engine_row(tid, pnl="50.0", real_entry_px="700.10", real_exit_px="705.05")
    out = qe._broker_trade_parity(row, _by_base(), log=NOOP)
    assert out["broker_entry_source"] == "repriced_tape"
    assert out["broker_exit_source"] == "repriced_tape"
    assert out["broker_parity_source"] == "repriced_tape"
    # matches tools/qqq_reprice.py's own sign convention: real - engine.
    assert out["broker_slip_entry_ps"] == 0.10
    assert out["broker_slip_exit_ps"] == 0.05


def test_mixed_source_when_only_one_leg_has_a_broker_fill():
    """A resend posted after the nightly reprice already ran can leave one leg with a
    real Webull fill and the other only with a repriced tape price."""
    tid = _trade_id()
    row = _engine_row(tid, pnl="50.0", real_exit_px="705.05")
    by_base = _by_base(_broker_row(tid, "OPEN", 700.10))  # no CLOSE order captured
    out = qe._broker_trade_parity(row, by_base, log=NOOP)
    assert out["broker_entry_source"] == "webull_fill"
    assert out["broker_exit_source"] == "repriced_tape"
    assert out["broker_parity_source"] == "mixed"


# ── _broker_trade_parity: the "not checked" state (never an error) ─────────────────

def test_not_checked_when_nothing_is_available():
    row = _engine_row(_trade_id())  # no broker order, no reprice fields
    out = qe._broker_trade_parity(row, _by_base(), log=NOOP)
    assert out["broker_parity_ok"] is None
    assert "not checked" in out["broker_parity_note"]
    assert "not checked" in out["broker_parity_note"].lower()


def test_not_checked_when_trade_has_no_trade_id():
    """A trades.csv row closed before feature #56 shipped has no trade_id at all --
    must degrade to not-checked, never raise, never fabricate a match."""
    row = _engine_row("")
    out = qe._broker_trade_parity(row, _by_base(_broker_row(_trade_id(), "OPEN", 700.0)),
                                  log=NOOP)
    assert out["broker_parity_ok"] is None


def test_broker_trade_parity_never_raises_on_garbage_row():
    out = qe._broker_trade_parity({}, {}, log=NOOP)
    assert out["broker_parity_ok"] is None
    out2 = qe._broker_trade_parity({"shares": "not-a-number", "trade_id": "x"}, {}, log=NOOP)
    assert out2["broker_parity_ok"] is None


# ── resend / id matching (_signal_id_base, _best_broker_row, _broker_order_for) ─────

def test_signal_id_base_strips_resend_suffix_only():
    assert qe._signal_id_base("qxENGUQ33520260921T171000ZLCR1") == \
        "qxENGUQ33520260921T171000ZLC"
    assert qe._signal_id_base("qxENGUQ33520260921T171000ZLC") == \
        "qxENGUQ33520260921T171000ZLC"


def test_best_broker_row_prefers_a_later_successful_resend():
    tid = _trade_id()
    blocked = _broker_row(tid, "OPEN", None, ok=False)
    resent = _broker_row(tid, "OPEN", 700.25, ok=True, resend=1)
    by_base = _by_base(blocked, resent)
    row = _engine_row(tid, pnl="47.75")
    out = qe._broker_trade_parity(row, by_base, log=NOOP)
    assert out["broker_entry_px"] == 700.25
    assert out["broker_entry_source"] == "webull_fill"


def test_broker_order_for_returns_none_without_trade_id():
    assert qe._broker_order_for("", "OPEN", _by_base()) is None
    assert qe._broker_order_for(None, "OPEN", _by_base()) is None


# ── _broker_parity_summary ──────────────────────────────────────────────────────────

def test_broker_parity_summary_counts_checked_ok_failed_not_checked():
    rows = [
        {"broker_parity_ok": True, "broker_track_err_usd": 0.1, "signal_source": "engine"},
        {"broker_parity_ok": False, "broker_track_err_usd": -12.0, "signal_source": "engine",
         "broker_parity_note": "tracking error too big"},
        {"broker_parity_ok": None, "signal_source": "engine"},
    ]
    out = qe._broker_parity_summary(rows)
    assert out["checked"] == 2
    assert out["ok"] == 1
    assert out["failed"] == 1
    assert out["not_checked"] == 1
    assert out["worst_err_usd"] == -12.0
    assert "worst" in out["note"]


def test_broker_parity_summary_skips_ninjatrader_rows():
    """A genuine NT-mirrored row must never count toward the engine-vs-broker tally,
    even if (by construction/a bug) it somehow carried a broker_parity_ok value."""
    rows = [
        {"broker_parity_ok": False, "signal_source": "ninjatrader"},
        {"broker_parity_ok": True, "broker_track_err_usd": 0.0, "signal_source": "engine"},
    ]
    out = qe._broker_parity_summary(rows)
    assert out["checked"] == 1
    assert out["failed"] == 0
    assert out["ok"] == 1


def test_broker_parity_summary_all_not_checked_note_is_not_an_error():
    out = qe._broker_parity_summary(
        [{"broker_parity_ok": None, "signal_source": "engine"}] * 3)
    assert out["checked"] == 0
    assert out["failed"] == 0
    assert "not an error" in out["note"]


# ── _apply_broker_parity: the row-dispatch rule (NT rows genuinely untouched) ───────

def test_apply_broker_parity_leaves_ninjatrader_rows_with_nt_parity_intact():
    """The exact requirement: a row that genuinely mirrors NinjaTrader keeps ITS OWN
    parity_ok/parity_note (whatever _trade_parity already computed, elsewhere in
    _build_doc) completely untouched by this feature -- it only gets a clear
    "n/a" placeholder in the NEW broker_* fields, never a fabricated broker read."""
    nt_row = {"signal_source": "ninjatrader", "parity_ok": True, "parity_note": ""}
    engine_row = _engine_row(_trade_id(), real_entry_px="700.1", real_exit_px="705.05",
                             pnl="50.0")
    trades_all = [dict(nt_row), engine_row]
    qe._apply_broker_parity(trades_all, _by_base(), log=NOOP)

    nt_out = trades_all[0]
    assert nt_out["parity_ok"] is True and nt_out["parity_note"] == "", \
        "NT parity fields must be untouched by the new feature"
    assert nt_out["broker_parity_ok"] is None
    assert nt_out["broker_parity_note"] == qe._NT_MIRROR_NOTE

    eng_out = trades_all[1]
    assert eng_out["broker_parity_source"] == "repriced_tape"
    assert eng_out["broker_parity_ok"] is True
