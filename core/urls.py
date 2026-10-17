from django.urls import path

from . import seo, views

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("healthz", views.healthz),
    path("robots.txt", seo.robots_txt, name="robots"),
    path("sitemap.xml", seo.sitemap_xml, name="sitemap"),
]
