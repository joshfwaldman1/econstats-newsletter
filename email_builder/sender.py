"""
Gmail SMTP email sender for the EconStats Daily newsletter.

Ported from daily-news-tracker. Sends MIME multipart emails with
both HTML and plain-text versions via Gmail's SMTP server using
an App Password (not regular password).
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import EMAIL_RECIPIENT, EMAIL_SUBJECT_PREFIX, SMTP_PORT, SMTP_SERVER, get_env

logger = logging.getLogger(__name__)


def send_newsletter(html_body: str, plain_text_body: str) -> bool:
    """
    Send the newsletter email via Gmail SMTP.

    Args:
        html_body: Complete HTML email content.
        plain_text_body: Plain-text fallback content.

    Returns:
        True if sent successfully, False on failure.
    """
    gmail_address = get_env("GMAIL_ADDRESS")
    gmail_app_password = get_env("GMAIL_APP_PASSWORD")
    recipient = EMAIL_RECIPIENT

    # Build subject with today's date
    today = datetime.now().strftime("%a, %b %d %Y")
    subject = f"{EMAIL_SUBJECT_PREFIX} — {today}"

    # Construct MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"EconStats Daily <{gmail_address}>"
    msg["To"] = recipient

    # Attach both versions — email client picks the best one
    msg.attach(MIMEText(plain_text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, [recipient], msg.as_string())

        logger.info("Newsletter sent to %s (%s)", recipient, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD. "
            "Note: you need an App Password, not your regular Gmail password. "
            "Generate one at https://myaccount.google.com/apppasswords"
        )
        return False
    except smtplib.SMTPException:
        logger.error("SMTP error sending newsletter", exc_info=True)
        return False
    except Exception:
        logger.error("Unexpected error sending newsletter", exc_info=True)
        return False
