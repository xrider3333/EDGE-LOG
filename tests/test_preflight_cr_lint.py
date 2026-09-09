"""Pins the stray-carriage-return lint in tools/preflight_boot.py.

index.html is CRLF in the working tree, so a CR that ends a line is normal and
git normalises it on check-in. A CR that is NOT a line ending is not touched by
that normalisation and reaches the stored blob -- three of them did, in the
RESEARCH_STUDIES rows array, on 2026-09-09. The lint must fire on that case and
stay silent on ordinary CRLF, or it is either useless or unshippable.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.preflight_boot import lint_stray_carriage_returns  # noqa: E402


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_plain_crlf_file_is_clean(tmp_path):
    p = _write(tmp_path, 'crlf.html', b'<html>\r\n<body>hi</body>\r\n</html>\r\n')
    assert lint_stray_carriage_returns(p) == []


def test_plain_lf_file_is_clean(tmp_path):
    p = _write(tmp_path, 'lf.html', b'<html>\n<body>hi</body>\n</html>\n')
    assert lint_stray_carriage_returns(p) == []


def test_mid_line_cr_is_caught(tmp_path):
    # the real artifact: a row object spliced in ahead of its existing comma
    p = _write(tmp_path, 'row.html', b"a\r\n        {n:1456,tot:5}\r,\r\nb\r\n")
    hits = lint_stray_carriage_returns(p)
    assert len(hits) == 1
    line_no, col, snippet = hits[0]
    assert line_no == 2
    assert '<CR>' in snippet and '{n:1456' in snippet


def test_counts_every_occurrence_and_reports_line_numbers(tmp_path):
    p = _write(tmp_path, 'many.html', b'one\rX\r\ntwo\r\nthree\rY\r\n')
    hits = lint_stray_carriage_returns(p)
    assert [h[0] for h in hits] == [1, 3]


def test_trailing_bare_cr_at_eof_is_caught(tmp_path):
    p = _write(tmp_path, 'eof.html', b'tail\r\nlast\r')
    assert len(lint_stray_carriage_returns(p)) == 1


def test_missing_file_returns_none(tmp_path):
    assert lint_stray_carriage_returns(str(tmp_path / 'nope.html')) is None


def test_shipped_index_html_has_no_stray_cr():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index = os.path.join(root, 'index.html')
    if not os.path.isfile(index):
        return
    assert lint_stray_carriage_returns(index) == []
