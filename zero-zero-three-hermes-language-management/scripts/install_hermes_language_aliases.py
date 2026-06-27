#!/usr/bin/env python3
"""Install Hermes quick-command aliases for the language-management skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ALIASES = ["语言", "lang", "hermes-lang", "hermes-language"]
DEFAULT_SKILL_OUTPUT_ALIASES = ["技能语言", "skill-lang", "skills-lang", "skill-language"]
DEFAULT_TARGET = "zero-zero-three-hermes-language-management"
DEFAULT_SKILL_OUTPUT_TARGET = "zero-zero-three-hermes-language-management skills"


def load_yaml_module():
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit("PyYAML is required to update Hermes config.yaml") from exc
    return yaml


def default_config_path() -> Path:
    return Path.home() / ".hermes" / "config.yaml"


def load_config(path: Path) -> dict[str, Any]:
    yaml = load_yaml_module()
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def write_config(path: Path, data: dict[str, Any]) -> None:
    yaml = load_yaml_module()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def install_aliases(config: dict[str, Any], aliases: list[str], target: str) -> dict[str, Any]:
    quick_commands = config.get("quick_commands")
    if not isinstance(quick_commands, dict):
        quick_commands = {}
        config["quick_commands"] = quick_commands

    changed: list[str] = []
    preserved: list[str] = []
    for alias in aliases:
        alias = alias.strip().lstrip("/")
        if not alias:
            continue
        desired = {"type": "alias", "target": target}
        if quick_commands.get(alias) == desired:
            preserved.append(alias)
            continue
        quick_commands[alias] = desired
        changed.append(alias)
    return {"changed": changed, "preserved": preserved, "target": target}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install quick command aliases for the Hermes language-management skill.")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Language target command without leading slash")
    parser.add_argument("--skill-output-target", default=DEFAULT_SKILL_OUTPUT_TARGET, help="Local-skill-output target command without leading slash")
    parser.add_argument("--aliases", nargs="*", default=DEFAULT_ALIASES, help="Language alias names without leading slash")
    parser.add_argument("--skill-output-aliases", nargs="*", default=DEFAULT_SKILL_OUTPUT_ALIASES, help="Local-skill-output alias names without leading slash")
    parser.add_argument("--skip-language-aliases", action="store_true")
    parser.add_argument("--skip-skill-output-aliases", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config_path = args.config.expanduser()
    config = load_config(config_path)
    results = []
    if not args.skip_language_aliases:
        results.append({"group": "language", **install_aliases(config, args.aliases, args.target.strip().lstrip("/"))})
    if not args.skip_skill_output_aliases:
        results.append({"group": "skill-output", **install_aliases(config, args.skill_output_aliases, args.skill_output_target.strip().lstrip("/"))})
    result = {
        "groups": results,
        "changed": [alias for group in results for alias in group["changed"]],
        "preserved": [alias for group in results for alias in group["preserved"]],
    }
    result["config"] = str(config_path)
    result["dry_run"] = bool(args.dry_run)

    if not args.dry_run:
        write_config(config_path, config)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for group in result["groups"]:
            changed = ", ".join(f"/{name}" for name in group["changed"]) or "none"
            preserved = ", ".join(f"/{name}" for name in group["preserved"]) or "none"
            print(f"{group['group']} installed aliases: {changed}")
            print(f"{group['group']} already present: {preserved}")
            print(f"{group['group']} target: /{group['target']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
