"""morning_digest.py -- B7 (AUTOMATIONS.md): one plain-words page for the owner each morning: every
chat inbox's open items + the open board's rows that are not done, ready by 06:00 MST.

PYTHON COMPUTES, THE MODEL COMMENTS (tools/local_llm.py rule). The FACTS block is counted and quoted
by this script from the files; the SUMMARY block is the local model's reading of those facts, marked
unverified, and is left out (with a line saying why) when no model answers.

Inputs (read-only):  C:/EdgeLog/chat_inbox/*.jsonl  (tools/chat_inbox.py)
                     C:/EdgeLog/manager/open_board/board.md  (the board copy Qwen reads)
Output:              C:/EdgeLog/manager/digest/digest-YYYY-MM-DD.md  (+ digest-latest.md)
Model:               Strata (127.0.0.1:8080/v1) when it lists its model, else Ollama (local_llm.MODEL),
                     else none. --no-model skips it.

    python tools/morning_digest.py [--date YYYY-MM-DD] [--no-model] [--out-dir DIR]
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chat_inbox  # noqa: E402

HOME = os.environ.get("EDGELOG_HOME", r"C:\EdgeLog")
BOARD = os.path.join(HOME, "manager", "open_board", "board.md")
OUT_DIR = os.path.join(HOME, "manager", "digest")
STRATA_URL = "http://127.0.0.1:8080/v1"
STRATA_MODEL = "qwen3.8-flash-next-gyro-gyro-s"
STALE_H = 24          # an open inbox item older than this is called out
TEXT_CAP = 220        # chars of each item quoted in FACTS
MODEL_INPUT_CAP = 24000

ROW_RE = re.compile(r"^- \*\*(item|test) (\d+)\*\* \[(\w+)\] (.*?)(?: \| who: (.*?))?(?: \| date: ([\d-]+))?\s*$")
# NOTE (owner rule): account numbers / long ids never leave a file in clear.
LONG_ID = re.compile(r"\d{8,}")


def _clean(s, cap=TEXT_CAP):
    s = LONG_ID.sub("<id>", " ".join(str(s or "").split()))
    return s if len(s) <= cap else s[:cap - 1] + "…"


def read_inboxes(now):
    """{chat: [open items]}, each item with an 'age_h'. Unparsable times count as fresh."""
    out = {}
    for chat in chat_inbox.known():
        rows = []
        for it in chat_inbox.load(chat):
            if it.get("status") == "done":
                continue
            try:
                at = datetime.datetime.strptime(it.get("at", ""), "%Y-%m-%d %H:%M")
                age = (now - at).total_seconds() / 3600.0
            except ValueError:
                age = 0.0
            rows.append(dict(it, age_h=age))
        if rows:
            out[chat] = rows
    return out


def read_board(path=BOARD):
    """Board rows not marked done: [{kind, n, status, title, who, date, statusText}]."""
    if not os.path.exists(path):
        return None
    rows, cur = [], None
    with open(path, encoding="utf-8") as f:
        for ln in f:
            m = ROW_RE.match(ln.rstrip("\n"))
            if m:
                cur = {"kind": m.group(1), "n": int(m.group(2)), "status": m.group(3),
                       "title": m.group(4).strip(), "who": (m.group(5) or "").strip(),
                       "date": m.group(6) or "", "statusText": ""}
                rows.append(cur)
            elif cur and ln.strip().startswith("- statusText:"):
                cur["statusText"] = ln.split(":", 1)[1].strip()
    return [r for r in rows if r["status"] != "done"]


def facts(day, now, inboxes, board):
    L = [f"# Morning digest {day}", "", f"Made {now:%Y-%m-%d %H:%M} MST from the inbox files and the board copy.", ""]
    needs = [r for r in (board or []) if r["status"] == "block" or "you" in r["who"].lower()]
    L.append("## Needs you")
    if needs:
        for r in sorted(needs, key=lambda r: r["n"]):
            L.append(f"- {r['kind']} {r['n']}: {_clean(r['title'], 120)} - {_clean(r['statusText'], 120) or r['status']}")
    else:
        L.append("- nothing on the board is waiting on you")
    L.append("")
    total = sum(len(v) for v in inboxes.values())
    L.append(f"## Inboxes: {total} open item(s) in {len(inboxes)} chat(s)")
    for chat in sorted(inboxes, key=lambda c: -len(inboxes[c])):
        rows = inboxes[chat]
        stale = sum(1 for r in rows if r["age_h"] > STALE_H)
        fresh = sorted((r for r in rows if r["age_h"] <= STALE_H), key=lambda r: r["age_h"])
        L.append(f"- **{chat}**: {len(rows)} open, {len(fresh)} new in the last {STALE_H} h")
        # the newest first: the old open items are mostly standing orders nobody closes
        for r in fresh[:3]:
            L.append(f"  - #{r['id']} {r.get('at', '')} from {r.get('from', '?')}: {_clean(r.get('text'))}")
        if len(fresh) > 3:
            L.append(f"  - (+{len(fresh) - 3} more new)")
    L.append("")
    if board is None:
        L.append(f"## Board: not found ({BOARD})")
    else:
        L.append(f"## Board: {len(board)} row(s) not done")
        for st in ("block", "run", "open"):
            sel = [r for r in board if r["status"] == st]
            if sel:
                L.append(f"- {st}: " + "; ".join(f"{r['kind']} {r['n']} {_clean(r['title'], 60)}" for r in sorted(sel, key=lambda r: r["n"])))
        other = [r for r in board if r["status"] not in ("block", "run", "open")]
        if other:
            L.append("- other: " + "; ".join(f"{r['kind']} {r['n']} [{r['status']}]" for r in other))
    L.append("")
    return L


def _strata_alive():
    try:
        with urllib.request.urlopen(STRATA_URL + "/models", timeout=10) as r:
            return STRATA_MODEL in r.read().decode("utf-8", "replace")
    except Exception:
        return False


def _ask_strata(prompt):
    body = json.dumps({"model": STRATA_MODEL, "max_tokens": 6000, "temperature": 0.2,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(STRATA_URL + "/chat/completions", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        txt = json.loads(r.read())["choices"][0]["message"].get("content")
    if not (txt or "").strip():   # its reasoning used the whole reply budget
        raise ValueError("empty answer")
    return txt


def summarize(fact_text):
    """(backend, text) or (None, reason). Never raises."""
    prompt = ("Below is today's status page for a trading-research project's owner. In 5-8 short plain "
              "bullets, say what most needs the owner's attention first and why, then what is moving. "
              "Use only what the page says; never invent numbers.\n\n" + fact_text[:MODEL_INPUT_CAP])
    try:
        if _strata_alive():
            return "Strata " + STRATA_MODEL, _ask_strata(prompt)
    except Exception as e:
        strata_err = f"Strata failed ({type(e).__name__})"
    else:
        strata_err = "Strata off"
    try:
        import local_llm
        if not local_llm.ping():
            return None, strata_err + "; Ollama off"
        d = local_llm.generate(prompt, num_predict=900, timeout=900)
        txt = str((d.get("response") if isinstance(d, dict) else d) or "").strip()
        if not txt:
            return None, strata_err + "; Ollama gave an empty answer"
        return "Ollama " + local_llm.MODEL, txt
    except Exception as e:
        return None, strata_err + f"; Ollama failed ({type(e).__name__})"


def build(day, now, use_model=True, board_path=BOARD):
    L = facts(day, now, read_inboxes(now), read_board(board_path))
    if use_model:
        backend, txt = summarize("\n".join(L))
        if backend:
            txt = LONG_ID.sub("<id>", re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip())[:6000]
            L += [f"## Summary ({backend}, unverified - the facts above are the record)", "", txt, ""]
        else:
            L += [f"## Summary: none ({txt})", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date")
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DIR)
    a = ap.parse_args(argv)
    now = datetime.datetime.now()
    day = a.date or now.strftime("%Y-%m-%d")
    text = build(day, now, use_model=not a.no_model)
    os.makedirs(a.out_dir, exist_ok=True)
    for name in (f"digest-{day}.md", "digest-latest.md"):
        tmp = os.path.join(a.out_dir, name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, os.path.join(a.out_dir, name))
    print(f"digest written: {os.path.join(a.out_dir, f'digest-{day}.md')} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
