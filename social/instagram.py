"""Minimal Instagram Graph API client (Instagram Login flavour, host graph.instagram.com).

Flow: create a media container from a public image URL, wait until it's FINISHED,
then publish it. The access token lives in the database and is refreshed
opportunistically whenever we post, so no scheduler is needed.
"""
import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from .models import InstagramToken

log = logging.getLogger(__name__)
TIMEOUT = 20


class InstagramError(Exception):
    pass


def is_configured():
    return bool(settings.INSTAGRAM_ENABLED and settings.INSTAGRAM_USER_ID and (settings.INSTAGRAM_ACCESS_TOKEN or InstagramToken.objects.exists()))


def _api(path):
    version = f"/{settings.INSTAGRAM_API_VERSION}" if settings.INSTAGRAM_API_VERSION else ""
    return f"{settings.INSTAGRAM_API_HOST}{version}/{path.lstrip('/')}"


def _call(method, path, **params):
    try:
        resp = requests.request(method, _api(path), params=params if method == "GET" else None,
                                data=params if method == "POST" else None, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise InstagramError(f"Could not reach Instagram: {exc.__class__.__name__}") from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        raise InstagramError(f"Instagram said: {err.get('message') or resp.text[:200]} (HTTP {resp.status_code})")
    return data


def get_token():
    token = InstagramToken.objects.first()
    if token is None:
        if not settings.INSTAGRAM_ACCESS_TOKEN:
            raise InstagramError("No Instagram access token. Set INSTAGRAM_ACCESS_TOKEN.")
        token = InstagramToken.objects.create(
            access_token=settings.INSTAGRAM_ACCESS_TOKEN,
            expires_at=timezone.now() + timedelta(days=60),  # assumed; corrected on first refresh
        )
    elif settings.INSTAGRAM_ACCESS_TOKEN and token.refreshed_at is None and token.access_token != settings.INSTAGRAM_ACCESS_TOKEN:
        # You pasted a new token in the environment and we've never refreshed the old one.
        token.access_token = settings.INSTAGRAM_ACCESS_TOKEN
        token.expires_at = timezone.now() + timedelta(days=60)
        token.save()
    return token


def refresh_if_needed(token):
    """Refresh when the token is >24h old (an API requirement) and within 30 days of expiry."""
    now = timezone.now()
    last = token.refreshed_at or token.expires_at - timedelta(days=60) if token.expires_at else None
    if token.expires_at and token.expires_at - now > timedelta(days=30):
        return token
    if last and now - last < timedelta(hours=24):
        return token
    try:
        data = _call("GET", "refresh_access_token", grant_type="ig_refresh_token", access_token=token.access_token)
        token.access_token = data["access_token"]
        token.expires_at = now + timedelta(seconds=int(data.get("expires_in", 60 * 86400)))
        token.refreshed_at = now
        token.save()
        log.info("Instagram token refreshed; expires %s", token.expires_at)
    except (InstagramError, KeyError) as exc:
        log.warning("Instagram token refresh failed: %s", exc)
    return token


def token_days_left():
    token = InstagramToken.objects.first()
    if token and token.expires_at:
        return (token.expires_at - timezone.now()).days
    return None


def create_container(image_url, caption, token):
    data = _call("POST", f"{settings.INSTAGRAM_USER_ID}/media", image_url=image_url, caption=caption, access_token=token)
    return data["id"]


def wait_until_ready(container_id, token, timeout=90):
    deadline = time.monotonic() + timeout
    delay = 2
    while True:
        status = _call("GET", container_id, fields="status_code", access_token=token).get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Instagram could not process the image (status {status}).")
        if time.monotonic() + delay > deadline:
            raise InstagramError("Instagram is still processing the image. Try again in a minute.")
        time.sleep(delay)
        delay = min(delay * 2, 15)


def publish_container(container_id, token):
    return _call("POST", f"{settings.INSTAGRAM_USER_ID}/media_publish", creation_id=container_id, access_token=token)["id"]


def permalink(media_id, token):
    try:
        return _call("GET", media_id, fields="permalink", access_token=token).get("permalink", "")
    except InstagramError:
        return ""
