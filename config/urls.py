from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views

from vendors.forms import EmailAuthenticationForm
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html", authentication_form=EmailAuthenticationForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("desk/", include("desk.urls")),
    path("vendors/", include("vendors.urls")),
    path("", include("core.urls")),
    path("", include("events.urls")),
]

# Local media in development only. In production, images live in the S3-compatible bucket.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
