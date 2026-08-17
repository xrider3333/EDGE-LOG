#!/usr/bin/env python3
"""
tools/matrix_scope_audit.py -- SAMPLE-scope audit of the 1E MATRIX (2B CONFIGS card).

WHY THIS EXISTS
    The owner's standing worry: a number rendered under a scoped label ("· LB")
    that was actually measured on a wider window. preflight_boot.py only proves
    the app BOOTS; this gate renders the four 1E tabs (RAW / GATE / TILT /
    HYBRID one-lot) against a REAL run doc, for every SAMPLE tick combo, and
    compares every displayed cell against an INDEPENDENT Python recomputation
    from the raw run-doc data for exactly the ticked stretches.

METHOD (the established one)
    selectionTableHtml + gvParts (and the helper shelf they close over) are
    lifted VERBATIM out of index.html into a headless-Chrome page next to the
    run doc, rendered once per tick combo, and the resulting DOM is flattened
    to {tab: {group, row, cells[]}} JSON. The Python side recomputes each cell
    from the doc and diffs. It also checks the RANK BY orderings, the crown
    column, the scatter points, and that scope tags in section headers wear the
    funnel period colours (IS var(--text4), WF #60a5fa, LB #a78bfa).

USAGE
    python tools/matrix_scope_audit.py path\to\run_doc.json [--keep] [--dump out.json]

Exit codes: 0 = PASS, 1 = FAIL (mismatch found), 2 = INCONCLUSIVE.
"""
import argparse
import html as _html
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preflight_boot import find_chrome  # noqa: E402

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, 'index.html')
HARNESS = os.path.join(REPO, 'tools', '_mtx_audit_probe.html')

COMBOS = ['is', 'wf', 'lb', 'is,wf', 'wf,lb', 'is,lb', 'is,wf,lb']


def read_index():
    with open(INDEX, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def seg(src, start_marker, end_marker, include_end=False):
    a = src.index(start_marker)
    b = src.index(end_marker, a)
    if include_end:
        b += len(end_marker)
    return src[a:b]


def lift_blocks(src):
    out = []
    # single-line global helpers
    for name in ('fmtUsd', 'fmtAx'):
        m = re.search(r'^[ \t]*const %s=.*$' % name, src, re.M)
        out.append(m.group(0))
    for name in ('_infoIc', '_pdChip', '_TILT_SCHEME_NM', '_TILT_SCHEME_AB'):
        m = re.search(r'^[ \t]*const %s=.*$' % name, src, re.M)
        out.append(m.group(0))
    # the control/matrix helper shelf, _scopeTag included, through _gateColor
    out.append(seg(src, '    const _mtxEmphBd=', '    const selectionTableHtml='))
    # selectionTableHtml, whole const
    out.append(seg(src, '    const selectionTableHtml=',
                   "scatterPts:_scatterPtsRaw};};", include_end=True))
    m = re.search(r'^[ \t]*const _pp=.*$', src, re.M)
    out.append(m.group(0))
    m = re.search(r'^[ \t]*const MTX_HYB2=.*$', src, re.M)
    out.append(m.group(0))
    # gvParts, whole const (ends right before gvTableHtml)
    out.append(seg(src, '    const gvParts=', '    const gvTableHtml='))
    return '\n'.join(out)


HARNESS_TMPL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>mtx audit probe</title></head>
<body style="margin:0;background:#0a0a0a">
<div id="host"></div><pre id="o"></pre>
<script>
(function(){
  var out={};
  try{
    var APREF={g2rank:'rec',g2heat:0};
    var savePref=function(k,v){APREF[k]=v;};
    var renderApp=function(){};
__BLOCK__
    var D=__DOC__;
    var host=document.getElementById('host');
    var flat=function(html){
      host.innerHTML=html;
      var res={heads:[],rows:[],groups:[]};
      var thead=host.querySelector('thead');
      if(thead)res.heads=[].slice.call(thead.querySelectorAll('th')).slice(1)
        .map(function(th){return th.textContent.replace(/\\s+/g,' ').trim();});
      var cur=null;
      [].slice.call(host.querySelectorAll('tbody tr')).forEach(function(tr){
        var tds=[].slice.call(tr.children);
        if(tds.length===1&&tds[0].getAttribute('colspan')){
          cur=tds[0].textContent.replace(/\\s+/g,' ').trim();
          res.groups.push({name:cur,html:tds[0].innerHTML});
          return;}
        if(!tds.length)return;
        res.rows.push({g:cur,
          lbl:tds[0].textContent.replace(/\\s+/g,' ').trim(),
          lblHtml:tds[0].innerHTML,
          cells:tds.slice(1).map(function(td){return td.textContent.replace(/\\s+/g,' ').trim();}),
          titles:tds.slice(1).map(function(td){var s=td.querySelector('[title]');return s?s.getAttribute('title'):null;})});
      });
      return res;};
    out={ok:true,combos:{}};
    __COMBOS__.forEach(function(combo){
      APREF.g2samp=combo;
      var one={};
      var selP=selectionTableHtml(D.selection,D.multiplier,null,D.validate);
      if(selP){one.raw=flat(selP.table);one.rawScatter=selP.scatterPts;}
      var gvD=D.gate_validate||(D.validate&&D.validate.gate_bakeoff);
      var gvP=gvD?gvParts(gvD,'S',D.multiplier):null;
      if(gvP){
        one.gate=flat(gvP.matrix);
        one.tilt=gvP.tilts?flat(gvP.tilts):null;
        one.hyb=gvP.hyb?flat(gvP.hyb):null;
        one.gvScatter=gvP.scatterPts;
      }
      out.combos[combo]=one;
    });
    // RANK BY orderings, checked on the full tick and on LB-only
    out.rank={};
    ['is,wf,lb','lb'].forEach(function(combo){
      APREF.g2samp=combo;out.rank[combo]={};
      ['rec','pnl','floor'].forEach(function(rk){
        APREF.g2rank=rk;
        var r={};
        var selP=selectionTableHtml(D.selection,D.multiplier,null,D.validate);
        if(selP)r.raw=flat(selP.table).heads;
        var gvD=D.gate_validate||(D.validate&&D.validate.gate_bakeoff);
        var gvP=gvD?gvParts(gvD,'S',D.multiplier):null;
        if(gvP){r.gate=flat(gvP.matrix).heads;r.tilt=gvP.tilts?flat(gvP.tilts).heads:null;
                r.hyb=gvP.hyb?flat(gvP.hyb).heads:null;}
        out.rank[combo][rk]=r;});
      APREF.g2rank='rec';});
  }catch(e){ out={ok:false,err:String(e&&e.stack||e)}; }
  document.getElementById('o').textContent='MTXPROBE:'+JSON.stringify(out)+':ENDPROBE';
})();
</script>
</body></html>
"""


def build_harness(doc):
    src = read_index()
    block = lift_blocks(src)
    html = (HARNESS_TMPL
            .replace('__BLOCK__', block)
            .replace('__DOC__', json.dumps(doc))
            .replace('__COMBOS__', json.dumps(COMBOS)))
    with open(HARNESS, 'w', encoding='utf-8') as f:
        f.write(html)


def run_probe(chrome):
    args = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
            '--virtual-time-budget=20000', '--dump-dom',
            'file:///' + HARNESS.replace('\\', '/')]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=180,
                           encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return None, 'chrome timed out'
    except OSError as e:
        return None, 'could not launch chrome: %s' % e
    m = re.search(r'MTXPROBE:(.*?):ENDPROBE', p.stdout or '', re.S)
    if not m:
        return None, 'no MTXPROBE marker in chrome output'
    try:
        return json.loads(_html.unescape(m.group(1))), None
    except json.JSONDecodeError as e:
        return None, 'probe JSON did not parse: %s' % e


# ---------------------------------------------------------------------------
# independent recomputation (mirrors the INTENDED semantics, from the doc only)
# ---------------------------------------------------------------------------

def dd_slice(arr, a, b):
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    a = max(0, min(len(arr) - 1, a)); b = max(a, min(len(arr) - 1, b))
    peak = arr[a] or 0; dd = 0.0
    for i in range(a, b + 1):
        v = arr[i] or 0
        if v > peak:
            peak = v
        if peak - v > dd:
            dd = peak - v
    return dd


def dd_from_cum(arr):
    if not isinstance(arr, list) or not arr:
        return None
    peak = 0.0; dd = 0.0
    for v in arr:
        v = v or 0
        if v > peak:
            peak = v
        if peak - v > dd:
            dd = peak - v
    return dd


def fmt_ax(v, k=1):
    a = abs(v or 0)
    if a >= 100000 or (k and a >= 1000):
        s = '-$' if v < 0 else '$'
        return s + (str(round(a / 1000)) if a >= 10000 else ('%.1f' % (a / 1000))) + 'k'
    return fmt_usd(round(v or 0))


def fmt_usd(v):
    s = '-$' if (v or 0) < 0 else '$'
    return s + format(abs(round(v or 0)), ',')


DASHES = (None, '', '—', '-', '–')


def parse_num(shown):
    if shown is None:
        return None
    t = str(shown).replace('°', '').replace('*', '').strip()
    if t in DASHES:
        return None
    neg = t.startswith('-')
    t = t.lstrip('-$').rstrip('%×')
    mul = 1000.0 if t.endswith('k') else 1.0
    t = t.rstrip('k').replace(',', '')
    try:
        return float(t) * mul * (-1 if neg else 1)
    except ValueError:
        return None


def approx(shown, expected, tol=0.02):
    """shown: text like $123k / -$45.2k / 1.23 / 45% ; expected: number or None."""
    v = parse_num(shown)
    if v is None or expected is None:
        return v is None and expected is None
    if expected == 0:
        return abs(v) < 1e-6
    t = str(shown)
    mul = 1000.0 if t.rstrip('°* ').endswith('k') else 1.0
    # display rounding: $123k has ~0.5k slack; $1.5k ~0.055k; 1dp ratios ~0.055; 2dp ~0.006
    if mul > 1:
        slack = mul * (0.55 if abs(expected) >= 10000 else 0.055)
    else:
        # infer decimals shown
        m = re.search(r'\.(\d+)', t)
        slack = 0.55 if not m and abs(expected) > 20 else (10 ** (-len(m.group(1))) * 0.55 if m else 0.55)
    slack = max(slack, abs(expected) * 0.0005)
    return abs(v - expected) <= slack + 1e-9


def blk(b, mlt=1.0):
    """normalise an engine stat block to {net,dd,pf,wr,kept,apt} in display units."""
    if not isinstance(b, dict):
        return None
    g = lambda k: b.get(k)
    return {'net': g('total_pnl') * mlt if g('total_pnl') is not None else None,
            'dd': abs(g('max_drawdown')) * mlt if g('max_drawdown') is not None else None,
            'pf': g('profit_factor'), 'wr': g('win_rate'),
            'rec': g('rec'),
            'kept': g('num_trades'),
            'apt': g('avg_pnl') * mlt if g('avg_pnl') is not None else None}


def pool_parts(parts):
    """combine per-stretch blocks the way the client does (sum $, pool PF, weight WR)."""
    net = sum((p['net'] or 0) for p in parts)
    kept = sum(p['kept'] for p in parts) if all(p['kept'] is not None for p in parts) else None
    gw = gl = 0.0; pf_ok = True; wins = 0.0; wr_ok = True
    for p in parts:
        if p['net'] is None or p['pf'] is None or not p['pf'] > 1.0000001:
            pf_ok = False
        else:
            L = p['net'] / (p['pf'] - 1); gl += L; gw += p['pf'] * L
        if p['wr'] is None or p['kept'] is None:
            wr_ok = False
        else:
            wins += p['wr'] / 100.0 * p['kept']
    return {'net': net, 'kept': kept,
            'apt': (net / kept) if kept else None,
            'pf': (gw / gl) if (pf_ok and gl > 1e-9) else None,
            'wr': (wins / kept * 100) if (wr_ok and kept) else None}


def sharpe_of(diffs, n_over_yrs):
    n = len(diffs)
    if n < 1:
        return None
    mean = sum(diffs) / n
    var = sum((x - mean) ** 2 for x in diffs) / max(1, n - 1)
    sd = math.sqrt(var)
    if not sd > 1e-9:
        return None
    return (mean / sd) * math.sqrt(n_over_yrs)


def years_between(a, b):
    from datetime import date
    try:
        d0 = date.fromisoformat(str(a)[:10]); d1 = date.fromisoformat(str(b)[:10])
    except ValueError:
        return None
    dt = (d1 - d0).days
    return dt / 365.25 if dt > 0 else None


class Auditor(object):
    def __init__(self, doc):
        self.doc = doc
        self.mlt = doc.get('multiplier') or 1.0
        self.problems = []
        self.checked = 0

    def bad(self, where, msg):
        self.problems.append('%s: %s' % (where, msg))

    def cmp(self, where, shown, expected, tol=0.02):
        self.checked += 1
        if not approx(shown, expected, tol):
            self.bad(where, 'shown %r != expected %r' % (shown, expected))

    def row(self, tab, label, contains=None):
        rows = [r for r in tab['rows'] if r['lbl'].split('·')[0].strip() == label]
        return rows[0] if rows else None

    # ---- RAW tab ---------------------------------------------------------
    def raw_cols(self):
        sel = self.doc['selection']
        cand = list(sel['candidates']) + list(sel.get('robust') or [])
        return sorted(cand, key=lambda c: -(c.get('wf_oos_pnl') or 0))

    def raw_stitch(self, c):
        eq = (c.get('equity') or {})
        a0 = eq.get('cum')
        if not isinstance(a0, list) or len(a0) < 2:
            return None
        a = list(a0)
        fin = eq.get('final')
        if fin is not None and (not a or abs(a[-1] - fin) > 1e-9):
            a.append(fin)
        lbe = c.get('lb_equity') or {}
        ok = bool(isinstance(lbe.get('cum'), list) and lbe.get('cum') and eq.get('final') is not None
                  and lbe.get('base') is not None)
        if not ok:
            return {'cum': a, 'isEnd': len(a) - 1, 'hasLb': False}
        anchor = eq['final']; base = lbe['base']
        lb_abs = [anchor + (v - base) for v in lbe['cum']]
        if lbe.get('final') is not None:
            fin2 = anchor + (lbe['final'] - base)
            if not lb_abs or abs(lb_abs[-1] - fin2) > 1e-9:
                lb_abs.append(fin2)
        return {'cum': a + lb_abs, 'isEnd': len(a) - 1, 'hasLb': True}

    def raw_frac(self, c):
        cal = c.get('cal') or {}
        def n(a, b):
            for x in (a, b):
                if isinstance(x, dict) and x.get('num_trades') is not None:
                    return x['num_trades']
            return None
        ni = n(c.get('is_rng'), cal.get('is')); nw = n(c.get('wf_rng'), cal.get('wf'))
        if ni is None or nw is None or (ni + nw) <= 0:
            return None
        return ni / float(ni + nw)

    def raw_span(self, c, segs):
        st = self.raw_stitch(c)
        if not st:
            return None
        has = lambda x: x in segs
        if has('is') and has('lb') and not has('wf'):
            return None
        cum, isEnd, hasLb = st['cum'], st['isEnd'], st['hasLb']
        frac = self.raw_frac(c)
        wfI = max(0, min(isEnd, round(frac * isEnd))) if frac is not None else None
        pick = None
        if segs == ['is']:
            pick = (0, wfI) if wfI is not None else None
        elif segs == ['wf']:
            pick = (wfI, isEnd) if wfI is not None else None
        elif segs == ['lb']:
            pick = (isEnd, len(cum) - 1) if hasLb else None
        elif segs == ['is', 'wf']:
            pick = (0, isEnd)
        elif segs == ['wf', 'lb']:
            pick = (wfI, len(cum) - 1) if (wfI is not None and hasLb) else None
        elif segs == ['is', 'wf', 'lb']:
            pick = (0, len(cum) - 1) if hasLb else None
        if not pick or pick[1] <= pick[0]:
            return None
        return {'cum': cum, 'i0': pick[0], 'i1': pick[1]}

    def raw_dd_exact(self, c, segs, mdd):
        cal = c.get('cal') or {}
        b = None
        if segs == ['is']:
            b = cal.get('is')
        elif segs == ['wf']:
            b = cal.get('wf')
        elif segs == ['is', 'wf']:
            b = cal.get('pre')
        if isinstance(b, dict) and b.get('max_drawdown') is not None:
            return abs(b['max_drawdown']) * self.mlt
        if segs == ['is', 'wf'] and mdd is not None:
            return mdd
        return None

    def raw_expected(self, c, segs, valblock):
        """expected Group-A values (net/dd/mar/sharpe) + Group-B (pf/wr/apt) for one candidate."""
        mlt = self.mlt
        cal = c.get('cal') or {}
        cal_is = (cal.get('is') or {}).get('total_pnl')
        cal_wf = (cal.get('wf') or {}).get('total_pnl')
        is_cal = cal_is is not None and cal_wf is not None
        isV = cal_is * mlt if is_cal else (c.get('is_pnl') * mlt if c.get('is_pnl') is not None else None)
        wfV = cal_wf * mlt if is_cal else (c.get('wf_oos_pnl') * mlt if c.get('wf_oos_pnl') is not None else None)
        eq = c.get('equity') or {}; lbe = c.get('lb_equity') or {}
        lb_ok = lbe.get('final') is not None
        opt_end = eq.get('final') * mlt if eq.get('final') is not None else None
        lbV = lbe['final'] * mlt if lb_ok else None
        lb_slice = (lbV - opt_end) if (lb_ok and opt_end is not None) else None
        full_run = lbV if lb_ok else opt_end
        mm = c.get('metrics') or {}
        mdd = abs(mm['max_drawdown']) * mlt if mm.get('max_drawdown') is not None else \
            (dd_from_cum(eq.get('cum')) * mlt if isinstance(eq.get('cum'), list) else None)
        # TOTAL of ticked
        if len(segs) >= 3:
            total = full_run
        else:
            vals = [v for sg, v in (('is', isV), ('wf', wfV), ('lb', lb_slice)) if sg in segs
                    and v is not None and math.isfinite(v)]
            total = sum(vals) if vals else None
        # per-slice engine blocks (new runs)
        per = {'is': blk(c.get('is_rng'), mlt), 'wf': blk(c.get('wf_rng'), mlt),
               'lb': blk(c.get('lockbox'), mlt)}
        exact = per[segs[0]] if len(segs) == 1 else None
        out = {'isV': isV, 'wfV': wfV, 'lbSlice': lb_slice, 'total': total}
        if exact:
            out.update({'net': exact['net'], 'dd': exact['dd'],
                        'mar': (exact['net'] / exact['dd']) if (exact['net'] is not None and exact['dd']) else None,
                        'pf': exact['pf'], 'wr': exact['wr'], 'apt': exact['apt']})
        else:
            parts = [per[sg] for sg in segs if per.get(sg)]
            has_new = any(per.values())
            dd_ex = self.raw_dd_exact(c, segs, mdd)
            if dd_ex is None:
                sp = self.raw_span(c, segs)
                dd = dd_slice(sp['cum'], sp['i0'], sp['i1']) * mlt if sp else None
            else:
                dd = dd_ex
            if has_new and len(parts) == len(segs):
                pooled = pool_parts(parts)
                net = pooled['net']
                out.update({'pf': pooled['pf'], 'wr': pooled['wr'], 'apt': pooled['apt']})
            else:
                net = total
                # old run: PF/WR/$T only when the tick is exactly IS+WF (whole optimize window)
                if segs == ['is', 'wf']:
                    out.update({'pf': mm.get('profit_factor'), 'wr': mm.get('win_rate'),
                                'apt': mm['avg_pnl'] * mlt if mm.get('avg_pnl') is not None else None})
                else:
                    out.update({'pf': None, 'wr': None, 'apt': None})
            out.update({'net': net, 'dd': dd,
                        'mar': (net / dd) if (net is not None and dd) else None})
        # SHARPE always off the stitched curve slice
        sp = self.raw_span(c, segs)
        sharpe = None
        if sp and sp['i1'] - sp['i0'] >= 3:
            yrs = self.raw_years(c, segs, valblock)
            if yrs:
                diffs = [sp['cum'][i] - sp['cum'][i - 1] for i in range(sp['i0'] + 1, sp['i1'] + 1)]
                sharpe = sharpe_of(diffs, len(diffs) / yrs)
        out['sharpe'] = sharpe
        out['trades'] = mm.get('num_trades')
        out['folds'] = c.get('folds_held')
        return out

    def raw_years(self, c, segs, valblock):
        w = ((valblock or {}).get('windows') or {}).get('optimize')
        yrs_w = years_between(w[0], w[1]) if w and w[0] and w[1] else None
        wl = ((valblock or {}).get('windows') or {}).get('lockbox')
        yrs_lb = years_between(wl[0], wl[1]) if wl and wl[0] and wl[1] else None
        frac = self.raw_frac(c)
        y = 0.0
        if 'is' in segs:
            if frac is None or not yrs_w:
                return None
            y += yrs_w * frac
        if 'wf' in segs:
            if frac is None or not yrs_w:
                return None
            y += yrs_w * (1 - frac)
        if 'lb' in segs:
            if not yrs_lb:
                return None
            y += yrs_lb
        return y if y > 0 else None

    def raw_scopedA(self, segs):
        """mirror of _rawScopedA: per-slice blocks on ANY candidate, or a usable
        curve span for the CURRENT tick on any candidate."""
        cols = self.raw_cols()
        has_new = any(c.get(k) for c in cols for k in ('is_rng', 'wf_rng', 'lockbox'))
        return has_new or any(self.raw_span(c, segs) for c in cols)

    def audit_raw(self, tab, segs, combo):
        cols = self.raw_cols()
        vb = self.doc.get('validate') or {}
        scoped = self.raw_scopedA(segs)
        for ci, c in enumerate(cols):
            exp = self.raw_expected(c, segs, vb)
            if not scoped:
                # v73.67 fallback: the tick cannot be honoured on this run, so Group A
                # reverts to the pinned whole-optimize-window stats -- each row MUST
                # then name its own window, which audit_raw_labels() checks below.
                mm = c.get('metrics') or {}
                eq = c.get('equity') or {}
                mdd = abs(mm['max_drawdown']) * self.mlt if mm.get('max_drawdown') is not None else \
                    (dd_from_cum(eq.get('cum')) * self.mlt if isinstance(eq.get('cum'), list) else None)
                wfV = exp['wfV']
                exp['dd'] = mdd
                exp['mar'] = (wfV / mdd) if (wfV is not None and mdd) else None
                w0 = ((vb.get('windows') or {}).get('optimize')) or [None, None]
                yrs = years_between(w0[0], w0[1]) if w0[0] and w0[1] else None
                cum = eq.get('cum')
                exp['sharpe'] = None
                if isinstance(cum, list) and len(cum) >= 3 and yrs:
                    diffs = [cum[i] - cum[i - 1] for i in range(1, len(cum))]
                    exp['sharpe'] = sharpe_of(diffs, len(diffs) / yrs)
                exp['pf'] = exp['wr'] = exp['apt'] = None
            w = 'raw[%s] col%d' % (combo, ci)
            for lbl, key in (('IS $', 'isV'), ('WF $', 'wfV'), ('LB $', 'lbSlice')):
                sg = lbl.split(' ')[0].lower()
                r = self.row(tab, lbl)
                if sg in segs:
                    if r is None:
                        self.bad(w, 'missing row %s' % lbl); continue
                    self.cmp(w + ' ' + lbl, r['cells'][ci], exp[key])
                elif r is not None:
                    self.bad(w, 'row %s shown though %s not ticked' % (lbl, sg))
            r = self.row(tab, 'TOTAL')
            if len(segs) > 1:
                self.cmp(w + ' TOTAL', r['cells'][ci] if r else None, exp['total'])
            elif r is not None:
                self.bad(w, 'TOTAL row shown with a single tick')
            r = self.row(tab, 'DD')
            self.cmp(w + ' DD', r['cells'][ci] if r else None,
                     -exp['dd'] if exp['dd'] is not None else None)
            if r is not None and ci == 0:
                if scoped and '·' in r['lbl']:
                    self.bad(w, 'DD row carries a redundant window tag (%r)' % r['lbl'])
                if not scoped and 'IS+WF' not in r['lbl']:
                    self.bad(w, 'pinned-fallback DD row must name its IS+WF window (%r)' % r['lbl'])
            for lbl, key in (('MAR', 'mar'), ('SHARPE', 'sharpe'), ('PF', 'pf'),
                             ('WIN %', 'wr'), ('$ / TRADE', 'apt')):
                r = self.row(tab, lbl)
                self.cmp(w + ' ' + lbl, r['cells'][ci] if r else None, exp[key])
                if r is not None and ci == 0 and lbl in ('MAR', 'SHARPE'):
                    tagged = '·' in r['lbl']
                    if scoped and tagged:
                        self.bad(w, '%s row carries a redundant window tag (%r)' % (lbl, r['lbl']))
                    if not scoped and not (tagged and 'IS+WF' in r['lbl']):
                        self.bad(w, '%s row in the pinned fallback must name its IS+WF window (%r)'
                                 % (lbl, r['lbl']))
            r = self.row(tab, 'TRADES')
            if r is not None:
                if '·' not in r['lbl'] or 'IS+WF' not in r['lbl']:
                    self.bad(w, 'TRADES row lost its IS+WF window tag (%r)' % r['lbl'])
                self.cmp(w + ' TRADES', r['cells'][ci], exp['trades'])
            r = self.row(tab, 'FOLDS HELD')
            if r is not None and exp['folds'] is not None:
                shown = r['cells'][ci].split('/')[0]
                self.cmp(w + ' FOLDS', shown, exp['folds'])
            # scatter: RAW pool dot must equal the scoped TOTAL/DD pair
        return cols

    # ---- GATE tab --------------------------------------------------------
    def gate_cols(self, segs, rank='rec'):
        V = self.gv()
        cands = sorted(V.get('candidates') or [], key=lambda c: -(c.get('pre_rec') or 0))
        cols = [self.gate_per(c) for c in cands]
        def rk(col):
            p = self.gate_P(col, segs)
            v = p.get('rec') if rank == 'rec' else p.get('net')
            return v if (v is not None and math.isfinite(v)) else -float('inf')
        if rank == 'floor':
            recs = [self.gate_P(c, segs).get('rec') for c in cols]
            mx = max([r for r in recs if r is not None and math.isfinite(r)] or [-float('inf')])
            ok = lambda c: (self.gate_P(c, segs).get('rec') or -1e18) >= 0.8 * mx if mx > -float('inf') else False
            return sorted(cols, key=lambda c: (not ok(c), -(self.gate_P(c, segs).get('net') if self.gate_P(c, segs).get('net') is not None else -float('inf'))))
        key = (lambda c: -(rk(c))) if rank != 'rec' else None
        if rank == 'rec':
            return sorted(cols, key=lambda c: -(self.gate_P(c, segs)['rec'] if self.gate_P(c, segs).get('rec') is not None and math.isfinite(self.gate_P(c, segs)['rec']) else -float('inf')))
        return sorted(cols, key=key)

    def gv(self):
        return self.doc.get('gate_validate') or ((self.doc.get('validate') or {}).get('gate_bakeoff'))

    def gate_per(self, cd):
        """mirror of the per-block assembly for one gate candidate (points units)."""
        V = self.gv()
        LB = V.get('lockbox'); ch = V.get('chosen')
        is_ch = bool(ch and cd.get('model') == ch.get('model')
                     and abs((cd.get('threshold') or 0) - (ch.get('threshold') or 0)) < 1e-6)
        cum = (cd.get('equity') or {}).get('cum')
        cum = cum if isinstance(cum, list) else None
        end = cum[-1] if cum else None
        lb_ex = LB['gated']['total_pnl'] if (is_ch and LB and (LB.get('gated') or {}).get('total_pnl') is not None) else None
        lb_s = lb_ex if lb_ex is not None else ((end - cd['pre_pnl']) if (end is not None and cd.get('pre_pnl') is not None) else None)
        m_lb = cd.get('lockbox') if isinstance(cd.get('lockbox'), dict) else None
        lb_net = m_lb['total_pnl'] if (m_lb and m_lb.get('total_pnl') is not None) else lb_s
        m_fu = cd.get('full') if isinstance(cd.get('full'), dict) else None
        fu_net = m_fu['total_pnl'] if (m_fu and m_fu.get('total_pnl') is not None) else \
            ((cd['pre_pnl'] + lb_s) if (cd.get('pre_pnl') is not None and lb_s is not None) else end)
        fu_dd = abs(m_fu['max_drawdown']) if (m_fu and m_fu.get('max_drawdown') is not None) else \
            (dd_slice(cum, 0, len(cum) - 1) if cum else None)
        per = {'pre': {'net': cd.get('pre_pnl'),
                       'dd': abs(cd['pre_pnl'] / cd['pre_rec']) if cd.get('pre_rec') else None,
                       'rec': cd.get('pre_rec'), 'pf': cd.get('pre_pf'), 'wr': cd.get('pre_wr'),
                       'kept': cd.get('kept_pre'),
                       'apt': (cd['pre_pnl'] / cd['kept_pre']) if (cd.get('pre_pnl') is not None and cd.get('kept_pre')) else None},
               'is': blk(cd.get('is_rng')), 'wf': blk(cd.get('wf_rng')),
               'wf_lb': blk(cd.get('wf_lb')), 'lb': blk(cd.get('lockbox')),
               'full': {'net': fu_net, 'dd': fu_dd,
                        'rec': (m_fu.get('rec') if (m_fu and m_fu.get('rec') is not None)
                                else ((fu_net / fu_dd) if (fu_net is not None and fu_dd) else None)),
                        'pf': m_fu.get('profit_factor') if m_fu else None,
                        'wr': m_fu.get('win_rate') if m_fu else None,
                        'kept': m_fu.get('num_trades') if m_fu else None,
                        'apt': m_fu.get('avg_pnl') if m_fu else None}}
        return {'cd': cd, 'per': per, 'cum': cum, 'chosen': is_ch, 'lb_net': lb_net}

    GATE_EXACT = {'is': 'is', 'wf': 'wf', 'lb': 'lb', 'is,wf': 'pre', 'is,wf,lb': 'full',
                  'wf,lb': 'wf_lb'}

    def gate_contig(self, segs):
        V = self.gv()
        n_pre = ((V.get('ungated_pre') or {}).get('num_trades')) or 0
        n_lb = ((V.get('ungated_lockbox') or {}).get('num_trades')) or 0
        n_is = ((V.get('ungated_is') or {}).get('num_trades')) or 0
        f_split = n_pre / float(n_pre + n_lb) if (n_pre + n_lb) > 0 else 1.0
        f_is = (n_is / float(n_pre + n_lb)) if ((n_pre + n_lb) > 0 and n_is) else 0.0
        span = {'is': (0, f_is), 'wf': (f_is, f_split), 'lb': (f_split, 1.0)}
        order = [s for s in ('is', 'wf', 'lb') if s in segs]
        for i in range(1, len(order)):
            if abs(span[order[i - 1]][1] - span[order[i]][0]) > 1e-9:
                return None
        return (span[order[0]][0], span[order[-1]][1]) if order else None

    def gate_P(self, col, segs):
        key = ','.join(segs)
        ex = self.GATE_EXACT.get(key)
        per = col['per']
        if ex and per.get(ex):
            p = dict(per[ex])
            if p.get('rec') is None and p.get('net') is not None and p.get('dd'):
                p['rec'] = p['net'] / abs(p['dd'])
            if p.get('apt') is None and p.get('net') is not None and p.get('kept'):
                p['apt'] = p['net'] / p['kept']
            return p
        parts = [per.get(sg) for sg in segs if per.get(sg)]
        if len(parts) != len(segs):
            return {}
        pooled = pool_parts(parts)
        contig = self.gate_contig(segs)
        cum = col['cum']
        dd = None
        if contig and isinstance(cum, list) and len(cum) > 1:
            i0 = round(contig[0] * (len(cum) - 1)); i1 = round(contig[1] * (len(cum) - 1))
            dd = dd_slice(cum, i0, i1)
        pooled['dd'] = dd
        pooled['rec'] = (pooled['net'] / dd) if (pooled.get('net') is not None and dd) else None
        return pooled

    def gate_sharpe(self, col, segs):
        V = self.gv()
        contig = self.gate_contig(segs)
        cum = col['cum']
        if not contig or not isinstance(cum, list):
            return None
        L = len(cum)
        i0 = round(contig[0] * (L - 1)); i1 = round(contig[1] * (L - 1))
        if i1 - i0 < 3:
            return None
        sp = V.get('span') or []
        lb_from = V.get('lockbox_from'); wf0 = (V.get('wf_range') or [None])[0]
        spans = {'is': (sp[0] if sp else None, wf0), 'wf': (wf0, lb_from),
                 'lb': (lb_from, sp[1] if len(sp) > 1 else None)}
        order = [s for s in ('is', 'wf', 'lb') if s in segs]
        a = spans[order[0]][0]; b = spans[order[-1]][1]
        yrs = years_between(a, b) if (a and b) else None
        if not yrs:
            return None
        diffs = [cum[i] - cum[i - 1] for i in range(i0 + 1, i1 + 1)]
        return sharpe_of(diffs, len(diffs) / yrs)

    def audit_gate(self, tab, segs, combo):
        m3 = self.mlt
        V = self.gv()
        cols = self.gate_cols(segs)
        heads = tab['heads']
        if len(heads) != len(cols):
            self.bad('gate[%s]' % combo, 'expected %d cols, see %d' % (len(cols), len(heads)))
            return
        for ci, col in enumerate(cols):
            w = 'gate[%s] col%d(%s)' % (combo, ci, heads[ci])
            p = self.gate_P(col, segs)
            per = col['per']
            for sg, lbl in (('is', 'IS $'), ('wf', 'WF $'), ('lb', 'LB $')):
                r = self.row(tab, lbl)
                if sg in segs:
                    v = (per.get(sg) or {}).get('net')
                    self.cmp(w + ' ' + lbl, r['cells'][ci] if r else None,
                             v * m3 if v is not None else None)
                elif r is not None:
                    self.bad(w, '%s shown though not ticked' % lbl)
            if len(segs) > 1:
                r = self.row(tab, 'TOTAL')
                self.cmp(w + ' TOTAL', r['cells'][ci] if r else None,
                         p.get('net') * m3 if p.get('net') is not None else None)
            r = self.row(tab, 'DD')
            self.cmp(w + ' DD', r['cells'][ci] if r else None,
                     -p['dd'] * m3 if p.get('dd') is not None else None)
            r = self.row(tab, 'MAR')
            self.cmp(w + ' MAR', r['cells'][ci] if r else None, p.get('rec'))
            r = self.row(tab, 'SHARPE')
            self.cmp(w + ' SHARPE', r['cells'][ci] if r else None, self.gate_sharpe(col, segs))
            r = self.row(tab, 'PF')
            self.cmp(w + ' PF', r['cells'][ci] if r else None, p.get('pf'))
            r = self.row(tab, 'WIN %')
            self.cmp(w + ' WIN%', r['cells'][ci] if r else None, p.get('wr'))
            r = self.row(tab, '$ / TRADE')
            self.cmp(w + ' $/T', r['cells'][ci] if r else None,
                     p.get('apt') * m3 if p.get('apt') is not None else None)
            r = self.row(tab, 'TRADES')
            self.cmp(w + ' TRADES', r['cells'][ci] if r else None, p.get('kept'))
            r = self.row(tab, 'NOT TAKEN')
            U = {'is': V.get('ungated_is'), 'wf': V.get('ungated_wf'), 'lb': V.get('ungated_lockbox')}
            tot = 0; ok = True
            for sg in segs:
                u = U.get(sg)
                if not u or u.get('num_trades') is None:
                    ok = False
                else:
                    tot += u['num_trades']
            exp_nt = max(0, tot - p['kept']) if (ok and p.get('kept') is not None) else None
            self.cmp(w + ' NOTTAKEN', r['cells'][ci] if r else None, exp_nt)

    # ---- TILT / HYBRID (one-lot) ----------------------------------------
    def sz_P(self, t, segs):
        per = {'is': blk(t.get('is_rng')), 'wf': blk(t.get('wf_rng')),
               'lb': blk(t.get('lockbox')), 'full': blk(t.get('full'))}
        key = ','.join(segs)
        ex = {'is': 'is', 'wf': 'wf', 'lb': 'lb', 'is,wf,lb': 'full'}.get(key)
        if ex and per.get(ex):
            p = dict(per[ex])
            if p.get('apt') is None and p.get('net') is not None and p.get('kept'):
                p['apt'] = p['net'] / p['kept']
            return p
        parts = [per.get(sg) for sg in segs if per.get(sg)]
        if len(parts) != len(segs):
            return {}
        pooled = pool_parts(parts)
        # DD off the saved curve across the trade-count span
        n = {sg: ((t.get(k) or {}).get('num_trades') or 0)
             for sg, k in (('is', 'is_rng'), ('wf', 'wf_rng'), ('lb', 'lockbox'))}
        T = n['is'] + n['wf'] + n['lb']
        dd = None
        if T:
            span = {'is': (0, n['is'] / T), 'wf': (n['is'] / T, (n['is'] + n['wf']) / T),
                    'lb': ((n['is'] + n['wf']) / T, 1.0)}
            order = [s for s in ('is', 'wf', 'lb') if s in segs]
            ok = all(abs(span[order[i - 1]][1] - span[order[i]][0]) <= 1e-9 for i in range(1, len(order)))
            cum = (t.get('equity') or {}).get('cum')
            if ok and isinstance(cum, list) and len(cum) > 1:
                a0 = span[order[0]][0]; a1 = span[order[-1]][1]
                dd = dd_slice(cum, round(a0 * (len(cum) - 1)), round(a1 * (len(cum) - 1)))
        pooled['dd'] = dd
        return pooled

    def sz_mar(self, t, segs):
        p = self.sz_P(t, segs)
        return (p['net'] / abs(p['dd'])) if (p.get('net') is not None and p.get('dd')) else None

    def sz_cols(self, V, kind, segs):
        lst = list(V.get('tilts' if kind == 'tilt' else 'hybrids') or [])
        # the client pre-sorts by LOCKBOX rec, then stable-sorts by the scoped MAR --
        # so ties in the scoped sort (e.g. a non-contiguous tick where MAR dashes)
        # keep the lockbox-rec order, not the doc order
        def lb_rec(t):
            x = t.get('lockbox') or {}
            dd = abs(x.get('max_drawdown') or 0)
            return (x['total_pnl'] / dd) if (x.get('total_pnl') is not None and dd > 1e-9) else -99
        lst.sort(key=lambda t: -lb_rec(t))
        lst.sort(key=lambda t: -(m if (m := self.sz_mar(t, segs)) is not None else -99))
        return lst

    def sz_sharpe(self, t, segs):
        V = self.gv()
        sp = V.get('span') or []
        yrs_full = years_between(sp[0], sp[1]) if len(sp) > 1 and sp[0] and sp[1] else None
        cum = (t.get('equity') or {}).get('cum')
        if not isinstance(cum, list) or len(cum) < 3 or not yrs_full:
            return None
        n = {sg: ((t.get(k) or {}).get('num_trades') or 0)
             for sg, k in (('is', 'is_rng'), ('wf', 'wf_rng'), ('lb', 'lockbox'))}
        T = n['is'] + n['wf'] + n['lb']
        a, b = 0.0, 1.0
        if T:
            span = {'is': (0, n['is'] / T), 'wf': (n['is'] / T, (n['is'] + n['wf']) / T),
                    'lb': ((n['is'] + n['wf']) / T, 1.0)}
            order = [s for s in ('is', 'wf', 'lb') if s in segs]
            for i in range(1, len(order)):
                if abs(span[order[i - 1]][1] - span[order[i]][0]) > 1e-9:
                    return None
            if order:
                a = span[order[0]][0]; b = span[order[-1]][1]
        i0 = max(0, round(a * (len(cum) - 1))); i1 = min(len(cum) - 1, round(b * (len(cum) - 1)))
        if i1 - i0 < 2:
            return None
        diffs = [cum[i] - cum[i - 1] for i in range(i0 + 1, i1 + 1)]
        yrs = yrs_full * max(1e-6, b - a)
        return sharpe_of(diffs, len(diffs) / yrs)

    def audit_sz(self, tab, segs, combo, kind):
        m3 = self.mlt
        V = self.gv()
        lst = self.sz_cols(V, kind, segs)
        mar = lambda t: self.sz_mar(t, segs)
        heads = tab['heads']
        if len(heads) != len(lst):
            self.bad('%s[%s]' % (kind, combo), 'expected %d cols, see %d' % (len(lst), len(heads)))
            return
        for ci, t in enumerate(lst):
            w = '%s[%s] col%d(%s)' % (kind, combo, ci, heads[ci])
            p = self.sz_P(t, segs)
            per = {'is': blk(t.get('is_rng')), 'wf': blk(t.get('wf_rng')), 'lb': blk(t.get('lockbox'))}
            for sg, lbl in (('is', 'IS $'), ('wf', 'WF $'), ('lb', 'LB $')):
                r = self.row(tab, lbl)
                if sg in segs:
                    v = (per.get(sg) or {}).get('net')
                    self.cmp(w + ' ' + lbl, r['cells'][ci] if r else None,
                             v * m3 if v is not None else None)
                elif r is not None:
                    self.bad(w, '%s shown though not ticked' % lbl)
            if len(segs) > 1:
                r = self.row(tab, 'TOTAL')
                self.cmp(w + ' TOTAL', r['cells'][ci] if r else None,
                         p.get('net') * m3 if p.get('net') is not None else None)
            r = self.row(tab, 'DD')
            self.cmp(w + ' DD', r['cells'][ci] if r else None,
                     -p['dd'] * m3 if p.get('dd') is not None else None)
            r = self.row(tab, 'MAR')
            self.cmp(w + ' MAR', r['cells'][ci] if r else None, mar(t))
            r = self.row(tab, 'SHARPE')
            self.cmp(w + ' SHARPE', r['cells'][ci] if r else None, self.sz_sharpe(t, segs))
            r = self.row(tab, 'PF')
            self.cmp(w + ' PF', r['cells'][ci] if r else None, p.get('pf'))
            r = self.row(tab, 'WIN %')
            self.cmp(w + ' WIN%', r['cells'][ci] if r else None, p.get('wr'))
            r = self.row(tab, '$ / TRADE')
            self.cmp(w + ' $/T', r['cells'][ci] if r else None,
                     p.get('apt') * m3 if p.get('apt') is not None else None)
            r = self.row(tab, 'TRADES')
            self.cmp(w + ' TRADES', r['cells'][ci] if r else None, p.get('kept'))
            r = self.row(tab, 'NOT TAKEN')
            if r is not None:
                U = {'is': V.get('ungated_is'), 'wf': V.get('ungated_wf'), 'lb': V.get('ungated_lockbox')}
                s = 0; ok = True
                for sg in segs:
                    u = U.get(sg); x = per.get(sg)
                    if not u or u.get('num_trades') is None or not x or x.get('kept') is None:
                        ok = False
                    else:
                        s += u['num_trades'] - x['kept']
                self.cmp(w + ' NOTTAKEN', r['cells'][ci], max(0, s) if ok else None)
            r = self.row(tab, 'BIGGEST SIZE')
            if r is not None:
                if 'FULL' not in r['lbl']:
                    self.bad(w, 'BIGGEST SIZE lost its FULL tag')
                self.cmp(w + ' BIGGEST', r['cells'][ci], t.get('max_size'))

    # ---- scatter + header tags ------------------------------------------
    def audit_scatter(self, one, segs, combo):
        m3 = self.mlt
        # RAW pool dots = scoped total/dd
        scoped = self.raw_scopedA(segs)
        for pt in (one.get('rawScatter') or []):
            i = int(pt['key'].split(':')[1])
            c = self.raw_cols()[i]
            exp = self.raw_expected(c, segs, self.doc.get('validate') or {})
            if not scoped:
                # pinned fallback: a dot is only allowed on the exact IS+WF tick,
                # carrying the pinned whole-optimize-window drawdown
                if segs == ['is', 'wf']:
                    mm = c.get('metrics') or {}
                    eq = c.get('equity') or {}
                    exp['dd'] = abs(mm['max_drawdown']) * self.mlt if mm.get('max_drawdown') is not None else                         (dd_from_cum(eq.get('cum')) * self.mlt if isinstance(eq.get('cum'), list) else None)
                else:
                    exp['dd'] = None
            w = 'scatter[%s] %s' % (combo, pt['key'])
            self.checked += 2
            if exp['total'] is None or exp['dd'] is None:
                self.bad(w, 'dot exists but scoped total/dd is %r/%r' % (exp['total'], exp['dd']))
                continue
            if abs(pt['pnl'] - exp['total']) > max(1, abs(exp['total']) * 0.001):
                self.bad(w, 'pnl %r != scoped total %r' % (pt['pnl'], exp['total']))
            if abs(pt['dd'] - exp['dd']) > max(1, abs(exp['dd']) * 0.001):
                self.bad(w, 'dd %r != scoped dd %r' % (pt['dd'], exp['dd']))
        for pt in (one.get('gvScatter') or []):
            kind, i = pt['key'].split(':'); i = int(i)
            w = 'scatter[%s] %s' % (combo, pt['key'])
            if kind == 'gate':
                col = self.gate_cols(segs)[i]
                p = self.gate_P(col, segs)
                net = p.get('net'); dd = p.get('dd')
            else:
                V = self.gv()
                if kind == 'hyb2':
                    continue   # recycle view shares candidates; sized by redeploy factor
                lst = self.sz_cols(V, 'tilt' if kind == 'tilt' else 'hyb', segs)
                p2 = self.sz_P(lst[i], segs)
                net = p2.get('net'); dd = p2.get('dd')
            self.checked += 2
            if net is None or dd is None:
                self.bad(w, 'dot exists but scoped net/dd is %r/%r' % (net, dd))
                continue
            if abs(pt['pnl'] - net * m3) > max(1, abs(net * m3) * 0.001):
                self.bad(w, 'pnl %r != scoped %r' % (pt['pnl'], net * m3))
            if abs(pt['dd'] - abs(dd) * m3) > max(1, abs(dd * m3) * 0.001):
                self.bad(w, 'dd %r != scoped %r' % (pt['dd'], abs(dd) * m3))

    TAG_COL = {'IS': 'var(--text4)', 'WF': '#60a5fa', 'LB': '#a78bfa'}

    def audit_tags(self, one, segs, combo):
        segs_up = [s.upper() for s in segs]
        for tabname in ('raw', 'gate', 'tilt', 'hyb'):
            t = one.get(tabname)
            if not t:
                continue
            for r in t['rows']:
                blob = r['lblHtml'] + ' '.join(x or '' for x in (r.get('titles') or []))
                self.checked += 1
                if 'undefined' in blob or 'NaN' in blob:
                    self.bad('%s[%s] row %r' % (tabname, combo, r['lbl']),
                             'undefined/NaN leaked into a label or tooltip')
            for g in t['groups']:
                nm = g['name']
                if '·' not in nm:
                    continue
                self.checked += 1
                for s in segs_up:
                    if not re.search(r'%s' % s, nm):
                        continue   # e.g. the old-run 'mixed slices' wording carries no seg names
                    pat = '<span style="color:%s">%s</span>' % (self.TAG_COL[s], s)
                    if pat not in g['html']:
                        self.bad('%s[%s] header %r' % (tabname, combo, nm),
                                 'scope %s not coloured %s' % (s, self.TAG_COL[s]))


GATE_MNM = {'logistic': 'LOGIT', 'rf': 'RF', 'xgb': 'XGB'}


def gate_label(cd):
    m = str(cd.get('model') or '')
    return '%s %d%%' % (GATE_MNM.get(m, m.upper()), round((cd.get('threshold') or 0) * 100))


def audit_rank(au, probe):
    """RANK BY must order the columns on the SCOPED values the highlighted rows show."""
    for combo, by_rank in (probe.get('rank') or {}).items():
        segs = combo.split(',')
        for rk, r in by_rank.items():
            w = 'rank[%s][%s]' % (combo, rk)
            # ---- RAW: heads carry the walk-forward rank number R<n> ----
            heads = r.get('raw') or []
            got = [int(m.group(1)) for h in heads for m in [re.search(r'R(\d+)', h)] if m]
            cols = au.raw_cols()
            recs = [{'i': i + 1, 'c': c} for i, c in enumerate(cols)]
            if rk == 'rec':
                exp = [x['i'] for x in recs]
            else:
                vb = au.doc.get('validate') or {}
                scoped = au.raw_scopedA(segs)
                def tot(x):
                    e = au.raw_expected(x['c'], segs, vb)
                    return e['total'] if e['total'] is not None else -float('inf')
                def marv(x):
                    e = au.raw_expected(x['c'], segs, vb)
                    mm = x['c'].get('metrics') or {}
                    if not scoped:
                        eq = x['c'].get('equity') or {}
                        mdd = abs(mm['max_drawdown']) * au.mlt if mm.get('max_drawdown') is not None else None
                        return (e['wfV'] / mdd) if (e['wfV'] is not None and mdd) else -float('inf')
                    return e['mar'] if e['mar'] is not None else -float('inf')
                order = sorted(recs, key=lambda x: -tot(x))
                if rk == 'floor':
                    mx = max([marv(x) for x in order] or [-float('inf')])
                    ok = lambda x: marv(x) > -float('inf') and mx > -float('inf') and marv(x) >= 0.8 * mx
                    order = sorted(order, key=lambda x: not ok(x))
                exp = [x['i'] for x in order]
            if got != exp:
                au.checked += 1
                au.bad(w + ' RAW', 'column order %s != expected scoped order %s' % (got, exp))
            else:
                au.checked += 1
            # ---- GATE: order on the scoped _P ----
            heads_g = [h.replace('\U0001f451', '').strip() for h in (r.get('gate') or [])]
            V = au.gv()
            if V and heads_g:
                cands = sorted(V.get('candidates') or [], key=lambda c: -(c.get('pre_rec') or 0))
                pcols = [au.gate_per(c) for c in cands]
                def gp(col, k):
                    v = au.gate_P(col, segs).get(k)
                    return v if (v is not None and math.isfinite(v)) else -float('inf')
                if rk == 'rec':
                    order = sorted(pcols, key=lambda c: -gp(c, 'rec'))
                else:
                    order = sorted(pcols, key=lambda c: -gp(c, 'net' if rk != 'rec' else 'rec'))
                    if rk == 'floor':
                        mx = max([gp(c, 'rec') for c in pcols] or [-float('inf')])
                        ok = lambda c: gp(c, 'rec') > -float('inf') and mx > -float('inf') and gp(c, 'rec') >= 0.8 * mx
                        order = sorted(order, key=lambda c: not ok(c))
                exp_g = [gate_label(c['cd']) for c in order]
                au.checked += 1
                if heads_g != exp_g:
                    au.bad(w + ' GATE', 'column order %s != expected scoped order %s' % (heads_g, exp_g))


def audit(doc, probe):
    au = Auditor(doc)
    for combo in COMBOS:
        segs = combo.split(',')
        one = probe['combos'][combo]
        if one.get('raw'):
            au.audit_raw(one['raw'], segs, combo)
        if one.get('gate'):
            au.audit_gate(one['gate'], segs, combo)
        if one.get('tilt'):
            au.audit_sz(one['tilt'], segs, combo, 'tilt')
        if one.get('hyb'):
            au.audit_sz(one['hyb'], segs, combo, 'hyb')
        au.audit_scatter(one, segs, combo)
        au.audit_tags(one, segs, combo)
    audit_rank(au, probe)
    return au


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('doc')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--dump')
    a = ap.parse_args()
    chrome = find_chrome()
    if not chrome:
        print('MTXAUDIT: INCONCLUSIVE -- chrome not found'); sys.exit(INCONCLUSIVE)
    doc = json.load(open(a.doc, encoding='utf-8'))
    build_harness(doc)
    obj, err = run_probe(chrome)
    if not a.keep:
        try:
            os.remove(HARNESS)
        except OSError:
            pass
    if err:
        print('MTXAUDIT: INCONCLUSIVE -- %s' % err); sys.exit(INCONCLUSIVE)
    if not obj.get('ok'):
        print('MTXAUDIT: FAIL -- probe threw:\n%s' % obj.get('err')); sys.exit(FAIL)
    if a.dump:
        json.dump(obj, open(a.dump, 'w', encoding='utf-8'), indent=1)
        print('dumped probe to %s' % a.dump)
    au = audit(doc, obj)
    if au.problems:
        print('MTXAUDIT: FAIL -- %d mismatch(es) out of %d checks' % (len(au.problems), au.checked))
        for p in au.problems[:80]:
            print('  - %s' % p)
        if len(au.problems) > 80:
            print('  ... and %d more' % (len(au.problems) - 80))
        sys.exit(FAIL)
    print('MTXAUDIT: PASS -- %d cell checks across %d combos, 4 tabs, scatter + header tags'
          % (au.checked, len(COMBOS)))
    sys.exit(PASS)
