FROM python:3.12.8-slim AS app-builder

WORKDIR /app
COPY ./requirements.txt ./tests/test-requirements.txt /
ARG BUILD_ENV="test" PLASTERED_RELEASE_TAG=""
RUN if [ "$BUILD_ENV" = "test" ]; then pip install --no-cache-dir -r /test-requirements.txt; fi \
    && pip install --no-cache-dir -r /requirements.txt --timeout=300 \
    && rm -rf /root/.cache/pip
RUN rebrowser_playwright install --with-deps chromium-headless-shell \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache/ms-playwright/ffmpeg-1010 \
    && find /usr/share/fonts/truetype -type f -name '*.ttc' -o -name '*.ttf' -o -name '*.otf' -delete
COPY . .
ENV APP_DIR=/app FORCE_COLOR=1 PLASTERED_RELEASE_TAG=${PLASTERED_RELEASE_TAG}

ENTRYPOINT ["/app/entrypoint.sh"]
