#!/usr/bin/env python3
"""
Simple YAML linter/formatter for your discovery artifacts.

Usage:
  python lint_yaml.py path1 [path2 ...]
    - If a path is a file: check that file.
    - If a path is a directory: recursively check all *.yml / *.yaml.

Add --fix to rewrite files in a normalized, pretty format:
  python lint_yaml.py --fix discovery_artifacts/
"""

import sys
from pathlib import Path

import yaml


def iter_yaml_files(paths):
    """Yield all YAML files from a list of file/dir paths."""
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix in {".yml", ".yaml"}:
            yield p
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix in {".yml", ".yaml"}:
                    yield f
        # silently ignore non-existent / non-yaml things


def lint_file(path: Path) -> bool:
    """Return True if YAML is valid, False otherwise."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        # Even an empty file is technically valid YAML (None)
        print(f"[OK]    {path}")
        return True
    except yaml.YAMLError as e:
        print(f"[ERROR] {path}")
        print(f"        {e}")
        return False


def format_file(path: Path) -> bool:
    """
    Load and re-dump YAML to a normalized format.
    Overwrites the file if valid.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            original_content = fh.read()
            fh.seek(0)
            data = yaml.safe_load(fh)
    except yaml.YAMLError as e:
        print(f"[SKIP]  {path} (invalid YAML, not reformatted)")
        print(f"        {e}")
        return False

    # Generate normalized content
    from io import StringIO
    output = StringIO()
    yaml.safe_dump(
        data,
        output,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    normalized_content = output.getvalue()

    # Only write if content changed
    if normalized_content != original_content:
        with path.open("w", encoding="utf-8") as fh:
            fh.write(normalized_content)
        print(f"[FIXED] {path}")
    else:
        print(f"[OK]    {path} (already formatted)")
    
    return True


def main(argv):
    if not argv:
        print("Usage: lint_yaml.py [--fix] path1 [path2 ...]")
        sys.exit(1)

    fix = False
    if "--fix" in argv:
        fix = True
        argv = [a for a in argv if a != "--fix"]

    files = list(iter_yaml_files(argv))
    if not files:
        print("No YAML files found under given paths.")
        sys.exit(1)

    ok = True
    for f in files:
        if fix:
            ok = format_file(f) and ok
        else:
            ok = lint_file(f) and ok

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1:])