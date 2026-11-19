from django.urls import path

from . import api


# Rutas de la API (se incluyen bajo /api/ desde apiAPP/urls.py).
urlpatterns = [
    # Reportes ciudadanos
    path("reportes/", api.reporte_lista, name="api_reporte_lista"),
    path("reportes/<int:pk>/", api.reporte_detalle, name="api_reporte_detalle"),
    path(
        "reportes/<int:pk>/reactivar/",
        api.reporte_reactivar,
        name="api_reporte_reactivar",
    ),
    path(
        "reportes/<int:pk>/resolver/",
        api.reporte_resolver,
        name="api_reporte_resolver",
    ),

    # Transacción: derivaciones
    path("derivaciones/", api.derivacion_lista, name="api_derivacion_lista"),
    path(
        "derivaciones/<int:pk>/",
        api.derivacion_detalle,
        name="api_derivacion_detalle",
    ),
]
