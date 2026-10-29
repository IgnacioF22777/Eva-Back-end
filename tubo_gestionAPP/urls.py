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

    # Fase 4: asignación, avance e historial
    path(
        "compromisos/<int:pk>/asignar/",
        views.compromiso_asignar,
        name="compromiso_asignar",
    ),
    path(
        "compromisos/<int:pk>/avance/",
        views.compromiso_avance,
        name="compromiso_avance",
    ),
    path(
        "compromisos/<int:pk>/historial/",
        views.compromiso_historial,
        name="compromiso_historial",
    ),

    path("", views.inicio, name="home_gestion"),
]
