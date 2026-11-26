"""record.py — the approved months `approved_totals` doesn't hold yet, and the site's view of the rest."""

from datetime import date

import pyarrow as pa

TOTALS = ("payouts", "paid_out", "orders", "refunds", "fees", "deposits", "deposited", "matched",
          "open_payouts", "open_deposits", "in_transit")
SCHEMA = pa.schema(
    [("month", pa.string()), ("checksum", pa.string()), ("approved_by", pa.string()),
     ("approved_on", pa.date32()), ("currency", pa.string())]
    + [(name, pa.int64()) for name in TOTALS])


def run(report, history):
    """Rows for each approved month whose checksum is not its last in `history`, and `kept`.

    Args:
        report: Json — `reconcile`'s report.
        history: Table — `approved_totals` as bound at the run's start.
    """
    latest = {}
    for row in history.to_pylist():
        latest[str(row["month"])] = row
    last = {month: str(row["checksum"]) for month, row in latest.items()}
    rows = []
    for m in report["months"]:
        if m["status"] != "approved" or last.get(m["month"]) == m["checksum"]:
            continue
        approval = max((a for a in m["approvals"] if a["current"]), key=lambda a: (a["approved_on"], a["row"]))
        rows.append({"month": m["month"], "checksum": m["checksum"], "approved_by": approval["approved_by"],
                     "approved_on": date.fromisoformat(approval["approved_on"]), "currency": report["currency"],
                     **{name: m["totals"][name] for name in TOTALS}})
    # What the site may show of a month this run found no rows for: its last row, no checksum.
    found = {m["month"] for m in report["months"]}
    kept = [{"month": month, "approved_by": row["approved_by"], "approved_on": str(row["approved_on"]),
             "currency": row["currency"], "totals": {name: row[name] for name in TOTALS}}
            for month, row in sorted(latest.items()) if month not in found]
    return {"rows": pa.Table.from_pylist(rows, schema=SCHEMA), "kept": kept}
