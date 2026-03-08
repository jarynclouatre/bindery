FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's/Components: main/Components: main contrib non-free non-free-firmware/g' \
        /etc/apt/sources.list.d/debian.sources; \
    else \
      sed -i 's/ main$/ main contrib non-free non-free-firmware/' /etc/apt/sources.list || true; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      git \
      p7zip-full \
      p7zip-rar \
      unrar \
      ca-certificates \
      gosu \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) asset="kepubify-linux-64bit"  ;; \
      arm64) asset="kepubify-linux-arm64"  ;; \
      armhf) asset="kepubify-linux-arm"    ;; \
      i386)  asset="kepubify-linux-32bit"  ;; \
      *) echo "Unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/pgaskin/kepubify/releases/download/v4.0.4/${asset}" \
      -o /usr/local/bin/kepubify; \
    chmod +x /usr/local/bin/kepubify; \
    kepubify --version

RUN ln -sf /usr/bin/7z /usr/local/bin/7za \
 && ln -sf /usr/bin/7z /usr/local/bin/7zr || true

RUN pip install --no-cache-dir Flask packaging gunicorn watchdog "git+https://github.com/ciromattia/kcc.git@v9.4.3"

RUN mkdir -p /app /app/config /Comics_in /Comics_out /Books_in /Books_out /Comics_raw

WORKDIR /app
COPY app.py            /app/app.py
COPY config.py         /app/config.py
COPY processor.py      /app/processor.py
COPY raw_processor.py  /app/raw_processor.py
COPY templates/        /app/templates/
COPY entrypoint.sh     /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:5000", "--timeout", "300", "--worker-tmp-dir", "/dev/shm", "--no-control-socket", "app:app"]
