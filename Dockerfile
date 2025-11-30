FROM python:3.12.8-slim-bookworm AS plastered-app

# https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
# Ensure uv installs in container do not create a virtualenv (since it is not needed in a container)
ENV UV_PROJECT_ENVIRONMENT=/usr/local/ HTMX_VERSION=2.0.8 HTMX_FILENAME=htmx.min.js
ADD "https://raw.githubusercontent.com/bigskysoftware/htmx/refs/tags/v${HTMX_VERSION}/dist/${HTMX_FILENAME}" .
COPY ./pyproject.toml uv.lock .
ARG PLASTERED_RELEASE_TAG=""
RUN uv lock --check && uv sync --locked --no-group test --no-cache
RUN uv run rebrowser_playwright install --with-deps chromium-headless-shell \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache/ms-playwright/ffmpeg-1010 \
    && find /usr/share/fonts/truetype -type f -name '*.ttc' -o -name '*.ttf' -o -name '*.otf' -delete
COPY  ./entrypoint.sh ./server_entrypoint.sh /app/
COPY ./plastered /app/plastered
RUN ln -sf "/app/${HTMX_FILENAME}" "/app/plastered/api/static/js/${HTMX_FILENAME}" && ln -sf "/app/${CLASSLESS_CSS_FILENAME}" "/app/plastered/api/static/css/${CLASSLESS_CSS_FILENAME}"
ENV APP_DIR=/app FORCE_COLOR=1 PLASTERED_RELEASE_TAG=${PLASTERED_RELEASE_TAG}
ENTRYPOINT ["/app/entrypoint.sh"]

# Test image stage defined below
FROM plastered-app AS plastered-test
RUN uv sync --locked --all-groups --no-cache
ENV SLOW_TESTS=0
COPY ./build_scripts /app/build_scripts
COPY ./docs /app/docs
COPY ./examples /app/examples 
COPY ./tests /app/tests

ENTRYPOINT ["/app/tests/tests_entrypoint.sh"]
CMD ["tests"]
