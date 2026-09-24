"""CHAT INBOX - hand an issue from one chat to another without the owner approving every message.

Owner 2026-09-24: "make sure other chats get the messages when ... messages from one chat surface issues
that another chat needs to address. not sure how to manage it and dont want to have to approve it
everytime or be on it 24/7."

Why a file and not SendMessage: a live cross-session message is held for the owner's approval whenever
the receiving chat runs in a stricter permission mode, and it expires if nobody clicks. A file on this
machine needs no approval, survives restarts, and is read by the receiving chat on its own schedule.

Where: C:\\EdgeLog\\chat_inbox\\<CHAT>.jsonl - outside git, so no commits, no push races, visible to every
chat on the machine the moment it is written. <CHAT> is the chat's name as ListAgents prints it,
upper-cased with spaces and punctuation turned into '-' (e.g. "Paper: WB" -> PAPER-WB).

    python tools/chat_inbox.py read  NOISE                        # open items for the NOISE chat
    python tools/chat_inbox.py post  NOISE --from TV "text"       # hand an issue to NOISE
    python tools/chat_inbox.py done  NOISE 3 "what was done"      # close item 3 in NOISE's inbox
    python tools/chat_inbox.py all                                # every chat's open items (owner view)

THE RULE every chat follows (CLAUDE.md "Chat inbox"): run `read <your name>` when you start a task and
again before you finish one; act on anything addressed to you or reply by posting back; close what you
handle with `done`. When you find an issue another chat owns, `post` it there - and ALSO try
SendMessage, which is faster when it does get through.
"""
import argparse, datetime, json, os, re, sys

BOX = os.environ.get("EDGELOG_CHAT_INBOX", r"C:\EdgeLog\chat_inbox")


def norm(name):
    s = re.sub(r"[^A-Z0-9]+", "-", str(name or "").upper()).strip("-")
    return s or "UNKNOWN"


def path(chat):
    return os.path.join(BOX, norm(chat) + ".jsonl")


def load(chat):
    p = path(chat)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    return out


def save(chat, items):
    os.makedirs(BOX, exist_ok=True)
    tmp = path(chat) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    os.replace(tmp, path(chat))


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def show(chat, items, only_open=True):
    rows = [i for i in items if not (only_open and i.get("status") == "done")]
    if not rows:
        print(f"[{norm(chat)}] inbox empty")
        return
    print(f"[{norm(chat)}] {len(rows)} open item(s):")
    for i in rows:
        print(f"  #{i['id']}  {i['at']}  from {i['from']}:  {i['text']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read"); r.add_argument("chat"); r.add_argument("--all", action="store_true")
    p = sub.add_parser("post"); p.add_argument("chat"); p.add_argument("text"); p.add_argument("--from", dest="frm", required=True)
    d = sub.add_parser("done"); d.add_argument("chat"); d.add_argument("id", type=int); d.add_argument("note", nargs="?", default="")
    sub.add_parser("all")
    a = ap.parse_args()
    if a.cmd == "read":
        show(a.chat, load(a.chat), only_open=not a.all)
    elif a.cmd == "post":
        items = load(a.chat)
        nid = max([i["id"] for i in items] + [0]) + 1
        items.append({"id": nid, "at": now(), "from": norm(a.frm), "text": a.text.strip(), "status": "open"})
        save(a.chat, items)
        print(f"posted #{nid} to {norm(a.chat)}")
    elif a.cmd == "done":
        items = load(a.chat)
        hit = [i for i in items if i["id"] == a.id]
        if not hit:
            sys.exit(f"no item #{a.id} in {norm(a.chat)}")
        hit[0].update(status="done", done_at=now(), done_note=a.note)
        save(a.chat, items)
        print(f"closed #{a.id} in {norm(a.chat)}")
    else:
        if not os.path.isdir(BOX):
            print("no inboxes yet"); return
        for fn in sorted(os.listdir(BOX)):
            if fn.endswith(".jsonl"):
                show(fn[:-6], load(fn[:-6]))


if __name__ == "__main__":
    main()
