from django.urls import path

from . import views


urlpatterns = [
    path("", views.inicio, name="inicio"),

    # Alias histórico: el menú y la portada usan "lista".
    path("lista/", views.delegacion_lista, name="lista"),

    # Mantenedor de delegaciones
    path(
        "delegaciones/",
        views.delegacion_lista,
        name="delegacion_lista",
    ),
    path(
        "delegaciones/nueva/",
        views.delegacion_crear,
        name="delegacion_crear",
    ),
    path(
        "delegaciones/<int:pk>/",
        views.delegacion_detalle,
        name="delegacion_detalle",
    ),
    path(
        "delegaciones/<int:pk>/editar/",
        views.delegacion_editar,
        name="delegacion_editar",
    ),
    path(
        "delegaciones/<int:pk>/estado/",
        views.delegacion_cambiar_estado,
        name="delegacion_cambiar_estado",
    ),

    # Servicios anidados por delegación
    path(
        "delegaciones/<int:delegacion_pk>/servicios/nuevo/",
        views.servicio_crear,
        name="servicio_crear",
    ),
    path(
        "servicios/<int:pk>/editar/",
        views.servicio_editar,
        name="servicio_editar",
    ),
    path(
        "servicios/<int:pk>/estado/",
        views.servicio_cambiar_estado,
        name="servicio_cambiar_estado",
    ),
]
