#!/usr/bin/env python3
"""
tools/roc_parity_probe.py -- WHY DOES ROC % / YR DISAGREE between EXPLORE and a run report?

THE QUESTION (owner 2026-11-14, MANAGER relay): EXPLORE's ALL CANDIDATES table shows
"#483 tree" at ROC 60.0 %, Sortino 3.71, PF 2.14, while run 483's report (1E MATRIX, the
same WF+LB tick) shows a tree row at ROC 47.8-49.7 % with the SAME Sortino and PF. One of
the two numbers is wrong, or the two rows are not the same configuration.

HOW THIS ANSWERS IT: it renders BOTH screens over the SAME run document - the real one,
pulled from Firestore once and cached in _probe/ - and prints, for every row whose label
mentions the model, the pool it belongs to, the net dollars in its own cell and the
rendered ROC. The years each screen divides by are then recovered arithmetically
(ROC % = net / years / ACCT x 100, so years = net / ROC / 1000 at ACCT $100k), which is
what tells a WRONG DENOMINATOR apart from a DIFFERENT ROW: a sized sibling (HYBRID
recycle, HYBRID equal-DD) has a different net at the same years, and PF and Sortino do not
move with sizing, so matching those two proves nothing.

  python tools/roc_parity_probe.py --pull     refresh the cached run documents (2 reads)
  python tools/roc_parity_probe.py            render both screens and print the table

Diagnostic, not a gate: it prints what it measured and exits 0 unless it could not measure
at all. Stdlib only, plus local Chrome, plus firebase-admin for --pull.
"""
import argparse
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, '_probe', 'roc_fixture.json')
PROBE_FILENAME = '_roc_parity_probe.html'
RUNS = ['483', '434']
ACCT = 100000.0


def pull():
    sys.path.insert(0, ROOT)
    import tools.runboard_watch as rw
    db = rw.real_client()
    col = db.collection('users').document(rw.UID).collection('runs')
    out = {}
    for rid in RUNS:
        snap = col.document(rid).get()
        if not snap.exists:
            print('run %s: NOT FOUND' % rid)
            continue
        out[rid] = json.loads(json.dumps(snap.to_dict(), default=str))
        out[rid]['id'] = rid
    os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
    with open(FIXTURE, 'w', encoding='utf-8') as f:
        json.dump(out, f)
    print('wrote %s (%d runs, %d document reads)' % (FIXTURE, len(out), len(RUNS)))
    return 0


# Both screens are driven exactly the way the render gates drive them: runHistory holds the
# documents, window._runFull / window._runCfg stand in for the per-run reads a signed-in
# page would make, and augurPrefs is written to localStorage before renderApp.
PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>roc parity probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1600px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
var DOCS = __DOCS__;
var MODEL = __MODEL__;
(function(){
  var reported=false;
  // every table on screen, as headings + rows, keeping only the rows whose text mentions the
  //   model word - the point is to compare like-labelled rows, not to dump the board.
  // EVERY TABLE THAT MENTIONS THE MODEL, head and body, BOTH ORIENTATIONS. The report's 1E
  //   matrix is transposed - configs are COLUMNS and the metrics are rows - while EXPLORE's
  //   table puts one config per row. Dumping head + rows lets the Python side read either.
  function tables(d){
    var out=[],tb=d.querySelectorAll('table');
    for(var t=0;t<tb.length;t++){
      if((tb[t].textContent||'').toLowerCase().indexOf(MODEL)<0)continue;
      var cell=function(e){return (e.textContent||'').replace(/\\s+/g,' ').trim();};
      var th=tb[t].querySelectorAll('thead th'),head=[];
      for(var h=0;h<th.length;h++)head.push(cell(th[h])||th[h].getAttribute('data-mtxallsort')||'');
      var rows=[],rs=tb[t].querySelectorAll('tr');
      for(var k=0;k<rs.length&&rows.length<60;k++){
        var cells=[];
        for(var c=0;c<rs[k].cells.length;c++)cells.push(cell(rs[k].cells[c]));
        if(cells.length)rows.push(cells);}
      out.push({head:head,rows:rows});}
    return out;
  }
  // the 1E scatter dots carry their pool and their own net, so a sized sibling is visible
  //   even where the table label does not say which pool it came from.
  function dots(d){
    var out=[],ds=d.querySelectorAll('[data-mtxsc]');
    for(var i=0;i<ds.length;i++){
      var tip=ds[i].getAttribute('data-tip')||'';
      if(tip.toLowerCase().indexOf(MODEL)<0)continue;
      out.push({pool:ds[i].getAttribute('data-pool'),key:ds[i].getAttribute('data-mtxkey'),
                net:ds[i].getAttribute('data-net'),tip:tip.replace(/\\s+/g,' ').slice(0,300)});}
    return out;
  }
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var w=document.getElementById('f').contentWindow,d=w.document;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      var inject="var D="+JSON.stringify(DOCS)+";"
        +"var ids=Object.keys(D);runHistory=ids.map(function(k){return D[k];});"
        +"window._runFull={};window._runCfg={};window._runFullOrder=[];window._runHydrating={};"
        +"ids.forEach(function(k){window._runFull[k]=D[k];window._runCfg[k]=D[k];});"
        +"window._c2Open=new Set();window._starRuns=[];window._runsLiteOk=true;";
      var CASES=[
        // the run report's 1E MATRIX, WF+LB ticked (APREF.g2samp is the report's stage tick).
        //   APREF.cfgTab picks WHICH POOL the card shows: hyb = HYBRID as tuned, hyb2 = the
        //   recycle (sized to equal contracts), hyb3 = equal drawdown. A sized sibling is a
        //   different configuration with a different net, so each gets its own case here.
        ['report-hyb',{g2samp:'wf,lb',cfgTab:'hyb',resVirt:false},
         "activeTab='augur';augurSub='runs';augurRunSel='483';renderApp();"],
        ['report-hyb2',{g2samp:'wf,lb',cfgTab:'hyb2',resVirt:false},
         "activeTab='augur';augurSub='runs';augurRunSel='483';renderApp();"],
        ['report-hyb3',{g2samp:'wf,lb',cfgTab:'hyb3',resVirt:false},
         "activeTab='augur';augurSub='runs';augurRunSel='483';renderApp();"],
        ['report-all',{g2samp:'wf,lb',cfgTab:'all',mtxAllSort:'net:d',resVirt:false},
         "activeTab='augur';augurSub='runs';augurRunSel='483';renderApp();"],
        // EXPLORE, 1E CONFIGS of run 483, the same WF+LB tick
        // EXPLORE is augurSub 'cmp2' (COMPARE BETA), the same sub cmp2_render_probe drives
        ['explore-483',{c2Screen:'explore',resLvl:'valid',resVirt:false,resSegs:['wf','lb'],resShow:'configs',
                        resCfgRun:['483'],c2Tbl:true,resCols:'all',resBasis:'year',reSortK:'run',resOrd:'res'},
         "activeTab='augur';augurSub='cmp2';renderApp();"],
        // and EXPLORE with both runs loaded, which is the screen the owner was reading
        ['explore-all',{c2Screen:'explore',resLvl:'valid',resVirt:false,resSegs:['wf','lb'],resShow:'configs',
                        resCfgRun:['483','434'],c2Tbl:true,resCols:'all',resBasis:'year',reSortK:'run',resOrd:'res'},
         "activeTab='augur';augurSub='cmp2';renderApp();"],
        // THE SAME BOARD ON THE OTHER TICKS. ROC % / YR divides by the ticked stretch's own
        //   years, so the identical configuration reads higher on a shorter tick - which is how
        //   the same row can be 60% on one screen and 82% on another with nothing wrong.
        ['explore-wf',{c2Screen:'explore',resLvl:'valid',resVirt:false,resSegs:['wf'],resShow:'configs',
                       resCfgRun:['483','434'],c2Tbl:true,resCols:'all',resBasis:'year',reSortK:'run',resOrd:'res'},
         "activeTab='augur';augurSub='cmp2';renderApp();"],
        ['explore-lb',{c2Screen:'explore',resLvl:'valid',resVirt:false,resSegs:['lb'],resShow:'configs',
                       resCfgRun:['483','434'],c2Tbl:true,resCols:'all',resBasis:'year',reSortK:'run',resOrd:'res'},
         "activeTab='augur';augurSub='cmp2';renderApp();"],
        // ROC % / YR IS MEASURED AGAINST THE ACCT CHIP, and the chip is a click away on the
        //   board: the same configuration reads 1/0.75 higher on a $75k account than on $100k.
        //   This case exists because a figure read off the owner's screen cannot be reproduced
        //   without knowing where his chip was set.
        ['explore-acct75',{c2Screen:'explore',resLvl:'valid',resVirt:false,resSegs:['wf','lb'],resShow:'configs',
                           resCfgRun:['483','434'],c2Tbl:true,resCols:'all',resBasis:'year',rocAcct:75000,
                           reSortK:'run',resOrd:'res'},
         "activeTab='augur';augurSub='cmp2';renderApp();"],
        ['explore-full',{c2Screen:'explore',resLvl:'valid',resVirt:false,resSegs:['is','wf','lb'],resShow:'configs',
                         resCfgRun:['483','434'],c2Tbl:true,resCols:'all',resBasis:'year',reSortK:'run',resOrd:'res'},
         "activeTab='augur';augurSub='cmp2';renderApp();"]
      ];
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0],pref=CASES[i][1],step=CASES[i][2],r={};
        r.call=w.eval("(function(){try{"+inject
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(pref))+");"
          +step+"return 'OK';}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        r.tables=tables(d);
        r.dots=dots(d);
        r.census=(function(){var tb=d.querySelectorAll('table'),n=0,sample=[];
          for(var t=0;t<tb.length;t++){var rs=tb[t].querySelectorAll('tbody tr');n+=rs.length;
            for(var k=0;k<rs.length&&sample.length<16;k++){
              var s=(rs[k].textContent||'').replace(/\\s+/g,' ').trim();
              if(s)sample.push(s.slice(0,120));}}
          return {tables:tb.length,rows:n,dots:d.querySelectorAll('[data-mtxsc]').length,
                  rerows:d.querySelectorAll('tr[data-rerow]').length,
                  appLen:(d.getElementById('app')||{innerHTML:''}).innerHTML.length,sample:sample};})();
        out.cases[nm]=r;
      }
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='ROCPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},6000);});
  setTimeout(function(){report('backstop');},60000);
})();
</script>
</body></html>
"""


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    return next((c for c in cands if os.path.isfile(c)), None)


def make_handler(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass
    return H


def num(s):
    """the figure inside a rendered cell: '$467,999' -> 467999.0, '60.0%' -> 60.0."""
    if s is None:
        return None
    m = re.search(r'-?\$?\s*-?[\d,]+(?:\.\d+)?', str(s).replace('\u2212', '-'))
    if not m:
        return None
    t = m.group(0).replace('$', '').replace(',', '').replace(' ', '')
    neg = str(s).strip().startswith('-') or t.startswith('-')
    try:
        v = abs(float(t))
    except ValueError:
        return None
    return -v if neg else v


def asc(s):
    """the board is full of glyphs the Windows console cannot encode; the text is here to be
    read, so strip them rather than crash the measurement."""
    return str(s).encode('ascii', 'replace').decode('ascii')


def pick(ix, *names):
    for n in names:
        for h, i in ix.items():
            if n in h:
                return i
    return None


def say(label, net, roc, yrs_shown=None):
    """one measured row: its net, its rendered ROC, and the YEARS that pair implies - which is
    what tells a wrong denominator (same net, different years) from a different row (different
    net, same years)."""
    yrs = (net / (roc * ACCT / 100.0)) if (roc and net) else None
    print('     cfg=%-34s net=%-11s roc=%-7s implied_years=%-7s shown_years=%s'
          % (asc(label)[:34], net, roc, ('%.3f' % yrs) if yrs else '-', asc(yrs_shown or '-')[:12]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pull', action='store_true', help='refresh the cached run documents')
    ap.add_argument('--top', type=int, default=6, help='how many highest-ROC rows to name')
    ap.add_argument('--model', default='tree', help='the model word to follow through both screens')
    args = ap.parse_args()
    if args.pull:
        return pull()
    if not os.path.isfile(FIXTURE):
        print('ROC PROBE: INCONCLUSIVE (no fixture - run with --pull once)')
        return INCONCLUSIVE
    docs = json.load(open(FIXTURE, encoding='utf-8'))
    chrome = find_chrome()
    if not chrome:
        print('ROC PROBE: INCONCLUSIVE (no chrome found)')
        return INCONCLUSIVE

    pdir = os.path.join(ROOT, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, PROBE_FILENAME)
    html = (PROBE_HTML.replace('__DOCS__', json.dumps(docs))
                      .replace('__MODEL__', json.dumps(args.model)))
    with open(ppath, 'w', encoding='utf-8') as f:
        f.write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, PROBE_FILENAME)
    prof = tempfile.mkdtemp(prefix='rocprobe')
    dump = os.path.join(prof, 'out.txt')
    cmd = [chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--window-size=1600,1000',
           '--user-data-dir=' + prof, '--virtual-time-budget=70000',
           '--dump-dom', url]
    try:
        with open(dump, 'w', encoding='utf-8') as fh:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL, timeout=240)
        dom = open(dump, encoding='utf-8', errors='replace').read()
    except subprocess.TimeoutExpired:
        print('ROC PROBE: INCONCLUSIVE (chrome timed out)')
        return INCONCLUSIVE
    finally:
        srv.shutdown()

    m = re.search(r'ROCPROBE: (\{.*?\})</pre>', dom, re.S)
    if not m:
        print('ROC PROBE: INCONCLUSIVE (probe produced no reading)')
        return INCONCLUSIVE
    rep = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                     .replace('&lt;', '<').replace('&gt;', '>'))
    print('ROC PROBE: version %s, model %r' % (rep.get('VERSION'), args.model))
    if rep.get('err'):
        print('  probe error: %s' % rep['err'])

    for nm, r in (rep.get('cases') or {}).items():
        print('\n== %s  call=%s' % (nm, r.get('call')))
        c = r.get('census') or {}
        print('   census tables=%s rows=%s dots=%s rerows=%s appLen=%s'
              % (c.get('tables'), c.get('rows'), c.get('dots'), c.get('rerows'), c.get('appLen')))
        if not (r.get('tables') or r.get('dots')):
            for s in (c.get('sample') or []):
                # the board is full of glyphs the Windows console cannot encode; the text is
                #   here to be read, so strip them rather than crash the measurement.
                print('     | %s' % s.encode('ascii', 'replace').decode('ascii'))
        for dd in (r.get('dots') or []):
            print('   dot  pool=%-12s key=%-10s net=%s' % (dd.get('pool'), dd.get('key'), dd.get('net')))
        for ti, tb in enumerate(r.get('tables') or []):
            print('   table %d  head=%s' % (ti, asc(' | '.join(tb['head'])[:220])))
            # ORIENTATION A - one config per row, metrics as columns (EXPLORE)
            ix = {h.upper(): i for i, h in enumerate(tb['head'])}
            roc_c = pick(ix, 'ROC % / YR')
            net_c = pick(ix, 'TOTAL', 'NET P&L', 'NET')
            yrs_c = pick(ix, 'YEARS')
            if roc_c is not None and net_c is not None:
                keep = []
                for cells in tb['rows']:
                    # A ROW CAN CARRY MORE CELLS THAN THE TABLE HAS HEADINGS (the crown / pin
                    #   marks ride in cells of their own), so align from the RIGHT - every
                    #   figure column is to the right of the label block.
                    # EXPLORE's rows carry exactly one cell per heading; the report's ALL table
                    #   can carry extra mark cells, so align from the right only when the row is
                    #   actually longer than the heading row.
                    off = (len(cells) - len(tb['head'])) if len(cells) > len(tb['head']) else 0
                    g = lambda i: (cells[i + off] if (i is not None and 0 <= i + off < len(cells)) else None)
                    roc, net = num(g(roc_c)), num(g(net_c))
                    row = (' '.join(cells[:4]), net, roc, g(yrs_c))
                    if args.model in ' '.join(cells).lower():
                        say(*row)
                    if roc is not None:
                        keep.append(row)
                # THE HIGHEST ROC ON THE BOARD, whatever its model: that is the lone dot far
                #   out to the right the owner asked about, and naming its row is the answer.
                for row in sorted(keep, key=lambda x: -(x[2] or 0))[:args.top]:
                    print('     TOP  %s' % asc('cfg=%-34s net=%-11s roc=%-7s years=%s'
                                                % (row[0][:34], row[1], row[2], row[3])))
                continue
            # ORIENTATION B - configs are COLUMNS, metrics are rows (the report's 1E matrix)
            labels = [(cells[0] if cells else '') for cells in tb['rows']]
            rrow = next((c for c, l in zip(tb['rows'], labels) if l.upper().startswith('ROC')), None)
            nrow = next((c for c, l in zip(tb['rows'], labels) if l.upper().startswith(('TOTAL', 'NET'))), None)
            names = tb['head'] or (tb['rows'][0] if tb['rows'] else [])
            for j, nmc in enumerate(names):
                if args.model not in str(nmc).lower():
                    continue
                say(nmc, num(nrow[j]) if (nrow and j < len(nrow)) else None,
                    num(rrow[j]) if (rrow and j < len(rrow)) else None)
    return PASS


if __name__ == '__main__':
    sys.exit(main())
