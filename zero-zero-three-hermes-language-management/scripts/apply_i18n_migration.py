#!/usr/bin/env python3
"""Apply approved i18n key migration items to locale files and source code."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from apply_locale_consistency_fixes import find_locale_file, load_locale_file, set_nested
from apply_translation_results import RISK_RANK, translation_entries, translated_text
from check_i18n_consistency import load_simple_yaml

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


LOCALE_EXTENSIONS = {".json", ".yaml", ".yml"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_path(repo: Path, value: str) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(repo)
    except Exception:
        return None
    return resolved


def plan_items(plan: Any) -> list[dict[str, Any]]:
    if isinstance(plan, dict) and isinstance(plan.get("items"), list):
        return [item for item in plan["items"] if isinstance(item, dict)]
    return []


def translations_by_id(data: Any) -> dict[str, dict[str, Any]]:
    return {str(entry.get("id")): entry for entry in translation_entries(data)}


def risk_rank(value: str) -> int:
    return RISK_RANK.get(value, RISK_RANK["medium"])


def ensure_loaded(path: Path, original_texts: dict[Path, str], current_texts: dict[Path, str]) -> None:
    if path in current_texts:
        return
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    original_texts[path] = original
    current_texts[path] = original


def replacement_for(path: Path, key: str, helper: str) -> str:
    quoted_key = json.dumps(key, ensure_ascii=False)
    suffix = path.suffix.lower()
    if suffix == ".py":
        return f"{helper}({quoted_key})"
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return f"{helper}({quoted_key})"
    return f"{helper}({quoted_key})"


def replace_source_text(text: str, source: str, replacement: str, path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    quoted_double = json.dumps(source, ensure_ascii=False)
    quoted_single = "'" + source.replace("\\", "\\\\").replace("'", "\\'") + "'"

    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        escaped = re.escape(source)
        attr_pattern = re.compile(rf"=\s*(['\"]){escaped}\1")
        next_text, count = attr_pattern.subn("={" + replacement + "}", text, count=1)
        if count:
            return next_text, "applied-jsx-attribute"
        text_node_pattern = re.compile(rf">(\\s*){escaped}(\\s*)<")
        next_text, count = text_node_pattern.subn(r">\\1{" + replacement + r"}\\2<", text, count=1)
        if count:
            return next_text, "applied-jsx-text"

    if quoted_double in text:
        return text.replace(quoted_double, replacement, 1), "applied-string-literal"
    if quoted_single in text:
        return text.replace(quoted_single, replacement, 1), "applied-string-literal"
    if source in text:
        return text.replace(source, replacement, 1), "applied-raw-text"
    return text, "source-not-found"


def locale_file_for(locales_dir: Path, locale: str, source_locale: str) -> Path:
    existing = find_locale_file(locales_dir, locale)
    if existing:
        return existing
    source_file = find_locale_file(locales_dir, source_locale)
    suffix = source_file.suffix if source_file else ".yaml"
    return locales_dir / f"{locale}{suffix}"


def load_locale_data(path: Path, current_text: str | None = None) -> dict[str, Any]:
    if current_text is not None:
        if path.suffix.lower() == ".json":
            data = json.loads(current_text) if current_text.strip() else {}
        elif yaml is not None:
            data = yaml.safe_load(current_text) if current_text.strip() else {}
        else:
            data = load_simple_yaml(current_text)
        return data if isinstance(data, dict) else {}
    if path.exists():
        data = load_locale_file(path)
        return data if isinstance(data, dict) else {}
    return {}


def add_locale_value(
    path: Path,
    key: str,
    value: str,
    original_texts: dict[Path, str],
    current_texts: dict[Path, str],
) -> None:
    ensure_loaded(path, original_texts, current_texts)
    data = load_locale_data(path, current_texts.get(path))
    set_nested(data, key, value)
    if path.suffix.lower() == ".json":
        current_texts[path] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    else:
        # Reuse the locale writer on a temporary in-memory update by writing later from current_texts.
        from apply_locale_consistency_fixes import dump_yaml

        current_texts[path] = dump_yaml(data) + "\n"


def write_changed_files(current_texts: dict[Path, str], changed_files: list[Path]) -> None:
    for path in changed_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current_texts[path], encoding="utf-8")


def write_rollback_patch(path: Path, repo: Path, original_texts: dict[Path, str], current_texts: dict[Path, str], changed_files: list[Path]) -> None:
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


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# i18n Migration Apply Report",
        "",
        f"- Applied: {report.get('summary', {}).get('applied', 0)}",
        f"- Skipped: {report.get('summary', {}).get('skipped', 0)}",
        f"- Changed files: {len(report.get('changed_files', []))}",
        f"- Rollback patch: `{report.get('rollback_patch')}`",
        "",
        "## Items",
        "",
        "| Status | File | Line | Key | Reason |",
        "|---|---|---:|---|---|",
    ]
    for item in report.get("items", []):
        lines.append(
            "| `{}` | `{}` | {} | `{}` | {} |".format(
                item.get("status"),
                item.get("path"),
                item.get("line") or 0,
                item.get("key") or "",
                str(item.get("reason") or "").replace("|", "\\|"),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply approved i18n key migration items.")
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path, help="i18n-migration-plan.json")
    parser.add_argument("--translations", type=Path, help="Optional merged translation results JSON")
    parser.add_argument("--locales-dir", type=Path, default=Path("locales"))
    parser.add_argument("--source-locale", default="en")
    parser.add_argument("--target-locale", default="zh-CN")
    parser.add_argument("--helper", default="t", help="Existing runtime i18n helper function name")
    parser.add_argument("--max-risk", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--fill-target-with-source", action="store_true", help="Use source text when no target translation exists")
    parser.add_argument("--apply", action="store_true", help="Write locale and source files")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--rollback-patch", type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    plan = load_json(args.plan)
    translations = translations_by_id(load_json(args.translations)) if args.translations else {}
    locales_dir = args.locales_dir if args.locales_dir.is_absolute() else repo / args.locales_dir
    max_rank = risk_rank(args.max_risk)

    original_texts: dict[Path, str] = {}
    current_texts: dict[Path, str] = {}
    changed: list[Path] = []
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for item in plan_items(plan):
        item_id = str(item.get("id") or "")
        risk = str(item.get("risk") or "medium")
        key = str(item.get("suggested_key") or "")
        source_text = str(item.get("source_text") or item.get("source_locale_value") or "")
        source_path_text = str(item.get("path") or "")
        line = int(item.get("line") or 0)
        base_record = {"id": item_id, "path": source_path_text, "line": line, "key": key, "risk": risk}

        if not key or not source_text:
            counts["invalid-item"] += 1
            records.append({**base_record, "status": "invalid-item", "reason": "missing key or source text"})
            continue
        if risk_rank(risk) > max_rank or str(item.get("action")) == "inspect_before_migration":
            counts["risk-excluded"] += 1
            records.append({**base_record, "status": "risk-excluded", "reason": f"risk {risk} exceeds max-risk {args.max_risk}"})
            continue

        target_text = ""
        translated_entry = translations.get(item_id)
        if translated_entry and not translated_entry.get("skip"):
            target_text = translated_text(translated_entry)
        if not target_text:
            target_text = str(item.get("target_locale_value") or "")
        if not target_text and args.fill_target_with_source:
            target_text = source_text
        if not target_text:
            counts["missing-target-translation"] += 1
            records.append({**base_record, "status": "missing-target-translation", "reason": "no target translation available"})
            continue

        source_locale_file = locale_file_for(locales_dir, args.source_locale, args.source_locale)
        target_locale_file = locale_file_for(locales_dir, args.target_locale, args.source_locale)
        add_locale_value(source_locale_file, key, source_text, original_texts, current_texts)
        add_locale_value(target_locale_file, key, target_text, original_texts, current_texts)
        for locale_path in (source_locale_file, target_locale_file):
            if locale_path not in changed:
                changed.append(locale_path)

        source_path = normalize_path(repo, source_path_text)
        if source_path is None:
            counts["invalid-source-path"] += 1
            records.append({**base_record, "status": "invalid-source-path", "reason": "source path is empty or outside repo"})
            continue
        if source_path.suffix.lower() in LOCALE_EXTENSIONS:
            counts["locale-only"] += 1
            records.append({**base_record, "status": "locale-only", "reason": "locale resource updated; source replacement skipped"})
            continue
        if not source_path.exists():
            counts["source-file-missing"] += 1
            records.append({**base_record, "status": "source-file-missing", "reason": "source file does not exist"})
            continue

        ensure_loaded(source_path, original_texts, current_texts)
        replacement = replacement_for(source_path, key, args.helper)
        next_text, replace_status = replace_source_text(current_texts[source_path], source_text, replacement, source_path)
        if replace_status.startswith("applied"):
            current_texts[source_path] = next_text
            if source_path not in changed:
                changed.append(source_path)
            counts["applied"] += 1
            records.append({**base_record, "status": "applied", "reason": replace_status})
        else:
            counts[replace_status] += 1
            records.append({**base_record, "status": replace_status, "reason": replace_status})

    rollback = args.rollback_patch or args.out.with_name("i18n-rollback.patch")
    report = {
        "schema": "zero-zero-three.i18n-migration-apply-report",
        "repo": str(repo),
        "plan": str(args.plan),
        "applied": bool(args.apply),
        "source_locale": args.source_locale,
        "target_locale": args.target_locale,
        "helper": args.helper,
        "changed_files": [str(path) for path in changed],
        "rollback_patch": str(rollback),
        "summary": {
            "applied": counts.get("applied", 0),
            "skipped": sum(value for key_name, value in counts.items() if key_name != "applied"),
            "counts_by_status": dict(sorted(counts.items())),
        },
        "items": records,
    }

    if args.apply:
        write_changed_files(current_texts, changed)
    if changed:
        write_rollback_patch(rollback, repo, original_texts, current_texts, changed)
    else:
        rollback.parent.mkdir(parents=True, exist_ok=True)
        rollback.write_text("", encoding="utf-8")
    write_json(args.out, report)
    if args.markdown:
        write_markdown(args.markdown, report)
    print(f"i18n migration apply report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
