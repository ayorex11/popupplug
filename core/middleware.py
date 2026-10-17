from django.http import HttpResponse

from .seo import PRIVATE_PATHS


class HealthCheckMiddleware:
    """Answer /healthz before host validation and HTTPS redirects, so Render's health check
    and uptime monitors always get a plain 200, whatever Host header they send."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in ("/healthz", "/healthz/"):
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)


class NoIndexMiddleware:
    """Belt and braces: private pages carry X-Robots-Tag: noindex even if a template forgets the meta tag."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if PRIVATE_PATHS.match(request.path):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
