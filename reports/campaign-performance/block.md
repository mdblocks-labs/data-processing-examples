---
mdblocks: 1
kind: composite
ports:
  in:
    sources: Json
  out:
    report: Json
params:
  folder:
    dtype: string
    default: "samples/alder-pine/period-2"
  week_ending:
    dtype: string
    default: "2026-11-22"
card:
  usage:
    - workflow
  field: Data processing / Reports / Dashboards
---

# campaign-performance

**Which of a client's campaigns gained qualified sales at a cost worth paying?**
Put a client's ad-spend, CRM and sales exports in one folder, as CSV files
with whatever headers each tool writes. This workflow merges them into one
weekly report: spend, qualified sales, cost per qualified sale and margin
after spend for each campaign, and whether to scale, hold or cut it.

[`sources.json`](sources.json) says which headers each tool writes, how it
writes dates, and in what currency. The folder's `client.json` names the
client, the report currency and the target cost per qualified sale. Amounts
are converted at the rates in the folder's rate file; nothing is fetched and
nothing leaves the machine.

Put last week's report in the folder as `previous-report.json` and the report
also says which recommendations changed since, and whether a corrected export
or the new week changed them. The folder is read on every run, and every
step after that is cached: replace one export and only that file is decoded
again before the report reruns. A row that can't be
used is listed under review, never guessed.

```mdb-wire
import collect
import per_file
import report

collect.exports -> per_file.exports

per_file.files -> report.files
@in.sources -> report.sources
collect.client -> report.client
collect.previous -> report.previous

report.report -> @out.report
```

## Try it

```sh
mdb run reports/campaign-performance --preset reports/campaign-performance/presets/period-1.yaml
mdb run reports/campaign-performance --preset reports/campaign-performance/presets/period-2.yaml
```

The [samples](samples/) are invented exports for Alder & Pine Outfitters over
two weeks. In period 2 the folder holds period 1's report, a new week of
exports and a corrected sales export from three weeks back: one refund grew,
and Shopping - Boots moves from scale to cut. `presets/harbor-lane.yaml` runs a
second client whose report is in euros.

To see the report, open the folder in `mdb ui` and pick the Site tab.

A built site carries the run history of the project it is built from, so
give each client their own project before you send one a copy: a folder with
an `mdblocks.toml`, a copy of this workflow and that client's preset. Then
build the dated copy after their run:

```sh
mkdir -p clients/harbor-lane && cd clients/harbor-lane
printf '[project]\nid = "harbor-lane"\n' > mdblocks.toml
cp -R ../../reports/campaign-performance campaign-performance
mdb run campaign-performance --preset campaign-performance/presets/harbor-lane.yaml
mdb site build campaign-performance -o sites/2026-11-22
```

To use your own exports, make a folder per client with a `client.json` like
the samples', set `folder` and `week_ending` in a preset, and edit the headers
in `sources.json` to match your tools. Keep each report for next week, from
the client's project:

```sh
cp "$(mdb runs show latest --workflow campaign-performance --block report --port report --path)" <client folder>/previous-report.json
```
