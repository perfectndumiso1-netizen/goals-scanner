# Offline club crest registry

Owner-approved club identity artwork for the football comparison cards and video covers.

- `manifest.json` pins country, club name, explicit aliases, source blob URL and SHA-256 for every local PNG.
- 129 clubs across England, Spain, Germany, Italy, France and South Africa; this is a bounded registry, not a claim to include every club in those countries or the world.
- European PNG originals: `luukhopman/football-logos` current and 2025–26 directories, selected only for the five approved European leagues. South African club originals: `JoseArroyave/football-logos`, South Africa club SVGs, rasterised once to local PNGs. Source blob hashes are recorded per file.
- PNGs are transparent, aspect-preserving and at most 256×256; they are read offline, validated and hash-checked by `club_crests.py`. No SVG renderer or network dependency is used in production.
- Country plus exact normalised aliases are required. No fuzzy matching, cross-provider numeric ID conversion, arbitrary URL loading or app-logo substitution. Unknown, corrupt or ambiguous entries omit the crest while preserving the real team name.
- Source mirrors are not independent proof of a club's permission or a blanket commercial licence. Logos/trademarks remain with their owners. Use is for factual club identification, not affiliation or endorsement; the project owner remains responsible for permitted visual use. Provenance is internal, not a source/assessment footer on the public artwork.

New clubs and identity/rebrand changes require reviewed source artwork and an updated manifest; never substitute the crest of a similarly named club.
