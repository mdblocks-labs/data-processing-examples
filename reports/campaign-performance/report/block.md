---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    files: Json
    sources: Json
    client: Json
    previous: Json
  out:
    report: Json
params:
  week_ending:
    dtype: string
code:
  lang: python
  entry: report.py
---

# report

Matches each export to the source in `sources.json` whose headers it carries,
parses its dates and amounts, and converts amounts to the client's currency at
the latest rate on or before each row's date. Over the 28 days ending
`week_ending`, it gives each campaign its spend, qualified sales (sales whose
deal is on a CRM lead marked won, unless refunded in full), cost per qualified
sale and margin after spend, and recommends:

- **cut** when margin after spend is below zero;
- **scale** when there is a sale, cost per qualified sale is at or under the
  client's target, and margin after spend is above zero;
- **hold** otherwise.

Given last period's report, it works that period out again from today's files,
so each changed recommendation says whether a corrected export or the new week
changed it. Every row it can't use is listed under `review` with its file and
row. It uses only Python's standard library and runs in milliseconds, so a
change to `sources.json` reruns it and never `read`.
