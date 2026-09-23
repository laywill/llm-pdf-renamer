# Devcontainer

A container for **working on** `llm-pdf-renamer`: running the test suite, the
linters and the pre-commit hooks against a fixed Python, without needing
Python installed on the host.

It is not a way to *use* the tool. Renaming real documents means reaching
folders on your own machine and an Ollama server on your own machine, and
both are easier natively. Install the project locally for that.

## What it provides

- Base image: `mcr.microsoft.com/devcontainers/python:3.10-bookworm`.
- `postCreateCommand` installs the project with its dev/test extras
  (`pip install -e ".[dev,test]"`) and registers the pre-commit hooks.
- VS Code extensions: Python, Pylance, Black formatter, isort, EditorConfig.

The test suite needs nothing external: `tests/` patches `pymupdf.open`,
`ollama.generate` and `_get_paddle_ocr`, so `pytest` passes in a fresh
container with no Ollama server running and no model download.

## No virtualenv inside the container

The container is the isolation, so the project installs straight into the
image's Python rather than into a nested `.venv`.

The image's `site-packages` is root-owned, so `pip` performs a *user* install
into `/home/vscode/.local`. That directory's `bin` is on `PATH` in login
shells but not in the non-login shell that runs `postCreateCommand`, so
`remoteEnv` adds it explicitly and the hooks are registered with
`python -m pre_commit install` rather than the `pre-commit` entry point.

`remoteEnv` *prepends* that directory rather than appending it. The base
image ships its own pipx-installed `pytest`, `black` and `flake8` in
`/usr/local/py-utils/bin`, which would otherwise shadow the versions this
project pins in `pyproject.toml`. Note that `black`, `isort` and `flake8`
are not project dependencies at all -- they are pinned in
`.pre-commit-config.yaml` and run through `pre-commit run`, so a bare
`black` in the terminal is the image's copy and may not match.

The repo's `.venv` convention (see [CLAUDE.md](../CLAUDE.md)) is for native
local development. If you have a `.venv` in the repo root it stays visible
through the bind mount but goes unused -- `python.defaultInterpreterPath`
pins the container's interpreter to the system one. That setting lives in
`devcontainer.json`, so it applies only inside the container and does not
disturb VS Code's `.venv` auto-discovery when you work on the repo natively.

## Python version

Pinned to **3.10**, the `requires-python` floor in `pyproject.toml`. CI runs
the matrix 3.10 through 3.14; developing on the floor means an accidental use
of a newer standard-library addition (`itertools.batched`, added in 3.12, for
instance) fails locally rather than in CI. This fixes only the *container's*
interpreter.

Per [CLAUDE.md](../CLAUDE.md), PaddleOCR here runs on the `onnxruntime`
backend only. Do not add `paddlepaddle` / `paddlepaddle-gpu` to the image or
the project -- `paddlepaddle` has no wheels for Python 3.13+ and would break
the import.

## PaddleOCR models are not pre-warmed

PaddleOCR downloads ~200 MB of ONNX models the first time OCR actually runs
(`_get_paddle_ocr()` in `file_rename.py`). This image does not fetch them at
build time: that would make image builds depend on an outbound network call,
make every rebuild slower, and pay a cost most sessions never incur. The test
suite never reaches that code path, so it only matters if you run the tool
against a real scanned PDF inside the container.

## Optional: reaching Ollama on the host

Only needed for a manual end-to-end check -- the test suite does not use it.
Ollama is expected to run on your **host**, with the model referenced by
`MODEL_NAME` in `file_rename.py` (default `gemma3:4b`) already pulled.

- `runArgs` adds `--add-host=host.docker.internal:host-gateway`, so
  `host.docker.internal` resolves to the host on Linux Docker Engine 20.10+
  too. Docker Desktop on macOS/Windows already provides this.
- `containerEnv` sets `OLLAMA_HOST=http://host.docker.internal:11434`, which
  the `ollama` Python client reads directly, so no code changes are needed.

If your host's Ollama is bound to `127.0.0.1` only (the default), it may not
accept connections from the container -- on Linux you may need `OLLAMA_HOST=0.0.0.0`
set for the Ollama *server* itself. See the
[Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.md) for
platform-specific networking notes.
