#!/usr/bin/env bash
set -euo pipefail

# 统一 pytest 入口，优先选择与已安装 wheel 架构一致的解释器。
# 这样可以避免 Apple Silicon 上默认 x86_64 解释器误加载 arm64 扩展导致的 ImportError。

PYTHON_CMD=()

pick_python() {
  # 允许调用方显式覆盖解释器，便于 CI 或特殊环境复用同一入口。
  if [[ -n "${VELARIS_TEST_PYTHON:-}" ]]; then
    read -r -a PYTHON_CMD <<<"${VELARIS_TEST_PYTHON}"
    return 0
  fi

  if [[ "$(uname -s)" == "Darwin" ]] && command -v arch >/dev/null 2>&1; then
    if [[ -x ".venv/bin/python" ]] && arch -arm64 .venv/bin/python -c 'import pytest, pydantic' >/dev/null 2>&1; then
      PYTHON_CMD=(arch -arm64 .venv/bin/python)
      return 0
    fi

    if arch -arm64 python3 -c 'import pytest, pydantic' >/dev/null 2>&1; then
      PYTHON_CMD=(arch -arm64 python3)
      return 0
    fi
  fi

  if [[ -x ".venv/bin/python" ]] && .venv/bin/python -c 'import pytest, pydantic' >/dev/null 2>&1; then
    PYTHON_CMD=(.venv/bin/python)
    return 0
  fi

  if python3 -c 'import pytest, pydantic' >/dev/null 2>&1; then
    PYTHON_CMD=(python3)
    return 0
  fi

  echo "未找到可用的 Python 测试解释器；请先准备依赖，或设置 VELARIS_TEST_PYTHON 覆盖默认入口。" >&2
  exit 1
}

pick_python
echo "[velaris] pytest interpreter: ${PYTHON_CMD[*]}" >&2
"${PYTHON_CMD[@]}" -m pytest "$@"
