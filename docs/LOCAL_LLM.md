# LOCAL MODEL - hand long reading to the local qwen, keep it out of your context

Owner 2026-10-11: "set up your local Qwen so the chats can hand it long reading (logs, papers)
and save tokens". The model is qwen3.8:27b (27B dense, Q4, 17 GB; replaced qwen3.6 on 2026-10-11 after a race: more accurate, 3-4x slower) in Ollama at
127.0.0.1:11434. Code: `tools/local_llm.py` (CLI) and `tools/local_llm_mcp.py` (MCP server,
same functions). Every call is appended to `C:\EdgeLog\local_llm.log` (question + answer,
never the file text).

## The rule

**PYTHON COMPUTES, THE MODEL COMMENTS.** Its answer is a pointer to where to look, never a
fact. Every answer is printed under
`LOCAL MODEL SUMMARY (qwen3.8, unverified - quote nothing from it as fact)`. If it says "the
push failed at PAPERPROBE", open the log and quote the line yourself.

## Use it for

- Long logs: "did the ship land, and if not why", "which gate failed first", "what did the
  runner do overnight" - with `--tail` / `--grep-first` to cut the file down first.
- Papers (PDF) and long docs: "how did they validate", "what data, what period".
- Big CSV / JSON as text, first-pass screening, drafts of a summary you will check.

## Do NOT use it for

- Numbers you will quote, verdicts, rankings, sizing - compute those in pandas
  (`--csv` triage already does that split).
- Code that ships, reviews you rely on, anything the owner will read as fact.
- Files whose point is a secret (key files, configs). Lines that look like keys / tokens /
  passwords / ntfy topics are redacted before sending (the header prints how many), but
  do not hand it a key file on purpose.

## Speed - check before a big read

`--status` shows whether the model is loaded and whether it is on the GPU.
Measured 2026-10-11 with Ollama on **CPU only** (the GPU was not detected at that day's
Ollama start; on 10-09/10-10 it was): reading ~24 tokens/s, writing ~4-8 tokens/s,
a 774-byte log answered in ~31 s, a 7 KB log in ~98 s. At that speed a full 24k-token
chunk is ~15+ minutes, so on CPU keep a read to a few KB with `--tail` / `--grep-first`.
A cold start (weights not loaded) adds 1.5-3.5 min. If `--status` says CPU ONLY,
restarting Ollama usually brings the GPU back.

## Commands

```
python tools/local_llm.py --status
python tools/local_llm.py --summarize C:\EdgeLog\manager\ship_ledgerbar_1011.log --tail 80 --ask "did it land, and if not why"
python tools/local_llm.py --summarize "C:\EdgeLog\manager\ship_*_1010*.log" --grep-first "FAIL|error|pushed" --ask "which ships failed and at which gate"
python tools/local_llm.py --summarize paper.pdf --ask "how did they validate out of sample" --words 150
python tools/local_llm.py --summarize big.log --tail 2000 --ask "..." --dry-run     # sizes, redactions, chunks; sends nothing
```

Options: `--words N` (answer cap, default 200), `--tail N` (last N lines of each file),
`--grep-first PATTERN` (regex, case-insensitive; matching lines +-3 lines, numbered `L123:`),
`--chunk-tokens` (default 24000, char-estimated at 3.5 chars/token), `--max-chunks`
(default 12 - a bigger read is refused, narrow it instead), `--timeout` (seconds per model
call, default 1800). Globs are expanded by the tool (PowerShell does not). PDFs need pypdf
(installed for python3.13); without it they are skipped with a note.

Exit code 2 and one line on stderr when Ollama is down:
`Ollama not reachable at 127.0.0.1:11434 - start Ollama`.

Every call sends `num_ctx` 32768 and `think: false`. Do not change num_ctx per call: Ollama
reloads the 17 GB weights when it changes.

## MCP (for the chats)

Tools: `local_summarize {paths: string[], question: string, words?, tail?, grep?}` and
`local_status {warm_test?: bool}`. Errors come back as isError text, never as a crash.

Registration - MANAGER runs this once after review (user scope, every chat gets it):

```
claude mcp add --scope user local-llm -- "C:\Users\xride\AppData\Local\Microsoft\WindowsApps\python3.13.exe" "C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\local_llm_mcp.py"
```

The `WindowsApps\python3.13.exe` alias survives Store updates of Python; the versioned path
(`C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe`)
works too but breaks on the next Python update. Check with `claude mcp list`. A long read
can outlast a client's tool timeout - narrow the read, or warm the model first with
`local_status`.

## MCP: edgelog (inbox, board, Qwen tasks)

`tools/edgelog_mcp.py` (server `edgelog`, same stdio wire as local_llm_mcp). Tools:
`inbox_read {lane, all?}`, `inbox_post {to, text}` (sender always QWEN, existing inboxes only,
1-4000 chars), `board_read {grep?, max_chars?}` (default cap 20000), `task_list {}`,
`task_result {name}` (basename .md/.txt in `manager\qwen_tasks` only). Paths from
`EDGELOG_HOME` (default `C:\EdgeLog`); inbox folder `EDGELOG_CHAT_INBOX` if set.

Registration - MANAGER runs this once after review (not registered yet):

```
claude mcp add --scope user edgelog -- "C:\Users\xride\AppData\Local\Microsoft\WindowsApps\python3.13.exe" "C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\edgelog_mcp.py"
```

For Cline / VS Code, the same command and args go under the `edgelog` server entry.
