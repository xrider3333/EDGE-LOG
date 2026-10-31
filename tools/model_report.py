r"""MODEL REPORT CARD (Open Board B11, owner 10-29 via MANAGER #137) - the weekly score of the local models.

Scores every Ollama model whose name starts with "2." to "5." (the owner's numbered models) and "1.STRATA qwen3.8-flash:125b-256k" (the Strata
server on :8080, OpenAI API) on the 11 hard trading / statistics questions of C:\EdgeLog\strata_test\qhard.py (copied below,
Python grades them: last number in the answer within 0.1% or 0.051 of the key), think OFF, temperature 0. Also measures
write speed (tok/s over the 11 answers) and read speed (one ~20K-token read of index.html).

Strata runs only after 13:00 MST (owner rule: heavy Strata tests after the close) and only if its server answers; otherwise its
row says why. Results are appended as a dated section to C:\EdgeLog\manager\model_report.md (newest first), raw rows to
model_report.jsonl beside it.

    python tools/model_report.py              (all models)
    python tools/model_report.py --only 3.    (one model, by name prefix)
    python tools/model_report.py --dry        (list what it would score + the trap questions; no model call)

TRAPS (c23, scope P3): besides the 11 questions, two known Qwen mistakes from qwen_vs_claude.md (Q2/Q4) are asked as
one question each and scored per model as two extra columns, "Unit trap" (points vs dollars on MES $5/pt) and
"TZ trap" (a GMT statement time asked in MST, where ET or MDT is the wrong answer). The unit trap is graded like the 11
(last number); the TZ trap on the last HH:MM in the answer. Promptfoo is not installed and nothing new is installed:
this script IS the saved test set. --dry never calls a model.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

OLLAMA = os.environ.get("AUGUR_LOCAL_LLM_HOST", "http://127.0.0.1:11434").rstrip("/")
STRATA = "http://127.0.0.1:8080"
STRATA_NAME = "1.STRATA qwen3.8-flash:125b-256k"   # owner renumber 10-30 (MANAGER #220)
OUT_MD = r"C:\EdgeLog\manager\model_report.md"
OUT_JSONL = r"C:\EdgeLog\manager\model_report.jsonl"
INDEX_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
STRATA_FROM_HOUR = 13            # MST, the owner's rule
READ_CHARS = 52000               # ~20K tokens of index.html
CTX = 32768

Q = [
    ("A strategy wins 52% of trades; the average win is 1.2R and the average loss is 1R. What is the expectancy per trade in R?", 0.144),
    ("You test 20 independent strategies that all have zero true edge, each at the 5% significance level. What is the probability, in percent, that at least one looks significant? One decimal.", 64.2),
    ("A bet wins with probability 0.55 and pays 1:1. What Kelly fraction of the account should be bet, in percent?", 10.0),
    ("An account of $10,000 returns +10%, -10%, +10%, -10% in that order. What is the final balance in dollars, to the cent?", 9801.0),
    ("An equity curve reads 100, 120, 90, 130, 104, 140, 112. What is the maximum drawdown from a peak, in percent, one decimal?", 25.0),
    ("1% of tested strategies have a real edge. A validation test passes 80% of real strategies and 10% of fake ones. Given a strategy passed, what is the probability in percent that it is real? One decimal.", 7.5),
    ("Daily mean return is 0.05% and daily standard deviation is 1%. Using 252 trading days, what is the annualized Sharpe ratio? Two decimals.", 0.79),
    ("A strategy must be profitable in all 3 independent walk-forward folds to pass; each fold is profitable with probability 60%. What is the probability it passes, in percent, one decimal?", 21.6),
    ("A strategy has a 50% win rate. What is the probability, in percent, of getting at least 7 wins in 10 independent trades? One decimal.", 17.2),
    ("MES is $5 per point. You buy 4 contracts at 5800.25 with a stop at 5795.75, and pay $1.24 round-trip commission per contract. What is the total dollar risk if stopped out? Two decimals.", 94.96),
    ("100 trades have a standard deviation of $200 per trade. What is the standard error of the mean trade P&L in dollars?", 20.0),
]
SUFFIX = " Show brief working, then give the final answer as a number on the last line."

# c23: the two traps Qwen fell into on Q2/Q4 (qwen_vs_claude.md). Keys: unit -> last number; tz -> last HH:MM.
TRAP_UNIT = ("MES is $5 per point. You buy 2 contracts at 5800.00 and sell them at 5803.50. The account statement must show "
             "the profit in DOLLARS, not points. What is the profit in dollars?" + SUFFIX, 35.0)
TRAP_TZ = ("A broker statement shows a fill at 14:30 GMT on 2026-07-15. The owner lives in Arizona and keeps all his logs in "
           "MST (Mountain Standard Time, UTC-7, no daylight saving). What is the fill time in MST? Answer as HH:MM 24-hour "
           "on the last line.", "07:30")
TRAPS = [("trap_unit", TRAP_UNIT[0], TRAP_UNIT[1], None), ("trap_tz", TRAP_TZ[0], TRAP_TZ[1], "time")]


def grade(text, want):
    nums = re.findall(r"-?\d[\d,]*\.?\d*", (text or "").replace("$", ""))
    try:
        got = float(nums[-1].replace(",", "")) if nums else None
    except ValueError:
        got = None
    return got is not None and abs(got - want) <= max(0.051, abs(want) * 0.001)


def grade_time(text, want):
    """Last HH:MM in the answer equals the key ("07:30" also accepts "7:30")."""
    hits = re.findall(r"\b(\d{1,2}):(\d{2})\b", text or "")
    if not hits:
        return False
    h, m = hits[-1]
    wh, wm = want.split(":")
    return int(h) == int(wh) and m == wm


def _post(url, body, timeout=3600):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def ollama_models():
    tags = json.load(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10))
    return sorted(m["name"] for m in tags.get("models", []) if re.match(r"^[2-5]\.", m["name"]))


def ollama_gen(model, prompt, n):
    r = _post(OLLAMA + "/api/generate", {"model": model, "prompt": prompt, "stream": False, "think": False,
                                          "options": {"num_ctx": CTX, "num_predict": n, "temperature": 0}, "keep_alive": "2m"})
    return r["response"], r.get("eval_count", 0), r.get("eval_duration", 0) / 1e9, r.get("prompt_eval_count", 0), r.get("prompt_eval_duration", 0) / 1e9


def strata_model():
    return json.load(urllib.request.urlopen(STRATA + "/v1/models", timeout=10))["data"][0]["id"]


def strata_gen(prompt, n, model):
    t = time.time()
    r = _post(STRATA + "/v1/chat/completions", {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                                                "max_tokens": n, "chat_template_kwargs": {"enable_thinking": False}})
    dt = time.time() - t
    u = r.get("usage", {})
    return (r["choices"][0]["message"].get("content") or ""), u.get("completion_tokens", 0), dt, u.get("prompt_tokens", 0), None


def score(name, gen):
    ok = toks = secs = 0
    t0 = time.time()
    for p, want in Q:
        text, n, s, _, _ = gen(p + SUFFIX, 1200)
        ok += grade(text, want)
        toks += n
        secs += s
    traps = {}
    for key, prompt, want, kind in TRAPS:                           # c23: scored but not counted in the 11
        text, n, s, _, _ = gen(prompt, 1200)
        traps[key] = bool(grade_time(text, want) if kind == "time" else grade(text, want))
        toks += n
        secs += s
    html = open(INDEX_HTML, encoding="utf-8", errors="ignore").read()[:READ_CHARS]
    _, _, _, ptok, psec = gen("Here is part of the EDGE-LOG site source:\n\n" + html + "\n\nIn 3 bullets: what are the main tabs?", 120)
    return dict({"model": name, "score": ok, "of": len(Q), "write_tps": round(toks / secs, 1) if secs else None,
                 "read_tps": round(ptok / psec, 0) if psec else None, "read_tokens": ptok, "minutes": round((time.time() - t0) / 60, 1)},
                **traps)


def stop(model):
    subprocess.run(["ollama", "stop", model], capture_output=True)
    time.sleep(3)


def _trap(r, key):
    return "-" if key not in r else ("ok" if r[key] else "MISS")


def render(rows, when):
    lines = ["## %s" % when.strftime("%Y-%m-%d %H:%M"), "",
             "| Model | 11 hard Qs | Unit trap | TZ trap | Write tok/s | Read tok/s | Minutes |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("skipped"):
            lines.append("| %s | - | - | - | - | - | %s |" % (r["model"], r["skipped"]))
        else:
            lines.append("| %s | %d/%d | %s | %s | %s | %s | %s |" % (r["model"], r["score"], r["of"], _trap(r, "trap_unit"), _trap(r, "trap_tz"),
                                                                  r["write_tps"], r["read_tps"] if r["read_tps"] else "-", r["minutes"]))
    lines += ["", "Think off, temperature 0, Python-graded (C:\\EdgeLog\\strata_test\\qhard.py questions). Read = one ~20K-token read of index.html. "
              "1.STRATA write tok/s includes its read time (its API reports no split). "
              "Unit trap = MES $5/pt profit asked in dollars (points = wrong); TZ trap = a GMT statement time asked in MST (ET or MDT = wrong); "
              "ok / MISS per model.", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", help="score only models whose name starts with this")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out", default=OUT_MD)
    a = ap.parse_args(argv)
    now = datetime.datetime.now()
    try:
        names = ollama_models() + [STRATA_NAME]
    except Exception as e:                                           # noqa: BLE001  (--dry must work with Ollama down)
        if not a.dry:
            raise
        print("ollama not answering (%s) - dry list without its models" % type(e).__name__)
        names = [STRATA_NAME]
    if a.only:
        names = [n for n in names if n.startswith(a.only)]
    if a.dry:
        print("would score:", ", ".join(names))
        print("questions: %d hard + %d traps (no model is called in --dry)" % (len(Q), len(TRAPS)))
        for key, prompt, want, _ in TRAPS:
            print("  %s -> %s: %s" % (key, want, prompt))
        return 0
    rows = []
    for n in names:
        if n == STRATA_NAME:
            if now.hour < STRATA_FROM_HOUR:
                rows.append({"model": n, "skipped": "before 13:00 MST (owner rule)"})
                continue
            try:
                sm = strata_model()
            except Exception as e:
                rows.append({"model": n, "skipped": "server not up (%s)" % type(e).__name__})
                continue
            rows.append(score(STRATA_NAME + " (%s)" % sm, lambda p, k: strata_gen(p, k, sm)))
        else:
            try:
                rows.append(score(n, lambda p, k, m=n: ollama_gen(m, p, k)))
            finally:
                stop(n)
        print(rows[-1], flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    old = open(a.out, encoding="utf-8").read() if os.path.exists(a.out) else ""
    head = "# Local model report card\n\nWeekly, newest first. Written by tools/model_report.py (board B11).\n\n"
    body = old.split("\n\n", 2)[2] if old.startswith("# Local model report card") and old.count("\n\n") >= 2 else old
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + render(rows, now) + "\n" + body)
    with open(os.path.join(os.path.dirname(a.out), "model_report.jsonl"), "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(dict(r, ts=now.isoformat(timespec="seconds"))) + "\n")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
