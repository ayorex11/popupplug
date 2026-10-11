from django.http import HttpResponse


def healthz(request):
    """Cheap liveness check for Render and uptime monitors. Deliberately touches no database."""
    return HttpResponse("ok", content_type="text/plain")
