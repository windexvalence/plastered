# plastered 1.0.0

`plastered` is now a web application. The CLI is gone — everything runs through a FastAPI server driven from the browser, launched with `plastered run --config <path-to-config.yaml>`.

## New Features + Improvements

* Added a web UI (FastAPI + HTMX): the Docker image now starts the server by default, with host/port/log-level/workers configured via the new `server` config section.
* Added an ad-hoc release search page (`/adhoc`) + matching JSON endpoints (`POST /api/adhoc_search`, `GET /api/adhoc_result`). Requires just an artist + release/track name; optional fields (mbid, release type, year, label, catalog number) refine the RED search, and per-request overrides of format preferences / search / snatch settings are supported.
* Added search-only ad-hoc runs: matches are recorded as `MATCHED` and can be downloaded after review via a per-result Download button.
* Added an LFM scraper page (`/lfm_recommendations_scraper`): pick the rec type, toggle downloads, watch live progress (scraping -> searching, processed/total recs) and a completion summary.
* Rebuilt `/run_history` as a paginated accordion view with status/artist/entity filters, sort direction, and search-id lookup. Scraper runs get their own rows showing the run summary + every rec pulled, including a per-rec skip/fail reason. The JSON `/api/run_history` endpoint is unchanged.
* Added retroactive downloads for scraper runs that ran with downloads disabled: matched recs are now persisted instead of discarded, and can be selectively (or bulk) snatched later from `/run_history`.
* Added optional login protection (`server.auth` config section, off by default): session tokens via `Authorization: Bearer` header or HttpOnly cookie, `/login` page, login/logout endpoints, nav-bar log out.
* Restyled the UI with a dark, red-accented private-tracker theme (dark wood background, panelled layout, Help button on every page).
* Reduced RED API usage: one format-agnostic browse call per recommendation (torrents are ranked against format preferences client-side instead of one browse per preference), input recs are deduped before processing, and unneeded musicbrainz lookups are skipped in the scraper flow.
* Enforce the RED rate limit globally: server defaults to 1 worker and the client throttle is thread-safe, so concurrent requests can never collectively exceed 1 request per `red_api_seconds_between_calls`.
* Made the scraper resilient to LFM client-side navigations mid-scrape (bounded retries waiting for network idle instead of a hard failure).
* Docker images are now published for both `linux/amd64` and `linux/arm64` platforms.
* Reduced the Docker image size: `uv`/`uvx` are no longer shipped in the app image (bind-mounted at build time only), runtime bytecode writes are disabled (`PYTHONDONTWRITEBYTECODE=1`), and the font cleanup during the image build now actually deletes `.ttc`/`.ttf` files (a `find` precedence bug meant only `.otf` files were removed).

## Bug Fixes

* Fixed RED searches stopping after the top format preference when it returned no results, instead of falling through to lower preferences.
* Fixed a track rec that failed origin-release resolution aborting the entire scrape run.
* Fixed prior-snatch dedup never working for track searches (compared track name against a release-keyed dict).
* Fixed crashes on a null or RED-unmapped musicbrainz release type (now falls back to `UNKNOWN`).
* Fixed a malformed LFM album blob crashing track resolution instead of falling through to musicbrainz.
* Fixed processor skip logs naming the metaclass (`ABCMeta`) instead of the actual filter class.

## Breaking Changes

* Removed the CLI entirely (`scrape` / `conf` / `cache` / `init_conf`). The only entrypoint is `plastered run --config <path>`; scrapes are run from the browser or `POST /api/scrape`. `docs/CLI_reference.md` is removed with it.
* Removed API response caching: the RED / LFM / musicbrainz clients always hit the network (throttled). `RunCache` remains only for the scraper's page cache. The `cache.api_cache_enabled` config field is removed.
* Reworked configuration as pydantic-settings models: env vars (`PLASTERED_*`) take precedence over the YAML file. Check `docs/config_reference.md` + `examples/config.yaml` when migrating.
* Moved server launch params (host, port, log level, workers) into the `server` config section. `workers` defaults to 1 — raising it risks exceeding RED's rate limit.
* Removed the `plastered.stats` module.
* Replaced the manual-search flow with the generalized ad-hoc search (`ManualSearch` -> `AdhocSearch`).
* The Docker image's default entrypoint is now the server; the config path is provided via `PLASTERED_CONFIG`.

## Development Improvements

* Enforce 100% test coverage; suite grew to ~740 tests with dedicated packages for the processor chain, snatcher, and API clients.
* Standardized on `anyio` over `asyncio` (dropped `pytest-asyncio` in favor of anyio's pytest plugin).
* Fixed two test-isolation leaks that caused flaky failures under `pytest-xdist`.
* Moved all shared server state (API clients, settings, DB startup) into a FastAPI lifespan singleton.
* Removed dead code across two holistic sweeps (vulture + reference greps), including ~680 lines of commented-out tests.
* Expanded the ruff rule set and consolidated code-check paths into shared hook scripts used by both local runs and CI.
* Added an FAQ doc; the config reference is now auto-generated from the pydantic models (`make render-config-doc`).
* Consolidated all styles into a single `classless.css`; HTMX + CSS are pulled at image build time instead of from CDNs.
* Bumped production + development dependency groups (uv lockfile verified via `uv lock --check` in the Docker build).
* Fixed the `.dockerignore` whitelist excluding `hooks/` from the image build (breaking the containerized CI code-check scripts) and removed stale entries for deleted files.

**Full Changelog**: https://github.com/windexvalence/plastered/compare/v0.2.2...v1.0.0
