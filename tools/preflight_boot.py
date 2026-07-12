#!/usr/bin/env python3
"""
tools/preflight_boot.py -- pre-push "boot gate" for EDGE-LOG's index.html.

Boots index.html in headless Chrome (via a same-origin iframe probe) and checks
that the app actually rendered -- VERSION present, renderApp defined, no
loadError, real body content -- rather than white-screening. Also runs a tight
static lint for the malformed-template-tag bug that shipped in v53.3 (an
opening HTML tag missing its closing ">" immediately followed by a "${...}"
template-interpolation line).

Exit codes:
  0 = PASS          index.html boots cleanly.
  1 = FAIL          definitely broken -- should block the push.
  2 = INCONCLUSIVE  tooling could not run (chrome missing, timeout, etc) --
                     should NOT block the push.

Usage:
  python tools/preflight_boot.py                  # checks the real index.html
  python tools/preflight_boot.py --file some.html  # checks an arbitrary file
                                                     # as if it were index.html
                                                     # (used for self-tests)

Dependency-free: Python stdlib only, plus a subprocess call to local Chrome.
Robust to being run from any cwd.

Implementation note: index.html declares `const VERSION=...` at the top level
of a classic (non-module) <script>. Top-level let/const/class bindings in a
classic script do NOT become properties of `window` (only `var` and function
declarations do) -- so reading VERSION from a parent frame via
`iframe.contentWindow.VERSION` always yields undefined, even on a healthy
boot. This was verified empirically against this repo's own index.html served
same-origin. To read VERSION reliably we instead use an indirect eval
(`w.eval('...')`) inside the probe page, which runs in the iframe's own
global scope and CAN see its top-level lexical bindings. renderApp is a
function DECLARATION so it is already exposed on window directly (function
declarations at top level of a classic script do become window properties).
"""
import argparse
import html as _html
import http.server
import json
import os
import re
import subprocess
import sys
import threading

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

PROBE_FILENAME = '_boot_probe.html'


def find_repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_chrome():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        candidates.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


# High-precision malformed-tag lint (v53.3 bug class): a line that opens an
# HTML tag and ends with a quoted attribute but NEVER closes with ">", whose
# next non-empty line starts a "${...}" template-interpolation content block.
# Multi-line tags that continue with MORE attributes on the next line must NOT
# trip this -- only a following "${" content line does.
MALFORMED_TAG_RE = re.compile(r'^\s*<\w[^>]*"\s*$')


def lint_malformed_template_tags(path):
    """Return a list of (line_no, text) hits, or None if the file could not be read."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    hits = []
    n = len(lines)
    for i, line in enumerate(lines):
        if not MALFORMED_TAG_RE.match(line):
            continue
        j = i + 1
        while j < n and lines[j].strip() == '':
            j += 1
        if j < n and lines[j].lstrip().startswith('${'):
            hits.append((i + 1, line.strip()))
    return hits


def make_handler(root_dir, alt_index):
    """Serve root_dir statically; if alt_index is set, /index.html is served
    from that path instead (used to validate an arbitrary file as if it were
    the real index.html, without ever touching the real one)."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root_dir, **kw)

        def do_GET(self):
            if alt_index and (self.path == '/index.html' or self.path.startswith('/index.html?')):
                try:
                    with open(alt_index, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError as e:
                    self.send_error(500, str(e))
                return
            super().do_GET()

        def log_message(self, fmt, *args):
            pass  # quiet

    return Handler


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>boot probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1200px;height:800px;border:0"></iframe>
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
      var ver = null;
      try { ver = w.eval('typeof VERSION!=="undefined"?VERSION:null'); } catch (e2) { ver = null; }
      var obj = {
        VERSION: ver,
        renderApp: typeof w.renderApp,
        expandChart: (w.expandChart ? 'function' : 'missing'),
        loadError: w.loadError || null,
        bodyLen: (w.document.body ? w.document.body.innerHTML.length : 0)
      };
      o.textContent = 'BOOTPROBE: ' + JSON.stringify(obj);
    } catch (e) {
      o.textContent = 'BOOTPROBE: ' + JSON.stringify({err:String(e)});
    }
  }
  document.getElementById('f').addEventListener('load', function(){ setTimeout(report, 2500); });
  setTimeout(report, 8000);
})();
</script>
</body></html>
"""


def write_probe(probe_path):
    with open(probe_path, 'w', encoding='utf-8') as f:
        f.write(PROBE_HTML)


def run_server(root_dir, alt_index):
    handler_cls = make_handler(root_dir, alt_index)
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler_cls)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def dump_dom(chrome_path, url, timeout=30):
    args = [
        chrome_path, '--headless=new', '--disable-gpu', '--no-sandbox',
        '--hide-scrollbars', '--virtual-time-budget=9000',
        '--run-all-compositor-stages-before-draw', '--dump-dom', url,
    ]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, 'chrome --dump-dom timed out after %ds' % timeout
    except OSError as e:
        return None, 'failed to launch chrome: %s' % e
    return proc.stdout, None


BOOTPROBE_RE = re.compile(r'BOOTPROBE:\s*(\{.*?\})\s*</pre>', re.S)


def parse_bootprobe(stdout):
    if not stdout:
        return None
    m = BOOTPROBE_RE.search(stdout)
    if not m:
        return None
    raw = _html.unescape(m.group(1))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', default=None,
                     help='validate this file as if it were index.html (self-test use)')
    args = ap.parse_args(argv)

    repo_root = find_repo_root()
    target = os.path.abspath(args.file) if args.file else os.path.join(repo_root, 'index.html')

    if not os.path.isfile(target):
        print('PREFLIGHT: INCONCLUSIVE -- target file not found: %s' % target)
        return INCONCLUSIVE

    # ---- static lint (fast, no deps): malformed template tag bug (v53.3) ----
    lint_hits = lint_malformed_template_tags(target)
    if lint_hits is None:
        print('PREFLIGHT: INCONCLUSIVE -- could not read %s for lint' % target)
        return INCONCLUSIVE
    if lint_hits:
        lines_desc = ', '.join(str(n) for n, _ in lint_hits)
        print('PREFLIGHT: FAIL -- malformed template tag(s) at line(s) %s '
              '(opening tag missing ">" immediately followed by a "${" content line)' % lines_desc)
        for n, txt in lint_hits:
            print('  line %d: %s' % (n, txt))
        return FAIL

    # ---- headless-Chrome boot probe ----
    chrome_path = find_chrome()
    if not chrome_path:
        print('PREFLIGHT: INCONCLUSIVE -- Chrome not found (checked Program Files, '
              'Program Files (x86), %LOCALAPPDATA%)')
        return INCONCLUSIVE

    probe_path = os.path.join(repo_root, 'tools', PROBE_FILENAME)
    httpd = None
    try:
        write_probe(probe_path)
        alt_index = target if args.file else None
        httpd, port = run_server(repo_root, alt_index)
        url = 'http://127.0.0.1:%d/tools/%s' % (port, PROBE_FILENAME)
        stdout, err = dump_dom(chrome_path, url)
        if err:
            print('PREFLIGHT: INCONCLUSIVE -- %s' % err)
            return INCONCLUSIVE

        obj = parse_bootprobe(stdout)
        if obj is None:
            print('PREFLIGHT: INCONCLUSIVE -- no BOOTPROBE marker found in chrome output '
                  '(could not determine boot state)')
            return INCONCLUSIVE

        if 'err' in obj:
            print('PREFLIGHT: FAIL -- probe threw: %s' % obj.get('err'))
            print('  parsed: %s' % obj)
            return FAIL

        version = obj.get('VERSION')
        render_app = obj.get('renderApp')
        load_error = obj.get('loadError')
        body_len = obj.get('bodyLen') or 0

        if not (isinstance(version, str) and version):
            print('PREFLIGHT: FAIL -- VERSION missing/empty (app did not boot)')
            print('  parsed: %s' % obj)
            return FAIL
        if render_app != 'function':
            print('PREFLIGHT: FAIL -- renderApp is not a function (got %r)' % render_app)
            print('  parsed: %s' % obj)
            return FAIL
        if load_error:
            print('PREFLIGHT: FAIL -- loadError set: %r' % load_error)
            print('  parsed: %s' % obj)
            return FAIL
        if not (isinstance(body_len, (int, float)) and body_len > 50000):
            print('PREFLIGHT: FAIL -- bodyLen too small (%r) -- app likely white-screened' % body_len)
            print('  parsed: %s' % obj)
            return FAIL

        print('PREFLIGHT: PASS (VERSION=%s, bodyLen=%d)' % (version, int(body_len)))
        return PASS
    finally:
        if httpd:
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


if __name__ == '__main__':
    sys.exit(main())
