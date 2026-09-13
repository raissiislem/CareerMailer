"""Safe CLI for previewing, testing, and sending personalized applications."""

import argparse
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
import smtplib
import sys
import time

from config import PROJECT_ROOT, Settings, load_settings, require_env_configured, require_cv, require_smtp
from email_sender import Contact, append_log, build_message, generate_email, load_contacts, send_one_message
from scheduler import execute_due_jobs, parse_schedule_time, schedule_job

CSV_PATH = PROJECT_ROOT / "data" / "contacts.csv"
PREVIEW_DIR = PROJECT_ROOT / "output" / "preview"
LOG_PATH = PROJECT_ROOT / "output" / "send_log.csv"


def print_validation_errors(errors: list[str], duplicates: list[str]) -> None:
    if errors:
        print("CSV validation errors:")
        for error in errors:
            print(f"- {error}")
    if duplicates:
        print("Duplicate email addresses detected:")
        for email in duplicates:
            print(f"- {email}")


def prepare_messages(
    settings: Settings, contacts: list[Contact], attach_cv: bool
) -> list[tuple[Contact, EmailMessage, str, str]]:
    prepared = []
    for contact in contacts:
        subject, body = generate_email(contact.name, contact.company, contact.personalization)
        prepared.append(
            (contact, build_message(settings, contact, subject, body, attach_cv), subject, body)
        )
    return prepared


def preview(settings: Settings, prepared: list[tuple[Contact, EmailMessage, str, str]]) -> None:
    print("DRY RUN MODE\n")
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for index, (contact, _, subject, body) in enumerate(prepared, start=1):
        print(f"Recipient: {contact.name} <{contact.email}>")
        print(f"Company: {contact.company}\n")
        print(f"Subject:\n{subject}\n")
        print(f"Body:\n{body}\n")
        print(f"Attachment:\n{settings.cv_path.relative_to(PROJECT_ROOT)}\n")
        print("-" * 40)
        preview_file = PREVIEW_DIR / f"{index:03d}_{contact.email.replace('@', '_at_')}.eml"
        preview_file.write_bytes(prepared[index - 1][1].as_bytes())
    print(f"{len(prepared)} emails ready for review.")
    print(f"Preview files: {PREVIEW_DIR.relative_to(PROJECT_ROOT)}")


def send_mode(settings: Settings, contacts: list[Contact]) -> int:
    sent = skipped = errors = 0
    print("ONE-BY-ONE SEND MODE")
    for index, contact in enumerate(contacts, start=1):
        subject, body = generate_email(contact.name, contact.company, contact.personalization)
        print("\n" + "=" * 72)
        print(f"Contact {index}/{len(contacts)}: {contact.name} <{contact.email}>")
        print(f"Company: {contact.company}")
        print(f"Subject:\n{subject}\n")
        print(f"Body:\n{body}")
        print(f"\nAttachment: {settings.cv_path.relative_to(PROJECT_ROOT)}")
        print("=" * 72)
        action = input("[s]end, [k]skip, [q]uit: ").strip().lower()
        if action in {"q", "quit"}:
            print("Sending stopped by user.")
            break
        if action not in {"s", "send"}:
            skipped += 1
            print(f"SKIPPED: {contact.email}")
            continue
        try:
            message = build_message(settings, contact, subject, body)
            send_one_message(settings, message)
            append_log(LOG_PATH, contact, "SENT")
            sent += 1
            print(f"SENT: {contact.email}")
        except (OSError, smtplib.SMTPException) as exc:
            errors += 1
            print(f"FAILED: {contact.email} ({exc})")
        if settings.delay_seconds > 0 and index < len(contacts):
            time.sleep(settings.delay_seconds)
    print(f"\nSummary: {sent} sent, {skipped} skipped, {errors} errors.")
    return 1 if errors else 0


def test_mode(settings: Settings) -> int:
    require_smtp(settings)
    require_cv(settings)
    if not settings.test_email:
        raise ValueError("TEST_EMAIL is required for --test and must never be taken from the CSV.")
    test_contact = Contact("Test recipient", settings.test_email, "SMTP test")
    subject, body = generate_email(test_contact.name, test_contact.company)
    message = build_message(settings, test_contact, subject, body)
    message["Subject"] = "[TEST] " + subject
    print(f"Sending one SMTP test email only to {settings.test_email}.")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        import ssl
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    print("SMTP test email sent successfully.")
    return 0


def schedule_mode(
    settings: Settings,
    mode: str,
    run_at_text: str,
    contacts: list[Contact] | None = None,
) -> int:
    run_at = parse_schedule_time(run_at_text)
    if run_at <= datetime.now().astimezone():
        raise ValueError("Scheduled time must be in the future.")
    if mode == "send":
        require_smtp(settings)
        require_cv(settings)
    else:
        require_smtp(settings)
        require_cv(settings)
        if not settings.test_email:
            raise ValueError("TEST_EMAIL is required for a scheduled test.")
    selected = contacts or []
    count = len(selected) if mode == "send" else 1
    answer = input(f"Schedule {count} {mode} email(s) for {run_at.astimezone().isoformat()}? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Scheduling cancelled.")
        return 0
    job = schedule_job(
        mode,
        run_at,
        selected,
        subject=generate_email("Test recipient", "SMTP test")[0] if mode == "test" else "",
        test_email=settings.test_email,
    )
    print(f"Scheduled {mode} job {job.job_id} for {run_at.astimezone().isoformat()}.")
    print("No email was sent. Run `python main.py --run-scheduled` at or after that time.")
    return 0


def run_scheduled_mode(settings: Settings) -> int:
    require_smtp(settings)
    require_cv(settings)
    completed = execute_due_jobs(settings, LOG_PATH)
    if not completed:
        print("No scheduled jobs are due. No email was sent.")
        return 0
    for job, results in completed:
        sent = sum(status == "SENT" for _, status, _ in results)
        failed = len(results) - sent
        print(f"Executed {job.mode} job {job.job_id}: {sent} sent, {failed} failed.")
    return 1 if any(any(status == "FAILED" for _, status, _ in results) for _, results in completed) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or send personalized PFE application emails.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--send", action="store_true", help="send emails after explicit confirmation")
    mode.add_argument("--test", action="store_true", help="send one test email to TEST_EMAIL only")
    mode.add_argument("--gui", action="store_true", help="launch the PySide6 desktop application")
    mode.add_argument("--run-scheduled", action="store_true", help="execute scheduled jobs that are due")
    parser.add_argument("--schedule", metavar="ISO_TIME", help="schedule --send or --test instead of sending now")
    args = parser.parse_args()
    try:
        if args.gui:
            from gui.main_window import launch
            return launch()
        settings = load_settings()
        require_env_configured(settings)
        if args.schedule and not (args.send or args.test):
            raise ValueError("--schedule must be used with --send or --test.")
        if args.run_scheduled and args.schedule:
            raise ValueError("--run-scheduled cannot be combined with --schedule.")
        if args.run_scheduled:
            return run_scheduled_mode(settings)
        if args.test:
            if args.schedule:
                return schedule_mode(settings, "test", args.schedule)
            return test_mode(settings)
        validation = load_contacts(settings.contacts_path if settings.contacts_path else CSV_PATH)
        print_validation_errors(validation.errors, validation.duplicate_emails)
        if validation.errors or validation.duplicate_emails:
            print("\nFix the CSV before continuing. No emails were sent.")
            return 2
        if not validation.contacts:
            print("The CSV contains no contacts.")
            return 2
        if args.send:
            require_smtp(settings)
            require_cv(settings)
            if args.schedule:
                return schedule_mode(settings, "send", args.schedule, validation.contacts)
        prepared = prepare_messages(settings, validation.contacts, attach_cv=args.send)
        if args.send:
            return send_mode(settings, validation.contacts)
        preview(settings, prepared)
        return 0
    except (ValueError, FileNotFoundError, OSError, smtplib.SMTPException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
