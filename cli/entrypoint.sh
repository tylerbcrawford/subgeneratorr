#!/bin/bash
set -e

# Default values
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Create group if it doesn't exist
if ! getent group abc > /dev/null 2>&1; then
    groupadd -g "${PGID}" abc
fi

# Create user if it doesn't exist
if ! id -u abc > /dev/null 2>&1; then
    useradd -u "${PUID}" -g "${PGID}" -d /app -s /bin/bash abc
fi

# Change ownership of working directory
chown -R abc:abc /app

# Execute the command as the abc user
exec gosu abc "$@"