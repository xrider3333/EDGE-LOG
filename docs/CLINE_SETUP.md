# Cline setup (owner's Qwen worker in VS Code) - versioned copy

Board rows C26 (settings in the repo) and C27 (Cline -> edgelog MCP). Scope: manager/scopes/AI-STACK-SCOPE.md P7, P6.

## What is where
| Piece | Live file (not versioned) | Repo copy |
|---|---|---|
| Rules Cline reads every task | `Documents\Cline\Rules\edgelog.md` + repo root `.clinerules` (Cline reads both) | `.clinerules`, `tools/cline/settings_template/clinerules.md` |
| MCP servers | `~/.cline/data/settings/cline_mcp_settings.json` | `tools/cline/settings_template/cline_mcp_settings.json` |
| Model list (5 names) | `~/.cline/data/settings/models.json` | `tools/cline/settings_template/models.json` |
| Router URL | `~/.cline/data/settings/providers.json` (`baseUrl`; the key stays untouched) | `tools/cline/settings_template/providers.json` |
| Auto-approve, checkpoints, default model | `~/.cline/data/globalState.json` | `tools/cline/settings_template/global_state.json` |
| Task loop | `Documents\Cline\Workflows\next.md` -> `C:\EdgeLog\manager\qwen_tasks\NEXT.md` | (manager folder, not the repo) |

Backups from earlier hand edits already sit beside the live files (`*.bak-1028`, `*.bak-1030`).

## The template in one breath
- Router `http://127.0.0.1:11435/v1` (one door; it auto-launches Strata and sends 3./4./5. to Strata while it is up).
- Models: `1.STRATA qwen3.8-flash:125b-256k` (owner's call, 256k), `2.qwen3.8:27b-48k` (default for plan + act), `3.qwen3.6:35b-128k`, `4.qwen3.6:35b-64k`, `5.qwen3.6:35b-32k`. One model in VRAM at a time.
- Auto-approve: read files (inside and outside the workspace - the manager folder is outside), safe commands, MCP tools. Edits, "all commands" and the browser need a click. 200 auto-approvals per task.
- Checkpoints ON: a bad edit is one click back.
- MCP `edgelog`: the four read tools auto-approve; `inbox_post` asks first (it writes to a lane's inbox, sender always QWEN).

## Apply it
```
python tools/cline/apply_settings.py              # dry run: unified diff per file, writes nothing
python tools/cline/apply_settings.py --apply      # Cline CLOSED first; writes after <file>.bak-<stamp>
```
Then restart VS Code / Cline. `--apply` merges: other MCP servers, other globalState keys and the API key are kept as they are.

## MCP: Cline -> edgelog (C27)
Server: `tools/edgelog_mcp.py` (on main since a1a703bb; AUTOMATIONS row B4 covers the ship note + the memory-read tool, the server itself is live and already registered for Claude). Tools: `inbox_read {lane, all?}`, `inbox_post {to, text}`, `board_read {grep?, max_chars?}`, `task_list {}`, `task_result {name}`. Full description: docs/LOCAL_LLM.md.
Cline entry (what the template writes):
```json
"edgelog": {
  "command": "C:\\Users\\xride\\AppData\\Local\\Microsoft\\WindowsApps\\python3.13.exe",
  "args": ["C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG\\tools\\edgelog_mcp.py"],
  "env": {"EDGELOG_HOME": "C:\\EdgeLog"},
  "disabled": false,
  "autoApprove": ["inbox_read", "board_read", "task_list", "task_result"]
}
```
It is stdio, stdlib-only, and loads no model. Check in Cline: MCP Servers panel -> edgelog -> green dot, then ask "list open Q tasks" (task_list).

## Not in the template on purpose
- The API key in providers.json (any value works for the router; never versioned).
- `Documents\Cline\Rules\edgelog.md` (owner-edited; `.clinerules` in the repo root carries the same rules in short form and Cline reads both).
