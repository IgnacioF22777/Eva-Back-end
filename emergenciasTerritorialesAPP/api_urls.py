from django.urls import path

from . import api


# Rutas de la API (se incluyen bajo /api/ desde apiAPP/urls.py).
urlpatterns = [
    # Mantenedor 1: zonas de riesgo
    path("zonas-riesgo/", api.zona_lista, name="api_zona_lista"),
    path("zonas-riesgo/<int:pk>/", api.zona_detalle, name="api_zona_detalle"),
    path(
        "zonas-riesgo/<int:pk>/reactivar/",
        api.zona_reactivar,
        name="api_zona_reactivar",
    ),

    # Mantenedor 2: contactos de emergencia
    path("contactos-emergencia/", api.contacto_lista, name="api_contacto_lista"),
    path(
        "contactos-emergencia/<int:pk>/",
        api.contacto_detalle,
        name="api_contacto_detalle",
    ),
    path(
        "contactos-emergencia/<int:pk>/reactivar/",
        api.contacto_reactivar,
        name="api_contacto_reactivar",
    ),
]
