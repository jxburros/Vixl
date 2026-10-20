# Security policy

## Supported versions

Only the latest minor release receives security fixes (see [CHANGELOG.md](CHANGELOG.md) for the current one).
Vixl is pre-release: upgrade to the newest version before reporting.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose **Report a
vulnerability** (<https://github.com/jxburros/Vixl/security/advisories/new>). Do not open a public issue or pull
request for a vulnerability.

Include the version (`vixl --version`), the interface (CLI, MCP, REST or Python), a minimal document or command that
reproduces the problem and the impact you expect.

Response targets, from a single maintainer: an acknowledgement within 7 days, and a fix or a mitigation plan within
90 days. Reporters are credited in the advisory unless they ask not to be.

## Scope

In scope: path handling and workspace boundaries, network fetches (fonts, images, content packs, updates), the
updater and release artefacts, the MCP and REST interfaces, parsing of untrusted documents, SVG, PDF and font input,
and anything that executes code or reads files the caller did not name.

The threat model and the controls that exist are described under "Trust and security" in
[the architecture reference](docs/reference/architecture.md#trust-and-security). Behaviour that page documents as the
caller's responsibility can still be raised as a hardening suggestion in a normal issue.
