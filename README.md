<p align="center">
  <img src="https://i.imgur.com/QE7p8ii.png" alt="CareerMailer logo" width="160">
</p>

<h1 align="center">CareerMailer</h1>

<p align="center">
  <a href="https://www.linkedin.com/in/islemraissi/">LinkedIn</a> ·
  <a href="https://islem-raissi-portfolio.vercel.app/">Portfolio</a>
</p>

---

## What is this?

CareerMailer is a personal, open-source Python desktop app (GUI + CLI) for sending personalized, individual "candidature spontanée" (unsolicited application) emails to HR contacts and recruiters — for an internship, a job, a freelance mission, or any professional outreach you're doing.

I built it for myself while job/internship hunting: I kept writing the same email over and over, tweaking a line here and there for each company, and manually attaching my CV every time. I realized this whole process — personalizing, previewing, attaching, sending one by one, tracking who I already contacted — could be automated. And honestly, I'm a bit lazy 😄. So I built a tool that does the repetitive part while keeping me fully in control of what actually gets sent.

CareerMailer is **not a mass-mailer or a spam tool**. Every message is sent individually, straight to one recipient's `To:` field. There's no bulk/group sending, no BCC blast. It's meant for the same use case as manually sending each email yourself — just faster, with previews, logs, and safety checks built in.

It's not tied to any specific field — it started as a Data Engineering PFE (end-of-studies internship) search tool, but it works the same way whether you're reaching out to HR for tech, marketing, finance, design, or anything else. You bring the leads and write (or generate) your personalization, and the app handles the sending workflow.

## How it works

### 1. You bring your leads

CareerMailer doesn't scrape or find contacts for you — you supply a list of people to reach out to. Create a CSV file named `contacts.csv` in the `data/` folder, with exactly these columns, in this order:

```csv
name,email,company,personalization
```

| Column | Meaning |
|---|---|
| `name` | The recruiter's / HR contact's name |
| `email` | Their email address |
| `company` | The company they work at |
| `personalization` | A short paragraph on why you specifically want to apply to that company |

### 2. Your email template

The `personalization` text gets inserted into your email template at the `{personalization}` placeholder. Here's the template I use by default, in `templates/email_template.txt` — feel free to fully rewrite it for your own situation, language, or field:

```
Bonjour {name},

{personalization}

Je m'appelle Islem Raissi, étudiant ingénieur en 4e année à ESPRIT et major de promotion. Je recherche un stage de fin d'études (PFE) de 6 mois à partir de janvier 2027, en Data Engineering, Data Analysis ou BI. Je reste ouvert selon les besoins de l'équipe.

Ce qui pourrait vous être utile :
- Projet data end-to-end pour une ONG, sur plusieurs années : pipelines, transformation, analyse et dashboards business & marketing
- Stack : Python, SQL, PostgreSQL, dbt, Airflow, Power BI, Docker, et actuellement en montée en compétences sur Spark et Databricks
- À l'aise aussi bien sur la partie construction de pipelines que sur l'analyse et la restitution des données — un profil polyvalent qui peut s'adapter aux besoins concrets d'une petite équipe data comme la vôtre

Basé en Tunisie, mobile partout en France, je gère moi-même les démarches de visa : côté entreprise, seule la convention de stage est nécessaire. Ouvert à une suite en CDI si l'opportunité se présente.

Mon CV est en pièce jointe. Disponible pour un échange si mon profil vous semble pertinent.

Bien cordialement,
Islem Raissi
```

`{name}`, `{company}`, and `{personalization}` are the placeholders the app fills in from your CSV. `{company}` doesn't have to appear in the body — it's also available if you want to reference it directly.

### An example of a real generated email

Given this CSV row:

```csv
name,email,company,personalization
Sophie Bernard,sophie.bernard@datawave.example,DataWave,"J'ai suivi le développement de vos pipelines de données temps réel et j'aimerais beaucoup contribuer à ce type de projets."
```

...the app would generate and preview exactly this message before anything is sent:

```
Objet : Candidature spontanée – PFE Data – Janvier 2027

Bonjour Sophie Bernard,

J'ai suivi le développement de vos pipelines de données temps réel et j'aimerais beaucoup contribuer à ce type de projets.

Je m'appelle Islem Raissi, étudiant ingénieur en 4e année à ESPRIT et major de promotion. Je recherche un stage de fin d'études (PFE) de 6 mois à partir de janvier 2027, en Data Engineering, Data Analysis ou BI. Je reste ouvert selon les besoins de l'équipe.

Ce qui pourrait vous être utile :
- Projet data end-to-end pour une ONG, sur plusieurs années : pipelines, transformation, analyse et dashboards business & marketing
- Stack : Python, SQL, PostgreSQL, dbt, Airflow, Power BI, Docker, et actuellement en montée en compétences sur Spark et Databricks
- À l'aise aussi bien sur la partie construction de pipelines que sur l'analyse et la restitution des données — un profil polyvalent qui peut s'adapter aux besoins concrets d'une petite équipe data comme la vôtre

Basé en Tunisie, mobile partout en France, je gère moi-même les démarches de visa : côté entreprise, seule la convention de stage est nécessaire. Ouvert à une suite en CDI si l'opportunité se présente.

Mon CV est en pièce jointe. Disponible pour un échange si mon profil vous semble pertinent.

Bien cordialement,
Islem Raissi
```

(CV attached automatically.) This preview is exactly what gets sent, nothing more — you'll see it before you confirm anything.

### 3. Finding and building your leads

You still need real contacts to put in `contacts.csv`. A few ways people do this:

- **Ask an LLM (Claude or ChatGPT).** If your LLM supports connectors/MCP, you can link it to a prospecting tool (for example, Vibe Prospecting) and ask it to find HR/recruiting contacts at companies matching criteria you give it — e.g. "give me HR contacts in Germany, Netherlands, and France working at Series-B fintech companies of 50–300 employees." Then explain your background and motivation to the LLM and ask it to produce a CSV with the `name,email,company,personalization` schema — including a written personalization line per company, based on what it found about each one.
- **Write it yourself.** Research companies manually and fill in the CSV directly.
- **Import from LinkedIn or elsewhere.** Export or copy contact/company info you've gathered from LinkedIn, job boards, or your own network into the same CSV format.

Whatever the source, the app only cares that `data/contacts.csv` follows the schema above.

## Installation

**Requirements:** Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Copy the example env file:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` (or use the GUI's **Settings** page, which creates `.env` for you automatically and walks you through setup):

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=your-smtp-password
SENDER_NAME=Your Name
SENDER_EMAIL=your-email@example.com
CV_PATH=attachments/your-cv.pdf
DELAY_SECONDS=5
TEST_EMAIL=your-personal-test-email@example.com
CONTACTS_PATH=data/contacts.csv
```

| Variable | Description |
|---|---|
| `SMTP_HOST` | Your email provider's SMTP server address (see below for Gmail/Outlook). |
| `SMTP_PORT` | SMTP port — use `587` for STARTTLS (the app always uses STARTTLS). |
| `SMTP_USERNAME` | Usually your full email address. |
| `SMTP_PASSWORD` | Your SMTP password or app password. Loaded from `.env`, never printed or logged. |
| `SENDER_NAME` | Display name shown to recipients. |
| `SENDER_EMAIL` | The "From" address — should match `SMTP_USERNAME` for most providers. |
| `CV_PATH` | Path to the PDF attached to every real and test email. |
| `DELAY_SECONDS` | Seconds to wait between each real send, to avoid tripping anti-spam limits. |
| `TEST_EMAIL` | The only address `--test` / the GUI test button will ever send to. |
| `CONTACTS_PATH` | Path to your contacts CSV file. |

The CLI refuses to run any feature until `.env` exists with real SMTP/sender values; it will print exactly what's missing.

### Gmail setup

Gmail requires an **App Password** — your normal password won't work.

1. Enable 2-Step Verification: `myaccount.google.com/security`.
2. Generate an app password at `myaccount.google.com/apppasswords` (choose "Mail" / "Other").
3. Use:

   ```dotenv
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=the-16-character-app-password
   SENDER_EMAIL=your-email@gmail.com
   ```

4. Gmail's default daily sending limit is around 500 emails for regular accounts — keep `DELAY_SECONDS` at 5+ for smaller volumes.

### Outlook / Microsoft 365 setup

1. If 2FA is enabled (recommended), create an app password at `account.microsoft.com/security` → "Advanced security options" → "App passwords."
2. Use:

   ```dotenv
   SMTP_HOST=smtp.office365.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@outlook.com
   SMTP_PASSWORD=your-password-or-app-password
   SENDER_EMAIL=your-email@outlook.com
   ```

3. Some organizational Microsoft 365 accounts disable SMTP AUTH by default — ask your admin to enable "Authenticated SMTP," or use an app password if MFA is enforced.

## Step-by-step: how to use CareerMailer

I'd recommend the **GUI** — it's simpler and guides you through every step. The CLI works the same way underneath, for people who prefer the terminal or want to automate/schedule things.

### Using the GUI (recommended)

```powershell
python main.py --gui
```

1. **First launch:** the app creates `.env` from `.env.example` and shows a short setup guide.
2. **Settings:** enter your SMTP details and sender info, pick your CV from `attachments/` (auto-selected if there's only one PDF), then click **Save settings**. Use the built-in connection test to confirm SMTP works.
3. **Contacts:** load `data/contacts.csv` (or another CSV). Invalid rows and duplicate emails are flagged and block sending — nothing gets silently skipped. You can edit contacts directly in the table.
4. **Email template:** edit the subject and body in the Email page, using `{name}`, `{company}`, and `{personalization}`.
5. **Preview:** see the exact, personalized message for each contact before anything is sent — identical to what will actually go out. Already-sent contacts (confirmed `SENT` in Logs) are excluded by default; toggle **Include already sent contacts** and click **Refresh previews** to bring them back.
6. **Confirm:** click **Confirm this email** for one message, or **Confirm all previews** for everything. Confirmed messages move to **Ready to send**.
7. **Ready to send:** review confirmed messages (one row per recipient). Click a row to see the full message. Send a single row, or select several and click **Send N selected** — both require typing `CONFIRM` and respect your configured delay. Sending happens in the background so the app stays responsive, and each sent contact is removed from this list.
8. **Logs:** check `output/send_log.csv` or the Logs page for timestamp, contact, company, status (`PREVIEW`, `SCHEDULED`, `SENT`, `FAILED`, `SKIPPED_DUPLICATE`), and error details for every attempt.
9. **Scheduling (optional):** you can schedule a campaign or a test email for a future time from either interface. The app won't send automatically when the time arrives — you (or `--run-scheduled` via a task scheduler) trigger the actual send.

### Using the CLI

**Safe preview** (no SMTP connection, nothing sent — generates `.eml` files in `output/preview/`):

```powershell
python main.py
```

**Test SMTP** (sends only to your `TEST_EMAIL`, never to CSV contacts):

```powershell
python main.py --test
```

**Real send** (sends individually to every valid CSV contact, after validating the CSV and CV and asking for confirmation):

```powershell
python main.py --send
```

**Schedule a real campaign:**

```powershell
python main.py --send --schedule "2026-09-14T18:30:00"
```

**Schedule the isolated test email:**

```powershell
python main.py --test --schedule "2026-09-14T18:30:00"
```

**Execute due scheduled jobs:**

```powershell
python main.py --run-scheduled
```

(Run this from Windows Task Scheduler if you want scheduled sends to fire while the GUI is closed.)

## Project structure

```text
CareerMailer/
├── data/contacts.csv
├── attachments/                 # Put your CV here
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

`data/contacts.example.csv` is included so the folder exists after cloning — copy it to `data/contacts.csv` and replace the rows with your own contacts. Your real `contacts.csv` is git-ignored, along with `.env`, `output/`, and PDFs in `attachments/`.

## Safety

- Real emails are never sent by default — the CLI does a dry run unless you pass `--send`, and the GUI requires typing `CONFIRM`/`SEND`.
- Test mode only ever sends to your explicit `TEST_EMAIL` — never to CSV recipients.
- Invalid and duplicate contacts can't be sent to.
- Each message goes individually to one `To:` address — never bulk/BCC.
- Sending large volumes too fast can trigger provider anti-spam systems — use a sensible `DELAY_SECONDS`, and please only use this for legitimate, personalized professional outreach.

## Security and Git safety

Never commit `.env`, SMTP passwords, real contact data, your CV, or generated logs. The included `.gitignore` already excludes `.env`, `output/`, Python cache files, and PDFs under `attachments/`. Always check `git status` before pushing to a public repo.

## Troubleshooting

- **SMTP authentication or connection failure:** double-check host, port, username, password, and your provider's STARTTLS/app-password requirements; use the GUI's connection test.
- **Missing CV:** select a real file in Settings or set `CV_PATH` in `.env`.
- **Invalid CSV or email:** keep the exact `name,email,company,personalization` header and fix any row errors the app shows.
- **Permission or attachment errors:** confirm the CSV, CV, and `output/` directory are readable/writable, and that the CV file isn't open elsewhere.

## Development

The GUI and CLI share `config.py` and `email_sender.py` — there's no separate mail-sending path for the GUI.

Syntax check:

```powershell
python -m py_compile config.py email_sender.py main.py gui/main_window.py gui/styles.py
```

Then run `python main.py` for a safe CLI preview.

---

If CareerMailer is useful to you, a ⭐ on the repo would mean a lot — thanks for checking it out!
