#!/usr/bin/env python3
"""Merge validated translation batch results into one result artifact."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def translations_from_response(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        value = data.get("translations") or data.get("items") or data.get("results")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge translation batch result files.")
    parser.add_argument("--batches-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--require-validation", action="store_true")
    parser.add_argument("--update-status", action="store_true")
    args = parser.parse_args()

    batches_dir = args.batches_dir.resolve()
    status_path = batches_dir / "status.json"
    status = load_json(status_path) if status_path.exists() else {"batches": []}
    batch_entries = [entry for entry in status.get("batches", []) if isinstance(entry, dict)]
    if not batch_entries:
        batch_entries = [
            {
                "id": path.name.removesuffix(".request.json"),
                "request": str(path),
                "result": str(path.with_name(path.name.replace(".request.json", ".result.json"))),
                "validation": str(path.with_name(path.name.replace(".request.json", ".validation.json"))),
            }
            for path in sorted(batches_dir.glob("batch-*.request.json"))
        ]

    merged: list[dict[str, Any]] = []
    batch_summaries: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    for entry in batch_entries:
        result_path = Path(str(entry.get("result", "")))
        validation_path = Path(str(entry.get("validation", "")))
        batch_id = str(entry.get("id", result_path.stem))
        if not result_path.exists():
            states["pending"] += 1
            batch_summaries.append({"id": batch_id, "state": "pending", "reason": "missing result"})
            continue
        validation_status = "missing"
        if validation_path.exists():
            validation = load_json(validation_path)
            validation_status = str(validation.get("status", "unknown"))
        elif args.require_validation:
            states["failed"] += 1
            batch_summaries.append({"id": batch_id, "state": "failed", "reason": "missing validation"})
            continue
        response = load_json(result_path)
        translations = translations_from_response(response)
        state = "validated" if validation_status == "pass" else ("warning" if validation_status == "warn" else "done")
        states[state] += 1
        merged.extend(translations)
        batch_summaries.append(
            {
                "id": batch_id,
                "state": state,
                "result": str(result_path),
                "validation": str(validation_path) if validation_path.exists() else None,
                "validation_status": validation_status,
                "item_count": len(translations),
            }
        )

    output = {
        "schema": "zero-zero-three.merged-translation-results",
        "created_at": now(),
        "batches_dir": str(batches_dir),
        "summary": {
            "batch_count": len(batch_entries),
            "translation_count": len(merged),
            "counts_by_batch_state": dict(sorted(states.items())),
        },
        "batches": batch_summaries,
        "translations": merged,
    }
    write_json(args.out, output)

    if args.update_status and status_path.exists():
        status["updated_at"] = now()
        status["completed_batches"] = states.get("validated", 0) + states.get("warning", 0) + states.get("done", 0)
        status["failed_batches"] = states.get("failed", 0)
        status["pending_batches"] = states.get("pending", 0)
        status["state"] = "complete" if status["pending_batches"] == 0 and status["failed_batches"] == 0 else "running"
        status["merged_results"] = str(args.out.resolve())
        write_json(status_path, status)

    print(f"Merged {len(merged)} translation(s) from {len(batch_entries)} batch(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
