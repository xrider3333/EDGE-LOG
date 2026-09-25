"""api/runner.py _doc_size follows Firestore's own size rules (2026-09-25).

The old len(json.dumps(doc)) proxy under-counted numbers (12.5 = 4 JSON characters, 8
Firestore bytes), so a numeric-heavy Auto-Validate run doc read as fitting, skipped every
shrink stage and was refused by Firestore at 1,049,722 bytes (CBU-Q, burned run id #426).
"""
import json

import api.runner as R


def test_value_sizes_follow_firestore_rules():
    assert R._fs_value_size("xyz") == 4            # UTF-8 bytes + 1
    assert R._fs_value_size(12.5) == 8
    assert R._fs_value_size(7) == 8
    assert R._fs_value_size(True) == 1
    assert R._fs_value_size(None) == 1
    assert R._fs_value_size([1.5, 2.5, "a"]) == 8 + 8 + 2
    assert R._fs_value_size({"ab": "xyz"}) == (2 + 1) + (3 + 1)
    assert R._fs_value_size({"k": {"m": [1, 2]}}) == (1 + 1) + (1 + 1) + 16


def test_numeric_heavy_doc_that_json_underestimates_gets_shrunk():
    # ~700 KB of JSON, ~1.12 MB in Firestore: the old proxy said "fits"
    doc = {"strategy": "X.py", "equity": [(i % 7) * 0.5 for i in range(140_000)]}
    assert len(json.dumps(doc)) < R.DOC_SIZE_BUDGET
    assert R._doc_size(doc) > R.FIRESTORE_DOC_LIMIT
    out = R.shrink_to_fit(dict(doc), log=lambda m: None, label="numeric-heavy")
    assert R._doc_size(out) <= R.DOC_SIZE_BUDGET
