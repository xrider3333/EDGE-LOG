"""B9: local model (Qwen) first read of papers/posts dropped in C:/EdgeLog/manager/papers/inbox/.

Each new file gets a one-page summary in papers/summaries/<name>.md with a 'worth Claude?' flag. UNVERIFIED model
output - Claude verifies before anything it says is used. Moves nothing; a file is skipped once its summary exists.
  python tools/paper_triage.py            # all new files
  python tools/paper_triage.py --force    # redo every file
"""
import datetime as dt, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_llm as L

BASE = r"C:\EdgeLog\manager\papers"
INBOX, OUT = os.path.join(BASE, "inbox"), os.path.join(BASE, "summaries")
EXT = (".pdf", ".md", ".txt", ".html", ".htm")
Q = ("For a futures trader who backtests intraday strategies (ES/NQ, walk-forward + lockbox validation): "
     "1) what the piece claims, 2) the method and data, 3) how it was validated (out-of-sample? costs?), "
     "4) anything usable for our strategies or validation, 5) red flags. End with one line exactly "
     "'WORTH CLAUDE: YES' or 'WORTH CLAUDE: NO' and a short reason.")

def main():
    os.makedirs(INBOX, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    force = "--force" in sys.argv
    files = [f for f in sorted(os.listdir(INBOX)) if f.lower().endswith(EXT)]
    todo = [f for f in files if force or not os.path.exists(os.path.join(OUT, f + ".md"))]
    if not todo:
        print("paper_triage: nothing new in", INBOX); return
    L.ping()
    for f in todo:
        print("reading", f, flush=True)
        try:
            r = L.summarize([os.path.join(INBOX, f)], Q, words=350)
            body = L.format_summary(r) if hasattr(L, "format_summary") else str(r)
        except Exception as e:
            print("  FAILED (retries next run):", type(e).__name__, str(e)[:160]); continue
        flag = "YES" if "WORTH CLAUDE: YES" in body.upper() else ("NO" if "WORTH CLAUDE: NO" in body.upper() else "?")
        with open(os.path.join(OUT, f + ".md"), "w", encoding="utf-8") as o:
            o.write("# %s\n\nWorth Claude: **%s** - Qwen first read %s, UNVERIFIED.\n\n%s\n" %
                    (f, flag, dt.datetime.now().strftime("%Y-%m-%d %H:%M"), body))
        print("  ->", flag, flush=True)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
