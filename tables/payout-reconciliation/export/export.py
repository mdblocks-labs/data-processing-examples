"""export.py — the reconciliation's evidence and exceptions as CSV."""

import csv
import io
import re

EVIDENCE = ("month", "status", "file", "row", "source", "kind", "id", "date", "amount", "processor",
            "payout_id", "payout_date", "description", "bank_file", "bank_row")
EXCEPTIONS = ("month", "side", "status", "processor", "payout_id", "date", "expected", "deposit",
              "difference", "bank_file", "bank_row", "description")
OPEN = {"amount differs", "no deposit", "ambiguous", "dates differ", "no payout"}


def money(value):
    if value is None:
        return ""
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value) // 100}.{abs(value) % 100:02d}"


def cell(value):
    """Text a spreadsheet would run as a formula gets a leading quote; numbers stay as they are."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") \
            and not re.fullmatch(r"-?\d+\.\d\d", value):
        return "'" + value
    return value


def table(header, rows):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([cell(row.get(col)) for col in header] for row in rows)
    return out.getvalue().encode("utf-8")


def run(report):
    """Write the two CSV files.

    Args:
        report: Json — `reconcile`'s report.

    Returns:
        {"evidence": bytes, "exceptions": bytes}
    """
    evidence = [{**r, "amount": money(r["amount"])} for r in report["evidence"]]
    bank = {(r["file"], r["row"]): r for r in report["evidence"] if r["kind"] == "bank"}
    payouts = {(p["processor"], p["payout_id"]): p for p in report["payouts"]}
    exceptions = []
    for p in report["payouts"]:
        if p["status"] in OPEN:
            b = p["bank"] or {}
            exceptions.append({
                "month": p["month"], "side": "payout", "status": p["status"], "processor": p["processor"],
                "payout_id": p["payout_id"], "date": p["date"], "expected": money(p["amount"]),
                "deposit": money(b.get("amount")), "difference": money(p["difference"]),
                "bank_file": b.get("file"), "bank_row": b.get("row"),
                "description": bank[(b["file"], b["row"])]["description"] if b else None,
            })
    for (file, row), b in bank.items():
        if b["status"] in OPEN:
            p = payouts.get((b["processor"], b["payout_id"])) or {}
            exceptions.append({
                "month": b["month"], "side": "deposit", "status": b["status"], "processor": b["processor"],
                "payout_id": b["payout_id"], "date": b["date"], "expected": money(p.get("amount")),
                "deposit": money(b["amount"]), "difference": money(p.get("difference")),
                "bank_file": file, "bank_row": row, "description": b["description"],
            })
    exceptions.sort(key=lambda e: (e["month"], e["side"] != "payout", e["date"], e["processor"] or "",
                                   e["payout_id"] or "", e["bank_file"] or "", e["bank_row"] or 0))
    return {"evidence": table(EVIDENCE, evidence), "exceptions": table(EXCEPTIONS, exceptions)}
