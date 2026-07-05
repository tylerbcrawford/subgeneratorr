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

# -local image: the whisper model cache must be writable so larger models can
# download at runtime. Only touch files whose ownership differs — a blanket
# chown -R would copy-up the ~500 MB baked model into the writable layer on
# every recreate. Ownership is baked at build for the default uid/gid.
if [ -d /models ]; then
    find /models \( ! -user abc -o ! -group abc \) \
        -exec chown abc:abc {} + 2>/dev/null || true
fi

# Execute the command as the abc user
exec gosu abc "$@"