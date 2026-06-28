# ReleaseSearcher Search Process Overview

This document visualizes the control flow of the `ReleaseSearcher`'s search process as a
directed acyclic graph (DAG).

- **Nodes** are `ReleaseSearcher` method calls (blue), `Snatcher` method calls (cyan), and the
  individual `SearchItemModifier` (green) / `SearchItemFilter` (orange) processors applied to each
  `SearchItem`.
- **Edges** point FROM a node TO the node that runs next.

Each search invocation first builds fresh per-run state via
`ReleaseSearcher._new_search_state_and_snatcher()` (a new `SearchState` plus the `Snatcher` that
owns it), gathering RED user details if they have not been fetched yet. Keeping this state out of
`__init__` lets a single `ReleaseSearcher` be reused across calls (the FastAPI app builds it once
at startup) without one run's matches leaking into the next.

Each `SearchItem` is then processed by an ordered sequence of modifiers and filters that branches by
`EntityType` (album vs. track) and re-converges on the processors the two share. Every
`SearchItemFilter` may short-circuit processing: if its rules reject the item, the item is
dropped (recorded with a `SkipReason`). Modifiers enrich the item in place and always pass it
along. Items that survive become snatch candidates handed off to the `Snatcher`. (See the
[Chain ordering reference](#chain-ordering-reference) for the exact per-entity ordering.)

```mermaid
flowchart TD
    %% ── ReleaseSearcher entrypoints & orchestration ──
    SFR["ReleaseSearcher.search_for_recs()"]
    MS["ReleaseSearcher.adhoc_search()"]
    NEW_STATE["ReleaseSearcher._new_search_state_and_snatcher()"]
    GRUD["ReleaseSearcher._gather_red_user_details()"]
    APPLY["ReleaseSearcher._apply_si_processor_chain()"]
    SNATCHES["Snatcher.snatch_matches()"]
    SNATCH["Snatcher._snatch_match()"]
    DROP(["SearchItem dropped (returns None)"])

    %% ── Processors ──
    RESOLVE_TRACK["ResolveTrackInfoModifier"]
    POST_TRACK["PostResolveOriginTrackFilter"]
    ATTACH["AttachSearchIdModifier"]
    PREMBID["PreMBIDResolutionFilter"]
    RESOLVE_ALBUM["ResolveAlbumInfoModifier"]
    ATTEMPT_MB["AttemptResolveMBReleaseModifier"]
    POSTMBID["PostMBIDResolutionFilter"]
    SEARCH_RED["SearchRedReleaseByPrefsModifier"]
    POST_RED["PostRedSearchFilter"]

    SFR --> NEW_STATE
    MS --> NEW_STATE
    NEW_STATE -->|"if RED user details not initialized"| GRUD
    NEW_STATE -.->|"already initialized"| APPLY
    GRUD --> APPLY

    APPLY -->|"EntityType.ALBUM"| ATTACH
    APPLY -->|"EntityType.TRACK"| RESOLVE_TRACK

    RESOLVE_TRACK --> POST_TRACK
    POST_TRACK -->|pass| ATTACH
    POST_TRACK -->|reject| DROP

    ATTACH --> PREMBID
    PREMBID -->|"pass (album)"| RESOLVE_ALBUM
    PREMBID -->|"pass (track)"| ATTEMPT_MB
    PREMBID -->|reject| DROP
    RESOLVE_ALBUM --> ATTEMPT_MB

    ATTEMPT_MB --> POSTMBID
    POSTMBID -->|pass| SEARCH_RED
    POSTMBID -->|reject| DROP

    SEARCH_RED --> POST_RED
    POST_RED -->|pass| SNATCHES
    POST_RED -->|reject| DROP

    SNATCHES -->|"per matched SearchItem"| SNATCH

    %% ── Styling ──
    classDef rsMethod fill:#cfe2ff,stroke:#0d6efd,color:#000;
    classDef snatcher fill:#cff4fc,stroke:#0dcaf0,color:#000;
    classDef modifier fill:#d1e7dd,stroke:#198754,color:#000;
    classDef filter fill:#ffe5d0,stroke:#fd7e14,color:#000;
    classDef terminal fill:#f8d7da,stroke:#dc3545,color:#000;

    class SFR,MS,NEW_STATE,GRUD,APPLY rsMethod;
    class SNATCHES,SNATCH snatcher;
    class RESOLVE_TRACK,ATTACH,RESOLVE_ALBUM,ATTEMPT_MB,SEARCH_RED modifier;
    class POST_TRACK,PREMBID,POSTMBID,POST_RED filter;
    class DROP terminal;
```

## Detailed view: filter → `SearchState` delegation

The diagram below expands every `SearchItemFilter` into the individual `SearchState` rule
methods it delegates to (purple). Each filter runs its rules in order; the first rule that
returns a `SkipReason` drops the item, otherwise the item advances. The final
`PostRedSearchFilter` rule, `add_search_item_to_snatch()`, always returns `None` (it registers
the match rather than rejecting it), so it passes the surviving item on to snatching.

> Note: `PostResolveOriginTrackFilter` does **not** delegate to a `SearchState` method — it
> applies an inline rule on the `SearchItem` itself (orange) and is shown here for completeness.

```mermaid
flowchart TD
    %% ── ReleaseSearcher orchestration ──
    SFR["ReleaseSearcher.search_for_recs()"]
    MS["ReleaseSearcher.adhoc_search()"]
    NEW_STATE["ReleaseSearcher._new_search_state_and_snatcher()"]
    GRUD["ReleaseSearcher._gather_red_user_details()"]
    APPLY["ReleaseSearcher._apply_si_processor_chain()"]
    SNATCHES["Snatcher.snatch_matches()"]
    SNATCH["Snatcher._snatch_match()"]
    DROP(["SearchItem dropped (returns None)"])

    %% ── Modifiers ──
    RESOLVE_TRACK["ResolveTrackInfoModifier"]
    ATTACH["AttachSearchIdModifier"]
    RESOLVE_ALBUM["ResolveAlbumInfoModifier"]
    ATTEMPT_MB["AttemptResolveMBReleaseModifier"]
    SEARCH_RED["SearchRedReleaseByPrefsModifier"]

    SFR --> NEW_STATE
    MS --> NEW_STATE
    NEW_STATE -->|"if RED user details not initialized"| GRUD
    NEW_STATE -.->|"already initialized"| APPLY
    GRUD --> APPLY

    APPLY -->|"EntityType.ALBUM"| ATTACH
    APPLY -->|"EntityType.TRACK"| RESOLVE_TRACK

    %% ── PostResolveOriginTrackFilter (track only, inline rule) ──
    subgraph TF0["PostResolveOriginTrackFilter"]
        direction TB
        TS_in["inline: si._lfm_track_info present?"]
    end
    RESOLVE_TRACK --> TS_in
    TS_in -->|present| ATTACH
    TS_in -->|NO_SOURCE_RELEASE_FOUND| DROP

    %% ── PreMBIDResolutionFilter ──
    subgraph PF["PreMBIDResolutionFilter"]
        direction TB
        S_snatched["state._pre_mbid_reso_rule_not_previously_snatched()"]
        S_context["state._pre_mbid_reso_rule_allowed_rec_context()"]
        S_snatched -->|None| S_context
    end
    ATTACH --> S_snatched
    S_context -->|"None (album)"| RESOLVE_ALBUM
    S_context -->|"None (track)"| ATTEMPT_MB
    RESOLVE_ALBUM --> ATTEMPT_MB

    %% ── PostMBIDResolutionFilter ──
    subgraph PMF["PostMBIDResolutionFilter"]
        direction TB
        S_required["state.post_mbid_reso_rule_has_required_fields()"]
    end
    ATTEMPT_MB --> S_required
    S_required -->|None| SEARCH_RED

    %% ── PostRedSearchFilter ──
    subgraph PRF["PostRedSearchFilter"]
        direction TB
        S_match["state.post_red_search_rule_found_match_with_allowed_size()"]
        S_dupe["state._post_red_search_rule_not_dupe_snatch()"]
        S_add["state.add_search_item_to_snatch()"]
        S_match -->|None| S_dupe
        S_dupe -->|None| S_add
    end
    SEARCH_RED --> S_match
    S_add --> SNATCHES

    %% ── Rule rejections drop the item ──
    S_snatched -->|SkipReason| DROP
    S_context -->|SkipReason| DROP
    S_required -->|SkipReason| DROP
    S_match -->|SkipReason| DROP
    S_dupe -->|SkipReason| DROP

    SNATCHES -->|"per matched SearchItem"| SNATCH

    %% ── Styling ──
    classDef rsMethod fill:#cfe2ff,stroke:#0d6efd,color:#000;
    classDef snatcher fill:#cff4fc,stroke:#0dcaf0,color:#000;
    classDef modifier fill:#d1e7dd,stroke:#198754,color:#000;
    classDef searchState fill:#e0cffc,stroke:#6f42c1,color:#000;
    classDef inlineRule fill:#ffe5d0,stroke:#fd7e14,color:#000;
    classDef terminal fill:#f8d7da,stroke:#dc3545,color:#000;

    class SFR,MS,NEW_STATE,GRUD,APPLY rsMethod;
    class SNATCHES,SNATCH snatcher;
    class RESOLVE_TRACK,ATTACH,RESOLVE_ALBUM,ATTEMPT_MB,SEARCH_RED modifier;
    class S_snatched,S_context,S_required,S_match,S_dupe,S_add searchState;
    class TS_in inlineRule;
    class DROP terminal;
```

## Chain ordering reference

The chains are defined on `SearchItemProcessorChain` in
[`processors/chains.py`](./processors/chains.py):

| Order | `album_chain` | `track_chain` |
| ----- | ------------- | ------------- |
| 1 | `AttachSearchIdModifier` | `ResolveTrackInfoModifier` |
| 2 | `PreMBIDResolutionFilter` | `PostResolveOriginTrackFilter` |
| 3 | `ResolveAlbumInfoModifier` | `AttachSearchIdModifier` |
| 4 | `AttemptResolveMBReleaseModifier` | `PreMBIDResolutionFilter` |
| 5 | `PostMBIDResolutionFilter` | `AttemptResolveMBReleaseModifier` |
| 6 | `SearchRedReleaseByPrefsModifier` | `PostMBIDResolutionFilter` |
| 7 | `PostRedSearchFilter` | `SearchRedReleaseByPrefsModifier` |
| 8 | — | `PostRedSearchFilter` |
