#!/usr/bin/env python3
"""
tools/capture_run_fixture.py -- capture ONE saved run document out of Firestore as the
fixture behind tools/report_render_probe.py (the RESULTS run-report render gate).

    python tools/capture_run_fixture.py 306            # -> tools/fixtures/run_report.json
    python tools/capture_run_fixture.py 306 --out x.json

The probe wants a VALIDATE run that carries the report-only blocks (gate_validate with
candidates / tilts / hybrids, validate, selection, plateau_pick ...), because those are
the tables that have shipped broken twice (v73.367, v73.442) behind a green boot gate.
Run 306 (NOISE_1_0, validated 2026-08) is the document that failed in v73.442.

TRIMMING. The document is ~540 KB as stored; the fixture is committed, so the long
chart series are thinned: any list longer than KEEP whose members are all numbers, all
number-pairs, or all flat number dicts (equity points, drawdown series, MC paths) is
subsampled evenly to KEEP points, first and last kept. Nothing structural is removed --
every key, every candidate / tilt / hybrid row and every scalar survives -- so the
report renders the same code paths it renders in production, just with shorter curves.

Needs serviceAccount.json (gitignored; lives in the shared checkout) and firebase_admin.
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
KEEP = 400


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _flat_numeric(x):
    if _num(x) or x is None:
        return True
    if isinstance(x, list):
        return len(x) <= 4 and all(_num(y) or y is None for y in x)
    if isinstance(x, dict):
        return len(x) <= 6 and all(_num(y) or y is None or isinstance(y, str) and len(y) <= 24
                                   for y in x.values())
    return False


def trim(node):
    if isinstance(node, dict):
        return {k: trim(v) for k, v in node.items()}
    if isinstance(node, list):
        if len(node) > KEEP and all(_flat_numeric(x) for x in node):
            step = (len(node) - 1) / float(KEEP - 1)
            idx = sorted({int(round(i * step)) for i in range(KEEP)} | {0, len(node) - 1})
            return [trim(node[i]) for i in idx]
        return [trim(x) for x in node]
    return node


def _conv(o):
    if hasattr(o, 'isoformat'):
        return o.isoformat()
    return str(o)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run_id')
    ap.add_argument('--out', default=os.path.join(ROOT, 'tools', 'fixtures', 'run_report.json'))
    ap.add_argument('--uid', default=UID)
    ap.add_argument('--no-trim', action='store_true')
    a = ap.parse_args()

    cred_path = next((p for p in (
        os.path.join(ROOT, 'serviceAccount.json'),
        os.path.expanduser(r'~\OneDrive\Desktop\EDGE-LOG\serviceAccount.json'),
    ) if os.path.isfile(p)), None)
    if not cred_path:
        raise SystemExit('serviceAccount.json not found (checked this repo and the shared checkout)')
    import firebase_admin
    from firebase_admin import credentials, firestore
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    db = firestore.client()
    snap = db.collection('users').document(a.uid).collection('runs').document(str(a.run_id)).get()
    if not snap.exists:
        raise SystemExit('run %s not found' % a.run_id)
    doc = json.loads(json.dumps(snap.to_dict(), default=_conv))
    doc.setdefault('id', int(a.run_id) if str(a.run_id).isdigit() else a.run_id)
    raw = len(json.dumps(doc))
    if not a.no_trim:
        doc = trim(doc)
    gv = doc.get('gate_validate') or {}
    out = json.dumps(doc, separators=(',', ':'), ensure_ascii=False)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    io.open(a.out, 'w', encoding='utf-8').write(out)
    print('run %s: %s  %d -> %d bytes  gate_validate: %d candidates / %d tilts / %d hybrids  -> %s'
          % (a.run_id, doc.get('strategy'), raw, len(out),
             len(gv.get('candidates') or []), len(gv.get('tilts') or []),
             len(gv.get('hybrids') or []), a.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
