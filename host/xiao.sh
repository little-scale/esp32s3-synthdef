#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
export SYNTHDEF_BOARD=xiao
export IDF_COMPONENT_MANAGER=0
export SYNTHDEF_BUILD_DIR="${SYNTHDEF_BUILD_DIR:-build-xiao}"
exec "$project_root/host/idf.sh" -D IDF_TARGET=esp32s3 \
    -D "SDKCONFIG=$project_root/build/host/xiao-sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$project_root/host/xiao.defaults" "$@"
