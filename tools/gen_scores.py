"""Generate the TRADE_SCORES JS block for EDGE LOG: authored factor scores + baked OHLC bars."""
import pandas as pd, json, os

SCR = os.path.dirname(os.path.abspath(__file__))

# sym, date, interval, csv, entryHHMM, exitHHMM, entry, exit, qty, breakout-candle HHMM, stop
TRADES = [
 ('EHGO','2026-07-23','1m','EHGO_1m.csv','09:32','09:33',3.95 ,4.515,100,'09:31',3.780),
 ('XRX' ,'2026-07-30','1m','XRX_1m.csv' ,'09:31','09:32',3.565,3.32 , 50,'09:30',3.425),
 ('OFAL','2026-08-12','1m','ofal_1m.csv','08:41','09:46',2.93 ,3.35 , 20,'08:40',2.100),
 ('LABT','2026-07-22','1m','LABT_1m.csv','08:08','08:11',5.11 ,5.23 , 30,'08:07',4.150),
 ('AMC' ,'2026-07-20','1m','AMC_2026-07-20_1m.csv' ,'07:11','07:13',2.239,2.25 ,  1,'07:10',2.190),
 ('GMM' ,'2026-07-10','5m','GMM_2026-07-10_5m.csv' ,'08:41','08:43',5.61 ,5.77 , 20,'08:35',4.890),
 ('SUGP','2026-07-07','5m','SUGP_2026-07-07_5m.csv','08:02','08:08',1.22 ,1.13 , 20,'07:55',1.080),
 ('LGCL','2026-07-02','5m','LGCL_2026-07-02_5m.csv','09:05','09:08',3.02 ,2.35 ,  1,'09:00',1.750),
 ('LHAI','2026-07-01','5m','LHAI_2026-07-01_5m.csv','08:38','08:38',1.48 ,1.60 ,  1,'08:30',1.220),
 ('CELZ','2026-06-30','5m','CELZ_2026-06-30_5m.csv','08:55','08:57',1.84 ,1.89 ,  3,'08:50',1.180),
 ('TNMG','2026-06-29','5m','TNMG_2026-06-29_5m.csv','08:16','08:17',1.17 ,1.18 ,  1,'08:10',0.909),
]

# authored: overall, summary, setup factors, exec factors  (label, weight, score, note)
A = {}
A['EHGO'] = (82,"The model trade. Bought a pullback BELOW the breakout candle close, sized up on the best catalyst, and sold into the spike. EHGO closed 2.71 — the exit was the trade.",
 [('Catalyst / RVOL',15,15,'+124% gap on a 1.76 prior close, 42M shares in the opening minute'),
  ('Front-side structure',20,16,'Genuine first expansion off a premarket base'),
  ('Entry location',20,18,'Filled 3.95 BELOW the 4.04 breakout close. Bought the dip, not the spike'),
  ('Risk definition',15,12,'Stop 3.78 = breakout candle low, 4.3% away'),
  ('R:R to a real level',10,8,'0.17 risk against a multi-point extension'),
  ('Liquidity',10,9,'Deep two-sided book'),
  ('Time of day',10,6,'09:32, two minutes into the open')],
 [('Entry timing',25,23,'No chase at all — the best fill in the whole log'),
  ('Risk control / MAE',25,20,'MAE 3.88 used only 41% of planned risk'),
  ('Exit vs MFE',25,17,'Sold 4.515 into a 4.97 spike = 55% capture, and EHGO closed 2.71'),
  ('Sizing',15,12,'100 sh / $395 = 13% of account. Biggest size on the best setup — correct'),
  ('Plan adherence',10,9,'Entry rule, stop and exit all followed')])

A['XRX'] = (61,"Entry was disciplined — he paid the breakout candle close almost exactly. The loss came from exiting a candle LATE, taking 75% more than the planned risk.",
 [('Catalyst / RVOL',15,13,'+35% gap, 6.0M shares in the opening minute'),
  ('Front-side structure',20,8,'Bought the opening-drive high after a 0.355-range bar'),
  ('Entry location',20,15,'3.565 against a 3.555 breakout close — his rule’s ideal fill'),
  ('Risk definition',15,12,'Stop 3.425 = breakout low, only 3.9% away. Tight and structural'),
  ('R:R to a real level',10,6,'0.14 risk, ~0.22 to the 3.78 high = 1.5:1'),
  ('Liquidity',10,9,'Large-cap, tight spread'),
  ('Time of day',10,6,'09:31 — first minute after the bell')],
 [('Entry timing',25,20,'Bought his level, no chase'),
  ('Risk control / MAE',25,8,'Stop 3.425 broke at 09:31 (low 3.380). He exited 3.32 — 0.105 BEYOND the stop'),
  ('Exit vs MFE',25,10,'Sold into the flush; XRX closed 3.42, above the exit'),
  ('Sizing',15,10,'50 sh / $178 = 5.9% of account'),
  ('Plan adherence',10,6,'Honoured the idea of stopping out, but a candle late and at a worse price')])

A['OFAL'] = (51,"Perfect stock, correct stop rule, chased fill. Paying 2.93 instead of the 2.65 his own rule pointed at gave away 34% of the risk budget and turned a 1.27R trade into 0.51R.",
 [('Catalyst / RVOL',15,15,'+256% gap, 147M shares, ~$375M traded. The ticker of the day'),
  ('Front-side structure',20,12,'Still front-side at 08:41, but bought the vertical rather than a base'),
  ('Entry location',20,4,'Breakout candle closed 2.65; paid 2.93 = 44% of the candle range above it'),
  ('Risk definition',15,7,'Stop 2.10 = breakout candle low. Correct rule, but 28% wide at this fill'),
  ('R:R to a real level',10,3,'0.83 risk for 0.42 reward = 0.51:1'),
  ('Liquidity',10,7,'$375M traded, but ~22 LULD halts between 09:30 and 12:30'),
  ('Time of day',10,3,'08:41 premarket — thin book, the open still ahead')],
 [('Entry timing',25,5,'Entry bar ran 2.65 to 3.50 then closed 2.88. Filled inside the wick'),
  ('Risk control / MAE',25,7,'Stop never hit (MAE used 58% of risk) but the geometry was sub-1R by construction'),
  ('Exit vs MFE',25,21,'Out 3.35 for 74% of MFE-to-exit. OFAL closed 1.34 — a genuinely good exit'),
  ('Sizing',15,8,'20 sh / $58.60 = 1.9% of account on the day’s best catalyst'),
  ('Plan adherence',10,9,'Stop honoured, target 3.35 hit exactly')])

A['LABT'] = (38,"The worst fill in the log: paid 5.11 when the breakout candle closed 4.54 — a full candle-range above it. Held through the stop zone, then took $3.60 out of a move that ran to 7.72.",
 [('Catalyst / RVOL',15,15,'+175% gap off a 1.86 close'),
  ('Front-side structure',20,10,'Third vertical extension in three minutes, not a first break'),
  ('Entry location',20,3,'Breakout close 4.54, filled 5.11 = 112% of the candle range above it'),
  ('Risk definition',15,4,'Stop 4.15 = 0.96 risk (19%) on a bar that had just printed a 6.98 wick'),
  ('R:R to a real level',10,3,'No overhead reference — blue sky after a 3.7x premarket run'),
  ('Liquidity',10,6,'Premarket only, thin book'),
  ('Time of day',10,3,'08:08, mid-vertical')],
 [('Entry timing',25,4,'Chased the extension bar by more than its own range'),
  ('Risk control / MAE',25,8,'MAE 4.44 ate 70% of risk inside one minute'),
  ('Exit vs MFE',25,6,'+0.12 captured out of an 0.83 in-hold move; LABT hit 7.72 nineteen minutes later'),
  ('Sizing',15,9,'30 sh / $153 = 5% of account'),
  ('Plan adherence',10,4,'Exit was neither the stop nor a target — a discretionary bail')])

A['AMC'] = (41,"Not a setup at all — a 1-share poke into premarket chop with no expansion bar to trade off. AMC then closed at 2.46, 9% above the exit.",
 [('Catalyst / RVOL',15,7,'+15% gap on a mega-liquid name, but no volume event at the entry moment'),
  ('Front-side structure',20,6,'Mid-range chop between 2.20 and 2.29 for fifteen minutes before the fill'),
  ('Entry location',20,7,'Bought a red bar inside the range. Not a chase, but not a level either'),
  ('Risk definition',15,3,'No expansion candle exists, so the stop rule has nothing to anchor to'),
  ('R:R to a real level',10,5,'Range top 2.32 was 0.08 away — thin reward for a range trade'),
  ('Liquidity',10,10,'The most liquid name he has traded'),
  ('Time of day',10,4,'07:11 — deep premarket, hours before the open')],
 [('Entry timing',25,10,'No chase, but no trigger either'),
  ('Risk control / MAE',25,15,'MAE 2.20 = 4 cents. Never in trouble'),
  ('Exit vs MFE',25,6,'+0.011 out of a day that ran to 2.48 and closed 2.46'),
  ('Sizing',15,4,'1 share / $2.24 = 0.07% of account. No size is no trade'),
  ('Plan adherence',10,4,'No identifiable plan to adhere to')])

A['GMM'] = (53,"Chased 65% of the breakout candle range into a +203% gapper, then cut for 0.16 when the very next bar still carried 0.79 more. GMM printed 6.57 two minutes after the exit.",
 [('Catalyst / RVOL',15,15,'+203% gap off a 1.85 close'),
  ('Front-side structure',20,14,'Clean first expansion after a 20-minute base'),
  ('Entry location',20,6,'5.61 = 65% of the breakout candle range above its 5.31 close'),
  ('Risk definition',15,7,'Breakout candle low 4.89 gives a 0.72 stop, 13% away'),
  ('R:R to a real level',10,3,'0.72 risk for the 0.16 he took = 0.22R'),
  ('Liquidity',10,7,'Premarket but active'),
  ('Time of day',10,4,'08:41 premarket')],
 [('Entry timing',25,14,'Early in the bar rather than after it — better than OFAL, worse than the rule'),
  ('Risk control / MAE',25,14,'Never pressed; the trade went his way immediately'),
  ('Exit vs MFE',25,8,'Kept 0.16 of the 0.79 still in the bar. GMM printed 6.57 two minutes later'),
  ('Sizing',15,9,'20 sh / $112 = 3.7% of account'),
  ('Plan adherence',10,7,'Consistent with his rule, just early and short')])

A['SUGP'] = (52,"The first trade where the management beat the idea. He bought the high tick of the bar (+55% chase) but cut it fast — SUGP closed at 0.751, so the exit saved roughly nine dollars.",
 [('Catalyst / RVOL',15,12,'+48% gap off a 0.825 close'),
  ('Front-side structure',20,8,'Fifth push of a premarket grind, not a first break'),
  ('Entry location',20,4,'1.22 was 55% of the breakout candle range above its 1.16 close — the high tick'.replace('X','X')),
  ('Risk definition',15,10,'Stop 1.08 = prior bar low, 0.14 risk'),
  ('R:R to a real level',10,3,'No overhead level; the 1.23 high printed one minute later was the top'),
  ('Liquidity',10,5,'Thin premarket book'),
  ('Time of day',10,4,'08:02 premarket')],
 [('Entry timing',25,6,'Filled at the extreme of the bar'),
  ('Risk control / MAE',25,18,'Exited ABOVE the stop. MAE used 64% of planned risk'),
  ('Exit vs MFE',25,18,'Cut at 1.13 before the collapse — SUGP closed 0.751'),
  ('Sizing',15,9,'20 sh / $24 = 0.8% of account'),
  ('Plan adherence',10,8,'Recognised it was wrong and acted')])

A['LGCL'] = (35,"Bought three minutes after a candle that doubled the stock. There was no structure left to trade against — the only real stop sat 42% away.",
 [('Catalyst / RVOL',15,13,'+63% gap, then an 84% single-bar vertical'),
  ('Front-side structure',20,4,'Entered at maximum extension, immediately after the doubling candle'),
  ('Entry location',20,6,'Technically below the vertical bar close, but the level itself is meaningless'),
  ('Risk definition',15,2,'The only structural stop is 1.75 — 42% below the fill'),
  ('R:R to a real level',10,2,'Nothing overhead, nothing underneath'),
  ('Liquidity',10,4,'Thin premarket, and the bar had a 1.53 range'),
  ('Time of day',10,5,'09:05, twenty-five minutes before the open')],
 [('Entry timing',25,6,'Chasing a vertical is the entry, regardless of the tick'),
  ('Risk control / MAE',25,6,'Down 22% within three minutes'),
  ('Exit vs MFE',25,12,'Bailed at 2.35; LGCL traded 1.10 five minutes later. The exit was right'),
  ('Sizing',15,6,'1 share / $3.02 — a test'),
  ('Plan adherence',10,4,'No stop was reachable, so there was no plan to hold to')])

A['LHAI'] = (42,"Right stock, mid-bar fill, and then out for 0.12 on a name that ran to 3.11 and closed 2.56. Everything after the entry was left on the table.",
 [('Catalyst / RVOL',15,14,'+124% gap off a 0.66 close'),
  ('Front-side structure',20,12,'Second expansion in a building premarket trend'),
  ('Entry location',20,4,'1.48 = 96% of the breakout candle range above its 1.27 close — nearly a full range'),
  ('Risk definition',15,6,'Stop 1.19 = 0.29 risk, 20% away'),
  ('R:R to a real level',10,4,'Wide stop against no defined target'),
  ('Liquidity',10,4,'Thin premarket'),
  ('Time of day',10,4,'08:38 premarket')],
 [('Entry timing',25,10,'Mid-bar rather than after the close'),
  ('Risk control / MAE',25,15,'Never under water'),
  ('Exit vs MFE',25,4,'+0.12 taken. LHAI printed 3.11 and closed 2.56 — over 100% left behind'),
  ('Sizing',15,4,'1 share / $1.48'),
  ('Plan adherence',10,5,'Exit had no rule behind it')])

A['CELZ'] = (39,"A 66% chase into the expansion bar, then out for five cents. CELZ ran to 4.72 the same session — the worst capture in the log at 1.7%.",
 [('Catalyst / RVOL',15,14,'+113% gap off a 0.864 close'),
  ('Front-side structure',20,13,'Live premarket trend with successive higher expansions'),
  ('Entry location',20,4,'1.84 = 66% of the breakout candle range above its 1.57 close'),
  ('Risk definition',15,4,'Stop 1.18 = 0.66 risk, 36% away'),
  ('R:R to a real level',10,3,'Risking 0.66 for a five-cent exit'),
  ('Liquidity',10,4,'Thin premarket'),
  ('Time of day',10,4,'08:55 premarket')],
 [('Entry timing',25,6,'Chased the bar'),
  ('Risk control / MAE',25,14,'MAE 1.53 stayed above the stop'),
  ('Exit vs MFE',25,3,'+0.05 of a move that reached 4.72. 1.7% capture — the worst here'),
  ('Sizing',15,5,'3 shares / $5.52'),
  ('Plan adherence',10,5,'No target, no stop, discretionary scratch')])

A['TNMG'] = (46,"A 35% chase on the fourth push of a +140% gapper, scratched flat one minute later. TNMG closed at 0.976 — flat was the right answer.",
 [('Catalyst / RVOL',15,13,'+140% gap off a 0.488 close'),
  ('Front-side structure',20,9,'Fourth push, already extended when he bought'),
  ('Entry location',20,6,'1.17 = 35% of the breakout candle range above its 1.08 close'),
  ('Risk definition',15,6,'Stop 0.909 = 0.26 risk, 22% away'),
  ('R:R to a real level',10,3,'Wide stop, no target'),
  ('Liquidity',10,4,'Thin premarket'),
  ('Time of day',10,4,'08:16 premarket')],
 [('Entry timing',25,8,'Chased, but modestly'),
  ('Risk control / MAE',25,16,'Never pressed'),
  ('Exit vs MFE',25,12,'Scratched before the fade — TNMG closed 0.976, 17% below the fill'),
  ('Sizing',15,4,'1 share / $1.17'),
  ('Plan adherence',10,6,'Scratch was a reasonable read')])


def esc(s):
    return s.replace('\\', '\\\\').replace("'", "\\'")


def main():
    out = []
    for sym, dt, iv, csv, i0, i1, E, X, Q, bo, stop in TRADES:
        d = pd.read_csv(os.path.join(SCR, csv), index_col=0, parse_dates=True)
        day = d[d.index.date == pd.Timestamp(dt).date()]
        step = 1 if iv == '1m' else 5
        t0 = pd.Timestamp(dt + ' ' + i0)
        # window: 10 bars before the breakout candle through 14 bars after the exit
        lo = (pd.Timestamp(dt + ' ' + bo) - pd.Timedelta(minutes=10 * step)).strftime('%H:%M')
        hi = (pd.Timestamp(dt + ' ' + i1) + pd.Timedelta(minutes=14 * step)).strftime('%H:%M')
        w = day.between_time(lo, hi)
        bars = [[k.strftime('%H:%M'), round(float(r.Open), 4), round(float(r.High), 4),
                 round(float(r.Low), 4), round(float(r.Close), 4)] for k, r in w.iterrows()]
        boRow = day.between_time(bo, bo)
        boClose = round(float(boRow.Close.iloc[0]), 4)
        boRange = round(float(boRow.High.iloc[0] - boRow.Low.iloc[0]), 4)
        chase = round((E - boClose) / boRange * 100, 1) if boRange else None
        risk = round(E - stop, 4)
        reward = round(X - E, 4)
        R = round(reward / risk, 2) if risk else None
        hold = day.between_time(i0, i1)
        mae = float(hold.Low.min()) if len(hold) else E
        mfe = float(hold.High.max()) if len(hold) else E
        maePct = round((E - mae) / risk * 100) if risk else None
        mfeCap = round(reward / (mfe - E) * 100) if mfe > E else None
        rth = day.between_time('09:30', '16:00')
        dayClose = round(float(rth.Close.iloc[-1]), 4) if len(rth) else None
        overall, summ, setF, exeF = A[sym]
        setT = sum(f[2] for f in setF)
        exeT = sum(f[2] for f in exeF)
        fj = lambda F: '[' + ','.join("['%s',%d,%d,'%s']" % (esc(a), b, c, esc(d_)) for a, b, c, d_ in F) + ']'
        out.append(
            "'%s|%s':{overall:%d,tf:'%s',summary:'%s',\n"
            "  stats:{bo:'%s',boClose:%s,boRange:%s,chase:%s,stop:%s,risk:%s,reward:%s,R:%s,maePct:%s,mfeCap:%s,dayClose:%s},\n"
            "  bars:%s,mark:{entry:%s,exit:%s,stop:%s,boT:'%s',inT:'%s',outT:'%s'},\n"
            "  setup:{total:%d,f:%s},\n  exec:{total:%d,f:%s}},"
            % (dt, sym, overall, iv, esc(summ), bo, boClose, boRange,
               'null' if chase is None else chase, stop, risk, reward,
               'null' if R is None else R, 'null' if maePct is None else maePct,
               'null' if mfeCap is None else mfeCap, 'null' if dayClose is None else dayClose,
               json.dumps(bars, separators=(',', ':')), E, X, stop, bo, i0, i1,
               setT, fj(setF), exeT, fj(exeF)))
    print('\n'.join(out))


main()
