# -*- coding: utf-8 -*-
"""Static checks on pine/POINT_SCORE_1_0.pine v1.4 (owner 2026-10-13: the 5m cell read red while price sat above the
5m 200 line - the Auto side had flipped to SHORT, and red meant 'missed for a short'). TradingView is the only Pine
compiler, so these tests pin the display contract and the live-snapshot plumbing, not the compiled behaviour."""
import os
import re

PINE = os.path.join(os.path.dirname(__file__), "..", "pine", "POINT_SCORE_1_0.pine")


def _src():
    return open(PINE, encoding="utf-8").read().replace("\r\n", "\n")


def _table_block(s):
    return s[s.index("if barstate.islast\n"):]


def test_arrow_helper_says_where_price_is():
    s = _src()
    assert 'f_arrow(float c, float lvl) => na(c) or na(lvl) ? "" : (c > lvl ? " ▲" : (c < lvl ? " ▼" : " ="))' in s


def test_compact_cells_carry_arrows_against_the_signal_close():
    t = _table_block(_src())
    # the four averages: close (tR index 13) against each average (tR index k)
    assert "array.get(CMP, k) + f_arrow(array.get(tR, 13), array.get(tR, k))" in t
    # yesterday's low / close / high get arrows; body and volume (k = 7, 8) have no level
    assert "(k < 7 ? f_arrow(array.get(tR, 13), array.get(tR, k)) : \"\")" in t


def test_side_is_spelled_out():
    s = _src()
    assert 'f_sideTxt(bool isL) => isL ? "LONG" : "SHORT"' in s
    t = _table_block(s)
    assert 'f_sideTxt(snapLong) + " " + f_sc(array.get(sv, 10), array.get(sv, 11))' in t      # Compact header
    assert 'f_sideTxt(snapLong) + " " + f_sc(tot, mx)' in t                                     # Minimal badge
    assert '(snapLong ? "L " : "S ")' not in t and '(snapLong ? " L" : " S")' not in t


def test_green_red_still_mean_hit_miss_for_the_side():
    s = _src()
    assert "f_col(float h) => na(h) ? C_NA : (h > 0.5 ? C_HIT : C_MISS)" in s
    t = _table_block(s)
    assert "array<float> sv = snapLong ? tL : tS" in t


def test_live_closed_minute_snapshot_above_one_minute():
    s = _src()
    assert "bool aboveMin = timeframe.in_seconds() > 60" in s
    for v in ("varip string lvPack", "varip int    lvT", "varip string rtPack", "varip int    rtT"):
        assert v in s
    assert "if aboveMin and barstate.isrealtime and not na(oSigT)" in s
    assert "if not na(lvT) and oSigT > lvT" in s
    t = _table_block(s)
    assert "if not na(rtT) and rtPack != \"\" and (na(snapT) or rtT > snapT)" in t
    assert "if array.size(rtParts) == 4" in t
    # the table reads only the chosen snapshot (t*), never the confirmed arrays directly after the choice
    body = t[t.index("float snapSide"):]
    assert not re.search(r"\bsnap[LSRNT]\b", body)


def test_pack_round_trip_tokens():
    s = _src()
    assert '(na(x) ? "na" : str.tostring(x, "#.##########"))' in s
    assert 'array.push(a, t == "na" ? na : str.tonumber(t))' in s


def test_score_labels_alerts_unchanged():
    s = _src()
    # the scoring core, the labels and the alerts still gate on the confirmed 1-minute signal bar
    assert 'request.security(syminfo.tickerid, "1", f_core(sigOff)' in s
    assert "if showLbl and barstate.isconfirmed and newSig and sigInBar and autoTot >= labThr" in s
    assert s.count("barstate.isconfirmed and newSig and sigInBar") >= 4


def test_brackets_balance():
    s = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', _src())
    s = re.sub(r"//[^\n]*", "", s)
    for a, b in ("()", "[]"):
        assert s.count(a) == s.count(b), (a, s.count(a), s.count(b))
