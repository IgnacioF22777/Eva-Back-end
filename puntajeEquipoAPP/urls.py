from django.urls import path

from . import views

app_name = "puntaje_equipo"

urlpatterns = [
    path("", views.puntaje_equipo, name="equipo"),
]
