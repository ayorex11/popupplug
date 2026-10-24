from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.home, name="home"),
    path("events/", views.event_list, name="list"),
    path("vendor-calls/", views.vendor_calls, name="vendor_calls"),
    path("events/new/", views.event_create, name="create"),
    path("e/<slug:slug>/", views.event_detail, name="detail"),
    path("e/<slug:slug>/edit/", views.event_edit, name="edit"),
    path("e/<slug:slug>/delete/", views.event_delete, name="delete"),
    path("e/<slug:slug>/interested/", views.toggle_interested, name="interested"),
]
