# Development Guide

## Pre-requisites
1. Install [`uv`](https://docs.astral.sh/uv/) if you do not already have it

## Setup / Installation

1. Clone the repo from `git@github.com:windexvalence/plastered.git`
2. Explore the full list of local development options by running `make` to see the help output.

### Optional: Code Editor Setup

Once `uv` is installed, you can follow this one-time setup for creating a host virtualenv. Make sure to run all commands from the root `plastered` repo directory:

1. Install the correct Python version:
    ```shell
    uv python install 3.12.8
    ```
2. Create a dedicated virtualenv:
    ```shell
    uv venv
    ```
3. Install the dependencies in the venv you just created in step 2:
    ```shell
    uv sync --all-groups
    ```
4. Optionally, configure your code editor / IDE of choice to use the uv-managed virtualenv located in the `.venv` directory at the root `plastered` project directory.

## Testing

1. To run code formatting checks, run: `make fmt-check`. 
    
    * If this command raises formatting errors, you will need to run the code auto-formatter by running: `make fmt`.

    * If this command and/or the `make fmt` command raises errors, you will need to manually address those and re-run the `make fmt` command to verify if the raised errors have been addressed.

2. To run ALL unit tests, run: `make test`

    * To run only a specific test file, run the make command with `TEST_TARGET` set to the relative test file's path. For example, the following will only run tests defined in `test_http_utils.py`:
        ```shell
        make test TEST_TARGET=tests/utils_tests/test_http_utils.py
        ```
    
    * To run only a specfici test function within a specific test file, run the make command with `TEST_TARGET` set to the relative test files's path followed by `::<target-test-function-name-here>`. For example, the following will only run the `test_throttle` test function in `test_http_utils.py`:
        ```shell
        make test TEST_TARGET=tests/utils_tests/test_http_utils.py::test_throttle
        ``` 


## Other testing commands

Run `make` to list the other available targets and their desciptions.
