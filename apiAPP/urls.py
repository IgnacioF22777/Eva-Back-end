from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from . import views


# ============================================================
# RUTAS DE LA API RESTFUL (todas bajo /api/)
# ============================================================
# Cada recurso tiene una ruta de colección (listar y crear) y una de
# detalle (consultar, modificar y dar de baja), más una acción para
# reactivar los registros dados de baja.

urlpatterns = [
    # Autenticación JWT
    path("token/", views.ObtenerTokenView.as_view(), name="api_token"),
    path(
        "token/refresh/",
        views.RenovarTokenView.as_view(),
        name="api_token_refresh",
    ),
    path("yo/", views.usuario_actual, name="api_usuario_actual"),

    # Delegaciones
    path(
        "delegaciones/",
        views.delegacion_lista,
        name="api_delegacion_lista",
    ),
    path(
        "delegaciones/<int:pk>/",
        views.delegacion_detalle,
        name="api_delegacion_detalle",
    ),
    path(
        "delegaciones/<int:pk>/reactivar/",
        views.delegacion_reactivar,
        name="api_delegacion_reactivar",
    ),

    # Servicios
    path("servicios/", views.servicio_lista, name="api_servicio_lista"),
    path(
        "servicios/<int:pk>/",
        views.servicio_detalle,
        name="api_servicio_detalle",
    ),
    path(
        "servicios/<int:pk>/reactivar/",
        views.servicio_reactivar,
        name="api_servicio_reactivar",
    ),

    # Compromisos del Tubo de Gestión
    path(
        "compromisos/",
        views.compromiso_lista,
        name="api_compromiso_lista",
    ),
    path(
        "compromisos/<int:pk>/",
        views.compromiso_detalle,
        name="api_compromiso_detalle",
    ),
    path(
        "compromisos/<int:pk>/reactivar/",
        views.compromiso_reactivar,
        name="api_compromiso_reactivar",
    ),

    # Catálogo de actividades
    path("catalogo/", views.catalogo_lista, name="api_catalogo_lista"),
    path(
        "catalogo/<int:pk>/",
        views.catalogo_detalle,
        name="api_catalogo_detalle",
    ),
    path(
        "catalogo/<int:pk>/reactivar/",
        views.catalogo_reactivar,
        name="api_catalogo_reactivar",
    ),

    # Períodos de medición
    path("periodos/", views.periodo_lista, name="api_periodo_lista"),
    path(
        "periodos/<int:pk>/",
        views.periodo_detalle,
        name="api_periodo_detalle",
    ),

    # Metas
    path("metas/", views.meta_lista, name="api_meta_lista"),
    path("metas/<int:pk>/", views.meta_detalle, name="api_meta_detalle"),
    path(
        "metas/<int:pk>/reactivar/",
        views.meta_reactivar,
        name="api_meta_reactivar",
    ),

    # Documentación OpenAPI
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "swagger/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]
