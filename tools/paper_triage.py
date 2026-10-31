"""B9: local model (Qwen) first read of papers/posts dropped in C:/EdgeLog/manager/papers/inbox/.

Each new file gets a one-page summary in papers/summaries/<name>.md with a 'worth Claude?' flag. UNVERIFIED model
output - Claude verifies before anything it says is used. Moves nothing; a file is skipped once its summary exists.
  python tools/paper_triage.py            # all new files
  python tools/paper_triage.py --force    # redo every file
ONE DOOR (MANAGER #222): no model call here. Each new file is filed as a Qwen task (tools/qwen_task.add_task) for
tools/qwen_runner.py, and its summaries/<name>.md gets a 'queued as Q<n>' stub so it is filed once.
"""
import datetime as dt, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = r"C:\EdgeLog\manager\papers"
INBOX, OUT = os.path.join(BASE, "inbox"), os.path.join(BASE, "summaries")
EXT = (".pdf", ".md", ".txt", ".html", ".htm")
Q = ("For a futures trader who backtests intraday strategies (ES/NQ, walk-forward + lockbox validation): "
     "1) what the piece claims, 2) the method and data, 3) how it was validated (out-of-sample? costs?), "
     "4) anything usable for our strategies or validation, 5) red flags. End with one line exactly "
     "'WORTH CLAUDE: YES' or 'WORTH CLAUDE: NO' and a short reason.")

def main():
    os.makedirs(INBOX, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    if "--direct" not in sys.argv:  # owner rule 10-30: no direct Qwen calls; switch to a Q task when tools/qwen_task.py lands
        print("paper_triage: direct Qwen path is OFF (owner rule 10-30); pass --direct to override"); return
    force = "--force" in sys.argv
    files = [f for f in sorted(os.listdir(INBOX)) if f.lower().endswith(EXT)]
    todo = [f for f in files if force or not os.path.exists(os.path.join(OUT, f + ".md"))]
    if not todo:
        print("paper_triage: nothing new in", INBOX); return
    import qwen_task
    for f in todo:
        src, out = os.path.join(INBOX, f), os.path.join(OUT, f + ".md")
        try:
            n = qwen_task.add_task("B9 paper first read: " + f[:60],
                                   "B9 first read of %s (read-only; one page max).\n%s\n"
                                   "Write the summary under ## RESULT, ending with the WORTH CLAUDE line." % (src, Q), "B9")
        except Exception as e:
            print("  FAILED to queue (retries next run):", type(e).__name__, str(e)[:160]); continue
        with open(out, "w", encoding="utf-8") as o:
            o.write("# %s\n\nWorth Claude: **?** - queued as Qwen task Q%d %s; the result lands in that task file.\n" %
                    (f, n, dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
        print("queued", f, "as Q%d" % n, flush=True)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
