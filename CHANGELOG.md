# Changelog

All notable changes to prompt-vcs are documented in this file.

## [0.6.0] - 2026-07-23

### Added

- `pvcs list`, `add`, `delete`, `unlock`, and `export` commands.
- JSON, OpenAI messages, and LangChain prompt export formats.
- Async `@prompt` decorator support.
- VS Code extension unit tests and multi-root workspace resolution.
- PEP 561 `py.typed` marker.

### Changed

- A/B selection is thread-safe and validates identifiers, weights, scores, and
  duplicate versions.
- A/B winner detection now requires 95% confidence and uses Welch's t-test
  when the optional `analysis` dependency is installed.
- Prompt and lockfile caches reload automatically after file changes.
- Lockfiles and experiment configuration files are written atomically.
- Locked versions fail closed when the referenced template is missing.
- CI now covers Windows, the VS Code extension, distributions, and wheel CLI
  smoke tests.

### Fixed

- The first A/B request can no longer select one variant while rendering
  another.
- Zero-weight variants are never selected.
- A/B prompt results are real strings and cannot be recorded twice.
- `@prompt(default_version=...)` now selects the requested default YAML version.
