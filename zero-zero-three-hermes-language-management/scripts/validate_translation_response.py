#!/usr/bin/env python3
"""Validate a model translation response against a request or batch request."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


PLACEHOLDER_RE = re.compile(r"(\{[^{}]+\}|%\([^)]+\)[sdif]|%[sdif]|\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*)")


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.S | re.I)
        if match:
            stripped = match.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])
    raise


def load_jsonish(path: Path) -> Any:
    return extract_json(load_text(path))


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


def placeholders(text: str) -> list[str]:
    return PLACEHOLDER_RE.findall(text or "")


def add_issue(issues: list[dict[str, Any]], severity: str, issue_type: str, item_id: str, message: str) -> None:
    issues.append({"severity": severity, "type": issue_type, "id": item_id, "message": message})


def validate(request: dict[str, Any], response: Any) -> dict[str, Any]:
    items = [item for item in request.get("items", []) if isinstance(item, dict)]
    expected = {str(item.get("id")): item for item in items}
    translations = translations_from_response(response)
    issues: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    valid_translations: list[dict[str, Any]] = []

    if not translations:
        add_issue(issues, "error", "no-translations", "", "Response has no translations list.")

    for entry in translations:
        item_id = str(entry.get("id", ""))
        seen[item_id] += 1
        if item_id not in expected:
            add_issue(issues, "error", "unexpected-id", item_id, "Response contains an id not present in request.")
            continue
        if seen[item_id] > 1:
            add_issue(issues, "error", "duplicate-id", item_id, "Response contains a duplicate translation id.")
            continue
        source_item = expected[item_id]
        skipped = bool(entry.get("skip"))
        translated = str(entry.get("translated_text") or "")
        if skipped:
            if not str(entry.get("reason") or "").strip():
                add_issue(issues, "warning", "skip-without-reason", item_id, "Skipped item has no reason.")
            valid_translations.append(entry)
            continue
        if not translated.strip():
            add_issue(issues, "error", "empty-translation", item_id, "Translated text is empty.")
            continue
        source_text = str(source_item.get("source_text") or "")
        source_placeholders = placeholders(source_text)
        target_placeholders = placeholders(translated)
        if Counter(source_placeholders) != Counter(target_placeholders):
            add_issue(
                issues,
                "error",
                "placeholder-mismatch",
                item_id,
                f"Expected placeholders {source_placeholders}, got {target_placeholders}.",
            )
        for token in source_item.get("preserve_tokens") or []:
            token = str(token)
            if token and token not in translated:
                add_issue(issues, "error", "missing-preserve-token", item_id, f"Missing preserve token: {token}")
        if translated == source_text and not request.get("target_locale", "").lower().startswith("en"):
            add_issue(issues, "warning", "identical-to-source", item_id, "Translation is identical to source.")
        valid_translations.append(entry)

    for item_id in sorted(set(expected) - set(seen)):
        add_issue(issues, "error", "missing-id", item_id, "Response is missing a requested id.")

    counts = Counter(issue["severity"] for issue in issues)
    status = "fail" if counts.get("error") else ("warn" if issues else "pass")
    return {
        "schema": "zero-zero-three.translation-validation",
        "status": status,
        "request_id": request.get("batch_id") or request.get("schema"),
        "expected_items": len(items),
        "response_items": len(translations),
        "valid_items": len(valid_translations),
        "summary": {
            "issue_count": len(issues),
            "counts_by_severity": dict(sorted(counts.items())),
            "counts_by_type": dict(sorted(Counter(issue["type"] for issue in issues).items())),
        },
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a translation response against a request.")
    parser.add_argument("--request", required=True, type=Path, help="translation request or batch request JSON")
    parser.add_argument("--response", required=True, type=Path, help="model response JSON or markdown containing JSON")
    parser.add_argument("--out", required=True, type=Path, help="validation JSON output")
    parser.add_argument("--fail-on", choices=("never", "errors", "warnings"), default="never")
    args = parser.parse_args()

    request = load_jsonish(args.request)
    response = load_jsonish(args.response)
    if not isinstance(request, dict):
        raise SystemExit("request must be a JSON object")
    report = validate(request, response)
    write_json(args.out, report)
    print(f"Validation status: {report['status']} ({report['summary']['issue_count']} issue(s))")
    if args.fail_on == "errors" and report["summary"]["counts_by_severity"].get("error"):
        return 1
    if args.fail_on == "warnings" and report["summary"]["issue_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
