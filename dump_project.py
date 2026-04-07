#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "data",
}

DEFAULT_EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".mp4",
    ".mp3",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
}

DEFAULT_INCLUDE_EXTS = {
    ".py",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".sql",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".xml",
    ".csv",
}


def is_probably_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(4096)
        if b"\x00" in chunk:
            return True
        chunk.decode("utf-8")
        return False
    except Exception:
        return True


def should_skip(
    path: Path,
    root: Path,
    include_all_text: bool,
    output_file: Path | None = None,
) -> bool:
    path_resolved = path.resolve()

    if output_file is not None and path_resolved == output_file.resolve():
        return True

    rel_parts = path.relative_to(root).parts

    if any(part in DEFAULT_EXCLUDE_DIRS for part in rel_parts[:-1]):
        return True

    if path.suffix.lower() in DEFAULT_EXCLUDE_EXTS:
        return True

    if not include_all_text:
        name = path.name.lower()
        suffix = path.suffix.lower()

        if name not in {".env", ".gitignore"} and suffix not in DEFAULT_INCLUDE_EXTS:
            return True

    return False


def iter_files(root: Path, include_all_text: bool, output_file: Path | None = None):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if should_skip(path, root, include_all_text, output_file=output_file):
            continue
        if is_probably_binary(path):
            continue
        yield path


def build_dump(root: Path, output_file: Path, include_all_text: bool) -> int:
    count = 0

    with output_file.open("w", encoding="utf-8") as out:
        for file_path in iter_files(
            root,
            include_all_text,
            output_file=output_file,
        ):
            rel = file_path.relative_to(root).as_posix()

            out.write("=" * 80 + "\n")
            out.write(f"FILE: {rel}\n")
            out.write("=" * 80 + "\n")

            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                text = f"[READ ERROR] {e}"

            out.write(text)
            if not text.endswith("\n"):
                out.write("\n")
            out.write("\n\n")
            count += 1

    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Собирает текстовый дамп проекта в один файл."
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Корень проекта, по умолчанию текущая директория.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="project_dump.txt",
        help="Имя выходного файла, по умолчанию project_dump.txt",
    )
    parser.add_argument(
        "--include-all-text",
        action="store_true",
        help="Включать все текстовые файлы, а не только известные расширения.",
    )

    args = parser.parse_args()

    root = Path(args.project_dir).resolve()
    output = Path(args.output).resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project dir not found: {root}")

    count = build_dump(
        root=root,
        output_file=output,
        include_all_text=args.include_all_text,
    )

    print(f"Dump created: {output}")
    print(f"Files included: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
