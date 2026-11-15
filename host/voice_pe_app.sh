#!/bin/bash
# Shared production application. Separate from the build-only commissioning probe.
set -euo pipefail
# The stock bootloader/NVS must be preserved during this experimental port.
# Use the reviewed same-unit migration helper, never idf.py flash.
if [[ $# -ne 1 || ! "$1" =~ ^(build|size|reconfigure)$ ]]; then
    echo "Voice PE app wrapper permits build, size or reconfigure only." >&2
    exit 2
fi
project_root="$(cd "$(dirname "$0")/.." && pwd)"
export SYNTHDEF_BOARD=voice_pe
export IDF_COMPONENT_MANAGER=0
export SYNTHDEF_BUILD_DIR="${SYNTHDEF_BUILD_DIR:-build-voice-pe-app}"
exec bash "$project_root/host/idf.sh" -D IDF_TARGET=esp32s3 \
    -D "SDKCONFIG=$project_root/build/host/voice-pe-app-sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$project_root/host/voice_pe.defaults" "$@"
