
"""Rutas de registro de actividades diarias del SGR (EVA 3)."""

from django.urls import path

from . import views
from .matriz import matriz

app_name = "actividades"

urlpatterns = [
    path("matriz/", matriz, name="matriz"),
    path("", views.actividad_lista, name="lista"),
    path("nueva/", views.actividad_crear, name="crear"),
    # Exportación a Excel y PDF de los registros propios
    path("exportar/excel/", views.exportar_actividades_excel, name="exportar_excel"),
    path("exportar/pdf/", views.exportar_actividades_pdf, name="exportar_pdf"),
    path("<int:pk>/editar/", views.actividad_editar, name="editar"),
    path(
        "<int:pk>/cambiar-estado/",
        views.actividad_cambiar_estado,
        name="cambiar_estado",
    ),
]
