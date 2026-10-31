# C4 Qwen edit plan template

Use with `python tools/qwen_edit.py plan <worktree> <plan.md> --from <LANE>`, then `python tools/qwen_edit.py check <id>` after each RESULT.

Rules: the first non-heading line is the goal. Then one `## FILE <path>` section per file, at most 8. Each path is relative to the worktree root and stays inside it. Each section says the exact change and has a `Tests:` line of pytest ids. Qwen edits the files in the order listed, one per Q task. Each file gets 2 tries, then the plan goes back to the lane. The combined patch lands in `C:\EdgeLog\qwen_edit\<id>.patch`. The lane reviews it, applies it and ships it.

```
Goal: <one line - what the whole change does>

## FILE tools/example.py
<exact change: which function, what to add/remove, edge cases>
Tests: tests/test_example.py::test_new_case tests/test_example.py

## FILE tests/test_example.py
<exact change>
Tests: tests/test_example.py
```
