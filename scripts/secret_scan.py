"""Fail when likely non-placeholder DataForSEO credentials appear in source files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".git",
    ".venv",
    ".venv-monthly",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "data",
    "logs",
    "target",
}
BINARY_SUFFIXES = {".duckdb", ".wal"}
ALLOWED_TEST_FIXTURE = Path("tests/unit/test_logging_redaction.py")
PATTERN = re.compile(
    r"DATAFORSEO_(?:LOGIN|PASSWORD)[ \t]*=[ \t]*([^\s#]+)"
)


def has_credentials(content: str, relative: Path) -> bool:
    """Empty assignments cannot consume another line; dummy fixtures stay narrow."""
    for match in PATTERN.finditer(content):
        value = match.group(1)
        if value.startswith("replace-with-"):
            continue
        if relative == Path("tests/unit/test_settings.py"):
            # Explicit fixture literals only, never arbitrary credentials in tests.
            literal = value.split("\\n", 1)[0].strip("\"'")
            if literal in {"dotenv-login", "dotenv-password"}:
                continue
        return True
    return False


def main() -> int:
    findings: list[str] = []
    paths: list[Path] = []
    for directory, directories, filenames in ROOT.walk():
        directories[:] = [name for name in directories if name not in EXCLUDED]
        paths.extend(directory / name for name in filenames)
    for path in paths:
        if not path.is_file() or EXCLUDED & set(path.parts):
            continue
        if path.name == ".env":
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if path.relative_to(ROOT) == ALLOWED_TEST_FIXTURE:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            print("Secret scan could not read: " + str(path.relative_to(ROOT)))
            return 1
        if has_credentials(content, path.relative_to(ROOT)):
            findings.append(str(path.relative_to(ROOT)))
    if findings:
        print("Potential credentials found: " + ", ".join(sorted(findings)))
        return 1
    print("Secret scan passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
