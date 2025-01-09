# `last-red-recs` User Guide

This guide covers the installation, configuration, and usage details of `last-red-recs`. For development documentation, please refer to the [Development Guide](./development_guide.md) instead.

## Getting Started
`last-red-recs` is a tool for automatically inspecting your Last.fm album/track recommendations and snatching those recommended releases from RED.

### 1: Pre-requisites
This tool assumes you have an existing Last.fm profile, with recommendations already present on your account.

Additionally, you will need to:
1. Setup a RED API key with `Torrents` and `Users` scoped permissions granted.
2. Setup a Last.fm API key (see their instructions page [here](https://www.last.fm/api))
3. Have [Docker](https://docs.docker.com/get-started/get-docker/) installed on the host machine you intend to run this from.
4. Have at least 1.5GB of free disk space on your host machine to pull the image (the image is large due to the browser dependencies)

### 2: Configure the App

1. Create a dedicated config directory on your host machine. This will hold your app config file, and any summary output files from the app runs.
    ```shell
    mkdir -p /your/host/path/to/config
    ```

2. Initialize a config.yaml file in the directory you just created by running:
    ```shell
    docker run --rm ghcr.io/windexvalence/last-red-recs:latest init-conf > /your/host/path/to/config/config.yaml
    ```

3. Fill in the required config values in the file skeleton created from step 2. Refer to the [Configuration Reference](./configuration_reference.md) for additional details and information on non-required config settings.

### 3: Run the App

You can use either docker-compose, or the docker CLI to run the app:

#### docker-compose (recommended)

```yaml
services:
  last-red-recs:
    container_name: last-red-recs
    image: ghcr.io/windexvalence/last-red-recs:latest
    restart: unless-stopped
    volumes:
      - /host/path/to/config/:/config
      - /host/path/to/downloads/:/downloads
    command: scrape
```

#### docker CLI

```shell
docker run --rm -d \
    --name=last-red-recs \
    --restart unless-stopped \
    -v /host/path/to/config/:/config \
    -v /host/path/to/downloads/:/downloads \
    ghcr.io/windexvalence/last-red-recs:latest
```


## Additional Details

TODO: fill this in 
