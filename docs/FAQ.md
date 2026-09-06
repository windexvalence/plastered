# Frequently Asked Questions

## What is `plastered`?

`plastered` is a self-hosted web app for automatically collecting your LFM recommendations from RED. It runs as a Docker container and is driven entirely from your browser. The web UI also supports ad-hoc RED searches and reviewing past run history.

## How does `plastered` work?

Plastered works as follows when it is run:

1. Automatically collects your LFM recommendations from your LFM page, filtering out the collected recommendations based on your configuration settings (e.g. by default, recommendations you have already snatched from — or are currently seeding on — RED are skipped).
2. Resolves any intermediate information necessary to search for the recommendations on RED. This is dependent on the user's configuration, but generally works by querying either the LFM API, or the musicbrainz API for any necessary extra details about each recommendation.
    * For album recommendations, `plastered` will only try to get extra information which the user enables as additional RED search attributes (`red.search`): release type and release year (both on by default) narrow the candidate releases, while record label and catalog number (both off by default) are used to prefer the best candidate. When LFM does not provide a MusicBrainz release ID for a recommendation (which is common), `plastered` falls back to musicbrainz's own release search — which tolerates minor naming differences — to resolve one.
    * For song recommendations, `plastered` must figure out which release(s) the song originated from. It gathers every candidate it can — the release the LFM API associates with the song, plus every release musicbrainz lists for the recording (looked up by the recording's MusicBrainz ID when LFM provides one, and found via musicbrainz's recording search when there is no ID, or when the lookup is capped or lists only releases a song cannot originate from, such as compilations and live albums — keeping only recordings credited to the artist and titled like the song, and retrying with the song title stripped of trailing decorations such as "(feat. X)" or "- Remastered" when the full title matches nothing, in which case a stripped "feat." artist must appear in the recording's artist credit) — drops the compilations, live albums and the like among them (those carry another version of the song at best, never its origin) and ranks the rest: official *albums* first, then EPs, then singles, then soundtracks, then candidates of unknown type, earliest release first. The candidates are then tried in that order against the artist's album, EP, single and soundtrack RED release groups (never any other type) until one matches. If no candidate origin release can be found at all, `plastered` will exclude the song from its RED searches. The resolved origin release (and which source it came from) is recorded per search, so the resolution accuracy can be inspected in the database.
3. After resolving any additional data about the recommendations, `plastered` looks the recommendation's artist up on RED, pulls the artist's full release listing, and matches the wanted release against it (see the next question for how matching works). If a match meeting your configured criteria (format preferences, size limits, etc.) is found, then `plastered` can optionally grab the match.
    * The artist listing is fetched at most once per artist per run: it is cached in memory for the duration of the run (never on disk), so several recommendations by the same artist share a single RED request.
    * A run's total download size can optionally be capped via the `red.snatches.min_allowed_ratio` setting: matches are grabbed largest-first and any that would drop your RED ratio below that floor are skipped. The cap is disabled by default.

## How does `plastered` match releases on RED?

RED's search does not offer fuzzy matching, so `plastered` does the matching itself instead of relying on RED's exact search fields:

* **Title matching**: a release title matches a RED release group when the names are the same after normalization (case, punctuation, curly quotes, accents, and `&`-vs-`and` differences are ignored), or when every word of the wanted title appears in the group's name (so *"OK Computer"* still matches the group *"OK Computer OKNOTOK 1997 2017"*).
* **Opt-in fuzzy matching** (`red.search.fuzzy_search_enabled`, off by default): additionally accepts highly similar titles — e.g. edition-suffix differences like *"Album (Deluxe Edition)"* vs *"Album"*, small spelling variations, and reordered words. This improves the hit rate at some risk of false-positive matches, so exact and word-level matches always rank above fuzzy ones.
* **Release type and year** (`use_release_type` / `use_first_release_year`): when enabled, candidate groups of a different release type or year are dropped. The release type is RED's own: a MusicBrainz release group tagged as a compilation, live album, soundtrack, remix, DJ-mix, mixtape, demo or interview is matched under that RED type, not under its album / EP / single primary type. The year is forgiving: if it would eliminate *every* candidate (e.g. a reissue-only group), it is skipped for that item rather than killing the match.
* **Record label and catalog number** (`use_record_label` / `use_catalog_number`): when enabled, these are *preferences*, not filters — among equally-titled candidates, groups whose label/catalog number match the musicbrainz-resolved values are preferred, but a mismatch never rules a group out.
* The best-matching group's torrents are then ranked against your `red.format_preferences` list, and the highest-priority format with a torrent within your size limit wins.

The same matching applies to ad-hoc searches, where any refinement fields you provide (release type, year, label, catalog number) behave the same way. An ad-hoc *track* search only ever matches album, EP, single and soundtrack release groups, so any release type you give it must be one of those. An ad-hoc search's result traces each of these stages, so when nothing matches you can see whether the artist is missing on RED, no group's title matched, the type / year filters dropped every match, or no torrent met your format preferences and size limit — and, for a track, which origin releases were tried.

## Can `plastered` scrape my recommendations automatically?

Yes. The LFM scraper page has a **Scheduled scrapes** section where you can set the scraper to run daily, every other
day, weekly, every other week, or monthly at a chosen time of day (in the server's local time zone). No scheduled
scrape runs unless you set one up, and a saved schedule is kept across restarts. See the
[User Guide](./user_guide.md#scheduled-scrapes) for the details.

## How do I get started with using `plastered`?

See the [User Guide](./user_guide.md)!

## How do I configure `plastered` to do X thing?

See the [Configuration Reference](./config_reference.md)

## Why does `plastered` run as a Docker container?

This is to ensure broader compatibility, and tool isolation from the host machine. Since `plastered` is written in Python, it _may_ be possible to run the python tooling directly, but that is not the recommended way and users who wish to run outside of a Docker container will have to figure out the slight differences in running the tool that way.
