"""AN INDEX MUST NOT BE ABLE TO HIDE A TRADE (MANAGER 2026-11-19, the hour after v91.06).

The journal and the open board are read from index documents - three reads instead of 108 and 324.
Those indexes are maintained by the code that writes the rows. The moment a writer runs OLD code
it writes a real document and tells no index, and a page that trusted the index would simply not
show the owner his new trade. On the day this shipped the shared checkout the PC runner runs from
was sixteen commits behind main, so this was not hypothetical.

Two halves, and these tests hold both:
  * THE PAGE AUDITS. After it loads an index it asks the collection for its newest row by each
    stamp every writer sets, and if that row is unknown to the index, or stamped after the index
    was last written, this tab stops trusting the index and reads the collection instead.
  * THE PC FIXES. tools/index_doctor.py compares each index with its collection, names what the
    page cannot see, and rebuilds on --fix. It is also what clears the mark the page leaves.

The failure these guard against is silent, which is the worst kind: a journal that quietly stops
at yesterday looks exactly like a day with no trades.
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HTML = os.path.join(ROOT, 'index.html')


def src():
    with open(HTML, encoding='utf-8') as f:
        return f.read()


# ───────────────────────────────── the page's audit ─────────────────────────────────
def test_the_audit_probes_every_stamp_a_writer_sets():
    s = src()
    i = s.index('function _ixBehind(')
    seg = s[i:s.index('function _ixMarkStale(')]
    assert "col.orderBy(f,'desc').limit(1).get()" in seg, "one document per stamp, not a scan"
    assert 'q.docs[0]' in seg
    t = s[s.index('function _tixAudit('):s.index('window._tixOnHead=')]
    assert "['createdAt','date']" in t, "every trade carries createdAt - the syncs and the page set it"
    b = s[s.index('function _bdAudit('):s.index('window._bdOnHead=')]
    assert "['updated_at','date']" in b, "tools/board.py stamps updated_at on every row it writes"


def test_an_unknown_row_or_a_newer_row_means_the_index_is_behind():
    s = src()
    i = s.index('function _ixBehind(')
    seg = s[i:s.index('function _ixMarkStale(')]
    assert 'if(!held(d.id))return' in seg, "a row the index never heard of"
    assert 't>(at+IX_SKEW_MS)' in seg, "or a row written after the index was last touched"
    assert 'const IX_SKEW_MS' in s, "a sync writes the row, then the index a moment later"


def test_a_refused_probe_is_not_evidence_of_staleness():
    """Otherwise a quota refusal would push every tab onto the 108-read path - the opposite of
    what this whole change is for."""
    s = src()
    i = s.index('function _ixBehind(')
    seg = s[i:s.index('function _ixMarkStale(')]
    j = seg.index('.catch(function(e){')
    assert 'return null;' in seg[j:j + 320]


def test_a_behind_index_falls_back_and_leaves_a_mark_for_the_pc():
    s = src()
    for fn, fb in (('_tixAudit', 'window._tixFallback'), ('_bdAudit', 'if(fallback)fallback(')):
        i = s.index('function %s(' % fn)
        seg = s[i:i + 1200]          # the whole audit function, not up to the first window. use
        assert '_ixMarkStale(' in seg, fn
        assert fb in seg, fn
    m = s[s.index('function _ixMarkStale('):]
    m = m[:m.index('\n// ')] if '\n// ' in m[:900] else m[:900]
    assert 'stale:new Date().toISOString()' in m and '{merge:true}' in m, "one write, merged"


def test_the_audit_runs_when_a_sleeping_tab_wakes():
    """A tab asleep since yesterday is exactly the one that may have missed a night of writes."""
    s = src()
    i = s.index('function _lsResume()')
    seg = s[i:s.index('function _lsVis()')]
    assert '_tixAudit(' in seg and '_bdAudit(' in seg
    assert 'window._tixAuditing=false' in seg, "the once-per-load guard has to be released first"


def test_the_audit_runs_after_the_shards_land_not_before():
    s = src()
    t = s[s.index('_tixFetch(uid,+head.shards)'):]
    t = t[:t.index('.catch(')]
    assert t.index('_tixPublish()') < t.index('_tixAudit(uid,head)'), \
        "audit what was actually loaded"
    b = s[s.index('_bdIndexFetch(u,+head.shards)'):]
    b = b[:b.index('.catch(')]
    assert '_bdAudit(u,head,fallback)' in b


def test_a_trade_added_on_the_page_reaches_the_index():
    """addTrade is the page's own writer - nothing on the PC would tell the index about it, and the
    journal is read from the index now."""
    s = src()
    i = s.index('if(colRef){')
    seg = s[i:i + 700]
    assert 'colRef.add(' in seg and '_tixPoke(' in seg


def test_a_date_only_stamp_is_read_as_a_day_not_a_midnight():
    s = src()
    assert 'function _ixDayMs(' in s
    seg = s[s.index('function _ixDayMs('):s.index('const IX_SKEW_MS')]
    assert '_ixMs(v)' in seg


# ───────────────────────────────── the PC's doctor ─────────────────────────────────
def doc_src():
    with open(os.path.join(ROOT, 'tools', 'index_doctor.py'), encoding='utf-8') as f:
        return f.read()


def test_the_doctor_names_what_the_page_cannot_see():
    s = doc_src()
    assert "missing = sorted(set(live) - indexed)" in s
    assert "ghosts = sorted(indexed - set(live))" in s
    assert 'CANNOT SEE' in s


def test_the_doctor_counts_the_head_s_inline_rows_as_indexed():
    """They are applied on top of the shards by the page, so a row that is only inline is NOT
    missing - calling it missing would make the doctor cry drift after every sync."""
    s = doc_src()
    seg = s[s.index("for e in head.get('recent')"):s.index('missing = sorted')]
    assert 'indexed.add(rid)' in seg and 'indexed.discard(rid)' in seg


def test_the_doctor_rebuilds_through_the_real_builders_and_clears_the_mark():
    s = doc_src()
    seg = s[s.index('def fix('):s.index('def main(')]
    assert 'T.rebuild(' in seg and 'B.cmd_index(' in seg, "one builder each, not a copy of them"
    assert seg.count("'stale': None") == 2, "a fixed index stops telling the page it is stale"
    assert 'backup=bk' in seg, "a rebuild backs the rows up first"


def test_the_doctor_reports_without_touching_anything_by_default():
    s = doc_src()
    assert "p.add_argument('--fix'" in s
    seg = s[s.index('if not a.fix:'):s.index('out = fix(')]
    assert 'run with --fix' in seg


def test_both_indexes_are_covered():
    s = doc_src()
    assert "'trades'" in s and "'board'" in s and "'both'" in s
    assert 'trades_index' in s and 'board_index' in s
