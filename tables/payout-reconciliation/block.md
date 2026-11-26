---
mdblocks: 1
kind: composite
ports:
  in:
    sources: Json
    history: Table
  out:
    report: Json
    summary: Json
    evidence: Bytes
    exceptions: Bytes
    new_approvals: Table
params:
  folder:
    dtype: string
    default: "samples/period-2"
card:
  usage:
    - workflow
  field: Data processing / Tables / Reconciliation
---

# payout-reconciliation

**Which deposits still need investigating, and which months can be signed
off?** Put a merchant's order, refund, fee and bank exports in one folder, as
CSV files with whatever headers each tool writes. This workflow ties each
processor payout to its bank deposit, month by month, and lists what is still
open: a deposit with another amount, a payout with no deposit, a deposit no
payout explains, and anything with two candidates.

[`sources.json`](sources.json) says which headers each export has, how it
writes dates, which processor it belongs to, and whether it writes refunds
and fees as positive numbers. The folder's `merchant.json` names the
merchant, its currency and `match_days`, how many days a deposit may land
after its payout. Nothing is fetched and nothing leaves the machine.

Each month gets an evidence checksum. To sign a month off, add a line to the
folder's `approvals.csv` with the month, that checksum, your name and the
date. If a corrected export changes the month later, the approval is out of
date until a new line is added. The folder is read on every run, and every
step after that is cached: replace one export and only that file is decoded
again. A row that can't be used is listed under review, never guessed.

Each approval is also kept in the `approved_totals` dataset
([`data/approved_totals/`](data/approved_totals/dataset.md)): one row with the
month, its checksum, who approved it and the month's totals. A month stays
there after its exports leave the folder, and a month approved again after a
correction gets a second row; its last row is current. The site shows such a
month's last recorded approval when a run finds no rows for it. A run that approves
nothing new adds nothing. The dataset lives in this folder's `.mdb/`, not in
git.

```mdb-wire
import collect
import per_file
import reconcile
import export
import record

collect.exports -> per_file.exports

per_file.files -> reconcile.files
@in.sources -> reconcile.sources
collect.merchant -> reconcile.merchant
collect.approvals -> reconcile.approvals
reconcile.report -> export.report
reconcile.report -> record.report
@in.history -> record.history

reconcile.report -> @out.report
reconcile.summary -> @out.summary
export.evidence -> @out.evidence
export.exceptions -> @out.exceptions
record.rows -> @out.new_approvals
```

## Try it

This folder is its own project. Seed the dataset once, then run each period:

```sh
cd tables/payout-reconciliation
mdb data init approved_totals --empty
mdb run . --preset presets/period-1.yaml
mdb run . --preset presets/period-2.yaml
```

The [samples](samples/) are invented exports for Lantern & Loom Candle Co.,
which sells through a card processor and a marketplace. Period 1 is the
exports pulled on 2 November: a card deposit short by a fee, a marketplace
settlement whose refunds export is missing a refund, a deposit no payout
explains, and a card payout still in transit. Period 2 is three weeks later,
with the refunds export corrected and October approved: period 1 adds nothing
to the dataset, and period 2 adds October's row. See it with
`mdb data head approved_totals`.

To see the months and the open items, open the folder in `mdb ui`: the Site
tab shows each month's status, and the `report` output has every row. Save
the two CSV files from the latest run:

```sh
cp "$(mdb runs show latest --block export --port exceptions --path)" exceptions.csv
cp "$(mdb runs show latest --block export --port evidence --path)" evidence.csv
```

Each month's status and evidence checksum, to copy into `approvals.csv`:

```sh
python3 -c 'import json, sys; [print(m["month"], m["status"], m["checksum"]) for m in json.load(open(sys.argv[1]))["months"]]' \
  "$(mdb runs show latest --block reconcile --port report --path)"
```

The site shows totals only for approved months, and for any other month only
how many payouts and deposits are open. A month whose exports have left the
folder shows its last recorded approval from the dataset. A copy built with
`mdb site build` carries no row, ID, unapproved amount or checksum.

To use your own exports, copy this folder once per merchant, since its
dataset holds one merchant's approvals. Copy only the tracked files: leave
out `.mdb/`, which holds the samples' runs and dataset, and run
`mdb data init approved_totals --empty` in the copy. There, put the exports
and a `merchant.json` like the samples' in a folder, set `folder` in a preset,
and edit the headers in `sources.json` to match your exports.
