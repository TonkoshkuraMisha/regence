# --- FILE: src/services/mailer.py ---
"""
Sending e-mails (task 17.5) via standard SMTP: any transactional mail provider (Brevo, Amazon SES,
Postmark, Mailgun...) or your own server fits -- only the SMTP_* variables in .env change. Without SMTP_HOST the e-mail is
not sent
but written to the log together with the link: this is how development and tests work.

The e-mail texts are here, in the three interface languages: an e-mail is read outside the client, the frontend catalogues
are unavailable to it.
This is a deliberate exception to the rule "not a single player-facing string on the server".

Who calls it: src/services/email_links.py -- address confirmation and password reset; it also issues the one-time link
and passes it to the template. Settings (src/core/config.py): SMTP_HOST, SMTP_PORT, SMTP_STARTTLS, SMTP_USER,
SMTP_PASSWORD, MAIL_FROM.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Literal

from src.core.config import settings

logger = logging.getLogger(__name__)

Language = Literal["en", "uk"]
LANGUAGES: tuple[Language, ...] = ("en", "uk")
Kind = Literal["verify", "reset"]

# E-mail kind -> language -> (subject, body). Template parameters: {username} -- the player's name, {link} -- the one-time
# link,
# {hours} -- its validity period in hours (from EMAIL_VERIFY_TTL_S and PASSWORD_RESET_TTL_S, computed by email_links.py).
TEMPLATES: dict[Kind, dict[Language, tuple[str, str]]] = {
    "verify": {
        "en": ("Confirm your e-mail for regence",
               "Hello, {username}!\n\nTo confirm this address for your regence account, open the link:\n{link}\n\n"
               "The link works for {hours} h. If you did not ask for it, just ignore this letter."),
        "uk": ("Підтвердіть e-mail для regence",
               "Вітаємо, {username}!\n\nЩоб підтвердити цю адресу для акаунта regence, відкрийте посилання:\n{link}\n\n"
               "Посилання діє {hours} год. Якщо ви цього не просили, просто проігноруйте лист."),
    },
    "reset": {
        "en": ("Reset your regence password",
               "Hello, {username}!\n\nTo set a new password, open the link:\n{link}\n\n"
               "The link works for {hours} h and only once. If you did not ask to reset the password, ignore this "
               "letter: your password stays the same."),
        "uk": ("Скидання пароля regence",
               "Вітаємо, {username}!\n\nЩоб задати новий пароль, відкрийте посилання:\n{link}\n\n"
               "Посилання діє {hours} год і лише один раз. Якщо ви не просили скинути пароль, проігноруйте лист: "
               "пароль не зміниться."),
    },
}


def render(kind: Kind, language: str, **params: str | int) -> tuple[str, str]:
    """The e-mail subject and body in the player's language; a language not in LANGUAGES -- English."""
    lang: Language = next((code for code in LANGUAGES if code == language), "en")
    subject, body = TEMPLATES[kind][lang]
    return subject, body.format(**params)


def _send_smtp(message: EmailMessage) -> None:
    """Blocking send (we wait for the server no more than 20 s): called from ``send`` in a separate thread."""
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)


async def send(to: str, subject: str, body: str) -> None:
    """An e-mail via SMTP; without SMTP_HOST -- to the log. A send error is logged and not shown to the requester."""
    if not settings.SMTP_HOST:
        logger.info("mail (SMTP_HOST is empty, not sent) to=%s subject=%s\n%s", to, subject, body)
        return
    message = EmailMessage()
    message["From"] = settings.MAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        await asyncio.to_thread(_send_smtp, message)
    except (OSError, smtplib.SMTPException):
        logger.exception("mail to %s failed", to)
