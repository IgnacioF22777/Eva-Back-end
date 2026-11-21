from django.urls import path

from . import api_asignaciones, api_avances


# Rutas de la API de las transacciones T1 y T2 (se incluyen bajo /api/
# desde apiAPP/urls.py).
urlpatterns = [
    path(
        "asignaciones/",
        api_asignaciones.asignacion_lista,
        name="api_asignacion_lista",
    ),
    path(
        "asignaciones/<int:pk>/",
        api_asignaciones.asignacion_detalle,
        name="api_asignacion_detalle",
    ),
    path("avances/", api_avances.avance_lista, name="api_avance_lista"),
    path("avances/<int:pk>/", api_avances.avance_detalle, name="api_avance_detalle"),
]
