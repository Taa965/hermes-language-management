#!/usr/bin/env python3
"""Scan local skill folders for user-visible output text."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


CURRENT_SKILL_NAME = "zero-zero-three-hermes-language-management"
TEXT_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json"}
OUTPUT_DIR_NAMES = {"assets", "asset", "templates", "template", "examples", "example"}
OPTIONAL_DIR_NAMES = {"references", "reference", "docs", "doc"}
INTERFACE_KEYS = {"display_name", "short_description", "default_prompt"}
YAML_TEXT_KEYS = {"title", "description", "summary", "label", "placeholder", "help", "name", "default_prompt"}
JSON_TEXT_RE = re.compile(r'"(?P<label>title|description|summary|label|placeholder|help|name|default_prompt|short_description|display_name)"\s*:\s*"(?P<text>(?:\\.|[^"])*)"')
YAML_LINE_RE = re.compile(r"^(?P<indent>\s*)(?P<label>[A-Za-z_][A-Za-z0-9_-]*):\s*(?P<value>.+?)\s*$")
ENGLISH_RE = re.compile(r"[A-Za-z][A-Za-z0-9][A-Za-z0-9 _.,:;!?()'\"/+-]{2,}")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
URL_RE = re.compile(r"https?://|wss?://|file://")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")


@dataclass
class Candidate:
    path: str
    line: int
    surface: str
    kind: str
    label: str
    text: str
    classification: str
    reason: str
    skill: str


def default_skill_roots() -> list[Path]:
    home = Path.home()
    return [home / ".hermes" / "skills"]


def has_english(text: str) -> bool:
    stripped = " ".join(text.split())
    return bool(ENGLISH_RE.search(stripped)) and not CJK_RE.search(stripped)


def unquote_yaml_value(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def classify(text: str, *, metadata: bool = False, review: bool = False) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped or not has_english(stripped):
        return "skip", "no untranslated English prose"
    if URL_RE.search(stripped):
        return "mixed-preserve", "contains URL"
    if len(stripped.split()) <= 2 and IDENTIFIER_RE.fullmatch(stripped):
        return "skip", "identifier-like text"
    if review:
        return "review", "skill instruction or metadata; inspect before changing"
    if metadata:
        return "mixed-preserve", "skill metadata; preserve skill name and trigger terms"
    return "translate", "likely user-visible skill output"


def skill_dirs(root: Path, include_current: bool) -> Iterable[Path]:
    if not root.exists():
        return
    for skill_md in sorted(root.glob("*/SKILL.md")):
        skill_dir = skill_md.parent
        if not include_current and skill_dir.name == CURRENT_SKILL_NAME:
            continue
        if any(part.startswith(".") and part not in {".well-known"} for part in skill_dir.relative_to(root).parts):
            continue
        yield skill_dir


def add_candidate(
    candidates: list[Candidate],
    root: Path,
    skill_dir: Path,
    path: Path,
    line: int,
    kind: str,
    label: str,
    text: str,
    *,
    metadata: bool = False,
    review: bool = False,
) -> None:
    cls, reason = classify(text, metadata=metadata, review=review)
    if cls == "skip":
        return
    candidates.append(
        Candidate(
            path=path.relative_to(root).as_posix(),
            line=line,
            surface="local-skill",
            kind=kind,
            label=label,
            text=text,
            classification=cls,
            reason=reason,
            skill=skill_dir.name,
        )
    )


def scan_openai_yaml(root: Path, skill_dir: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    path = skill_dir / "agents" / "openai.yaml"
    if not path.exists():
        return candidates
    in_interface = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.strip() == "interface:":
            in_interface = True
            continue
        if in_interface and line and not line.startswith((" ", "\t")):
            in_interface = False
        match = YAML_LINE_RE.match(line)
        if not match:
            continue
        label = match.group("label")
        if in_interface and label in INTERFACE_KEYS:
            add_candidate(
                candidates,
                root,
                skill_dir,
                path,
                lineno,
                "openai-yaml-interface",
                label,
                unquote_yaml_value(match.group("value")),
                metadata=True,
            )
    return candidates


def scan_skill_description(root: Path, skill_dir: Path, include_description: bool) -> list[Candidate]:
    candidates: list[Candidate] = []
    if not include_description:
        return candidates
    path = skill_dir / "SKILL.md"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return candidates
    for lineno, line in enumerate(lines[1:], 2):
        if line.strip() == "---":
            break
        match = YAML_LINE_RE.match(line)
        if match and match.group("label") == "description":
            add_candidate(
                candidates,
                root,
                skill_dir,
                path,
                lineno,
                "skill-frontmatter",
                "description",
                unquote_yaml_value(match.group("value")),
                review=True,
            )
    return candidates


def is_output_resource(path: Path, skill_dir: Path, include_references: bool) -> bool:
    try:
        rel = path.relative_to(skill_dir)
    except ValueError:
        return False
    if len(rel.parts) < 2:
        return False
    top = rel.parts[0].lower()
    return top in OUTPUT_DIR_NAMES or (include_references and top in OPTIONAL_DIR_NAMES)


def scan_resource_file(root: Path, skill_dir: Path, path: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    suffix = path.suffix.lower()
    in_code_fence = False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return candidates
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if suffix in {".md", ".txt"}:
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence or not stripped:
                continue
            if stripped.startswith("#"):
                text = stripped.lstrip("#").strip()
            elif stripped.startswith(("-", "*", ">")):
                text = stripped.lstrip("-*> ").strip()
            else:
                text = stripped
            add_candidate(candidates, root, skill_dir, path, lineno, "resource-text", "text", text)
        elif suffix in {".yaml", ".yml"}:
            match = YAML_LINE_RE.match(line)
            if match and match.group("label") in YAML_TEXT_KEYS:
                add_candidate(
                    candidates,
                    root,
                    skill_dir,
                    path,
                    lineno,
                    "resource-yaml",
                    match.group("label"),
                    unquote_yaml_value(match.group("value")),
                )
        elif suffix == ".json":
            for match in JSON_TEXT_RE.finditer(line):
                add_candidate(
                    candidates,
                    root,
                    skill_dir,
                    path,
                    lineno,
                    "resource-json",
                    match.group("label"),
                    match.group("text"),
                )
    return candidates


def scan_root(root: Path, include_current: bool, include_description: bool, include_references: bool) -> list[Candidate]:
    root = root.expanduser().resolve()
    candidates: list[Candidate] = []
    for skill_dir in skill_dirs(root, include_current):
        candidates.extend(scan_openai_yaml(root, skill_dir))
        candidates.extend(scan_skill_description(root, skill_dir, include_description))
        for path in sorted(skill_dir.rglob("*")):
            if path.is_dir() or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            if path.name == "SKILL.md" or path.as_posix().endswith("/agents/openai.yaml"):
                continue
            if is_output_resource(path, skill_dir, include_references):
                candidates.extend(scan_resource_file(root, skill_dir, path))
    return candidates


def write_markdown(candidates: list[Candidate]) -> str:
    lines = [
        "# Local Skill Output Localization Candidates",
        "",
        "| Skill | File | Line | Class | Label | Text | Reason |",
        "|---|---|---:|---|---|---|---|",
    ]
    for item in candidates:
        text = item.text.replace("|", "\\|").replace("\n", "\\n")
        if len(text) > 160:
            text = text[:157] + "..."
        lines.append(f"| `{item.skill}` | `{item.path}` | {item.line} | `{item.classification}` | `{item.kind}:{item.label}` | {text} | {item.reason} |")
    lines.append("")
    lines.append(f"Total candidates: {len(candidates)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan local skills for user-visible output language.")
    parser.add_argument("--skill-root", action="append", type=Path, help="Skill root containing skill folders; defaults to ~/.hermes/skills")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--include-current", action="store_true", help="Include this language-management skill")
    parser.add_argument("--include-skill-description", action="store_true", help="Include SKILL.md frontmatter descriptions as review items")
    parser.add_argument("--include-references", action="store_true", help="Scan references/docs folders in addition to assets/templates/examples")
    parser.add_argument("--classes", nargs="*", help="Only include these classifications")
    args = parser.parse_args()

    roots = args.skill_root or default_skill_roots()
    candidates: list[Candidate] = []
    for root in roots:
        candidates.extend(scan_root(root, args.include_current, args.include_skill_description, args.include_references))
    if args.classes:
        wanted = set(args.classes)
        candidates = [item for item in candidates if item.classification in wanted]
    candidates.sort(key=lambda item: (item.skill, item.path, item.line, item.text))
    output = json.dumps([asdict(item) for item in candidates], ensure_ascii=False, indent=2) if args.format == "json" else write_markdown(candidates)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
