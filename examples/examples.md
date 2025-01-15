# Examples

This doc covers some additional `plastered` usage examples. You should make sure to have followed the instructions in the [user guide](../docs/user_guide.md) prior to reading this doc.

These examples meant as a helpful reference for some potential usage options, but are not the required way to use plastered.

## Running Plastered on a schedule

While it is useful to run the plastered `scrape` command manually while you're first adjusting your plastered config, 
it is recommended that plastered run on a pre-defined schedule once you're happy with your config. 
This can easily be done with [crontab](https://man7.org/linux/man-pages/man8/cron.8.html) (Linux / MacOS) or 
with [schtasks](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2012-R2-and-2012/cc725744(v=ws.11)?redirectedfrom=MSDN) (Windows). 
A crontab example which runs `plastered scrape` every other day is shown below:

```txt
0 0 * * */2 docker run --rm --name=plastered -e PLASTERED_CONFIG=/config/config.yaml -v /host/path/to/plastered_dir/:/config -v /host/path/to/downloads/:/downloads ghcr.io/windexvalence/plastered:latest 
```

Use [crontab.guru](https://crontab.guru/#0_0_*_*_*/2) to find the cron pattern that defines the schedule which you want to run plastered scrape on.

## Docker Compose

While the easiest way to use plastered is via the `docker run` CLI command (preferably via a bash alias to the docker run command), it is also possible to run plastered in a docker-compose file. The docker-compose approach may be useful if you want to run plastered through a containerized VPN client, such as [gluetun](https://github.com/qdm12/gluetun?tab=readme-ov-file#gluetun-vpn-client). Below is the minimal required setup for using plastered via docker-compose:

1. Add a plastered service to an existing `docker-compose.yml` file, or create a new `docker-compose.yml` file with the following contents:
    ```yaml
    ---
    services:
    plastered:
        image: ghcr.io/windexvalence/plastered:latest
        container_name: plastered
        volumes:
        - /host/path/to/plastered_dir/:/config
        - /host/path/to/downloads/:/downloads
        environment:
        - PLASTERED_CONFIG=/config/config.yaml
        restart: unless-stopped
    ```

2. Set alias in your host shell profile (`.zshrc`, `.bash_profile`, etc.) to the the Docker compose command which executes the `plastered` CLI, as follows:
    ```shell
    alias plastered="docker compose -f /your/host/path/to/docker-compose.yml"
    ```


