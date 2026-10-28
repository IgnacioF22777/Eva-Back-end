from django.urls import path

from . import views


urlpatterns = [
    # Alias histórico usado por el menú y los paneles.
    path(
        "tablero_metas/",
        views.compromiso_lista,
        name="tablero_metas",
    ),

    # Mantenedor de compromisos
    path(
        "compromisos/",
        views.compromiso_lista,
        name="compromiso_lista",
    ),
    path(
        "compromisos/nuevo/",
        views.compromiso_crear,
        name="compromiso_crear",
    ),
    path(
        "compromisos/<int:pk>/editar/",
        views.compromiso_editar,
        name="compromiso_editar",
    ),
    path(
        "compromisos/<int:pk>/estado/",
        views.compromiso_cambiar_estado,
        name="compromiso_cambiar_estado",
    ),

    path("", views.inicio, name="home_gestion"),
]
