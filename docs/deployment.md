# Deployment notes

## Local clients

Use the executable inside your virtual environment. GUI apps often have a different
PATH, so prefer its absolute path in the client configuration. Arguments should
remain an array, and folder IDs should remain single arguments. Copy an example
into your client's own private configuration and replace every placeholder.

The CLI does not load `.env` automatically. `.env.example` documents environment
names, not credentials. Use your launcher/client to set only the gates you intend.
A read-only setup should omit `NOTES_ALLOW_WRITE` and `--enable-writes` entirely.

## Automation identity

Run `--preflight` in the intended launching context. Status `0` means allowed;
`-1744` means consent is needed; `-1743` means not permitted; `-600` means Notes is
not running. Open Notes normally and use the explicit local setup command when
appropriate. Do not programmatically modify TCC databases or privacy settings.
A Terminal grant does not prove a launchd-launched process has permission.

## Optional private transport

An external transport can launch `apple-notes-mcp --notes ...` over stdio. Review
its vendor documentation and ensure access is private and authenticated. This
repository neither provisions organizations/workspaces nor installs credentials.
Consult the [official OpenAI secure MCP tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
if choosing that transport; CLI details and availability may change.

Keep runtime secrets out of this repository, shell arguments, chat messages and
logs. A key required by a transport is not required by the Notes server. Prefer
letting the transport read its own protected credential source and exclude those
credentials from the child process environment.

## Background operation

No launchd job is installed by `pip install`. An administrator may separately
configure a user LaunchAgent with their own virtual-environment executable,
allowlist and explicit environment gates. Start with read-only access, use a
restart throttle to avoid loops, and verify Automation permission in that context.
Do not enable automatic wake-from-sleep or reboot the machine as a test.

Closing a foreground terminal can terminate its child processes. A supervisor can
recover a stopped process, but cannot make an asleep/offline Mac serve requests.
The originating deployment verified recovery after termination; this portable
package makes no verified reboot/login-recovery or zero-energy claim.
