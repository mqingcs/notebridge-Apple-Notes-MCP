# Validation and release scope

The source was extracted from an existing local deployment, not from its private
configuration, logs or note backups. A separate later successful Notes read/write
acceptance was also reported by the maintainer; release claims below are limited
to the code and inspectable evidence available during this preparation.

| Capability | Evidence | Release status |
| --- | --- | --- |
| stdio lifecycle, repeated initialize, framing, tool discovery | Automated synthetic subprocess tests | Supported |
| Exact folder scope, locked-note exclusion, bounded text, title search, changes | Automated synthetic tests; originating real list/search/get acceptance | Supported within documented limits |
| Create, plain edit, append, rename, basic HTML, backup restore | Originating real client acceptance on one explicitly authorized test note, plus synthetic tests | Supported; no concurrent-edit guarantee |
| Cross-folder move | Synthetic tests; no real cross-folder acceptance evidence | Implemented, not real-world validated |
| Attachment metadata/export/addition | Synthetic tests and JXA syntax compilation only | Experimental; extra flag required |
| Native checklist state, pinning, tags, folder management | No implementation; checklist/pin absent from inspected public scripting dictionary | Unsupported |
| macOS Automation | Originating deployment granted permission and completed real client calls | Must be granted/verified per user's launcher |
| Background termination recovery | Originating user LaunchAgent recovered after termination | Deployment-specific; no service installer bundled |
| Reboot/login recovery, long-term power usage | Not exercised for this package | No claim |

No real Notes access, new note creation, or note modification is performed during
open-source packaging or CI. Automated tests run with synthetic fixtures. CI also
builds and installs a wheel, exercises the installed stdio entry point and scans
tracked files/history for accidentally included secrets or personal paths.

Resource figures from a different, private deployment are deliberately not
advertised as package performance guarantees. Query cost depends on Notes/account
state, selected folders, note size and the external transport. Returned text/byte
limits do not cap Notes' own resource usage.

The attachment `get` tool returns base64 bytes and UTF-8 text for selected text
extensions. It does not make binary documents semantically readable to every MCP
client. An accepted `make`/`save` call is not yet evidence of end-to-end transfer
compatibility; native/client acceptance remains outstanding.
