# Release Notes

## v0.1.0 - 2026-06-27

Initial public release candidate for `zero-zero-three-hermes-language-management`.

### Added

- Deterministic shortcut parsing for `/zero-zero-three-hermes-language-management`, `/语言`, `/lang`, `/技能语言`, and `/skill-lang`.
- Default target-language guard: bare shortcut invocations resolve to Simplified Chinese (`zh-CN`).
- Hermes user-facing text scanner and adaptive update reports.
- Translation request export, batch splitting, batch queue status, and failed/truncated batch retry generation.
- Translation response validation for JSON shape, IDs, placeholders, and preserve tokens.
- Safe translation application with report and rollback patch generation.
- Local skill output localization scan and pipeline.
- i18n key migration plan generation and safe migration application for existing i18n helper patterns.
- Multilingual locale consistency checks and deterministic missing-key fix planning.
- Smoke tests covering shortcut parsing, translation batches, retry creation, direct apply, local skill output mode, i18n consistency, and i18n migration application.

### Notes

- This release is intended for Hermes / Hermes-derived projects and local skill output localization.
- The skill does not create a new i18n runtime by itself; it works with existing project helpers and locale files.
- High-risk strings, model-facing prompts, command syntax, paths, provider IDs, model IDs, URLs, and unsafe replacements are skipped or reported for review.
