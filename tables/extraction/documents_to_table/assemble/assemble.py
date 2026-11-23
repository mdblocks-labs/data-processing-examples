"""assemble.py — the extracted records as three tables."""

from datetime import date
from decimal import Decimal

import pyarrow as pa

MONEY = pa.decimal128(12, 2)
TOTALS = ("subtotal", "tax", "total")  # always money, as in extract
TYPES = {"money": MONEY, "date": pa.date32(), "string": pa.string()}


def run(records, schema):
    """Lay the records out as invoices, line items and review rows.

    Args:
        records: Json — `extract`'s output: one record per file.
        schema: Json — the fields, whose order and types give the invoice columns.

    Returns:
        {"invoices": Table, "line_items": Table, "review": Table}
    """
    clash = {"file", "read_by", "line_items", "needs_review"} & set(schema["fields"])
    if clash:
        raise ValueError(f"schema fields {sorted(clash)} are the names of built-in invoice columns; rename them")
    FIELDS = [(name, TYPES["money" if name in TOTALS else rule.get("type", "string")]) for name, rule in schema["fields"].items()]
    invoices = {"file": [], "read_by": []}
    invoices.update({name: [] for name, _ in FIELDS})
    invoices.update({"line_items": [], "needs_review": []})
    items = {k: [] for k in ("file", "invoice_number", "description", "quantity", "unit_price", "amount")}
    review = {"file": [], "invoice_number": [], "problem": []}
    for r in records:
        f = r["fields"]
        invoices["file"].append(r["file"])
        invoices["read_by"].append(r["method"])
        for name, kind in FIELDS:
            invoices[name].append(convert(f.get(name), kind))
        invoices["line_items"].append(len(r["line_items"]))
        invoices["needs_review"].append(bool(r["problems"]))
        for item in r["line_items"]:
            items["file"].append(r["file"])
            items["invoice_number"].append(f.get("invoice_number"))
            items["description"].append(item["description"])
            items["quantity"].append(item["quantity"])
            items["unit_price"].append(Decimal(item["unit_price"]))
            items["amount"].append(Decimal(item["amount"]))
        for problem in r["problems"]:
            review["file"].append(r["file"])
            review["invoice_number"].append(f.get("invoice_number"))
            review["problem"].append(problem)
    schema = pa.schema([("file", pa.string()), ("read_by", pa.string()), *FIELDS,
                        ("line_items", pa.int32()), ("needs_review", pa.bool_())])
    item_schema = pa.schema([("file", pa.string()), ("invoice_number", pa.string()),
                             ("description", pa.string()), ("quantity", pa.int32()),
                             ("unit_price", MONEY), ("amount", MONEY)])
    review_schema = pa.schema([("file", pa.string()), ("invoice_number", pa.string()),
                               ("problem", pa.string())])
    return {
        "invoices": pa.Table.from_pydict(invoices, schema=schema),
        "line_items": pa.Table.from_pydict(items, schema=item_schema),
        "review": pa.Table.from_pydict(review, schema=review_schema),
    }


def convert(value, kind):
    if value is None:
        return None
    if kind == pa.date32():
        return date.fromisoformat(value)
    if kind == MONEY:
        return Decimal(value)
    return value
