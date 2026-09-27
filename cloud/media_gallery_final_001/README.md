# Final media gallery layout and existing saved URLs

The canonical gallery install 36356222769 finished successfully and passed all 24 exact public checks. Live Chromium acceptance confirmed thumbnail clicks, keyboard navigation, enlarged selection, Escape/focus restoration and mouse dragging. It also found two actual CSS sizing defects: a 1348 px main gallery had a 873.6 px stage, and a portrait video grew to 2199 px inside a 737.8 px modal panel, putting native controls outside the visible frame.

This correction changes only the existing `ua_media_styles.py` runtime module. The stage gets an explicit 100% width. The native video fills its positioned panel, with its own zero margin and minimum sizes, so intrinsic poster dimensions and the old page-wide video margins cannot expand the player. The photo/video renderer and JavaScript remain byte-identical to the installed release. No dependencies or services are added.

Existing canonical gallery pages receive an exact style-block replacement. Saved public `UA-NNNN-xxxxxxxx.html` pages receive the same gallery through the previously reviewed media-only migration. Other page bytes, vehicle data and ordered media URLs remain unchanged. This release covers the still-inert `media_gallery_aliases_001` companion as well; do not launch that obsolete asset-bound candidate after this correction.

Use a fresh exact server plan after other active card publications. Preserve all original requests and receipts. Existing backup, rollback, drift, writer and database protections remain in force. The corrected source and actual published dimensions/native playback must be checked before full UI acceptance is recorded. Fullscreen fallback works in the current browser; native fullscreen and real iPhone/TikTok acceptance are not yet confirmed.

Official layout references: https://www.w3.org/TR/css-grid/#min-size-auto and https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/aspect-ratio .
