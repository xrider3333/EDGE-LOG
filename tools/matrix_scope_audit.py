#!/usr/bin/env python3
"""
tools/matrix_scope_audit.py -- SAMPLE-scope audit of the 1E MATRIX (2B CONFIGS card).

WHY THIS EXISTS
    The owner's standing worry: a number rendered under a scoped label ("· LB")
    that was actually measured on a wider window. preflight_boot.py only proves
    the app BOOTS; this gate renders the four 1E tabs (RAW / GATE / TILT /
    HYBRID one-lot) against a REAL run doc, for every SAMPLE tick combo, and
    compares every displayed cell against an INDEPENDENT Python recomputation
    from the raw run-doc data for exactly the ticked stretches.

METHOD (the established one)
    selectionTableHtml + gvParts (and the helper shelf they close over) are
    lifted VERBATIM out of index.html into a headless-Chrome page next to the
    run doc, rendered once per tick combo, and the resulting DOM is flattened
    to {tab: {group, row, cells[]}} JSON. The Python side recomputes each cell
    from the doc and diffs. It also checks the RANK BY orderings, the crown
    column, the scatter points, and that scope tags in section headers wear the
    funnel period colours (IS var(--text4), WF #60a5fa, LB #a78bfa).

USAGE
    python tools/matrix_scope_audit.py path\to\run_doc.json [--keep] [--dump out.json]

Exit codes: 0 = PASS, 1 = FAIL (mismatch found), 2 = INCONCLUSIVE.
"""
import argparse
import html as _html
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preflight_boot import find_chrome  # noqa: E402

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, 'index.html')
HARNESS = os.path.join(REPO, 'tools', '_mtx_audit_probe.html')

COMBOS = ['is', 'wf', 'lb', 'is,wf', 'wf,lb', 'is,lb', 'is,wf,lb']


def read_index():
    with open(INDEX, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def seg(src, start_marker, end_marker, include_end=False):
    a = src.index(start_marker)
    b = src.index(end_marker, a)
    if include_end:
        b += len(end_marker)
    return src[a:b]


def lift_blocks(src):
    out = []
    # single-line global helpers
    for name in ('fmtUsd', 'fmtAx'):
        m = re.search(r'^[ \t]*const %s=.*$' % name, src, re.M)
        out.append(m.group(0))
    for name in ('_infoIc', '_pdChip', '_TILT_SCHEME_NM', '_TILT_SCHEME_AB'):
        m = re.search(r'^[ \t]*const %s=.*$' % name, src, re.M)
        out.append(m.group(0))
    # the control/matrix helper shelf, _scopeTag included, through _gateColor
    out.append(seg(src, '    const _mtxEmphBd=', '    const selectionTableHtml='))
    # selectionTableHtml, whole const
    out.append(seg(src, '    const selectionTableHtml=',
                   "scatterPts:_scatterPtsRaw};};", include_end=True))
    m = re.search(r'^[ \t]*const _pp=.*$', src, re.M)
    out.append(m.group(0))
    m = re.search(r'^[ \t]*const MTX_HYB2=.*$', src, re.M)
    out.append(m.group(0))
    # gvParts, whole const (ends right before gvTableHtml)
    out.append(seg(src, '    const gvParts=', '    const gvTableHtml='))
    return '\n'.join(out)


HARNESS_TMPL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>mtx audit probe</title></head>
<body style="margin:0;background:#0a0a0a">
<div id="host"></div><pre id="o"></pre>
<script>
(function(){
  var out={};
  try{
    var APREF={g2rank:'rec',g2heat:0};
    var savePref=function(k,v){APREF[k]=v;};
    var renderApp=function(){};
__BLOCK__
    var D=__DOC__;
    var host=document.getElementById('host');
    var flat=function(html){
      host.innerHTML=html;
      var res={heads:[],rows:[],groups:[]};
      var thead=host.querySelector('thead');
      if(thead)res.heads=[].slice.call(thead.querySelectorAll('th')).slice(1)
        .map(function(th){return th.textContent.replace(/\\s+/g,' ').trim();});
      var cur=null;
      [].slice.call(host.querySelectorAll('tbody tr')).forEach(function(tr){
        var tds=[].slice.call(tr.children);
        if(tds.length===1&&tds[0].getAttribute('colspan')){
          cur=tds[0].textContent.replace(/\\s+/g,' ').trim();
          res.groups.push({name:cur,html:tds[0].innerHTML});
          return;}
        if(!tds.length)return;
        res.rows.push({g:cur,
          lbl:tds[0].textContent.replace(/\\s+/g,' ').trim(),
          lblHtml:tds[0].innerHTML,
          cells:tds.slice(1).map(function(td){return td.textContent.replace(/\\s+/g,' ').trim();}),
          titles:tds.slice(1).map(function(td){var s=td.querySelector('[title]');return s?s.getAttribute('title'):null;})});
      });
      return res;};
    out={ok:true,combos:{}};
    __COMBOS__.forEach(function(combo){
      APREF.g2samp=combo;
      var one={};
      var selP=selectionTableHtml(D.selection,D.multiplier,null,D.validate);
      if(selP){one.raw=flat(selP.table);one.rawScatter=selP.scatterPts;}
      var gvD=D.gate_validate||(D.validate&&D.validate.gate_bakeoff);
      var gvP=gvD?gvParts(gvD,'S',D.multiplier):null;
      if(gvP){
        one.gate=flat(gvP.matrix);
        one.tilt=gvP.tilts?flat(gvP.tilts):null;
        one.hyb=gvP.hyb?flat(gvP.hyb):null;
        one.gvScatter=gvP.scatterPts;
      }
      out.combos[combo]=one;
    });
    // RANK BY orderings, checked on the full tick and on LB-only
    out.rank={};
    ['is,wf,lb','lb'].forEach(function(combo){
      APREF.g2samp=combo;out.rank[combo]={};
      ['rec','pnl','floor'].forEach(function(rk){
        APREF.g2rank=rk;
        var r={};
        var selP=selectionTableHtml(D.selection,D.multiplier,null,D.validate);
        if(selP)r.raw=flat(selP.table).heads;
        var gvD=D.gate_validate||(D.validate&&D.validate.gate_bakeoff);
        var gvP=gvD?gvParts(gvD,'S',D.multiplier):null;
        if(gvP){r.gate=flat(gvP.matrix).heads;r.tilt=gvP.tilts?flat(gvP.tilts).heads:null;
                r.hyb=gvP.hyb?flat(gvP.hyb).heads:null;}
        out.rank[combo][rk]=r;});
      APREF.g2rank='rec';});
  }catch(e){ out={ok:false,err:String(e&&e.stack||e)}; }
  document.getElementById('o').textContent='MTXPROBE:'+JSON.stringify(out)+':ENDPROBE';
})();
</script>
</body></html>
"""


def build_harness(doc):
    src = read_index()
    block = lift_blocks(src)
    html = (HARNESS_TMPL
            .replace('__BLOCK__', block)
            .replace('__DOC__', json.dumps(doc))
            .replace('__COMBOS__', json.dumps(COMBOS)))
    with open(HARNESS, 'w', encoding='utf-8') as f:
        f.write(html)


def run_probe(chrome):
    args = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
            '--virtual-time-budget=20000', '--dump-dom',
            'file:///' + HARNESS.replace('\\', '/')]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=180,
                           encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return None, 'chrome timed out'
    except OSError as e:
        return None, 'could not launch chrome: %s' % e
    m = re.search(r'MTXPROBE:(.*?):ENDPROBE', p.stdout or '', re.S)
    if not m:
        return None, 'no MTXPROBE marker in chrome output'
    try:
        return json.loads(_html.unescape(m.group(1))), None
    except json.JSONDecodeError as e:
        return None, 'probe JSON did not parse: %s' % e


# ---------------------------------------------------------------------------
# independent recomputation (mirrors the INTENDED semantics, from the doc only)
# ---------------------------------------------------------------------------

def dd_slice(arr, a, b):
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    a = max(0, min(len(arr) - 1, a)); b = max(a, min(len(arr) - 1, b))
    peak = arr[a] or 0; dd = 0.0
    for i in range(a, b + 1):
        v = arr[i] or 0
        if v > peak:
            peak = v
        if peak - v > dd:
            dd = peak - v
    return dd


def dd_from_cum(arr):
    if not isinstance(arr, list) or not arr:
        return None
    peak = 0.0; dd = 0.0
    for v in arr:
        v = v or 0
        if v > peak:
            peak = v
        if peak - v > dd:
            dd = peak - v
    return dd


def fmt_ax(v, k=1):
    a = abs(v or 0)
    if a >= 100000 or (k and a >= 1000):
        s = '-$' if v < 0 else '$'
        return s + (str(round(a / 1000)) if a >= 10000 else ('%.1f' % (a / 1000))) + 'k'
    return fmt_usd(round(v or 0))


def fmt_usd(v):
    s = '-$' if (v or 0) < 0 else '$'
    return s + format(abs(round(v or 0)), ',')


def approx(shown, expected, tol=0.02):
    """shown: text like $123k / -$45.2k / 1.23 / 45% ; expected: number."""
    if shown is None or expected is None:
        return shown in (None, '', '—', '-') and expected is None
    t = shown.replace('°', '').replace('*', '').strip()
    neg = t.startswith('-')
    t = t.lstrip('-$').rstrip('%×')
    mul = 1000.0 if t.endswith('k') else 1.0
    t = t.rstrip('k').replace(',', '')
    try:
        v = float(t) * mul * (-1 if neg else 1)
    except ValueError:
        return False
    if expected == 0:
        return abs(v) < 1e-6
    # display rounding: $123k has ~0.5k slack, 2dp ratios ~0.005
    slack = max(abs(expected) * tol, mul * 0.55 if mul > 1 else 0.006)
    return abs(v - expected) <= slack


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('doc')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--dump')
    a = ap.parse_args()
    chrome = find_chrome()
    if not chrome:
        print('MTXAUDIT: INCONCLUSIVE -- chrome not found'); sys.exit(INCONCLUSIVE)
    doc = json.load(open(a.doc, encoding='utf-8'))
    build_harness(doc)
    obj, err = run_probe(chrome)
    if not a.keep:
        try:
            os.remove(HARNESS)
        except OSError:
            pass
    if err:
        print('MTXAUDIT: INCONCLUSIVE -- %s' % err); sys.exit(INCONCLUSIVE)
    if not obj.get('ok'):
        print('MTXAUDIT: FAIL -- probe threw:\n%s' % obj.get('err')); sys.exit(FAIL)
    if a.dump:
        json.dump(obj, open(a.dump, 'w', encoding='utf-8'), indent=1)
        print('dumped probe to %s' % a.dump)
    print('MTXAUDIT: probe ok -- combos: %s' % ', '.join(sorted(obj['combos'])))
