# -*- coding: utf-8 -*-
"""Build NOISE_1_9_HSQ304H.py from the shipped HSQ304 file: the verification frame is FIXED at 60 minutes and only
the squeeze length and threshold stay open (9 cells), so every cell the validate can crown is an hourly squeeze."""
import io
import re

SRC = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\noisehourly\augur_strategies\NOISE_1_9_HSQ304.py"
DST = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\noisehourly\augur_strategies\NOISE_1_9_HSQ304H.py"
s = io.open(SRC, encoding="utf-8").read()

head_end = s.index('"""', 3) + 3
doc = '''"""
NOISE 1.9 HSQ304H -- the LIVE crown keeping only trades taken during an HOURLY squeeze (hourly frame fixed).

ROUND 58 (2026-09-14, NOISE.md). Owner: "auto validate anything that needs the auto validation." The live crown
with the textbook hourly squeeze filter (60-minute frame, length 20, ratio 1.0) reads profit factor 2.351 over
615 trades on a continuous replay and is on EL only as a single validate (#390), which saves no walk-forward
years, so it cannot sit beside the other NOISE rows on COMPARE > EXPLORE. Three neighbourhood Auto-Validates that
contained it (#385, #387 on the live crown; #386 on #243) all crowned a 30-MINUTE squeeze instead, where more
trades qualify.

This file keeps the question inside the hourly frame: the verification timeframe is FROZEN at 60 minutes and only
the squeeze length (16 / 20 / 24) and threshold (0.85 / 1.0 / 1.15) are open - 9 cells, the textbook setting at
the centre and as every default. The fence was drawn after the hourly frame was seen to beat the 30-minute one on
these same years, so this validate cannot un-see that selection; its walk-forward folds and overfit test still
judge the choice among hourly settings. Parity-checked: the centre reproduces 615 trades / $139,997.

READ THE LOCKBOX CONTINUOUSLY - the saved strip is a cold-restart reload for NOISE.
"""'''
s = doc + s[head_end:]
s = s.replace('"NOISE 1.9 live crown x hourly squeeze filter (neighbourhood)"',
              '"NOISE 1.9 live crown x hourly squeeze filter (hourly frame fixed)"')
s = re.sub(r"_ADMISSIBLE = \{[^}]*\}", "_ADMISSIBLE = {'gate_len': [16, 20, 24], 'gate_ratio': [0.85, 1.0, 1.15]}", s, count=1)
s = re.sub(r"_CENTER = \{[^}]*\}", "_CENTER = {'gate_len': 20, 'gate_ratio': 1.0}", s, count=1)
s = re.sub(r'    "gate_tf_min": \{[^\n]*\n', "", s, count=1)
s = s.replace("27-cell neighbourhood", "9-cell hourly neighbourhood")
s = s.replace('int(round(float(p["gate_tf_min"])))', "60")
assert "gate_tf_min" not in s.split('"""', 2)[2], "gate_tf_min still referenced in code"
io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print("wrote", DST)
