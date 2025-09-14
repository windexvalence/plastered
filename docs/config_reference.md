# `plastered` 0.2.2 config reference

This doc is Auto-generated. If in doubt, refer to `examples/config.yaml`
# config

Pydantic settings class encapsulating the `plastered` application yaml config.

### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| red | `object` | ✅ | object |  |  | App settings defined under the plastered yaml config's top-level `red` key. |  |
| red.red_user_id | `integer` | ✅ | `0 < x ` |  |  |  |  |
| red.red_api_key | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
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
| red.snatches.min_allowed_ratio | `number` |  | number |  | `-1.0` |  |  |
| red.search | `object` |  | object |  |  | RED search settings defined in the plastered config at `red.search`. |  |
| red.search.use_release_type | `boolean` |  | boolean |  | `true` |  |  |
| red.search.use_first_release_year | `boolean` |  | boolean |  | `true` |  |  |
| red.search.use_record_label | `boolean` |  | boolean |  | `false` |  |  |
| red.search.use_catalog_number | `boolean` |  | boolean |  | `false` |  |  |
| lfm | `object` | ✅ | object |  |  |  |  |
| lfm.lfm_api_key | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm.lfm_username | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm.lfm_password | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm.lfm_api_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| lfm.lfm_api_seconds_between_calls | `integer` |  | `1 <= x <= 6` |  | `2` |  |  |
| lfm.rec_types_to_scrape | `array` |  | string |  |  |  |  |
| lfm.scraper_max_rec_pages_to_scrape | `integer` |  | `1 <= x <= 5` |  | `5` |  |  |
| lfm.allow_library_items | `boolean` |  | boolean |  | `false` |  |  |
| musicbrainz | `object` |  | object |  |  |  |  |
| musicbrainz.musicbrainz_api_max_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| musicbrainz.musicbrainz_api_seconds_between_calls | `integer` |  | `1 <= x <= 6` |  | `2` |  |  |
| cache | `object` |  | object |  |  |  |  |
| cache.api_cache_enabled | `boolean` |  | boolean |  | `true` |  |  |
| cache.scraper_cache_enabled | `boolean` |  | boolean |  | `true` |  |  |


---

# Definitions

## CacheConfig

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| api_cache_enabled | `boolean` |  | boolean |  | `true` |  |  |
| scraper_cache_enabled | `boolean` |  | boolean |  | `true` |  |  |

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
| lfm_api_key | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm_username | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm_password | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
| lfm_api_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| lfm_api_seconds_between_calls | `integer` |  | `1 <= x <= 6` |  | `2` |  |  |
| rec_types_to_scrape | `array` |  | string |  |  |  |  |
| scraper_max_rec_pages_to_scrape | `integer` |  | `1 <= x <= 5` |  | `5` |  |  |
| allow_library_items | `boolean` |  | boolean |  | `false` |  |  |

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
| red_api_key | `string` | ✅ | Length: `string >= 1` |  |  |  |  |
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
| snatches.min_allowed_ratio | `number` |  | number |  | `-1.0` |  |  |
| red_api_retries | `integer` |  | `1 <= x <= 10` |  | `3` |  |  |
| red_api_seconds_between_calls | `integer` |  | `2 <= x <= 10` |  | `5` |  |  |
| search | `object` |  | object |  |  | RED search settings defined in the plastered config at `red.search`. |  |
| search.use_release_type | `boolean` |  | boolean |  | `true` |  |  |
| search.use_first_release_year | `boolean` |  | boolean |  | `true` |  |  |
| search.use_record_label | `boolean` |  | boolean |  | `false` |  |  |
| search.use_catalog_number | `boolean` |  | boolean |  | `false` |  |  |

## SearchConfig

RED search settings defined in the plastered config at `red.search`.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| use_release_type | `boolean` |  | boolean |  | `true` |  |  |
| use_first_release_year | `boolean` |  | boolean |  | `true` |  |  |
| use_record_label | `boolean` |  | boolean |  | `false` |  |  |
| use_catalog_number | `boolean` |  | boolean |  | `false` |  |  |

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
| min_allowed_ratio | `number` |  | number |  | `-1.0` |  |  |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown).
