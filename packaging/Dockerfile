FROM ghcr.io/astral-sh/uv:0.11.25 AS uv
FROM ubuntu:24.04
COPY --from=uv /uv /uvx /usr/local/bin/
ENV DEBIAN_FRONTEND=noninteractive UV_LINK_MODE=copy UV_PYTHON_INSTALL_DIR=/opt/python \
    PYINSTALLER_CONFIG_DIR=/tmp/pyinstaller QT_QPA_PLATFORM=offscreen \
    PATH=/app/.venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates binutils dpkg-dev xz-utils \
    libglib2.0-0t64 libgssapi-krb5-2 libgl1 libegl1 libopengl0 libdbus-1-3 libfontconfig1 libfreetype6 \
    libx11-6 libx11-xcb1 libxext6 libxrender1 libxi6 libsm6 libice6 \
    libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon0 libxkbcommon-x11-0 \
    libwayland-client0 libwayland-cursor0 libwayland-egl1 wl-clipboard xclip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN uv sync --frozen --group build --python 3.14.6 \
    && chmod -R a+rX /app/.venv /opt/python
ENTRYPOINT ["python", "tools/release.py"]
CMD ["linux"]
