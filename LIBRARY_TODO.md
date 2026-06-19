# EDGELOG Library tab — TODO / backlog

Tracked here so it survives across sessions. Newest ideas on top.

## Open
- [ ] **Package the runner as a desktop app (.exe / tray app).** PyInstaller-wrap
      `api/runner.py` into `AugurRunner.exe`: system-tray icon, auto-start with
      Windows, connected/disconnected status dot, pause/convert menu — kills the
      `.bat` + console-window friction. Optional later: PWA "install" of the site for
      an app-like iPhone/desktop launcher. (Engine/perf unchanged; UI stays in the
      website.)
- [ ] **Set / show the active strategy** in Library (augur_config.json `active_strategy`)
      + one-click "use in Builder" (quick-launch, pre-filled).
- [ ] **Per-strategy stats inline** — best/last run + PF pulled from run history into
      the row or a detail panel.
- [ ] **Auto-detect instrument from CSV filename/symbol on upload** (AUGUR TODO #10).
- [ ] **Per-master actions** — select + per-master auto-pull toggle + delete (masters
      currently read-only; strategies already have an action bar).
- [ ] **Expand a strategy** to view its params / preset tiers (currently just a SCOPES
      count).

## Done (recent)
- [x] v24.3 Pine provenance badge (qwen/claude/claude-review/bundled/scaffold/hand);
      download buttons grouped by DELETE; masters title moved inside its tile.
- [x] v24.2 per-click AI provider toggle; Claude REVIEW → APPLY flow.
- [x] v24.1 MAKE PINE defaults to free local qwen; cost shown on button.
- [x] v24.0 STRATEGY header sorts by # or name; no fade-flash on select.
- [x] v23.8 command channel (download/delete/add/make-pine); clickable headers.
- [x] v23.7 action bar + compact table + py/pine chips + date-added + last-ran.
