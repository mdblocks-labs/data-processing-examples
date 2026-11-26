"""Write the synthetic sample exports for two invented clients.

Every client, campaign, lead and amount here is invented. Run from this folder
with Python 3.11 or newer (standard library only):

    python3 generate.py

Alder & Pine Outfitters (report in USD) gets two folders. `period-1` holds the
weeks ending 2026-10-25 to 2026-11-15. `period-2` is one week later: a new week
of exports, the sales export for the week ending 2026-11-08 corrected (one
large boots order was returned in full), a Meta export that stops a day early,
and period 1's report as `previous-report.json`, made by the workflow's own
`read` and `report` code. Harbor Lane Dental (report in EUR) gets one period
and its own `sources.json`, since it runs no Meta ads.
"""

import csv
import importlib.util
import json
import shutil
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).parent
WORKFLOW = HERE.parent
WEEKS = [date(2026, 10, 25) + timedelta(days=7 * k) for k in range(5)]  # Sundays

# Per campaign: platform, daily spend (in the platform's currency), qualified
# sales per week (W43..W47), revenue and cost of goods per sale, in USD.
ALDER = {
    "Search - Brand": ("google", "41.50", [4, 4, 5, 4, 4], "182.00", "91.00"),
    "Search - Tents": ("google", "88.00", [3, 2, 3, 3, 5], "264.00", "148.00"),
    "Shopping - Boots": ("google", "62.25", [4, 4, 4, 5, 4], "219.00", "112.00"),
    "Prospecting - Spring": ("meta", "34.00", [1, 2, 2, 1, 4], "318.00", "112.00"),
    "Retargeting - Cart": ("meta", "14.80", [5, 6, 5, 5, 6], "128.00", "57.00"),
}
# The boots order in the week ending 2026-11-08 that period 2's export shows returned.
BIG_ORDER = ("Shopping - Boots", 2, "1,480.00", "655.00")

HARBOR = {
    "Search - Implants": ("google", "120.00", [0, 0, 1, 2, 1], "2450.00", "980.00"),
    "Search - Emergency": ("google", "45.00", [3, 4, 3, 4, 4], "210.00", "95.00"),
}


def eur_usd(day):
    """An invented, gently moving EUR to USD rate."""
    step = (day - date(2026, 10, 1)).days
    return Decimal("1.0800") + Decimal((step * 7) % 11 - 5) / 1000


def days(week_end):
    return [week_end - timedelta(days=6 - k) for k in range(7)]


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def week_name(week_end):
    year, week, _ = week_end.isocalendar()
    return f"{year}-W{week:02d}"


def money(value):
    return f"{Decimal(value):,.2f}"


def client_exports(folder, prefix, campaigns, weeks, *, report_currency, corrected=False,
                   meta_short=False, bad_meta_row=False, extras=True):
    """One CSV per source per week, plus a rate file covering every day."""
    order_no = lead_no = 0
    for w, week_end in enumerate(weeks):
        name = week_name(week_end)
        google, meta, leads, sales = [], [], [], []
        for campaign, (platform, daily, per_week, revenue, cost) in campaigns.items():
            for k, day in enumerate(days(week_end)):
                # A small, repeatable wobble so days differ.
                spend = Decimal(daily) * (Decimal(95 + (k * 3 + w * 5) % 11) / 100)
                if platform == "google":
                    google.append([day.isoformat(), campaign, money(spend), "USD"])
                elif not (meta_short and w == len(weeks) - 1 and k == 6):
                    meta.append([day.strftime("%d/%m/%Y"), campaign, f"{spend:.2f}"])
            for s in range(per_week[w]):
                order_no += 1
                lead_no += 1
                sale_day = days(week_end)[(s * 2 + w) % 7]
                deal = f"D-{prefix}{order_no:04d}"
                created = sale_day - timedelta(days=3 + s % 4)
                leads.append([f"L-{prefix}{lead_no:05d}", created.strftime("%m/%d/%Y") + f" 10:{(s * 7) % 60:02d}",
                              campaign, "Closed Won", deal])
                sales.append([f"O-{prefix}{order_no:05d}", deal, sale_day.isoformat(),
                              money(revenue), money(cost), "0.00", "USD" if report_currency == "USD" else "EUR"])
                # Two open leads for every sale.
                for stage in ("Qualified", "Lost"):
                    lead_no += 1
                    leads.append([f"L-{prefix}{lead_no:05d}", created.strftime("%m/%d/%Y 15:30"), campaign, stage, ""])
        if (prefix, w) == ("AP", BIG_ORDER[1]):
            campaign, _, revenue, cost = BIG_ORDER
            order_no += 1
            lead_no += 1
            deal = f"D-{prefix}{order_no:04d}"
            sale_day = days(week_end)[3]
            leads.append([f"L-{prefix}{lead_no:05d}", (sale_day - timedelta(days=2)).strftime("%m/%d/%Y 09:15"),
                          campaign, "Closed Won", deal])
            sales.append([f"O-{prefix}{order_no:05d}", deal, sale_day.isoformat(), revenue, cost,
                          revenue if corrected else "0.00", "USD"])
        if extras:
            # A walk-in sale with no deal: counted as margin no campaign earned.
            order_no += 1
            sales.append([f"O-{prefix}{order_no:05d}", "", days(week_end)[5].isoformat(),
                          "96.00", "41.00", "0.00", "USD" if report_currency == "USD" else "EUR"])
        if bad_meta_row and w == 1:
            meta.insert(3, ["32/10/2026", "Prospecting - Spring", "33.10"])
        write(folder / f"google-ads-{name}.csv", ["Day", "Campaign", "Cost", "Currency code"], google)
        if meta:
            write(folder / f"meta-ads-{name}.csv", ["Reporting starts", "Campaign name", "Amount spent (EUR)"], meta)
        write(folder / f"crm-leads-{name}.csv", ["Lead ID", "Created", "UTM Campaign", "Stage", "Deal ID"], leads)
        write(folder / f"sales-{name}.csv",
              ["order_id", "deal_id", "order_date", "revenue", "cost_of_goods", "refunded", "currency"], sales)
    first = weeks[0] - timedelta(days=13)
    rates = []
    for k in range((weeks[-1] - first).days + 1):
        day = first + timedelta(days=k)
        if report_currency == "USD":
            rates.append([day.isoformat(), "EUR", f"{eur_usd(day):.4f}"])
        else:
            rates.append([day.isoformat(), "USD", f"{1 / eur_usd(day):.4f}"])
    write(folder / "fx-rates.csv", ["date", "currency", "rate"], rates)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report_of(folder, week_ending, sources):
    """The workflow's own report for a folder, as `previous-report.json` holds it."""
    read = load(WORKFLOW / "per_file/read/read.py", "read")
    report = load(WORKFLOW / "report/report.py", "report")
    files = [read.run([(p.name, p)])["files"] for p in sorted(folder.glob("*.csv"))]
    client = json.loads((folder / "client.json").read_text())
    return report.run(files, sources, client, None, week_ending)["report"]


def main():
    sources = json.loads((WORKFLOW / "sources.json").read_text())
    alder = HERE / "alder-pine"
    shutil.rmtree(alder, ignore_errors=True)
    client = {"name": "Alder & Pine Outfitters", "currency": "USD", "target_cost_per_sale": "120.00"}
    for period, weeks in (("period-1", WEEKS[:4]), ("period-2", WEEKS)):
        folder = alder / period
        client_exports(folder, "AP", ALDER, weeks, report_currency="USD", corrected=period == "period-2",
                       meta_short=period == "period-2", bad_meta_row=True)
        (folder / "client.json").write_text(json.dumps(client, indent=2) + "\n")
    previous = report_of(alder / "period-1", WEEKS[3].isoformat(), sources)
    (alder / "period-2" / "previous-report.json").write_text(json.dumps(previous, indent=2) + "\n")

    harbor = HERE / "harbor-lane"
    shutil.rmtree(harbor, ignore_errors=True)
    client_exports(harbor, "HL", HARBOR, WEEKS[1:], report_currency="EUR", extras=False)
    (harbor / "client.json").write_text(json.dumps(
        {"name": "Harbor Lane Dental", "currency": "EUR", "target_cost_per_sale": "400.00"}, indent=2) + "\n")
    (harbor / "sources.json").write_text(json.dumps(
        {k: v for k, v in sources.items() if k != "meta_ads"}, indent=2) + "\n")


if __name__ == "__main__":
    main()
