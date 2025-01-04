# Last-Red-Recs

![CI status](https://github.com/windexvalence/last-red-recs/actions/workflows/build-and-test.yml/badge.svg?branch=main) ![coverage](./docs/image_assets/coverage.svg) ![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg) ![Linting](https://img.shields.io/badge/linting-pylint-4c1) ![Security: Bandit](https://img.shields.io/badge/security-bandit-8A2BE2) 

![Built for RED](https://img.shields.io/badge/built_for-RED-%23a30800?style=for-the-badge)

A docker utility for automatically scraping the recommended albums/tracks from your Last.fm user profile

## Releases

Check out the [Releases](./docs/RELEASES.md) page for more details.

## User Setup / Installation

Refer to the [User Guide page](./docs/user_guide.md) for installation, configuration, and usage details.

## Dev Setup / Installation

1. Install [Docker](https://docs.docker.com/get-started/get-docker/) if you do not already have it
2. Locally build the image with `make docker-build`
3. Explore the full list of local development options by running `make` to see the help output.

## Development TODOs

- [ ] Add functionality to optionally add a matched rec release to a personal collage
- [x] Add logic to optionally filter out recs with pre-existing snatches in t_group
- [ ] Possibly use this bot-detection page [here](https://bot-detector.rebrowser.net/) during CICD ? 
- [ ] Add CLI / config documentation
- [ ] Set up more automated semver tagging process: after initial main tag is set (such as [this](https://github.com/marketplace/actions/get-latest-tag) or this [recomendation](https://stackoverflow.com/a/74955554))
