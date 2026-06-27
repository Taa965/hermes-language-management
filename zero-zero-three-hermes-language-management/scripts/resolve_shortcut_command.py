#!/usr/bin/env python3
"""Resolve Hermes language-management shortcut arguments deterministically."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TARGET_ALIASES: dict[str, tuple[str, str]] = {
    "hanhua": ("zh-CN", "Simplified Chinese"),
    "汉化": ("zh-CN", "Simplified Chinese"),
    "中文": ("zh-CN", "Simplified Chinese"),
    "简体": ("zh-CN", "Simplified Chinese"),
    "简体中文": ("zh-CN", "Simplified Chinese"),
    "zh": ("zh-CN", "Simplified Chinese"),
    "zh-cn": ("zh-CN", "Simplified Chinese"),
    "繁中": ("zh-Hant", "Traditional Chinese"),
    "繁体": ("zh-Hant", "Traditional Chinese"),
    "繁体中文": ("zh-Hant", "Traditional Chinese"),
    "zh-hant": ("zh-Hant", "Traditional Chinese"),
    "日文": ("ja-JP", "Japanese"),
    "日语": ("ja-JP", "Japanese"),
    "日本語": ("ja-JP", "Japanese"),
    "ja": ("ja-JP", "Japanese"),
    "ja-jp": ("ja-JP", "Japanese"),
    "韩文": ("ko-KR", "Korean"),
    "韩语": ("ko-KR", "Korean"),
    "한국어": ("ko-KR", "Korean"),
    "ko": ("ko-KR", "Korean"),
    "ko-kr": ("ko-KR", "Korean"),
    "英文": ("en", "English"),
    "英语": ("en", "English"),
    "english": ("en", "English"),
    "en": ("en", "English"),
    "en-us": ("en", "English"),
}

COMMAND_ALIASES = {
    "/zero-zero-three-hermes-language-management",
    "/语言",
    "/lang",
    "/hermes-lang",
    "/hermes-language",
    "/技能语言",
    "/skill-lang",
    "/skills-lang",
    "/skill-language",
}
SKILL_MODE_COMMANDS = {"/技能语言", "/skill-lang", "/skills-lang", "/skill-language"}
SKILL_MODE_OPTIONS = {"skills", "skill", "技能", "本地skill", "本地技能", "local-skills", "skill-output"}
SCAN_ONLY_OPTIONS = {"只扫描", "scan", "dry-run", "--dry-run"}
RESUME_OPTIONS = {"续跑", "resume", "--resume"}
STATUS_OPTIONS = {"状态", "status", "--status"}
ALLOW_HIGH_RISK_OPTIONS = {"高风险也改", "--allow-high-risk", "allow-high-risk"}
I18N_OPTIONS = {"i18n", "i18n-key", "i18n迁移", "key迁移"}
PUNCTUATION = ";；.。:："


def normalize_token(token: str) -> str:
    return token.strip().strip(PUNCTUATION).strip()


def split_segments(text: str) -> list[str]:
    normalized = text.replace("，", ",")
    raw_parts = re.split(r"[\s,]+", normalized)
    return [normalize_token(part) for part in raw_parts if normalize_token(part)]


def collect_tokens(command: str | None, argv: list[str]) -> list[str]:
    pieces: list[str] = []
    if command:
        pieces.append(command)
    pieces.extend(argv)
    tokens: list[str] = []
    for piece in pieces:
        tokens.extend(split_segments(piece))
    return tokens


def resolve(tokens: list[str]) -> dict[str, Any]:
    command: str | None = None
    cleaned: list[str] = []
    for token in tokens:
        if token.startswith("/") and command is None:
            command = token
            continue
        cleaned.append(token)

    mode = "skill-output" if command in SKILL_MODE_COMMANDS else "hermes-project"
    target_locale = "zh-CN"
    target_language = "Simplified Chinese"
    explicit_target = False
    options: dict[str, Any] = {
        "scan_only": False,
        "resume": False,
        "status": False,
        "allow_high_risk": False,
        "i18n": False,
    }
    unknown: list[str] = []

    for token in cleaned:
        lowered = token.lower()
        if lowered in TARGET_ALIASES:
            target_locale, target_language = TARGET_ALIASES[lowered]
            explicit_target = True
            continue
        if token in TARGET_ALIASES:
            target_locale, target_language = TARGET_ALIASES[token]
            explicit_target = True
            continue
        if lowered in SKILL_MODE_OPTIONS or token in SKILL_MODE_OPTIONS:
            mode = "skill-output"
            continue
        if lowered in SCAN_ONLY_OPTIONS or token in SCAN_ONLY_OPTIONS:
            options["scan_only"] = True
            continue
        if lowered in RESUME_OPTIONS or token in RESUME_OPTIONS:
            options["resume"] = True
            continue
        if lowered in STATUS_OPTIONS or token in STATUS_OPTIONS:
            options["status"] = True
            continue
        if lowered in ALLOW_HIGH_RISK_OPTIONS or token in ALLOW_HIGH_RISK_OPTIONS:
            options["allow_high_risk"] = True
            continue
        if lowered in I18N_OPTIONS or token in I18N_OPTIONS:
            options["i18n"] = True
            continue
        if token not in COMMAND_ALIASES:
            unknown.append(token)

    pipeline_args = [
        "--target-locale",
        target_locale,
        "--target-language",
        target_language,
    ]
    if options["resume"]:
        pipeline_args.append("--resume")
    if options["i18n"]:
        pipeline_args.extend(["--mode", "i18n-key-migration"])

    return {
        "schema": "zero-zero-three.hermes-shortcut-resolution",
        "command": command,
        "mode": mode,
        "target_locale": target_locale,
        "target_language": target_language,
        "explicit_target": explicit_target,
        "defaulted_target": not explicit_target,
        "options": options,
        "unknown_tokens": unknown,
        "pipeline_args": pipeline_args,
        "local_skill_output": mode == "skill-output",
        "direct_apply": not options["scan_only"] and not options["status"],
        "status_only": bool(options["status"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Hermes language-management shortcut arguments.")
    parser.add_argument("args", nargs="*", help="Shortcut arguments after the slash command")
    parser.add_argument("--command", help="Full shortcut command text, e.g. '/语言 日文'")
    parser.add_argument("--out", type=Path, help="Optional JSON output path")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    result = resolve(collect_tokens(args.command, args.args))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        print(f"Mode: {result['mode']}")
        print(f"Target: {result['target_language']} ({result['target_locale']})")
        print(f"Defaulted: {result['defaulted_target']}")
        if result["unknown_tokens"]:
            print("Unknown tokens: " + ", ".join(result["unknown_tokens"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
