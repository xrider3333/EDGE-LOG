#!/usr/bin/env python3
"""Render-check for the SHIPPED per-trade candle chart (d4b0c7a, docs/VISUAL_TRADE_REPORT.md
§3): same boot technique as tools/candle_probe.py (serve the repo root off a throwaway local
http.server, load index.html in a same-origin iframe under headless Chrome) but instead of
just asserting on the candleSVG() string, this drives the REAL call path end to end exactly
the way index.html's _openCandles() does it — build the same `markers` shape, call
window.candleSVG(bars, overlays, markers, {}), then hand the string to window.expandChart()
so the real modal chrome (title/sub/close button/crosshair scaffolding) gets exercised too —
and captures an actual PNG screenshot so a human can eyeball it, plus reads render stats
(candle body count, session-divider count, axis labels, entry/exit marker text) back out of
the live DOM so the picture comes with numbers attached.

Usage:
    python tools/candle_render_check.py [bars.json] [--out shot.png]

`bars.json` defaults to the real load_session_bars() output already pulled for run200 NQ 5m
trade #3654 (see TRADE below for that same trade's blotter-row fields — entry/exit price,
side, pnl — which is the OTHER half _openCandles combines with the bars endpoint response to
build `markers`; the bars payload itself carries no price/side/pnl, only OHLCV + entry/exit
index).

Screenshot route: DevTools Page.captureScreenshot over a live CDP websocket (`websockets`
package) — the browser is driven in real time, polling the page for a completion flag the
injected script sets only after expandChart's modal has actually painted (two rAFs + a short
settle), so there is no virtual-time-budget guessing about whether the async work finished.
Falls back to the plain `chrome --headless --screenshot=` CLI flag (same one-shot-automation
technique as --dump-dom in candle_probe.py / preflight_boot.py) only if the CDP route can't
get off the ground at all (e.g. `websockets` not installed, Chrome won't open a debug port).
If NEITHER route produces a real PNG, this says so plainly and exits non-zero — it never
fabricates a screenshot path that doesn't exist.
"""
import argparse
import asyncio
import base64
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

# Windows console default codepage (cp1252) chokes on the arrow / middot glyphs this
# script prints (chart-sub line mirrors index.html's own unicode punctuation) — widen
# stdout/stderr to utf-8 so a print never crashes AFTER the screenshot already succeeded.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCRATCHPAD = (r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop"
              r"\377e32ce-c40c-4d0a-a804-d850a5bfa7e7\scratchpad")
DEFAULT_BARS = os.path.join(SCRATCHPAD, "real_bars.json")
DEFAULT_OUT = os.path.join(SCRATCHPAD, "candle_render_check.png")

VIEWPORT_W, VIEWPORT_H = 1400, 900

# The real trade real_bars.json belongs to (run200 NQ 5m #3654) — these are the blotter-row
# fields (index.html's x._ep/x._xp/x._side/x._usd/x._no) that _openCandles() combines with
# the bars-endpoint response (r.entry_idx/r.exit_idx) to build `markers`. Hardcoded here
# because real_bars.json (the `r` half) doesn't carry price/side/pnl at all.
TRADE = {
    "no": 3654, "side": "short",
    "entry_price": 17919.5, "entry_time": "2025-04-08 12:30",
    "exit_price": 17239.5, "exit_time": "2025-04-08 15:55",
    "pnl_usd": 13159.34,
}

# ── outer probe page: iframe-loads index.html (same-origin, off the local http.server),
# waits for it to boot, then drives the real _openCandles() call path against the injected
# real bars + trade, then reads the rendered DOM back out. Completion is signalled BOTH via
# window.__PROBE_DONE__/__PROBE_RESULT__ (polled live by the CDP route) AND via the
# <pre id="o"> CANDLEPROBE: marker candle_probe.py uses (read by the --dump-dom CLI fallback)
# so one template serves both routes. ──
PROBE_HTML_TMPL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>candle render check</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="/index.html" style="width:__VIEWPORT_W__px;height:__VIEWPORT_H__px;border:0;display:block"></iframe>
<pre id="o" style="display:none"></pre>
<script>
window.__REAL_BARS__ = __REAL_BARS_JSON__;
window.__TRADE__ = __TRADE_JSON__;
window.__PROBE_DONE__ = false;
window.__PROBE_RESULT__ = null;
(function(){
  function finish(result){
    window.__PROBE_RESULT__ = result;
    window.__PROBE_DONE__ = true;
    var o = document.getElementById('o');
    if (o) o.textContent = 'CANDLEPROBE: ' + JSON.stringify(result);
  }
  function run(){
    if (window.__PROBE_DONE__) return;
    try {
      var w = document.getElementById('f').contentWindow;
      if (typeof w.candleSVG !== 'function' || typeof w.expandChart !== 'function') {
        finish({ok:false, err:'candleSVG/expandChart missing on index.html window (typeof candleSVG=' +
          typeof w.candleSVG + ', typeof expandChart=' + typeof w.expandChart + ')'});
        return;
      }
      var data = window.__REAL_BARS__;
      var trade = window.__TRADE__;
      if (!data || data.ok !== true || !data.bars || !data.bars.length) {
        finish({ok:false, err:'bars payload is not a usable {ok:true, bars:[...]} shape'});
        return;
      }
      var bars = data.bars;
      var overlays = data.overlays || {};

      // ---- exact markers shape index.html's _openCandles() builds ----
      var hasEntry = (data.entry_idx !== undefined && data.entry_idx !== null);
      var hasExit = (data.exit_idx !== undefined && data.exit_idx !== null);
      var markers = {
        entryIdx: hasEntry ? data.entry_idx : undefined, entryPrice: trade.entry_price, side: trade.side,
        exitIdx: hasExit ? data.exit_idx : undefined, exitPrice: trade.exit_price, pnlUsd: trade.pnl_usd
      };
      if (hasEntry && hasExit) { markers.shadeFrom = data.entry_idx; markers.shadeTo = data.exit_idx; }

      var svgStr = w.candleSVG(bars, overlays, markers, {});
      if (typeof svgStr !== 'string' || svgStr.indexOf('<svg') !== 0) {
        finish({ok:false, err:'candleSVG() did not return an <svg string: ' + String(svgStr).slice(0,200)});
        return;
      }

      var fmtUsd = function(v){ return (v<0?'-$':'$') + Math.abs(Math.round(v)).toLocaleString(); };
      var meta = data.meta || {};
      var sub = 'entry ' + trade.entry_time + ' &rarr; exit ' + trade.exit_time + ' &middot; ' +
        (trade.side === 'long' ? 'LONG' : 'SHORT') + ' &middot; net ' + fmtUsd(trade.pnl_usd) +
        (meta.master ? (' &middot; master: ' + meta.master) : '');

      // ---- the real modal chrome, not just the raw SVG ----
      w.expandChart('TRADE #' + trade.no + ' \\u00b7 CANDLES', svgStr, {sub: sub});

      // two rAFs (guarantee at least one real layout+paint cycle) + a short real-time settle
      // before reading the DOM back / letting the CDP side screenshot.
      requestAnimationFrame(function(){
        requestAnimationFrame(function(){
          setTimeout(function(){
            try {
              var doc = w.document;
              var modalBody = doc.querySelector('#chart-body');
              var svgEl = modalBody ? modalBody.querySelector('svg') : null;
              if (!svgEl) { finish({ok:false, err:'no <svg> inside #chart-body after expandChart()'}); return; }
              var allRects = Array.prototype.slice.call(svgEl.querySelectorAll('rect'));
              var candleRects = allRects.filter(function(r){
                var f = r.getAttribute('fill');
                return f === 'var(--green)' || f === 'var(--red)';
              });
              var allLines = Array.prototype.slice.call(svgEl.querySelectorAll('line'));
              var dividers = allLines.filter(function(l){ return l.getAttribute('stroke-dasharray') === '2,3'; });
              var allTexts = Array.prototype.slice.call(svgEl.querySelectorAll('text'));
              var axisLabels = allTexts.filter(function(t){
                return t.getAttribute('font-size') === '9' && t.getAttribute('text-anchor') === 'middle' &&
                  t.getAttribute('fill') === 'var(--text5)';
              }).map(function(t){ return t.textContent; });
              var entryLabel = null, exitLabel = null;
              allTexts.forEach(function(t){
                var tc = t.textContent || '';
                if (tc.indexOf('entry ') === 0) entryLabel = tc;
                if (tc.indexOf('exit ') === 0) exitLabel = tc;
              });
              finish({
                ok: true,
                barCount: bars.length,
                svgLen: svgStr.length,
                rectTotal: allRects.length,
                candleRectCount: candleRects.length,
                dividerCount: dividers.length,
                axisLabelCount: axisLabels.length,
                axisLabels: axisLabels,
                entryLabel: entryLabel,
                exitLabel: exitLabel,
                chartTitle: (doc.querySelector('#chart-body') && doc.body.textContent.indexOf('TRADE #3654') !== -1),
                chartSub: (doc.getElementById('chart-sub') || {}).textContent || null
              });
            } catch (eInner) {
              finish({ok:false, err:String(eInner), stack:String(eInner.stack||'')});
            }
          }, 150);
        });
      });
    } catch (e) {
      finish({ok:false, err:String(e), stack:String(e.stack||'')});
    }
  }
  document.getElementById('f').addEventListener('load', function(){ setTimeout(run, 2000); });
  setTimeout(run, 8000);
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


def _build_probe_html(bars_payload):
    real_bars_json = json.dumps(bars_payload).replace('</', '<\\/')
    trade_json = json.dumps(TRADE).replace('</', '<\\/')
    html = PROBE_HTML_TMPL
    html = html.replace('__REAL_BARS_JSON__', real_bars_json)
    html = html.replace('__TRADE_JSON__', trade_json)
    html = html.replace('__VIEWPORT_W__', str(VIEWPORT_W))
    html = html.replace('__VIEWPORT_H__', str(VIEWPORT_H))
    return html


# ═══════════════════════════ CDP route (primary) ═══════════════════════════
async def _cdp_screenshot(url, out_png):
    """Drive headless Chrome over the DevTools protocol in real time: open the probe
    page in a fresh tab, poll it for window.__PROBE_DONE__, pull __PROBE_RESULT__, then
    Page.captureScreenshot. Returns (result_dict, png_bytes). Raises on any tooling
    failure (Chrome not found / no debug port / websocket error / timeout) — callers
    fall back to the CLI route on exception, they don't swallow it here."""
    import websockets  # deferred import: caller catches ImportError and falls back

    if not os.path.isfile(CHROME):
        raise RuntimeError("Chrome not found at %s" % CHROME)

    args = [
        CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--window-size=%d,%d" % (VIEWPORT_W, VIEWPORT_H),
        "--remote-debugging-port=0",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    stderr_lines = []
    lock = threading.Lock()

    def _drain():
        try:
            for line in proc.stderr:
                with lock:
                    stderr_lines.append(line)
        except Exception:
            pass

    threading.Thread(target=_drain, daemon=True).start()

    ws_url = None
    deadline = time.time() + 10
    while time.time() < deadline and ws_url is None:
        with lock:
            for line in stderr_lines:
                m = re.search(r"DevTools listening on (ws://\S+)", line)
                if m:
                    ws_url = m.group(1)
                    break
        if ws_url is None:
            await asyncio.sleep(0.05)

    try:
        if not ws_url:
            with lock:
                tail = "".join(stderr_lines[-20:])
            raise RuntimeError("Chrome never printed a DevTools ws URL within 10s; stderr tail:\n%s" % tail)

        port = re.search(r":(\d+)/", ws_url).group(1)
        api = "http://127.0.0.1:%s/json/new?%s" % (port, url)
        req = urllib.request.Request(api, method="PUT")  # newer Chrome requires PUT, not GET
        with urllib.request.urlopen(req, timeout=10) as resp:
            tab = json.loads(resp.read().decode("utf-8"))
        tab_ws = tab["webSocketDebuggerUrl"]

        async with websockets.connect(tab_ws, max_size=None) as ws:
            _id = 0

            async def send(method, params=None):
                nonlocal _id
                _id += 1
                mid = _id
                await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    if data.get("id") == mid:
                        if "error" in data:
                            raise RuntimeError("%s failed: %s" % (method, data["error"]))
                        return data.get("result", {})

            await send("Page.enable")
            await send("Runtime.enable")
            # belt-and-suspenders on top of --window-size, per Puppeteer-style practice
            await send("Emulation.setDeviceMetricsOverride",
                        {"width": VIEWPORT_W, "height": VIEWPORT_H, "deviceScaleFactor": 1, "mobile": False})

            result = None
            deadline2 = time.time() + 25
            while time.time() < deadline2:
                r = await send("Runtime.evaluate",
                                {"expression": "window.__PROBE_DONE__ === true", "returnByValue": True})
                if r.get("result", {}).get("value") is True:
                    rr = await send("Runtime.evaluate",
                                     {"expression": "JSON.stringify(window.__PROBE_RESULT__)", "returnByValue": True})
                    result = json.loads(rr["result"]["value"])
                    break
                await asyncio.sleep(0.25)
            if result is None:
                raise RuntimeError("timed out waiting for window.__PROBE_DONE__ (25s) — page may be stuck booting")

            shot = await send("Page.captureScreenshot", {"format": "png"})
            png_bytes = base64.b64decode(shot["data"])
            with open(out_png, "wb") as f:
                f.write(png_bytes)
            return result, png_bytes
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# ═══════════════════════════ CLI route (fallback only) ═══════════════════════════
def _cli_fallback(url, out_png):
    """chrome --headless --screenshot=, same one-shot-automation technique as
    candle_probe.py's --dump-dom, just capturing pixels instead of (or in addition to)
    markup. Two invocations of the SAME deterministic page: one --dump-dom (to pull the
    CANDLEPROBE: marker out of <pre id="o"> for the stats), one --screenshot (for the
    PNG). Used only if the CDP route couldn't run at all."""
    common = [
        CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--window-size=%d,%d" % (VIEWPORT_W, VIEWPORT_H),
        "--virtual-time-budget=9000", "--run-all-compositor-stages-before-draw",
    ]
    dom_args = common + ["--dump-dom", url]
    proc = subprocess.run(dom_args, capture_output=True, text=True, timeout=30)
    m = re.search(r"CANDLEPROBE:\s*(\{.*?\})\s*</pre>", proc.stdout, re.S)
    if not m:
        raise RuntimeError("--dump-dom produced no CANDLEPROBE marker; stdout tail:\n%s" % proc.stdout[-2000:])
    import html as _html
    result = json.loads(_html.unescape(m.group(1)))

    shot_args = common + ["--screenshot=%s" % out_png, url]
    proc2 = subprocess.run(shot_args, capture_output=True, text=True, timeout=30)
    if not os.path.isfile(out_png) or os.path.getsize(out_png) == 0:
        raise RuntimeError("--screenshot did not produce a PNG at %s; stderr tail:\n%s" %
                            (out_png, (proc2.stderr or "")[-2000:]))
    with open(out_png, "rb") as f:
        png_bytes = f.read()
    return result, png_bytes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bars", nargs="?", default=DEFAULT_BARS, help="path to a load_session_bars()-shaped JSON file")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output PNG path")
    args = ap.parse_args()

    bars_path = os.path.abspath(args.bars)
    out_png = os.path.abspath(args.out)

    if not os.path.isfile(bars_path):
        print("INCONCLUSIVE: bars file not found: %s" % bars_path)
        return 2
    with open(bars_path, "r", encoding="utf-8") as f:
        bars_payload = json.load(f)
    if not isinstance(bars_payload, dict) or bars_payload.get("ok") is not True or not bars_payload.get("bars"):
        print("FAIL: %s is not a usable {ok:true, bars:[...]} payload" % bars_path)
        return 1
    print("loaded %d bars from %s (sessions %s, entry_idx=%s, exit_idx=%s)" % (
        len(bars_payload["bars"]), bars_path,
        (bars_payload.get("meta") or {}).get("sessions"),
        bars_payload.get("entry_idx"), bars_payload.get("exit_idx")))

    probe_path = os.path.join(REPO_ROOT, "_candle_render_check.html")
    with open(probe_path, "w", encoding="utf-8") as f:
        f.write(_build_probe_html(bars_payload))

    handler_cls = make_handler(REPO_ROOT)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    result = None
    png_bytes = None
    route_used = None
    errors = []
    try:
        if not os.path.isfile(CHROME):
            print("INCONCLUSIVE: Chrome not found at %s" % CHROME)
            return 2

        url = "http://127.0.0.1:%d/_candle_render_check.html" % port

        try:
            result, png_bytes = asyncio.run(_cdp_screenshot(url, out_png))
            route_used = "cdp (Page.captureScreenshot over DevTools websocket)"
        except Exception as e:
            errors.append("CDP route failed: %s" % e)
            print("CDP route failed (%s) -- falling back to chrome --headless --screenshot=" % e)
            try:
                result, png_bytes = _cli_fallback(url, out_png)
                route_used = "cli fallback (chrome --headless --screenshot=)"
            except Exception as e2:
                errors.append("CLI fallback also failed: %s" % e2)

        if result is None or png_bytes is None:
            print("FAIL: could not produce a real screenshot by any route.")
            for e in errors:
                print("  -", e)
            return 1

        print("\nscreenshot route:", route_used)
        print("PNG saved to:", out_png, "(%d bytes)" % len(png_bytes))
        print("\nRESULT:", json.dumps(result, indent=2))

        if not result.get("ok"):
            print("\nFAIL: page-side render threw:", result.get("err"))
            if result.get("stack"):
                print(result["stack"])
            return 1

        print("\n-- numbers alongside the picture --")
        print("candle body <rect> count :", result.get("candleRectCount"), "(expected == barCount == %s)" % result.get("barCount"))
        print("dashed session dividers  :", result.get("dividerCount"))
        print("x-axis label texts       :", result.get("axisLabels"))
        print("entry marker label       :", result.get("entryLabel"))
        print("exit marker label        :", result.get("exitLabel"))
        print("chart-sub line           :", result.get("chartSub"))
        print("modal title present      :", result.get("chartTitle"))

        print("\nPASS" if route_used.startswith("cdp") else "\nPASS (via CLI fallback)")
        return 0
    finally:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass
        try:
            if os.path.isfile(probe_path):
                os.remove(probe_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
