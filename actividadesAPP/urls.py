
"""Rutas de registro de actividades diarias del SGR (EVA 3)."""

from django.urls import path

from . import seguimiento, views
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
    # Verificación por el delegado y tubo de seguimiento (Eva 3)
    path("verificacion/", seguimiento.verificacion_lista, name="verificacion"),
    path("<int:pk>/verificar/", seguimiento.actividad_verificar, name="verificar"),
    path("tubo/", seguimiento.tubo, name="tubo"),
    path("<int:pk>/tubo-estado/", seguimiento.tubo_cambiar_estado, name="tubo_estado"),
    path("<int:pk>/evidencia/", seguimiento.evidencia_descargar, name="evidencia"),
    path(
        "<int:pk>/cambiar-estado/",
        views.actividad_cambiar_estado,
        name="cambiar_estado",
    ),
]
