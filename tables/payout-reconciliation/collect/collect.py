"""collect.py — a merchant's exports, settings and approvals, from one folder."""

import json
import os
import shutil
import stat
from pathlib import Path


def run(folder, exports):
    """Copy every CSV under `folder` but `approvals.csv` into `exports`; read the other two files.

    Args:
        folder: str — absolute, or relative to the workflow folder.
        exports: Path — the `exports` out-port's directory.

    Returns:
        {"merchant": dict, "approvals": str | None}
    """
    source = Path(folder).expanduser()
    if not source.is_absolute():
        # The working directory is this block's folder; its parent is the workflow.
        source = Path.cwd().parent / source
    if not source.is_dir():
        raise FileNotFoundError(f"folder not found: {source}")
    approvals = source / "approvals.csv"
    found = 0
    for path in sorted(csv_files(source)):
        if path == approvals:
            continue
        target = exports / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        found += 1
    if not found:
        raise FileNotFoundError(f"no CSV files in {source}")
    merchant = source / "merchant.json"
    if not merchant.is_file():
        raise FileNotFoundError(f"merchant.json not found in {source}")
    try:
        settings = json.loads(merchant.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"merchant.json is not valid JSON: {exc}") from None
    if approvals.is_symlink() and not approvals.exists():
        raise FileNotFoundError(f"approvals.csv can't be read: {approvals} points to a missing file")
    return {
        "merchant": settings,
        # As text: `reconcile` parses it, so a bad line goes to review rather than stopping the run.
        "approvals": approvals.read_text(encoding="utf-8-sig", errors="replace") if approvals.exists() else None,
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
