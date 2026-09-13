"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
ATTACHMENTS_PATH = PROJECT_ROOT / "attachments"


@dataclass(frozen=True)
class Settings:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    sender_name: str
    sender_email: str
    cv_path: Path
    delay_seconds: float
    test_email: str
    contacts_path: Path


def load_settings() -> Settings:
    """Load .env values without exposing secrets in logs."""
    load_dotenv(ENV_PATH)

    port_text = os.getenv("SMTP_PORT", "587")
    delay_text = os.getenv("DELAY_SECONDS", "5")
    try:
        smtp_port = int(port_text)
        delay_seconds = float(delay_text)
    except ValueError as exc:
        raise ValueError("SMTP_PORT must be an integer and DELAY_SECONDS a number.") from exc

    configured_cv = _resolve_path(os.getenv("CV_PATH", "")) if os.getenv("CV_PATH", "").strip() else None
    cv_candidates = available_cv_paths()
    if configured_cv and configured_cv.is_file():
        cv_path = configured_cv
    elif cv_candidates:
        cv_path = cv_candidates[0]
    else:
        cv_path = configured_cv or _resolve_path("attachments/Islem_Raissi_CV_FR.pdf")

    return Settings(
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=smtp_port,
        smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        sender_name=os.getenv("SENDER_NAME", "").strip(),
        sender_email=os.getenv("SENDER_EMAIL", "").strip(),
        cv_path=cv_path,
        delay_seconds=delay_seconds,
        test_email=os.getenv("TEST_EMAIL", "").strip(),
        contacts_path=_resolve_path(os.getenv("CONTACTS_PATH", "data/contacts.csv")),
    )


def require_smtp(settings: Settings) -> None:
    """Raise a readable error when real SMTP settings are incomplete."""
    missing = [
        name
        for name, value in {
            "SMTP_HOST": settings.smtp_host,
            "SMTP_USERNAME": settings.smtp_username,
            "SMTP_PASSWORD": settings.smtp_password,
            "SENDER_NAME": settings.sender_name,
            "SENDER_EMAIL": settings.sender_email,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError("Missing SMTP configuration: " + ", ".join(missing))


def ensure_env_file() -> bool:
    """Create .env from the example once; return whether it was created."""
    if ENV_PATH.exists():
        return False
    if not ENV_EXAMPLE_PATH.exists():
        raise FileNotFoundError(".env is missing and .env.example is not available.")
    ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def environment_missing(settings: Settings) -> list[str]:
    """Return configuration keys that still need user values."""
    missing = [
        name
        for name, value in {
            "SMTP_HOST": settings.smtp_host,
            "SMTP_USERNAME": settings.smtp_username,
            "SMTP_PASSWORD": settings.smtp_password,
            "SENDER_NAME": settings.sender_name,
            "SENDER_EMAIL": settings.sender_email,
        }.items()
        if not value or "example.com" in value or value.startswith("your-") or value.startswith("replace-")
    ]
    return missing


def require_env_configured(settings: Settings) -> None:
    if not ENV_PATH.exists():
        raise ValueError(".env is not configured. Copy .env.example to .env and fill in your SMTP settings first.")
    missing = environment_missing(settings)
    if missing:
        raise ValueError("Configure .env first. Missing or placeholder values: " + ", ".join(missing))


def available_cv_paths() -> list[Path]:
    if not ATTACHMENTS_PATH.is_dir():
        return []
    return sorted(path for path in ATTACHMENTS_PATH.glob("*.pdf") if path.is_file())


def require_cv(settings: Settings) -> None:
    if not settings.cv_path.is_file():
        raise FileNotFoundError(
            f"CV file not found: {settings.cv_path}. "
            "Set CV_PATH in .env or add the file at that path."
        )


def save_settings(settings: Settings) -> None:
    """Persist editable GUI settings without writing secrets to application logs."""
    env_path = ENV_PATH
    values = {
        "SMTP_HOST": settings.smtp_host,
        "SMTP_PORT": str(settings.smtp_port),
        "SMTP_USERNAME": settings.smtp_username,
        "SMTP_PASSWORD": settings.smtp_password,
        "SENDER_NAME": settings.sender_name,
        "SENDER_EMAIL": settings.sender_email,
        "CV_PATH": _relative_or_absolute(settings.cv_path),
        "DELAY_SECONDS": str(settings.delay_seconds),
        "TEST_EMAIL": settings.test_email,
        "CONTACTS_PATH": _relative_or_absolute(settings.contacts_path),
    }
    env_path.write_text(
        "# CareerMailer settings. Keep this file private.\n"
        + "\n".join(f"{key}={value}" for key, value in values.items())
        + "\n",
        encoding="utf-8",
    )


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _resolve_path(value: str) -> Path:
    """Resolve relative configuration paths from the project, not the launch directory."""
    path = Path(value.strip()).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path
