# Third-party notices and provenance

The Python/JXA implementation and synthetic fixtures are maintained as this
project's source, licensed under the repository MIT license. The source was
extracted from its originating local project; no vendor code, personal deployment
files, credentials, note exports, or runtime binaries were imported.

| Component | Relationship | License / ownership |
| --- | --- | --- |
| Python standard library | Runtime prerequisite; not vendored | [Python Software Foundation license](https://docs.python.org/3/license.html) |
| Apple Notes, Foundation, CoreServices, JXA/osascript | macOS-provided services and tools; not redistributed | Apple platform software, governed by Apple's applicable terms |
| Model Context Protocol | Protocol implemented by this source; no MCP SDK bundled | [MIT specification license](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/LICENSE) |
| setuptools | Build backend only; not a runtime dependency | [MIT](https://github.com/pypa/setuptools/blob/main/LICENSE) |
| actions/checkout | CI action, pinned to a reviewed commit | [MIT](https://github.com/actions/checkout/blob/main/LICENSE) |
| actions/setup-python | CI action, pinned to a reviewed commit | [MIT](https://github.com/actions/setup-python/blob/main/LICENSE) |
| OpenAI tunnel-client | Optional, separately installed deployment transport; not bundled or required | [Apache-2.0](https://github.com/openai/tunnel-client/blob/main/LICENSE); verify the version you install |

The release review may use Ruff and Gitleaks locally. These tools and their
binaries are not included in the Python distribution. Their licenses remain with
[Ruff](https://github.com/astral-sh/ruff/blob/main/LICENSE) and
[Gitleaks](https://github.com/gitleaks/gitleaks/blob/master/LICENSE).

No third-party Python packages are imported by the server. The build system and CI
are separate from runtime dependencies. Adding a dependency or copying upstream
source requires a fresh attribution/license review; this notice is not a license
grant for Apple software or optional services. Apple and OpenAI names identify
interoperability only and do not imply endorsement.
