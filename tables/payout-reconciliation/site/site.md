---
mdblocks: 1
title: Payout reconciliation by month
reads:
  - reconcile.summary
  - record.kept
---

# Payout reconciliation by month

The question this page answers: **which months are signed off, and how much
is still open in the others?** Each month shows its status. An approved month
shows its totals; any other month shows only how many payouts and deposits
are open or in transit. A month this run found no rows for, but which the
`approved_totals` dataset holds, shows its last recorded approval. The page
reads the summary and `record.kept`, which hold approved totals only, so a
built copy carries no source row, payout ID, unapproved amount or checksum.
