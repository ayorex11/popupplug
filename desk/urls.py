from django.urls import path

from . import views

app_name = "desk"

urlpatterns = [
    path("", views.home, name="home"),
    path("vendors/", views.vendors, name="vendors"),
    path("vendors/<int:pk>/", views.vendor_action, name="vendor_action"),
    path("events/", views.events, name="events"),
    path("events/<int:pk>/", views.event_action, name="event_action"),
    path("giveaway/", views.giveaway, name="giveaway"),
    path("giveaway/<int:pk>/", views.giveaway_action, name="giveaway_action"),
    path("instagram/", views.social, name="social"),
    path("instagram/<int:pk>/", views.social_action, name="social_action"),
]
