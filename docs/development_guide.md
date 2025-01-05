# Development Guide

## Pre-requisites
1. Install [Docker](https://docs.docker.com/get-started/get-docker/) if you do not already have it

## Setup / Installation
This repo will require that you have Docker and `make` installed. All the builds and tests are executed inside of a docker container, so you do not need to have python installed locally.

1. Clone the repo from git@github.com:windexvalence/last-red-recs.git
2. Ensure that you're able to locally build the main Docker image from master by running `make docker-build`. Address any build issues or local dev issues as necessary
3. Explore the full list of local development options by running `make` to see the help output.

### Optional: Code Editor Setup

While this application along with all its tests / code analysis is fully containerized with Docker, if 
you wish to have accurate imports and syntax highlighting in your code editor, you should configure a 
dedicated virtual environment running Python version `3.12.8` on your host machine which you're running the code editor from.

The **strongly** recommended approach for this is to use [pyenv](https://github.com/pyenv/pyenv) along with [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv). Both those links detail the installation and setup process for those tools.

Once those are installed, you can follow this one-time setup for creating a host virtualenv:

1. Install the correct Python version via pyenv:
    ```shell
    pyenv install 3.12.8
    ```
2. Create a dedicated virtualenv via pyenv-virtualenv:
    ```shell
    pyenv virtualenv 3.12.8 last-red-recs
    ```
3. Activate the virtualenv you just created in step 2:
    ```shell
    pyenv activate last-red-recs
    ```
4. Install both the application and test pip requirements in your newly activated virtualenv:
    ```shell
    pip install -r requirements.txt && pip install -r tests/test-requirements.txt
    ```
5. Lastly, configure your code editor / IDE of choice to use the `last-red-recs` virtualenv for this project.

## Testing

> Warning: Currently, there are some unit tests which will fail in a local environment as they depend on encrypted files which can only be decrypted by the GitHub actions script. The pending issue to resolve this may be found [here](https://github.com/windexvalence/last-red-recs/issues/13). Since these encrypted files are massive JSON / HTML blobs, they require a lot of time to comb through their contents to ensure they are not leaking any sensitive data.

1. To run code formatting checks, run: `make code-format-check`. 
    
    * If this command raises formatting errors, you will need to run the code auto-formatter by running: `make code-format`.

    * If this command and/or the `make code-format` command raise additional [pylint](https://github.com/pylint-dev/pylint) / [bandit](https://github.com/PyCQA/bandit) errors, you will need to manually address those and re-run the `make code-format` command to verify if the raised errors have been addressed.

2. To run unit tests, run: `make docker-test`

3. To remove all the pre-existing local images you've built, run: `make docker-clean`
