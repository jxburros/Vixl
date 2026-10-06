# Contributing

Use the canonical operation schema for CLI, Python, REST and MCP changes. Keep historical spellings in `normalize.py`; aliases must validate and execute through the same implementation as their canonical operation. New operations need a short description, typed and described fields, and regression coverage of their public behavior.

Run `pytest -q` and build the distributions before submitting a release change. Keep the package, plugin manifests and versioned installation URLs synchronized; document user-visible changes in `CHANGELOG.md`. Release automation publishes only after Linux and Windows verification and installer checks succeed. See [the release process](docs/releases.md).

Commit messages, generated pull requests, issue text and generated artwork should describe the work without model signatures or authorship trailers. Keep comments that explain constraints, tradeoffs or non-obvious behavior; remove comments that only repeat the next statement. Provider configuration identifiers are functional data and should remain intact.
