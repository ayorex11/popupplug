from django.urls import path

from . import views

app_name = "vendors"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("<slug:slug>/", views.public_profile, name="profile"),
]
