from django.urls import path

from . import dashboard, views

app_name = "puntaje_equipo"

urlpatterns = [
    path("", views.puntaje_equipo, name="equipo"),
    path("dashboard/", dashboard.dashboard, name="dashboard"),
]
