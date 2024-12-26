FROM selenium/standalone-chrome:131.0

# FROM selenium/standalone-firefox:133.0-geckodriver-0.35

# FROM selenium/standalone-firefox:4.27.0

USER root
RUN sudo apt update && sudo apt install -y python3.12-venv
SHELL ["/bin/bash", "-c"]
ENV APP_VIRTUAL_ENV=lastfm-recs
RUN python3 -m venv /usr/local/${APP_VIRTUAL_ENV} \
    && source /usr/local/${APP_VIRTUAL_ENV}/bin/activate

COPY ./requirements.txt /requirements.txt
RUN /usr/local/${APP_VIRTUAL_ENV}/bin/pip install -r /requirements.txt

ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
ENV APP_DIR=/app
ADD . .

ENTRYPOINT ["/app/entrypoint.sh"]
