"""read.py — one CSV export as its header and rows of text."""

import csv
import hashlib
import io


def run(exports):
    """Decode every export this block was handed.

    Args:
        exports: FilesIn — `(relative_path, Path)` pairs; inside the map, one file.

    Returns:
        {"files": list} — per file: `{file, sha256, header, rows, error}`.
    """
    out = []
    for name, path in exports:
        data = path.read_bytes()
        record = {"file": name, "sha256": hashlib.sha256(data).hexdigest(),
                  "header": [], "rows": [], "error": None}
        # A field can be as long as the file; Python's default limit is 131,072 characters.
        csv.field_size_limit(max(csv.field_size_limit(), len(data)))
        try:
            # strict=True turns a stray quote into an error rather than a guess.
            table = list(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True))
        except (UnicodeDecodeError, csv.Error) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        else:
            if not table:
                record["error"] = "empty file"
            else:
                record["header"], record["rows"] = table[0], table[1:]
        out.append(record)
    return {"files": out}
