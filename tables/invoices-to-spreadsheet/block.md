---
mdblocks: 1
kind: composite
ports:
  in:
    schema: Json
  out:
    invoices: Table
    line_items: Table
    review: Table
    workbook: Bytes
params:
  folder:
    dtype: string
    default: "samples/invoices"
card:
  field: Data processing / Tables / Extraction
---

# invoices-to-spreadsheet

**Turn a folder of invoices, PDFs or scans, into one spreadsheet.** Each file
is read once: a digital PDF from its text layer, a scan or photo by OCR on your
own machine. Then the fields in [`schema.json`](schema.json) are pulled out by
pattern. You get a table of invoices, a table of line items, a review table and
an Excel workbook holding all three.

Nothing leaves the machine and nothing is guessed. A file goes to `review` when
a required field is missing, a line's quantity times its price isn't its
amount, the lines don't add up to the subtotal, or the subtotal plus tax isn't
the total.

Every step is cached by its inputs. Add ten invoices to a folder of a thousand
and only those ten are read; edit a pattern in the schema and only extraction
reruns.

```mdb-wire
import assemble
import collect
import export
import extract
import per_document

collect.documents -> per_document.documents

per_document.text -> extract.text
@in.schema -> extract.schema
@in.schema -> assemble.schema
extract.records -> assemble.records

assemble.invoices -> export.invoices
assemble.line_items -> export.line_items
assemble.review -> export.review

assemble.invoices -> @out.invoices
assemble.line_items -> @out.line_items
assemble.review -> @out.review
export.workbook -> @out.workbook
```

## Try it

```sh
mdb run tables/invoices-to-spreadsheet --preset tables/invoices-to-spreadsheet/presets/samples.yaml
```

The [samples](samples/) are nine invented invoices: six digital PDFs, two scans
and a phone photo. One has a total that doesn't add up, so it lands in
`review`. To use your own, set the `folder` param to your folder (under
`params:` in a preset) and, if your invoices use other labels, edit the
patterns in `schema.json`.

To see the results, open the folder in `mdb ui` and pick the Site tab, or
build a static copy with `mdb site build tables/invoices-to-spreadsheet -o out`. The
page shows the counts, the review list and every invoice; the workbook is the
`workbook` output.
