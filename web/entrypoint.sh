#!/bin/sh
set -eu

mkdir -p /logs

if [ "$(id -u)" = "0" ]; then
    chown appuser:appuser /logs 2>/dev/null || true
    exec gosu appuser "$@"
fi

exec "$@"
