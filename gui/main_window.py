"""Modern desktop UI built on top of the shared CareerMailer services."""

from dataclasses import replace
from datetime import datetime
import csv
import os
from pathlib import Path
import smtplib
import traceback

from PySide6.QtCore import QObject, QDateTime, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QInputDialog, QMainWindow, QMessageBox, QPlainTextEdit,
    QDateTimeEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from config import Settings, available_cv_paths, ensure_env_file, environment_missing, load_settings, require_cv, require_env_configured, require_smtp, save_settings
from email_sender import (
    Contact, append_log, build_message, generate_email, load_contacts, save_contacts,
    send_messages, test_smtp_connection,
)
from scheduler import ScheduledJob, execute_job, list_scheduled_jobs, remove_contact_from_job, remove_job, schedule_job
from .styles import apply_theme


class Card(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")


def format_display_datetime(value: str | datetime) -> str:
    """Format internal ISO/local datetimes for the GUI without changing storage."""
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%d/%m/%Y - %H:%M")


class CampaignWorker(QObject):
    progress = Signal(int, int, str, str, str, str)
    finished = Signal(int, int)
    failed = Signal(str)

    def __init__(self, settings: Settings, prepared: list[tuple[Contact, object, str, str]]) -> None:
        super().__init__()
        self.settings = settings
        self.prepared = prepared

    def run(self) -> None:
        try:
            results = send_messages(
                self.settings,
                ((contact, message) for contact, message, _, _ in self.prepared),
            )
            sent = failed = 0
            for index, (contact, status, error) in enumerate(results, start=1):
                if status == "SENT":
                    append_log(Path(__file__).resolve().parent.parent / "output" / "send_log.csv", contact, status, error)
                if status == "SENT":
                    sent += 1
                else:
                    failed += 1
                self.progress.emit(index, len(results), contact.name, contact.email, status, error)
            self.finished.emit(sent, failed)
        except Exception:
            self.failed.emit(traceback.format_exc())


class SingleScheduledWorker(QObject):
    finished = Signal(int, int, str)
    failed = Signal(str)

    def __init__(self, settings: Settings, log_path: Path, job: ScheduledJob, removals: list[tuple[str, str]]) -> None:
        super().__init__()
        self.settings = settings
        self.log_path = log_path
        self.job = job
        self.removals = removals

    def run(self) -> None:
        try:
            results = execute_job(self.job, self.settings, self.log_path)
            sent = sum(status == "SENT" for _, status, _ in results)
            failed = sum(status == "FAILED" for _, status, _ in results)
            if failed == 0:
                for job_id, email in self.removals:
                    remove_contact_from_job(job_id, email)
            self.finished.emit(sent, failed, self.job.job_id)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PFE Outreach")
        self.resize(1540, 980)
        self.setMinimumSize(1120, 720)
        self.env_created = ensure_env_file()
        self.settings = load_settings()
        self.env_missing = environment_missing(self.settings)
        self.contacts = []
        self.validation_errors: list[str] = []
        self.duplicate_emails: list[str] = []
        self.current_preview_index = 0
        self.preview_overrides: dict[str, str] = {}
        self.preview_contact_email = ""
        self.execution_state = "No action chosen in Preview"
        self.execution_contacts: list[Contact] = []
        self.execution_job_id = ""
        self.template_path = Path(__file__).resolve().parent.parent / "templates" / "email_template.txt"
        self.log_path = Path(__file__).resolve().parent.parent / "output" / "send_log.csv"
        self._build_ui()
        self._load_template()
        self.refresh_contacts()
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.run_due_schedules)
        self.schedule_timer.start(30_000)
        if self.env_created or self.env_missing:
            QTimer.singleShot(250, self.show_configuration_guide)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame(objectName="sidebar")
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(280)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 20, 16, 16)
        brand = QLabel("PFE Outreach")
        brand.setObjectName("brand")
        side_layout.addWidget(brand)
        side_layout.addWidget(QLabel("CAMPAIGN WORKSPACE", objectName="navSection"))
        self.nav = QButtonGroupProxy()
        for label in ("Dashboard", "Contacts", "Email", "Preview", "Ready to send"):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, name=label: self.show_page(name))
            side_layout.addWidget(button)
            self.nav.buttons.append(button)
        side_layout.addSpacing(18)
        side_layout.addWidget(QLabel("DELIVERY", objectName="navSection"))
        for label in ("Settings", "Logs"):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, name=label: self.show_page(name))
            side_layout.addWidget(button)
            self.nav.buttons.append(button)
        self.nav.buttons[0].setChecked(True)
        side_layout.addStretch()
        side_layout.addWidget(QLabel("DRY RUN by default", objectName="muted"))
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(36, 30, 36, 24)
        content_layout.setSpacing(18)
        topbar = QFrame(objectName="topbar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(18, 12, 18, 12)
        topbar_layout.addWidget(QLabel("Outreach command center", objectName="topbarTitle"))
        topbar_layout.addStretch()
        self.mode_pill = QLabel("DRY RUN", objectName="modePill")
        topbar_layout.addWidget(self.mode_pill)
        topbar_layout.addWidget(QLabel("● Local workspace", objectName="workspaceStatus"))
        content_layout.addWidget(topbar)
        self.feedback = QLabel("Ready · dry-run mode")
        self.feedback.setObjectName("feedback")
        self.feedback.setWordWrap(True)
        content_layout.addWidget(self.feedback)
        self.stack = QStackedWidget()
        self.pages = {
            "Dashboard": self.dashboard_page(), "Contacts": self.contacts_page(),
            "Email": self.email_page(), "Preview": self.preview_page(),
            "Ready to send": self.scheduled_page(), "Settings": self.settings_page(), "Logs": self.logs_page(),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(sidebar)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([245, 1295])
        layout.addWidget(splitter)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready · dry run mode")

    def page_header(self, title: str, subtitle: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(6)
        title_label = QLabel(title, objectName="pageTitle")
        layout.addWidget(title_label)
        layout.addWidget(QLabel(subtitle, objectName="muted"))
        return layout

    def set_feedback(self, message: str, state: str = "ready") -> None:
        self.feedback.setText(message)
        self.feedback.setProperty("state", state)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def show_configuration_guide(self) -> None:
        missing = ", ".join(self.env_missing) if self.env_missing else "SMTP settings"
        QMessageBox.information(
            self,
            ".env configuration required",
            "A .env file was created from .env.example.\n\n"
            f"Configure these values first: {missing}.\n\n"
            "Open Settings, enter your SMTP credentials and sender details, then click Save settings. "
            "The application will not send or schedule mail until .env is configured.",
        )

    def dashboard_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Good morning, Islem", "Start here to check your contacts, message, and campaign readiness.")
        hero = QFrame(objectName="hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_copy = QVBoxLayout()
        hero_copy.addWidget(QLabel("Build thoughtful conversations.", objectName="heroTitle"))
        hero_copy.addWidget(QLabel("Review your contacts, perfect each message, then send with confidence.", objectName="heroSubtitle"))
        hero_layout.addLayout(hero_copy, 1)
        hero_action = QPushButton("Open preview", objectName="heroAction")
        hero_action.clicked.connect(lambda: self.show_page("Preview"))
        hero_layout.addWidget(hero_action, 0, Qt.AlignVCenter)
        layout.addWidget(hero)
        grid = QGridLayout(); grid.setSpacing(14)
        self.dashboard_values = {}
        for index, (key, label) in enumerate((("contacts", "Contacts loaded"), ("ready", "Ready to send"), ("attention", "Needs attention"), ("chosen", "Chosen for campaign"))):
            card = Card(); card.setProperty("accent", key); card_layout = QVBoxLayout(card); card_layout.setContentsMargins(18, 16, 18, 16); card_layout.addWidget(QLabel(label, objectName="cardLabel"))
            value = QLabel("0", objectName="cardValue"); card_layout.addWidget(value); self.dashboard_values[key] = value
            grid.addWidget(card, 0, index)
        layout.addLayout(grid)
        status_grid = QGridLayout(); status_grid.setSpacing(14)
        self.dashboard_status = {}
        for index, (key, label) in enumerate((("smtp", "SMTP"), ("cv", "CV"), ("mode", "Mode"), ("template", "Template"))):
            card = Card(); card_layout = QVBoxLayout(card); card_layout.setContentsMargins(18, 16, 18, 16); card_layout.addWidget(QLabel(label, objectName="cardLabel"))
            value = QLabel("Checking…"); card_layout.addWidget(value); self.dashboard_status[key] = value
            status_grid.addWidget(card, 0, index)
        layout.addLayout(status_grid); layout.addStretch(); page.setLayout(layout); return page

    def contacts_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Contacts", "Manage the CSV contact list. Changes are saved directly to the configured CSV file.")
        actions = QHBoxLayout(); self.search = QLineEdit(placeholderText="Search name, email, or company…"); self.search.textChanged.connect(self.filter_contacts)
        actions.addWidget(self.search, 1)
        load = QPushButton("Load CSV", objectName="primary"); load.clicked.connect(self.choose_csv); actions.addWidget(load)
        refresh = QPushButton("Refresh", objectName="secondary"); refresh.clicked.connect(self.refresh_contacts); actions.addWidget(refresh)
        open_csv = QPushButton("Open location", objectName="secondary"); open_csv.clicked.connect(self.open_csv_location); actions.addWidget(open_csv)
        instructions = QPushButton("CSV format", objectName="secondary"); instructions.clicked.connect(self.show_csv_instructions); actions.addWidget(instructions)
        add = QPushButton("Add contact", objectName="primary"); add.clicked.connect(self.add_contact); actions.addWidget(add)
        remove = QPushButton("Remove selected row", objectName="secondary"); remove.clicked.connect(self.remove_contact); actions.addWidget(remove)
        save = QPushButton("Save changes", objectName="primary"); save.clicked.connect(self.save_contact_changes); actions.addWidget(save)
        layout.addLayout(actions)
        self.contact_info = QLabel("", objectName="muted"); self.contact_info.setWordWrap(True); layout.addWidget(self.contact_info)
        self.contact_table = QTableWidget(0, 5); self.contact_table.setAlternatingRowColors(True); self.contact_table.setWordWrap(False); self.contact_table.setMinimumHeight(360); self.contact_table.setHorizontalHeaderLabels(("Name", "Email", "Company", "Personalization", "Mail history")); self.contact_table.setSortingEnabled(True); self.contact_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.contact_table.itemChanged.connect(self.contact_changed); layout.addWidget(self.contact_table, 1)
        page.setLayout(layout); return page

    def email_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Email", "Edit the subject and template. Preview shows the final personalized message for each contact.")
        form = QFormLayout(); self.subject_edit = QLineEdit(); form.addRow("Subject", self.subject_edit); layout.addLayout(form)
        self.template_edit = QPlainTextEdit(); self.template_edit.setMinimumHeight(420); self.template_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); layout.addWidget(self.template_edit, 1)
        layout.addWidget(QLabel("Available placeholders: {name}, {company}, and {personalization}. They are replaced for every contact.", objectName="muted"))
        buttons = QHBoxLayout(); save = QPushButton("Save template", objectName="primary"); save.clicked.connect(self.save_template); reset = QPushButton("Reset to default", objectName="secondary"); reset.clicked.connect(self._load_template); buttons.addWidget(save); buttons.addWidget(reset); buttons.addStretch(); layout.addLayout(buttons); page.setLayout(layout); return page

    def preview_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Preview", "Inspect messages for every contact, then choose Send now or Schedule. Contacts are managed in Contacts.")
        controls = QHBoxLayout(); self.preview_selector = QComboBox(); self.preview_selector.currentIndexChanged.connect(self.update_preview); controls.addWidget(self.preview_selector, 1); self.preview_include_sent = QCheckBox("Include already sent contacts"); self.preview_include_sent.stateChanged.connect(self.refresh_preview_contacts); controls.addWidget(self.preview_include_sent); refresh_preview = QPushButton("Refresh previews", objectName="secondary"); refresh_preview.clicked.connect(self.refresh_contacts); controls.addWidget(refresh_preview)
        previous = QPushButton("Previous", objectName="secondary"); previous.clicked.connect(lambda: self.move_preview(-1)); next_button = QPushButton("Next", objectName="secondary"); next_button.clicked.connect(lambda: self.move_preview(1)); controls.addWidget(previous); controls.addWidget(next_button); layout.addLayout(controls)
        card = Card(); card_layout = QVBoxLayout(card); self.preview_meta = QLabel(); self.preview_body = QPlainTextEdit(); self.preview_body.setPlaceholderText("Edit this personalized message before sending…"); self.preview_body.textChanged.connect(self.preview_body_changed); card_layout.addWidget(self.preview_meta); card_layout.addWidget(self.preview_body); layout.addWidget(card)
        actions = QHBoxLayout(); self.preview_confirm_button = QPushButton("Confirm this email", objectName="primary"); self.preview_confirm_button.clicked.connect(self.confirm_preview_email); self.preview_confirm_all_button = QPushButton("Confirm all previews", objectName="primary"); self.preview_confirm_all_button.clicked.connect(self.confirm_all_previews); reset_preview = QPushButton("Reset this message", objectName="secondary"); reset_preview.clicked.connect(self.reset_preview_message); actions.addWidget(self.preview_confirm_button); actions.addWidget(self.preview_confirm_all_button); actions.addWidget(reset_preview); actions.addStretch(); layout.addLayout(actions)
        guidance = QLabel("Edit the message, then confirm it to move it to Ready to send. From there you can send one or several confirmed mails.", objectName="muted")
        guidance.setWordWrap(True)
        layout.addWidget(guidance); page.setLayout(layout); return page

    def send_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Send", "Final execution status for the action chosen in Preview. No action is launched from this page automatically.")
        self.execution_state_label = QLabel(self.execution_state, objectName="feedback")
        self.execution_state_label.setWordWrap(True)
        layout.addWidget(self.execution_state_label)
        execution_card = Card(); execution_layout = QVBoxLayout(execution_card); execution_layout.addWidget(QLabel("Confirmed message from Preview", objectName="cardLabel")); self.execution_meta = QLabel("Nothing has been confirmed yet. Go to Preview and choose Send or Schedule."); self.execution_meta.setWordWrap(True); execution_layout.addWidget(self.execution_meta); self.execution_body = QPlainTextEdit(readOnly=True); self.execution_body.setPlaceholderText("The confirmed email will appear here."); execution_layout.addWidget(self.execution_body); layout.addWidget(execution_card, 1)
        self.send_summary = QLabel(); layout.addWidget(self.send_summary)
        warning = QLabel("⚠ Real emails will be sent to every valid, non-duplicate contact in the CSV."); warning.setStyleSheet("color:#a05a00; font-weight:700; padding:12px 0;"); layout.addWidget(warning)
        row = QHBoxLayout(); row.addWidget(QLabel("Delay between emails")); self.delay_spin = QSpinBox(); self.delay_spin.setRange(0, 3600); self.delay_spin.setSuffix(" seconds"); self.delay_spin.setValue(int(self.settings.delay_seconds)); self.delay_spin.valueChanged.connect(self.update_send_summary); row.addWidget(self.delay_spin); row.addStretch(); layout.addLayout(row)
        self.progress = QProgressBar(); self.progress.setRange(0, 1); self.progress.setValue(0); layout.addWidget(self.progress)
        self.activity = QListWidget(); layout.addWidget(self.activity)
        self.send_button = QPushButton("Choose an action in Preview", objectName="danger"); self.send_button.clicked.connect(self.confirm_and_send); layout.addWidget(self.send_button); page.setLayout(layout); return page

    def settings_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Settings", "Configure SMTP, sender details, test recipient, contacts file, and CV attachment.")
        form = QFormLayout(); self.setting_edits = {}
        fields = (("smtp_host", "SMTP host", False), ("smtp_port", "SMTP port", False), ("smtp_username", "SMTP username", False), ("smtp_password", "SMTP password", True), ("sender_name", "Sender name", False), ("sender_email", "Sender email", False), ("test_email", "Test recipient", False), ("contacts_path", "CSV path", False))
        for key, label, secret in fields:
            edit = QLineEdit(); edit.setText(str(getattr(self.settings, key))); edit.setEchoMode(QLineEdit.Password if secret else QLineEdit.Normal); self.setting_edits[key] = edit; form.addRow(label, edit)
        self.cv_combo = QComboBox()
        cv_paths = available_cv_paths()
        if self.settings.cv_path not in cv_paths:
            cv_paths.insert(0, self.settings.cv_path)
        for path in cv_paths:
            self.cv_combo.addItem(path.name, str(path))
        current_index = self.cv_combo.findData(str(self.settings.cv_path))
        self.cv_combo.setCurrentIndex(max(0, current_index))
        form.addRow("CV attachment", self.cv_combo)
        layout.addLayout(form)
        buttons = QHBoxLayout(); save = QPushButton("Save settings", objectName="primary"); save.clicked.connect(self.save_settings); test = QPushButton("Test SMTP connection", objectName="secondary"); test.clicked.connect(self.test_connection); test_email = QPushButton("Send test email", objectName="secondary"); test_email.clicked.connect(self.send_test_email); choose_cv = QPushButton("Choose CV", objectName="secondary"); choose_cv.clicked.connect(self.choose_cv); buttons.addWidget(save); buttons.addWidget(test); buttons.addWidget(test_email); buttons.addWidget(choose_cv); buttons.addStretch(); layout.addLayout(buttons); layout.addStretch(); page.setLayout(layout); return page

    def logs_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Logs", "Review previews, scheduled campaigns, successful sends, and delivery errors.")
        actions = QHBoxLayout(); self.log_search = QLineEdit(placeholderText="Search logs…"); self.log_search.textChanged.connect(self.filter_logs); actions.addWidget(self.log_search, 1); refresh = QPushButton("Refresh", objectName="secondary"); refresh.clicked.connect(self.refresh_logs); actions.addWidget(refresh); clear = QPushButton("Clear logs", objectName="secondary"); clear.clicked.connect(self.clear_logs); actions.addWidget(clear); actions.addStretch(); layout.addLayout(actions)
        self.log_table = QTableWidget(0, 6); self.log_table.setAlternatingRowColors(True); self.log_table.setWordWrap(False); self.log_table.setMinimumHeight(360); self.log_table.setHorizontalHeaderLabels(("Timestamp", "Name", "Email", "Company", "Status", "Error")); self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); layout.addWidget(self.log_table, 1); page.setLayout(layout); return page

    def scheduled_page(self) -> QWidget:
        page = QWidget(); layout = self.page_header("Ready to send", "Final step: review a confirmed message and click Send on its row when you are ready.")
        actions = QHBoxLayout(); refresh = QPushButton("Refresh ready mail", objectName="secondary"); refresh.clicked.connect(self.refresh_scheduled); actions.addWidget(refresh); actions.addStretch(); layout.addLayout(actions)
        layout.addWidget(QLabel("Messages stay here after Preview confirmation. They are not sent until you click Send. A successfully sent job is removed and appears in Logs and Contacts as Already sent.", objectName="muted"))
        self.scheduled_table = QTableWidget(0, 4); self.scheduled_table.setAlternatingRowColors(True); self.scheduled_table.setWordWrap(False); self.scheduled_table.setMinimumHeight(280); self.scheduled_table.setSelectionBehavior(QTableWidget.SelectRows); self.scheduled_table.setHorizontalHeaderLabels(("Confirmed", "To", "Delete", "Send")); self.scheduled_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.scheduled_table.itemSelectionChanged.connect(self.scheduled_row_selected); layout.addWidget(self.scheduled_table, 1)
        self.send_selected_button = QPushButton("Send selected", objectName="danger"); self.send_selected_button.clicked.connect(self.send_selected_ready); self.send_selected_button.setVisible(False); layout.addWidget(self.send_selected_button)
        detail_card = Card(); detail_layout = QVBoxLayout(detail_card); detail_layout.addWidget(QLabel("Confirmed message", objectName="cardLabel")); self.scheduled_detail = QPlainTextEdit(readOnly=True); self.scheduled_detail.setPlaceholderText("Click a ready-to-send row to review its confirmed message."); detail_layout.addWidget(self.scheduled_detail); layout.addWidget(detail_card, 1); page.setLayout(layout); return page

    def show_page(self, name: str) -> None:
        self.stack.setCurrentWidget(self.pages[name])
        for button in self.nav.buttons: button.setChecked(button.text() == name)
        if name == "Preview": self.update_preview()
        if name == "Ready to send": self.refresh_scheduled()
        if name == "Logs": self.refresh_logs()

    def refresh_contacts(self) -> None:
        self.set_feedback("Loading contacts…", "loading")
        QApplication.processEvents()
        result = load_contacts(self.settings.contacts_path)
        self.contacts, self.validation_errors, self.duplicate_emails = result.contacts, result.errors, result.duplicate_emails
        self.populate_contacts(); self.update_dashboard()
        self.update_preview()
        if result.errors:
            self.set_feedback(f"Loaded with attention · {len(result.errors)} issue(s) found in the CSV.", "error")
        else:
            self.set_feedback(f"Contacts ready · {len(self.contacts)} contact(s) loaded.", "success")
        self.statusBar().showMessage(f"Loaded {len(self.contacts)} contacts · {len(self.validation_errors)} issue(s)")

    def populate_contacts(self) -> None:
        sorting_enabled = self.contact_table.isSortingEnabled()
        self.contact_table.blockSignals(True)
        self.contact_table.setSortingEnabled(False)
        self.contact_table.setRowCount(0)
        for contact in self.contacts:
            row = self.contact_table.rowCount(); self.contact_table.insertRow(row)
            sent_emails = self.sent_email_addresses()
            for col, value in enumerate((contact.name, contact.email, contact.company, contact.personalization), start=0): self.contact_table.setItem(row, col, QTableWidgetItem(value))
            history = QTableWidgetItem("Already sent" if contact.email.casefold() in sent_emails else "Not sent yet")
            history.setFlags(history.flags() & ~Qt.ItemIsEditable)
            self.contact_table.setItem(row, 4, history)
        self.contact_table.setSortingEnabled(sorting_enabled)
        details = "<br>".join(self.validation_errors[:6])
        duplicate_text = "; ".join(self.duplicate_emails)
        message = f"CSV: {self.settings.contacts_path}\n{len(self.contacts)} contacts loaded · {len(self.sent_email_addresses())} already sent · {len(self.validation_errors)} issue(s)"
        if details: message += f"<br><b>Validation issues:</b> {details}"
        if duplicate_text: message += f"<br><b>Duplicate emails:</b> {duplicate_text}"
        self.contact_info.setText(message)

    def contact_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 4:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def filter_contacts(self, text: str) -> None:
        term = text.casefold()
        for row in range(self.contact_table.rowCount()): self.contact_table.setRowHidden(row, term not in " ".join(self.contact_table.item(row, col).text() for col in range(4)).casefold())

    def sent_email_addresses(self) -> set[str]:
        addresses: set[str] = set()
        if not self.log_path.is_file():
            return addresses
        try:
            with self.log_path.open(encoding="utf-8", newline="") as file:
                for record in csv.DictReader(file):
                    if record.get("status") == "SENT" and record.get("email"):
                        addresses.add(record["email"].casefold())
        except OSError:
            pass
        return addresses

    def add_contact(self) -> None:
        row = self.contact_table.rowCount()
        self.contact_table.insertRow(row)
        for column in range(4):
            self.contact_table.setItem(row, column, QTableWidgetItem(""))
        self.contact_table.setItem(row, 4, QTableWidgetItem("Not sent yet"))
        self.contact_table.selectRow(row)
        self.set_feedback("New contact added to the table. Fill the fields, then click Save changes.", "loading")

    def remove_contact(self) -> None:
        rows = sorted({index.row() for index in self.contact_table.selectedIndexes()}, reverse=True)
        if not rows:
            self.show_error("No contact selected", "Select a table row before removing it.")
            return
        for row in rows:
            self.contact_table.removeRow(row)
        self.save_contact_changes()

    def save_contact_changes(self) -> None:
        contacts: list[Contact] = []
        for row in range(self.contact_table.rowCount()):
            values = [self.contact_table.item(row, column).text().strip() for column in range(4)]
            contacts.append(Contact(*values))
        if any(not contact.name or not contact.email or not contact.company for contact in contacts):
            self.show_error("Incomplete contact", "Name, email, and company are required before saving.")
            return
        try:
            save_contacts(self.settings.contacts_path, contacts)
            self.refresh_contacts()
            self.set_feedback("Contacts saved to the CSV successfully.", "success")
        except OSError as exc:
            self.show_error("Could not save contacts", str(exc))

    def update_dashboard(self) -> None:
        self.dashboard_values["contacts"].setText(str(len(self.contacts))); self.dashboard_values["ready"].setText(str(len(self.contacts) - len(self.sent_email_addresses()))); self.dashboard_values["attention"].setText(str(len(self.validation_errors) + len(self.duplicate_emails))); self.dashboard_values["chosen"].setText(str(len(self.campaign_contacts())))
        self.dashboard_status["cv"].setText("✓ Ready" if self.settings.cv_path.is_file() else "⚠ Missing")
        self.dashboard_status["smtp"].setText("Configured" if all((self.settings.smtp_host, self.settings.smtp_username, self.settings.smtp_password, self.settings.sender_email)) else "⚠ Incomplete")
        self.dashboard_status["mode"].setText("Dry Run")
        self.dashboard_status["template"].setText("✓ Ready" if self.template_path.is_file() else "⚠ Missing")
        self.update_send_summary()

    def update_send_summary(self) -> None:
        valid_selected = self.campaign_contacts()
        if hasattr(self, "send_summary"): self.send_summary.setText(f"{len(valid_selected)} contacts in this campaign · {len(self.validation_errors) + len(self.duplicate_emails)} need attention")
        if hasattr(self, "send_button"):
            if self.execution_state.startswith("Scheduled"):
                self.send_button.setText("Already scheduled")
                self.send_button.setEnabled(False)
            elif self.execution_state.startswith("Sending"):
                self.send_button.setText("Sending…")
                self.send_button.setEnabled(False)
            elif self.execution_state.startswith("Sent"):
                self.send_button.setText("Campaign sent")
                self.send_button.setEnabled(False)
            else:
                self.send_button.setText("Choose Send now in Preview")
                self.send_button.setEnabled(bool(valid_selected))
        if hasattr(self, "preview_confirm_button"):
            self.preview_confirm_button.setEnabled(bool(valid_selected))
            self.preview_confirm_all_button.setEnabled(bool(valid_selected))

    def update_execution_plan(self, state: str, contacts: list[Contact], subject: str = "", body: str = "", job_id: str = "") -> None:
        self.execution_state = state
        self.execution_contacts = contacts
        self.execution_job_id = job_id
        if hasattr(self, "execution_state_label"):
            self.execution_state_label.setText(state)
            self.execution_meta.setText(
                f"Recipients: {len(contacts)}\nSubject: {subject}\nAttachment: {self.settings.cv_path.name}"
                + (f"\nJob: {job_id}" if job_id else "")
            )
            self.execution_body.setPlainText(body)
            self.update_send_summary()

    def campaign_contacts(self) -> list[Contact]:
        return [contact for contact in self.preview_contacts() if contact.email.casefold() not in self.duplicate_emails]

    def preview_contacts(self) -> list[Contact]:
        if hasattr(self, "preview_include_sent") and self.preview_include_sent.isChecked():
            return list(self.contacts)
        sent = self.sent_email_addresses()
        return [contact for contact in self.contacts if contact.email.casefold() not in sent]

    def _load_template(self) -> None:
        self.template_edit.setPlainText(self.template_path.read_text(encoding="utf-8") if self.template_path.is_file() else "")
        self.subject_edit.setText("Candidature spontanée – PFE Data – Janvier 2027")
        self.update_preview()

    def save_template(self) -> None:
        try:
            self.template_path.write_text(self.template_edit.toPlainText(), encoding="utf-8")
            self.set_feedback("Template saved successfully.", "success")
            self.statusBar().showMessage("Template saved")
        except OSError as exc: self.show_error("Could not save template", str(exc))

    def choose_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose contacts CSV", str(self.settings.contacts_path), "CSV files (*.csv)")
        if path: self.settings = replace(self.settings, contacts_path=Path(path)); self.settings_page_refresh(); self.refresh_contacts()

    def open_csv_location(self) -> None:
        path = self.settings.contacts_path
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent if path.parent.exists() else path)))

    def show_csv_instructions(self) -> None:
        QMessageBox.information(self, "CSV format", "Use exactly these columns:\n\nname,email,company,personalization\n\nThe personalization text is inserted into {personalization}. Quote values containing commas. Invalid rows and duplicate email addresses cannot be sent.")

    def choose_cv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose CV", str(self.settings.cv_path), "PDF files (*.pdf);;All files (*)")
        if path:
            existing = self.cv_combo.findData(path)
            if existing < 0:
                self.cv_combo.addItem(Path(path).name, path)
                existing = self.cv_combo.findData(path)
            self.cv_combo.setCurrentIndex(existing)
            self.save_settings()

    def settings_page_refresh(self) -> None:
        self.setting_edits["contacts_path"].setText(str(self.settings.contacts_path))

    def save_settings(self) -> None:
        try:
            selected_cv = Path(self.cv_combo.currentData())
            self.settings = replace(self.settings, smtp_host=self.setting_edits["smtp_host"].text().strip(), smtp_port=int(self.setting_edits["smtp_port"].text()), smtp_username=self.setting_edits["smtp_username"].text().strip(), smtp_password=self.setting_edits["smtp_password"].text(), sender_name=self.setting_edits["sender_name"].text().strip(), sender_email=self.setting_edits["sender_email"].text().strip(), test_email=self.setting_edits["test_email"].text().strip(), contacts_path=Path(self.setting_edits["contacts_path"].text().strip()), cv_path=selected_cv, delay_seconds=float(self.delay_spin.value()))
            save_settings(self.settings); self.env_missing = environment_missing(self.settings); self.update_dashboard(); self.refresh_contacts(); self.set_feedback("Settings saved successfully.", "success"); self.statusBar().showMessage("Settings saved")
        except (ValueError, OSError) as exc: self.show_error("Could not save settings", str(exc))

    def test_connection(self) -> None:
        try:
            self.set_feedback("Testing SMTP connection…", "loading")
            QApplication.processEvents()
            require_smtp(self.settings); test_smtp_connection(self.settings); self.set_feedback("SMTP connection successful. No email was sent.", "success"); QMessageBox.information(self, "SMTP connection", "✓ SMTP authentication successful. No email was sent.")
        except Exception as exc: self.show_error("SMTP connection failed", str(exc))

    def send_test_email(self) -> None:
        try:
            self.save_settings()
            require_smtp(self.settings); require_cv(self.settings)
            if not self.settings.test_email: raise ValueError("Enter a test recipient first.")
            if QMessageBox.question(self, "Send test email", f"Send one test email only to:\n{self.settings.test_email}\n\nAttachment: {self.settings.cv_path.name}") != QMessageBox.Yes: return
            contact = Contact("Test recipient", self.settings.test_email, "SMTP test")
            subject, body = generate_email(contact.name, contact.company, contact.personalization, self.template_path, self.subject_edit.text())
            message = build_message(self.settings, contact, "[TEST] " + subject, body)
            import ssl
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp:
                smtp.starttls(context=ssl.create_default_context()); smtp.login(self.settings.smtp_username, self.settings.smtp_password); smtp.send_message(message)
            QMessageBox.information(self, "Test email", "✓ Test email sent successfully.")
        except Exception as exc: self.show_error("Test email failed", str(exc))

    def schedule_test_email(self) -> None:
        try:
            self.save_settings()
            require_smtp(self.settings); require_cv(self.settings)
            if not self.settings.test_email: raise ValueError("Enter a test recipient first.")
            run_at = self.schedule_time.dateTime().toPython()
            if QMessageBox.question(self, "Schedule test email", f"Schedule one test email for {format_display_datetime(run_at)}?\nTo: {self.settings.test_email}\n\nNo email will be sent now.") != QMessageBox.Yes: return
            job = schedule_job("test", run_at, [], subject=self.subject_edit.text(), template_path=self.template_path, test_email=self.settings.test_email)
            self.statusBar().showMessage(f"Test email scheduled for {format_display_datetime(run_at)} · job {job.job_id}")
        except Exception as exc: self.show_error("Could not schedule test email", str(exc))

    def update_preview(self, index: int = 0) -> None:
        contacts = self.preview_contacts()
        if not contacts: self.preview_meta.setText("No unsent contacts available. Enable 'Include already sent contacts' and refresh if needed."); self.preview_body.clear(); return
        if self.preview_contact_email:
            self.preview_overrides[self.preview_contact_email] = self.preview_body.toPlainText()
        self.preview_selector.blockSignals(True); self.preview_selector.clear()
        for contact in contacts: self.preview_selector.addItem(f"{contact.name} · {contact.email}")
        self.preview_selector.setCurrentIndex(max(0, min(index, len(contacts) - 1))); self.preview_selector.blockSignals(False)
        contact = contacts[self.preview_selector.currentIndex()]; subject, body = generate_email(contact.name, contact.company, contact.personalization, self.template_path, self.subject_edit.text() or "Candidature spontanée")
        self.preview_contact_email = contact.email.casefold()
        body = self.preview_overrides.get(self.preview_contact_email, body)
        self.preview_meta.setWordWrap(True)
        self.preview_meta.setText(f"To: {contact.name} <{contact.email}>\nCompany: {contact.company}\nSubject: {subject}\nAttachment: {'✓ ' + self.settings.cv_path.name if self.settings.cv_path.is_file() else '⚠ CV missing'}")
        self.preview_body.setPlainText(body)

    def preview_body_changed(self) -> None:
        if self.preview_contact_email:
            self.preview_overrides[self.preview_contact_email] = self.preview_body.toPlainText()

    def reset_preview_message(self) -> None:
        self.preview_overrides.pop(self.preview_contact_email, None)
        current = self.preview_selector.currentIndex()
        self.preview_contact_email = ""
        self.update_preview(current)
        self.set_feedback("Preview reset from the saved template.", "success")

    def move_preview(self, direction: int) -> None: self.update_preview(self.preview_selector.currentIndex() + direction)

    def refresh_preview_contacts(self) -> None:
        self.update_preview(0)

    def confirm_and_send(self) -> None:
        selected = self.campaign_contacts()
        if not selected:
            QMessageBox.information(self, "No contacts ready", "There are no valid, non-duplicate contacts available to send.")
            self.set_feedback("No valid contacts are ready to send.", "error")
            return
        try: require_smtp(self.settings); require_cv(self.settings)
        except Exception as exc: self.show_error("Campaign cannot start", str(exc)); return
        contact = selected[0]
        subject, body = generate_email(contact.name, contact.company, contact.personalization, self.template_path, self.subject_edit.text() or "Candidature spontanée")
        body = self.preview_overrides.get(contact.email.casefold(), body)
        dialog = QDialog(self); dialog.setWindowTitle("Confirm real sending"); dialog.resize(680, 560); form = QVBoxLayout(dialog)
        form.addWidget(QLabel(f"You are about to send {len(selected)} individual email(s).\nThe preview below is the first selected message.\n\nTo: {contact.name} <{contact.email}>\nCompany: {contact.company}\nSubject: {subject}\nAttachment: {self.settings.cv_path.name}"))
        details = QPlainTextEdit(readOnly=True); details.setPlainText(body); form.addWidget(details)
        form.addWidget(QLabel("Type SEND to confirm real delivery.")); confirm = QLineEdit(); form.addWidget(confirm); buttons = QHBoxLayout(); cancel = QPushButton("Cancel", objectName="secondary"); send = QPushButton("Send emails", objectName="danger"); send.setEnabled(False); confirm.textChanged.connect(lambda text: send.setEnabled(text == "SEND")); cancel.clicked.connect(dialog.reject); send.clicked.connect(dialog.accept); buttons.addWidget(cancel); buttons.addWidget(send); form.addLayout(buttons)
        if dialog.exec() == QDialog.Accepted: self.start_campaign(selected)

    def confirm_preview_email(self) -> None:
        if not self.contacts:
            self.show_error("No contacts loaded", "Load at least one contact before confirming.")
            return
        contact = self.preview_contacts()[self.preview_selector.currentIndex()]
        self.confirm_preview_contacts([contact], "this email")

    def confirm_all_previews(self) -> None:
        self.confirm_preview_contacts(self.campaign_contacts(), "all previews")

    def confirm_preview_contacts(self, selected: list[Contact], scope_label: str) -> None:
        if not selected:
            self.show_error("No contacts ready", "There are no valid contacts to confirm.")
            return
        overrides = {contact.email.casefold(): self.preview_overrides[contact.email.casefold()] for contact in selected if contact.email.casefold() in self.preview_overrides}
        job = schedule_job("send", datetime.now().astimezone(), selected, subject=self.subject_edit.text(), template_path=self.template_path, body_overrides=overrides)
        self.set_feedback(f"Confirmed · {len(selected)} email(s) moved to Ready to send.", "success")
        self.show_page("Ready to send")

    def run_due_schedules(self) -> None:
        # The GUI never sends silently when a time arrives. The user must click Send.
        self.refresh_scheduled()

    def show_scheduled_job(self, job: ScheduledJob, email: str = "") -> None:
        if not job.contacts:
            self.scheduled_detail.setPlainText(f"Test email to: {job.test_email}\nSubject: [TEST] {job.subject}")
            return
        contact_data = next((item for item in job.contacts if item["email"].casefold() == email.casefold()), job.contacts[0])
        contact = Contact(**contact_data)
        subject, body = generate_email(contact.name, contact.company, contact.personalization, Path(job.template_path) if job.template_path else self.template_path, job.subject)
        body = (job.body_overrides or {}).get(contact.email.casefold(), body)
        self.scheduled_detail.setPlainText(f"To: {contact.name} <{contact.email}>\nCompany: {contact.company}\nSubject: {subject}\nAttachment: {self.settings.cv_path.name}\n\n{body}")

    def send_scheduled_job(self, job: ScheduledJob, email: str = "") -> None:
        scheduled_at = datetime.fromisoformat(job.run_at.replace("Z", "+00:00"))
        if scheduled_at > datetime.now(scheduled_at.tzinfo):
            QMessageBox.information(
                self,
                "Not ready yet",
                f"This mail is scheduled for {format_display_datetime(job.run_at)}.\n\n"
                "It cannot be sent before that time and remains in Ready to send. "
                "To send immediately, go back to Preview and choose Send this campaign now.",
            )
            self.set_feedback(f"Waiting until {format_display_datetime(job.run_at)} before sending.", "loading")
            return
        removals = []
        if email and job.contacts:
            selected = [item for item in job.contacts if item["email"].casefold() == email.casefold()]
            removals = [(job.job_id, email)]
            job = replace(job, contacts=selected)
        recipient_count = len(job.contacts) if job.contacts else 1
        answer, ok = QInputDialog.getText(self, "Final send confirmation", f"Send this ready-to-send mail now?\n\nRecipients: {recipient_count}\n\nType CONFIRM to send:")
        if not ok or answer.strip() != "CONFIRM":
            return
        self.set_feedback(f"Sending ready job {job.job_id}…", "loading")
        self.scheduled_thread = QThread(self)
        self.scheduled_worker = SingleScheduledWorker(self.settings, self.log_path, job, removals)
        self.scheduled_worker.moveToThread(self.scheduled_thread)
        self.scheduled_thread.started.connect(self.scheduled_worker.run)
        self.scheduled_worker.finished.connect(self.scheduled_job_finished)
        self.scheduled_worker.failed.connect(lambda error: self.show_error("Scheduled send failed", error))
        self.scheduled_worker.finished.connect(self.scheduled_thread.quit)
        self.scheduled_worker.failed.connect(self.scheduled_thread.quit)
        self.scheduled_thread.finished.connect(self.scheduled_worker.deleteLater)
        self.scheduled_thread.finished.connect(self.scheduled_thread.deleteLater)
        self.scheduled_thread.finished.connect(lambda: delattr(self, "scheduled_thread"))
        self.scheduled_thread.start()

    def scheduled_job_finished(self, sent: int, failed: int, job_id: str) -> None:
        self.refresh_scheduled()
        self.refresh_logs()
        self.refresh_contacts()
        if failed == 0:
            self.set_feedback(f"Sent successfully · {sent} email(s).", "success")
            self.statusBar().showMessage(f"Ready job {job_id} sent and removed")
        else:
            self.set_feedback(f"Send completed with {failed} error(s). The job remains available.", "error")

    def delete_scheduled_contact(self, job: ScheduledJob, email: str = "") -> None:
        target = email or job.test_email
        if QMessageBox.question(self, "Delete ready mail", f"Remove the ready mail for {target}?\n\nIt will not be sent.") != QMessageBox.Yes:
            return
        remove_contact_from_job(job.job_id, target)
        self.refresh_scheduled()
        self.set_feedback("Ready mail removed without sending.", "success")

    def scheduled_row_selected(self) -> None:
        rows = self.scheduled_table.selectionModel().selectedRows()
        self.send_selected_button.setVisible(bool(rows))
        if rows:
            self.send_selected_button.setText(f"Send {len(rows)} selected")
        if not rows or rows[0].row() >= len(self.ready_rows):
            return
        job, email = self.ready_rows[rows[0].row()]
        self.show_scheduled_job(job, email)

    def send_selected_ready(self) -> None:
        rows = self.scheduled_table.selectionModel().selectedRows()
        if not rows:
            return
        selected_rows = [self.ready_rows[index.row()] for index in rows if index.row() < len(self.ready_rows)]
        contacts = []
        removals = []
        first_job = selected_rows[0][0]
        overrides: dict[str, str] = {}
        for job, email in selected_rows:
            item = next((value for value in job.contacts if value["email"].casefold() == email.casefold()), None)
            if item:
                contacts.append(item)
                removals.append((job.job_id, email))
                if job.body_overrides and email.casefold() in job.body_overrides:
                    overrides[email.casefold()] = job.body_overrides[email.casefold()]
        if not contacts:
            return
        answer, ok = QInputDialog.getText(self, "Confirm selected sends", f"Send {len(contacts)} selected mails now? Type CONFIRM:")
        if not ok or answer.strip() != "CONFIRM":
            return
        combined = replace(first_job, job_id=f"batch-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", contacts=contacts, body_overrides=overrides)
        self.set_feedback(f"Sending {len(contacts)} selected mail(s)…", "loading")
        self.scheduled_thread = QThread(self)
        self.scheduled_worker = SingleScheduledWorker(self.settings, self.log_path, combined, removals)
        self.scheduled_worker.moveToThread(self.scheduled_thread)
        self.scheduled_thread.started.connect(self.scheduled_worker.run)
        self.scheduled_worker.finished.connect(self.scheduled_job_finished)
        self.scheduled_worker.failed.connect(lambda error: self.show_error("Selected send failed", error))
        self.scheduled_worker.finished.connect(self.scheduled_thread.quit)
        self.scheduled_worker.failed.connect(self.scheduled_thread.quit)
        self.scheduled_thread.finished.connect(self.scheduled_worker.deleteLater)
        self.scheduled_thread.finished.connect(self.scheduled_thread.deleteLater)
        self.scheduled_thread.finished.connect(lambda: delattr(self, "scheduled_thread"))
        self.scheduled_thread.start()

    def start_campaign(self, selected: list[Contact]) -> None:
        prepared = []
        for contact in selected:
            subject, body = generate_email(contact.name, contact.company, contact.personalization, self.template_path, self.subject_edit.text())
            body = self.preview_overrides.get(contact.email.casefold(), body)
            prepared.append((contact, build_message(self.settings, contact, subject, body), subject, body))
        first_contact, _, first_subject, first_body = prepared[0]
        self.update_execution_plan(f"Sending now · {len(selected)} email(s)", selected, first_subject, first_body)
        self.set_feedback(f"Sending {len(prepared)} email(s)…", "loading")
        self.preview_confirm_button.setEnabled(False)
        self.preview_confirm_all_button.setEnabled(False)
        self.thread = QThread(self); self.worker = CampaignWorker(self.settings, prepared); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.campaign_progress); self.worker.finished.connect(self.campaign_finished); self.worker.failed.connect(lambda error: self.show_error("Campaign failed", error)); self.worker.finished.connect(self.thread.quit); self.thread.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater); self.thread.start()

    def campaign_progress(self, index: int, total: int, name: str, email: str, status: str, error: str) -> None: self.progress.setValue(index); self.activity.addItem(f"{index}/{total}  {'✓' if status == 'SENT' else '✕'} {name} · {email}" + (f" · {error}" if error else "")); self.activity.scrollToBottom()

    def campaign_finished(self, sent: int, failed: int) -> None:
        self.set_feedback(f"Campaign finished · {sent} sent · {failed} failed.", "success" if failed == 0 else "error")
        self.statusBar().showMessage(f"Campaign finished · {sent} sent · {failed} failed")
        self.update_preview()
        QMessageBox.information(self, "Campaign finished", f"✓ {sent} emails sent\n✕ {failed} emails failed")

    def refresh_logs(self) -> None:
        self.log_table.setRowCount(0)
        if not self.log_path.is_file():
            self.statusBar().showMessage(f"No log file yet: {self.log_path}")
            return
        try:
            with self.log_path.open(encoding="utf-8", newline="") as file:
                for record in csv.DictReader(file):
                    if record.get("status") != "SENT":
                        continue
                    row = self.log_table.rowCount(); self.log_table.insertRow(row)
                    for column, key in enumerate(("timestamp", "name", "email", "company", "status", "error")):
                        value = record.get(key, "")
                        if key == "timestamp" and value:
                            try: value = format_display_datetime(value)
                            except ValueError: pass
                        self.log_table.setItem(row, column, QTableWidgetItem(value))
            self.set_feedback(f"Logs loaded successfully · {self.log_table.rowCount()} entr(y/ies).", "success")
            self.statusBar().showMessage(f"Loaded {self.log_table.rowCount()} log entries from {self.log_path}")
        except OSError as exc: self.show_error("Could not read logs", str(exc))

    def refresh_scheduled(self) -> None:
        self.scheduled_table.setRowCount(0)
        self.ready_rows: list[tuple[ScheduledJob, str]] = []
        for job in list_scheduled_jobs():
            recipients = [job.test_email] if job.mode == "test" else [item["email"] for item in job.contacts]
            for email in recipients:
                row = self.scheduled_table.rowCount(); self.scheduled_table.insertRow(row)
                self.ready_rows.append((job, email))
                self.scheduled_table.setItem(row, 0, QTableWidgetItem(format_display_datetime(job.run_at)))
                self.scheduled_table.setItem(row, 1, QTableWidgetItem(email))
                delete_button = QPushButton("Delete", objectName="secondary")
                delete_button.clicked.connect(lambda checked=False, current_job=job, current_email=email: self.delete_scheduled_contact(current_job, current_email))
                self.scheduled_table.setCellWidget(row, 2, delete_button)
                scheduled_at = datetime.fromisoformat(job.run_at.replace("Z", "+00:00"))
                is_due = scheduled_at <= datetime.now(scheduled_at.tzinfo)
                send_button = QPushButton("Send" if is_due else "Not ready", objectName="danger" if is_due else "secondary")
                send_button.setEnabled(is_due)
                if not is_due:
                    send_button.setToolTip(f"Available on {format_display_datetime(job.run_at)}")
                send_button.clicked.connect(lambda checked=False, current_job=job, current_email=email: self.send_scheduled_job(current_job, current_email))
                self.scheduled_table.setCellWidget(row, 3, send_button)
        if self.scheduled_table.rowCount() == 0:
            self.scheduled_detail.setPlainText("No ready-to-send messages. Confirm a message in Preview first.")
        elif self.scheduled_table.rowCount() > 0:
            self.scheduled_table.selectRow(0)
            self.show_scheduled_job(*self.ready_rows[0])

    def filter_logs(self, text: str) -> None:
        term = text.casefold()
        for row in range(self.log_table.rowCount()):
            values = " ".join(self.log_table.item(row, column).text() for column in range(self.log_table.columnCount()))
            self.log_table.setRowHidden(row, term not in values.casefold())

    def clear_logs(self) -> None:
        if QMessageBox.question(self, "Clear logs", "Delete the local send log?") == QMessageBox.Yes:
            try: self.log_path.unlink(missing_ok=True); self.refresh_logs()
            except OSError as exc: self.show_error("Could not clear logs", str(exc))

    def show_error(self, title: str, message: str) -> None:
        self.set_feedback(f"{title}: {message}", "error")
        QMessageBox.critical(self, title, message)


class QButtonGroupProxy:
    def __init__(self) -> None: self.buttons: list[QPushButton] = []


def launch() -> int:
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    window = MainWindow(); window.show()
    return app.exec()
