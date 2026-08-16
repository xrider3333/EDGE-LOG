#!/usr/bin/env python3
"""
tools/allpools_render_test.py -- render test for the two 1A cross-pool charts.

WHY THIS EXISTS
    tools/preflight_boot.py only proves index.html BOOTS. It renders the app
    shell, not a run report -- and the report builders are the part that keeps
    breaking (v64.24 shipped a _dOpts crash straight past the boot gate; v73.62
    shipped a block-scope crash the same way). The run reports themselves live
    in Firestore behind a login, so they cannot be rendered in CI.

    This gate closes the gap for the two charts on the 1A card that were rebuilt
    for the "ALL POOLS / PNL vs DD" work: it lifts mtxScatterHtml + mtxBarsHtml
    (and the _mtxPoolCol / _mtxSampBar / _mtxLegend helpers they sit on) VERBATIM
    out of index.html, drops them into a headless page next to faithful copies of
    the handful of helpers they close over, and renders them against candidate
    points shaped like real ones -- including the awkward cases a live run report
    may or may not happen to contain that day (a losing candidate, a zero
    drawdown, a quote in a label, an unknown pool name).

    It asserts on the RESULT, not on the source text, so it fails on a runtime
    throw, a swallowed exception, a pool that renders grey, an axis that never
    got drawn, or a bar row that splits back into two rows.

Exit codes: 0 = PASS, 1 = FAIL, 2 = INCONCLUSIVE (chrome missing / timed out).

Usage:
  python tools/allpools_render_test.py
  python tools/allpools_render_test.py --keep   # leave the harness html on disk
"""
import argparse
import html as _html
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preflight_boot import find_chrome  # noqa: E402  (same repo, same dir)

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, 'index.html')
HARNESS = os.path.join(REPO, 'tools', '_allpools_probe.html')

# Helpers the two charts close over, lifted straight out of index.html rather
# than re-implemented here -- a stub that drifts from the real helper turns this
# gate into a test of the stub.
BORROWED = ['fmtUsd', 'fmtAx', 'c2Txt', 'c2YTitle', '_ctlChip', '_sampChips', '_segsOf']


def read_index():
    with open(INDEX, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def lift_const(src, name):
    """Return the WHOLE `const <name>= ... ;` statement, however many lines it
    spans. Several of these helpers (_sampChips, _segsOf) are multi-line, and
    lifting only their first line produces a file that fails to parse -- with no
    error anywhere, because a script with a syntax error simply never runs.

    Scan forward from the declaration and stop at the first line that both ends
    in `;` and leaves every bracket balanced. Bracket counting is string-aware
    because these one-liners embed CSS in string literals (`color-mix(in srgb,
    ...)`), whose parens would otherwise be counted. Only single quotes and
    backticks delimit strings in this file -- a double quote only ever appears
    INSIDE one, or inside a `/"/g` regex -- so treating `"` as an ordinary
    character is both correct here and avoids needing a regex-literal parser.
    """
    m = re.search(r'^[ \t]*const %s=' % re.escape(name), src, re.M)
    if not m:
        raise LookupError('could not find `const %s=` in index.html' % name)
    i, depth, quote, esc = m.start(), 0, None, False
    while i < len(src):
        c = src[i]
        if esc:
            esc = False
        elif quote:
            if c == '\\':
                esc = True
            elif c == quote:
                quote = None
        elif c in "'`":
            quote = c
        elif c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == ';' and depth == 0:
            j = src.index('\n', i) if '\n' in src[i:] else len(src)
            if not src[i + 1:j].strip():          # `;` is the last thing on its line
                return src[m.start():i + 1].strip()
        i += 1
    raise LookupError('never found the end of `const %s=`' % name)


def lift_block(src):
    """Return the verbatim source from `const _mtxPoolCol=` through the closing
    `};` of mtxBarsHtml -- i.e. everything this test is actually gating."""
    start = src.index('    const _mtxPoolCol=')
    bars = src.index('    const mtxBarsHtml=', start)
    end = src.index('\n    };\n', bars) + len('\n    };\n')
    return src[start:end]


# Candidate points shaped exactly like the ones selectionTableHtml / gvParts
# push onto scatterPts. Deliberately includes the cases a given day's run may
# not: a LOSING candidate (its net bar has to run left, over the drawdown bar),
# a zero-drawdown candidate (the x scale must not divide by it), a candidate
# whose label carries a double quote (it is injected into data-tip="..."), and
# an unknown pool name (must not throw, just fall back to grey).
POINTS = [
    {"pool": "RAW", "label": "R1 · #12", "pnl": 78822, "dd": 47955, "key": "raw:0", "crowned": True},
    {"pool": "RAW", "label": "R2 · #33", "pnl": -4486, "dd": 18142, "key": "raw:1", "crowned": False},
    {"pool": "RAW", "label": "R8 · #263", "pnl": -9218, "dd": 18736, "key": "raw:7", "crowned": False},
    {"pool": "RAW", "label": 'R9 " quote', "pnl": 12040, "dd": 9000, "key": "raw:8", "crowned": False},
    {"pool": "GATE", "label": "ET 55%", "pnl": -30026, "dd": 39677, "key": "gate:18", "crowned": False},
    {"pool": "GATE", "label": "TREE 60%", "pnl": 1046, "dd": 1517, "key": "gate:13", "crowned": False},
    {"pool": "GATE", "label": "RF 55%", "pnl": 40311, "dd": 22000, "key": "gate:2", "crowned": False},
    {"pool": "TILT", "label": "xgb (ST)", "pnl": 25110, "dd": 31200, "key": "tilt:0", "crowned": False},
    {"pool": "TILT", "label": "logistic (SL)", "pnl": 6120, "dd": 0, "key": "tilt:5", "crowned": False},
    {"pool": "HYBRID", "label": "et", "pnl": -31416, "dd": 40565, "key": "hyb:4", "crowned": False},
    {"pool": "HYBRID", "label": "logistic", "pnl": 4856, "dd": 26140, "key": "hyb:3", "crowned": False},
    {"pool": "MYSTERY", "label": "unknown pool", "pnl": 500, "dd": 500, "key": "zzz:0", "crowned": False},
]

HARNESS_TMPL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>allpools probe</title></head>
<body style="margin:0;background:#0a0a0a">
<div id="host"></div><pre id="o"></pre>
<script>
(function(){
  var out={};
  try{
    // ---- helpers lifted verbatim from index.html ----
    var APREF=__APREF__;
    __BORROWED__
    var C2W=560,C2R=46,C2P=C2W-C2R;
    // ---- the code under test, lifted verbatim from index.html ----
__BLOCK__
    // ---- render ----
    var PTS=__POINTS__;
    var host=document.getElementById('host');
    var sc=mtxScatterHtml(PTS), bars=mtxBarsHtml(PTS);
    host.innerHTML='<div id="sc">'+sc+'</div><div id="bars">'+bars+'</div>';
    var scEl=document.getElementById('sc'), barEl=document.getElementById('bars');
    var circles=[].slice.call(scEl.querySelectorAll('circle[data-mtxsc]'));
    var barRows=[].slice.call(barEl.querySelectorAll('[data-mtxsc]'));
    var fills={};
    circles.forEach(function(c){var k=c.getAttribute('data-pool')+'='+c.getAttribute('fill');fills[k]=(fills[k]||0)+1;});
    var svg=scEl.querySelector('svg');
    var lines=[].slice.call(svg.querySelectorAll('line'));
    var texts=[].slice.call(svg.querySelectorAll('text')).map(function(t){return t.textContent;});
    // an axis line = full-length horizontal at the plot floor / vertical at the plot left
    var dashed=lines.filter(function(l){return l.getAttribute('stroke-dasharray');});
    out={
      ok:true,
      scatterEmpty:!sc, barsEmpty:!bars,
      nCircles:circles.length, nBarRows:barRows.length, nPoints:PTS.length,
      fills:fills,
      // every bar row must be ONE flex row carrying BOTH numbers (the owner ask)
      barRowIsFlex:barRows.map(function(r){return r.style.display;}).filter(function(v,i,a){return a.indexOf(v)===i;}),
      barRowChildCounts:barRows.map(function(r){return r.children.length;}).filter(function(v,i,a){return a.indexOf(v)===i;}),
      barRowSample:barRows.length?barRows[0].textContent.replace(/\\s+/g,' ').trim():null,
      barRowsWithTwoNumbers:barRows.filter(function(r){return (r.textContent.match(/\\$/g)||[]).length>=2;}).length,
      nDashedLines:dashed.length,
      axisTexts:texts,
      hasSampleChips:!!document.querySelector('[data-g2seg]'),
      sampleSegs:[].slice.call(document.querySelectorAll('[data-g2seg]')).map(function(e){return e.getAttribute('data-g2seg');}),
      legendPools:(function(){var m=[];[].slice.call(document.querySelectorAll('#sc span, #bars span')).forEach(function(s){
        var t=s.textContent.trim(); if(/^\\u25cf (RAW|GATE|TILT|HYBRID)$/.test(t)) m.push(t.slice(2)+':'+(s.style.color||''));}); return m;})(),
      trendText:(function(){var e=[].slice.call(document.querySelectorAll('#sc span')).filter(function(s){return /TREND/.test(s.textContent);})[0];
        return e?e.textContent.replace(/\\s+/g,' ').trim():null;})(),
      // literal-text spill check: an unescaped quote in data-tip dumps raw markup onto the page
      spill:/style=|<circle|<span style/.test(host.textContent)
    };
  }catch(e){ out={ok:false,err:String(e&&e.stack||e)}; }
  document.getElementById('o').textContent='PROBE: '+JSON.stringify(out);
})();
</script>
</body></html>
"""


def build_harness():
    src = read_index()
    borrowed = '\n    '.join(lift_const(src, n) for n in BORROWED)
    block = lift_block(src)
    html = (HARNESS_TMPL
            .replace('__APREF__', json.dumps({'g2samp': 'is,wf'}))
            .replace('__BORROWED__', borrowed)
            .replace('__BLOCK__', block)
            .replace('__POINTS__', json.dumps(POINTS)))
    with open(HARNESS, 'w', encoding='utf-8') as f:
        f.write(html)
    return len(block)


PROBE_RE = re.compile(r'PROBE:\s*(\{.*?\})\s*</pre>', re.S)


def run_probe(chrome):
    args = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
            '--virtual-time-budget=4000', '--dump-dom',
            'file:///' + HARNESS.replace('\\', '/')]
    try:
        # encoding must be forced: the rendered DOM carries the crown glyph and
        # other non-ASCII, and Python defaults stdout decoding to the Windows
        # ANSI codepage, which dies on them mid-read.
        p = subprocess.run(args, capture_output=True, text=True, timeout=60,
                           encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return None, 'chrome timed out'
    except OSError as e:
        return None, 'could not launch chrome: %s' % e
    m = PROBE_RE.search(p.stdout or '')
    if not m:
        return None, 'no PROBE marker in chrome output'
    try:
        return json.loads(_html.unescape(m.group(1))), None
    except json.JSONDecodeError as e:
        return None, 'probe JSON did not parse: %s' % e


# The funnel KEY palette (index.html _kOrder). The whole point of the colour fix
# is that these are literal hexes, so a theme like MONO -- whose --blue/--purple/
# --yellow are all greys -- cannot flatten three pools into one colour.
EXPECT_COL = {'RAW': '#1d9e75', 'GATE': '#e24b4a', 'TILT': '#f0b429', 'HYBRID': '#c084fc'}


def check(o):
    fails = []
    if not o.get('ok'):
        return ['probe threw: %s' % o.get('err')]
    if o.get('scatterEmpty'):
        fails.append('mtxScatterHtml returned empty')
    if o.get('barsEmpty'):
        fails.append('mtxBarsHtml returned empty')
    if o.get('nCircles') != o.get('nPoints'):
        fails.append('scatter drew %s dots for %s points' % (o.get('nCircles'), o.get('nPoints')))
    if o.get('nBarRows') != o.get('nPoints'):
        fails.append('bars drew %s rows for %s points' % (o.get('nBarRows'), o.get('nPoints')))

    # --- colours: every known pool on its funnel hex, none on a theme var ---
    for pool, hexc in EXPECT_COL.items():
        key = '%s=%s' % (pool, hexc)
        if key not in (o.get('fills') or {}):
            fails.append('pool %s is not painted %s (got %s)'
                         % (pool, hexc, sorted((o.get('fills') or {}).keys())))
    for k in (o.get('fills') or {}):
        if 'var(--' in k and not k.startswith('MYSTERY'):
            fails.append('pool colour still resolves through a theme variable: %s '
                         '(mono theme flattens those to grey)' % k)

    # --- bars: ONE row per candidate, carrying BOTH dollar figures ---
    if o.get('barRowIsFlex') != ['flex']:
        fails.append('bar rows are not a single flex row (display: %s)' % o.get('barRowIsFlex'))
    if o.get('barRowsWithTwoNumbers') != o.get('nBarRows'):
        fails.append('only %s of %s bar rows carry BOTH the DD and the net $ figure'
                     % (o.get('barRowsWithTwoNumbers'), o.get('nBarRows')))

    # --- axes + trend (the owner ask) ---
    texts = o.get('axisTexts') or []
    if not any('NET PNL' in t for t in texts):
        fails.append('no NET PNL axis title in the scatter')
    if not any('DRAWDOWN' in t for t in texts):
        fails.append('no DRAWDOWN axis title in the scatter')
    dollar_ticks = [t for t in texts if t.strip().startswith('$') or t.strip().startswith('-$')]
    if len(dollar_ticks) < 4:
        fails.append('expected reference values on both axes, found %d $ labels' % len(dollar_ticks))
    if not o.get('nDashedLines'):
        fails.append('no dashed trend line drawn')
    if not o.get('trendText'):
        fails.append('no trend readout (slope / r-squared) rendered')

    # --- sample toggles ---
    if not o.get('hasSampleChips'):
        fails.append('no SAMPLE chips rendered on the charts')
    if sorted(set(o.get('sampleSegs') or [])) != ['is', 'lb', 'wf']:
        fails.append('SAMPLE chips are not IS/WF/LB (got %s)' % o.get('sampleSegs'))

    if o.get('spill'):
        fails.append('raw markup spilled into the page text (an unescaped quote in data-tip)')
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--keep', action='store_true', help='leave the harness html on disk')
    a = ap.parse_args(argv)

    chrome = find_chrome()
    if not chrome:
        print('ALLPOOLS: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    try:
        n = build_harness()
    except (LookupError, ValueError) as e:
        print('ALLPOOLS: FAIL -- could not lift the chart code out of index.html: %s' % e)
        return FAIL
    try:
        obj, err = run_probe(chrome)
        if err:
            print('ALLPOOLS: INCONCLUSIVE -- %s' % err)
            return INCONCLUSIVE
        fails = check(obj)
        if fails:
            print('ALLPOOLS: FAIL (%d problem(s), %d chars of chart code under test)' % (len(fails), n))
            for f in fails:
                print('  - %s' % f)
            print('  probe: %s' % json.dumps(obj)[:1500])
            return FAIL
        print('ALLPOOLS: PASS (%d chars of chart code, %d dots, %d bar rows, trend=%s)'
              % (n, obj.get('nCircles'), obj.get('nBarRows'), obj.get('trendText')))
        print('  pool colours: %s' % ', '.join(sorted(obj.get('fills') or {})))
        return PASS
    finally:
        if not a.keep:
            try:
                os.remove(HARNESS)
            except OSError:
                pass


if __name__ == '__main__':
    sys.exit(main())
