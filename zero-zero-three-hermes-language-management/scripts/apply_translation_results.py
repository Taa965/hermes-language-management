#!/usr/bin/env python3
"""Apply validated translation results to source files by exact-match replacement."""

from __future__ import annotations

import argparse
import difflib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RISK_RANK = {"low": 0, "medium": 1, "high": 2}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def translation_entries(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        value = data.get("translations") or data.get("items") or data.get("results")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def request_items(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        return {}
    items = data.get("items")
    if not isinstance(items, list):
        return {}
    return {str(item.get("id")): item for item in items if isinstance(item, dict) and item.get("id") is not None}


def item_context(item: dict[str, Any]) -> dict[str, Any]:
    context = item.get("context")
    return context if isinstance(context, dict) else {}


def item_path(item: dict[str, Any]) -> str:
    context = item_context(item)
    return str(context.get("path") or item.get("path") or "")


def item_line(item: dict[str, Any]) -> int:
    context = item_context(item)
    raw = context.get("line") or item.get("line") or 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def item_risk(item: dict[str, Any]) -> str:
    context = item_context(item)
    risk = str(context.get("risk") or item.get("risk") or "medium")
    return risk if risk in RISK_RANK else "medium"


def item_source_text(item: dict[str, Any]) -> str:
    return str(item.get("source_text") or item.get("text") or "")


def translated_text(entry: dict[str, Any]) -> str:
    return str(entry.get("translated_text") or entry.get("translation") or "")


def resolve_repo_path(repo: Path, rel_path: str) -> Path | None:
    if not rel_path:
        return None
    rel = Path(rel_path)
    if not rel.is_absolute():
        rel = repo.joinpath(*rel_path.replace("\\", "/").split("/"))
    try:
        resolved = rel.resolve()
        resolved.relative_to(repo)
    except (OSError, ValueError):
        return None
    return resolved


def replace_exact(text: str, source: str, target: str, line: int) -> tuple[str, str]:
    if not source.strip():
        return text, "empty-source"
    if not target.strip():
        return text, "empty-translation"
    if source == target:
        return text, "unchanged"

    count = text.count(source)
    if count == 1:
        return text.replace(source, target, 1), "applied"
    if count == 0:
        return text, "source-not-found"

    if line > 0:
        lines = text.splitlines(keepends=True)
        index = line - 1
        if 0 <= index < len(lines) and lines[index].count(source) == 1:
            lines[index] = lines[index].replace(source, target, 1)
            return "".join(lines), "applied"
    return text, "ambiguous-source"


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Translation Apply Report",
        "",
        f"- Applied mode: `{report['applied']}`",
        f"- Max risk: `{report['max_risk']}`",
        f"- Changed files: {len(report.get('changed_files', []))}",
        f"- Rollback patch: `{report.get('rollback_patch') or ''}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in sorted(report.get("summary", {}).items()):
        lines.append(f"- `{key}`: {value}")
    skipped = [item for item in report.get("items", []) if item.get("status") != "applied"]
    if skipped:
        lines.extend(["", "## Skipped Items", "", "| Status | File | Line | Reason |", "|---|---|---:|---|"])
        for item in skipped:
            lines.append(
                "| `{}` | `{}` | {} | {} |".format(
                    item.get("status"),
                    item.get("path"),
                    item.get("line") or 0,
                    str(item.get("reason") or "").replace("|", "\\|"),
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_rollback_patch(
    path: Path,
    repo: Path,
    original_texts: dict[Path, str],
    current_texts: dict[Path, str],
    changed_files: list[Path],
) -> None:
    chunks: list[str] = []
    for file_path in changed_files:
        rel = file_path.relative_to(repo).as_posix()
        before_apply = current_texts[file_path].splitlines(keepends=True)
        after_rollback = original_texts[file_path].splitlines(keepends=True)
        chunks.append(f"diff --git a/{rel} b/{rel}\n")
        chunks.extend(
            difflib.unified_diff(
                before_apply,
                after_rollback,
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                lineterm="\n",
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(chunks), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply validated translation results to source files.")
    parser.add_argument("--repo", required=True, type=Path, help="Repository root to modify")
    parser.add_argument("--request", required=True, type=Path, help="translation-request.json used to produce results")
    parser.add_argument("--translations", required=True, type=Path, help="merged translation results JSON")
    parser.add_argument("--out", required=True, type=Path, help="Apply report JSON")
    parser.add_argument("--markdown", type=Path, help="Optional apply report Markdown")
    parser.add_argument("--apply", action="store_true", help="Write source file changes")
    parser.add_argument("--max-risk", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--rollback-patch", type=Path, help="Rollback patch path; defaults to rollback.patch next to --out")
    args = parser.parse_args()

    repo = args.repo.resolve()
    request = load_json(args.request)
    results = load_json(args.translations)
    items_by_id = request_items(request)
    max_rank = RISK_RANK[args.max_risk]

    original_texts: dict[Path, str] = {}
    current_texts: dict[Path, str] = {}
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for entry in translation_entries(results):
        item_id = str(entry.get("id") or "")
        item = items_by_id.get(item_id)
        if not item:
            status = "missing-request-item"
            counts[status] += 1
            records.append({"id": item_id, "status": status, "reason": "id not found in request"})
            continue

        path_text = item_path(item)
        line = item_line(item)
        risk = item_risk(item)
        source = item_source_text(item)
        target = translated_text(entry)
        base_record = {"id": item_id, "path": path_text, "line": line, "risk": risk}

        if bool(entry.get("skip")):
            status = "model-skipped"
            counts[status] += 1
            records.append({**base_record, "status": status, "reason": str(entry.get("reason") or "model skipped")})
            continue
        if RISK_RANK[risk] > max_rank:
            status = "risk-excluded"
            counts[status] += 1
            records.append({**base_record, "status": status, "reason": f"risk {risk} exceeds max-risk {args.max_risk}"})
            continue

        file_path = resolve_repo_path(repo, path_text)
        if file_path is None:
            status = "invalid-path"
            counts[status] += 1
            records.append({**base_record, "status": status, "reason": "path is empty or outside repo"})
            continue
        if not file_path.exists():
            status = "file-missing"
            counts[status] += 1
            records.append({**base_record, "status": status, "reason": "file does not exist"})
            continue

        if file_path not in current_texts:
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                status = "decode-error"
                counts[status] += 1
                records.append({**base_record, "status": status, "reason": "file is not utf-8 text"})
                continue
            original_texts[file_path] = text
            current_texts[file_path] = text

        next_text, status = replace_exact(current_texts[file_path], source, target, line)
        counts[status] += 1
        if status == "applied":
            current_texts[file_path] = next_text
        records.append({**base_record, "status": status, "reason": status})

    changed_files = [
        path
        for path, text in current_texts.items()
        if original_texts.get(path) != text
    ]
    rollback_patch = args.rollback_patch or args.out.with_name("rollback.patch")
    rollback_patch_written = False
    if args.apply:
        if changed_files:
            write_rollback_patch(rollback_patch, repo, original_texts, current_texts, changed_files)
            rollback_patch_written = True
        for path in changed_files:
            path.write_text(current_texts[path], encoding="utf-8")

    report = {
        "schema": "zero-zero-three.translation-apply-report",
        "created_at": now(),
        "repo": str(repo),
        "applied": bool(args.apply),
        "max_risk": args.max_risk,
        "rollback_patch": str(rollback_patch) if rollback_patch_written else None,
        "changed_files": [str(path.relative_to(repo).as_posix()) for path in changed_files],
        "summary": dict(sorted(counts.items())),
        "items": records,
    }
    write_json(args.out, report)
    if args.markdown:
        write_markdown(args.markdown, report)
    suffix = f"; rollback: {rollback_patch}" if rollback_patch_written else ""
    print(f"{'Applied' if args.apply else 'Planned'} {len(changed_files)} changed file(s); {counts.get('applied', 0)} replacement(s){suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
