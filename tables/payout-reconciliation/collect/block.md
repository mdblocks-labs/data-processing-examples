---
mdblocks: 1
kind: leaf
execution: io
ports:
  out:
    exports: Files
    merchant: Json
    approvals: Json
params:
  folder:
    dtype: string
code:
  lang: python
  entry: collect.py
---

# collect

Copies the CSV files in `folder` into `exports`, keeping their paths below
it, and skips any `.mdb` folder and the folder's `approvals.csv`. Outputs the
folder's `merchant.json`, and the text of `approvals.csv` when there is one
(`null` when not). A relative `folder` is read from the workflow's own
folder. It is an `io` step because it reads files no port declares, so it
runs every time; the steps after it are cached by content.
