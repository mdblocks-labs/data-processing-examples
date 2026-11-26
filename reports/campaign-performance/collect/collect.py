"""collect.py — a client's exports, settings and last report, from one folder."""

import json
import os
import shutil
import stat
from pathlib import Path


def run(folder, exports):
    """Copy every CSV under `folder` into `exports`; read its two JSON files.

    Args:
        folder: str — absolute, or relative to the workflow folder.
        exports: Path — the `exports` out-port's directory.

    Returns:
        {"client": dict, "previous": str | None}
    """
    source = Path(folder).expanduser()
    if not source.is_absolute():
        # The working directory is this block's folder; its parent is the workflow.
        source = Path.cwd().parent / source
    if not source.is_dir():
        raise FileNotFoundError(f"folder not found: {source}")
    found = 0
    for path in sorted(csv_files(source)):
        target = exports / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        found += 1
    if not found:
        raise FileNotFoundError(f"no CSV files in {source}")
    client = source / "client.json"
    if not client.is_file():
        raise FileNotFoundError(f"client.json not found in {source}")
    previous = source / "previous-report.json"
    if previous.is_symlink() and not previous.exists():
        raise FileNotFoundError(f"previous-report.json can't be read: {previous} points to a missing file")
    return {
        "client": json.loads(client.read_text(encoding="utf-8")),
        # As text: `report` parses it, so a damaged file goes to review rather than stopping the run.
        # Absent means none; an entry that can't be read (a broken link) stops the run, naming it.
        "previous": previous.read_text(encoding="utf-8", errors="replace")
        if previous.exists() or previous.is_symlink() else None,
    }


def csv_files(source):
    """Every CSV under `source`, skipping any `.mdb` store; a folder that can't
    be listed stops the run."""
    def fail(error):
        raise PermissionError(f"folder not readable: {error.filename}") from error
    for root, dirs, names in os.walk(source, onerror=fail):
        dirs[:] = [d for d in dirs if d != ".mdb"]
        for name in names:
            path = Path(root) / name
            # stat() raises when a file can't be reached; is_file() would say False.
            if path.suffix.lower() == ".csv" and stat.S_ISREG(path.stat().st_mode):
                yield path
