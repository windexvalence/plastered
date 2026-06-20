from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plastered.models import SearchItem
    from plastered.release_search.search_helpers import SearchState
    from plastered.utils.httpx_utils import RedSnatchAPIClient

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snatcher:
    """
    Wrapper responsible for all RED snatching request and response handling along with any state information updates
    pertaining to snatch operations.
    """

    red_snatch_client: RedSnatchAPIClient
    search_state: SearchState
    snatch_directory: Path
    enable_snatches: bool

    def snatch_matches(self, manual_run: bool = False) -> None:
        """Snatch every matched SearchItem the search state has flagged, provided snatching is enabled."""
        if not self.enable_snatches:
            _LOGGER.warning("Not configured to snatch. Please update your config to enable.")
            return
        if search_items_to_snatch := self.search_state.get_search_items_to_snatch(manual_run=manual_run):
            _LOGGER.debug(f"Beginning to snatch matched torrents to download directory '{self.snatch_directory}' ...")
            for si_to_snatch in search_items_to_snatch:
                self._snatch_match(si_to_snatch=si_to_snatch)
        else:  # pragma: no cover
            _LOGGER.warning("No torrents matched to your LFM recs. Consider adjusting the search config preferences.")

    def _snatch_match(self, si_to_snatch: SearchItem) -> None:
        te_to_snatch = si_to_snatch.torrent_entry
        if not te_to_snatch:  # pragma: no cover
            _LOGGER.error("SearchItem marked for snatching unexpected missing torrent entry: ")
            return
        tid = te_to_snatch.torrent_id
        permalink = te_to_snatch.get_permalink_url()
        out_filepath = Path(os.path.join(self.snatch_directory, f"{tid}.torrent"))
        exc_name: str | None = None
        _LOGGER.debug(f"Snatching {permalink} and saving to {out_filepath} ...")
        try:
            binary_contents = self.red_snatch_client.snatch(tid=str(tid), can_use_token=te_to_snatch.can_use_token)
            out_filepath.write_bytes(binary_contents)
        except Exception as ex:  # pragma: no cover
            # Delete any potential file artifacts in case the failure took place in the middle of the .torrent file writing.
            if os.path.exists(out_filepath):
                os.remove(out_filepath)
            _LOGGER.error(f"Failed to snatch due to uncaught error for: {permalink}: ", exc_info=True)
            exc_name = ex.__class__.__name__
        finally:
            fl_token_used = self.red_snatch_client.tid_snatched_with_fl_token(tid=tid)
            self.search_state.add_snatch_final_status_row(
                si=si_to_snatch, snatched_with_fl=fl_token_used, snatch_path=str(out_filepath), exc_name=exc_name
            )
