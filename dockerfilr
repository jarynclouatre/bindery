FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

# Enable contrib + non-free repos for unrar and p7zip-rar
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's/Components: main/Components: main contrib non-free non-free-firmware/g' /etc/apt/sources.list.d/debian.sources; \
    else \
      sed -i 's/ main$/ main contrib non-free non-free-firmware/' /etc/apt/sources.list || true; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    p7zip-full \
    p7zip-rar \
    unrar \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install kepubify (auto-pick arch)
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) asset="kepubify-linux-64bit" ;; \
        arm64) asset="kepubify-linux-arm64" ;; \
        armhf) asset="kepubify-linux-arm" ;; \
        i386)  asset="kepubify-linux-32bit" ;; \
        *) echo "Unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/pgaskin/kepubify/releases/latest/download/${asset}" -o /usr/local/bin/kepubify; \
    chmod +x /usr/local/bin/kepubify; \
    kepubify --version

# Some tooling expects 7za
RUN ln -sf /usr/bin/7z /usr/local/bin/7za \
    && ln -sf /usr/bin/7z /usr/local/bin/7zr || true

# Install Python requirements
RUN pip install --no-cache-dir Flask packaging "git+https://github.com/ciromattia/kcc.git"

RUN mkdir -p /app /app/config /Comics_in /Comics_out /Books_in /Books_out

WORKDIR /app
COPY app.py /app/app.py

EXPOSE 5000

CMD ["python", "app.py"]
