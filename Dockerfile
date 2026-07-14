FROM python:3.12.8-slim-bookworm AS plastered-app

WORKDIR /app
# Ensure uv installs in container do not create a virtualenv (since it is not needed in a container).
# PYTHONDONTWRITEBYTECODE keeps runtime .pyc files out of the container's writable layer (see issue #50).
ENV UV_PROJECT_ENVIRONMENT=/usr/local/ HTMX_VERSION=2.0.8 HTMX_FILENAME=htmx.min.js PYTHONDONTWRITEBYTECODE=1
ADD "https://raw.githubusercontent.com/bigskysoftware/htmx/refs/tags/v${HTMX_VERSION}/dist/${HTMX_FILENAME}" .
COPY ./pyproject.toml uv.lock .
ARG PLASTERED_RELEASE_TAG=""
# uv is bind-mounted for the install step only, so the uv/uvx binaries never land in an app image layer
# (the test stage below copies them in permanently since the test/CI hook scripts need `uv run`).
# https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv lock --check && uv sync --locked --no-group test --no-cache
# rebrowser_playwright is a console script installed into /usr/local/bin by the sync above.
# All the install cruft (apt lists, the unused ffmpeg build, fonts) is removed in the same RUN so it
# never becomes part of a layer.
RUN rebrowser_playwright install --with-deps chromium-headless-shell \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache/ms-playwright/ffmpeg-* \
    && find /usr/share/fonts/truetype -type f \( -name '*.ttc' -o -name '*.ttf' -o -name '*.otf' \) -delete
COPY ./server_entrypoint.sh /app/
COPY ./plastered /app/plastered
RUN ln -sf "/app/${HTMX_FILENAME}" "/app/plastered/api/static/js/${HTMX_FILENAME}"
ENV APP_DIR=/app FORCE_COLOR=1 PLASTERED_RELEASE_TAG=${PLASTERED_RELEASE_TAG}
ENTRYPOINT ["/app/server_entrypoint.sh"]

# Test image stage defined below
FROM plastered-app AS plastered-test
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv sync --locked --all-groups --no-cache
ENV SLOW_TESTS=0
COPY ./build_scripts /app/build_scripts
COPY ./hooks /app/hooks
COPY ./docs /app/docs
COPY ./examples /app/examples
COPY ./tests /app/tests

ENTRYPOINT ["/app/tests/tests_entrypoint.sh"]
CMD ["tests"]
