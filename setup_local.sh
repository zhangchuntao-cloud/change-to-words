#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS="$ROOT/.deps"

# 优先使用 CTW_PYTHON；否则依次尝试 python3、python、py。
if [ -n "${CTW_PYTHON:-}" ]; then
  PYTHON_BIN="$CTW_PYTHON"
else
  PYTHON_BIN=""
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c "import sys" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "错误: 找不到可用的 Python，请安装 Python 3.9+ 或设置 CTW_PYTHON" >&2
  exit 1
fi

echo "使用解释器: $("$PYTHON_BIN" --version 2>&1)"
"$PYTHON_BIN" -m pip install --target "$DEPS" \
  "faster-whisper>=1.0,<1.2" \
  "requests>=2.28,<3" \
  "av>=11,<19" \
  "fastapi>=0.110,<1" \
  "uvicorn>=0.29,<1" \
  "python-multipart>=0.0.9,<1"
echo "完成。现在可以运行: ./ctw --help 或 ./ctw serve"
