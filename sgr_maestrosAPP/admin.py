
from django.contrib import admin

from .models import (
    CatalogoActividad,
    Periodo,
    DetallePeriodo,
    Meta,
)


# ============================================================
# ADMINISTRACIÓN DEL CATÁLOGO DE ACTIVIDADES
# ============================================================

@admin.register(CatalogoActividad)
class CatalogoActividadAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "area",
        "activo",
    )

    search_fields = (
        "codigo",
        "nombre",
        "area",
    )

    list_filter = (
        "activo",
        "area",
    )

    list_per_page = 20

    ordering = ("nombre",)


# ============================================================
# ADMINISTRACIÓN DE PERÍODOS
# ============================================================

@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "fecha_inicio",
        "fecha_fin",
        "cerrado",
    )

    search_fields = (
        "codigo",
        "nombre",
    )

    list_filter = (
        "cerrado",
        "fecha_inicio",
    )

    list_per_page = 20

    ordering = ("-fecha_inicio",)


# ============================================================
# ADMINISTRACIÓN DE DETALLES DE PERÍODO
# ============================================================

@admin.register(DetallePeriodo)
class DetallePeriodoAdmin(admin.ModelAdmin):

    list_display = (
        "nombre",
        "periodo",
        "fecha_inicio",
        "fecha_fin",
        "dias_computables",
    )

    search_fields = (
        "nombre",
        "periodo__codigo",
        "periodo__nombre",
    )

    list_filter = (
        "periodo",
    )

    list_select_related = (
        "periodo",
    )

    list_per_page = 20


# ============================================================
# ADMINISTRACIÓN DE METAS
# ============================================================

@admin.register(Meta)
class MetaAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "periodo",
        "actividad",
        "valor_objetivo",
        "ponderacion",
        "activo",
    )

    search_fields = (
        "codigo",
        "nombre",
        "periodo__nombre",
        "actividad__nombre",
    )

    list_filter = (
        "activo",
        "periodo",
    )

    list_select_related = (
        "periodo",
        "actividad",
    )

    list_per_page = 20

    ordering = ("nombre",)
