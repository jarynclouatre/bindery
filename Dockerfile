# syntax=docker/dockerfile:1

FROM --platform=$BUILDPLATFORM golang:1.26.5-alpine3.24@sha256:0178a641fbb4858c5f1b48e34bdaabe0350a330a1b1149aabd498d0699ff5fb2 AS kepubify-builder

ARG TARGETOS
ARG TARGETARCH
ARG KEPUBIFY_REVISION=8e959eda11d783041fc03c1a8109275a27f2f2dc

RUN apk add --no-cache git
WORKDIR /src
RUN git clone https://github.com/pgaskin/kepubify.git . \
    && git checkout --detach "${KEPUBIFY_REVISION}" \
    && test "$(git rev-parse HEAD)" = "${KEPUBIFY_REVISION}"

# Preserve kepubify v4.0.4's behaviour while building it with a current Go
# toolchain and updated direct dependencies.
RUN sed -i \
      -e 's#golang.org/x/sync v0.0.0-20210220032951-036812b2e83c#golang.org/x/sync v0.0.0-20220722155255-886fb9371eb4#' \
      -e 's#golang.org/x/text v0.3.6#golang.org/x/text v0.3.8#' \
      go.mod \
    && grep -F 'golang.org/x/sync v0.0.0-20220722155255-886fb9371eb4' go.mod \
    && grep -F 'golang.org/x/text v0.3.8' go.mod \
    && go mod tidy \
    && go mod download \
    && go mod verify

RUN CGO_ENABLED=0 go test -mod=readonly ./kepub ./cmd/kepubify
RUN CGO_ENABLED=0 GOOS="$TARGETOS" GOARCH="$TARGETARCH" go build \
      -mod=readonly \
      -buildvcs=false \
      -trimpath \
      -ldflags "-s -w -X main.version=v4.0.4" \
      -o /out/kepubify \
      ./cmd/kepubify

FROM python:3.13-slim

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

COPY --from=kepubify-builder /out/kepubify /usr/local/bin/kepubify
RUN kepubify --version | grep -F 'kepubify v4.0.4'

RUN ln -sf /usr/bin/7z /usr/local/bin/7za \
 && ln -sf /usr/bin/7z /usr/local/bin/7zr || true

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
 && pip install --no-cache-dir --no-deps git+https://github.com/ciromattia/kcc.git@v11.0.1

RUN mkdir -p /app /app/config /Comics_in /Comics_out /Books_in /Books_out /Comics_raw

WORKDIR /app
COPY app.py            /app/app.py
COPY config.py         /app/config.py
COPY processor.py      /app/processor.py
COPY raw_processor.py  /app/raw_processor.py
COPY templates/        /app/templates/
COPY static/           /app/static/
COPY entrypoint.sh     /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:5000", "--timeout", "300", "--worker-tmp-dir", "/dev/shm", "--no-control-socket", "app:app"]
