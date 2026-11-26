---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    invoices: Table
    line_items: Table
    review: Table
  out:
    workbook: Bytes
env:
  requires_python: ">=3.11"
  python:
    - "pyarrow>=16"
    - "openpyxl>=3.1"
code:
  lang: python
  entry: export.py
---

# export

Writes the three tables as sheets of one `.xlsx` workbook, with a frozen
header row and amounts as numbers.
