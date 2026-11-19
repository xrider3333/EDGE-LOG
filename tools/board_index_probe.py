#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/board_index_probe.py -- gate for reading the open board out of meta/board_index.

WHY THIS EXISTS
---------------
The board used to be read by listening to the whole users/{uid}/board collection: 324 documents,
324 billed reads, every time a tab opened the page and again every time a listener re-attached.
That was the biggest single line in a tab's daily bill, and the free allowance ran dry twice in
November because of bills like it. The board is now read from meta/board_index (a head document
with a revision counter and the last two dozen writes carried inline) plus meta/board_index_<i>
shard documents: three reads instead of 324, and nothing at all for the usual row change.

The thing that must not break is the OWNER'S BOARD. He reads it to decide what to work on, DONE
rows stay on it on purpose, and a row silently missing is worse than a slow page. So this probe
drives the real page with a 324-row fixture and checks, on a laptop and a phone:

  * the first head snapshot reads the SHARDS and nothing else: every one of the 324 rows lands,
    and the collection listener is never attached (that would spend the reads anyway)
  * a row written on the PC arrives INLINE on the next head snapshot: the new text is on the page
    and NOT ONE further document was fetched
  * a tab that has missed more than the inline window re-reads the shards - three reads, not 324
  * no index, or a shard that will not read, FALLS BACK to the old collection listener, because a
    stale index may make the board slower and must never make it wrong
  * the owner's own CONFIRM click writes the row AND tells the index, so his click cannot be
    undone by the next head snapshot
  * the board renders all 324 rows, DONE rows included, with no console error and no sideways
    scroll on a phone

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks a push on
tooling trouble - no Chrome, timeout).

Stdlib only, plus a subprocess call to local Chrome.
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
<html><head><meta charset="utf-8"><title>board index probe</title></head>
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
      out.r=w.__bdp||null;
      out.scrollW=d.documentElement.scrollWidth;
      out.clientW=d.documentElement.clientWidth;
      out.rows=d.querySelectorAll('[data-bdrow]').length;
      out.loadErr=/LOAD ERROR/.test(d.body.innerText||'')?1:0;
      out.text=(d.body.innerText||'').slice(0,4000);
    }catch(e){out.err=String(e);}
    document.getElementById('o').textContent='BDPROBE: '+JSON.stringify(out);
  }
  var fr=document.getElementById('f');
  fr.onload=function(){
    var w=fr.contentWindow;
    w.eval(`(function(){
      window.renderAuth=function(){};
      window._bdpErr=[];
      window.onerror=function(m){window._bdpErr.push('onerror: '+String(m));};
      window.addEventListener('unhandledrejection',function(e){window._bdpErr.push('rejection: '+String(e&&e.reason));});
      window._bdpWarn=[];var cw=console.warn.bind(console);
      console.warn=function(){window._bdpWarn.push(Array.prototype.slice.call(arguments).map(String).join(' '));cw.apply(console,arguments);};
      var ce=console.error.bind(console);
      console.error=function(){window._bdpErr.push('console.error: '+Array.prototype.slice.call(arguments).join(' '));ce.apply(console,arguments);};
      __THEME__
      currentUser=currentUser||{uid:'probe-uid'};
      // THE 324-ROW BOARD, built here so the case does not depend on what is live.
      var STATUSES=['done','pass','fail','confirmed','run','queued','park','needs-you','open'];
      var PREF=['w','t','b','c','p','q'];
      var rows=[];
      for(var i=0;i<324;i++){
        var pre=PREF[i%PREF.length];
        rows.push({_id:pre+(i+1),label:'item '+(i+1),title:'row number '+(i+1)+' on the board',
          status:STATUSES[i%STATUSES.length],statusText:'state line '+(i+1),
          why:'the reason row '+(i+1)+' exists',who:'LANE',date:'2026-11-19',order:i+1,
          tab:({w:'WORK',t:'RUNS',b:'AUTOMATIONS',c:'AUTOMATIONS',p:'PC',q:'QWEN'})[pre]});
      }
      window.__bdpRows=rows;
      var parts=[[],[],[]];
      rows.forEach(function(r,i){parts[Math.floor(i/120)].push(r);});
      window.__bdpShards=parts;
      // EVERY FETCH RECORDED, and answered from the fixture - so the probe can say exactly how
      //   many documents a decision cost. The shape is the Firestore REST shape the page parses.
      window.__bdpFetched=[];
      function fsVal(v){
        if(v===null||v===undefined)return {nullValue:null};
        if(typeof v==='number')return Number.isInteger(v)?{integerValue:String(v)}:{doubleValue:v};
        if(typeof v==='boolean')return {booleanValue:v};
        if(Array.isArray(v))return {arrayValue:{values:v.map(fsVal)}};
        if(typeof v==='object'){var f={};Object.keys(v).forEach(function(k){f[k]=fsVal(v[k]);});return {mapValue:{fields:f}};}
        return {stringValue:String(v)};
      }
      window.fetch=function(u){
        window.__bdpFetched.push(String(u));
        var m=/board_index_([0-9]+)/.exec(String(u));
        if(!m)return Promise.resolve({ok:false,status:404,json:function(){return Promise.resolve({});}});
        var i=+m[1];
        if(window.__bdpShardFail)return Promise.resolve({ok:false,status:500,json:function(){return Promise.resolve({});}});
        return Promise.resolve({ok:true,status:200,json:function(){
          return Promise.resolve({fields:fsVal({rows:window.__bdpShards[i]}).mapValue.fields});}});
      };
      window._idToken=function(){return Promise.resolve('probe-token');};
      // A RECORDING DATABASE. onSnapshot is recorded, never attached, so the probe can prove the
      //   collection listener was not used; set / increment are recorded with their payload.
      window.__bdpListens=[];window.__bdpWrites=[];
      var rec=function(path){return {
        collection:function(c){return rec(path+'/'+c);},
        doc:function(x){return rec(path+'/'+x);},
        onSnapshot:function(){window.__bdpListens.push(path);return function(){};},
        set:function(o){window.__bdpWrites.push({doc:path,keys:Object.keys(o||{}).join(','),
          status:o.status,statusText:o.statusText,confirmedBy:o.confirmedBy,
          rev:(o.rev&&o.rev.__inc)||null,recent:(o.recent&&o.recent.__union)||null});
          return Promise.resolve();},
        get:function(){return Promise.resolve({exists:false,data:function(){return {};}});}};};
      db=rec('');
      auth={currentUser:{uid:'probe-uid',getIdToken:function(){return Promise.resolve('probe-token');}}};
      if(typeof firebase==='undefined')firebase={};
      firebase.app=function(){return {options:{projectId:'probe'}};};
      firebase.firestore=firebase.firestore||function(){return db;};
      firebase.firestore.FieldValue={increment:function(n){return {__inc:n};},
        arrayUnion:function(x){return {__union:x};}};
      activeTab='augur';augurSub='board';boardSub='board';
      window._bdRows={};window._bdRev=0;window._bdMeta={};
      window.__bdp={err:window._bdpErr};
      return 1;
    })()`);

    // every step is driven from here, so each decision can be measured on its own
    var steps = [
      // 1. FIRST SNAPSHOT: the shards, and nothing else
      `(function(){
         window.__bdpFetched=[];window.__bdpListens=[];
         var head={rev:100,shards:3,recent:[],map:{}};
         window.__bdp.first=window._bdOnHead('probe-uid',head,function(){},function(y){window.__bdp.fell='first: '+y;});
         return 1;})()`,
      // give the shard fetches a turn, then read what landed
      `(function(){
         window.__bdp.firstRows=Object.keys(window._bdRows||{}).length;
         window.__bdp.firstFetched=window.__bdpFetched.length;
         window.__bdp.firstListens=window.__bdpListens.slice();
         window.__bdp.firstRev=window._bdRev;
         window.__bdp.sample=(window._bdRows['w1']||{}).statusText||null;
         renderApp();return 1;})()`,
      // 2. A ROW WRITTEN ON THE PC: inline, no further reads
      `(function(){
         window.__bdpFetched=[];
         var r=Object.assign({},window.__bdpRows[0]);r.statusText='CHANGED ON THE PC';
         var head={rev:101,shards:3,map:{},recent:[{rev:101,id:'w1',row:r}]};
         window.__bdp.second=window._bdOnHead('probe-uid',head,function(){},function(y){window.__bdp.fell='second: '+y;});
         window.__bdp.secondFetched=window.__bdpFetched.length;
         window.__bdp.secondText=(window._bdRows['w1']||{}).statusText||null;
         window.__bdp.secondRows=Object.keys(window._bdRows||{}).length;
         window.__bdp.secondRev=window._bdRev;
         return 1;})()`,
      // 3. A TAB THAT MISSED TOO MANY WRITES: the shards again, three reads, not 324
      `(function(){
         window.__bdpFetched=[];window._bdFetching=false;
         var head={rev:400,shards:3,map:{},recent:[{rev:399,id:'w1',row:window.__bdpRows[0]}]};
         window.__bdp.third=window._bdOnHead('probe-uid',head,function(){},function(y){window.__bdp.fell='third: '+y;});
         return 1;})()`,
      `(function(){
         window.__bdp.thirdFetched=window.__bdpFetched.length;
         window.__bdp.thirdRows=Object.keys(window._bdRows||{}).length;
         return 1;})()`,
      // 4. NO INDEX AT ALL: fall back to the collection, once
      `(function(){
         window.__bdpListens=[];window._bdFellBack=false;
         window.__bdp.none=window._bdOnHead('probe-uid',null,function(){},window._bdFallback||function(y){window.__bdp.fellNone=y;});
         window.__bdp.noneListens=window.__bdpListens.slice();
         return 1;})()`,
      // 5. A SHARD THAT WILL NOT READ: same fallback
      `(function(){
         window.__bdpShardFail=true;window._bdFetching=false;window._bdFellBack=false;
         window.__bdpListens=[];window.__bdp.fellShard=null;
         window._bdOnHead('probe-uid',{rev:900,shards:3,map:{},recent:[]},function(){},
           function(y){window.__bdp.fellShard=y;});
         return 1;})()`,
      `(function(){window.__bdpShardFail=false;
         window.__bdp.fellShardSeen=window.__bdp.fellShard;return 1;})()`,
      // 6. THE OWNER'S CONFIRM: the row AND the index
      `(function(){
         window.__bdpWrites=[];
         window._bdRows['w1']=Object.assign({},window.__bdpRows[0]);
         bdAct('w1','confirm');return 1;})()`,
      // 7. THE SAME BOARD THE OLD LISTENER DREW: fill the rows the way the collection listener
      //    did and count again. The index is only correct if the page looks identical.
      `(function(){
         window.__bdp.idxDrawn=document.querySelectorAll('[data-bdrow]').length;
         var m={};window.__bdpRows.forEach(function(r){m[r._id]=Object.assign({},r);});
         window._bdRows=m;renderApp();
         window.__bdp.refDrawn=document.querySelectorAll('[data-bdrow]').length;
         return 1;})()`,
      `(function(){
         window.__bdp.writes=window.__bdpWrites.slice();
         window.__bdp.errs=window._bdpErr.slice();
         window.__bdp.warns=window._bdpWarn.slice();
         renderApp();
         return 1;})()`
    ];
    var i=0;
    (function next(){
      if(i>=steps.length){setTimeout(function(){report('done');},700);return;}
      try{w.eval(steps[i]);}catch(e){w.__bdp=w.__bdp||{};w.__bdp.threw=String(e);}
      i++;setTimeout(next,450);
    })();
  };
  setTimeout(function(){report('timeout');},60000);
})();
</script></body></html>
"""


def run_case(chrome, name, width, height, theme):
    pdir = os.path.join(ROOT, '_bdprobe')
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
    prof = tempfile.mkdtemp(prefix='bdprobe-')
    url = 'http://127.0.0.1:%d/_bdprobe/probe_%s.html' % (port, name)
    base = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
            '--user-data-dir=' + prof, '--virtual-time-budget=90000',
            '--window-size=%d,%d' % (width, height + 40)]
    try:
        out = subprocess.run(base + ['--dump-dom', url], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=240).stdout
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'BDPROBE: (\{.*\})\s*</pre>', out or '', re.S)
    if not m:
        return {'err': 'no readout', 'raw_tail': (out or '')[-1500:]}
    try:
        return json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return {'err': 'unreadable readout: %s' % e}


def judge(nm, res, phone):
    bad = []
    if res.get('err'):
        return ['%s: %s %s' % (nm, res['err'], str(res.get('raw_tail', ''))[-400:])]
    r = res.get('r') or {}
    if r.get('threw'):
        bad.append('%s: a step threw: %s' % (nm, r['threw']))

    # 1. the first snapshot reads the shards, lands every row, and never touches the collection
    if r.get('first') != 'shards':
        bad.append('%s: the first head snapshot decided %r, not shards' % (nm, r.get('first')))
    if r.get('firstRows') != 324:
        bad.append('%s: %s of 324 rows landed from the index' % (nm, r.get('firstRows')))
    if r.get('firstFetched') != 3:
        bad.append('%s: the first read cost %s documents, expected 3' % (nm, r.get('firstFetched')))
    if [x for x in (r.get('firstListens') or []) if x.endswith('/board')]:
        bad.append('%s: the collection listener was attached anyway: %s'
                   % (nm, r.get('firstListens')))
    if r.get('fell'):
        bad.append('%s: fell back when it should not have: %s' % (nm, r.get('fell')))

    # 2. a row written on the PC costs NOTHING to see
    if r.get('second') != 'inline':
        bad.append('%s: a single new row decided %r, not inline' % (nm, r.get('second')))
    if r.get('secondFetched'):
        bad.append('%s: seeing one changed row cost %s extra read(s)' % (nm, r.get('secondFetched')))
    if r.get('secondText') != 'CHANGED ON THE PC':
        bad.append('%s: the changed row did not arrive: %r' % (nm, r.get('secondText')))
    if r.get('secondRows') != 324:
        bad.append('%s: the inline update left %s rows' % (nm, r.get('secondRows')))

    # 3. a long-asleep tab pays three reads, never 324
    if r.get('third') != 'shards':
        bad.append('%s: a tab far behind decided %r, not shards' % (nm, r.get('third')))
    if r.get('thirdFetched') != 3:
        bad.append('%s: catching up cost %s documents, expected 3' % (nm, r.get('thirdFetched')))
    if r.get('thirdRows') != 324:
        bad.append('%s: catching up left %s rows' % (nm, r.get('thirdRows')))

    # 4 + 5. no index, or an unreadable shard, still shows a board
    if r.get('none') != 'fallback':
        bad.append('%s: no index decided %r, not fallback' % (nm, r.get('none')))
    if not [x for x in (r.get('noneListens') or []) if x.endswith('/board')]:
        bad.append('%s: with no index the collection listener was NOT attached: %s'
                   % (nm, r.get('noneListens')))
    if not r.get('fellShardSeen'):
        bad.append('%s: an unreadable shard did not fall back' % nm)

    # 6. the owner's click reaches both the row and the index
    w = r.get('writes') or []
    row_w = [x for x in w if str(x.get('doc', '')).endswith('/board/w1')]
    idx_w = [x for x in w if str(x.get('doc', '')).endswith('/meta/board_index')]
    if not row_w:
        bad.append('%s: CONFIRM wrote no board row' % nm)
    elif not row_w[0].get('confirmedBy'):
        bad.append('%s: CONFIRM wrote the row without the stamp: %s' % (nm, row_w[0]))
    if not idx_w:
        bad.append('%s: CONFIRM did not tell the index - his click would be undone' % nm)
    elif idx_w[0].get('rev') != 1 or not idx_w[0].get('recent'):
        bad.append('%s: the index poke is wrong: %s' % (nm, idx_w[0]))

    # the board itself
    if res.get('loadErr'):
        bad.append('%s: LOAD ERROR on the page' % nm)
    if not (r.get('idxDrawn') or 0):
        bad.append('%s: the board drew nothing from the index' % nm)
    elif r.get('idxDrawn') != r.get('refDrawn'):
        bad.append('%s: the index board drew %s rows, the collection board drew %s - not the '
                   'same board' % (nm, r.get('idxDrawn'), r.get('refDrawn')))
    for e in (r.get('errs') or []):
        if 'index read failed' in e or 'collection directly' in e:
            continue
        bad.append('%s: %s' % (nm, e))
    if phone and (res.get('scrollW') or 0) > (res.get('clientW') or 0):
        bad.append('%s: the phone page scrolls sideways (%s > %s)'
                   % (nm, res.get('scrollW'), res.get('clientW')))
    return bad


def main():
    chrome = find_chrome()
    if not chrome:
        print('BDPROBE: INCONCLUSIVE (no chrome found)')
        return 2
    cases = (('laptop_1400', 1400, 900, '', False),
             ('phone_375', 375, 812, '', True))
    fails = []
    for nm, w, h, theme, phone in cases:
        try:
            res = run_case(chrome, nm, w, h, theme)
        except subprocess.TimeoutExpired:
            print('BDPROBE: INCONCLUSIVE (%s timed out)' % nm)
            return 2
        bad = judge(nm, res, phone)
        r = res.get('r') or {}
        print('%s: first=%s rows=%s fetched=%s | inline=%s extra=%s | behind=%s fetched=%s | '
              'drawn=%s/%s' % (nm, r.get('first'), r.get('firstRows'), r.get('firstFetched'),
                            r.get('second'), r.get('secondFetched'), r.get('third'),
                            r.get('thirdFetched'), r.get('idxDrawn'), r.get('refDrawn')))
        for wmsg in (r.get('warns') or [])[:6]:
            print('   warn: ' + str(wmsg)[:220])
        fails += bad
    if fails:
        print('BDPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('BDPROBE: PASS (324 rows read from the index for 3 documents instead of 324; a row '
          'written on the PC arrives inline for nothing; a tab far behind pays 3; no index or an '
          'unreadable shard falls back to the collection; the owner CONFIRM writes row and index)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
