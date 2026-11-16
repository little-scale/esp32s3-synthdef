#!/bin/sh
set -eu
upload_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
upload_python=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from firmware_upload import programmer_python; print(programmer_python())' "$upload_root/host")
exec "$upload_python" "$upload_root/host/dual_upload.py" "$@"
