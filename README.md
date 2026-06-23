# llm-pdf-renamer

Batch-rename PDF files using a local [Ollama](https://ollama.com) LLM. Extracts text from the first two pages of each PDF and asks the model to generate a standardised `YYYY-MM-DD - Vendor - Document Type.pdf` filename. For scanned (image-only) PDFs, the tool automatically falls back to [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) before passing the extracted text to the LLM.

## Hardware requirements

| Component                       | RAM        |
| ------------------------------- | ---------- |
| LLM model weights (`gemma3:4b`) | ~4 GB      |
| LLM context window              | ~2 GB      |
| PaddleOCR models + processing   | ~1 GB      |
| **Total recommended**           | **≥ 8 GB** |

For GPU acceleration, a CUDA-capable GPU with ≥ 6 GB VRAM will significantly speed up both OCR and LLM inference, but everything runs on CPU by default.

## Prerequisites

- **Python 3.9+** — Python 3.13 and 3.14 are fully supported via the `onnxruntime` backend.
  > **Important:** Do **not** install `paddlepaddle` or `paddlepaddle-gpu`. PaddleOCR 3.x uses
  > `onnxruntime` as its inference backend in this project. `paddlepaddle` has no wheels for
  > Python 3.13+ and would cause import errors.

- [Ollama](https://ollama.com) running locally with your chosen model pulled, e.g.:

  ```shell
  ollama pull gemma3:4b
  ```

### Ollama context window

Ollama defaults to a small context window that may truncate long documents. Set a sensible minimum before starting the server:

```shell
# Linux / macOS (systemd or launchd unit — set in the environment block)
OLLAMA_CONTEXT_LENGTH=4096 ollama serve

# Windows (PowerShell — set before launching Ollama)
$env:OLLAMA_CONTEXT_LENGTH = "4096"
ollama serve
```

A value of `4096` tokens covers most invoices and statements. Increase to `8192` if you process long multi-page documents.

## Installation

Create and activate a virtual environment, then install dependencies.

**Production:**

```shell
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS / Linux

pip install -e .
```

**Development (includes pytest and pre-commit):**

```shell
pip install -e ".[dev,test]"
```

> **Note:** PaddleOCR 3.x downloads ONNX model files (~200 MB total across 5 models) to
> `~/.paddlex/official_models/` on first use. Ensure you have an internet connection the first
> time you process a scanned PDF. Subsequent runs use the cached models and start faster.

## Usage

```powershell
python file_rename.py --folder C:\path\to\pdfs
python file_rename.py --folder C:\path\to\pdfs --dry-run
python file_rename.py --folder C:\path\to\pdfs --model gemma3:4b --debug
python file_rename.py --folder C:\path\to\pdfs --log-file rename.log
python file_rename.py --folder C:\path\to\pdfs --ocr-pages 3
```

| Flag              | Default                | Description                                 |
| ----------------- | ---------------------- | ------------------------------------------- |
| `--folder`        | `FOLDER_PATH` constant | Path to the folder containing PDFs          |
| `--model`         | `gemma3:4b`            | Ollama model name                           |
| `--dry-run`       | off                    | Preview renames without making any changes  |
| `--debug`         | off                    | Verbose debug logging                       |
| `--log-file PATH` | none                   | Also write log output to a file             |
| `--ocr-pages N`   | `2`                    | Pages to OCR when no embedded text is found |

## How it works

1. **Text extraction** — PyMuPDF reads embedded text from the first two pages. Fast and lossless.
2. **OCR fallback** — If no embedded text is found (e.g. a scanned document), PaddleOCR renders each page to a high-resolution image and extracts text. PaddleOCR handles skewed/rotated pages via its built-in angle classifier.
3. **LLM naming** — The extracted text is sent to your local Ollama model, which returns a standardised filename in `YYYY-MM-DD - Vendor - Document Type.pdf` format.

### Alternative: Ollama vision model (last resort)

For documents where PaddleOCR also struggles (e.g. handwritten notes, very poor scans), a vision-capable Ollama model such as `qwen2.5vl:7b` can read page images directly. This approach is significantly slower (several minutes per page) and requires an additional ~6 GB of RAM and disk space, but produces excellent results on complex or degraded documents. It is not automated by this tool but can be used manually.

## Running tests

```shell
pytest
```
