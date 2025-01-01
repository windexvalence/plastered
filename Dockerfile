FROM python:3.12-slim

COPY ./requirements.txt ./tests/test-requirements.txt /
RUN pip install -r /requirements.txt --timeout=300
# TODO: Make sure we don't need the --with-deps flag, as that might be needed but makes the image much bigger
RUN rebrowser_playwright install chromium
# RUN rebrowser_playwright install --with-deps chromium
ARG BUILD_ENV="test"
RUN if [ "$BUILD_ENV" = "test" ]; then pip install -r /test-requirements.txt; fi
RUN rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV APP_DIR=/app
ADD . .

ENTRYPOINT ["/app/entrypoint.sh"]
