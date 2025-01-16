# `plastered` User Guide

## 1: Pre-requisites
Make sure you have completed the following before installing or using `plastered`:

1. Setup a RED API key with `Torrents` and `Users` scoped permissions granted.
2. Setup a Last.fm API key (see their instructions page [here](https://www.last.fm/api))
3. Have [Docker](https://docs.docker.com/get-started/get-docker/) installed on the host machine you intend to run this from.
4. Have at least 1.5GB of free disk space on your host machine to pull the image (the image is large due to the browser dependencies)

## 2: Configure the App

1. Create a dedicated config directory on your host machine. This will hold your app config file, and any summary output files from the app runs.
    ```shell
    mkdir -p /your/host/path/to/plastered_dir
    ```

2. Pull the latest official release of the plastered Docker image:
  ```shell
  docker pull ghcr.io/windexvalence/plastered:latest
  ```

2. Initialize a config.yaml file in the directory you just created by running:
    ```shell
    docker run --rm ghcr.io/windexvalence/plastered:latest init-conf > /your/host/path/to/plastered_dir/config.yaml
    ```

3. Fill in the required config values in the file skeleton created from step 2. Refer to the [Configuration Reference](./configuration_reference.md) for additional details and information on non-required config settings.

4. Set alias in your host shell profile (`.zshrc`, `.bash_profile`, etc.) to the the Docker command which executes the `plastered` CLI, as follows:
  ```shell
  alias plastered='docker run --rm --name=plastered -e PLASTERED_CONFIG=/config/config.yaml -e COLUMNS="$(tput cols)" -e LINES="$(tput lines)" -v /host/path/to/plastered_dir/:/config -v /host/path/to/downloads/:/downloads ghcr.io/windexvalence/plastered:latest'
  ```

5. Verify that you're able to view the plastered help output with the following command. If this works, then you're ready to run the app:
  ```shell
  plastered --help
  ```

## 3: Run the App

You can either immediately try snatching your LFM recs with the current default config you just created, or you can explore the [configuration reference](./configuration_reference.md) and fine-tune your config before snatching your LFM recs.

Once you're happy with your config settings, simply run the following to kick off the LFM scraping / snatching.

```shell
plastered scrape
```

### Additional Commands

Along with `scrape`, plastered offers a few other helpful commands. You can find the full list of commands by running `plastered --help`.

Further command-specific details are accessible by running the command of interest with the help flag, for example to see more details about the `plastered cache` command, run the following:
```
plastered cache --help
```
