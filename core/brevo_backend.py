"""Send email through Brevo's HTTPS API instead of SMTP.

Render's free web services block outbound SMTP ports (25, 465, 587), so SMTP can't work there.
An HTTPS call to api.brevo.com goes through normally.
"""
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

API_URL = "https://api.brevo.com/v3/smtp/email"


def _person(address):
    name, email = parseaddr(address)
    return {"email": email, **({"name": name} if name else {})}


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            payload = {
                "sender": _person(message.from_email or settings.DEFAULT_FROM_EMAIL),
                "to": [_person(a) for a in message.to],
                "subject": message.subject,
                "textContent": message.body or " ",
            }
            for content, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    payload["htmlContent"] = content
            if message.cc:
                payload["cc"] = [_person(a) for a in message.cc]
            if message.reply_to:
                payload["replyTo"] = _person(message.reply_to[0])
            try:
                resp = requests.post(API_URL, json=payload, timeout=15,
                                     headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"})
                if resp.status_code >= 300:
                    raise RuntimeError(f"Brevo API {resp.status_code}: {resp.text[:300]}")
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent