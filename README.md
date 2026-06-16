# llm-pdf-renamer

Batch-rename PDF files using a local [Ollama](https://ollama.com) LLM. Extracts text from the first two pages of each PDF and asks the model to generate a standardised `YYYY-MM-DD - Vendor - Document Type.pdf` filename.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running locally with your chosen model pulled, e.g.:

  ```shell
  ollama pull llama3.1
  ```

## Installation

Create and activate a virtual environment, then install dependencies.

**Production:**

```shell
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

**Development (includes pytest):**

```shell
pip install -r requirements-dev.txt
```

## Usage

```powershell
python file_rename.py --folder C:\path\to\pdfs
python file_rename.py --folder C:\path\to\pdfs --dry-run
python file_rename.py --folder C:\path\to\pdfs --model llama3.2 --debug
python file_rename.py --folder C:\path\to\pdfs --log-file rename.log
```

| Flag | Default | Description |
|------|---------|-------------|
| `--folder` | `FOLDER_PATH` constant | Path to the folder containing PDFs |
| `--model` | `llama3.1` | Ollama model name |
| `--dry-run` | off | Preview renames without making any changes |
| `--debug` | off | Verbose debug logging |
| `--log-file PATH` | none | Also write log output to a file |

## Running tests

```shell
pytest
```
