---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    report: Json
  out:
    evidence: Bytes
    exceptions: Bytes
code:
  lang: python
  entry: export.py
---

# export

Writes two CSV files from the report. `evidence` has one line per counted
source row: its month, status, file and row number, values, and the bank row
or payout it was tied to. `exceptions` has one line per open payout or
deposit: `amount differs`, `no deposit`, `ambiguous`, `dates differ` and `no
payout`, with the expected amount, the deposit and the difference.

Text that starts like a spreadsheet formula (`=`, `+`, `-`, `@`) gets a
leading `'` in both files, so opening one in a spreadsheet shows the text the
export held; `report` keeps it as it was.
