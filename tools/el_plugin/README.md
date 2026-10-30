# EDGE-LOG Claude plugin (board B17) - draft, owner installs

Every chat gets: open inbox items + latest ships + local model up/down at session start; a reminder (never a block) at the end if inbox items are still open; `/el-status` on demand. Read-only.

Install (owner): `claude plugin install C:/Users/xride/OneDrive/Desktop/EDGE-LOG/tools/el_plugin` (or add the folder as a local marketplace). Optional: set `EL_CHAT=<inbox name>` per chat; otherwise the chat's title is used when it matches an inbox.
