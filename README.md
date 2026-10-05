# Scoped Apple Notes MCP

A local MCP server for Apple Notes on macOS. It reads only explicitly selected
folders and can optionally create and edit notes **without exposing deletion**.
It uses the Notes scripting interface through a fixed JavaScript for Automation
(JXA) adapter. No Notes database access, browser automation, or third-party Python
runtime dependencies are required.

[中文说明](docs/README.zh-CN.md) · [Architecture](docs/architecture.md) ·
[Security and privacy](SECURITY.md) · [Validation](docs/validation.md)

**Status: early release.** Reading and core non-deleting edits have been exercised
through a real ChatGPT/private-tunnel client in the originating deployment.
Attachment tools have synthetic coverage only and require an additional
experimental flag. This repository does not claim support for every Notes feature.

## Requirements

- Python **3.9 or newer**. The synthetic test suite can run on macOS and Linux.
- For real notes: macOS, the built-in Notes app, `/usr/bin/osascript`, and the
  Foundation/CoreServices frameworks. The originating deployment used Apple
  silicon and macOS 27; other macOS versions have not been acceptance-tested.
- A logged-in desktop session with the relevant Notes account available locally.
  Unlock/synchronize the account yourself; this server cannot unlock notes.
- macOS **Automation** permission for the application launching the server to
  control Notes. It does not request Full Disk Access or Accessibility permission.
- An MCP client that supports stdio, or a separately configured private transport.

There is no direct iCloud web API here. The Mac must remain awake, logged in and
online for remote clients. Apple sync and account availability remain prerequisites.

## Install from this repository

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
apple-notes-mcp --help
```

Or run without installing:

```sh
python3 -m apple_notes_mcp --help
```

Installation does **not** grant permissions, start a background service, install a
tunnel client, or connect to Notes. No API key is needed for local stdio use.
A wheel includes the JXA adapter; it does not depend on a checkout at runtime.

## Try synthetic notes first

From the repository root:

```sh
python3 scripts/smoke_test.py
python3 -m unittest discover -s tests -v
```

The smoke test performs a real stdio handshake, discovers tools, and calls
list/search/get on the included synthetic fixture. It prints only a short status
summary, then closes the process. It never contacts Notes.

To leave the synthetic server waiting for an MCP client:

```sh
python3 -m apple_notes_mcp \
  --fixture fixtures/synthetic.json --allowed-folder folder-demo
```

A quiet terminal is normal: stdout is reserved for newline-delimited MCP JSON-RPC.
Use `--enable-writes --backup-dir /absolute/private/test-backups` to try mutations
against the in-memory fixture. Fixture changes are not saved to the fixture file.

## Connect real Notes

1. Open Notes normally and let the desired account synchronize.
2. Check permission without prompting or reading notes:

   ```sh
   apple-notes-mcp --preflight
   ```

3. If needed, deliberately request permission from the **same launching context**
   you will use for the server:

   ```sh
   NOTES_ALLOW_REAL=1 apple-notes-mcp --notes --request-automation
   ```

   This is a local setup command: it requests consent once, prints a status and
   exits. Remote tools never request permission or change macOS privacy settings.
   A background launcher may have a different Automation identity from Terminal.

4. Enumerate account/folder names and IDs locally:

   ```sh
   NOTES_ALLOW_REAL=1 apple-notes-mcp --notes --folders
   ```

   This command exposes your folder metadata on your terminal. Select only the
   exact folder IDs you intend to expose; do not commit or share its output.

5. Start a read-only server with the chosen ID:

   ```sh
   NOTES_ALLOW_REAL=1 apple-notes-mcp --notes \
     --allowed-folder 'REPLACE_WITH_YOUR_EXACT_FOLDER_ID'
   ```

Repeat `--allowed-folder` for another explicitly approved folder. Child folders
are **not** included automatically. Missing or moved folders fail closed.
The placeholder above is not a functional Notes ID.

[examples/client.readonly.json](examples/client.readonly.json) is a generic client
configuration. Replace its executable and folder placeholders locally. Client
configuration formats differ; the example is not automatically installed.

## Enable non-deleting edits deliberately

```sh
NOTES_ALLOW_REAL=1 NOTES_ALLOW_WRITE=1 apple-notes-mcp --notes \
  --allowed-folder 'REPLACE_WITH_YOUR_EXACT_FOLDER_ID' --enable-writes
```

Both the CLI flag and environment gate are required for real writes. The folder
allowlist is unchanged. Use `apple_notes_prepare_edit` to obtain a fresh
`expected_version` before each mutation. Each edit checks that version and saves a
private backup before its final JXA recheck. **Notes has no atomic compare-and-swap:**
concurrent manual edits can still race with a write.

Backups default to `~/Library/Application Support/Apple Notes MCP/backups`.
Override with `--backup-dir` or `NOTES_BACKUP_DIR`. Directories must be owner-only
(`0700`), and files are created `0600`. Backups contain private note content; they
are not encrypted by this package and must remain outside the repository. When
the backup budget is exhausted, further edits are refused; backups are not pruned.

If a write times out, its outcome is uncertain. Inspect the target before retrying.
Do not run mutations concurrently on the same note. Keep backups and the Python
code protected from other local users.

## Tools

| Mode | Tools | Behavior |
| --- | --- | --- |
| Default | `apple_notes_list`, `apple_notes_search`, `apple_notes_changes` | Paged metadata; literal, case-insensitive **title** search; timestamp changes without deletions |
| Default | `apple_notes_get`, `search`, `fetch` | Bounded plain text / citation compatibility; locked notes excluded |
| `--enable-writes` | `apple_notes_capabilities`, `apple_notes_prepare_edit` | Capability report and bounded preview/version |
| `--enable-writes` | `apple_notes_create`, `apple_notes_append`, `apple_notes_edit`, `apple_notes_rename` | Nonempty plain text or restricted basic HTML; version checks and backups for edits |
| `--enable-writes` | `apple_notes_move`, `apple_notes_restore` | Move only between allowed folders; restore an existing attachment-free note from its own backup |
| Also `--experimental-attachments` | `apple_notes_list_attachments`, `apple_notes_get_attachment`, `apple_notes_add_attachment` | Experimental native metadata, byte export, and additive attachment creation |

There are 6 tools by default, 14 with edits, and 17 with experimental attachments.
Write tools are annotated as mutations; annotations do not replace server checks or
client approval policies. Shared notes are not editable. Basic reads can include
shared notes within an allowed folder; do not allow such a folder if that is not
what you intend.

### Limits and unsupported operations

- No delete, empty-body clearing, unlock, sharing, account changes or remote scope
  changes. Native checklist toggling, pinning, tags and folder management are not
  implemented; the inspected Notes scripting dictionary exposes no checklist/pin
  command or property.
- Reads scan scoped metadata (at most 2,000 notes) on demand. There is no index or
  background scanner. Lists default to 10 records, maximum 50; get defaults to
  1,000 characters, maximum 8,000. Body text may be read by Notes before truncation;
  the returned bound is not a whole-process memory guarantee.
- Mutation previews are at most 500 characters; incoming text is at most 16,000
  characters, and edit snapshots are capped at 256 KiB. Basic HTML permits lists,
  tables, and formatting, but no attributes, scripts, images or remote resources.
- Any note with attachments is protected from append/body replacement/restore.
  Text/metadata backups are **not** backups of attachment binaries.
- Experimental attachment transfers default to 64 KiB reads and have a 256 KiB
  returned/addition limit. Native export may write the **entire** original into a
  private temporary file before checking size. Some native objects may not export
  as regular files. No PDF extraction, OCR, image interpretation or URL fetching
  is implemented. Added attachments remain; removal is unavailable.
- Metadata pagination is not a database snapshot. Notes can change during reads;
  the changes feed includes boundary duplicates and does not report deletions.

See [validation details](docs/validation.md) for what was and was not tested.

## Remote access and background operation

This server implements stdio only: no HTTP listener, authentication service,
telemetry, or built-in cloud connection. Configure any remote transport separately,
using authenticated private access. Never expose unauthenticated stdio-to-HTTP
bridges on the public internet.

The originating deployment used the official OpenAI tunnel client. It is optional,
separately installed, and not bundled. Organization/workspace IDs, runtime keys,
and installed launchd jobs are intentionally absent from this repository.
[Deployment notes](docs/deployment.md) explain credential boundaries and recovery.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 scripts/smoke_test.py
python3 scripts/scan_publication.py
```

Tests use synthetic data and mocked permissions. No test grants macOS permissions
or requires an Apple account. On macOS you can additionally syntax-check the adapter:

```sh
osacompile -l JavaScript -o /tmp/notes-mcp-adapter.scpt apple_notes_mcp/adapter.js
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). This project is
not affiliated with Apple or OpenAI. MIT licensed; external components retain their
own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
