---
mdblocks: 1
name: Example mdBlocks workflows for data processing
description: Invoices read into tables, payouts reconciled against bank deposits, and a weekly campaign report, from your own files on your own machine.
license: MIT
field: Data processing / Tables / Extraction
---

# Example mdBlocks workflows for data processing

Each example is one workflow you can run, read and copy, in its domain's folder.

| Example | Domain / Application | What it does |
|---|---|---|
| [Invoices to spreadsheet](tables/invoices-to-spreadsheet/) | Tables / Extraction | Reads invoices from their text layer or by OCR, pulls out the fields a schema file describes, checks the totals, and writes tables of invoices, line items and records to review, plus an Excel workbook. |
| [Payout reconciliation](tables/payout-reconciliation/) | Tables / Reconciliation | Ties each card or marketplace payout to its bank deposit from CSV exports, month by month, lists the deposits and payouts still open, and keeps the totals of each month you sign off in a dataset. |
| [Campaign performance](reports/campaign-performance/) | Reports / Dashboards | Merges one client's ad-spend, CRM and sales CSV exports into a weekly report of spend, qualified sales, cost per qualified sale and margin for each campaign, with a scale, hold or cut call and a results page. |
