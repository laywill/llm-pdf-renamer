"""
PDF batch renamer using a local Ollama LLM.

Usage:
    python file_rename.py                      # rename files in FOLDER_PATH
    python file_rename.py --dry-run            # preview renames without making changes
    python file_rename.py --log-file out.log   # also write logs to a file
    python file_rename.py --debug              # verbose debug output
"""

import argparse
import contextlib
import io
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf
import ollama
from PIL import Image

# ---------------------------------------------------------------------------
# CONFIGURATION — override with CLI flags where possible
# ---------------------------------------------------------------------------
FOLDER_PATH = r"C:\path\to\your\backed_up_pdfs"
MODEL_NAME = "gemma3:4b"
MAX_TEXT_CHARS = 2000   # chars sent to the LLM per document
MAX_FILENAME_LEN = 200  # characters, well under the 255-byte FS limit
OCR_MAX_PAGES = 2       # pages to OCR when no embedded text is found
OCR_DPI = 200           # render resolution for OCR; 200 DPI balances speed and accuracy

# Windows-illegal filename characters
_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def setup_logging(debug: bool = False, log_file: str | None = None) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    if not debug:
        # Silence httpx INFO logs ("HTTP Request: POST ...") emitted by the ollama client
        logging.getLogger("httpx").setLevel(logging.WARNING)


@contextlib.contextmanager
def _quiet_libs():
    """Redirect stdout/stderr FDs to devnull to silence C-extension library chatter.

    Flush Python buffers before restoring so any buffered output from the quiet
    period drains to devnull rather than leaking to the terminal after exit.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved: dict[int, int] = {}
    try:
        for fd in (1, 2):
            saved[fd] = os.dup(fd)
            os.dup2(devnull_fd, fd)
        os.close(devnull_fd)
        devnull_fd = -1
        yield
    finally:
        if devnull_fd != -1:
            os.close(devnull_fd)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        for fd, orig in saved.items():
            os.dup2(orig, fd)
            os.close(orig)


def _maybe_quiet() -> contextlib.AbstractContextManager:
    return contextlib.nullcontext() if log.isEnabledFor(logging.DEBUG) else _quiet_libs()


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitise_filename(name: str) -> str:
    """Strip illegal chars, path separators, and enforce length limits."""
    name = name.strip()
    # Remove any path-traversal attempts
    name = Path(name).name
    # Replace Windows-illegal characters with a dash
    name = _ILLEGAL_CHARS_RE.sub("-", name)
    # Collapse repeated spaces and repeated dashes independently so " - " is preserved
    name = re.sub(r" {2,}", " ", name)
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip(" -")
    # Enforce length (keep the .pdf extension)
    stem, sep, ext = name.rpartition(".")
    if sep:
        ext = f".{ext}"
    else:
        stem, ext = name, ".pdf"
    if len(stem) > MAX_FILENAME_LEN:
        stem = stem[:MAX_FILENAME_LEN].rstrip(" -")
    return f"{stem}{ext}"


def unique_path(path: Path) -> Path:
    """If *path* already exists, append _1, _2, … until a free slot is found."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Return text from the first two pages of a PDF, or an empty string on failure."""
    text_parts: list[str] = []
    try:
        with pymupdf.open(pdf_path) as doc:
            for page in doc[:2]:
                text_parts.append(str(page.get_text("text")))
        log.debug("Extracted %d chars from '%s'", sum(len(t) for t in text_parts), pdf_path.name)
    except Exception:
        log.exception("Failed to read PDF: %s", pdf_path)
    return "".join(text_parts).strip()


_paddle_ocr: Any = None


def _get_paddle_ocr() -> Any:
    """Lazy-initialize the PaddleOCR engine (models downloaded on first use, ~200 MB).

    Uses the onnxruntime backend, which works on Python 3.9+ including 3.13+
    where paddlepaddle has no wheels.
    """
    global _paddle_ocr
    if _paddle_ocr is None:
        from paddleocr import PaddleOCR  # type: ignore[import-untyped]  # noqa: PLC0415
        import logging as _logging  # noqa: PLC0415
        # paddlex/__init__.py calls setup_logging() on import, resetting its logger to INFO.
        # Set to ERROR *after* the import so our level isn't overridden.
        # Skip silencing in debug mode so the full paddlex output remains visible.
        if not log.isEnabledFor(logging.DEBUG):
            for _name in ("ppocr", "paddleocr", "paddlex", "paddle"):
                _logging.getLogger(_name).setLevel(_logging.ERROR)
        with _maybe_quiet():
            _paddle_ocr = PaddleOCR(
                use_textline_orientation=True,
                lang="en",
                engine="onnxruntime",
            )
    return _paddle_ocr


def ocr_pdf_pages(pdf_path: Path, max_pages: int = OCR_MAX_PAGES) -> str:
    """OCR the first *max_pages* pages of a PDF using PaddleOCR (onnxruntime backend).

    Renders each page to a pixmap via PyMuPDF, converts it to a BGR numpy
    array, and passes it to PaddleOCR.  Returns combined text or "" on any error.
    Each OCRResult exposes rec_texts: list[str], one entry per detected text line.
    """
    text_parts: list[str] = []
    try:
        engine = _get_paddle_ocr()
        with pymupdf.open(pdf_path) as doc:
            for page in doc[:max_pages]:
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                img_array = np.array(img)[:, :, ::-1]  # RGB → BGR (PaddleOCR convention)
                for ocr_result in engine.predict(img_array):
                    text_parts.extend(ocr_result.get("rec_texts") or [])
        log.debug("OCR extracted %d chars from '%s'", sum(len(t) for t in text_parts), pdf_path.name)
    except Exception:
        log.exception("OCR failed for '%s'", pdf_path.name)
    return " ".join(text_parts).strip()


def get_new_filename(pdf_text: str, current_name: str, model: str = MODEL_NAME) -> str | None:
    """Ask the local LLM to suggest a structured filename."""
    if not pdf_text:
        log.debug("No text to send to LLM for '%s'", current_name)
        return None

    prompt = (
        "Analyze the following text extracted from a document scan.\n"
        "Generate a clean, standardized filename based strictly on the document details.\n\n"
        "FORMAT REQUIREMENT:\n"
        "Your response must ONLY be the filename in this exact format: "
        "YYYY-MM-DD - [Vendor or Sender Name] - [Document Type].pdf\n"
        "Do not include any introductory text, markdown, or explanations. Only output the filename.\n\n"
        "DATE HANDLING:\n"
        "This document originates from the United Kingdom. All dates in the source text use "
        "UK format: DD/MM/YYYY (day first, then month, then year). "
        "For example, '03/06/2025' means the 3rd of June 2025, NOT March 6th. "
        "Convert the document date to ISO format YYYY-MM-DD in the filename.\n\n"
        "Example: 2026-03-15 - Barclays - Monthly Statement.pdf\n\n"
        "Document Text:\n"
        f"{pdf_text[:MAX_TEXT_CHARS]}"
    )

    try:
        log.debug("Sending %d chars to model '%s' for '%s'", len(prompt), model, current_name)
        response = ollama.generate(model=model, prompt=prompt)
        raw_response = response.response
        if raw_response is None:
            log.warning("LLM returned no response for '%s'", current_name)
            return None
        raw: str = raw_response.strip()
        log.debug("LLM raw response: %r", raw)

        # Strip accidental markdown / quotes
        cleaned = raw.replace("`", "").replace('"', "").replace("'", "").strip()
        if not cleaned:
            log.warning("LLM returned an empty response for '%s'", current_name)
            return None

        filename = sanitise_filename(cleaned)
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        return filename

    except Exception:
        log.exception("LLM call failed for '%s'", current_name)
        return None


# ---------------------------------------------------------------------------
# Main batch loop
# ---------------------------------------------------------------------------

def batch_rename_pdfs(
    folder: Path,
    dry_run: bool = False,
    model: str = MODEL_NAME,
    ocr_pages: int = OCR_MAX_PAGES,
) -> None:
    if not folder.exists():
        log.error("Folder does not exist: %s", folder)
        sys.exit(1)
    if not folder.is_dir():
        log.error("Path is not a directory: %s", folder)
        sys.exit(1)

    pdf_files = sorted(folder.glob("*.pdf"))
    if not pdf_files:
        log.warning("No PDF files found in %s", folder)
        return

    log.info("Found %d PDF(s) in %s", len(pdf_files), folder)
    if dry_run:
        log.info("DRY-RUN mode — no files will be renamed")

    stats = {"renamed": 0, "skipped": 0, "failed": 0}

    for pdf_path in pdf_files:
        log.info("Processing: %s", pdf_path.name)

        pdf_text = extract_text_from_pdf(pdf_path)
        if not pdf_text:
            log.info("  -> No embedded text found; attempting OCR…")
            pdf_text = ocr_pdf_pages(pdf_path, max_pages=ocr_pages)
        if not pdf_text:
            log.warning("  -> Skipped (no readable text found and OCR produced nothing)")
            stats["skipped"] += 1
            continue

        new_name = get_new_filename(pdf_text, pdf_path.name, model=model)
        if not new_name:
            log.warning("  -> Skipped (LLM could not determine a better name)")
            stats["skipped"] += 1
            continue

        if new_name == pdf_path.name:
            log.info("  -> Skipped (suggested name matches current name)")
            stats["skipped"] += 1
            continue

        target = unique_path(folder / new_name)
        if target.name != new_name:
            log.info("  -> Collision: renamed target to '%s' to avoid overwrite", target.name)

        if dry_run:
            log.info("  -> Would rename to: %s", target.name)
            stats["renamed"] += 1
        else:
            try:
                pdf_path.rename(target)
                log.info("  -> Renamed to: %s", target.name)
                stats["renamed"] += 1
            except OSError:
                log.exception("  -> Failed to rename '%s'", pdf_path.name)
                stats["failed"] += 1

    log.info(
        "\nDone. Renamed: %d  |  Skipped: %d  |  Failed: %d",
        stats["renamed"], stats["skipped"], stats["failed"],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-rename PDFs using a local Ollama LLM."
    )
    parser.add_argument(
        "--folder",
        default=FOLDER_PATH,
        help="Path to the folder containing PDFs (default: FOLDER_PATH constant)",
    )
    parser.add_argument(
        "--model",
        default=MODEL_NAME,
        help="Ollama model name (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview renames without making any changes",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging",
    )
    parser.add_argument(
        "--log-file",
        metavar="PATH",
        help="Optional path to write log output to a file",
    )
    parser.add_argument(
        "--ocr-pages",
        type=int,
        default=OCR_MAX_PAGES,
        metavar="N",
        help="Number of pages to OCR when no embedded text is found (default: %(default)s)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(debug=args.debug, log_file=args.log_file)

    batch_rename_pdfs(
        folder=Path(args.folder),
        dry_run=args.dry_run,
        model=args.model,
        ocr_pages=args.ocr_pages,
    )
