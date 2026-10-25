"""local_llm.py -- run the LOCAL model (Ollama / qwen3.8:27b) as a triage assistant.

WHY THIS EXISTS (owner 2026-09-05): "in order to save tokens and run longer backtests,
consider use ollama qwen ... to help allocate more robust/longer testing, while you stay
the supervisor."

WHAT IT DOES AND DOES NOT DO -- read this before reaching for it
---------------------------------------------------------------
A local model CANNOT make a backtest faster. Backtests here are numpy/pandas over master
bars; the engine is the bottleneck, not a language model. Long runs are already free of
model cost -- they run as background python and consume no tokens at all.

What a local model CAN do is keep large RESULT FILES out of the supervising model's
context. A 300-row sweep CSV costs thousands of tokens to read directly; this tool reads
it locally, computes the numbers in pandas, and asks qwen only for a short qualitative
read. The supervisor then sees ~15 lines instead of 300 rows.

THE HARD RULE, enforced by the output format: **PYTHON COMPUTES, THE MODEL COMMENTS.**
Every number printed under DETERMINISTIC comes from pandas and can be quoted. Everything
under MODEL is a 17 GB local model's opinion, is not verified, and must never reach a doc,
a bookmark, a board row or the owner as fact without being re-derived. The model is shown
the numbers; it is not asked to produce them.

MEASURED ON THIS MACHINE 2026-09-05 (qwen3.6:latest, 23 GB, RTX-class desktop):
  * COLD start: 3m30s to first token -- the 23 GB weights loading from disk.
  * WARM: ~26 tokens/sec, a 10-token answer in 1.5s.
  * `think:false` IS REQUIRED. qwen3.x emits a reasoning block first; with a small
    num_predict the whole budget goes to thinking and the response comes back EMPTY.
    That is exactly what happened on the first trial here (8 tokens, empty string).
  So: keep it warm (`--warm`, keep_alive), always think:false, and treat the first call
  of a session as a ~3 minute cost, not a 2 second one.

WHAT IT DID ON ITS FIRST REAL RUN (ryr_frontier.csv, 802 rows, n>=300, top 8 by R/YR)
-------------------------------------------------------------------------------------
The deterministic half printed the family ranking that matters -- best R / YR per family:
BOOK 130.0 - COMBINED 111.1 - ENGU-Q 104.4 - NOISE 84.4 - TTMSQZ 58.5 - ORB 55.8 -
NQDIP 26.1 - TTIBS 10.7 -- for about fifteen lines of supervisor context instead of 802 rows.

The model half flagged run #261 as internally inconsistent: net $19,684,006 against a
$1,121,804 drawdown. **The flag was right and its explanation was wrong.** It guessed "data
entry error"; the real cause is documented in BOOK.md section 9 -- a BOOK run's headline net
was ~20x too large (19,684,006 / 1,245,994 = 15.80 = 20 x 0.7899), fixed forward-only, so
pre-fix book runs keep the inflated field. That is this tool's rule in one example: the model
is useful for pointing at a row, useless as an authority on why. (Consequence worth knowing:
the `net` column for pre-fix BOOK rows in any mined CSV is inflated. EV R and R / YR are
ratios and are NOT affected.)

LONG READING (owner 2026-10-11: "set up your local Qwen so the chats can hand it long
reading (logs, papers) and save tokens") -- `--summarize`
-------------------------------------------------------------------------------------
Reads text files (logs, .md, .py, .csv/.json as text) and PDFs (pypdf), keeps only what
you ask for (`--tail N` last lines, `--grep-first PATTERN` matching lines +-3), REDACTS
every line that looks like a key / token / password / ntfy topic BEFORE anything is
sent, cuts the rest into chunks of ~24k tokens (char estimate), map-reduces them with
the question in view, and prints a short answer under the header
"LOCAL MODEL SUMMARY (qwen3.8, unverified - quote nothing from it as fact)".
Same rule as above: the answer tells you WHERE to look; quote the file, never the model.
tools/local_llm_mcp.py exposes the same thing to the chats as an MCP server
(local_summarize / local_status). docs/LOCAL_LLM.md has when-to-use / when-not.

CONTEXT: every call sends num_ctx = NUM_CTX (32768). Ollama reloads the weights when
num_ctx changes between calls, so ONE value for every call keeps the model warm.

USE
  python tools/local_llm.py --status
  python tools/local_llm.py --warm
  python tools/local_llm.py --ask "one sentence: what does a 101% top-10 share mean?"
  python tools/local_llm.py --csv tools/r16_results/ryr_frontier.csv --metric ryr \
      --top 12 --group famKey --ask "which families cluster at the top, and what looks odd"
  python tools/local_llm.py --summarize C:/EdgeLog/manager/ship_*.log --tail 80 \
      --ask "did it land, and if not why"
  python tools/local_llm.py --summarize paper.pdf --grep-first "lockbox|out-of-sample" \
      --ask "how did they validate" --words 150

Stdlib + pandas (CSV triage only) + pypdf (PDFs only, optional). No new dependency:
Ollama is already installed and serving on 127.0.0.1:11434.
"""
from __future__ import annotations
import argparse
import glob
import io
import json
import re
import socket
import sys
import time
import os
import urllib.error
import urllib.request

HOST = (os.environ.get("AUGUR_LOCAL_LLM_HOST") or "http://127.0.0.1:11434").rstrip("/")
# qwen3.8:27b (dense, 17 GB) replaced qwen3.6 on 2026-10-11 (owner pick after a 4-job race:
# more accurate, 3-4x slower; ~61% on the 16 GB GPU at num_ctx 32768, 52% at 65536).
MODEL = "qwen3.6:35b-a3b-coding"   # 2026-10-25 owner bench: 56 tok/s, code 18/21, reasoning 5/7 vs qwen3:14b 31 tok/s 13/21 2/7; MoE ~3B active so it stays fast 39% on CPU
KEEP_ALIVE = "30m"          # hold the weights in RAM so the next call is warm
# One context size for EVERY call (see the docstring): a 24k-token chunk + the prompt +
# the answer fits with room to spare, and the model never reloads between calls.
NUM_CTX = int(os.environ.get("AUGUR_LOCAL_LLM_CTX") or 16384)
CHUNK_TOKENS = 24000        # per map call; chars = tokens * CHARS_PER_TOKEN
CHARS_PER_TOKEN = 3.5       # conservative for logs (digits/punctuation tokenise worse than prose)
MAX_CHUNKS = 12             # refuse beyond this: on CPU a 24k chunk is minutes, not seconds
CALL_TIMEOUT = 1800         # seconds per model call: cold load (minutes) + a full chunk
WORDS = 200                 # default answer length for --summarize
GREP_CONTEXT = 3            # lines either side of a --grep-first hit


def _host_label():
    return HOST.split("://", 1)[-1]


def down_message():
    return "Ollama not reachable at %s - start Ollama" % _host_label()


class OllamaDown(RuntimeError):
    """Nothing listening at HOST (connection refused / no route)."""


class OllamaError(RuntimeError):
    """Ollama answered with an error, timed out, or returned nothing usable."""

# WHERE YOU SEE THIS BEING USED (owner 2026-09-05: "where do i see the ollama being
# used?"). It has no screen in the app and it should not have one - it is a tool the
# supervising model runs, not a feature. So it writes a plain-text LOG instead, next to
# runner.log in the same operational folder, and every single call appends one block:
# when, what was asked, how long it took, how fast it ran, and the answer verbatim.
# That is the audit trail - if a number ever traces back to this model rather than to
# pandas, this file is where you catch it.
LOG_PATH = os.environ.get("AUGUR_LOCAL_LLM_LOG") or r"C:\EdgeLog\local_llm.log"

SYSTEM = (
    "You are a research assistant for a quantitative trading log. You are given numbers "
    "that were ALREADY COMPUTED by python. Never recompute, never estimate, never invent a "
    "figure: if you cite a number, copy it exactly from the input. Answer in at most six "
    "short lines. Say 'not visible in this data' rather than guessing. No preamble, no "
    "restating of the question, no markdown headers."
)


def _http_json(path, payload=None, timeout=10):
    """GET (payload None) or POST JSON to Ollama; returns the decoded JSON reply.

    Raises OllamaDown when nothing is listening, OllamaError on a timeout / HTTP error.
    """
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        raise OllamaError("Ollama HTTP %s on %s: %s" % (e.code, path, detail))
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise OllamaError("Ollama timed out after %ds on %s (cold weights load in minutes "
                              "- run --warm / --status first)" % (timeout, path))
        raise OllamaDown(down_message())
    except (socket.timeout, TimeoutError):
        raise OllamaError("Ollama timed out after %ds on %s (cold weights load in minutes "
                          "- run --warm / --status first)" % (timeout, path))
    except (ConnectionError, OSError):
        raise OllamaDown(down_message())
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise OllamaError("Ollama returned non-JSON on %s: %r" % (path, raw[:200]))


def ping(timeout=5):
    """Ollama's version string, or raise OllamaDown. Fast: use before any long call."""
    return str(_http_json("/api/version", timeout=timeout).get("version") or "?")


def generate(prompt, system=SYSTEM, num_predict=400, timeout=CALL_TIMEOUT, model=MODEL,
             think=False, num_ctx=None):
    """One raw completion. Returns a dict: text, secs, tps (writing), prompt_tps (reading),
    prompt_tokens, eval_tokens, load_secs. Raises OllamaDown / OllamaError; an empty answer comes back as text ''."""
    payload = {
        "model": model, "prompt": prompt, "system": system, "stream": False,
        "think": think, "keep_alive": KEEP_ALIVE,
        "options": {"num_predict": int(num_predict), "temperature": 0,
                    "num_ctx": int(num_ctx or NUM_CTX)},
    }
    t0 = time.time()
    d = _http_json("/api/generate", payload, timeout=timeout)
    if d.get("error"):
        raise OllamaError("Ollama error: %s" % str(d["error"])[:300])
    ec = d.get("eval_count") or 0
    ed = (d.get("eval_duration") or 0) / 1e9
    pc = d.get("prompt_eval_count") or 0
    pd = (d.get("prompt_eval_duration") or 0) / 1e9
    return {"text": (d.get("response") or "").strip(), "secs": time.time() - t0,
            "tps": (ec / ed) if ed else 0.0, "prompt_tps": (pc / pd) if pd else 0.0,
            "prompt_tokens": pc, "eval_tokens": ec,
            "load_secs": (d.get("load_duration") or 0) / 1e9}


def ask(prompt, system=SYSTEM, num_predict=400, timeout=600, model=MODEL, think=False,
        num_ctx=None):
    """One completion from the local model. Returns (text, seconds, tokens_per_sec).

    think=False matters: see the measurement note in the module docstring.
    Never raises: an unreachable / timed-out model comes back as a bracketed message.
    """
    t0 = time.time()
    try:
        r = generate(prompt, system=system, num_predict=num_predict, timeout=timeout,
                     model=model, think=think, num_ctx=num_ctx)
    except (OllamaDown, OllamaError) as e:
        return ("[%s]" % e, time.time() - t0, 0.0)
    txt = r["text"]
    if not txt:
        txt = ("[empty response -- num_predict %d was consumed before any answer. Raise it, "
               "or check think=False.]" % num_predict)
    _log(prompt, txt, r["secs"], r["tps"], model)
    return (txt, r["secs"], r["tps"])


def _log(prompt, answer, secs, tps, model):
    """Append one block to LOG_PATH. Never raises: a logging failure must not lose an answer."""
    try:
        d = os.path.dirname(LOG_PATH)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n%s  %s  %.1fs  %.1f tok/s\n"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), model, secs, tps))
            f.write("  ASKED : %s\n" % " ".join(str(prompt).split())[:600])
            for line in str(answer).splitlines():
                f.write("  MODEL : %s\n" % line[:300])
    except Exception:
        pass


def triage_csv(path, metric, top=12, group=None, question=None, floor_col=None, floor=None):
    """Deterministic top-N in pandas, then a qualitative read from the local model."""
    import pandas as pd
    df = pd.read_csv(path)
    if metric not in df.columns:
        raise SystemExit("metric %r not in %s -- columns: %s"
                         % (metric, path, ", ".join(map(str, df.columns))[:400]))
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    if floor_col and floor is not None and floor_col in df.columns:
        df = df[pd.to_numeric(df[floor_col], errors="coerce") >= float(floor)]
    keep = [c for c in df.columns if c != "params"]      # params blobs are noise here
    tbl = df.sort_values(metric, ascending=False).head(int(top))[keep]

    print("=" * 100)
    print("DETERMINISTIC -- computed in pandas from %s; these numbers are quotable." % path)
    print("rows read %d | after filter %d | top %d by %s"
          % (len(pd.read_csv(path)), len(df), len(tbl), metric))
    print(tbl.to_string(index=False, max_colwidth=28))
    if group and group in df.columns:
        g = df.groupby(group)[metric].agg(["count", "max", "median"]).sort_values("max", ascending=False)
        print("\nby %s:" % group)
        print(g.to_string())
    print()

    q = question or ("What pattern do the top rows share, and is anything in this table "
                     "internally inconsistent or suspicious?")
    prompt = ("Here is a table of already-computed backtest results, sorted by %s.\n\n%s\n\n%s"
              % (metric, tbl.to_string(index=False, max_colwidth=28), q))
    txt, secs, tps = ask(prompt)
    print("=" * 100)
    print("MODEL (%s, %.1fs, %.1f tok/s) -- UNVERIFIED OPINION. Do not quote its numbers; "
          "re-derive anything you intend to act on." % (MODEL, secs, tps))
    print(txt)


# ── long reading: --summarize ────────────────────────────────────────────────────────────
SUMMARY_HEADER = ("LOCAL MODEL SUMMARY (%s, unverified - quote nothing from it as fact)"
                  % MODEL.split(":")[0])

READ_SYSTEM = (
    "You read files for a quantitative trading research team and answer ONE question about "
    "them. Use only the text you are given. When a line decides the answer (an error, a "
    "PASS/FAIL, a final status), copy it exactly. Never invent a number, a file name or a "
    "cause. If the text does not settle the question, say so plainly, then say what it DOES "
    "show (for a log: the last step it reached, copied exactly) - do not guess past that. "
    "Lines reading [REDACTED] were removed on purpose - ignore them. Plain text, no "
    "markdown headers, no preamble, no restating of the question."
)

# A line matching ANY of these never reaches the model (nor the audit log): it is replaced
# by REDACTED_LINE before chunking. Case-insensitive. Deliberately broad - losing a log line
# is cheap, a key in a prompt (and in C:\EdgeLog\local_llm.log) is not.
_SECRET_PATTERNS = (
    r"ALPACA_", r"APCA[-_]", r"API[_-]?KEY", r"SECRET",
    r"TOKEN[\"']?\s*[=:]",                  # TOKEN=..., "access_token": ..., token: ...
    r"PASSW(?:OR)?D", r"\bPWD\s*[=:]", r"\bPIN\s*[\"']?\s*[=:]",
    r"\bBearer\b", r"Authorization\s*[\"']?\s*:",
    r"NTFY_", r"ntfy\.sh/\S", r"\btopic[\"']?\s*[=:]",      # ntfy topic = a write capability
    r"[_-]KEY[\"']?\s*[=:]", r"[?&](?:api)?key=",           # app_key=, x-api-key:, ?key=
    r"\b(?:access|private|client|app)[_-]?key\b",
    r"://[^/\s:@]+:[^/\s@]+@",                              # user:pass@host URLs
    r"\bsk-[A-Za-z0-9_-]{16,}", r"\bgh[pousr]_[A-Za-z0-9]{20,}", r"\bAKIA[0-9A-Z]{16}\b",
    r"\bxox[abprs]-", r"BEGIN [A-Z ]*PRIVATE KEY",
)
_SECRET_RE = re.compile("|".join("(?:%s)" % p for p in _SECRET_PATTERNS), re.IGNORECASE)
_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY", re.IGNORECASE)
_PEM_END = re.compile(r"-----END [A-Z ]*PRIVATE KEY", re.IGNORECASE)
REDACTED_LINE = "[REDACTED]"


def secret_mask(lines):
    """[bool] per line: True = must not be sent. A PEM private-key block is masked whole."""
    mask, in_pem = [], False
    for ln in lines:
        if _PEM_BEGIN.search(ln):
            in_pem = True
        hit = in_pem or bool(_SECRET_RE.search(ln))
        if in_pem and _PEM_END.search(ln):
            in_pem = False
        mask.append(hit)
    return mask


def redact_lines(lines):
    """(clean_lines, n_redacted)."""
    mask = secret_mask(lines)
    return ([REDACTED_LINE if m else ln for ln, m in zip(lines, mask)], sum(mask))


def expand_paths(paths):
    """(files, problems): globs expanded (recursive ** allowed), duplicates dropped in order."""
    files, problems, seen = [], [], set()
    for p in paths:
        p = os.path.expanduser(os.path.expandvars(str(p).strip().strip('"')))
        if not p:
            continue
        if any(c in p for c in "*?["):
            hits = sorted(h for h in glob.glob(p, recursive=True) if os.path.isfile(h))
            if not hits:
                problems.append("%s: no file matches" % p)
        elif os.path.isdir(p):
            problems.append("%s: is a folder - pass a glob such as %s" % (p, os.path.join(p, "*.log")))
            hits = []
        elif not os.path.isfile(p):
            problems.append("%s: not found" % p)
            hits = []
        else:
            hits = [p]
        for h in hits:
            key = os.path.normcase(os.path.abspath(h))
            if key not in seen:
                seen.add(key)
                files.append(os.path.abspath(h))
    return files, problems


def _decode(raw):
    """bytes -> str, or None when the file looks binary. Handles UTF-8/16 BOMs and the
    BOM-less UTF-16LE that Windows PowerShell 5.1 redirection writes."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", "replace")
    head = raw[:8192]
    if len(head) >= 4 and head[1::2].count(0) > 0.4 * len(head[1::2]) and head[0::2].count(0) < 0.05 * len(head[0::2]):
        return raw.decode("utf-16-le", "replace")
    if b"\x00" in head:
        return None
    return raw.decode("utf-8", "replace")


def read_text(path):
    """(text or None, note). PDFs through pypdf with [page N] markers; None = skipped."""
    if path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            return None, "pypdf not installed - PDF skipped (pip install pypdf)"
        try:
            reader = PdfReader(path)
            parts = []
            for i, page in enumerate(reader.pages, 1):
                parts.append("[page %d]\n%s" % (i, (page.extract_text() or "").strip()))
            text = "\n".join(parts)
        except Exception as e:
            return None, "PDF unreadable (%s: %s)" % (type(e).__name__, str(e)[:120])
        if not text.replace("[page", "").strip(" ]0123456789\n"):
            return None, "PDF has no extractable text (scanned images?) - skipped"
        return text, "pdf, %d pages" % len(reader.pages)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return None, "unreadable (%s)" % e.strerror
    text = _decode(raw)
    if text is None:
        return None, "binary file - skipped"
    return text, ""


def grep_select(lines, pattern, context=GREP_CONTEXT):
    """Indices of lines matching `pattern` (regex, case-insensitive; an invalid regex is
    taken literally) plus `context` lines either side, in order."""
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        rx = re.compile(re.escape(pattern), re.IGNORECASE)
    keep = set()
    for i, ln in enumerate(lines):
        if rx.search(ln):
            keep.update(range(max(0, i - context), min(len(lines), i + context + 1)))
    return sorted(keep)


def prepare_file(path, tail=None, grep=None):
    """Read one file and reduce it to what will be sent. Returns a dict:
    path, bytes, lines_total, lines_sent, chars_sent, redacted, note, body (list of lines or
    None when the file was skipped). Redaction is applied to every line that is sent."""
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    info = {"path": path, "bytes": size, "lines_total": 0, "lines_sent": 0, "chars_sent": 0,
            "redacted": 0, "note": "", "body": None}
    text, note = read_text(path)
    info["note"] = note
    if text is None:
        return info
    lines = text.splitlines()
    info["lines_total"] = len(lines)
    offset = 0
    if tail and len(lines) > tail:
        offset = len(lines) - int(tail)
        lines = lines[offset:]
    mask = secret_mask(lines)            # computed on the whole (tailed) text: PEM blocks span lines
    if grep:
        idx = grep_select(lines, grep)
        body, prev = [], None
        for i in idx:
            if prev is not None and i != prev + 1:
                body.append("--")
            body.append("L%d: %s" % (offset + i + 1, REDACTED_LINE if mask[i] else lines[i]))
            prev = i
        info["redacted"] = sum(1 for i in idx if mask[i])
        info["lines_sent"] = len(idx)
    else:
        body = [REDACTED_LINE if m else ln for ln, m in zip(lines, mask)]
        info["redacted"] = sum(mask)
        info["lines_sent"] = len(lines)
    info["body"] = body
    info["chars_sent"] = sum(len(b) + 1 for b in body)
    return info


def make_chunks(docs, chunk_chars):
    """Pack (label, lines) documents into chunks of at most `chunk_chars` characters,
    breaking on line boundaries. Every chunk names the file each of its lines came from
    ('===== FILE: x =====', or '(continued)' when a file runs across a chunk boundary).
    A single line longer than a quarter chunk is hard-split."""
    chunk_chars = max(2000, int(chunk_chars))
    piece_max = chunk_chars // 4
    chunks, cur, cur_len, cur_file = [], [], 0, None

    def flush():
        nonlocal cur, cur_len, cur_file
        if cur:
            chunks.append("\n".join(cur))
        cur, cur_len, cur_file = [], 0, None

    for label, lines in docs:
        started = False
        for line in lines:
            pieces = [line[i:i + piece_max] for i in range(0, len(line), piece_max)] or [""]
            for piece in pieces:
                header = "===== FILE: %s%s =====" % (label, " (continued)" if started else "")
                need = len(piece) + 1 + (0 if cur_file == label else len(header) + 1)
                if cur and cur_len + need > chunk_chars:
                    flush()
                if cur_file != label:
                    cur.append(header)
                    cur_len += len(header) + 1
                    cur_file = label
                cur.append(piece)
                cur_len += len(piece) + 1
                started = True
    flush()
    return chunks


def _cap_words(text, words):
    w = text.split()
    if len(w) <= int(words * 1.15):
        return text
    return " ".join(w[:words]) + " [cut at %d words]" % words


def _say(progress, msg):
    if progress:
        progress(msg)


def summarize(paths, question, words=WORDS, tail=None, grep=None, chunk_tokens=CHUNK_TOKENS,
              max_chunks=MAX_CHUNKS, timeout=CALL_TIMEOUT, dry_run=False, progress=None):
    """Map-reduce a short answer to `question` over `paths`. Returns a result dict (render
    it with format_summary). Raises ValueError for bad input / nothing to read / too many
    chunks, OllamaDown / OllamaError for the model. Never prints: `progress` (a callable
    taking one line) gets the running commentary."""
    t0 = time.time()
    question = " ".join(str(question or "").split())
    if not question:
        raise ValueError("a question is required (--ask \"...\")")
    words = max(20, int(words or WORDS))
    if tail is not None and int(tail) < 1:
        raise ValueError("--tail must be >= 1")
    if isinstance(paths, str):
        paths = [paths]
    files, problems = expand_paths(paths or [])
    if not files:
        raise ValueError("nothing to read: " + ("; ".join(problems) or "no paths given"))
    num_ctx = NUM_CTX
    # the chunk must leave room for the instructions and the answer inside num_ctx
    budget = num_ctx - 2000 - max(600, int(words * 2))
    chunk_tokens = max(1000, min(int(chunk_tokens), budget))
    chunk_chars = int(chunk_tokens * CHARS_PER_TOKEN)

    infos = [prepare_file(f, tail=tail, grep=grep) for f in files]
    docs = [(i["path"], i["body"]) for i in infos if i["body"]]
    res = {"question": question, "files": infos, "problems": problems, "grep": grep,
           "tail": tail, "words": words, "chunk_tokens": chunk_tokens, "num_ctx": num_ctx,
           "chunks": 0, "calls": 0, "secs": 0.0, "tps": 0.0, "answer": "", "warnings": [],
           "dry_run": bool(dry_run)}
    res["redacted"] = sum(i["redacted"] for i in infos)
    if not docs:
        if grep and any(i["body"] is not None for i in infos):
            res["answer"] = "(no line matched --grep-first %r - nothing was sent to the model)" % grep
            res["secs"] = time.time() - t0
            return res
        raise ValueError("nothing readable: " + "; ".join(
            "%s: %s" % (i["path"], i["note"] or "empty") for i in infos))
    chunks = make_chunks(docs, chunk_chars)
    res["chunks"] = len(chunks)
    if len(chunks) > max_chunks:
        raise ValueError(
            "%d chunks of ~%dk tokens is more than max_chunks=%d (each chunk is minutes of "
            "local compute). Narrow it: --tail N, --grep-first PATTERN, fewer files - or "
            "raise --max-chunks." % (len(chunks), chunk_tokens // 1000, max_chunks))
    if dry_run:
        res["answer"] = "(dry run - nothing sent to the model)"
        res["secs"] = time.time() - t0
        return res

    ping()                                   # fail in 5 s, not after a 30-minute timeout
    q_block = "QUESTION: %s" % question
    eval_tokens, eval_secs, read_tokens, read_secs = 0, 0.0, 0, 0.0

    def call(prompt, num_predict, label):
        nonlocal eval_tokens, eval_secs, read_tokens, read_secs
        _say(progress, "%s ... (%.0fs elapsed)" % (label, time.time() - t0))
        r = generate(prompt, system=READ_SYSTEM, num_predict=num_predict, timeout=timeout,
                     num_ctx=num_ctx)
        res["calls"] += 1
        eval_tokens += r["eval_tokens"]
        eval_secs += (r["eval_tokens"] / r["tps"]) if r["tps"] else 0.0
        if r["prompt_tps"]:
            read_tokens += r["prompt_tokens"]
            read_secs += r["prompt_tokens"] / r["prompt_tps"]
        if r["prompt_tokens"] >= num_ctx - num_predict - 64:
            res["warnings"].append("%s: prompt filled the context (%d tokens) - Ollama may "
                                   "have cut it; use a smaller --chunk-tokens"
                                   % (label, r["prompt_tokens"]))
        return r["text"]

    final_predict = int(words * 2) + 64
    if len(chunks) == 1:
        prompt = ("%s\n\nFILES:\n%s\n\n%s\nAnswer in at most %d words."
                  % (q_block, chunks[0], q_block, words))
        answer = call(prompt, final_predict, "reading 1 chunk")
    else:
        notes = []
        for i, ch in enumerate(chunks, 1):
            prompt = ("%s\n\nThis is part %d of %d of the files. Write terse notes (at most 120 "
                      "words) on everything in THIS part that bears on the question: copy "
                      "decisive lines exactly and say which file they are in. If nothing here "
                      "is relevant, reply exactly: nothing relevant.\n\n%s\n\n%s"
                      % (q_block, i, len(chunks), ch, q_block))
            note = call(prompt, 400, "map chunk %d/%d" % (i, len(chunks)))
            notes.append("[part %d of %d] %s" % (i, len(chunks), note or "(empty)"))
        # reduce; if the notes themselves overflow a chunk, reduce them in groups first
        level = 0
        while sum(len(n) + 2 for n in notes) > chunk_chars and len(notes) > 1 and level < 4:
            level += 1
            groups = make_chunks([("notes", notes)], chunk_chars)
            notes = [call("%s\n\nCondense these notes, keeping every exact quoted line that "
                          "bears on the question (at most 200 words):\n\n%s" % (q_block, g),
                          500, "condense %d.%d/%d" % (level, j, len(groups)))
                     for j, g in enumerate(groups, 1)]
        prompt = ("%s\n\nBelow are notes taken from %d consecutive parts of the files "
                  "(later parts come later in the files). Answer the question from these "
                  "notes only, in at most %d words. If the notes disagree, say so.\n\n%s\n\n%s"
                  % (q_block, len(chunks), words, "\n\n".join(notes), q_block))
        answer = call(prompt, final_predict, "reduce %d notes" % len(notes))
    res["answer"] = _cap_words(answer, words) if answer else (
        "[empty answer from the model - try again, or raise --words]")
    res["secs"] = time.time() - t0
    res["tps"] = (eval_tokens / eval_secs) if eval_secs else 0.0
    res["read_tps"] = (read_tokens / read_secs) if read_secs else 0.0
    _log("SUMMARIZE %s | tail=%s grep=%s | Q: %s"
         % (", ".join(os.path.basename(i["path"]) for i in infos), tail, grep, question),
         res["answer"], res["secs"], res["tps"], MODEL)
    return res


def format_summary(res):
    """The printed / MCP-returned text of a summarize() result."""
    out = [SUMMARY_HEADER, "question: %s" % res["question"]]
    sent = [i for i in res["files"] if i["body"] is not None]
    skipped = [i for i in res["files"] if i["body"] is None]
    out.append("files read (%d):" % len(sent))
    for i in sent:
        extra = []
        if res.get("tail"):
            extra.append("tail %d" % res["tail"])
        if res.get("grep"):
            extra.append("grep hits+ctx")
        if i["note"]:
            extra.append(i["note"])
        out.append("  %s - %s bytes on disk, %s chars sent (%d of %d lines%s)"
                   % (i["path"], format(i["bytes"], ","), format(i["chars_sent"], ","),
                      i["lines_sent"], i["lines_total"],
                      (", " + ", ".join(extra)) if extra else ""))
    for i in skipped:
        out.append("  SKIPPED %s - %s" % (i["path"], i["note"]))
    for p in res.get("problems") or []:
        out.append("  NOT READ %s" % p)
    out.append("redacted: %d line%s (key/token/password/ntfy patterns) | grep-first: %s"
               % (res["redacted"], "" if res["redacted"] == 1 else "s",
                  repr(res["grep"]) if res.get("grep") else "off"))
    speed = ""
    if res.get("read_tps") or res.get("tps"):
        speed = " | reading %.0f tok/s, writing %.1f tok/s" % (res.get("read_tps") or 0.0,
                                                               res.get("tps") or 0.0)
    out.append("chunks: %d (<= ~%dk tokens each, num_ctx %d) | model calls: %d | %.1fs%s"
               % (res["chunks"], res["chunk_tokens"] // 1000, res["num_ctx"], res["calls"],
                  res["secs"], speed))
    for w in res.get("warnings") or []:
        out.append("WARNING: %s" % w)
    out.append("-" * 72)
    out.append(res["answer"])
    return "\n".join(out)


def status(warm_test=True, timeout=CALL_TIMEOUT):
    """(ok, text): is Ollama up, is the model installed / loaded / on the GPU, and a
    one-line warm test with tokens/sec. Never raises."""
    lines = []
    try:
        ver = ping()
    except (OllamaDown, OllamaError) as e:
        return False, str(e)
    lines.append("Ollama: UP at %s (version %s)" % (_host_label(), ver))
    ok = True
    try:
        tags = _http_json("/api/tags", timeout=10).get("models") or []
        m = next((t for t in tags if t.get("name") == MODEL or t.get("model") == MODEL), None)
        if m:
            det = m.get("details") or {}
            lines.append("model %s: installed (%.1f GB, %s, %s)"
                         % (MODEL, (m.get("size") or 0) / 1e9, det.get("parameter_size", "?"),
                            det.get("quantization_level", "?")))
        else:
            ok = False
            lines.append("model %s: NOT INSTALLED - run: ollama pull %s" % (MODEL, MODEL))
        ps = _http_json("/api/ps", timeout=10).get("models") or []
        p = next((x for x in ps if x.get("name") == MODEL or x.get("model") == MODEL), None)
        if p:
            size, vram = p.get("size") or 0, p.get("size_vram") or 0
            gpu = (100.0 * vram / size) if size else 0.0
            lines.append("loaded: yes - %.0f%% GPU / %.0f%% CPU, context %s, unloads at %s"
                         % (gpu, 100 - gpu, p.get("context_length", "?"),
                            str(p.get("expires_at", "?"))[11:19]))
            if not vram:
                lines.append("WARNING: CPU ONLY - Ollama is not using the GPU (expect a few "
                             "tok/s). Its server.log 'inference compute' line says why; "
                             "restarting Ollama usually re-detects the GPU.")
        else:
            lines.append("loaded: no - the first call cold-loads the weights (minutes)")
    except (OllamaDown, OllamaError) as e:
        lines.append("could not read model state: %s" % e)
    if warm_test and ok:
        try:
            r = generate("Reply with the numbers 1 to 10 separated by spaces, nothing else.",
                         system="Answer exactly as asked.", num_predict=40, timeout=timeout)
            lines.append("warm test: %r in %.1fs, %.1f tok/s generation, load %.1fs%s"
                         % (r["text"][:40], r["secs"], r["tps"], r["load_secs"],
                            " (was cold)" if r["load_secs"] > 5 else ""))
        except (OllamaDown, OllamaError) as e:
            ok = False
            lines.append("warm test FAILED: %s" % e)
    return ok, "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--warm", action="store_true", help="preload the weights (~3.5 min cold)")
    ap.add_argument("--ask", help="a question; with --csv it is asked ABOUT the table")
    ap.add_argument("--csv", help="results file to triage")
    ap.add_argument("--metric", default="ryr", help="numeric column to rank by")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--group", help="column to group the summary by (e.g. famKey)")
    ap.add_argument("--floor-col", help="optional column to filter on")
    ap.add_argument("--floor", type=float, help="minimum value for --floor-col")
    ap.add_argument("--num-predict", type=int, default=400)
    ap.add_argument("--status", action="store_true",
                    help="is Ollama up, model installed/loaded/on GPU, 1-line warm test")
    ap.add_argument("--summarize", nargs="+", metavar="PATH",
                    help="files/globs to read (text, logs, .md, .py, .csv, .json, .pdf); "
                         "the question goes in --ask")
    ap.add_argument("--words", type=int, default=WORDS, help="answer length cap (default 200)")
    ap.add_argument("--tail", type=int, help="read only the last N lines of each file")
    ap.add_argument("--grep-first", metavar="PATTERN",
                    help="send only lines matching this regex (case-insensitive) +-3 lines")
    ap.add_argument("--chunk-tokens", type=int, default=CHUNK_TOKENS,
                    help="tokens per chunk, char-estimated (default 24000)")
    ap.add_argument("--max-chunks", type=int, default=MAX_CHUNKS,
                    help="refuse a read bigger than this many chunks (default 12)")
    ap.add_argument("--timeout", type=int, default=CALL_TIMEOUT, help="seconds per model call")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --summarize: show files, redactions and chunks; send nothing")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(errors="replace")     # a cp1252 pipe must not kill the answer
    except Exception:
        pass

    if a.status:
        ok, txt = status(timeout=a.timeout)
        print(txt)
        sys.exit(0 if ok else 2)
    if a.summarize:
        if not a.ask:
            ap.error("--summarize needs the question in --ask \"...\"")
        try:
            res = summarize(a.summarize, a.ask, words=a.words, tail=a.tail, grep=a.grep_first,
                            chunk_tokens=a.chunk_tokens, max_chunks=a.max_chunks,
                            timeout=a.timeout, dry_run=a.dry_run,
                            progress=lambda m: print("  .. " + m, file=sys.stderr, flush=True))
        except (OllamaDown, OllamaError, ValueError) as e:
            print("local_llm: %s" % e, file=sys.stderr)
            sys.exit(2)
        print(format_summary(res))
        return

    if a.warm:
        t, secs, tps = ask("Reply with the single word: ready", num_predict=16)
        print("warm-up: %r in %.1fs (%.1f tok/s)" % (t[:40], secs, tps))
        if not a.ask and not a.csv:
            return
    if a.csv:
        triage_csv(a.csv, a.metric, a.top, a.group, a.ask, a.floor_col, a.floor)
        return
    if a.ask:
        t, secs, tps = ask(a.ask, num_predict=a.num_predict)
        print("MODEL (%.1fs, %.1f tok/s) -- UNVERIFIED:" % (secs, tps))
        print(t)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
