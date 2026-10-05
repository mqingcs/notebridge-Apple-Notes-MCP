# Contributing

Keep the default read-only behavior and exact-folder scope. Do not add deletion,
unlocking, implicit cloud uploads or silent permission changes. Native functionality
must be supported by the public interface; document real validation separately from
synthetic tests. Experimental features must not appear as validated capabilities.

Run the unittest suite and synthetic smoke test before submitting changes. Tests
must not touch real Notes, prompt for macOS permissions, or depend on your account.
Use synthetic note IDs/content and repository-relative fixture paths. Add focused
regression tests for changes to scope, versioning, backup or transport behavior.

Before committing, run `python3 scripts/scan_publication.py` and review `git diff`.
Do not commit `.env`, runtime profiles, credentials, note bodies, personal backups,
recorded UI sessions, machine paths or private logs. A passing scanner does not
replace manual review. New dependencies need a license/provenance review and a
clear reason; the server currently has no third-party runtime dependencies.

CI installs a built wheel and runs only synthetic data. Please describe what was
changed, why, what was tested, and any unverified native behavior in your PR.
