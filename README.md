# Lastfm-Recs-Scraper
A docker utility for automatically scraping the recommended albums/tracks from your Last.fm user profile

## Setup / Installation
1. Locally build the image with `make docker-build`
2. execute the relevant commands with docker run, such as:

    ```shell
    docker run -it --rm wv/lastfm-recs:latest --help
    ```

## Development TODOs
- [ ] Add unit tests
- [ ] Allow for tests.Dockerfile builds to cache test-requirements.txt pip installs
- [ ] Add functinoality to optionally add a matched rec release to a personal collage
- [ ] Add code autoformatting / linting (black, isort)
- [ ] Add CLI / config documentation
- [ ] Implement `release_search` module's logic
- [ ] Create GitHub repo
- [ ] Add CICD
