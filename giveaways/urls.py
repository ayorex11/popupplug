from django.urls import path

from . import views

app_name = "giveaways"

urlpatterns = [
    path("e/<slug:slug>/giveaway/", views.enter, name="enter"),
]
