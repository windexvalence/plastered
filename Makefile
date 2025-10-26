# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'
PROJECT_DIR_PATH := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))
# For colored shell output from Makefile echos: https://stackoverflow.com/a/24148388
RED := $(shell echo "\033[1;33m")
NC := $(shell echo "\033[0m")
ifndef TEST_TARGET
override TEST_TARGET = tests
endif

# Default to not running slow tests locally
ifndef SLOW_TESTS
override SLOW_TESTS = 0
endif

ifndef PDB
override PDB = 0
endif

ifndef DB_TEST_MODE
override DB_TEST_MODE = false
endif

ifndef APP_CONFIG_DIR
override APP_CONFIG_DIR = $(PROJECT_DIR_PATH)/examples
endif

ifndef DOWNLOADS_DIR
override DOWNLOADS_DIR = $(APP_CONFIG_DIR)
endif

help:           ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

docker-clean:  ## Remove old local docker image and container artifacts
	docker ps -aq | xargs docker container stop
	docker ps -aq | xargs docker container rm
	docker images "*/*plastered*" -q | xargs docker rmi -f

clean:  docker-clean ## Removes docker artifacts and any local pycache artifacts
	find . -type d -name '__pycache__' -print | xargs rm -rf

docker-build:  ## Build the plastered docker app and test images locally
	docker build --target plastered-app -t wv/plastered:$$(date +%s) -t wv/plastered-app:latest .
	docker build --target plastered-test -t wv/plastered-test:$$(date +%s) -t wv/plastered-test:latest .

docker-build-no-test:  ## Build the plastered docker image locally without test-requirements installed
	docker build --target plastered-app --build-arg BUILD_ENV=non-test -t wv/plastered:non-test .

docker-shell:  docker-build  ## Execs a local shell inside a locally built plastered docker container for testing and debugging
	docker run -it --rm --entrypoint /bin/bash wv/plastered-test:latest

docker-server:  docker-build-no-test  ## Execs a local container running the server on localhost port 8000
	@echo "\n $(RED) Enter http://localhost:8000/ into your browser. $(NC) \n"
	docker run --rm --name plastered-api \
		-p 8000:80 \
		-v $(APP_CONFIG_DIR):/config \
		-v $(DOWNLOADS_DIR):/downloads \
		-v $(PROJECT_DIR_PATH)/plastered/api/static:/app/plastered/api/static \
		-v $(PROJECT_DIR_PATH)/plastered/api/templates:/app/plastered/api/templates \
		-e PLASTERED_CONFIG=/config/config.yaml \
		-e DB_TEST_MODE=$(DB_TEST_MODE) \
		--entrypoint /bin/bash wv/plastered:non-test -c '/app/server_entrypoint.sh'

docker-py-shell:  docker-build  ## Execs a local python shell inside a locally built plastered docker container for testing and debugging
	docker run -it --rm --env PYTHONPATH=/app --entrypoint python wv/plastered-test:latest -i

fmt-check:  ## Runs code-auto-formatting checks, lint checks, and security checks
	CODE_FORMAT_CHECK=1 PYTHONPATH=$(PROJECT_DIR_PATH) APP_DIR=$(PROJECT_DIR_PATH) uv run ./build_scripts/code-format.sh

fmt:  ## Runs code-auto-formatting, followed by lint checks, and then security checks
	PYTHONPATH=$(PROJECT_DIR_PATH) APP_DIR=$(PROJECT_DIR_PATH) uv run ./build_scripts/code-format.sh

mypy:  ## Runs mypy type checking
	uv run mypy --config-file pyproject.toml .

test:  ## Runs unit tests locally (non-containerized)
	PYTHONPATH=$(PROJECT_DIR_PATH) APP_DIR=$(PROJECT_DIR_PATH) PDB=$(PDB) uv run ./tests/tests_entrypoint.sh $(TEST_TARGET)

# TODO: write a script that does the rendering of the CLI docs via the mkdocs CLI
render-cli-doc: docker-build  ## Autogenerates the CLI help output as a markdown file
	docker run -it --rm \
		-v $(PROJECT_DIR_PATH):/project_src_mnt \
		--entrypoint /app/build_scripts/render-cli-docs.sh wv/plastered-test:latest

render-config-doc: docker-build  ## Autogenerates the config model fields as a markdown file.
	docker run -it --rm \
		-v $(PROJECT_DIR_PATH):/project_src_mnt \
		--entrypoint /app/build_scripts/render-config-markdown.sh wv/plastered-test:latest

docker-test: docker-build  ## Runs unit tests inside a local docker container
	docker run -it --rm -e SLOW_TESTS=$(SLOW_TESTS) -e PDB=$(PDB) \
		-v $(PROJECT_DIR_PATH)/docs:/docs \
		--entrypoint /app/tests/tests_entrypoint.sh wv/plastered-test:latest "$(TEST_TARGET)"
