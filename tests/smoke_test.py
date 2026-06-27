#!/usr/bin/env python3
"""Release smoke tests for the Hermes language-management skill."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "zero-zero-three-hermes-language-management"
SCRIPTS = SKILL / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "hermes-mini"


def run(command: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(
            "command failed: {}\nstdout:\n{}\nstderr:\n{}".format(" ".join(command), proc.stdout, proc.stderr)
        )
    return proc


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_skill_shape() -> None:
    skill_md = SKILL / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    assert "\nname: zero-zero-three-hermes-language-management\n" in text
    assert "\ndescription:" in text
    assert "## Default Target Guard" in text
    assert "Bare invocations with no target" in text
    assert "must use `zh-CN`" in text
    assert "Do not infer Japanese" in text
    openai_yaml = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "bare /zero-zero-three-hermes-language-management" in openai_yaml
    assert "default to Simplified Chinese (zh-CN)" in openai_yaml
    assert "resolve_shortcut_command.py" in text
    assert "manage_translation_batches.py" in text
    assert "apply_i18n_migration.py" in text
    forbidden = {"README.md", "INSTALLATION_GUIDE.md", "QUICK_REFERENCE.md", "CHANGELOG.md", "LICENSE"}
    present = {path.name for path in SKILL.iterdir()}
    assert not (present & forbidden), f"skill folder contains release-only files: {present & forbidden}"


def validate_release_metadata() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), "VERSION must use semantic version format"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert f"v{version}" in readme, "README should mention the current release version"
    assert f"v{version}" in release_notes, "RELEASE_NOTES should contain the current version"
    assert "resolve_shortcut_command.py" in readme
    assert "manage_translation_batches.py" in readme
    assert "apply_i18n_migration.py" in readme


def check_release_boundary() -> None:
    forbidden = [
        re.compile("C:" + r"\\Users\\" + "aaaa", re.IGNORECASE),
        re.compile("/home/" + "aaaa"),
        re.compile("wsl" + r"\.localhost", re.IGNORECASE),
        re.compile("AppData" + r"[\\/]+Local[\\/]+Temp", re.IGNORECASE),
    ]
    ignored_parts = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    for path in ROOT.rglob("*"):
        if any(part in ignored_parts for part in path.parts):
            continue
        if path.is_dir() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in forbidden:
            assert not pattern.search(text), f"local machine path leaked in {path}"


def main() -> int:
    validate_skill_shape()
    validate_release_metadata()
    check_release_boundary()

    run([sys.executable, "-m", "py_compile", *[str(path) for path in sorted(SCRIPTS.glob("*.py"))]])

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        scan = tmp_path / "scan.json"
        scan_md = tmp_path / "scan.md"
        patch_plan = tmp_path / "patch-plan.json"
        patch_md = tmp_path / "patch-plan.md"
        migration = tmp_path / "migration.json"
        migration_md = tmp_path / "migration.md"
        request = tmp_path / "translation-request.json"
        batches_dir = tmp_path / "batches"
        first_batch_result = batches_dir / "batch-000.result.json"
        first_batch_validation = batches_dir / "batch-000.validation.json"
        merged_results = tmp_path / "merged-results.json"
        queue_report = tmp_path / "queue-report.json"
        queue_md = tmp_path / "queue-report.md"
        retry_request = tmp_path / "retry-request.json"
        retry_batches = tmp_path / "retry-batches"
        retry_queue = tmp_path / "retry-queue.json"
        apply_repo = tmp_path / "apply-repo"
        apply_report = tmp_path / "apply-report.json"
        apply_md = tmp_path / "apply-report.md"
        rollback_patch = tmp_path / "rollback.patch"
        i18n_repo = tmp_path / "i18n-repo"
        i18n_plan = tmp_path / "i18n-plan.json"
        i18n_translations = tmp_path / "i18n-translations.json"
        i18n_apply_report = tmp_path / "i18n-apply-report.json"
        i18n_apply_md = tmp_path / "i18n-apply-report.md"
        i18n_rollback = tmp_path / "i18n-rollback.patch"
        alias_config = tmp_path / "config.yaml"
        local_skill_root = tmp_path / "local-skills"
        local_skill_work = tmp_path / "local-skill-work"
        local_skill_request = local_skill_work / "translation-request.json"
        local_skill_batches = local_skill_work / "batches"
        local_skill_result = local_skill_batches / "batch-000.result.json"
        local_skill_validation = local_skill_batches / "batch-000.validation.json"
        local_skill_merged = local_skill_work / "merged-results.json"
        local_skill_apply = local_skill_work / "apply-report.json"
        local_skill_rollback = local_skill_work / "rollback.patch"
        consistency = tmp_path / "consistency.json"
        locale_fix = tmp_path / "locale-fix.json"
        pipeline_dir = tmp_path / "pipeline"

        shortcut_default = load_json(
            Path(
                run(
                    [
                        sys.executable,
                        str(SCRIPTS / "resolve_shortcut_command.py"),
                        "--command",
                        "/zero-zero-three-hermes-language-management",
                        "--out",
                        str(tmp_path / "shortcut-default.json"),
                        "--json",
                    ]
                ).stdout
                and (tmp_path / "shortcut-default.json")
            )
        )
        assert shortcut_default["target_locale"] == "zh-CN"
        assert shortcut_default["defaulted_target"] is True
        shortcut_ja = json.loads(
            run(
                [
                    sys.executable,
                    str(SCRIPTS / "resolve_shortcut_command.py"),
                    "--command",
                    "/语言 日文 续跑",
                    "--json",
                ]
            ).stdout
        )
        assert shortcut_ja["target_locale"] == "ja-JP"
        assert shortcut_ja["options"]["resume"] is True
        shortcut_skills = json.loads(
            run(
                [
                    sys.executable,
                    str(SCRIPTS / "resolve_shortcut_command.py"),
                    "--command",
                    "/技能语言",
                    "--json",
                ]
            ).stdout
        )
        assert shortcut_skills["mode"] == "skill-output"
        assert shortcut_skills["target_locale"] == "zh-CN"

        run(
            [
                sys.executable,
                str(SCRIPTS / "scan_user_facing_text.py"),
                str(FIXTURE),
                "--profile",
                "hermes",
                "--format",
                "json",
                "--classes",
                "translate",
                "mixed-preserve",
                "review",
                "--out",
                str(scan),
            ]
        )
        candidates = load_json(scan)
        assert candidates, "scanner should find fixture candidates"

        run(
            [
                sys.executable,
                str(SCRIPTS / "scan_user_facing_text.py"),
                str(FIXTURE),
                "--profile",
                "hermes",
                "--format",
                "markdown",
                "--classes",
                "translate",
                "mixed-preserve",
                "review",
                "--out",
                str(scan_md),
            ]
        )
        assert scan_md.exists()

        run(
            [
                sys.executable,
                str(SCRIPTS / "generate_patch_plan.py"),
                "--input",
                str(scan),
                "--language",
                "zh-CN",
                "--out",
                str(patch_plan),
                "--markdown",
                str(patch_md),
                "--include-review",
            ]
        )
        assert load_json(patch_plan)["items"], "patch plan should contain items"

        run(
            [
                sys.executable,
                str(SCRIPTS / "generate_i18n_migration_plan.py"),
                "--input",
                str(patch_plan),
                "--namespace",
                "auto",
                "--source-locale",
                "en",
                "--target-locale",
                "zh-CN",
                "--out",
                str(migration),
                "--markdown",
                str(migration_md),
            ]
        )
        assert load_json(migration)["items"], "migration plan should contain items"

        run(
            [
                sys.executable,
                str(SCRIPTS / "export_translation_request.py"),
                "--input",
                str(migration),
                "--target-language",
                "Simplified Chinese",
                "--target-locale",
                "zh-CN",
                "--out",
                str(request),
            ]
        )
        assert load_json(request)["items"], "translation request should contain items"

        run(
            [
                sys.executable,
                str(SCRIPTS / "split_translation_request.py"),
                "--input",
                str(request),
                "--out-dir",
                str(batches_dir),
                "--batch-size",
                "2",
                "--max-chars",
                "5000",
            ]
        )
        batch_status = load_json(batches_dir / "status.json")
        assert batch_status["batch_count"] >= 1
        first_batch = load_json(batches_dir / "batch-000.request.json")
        first_batch_result.write_text(
            json.dumps(
                {
                    "translations": [
                        {
                            "id": item["id"],
                            "translated_text": "翻译：" + item["source_text"],
                            "skip": False,
                            "reason": "",
                        }
                        for item in first_batch["items"]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "validate_translation_response.py"),
                "--request",
                str(batches_dir / "batch-000.request.json"),
                "--response",
                str(first_batch_result),
                "--out",
                str(first_batch_validation),
                "--fail-on",
                "errors",
            ]
        )
        assert load_json(first_batch_validation)["status"] in {"pass", "warn"}
        run(
            [
                sys.executable,
                str(SCRIPTS / "manage_translation_batches.py"),
                "--batches-dir",
                str(batches_dir),
                "--next",
                "2",
                "--out",
                str(queue_report),
                "--markdown",
                str(queue_md),
                "--json",
            ]
        )
        queue_data = load_json(queue_report)
        assert queue_data["summary"]["completed_batches"] >= 1
        assert queue_md.exists()
        run(
            [
                sys.executable,
                str(SCRIPTS / "merge_translation_results.py"),
                "--batches-dir",
                str(batches_dir),
                "--out",
                str(merged_results),
                "--require-validation",
                "--update-status",
            ]
        )
        assert load_json(merged_results)["summary"]["translation_count"] >= 1
        run([sys.executable, str(SCRIPTS / "localization_status.py"), "--work-dir", str(tmp_path), "--json"])

        retry_request.write_text(
            json.dumps(
                {
                    "schema": "zero-zero-three.translation-request",
                    "source_language": "English",
                    "target_language": "Simplified Chinese",
                    "target_locale": "zh-CN",
                    "response_schema": {"translations": []},
                    "items": [
                        {"id": "retry-a", "source_text": "Retry this", "preserve_tokens": []},
                        {"id": "retry-b", "source_text": "Retry that", "preserve_tokens": []},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "split_translation_request.py"),
                "--input",
                str(retry_request),
                "--out-dir",
                str(retry_batches),
                "--batch-size",
                "2",
                "--max-chars",
                "5000",
            ]
        )
        (retry_batches / "batch-000.result.json").write_text(
            json.dumps(
                {
                    "translations": [
                        {"id": "retry-a", "translated_text": "重试这个", "skip": False, "reason": ""}
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "manage_translation_batches.py"),
                "--batches-dir",
                str(retry_batches),
                "--retry-failed",
                "--retry-batch-size",
                "1",
                "--retry-max-chars",
                "1000",
                "--out",
                str(retry_queue),
            ]
        )
        retry_data = load_json(retry_queue)
        assert len(retry_data["created_retry_batches"]) == 2
        retry_status = load_json(retry_batches / "status.json")
        assert retry_status["pending_batches"] >= 2

        shutil.copytree(FIXTURE, apply_repo)
        run(
            [
                sys.executable,
                str(SCRIPTS / "apply_translation_results.py"),
                "--repo",
                str(apply_repo),
                "--request",
                str(request),
                "--translations",
                str(merged_results),
                "--out",
                str(apply_report),
                "--markdown",
                str(apply_md),
                "--rollback-patch",
                str(rollback_patch),
                "--apply",
                "--max-risk",
                "medium",
            ]
        )
        apply_data = load_json(apply_report)
        assert apply_data["summary"]["applied"] >= 1
        assert apply_md.exists()
        assert rollback_patch.exists()
        assert apply_data["rollback_patch"] == str(rollback_patch)
        assert "翻译：" in (apply_repo / "cli.py").read_text(encoding="utf-8") or "翻译：" in (
            apply_repo / "ui-tui" / "src" / "App.tsx"
        ).read_text(encoding="utf-8")
        run(["git", "apply", "--check", str(rollback_patch)], cwd=apply_repo)

        alias_config.write_text("quick_commands: {}\n", encoding="utf-8")
        run(
            [
                sys.executable,
                str(SCRIPTS / "install_hermes_language_aliases.py"),
                "--config",
                str(alias_config),
                "--aliases",
                "语言",
                "lang",
                "--json",
            ]
        )
        alias_text = alias_config.read_text(encoding="utf-8")
        assert "语言:" in alias_text
        assert "技能语言:" in alias_text
        assert "target: zero-zero-three-hermes-language-management" in alias_text
        assert "target: zero-zero-three-hermes-language-management skills" in alias_text

        sample_skill = local_skill_root / "sample-output-skill"
        (sample_skill / "agents").mkdir(parents=True)
        (sample_skill / "assets").mkdir()
        (sample_skill / "SKILL.md").write_text(
            "---\nname: sample-output-skill\ndescription: Creates a friendly status update.\n---\n\n# Sample\n",
            encoding="utf-8",
        )
        (sample_skill / "agents" / "openai.yaml").write_text(
            'interface:\n  display_name: "Sample Output Skill"\n  short_description: "Creates friendly status updates"\n  default_prompt: "Use $sample-output-skill to draft a weekly update."\n',
            encoding="utf-8",
        )
        (sample_skill / "assets" / "template.md").write_text("# Weekly Update\n\nReady to share with your team.\n", encoding="utf-8")
        run(
            [
                sys.executable,
                str(SCRIPTS / "run_local_skill_output_pipeline.py"),
                "--skill-root",
                str(local_skill_root),
                "--target-locale",
                "zh-CN",
                "--out-dir",
                str(local_skill_work),
            ]
        )
        local_pipeline = load_json(local_skill_work / "pipeline-report.json")
        assert local_pipeline["counts"]["scan_candidates"] >= 2
        assert local_pipeline["counts"]["translation_request_items"] >= 2
        local_batch = load_json(local_skill_batches / "batch-000.request.json")
        local_skill_result.write_text(
            json.dumps(
                {
                    "translations": [
                        {
                            "id": item["id"],
                            "translated_text": "技能翻译：" + item["source_text"],
                            "skip": False,
                            "reason": "",
                        }
                        for item in local_batch["items"]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "validate_translation_response.py"),
                "--request",
                str(local_skill_batches / "batch-000.request.json"),
                "--response",
                str(local_skill_result),
                "--out",
                str(local_skill_validation),
                "--fail-on",
                "errors",
            ]
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "merge_translation_results.py"),
                "--batches-dir",
                str(local_skill_batches),
                "--out",
                str(local_skill_merged),
                "--require-validation",
                "--update-status",
            ]
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "apply_translation_results.py"),
                "--repo",
                str(local_skill_root),
                "--request",
                str(local_skill_request),
                "--translations",
                str(local_skill_merged),
                "--out",
                str(local_skill_apply),
                "--rollback-patch",
                str(local_skill_rollback),
                "--apply",
                "--max-risk",
                "medium",
            ]
        )
        assert "技能翻译：" in (sample_skill / "agents" / "openai.yaml").read_text(encoding="utf-8") or "技能翻译：" in (
            sample_skill / "assets" / "template.md"
        ).read_text(encoding="utf-8")
        assert local_skill_rollback.exists()

        (i18n_repo / "locales").mkdir(parents=True)
        (i18n_repo / "app.py").write_text('from i18n import t\n\nprint("Hello world")\n', encoding="utf-8")
        (i18n_repo / "locales" / "en.yaml").write_text("app:\n  existing: \"Existing\"\n", encoding="utf-8")
        (i18n_repo / "locales" / "zh-CN.yaml").write_text("app:\n  existing: \"已有\"\n", encoding="utf-8")
        i18n_plan.write_text(
            json.dumps(
                {
                    "schema": "zero-zero-three.hermes-i18n-key-migration-plan",
                    "source_locale": "en",
                    "target_locale": "zh-CN",
                    "items": [
                        {
                            "id": "i18n-1",
                            "path": "app.py",
                            "line": 3,
                            "risk": "low",
                            "action": "replace_with_i18n_key",
                            "source_text": "Hello world",
                            "suggested_key": "cli.helloWorld",
                            "source_locale_value": "Hello world",
                            "target_locale_value": "",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        i18n_translations.write_text(
            json.dumps(
                {
                    "translations": [
                        {"id": "i18n-1", "translated_text": "你好，世界", "skip": False, "reason": ""}
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(SCRIPTS / "apply_i18n_migration.py"),
                "--repo",
                str(i18n_repo),
                "--plan",
                str(i18n_plan),
                "--translations",
                str(i18n_translations),
                "--out",
                str(i18n_apply_report),
                "--markdown",
                str(i18n_apply_md),
                "--rollback-patch",
                str(i18n_rollback),
                "--apply",
            ]
        )
        assert 't("cli.helloWorld")' in (i18n_repo / "app.py").read_text(encoding="utf-8")
        assert "helloWorld" in (i18n_repo / "locales" / "en.yaml").read_text(encoding="utf-8")
        assert "你好，世界" in (i18n_repo / "locales" / "zh-CN.yaml").read_text(encoding="utf-8")
        assert load_json(i18n_apply_report)["summary"]["applied"] == 1
        assert i18n_apply_md.exists()
        assert i18n_rollback.exists()

        run(
            [
                sys.executable,
                str(SCRIPTS / "check_i18n_consistency.py"),
                "--locales-dir",
                str(FIXTURE / "locales"),
                "--source-locale",
                "en",
                "--format",
                "json",
                "--out",
                str(consistency),
            ]
        )
        consistency_report = load_json(consistency)
        assert consistency_report["summary"]["issue_count"] >= 1

        run(
            [
                sys.executable,
                str(SCRIPTS / "apply_locale_consistency_fixes.py"),
                "--locales-dir",
                str(FIXTURE / "locales"),
                "--source-locale",
                "en",
                "--out",
                str(locale_fix),
            ]
        )
        assert load_json(locale_fix)["plan"]["summary"]["change_count"] >= 1

        run(
            [
                sys.executable,
                str(SCRIPTS / "run_localization_pipeline.py"),
                str(FIXTURE),
                "--target-locale",
                "zh-CN",
                "--mode",
                "both",
                "--out-dir",
                str(pipeline_dir),
            ]
        )
        pipeline = load_json(pipeline_dir / "pipeline-report.json")
        assert pipeline["counts"]["scan_candidates"] >= 1
        assert pipeline["counts"]["translation_request_items"] >= 1
        assert pipeline["counts"]["translation_batch_count"] >= 1
        assert pipeline["counts"]["version_update_actionable"] >= 1
        assert (pipeline_dir / "status.json").exists()
        assert (pipeline_dir / "progress.log").exists()
        assert (pipeline_dir / "DONE.md").exists()
        assert (pipeline_dir / "batches" / "status.json").exists()
        assert (pipeline_dir / "version-update-report.json").exists()
        (pipeline_dir / "DONE.md").unlink()
        run(
            [
                sys.executable,
                str(SCRIPTS / "run_localization_pipeline.py"),
                str(FIXTURE),
                "--target-locale",
                "zh-CN",
                "--mode",
                "both",
                "--out-dir",
                str(pipeline_dir),
                "--resume",
            ]
        )
        resumed = load_json(pipeline_dir / "pipeline-report.json")
        assert any(step.get("skipped") for step in resumed["steps"])
        status_text = run([sys.executable, str(SCRIPTS / "localization_status.py"), "--work-dir", str(pipeline_dir)]).stdout
        assert "Update:" in status_text
        assert "Batches:" in status_text

    print("smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
