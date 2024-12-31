FROM python:3.12

COPY ./requirements.txt /requirements.txt
COPY ./tests/test-requirements.txt /test-requirements.txt
RUN pip install -r /requirements.txt --timeout=300

RUN rebrowser_playwright install --with-deps chromium
ARG BUILD_ENV="test"
RUN if [ "$BUILD_ENV" = "test" ]; then pip install -r /test-requirements.txt; fi

WORKDIR /app
ENV APP_DIR=/app
ADD . .

ENTRYPOINT ["/app/entrypoint.sh"]
