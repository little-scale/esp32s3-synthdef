#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
export IDF_PATH="${IDF_PATH:-$HOME/esp/esp-idf}"
# Prefer an explicitly selected environment; otherwise use an existing IDF 5.5 environment.
if [[ -z "${IDF_PYTHON_ENV_PATH:-}" ]]; then
    for candidate_env in "$HOME"/.espressif/python_env/idf5.5_py*_env; do
        if [[ -x "$candidate_env/bin/python" ]]; then export IDF_PYTHON_ENV_PATH="$candidate_env"; break; fi
    done
fi
if [[ -n "${IDF_PYTHON_ENV_PATH:-}" ]]; then export PATH="$IDF_PYTHON_ENV_PATH/bin:$PATH"; fi
source "$IDF_PATH/export.sh" >/dev/null
cd "${SYNTHDEF_PROJECT_DIR:-$project_root/firmware}"
exec idf.py -B "${SYNTHDEF_BUILD_DIR:-build-esp32s3}" "$@"
