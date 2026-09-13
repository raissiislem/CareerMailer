"""CSV validation, email generation, SMTP delivery, and logging."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
import csv
from pathlib import Path
import re
import smtplib
import ssl
from typing import Iterable

from config import Settings

REQUIRED_COLUMNS = ("name", "email", "company", "personalization")
EMAIL_SUBJECT = "Candidature spontanée – PFE Data – Janvier 2027"
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "email_template.txt"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class Contact:
    name: str
    email: str
    company: str
    personalization: str = ""


@dataclass(frozen=True)
class ValidationResult:
    contacts: list[Contact]
    errors: list[str]
    duplicate_emails: list[str]


def load_contacts(csv_path: Path) -> ValidationResult:
    errors: list[str] = []
    contacts: list[Contact] = []
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != list(REQUIRED_COLUMNS):
                actual = ",".join(reader.fieldnames or [])
                errors.append(f"CSV columns must be exactly name,email,company; found: {actual or '(none)'}")
            else:
                for row_number, row in enumerate(reader, start=2):
                    name = (row.get("name") or "").strip()
                    email = (row.get("email") or "").strip()
                    company = (row.get("company") or "").strip()
                    personalization = (row.get("personalization") or "").strip()
                    row_errors = []
                    if not name:
                        row_errors.append("name is empty")
                    if not company:
                        row_errors.append("company is empty")
                    if not EMAIL_PATTERN.fullmatch(email) or parseaddr(email)[1] != email:
                        row_errors.append(f"invalid email: {email or '(empty)'}")
                    if row_errors:
                        errors.append(f"Row {row_number}: " + "; ".join(row_errors))
                    else:
                        contacts.append(Contact(name, email, company, personalization))
    except FileNotFoundError:
        errors.append(f"CSV file not found: {csv_path}")
    except OSError as exc:
        errors.append(f"Could not read CSV: {exc}")

    email_counts = Counter(contact.email.casefold() for contact in contacts)
    duplicates = sorted(email for email, count in email_counts.items() if count > 1)
    return ValidationResult(contacts, errors, duplicates)


def save_contacts(csv_path: Path, contacts: list[Contact]) -> None:
    """Persist the editable contact list using the required CSV schema."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {
                "name": contact.name,
                "email": contact.email,
                "company": contact.company,
                "personalization": contact.personalization,
            }
            for contact in contacts
        )


def generate_email(
    name: str,
    company: str,
    personalization: str = "",
    template_path: Path = TEMPLATE_PATH,
    subject: str = EMAIL_SUBJECT,
) -> tuple[str, str]:
    """Return the subject and a short, direct French application email."""
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Email template not found: {template_path}") from exc
    body = template.format(name=name, company=company, personalization=personalization)
    return subject, body


def build_message(
    settings: Settings,
    contact: Contact,
    subject: str,
    body: str,
    attach_cv: bool = True,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((settings.sender_name, settings.sender_email))
    message["To"] = formataddr((contact.name, contact.email))
    message["Subject"] = subject
    message.set_content(body)
    if attach_cv:
        with settings.cv_path.open("rb") as file:
            message.add_attachment(
                file.read(), maintype="application", subtype="pdf", filename=settings.cv_path.name
            )
    return message


def send_messages(settings: Settings, messages: Iterable[tuple[Contact, EmailMessage]]) -> list[tuple[Contact, str, str]]:
    """Send each message separately and return (contact, status, error)."""
    results: list[tuple[Contact, str, str]] = []
    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls(context=context)
        smtp.login(settings.smtp_username, settings.smtp_password)
        message_list = list(messages)
        for index, (contact, message) in enumerate(message_list):
            try:
                smtp.send_message(message)
                results.append((contact, "SENT", ""))
            except (OSError, smtplib.SMTPException) as exc:
                results.append((contact, "FAILED", str(exc)))
            if index < len(message_list) - 1 and settings.delay_seconds > 0:
                import time
                time.sleep(settings.delay_seconds)
    return results


def test_smtp_connection(settings: Settings) -> None:
    """Connect and authenticate without sending a message."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_username, settings.smtp_password)


def send_one_message(settings: Settings, message: EmailMessage) -> None:
    """Send exactly one already-rendered message."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def append_log(log_path: Path, contact: Contact, status: str, error: str = "") -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        if new_file:
            writer.writerow(("timestamp", "name", "email", "company", "status", "error"))
        writer.writerow((datetime.now(timezone.utc).isoformat(), contact.name, contact.email, contact.company, status, error))
