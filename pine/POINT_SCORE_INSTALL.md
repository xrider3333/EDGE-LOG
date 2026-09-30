# EDGELOG Point Score - install (TradingView)

This adds your 9-point score to a TradingView chart. It follows `docs/POINT_SCORE_SPEC.md` and is built for a **1-minute** chart.

## Install (3 steps)

1. Open a **1-minute** chart of NQ1! (or MNQ1! / ES1!) in TradingView. Open the **Pine Editor** at the bottom, choose **Open > New indicator**, delete the template text, and paste the whole of `POINT_SCORE_1_0.pine`. Click **Save**, name it `EDGELOG Point Score`, then click **Add to chart**.
2. Open the indicator's **Settings**. Pick the **Market** (Futures = "today" starts at 09:30, Stocks = 04:00), and set the **Label threshold** (default 7) and **Alert threshold** (default 8). If TradingView shows an error about the 10-second data, your plan has no seconds timeframes: untick **Use 10-second data** (that one point then shows NA).
3. Optional alert: click **Create Alert**, set Condition to `EDGELOG Point Score`, choose **Any alert() function call**, and set it to **Once per bar close**. The message carries the symbol, the bar time, the side, the score (like 8/9) and which points hit.

## Parity export (only needed once, to check TradingView against EDGE LOG)

After a few regular sessions have printed on the chart (5 to 10 is plenty, and avoid the week of a futures roll), open the chart menu, choose **Export chart data**, and save the CSV into `C:\EdgeLog\point_score\tv_exports\`. Then tell MANAGER; Claude runs the comparison against EDGE LOG's own numbers. Claude never logs in to TradingView.

## What the table shows

- **Top right, for the last closed bar:** its time, one row per point with a tick, a cross or NA in a Long and a Short column (the side the chart is following is starred), and a Ref column with the EMA or level the close was compared with, or the body and volume it had to beat.
- **Total and trend:** the total for each side as "8/9" (or "7/8 (1 NA)" when a point could not be scored; NA is never counted as a miss), and the daily trend point on its own row, never added into the 9.
- **Bars loaded:** how many bars each timeframe has. An EMA point stays NA until its timeframe has 600 bars, and the 30-minute one needs about 13 trading days of history, so it may show "warming up" on a short chart.
