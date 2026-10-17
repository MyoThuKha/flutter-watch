#!/bin/sh
# Local, offline installer. No sudo, downloads, or shell-profile modifications.
set -eu

if ! command -v python3 >/dev/null 2>&1; then
    echo 'flutter-watch installer: Python 3.9+ is required. Install python3 first.' >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/tool/install.py" "$@"
