#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/pc_render_probe.py -- render gate for the PC page (activeTab='augur', augurSub='pc'),
the board's pc p12: what the machine is doing, and the QUIET button.

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html boots; it never enters a view, and this repo has shipped
views that crashed behind a green boot gate. The PC page is a brand new view with its own two
Firestore documents, so it gets its own gate on the day it ships.

WHAT IT ASSERTS, per case (laptop 1400x900, phone 375x812, phone in the owner's MONO theme)
-------------------------------------------------------------------------------------------
  * renderApp returned, no window.onerror, no console.error, no LOAD ERROR overlay
  * a click on the PC strip button lands on augurSub='pc' from another tab
  * WITH A QUIET STATE SEEDED: the page says QUIET, repeats the runner's own reason, and lists the
    running, held and deferred jobs it was given - the numbers come from the document, not the page
  * WITH NO QUIET: it says RUNNING NORMALLY and offers to quiet the machine
  * THE THREE FIGURES NOTHING PUBLISHES - processor, memory, graphics - are drawn as dashes with a
    reason, never as a zero and never as a guess. This is the half of the owner's ask that cannot
    be built from the web alone, and the page has to keep saying so.
  * the page NEVER claims trading is paused: the standing promise is that quiet holds jobs, ships
    and refreshes and never touches trades, the paper books or the live gate
  * the button writes ONE document - users/{uid}/control/quiet - and writes nothing else
  * a phone page does not scroll sideways
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


PROBE_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>pc probe</title></head>
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
        window._pcErr=[];
        window.onerror=function(m){window._pcErr.push('onerror: '+String(m));};
        window.addEventListener('unhandledrejection',function(e){window._pcErr.push('unhandledrejection: '+String(e&&e.reason));});
        var ce=console.error.bind(console);
        console.error=function(){window._pcErr.push('console.error: '+Array.prototype.slice.call(arguments).join(' '));ce.apply(console,arguments);};
        currentUser=currentUser||{uid:'probe-uid'};
        __THEME__
        // THE RUNNER'S OWN WORDS, seeded: the page must repeat these and count these, never
        //   invent its own. loadQuiet is short-circuited so no network read can race the case.
        window._qtLoaded=true;window._qtAt=Date.now();window._qtLoading=false;
        window._qtStatus={quiet:true,why:'auto 06:25-09:00 MST',since:'2026-10-29 06:25',
          until:'2026-10-29 09:00',held_jobs:['job-aaa','job-bbb'],
          deferred:['startup refresh','build_adjusted_masters'],
          running_jobs:['job-zzz'],runner_seen_at:new Date().toISOString()};
        window._qtWant={on:true,auto:true};
        window.loadQuiet=function(){};
        // EVERY WRITE THIS PAGE MAKES, recorded rather than sent. The page's own setQuiet runs
        //   for real against a RECORDING database: assigning window.setQuiet would not have
        //   shadowed it (a top-level function declaration is a lexical binding, not a window
        //   property), and the first cut of this case silently tested nothing because of that.
        //   Assigning db and auth through eval reaches the page's own bindings (no backticks in
        //   here: this comment lives inside a template literal and a backtick would end it), so
        //   the real
        //   write path is exercised - the document path and the payload included.
        window._pcWrites=[];
        var _rec=function(path){return {
          collection:function(c){return _rec(path+'/'+c);},
          doc:function(x){return _rec(path+'/'+x);},
          set:function(o){window._pcWrites.push({doc:path.split('/').slice(3).join('/'),
            on:!!o.on,auto:o.auto,reason:String(o.reason||''),by:o.set_by});
            return Promise.resolve();},
          get:function(){return Promise.resolve({exists:false,data:function(){return {};}});}};};
        window._pcRecDb=_rec('');
        db=window._pcRecDb;
        auth={currentUser:{uid:'probe-uid'}};
        if(typeof firebase==='undefined')firebase={};
        firebase.firestore=firebase.firestore||{};
        firebase.firestore.FieldValue={serverTimestamp:function(){return 'SERVER_TIME';}};
        activeTab='augur';augurSub='runs';renderApp();
        var b=document.querySelector('[data-asubtop="pc"]');
        if(!b)return 'no PC strip button';
        b.click();
        return 'OK';
      }catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()`);
      out.augurSub=w.eval('augurSub');
      out.btnVisible=w.eval(`(function(){var b=document.querySelector('[data-asubtop="pc"]');
        if(!b)return false;var r=b.getBoundingClientRect();return r.width>0&&r.height>0;})()`);
      var tx=(d.getElementById('app')||d.body).textContent.replace(/\s+/g,' ');
      out.tx=tx.slice(0,1400);
      // the dashed rows, with the reason each one carries
      out.dashes=w.eval(`(function(){var o=[];
        [].forEach.call(document.querySelectorAll('span[title]'),function(s){
          if((s.textContent||'').indexOf('\u2014')>=0)o.push((s.getAttribute('title')||'').slice(0,120));});
        return o;})()`);
      out.btns=w.eval(`(function(){return [].map.call(document.querySelectorAll('[data-pcquiet]'),
        function(b){return b.getAttribute('data-pcquiet')+':'+(b.textContent||'').trim();});})()`);
      // CLICK THE BUTTON and see which document it would write
      out.click=w.eval(`(function(){try{
        // the recording database is installed HERE, immediately before the click: the page's own
        //   boot resets db and auth while it renders, so installing it once at setup left the real
        //   setQuiet taking its not-signed-in path and writing nothing, which read as a pass of
        //   nothing at all.
        db=window._pcRecDb;auth={currentUser:{uid:'probe-uid'}};
        window._pcWrites=[];
        var b=document.querySelector('[data-pcquiet]');
        if(!b)return {ok:false,why:'no quiet button'};
        b.click();
        return {ok:true,writes:(window._pcWrites||[]),dbT:(typeof db),dbRec:(db===window._pcRecDb),uid:(auth&&auth.currentUser&&auth.currentUser.uid)||null,err:(window._qtErr||null),sq:(typeof setQuiet)};
      }catch(e){return {ok:false,why:String(e&&e.stack?e.stack:e)};}})()`);
      // AND THE OTHER STATE: no quiet at all
      out.off=w.eval(`(function(){try{
        window._qtStatus={quiet:false,why:null,since:null,until:null,held_jobs:[],deferred:[],
          running_jobs:['job-yyy'],runner_seen_at:new Date().toISOString()};
        renderApp();
        var t=(document.getElementById('app')||document.body).textContent.replace(/\s+/g,' ');
        return {tx:t.slice(0,600),btns:[].map.call(document.querySelectorAll('[data-pcquiet]'),
          function(b){return b.getAttribute('data-pcquiet');})};
      }catch(e){return {err:String(e&&e.stack?e.stack:e)};}})()`);
      var de=d.documentElement;
      out.scrollW=de.scrollWidth;out.clientW=de.clientWidth;
      out.overlay=[].slice.call(d.body.children).filter(function(e){return /^\s*LOAD ERROR/.test(e.textContent||'');}).length;
      out.errs=w.eval('window._pcErr||[]');
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='PCPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, name, width, height, theme, shot_path):
    pdir = os.path.join(ROOT, '_pcprobe')
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
    prof = tempfile.mkdtemp(prefix='pcprobe-')
    url = 'http://127.0.0.1:%d/_pcprobe/probe_%s.html' % (port, name)
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
    m = re.search(r'PCPROBE: (\{.*\})\s*</pre>', out or '', re.S)
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
        return f
    if not r.get('btnVisible'):
        f.append('%s: the PC strip button is missing or hidden' % nm)
    if r.get('augurSub') != 'pc':
        f.append('%s: a click on PC left augurSub=%r' % (nm, r.get('augurSub')))
    if r.get('overlay'):
        f.append('%s: a LOAD ERROR overlay is on the page' % nm)
    if r.get('errs'):
        f.append('%s: errors on the page: %s' % (nm, r['errs'][:3]))
    tx = r.get('tx') or ''
    # IT REPEATS THE RUNNER'S OWN WORDS AND COUNTS, rather than deciding anything itself
    if 'QUIET' not in tx.upper():
        f.append('%s: a quiet machine does not say QUIET' % nm)
    if 'auto 06:25-09:00 MST' not in tx:
        f.append("%s: the runner's own reason for being quiet is not repeated" % nm)
    for want, what in (('job-zzz', 'the running job'), ('job-aaa', 'a held job'),
                       ('startup refresh', 'the deferred refresh')):
        if want not in tx:
            f.append('%s: %s from the runner document is not listed' % (nm, what))
    # THE PROMISE THAT MUST NEVER SLIP: quiet does not touch trading
    low = tx.lower()
    if 'never pauses trading' not in low and 'never pause' not in low:
        f.append('%s: the page does not say that quiet never pauses trading' % nm)
    # THE THREE FIGURES NOTHING PUBLISHES: dashed, with a reason, never a zero
    dashes = r.get('dashes') or []
    reasoned = [d for d in dashes if 'publishes this figure' in d]
    if len(reasoned) < 3:
        f.append('%s: the processor, memory and graphics rows must each be a dash WITH its reason '
                 '(found %d of 3)' % (nm, len(reasoned)))
    if re.search(r'\b(cpu|processor|memory|graphics)\b[^.]{0,20}\b0 ?%', low):
        f.append('%s: a load figure is printed as zero, which is a guess, not a reading' % nm)
    # THE BUTTON WRITES ONE DOCUMENT
    cl = r.get('click') or {}
    wr = cl.get('writes') or []
    if not (cl.get('ok') and len(wr) == 1 and wr[0].get('doc') == 'control/quiet'):
        f.append('%s: the button must write exactly one document, control/quiet - got %r' % (nm, wr))
    elif not (wr[0].get('by') == 'web' and wr[0].get('on') is False):
        # the seeded machine is QUIET, so the one button on screen switches it OFF, and the runner
        #   contract wants to know the web set it
        f.append('%s: the write does not match contract #147 (set_by web, on false here) - %r'
                 % (nm, wr[0]))
    # THE OTHER STATE
    off = r.get('off') or {}
    otx = (off.get('tx') or '')
    if 'RUNNING NORMALLY' not in otx.upper():
        f.append('%s: a machine that is not quiet does not say so (%r)' % (nm, otx[:120]))
    if 'on' not in (off.get('btns') or []):
        f.append('%s: no button to quiet a machine that is running normally' % nm)
    if (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
        f.append('%s: the page scrolls sideways (%r > %r)' % (nm, r.get('scrollW'), r.get('clientW')))
    return f


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    chrome = find_chrome()
    if not chrome:
        print('PCPROBE: INCONCLUSIVE -- chrome not found')
        return 2
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.gettempdir()
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    cases = (('desk_1400', 1400, 900, ''), ('phone_375', 375, 812, ''),
             ('mono_375', 375, 812, 'mono'))
    fails = []
    for nm, w, h, theme in cases:
        shot = os.path.join(out_dir, 'pc_%s.png' % nm)
        r = run_case(chrome, nm, w, h, theme, shot)
        brief = {k: r.get(k) for k in ('call', 'augurSub', 'btns', 'scrollW', 'clientW',
                                       'errs', 'err')}
        print('%s: %s  shot -> %s' % (nm, json.dumps(brief), shot))
        fails += judge(nm, r)
    if fails:
        print('PCPROBE: FAIL')
        for x in fails:
            print('  - ' + x)
        return 1
    print('PCPROBE: PASS (PC opens from another tab; a quiet machine repeats the runner own reason '
          'and lists its running, held and deferred jobs; the three figures nothing publishes are '
          'dashes with reasons, never zeros; the button writes only control/quiet; the page keeps '
          'saying quiet never pauses trading; laptop 1400 + phone 375 + MONO 375)')
    return 0


if __name__ == '__main__':
    try:   # any Chrome this run starts dies with it, however the run ends (tools/kill_on_exit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kill_on_exit
        kill_on_exit.install()
    except Exception:
        pass
    sys.exit(main())
