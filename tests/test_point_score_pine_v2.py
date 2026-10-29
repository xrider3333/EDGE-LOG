# -*- coding: utf-8 -*-
"""Static checks on pine/POINT_SCORE_2_0.pine (owner 2026-10-29: visual redesign, labels off, plain words). TradingView
is the only Pine compiler, so these pin the display contract and that the score / alerts / parity export are v1.4's."""
import os
import re

HERE = os.path.dirname(__file__)
V2 = os.path.join(HERE, "..", "pine", "POINT_SCORE_2_0.pine")
V1 = os.path.join(HERE, "..", "pine", "POINT_SCORE_1_0.pine")


def _src(p):
    return open(p, encoding="utf-8").read().replace("\r\n", "\n")


def _between(s, a, b):
    return s[s.index(a):s.index(b, s.index(a))]


def test_title_and_defaults():
    s = _src(V2)
    assert 'indicator("EDGELOG Point Score 2.0"' in s
    assert 'showLbl   = input.bool(false, "Show labels on bars"' in s
    assert 'input.string("Plain words", "Display", options = ["Plain words", "Compact", "Minimal", "Full"]' in s
    assert 'showStrip = input.bool(false,' in s and 'showYLn   = input.bool(false,' in s


def test_plain_words_layout():
    s = _src(V2)
    t = _between(s, 'if layout == "Plain words"', 'else if layout == "Compact"')
    assert '"Trend averages (" + str.tostring(emaLen) + " " + maType + ")"' in t
    assert '(sideIn == "Auto" ? "  (auto side)" : "  (forced side)")' in t
    for word in ('"Yesterday"', '"This candle"'):
        assert word in t
    assert '"Low", "Close", "High", "Big body", "Big volume"' in s
    assert "Y-L" not in t and "Y-C" not in t and "Y-H" not in t
    assert t.count("tooltip = array.get(PLAIN_TIP, k)") == 3
    # badge: green 7+, yellow 5-6, grey under 5
    assert "(tot >= 7 ? C_GOOD : (tot >= 5 ? C_MID : C_NA))" in t
    assert "size.large" in t


def test_score_alerts_and_export_unchanged():
    a, b = _src(V1), _src(V2)
    # everything from the inputs' constants through the live snapshot = the score engine
    core = ("// -- Constants", "// -- Short names")
    assert _between(a, *core) == _between(b, *core)
    alerts = ("// -- Alerts", "// -- Table: the 1-minute bar")
    a_al = _between(a, *alerts)
    b_al = _between(b, *alerts)
    b_al = b_al[:b_al.index("// -- v2.0 optional chart marks")]
    assert a_al == b_al
    assert "if showLbl and barstate.isconfirmed and newSig and sigInBar and autoTot >= labThr" in b


def test_new_marks_stay_off_the_export():
    s = _src(V2)
    marks = _between(s, "// -- v2.0 optional chart marks", "// -- Table: the 1-minute bar")
    assert marks.count("display = display.pane") == 4
    assert "display.data_window" not in marks


def test_brackets_balance():
    s = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', _src(V2))
    s = re.sub(r"//[^\n]*", "", s)
    for a, b in ("()", "[]"):
        assert s.count(a) == s.count(b), (a, s.count(a), s.count(b))
