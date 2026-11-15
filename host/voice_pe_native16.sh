#!/bin/bash
# Build only: this application needs a separately qualified native-16k XMOS image.
set -euo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^(build|size|reconfigure)$ ]]; then
    echo 'Usage: bash host/voice_pe_native16.sh {build|size|reconfigure}' >&2
    exit 2
fi
project_root="$(cd "$(dirname "$0")/.." && pwd)"
export SYNTHDEF_BOARD=voice_pe
export IDF_COMPONENT_MANAGER=0
export SYNTHDEF_BUILD_DIR="${SYNTHDEF_BUILD_DIR:-build-voice-pe-native16}"
exec bash "$project_root/host/idf.sh" -D IDF_TARGET=esp32s3 \
    -D "SDKCONFIG=$project_root/build/host/voice-pe-native16-sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$project_root/host/voice_pe.defaults;$project_root/host/voice_pe_native16.defaults" \
    -D SYNTHDEF_DSP_CANDIDATES=saw,impulse "$@"
