---
mdblocks: 1
type: mdblocks/block
kind: leaf
execution: transform
ports:
  in:
    text: Json
    schema: Json
  out:
    records: Json
code:
  lang: python
  entry: extract.py
---

# extract

One record per file, from the text `per_document` gathered: each field is the first match of its pattern in the
schema, dates become `YYYY-MM-DD`, and amounts become exact decimals. Line
items are the lines between the `start` and `end` patterns that match the line
pattern.

Every disagreement becomes a problem on the record: a required field that
isn't found, a line whose quantity times price isn't its amount, line items
that don't add up to the subtotal, or a subtotal and tax that don't make the
total. It uses only Python's standard library, and takes milliseconds a file, so it
runs once over all the text: a schema change reruns it and never `read`.
