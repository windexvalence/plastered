# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'
PROJECT_DIR_PATH := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))

help:           ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

docker-clean:  ## Remove old local docker image and container artifacts
	docker ps -aq | xargs docker container stop
	docker ps -aq | xargs docker container rm
	docker images --filter=reference=wv/last-red-recs -q | xargs docker rmi -f

clean:  docker-clean ## Removes docker artifacts and any local pycache artifacts
	find . -type d -name '__pycache__' -print | xargs rm -rf

docker-build:  ## Build the last-red-recs docker image locally
	docker build -t wv/last-red-recs:$$(date +%s) -t wv/last-red-recs:latest .

docker-build-no-test:  ## Build the last-red-recs docker image locally without test-requirements installed
	docker build --build-arg BUILD_ENV=non-test -t wv/last-red-recs:non-test .

docker-shell:  docker-build  ## Execs a local shell inside a locally built last-red-recs docker container for testing and debugging
	docker run -it --rm --entrypoint /bin/bash wv/last-red-recs:latest

code-format-check: docker-build  ## Runs code-auto-formatting checks, lint checks, and security checks
	docker run -t --rm -e CODE_FORMAT_CHECK=1 -v $(PROJECT_DIR_PATH):/project_src_mnt --entrypoint /app/build_scripts/code-format.sh wv/last-red-recs:latest

code-format: docker-build  ## Runs code-auto-formatting, followed by lint checks, and then security checks
	docker run -it --rm -v $(PROJECT_DIR_PATH):/project_src_mnt --entrypoint /app/build_scripts/code-format.sh wv/last-red-recs:latest

docker-test: docker-build  ## Runs unit tests inside a local docker container
	docker run -it --rm -v $(PROJECT_DIR_PATH)/docs:/docs --entrypoint /app/tests/tests_entrypoint.sh wv/last-red-recs:latest
