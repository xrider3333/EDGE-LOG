#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/research_render_probe.py -- render gate for the top-level RESEARCH tab (activeTab='augur',
augurSub='research') and its ML RESEARCH section.

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html boots, and the other render probes open HOME, STUDIES,
PAPER, BUILDER, the run report and COMPARE. None of them ever opened RESEARCH. The owner asked on
2026-10-11 for "our ML researched/links etc" on the research section and to "make sure that tab is
opened", so this probe opens it the way a person does - a click on the RESEARCH button in the
sub-tab strip from another tab - and checks what renders, on a laptop and on a phone.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe (the iframe IS the viewport), keeps the
signed-out screen off the page, parks the app on RESULTS, clears the remembered RESEARCH / REFERENCE
toggle and clicks the RESEARCH strip button. Cases: laptop 1400x900, phone 375x812, phone 375x812 in
the MONO theme (the owner's theme: --green is white, --red is grey).

WHAT IT ASSERTS (per case)
--------------------------
  * renderApp returned; no window.onerror, no console.error, no load error and no LOAD ERROR overlay
  * the strip has a visible RESEARCH button and a click on it lands on augurSub='research'
  * #ml-research is on the page, OPEN with no click (not inside a closed <details>, has height) and
    its top is inside the first screen
  * it draws one [data-mlrow] per ML_RESEARCH_ROWS entry, and at least 10
  * every row's verdict is one of DEAD / FAIL / PASS-small / OPEN, every row has a date, a "Tested"
    line and a "Found" line
  * every link is https; every GitHub blob link names a file that exists in this checkout
  * the verdict word is drawn in --text (readable in MONO, where --red is a dark grey)
  * the backtesting-stack frame (#stack-frame) is still there, under the ML section
  * no sideways scroll (page scrollWidth <= clientWidth + 1, and the section fits its box)

Exits 0 on PASS, 1 on FAIL, 2 if Chrome cannot be found. Screenshots go to the folder given as the
first argument (default: the system temp dir), named research_<case>.png.
"""
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = 'https://github.com/xrider3333/EDGE-LOG/blob/main/'
VERDICTS = ('DEAD', 'FAIL', 'PASS-small', 'OPEN')


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def make_handler(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass
    return H


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>research probe</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="../index.html" style="width:__IW__px;height:__IH__px;border:0"></iframe>
<pre id="o"></pre>
<script>
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.call=w.eval(`(function(){try{
        window.renderAuth=function(){};
        window._rsProbeErr=[];
        window.onerror=function(m){window._rsProbeErr.push('onerror: '+String(m));};
        window.addEventListener('unhandledrejection',function(e){window._rsProbeErr.push('unhandledrejection: '+String(e&&e.reason));});
        var le=window._loadError;window._rsLoadErr=[];
        window._loadError=function(err,stage){window._rsLoadErr.push(String(err&&err.message||err)+' (stage '+stage+')');if(typeof le==='function')return le.apply(this,arguments);};
        var ce=console.error.bind(console);
        console.error=function(){window._rsProbeErr.push('console.error: '+Array.prototype.slice.call(arguments).join(' '));ce.apply(console,arguments);};
        currentUser=currentUser||{uid:'probe-uid'};
        __THEME__
        try{localStorage.removeItem('el_researchSub');}catch(e){}
        activeTab='augur';augurSub='runs';renderApp();
        var b=document.querySelector('[data-asubtop="research"]');
        if(!b)return 'NO RESEARCH BUTTON';
        window._rsBtnVisible=!!(b.offsetWidth&&b.offsetHeight);
        b.click();
        return 'OK';
      }catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()`);
      out.btnVisible=w.eval('!!window._rsBtnVisible');
      out.augurSub=w.eval("typeof augurSub!=='undefined'?augurSub:null");
      out.theme=d.documentElement.getAttribute('data-theme');
      out.nData=w.eval("typeof ML_RESEARCH_ROWS!=='undefined'?ML_RESEARCH_ROWS.length:-1");
      var sec=d.getElementById('ml-research');
      out.hasSection=!!sec;
      if(sec){
        var r=sec.getBoundingClientRect();
        out.secTop=r.top;out.secHeight=r.height;out.innerHeight=w.innerHeight;
        out.secOpenAttr=sec.getAttribute('data-mlopen');
        var det=sec.closest('details');
        out.inClosedDetails=!!(det&&!det.open);
        out.secFits=sec.scrollWidth<=sec.clientWidth+1;
        var rows=[].slice.call(sec.querySelectorAll('[data-mlrow]'));
        out.nRows=rows.length;
        out.rows=rows.map(function(e){
          var v=e.querySelector('[data-mlverdict]');
          var t=e.textContent.replace(/\\s+/g,' ');
          return {v:v?v.textContent.trim():null,
                  hasTested:t.indexOf('Tested:')>=0,hasFound:t.indexOf('Found:')>=0,
                  hasDate:/20\\d\\d-\\d\\d/.test(t),
                  vColor:v?w.getComputedStyle(v).color:null,
                  h:e.getBoundingClientRect().height};
        });
        var probe=d.createElement('span');probe.style.color='var(--text)';sec.appendChild(probe);
        out.textColor=w.getComputedStyle(probe).color;probe.remove();
        out.links=[].slice.call(sec.querySelectorAll('a')).map(function(a){return a.getAttribute('href');});
        var sf=d.getElementById('stack-frame');
        out.hasStack=!!sf;
        out.stackBelow=!!(sf&&(sec.compareDocumentPosition(sf)&4));
      }
      var de=d.documentElement;
      out.scrollW=de.scrollWidth;out.clientW=de.clientWidth;
      out.loadErr=w.eval("(window._rsLoadErr||[]).join(' | ')+(window.loadError?' loadError='+String(window.loadError):'')");
      out.overlay=[].slice.call(d.body.children).filter(function(e){return /^\\s*LOAD ERROR/.test(e.textContent||'');}).length;
      out.errs=w.eval('window._rsProbeErr||[]');
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='RSPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, name, width, height, theme, shot_path):
    pdir = os.path.join(ROOT, '_rsprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    theme_js = ("prefs.theme='%s';applyTheme();" % theme) if theme else ''
    html = (PROBE_HTML.replace('__THEME__', theme_js)
            .replace('__IW__', str(width)).replace('__IH__', str(height)))
    io.open(ppath, 'w', encoding='utf-8').write(html)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(ROOT))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='rsprobe-')
    url = 'http://127.0.0.1:%d/_rsprobe/probe_%s.html' % (port, name)
    base = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
            '--user-data-dir=' + prof, '--virtual-time-budget=50000',
            '--window-size=%d,%d' % (width, height + 40)]
    try:
        out = subprocess.run(base + ['--dump-dom', url], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=180).stdout
        if shot_path:
            subprocess.run(base + ['--screenshot=' + shot_path, url], capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=180)
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'RSPROBE: (\{.*\})\s*</pre>', out or '', re.S)
    if not m:
        return {'err': 'no readout', 'raw_tail': (out or '')[-1500:]}
    try:
        return json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return {'err': 'unreadable readout: %s' % e}


def judge(nm, r):
    f = []
    if r.get('err'):
        return ['%s: %s' % (nm, r['err'])]
    if r.get('call') != 'OK':
        f.append('%s: setup/click returned %r' % (nm, r.get('call')))
    if not r.get('btnVisible'):
        f.append('%s: the RESEARCH strip button is missing or hidden' % nm)
    if r.get('augurSub') != 'research':
        f.append('%s: a click on RESEARCH left augurSub=%r' % (nm, r.get('augurSub')))
    if r.get('errs'):
        f.append('%s: errors on the page: %s' % (nm, r['errs'][:5]))
    if r.get('loadErr'):
        f.append('%s: the app reported a load error: %s' % (nm, r['loadErr'][:200]))
    if r.get('overlay'):
        f.append('%s: the LOAD ERROR overlay is on the page' % nm)
    if not r.get('hasSection'):
        return f + ['%s: #ml-research is not on the RESEARCH tab' % nm]
    if r.get('secOpenAttr') != '1' or r.get('inClosedDetails') or not (r.get('secHeight') or 0) > 100:
        f.append('%s: ML RESEARCH is not open without a click (open=%r, closed details=%r, height=%r)'
                 % (nm, r.get('secOpenAttr'), r.get('inClosedDetails'), r.get('secHeight')))
    if not (r.get('secTop') is not None and r['secTop'] < (r.get('innerHeight') or 0)):
        f.append('%s: ML RESEARCH starts below the first screen (top %r, screen %r)'
                 % (nm, r.get('secTop'), r.get('innerHeight')))
    n = r.get('nRows') or 0
    if n < 10:
        f.append('%s: only %d ML RESEARCH rows (need >= 10)' % (nm, n))
    if n != r.get('nData'):
        f.append('%s: %d rows drawn for %r in ML_RESEARCH_ROWS' % (nm, n, r.get('nData')))
    for i, row in enumerate(r.get('rows') or []):
        if row.get('v') not in VERDICTS:
            f.append('%s: row %d verdict %r is not one of %s' % (nm, i, row.get('v'), '/'.join(VERDICTS)))
        if not (row.get('hasTested') and row.get('hasFound') and row.get('hasDate')):
            f.append('%s: row %d is missing its Tested / Found line or its date' % (nm, i))
        if row.get('vColor') != r.get('textColor'):
            f.append('%s: row %d verdict drawn in %r, not --text %r' % (nm, i, row.get('vColor'), r.get('textColor')))
        if not (row.get('h') or 0) > 20:
            f.append('%s: row %d has no height' % (nm, i))
    for href in r.get('links') or []:
        if not (href or '').startswith('https://'):
            f.append('%s: link %r is not https' % (nm, href))
        elif href.startswith(GH):
            path = href[len(GH):].split('#')[0]
            if not os.path.isfile(os.path.join(ROOT, *path.split('/'))):
                f.append('%s: GitHub link names a file not in this checkout: %s' % (nm, path))
    if not r.get('hasStack') or not r.get('stackBelow'):
        f.append('%s: the backtesting-stack frame is gone or no longer under ML RESEARCH' % nm)
    if (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
        f.append('%s: the page scrolls sideways (%r > %r)' % (nm, r.get('scrollW'), r.get('clientW')))
    if not r.get('secFits'):
        f.append('%s: the ML RESEARCH section is wider than its box' % nm)
    return f


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    chrome = find_chrome()
    if not chrome:
        print('RSPROBE: INCONCLUSIVE -- chrome not found')
        return 2
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.gettempdir()
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    cases = (('desk_1400', 1400, 900, ''), ('phone_375', 375, 812, ''), ('mono_375', 375, 812, 'mono'))
    fails = []
    for nm, w, h, theme in cases:
        shot = os.path.join(out_dir, 'research_%s.png' % nm)
        r = run_case(chrome, nm, w, h, theme, shot)
        brief = {k: r.get(k) for k in ('call', 'augurSub', 'theme', 'nRows', 'nData', 'secTop',
                                       'secHeight', 'scrollW', 'clientW', 'errs', 'err')}
        print('%s: %s  shot -> %s' % (nm, json.dumps(brief), shot))
        fails += judge(nm, r)
    if fails:
        print('RSPROBE: FAIL')
        for x in fails:
            print('  - ' + x)
        return 1
    print('RSPROBE: PASS (RESEARCH opens on a click from another tab; ML RESEARCH open, >= 10 rows, '
          'laptop 1400 + phone 375 + MONO 375, no sideways scroll, no console error)')
    return 0


if __name__ == '__main__':
    try:   # any Chrome this run starts dies with it, however the run ends (tools/kill_on_exit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kill_on_exit
        kill_on_exit.install()
    except Exception:
        pass
    sys.exit(main())
