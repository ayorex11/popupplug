"""Creating and publishing SocialPosts. Everything here is safe to call from signals and views."""
import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from core.notifications import absolute_url

from . import cards, instagram
from .models import SocialPost

log = logging.getLogger(__name__)


def enabled():
    return settings.INSTAGRAM_ENABLED


def queue_event_post(event):
    """Make the card + caption for a newly published event. Never raises."""
    if not enabled() or SocialPost.objects.filter(event=event, kind=SocialPost.Kind.EVENT).exists():
        return None
    try:
        post = SocialPost(kind=SocialPost.Kind.EVENT, event=event, vendor=event.vendor, caption=cards.event_caption(event))
        post.image.save(f"event-{event.pk}.jpg", cards.render_event_card(event), save=False)
        post.save()
    except Exception:  # noqa: BLE001
        log.exception("Could not build Instagram card for event %s", event.pk)
        return None
    if settings.INSTAGRAM_AUTOPOST and instagram.is_configured():
        transaction.on_commit(lambda: _run(post.pk))
    return post


def queue_welcome_post(vendor):
    if not enabled() or SocialPost.objects.filter(vendor=vendor, kind=SocialPost.Kind.WELCOME).exists():
        return None
    try:
        post = SocialPost(kind=SocialPost.Kind.WELCOME, vendor=vendor, caption=cards.welcome_caption(vendor))
        post.image.save(f"welcome-{vendor.pk}.jpg", cards.render_welcome_card(vendor), save=False)
        post.save()
        return post
    except Exception:  # noqa: BLE001
        log.exception("Could not build welcome card for vendor %s", vendor.pk)
        return None


def regenerate(post):
    """Rebuild the card and caption (after the event or vendor was edited)."""
    if post.kind == post.Kind.EVENT and post.event:
        post.image.save(f"event-{post.event.pk}.jpg", cards.render_event_card(post.event), save=False)
        post.caption = cards.event_caption(post.event)
    elif post.vendor:
        post.image.save(f"welcome-{post.vendor.pk}.jpg", cards.render_welcome_card(post.vendor), save=False)
        post.caption = cards.welcome_caption(post.vendor)
    post.save()


def _run(post_id):
    if settings.NOTIFY_ASYNC:
        def target():
            try:
                publish(post_id)
            except Exception:  # noqa: BLE001
                log.exception("Instagram autopost failed for post %s", post_id)
            finally:
                close_old_connections()
        threading.Thread(target=target, daemon=True).start()
    else:
        try:
            publish(post_id)
        except Exception:  # noqa: BLE001
            log.exception("Instagram autopost failed for post %s", post_id)


def publish(post_id):
    """Post to Instagram. Returns a short message. Raises nothing the caller must handle."""
    claimed = SocialPost.objects.filter(pk=post_id, status__in=[SocialPost.Status.DRAFT, SocialPost.Status.FAILED]).update(
        status=SocialPost.Status.POSTING)
    if not claimed:
        return "Already posted or being posted."
    post = SocialPost.objects.get(pk=post_id)

    if settings.INSTAGRAM_DRY_RUN:
        post.status, post.note = SocialPost.Status.DRAFT, "Dry run OK: card and caption built, nothing was sent to Instagram."
        post.save(update_fields=["status", "note"])
        return post.note
    try:
        if not instagram.is_configured():
            raise instagram.InstagramError("Instagram isn't configured (see DEPLOY.md, Instagram).")
        token = instagram.refresh_if_needed(instagram.get_token())
        if not post.ig_container_id:
            post.ig_container_id = instagram.create_container(absolute_url(post.image.url), post.caption, token.access_token)
            post.save(update_fields=["ig_container_id"])
        instagram.wait_until_ready(post.ig_container_id, token.access_token)
        post.ig_media_id = instagram.publish_container(post.ig_container_id, token.access_token)
        post.permalink = instagram.permalink(post.ig_media_id, token.access_token)
        post.status, post.posted_at, post.note = SocialPost.Status.POSTED, timezone.now(), ""
        post.save()
        return "Posted to Instagram."
    except Exception as exc:  # noqa: BLE001
        log.warning("Instagram post %s failed: %s", post_id, exc)
        post.status, post.note = SocialPost.Status.FAILED, str(exc)[:300]
        post.save(update_fields=["status", "note"])
        return post.note
