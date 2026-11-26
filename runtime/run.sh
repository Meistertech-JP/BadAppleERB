#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
mkdir -p logs
if [ -n "${PYEMUERA_PYTHON:-}" ]; then
    ba_python="$PYEMUERA_PYTHON"
elif [ -x ./pypy/bin/pypy3 ]; then
    ba_python=./pypy/bin/pypy3
else
    ba_python=python3
fi
exec "$ba_python" -B PyEmuera.pyz . "$@" 2>logs/diagnostics.log
