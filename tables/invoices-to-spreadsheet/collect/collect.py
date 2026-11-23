"""collect.py — the documents in a folder, as a `Files` value."""

import os
import shutil
import stat
from pathlib import Path

SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def run(folder, documents):
    """Copy every PDF and image under `folder` into the `documents` directory.

    Args:
        folder: str — absolute, or relative to the workflow folder.
        documents: Path — the `documents` out-port's directory.
    """
    source = Path(folder).expanduser()
    if not source.is_absolute():
        # The working directory is this block's folder; its parent is the workflow.
        source = Path.cwd().parent / source
    if not source.is_dir():
        raise FileNotFoundError(f"folder not found: {source}")
    found = 0
    for path in sorted(files(source)):
        target = documents / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        found += 1
    if not found:
        raise FileNotFoundError(f"no PDF or image files in {source}")


def files(source):
    """Every PDF and image under `source`, skipping any `.mdb` store; a folder
    that can't be listed stops the run."""
    def fail(error):
        raise PermissionError(f"folder not readable: {error.filename}") from error
    for root, dirs, names in os.walk(source, onerror=fail):
        # A project's `.mdb` store holds copies from earlier runs.
        dirs[:] = [d for d in dirs if d != ".mdb"]
        for name in names:
            path = Path(root) / name
            # stat() raises when a document can't be reached; is_file() would say False.
            if path.suffix.lower() in SUFFIXES and stat.S_ISREG(path.stat().st_mode):
                yield path
