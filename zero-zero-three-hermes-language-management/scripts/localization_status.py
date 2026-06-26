#!/usr/bin/env python3
"""Print localization workflow status from artifact files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Show localization-work progress.")
    parser.add_argument("--work-dir", type=Path, default=Path("localization-work"))
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    work_dir = args.work_dir.resolve()
    pipeline = load_json(work_dir / "status.json")
    batch_status = load_json(work_dir / "batches" / "status.json")
    report = {
        "schema": "zero-zero-three.localization-status",
        "work_dir": str(work_dir),
        "pipeline": pipeline,
        "translation_batches": batch_status,
        "done": (work_dir / "DONE.md").exists(),
        "failed": (work_dir / "FAILED.md").exists(),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"Work dir: {work_dir}")
    if pipeline:
        print(f"Pipeline: {pipeline.get('state')} | phase: {pipeline.get('phase')} | step: {pipeline.get('step')}")
        if pipeline.get("message"):
            print(f"Message: {pipeline.get('message')}")
        if pipeline.get("updated_at"):
            print(f"Updated: {pipeline.get('updated_at')}")
    else:
        print("Pipeline: no status.json")
    if batch_status:
        total = batch_status.get("batch_count", 0)
        done = batch_status.get("completed_batches", 0)
        failed = batch_status.get("failed_batches", 0)
        pending = batch_status.get("pending_batches", 0)
        print(f"Batches: {done}/{total} complete, {pending} pending, {failed} failed")
        next_step = batch_status.get("next_step")
        if next_step:
            print(f"Next: {next_step}")
    else:
        print("Batches: no batch status")
    if report["done"]:
        print("Completion marker: DONE.md")
    if report["failed"]:
        print("Failure marker: FAILED.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
