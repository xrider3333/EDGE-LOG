"""Tests for api/paper_reconcile.py's signal-name -> leg mapping.

ROLL_AUDIT.md ("Urgent (live/paper)" item 7, (V)) found that the reconcile mapped every
NT8 'EQ' fill to ENGUQ_ER, although EdgeLogENGUQ1m has run the #335 (R2) settings since
2026-09-08 (commit f484c0e). That made every EQ fill from 09-08 on land in ENGUQ_ER's
live_only bucket while ENGUQ_335's matching shadow trades sat in shadow_only -- a real
fill and a real shadow trade, permanently reported as two divergences instead of one
match. These tests pin the fix: EQ resolves by date, NZ and ORB stay fixed.
"""
from datetime import date

from api import paper_reconcile as PR


def test_eq_before_switch_maps_to_enguq_er():
    assert PR.leg_from_signal("EQ", trade_date=date(2026, 9, 7)) == "ENGUQ_ER"
    # String dates (as gate_audit's date_et arrives) work the same way.
    assert PR.leg_from_signal("EQL2", trade_date="2026-08-21") == "ENGUQ_ER"


def test_eq_on_and_after_switch_maps_to_enguq_335():
    assert PR.leg_from_signal("EQ", trade_date=date(2026, 9, 8)) == "ENGUQ_335"
    assert PR.leg_from_signal("EQ", trade_date=date(2026, 9, 16)) == "ENGUQ_335"
    assert PR.leg_from_signal("EQ", trade_date="2026-09-16") == "ENGUQ_335"


def test_eq_with_no_date_defaults_to_current_leg():
    # A caller that cannot supply a date (there should be none left in this file) still
    # gets today's leg rather than the retired one or None.
    assert PR.leg_from_signal("EQ", trade_date=None) == "ENGUQ_335"
    assert PR.leg_from_signal("EQ") == "ENGUQ_335"


def test_nz_and_orb_are_unchanged_and_not_date_dependent():
    assert PR.leg_from_signal("NZ", trade_date=date(2020, 1, 1)) == "NOISE_H_RF"
    assert PR.leg_from_signal("NZL1", trade_date=date(2026, 9, 20)) == "NOISE_H_RF"
    assert PR.leg_from_signal("ORB", trade_date=date(2020, 1, 1)) == "ORB"
    assert PR.leg_from_signal("ORBR6", trade_date=date(2026, 9, 20)) == "ORB"


def test_eq_no_longer_a_static_signal_prefix_entry():
    # EQ is resolved specially in _map_signal; it must not also sit in the static table,
    # or a future edit to SIGNAL_PREFIX could silently override the date-aware branch.
    assert "EQ" not in PR.SIGNAL_PREFIX


def test_unknown_signal_returns_none():
    assert PR.leg_from_signal("", trade_date=date(2026, 9, 16)) is None
    assert PR.leg_from_signal(None, trade_date=date(2026, 9, 16)) is None
    assert PR.leg_from_signal("XYZ", trade_date=date(2026, 9, 16)) is None


def test_match_day_attributes_post_switch_eq_fill_to_enguq_335():
    """End-to-end: match_day must not leave a real EQ fill/shadow pair split across
    ENGUQ_ER (live_only) and ENGUQ_335 (shadow_only) for a post-09-08 date."""
    shadow_by_leg = {
        "ENGUQ_335": [{"entryIso": "2026-09-16T05:44:00-04:00", "side": 1,
                        "pnl_usd": -2982.64}],
        "ENGUQ_ER": [],
    }
    live_trades = [{"date": "2026-09-16", "entryTime": "05:44", "type": "long",
                     "signal": "EQ", "pnl": -2982.64}]
    rec = PR.match_day(shadow_by_leg, live_trades)
    assert len(rec["legs"]["ENGUQ_335"]["matched"]) == 1
    assert rec["legs"]["ENGUQ_335"]["shadow_only"] == []
    assert rec["legs"]["ENGUQ_ER"]["live_only"] == []
    assert rec["unattributed"] == []


def test_match_day_attributes_pre_switch_eq_fill_to_enguq_er():
    shadow_by_leg = {
        "ENGUQ_335": [],
        "ENGUQ_ER": [{"entryIso": "2026-08-20T09:45:00-04:00", "side": 1,
                       "pnl_usd": 500.0}],
    }
    live_trades = [{"date": "2026-08-20", "entryTime": "09:45", "type": "long",
                     "signal": "EQ", "pnl": 500.0}]
    rec = PR.match_day(shadow_by_leg, live_trades)
    assert len(rec["legs"]["ENGUQ_ER"]["matched"]) == 1
    assert rec["legs"]["ENGUQ_335"]["shadow_only"] == []
