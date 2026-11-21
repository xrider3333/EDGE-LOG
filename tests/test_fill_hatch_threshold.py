"""FILL HATCH THRESHOLD (owner 11-21, MANAGER ruling - the AND rule): a Webull fill hatches its WEBULL PAPER calendar /
chart day only when it is BOTH outside its delay-scaled parity band (pok 0) AND MORE than 25c a share worse than the
backtest price (design gap taken out). Three copies of that rule must
agree: the page (index.html FILL_HATCH_WORSE_PS + ledgerFillSideHatch, used by the calendar AND the chart through
qbFillHatch), the box (api/qqq_exec.py FILL_HATCH_WORSE_PS, published as fill_parity_hatch) and the render probe's
python twin (tools/webull_board_probe.py). The page's own function is run in headless Chrome on real packed fp sides.
"""
import json
import os
import re
import subprocess
import tempfile

import pytest

from api import qqq_exec as qe
from tools import webull_board_probe as wbp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, 'index.html')

# (packed side, expected) - real sides from the box doc where dated
CASES = [
    ('649.99|649.35|o|-0.64|0|-0.64|0||0.426|0|0|0', True),        # 11-19 12:05 NOISE entry 64c worse
    ('674.09|674.31|o|-0.22|0|-0.22|0||0.4234|1|0|0', False),      # 11-19 09:45 NOISE entry 22c worse
    ('722.43|721.97|o|-0.46|0|-0.46|0||0.4151|0|0|0', True),       # 10-16 NOISE entry 46c worse
    ('691.79|690.99|o|-0.8|0|-0.8|0||0.4151|0|0|0', True),         # 11-04 NOISE exit 80c worse
    ('674.92|674.24|o|-0.68|0|-0.68|0||0.4144|0|0|0', True),       # 11-05 NOISE entry 68c worse
    ('676.96|676.42|o|-0.54|0|-0.54|0||0.4165|0|0|0', True),       # 11-13 NOISE entry 54c worse
    ('679.2|678.73|o|0.47|0|0.47|0||0.4254|0|0|0', False),         # 11-13 47c BETTER: never
    ('700|700.26|o|-0.26|0|-0.26|0||0.4151|1|0|0', False),         # 26c worse but inside its 41.5c band: never (11-16 style)
    ('700|700.26|o|-0.26|0|-0.26|0||0.2|0|0|0', True),             # 26c worse, outside a narrow 20c band (sub-1 s send): hatches
    ('700|700.24|o|-0.24|0|-0.24|0||0.2|0|0|0', False),            # outside a 20c band but only 24c worse: the 25c floor binds
    ('700|700.25|o|-0.25|0|-0.25|0||0.4151|1|0|0', False),         # exactly 25c: never
    ('647.05|648.06|o|-1.01|-0.78|-0.23|0|eod|0.4151|1|0|0', False),  # 101c worse but 78c of it design: 23c slippage
    ('691.95|691.45|s|-0.5|0|0|-0.5|suspect|0.4151||1|0', None),   # 11-04 off tape: never judged
    ('671.1|669.8|o|-1.3|0|-1.3|0||1.7949|1|0|1', None),           # ORB breakout-level design: never judged
    ('678.57||n|||||nofill||||0', None),                           # no fill
    ('700|700.5|o|-0.5|0|-0.5|0||||0|0', None),                    # no band verdict: not judged
    ('700|700.5|o|-0.5|||||0.4151|0|0|0', True),                              # no slippage split: the whole edge decides
]


def _page_js():
    src = open(INDEX, encoding='utf-8').read()
    c = re.search(r"const FILL_HATCH_WORSE_PS=([0-9.]+);", src)
    f = re.search(r"function ledgerFillSideHatch\(x\)\{.*?\n\}", src, re.S)
    assert c and f, 'index.html lost FILL_HATCH_WORSE_PS / ledgerFillSideHatch'
    return float(c.group(1)), c.group(0) + '\n' + f.group(0)


def test_one_threshold_everywhere():
    page_c, _ = _page_js()
    assert page_c == pytest.approx(0.25)
    assert qe.FILL_HATCH_WORSE_PS == pytest.approx(page_c)
    assert wbp.FILL_HATCH_WORSE_PS == pytest.approx(page_c)
    src = open(INDEX, encoding='utf-8').read()
    # the calendar and the chart read the same function
    assert 'const qbFpV=qbFillHatch;' in src
    assert 'const hv=qbFillHatch(t);if(hv?(hv.band||hv.omr):qeParityFailed(t))f.par++;' in src


def test_probe_twin_matches_cases():
    for side, want in CASES:
        assert wbp._fill_side_hatch(side) is want, side


def test_box_matches_cases():
    # the box judges unpacked sides; rebuild one from the packed fields (fs 'o' only - the rest are never judged)
    for side, want in CASES:
        q = side.split('|')
        if q[2] != 'o' or q[10] == '1' or q[11] == '1':
            continue
        if q[9] not in ('0', '1'):
            continue
        n = lambda v: None if v == '' else float(v)  # noqa: E731
        s = {'edge': n(q[3]), 'dsg': n(q[4]), 'slp': n(q[5]), 'unx': n(q[6])}
        hg = qe._side_hatch_gap_ps(s)
        assert (q[9] == '0' and hg < -qe.FILL_HATCH_WORSE_PS - 1e-9) is want, side


def test_page_function_matches_cases_in_chrome():
    chrome = wbp.find_chrome()
    if not chrome:
        pytest.skip('Chrome not installed')
    _, js = _page_js()
    sides = [c[0] for c in CASES]
    html = ('<!DOCTYPE html><html><body><pre id="o"></pre><script>' + js
            + ';var S=' + json.dumps(sides) + ';document.getElementById("o").textContent='
            + '"RES:"+JSON.stringify(S.map(ledgerFillSideHatch))+":END";</script></body></html>')
    d = tempfile.mkdtemp(prefix='fillhatch_')
    p = os.path.join(d, 't.html')
    open(p, 'w', encoding='utf-8').write(html)
    out = subprocess.run([chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--user-data-dir=' + os.path.join(d, 'prof'),
                          '--dump-dom', 'file:///' + p.replace(os.sep, '/')],
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120).stdout
    m = re.search(r'RES:(.*?):END', out or '')
    if not m:
        pytest.skip('headless Chrome gave no readout')
    got = json.loads(m.group(1))
    assert got == [c[1] for c in CASES]
