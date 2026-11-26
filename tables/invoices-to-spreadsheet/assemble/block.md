---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    records: Json
    schema: Json
  out:
    invoices: Table
    line_items: Table
    review: Table
env:
  requires_python: ">=3.11"
  python:
    - "pyarrow>=16"
code:
  lang: python
  entry: assemble.py
---

# assemble

Lays the records out as three tables: `invoices`, one row per file with a
`needs_review` flag; `line_items`, one row per line; and `review`, one row per
problem. The invoice columns are the schema's fields in its order, so a field
added there becomes a column. Amounts are `decimal(12, 2)` and dates are dates.
