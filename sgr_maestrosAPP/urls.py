
from django.urls import path
from . import views


app_name = "sgr_maestros"


urlpatterns = [

    # ========================================================
    # CRUD 1: CATÁLOGO DE ACTIVIDADES
    # ========================================================

    path(
        "catalogo/",
        views.catalogo_lista,
        name="catalogo_lista"
    ),

    path(
        "catalogo/nuevo/",
        views.catalogo_crear,
        name="catalogo_crear"
    ),

    path(
        "catalogo/<int:pk>/editar/",
        views.catalogo_editar,
        name="catalogo_editar"
    ),

    path(
        "catalogo/<int:pk>/estado/",
        views.catalogo_cambiar_estado,
        name="catalogo_cambiar_estado"
    ),

    # ========================================================
    # CRUD 2: GESTIÓN DE PERÍODOS
    # ========================================================

    path(
        "periodos/",
        views.periodo_lista,
        name="periodo_lista"
    ),

    path(
        "periodos/nuevo/",
        views.periodo_crear,
        name="periodo_crear"
    ),

    path(
        "periodos/<int:pk>/editar/",
        views.periodo_editar,
        name="periodo_editar"
    ),

    # ========================================================
    # CRUD 3: DETALLE DE PERÍODO
    # ========================================================

    path(
        "detalle-periodos/",
        views.detalle_periodo_lista,
        name="detalle_periodo_lista"
    ),

    path(
        "detalle-periodos/nuevo/",
        views.detalle_periodo_crear,
        name="detalle_periodo_crear"
    ),

    path(
        "detalle-periodos/<int:pk>/editar/",
        views.detalle_periodo_editar,
        name="detalle_periodo_editar"
    ),

    path(
        "detalle-periodos/<int:pk>/eliminar/",
        views.detalle_periodo_eliminar,
        name="detalle_periodo_eliminar"
    ),

    # ========================================================
    # CRUD 4: GESTIÓN DE METAS
    # ========================================================

    path(
        "metas/",
        views.meta_lista,
        name="meta_lista"
    ),

    path(
        "metas/nueva/",
        views.meta_crear,
        name="meta_crear"
    ),

    path(
        "metas/<int:pk>/editar/",
        views.meta_editar,
        name="meta_editar"
    ),

    path(
        "metas/<int:pk>/estado/",
        views.meta_cambiar_estado,
        name="meta_cambiar_estado"
    ),

]
