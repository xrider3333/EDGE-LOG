#!/usr/bin/env python3
"""Sanity check for window.candleSVG in index.html, same technique as
tools/preflight_boot.py: serve the repo root, load index.html in a same-origin
iframe via headless Chrome, then eval window.candleSVG with synthetic bars +
a vwap overlay + entry/exit markers and assert on the returned SVG string.

Extended for session-boundary handling: a MULTI-SESSION case (3 calendar days,
40 bars each, 5-min steps from 09:30) checks the dashed session-divider lines,
the 3 bold M/D axis labels, and that non-boundary labels stay HH:MM. Also
re-runs the original single-session case and empty-bars / empty-markers
regression cases."""
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import html as _html

REPO_ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>candle probe</title></head>
<body style="margin:0">
<iframe id="f" src="/index.html" style="width:1200px;height:800px;border:0"></iframe>
<pre id="o"></pre>
<script>
(function(){
  var reported = false;
  function report(){
    if (reported) return;
    reported = true;
    var o = document.getElementById('o');
    try {
      var w = document.getElementById('f').contentWindow;
      var result = {};

      // ---- helper: count dashed session-divider <line> elements ----
      function countDividers(svgStr){
        var m = svgStr.match(/<line[^>]*stroke-dasharray="2,3"[^>]*\\/>/g);
        return m ? m.length : 0;
      }
      // ---- helper: extract bold (font-weight=700) x-axis labels, in the
      // exact attribute order the axis-label code emits (distinguishes them
      // from the entry-glyph / exit-label text elements which also use
      // font-weight="700" but in a different attribute order / font-size) ----
      function boldAxisLabels(svgStr){
        var re = /<text x="[^"]*" y="[^"]*" text-anchor="middle" font-size="9" font-weight="700" fill="var\\(--text5\\)">([^<]*)<\\/text>/g;
        var out = [], mm;
        while ((mm = re.exec(svgStr))) out.push(mm[1]);
        return out;
      }
      function nonBoldAxisLabels(svgStr){
        var re = /<text x="[^"]*" y="[^"]*" text-anchor="middle" font-size="9" font-weight="400" fill="var\\(--text5\\)">([^<]*)<\\/text>/g;
        var out = [], mm;
        while ((mm = re.exec(svgStr))) out.push(mm[1]);
        return out;
      }

      // ================= CASE 1: MULTI-SESSION (new) =================
      var sessions = ['2025-03-13','2025-03-14','2025-03-17'];
      var barsPerSession = 40;
      var mbars = [];
      var base = 20000;
      for (var s = 0; s < sessions.length; s++){
        for (var i = 0; i < barsPerSession; i++){
          var mins = i * 5;
          var hh = 9 + Math.floor((30 + mins) / 60);
          var mm2 = (30 + mins) % 60;
          var ts = sessions[s] + ' ' + String(hh).padStart(2,'0') + ':' + String(mm2).padStart(2,'0');
          var idx = s * barsPerSession + i;
          var o0 = base + idx * 0.5;
          var c0 = o0 + (idx % 3 === 0 ? -3 : 2);
          var h0 = Math.max(o0,c0) + 2;
          var l0 = Math.min(o0,c0) - 2;
          mbars.push({t: ts, o:o0, h:h0, l:l0, c:c0, v:100+idx});
        }
      }
      var mn = mbars.length;
      // vwap overlay with a few nulls sprinkled in (start of each session + one mid-array)
      var mvwap = mbars.map(function(b,i){
        if (i === 0 || i === 1 || i === barsPerSession || i === barsPerSession*2 || i === 60) return null;
        return base + i*0.4;
      });
      // entry/exit markers inside the MIDDLE session (indices 40-79)
      var midStart = barsPerSession; // 40
      var entryIdx = midStart + 5;   // 45
      var exitIdx = midStart + 30;   // 70
      var mmarkers = {
        entryIdx: entryIdx, entryPrice: mbars[entryIdx].o, side: 'long',
        exitIdx: exitIdx, exitPrice: mbars[exitIdx].c, pnlUsd: 250,
        shadeFrom: entryIdx, shadeTo: exitIdx
      };
      var msvg = w.candleSVG(mbars, {vwap: mvwap}, mmarkers, {});
      var dividerCount = countDividers(msvg);
      var boldLabels = boldAxisLabels(msvg);
      var nonBoldLabels = nonBoldAxisLabels(msvg);
      var mdRe = /^\\d{2}\\/\\d{2}$/;
      var hmRe = /^\\d{2}:\\d{2}$/;
      result.multiSession = {
        n: mn,
        startsWithSvg: msvg.slice(0,4) === '<svg',
        dividerCount: dividerCount,
        boldLabelCount: boldLabels.length,
        boldLabelTexts: boldLabels,
        boldLabelsAllMD: boldLabels.length > 0 && boldLabels.every(function(t){return mdRe.test(t);}),
        boldLabelsExpected: JSON.stringify(boldLabels) === JSON.stringify(['03/13','03/14','03/17']),
        nonBoldLabelCount: nonBoldLabels.length,
        nonBoldLabelTexts: nonBoldLabels,
        nonBoldLabelsAllHHMM: nonBoldLabels.length > 0 && nonBoldLabels.every(function(t){return hmRe.test(t);}),
        hasVwapPath: /stroke="var\\(--purple\\)"/.test(msvg),
        vwapNullCount: mvwap.filter(function(v){return v===null;}).length,
        len: msvg.length
      };

      // ================= CASE 2: SINGLE-SESSION (original, regression) =================
      var n = 40;
      var bars = [];
      var base1 = 20000;
      for (var i2 = 0; i2 < n; i2++){
        var t = '2026-08-07T' + String(9 + Math.floor(i2/12)).padStart(2,'0') + ':' + String((i2%12)*5).padStart(2,'0') + ':00';
        var o1 = base1 + i2*0.5;
        var c1 = o1 + (i2 % 3 === 0 ? -3 : 2);
        var h1 = Math.max(o1,c1) + 2;
        var l1 = Math.min(o1,c1) - 2;
        bars.push({t:t, o:o1, h:h1, l:l1, c:c1, v:100+i2});
      }
      var vwap = bars.map(function(b,i){ return i < 3 ? null : base1 + i*0.4; });
      var overlays = {vwap: vwap};
      var markers = {entryIdx: 5, entryPrice: bars[5].o, side: 'long', exitIdx: 30, exitPrice: bars[30].c, pnlUsd: 250, shadeFrom: 5, shadeTo: 30};
      var svgStr = w.candleSVG(bars, overlays, markers, {});
      var singleDividers = countDividers(svgStr);
      var singleBold = boldAxisLabels(svgStr);
      result.singleSession = {
        candleSVGType: typeof w.candleSVG,
        startsWithSvg: svgStr.slice(0,4) === '<svg',
        len: svgStr.length,
        hasRect: /<rect[^>]*fill="var\\(--(green|red)\\)"/.test(svgStr),
        hasEntryGlyph: svgStr.indexOf('entry ' + bars[5].o.toLocaleString('en-US')) !== -1 || svgStr.indexOf('\\u25b2') !== -1,
        hasExitLabel: svgStr.indexOf('exit ') !== -1,
        hasVwapPath: /stroke="var\\(--purple\\)"/.test(svgStr),
        dividerCount: singleDividers,
        boldLabelTexts: singleBold,
        snippet: svgStr.slice(0,120)
      };
      var svg2 = w.candleSVG(bars, {}, {}, {});
      result.emptyMarkersOk = (typeof svg2 === 'string' && svg2.slice(0,4) === '<svg');
      var svg3 = w.candleSVG(bars, {ub:vwap, lb:vwap}, {}, {width:500,height:200});
      result.customOptsOk = (typeof svg3 === 'string' && svg3.slice(0,4) === '<svg');

      // ================= CASE 3: EMPTY BARS =================
      var svgEmptyBars = w.candleSVG([], {}, {}, {});
      result.emptyBars = {
        val: svgEmptyBars,
        isString: typeof svgEmptyBars === 'string',
        startsWithSvg: typeof svgEmptyBars === 'string' && svgEmptyBars.slice(0,4) === '<svg'
      };

      // ================= CASE 4: EMPTY MARKERS (explicit, standalone) =================
      var svgEmptyMarkers = w.candleSVG(bars, {vwap: vwap}, {}, {});
      result.emptyMarkersStandalone = {
        startsWithSvg: svgEmptyMarkers.slice(0,4) === '<svg',
        noEntryText: svgEmptyMarkers.indexOf('entry ') === -1,
        noExitText: svgEmptyMarkers.indexOf('exit ') === -1
      };

      o.textContent = 'CANDLEPROBE: ' + JSON.stringify(result);
    } catch (e) {
      o.textContent = 'CANDLEPROBE: ' + JSON.stringify({err:String(e), stack:String(e.stack||'')});
    }
  }
  document.getElementById('f').addEventListener('load', function(){ setTimeout(report, 2000); });
  setTimeout(report, 8000);
})();
</script>
</body></html>
"""

def make_handler(root_dir):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root_dir, **kw)
        def log_message(self, fmt, *args):
            pass
    return Handler

def main():
    probe_path = os.path.join(REPO_ROOT, '_candle_probe.html')
    with open(probe_path, 'w', encoding='utf-8') as f:
        f.write(PROBE_HTML)
    handler_cls = make_handler(REPO_ROOT)
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler_cls)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        if not os.path.isfile(CHROME):
            print("INCONCLUSIVE: Chrome not found at %s" % CHROME)
            return 2
        url = 'http://127.0.0.1:%d/_candle_probe.html' % port
        args = [
            CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
            '--hide-scrollbars', '--virtual-time-budget=9000',
            '--run-all-compositor-stages-before-draw', '--dump-dom', url,
        ]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            print("INCONCLUSIVE: chrome timed out")
            return 2
        stdout = proc.stdout
        m = re.search(r'CANDLEPROBE:\s*(\{.*?\})\s*</pre>', stdout, re.S)
        if not m:
            print("INCONCLUSIVE: no CANDLEPROBE marker found")
            print(stdout[-3000:])
            return 2
        raw = _html.unescape(m.group(1))
        obj = json.loads(raw)
        print("RESULT:", json.dumps(obj, indent=2))
        if 'err' in obj:
            print("FAIL: candleSVG threw:", obj['err'])
            return 1

        failures = []

        ms = obj.get('multiSession', {})
        if not ms.get('startsWithSvg'): failures.append('multiSession.startsWithSvg is False')
        if ms.get('dividerCount') != 2: failures.append('multiSession.dividerCount expected 2, got %r' % ms.get('dividerCount'))
        if ms.get('boldLabelCount') != 3: failures.append('multiSession.boldLabelCount expected 3, got %r (%r)' % (ms.get('boldLabelCount'), ms.get('boldLabelTexts')))
        if not ms.get('boldLabelsAllMD'): failures.append('multiSession.boldLabelsAllMD is False, texts=%r' % ms.get('boldLabelTexts'))
        if not ms.get('boldLabelsExpected'): failures.append('multiSession bold labels != [03/13,03/14,03/17], got %r' % ms.get('boldLabelTexts'))
        if not ms.get('nonBoldLabelsAllHHMM'): failures.append('multiSession.nonBoldLabelsAllHHMM is False, texts=%r' % ms.get('nonBoldLabelTexts'))
        if not ms.get('hasVwapPath'): failures.append('multiSession.hasVwapPath is False (nulls may have broken overlay path)')

        ss = obj.get('singleSession', {})
        if ss.get('candleSVGType') != 'function': failures.append('singleSession.candleSVGType != function')
        if not ss.get('startsWithSvg'): failures.append('singleSession.startsWithSvg is False')
        if not ss.get('hasRect'): failures.append('singleSession.hasRect is False')
        if not ss.get('hasExitLabel'): failures.append('singleSession.hasExitLabel is False')
        if not ss.get('hasVwapPath'): failures.append('singleSession.hasVwapPath is False')
        if ss.get('dividerCount') != 0: failures.append('singleSession.dividerCount expected 0, got %r' % ss.get('dividerCount'))

        if not obj.get('emptyMarkersOk'): failures.append('emptyMarkersOk is False')
        if not obj.get('customOptsOk'): failures.append('customOptsOk is False')

        eb = obj.get('emptyBars', {})
        if not eb.get('startsWithSvg'): failures.append('emptyBars.startsWithSvg is False, val=%r' % eb.get('val'))

        em = obj.get('emptyMarkersStandalone', {})
        if not em.get('startsWithSvg'): failures.append('emptyMarkersStandalone.startsWithSvg is False')
        if not em.get('noEntryText'): failures.append('emptyMarkersStandalone.noEntryText is False (entry text leaked with no markers)')
        if not em.get('noExitText'): failures.append('emptyMarkersStandalone.noExitText is False (exit text leaked with no markers)')

        if failures:
            print("FAIL:")
            for fmsg in failures:
                print("  -", fmsg)
            return 1
        print("PASS")
        return 0
    finally:
        try:
            httpd.shutdown(); httpd.server_close()
        except Exception:
            pass
        try:
            if os.path.isfile(probe_path):
                os.remove(probe_path)
        except OSError:
            pass

if __name__ == '__main__':
    sys.exit(main())
