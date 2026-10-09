# Validation scope

| Capability | Existing evidence |
| --- | --- |
| stdio lifecycle, repeated initialize, framing and tool discovery | Synthetic subprocess tests |
| Folder scope, locked-note exclusion, metadata, title search and plain text | Synthetic tests and originating real-client acceptance |
| Create, edit, append, rename, basic HTML and text restore | Synthetic tests and originating real-client acceptance |
| PNG and HEIC original export | Real local MCP reads; exported bytes match the corresponding inline HTML bytes by SHA-256 |
| Image previews | Real local MCP JPEG preview output for PNG and HEIC |
| HTML structure and embedded-image references | Real local extraction plus synthetic reconstruction coverage |
| Chunk reassembly, changed-file detection, resources and duplicate filenames | Synthetic tests |
| JPEG, GPG, PDF-like and unknown-extension bytes | Synthetic byte fixtures, not a format parser or decryption test |
| Attachment addition and cross-folder moves | Synthetic tests; real acceptance not claimed |

The original deployed implementation passed 52 regression tests following the
attachment repair. Earlier portable-package checks covered Python3.9/3.13, wheel
installation and stdio startup. Tests were not rerun for the public release at the
maintainer's request; the repository retains a CI workflow for subsequent changes.

Tests and CI use synthetic fixtures. No private notes, files, runtime credentials,
local identifiers, or deployment receipts are distributed with the source.

Resource use depends on Notes, note size and transport. There is no background
indexer. Returned chunk bounds do not bound the native app's memory or the temporary
full-file export. The Mac must remain available for remote requests.
