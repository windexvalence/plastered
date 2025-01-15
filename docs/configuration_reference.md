# Configuration Reference

This doc covers the entire list of available configuration options for `plastered`.

> NOTE: You may check the full settings of your app (including default values) by running the following command:

```shell
# assuming you mounted your config to /config/config.yaml inside the container
docker run --rm -v /host/path/to/config/:/config ghcr.io/windexvalence/plastered:latest conf --config /config/config.yaml
```

## Config options reference table

Notably, a subset of the application options may be configured via the CLI options' equivalent, or via an environment variable. If said option is set via its corresponding CLI option and/or environment variable, then that value will take precedence over any value potentially set in your `config.yaml` file.

### `red` section parameters

The following parameters appear under the top-level `red` key in the YAML configuration:

<table>
    <tr><th>Parameter</th><th>Function</th><th>Required?</th><th>Default</th><th>CLI override?</th><th>Env var override?</th></tr>
    <tr><td>red_user_id</td><td>Your RED user ID which may be found in your user profile URL</td><td>Yes</td><td>None</td><td>--red-user-id</td><td>PLASTERED_RED_USER_ID</td></tr>
    <tr><td>red_api_key</td><td>Your RED API key</td><td>Yes</td><td>None</td><td>--red-api-key</td><td>PLASTERED_RED_API_KEY</td></tr>
    <tr><td>red_api_retries</td><td>Max # retries against RED API before failing</td><td>No</td><td>3</td><td>None</td><td>None</td></tr>
    <tr><td>red_api_seconds_between_calls</td><td>Min seconds to wait between RED API calls</td><td>No</td><td>5</td><td>None</td><td>None</td></tr>
</table>

### `lfm` section parameters

The following parameters appear under the top-level `lfm` key in the YAML configuration:

<table>
    <tr><th>Parameter</th><th>Function</th><th>Required?</th><th>Default</th><th>CLI override?</th><th>Env var override?</th></tr>
    <tr><td>lfm_api_key</td><td>Your LFM API key</td><td>Yes</td><td>None</td><td>--lfm-api-key</td><td>PLASTERED_LFM_API_KEY</td></tr>
    <tr><td>lfm_username</td><td>Your LFM Username</td><td>Yes</td><td>None</td><td>--lfm-username</td><td>PLASTERED_LFM_USERNAME</td></tr>
    <tr><td>lfm_password</td><td>Your LFM Password</td><td>Yes</td><td>None</td><td>--lfm-password</td><td>PLASTERED_LFM_PASSWORD</td></tr>
    <tr><td>lfm_api_retries</td><td>Max # retries against LFM API before failing</td><td>No</td><td>3</td><td>None</td><td>None</td></tr>
    <tr><td>lfm_api_seconds_between_calls</td><td>Min seconds to wait between LFM API calls</td><td>No</td><td>2</td><td>None</td><td>None</td></tr>
    <tr><td>enable_scraper_cache</td><td>enables/disables local caching of scraper results</td><td>No</td><td>true</td><td>None</td><td>None</td></tr>
    <tr><td>allow_library_items</td><td>Enable pulling LFM recs which LFM has recommended based on the artist existing in your library</td><td>No</td><td>False</td><td>None</td><td>None</td></tr>
    <tr><td>enable_scraper_cache</td><td>Indicate whether to cache the lfm recs results or not</td><td>No</td><td>True</td><td>None</td><td>None</td></tr>
</table>

<!-- <tr><td>param</td><td>function</td><td>Req</td><td>Default</td><td>cli</td><td>env</td></tr> -->

### `musicbrainz` section parameters

The following parameters appear under the top-level `musicbrainz` key in the YAML configuration:

<table>
    <tr><th>Parameter</th><th>Function</th><th>Required?</th><th>Default</th><th>CLI override?</th><th>Env var override?</th></tr>
    <tr><td>musicbrainz_api_max_retries</td><td>Max # retries against MB API before failing</td><td>No</td><td>3</td><td>None</td><td>None</td></tr>
    <tr><td>musicbrainz_api_seconds_between_calls</td><td>Min seconds to wait between MB API calls</td><td>No</td><td>2</td><td>None</td><td>None</td></tr>
</table>

### `search` section parameters

The following parameters appear under the top-level `search` key in the YAML configuration:

<table>
    <tr><th>Parameter</th><th>Function</th><th>Required?</th><th>Default</th><th>CLI override?</th><th>Env var override?</th></tr>
    <tr><td>use_release_type</td><td>Filter RED search by rec's release type field</td><td>No</td><td>true</td><td>None</td><td>None</td></tr>
    <tr><td>use_first_release_year</td><td>Filter RED search by rec's initial release year</td><td>No</td><td>true</td><td>None</td><td>None</td></tr>
    <tr><td>use_record_label</td><td>Filter RED search by rec's record label</td><td>No</td><td>false</td><td>None</td><td>None</td></tr>
    <tr><td>use_catalog_number</td><td>Filter RED search by rec's catalog number - experimental and unreliable</td><td>No</td><td>false</td><td>None</td><td>None</td></tr>
    <tr><td>enable_api_cache</td><td>Indicate whether to cache the lfm recs results or not</td><td>No</td><td>true</td><td>None</td><td>None</td></tr>
    <tr><td>use_fl_tokens</td><td>Enable the use of available RED FL tokens or not</td><td>No</td><td>false</td><td>None</td><td>None</td></tr>
</table>

### `snatches` section parameters

The following parameters appear under the top-level `snatches` key in the YAML configuration:

<table>
    <tr><th>Parameter</th><th>Function</th><th>Required?</th><th>Default</th><th>CLI override?</th><th>Env var override?</th></tr>
    <tr><td>snatch_directory</td><td>Mounted directory to save .torrent downloads</td><td>Yes</td><td>None</td><td>None</td><td>None</td></tr>
    <tr><td>snatch_recs</td><td>Enable/disable .torrent file downloading</td><td>Yes</td><td>None</td><td>None</td><td>None</td></tr>
    <tr><td>skip_prior_snatches</td><td>Do not search RED for LFM recs that are already in your snatch history</td><td>No</td><td>true</td><td>None</td><td>None</td></tr>
    <tr><td>max_size_gb</td><td>Max size, in GB, of any single RED snatch you wish to allow</td><td>Yes</td><td>None</td><td>None</td><td>None</td></tr>
</table>

### `format_preferences` section parameters

Format preferences dictate the file format, encoding, and source media which you want prioritized during the RED searches for the pulled LFM recommendations. The list is ordered from most-preferred to least-preferred. These values may only be configured in your config.yaml, and are not overridable via the CLI / environment variables.

The general structure of the `format_preferences` section is:

```yaml
format_preferences:
  - preference:
      format: "FLAC"
      encoding: "24bit+Lossless"
      media: "WEB"
  - preference:
      format: "FLAC"
      encoding: "Lossless"
      media: "CD"
      cd_only_extras:  # May optionally set this when the preference's media is "CD"
        log: 100
        has_cue: true
 # and so on ...
```

For each preference entry, at a bare minimum you must have the `format`, `encoding`, and `media` fields set, and each preference entry must be unique from the others. These options are describe below:

* `format`: The file format. Must be either `FLAC` or `MP3`
* `encoding`: The file encoding. Must be one of the following:
    * `"24bit+Lossless"` (24bit lossless)
    * `"LOSSLESS"` (standard 16bit losses)
    * `"MP3_320"` (MP3 CBR @ 320)
    * `"MP3_V0"` (MP3 VBR)
* `media`: The original source media. Must be one of the following:
    * `"CASSETTE"`
    * `"CD"`
    * `"SACD"`
    * `"VINYL"`
    * `"WEB"`

#### Additional CD-only preference fields

You may optionally set the additional CD-only `cd_only_extras` parameter for any preference entry which has `media` set to `"CD"`. Both sub-fields of the cd_only_extras parameter are optional, and defined below:

* `log`: indicate the CD log-score requirements. If set, this value may be one of `-1, 0, 1, 100`, to match the available log-score search params on RED.
* `has_cue`: indicate the CD cue requirements. If set, this value may be either `true`, or `false`.
