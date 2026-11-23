# Example mdBlocks workflows for data processing

Each example is one workflow you can run, read and copy, in a folder by
domain, then application.

| Example | Domain / Application | What it does |
|---|---|---|
| [Documents to table](tables/extraction/documents_to_table/) | Tables / Extraction | Reads invoices from their text layer or by OCR, pulls out the fields a schema file describes, checks the totals, and writes tables of invoices, line items and records to review, plus an Excel workbook. |

## Try one

You need [mdBlocks](https://mdblocks.com) and [uv](https://docs.astral.sh/uv/). From the
repository root:

```sh
mdb run tables/extraction/documents_to_table --preset tables/extraction/documents_to_table/presets/samples.yaml
```

The sample invoices are invented. Each workflow's `block.md` explains what it does, what it
promises and how to use your own files.

## Licence

MIT. See [LICENSE](LICENSE).
