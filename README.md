# Plastered

[![Latest release](https://img.shields.io/github/release/windexvalence/plastered?label=Latest%20release)](https://github.com/windexvalence/plastered/releases/latest)

![CI status](https://github.com/windexvalence/plastered/actions/workflows/build-and-test.yml/badge.svg?branch=main) ![coverage](./docs/image_assets/coverage.svg) ![Security: Bandit](https://img.shields.io/badge/security-bandit-8A2BE2) 
[![python](https://img.shields.io/badge/python-3.14%2B-blue.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)


## `Python + Last + RED = plastered`

`plastered` is a self-hosted web app for automatically pulling your LFM album/track recommendations and snatching those recommended releases from RED. It runs as a Docker container and is driven entirely from your browser.

The idea behind `plastered` is similar to L*darr's "import lists", but instead of automatically snatching from an LFM playlist, `plastered` will automatically snatch based on your recommendations.

Additionally, `plastered` is completely agnostic to your download client as well as your library management, so it will not disrupt your existing music organization.

Some other nice perks:
* Rate-limits and retries for all API calls are enabled by default, with configurable retry counts and per-API rate limit settings.
* Search filtering and criteria are very configurable to suit your needs.
* Resilient release matching: RED search offers no fuzzy matching, so `plastered` matches releases itself — tolerating punctuation/edition-suffix naming differences (with an opt-in fuzzy mode), and falling back to musicbrainz's scored search when Last.fm lacks release metadata. See the [FAQ](./docs/FAQ.md#how-does-plastered-match-releases-on-red) for details.
* Only one RED search request is made per artist per run, no matter how many of that artist's releases are being searched for.
* Setup and installation is quick.
* Supports use of FL tokens (prioritizing the use of FL on the largest RED matches over smaller ones in a given run)

## User Setup + Installation

Refer to the [User Guide page](./docs/user_guide.md) for installation, configuration, and usage details.

## Releases

Check out the [Releases page](https://github.com/windexvalence/plastered/releases) for more details.

## Bug Reports / Feature Requests

Refer to this repo's [issues page](https://github.com/windexvalence/plastered/issues)

## Developing / Contributing

Refer to the [Development Guide](./docs/contributing/development_guide.md) for details on development environment setup instructions, and code contribution details for this repo.

