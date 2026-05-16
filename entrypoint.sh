#!/bin/bash
set -euo pipefail

PUID=${PUID:-1000}
PGID=${PGID:-1000}
SKIP_CHOWN=${SKIP_CHOWN:-false}

# Create internal user matching the host UID/GID
if ! getent group abc >/dev/null 2>&1; then
    groupadd --non-unique -g "${PGID}" abc
fi
if ! getent passwd abc >/dev/null 2>&1; then
    useradd --non-unique -u "${PUID}" -g "${PGID}" -m -s /bin/sh abc
fi

# Set ownership on the directories themselves, then only fix files that need it.
# Avoids walking every file in large libraries on every container start.
# Set SKIP_CHOWN=true to skip entirely — useful for NFS/SMB mounts where the
# container cannot chown but file access works regardless (e.g. unprivileged LXC).
if [[ "${SKIP_CHOWN,,}" != "true" ]]; then
    chown abc:abc /app/config /Comics_in /Comics_out /Books_in /Books_out /Comics_raw
    find /app/config /Comics_in /Comics_out /Books_in /Books_out /Comics_raw \
         ! -user abc -exec chown abc:abc {} +
fi

# Drop privileges and execute application
exec gosu abc "$@"
