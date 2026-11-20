from django.urls import path

from . import api_avances


# Rutas de la API de la transacción T2 (se incluyen bajo /api/ desde
# apiAPP/urls.py).
urlpatterns = [
    path("avances/", api_avances.avance_lista, name="api_avance_lista"),
    path("avances/<int:pk>/", api_avances.avance_detalle, name="api_avance_detalle"),
]
