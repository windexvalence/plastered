FROM wv/lastfm-recs:latest

# ENV TESTING_DIR=/app_tests

RUN source /usr/local/${APP_VIRTUAL_ENV}/bin/activate \
    && /usr/local/${APP_VIRTUAL_ENV}/bin/pip3 install -r /app/tests/test-requirements.txt

ENTRYPOINT ["/app/tests/tests_entrypoint.sh"]
