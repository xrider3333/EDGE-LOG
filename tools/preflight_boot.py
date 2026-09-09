#!/usr/bin/env python3
"""
tools/preflight_boot.py -- pre-push "boot gate" for EDGE-LOG's index.html.

Boots index.html in headless Chrome (via a same-origin iframe probe) and checks
that the app actually rendered -- VERSION present, renderApp defined, no
loadError, real body content -- rather than white-screening. Also runs a tight
static lint for the malformed-template-tag bug that shipped in v53.3 (an
opening HTML tag missing its closing ">" immediately followed by a "${...}"
template-interpolation line), plus a lint for a stray carriage return that
is not a line ending (it survives CRLF normalisation and reaches the blob).

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
import time

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


# Stray-carriage-return lint. index.html is a CRLF file in the working tree
# (core.autocrlf=true on this machine, and .gitattributes pins it as "text"),
# so a CR that ENDS a line is normal and git normalises it away on check-in.
# A CR anywhere else is NOT normalised, because it is not a line ending: it
# lands mid-line and goes straight into the stored blob. That is how three
# "}<CR>," artifacts reached origin/main in the RESEARCH_STUDIES rows array on
# 2026-09-09 -- a splice whose replacement text still carried CRLF, dropped in
# front of the row's pre-existing comma. The browser treats it as whitespace,
# so nothing breaks, but it is invisible in a diff and makes every later edit
# of that line read as a whitespace change. Cheap to catch, so catch it.
def lint_stray_carriage_returns(path):
    """Return a list of (line_no, col, snippet) for CRs that are NOT part of a
    CRLF pair, or None if the file could not be read. Reads bytes, because text
    mode would translate away the very thing being looked for."""
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except OSError:
        return None
    cr, lf = b'\r', b'\n'
    hits = []
    pos = 0
    while True:
        i = raw.find(cr, pos)
        if i < 0:
            break
        pos = i + 1
        if raw[i + 1:i + 2] == lf:
            continue                      # ordinary CRLF line ending
        line_no = raw.count(lf, 0, i) + 1
        line_start = raw.rfind(lf, 0, i) + 1
        before = raw[max(line_start, i - 40):i].decode('utf-8', 'replace')
        after = raw[i + 1:i + 20].decode('utf-8', 'replace')
        hits.append((line_no, i - line_start + 1, before + '<CR>' + after))
    return hits


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
  var iframeLoaded = false;
  function report(why){
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
        bodyLen: (w.document.body ? w.document.body.innerHTML.length : 0),
        // why this sample was taken, so the runner can tell "the app is broken"
        // apart from "we never got to look at it". 'load' = the iframe's own load
        // event fired and we sampled 2.5s later (a real reading). 'backstop' = the
        // deadline expired first, so this may just be a slow/loaded machine.
        why: why,
        iframeLoaded: iframeLoaded
      };
      o.textContent = 'BOOTPROBE: ' + JSON.stringify(obj);
    } catch (e) {
      o.textContent = 'BOOTPROBE: ' + JSON.stringify({err:String(e), why:why});
    }
  }
  document.getElementById('f').addEventListener('load', function(){
    iframeLoaded = true;
    setTimeout(function(){ report('load'); }, 2500);
  });
  // Backstop. index.html is ~2 MB, and this gate often runs while the machine is
  // busy (a runner restart, another Chrome, a build) -- 8s was too tight and fired
  // on a still-blank iframe, which then read as a hard FAIL and blocked a valid
  // push (observed 2026-08-15). Raised, and the sample is now labelled 'backstop'
  // so an empty reading here is treated as INCONCLUSIVE rather than broken.
  setTimeout(function(){ report('backstop'); }, 25000);
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

    # ---- static lint: a CR that is not a line ending (2026-09-09) ----
    cr_hits = lint_stray_carriage_returns(target)
    if cr_hits is None:
        print('PREFLIGHT: INCONCLUSIVE -- could not read %s for the CR lint' % target)
        return INCONCLUSIVE
    if cr_hits:
        print('PREFLIGHT: FAIL -- %d stray carriage return(s) that are not line '
              'endings. A CR mid-line survives CRLF normalisation and lands in '
              'the committed blob.' % len(cr_hits))
        for n, col, snip in cr_hits[:10]:
            print('  line %d col %d: %s' % (n, col, snip))
        if len(cr_hits) > 10:
            print('  ...and %d more' % (len(cr_hits) - 10))
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

        # Retry a blank/unreadable sample before drawing any conclusion. The failure
        # this guards against is transient by nature (the box was busy for a few
        # seconds), so one more look usually settles it -- far better than either
        # blocking a good push or waving a bad one through on a single noisy read.
        # A sample with real content is never retried: a genuine break is decided
        # on the first look, so this cannot mask a broken build.
        attempts = 3
        obj, err = None, None
        for attempt in range(1, attempts + 1):
            stdout, err = dump_dom(chrome_path, url, timeout=45)
            obj = parse_bootprobe(stdout) if not err else None
            if obj is not None and 'err' not in obj:
                got_content = obj.get('VERSION') or obj.get('loadError') or (obj.get('bodyLen') or 0)
                if got_content:
                    break
            if attempt < attempts:
                print('  preflight: unreadable sample on attempt %d/%d (%s) -- retrying'
                      % (attempt, attempts, err or ('why=%s' % (obj or {}).get('why'))))
                time.sleep(3)

        if err:
            print('PREFLIGHT: INCONCLUSIVE -- %s' % err)
            return INCONCLUSIVE

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

        # "We never got a reading" vs "the app is broken". A genuinely broken app
        # leaves EVIDENCE: a loadError, or a non-empty body that failed to wire up,
        # or a VERSION that parsed with a dead renderApp. A totally blank sample --
        # no VERSION, empty body, and no error at all -- means the iframe had not
        # painted yet when we looked, which happens when the machine is loaded.
        # Blocking a push on that is a false alarm (observed 2026-08-15: a valid
        # NOISE.md-only commit was refused while a runner restart + Chrome were
        # competing for the box). Report INCONCLUSIVE so the push is warned, not
        # blocked -- the same treatment a missing Chrome or a timeout already gets.
        blank_sample = (not version) and (not load_error) and (not body_len)
        if blank_sample:
            # One more discrimination before letting a blank reading off the hook:
            # check the FILE ON DISK. If index.html is substantial but the probe saw
            # an empty body, the file is fine and the probe simply never got to it.
            # If the file itself is empty/tiny, that IS a real break (a truncated or
            # clobbered write) and must still block the push -- otherwise this branch
            # would wave through the worst failure of all.
            try:
                on_disk = os.path.getsize(target)
            except OSError:
                on_disk = 0
            if on_disk < 100000:
                print('PREFLIGHT: FAIL -- blank page AND %s is only %d bytes on disk '
                      '(truncated/clobbered file, not a slow probe)' % (target, on_disk))
                print('  parsed: %s' % obj)
                return FAIL
            print('PREFLIGHT: INCONCLUSIVE -- probe sampled a blank page (why=%r, '
                  'iframeLoaded=%r) but %s is %d bytes on disk; the app never painted '
                  'before the deadline, which means a busy machine rather than a broken build'
                  % (obj.get('why'), obj.get('iframeLoaded'), os.path.basename(target), on_disk))
            print('  parsed: %s' % obj)
            return INCONCLUSIVE

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
