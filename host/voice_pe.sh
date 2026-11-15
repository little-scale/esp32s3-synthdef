#!/bin/bash
# Build-only front end. No serial enumeration, monitor, flash or erase actions.
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -ne 1 ]]; then echo "Usage: bash host/voice_pe.sh {build|size|reconfigure}" >&2; exit 2; fi
case "$1" in build|size|reconfigure) ;; *) echo "Build-only wrapper: action refused: $1" >&2; exit 2 ;; esac
export IDF_COMPONENT_MANAGER=0
unset SYNTHDEF_BOARD
export SYNTHDEF_PROJECT_DIR="$project_root/ports/voice_pe"
export SYNTHDEF_BUILD_DIR="$project_root/build/voice-pe"
exec bash "$project_root/host/idf.sh" -D IDF_TARGET=esp32s3 \
    -D "SDKCONFIG=$project_root/build/voice-pe/sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$project_root/ports/voice_pe/sdkconfig.defaults" "$1"
