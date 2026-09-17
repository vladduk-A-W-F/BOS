#!/usr/bin/env bash
set -euo pipefail
export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${BOS_PYTHON:-python3}" "$script_dir/verify.py" "$@"
