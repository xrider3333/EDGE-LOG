# EDGE-LOG rules for Cline (checked in; the long form is tools/cline/settings_template/clinerules.md)
- Read C:\EdgeLog\manager\qwen_tasks\WORKING_RULES.md before every task, then C:\EdgeLog\manager\qwen_tasks\NEXT.md for the loop.
- This checkout (C:\Users\xride\OneDrive\Desktop\EDGE-LOG) is READ-ONLY: never edit, commit or push here. Changes go in a worktree: python tools/wt.py new <short-name>.
- Never git push, never commit on main, never lower the 900-trial budget, never start a validate / box deploy / anything touching Webull, NinjaTrader or an account. Write the command and ask.
- Never type or print passwords, API keys, tokens or PINs. Never delete anything under C:\EdgeLog\.
- index.html is ~50k lines: search C:\EdgeLog\manager\qwen_tasks\INDEX_MAP.md first, then read a range (max 1500 lines). Never read it whole.
- PYTHON COMPUTES, YOU COMMENT: every number comes from a command you ran and show. The four numbers: ROC %/yr at $30k, DD5, DD % from peak, Sortino.
- Models (router http://127.0.0.1:11435/v1, one in VRAM at a time): 1.STRATA qwen3.8-flash:125b-256k (owner's call), 2.qwen3.8:27b-48k (default), 3./4./5. qwen3.6:35b at 128k/64k/32k.
- Board + inbox + Q tasks: use the edgelog MCP tools (board_read, inbox_read, task_list, task_result, inbox_post - posts are always from QWEN). Fallback: python tools/chat_inbox.py read QWEN.
- Keep answers short; say what you did not check; do not ask questions mid-task; finish by writing ## RESULT into the Q file.
