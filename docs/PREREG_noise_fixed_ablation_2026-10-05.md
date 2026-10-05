# PRE-REGISTRATION (DRAFT for MANAGER) - which part of the 09-27 NOISE "fixed" package carries it? (2026-10-05)

Custom ML queue item 2 under MANAGER #50 (MANAGER asked: the 09-27 package read ~109-112 WF ROC at $30k against #422's
85, and NOISE round 69 has now shown its compression WEIGHT alone does not carry that). Walk-forward ONLY. The package's
lockbox was read on 09-27 (round 61 / run #457), so no lockbox is read here and a pass can only ever become a forward
no-order shadow. The only numbers computed before this draft are the feature-only counts below (no P&L read).

## Map placement first (docs/MDL_MAP_R1.md)
A re-sizing of #463's NOISE leg: it must beat PLAIN EXTRA NOISE (the same leg scaled to the same mean size) inside
BOOK #463 (WF 93.8 / Sortino 3.82 at $30k). Standalone ROC at $30k is leverage-free, so a standalone #422 read cannot
tell a tilt from extra size; the book read can. Plausible: the package's standalone WF gain (~109 vs 85) is far above
the extra-NOISE line, and book round 58 found the NOISE leg the one place re-sizing has shown anything real.

## The package (frozen 09-27, ml_keel.compression_sizes with v12's fixed settings; no model)
On top of #422's own sizes (1x, or 1.75x in its compressed hours): KEEL's 60-minute squeeze (sq60_on) x1.5; Friday
entries x1.5; FOMC pre-statement entries (statement day, entry before 14:00 ET) x0.5; product capped at 3.

**Feature-only counts (BOOK #463's NOISE leg, NQ 5m RTH no-adjust, WF 2016-07-01..2025-06-29, 2,797 trades):**
| part | WF trades tilted | 2011-01..2016-06 block |
|---|---|---|
| squeeze x1.5 | 308 | 245 |
| Friday x1.5 | 510 | 264 |
| FOMC x0.5 | 66 | 20 |
| full package | 820 (60 at 2.25x) | 479 |
The cap of 3 NEVER binds (largest package multiplier 2.25x; capped and uncapped are identical), so it is not a part.

## Arms (each is the #463 NOISE leg re-sized; every other leg and the book convention unchanged)
- **P** = the full package.
- Leave-one-out: **P-squeeze**, **P-Friday**, **P-FOMC**.
- Singles: **squeeze**, **Friday**, **FOMC** (each alone on #422).

## Yardstick and twin
BOOK #463 rebuilt from the identical leg runs (parity 93.8 / 3.82 asserted first, as in tools/noise_hedge_tilt.py).
For every arm its own twin = #463 with the NOISE leg scaled by c = mean(m x s) / mean(s) over WF trades (s = #422's own
size), i.e. plain extra NOISE at the same average size. Unified convention: daily-valued, years = (last - first) / 365.25.

## Bars for a part to "carry" the package (Stage A, walk-forward only), judged on its SINGLE arm
1. Beats its twin AND #463 on WF ROC at $30k AND Sortino.
2. Without Feb-Apr 2020: still beats its twin.
3. Beats its twin in >= 6 of the 9 WF years (July-June).
4. The untuned 2011-01..2016-06 block: beats its twin.
5. Aim, not shape: its WF ROC lead over its twin is above the 98.3rd percentile (95% over the three singles) of
   1,000 shuffles of its own multipliers across the WF NOISE trades, each shuffle scored against its own twin at its
   own c (seed 20261005).
6. >= 100 tilted WF trades. **FOMC has 66, so FOMC can never pass; it is reported only** (power stated now).

Attribution (reported regardless, never a bar): each leave-one-out drop = lead(P) - lead(P-part); P and every arm's
lead over its twin, ROC and Sortino; per-year leads.

## What a result means
- A part that passes 1-6 -> a forward no-order shadow judged by the paired sequential stop (running-mean form,
  docs/PREREG_paired_sequential_stop_2026-09-29.md) at 50 closed relevant trades. NOISE's sub-arm reader
  (tools/noise_fixed_subarm_read.py, c0787605) already tracks full / Friday / FOMC forward; a squeeze pass would add a
  squeeze sub-arm there via the NOISE lane. RUNBOARD entry either way.
- If P itself fails bar 1 inside the book, the 09-27 standalone gain was extra size, not aim, and the package is
  recorded dead as a book re-sizing (ledger + memory); NOISE's forward reader keeps running as NOISE decides.
- No variants (no other multipliers, days or thresholds). Nothing live or in the book changes without the owner.

## Priors to disclose
- Friday 1.5x FAILED the tilt guard in NOISE round 47.
- Book round 62 parts check (09-27, old convention, standalone): package 3.63 return/DD vs 3.33 without squeeze vs
  #422 2.82 - both the squeeze and Friday+FOMC looked positive standalone; never read against plain extra NOISE.
- The ML shuffle audit (09-30): no ML-sized leg beat its own shuffled sizes at the 95th pct in both stretches.
- NOISE round 69 (10-04): more weight on #422's own compressed hours LOWERS WF ROC at $30k (84.6 -> 80.9 at 2.25x).

---

## ADDENDUM 2026-10-05 07:15 MST - reviews folded in BEFORE any arm number (MANAGER #58 GO + #60; NOISE #59)
Binding changes:
1. **Disclosure (NOISE #59 A):** NOISE round 69b (10-04, eb4443a7, tools/r69b_noise_fixed_ablation.py) already ran this
   leave-one-out on #422 STANDALONE in walk-forward: #422 84.6; full package 109.0; minus squeeze 100.0, minus Friday
   100.4, minus FOMC 98.1; squeeze alone 82.5, Friday alone 96.6, FOMC alone 97.8. This round is therefore CONFIRMATORY
   for the parts and NEW ONLY at the book level, against plain extra NOISE. No standalone claim goes in the owner line.
2. **Power line first (MANAGER #58-1):** `python tools/noise_fixed_ablation.py power` prints each arm's own-size shuffle
   null (1,000) 50th / 95th / 98.3rd pct lead and the squeeze time-shift null BEFORE any arm's own P&L is read; POWER.txt
   is committed before `run`. Expectation stated now: leads of NOISE r70's size (~3 ROC points in the book) may sit
   inside these nulls and then cannot be told from luck.
3. **Friday calendar null (MANAGER #58-2):** four weekday placebos (Mon..Thu x1.5, each vs its own twin); Friday's bar 7
   = its lead beats all four.
4. **Squeeze time-shift null (MANAGER #58-3):** the sq60 flag read k sessions later at the same time of day, k uniform
   in 60..250 sessions, wrapped inside the WF sessions, 200 shifts (seed 20261006); squeeze's bar 8 = its lead above the
   null's 95th pct. The own-size shuffle stays as bar 5.
5. **Twin worst-drawdown window (NOISE #59 B):** for every arm, the lead over its twin with the TWIN's own worst WF
   drawdown window (peak..trough) removed - reported, and said plainly in the owner line if a lead lives there.
6. **Book to 2025-06-29 only (NOISE #59 C):** every leg is built 2010-06-07..2025-06-29 exactly as
   api.book_shadow.book463_valued_daily; parity 93.81 / 3.816 is asserted or the run stops.
7. **If P fails bar 1 (MANAGER #58-4)** the owner line reads: "the 09-27 package's standalone 109-vs-85 walk-forward gain
   was extra size, not aim."
8. **Stated limits:** single-arm bars cannot credit a combination-only squeeze effect (69b: the squeeze helps only inside
   the package); KEEL v12's Friday and FOMC multipliers were chosen on other families' full histories, so the 2011-16
   block is untuned for NOISE but not blind (bar 4 is a consistency check, not out-of-sample evidence).

## POWER LINE (committed before `run`; nulls only, no arm's own P&L read) - C:\EdgeLog\custom_ml\fixed_ablation\POWER.txt
```
#463 parity, built to 2025-06-29: WF ROC@$30k 93.81  Sortino 3.816 (93.81 / 3.816)
POWER LINE - nulls only, no arm's own P&L read. Minimum detectable WF ROC lead over the twin:
  P          own-size shuffle (1,000): 50th +0.05  95th +3.52  98.3th +4.62
  P-squeeze  own-size shuffle (1,000): 50th +0.11  95th +2.70  98.3th +3.31
  P-Friday   own-size shuffle (1,000): 50th +0.06  95th +2.24  98.3th +2.92
  P-FOMC     own-size shuffle (1,000): 50th +0.15  95th +3.24  98.3th +4.18
  squeeze    own-size shuffle (1,000): 50th +0.07  95th +1.79  98.3th +2.21
  Friday     own-size shuffle (1,000): 50th +0.21  95th +2.27  98.3th +2.98
  FOMC       own-size shuffle (1,000): 50th -0.02  95th +1.26  98.3th +1.74
  squeeze time-shift (200, 60..250 sessions): 50th +0.22  95th +1.50
Expectation stated now (MANAGER #58): real leads of NOISE r70's size (~3 ROC points in the book) may sit inside these nulls and then cannot be told from luck.
```

---

## RESULT 2026-10-05 ~07:40 MST - SQUEEZE CARRIES inside the book; Friday and FOMC do not. Lockbox never read.
`python tools/noise_fixed_ablation.py run` -> C:\EdgeLog\custom_ml\fixed_ablation\ (STAGE_A.txt, arms.csv, nulls.csv).
Book built to 2025-06-29, parity 93.81 / 3.816 exact. WF 2016-07-01..2025-06-29, ROC %/yr at a $30k drawdown, valued daily.

| arm | WF ROC / Sortino | its twin (plain extra NOISE, same mean size) | lead | no Feb-Apr 2020 | ex twin's worst-DD window (2020-03-02..03-27) | 2011-16 | years | own-shuffle pct |
|---|---|---|---|---|---|---|---|---|
| P (full package) | 107.8 / 4.28 | 97.9 / 3.92 | +9.82 / +0.353 | +5.21 | +5.36 | -0.19 | 9/9 | 100.0 |
| P-squeeze | 99.3 / 3.99 | 95.7 / 3.87 | +3.57 | +2.78 | +2.65 | +0.31 | 8/9 | 98.7 |
| P-Friday | 101.9 / 4.10 | 95.6 / 3.86 | +6.38 | +4.20 | +4.53 | +1.55 | 9/9 | 100.0 |
| P-FOMC | 106.9 / 4.23 | 98.2 / 3.93 | +8.66 | +3.42 | +3.57 | -1.06 | 9/9 | 100.0 |
| **squeeze alone** | **101.1 / 4.06** | 95.9 / 3.87 | **+5.21 / +0.186** | +2.35 | +2.68 | +0.56 | 9/9 | 100.0 |
| Friday alone | 98.5 / 3.95 | 96.0 / 3.87 | +2.52 / +0.077 | +1.04 | +0.91 | -0.47 | 7/9 | 96.5 |
| FOMC alone | 94.6 / 3.86 | 93.5 / 3.81 | +1.06 / +0.050 | +1.79 | +1.79 | +0.83 | 9/9 | 93.9 |
BOOK #463 itself: 93.81 / 3.816.

- **Squeeze: all 7 of its bars PASS** - beats its twin and #463 on ROC and Sortino; holds without Feb-Apr 2020; 9 of 9
  years; the 2011-16 block; above its own-size shuffle's 98.3rd pct (+2.21) and the time-shift null's 95th pct (+1.50).
- **Friday: does not carry** - fails the 2011-16 block (-0.47) and its shuffle cut (+2.52 vs +2.98); it does beat all
  four weekday placebos (Mon +0.74, Tue +0.55, Wed -4.69, Thu +1.09).
- **FOMC: does not carry** - 66 trades (report-only by power) and below its shuffle cut (+1.06 vs +1.74).
- **Leave-one-out inside P** (drop in P's lead when the part is removed): squeeze +6.25, Friday +3.45, FOMC +1.16.
- **P beats its twin AND #463 inside the book**, so the 09-27 package is NOT "extra size only"; most of it is the squeeze.

**Post-hoc checks (C:\EdgeLog\custom_ml\fixed_ablation\POSTHOC.txt; reported, they cannot change the verdict):**
- No look-ahead: the squeeze flag recomputed on data cut at the fill (bar E's own high/low/close blanked) matches on
  300 of 300 random WF fills. The flag reads the last COMPLETE 60-minute block, which ends at or before the decision.
- **Concentration - the main caveat:** the 308 squeeze-on WF trades average $635 against $101 for the rest (#422 sizes)
  and hold 44% of WF NOISE dollars. Removing the extra size from the top 1 / 5 / 10 / 20 of them leaves a lead of
  +4.76 / +3.51 / +2.28 / +0.29. The edge is the squeeze's big winners (the survivors), as in every NOISE read.
- Standalone the squeeze LOWERS #422's own ROC (NOISE 69b: 82.5 vs 84.6); the gain exists only in the book, where NOISE's
  own drawdown is diluted by the other legs - extra money per unit of size, not a smoother NOISE.
- About half the lead sits in March 2020 (no-2020 +2.35; ex twin-DD window +2.68).

**Seen-ness, stated plainly:** confirmatory. KEEL v12's 1.5x squeeze was chosen on other families' full histories, the
package (squeeze inside) was read at book level with the lockbox in round 61 (run #457), and 69b read it standalone.
What is new: the squeeze alone, inside #463, beats plain extra NOISE and both its nulls in walk-forward.

**Next, per the registration:** a forward no-order SQUEEZE sub-arm in NOISE's reader (tools/noise_fixed_subarm_read.py),
judged by the paired sequential stop at 50 closed squeeze-on trades (request to NOISE). Any BOOK run (#463 with the
squeeze on its NOISE leg) reads a partly seen lockbox and waits for MANAGER's line. Nothing live changes.

Hedge-tilt follow-up (MANAGER #56): the hedge arm's daily difference vs its twin correlates +0.67 with NOISE round 70's
shorts-x1.5 difference over the WF days (+0.67 on the 1,394 days either moved) - the same side-tilt hunt, both dead.
