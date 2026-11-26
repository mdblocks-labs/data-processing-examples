"""reconcile.py — processor payouts tied to bank deposits, month by month.

Each file is matched to the source in `sources.json` whose headers it carries.
Order, refund and fee rows add up to payouts, keyed by processor and payout ID;
bank rows are deposits. A deposit is tied to a payout one to one: first by the
payout ID as a whole word in the bank description, then by the same amount to
the cent dated 0 to `match_days` days after the payout, when neither side has a
second candidate. A row that can't be used goes to `review` with its file and
row. Amounts are integer cents.
"""

import hashlib
import json
import re
from datetime import date, datetime

AMOUNT = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")
MAX_CENTS = 10 ** 14  # a trillion
CURRENCY = re.compile(r"[A-Z]{3}")
MONTH = re.compile(r"\d{4}-\d{2}")
HEX64 = re.compile(r"[0-9a-f]{64}")
APPROVAL_HEADER = ["month", "checksum", "approved_by", "approved_on"]

PAYOUT_KINDS = ("orders", "refunds", "fees")
COLUMNS = {kind: ("id", "date", "amount", "payout_id", "payout_date") for kind in PAYOUT_KINDS}
COLUMNS["bank"] = ("id", "date", "amount", "description")
SETTINGS = {"orders": {"processor"}, "refunds": {"processor", "negate"}, "fees": {"processor", "negate"},
            "bank": set()}

# Statuses that leave a payout or a deposit open, to investigate.
OPEN = {"amount differs", "no deposit", "ambiguous", "dates differ", "no payout"}


def run(files, sources, merchant, approvals):
    """Reconcile.

    Args:
        files: Json — `per_file`'s output: per file, a list of `{file, sha256, header, rows, error}`.
        sources: Json — per source: `kind`, `columns` (column -> header), `date_format`;
            orders, refunds and fees add `processor`, and refunds and fees may set `negate`.
        merchant: Json — `{name, currency, match_days}`.
        approvals: Json — the text of `approvals.csv`, or null.
    """
    settings = {"merchant": merchant, "sources": sources}
    merchant = check_merchant(merchant)
    sources = check_sources(sources)
    book = Book(merchant["currency"])
    for doc in sorted((doc for piece in files for doc in piece), key=lambda doc: doc["file"]):
        book.add_file(doc, sources)
    book.dedupe()

    payouts = book.payouts()
    bank = sorted(book.bank, key=lambda r: (r["file"], r["row"]))
    tie(payouts, bank, merchant["match_days"])
    through = max((b["date"] for b in bank), default=None)
    for p in payouts:
        if p["status"] is None:
            waiting = through is None or (date.fromisoformat(through) - date.fromisoformat(p["date"])).days \
                < merchant["match_days"]
            p["status"] = "in transit" if waiting else "no deposit"
    for b in bank:
        if b["status"] is None:
            b["status"] = "no payout" if b["amount"] > 0 else "not a deposit"

    rows = evidence(book, payouts, bank)
    months = month_list(rows, payouts, bank, settings)
    approve(months, approvals, book)
    report = {
        "merchant": merchant["name"],
        "currency": merchant["currency"],
        "match_days": merchant["match_days"],
        "bank_through": through,
        "months": months,
        "payouts": [{k: v for k, v in p.items() if k != "rows"} for p in payouts],
        "evidence": rows,
        "files": book.file_summaries(),
        "review": sorted(book.problems, key=lambda p: (p["file"] or "", p["row"] or 0, p["problem"])),
    }
    return {"report": report, "summary": summary(report)}


def check_merchant(merchant):
    """Each field's shape; the first that's wrong stops the run, naming it."""
    if not isinstance(merchant, dict):
        raise ValueError("merchant.json must be an object with name, currency and match_days")
    name, currency, days = (merchant.get(k) for k in ("name", "currency", "match_days"))
    if not (isinstance(name, str) and name.strip()):
        raise ValueError("merchant.json: name must be the merchant's name")
    if not (isinstance(currency, str) and CURRENCY.fullmatch(currency)):
        raise ValueError("merchant.json: currency must be a three-letter code such as USD")
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("merchant.json: match_days must be a whole number of days, 0 or more")
    return {"name": name, "currency": currency, "match_days": days}


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
        if not isinstance(kind, str) or kind not in COLUMNS:
            bad("kind", f"one of {', '.join(COLUMNS)}")
        keys = {"kind", "columns", "date_format"} | SETTINGS[kind]
        for key in source:
            if key not in keys:
                raise ValueError(f"sources.json: {name}.{key} is not a setting; a {kind} source takes "
                                 f"{', '.join(sorted(keys))}")
        columns = source.get("columns")
        if not isinstance(columns, dict):
            bad("columns", "an object mapping each column to its header")
        for col in COLUMNS[kind]:
            if col not in columns:
                bad(f"columns.{col}", "the header of that column")
        allowed = set(COLUMNS[kind]) | {"currency"}
        for col, header in columns.items():
            if col not in allowed:
                raise ValueError(f"sources.json: {name}.columns.{col} is not a column; a {kind} source "
                                 f"has {', '.join(sorted(allowed))}")
            if not text(header):
                bad(f"columns.{col}", "a header name")
        if not text(source.get("date_format")):
            bad("date_format", "a strptime format such as %Y-%m-%d")
        if "processor" in SETTINGS[kind] and not text(source.get("processor")):
            bad("processor", "the processor's name")
        if "negate" in source and not isinstance(source["negate"], bool):
            bad("negate", "true or false")
        trimmed[name] = {
            "kind": kind,
            "columns": {k: v.strip() for k, v in columns.items()},
            "date_format": source["date_format"].strip(),
            "processor": source.get("processor", "").strip() or None,
            "negate": source.get("negate", False),
        }
    return trimmed


def cents(text):
    """Whole cents from an amount with at most two decimals; ValueError naming what's wrong."""
    text = text.strip()
    match = AMOUNT.fullmatch(text)
    if not match:
        raise ValueError(f"bad amount {text!r}")
    if match.group(1) is not None and len(match.group(1)) > 2:
        raise ValueError(f"amount {text!r} has more than two decimals")
    whole, _, frac = text.replace(",", "").lstrip("-").partition(".")
    value = int(whole) * 100 + int((frac + "00")[:2])
    if value >= MAX_CENTS:
        raise ValueError(f"amount {text!r} is too large")
    return -value if text.startswith("-") else value


def money(value):
    """Cents as a decimal string: -1234 -> '-12.34'."""
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value) // 100}.{abs(value) % 100:02d}"


def parse_date(text, fmt):
    text = text.strip()
    try:
        return datetime.strptime(text, fmt).date().isoformat()
    except ValueError:
        raise ValueError(f"bad date {text!r}; expected {fmt}") from None


class Book:
    """Every usable row, by source, with the problems found on the way."""

    def __init__(self, currency):
        self.currency = currency
        self.rows = {}      # source -> list of row dicts, files in path order
        self.files = []     # per file: {file, sha256, source}
        self.bank = []
        self.problems = []

    def problem(self, file, row, text):
        self.problems.append({"file": file, "row": row, "problem": text})

    def add_file(self, doc, sources):
        name = doc["file"]
        entry = {"file": name, "sha256": doc["sha256"], "source": None, "parsed": []}
        self.files.append(entry)
        if doc["error"]:
            self.problem(name, None, f"not read: {doc['error']}")
            return
        header = [h.strip() for h in doc["header"]]
        matches = [s for s, src in sources.items() if all(h in header for h in src["columns"].values())]
        # Every data row of a file left out is named, so each source row is accounted for.
        last = len(doc["rows"]) + 1
        rows = "" if not doc["rows"] else "; row 2 left out" if last == 2 else f"; rows 2 to {last} left out"
        if len(matches) != 1:
            self.problem(name, None, "its headers match no source in sources.json" + rows if not matches
                         else f"its headers match {' and '.join(matches)}; make one source's headers differ{rows}")
            return
        source_name = matches[0]
        source = sources[source_name]
        entry["source"] = source_name
        twice = sorted({h for h in source["columns"].values() if header.count(h) > 1})
        if twice:
            self.problem(name, None, f"has more than one {', '.join(repr(h) for h in twice)} column{rows or '; left out'}")
            return
        index = {col: header.index(h) for col, h in source["columns"].items()}
        rows = self.rows.setdefault(source_name, [])
        for number, cells in enumerate(doc["rows"], start=2):
            if not any(c.strip() for c in cells):
                continue
            if len(cells) != len(header):
                self.problem(name, number, f"has {len(cells)} cells; the header has {len(header)}")
                continue
            try:
                row = self.parse(source, {col: cells[i] for col, i in index.items()})
            except ValueError as exc:
                self.problem(name, number, str(exc))
                continue
            row.update(file=name, row=number, source=source_name)
            rows.append(row)
            entry["parsed"].append(row)

    def parse(self, source, raw):
        kind = source["kind"]
        row = {"kind": kind, "id": raw["id"].strip()}
        if not row["id"]:
            raise ValueError("no id")
        row["date"] = parse_date(raw["date"], source["date_format"])
        row["amount"] = row["written"] = cents(raw["amount"])
        if "currency" in raw:
            currency = raw["currency"].strip().upper()
            if currency != self.currency:
                raise ValueError(f"currency {currency or 'blank'}, not the merchant's {self.currency}")
        if kind == "bank":
            row["description"] = raw["description"].strip()
            return row
        if source["negate"]:
            row["amount"] = -row["amount"]
        row["processor"] = source["processor"]
        row["payout_id"] = raw["payout_id"].strip()
        payout_date = raw["payout_date"].strip()
        if bool(row["payout_id"]) != bool(payout_date):
            raise ValueError("payout ID without a payout date" if row["payout_id"]
                             else "payout date without a payout ID")
        row["payout_date"] = parse_date(payout_date, source["date_format"]) if payout_date else None
        return row

    def dedupe(self):
        """An ID repeated within a source counts once: the last by file path, then by row.
        The others are listed."""
        for source, rows in self.rows.items():
            last = {}
            for row in rows:  # files arrive in path order, rows in order
                last[row["id"]] = row
            kept = []
            for row in rows:
                winner = last[row["id"]]
                if winner is row:
                    kept.append(row)
                else:
                    self.problem(row["file"], row["row"],
                                 f"{source} ID {row['id']} is repeated in {winner['file']} row {winner['row']}, "
                                 "which is counted")
            self.rows[source] = kept
            if kept and kept[0]["kind"] == "bank":
                self.bank.extend(kept)

    def payouts(self):
        """One entry per (processor, payout ID), from the rows that name one, sorted."""
        grouped = {}
        for rows in self.rows.values():
            for row in rows:
                if row["kind"] != "bank" and row["payout_id"]:
                    grouped.setdefault((row["processor"], row["payout_id"]), []).append(row)
        out = []
        for (processor, payout_id), rows in sorted(grouped.items()):
            dates = sorted({r["payout_date"] for r in rows})
            by_kind = {k: sum(r["amount"] for r in rows if r["kind"] == k) for k in PAYOUT_KINDS}
            out.append({
                "processor": processor, "payout_id": payout_id,
                # Placed by its latest date when its rows disagree.
                "date": dates[-1], "dates": dates, "month": dates[-1][:7],
                "amount": sum(by_kind.values()), **by_kind,
                "status": "dates differ" if len(dates) > 1 else None,
                "bank": None, "difference": None, "rows": rows,
            })
        return out

    def file_summaries(self):
        out = []
        for entry in self.files:
            rows = entry.pop("parsed")  # every usable row, before repeats are dropped
            dates = sorted(r["date"] for r in rows)
            out.append({**entry, "rows": len(rows), "first": dates[0] if dates else None,
                        "last": dates[-1] if dates else None,
                        # As the export writes them, before `negate`, to tie to the source.
                        "total": sum(r["written"] for r in rows)})
        return out


def tie(payouts, bank, match_days):
    """Tie deposits to payouts one to one; set each side's status, leaving open ones None."""
    for b in bank:
        b.update(status=None, payout=None)

    def link(p, b):
        p["bank"] = {"file": b["file"], "row": b["row"], "date": b["date"], "amount": b["amount"]}
        b["payout"] = {"processor": p["processor"], "payout_id": p["payout_id"]}
        same = b["amount"] == p["amount"]
        p["difference"] = b["amount"] - p["amount"]
        b["status"] = "matched" if same else "amount differs"
        if p["status"] is None:
            p["status"] = b["status"]

    # By ID: the payout ID as a whole word in the description, ignoring case.
    named = {id(p): [] for p in payouts}
    names = {}
    patterns = [(p, re.compile(r"(?<!\w)" + re.escape(p["payout_id"]) + r"(?!\w)", re.I))
                for p in payouts]
    for b in bank:
        names[id(b)] = [p for p, pattern in patterns if pattern.search(b["description"])]
        for p in names[id(b)]:
            named[id(p)].append(b)
    for b in bank:
        found = names[id(b)]
        if not found:
            continue
        if len(found) == 1 and len(named[id(found[0])]) == 1:
            link(found[0], b)
        else:
            b["status"] = "ambiguous"
            for p in found:
                if p["status"] is None:
                    p["status"] = "ambiguous"

    # By amount and date, among what is still open; a payout whose dates differ is tied by ID only.
    open_p = [p for p in payouts if p["status"] is None]
    open_b = [b for b in bank if b["status"] is None]
    by_amount = {}
    for p in open_p:
        by_amount.setdefault(p["amount"], []).append(p)
    candidates = {id(b): [p for p in by_amount.get(b["amount"], [])
                          if 0 <= (date.fromisoformat(b["date"]) - date.fromisoformat(p["date"])).days <= match_days]
                  for b in open_b}
    count = {id(p): 0 for p in open_p}
    for b in open_b:
        for p in candidates[id(b)]:
            count[id(p)] += 1
    for b in open_b:
        found = candidates[id(b)]
        if len(found) == 1 and count[id(found[0])] == 1:
            link(found[0], b)
        elif found:
            b["status"] = "ambiguous"
            for p in found:
                p["status"] = "ambiguous"


EVIDENCE = ("month", "status", "file", "row", "source", "kind", "id", "date", "amount", "processor",
            "payout_id", "payout_date", "description", "bank_file", "bank_row")


def evidence(book, payouts, bank):
    """One line per counted source row: its values, its status and what it was tied to."""
    of = {(p["processor"], p["payout_id"]): p for p in payouts}
    rows = []
    for source_rows in book.rows.values():
        for r in source_rows:
            line = dict.fromkeys(EVIDENCE)
            line.update({k: r.get(k) for k in ("file", "row", "source", "kind", "id", "date", "amount")})
            if r["kind"] == "bank":
                line.update(month=r["date"][:7], status=r["status"], description=r["description"],
                            **(r["payout"] or {}))
            else:
                line.update(processor=r["processor"], payout_id=r["payout_id"] or None,
                            payout_date=r["payout_date"])
                p = of.get((r["processor"], r["payout_id"]))
                if p is None:
                    line["status"] = "not paid out"
                else:
                    line.update(month=p["month"], status=p["status"])
                    if p["bank"]:
                        line.update(bank_file=p["bank"]["file"], bank_row=p["bank"]["row"])
            rows.append(line)
    return sorted(rows, key=lambda r: (r["file"], r["row"]))


def month_list(rows, payouts, bank, settings):
    """Per month: totals, open counts and the evidence checksum."""
    months = sorted({r["month"] for r in rows if r["month"]})
    out = []
    for month in months:
        mine = [p for p in payouts if p["month"] == month]
        deposits = [b for b in bank if b["date"][:7] == month]
        lines = [r for r in rows if r["month"] == month]
        body = json.dumps({"month": month, "rows": lines, **settings}, sort_keys=True, separators=(",", ":"))
        out.append({
            "month": month,
            "checksum": hashlib.sha256(body.encode()).hexdigest(),
            "status": "not approved",
            "approvals": [],
            "totals": {
                "payouts": len(mine),
                "paid_out": sum(p["amount"] for p in mine),
                **{k: sum(p[k] for p in mine) for k in PAYOUT_KINDS},
                "deposits": sum(1 for b in deposits if b["amount"] > 0),
                "deposited": sum(b["amount"] for b in deposits if b["amount"] > 0),
                "matched": sum(1 for p in mine if p["status"] == "matched"),
                "open_payouts": sum(1 for p in mine if p["status"] in OPEN),
                "open_deposits": sum(1 for b in deposits if b["status"] in OPEN),
                "in_transit": sum(1 for p in mine if p["status"] == "in transit"),
            },
        })
    return out


def approve(months, text, book):
    """Mark a month approved while one of its approval lines carries its current checksum."""
    if text is None:
        return
    name = "approvals.csv"
    # One line at a time, split on commas: no field needs quoting, so a bad line can't affect another.
    lines = text.splitlines()
    if not lines or [h.strip() for h in lines[0].split(",")] != APPROVAL_HEADER:
        book.problem(name, 1, f"the header must be {','.join(APPROVAL_HEADER)}")
        return
    by_month = {m["month"]: m for m in months}
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cells = line.split(",")
        if '"' in line:
            book.problem(name, number, "has a quote; write each field without quotes")
            continue
        if len(cells) != len(APPROVAL_HEADER):
            book.problem(name, number, f"has {len(cells)} cells; the header has {len(APPROVAL_HEADER)}")
            continue
        month, checksum, by, on = (c.strip() for c in cells)
        if "\ufffd" in line:
            book.problem(name, number, "not valid UTF-8")
        elif not MONTH.fullmatch(month) or not 1 <= int(month[5:]) <= 12:
            book.problem(name, number, f"bad month {month!r}; expected YYYY-MM")
        elif not HEX64.fullmatch(checksum):
            book.problem(name, number, "the checksum must be the 64 characters the run reported for the month")
        elif not by:
            book.problem(name, number, "no name in approved_by")
        elif not valid_day(on):
            book.problem(name, number, f"bad approved_on {on!r}; expected YYYY-MM-DD")
        elif month not in by_month:
            book.problem(name, number, f"approves {month}, a month with no rows")
        else:
            entry = by_month[month]
            current = checksum == entry["checksum"]
            entry["approvals"].append({"row": number, "approved_by": by, "approved_on": on, "current": current})
    for entry in months:
        if any(a["current"] for a in entry["approvals"]):
            entry["status"] = "approved"
        elif entry["approvals"]:
            entry["status"] = "approval out of date"


def valid_day(text):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def summary(report):
    """What the site may show: totals only for approved months, counts for the others."""
    months = []
    for m in report["months"]:
        entry = {"month": m["month"], "status": m["status"]}
        if m["status"] == "approved":
            last = max((a for a in m["approvals"] if a["current"]), key=lambda a: (a["approved_on"], a["row"]))
            entry.update(approved_by=last["approved_by"], approved_on=last["approved_on"], totals=m["totals"])
        else:
            entry.update({k: m["totals"][k] for k in ("open_payouts", "open_deposits", "in_transit")})
        months.append(entry)
    return {"merchant": report["merchant"], "currency": report["currency"],
            "bank_through": report["bank_through"], "months": months}
