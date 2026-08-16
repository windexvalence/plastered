# `plastered` User Guide

`plastered` runs as a web application: you launch its Docker container as a server and interact with it entirely
through your browser.

## 1: Pre-requisites

Make sure you have completed the following before installing or using `plastered`:

1. Setup a RED API key with `Torrents` and `Users` scoped permissions granted.
2. Setup a Last.fm API key (see their instructions page [here](https://www.last.fm/api)).
3. Have [Docker](https://docs.docker.com/get-started/get-docker/) installed on the host machine you intend to run this from.
4. Have at least 1.5GB of free disk space on your host machine to pull the image (the image is large due to the browser dependencies).

## 2: Configure the App

1. Create a dedicated config directory on your host machine. This holds your app config file and the app's SQLite DB.
    ```shell
    mkdir -p /your/host/path/to/plastered_dir
    ```

2. Pull the [latest plastered Docker image release](https://github.com/windexvalence/plastered/pkgs/container/plastered?tag=latest):
    ```shell
    docker pull ghcr.io/windexvalence/plastered:latest
    ```

3. Write a starter `config.yaml` into that directory by copying the bundled skeleton out of the image:
    ```shell
    docker run --rm --entrypoint cat ghcr.io/windexvalence/plastered:latest \
      /app/init_conf.yaml > /your/host/path/to/plastered_dir/config.yaml
    ```

4. Fill in the required config values in the skeleton from step 3. Refer to the
   [Configuration Reference](./config_reference.md) for details and the non-required settings.

## 3: Run the Server

Launch the container as a server, mapping a host port to the container's port 80, and mounting your config and
downloads directories:

```shell
docker run -it --rm --name plastered \
  -p 8000:80 \
  -e PLASTERED_CONFIG=/config/config.yaml \
  -v /your/host/path/to/plastered_dir/:/config \
  -v /host/path/to/downloads/:/downloads \
  ghcr.io/windexvalence/plastered:latest
```

Then open <http://localhost:8000/> in your browser.

> The container serves the app on port 80 internally; the `-p 8000:80` above exposes it as `localhost:8000` on your
> host — change the left-hand `8000` if that port is taken.

### User / Group Identifiers

The app never runs as root: the image defaults to a non-root user with uid:gid `1000:1000`. When using volumes (`-v`
flags), permissions issues can arise between the host OS and the container — avoid them by matching the container's
ids to the host user that owns your mounted directories. To find that user's ids, run `id your_user`:

```shell
$ id your_user
uid=1000(your_user) gid=1000(your_user) groups=1000(your_user)
```

If those ids are not `1000:1000`, pick one of these ways to change the container's ids:

- **`PUID`/`PGID` environment variables (linuxserver.io-style):** start the container as root so it can remap its
  internal user; it re-drops privileges to the requested ids before booting the app:

  ```shell
  docker run ... --user root -e PUID=1000 -e PGID=1000 ...
  ```

  On startup the config directory is chowned to those ids automatically (it holds the app's SQLite DB); the
  downloads directory is left untouched, so ensure it is writable by `PUID:PGID`.

- **`--user` (docker-native):** `docker run --user <uid>:<gid>` runs the app directly as those ids. Nothing is
  chowned for you, so both mounted directories must already be writable by those ids.

## 4: Use the App

Everything is driven from the web UI:

- **Scrape & snatch your Last.fm recs** — the LFM recommendations scraper page pulls your album/track recs and searches
  RED for matches (downloading them when snatching is enabled).
- **Ad-hoc search** — search RED for a specific artist + album/track on demand, optionally downloading the top match.
- **Run history** — review past scraper and ad-hoc runs, see per-rec results/skip reasons, and (for downloads-disabled
  scraper runs) retroactively download matched releases.
- **Config** — inspect the effective app config the server loaded.

Snatched `.torrent` files are written to the mounted downloads directory; point your download client at it.

## 5. Full REST API Reference

You can view the full API documentation for your server at `<plastered URL and port here>/docs`.
