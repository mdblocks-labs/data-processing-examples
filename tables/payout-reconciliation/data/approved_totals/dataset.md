---
mdblocks: 1
kind: table
schema:
  month: Utf8
  checksum: Utf8
  approved_by: Utf8
  approved_on: Date
  currency: Utf8
  payouts: Int64
  paid_out: Int64
  orders: Int64
  refunds: Int64
  fees: Int64
  deposits: Int64
  deposited: Int64
  matched: Int64
  open_payouts: Int64
  open_deposits: Int64
  in_transit: Int64
---

# approved_totals

One row per month approval: the month, the evidence checksum that was
approved, who approved it and when, and the month's totals in whole cents.
`record` appends a row when a month is approved with a checksum other than its
last row's, so a month approved again after a corrected export has two rows
and its last one is current. Rows are never removed, so a month stays here
after its exports leave the folder. No source row, payout ID or unapproved
amount is kept.
