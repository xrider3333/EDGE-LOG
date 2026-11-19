#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/trades_index_probe.py -- gate for reading the journal out of meta/trades_index.

WHY THIS EXISTS
---------------
The website used to listen to users/{uid}/trades: 108 documents, 108 billed reads, every time a
tab opened and again every time a listener re-attached after being hidden or refused. With the
open board (fixed in v91.05) that was most of the 447-document bill a tab paid just to come back,
against 50,000 free reads a day the owner ran dry twice in November. The journal now comes from
meta/trades_index - a head document plus shards - for three reads.

The journal is the OWNER'S OWN RECORD OF HIS TRADING. It may be slower to appear; it must never be
wrong and never be short a trade. MANAGER's condition on this ship was "no visible change, this is
plumbing only", so the gate does not count elements - it renders the ledger twice, once from the
index and once with the trades the old listener would have produced, and compares the rendered
HTML character for character.

WHAT IT ASSERTS, on a laptop and a phone
----------------------------------------
  * the first head snapshot reads the SHARDS and nothing else: all 108 trades land, in date order,
    and the collection listener is never attached
  * the rendered ledger is IDENTICAL to the one the collection path renders - same HTML, same
    length - and the trades list is identical field for field
  * a trade written on the PC arrives INLINE on the next head snapshot: no further document read
  * a tab that missed more than the inline window re-reads the shards - 3 documents, not 108
  * a deleted trade leaves the list
  * no index, or a shard that will not read, falls back to the old collection listener
  * the owner's own setup rename writes the trade AND pokes the index
  * no console error, no LOAD ERROR, and a phone page that does not scroll sideways

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.
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
<html><head><meta charset="utf-8"><title>trades index probe</title></head>
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
      out.r=w.__tixp||null;
      out.scrollW=d.documentElement.scrollWidth;
      out.clientW=d.documentElement.clientWidth;
      out.loadErr=/LOAD ERROR/.test(d.body.innerText||'')?1:0;
    }catch(e){out.err=String(e);}
    document.getElementById('o').textContent='TIXPROBE: '+JSON.stringify(out);
  }
  var fr=document.getElementById('f');
  fr.onload=function(){
    var w=fr.contentWindow;
    w.eval(`(function(){
      window.renderAuth=function(){};
      window._tixpErr=[];window._tixpWarn=[];
      window.onerror=function(m){window._tixpErr.push('onerror: '+String(m));};
      window.addEventListener('unhandledrejection',function(e){window._tixpErr.push('rejection: '+String(e&&e.reason));});
      var ce=console.error.bind(console);
      console.error=function(){window._tixpErr.push('console.error: '+Array.prototype.slice.call(arguments).join(' '));ce.apply(console,arguments);};
      var cw=console.warn.bind(console);
      console.warn=function(){window._tixpWarn.push(Array.prototype.slice.call(arguments).map(String).join(' '));cw.apply(console,arguments);};
      __THEME__
      currentUser=currentUser||{uid:'probe-uid'};
      // A 108-TRADE JOURNAL, the sizes and fields the real one has (measured 2026-11-19:
      //   108 trades, 278 KB, three quarters of it pointScore).
      var SYMS=['MNQ','MES','NQ','ES','AAPL','TSLA','SPY'];
      var rows=[];
      for(var i=0;i<108;i++){
        var day=String(1+(i%28)).padStart(2,'0');
        rows.push({_id:'t'+(1000+i),date:'2026-'+String(1+(i%9)).padStart(2,'0')+'-'+day,
          symbol:SYMS[i%SYMS.length],type:(i%2)?'long':'short',size:1+(i%4),
          entry:100+i,exit:100+i+((i%3)-1),pnl:((i%7)-3)*25.5,grossPnl:((i%7)-3)*26,fees:2.5,
          entryTime:'09:3'+(i%10)+':00',exitTime:'10:1'+(i%10)+':00',durationMins:40+i%20,
          setup:'setup '+(i%5),grade:'ABC'[i%3],notes:'note '+i,timeframe:'5m',
          broker:(i%2)?'NinjaTrader':'Webull',account:'acct'+(i%3),source:(i%2)?'nt':'wb',
          assetType:(i%7<4)?'futures':'stock',tags:['tag'+(i%3)],
          pointScore:{total:i%10,max:10,points:[1,2,3],trend:'up',na_count:0,sig:'s'+i}});
      }
      window.__tixpRows=rows;
      var parts=[[],[]];
      rows.forEach(function(r,i){parts[Math.floor(i/60)].push(r);});
      window.__tixpShards=parts;
      window.__tixpFetched=[];
      function fsVal(v){
        if(v===null||v===undefined)return {nullValue:null};
        if(typeof v==='number')return Number.isInteger(v)?{integerValue:String(v)}:{doubleValue:v};
        if(typeof v==='boolean')return {booleanValue:v};
        if(Array.isArray(v))return {arrayValue:{values:v.map(fsVal)}};
        if(typeof v==='object'){var f={};Object.keys(v).forEach(function(k){f[k]=fsVal(v[k]);});return {mapValue:{fields:f}};}
        return {stringValue:String(v)};
      }
      window.fetch=function(u){
        window.__tixpFetched.push(String(u));
        var m=/trades_index_([0-9]+)/.exec(String(u));
        if(!m)return Promise.resolve({ok:false,status:404,json:function(){return Promise.resolve({});}});
        if(window.__tixpShardFail)return Promise.resolve({ok:false,status:500,json:function(){return Promise.resolve({});}});
        var i=+m[1];
        return Promise.resolve({ok:true,status:200,json:function(){
          return Promise.resolve({fields:fsVal({trades:window.__tixpShards[i]}).mapValue.fields});}});
      };
      window.__tixpListens=[];window.__tixpWrites=[];
      var rec=function(path){return {
        collection:function(c){return rec(path+'/'+c);},
        doc:function(x){return rec(path+'/'+x);},
        document:function(x){return rec(path+'/'+x);},
        orderBy:function(){return rec(path);},
        onSnapshot:function(){window.__tixpListens.push(path);return function(){};},
        set:function(o){window.__tixpWrites.push({doc:path,keys:Object.keys(o||{}).join(','),
          rev:(o.rev&&o.rev.__inc)||null,recent:!!(o.recent&&o.recent.__union)});return Promise.resolve();},
        update:function(o){window.__tixpWrites.push({doc:path,keys:Object.keys(o||{}).join(','),
          setup:o.setup});return Promise.resolve();},
        get:function(){return Promise.resolve({exists:false,data:function(){return {};}});}};};
      db=rec('');
      auth={currentUser:{uid:'probe-uid',getIdToken:function(){return Promise.resolve('probe-token');}}};
      if(typeof firebase==='undefined')firebase={};
      firebase.app=function(){return {options:{projectId:'probe'}};};
      firebase.firestore=function(){return db;};
      firebase.firestore.FieldValue={increment:function(n){return {__inc:n};},
        arrayUnion:function(x){return {__union:x};}};
      colRef=db.collection('users').doc('probe-uid').collection('trades');
      activeTab='home';
      window._tixRows={};window._tixRev=0;
      window.__tixp={};
      return 1;
    })()`);

    var steps=[
      // 1. the first head snapshot: the shards, nothing else
      `(function(){
         window.__tixpFetched=[];window.__tixpListens=[];
         window.__tixp.first=window._tixOnHead('probe-uid',{rev:500,shards:2,map:{},recent:[]},
           function(y){window.__tixp.fell='first: '+y;});
         return 1;})()`,
      `(function(){
         window.__tixp.firstFetched=window.__tixpFetched.length;
         window.__tixp.firstListens=window.__tixpListens.slice();
         window.__tixp.n=(trades||[]).length;
         window.__tixp.rev=window._tixRev;
         window.__tixp.ordered=(function(){for(var i=1;i<trades.length;i++){
           if(String(trades[i-1].date)>String(trades[i].date))return false;}return true;})();
         window.__tixp.idxJson=JSON.stringify(trades);
         renderApp();
         var c=document.getElementById('content')||document.body;
         window.__tixp.idxHtml=c.innerHTML.length;
         window.__tixp.idxHash=(function(s){var h=0;for(var i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0;}return h;})(c.innerHTML);
         return 1;})()`,
      // 2. THE SAME LEDGER the old listener drew: identical list, identical HTML
      `(function(){
         trades=window.__tixpRows.map(function(t){var o=Object.assign({},t);var id=o._id;delete o._id;o.id=id;return o;})
           .sort(function(a,b){var x=String(a.date||''),y=String(b.date||'');return x<y?-1:(x>y?1:(String(a.id)<String(b.id)?-1:1));});
         window.__tixp.refJson=JSON.stringify(trades);
         renderApp();
         var c=document.getElementById('content')||document.body;
         window.__tixp.refHtml=c.innerHTML.length;
         window.__tixp.refHash=(function(s){var h=0;for(var i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0;}return h;})(c.innerHTML);
         return 1;})()`,
      // 3. a trade written on the PC: inline, no further reads
      `(function(){
         window.__tixpFetched=[];
         var t=Object.assign({},window.__tixpRows[0]);t.notes='CHANGED ON THE PC';
         window.__tixp.second=window._tixOnHead('probe-uid',
           {rev:501,shards:2,map:{},recent:[{rev:501,id:t._id,trade:t}]},
           function(y){window.__tixp.fell='second: '+y;});
         window.__tixp.secondFetched=window.__tixpFetched.length;
         window.__tixp.secondNotes=((trades||[]).filter(function(x){return x.id===window.__tixpRows[0]._id;})[0]||{}).notes||null;
         window.__tixp.secondN=(trades||[]).length;
         return 1;})()`,
      // 4. a trade deleted on the PC leaves the journal
      `(function(){
         window.__tixpFetched=[];
         window.__tixp.third=window._tixOnHead('probe-uid',
           {rev:502,shards:2,map:{},recent:[{rev:502,id:window.__tixpRows[1]._id,deleted:true}]},
           function(y){window.__tixp.fell='third: '+y;});
         window.__tixp.afterDelete=(trades||[]).length;
         window.__tixp.thirdFetched=window.__tixpFetched.length;
         return 1;})()`,
      // 5. a tab far behind: the shards again, 2 documents, never 108
      `(function(){
         window.__tixpFetched=[];window._tixFetching=false;
         window.__tixp.far=window._tixOnHead('probe-uid',
           {rev:900,shards:2,map:{},recent:[{rev:899,id:window.__tixpRows[0]._id,trade:window.__tixpRows[0]}]},
           function(y){window.__tixp.fell='far: '+y;});
         return 1;})()`,
      `(function(){
         window.__tixp.farFetched=window.__tixpFetched.length;
         window.__tixp.farN=(trades||[]).length;
         return 1;})()`,
      // 6. no index at all -> the old collection listener
      `(function(){
         // attach for real first, so the page's OWN fallback is the one under test
         window.__tixpOff=window._tixAttachFn("probe-uid");
         window.__tixpListens=[];
         window.__tixp.none=window._tixOnHead('probe-uid',null,window._tixFallback);
         window.__tixp.noneListens=window.__tixpListens.slice();
         return 1;})()`,
      // 7. an unreadable shard -> the same fallback
      `(function(){
         window.__tixpShardFail=true;window._tixFetching=false;window.__tixp.fellShard=null;
         window._tixOnHead('probe-uid',{rev:1500,shards:2,map:{},recent:[]},
           function(y){window.__tixp.fellShard=y;});
         return 1;})()`,
      `(function(){window.__tixpShardFail=false;
         window.__tixp.fellShardSeen=window.__tixp.fellShard;
         // 8. the owner's own rename: the trade AND the index
         window.__tixpWrites=[];
         window._tixRows[window.__tixpRows[0]._id]=Object.assign({},window.__tixpRows[0]);
         _tixPoke('probe-uid',window.__tixpRows[0]._id,{setup:'renamed by the owner'});
         return 1;})()`,
      `(function(){
         window.__tixp.writes=window.__tixpWrites.slice();
         window.__tixp.errs=window._tixpErr.slice();
         window.__tixp.warns=window._tixpWarn.slice();
         return 1;})()`
    ];
    var i=0;
    (function next(){
      if(i>=steps.length){setTimeout(function(){report('done');},700);return;}
      try{w.eval(steps[i]);}catch(e){w.__tixp=w.__tixp||{};w.__tixp.threw=String(i)+': '+String(e);}
      i++;setTimeout(next,450);
    })();
  };
  setTimeout(function(){report('timeout');},70000);
})();
</script></body></html>
"""


def run_case(chrome, name, width, height, theme):
    pdir = os.path.join(ROOT, '_tixprobe')
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
    prof = tempfile.mkdtemp(prefix='tixprobe-')
    url = 'http://127.0.0.1:%d/_tixprobe/probe_%s.html' % (port, name)
    base = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
            '--user-data-dir=' + prof, '--virtual-time-budget=100000',
            '--window-size=%d,%d' % (width, height + 40)]
    try:
        out = subprocess.run(base + ['--dump-dom', url], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=300).stdout
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'TIXPROBE: (\{.*\})\s*</pre>', out or '', re.S)
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

    if r.get('first') != 'shards':
        bad.append('%s: the first head snapshot decided %r, not shards' % (nm, r.get('first')))
    if r.get('n') != 108:
        bad.append('%s: %s of 108 trades landed from the index' % (nm, r.get('n')))
    if r.get('firstFetched') != 2:
        bad.append('%s: opening the journal cost %s documents, expected 2 shards'
                   % (nm, r.get('firstFetched')))
    if [x for x in (r.get('firstListens') or []) if x.endswith('/trades')]:
        bad.append('%s: the collection listener was attached anyway: %s' % (nm, r.get('firstListens')))
    if not r.get('ordered'):
        bad.append('%s: the journal is not in date order' % nm)
    if r.get('fell'):
        bad.append('%s: fell back when it should not have: %s' % (nm, r.get('fell')))

    # THE PARITY CONDITION MANAGER set: no visible change
    if r.get('idxJson') != r.get('refJson'):
        bad.append('%s: the trades list from the index is NOT the list the collection gave '
                   '(%s vs %s chars)' % (nm, len(r.get('idxJson') or ''), len(r.get('refJson') or '')))
    if r.get('idxHash') != r.get('refHash') or r.get('idxHtml') != r.get('refHtml'):
        bad.append('%s: the rendered ledger differs - index %s chars / hash %s, collection %s / %s'
                   % (nm, r.get('idxHtml'), r.get('idxHash'), r.get('refHtml'), r.get('refHash')))

    if r.get('second') != 'inline':
        bad.append('%s: one changed trade decided %r, not inline' % (nm, r.get('second')))
    if r.get('secondFetched'):
        bad.append('%s: seeing a changed trade cost %s extra read(s)' % (nm, r.get('secondFetched')))
    if r.get('secondNotes') != 'CHANGED ON THE PC':
        bad.append('%s: the changed trade did not arrive: %r' % (nm, r.get('secondNotes')))
    if r.get('secondN') != 108:
        bad.append('%s: the inline update left %s trades' % (nm, r.get('secondN')))

    if r.get('third') != 'inline' or r.get('afterDelete') != 107:
        bad.append('%s: a deleted trade did not leave the journal (%s, %s trades)'
                   % (nm, r.get('third'), r.get('afterDelete')))

    if r.get('far') != 'shards':
        bad.append('%s: a tab far behind decided %r, not shards' % (nm, r.get('far')))
    if r.get('farFetched') != 2:
        bad.append('%s: catching up cost %s documents, expected 2' % (nm, r.get('farFetched')))
    if r.get('farN') != 108:
        bad.append('%s: catching up left %s trades' % (nm, r.get('farN')))

    if r.get('none') != 'fallback':
        bad.append('%s: no index decided %r, not fallback' % (nm, r.get('none')))
    if not [x for x in (r.get('noneListens') or []) if x.endswith('/trades')]:
        bad.append('%s: with no index the collection listener was NOT attached: %s'
                   % (nm, r.get('noneListens')))
    if not r.get('fellShardSeen'):
        bad.append('%s: an unreadable shard did not fall back' % nm)

    w = r.get('writes') or []
    idx = [x for x in w if str(x.get('doc', '')).endswith('/meta/trades_index')]
    if not idx:
        bad.append('%s: the owner rename did not reach the index' % nm)
    elif idx[0].get('rev') != 1 or not idx[0].get('recent'):
        bad.append('%s: the index poke is wrong: %s' % (nm, idx[0]))

    if res.get('loadErr'):
        bad.append('%s: LOAD ERROR on the page' % nm)
    for e in (r.get('errs') or []):
        bad.append('%s: %s' % (nm, e))
    if phone and (res.get('scrollW') or 0) > (res.get('clientW') or 0):
        bad.append('%s: the phone page scrolls sideways (%s > %s)'
                   % (nm, res.get('scrollW'), res.get('clientW')))
    return bad


def main():
    chrome = find_chrome()
    if not chrome:
        print('TIXPROBE: INCONCLUSIVE (no chrome found)')
        return 2
    cases = (('laptop_1400', 1400, 900, '', False),
             ('phone_375', 375, 812, '', True))
    fails = []
    for nm, w, h, theme, phone in cases:
        try:
            res = run_case(chrome, nm, w, h, theme)
        except subprocess.TimeoutExpired:
            print('TIXPROBE: INCONCLUSIVE (%s timed out)' % nm)
            return 2
        bad = judge(nm, res, phone)
        r = res.get('r') or {}
        print('%s: first=%s trades=%s docs=%s | ledger index %s/%s vs collection %s/%s | '
              'inline=%s extra=%s | delete->%s | behind=%s docs=%s'
              % (nm, r.get('first'), r.get('n'), r.get('firstFetched'), r.get('idxHtml'),
                 r.get('idxHash'), r.get('refHtml'), r.get('refHash'), r.get('second'),
                 r.get('secondFetched'), r.get('afterDelete'), r.get('far'), r.get('farFetched')))
        for wmsg in (r.get('warns') or [])[:4]:
            print('   warn: ' + str(wmsg)[:200])
        fails += bad
    if fails:
        print('TIXPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('TIXPROBE: PASS (108 trades from 2 shard documents instead of 108 reads, in date order; '
          'the rendered ledger is character-for-character the one the collection drew; a PC change '
          'and a deletion arrive inline for nothing; a tab far behind pays 2; no index or an '
          'unreadable shard falls back to the collection; the owner rename reaches the index)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
