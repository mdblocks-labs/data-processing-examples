"""report.py — a client's campaign report from decoded CSV exports.

Each file is matched to the source in `sources.json` whose headers it carries,
and each row is parsed by its kind: `spend`, `leads`, `sales` or `rates`. A row
that can't be used goes to `review` with its file and row and is left out.
Amounts become the report currency at the latest rate on or before the row's
date. The period is the 28 days ending `week_ending`.

A qualified sale is a sale in the period whose deal is on a CRM lead marked won,
unless refunded in full; its campaign is the lead's. Margin is revenue minus
cost minus refund. Decisions use the rounded figures the report shows.
"""

import hashlib
import json
import re
from bisect import bisect_right
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")
AMOUNT = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
MAX_AMOUNT = Decimal("1e12")  # far above any export's amount, and far below the decimal context's limits
CURRENCY = re.compile(r"[A-Z]{3}")
DAYS = 28

# Per kind: the columns a source must map, the columns that identify a row
# (a repeat is counted once), and the amount a file's totals add up.
KINDS = {
    "spend": {"columns": ("date", "campaign", "spend"), "key": ("date", "campaign"), "total": "spend"},
    "leads": {"columns": ("lead", "date", "campaign", "stage", "deal"), "key": ("lead",), "total": None},
    "sales": {"columns": ("order", "deal", "date", "revenue", "cost", "refund"), "key": ("order",),
              "total": "revenue"},
    "rates": {"columns": ("date", "currency", "rate"), "key": ("date", "currency"), "total": None},
}
MONEY_KINDS = ("spend", "sales")


def run(files, sources, client, previous, week_ending):
    """Build the report.

    Args:
        files: Json — `per_file`'s output: per file, a list of `{file, sha256, header, rows, error}`.
        sources: Json — per source: `kind`, `columns` (column -> header), `date_format`,
            and `currency` (a fixed one) or a `currency` column; leads add `won`, a list of stages.
        client: Json — `{name, currency, target_cost_per_sale}`.
        previous: Json — the text of the last report for this client, or null.
        week_ending: str — `YYYY-MM-DD`, the period's last day.
    """
    settings = fingerprint(client, sources)
    client = check_client(client)
    sources = check_sources(sources)
    end = parse_param(week_ending)
    records = sorted((doc for piece in files for doc in piece), key=lambda doc: doc["file"])
    book = Book(client["currency"], client["target"])
    for doc in records:
        book.add_file(doc, sources)
    book.dedupe()

    current = book.period(end)
    comparison = None
    if previous is not None:
        previous, prev_end = check_previous(previous, client, settings, end, book)
        if prev_end is not None:
            comparison = (previous, book.period(prev_end))
    book.stale(sources, end)

    campaigns = []
    names = set(current["campaigns"])
    if comparison:
        # A campaign the last report showed with no activity is retired.
        names |= set(comparison[1]["campaigns"]) | {
            c["campaign"] for c in comparison[0]["campaigns"] if c.get("recommendation")}
    for name in sorted(names):
        entry = current["campaigns"].get(name) or blank(name, end)
        if comparison:
            entry = with_history(entry, comparison)
        campaigns.append(entry)

    report = {
        "client": client["name"],
        "currency": client["currency"],
        "target_cost_per_sale": money(client["target"]),
        "settings": settings,
        "week_ending": end.isoformat(),
        "period_start": (end - timedelta(days=DAYS - 1)).isoformat(),
        "totals": current["totals"],
        "campaigns": campaigns,
        "files": book.file_summaries(),
        "changes": changes(comparison, book) if comparison else None,
        "review": sorted(book.problems, key=lambda p: (p["file"] or "", p["row"] or 0, p["problem"])),
    }
    report["checksum"] = checksum(report)
    return {"report": report}


def checksum(report):
    """The SHA-256 of the report without this field, so an edited or damaged copy is refused."""
    body = {k: v for k, v in report.items() if k != "checksum"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fingerprint(client, sources):
    """The SHA-256 of `client.json` and `sources.json` as values, so a report compares only
    with one made under the same settings."""
    text = json.dumps({"client": client, "sources": sources}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def check_client(client):
    """Each field's shape; the first that's wrong stops the run, naming it."""
    if not isinstance(client, dict):
        raise ValueError("client.json must be an object with name, currency and target_cost_per_sale")
    name, currency, target = (client.get(k) for k in ("name", "currency", "target_cost_per_sale"))
    if not (isinstance(name, str) and name.strip()):
        raise ValueError("client.json: name must be the client's name")
    if not (isinstance(currency, str) and CURRENCY.fullmatch(currency)):
        raise ValueError("client.json: currency must be a three-letter code such as USD")
    # At most two decimals, so the target compared is the target shown.
    if isinstance(target, bool) or not isinstance(target, (str, int, float)) \
            or not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?", str(target)):
        raise ValueError("client.json: target_cost_per_sale must be an amount with at most two decimals, such as 120.00")
    return {"name": name, "currency": currency, "target": Decimal(str(target).replace(",", ""))}


def check_sources(sources):
    """Every setting's shape, in one place; the first that's wrong stops the run, naming it.
    Returns the settings with every text value trimmed, as the CSV values they meet are."""
    if not isinstance(sources, dict) or not sources:
        raise ValueError("sources.json must map source names to their settings")

    def text(value):
        return isinstance(value, str) and value.strip() != ""

    trimmed = {}
    for name, source in sources.items():
        def bad(field, want):
            raise ValueError(f"sources.json: {name}.{field} must be {want}")
        if not isinstance(source, dict):
            bad("", "an object")
        kind = source.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            bad("kind", f"one of {', '.join(KINDS)}")
        keys = {"kind", "columns", "date_format"} | ({"currency"} if kind in MONEY_KINDS else set()) \
            | ({"won"} if kind == "leads" else set())
        for key in source:
            if key not in keys:
                raise ValueError(f"sources.json: {name}.{key} is not a setting; a {kind} source takes "
                                 f"{', '.join(sorted(keys))}")
        columns = source.get("columns")
        allowed = set(KINDS[kind]["columns"]) | ({"currency"} if kind in MONEY_KINDS else set())
        if not isinstance(columns, dict):
            bad("columns", "an object mapping each column to its header")
        for col in KINDS[kind]["columns"]:
            if col not in columns:
                bad(f"columns.{col}", "the header of that column")
        for col, header in columns.items():
            if col not in allowed:
                raise ValueError(f"sources.json: {name}.columns.{col} is not a column; a {kind} source "
                                 f"has {', '.join(sorted(allowed))}")
            if not text(header):
                bad(f"columns.{col}", "a header name")
        if not text(source.get("date_format")):
            bad("date_format", "a strptime format such as %Y-%m-%d")
        if kind in MONEY_KINDS:
            if ("currency" in columns) == ("currency" in source):
                bad("currency", "set once: a currency column under columns, or a fixed currency here")
            if "currency" in source and not (text(source["currency"]) and CURRENCY.fullmatch(source["currency"].strip())):
                bad("currency", "a three-letter code such as EUR")
        if kind == "leads":
            won = source.get("won")
            if not (isinstance(won, list) and won and all(text(w) for w in won)):
                bad("won", "a list of stage names")
        trimmed[name] = {key: value.strip() if isinstance(value, str)
                         else [v.strip() for v in value] if isinstance(value, list)
                         else {k: v.strip() for k, v in value.items()}
                         for key, value in source.items()}
    return trimmed


def parse_param(week_ending):
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", week_ending):
            raise ValueError  # fromisoformat would take a week such as 2026-W47 as its Monday
        return date.fromisoformat(week_ending)
    except (TypeError, ValueError):
        raise ValueError(f"week_ending {week_ending!r} is not a date in the form YYYY-MM-DD") from None


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_EVEN))


def amount(text):
    text = text.strip()
    if not AMOUNT.fullmatch(text):
        raise ValueError(f"bad amount {text!r}")
    value = Decimal(text.replace(",", ""))
    if value >= MAX_AMOUNT:
        raise ValueError(f"amount {text!r} is too large")
    return value


class Book:
    """Every usable row, by source, with the problems found on the way."""

    def __init__(self, currency, target):
        self.currency = currency
        self.target = target
        self.rows = {}      # source -> list of row dicts
        self.files = []     # per file: {file, sha256, source}
        self.problems = []
        self.rates = {}     # currency -> ([dates], [rates])
        self._noted = set()

    def problem(self, file, row, text):
        if (file, row, text) not in self._noted:
            self._noted.add((file, row, text))
            self.problems.append({"file": file, "row": row, "problem": text})

    def add_file(self, doc, sources):
        name = doc["file"]
        entry = {"file": name, "sha256": doc["sha256"], "source": None}
        self.files.append(entry)
        if doc["error"]:
            self.problem(name, None, f"not read: {doc['error']}")
            return
        header = [h.strip() for h in doc["header"]]
        matches = [s for s, src in sources.items() if all(h in header for h in headers(src))]
        if len(matches) != 1:
            self.problem(name, None, "its headers match no source in sources.json" if not matches
                         else f"its headers match {' and '.join(matches)}; make one source's headers differ")
            return
        source_name = matches[0]
        source = sources[source_name]
        entry["source"] = source_name
        twice = sorted({h for h in headers(source) if header.count(h) > 1})
        if twice:
            self.problem(name, None, f"has more than one {', '.join(repr(h) for h in twice)} column; left out")
            return
        index = {h: header.index(h) for h in headers(source)}
        rows = self.rows.setdefault(source_name, [])
        entry["parsed"] = parsed = []
        for number, cells in enumerate(doc["rows"], start=2):
            if not any(c.strip() for c in cells):
                continue
            if len(cells) != len(header):
                self.problem(name, number, f"has {len(cells)} cells; the header has {len(header)}")
                continue
            raw = {col: cells[index[h]] for col, h in source["columns"].items()}
            try:
                row = parse_row(source["kind"], source, raw)
            except ValueError as exc:
                self.problem(name, number, str(exc))
                continue
            row.update(file=name, row=number, source=source_name)
            rows.append(row)
            parsed.append(row)

    def dedupe(self):
        """A key found in several files of a source counts from the file whose path sorts
        last, all its rows for that key; the other files' rows for it are listed."""
        for source, rows in self.rows.items():
            winner = {}
            for row in rows:  # files arrive in path order
                winner[self.key(row)] = row
            kept = []
            for row in rows:
                last = winner[self.key(row)]
                if row["file"] == last["file"]:
                    kept.append(row)
                else:
                    self.problem(row["file"], row["row"],
                                 f"repeated in {last['file']} row {last['row']}, which is counted")
            self.rows[source] = kept
        by_day = {}
        for row in self.of_kind("rates"):
            by_day.setdefault(row["currency"], {}).setdefault(row["date"], set()).add(row["rate"])
        for currency, days in by_day.items():
            dates = sorted(days)
            # Two different rates for one day: neither is used (None).
            self.rates[currency] = (dates, [next(iter(days[d])) if len(days[d]) == 1 else None for d in dates])

    @staticmethod
    def key(row):
        return tuple(row[k] for k in KINDS[row["kind"]]["key"])

    def of_kind(self, kind):
        return [r for rows in self.rows.values() for r in rows if r["kind"] == kind]

    def convert(self, row, value):
        """`value` in the report currency, or None (and a problem) without a rate."""
        if row["currency"] == self.currency:
            return value
        dates, values = self.rates.get(row["currency"], ([], []))
        at = bisect_right(dates, row["date"])
        if not at:
            self.problem(row["file"], row["row"],
                         f"no {row['currency']} rate on or before {row['date']}")
            return None
        if values[at - 1] is None:
            self.problem(row["file"], row["row"],
                         f"two different {row['currency']} rates on {dates[at - 1]}, the latest on or before {row['date']}")
            return None
        return value * values[at - 1]

    def period(self, end):
        """Per campaign, and in total, the 28 days ending `end`, with four weekly figures."""
        start = (end - timedelta(days=DAYS - 1)).isoformat()
        weeks = [(end - timedelta(days=7 * k)).isoformat() for k in (3, 2, 1, 0)]
        stop = end.isoformat()

        def week_of(day):
            return next(w for w in weeks if day <= w)

        stats = {}

        def campaign(name):
            return stats.setdefault(name, {
                "spend": Decimal(0), "sales": 0, "margin": Decimal(0),
                "weeks": {w: {"spend": Decimal(0), "sales": 0, "margin": Decimal(0)} for w in weeks}})

        spend_total = Decimal(0)
        for row in self.of_kind("spend"):
            if start <= row["date"] <= stop:
                value = self.convert(row, row["spend"])
                if value is None:
                    continue
                c = campaign(row["campaign"])
                c["spend"] += value
                c["weeks"][week_of(row["date"])]["spend"] += value
                spend_total += value

        won = {}
        for lead in self.of_kind("leads"):
            if lead["won"] and lead["deal"]:
                # One lead listed twice with the same campaign is one lead.
                won.setdefault(lead["deal"], {})[(lead["lead"], lead["campaign"])] = lead
        won = {deal: list(leads.values()) for deal, leads in won.items()}
        unattributed = Decimal(0)
        no_campaign = {"sales": 0, "margin": Decimal(0)}  # won, but no one campaign to credit
        for sale in self.of_kind("sales"):
            if not start <= sale["date"] <= stop:
                continue
            margin = self.convert(sale, sale["revenue"] - sale["cost"] - sale["refund"])
            if margin is None:
                continue
            leads = won.get(sale["deal"], []) if sale["deal"] else []
            if not leads:
                unattributed += margin
                continue
            qualified = sale["refund"] < sale["revenue"]
            if len(leads) > 1:
                # A won sale all the same: in the totals, in no campaign.
                ids = " and ".join(sorted(lead["lead"] for lead in leads))
                self.problem(sale["file"], sale["row"],
                             f"deal {sale['deal']} is on won leads {ids}; counted in the totals only")
                no_campaign["sales"] += qualified
                no_campaign["margin"] += margin
                continue
            if not leads[0]["campaign"]:
                # A qualified sale all the same: in the totals, in no campaign.
                self.problem(leads[0]["file"], leads[0]["row"],
                             "won lead with no campaign; its sale counts in the totals only")
                no_campaign["sales"] += qualified
                no_campaign["margin"] += margin
                continue
            c = campaign(leads[0]["campaign"])
            week = c["weeks"][week_of(sale["date"])]
            c["sales"] += qualified
            c["margin"] += margin
            week["sales"] += qualified
            week["margin"] += margin

        campaigns = {name: figures(name, s, self) for name, s in stats.items()}
        totals = metrics(spend_total, sum(s["sales"] for s in stats.values()) + no_campaign["sales"],
                         sum((s["margin"] for s in stats.values()), no_campaign["margin"]), self.target)
        totals["unattributed_margin"] = money(unattributed)
        del totals["recommendation"]
        return {"campaigns": campaigns, "totals": totals}

    def stale(self, sources, end):
        stop, week = end.isoformat(), (end - timedelta(days=6)).isoformat()
        for name, source in sources.items():
            dates = [r["date"] for r in self.rows.get(name, [])]
            if not any(f["source"] == name for f in self.files):
                self.problem(None, None, f"{name}: no file in the folder matches its headers")
            elif source["kind"] == "rates":
                continue  # a missing rate is listed on the row that needs it
            elif not dates:
                self.problem(None, None, f"{name}: no usable rows")
            elif source["kind"] == "spend" and stop not in dates:
                # Spend comes a row a day, so a missing last day is a short export.
                last = max((d for d in dates if d <= stop), default=None)
                self.problem(None, None, f"{name}: no row on {stop}, the week ending; last before it {last}")
            elif not any(week <= d <= stop for d in dates):
                self.problem(None, None, f"{name}: no rows in the week ending {stop}")

    def file_summaries(self):
        out = []
        for entry in self.files:
            rows = entry.pop("parsed", [])  # every usable row, before repeats are dropped
            totals = {}
            kind = rows[0]["kind"] if rows else None
            field = KINDS[kind]["total"] if kind else None
            if field:
                for r in rows:
                    totals[r["currency"]] = totals.get(r["currency"], Decimal(0)) + r[field]
            dates = sorted(r["date"] for r in rows)
            out.append({**entry, "rows": len(rows),
                        "first": dates[0] if dates else None, "last": dates[-1] if dates else None,
                        "totals": {cur: money(v) for cur, v in sorted(totals.items())}})
        return out


def headers(source):
    return list(source["columns"].values())


def parse_row(kind, source, raw):
    row = {"kind": kind}
    if "date" in raw:
        text = raw["date"].strip()
        try:
            row["date"] = datetime.strptime(text, source["date_format"]).date().isoformat()
        except ValueError:
            raise ValueError(f"bad date {text!r}; expected {source['date_format']}") from None
    if kind in MONEY_KINDS or kind == "rates":
        currency = (raw["currency"] if "currency" in raw else source["currency"]).strip().upper()
        if not CURRENCY.fullmatch(currency):
            raise ValueError(f"bad currency {currency!r}")
        row["currency"] = currency
    if kind == "spend":
        row["campaign"] = raw["campaign"].strip()
        if not row["campaign"]:
            raise ValueError("no campaign")
        row["spend"] = amount(raw["spend"])
    elif kind == "leads":
        row["lead"] = raw["lead"].strip()
        if not row["lead"]:
            raise ValueError("no lead id")
        row["campaign"] = raw["campaign"].strip()
        row["deal"] = raw["deal"].strip()
        row["won"] = raw["stage"].strip() in source["won"]
    elif kind == "sales":
        row["order"] = raw["order"].strip()
        if not row["order"]:
            raise ValueError("no order id")
        row["deal"] = raw["deal"].strip()
        for col in ("revenue", "cost", "refund"):
            row[col] = amount(raw[col])
        if row["refund"] > row["revenue"]:
            raise ValueError(f"refund {raw['refund'].strip()} is more than the revenue {raw['revenue'].strip()}")
    else:
        row["rate"] = amount(raw["rate"])
        if not row["rate"]:
            raise ValueError("rate is zero")
    return row


def metrics(spend, sales, margin, target):
    spend, margin = spend.quantize(CENT, ROUND_HALF_EVEN), margin.quantize(CENT, ROUND_HALF_EVEN)
    after = margin - spend
    cost = (spend / sales).quantize(CENT, ROUND_HALF_EVEN) if sales else None
    if after < 0:
        rec = "cut"
    elif sales and cost <= target and after > 0:
        rec = "scale"
    else:
        rec = "hold"
    return {"spend": str(spend), "sales": sales, "cost_per_sale": None if cost is None else str(cost),
            "margin": str(margin), "margin_after_spend": str(after), "recommendation": rec}


def figures(name, s, book):
    out = {"campaign": name, **metrics(s["spend"], s["sales"], s["margin"], book.target)}
    out["weeks"] = [{"week_ending": w, "spend": money(v["spend"]), "sales": v["sales"],
                     "margin": money(v["margin"])} for w, v in s["weeks"].items()]
    return out


def blank(name, end):
    """A campaign the previous report had that has no rows in this period: no recommendation."""
    weeks = [(end - timedelta(days=7 * k)).isoformat() for k in (3, 2, 1, 0)]
    return {"campaign": name, "spend": "0.00", "sales": 0, "cost_per_sale": None, "margin": "0.00",
            "margin_after_spend": "0.00", "recommendation": None,
            "weeks": [{"week_ending": w, "spend": "0.00", "sales": 0, "margin": "0.00"} for w in weeks]}


SUMMARY = ("recommendation", "spend", "sales", "cost_per_sale", "margin_after_spend")


def check_previous(text, client, settings, end, book):
    """The previous report and its last day, or None (and a problem) when it can't be compared."""
    name = "previous-report.json"

    def refuse(why):
        book.problem(name, None, f"{why}; not compared")
        return None, None

    try:
        previous = json.loads(text)
    except (TypeError, ValueError) as exc:
        return refuse(f"is not valid JSON ({exc})")
    # The checksum vouches for everything else in it: this workflow wrote it, unchanged.
    if not isinstance(previous, dict) or previous.get("checksum") != checksum(previous):
        return refuse("doesn't match its checksum, so it was edited or damaged after this workflow wrote it")
    if previous["client"] != client["name"]:
        return refuse(f"is for {previous['client']!r}, not {client['name']!r}")
    # A change to client.json or sources.json would read as a corrected export.
    if previous["settings"] != settings:
        return refuse("was made with other settings in client.json or sources.json")
    prev_end = date.fromisoformat(previous["week_ending"])
    if prev_end >= end:
        return refuse(f"ends {prev_end.isoformat()}, not before {end.isoformat()}")
    return previous, prev_end


def with_history(entry, comparison):
    previous, restated = comparison
    before = next((c for c in previous["campaigns"] if c.get("campaign") == entry["campaign"]), None)
    again = restated["campaigns"].get(entry["campaign"])
    entry = dict(entry)
    entry["previous"] = {k: before.get(k) for k in SUMMARY} if before else None
    entry["restated"] = {k: again[k] for k in SUMMARY} if again else None
    was = before.get("recommendation") if before else None
    mid = again["recommendation"] if again else None
    entry["changed_by"] = ([] if was == mid else ["corrected export"]) + \
        ([] if mid == entry["recommendation"] else ["new week"])
    return entry


def changes(comparison, book):
    previous, restated = comparison
    before = {f["file"]: f.get("sha256") for f in previous["files"]}
    now = {f["file"]: f["sha256"] for f in book.files}
    return {
        "previous_week_ending": previous["week_ending"],
        "previous_totals": previous.get("totals"),
        "restated_totals": restated["totals"],
        "added": sorted(set(now) - set(before)),
        "changed": sorted(f for f in now if f in before and before[f] != now[f]),
        "removed": sorted(set(before) - set(now)),
    }
