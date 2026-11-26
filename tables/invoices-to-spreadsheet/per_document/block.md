---
mdblocks: 1
kind: map
ports:
  in:
    documents: Files
  out:
    text: Json
over:
  documents: {}
---

# per_document

Runs `read` once per file in `documents`, so each file is read and cached on
its own: adding one file to the folder reads that file only. The text is
gathered into one list in file order.

```mdb-wire
import read
```
