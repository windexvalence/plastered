# `plastered` 1.2.1.dev0+gd90b7d9f8.d20260818 config reference

This doc is Auto-generated. If in doubt, refer to `examples/config.yaml`
# config

Pydantic settings class encapsulating the `plastered` application yaml config.

### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| red | `object` | ✅ | object |  |  | App settings defined under the plastered yaml config's top-level `red` key. |  |
| red.red_user_id | `integer` | ✅ | `0 < x ` |  |  |  |  |
| red.red_api_key | `string` | ✅ | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| red.red_api_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| red.red_api_seconds_between_calls | `integer` |  | `2 <= x <= 10` |  | `5` |  |  |
| red.format_preferences | `array` | ✅ | object |  |  |  |  |
| red.format_preferences[].format | `string` | ✅ | `FLAC` `MP3` |  |  | Enum class to map to the supported file format search fields on the RED API |  |
| red.format_preferences[].encoding | `string` | ✅ | `24bit+Lossless` `Lossless` `320` `V0+(VBR)` |  |  | Enum class to map to the supported encoding search fields on the RED API |  |
| red.format_preferences[].media | `string` | ✅ | `ANY` `Cassette` `CD` `SACD` `Vinyl` `WEB` |  |  | Enum class to map to the supported media search fields on the RED API |  |
| red.format_preferences[].cd_only_extras | `object` or `null` |  | object |  | `null` |  |  |
| red.snatches | `object` | ✅ | object |  |  | RED snatch settings defined in the plastered config at `red.snatches`. |  |
| red.snatches.snatch_directory | `string` | ✅ | Format: [`path`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| red.snatches.snatch_recs | `boolean` | ✅ | boolean |  |  |  |  |
| red.snatches.max_size_gb | `number` | ✅ | `0.02 <= x <= 100.0` |  |  |  |  |
| red.snatches.skip_prior_snatches | `boolean` |  | boolean |  | `true` |  |  |
| red.snatches.use_fl_tokens | `boolean` |  | boolean |  | `false` |  |  |
| red.snatches.min_allowed_ratio | `number` |  | number |  | `-1.0` | Ratio floor for scraper runs: candidate snatches are dropped (largest-first) once the run's cumulative download would push the RED ratio below this value. Any value <= 0 (the default) disables the cap entirely. Not applicable to ad-hoc searches, which are explicit user-initiated downloads. |  |
| red.search | `object` |  | object |  |  | RED search settings defined in the plastered config at `red.search`. |  |
| red.search.use_release_type | `boolean` |  | boolean |  | `true` | Filter candidate RED release groups to the release type (album/EP/single/...) resolved from MusicBrainz. A scraper rec whose release type cannot be resolved is skipped. |  |
| red.search.use_first_release_year | `boolean` |  | boolean |  | `true` | Filter candidate RED release groups to the original release year resolved from MusicBrainz. When the year filter would eliminate every candidate group, it is skipped for that item (the year should narrow a match, never kill it). A scraper rec whose release year cannot be resolved is skipped. |  |
| red.search.use_record_label | `boolean` |  | boolean |  | `false` | Prefer candidate RED release groups whose record label matches the one resolved from MusicBrainz. A ranking signal only: a mismatched or unresolved label never drops a candidate. |  |
| red.search.use_catalog_number | `boolean` |  | boolean |  | `false` | Prefer candidate RED release groups whose catalogue number matches the one resolved from MusicBrainz. A ranking signal only: a mismatched or unresolved catalogue number never drops a candidate. |  |
| red.search.fuzzy_search_enabled | `boolean` |  | boolean |  | `false` | Opt-in fuzzy title matching of RED release groups: in addition to exact/word-subset matches, accept groups whose (normalized) name is highly similar to the wanted release title. Improves the hit rate for titles with punctuation/edition-suffix differences, at some risk of false-positive matches. |  |
| lfm | `object` | ✅ | object |  |  |  |  |
| lfm.lfm_api_key | `string` | ✅ | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| lfm.lfm_username | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm.lfm_password | `string` | ✅ | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| lfm.lfm_api_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| lfm.lfm_api_seconds_between_calls | `integer` |  | `1 <= x <= 6` |  | `2` |  |  |
| lfm.rec_types_to_scrape | `array` |  | string |  |  |  |  |
| lfm.scraper_max_rec_pages_to_scrape | `integer` |  | `1 <= x <= 5` |  | `5` |  |  |
| lfm.allow_library_items | `boolean` or `null` |  | boolean |  | `null` | DEPRECATED and ignored: LFM rec-context filtering has been removed (LFM's 'in your library' context refers to the rec's artist, not the release itself). Use `red.snatches.skip_prior_snatches` to skip releases you already have. Remove this option from your config; it will be rejected in a future release. |  |
| musicbrainz | `object` |  | object |  |  |  |  |
| musicbrainz.musicbrainz_api_max_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| musicbrainz.musicbrainz_api_seconds_between_calls | `integer` |  | `1 <= x <= 6` |  | `2` |  |  |
| server | `object` |  | object |  |  | Config section for the plastered API server. |  |
| server.host | `string` |  | string |  | `"0.0.0.0"` |  |  |
| server.port | `integer` |  | integer |  | `80` |  |  |
| server.log_level | `string` |  | string |  | `"INFO"` |  |  |
| server.auth | `object` |  | object |  |  | Optional config section for the plastered API server's authentication setup.

plastered supports a single user: when `enable_login_protection` is on, every request (outside a small exempt
set — see `plastered.api.middleware`) must carry a session token obtained from `POST /api/auth/login` (or the
browser `/login` page) using the `username`/`password` configured here. |  |
| server.auth.enable_login_protection | `boolean` |  | boolean |  | `false` | Opt-in: when true, all routes require a session token from a successful `/api/auth/login`. |  |
| server.auth.username | `string` or `null` |  | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  | `null` |  |  |
| server.auth.password | `string` or `null` |  | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  | `null` |  |  |
| server.auth.session_ttl_hours | `integer` |  | `0 <= x ` |  | `168` | How long a login token stays valid before a new login is required. Setting to zero disables expiration. Not recommended. |  |
| server.workers | `integer` |  | integer |  | `1` |  |  |


---

# Definitions

## AuthConfig

Optional config section for the plastered API server's authentication setup.

plastered supports a single user: when `enable_login_protection` is on, every request (outside a small exempt
set — see `plastered.api.middleware`) must carry a session token obtained from `POST /api/auth/login` (or the
browser `/login` page) using the `username`/`password` configured here.

#### Type: `object`

> ⚠️ Additional properties are not allowed.

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| enable_login_protection | `boolean` |  | boolean |  | `false` | Opt-in: when true, all routes require a session token from a successful `/api/auth/login`. |  |
| username | `string` |  | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  | `null` |  |  |
| password | `string` |  | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  | `null` |  |  |
| session_ttl_hours | `integer` |  | `0 <= x ` |  | `168` | How long a login token stays valid before a new login is required. Setting to zero disables expiration. Not recommended. |  |

## CdOnlyExtras

RED settings defined for a `red.format_preferences.cd_only_extras` entry in the plasterd yaml config.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| log | `integer` | ✅ | integer |  |  |  |  |
| has_cue | `boolean` | ✅ | boolean |  |  |  |  |

## EncodingEnum

Enum class to map to the supported encoding search fields on the RED API

#### Type: `string`

**Possible Values:** `24bit+Lossless` or `Lossless` or `320` or `V0+(VBR)`

## FormatEnum

Enum class to map to the supported file format search fields on the RED API

#### Type: `string`

**Possible Values:** `FLAC` or `MP3`

## FormatPreference

RED settings entry for a `red.format_preferences` entry in the plastered yaml config.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| format | `string` | ✅ | `FLAC` `MP3` |  |  | Enum class to map to the supported file format search fields on the RED API |  |
| encoding | `string` | ✅ | `24bit+Lossless` `Lossless` `320` `V0+(VBR)` |  |  | Enum class to map to the supported encoding search fields on the RED API |  |
| media | `string` | ✅ | `ANY` `Cassette` `CD` `SACD` `Vinyl` `WEB` |  |  | Enum class to map to the supported media search fields on the RED API |  |
| cd_only_extras | `object` |  | object |  | `null` |  |  |

## LFMConfig

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| lfm_api_key | `string` | ✅ | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| lfm_username | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm_password | `string` | ✅ | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| lfm_api_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| lfm_api_seconds_between_calls | `integer` |  | `1 <= x <= 6` |  | `2` |  |  |
| rec_types_to_scrape | `array` |  | string |  |  |  |  |
| scraper_max_rec_pages_to_scrape | `integer` |  | `1 <= x <= 5` |  | `5` |  |  |
| allow_library_items | `boolean` |  | boolean |  | `null` | DEPRECATED and ignored: LFM rec-context filtering has been removed (LFM's 'in your library' context refers to the rec's artist, not the release itself). Use `red.snatches.skip_prior_snatches` to skip releases you already have. Remove this option from your config; it will be rejected in a future release. |  |

## MediaEnum

Enum class to map to the supported media search fields on the RED API

#### Type: `string`

**Possible Values:** `ANY` or `Cassette` or `CD` or `SACD` or `Vinyl` or `WEB`

## MusicBrainzConfig

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| musicbrainz_api_max_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| musicbrainz_api_seconds_between_calls | `integer` |  | `1 <= x <= 6` |  | `2` |  |  |

## RedConfig

App settings defined under the plastered yaml config's top-level `red` key.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| red_user_id | `integer` | ✅ | `0 < x ` |  |  |  |  |
| red_api_key | `string` | ✅ | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| format_preferences | `array` | ✅ | object |  |  |  |  |
| format_preferences[].format | `string` | ✅ | `FLAC` `MP3` |  |  | Enum class to map to the supported file format search fields on the RED API |  |
| format_preferences[].encoding | `string` | ✅ | `24bit+Lossless` `Lossless` `320` `V0+(VBR)` |  |  | Enum class to map to the supported encoding search fields on the RED API |  |
| format_preferences[].media | `string` | ✅ | `ANY` `Cassette` `CD` `SACD` `Vinyl` `WEB` |  |  | Enum class to map to the supported media search fields on the RED API |  |
| format_preferences[].cd_only_extras | `object` |  | object |  | `null` |  |  |
| snatches | `object` | ✅ | object |  |  | RED snatch settings defined in the plastered config at `red.snatches`. |  |
| snatches.snatch_directory | `string` | ✅ | Format: [`path`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| snatches.snatch_recs | `boolean` | ✅ | boolean |  |  |  |  |
| snatches.max_size_gb | `number` | ✅ | `0.02 <= x <= 100.0` |  |  |  |  |
| snatches.skip_prior_snatches | `boolean` |  | boolean |  | `true` |  |  |
| snatches.use_fl_tokens | `boolean` |  | boolean |  | `false` |  |  |
| snatches.min_allowed_ratio | `number` |  | number |  | `-1.0` | Ratio floor for scraper runs: candidate snatches are dropped (largest-first) once the run's cumulative download would push the RED ratio below this value. Any value <= 0 (the default) disables the cap entirely. Not applicable to ad-hoc searches, which are explicit user-initiated downloads. |  |
| red_api_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| red_api_seconds_between_calls | `integer` |  | `2 <= x <= 10` |  | `5` |  |  |
| search | `object` |  | object |  |  | RED search settings defined in the plastered config at `red.search`. |  |
| search.use_release_type | `boolean` |  | boolean |  | `true` | Filter candidate RED release groups to the release type (album/EP/single/...) resolved from MusicBrainz. A scraper rec whose release type cannot be resolved is skipped. |  |
| search.use_first_release_year | `boolean` |  | boolean |  | `true` | Filter candidate RED release groups to the original release year resolved from MusicBrainz. When the year filter would eliminate every candidate group, it is skipped for that item (the year should narrow a match, never kill it). A scraper rec whose release year cannot be resolved is skipped. |  |
| search.use_record_label | `boolean` |  | boolean |  | `false` | Prefer candidate RED release groups whose record label matches the one resolved from MusicBrainz. A ranking signal only: a mismatched or unresolved label never drops a candidate. |  |
| search.use_catalog_number | `boolean` |  | boolean |  | `false` | Prefer candidate RED release groups whose catalogue number matches the one resolved from MusicBrainz. A ranking signal only: a mismatched or unresolved catalogue number never drops a candidate. |  |
| search.fuzzy_search_enabled | `boolean` |  | boolean |  | `false` | Opt-in fuzzy title matching of RED release groups: in addition to exact/word-subset matches, accept groups whose (normalized) name is highly similar to the wanted release title. Improves the hit rate for titles with punctuation/edition-suffix differences, at some risk of false-positive matches. |  |

## SearchConfig

RED search settings defined in the plastered config at `red.search`.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| use_release_type | `boolean` |  | boolean |  | `true` | Filter candidate RED release groups to the release type (album/EP/single/...) resolved from MusicBrainz. A scraper rec whose release type cannot be resolved is skipped. |  |
| use_first_release_year | `boolean` |  | boolean |  | `true` | Filter candidate RED release groups to the original release year resolved from MusicBrainz. When the year filter would eliminate every candidate group, it is skipped for that item (the year should narrow a match, never kill it). A scraper rec whose release year cannot be resolved is skipped. |  |
| use_record_label | `boolean` |  | boolean |  | `false` | Prefer candidate RED release groups whose record label matches the one resolved from MusicBrainz. A ranking signal only: a mismatched or unresolved label never drops a candidate. |  |
| use_catalog_number | `boolean` |  | boolean |  | `false` | Prefer candidate RED release groups whose catalogue number matches the one resolved from MusicBrainz. A ranking signal only: a mismatched or unresolved catalogue number never drops a candidate. |  |
| fuzzy_search_enabled | `boolean` |  | boolean |  | `false` | Opt-in fuzzy title matching of RED release groups: in addition to exact/word-subset matches, accept groups whose (normalized) name is highly similar to the wanted release title. Improves the hit rate for titles with punctuation/edition-suffix differences, at some risk of false-positive matches. |  |

## ServerConfig

Config section for the plastered API server.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| host | `string` |  | string |  | `"0.0.0.0"` |  |  |
| port | `integer` |  | integer |  | `80` |  |  |
| log_level | `string` |  | string |  | `"INFO"` |  |  |
| auth | `object` |  | object |  |  | Optional config section for the plastered API server's authentication setup.

plastered supports a single user: when `enable_login_protection` is on, every request (outside a small exempt
set — see `plastered.api.middleware`) must carry a session token obtained from `POST /api/auth/login` (or the
browser `/login` page) using the `username`/`password` configured here. |  |
| auth.enable_login_protection | `boolean` |  | boolean |  | `false` | Opt-in: when true, all routes require a session token from a successful `/api/auth/login`. |  |
| auth.username | `string` |  | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  | `null` |  |  |
| auth.password | `string` |  | Format: [`password`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  | `null` |  |  |
| auth.session_ttl_hours | `integer` |  | `0 <= x ` |  | `168` | How long a login token stays valid before a new login is required. Setting to zero disables expiration. Not recommended. |  |
| workers | `integer` |  | integer |  | `1` |  |  |

## SnatchesConfig

RED snatch settings defined in the plastered config at `red.snatches`.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| snatch_directory | `string` | ✅ | Format: [`path`](https://json-schema.org/understanding-json-schema/reference/string#built-in-formats) |  |  |  |  |
| snatch_recs | `boolean` | ✅ | boolean |  |  |  |  |
| max_size_gb | `number` | ✅ | `0.02 <= x <= 100.0` |  |  |  |  |
| skip_prior_snatches | `boolean` |  | boolean |  | `true` |  |  |
| use_fl_tokens | `boolean` |  | boolean |  | `false` |  |  |
| min_allowed_ratio | `number` |  | number |  | `-1.0` | Ratio floor for scraper runs: candidate snatches are dropped (largest-first) once the run's cumulative download would push the RED ratio below this value. Any value <= 0 (the default) disables the cap entirely. Not applicable to ad-hoc searches, which are explicit user-initiated downloads. |  |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown).
