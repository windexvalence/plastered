# Lastfm-Recs-Scraper
![CI status](https://github.com/windexvalence/last-red-recs/actions/workflows/build-and-test.yml/badge.svg?branch=wv/add-cicd) ![coverage](./docs/image_assets/coverage.svg)

A docker utility for automatically scraping the recommended albums/tracks from your Last.fm user profile

## Releases

Check out the [Releases](./docs/RELEASES.md) page for more details.

## Setup / Installation

1. Locally build the image with `make docker-build`
2. execute the relevant commands with docker run, such as:

    ```shell
    docker run -it --rm wv/last-red-recs:latest --help
    ```

## Development TODOs

- [ ] Add functionality to optionally add a matched rec release to a personal collage
- [ ] Add logic to optionally filter out recs with pre-existing snatches in t_group
- [ ] Possibly use this bot-detection page [here](https://bot-detector.rebrowser.net/) during CICD ? 
- [ ] Add CLI / config documentation
- [ ] Set up more automated semver tagging process: after initial main tag is set (such as [this](https://github.com/marketplace/actions/get-latest-tag) or this [recomendation](https://stackoverflow.com/a/74955554))
