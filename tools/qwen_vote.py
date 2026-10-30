r"""QWEN VOTE (board C3, owner 10-30 via MANAGER #139) - ask the local model the same yes/no question 3-5 times, keep the majority.

One local-model answer to "does this log show a failure?" or "does this paper test on out-of-sample data?" is a coin with a
bias. Voting N times (temperature 0.7, a different seed each time) turns it into a label with an agreement score: 5/5 YES is
a label, 3/5 is a "look yourself". Python counts the votes; the model only says YES or NO.

Goes through the router at 127.0.0.1:11435/v1 (OpenAI API), model 5.qwen3.6:35b-32k, think off. Text is redacted with
local_llm's secret mask before it leaves this process. The answer is UNVERIFIED like every local-model read: a label tells
you where to look, never a verdict to quote.

    python tools/qwen_vote.py -q "Does this log show a failed ship?" C:/EdgeLog/post_push/*.log
    python tools/qwen_vote.py -q "Is this paper tested on out-of-sample data?" --votes 5 paper1.txt paper2.txt
    some_cmd | python tools/qwen_vote.py -q "Is this line an error?" --lines -      (one label per stdin line)
    ONE DOOR (MANAGER #222): with no `ask` given, vote() files the question as a Qwen task (tools/qwen_task.add_task)
    for tools/qwen_runner.py and returns {"label": None, "queued": n}; the CLI does the same per item unless --direct.
    --tail N (last N lines of each file) | --json (one JSON object per item) | --model / --host to override
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from local_llm import redact_lines  # noqa: E402

HOST = os.environ.get("AUGUR_QWEN_ROUTER", "http://127.0.0.1:11435/v1").rstrip("/")
MODEL = "5.qwen3.6:35b-32k"
TEMPERATURE = 0.7
MAX_TOKENS = 1024             # a model that thinks anyway spends its budget there first; 8 tokens left it empty (10-30 smoke)
MAX_CHARS = 60000              # ~17K tokens: fits the 32k context with room for the question
SYSTEM = ("You label text for a trading-research team. Read the text, then answer the question with exactly one word: "
          "YES or NO. No other words.")
_WORD = re.compile(r"\b(YES|NO)\b", re.I)


def parse_vote(text):
    """'YES' / 'NO' from the model's reply (first such word), else None (a spoiled ballot)."""
    m = _WORD.search(text or "")
    return m.group(1).upper() if m else None


def tally(votes):
    """{label, yes, no, spoiled, agree}: label = the majority of the valid votes, 'SPLIT' on a tie, None when no vote
    counted. agree = majority share of the valid votes."""
    yes, no = votes.count("YES"), votes.count("NO")
    spoiled = len(votes) - yes - no
    valid = yes + no
    label = None if not valid else ("YES" if yes > no else "NO" if no > yes else "SPLIT")
    return {"label": label, "yes": yes, "no": no, "spoiled": spoiled,
            "agree": round(max(yes, no) / valid, 2) if valid else 0.0}


def chat(question, text, seed, model=MODEL, host=HOST, timeout=1800):
    body = {"model": model, "temperature": TEMPERATURE, "seed": seed, "max_tokens": MAX_TOKENS, "reasoning_effort": "none",
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": "/no_think\nTEXT:\n" + text + "\n\nQUESTION: " + question + "\nAnswer YES or NO."}],
            "chat_template_kwargs": {"enable_thinking": False}, "think": False}
    req = urllib.request.Request(host + "/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    ans = r["choices"][0]["message"].get("content") or ""
    return re.sub(r"(?s)<think>.*?</think>", "", ans)          # the vote is in the answer, never the reasoning


def queue_vote(question, text, n=3, frm="C3", name=None):
    import qwen_task
    body = ("C3 vote task. Read the TEXT and answer the QUESTION %d times independently, each time with exactly one word "
            "YES or NO; then give the majority and the count (e.g. YES 3/3). Copy, never guess.\n\nQUESTION: %s\n%s\nTEXT:\n%s"
            % (n, question, ("ITEM: %s\n" % name) if name else "", text))
    return qwen_task.add_task("C3 vote: " + " ".join(question.split())[:60], body, frm)


def vote(question, text, n=3, ask=None, name=None):
    """Ask n times (seeds 1..n) and tally. `ask(question, text, seed)` is injectable for tests; with no ask the
    question is queued for the qwen runner (the one door) and nothing calls the model here."""
    clean, _ = redact_lines(text.splitlines())
    text = "\n".join(clean)[-MAX_CHARS:]
    if ask is None:
        q = queue_vote(question, text, n, name=name)
        return dict(tally([]), votes=[], queued=q)
    votes = []
    for seed in range(1, n + 1):
        try:
            votes.append(parse_vote(ask(question, text, seed)))
        except Exception:               # a dead call is a spoiled ballot, never a guess
            votes.append(None)
    return dict(tally(votes), votes=votes)


def items(paths, lines=False, tail=None):
    """[(name, text)] from files / globs / '-' (stdin). --lines makes every non-empty line its own item."""
    out = []
    for p in paths:
        if p == "-":
            srcs = [("stdin", sys.stdin.read())]
        else:
            srcs = []
            for f in sorted(glob.glob(p)) or [p]:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    srcs.append((f, fh.read()))
        for name, text in srcs:
            if tail:
                text = "\n".join(text.splitlines()[-tail:])
            if lines:
                out += [("%s:%d" % (name, i), ln) for i, ln in enumerate(text.splitlines(), 1) if ln.strip()]
            else:
                out.append((name, text))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-q", "--question", required=True)
    ap.add_argument("paths", nargs="+", help="files, globs, or - for stdin")
    ap.add_argument("--votes", type=int, default=3, choices=[3, 4, 5])
    ap.add_argument("--lines", action="store_true", help="one label per line instead of per file")
    ap.add_argument("--tail", type=int)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--direct", action="store_true", help="call the router now (the worker's own use) instead of queueing")
    a = ap.parse_args(argv)
    ask = (lambda q, t, s: chat(q, t, s, model=a.model, host=a.host)) if a.direct else None  # noqa: E731
    for name, text in items(a.paths, a.lines, a.tail):
        r = vote(a.question, text, a.votes, ask, name=name)
        if r.get("queued"):
            print(json.dumps({"item": name, "queued": r["queued"]}) if a.json else "QUEUED Q%d  %s" % (r["queued"], name),
                  flush=True)
            continue
        if a.json:
            print(json.dumps(dict(r, item=name)), flush=True)
        else:
            print("%-5s %d/%d  %s%s" % (r["label"] or "NONE", max(r["yes"], r["no"]), a.votes, name,
                                        "  (%d spoiled)" % r["spoiled"] if r["spoiled"] else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
