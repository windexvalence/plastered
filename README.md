# Last-Red-Recs

![CI status](https://github.com/windexvalence/last-red-recs/actions/workflows/build-and-test.yml/badge.svg?branch=main) ![coverage](./docs/image_assets/coverage.svg) ![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg) ![Linting](https://img.shields.io/badge/linting-pylint-4c1) ![Security: Bandit](https://img.shields.io/badge/security-bandit-8A2BE2) 

![Built for RED](https://img.shields.io/badge/built_for-RED-%23a30800?style=for-the-badge)

`last-red-recs` is a stand-alone tool for automatically inspecting your LFM album/track recommendations and snatching those recommended releases from RED.

The idea behind `last-red-recs` is similar to Lidarr's "import lists", but instead of automatically snatching from a Last.fm playlist, `last-red-recs` will automatically snatch based on your recommendations.

Additionally, `last-red-recs` is completely agnostic to your download client as well as your library management, so it will not disrupt your existing music organization.

Some other nice perks:
* Rate-limits and retries for all API calls are enabled by default, with configurable retry counts and per-API rate limit settings.
* Search filtering and criteria are very configurable to suit your needs.
* Setup and installation is quick.

## User Setup + Installation

Refer to the [User Guide page](./docs/user_guide.md) for installation, configuration, and usage details.

## Dev Setup + Installation

Refer to the [Development Guide](./docs/development_guide.md) for details on development environment setup instructions, and code contribution details for this repo.

## Releases

Check out the [Releases](./docs/RELEASES.md) page for more details.

## Bug Reports / Feature Requests

Refer to this repo's [issues page](https://github.com/windexvalence/last-red-recs/issues)

