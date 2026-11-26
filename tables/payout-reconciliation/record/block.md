---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    report: Json
    history: Table
  out:
    rows: Table
    kept: Json
env:
  requires_python: ">=3.11"
  python:
    - "pyarrow>=16"
code:
  lang: python
  entry: record.py
---

# record

The rows to append to `approved_totals`: one for each approved month whose
evidence checksum differs from that month's last row in `history`, or that
has no row yet. A row holds the month, the checksum, the latest current
approval's name and date, the currency and the month's totals. A month that
is not approved, or whose approval is out of date, adds nothing, and a month
in `history` that the folder no longer holds is left as it is. With nothing
new, `rows` is empty and the sink commits nothing.

`kept` is what the site shows of a month the dataset holds but this run found
no rows for: the month's last row, as its month, approver, date, currency and totals,
without the checksum or earlier rows.
