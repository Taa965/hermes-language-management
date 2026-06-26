#!/usr/bin/env python3
"""Split a large translation request into resumable batch request files."""

from __future__ import annotations

import argparse
import json
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


def estimate_chars(item: dict[str, Any]) -> int:
    return len(json.dumps(item, ensure_ascii=False))


def chunk_items(items: list[dict[str, Any]], batch_size: int, max_chars: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for item in items:
        item_chars = estimate_chars(item)
        would_exceed_count = len(current) >= batch_size
        would_exceed_chars = current and current_chars + item_chars > max_chars
        if would_exceed_count or would_exceed_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_chars
    if current:
        batches.append(current)
    return batches


def build_batch_request(source: dict[str, Any], batch_id: str, index: int, count: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "zero-zero-three.translation-batch-request",
        "batch_id": batch_id,
        "batch_index": index,
        "batch_count": count,
        "source_language": source.get("source_language"),
        "target_language": source.get("target_language"),
        "target_locale": source.get("target_locale"),
        "instructions": [
            "Return JSON only.",
            "Return one translation per input item.",
            "Preserve every token in preserve_tokens exactly.",
            "Keep placeholders with the same spelling and count.",
            "If an item is unsafe or model-facing, return skip=true with a short reason.",
            "Do not include commentary, markdown, or repeated source items in the response.",
        ],
        "response_schema": source.get("response_schema"),
        "glossary": source.get("glossary"),
        "items": items,
    }


def write_prompt(path: Path, batch_request: dict[str, Any]) -> None:
    prompt = "\n".join(
        [
            "# Translation Batch",
            "",
            f"Batch: {batch_request['batch_id']} ({batch_request['batch_index'] + 1}/{batch_request['batch_count']})",
            f"Target: {batch_request.get('target_language')} ({batch_request.get('target_locale')})",
            "",
            "Translate the JSON request below. Return JSON only, matching `response_schema`.",
            "",
            "```json",
            json.dumps(batch_request, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    path.write_text(prompt + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a translation request into smaller resumable batches.")
    parser.add_argument("--input", required=True, type=Path, help="translation-request.json")
    parser.add_argument("--out-dir", required=True, type=Path, help="Output batches directory")
    parser.add_argument("--batch-size", type=int, default=40, help="Maximum items per batch")
    parser.add_argument("--max-chars", type=int, default=12000, help="Approximate maximum JSON chars per batch")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing batch request files")
    args = parser.parse_args()

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    if args.max_chars < 1000:
        raise SystemExit("--max-chars must be >= 1000")

    source = load_json(args.input)
    if not isinstance(source, dict) or not isinstance(source.get("items"), list):
        raise SystemExit("input must be a translation request object with an items list")

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    items = [item for item in source["items"] if isinstance(item, dict)]
    batches = chunk_items(items, args.batch_size, args.max_chars)
    batch_entries: list[dict[str, Any]] = []

    for index, batch_items in enumerate(batches):
        batch_id = f"batch-{index:03d}"
        request_path = out_dir / f"{batch_id}.request.json"
        prompt_path = out_dir / f"{batch_id}.prompt.md"
        result_path = out_dir / f"{batch_id}.result.json"
        validation_path = out_dir / f"{batch_id}.validation.json"
        if request_path.exists() and not args.overwrite:
            raise SystemExit(f"Refusing to overwrite existing batch: {request_path}")
        batch_request = build_batch_request(source, batch_id, index, len(batches), batch_items)
        write_json(request_path, batch_request)
        write_prompt(prompt_path, batch_request)
        batch_entries.append(
            {
                "id": batch_id,
                "state": "pending",
                "item_count": len(batch_items),
                "request": str(request_path),
                "prompt": str(prompt_path),
                "result": str(result_path),
                "validation": str(validation_path),
                "created_at": now(),
            }
        )

    status = {
        "schema": "zero-zero-three.translation-batch-status",
        "state": "ready",
        "source_request": str(args.input.resolve()),
        "created_at": now(),
        "updated_at": now(),
        "total_items": len(items),
        "batch_count": len(batches),
        "batch_size": args.batch_size,
        "max_chars": args.max_chars,
        "completed_batches": 0,
        "failed_batches": 0,
        "pending_batches": len(batches),
        "batches": batch_entries,
        "next_step": "Translate each batch request and write batch-XXX.result.json, then run validate_translation_response.py.",
    }
    write_json(out_dir / "status.json", status)
    (out_dir / "progress.log").write_text(
        f"{now()} created {len(batches)} batch(es) from {len(items)} item(s)\n",
        encoding="utf-8",
    )
    print(f"Created {len(batches)} batch(es) in {out_dir}")
    print(f"Status: {out_dir / 'status.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
