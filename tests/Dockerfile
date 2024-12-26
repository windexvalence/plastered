FROM wv/lastfm-recs:latest

WORKDIR /app/tests

COPY test-requirements.txt .

RUN source /usr/local/${APP_VIRTUAL_ENV}/bin/activate \
    && /usr/local/${APP_VIRTUAL_ENV}/bin/pip install -r /app/tests/test-requirements.txt

COPY . .

ENTRYPOINT ["/app/tests/tests_entrypoint.sh"]
