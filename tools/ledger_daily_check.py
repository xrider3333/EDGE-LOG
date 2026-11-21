"""tools/ledger_daily_check.py -- one layout + hover check for the shared LEDGER daily chart (ledgerDailyChart in index.html).

Owner bug report 11-21: the daily chart (REAL, NT8 PAPER, WEBULL PAPER all draw it) left wide empty margins on both sides of the plot,
drew its hover readout ON the bars / line, kept the readout up after the pointer left, and squeezed the DAY / TOTAL axis titles into
the tick numbers. home_render_probe.py, paper_render_probe.py and webull_board_probe.py each paste DAILY_CHECK_JS into their probe page,
call __lgDailyCheck(wrapEl, attr) on their own chart ('hmdaily' for REAL, 'lgdaily' for the paper boards) and hand the readout to
judge_daily(), which appends one plain-words fail per broken rule.

Rules judged:
  * the svg fills its box (>= 98 pct of the box's content width: no letterboxing by viewBox + a fixed CSS height)
  * each side gutter is only as wide as its widest tick label plus at most GUTTER_SLACK px (the titles have their own row above)
  * the plot itself is at least PLOT_MIN (laptop) / PLOT_MIN_NARROW (box under 420 px) of the box width
  * a synthetic mousemove over the middle of the plot shows the readout, and the readout box does not intersect the plot area
  * a synthetic mouseleave hides the readout and the crosshair; so does a synthetic touchend
  * no axis title box overlaps a tick label box, and no tick label / title is clipped by the svg edge
The JS has no backslashes, so it pastes into the probes' non-raw Python strings as is.
"""

GUTTER_SLACK = 12
PLOT_MIN = 0.80
PLOT_MIN_NARROW = 0.74

DAILY_CHECK_JS = r"""
function __lgDailyCheck(wrap,A){
  var o={ok:false};if(!wrap)return o;var sv=wrap.querySelector('svg[data-'+A+']');if(!sv)return o;o.ok=true;
  var wv=wrap.ownerDocument.defaultView;
  function R(e){var b=e.getBoundingClientRect();return {l:b.left,t:b.top,r:b.right,b:b.bottom,w:b.width,h:b.height};}
  function hit(a,b){return a.l<b.r-0.5&&b.l<a.r-0.5&&a.t<b.b-0.5&&b.t<a.b-0.5;}
  var cs=wv.getComputedStyle(wrap),wr=R(wrap),sr=R(sv);
  var cw=wr.w-(parseFloat(cs.paddingLeft)||0)-(parseFloat(cs.paddingRight)||0);
  o.boxW=Math.round(cw);o.svgW=Math.round(sr.w);
  var zl=sv.querySelector('[data-'+A+'-zero]'),cr=sv.querySelector('[data-'+A+'-cross]');
  if(!zl||!cr){o.parts=false;return o;}
  var vb=(sv.getAttribute('viewBox')||'').split(' ').map(Number),k=vb[3]?sr.h/vb[3]:1;
  var z=R(zl),plot={l:z.l,r:z.r,t:sr.t+(+cr.getAttribute('y1'))*k,b:sr.t+(+cr.getAttribute('y2'))*k};
  o.plotW=Math.round(plot.r-plot.l);o.plotH=Math.round(plot.b-plot.t);
  var L=[].slice.call(sv.querySelectorAll('[data-'+A+'-y]')),Rt=[].slice.call(sv.querySelectorAll('[data-'+A+'-yr]')),
      T=[].slice.call(sv.querySelectorAll('[data-'+A+'-ylab]'));
  var wmax=function(a){return Math.max.apply(null,[0].concat(a.map(function(e){return R(e).w;})));};
  o.titles=T.length;o.lGut=Math.round(plot.l-sr.l);o.rGut=Math.round(sr.r-plot.r);
  o.lSlack=Math.round(plot.l-sr.l-wmax(L));o.rSlack=Math.round(sr.r-plot.r-wmax(Rt));
  o.overlap=[];T.forEach(function(t){L.concat(Rt).forEach(function(x){if(hit(R(t),R(x)))o.overlap.push(t.textContent+' / '+x.textContent);});});
  o.clipped=[];L.concat(Rt).concat(T).forEach(function(e){var b=R(e);if(b.l<sr.l-0.5||b.r>sr.r+0.5||b.t<sr.t-0.5||b.b>sr.b+0.5)o.clipped.push(e.textContent);});
  var tip=wrap.querySelector('[data-'+A+'-tip]');if(!tip){o.tip=false;return o;}o.tip=true;
  var vis=function(){return wv.getComputedStyle(tip).display!=='none'&&!tip.hidden;};
  var mv=function(){sv.dispatchEvent(new wv.MouseEvent('mousemove',{clientX:(plot.l+plot.r)/2,clientY:(plot.t+plot.b)/2,bubbles:true}));};
  mv();o.tipShown=vis();var tr=R(tip);o.tipBox=[Math.round(tr.l),Math.round(tr.t),Math.round(tr.w),Math.round(tr.h)];
  o.tipOverPlot=hit(tr,plot);o.crossShown=cr.getAttribute('visibility');
  sv.dispatchEvent(new wv.MouseEvent('mouseleave',{clientX:0,clientY:0}));
  o.tipAfterLeave=vis();o.crossAfterLeave=cr.getAttribute('visibility');
  mv();sv.dispatchEvent(new wv.Event('touchend'));o.tipAfterTouch=vis();o.crossAfterTouch=cr.getAttribute('visibility');
  return o;
}
"""


def judge_daily(tag, m, fails):
    """Append a fail per broken rule; m is __lgDailyCheck's readout (None or ok:false = no daily chart, judged elsewhere)."""
    if not m or not m.get('ok'):
        return
    if m.get('parts') is False:
        fails.append('%s: the daily chart has no $0 line or crosshair to measure the plot by' % tag)
        return
    bw, sw, pw = m.get('boxW') or 0, m.get('svgW') or 0, m.get('plotW') or 0
    if bw and sw < 0.98 * bw:
        fails.append('%s: the daily chart svg is %s px wide in a %s px box - it does not fill its card' % (tag, sw, bw))
    for side, key in (('left', 'lSlack'), ('right', 'rSlack')):
        if (m.get(key) or 0) > GUTTER_SLACK:
            fails.append('%s: the daily chart %s gutter is %s px wider than its widest tick label (limit %s)'
                         % (tag, side, m.get(key), GUTTER_SLACK))
    lo = PLOT_MIN if bw >= 420 else PLOT_MIN_NARROW
    if bw and pw < lo * bw:
        fails.append('%s: the daily chart plot is %s px of a %s px box (%.0f pct, want %.0f pct or more)' % (tag, pw, bw, 100.0 * pw / bw, 100 * lo))
    if m.get('overlap'):
        fails.append('%s: a daily chart axis title overlaps a tick label: %s' % (tag, '; '.join(m['overlap'][:4])))
    if m.get('clipped'):
        fails.append('%s: daily chart labels are clipped by the svg edge: %s' % (tag, ', '.join(m['clipped'][:4])))
    if not m.get('titles'):
        fails.append('%s: the daily chart has no DAY / TOTAL axis titles' % tag)
    if not m.get('tip'):
        fails.append('%s: the daily chart has no hover readout' % tag)
        return
    if not m.get('tipShown') or m.get('crossShown') != 'visible':
        fails.append('%s: a mousemove over the daily chart did not show the readout (%s) and crosshair (%s)' % (tag, m.get('tipShown'), m.get('crossShown')))
    if m.get('tipOverPlot'):
        fails.append('%s: the daily chart hover readout %s sits on the plot area - it must not cover data' % (tag, m.get('tipBox')))
    if m.get('tipAfterLeave') or m.get('crossAfterLeave') != 'hidden':
        fails.append('%s: the daily chart readout / crosshair stay up after mouseleave (readout %s, crosshair %s)'
                     % (tag, m.get('tipAfterLeave'), m.get('crossAfterLeave')))
    if m.get('tipAfterTouch') or m.get('crossAfterTouch') != 'hidden':
        fails.append('%s: the daily chart readout / crosshair stay up after touchend (readout %s, crosshair %s)'
                     % (tag, m.get('tipAfterTouch'), m.get('crossAfterTouch')))


def summary(m):
    if not m or not m.get('ok'):
        return 'none'
    return 'box %s svg %s plot %s (%s/%s gutters)' % (m.get('boxW'), m.get('svgW'), m.get('plotW'), m.get('lGut'), m.get('rGut'))
