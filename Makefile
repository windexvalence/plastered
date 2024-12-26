# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'
PROJECT_DIR_PATH := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))
 
help:           ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

docker-clean:  ## Remove old local docker image and container artifacts
	docker ps -aq | xargs docker container stop
	docker ps -aq | xargs docker container rm
	docker images --filter=reference=wv/lastfm-recs-tests -q | xargs docker rmi -f
	docker images --filter=reference=wv/lastfm-recs -q | xargs docker rmi -f

docker-build:  ## Build the lastfm-recs docker image locally
	docker build -t wv/lastfm-recs:$$(date +%s) -t wv/lastfm-recs:latest .

docker-shell:  docker-build  ## Execs a local shell inside a locally built lastfm-recs docker container for testing and debugging
	docker run -it --rm wv/lastfm-recs:latest /bin/bash

docker-test-image: docker-build  ## Builds the test image
	docker build -t wv/lastfm-recs-tests:$$(date +%s) -t wv/lastfm-recs-tests:latest . -f tests/tests.Dockerfile

code-format-check: docker-test-image  ## Runs code-auto-formatting
	docker run -it --rm -e CODE_FORMAT_CHECK=1 -v $(PROJECT_DIR_PATH):/project_src_mnt --entrypoint /app/build_scripts/code-format.sh wv/lastfm-recs-tests:latest

code-format: docker-test-image  ## Runs code-auto-formatting
	docker run -it --rm -v $(PROJECT_DIR_PATH):/project_src_mnt --entrypoint /app/build_scripts/code-format.sh wv/lastfm-recs-tests:latest

docker-test: docker-test-image  ## Runs unit tests inside a local docker container
	docker run -it --rm wv/lastfm-recs-tests:latest
