FROM python:3.12.8-slim

COPY ./requirements.txt ./tests/test-requirements.txt /
RUN pip install -r /requirements.txt --timeout=300 --no-cache-dir
RUN rebrowser_playwright install --with-deps chromium 

ARG BUILD_ENV="test"
RUN if [ "$BUILD_ENV" = "test" ]; then pip install -r /test-requirements.txt; fi
RUN rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV APP_DIR=/app FORCE_COLOR=1
ADD . .

ENTRYPOINT ["/app/entrypoint.sh"]
