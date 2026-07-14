import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app import config as cfg

from core.shared.email import send_test_email

from core.database.engine import Database


print("SMTP Config:", cfg.get_smtp_config())
print("Is SMTP configured:", cfg.is_smtp_configured())

db = Database()
res = send_test_email(
    to_addresses=["sumitkumar.nayak@licious.com"],
    username="Test Agent",
    custom_message="Hello, this is a diagnostic test of the email notification system.",
    db=db
)
print("Result of send_test_email:", res)
