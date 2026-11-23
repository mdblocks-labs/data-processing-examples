"""Write the synthetic sample invoices in `invoices/` and their expected fields.

Every vendor, customer and amount here is invented. Run from this folder:

    uv run --python 3.13 --with reportlab==5.1.0 --with pypdfium2==5.15.2 \
        --with pillow==13.0.0 python generate.py

Most samples are digital PDFs with a text layer. Two are made to look scanned
(an image-only PDF, slightly rotated, with noise) and one is a phone-style PNG,
so the workflow's OCR path runs too. One invoice's total is wrong on purpose.
"""

import csv
import io
import random
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
OUT = HERE / "invoices"

VENDORS = [
    ("Northwind Office Supply", "Invoice No"),
    ("Bluebird Cloud Services", "Invoice Number"),
    ("Harbor Freight Logistics", "Invoice No"),
    ("Juniper Design Studio", "Invoice Number"),
]
ITEMS = [
    ("Printer paper A4, box of 5", Decimal("24.90")),
    ("Toner cartridge black", Decimal("68.00")),
    ("Cloud hosting, October", Decimal("310.00")),
    ("Backup storage 500 GB", Decimal("45.00")),
    ("Pallet shipping, zone 2", Decimal("128.50")),
    ("Customs handling fee", Decimal("35.00")),
    ("Logo design revision", Decimal("220.00")),
    ("Brand guidelines document", Decimal("480.00")),
    ("Desk chair, ergonomic", Decimal("189.99")),
]
DATE_STYLES = ["%Y-%m-%d", "%d %b %Y", "%B %d, %Y"]


def money(value):
    return f"{value:,.2f}"


def invoice(seq, rng):
    vendor, label = VENDORS[seq % len(VENDORS)]
    lines = []
    for description, price in rng.sample(ITEMS, rng.randint(2, 4)):
        quantity = rng.randint(1, 6)
        lines.append((description, quantity, price, price * quantity))
    subtotal = sum(line[3] for line in lines)
    tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
    from datetime import date, timedelta

    issued = date(2026, 9, 1) + timedelta(days=7 * seq)
    return {
        "vendor": vendor,
        "label": label,
        "number": f"INV-2026-{1040 + seq:04d}",
        "issued": issued,
        "due": issued + timedelta(days=30),
        "date_style": DATE_STYLES[seq % len(DATE_STYLES)],
        "lines": lines,
        "subtotal": subtotal,
        "tax": tax,
        "total": subtotal + tax,
    }


def draw(inv, printed_total):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    c.setTitle(inv["number"])
    width, height = A4
    y = height - 60
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, inv["vendor"])
    c.setFont("Helvetica", 11)
    c.drawString(50, y - 18, "12 Example Street, Springfield")
    fmt = inv["date_style"]
    rows = [
        (f"{inv['label']}:", inv["number"]),
        ("Invoice Date:", inv["issued"].strftime(fmt)),
        ("Due Date:", inv["due"].strftime(fmt)),
        ("Currency:", "USD"),
    ]
    for i, (key, value) in enumerate(rows):
        c.drawString(350, y - 60 - 18 * i, key)
        c.drawString(460, y - 60 - 18 * i, value)
    c.drawString(50, y - 60, "Bill To: Acme Analytics LLC")
    y -= 170
    c.setFont("Helvetica-Bold", 11)
    for x, text in [(50, "Description"), (330, "Qty"), (400, "Unit Price"), (490, "Amount")]:
        c.drawString(x, y, text)
    c.setFont("Helvetica", 11)
    for description, quantity, price, amount in inv["lines"]:
        y -= 22
        c.drawString(50, y, description)
        c.drawRightString(350, y, str(quantity))
        c.drawRightString(460, y, money(price))
        c.drawRightString(545, y, money(amount))
    y -= 40
    for key, value in [("Subtotal:", inv["subtotal"]), ("Tax (8%):", inv["tax"]), ("Total:", printed_total)]:
        c.drawString(400, y, key)
        c.drawRightString(545, y, money(value))
        y -= 20
    c.drawString(50, 80, "Thank you for your business. Payment terms: net 30.")
    c.showPage()
    c.save()
    return buf.getvalue()


def scanned(pdf_bytes, rng, angle):
    page = pdfium.PdfDocument(pdf_bytes)[0]
    img = page.render(scale=200 / 72).to_pil().convert("L")
    img = img.rotate(angle, expand=True, fillcolor=255, resample=Image.BICUBIC)
    w, h = img.size
    noise = Image.frombytes("L", (w, h), rng.randbytes(w * h)).point(lambda v: 255 if v > 2 else 200)
    img = Image.composite(img, noise, img.point(lambda v: 255 if v < 250 else 0))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def image_pdf(img):
    """An image-only PDF page, written reproducibly."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    jpeg = io.BytesIO()
    img.save(jpeg, format="JPEG", quality=80)
    c.drawImage(ImageReader(io.BytesIO(jpeg.getvalue())), 0, 0, *A4)
    c.showPage()
    c.save()
    return buf.getvalue()


def main():
    rng = random.Random(20261120)
    OUT.mkdir(exist_ok=True)
    expected = []
    for seq in range(9):
        inv = invoice(seq, rng)
        wrong_total = seq == 5
        printed = inv["total"] + Decimal("10.00") if wrong_total else inv["total"]
        pdf = draw(inv, printed)
        stem = f"{seq + 1:02d}-{inv['vendor'].split()[0].lower()}"
        if seq in (3, 7):
            img = scanned(pdf, rng, angle=0.8 if seq == 3 else -0.6)
            name = f"{stem}-scan.pdf"
            (OUT / name).write_bytes(image_pdf(img))
        elif seq == 8:
            name = f"{stem}-photo.png"
            scanned(pdf, rng, angle=0.4).save(OUT / name, optimize=True)
        else:
            name = f"{stem}.pdf"
            (OUT / name).write_bytes(pdf)
        expected.append({
            "file": name,
            "vendor": inv["vendor"],
            "invoice_number": inv["number"],
            "invoice_date": inv["issued"].isoformat(),
            "due_date": inv["due"].isoformat(),
            "currency": "USD",
            "subtotal": f"{inv['subtotal']:.2f}",
            "tax": f"{inv['tax']:.2f}",
            "total": f"{printed:.2f}",
            "line_items": len(inv["lines"]),
            "total_is_wrong": "true" if wrong_total else "false",
        })
    with open(HERE / "expected.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(expected[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(expected)


if __name__ == "__main__":
    main()
