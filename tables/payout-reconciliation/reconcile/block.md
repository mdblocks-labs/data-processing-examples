---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    files: Json
    sources: Json
    merchant: Json
    approvals: Json
  out:
    report: Json
    summary: Json
code:
  lang: python
  entry: reconcile.py
---

# reconcile

Matches each export to the source in `sources.json` whose headers it carries
and parses its rows. Order, refund and fee rows add up to payouts, one per
processor and payout ID, in whole cents; bank rows are deposits. A deposit is
tied to a payout one to one:

- **by ID** when the bank description carries the payout ID as a whole word;
- **by amount and date** when exactly one open payout has the deposit's
  amount to the cent and is dated 0 to `match_days` days before it, and that
  payout has no other such deposit.

Two candidates on either side are `ambiguous`, never a guess; a deposit tied by
ID with another amount is `amount differs`. A payout with no deposit is `in
transit` until the bank rows reach `match_days` past its date, then `no
deposit`; a deposit no payout explains is `no payout`. A payout whose rows
give different payout dates is `dates differ`, placed by the latest, and tied
by ID only.

Every month the exports hold gets totals, open counts and an evidence
checksum over its rows, their statuses, `merchant.json` and `sources.json`. A
month is approved while a line in `approvals.csv` carries that checksum.
`report` has everything; `summary` has only what the site shows. Every row it
can't use is listed under `review` with its file and row. It uses only
Python's standard library.
