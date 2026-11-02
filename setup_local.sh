#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS="$ROOT/.deps"

# 默认使用 PATH 中的 python3；可用 CTW_PYTHON 指定其他解释器。
PYTHON_BIN="${CTW_PYTHON:-python3}"

echo "使用解释器: $("$PYTHON_BIN" --version 2>&1)"
"$PYTHON_BIN" -m pip install --target "$DEPS" \
  "faster-whisper>=1.0,<1.2" \
  "fastapi>=0.110,<1" \
  "uvicorn>=0.29,<1" \
  "python-multipart>=0.0.9,<1"
echo "完成。现在可以运行: ./ctw --help 或 ./ctw serve"
