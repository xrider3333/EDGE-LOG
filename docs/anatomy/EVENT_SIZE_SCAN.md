# EVENT SIZE SCAN — scheduled-event position-size rules on three crowned legs

Generated 2026-09-09 08:04 · `tools/event_size_scan.py` · 1080 cells · 2000 permutation draws · seed 20260909

## Blunt summary

**40 of 1080 cells survive** all five clauses on the pre-lockbox window (3.7%). They are listed below with their permutation ranks, and the sealed year is opened once for them at the end.

**But read the survivor list as a hypothesis list, not as 40 findings.** The pre-registration has a hole in it: it judged every one of 1080 cells at a nominal one-sided 5% and never wrote down a multiple-comparisons clause. The cells are also heavily redundant — m=0.0 and m=0.5 always share a permutation p-value with each other (and m=1.5 with m=2.0), because the improvement is (m-1) x the same affected-trade sum; 'whole session' and 'before 14:00' overlap almost completely on an RTH leg; and consecutive day offsets of a multi-day calendar overlap. So the honest denominator is a few hundred effectively independent tests, and roughly five percent of them are expected to clear a 5% threshold with no edge at all.

The post-hoc family-wide null below settles it: with all ten calendars replaced by random ones of the same size, the identical pipeline still produces a median of **32** survivors (range 18-54, mean 31.8) across 25 replicates, against the real scan's **40**. P(random >= real) = 0.120.

## Pre-registration (verbatim, written before any number was computed)

```
EVENT SIZE SCAN — pre-registered sweep of scheduled-event SIZE rules on three crowned legs.

WHY THIS EXISTS
    Through 2026-09 the per-trade feature mining, four new mechanisms and four new feature
    families all produced nothing that survived out of sample.  The one thing that DID work
    was different in kind: KEEL v12 (2026-09-09) halves position size before the 14:00 ET
    FOMC statement, read straight off the Fed's own published calendar.  It improved net in
    4 of 4 stretches with drawdown never worse, sat in the bottom 0.1% of 4,000 random
    calendars, beat 3 placebos, and the same hole shows up on ORB and ENGU-Q.  The lesson
    recorded was: WHEN TILTS DRY UP, GET NEW INFORMATION.  Scheduled events are new
    information the machine has never systematically used.  This file generalises that one
    finding into a pre-registered sweep over many published calendars.

    SIZE RULES ONLY.  Never an entry filter.  Filters have failed every single time this
    month; a size rule keeps every trade the strategy would have taken and only changes how
    many contracts ride on it, so the trade COUNT is identical in every cell (tested).

================================================================================================
PRE-REGISTRATION  — written before a single number was computed, and NOT edited afterwards.
================================================================================================

LEGS (crowned; each run at its own file's DEFAULT_PARAMS defaults, nothing else pinned)
    NOISE   augur_strategies/NOISE_1_1_SBS_V90.py      NQ 5m RTH   cost 0.533 pts, $20/pt, 1 contract
    ORB     augur_strategies/ORB_3_6_R6.py             NQ 5m RTH   cost 0.533 pts, $20/pt, 1 contract
    ENGUQ   augur_strategies/ENGUQ_1M_ETH_ER_1_0.py    NQ 1m ETH   cost 0.533 pts, $20/pt, 1 contract

WINDOW
    2010-06-07 .. 2025-06-30.
    The LAST 12 MONTHS (entry date >= 2024-07-01) are a SEALED LOCKBOX.  Every number in the
    scan below is computed on the pre-lockbox slice 2010-06-07 .. 2024-06-30 only.  The
    lockbox is loaded ONCE, at the very end, for the cells that already cleared everything
    else, and is reported separately and clearly marked as the single peek.

EVENT CALENDARS  (built into tools/data/*.csv, each with a `date` column and a source note)
    fomc_decision   scheduled FOMC decision (statement) days.  ALREADY ON MAIN
                    (tools/data/fomc_dates.txt / .csv, scraped from federalreserve.gov).
                    Included as the known-positive control, since KEEL v12 lives on it.
    cpi             BLS Consumer Price Index news-release days, 08:30 ET.  Hard-coded from
                    the BLS published annual schedules (bls.gov/schedule/<year>/home.htm).
    nfp             BLS Employment Situation ("non-farm payrolls") release days, 08:30 ET.
                    Hard-coded from the SAME BLS annual schedules, so the published
                    exceptions to "first Friday" (e.g. 2015-05-08, 2013-10-22, 2020-01-10)
                    are the real dates, not a re-derived rule.
    fomc_minutes    3 weeks (21 calendar days) after each scheduled decision day, 14:00 ET.
                    Derived from the verified FOMC decision file — that is the Fed's own
                    stated publication rule.
    quad_witching   3rd Friday of March / June / September / December.  Derived.
    month_end       last TWO trading days of each calendar month.       Derived from the tape.
    month_start     first TWO trading days of each calendar month.      Derived from the tape.
    quarter_end     last TWO trading days of each calendar quarter.     Derived from the tape.
    quarter_start   first TWO trading days of each calendar quarter.    Derived from the tape.
    fed_blackout    every trading day in the 10 calendar days BEFORE a scheduled decision
                    day (decision day itself excluded).  Derived from the FOMC file.
    Verification: a handful of dates are cross-checked against the FOMC file already on main
    (fomc_minutes and fed_blackout are DERIVED from it, so they inherit its verification),
    and the CSV header of every file records its source and whether it was verified.  Any
    date that could not be verified is marked in the file's own note line.

RULE FORM  (fixed; no other form is tried)
    On a day in the calendar (and, run separately, the trading day BEFORE it and the trading
    day AFTER it), multiply position size by m for trades whose DECISION BAR (entry bar)
    falls inside a stated clock window.  Size only.  No signal is ever skipped, no entry or
    exit is ever touched.  m = 0.0 is "flat that trade" as a SIZE of zero — the trade is
    still taken and still counted, it just carries no contracts.
        day offset    : {0 = event day, -1 = the trading day before, +1 = the trading day after}
        multiplier m  : {0.0, 0.5, 1.5, 2.0}
        clock window  : {all = whole session, am = entry bar before 14:00 ET,
                         pm = entry bar at/after 14:00 ET}
    A trade's event day is the ET CALENDAR DATE of its entry bar (the same convention
    augur_engine.ml_keel.pre_statement_mask uses), and its clock is that bar's ET hour.
    3 legs x 10 calendars x 3 offsets x 4 multipliers x 3 clock windows = 1,080 cells.
    EVERY cell is reported.  Never only the best.

BAR PER CELL  (ALL of these required, computed on the pre-lockbox slice only)
    B0  at least 30 pre-lockbox trades are affected by the rule (n_affected >= 30).
    B1  NET improves versus the untouched leg.
    B2  ANNUALISED MAR = (net / years) / |max drawdown| improves versus the untouched leg.
    B3  the improvement is not carried by one calendar year:
          (a) the per-year net improvement is positive in at least half of the calendar
              years that contain at least one affected trade, AND
          (b) dropping the single best calendar year still leaves the total improvement > 0.
        The full year table is reported for every cell that reaches this test.
    B4  it survives a PERMUTATION test: 2,000 random calendars drawn from the leg's own
        trading days with the SAME NUMBER OF DAYS PER CALENDAR YEAR as the real calendar.
        The real calendar's net improvement must rank in the top 5% (p <= 0.05, one-sided).
        The rank is reported.  PLUS it must beat at least 2 placebo calendars — the same
        calendar shifted +7 and -7 calendar days (then snapped to trading days) — on net
        improvement.
    A cell SURVIVES only if B0 and B1 and B2 and B3 and B4 all hold.  Nothing else is a pass.

LOCKBOX
    Opened once, at the end, for the surviving cells only.  Reported separately.  A lockbox
    number is never part of the bar and never selects a cell.

OUTPUT
    docs/anatomy/EVENT_SIZE_SCAN.md — this pre-registration, all 1,080 cells, the year
    tables, the permutation ranks, the lockbox peek, and a blunt summary.

USAGE
    python tools/event_size_scan.py                 # full scan + lockbox peek for survivors
    python tools/event_size_scan.py --perm 500      # fewer permutation draws (dev only)
    python tools/event_size_scan.py --no-lockbox    # pre-lockbox work only, seal stays shut
    python tools/event_size_scan.py --print-all     # dump all 1,080 rows to stdout too
```

## Legs — untouched baseline (pre-lockbox 2010-06-07 .. 2024-06-30)

| leg | trades | net | max DD | annualised MAR |
|---|---:|---:|---:|---:|
| NOISE | 3,893 | $252,780 | $-18,425 | 0.98 |
| ORB | 1,865 | $214,259 | $-32,529 | 0.47 |
| ENGUQ | 2,447 | $277,062 | $-50,420 | 0.39 |

## Event calendars built

> **Shipping note:** the repo `.gitignore` ignores `*.csv` globally, so these files exist on disk but git will not see them. `tools/data/fomc_dates.csv` is tracked only because it was force-added. Ship these the same way (`git add -f tools/data/*_dates.csv`) or they will silently not travel with the tool. Regenerating them is cheap and deterministic — `python tools/event_size_scan.py` rewrites all nine every run.

Day counts are what the SCAN saw (pre-lockbox years only). The CSV files themselves cover the whole 2010-06-07..2025-06-30 window.

| calendar | days seen by the scan | file | source | verification |
|---|---:|---|---|---|
| fomc_decision | 119 | `tools\data\fomc_dates.txt` | tools/data/fomc_dates.txt (federalreserve.gov, already verified on main) | already verified on main |
| cpi | 175 | `tools\data\cpi_dates.csv` | BLS published annual schedules bls.gov/schedule/<year>/home.htm, fetched 2026-09-09 | PARTIALLY VERIFIED: 175 dates transcribed from the BLS annual schedule pages; all weekdays: True; NOT independently cross-checked against a second source |
| nfp | 174 | `tools\data\nfp_dates.csv` | BLS published annual schedules bls.gov/schedule/<year>/home.htm, fetched 2026-09-09 | PARTIALLY VERIFIED: 174 dates transcribed from the BLS annual schedule pages; 170/174 are Fridays (the rest are the published exceptions); NOT independently cross-checked against a second source |
| fomc_minutes | 118 | `tools\data\fomc_minutes_dates.csv` | DERIVED: scheduled FOMC decision day + 21 calendar days (the Fed's own rule) | VERIFIED: derived from the on-main FOMC file; 118/119 decisions map to a minutes date exactly 21 days later |
| quad_witching | 60 | `tools\data\quad_witching_dates.csv` | DERIVED: 3rd Friday of Mar/Jun/Sep/Dec | VERIFIED: 2024 spot-check all 4 present; all entries are Fridays: True |
| month_start | 338 | `tools\data\month_start_dates.csv` | DERIVED: first 2 trading days of each calendar month (from the NQ RTH tape) | VERIFIED BY CONSTRUCTION: taken from the traded tape's own session dates |
| month_end | 338 | `tools\data\month_end_dates.csv` | DERIVED: last 2 trading days of each calendar month (from the NQ RTH tape) | VERIFIED BY CONSTRUCTION: taken from the traded tape's own session dates |
| quarter_start | 114 | `tools\data\quarter_start_dates.csv` | DERIVED: first 2 trading days of each calendar quarter (from the NQ RTH tape) | VERIFIED BY CONSTRUCTION: taken from the traded tape's own session dates |
| quarter_end | 114 | `tools\data\quarter_end_dates.csv` | DERIVED: last 2 trading days of each calendar quarter (from the NQ RTH tape) | VERIFIED BY CONSTRUCTION: taken from the traded tape's own session dates |
| fed_blackout | 776 | `tools\data\fed_blackout_dates.csv` | DERIVED: trading days in the 10 calendar days before a scheduled decision day | VERIFIED: derived from the on-main FOMC file; no decision day is itself in the set (0 overlaps, must be 0) |

## Surviving cells

| leg | calendar | offset | clock | m | n_aff | net | ΔNet | MAR | ΔMAR | perm rank | perm p | placebo +7 | placebo -7 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| NOISE | fomc_decision | event day | before 14:00 ET | 0.0 | 80 | $270,003 | $+17,223 | 1.11 | +0.14 | 1/2001 | 0.0005 | $-893 | $-11,153 |
| NOISE | fomc_decision | event day | before 14:00 ET | 0.5 | 80 | $261,392 | $+8,612 | 1.06 | +0.09 | 1/2001 | 0.0005 | $-446 | $-5,577 |
| NOISE | cpi | event day | at/after 14:00 ET | 0.0 | 37 | $258,376 | $+5,596 | 1.02 | +0.05 | 45/2001 | 0.0225 | $+237 | $-9,127 |
| NOISE | cpi | event day | at/after 14:00 ET | 0.5 | 37 | $255,578 | $+2,798 | 1.00 | +0.02 | 45/2001 | 0.0225 | $+119 | $-4,563 |
| NOISE | fomc_minutes | event day | whole session | 0.0 | 123 | $261,930 | $+9,150 | 1.12 | +0.14 | 30/2001 | 0.0150 | $-18,927 | $-17,829 |
| NOISE | fomc_minutes | event day | whole session | 0.5 | 123 | $257,355 | $+4,575 | 1.06 | +0.09 | 30/2001 | 0.0150 | $-9,464 | $-8,915 |
| NOISE | fomc_minutes | day after | whole session | 1.5 | 130 | $266,810 | $+14,031 | 1.01 | +0.03 | 20/2001 | 0.0100 | $+7,935 | $+944 |
| NOISE | fomc_minutes | day after | whole session | 2.0 | 130 | $280,841 | $+28,061 | 1.04 | +0.07 | 20/2001 | 0.0100 | $+15,870 | $+1,888 |
| NOISE | fomc_minutes | day after | before 14:00 ET | 1.5 | 108 | $267,258 | $+14,478 | 1.01 | +0.04 | 14/2001 | 0.0070 | $+8,093 | $-1,812 |
| NOISE | fomc_minutes | day after | before 14:00 ET | 2.0 | 108 | $281,735 | $+28,956 | 1.05 | +0.07 | 14/2001 | 0.0070 | $+16,186 | $-3,624 |
| ORB | quad_witching | day before | whole session | 1.5 | 37 | $225,252 | $+10,993 | 0.49 | +0.03 | 32/2001 | 0.0160 | $+848 | $+4,674 |
| ORB | quad_witching | day before | whole session | 2.0 | 37 | $236,245 | $+21,986 | 0.52 | +0.05 | 32/2001 | 0.0160 | $+1,696 | $+9,347 |
| ORB | quad_witching | day before | before 14:00 ET | 1.5 | 35 | $225,453 | $+11,193 | 0.49 | +0.03 | 25/2001 | 0.0125 | $+424 | $+1,090 |
| ORB | quad_witching | day before | before 14:00 ET | 2.0 | 35 | $236,646 | $+22,387 | 0.52 | +0.05 | 25/2001 | 0.0125 | $+848 | $+2,180 |
| ORB | month_start | day before | before 14:00 ET | 0.0 | 150 | $227,316 | $+13,056 | 0.50 | +0.04 | 89/2001 | 0.0445 | $-6,344 | $-18,571 |
| ORB | month_start | day before | before 14:00 ET | 0.5 | 150 | $220,787 | $+6,528 | 0.49 | +0.02 | 89/2001 | 0.0445 | $-3,172 | $-9,286 |
| ORB | month_start | day after | before 14:00 ET | 1.5 | 175 | $239,544 | $+25,285 | 0.51 | +0.04 | 74/2001 | 0.0370 | $+10,398 | $+21,505 |
| ORB | month_start | day after | before 14:00 ET | 2.0 | 175 | $264,829 | $+50,569 | 0.54 | +0.07 | 74/2001 | 0.0370 | $+20,797 | $+43,010 |
| ORB | month_end | event day | whole session | 0.0 | 159 | $236,392 | $+22,132 | 0.48 | +0.01 | 21/2001 | 0.0105 | $-29,031 | $-36,418 |
| ORB | month_end | event day | whole session | 0.5 | 159 | $225,325 | $+11,066 | 0.48 | +0.01 | 21/2001 | 0.0105 | $-14,516 | $-18,209 |
| ORB | month_end | event day | before 14:00 ET | 0.0 | 147 | $238,444 | $+24,185 | 0.47 | +0.01 | 20/2001 | 0.0100 | $-22,933 | $-34,602 |
| ORB | month_end | event day | before 14:00 ET | 0.5 | 147 | $226,351 | $+12,092 | 0.47 | +0.01 | 20/2001 | 0.0100 | $-11,467 | $-17,301 |
| ORB | month_end | day after | before 14:00 ET | 0.0 | 150 | $227,931 | $+13,671 | 0.51 | +0.04 | 85/2001 | 0.0425 | $-3,904 | $-12,574 |
| ORB | month_end | day after | before 14:00 ET | 0.5 | 150 | $221,095 | $+6,836 | 0.49 | +0.02 | 85/2001 | 0.0425 | $-1,952 | $-6,287 |
| ORB | quarter_end | event day | before 14:00 ET | 0.0 | 49 | $227,106 | $+12,847 | 0.50 | +0.03 | 75/2001 | 0.0375 | $-14,981 | $-6,444 |
| ORB | quarter_end | event day | before 14:00 ET | 0.5 | 49 | $220,683 | $+6,424 | 0.48 | +0.01 | 75/2001 | 0.0375 | $-7,491 | $-3,222 |
| ENGUQ | cpi | day before | whole session | 1.5 | 107 | $310,540 | $+33,477 | 0.42 | +0.03 | 47/2001 | 0.0235 | $+17,826 | $+12,068 |
| ENGUQ | cpi | day before | whole session | 2.0 | 107 | $344,017 | $+66,954 | 0.45 | +0.06 | 47/2001 | 0.0235 | $+35,652 | $+24,137 |
| ENGUQ | cpi | day before | before 14:00 ET | 1.5 | 74 | $309,412 | $+32,349 | 0.43 | +0.04 | 51/2001 | 0.0255 | $+3,712 | $+12,370 |
| ENGUQ | cpi | day before | before 14:00 ET | 2.0 | 74 | $341,761 | $+64,699 | 0.47 | +0.08 | 51/2001 | 0.0255 | $+7,425 | $+24,741 |
| ENGUQ | cpi | day after | whole session | 0.0 | 136 | $303,955 | $+26,892 | 0.43 | +0.04 | 50/2001 | 0.0250 | $-5,205 | $-6,358 |
| ENGUQ | cpi | day after | whole session | 0.5 | 136 | $290,509 | $+13,446 | 0.41 | +0.02 | 50/2001 | 0.0250 | $-2,603 | $-3,179 |
| ENGUQ | cpi | day after | before 14:00 ET | 0.0 | 100 | $298,396 | $+21,334 | 0.42 | +0.03 | 59/2001 | 0.0295 | $-1,716 | $+926 |
| ENGUQ | cpi | day after | before 14:00 ET | 0.5 | 100 | $287,729 | $+10,667 | 0.41 | +0.02 | 59/2001 | 0.0295 | $-858 | $+463 |
| ENGUQ | nfp | day before | at/after 14:00 ET | 0.0 | 34 | $295,532 | $+18,470 | 0.42 | +0.03 | 9/2001 | 0.0045 | $+834 | $-2,612 |
| ENGUQ | nfp | day before | at/after 14:00 ET | 0.5 | 34 | $286,297 | $+9,235 | 0.41 | +0.02 | 9/2001 | 0.0045 | $+417 | $-1,306 |
| ENGUQ | nfp | day after | whole session | 1.5 | 82 | $311,619 | $+34,557 | 0.44 | +0.05 | 43/2001 | 0.0215 | $-293 | $+21,764 |
| ENGUQ | nfp | day after | whole session | 2.0 | 82 | $346,176 | $+69,113 | 0.48 | +0.09 | 43/2001 | 0.0215 | $-585 | $+43,529 |
| ENGUQ | nfp | day after | before 14:00 ET | 1.5 | 57 | $311,496 | $+34,434 | 0.44 | +0.05 | 38/2001 | 0.0190 | $-3,039 | $+16,255 |
| ENGUQ | nfp | day after | before 14:00 ET | 2.0 | 57 | $345,930 | $+68,867 | 0.49 | +0.10 | 38/2001 | 0.0190 | $-6,078 | $+32,509 |

## Family-wide null — post-hoc diagnostic, NOT part of the pre-registered bar

This was not in the pre-registration and it neither rescues nor kills a single cell. It exists because the pre-registration forgot a multiple-comparisons clause, and the only way to read the survivor count honestly is to know what the same pipeline does when the calendars mean nothing. Each replicate replaces all ten calendars with random ones carrying the same number of days per calendar year, then runs the identical B0-B4 pipeline over all three legs.

| replicates | real survivors | null median | null range | null mean | P(null >= real) |
|---:|---:|---:|---|---:|---:|
| 25 | 40 | 32 | 18-54 | 31.8 | 0.120 |

Per-replicate survivor counts: 36, 34, 20, 22, 32, 36, 22, 29, 22, 38, 32, 24, 26, 44, 18, 24, 22, 50, 36, 38, 54, 34, 38, 26, 38

Cells that reached the permutation at all (cleared B0-B3): 122 of 1080. Of those, 40 cleared B4.

## Lockbox — THE SINGLE PEEK (2024-07-01 .. 2025-06-30)

| leg | calendar | offset | clock | m | LB n_aff | LB base net | LB sized net | ΔNet | LB base DD | LB sized DD |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| NOISE | fomc_decision | event day | before 14:00 ET | 0.0 | 4 | $82,387 | $82,300 | $-87 | $-7,531 | $-7,826 |
| NOISE | fomc_decision | event day | before 14:00 ET | 0.5 | 4 | $82,387 | $82,344 | $-44 | $-7,531 | $-7,138 |
| NOISE | cpi | event day | at/after 14:00 ET | 0.0 | 1 | $82,387 | $82,383 | $-4 | $-7,531 | $-7,531 |
| NOISE | cpi | event day | at/after 14:00 ET | 0.5 | 1 | $82,387 | $82,385 | $-2 | $-7,531 | $-7,531 |
| NOISE | fomc_minutes | event day | whole session | 0.0 | 5 | $82,387 | $82,681 | $+293 | $-7,531 | $-7,167 |
| NOISE | fomc_minutes | event day | whole session | 0.5 | 5 | $82,387 | $82,534 | $+147 | $-7,531 | $-7,167 |
| NOISE | fomc_minutes | day after | whole session | 1.5 | 9 | $82,387 | $84,602 | $+2,215 | $-7,531 | $-7,531 |
| NOISE | fomc_minutes | day after | whole session | 2.0 | 9 | $82,387 | $86,816 | $+4,429 | $-7,531 | $-7,531 |
| NOISE | fomc_minutes | day after | before 14:00 ET | 1.5 | 9 | $82,387 | $84,602 | $+2,215 | $-7,531 | $-7,531 |
| NOISE | fomc_minutes | day after | before 14:00 ET | 2.0 | 9 | $82,387 | $86,816 | $+4,429 | $-7,531 | $-7,531 |
| ORB | quad_witching | day before | whole session | 1.5 | 1 | $82,338 | $83,580 | $+1,242 | $-24,205 | $-24,205 |
| ORB | quad_witching | day before | whole session | 2.0 | 1 | $82,338 | $84,822 | $+2,484 | $-24,205 | $-24,205 |
| ORB | quad_witching | day before | before 14:00 ET | 1.5 | 1 | $82,338 | $83,580 | $+1,242 | $-24,205 | $-24,205 |
| ORB | quad_witching | day before | before 14:00 ET | 2.0 | 1 | $82,338 | $84,822 | $+2,484 | $-24,205 | $-24,205 |
| ORB | month_start | day before | before 14:00 ET | 0.0 | 15 | $82,338 | $83,713 | $+1,375 | $-24,205 | $-22,453 |
| ORB | month_start | day before | before 14:00 ET | 0.5 | 15 | $82,338 | $83,025 | $+687 | $-24,205 | $-22,784 |
| ORB | month_start | day after | before 14:00 ET | 1.5 | 14 | $82,338 | $84,131 | $+1,793 | $-24,205 | $-23,733 |
| ORB | month_start | day after | before 14:00 ET | 2.0 | 14 | $82,338 | $85,924 | $+3,586 | $-24,205 | $-26,304 |
| ORB | month_end | event day | whole session | 0.0 | 13 | $82,338 | $75,109 | $-7,229 | $-24,205 | $-25,634 |
| ORB | month_end | event day | whole session | 0.5 | 13 | $82,338 | $78,724 | $-3,614 | $-24,205 | $-24,594 |
| ORB | month_end | event day | before 14:00 ET | 0.0 | 13 | $82,338 | $75,109 | $-7,229 | $-24,205 | $-25,634 |
| ORB | month_end | event day | before 14:00 ET | 0.5 | 13 | $82,338 | $78,724 | $-3,614 | $-24,205 | $-24,594 |
| ORB | month_end | day after | before 14:00 ET | 0.0 | 14 | $82,338 | $80,802 | $-1,536 | $-24,205 | $-22,453 |
| ORB | month_end | day after | before 14:00 ET | 0.5 | 14 | $82,338 | $81,570 | $-768 | $-24,205 | $-22,784 |
| ORB | quarter_end | event day | before 14:00 ET | 0.0 | 4 | $82,338 | $82,011 | $-327 | $-24,205 | $-24,205 |
| ORB | quarter_end | event day | before 14:00 ET | 0.5 | 4 | $82,338 | $82,174 | $-164 | $-24,205 | $-24,205 |
| ENGUQ | cpi | day before | whole session | 1.5 | 15 | $47,575 | $51,342 | $+3,766 | $-41,519 | $-48,944 |
| ENGUQ | cpi | day before | whole session | 2.0 | 15 | $47,575 | $55,108 | $+7,533 | $-41,519 | $-59,329 |
| ENGUQ | cpi | day before | before 14:00 ET | 1.5 | 12 | $47,575 | $49,395 | $+1,820 | $-41,519 | $-45,777 |
| ENGUQ | cpi | day before | before 14:00 ET | 2.0 | 12 | $47,575 | $51,215 | $+3,640 | $-41,519 | $-54,042 |
| ENGUQ | cpi | day after | whole session | 0.0 | 6 | $47,575 | $50,559 | $+2,984 | $-41,519 | $-44,092 |
| ENGUQ | cpi | day after | whole session | 0.5 | 6 | $47,575 | $49,067 | $+1,492 | $-41,519 | $-42,443 |
| ENGUQ | cpi | day after | before 14:00 ET | 0.0 | 5 | $47,575 | $50,549 | $+2,973 | $-41,519 | $-44,092 |
| ENGUQ | cpi | day after | before 14:00 ET | 0.5 | 5 | $47,575 | $49,062 | $+1,487 | $-41,519 | $-42,443 |
| ENGUQ | nfp | day before | at/after 14:00 ET | 0.0 | 1 | $47,575 | $46,776 | $-799 | $-41,519 | $-41,519 |
| ENGUQ | nfp | day before | at/after 14:00 ET | 0.5 | 1 | $47,575 | $47,176 | $-400 | $-41,519 | $-41,519 |
| ENGUQ | nfp | day after | whole session | 1.5 | 14 | $47,575 | $56,232 | $+8,657 | $-41,519 | $-40,830 |
| ENGUQ | nfp | day after | whole session | 2.0 | 14 | $47,575 | $64,888 | $+17,313 | $-41,519 | $-40,778 |
| ENGUQ | nfp | day after | before 14:00 ET | 1.5 | 9 | $47,575 | $56,846 | $+9,271 | $-41,519 | $-40,425 |
| ENGUQ | nfp | day after | before 14:00 ET | 2.0 | 9 | $47,575 | $66,117 | $+18,542 | $-41,519 | $-40,140 |

## Cells that cleared net + MAR + the year test (B0-B3) and so reached the permutation

| leg | calendar | offset | clock | m | n_aff | ΔNet | ΔMAR | years + / n | drop-best-year Δ | perm rank | perm p | beats placebos |
|---|---|---|---|---:|---:|---:|---:|---|---:|---|---:|---|
| NOISE | fomc_decision | event day | before 14:00 ET | 0.0 | 80 | $+17,223 | +0.14 | 14/15 | $+8,497 | 1/2001 | 0.0005 | yes |
| NOISE | fomc_decision | event day | before 14:00 ET | 0.5 | 80 | $+8,612 | +0.09 | 14/15 | $+4,248 | 1/2001 | 0.0005 | yes |
| ENGUQ | nfp | day before | at/after 14:00 ET | 0.0 | 34 | $+18,470 | +0.03 | 12/14 | $+7,737 | 9/2001 | 0.0045 | yes |
| ENGUQ | nfp | day before | at/after 14:00 ET | 0.5 | 34 | $+9,235 | +0.02 | 12/14 | $+3,868 | 9/2001 | 0.0045 | yes |
| NOISE | fomc_minutes | day after | before 14:00 ET | 1.5 | 108 | $+14,478 | +0.04 | 13/15 | $+8,795 | 14/2001 | 0.0070 | yes |
| NOISE | fomc_minutes | day after | before 14:00 ET | 2.0 | 108 | $+28,956 | +0.07 | 13/15 | $+17,590 | 14/2001 | 0.0070 | yes |
| NOISE | fomc_minutes | day after | whole session | 1.5 | 130 | $+14,031 | +0.03 | 13/15 | $+8,348 | 20/2001 | 0.0100 | yes |
| NOISE | fomc_minutes | day after | whole session | 2.0 | 130 | $+28,061 | +0.07 | 13/15 | $+16,695 | 20/2001 | 0.0100 | yes |
| ORB | month_end | event day | before 14:00 ET | 0.0 | 147 | $+24,185 | +0.01 | 11/15 | $+12,173 | 20/2001 | 0.0100 | yes |
| ORB | month_end | event day | before 14:00 ET | 0.5 | 147 | $+12,092 | +0.01 | 11/15 | $+6,086 | 20/2001 | 0.0100 | yes |
| ORB | month_end | event day | whole session | 0.0 | 159 | $+22,132 | +0.01 | 11/15 | $+11,730 | 21/2001 | 0.0105 | yes |
| ORB | month_end | event day | whole session | 0.5 | 159 | $+11,066 | +0.01 | 11/15 | $+5,865 | 21/2001 | 0.0105 | yes |
| ORB | quad_witching | day before | before 14:00 ET | 1.5 | 35 | $+11,193 | +0.03 | 8/15 | $+7,457 | 25/2001 | 0.0125 | yes |
| ORB | quad_witching | day before | before 14:00 ET | 2.0 | 35 | $+22,387 | +0.05 | 8/15 | $+14,914 | 25/2001 | 0.0125 | yes |
| NOISE | fomc_minutes | event day | whole session | 0.0 | 123 | $+9,150 | +0.14 | 11/15 | $+4,426 | 30/2001 | 0.0150 | yes |
| NOISE | fomc_minutes | event day | whole session | 0.5 | 123 | $+4,575 | +0.09 | 11/15 | $+2,213 | 30/2001 | 0.0150 | yes |
| ORB | quad_witching | day before | whole session | 1.5 | 37 | $+10,993 | +0.03 | 8/15 | $+7,256 | 32/2001 | 0.0160 | yes |
| ORB | quad_witching | day before | whole session | 2.0 | 37 | $+21,986 | +0.05 | 8/15 | $+14,513 | 32/2001 | 0.0160 | yes |
| ENGUQ | nfp | day after | before 14:00 ET | 1.5 | 57 | $+34,434 | +0.05 | 9/14 | $+2,416 | 38/2001 | 0.0190 | yes |
| ENGUQ | nfp | day after | before 14:00 ET | 2.0 | 57 | $+68,867 | +0.10 | 9/14 | $+4,831 | 38/2001 | 0.0190 | yes |
| ENGUQ | nfp | day after | whole session | 1.5 | 82 | $+34,557 | +0.05 | 10/14 | $+3,352 | 43/2001 | 0.0215 | yes |
| ENGUQ | nfp | day after | whole session | 2.0 | 82 | $+69,113 | +0.09 | 10/14 | $+6,704 | 43/2001 | 0.0215 | yes |
| NOISE | cpi | event day | at/after 14:00 ET | 0.0 | 37 | $+5,596 | +0.05 | 11/13 | $+3,924 | 45/2001 | 0.0225 | yes |
| NOISE | cpi | event day | at/after 14:00 ET | 0.5 | 37 | $+2,798 | +0.02 | 11/13 | $+1,962 | 45/2001 | 0.0225 | yes |
| ENGUQ | cpi | day before | whole session | 1.5 | 107 | $+33,477 | +0.03 | 8/14 | $+5,149 | 47/2001 | 0.0235 | yes |
| ENGUQ | cpi | day before | whole session | 2.0 | 107 | $+66,954 | +0.06 | 8/14 | $+10,297 | 47/2001 | 0.0235 | yes |
| ENGUQ | cpi | day after | whole session | 0.0 | 136 | $+26,892 | +0.04 | 10/15 | $+15,896 | 50/2001 | 0.0250 | yes |
| ENGUQ | cpi | day after | whole session | 0.5 | 136 | $+13,446 | +0.02 | 10/15 | $+7,948 | 50/2001 | 0.0250 | yes |
| ENGUQ | cpi | day before | before 14:00 ET | 1.5 | 74 | $+32,349 | +0.04 | 8/13 | $+4,021 | 51/2001 | 0.0255 | yes |
| ENGUQ | cpi | day before | before 14:00 ET | 2.0 | 74 | $+64,699 | +0.08 | 8/13 | $+8,041 | 51/2001 | 0.0255 | yes |
| ENGUQ | cpi | day after | before 14:00 ET | 0.0 | 100 | $+21,334 | +0.03 | 9/15 | $+10,312 | 59/2001 | 0.0295 | yes |
| ENGUQ | cpi | day after | before 14:00 ET | 0.5 | 100 | $+10,667 | +0.02 | 9/15 | $+5,156 | 59/2001 | 0.0295 | yes |
| ORB | month_start | day after | before 14:00 ET | 1.5 | 175 | $+25,285 | +0.04 | 8/15 | $+13,015 | 74/2001 | 0.0370 | yes |
| ORB | month_start | day after | before 14:00 ET | 2.0 | 175 | $+50,569 | +0.07 | 8/15 | $+26,031 | 74/2001 | 0.0370 | yes |
| ORB | quarter_end | event day | before 14:00 ET | 0.0 | 49 | $+12,847 | +0.03 | 10/15 | $+9,062 | 75/2001 | 0.0375 | yes |
| ORB | quarter_end | event day | before 14:00 ET | 0.5 | 49 | $+6,424 | +0.01 | 10/15 | $+4,531 | 75/2001 | 0.0375 | yes |
| ORB | month_end | day after | before 14:00 ET | 0.0 | 150 | $+13,671 | +0.04 | 11/15 | $+3,314 | 85/2001 | 0.0425 | yes |
| ORB | month_end | day after | before 14:00 ET | 0.5 | 150 | $+6,836 | +0.02 | 11/15 | $+1,657 | 85/2001 | 0.0425 | yes |
| ORB | month_start | day before | before 14:00 ET | 0.0 | 150 | $+13,056 | +0.04 | 10/15 | $+2,699 | 89/2001 | 0.0445 | yes |
| ORB | month_start | day before | before 14:00 ET | 0.5 | 150 | $+6,528 | +0.02 | 10/15 | $+1,350 | 89/2001 | 0.0445 | yes |
| ENGUQ | fed_blackout | day before | whole session | 1.5 | 524 | $+66,257 | +0.02 | 12/15 | $+26,650 | 101/2001 | 0.0505 | yes |
| ENGUQ | fed_blackout | day before | whole session | 2.0 | 524 | $+132,514 | +0.04 | 12/15 | $+53,301 | 101/2001 | 0.0505 | yes |
| ENGUQ | fed_blackout | day before | before 14:00 ET | 1.5 | 410 | $+62,033 | +0.03 | 11/15 | $+23,628 | 101/2001 | 0.0505 | yes |
| ENGUQ | fed_blackout | day before | before 14:00 ET | 2.0 | 410 | $+124,067 | +0.06 | 11/15 | $+47,257 | 101/2001 | 0.0505 | yes |
| ORB | quarter_end | event day | whole session | 0.0 | 53 | $+11,500 | +0.04 | 9/15 | $+7,054 | 104/2001 | 0.0520 | yes |
| ORB | quarter_end | event day | whole session | 0.5 | 53 | $+5,750 | +0.02 | 9/15 | $+3,527 | 104/2001 | 0.0520 | yes |
| NOISE | fomc_minutes | event day | before 14:00 ET | 0.0 | 97 | $+4,983 | +0.08 | 9/14 | $+259 | 122/2001 | 0.0610 | yes |
| NOISE | fomc_minutes | event day | before 14:00 ET | 0.5 | 97 | $+2,492 | +0.04 | 9/14 | $+130 | 122/2001 | 0.0610 | yes |
| ENGUQ | quad_witching | day before | before 14:00 ET | 0.0 | 31 | $+10,585 | +0.01 | 8/10 | $+6,883 | 143/2001 | 0.0715 | yes |
| ENGUQ | quad_witching | day before | before 14:00 ET | 0.5 | 31 | $+5,293 | +0.01 | 8/10 | $+3,442 | 143/2001 | 0.0715 | yes |
| ORB | month_end | day after | whole session | 0.0 | 161 | $+7,844 | +0.03 | 9/15 | $+185 | 146/2001 | 0.0730 | yes |
| ORB | month_end | day after | whole session | 0.5 | 161 | $+3,922 | +0.02 | 9/15 | $+93 | 146/2001 | 0.0730 | yes |
| ENGUQ | nfp | day before | before 14:00 ET | 1.5 | 66 | $+20,792 | +0.01 | 8/13 | $+9,856 | 175/2001 | 0.0875 | yes |
| ENGUQ | nfp | day before | before 14:00 ET | 2.0 | 66 | $+41,584 | +0.01 | 8/13 | $+19,712 | 175/2001 | 0.0875 | yes |
| ENGUQ | fomc_minutes | day before | before 14:00 ET | 0.0 | 46 | $+12,515 | +0.02 | 10/13 | $+6,556 | 178/2001 | 0.0890 | NO |
| ENGUQ | fomc_minutes | day before | before 14:00 ET | 0.5 | 46 | $+6,258 | +0.01 | 10/13 | $+3,278 | 178/2001 | 0.0890 | NO |
| NOISE | nfp | day after | whole session | 1.5 | 166 | $+12,812 | +0.06 | 11/15 | $+7,554 | 197/2001 | 0.0985 | yes |
| NOISE | nfp | day after | whole session | 2.0 | 166 | $+25,624 | +0.09 | 11/15 | $+15,109 | 197/2001 | 0.0985 | yes |
| NOISE | month_end | event day | at/after 14:00 ET | 0.0 | 70 | $+3,686 | +0.11 | 10/14 | $+1,909 | 206/2001 | 0.1029 | yes |
| NOISE | month_end | event day | at/after 14:00 ET | 0.5 | 70 | $+1,843 | +0.05 | 10/14 | $+954 | 206/2001 | 0.1029 | yes |
| ENGUQ | fomc_minutes | day after | before 14:00 ET | 1.5 | 31 | $+14,157 | +0.02 | 7/11 | $+8,616 | 206/2001 | 0.1029 | yes |
| ENGUQ | fomc_minutes | day after | before 14:00 ET | 2.0 | 31 | $+28,315 | +0.03 | 7/11 | $+17,232 | 206/2001 | 0.1029 | yes |
| NOISE | nfp | day after | before 14:00 ET | 1.5 | 137 | $+11,527 | +0.06 | 11/15 | $+6,269 | 227/2001 | 0.1134 | yes |
| NOISE | nfp | day after | before 14:00 ET | 2.0 | 137 | $+23,053 | +0.08 | 11/15 | $+12,538 | 227/2001 | 0.1134 | yes |
| ENGUQ | fomc_minutes | day after | whole session | 1.5 | 56 | $+14,408 | +0.01 | 10/14 | $+9,659 | 233/2001 | 0.1164 | yes |
| ENGUQ | fomc_minutes | day after | whole session | 2.0 | 56 | $+28,816 | +0.01 | 10/14 | $+19,319 | 233/2001 | 0.1164 | yes |
| ORB | quad_witching | event day | before 14:00 ET | 1.5 | 36 | $+6,151 | +0.03 | 11/14 | $+3,497 | 253/2001 | 0.1264 | yes |
| ORB | quad_witching | event day | before 14:00 ET | 2.0 | 36 | $+12,301 | +0.07 | 11/14 | $+6,993 | 253/2001 | 0.1264 | yes |
| ORB | quad_witching | event day | whole session | 1.5 | 36 | $+6,151 | +0.03 | 11/14 | $+3,497 | 259/2001 | 0.1294 | yes |
| ORB | quad_witching | event day | whole session | 2.0 | 36 | $+12,301 | +0.07 | 11/14 | $+6,993 | 259/2001 | 0.1294 | yes |
| ENGUQ | quad_witching | day before | whole session | 0.0 | 46 | $+8,910 | +0.01 | 10/13 | $+5,538 | 266/2001 | 0.1329 | yes |
| ENGUQ | quad_witching | day before | whole session | 0.5 | 46 | $+4,455 | +0.01 | 10/13 | $+2,769 | 266/2001 | 0.1329 | yes |
| NOISE | nfp | event day | before 14:00 ET | 1.5 | 128 | $+10,781 | +0.10 | 10/15 | $+7,489 | 287/2001 | 0.1434 | NO |
| NOISE | nfp | event day | before 14:00 ET | 2.0 | 128 | $+21,562 | +0.11 | 10/15 | $+14,978 | 287/2001 | 0.1434 | NO |
| ENGUQ | fomc_minutes | event day | whole session | 1.5 | 95 | $+13,335 | +0.01 | 8/15 | $+7,797 | 328/2001 | 0.1639 | yes |
| ENGUQ | fomc_minutes | event day | whole session | 2.0 | 95 | $+26,670 | +0.00 | 8/15 | $+15,595 | 328/2001 | 0.1639 | yes |
| ENGUQ | fomc_decision | event day | before 14:00 ET | 0.0 | 56 | $+8,452 | +0.00 | 11/14 | $+5,475 | 329/2001 | 0.1644 | NO |
| ENGUQ | fomc_decision | event day | before 14:00 ET | 0.5 | 56 | $+4,226 | +0.01 | 11/14 | $+2,737 | 329/2001 | 0.1644 | NO |
| ENGUQ | fomc_minutes | day before | whole session | 0.0 | 62 | $+9,828 | +0.01 | 8/13 | $+3,869 | 336/2001 | 0.1679 | NO |
| ENGUQ | fomc_minutes | day before | whole session | 0.5 | 62 | $+4,914 | +0.01 | 8/13 | $+1,934 | 336/2001 | 0.1679 | NO |
| ORB | cpi | day after | whole session | 1.5 | 93 | $+11,291 | +0.02 | 8/15 | $+5,541 | 339/2001 | 0.1694 | yes |
| ORB | cpi | day after | whole session | 2.0 | 93 | $+22,581 | +0.05 | 8/15 | $+11,082 | 339/2001 | 0.1694 | yes |
| ORB | quarter_end | day after | before 14:00 ET | 0.0 | 51 | $+3,249 | +0.03 | 10/15 | $+703 | 369/2001 | 0.1844 | NO |
| ORB | quarter_end | day after | before 14:00 ET | 0.5 | 51 | $+1,624 | +0.02 | 10/15 | $+352 | 369/2001 | 0.1844 | NO |
| ORB | quarter_start | day before | before 14:00 ET | 0.0 | 51 | $+2,634 | +0.03 | 8/14 | $+88 | 410/2001 | 0.2049 | NO |
| ORB | quarter_start | day before | before 14:00 ET | 0.5 | 51 | $+1,317 | +0.02 | 8/14 | $+44 | 410/2001 | 0.2049 | NO |
| ENGUQ | month_start | event day | whole session | 1.5 | 246 | $+24,450 | +0.00 | 8/15 | $+9,476 | 434/2001 | 0.2169 | yes |
| NOISE | nfp | event day | whole session | 1.5 | 139 | $+9,842 | +0.08 | 9/15 | $+6,443 | 436/2001 | 0.2179 | NO |
| NOISE | nfp | event day | whole session | 2.0 | 139 | $+19,685 | +0.08 | 9/15 | $+12,887 | 436/2001 | 0.2179 | NO |
| ORB | cpi | day after | before 14:00 ET | 1.5 | 85 | $+9,531 | +0.02 | 8/15 | $+3,781 | 445/2001 | 0.2224 | yes |
| ORB | cpi | day after | before 14:00 ET | 2.0 | 85 | $+19,061 | +0.04 | 8/15 | $+7,563 | 445/2001 | 0.2224 | yes |
| ENGUQ | quarter_start | day before | before 14:00 ET | 0.0 | 69 | $+5,253 | +0.01 | 7/14 | $+281 | 468/2001 | 0.2339 | yes |
| ENGUQ | quarter_start | day before | before 14:00 ET | 0.5 | 69 | $+2,627 | +0.01 | 7/14 | $+141 | 468/2001 | 0.2339 | yes |
| NOISE | cpi | day before | whole session | 1.5 | 160 | $+9,624 | +0.03 | 10/15 | $+5,790 | 472/2001 | 0.2359 | yes |
| NOISE | cpi | day before | whole session | 2.0 | 160 | $+19,247 | +0.04 | 10/15 | $+11,581 | 472/2001 | 0.2359 | yes |
| NOISE | cpi | day after | whole session | 1.5 | 186 | $+9,567 | +0.03 | 10/15 | $+5,549 | 478/2001 | 0.2389 | NO |
| NOISE | cpi | day after | whole session | 2.0 | 186 | $+19,134 | +0.06 | 10/15 | $+11,098 | 478/2001 | 0.2389 | NO |
| NOISE | fomc_decision | day after | at/after 14:00 ET | 0.0 | 32 | $+1,136 | +0.01 | 5/8 | $+318 | 491/2001 | 0.2454 | yes |
| NOISE | fomc_decision | day after | at/after 14:00 ET | 0.5 | 32 | $+568 | +0.00 | 5/8 | $+159 | 491/2001 | 0.2454 | yes |
| ENGUQ | quarter_start | day after | whole session | 1.5 | 67 | $+9,432 | +0.01 | 9/14 | $+387 | 525/2001 | 0.2624 | yes |
| NOISE | fomc_minutes | day before | at/after 14:00 ET | 0.0 | 31 | $+830 | +0.03 | 6/10 | $+352 | 531/2001 | 0.2654 | NO |
| NOISE | fomc_minutes | day before | at/after 14:00 ET | 0.5 | 31 | $+415 | +0.01 | 6/10 | $+176 | 531/2001 | 0.2654 | NO |
| NOISE | month_start | day after | whole session | 1.5 | 345 | $+16,053 | +0.02 | 9/15 | $+9,674 | 541/2001 | 0.2704 | NO |
| NOISE | month_start | day after | whole session | 2.0 | 345 | $+32,105 | +0.00 | 9/15 | $+19,347 | 541/2001 | 0.2704 | NO |
| NOISE | cpi | day before | before 14:00 ET | 1.5 | 138 | $+8,191 | +0.03 | 10/15 | $+4,510 | 572/2001 | 0.2859 | yes |
| NOISE | cpi | day before | before 14:00 ET | 2.0 | 138 | $+16,382 | +0.03 | 10/15 | $+9,020 | 572/2001 | 0.2859 | yes |
| NOISE | cpi | day after | at/after 14:00 ET | 1.5 | 39 | $+1,082 | +0.04 | 6/11 | $+268 | 630/2001 | 0.3148 | NO |
| NOISE | cpi | day after | at/after 14:00 ET | 2.0 | 39 | $+2,164 | +0.04 | 6/11 | $+536 | 630/2001 | 0.3148 | NO |
| NOISE | quad_witching | event day | before 14:00 ET | 1.5 | 49 | $+2,994 | +0.06 | 8/14 | $+813 | 633/2001 | 0.3163 | NO |
| NOISE | quad_witching | event day | before 14:00 ET | 2.0 | 49 | $+5,988 | +0.08 | 8/14 | $+1,627 | 633/2001 | 0.3163 | NO |
| NOISE | quad_witching | event day | whole session | 1.5 | 53 | $+2,973 | +0.06 | 9/14 | $+792 | 717/2001 | 0.3583 | NO |
| NOISE | quad_witching | event day | whole session | 2.0 | 53 | $+5,945 | +0.08 | 9/14 | $+1,584 | 717/2001 | 0.3583 | NO |
| ENGUQ | month_end | day before | whole session | 1.5 | 241 | $+15,757 | +0.03 | 10/15 | $+6,282 | 796/2001 | 0.3978 | yes |
| ENGUQ | month_end | day before | whole session | 2.0 | 241 | $+31,513 | +0.04 | 10/15 | $+12,563 | 796/2001 | 0.3978 | yes |
| ORB | fomc_minutes | day after | before 14:00 ET | 1.5 | 46 | $+3,667 | +0.00 | 9/15 | $+1,933 | 904/2001 | 0.4518 | NO |
| ORB | fomc_minutes | day after | before 14:00 ET | 2.0 | 46 | $+7,335 | +0.00 | 9/15 | $+3,865 | 904/2001 | 0.4518 | NO |
| ORB | fomc_minutes | day after | whole session | 1.5 | 48 | $+3,669 | +0.00 | 9/15 | $+1,934 | 905/2001 | 0.4523 | NO |
| ORB | fomc_minutes | day after | whole session | 2.0 | 48 | $+7,338 | +0.00 | 9/15 | $+3,869 | 905/2001 | 0.4523 | NO |
| NOISE | fomc_decision | day before | before 14:00 ET | 1.5 | 93 | $+2,873 | +0.03 | 8/15 | $+1,434 | 1140/2001 | 0.5697 | NO |
| NOISE | fomc_decision | day before | before 14:00 ET | 2.0 | 93 | $+5,745 | +0.03 | 8/15 | $+2,868 | 1140/2001 | 0.5697 | NO |
| NOISE | fomc_decision | day before | whole session | 1.5 | 117 | $+2,785 | +0.03 | 8/15 | $+949 | 1190/2001 | 0.5947 | NO |
| NOISE | fomc_decision | day before | whole session | 2.0 | 117 | $+5,570 | +0.02 | 8/15 | $+1,898 | 1190/2001 | 0.5947 | NO |

## Year tables

Per-calendar-year net change the rule makes, for every cell that cleared B0-B2 (the cells where a year table can even be read).

**NOISE · fomc_decision · event day · before 14:00 ET · m=0.0** — years positive 14/15, drop-best-year Δ $+8,497, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +161 | +243 | -676 | +423 | +111 | +606 | +428 | +1,288 | +327 | +707 | +1,483 | +8,726 | +1,053 | +1,977 | +366 |

**NOISE · fomc_decision · event day · before 14:00 ET · m=0.5** — years positive 14/15, drop-best-year Δ $+4,248, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +81 | +121 | -338 | +212 | +56 | +303 | +214 | +644 | +164 | +353 | +741 | +4,363 | +526 | +988 | +183 |

**NOISE · fomc_decision · event day · at/after 14:00 ET · m=1.5** — years positive 6/15, drop-best-year Δ $+709, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -123 | -21 | -21 | +399 | -38 | -19 | +549 | -296 | -1,451 | +711 | -729 | +3,338 | +484 | +2,618 | -1,354 |

**NOISE · fomc_decision · event day · at/after 14:00 ET · m=2.0** — years positive 6/15, drop-best-year Δ $+1,419, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -246 | -41 | -41 | +797 | -76 | -39 | +1,098 | -592 | -2,901 | +1,422 | -1,458 | +6,675 | +969 | +5,235 | -2,709 |

**NOISE · fomc_decision · day before · whole session · m=1.5** — years positive 8/15, drop-best-year Δ $+949, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +66 | +209 | -63 | -35 | +511 | -293 | -160 | -70 | +583 | -654 | +321 | +313 | -951 | +1,174 | +1,836 |

**NOISE · fomc_decision · day before · whole session · m=2.0** — years positive 8/15, drop-best-year Δ $+1,898, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +131 | +418 | -127 | -71 | +1,022 | -585 | -320 | -141 | +1,166 | -1,308 | +641 | +627 | -1,903 | +2,347 | +3,672 |

**NOISE · fomc_decision · day before · before 14:00 ET · m=1.5** — years positive 8/15, drop-best-year Δ $+1,434, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +66 | +209 | -1 | -35 | +511 | -293 | -160 | -70 | +368 | -522 | +323 | +673 | -951 | +1,317 | +1,439 |

**NOISE · fomc_decision · day before · before 14:00 ET · m=2.0** — years positive 8/15, drop-best-year Δ $+2,868, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +131 | +418 | -3 | -71 | +1,022 | -585 | -320 | -141 | +737 | -1,044 | +647 | +1,345 | -1,903 | +2,633 | +2,877 |

**NOISE · fomc_decision · day after · at/after 14:00 ET · m=0.0** — years positive 5/8, drop-best-year Δ $+318, B3 PASS

| year | 2011 | 2012 | 2013 | 2016 | 2018 | 2019 | 2021 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -189 | +385 | +36 | -168 | -81 | +275 | +818 | +61 |

**NOISE · fomc_decision · day after · at/after 14:00 ET · m=0.5** — years positive 5/8, drop-best-year Δ $+159, B3 PASS

| year | 2011 | 2012 | 2013 | 2016 | 2018 | 2019 | 2021 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -95 | +192 | +18 | -84 | -41 | +138 | +409 | +30 |

**NOISE · cpi · event day · whole session · m=0.0** — years positive 9/15, drop-best-year Δ $-6,020, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -83 | -245 | +1,121 | +519 | +77 | +304 | +277 | +222 | -3,386 | -182 | +1,218 | +3,672 | -7,859 | +7,854 | -1,674 |

**NOISE · cpi · event day · whole session · m=0.5** — years positive 9/15, drop-best-year Δ $-3,010, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -42 | -122 | +560 | +259 | +39 | +152 | +138 | +111 | -1,693 | -91 | +609 | +1,836 | -3,930 | +3,927 | -837 |

**NOISE · cpi · event day · at/after 14:00 ET · m=0.0** — years positive 11/13, drop-best-year Δ $+3,924, B3 PASS

| year | 2010 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -99 | +465 | +6 | +162 | +406 | -518 | +373 | +246 | +636 | +486 | +816 | +946 | +1,672 |

**NOISE · cpi · event day · at/after 14:00 ET · m=0.5** — years positive 11/13, drop-best-year Δ $+1,962, B3 PASS

| year | 2010 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -50 | +232 | +3 | +81 | +203 | -259 | +186 | +123 | +318 | +243 | +408 | +473 | +836 |

**NOISE · cpi · day before · whole session · m=1.5** — years positive 10/15, drop-best-year Δ $+5,790, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -48 | -52 | +341 | +363 | +151 | +749 | +713 | +55 | +1,917 | +838 | +3,805 | -1,489 | -670 | +3,833 | -881 |

**NOISE · cpi · day before · whole session · m=2.0** — years positive 10/15, drop-best-year Δ $+11,581, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -96 | -104 | +682 | +726 | +302 | +1,498 | +1,425 | +109 | +3,834 | +1,676 | +7,609 | -2,979 | -1,340 | +7,666 | -1,762 |

**NOISE · cpi · day before · before 14:00 ET · m=1.5** — years positive 10/15, drop-best-year Δ $+4,510, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -48 | -86 | +397 | +363 | +151 | +882 | +829 | +40 | +1,917 | +1,384 | +3,213 | -1,669 | -1,229 | +3,681 | -1,633 |

**NOISE · cpi · day before · before 14:00 ET · m=2.0** — years positive 10/15, drop-best-year Δ $+9,020, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -96 | -172 | +794 | +726 | +302 | +1,764 | +1,657 | +80 | +3,834 | +2,768 | +6,426 | -3,338 | -2,458 | +7,362 | -3,266 |

**NOISE · cpi · day after · whole session · m=1.5** — years positive 10/15, drop-best-year Δ $+5,549, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +116 | -133 | +298 | +526 | +160 | +1,257 | +91 | +112 | -292 | -412 | -1,049 | +2,282 | +4,018 | +2,895 | -302 |

**NOISE · cpi · day after · whole session · m=2.0** — years positive 10/15, drop-best-year Δ $+11,098, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +232 | -265 | +595 | +1,051 | +319 | +2,515 | +183 | +224 | -584 | -823 | -2,098 | +4,563 | +8,036 | +5,789 | -603 |

**NOISE · cpi · day after · at/after 14:00 ET · m=1.5** — years positive 6/11, drop-best-year Δ $+268, B3 PASS

| year | 2010 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -71 | +122 | +408 | -62 | -156 | +44 | -74 | -195 | +129 | +814 | +122 |

**NOISE · cpi · day after · at/after 14:00 ET · m=2.0** — years positive 6/11, drop-best-year Δ $+536, B3 PASS

| year | 2010 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -143 | +244 | +817 | -123 | -312 | +89 | -148 | -391 | +258 | +1,629 | +244 |

**NOISE · nfp · event day · whole session · m=1.5** — years positive 9/15, drop-best-year Δ $+6,443, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -66 | -427 | +152 | -8 | -174 | +407 | +833 | +787 | +2,980 | +2,747 | -37 | +3,399 | -1,634 | +243 | +640 |

**NOISE · nfp · event day · whole session · m=2.0** — years positive 9/15, drop-best-year Δ $+12,887, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -131 | -855 | +305 | -17 | -347 | +815 | +1,666 | +1,574 | +5,960 | +5,493 | -74 | +6,798 | -3,268 | +485 | +1,280 |

**NOISE · nfp · event day · before 14:00 ET · m=1.5** — years positive 10/15, drop-best-year Δ $+7,489, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -66 | -427 | +156 | +25 | -188 | +407 | +854 | +787 | +2,975 | +2,747 | -37 | +3,292 | -791 | +408 | +640 |

**NOISE · nfp · event day · before 14:00 ET · m=2.0** — years positive 10/15, drop-best-year Δ $+14,978, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -131 | -855 | +311 | +49 | -376 | +815 | +1,708 | +1,574 | +5,951 | +5,493 | -74 | +6,584 | -1,582 | +816 | +1,280 |

**NOISE · nfp · day after · whole session · m=1.5** — years positive 11/15, drop-best-year Δ $+7,554, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -91 | +198 | -109 | +54 | +110 | +312 | -301 | +352 | -167 | +1,307 | +1,772 | +1,248 | +5,258 | +1,538 | +1,331 |

**NOISE · nfp · day after · whole session · m=2.0** — years positive 11/15, drop-best-year Δ $+15,109, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -181 | +396 | -218 | +107 | +221 | +624 | -602 | +704 | -335 | +2,615 | +3,544 | +2,496 | +10,515 | +3,076 | +2,661 |

**NOISE · nfp · day after · before 14:00 ET · m=1.5** — years positive 11/15, drop-best-year Δ $+6,269, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -91 | +120 | -211 | +17 | +110 | +293 | -221 | +352 | -167 | +1,549 | +571 | +1,248 | +5,258 | +1,574 | +1,126 |

**NOISE · nfp · day after · before 14:00 ET · m=2.0** — years positive 11/15, drop-best-year Δ $+12,538, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -181 | +240 | -422 | +33 | +221 | +585 | -441 | +704 | -335 | +3,098 | +1,141 | +2,496 | +10,515 | +3,148 | +2,252 |

**NOISE · fomc_minutes · event day · whole session · m=0.0** — years positive 11/15, drop-best-year Δ $+4,426, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +18 | +507 | +839 | -527 | -1,795 | +69 | -1,955 | +627 | +358 | +3,293 | -3,069 | +4,724 | +2,419 | +1,418 | +2,226 |

**NOISE · fomc_minutes · event day · whole session · m=0.5** — years positive 11/15, drop-best-year Δ $+2,213, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +9 | +254 | +420 | -264 | -898 | +34 | -978 | +314 | +179 | +1,646 | -1,535 | +2,362 | +1,209 | +709 | +1,113 |

**NOISE · fomc_minutes · event day · before 14:00 ET · m=0.0** — years positive 9/14, drop-best-year Δ $+259, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +62 | +286 | +657 | -669 | -1,795 | -700 | -1,955 | +396 | +467 | +2,771 | -3,069 | +4,724 | +2,392 | +1,418 |

**NOISE · fomc_minutes · event day · before 14:00 ET · m=0.5** — years positive 9/14, drop-best-year Δ $+130, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +31 | +143 | +328 | -335 | -898 | -350 | -978 | +198 | +233 | +1,385 | -1,535 | +2,362 | +1,196 | +709 |

**NOISE · fomc_minutes · day before · whole session · m=0.0** — years positive 11/15, drop-best-year Δ $-3,676, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +318 | +761 | -609 | +501 | -831 | +595 | +310 | +51 | -4,584 | +1,133 | +1,397 | +4,397 | -7,179 | +2,456 | +2,005 |

**NOISE · fomc_minutes · day before · whole session · m=0.5** — years positive 11/15, drop-best-year Δ $-1,838, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +159 | +381 | -305 | +250 | -415 | +298 | +155 | +25 | -2,292 | +566 | +699 | +2,199 | -3,590 | +1,228 | +1,002 |

**NOISE · fomc_minutes · day before · at/after 14:00 ET · m=0.0** — years positive 6/10, drop-best-year Δ $+352, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2019 | 2020 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +317 | +81 | -89 | -227 | +456 | -319 | +406 | +226 | -498 | +478 |

**NOISE · fomc_minutes · day before · at/after 14:00 ET · m=0.5** — years positive 6/10, drop-best-year Δ $+176, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2019 | 2020 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +158 | +41 | -45 | -114 | +228 | -160 | +203 | +113 | -249 | +239 |

**NOISE · fomc_minutes · day after · whole session · m=1.5** — years positive 13/15, drop-best-year Δ $+8,348, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +142 | +81 | +63 | +279 | +848 | +691 | -10 | +432 | +234 | -796 | +765 | +3,043 | +5,683 | +829 | +1,746 |

**NOISE · fomc_minutes · day after · whole session · m=2.0** — years positive 13/15, drop-best-year Δ $+16,695, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +284 | +161 | +125 | +558 | +1,697 | +1,382 | -20 | +865 | +468 | -1,593 | +1,529 | +6,087 | +11,366 | +1,658 | +3,492 |

**NOISE · fomc_minutes · day after · before 14:00 ET · m=1.5** — years positive 13/15, drop-best-year Δ $+8,795, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +142 | +96 | +141 | +266 | +934 | +594 | -10 | +443 | +430 | -897 | +1,083 | +2,999 | +5,683 | +829 | +1,746 |

**NOISE · fomc_minutes · day after · before 14:00 ET · m=2.0** — years positive 13/15, drop-best-year Δ $+17,590, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +284 | +192 | +282 | +531 | +1,868 | +1,188 | -20 | +886 | +859 | -1,795 | +2,167 | +5,997 | +11,366 | +1,658 | +3,492 |

**NOISE · quad_witching · event day · whole session · m=1.5** — years positive 9/14, drop-best-year Δ $+792, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -64 | +117 | +162 | +142 | -120 | +6 | +34 | -268 | -366 | +155 | +1,039 | +2,181 | +813 | -856 |

**NOISE · quad_witching · event day · whole session · m=2.0** — years positive 9/14, drop-best-year Δ $+1,584, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -128 | +234 | +324 | +283 | -241 | +12 | +67 | -536 | -733 | +309 | +2,079 | +4,361 | +1,627 | -1,712 |

**NOISE · quad_witching · event day · before 14:00 ET · m=1.5** — years positive 8/14, drop-best-year Δ $+813, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -64 | +117 | +162 | +142 | -120 | -38 | +99 | -268 | -366 | +155 | +1,039 | +2,181 | +813 | -856 |

**NOISE · quad_witching · event day · before 14:00 ET · m=2.0** — years positive 8/14, drop-best-year Δ $+1,627, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -128 | +234 | +324 | +283 | -241 | -77 | +198 | -536 | -733 | +309 | +2,079 | +4,361 | +1,627 | -1,712 |

**NOISE · month_start · day before · at/after 14:00 ET · m=1.5** — years positive 6/15, drop-best-year Δ $-1,592, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -0 | -11 | -258 | -60 | -0 | +207 | -196 | -123 | +339 | +359 | -547 | +172 | +197 | +1,623 | -1,668 |

**NOISE · month_start · day before · at/after 14:00 ET · m=2.0** — years positive 6/15, drop-best-year Δ $-3,184, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1 | -22 | -516 | -121 | -1 | +413 | -392 | -246 | +678 | +717 | -1,095 | +343 | +394 | +3,245 | -3,337 |

**NOISE · month_start · day after · whole session · m=1.5** — years positive 9/15, drop-best-year Δ $+9,674, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +134 | -67 | -39 | +483 | -708 | +297 | -1,044 | -701 | +2,223 | +1,661 | +1,845 | +4,433 | +6,379 | -895 | +2,051 |

**NOISE · month_start · day after · whole session · m=2.0** — years positive 9/15, drop-best-year Δ $+19,347, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +268 | -134 | -78 | +966 | -1,417 | +593 | -2,089 | -1,401 | +4,447 | +3,323 | +3,691 | +8,866 | +12,758 | -1,789 | +4,103 |

**NOISE · month_start · day after · at/after 14:00 ET · m=1.5** — years positive 5/12, drop-best-year Δ $+1,128, B3 FAIL

| year | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -9 | -135 | -75 | -4 | +26 | -68 | +169 | -33 | -11 | +1,051 | +515 | +754 |

**NOISE · month_start · day after · at/after 14:00 ET · m=2.0** — years positive 5/12, drop-best-year Δ $+2,256, B3 FAIL

| year | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -19 | -271 | -151 | -8 | +52 | -137 | +338 | -66 | -22 | +2,101 | +1,031 | +1,507 |

**NOISE · month_end · event day · at/after 14:00 ET · m=0.0** — years positive 10/14, drop-best-year Δ $+1,909, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -79 | +174 | +363 | +31 | -444 | -99 | +303 | +379 | -715 | +178 | +480 | +166 | +1,778 | +1,172 |

**NOISE · month_end · event day · at/after 14:00 ET · m=0.5** — years positive 10/14, drop-best-year Δ $+954, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -39 | +87 | +181 | +15 | -222 | -49 | +152 | +189 | -358 | +89 | +240 | +83 | +889 | +586 |

**NOISE · month_end · day after · at/after 14:00 ET · m=1.5** — years positive 6/15, drop-best-year Δ $-1,592, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -0 | -11 | -258 | -60 | -0 | +207 | -196 | -123 | +339 | +359 | -547 | +172 | +197 | +1,623 | -1,668 |

**NOISE · month_end · day after · at/after 14:00 ET · m=2.0** — years positive 6/15, drop-best-year Δ $-3,184, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1 | -22 | -516 | -121 | -1 | +413 | -392 | -246 | +678 | +717 | -1,095 | +343 | +394 | +3,245 | -3,337 |

**NOISE · quarter_start · event day · at/after 14:00 ET · m=0.0** — years positive 4/7, drop-best-year Δ $-159, B3 FAIL

| year | 2011 | 2013 | 2016 | 2018 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +101 | -179 | +345 | -519 | -169 | +652 | +261 |

**NOISE · quarter_start · event day · at/after 14:00 ET · m=0.5** — years positive 4/7, drop-best-year Δ $-80, B3 FAIL

| year | 2011 | 2013 | 2016 | 2018 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +50 | -89 | +173 | -260 | -84 | +326 | +131 |

**NOISE · quarter_start · day before · at/after 14:00 ET · m=0.0** — years positive 4/9, drop-best-year Δ $-478, B3 FAIL

| year | 2011 | 2013 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +101 | -193 | +345 | -14 | -519 | +563 | -64 | -394 | +261 |

**NOISE · quarter_start · day before · at/after 14:00 ET · m=0.5** — years positive 4/9, drop-best-year Δ $-239, B3 FAIL

| year | 2011 | 2013 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +50 | -97 | +173 | -7 | -260 | +281 | -32 | -197 | +131 |

**NOISE · quarter_end · day before · at/after 14:00 ET · m=1.5** — years positive 4/10, drop-best-year Δ $-97, B3 FAIL

| year | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -18 | -15 | +174 | +136 | +22 | -54 | -184 | +886 | -83 | -75 |

**NOISE · quarter_end · day before · at/after 14:00 ET · m=2.0** — years positive 4/10, drop-best-year Δ $-194, B3 FAIL

| year | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -36 | -31 | +349 | +272 | +44 | -108 | -368 | +1,772 | -166 | -151 |

**NOISE · quarter_end · day after · at/after 14:00 ET · m=0.0** — years positive 4/9, drop-best-year Δ $-478, B3 FAIL

| year | 2011 | 2013 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +101 | -193 | +345 | -14 | -519 | +563 | -64 | -394 | +261 |

**NOISE · quarter_end · day after · at/after 14:00 ET · m=0.5** — years positive 4/9, drop-best-year Δ $-239, B3 FAIL

| year | 2011 | 2013 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +50 | -97 | +173 | -7 | -260 | +281 | -32 | -197 | +131 |

**NOISE · fed_blackout · day after · at/after 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $+1,430, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -123 | -89 | -165 | +257 | -22 | +261 | +368 | -440 | -1,355 | +396 | -547 | +4,189 | +2,601 | +2,191 | -1,903 |

**NOISE · fed_blackout · day after · at/after 14:00 ET · m=2.0** — years positive 7/15, drop-best-year Δ $+2,861, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -246 | -179 | -329 | +513 | -44 | +522 | +736 | -881 | -2,710 | +792 | -1,093 | +8,377 | +5,202 | +4,382 | -3,805 |

**ORB · fomc_decision · event day · before 14:00 ET · m=0.0** — years positive 8/13, drop-best-year Δ $-555, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -271 | +1,073 | -1,757 | +11 | -376 | -1,209 | -182 | +226 | +271 | +11 | +7,943 | +1,526 | +122 |

**ORB · fomc_decision · event day · before 14:00 ET · m=0.5** — years positive 8/13, drop-best-year Δ $-277, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -135 | +537 | -878 | +5 | -188 | -605 | -91 | +113 | +136 | +5 | +3,971 | +763 | +61 |

**ORB · fomc_decision · day before · whole session · m=0.0** — years positive 10/15, drop-best-year Δ $-2,332, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +398 | +538 | +1,183 | -86 | -1,286 | +1,399 | +386 | +1,380 | +1,155 | +1,358 | -1,268 | +74 | -3,466 | -4,097 | +3,782 |

**ORB · fomc_decision · day before · whole session · m=0.5** — years positive 10/15, drop-best-year Δ $-1,166, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +199 | +269 | +592 | -43 | -643 | +699 | +193 | +690 | +578 | +679 | -634 | +37 | -1,733 | -2,048 | +1,891 |

**ORB · fomc_decision · day after · whole session · m=1.5** — years positive 6/15, drop-best-year Δ $+6,900, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -178 | -648 | +172 | -28 | +124 | -433 | -685 | -14 | -102 | -1,467 | +3,534 | +6,549 | +7,820 | -12 | +89 |

**ORB · fomc_decision · day after · whole session · m=2.0** — years positive 6/15, drop-best-year Δ $+13,800, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -356 | -1,296 | +344 | -56 | +248 | -866 | -1,371 | -28 | -204 | -2,934 | +7,067 | +13,097 | +15,640 | -24 | +178 |

**ORB · fomc_decision · day after · before 14:00 ET · m=1.5** — years positive 6/15, drop-best-year Δ $+6,811, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -178 | -648 | +172 | -28 | +69 | -433 | -588 | -14 | -102 | -1,467 | +3,402 | +6,549 | +7,820 | -12 | +89 |

**ORB · fomc_decision · day after · before 14:00 ET · m=2.0** — years positive 6/15, drop-best-year Δ $+13,622, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -356 | -1,296 | +344 | -56 | +139 | -866 | -1,175 | -28 | -204 | -2,934 | +6,803 | +13,097 | +15,640 | -24 | +178 |

**ORB · cpi · event day · whole session · m=1.5** — years positive 7/15, drop-best-year Δ $+1,216, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -280 | -687 | +62 | -2 | +46 | -403 | -44 | +344 | +2,037 | -414 | +3,461 | +2,753 | +3,698 | -5,100 | -556 |

**ORB · cpi · event day · whole session · m=2.0** — years positive 7/15, drop-best-year Δ $+2,432, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -559 | -1,374 | +124 | -4 | +91 | -806 | -89 | +688 | +4,075 | -829 | +6,921 | +5,507 | +7,395 | -10,199 | -1,112 |

**ORB · cpi · event day · before 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $+572, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -280 | -687 | +62 | -2 | +101 | -370 | -44 | +212 | +2,043 | -409 | +2,606 | +2,753 | +3,698 | -4,857 | -556 |

**ORB · cpi · event day · before 14:00 ET · m=2.0** — years positive 7/15, drop-best-year Δ $+1,143, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -559 | -1,374 | +124 | -4 | +202 | -740 | -89 | +424 | +4,085 | -818 | +5,212 | +5,507 | +7,395 | -9,713 | -1,112 |

**ORB · cpi · day before · whole session · m=1.5** — years positive 7/15, drop-best-year Δ $+3,824, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +9 | -256 | -75 | -455 | -421 | +193 | +1,238 | -152 | -64 | +731 | +336 | +3,480 | +6,043 | -247 | -493 |

**ORB · cpi · day before · whole session · m=2.0** — years positive 7/15, drop-best-year Δ $+7,647, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +18 | -512 | -150 | -911 | -842 | +387 | +2,475 | -305 | -128 | +1,461 | +673 | +6,960 | +12,086 | -495 | -985 |

**ORB · cpi · day before · before 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $+3,649, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +9 | -183 | +31 | -455 | -421 | +276 | +1,238 | -172 | -64 | +811 | -161 | +3,480 | +3,813 | -247 | -493 |

**ORB · cpi · day before · before 14:00 ET · m=2.0** — years positive 7/15, drop-best-year Δ $+7,298, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +18 | -366 | +62 | -911 | -842 | +552 | +2,475 | -344 | -128 | +1,622 | -321 | +6,960 | +7,627 | -495 | -985 |

**ORB · cpi · day after · whole session · m=1.5** — years positive 8/15, drop-best-year Δ $+5,541, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -361 | -470 | +585 | +567 | -791 | +1,706 | -1,241 | +511 | -222 | +54 | +4,583 | -1,360 | +5,749 | +4,620 | -2,638 |

**ORB · cpi · day after · whole session · m=2.0** — years positive 8/15, drop-best-year Δ $+11,082, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -723 | -940 | +1,170 | +1,133 | -1,582 | +3,412 | -2,482 | +1,021 | -444 | +107 | +9,166 | -2,721 | +11,499 | +9,240 | -5,276 |

**ORB · cpi · day after · before 14:00 ET · m=1.5** — years positive 8/15, drop-best-year Δ $+3,781, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -361 | -470 | +585 | +112 | -846 | +1,711 | -1,143 | +511 | -222 | +54 | +3,013 | -1,360 | +5,749 | +4,836 | -2,638 |

**ORB · cpi · day after · before 14:00 ET · m=2.0** — years positive 8/15, drop-best-year Δ $+7,563, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -723 | -940 | +1,170 | +225 | -1,691 | +3,422 | -2,286 | +1,021 | -444 | +107 | +6,027 | -2,721 | +11,499 | +9,672 | -5,276 |

**ORB · nfp · day after · before 14:00 ET · m=0.0** — years positive 7/14, drop-best-year Δ $-2,127, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +546 | +8 | -12 | +1,016 | -117 | +1,768 | -54 | +1,584 | -1,330 | -2,553 | -2,962 | +13,313 | +4,122 | -4,143 |

**ORB · nfp · day after · before 14:00 ET · m=0.5** — years positive 7/14, drop-best-year Δ $-1,064, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +273 | +4 | -6 | +508 | -59 | +884 | -27 | +792 | -665 | -1,277 | -1,481 | +6,657 | +2,061 | -2,072 |

**ORB · fomc_minutes · event day · whole session · m=1.5** — years positive 7/15, drop-best-year Δ $-1,463, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +169 | -44 | +239 | +331 | +1,091 | -137 | -290 | -288 | -814 | -368 | +1,219 | +391 | +2,064 | -2,656 | -306 |

**ORB · fomc_minutes · event day · whole session · m=2.0** — years positive 7/15, drop-best-year Δ $-2,926, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +337 | -88 | +477 | +661 | +2,182 | -273 | -579 | -575 | -1,628 | -736 | +2,437 | +782 | +4,128 | -5,313 | -611 |

**ORB · fomc_minutes · event day · before 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $-1,115, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +169 | -13 | +239 | +341 | +1,091 | -137 | -290 | -210 | -604 | -368 | +952 | +269 | +2,064 | -2,253 | -300 |

**ORB · fomc_minutes · event day · before 14:00 ET · m=2.0** — years positive 7/15, drop-best-year Δ $-2,229, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +337 | -26 | +477 | +682 | +2,182 | -273 | -579 | -419 | -1,208 | -736 | +1,903 | +538 | +4,128 | -4,507 | -601 |

**ORB · fomc_minutes · day after · whole session · m=1.5** — years positive 9/15, drop-best-year Δ $+1,934, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -5 | +304 | +177 | +433 | +1,031 | +789 | -817 | +470 | -144 | -166 | -208 | +480 | +1,735 | +1,609 | -2,017 |

**ORB · fomc_minutes · day after · whole session · m=2.0** — years positive 9/15, drop-best-year Δ $+3,869, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -11 | +609 | +353 | +866 | +2,062 | +1,578 | -1,634 | +940 | -289 | -332 | -417 | +960 | +3,469 | +3,217 | -4,034 |

**ORB · fomc_minutes · day after · before 14:00 ET · m=1.5** — years positive 9/15, drop-best-year Δ $+1,933, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -5 | +304 | +177 | +431 | +1,031 | +789 | -817 | +470 | -144 | -166 | -208 | +480 | +1,735 | +1,609 | -2,017 |

**ORB · fomc_minutes · day after · before 14:00 ET · m=2.0** — years positive 9/15, drop-best-year Δ $+3,865, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -11 | +609 | +353 | +862 | +2,062 | +1,579 | -1,634 | +940 | -289 | -332 | -417 | +960 | +3,469 | +3,217 | -4,034 |

**ORB · quad_witching · event day · whole session · m=1.5** — years positive 11/14, drop-best-year Δ $+3,497, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +159 | +136 | +124 | +254 | +637 | +102 | -86 | -80 | -374 | +1,929 | +449 | +2,654 | +194 | +52 |

**ORB · quad_witching · event day · whole session · m=2.0** — years positive 11/14, drop-best-year Δ $+6,993, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +319 | +272 | +249 | +507 | +1,273 | +205 | -171 | -161 | -748 | +3,859 | +899 | +5,308 | +387 | +104 |

**ORB · quad_witching · event day · before 14:00 ET · m=1.5** — years positive 11/14, drop-best-year Δ $+3,497, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +159 | +136 | +124 | +254 | +637 | +102 | -86 | -80 | -374 | +1,929 | +449 | +2,654 | +194 | +52 |

**ORB · quad_witching · event day · before 14:00 ET · m=2.0** — years positive 11/14, drop-best-year Δ $+6,993, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +319 | +272 | +249 | +507 | +1,273 | +205 | -171 | -161 | -748 | +3,859 | +899 | +5,308 | +387 | +104 |

**ORB · quad_witching · day before · whole session · m=1.5** — years positive 8/15, drop-best-year Δ $+7,256, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -3 | -329 | -153 | -11 | -5 | +919 | +116 | +229 | -524 | -21 | +152 | +3,737 | +3,189 | +2,523 | +1,174 |

**ORB · quad_witching · day before · whole session · m=2.0** — years positive 8/15, drop-best-year Δ $+14,513, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -6 | -658 | -307 | -21 | -11 | +1,839 | +232 | +459 | -1,048 | -41 | +304 | +7,473 | +6,377 | +5,046 | +2,349 |

**ORB · quad_witching · day before · before 14:00 ET · m=1.5** — years positive 8/15, drop-best-year Δ $+7,457, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -3 | -329 | -51 | -11 | -5 | +919 | +214 | +229 | -524 | -21 | +152 | +3,737 | +3,189 | +2,523 | +1,174 |

**ORB · quad_witching · day before · before 14:00 ET · m=2.0** — years positive 8/15, drop-best-year Δ $+14,914, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -6 | -658 | -101 | -21 | -11 | +1,839 | +428 | +459 | -1,048 | -41 | +304 | +7,473 | +6,377 | +5,046 | +2,349 |

**ORB · month_start · day before · whole session · m=0.0** — years positive 8/15, drop-best-year Δ $-430, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1 | -247 | +158 | +1,499 | +52 | +4,007 | -2,475 | +3,824 | -1,729 | -54 | +2,037 | -6,101 | +7,659 | +1,759 | -3,159 |

**ORB · month_start · day before · whole session · m=0.5** — years positive 8/15, drop-best-year Δ $-215, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1 | -123 | +79 | +750 | +26 | +2,004 | -1,237 | +1,912 | -864 | -27 | +1,018 | -3,051 | +3,829 | +880 | -1,580 |

**ORB · month_start · day before · before 14:00 ET · m=0.0** — years positive 10/15, drop-best-year Δ $+2,699, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1 | +48 | +262 | +1,118 | +52 | +4,007 | -2,475 | +3,824 | -1,729 | +3,184 | +1,910 | -6,101 | +10,357 | +1,759 | -3,159 |

**ORB · month_start · day before · before 14:00 ET · m=0.5** — years positive 10/15, drop-best-year Δ $+1,350, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1 | +24 | +131 | +559 | +26 | +2,004 | -1,237 | +1,912 | -864 | +1,592 | +955 | -3,051 | +5,179 | +880 | -1,580 |

**ORB · month_start · day after · whole session · m=1.5** — years positive 7/15, drop-best-year Δ $+11,901, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -180 | -680 | +321 | -114 | -160 | +1,263 | -546 | -86 | +1,660 | +1,659 | +3,318 | +8,698 | +13,068 | -441 | -2,810 |

**ORB · month_start · day after · whole session · m=2.0** — years positive 7/15, drop-best-year Δ $+23,802, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -360 | -1,360 | +642 | -228 | -320 | +2,526 | -1,092 | -173 | +3,320 | +3,318 | +6,637 | +17,395 | +26,135 | -882 | -5,621 |

**ORB · month_start · day after · before 14:00 ET · m=1.5** — years positive 8/15, drop-best-year Δ $+13,015, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -180 | -650 | +321 | -116 | -62 | +1,193 | -546 | -8 | +1,705 | +1,870 | +3,318 | +8,698 | +12,269 | +283 | -2,810 |

**ORB · month_start · day after · before 14:00 ET · m=2.0** — years positive 8/15, drop-best-year Δ $+26,031, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -360 | -1,299 | +642 | -232 | -124 | +2,387 | -1,092 | -17 | +3,411 | +3,739 | +6,637 | +17,395 | +24,539 | +566 | -5,621 |

**ORB · month_end · event day · whole session · m=0.0** — years positive 11/15, drop-best-year Δ $+11,730, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +873 | -2,019 | +883 | +1,022 | +1,144 | +4,547 | -1,358 | -1,568 | +2,089 | +866 | +5,229 | -1,556 | +10,402 | +680 | +897 |

**ORB · month_end · event day · whole session · m=0.5** — years positive 11/15, drop-best-year Δ $+5,865, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +437 | -1,009 | +442 | +511 | +572 | +2,274 | -679 | -784 | +1,044 | +433 | +2,615 | -778 | +5,201 | +340 | +449 |

**ORB · month_end · event day · before 14:00 ET · m=0.0** — years positive 11/15, drop-best-year Δ $+12,173, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +873 | -1,724 | +988 | +651 | +1,253 | +4,547 | -1,358 | -1,568 | +1,292 | +2,364 | +4,833 | -1,556 | +12,012 | +680 | +897 |

**ORB · month_end · event day · before 14:00 ET · m=0.5** — years positive 11/15, drop-best-year Δ $+6,086, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +437 | -862 | +494 | +326 | +626 | +2,274 | -679 | -784 | +646 | +1,182 | +2,416 | -778 | +6,006 | +340 | +449 |

**ORB · month_end · day before · whole session · m=1.5** — years positive 7/15, drop-best-year Δ $+4,969, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -686 | +1,077 | -715 | -643 | +70 | -960 | -291 | +873 | +5,308 | -713 | -1,208 | +2,286 | +8,154 | +907 | -335 |

**ORB · month_end · day before · whole session · m=2.0** — years positive 7/15, drop-best-year Δ $+9,937, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1,373 | +2,154 | -1,429 | -1,286 | +140 | -1,920 | -583 | +1,746 | +10,616 | -1,426 | -2,416 | +4,572 | +16,308 | +1,814 | -671 |

**ORB · month_end · day before · before 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $+4,918, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -686 | +1,077 | -715 | -578 | +15 | -847 | -291 | +851 | +5,689 | -440 | -1,340 | +1,741 | +8,174 | +777 | -335 |

**ORB · month_end · day before · before 14:00 ET · m=2.0** — years positive 7/15, drop-best-year Δ $+9,836, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1,373 | +2,154 | -1,429 | -1,155 | +31 | -1,694 | -583 | +1,702 | +11,378 | -880 | -2,680 | +3,482 | +16,349 | +1,555 | -671 |

**ORB · month_end · day after · whole session · m=0.0** — years positive 9/15, drop-best-year Δ $+185, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +603 | -247 | +158 | +1,499 | +52 | +4,007 | -2,475 | +3,824 | -1,729 | -54 | +2,037 | -6,101 | +7,659 | +1,759 | -3,149 |

**ORB · month_end · day after · whole session · m=0.5** — years positive 9/15, drop-best-year Δ $+93, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +302 | -123 | +79 | +750 | +26 | +2,004 | -1,237 | +1,912 | -864 | -27 | +1,018 | -3,051 | +3,829 | +880 | -1,574 |

**ORB · month_end · day after · before 14:00 ET · m=0.0** — years positive 11/15, drop-best-year Δ $+3,314, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +603 | +48 | +262 | +1,118 | +52 | +4,007 | -2,475 | +3,824 | -1,729 | +3,184 | +1,910 | -6,101 | +10,357 | +1,759 | -3,149 |

**ORB · month_end · day after · before 14:00 ET · m=0.5** — years positive 11/15, drop-best-year Δ $+1,657, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +302 | +24 | +131 | +559 | +26 | +2,004 | -1,237 | +1,912 | -864 | +1,592 | +955 | -3,051 | +5,179 | +880 | -1,574 |

**ORB · quarter_start · event day · whole session · m=0.0** — years positive 8/15, drop-best-year Δ $-452, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -466 | +307 | +738 | +84 | -1,177 | -1,042 | +773 | +1,121 | -2,217 | -1,502 | +4,176 | -777 | -2,814 | +4,172 | +2,348 |

**ORB · quarter_start · event day · whole session · m=0.5** — years positive 8/15, drop-best-year Δ $-226, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -233 | +153 | +369 | +42 | -588 | -521 | +387 | +560 | -1,109 | -751 | +2,088 | -389 | -1,407 | +2,086 | +1,174 |

**ORB · quarter_start · event day · before 14:00 ET · m=0.0** — years positive 8/15, drop-best-year Δ $-810, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -466 | +307 | +738 | +78 | -1,372 | -1,042 | +773 | +965 | -2,217 | -1,502 | +4,711 | -777 | -2,814 | +4,172 | +2,348 |

**ORB · quarter_start · event day · before 14:00 ET · m=0.5** — years positive 8/15, drop-best-year Δ $-405, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -233 | +153 | +369 | +39 | -686 | -521 | +387 | +483 | -1,109 | -751 | +2,355 | -389 | -1,407 | +2,086 | +1,174 |

**ORB · quarter_start · day before · whole session · m=0.0** — years positive 7/14, drop-best-year Δ $-1,054, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -378 | -212 | +193 | -157 | -811 | +583 | +71 | +789 | -119 | -713 | +800 | +1,817 | +936 | -2,038 |

**ORB · quarter_start · day before · whole session · m=0.5** — years positive 7/14, drop-best-year Δ $-527, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -189 | -106 | +97 | -78 | -406 | +292 | +36 | +395 | -60 | -357 | +400 | +908 | +468 | -1,019 |

**ORB · quarter_start · day before · before 14:00 ET · m=0.0** — years positive 8/14, drop-best-year Δ $+88, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -378 | +82 | +298 | -167 | -811 | +583 | +71 | +789 | -119 | -713 | +674 | +1,817 | +2,546 | -2,038 |

**ORB · quarter_start · day before · before 14:00 ET · m=0.5** — years positive 8/14, drop-best-year Δ $+44, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -189 | +41 | +149 | -84 | -406 | +292 | +36 | +395 | -60 | -357 | +337 | +908 | +1,273 | -1,019 |

**ORB · quarter_end · event day · whole session · m=0.0** — years positive 9/15, drop-best-year Δ $+7,054, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +396 | -1,488 | +425 | -423 | +823 | +1,384 | -865 | -1,064 | +3,432 | +1,407 | +4,446 | +3,689 | -687 | -778 | +801 |

**ORB · quarter_end · event day · whole session · m=0.5** — years positive 9/15, drop-best-year Δ $+3,527, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +198 | -744 | +213 | -212 | +412 | +692 | -432 | -532 | +1,716 | +703 | +2,223 | +1,845 | -344 | -389 | +401 |

**ORB · quarter_end · event day · before 14:00 ET · m=0.0** — years positive 10/15, drop-best-year Δ $+9,062, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +396 | -1,194 | +529 | -423 | +823 | +1,384 | -865 | -1,064 | +3,432 | +1,407 | +3,786 | +3,689 | +922 | -778 | +801 |

**ORB · quarter_end · event day · before 14:00 ET · m=0.5** — years positive 10/15, drop-best-year Δ $+4,531, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +198 | -597 | +265 | -212 | +412 | +692 | -432 | -532 | +1,716 | +703 | +1,893 | +1,845 | +461 | -389 | +401 |

**ORB · quarter_end · day before · whole session · m=0.0** — years positive 9/15, drop-best-year Δ $-501, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +472 | -908 | +690 | +124 | -313 | +793 | -681 | -70 | -3,317 | +808 | +2,392 | +2,100 | -1,583 | +582 | +801 |

**ORB · quarter_end · day before · whole session · m=0.5** — years positive 9/15, drop-best-year Δ $-250, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +236 | -454 | +345 | +62 | -157 | +397 | -340 | -35 | -1,659 | +404 | +1,196 | +1,050 | -792 | +291 | +401 |

**ORB · quarter_end · day before · before 14:00 ET · m=0.0** — years positive 9/15, drop-best-year Δ $-634, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +472 | -908 | +690 | +124 | -313 | +623 | -681 | -26 | -3,284 | +808 | +2,392 | +2,100 | -1,624 | +582 | +801 |

**ORB · quarter_end · day before · before 14:00 ET · m=0.5** — years positive 9/15, drop-best-year Δ $-317, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +236 | -454 | +345 | +62 | -157 | +311 | -340 | -13 | -1,642 | +404 | +1,196 | +1,050 | -812 | +291 | +401 |

**ORB · quarter_end · day after · whole session · m=0.0** — years positive 9/15, drop-best-year Δ $-439, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +226 | -212 | +193 | -157 | -811 | +583 | +71 | +789 | -119 | -713 | +800 | +1,817 | +936 | -2,038 | +11 |

**ORB · quarter_end · day after · whole session · m=0.5** — years positive 9/15, drop-best-year Δ $-220, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +113 | -106 | +97 | -78 | -406 | +292 | +36 | +395 | -60 | -357 | +400 | +908 | +468 | -1,019 | +5 |

**ORB · quarter_end · day after · before 14:00 ET · m=0.0** — years positive 10/15, drop-best-year Δ $+703, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +226 | +82 | +298 | -167 | -811 | +583 | +71 | +789 | -119 | -713 | +674 | +1,817 | +2,546 | -2,038 | +11 |

**ORB · quarter_end · day after · before 14:00 ET · m=0.5** — years positive 10/15, drop-best-year Δ $+352, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +113 | +41 | +149 | -84 | -406 | +292 | +36 | +395 | -60 | -357 | +337 | +908 | +1,273 | -1,019 | +5 |

**ORB · fed_blackout · day after · at/after 14:00 ET · m=1.5** — years positive 6/13, drop-best-year Δ $+792, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +144 | -118 | +93 | -6 | -116 | -78 | -1,609 | +1,254 | -5 | +545 | +1,287 | +729 | -40 |

**ORB · fed_blackout · day after · at/after 14:00 ET · m=2.0** — years positive 6/13, drop-best-year Δ $+1,584, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +289 | -236 | +187 | -12 | -232 | -156 | -3,218 | +2,508 | -11 | +1,089 | +2,574 | +1,457 | -81 |

**ENGUQ · fomc_decision · event day · before 14:00 ET · m=0.0** — years positive 11/14, drop-best-year Δ $+5,475, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +711 | +311 | -276 | +24 | -1,248 | +1,464 | +894 | +11 | +722 | +832 | +2,826 | +2,977 | -1,885 | +1,086 |

**ENGUQ · fomc_decision · event day · before 14:00 ET · m=0.5** — years positive 11/14, drop-best-year Δ $+2,737, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +356 | +156 | -138 | +12 | -624 | +732 | +447 | +5 | +361 | +416 | +1,413 | +1,488 | -942 | +543 |

**ENGUQ · fomc_decision · day before · whole session · m=0.0** — years positive 9/13, drop-best-year Δ $-6,310, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -296 | +141 | +750 | +1,266 | +1,511 | +1,730 | -858 | +3,853 | -2,393 | -16,762 | +3,688 | +7,896 | +1,061 |

**ENGUQ · fomc_decision · day before · whole session · m=0.5** — years positive 9/13, drop-best-year Δ $-3,155, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -148 | +70 | +375 | +633 | +756 | +865 | -429 | +1,927 | -1,196 | -8,381 | +1,844 | +3,948 | +531 |

**ENGUQ · fomc_decision · day after · before 14:00 ET · m=1.5** — years positive 6/14, drop-best-year Δ $+786, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -5 | +1,490 | -190 | +152 | +222 | -486 | -62 | -750 | +290 | +830 | -76 | -5 | -623 | +10,936 |

**ENGUQ · fomc_decision · day after · before 14:00 ET · m=2.0** — years positive 6/14, drop-best-year Δ $+1,571, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -11 | +2,980 | -381 | +304 | +445 | -973 | -124 | -1,501 | +581 | +1,659 | -151 | -11 | -1,246 | +21,872 |

**ENGUQ · cpi · event day · at/after 14:00 ET · m=0.0** — years positive 8/12, drop-best-year Δ $-858, B3 FAIL

| year | 2011 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +302 | +541 | -630 | +11 | +101 | -1,419 | +1,992 | -349 | +786 | +431 | -1,679 | +1,046 |

**ENGUQ · cpi · event day · at/after 14:00 ET · m=0.5** — years positive 8/12, drop-best-year Δ $-429, B3 FAIL

| year | 2011 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +151 | +271 | -315 | +5 | +50 | -709 | +996 | -174 | +393 | +216 | -839 | +523 |

**ENGUQ · cpi · day before · whole session · m=1.5** — years positive 8/14, drop-best-year Δ $+5,149, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -203 | -446 | +423 | +16 | +120 | +2,148 | -309 | +121 | -821 | +4,477 | +2,590 | -2,839 | -128 | +28,329 |

**ENGUQ · cpi · day before · whole session · m=2.0** — years positive 8/14, drop-best-year Δ $+10,297, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -407 | -892 | +845 | +32 | +240 | +4,295 | -617 | +242 | -1,642 | +8,955 | +5,180 | -5,677 | -256 | +56,657 |

**ENGUQ · cpi · day before · before 14:00 ET · m=1.5** — years positive 8/13, drop-best-year Δ $+4,021, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -194 | +423 | -27 | +194 | +1,752 | +54 | +182 | -821 | +611 | +4,466 | -1,715 | -904 | +28,329 |

**ENGUQ · cpi · day before · before 14:00 ET · m=2.0** — years positive 8/13, drop-best-year Δ $+8,041, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -388 | +845 | -54 | +387 | +3,504 | +109 | +363 | -1,642 | +1,222 | +8,933 | -3,430 | -1,808 | +56,657 |

**ENGUQ · cpi · day after · whole session · m=0.0** — years positive 10/15, drop-best-year Δ $+15,896, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +268 | -299 | -1,957 | -1,315 | +467 | -121 | +2,983 | -469 | +3,463 | +174 | +10,996 | +2,600 | +5,516 | +2,192 | +2,393 |

**ENGUQ · cpi · day after · whole session · m=0.5** — years positive 10/15, drop-best-year Δ $+7,948, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +134 | -150 | -978 | -658 | +234 | -60 | +1,491 | -235 | +1,731 | +87 | +5,498 | +1,300 | +2,758 | +1,096 | +1,197 |

**ENGUQ · cpi · day after · before 14:00 ET · m=0.0** — years positive 9/15, drop-best-year Δ $+10,312, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +83 | +623 | -1,460 | -545 | +382 | -788 | +2,042 | -480 | +3,441 | -204 | +11,021 | +3,310 | -676 | +2,192 | +2,393 |

**ENGUQ · cpi · day after · before 14:00 ET · m=0.5** — years positive 9/15, drop-best-year Δ $+5,156, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +42 | +311 | -730 | -273 | +191 | -394 | +1,021 | -240 | +1,721 | -102 | +5,511 | +1,655 | -338 | +1,096 | +1,197 |

**ENGUQ · cpi · day after · at/after 14:00 ET · m=0.0** — years positive 8/13, drop-best-year Δ $-633, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +185 | -922 | -497 | -770 | +86 | +667 | +941 | +11 | +21 | +378 | -25 | -709 | +6,192 |

**ENGUQ · cpi · day after · at/after 14:00 ET · m=0.5** — years positive 8/13, drop-best-year Δ $-317, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +93 | -461 | -248 | -385 | +43 | +333 | +471 | +5 | +11 | +189 | -12 | -355 | +3,096 |

**ENGUQ · nfp · event day · before 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $+9,105, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -5 | -998 | -191 | +872 | -5 | -191 | -14 | +19 | -1,304 | +1,554 | +2,899 | +1,177 | -3,014 | +8,307 | +9,572 |

**ENGUQ · nfp · event day · before 14:00 ET · m=2.0** — years positive 7/15, drop-best-year Δ $+18,210, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -11 | -1,997 | -382 | +1,744 | -11 | -382 | -29 | +38 | -2,607 | +3,108 | +5,797 | +2,355 | -6,029 | +16,614 | +19,144 |

**ENGUQ · nfp · day before · before 14:00 ET · m=1.5** — years positive 8/13, drop-best-year Δ $+9,856, B3 PASS

| year | 2010 | 2011 | 2012 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +20 | +318 | +1,486 | -136 | -108 | -2,195 | +2,202 | +941 | -269 | +8,872 | +2,028 | -3,303 | +10,936 |

**ENGUQ · nfp · day before · before 14:00 ET · m=2.0** — years positive 8/13, drop-best-year Δ $+19,712, B3 PASS

| year | 2010 | 2011 | 2012 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +39 | +636 | +2,973 | -271 | -216 | -4,390 | +4,404 | +1,881 | -538 | +17,745 | +4,055 | -6,606 | +21,872 |

**ENGUQ · nfp · day before · at/after 14:00 ET · m=0.0** — years positive 12/14, drop-best-year Δ $+7,737, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +351 | +181 | +284 | +11 | -619 | -494 | +236 | +140 | +1,687 | +499 | +1,931 | +10,733 | +3,519 | +11 |

**ENGUQ · nfp · day before · at/after 14:00 ET · m=0.5** — years positive 12/14, drop-best-year Δ $+3,868, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +175 | +90 | +142 | +5 | -310 | -247 | +118 | +70 | +843 | +250 | +965 | +5,367 | +1,759 | +5 |

**ENGUQ · nfp · day after · whole session · m=1.5** — years positive 10/14, drop-best-year Δ $+3,352, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -140 | +260 | -261 | +127 | +26 | +800 | +125 | -1,008 | +2,323 | -4,465 | +1,651 | +2,594 | +31,205 | +1,321 |

**ENGUQ · nfp · day after · whole session · m=2.0** — years positive 10/14, drop-best-year Δ $+6,704, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -280 | +520 | -523 | +254 | +52 | +1,600 | +251 | -2,016 | +4,646 | -8,930 | +3,302 | +5,187 | +62,409 | +2,641 |

**ENGUQ · nfp · day after · before 14:00 ET · m=1.5** — years positive 9/14, drop-best-year Δ $+2,416, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -110 | +187 | -193 | +127 | +27 | +903 | +131 | -1,008 | +2,469 | -4,034 | -529 | +2,952 | +32,018 | +1,493 |

**ENGUQ · nfp · day after · before 14:00 ET · m=2.0** — years positive 9/14, drop-best-year Δ $+4,831, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -219 | +375 | -387 | +254 | +53 | +1,806 | +261 | -2,016 | +4,939 | -8,068 | -1,057 | +5,904 | +64,036 | +2,987 |

**ENGUQ · fomc_minutes · event day · whole session · m=1.5** — years positive 8/15, drop-best-year Δ $+7,797, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -663 | -447 | -239 | -126 | +872 | +771 | +11 | -569 | +1,235 | +4,380 | -99 | +2,980 | +5,537 | -4,842 | +4,532 |

**ENGUQ · fomc_minutes · event day · whole session · m=2.0** — years positive 8/15, drop-best-year Δ $+15,595, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1,325 | -894 | -477 | -251 | +1,745 | +1,542 | +22 | -1,138 | +2,469 | +8,760 | -198 | +5,960 | +11,075 | -9,684 | +9,064 |

**ENGUQ · fomc_minutes · event day · before 14:00 ET · m=1.5** — years positive 5/13, drop-best-year Δ $+2,241, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -391 | -271 | -113 | -126 | +872 | -110 | -312 | +1,240 | -370 | +234 | +5,194 | +5,537 | -3,607 |

**ENGUQ · fomc_minutes · event day · at/after 14:00 ET · m=1.5** — years positive 4/12, drop-best-year Δ $+806, B3 FAIL

| year | 2010 | 2011 | 2012 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -272 | -176 | -125 | +881 | +322 | -569 | -5 | +4,750 | -333 | -2,214 | -1,235 | +4,532 |

**ENGUQ · fomc_minutes · event day · at/after 14:00 ET · m=2.0** — years positive 4/12, drop-best-year Δ $+1,613, B3 FAIL

| year | 2010 | 2011 | 2012 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -543 | -351 | -251 | +1,761 | +645 | -1,138 | -11 | +9,500 | -666 | -4,428 | -2,470 | +9,064 |

**ENGUQ · fomc_minutes · day before · whole session · m=0.0** — years positive 8/13, drop-best-year Δ $+3,869, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +1,320 | -1,194 | -857 | -589 | +48 | +766 | -1,721 | +2,164 | +1,469 | +451 | +5,960 | +2,064 | -54 |

**ENGUQ · fomc_minutes · day before · whole session · m=0.5** — years positive 8/13, drop-best-year Δ $+1,934, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +660 | -597 | -428 | -294 | +24 | +383 | -861 | +1,082 | +734 | +226 | +2,980 | +1,032 | -27 |

**ENGUQ · fomc_minutes · day before · before 14:00 ET · m=0.0** — years positive 10/13, drop-best-year Δ $+6,556, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +1,008 | -1,233 | -993 | +266 | -53 | +766 | +556 | +2,243 | +1,480 | +451 | +5,960 | +2,054 | +11 |

**ENGUQ · fomc_minutes · day before · before 14:00 ET · m=0.5** — years positive 10/13, drop-best-year Δ $+3,278, B3 PASS

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +504 | -616 | -497 | +133 | -27 | +383 | +278 | +1,122 | +740 | +226 | +2,980 | +1,027 | +5 |

**ENGUQ · fomc_minutes · day after · whole session · m=1.5** — years positive 10/14, drop-best-year Δ $+9,659, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -144 | +325 | +122 | +717 | +497 | +1,871 | +611 | +2,280 | +4,131 | -456 | +2,534 | +4,748 | -2,742 | -86 |

**ENGUQ · fomc_minutes · day after · whole session · m=2.0** — years positive 10/14, drop-best-year Δ $+19,319, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -288 | +650 | +244 | +1,435 | +993 | +3,741 | +1,222 | +4,559 | +8,262 | -911 | +5,069 | +9,497 | -5,484 | -172 |

**ENGUQ · fomc_minutes · day after · before 14:00 ET · m=1.5** — years positive 7/11, drop-best-year Δ $+8,616, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2015 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -78 | +325 | +122 | +671 | -170 | +2,445 | +4,136 | -456 | +2,747 | +5,542 | -1,125 |

**ENGUQ · fomc_minutes · day after · before 14:00 ET · m=2.0** — years positive 7/11, drop-best-year Δ $+17,232, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2015 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -157 | +650 | +244 | +1,341 | -341 | +4,890 | +8,272 | -911 | +5,494 | +11,083 | -2,251 |

**ENGUQ · quad_witching · day before · whole session · m=0.0** — years positive 10/13, drop-best-year Δ $+5,538, B3 PASS

| year | 2010 | 2011 | 2012 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -65 | +474 | +306 | -152 | -65 | +371 | +11 | +748 | +504 | +378 | +3,017 | +3,372 | +11 |

**ENGUQ · quad_witching · day before · whole session · m=0.5** — years positive 10/13, drop-best-year Δ $+2,769, B3 PASS

| year | 2010 | 2011 | 2012 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -32 | +237 | +153 | -76 | -32 | +186 | +5 | +374 | +252 | +189 | +1,508 | +1,686 | +5 |

**ENGUQ · quad_witching · day before · before 14:00 ET · m=0.0** — years positive 8/10, drop-best-year Δ $+6,883, B3 PASS

| year | 2010 | 2011 | 2012 | 2015 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -76 | +172 | +161 | -456 | +795 | +504 | +3,702 | +2,400 | +3,372 | +11 |

**ENGUQ · quad_witching · day before · before 14:00 ET · m=0.5** — years positive 8/10, drop-best-year Δ $+3,442, B3 PASS

| year | 2010 | 2011 | 2012 | 2015 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -38 | +86 | +80 | -228 | +398 | +252 | +1,851 | +1,200 | +1,686 | +5 |

**ENGUQ · quad_witching · day after · whole session · m=1.5** — years positive 5/13, drop-best-year Δ $-901, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -5 | -198 | -88 | -206 | +536 | -78 | +117 | +313 | +302 | +5,925 | -238 | -98 | -1,258 |

**ENGUQ · quad_witching · day after · whole session · m=2.0** — years positive 5/13, drop-best-year Δ $-1,803, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -11 | -396 | -176 | -411 | +1,071 | -157 | +234 | +627 | +604 | +11,851 | -476 | -196 | -2,516 |

**ENGUQ · month_start · event day · whole session · m=1.5** — years positive 8/15, drop-best-year Δ $+9,476, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -513 | +1,145 | +1,450 | +52 | +1,113 | -167 | -1,163 | +80 | -643 | -153 | +14,974 | +2,846 | -3,350 | -3,416 | +12,195 |

**ENGUQ · month_start · day before · whole session · m=0.5** — years positive 8/15, drop-best-year Δ $-6,091, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +596 | +758 | -1,287 | +621 | -1,472 | +167 | -375 | -726 | +2,090 | +933 | -4,497 | -2,974 | +8,536 | +109 | -34 |

**ENGUQ · month_start · day before · before 14:00 ET · m=0.0** — years positive 7/15, drop-best-year Δ $-9,674, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +838 | +1,914 | -2,838 | +904 | -2,421 | -383 | -1,035 | +2,512 | -185 | +1,375 | -3,451 | -6,767 | +17,374 | +283 | -420 |

**ENGUQ · month_start · day before · before 14:00 ET · m=0.5** — years positive 7/15, drop-best-year Δ $-4,837, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +419 | +957 | -1,419 | +452 | -1,211 | -192 | -518 | +1,256 | -93 | +688 | -1,726 | -3,383 | +8,687 | +141 | -210 |

**ENGUQ · month_start · day before · at/after 14:00 ET · m=1.5** — years positive 6/15, drop-best-year Δ $-1,367, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -177 | +199 | -132 | -169 | +262 | -358 | -143 | +1,982 | -2,183 | -245 | +2,772 | -409 | +151 | +32 | -176 |

**ENGUQ · month_start · day before · at/after 14:00 ET · m=2.0** — years positive 6/15, drop-best-year Δ $-2,734, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -354 | +398 | -264 | -338 | +523 | -716 | -286 | +3,964 | -4,365 | -491 | +5,544 | -818 | +301 | +64 | -351 |

**ENGUQ · month_start · day after · before 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $+14,091, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +45 | +701 | +1,696 | -21 | +574 | -1,005 | -457 | -1,008 | -601 | +10,270 | +14,639 | -2,628 | -4,022 | -792 | +11,339 |

**ENGUQ · month_start · day after · at/after 14:00 ET · m=0.0** — years positive 8/14, drop-best-year Δ $-1,380, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -2,834 | +200 | +153 | -383 | -24 | +1,998 | +1,105 | -613 | +120 | -2,255 | +3,252 | +11,588 | +2,533 | -4,632 |

**ENGUQ · month_start · day after · at/after 14:00 ET · m=0.5** — years positive 8/14, drop-best-year Δ $-690, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -1,417 | +100 | +76 | -192 | -12 | +999 | +552 | -307 | +60 | -1,127 | +1,626 | +5,794 | +1,267 | -2,316 |

**ENGUQ · month_end · event day · whole session · m=1.5** — years positive 7/15, drop-best-year Δ $+4,589, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -254 | +1,082 | +1,781 | -769 | -228 | -1,818 | -723 | -104 | -2,149 | +725 | +8,145 | -3,503 | +685 | +10,188 | +1,721 |

**ENGUQ · month_end · event day · at/after 14:00 ET · m=1.5** — years positive 4/14, drop-best-year Δ $-3,716, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -111 | +142 | -202 | -328 | +506 | -78 | -241 | +783 | -1,224 | -1,464 | -746 | -409 | +8,215 | -343 |

**ENGUQ · month_end · event day · at/after 14:00 ET · m=2.0** — years positive 4/14, drop-best-year Δ $-7,431, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -221 | +284 | -404 | -657 | +1,012 | -156 | -483 | +1,566 | -2,448 | -2,928 | -1,491 | -818 | +16,430 | -686 |

**ENGUQ · month_end · day before · whole session · m=1.5** — years positive 10/15, drop-best-year Δ $+6,282, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +2,724 | +1,528 | +426 | -527 | -972 | -2,270 | +676 | +815 | -2,431 | +1,729 | +9,475 | -6,229 | +2,073 | +8,647 | +93 |

**ENGUQ · month_end · day before · whole session · m=2.0** — years positive 10/15, drop-best-year Δ $+12,563, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +5,448 | +3,057 | +851 | -1,054 | -1,944 | -4,540 | +1,352 | +1,630 | -4,862 | +3,457 | +18,950 | -12,458 | +4,145 | +17,294 | +186 |

**ENGUQ · month_end · day before · at/after 14:00 ET · m=1.5** — years positive 6/13, drop-best-year Δ $+134, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -143 | +91 | -175 | -396 | +273 | -131 | +2 | -161 | -5 | +806 | -718 | +5,518 | +693 |

**ENGUQ · month_end · day before · at/after 14:00 ET · m=2.0** — years positive 6/13, drop-best-year Δ $+269, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -287 | +181 | -350 | -793 | +546 | -262 | +4 | -321 | -11 | +1,613 | -1,437 | +11,036 | +1,386 |

**ENGUQ · month_end · day after · whole session · m=0.5** — years positive 8/15, drop-best-year Δ $-6,447, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +240 | +758 | -1,287 | +621 | -1,472 | +167 | -375 | -726 | +2,090 | +933 | -4,497 | -2,974 | +8,536 | +109 | -34 |

**ENGUQ · month_end · day after · before 14:00 ET · m=0.0** — years positive 7/15, drop-best-year Δ $-10,385, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +126 | +1,914 | -2,838 | +904 | -2,421 | -383 | -1,035 | +2,512 | -185 | +1,375 | -3,451 | -6,767 | +17,374 | +283 | -420 |

**ENGUQ · month_end · day after · before 14:00 ET · m=0.5** — years positive 7/15, drop-best-year Δ $-5,193, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +63 | +957 | -1,419 | +452 | -1,211 | -192 | -518 | +1,256 | -93 | +688 | -1,726 | -3,383 | +8,687 | +141 | -210 |

**ENGUQ · month_end · day after · at/after 14:00 ET · m=1.5** — years positive 6/15, drop-best-year Δ $-1,367, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -177 | +199 | -132 | -169 | +262 | -358 | -143 | +1,982 | -2,183 | -245 | +2,772 | -409 | +151 | +32 | -176 |

**ENGUQ · month_end · day after · at/after 14:00 ET · m=2.0** — years positive 6/15, drop-best-year Δ $-2,734, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -354 | +398 | -264 | -338 | +523 | -716 | -286 | +3,964 | -4,365 | -491 | +5,544 | -818 | +301 | +64 | -351 |

**ENGUQ · quarter_start · day before · whole session · m=0.0** — years positive 6/14, drop-best-year Δ $-1,177, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +1,062 | +728 | -2,802 | -46 | -1,115 | +1,293 | -18 | -956 | -1,614 | -82 | +198 | +7,643 | +4,899 | -2,724 |

**ENGUQ · quarter_start · day before · whole session · m=0.5** — years positive 6/14, drop-best-year Δ $-588, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +531 | +364 | -1,401 | -23 | -557 | +646 | -9 | -478 | -807 | -41 | +99 | +3,821 | +2,449 | -1,362 |

**ENGUQ · quarter_start · day before · before 14:00 ET · m=0.0** — years positive 7/14, drop-best-year Δ $+281, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +711 | +647 | -2,877 | -46 | -278 | +722 | -304 | +1,321 | -1,534 | +159 | -468 | +4,972 | +4,888 | -2,660 |

**ENGUQ · quarter_start · day before · before 14:00 ET · m=0.5** — years positive 7/14, drop-best-year Δ $+141, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +356 | +323 | -1,439 | -23 | -139 | +361 | -152 | +660 | -767 | +79 | -234 | +2,486 | +2,444 | -1,330 |

**ENGUQ · quarter_start · day after · whole session · m=1.5** — years positive 9/14, drop-best-year Δ $+387, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +31 | +2,299 | -142 | +3 | +184 | +104 | -1,185 | -341 | +485 | +1,470 | +9,045 | -994 | +708 | -2,234 |

**ENGUQ · quarter_start · day after · before 14:00 ET · m=1.5** — years positive 9/14, drop-best-year Δ $-864, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +31 | +468 | +30 | +68 | -120 | +127 | -577 | -173 | +45 | +1,470 | +9,386 | -886 | +708 | -2,056 |

**ENGUQ · quarter_end · event day · whole session · m=1.5** — years positive 6/15, drop-best-year Δ $-706, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -96 | +1,443 | +1,048 | -58 | -178 | -794 | -66 | -543 | -1,486 | +2,673 | +9,488 | -3,994 | -1,712 | +1,335 | +1,721 |

**ENGUQ · quarter_end · event day · whole session · m=2.0** — years positive 6/15, drop-best-year Δ $-1,412, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -191 | +2,886 | +2,095 | -115 | -355 | -1,587 | -131 | -1,086 | -2,971 | +5,345 | +18,976 | -7,988 | -3,425 | +2,671 | +3,441 |

**ENGUQ · quarter_end · event day · before 14:00 ET · m=1.5** — years positive 7/15, drop-best-year Δ $+570, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -48 | +1,443 | +1,112 | -58 | -596 | -794 | +176 | -543 | -1,486 | +2,673 | +9,488 | -2,659 | -1,707 | +1,335 | +1,721 |

**ENGUQ · quarter_end · event day · before 14:00 ET · m=2.0** — years positive 7/15, drop-best-year Δ $+1,139, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -96 | +2,886 | +2,224 | -115 | -1,192 | -1,587 | +351 | -1,086 | -2,971 | +5,345 | +18,976 | -5,318 | -3,414 | +2,671 | +3,441 |

**ENGUQ · quarter_end · day before · whole session · m=1.5** — years positive 6/15, drop-best-year Δ $-534, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -427 | +1,443 | -330 | -86 | -530 | -700 | +1,198 | -234 | -2,756 | +2,651 | +9,488 | -1,603 | +344 | -514 | +1,010 |

**ENGUQ · quarter_end · day before · whole session · m=2.0** — years positive 6/15, drop-best-year Δ $-1,068, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -853 | +2,886 | -661 | -172 | -1,061 | -1,401 | +2,396 | -467 | -5,513 | +5,303 | +18,976 | -3,206 | +687 | -1,027 | +2,021 |

**ENGUQ · quarter_end · day before · before 14:00 ET · m=1.5** — years positive 6/15, drop-best-year Δ $-387, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -346 | +1,443 | -155 | -86 | -530 | -700 | +1,021 | -176 | -2,751 | +2,651 | +9,488 | -1,603 | +344 | -508 | +1,010 |

**ENGUQ · quarter_end · day before · before 14:00 ET · m=2.0** — years positive 6/15, drop-best-year Δ $-775, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | -692 | +2,886 | -311 | -172 | -1,061 | -1,401 | +2,041 | -351 | -5,502 | +5,303 | +18,976 | -3,206 | +687 | -1,016 | +2,021 |

**ENGUQ · quarter_end · day after · whole session · m=0.0** — years positive 6/14, drop-best-year Δ $-1,888, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +351 | +728 | -2,802 | -46 | -1,115 | +1,293 | -18 | -956 | -1,614 | -82 | +198 | +7,643 | +4,899 | -2,724 |

**ENGUQ · quarter_end · day after · whole session · m=0.5** — years positive 6/14, drop-best-year Δ $-944, B3 FAIL

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +175 | +364 | -1,401 | -23 | -557 | +646 | -9 | -478 | -807 | -41 | +99 | +3,821 | +2,449 | -1,362 |

**ENGUQ · quarter_end · day after · before 14:00 ET · m=0.0** — years positive 6/13, drop-best-year Δ $-430, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +647 | -2,877 | -46 | -278 | +722 | -304 | +1,321 | -1,534 | +159 | -468 | +4,972 | +4,888 | -2,660 |

**ENGUQ · quarter_end · day after · before 14:00 ET · m=0.5** — years positive 6/13, drop-best-year Δ $-215, B3 FAIL

| year | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +323 | -1,439 | -23 | -139 | +361 | -152 | +660 | -767 | +79 | -234 | +2,486 | +2,444 | -1,330 |

**ENGUQ · fed_blackout · day before · whole session · m=1.5** — years positive 12/15, drop-best-year Δ $+26,650, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +604 | +490 | +1,634 | +1,311 | -2,243 | +177 | -1,314 | +3,709 | +4,275 | +3,317 | +5,441 | +9,177 | -9,258 | +39,607 | +9,331 |

**ENGUQ · fed_blackout · day before · whole session · m=2.0** — years positive 12/15, drop-best-year Δ $+53,301, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +1,209 | +980 | +3,268 | +2,621 | -4,485 | +354 | -2,629 | +7,417 | +8,549 | +6,634 | +10,883 | +18,355 | -18,517 | +79,213 | +18,662 |

**ENGUQ · fed_blackout · day before · before 14:00 ET · m=1.5** — years positive 11/15, drop-best-year Δ $+23,628, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +222 | -878 | +495 | +1,645 | -1,706 | +60 | -2,222 | +3,392 | +4,994 | +2,954 | +4,777 | +6,931 | -6,206 | +38,405 | +9,172 |

**ENGUQ · fed_blackout · day before · before 14:00 ET · m=2.0** — years positive 11/15, drop-best-year Δ $+47,257, B3 PASS

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Δnet | +445 | -1,756 | +990 | +3,289 | -3,413 | +120 | -4,445 | +6,784 | +9,989 | +5,908 | +9,553 | +13,861 | -12,411 | +76,810 | +18,344 |


## All 1080 cells

`B0` n_affected>=30 · `B1` net improves · `B2` annualised MAR improves · `B3` not carried by one year · `B4` permutation p<=0.05 AND beats both placebos. The permutation is only run for cells that already cleared B0-B3 (it cannot rescue a cell that failed an earlier clause), so `perm p` is blank elsewhere.

| leg | calendar | offset | clock | m | n_aff | net | ΔNet | MAR | ΔMAR | B0 | B1 | B2 | B3 | B4 | perm p | rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---:|---|
| NOISE | fomc_decision | event day | all | 0.0 | 138 | $261,909 | $+9,129 | 0.80 | -0.17 | Y | Y | no | Y | no |  |  |
| NOISE | fomc_decision | event day | all | 0.5 | 138 | $257,345 | $+4,565 | 0.88 | -0.10 | Y | Y | no | Y | no |  |  |
| NOISE | fomc_decision | event day | all | 1.5 | 138 | $248,215 | $-4,565 | 1.06 | +0.08 | Y | no | Y | no | no |  |  |
| NOISE | fomc_decision | event day | all | 2.0 | 138 | $243,650 | $-9,129 | 1.11 | +0.14 | Y | no | Y | no | no |  |  |
| NOISE | fomc_decision | event day | am | 0.0 | 80 | $270,003 | $+17,223 | 1.11 | +0.14 | Y | Y | Y | Y | Y | 0.0005 | 1/2001 |
| NOISE | fomc_decision | event day | am | 0.5 | 80 | $261,392 | $+8,612 | 1.06 | +0.09 | Y | Y | Y | Y | Y | 0.0005 | 1/2001 |
| NOISE | fomc_decision | event day | am | 1.5 | 80 | $244,168 | $-8,612 | 0.90 | -0.08 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | event day | am | 2.0 | 80 | $235,557 | $-17,223 | 0.83 | -0.15 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | event day | pm | 0.0 | 58 | $244,686 | $-8,094 | 0.69 | -0.28 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | event day | pm | 0.5 | 58 | $248,733 | $-4,047 | 0.81 | -0.16 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | event day | pm | 1.5 | 58 | $256,827 | $+4,047 | 1.11 | +0.14 | Y | Y | Y | no | no |  |  |
| NOISE | fomc_decision | event day | pm | 2.0 | 58 | $260,874 | $+8,094 | 1.24 | +0.26 | Y | Y | Y | no | no |  |  |
| NOISE | fomc_decision | day before | all | 0.0 | 117 | $247,210 | $-5,570 | 0.91 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | day before | all | 0.5 | 117 | $249,995 | $-2,785 | 0.94 | -0.03 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | day before | all | 1.5 | 117 | $255,565 | $+2,785 | 1.00 | +0.03 | Y | Y | Y | Y | no | 0.5947 | 1190/2001 |
| NOISE | fomc_decision | day before | all | 2.0 | 117 | $258,349 | $+5,570 | 1.00 | +0.02 | Y | Y | Y | Y | no | 0.5947 | 1190/2001 |
| NOISE | fomc_decision | day before | am | 0.0 | 93 | $247,035 | $-5,745 | 0.90 | -0.07 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | day before | am | 0.5 | 93 | $249,907 | $-2,873 | 0.94 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | day before | am | 1.5 | 93 | $255,653 | $+2,873 | 1.01 | +0.03 | Y | Y | Y | Y | no | 0.5697 | 1140/2001 |
| NOISE | fomc_decision | day before | am | 2.0 | 93 | $258,525 | $+5,745 | 1.01 | +0.03 | Y | Y | Y | Y | no | 0.5697 | 1140/2001 |
| NOISE | fomc_decision | day before | pm | 0.0 | 24 | $252,956 | $+176 | 0.99 | +0.01 | no | Y | Y | no | no |  |  |
| NOISE | fomc_decision | day before | pm | 0.5 | 24 | $252,868 | $+88 | 0.98 | +0.01 | no | Y | Y | no | no |  |  |
| NOISE | fomc_decision | day before | pm | 1.5 | 24 | $252,692 | $-88 | 0.97 | -0.01 | no | no | no | no | no |  |  |
| NOISE | fomc_decision | day before | pm | 2.0 | 24 | $252,604 | $-176 | 0.96 | -0.01 | no | no | no | no | no |  |  |
| NOISE | fomc_decision | day after | all | 0.0 | 146 | $239,556 | $-13,224 | 1.01 | +0.04 | Y | no | Y | no | no |  |  |
| NOISE | fomc_decision | day after | all | 0.5 | 146 | $246,168 | $-6,612 | 1.00 | +0.03 | Y | no | Y | no | no |  |  |
| NOISE | fomc_decision | day after | all | 1.5 | 146 | $259,392 | $+6,612 | 0.95 | -0.02 | Y | Y | no | Y | no |  |  |
| NOISE | fomc_decision | day after | all | 2.0 | 146 | $266,004 | $+13,224 | 0.93 | -0.04 | Y | Y | no | Y | no |  |  |
| NOISE | fomc_decision | day after | am | 0.0 | 114 | $238,420 | $-14,360 | 1.00 | +0.03 | Y | no | Y | no | no |  |  |
| NOISE | fomc_decision | day after | am | 0.5 | 114 | $245,600 | $-7,180 | 1.00 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | fomc_decision | day after | am | 1.5 | 114 | $259,960 | $+7,180 | 0.96 | -0.02 | Y | Y | no | Y | no |  |  |
| NOISE | fomc_decision | day after | am | 2.0 | 114 | $267,140 | $+14,360 | 0.94 | -0.04 | Y | Y | no | Y | no |  |  |
| NOISE | fomc_decision | day after | pm | 0.0 | 32 | $253,916 | $+1,136 | 0.98 | +0.01 | Y | Y | Y | Y | no | 0.2454 | 491/2001 |
| NOISE | fomc_decision | day after | pm | 0.5 | 32 | $253,348 | $+568 | 0.98 | +0.00 | Y | Y | Y | Y | no | 0.2454 | 491/2001 |
| NOISE | fomc_decision | day after | pm | 1.5 | 32 | $252,212 | $-568 | 0.97 | -0.00 | Y | no | no | no | no |  |  |
| NOISE | fomc_decision | day after | pm | 2.0 | 32 | $251,644 | $-1,136 | 0.97 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | cpi | event day | all | 0.0 | 193 | $254,614 | $+1,834 | 1.08 | +0.11 | Y | Y | Y | no | no |  |  |
| NOISE | cpi | event day | all | 0.5 | 193 | $253,697 | $+917 | 1.03 | +0.05 | Y | Y | Y | no | no |  |  |
| NOISE | cpi | event day | all | 1.5 | 193 | $251,863 | $-917 | 0.92 | -0.05 | Y | no | no | no | no |  |  |
| NOISE | cpi | event day | all | 2.0 | 193 | $250,945 | $-1,834 | 0.85 | -0.13 | Y | no | no | no | no |  |  |
| NOISE | cpi | event day | am | 0.0 | 156 | $249,018 | $-3,762 | 1.03 | +0.05 | Y | no | Y | no | no |  |  |
| NOISE | cpi | event day | am | 0.5 | 156 | $250,899 | $-1,881 | 1.00 | +0.03 | Y | no | Y | no | no |  |  |
| NOISE | cpi | event day | am | 1.5 | 156 | $254,661 | $+1,881 | 0.95 | -0.03 | Y | Y | no | no | no |  |  |
| NOISE | cpi | event day | am | 2.0 | 156 | $256,542 | $+3,762 | 0.89 | -0.09 | Y | Y | no | no | no |  |  |
| NOISE | cpi | event day | pm | 0.0 | 37 | $258,376 | $+5,596 | 1.02 | +0.05 | Y | Y | Y | Y | Y | 0.0225 | 45/2001 |
| NOISE | cpi | event day | pm | 0.5 | 37 | $255,578 | $+2,798 | 1.00 | +0.02 | Y | Y | Y | Y | Y | 0.0225 | 45/2001 |
| NOISE | cpi | event day | pm | 1.5 | 37 | $249,982 | $-2,798 | 0.95 | -0.02 | Y | no | no | no | no |  |  |
| NOISE | cpi | event day | pm | 2.0 | 37 | $247,184 | $-5,596 | 0.93 | -0.05 | Y | no | no | no | no |  |  |
| NOISE | cpi | day before | all | 0.0 | 160 | $233,533 | $-19,247 | 0.86 | -0.12 | Y | no | no | no | no |  |  |
| NOISE | cpi | day before | all | 0.5 | 160 | $243,156 | $-9,624 | 0.91 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | cpi | day before | all | 1.5 | 160 | $262,404 | $+9,624 | 1.01 | +0.03 | Y | Y | Y | Y | no | 0.2359 | 472/2001 |
| NOISE | cpi | day before | all | 2.0 | 160 | $272,027 | $+19,247 | 1.02 | +0.04 | Y | Y | Y | Y | no | 0.2359 | 472/2001 |
| NOISE | cpi | day before | am | 0.0 | 138 | $236,398 | $-16,382 | 0.87 | -0.11 | Y | no | no | no | no |  |  |
| NOISE | cpi | day before | am | 0.5 | 138 | $244,589 | $-8,191 | 0.92 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | cpi | day before | am | 1.5 | 138 | $260,971 | $+8,191 | 1.00 | +0.03 | Y | Y | Y | Y | no | 0.2859 | 572/2001 |
| NOISE | cpi | day before | am | 2.0 | 138 | $269,162 | $+16,382 | 1.01 | +0.03 | Y | Y | Y | Y | no | 0.2859 | 572/2001 |
| NOISE | cpi | day before | pm | 0.0 | 22 | $249,914 | $-2,865 | 0.96 | -0.01 | no | no | no | no | no |  |  |
| NOISE | cpi | day before | pm | 0.5 | 22 | $251,347 | $-1,433 | 0.97 | -0.01 | no | no | no | no | no |  |  |
| NOISE | cpi | day before | pm | 1.5 | 22 | $254,213 | $+1,433 | 0.98 | +0.01 | no | Y | Y | Y | no |  |  |
| NOISE | cpi | day before | pm | 2.0 | 22 | $255,645 | $+2,865 | 0.99 | +0.01 | no | Y | Y | Y | no |  |  |
| NOISE | cpi | day after | all | 0.0 | 186 | $233,646 | $-19,134 | 0.91 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | cpi | day after | all | 0.5 | 186 | $243,213 | $-9,567 | 0.95 | -0.03 | Y | no | no | no | no |  |  |
| NOISE | cpi | day after | all | 1.5 | 186 | $262,347 | $+9,567 | 1.00 | +0.03 | Y | Y | Y | Y | no | 0.2389 | 478/2001 |
| NOISE | cpi | day after | all | 2.0 | 186 | $271,914 | $+19,134 | 1.03 | +0.06 | Y | Y | Y | Y | no | 0.2389 | 478/2001 |
| NOISE | cpi | day after | am | 0.0 | 147 | $235,810 | $-16,970 | 0.92 | -0.05 | Y | no | no | no | no |  |  |
| NOISE | cpi | day after | am | 0.5 | 147 | $244,295 | $-8,485 | 0.97 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | cpi | day after | am | 1.5 | 147 | $261,265 | $+8,485 | 0.95 | -0.03 | Y | Y | no | Y | no |  |  |
| NOISE | cpi | day after | am | 2.0 | 147 | $269,749 | $+16,970 | 0.92 | -0.05 | Y | Y | no | Y | no |  |  |
| NOISE | cpi | day after | pm | 0.0 | 39 | $250,616 | $-2,164 | 0.87 | -0.11 | Y | no | no | no | no |  |  |
| NOISE | cpi | day after | pm | 0.5 | 39 | $251,698 | $-1,082 | 0.92 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | cpi | day after | pm | 1.5 | 39 | $253,862 | $+1,082 | 1.01 | +0.04 | Y | Y | Y | Y | no | 0.3148 | 630/2001 |
| NOISE | cpi | day after | pm | 2.0 | 39 | $254,944 | $+2,164 | 1.02 | +0.04 | Y | Y | Y | Y | no | 0.3148 | 630/2001 |
| NOISE | nfp | event day | all | 0.0 | 139 | $233,095 | $-19,685 | 0.72 | -0.25 | Y | no | no | no | no |  |  |
| NOISE | nfp | event day | all | 0.5 | 139 | $242,937 | $-9,842 | 0.84 | -0.14 | Y | no | no | no | no |  |  |
| NOISE | nfp | event day | all | 1.5 | 139 | $262,622 | $+9,842 | 1.06 | +0.08 | Y | Y | Y | Y | no | 0.2179 | 436/2001 |
| NOISE | nfp | event day | all | 2.0 | 139 | $272,465 | $+19,685 | 1.06 | +0.08 | Y | Y | Y | Y | no | 0.2179 | 436/2001 |
| NOISE | nfp | event day | am | 0.0 | 128 | $231,218 | $-21,562 | 0.71 | -0.27 | Y | no | no | no | no |  |  |
| NOISE | nfp | event day | am | 0.5 | 128 | $241,999 | $-10,781 | 0.83 | -0.15 | Y | no | no | no | no |  |  |
| NOISE | nfp | event day | am | 1.5 | 128 | $263,561 | $+10,781 | 1.07 | +0.10 | Y | Y | Y | Y | no | 0.1434 | 287/2001 |
| NOISE | nfp | event day | am | 2.0 | 128 | $274,342 | $+21,562 | 1.09 | +0.11 | Y | Y | Y | Y | no | 0.1434 | 287/2001 |
| NOISE | nfp | event day | pm | 0.0 | 11 | $254,657 | $+1,877 | 1.00 | +0.03 | no | Y | Y | Y | no |  |  |
| NOISE | nfp | event day | pm | 0.5 | 11 | $253,718 | $+939 | 0.99 | +0.01 | no | Y | Y | Y | no |  |  |
| NOISE | nfp | event day | pm | 1.5 | 11 | $251,841 | $-939 | 0.96 | -0.01 | no | no | no | no | no |  |  |
| NOISE | nfp | event day | pm | 2.0 | 11 | $250,903 | $-1,877 | 0.95 | -0.02 | no | no | no | no | no |  |  |
| NOISE | nfp | day before | all | 0.0 | 195 | $234,656 | $-18,124 | 0.87 | -0.10 | Y | no | no | no | no |  |  |
| NOISE | nfp | day before | all | 0.5 | 195 | $243,718 | $-9,062 | 0.93 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | nfp | day before | all | 1.5 | 195 | $261,842 | $+9,062 | 0.95 | -0.02 | Y | Y | no | Y | no |  |  |
| NOISE | nfp | day before | all | 2.0 | 195 | $270,904 | $+18,124 | 0.93 | -0.04 | Y | Y | no | Y | no |  |  |
| NOISE | nfp | day before | am | 0.0 | 168 | $240,108 | $-12,672 | 1.02 | +0.04 | Y | no | Y | no | no |  |  |
| NOISE | nfp | day before | am | 0.5 | 168 | $246,444 | $-6,336 | 1.00 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | nfp | day before | am | 1.5 | 168 | $259,116 | $+6,336 | 0.96 | -0.02 | Y | Y | no | Y | no |  |  |
| NOISE | nfp | day before | am | 2.0 | 168 | $265,452 | $+12,672 | 0.94 | -0.04 | Y | Y | no | Y | no |  |  |
| NOISE | nfp | day before | pm | 0.0 | 27 | $247,328 | $-5,452 | 0.84 | -0.13 | no | no | no | no | no |  |  |
| NOISE | nfp | day before | pm | 0.5 | 27 | $250,054 | $-2,726 | 0.92 | -0.06 | no | no | no | no | no |  |  |
| NOISE | nfp | day before | pm | 1.5 | 27 | $255,506 | $+2,726 | 0.97 | -0.00 | no | Y | no | Y | no |  |  |
| NOISE | nfp | day before | pm | 2.0 | 27 | $258,232 | $+5,452 | 0.97 | -0.01 | no | Y | no | Y | no |  |  |
| NOISE | nfp | day after | all | 0.0 | 166 | $227,156 | $-25,624 | 0.67 | -0.31 | Y | no | no | no | no |  |  |
| NOISE | nfp | day after | all | 0.5 | 166 | $239,968 | $-12,812 | 0.80 | -0.17 | Y | no | no | no | no |  |  |
| NOISE | nfp | day after | all | 1.5 | 166 | $265,592 | $+12,812 | 1.04 | +0.06 | Y | Y | Y | Y | no | 0.0985 | 197/2001 |
| NOISE | nfp | day after | all | 2.0 | 166 | $278,404 | $+25,624 | 1.06 | +0.09 | Y | Y | Y | Y | no | 0.0985 | 197/2001 |
| NOISE | nfp | day after | am | 0.0 | 137 | $229,727 | $-23,053 | 0.68 | -0.30 | Y | no | no | no | no |  |  |
| NOISE | nfp | day after | am | 0.5 | 137 | $241,253 | $-11,527 | 0.81 | -0.17 | Y | no | no | no | no |  |  |
| NOISE | nfp | day after | am | 1.5 | 137 | $264,306 | $+11,527 | 1.03 | +0.06 | Y | Y | Y | Y | no | 0.1134 | 227/2001 |
| NOISE | nfp | day after | am | 2.0 | 137 | $275,833 | $+23,053 | 1.05 | +0.08 | Y | Y | Y | Y | no | 0.1134 | 227/2001 |
| NOISE | nfp | day after | pm | 0.0 | 29 | $250,209 | $-2,571 | 0.97 | -0.01 | no | no | no | no | no |  |  |
| NOISE | nfp | day after | pm | 0.5 | 29 | $251,494 | $-1,285 | 0.97 | -0.00 | no | no | no | no | no |  |  |
| NOISE | nfp | day after | pm | 1.5 | 29 | $254,065 | $+1,285 | 0.98 | +0.00 | no | Y | Y | Y | no |  |  |
| NOISE | nfp | day after | pm | 2.0 | 29 | $255,351 | $+2,571 | 0.99 | +0.01 | no | Y | Y | Y | no |  |  |
| NOISE | fomc_minutes | event day | all | 0.0 | 123 | $261,930 | $+9,150 | 1.12 | +0.14 | Y | Y | Y | Y | Y | 0.0150 | 30/2001 |
| NOISE | fomc_minutes | event day | all | 0.5 | 123 | $257,355 | $+4,575 | 1.06 | +0.09 | Y | Y | Y | Y | Y | 0.0150 | 30/2001 |
| NOISE | fomc_minutes | event day | all | 1.5 | 123 | $248,205 | $-4,575 | 0.88 | -0.10 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | event day | all | 2.0 | 123 | $243,630 | $-9,150 | 0.80 | -0.18 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | event day | am | 0.0 | 97 | $257,763 | $+4,983 | 1.06 | +0.08 | Y | Y | Y | Y | no | 0.0610 | 122/2001 |
| NOISE | fomc_minutes | event day | am | 0.5 | 97 | $255,272 | $+2,492 | 1.02 | +0.04 | Y | Y | Y | Y | no | 0.0610 | 122/2001 |
| NOISE | fomc_minutes | event day | am | 1.5 | 97 | $250,288 | $-2,492 | 0.94 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | event day | am | 2.0 | 97 | $247,797 | $-4,983 | 0.90 | -0.07 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | event day | pm | 0.0 | 26 | $256,946 | $+4,167 | 1.03 | +0.05 | no | Y | Y | Y | no |  |  |
| NOISE | fomc_minutes | event day | pm | 0.5 | 26 | $254,863 | $+2,083 | 1.02 | +0.04 | no | Y | Y | Y | no |  |  |
| NOISE | fomc_minutes | event day | pm | 1.5 | 26 | $250,697 | $-2,083 | 0.91 | -0.06 | no | no | no | no | no |  |  |
| NOISE | fomc_minutes | event day | pm | 2.0 | 26 | $248,613 | $-4,167 | 0.86 | -0.12 | no | no | no | no | no |  |  |
| NOISE | fomc_minutes | day before | all | 0.0 | 140 | $253,501 | $+721 | 0.99 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | fomc_minutes | day before | all | 0.5 | 140 | $253,140 | $+361 | 0.98 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | fomc_minutes | day before | all | 1.5 | 140 | $252,419 | $-361 | 0.94 | -0.03 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day before | all | 2.0 | 140 | $252,059 | $-721 | 0.89 | -0.08 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day before | am | 0.0 | 109 | $252,670 | $-109 | 0.96 | -0.02 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day before | am | 0.5 | 109 | $252,725 | $-55 | 0.97 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day before | am | 1.5 | 109 | $252,835 | $+55 | 0.96 | -0.02 | Y | Y | no | no | no |  |  |
| NOISE | fomc_minutes | day before | am | 2.0 | 109 | $252,889 | $+109 | 0.92 | -0.06 | Y | Y | no | no | no |  |  |
| NOISE | fomc_minutes | day before | pm | 0.0 | 31 | $253,610 | $+830 | 1.00 | +0.03 | Y | Y | Y | Y | no | 0.2654 | 531/2001 |
| NOISE | fomc_minutes | day before | pm | 0.5 | 31 | $253,195 | $+415 | 0.99 | +0.01 | Y | Y | Y | Y | no | 0.2654 | 531/2001 |
| NOISE | fomc_minutes | day before | pm | 1.5 | 31 | $252,365 | $-415 | 0.96 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day before | pm | 2.0 | 31 | $251,949 | $-830 | 0.95 | -0.03 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day after | all | 0.0 | 130 | $224,719 | $-28,061 | 0.90 | -0.07 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day after | all | 0.5 | 130 | $238,749 | $-14,031 | 0.94 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day after | all | 1.5 | 130 | $266,810 | $+14,031 | 1.01 | +0.03 | Y | Y | Y | Y | Y | 0.0100 | 20/2001 |
| NOISE | fomc_minutes | day after | all | 2.0 | 130 | $280,841 | $+28,061 | 1.04 | +0.07 | Y | Y | Y | Y | Y | 0.0100 | 20/2001 |
| NOISE | fomc_minutes | day after | am | 0.0 | 108 | $223,824 | $-28,956 | 0.90 | -0.08 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day after | am | 0.5 | 108 | $238,302 | $-14,478 | 0.94 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | fomc_minutes | day after | am | 1.5 | 108 | $267,258 | $+14,478 | 1.01 | +0.04 | Y | Y | Y | Y | Y | 0.0070 | 14/2001 |
| NOISE | fomc_minutes | day after | am | 2.0 | 108 | $281,735 | $+28,956 | 1.05 | +0.07 | Y | Y | Y | Y | Y | 0.0070 | 14/2001 |
| NOISE | fomc_minutes | day after | pm | 0.0 | 22 | $253,674 | $+895 | 0.98 | +0.00 | no | Y | Y | Y | no |  |  |
| NOISE | fomc_minutes | day after | pm | 0.5 | 22 | $253,227 | $+447 | 0.98 | +0.00 | no | Y | Y | Y | no |  |  |
| NOISE | fomc_minutes | day after | pm | 1.5 | 22 | $252,333 | $-447 | 0.97 | -0.00 | no | no | no | no | no |  |  |
| NOISE | fomc_minutes | day after | pm | 2.0 | 22 | $251,885 | $-895 | 0.97 | -0.00 | no | no | no | no | no |  |  |
| NOISE | quad_witching | event day | all | 0.0 | 53 | $246,835 | $-5,945 | 0.85 | -0.13 | Y | no | no | no | no |  |  |
| NOISE | quad_witching | event day | all | 0.5 | 53 | $249,807 | $-2,973 | 0.92 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | quad_witching | event day | all | 1.5 | 53 | $255,752 | $+2,973 | 1.04 | +0.06 | Y | Y | Y | Y | no | 0.3583 | 717/2001 |
| NOISE | quad_witching | event day | all | 2.0 | 53 | $258,725 | $+5,945 | 1.05 | +0.08 | Y | Y | Y | Y | no | 0.3583 | 717/2001 |
| NOISE | quad_witching | event day | am | 0.0 | 49 | $246,792 | $-5,988 | 0.85 | -0.13 | Y | no | no | no | no |  |  |
| NOISE | quad_witching | event day | am | 0.5 | 49 | $249,786 | $-2,994 | 0.92 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | quad_witching | event day | am | 1.5 | 49 | $255,774 | $+2,994 | 1.04 | +0.06 | Y | Y | Y | Y | no | 0.3163 | 633/2001 |
| NOISE | quad_witching | event day | am | 2.0 | 49 | $258,768 | $+5,988 | 1.05 | +0.08 | Y | Y | Y | Y | no | 0.3163 | 633/2001 |
| NOISE | quad_witching | event day | pm | 0.0 | 4 | $252,823 | $+43 | 0.98 | +0.00 | no | Y | Y | no | no |  |  |
| NOISE | quad_witching | event day | pm | 0.5 | 4 | $252,801 | $+21 | 0.98 | +0.00 | no | Y | Y | no | no |  |  |
| NOISE | quad_witching | event day | pm | 1.5 | 4 | $252,759 | $-21 | 0.98 | -0.00 | no | no | no | no | no |  |  |
| NOISE | quad_witching | event day | pm | 2.0 | 4 | $252,737 | $-43 | 0.98 | -0.00 | no | no | no | no | no |  |  |
| NOISE | quad_witching | day before | all | 0.0 | 46 | $245,425 | $-7,355 | 1.00 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day before | all | 0.5 | 46 | $249,103 | $-3,677 | 1.00 | +0.03 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day before | all | 1.5 | 46 | $256,457 | $+3,677 | 0.87 | -0.11 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day before | all | 2.0 | 46 | $260,135 | $+7,355 | 0.78 | -0.19 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day before | am | 0.0 | 39 | $243,271 | $-9,509 | 0.99 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day before | am | 0.5 | 39 | $248,025 | $-4,755 | 1.00 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day before | am | 1.5 | 39 | $257,534 | $+4,755 | 0.91 | -0.06 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day before | am | 2.0 | 39 | $262,289 | $+9,509 | 0.86 | -0.12 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day before | pm | 0.0 | 7 | $254,934 | $+2,155 | 1.02 | +0.04 | no | Y | Y | Y | no |  |  |
| NOISE | quad_witching | day before | pm | 0.5 | 7 | $253,857 | $+1,077 | 1.01 | +0.04 | no | Y | Y | Y | no |  |  |
| NOISE | quad_witching | day before | pm | 1.5 | 7 | $251,703 | $-1,077 | 0.92 | -0.05 | no | no | no | no | no |  |  |
| NOISE | quad_witching | day before | pm | 2.0 | 7 | $250,625 | $-2,155 | 0.88 | -0.10 | no | no | no | no | no |  |  |
| NOISE | quad_witching | day after | all | 0.0 | 57 | $255,206 | $+2,426 | 0.97 | -0.00 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day after | all | 0.5 | 57 | $253,993 | $+1,213 | 0.97 | -0.00 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day after | all | 1.5 | 57 | $251,567 | $-1,213 | 0.98 | +0.00 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day after | all | 2.0 | 57 | $250,354 | $-2,426 | 0.98 | +0.00 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day after | am | 0.0 | 53 | $255,103 | $+2,323 | 0.97 | -0.00 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day after | am | 0.5 | 53 | $253,942 | $+1,162 | 0.97 | -0.00 | Y | Y | no | Y | no |  |  |
| NOISE | quad_witching | day after | am | 1.5 | 53 | $251,618 | $-1,162 | 0.98 | +0.00 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day after | am | 2.0 | 53 | $250,456 | $-2,323 | 0.98 | +0.00 | Y | no | Y | no | no |  |  |
| NOISE | quad_witching | day after | pm | 0.0 | 4 | $252,883 | $+103 | 0.98 | +0.00 | no | Y | Y | Y | no |  |  |
| NOISE | quad_witching | day after | pm | 0.5 | 4 | $252,831 | $+51 | 0.98 | +0.00 | no | Y | Y | Y | no |  |  |
| NOISE | quad_witching | day after | pm | 1.5 | 4 | $252,729 | $-51 | 0.98 | -0.00 | no | no | no | no | no |  |  |
| NOISE | quad_witching | day after | pm | 2.0 | 4 | $252,677 | $-103 | 0.97 | -0.00 | no | no | no | no | no |  |  |
| NOISE | month_start | event day | all | 0.0 | 431 | $240,662 | $-12,118 | 0.85 | -0.13 | Y | no | no | no | no |  |  |
| NOISE | month_start | event day | all | 0.5 | 431 | $246,721 | $-6,059 | 0.91 | -0.07 | Y | no | no | no | no |  |  |
| NOISE | month_start | event day | all | 1.5 | 431 | $258,839 | $+6,059 | 0.97 | -0.01 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | event day | all | 2.0 | 431 | $264,898 | $+12,118 | 0.93 | -0.05 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | event day | am | 0.0 | 341 | $237,297 | $-15,483 | 0.92 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | month_start | event day | am | 0.5 | 341 | $245,038 | $-7,742 | 0.95 | -0.03 | Y | no | no | no | no |  |  |
| NOISE | month_start | event day | am | 1.5 | 341 | $260,521 | $+7,742 | 0.93 | -0.05 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | event day | am | 2.0 | 341 | $268,263 | $+15,483 | 0.86 | -0.11 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | event day | pm | 0.0 | 90 | $256,145 | $+3,365 | 0.90 | -0.07 | Y | Y | no | no | no |  |  |
| NOISE | month_start | event day | pm | 0.5 | 90 | $254,463 | $+1,683 | 0.94 | -0.04 | Y | Y | no | no | no |  |  |
| NOISE | month_start | event day | pm | 1.5 | 90 | $251,097 | $-1,683 | 1.02 | +0.04 | Y | no | Y | no | no |  |  |
| NOISE | month_start | event day | pm | 2.0 | 90 | $249,414 | $-3,365 | 1.06 | +0.09 | Y | no | Y | no | no |  |  |
| NOISE | month_start | day before | all | 0.0 | 432 | $236,820 | $-15,960 | 1.11 | +0.14 | Y | no | Y | no | no |  |  |
| NOISE | month_start | day before | all | 0.5 | 432 | $244,800 | $-7,980 | 1.08 | +0.11 | Y | no | Y | no | no |  |  |
| NOISE | month_start | day before | all | 1.5 | 432 | $260,760 | $+7,980 | 0.89 | -0.08 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | day before | all | 2.0 | 432 | $268,740 | $+15,960 | 0.83 | -0.15 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | day before | am | 0.0 | 350 | $236,881 | $-15,899 | 1.29 | +0.31 | Y | no | Y | no | no |  |  |
| NOISE | month_start | day before | am | 0.5 | 350 | $244,830 | $-7,950 | 1.13 | +0.15 | Y | no | Y | no | no |  |  |
| NOISE | month_start | day before | am | 1.5 | 350 | $260,729 | $+7,950 | 0.86 | -0.11 | Y | Y | no | no | no |  |  |
| NOISE | month_start | day before | am | 2.0 | 350 | $268,679 | $+15,899 | 0.78 | -0.19 | Y | Y | no | no | no |  |  |
| NOISE | month_start | day before | pm | 0.0 | 82 | $252,719 | $-61 | 0.91 | -0.07 | Y | no | no | no | no |  |  |
| NOISE | month_start | day before | pm | 0.5 | 82 | $252,749 | $-31 | 0.94 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | month_start | day before | pm | 1.5 | 82 | $252,810 | $+31 | 1.01 | +0.04 | Y | Y | Y | no | no |  |  |
| NOISE | month_start | day before | pm | 2.0 | 82 | $252,841 | $+61 | 1.05 | +0.08 | Y | Y | Y | no | no |  |  |
| NOISE | month_start | day after | all | 0.0 | 345 | $220,675 | $-32,105 | 0.91 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | month_start | day after | all | 0.5 | 345 | $236,727 | $-16,053 | 0.95 | -0.03 | Y | no | no | no | no |  |  |
| NOISE | month_start | day after | all | 1.5 | 345 | $268,832 | $+16,053 | 0.99 | +0.02 | Y | Y | Y | Y | no | 0.2704 | 541/2001 |
| NOISE | month_start | day after | all | 2.0 | 345 | $284,885 | $+32,105 | 0.98 | +0.00 | Y | Y | Y | Y | no | 0.2704 | 541/2001 |
| NOISE | month_start | day after | am | 0.0 | 282 | $225,032 | $-27,748 | 0.99 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | month_start | day after | am | 0.5 | 282 | $238,906 | $-13,874 | 0.98 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | month_start | day after | am | 1.5 | 282 | $266,654 | $+13,874 | 0.96 | -0.02 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | day after | am | 2.0 | 282 | $280,528 | $+27,748 | 0.92 | -0.06 | Y | Y | no | Y | no |  |  |
| NOISE | month_start | day after | pm | 0.0 | 63 | $248,423 | $-4,357 | 0.91 | -0.07 | Y | no | no | no | no |  |  |
| NOISE | month_start | day after | pm | 0.5 | 63 | $250,601 | $-2,179 | 0.94 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | month_start | day after | pm | 1.5 | 63 | $254,958 | $+2,179 | 1.01 | +0.04 | Y | Y | Y | no | no |  |  |
| NOISE | month_start | day after | pm | 2.0 | 63 | $257,137 | $+4,357 | 1.05 | +0.08 | Y | Y | Y | no | no |  |  |
| NOISE | month_end | event day | all | 0.0 | 390 | $232,762 | $-20,018 | 1.12 | +0.15 | Y | no | Y | no | no |  |  |
| NOISE | month_end | event day | all | 0.5 | 390 | $242,771 | $-10,009 | 1.18 | +0.21 | Y | no | Y | no | no |  |  |
| NOISE | month_end | event day | all | 1.5 | 390 | $262,789 | $+10,009 | 0.84 | -0.14 | Y | Y | no | no | no |  |  |
| NOISE | month_end | event day | all | 2.0 | 390 | $272,797 | $+20,018 | 0.74 | -0.23 | Y | Y | no | no | no |  |  |
| NOISE | month_end | event day | am | 0.0 | 320 | $229,076 | $-23,704 | 1.05 | +0.07 | Y | no | Y | no | no |  |  |
| NOISE | month_end | event day | am | 0.5 | 320 | $240,928 | $-11,852 | 1.11 | +0.13 | Y | no | Y | no | no |  |  |
| NOISE | month_end | event day | am | 1.5 | 320 | $264,632 | $+11,852 | 0.88 | -0.10 | Y | Y | no | no | no |  |  |
| NOISE | month_end | event day | am | 2.0 | 320 | $276,484 | $+23,704 | 0.80 | -0.17 | Y | Y | no | no | no |  |  |
| NOISE | month_end | event day | pm | 0.0 | 70 | $256,466 | $+3,686 | 1.08 | +0.11 | Y | Y | Y | Y | no | 0.1029 | 206/2001 |
| NOISE | month_end | event day | pm | 0.5 | 70 | $254,623 | $+1,843 | 1.03 | +0.05 | Y | Y | Y | Y | no | 0.1029 | 206/2001 |
| NOISE | month_end | event day | pm | 1.5 | 70 | $250,937 | $-1,843 | 0.93 | -0.05 | Y | no | no | no | no |  |  |
| NOISE | month_end | event day | pm | 2.0 | 70 | $249,094 | $-3,686 | 0.89 | -0.09 | Y | no | no | no | no |  |  |
| NOISE | month_end | day before | all | 0.0 | 397 | $218,624 | $-34,156 | 1.03 | +0.06 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day before | all | 0.5 | 397 | $235,702 | $-17,078 | 1.03 | +0.06 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day before | all | 1.5 | 397 | $269,858 | $+17,078 | 0.93 | -0.04 | Y | Y | no | Y | no |  |  |
| NOISE | month_end | day before | all | 2.0 | 397 | $286,936 | $+34,156 | 0.89 | -0.08 | Y | Y | no | Y | no |  |  |
| NOISE | month_end | day before | am | 0.0 | 325 | $224,216 | $-28,564 | 1.04 | +0.07 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day before | am | 0.5 | 325 | $238,498 | $-14,282 | 1.01 | +0.03 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day before | am | 1.5 | 325 | $267,062 | $+14,282 | 0.95 | -0.03 | Y | Y | no | Y | no |  |  |
| NOISE | month_end | day before | am | 2.0 | 325 | $281,344 | $+28,564 | 0.92 | -0.06 | Y | Y | no | Y | no |  |  |
| NOISE | month_end | day before | pm | 0.0 | 72 | $247,187 | $-5,592 | 1.01 | +0.04 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day before | pm | 0.5 | 72 | $249,984 | $-2,796 | 0.99 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day before | pm | 1.5 | 72 | $255,576 | $+2,796 | 0.96 | -0.02 | Y | Y | no | no | no |  |  |
| NOISE | month_end | day before | pm | 2.0 | 72 | $258,372 | $+5,592 | 0.94 | -0.04 | Y | Y | no | no | no |  |  |
| NOISE | month_end | day after | all | 0.0 | 435 | $236,782 | $-15,998 | 1.11 | +0.14 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day after | all | 0.5 | 435 | $244,781 | $-7,999 | 1.08 | +0.11 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day after | all | 1.5 | 435 | $260,779 | $+7,999 | 0.89 | -0.08 | Y | Y | no | Y | no |  |  |
| NOISE | month_end | day after | all | 2.0 | 435 | $268,778 | $+15,998 | 0.83 | -0.15 | Y | Y | no | Y | no |  |  |
| NOISE | month_end | day after | am | 0.0 | 353 | $236,843 | $-15,937 | 1.29 | +0.31 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day after | am | 0.5 | 353 | $244,811 | $-7,969 | 1.13 | +0.15 | Y | no | Y | no | no |  |  |
| NOISE | month_end | day after | am | 1.5 | 353 | $260,748 | $+7,969 | 0.86 | -0.11 | Y | Y | no | no | no |  |  |
| NOISE | month_end | day after | am | 2.0 | 353 | $268,717 | $+15,937 | 0.78 | -0.19 | Y | Y | no | no | no |  |  |
| NOISE | month_end | day after | pm | 0.0 | 82 | $252,719 | $-61 | 0.91 | -0.07 | Y | no | no | no | no |  |  |
| NOISE | month_end | day after | pm | 0.5 | 82 | $252,749 | $-31 | 0.94 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | month_end | day after | pm | 1.5 | 82 | $252,810 | $+31 | 1.01 | +0.04 | Y | Y | Y | no | no |  |  |
| NOISE | month_end | day after | pm | 2.0 | 82 | $252,841 | $+61 | 1.05 | +0.08 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_start | event day | all | 0.0 | 177 | $241,988 | $-10,792 | 1.11 | +0.13 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | event day | all | 0.5 | 177 | $247,384 | $-5,396 | 1.06 | +0.08 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | event day | all | 1.5 | 177 | $258,176 | $+5,396 | 0.89 | -0.08 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | event day | all | 2.0 | 177 | $263,572 | $+10,792 | 0.82 | -0.15 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | event day | am | 0.0 | 142 | $241,495 | $-11,285 | 1.09 | +0.11 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | event day | am | 0.5 | 142 | $247,137 | $-5,642 | 1.05 | +0.07 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | event day | am | 1.5 | 142 | $258,422 | $+5,642 | 0.90 | -0.08 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | event day | am | 2.0 | 142 | $264,065 | $+11,285 | 0.83 | -0.14 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | event day | pm | 0.0 | 35 | $253,273 | $+493 | 0.99 | +0.02 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_start | event day | pm | 0.5 | 35 | $253,026 | $+247 | 0.98 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_start | event day | pm | 1.5 | 35 | $252,533 | $-247 | 0.97 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | quarter_start | event day | pm | 2.0 | 35 | $252,287 | $-493 | 0.96 | -0.02 | Y | no | no | no | no |  |  |
| NOISE | quarter_start | day before | all | 0.0 | 168 | $249,710 | $-3,070 | 1.37 | +0.40 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | day before | all | 0.5 | 168 | $251,245 | $-1,535 | 1.15 | +0.18 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | day before | all | 1.5 | 168 | $254,315 | $+1,535 | 0.85 | -0.13 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | day before | all | 2.0 | 168 | $255,850 | $+3,070 | 0.75 | -0.23 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | day before | am | 0.0 | 138 | $249,625 | $-3,155 | 1.35 | +0.37 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | day before | am | 0.5 | 138 | $251,203 | $-1,577 | 1.14 | +0.17 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | day before | am | 1.5 | 138 | $254,357 | $+1,577 | 0.85 | -0.12 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | day before | am | 2.0 | 138 | $255,934 | $+3,155 | 0.76 | -0.22 | Y | Y | no | no | no |  |  |
| NOISE | quarter_start | day before | pm | 0.0 | 30 | $252,865 | $+85 | 0.99 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_start | day before | pm | 0.5 | 30 | $252,822 | $+42 | 0.98 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_start | day before | pm | 1.5 | 30 | $252,737 | $-42 | 0.97 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | quarter_start | day before | pm | 2.0 | 30 | $252,695 | $-85 | 0.96 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | quarter_start | day after | all | 0.0 | 116 | $233,199 | $-19,581 | 0.91 | -0.06 | Y | no | no | no | no |  |  |
| NOISE | quarter_start | day after | all | 0.5 | 116 | $242,990 | $-9,790 | 0.96 | -0.02 | Y | no | no | no | no |  |  |
| NOISE | quarter_start | day after | all | 1.5 | 116 | $262,570 | $+9,790 | 0.97 | -0.00 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_start | day after | all | 2.0 | 116 | $272,360 | $+19,581 | 0.97 | -0.01 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_start | day after | am | 0.0 | 93 | $234,599 | $-18,181 | 0.98 | +0.00 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | day after | am | 0.5 | 93 | $243,690 | $-9,090 | 0.99 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | quarter_start | day after | am | 1.5 | 93 | $261,870 | $+9,090 | 0.94 | -0.04 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_start | day after | am | 2.0 | 93 | $270,961 | $+18,181 | 0.91 | -0.07 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_start | day after | pm | 0.0 | 23 | $251,380 | $-1,400 | 0.91 | -0.06 | no | no | no | no | no |  |  |
| NOISE | quarter_start | day after | pm | 0.5 | 23 | $252,080 | $-700 | 0.94 | -0.03 | no | no | no | no | no |  |  |
| NOISE | quarter_start | day after | pm | 1.5 | 23 | $253,480 | $+700 | 1.01 | +0.03 | no | Y | Y | no | no |  |  |
| NOISE | quarter_start | day after | pm | 2.0 | 23 | $254,180 | $+1,400 | 1.05 | +0.07 | no | Y | Y | no | no |  |  |
| NOISE | quarter_end | event day | all | 0.0 | 147 | $249,615 | $-3,165 | 1.00 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | event day | all | 0.5 | 147 | $251,197 | $-1,582 | 0.99 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | event day | all | 1.5 | 147 | $254,362 | $+1,582 | 0.96 | -0.01 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_end | event day | all | 2.0 | 147 | $255,945 | $+3,165 | 0.95 | -0.02 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_end | event day | am | 0.0 | 119 | $248,642 | $-4,138 | 1.00 | +0.02 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | event day | am | 0.5 | 119 | $250,711 | $-2,069 | 0.99 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | event day | am | 1.5 | 119 | $254,849 | $+2,069 | 0.97 | -0.01 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_end | event day | am | 2.0 | 119 | $256,918 | $+4,138 | 0.96 | -0.02 | Y | Y | no | Y | no |  |  |
| NOISE | quarter_end | event day | pm | 0.0 | 28 | $253,753 | $+973 | 0.98 | +0.00 | no | Y | Y | Y | no |  |  |
| NOISE | quarter_end | event day | pm | 0.5 | 28 | $253,267 | $+487 | 0.98 | +0.00 | no | Y | Y | Y | no |  |  |
| NOISE | quarter_end | event day | pm | 1.5 | 28 | $252,293 | $-487 | 0.97 | -0.00 | no | no | no | no | no |  |  |
| NOISE | quarter_end | event day | pm | 2.0 | 28 | $251,806 | $-973 | 0.97 | -0.00 | no | no | no | no | no |  |  |
| NOISE | quarter_end | day before | all | 0.0 | 178 | $250,031 | $-2,749 | 0.98 | +0.00 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day before | all | 0.5 | 178 | $251,406 | $-1,374 | 0.99 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day before | all | 1.5 | 178 | $254,154 | $+1,374 | 0.96 | -0.01 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day before | all | 2.0 | 178 | $255,529 | $+2,749 | 0.95 | -0.02 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day before | am | 0.0 | 144 | $251,609 | $-1,171 | 0.98 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day before | am | 0.5 | 144 | $252,194 | $-586 | 0.99 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day before | am | 1.5 | 144 | $253,365 | $+586 | 0.96 | -0.01 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day before | am | 2.0 | 144 | $253,951 | $+1,171 | 0.95 | -0.03 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day before | pm | 0.0 | 34 | $251,202 | $-1,578 | 0.97 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | quarter_end | day before | pm | 0.5 | 34 | $251,991 | $-789 | 0.97 | -0.00 | Y | no | no | no | no |  |  |
| NOISE | quarter_end | day before | pm | 1.5 | 34 | $253,569 | $+789 | 0.98 | +0.00 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_end | day before | pm | 2.0 | 34 | $254,357 | $+1,578 | 0.98 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_end | day after | all | 0.0 | 171 | $249,672 | $-3,108 | 1.37 | +0.40 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day after | all | 0.5 | 171 | $251,226 | $-1,554 | 1.15 | +0.18 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day after | all | 1.5 | 171 | $254,334 | $+1,554 | 0.85 | -0.13 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day after | all | 2.0 | 171 | $255,888 | $+3,108 | 0.75 | -0.23 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day after | am | 0.0 | 141 | $249,587 | $-3,193 | 1.35 | +0.37 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day after | am | 0.5 | 141 | $251,184 | $-1,596 | 1.14 | +0.17 | Y | no | Y | no | no |  |  |
| NOISE | quarter_end | day after | am | 1.5 | 141 | $254,376 | $+1,596 | 0.85 | -0.12 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day after | am | 2.0 | 141 | $255,972 | $+3,193 | 0.76 | -0.22 | Y | Y | no | no | no |  |  |
| NOISE | quarter_end | day after | pm | 0.0 | 30 | $252,865 | $+85 | 0.99 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_end | day after | pm | 0.5 | 30 | $252,822 | $+42 | 0.98 | +0.01 | Y | Y | Y | no | no |  |  |
| NOISE | quarter_end | day after | pm | 1.5 | 30 | $252,737 | $-42 | 0.97 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | quarter_end | day after | pm | 2.0 | 30 | $252,695 | $-85 | 0.96 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | fed_blackout | event day | all | 0.0 | 857 | $186,867 | $-65,913 | 1.00 | +0.03 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | event day | all | 0.5 | 857 | $219,823 | $-32,957 | 1.19 | +0.22 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | event day | all | 1.5 | 857 | $285,736 | $+32,957 | 0.82 | -0.16 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | event day | all | 2.0 | 857 | $318,693 | $+65,913 | 0.73 | -0.25 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | event day | am | 0.0 | 714 | $190,177 | $-62,602 | 0.93 | -0.04 | Y | no | no | no | no |  |  |
| NOISE | fed_blackout | event day | am | 0.5 | 714 | $221,479 | $-31,301 | 1.13 | +0.16 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | event day | am | 1.5 | 714 | $284,081 | $+31,301 | 0.88 | -0.10 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | event day | am | 2.0 | 714 | $315,382 | $+62,602 | 0.81 | -0.16 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | event day | pm | 0.0 | 143 | $249,469 | $-3,311 | 1.10 | +0.12 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | event day | pm | 0.5 | 143 | $251,125 | $-1,655 | 1.05 | +0.08 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | event day | pm | 1.5 | 143 | $254,435 | $+1,655 | 0.90 | -0.08 | Y | Y | no | no | no |  |  |
| NOISE | fed_blackout | event day | pm | 2.0 | 143 | $256,090 | $+3,311 | 0.83 | -0.14 | Y | Y | no | no | no |  |  |
| NOISE | fed_blackout | day before | all | 0.0 | 834 | $173,030 | $-79,750 | 0.99 | +0.01 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day before | all | 0.5 | 834 | $212,905 | $-39,875 | 1.07 | +0.09 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day before | all | 1.5 | 834 | $292,655 | $+39,875 | 0.88 | -0.09 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day before | all | 2.0 | 834 | $332,530 | $+79,750 | 0.81 | -0.17 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day before | am | 0.0 | 707 | $176,826 | $-75,954 | 0.92 | -0.05 | Y | no | no | no | no |  |  |
| NOISE | fed_blackout | day before | am | 0.5 | 707 | $214,803 | $-37,977 | 0.96 | -0.01 | Y | no | no | no | no |  |  |
| NOISE | fed_blackout | day before | am | 1.5 | 707 | $290,757 | $+37,977 | 0.91 | -0.07 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day before | am | 2.0 | 707 | $328,734 | $+75,954 | 0.84 | -0.14 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day before | pm | 0.0 | 127 | $248,984 | $-3,796 | 1.08 | +0.10 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day before | pm | 0.5 | 127 | $250,882 | $-1,898 | 1.04 | +0.07 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day before | pm | 1.5 | 127 | $254,678 | $+1,898 | 0.90 | -0.07 | Y | Y | no | no | no |  |  |
| NOISE | fed_blackout | day before | pm | 2.0 | 127 | $256,576 | $+3,796 | 0.84 | -0.13 | Y | Y | no | no | no |  |  |
| NOISE | fed_blackout | day after | all | 0.0 | 863 | $211,078 | $-41,701 | 1.04 | +0.07 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day after | all | 0.5 | 863 | $231,929 | $-20,851 | 1.05 | +0.08 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day after | all | 1.5 | 863 | $273,631 | $+20,851 | 0.91 | -0.07 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day after | all | 2.0 | 863 | $294,481 | $+41,701 | 0.83 | -0.14 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day after | am | 0.0 | 698 | $222,317 | $-30,463 | 1.07 | +0.10 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day after | am | 0.5 | 698 | $237,548 | $-15,232 | 1.19 | +0.21 | Y | no | Y | no | no |  |  |
| NOISE | fed_blackout | day after | am | 1.5 | 698 | $268,011 | $+15,232 | 0.84 | -0.14 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day after | am | 2.0 | 698 | $283,243 | $+30,463 | 0.74 | -0.23 | Y | Y | no | Y | no |  |  |
| NOISE | fed_blackout | day after | pm | 0.0 | 165 | $241,542 | $-11,238 | 0.80 | -0.18 | Y | no | no | no | no |  |  |
| NOISE | fed_blackout | day after | pm | 0.5 | 165 | $247,161 | $-5,619 | 0.88 | -0.10 | Y | no | no | no | no |  |  |
| NOISE | fed_blackout | day after | pm | 1.5 | 165 | $258,399 | $+5,619 | 1.07 | +0.09 | Y | Y | Y | no | no |  |  |
| NOISE | fed_blackout | day after | pm | 2.0 | 165 | $264,018 | $+11,238 | 1.13 | +0.16 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | event day | all | 0.0 | 59 | $218,566 | $+4,306 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | fomc_decision | event day | all | 0.5 | 59 | $216,412 | $+2,153 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | fomc_decision | event day | all | 1.5 | 59 | $212,106 | $-2,153 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fomc_decision | event day | all | 2.0 | 59 | $209,953 | $-4,306 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fomc_decision | event day | am | 0.0 | 35 | $221,647 | $+7,388 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | event day | am | 0.5 | 35 | $217,953 | $+3,694 | 0.48 | +0.01 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | event day | am | 1.5 | 35 | $210,565 | $-3,694 | 0.46 | -0.01 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | event day | am | 2.0 | 35 | $206,871 | $-7,388 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | event day | pm | 0.0 | 24 | $211,177 | $-3,082 | 0.45 | -0.02 | no | no | no | no | no |  |  |
| ORB | fomc_decision | event day | pm | 0.5 | 24 | $212,718 | $-1,541 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | fomc_decision | event day | pm | 1.5 | 24 | $215,800 | $+1,541 | 0.48 | +0.01 | no | Y | Y | Y | no |  |  |
| ORB | fomc_decision | event day | pm | 2.0 | 24 | $217,341 | $+3,082 | 0.49 | +0.02 | no | Y | Y | Y | no |  |  |
| ORB | fomc_decision | day before | all | 0.0 | 68 | $215,709 | $+1,450 | 0.52 | +0.05 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | day before | all | 0.5 | 68 | $214,984 | $+725 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | day before | all | 1.5 | 68 | $213,534 | $-725 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | day before | all | 2.0 | 68 | $212,809 | $-1,450 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | day before | am | 0.0 | 62 | $210,403 | $-3,857 | 0.50 | +0.04 | Y | no | Y | no | no |  |  |
| ORB | fomc_decision | day before | am | 0.5 | 62 | $212,331 | $-1,928 | 0.49 | +0.02 | Y | no | Y | no | no |  |  |
| ORB | fomc_decision | day before | am | 1.5 | 62 | $216,187 | $+1,928 | 0.45 | -0.02 | Y | Y | no | no | no |  |  |
| ORB | fomc_decision | day before | am | 2.0 | 62 | $218,116 | $+3,857 | 0.44 | -0.03 | Y | Y | no | no | no |  |  |
| ORB | fomc_decision | day before | pm | 0.0 | 6 | $219,566 | $+5,306 | 0.48 | +0.01 | no | Y | Y | Y | no |  |  |
| ORB | fomc_decision | day before | pm | 0.5 | 6 | $216,912 | $+2,653 | 0.47 | +0.01 | no | Y | Y | Y | no |  |  |
| ORB | fomc_decision | day before | pm | 1.5 | 6 | $211,606 | $-2,653 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | fomc_decision | day before | pm | 2.0 | 6 | $208,953 | $-5,306 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | fomc_decision | day after | all | 0.0 | 73 | $184,820 | $-29,439 | 0.40 | -0.07 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | day after | all | 0.5 | 73 | $199,539 | $-14,720 | 0.43 | -0.03 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | day after | all | 1.5 | 73 | $228,979 | $+14,720 | 0.50 | +0.03 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | day after | all | 2.0 | 73 | $243,698 | $+29,439 | 0.54 | +0.07 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | day after | am | 0.0 | 70 | $184,998 | $-29,261 | 0.40 | -0.07 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | day after | am | 0.5 | 70 | $199,628 | $-14,631 | 0.43 | -0.03 | Y | no | no | no | no |  |  |
| ORB | fomc_decision | day after | am | 1.5 | 70 | $228,890 | $+14,631 | 0.50 | +0.03 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | day after | am | 2.0 | 70 | $243,520 | $+29,261 | 0.54 | +0.07 | Y | Y | Y | no | no |  |  |
| ORB | fomc_decision | day after | pm | 0.0 | 3 | $214,081 | $-178 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fomc_decision | day after | pm | 0.5 | 3 | $214,170 | $-89 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fomc_decision | day after | pm | 1.5 | 3 | $214,348 | $+89 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | fomc_decision | day after | pm | 2.0 | 3 | $214,437 | $+178 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | cpi | event day | all | 0.0 | 91 | $204,432 | $-9,827 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | cpi | event day | all | 0.5 | 91 | $209,345 | $-4,914 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | cpi | event day | all | 1.5 | 91 | $219,173 | $+4,914 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | cpi | event day | all | 2.0 | 91 | $224,087 | $+9,827 | 0.51 | +0.04 | Y | Y | Y | no | no |  |  |
| ORB | cpi | event day | am | 0.0 | 82 | $205,721 | $-8,538 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | cpi | event day | am | 0.5 | 82 | $209,990 | $-4,269 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | cpi | event day | am | 1.5 | 82 | $218,528 | $+4,269 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | cpi | event day | am | 2.0 | 82 | $222,797 | $+8,538 | 0.50 | +0.03 | Y | Y | Y | no | no |  |  |
| ORB | cpi | event day | pm | 0.0 | 9 | $212,970 | $-1,289 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | cpi | event day | pm | 0.5 | 9 | $213,615 | $-645 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | cpi | event day | pm | 1.5 | 9 | $214,904 | $+645 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | cpi | event day | pm | 2.0 | 9 | $215,548 | $+1,289 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | cpi | day before | all | 0.0 | 97 | $194,526 | $-19,733 | 0.42 | -0.05 | Y | no | no | no | no |  |  |
| ORB | cpi | day before | all | 0.5 | 97 | $204,392 | $-9,867 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | cpi | day before | all | 1.5 | 97 | $224,126 | $+9,867 | 0.50 | +0.03 | Y | Y | Y | no | no |  |  |
| ORB | cpi | day before | all | 2.0 | 97 | $233,993 | $+19,733 | 0.52 | +0.05 | Y | Y | Y | no | no |  |  |
| ORB | cpi | day before | am | 0.0 | 88 | $199,335 | $-14,924 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | cpi | day before | am | 0.5 | 88 | $206,797 | $-7,462 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | cpi | day before | am | 1.5 | 88 | $221,721 | $+7,462 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | cpi | day before | am | 2.0 | 88 | $229,184 | $+14,924 | 0.51 | +0.04 | Y | Y | Y | no | no |  |  |
| ORB | cpi | day before | pm | 0.0 | 9 | $209,450 | $-4,809 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | cpi | day before | pm | 0.5 | 9 | $211,855 | $-2,405 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | cpi | day before | pm | 1.5 | 9 | $216,664 | $+2,405 | 0.47 | +0.01 | no | Y | Y | no | no |  |  |
| ORB | cpi | day before | pm | 2.0 | 9 | $219,068 | $+4,809 | 0.48 | +0.01 | no | Y | Y | no | no |  |  |
| ORB | cpi | day after | all | 0.0 | 93 | $191,678 | $-22,581 | 0.42 | -0.05 | Y | no | no | no | no |  |  |
| ORB | cpi | day after | all | 0.5 | 93 | $202,969 | $-11,291 | 0.44 | -0.02 | Y | no | no | no | no |  |  |
| ORB | cpi | day after | all | 1.5 | 93 | $225,550 | $+11,291 | 0.49 | +0.02 | Y | Y | Y | Y | no | 0.1694 | 339/2001 |
| ORB | cpi | day after | all | 2.0 | 93 | $236,840 | $+22,581 | 0.52 | +0.05 | Y | Y | Y | Y | no | 0.1694 | 339/2001 |
| ORB | cpi | day after | am | 0.0 | 85 | $195,198 | $-19,061 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | cpi | day after | am | 0.5 | 85 | $204,728 | $-9,531 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | cpi | day after | am | 1.5 | 85 | $223,790 | $+9,531 | 0.49 | +0.02 | Y | Y | Y | Y | no | 0.2224 | 445/2001 |
| ORB | cpi | day after | am | 2.0 | 85 | $233,321 | $+19,061 | 0.51 | +0.04 | Y | Y | Y | Y | no | 0.2224 | 445/2001 |
| ORB | cpi | day after | pm | 0.0 | 8 | $210,739 | $-3,520 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | cpi | day after | pm | 0.5 | 8 | $212,499 | $-1,760 | 0.46 | -0.00 | no | no | no | no | no |  |  |
| ORB | cpi | day after | pm | 1.5 | 8 | $216,019 | $+1,760 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | cpi | day after | pm | 2.0 | 8 | $217,779 | $+3,520 | 0.48 | +0.01 | no | Y | Y | Y | no |  |  |
| ORB | nfp | event day | all | 0.0 | 87 | $202,974 | $-11,285 | 0.60 | +0.13 | Y | no | Y | no | no |  |  |
| ORB | nfp | event day | all | 0.5 | 87 | $208,617 | $-5,643 | 0.52 | +0.05 | Y | no | Y | no | no |  |  |
| ORB | nfp | event day | all | 1.5 | 87 | $219,902 | $+5,643 | 0.42 | -0.05 | Y | Y | no | Y | no |  |  |
| ORB | nfp | event day | all | 2.0 | 87 | $225,544 | $+11,285 | 0.36 | -0.10 | Y | Y | no | Y | no |  |  |
| ORB | nfp | event day | am | 0.0 | 86 | $203,018 | $-11,241 | 0.60 | +0.13 | Y | no | Y | no | no |  |  |
| ORB | nfp | event day | am | 0.5 | 86 | $208,639 | $-5,620 | 0.52 | +0.05 | Y | no | Y | no | no |  |  |
| ORB | nfp | event day | am | 1.5 | 86 | $219,879 | $+5,620 | 0.42 | -0.05 | Y | Y | no | Y | no |  |  |
| ORB | nfp | event day | am | 2.0 | 86 | $225,500 | $+11,241 | 0.36 | -0.10 | Y | Y | no | Y | no |  |  |
| ORB | nfp | event day | pm | 0.0 | 1 | $214,215 | $-44 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | nfp | event day | pm | 0.5 | 1 | $214,237 | $-22 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | nfp | event day | pm | 1.5 | 1 | $214,281 | $+22 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | nfp | event day | pm | 2.0 | 1 | $214,303 | $+44 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | nfp | day before | all | 0.0 | 100 | $194,243 | $-20,016 | 0.44 | -0.02 | Y | no | no | no | no |  |  |
| ORB | nfp | day before | all | 0.5 | 100 | $204,251 | $-10,008 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | nfp | day before | all | 1.5 | 100 | $224,267 | $+10,008 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | nfp | day before | all | 2.0 | 100 | $234,276 | $+20,016 | 0.46 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | nfp | day before | am | 0.0 | 94 | $200,854 | $-13,405 | 0.46 | -0.01 | Y | no | no | no | no |  |  |
| ORB | nfp | day before | am | 0.5 | 94 | $207,556 | $-6,703 | 0.48 | +0.01 | Y | no | Y | no | no |  |  |
| ORB | nfp | day before | am | 1.5 | 94 | $220,962 | $+6,703 | 0.46 | -0.01 | Y | Y | no | no | no |  |  |
| ORB | nfp | day before | am | 2.0 | 94 | $227,665 | $+13,405 | 0.45 | -0.02 | Y | Y | no | no | no |  |  |
| ORB | nfp | day before | pm | 0.0 | 6 | $207,648 | $-6,611 | 0.45 | -0.01 | no | no | no | no | no |  |  |
| ORB | nfp | day before | pm | 0.5 | 6 | $210,954 | $-3,306 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | nfp | day before | pm | 1.5 | 6 | $217,565 | $+3,306 | 0.48 | +0.01 | no | Y | Y | Y | no |  |  |
| ORB | nfp | day before | pm | 2.0 | 6 | $220,870 | $+6,611 | 0.48 | +0.01 | no | Y | Y | Y | no |  |  |
| ORB | nfp | day after | all | 0.0 | 70 | $221,573 | $+7,314 | 0.45 | -0.02 | Y | Y | no | no | no |  |  |
| ORB | nfp | day after | all | 0.5 | 70 | $217,916 | $+3,657 | 0.46 | -0.01 | Y | Y | no | no | no |  |  |
| ORB | nfp | day after | all | 1.5 | 70 | $210,602 | $-3,657 | 0.48 | +0.01 | Y | no | Y | no | no |  |  |
| ORB | nfp | day after | all | 2.0 | 70 | $206,945 | $-7,314 | 0.49 | +0.03 | Y | no | Y | no | no |  |  |
| ORB | nfp | day after | am | 0.0 | 66 | $225,445 | $+11,186 | 0.52 | +0.05 | Y | Y | Y | no | no |  |  |
| ORB | nfp | day after | am | 0.5 | 66 | $219,852 | $+5,593 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | nfp | day after | am | 1.5 | 66 | $208,666 | $-5,593 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | nfp | day after | am | 2.0 | 66 | $203,073 | $-11,186 | 0.42 | -0.04 | Y | no | no | no | no |  |  |
| ORB | nfp | day after | pm | 0.0 | 4 | $210,387 | $-3,872 | 0.41 | -0.06 | no | no | no | no | no |  |  |
| ORB | nfp | day after | pm | 0.5 | 4 | $212,323 | $-1,936 | 0.44 | -0.03 | no | no | no | no | no |  |  |
| ORB | nfp | day after | pm | 1.5 | 4 | $216,195 | $+1,936 | 0.50 | +0.04 | no | Y | Y | no | no |  |  |
| ORB | nfp | day after | pm | 2.0 | 4 | $218,131 | $+3,872 | 0.55 | +0.08 | no | Y | Y | no | no |  |  |
| ORB | fomc_minutes | event day | all | 0.0 | 58 | $213,057 | $-1,202 | 0.46 | -0.01 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | event day | all | 0.5 | 58 | $213,658 | $-601 | 0.47 | -0.00 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | event day | all | 1.5 | 58 | $214,860 | $+601 | 0.47 | +0.00 | Y | Y | Y | no | no |  |  |
| ORB | fomc_minutes | event day | all | 2.0 | 58 | $215,461 | $+1,202 | 0.47 | +0.01 | Y | Y | Y | no | no |  |  |
| ORB | fomc_minutes | event day | am | 0.0 | 47 | $212,360 | $-1,899 | 0.46 | -0.00 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | event day | am | 0.5 | 47 | $213,310 | $-949 | 0.47 | -0.00 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | event day | am | 1.5 | 47 | $215,209 | $+949 | 0.47 | +0.00 | Y | Y | Y | no | no |  |  |
| ORB | fomc_minutes | event day | am | 2.0 | 47 | $216,158 | $+1,899 | 0.47 | +0.00 | Y | Y | Y | no | no |  |  |
| ORB | fomc_minutes | event day | pm | 0.0 | 11 | $214,956 | $+697 | 0.47 | -0.00 | no | Y | no | no | no |  |  |
| ORB | fomc_minutes | event day | pm | 0.5 | 11 | $214,608 | $+349 | 0.47 | -0.00 | no | Y | no | no | no |  |  |
| ORB | fomc_minutes | event day | pm | 1.5 | 11 | $213,910 | $-349 | 0.47 | +0.00 | no | no | Y | no | no |  |  |
| ORB | fomc_minutes | event day | pm | 2.0 | 11 | $213,562 | $-697 | 0.47 | +0.00 | no | no | Y | no | no |  |  |
| ORB | fomc_minutes | day before | all | 0.0 | 59 | $218,533 | $+4,274 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | fomc_minutes | day before | all | 0.5 | 59 | $216,396 | $+2,137 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | fomc_minutes | day before | all | 1.5 | 59 | $212,122 | $-2,137 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fomc_minutes | day before | all | 2.0 | 59 | $209,985 | $-4,274 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fomc_minutes | day before | am | 0.0 | 56 | $218,806 | $+4,547 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | fomc_minutes | day before | am | 0.5 | 56 | $216,533 | $+2,273 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | fomc_minutes | day before | am | 1.5 | 56 | $211,986 | $-2,273 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fomc_minutes | day before | am | 2.0 | 56 | $209,712 | $-4,547 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fomc_minutes | day before | pm | 0.0 | 3 | $213,986 | $-273 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fomc_minutes | day before | pm | 0.5 | 3 | $214,123 | $-137 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fomc_minutes | day before | pm | 1.5 | 3 | $214,396 | $+137 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | fomc_minutes | day before | pm | 2.0 | 3 | $214,532 | $+273 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | fomc_minutes | day after | all | 0.0 | 48 | $206,921 | $-7,338 | 0.46 | -0.00 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | day after | all | 0.5 | 48 | $210,590 | $-3,669 | 0.47 | -0.00 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | day after | all | 1.5 | 48 | $217,928 | $+3,669 | 0.47 | +0.00 | Y | Y | Y | Y | no | 0.4523 | 905/2001 |
| ORB | fomc_minutes | day after | all | 2.0 | 48 | $221,597 | $+7,338 | 0.47 | +0.00 | Y | Y | Y | Y | no | 0.4523 | 905/2001 |
| ORB | fomc_minutes | day after | am | 0.0 | 46 | $206,924 | $-7,335 | 0.46 | -0.00 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | day after | am | 0.5 | 46 | $210,592 | $-3,667 | 0.47 | -0.00 | Y | no | no | no | no |  |  |
| ORB | fomc_minutes | day after | am | 1.5 | 46 | $217,926 | $+3,667 | 0.47 | +0.00 | Y | Y | Y | Y | no | 0.4518 | 904/2001 |
| ORB | fomc_minutes | day after | am | 2.0 | 46 | $221,594 | $+7,335 | 0.47 | +0.00 | Y | Y | Y | Y | no | 0.4518 | 904/2001 |
| ORB | fomc_minutes | day after | pm | 0.0 | 2 | $214,255 | $-4 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fomc_minutes | day after | pm | 0.5 | 2 | $214,257 | $-2 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fomc_minutes | day after | pm | 1.5 | 2 | $214,261 | $+2 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | fomc_minutes | day after | pm | 2.0 | 2 | $214,263 | $+4 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | quad_witching | event day | all | 0.0 | 36 | $201,958 | $-12,301 | 0.41 | -0.06 | Y | no | no | no | no |  |  |
| ORB | quad_witching | event day | all | 0.5 | 36 | $208,108 | $-6,151 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quad_witching | event day | all | 1.5 | 36 | $220,410 | $+6,151 | 0.50 | +0.03 | Y | Y | Y | Y | no | 0.1294 | 259/2001 |
| ORB | quad_witching | event day | all | 2.0 | 36 | $226,560 | $+12,301 | 0.54 | +0.07 | Y | Y | Y | Y | no | 0.1294 | 259/2001 |
| ORB | quad_witching | event day | am | 0.0 | 36 | $201,958 | $-12,301 | 0.41 | -0.06 | Y | no | no | no | no |  |  |
| ORB | quad_witching | event day | am | 0.5 | 36 | $208,108 | $-6,151 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quad_witching | event day | am | 1.5 | 36 | $220,410 | $+6,151 | 0.50 | +0.03 | Y | Y | Y | Y | no | 0.1264 | 253/2001 |
| ORB | quad_witching | event day | am | 2.0 | 36 | $226,560 | $+12,301 | 0.54 | +0.07 | Y | Y | Y | Y | no | 0.1264 | 253/2001 |
| ORB | quad_witching | event day | pm | 0.0 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | event day | pm | 0.5 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | event day | pm | 1.5 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | event day | pm | 2.0 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | day before | all | 0.0 | 37 | $192,274 | $-21,986 | 0.42 | -0.05 | Y | no | no | no | no |  |  |
| ORB | quad_witching | day before | all | 0.5 | 37 | $203,266 | $-10,993 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quad_witching | day before | all | 1.5 | 37 | $225,252 | $+10,993 | 0.49 | +0.03 | Y | Y | Y | Y | Y | 0.0160 | 32/2001 |
| ORB | quad_witching | day before | all | 2.0 | 37 | $236,245 | $+21,986 | 0.52 | +0.05 | Y | Y | Y | Y | Y | 0.0160 | 32/2001 |
| ORB | quad_witching | day before | am | 0.0 | 35 | $191,872 | $-22,387 | 0.42 | -0.05 | Y | no | no | no | no |  |  |
| ORB | quad_witching | day before | am | 0.5 | 35 | $203,066 | $-11,193 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quad_witching | day before | am | 1.5 | 35 | $225,453 | $+11,193 | 0.49 | +0.03 | Y | Y | Y | Y | Y | 0.0125 | 25/2001 |
| ORB | quad_witching | day before | am | 2.0 | 35 | $236,646 | $+22,387 | 0.52 | +0.05 | Y | Y | Y | Y | Y | 0.0125 | 25/2001 |
| ORB | quad_witching | day before | pm | 0.0 | 2 | $214,660 | $+401 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | quad_witching | day before | pm | 0.5 | 2 | $214,460 | $+201 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | quad_witching | day before | pm | 1.5 | 2 | $214,058 | $-201 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | day before | pm | 2.0 | 2 | $213,858 | $-401 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | all | 0.0 | 23 | $218,944 | $+4,685 | 0.56 | +0.09 | no | Y | Y | no | no |  |  |
| ORB | quad_witching | day after | all | 0.5 | 23 | $216,602 | $+2,343 | 0.51 | +0.04 | no | Y | Y | no | no |  |  |
| ORB | quad_witching | day after | all | 1.5 | 23 | $211,917 | $-2,343 | 0.43 | -0.04 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | all | 2.0 | 23 | $209,574 | $-4,685 | 0.40 | -0.07 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | am | 0.0 | 23 | $218,944 | $+4,685 | 0.56 | +0.09 | no | Y | Y | no | no |  |  |
| ORB | quad_witching | day after | am | 0.5 | 23 | $216,602 | $+2,343 | 0.51 | +0.04 | no | Y | Y | no | no |  |  |
| ORB | quad_witching | day after | am | 1.5 | 23 | $211,917 | $-2,343 | 0.43 | -0.04 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | am | 2.0 | 23 | $209,574 | $-4,685 | 0.40 | -0.07 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | pm | 0.0 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | pm | 0.5 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | pm | 1.5 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | quad_witching | day after | pm | 2.0 | 0 | $214,259 | $+0 | 0.47 | +0.00 | no | no | no | no | no |  |  |
| ORB | month_start | event day | all | 0.0 | 173 | $207,021 | $-7,238 | 0.53 | +0.07 | Y | no | Y | no | no |  |  |
| ORB | month_start | event day | all | 0.5 | 173 | $210,640 | $-3,619 | 0.50 | +0.04 | Y | no | Y | no | no |  |  |
| ORB | month_start | event day | all | 1.5 | 173 | $217,878 | $+3,619 | 0.44 | -0.03 | Y | Y | no | no | no |  |  |
| ORB | month_start | event day | all | 2.0 | 173 | $221,497 | $+7,238 | 0.41 | -0.06 | Y | Y | no | no | no |  |  |
| ORB | month_start | event day | am | 0.0 | 163 | $213,974 | $-285 | 0.55 | +0.08 | Y | no | Y | no | no |  |  |
| ORB | month_start | event day | am | 0.5 | 163 | $214,117 | $-142 | 0.51 | +0.04 | Y | no | Y | no | no |  |  |
| ORB | month_start | event day | am | 1.5 | 163 | $214,402 | $+142 | 0.43 | -0.04 | Y | Y | no | no | no |  |  |
| ORB | month_start | event day | am | 2.0 | 163 | $214,544 | $+285 | 0.40 | -0.07 | Y | Y | no | no | no |  |  |
| ORB | month_start | event day | pm | 0.0 | 10 | $207,306 | $-6,953 | 0.45 | -0.02 | no | no | no | no | no |  |  |
| ORB | month_start | event day | pm | 0.5 | 10 | $210,782 | $-3,477 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | month_start | event day | pm | 1.5 | 10 | $217,736 | $+3,477 | 0.48 | +0.01 | no | Y | Y | Y | no |  |  |
| ORB | month_start | event day | pm | 2.0 | 10 | $221,213 | $+6,953 | 0.48 | +0.02 | no | Y | Y | Y | no |  |  |
| ORB | month_start | day before | all | 0.0 | 161 | $221,488 | $+7,229 | 0.50 | +0.03 | Y | Y | Y | no | no |  |  |
| ORB | month_start | day before | all | 0.5 | 161 | $217,873 | $+3,614 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | month_start | day before | all | 1.5 | 161 | $210,645 | $-3,614 | 0.43 | -0.03 | Y | no | no | no | no |  |  |
| ORB | month_start | day before | all | 2.0 | 161 | $207,030 | $-7,229 | 0.40 | -0.06 | Y | no | no | no | no |  |  |
| ORB | month_start | day before | am | 0.0 | 150 | $227,316 | $+13,056 | 0.50 | +0.04 | Y | Y | Y | Y | Y | 0.0445 | 89/2001 |
| ORB | month_start | day before | am | 0.5 | 150 | $220,787 | $+6,528 | 0.49 | +0.02 | Y | Y | Y | Y | Y | 0.0445 | 89/2001 |
| ORB | month_start | day before | am | 1.5 | 150 | $207,731 | $-6,528 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | month_start | day before | am | 2.0 | 150 | $201,203 | $-13,056 | 0.40 | -0.07 | Y | no | no | no | no |  |  |
| ORB | month_start | day before | pm | 0.0 | 11 | $208,431 | $-5,828 | 0.46 | -0.00 | no | no | no | no | no |  |  |
| ORB | month_start | day before | pm | 0.5 | 11 | $211,345 | $-2,914 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | month_start | day before | pm | 1.5 | 11 | $217,173 | $+2,914 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | month_start | day before | pm | 2.0 | 11 | $220,087 | $+5,828 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | month_start | day after | all | 0.0 | 186 | $164,322 | $-49,937 | 0.31 | -0.15 | Y | no | no | no | no |  |  |
| ORB | month_start | day after | all | 0.5 | 186 | $189,290 | $-24,969 | 0.41 | -0.06 | Y | no | no | no | no |  |  |
| ORB | month_start | day after | all | 1.5 | 186 | $239,228 | $+24,969 | 0.50 | +0.04 | Y | Y | Y | no | no |  |  |
| ORB | month_start | day after | all | 2.0 | 186 | $264,196 | $+49,937 | 0.54 | +0.07 | Y | Y | Y | no | no |  |  |
| ORB | month_start | day after | am | 0.0 | 175 | $163,690 | $-50,570 | 0.31 | -0.16 | Y | no | no | no | no |  |  |
| ORB | month_start | day after | am | 0.5 | 175 | $188,974 | $-25,285 | 0.41 | -0.06 | Y | no | no | no | no |  |  |
| ORB | month_start | day after | am | 1.5 | 175 | $239,544 | $+25,285 | 0.51 | +0.04 | Y | Y | Y | Y | Y | 0.0370 | 74/2001 |
| ORB | month_start | day after | am | 2.0 | 175 | $264,829 | $+50,569 | 0.54 | +0.07 | Y | Y | Y | Y | Y | 0.0370 | 74/2001 |
| ORB | month_start | day after | pm | 0.0 | 11 | $214,891 | $+632 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | month_start | day after | pm | 0.5 | 11 | $214,575 | $+316 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | month_start | day after | pm | 1.5 | 11 | $213,943 | $-316 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | month_start | day after | pm | 2.0 | 11 | $213,627 | $-632 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | month_end | event day | all | 0.0 | 159 | $236,392 | $+22,132 | 0.48 | +0.01 | Y | Y | Y | Y | Y | 0.0105 | 21/2001 |
| ORB | month_end | event day | all | 0.5 | 159 | $225,325 | $+11,066 | 0.48 | +0.01 | Y | Y | Y | Y | Y | 0.0105 | 21/2001 |
| ORB | month_end | event day | all | 1.5 | 159 | $203,193 | $-11,066 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | month_end | event day | all | 2.0 | 159 | $192,127 | $-22,132 | 0.42 | -0.05 | Y | no | no | no | no |  |  |
| ORB | month_end | event day | am | 0.0 | 147 | $238,444 | $+24,185 | 0.47 | +0.01 | Y | Y | Y | Y | Y | 0.0100 | 20/2001 |
| ORB | month_end | event day | am | 0.5 | 147 | $226,351 | $+12,092 | 0.47 | +0.01 | Y | Y | Y | Y | Y | 0.0100 | 20/2001 |
| ORB | month_end | event day | am | 1.5 | 147 | $202,167 | $-12,092 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | month_end | event day | am | 2.0 | 147 | $190,075 | $-24,185 | 0.42 | -0.05 | Y | no | no | no | no |  |  |
| ORB | month_end | event day | pm | 0.0 | 12 | $212,207 | $-2,052 | 0.47 | +0.01 | no | no | Y | no | no |  |  |
| ORB | month_end | event day | pm | 0.5 | 12 | $213,233 | $-1,026 | 0.47 | +0.00 | no | no | Y | no | no |  |  |
| ORB | month_end | event day | pm | 1.5 | 12 | $215,285 | $+1,026 | 0.47 | -0.00 | no | Y | no | Y | no |  |  |
| ORB | month_end | event day | pm | 2.0 | 12 | $216,311 | $+2,052 | 0.46 | -0.00 | no | Y | no | Y | no |  |  |
| ORB | month_end | day before | all | 0.0 | 170 | $188,014 | $-26,245 | 0.35 | -0.12 | Y | no | no | no | no |  |  |
| ORB | month_end | day before | all | 0.5 | 170 | $201,136 | $-13,123 | 0.40 | -0.07 | Y | no | no | no | no |  |  |
| ORB | month_end | day before | all | 1.5 | 170 | $227,382 | $+13,123 | 0.53 | +0.06 | Y | Y | Y | no | no |  |  |
| ORB | month_end | day before | all | 2.0 | 170 | $240,504 | $+26,245 | 0.58 | +0.11 | Y | Y | Y | no | no |  |  |
| ORB | month_end | day before | am | 0.0 | 156 | $188,075 | $-26,185 | 0.36 | -0.11 | Y | no | no | no | no |  |  |
| ORB | month_end | day before | am | 0.5 | 156 | $201,167 | $-13,092 | 0.41 | -0.06 | Y | no | no | no | no |  |  |
| ORB | month_end | day before | am | 1.5 | 156 | $227,351 | $+13,092 | 0.52 | +0.05 | Y | Y | Y | no | no |  |  |
| ORB | month_end | day before | am | 2.0 | 156 | $240,444 | $+26,185 | 0.57 | +0.10 | Y | Y | Y | no | no |  |  |
| ORB | month_end | day before | pm | 0.0 | 14 | $214,198 | $-61 | 0.45 | -0.02 | no | no | no | no | no |  |  |
| ORB | month_end | day before | pm | 0.5 | 14 | $214,229 | $-30 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | month_end | day before | pm | 1.5 | 14 | $214,289 | $+30 | 0.48 | +0.01 | no | Y | Y | no | no |  |  |
| ORB | month_end | day before | pm | 2.0 | 14 | $214,320 | $+61 | 0.48 | +0.02 | no | Y | Y | no | no |  |  |
| ORB | month_end | day after | all | 0.0 | 161 | $222,103 | $+7,844 | 0.50 | +0.03 | Y | Y | Y | Y | no | 0.0730 | 146/2001 |
| ORB | month_end | day after | all | 0.5 | 161 | $218,181 | $+3,922 | 0.49 | +0.02 | Y | Y | Y | Y | no | 0.0730 | 146/2001 |
| ORB | month_end | day after | all | 1.5 | 161 | $210,337 | $-3,922 | 0.43 | -0.03 | Y | no | no | no | no |  |  |
| ORB | month_end | day after | all | 2.0 | 161 | $206,415 | $-7,844 | 0.40 | -0.06 | Y | no | no | no | no |  |  |
| ORB | month_end | day after | am | 0.0 | 150 | $227,931 | $+13,671 | 0.51 | +0.04 | Y | Y | Y | Y | Y | 0.0425 | 85/2001 |
| ORB | month_end | day after | am | 0.5 | 150 | $221,095 | $+6,836 | 0.49 | +0.02 | Y | Y | Y | Y | Y | 0.0425 | 85/2001 |
| ORB | month_end | day after | am | 1.5 | 150 | $207,423 | $-6,836 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | month_end | day after | am | 2.0 | 150 | $200,588 | $-13,672 | 0.40 | -0.07 | Y | no | no | no | no |  |  |
| ORB | month_end | day after | pm | 0.0 | 11 | $208,431 | $-5,828 | 0.46 | -0.00 | no | no | no | no | no |  |  |
| ORB | month_end | day after | pm | 0.5 | 11 | $211,345 | $-2,914 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | month_end | day after | pm | 1.5 | 11 | $217,173 | $+2,914 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | month_end | day after | pm | 2.0 | 11 | $220,087 | $+5,828 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | quarter_start | event day | all | 0.0 | 60 | $217,984 | $+3,725 | 0.57 | +0.10 | Y | Y | Y | no | no |  |  |
| ORB | quarter_start | event day | all | 0.5 | 60 | $216,121 | $+1,862 | 0.51 | +0.04 | Y | Y | Y | no | no |  |  |
| ORB | quarter_start | event day | all | 1.5 | 60 | $212,397 | $-1,862 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | quarter_start | event day | all | 2.0 | 60 | $210,535 | $-3,725 | 0.40 | -0.07 | Y | no | no | no | no |  |  |
| ORB | quarter_start | event day | am | 0.0 | 55 | $218,160 | $+3,901 | 0.57 | +0.10 | Y | Y | Y | no | no |  |  |
| ORB | quarter_start | event day | am | 0.5 | 55 | $216,210 | $+1,951 | 0.51 | +0.04 | Y | Y | Y | no | no |  |  |
| ORB | quarter_start | event day | am | 1.5 | 55 | $212,308 | $-1,951 | 0.43 | -0.04 | Y | no | no | no | no |  |  |
| ORB | quarter_start | event day | am | 2.0 | 55 | $210,358 | $-3,901 | 0.40 | -0.07 | Y | no | no | no | no |  |  |
| ORB | quarter_start | event day | pm | 0.0 | 5 | $214,082 | $-177 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quarter_start | event day | pm | 0.5 | 5 | $214,171 | $-88 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quarter_start | event day | pm | 1.5 | 5 | $214,347 | $+88 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | quarter_start | event day | pm | 2.0 | 5 | $214,436 | $+177 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | quarter_start | day before | all | 0.0 | 57 | $215,022 | $+763 | 0.51 | +0.04 | Y | Y | Y | no | no |  |  |
| ORB | quarter_start | day before | all | 0.5 | 57 | $214,640 | $+381 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | quarter_start | day before | all | 1.5 | 57 | $213,878 | $-381 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | quarter_start | day before | all | 2.0 | 57 | $213,496 | $-763 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_start | day before | am | 0.0 | 51 | $216,893 | $+2,634 | 0.50 | +0.03 | Y | Y | Y | Y | no | 0.2049 | 410/2001 |
| ORB | quarter_start | day before | am | 0.5 | 51 | $215,576 | $+1,317 | 0.48 | +0.02 | Y | Y | Y | Y | no | 0.2049 | 410/2001 |
| ORB | quarter_start | day before | am | 1.5 | 51 | $212,942 | $-1,317 | 0.45 | -0.01 | Y | no | no | no | no |  |  |
| ORB | quarter_start | day before | am | 2.0 | 51 | $211,625 | $-2,634 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_start | day before | pm | 0.0 | 6 | $212,388 | $-1,871 | 0.47 | +0.01 | no | no | Y | no | no |  |  |
| ORB | quarter_start | day before | pm | 0.5 | 6 | $213,324 | $-936 | 0.47 | +0.00 | no | no | Y | no | no |  |  |
| ORB | quarter_start | day before | pm | 1.5 | 6 | $215,195 | $+936 | 0.47 | -0.00 | no | Y | no | Y | no |  |  |
| ORB | quarter_start | day before | pm | 2.0 | 6 | $216,130 | $+1,871 | 0.46 | -0.01 | no | Y | no | Y | no |  |  |
| ORB | quarter_start | day after | all | 0.0 | 63 | $201,733 | $-12,526 | 0.49 | +0.03 | Y | no | Y | no | no |  |  |
| ORB | quarter_start | day after | all | 0.5 | 63 | $207,996 | $-6,263 | 0.48 | +0.01 | Y | no | Y | no | no |  |  |
| ORB | quarter_start | day after | all | 1.5 | 63 | $220,522 | $+6,263 | 0.46 | -0.01 | Y | Y | no | no | no |  |  |
| ORB | quarter_start | day after | all | 2.0 | 63 | $226,785 | $+12,526 | 0.45 | -0.02 | Y | Y | no | no | no |  |  |
| ORB | quarter_start | day after | am | 0.0 | 58 | $200,960 | $-13,299 | 0.49 | +0.02 | Y | no | Y | no | no |  |  |
| ORB | quarter_start | day after | am | 0.5 | 58 | $207,609 | $-6,650 | 0.48 | +0.01 | Y | no | Y | no | no |  |  |
| ORB | quarter_start | day after | am | 1.5 | 58 | $220,909 | $+6,650 | 0.46 | -0.01 | Y | Y | no | no | no |  |  |
| ORB | quarter_start | day after | am | 2.0 | 58 | $227,558 | $+13,299 | 0.45 | -0.02 | Y | Y | no | no | no |  |  |
| ORB | quarter_start | day after | pm | 0.0 | 5 | $215,032 | $+773 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | quarter_start | day after | pm | 0.5 | 5 | $214,646 | $+387 | 0.47 | +0.00 | no | Y | Y | Y | no |  |  |
| ORB | quarter_start | day after | pm | 1.5 | 5 | $213,872 | $-387 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quarter_start | day after | pm | 2.0 | 5 | $213,486 | $-773 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quarter_end | event day | all | 0.0 | 53 | $225,759 | $+11,500 | 0.50 | +0.04 | Y | Y | Y | Y | no | 0.0520 | 104/2001 |
| ORB | quarter_end | event day | all | 0.5 | 53 | $220,009 | $+5,750 | 0.49 | +0.02 | Y | Y | Y | Y | no | 0.0520 | 104/2001 |
| ORB | quarter_end | event day | all | 1.5 | 53 | $208,509 | $-5,750 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | quarter_end | event day | all | 2.0 | 53 | $202,759 | $-11,500 | 0.43 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_end | event day | am | 0.0 | 49 | $227,106 | $+12,847 | 0.50 | +0.03 | Y | Y | Y | Y | Y | 0.0375 | 75/2001 |
| ORB | quarter_end | event day | am | 0.5 | 49 | $220,683 | $+6,424 | 0.48 | +0.01 | Y | Y | Y | Y | Y | 0.0375 | 75/2001 |
| ORB | quarter_end | event day | am | 1.5 | 49 | $207,835 | $-6,424 | 0.45 | -0.01 | Y | no | no | no | no |  |  |
| ORB | quarter_end | event day | am | 2.0 | 49 | $201,412 | $-12,847 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_end | event day | pm | 0.0 | 4 | $212,912 | $-1,347 | 0.47 | +0.01 | no | no | Y | no | no |  |  |
| ORB | quarter_end | event day | pm | 0.5 | 4 | $213,585 | $-674 | 0.47 | +0.00 | no | no | Y | no | no |  |  |
| ORB | quarter_end | event day | pm | 1.5 | 4 | $214,933 | $+674 | 0.46 | -0.00 | no | Y | no | no | no |  |  |
| ORB | quarter_end | event day | pm | 2.0 | 4 | $215,606 | $+1,347 | 0.46 | -0.01 | no | Y | no | no | no |  |  |
| ORB | quarter_end | day before | all | 0.0 | 55 | $216,150 | $+1,891 | 0.50 | +0.03 | Y | Y | Y | no | no |  |  |
| ORB | quarter_end | day before | all | 0.5 | 55 | $215,205 | $+946 | 0.48 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | quarter_end | day before | all | 1.5 | 55 | $213,313 | $-946 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day before | all | 2.0 | 55 | $212,368 | $-1,891 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day before | am | 0.0 | 50 | $216,017 | $+1,758 | 0.50 | +0.03 | Y | Y | Y | no | no |  |  |
| ORB | quarter_end | day before | am | 0.5 | 50 | $215,138 | $+879 | 0.48 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | quarter_end | day before | am | 1.5 | 50 | $213,380 | $-879 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day before | am | 2.0 | 50 | $212,501 | $-1,758 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day before | pm | 0.0 | 5 | $214,392 | $+133 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | quarter_end | day before | pm | 0.5 | 5 | $214,326 | $+67 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | quarter_end | day before | pm | 1.5 | 5 | $214,192 | $-67 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quarter_end | day before | pm | 2.0 | 5 | $214,126 | $-133 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | quarter_end | day after | all | 0.0 | 57 | $215,637 | $+1,378 | 0.51 | +0.04 | Y | Y | Y | no | no |  |  |
| ORB | quarter_end | day after | all | 0.5 | 57 | $214,948 | $+689 | 0.49 | +0.02 | Y | Y | Y | no | no |  |  |
| ORB | quarter_end | day after | all | 1.5 | 57 | $213,570 | $-689 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day after | all | 2.0 | 57 | $212,881 | $-1,378 | 0.43 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day after | am | 0.0 | 51 | $217,508 | $+3,249 | 0.50 | +0.03 | Y | Y | Y | Y | no | 0.1844 | 369/2001 |
| ORB | quarter_end | day after | am | 0.5 | 51 | $215,883 | $+1,624 | 0.48 | +0.02 | Y | Y | Y | Y | no | 0.1844 | 369/2001 |
| ORB | quarter_end | day after | am | 1.5 | 51 | $212,635 | $-1,624 | 0.45 | -0.02 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day after | am | 2.0 | 51 | $211,010 | $-3,249 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | quarter_end | day after | pm | 0.0 | 6 | $212,388 | $-1,871 | 0.47 | +0.01 | no | no | Y | no | no |  |  |
| ORB | quarter_end | day after | pm | 0.5 | 6 | $213,324 | $-936 | 0.47 | +0.00 | no | no | Y | no | no |  |  |
| ORB | quarter_end | day after | pm | 1.5 | 6 | $215,195 | $+936 | 0.47 | -0.00 | no | Y | no | Y | no |  |  |
| ORB | quarter_end | day after | pm | 2.0 | 6 | $216,130 | $+1,871 | 0.46 | -0.01 | no | Y | no | Y | no |  |  |
| ORB | fed_blackout | event day | all | 0.0 | 424 | $176,934 | $-37,325 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | event day | all | 0.5 | 424 | $195,597 | $-18,663 | 0.49 | +0.02 | Y | no | Y | no | no |  |  |
| ORB | fed_blackout | event day | all | 1.5 | 424 | $232,922 | $+18,663 | 0.45 | -0.01 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | event day | all | 2.0 | 424 | $251,584 | $+37,325 | 0.44 | -0.03 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | event day | am | 0.0 | 403 | $177,813 | $-36,447 | 0.45 | -0.01 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | event day | am | 0.5 | 403 | $196,036 | $-18,223 | 0.49 | +0.02 | Y | no | Y | no | no |  |  |
| ORB | fed_blackout | event day | am | 1.5 | 403 | $232,482 | $+18,223 | 0.45 | -0.02 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | event day | am | 2.0 | 403 | $250,706 | $+36,447 | 0.44 | -0.03 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | event day | pm | 0.0 | 21 | $213,380 | $-879 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fed_blackout | event day | pm | 0.5 | 21 | $213,820 | $-439 | 0.47 | -0.00 | no | no | no | no | no |  |  |
| ORB | fed_blackout | event day | pm | 1.5 | 21 | $214,698 | $+439 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | fed_blackout | event day | pm | 2.0 | 21 | $215,138 | $+879 | 0.47 | +0.00 | no | Y | Y | no | no |  |  |
| ORB | fed_blackout | day before | all | 0.0 | 403 | $161,445 | $-52,814 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | day before | all | 0.5 | 403 | $187,852 | $-26,407 | 0.46 | -0.01 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | day before | all | 1.5 | 403 | $240,666 | $+26,407 | 0.47 | -0.00 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | day before | all | 2.0 | 403 | $267,073 | $+52,814 | 0.44 | -0.03 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | day before | am | 0.0 | 387 | $167,620 | $-46,640 | 0.46 | -0.01 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | day before | am | 0.5 | 387 | $190,939 | $-23,320 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fed_blackout | day before | am | 1.5 | 387 | $237,579 | $+23,320 | 0.46 | -0.01 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | day before | am | 2.0 | 387 | $260,899 | $+46,640 | 0.43 | -0.04 | Y | Y | no | Y | no |  |  |
| ORB | fed_blackout | day before | pm | 0.0 | 16 | $208,085 | $-6,174 | 0.45 | -0.01 | no | no | no | no | no |  |  |
| ORB | fed_blackout | day before | pm | 0.5 | 16 | $211,172 | $-3,087 | 0.46 | -0.01 | no | no | no | no | no |  |  |
| ORB | fed_blackout | day before | pm | 1.5 | 16 | $217,346 | $+3,087 | 0.47 | +0.01 | no | Y | Y | no | no |  |  |
| ORB | fed_blackout | day before | pm | 2.0 | 16 | $220,434 | $+6,174 | 0.48 | +0.01 | no | Y | Y | no | no |  |  |
| ORB | fed_blackout | day after | all | 0.0 | 436 | $196,929 | $-17,330 | 0.44 | -0.03 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | day after | all | 0.5 | 436 | $205,594 | $-8,665 | 0.47 | +0.00 | Y | no | Y | no | no |  |  |
| ORB | fed_blackout | day after | all | 1.5 | 436 | $222,924 | $+8,665 | 0.47 | -0.00 | Y | Y | no | no | no |  |  |
| ORB | fed_blackout | day after | all | 2.0 | 436 | $231,589 | $+17,330 | 0.41 | -0.06 | Y | Y | no | no | no |  |  |
| ORB | fed_blackout | day after | am | 0.0 | 394 | $201,087 | $-13,172 | 0.46 | -0.01 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | day after | am | 0.5 | 394 | $207,673 | $-6,586 | 0.48 | +0.02 | Y | no | Y | no | no |  |  |
| ORB | fed_blackout | day after | am | 1.5 | 394 | $220,845 | $+6,586 | 0.45 | -0.01 | Y | Y | no | no | no |  |  |
| ORB | fed_blackout | day after | am | 2.0 | 394 | $227,432 | $+13,172 | 0.41 | -0.05 | Y | Y | no | no | no |  |  |
| ORB | fed_blackout | day after | pm | 0.0 | 42 | $210,102 | $-4,157 | 0.44 | -0.02 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | day after | pm | 0.5 | 42 | $212,180 | $-2,079 | 0.46 | -0.01 | Y | no | no | no | no |  |  |
| ORB | fed_blackout | day after | pm | 1.5 | 42 | $216,338 | $+2,079 | 0.48 | +0.01 | Y | Y | Y | no | no |  |  |
| ORB | fed_blackout | day after | pm | 2.0 | 42 | $218,416 | $+4,157 | 0.49 | +0.03 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_decision | event day | all | 0.0 | 86 | $279,189 | $+2,127 | 0.31 | -0.08 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | all | 0.5 | 86 | $278,126 | $+1,063 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | all | 1.5 | 86 | $275,999 | $-1,063 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | all | 2.0 | 86 | $274,936 | $-2,127 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | am | 0.0 | 56 | $285,514 | $+8,452 | 0.40 | +0.00 | Y | Y | Y | Y | no | 0.1644 | 329/2001 |
| ENGUQ | fomc_decision | event day | am | 0.5 | 56 | $281,288 | $+4,226 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.1644 | 329/2001 |
| ENGUQ | fomc_decision | event day | am | 1.5 | 56 | $272,837 | $-4,226 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | am | 2.0 | 56 | $268,611 | $-8,452 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | pm | 0.0 | 30 | $270,737 | $-6,325 | 0.30 | -0.09 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | pm | 0.5 | 30 | $273,900 | $-3,163 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | pm | 1.5 | 30 | $280,225 | $+3,163 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | event day | pm | 2.0 | 30 | $283,388 | $+6,325 | 0.34 | -0.05 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | day before | all | 0.0 | 82 | $278,649 | $+1,587 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_decision | day before | all | 0.5 | 82 | $277,856 | $+793 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_decision | day before | all | 1.5 | 82 | $276,269 | $-793 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day before | all | 2.0 | 82 | $275,476 | $-1,587 | 0.31 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day before | am | 0.0 | 53 | $276,207 | $-855 | 0.39 | +0.00 | Y | no | Y | no | no |  |  |
| ENGUQ | fomc_decision | day before | am | 0.5 | 53 | $276,635 | $-428 | 0.39 | +0.00 | Y | no | Y | no | no |  |  |
| ENGUQ | fomc_decision | day before | am | 1.5 | 53 | $277,490 | $+428 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | day before | am | 2.0 | 53 | $277,918 | $+855 | 0.35 | -0.04 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | day before | pm | 0.0 | 29 | $279,504 | $+2,442 | 0.40 | +0.01 | no | Y | Y | Y | no |  |  |
| ENGUQ | fomc_decision | day before | pm | 0.5 | 29 | $278,283 | $+1,221 | 0.40 | +0.01 | no | Y | Y | Y | no |  |  |
| ENGUQ | fomc_decision | day before | pm | 1.5 | 29 | $275,842 | $-1,221 | 0.37 | -0.03 | no | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day before | pm | 2.0 | 29 | $274,621 | $-2,442 | 0.34 | -0.05 | no | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | all | 0.0 | 57 | $259,443 | $-17,620 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | all | 0.5 | 57 | $268,253 | $-8,810 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | all | 1.5 | 57 | $285,872 | $+8,810 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | all | 2.0 | 57 | $294,682 | $+17,620 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | am | 0.0 | 40 | $253,619 | $-23,444 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | am | 0.5 | 40 | $265,341 | $-11,722 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | am | 1.5 | 40 | $288,784 | $+11,722 | 0.41 | +0.02 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_decision | day after | am | 2.0 | 40 | $300,506 | $+23,444 | 0.42 | +0.03 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_decision | day after | pm | 0.0 | 17 | $282,886 | $+5,824 | 0.40 | +0.01 | no | Y | Y | Y | no |  |  |
| ENGUQ | fomc_decision | day after | pm | 0.5 | 17 | $279,974 | $+2,912 | 0.40 | +0.01 | no | Y | Y | Y | no |  |  |
| ENGUQ | fomc_decision | day after | pm | 1.5 | 17 | $274,151 | $-2,912 | 0.37 | -0.02 | no | no | no | no | no |  |  |
| ENGUQ | fomc_decision | day after | pm | 2.0 | 17 | $271,239 | $-5,824 | 0.36 | -0.03 | no | no | no | no | no |  |  |
| ENGUQ | cpi | event day | all | 0.0 | 109 | $260,414 | $-16,648 | 0.30 | -0.09 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | event day | all | 0.5 | 109 | $268,738 | $-8,324 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | event day | all | 1.5 | 109 | $285,387 | $+8,324 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | cpi | event day | all | 2.0 | 109 | $293,711 | $+16,648 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | cpi | event day | am | 0.0 | 76 | $259,280 | $-17,782 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | event day | am | 0.5 | 76 | $268,171 | $-8,891 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | event day | am | 1.5 | 76 | $285,954 | $+8,891 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | cpi | event day | am | 2.0 | 76 | $294,845 | $+17,782 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | cpi | event day | pm | 0.0 | 33 | $278,197 | $+1,134 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | cpi | event day | pm | 0.5 | 33 | $277,630 | $+567 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | cpi | event day | pm | 1.5 | 33 | $276,495 | $-567 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | event day | pm | 2.0 | 33 | $275,928 | $-1,134 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day before | all | 0.0 | 107 | $210,108 | $-66,954 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day before | all | 0.5 | 107 | $243,585 | $-33,477 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day before | all | 1.5 | 107 | $310,540 | $+33,477 | 0.42 | +0.03 | Y | Y | Y | Y | Y | 0.0235 | 47/2001 |
| ENGUQ | cpi | day before | all | 2.0 | 107 | $344,017 | $+66,954 | 0.45 | +0.06 | Y | Y | Y | Y | Y | 0.0235 | 47/2001 |
| ENGUQ | cpi | day before | am | 0.0 | 74 | $212,364 | $-64,699 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day before | am | 0.5 | 74 | $244,713 | $-32,349 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day before | am | 1.5 | 74 | $309,412 | $+32,349 | 0.43 | +0.04 | Y | Y | Y | Y | Y | 0.0255 | 51/2001 |
| ENGUQ | cpi | day before | am | 2.0 | 74 | $341,761 | $+64,699 | 0.47 | +0.08 | Y | Y | Y | Y | Y | 0.0255 | 51/2001 |
| ENGUQ | cpi | day before | pm | 0.0 | 33 | $274,807 | $-2,256 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day before | pm | 0.5 | 33 | $275,935 | $-1,128 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day before | pm | 1.5 | 33 | $278,190 | $+1,128 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | cpi | day before | pm | 2.0 | 33 | $279,318 | $+2,256 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | cpi | day after | all | 0.0 | 136 | $303,955 | $+26,892 | 0.43 | +0.04 | Y | Y | Y | Y | Y | 0.0250 | 50/2001 |
| ENGUQ | cpi | day after | all | 0.5 | 136 | $290,509 | $+13,446 | 0.41 | +0.02 | Y | Y | Y | Y | Y | 0.0250 | 50/2001 |
| ENGUQ | cpi | day after | all | 1.5 | 136 | $263,616 | $-13,446 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day after | all | 2.0 | 136 | $250,170 | $-26,892 | 0.31 | -0.09 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day after | am | 0.0 | 100 | $298,396 | $+21,334 | 0.42 | +0.03 | Y | Y | Y | Y | Y | 0.0295 | 59/2001 |
| ENGUQ | cpi | day after | am | 0.5 | 100 | $287,729 | $+10,667 | 0.41 | +0.02 | Y | Y | Y | Y | Y | 0.0295 | 59/2001 |
| ENGUQ | cpi | day after | am | 1.5 | 100 | $266,396 | $-10,667 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day after | am | 2.0 | 100 | $255,729 | $-21,334 | 0.31 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day after | pm | 0.0 | 36 | $282,621 | $+5,559 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | cpi | day after | pm | 0.5 | 36 | $279,842 | $+2,779 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | cpi | day after | pm | 1.5 | 36 | $274,283 | $-2,779 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | cpi | day after | pm | 2.0 | 36 | $271,504 | $-5,559 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | event day | all | 0.0 | 88 | $249,756 | $-27,307 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | event day | all | 0.5 | 88 | $263,409 | $-13,653 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | event day | all | 1.5 | 88 | $290,716 | $+13,653 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | nfp | event day | all | 2.0 | 88 | $304,369 | $+27,307 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | nfp | event day | am | 0.0 | 78 | $239,709 | $-37,354 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | event day | am | 0.5 | 78 | $258,386 | $-18,677 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | event day | am | 1.5 | 78 | $295,739 | $+18,677 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | nfp | event day | am | 2.0 | 78 | $314,416 | $+37,354 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | nfp | event day | pm | 0.0 | 10 | $287,109 | $+10,047 | 0.40 | +0.01 | no | Y | Y | Y | no |  |  |
| ENGUQ | nfp | event day | pm | 0.5 | 10 | $282,086 | $+5,023 | 0.40 | +0.01 | no | Y | Y | Y | no |  |  |
| ENGUQ | nfp | event day | pm | 1.5 | 10 | $272,039 | $-5,023 | 0.37 | -0.02 | no | no | no | no | no |  |  |
| ENGUQ | nfp | event day | pm | 2.0 | 10 | $267,016 | $-10,047 | 0.35 | -0.04 | no | no | no | no | no |  |  |
| ENGUQ | nfp | day before | all | 0.0 | 100 | $253,948 | $-23,114 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day before | all | 0.5 | 100 | $265,505 | $-11,557 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day before | all | 1.5 | 100 | $288,619 | $+11,557 | 0.35 | -0.04 | Y | Y | no | Y | no |  |  |
| ENGUQ | nfp | day before | all | 2.0 | 100 | $300,176 | $+23,114 | 0.32 | -0.07 | Y | Y | no | Y | no |  |  |
| ENGUQ | nfp | day before | am | 0.0 | 66 | $235,479 | $-41,584 | 0.34 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day before | am | 0.5 | 66 | $256,271 | $-20,792 | 0.37 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day before | am | 1.5 | 66 | $297,854 | $+20,792 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.0875 | 175/2001 |
| ENGUQ | nfp | day before | am | 2.0 | 66 | $318,646 | $+41,584 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.0875 | 175/2001 |
| ENGUQ | nfp | day before | pm | 0.0 | 34 | $295,532 | $+18,470 | 0.42 | +0.03 | Y | Y | Y | Y | Y | 0.0045 | 9/2001 |
| ENGUQ | nfp | day before | pm | 0.5 | 34 | $286,297 | $+9,235 | 0.41 | +0.02 | Y | Y | Y | Y | Y | 0.0045 | 9/2001 |
| ENGUQ | nfp | day before | pm | 1.5 | 34 | $267,828 | $-9,235 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day before | pm | 2.0 | 34 | $258,593 | $-18,470 | 0.30 | -0.09 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day after | all | 0.0 | 82 | $207,949 | $-69,113 | 0.27 | -0.12 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day after | all | 0.5 | 82 | $242,506 | $-34,557 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day after | all | 1.5 | 82 | $311,619 | $+34,557 | 0.44 | +0.05 | Y | Y | Y | Y | Y | 0.0215 | 43/2001 |
| ENGUQ | nfp | day after | all | 2.0 | 82 | $346,176 | $+69,113 | 0.48 | +0.09 | Y | Y | Y | Y | Y | 0.0215 | 43/2001 |
| ENGUQ | nfp | day after | am | 0.0 | 57 | $208,195 | $-68,867 | 0.27 | -0.12 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day after | am | 0.5 | 57 | $242,629 | $-34,434 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | nfp | day after | am | 1.5 | 57 | $311,496 | $+34,434 | 0.44 | +0.05 | Y | Y | Y | Y | Y | 0.0190 | 38/2001 |
| ENGUQ | nfp | day after | am | 2.0 | 57 | $345,930 | $+68,867 | 0.49 | +0.10 | Y | Y | Y | Y | Y | 0.0190 | 38/2001 |
| ENGUQ | nfp | day after | pm | 0.0 | 25 | $276,816 | $-246 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | nfp | day after | pm | 0.5 | 25 | $276,939 | $-123 | 0.39 | +0.00 | no | no | Y | no | no |  |  |
| ENGUQ | nfp | day after | pm | 1.5 | 25 | $277,185 | $+123 | 0.39 | -0.00 | no | Y | no | no | no |  |  |
| ENGUQ | nfp | day after | pm | 2.0 | 25 | $277,308 | $+246 | 0.39 | -0.01 | no | Y | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | all | 0.0 | 95 | $250,393 | $-26,670 | 0.28 | -0.11 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | all | 0.5 | 95 | $263,728 | $-13,335 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | all | 1.5 | 95 | $290,397 | $+13,335 | 0.41 | +0.01 | Y | Y | Y | Y | no | 0.1639 | 328/2001 |
| ENGUQ | fomc_minutes | event day | all | 2.0 | 95 | $303,732 | $+26,670 | 0.39 | +0.00 | Y | Y | Y | Y | no | 0.1639 | 328/2001 |
| ENGUQ | fomc_minutes | event day | am | 0.0 | 61 | $261,505 | $-15,557 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | am | 0.5 | 61 | $269,284 | $-7,779 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | am | 1.5 | 61 | $284,841 | $+7,779 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_minutes | event day | am | 2.0 | 61 | $292,620 | $+15,557 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | pm | 0.0 | 34 | $265,950 | $-11,113 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | pm | 0.5 | 34 | $271,506 | $-5,556 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | event day | pm | 1.5 | 34 | $282,619 | $+5,556 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_minutes | event day | pm | 2.0 | 34 | $288,175 | $+11,113 | 0.41 | +0.02 | Y | Y | Y | no | no |  |  |
| ENGUQ | fomc_minutes | day before | all | 0.0 | 62 | $286,891 | $+9,828 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.1679 | 336/2001 |
| ENGUQ | fomc_minutes | day before | all | 0.5 | 62 | $281,977 | $+4,914 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.1679 | 336/2001 |
| ENGUQ | fomc_minutes | day before | all | 1.5 | 62 | $272,148 | $-4,914 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day before | all | 2.0 | 62 | $267,234 | $-9,828 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day before | am | 0.0 | 46 | $289,578 | $+12,515 | 0.41 | +0.02 | Y | Y | Y | Y | no | 0.0890 | 178/2001 |
| ENGUQ | fomc_minutes | day before | am | 0.5 | 46 | $283,320 | $+6,258 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.0890 | 178/2001 |
| ENGUQ | fomc_minutes | day before | am | 1.5 | 46 | $270,805 | $-6,258 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day before | am | 2.0 | 46 | $264,547 | $-12,515 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day before | pm | 0.0 | 16 | $274,376 | $-2,687 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day before | pm | 0.5 | 16 | $275,719 | $-1,343 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day before | pm | 1.5 | 16 | $278,406 | $+1,343 | 0.39 | +0.00 | no | Y | Y | Y | no |  |  |
| ENGUQ | fomc_minutes | day before | pm | 2.0 | 16 | $279,749 | $+2,687 | 0.39 | +0.00 | no | Y | Y | Y | no |  |  |
| ENGUQ | fomc_minutes | day after | all | 0.0 | 56 | $248,247 | $-28,816 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day after | all | 0.5 | 56 | $262,655 | $-14,408 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day after | all | 1.5 | 56 | $291,470 | $+14,408 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.1164 | 233/2001 |
| ENGUQ | fomc_minutes | day after | all | 2.0 | 56 | $305,878 | $+28,816 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.1164 | 233/2001 |
| ENGUQ | fomc_minutes | day after | am | 0.0 | 31 | $248,748 | $-28,315 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day after | am | 0.5 | 31 | $262,905 | $-14,157 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | fomc_minutes | day after | am | 1.5 | 31 | $291,220 | $+14,157 | 0.41 | +0.02 | Y | Y | Y | Y | no | 0.1029 | 206/2001 |
| ENGUQ | fomc_minutes | day after | am | 2.0 | 31 | $305,377 | $+28,315 | 0.42 | +0.03 | Y | Y | Y | Y | no | 0.1029 | 206/2001 |
| ENGUQ | fomc_minutes | day after | pm | 0.0 | 25 | $276,561 | $-501 | 0.39 | +0.00 | no | no | Y | no | no |  |  |
| ENGUQ | fomc_minutes | day after | pm | 0.5 | 25 | $276,812 | $-251 | 0.39 | +0.00 | no | no | Y | no | no |  |  |
| ENGUQ | fomc_minutes | day after | pm | 1.5 | 25 | $277,313 | $+250 | 0.38 | -0.01 | no | Y | no | no | no |  |  |
| ENGUQ | fomc_minutes | day after | pm | 2.0 | 25 | $277,563 | $+501 | 0.37 | -0.02 | no | Y | no | no | no |  |  |
| ENGUQ | quad_witching | event day | all | 0.0 | 30 | $282,100 | $+5,037 | 0.35 | -0.04 | Y | Y | no | no | no |  |  |
| ENGUQ | quad_witching | event day | all | 0.5 | 30 | $279,581 | $+2,519 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | quad_witching | event day | all | 1.5 | 30 | $274,544 | $-2,519 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | event day | all | 2.0 | 30 | $272,025 | $-5,037 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | event day | am | 0.0 | 29 | $279,844 | $+2,782 | 0.35 | -0.05 | no | Y | no | no | no |  |  |
| ENGUQ | quad_witching | event day | am | 0.5 | 29 | $278,453 | $+1,391 | 0.37 | -0.02 | no | Y | no | no | no |  |  |
| ENGUQ | quad_witching | event day | am | 1.5 | 29 | $275,672 | $-1,391 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | event day | am | 2.0 | 29 | $274,281 | $-2,782 | 0.38 | -0.01 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | event day | pm | 0.0 | 1 | $279,318 | $+2,256 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | event day | pm | 0.5 | 1 | $278,190 | $+1,128 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | event day | pm | 1.5 | 1 | $275,935 | $-1,128 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | event day | pm | 2.0 | 1 | $274,807 | $-2,256 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | day before | all | 0.0 | 46 | $285,973 | $+8,910 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.1329 | 266/2001 |
| ENGUQ | quad_witching | day before | all | 0.5 | 46 | $281,518 | $+4,455 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.1329 | 266/2001 |
| ENGUQ | quad_witching | day before | all | 1.5 | 46 | $272,607 | $-4,455 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | day before | all | 2.0 | 46 | $268,152 | $-8,910 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | day before | am | 0.0 | 31 | $287,648 | $+10,585 | 0.41 | +0.01 | Y | Y | Y | Y | no | 0.0715 | 143/2001 |
| ENGUQ | quad_witching | day before | am | 0.5 | 31 | $282,355 | $+5,293 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.0715 | 143/2001 |
| ENGUQ | quad_witching | day before | am | 1.5 | 31 | $271,770 | $-5,293 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | day before | am | 2.0 | 31 | $266,477 | $-10,585 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | day before | pm | 0.0 | 15 | $275,387 | $-1,675 | 0.38 | -0.02 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | day before | pm | 0.5 | 15 | $276,225 | $-838 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | day before | pm | 1.5 | 15 | $277,900 | $+838 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | day before | pm | 2.0 | 15 | $278,738 | $+1,675 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | day after | all | 0.0 | 34 | $267,015 | $-10,048 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | day after | all | 0.5 | 34 | $272,039 | $-5,024 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quad_witching | day after | all | 1.5 | 34 | $282,086 | $+5,024 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | day after | all | 2.0 | 34 | $287,110 | $+10,048 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | day after | am | 0.0 | 21 | $269,039 | $-8,024 | 0.38 | -0.01 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | day after | am | 0.5 | 21 | $273,051 | $-4,012 | 0.38 | -0.01 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | day after | am | 1.5 | 21 | $281,074 | $+4,012 | 0.40 | +0.01 | no | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | day after | am | 2.0 | 21 | $285,086 | $+8,024 | 0.40 | +0.01 | no | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | day after | pm | 0.0 | 13 | $275,039 | $-2,024 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | day after | pm | 0.5 | 13 | $276,051 | $-1,012 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quad_witching | day after | pm | 1.5 | 13 | $278,074 | $+1,012 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quad_witching | day after | pm | 2.0 | 13 | $279,086 | $+2,024 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | month_start | event day | all | 0.0 | 246 | $228,162 | $-48,900 | 0.34 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | event day | all | 0.5 | 246 | $252,612 | $-24,450 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | event day | all | 1.5 | 246 | $301,513 | $+24,450 | 0.39 | +0.00 | Y | Y | Y | Y | no | 0.2169 | 434/2001 |
| ENGUQ | month_start | event day | all | 2.0 | 246 | $325,963 | $+48,900 | 0.38 | -0.01 | Y | Y | no | Y | no |  |  |
| ENGUQ | month_start | event day | am | 0.0 | 177 | $234,202 | $-42,861 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | event day | am | 0.5 | 177 | $255,632 | $-21,430 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | event day | am | 1.5 | 177 | $298,493 | $+21,430 | 0.39 | -0.00 | Y | Y | no | Y | no |  |  |
| ENGUQ | month_start | event day | am | 2.0 | 177 | $319,923 | $+42,861 | 0.39 | -0.00 | Y | Y | no | Y | no |  |  |
| ENGUQ | month_start | event day | pm | 0.0 | 69 | $271,023 | $-6,039 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | event day | pm | 0.5 | 69 | $274,043 | $-3,020 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | event day | pm | 1.5 | 69 | $280,082 | $+3,020 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | month_start | event day | pm | 2.0 | 69 | $283,102 | $+6,039 | 0.37 | -0.02 | Y | Y | no | no | no |  |  |
| ENGUQ | month_start | day before | all | 0.0 | 235 | $281,953 | $+4,890 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | month_start | day before | all | 0.5 | 235 | $279,508 | $+2,445 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day before | all | 1.5 | 235 | $274,617 | $-2,445 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day before | all | 2.0 | 235 | $272,172 | $-4,890 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day before | am | 0.0 | 178 | $284,762 | $+7,700 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day before | am | 0.5 | 178 | $280,912 | $+3,850 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day before | am | 1.5 | 178 | $273,212 | $-3,850 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day before | am | 2.0 | 178 | $269,362 | $-7,700 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day before | pm | 0.0 | 57 | $274,253 | $-2,810 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day before | pm | 0.5 | 57 | $275,658 | $-1,405 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day before | pm | 1.5 | 57 | $278,467 | $+1,405 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day before | pm | 2.0 | 57 | $279,872 | $+2,810 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day after | all | 0.0 | 239 | $229,810 | $-47,252 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day after | all | 0.5 | 239 | $253,436 | $-23,626 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day after | all | 1.5 | 239 | $300,689 | $+23,626 | 0.35 | -0.04 | Y | Y | no | no | no |  |  |
| ENGUQ | month_start | day after | all | 2.0 | 239 | $324,315 | $+47,252 | 0.31 | -0.08 | Y | Y | no | no | no |  |  |
| ENGUQ | month_start | day after | am | 0.0 | 171 | $219,603 | $-57,460 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day after | am | 0.5 | 171 | $248,333 | $-28,730 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day after | am | 1.5 | 171 | $305,792 | $+28,730 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day after | am | 2.0 | 171 | $334,522 | $+57,460 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | month_start | day after | pm | 0.0 | 68 | $287,270 | $+10,207 | 0.41 | +0.02 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day after | pm | 0.5 | 68 | $282,166 | $+5,104 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_start | day after | pm | 1.5 | 68 | $271,959 | $-5,104 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | month_start | day after | pm | 2.0 | 68 | $266,855 | $-10,207 | 0.31 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | event day | all | 0.0 | 241 | $247,509 | $-29,553 | 0.26 | -0.13 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | event day | all | 0.5 | 241 | $262,286 | $-14,777 | 0.32 | -0.07 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | event day | all | 1.5 | 241 | $291,839 | $+14,777 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | event day | all | 2.0 | 241 | $306,616 | $+29,553 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | month_end | event day | am | 0.0 | 190 | $256,508 | $-20,555 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | event day | am | 0.5 | 190 | $266,785 | $-10,277 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | event day | am | 1.5 | 190 | $287,340 | $+10,277 | 0.36 | -0.03 | Y | Y | no | no | no |  |  |
| ENGUQ | month_end | event day | am | 2.0 | 190 | $297,617 | $+20,555 | 0.32 | -0.07 | Y | Y | no | no | no |  |  |
| ENGUQ | month_end | event day | pm | 0.0 | 51 | $268,064 | $-8,999 | 0.29 | -0.11 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | event day | pm | 0.5 | 51 | $272,563 | $-4,499 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | event day | pm | 1.5 | 51 | $281,562 | $+4,499 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | event day | pm | 2.0 | 51 | $286,061 | $+8,999 | 0.41 | +0.02 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | day before | all | 0.0 | 241 | $245,549 | $-31,513 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day before | all | 0.5 | 241 | $261,306 | $-15,757 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day before | all | 1.5 | 241 | $292,819 | $+15,757 | 0.42 | +0.03 | Y | Y | Y | Y | no | 0.3978 | 796/2001 |
| ENGUQ | month_end | day before | all | 2.0 | 241 | $308,576 | $+31,513 | 0.44 | +0.04 | Y | Y | Y | Y | no | 0.3978 | 796/2001 |
| ENGUQ | month_end | day before | am | 0.0 | 198 | $256,853 | $-20,209 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day before | am | 0.5 | 198 | $266,958 | $-10,105 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day before | am | 1.5 | 198 | $287,167 | $+10,105 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | month_end | day before | am | 2.0 | 198 | $297,272 | $+20,209 | 0.36 | -0.03 | Y | Y | no | no | no |  |  |
| ENGUQ | month_end | day before | pm | 0.0 | 43 | $265,758 | $-11,304 | 0.31 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day before | pm | 0.5 | 43 | $271,410 | $-5,652 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day before | pm | 1.5 | 43 | $282,715 | $+5,652 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | day before | pm | 2.0 | 43 | $288,367 | $+11,304 | 0.41 | +0.02 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | day after | all | 0.0 | 233 | $281,241 | $+4,179 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | month_end | day after | all | 0.5 | 233 | $279,152 | $+2,089 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | day after | all | 1.5 | 233 | $274,973 | $-2,089 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day after | all | 2.0 | 233 | $272,884 | $-4,179 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day after | am | 0.0 | 176 | $284,051 | $+6,989 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | day after | am | 0.5 | 176 | $280,557 | $+3,494 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | day after | am | 1.5 | 176 | $273,568 | $-3,494 | 0.33 | -0.06 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day after | am | 2.0 | 176 | $270,074 | $-6,989 | 0.29 | -0.10 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day after | pm | 0.0 | 57 | $274,253 | $-2,810 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day after | pm | 0.5 | 57 | $275,658 | $-1,405 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | month_end | day after | pm | 1.5 | 57 | $278,467 | $+1,405 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | month_end | day after | pm | 2.0 | 57 | $279,872 | $+2,810 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_start | event day | all | 0.0 | 81 | $260,103 | $-16,959 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | event day | all | 0.5 | 81 | $268,583 | $-8,480 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | event day | all | 1.5 | 81 | $285,542 | $+8,480 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | quarter_start | event day | all | 2.0 | 81 | $294,022 | $+16,959 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | quarter_start | event day | am | 0.0 | 59 | $264,291 | $-12,771 | 0.34 | -0.05 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | event day | am | 0.5 | 59 | $270,677 | $-6,386 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | event day | am | 1.5 | 59 | $283,448 | $+6,386 | 0.39 | -0.00 | Y | Y | no | no | no |  |  |
| ENGUQ | quarter_start | event day | am | 2.0 | 59 | $289,834 | $+12,771 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | quarter_start | event day | pm | 0.0 | 22 | $272,875 | $-4,188 | 0.38 | -0.01 | no | no | no | no | no |  |  |
| ENGUQ | quarter_start | event day | pm | 0.5 | 22 | $274,968 | $-2,094 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_start | event day | pm | 1.5 | 22 | $279,156 | $+2,094 | 0.39 | +0.00 | no | Y | Y | Y | no |  |  |
| ENGUQ | quarter_start | event day | pm | 2.0 | 22 | $281,250 | $+4,188 | 0.40 | +0.01 | no | Y | Y | Y | no |  |  |
| ENGUQ | quarter_start | day before | all | 0.0 | 85 | $283,529 | $+6,466 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_start | day before | all | 0.5 | 85 | $280,296 | $+3,233 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_start | day before | all | 1.5 | 85 | $273,829 | $-3,233 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day before | all | 2.0 | 85 | $270,596 | $-6,466 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day before | am | 0.0 | 69 | $282,316 | $+5,253 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.2339 | 468/2001 |
| ENGUQ | quarter_start | day before | am | 0.5 | 69 | $279,689 | $+2,627 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.2339 | 468/2001 |
| ENGUQ | quarter_start | day before | am | 1.5 | 69 | $274,436 | $-2,627 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day before | am | 2.0 | 69 | $271,809 | $-5,253 | 0.36 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day before | pm | 0.0 | 16 | $278,276 | $+1,213 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_start | day before | pm | 0.5 | 16 | $277,669 | $+607 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_start | day before | pm | 1.5 | 16 | $276,456 | $-607 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_start | day before | pm | 2.0 | 16 | $275,849 | $-1,213 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_start | day after | all | 0.0 | 67 | $258,199 | $-18,863 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day after | all | 0.5 | 67 | $267,631 | $-9,432 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day after | all | 1.5 | 67 | $286,494 | $+9,432 | 0.40 | +0.01 | Y | Y | Y | Y | no | 0.2624 | 525/2001 |
| ENGUQ | quarter_start | day after | all | 2.0 | 67 | $295,926 | $+18,863 | 0.39 | -0.00 | Y | Y | no | Y | no |  |  |
| ENGUQ | quarter_start | day after | am | 0.0 | 42 | $260,020 | $-17,042 | 0.37 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day after | am | 0.5 | 42 | $268,541 | $-8,521 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_start | day after | am | 1.5 | 42 | $285,584 | $+8,521 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_start | day after | am | 2.0 | 42 | $294,105 | $+17,042 | 0.38 | -0.01 | Y | Y | no | no | no |  |  |
| ENGUQ | quarter_start | day after | pm | 0.0 | 25 | $275,241 | $-1,821 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_start | day after | pm | 0.5 | 25 | $276,152 | $-910 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_start | day after | pm | 1.5 | 25 | $277,973 | $+910 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_start | day after | pm | 2.0 | 25 | $278,883 | $+1,821 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | event day | all | 0.0 | 85 | $259,499 | $-17,564 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | event day | all | 0.5 | 85 | $268,281 | $-8,782 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | event day | all | 1.5 | 85 | $285,844 | $+8,782 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | event day | all | 2.0 | 85 | $294,626 | $+17,564 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | event day | am | 0.0 | 75 | $256,947 | $-20,116 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | event day | am | 0.5 | 75 | $267,005 | $-10,058 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | event day | am | 1.5 | 75 | $287,120 | $+10,058 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | event day | am | 2.0 | 75 | $297,178 | $+20,116 | 0.39 | +0.00 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | event day | pm | 0.0 | 10 | $279,614 | $+2,552 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | event day | pm | 0.5 | 10 | $278,338 | $+1,276 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | event day | pm | 1.5 | 10 | $275,787 | $-1,276 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_end | event day | pm | 2.0 | 10 | $274,511 | $-2,552 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_end | day before | all | 0.0 | 79 | $259,155 | $-17,908 | 0.37 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day before | all | 0.5 | 79 | $268,109 | $-8,954 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day before | all | 1.5 | 79 | $286,016 | $+8,954 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day before | all | 2.0 | 79 | $294,970 | $+17,908 | 0.41 | +0.02 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day before | am | 0.0 | 66 | $258,861 | $-18,201 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day before | am | 0.5 | 66 | $267,962 | $-9,101 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day before | am | 1.5 | 66 | $286,163 | $+9,101 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day before | am | 2.0 | 66 | $295,264 | $+18,201 | 0.41 | +0.02 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day before | pm | 0.0 | 13 | $277,356 | $+294 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day before | pm | 0.5 | 13 | $277,209 | $+147 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day before | pm | 1.5 | 13 | $276,916 | $-147 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_end | day before | pm | 2.0 | 13 | $276,769 | $-294 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_end | day after | all | 0.0 | 83 | $282,817 | $+5,755 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day after | all | 0.5 | 83 | $279,940 | $+2,877 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day after | all | 1.5 | 83 | $274,185 | $-2,877 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day after | all | 2.0 | 83 | $271,308 | $-5,755 | 0.36 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day after | am | 0.0 | 67 | $281,604 | $+4,542 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day after | am | 0.5 | 67 | $279,333 | $+2,271 | 0.40 | +0.01 | Y | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day after | am | 1.5 | 67 | $274,792 | $-2,271 | 0.37 | -0.02 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day after | am | 2.0 | 67 | $272,521 | $-4,542 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | quarter_end | day after | pm | 0.0 | 16 | $278,276 | $+1,213 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day after | pm | 0.5 | 16 | $277,669 | $+607 | 0.39 | +0.00 | no | Y | Y | no | no |  |  |
| ENGUQ | quarter_end | day after | pm | 1.5 | 16 | $276,456 | $-607 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | quarter_end | day after | pm | 2.0 | 16 | $275,849 | $-1,213 | 0.39 | -0.00 | no | no | no | no | no |  |  |
| ENGUQ | fed_blackout | event day | all | 0.0 | 553 | $152,030 | $-125,033 | 0.22 | -0.17 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | event day | all | 0.5 | 553 | $214,546 | $-62,516 | 0.31 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | event day | all | 1.5 | 553 | $339,579 | $+62,516 | 0.38 | -0.01 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | event day | all | 2.0 | 553 | $402,095 | $+125,033 | 0.36 | -0.03 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | event day | am | 0.0 | 416 | $157,477 | $-119,585 | 0.22 | -0.17 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | event day | am | 0.5 | 416 | $217,270 | $-59,793 | 0.31 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | event day | am | 1.5 | 416 | $336,855 | $+59,793 | 0.39 | -0.00 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | event day | am | 2.0 | 416 | $396,648 | $+119,585 | 0.38 | -0.01 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | event day | pm | 0.0 | 137 | $271,615 | $-5,447 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | event day | pm | 0.5 | 137 | $274,339 | $-2,724 | 0.39 | +0.00 | Y | no | Y | no | no |  |  |
| ENGUQ | fed_blackout | event day | pm | 1.5 | 137 | $279,786 | $+2,724 | 0.36 | -0.03 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | event day | pm | 2.0 | 137 | $282,510 | $+5,447 | 0.34 | -0.05 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | day before | all | 0.0 | 524 | $144,548 | $-132,514 | 0.20 | -0.19 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day before | all | 0.5 | 524 | $210,805 | $-66,257 | 0.30 | -0.09 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day before | all | 1.5 | 524 | $343,320 | $+66,257 | 0.41 | +0.02 | Y | Y | Y | Y | no | 0.0505 | 101/2001 |
| ENGUQ | fed_blackout | day before | all | 2.0 | 524 | $409,577 | $+132,514 | 0.43 | +0.04 | Y | Y | Y | Y | no | 0.0505 | 101/2001 |
| ENGUQ | fed_blackout | day before | am | 0.0 | 410 | $152,996 | $-124,067 | 0.20 | -0.19 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day before | am | 0.5 | 410 | $215,029 | $-62,033 | 0.30 | -0.09 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day before | am | 1.5 | 410 | $339,096 | $+62,033 | 0.42 | +0.03 | Y | Y | Y | Y | no | 0.0505 | 101/2001 |
| ENGUQ | fed_blackout | day before | am | 2.0 | 410 | $401,129 | $+124,067 | 0.45 | +0.06 | Y | Y | Y | Y | no | 0.0505 | 101/2001 |
| ENGUQ | fed_blackout | day before | pm | 0.0 | 114 | $268,615 | $-8,447 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day before | pm | 0.5 | 114 | $272,839 | $-4,224 | 0.39 | -0.00 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day before | pm | 1.5 | 114 | $281,286 | $+4,224 | 0.38 | -0.01 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | day before | pm | 2.0 | 114 | $285,510 | $+8,447 | 0.37 | -0.03 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | day after | all | 0.0 | 560 | $218,592 | $-58,470 | 0.31 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day after | all | 0.5 | 560 | $247,827 | $-29,235 | 0.35 | -0.04 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day after | all | 1.5 | 560 | $306,298 | $+29,235 | 0.34 | -0.05 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | day after | all | 2.0 | 560 | $335,533 | $+58,470 | 0.31 | -0.08 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | day after | am | 0.0 | 410 | $223,953 | $-53,109 | 0.32 | -0.07 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day after | am | 0.5 | 410 | $250,508 | $-26,555 | 0.36 | -0.03 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day after | am | 1.5 | 410 | $303,617 | $+26,555 | 0.35 | -0.04 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | day after | am | 2.0 | 410 | $330,172 | $+53,109 | 0.32 | -0.07 | Y | Y | no | Y | no |  |  |
| ENGUQ | fed_blackout | day after | pm | 0.0 | 150 | $271,701 | $-5,361 | 0.32 | -0.08 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day after | pm | 0.5 | 150 | $274,382 | $-2,680 | 0.38 | -0.01 | Y | no | no | no | no |  |  |
| ENGUQ | fed_blackout | day after | pm | 1.5 | 150 | $279,743 | $+2,680 | 0.36 | -0.03 | Y | Y | no | no | no |  |  |
| ENGUQ | fed_blackout | day after | pm | 2.0 | 150 | $282,423 | $+5,361 | 0.33 | -0.06 | Y | Y | no | no | no |  |  |
