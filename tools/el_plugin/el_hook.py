"""EDGE-LOG plugin hook (board B17). start / stop / status. Read-only: never posts, ships or edits."""
import json, os, subprocess, sys, urllib.request
REPO = os.environ.get("EL_REPO", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
INBOX = r"C:\EdgeLog\chat_inbox"

def run(*a):
    try:
        return subprocess.run(a, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=12).stdout.strip()
    except Exception as e:
        return "(%s)" % type(e).__name__

def chat_name(info):
    # EL_CHAT wins; else the session's custom title if it names a known inbox
    n = os.environ.get("EL_CHAT", "")
    known = {f[:-6].upper() for f in os.listdir(INBOX) if f.endswith(".jsonl")} if os.path.isdir(INBOX) else set()
    if not n:
        try:
            for line in open(info.get("transcript_path") or "", encoding="utf-8", errors="replace"):
                r = json.loads(line)
                if r.get("type") in ("custom-title", "agent-name"):
                    n = r.get("customTitle") or r.get("agentName") or n
        except Exception:
            pass
    return n.upper() if n.upper() in known else ""

def inbox(name):
    if not name:
        return "inbox: chat name unknown (set EL_CHAT) - run: python tools/chat_inbox.py all"
    out = run(sys.executable, "tools/chat_inbox.py", "read", name)
    return "\n".join(out.splitlines()[:12])

def ships():
    return "latest main: " + run("git", "log", "origin/main", "-3", "--format=%h %cr %s").replace("\n", " | ")[:400]

def ollama():
    try:
        v = json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=3)).get("version")
        return "local model: UP (Ollama %s)" % v
    except Exception:
        return "local model: DOWN (Ollama not answering on 11434)"

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        info = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        info = {}
    sys.stdout.reconfigure(encoding="utf-8")
    name = chat_name(info)
    if mode == "stop":
        if info.get("stop_hook_active"):
            return
        n = inbox(name)
        if name and "0 open" not in n:  # remind once, never block
            print(json.dumps({"systemMessage": "EDGE-LOG: open inbox items for %s before you finish:\n%s" % (name, n)}))
        return
    text = "\n".join(x for x in (inbox(name), ships(), ollama()) if x)
    if mode == "start":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "EDGE-LOG status:\n" + text}}))
    else:
        print(text)

if __name__ == "__main__":
    main()
