#!/bin/bash
set -euo pipefail

PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Create internal user matching the host UID/GID
if ! getent group abc >/dev/null 2>&1; then
    groupadd -g "${PGID}" abc
fi
if ! getent passwd abc >/dev/null 2>&1; then
    useradd -u "${PUID}" -g "${PGID}" -m -s /bin/sh abc
fi

# Force ownership of mapped volumes
chown -R abc:abc /app/config /Comics_in /Comics_out /Books_in /Books_out /Comics_raw

# Drop privileges and execute application
exec gosu abc "$@"
