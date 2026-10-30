"""C1 QWEN-FIRST CASCADE (Open Board C1, MANAGER #196). Qwen (model 5 via the router at 127.0.0.1:11435/v1) tries a task first;
a CHECK - never the model - decides whether its answer stands or Claude must look.

    from qwen_cascade import cascade, json_check, pydantic_check, pytest_check
    r = cascade(prompt, check=pydantic_check(contracts.InboxItem), tries=3)
    r -> {"ok": bool, "answer": str, "tries": n, "escalate": bool, "why": [per-try reasons], "model": ...}

Checks are plain callables answer -> (ok, reason). Built in: json_check(required_keys), pydantic_check(Model) (JSON answer
validated by a model, e.g. tools/contracts.py), pytest_check(cmd) (runs a test command on a file the caller wrote from the
answer), regex_check(pattern). Each failed try feeds the reason back to Qwen; after `tries` failures escalate=True and the
caller hands the task to Claude. Qwen output stays UNVERIFIED unless its check passed; numbers and verdicts that ship still
need Claude (memory: local AI is a screener).

CLI (one-shot): python tools/qwen_cascade.py "prompt" [--json-keys a,b] [--tries 3]   exit 0 = Qwen answer passed, 2 = escalate
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request

ROUTER = "http://127.0.0.1:11435/v1"
MODEL = "5.qwen3.6:35b-32k"


def _chat(messages, model=MODEL, url=ROUTER, timeout=600):
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.2, "stream": False}).encode()
    req = urllib.request.Request(url + "/chat/completions", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"] or ""


def _strip(ans):
    """Drop a <think> block and a ``` fence so checks see the payload."""
    ans = re.sub(r"(?s)<think>.*?</think>", "", ans).strip()
    m = re.search(r"(?s)```(?:\w+)?\n(.*?)```", ans)
    return (m.group(1) if m else ans).strip()


def json_check(required=()):
    def chk(ans):
        try:
            d = json.loads(ans)
        except ValueError as e:
            return False, f"not valid JSON: {e}"
        miss = [k for k in required if not isinstance(d, dict) or k not in d]
        return (not miss), (f"missing keys {miss}" if miss else "json ok")
    return chk


def pydantic_check(model):
    def chk(ans):
        try:
            model.model_validate(json.loads(ans))
            return True, "schema ok"
        except Exception as e:  # ValueError / ValidationError
            return False, f"schema: {str(e).splitlines()[0][:300]}"
    return chk


def regex_check(pattern):
    def chk(ans):
        return (bool(re.search(pattern, ans)), f"must match /{pattern}/")
    return chk


def pytest_check(write_answer, cmd, timeout=300):
    """write_answer(ans) puts the answer where the tests read it; cmd = the test command (list)."""
    def chk(ans):
        write_answer(ans)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        tail = (p.stdout + p.stderr).strip().splitlines()[-15:]
        return p.returncode == 0, "tests pass" if p.returncode == 0 else "tests failed:\n" + "\n".join(tail)
    return chk


def cascade(prompt, check, tries=3, system=None, chat=_chat):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    why, ans = [], ""
    for i in range(1, tries + 1):
        try:
            raw = chat(msgs)
        except Exception as e:
            why.append(f"try {i}: model unreachable ({type(e).__name__}: {e})")
            return {"ok": False, "answer": "", "tries": i, "escalate": True, "why": why, "model": MODEL}
        ans = _strip(raw)
        ok, reason = check(ans)
        why.append(f"try {i}: {reason}")
        if ok:
            return {"ok": True, "answer": ans, "tries": i, "escalate": False, "why": why, "model": MODEL}
        msgs += [{"role": "assistant", "content": raw},
                 {"role": "user", "content": f"That failed the check: {reason}\nFix it and answer again, payload only."}]
    return {"ok": False, "answer": ans, "tries": tries, "escalate": True, "why": why, "model": MODEL}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--json-keys", default=None)
    ap.add_argument("--regex", default=None)
    ap.add_argument("--tries", type=int, default=3)
    a = ap.parse_args(argv)
    chk = (json_check([k for k in a.json_keys.split(",") if k]) if a.json_keys is not None
           else regex_check(a.regex) if a.regex else (lambda s: (bool(s.strip()), "non-empty")))
    r = cascade(a.prompt, chk, tries=a.tries)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
