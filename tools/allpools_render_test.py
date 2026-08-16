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
BORROWED = ['fmtUsd', 'fmtAx', 'c2Txt', 'c2YTitle', '_ctlChip', '_sampChips', '_segsOf',
            '_tabBtn', '_tabStrip']


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
    """Return the verbatim source from `const MTX_HYB2=` (the first declaration the
    charts depend on) through the closing `};` of mtxBarsHtml -- i.e. everything
    this test is actually gating."""
    start = src.index('    const MTX_HYB2=')
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
    {"pool": "HYBRID ♻", "label": "logistic", "pnl": 61200, "dd": 44100, "key": "hyb2:3", "crowned": False},
    {"pool": "HYBRID ♻", "label": "et", "pnl": -52800, "dd": 66900, "key": "hyb2:4", "crowned": False},
    {"pool": "MYSTERY", "label": "unknown pool", "pnl": 500, "dd": 500, "key": "zzz:0", "crowned": False},
]

# The five families the 1A funnel KEY lists, on its five colours. MYSTERY is not one
# and must fall through to grey without throwing.
EXPECT_COL = {'RAW': '#1d9e75', 'GATE': '#e24b4a', 'TILT': '#f0b429',
              'HYBRID': '#c084fc', 'HYBRID ♻': '#f0abfc'}

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
      // the scatter must opt out of the fill-the-tile stretch (_rsCharts sets
      // preserveAspectRatio=none on everything else), or dots render as ellipses and the
      // trend line's apparent slope stops matching the slope it was fitted at.
      keepAspect:svg.hasAttribute('data-keepaspect'),
      par:svg.getAttribute('preserveAspectRatio'),
      dotAspect:(function(){var b=circles[0].getBoundingClientRect();
        return b.height>0?+(b.width/b.height).toFixed(3):null;})(),
      hasSampleChips:!!document.querySelector('[data-g2seg]'),
      sampleSegs:[].slice.call(document.querySelectorAll('[data-g2seg]')).map(function(e){return e.getAttribute('data-g2seg');}),
      trendText:(function(){var e=[].slice.call(document.querySelectorAll('#sc span')).filter(function(s){return /TREND/.test(s.textContent);})[0];
        return e?e.textContent.replace(/\\s+/g,' ').trim():null;})(),
      // ---- legend keys must be clickable family toggles, on BOTH charts ----
      legendKeysScatter:[].slice.call(scEl.querySelectorAll('[data-mtxpool]')).map(function(e){return e.getAttribute('data-mtxpool');}),
      legendKeysBars:[].slice.call(barEl.querySelectorAll('[data-mtxpool]')).map(function(e){return e.getAttribute('data-mtxpool');}),
      // ---- the BOTH / NET / DD metric toggle on the bar chart ----
      metToggles:[].slice.call(barEl.querySelectorAll('[data-mtxbarmet]')).map(function(e){return e.getAttribute('data-mtxbarmet');}),
      // ---- both bars must share ONE vertical band (owner: "dd bar sits below pnl bar
      //      created its own row"). Compare the two bars inside one track: same top, same
      //      height means one line; anything else is the two-row bug coming back. ----
      barBands:(function(){
        var track=barEl.querySelector('[data-mtxsc] span[style*="position:relative"]');
        if(!track)return 'no track';
        var bs=[].slice.call(track.children);
        if(bs.length<2)return 'only '+bs.length+' bar(s)';
        var t=bs.map(function(b){return b.style.top+'/'+b.style.height;});
        return t.filter(function(v,i,a){return a.indexOf(v)===i;}).join(' vs ');})(),
      // literal-text spill check: an unescaped quote in data-tip dumps raw markup onto the page
      spill:/style=|<circle|<span style/.test(host.textContent)
    };
    // ---- SECOND PASS: hide a family and confirm every chart AND scale re-fits ----
    APREF.mtxOff='TILT';
    var sc2=mtxScatterHtml(PTS), bars2=mtxBarsHtml(PTS);
    host.innerHTML='<div id="sc2">'+sc2+'</div><div id="bars2">'+bars2+'</div>';
    var nTilt=PTS.filter(function(p){return p.pool==='TILT';}).length;
    out.hidden={
      tiltInSource:nTilt,
      dotsAfterHide:document.querySelectorAll('#sc2 circle[data-mtxsc]').length,
      rowsAfterHide:document.querySelectorAll('#bars2 [data-mtxsc]').length,
      expected:PTS.length-nTilt,
      // the hidden family keeps a (struck-through) key so it can be clicked back on
      keyStillThere:!!document.querySelector('#sc2 [data-mtxpool="TILT"]'),
      keyStruck:(function(){var e=document.querySelector('#sc2 [data-mtxpool="TILT"]');
        return e?/line-through/.test(e.style.textDecoration||e.getAttribute('style')||''):false;})()
    };
    // ---- THIRD PASS: the DD-only view must re-fit the scale to drawdown alone ----
    APREF.mtxOff='';
    var maxDd=Math.max.apply(null,PTS.map(function(p){return Math.abs(p.dd);}));
    var widthOfLongestDd=function(html){
      var d=document.createElement('div');d.innerHTML=html;document.body.appendChild(d);
      var w=0;[].slice.call(d.querySelectorAll('[data-mtxsc] span[style*="position:relative"]')).forEach(function(tr){
        [].slice.call(tr.children).forEach(function(b){
          if(/e24b4a 32%/.test(b.getAttribute('style')||''))w=Math.max(w,parseFloat(b.style.width)||0);});});
      d.remove();return w;};
    APREF.mtxBarMet='both';var wBoth=widthOfLongestDd(mtxBarsHtml(PTS));
    APREF.mtxBarMet='dd';  var wDd  =widthOfLongestDd(mtxBarsHtml(PTS));
    APREF.mtxBarMet='net'; var netOnly=mtxBarsHtml(PTS);
    var dOnly=document.createElement('div');dOnly.innerHTML=netOnly;
    out.metric={maxDd:maxDd,longestDdPctBoth:+wBoth.toFixed(2),longestDdPctDdOnly:+wDd.toFixed(2),
      ddBarsInNetOnlyView:(netOnly.match(/e24b4a 32%/g)||[]).length};
    APREF.mtxBarMet='both';
    // Exposed so the harness can be opened in a browser and driven by hand when a change needs
    // LOOKING at rather than asserting on: window.__mtx.show('dd'), .hide('TILT'), .reset().
    window.__mtx={APREF:APREF,PTS:PTS,
      draw:function(){host.innerHTML='<div id="sc">'+mtxScatterHtml(PTS)+'</div><div id="bars">'+mtxBarsHtml(PTS)+'</div>';},
      show:function(m){APREF.mtxBarMet=m;window.__mtx.draw();return m;},
      hide:function(f){APREF.mtxOff=f||'';window.__mtx.draw();return f;},
      reset:function(){APREF.mtxOff='';APREF.mtxBarMet='both';window.__mtx.draw();}};
    window.__mtx.reset();
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
    if not o.get('keepAspect'):
        fails.append('the scatter svg has no data-keepaspect, so _rsCharts will stretch it to '
                     'fill its tile -- dots become ellipses and the trend slope stops matching '
                     'the data (observed live before v73.68: r=3 dots rendered 4.1 x 9.4px)')
    if o.get('par') == 'none':
        fails.append('scatter preserveAspectRatio is "none" -- it will render distorted')
    da = o.get('dotAspect')
    if da is not None and not (0.9 <= da <= 1.1):
        fails.append('dots are not round: width/height = %s (1.0 = round)' % da)
    if not o.get('nDashedLines'):
        fails.append('no dashed trend line drawn')
    if not o.get('trendText'):
        fails.append('no trend readout (slope / r-squared) rendered')

    # --- sample toggles ---
    if not o.get('hasSampleChips'):
        fails.append('no SAMPLE chips rendered on the charts')
    if sorted(set(o.get('sampleSegs') or [])) != ['is', 'lb', 'wf']:
        fails.append('SAMPLE chips are not IS/WF/LB (got %s)' % o.get('sampleSegs'))

    # --- bars: both bars on ONE vertical band, not stacked into two rows ---
    bands = o.get('barBands')
    if not isinstance(bands, str) or ' vs ' in bands or bands.startswith('no ') or bands.startswith('only '):
        fails.append('the drawdown bar and the net bar are NOT on one band (%s) -- stacking them '
                     'at different tops is exactly the "dd bar sits below pnl bar, created its own '
                     'row" complaint' % bands)
    elif not (bands.startswith('0/') or bands.startswith('0px/')):
        fails.append('bars are not anchored at the top of their track (%s)' % bands)

    # --- legend keys are clickable family toggles on BOTH charts ---
    for where, got in (('scatter', o.get('legendKeysScatter')), ('bars', o.get('legendKeysBars'))):
        missing = [k for k in EXPECT_COL if k not in (got or [])]
        if missing:
            fails.append('%s legend is missing clickable keys for %s (got %s)'
                         % (where, missing, got))
    h = o.get('hidden') or {}
    if h.get('dotsAfterHide') != h.get('expected') or h.get('rowsAfterHide') != h.get('expected'):
        fails.append('hiding a family did not filter both charts: expected %s points, got %s dots / '
                     '%s bar rows' % (h.get('expected'), h.get('dotsAfterHide'), h.get('rowsAfterHide')))
    if not h.get('keyStillThere'):
        fails.append('a hidden family lost its legend key -- there is no way to switch it back on')
    if not h.get('keyStruck'):
        fails.append('a hidden family key is not visibly marked as off')

    # --- the BOTH / NET / DD toggle, and that isolating DD really re-fits the scale ---
    mt = o.get('metToggles') or []
    if sorted(mt) != ['both', 'dd', 'net']:
        fails.append('bar chart is missing the BOTH / NET / DD toggle (got %s)' % mt)
    m = o.get('metric') or {}
    if m.get('ddBarsInNetOnlyView'):
        fails.append('NET-only view still draws %s drawdown bars' % m.get('ddBarsInNetOnlyView'))
    # DD-only must stretch the deepest drawdown to a full half-track (50%); on BOTH it is
    # dwarfed by net. If isolating DD does not grow it, the toggle is not re-scaling and the
    # "so i can see scale better" ask is unmet.
    if not (m.get('longestDdPctDdOnly') or 0) > (m.get('longestDdPctBoth') or 0):
        fails.append('DD-only view did not re-fit the scale: longest DD bar is %s%% on BOTH and '
                     '%s%% on DD-only' % (m.get('longestDdPctBoth'), m.get('longestDdPctDdOnly')))
    elif abs((m.get('longestDdPctDdOnly') or 0) - 50.0) > 0.6:
        fails.append('DD-only view does not fill its half of the track (longest DD bar %s%%, '
                     'expected ~50%%)' % m.get('longestDdPctDdOnly'))

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
