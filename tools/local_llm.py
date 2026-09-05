"""local_llm.py -- run the LOCAL model (Ollama / qwen3.6) as a triage assistant.

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
under MODEL is a 23 GB local model's opinion, is not verified, and must never reach a doc,
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

USE
  python tools/local_llm.py --warm
  python tools/local_llm.py --ask "one sentence: what does a 101% top-10 share mean?"
  python tools/local_llm.py --csv tools/r16_results/ryr_frontier.csv --metric ryr \
      --top 12 --group famKey --ask "which families cluster at the top, and what looks odd"

Stdlib + pandas only. No new dependency: Ollama is already installed and serving on
127.0.0.1:11434.
"""
from __future__ import annotations
import argparse
import io
import json
import sys
import time
import os
import urllib.error
import urllib.request

HOST = "http://127.0.0.1:11434"
MODEL = "qwen3.6:latest"
KEEP_ALIVE = "30m"          # hold the weights in RAM so the next call is warm

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


def ask(prompt, system=SYSTEM, num_predict=400, timeout=600, model=MODEL, think=False):
    """One completion from the local model. Returns (text, seconds, tokens_per_sec).

    think=False matters: see the measurement note in the module docstring.
    """
    body = json.dumps({
        "model": model, "prompt": prompt, "system": system, "stream": False,
        "think": think, "keep_alive": KEEP_ALIVE,
        "options": {"num_predict": int(num_predict), "temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(HOST + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        return ("[local model unreachable: %s -- is `ollama serve` running?]" % e, time.time() - t0, 0.0)
    except TimeoutError:
        return ("[local model timed out after %ds -- it was probably cold; run --warm first]"
                % timeout, time.time() - t0, 0.0)
    txt = (d.get("response") or "").strip()
    ec = d.get("eval_count") or 0
    ed = (d.get("eval_duration") or 0) / 1e9
    if not txt:
        txt = ("[empty response -- num_predict %d was consumed before any answer. Raise it, "
               "or check think=False.]" % num_predict)
    secs, tps = time.time() - t0, ((ec / ed) if ed else 0.0)
    _log(prompt, txt, secs, tps, model)
    return (txt, secs, tps)


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
    a = ap.parse_args()

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
