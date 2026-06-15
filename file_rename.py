"""
PDF batch renamer using a local Ollama LLM.

Usage:
    python file_rename.py                      # rename files in FOLDER_PATH
    python file_rename.py --dry-run            # preview renames without making changes
    python file_rename.py --log-file out.log   # also write logs to a file
    python file_rename.py --debug              # verbose debug output
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import ollama

# ---------------------------------------------------------------------------
# CONFIGURATION — override with CLI flags where possible
# ---------------------------------------------------------------------------
FOLDER_PATH = r"C:\path\to\your\backed_up_pdfs"
MODEL_NAME = "llama3.1"
MAX_TEXT_CHARS = 2000   # chars sent to the LLM per document
MAX_FILENAME_LEN = 200  # characters, well under the 255-byte FS limit

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
    # Collapse repeated dashes/spaces
    name = re.sub(r"[-\s]{2,}", " ", name).strip(" -")
    # Enforce length (keep the .pdf extension)
    stem, _, ext = name.rpartition(".")
    ext = f".{ext}" if ext else ".pdf"
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
        with fitz.open(str(pdf_path)) as doc:
            for page in doc[:2]:
                text_parts.append(page.get_text())
        log.debug("Extracted %d chars from '%s'", sum(len(t) for t in text_parts), pdf_path.name)
    except Exception:
        log.exception("Failed to read PDF: %s", pdf_path)
    return "".join(text_parts).strip()


def get_new_filename(pdf_text: str, current_name: str) -> str | None:
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
        "Example: 2026-03-15 - Chase Bank - Monthly Statement.pdf\n\n"
        "Document Text:\n"
        f"{pdf_text[:MAX_TEXT_CHARS]}"
    )

    try:
        log.debug("Sending %d chars to model '%s' for '%s'", len(prompt), MODEL_NAME, current_name)
        response = ollama.generate(model=MODEL_NAME, prompt=prompt)
        raw: str = response["response"].strip()
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

def batch_rename_pdfs(folder: Path, dry_run: bool = False) -> None:
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
            log.warning("  -> Skipped (no readable text found)")
            stats["skipped"] += 1
            continue

        new_name = get_new_filename(pdf_text, pdf_path.name)
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(debug=args.debug, log_file=args.log_file)

    # Allow CLI overrides of module-level config
    MODEL_NAME = args.model

    batch_rename_pdfs(folder=Path(args.folder), dry_run=args.dry_run)
