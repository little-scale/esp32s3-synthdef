#!/bin/bash
# Build only; flash the reviewed image through Studio's exact-board installer.
set -euo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^(build|size|reconfigure)$ ]]; then
    echo 'Usage: bash host/xiao_native16.sh {build|size|reconfigure}' >&2
    exit 2
fi
project_root="$(cd "$(dirname "$0")/.." && pwd)"
export SYNTHDEF_BOARD=xiao
export IDF_COMPONENT_MANAGER=0
export SYNTHDEF_BUILD_DIR="${SYNTHDEF_BUILD_DIR:-build-xiao-native16}"
exec bash "$project_root/host/idf.sh" -D IDF_TARGET=esp32s3 \
    -D "SDKCONFIG=$project_root/build/host/xiao-native16-sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$project_root/host/xiao.defaults;$project_root/host/xiao_native16.defaults" "$@"
