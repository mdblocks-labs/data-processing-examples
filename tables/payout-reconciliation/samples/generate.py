"""Write the synthetic sample exports for one invented merchant.

Every merchant, ID and amount here is invented. Run from this folder with
Python 3.11 or newer (standard library only):

    python3 generate.py

Lantern & Loom Candle Co. sells through a card processor and a marketplace
and banks with one account, in USD.

- The card processor writes ISO dates and negative refunds and fees, and pays
  out every Monday and Thursday; the bank description carries the payout ID.
- The marketplace writes US dates and positive refunds and fees (`negate` in
  `sources.json`), and settles every other Saturday; its deposits carry no
  settlement ID, so they are tied by amount and date.

`period-1` holds the exports pulled on 2026-11-02, bank rows through that day.
It seeds: a card deposit short of its payout by a fee, a marketplace refund
missing from the export (so a settlement and its deposit disagree), a deposit
no payout explains, a partial refund, a settlement on 2026-10-31 deposited in
November, a card payout still in transit, a pending bank row with no date, and
orders not paid out yet.

`period-2` is the exports pulled on 2026-11-20, bank rows through 2026-11-19,
with the marketplace refunds export for October corrected and `approvals.csv`
approving October twice: once with period 1's checksum, now out of date, and
once with period 2's. The checksums come from the workflow's own `read` and
`reconcile` code.
"""

import csv
import importlib.util
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
WORKFLOW = HERE.parent
START = date(2026, 10, 1)
MERCHANT = {"name": "Lantern & Loom Candle Co.", "currency": "USD", "match_days": 3}
CARD_PRICES = [1800, 2450, 3200, 4675, 1225, 5800, 2900]
MARKET_PRICES = [3650, 2200, 4100, 1575, 2875]
# Each period: the day the exports were pulled and the bank's last posted day.
PERIODS = {"period-1": (date(2026, 11, 2), date(2026, 11, 2)),
           "period-2": (date(2026, 11, 20), date(2026, 11, 19))}
SHORT_PAYOUT = date(2026, 10, 15)        # its deposit is 3.50 short
MISSING_REFUND = "MR-5003"               # left out of period 1's marketplace refunds


def money(cents):
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def us(day):
    return day.strftime("%m/%d/%Y")


def days(first, last):
    return [first + timedelta(days=k) for k in range((last - first).days + 1)]


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def by_month(rows, day_of):
    months = {}
    for row in rows:
        months.setdefault(day_of(row).strftime("%Y-%m"), []).append(row)
    return months


def card(pulled):
    """Charges, refunds and fees, each with the payout that paid it once it is paid out."""
    payout_days = [d for d in days(START, pulled) if d.weekday() in (0, 3)]
    ids = {d: f"PO-C{1001 + k}" for k, d in enumerate(payout_days)}

    def payout(day):
        # The first payout after the day it happened.
        return next((p for p in payout_days if p > day), None)

    charges, refunds = [], []
    for k, day in enumerate(days(START, pulled)):
        for n in range(1 + k % 3):
            charges.append({"id": f"ch_{k:03d}{n}", "day": day, "cents": CARD_PRICES[(k * 3 + n) % 7]})
    full = charges[10]
    partial = charges[37]
    refunds.append({"id": "re_0001", "day": full["day"] + timedelta(days=3), "cents": -full["cents"]})
    refunds.append({"id": "re_0002", "day": partial["day"] + timedelta(days=2), "cents": -1000})
    refunds.append({"id": "re_0003", "day": date(2026, 11, 10), "cents": -2450})
    refunds = [r for r in refunds if r["day"] <= pulled]
    for row in charges + refunds:
        row["payout"] = payout(row["day"])
    fees = []
    for day in payout_days:
        paid = [c for c in charges if c["payout"] == day]
        if paid:
            cents = sum((c["cents"] * 29 + 500) // 1000 + 30 for c in paid)
            fees.append({"id": f"fee_{ids[day][3:]}", "day": day, "cents": -cents, "payout": day})
    totals = {}
    for row in charges + refunds + fees:
        if row["payout"]:
            totals[row["payout"]] = totals.get(row["payout"], 0) + row["cents"]
    return charges, refunds, fees, ids, totals


def market(pulled):
    """Orders, refunds and fees; a settlement every other Saturday from 2026-10-03."""
    settle_days = [d for d in days(START, pulled) if d.weekday() == 5 and (d - date(2026, 10, 3)).days % 14 == 0]
    ids = {d: f"MS-{3001 + k}" for k, d in enumerate(settle_days)}

    def settlement(day):
        return next((s for s in settle_days if s > day), None)

    orders = [{"id": f"MO-{7001 + k}", "day": day, "cents": MARKET_PRICES[k % 5]}
              for k, day in enumerate(days(START, pulled - timedelta(days=1)))]
    refunds = [{"id": "MR-5001", "day": date(2026, 10, 8), "cents": 2200},
               {"id": "MR-5002", "day": date(2026, 10, 12), "cents": 1575},
               {"id": MISSING_REFUND, "day": date(2026, 10, 14), "cents": 4100},
               {"id": "MR-5004", "day": date(2026, 11, 6), "cents": 2875}]
    refunds = [r for r in refunds if r["day"] <= pulled]
    for row in orders + refunds:
        row["settlement"] = settlement(row["day"])
    fees = []
    for day in settle_days:
        sold = sum(o["cents"] for o in orders if o["settlement"] == day)
        if sold:
            fees.append({"id": f"MF-{ids[day][3:]}", "day": day, "cents": (sold * 12 + 50) // 100, "settlement": day})
    totals = {}
    for row in orders:
        if row["settlement"]:
            totals[row["settlement"]] = totals.get(row["settlement"], 0) + row["cents"]
    for row in refunds + fees:
        if row["settlement"]:
            totals[row["settlement"]] -= row["cents"]
    return orders, refunds, fees, ids, totals


def next_business_day(day):
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def bank(card_totals, card_ids, market_totals, through):
    rows = []
    for day, cents in card_totals.items():
        if day in card_ids:
            if day == SHORT_PAYOUT:
                cents -= 350
            rows.append((next_business_day(day), cents, f"CARD PROCESSOR TRANSFER {card_ids[day]}"))
    for day, cents in market_totals.items():
        rows.append((day + timedelta(days=2), cents, "MARKETPLACE SETTLEMENT ACH CREDIT"))
    rows.append((date(2026, 10, 21), 25000, "MOBILE CHECK DEPOSIT"))
    for day in days(START, through):
        if day.day == 1:
            rows.append((day, -180000, "RENT STUDIO 4B"))
        if day.weekday() == 3:
            rows.append((day, -8400, "WAX AND WICK SUPPLY"))
    rows = sorted((r for r in rows if r[0] <= through), key=lambda r: (r[0], r[2]))
    return [[f"TX{day:%m%d}{k:02d}", day.isoformat(), money(cents), text]
            for k, (day, cents, text) in enumerate(rows)]


def period(folder, pulled, through):
    charges, c_refunds, c_fees, card_ids, card_totals = card(pulled)
    orders, m_refunds, m_fees, market_ids, market_totals = market(pulled)
    if folder.name == "period-1":
        m_refunds = [r for r in m_refunds if r["id"] != MISSING_REFUND]
    card_header = ["Created", "Amount", "Currency", "Payout ID", "Payout Date"]

    def card_row(r):
        paid = r["payout"]
        return [r["id"], r["day"].isoformat(), money(r["cents"]), "usd",
                card_ids[paid] if paid else "", paid.isoformat() if paid else ""]

    def market_row(r):
        paid = r["settlement"]
        return [r["id"], us(r["day"]), money(r["cents"]), market_ids[paid] if paid else "", us(paid) if paid else ""]

    for name, first, rows in (("card-charges", "Charge ID", charges), ("card-refunds", "Refund ID", c_refunds),
                              ("card-fees", "Fee ID", c_fees)):
        for month, part in by_month(rows, lambda r: r["day"]).items():
            write(folder / f"{name}-{month}.csv", [first, *card_header], [card_row(r) for r in part])
    for name, header, rows in (
            ("marketplace-orders", ["Order Number", "Order Date", "Item Total"], orders),
            ("marketplace-returns", ["Return Number", "Return Date", "Refund Amount"], m_refunds),
            ("marketplace-fees", ["Fee Reference", "Fee Date", "Fee Amount"], m_fees)):
        for month, part in by_month(rows, lambda r: r["day"]).items():
            write(folder / f"{name}-{month}.csv", [*header, "Settlement ID", "Settlement Date"],
                  [market_row(r) for r in part])
    # The bank's own file per month, ending with a pending line it writes with no date.
    lines = bank(card_totals, card_ids, market_totals, through)
    for month, part in by_month(lines, lambda r: date.fromisoformat(r[1])).items():
        if month == through.strftime("%Y-%m"):
            part = part + [["TXPEND01", "Pending", "-42.18", "CARD PURCHASE PENDING"]]
        write(folder / f"bank-{month}.csv", ["Transaction ID", "Posted Date", "Amount", "Description"], part)
    (folder / "merchant.json").write_text(json.dumps(MERCHANT, indent=2) + "\n")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checksum(folder, month, sources):
    """A month's evidence checksum, as the workflow reports it for this folder."""
    read = load(WORKFLOW / "per_file/read/read.py", "read")
    reconcile = load(WORKFLOW / "reconcile/reconcile.py", "reconcile")
    files = [read.run([(p.name, p)])["files"] for p in sorted(folder.glob("*.csv")) if p.name != "approvals.csv"]
    merchant = json.loads((folder / "merchant.json").read_text())
    report = reconcile.run(files, sources, merchant, None)["report"]
    return next(m["checksum"] for m in report["months"] if m["month"] == month)


def main():
    sources = json.loads((WORKFLOW / "sources.json").read_text())
    for name, (pulled, through) in PERIODS.items():
        shutil.rmtree(HERE / name, ignore_errors=True)
        period(HERE / name, pulled, through)
    old = checksum(HERE / "period-1", "2026-10", sources)
    new = checksum(HERE / "period-2", "2026-10", sources)
    write(HERE / "period-2" / "approvals.csv", ["month", "checksum", "approved_by", "approved_on"],
          [["2026-10", old, "R. Okafor", "2026-11-03"], ["2026-10", new, "R. Okafor", "2026-11-20"]])


if __name__ == "__main__":
    main()
