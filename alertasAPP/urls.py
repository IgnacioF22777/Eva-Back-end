from django.urls import path

from . import views

app_name = "alertas"

urlpatterns = [
    path("", views.alerta_lista, name="lista"),
]
