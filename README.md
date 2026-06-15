# llm-pdf-renamer

Connect a local LLM (via [Ollama](https://ollama.com)) to a folder of scanned PDFs and automatically rename them into a clean, consistent format:

```
YYYY-MM-DD - Vendor or Sender Name - Document Type.pdf
```

Everything runs locally — no data leaves your machine.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.12+ | 3.10+ works; 3.12 recommended for `str \| None` syntax |
| [Ollama](https://ollama.com) | Installed and running (`ollama serve`) |
| An Ollama model | e.g. `llama3.1` — see [Ollama library](https://ollama.com/library) |

### Pull a model

```powershell
ollama pull llama3.1
```

---

## Setup

### 1. Clone and enter the repo

```powershell
git clone https://github.com/yourname/llm-pdf-renamer.git
cd llm-pdf-renamer
```

### 2. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
# or on Mac/Linux:
# source .venv/bin/activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

---

## Configuration

Open `file_rename.py` and set the two constants at the top, or pass them as CLI flags:

| Constant | Default | Description |
|----------|---------|-------------|
| `FOLDER_PATH` | `C:\path\to\your\backed_up_pdfs` | Folder containing your PDFs |
| `MODEL_NAME` | `llama3.1` | Ollama model to use |

---

## Usage

> **Always run with `--dry-run` first** to preview what would be renamed before making changes.

```powershell
# Preview (no files are touched)
python file_rename.py --dry-run --folder "C:\Users\you\Documents\Scans"

# Run for real
python file_rename.py --folder "C:\Users\you\Documents\Scans"

# Use a different model
python file_rename.py --folder "C:\Users\you\Scans" --model mistral

# Verbose debug output
python file_rename.py --folder "C:\Users\you\Scans" --debug

# Save a log file for auditing
python file_rename.py --folder "C:\Users\you\Scans" --log-file rename.log
```

### All flags

```
--folder PATH     Path to your PDF folder (overrides FOLDER_PATH constant)
--model NAME      Ollama model name (default: llama3.1)
--dry-run         Preview renames without making any changes
--debug           Verbose debug output (LLM prompts, responses, etc.)
--log-file PATH   Write log output to a file as well as the console
```

---

## How it works

1. Scans the target folder for `*.pdf` files.
2. Extracts text from the first two pages of each PDF (via PyMuPDF).
3. Sends up to 2 000 characters to the local LLM with a prompt asking for a structured filename.
4. Sanitises the LLM response (removes illegal characters, path traversal, enforces length limits).
5. Renames the file, automatically handling name collisions with a numeric suffix.
6. Prints a summary of renamed / skipped / failed files.

---

## Tips

- **Back up your PDFs before running.** The script renames in-place.
- If a PDF contains only scanned images (no embedded text), it will be skipped. Consider running an OCR tool first (e.g. `ocrmypdf`).
- Larger models (e.g. `llama3.1:70b`) give better results on messy scans but are slower.
- Run `ollama serve` in a separate terminal before executing the script if Ollama is not already running as a service.
