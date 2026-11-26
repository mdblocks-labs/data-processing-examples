---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    exports: Files
  out:
    files: Json
code:
  lang: python
  entry: read.py
---

# read

Decodes a CSV export: its SHA-256, its header and its rows as text, with a
leading byte-order mark dropped. A file that isn't UTF-8 or valid CSV gets
the reason instead, and `report` lists it under review. It uses only
Python's standard library.
