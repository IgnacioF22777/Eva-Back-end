from django.contrib import admin

from .models import CampanaRegalo, NinoInscrito


@admin.register(CampanaRegalo)
class CampanaRegaloAdmin(admin.ModelAdmin):
    list_display = ("__str__", "fecha_inicio", "fecha_fin", "edad_maxima", "activo")
    list_filter = ("tipo", "anio", "activo")


@admin.register(NinoInscrito)
class NinoInscritoAdmin(admin.ModelAdmin):
    list_display = ("rut", "nombre", "apellido", "sexo", "campana", "delegacion", "activo")
    list_filter = ("campana", "delegacion", "sexo", "activo")
    search_fields = ("rut", "nombre", "apellido")
