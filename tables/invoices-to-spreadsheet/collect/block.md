---
mdblocks: 1
type: mdblocks/block
kind: leaf
execution: io
ports:
  in:
    folder:
      type: Param
      dtype: string
  out:
    documents: Files
code:
  lang: python
  entry: collect.py
---

# collect

Copies the PDFs and images in `folder` into `documents`, keeping their paths
below it. It skips any `.mdb` folder, where a project keeps copies from
earlier runs. A relative `folder` is read from the workflow's own folder. It
is an `io` step because it reads files no port declares, so it runs every
time; the steps after it are cached by each file's content, so an unchanged
file is never read twice.
