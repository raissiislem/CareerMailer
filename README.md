# CareerMailer

PFE Outreach is a small Python desktop application and CLI for reviewing and sending personalized, individual PFE (internship) applications to HR contacts. Every real message is sent separately to each recipient's `To:` field — never as a bulk/group email.

The tool is safe by default: the terminal command runs a dry run unless you pass `--send`, and the GUI requires you to type `SEND` before a real campaign starts.

## Features

- Modern PySide6 GUI, plus a full CLI
- CSV loading, search, sorting, validation, duplicate detection, and contact management
- Editable, personalized French email template with exact previews
- CV attached automatically to test and real messages
- SMTP settings with a built-in connection test and an isolated test-email recipient
- Background campaign sending with progress tracking and per-recipient failure reporting
- Configurable delay between emails, plus a CSV send log
- Persistent scheduling for campaigns and test emails
- Clear Send now / Schedule actions with confirmation details
- Safe dry-run mode and an explicit real-send confirmation step

## Project Structure

```text
CareerMailer/
├── data/contacts.csv
├── attachments/                 # Put a private CV here
├── templates/email_template.txt
├── output/preview/ and send_log.csv
├── gui/main_window.py
├── gui/styles.py
├── config.py
├── email_sender.py              # Shared validation, generation, SMTP, logging
├── main.py                      # CLI and --gui entry point
├── requirements.txt
├── .env.example
└── README.md
```

## Requirements

- Python 3.11 or newer

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Quick Start

1. Create and activate a virtual environment, then install dependencies (see [Installation](#installation)).
2. Copy `.env.example` to `.env` and fill in your SMTP settings (see [Configuration](#configuration) below).
3. Put your CV at `attachments/Islem_Raissi_CV_FR.pdf`, or choose another path in the GUI / set `CV_PATH`.
4. Replace the example rows in `data/contacts.csv` with your real contacts.
5. Run a safe preview:

   ```powershell
   python main.py
   ```

6. Review the terminal output and the `.eml` files generated in `output/preview/`.

## Adding Contacts

The default contacts file is `data/contacts.csv` (the GUI can also load a different CSV). It must have exactly these columns, in this order:

```csv
name,email,company,personalization
Marie Dupont,marie.dupont@example.com,ExampleTech,"J'ai vu que votre plateforme travaille sur des sujets data qui m'intéressent particulièrement."
Jean Martin,jean.martin@example.com,DataCorp,"Votre activité data correspond particulièrement au type de contexte que je recherche."
```

- One contact per row.
- `personalization` is inserted into `{personalization}` in the template. It may be empty, but quote values containing commas.
- Invalid rows and duplicate email addresses are flagged and **block sending** — they are never silently skipped.

## Adding a CV

Put one or more PDF files in `attachments/`. If there is exactly one PDF, it is selected automatically. If there are several, the GUI Settings page shows them in a dropdown; the first PDF is selected by default, and your choice is saved to `CV_PATH` in `.env`. You can change it later in the GUI or by editing `.env` manually. Both a real send (`--send`) and a test email (`--test`) stop with an error if the selected CV does not exist.

## Configuration

Copy the example file first:

```powershell
Copy-Item .env.example .env
```

The GUI creates `.env` automatically from `.env.example` if it does not exist, then shows a short setup guide at launch. Configure SMTP and sender values in **Settings** and click **Save settings**. The CLI refuses to run any feature until `.env` exists and contains real SMTP/sender values; it prints the missing configuration message instead.

Then edit `.env`. Here is what each line means:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=your-smtp-password
SENDER_NAME=Islem Raissi
SENDER_EMAIL=your-email@example.com
CV_PATH=attachments/Islem_Raissi_CV_FR.pdf
DELAY_SECONDS=5
TEST_EMAIL=your-personal-test-email@example.com
CONTACTS_PATH=data/contacts.csv
```

| Variable | Description |
|---|---|
| `SMTP_HOST` | Address of your email provider's SMTP server (see provider tables below). |
| `SMTP_PORT` | SMTP port. Use `587` for STARTTLS (the app always uses STARTTLS). |
| `SMTP_USERNAME` | Usually your full email address. |
| `SMTP_PASSWORD` | Your SMTP password or app password (see below). Loaded from `.env`, never printed or logged. |
| `SENDER_NAME` | Display name shown to recipients (e.g. `Islem Raissi`). |
| `SENDER_EMAIL` | The "From" address — should match `SMTP_USERNAME` for most providers. |
| `CV_PATH` | Path to the PDF attached to every real and test email. |
| `DELAY_SECONDS` | Seconds to wait between each real send, to avoid tripping anti-spam limits. |
| `TEST_EMAIL` | The only address `--test` / the GUI test button will ever send to. |
| `CONTACTS_PATH` | Path to the CSV file of contacts. |

### Setting up SMTP with Gmail

Gmail requires an **App Password** — your normal Google account password will not work.

1. Enable 2-Step Verification on your Google account: `myaccount.google.com/security`.
2. Go to `myaccount.google.com/apppasswords` and generate a new app password (choose "Mail" / "Other").
3. Use these values in `.env`:

   ```dotenv
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=the-16-character-app-password
   SENDER_EMAIL=your-email@gmail.com
   ```

4. Gmail's default daily sending limit is around 500 emails for regular accounts — keep `DELAY_SECONDS` reasonable (5+ seconds) for smaller volumes.

### Setting up SMTP with Outlook / Microsoft 365

1. If your account has 2-factor authentication enabled (recommended), create an app password at `account.microsoft.com/security` → "Advanced security options" → "App passwords."
2. Use these values in `.env`:

   ```dotenv
   SMTP_HOST=smtp.office365.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@outlook.com
   SMTP_PASSWORD=your-password-or-app-password
   SENDER_EMAIL=your-email@outlook.com
   ```

3. Some organizational Microsoft 365 accounts disable SMTP AUTH by default — if authentication fails, ask your admin to enable "Authenticated SMTP" for your mailbox, or use an app password if MFA is enforced.

## Running the Application

### GUI

```powershell
python main.py --gui
```

Workflow: load contacts → review validation → configure SMTP → select a CV → edit and save the template → manage contacts in the editable Contacts table → open **Preview** → click **Confirm this email** or **Confirm all previews**. Preview excludes contacts whose address already has a confirmed `SENT` entry in Logs; enable **Include already sent contacts** and click **Refresh previews** to bring them back with their current CSV information. Confirmed messages appear immediately in **Ready to send** as one row per recipient with timestamp, `To` address, **Delete**, and **Send** buttons. Clicking a row shows the confirmed message below. Send one row directly, or select multiple rows and click **Send N selected**; both actions require typing `CONFIRM` and use the configured delay. Sending removes the recipient from Ready to send and updates Logs and Contacts. Logs contain only confirmed `SENT` deliveries. Sending runs in a background thread, so the window stays responsive.

### CLI

**Safe preview** — no SMTP connection, nothing is sent:

```powershell
python main.py
```

**Test SMTP** — sends only to the configured `TEST_EMAIL`, never to CSV contacts:

```powershell
python main.py --test
```

**Real send** — sends individually to every valid CSV contact:

```powershell
python main.py --send
```

`--send` validates the entire CSV and the CV first, shows a confirmation prompt, and proceeds only if you answer `y` or `yes`. A failed individual send is logged but does not stop the rest of the campaign.

**Schedule a real campaign** without sending immediately:

```powershell
python main.py --send --schedule "2026-09-14T18:30:00"
```

**Schedule the isolated test email** using only `TEST_EMAIL`:

```powershell
python main.py --test --schedule "2026-09-14T18:30:00"
```

The schedule time uses ISO format. A timestamp without a timezone uses the computer's local timezone. Scheduling validates the configuration, asks for confirmation, and writes a pending job to `output/scheduled_jobs.json`; it does not contact SMTP. Execute due jobs explicitly:

```powershell
python main.py --run-scheduled
```

The GUI has equivalent scheduling controls and uses the same queue. The GUI does not send automatically when the scheduled time arrives; you must click the job's **Send** button. For command-line execution while the GUI is closed, run `--run-scheduled` from Windows Task Scheduler.

The **Ready to send** page is the app's local pre-final execution inbox. Standard SMTP sends immediately and cannot place a future message into Gmail or Outlook's native Scheduled folder. In the GUI, click the job's **Send** button when ready. From the CLI, scheduled jobs can be executed with `python main.py --run-scheduled`.

## Template, Preview, and Logs

Edit `templates/email_template.txt`, or use the Email page in the GUI. Supported placeholders are `{name}`, `{company}`, and `{personalization}`. The subject line can also be edited in the GUI; the default is:

```
Candidature spontanée – PFE Data – Janvier 2027
```

- The **Preview** page (GUI) or `output/preview/*.eml` files (CLI) show the exact personalized message that will be sent.
- The **Logs** page and `output/send_log.csv` record timestamp, contact, company, status, and error for every attempt.
- Possible statuses: `PREVIEW`, `SCHEDULED`, `SENT`, `FAILED`, `SKIPPED_DUPLICATE`.

## Safety

- Real emails are never sent by default.
- Test mode only ever sends to the explicit `TEST_EMAIL` (or GUI test-recipient field) — never to CSV recipients.
- Invalid and duplicate contacts cannot be sent to.
- Sending large volumes too quickly can trigger provider anti-spam systems — use a sensible `DELAY_SECONDS` and use this tool only for legitimate, personalized professional outreach.

## Security and Git Safety

Never commit `.env`, SMTP passwords, real contact data, private CV files, or generated logs. The included `.gitignore` excludes `.env`, `output/`, Python cache files, and PDF files under `attachments/`. Always review `git status` before pushing to a public repository.

## Troubleshooting

- **SMTP authentication or connection failure:** double-check host, port, username, password, and your provider's STARTTLS/app-password requirements; use the GUI's connection test.
- **Missing CV:** select a real file in Settings or set `CV_PATH` in `.env`.
- **Invalid CSV or email:** keep the exact `name,email,company` header and fix any row errors shown by the app.
- **Permission or attachment errors:** confirm the CSV, CV, and `output/` directory are readable/writable, and that the CV file isn't open/locked elsewhere.

## Development

The GUI and CLI share `config.py` and `email_sender.py` — there is no separate mail-sending path for the GUI.

Syntax check:

```powershell
python -m py_compile config.py email_sender.py main.py gui/main_window.py gui/styles.py
```

Then run `python main.py` for a safe CLI preview. Install `requirements.txt` before launching the GUI.