"""Tests for file_rename.py — covers unique_path, setup_logging,
extract_text_from_pdf, ocr_pdf_pages, get_new_filename, batch_rename_pdfs,
parse_args."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from file_rename import (
    OCR_MAX_PAGES,
    batch_rename_pdfs,
    extract_text_from_pdf,
    get_new_filename,
    ocr_pdf_pages,
    parse_args,
    setup_logging,
    unique_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_blank_png(width: int = 10, height: int = 10) -> bytes:
    """Return minimal valid PNG bytes (white image) for test pixmap mocks."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _make_mock_paddle_result(texts: list[str]) -> list:
    """Build a PaddleOCR 3.x-style result: list of OCRResult-like dicts.

    PaddleOCR 3.x returns List[OCRResult] where OCRResult is a dict-like object
    with at minimum a 'rec_texts' key containing a list of recognised strings.
    """
    return [{"rec_texts": texts, "rec_scores": [0.99] * len(texts)}]


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
# ocr_pdf_pages
# ---------------------------------------------------------------------------


def _make_mock_ocr_doc(pages: int = 1) -> MagicMock:
    """Build a mock PyMuPDF doc whose pages return blank PNG pixmaps.

    Slice-aware: doc[:N] returns only the first N mock pages.
    """
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = _make_blank_png()

    mock_pages = []
    for _ in range(pages):
        mock_page = MagicMock()
        mock_page.get_pixmap.return_value = mock_pix
        mock_pages.append(mock_page)

    doc = MagicMock()
    doc.__getitem__ = MagicMock(side_effect=lambda s: mock_pages[s])
    return doc


class TestOcrPdfPages:
    def _patch_ocr(self, result):
        """Context manager that stubs PaddleOCR with *result*."""
        mock_engine = MagicMock()
        mock_engine.predict.return_value = result
        return patch("file_rename._get_paddle_ocr", return_value=mock_engine)

    def test_returns_text_from_single_page(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        doc = _make_mock_ocr_doc()
        with (
            self._patch_ocr(_make_mock_paddle_result(["Invoice", "Total 50.00"])),
            patch("pymupdf.open") as mock_open,
        ):
            mock_open.return_value.__enter__.return_value = doc
            result = ocr_pdf_pages(pdf)
        assert "Invoice" in result and "Total 50.00" in result

    def test_returns_empty_string_when_no_text_detected(self, tmp_path):
        """An empty OCR result list (no detections at all) must return ''."""
        pdf = tmp_path / "blank.pdf"
        pdf.touch()
        doc = _make_mock_ocr_doc()
        with self._patch_ocr([]), patch("pymupdf.open") as mock_open:
            mock_open.return_value.__enter__.return_value = doc
            result = ocr_pdf_pages(pdf)
        assert result == ""

    def test_returns_empty_string_on_pymupdf_exception(self, tmp_path):
        pdf = tmp_path / "bad.pdf"
        pdf.touch()
        mock_engine = MagicMock()
        with (
            patch("file_rename._get_paddle_ocr", return_value=mock_engine),
            patch("pymupdf.open", side_effect=Exception("corrupt pdf")),
        ):
            result = ocr_pdf_pages(pdf)
        assert result == ""

    def test_returns_empty_string_on_ocr_engine_exception(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        doc = _make_mock_ocr_doc()
        mock_engine = MagicMock()
        mock_engine.predict.side_effect = Exception("OCR error")
        with (
            patch("file_rename._get_paddle_ocr", return_value=mock_engine),
            patch("pymupdf.open") as mock_open,
        ):
            mock_open.return_value.__enter__.return_value = doc
            result = ocr_pdf_pages(pdf)
        assert result == ""

    def test_respects_max_pages(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        doc = _make_mock_ocr_doc(pages=3)
        mock_engine = MagicMock()
        mock_engine.predict.return_value = _make_mock_paddle_result(["text"])
        with (
            patch("file_rename._get_paddle_ocr", return_value=mock_engine),
            patch("pymupdf.open") as mock_open,
        ):
            mock_open.return_value.__enter__.return_value = doc
            ocr_pdf_pages(pdf, max_pages=1)
        # doc sliced to [:1] — the mock returns [mock_page]*3 but iterates only 1
        assert mock_engine.predict.call_count == 1

    def test_default_max_pages_matches_constant(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        doc = _make_mock_ocr_doc(pages=OCR_MAX_PAGES)
        mock_engine = MagicMock()
        mock_engine.predict.return_value = _make_mock_paddle_result(["text"])
        with (
            patch("file_rename._get_paddle_ocr", return_value=mock_engine),
            patch("pymupdf.open") as mock_open,
        ):
            mock_open.return_value.__enter__.return_value = doc
            ocr_pdf_pages(pdf)
        assert mock_engine.predict.call_count == OCR_MAX_PAGES

    def test_returns_empty_string_when_rec_texts_empty(self, tmp_path):
        """An OCRResult with an empty rec_texts list must return ''."""
        pdf = tmp_path / "blank.pdf"
        pdf.touch()
        doc = _make_mock_ocr_doc()
        with (
            self._patch_ocr([{"rec_texts": [], "rec_scores": []}]),
            patch("pymupdf.open") as mock_open,
        ):
            mock_open.return_value.__enter__.return_value = doc
            result = ocr_pdf_pages(pdf)
        assert result == ""

    def test_get_paddle_ocr_singleton(self):
        """_get_paddle_ocr returns the same object on repeated calls."""
        import file_rename

        orig = file_rename._paddle_ocr
        try:
            file_rename._paddle_ocr = None
            mock_cls = MagicMock(return_value=MagicMock())
            with patch.dict(
                "sys.modules", {"paddleocr": MagicMock(PaddleOCR=mock_cls)}
            ):
                # Force re-import inside _get_paddle_ocr
                engine1 = file_rename._get_paddle_ocr()
                engine2 = file_rename._get_paddle_ocr()
            assert engine1 is engine2
            assert mock_cls.call_count == 1
        finally:
            file_rename._paddle_ocr = orig


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
        with patch(
            "ollama.generate",
            return_value=_llm_response("2024-01-15 - Chase Bank - Statement.pdf"),
        ):
            result = get_new_filename("some text", "doc.pdf")
        assert result == "2024-01-15 - Chase Bank - Statement.pdf"

    def test_appends_pdf_extension_when_missing(self):
        with patch(
            "ollama.generate",
            return_value=_llm_response("2024-01-15 - Chase Bank - Statement"),
        ):
            result = get_new_filename("some text", "doc.pdf")
        assert result is not None and result.endswith(".pdf")

    def test_strips_markdown_backticks(self):
        with patch(
            "ollama.generate", return_value=_llm_response("`2024-01-15 - Invoice.pdf`")
        ):
            result = get_new_filename("some text", "doc.pdf")
        assert result is not None and "`" not in result

    def test_strips_double_quotes(self):
        with patch(
            "ollama.generate", return_value=_llm_response('"2024-01-15 - Invoice.pdf"')
        ):
            result = get_new_filename("some text", "doc.pdf")
        assert result is not None and '"' not in result

    def test_strips_single_quotes(self):
        with patch(
            "ollama.generate", return_value=_llm_response("'2024-01-15 - Invoice.pdf'")
        ):
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

        def capture(_model, prompt):
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

    def test_skips_pdf_when_no_text_and_ocr_also_empty(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with (
            patch("file_rename.extract_text_from_pdf", return_value=""),
            patch("file_rename.ocr_pdf_pages", return_value=""),
        ):
            batch_rename_pdfs(tmp_path)
        assert pdf.exists()

    def test_renames_pdf_when_ocr_finds_text(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        new_name = "2024-06-01 - HMRC - Tax Return.pdf"
        with (
            patch("file_rename.extract_text_from_pdf", return_value=""),
            patch("file_rename.ocr_pdf_pages", return_value="some ocr text"),
            patch("file_rename.get_new_filename", return_value=new_name),
        ):
            batch_rename_pdfs(tmp_path)
        assert (tmp_path / new_name).exists()
        assert not pdf.exists()

    def test_ocr_called_only_when_extract_returns_empty(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with (
            patch("file_rename.extract_text_from_pdf", return_value="real text"),
            patch("file_rename.ocr_pdf_pages") as mock_ocr,
            patch("file_rename.get_new_filename", return_value="new.pdf"),
        ):
            batch_rename_pdfs(tmp_path)
        mock_ocr.assert_not_called()

    def test_ocr_called_when_extract_returns_empty(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with (
            patch("file_rename.extract_text_from_pdf", return_value=""),
            patch("file_rename.ocr_pdf_pages", return_value="") as mock_ocr,
        ):
            batch_rename_pdfs(tmp_path)
        mock_ocr.assert_called_once()

    def test_skips_pdf_with_no_text(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with (
            patch("file_rename.extract_text_from_pdf", return_value=""),
            patch("file_rename.ocr_pdf_pages", return_value=""),
        ):
            batch_rename_pdfs(tmp_path)
        assert pdf.exists()

    def test_skips_pdf_when_llm_returns_none(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with (
            patch("file_rename.extract_text_from_pdf", return_value="text"),
            patch("file_rename.get_new_filename", return_value=None),
        ):
            batch_rename_pdfs(tmp_path)
        assert pdf.exists()

    def test_skips_pdf_when_suggested_name_is_same(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with (
            patch("file_rename.extract_text_from_pdf", return_value="text"),
            patch("file_rename.get_new_filename", return_value="scan.pdf"),
        ):
            batch_rename_pdfs(tmp_path)
        assert pdf.exists()

    def test_renames_pdf(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        new_name = "2024-01-15 - Chase Bank - Statement.pdf"
        with (
            patch("file_rename.extract_text_from_pdf", return_value="text"),
            patch("file_rename.get_new_filename", return_value=new_name),
        ):
            batch_rename_pdfs(tmp_path)
        assert (tmp_path / new_name).exists()
        assert not pdf.exists()

    def test_dry_run_does_not_rename(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        new_name = "2024-01-15 - Chase Bank - Statement.pdf"
        with (
            patch("file_rename.extract_text_from_pdf", return_value="text"),
            patch("file_rename.get_new_filename", return_value=new_name),
        ):
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
        with (
            patch("file_rename.extract_text_from_pdf", side_effect=["", "text"]),
            patch("file_rename.get_new_filename", return_value=new_name),
        ):
            batch_rename_pdfs(tmp_path)
        assert (tmp_path / "2024-01-15 - Chase Bank - Statement_1.pdf").exists()

    def test_handles_oserror_on_rename(self, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.touch()
        with (
            patch("file_rename.extract_text_from_pdf", return_value="text"),
            patch("file_rename.get_new_filename", return_value="new-name.pdf"),
            patch.object(Path, "rename", side_effect=OSError("permission denied")),
        ):
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

    def test_ocr_pages_default(self):
        with patch("sys.argv", ["prog"]):
            args = parse_args()
        assert args.ocr_pages == OCR_MAX_PAGES

    def test_ocr_pages_arg(self):
        with patch("sys.argv", ["prog", "--ocr-pages", "5"]):
            args = parse_args()
        assert args.ocr_pages == 5
