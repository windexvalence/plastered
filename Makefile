# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'
PROJECT_DIR_PATH := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))
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

help:           ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

docker-clean:  ## Remove old local docker image and container artifacts
	docker ps -aq | xargs docker container stop
	docker ps -aq | xargs docker container rm
	docker images "*/*plastered*" -q | xargs docker rmi -f

clean:  docker-clean ## Removes docker artifacts and any local pycache artifacts
	find . -type d -name '__pycache__' -print | xargs rm -rf

docker-build:  ## Build the plastered docker app and test images locally
	docker build --target plastered-app -t wv/plastered:$$(date +%s) -t wv/plastered:latest .
	docker build --target plastered-test -t wv/plastered-test:$$(date +%s) -t wv/plastered-test:latest .

docker-build-no-test:  ## Build the plastered docker image locally without test-requirements installed
	docker build --target plastered-app --build-arg BUILD_ENV=non-test -t wv/plastered:non-test .

docker-shell:  docker-build  ## Execs a local shell inside a locally built plastered docker container for testing and debugging
	docker run -it --rm --entrypoint /bin/bash wv/plastered-test:latest

docker-py-shell:  docker-build  ## Execs a local python shell inside a locally built plastered docker container for testing and debugging
	docker run -it --rm --env PYTHONPATH=/app --entrypoint python wv/plastered-test:latest -i

fmt-check: docker-build  ## Runs code-auto-formatting checks, lint checks, and security checks
	docker run -t --rm -e CODE_FORMAT_CHECK=1 \
		-v $(PROJECT_DIR_PATH):/project_src_mnt \
		--entrypoint /app/build_scripts/code-format.sh wv/plastered-test:latest

fmt: docker-build  ## Runs code-auto-formatting, followed by lint checks, and then security checks
	docker run -it --rm \
		-v $(PROJECT_DIR_PATH):/project_src_mnt \
		--entrypoint /app/build_scripts/code-format.sh wv/plastered-test:latest

mypy:  ## Runs mypy type checking
	uv run mypy --config-file pyproject.toml .

test:  ## Runs unit tests locally (non-containerized)
	PYTHONPATH=$(PROJECT_DIR_PATH) APP_DIR=$(PROJECT_DIR_PATH) uv run pytest -n auto -vv $(TEST_TARGET)

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
