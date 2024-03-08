ARG BUILD_FROM=ghcr.io/hassio-addons/base:14.0.7
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Install requirements for add-on
RUN apk add --no-cache \
  coreutils=9.3-r2 \
  wget=1.21.4-r0 \
  python3 py3-pip

RUN \
  pip3 install --no-cache-dir --upgrade pip && \
  pip3 install --no-cache-dir python-socketio asyncio aiohttp

# Copy root filesystem
COPY rootfs /

# Make services in 'example' executable
RUN chmod +x /etc/services.d/example/*

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
  io.hass.name="${BUILD_NAME}" \
  io.hass.description="${BUILD_DESCRIPTION}" \
  io.hass.arch="${BUILD_ARCH}" \
  io.hass.type="addon" \
  io.hass.version=${BUILD_VERSION} \
  org.opencontainers.image.title="${BUILD_NAME}" \
  org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
  org.opencontainers.image.created=${BUILD_DATE} \
  org.opencontainers.image.revision=${BUILD_REF} \
  org.opencontainers.image.version=${BUILD_VERSION}