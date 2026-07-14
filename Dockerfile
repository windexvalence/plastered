########## Stage 1: build the single-file app PEX ##########
FROM python:3.12.8-slim-bookworm AS pex-builder
WORKDIR /build
ENV HTMX_VERSION=2.0.8 HTMX_FILENAME=htmx.min.js
COPY ./pyproject.toml ./uv.lock ./
COPY ./plastered ./src/plastered
# Pack pyproject.toml inside the package: get_project_version() resolves it via importlib.resources.
COPY ./pyproject.toml ./src/plastered/pyproject.toml
# Bake htmx into the static dir as a real file (resolved at runtime via importlib.resources).
ADD "https://raw.githubusercontent.com/bigskysoftware/htmx/refs/tags/v${HTMX_VERSION}/dist/${HTMX_FILENAME}" ./src/plastered/api/static/js/${HTMX_FILENAME}
# Export the locked runtime deps and build one PEX containing deps + the plastered sources.
# --venv: install into a real venv under PEX_ROOT on first boot (fast imports, real on-disk
#         static/template files for FastAPI). --sh-boot: cheap re-boot via a shell shim.
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv lock --check \
    && uv export --locked --no-group test --no-emit-project --no-hashes -o requirements.txt \
    && uv tool run pex \
        -r requirements.txt \
        -D ./src \
        -m plastered.main \
        --venv --sh-boot \
        -o /plastered.pex

########## Stage 2: the app image (the published end-user product) ##########
FROM python:3.12.8-slim-bookworm AS plastered-app
WORKDIR /app
ARG PLASTERED_RELEASE_TAG=""
ENV PYTHONDONTWRITEBYTECODE=1
# The single PEX is the entire application: 1st-party sources (incl. static/templates/pyproject.toml,
# all resolved at runtime via importlib.resources) + all locked 3rd-party deps.
COPY --from=pex-builder /plastered.pex /app/plastered.pex
# The starter config skeleton, kept on disk so users can copy it out of the image (see the user guide).
COPY ./plastered/config/init_conf.yaml /app/init_conf.yaml
# Install the browser + its system deps via the playwright CLI shipped inside the PEX.
# The PEX venv this extracts is pointed at a throwaway PEX_ROOT and removed in the same RUN,
# so the unpacked dependency tree never lands in an image layer.
RUN PEX_ROOT=/tmp/pex-root PEX_SCRIPT=rebrowser_playwright /app/plastered.pex install --with-deps chromium-headless-shell \
    # Purge with-deps packages that headless-shell scraping doesn't use (verified: page load + screenshot
    # still work): the software-GL stack (libgl1-mesa-dri drags in the ~110MB libllvm15 + libz3-4;
    # headless-shell bundles SwiftShader), xvfb (headless mode never talks to an X server), and the
    # CJK/emoji/latin font packs (DOM-text scraping doesn't rasterize text).
    && apt-get purge -y --auto-remove \
        libgl1-mesa-dri \
        xvfb \
        fonts-freefont-ttf \
        fonts-ipafont-gothic \
        fonts-liberation \
        fonts-noto-color-emoji \
        fonts-tlwg-loma-otf \
        fonts-unifont \
        fonts-wqy-zenhei \
    && rm -rf /tmp/pex-root \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache/ms-playwright/ffmpeg-* \
    && rm -rf /usr/share/doc /usr/share/man
ENV APP_DIR=/app FORCE_COLOR=1 PLASTERED_RELEASE_TAG=${PLASTERED_RELEASE_TAG}
# `run` resolves the config path from the PLASTERED_CONFIG env var and launches uvicorn with the
# host / port / log level / workers from the app config.
ENTRYPOINT ["/app/plastered.pex", "run"]

########## Stage 3: the test image (CI + local dev only; size does not matter here) ##########
FROM python:3.12.8-slim-bookworm AS plastered-test
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
# Ensure uv installs in container do not create a virtualenv (since it is not needed in a container).
ENV UV_PROJECT_ENVIRONMENT=/usr/local/ HTMX_VERSION=2.0.8 HTMX_FILENAME=htmx.min.js PYTHONDONTWRITEBYTECODE=1
COPY ./pyproject.toml uv.lock .
ARG PLASTERED_RELEASE_TAG=""
RUN uv lock --check && uv sync --locked --all-groups --no-cache
RUN rebrowser_playwright install --with-deps chromium-headless-shell \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY ./plastered /app/plastered
ADD "https://raw.githubusercontent.com/bigskysoftware/htmx/refs/tags/v${HTMX_VERSION}/dist/${HTMX_FILENAME}" /app/plastered/api/static/js/${HTMX_FILENAME}
ENV APP_DIR=/app FORCE_COLOR=1 PLASTERED_RELEASE_TAG=${PLASTERED_RELEASE_TAG} SLOW_TESTS=0
COPY ./build_scripts /app/build_scripts
COPY ./hooks /app/hooks
COPY ./docs /app/docs
COPY ./examples /app/examples
COPY ./tests /app/tests

ENTRYPOINT ["/app/tests/tests_entrypoint.sh"]
CMD ["tests"]
