# Frequently Asked Questions

## What is `plastered`?

`plastered` is a tool for automatically collecting your LFM recommendations from RED.

## How does `plastered` work?

Plastered works as follows when it is run:

1. Automatically collects your LFM recommendations from your LFM page, optionally filtering out the recommendations it collects based on your configuration settings (e.g. it can filter out recommendations which are already in your library).
2. Resolves any intermediate information necessary to search for the recommendations on RED. This is dependent on the user's configuration, but generally works by querying either the LFM API, or the musicbrainz API for any necessary extra details about each recommendation.
    * For album recommendations, `plastered` will only try to get extra information which the user specifies as additional RED search fields, such as catalog number, record label, etc. By default, the only extra information `plastered` will look for on any album recommendation is the release year.
    * For song recommendations, `plastered` must figure out the release the song originated from. This is done by first querying the LFM API for any associated origin release, and if that fails then querying the musicbrainz API for an origin release. If no origin release can be found, `plastered` will exclude the song from its RED searches.
3. After resolving any additional data about the recommendations, `plastered` will use the RED search API to find a valid entry on RED which meets the user-configured search criteria, and which matches the recommendation's data. If a match is found, then `plastered` can optionally grab the match.

## How do I get started with using `plastered`?

See the [User Guide](./user_guide.md)!

## How do I configure `plastered` to do X thing?

See the [Configuration Reference](./configuration_reference.md)

## Why does `plastered` run as a Docker container?

This is to ensure broader compatibility, and tool isolation from the host machine. Since `plastered` is written in Python, it _may_ be possible to run the python tooling directly, but that is not the recommended way and users who wish to run outside of a Docker container will have to figure out the slight differences in running the tool that way.
