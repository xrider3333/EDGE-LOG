"""The web draws a paper trade's exit line from its leg KEY alone (index.html window._legXline: a key starting with
NOISE = the VWAP, owner 2026-11-26 "do the same for the webull and nt8 trade charts"). That rule is only true while
every NOISE leg the box and NinjaTrader run closes on a bar closing across the VWAP and no other family does - this
test reads each leg's own strategy chain (api.blotter._exit_line) and fails the day that stops holding."""
import re
from pathlib import Path

import api.blotter as B
from api.cloud_signal import CROWN_LEGS
from api.paper import PAPER_LEGS

ROOT = Path(__file__).resolve().parents[1]


def _legs():
    """The NT8 / shadow legs (api.paper.PAPER_LEGS) and the Webull box's crown legs (api.cloud_signal.CROWN_LEGS)."""
    out = []
    for legs in (PAPER_LEGS, CROWN_LEGS):
        items = legs.items() if isinstance(legs, dict) else [(c.get("key") or c.get("leg"), c) for c in legs]
        out += [(str(k), c) for k, c in items if isinstance(c, dict) and c.get("strategy")]
    return out


def test_every_noise_leg_exits_on_the_vwap_and_no_other_does():
    wrong = []
    for k, c in _legs():
        got = B._exit_line(c["strategy"], c.get("params") or {})
        want = "vwap" if k.upper().startswith("NOISE") else ""
        if got != want:
            wrong.append((k, c["strategy"], got))
    assert not wrong, f"index.html window._legXline would draw the wrong exit line for: {wrong}"
    keys = {k for k, _ in _legs()}
    assert "NOISE_422" in keys and "NOISE_382" in keys          # both sources were read


def test_the_web_rule_is_the_one_this_test_checks():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    m = re.search(r"window\._legXline=leg=>(.+?);\r?\n", html)
    assert m and "indexOf('NOISE')===0" in m.group(1) and "'vwap'" in m.group(1)
