"""Persistent, opt-in scheduling for campaign and test email jobs."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from email.message import EmailMessage

from config import Settings
from email_sender import (
    EMAIL_SUBJECT,
    TEMPLATE_PATH,
    Contact,
    append_log,
    build_message,
    generate_email,
    send_messages,
)

SCHEDULE_PATH = Path(__file__).resolve().parent / "output" / "scheduled_jobs.json"


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    mode: str
    run_at: str
    contacts: list[dict[str, str]]
    test_email: str = ""
    subject: str = ""
    template_path: str = ""
    body_overrides: dict[str, str] | None = None


def parse_schedule_time(value: str) -> datetime:
    """Parse an ISO timestamp and normalize it to a timezone-aware UTC value."""
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Schedule time must be ISO format, e.g. 2026-09-14T18:30:00") from exc
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc)


def _read_jobs(path: Path = SCHEDULE_PATH) -> list[ScheduledJob]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [ScheduledJob(**item) for item in raw]
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Could not read schedule file {path}: {exc}") from exc


def _write_jobs(jobs: list[ScheduledJob], path: Path = SCHEDULE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(job) for job in jobs], indent=2), encoding="utf-8")


def list_scheduled_jobs(path: Path = SCHEDULE_PATH) -> list[ScheduledJob]:
    return _read_jobs(path)


def schedule_job(
    mode: str,
    run_at: datetime,
    contacts: list[Contact],
    subject: str = "",
    template_path: Path | None = None,
    test_email: str = "",
    body_overrides: dict[str, str] | None = None,
    path: Path = SCHEDULE_PATH,
) -> ScheduledJob:
    if mode not in {"send", "test"}:
        raise ValueError("Scheduled mode must be 'send' or 'test'.")
    if mode == "test" and not test_email:
        raise ValueError("A test email address is required for a scheduled test.")
    if mode == "send" and not contacts:
        raise ValueError("A scheduled campaign must contain at least one contact.")
    timestamp = run_at.astimezone(timezone.utc)
    job = ScheduledJob(
        job_id=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
        mode=mode,
        run_at=timestamp.isoformat(),
        contacts=[asdict(contact) for contact in contacts],
        test_email=test_email,
        subject=subject,
        template_path=str(template_path or ""),
        body_overrides=body_overrides or {},
    )
    jobs = _read_jobs(path)
    jobs.append(job)
    _write_jobs(jobs, path)
    return job


def due_jobs(now: datetime | None = None, path: Path = SCHEDULE_PATH) -> list[ScheduledJob]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return [job for job in _read_jobs(path) if parse_schedule_time(job.run_at) <= current]


def remove_job(job_id: str, path: Path = SCHEDULE_PATH) -> None:
    _write_jobs([job for job in _read_jobs(path) if job.job_id != job_id], path)


def remove_contact_from_job(job_id: str, email: str, path: Path = SCHEDULE_PATH) -> None:
    """Remove one recipient from a pending job; remove the job when empty."""
    remaining: list[ScheduledJob] = []
    for job in _read_jobs(path):
        if job.job_id != job_id:
            remaining.append(job)
            continue
        contacts = [item for item in job.contacts if item["email"].casefold() != email.casefold()]
        if contacts or job.mode == "test":
            remaining.append(ScheduledJob(job.job_id, job.mode, job.run_at, contacts, job.test_email, job.subject, job.template_path, job.body_overrides))
    _write_jobs(remaining, path)


def execute_job(job: ScheduledJob, settings: Settings, log_path: Path) -> list[tuple[Contact, str, str]]:
    """Execute one already-due job through the same SMTP service as immediate sends."""
    template_path = Path(job.template_path) if job.template_path else None
    contacts = [Contact(**item) for item in job.contacts]
    if job.mode == "test":
        contacts = [Contact("Test recipient", job.test_email, "SMTP test")]
    messages: list[tuple[Contact, EmailMessage]] = []
    for contact in contacts:
        subject, body = generate_email(
            contact.name,
            contact.company,
            template_path=template_path or TEMPLATE_PATH,
            subject=job.subject or EMAIL_SUBJECT,
        )
        if job.body_overrides and contact.email.casefold() in job.body_overrides:
            body = job.body_overrides[contact.email.casefold()]
        if job.mode == "test":
            subject = "[TEST] " + subject
        messages.append((contact, build_message(settings, contact, subject, body)))
    results = send_messages(settings, messages)
    for contact, status, error in results:
        if status == "SENT":
            append_log(log_path, contact, status, error)
    return results


def execute_due_jobs(settings: Settings, log_path: Path, path: Path = SCHEDULE_PATH) -> list[tuple[ScheduledJob, list[tuple[Contact, str, str]]]]:
    completed: list[tuple[ScheduledJob, list[tuple[Contact, str, str]]]] = []
    for job in due_jobs(path=path):
        completed.append((job, execute_job(job, settings, log_path)))
        remove_job(job.job_id, path)
    return completed
