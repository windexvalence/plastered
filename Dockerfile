FROM python:3.12.5-slim AS app-builder

WORKDIR /tmp
ENV VIRTUAL_ENV=/home/venv
COPY ./requirements.txt ./tests/test-requirements.txt ./
RUN python -m venv ${VIRTUAL_ENV} \
    && . ${VIRTUAL_ENV}/bin/activate \
    && pip install --no-cache-dir -r ./requirements.txt --timeout=300 \
    && rebrowser_playwright install --with-deps chromium 

ARG BUILD_ENV="test" PLASTERED_RELEASE_TAG=""
RUN if [ "$BUILD_ENV" = "test" ]; then . ${VIRTUAL_ENV}/bin/activate && pip install --no-cache-dir -r ./test-requirements.txt; fi

# https://github.com/alexdmoss/distroless-python
FROM al3xos/python-distroless:3.12-debian12-debug

ARG BUILD_ENV="test" PLASTERED_RELEASE_TAG=""
ENV VIRTUAL_ENV=/home/venv APP_DIR=/app FORCE_COLOR=1 PLASTERED_RELEASE_TAG=${PLASTERED_RELEASE_TAG}
USER root
WORKDIR /app
# https://stackoverflow.com/a/71756170
COPY --from=busybox:1.36.1-glibc /bin/sh /bin/sh

COPY --from=app-builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY --from=app-builder /usr/lib/x86_64-linux-gnu/libsqlite3.so.0 /usr/lib/x86_64-linux-gnu/libsqlite3.so.0
COPY . .

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
