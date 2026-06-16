"""Tests for file_rename.py — covers unique_path, setup_logging,
extract_text_from_pdf, get_new_filename, batch_rename_pdfs, parse_args."""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_rename import (
    batch_rename_pdfs,
    extract_text_from_pdf,
    get_new_filename,
    parse_args,
    setup_logging,
    unique_path,
)


# ---------------------------------------------------------------------------
# unique_path
# ---------------------------------------------------------------------------


class TestUniquePath:
    def test_nonexistent_path_returned_unchanged(self, tmp_path):
        p = tmp_path / "file.pdf"
        assert unique_path(p) == p

    def test_existing_path_gets_counter(self, tmp_path):
        p = tmp_path / "file.pdf"
        p.touch()
        assert unique_path(p) == tmp_path / "file_1.pdf"

    def test_multiple_collisions_increment_counter(self, tmp_path):
        p = tmp_path / "file.pdf"
        p.touch()
        (tmp_path / "file_1.pdf").touch()
        assert unique_path(p) == tmp_path / "file_2.pdf"


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_debug_mode_does_not_raise(self):
        setup_logging(debug=True)

    def test_info_mode_does_not_raise(self):
        setup_logging(debug=False)

    def test_log_file_does_not_raise(self, tmp_path):
        setup_logging(log_file=str(tmp_path / "run.log"))


# ---------------------------------------------------------------------------
# extract_text_from_pdf
# ---------------------------------------------------------------------------


def _make_mock_doc(pages_text: list[str]) -> MagicMock:
    pages = []
    for text in pages_text:
        page = MagicMock()
        page.get_text.return_value = text
        pages.append(page)
    doc = MagicMock()
    doc.__getitem__ = MagicMock(return_value=pages)
    return doc


class TestExtractTextFromPdf:
    def test_returns_text_from_pages(self, tmp_path):
        doc = _make_mock_doc(["Hello ", "World"])
        with patch("pymupdf.open") as mock_open:
            mock_open.return_value.__enter__.return_value = doc
            result = extract_text_from_pdf(tmp_path / "doc.pdf")
        assert "Hello" in result and "World" in result

    def test_strips_surrounding_whitespace(self, tmp_path):
        doc = _make_mock_doc(["  text  "])
        with patch("pymupdf.open") as mock_open:
            mock_open.return_value.__enter__.return_value = doc
            result = extract_text_from_pdf(tmp_path / "doc.pdf")
        assert result == "text"

    def test_returns_empty_string_on_exception(self, tmp_path):
        with patch("pymupdf.open", side_effect=Exception("corrupt")):
            result = extract_text_from_pdf(tmp_path / "bad.pdf")
        assert result == ""

    def test_returns_empty_string_for_blank_pages(self, tmp_path):
        doc = _make_mock_doc(["   ", "  "])
        with patch("pymupdf.open") as mock_open:
            mock_open.return_value.__enter__.return_value = doc
            result = extract_text_from_pdf(tmp_path / "blank.pdf")
        assert result == ""


# ---------------------------------------------------------------------------
# get_new_filename
# ---------------------------------------------------------------------------


def _llm_response(text: str) -> MagicMock:
    r = MagicMock()
    r.response = text
    return r


class TestGetNewFilename:
    def test_returns_none_for_empty_text(self):
        assert get_new_filename("", "doc.pdf") is None

    def test_returns_sanitised_filename(self):
        with patch("ollama.generate", return_value=_llm_response("2024-01-15 - Chase Bank - Statement.pdf")):
            result = get_new_filename("some text", "doc.pdf")
        assert result == "2024-01-15 - Chase Bank - Statement.pdf"

    def test_appends_pdf_extension_when_missing(self):
        with patch("ollama.generate", return_value=_llm_response("2024-01-15 - Chase Bank - Statement")):
            result = get_new_filename("some text", "doc.pdf")
        assert result is not None and result.endswith(".pdf")

    def test_strips_markdown_backticks(self):
        with patch("ollama.generate", return_value=_llm_response("`2024-01-15 - Invoice.pdf`")):
            result = get_new_filename("some text", "doc.pdf")
        assert result is not None and "`" not in result

    def test_strips_double_quotes(self):
        with patch("ollama.generate", return_value=_llm_response('"2024-01-15 - Invoice.pdf"')):
            result = get_new_filename("some text", "doc.pdf")
        assert result is not None and '"' not in result

    def test_strips_single_quotes(self):
        with patch("ollama.generate", return_value=_llm_response("'2024-01-15 - Invoice.pdf'")):
            result = get_new_filename("some text", "doc.pdf")
        assert result is not None and "'" not in result

    def test_returns_none_for_empty_llm_response(self):
        with patch("ollama.generate", return_value=_llm_response("   ")):
            result = get_new_filename("some text", "doc.pdf")
        assert result is None

    def test_returns_none_on_ollama_exception(self):
        with patch("ollama.generate", side_effect=Exception("connection refused")):
            result = get_new_filename("some text", "doc.pdf")
        assert result is None

    def test_text_truncated_to_max_chars(self):
        long_text = "x" * 5000
        captured_prompt: list[str] = []

        def capture(model, prompt):
            captured_prompt.append(prompt)
            return _llm_response("2024-01-15 - Test.pdf")

        with patch("ollama.generate", side_effect=capture):
            get_new_filename(long_text, "doc.pdf")

        from file_rename import MAX_TEXT_CHARS
        assert "x" * MAX_TEXT_CHARS in captured_prompt[0]
        assert "x" * (MAX_TEXT_CHARS + 1) not in captured_prompt[0]


# ---------------------------------------------------------------------------
# batch_rename_pdfs
# ---------------------------------------------------------------------------


class TestBatchRenamePdfs:
    def test_exits_if_folder_missing(self, tmp_path):
        with pytest.raises(SystemExit):
            batch_rename_pdfs(tmp_path / "nonexistent")

    def test_exits_if_path_is_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        with pytest.raises(SystemExit):
            batch_rename_pdfs(f)

    def test_no_error_when_no_pdfs(self, tmp_path):
        batch_rename_pdfs(tmp_path)  # should return silently

    def test_skips_pdf_with_no_text(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with patch("file_rename.extract_text_from_pdf", return_value=""):
            batch_rename_pdfs(tmp_path)
        assert pdf.exists()

    def test_skips_pdf_when_llm_returns_none(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with patch("file_rename.extract_text_from_pdf", return_value="text"), \
             patch("file_rename.get_new_filename", return_value=None):
            batch_rename_pdfs(tmp_path)
        assert pdf.exists()

    def test_skips_pdf_when_suggested_name_is_same(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with patch("file_rename.extract_text_from_pdf", return_value="text"), \
             patch("file_rename.get_new_filename", return_value="scan.pdf"):
            batch_rename_pdfs(tmp_path)
        assert pdf.exists()

    def test_renames_pdf(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        new_name = "2024-01-15 - Chase Bank - Statement.pdf"
        with patch("file_rename.extract_text_from_pdf", return_value="text"), \
             patch("file_rename.get_new_filename", return_value=new_name):
            batch_rename_pdfs(tmp_path)
        assert (tmp_path / new_name).exists()
        assert not pdf.exists()

    def test_dry_run_does_not_rename(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        new_name = "2024-01-15 - Chase Bank - Statement.pdf"
        with patch("file_rename.extract_text_from_pdf", return_value="text"), \
             patch("file_rename.get_new_filename", return_value=new_name):
            batch_rename_pdfs(tmp_path, dry_run=True)
        assert pdf.exists()
        assert not (tmp_path / new_name).exists()

    def test_handles_rename_collision(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        new_name = "2024-01-15 - Chase Bank - Statement.pdf"
        (tmp_path / new_name).touch()
        # glob returns sorted: the collision file comes first (alpha), skip it;
        # then scan.pdf is renamed to the _1 variant
        with patch("file_rename.extract_text_from_pdf", side_effect=["", "text"]), \
             patch("file_rename.get_new_filename", return_value=new_name):
            batch_rename_pdfs(tmp_path)
        assert (tmp_path / "2024-01-15 - Chase Bank - Statement_1.pdf").exists()

    def test_handles_oserror_on_rename(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with patch("file_rename.extract_text_from_pdf", return_value="text"), \
             patch("file_rename.get_new_filename", return_value="new-name.pdf"), \
             patch.object(Path, "rename", side_effect=OSError("permission denied")):
            batch_rename_pdfs(tmp_path)  # must not raise


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults(self):
        with patch("sys.argv", ["prog"]):
            args = parse_args()
        assert args.dry_run is False
        assert args.debug is False
        assert args.log_file is None

    def test_dry_run_flag(self):
        with patch("sys.argv", ["prog", "--dry-run"]):
            args = parse_args()
        assert args.dry_run is True

    def test_debug_flag(self):
        with patch("sys.argv", ["prog", "--debug"]):
            args = parse_args()
        assert args.debug is True

    def test_folder_arg(self, tmp_path):
        with patch("sys.argv", ["prog", "--folder", str(tmp_path)]):
            args = parse_args()
        assert args.folder == str(tmp_path)

    def test_model_arg(self):
        with patch("sys.argv", ["prog", "--model", "mistral"]):
            args = parse_args()
        assert args.model == "mistral"

    def test_log_file_arg(self, tmp_path):
        log = str(tmp_path / "out.log")
        with patch("sys.argv", ["prog", "--log-file", log]):
            args = parse_args()
        assert args.log_file == log
