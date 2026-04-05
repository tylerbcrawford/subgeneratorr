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
    exec gosu appuser "$@"
fi

exec "$@"
