#!/bin/sh
set -eu
apps_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
apps_python=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from firmware_upload import programmer_python; print(programmer_python())' "$apps_root/host")
exec "$apps_python" "$apps_root/host/dual_apps.py" "$@"
