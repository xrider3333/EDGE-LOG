#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/header_render_probe.py -- render gate for the APP HEADER (the top bar and the sub-tab row).

WHY THIS EXISTS
---------------
The owner asked on 2026-11-17, looking at v90.31: "push all the tabs circled into one horizontal
line. trying to reclaim space (subtabs can be a second row). the status of backtest can just be a
simple gauge per backtest further right. the NT Gate can be moved far right along with any other
status indicators. remove the 134 net and trade count, that info is below on the page." -- and
reported a bug with it: "subtabs disappear when scrolling down".

The header is the one piece of this app that is on EVERY screen, and until now nothing measured
it. Every other render probe opens one tab and checks what is inside it; a header that silently
wrapped onto three rows, or a sub-tab row that scrolled away, would pass all of them. This probe
measures the header itself: how many rows it actually renders at a given width, what is in it,
and whether the second row is still on screen after the page is scrolled.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe (the iframe IS the viewport), keeps
the signed-out screen off the page, seeds a couple of trades so the old header would have had a
trade count and a net to print, then renders one case per (tab, viewport):

  home_1400    1400x900  LEDGER    -- a tab that HAS sub-tabs (REAL / NT8 PAPER / WEBULL PAPER)
  anal_1400    1400x900  ANALYTICS -- a tab with NO sub-tabs
  home_375      375x812  LEDGER, phone width
  mono_375      375x812  LEDGER, phone width, MONO theme

WHAT IT ASSERTS (per case)
--------------------------
  * renderApp returned; no window.onerror, no console.error, no load error, no LOAD ERROR overlay
  * ONE TOP ROW: every main tab button is inside .topbar, and the logo, every tab, the status
    cluster and the OUT button all sit on the same line (their boxes overlap vertically); the top
    bar is no taller than one button row (<= TOPBAR_MAX px)
  * the status cluster (.tbstat) is in the top bar, holds the NT GATE chip, and starts to the
    RIGHT of the last tab button; the backtest gauges and the WEBULL chip sit inside it
  * NO TRADE COUNT AND NO NET in the header: the top bar's text has no "<n> trades" and no
    dollar figure
  * SUB-TABS ARE THE SECOND ROW: a tab with sub-tabs draws exactly one .nav-subrow, pinned
    directly under the top bar (its top == the top bar's height, +/- 2 px), and the whole header
    is two rows (<= HEADER_MAX px); a tab without sub-tabs draws none and is one row
  * THE SUB-TAB ROW STAYS PUT (the owner's bug): after scrolling the page 2000 px the row is
    still fully on screen, still welded to the top bar, still holds its buttons, and nothing is
    drawn over it
  * the page never scrolls sideways (scrollWidth <= clientWidth + 1), at 1400 or at 375

Exits 0 on PASS, 1 on FAIL, 2 if Chrome cannot be found. Screenshots go to the folder given as
the first argument (default: the system temp dir), named header_<case>.png.
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

# one button row plus the bar's own padding. A second wrapped line would be well over this.
TOPBAR_MAX = 64
# top bar + the sub-tab row. A third row would be well over this.
HEADER_MAX = 104


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
<html><head><meta charset="utf-8"><title>header probe</title></head>
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
        window._hdProbeErr=[];
        window.onerror=function(m){window._hdProbeErr.push('onerror: '+String(m));};
        window.addEventListener('unhandledrejection',function(e){window._hdProbeErr.push('unhandledrejection: '+String(e&&e.reason));});
        var le=window._loadError;window._hdLoadErr=[];
        window._loadError=function(err,stage){window._hdLoadErr.push(String(err&&err.message||err)+' (stage '+stage+')');if(typeof le==='function')return le.apply(this,arguments);};
        var ce=console.error.bind(console);
        console.error=function(){window._hdProbeErr.push('console.error: '+Array.prototype.slice.call(arguments).join(' '));ce.apply(console,arguments);};
        currentUser=currentUser||{uid:'probe-uid'};
        __THEME__
        // seed trades, so the OLD header would have had a count and a net to print here
        try{trades=[{id:'p1',symbol:'MNQ',side:'long',date:'2026-11-10',entryTime:'2026-11-10T14:31:00Z',exitTime:'2026-11-10T14:45:00Z',qty:1,entry:20000,exit:20030,pnl:134.97,net:134.97,gross:140,instrument:'futures'},
                     {id:'p2',symbol:'MES',side:'short',date:'2026-11-11',entryTime:'2026-11-11T15:01:00Z',exitTime:'2026-11-11T15:20:00Z',qty:2,entry:5800,exit:5795,pnl:-40,net:-40,gross:-36,instrument:'futures'}];}catch(e){}
        __TAB__
        renderApp();
        return 'OK';
      }catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()`);

      out.measure=w.eval(`(function(){try{
        var o={};
        var tb=document.querySelector('#app .topbar');
        if(!tb)return {noTopbar:true};
        var tr=tb.getBoundingClientRect();
        o.topH=tr.height;o.topTop=tr.top;
        o.innerH=window.innerHeight;o.innerW=window.innerWidth;
        var tabs=[].slice.call(document.querySelectorAll('#app [data-tab],#app [data-asubtop],#app [data-hometab]'));
        o.nTabs=tabs.length;
        o.tabsInTopbar=tabs.filter(function(b){return tb.contains(b);}).length;
        o.tabLabels=tabs.map(function(b){return b.textContent.replace(/\s+/g,' ').trim();});
        var vis=tabs.filter(function(b){return b.offsetWidth&&b.offsetHeight;});
        o.nTabsVisible=vis.length;
        var boxes=vis.map(function(b){var r=b.getBoundingClientRect();return {t:r.top,b:r.bottom,l:r.left,r:r.right};});
        o.tabBoxes=boxes;
        var logo=document.getElementById('logo-area'), outb=document.getElementById('so-btn');
        var stat=tb.querySelector('.tbstat');
        var rb=function(e){if(!e)return null;var r=e.getBoundingClientRect();return {t:r.top,b:r.bottom,l:r.left,r:r.right,w:r.width,h:r.height};};
        o.logo=rb(logo);o.out=rb(outb);o.stat=rb(stat);
        stat=stat||document.querySelector('#app .tbstat');
        o.statInTopbar=!!(stat&&tb.contains(stat));
        o.statInSubRow=!!(stat&&document.querySelector('#app .nav-subrow')&&document.querySelector('#app .nav-subrow').contains(stat));
        o.hasGate=!!(stat&&stat.querySelector('#tb-gate'));
        o.nStat=document.querySelectorAll('#app .tbstat').length;
        o.nGate=document.querySelectorAll('#app #tb-gate').length;
        o.gateTxt=(function(){var g=document.querySelector('#app #tb-gate');return g?g.textContent.replace(/\s+/g,' ').trim():null;})();
        o.queueInStat=(function(){var q=document.getElementById('tb-queue');return !!(q&&stat&&stat.contains(q));})();
        o.subStatText=(function(){var r=document.querySelector('#app .nav-subrow');return r?r.textContent.replace(/\s+/g,' ').trim():null;})();
        o.webullInStat=(function(){var c=document.getElementById('qb-top-chip');return c?!!(stat&&stat.contains(c)):'none';})();
        o.topText=tb.textContent.replace(/\s+/g,' ').trim();
        var subs=[].slice.call(document.querySelectorAll('#app .nav-subrow'));
        o.nSubRows=subs.length;
        if(subs.length){
          var s0=subs[0],sr=s0.getBoundingClientRect();
          o.subTop=sr.top;o.subH=sr.height;
          o.subBtns=s0.querySelectorAll('button').length;
          o.subPos=getComputedStyle(s0).position;
          o.subIsNext=(tb.nextElementSibling===s0);
        }
        o.subTabs=(function(){var r0=document.querySelector('#app .nav-subrow');if(!r0)return [];
          return [].slice.call(r0.querySelectorAll('button,[data-hometab],[data-asubtop]'))
            .filter(function(b){return b.offsetWidth&&b.offsetHeight;})
            .map(function(b){var r=b.getBoundingClientRect();
              return {n:b.textContent.replace(/\s+/g,' ').trim().slice(0,24),l:r.left,r:r.right,t:r.top,b:r.bottom};});})();
        o.subRowBox=(function(){var r0=document.querySelector('#app .nav-subrow');if(!r0)return null;
          var r=r0.getBoundingClientRect();return {l:r.left,r:r.right,t:r.top,b:r.bottom};})();
        // CAN THE LAST SUB-TAB BE READ AT ALL? The chip cluster is stuck to the right edge of
        //   the second row and carries a background, so whatever is under it is unreadable.
        //   With a scroller the honest question is not 'is it clear right now' but 'can it be
        //   brought clear': scroll the row hard right and measure the last sub-tab against the
        //   WHOLE cluster box (not the chips inside it - the cluster's own background is what
        //   hides the label).
        // THE ACTIVE SUB-TAB, AT REST (2026-11-18). This is the one the audit caught: the chip
        //   cluster is stuck to the right edge of the second row and carries a background, so a
        //   pill underneath it cannot be read - and the pill you are ON is the one that has to
        //   be readable without touching anything. Measured where the row actually sits.
        o.activeSub=(function(){var r0=document.querySelector('#app .nav-subrow');if(!r0)return null;
          var a=r0.querySelector('.btn-ghost.on'),st=r0.querySelector('.tbstat');
          if(!a)return {none:true};
          var r=a.getBoundingClientRect(),sr=st?st.getBoundingClientRect():null;
          return {n:a.textContent.replace(/\s+/g,' ').trim().slice(0,24),l:r.left,r:r.right,
                  statL:sr?sr.left:null,statR:sr?sr.right:null,
                  under:sr?Math.round(Math.min(r.right,sr.right)-Math.max(r.left,sr.left)):0,
                  offRight:Math.round(r.right-r0.getBoundingClientRect().right)};})();
        o.subClear=(function(){var r0=document.querySelector('#app .nav-subrow'),
            st=document.querySelector('#app .nav-subrow .tbstat');
          if(!r0||!st)return null;
          var was=r0.scrollLeft;r0.scrollLeft=r0.scrollWidth;
          var tabs=[].slice.call(r0.querySelectorAll('button,[data-hometab],[data-asubtop]'))
            .filter(function(b){return b.offsetWidth&&b.offsetHeight;});
          var sr=st.getBoundingClientRect(),worst=null;
          tabs.forEach(function(b){var r=b.getBoundingClientRect();
            var ov=Math.min(r.right,sr.right)-Math.max(r.left,sr.left);
            if(ov>1&&(!worst||ov>worst.ov))worst={n:b.textContent.replace(/\s+/g,' ').trim().slice(0,24),
              ov:Math.round(ov),l:r.left,r:r.right};});
          var out={scrolledTo:r0.scrollLeft,statL:sr.left,statR:sr.right,worst:worst,
                   gap:(function(){var g=r0.querySelector('.tbstat-gap');return g?Math.round(g.getBoundingClientRect().width):null;})()};
          r0.scrollLeft=was;return out;})();
        o.headerH=tr.height+(subs.length?subs[0].getBoundingClientRect().height:0);
        var de=document.documentElement;
        o.scrollW=de.scrollWidth;o.clientW=de.clientWidth;
        var strip=tb.querySelector('.tbscroll');
        o.stripOverflows=!!(strip&&strip.scrollWidth>strip.clientWidth+1);
        o.strip=rb(strip);
        // PHONE CLIPPING / COLLISION (Trading Log audit, 2026-11-18): every tab with its
        //   label, and every chip of the status cluster, so the judge names WHICH tab is cut
        //   off and WHICH chip is sitting on top of it instead of just 'it looks wrong'.
        o.tabNamed=vis.map(function(b){var r=b.getBoundingClientRect();
          return {n:b.textContent.replace(/\s+/g,' ').trim(),l:r.left,r:r.right,t:r.top,b:r.bottom};});
        // the cluster wraps the gate and the gauges in display:contents spans, which have NO
        //   box of their own - so walk descendants and keep the ones that actually draw.
        o.chips=(function(){var st=document.querySelector('#app .tbstat');if(!st)return [];
          return [].slice.call(st.querySelectorAll('*')).filter(function(c){
            if(!(c.offsetWidth&&c.offsetHeight))return false;
            for(var p=c.parentElement;p&&p!==st;p=p.parentElement){if(p.offsetWidth&&p.offsetHeight)return false;}
            return true;})
            .map(function(c){var r=c.getBoundingClientRect();
              return {n:c.textContent.replace(/\s+/g,' ').trim().slice(0,24),l:r.left,r:r.right,t:r.top,b:r.bottom};});})();
        return o;
      }catch(e){return {err:String(e&&e.stack?e.stack:e)};}})()`);

      // THE OWNER'S BUG: scroll the page down and look again
      out.scrolled=w.eval(`(function(){try{
        var c=document.querySelector('#app .content')||document.body;
        var sp=document.createElement('div');sp.id='hd-spacer';sp.style.height='4000px';c.appendChild(sp);
        window.scrollTo(0,2000);
        var o={scrollY:window.pageYOffset};
        var tb=document.querySelector('#app .topbar');
        var tr=tb?tb.getBoundingClientRect():null;
        o.topTop=tr?tr.top:null;o.topH=tr?tr.height:null;
        var s0=document.querySelector('#app .nav-subrow');
        if(s0){var sr=s0.getBoundingClientRect();
          o.subTop=sr.top;o.subBottom=sr.bottom;o.subH=sr.height;
          o.subBtns=s0.querySelectorAll('button').length;
          o.subVisible=(sr.top>=-1&&sr.bottom<=window.innerHeight+1&&sr.height>0);
          o.gap=tr?(sr.top-tr.bottom):null;
          var mid=document.elementFromPoint(Math.max(2,sr.left+6),sr.top+sr.height/2);
          o.hitSelf=!!(mid&&(s0===mid||s0.contains(mid)));
        } else {o.none=true;}
        return o;
      }catch(e){return {err:String(e&&e.stack?e.stack:e)};}})()`);

      out.loadErr=w.eval("(window._hdLoadErr||[]).join(' | ')+(window.loadError?' loadError='+String(window.loadError):'')");
      out.overlay=[].slice.call(d.body.children).filter(function(e){return /^\s*LOAD ERROR/.test(e.textContent||'');}).length;
      out.errs=w.eval('window._hdProbeErr||[]');
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='HDPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, name, width, height, theme, tab_js, shot_path):
    pdir = os.path.join(ROOT, '_hdprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    theme_js = ("prefs.theme='%s';applyTheme();" % theme) if theme else ''
    html = (PROBE_HTML.replace('__THEME__', theme_js).replace('__TAB__', tab_js)
            .replace('__IW__', str(width)).replace('__IH__', str(height)))
    io.open(ppath, 'w', encoding='utf-8').write(html)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(ROOT))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='hdprobe-')
    url = 'http://127.0.0.1:%d/_hdprobe/probe_%s.html' % (port, name)
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
    m = re.search(r'HDPROBE: (\{.*\})\s*</pre>', out or '', re.S)
    if not m:
        return {'err': 'no readout', 'raw_tail': (out or '')[-1500:]}
    try:
        return json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return {'err': 'unreadable readout: %s' % e}


def _overlap(a, b):
    """True when two boxes share any vertical band - i.e. they are on the same line."""
    if not a or not b:
        return False
    return min(a['b'], b['b']) - max(a['t'], b['t']) > 0


def judge(nm, r, want_sub):
    f = []
    if r.get('err'):
        return ['%s: %s' % (nm, r['err'])]
    if r.get('call') != 'OK':
        f.append('%s: setup returned %r' % (nm, r.get('call')))
    if r.get('errs'):
        f.append('%s: errors on the page: %s' % (nm, r['errs'][:5]))
    if r.get('loadErr'):
        f.append('%s: the app reported a load error: %s' % (nm, r['loadErr'][:200]))
    if r.get('overlay'):
        f.append('%s: the LOAD ERROR overlay is on the page' % nm)
    m = r.get('measure') or {}
    if m.get('noTopbar'):
        return f + ['%s: there is no .topbar' % nm]
    if m.get('err'):
        return f + ['%s: measuring failed: %s' % (nm, m['err'])]

    # --- ONE TOP ROW ---
    if (m.get('topH') or 0) > TOPBAR_MAX:
        f.append('%s: the top bar is %r px tall - more than one row (limit %d)'
                 % (nm, m.get('topH'), TOPBAR_MAX))
    if not m.get('nTabs'):
        f.append('%s: no main tab buttons on the page at all' % nm)
    elif m.get('tabsInTopbar') != m.get('nTabs'):
        f.append('%s: %r of %r main tabs are outside the top bar - they must be on the top line'
                 % (nm, m.get('tabsInTopbar'), m.get('nTabs')))
    boxes = m.get('tabBoxes') or []
    if len(boxes) < 2:
        f.append('%s: only %d visible tab buttons' % (nm, len(boxes)))
    else:
        first, last = boxes[0], boxes[-1]
        if not _overlap(first, last):
            f.append('%s: the first and last tab are not on the same line (%r vs %r)'
                     % (nm, first, last))
        for i, b in enumerate(boxes):
            if not _overlap(first, b):
                f.append('%s: tab %d sits on a different line from the first tab' % (nm, i))
                break
        same_line = [('the logo', m.get('logo')), ('the OUT button', m.get('out'))]
        if m.get('statInTopbar'):
            same_line.append(('the status cluster', m.get('stat')))
        for who, box in same_line:
            if box and not _overlap(first, box):
                f.append('%s: %s is not on the same line as the tabs' % (nm, who))

    # --- A PHONE SHOWS THE TAB YOU ARE ON, AND NO CHIP SITS ON A SUB-TAB (2026-11-18) ---
    # Trading Log's audit found both halves of this at 375 px: the BUILDER tab cut in half, and
    #   the WEBULL PAPER sub-tab under the NT GATE chip. The strip is a sideways scroller on
    #   purpose, so a tab off to the right is NOT the bug - the bugs are (a) the tab you are
    #   actually on being off screen, and (b) a chip drawn on top of a sub-tab, which no amount of
    #   scrolling can fix. Measured, not eyeballed: the geometry is in tabNamed / subTabs / chips.
    strip = m.get('strip') or {}
    if (m.get('innerW') or 0) <= 700 and strip:
        vis = [t for t in (m.get('tabNamed') or [])
               if t['l'] >= strip.get('l', 0) - 1 and t['r'] <= strip.get('r', 0) + 1]
        if len(vis) < 3:
            cut = [t['n'] for t in (m.get('tabNamed') or []) if t not in vis][:3]
            f.append('%s: only %d of %d main tabs fit the %.0f px tab strip - %s cut off. The '
                     'strip scrolls, but three tabs is the floor: fewer means the bar is being '
                     'eaten by something that is not a tab'
                     % (nm, len(vis), len(m.get('tabNamed') or []), strip.get('w') or 0,
                        ', '.join(cut) or 'nothing named'))
        # THE SUB-TAB YOU ARE ON MUST BE READABLE WITHOUT SCROLLING. The cluster is sticky over
        #   this row, so a pill left under it is a label nobody can read - and the active pill is
        #   the one that matters. The fix scrolls it clear; this is what proves it happened.
        a = m.get('activeSub') or {}
        if a.get('none'):
            f.append('%s: the second row has sub-tabs but none of them is marked active - nothing '
                     'can scroll the open one into view' % nm)
        elif a.get('under', 0) > 1:
            f.append('%s: the open %r sub-tab is %r px under the status cluster (sub-tab %.0f-%.0f, '
                     'cluster %.0f-%.0f) - the chips are stuck to the right edge and carry a '
                     'background, so the open pill has to be scrolled clear of them'
                     % (nm, a.get('n'), a.get('under'), a.get('l'), a.get('r'),
                        a.get('statL') or 0, a.get('statR') or 0))
        elif (a.get('offRight') or 0) > 1:
            f.append('%s: the open %r sub-tab is %r px past the right edge of its row'
                     % (nm, a.get('n'), a.get('offRight')))

    # --- STATUS CLUSTER, FAR RIGHT ---
    # THE STATUS CLUSTER lives in the top bar on a laptop and on the second row on a phone (see
    #   .tbstat): below 700 px the logo, the tabs, the chips and NET / GROSS + gear + OUT do not fit
    #   on one line, and a chip scrolled off the side is a status nobody reads. Either way there is
    #   exactly ONE of it - the gate chip and the queue dials refresh in place by id.
    if not (m.get('statInTopbar') or m.get('statInSubRow')):
        f.append('%s: the status cluster (.tbstat) is in neither header row' % nm)
    if (m.get('innerW') or 0) > 700 and not m.get('statInTopbar'):
        f.append('%s: on a %r px window the status cluster is not in the top bar' % (nm, m.get('innerW')))
    if (m.get('nStat') or 0) != 1 or (m.get('nGate') or 0) != 1:
        f.append('%s: %r status clusters and %r gate chips in the page - there must be exactly one of each'
                 % (nm, m.get('nStat'), m.get('nGate')))
    if not m.get('hasGate'):
        f.append('%s: the NT GATE chip is not in the status cluster' % nm)
    elif 'NT GATE' not in (m.get('gateTxt') or ''):
        f.append('%s: the NT GATE chip reads %r' % (nm, m.get('gateTxt')))
    if m.get('webullInStat') is False:
        f.append('%s: the WEBULL chip is drawn outside the status cluster' % nm)
    # FAR RIGHT, AND ALWAYS ON SCREEN. The cluster is stuck to the right edge of the scrolling
    #   strip, so the test is its right edge against the strip's, not its left against the tabs:
    #   on a phone the tabs slide UNDER it and it is deliberately over them. Where the strip does
    #   not overflow at all, nothing can be under it, so there it must also start past the last tab.
    if m.get('stat'):
        if m.get('statInTopbar') and m.get('strip') and abs(m['stat']['r'] - m['strip']['r']) > 2:
            f.append('%s: the status cluster is not at the right edge of the tab strip (%r vs %r)'
                     % (nm, m['stat']['r'], m['strip']['r']))
        if m['stat']['l'] < -1 or m['stat']['r'] > (m.get('innerW') or 0) + 1:
            f.append('%s: the status cluster is off screen (%r to %r, viewport %r) - a status the '
                     'owner cannot see is no status' % (nm, m['stat']['l'], m['stat']['r'], m.get('innerW')))
        if m.get('statInTopbar') and not m.get('stripOverflows') and boxes and m['stat']['l'] < boxes[-1]['r'] - 1:
            f.append('%s: the status cluster starts left of the last tab (%r < %r) - it belongs far right'
                     % (nm, m['stat']['l'], boxes[-1]['r']))

    # --- NO TRADE COUNT, NO NET (owner: "remove the 134 net and trade count") ---
    txt = m.get('topText') or ''
    if re.search(r'\d+\s+trades\b', txt):
        f.append('%s: the header still prints a trade count: %r' % (nm, txt[:160]))
    if re.search(r'[-+]?\$\s?[\d,]', txt):
        f.append('%s: the header still prints a money figure: %r' % (nm, txt[:160]))

    # --- SECOND ROW ---
    n_sub = m.get('nSubRows') or 0
    if want_sub:
        if n_sub != 1:
            f.append('%s: a tab with sub-tabs drew %d sub-tab rows, expected exactly 1' % (nm, n_sub))
        else:
            if not m.get('subIsNext'):
                f.append('%s: the sub-tab row is not the element directly after the top bar' % nm)
            if m.get('subPos') != 'sticky':
                f.append('%s: the sub-tab row is position:%r, not sticky - it will scroll away'
                         % (nm, m.get('subPos')))
            # measured as a GAP, not as an absolute y: the probe's own iframe puts the app a few
            # px down the page, and what matters is that the two rows are welded together.
            _gap = (m.get('subTop') or 0) - ((m.get('topTop') or 0) + (m.get('topH') or 0))
            if abs(_gap) > 3:
                f.append('%s: the sub-tab row sits %r px from the bottom of the top bar, not welded to it'
                         % (nm, _gap))
            if not (m.get('subBtns') or 0) >= 2:
                f.append('%s: the sub-tab row has %r buttons' % (nm, m.get('subBtns')))
        if (m.get('headerH') or 0) > HEADER_MAX:
            f.append('%s: the header is %r px - more than two rows (limit %d)'
                     % (nm, m.get('headerH'), HEADER_MAX))
    else:
        if n_sub:
            f.append('%s: a tab with no sub-tabs drew %d sub-tab row(s) - it must be one row tall'
                     % (nm, n_sub))
        if (m.get('headerH') or 0) > TOPBAR_MAX:
            f.append('%s: a tab with no sub-tabs has a %r px header' % (nm, m.get('headerH')))

    # --- THE OWNER'S BUG: still there after scrolling ---
    sc = r.get('scrolled') or {}
    if sc.get('err'):
        f.append('%s: the scroll check failed: %s' % (nm, sc['err']))
    elif want_sub:
        if sc.get('none'):
            f.append('%s: the sub-tab row is gone from the page after scrolling' % nm)
        else:
            if not (sc.get('scrollY') or 0) >= 1500:
                f.append('%s: the page only scrolled to %r px - the check did not run'
                         % (nm, sc.get('scrollY')))
            if not sc.get('subVisible'):
                f.append('%s: THE SUB-TABS DISAPPEAR WHEN SCROLLING (after a 2000 px scroll the row '
                         'is at top %r, bottom %r)' % (nm, sc.get('subTop'), sc.get('subBottom')))
            if abs((sc.get('gap') if sc.get('gap') is not None else 99)) > 2:
                f.append('%s: after scrolling the sub-tab row is %r px from the top bar, not welded to it'
                         % (nm, sc.get('gap')))
            if not (sc.get('subBtns') or 0) >= 2:
                f.append('%s: after scrolling the sub-tab row has %r buttons' % (nm, sc.get('subBtns')))
            if sc.get('hitSelf') is False:
                f.append('%s: after scrolling something is drawn over the sub-tab row' % nm)

    # --- NO SIDEWAYS PAGE SCROLL ---
    if (m.get('scrollW') or 0) > (m.get('clientW') or 0) + 1:
        f.append('%s: the page scrolls sideways (%r > %r)' % (nm, m.get('scrollW'), m.get('clientW')))
    return f


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    chrome = find_chrome()
    if not chrome:
        print('HDPROBE: INCONCLUSIVE -- chrome not found')
        return 2
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.gettempdir()
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    HOME = "activeTab='home';window._lastLogTab='home';"
    ANAL = "activeTab='analytics';window._lastLogTab='analytics';"
    # WEBULL PAPER on a phone is the audit's own case (Trading Log, 11-18): the LAST and widest
    #   sub-tab, active, on the narrowest screen - the pill most likely to end up under the chips.
    WBSUB = "activeTab='augur';augurSub='qqqpaper';window._lastLogTab='augur';"
    # THE PC LOAD CHIP WITH A READING IN IT (board item 12, 11-18). Absent data draws nothing, so
    #   the other cases only ever test the empty chip. These two put a loaded box in the doc - the
    #   widest the chip ever gets, in its red state - and check the header still fits: one top line
    #   on a laptop, no sideways page scroll on a phone.
    PCL = ("window._pcLoad={ok:true,cpu_pct:98.9,mem_pct:92.4,free_gb:2.4,total_gb:31.7,runners:5,"
           "checked_at:new Date().toISOString().slice(0,19).replace('T',' ')};")
    # THE SAME CHIP WITH THE LIVE FEED PAUSED (11-19). A tab nobody is looking at detaches its
    #   listeners, so the chip says LIVE PAUSED rather than a number nothing is refreshing. It is
    #   wider than the numbers it replaces, so the header has to still fit on a laptop and a phone.
    LSP = PCL + "window._lsPaused=true;"
    # AND WITH THE DAILY ALLOWANCE GONE (11-19 circuit breaker). The chip says LIVE OFF and a line is
    #   pinned to the bottom of the screen; neither may push the header off its one line or make the
    #   page scroll sideways on a phone.
    QOUT = PCL + "window._fsQuotaOut=true;"
    cases = (('home_1400', 1400, 900, '', HOME, True),
             ('anal_1400', 1400, 900, '', ANAL, False),
             ('home_375', 375, 812, '', HOME, True),
             ('mono_375', 375, 812, 'mono', HOME, True),
             ('wbsub_375', 375, 812, '', WBSUB, True),
             ('pcload_1366', 1366, 900, '', PCL + HOME, True),
             ('pcload_375', 375, 812, '', PCL + HOME, True),
             ('lspaused_1366', 1366, 900, '', LSP + HOME, True),
             ('lspaused_375', 375, 812, '', LSP + HOME, True),
             ('quotaout_1366', 1366, 900, '', QOUT + HOME, True),
             ('quotaout_375', 375, 812, '', QOUT + HOME, True))
    fails = []
    for nm, w, h, theme, tab_js, want_sub in cases:
        shot = os.path.join(out_dir, 'header_%s.png' % nm)
        r = run_case(chrome, nm, w, h, theme, tab_js, shot)
        m = r.get('measure') or {}
        brief = {k: m.get(k) for k in ('topH', 'headerH', 'nTabs', 'tabsInTopbar', 'nSubRows',
                                       'subTop', 'topTop', 'subH', 'scrollW', 'clientW', 'stripOverflows')}
        brief['scrolledSubTop'] = (r.get('scrolled') or {}).get('subTop')
        brief['errs'] = r.get('errs')
        if os.environ.get('HDPROBE_GEOM'):
            brief['strip'] = m.get('strip'); brief['statInSubRow'] = m.get('statInSubRow')
            brief['tabNamed'] = m.get('tabNamed'); brief['chips'] = m.get('chips')
            brief['subTabs'] = m.get('subTabs')
        print('%s: %s  shot -> %s' % (nm, json.dumps(brief), shot))
        fails += judge(nm, r, want_sub)
    if fails:
        print('HDPROBE: FAIL')
        for x in fails:
            print('  - ' + x)
        return 1
    print('HDPROBE: PASS (one top line - logo, every main tab, then the status cluster far right '
          'with NT GATE and the backtest gauges, no trade count and no net; sub-tabs are the second '
          'row, pinned under it and still on screen after a 2000 px scroll; a tab with no sub-tabs '
          'is one row; laptop 1400 + phone 375 + MONO 375, no sideways page scroll)')
    return 0


if __name__ == '__main__':
    try:   # any Chrome this run starts dies with it, however the run ends (tools/kill_on_exit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kill_on_exit
        kill_on_exit.install()
    except Exception:
        pass
    sys.exit(main())
