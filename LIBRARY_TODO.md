# EDGELOG Library tab — TODO / backlog

Tracked here so it survives across sessions. Newest ideas on top.

## Open — backend wave (needs new runner command handlers)
- [ ] **Multi-instrument master pull** — "start a pull" for GC (gold), YM (Dow), CL, RTY,
      etc. Instruments already exist in optimizer.INSTRUMENTS (GC=F, YM=F…); need a
      `pull_master {instrument, timeframe, session}` command that does the initial Yahoo
      pull via the augur_refresh shim + save_master_csv, then a "+ PULL MASTER" picker in
      the Library masters pane. (Yahoo only gives ~recent intraday history — see data note.)
- [ ] **Per-master actions** — select a master → toggle its auto-pull (writes
      augur_config autorefresh.masters[key]) + delete master. Masters pane still read-only.
- [ ] **Order-flow / Time-&-Sales enrichment** (Databento, paid) — AUGUR TODO #23.

## Open — frontend / other
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
- [x] v24.4 download/AI dropdown menus; SET ACTIVE + USE IN BUILDER quick-launch;
      inline per-strategy stats; ROADMAP checklist tab.
- [x] v24.3 Pine provenance badge (qwen/claude/claude-review/bundled/scaffold/hand);
      download buttons grouped by DELETE; masters title moved inside its tile.
- [x] v24.2 per-click AI provider toggle; Claude REVIEW → APPLY flow.
- [x] v24.1 MAKE PINE defaults to free local qwen; cost shown on button.
- [x] v24.0 STRATEGY header sorts by # or name; no fade-flash on select.
- [x] v23.8 command channel (download/delete/add/make-pine); clickable headers.
- [x] v23.7 action bar + compact table + py/pine chips + date-added + last-ran.
