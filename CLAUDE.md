# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`plastered` pulls a user's Last.fm (LFM) album/track recommendations and automatically snatches the matching releases from RED (a private music tracker). It runs both as a CLI (`scrape`/`conf`/`cache`/`init_conf`) and as a FastAPI web server. It is download-client- and library-agnostic — it only writes `.torrent` files to a configured directory.

## Common commands

All workflows go through the `Makefile` and `uv` (Python 3.12). Run `make` for the full target list.

- `make test` — run all tests (non-containerized). Sets `PYTHONPATH`/`APP_DIR` and calls `tests/tests_entrypoint.sh`.
- `make test TEST_TARGET=tests/utils_tests/test_http_utils.py` — run a single test file.
- `make test TEST_TARGET=tests/utils_tests/test_http_utils.py::test_throttle` — run a single test function.
- `make test PDB=1` — run serially (no `xdist`) and drop into pdb on failure.
- `make fmt` — auto-format + lint (ruff format, `ruff check --fix`, bandit). `make fmt-check` is the check-only variant used in CI.
- `make mypy` — type-check (`mypy --config-file pyproject.toml .`).
- `make docker-server APP_CONFIG_DIR=<dir>` — run the web server locally at http://localhost:8000.
- `make docker-build-no-test` then `docker run …` — run the CLI locally (Playwright deps make host-only CLI runs impractical; see `docs/contributing/development_guide.md`).

### Test details

- Test runner config lives in `pyproject.toml` `[tool.pytest.ini_options]`. Coverage `fail_under = 100` — **new code must be fully covered** or use the documented `pragma: no cover` / `exclude_also` patterns already in the codebase.
- Sockets are disabled in tests (`--disable-socket`); HTTP is mocked via `pytest-httpx`. Tests run in parallel with `pytest -n auto --dist=loadfile`.
- Markers gate optional suites: `slow` (run in CI or with `--slowtests`), `releasetest` (release builds only, `--releasetests`). See also `no_autouse_mock_lifespan_singleton_inst` and `override_global_httpx_mock` for opting out of autouse fixtures.
- `tests/conftest.py` sets `PLASTERED_CONFIG` to `examples/config.yaml` before any imports — config loads eagerly at import time, so import order matters.

## Architecture

### Request → snatch flow (CLI `scrape`)

1. `cli.py` builds an `AppSettings` via `get_app_settings()`, merging `config.yaml` + env vars (`PLASTERED_*`) + CLI overrides, then calls `scrape_action` (`plastered/actions/common_actions.py`).
2. `LFMRecsScraper` (`plastered/scraper/lfm_scraper.py`) uses Playwright (rebrowser-playwright) to scrape recommendation pages into `dict[EntityType, list[LFMRec]]`.
3. `ReleaseSearcher` (`plastered/release_search/release_searcher.py`) is the orchestrator. It owns four httpx API clients (LFM, MusicBrainz, RED, RED-snatch), a `RunCache`, and a `SearchState`. It wraps each `LFMRec` in a `SearchItem` and runs them through the processor chain, then snatches matches.

### The processor chain (core of release_search)

`SearchItemProcessorChain` (`processors/chains.py`) defines an **ordered tuple of processors** — separate `album_chain` and `track_chain`. Each `SearchItem` is passed through every processor in order; the first one to reject it short-circuits and drops the item (returns `None`).

Two processor kinds, both defined in `processors/bases.py`:
- **Modifiers** (`SearchItemModifier`, `processors/modifiers.py`) — enrich the `SearchItem` in place (attach search ID, resolve LFM album/track info, resolve MusicBrainz release/MBID, query the RED browse endpoint). Always return the item.
- **Filters** (`SearchItemFilter`, `processors/filters.py`) — return the item to keep it or `None` to drop it. Filters delegate their actual rules to `SearchState` methods (e.g. already-snatched, rec-context, required-fields-present, dupe, size limits) and record a `SkipReason`.

When adding/reordering search logic, edit the chain tuples in `chains.py` and add the corresponding modifier/filter.

### SearchState

`SearchState` (`release_search/search_helpers.py`) holds the mutable per-run state and **all the filtering business rules**: RED user ratio/quota limits, prior-snatch dedup, building RED browse query params, and `get_search_items_to_snatch()` which sorts candidates largest-first (to optimize FL token use) and caps the cumulative download by the allowed ratio limit. It also writes `SearchRecord` status rows (`IN_PROGRESS` → `GRABBED`/`SKIPPED`/`FAILED`).

### Config (`plastered/config/app_settings.py`)

`AppSettings` is a pydantic-settings `BaseSettings` composed of frozen pydantic sub-models (`SearchConfig`, `SnatchesConfig`, `FormatPreference`, etc.). Sources merge in this precedence: CLI overrides > env (`PLASTERED_*`) > YAML. The config doc at `docs/config_reference.md` is **auto-generated** from these models — after changing config fields, regenerate via `make render-config-doc` (a `deploy_tests` test asserts the docs are fresh).

### API clients (`plastered/utils/httpx_utils/`)

All clients subclass `ThrottledAPIBaseClient` (`base_client.py`), which wraps `httpx.Client` with a custom retry transport (`HTTPXRetryTransport`, tenacity-based) and per-API rate limiting. Each client takes a shared `RunCache`. Responses are optionally cached on disk via diskcache (`plastered/run_cache/run_cache.py`); cache types are `API` and `SCRAPER`, managed by the CLI `cache` command.

### Web server (`plastered/api/`)

NOTE: the web server is experimental and not all features are fully implemnented.

`api/main.py` is the FastAPI entrypoint. A lifespan context (`api/lifespan_resources.py`, `LifespanSingleton`) initializes the SQLite DB (`db_startup`) and shared singletons. Routes split into `api/routes/api_routes.py` (JSON API) and `webserver_routes.py` (HTML via jinja2-fragments, with `static/` + `templates/`). The manual-search endpoint calls `ReleaseSearcher.manual_search()`.

### Persistence (`plastered/db/`)

SQLModel over SQLite. `SearchRecord` is the main results table; status/skip/fail enums (`Status`, `SkipReason`, `FailReason`) live in `db/db_models.py`.

## Conventions

- **`from __future__ import annotations`** and heavy use of `TYPE_CHECKING` import blocks — ruff's `flake8-type-checking` (`TC`) rules are enforced; keep runtime-only imports out of `TYPE_CHECKING`.
- ruff line length is 120; `E501`/`E203` are ignored (formatter handles wrapping). Tests are excluded from lint (`[tool.ruff.lint] exclude`).
- Raising bare `Exception` is banned (`TRY002`); use the typed exceptions in `plastered/utils/exceptions.py`.
- Domain models are re-exported from `plastered/models/__init__.py` and clients from `plastered/utils/httpx_utils/__init__.py` — import from the package, not the submodule.
- `mypy` runs with the pydantic plugin; tests and `build_scripts` are excluded from type-checking.
- **Prefer `anyio` over `asyncio`.** FastAPI/Starlette run on anyio, so avoid the `asyncio` stdlib module (event loop, `asyncio.Lock`/`sleep`/`create_task`, etc.) whenever an anyio equivalent fits — e.g. offload blocking sync work with `starlette.concurrency.run_in_threadpool` (anyio's `to_thread`), use `anyio` sync primitives in async code, and use plain `threading` primitives only for coordinating sync worker-thread code. For async tests, use `@pytest.mark.anyio` with the `anyio_backend` fixture (`tests/conftest.py`), not `pytest-asyncio`.
