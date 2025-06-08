FROM python:3.12.8-slim AS plastered-app

WORKDIR /app
COPY ./requirements.txt /
ARG PLASTERED_RELEASE_TAG=""
RUN pip install --no-cache-dir -r /requirements.txt --timeout=300 && rm -rf /root/.cache/pip
RUN rebrowser_playwright install --with-deps chromium-headless-shell \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache/ms-playwright/ffmpeg-1010 \
    && find /usr/share/fonts/truetype -type f -name '*.ttc' -o -name '*.ttf' -o -name '*.otf' -delete
COPY  ./entrypoint.sh ./pyproject.toml .
COPY ./plastered /app/plastered
ENV APP_DIR=/app FORCE_COLOR=1 PLASTERED_RELEASE_TAG=${PLASTERED_RELEASE_TAG}
ENTRYPOINT ["/app/entrypoint.sh"]

# Test image stage defined below
FROM plastered-app AS plastered-test
COPY ./tests/test-requirements.txt /
RUN pip install --no-cache-dir -r /test-requirements.txt
ENV SLOW_TESTS=0
COPY ./build_scripts /app/build_scripts
COPY ./docs /app/docs
COPY ./examples /app/examples 
COPY ./tests /app/tests

ENTRYPOINT ["/app/tests/tests_entrypoint.sh"]
CMD ["tests"]
