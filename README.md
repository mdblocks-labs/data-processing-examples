# Example mdBlocks workflows for data processing

Each example is one workflow you can run, read and copy, in its domain's folder.

| Example | Domain / Application | What it does |
|---|---|---|
| [Invoices to spreadsheet](tables/invoices-to-spreadsheet/) | Tables / Extraction | Reads invoices from their text layer or by OCR, pulls out the fields a schema file describes, checks the totals, and writes tables of invoices, line items and records to review, plus an Excel workbook. |
| [Payout reconciliation](tables/payout-reconciliation/) | Tables / Reconciliation | Ties each card or marketplace payout to its bank deposit from CSV exports, month by month, lists the deposits and payouts still open, and keeps the totals of each month you sign off in a dataset. |
| [Campaign performance](reports/campaign-performance/) | Reports / Dashboards | Merges one client's ad-spend, CRM and sales CSV exports into a weekly report of spend, qualified sales, cost per qualified sale and margin for each campaign, with a scale, hold or cut call and a results page. |

## Try one

You need [mdBlocks](https://mdblocks.com) and [uv](https://docs.astral.sh/uv/). From the
repository root:

```sh
mdb run tables/invoices-to-spreadsheet --preset tables/invoices-to-spreadsheet/presets/samples.yaml
mdb run reports/campaign-performance --preset reports/campaign-performance/presets/period-1.yaml
```

Payout reconciliation is its own project, because it keeps the months you sign off in a
dataset. Seed the dataset once in its folder, then run it there:

```sh
cd tables/payout-reconciliation
mdb data init approved_totals --empty
mdb run . --preset presets/period-1.yaml
```

The samples are invented. Each workflow's `block.md` explains what it does, what it
promises and how to use your own files.

## Licence

MIT. See [LICENSE](LICENSE).
