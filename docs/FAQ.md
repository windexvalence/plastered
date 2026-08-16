# Frequently Asked Questions

## What is `plastered`?

`plastered` is a self-hosted web app for automatically collecting your LFM recommendations from RED. It runs as a Docker container and is driven entirely from your browser. The web UI also supports ad-hoc RED searches and reviewing past run history.

## How does `plastered` work?

Plastered works as follows when it is run:

1. Automatically collects your LFM recommendations from your LFM page, filtering out the collected recommendations based on your configuration settings (e.g. by default, recommendations you have already snatched from — or are currently seeding on — RED are skipped).
2. Resolves any intermediate information necessary to search for the recommendations on RED. This is dependent on the user's configuration, but generally works by querying either the LFM API, or the musicbrainz API for any necessary extra details about each recommendation.
    * For album recommendations, `plastered` will only try to get extra information which the user specifies as additional RED search fields, such as catalog number, record label, etc. By default, the only extra information `plastered` will look for on any album recommendation is the release year.
    * For song recommendations, `plastered` must figure out the release the song originated from. This is done by first querying the LFM API for any associated origin release, and if that fails then querying the musicbrainz API for an origin release. If no origin release can be found, `plastered` will exclude the song from its RED searches.
3. After resolving any additional data about the recommendations, `plastered` will use the RED search API to find a valid entry on RED which meets the user-configured search criteria, and which matches the recommendation's data. If a match is found, then `plastered` can optionally grab the match.
    * A run's total download size can optionally be capped via the `red.snatches.min_allowed_ratio` setting: matches are grabbed largest-first and any that would drop your RED ratio below that floor are skipped. The cap is disabled by default.

## How do I get started with using `plastered`?

See the [User Guide](./user_guide.md)!

## How do I configure `plastered` to do X thing?

See the [Configuration Reference](./config_reference.md)

## Why does `plastered` run as a Docker container?

This is to ensure broader compatibility, and tool isolation from the host machine. Since `plastered` is written in Python, it _may_ be possible to run the python tooling directly, but that is not the recommended way and users who wish to run outside of a Docker container will have to figure out the slight differences in running the tool that way.
