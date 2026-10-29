# B16 auto-recovery: hooks DRAFT (owner applies - nothing here is installed)

The script half of B16 is live: `tools/auto_recovery.py` scans every detached job launched in the last 3 days
(`C:\EdgeLog\detach\*.cmd` + its log) and the morning digest prints a "Dead or failed jobs" section from it
(DIED = killed at sign-out / log stopped before a push; FAILED = non-zero exit or a ship that ended unpushed;
each with its exact relaunch line in `python tools/auto_recovery.py`). It never relaunches by itself: the
worktree may have moved on, so the owning chat reads the log first.

The hook half needs Claude Code settings, which only the owner changes. Draft for `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command",
        "command": "python C:/Users/xride/OneDrive/Desktop/EDGE-LOG/tools/auto_recovery.py --days 1"}]}
    ],
    "PreCompact": [
      {"hooks": [{"type": "command",
        "command": "python C:/Users/xride/OneDrive/Desktop/EDGE-LOG/tools/chat_inbox.py all"}]}
    ]
  }
}
```

- **SessionStart**: every chat sees the dead or failed jobs from the last day when it opens (stdout is added to its context).
- **PreCompact**: the open inbox items are printed into the transcript just before a compaction, so the summary keeps them.
- Neither hook writes anything. Remove the block to undo.
