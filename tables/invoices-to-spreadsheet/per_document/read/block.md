---
mdblocks: 1
kind: leaf
execution: transform
ports:
  in:
    documents: Files
  out:
    text: Json
env:
  requires_python: ">=3.11"
  python:
    - "pypdfium2>=5.15"
    - "rapidocr-onnxruntime>=1.4.4"
    - "pillow>=12"
    - "numpy>=2"
code:
  lang: python
  entry: read.py
---

# read

The text of each page. A PDF page with a text layer is read from it. A page
with none, and any image file, is read by OCR (RapidOCR, which runs on the CPU
and ships its models in the package). OCR drops the spaces inside a text box,
so they are put back where two characters sit further apart than usual.
