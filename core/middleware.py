from django.http import HttpResponse


class HealthCheckMiddleware:
    """Answer /healthz before host validation and HTTPS redirects, so Render's health check
    and uptime monitors always get a plain 200, whatever Host header they send."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in ("/healthz", "/healthz/"):
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
