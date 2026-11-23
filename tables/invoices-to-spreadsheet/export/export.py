"""export.py — the three tables as one Excel workbook."""

import io
import re
import zipfile
from datetime import datetime

import pyarrow as pa
from openpyxl import Workbook

FIXED = datetime(2026, 1, 1)

# Characters XML 1.0 can't store (from a filename, a PDF's text layer or the schema).
NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def clean(value):
    return NOT_XML.sub("", value) if isinstance(value, str) else value


def run(invoices, line_items, review):
    """Write each table as a sheet.

    Args:
        invoices, line_items, review: Table — `assemble`'s outputs.

    Returns:
        bytes — the `.xlsx` workbook.
    """
    book = Workbook()
    book.remove(book.active)
    for title, table in (("Invoices", invoices), ("Line items", line_items), ("Review", review)):
        sheet = book.create_sheet(title)
        sheet.append([clean(v) for v in table.column_names])
        for row in table.to_pylist():
            sheet.append([clean(v) for v in row.values()])
        for index, field in enumerate(table.schema, start=1):
            cells = [c for (c,) in sheet.iter_rows(min_row=2, min_col=index, max_col=index)]
            for cell in cells:
                if pa.types.is_string(field.type) and cell.value is not None:
                    # Text from a document stays text: "=1+1" is not a formula.
                    cell.data_type = "s"
                elif pa.types.is_date(field.type):
                    cell.number_format = "yyyy-mm-dd"
                elif pa.types.is_decimal(field.type):
                    cell.number_format = "#,##0.00"
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = max(len(str(cell.value or "")) for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 60)
    book.properties.created = book.properties.modified = FIXED
    return reproducible(book)


def reproducible(book):
    """Save, then rewrite the zip with fixed entry times, so equal tables give equal bytes."""
    raw = io.BytesIO()
    book.save(raw)
    out = io.BytesIO()
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=FIXED.timetuple()[:6])
            fixed.compress_type = zipfile.ZIP_DEFLATED
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl stamps the save time here, whatever `modified` says.
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2026-01-01T00:00:00Z", data)
            dst.writestr(fixed, data)
    return out.getvalue()
