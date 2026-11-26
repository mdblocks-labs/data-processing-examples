---
mdblocks: 1
kind: map
ports:
  in:
    exports: Files
  out:
    files: Json
over:
  exports: {}
---

# per_file

Runs `read` once per export, so each file is decoded and cached on its own:
replacing one export decodes that file only. The records are gathered into
one list in file order.

```mdb-wire
import read
```
