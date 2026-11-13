
"""Rutas de registro de actividades diarias del SGR (EVA 3)."""

from django.urls import path

from . import views

app_name = "actividades"

urlpatterns = [
    path("", views.actividad_lista, name="lista"),
    path("nueva/", views.actividad_crear, name="crear"),
    path("<int:pk>/editar/", views.actividad_editar, name="editar"),
    path(
        "<int:pk>/cambiar-estado/",
        views.actividad_cambiar_estado,
        name="cambiar_estado",
    ),
]
