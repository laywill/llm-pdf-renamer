"""Tests for sanitise_filename in file_rename.py."""

import pytest

from file_rename import MAX_FILENAME_LEN, sanitise_filename

# ---------------------------------------------------------------------------
# Dotless input — regression for the rpartition bug (Issue 4)
# ---------------------------------------------------------------------------


def test_dotless_name_gets_pdf_extension():
    """Dotless input must produce 'name.pdf', not '.name.pdf'."""
    result = sanitise_filename("Chase Bank Statement")
    assert result == "Chase Bank Statement.pdf"


def test_dotless_name_stem_not_empty():
    """The stem must not be empty when there is no dot in the input."""
    result = sanitise_filename("Invoice March 2024")
    stem = result.removesuffix(".pdf")
    assert stem != ""


# ---------------------------------------------------------------------------
# Normal cases — must still work after the fix
# ---------------------------------------------------------------------------


def test_pdf_extension_preserved():
    name = "2024-01-15 - Chase Bank - Statement.pdf"
    assert sanitise_filename(name) == name


def test_illegal_chars_replaced():
    result = sanitise_filename("file<name>:doc.pdf")
    assert result.endswith(".pdf")
    for ch in '<>:"/\\|?*':
        assert ch not in result


def test_stem_truncated_to_max_length():
    result = sanitise_filename("a" * 300 + ".pdf")
    stem = result.removesuffix(".pdf")
    assert len(stem) <= MAX_FILENAME_LEN
    assert result.endswith(".pdf")


def test_multiple_dots_keeps_last_as_extension():
    result = sanitise_filename("2024.01.15 - Invoice.pdf")
    assert result == "2024.01.15 - Invoice.pdf"


def test_leading_trailing_whitespace_stripped():
    result = sanitise_filename("  My Document.pdf  ")
    assert result == "My Document.pdf"


def test_consecutive_dashes_collapsed():
    result = sanitise_filename("file--name.pdf")
    assert result == "file-name.pdf"


def test_path_traversal_stripped():
    result = sanitise_filename("../../../etc/passwd.pdf")
    assert result == "passwd.pdf"


def test_space_dash_separator_preserved():
    """Separator pattern ' - ' must survive sanitisation unchanged."""
    name = "2024-01-15 - Vendor Name - Invoice.pdf"
    assert sanitise_filename(name) == name
