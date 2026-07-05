#!/bin/sh
set -eu

mkdir -p /logs
APP_UID="${PUID:-1000}"
APP_GID="${PGID:-1000}"

if [ "$(id -u)" = "0" ]; then
    target_group="appuser"
    current_uid="$(id -u appuser)"
    current_gid="$(id -g appuser)"

    if [ "$APP_GID" != "$current_gid" ]; then
        existing_group="$(getent group "$APP_GID" | cut -d: -f1 || true)"
        if [ -n "$existing_group" ] && [ "$existing_group" != "$target_group" ]; then
            target_group="$existing_group"
        else
            groupmod -o -g "$APP_GID" appuser
        fi
    fi

    if [ "$APP_UID" != "$current_uid" ] || [ "$target_group" != "appuser" ]; then
        usermod -o -u "$APP_UID" -g "$target_group" appuser
    fi

    chown appuser:"$target_group" /logs 2>/dev/null || true
    # -local image: the whisper model cache must be writable so larger models
    # can download at runtime and hf_hub can refresh revision refs. Only touch
    # files whose ownership actually differs — a blanket chown -R would
    # copy-up the ~500 MB baked model into the container's writable layer on
    # every recreate (overlayfs). Ownership is baked at build for the default
    # uid/gid, so this is a no-op unless PUID/PGID are customized.
    if [ -d /models ]; then
        find /models \( ! -user appuser -o ! -group "$target_group" \) \
            -exec chown appuser:"$target_group" {} + 2>/dev/null || true
    fi
    exec gosu appuser "$@"
fi

exec "$@"
