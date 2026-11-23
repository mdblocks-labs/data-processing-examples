"""extract.py — one invoice record per document, from its text and the schema.

Each field is the first capture group of its pattern, searched line by line
(multiline mode). The subtotal, tax and total are always money and are searched
only from the line that ends the items onward, so text above or inside the items
can't supply them; the schema sets only their patterns. A field's
`reject` pattern, tried on the value with spaces removed, turns a match into a
missing value. Line items are the lines between the `start` and `end` patterns
that match the line pattern.

OCR can split a word ("D ate"): on an OCR'd page a field that is not found is
searched again with single spaces removed, and its value is taken from the
original text. On an OCR'd page every line-item field must also start a new
column (two spaces); a page read from its text layer has no such rule.

Nothing is guessed. An amount must be well formed (thousands grouped by commas,
at most two decimals) and fit the tables; a quantity must be a whole number that
fits. The totals are always checked: if the subtotal, tax or total can't be read,
that is a problem too. Every problem sends the record to review.
"""

import re
from datetime import datetime
from decimal import Decimal

# The largest amount the tables hold, decimal(12, 2), and the largest quantity, int32.
MAX_MONEY = Decimal("9999999999.99")
MAX_QUANTITY = 2**31 - 1
MONEY = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?")
TOTALS = ("subtotal", "tax", "total")


def field_type(name, rule):
    return "money" if name in TOTALS else rule.get("type", "string")


def run(text, schema):
    """Extract a record from each document's text.

    Args:
        text: Json — `per_document`'s output: per file, a list of
            `{file, method, pages, page_methods, error}`.
        schema: Json — field patterns, date formats and the line-item rule.

    Returns:
        {"records": list} — per file: its fields, line items and problems.
    """
    docs = [doc for piece in text for doc in piece]
    return {"records": [record(doc, schema) for doc in docs]}


def record(doc, schema):
    if doc.get("error"):
        return {"file": doc["file"], "method": doc["method"],
                "fields": {name: None for name in schema["fields"]}, "line_items": [],
                "problems": [f"file not read: {doc['error']}"]}
    lines = [(line, method == "ocr")
             for page, method in zip(doc["pages"], doc["page_methods"], strict=True)
             for line in page.splitlines()]
    body = "\n".join(line for line, _ in lines)
    summary = summary_text(lines, schema["line_items"])
    ocr = "ocr" in doc["method"]
    fields, problems = {}, []
    for name, rule in schema["fields"].items():
        text = summary if name in TOTALS else body
        match = re.search(rule["pattern"], text, re.MULTILINE)
        raw = match.group(1) if match else None
        if match is None and ocr:
            raw = split_label(rule["pattern"], text, name, problems)
        if raw is not None:
            raw = raw.strip() or None  # a blank value is a missing one
        if raw is not None and rule.get("reject") and re.search(rule["reject"], re.sub(r"\s", "", raw)):
            raw = None
        kind = field_type(name, rule)
        value = convert(raw, kind, schema)
        if raw is not None and value is None:
            problems.append(f"{name}: cannot read {raw!r} as {kind}")
        elif value is None and rule.get("required"):
            problems.append(f"{name}: not found")
        fields[name] = value
    items = line_items(lines, schema["line_items"], problems)
    check(fields, items, problems)
    return {"file": doc["file"], "method": doc["method"], "fields": fields,
            "line_items": items, "problems": problems}


def summary_text(lines, rule):
    """The text from the line that ends the items onward, found after the item
    header, or anywhere if OCR missed the header; nothing if there is no such line."""
    start = next((i for i, (line, _) in enumerate(lines) if re.search(rule["start"], line)), -1)
    end = next((i for i in range(start + 1, len(lines)) if re.search(rule["end"], lines[i][0])), None)
    return "" if end is None else "\n".join(line for line, _ in lines[end:])


def split_label(pattern, text, name, problems):
    """Find the field with single spaces removed, then take its value from the
    original text, so "Northwind Office Supply" keeps its spaces. A value the
    pattern no longer accepts with its spaces back is a problem."""
    keep = [i for i, ch in enumerate(text)
            if not (ch == " " and 0 < i < len(text) - 1 and not text[i - 1].isspace() and not text[i + 1].isspace())]
    squeezed = "".join(text[i] for i in keep)
    match = re.search(pattern, squeezed, re.MULTILINE)
    if match is None:
        return None
    if match.end(1) == match.start(1):
        return ""
    value = text[keep[match.start(1)]:keep[match.end(1) - 1] + 1]
    again = re.search(pattern, squeezed[match.start():match.start(1)] + value, re.MULTILINE)
    if again is None or again.group(1) != value:
        problems.append(f"{name}: OCR split {value!r}")
        return None
    return value


def convert(raw, kind, schema):
    if raw is None:
        return None
    if kind == "money":
        if not MONEY.fullmatch(raw):
            return None
        value = Decimal(raw.replace(",", ""))
        return f"{value:.2f}" if value <= MAX_MONEY else None
    if kind == "date":
        squeezed = raw.replace(" ", "")
        for fmt in schema["date_formats"]:
            for value, form in ((raw, fmt), (squeezed, fmt.replace(" ", ""))):
                try:
                    return datetime.strptime(value, form).date().isoformat()
                except ValueError:
                    pass
        return None
    return raw


def line_items(lines, rule, problems):
    items, inside = [], False
    for line, ocr in lines:
        if not inside:
            inside = re.search(rule["start"], line) is not None
            continue
        if re.search(rule["end"], line):
            break
        text = line.strip()
        match = re.match(rule["pattern"], text)
        if not match:
            if text:
                problems.append(f"line not read: {text!r}")
            continue
        if any(match[name] is None for name in ("description", "quantity", "unit_price", "amount")):
            problems.append(f"line not read, a value is missing: {text!r}")
            continue
        if ocr and not columns(text, match):
            problems.append(f"line not read, a column is missing: {text!r}")
            continue
        unit_price, amount = convert(match["unit_price"], "money", {}), convert(match["amount"], "money", {})
        quantity = match["quantity"]
        if unit_price is None or amount is None:
            problems.append(f"line not read, an amount is malformed or too large: {text!r}")
            continue
        if not re.fullmatch(r"[0-9]{1,10}", quantity) or int(quantity) > MAX_QUANTITY:
            problems.append(f"line not read, the quantity is not a whole number in range: {text!r}")
            continue
        item = {"description": match["description"].strip(), "quantity": int(quantity),
                "unit_price": unit_price, "amount": amount}
        if Decimal(unit_price) * item["quantity"] != Decimal(amount):
            problems.append(f"line {item['description']!r}: {quantity} x {unit_price} is not {amount}")
        items.append(item)
    if not inside:
        # An unread item section must not pass as a verified sum of zero.
        problems.append("item header not found, so no line items were read")
    return items


def columns(line, match):
    """On an OCR'd line, columns are joined by two spaces: each field after the
    first must begin one, so "Zone 1  10.00  10.00" is not read as quantity 1."""
    names = sorted((n for n in match.re.groupindex if match.start(n) >= 0), key=match.start)
    return all("  " in line[match.end(a):match.start(b)] for a, b in zip(names, names[1:]))


def check(fields, items, problems):
    """The totals are checked, or the record says why they couldn't be. A schema
    without a `subtotal`, `tax` or `total` field leaves every record unchecked."""
    missing = [name for name in TOTALS if fields.get(name) is None]
    if missing:
        problems.append(f"totals not checked: {', '.join(missing)} not read")
        return
    subtotal, tax, total = (Decimal(fields[name]) for name in TOTALS)
    lines_sum = sum((Decimal(i["amount"]) for i in items), Decimal("0.00"))
    if lines_sum != subtotal:
        problems.append(f"line items add up to {lines_sum}, subtotal is {subtotal}")
    if subtotal + tax != total:
        problems.append(f"subtotal {subtotal} + tax {tax} is {subtotal + tax}, total is {total}")
