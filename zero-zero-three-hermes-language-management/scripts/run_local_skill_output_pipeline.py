#!/usr/bin/env python3
"""Create translation batches for local skill output localization."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_localization_pipeline import default_target_language, locale_glossary


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_step(name: str, command: list[str], cwd: Path) -> dict[str, Any]:
    started = now()
    proc = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True)
    step = {
        "name": name,
        "command": command,
        "returncode": proc.returncode,
        "started_at": started,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }
    if proc.returncode != 0:
        raise RuntimeError(f"{name} failed: {proc.stderr or proc.stdout}")
    return step


def maybe_count(path: Path, key: str | None = None) -> int | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return len(data)
    if key and isinstance(data, dict) and isinstance(data.get(key), list):
        return len(data[key])
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return len(data["items"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local skill output localization artifact pipeline.")
    parser.add_argument("--skill-root", type=Path, default=Path.home() / ".hermes" / "skills")
    parser.add_argument("--target-locale", default="zh-CN")
    parser.add_argument("--target-language")
    parser.add_argument("--out-dir", type=Path, default=Path("local-skill-language-work"))
    parser.add_argument("--include-current", action="store_true")
    parser.add_argument("--include-skill-description", action="store_true")
    parser.add_argument("--include-references", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--translation-batch-size", type=int, default=40)
    parser.add_argument("--translation-batch-max-chars", type=int, default=12000)
    args = parser.parse_args()

    skill_root = args.skill_root.expanduser().resolve()
    out_dir = args.out_dir.resolve()
    scripts = script_dir()
    skill_root_dir = scripts.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    target_language = args.target_language or default_target_language(args.target_locale)

    scan_json = out_dir / "skill-output-scan.json"
    scan_md = out_dir / "skill-output-scan.md"
    patch_plan_json = out_dir / "skill-output-patch-plan.json"
    patch_plan_md = out_dir / "skill-output-patch-plan.md"
    request_json = out_dir / "translation-request.json"
    request_md = out_dir / "translation-request.md"
    batches_dir = out_dir / "batches"
    status_json = out_dir / "status.json"
    report_json = out_dir / "pipeline-report.json"
    report_md = out_dir / "pipeline-report.md"
    done_md = out_dir / "DONE.md"

    steps: list[dict[str, Any]] = []

    def update_status(state: str, phase: str, message: str) -> None:
        write_json(
            status_json,
            {
                "schema": "zero-zero-three.local-skill-output-status",
                "state": state,
                "phase": phase,
                "message": message,
                "skill_root": str(skill_root),
                "target_locale": args.target_locale,
                "target_language": target_language,
                "out_dir": str(out_dir),
                "updated_at": now(),
                "steps": steps,
                "counts": {
                    "scan_candidates": maybe_count(scan_json),
                    "patch_plan_items": maybe_count(patch_plan_json),
                    "translation_request_items": maybe_count(request_json, "items"),
                },
            },
        )

    def call(name: str, command: list[str], outputs: list[Path]) -> None:
        if args.resume and not args.force and outputs and all(path.exists() for path in outputs):
            steps.append({"name": name, "command": command, "returncode": 0, "started_at": now(), "skipped": True})
            update_status("running", name, f"{name} skipped; resume artifacts already exist")
            return
        update_status("running", name, f"{name} started")
        steps.append(run_step(name, command, skill_root))
        update_status("running", name, f"{name} completed")

    if args.resume and done_md.exists() and report_json.exists() and not args.force:
        update_status("complete", "resume", "existing completed local skill output pipeline found")
        print(f"Pipeline already complete: {report_md}")
        return 0

    scan_base = [
        sys.executable,
        str(scripts / "scan_local_skill_outputs.py"),
        "--skill-root",
        str(skill_root),
        "--classes",
        "translate",
        "mixed-preserve",
        "review",
    ]
    if args.include_current:
        scan_base.append("--include-current")
    if args.include_skill_description:
        scan_base.append("--include-skill-description")
    if args.include_references:
        scan_base.append("--include-references")

    call("scan-json", [*scan_base, "--format", "json", "--out", str(scan_json)], [scan_json])
    call("scan-markdown", [*scan_base, "--format", "markdown", "--out", str(scan_md)], [scan_md])
    call(
        "patch-plan",
        [
            sys.executable,
            str(scripts / "generate_patch_plan.py"),
            "--input",
            str(scan_json),
            "--language",
            args.target_locale,
            "--out",
            str(patch_plan_json),
            "--markdown",
            str(patch_plan_md),
            "--include-review",
        ],
        [patch_plan_json, patch_plan_md],
    )

    request_cmd = [
        sys.executable,
        str(scripts / "export_translation_request.py"),
        "--input",
        str(patch_plan_json),
        "--target-language",
        target_language,
        "--target-locale",
        args.target_locale,
        "--out",
        str(request_json),
        "--prompt-out",
        str(request_md),
    ]
    glossary = locale_glossary(skill_root_dir, args.target_locale)
    if glossary:
        request_cmd.extend(["--glossary", str(glossary)])
    call("translation-request", request_cmd, [request_json, request_md])

    split_cmd = [
        sys.executable,
        str(scripts / "split_translation_request.py"),
        "--input",
        str(request_json),
        "--out-dir",
        str(batches_dir),
        "--batch-size",
        str(args.translation_batch_size),
        "--max-chars",
        str(args.translation_batch_max_chars),
    ]
    if not args.resume or args.force:
        split_cmd.append("--overwrite")
    call("translation-batches", split_cmd, [batches_dir / "status.json"])

    report = {
        "schema": "zero-zero-three.local-skill-output-pipeline-report",
        "created_at": now(),
        "skill_root": str(skill_root),
        "target_locale": args.target_locale,
        "target_language": target_language,
        "out_dir": str(out_dir),
        "artifacts": {
            "scan_json": str(scan_json),
            "scan_markdown": str(scan_md),
            "patch_plan_json": str(patch_plan_json),
            "translation_request_json": str(request_json),
            "translation_batches_status": str(batches_dir / "status.json"),
        },
        "counts": {
            "scan_candidates": maybe_count(scan_json),
            "patch_plan_items": maybe_count(patch_plan_json),
            "translation_request_items": maybe_count(request_json, "items"),
        },
        "steps": steps,
    }
    write_json(report_json, report)
    report_md.write_text(
        "\n".join(
            [
                "# Local Skill Output Localization Pipeline",
                "",
                f"- Skill root: `{skill_root}`",
                f"- Target locale: `{args.target_locale}`",
                f"- Scan candidates: {report['counts']['scan_candidates']}",
                f"- Translation request items: {report['counts']['translation_request_items']}",
                f"- Batches: `{batches_dir}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    done_md.write_text(f"# Complete\n\nReport: `{report_md}`\n", encoding="utf-8")
    update_status("complete", "done", "local skill output pipeline completed")
    print(f"Pipeline report: {report_md}")
    print(f"Status: {status_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
