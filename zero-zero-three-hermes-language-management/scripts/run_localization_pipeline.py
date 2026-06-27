#!/usr/bin/env python3
"""Run the Hermes localization workflow as a deterministic artifact pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "zh-CN": "Simplified Chinese",
    "zh-Hans": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese",
    "ja": "Japanese",
    "ja-JP": "Japanese",
    "ko": "Korean",
    "ko-KR": "Korean",
    "en": "English",
    "en-US": "English",
}


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def run_step(name: str, command: list[str], cwd: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True)
    return {
        "name": name,
        "command": command,
        "returncode": proc.returncode,
        "started_at": started,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def skipped_step(name: str, command: list[str], reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "command": command,
        "returncode": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stdout": "",
        "stderr": "",
        "skipped": True,
        "reason": reason,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_ok(step: dict[str, Any]) -> None:
    if step["returncode"] != 0:
        cmd = " ".join(step["command"])
        raise RuntimeError(f"Step failed: {step['name']} ({cmd})\n{step.get('stderr') or step.get('stdout')}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_count(path: Path, key: str | None = None) -> int | None:
    if not path.exists():
        return None
    data = load_json(path)
    if isinstance(data, list):
        return len(data)
    if key and isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return len(data["items"])
    return None


def default_target_language(locale: str) -> str:
    return LANGUAGE_NAMES.get(locale, locale)


def locale_glossary(skill_root: Path, target_locale: str) -> Path | None:
    candidates = [
        skill_root / "references" / f"glossary.{target_locale}.md",
        skill_root / "references" / f"glossary.{target_locale.split('-')[0]}.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def all_exist(paths: list[Path]) -> bool:
    return bool(paths) and all(path.exists() for path in paths)


def delta_count(delta: dict[str, Any], key: str) -> int:
    value = delta.get(key)
    return len(value) if isinstance(value, list) else 0


def write_version_update_report(
    json_path: Path,
    markdown_path: Path,
    *,
    repo: Path,
    target_locale: str,
    baseline: Path,
    scan_json: Path,
    delta_json: Path,
) -> dict[str, Any]:
    scan_count = maybe_count(scan_json) or 0
    baseline_exists = baseline.exists()
    delta: dict[str, Any] = {}
    if baseline_exists and delta_json.exists():
        loaded = load_json(delta_json)
        if isinstance(loaded, dict):
            delta = loaded

    if baseline_exists and delta:
        counts = {
            "new_candidates": delta_count(delta, "new_candidates"),
            "changed_candidates": delta_count(delta, "changed_candidates"),
            "moved_candidates": delta_count(delta, "moved_candidates"),
            "removed_candidates": delta_count(delta, "removed_candidates"),
            "still_untranslated": delta_count(delta, "still_untranslated"),
        }
        mode = "adaptive-update"
    else:
        counts = {
            "scan_candidates": scan_count,
            "new_candidates": scan_count,
            "changed_candidates": 0,
            "moved_candidates": 0,
            "removed_candidates": 0,
            "still_untranslated": 0,
        }
        mode = "initial-scan"

    actionable = counts.get("new_candidates", 0) + counts.get("changed_candidates", 0) + counts.get("still_untranslated", 0)
    report = {
        "schema": "zero-zero-three.version-update-report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "target_locale": target_locale,
        "mode": mode,
        "baseline": str(baseline) if baseline_exists else None,
        "scan": str(scan_json),
        "delta": str(delta_json) if delta else None,
        "counts": counts,
        "actionable_candidates": actionable,
    }
    write_json(json_path, report)

    lines = [
        "# Version Update Localization Report",
        "",
        f"- Mode: `{mode}`",
        f"- Target locale: `{target_locale}`",
        f"- Scan candidates: {scan_count}",
        f"- Actionable candidates: {actionable}",
        "",
        "## Counts",
        "",
    ]
    for key, value in counts.items():
        lines.append(f"- `{key}`: {value}")
    if mode == "adaptive-update":
        lines.extend([
            "",
            "Patch `new_candidates`, `changed_candidates`, and `still_untranslated`; update locations for moved candidates; mark removed candidates in the next baseline.",
        ])
    else:
        lines.extend(["", "No baseline was found; treat this as the first full localization pass."])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def write_summary(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Localization Pipeline Report",
        "",
        f"- Repository: `{report['repo']}`",
        f"- Target locale: `{report['target_locale']}`",
        f"- Mode: `{report['mode']}`",
        f"- Output directory: `{report['out_dir']}`",
        "",
        "## Artifacts",
        "",
    ]
    for name, value in report.get("artifacts", {}).items():
        if value:
            lines.append(f"- `{name}`: `{value}`")
    lines.extend(["", "## Counts", ""])
    for name, value in report.get("counts", {}).items():
        if value is not None:
            lines.append(f"- `{name}`: {value}")
    lines.extend(["", "## Steps", "", "| Step | Result |", "|---|---|"])
    for step in report.get("steps", []):
        status = "passed" if step["returncode"] == 0 else f"failed ({step['returncode']})"
        lines.append(f"| `{step['name']}` | `{status}` |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Hermes localization artifact pipeline.")
    parser.add_argument("repo", nargs="?", default=".", type=Path, help="Repository root")
    parser.add_argument("--target-locale", default="zh-CN")
    parser.add_argument("--target-language", help="Human-readable target language")
    parser.add_argument("--source-locale", default="en")
    parser.add_argument("--mode", choices=("hardcoded-replace", "i18n-key-migration", "both"), default="both")
    parser.add_argument("--out-dir", type=Path, default=Path("localization-work"))
    parser.add_argument("--profile", choices=("hermes", "generic"), default="hermes")
    parser.add_argument("--classes", nargs="*", default=["translate", "mixed-preserve", "review"])
    parser.add_argument("--surfaces", nargs="*", help="Optional scan surfaces")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--include-ci", action="store_true")
    parser.add_argument("--include-docs", action="store_true")
    parser.add_argument("--baseline", type=Path, default=Path("localization-baseline.json"))
    parser.add_argument("--translation-memory", type=Path, default=Path("translation-memory.json"))
    parser.add_argument("--locales-dir", type=Path, default=Path("locales"))
    parser.add_argument("--skip-consistency", action="store_true")
    parser.add_argument("--autofix-locales", action="store_true", help="Plan deterministic locale missing-key fixes.")
    parser.add_argument("--apply", action="store_true", help="Apply deterministic locale fixes when used with --autofix-locales.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop immediately when a sub-step fails.")
    parser.add_argument("--translation-batch-size", type=int, default=40, help="Maximum translation-request items per batch")
    parser.add_argument("--translation-batch-max-chars", type=int, default=12000, help="Approximate maximum JSON chars per translation batch")
    parser.add_argument("--translation-concurrency", type=int, default=3, help="Number of next translation batches to select")
    parser.add_argument("--no-translation-batches", action="store_true", help="Do not split translation-request.json into batches")
    parser.add_argument("--resume", action="store_true", help="Reuse existing artifacts and preserve completed translation batches")
    parser.add_argument("--force", action="store_true", help="Rebuild artifacts even when --resume could skip them")
    args = parser.parse_args()

    repo = args.repo.resolve()
    skill_scripts = script_dir()
    skill_root = skill_scripts.parent
    out_dir = args.out_dir if args.out_dir.is_absolute() else repo / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    target_language = args.target_language or default_target_language(args.target_locale)

    scan_json = out_dir / "localization-scan.json"
    scan_md = out_dir / "localization-scan.md"
    delta_json = out_dir / "localization-delta.json"
    delta_md = out_dir / "localization-delta.md"
    patch_plan_json = out_dir / "localization-patch-plan.json"
    patch_plan_md = out_dir / "localization-patch-plan.md"
    migration_json = out_dir / "i18n-migration-plan.json"
    migration_md = out_dir / "i18n-migration-plan.md"
    consistency_json = out_dir / "i18n-consistency.json"
    consistency_md = out_dir / "i18n-consistency.md"
    locale_fix_json = out_dir / "locale-consistency-fixes.json"
    locale_fix_md = out_dir / "locale-consistency-fixes.md"
    translation_request_json = out_dir / "translation-request.json"
    translation_request_md = out_dir / "translation-request.md"
    version_report_json = out_dir / "version-update-report.json"
    version_report_md = out_dir / "version-update-report.md"
    pipeline_json = out_dir / "pipeline-report.json"
    pipeline_md = out_dir / "pipeline-report.md"
    status_json = out_dir / "status.json"
    progress_log = out_dir / "progress.log"
    done_md = out_dir / "DONE.md"
    failed_md = out_dir / "FAILED.md"
    batches_dir = out_dir / "batches"
    batch_queue_json = batches_dir / "queue-report.json"
    batch_queue_md = batches_dir / "queue-report.md"

    steps: list[dict[str, Any]] = []
    artifacts: dict[str, str | None] = {}
    counts: dict[str, int | None] = {}

    def update_status(state: str, phase: str, message: str, step: str | None = None) -> None:
        payload = {
            "schema": "zero-zero-three.localization-pipeline-status",
            "state": state,
            "phase": phase,
            "step": step,
            "message": message,
            "repo": str(repo),
            "target_locale": args.target_locale,
            "target_language": target_language,
            "mode": args.mode,
            "resume": bool(args.resume),
            "out_dir": str(out_dir),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifacts,
            "counts": counts,
            "steps": [
                {"name": item["name"], "returncode": item["returncode"], "started_at": item["started_at"]}
                for item in steps
            ],
        }
        write_json(status_json, payload)
        with progress_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{payload['updated_at']} {state} {phase} {message}\n")

    def call(name: str, command: list[str]) -> dict[str, Any]:
        print(f"[{len(steps) + 1}] {name} started", flush=True)
        update_status("running", name, f"{name} started", name)
        step = run_step(name, command, repo)
        steps.append(step)
        if step["returncode"] == 0:
            print(f"[{len(steps)}] {name} completed", flush=True)
            update_status("running", name, f"{name} completed", name)
        else:
            print(f"[{len(steps)}] {name} failed ({step['returncode']})", flush=True)
            update_status("failed", name, f"{name} failed with return code {step['returncode']}", name)
            failed_md.write_text(
                f"# Localization Pipeline Failed\n\nStep `{name}` failed with return code `{step['returncode']}`.\n\n",
                encoding="utf-8",
            )
        if args.fail_fast:
            require_ok(step)
        return step

    def call_or_resume(name: str, command: list[str], outputs: list[Path]) -> dict[str, Any]:
        if args.resume and not args.force and all_exist(outputs):
            step = skipped_step(name, command, "resume artifact exists")
            steps.append(step)
            print(f"[{len(steps)}] {name} skipped (resume)", flush=True)
            update_status("running", name, f"{name} skipped; resume artifacts already exist", name)
            return step
        return call(name, command)

    if args.resume and done_md.exists() and pipeline_json.exists() and not args.force:
        update_status("complete", "resume", "existing completed pipeline found", "resume")
        print(f"Pipeline already complete: {pipeline_md}")
        print(f"Status: {status_json}")
        return 0

    if args.resume and progress_log.exists():
        with progress_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(timezone.utc).isoformat()} running resume resume requested\n")
    else:
        progress_log.write_text("", encoding="utf-8")
    if done_md.exists() and not args.resume:
        done_md.unlink()
    if failed_md.exists():
        failed_md.unlink()
    update_status("running", "init", "pipeline initialized", "init")

    scan_base = [
        sys.executable,
        str(skill_scripts / "scan_user_facing_text.py"),
        str(repo),
        "--profile",
        args.profile,
        "--classes",
        *args.classes,
    ]
    if args.surfaces:
        scan_base.extend(["--surfaces", *args.surfaces])
    if args.include_tests:
        scan_base.append("--include-tests")
    if args.include_ci:
        scan_base.append("--include-ci")
    if args.include_docs:
        scan_base.append("--include-docs")

    require_ok(call_or_resume("scan-json", [*scan_base, "--format", "json", "--out", str(scan_json)], [scan_json]))
    counts["scan_candidates"] = maybe_count(scan_json)
    artifacts["scan_json"] = str(scan_json)
    require_ok(call_or_resume("scan-markdown", [*scan_base, "--format", "markdown", "--out", str(scan_md)], [scan_md]))
    artifacts["scan_markdown"] = str(scan_md)

    baseline = args.baseline if args.baseline.is_absolute() else repo / args.baseline
    plan_input = scan_json
    if baseline.exists():
        require_ok(
            call_or_resume(
                "diff-baseline",
                [
                    sys.executable,
                    str(skill_scripts / "diff_localization_scan.py"),
                    "--baseline",
                    str(baseline),
                    "--scan",
                    str(scan_json),
                    "--out",
                    str(delta_json),
                    "--summary",
                    str(delta_md),
                ],
                [delta_json, delta_md],
            )
        )
        plan_input = delta_json
        artifacts["delta_json"] = str(delta_json)

    update_report = write_version_update_report(
        version_report_json,
        version_report_md,
        repo=repo,
        target_locale=args.target_locale,
        baseline=baseline,
        scan_json=scan_json,
        delta_json=delta_json,
    )
    artifacts["version_update_report_json"] = str(version_report_json)
    counts["version_update_actionable"] = int(update_report.get("actionable_candidates", 0))

    patch_cmd = [
        sys.executable,
        str(skill_scripts / "generate_patch_plan.py"),
        "--input",
        str(plan_input),
        "--language",
        args.target_locale,
        "--out",
        str(patch_plan_json),
        "--markdown",
        str(patch_plan_md),
        "--include-review",
    ]
    memory = args.translation_memory if args.translation_memory.is_absolute() else repo / args.translation_memory
    if memory.exists():
        patch_cmd.extend(["--translation-memory", str(memory)])
    require_ok(call_or_resume("patch-plan", patch_cmd, [patch_plan_json, patch_plan_md]))
    artifacts["patch_plan_json"] = str(patch_plan_json)
    counts["patch_plan_items"] = maybe_count(patch_plan_json)

    translation_source = patch_plan_json
    if args.mode in {"i18n-key-migration", "both"}:
        migration_cmd = [
            sys.executable,
            str(skill_scripts / "generate_i18n_migration_plan.py"),
            "--input",
            str(patch_plan_json),
            "--namespace",
            "auto",
            "--source-locale",
            args.source_locale,
            "--target-locale",
            args.target_locale,
            "--out",
            str(migration_json),
            "--markdown",
            str(migration_md),
        ]
        if memory.exists():
            migration_cmd.extend(["--translation-memory", str(memory)])
        require_ok(call_or_resume("i18n-migration-plan", migration_cmd, [migration_json, migration_md]))
        translation_source = migration_json
        artifacts["i18n_migration_plan_json"] = str(migration_json)
        counts["migration_items"] = maybe_count(migration_json)

    glossary = locale_glossary(skill_root, args.target_locale)
    request_cmd = [
        sys.executable,
        str(skill_scripts / "export_translation_request.py"),
        "--input",
        str(translation_source),
        "--target-language",
        target_language,
        "--target-locale",
        args.target_locale,
        "--out",
        str(translation_request_json),
        "--prompt-out",
        str(translation_request_md),
    ]
    if glossary:
        request_cmd.extend(["--glossary", str(glossary)])
    require_ok(call_or_resume("translation-request", request_cmd, [translation_request_json, translation_request_md]))
    artifacts["translation_request_json"] = str(translation_request_json)
    counts["translation_request_items"] = maybe_count(translation_request_json, "items")

    if not args.no_translation_batches:
        split_cmd = [
            sys.executable,
            str(skill_scripts / "split_translation_request.py"),
            "--input",
            str(translation_request_json),
            "--out-dir",
            str(batches_dir),
            "--batch-size",
            str(args.translation_batch_size),
            "--max-chars",
            str(args.translation_batch_max_chars),
        ]
        if not args.resume or args.force:
            split_cmd.append("--overwrite")
        require_ok(call_or_resume("translation-batches", split_cmd, [batches_dir / "status.json"]))
        artifacts["translation_batches_status"] = str(batches_dir / "status.json")
        batch_status = load_json(batches_dir / "status.json")
        counts["translation_batch_count"] = int(batch_status.get("batch_count", 0)) if isinstance(batch_status, dict) else None
        queue_cmd = [
            sys.executable,
            str(skill_scripts / "manage_translation_batches.py"),
            "--batches-dir",
            str(batches_dir),
            "--next",
            str(args.translation_concurrency),
            "--retry-failed",
            "--out",
            str(batch_queue_json),
            "--markdown",
            str(batch_queue_md),
        ]
        require_ok(call("translation-batch-queue", queue_cmd))
        artifacts["translation_batch_queue_json"] = str(batch_queue_json)

    locales_dir = args.locales_dir if args.locales_dir.is_absolute() else repo / args.locales_dir
    if locales_dir.exists() and not args.skip_consistency:
        require_ok(
            call_or_resume(
                "i18n-consistency-json",
                [
                    sys.executable,
                    str(skill_scripts / "check_i18n_consistency.py"),
                    "--locales-dir",
                    str(locales_dir),
                    "--source-locale",
                    args.source_locale,
                    "--format",
                    "json",
                    "--out",
                    str(consistency_json),
                ],
                [consistency_json],
            )
        )
        artifacts["consistency_json"] = str(consistency_json)
        require_ok(
            call_or_resume(
                "i18n-consistency-markdown",
                [
                    sys.executable,
                    str(skill_scripts / "check_i18n_consistency.py"),
                    "--locales-dir",
                    str(locales_dir),
                    "--source-locale",
                    args.source_locale,
                    "--format",
                    "markdown",
                    "--out",
                    str(consistency_md),
                ],
                [consistency_md],
            )
        )
        if args.autofix_locales:
            fix_cmd = [
                sys.executable,
                str(skill_scripts / "apply_locale_consistency_fixes.py"),
                "--locales-dir",
                str(locales_dir),
                "--source-locale",
                args.source_locale,
                "--fill",
                "source",
                "--out",
                str(locale_fix_json),
                "--markdown",
                str(locale_fix_md),
            ]
            if args.apply:
                fix_cmd.append("--apply")
            locale_outputs = [locale_fix_json, locale_fix_md]
            require_ok(call_or_resume("locale-consistency-fixes", fix_cmd, locale_outputs))
            artifacts["locale_fix_json"] = str(locale_fix_json)

    report = {
        "schema": "zero-zero-three.localization-pipeline-report",
        "repo": str(repo),
        "target_locale": args.target_locale,
        "target_language": target_language,
        "mode": args.mode,
        "out_dir": str(out_dir),
        "applied": bool(args.apply),
        "artifacts": {
            "scan_json": str(scan_json),
            "scan_markdown": str(scan_md),
            "delta_json": str(delta_json) if delta_json.exists() else None,
            "patch_plan_json": str(patch_plan_json),
            "version_update_report_json": str(version_report_json),
            "i18n_migration_plan_json": str(migration_json) if migration_json.exists() else None,
            "translation_request_json": str(translation_request_json),
            "translation_batches_status": str(batches_dir / "status.json") if (batches_dir / "status.json").exists() else None,
            "translation_batch_queue_json": str(batch_queue_json) if batch_queue_json.exists() else None,
            "consistency_json": str(consistency_json) if consistency_json.exists() else None,
            "locale_fix_json": str(locale_fix_json) if locale_fix_json.exists() else None,
        },
        "counts": {
            "scan_candidates": maybe_count(scan_json),
            "patch_plan_items": maybe_count(patch_plan_json),
            "migration_items": maybe_count(migration_json),
            "translation_request_items": maybe_count(translation_request_json, "items"),
            "translation_batch_count": counts.get("translation_batch_count"),
            "version_update_actionable": counts.get("version_update_actionable"),
        },
        "steps": steps,
    }
    pipeline_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary(pipeline_md, report)
    done_md.write_text(
        "\n".join(
            [
                "# Localization Pipeline Complete",
                "",
                f"- Report: `{pipeline_md}`",
                f"- Status: `{status_json}`",
                f"- Translation batches: `{batches_dir}`" if (batches_dir / "status.json").exists() else "- Translation batches: not generated",
                "",
            ]
        ),
        encoding="utf-8",
    )
    update_status("complete", "done", "pipeline completed", "done")
    print(f"Pipeline report: {pipeline_md}")
    print(f"Status: {status_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
