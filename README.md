# Lastfm-Recs-Scraper
A docker utility for automatically scraping the recommended albums/tracks from your Last.fm user profile

## Setup / Installation
1. Locally build the image with `make docker-build`
2. execute the relevant commands with docker run, such as:

    ```shell
    docker run -it --rm wv/last-red-recs:latest --help
    ```

## Development TODOs
- [x] Add unit tests
- [ ] Add functionality to optionally add a matched rec release to a personal collage
- [x] Add code autoformatting / linting (black, isort)
- [ ] Possibly use this bot-detection page [here](https://bot-detector.rebrowser.net/) during CICD ? 
- [ ] Add CLI / config documentation
    - [ ] Encrypt the test resources html / json as GitHub actions secrets: more info [here](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions#storing-large-secrets)
- [x] Implement `release_search` module's logic
- [x] Create GitHub repo
- [ ] Add CICD
