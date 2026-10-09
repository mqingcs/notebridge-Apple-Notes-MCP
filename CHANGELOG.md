# Changelog

## 0.1.0 — 2026-10-09

First public release of **NoteBridge**.

- Folder-scoped Apple Notes access through MCP stdio.
- Title search, paginated metadata, bounded text, and exported HTML structure.
- Opt-in non-deleting edits with version checks and private local backups.
- Original attachment bytes with MIME metadata, full SHA-256 and chunked transfer.
- Whole-file MCP resources and separate image previews, including HEIC.
- SHA-256 references for inline images in exported HTML.
- Dependency-free Python runtime, synthetic fixtures, client configuration examples,
  English/Chinese documentation and a cross-platform CI workflow.

Core reads/edits have originating real-client evidence. PNG and HEIC originals and
previews have real local MCP evidence. Attachment addition, other file formats and
cross-folder moves retain their documented validation limits.
