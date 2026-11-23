"""read.py — the text of each document, page by page.

A PDF page with a text layer is read from it. A page without one (a scan) and an
image file are read by OCR on the CPU. OCR loses the spaces inside a text box, so
they are put back where the gap between two characters is wider than usual.
"""

from pathlib import Path
from statistics import median

import pypdfium2 as pdfium
from PIL import Image, ImageSequence

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
DPI = 200
_ocr = None


def run(documents):
    """Read every document this block was handed.

    Args:
        documents: FilesIn — `(relative_path, Path)` pairs; inside the map, one file.

    Returns:
        {"text": list} — per file: its name, how it was read, one string per page,
        how each page was read (`text` or `ocr`), and why it couldn't be read, if so.
    """
    out = []
    for name, path in documents:
        pages, page_methods, error = [], [], None
        sources = decode(name, path)
        while True:
            # Only decoding is guarded: any error there means a bad document, which goes to
            # review. A machine failure (an OSError with an errno) or an OCR error stops the run.
            try:
                source = next(sources, None)
            except Exception as exc:
                if isinstance(exc, MemoryError) or (isinstance(exc, OSError) and exc.errno is not None):
                    raise
                # The staging path changes per run; name the file instead, so equal inputs give equal outputs.
                reason = str(exc).replace(str(path), name)
                pages, page_methods, error = [], [], f"{type(exc).__name__}: {reason}"
                break
            if source is None:
                break
            method, content = source
            pages.append(ocr(content) if method == "ocr" else content)  # one page in memory at a time
            page_methods.append(method)
        method = "+".join(sorted(set(page_methods))) or ("unreadable" if error else "unsupported")
        out.append({"file": name, "method": method, "pages": pages, "page_methods": page_methods,
                    "error": error})
    return {"text": out}


def decode(name, path):
    """Yield each page as `("text", str)` or `("ocr", image)`."""
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        # Read the bytes here so a system failure raises OSError with an errno, not a pdfium error.
        for page in pdfium.PdfDocument(Path(path).read_bytes()):
            text = page.get_textpage().get_text_bounded().replace("\r\n", "\n").strip()
            yield ("text", text) if text else ("ocr", page.render(scale=DPI / 72).to_pil())
    elif suffix in IMAGE_SUFFIXES:
        # A TIFF can hold several pages; every other image is one frame. copy() decodes it.
        for frame in ImageSequence.Iterator(Image.open(path)):
            yield "ocr", frame.copy()


def ocr(image):
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR

        # A larger detector input keeps lone narrow digits, such as a quantity of 1.
        _ocr = RapidOCR(det_limit_side_len=1600)
    import numpy as np

    result, _ = _ocr(np.array(image.convert("RGB")), return_word_box=True)
    boxes = []
    for box, text, _score, chars, *_ in result or []:
        top = min(p[1] for p in box)
        bottom = max(p[1] for p in box)
        boxes.append((top, bottom, box[0][0], respace(text, chars)))
    return "\n".join(lines(boxes))


def respace(text, chars):
    """Put back the spaces OCR dropped inside one box, from its character boxes."""
    if not chars or len(chars) != len(text):
        return text
    spans = [(min(p[0] for p in c), max(p[0] for p in c)) for c in chars]
    width = median(right - left for left, right in spans) or 1
    out = text[0]
    for i in range(1, len(text)):
        if spans[i][0] - spans[i - 1][1] > 0.75 * width:
            out += " "
        out += text[i]
    return out


def lines(boxes):
    """Group boxes into lines by vertical overlap; columns are joined by two spaces."""
    rows = []
    for top, bottom, left, text in sorted(boxes):
        for row in rows:
            r_top, r_bottom = row["span"]
            overlap = min(bottom, r_bottom) - max(top, r_top)
            if overlap > 0.5 * min(bottom - top, r_bottom - r_top):
                row["items"].append((left, text))
                row["span"] = (min(top, r_top), max(bottom, r_bottom))
                break
        else:
            rows.append({"span": (top, bottom), "items": [(left, text)]})
    return ["  ".join(text for _, text in sorted(row["items"])) for row in rows]
