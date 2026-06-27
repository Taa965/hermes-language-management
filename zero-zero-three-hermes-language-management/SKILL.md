---
name: zero-zero-three-hermes-language-management
description: Hermes localization workflow for deterministic shortcut parsing, scanning, translating, retrying translation batches, patching, validating, resuming interrupted work, generating rollback patches, showing progress, applying i18n key migrations, installing short aliases, reporting adaptive update deltas, and localizing other local skills' user-visible output text. Use when localizing Hermes or Hermes-derived projects into Chinese, Japanese, Korean, English, or another language; replacing remaining English UI/CLI/TUI/Web strings; localizing local skill output strings; checking i18n consistency; using shortcuts like /zero-zero-three-hermes-language-management, /语言, /lang, /技能语言, or /skill-lang, where bare shortcut invocations default to Simplified Chinese (zh-CN); or maintaining localization maps and i18n key migration plans.
---

# 零点零三Hermes语言管理

## Goal

Localize Hermes user-facing text to the requested language while preserving runtime identifiers and agent instructions. Execute the workflow end to end: scan, classify, export translation work, patch or migrate to i18n keys, validate, report, and maintain a baseline so future Hermes updates are handled incrementally.

## Default Target Guard

Default to `zh-CN` Simplified Chinese for every shortcut invocation unless the current user message contains an explicit target-language alias. This is a hard rule.

Bare invocations with no target, including `/zero-zero-three-hermes-language-management`, `/语言`, `/lang`, `/技能语言`, `/skill-lang`, or the same commands followed only by mode/options such as `skills`, `skill`, `技能`, `本地skill`, `状态`, or `续跑`, must use `zh-CN`.

Do not infer Japanese, Korean, English, or any other language from examples, previous conversation, previous runs, cached state, or skill metadata. Select `ja-JP` only when the current invocation explicitly contains `日文`, `日语`, `日本語`, `ja`, or `ja-JP`; apply the same current-message-only rule to every non-default language. If multiple explicit target aliases appear in the current invocation, use the last one.

## Shortcut Command Protocol

Treat slash/comma prompts as one-click execution requests, not planning or preview requests.

Hermes uses `/` only to trigger the skill slash command. The language selector must be passed as the skill argument, separated from the skill name by whitespace.

Format:

```text
/zero-zero-three-hermes-language-management
/zero-zero-three-hermes-language-management <target> [option...]
/zero-zero-three-hermes-language-management ，<target> [，option...]
/语言 [target] [option...]
/lang [target] [option...]
/技能语言 [target] [option...]
/skill-lang [target] [option...]
```

Inside the skill argument, accept either ASCII comma `,` or Chinese comma `，`, and trim spaces around each segment. Also trim trailing punctuation such as `;`, `；`, `.`, `。`, `:`, and `：`.

Do not require a comma. A bare target like `中文` is valid. `中文` always means Simplified Chinese (`zh-CN`) unless the user explicitly says Traditional Chinese.

If the skill is invoked with no target argument, follow Default Target Guard: use `zh-CN`, Simplified Chinese, and run the direct apply workflow. Do not ask the user for a language in the bare slash-command case.

Avoid documenting `/zero-zero-three-hermes-language-management,中文` as the primary form because Hermes may parse the comma as part of the slash command name before the skill is loaded.

Always resolve shortcut arguments with the deterministic parser before choosing locale, mode, or options:

```bash
python scripts/resolve_shortcut_command.py --command "/zero-zero-three-hermes-language-management" --json
python scripts/resolve_shortcut_command.py --command "/语言 日文 续跑" --json
python scripts/resolve_shortcut_command.py --command "/技能语言" --json
```

Use the parser output, not examples or prior context, as the source of truth for `target_locale`, `target_language`, `mode`, and shortcut options.

Target aliases:

- `汉化`, `中文`, `简体中文`, `zh`, `zh-CN`: `zh-CN`, Simplified Chinese.
- `繁中`, `繁体中文`, `zh-Hant`: `zh-Hant`, Traditional Chinese.
- `日文`, `日语`, `日本語`, `ja`, `ja-JP`: `ja-JP`, Japanese.
- `韩文`, `韩语`, `한국어`, `ko`, `ko-KR`: `ko-KR`, Korean.
- `英文`, `英语`, `English`, `en`, `en-US`: `en`, English.
- For other language names, infer the closest locale and target-language name from the user text.

Examples:

```text
/zero-zero-three-hermes-language-management
/zero-zero-three-hermes-language-management 中文
/zero-zero-three-hermes-language-management ，中文
/语言
/技能语言
/zero-zero-three-hermes-language-management 日文
/zero-zero-three-hermes-language-management ，繁体中文
/语言 日文
/lang ko
/技能语言 日文
/skill-lang ko
```

In these examples, bare commands select `zh-CN`; Japanese, Korean, Traditional Chinese, or English are selected only by explicit target aliases in that same command.

Default behavior for a shortcut with only a target language: scan the current Hermes project, translate user-visible strings, validate translation batches, directly apply safe source-code changes, run validation, update the baseline, and report final results. Do not ask the user to approve a preview first.

Shortcut options:

- `只扫描`, `scan`, `dry-run`: generate artifacts only; do not write source files.
- `续跑`, `resume`, `--resume`: continue from existing `localization-work` without overwriting completed translation batches.
- `状态`, `status`: show the progress dashboard with `scripts/localization_status.py`.
- `高风险也改`, `--allow-high-risk`: include high-risk translated items after validation.
- `i18n`: prefer i18n key migration where the repository already has an i18n runtime.
- `skills`, `skill`, `技能`, `本地skill`: switch to Local Skill Output Mode.

Direct apply workflow for shortcut commands:

1. Run `scripts/resolve_shortcut_command.py` on the current shortcut text. Use its `target_locale`, `target_language`, `mode`, `direct_apply`, `status_only`, and `options` fields as the source of truth.
2. If `localization-work` exists without `DONE.md`, run the pipeline with `--resume`. Otherwise run a fresh pipeline.
3. Run `scripts/run_localization_pipeline.py` from the current Hermes repo with `--mode both --out-dir localization-work`.
4. Report progress with `scripts/localization_status.py --work-dir localization-work` after each major phase and use `--watch 30` during long batch work.
5. Check `localization-work/version-update-report.md` to prioritize newly changed text after Hermes updates.
6. Use `scripts/manage_translation_batches.py --batches-dir localization-work/batches --retry-failed --next 3` to select the next small batch fan-out. Translate only `next_batches`, at most three concurrently.
7. After each batch result is written, rerun `manage_translation_batches.py`. It validates available results, updates progress, and creates smaller retry child batches for failed or truncated responses.
8. Merge validated batches with `scripts/merge_translation_results.py`.
9. Apply validated low and medium risk translations directly:

```bash
python scripts/apply_translation_results.py \
  --repo . \
  --request localization-work/translation-request.json \
  --translations localization-work/merged-translation-results.json \
  --out localization-work/apply-report.json \
  --markdown localization-work/apply-report.md \
  --rollback-patch localization-work/rollback.patch \
  --apply \
  --max-risk medium
```

Use `--max-risk high` only when the shortcut includes `高风险也改` or `--allow-high-risk`. Skip model-facing, ambiguous, generated, unmatched, or unsafe items and list them in the final report. The rollback patch can be checked or applied from the repo root with `git apply --check localization-work/rollback.patch` and `git apply localization-work/rollback.patch`.

Install short aliases when the user asks for local deployment:

```bash
python scripts/install_hermes_language_aliases.py
```

This installs `/语言`, `/lang`, `/hermes-lang`, and `/hermes-language` for Hermes project localization. It also installs `/技能语言`, `/skill-lang`, `/skills-lang`, and `/skill-language` for Local Skill Output Mode.

## Quick Start

1. Determine the target language from the user request or Shortcut Command Protocol. If the skill was invoked as bare `/zero-zero-three-hermes-language-management`, `/语言`, `/lang`, `/技能语言`, or `/skill-lang`, use `zh-CN` Simplified Chinese. If a non-shortcut natural-language request is missing a target language, ask for it.
2. If the repository has `localization-baseline.json`, `docs/zh-localization-map.md`, or another localization map, read it before scanning.
3. Run the scanner. Use JSON for automated patch planning and Markdown for human review:

```bash
python scripts/scan_user_facing_text.py <repo-root> --profile hermes --format json --out localization-candidates.json
python scripts/scan_user_facing_text.py <repo-root> --profile hermes --format markdown --out localization-candidates.md
```

4. Read `references/preserve-patterns.md`.
5. Read the target-language glossary if one exists, such as `references/glossary.zh-CN.md` or `references/glossary.ja-JP.md`.
6. Patch only strings classified as user-facing. Preserve command names, flags, env vars, config keys, IDs, URLs, paths, protocol values, model/provider/tool/skill names, and model-facing skill instructions.
7. Update or create a localization map in the repo, recording every changed file and field category.
8. Validate with project-appropriate commands.
9. Generate a report with `scripts/render_localization_report.py`.
10. Create or update `localization-baseline.json` with `scripts/update_localization_baseline.py`.
11. If the project uses locale files or the user wants language switching, run Multilingual Consistency Mode and i18n Key Migration Mode.

## One-Command Pipeline

Use this mode when the user asks to handle a Hermes update end to end or wants a single command that produces review artifacts. Shortcut commands use this as the first phase before translation validation and direct application.

```bash
python scripts/run_localization_pipeline.py . \
  --target-locale zh-CN \
  --mode both \
  --out-dir localization-work
```

The pipeline creates scan, delta, patch-plan, i18n migration, translation-request, consistency, and summary artifacts. The pipeline itself does not rewrite source code except deterministic locale fixes when explicitly requested; direct shortcut commands continue by validating model translations and running `apply_translation_results.py --apply`. Add `--surfaces tui web cli` for a focused pass. Add `--autofix-locales` to plan missing locale-key fixes. Add `--apply --autofix-locales` only after confirming deterministic locale key additions are desired.

The pipeline also writes:

- `localization-work/status.json`: current phase and latest message.
- `localization-work/progress.log`: append-only timeline.
- `localization-work/DONE.md` or `FAILED.md`: completion marker.
- `localization-work/batches/status.json`: translation batch status.
- `localization-work/batches/queue-report.json` and `.md`: next batches and retry queue state.
- `localization-work/version-update-report.json` and `.md`: adaptive update counts for new, changed, moved, removed, and still-untranslated candidates.

Check progress without interrupting the agent:

```bash
python scripts/localization_status.py --work-dir localization-work
python scripts/localization_status.py --work-dir localization-work --watch 30
```

Do not read or delegate the full `translation-request.json` when it has more than 100 items. Use the generated `localization-work/batches/batch-XXX.request.json` files. Default batches are capped at 40 items and approximately 12k JSON characters to avoid model output truncation.

After any batch result appears, run the queue manager:

```bash
python scripts/manage_translation_batches.py \
  --batches-dir localization-work/batches \
  --retry-failed \
  --next 3 \
  --out localization-work/batches/queue-report.json \
  --markdown localization-work/batches/queue-report.md
```

If a response is truncated, invalid JSON, missing ids, or fails placeholder checks, the queue manager marks the parent batch and creates smaller retry child batches such as `batch-000-r1-000`. Translate those retry batches before merging.

Resume interrupted work without overwriting batches:

```bash
python scripts/run_localization_pipeline.py . \
  --target-locale zh-CN \
  --mode both \
  --out-dir localization-work \
  --resume
```

## Adaptive Update Mode

Use this mode after Hermes is updated and an existing baseline is available. It should be the default when `localization-baseline.json` exists.

```bash
python scripts/scan_user_facing_text.py . --profile hermes --format json --out localization-scan-new.json
python scripts/diff_localization_scan.py \
  --baseline localization-baseline.json \
  --scan localization-scan-new.json \
  --out localization-delta.json \
  --summary localization-delta.md
python scripts/generate_patch_plan.py \
  --input localization-delta.json \
  --language zh-CN \
  --translation-memory translation-memory.json \
  --out localization-patch-plan.json \
  --markdown localization-patch-plan.md
```

Then patch only:

1. `new_candidates`: newly discovered user-facing strings.
2. `changed_candidates`: existing locations whose source text changed.
3. `still_untranslated`: candidates previously left pending/review after confirming they are user-facing.

Do not re-translate `moved_candidates`; update their recorded location through the next baseline update. Mark `removed_candidates` as removed in the next baseline.

Before editing, read `localization-patch-plan.json`. Patch low-risk items directly, patch medium-risk items while preserving every `preserve_tokens` entry, and inspect high-risk items before changing them.

After patching and validation:

```bash
python scripts/update_localization_baseline.py \
  --scan localization-scan-new.json \
  --baseline localization-baseline.json \
  --language zh-CN \
  --repo . \
  --out localization-baseline.json
```

Use the requested target language in `--language`.

## Version Update Report

Every pipeline run writes `localization-work/version-update-report.json` and `.md`. Use it to decide whether the current run is a first scan or an upstream-update pass.

Key fields:

- `mode`: `initial-scan` or `adaptive-update`.
- `actionable_candidates`: total items to translate or review now.
- `counts.new_candidates`: newly discovered user-visible strings.
- `counts.changed_candidates`: existing locations whose source text changed.
- `counts.moved_candidates`: known strings that moved location.
- `counts.removed_candidates`: baseline strings no longer present.
- `counts.still_untranslated`: previously pending/review items still present.

For adaptive updates, translate `new_candidates`, `changed_candidates`, and `still_untranslated` first. Do not re-translate `moved_candidates`.

## Local Skill Output Mode

Use this mode when the user wants to localize other local skills' user-visible output text. Trigger examples:

```text
/技能语言
/zero-zero-three-hermes-language-management skills 中文
/技能语言 日文
/skill-lang ko
```

Default target language is `zh-CN` Simplified Chinese. Default skill root is `~/.hermes/skills`, and the current language-management skill is excluded unless the user explicitly asks to include it.

Scan and prepare translation work:

```bash
python scripts/run_local_skill_output_pipeline.py \
  --skill-root ~/.hermes/skills \
  --target-locale zh-CN \
  --out-dir local-skill-language-work
```

The scanner targets output-facing skill surfaces:

- `agents/openai.yaml` interface fields: `display_name`, `short_description`, `default_prompt`.
- Text resources under `assets/`, `templates/`, and `examples/`.
- Optional `references/` and `docs/` only when the user asks to include them.
- `SKILL.md` frontmatter description only with explicit review mode.

Do not translate `SKILL.md` instruction bodies by default. Those are model-facing operating instructions, not ordinary user output. If the user explicitly asks to translate instruction bodies, treat every item as high risk and preserve tool names, command syntax, file paths, and trigger phrases.

After model translation batches are validated and merged, apply changes to the skill root:

```bash
python scripts/apply_translation_results.py \
  --repo ~/.hermes/skills \
  --request local-skill-language-work/translation-request.json \
  --translations local-skill-language-work/merged-translation-results.json \
  --out local-skill-language-work/apply-report.json \
  --markdown local-skill-language-work/apply-report.md \
  --rollback-patch local-skill-language-work/rollback.patch \
  --apply \
  --max-risk medium
```

Then run `/reload-skills` in Hermes so updated local skill metadata is visible.

## Hermes Workflow

Use this order for Hermes and Hermes forks:

1. If `localization-baseline.json` exists, run Adaptive Update Mode first.
2. If no baseline exists, run a full scan.
3. Patch Python CLI/gateway/tool strings.
4. Patch TUI TypeScript strings.
5. Patch Web source strings.
6. Rebuild Web if `web/src/**` changed so `hermes_cli/web_dist` is refreshed.
7. Re-scan or diff again for remaining user-visible English.
8. Run validation.
9. Update the baseline.

Recommended commands from repo root:

```bash
python scripts/scan_user_facing_text.py . --profile hermes --format json --out localization-candidates.json
python scripts/scan_user_facing_text.py . --profile hermes --format markdown --out localization-candidates.md
git diff --name-only -- '*.py' | xargs -r python3 -m py_compile
npm_config_script_shell=/bin/bash npm --prefix ui-tui run typecheck
npm_config_script_shell=/bin/bash npm --prefix web run build
git diff --check
```

If tests assert old English copy, do not blindly update all tests. Update only tests that intentionally cover user-visible localized output.

## Translation Rules

- Translate UI labels, buttons, dialogs, toasts, headings, status text, warnings, errors, empty states, help text, CLI prompts, and gateway messages sent to users.
- Keep placeholders intact: `{name}`, `{count}`, `%s`, `$VAR`, `${value}`, `{0}`, `<path>`.
- Keep command examples executable.
- Do not translate external provider output or subprocess stdout/stderr unless Hermes itself authored that text.
- Do not translate `SKILL.md` bodies used as model instructions unless the user explicitly asks to localize documentation rather than runtime UI.
- Prefer source-level changes. Avoid patching `dist`, `build`, `web_dist`, or generated assets unless the repo's build process regenerates them.

## Automatic Patching Behavior

When the user asks to automatically replace strings, proceed without proposing every individual translation. Still protect high-risk strings:

- If a candidate includes a command, config key, env var, URL, path, model ID, provider ID, or protocol value, translate only surrounding prose.
- If a string is model-facing prompt/instruction content, skip it and record it in the report.
- If a file is generated, patch the source file and rebuild.
- If a string's purpose is unclear, leave it unchanged and list it under "needs review".

Use this candidate priority:

1. In update mode, patch `new_candidates` and `changed_candidates` before doing any full-scan work.
2. Generate `localization-patch-plan.json`.
3. Patch `low` risk plan items first.
4. Patch `medium` risk items by translating prose around protected tokens.
5. Inspect `high` risk and `review_then_translate` items and patch only when clearly user-facing.
6. Do not patch `skip-*` candidates unless the user explicitly requests documentation or test localization.

## Patch Plan and Translation Memory

Generate a patch plan from either a full scan or an update delta:

```bash
python scripts/generate_patch_plan.py \
  --input localization-delta.json \
  --language zh-CN \
  --translation-memory translation-memory.json \
  --out localization-patch-plan.json \
  --markdown localization-patch-plan.md
```

If there is no `translation-memory.json`, proceed without it. If one exists, reuse `translation_memory_hit` exactly unless local grammar requires minor adjustment. Keep all `preserve_tokens` unchanged.

Translation memory shape:

```json
{
  "zh-CN": {
    "Start chatting": "开始聊天"
  },
  "ja-JP": {
    "Start chatting": "チャットを開始"
  }
}
```

After applying translations, add stable repeated source strings and their final translations to `translation-memory.json` when the repository owner wants persistent terminology. Do not add secrets, user data, URLs with credentials, or external provider output to translation memory.

If the baseline contains `translated_text` fields, update memory with:

```bash
python scripts/update_translation_memory.py \
  --memory translation-memory.json \
  --input localization-baseline.json \
  --language zh-CN
```

## Multilingual Consistency Mode

Use this mode when Hermes already has locale resources or after migrating hardcoded text into i18n keys.

```bash
python scripts/check_i18n_consistency.py \
  --locales-dir locales \
  --source-locale en \
  --format markdown \
  --out i18n-consistency.md
python scripts/check_i18n_consistency.py \
  --locales-dir locales \
  --source-locale en \
  --format json \
  --out i18n-consistency.json
```

Treat `missing-key`, `empty-value`, and `placeholder-mismatch` as blockers before claiming a locale is complete. Treat `identical-to-source`, `likely-untranslated`, and `extra-key` as review items. Use `--target-locales zh-CN ja-JP` for a focused check and `--fail-on errors` in CI.

For deterministic missing-key repair, generate a fix plan:

```bash
python scripts/apply_locale_consistency_fixes.py \
  --locales-dir locales \
  --source-locale en \
  --out locale-consistency-fixes.json \
  --markdown locale-consistency-fixes.md
```

Only add `--apply` when the user wants the script to write locale files. This script fills missing keys from the source locale by default, so follow it with translation-request export and review before considering the target language complete.

## Translation Request Mode

Use this mode when the next step is model translation rather than direct manual editing.

```bash
python scripts/export_translation_request.py \
  --input localization-patch-plan.json \
  --target-language "Simplified Chinese" \
  --target-locale zh-CN \
  --glossary references/glossary.zh-CN.md \
  --out translation-request.json \
  --prompt-out translation-request.md
```

The request JSON includes source text, file context, risk, action, preserve tokens, and response schema. Ask the model to return JSON only, then verify placeholders before applying the translations.

For large requests, split before translating:

```bash
python scripts/split_translation_request.py \
  --input localization-work/translation-request.json \
  --out-dir localization-work/batches \
  --batch-size 40 \
  --max-chars 12000 \
  --overwrite
python scripts/localization_status.py --work-dir localization-work
```

Translate one batch at a time or at most three small batches concurrently. Never delegate 400-item batches; that risks truncated model output and exhausted iteration budgets.

After a batch result is written, validate it:

```bash
python scripts/validate_translation_response.py \
  --request localization-work/batches/batch-000.request.json \
  --response localization-work/batches/batch-000.result.json \
  --out localization-work/batches/batch-000.validation.json \
  --fail-on errors
```

Prefer the queue manager for normal runs because it performs this validation automatically and creates retry batches when needed:

```bash
python scripts/manage_translation_batches.py --batches-dir localization-work/batches --retry-failed --next 3
```

Merge completed batches:

```bash
python scripts/merge_translation_results.py \
  --batches-dir localization-work/batches \
  --out localization-work/merged-translation-results.json \
  --require-validation \
  --update-status
```

For a shortcut command or any request that says to apply changes directly, apply merged results to the repository after validation:

```bash
python scripts/apply_translation_results.py \
  --repo . \
  --request localization-work/translation-request.json \
  --translations localization-work/merged-translation-results.json \
  --out localization-work/apply-report.json \
  --markdown localization-work/apply-report.md \
  --rollback-patch localization-work/rollback.patch \
  --apply \
  --max-risk medium
```

Use `--max-risk high` only when explicitly requested. If a source string cannot be matched exactly or is ambiguous, leave it unchanged and report it instead of guessing.

## i18n Key Migration Mode

Use this mode when the user wants durable language switching instead of one-off hardcoded replacements.

1. Read `references/i18n-migration-patterns.md`.
2. Generate or refresh a scan, delta, or patch plan.
3. Generate a migration plan:

```bash
python scripts/generate_i18n_migration_plan.py \
  --input localization-patch-plan.json \
  --namespace auto \
  --source-locale en \
  --target-locale zh-CN \
  --translation-memory translation-memory.json \
  --out i18n-migration-plan.json \
  --markdown i18n-migration-plan.md
```

4. Inspect the repository for its existing i18n helper and locale-file layout.
5. Add source and target locale entries before replacing runtime strings.
6. When translation results are validated and the repository already has an i18n helper, apply approved low/medium risk items with:

```bash
python scripts/apply_i18n_migration.py \
  --repo . \
  --plan localization-work/i18n-migration-plan.json \
  --translations localization-work/merged-translation-results.json \
  --locales-dir locales \
  --source-locale en \
  --target-locale zh-CN \
  --out localization-work/i18n-apply-report.json \
  --markdown localization-work/i18n-apply-report.md \
  --rollback-patch localization-work/i18n-rollback.patch \
  --apply \
  --max-risk medium
```

7. Replace only approved `replace_with_i18n_key` items with the local helper pattern. The executor writes source and target locale values first, then replaces exact source text with helper calls such as `t("key")`.
8. Inspect `inspect_before_migration`, high-risk, helper-missing, source-not-found, or missing-translation items before editing; skip model-facing or ambiguous strings.
9. Run Multilingual Consistency Mode and project validation.

Do not invent a new i18n runtime unless the user explicitly requests it. If no helper exists, report the required integration points and keep the migration plan as the handoff artifact.

## CI Gate Mode

Use these commands in CI or release checks:

```bash
python scripts/check_i18n_consistency.py --locales-dir locales --source-locale en --fail-on errors
python scripts/run_localization_pipeline.py . --target-locale zh-CN --mode both --out-dir localization-work --skip-consistency
```

The first command blocks missing keys, empty values, and placeholder mismatches. The second command refreshes localization artifacts for review; keep it non-mutating in CI unless the workflow opens a bot PR.

## Reporting

At the end, summarize:

- Target language.
- Files changed by surface: CLI, gateway, TUI, Web, tools, docs/map.
- Progress status from `localization_status.py`.
- Version update counts from `version-update-report.md`.
- Rollback patch path, usually `localization-work/rollback.patch`.
- Validation commands and results.
- Remaining English categories intentionally preserved.
- Any low-confidence candidates left for review.

Keep the final report concise and do not claim all English is gone. Say that all scanned user-facing candidates were handled, and list intentional remaining English categories.

Generate an artifact report when useful:

```bash
git diff --name-only > localization-changed-files.txt
python scripts/render_localization_report.py \
  --language zh-CN \
  --repo . \
  --candidates localization-candidates.json \
  --changed-files localization-changed-files.txt \
  --validation "py_compile: passed" \
  --validation "ui-tui typecheck: passed" \
  --validation "web build: passed" \
  --validation "git diff --check: passed" \
  --out localization-report.md
```

Create/update a baseline:

```bash
python scripts/update_localization_baseline.py \
  --scan localization-candidates.json \
  --language zh-CN \
  --repo . \
  --out localization-baseline.json
```

When updating an existing baseline, pass `--baseline localization-baseline.json`.

## Resources

- `scripts/scan_user_facing_text.py`: deterministic scanner for likely user-facing strings.
- `scripts/resolve_shortcut_command.py`: deterministic parser for slash command arguments, target locale defaults, modes, and options.
- `scripts/diff_localization_scan.py`: compares a fresh scan with a baseline and emits update-only deltas.
- `scripts/generate_patch_plan.py`: creates a risk-ranked patch plan with preserve tokens, memory hits, and validation suggestions.
- `scripts/generate_i18n_migration_plan.py`: converts scan, delta, or patch-plan artifacts into stable i18n key migration work items.
- `scripts/apply_i18n_migration.py`: applies approved i18n migration items to locale files and source helper calls, with rollback patch generation.
- `scripts/export_translation_request.py`: exports patch or migration plans as model-facing translation batches.
- `scripts/run_localization_pipeline.py`: runs the scan, delta, plan, migration, translation-request, consistency, and summary artifact pipeline.
- `scripts/scan_local_skill_outputs.py`: scans local skill output-facing metadata and resource text.
- `scripts/run_local_skill_output_pipeline.py`: creates translation requests and batches for local skill output localization.
- `scripts/split_translation_request.py`: splits large translation requests into resumable small batch files.
- `scripts/manage_translation_batches.py`: validates available batch results, tracks queue progress, selects next batches, and creates smaller retry batches after failed or truncated responses.
- `scripts/localization_status.py`: prints pipeline, version-update, batch, apply, and rollback progress; supports `--watch`.
- `scripts/validate_translation_response.py`: validates batch translations for JSON shape, missing ids, placeholders, and preserve tokens.
- `scripts/merge_translation_results.py`: merges validated batch results into one translation result artifact.
- `scripts/apply_translation_results.py`: applies validated translation results to source files by exact source-text replacement, generates rollback patches, and reports skipped unsafe or ambiguous items.
- `scripts/install_hermes_language_aliases.py`: installs `/语言`, `/lang`, `/hermes-lang`, `/hermes-language`, `/技能语言`, `/skill-lang`, `/skills-lang`, and `/skill-language` quick-command aliases for local Hermes.
- `scripts/check_i18n_consistency.py`: checks locale files for missing keys, extra keys, placeholder mismatches, empty values, and likely untranslated text.
- `scripts/apply_locale_consistency_fixes.py`: plans or applies deterministic locale missing-key and empty-value fixes.
- `scripts/update_localization_baseline.py`: creates or refreshes a stable localization baseline.
- `scripts/update_translation_memory.py`: merges reviewed translations into translation memory.
- `scripts/render_localization_report.py`: report renderer for candidate counts, changed files, validation, and review items.
- `references/preserve-patterns.md`: exact preservation and classification policy.
- `references/i18n-migration-patterns.md`: i18n key naming, replacement, and locale consistency policy.
- `references/glossary.zh-CN.md`: Simplified Chinese terminology.
- `references/glossary.ja-JP.md`: Japanese terminology.
- `references/translation-memory.example.json`: example translation memory format.
