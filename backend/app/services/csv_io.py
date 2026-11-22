"""CSV import (preview first, per-row errors, limits) and export (formula-injection safe)."""

import csv
import io
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Organization
from app.schemas.public import EMAIL_RE
from app.services import crm
from app.services.activity import audit
from app.services.normalize import normalize_email, normalize_phone

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
FIELDS = ("full_name", "email", "phone", "company", "website", "message")
# Header guesses, compared lowercase with spaces and underscores removed.
SYNONYMS = {
    "full_name": {"name", "fullname", "contact", "contactname", "lead", "leadname"},
    "email": {"email", "emailaddress", "mail", "e-mail"},
    "phone": {"phone", "phonenumber", "mobile", "tel", "telephone", "whatsapp"},
    "company": {"company", "companyname", "organization", "organisation", "business"},
    "website": {"website", "url", "site", "web"},
    "message": {"message", "notes", "inquiry", "enquiry", "comment", "details"},
}
LIMITS = {
    "full_name": 200,
    "email": 320,
    "phone": 40,
    "company": 200,
    "website": 300,
    "message": 4000,
}


@dataclass
class RowError:
    row: int  # 1-based data row number (the header is row 0)
    field: str
    message: str


@dataclass
class ImportReport:
    dry_run: bool
    columns: list[str]
    mapping: dict[str, str]
    total_rows: int = 0
    valid_rows: int = 0
    would_create: int = 0
    would_merge: int = 0
    created: int = 0
    merged: int = 0
    errors: list[RowError] = field(default_factory=list)


class CsvRejected(ValueError):
    """The whole file is unusable (too big, no header, unknown mapping)."""


def _key(header: str) -> str:
    return header.strip().lower().replace(" ", "").replace("_", "")


def guess_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        k = _key(header)
        for target, names in SYNONYMS.items():
            if target not in mapping and (k in names or k == target.replace("_", "")):
                mapping[target] = header
    return mapping


def parse(text: str) -> tuple[list[str], list[dict[str, str]]]:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise CsvRejected("The file is larger than 2 MB. Split it and import the parts.")
    text = text.lstrip("﻿")  # Excel's UTF-8 byte-order mark
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or []) if h and h.strip()]
    if not headers:
        raise CsvRejected("The file has no header row.")
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise CsvRejected(f"The file has more than {MAX_ROWS} rows. Split it first.")
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k})
    return headers, rows


def run_import(
    db: Session,
    org: Organization,
    actor_id: uuid.UUID,
    text: str,
    mapping: dict[str, str] | None,
    dry_run: bool,
    ip: str | None = None,
) -> ImportReport:
    headers, rows = parse(text)
    mapping = {k: v for k, v in (mapping or guess_mapping(headers)).items() if v}
    unknown = [t for t in mapping if t not in FIELDS]
    missing_cols = [c for c in mapping.values() if c not in headers]
    if unknown or missing_cols:
        raise CsvRejected(f"Unknown fields {unknown} or columns {missing_cols} in the mapping.")
    if "full_name" not in mapping:
        raise CsvRejected("Map a column to the lead's name (full_name).")

    report = ImportReport(dry_run=dry_run, columns=headers, mapping=mapping, total_rows=len(rows))
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    for n, raw in enumerate(rows, start=1):
        values = {f: raw.get(col, "") for f, col in mapping.items()}
        problems = []
        if not values.get("full_name"):
            problems.append(RowError(n, "full_name", "Name is empty."))
        for f, limit in LIMITS.items():
            if len(values.get(f, "")) > limit:
                problems.append(RowError(n, f, f"Longer than {limit} characters."))
        email = values.get("email") or None
        if email and not EMAIL_RE.match(email):
            problems.append(RowError(n, "email", "Not a valid email address."))
        if problems:
            report.errors.extend(problems)
            continue

        report.valid_rows += 1
        email_n = normalize_email(email)
        phone_e = normalize_phone(values.get("phone"), org.default_country)
        in_file_dupe = (email_n and email_n in seen_emails) or (phone_e and phone_e in seen_phones)
        exists = crm.find_existing(db, org.id, email_n, phone_e) is not None
        if email_n:
            seen_emails.add(email_n)
        if phone_e:
            seen_phones.add(phone_e)
        if dry_run:
            if exists or in_file_dupe:
                report.would_merge += 1
            else:
                report.would_create += 1
            continue
        result = crm.create_lead(
            db,
            org,
            actor_id,
            full_name=values["full_name"],
            email=email,
            phone=values.get("phone"),
            company=values.get("company"),
            website=values.get("website"),
            message=values.get("message"),
            source_key="csv",
            channel="csv",
            analyze=False,
        )
        if result.merged:
            report.merged += 1
        else:
            report.created += 1

    if not dry_run:
        audit(
            db,
            org.id,
            actor_id,
            "leads.imported",
            "lead",
            ip=ip,
            rows=report.total_rows,
            created=report.created,
            merged=report.merged,
            errors=len(report.errors),
        )
        db.commit()
    return report


# ---------------------------------------------------------------- export

_DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """Neutralize spreadsheet formula injection: a leading apostrophe makes it plain text."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_DANGEROUS_START) else text


def to_csv(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_cell(row.get(c)) for c in columns])
    return "﻿" + buf.getvalue()  # BOM so Excel opens UTF-8 correctly
