#!/bin/sh
# Use an existing Python with USB support, including the project's IDF environment.
set -eu
studio_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -n "${STUDIO_PYTHON:-}" ]; then
    exec "$STUDIO_PYTHON" "$studio_root/host/studio.py" "$@"
fi
if python3 -c 'import serial' >/dev/null 2>&1; then
    exec python3 "$studio_root/host/studio.py" "$@"
fi
if [ -n "${IDF_PYTHON_ENV_PATH:-}" ] && [ -x "$IDF_PYTHON_ENV_PATH/bin/python" ]; then
    exec "$IDF_PYTHON_ENV_PATH/bin/python" "$studio_root/host/studio.py" "$@"
fi
for studio_python in "$HOME"/.espressif/python_env/idf5.5*/bin/python; do
    if [ -x "$studio_python" ] && "$studio_python" -c 'import serial' >/dev/null 2>&1; then
        exec "$studio_python" "$studio_root/host/studio.py" "$@"
    fi
done
printf '%s\n' 'USB support needs pyserial. Install host/requirements.txt in a Python environment, then run host/studio.py with that Python.' >&2
exit 1
