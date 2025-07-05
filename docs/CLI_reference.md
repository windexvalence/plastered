# `plastered` CLI Reference (v0.2.2)

> NOTE: this doc is auto-generated from the CLI source code. For a more thorough version of this information, run `plastered --help`, as outlined in the user guide.
plastered: Finds your LFM recs and snatches them from RED.

**Usage:**

```text
plastered [OPTIONS] COMMAND [ARGS]...
```

**Options:**

```text
  --version                       Show the version and exit.
  -v, --verbosity [debug|info|warning|error]
                                  Sets the logging level.  [default: WARNING]
  --red-user-id INTEGER
  --red-api-key TEXT
  --lfm-api-key TEXT
  --lfm-username TEXT
  --lfm-password TEXT
  --help                          Show this message and exit.
```

## cache

Helper command to inspect or empty the local run cache(s). See this docs page for more info on the run cache: https://github.com/windexvalence/plastered/blob/main/docs/configuration_reference.md

**Usage:**

```text
plastered cache [OPTIONS] {api|scraper|@all}
```

**Options:**

```text
  -c, --config PATH  Absolute path to the application config.yaml file.  [env
                     var: PLASTERED_CONFIG; required]
  --info             Print meta-info about the disk cache(s).
  --empty            When present, clear cache specified by the command
                     argument.
  --check            Verify / try to fix diskcache consistency for specified
                     cache argument.
  --list-keys        When present, list all the current keys available in the
                     cache
  --read-value TEXT  Retrieves the string representation of the value for the
                     specified cache key.
  --help             Show this message and exit.
```

## conf

Output the contents of your existing config.yaml, along with any default values and/or CLI option overrides.

**Usage:**

```text
plastered conf [OPTIONS]
```

**Options:**

```text
  -c, --config PATH  Absolute path to the application config.yaml file.  [env
                     var: PLASTERED_CONFIG; required]
  --help             Show this message and exit.
```

## init-conf

Output the contents of a template starter config to aid in initial app setup. Output may be redirected to the desired config filepath on your host machine.

**Usage:**

```text
plastered init-conf [OPTIONS]
```

**Options:**

```text
  --help  Show this message and exit.
```

## inspect-stats

Gather and inspect the summary stats of a prior scrape run identified by the specified run_date.

**Usage:**

```text
plastered inspect-stats [OPTIONS]
```

**Options:**

```text
  -c, --config PATH               Absolute path to the application config.yaml
                                  file.  [env var: PLASTERED_CONFIG; required]
  -d, --run-date [%Y-%m-%d__%H-%M-%S]
                                  Specify the exact run date to inspect.
                                  Overrides the default interactive prompts
                                  for choosing the run date to inspect.
  --help                          Show this message and exit.
```

## scrape

Run the app to pull LFM recs and snatch them from RED, per the settings of your config.yaml along with any CLI overrides you provide.

**Usage:**

```text
plastered scrape [OPTIONS]
```

**Options:**

```text
  -c, --config PATH               Absolute path to the application config.yaml
                                  file.  [env var: PLASTERED_CONFIG; required]
  --no-snatch                     When present, disables downloading the
                                  .torrent files matched to your LFM recs
                                  results.
  -r, --rec-types [album|track|@all]
                                  Indicate what type of LFM recs to scrape and
                                  snatch. Defaults to 'rec_types_to_scrape'
                                  config setting otherwise.
  --help                          Show this message and exit.
```
