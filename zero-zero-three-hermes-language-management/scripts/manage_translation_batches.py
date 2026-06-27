#!/usr/bin/env python3
"""Validate, retry, and schedule translation batches."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from split_translation_request import build_batch_request, chunk_items, estimate_chars, write_json, write_prompt


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def status_path_for(batches_dir: Path) -> Path:
    return batches_dir / "status.json"


def default_path(batches_dir: Path, batch_id: str, suffix: str) -> Path:
    return batches_dir / f"{batch_id}.{suffix}"


def entry_path(batches_dir: Path, entry: dict[str, Any], field: str, suffix: str) -> Path:
    value = entry.get(field)
    if value:
        return Path(str(value))
    return default_path(batches_dir, str(entry.get("id")), suffix)


def append_log(batches_dir: Path, message: str) -> None:
    with (batches_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now()} {message}\n")


def validation_is_stale(request: Path, result: Path, validation: Path) -> bool:
    if not validation.exists():
        return True
    return validation.stat().st_mtime < max(request.stat().st_mtime, result.stat().st_mtime)


def run_validation(request: Path, result: Path, validation: Path, fail_on: str) -> dict[str, Any] | None:
    script = Path(__file__).resolve().parent / "validate_translation_response.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--request",
            str(request),
            "--response",
            str(result),
            "--out",
            str(validation),
            "--fail-on",
            fail_on,
        ],
        text=True,
        capture_output=True,
    )
    if validation.exists():
        report = load_json(validation)
        report["_validator_returncode"] = proc.returncode
        report["_validator_stdout"] = proc.stdout.strip()
        report["_validator_stderr"] = proc.stderr.strip()
        return report
    return {
        "status": "fail",
        "_validator_returncode": proc.returncode,
        "_validator_stdout": proc.stdout.strip(),
        "_validator_stderr": proc.stderr.strip(),
    }


def retry_prefix(batch_id: str, retry_count: int) -> str:
    return f"{batch_id}-r{retry_count}"


def has_retry_children(status: dict[str, Any], batch_id: str) -> bool:
    for entry in status.get("batches", []) or []:
        if isinstance(entry, dict) and entry.get("retry_of") == batch_id:
            return True
    return False


def create_retry_batches(
    status: dict[str, Any],
    batches_dir: Path,
    entry: dict[str, Any],
    retry_batch_size: int,
    retry_max_chars: int,
    max_retries: int,
) -> list[dict[str, Any]]:
    batch_id = str(entry.get("id"))
    retry_count = int(entry.get("retry_count") or 0) + 1
    if retry_count > max_retries:
        return []
    if has_retry_children(status, batch_id):
        return []

    request_path = entry_path(batches_dir, entry, "request", "request.json")
    if not request_path.exists():
        return []
    request = load_json(request_path)
    items = [item for item in request.get("items", []) if isinstance(item, dict)]
    if not items:
        return []

    chunks = chunk_items(items, max(1, retry_batch_size), max(1000, retry_max_chars))
    created: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        child_id = f"{retry_prefix(batch_id, retry_count)}-{index:03d}"
        child_request = build_batch_request(request, child_id, index, len(chunks), chunk)
        child_request["retry_of"] = batch_id
        child_request["retry_count"] = retry_count
        request_out = default_path(batches_dir, child_id, "request.json")
        prompt_out = default_path(batches_dir, child_id, "prompt.md")
        result_out = default_path(batches_dir, child_id, "result.json")
        validation_out = default_path(batches_dir, child_id, "validation.json")
        if request_out.exists():
            continue
        write_json(request_out, child_request)
        write_prompt(prompt_out, child_request)
        child_entry = {
            "id": child_id,
            "state": "pending",
            "retry_of": batch_id,
            "retry_count": retry_count,
            "item_count": len(chunk),
            "estimated_chars": sum(estimate_chars(item) for item in chunk),
            "request": str(request_out),
            "prompt": str(prompt_out),
            "result": str(result_out),
            "validation": str(validation_out),
            "created_at": now(),
        }
        created.append(child_entry)
    return created


def refresh_status(
    batches_dir: Path,
    status: dict[str, Any],
    validate: bool,
    retry_failed: bool,
    max_retries: int,
    retry_batch_size: int,
    retry_max_chars: int,
    fail_on: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entries = [entry for entry in status.get("batches", []) if isinstance(entry, dict)]
    created_retries: list[dict[str, Any]] = []

    for entry in entries:
        batch_id = str(entry.get("id"))
        request_path = entry_path(batches_dir, entry, "request", "request.json")
        result_path = entry_path(batches_dir, entry, "result", "result.json")
        validation_path = entry_path(batches_dir, entry, "validation", "validation.json")
        entry["request"] = str(request_path)
        entry["result"] = str(result_path)
        entry["validation"] = str(validation_path)

        if not request_path.exists():
            entry["state"] = "failed"
            entry["reason"] = "missing request"
            continue
        if not result_path.exists():
            entry["state"] = "pending"
            entry["reason"] = "missing result"
            continue

        report: dict[str, Any] | None = None
        if validate and validation_is_stale(request_path, result_path, validation_path):
            report = run_validation(request_path, result_path, validation_path, fail_on)
        elif validation_path.exists():
            report = load_json(validation_path)
        else:
            entry["state"] = "failed"
            entry["reason"] = "missing validation"
            continue

        validation_status = str((report or {}).get("status") or "unknown")
        entry["validation_status"] = validation_status
        entry["validated_at"] = now()
        if validation_status == "pass":
            entry["state"] = "validated"
            entry["reason"] = ""
        elif validation_status == "warn":
            entry["state"] = "warning"
            entry["reason"] = "validation warnings"
        else:
            entry["state"] = "failed"
            entry["reason"] = f"validation {validation_status}"
            if retry_failed:
                children = create_retry_batches(
                    status,
                    batches_dir,
                    entry,
                    retry_batch_size=retry_batch_size,
                    retry_max_chars=retry_max_chars,
                    max_retries=max_retries,
                )
                if children:
                    entry["state"] = "retry-created"
                    entry["retry_children"] = [child["id"] for child in children]
                    entry["reason"] = "retry child batches created"
                    created_retries.extend(children)
                    append_log(batches_dir, f"created {len(children)} retry batch(es) for {batch_id}")

    if created_retries:
        entries.extend(created_retries)
    states = Counter(str(entry.get("state") or "unknown") for entry in entries)
    completed = states.get("validated", 0) + states.get("warning", 0) + states.get("done", 0)
    failed = states.get("failed", 0)
    pending = states.get("pending", 0)
    status["batches"] = entries
    status["updated_at"] = now()
    status["completed_batches"] = completed
    status["failed_batches"] = failed
    status["pending_batches"] = pending
    status["counts_by_state"] = dict(sorted(states.items()))
    status["state"] = "complete" if pending == 0 and failed == 0 else "running"
    return status, created_retries


def next_batches(status: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    pending = [entry for entry in status.get("batches", []) if isinstance(entry, dict) and entry.get("state") == "pending"]
    return pending[: max(0, limit)]


def write_markdown(path: Path, status: dict[str, Any], selected: list[dict[str, Any]], created: list[dict[str, Any]]) -> None:
    lines = [
        "# Translation Batch Queue",
        "",
        f"- State: `{status.get('state')}`",
        f"- Completed: {status.get('completed_batches', 0)}",
        f"- Failed: {status.get('failed_batches', 0)}",
        f"- Pending: {status.get('pending_batches', 0)}",
        f"- Retry batches created: {len(created)}",
        "",
        "## Next Batches",
        "",
    ]
    if selected:
        for entry in selected:
            lines.append(f"- `{entry.get('id')}`: `{entry.get('prompt')}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Counts By State", ""])
    for state, count in sorted((status.get("counts_by_state") or {}).items()):
        lines.append(f"- `{state}`: {count}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage translation batch validation, retry creation, and scheduling.")
    parser.add_argument("--batches-dir", required=True, type=Path)
    parser.add_argument("--next", type=int, default=3, help="Number of pending batches to select for the next fan-out")
    parser.add_argument("--no-validate", action="store_true", help="Do not run validation for existing result files")
    parser.add_argument("--retry-failed", action="store_true", help="Create smaller retry batches for failed batches")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-batch-size", type=int, default=10)
    parser.add_argument("--retry-max-chars", type=int, default=6000)
    parser.add_argument("--fail-on", choices=("never", "errors", "warnings"), default="errors")
    parser.add_argument("--out", type=Path, help="Optional JSON queue report")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown queue report")
    parser.add_argument("--json", action="store_true", help="Print JSON queue report")
    args = parser.parse_args()

    batches_dir = args.batches_dir.resolve()
    status_path = status_path_for(batches_dir)
    if not status_path.exists():
        raise SystemExit(f"Missing batch status: {status_path}")
    status = load_json(status_path)
    if not isinstance(status, dict):
        raise SystemExit("status.json must be a JSON object")

    status, created = refresh_status(
        batches_dir,
        status,
        validate=not args.no_validate,
        retry_failed=args.retry_failed,
        max_retries=max(0, args.max_retries),
        retry_batch_size=max(1, args.retry_batch_size),
        retry_max_chars=max(1000, args.retry_max_chars),
        fail_on=args.fail_on,
    )
    selected = next_batches(status, args.next)
    status["next_batches"] = selected
    status["next_step"] = (
        "Translate next_batches and write each batch result JSON, then rerun manage_translation_batches.py."
        if selected
        else "No pending batches. Merge results when all batches are validated or warning."
    )
    write_json(status_path, status)
    append_log(batches_dir, f"managed queue: {status.get('state')} pending={status.get('pending_batches')} failed={status.get('failed_batches')}")

    report = {
        "schema": "zero-zero-three.translation-batch-queue-report",
        "batches_dir": str(batches_dir),
        "state": status.get("state"),
        "created_retry_batches": created,
        "next_batches": selected,
        "summary": {
            "completed_batches": status.get("completed_batches", 0),
            "failed_batches": status.get("failed_batches", 0),
            "pending_batches": status.get("pending_batches", 0),
            "counts_by_state": status.get("counts_by_state", {}),
        },
    }
    if args.out:
        write_json(args.out, report)
    if args.markdown:
        write_markdown(args.markdown, status, selected, created)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Batch queue: {report['state']} | pending={report['summary']['pending_batches']} failed={report['summary']['failed_batches']}")
        if selected:
            print("Next: " + ", ".join(str(entry.get("id")) for entry in selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
