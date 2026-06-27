#!/usr/bin/env python3
"""Print localization workflow status from artifact files."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def count_batches(batch_status: dict[str, Any] | None, state: str) -> int:
    if not isinstance(batch_status, dict):
        return 0
    value = batch_status.get(state)
    if isinstance(value, int):
        return value
    return 0


def percent(done: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(done * 100 / total)}%"


def build_report(work_dir: Path) -> dict[str, Any]:
    pipeline = load_json(work_dir / "status.json")
    batch_status = load_json(work_dir / "batches" / "status.json")
    apply_report = load_json(work_dir / "apply-report.json")
    version_report = load_json(work_dir / "version-update-report.json")
    done = (work_dir / "DONE.md").exists()
    failed = (work_dir / "FAILED.md").exists()
    return {
        "schema": "zero-zero-three.localization-status",
        "work_dir": str(work_dir),
        "pipeline": pipeline,
        "translation_batches": batch_status,
        "apply_report": apply_report,
        "version_update_report": version_report,
        "done": done,
        "failed": failed,
    }


def print_dashboard(report: dict[str, Any]) -> None:
    work_dir = report["work_dir"]
    pipeline = report.get("pipeline") if isinstance(report.get("pipeline"), dict) else None
    batch_status = report.get("translation_batches") if isinstance(report.get("translation_batches"), dict) else None
    apply_report = report.get("apply_report") if isinstance(report.get("apply_report"), dict) else None
    version_report = report.get("version_update_report") if isinstance(report.get("version_update_report"), dict) else None

    print(f"Work dir: {work_dir}")
    if pipeline:
        steps = pipeline.get("steps") if isinstance(pipeline.get("steps"), list) else []
        passed = sum(1 for step in steps if isinstance(step, dict) and step.get("returncode") == 0)
        failed_steps = sum(1 for step in steps if isinstance(step, dict) and step.get("returncode") not in (0, None))
        print(f"Pipeline: {pipeline.get('state')} | phase: {pipeline.get('phase')} | step: {pipeline.get('step')}")
        print(f"Target: {pipeline.get('target_locale')} | mode: {pipeline.get('mode')} | resume: {pipeline.get('resume')}")
        print(f"Steps: {passed} passed/skipped, {failed_steps} failed")
        if pipeline.get("message"):
            print(f"Message: {pipeline.get('message')}")
        if pipeline.get("updated_at"):
            print(f"Updated: {pipeline.get('updated_at')}")
    else:
        print("Pipeline: no status.json")

    if version_report:
        counts = version_report.get("counts") if isinstance(version_report.get("counts"), dict) else {}
        print(
            "Update: mode={mode}, actionable={actionable}, new={new}, changed={changed}, moved={moved}, removed={removed}".format(
                mode=version_report.get("mode"),
                actionable=version_report.get("actionable_candidates", 0),
                new=counts.get("new_candidates", 0),
                changed=counts.get("changed_candidates", 0),
                moved=counts.get("moved_candidates", 0),
                removed=counts.get("removed_candidates", 0),
            )
        )
    else:
        print("Update: no version-update-report.json")

    if batch_status:
        total = int(batch_status.get("batch_count", 0) or 0)
        done = int(batch_status.get("completed_batches", 0) or 0)
        failed = int(batch_status.get("failed_batches", 0) or 0)
        pending = int(batch_status.get("pending_batches", 0) or 0)
        print(f"Batches: {done}/{total} complete ({percent(done, total)}), {pending} pending, {failed} failed")
        next_pending = []
        for entry in batch_status.get("batches", []) or []:
            if isinstance(entry, dict) and entry.get("state") in {None, "pending", "ready"}:
                result = Path(str(entry.get("result", "")))
                if not result.exists():
                    next_pending.append(str(entry.get("id", "")))
            if len(next_pending) >= 5:
                break
        if next_pending:
            print(f"Next batches: {', '.join(next_pending)}")
        next_step = batch_status.get("next_step")
        if next_step:
            print(f"Next: {next_step}")
    else:
        print("Batches: no batch status")

    if apply_report:
        summary = apply_report.get("summary") if isinstance(apply_report.get("summary"), dict) else {}
        skipped = sum(int(v) for k, v in summary.items() if k != "applied" and isinstance(v, int))
        print(
            f"Apply: applied={summary.get('applied', 0)}, skipped={skipped}, changed_files={len(apply_report.get('changed_files', []) or [])}"
        )
        if apply_report.get("rollback_patch"):
            print(f"Rollback: {apply_report.get('rollback_patch')}")
    else:
        print("Apply: no apply-report.json")

    if report["done"]:
        print("Completion marker: DONE.md")
    if report["failed"]:
        print("Failure marker: FAILED.md")


def main() -> int:
    parser = argparse.ArgumentParser(description="Show localization-work progress.")
    parser.add_argument("--work-dir", type=Path, default=Path("localization-work"))
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--watch", type=float, default=0, help="Refresh every N seconds until DONE.md or FAILED.md exists")
    args = parser.parse_args()

    work_dir = args.work_dir.resolve()
    report = build_report(work_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print_dashboard(report)
    while args.watch > 0 and not report["done"] and not report["failed"]:
        time.sleep(args.watch)
        print("")
        report = build_report(work_dir)
        print_dashboard(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
