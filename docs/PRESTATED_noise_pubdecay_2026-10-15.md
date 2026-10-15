# NOISE PUBLICATION-DECAY READ (pre-stated 2026-10-15, before any number; NOISE lane, MANAGER #100 / owner 10-15)

**Status:** a report, not a test. Nothing live or in the book can change from it. It sets the haircut NOISE's forward reads
should expect.

## Papers

- **The source:** Zarattini, Aziz & Barbon, "Beat the Market" (SSRN 4824172).
  - Posted in May 2024 (CXO Advisory dates it to that month).
  - It was widely read afterwards: 4th place at the Quantpedia Awards 2025.
- **The haircuts, from the reading shelf:**

  | Shelf no. | Paper | Expected post-publication level |
  |---|---|---|
  | 17 | McLean & Pontiff (2016) | about 0.42 of pre (returns fall about 58% after publication) |
  | 19 | Falck, Rej & Thesmar (2022) | about 0.5 |

## Question

Did NOISE's edge per trade fall after the paper made its mechanism public?

## Object

- **Unit object (scale-free):** the #304 core trades.
  - These are the entries and exits #382 and #422 share; `tools/noise_halves_read.py`'s object.
  - NQ 5m RTH no-adjust master, cost 0.533.
  - Each trade's P&L is in BAND UNITS (signed move net of cost, over sigma x entry), so 2010 and 2026 price levels compare.
- **Dollar object, for the house's four numbers:** the #422 crown (CT304H 20 / 1.15 / 1.75).
  - House cost 0.533, re-costed per contract at real 0.7825 as a second line.
  - Four numbers per stretch.

## Stretches (by signal date)

| Stretch | Dates | Note |
|---|---|---|
| PRE | 2016-07-01 .. 2024-05-31 | The WF era up to the posting |
| POST | 2024-06-01 .. the master's last bar | Mixes NOISE's own design window up to 2025-07-15, the spent lockbox and the forward |
| POST-DESIGN | 2025-07-16 .. last bar | Lockbox (spent) + forward; a report |
| Sensitivity | POST from 2024-05-01 | Printed beside the main line |

## Statistic and the reading rule (fixed now)

**Statistic:**
- R = mean band units a trade, POST / PRE.
- A 90% CI from a month-block bootstrap: 2,000 draws, months resampled within each stretch, seed 20261015.

**Power line, printed FIRST:**
- SE of (POST mean - PRE mean).
- The drop McLean-Pontiff predicts: 0.58 x the PRE mean.
- It is detectable only if that drop >= 2.5 x SE. If not, the read says "underpowered" whatever R is.

**Reading:**

| R's 90% CI | Reading |
|---|---|
| Contains 1.0 and excludes 0.42 | NO DETECTABLE DECAY. NOISE runs at its pre-publication edge; no haircut beyond the house's usual one. |
| Excludes 1.0 and contains 0.42 | DECAY CONSISTENT WITH McLEAN-PONTIFF. Forward reads should expect about 0.4-0.5 of the WF edge; tell the harm monitor's owner. |
| Contains both | CAN'T TELL (underpowered). Report R and the CI only. |
| Excludes both | Report as printed: a partial decay or an improvement. |

**Context lines, never the verdict:**
- Band units a trade by calendar year, 2016 .. 2026.
- The held-to-close share by stretch (the trend-day catch rate).

## Not done

- No parameter is refit.
- The lockbox and forward appear only inside POST and POST-DESIGN, as a report.
- The SSRN page itself was not read (bot check). The posting month comes from CXO Advisory's May 2024 write-up.
