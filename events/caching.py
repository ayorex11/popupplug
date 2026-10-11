"""Cheap full-page caching for anonymous visitors.

Event lists are read-heavy and identical for everyone who isn't logged in, so we
cache the rendered HTML for a couple of minutes. That alone absorbs most traffic
spikes. Logged-in users (and anyone with a session cookie) always get fresh pages.

Pages cached this way must never contain per-user content or CSRF tokens.
A version key is bumped whenever an event changes, so edits show up immediately.
"""
import functools
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

VERSION_KEY = "events:version"


def bump_version():
    cache.set(VERSION_KEY, time.time_ns(), None)


def _version():
    version = cache.get(VERSION_KEY)
    if version is None:
        version = time.time_ns()
        cache.set(VERSION_KEY, version, None)
    return version


def cache_public(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        ttl = settings.PUBLIC_PAGE_CACHE_SECONDS
        cacheable = (
            ttl > 0
            and request.method == "GET"
            and not request.user.is_authenticated
            and settings.SESSION_COOKIE_NAME not in request.COOKIES
        )
        if not cacheable:
            return view(request, *args, **kwargs)

        key = f"page:{_version()}:{request.get_full_path()}"
        if len(key) > 200:  # memcached-style key limit safety
            return view(request, *args, **kwargs)
        cached = cache.get(key)
        if cached is not None:
            return HttpResponse(cached)

        response = view(request, *args, **kwargs)
        if response.status_code == 200 and hasattr(response, "render"):
            response.render()
        if response.status_code == 200:
            cache.set(key, response.content, ttl)
        return response

    return wrapper
