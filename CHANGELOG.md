# Changelog

All notable changes to OpenHarness should be recorded in this file.

The format is based on Keep a Changelog, and this project currently tracks changes in a lightweight, repository-oriented way.

## [Unreleased]

### Added

- `diagnose` skill: trace agent run failures and regressions using structured evidence from run artifacts.
- `hotel_biztravel` shared decision core: domain_rank / bundle_rank, candidate briefs, inferred user needs, and confirmation-time preference writeback into `DecisionMemory`.
- GitHub Actions CI workflow for Python linting, tests, and frontend TypeScript checks.
- `CONTRIBUTING.md` with local setup, validation commands, and PR expectations.
- `docs/SHOWCASE.md` with concrete OpenHarness usage patterns and demo commands.
- GitHub issue templates and a pull request template.
- MCP runtime upgrades: WebSocket transport support, active-session `/mcp auth` hot refresh, server auto-reconnect, and explicit notice severity in UI/backend snapshots.

### Fixed

- Memory scanner now parses YAML frontmatter (`name`, `description`, `type`) instead of returning raw `---` as description.
- Memory search matches against body content in addition to metadata, with metadata weighted higher for relevance.
- Memory search tokenizer handles Han characters for multilingual queries.
- MCP text summaries and terminal surfaces now use consistent recovered/error labels for reconnect outcomes and per-server details.

### Changed

- README now links to contribution docs, changelog, showcase material, and provider compatibility guidance.
- README quick start now includes a one-command demo and clearer provider compatibility notes.
- README, `CONTRIBUTING.md`, and `docs/MIGRATION.md` now document the current Velaris MCP workflow, auth refresh commands, and compact `/mcp` summary format.

## [0.1.0] - 2026-04-01

### Added

- Initial public release of OpenHarness.
- Core agent loop, tool registry, permission system, hooks, skills, plugins, MCP support, and terminal UI.
