# The official vixl host image (#546): ghcr.io/jxburros/vixl:VERSION, and VERSION-full with ffmpeg.
#
#   docker build -f distribution/container/Dockerfile --build-arg VERSION=X.Y.Z -t vixl:X.Y.Z .
#   docker build -f distribution/container/Dockerfile --build-arg VERSION=X.Y.Z --target full -t vixl:X.Y.Z-full .
#   docker run --read-only --tmpfs /tmp -v vixl-data:/data -e VIXL_HOST_TOKEN -p 8767:8767 vixl:X.Y.Z
#
# The host runs offline: content packs are fetched here, at build time, and checked against their pinned SHA-256
# (vixl.packs). The token comes from VIXL_HOST_TOKEN or a file named by VIXL_HOST_TOKEN_FILE (a mounted secret).
# VERSION must equal src/vixl/__init__.py (tests/test_container.py); the release bumps both.

ARG PYTHON=3.12-slim-bookworm

FROM python:${PYTHON} AS build
ARG VERSION=0.33.2
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 VIXL_PACK_DIR=/opt/vixl/packs
RUN python -m venv /opt/vixl/venv \
 && /opt/vixl/venv/bin/pip install "vixl-engine[server,pdf]==${VERSION}" \
 && /opt/vixl/venv/bin/python -c "from vixl import __version__; assert __version__ == '${VERSION}', __version__" \
 && /opt/vixl/venv/bin/python -c "from vixl import packs; [print(packs.install(name)['path']) for name in packs.PACKS]"

FROM python:${PYTHON} AS base
ARG VERSION=0.33.2
LABEL org.opencontainers.image.title="Vixl host" \
      org.opencontainers.image.description="vixl host: layered-image documents served to a host application" \
      org.opencontainers.image.source="https://github.com/jxburros/Vixl" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="LicenseRef-PolyForm-Small-Business-1.0.0"
RUN groupadd --gid 10001 vixl && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp/vixl vixl \
 && mkdir -p /data && chown 10001:10001 /data
COPY --from=build /opt/vixl /opt/vixl
COPY distribution/container/healthcheck.py /opt/vixl/healthcheck.py
# Caches (fonts, renders) live under HOME in /tmp, so the image runs with --read-only and a tmpfs /tmp.
ENV PATH=/opt/vixl/venv/bin:$PATH HOME=/tmp/vixl VIXL_PACK_DIR=/opt/vixl/packs VIXL_OFFLINE=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8767
USER 10001:10001
WORKDIR /data
HEALTHCHECK --interval=30s --timeout=6s --start-period=20s --retries=3 CMD ["python", "/opt/vixl/healthcheck.py"]
ENTRYPOINT ["vixl", "host", "--root", "/data", "--offline", "--bind", "0.0.0.0"]

# The -full variant: the same host with ffmpeg for MP4/WebM exports.
FROM base AS full
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
USER 10001:10001

# The default target: the image without ffmpeg.
FROM base AS runtime
