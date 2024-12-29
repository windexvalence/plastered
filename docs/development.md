# Development

## Setup / Installation
This repo will require that you have Docker and `make` installed. All the builds and tests are executed inside of a docker container, so you do not need to have python installed locally.

1. Clone the repo from git@github.com:windexvalence/last-red-recs.git
2. Ensure that you're able to locally build the main Docker image from master by running `make docker-build`. Address any build issues or local dev issues as necessary

## Testing
1. To run code formatting checks, run: `make code-format-check`. If this command raises formatting errors, you will need to run the code auto-formatter by running: `make code-format`.
2. To run unit tests, run: `make docker-test`
